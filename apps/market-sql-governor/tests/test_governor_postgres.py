"""Governor integration tests on a real PostgreSQL server, running as the market_sql_governor login.

Set GOVERNOR_TEST_POSTGRES_URL (or ORC_TEST_POSTGRES_URL) to a disposable admin connection.
"""
from __future__ import annotations

import hashlib
import json
import logging
import tempfile
from pathlib import Path
from typing import Any

import pytest

psycopg = pytest.importorskip("psycopg")
pq = pytest.importorskip("pyarrow.parquet")

from app.compiler import compile_query  # noqa: E402
from app.config import Settings  # noqa: E402
from app.governor import Database, Governor  # noqa: E402
from app.policy import Policy, Validator  # noqa: E402
from app.spec import DataRequestSpec  # noqa: E402
from app.store import LocalStore  # noqa: E402
from conftest import API_KEY, LOGIN_PASSWORD, base_env  # noqa: E402
from fixture import MARKET_TABLES, TABLE_META  # noqa: E402

PRICE = "Price_Stock_Indonesia_IDX"


def governor(db: dict, tmp_path: Path | None = None, storage: bool = True, **limits: str) -> Governor:
    env = base_env(GOVERNOR_DATABASE_URL=db["login"], **limits)
    if storage and tmp_path is None:
        tmp_path = Path(tempfile.mkdtemp(prefix="gov-test-"))
    if storage:
        env["SQL_DATASET_LOCAL_DIR"] = str(tmp_path)
    settings = Settings.from_env(env)
    return Governor(settings, Database(settings), LocalStore(str(tmp_path)) if storage else None)


def dataset_rows(gov: Governor, result) -> list[list[Any]]:
    """The rows of a DATASET_READY snapshot, read the way the sandbox reads them."""
    assert result.decision == "DATASET_READY", (result.reason_code, result.message)
    path = Path(gov.store.root) / "datasets" / result.dataset.dataset_id / "data.parquet"
    table = pq.read_table(path)
    return [list(row.values()) for row in table.to_pylist()]


def cols(table: str, *names: str) -> list[dict[str, str]]:
    return [{"table": table, "column": name} for name in names]


def filt(table: str, column: str, operator: str, value: Any) -> dict[str, Any]:
    return {"table": table, "column": column, "operator": operator, "value": value}


def spec(from_table: str = PRICE, **overrides: Any) -> dict[str, Any]:
    body = {
        "purpose": "test", "from_table": from_table, "columns": cols(PRICE, "ticker", "date", "close"),
        "joins": [], "filters": [filt(PRICE, "ticker", "EQ", "BBCA")], "group_by": [], "aggregations": [],
        "order_by": [{"table": PRICE, "column": "date", "function": None, "direction": "DESC"}],
        "requested_limit": 20,
    }
    body.update(overrides)
    return body


def run(gov: Governor, body: dict[str, Any]):
    return gov.handle("test-request", body)


# --- Gate 1: tables ---------------------------------------------------------------------------

@pytest.mark.parametrize("table", MARKET_TABLES)
def test_each_approved_table_is_accepted_when_catalog_policy_allows_it(governed_db, tmp_path, table) -> None:
    time_col, entity_col, _ = TABLE_META[table]
    columns = [entity_col] + ([time_col] if time_col else [])
    filters = [filt(table, time_col, "BETWEEN", ["2026-08-01", "2026-08-31"])] if time_col else []
    result = run(governor(governed_db, tmp_path), spec(
        table, columns=cols(table, *columns), filters=filters, order_by=[], requested_limit=None))
    assert result.decision == "DATASET_READY", (result.reason_code, result.message)
    assert result.source_tables == [table]


@pytest.mark.parametrize(
    ("table", "reason"),
    [("Unapproved_Market_Table", "TABLE_NOT_APPROVED"), ("Inactive_Table", "TABLE_INACTIVE"),
     ("Denied_Table", "TABLE_DENIED"), ("Table_Catalog", "TABLE_NOT_APPROVED")],
)
def test_unapproved_inactive_and_denied_tables_are_rejected(governed_db, table, reason) -> None:
    result = run(governor(governed_db), spec(table, columns=cols(table, "ticker"), filters=[], order_by=[]))
    assert (result.decision, result.reason_code, result.next_action) == ("REJECTED", reason, "STOP_OR_REFORMULATE")
    assert result.dataset is None and result.query_hash is None


