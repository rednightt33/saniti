"""Governed data bundles: verified storage, the Data Quality Profiler (confined, validator user) and delivery
coverage (lineage, executed scope, partition tiling, entities against the SQL manifests)."""
from __future__ import annotations

import os
import stat
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.coverage import part_key, tiling
from app.main import create_app
from conftest import API_KEY, SOURCE_CONTRACTS, requires_root
from dataneed_fixtures import classification, data_need_catalog, prices, ytd_spec

HEADERS = {"Authorization": f"Bearer {API_KEY}"}
REFERENCE = "2026-09-25T03:00:00+00:00"
PLAN = "plan_" + "d" * 24
TICKERS = {"BBCA": "Banks", "BBRI": "Banks", "BMRI": "Banks"}


@pytest.fixture
def env(make_service, governor):
    governor.catalog = data_need_catalog()
    service = make_service(start=False, PY_SANDBOX_DATANEED_ENABLED="true")
    client = TestClient(create_app(service.settings, service=service, run_workers=False))
    return {"api": client, "governor": governor, "dataneed": client.app.state.dataneed, "service": service}


def approve(env, spec=None, request_id="req_bundle_1") -> dict[str, Any]:
    body = {"request_id": request_id, "reference_time": REFERENCE, "timezone": "Asia/Jakarta",
            "spec": spec or ytd_spec()}
    result = env["api"].post("/v1/data-needs", json=body, headers=HEADERS).json()
    assert result["status"] == "APPROVED", result
    return env["dataneed"].get_need(result["need_id"])


def price_rows(tickers, start: str, end: str, skip: dict[str, set[str]] | None = None) -> pd.DataFrame:
    days = [d.date() for d in pd.bdate_range(start, end)]
    rows = []
    for index, ticker in enumerate(tickers):
        for day in days:
            if skip and day.isoformat() in skip.get(ticker, set()):
                continue
            close = 1000.0 + index * 10 + day.toordinal() % 17
            rows.append({"ticker": ticker, "date": day, "open": close - 1, "high": close + 2, "low": close - 3,
                         "close": close, "volume": 1000.0 + index})
    return pd.DataFrame(rows)


def universe_rows() -> pd.DataFrame:
    return pd.DataFrame([{"Ticker": t, "Sector": "Financials", "Industry": industry} for t, industry in TICKERS.items()])


def extract_part(env, need, rid: str, frame: pd.DataFrame, partition_id: str, *, window=None, partition=None,
                 executed: dict | None = None, lineage: dict | None = None, entities=None) -> dict[str, Any]:
    """A dataset shaped like a Governor /v1/extract result: lineage and executed scope in its validator manifest."""
    request = need["requests"][rid]
    key = part_key(window, partition)
    executed_scope = {"version": "extract/v1", "data_request_id": rid, "source_table": request["source_table"],
                      "columns": request["extract_columns"], "scope": request["scope"],
                      "scope_sha256": request["scope_sha256"], "restrictions": request["restrictions"],
                      "restriction_sha256": request["restriction_sha256"],
                      "window": {"column": request["time_column"], **window} if window else None,
                      "entity_partition": partition, "part_key": key, "order_by": [], "sampling": False,
                      "truncation": False, **(executed or {})}
    lineage_record = {"need_id": need["need_id"], "spec_sha256": need["spec_sha256"],
                      "request_group_id": need["request_group_id"], "revision": need["revision"],
                      "data_request_id": rid, "logical_name": request["logical_name"],
                      "scope_sha256": request["scope_sha256"], "restriction_sha256": request["restriction_sha256"],
                      "plan_id": PLAN, "part_key": key, "envelope": None, "catalog_sha256": need["catalog_sha256"],
                      "extraction_sha256": "e" * 64, **(lineage or {})}
    table = request["source_table"]
    dataset_id = env["governor"].add(frame[request["extract_columns"]], source_table=table, lineage=lineage_record,
                                     executed_scope=executed_scope,
                                     source_contracts={table: SOURCE_CONTRACTS[table]})
    if entities is not None:
        env["governor"].datasets[dataset_id]["manifest"]["validator_manifest"]["entities_present"] = entities
    return {"partition_id": partition_id, "dataset_id": dataset_id, "part_key": key, "window": window,
            "entity_partition": partition}


def window_of(need, rid, range_id) -> dict[str, str]:
    w = next(w for w in need["requests"][rid]["windows"] if w["range_id"] == range_id)
    return {"from": w["extract_from"], "to": w["extract_to"]}


