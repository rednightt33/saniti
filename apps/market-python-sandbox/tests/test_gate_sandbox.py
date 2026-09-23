"""Addendum acceptance tests A–H through the real service: isolated analysis and validator processes,
immutable specs, logical datasets, locked DuckDB, request budgets, and workspace cleanup."""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models import AnalysisRequest
from app.service import ServiceUnavailable
from app.spec import SpecRequest
from conftest import API_KEY, price_frame, requires_root, zscore_spec

pytestmark = requires_root
HEADERS = {"Authorization": f"Bearer {API_KEY}"}
REFERENCE = datetime(2026, 9, 23, 3, 0, tzinfo=timezone.utc)
THREE_MONTHS = "Calculate rolling 20-day z-scores for all IDX stocks over the last three months."
FULL = price_frame({f"T{i:02d}": ("2026-04-01", 125) for i in range(12)})
Z = '''
import pandas as pd, saniti
df = saniti.load("prices", columns=["ticker", "date", "close"])
df["date"] = pd.to_datetime(df["date"])
g = df.groupby("ticker")["close"]
df["zscore_20"] = (df["close"] - g.transform(lambda s: s.rolling(WINDOW).mean())) / g.transform(
    lambda s: s.rolling(WINDOW).std())
out = df[(df["date"] >= pd.Timestamp(START)) & (df["date"] <= pd.Timestamp(ANALYSIS_END))]
'''
EMIT = 'saniti.emit_table("zscores", out[["ticker", "date", "zscore_20"]])\n'


def spec_id(service, spec: dict | None = None, message: str = THREE_MONTHS, request_id: str = "req") -> str:
    review = service.create_spec(SpecRequest(request_id=request_id, reference_time=REFERENCE,
                                             user_messages=[{"role": "user", "content": message}],
                                             spec=spec or zscore_spec()))
    assert review.get("spec_id"), review
    return review["spec_id"]


def run(service, spec: str, ds, code: str, outputs=("TABLE",), request_id: str = "req", policy="ERROR_ON_CONFLICT"):
    ids = ds if isinstance(ds, list) else [ds]
    return service.submit(AnalysisRequest(request_id=request_id, spec_id=spec, python_code=code,
                                          inputs=[{"name": "prices", "dataset_ids": ids, "duplicate_policy": policy}],
                                          expected_outputs=list(outputs)))


def zcode(window: int = 20, start: str = "ANALYSIS_START", extra: str = "") -> str:
    return f"WINDOW = {window}\nSTART = {start}\n" + Z + extra + EMIT


def full_dataset(governor, frame=FULL, **kwargs) -> str:
    return governor.add(frame, requested_from="2026-04-01", requested_to="2026-09-23", **kwargs)


def reasons(result) -> list[str]:
    return result["reason_codes"]


def test_correct_analysis_passes_with_calculation_verified_and_records_everything(make_service, governor) -> None:
    service = make_service()
    result = run(service, spec_id(service), full_dataset(governor), zcode())
    assert (result["execution_status"], result["validation_status"], result["validation_level"]) == (
        "COMPLETED", "PASS", "CALCULATION_VERIFIED"), result["validation_evidence"]
    assert result["next_action"] == "USE_ANALYSIS_RESULT" and result["reason_codes"] == []
    assert result["expected_scope"]["analysis_start"] == "2026-06-24" and result["expected_scope"][
        "expected_entities"] == 12
    output = result["actual_scope"]["outputs"][0]
    assert output["values_checked"] == 12 * 65 and output["date_range"] == ["2026-06-24", "2026-09-22"]
    feature = result["derived_features"][0]
    assert (feature["name"], feature["origin"], feature["independent_check_result"], feature["statistical_validation"]
            ) == ("zscore_20", "DERIVED_IN_ANALYSIS", "RECALCULATED_MATCH", "NOT_PERFORMED")
    api = TestClient(create_app(service.settings, service=service, run_workers=False))
    definitions = api.get(f"/v1/artifacts/{result['derived_feature_definitions']['artifact_id']}", headers=HEADERS)
    assert definitions.json()["features"][0]["definition_sha256"] == feature["definition_sha256"]
    assert service.records.derived_features_for(result["analysis_id"])[0]["name"] == "zscore_20"
    assert result["lineage"]["spec_sha256"] == result["spec_sha256"] and result["lineage"]["reproducible_until"]


