"""Unit tests (no database) for read_catalog_rows and preview_table_rows defensive behavior."""
from __future__ import annotations

import json
from contextlib import contextmanager
from decimal import Decimal
from typing import Any

import pytest

from app.tools import build_default_registry
from app.tools.catalog_rows import COLUMNS_SQL, PRIMARY_KEY_SQL
from app.tools.preview import ORDERING, PREVIEW_SQL
from app.tools.registry import ToolError
from app.tools.rows import CursorCodec, jsonable, load_exact


class ScriptedReader:
    """Dispatches fixed SQL strings and psycopg Composed statements to scripted answers."""

    def __init__(self, answer) -> None:
        self.answer = answer
        self.calls: list[tuple[str, tuple]] = []

    @contextmanager
    def read_only(self):
        def run(statement: Any, params: tuple) -> list[dict]:
            text = statement if isinstance(statement, str) else statement.as_string(None)
            self.calls.append((text, params))
            return self.answer(text, params)

        yield run


def preview_payload(table: str, rows: int, **overrides: Any) -> str:
    payload = {
        "table_name": table, "order_by": ORDERING[table][0], "row_limit": 20,
        "columns": [{"name": "date", "type": "date", "nullable": False},
                    {"name": "close", "type": "numeric", "nullable": False}],
        "rows": [{"date": f"2026-08-{i + 1:02d}", "close": 1.5} for i in range(rows)],
        **overrides,
    }
    return json.dumps(payload)


def preview_reader(payload: str) -> ScriptedReader:
    return ScriptedReader(lambda text, params: [{"payload": payload}] if text == PREVIEW_SQL else [])


def run_tool(reader, name: str, arguments: dict, **options):
    registry = build_default_registry(reader, cursor_secret=b"k", **options)
    return registry.execute("c1", name, json.dumps(arguments))


# --- rows helpers --------------------------------------------------------------------------------

def test_numbers_are_exact_and_integers_stay_integers() -> None:
    parsed = load_exact('{"a": 12345678901234567.89, "b": 7, "c": [0.1, {"d": 2.50}]}')
    assert parsed["a"] == Decimal("12345678901234567.89")
    assert jsonable(parsed) == {"a": "12345678901234567.89", "b": 7, "c": ["0.1", {"d": "2.50"}]}


def test_cursor_round_trip_and_tamper_detection() -> None:
    codec = CursorCodec(b"secret")
    token = codec.encode("AI_column_catalog", ["Feature_02_Broker_Rolling", "net_value_1d"])
    assert codec.decode(token, "AI_column_catalog", 2) == ["Feature_02_Broker_Rolling", "net_value_1d"]
    for bad_token, catalog, length in (
        (token, "AI_table_catalog", 2),
        (token, "AI_column_catalog", 1),
        (token[:-3] + "AAA", "AI_column_catalog", 2),
        ("garbage", "AI_column_catalog", 2),
        (CursorCodec(b"other").encode("AI_column_catalog", ["a", "b"]), "AI_column_catalog", 2),
        (codec.encode("AI_column_catalog", [True, "b"]), "AI_column_catalog", 2),
    ):
        with pytest.raises(ToolError, match="cursor is invalid"):
            codec.decode(bad_token, catalog, length)


# --- read_catalog_rows ---------------------------------------------------------------------------

def catalog_reader(rows: int, row_bytes: int = 50) -> ScriptedReader:
    def answer(text: str, params: tuple) -> list[dict]:
        if text == COLUMNS_SQL:
            return [{"name": "coverage_id", "type": "bigint", "nullable": False},
                    {"name": "note", "type": "text", "nullable": True}]
        if text == PRIMARY_KEY_SQL:
            return [{"name": "coverage_id"}]
        if "count(*)" in text:
            return [{"total_rows": rows, "rows_before": 0}]
        start = params[0] if len(params) == 2 else 0
        limit = params[-1]
        return [
            {"__row_json": json.dumps({"coverage_id": i, "note": "x" * row_bytes}), "__key_0": i}
            for i in range(start + 1, min(rows, start + limit) + 1)
        ]
    return ScriptedReader(answer)