def test_catalog_approved_table_without_database_grant_is_denied_by_the_role(governed_db) -> None:
    result = run(governor(governed_db), spec("Catalog_Only_Table", columns=cols("Catalog_Only_Table", "ticker"),
                                             filters=[], order_by=[]))
    assert (result.decision, result.reason_code) == ("REJECTED", "DATABASE_PERMISSION_DENIED")


def test_database_role_cannot_select_unapproved_tables_directly(governed_db) -> None:
    with psycopg.connect(governed_db["login"]) as connection:
        for table in ("Unapproved_Market_Table", "Catalog_Only_Table", "Table_Catalog", "Analysis_Request"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute(f'SELECT * FROM public."{table}" LIMIT 1')
            connection.rollback()
        assert connection.execute(f'SELECT count(*) FROM public."{PRICE}"').fetchone()[0] > 0


# --- Gates 2, 3, 5, 6: columns, filters, grouping, aggregation ------------------------------------

@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"columns": cols(PRICE, "ticker", "no_such_column")}, "UNKNOWN_COLUMN"),
        ({"columns": cols(PRICE, "ticker", "source")}, "COLUMN_NOT_ALLOWED"),          # ai_allowed = false
        ({"columns": cols(PRICE, "ticker", "ingestion_time")}, "COLUMN_NOT_ALLOWED"),  # is_sensitive = true
        ({"filters": [filt(PRICE, "ticker", "EQ", "BBCA"), filt(PRICE, "source", "EQ", "x")]}, "COLUMN_NOT_ALLOWED"),
        ({"filters": [filt(PRICE, "query_date", "EQ", "2026-09-01")]}, "FILTER_NOT_ALLOWED"),
        ({"columns": cols(PRICE, "close"), "group_by": cols(PRICE, "close"), "order_by": []}, "GROUP_BY_NOT_ALLOWED"),
        ({"columns": cols(PRICE, "ticker"), "group_by": cols(PRICE, "ticker"), "order_by": [],
          "aggregations": [{"table": PRICE, "column": "close", "function": "MEDIAN"}]}, "AGGREGATION_NOT_ALLOWED"),
        ({"columns": cols(PRICE, "ticker"), "group_by": cols(PRICE, "ticker"), "order_by": [],
          "aggregations": [{"table": PRICE, "column": "ticker", "function": "SUM"}]}, "AGGREGATION_NOT_ALLOWED"),
        ({"columns": cols(PRICE, "ticker", "close"), "order_by": [],
          "aggregations": [{"table": PRICE, "column": "close", "function": "AVG"}], "group_by": cols(PRICE, "ticker")},
         "COLUMN_NOT_GROUPED"),
        ({"filters": [filt(PRICE, "close", "EQ", "abc")]}, "INVALID_FILTER_VALUE"),
        ({"filters": [filt(PRICE, "date", "BETWEEN", ["2026-02-01", "2026-01-01"])]}, "INVALID_FILTER_VALUE"),
        ({"columns": cols("Feature_01_Stock_Daily", "close")}, "TABLE_NOT_IN_REQUEST"),
    ],
)
def test_column_filter_group_and_aggregation_gates_reject_the_whole_request(governed_db, overrides, reason) -> None:
    result = run(governor(governed_db), spec(**overrides))
    assert (result.decision, result.reason_code) == ("REJECTED", reason), result.message
    assert result.dataset is None


def test_approved_aggregation_is_accepted_and_computed(governed_db) -> None:
    gov = governor(governed_db)
    result = run(gov, spec(
        columns=cols(PRICE, "ticker"), group_by=cols(PRICE, "ticker"),
        aggregations=[{"table": PRICE, "column": "close", "function": "AVG"},
                      {"table": PRICE, "column": "volume", "function": "MEDIAN"},
                      {"table": PRICE, "column": "date", "function": "COUNT"}],
        filters=[filt(PRICE, "ticker", "IN", ["BBCA", "BBRI"]), filt(PRICE, "date", "GTE", "2026-01-01")],
        order_by=[{"table": PRICE, "column": "close", "function": "AVG", "direction": "DESC"}], requested_limit=None))
    rows = dataset_rows(gov, result)
    assert [c.name for c in result.columns] == ["ticker", "avg_close", "median_volume", "count_date"]
    assert result.dataset.row_count == 2 and float(rows[0][1]) >= float(rows[1][1])