def test_A_three_months_requested_two_calculated(make_service, governor) -> None:
    service = make_service()
    result = run(service, spec_id(service), full_dataset(governor), zcode(start="'2026-07-24'"))
    assert (result["execution_status"], result["validation_status"]) == ("COMPLETED", "FAILED")
    assert "ANALYSIS_SCOPE_MISMATCH" in reasons(result) and result["next_action"] == "REVISE_ANALYSIS"
    coverage = next(e for e in result["validation_evidence"] if e["check"] == "output.zscores.coverage")
    assert coverage["expected_range"] == ["2026-06-24", "2026-09-23"] and coverage["actual_range"][0] == "2026-07-24"


def test_A_spec_that_shrinks_the_period_is_refused_before_any_data_is_used(make_service) -> None:
    service = make_service()
    two = zscore_spec(period={"mode": "TRAILING", "unit": "MONTH", "count": 2, "provenance": "USER_EXPLICIT"})
    review = service.create_spec(SpecRequest(request_id="req", reference_time=REFERENCE, spec=two,
                                             user_messages=[{"role": "user", "content": THREE_MONTHS}]))
    assert review["status"] == "ANALYSIS_SPEC_MISMATCH" and "spec_id" not in review
    assert service.records.count_specs("req") == 0


def test_B_insufficient_warmup_is_stopped_before_execution(make_service, governor) -> None:
    late = price_frame({f"T{i:02d}": ("2026-06-24", 65) for i in range(4)})
    service = make_service()
    result = run(service, spec_id(service), governor.add(late, requested_from="2026-06-24"), zcode())
    assert (result["execution_status"], result["validation_status"]) == ("FAILED", "INCOMPLETE")
    assert reasons(result) == ["INSUFFICIENT_WARMUP_HISTORY"] and result["next_action"] == "REVISE_DATA_REQUEST"
    assert "2026-05-15" in result["error"]["message"] and result["resource_usage"].get("cpu_seconds") is None


def test_C_universe_subset(make_service, governor) -> None:
    service = make_service()
    code = zcode(extra='out = out[out["ticker"].isin(["T00", "T01", "T02"])]\n')
    result = run(service, spec_id(service), full_dataset(governor), code)
    assert result["validation_status"] == "FAILED" and "UNIVERSE_MISMATCH" in reasons(result)
    universe = next(e for e in result["validation_evidence"] if e["check"] == "output.zscores.universe")
    assert universe["missing_entities"] == 9 and universe["classification"] == "LOST_IN_TRANSFORMATION"


def test_D_wrong_window_is_detected_by_the_independent_reference(make_service, governor) -> None:
    service = make_service()
    result = run(service, spec_id(service), full_dataset(governor), zcode(window=10))
    assert result["validation_status"] == "FAILED" and reasons(result) == ["CALCULATION_MISMATCH"]
    check = next(e for e in result["validation_evidence"] if e.get("code") == "CALCULATION_MISMATCH")
    assert check["diagnosis"]["parameter"] == "window" and check["diagnosis"]["values_match"] == 10
    assert result["derived_features"][0]["independent_check_result"] == "RECALCULATED_MISMATCH"