def ytd_parts(env, need, *, current_frame=None, **overrides) -> list[dict[str, Any]]:
    a, b = "data_request_1_A", "data_request_1_B"
    current, previous = window_of(need, a, "current_ytd"), window_of(need, a, "previous_comparable")
    return [
        {"data_request_id": a, "envelopes": [], "parts": [
            extract_part(env, need, a, current_frame if current_frame is not None else
                         price_rows(TICKERS, current["from"], current["to"]), f"{a}__current_ytd__part_001",
                         window=current, **overrides),
            extract_part(env, need, a, price_rows(TICKERS, previous["from"], previous["to"]),
                         f"{a}__previous_comparable__part_001", window=previous)]},
        {"data_request_id": b, "envelopes": [], "parts": [
            extract_part(env, need, b, universe_rows(), f"{b}__static__part_001")]}]


def build(env, need, requests, request_id="req_bundle_1"):
    body = {"request_id": request_id, "need_id": need["need_id"],
            "plan": {"plan_id": PLAN, "requests": requests,
                     "decisions": [{"data_request_id": "data_request_1_A", "kind": "SEMI_JOIN_PUSHDOWN"}]}}
    return env["api"].post("/v1/bundles", json=body, headers=HEADERS)


pytestmark = requires_root


def test_the_documented_ytd_bundle_is_ready_profiled_and_covered(env) -> None:
    need = approve(env)
    response = build(env, need, ytd_parts(env, need))
    assert response.status_code == 200, response.text
    view = response.json()
    assert view["status"] == "READY" and view["coverage_status"] == "PASS", view
    assert view["next_action"] == "OPEN_ANALYSIS_SESSION"
    prices_view = next(d for d in view["datasets"] if d["logical_name"] == "prices")
    assert prices_view["partitions"] == 2 and prices_view["entities"] == 3
    assert [r["range_id"] for r in prices_view["ranges"]] == ["current_ytd", "previous_comparable"]
    assert {r["status"] for r in prices_view["ranges"]} == {"OK"}
    assert view["relationship_warnings"][0]["code"] == "HISTORICAL_REFERENCE_USES_CURRENT_STATE"
    assert "file" not in str(view) and "/" not in str(prices_view["columns"])
    manifest = env["api"].get(f"/v1/bundles/{view['input_bundle_id']}", headers=HEADERS).json()
    quality = next(d for d in manifest["datasets"] if d["logical_name"] == "prices")["quality"]
    assert quality["duplicate_keys"]["groups"] == 0 and quality["null_by_column"]["close"] == 0
    assert quality["requested_ranges"][0]["history_buffer"]["entities_short"] == 0
    assert manifest["coverage"]["requests"][0]["partitions_expected"] == 2
    # immutable, read-only files on the volume, root only
    folder = Path(env["service"].settings.bundle_dir) / view["input_bundle_id"]
    files = list(folder.rglob("*.parquet"))
    assert len(files) == 3 and all(stat.S_IMODE(f.stat().st_mode) == 0o444 for f in files)
    assert stat.S_IMODE(Path(env["service"].settings.bundle_dir).stat().st_mode) == 0o700
    # the same plan again returns the same bundle
    again = build(env, need, [dict(r, parts=r["parts"]) for r in manifest_plan(manifest)]).json()
    assert again["replayed"] is True and again["input_bundle_id"] == view["input_bundle_id"]


def manifest_plan(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"data_request_id": d["data_request_id"], "envelopes": [], "parts": [
        {k: p[k] for k in ("partition_id", "dataset_id", "window", "entity_partition")} |
        {"part_key": part_key(p["window"], p["entity_partition"])} for p in d["partitions"]]}
        for d in manifest["datasets"]]


