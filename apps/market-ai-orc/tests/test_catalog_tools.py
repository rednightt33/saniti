from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any

import pytest

from app.catalog_store import CatalogStore
from app.compaction import dumps
from app.orchestrator import SYSTEM_PROMPT
from app.tools import ToolError, build_default_registry
from app.tools import catalog as catalog_module
from app.tools.catalog import (
    CALCULATIONS_SQL, COLUMNS_SQL, COVERAGE_DATASET_SQL, COVERAGE_ENTITIES_SQL, COVERAGE_STATUS_SQL,
    DISCOVER_SQL, FOUND_COLUMNS_SQL, RELATIONSHIPS_SQL, RESOLVE_TABLES_SQL,
)
from app.tools.registry import DEFAULT_MAX_RESULT_BYTES

ALL_SQL = {
    DISCOVER_SQL, RESOLVE_TABLES_SQL, COLUMNS_SQL, FOUND_COLUMNS_SQL, RELATIONSHIPS_SQL,
    CALCULATIONS_SQL, COVERAGE_DATASET_SQL, COVERAGE_STATUS_SQL, COVERAGE_ENTITIES_SQL,
}


class FakeReader:
    """Answers the module's fixed SQL constants with scripted rows and records every call."""

    def __init__(self, responses: dict[str, Any] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    @contextmanager
    def read_only(self):
        def run(statement: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
            self.calls.append((statement, params))
            answer = self.responses.get(statement, [])
            return list(answer(params) if callable(answer) else answer)

        yield run


def table_row(name: str, **extra: Any) -> dict[str, Any]:
    return {
        "table_name": name, "description": f"{name} description", "category": "FEATURE",
        "grain": "date x ticker", "primary_key_columns": ["date", "ticker"], "time_column": "date",
        "entity_column": "ticker", "documentation_status": "VERIFIED", "coverage_enabled": True,
        "freshness_sla": "1 day", "column_count": 2, "calculation_count": 1, "relationship_count": 1,
        **extra,
    }


def resolve(*names: str, coverage: bool = True):
    return lambda params: [
        {"table_name": name, "coverage_enabled": coverage} for name in names if name in params[0]
    ]


def column_row(table: str, column: str, **extra: Any) -> dict[str, Any]:
    return {
        "table_name": table, "column_name": column, "description": f"{column} meaning",
        "data_type": "numeric", "semantic_type": "MEASURE", "unit": "IDR", "nullable": False,
        "is_primary_key": False, "source_column_or_expression": None,
        "allowed_aggregations": ["SUM"], "filter_allowed": True, "group_by_allowed": False,
        "example_value": None, "documentation_status": "VERIFIED", "total_matching": 1, **extra,
    }


def execute(registry, name: str, arguments: dict[str, Any] | str):
    raw = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return registry.execute("call_1", name, raw)


def details_args(**overrides: Any) -> dict[str, Any]:
    return {"table_names": ["Feature_02_Broker_Rolling"], "sections": ["COLUMNS"],
            "column_names": None, "entity_ids": None, **overrides}


# 1. Registration and exposure -------------------------------------------------------------

def test_catalog_tools_are_registered_and_exposed() -> None:
    registry = build_default_registry(FakeReader())
    assert registry.names() == ["get_system_capabilities", "discover_catalog", "get_catalog_details", "read_catalog_rows", "preview_table_rows"]
    definitions = {tool["name"]: tool for tool in registry.definitions()}
    assert definitions["discover_catalog"]["parameters"]["properties"] == {}
    params = definitions["get_catalog_details"]["parameters"]
    assert params["required"] == ["table_names", "sections", "column_names", "entity_ids"]
    assert params["additionalProperties"] is False
    assert params["properties"]["sections"]["items"]["enum"] == [
        "COLUMNS", "RELATIONSHIPS", "CALCULATIONS", "COVERAGE",
    ]
    assert all(tool["strict"] for tool in definitions.values())


def test_catalog_tools_absent_without_configured_catalog() -> None:
    registry = build_default_registry()
    assert registry.names() == ["get_system_capabilities"]
    caps = execute(registry, "get_system_capabilities", "{}").output["result"]
    assert caps["catalog_discovery"] is False and caps["database_query"] is False


def test_capabilities_report_catalog_discovery_only() -> None:
    caps = execute(build_default_registry(FakeReader()), "get_system_capabilities", "{}").output["result"]
    assert caps["catalog_discovery"] is True
    assert caps["database_query"] is False and caps["python_analysis"] is False


def test_system_prompt_ends_with_exact_data_discovery_block() -> None:
    block = """DATA DISCOVERY RULES
You have access to a catalog-governed data universe.
Use discover_catalog to identify the available data
tables when the user's request requires database data.
Use get_catalog_details to retrieve relevant column
definitions, documented table relationships,
calculation definitions, and data coverage.
Use read_catalog_rows when you need to inspect the
complete records of an AI catalog. You may retrieve
additional pages until the required catalog records
have been obtained.
Use preview_table_rows when you need to inspect
example records from an available market-data table.
This tool returns a maximum of 20 rows per call.
The catalog and preview tools enforce their
respective access restrictions.
Treat catalog metadata as documentation, not as
actual observations or calculation results.
Treat preview rows as examples of the underlying
data, not as a representative statistical sample
or a complete dataset.
Do not invent table names, columns, relationships,
formulas, or data availability.
Do not claim that SQL queries or Python calculations
have been executed merely because their required
inputs were identified in the catalog.
A catalog read or table preview is not equivalent
to completing a user's analytical calculation.
When the required execution capability is unavailable,
return a LIMITATION response explaining what has
been identified and what remains unexecuted."""
    assert SYSTEM_PROMPT.endswith("strict output schema.\n\n" + block)
    assert SYSTEM_PROMPT.count("DATA DISCOVERY RULES") == 1
    assert SYSTEM_PROMPT.startswith("You are the Saniti AI orchestration agent.")


# 2. discover_catalog ----------------------------------------------------------------------

def test_discover_returns_catalog_rows_verbatim() -> None:
    reader = FakeReader({DISCOVER_SQL: [table_row("Feature_02_Broker_Rolling"),
                                        table_row("IDX_Stock_Universe", time_column=None, category="REFERENCE")]})
    outcome = execute(build_default_registry(reader), "discover_catalog", "{}")
    assert outcome.ok
    result = outcome.output["result"]
    assert result["table_count"] == 2 and result["truncated"] is False
    first, second = result["tables"]
    assert first["table_name"] == "Feature_02_Broker_Rolling"
    assert first["description"] == "Feature_02_Broker_Rolling description"
    assert first["available_metadata"] == {"columns": 2, "calculations": 1, "relationships": 1}
    assert "time_column" not in second
    assert "documentation" in result["notice"]
    assert reader.calls == [(DISCOVER_SQL, (51,))]


def test_discover_keeps_null_description_and_reports_empty_catalog() -> None:
    reader = FakeReader({DISCOVER_SQL: [table_row("X_Table", description=None)]})
    result = execute(build_default_registry(reader), "discover_catalog", "{}").output["result"]
    assert result["tables"][0]["description"] is None
    empty = execute(build_default_registry(FakeReader()), "discover_catalog", "{}").output["result"]
    assert empty["tables"] == [] and "no tables" in empty["note"]


def test_visibility_rules_come_from_catalog_flags_not_an_allowlist() -> None:
    assert "is_active AND ai_access_level = 'BOUNDED_READ'" in DISCOVER_SQL
    assert "ai_allowed AND NOT is_sensitive" in COLUMNS_SQL
    assert "is_allowed" in RELATIONSHIPS_SQL and "visible" in RELATIONSHIPS_SQL
    assert "status = 'ACTIVE'" in CALCULATIONS_SQL
    source = open(catalog_module.__file__).read()
    assert "Feature_01_Stock_Daily" not in source and "Price_Stock_Indonesia_IDX" not in source


# 3. get_catalog_details: section routing ----------------------------------------------------

def test_each_section_reads_its_own_catalog_table() -> None:
    table = "Feature_02_Broker_Rolling"
    reader = FakeReader({
        RESOLVE_TABLES_SQL: resolve(table),
        COLUMNS_SQL: [column_row(table, "net_value_1d")],
        RELATIONSHIPS_SQL: [{
            "relationship_id": 4, "left_table": "IDX_Broker_Summary", "left_columns": ["Date", "Symbol"],
            "right_table": table, "right_columns": ["date", "ticker"], "relationship_type": "ONE_TO_ONE",
            "temporal_rule": "Exact source trading date", "safe_output_grain": "date x ticker",
            "requires_preaggregation": False, "description": "Source to Feature.", "version": "v1",
            "total_matching": 1,
        }],
        CALCULATIONS_SQL: [{
            "target_table": table, "calculation_name": "net_value_20d", "version": "v2",
            "target_columns": ["net_value_20d"], "definition": "Sum over 20 dates.",
            "required_inputs": {"source_tables": ["IDX_Broker_Summary"]}, "parameters": {},
            "defaults": {}, "alignment_rules": "Ticker calendar.", "missing_data_policy": "NULL early.",
            "output_definition": {"unit": "IDR"}, "total_matching": 1,
        }],
        COVERAGE_DATASET_SQL: [{
            "dataset_name": table, "coverage_mode": "EXPECTED_DERIVED",
            "reference_dataset_name": "IDX_Broker_Summary", "pipeline_status": "MANUAL_REFRESH_REQUIRED",
            "verification_status": "UNVERIFIED", "quality_status": "WARNING", "actual_min_date": None,
        }],
        COVERAGE_STATUS_SQL: [{"dataset_name": table, "pipeline_status": "MANUAL_REFRESH_REQUIRED",
                               "verification_status": "UNVERIFIED", "quality_status": "WARNING",
                               "entity_count": 4125}],
    })
    outcome = execute(build_default_registry(reader), "get_catalog_details", details_args(
        sections=["COLUMNS", "RELATIONSHIPS", "CALCULATIONS", "COVERAGE"]))
    assert outcome.ok
    sections = outcome.output["result"]["sections"]
    assert list(sections) == ["COLUMNS", "RELATIONSHIPS", "CALCULATIONS", "COVERAGE"]
    assert sections["COLUMNS"]["by_table"][table][0]["column_name"] == "net_value_1d"
    assert sections["RELATIONSHIPS"]["entries"][0]["left_columns"] == ["Date", "Symbol"]
    calc = sections["CALCULATIONS"]["by_table"][table][0]
    assert calc["definition"] == "Sum over 20 dates." and "parameters" not in calc
    coverage = sections["COVERAGE"]
    assert coverage["datasets"][table]["verification_status"] == "UNVERIFIED"
    assert "actual_min_date" not in coverage["datasets"][table]
    assert coverage["entity_status_counts"][table][0]["entity_count"] == 4125
    statements = [statement for statement, _ in reader.calls]
    assert set(statements) <= ALL_SQL
    for statement, params in reader.calls:
        assert isinstance(params, tuple)


def test_column_filter_and_entity_ids_are_parameters() -> None:
    table = "IDX_Broker_Summary"
    reader = FakeReader({
        RESOLVE_TABLES_SQL: resolve(table),
        COLUMNS_SQL: [column_row(table, "Investor Type")],
        FOUND_COLUMNS_SQL: [{"column_name": "Investor Type"}],
        COVERAGE_ENTITIES_SQL: [{"dataset_name": table, "entity_id": "BBCA", "coverage_mode": "ACTUAL_SOURCE"}],
    })
    result = execute(build_default_registry(reader), "get_catalog_details", details_args(
        table_names=[table], sections=["COLUMNS", "COVERAGE"],
        column_names=["Investor Type", "Nonexistent"], entity_ids=["BBCA", "ZZZZ"],
    )).output["result"]
    assert result["sections"]["COLUMNS"]["unknown_columns"] == ["Nonexistent"]
    assert result["sections"]["COVERAGE"]["unknown_entities"] == ["ZZZZ"]
    columns_call = next(params for statement, params in reader.calls if statement == COLUMNS_SQL)
    assert columns_call[:3] == ([table], ["Investor Type", "Nonexistent"], ["Investor Type", "Nonexistent"])


# 4. Unknown tables and invalid arguments ------------------------------------------------------

def test_unknown_tables_are_reported_not_fabricated() -> None:
    reader = FakeReader({RESOLVE_TABLES_SQL: resolve("Feature_02_Broker_Rolling")})
    result = execute(build_default_registry(reader), "get_catalog_details", details_args(
        table_names=["Feature_02_Broker_Rolling", "Made_Up_Table"])).output["result"]
    assert result["tables"] == ["Feature_02_Broker_Rolling"]
    assert result["unknown_tables"] == ["Made_Up_Table"]


def test_only_unknown_tables_returns_recoverable_error() -> None:
    outcome = execute(build_default_registry(FakeReader()), "get_catalog_details",
                      details_args(table_names=["Made_Up_Table"]))
    assert outcome.error_code == "TOOL_ERROR"
    assert "discover_catalog" in outcome.output["error"]["message"]


@pytest.mark.parametrize(
    "arguments",
    [
        details_args(sections=["FORMULAS"]),
        details_args(sections=[]),
        details_args(table_names=[]),
        details_args(table_names=["A", "B", "C", "D"]),
        details_args(table_names=['Feature_02"; DROP TABLE x; --']),
        details_args(table_names=["Feature_02_Broker_Rolling OR 1=1"]),
        details_args(column_names=["net_value_1d; SELECT 1"]),
        details_args(entity_ids=["BBCA' OR '1'='1"]),
        details_args(column_names=["c"] * 0),
        details_args(entity_ids=[f"T{i}" for i in range(21)]),
        {**details_args(), "sql": "SELECT * FROM \"Price_Stock_Indonesia_IDX\""},
        {"table_names": ["Feature_02_Broker_Rolling"], "sections": ["COLUMNS"]},
    ],
)
def test_invalid_arguments_never_reach_the_database(arguments: dict[str, Any]) -> None:
    reader = FakeReader()
    outcome = execute(build_default_registry(reader), "get_catalog_details", arguments)
    assert outcome.error_code == "INVALID_ARGUMENTS"
    assert reader.calls == []


def test_discover_rejects_any_argument() -> None:
    reader = FakeReader()
    outcome = execute(build_default_registry(reader), "discover_catalog", '{"sql": "SELECT 1"}')
    assert outcome.error_code == "INVALID_ARGUMENTS" and reader.calls == []


# 5. Empty or incomplete records ---------------------------------------------------------------

def test_empty_sections_are_explicit_and_nulls_are_not_filled() -> None:
    table = "Feature_03_Stock_Broker_Daily"
    reader = FakeReader({
        RESOLVE_TABLES_SQL: resolve(table),
        COLUMNS_SQL: [column_row(table, "mystery", description=None, unit=None,
                                 documentation_status="NEEDS_REVIEW")],
    })
    result = execute(build_default_registry(reader), "get_catalog_details", details_args(
        table_names=[table], sections=["COLUMNS", "RELATIONSHIPS", "CALCULATIONS", "COVERAGE"],
    )).output["result"]
    column = result["sections"]["COLUMNS"]["by_table"][table][0]
    assert column["description"] is None and "unit" not in column
    assert column["documentation_status"] == "NEEDS_REVIEW"
    assert result["sections"]["RELATIONSHIPS"]["entries"] == []
    assert "No documented relationships" in result["sections"]["RELATIONSHIPS"]["note"]
    assert result["sections"]["CALCULATIONS"]["by_table"] == {}
    assert result["sections"]["CALCULATIONS"]["note"] == "No matching catalog records."
    assert result["sections"]["COVERAGE"]["no_coverage_record"] == [table]
    assert "NULL or empty" in result["notice"]


def test_coverage_disabled_tables_are_not_queried() -> None:
    reader = FakeReader({RESOLVE_TABLES_SQL: resolve("IDX_Broker_Profile", coverage=False)})
    result = execute(build_default_registry(reader), "get_catalog_details", details_args(
        table_names=["IDX_Broker_Profile"], sections=["COVERAGE"])).output["result"]
    assert result["sections"]["COVERAGE"]["coverage_disabled_tables"] == ["IDX_Broker_Profile"]
    assert all(statement == RESOLVE_TABLES_SQL for statement, _ in reader.calls)


# 6. Bounded responses ---------------------------------------------------------------------------

def test_large_sections_degrade_to_summary_then_truncate_within_budget() -> None:
    tables = ["Feature_01_Stock_Daily", "Feature_02_Broker_Rolling", "Feature_03_Stock_Broker_Daily"]
    long_text = "x" * 600
    columns = [column_row(tables[i % 3], f"col_{i}", description=long_text, total_matching=150)
               for i in range(150)]
    calcs = [{
        "target_table": tables[i % 3], "calculation_name": f"calc_{i}", "version": "v2",
        "target_columns": [f"col_{i}"], "definition": long_text,
        "required_inputs": {"source_tables": ["IDX_Broker_Summary"], "note": long_text},
        "parameters": {}, "defaults": {}, "alignment_rules": long_text,
        "missing_data_policy": long_text, "output_definition": {"unit": "IDR"}, "total_matching": 100,
    } for i in range(100)]
    reader = FakeReader({RESOLVE_TABLES_SQL: resolve(*tables), COLUMNS_SQL: columns, CALCULATIONS_SQL: calcs})
    outcome = execute(build_default_registry(reader), "get_catalog_details", {
        "table_names": tables, "sections": ["COLUMNS", "CALCULATIONS"],
        "column_names": None, "entity_ids": None,
    })
    assert outcome.ok, outcome.output
    assert len(dumps(outcome.output).encode()) < DEFAULT_MAX_RESULT_BYTES
    for name in ("COLUMNS", "CALCULATIONS"):
        section = outcome.output["result"]["sections"][name]
        assert section["detail"] == "SUMMARY"
        assert section["truncated"] is True and section["returned"] < section["total_matching"]
        assert "column_names" in section["hint"]


def test_row_limits_are_passed_to_sql() -> None:
    reader = FakeReader({RESOLVE_TABLES_SQL: resolve("Feature_02_Broker_Rolling")})
    execute(build_default_registry(reader), "get_catalog_details", details_args(
        sections=["COLUMNS", "RELATIONSHIPS", "CALCULATIONS", "COVERAGE"], entity_ids=["BBCA"]))
    limits = {statement: params[-1] for statement, params in reader.calls}
    assert limits[COLUMNS_SQL] == 151 and limits[CALCULATIONS_SQL] == 101
    assert limits[RELATIONSHIPS_SQL] == 51 and limits[COVERAGE_STATUS_SQL] == 61
    assert limits[COVERAGE_ENTITIES_SQL] == 61


# 7. No arbitrary SQL ------------------------------------------------------------------------------

def test_sql_is_fixed_and_fully_parameterized() -> None:
    for statement in ALL_SQL:
        assert "{" not in statement and "}" not in statement
        assert statement.count("%s") >= 1 or statement is DISCOVER_SQL
        assert not any(word in statement.upper().split() for word in ("INSERT", "UPDATE", "DELETE", "DROP"))


def test_store_errors_are_generic_and_leak_nothing() -> None:
    store = CatalogStore("postgresql://secret_user:secret_pass@127.0.0.1:1/db",
                         connect_timeout_seconds=1, statement_timeout_ms=1000)
    with pytest.raises(ToolError) as raised:
        with store.read_only() as run:
            run("SELECT 1", ())
    assert str(raised.value) == "The catalog database is currently unavailable."
    assert "secret" not in str(raised.value)


# 8. Existing agent loop drives the catalog tools unchanged ---------------------------------------

def test_agent_loop_discovers_then_reads_details_then_limits() -> None:
    from app.orchestrator import AgentOrchestrator
    from app.schemas import AgentRunRequest
    from conftest import ScriptedClient, final_response, make_settings, tool_call_response

    table = "Feature_02_Broker_Rolling"
    reader = FakeReader({
        DISCOVER_SQL: [table_row(table)],
        RESOLVE_TABLES_SQL: resolve(table),
        CALCULATIONS_SQL: [{
            "target_table": table, "calculation_name": "net_value_20d", "version": "v2",
            "target_columns": ["net_value_20d"], "definition": "Sum of net_value_1d over 20 dates.",
            "required_inputs": {"source_tables": ["IDX_Broker_Summary"]}, "total_matching": 1,
        }],
    })
    limitation = {
        "response_type": "LIMITATION",
        "answer": "Feature_02_Broker_Rolling documents net_value_20d.",
        "clarification_question": None, "assumptions": [],
        "limitations": ["No query or calculation was executed."],
    }
    client = ScriptedClient([
        tool_call_response("discover_catalog", "{}", call_id="c_disc"),
        tool_call_response("get_catalog_details", json.dumps(details_args(sections=["CALCULATIONS"])),
                           call_id="c_det"),
        final_response(limitation),
    ])
    agent = AgentOrchestrator(make_settings(), client, build_default_registry(reader))
    result = agent.run(AgentRunRequest(request_id="r1", message="What broker accumulation data exists?"))

    assert result.status == "LIMITED" and result.response.model_dump() == limitation
    assert result.execution.tool_call_count == 2 and result.execution.iterations == 3
    first = client.payloads[0]
    assert [tool["name"] for tool in first["tools"]] == ["get_system_capabilities", "discover_catalog", "get_catalog_details", "read_catalog_rows", "preview_table_rows"]
    assert first["instructions"] == SYSTEM_PROMPT
    outputs = [item for item in client.payloads[2]["input"] if item.get("type") == "function_call_output"]
    assert [item["call_id"] for item in outputs] == ["c_disc", "c_det"]
    detail_output = json.loads(outputs[1]["output"])
    assert detail_output["ok"] is True
    assert detail_output["result"]["sections"]["CALCULATIONS"]["by_table"][table][0]["calculation_name"] == "net_value_20d"