def test_E_large_multi_file_workspace_is_scanned_by_duckdb(make_service, governor, capsys) -> None:
    """Four Parquet snapshots (~1.7M rows) form one logical input; DuckDB scans, spills, and aggregates them."""
    tickers = [f"X{i:03d}" for i in range(844)]
    dates = pd.bdate_range("2018-12-03", periods=2000)
    rng = np.random.default_rng(5)
    close = 1000 + np.cumsum(rng.normal(0, 10, (len(tickers), len(dates))), axis=1)
    frame = pd.DataFrame({"ticker": np.repeat(tickers, len(dates)), "date": np.tile(dates.date, len(tickers)),
                          "close": close.ravel()})
    edges = [dates[0], dates[500], dates[1000], dates[1500], dates[-1] + timedelta(days=1)]
    ids = []
    for low, high in zip(edges, edges[1:]):
        part = frame[(frame.date >= low.date()) & (frame.date < high.date())]
        ids.append(governor.add(part, requested_from=str(low.date()), requested_to=str((high - timedelta(days=1)).date())))
    spec = zscore_spec(period={"mode": "LATEST", "provenance": "USER_EXPLICIT"}, output_grain="ENTITY",
                       question="Latest 20-day rolling z-score for all IDX stocks.")
    service = make_service(PY_SANDBOX_DUCKDB_MEMORY_MB="256", PY_SANDBOX_MAX_RUNTIME_SECONDS="120")
    code = '''
import saniti
con = saniti.duckdb_connection()
rows = con.sql("SELECT count(*) FROM prices").fetchone()[0]
con.execute(f"COPY (SELECT * FROM prices ORDER BY close) TO '{saniti.intermediate_path('sorted')}' (FORMAT PARQUET)")
latest = saniti.sql("""
  WITH z AS (
    SELECT ticker, date, (close - avg(close) OVER w) / stddev_samp(close) OVER w AS zscore_20,
           count(*) OVER w AS n, row_number() OVER (PARTITION BY ticker ORDER BY date DESC) AS rn
    FROM prices WHERE date <= CAST(? AS DATE)
    WINDOW w AS (PARTITION BY ticker ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW))
  SELECT ticker, date, zscore_20 FROM z WHERE rn = 1 AND n = 20 ORDER BY ticker""", [ANALYSIS_END])
saniti.emit_table("zscores", latest)
saniti.emit_metrics({"rows_scanned": int(rows)})
'''
    started = time.monotonic()
    result = run(service, spec_id(service, spec, "Latest 20-day rolling z-score for all IDX stocks"), ids, code,
                 outputs=("TABLE", "METRICS"))
    elapsed = time.monotonic() - started
    assert result["execution_status"] == "COMPLETED", result["error"]
    assert (result["validation_status"], result["validation_level"]) == ("PASS", "CALCULATION_VERIFIED"), \
        result["validation_evidence"]
    usage = result["resource_usage"]
    inputs = result["actual_scope"]["inputs"][0]
    assert inputs["files"] == 4 and inputs["rows_used"] == len(frame) == 1_688_000
    assert result["outputs"][0]["row_count"] == 844 and result["outputs"][1]["values"]["rows_scanned"] == len(frame)
    assert usage["max_rss_mb"] < 1024 and usage["peak_intermediate_bytes"] > 0
    with capsys.disabled():
        print("\nTEST_E_MEASUREMENTS " + json.dumps({
            "input_files": 4, "input_rows": len(frame), "input_bytes": usage["input_bytes"],
            "analysis_peak_rss_mb": usage["max_rss_mb"], "analysis_cpu_seconds": usage["cpu_seconds"],
            "peak_intermediate_bytes": usage["peak_intermediate_bytes"], "duckdb_memory_limit_mb": 256,
            "validator_peak_rss_mb": usage.get("validator_max_rss_mb"),
            "validator_cpu_seconds": usage["validator_cpu_seconds"], "wall_seconds": round(elapsed, 1),
            "values_checked": result["actual_scope"]["outputs"][0]["values_checked"]}))


def test_F_logical_dataset_from_overlapping_snapshots(make_service, governor) -> None:
    first = governor.add(FULL[FULL.date < date(2026, 8, 1)], requested_from="2026-04-01", requested_to="2026-07-31")
    second = governor.add(FULL[FULL.date >= date(2026, 7, 1)], requested_from="2026-07-01", requested_to="2026-09-23")
    service = make_service()
    code = zcode(extra='saniti.emit_metrics({"rows_seen": len(df), "tickers": int(df.ticker.nunique())})\n')
    result = run(service, spec_id(service), [first, second], code, outputs=("TABLE", "METRICS"))
    assert result["validation_status"] == "PASS", result["validation_evidence"]
    assert result["inputs"] == {"prices": [first, second]}
    lineage = result["actual_scope"]["inputs"][0]
    assert (lineage["files"], lineage["identical_duplicates_removed"], lineage["rows_used"]) == (2, 12 * 23, len(FULL))
    metrics = next(o for o in result["outputs"] if o["type"] == "METRICS")
    assert metrics["values"] == {"rows_seen": len(FULL), "tickers": 12}   # the view already removed the overlap