@pytest.mark.parametrize("overrides, code", [
    ({"executed": {"scope_sha256": "f" * 64}}, "EXECUTED_SCOPE_MISMATCH"),
    ({"executed": {"truncation": True}}, "TRUNCATION_DETECTED"),
    ({"executed": {"sampling": True}}, "SAMPLING_DETECTED"),
    ({"lineage": {"need_id": "need_" + "0" * 24}}, "LINEAGE_MISMATCH"),
    ({"lineage": {"plan_id": "plan_" + "0" * 24}}, "LINEAGE_MISMATCH"),
    ({"entities": ["BBCA", "BBRI", "BMRI", "TLKM"]}, "ENTITY_MISSING_DOWNSTREAM"),
])
def test_a_delivery_that_differs_from_the_approved_need_is_rejected(env, overrides, code) -> None:
    need = approve(env)
    view = build(env, need, ytd_parts(env, need, **overrides)).json()
    assert view["status"] == "REJECTED" and view["coverage_status"] == "FAIL"
    assert code in {i["code"] for i in view["coverage_issues"]}
    assert view["next_action"] == "REPORT_LIMITATION"
    assert not (Path(env["service"].settings.bundle_dir) / view["input_bundle_id"]).exists()


def test_a_missing_range_part_fails_coverage_for_that_range_only(env) -> None:
    need = approve(env)
    requests = ytd_parts(env, need)
    requests[0]["parts"] = requests[0]["parts"][:1]  # previous_comparable never extracted
    manifest_view = build(env, need, requests).json()
    assert manifest_view["status"] == "REJECTED"
    full = env["dataneed"].get_bundle(manifest_view["input_bundle_id"])
    ranges = {r["range_id"]: r["status"] for r in full["coverage"]["requests"][0]["ranges"]}
    assert ranges == {"current_ytd": "PASS", "previous_comparable": "FAIL"}


def test_a_catalog_change_since_approval_asks_for_a_revision(env) -> None:
    need = approve(env)
    table = "Price_Stock_Indonesia_IDX"
    original = SOURCE_CONTRACTS[table]["catalog_table_sha256"]
    SOURCE_CONTRACTS[table]["catalog_table_sha256"] = "9" * 64
    try:
        view = build(env, need, ytd_parts(env, need)).json()
    finally:
        SOURCE_CONTRACTS[table]["catalog_table_sha256"] = original
    assert "CATALOG_CHANGED_SINCE_APPROVAL" in {i["code"] for i in view["coverage_issues"]}
    assert view["next_action"] == "REVISE_DATA_NEED_SPEC"


def test_quality_findings_are_flags_not_coverage_failures(env) -> None:
    need = approve(env)
    current = window_of(need, "data_request_1_A", "current_ytd")
    frame = price_rows(TICKERS, current["from"], current["to"], skip={"BBRI": {"2026-03-04", "2026-03-05"}})
    frame.loc[frame.index[5], "close"] = None
    frame = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)  # one duplicated key
    late = frame[~((frame["ticker"] == "BMRI") & (frame["date"] < date(2026, 1, 20)))]
    view = build(env, need, ytd_parts(env, need, current_frame=late)).json()
    assert view["status"] == "READY" and view["coverage_status"] == "PASS", view
    flags = set(next(d for d in view["datasets"] if d["logical_name"] == "prices")["quality_flags"])
    assert {"DUPLICATE_KEYS", "NULL_VALUES", "FREQUENCY_GAPS", "HISTORY_BUFFER_SHORTFALL"} <= flags
    full = env["dataneed"].get_bundle(view["input_bundle_id"])
    quality = next(d for d in full["datasets"] if d["logical_name"] == "prices")["quality"]
    gaps = quality["requested_ranges"][0]["frequency_gaps"]
    assert gaps["entities_with_gaps"] == 1 and gaps["examples"][0] == {"entity": "BBRI", "missing": 2}
    assert quality["duplicate_keys"] == {"key_columns": ["ticker", "date"], "groups": 1, "excess_rows": 1,
                                         "examples": [quality["duplicate_keys"]["examples"][0]]}
    short = quality["requested_ranges"][0]["history_buffer"]
    assert short["entities_short"] == 1 and short["examples"][0]["entity"] == "BMRI"


def test_an_explicit_entity_without_data_is_an_empty_entity_flag(env) -> None:
    scope = {"type": "PREDICATE", "column": "ticker", "operator": "IN", "value": ["BBCA", "ZZZZ"]}
    need = approve(env, ytd_spec(data_requests=[prices(scope=scope)], relationships=[]))
    rid = "data_request_1_A"
    parts = [extract_part(env, need, rid, price_rows(["BBCA"], window_of(need, rid, r)["from"],
                                                     window_of(need, rid, r)["to"]),
                          f"{rid}__{r}__part_001", window=window_of(need, rid, r))
             for r in ("current_ytd", "previous_comparable")]
    view = build(env, need, [{"data_request_id": rid, "envelopes": [], "parts": parts}]).json()
    assert view["status"] == "READY"
    assert "EMPTY_ENTITY" in view["datasets"][0]["quality_flags"]
    full = env["dataneed"].get_bundle(view["input_bundle_id"])
    assert full["datasets"][0]["quality"]["empty_entities"] == ["ZZZZ"]