def test_page_size_page_signals_more_rows_and_continues_exactly() -> None:
    reader = catalog_reader(rows=5)
    first = run_tool(reader, "read_catalog_rows", {"catalog_name": "AI_data_coverage", "page_size": 2, "cursor": None})
    result = first.output["result"]
    assert [row[0] for row in result["rows"]] == [1, 2]
    assert result["has_more"] is True and result["page_limited_by"] == "PAGE_SIZE"
    page_sql, params = next((text, params) for text, params in reader.calls if "LIMIT %s" in text)
    assert params == (3,) and '"public"."AI_data_coverage"' in page_sql
    second = run_tool(reader, "read_catalog_rows", {
        "catalog_name": "AI_data_coverage", "page_size": 2, "cursor": result["next_cursor"]})
    assert [row[0] for row in second.output["result"]["rows"]] == [3, 4]


def test_single_oversized_row_is_an_explicit_error() -> None:
    reader = catalog_reader(rows=3, row_bytes=6000)
    outcome = run_tool(reader, "read_catalog_rows", {"catalog_name": "AI_data_coverage", "page_size": 10, "cursor": None},
                       page_max_bytes=4096)
    assert outcome.error_code == "TOOL_ERROR" and "single AI_data_coverage row" in outcome.output["error"]["message"]


def test_missing_primary_key_makes_paging_impossible_not_unstable() -> None:
    reader = ScriptedReader(lambda text, params: [{"name": "x", "type": "text", "nullable": True}] if text == COLUMNS_SQL else [])
    outcome = run_tool(reader, "read_catalog_rows", {"catalog_name": "AI_table_catalog", "page_size": None, "cursor": None})
    assert outcome.error_code == "TOOL_ERROR" and "stable paging is impossible" in outcome.output["error"]["message"]


# --- preview_table_rows --------------------------------------------------------------------------

def test_valid_preview_is_returned_as_aligned_rows() -> None:
    outcome = run_tool(preview_reader(preview_payload("Price_Stock_Indonesia_IDX", 3)),
                       "preview_table_rows", {"table_name": "Price_Stock_Indonesia_IDX"})
    result = outcome.output["result"]
    assert result["rows"][0] == ["2026-08-01", "1.5"]
    assert result["returned_rows"] == 3 and result["row_limit"] == 20 and result["is_sample"] is True


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (preview_payload("Price_Stock_Indonesia_IDX", 21), "20-row contract"),
        (preview_payload("Price_Stock_Indonesia_IDX", 3, row_limit=100), "20-row contract"),
        (preview_payload("Price_Stock_Indonesia_IDX", 3, table_name="Feature_01_Stock_Daily"), "unexpected response"),
        (preview_payload("Price_Stock_Indonesia_IDX", 3, order_by="date ASC"), "ordering does not match"),
        (json.dumps({"unexpected": True}), "unexpected response"),
    ],
)
def test_database_contract_violations_return_nothing(payload: str, message: str) -> None:
    outcome = run_tool(preview_reader(payload), "preview_table_rows", {"table_name": "Price_Stock_Indonesia_IDX"})
    assert outcome.error_code == "TOOL_ERROR" and message in outcome.output["error"]["message"]


def test_oversized_preview_is_an_explicit_error_not_partial() -> None:
    wide = json.dumps({**json.loads(preview_payload("IDX_Stock_Universe", 0)),
                       "rows": [{"date": "x" * 3000, "close": 1} for _ in range(20)]})
    outcome = run_tool(preview_reader(wide), "preview_table_rows", {"table_name": "IDX_Stock_Universe"})
    assert outcome.error_code == "TOOL_ERROR" and "No partial preview" in outcome.output["error"]["message"]


def test_preview_can_be_disabled_without_affecting_catalog_tools() -> None:
    registry = build_default_registry(preview_reader("{}"), preview_enabled=False)
    assert "preview_table_rows" not in registry.names() and "read_catalog_rows" in registry.names()


def test_preview_schema_lists_exactly_seven_tables() -> None:
    registry = build_default_registry(preview_reader("{}"))
    [definition] = [d for d in registry.definitions() if d["name"] == "preview_table_rows"]
    assert definition["parameters"]["properties"]["table_name"]["enum"] == sorted(ORDERING, key=list(ORDERING).index)
    assert len(ORDERING) == 7 and definition["parameters"]["required"] == ["table_name"]
