"""Governor tests that need no database: config, API surface, contract, compiler."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.compiler import compile_query
from app.config import ConfigError, Settings
from app.decisions import NEXT_ACTION, GovernorResponse
from app.main import create_app
from app.policy import FilterPlan, SelectItem, TableUse, ValidatedQuery
from app.spec import DataRequestSpec
from conftest import API_KEY, base_env


def test_defaults_are_conservative_backend_limits() -> None:
    s = Settings.from_env(base_env())
    assert (s.max_tables, s.max_joins, s.max_columns, s.max_filters) == (3, 2, 20, 10)
    assert (s.max_inline_rows, s.max_inline_output_bytes) == (200, 24000)
    assert (s.max_estimated_scan_rows, s.max_plan_cost, s.max_execution_seconds) == (2_000_000, 600_000, 60)
    assert (s.max_date_range_days, s.max_unfiltered_date_range_days) == (3660, 400)
    assert (s.statement_timeout_seconds, s.lock_timeout_seconds) == (20, 2)
    assert (s.max_dataset_rows, s.max_dataset_bytes) == (500_000, 134_217_728)
    assert s.dataset_storage_configured is False
    assert API_KEY not in repr(s) and "postgresql://" not in repr(s)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"SQL_GOVERNOR_API_KEY": ""}, "SQL_GOVERNOR_API_KEY"),
        ({"SQL_GOVERNOR_API_KEY": "short"}, "at least 32"),
        ({"GOVERNOR_DATABASE_URL": "mysql://x"}, "postgresql://"),
        ({"SQL_MAX_UNFILTERED_DATE_RANGE_DAYS": "5000"}, "must not exceed SQL_MAX_DATE_RANGE_DAYS"),
        ({"SQL_MAX_JOINS": "3"}, "below SQL_MAX_TABLES"),
        ({"SQL_STATEMENT_TIMEOUT_SECONDS": "500"}, "between 1 and 120"),
        ({"SQL_STATEMENT_TIMEOUT_SECONDS": "90", "SQL_MAX_EXECUTION_SECONDS": "60"}, "must not exceed SQL_MAX_EXECUTION"),
        ({"SQL_DATASET_BUCKET_NAME": "b"}, "requires endpoint"),
        ({"SQL_MAX_INLINE_ROWS": "abc"}, "integer"),
    ],
)
def test_invalid_configuration_is_rejected(overrides: dict, message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        Settings.from_env(base_env(**overrides))


def test_next_action_is_a_fixed_function_of_decision() -> None:
    assert NEXT_ACTION == {
        "INLINE_RESULT": "USE_INLINE_RESULT", "DATASET_READY": "RUN_ANALYSIS",
        "NEEDS_NARROWING": "REVISE_DATA_REQUEST", "REJECTED": "STOP_OR_REFORMULATE",
        "SANDBOX_REQUIRED": "USE_ANALYSIS_SANDBOX",
    }


def test_spec_has_no_sql_or_delivery_fields() -> None:
    fields = set(DataRequestSpec.model_fields)
    assert fields == {"purpose", "from_table", "columns", "joins", "filters", "group_by", "aggregations",
                      "order_by", "requested_limit"}
    text = str(DataRequestSpec.model_json_schema())
    for forbidden in ("return_as", "delivery_mode", "PARQUET", "\"sql\"", "expression"):
        assert forbidden not in text


def test_compiler_binds_every_value_and_quotes_every_identifier() -> None:
    query = ValidatedQuery(
        tables=[TableUse("IDX_Broker_Summary", "t0", "Date", "Symbol")], joins=[],
        select=[SelectItem("Symbol", "IDX_Broker_Summary", "t0", "Symbol", None, "character varying"),
                SelectItem("sum_Net Value", "IDX_Broker_Summary", "t0", "Net Value", "SUM", "numeric")],
        filters=[FilterPlan("t0", "Symbol", "IN", ["BBCA", "x'; DROP TABLE y; --"]),
                 FilterPlan("t0", "Investor Type", "EQ", ["Foreign"]),
                 FilterPlan("t0", "Net Value", "IS_NOT_NULL", [])],
        group_by=[("t0", "Symbol")], order_by=[], limit=None)
    query.order_by = [(query.select[1], "DESC")]
    compiled = compile_query(query, 101)
    assert compiled.text == (
        'SELECT "t0"."Symbol" AS "Symbol", sum("t0"."Net Value") AS "sum_Net Value" '
        'FROM "public"."IDX_Broker_Summary" AS "t0" WHERE "t0"."Symbol" = ANY(%s) AND "t0"."Investor Type" = %s '
        'AND "t0"."Net Value" IS NOT NULL GROUP BY "t0"."Symbol" ORDER BY "sum_Net Value" DESC LIMIT %s')
    assert compiled.params == (["BBCA", "x'; DROP TABLE y; --"], "Foreign", 101)
    assert len(compiled.query_hash) == 64 and compiled.query_hash == compile_query(query, 101).query_hash


class FakeGovernor:
    class database:
        @staticmethod
        def ping() -> None:
            return None

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def handle(self, request_id: str, spec: dict) -> GovernorResponse:
        self.calls.append((request_id, spec))
        return GovernorResponse(decision="REJECTED", next_action="STOP_OR_REFORMULATE", reason_code="X",
                                message="m", request_id=request_id, query_id="qry_1")


def client() -> tuple[TestClient, FakeGovernor]:
    fake = FakeGovernor()
    return TestClient(create_app(Settings.from_env(base_env()), governor=fake)), fake


def test_query_endpoint_requires_the_bearer_key() -> None:
    api, fake = client()
    body = {"request_id": "r1", "spec": {}}
    assert api.post("/v1/query", json=body).status_code == 401
    assert api.post("/v1/query", json=body, headers={"Authorization": "Bearer wrong"}).status_code == 401
    ok = api.post("/v1/query", json=body, headers={"Authorization": f"Bearer {API_KEY}"})
    assert ok.status_code == 200 and ok.json()["decision"] == "REJECTED" and fake.calls == [("r1", {})]


@pytest.mark.parametrize("body", [{"spec": {}}, {"request_id": "r1", "spec": {}, "sql": "SELECT 1"},
                                  {"request_id": "bad id!", "spec": {}}, ["not", "an", "object"]])
def test_query_endpoint_accepts_only_request_id_and_spec(body) -> None:
    api, fake = client()
    assert api.post("/v1/query", json=body, headers={"Authorization": f"Bearer {API_KEY}"}).status_code == 422
    assert fake.calls == []


def test_there_is_no_sql_endpoint_and_no_docs() -> None:
    api, _ = client()
    headers = {"Authorization": f"Bearer {API_KEY}"}
    for path in ("/v1/sql", "/v1/execute", "/docs", "/openapi.json"):
        assert api.post(path, json={"sql": "SELECT 1"}, headers=headers).status_code in (404, 405)
    assert api.get("/health").json() == {"status": "ok"} and api.get("/ready").json() == {"status": "ready"}