def test_entity_partitions_must_tile_every_date(env) -> None:
    need = approve(env)
    rid = "data_request_1_A"
    current, previous = window_of(need, rid, "current_ytd"), window_of(need, rid, "previous_comparable")
    halves = [extract_part(env, need, rid, price_rows(tickers, current["from"], current["to"]),
                           f"{rid}__current_ytd__part_00{k + 1}", window=current,
                           partition={"modulus": 2, "remainder": k})
              for k, tickers in enumerate((["BBCA"], ["BBRI", "BMRI"]))]
    prev = extract_part(env, need, rid, price_rows(TICKERS, previous["from"], previous["to"]),
                        f"{rid}__previous_comparable__part_001", window=previous)
    static = ytd_parts(env, need)[1]
    ready = build(env, need, [{"data_request_id": rid, "envelopes": [], "parts": halves + [prev]}, static]).json()
    assert ready["status"] == "READY", ready
    broken = build(env, need, [{"data_request_id": rid, "envelopes": [], "parts": halves[:1] + [prev]}, static])
    assert "MISSING_PARTITION" in {i["code"] for i in broken.json()["coverage_issues"]}


def test_an_oversized_bundle_is_refused_before_any_download(env, make_service) -> None:
    need = approve(env)
    env["service"].settings.__dict__["bundle_max_rows"] = 10  # frozen dataclass: tests only
    response = build(env, need, ytd_parts(env, need))
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "BUNDLE_TOO_LARGE" and body["next_action"] == "REVISE_DATA_NEED_SPEC"
    assert not any(Path(env["service"].settings.bundle_dir).iterdir())


def test_a_bundle_belongs_to_the_request_and_need_it_was_approved_for(env) -> None:
    need = approve(env)
    response = build(env, need, ytd_parts(env, need), request_id="req_other")
    assert response.status_code == 404 and response.json()["error"]["code"] == "NEED_NOT_FOUND"
    assert env["api"].get("/v1/bundles/bundle_" + "0" * 24, headers=HEADERS).status_code == 404


def test_the_plan_is_structurally_checked(env) -> None:
    need = approve(env)
    requests = ytd_parts(env, need)
    requests[0]["parts"][1]["partition_id"] = "other_request__part_001"
    response = build(env, need, requests)
    assert response.status_code == 422 and response.json()["error"]["code"] == "INVALID_PLAN"


# ---------------------------------------------------------------- tiling (pure)

def part(window, partition=None):
    return {"window": {"from": window[0], "to": window[1]} if window else None, "entity_partition": partition}


@pytest.mark.parametrize("parts, required, codes", [
    ([part(("2026-01-01", "2026-01-31"))], [(date(2026, 1, 1), date(2026, 1, 31))], set()),
    ([part(("2026-01-01", "2026-01-15")), part(("2026-01-16", "2026-01-31"))],
     [(date(2026, 1, 1), date(2026, 1, 31))], set()),
    ([part(("2026-01-01", "2026-01-15")), part(("2026-01-17", "2026-01-31"))],
     [(date(2026, 1, 1), date(2026, 1, 31))], {"MISSING_PARTITION"}),
    ([part(("2026-01-01", "2026-01-20")), part(("2026-01-16", "2026-01-31"))],
     [(date(2026, 1, 1), date(2026, 1, 31))], {"OVERLAPPING_PARTITIONS"}),
    ([part(("2026-01-01", "2026-01-31"), {"modulus": 2, "remainder": 0}),
      part(("2026-01-01", "2026-01-15"), {"modulus": 4, "remainder": 1}),
      part(("2026-01-01", "2026-01-15"), {"modulus": 4, "remainder": 3}),
      part(("2026-01-16", "2026-01-31"), {"modulus": 2, "remainder": 1})],
     [(date(2026, 1, 1), date(2026, 1, 31))], set()),
    ([part(None, {"modulus": 3, "remainder": 0}), part(None, {"modulus": 3, "remainder": 1})], None,
     {"MISSING_PARTITION"}),
])
def test_partition_tiling(parts, required, codes) -> None:
    assert {i["code"] for i in tiling(parts, required)} == codes
