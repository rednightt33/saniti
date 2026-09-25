"""POST /v1/extract: DataNeed extractions (scope tree, point-in-time semi-joins, partitions, statuses, lineage).

Unit tests need no database. Integration tests run as the market_sql_governor login on the shared test database;
the point-in-time tables (AS_OF / EFFECTIVE_DATED) are synthetic and created only for this module.
"""
from __future__ import annotations

import importlib.util
import json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from app import extract as ex
from app.catalog_contract import sha256_json

PRICE = "Price_Stock_Indonesia_IDX"
UNIVERSE = "IDX_Stock_Universe"
SANDBOX_DATA_NEED = Path(__file__).resolve().parents[2] / "market-python-sandbox" / "app" / "data_need.py"
NEED = "need_" + "a" * 24
PLAN = "plan_" + "b" * 24


def pred(column: str, operator: str, *values: str) -> dict[str, Any]:
    return {"type": "PREDICATE", "column": column, "operator": operator, "values": list(values)}


ALL = {"type": "ALL"}


def restriction(relationship_id: int, semantics: str, right_table: str, right_scope: dict[str, Any], *,
                left_column: str = "ticker", right_column: str = "Ticker", left_time: str | None = None,
                right_time: str | None = None, direction: str | None = None, effective: tuple | None = None
                ) -> dict[str, Any]:
    return {"relationship_id": relationship_id, "join_semantics": semantics, "left_column": left_column,
            "right_column": right_column, "left_time_column": left_time, "right_time_column": right_time,
            "as_of_direction": direction, "effective_from_column": effective[0] if effective else None,
            "effective_to_column": effective[1] if effective else None, "right_table": right_table,
            "right_scope": right_scope, "right_scope_sha256": sha256_json(right_scope)}


def extraction(table: str = PRICE, columns: tuple[str, ...] = ("ticker", "date", "close"), scope: dict = ALL,
               restrictions: list | None = None, window: tuple[str, str] | None = ("2025-01-02", "2025-03-31"),
               partition: dict | None = None, order_by: list | None = None,
               rid: str = "data_request_1_A") -> dict[str, Any]:
    return {"extraction_version": "extraction_spec/v1", "data_request_id": rid, "source_table": table,
            "columns": list(columns), "scope": scope, "restrictions": restrictions or [],
            "window": {"from": window[0], "to": window[1]} if window else None, "entity_partition": partition,
            "order_by": order_by or []}


