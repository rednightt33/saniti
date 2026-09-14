from __future__ import annotations

from datetime import date

import pytest

from app.config import Settings
from app.schemas import FINAL_RESPONSE_SCHEMA
from app.tools import ToolError, ToolRegistry


def test_evidence_and_completion_are_always_exposed() -> None:
    assert ToolRegistry.ALWAYS_EXPOSED == {"record_evidence", "complete_analysis"}


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


def test_evidence_ready_date_normalizes_literal_null_and_rejects_other_text() -> None:
    assert ToolRegistry._normalize_analysis_ready_date(None) is None
    assert ToolRegistry._normalize_analysis_ready_date("null") is None
    assert ToolRegistry._normalize_analysis_ready_date("2026-08-31") == date(2026, 8, 31)
    with pytest.raises(ToolError, match="ISO date"):
        ToolRegistry._normalize_analysis_ready_date("N/A definition only")


def test_completion_requires_explicit_stopping_checklist() -> None:
    registry = object.__new__(ToolRegistry)
    with pytest.raises(ToolError, match="necessary follow-up"):
        registry.complete_analysis(
            {
                "evidence_sufficient": True,
                "necessary_followups_completed": False,
                "completion_reason": "Initial result only",
                "remaining_uncertainties": [],
                "optional_next_analysis": [],
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


def test_condition_runs_schema_is_strict_and_generic() -> None:
    schema = ToolRegistry.schema_for("find_condition_runs")
    assert schema["additionalProperties"] is False
    assert "conditions" in schema["required"]
    assert "minimum_consecutive_observations" in schema["required"]
    assert schema["properties"]["conditions"]["items"]["additionalProperties"] is False


def test_every_handler_rejects_missing_required_arguments_before_indexing() -> None:
    registry = ToolRegistry(None, Settings.from_env(require_runtime_secrets=False))
    with pytest.raises(ToolError, match="missing required fields.*tables"):
        registry.execute("check_data_freshness", {}, "request-id")


def test_generic_analytics_sql_policy_rejects_mutation_and_external_readers() -> None:
    assert ToolRegistry._validate_worker_sql("WITH x AS (SELECT 1 n) SELECT * FROM x")
    with pytest.raises(ToolError, match="forbidden operation"):
        ToolRegistry._validate_worker_sql("SELECT * FROM read_parquet('s3://private/file')")
    with pytest.raises(ToolError, match="SELECT or WITH"):
        ToolRegistry._validate_worker_sql("DELETE FROM prices")