def test_min_max_on_date_columns_is_allowed_by_migration_007(governed_db) -> None:
    gov = governor(governed_db)
    result = run(gov, spec(
        columns=cols(PRICE, "ticker"), group_by=cols(PRICE, "ticker"), order_by=[], requested_limit=None,
        aggregations=[{"table": PRICE, "column": "date", "function": "MIN"},
                      {"table": PRICE, "column": "date", "function": "MAX"}],
        filters=[filt(PRICE, "ticker", "IN", ["BBCA", "BBRI"])]))
    rows = dataset_rows(gov, result)
    assert [c.name for c in result.columns] == ["ticker", "min_date", "max_date"]
    assert {tuple(str(v) for v in row[1:]) for row in rows} == {("2025-01-02", "2026-08-31")}
    still_blocked = run(governor(governed_db), spec(
        columns=cols(PRICE, "ticker"), group_by=cols(PRICE, "ticker"), order_by=[],
        aggregations=[{"table": PRICE, "column": "date", "function": "SUM"}]))
    assert still_blocked.reason_code == "AGGREGATION_NOT_ALLOWED"


# --- Gate 4: joins --------------------------------------------------------------------------------

def test_approved_relationship_join_uses_catalog_keys(governed_db) -> None:
    f01 = "Feature_01_Stock_Daily"
    result = run(governor(governed_db), spec(
        columns=cols(PRICE, "ticker", "date", "close") + cols(f01, "return_1d_pct"),
        joins=[{"table": f01, "relationship_id": None}]))
    assert result.decision == "DATASET_READY", result.message
    assert result.source_tables == [PRICE, f01] and result.dataset.row_count == 20


@pytest.mark.parametrize(
    ("from_table", "join", "reason"),
    [
        (PRICE, {"table": "IDX_Broker_Profile", "relationship_id": None}, "RELATIONSHIP_NOT_APPROVED"),
        (PRICE, {"table": "Feature_01_Stock_Daily", "relationship_id": 999}, "UNKNOWN_RELATIONSHIP"),
        ("Feature_01_Stock_Daily", {"table": "Feature_03_Stock_Broker_Daily", "relationship_id": None},
         "RELATIONSHIP_NOT_ALLOWED"),
    ],
)
def test_unknown_or_disallowed_relationships_are_rejected(governed_db, from_table, join, reason) -> None:
    result = run(governor(governed_db), spec(from_table, columns=cols(from_table, "ticker"), joins=[join],
                                             filters=[], order_by=[]))
    assert (result.decision, result.reason_code) == ("REJECTED", reason)


def test_preaggregation_relationship_is_never_joined_naively(governed_db) -> None:
    f02, f03 = "Feature_02_Broker_Rolling", "Feature_03_Stock_Broker_Daily"
    result = run(governor(governed_db), spec(f02, columns=cols(f02, "ticker", "date"),
                                             joins=[{"table": f03, "relationship_id": None}],
                                             filters=[filt(f02, "ticker", "EQ", "BBCA")], order_by=[]))
    assert (result.decision, result.reason_code) == ("REJECTED", "PREAGGREGATION_REQUIRED")
    relationship = result.details["relationship"]
    assert relationship["requires_preaggregation"] is True
    assert relationship["safe_output_grain"] and relationship["temporal_rule"]
    assert result.query_hash is None and result.estimated_scan_rows is None  # nothing compiled or executed


# --- Raw SQL and parameterization -------------------------------------------------------------------

@pytest.mark.parametrize(
    "body",
    [
        spec(sql="SELECT * FROM pg_shadow"),
        spec(from_table='Price_Stock_Indonesia_IDX" UNION SELECT 1 --'),
        spec(columns=[{"table": PRICE, "column": "close); DROP TABLE x; --"}]),
        spec(return_as="PARQUET"),
        spec(delivery_mode="INLINE"),
        {**spec(), "filters": [{**filt(PRICE, "ticker", "EQ", "BBCA"), "expression": "1=1"}]},
    ],
)
def test_raw_sql_and_delivery_mode_cannot_be_passed(governed_db, body) -> None:
    result = run(governor(governed_db), body)
    assert (result.decision, result.reason_code) == ("REJECTED", "INVALID_REQUEST_SPEC")


