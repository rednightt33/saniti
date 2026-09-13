from __future__ import annotations

import pytest

from app.config import Settings
from app.schemas import FINAL_RESPONSE_SCHEMA
from app.tools import ToolError, ToolRegistry


def test_evidence_recording_is_always_exposed() -> None:
    assert ToolRegistry.ALWAYS_EXPOSED == {"record_evidence"}


def test_malformed_evidence_call_is_recoverable_before_database_access() -> None:
    registry = object.__new__(ToolRegistry)
    with pytest.raises(ToolError, match="missing required fields.*evidence_type"):
        registry.record_evidence(
            {
                "claim": "Observed result",
                "compact_payload_json": "{}",
                "source_tables": ["Feature_01_Stock_Daily"],
            },
            "request-id",
        )


class CatalogOnlyRegistry(ToolRegistry):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _catalog(self, table: str):
        if table != "Feature_01_Stock_Daily":
            raise ToolError("Unknown table")
        return {
            "date": {"is_filterable": True, "is_groupable": False},
            "ticker": {"is_filterable": True, "is_groupable": True},
            "return_1d_pct": {"is_filterable": True, "is_groupable": False},
        }


def base_query() -> dict:
    return {
        "table": "Feature_01_Stock_Daily", "columns": ["date", "ticker", "return_1d_pct"],
        "tickers": ["BBCA"], "start_date": "2026-01-01", "end_date": "2026-02-01",
        "filters": None, "order_by": [{"column": "date", "direction": "asc"}], "limit": 100,
    }


def test_query_requires_catalog_allowlist() -> None:
    registry = CatalogOnlyRegistry(Settings.from_env(require_runtime_secrets=False))
    query = base_query(); query["columns"].append("raw_secret")
    with pytest.raises(ToolError, match="not active"):
        registry._validate_query(query)


def test_unbounded_cross_section_is_rejected() -> None:
    registry = CatalogOnlyRegistry(Settings.from_env(require_runtime_secrets=False))
    query = base_query(); query.update({"tickers": None, "start_date": None, "end_date": None})
    with pytest.raises(ToolError, match="ticker filter or bounded date range"):
        registry._validate_query(query)


def test_unfiltered_date_range_has_smaller_ceiling() -> None:
    registry = CatalogOnlyRegistry(Settings.from_env(require_runtime_secrets=False))
    query = base_query(); query.update({"tickers": None, "start_date": "2026-01-01", "end_date": "2026-03-01"})
    with pytest.raises(ToolError, match="31 days"):
        registry._validate_query(query)


def _assert_strict_objects(schema: dict) -> None:
    if schema.get("type") == "object":
        assert schema.get("additionalProperties") is False
        assert set(schema.get("required", [])) == set(schema.get("properties", {}))
    for value in schema.values():
        if isinstance(value, dict):
            _assert_strict_objects(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _assert_strict_objects(item)


def test_every_tool_and_final_schema_is_strict() -> None:
    for name in ToolRegistry(None, Settings.from_env(require_runtime_secrets=False)).handlers:
        _assert_strict_objects(ToolRegistry.schema_for(name))
    _assert_strict_objects(FINAL_RESPONSE_SCHEMA)


def test_estimate_uses_largest_plan_node() -> None:
    plan = {"Plan Rows": 100, "Plans": [{"Plan Rows": 9000}, {"Plan Rows": 500}]}
    assert ToolRegistry._estimated_rows(plan) == 9000
