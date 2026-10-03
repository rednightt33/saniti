"""D5 (round 2026-10-03): query_metric maps an official metric of AI_metric_catalog to one Governor summary per period
(the Governor re-derives the rules), defaults to the conversation's data date, refuses metrics and dimensions outside
the catalog with a next step, and its values are database aggregates the answer may cite. The catalog migration is
applied to a scratch database and verified there."""
from __future__ import annotations

import json
import secrets
from pathlib import Path

import httpx
import psycopg
import pytest

from app.tools import build_default_registry
from app.tools.analysis import DataDate, current_data_date
from app.tools.data_planner import sha256_json
from app.tools.request_data import GovernorClient, current_request_id
from test_conversations import ADMIN_URL

REPO = Path(__file__).resolve().parents[3]
MIGRATION = REPO / "database/migrations/20261003_008_ai_metric_catalog.sql"
METRICS = [{"metric_id": "net_foreign_value", "metric_version": 1, "label": "Net beli asing (nilai)",
            "description": "Net value of source Foreign investors.", "source_table": "Feature_03_Stock_Broker_Daily",
            "measure_column": "foreign_net_value", "time_function": "SUM", "entity_column": "ticker",
            "default_dimensions": ["ticker", "market_board"], "allowed_dimensions": ["ticker", "market_board"],
            "default_scope": {"type": "ALL"}, "formula": "x", "interpretation": "x",
            "misuse_warning": "Boards stay separate.", "review_status": "INFERRED", "unit": "IDR"},
           {"metric_id": "last_close", "metric_version": 1, "label": "Harga penutupan terakhir",
            "description": "Last close.", "source_table": "Price_Stock_Indonesia_IDX", "measure_column": "close",
            "time_function": "LAST", "entity_column": "ticker", "default_dimensions": ["ticker"],
            "allowed_dimensions": ["ticker"], "default_scope": {"type": "ALL"}, "formula": "x", "interpretation": "x",
            "misuse_warning": "Not adjusted.", "review_status": "INFERRED", "unit": "IDR"}]


class FakeGovernor:
    def __init__(self, answer: dict | None = None) -> None:
        self.bodies: list[dict] = []
        self.answer = answer

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.bodies.append(body)
        if self.answer is not None:
            return httpx.Response(200, json=self.answer)
        days = body["summary"]["period"].get("trading_days") or 22
        return httpx.Response(200, json={
            "status": "OK", "query_id": "qry_" + "1" * 24, "query_hash": "h" * 64,
            "period": {"from": "2026-09-01", "to": "2026-09-30", "calendar_dates": days},
            "rows": [{"ticker": "BBCA", "market_board": "Regular", "net_foreign_value": 1250000000.0,
                      "days_present": days, "first_date": "2026-09-01", "last_date": "2026-09-30"}],
            "row_count": 1})


def registry(fake: FakeGovernor, metrics=METRICS):
    governor = GovernorClient("http://governor.test", "g" * 40, 10, transport=httpx.MockTransport(fake.handler))
    return build_default_registry(governor_client=governor, metrics=metrics)


def call(reg, arguments: dict, data_date: DataDate | None = None):
    token, pinned = current_request_id.set("req_metric"), current_data_date.set(data_date)
    try:
        return reg.execute("c1", "query_metric", arguments)
    finally:
        current_request_id.reset(token)
        current_data_date.reset(pinned)


def test_the_tool_and_its_menu_exist_only_with_metrics() -> None:
    reg = registry(FakeGovernor())
    assert "query_metric" in reg.names() and "net_foreign_value" in reg.metric_menu
    assert "query_metric" not in registry(FakeGovernor(), metrics=None).names()


def test_one_summary_per_period_at_the_conversation_data_date() -> None:
    fake = FakeGovernor()
    result = call(registry(fake), {"metric": "net_foreign_value", "entities": ["BBCA"],
                                   "periods": [{"trading_days": 5}, {"trading_days": 20}]},
                  DataDate("2026-09-30")).output["result"]
    assert result["status"] == "OK" and result["as_of"] == "2026-09-30" and len(result["periods"]) == 2
    first = fake.bodies[0]
    assert first["summary"]["source_table"] == "Feature_03_Stock_Broker_Daily"
    assert first["summary"]["group_by"] == ["ticker", "market_board"]  # boards stay separate by default
    assert first["summary"]["scope"] == {"type": "PREDICATE", "column": "ticker", "operator": "EQ",
                                         "values": ["BBCA"]}
    assert first["summary"]["measures"] == [{"column": "foreign_net_value", "function": "SUM",
                                             "as": "net_foreign_value"}]
    assert first["summary"]["period"] == {"trading_days": 5, "as_of": "2026-09-30"}
    assert first["lineage"] == {"purpose": "METRIC", "recipe_sha256": sha256_json(first["summary"]),
                                "metric_id": "net_foreign_value"}
    assert result["metric"]["unit"] == "IDR" and result["metric"]["review_status"] == "INFERRED"


def test_a_date_range_and_combined_boards() -> None:
    """Another case: a date range, the boards combined on request (dimensions ticker only), several entities."""
    fake = FakeGovernor()
    call(registry(fake), {"metric": "net_foreign_value", "entities": ["BMRI", "BBCA"], "dimensions": ["ticker"],
                          "periods": [{"start_date": "2026-09-01", "end_date": "2026-09-30"}]})
    summary = fake.bodies[0]["summary"]
    assert summary["group_by"] == ["ticker"] and summary["period"] == {"from": "2026-09-01", "to": "2026-09-30"}
    assert summary["scope"]["operator"] == "IN" and summary["scope"]["values"] == ["BBCA", "BMRI"]