def test_filter_values_are_bound_parameters_never_sql_text(governed_db) -> None:
    hostile = "BBCA'; DROP TABLE public.\"Price_Stock_Indonesia_IDX\"; --"
    body = DataRequestSpec.model_validate(spec(filters=[filt(PRICE, "ticker", "IN", [hostile, "BBRI"])]))
    settings = Settings.from_env(base_env(GOVERNOR_DATABASE_URL=governed_db["login"]))
    with Database(settings).session() as connection:
        def runner(statement, params):
            with connection.cursor(row_factory=psycopg.rows.dict_row) as cursor:
                return cursor.execute(statement, params).fetchall()
        compiled = compile_query(Validator(settings).validate(body, Policy.load(runner, body)), 21)
    assert "BBCA" not in compiled.text and "DROP" not in compiled.text
    assert compiled.text.count("%s") == len(compiled.params) == 2 and [hostile, "BBRI"] in compiled.params
    result = run(governor(governed_db), spec(filters=[filt(PRICE, "ticker", "EQ", hostile)]))
    assert result.decision == "DATASET_READY" and result.dataset.row_count == 0
    with psycopg.connect(governed_db["admin"]) as connection:
        assert connection.execute(f'SELECT count(*) FROM public."{PRICE}"').fetchone()[0] > 0


# --- Gate 7: coverage and date bounds ------------------------------------------------------------------

def test_period_outside_verified_coverage_needs_narrowing(governed_db) -> None:
    result = run(governor(governed_db), spec(filters=[filt(PRICE, "ticker", "EQ", "BBCA"),
                                                      filt(PRICE, "date", "BETWEEN", ["2020-01-01", "2020-12-31"])]))
    assert (result.decision, result.reason_code, result.next_action) == (
        "NEEDS_NARROWING", "OUTSIDE_VERIFIED_COVERAGE", "REVISE_DATA_REQUEST")
    assert result.details["available_range"]["from"] == "2025-01-02"


def test_unverified_expected_coverage_is_a_warning_not_a_guarantee(governed_db) -> None:
    f01 = "Feature_01_Stock_Daily"
    result = run(governor(governed_db), spec(f01, columns=cols(f01, "ticker", "date"),
                                             filters=[filt(f01, "ticker", "EQ", "BBCA")], order_by=[]))
    assert result.decision == "DATASET_READY"
    assert any("EXPECTED_DERIVED/UNVERIFIED" in warning for warning in result.warnings)


def test_date_range_limits_depend_on_entity_filter(governed_db, tmp_path) -> None:
    unfiltered = run(governor(governed_db), spec(filters=[], requested_limit=None, order_by=[]))
    assert (unfiltered.decision, unfiltered.reason_code) == ("NEEDS_NARROWING", "DATE_RANGE_TOO_LARGE")
    assert unfiltered.details["entity_filtered"] is False and unfiltered.details["max_days"] == 400
    filtered = run(governor(governed_db, tmp_path), spec(requested_limit=None, order_by=[]))  # BBCA, all dates
    assert filtered.decision == "DATASET_READY", filtered.message
    assert filtered.dataset.row_count == 433 and filtered.dataset.actual_date_range["from"] == "2025-01-02"


# --- Gate 9: EXPLAIN --------------------------------------------------------------------------------------

def test_explain_gate_rejects_excessive_scan_before_execution(governed_db) -> None:
    f02 = "Feature_02_Broker_Rolling"
    result = run(governor(governed_db, SQL_MAX_ESTIMATED_SCAN_ROWS="5000"), spec(
        f02, columns=cols(f02, "ticker", "date", "broker", "net_value_1d"),
        filters=[filt(f02, "date", "BETWEEN", ["2026-03-01", "2026-08-31"])], order_by=[], requested_limit=None))
    assert (result.decision, result.reason_code) == ("NEEDS_NARROWING", "ESTIMATED_SCAN_TOO_LARGE")
    assert result.estimated_scan_rows > 5000 and result.dataset is None and result.returned_rows is None