def test_F_incompatible_sources_are_not_merged(make_service, governor) -> None:
    first = governor.add(FULL[FULL.date < date(2026, 8, 1)], requested_from="2026-04-01")
    second = governor.add(FULL[FULL.date >= date(2026, 8, 1)], requested_from="2026-08-01",
                          aggregation={"close": "AVG"})
    service = make_service()
    result = run(service, spec_id(service), [first, second], zcode())
    assert (result["execution_status"], result["validation_status"]) == ("FAILED", "FAILED")
    assert reasons(result) == ["INCOMPATIBLE_LOGICAL_DATASET"] and result["error"]["code"] == "INPUT_VALIDATION_FAILED"


def test_G_workspace_cleanup_and_retention(make_service, governor) -> None:
    service = make_service()
    jobs = service.settings.jobs_dir
    ds = full_dataset(governor)
    spec = spec_id(service)
    good = run(service, spec, ds, zcode())
    assert good["validation_status"] == "PASS"
    assert not (service.outputs.root.parent / "x").exists()
    from pathlib import Path
    root = Path(jobs)
    assert not (root / good["analysis_id"]).exists()                      # completed: released at once
    failed = run(service, spec, ds, "raise ValueError('boom')")
    kept = root / failed["analysis_id"]
    assert failed["execution_status"] == "FAILED" and (kept / ".retain_until").exists()
    assert not (kept / "input").exists() and (kept / "analysis.py").exists()   # inputs never retained
    orphan, active = root / ("ana_" + "0" * 24), root / ("ana_" + "1" * 24)
    for path in (orphan, active):
        path.mkdir()
        (path / "leftover.bin").write_bytes(b"x" * 1024)
    service.active.add(active.name)
    now = datetime.now(timezone.utc)
    summary = service.cleanup(now + timedelta(hours=1))
    assert not orphan.exists() and active.exists() and kept.exists() and summary["workspaces_removed"] == 1
    summary = service.cleanup(now + timedelta(hours=7))
    assert not kept.exists() and active.exists()                            # bounded diagnostic TTL
    api = TestClient(create_app(service.settings, service=service, run_workers=False))
    page = api.get(f"/v1/results/{good['outputs'][0]['result_id']}", headers=HEADERS)
    assert page.status_code == 200 and page.json()["row_count"] == 12 * 65  # results outlive the workspace
    cached = list(Path(service.settings.cache_dir).glob("ds_*.parquet"))
    assert cached and service.records.cache_entries()
    later = service.cleanup(now + timedelta(days=8))                         # after the snapshot's own expiry
    assert later["cache_files_removed"] == len(cached) and not service.records.cache_entries()
    assert governor.datasets[ds]["path"].exists()                           # Governor snapshots are untouched
    service.active.discard(active.name)


def test_H_self_reported_claims_do_not_count_as_evidence(make_service, governor) -> None:
    service = make_service()
    code = zcode(extra='out = out[out["ticker"] == "T00"]\nsaniti.emit_metrics({"entities_analyzed": 844, '
                       '"date_range": ["2026-06-24", "2026-09-23"], "complete": True})\n')
    result = run(service, spec_id(service), full_dataset(governor), code, outputs=("TABLE", "METRICS"))
    assert result["validation_status"] == "FAILED" and "UNIVERSE_MISMATCH" in reasons(result)
    assert "never used as evidence" in result["self_reported"]["note"]
    load = result["self_reported"]["access_log"][0]
    assert load["call"] == "load" and load["input"] == "prices"