def test_outside_the_catalog_the_next_step_is_a_data_need() -> None:
    reg = registry(FakeGovernor())
    unknown = call(reg, {"metric": "rsi_14", "periods": [{"trading_days": 5}]}).output["result"]
    assert unknown["code"] == "METRIC_NOT_IN_CATALOG" and unknown["next_action"] == "CALL:submit_data_need_spec"
    bad = call(reg, {"metric": "last_close", "dimensions": ["market_board"],
                     "periods": [{"trading_days": 5}]}).output["result"]
    assert bad["code"] == "METRIC_DIMENSION_NOT_ALLOWED" and bad["allowed_dimensions"] == ["ticker"]
    both = call(reg, {"metric": "last_close", "periods": [{"trading_days": 5, "start_date": "2026-09-01",
                                                          "end_date": "2026-09-30"}]})
    assert not both.ok and both.error_code == "INVALID_ARGUMENTS"


def test_a_governor_refusal_is_passed_on_with_a_next_step() -> None:
    fake = FakeGovernor({"status": "REJECTED_POLICY", "code": "AGGREGATION_NOT_ADDITIVE", "message": "no SUM rule"})
    result = call(registry(fake), {"metric": "net_foreign_value", "periods": [{"trading_days": 5}]}).output["result"]
    assert result["status"] == "REJECTED" and result["code"] == "AGGREGATION_NOT_ADDITIVE"
    assert result["next_action"] == "FIX_ARGUMENTS"


CATALOG_STUBS = '''
CREATE TABLE public."Table_Catalog" (table_schema text, table_name text, category text, definition text, grain text,
    primary_key_columns text[], source_system text, source_tables text[], source_code_paths text[], update_rule text,
    related_functions text[], documentation_status text, readiness_mode text, readiness_date_column text,
    observation_date_column text, data_available_at_column text, availability_rule text, point_in_time_status text,
    historical_metadata_method text);
CREATE TABLE public."Column_Catalog" (table_schema text, table_name text, column_name text, ordinal_position integer,
    data_type text, is_nullable boolean, default_expression text, is_primary_key boolean, definition text,
    source_column_or_expression text, unit text, null_rule text, source_code_paths text[], documentation_status text);
CREATE TABLE public."AI_column_catalog" (table_name text, column_name text, ai_allowed boolean);
INSERT INTO public."AI_column_catalog" VALUES
  ('Feature_03_Stock_Broker_Daily', 'foreign_net_value', true), ('Feature_03_Stock_Broker_Daily', 'ticker', true),
  ('Feature_03_Stock_Broker_Daily', 'market_board', true), ('IDX_Broker_Summary', 'Net Value', true),
  ('IDX_Broker_Summary', 'Symbol', true), ('IDX_Broker_Summary', 'Broker', true),
  ('IDX_Broker_Summary', 'Investor Type', true), ('IDX_Broker_Summary', 'Market Board', true),
  ('Price_Stock_Indonesia_IDX', 'ticker', true), ('Price_Stock_Indonesia_IDX', 'volume', true),
  ('Price_Stock_Indonesia_IDX', 'close', true), ('Price_Stock_Indonesia_IDX', 'high', true),
  ('Price_Stock_Indonesia_IDX', 'low', true);
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'market_ai_catalog_reader') THEN
    CREATE ROLE market_ai_catalog_reader NOLOGIN;
  END IF;
END $$;
'''


@pytest.mark.skipif(not ADMIN_URL, reason="ORC_TEST_POSTGRES_URL not set")
def test_the_catalog_migration_applies_and_verifies() -> None:
    name = f"orc_metrics_{secrets.token_hex(4)}"
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    url = ADMIN_URL.rsplit("/", 1)[0] + f"/{name}"
    try:
        with psycopg.connect(url, autocommit=True) as connection:
            connection.execute(CATALOG_STUBS)
            connection.execute(MIGRATION.read_text())
            rows = connection.execute('SELECT metric_id, time_function, review_status FROM public."AI_metric_catalog" '
                                      "ORDER BY metric_id").fetchall()
            assert [r[0] for r in rows] == ["broker_net_value", "last_close", "net_foreign_value", "period_high",
                                            "period_low", "volume"]
            assert {r[2] for r in rows} == {"INFERRED"}  # never VERIFIED before the user reviews them
            # a second run is refused by the preflight
            with pytest.raises(psycopg.Error):
                connection.execute(MIGRATION.read_text())
    finally:
        with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def test_a_run_offers_the_metrics_and_its_numbers_are_database_aggregates() -> None:
    from app.orchestrator import AgentOrchestrator
    from app.schemas import AgentRunRequest
    from conftest import ScriptedClient, final_response, make_settings, tool_call_response

    answer = {"response_type": "ANSWER", "answer": "Net beli asing BBCA 5 hari bursa: 1.250.000.000 rupiah.",
              "clarification_question": None, "assumptions": [], "limitations": []}
    client = ScriptedClient([
        tool_call_response("query_metric", json.dumps({"metric": "net_foreign_value", "entities": ["BBCA"],
                                                       "periods": [{"trading_days": 5}]})),
        final_response(answer)])
    settings = make_settings(AI_ENABLE_DATANEED="true", AI_ENABLE_VALUE_REFERENCES="true")
    result = AgentOrchestrator(settings, client, registry(FakeGovernor())).run(
        AgentRunRequest(request_id="req_metric_run", message="Net beli asing BBCA 5 hari?"))
    first_input = json.dumps(client.payloads[0]["input"])
    assert "METRICS (application context" in first_input and "net_foreign_value" in first_input
    tool_output = json.dumps(client.payloads[1]["input"])
    assert "metric.m1.periods" in tool_output  # the reference the answer may cite
    assert result.status == "COMPLETED"
    provenance = result.execution.number_provenance
    assert provenance is None or not provenance.unsupported, provenance