def test_sequential_scans_count_the_whole_relation(governed_db) -> None:
    result = run(governor(governed_db), spec(
        "IDX_Stock_Universe", columns=cols("IDX_Stock_Universe", "Ticker", "Sector"),
        filters=[filt("IDX_Stock_Universe", "Sector", "EQ", "no-such-sector")], order_by=[], requested_limit=None))
    assert result.decision == "DATASET_READY" and result.dataset.row_count == 0
    assert result.estimated_scan_rows >= 30  # all 30 rows are read even though none match


def test_plan_cost_ceiling_is_enforced(governed_db) -> None:
    result = run(governor(governed_db, SQL_MAX_PLAN_COST="1"), spec())
    assert (result.decision, result.reason_code) == ("NEEDS_NARROWING", "ESTIMATED_COST_TOO_LARGE")


# --- Session safety -----------------------------------------------------------------------------------------

def test_statement_timeout_is_applied_and_mapped(governed_db, monkeypatch) -> None:
    settings = Settings.from_env(base_env(GOVERNOR_DATABASE_URL=governed_db["login"], SQL_STATEMENT_TIMEOUT_SECONDS="1"))
    with Database(settings).session() as connection:
        with pytest.raises(psycopg.errors.QueryCanceled):
            connection.execute("SELECT pg_sleep(3)")
    gov = governor(governed_db)

    def slow(*args, **kwargs):
        raise psycopg.errors.QueryCanceled("canceling statement due to statement timeout")
    monkeypatch.setattr(gov, "_explain", slow)
    result = run(gov, spec())
    assert (result.decision, result.reason_code) == ("NEEDS_NARROWING", "QUERY_TIMEOUT")


def test_sessions_are_read_only(governed_db) -> None:
    settings = Settings.from_env(base_env(GOVERNOR_DATABASE_URL=governed_db["login"]))
    for statement in ('CREATE TEMP TABLE scratch (x int)', f'DELETE FROM public."{PRICE}"',
                      'INSERT INTO public."AI_table_catalog" (table_name) VALUES (\'x\')'):
        with Database(settings).session() as connection:
            with pytest.raises((psycopg.errors.ReadOnlySqlTransaction, psycopg.errors.InsufficientPrivilege)):
                connection.execute(statement)


# --- Gate 10: every approved request is a dataset -----------------------------------------------------------

def test_even_a_tiny_result_is_a_dataset_never_rows(governed_db, tmp_path) -> None:
    gov = governor(governed_db, tmp_path)
    result = run(gov, spec(requested_limit=3))
    assert (result.decision, result.next_action) == ("DATASET_READY", "RUN_ANALYSIS")
    assert result.dataset.row_count == 3 and len(dataset_rows(gov, result)) == 3
    assert "rows" not in result.model_dump() and result.returned_rows == 0 and result.output_bytes == 0


def test_without_storage_an_approved_request_is_refused_not_returned_inline(governed_db) -> None:
    result = run(governor(governed_db, storage=False), spec(requested_limit=5))
    assert (result.decision, result.reason_code) == ("REJECTED", "DATASET_STORAGE_UNAVAILABLE")
    assert result.dataset is None and "lookup_fact" in result.message


def test_dataset_ready_returns_reference_only_and_writes_a_verifiable_parquet(governed_db, tmp_path) -> None:
    result = run(governor(governed_db, tmp_path), spec(
        columns=cols(PRICE, "ticker", "date", "close"), requested_limit=None, order_by=[],
        filters=[filt(PRICE, "ticker", "IN", ["BBCA", "BBRI", "ZZZZ"]), filt(PRICE, "date", "GTE", "2025-06-01")]))
    assert result.decision == "DATASET_READY", result.message
    body = result.model_dump_json()
    assert "rows" not in result.model_dump() and len(body) < 6000 and str(tmp_path) not in body and "data.parquet" not in body
    dataset = result.dataset
    assert dataset.format == "PARQUET" and dataset.missing_entities == ["ZZZZ"]
    assert dataset.completeness_status == "MISSING_REQUESTED_ENTITIES" and dataset.entities_present_count == 2
    folder = tmp_path / "datasets" / dataset.dataset_id
    payload = (folder / "data.parquet").read_bytes()
    assert hashlib.sha256(payload).hexdigest() == dataset.checksum_sha256 == \
        json.loads((folder / "manifest.json").read_text())["checksum_sha256"]
    table = pq.read_table(folder / "data.parquet")
    assert table.num_rows == dataset.row_count and table.column_names == ["ticker", "date", "close"]
    manifest = json.loads((folder / "manifest.json").read_text())
    for key in ("requested_scope", "actual_date_range", "entities_present", "missing_entities", "row_count",
                "schema", "source_tables", "query_hash", "checksum_sha256", "truncated", "completeness_status",
                "expires_at"):
        assert key in manifest
    assert manifest["actual_date_range"]["from"] >= "2025-06-01" and manifest["truncated"] is False