def test_H_unverifiable_outputs_are_unverified_not_pass(make_service, governor) -> None:
    service = make_service()
    spec = zscore_spec(output_grain="UNSPECIFIED")
    code = 'import pandas as pd, saniti\nsaniti.emit_table("zscores", pd.DataFrame({"claimed_entities": [844]}))\n'
    result = run(service, spec_id(service, spec), full_dataset(governor), code)
    assert (result["execution_status"], result["validation_status"], result["validation_level"]) == (
        "COMPLETED", "UNVERIFIED", "EXECUTION_ONLY")
    assert result["next_action"] == "USE_RESULT_WITH_VALIDATION_LIMITATION"


@pytest.mark.parametrize(("code", "error"), [
    ("import duckdb\nduckdb.sql(\"SELECT * FROM read_text('/etc/hostname')\").fetchall()", "FORBIDDEN_OPERATION"),
    ("import duckdb\nduckdb.sql(\"COPY (SELECT 1) TO '/tmp/leak.csv'\")", "FORBIDDEN_OPERATION"),
    ("import duckdb\nduckdb.sql(\"INSTALL httpfs\")", "FORBIDDEN_OPERATION"),
    ("import duckdb\nduckdb.sql(\"SET enable_external_access = true\")", "PYTHON_EXCEPTION"),
    ("import duckdb\nduckdb.connect('/tmp/other.duckdb')", "FORBIDDEN_OPERATION"),
    ("import saniti\nsaniti.sql('SELECT * FROM prices')", "MATERIALIZATION_LIMIT_EXCEEDED"),
    ("open('../validation/outputs/out_001.parquet', 'wb').write(b'forged')", "FORBIDDEN_OPERATION"),
    ("open('../manifest.json', 'w').write('{}')", "FORBIDDEN_OPERATION"),
])
def test_duckdb_and_workspace_boundaries_hold_in_a_real_process(make_service, governor, code: str,
                                                                 error: str) -> None:
    service = make_service(PY_SANDBOX_MAX_MATERIALIZE_ROWS="1000")
    result = run(service, spec_id(service, request_id="boundary"), full_dataset(governor), code,
                 request_id="boundary")
    assert result["execution_status"] == "FAILED" and result["error"]["code"] == error, result["error"]


def test_spec_api_is_immutable_and_scoped_to_its_request(make_service, governor) -> None:
    service = make_service()
    api = TestClient(create_app(service.settings, service=service, run_workers=False))
    body = {"request_id": "api-1", "reference_time": REFERENCE.isoformat(), "timezone": "Asia/Jakarta",
            "user_messages": [{"role": "user", "content": "Tolong: " + THREE_MONTHS}], "spec": zscore_spec()}
    created = api.post("/v1/specs", json=body, headers=HEADERS).json()
    assert created["status"] == "APPROVED" and created["resolved_period"]["start"] == "2026-06-24"
    stored = api.get(f"/v1/specs/{created['spec_id']}", headers=HEADERS).json()
    assert stored["spec_sha256"] == created["spec_sha256"] and stored["user_messages_sha256"]
    assert "Tolong" not in json.dumps(stored) and "user_messages" not in stored   # only its hash is stored
    assert api.post("/v1/specs", json={**body, "spec": {**body["spec"], "sql": "x"}}, headers=HEADERS
                    ).status_code == 422
    with pytest.raises(ServiceUnavailable) as info:
        run(service, created["spec_id"], full_dataset(governor), zcode(), request_id="another-request")
    assert info.value.code == "SPEC_NOT_FOUND"


def test_request_level_budget_cannot_be_bypassed_by_repeated_calls(make_service, governor) -> None:
    service = make_service(PY_SANDBOX_MAX_ANALYSES_PER_REQUEST="2")
    ds, spec = full_dataset(governor), spec_id(service)
    for i in range(2):
        assert run(service, spec, ds, f"x = {i}\n" + zcode())["execution_status"] == "COMPLETED"
    with pytest.raises(ServiceUnavailable) as info:
        run(service, spec, ds, "x = 3\n" + zcode())
    assert (info.value.code, info.value.http_status) == ("REQUEST_BUDGET_EXCEEDED", 429)
    assert run(service, spec, ds, "x = 0\n" + zcode())["execution_status"] == "COMPLETED"   # idempotent replay