def lineage(spec: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    restrictions = [r for r in spec["restrictions"]]
    body = {"need_id": NEED, "spec_sha256": "c" * 64, "request_group_id": "data_request_1", "revision": 1,
            "data_request_id": spec["data_request_id"], "logical_name": "prices",
            "scope_sha256": sha256_json(spec["scope"]), "restriction_sha256": sha256_json(restrictions),
            "plan_id": PLAN, "part_key": ex.part_key(spec["window"], spec["entity_partition"]),
            "envelope": {"from": spec["window"]["from"], "to": spec["window"]["to"], "range_ids": ["r1"]}
            if spec["window"] else None, "catalog_sha256": None, "extraction_sha256": ex.extraction_sha256(spec)}
    body.update(overrides)
    return body


# ---------------------------------------------------------------- unit: binding, compilation, partitioning

def contract(**extra_relationships: Any) -> dict[str, Any]:
    def column(kind: str, filterable: bool = True) -> dict[str, Any]:
        return {"data_type": kind, "filter_allowed": filterable, "unit": None}

    return {
        "tables": {PRICE: {"table_name": PRICE, "entity_column": "ticker", "time_column": "date",
                           "primary_key_columns": ["ticker", "date"]},
                   UNIVERSE: {"table_name": UNIVERSE, "entity_column": "Ticker", "time_column": None,
                              "primary_key_columns": ["Ticker"]}},
        "columns": {PRICE: {"ticker": column("text"), "date": column("date"), "close": column("numeric"),
                            "volume": column("bigint"), "query_date": column("date", False)},
                    UNIVERSE: {"Ticker": column("text"), "Sector": column("text"), "Industry": column("text"),
                               "Shares": column("bigint")}},
        "relationships": [{"relationship_id": 7, "left_table": UNIVERSE, "left_columns": ["Ticker"],
                           "right_table": PRICE, "right_columns": ["ticker"], "is_allowed": True,
                           "requires_preaggregation": False, "supported_join_semantics": ["CURRENT_STATE"],
                           "left_time_column": None, "right_time_column": None, "effective_from_column": None,
                           "effective_to_column": None}],
    }


def bind(spec: dict[str, Any], catalog: dict[str, Any] | None = None) -> ex.BoundExtraction:
    return ex.bind(ex.ExtractionSpec.model_validate(spec), catalog or contract(), max_in_values=500, max_columns=60)


def test_the_executed_scope_uses_the_sandbox_canonical_form_and_hashes() -> None:
    """Contract: the approved scope (sandbox) and the compiled scope (Governor) render and hash identically."""
    module_spec = importlib.util.spec_from_file_location("sandbox_data_need", SANDBOX_DATA_NEED)
    sandbox = importlib.util.module_from_spec(module_spec)
    sys.modules["sandbox_data_need"] = sandbox  # dataclasses resolve annotations through sys.modules
    module_spec.loader.exec_module(sandbox)
    raw = {"type": "AND", "children": [
        {"type": "PREDICATE", "column": "close", "operator": "BETWEEN", "value": [1000, 2500.50]},
        {"type": "OR", "children": [
            {"type": "PREDICATE", "column": "ticker", "operator": "IN", "value": ["BBRI", "BBCA", "BBRI"]},
            {"type": "NOT", "child": {"type": "PREDICATE", "column": "volume", "operator": "LT", "value": 10}}]},
        {"type": "PREDICATE", "column": "date", "operator": "GTE", "value": "2025-02-03"}]}
    approved = sandbox.canonical_scope(raw, {"close": "numeric", "ticker": "text", "volume": "bigint",
                                             "date": "date"})
    bound = bind(extraction(scope=approved))
    assert bound.canonical_scope == approved
    assert ex.executed_scope(bound)["scope_sha256"] == sandbox.sha256_json(approved)


def test_values_are_bound_parameters_and_never_sql_text() -> None:
    marker = "Banks'); DROP TABLE x; --"
    spec = extraction(scope=pred("ticker", "IN", marker, "BBCA"),
                      restrictions=[restriction(7, "CURRENT_STATE", UNIVERSE, pred("Industry", "EQ", marker))])
    compiled = ex.compile_extraction(bind(spec), 1001)
    assert marker not in compiled.text and "DROP" not in compiled.text
    assert [marker, "BBCA"] in [p for p in compiled.params if isinstance(p, list)] or \
        sorted([marker, "BBCA"]) in [sorted(p) for p in compiled.params if isinstance(p, list)]
    assert compiled.params[-1] == 1001 and "LIMIT" in compiled.text
    assert "EXISTS (SELECT 1 FROM" in compiled.text and '"r0"."Ticker" = "t0"."ticker"' in compiled.text
    assert ex.compile_extraction(bind(spec), None).text.count("LIMIT") == 0


def test_the_order_is_total_and_deterministic() -> None:
    bound = bind(extraction(order_by=[{"column": "date", "direction": "DESC"}]))
    assert bound.order_by == [("date", "DESC"), ("ticker", "ASC")]
    assert bind(extraction()).order_by == [("ticker", "ASC"), ("date", "ASC")]


@pytest.mark.parametrize("spec, code", [
    (extraction(table="Unapproved"), "TABLE_NOT_APPROVED"),
    (extraction(columns=("ticker", "date", "secret")), "COLUMN_NOT_ALLOWED"),
    (extraction(columns=("date", "close")), "KEY_COLUMNS_REQUIRED"),
    (extraction(scope=pred("query_date", "EQ", "2025-01-02")), "FILTER_NOT_ALLOWED"),
    (extraction(scope=pred("ticker", "GT", "A")), "INVALID_FILTER_OPERATOR"),
    (extraction(scope=pred("close", "EQ", "1000.50")), "NON_CANONICAL_VALUE"),
    (extraction(scope=pred("volume", "EQ", "many")), "INVALID_FILTER_VALUE"),
    (extraction(scope=pred("close", "BETWEEN", "9", "1")), "INVALID_FILTER_VALUE"),
    (extraction(scope={"type": "AND", "children": [pred("ticker", "EQ", "A")]}), "INVALID_SCOPE"),
    (extraction(scope={"type": "AND", "children": [ALL, pred("ticker", "EQ", "A")]}), "INVALID_SCOPE"),
    (extraction(window=None), "TIME_WINDOW_REQUIRED"),
    (extraction(window=("2025-03-01", "2025-01-01")), "INVALID_TIME_WINDOW"),
    (extraction(table=UNIVERSE, columns=("Ticker", "Sector")), "INVALID_TIME_WINDOW"),
    (extraction(partition={"modulus": 3, "remainder": 3}), "INVALID_ENTITY_PARTITION"),
    (extraction(order_by=[{"column": "volume", "direction": "ASC"}]), "ORDERING_COLUMN_INVALID"),
    (extraction(restrictions=[restriction(8, "CURRENT_STATE", UNIVERSE, ALL)]), "UNKNOWN_RELATIONSHIP"),
    (extraction(restrictions=[restriction(7, "EXACT_DATE", UNIVERSE, ALL, left_time="date",
                                          right_time="date")]), "JOIN_SEMANTICS_UNAVAILABLE"),
    (extraction(restrictions=[restriction(7, "CURRENT_STATE", UNIVERSE, ALL, right_column="Sector")]),
     "RELATIONSHIP_KEY_MISMATCH"),
    (extraction(restrictions=[{**restriction(7, "CURRENT_STATE", UNIVERSE, pred("Sector", "EQ", "Banks")),
                               "right_scope_sha256": "0" * 64}]), "SCOPE_HASH_MISMATCH"),
])
def test_catalog_policy_is_rechecked(spec, code) -> None:
    with pytest.raises(ex.ExtractStop) as caught:
        bind(spec)
    assert (caught.value.status, caught.value.code) == ("REJECTED_POLICY", code)


def point_in_time_contract() -> dict[str, Any]:
    catalog = contract()
    catalog["tables"]["Shares_History"] = {"table_name": "Shares_History", "entity_column": "ticker",
                                           "time_column": "effective_date",
                                           "primary_key_columns": ["ticker", "effective_date"]}
    catalog["columns"]["Shares_History"] = {"ticker": {"data_type": "text", "filter_allowed": True},
                                            "effective_date": {"data_type": "date", "filter_allowed": True},
                                            "shares": {"data_type": "bigint", "filter_allowed": True}}
    catalog["relationships"].append({
        "relationship_id": 9, "left_table": PRICE, "left_columns": ["ticker", "date"], "right_table": "Shares_History",
        "right_columns": ["ticker", "effective_date"], "is_allowed": True, "requires_preaggregation": False,
        "supported_join_semantics": ["AS_OF"], "left_time_column": "date", "right_time_column": "effective_date",
        "effective_from_column": None, "effective_to_column": None})
    return catalog


def test_as_of_is_backward_only_and_uses_the_catalog_time_columns() -> None:
    good = restriction(9, "AS_OF", "Shares_History", pred("shares", "GTE", "200"), right_column="ticker",
                       left_time="date", right_time="effective_date", direction="BACKWARD")
    compiled = ex.compile_extraction(bind(extraction(restrictions=[good]), point_in_time_contract()), None)
    assert 'ORDER BY "r0"."effective_date" DESC LIMIT 1' in compiled.text
    assert '"r0"."effective_date" <= "t0"."date"' in compiled.text
    for bad, code in ((dict(good, as_of_direction=None), "TEMPORAL_DIRECTION_NOT_ALLOWED"),
                      (dict(good, right_time_column="ticker"), "TIME_COLUMN_MISMATCH")):
        with pytest.raises(ex.ExtractStop) as caught:
            bind(extraction(restrictions=[bad]), point_in_time_contract())
        assert caught.value.code == code


def test_partitioning_decisions_follow_the_violated_limit() -> None:
    limits = ex.Limits(max_scan_rows=1000, max_result_rows=100, max_plan_cost=1e6, max_window_days=400, max_parts=64)
    dated = bind(extraction(window=("2025-01-02", "2025-12-31")))
    static = bind(extraction(table=UNIVERSE, columns=("Ticker", "Sector"), window=None))
    fits = ex.Estimates(scan_rows=900, result_rows=90, plan_cost=10)
    assert ex.partitioning(dated, fits, limits, set()) is None
    rows = ex.partitioning(dated, ex.Estimates(900, 450, 10), limits, set())
    assert rows.status == "APPROVED_WITH_PARTITIONING" and rows.details["partitioning"] == {"kind": "DATE",
                                                                                              "parts": 6}
    assert ex.partitioning(static, ex.Estimates(900, 450, 10), limits, set()).details["partitioning"]["kind"] == \
        "ENTITY"
    # a sequential scan reads the whole table whatever the window: only a time index lets a date split help
    assert ex.partitioning(dated, ex.Estimates(5000, 90, 10), limits, set()).status == "REJECTED_SCAN_SIZE"
    assert ex.partitioning(dated, ex.Estimates(5000, 90, 10), limits, {"date"}).status == \
        "APPROVED_WITH_PARTITIONING"
    long = bind(extraction(window=("2015-01-01", "2025-12-31")))
    assert ex.partitioning(long, fits, limits, set()).details["partitioning"] == {"kind": "DATE", "parts": 11}
    assert ex.partitioning(dated, ex.Estimates(900, 450, 10), limits, set(), part_count=20).status == \
        "REJECTED_ROW_LIMIT"
    joined = bind(extraction(restrictions=[restriction(7, "CURRENT_STATE", UNIVERSE, ALL)]))
    costly = ex.Estimates(900, 90, 1e9)  # would need 1250 parts, above the 64-part limit
    assert ex.partitioning(joined, costly, limits, set()).status == "REJECTED_JOIN_COST"
    assert ex.partitioning(dated, costly, limits, set()).status == "REJECTED_COMPUTE_COST"
    single_day = bind(extraction(window=("2025-01-02", "2025-01-02")))
    assert ex.partitioning(single_day, ex.Estimates(900, 450, 10), limits, set()).details["partitioning"] == \
        {"kind": "ENTITY", "parts": 6}


def test_windows_split_contiguously_and_exactly() -> None:
    parts = ex.split_window(date(2025, 1, 1), date(2025, 1, 10), 3)
    assert parts[0][0] == date(2025, 1, 1) and parts[-1][1] == date(2025, 1, 10)
    assert all(b[0] == a[1] + timedelta(days=1) for a, b in zip(parts, parts[1:]))


# ---------------------------------------------------------------- integration (PostgreSQL)

psycopg = pytest.importorskip("psycopg")
pq = pytest.importorskip("pyarrow.parquet")

from app.config import Settings  # noqa: E402
from app.governor import Database, Extractor, Governor  # noqa: E402
from app.store import LocalStore  # noqa: E402
from conftest import base_env  # noqa: E402


def extractor(db: dict, tmp_path: Path, **limits: str) -> Extractor:
    env = base_env(GOVERNOR_DATABASE_URL=db["login"], SQL_DATASET_LOCAL_DIR=str(tmp_path), **limits)
    settings = Settings.from_env(env)
    return Extractor(Governor(settings, Database(settings), LocalStore(str(tmp_path))))


def admin(db: dict, statement: str, params: tuple = ()) -> list[tuple]:
    with psycopg.connect(db["admin"], autocommit=True) as connection:
        cursor = connection.execute(statement, params)
        return cursor.fetchall() if cursor.description else []


def rows_of(ext: Extractor, outcome: dict[str, Any]) -> list[dict[str, Any]]:
    assert outcome["status"] == "APPROVED", outcome
    path = Path(ext.governor.store.root) / "datasets" / outcome["dataset"]["dataset_id"] / "data.parquet"
    return pq.read_table(path).to_pylist()


def manifest_of(ext: Extractor, outcome: dict[str, Any]) -> dict[str, Any]:
    path = Path(ext.governor.store.root) / "datasets" / outcome["dataset"]["dataset_id"] / "manifest.json"
    return json.loads(path.read_text())


def submit(ext: Extractor, spec: dict[str, Any], planned: int = 1, **lineage_overrides: Any) -> dict[str, Any]:
    return ext.handle("test-extract", spec, lineage(spec, **lineage_overrides), part_count=planned)


@pytest.fixture(scope="module")
def pit(governed_db):
    """Synthetic point-in-time reference tables with AS_OF and EFFECTIVE_DATED catalog relationships."""
    admin(governed_db, '''
CREATE TABLE public."Shares_History" (ticker text, effective_date date, shares bigint,
                                      PRIMARY KEY (ticker, effective_date));
INSERT INTO public."Shares_History" VALUES ('BBCA', '2025-01-01', 100), ('BBCA', '2025-02-03', 300),
                                           ('BBRI', '2025-02-10', 50);
CREATE TABLE public."Sector_History" ("Ticker" text, "Sector" text, valid_from date, valid_to date,
                                      PRIMARY KEY ("Ticker", valid_from));
INSERT INTO public."Sector_History" VALUES ('BBCA', 'Banks', '2025-01-01', '2025-02-01'),
                                           ('BBCA', 'Finance', '2025-02-01', NULL),
                                           ('BMRI', 'Banks', '2025-02-03', NULL);
GRANT SELECT ON public."Shares_History", public."Sector_History" TO market_ai_sql_reader;
INSERT INTO public."AI_table_catalog" (table_name, description, category, grain, primary_key_columns, time_column,
    entity_column, is_active, ai_access_level, coverage_enabled, documentation_status, data_domain, entity_type,
    asset_type, supported_frequencies, time_semantics) VALUES
 ('Shares_History', 'Synthetic.', 'REFERENCE', 'ticker x effective_date', ARRAY['ticker','effective_date'],
  'effective_date', 'ticker', true, 'BOUNDED_READ', false, 'VERIFIED', 'MARKET', 'STOCK', 'IDX_EQUITY',
  ARRAY['1D'], 'Effective date'),
 ('Sector_History', 'Synthetic.', 'REFERENCE', 'Ticker x valid_from', ARRAY['Ticker','valid_from'], NULL, 'Ticker',
  true, 'BOUNDED_READ', false, 'VERIFIED', 'MARKET', 'STOCK', 'IDX_EQUITY', ARRAY['STATIC'], 'Validity range');
INSERT INTO public."AI_column_catalog" (table_name, column_name, ordinal_position, description, data_type,
    semantic_type, nullable, is_primary_key, allowed_aggregations, filter_allowed, group_by_allowed,
    documentation_status) VALUES
 ('Shares_History', 'ticker', 1, 'x', 'text', 'IDENTIFIER', false, true, ARRAY['COUNT'], true, true, 'VERIFIED'),
 ('Shares_History', 'effective_date', 2, 'x', 'date', 'TIME', false, true, ARRAY['COUNT'], true, true, 'VERIFIED'),
 ('Shares_History', 'shares', 3, 'x', 'bigint', 'MEASURE', true, false, ARRAY['SUM'], true, false, 'VERIFIED'),
 ('Sector_History', 'Ticker', 1, 'x', 'text', 'IDENTIFIER', false, true, ARRAY['COUNT'], true, true, 'VERIFIED'),
 ('Sector_History', 'Sector', 2, 'x', 'text', 'DIMENSION', true, false, ARRAY['COUNT'], true, true, 'VERIFIED'),
 ('Sector_History', 'valid_from', 3, 'x', 'date', 'TIME', false, true, ARRAY['COUNT'], true, true, 'VERIFIED'),
 ('Sector_History', 'valid_to', 4, 'x', 'date', 'TIME', true, false, ARRAY['COUNT'], true, true, 'VERIFIED');
''')
    as_of = admin(governed_db, '''
INSERT INTO public."AI_catalog_relationships" (left_table, left_columns, right_table, right_columns,
    relationship_type, temporal_rule, safe_output_grain, requires_preaggregation, description, version, is_allowed,
    supported_join_semantics, left_time_column, right_time_column)
VALUES ('Price_Stock_Indonesia_IDX', ARRAY['ticker','date'], 'Shares_History', ARRAY['ticker','effective_date'],
        'MANY_TO_ONE', 'Latest shares at or before the date', 'date x ticker', false, 'Synthetic.', 'v1', true,
        ARRAY['AS_OF'], 'date', 'effective_date') RETURNING relationship_id''')[0][0]
    effective = admin(governed_db, '''
INSERT INTO public."AI_catalog_relationships" (left_table, left_columns, right_table, right_columns,
    relationship_type, temporal_rule, safe_output_grain, requires_preaggregation, description, version, is_allowed,
    supported_join_semantics, effective_from_column, effective_to_column)
VALUES ('Price_Stock_Indonesia_IDX', ARRAY['ticker'], 'Sector_History', ARRAY['Ticker'], 'MANY_TO_ONE',
        'Classification valid on the date', 'date x ticker', false, 'Synthetic.', 'v1', true,
        ARRAY['EFFECTIVE_DATED'], 'valid_from', 'valid_to') RETURNING relationship_id''')[0][0]
    admin(governed_db, "ANALYZE")
    yield {"as_of": as_of, "effective": effective}
    admin(governed_db, '''
DELETE FROM public."AI_catalog_relationships" WHERE right_table IN ('Shares_History', 'Sector_History');
DELETE FROM public."AI_column_catalog" WHERE table_name IN ('Shares_History', 'Sector_History');
DELETE FROM public."AI_table_catalog" WHERE table_name IN ('Shares_History', 'Sector_History');
DROP TABLE public."Shares_History", public."Sector_History";''')


def universe_relationship(db: dict) -> int:
    return admin(db, '''SELECT relationship_id FROM public."AI_catalog_relationships"
                        WHERE left_table = 'IDX_Stock_Universe' AND right_table = 'Price_Stock_Indonesia_IDX' ''')[0][0]


def test_an_inner_current_state_restriction_keeps_only_matching_entities(governed_db, tmp_path) -> None:
    ext = extractor(governed_db, tmp_path)
    industry = admin(governed_db, '''SELECT "Industry" FROM public."IDX_Stock_Universe" GROUP BY 1
                                     ORDER BY count(*) DESC, 1 LIMIT 1''')[0][0]
    members = {r[0] for r in admin(governed_db, 'SELECT "Ticker" FROM public."IDX_Stock_Universe" '
                                                'WHERE "Industry" = %s', (industry,))}
    rule = restriction(universe_relationship(governed_db), "CURRENT_STATE", UNIVERSE, pred("Industry", "EQ", industry))
    spec = extraction(restrictions=[rule])
    outcome = submit(ext, spec)
    rows = rows_of(ext, outcome)
    assert {r["ticker"] for r in rows} == members and 0 < len(members) < 30
    assert min(r["date"] for r in rows) >= date(2025, 1, 2) and max(r["date"] for r in rows) <= date(2025, 3, 31)
    assert [(r["ticker"], r["date"]) for r in rows] == sorted((r["ticker"], r["date"]) for r in rows)
    manifest = manifest_of(ext, outcome)
    executed = manifest["executed_scope"]
    assert executed["scope_sha256"] == sha256_json(ALL)
    assert executed["restriction_sha256"] == sha256_json([rule])
    assert executed["sampling"] is False and executed["truncation"] is False and manifest["truncated"] is False
    assert manifest["lineage"]["need_id"] == NEED and manifest["lineage"]["part_key"] == executed["part_key"]
    assert outcome["executed_scope_sha256"] == sha256_json(executed)
    assert "Industry" not in json.dumps(outcome) and industry not in json.dumps(outcome)  # no values returned


def test_entity_partitions_are_complete_and_disjoint(governed_db, tmp_path) -> None:
    ext = extractor(governed_db, tmp_path)
    whole = {(r["ticker"], r["date"]) for r in rows_of(ext, submit(ext, extraction()))}
    parts = [{(r["ticker"], r["date"]) for r in rows_of(ext, submit(
        ext, extraction(partition={"modulus": 3, "remainder": k}), planned=3))} for k in range(3)]
    assert set().union(*parts) == whole and sum(len(p) for p in parts) == len(whole)
    assert all(parts)
    assert not {r[0] for r in parts[0]} & {r[0] for r in parts[1]}  # an entity lives in exactly one part


def test_a_result_above_the_row_cap_is_partitioned_never_truncated(governed_db, tmp_path) -> None:
    ext = extractor(governed_db, tmp_path, SQL_MAX_DATASET_ROWS="500")
    outcome = submit(ext, extraction())
    assert outcome["status"] == "APPROVED_WITH_PARTITIONING" and outcome["next_action"] == "PARTITION_AND_RESUBMIT"
    assert outcome["partitioning"]["kind"] == "DATE" and outcome["dataset"] is None if "dataset" in outcome else True
    assert not list(tmp_path.glob("datasets/*/data.parquet"))
    windows = ex.split_window(date(2025, 1, 2), date(2025, 3, 31), outcome["partitioning"]["parts"])
    total = 0
    for start, end in windows:
        part = submit(ext, extraction(window=(start.isoformat(), end.isoformat())),
                      planned=outcome["partitioning"]["parts"])
        total += len(rows_of(ext, part))
    assert total == 30 * len([d for d in range(89) if (date(2025, 1, 2) + timedelta(days=d)).weekday() < 5])


def test_the_row_cap_holds_even_when_the_estimate_is_too_low(governed_db, tmp_path, monkeypatch) -> None:
    ext = extractor(governed_db, tmp_path, SQL_MAX_DATASET_ROWS="500")
    original = ext.governor._explain
    monkeypatch.setattr(ext.governor, "_explain", lambda *a: (*original(*a)[:2], 5))
    outcome = submit(ext, extraction())
    assert outcome["status"] == "APPROVED_WITH_PARTITIONING" and outcome["code"] == "ROWS_LIMIT"
    assert not list(tmp_path.glob("datasets/*/data.parquet"))


def test_policy_refusals_name_the_logical_request(governed_db, tmp_path) -> None:
    ext = extractor(governed_db, tmp_path)
    outcome = submit(ext, extraction(columns=("ticker", "date", "source")))
    assert (outcome["status"], outcome["code"], outcome["data_request_id"], outcome["next_action"]) == (
        "REJECTED_POLICY", "COLUMN_NOT_ALLOWED", "data_request_1_A", "REVISE_DATA_NEED_SPEC")
    spec = extraction()
    mislabeled = ext.handle("test-extract", spec, lineage(spec, part_key="0" * 64))
    assert (mislabeled["status"], mislabeled["code"]) == ("REJECTED_POLICY", "LINEAGE_MISMATCH")


def test_exact_date_restriction_matches_the_same_date(governed_db, tmp_path) -> None:
    ext = extractor(governed_db, tmp_path)
    rel = admin(governed_db, '''SELECT relationship_id FROM public."AI_catalog_relationships"
                                WHERE left_table = 'Price_Stock_Indonesia_IDX'
                                  AND right_table = 'Feature_01_Stock_Daily' ''')[0][0]
    rule = restriction(rel, "EXACT_DATE", "Feature_01_Stock_Daily", pred("ticker", "EQ", "BBCA"),
                       right_column="ticker", left_time="date", right_time="date")
    rows = rows_of(ext, submit(ext, extraction(restrictions=[rule])))
    assert {r["ticker"] for r in rows} == {"BBCA"} and len(rows) > 50


def test_as_of_uses_the_latest_reference_row_at_or_before_each_date(governed_db, tmp_path, pit) -> None:
    ext = extractor(governed_db, tmp_path)
    rule = restriction(pit["as_of"], "AS_OF", "Shares_History", pred("shares", "GTE", "200"), right_column="ticker",
                       left_time="date", right_time="effective_date", direction="BACKWARD")
    rows = rows_of(ext, submit(ext, extraction(restrictions=[rule])))
    # BBCA had 100 shares until 2025-02-02 and 300 from 2025-02-03; BBRI never reached 200
    assert {r["ticker"] for r in rows} == {"BBCA"}
    assert min(r["date"] for r in rows) == date(2025, 2, 3)
    none = restriction(pit["as_of"], "AS_OF", "Shares_History", pred("shares", "LT", "80"), right_column="ticker",
                       left_time="date", right_time="effective_date", direction="BACKWARD")
    rows = rows_of(ext, submit(ext, extraction(restrictions=[none])))
    assert {r["ticker"] for r in rows} == {"BBRI"} and min(r["date"] for r in rows) == date(2025, 2, 10)


def test_effective_dated_uses_the_row_valid_on_each_date(governed_db, tmp_path, pit) -> None:
    ext = extractor(governed_db, tmp_path)
    rule = restriction(pit["effective"], "EFFECTIVE_DATED", "Sector_History", pred("Sector", "EQ", "Banks"),
                       left_time="date", effective=("valid_from", "valid_to"))
    rows = rows_of(ext, submit(ext, extraction(restrictions=[rule])))
    bbca = [r["date"] for r in rows if r["ticker"] == "BBCA"]
    bmri = [r["date"] for r in rows if r["ticker"] == "BMRI"]
    assert {r["ticker"] for r in rows} == {"BBCA", "BMRI"}
    assert max(bbca) == date(2025, 1, 31)  # valid_to is exclusive: Finance from 2025-02-01
    assert min(bmri) == date(2025, 2, 3) and max(bmri) == date(2025, 3, 31)


def test_the_extraction_log_has_decisions_and_no_values(governed_db, tmp_path) -> None:
    logger = logging.getLogger("market_sql_governor")
    records: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    handler = Capture(level=logging.INFO)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        submit(extractor(governed_db, tmp_path), extraction(scope=pred("ticker", "EQ", "BBCA")))
    finally:
        logger.removeHandler(handler)
    event = next(json.loads(r) for r in records if '"sql_governor_extract"' in r)
    assert event["status"] == "APPROVED" and event["data_request_id"] == "data_request_1_A"
    assert event["need_id"] == NEED and event["rows"] > 0
    assert "BBCA" not in json.dumps(event) and "password" not in json.dumps(event).lower()