def test_estimated_result_above_dataset_ceiling_is_refused_before_execution(governed_db, tmp_path) -> None:
    result = run(governor(governed_db, tmp_path, SQL_MAX_DATASET_ROWS="100"),
                 spec(requested_limit=None, order_by=[]))
    assert (result.decision, result.reason_code) == ("NEEDS_NARROWING", "ESTIMATED_RESULT_TOO_LARGE")
    assert result.details["estimated_result_rows"] == 101 and result.returned_rows is None
    assert not list(tmp_path.glob("datasets/*/data.parquet"))


def test_dataset_row_ceiling_holds_even_when_the_estimate_is_too_low(governed_db, tmp_path, monkeypatch) -> None:
    gov = governor(governed_db, tmp_path, SQL_MAX_DATASET_ROWS="100")
    original = gov._explain
    monkeypatch.setattr(gov, "_explain", lambda *a: (*original(*a)[:2], 5))  # pretend the planner expects 5 rows
    result = run(gov, spec(requested_limit=None, order_by=[]))
    assert (result.decision, result.reason_code) == ("NEEDS_NARROWING", "DATASET_TOO_LARGE")
    assert not list(tmp_path.glob("datasets/*/data.parquet"))


def test_total_extraction_time_is_bounded(governed_db, tmp_path, monkeypatch) -> None:
    import app.governor as governor_module
    gov = governor(governed_db, tmp_path, SQL_MAX_EXECUTION_SECONDS="20")
    monkeypatch.setattr(governor_module, "FETCH_BATCH_ROWS", 5)
    clock = iter(range(0, 10_000, 7))  # every call advances 7 s
    monkeypatch.setattr(governor_module.time, "monotonic", lambda: next(clock))
    result = run(gov, spec(requested_limit=100))
    assert (result.decision, result.reason_code) == ("NEEDS_NARROWING", "QUERY_TIMEOUT")
    assert result.details["limit_seconds"] == 20 and not list(tmp_path.glob("datasets/*/data.parquet"))


def test_structured_log_has_decision_fields_and_no_secrets_or_values(governed_db, tmp_path) -> None:
    logger = logging.getLogger("market_sql_governor")
    records: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())
    handler = Capture(level=logging.INFO)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        run(governor(governed_db, tmp_path), spec())
        run(governor(governed_db, tmp_path), spec(requested_limit=None, order_by=[],
                                                  filters=[filt(PRICE, "date", "GTE", "2026-06-01")]))
    finally:
        logger.removeHandler(handler)
    events = [json.loads(record) for record in records]
    assert [event["decision"] for event in events] == ["DATASET_READY", "DATASET_READY"]
    for key in ("request_id", "query_id", "query_hash", "source_tables", "requested_columns", "decision",
                "reason_code", "next_action", "estimated_scan_rows", "returned_rows", "output_bytes", "runtime_ms"):
        assert key in events[0]
    text = "\n".join(records)
    for secret in (API_KEY, LOGIN_PASSWORD, governed_db["login"], "postgresql://", "BBCA"):
        assert secret not in text


# --- lookup_fact: the narrow path for specific source facts -------------------------------------------------------

def lookup_spec(**overrides: Any) -> dict[str, Any]:
    body = {"purpose": "test fact", "mode": "VALUE", "table": PRICE, "entities": ["BBCA"],
            "dates": ["2026-08-28", "2026-08-31"], "date_range": None, "columns": ["close"], "aggregations": None,
            "per_entity": None}
    body.update(overrides)
    return body


