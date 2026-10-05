"""Two-path analysis: catalog contracts, data-plan lineage, executed scope, and the internal validator manifest.

The sandbox approves an Analysis Spec V2 against a catalog contract and, before any analysis runs, compares the
Governor's executed scope (derived from the validated query, not from the caller) with the approved spec.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.catalog_contract import canonical_value, executed_scope, load_contract, sha256_json
from app.config import Settings
from app.datasets import DatasetService, safe_manifest
from app.main import create_app
from conftest import API_KEY, base_env
from test_governor_postgres import PRICE, cols, filt, governor, spec

UNIVERSE = "IDX_Stock_Universe"
ACCESS_KEY = "test-dataset-access-key-" + "a" * 24


def lineage(**overrides: Any) -> dict[str, Any]:
    body = {"spec_id": "spec_" + "1" * 24, "spec_sha256": "a" * 64, "scope_sha256": "b" * 64,
            "data_plan_id": "plan_" + "2" * 24, "logical_input_name": "prices", "part_index": 1, "part_count": 1,
            "request_sha256": "c" * 64, "catalog_sha256": None, "partition": None}
    body.update(overrides)
    return body


def banks_request() -> dict[str, Any]:
    """Prices of the stocks whose universe row satisfies an attribute predicate, via the catalog relationship."""
    return spec(columns=cols(PRICE, "ticker", "date", "close"), joins=[{"table": UNIVERSE, "relationship_id": None}],
                filters=[filt(UNIVERSE, "Industry", "EQ", "Industry-1"),
                         filt(PRICE, "date", "BETWEEN", ["2026-07-01", "2026-08-31"])],
                order_by=[], requested_limit=None)



def contract(db: dict, tables: list[str]) -> dict[str, Any]:
    gov = governor(db, storage=False)
    return gov.catalog_contract("test-request", tables)


def test_catalog_contract_carries_subject_metadata_and_per_table_hashes(governed_db) -> None:
    result = contract(governed_db, [PRICE, UNIVERSE, "Unapproved_Market_Table", "Inactive_Table"])
    assert result["subject_metadata"] is True
    assert sorted(result["tables"]) == [UNIVERSE, PRICE]
    assert sorted(result["unknown_tables"]) == ["Inactive_Table", "Unapproved_Market_Table"]
    price, universe = result["tables"][PRICE], result["tables"][UNIVERSE]
    assert (price["data_domain"], price["entity_type"], price["asset_type"]) == ("MARKET", "STOCK", "IDX_EQUITY")
    assert price["supported_frequencies"] == ["1D"] and universe["supported_frequencies"] == ["STATIC"]
    assert price["subject_metadata_status"] == "INFERRED"  # seeded values are never VERIFIED by the migration
    # the catalog-policy exclusions stay excluded from what a spec may name
    assert "source" not in result["columns"][PRICE] and "ingestion_time" not in result["columns"][PRICE]
    assert result["columns"][PRICE]["query_date"]["filter_allowed"] is False
    assert {r["relationship_id"] for r in result["relationships"]} >= {
        r["relationship_id"] for r in result["relationships"] if {r["left_table"], r["right_table"]} == {PRICE, UNIVERSE}}
    # hashes are content hashes: a second read is identical
    again = contract(governed_db, [UNIVERSE, PRICE])
    assert again["tables"][PRICE]["catalog_table_sha256"] == price["catalog_table_sha256"]


def test_a_catalog_change_changes_the_table_hash(governed_db) -> None:
    import psycopg

    before = contract(governed_db, [UNIVERSE])["tables"][UNIVERSE]["catalog_table_sha256"]
    with psycopg.connect(governed_db["admin"], autocommit=True) as admin:
        admin.execute('UPDATE public."AI_column_catalog" SET unit = %s WHERE table_name = %s AND column_name = %s',
                      ("label", UNIVERSE, "Sector"))
        try:
            after = contract(governed_db, [UNIVERSE])["tables"][UNIVERSE]["catalog_table_sha256"]
        finally:
            admin.execute('UPDATE public."AI_column_catalog" SET unit = NULL WHERE table_name = %s AND column_name = %s',
                          (UNIVERSE, "Sector"))
    assert before != after


def test_without_the_subject_migration_the_contract_says_so() -> None:
    calls: list[str] = []

    def run(statement: str, params: tuple) -> list[dict[str, Any]]:
        calls.append(statement)
        if "information_schema" in statement:
            return [{"present": 0}]
        if "AI_table_catalog" in statement:
            assert "data_domain" not in statement
            return [{"table_name": PRICE, "description": "d", "grain": "g", "primary_key_columns": ["ticker", "date"],
                     "time_column": "date", "entity_column": "ticker", "is_active": True,
                     "ai_access_level": "BOUNDED_READ"}]
        return []

    result = load_contract(run, [PRICE])
    assert result["subject_metadata"] is False and result["tables"][PRICE]["data_domain"] is None


def test_a_compiled_request_records_lineage_and_the_executed_attribute_scope(governed_db, tmp_path) -> None:
    gov = governor(governed_db, tmp_path)
    plan = lineage()
    result = gov.handle("test-request", banks_request(), lineage=plan)
    assert result.decision == "DATASET_READY", (result.reason_code, result.message)
    stored = json.loads((Path(gov.store.root) / "datasets" / result.dataset.dataset_id / "manifest.json").read_text())
    assert stored["manifest_version"] == "v2" and stored["lineage"] == plan
    scope = stored["executed_scope"]
    assert scope["source_table"] == PRICE and scope["joins"][0]["table"] == UNIVERSE
    assert {"table": UNIVERSE, "column": "Industry", "operator": "EQ", "values": ["Industry-1"]} in scope["filters"]
    assert {"table": PRICE, "column": "date", "operator": "BETWEEN", "values": ["2026-07-01", "2026-08-31"]} \
        in scope["filters"]
    assert stored["request_sha256"] == sha256_json(stored["request_spec"])
    contracts = stored["source_contracts"]
    assert contracts[PRICE]["grain"] == ["ticker", "date"] and contracts[PRICE]["entity_column"] == "ticker"
    assert contracts[UNIVERSE]["frequency"] == "STATIC" and contracts[PRICE]["entity_type"] == "STOCK"


def test_the_validator_manifest_goes_only_with_the_sandbox_grant(governed_db, tmp_path) -> None:
    gov = governor(governed_db, tmp_path)
    result = gov.handle("test-request", banks_request(), lineage=lineage())
    settings = Settings.from_env(base_env(SQL_DATASET_LOCAL_DIR=str(tmp_path), SQL_GOVERNOR_DATASET_ACCESS_KEY=ACCESS_KEY))
    service = DatasetService(settings, gov.store)
    dataset_id = result.dataset.dataset_id
    model_view = service.manifest(dataset_id)
    assert "validator_manifest" not in model_view and "executed_scope" not in json.dumps(model_view)
    assert "Industry-1" not in json.dumps(model_view)  # filter values are not shown to the model
    grant = service.access(dataset_id, request_id="r", analysis_id="ana_" + "0" * 24)
    internal = grant["validator_manifest"]
    assert internal["lineage"]["spec_id"] == "spec_" + "1" * 24
    assert internal["executed_scope"]["joins"][0]["relationship_id"] >= 1
    text = json.dumps(internal)
    assert "SELECT" not in text and "datasets/" not in text and "X-Amz" not in text


@pytest.mark.parametrize("bad", [
    {"part_index": 3, "part_count": 2},
    {"spec_id": "not-a-spec"},
    {"scope_sha256": "short"},
    {"unexpected": "field"},
])
def test_malformed_lineage_is_refused_before_any_query(tmp_path, bad) -> None:
    from test_units import FakeGovernor

    fake = FakeGovernor()
    app = create_app(Settings.from_env(base_env(SQL_DATASET_LOCAL_DIR=str(tmp_path))), governor=fake)
    response = TestClient(app).post("/v1/query", headers={"Authorization": f"Bearer {API_KEY}"},
                                    json={"request_id": "r1", "spec": {}, "lineage": lineage(**bad)})
    assert response.status_code == 422 and fake.calls == []


def test_the_catalog_contract_endpoint_takes_either_key_but_never_rows(governed_db, tmp_path) -> None:
    settings = Settings.from_env(base_env(GOVERNOR_DATABASE_URL=governed_db["login"], SQL_DATASET_LOCAL_DIR=str(tmp_path),
                                          SQL_GOVERNOR_DATASET_ACCESS_KEY=ACCESS_KEY))
    client = TestClient(create_app(settings))
    body = {"request_id": "r1", "tables": [UNIVERSE]}
    assert client.post("/v1/catalog/contract", json=body).status_code == 401
    for key in (API_KEY, ACCESS_KEY):
        response = client.post("/v1/catalog/contract", json=body, headers={"Authorization": f"Bearer {key}"})
        assert response.status_code == 200
        assert "BBCA" not in response.text  # metadata only
    bad = client.post("/v1/catalog/contract", json={"request_id": "r1", "tables": ["x; drop"]},
                      headers={"Authorization": f"Bearer {API_KEY}"})
    assert bad.status_code == 422


@pytest.mark.parametrize(("value", "text"), [
    ("Banks", "Banks"), (5, "5"), (5.0, "5"), (0.10, "0.1"), (True, "true"), (-0.0, "0"), (1e-7, "0.0000001"),
])
def test_canonical_values_have_one_text_form(value, text) -> None:
    assert canonical_value(value) == text


# ---------------------------------------------------------------- dimension values

def test_dimension_values_are_exact_stored_values_without_counts(governed_db) -> None:
    gov = governor(governed_db, storage=False)
    result = gov.dimension_values("r", UNIVERSE, "Industry", None)
    assert result["status"] == "VALUES_READY" and result["truncated"] is False
    assert result["values"] == sorted(result["values"]) and all(isinstance(v, str) for v in result["values"])
    assert set(result) == {"status", "table", "column", "match", "values", "truncated", "note"}  # no counts
    matched = gov.dimension_values("r", UNIVERSE, "Industry", "USTRY-1")
    assert matched["values"] and all("ustry-1" in v.casefold() for v in matched["values"])


@pytest.mark.parametrize(("table", "column", "code"), [
    (PRICE, "ticker", "DIMENSION_VALUES_STATIC_ONLY"),
    (UNIVERSE, "Ticker", "DIMENSION_IS_ENTITY"),
    ("Unapproved_Market_Table", "ticker", "TABLE_NOT_APPROVED"),
    ("Inactive_Table", "ticker", "TABLE_NOT_APPROVED"),
    (UNIVERSE, "made_up", "UNKNOWN_COLUMN"),
])
def test_dimension_values_refuse_non_dimensions(governed_db, table, column, code) -> None:
    result = governor(governed_db, storage=False).dimension_values("r", table, column, None)
    assert result["status"] == "REJECTED" and result["reason_code"] == code


def test_dimension_values_endpoint_takes_only_the_orchestrator_key(governed_db, tmp_path) -> None:
    settings = Settings.from_env(base_env(GOVERNOR_DATABASE_URL=governed_db["login"], SQL_DATASET_LOCAL_DIR=str(tmp_path),
                                          SQL_GOVERNOR_DATASET_ACCESS_KEY=ACCESS_KEY))
    client = TestClient(create_app(settings))
    body = {"request_id": "r1", "table": UNIVERSE, "column": "Sector", "match": None}
    assert client.post("/v1/catalog/dimension-values", json=body,
                       headers={"Authorization": f"Bearer {ACCESS_KEY}"}).status_code == 401
    ok = client.post("/v1/catalog/dimension-values", json=body, headers={"Authorization": f"Bearer {API_KEY}"})
    assert ok.status_code == 200 and ok.json()["status"] == "VALUES_READY"
    bad = client.post("/v1/catalog/dimension-values", json={**body, "match": "x" * 61},
                      headers={"Authorization": f"Bearer {API_KEY}"})
    assert bad.status_code == 422


# ---------------------------------------------------------------- P14: value domains of filterable text columns

def test_check_constraint_value_lists_are_read_from_the_database_definitions() -> None:
    from app.catalog_contract import check_value_lists

    # the three forms pg_get_constraintdef prints (PostgreSQL 16), and two shapes that are not value lists
    definitions = [
        ("a", "CHECK (((\"Market Board\")::text = ANY (ARRAY[('Regular'::character varying)::text, "
              "('Nego'::character varying)::text, ('Tunai'::character varying)::text])))"),
        ("a", "CHECK ((market_board = ANY (ARRAY['Regular'::text, 'Nego'::text, 'O''Brien'::text])))"),
        ("a", "CHECK (((\"Investor Type\")::text = ANY ((ARRAY['Foreign'::character varying, "
              "'Domestic'::character varying])::text[])))"),
        ("a", "CHECK (((x >= (0)::numeric) AND (y >= (0)::numeric)))"),
        ("a", "CHECK ((btrim(ticker) <> ''::text))"),
    ]
    assert check_value_lists(definitions) == {"a": {"Market Board": ["Nego", "Regular", "Tunai"],
                                                    "market_board": ["Nego", "O'Brien", "Regular"],
                                                    "Investor Type": ["Domestic", "Foreign"]}}


def test_the_contract_carries_value_domains_outside_the_catalog_hash(governed_db) -> None:
    got = contract(governed_db, [UNIVERSE, PRICE])
    industry = got["value_domains"][UNIVERSE]["Industry"]
    assert "Ticker" not in got["value_domains"][UNIVERSE]  # entity codes are rows, never in the contract
    assert industry["source"] == "STATIC_TABLE" and industry["complete"] and "Industry-1" in industry["values"]
    assert PRICE not in got["value_domains"] or all(  # a dated table's text columns are not scanned
        d["source"] == "CHECK_CONSTRAINT" for d in got["value_domains"][PRICE].values())
    assert got["catalog_sha256"] == sha256_json({k: got[k] for k in ("tables", "columns", "relationships")})


def test_a_static_column_above_the_bound_is_marked_incomplete(monkeypatch) -> None:
    from app import catalog_contract as cc

    monkeypatch.setattr(cc, "VALUE_DOMAIN_MAX", 2)

    def run(statement, params):
        if "pg_constraint" in statement:
            return []
        return [{"value": v} for v in ("A", "B", "C")]

    tables = {"Ref": {"time_column": None, "entity_column": "Ticker"}, "Daily": {"time_column": "date"}}
    columns = {"Ref": {"code": {"data_type": "text", "filter_allowed": True, "group_by_allowed": True},
                       "Ticker": {"data_type": "text", "filter_allowed": True, "group_by_allowed": True},
                       "n": {"data_type": "numeric", "filter_allowed": True}},
               "Daily": {"board": {"data_type": "text", "filter_allowed": True}}}
    domains = cc.value_domains(run, tables, columns)
    assert domains == {"Ref": {"code": {"values": [], "source": "STATIC_TABLE", "complete": False}}}


# ---------------------------------------------------------------- P34: reference tables (database before the web)

def test_reference_columns_are_static_readable_and_ai_allowed(governed_db) -> None:
    result = governor(governed_db, storage=False).reference_columns("r")
    tables = {t["table"]: t for t in result["tables"]}
    assert result["status"] == "OK" and UNIVERSE in tables and "IDX_Broker_Profile" in tables
    assert PRICE not in tables                     # dated: needs a data need
    assert "Catalog_Only_Table" not in tables      # in the catalog, but this role has no grant
    assert "Inactive_Table" not in tables
    universe = tables[UNIVERSE]
    assert universe["entity_column"] == "Ticker" and "Sector" in {c["column"] for c in universe["columns"]}
    assert set(universe["columns"][0]) == {"column", "description", "semantic_type", "filter_allowed"}  # never rows


def test_reference_rows_read_forward_and_reverse(governed_db) -> None:
    gov = governor(governed_db, storage=False)
    one = gov.reference_rows("r", UNIVERSE, ["Sector", "Industry"],
                             [{"column": "Ticker", "operator": "EQ", "value": "BBCA"}], None)
    assert one["status"] == "ROWS_READY" and one["columns"] == ["Ticker", "Sector", "Industry"]
    assert [r["Ticker"] for r in one["rows"]] == ["BBCA"] and one["matched"] == 1
    sector = one["rows"][0]["Sector"]
    members = gov.reference_rows("r", UNIVERSE, ["Sector"], [{"column": "Sector", "operator": "EQ", "value": sector}],
                                 None)
    assert "BBCA" in {r["Ticker"] for r in members["rows"]} and {r["Sector"] for r in members["rows"]} == {sector}
    several = gov.reference_rows("r", UNIVERSE, ["Sector"],
                                 [{"column": "Ticker", "operator": "IN", "value": ["BBCA", "BBRI"]}], None)
    assert [r["Ticker"] for r in several["rows"]] == ["BBCA", "BBRI"]
    matched = gov.reference_rows("r", UNIVERSE, ["Sector"], [], {"column": "Industry", "text": "ustry-1"})
    assert matched["columns"] == ["Ticker", "Sector", "Industry"]  # the matched column is returned
    assert matched["rows"] and all("ustry-1" in r["Industry"].casefold() for r in matched["rows"])
    assert matched["matched"] == len(matched["rows"]) < 30


def test_reference_rows_cap_the_scan_and_the_return(governed_db, monkeypatch) -> None:
    import app.governor as G

    gov = governor(governed_db, storage=False)
    monkeypatch.setattr(G, "REFERENCE_ROWS_RETURN_LIMIT", 3)
    capped = gov.reference_rows("r", UNIVERSE, ["Sector"], [], None)
    assert len(capped["rows"]) == 3 and capped["matched"] == 30 and capped["truncated"] is True
    monkeypatch.setattr(G, "REFERENCE_ROWS_SCAN_LIMIT", 5)
    wide = gov.reference_rows("r", UNIVERSE, ["Sector"], [], None)
    assert wide["status"] == "NEEDS_NARROWING" and wide["reason_code"] == "TOO_MANY_ROWS"


@pytest.mark.parametrize(("table", "columns", "where", "code"), [
    (PRICE, ["close"], [], "REFERENCE_STATIC_ONLY"),
    ("Unapproved_Market_Table", ["ticker"], [], "TABLE_NOT_APPROVED"),
    ("Inactive_Table", ["ticker"], [], "TABLE_NOT_APPROVED"),
    (UNIVERSE, ["made_up"], [], "UNKNOWN_COLUMN"),
    (UNIVERSE, ["Sector"], [{"column": "made_up", "operator": "EQ", "value": "x"}], "UNKNOWN_COLUMN"),
])
def test_reference_rows_refuse_what_is_not_a_static_approved_column(governed_db, table, columns, where, code) -> None:
    result = governor(governed_db, storage=False).reference_rows("r", table, columns, where, None)
    assert result["status"] == "REJECTED" and result["reason_code"] == code


def test_reference_endpoints_take_only_the_orchestrator_key(governed_db, tmp_path) -> None:
    settings = Settings.from_env(base_env(GOVERNOR_DATABASE_URL=governed_db["login"], SQL_DATASET_LOCAL_DIR=str(tmp_path),
                                          SQL_GOVERNOR_DATASET_ACCESS_KEY=ACCESS_KEY))
    client = TestClient(create_app(settings))
    good, wrong = {"Authorization": f"Bearer {API_KEY}"}, {"Authorization": f"Bearer {ACCESS_KEY}"}
    assert client.post("/v1/catalog/reference-columns", json={"request_id": "r1"}, headers=wrong).status_code == 401
    listed = client.post("/v1/catalog/reference-columns", json={"request_id": "r1"}, headers=good)
    assert listed.json()["status"] == "OK"
    body = {"request_id": "r1", "table": UNIVERSE, "columns": ["Sector"],
            "where": [{"column": "Ticker", "operator": "EQ", "value": "BBCA"}], "match": None}
    assert client.post("/v1/catalog/reference-rows", json=body, headers=wrong).status_code == 401
    ok = client.post("/v1/catalog/reference-rows", json=body, headers=good)
    assert ok.status_code == 200 and ok.json()["status"] == "ROWS_READY"
    for bad in ({**body, "columns": []}, {**body, "match": {"column": "Sector", "text": "x"}},
                {**body, "where": [{"column": "Ticker", "operator": "LIKE", "value": "B%"}]}, {**body, "extra": 1}):
        assert client.post("/v1/catalog/reference-rows", json=bad, headers=good).status_code == 422