def admin_scalar(db: dict, statement: str, params: tuple = ()) -> Any:
    with psycopg.connect(db["admin"]) as connection:
        return connection.execute(statement, params).fetchone()[0]


def test_lookup_value_returns_source_values_with_fact_ids(governed_db) -> None:
    result = governor(governed_db, storage=False).lookup("test-request", lookup_spec())
    assert (result.decision, result.next_action, result.reason_code) == ("FACTS_READY", "USE_FACTS", "OK")
    assert [(f.entity, f.date, f.column, f.kind) for f in result.facts] == [
        ("BBCA", "2026-08-28", "close", "VALUE"), ("BBCA", "2026-08-31", "close", "VALUE")]
    for fact in result.facts:
        expected = admin_scalar(governed_db, f'SELECT close FROM public."{PRICE}" WHERE ticker = %s AND date = %s',
                                ("BBCA", fact.date))
        assert float(fact.value) == float(expected)
        assert fact.fact_id.startswith("fct_") and fact.query_id == result.query_id and fact.table == PRICE
    assert len({f.fact_id for f in result.facts}) == 2 and result.missing == []
    assert result.scope == {"entities": ["BBCA"], "dates": ["2026-08-28", "2026-08-31"], "columns": ["close"]}


def test_lookup_reports_explicit_keys_without_a_source_row(governed_db) -> None:
    result = governor(governed_db, storage=False).lookup("test-request", lookup_spec(
        entities=["BBCA", "ZZZZ"], dates=["2026-08-31", "2026-08-29"]))  # 2026-08-29 is a Saturday
    assert result.decision == "FACTS_READY" and len(result.facts) == 1
    assert {"entity": "ZZZZ", "date": "2026-08-31"} in result.missing
    assert {"entity": "BBCA", "date": "2026-08-29"} in result.missing


def test_lookup_value_range_of_at_most_ten_trading_dates(governed_db) -> None:
    gov = governor(governed_db, storage=False)
    ok = gov.lookup("r", lookup_spec(dates=None, date_range={"start": "2026-08-18", "end": "2026-08-31"}))
    assert ok.decision == "FACTS_READY" and 1 <= len(ok.facts) <= 10
    wide = gov.lookup("r", lookup_spec(dates=None, date_range={"start": "2026-07-01", "end": "2026-08-31"}))
    assert (wide.decision, wide.reason_code, wide.next_action) == ("REJECTED", "LOOKUP_TOO_LARGE", "USE_ANALYSIS_PATH")
    assert wide.facts == []


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        # more than 20 values: 5 entities x 5 dates x 1 column = 25
        ({"entities": ["BBCA", "BBRI", "BMRI", "TLKM", "ASII"],
          "dates": ["2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28", "2026-08-31"]}, "LOOKUP_TOO_LARGE"),
        ({"entities": ["BBCA", "BBRI", "BMRI", "TLKM", "ASII", "T001"]}, "LOOKUP_NOT_ALLOWED"),       # > 5 entities
        ({"columns": ["open", "high", "low", "close", "volume"]}, "LOOKUP_NOT_ALLOWED"),              # > 4 columns
        ({"aggregations": [{"column": "close", "function": "AVG"}]}, "LOOKUP_NOT_ALLOWED"),          # agg in VALUE
        ({"order_by": [{"column": "close", "direction": "DESC"}]}, "LOOKUP_NOT_ALLOWED"),            # ranking
        ({"rank": "top 5"}, "LOOKUP_NOT_ALLOWED"),
        ({"mode": "AGGREGATE", "columns": None, "per_entity": True,
          "aggregations": [{"column": "close", "function": "STDDEV"}]}, "LOOKUP_NOT_ALLOWED"),        # statistic
        ({"mode": "AGGREGATE", "columns": None, "per_entity": True,
          "aggregations": [{"column": "close", "function": "MEDIAN"}]}, "LOOKUP_NOT_ALLOWED"),
        ({"mode": "CORRELATION"}, "LOOKUP_NOT_ALLOWED"),
    ],
)
def test_lookup_refuses_everything_outside_the_narrow_contract(governed_db, overrides, reason) -> None:
    result = governor(governed_db, storage=False).lookup("r", lookup_spec(**overrides))
    assert (result.decision, result.reason_code, result.next_action) == ("REJECTED", reason, "USE_ANALYSIS_PATH")
    assert result.facts == []


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"table": "Unapproved_Market_Table"}, "TABLE_NOT_APPROVED"),
        ({"table": "Table_Catalog"}, "TABLE_NOT_APPROVED"),
        ({"columns": ["no_such_column"]}, "UNKNOWN_COLUMN"),
        ({"columns": ["source"]}, "COLUMN_NOT_ALLOWED"),         # ai_allowed = false in the catalog
        ({"columns": ["ingestion_time"]}, "COLUMN_NOT_ALLOWED"),  # is_sensitive
    ],
)
def test_lookup_applies_the_same_catalog_gates_as_request_data(governed_db, overrides, reason) -> None:
    result = governor(governed_db, storage=False).lookup("r", lookup_spec(**overrides))
    assert (result.decision, result.reason_code) == ("REJECTED", reason), result.message
    assert result.facts == []


def test_lookup_aggregate_is_computed_by_the_database_over_the_explicit_scope(governed_db) -> None:
    gov = governor(governed_db, storage=False)
    result = gov.lookup("r", lookup_spec(mode="AGGREGATE", columns=None, dates=None, per_entity=True,
                                         entities=["BBCA", "BBRI"],
                                         date_range={"start": "2026-08-24", "end": "2026-08-28"},
                                         aggregations=[{"column": "volume", "function": "SUM"},
                                                       {"column": "close", "function": "MAX"}]))
    assert result.decision == "FACTS_READY", result.message
    assert [(f.entity, f.aggregation, f.column) for f in result.facts] == [
        ("BBCA", "SUM", "volume"), ("BBCA", "MAX", "close"), ("BBRI", "SUM", "volume"), ("BBRI", "MAX", "close")]
    total = admin_scalar(governed_db, f'SELECT sum(volume) FROM public."{PRICE}" WHERE ticker = %s AND date '
                                      "BETWEEN %s AND %s", ("BBCA", "2026-08-24", "2026-08-28"))
    assert float(result.facts[0].value) == float(total)
    assert result.facts[0].scope == {"entities": ["BBCA"], "from": "2026-08-24", "to": "2026-08-28"}
    assert result.facts[0].kind == "AGGREGATE" and result.facts[0].date is None
    across = gov.lookup("r", lookup_spec(mode="AGGREGATE", columns=None, dates=["2026-08-31"], per_entity=False,
                                         entities=["BBCA", "BBRI"], aggregations=[{"column": "volume",
                                                                                   "function": "SUM"}]))
    assert len(across.facts) == 1 and across.facts[0].entity is None
    assert across.facts[0].scope == {"entities": ["BBCA", "BBRI"], "dates": ["2026-08-31"]}


def test_lookup_through_the_api_and_its_log_hold_ids_not_values(governed_db, caplog) -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app

    gov = governor(governed_db, storage=False)
    client = TestClient(create_app(gov.settings, governor=gov))
    headers = {"Authorization": f"Bearer {API_KEY}"}
    assert client.post("/v1/lookup", json={"request_id": "r", "spec": lookup_spec()}).status_code == 401
    assert client.post("/v1/lookup", json={"spec": lookup_spec()}, headers=headers).status_code == 422
    logger = logging.getLogger("market_sql_governor")
    records: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())
    handler = Capture(level=logging.INFO)
    logger.addHandler(handler)
    try:
        body = client.post("/v1/lookup", json={"request_id": "r", "spec": lookup_spec()}, headers=headers).json()
    finally:
        logger.removeHandler(handler)
    assert body["decision"] == "FACTS_READY" and len(body["facts"]) == 2
    event = json.loads(records[-1])
    assert event["event"] == "sql_governor_lookup" and event["fact_count"] == 2 and event["values_sha256"]
    assert [f["fact_id"] for f in event["facts"]] == [f["fact_id"] for f in body["facts"]]
    for fact in body["facts"]:
        assert str(fact["value"]) not in records[-1]
    assert API_KEY not in records[-1] and "postgresql://" not in records[-1]
