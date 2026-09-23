"""Real executions: isolation, TA-Lib, time-series safety, outputs, limits, lifecycle, and dataset security."""
from __future__ import annotations

import io
import json
import logging
import time
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models import AnalysisRequest
from app.spec import SpecRequest
from conftest import ACCESS_KEY, API_KEY, ohlc_frame, requires_root

pytestmark = requires_root
HEADERS = {"Authorization": f"Bearer {API_KEY}"}
REFERENCE = datetime(2026, 9, 23, 3, 0, tzinfo=timezone.utc)


def generic_spec(columns: list[str]) -> dict:
    """A spec for tests of execution mechanics: its output grain is not checkable, so validation is UNVERIFIED."""
    return {"question": "test", "universe": {"type": "ALL_IN_SOURCE", "provenance": "AI_INFERRED"},
            "analysis_period": {"mode": "LATEST", "provenance": "AI_INFERRED"},
            "frequency": {"value": "1D", "provenance": "APPROVED_DEFAULT", "default_id": "DEFAULT_FREQUENCY_DAILY"},
            "inputs": [{"name": "data", "source_table": "Price_Stock_Indonesia_IDX", "columns": columns}],
            "calculations": [{"id": "calc", "method": "CUSTOM", "dataset": "data", "columns": [columns[0]],
                              "output_column": "value", "formula": "test", "time_alignment": "n/a",
                              "provenance": "AI_INFERRED"}],
            "outputs": [{"name": "result", "grain": "UNSPECIFIED"}]}


def spec_for(service, dataset_ids, request_id: str) -> str:
    cache = service.__dict__.setdefault("test_specs", {})
    if request_id in cache:
        return cache[request_id]
    known = next((service.datasets_governor.datasets[d] for d in dataset_ids
                  if d in service.datasets_governor.datasets), None)
    columns = [c["name"] for c in known["manifest"]["columns"]] if known else ["x"]
    review = service.create_spec(SpecRequest(request_id=request_id, reference_time=REFERENCE,
                                             user_messages=[{"role": "user", "content": "test"}],
                                             spec=generic_spec(columns)))
    assert review.get("spec_id"), review
    cache[request_id] = review["spec_id"]
    return review["spec_id"]


def submit(service, dataset_ids, code, outputs=("TABLE",), request_id="req-1", purpose="test"):
    return service.submit(AnalysisRequest(request_id=request_id, spec_id=spec_for(service, dataset_ids, request_id),
                                          inputs=[{"name": "data", "dataset_ids": list(dataset_ids)}],
                                          python_code=code, expected_outputs=list(outputs)))


# ---------------------------------------------------------------- isolation self-test

def test_isolation_self_test_passes_and_records_versions(make_service) -> None:
    service = make_service()
    assert service.isolation.ok, service.isolation.failure
    assert set(service.isolation.checks.values()) == {"PASS"}
    for check in ("uid_non_root", "seccomp_filter_active", "socket_inet_denied", "socket_inet6_denied", "fork_denied",
                  "execve_denied", "parent_environment_unreadable", "environment_clean", "talib_functions",
                  "duckdb_outside_file_denied", "duckdb_config_locked", "duckdb_extension_install_denied",
                  "duckdb_attach_denied", "duckdb_new_connection_locked", "duckdb_memory_limit",
                  "validator_uid_non_root", "validator_seccomp_filter_active", "validator_socket_inet_denied"):
        assert service.isolation.checks[check] == "PASS"
    versions = service.isolation.versions
    for library in ("python", "numpy", "pandas", "polars", "pyarrow", "duckdb", "scipy", "statsmodels", "matplotlib",
                    "talib", "ta-lib-c"):
        assert versions.get(library), library


def test_failed_isolation_refuses_analyses(make_service, governor) -> None:
    service = make_service(start=False)
    service.start(run_workers=False)
    service.isolation.ok = False
    ds = governor.add(pd.DataFrame({"x": [1]}))
    api = TestClient(create_app(service.settings, service=service, run_workers=False))
    with api:
        service.isolation.ok = False
        assert api.get("/ready").status_code == 503
        response = api.post("/v1/analyses", headers=HEADERS, json={
            "request_id": "r", "spec_id": "spec_" + "0" * 24, "inputs": [{"name": "data", "dataset_ids": [ds]}],
            "python_code": "x=1", "expected_outputs": ["TABLE"]})
    assert response.status_code == 503 and response.json()["error"]["code"] == "SANDBOX_ISOLATION_UNAVAILABLE"


# ---------------------------------------------------------------- acceptance A: TA-Lib screening

TALIB_SCREEN = '''
import numpy as np, pandas as pd, talib
from saniti import load_dataset, iter_series, emit_table, emit_metrics, add_warning
df = load_dataset("data")
rows, nan_rsi = [], 0
for ticker, g in iter_series(df, "Symbol", "Date", min_history=30):
    close = g["Close"].to_numpy(float)
    rsi = talib.RSI(close, timeperiod=14)
    engulfing = talib.CDLENGULFING(g["Open"].to_numpy(float), g["High"].to_numpy(float),
                                   g["Low"].to_numpy(float), close)
    if np.isnan(rsi[-1]):
        nan_rsi += 1
        continue
    rows.append({"ticker": ticker, "date": g["Date"].iloc[-1], "close": close[-1], "rsi14": float(rsi[-1]),
                 "sma5": float(talib.SMA(close, 5)[-1]), "stddev5": float(talib.STDDEV(close, 5)[-1]),
                 "engulfing": int(engulfing[-1])})
table = pd.DataFrame(rows).sort_values("ticker")
matched = table[(table.rsi14 < RSI_MAX) & (table.engulfing > 0)]
emit_table("latest_indicators", table)
emit_table("rsi_below_and_bullish_engulfing", matched)
emit_metrics({"entities_analyzed": len(table), "matched_assets": len(matched), "nan_rsi_excluded": nan_rsi})
'''


def test_acceptance_a_talib_rsi_and_engulfing_keep_tickers_separate(make_service, governor) -> None:
    frame = ohlc_frame({"AAAA": 80, "BBBB": 80, "CCCC": 80, "TINY": 10})
    # Force a bullish engulfing on CCCC's last candle.
    c = frame[frame.Symbol == "CCCC"].sort_values("Date").index
    frame.loc[c[-2], ["Open", "High", "Low", "Close"]] = [1000.0, 1001.0, 979.0, 980.0]
    frame.loc[c[-1], ["Open", "High", "Low", "Close"]] = [978.0, 1012.0, 977.0, 1010.0]
    ds = governor.add(frame, numeric=("Open", "High", "Low", "Close"))
    service = make_service()
    code = f"DS = {ds!r}\nRSI_MAX = 101\n" + TALIB_SCREEN
    result = submit(service, [ds], code, outputs=("TABLE", "METRICS"))
    assert result["execution_status"] == "COMPLETED", result["error"]
    table, matched, metrics = result["outputs"]
    assert metrics["values"] == {"entities_analyzed": 3, "matched_assets": 1, "nan_rsi_excluded": 0}
    assert matched["preview_rows"][0][0] == "CCCC"
    got = {row[0]: row for row in table["preview_rows"]}
    import talib
    for ticker in ("AAAA", "BBBB", "CCCC"):  # reference: each ticker's own sorted history
        g = frame[frame.Symbol == ticker].sort_values("Date")
        close = g["Close"].to_numpy(float)
        assert got[ticker][3] == pytest.approx(talib.RSI(close, 14)[-1], rel=1e-9)
        assert got[ticker][1] == str(g["Date"].iloc[-1])
    whole = talib.RSI(frame.sort_values("Date")["Close"].to_numpy(float), 14)[-1]
    assert all(got[t][3] != pytest.approx(whole) for t in got)   # not one continuous multi-asset series
    codes = [w["code"] for w in result["warnings"]]
    assert "NUMERIC_AS_FLOAT64" in codes and "INSUFFICIENT_HISTORY" in codes
    assert "TINY" in next(w["message"] for w in result["warnings"] if w["code"] == "INSUFFICIENT_HISTORY")
    lineage = result["lineage"]
    assert lineage["datasets"][ds]["checksum_sha256"] == governor.datasets[ds]["manifest"]["checksum_sha256"]
    assert lineage["library_versions"]["talib"] and lineage["code_sha256"] and lineage["seed"] == 0


# ---------------------------------------------------------------- acceptance B: rolling z-score

ZSCORE = '''
import pandas as pd
from saniti import load_dataset, prepare_panel, emit_table, emit_metrics
df = prepare_panel(load_dataset("data"), "Symbol", "Date")
g = df.groupby("Symbol", sort=False)["Close"]
df["rolling_mean_20"] = g.transform(lambda s: s.rolling(20, min_periods=20).mean())
df["rolling_std_20"] = g.transform(lambda s: s.rolling(20, min_periods=20).std())
df["zscore_20"] = (df["Close"] - df["rolling_mean_20"]) / df["rolling_std_20"]
latest = df.groupby("Symbol", sort=False).tail(1)
valid = latest.dropna(subset=["zscore_20"])
hits = valid[valid.zscore_20 > 2].rename(columns={"Symbol": "ticker", "Date": "date", "Close": "close"})
emit_table("above_2_sigma", hits[["ticker", "date", "close", "rolling_mean_20", "rolling_std_20", "zscore_20"]])
emit_metrics({"universe_size": int(latest.Symbol.nunique()), "entities_analyzed": len(valid),
              "matched_assets": len(hits), "median_zscore": float(valid.zscore_20.median())})
'''


def test_acceptance_b_rolling_zscore_table_and_metrics(make_service, governor) -> None:
    frame = ohlc_frame({"UP01": 40, "FLAT": 40, "SHRT": 12})
    last = frame[frame.Symbol == "UP01"].sort_values("Date").index[-1]
    frame.loc[last, "Close"] = frame.loc[frame.Symbol == "UP01", "Close"].max() + 400
    ds = governor.add(frame)
    result = submit(make_service(), [ds], f"DS = {ds!r}\n" + ZSCORE, outputs=("TABLE", "METRICS"))
    assert result["execution_status"] == "COMPLETED", result["error"]
    table, metrics = result["outputs"]
    assert [c["name"] for c in table["columns"]] == ["ticker", "date", "close", "rolling_mean_20", "rolling_std_20",
                                                     "zscore_20"]
    assert table["row_count"] == 1 and table["preview_rows"][0][0] == "UP01" and table["preview_rows"][0][5] > 2
    assert metrics["values"]["universe_size"] == 3 and metrics["values"]["entities_analyzed"] == 2


# ---------------------------------------------------------------- acceptance C: large table

def test_acceptance_c_large_table_is_stored_and_only_previewed(make_service, governor) -> None:
    ds = governor.add(pd.DataFrame({"x": np.arange(3000)}))
    code = f'''
from saniti import load_dataset, emit_table
df = load_dataset('data')
df["y"] = df["x"] * 2
emit_table("all_rows", df)
'''
    service = make_service()
    result = submit(service, [ds], code)
    table = result["outputs"][0]
    assert table["row_count"] == 3000 and table["preview_row_count"] == 50 and table["preview_truncated"] is True
    assert len(table["preview_rows"]) == 50 and table["result_id"].startswith("res_")
    api = TestClient(create_app(service.settings, service=service, run_workers=False))
    rows, offset = [], 0
    while offset is not None:
        page = api.get(f"/v1/results/{table['result_id']}", params={"offset": offset, "limit": 500},
                       headers=HEADERS).json()
        rows += page["rows"]
        offset = page["next_offset"]
    assert len(rows) == 3000 and rows[2999] == [2999, 5998]


def test_previews_shrink_explicitly_to_fit_the_output_budget(make_service, governor) -> None:
    ds = governor.add(pd.DataFrame({"x": [1]}))
    code = '''
import pandas as pd
from saniti import emit_table
for i in range(4):
    emit_table(f"t{i}", pd.DataFrame({f"c{j}": ["v" * 40] * 60 for j in range(10)}))
'''
    result = submit(make_service(PY_SANDBOX_MAX_OUTPUT_BYTES="20000"), [ds], code)
    assert result["execution_status"] == "COMPLETED", result["error"]
    assert len(json.dumps({"outputs": result["outputs"], "warnings": result["warnings"]})) <= 20000
    for table in result["outputs"]:
        assert table["row_count"] == 60 and table["preview_truncated"] and table["preview_row_count"] < 50


# ---------------------------------------------------------------- charts and artifacts

def test_chart_and_artifact_are_stored_and_referenced_by_id(make_service, governor) -> None:
    ds = governor.add(pd.DataFrame({"x": np.arange(100.0)}))
    code = f'''
import matplotlib.pyplot as plt
from saniti import load_dataset, emit_chart, emit_artifact
df = load_dataset('data')
fig, ax = plt.subplots()
ax.plot(df["x"], df["x"] ** 2)
emit_chart(fig, name="curve", title="x squared", description="test chart")
emit_artifact("full", df, format="PARQUET")
emit_artifact("summary", {{"n": len(df)}}, format="JSON")
'''
    service = make_service()
    result = submit(service, [ds], code, outputs=("CHART", "ARTIFACT"))
    assert result["execution_status"] == "COMPLETED", result["error"]
    chart, parquet_artifact, json_artifact = result["outputs"]
    assert chart["type"] == "CHART" and chart["format"] == "PNG" and chart["artifact_id"].startswith("art_")
    assert "file" not in chart and "path" not in json.dumps(result)
    assert parquet_artifact["row_count"] == 100 and len(parquet_artifact["checksum_sha256"]) == 64
    api = TestClient(create_app(service.settings, service=service, run_workers=False))
    png = api.get(f"/v1/artifacts/{chart['artifact_id']}", headers=HEADERS)
    assert png.status_code == 200 and png.headers["content-type"] == "image/png" and png.content[:4] == b"\x89PNG"
    data = api.get(f"/v1/artifacts/{parquet_artifact['artifact_id']}", headers=HEADERS)
    assert pq.read_table(io.BytesIO(data.content)).num_rows == 100
    assert api.get(f"/v1/artifacts/{chart['artifact_id']}").status_code == 401


# ---------------------------------------------------------------- acceptance D: failures

@pytest.mark.parametrize(("code", "error_code"), [
    ("x = (1", "SYNTAX_ERROR"),
    ("import socket", "FORBIDDEN_IMPORT"),
    ("import subprocess\nsubprocess.run(['id'])", "FORBIDDEN_IMPORT"),
    ("raise ValueError('boom')", "PYTHON_EXCEPTION"),
    ("x = 1", "NO_OUTPUT"),
    ("from saniti import emit_chart\nemit_chart()", "OUTPUT_INVALID"),                          # undeclared
    ("from saniti import InsufficientHistory\nraise InsufficientHistory('need 200 bars')", "INSUFFICIENT_HISTORY"),
])
def test_code_failures_are_structured(make_service, governor, code: str, error_code: str) -> None:
    ds = governor.add(pd.DataFrame({"x": [1]}))
    result = submit(make_service(), [ds], code)
    assert result["execution_status"] == "FAILED" and result["error"]["code"] == error_code
    assert result["next_action"] == "REVISE_ANALYSIS" and result["validation_status"] == "UNVERIFIED"
    assert "Traceback" not in result["error"]["message"] and "/sandbox" not in json.dumps(result["error"])


# Bypass the source screen on purpose: the kernel filter, not the screen, is the boundary.
BYPASS = "imp = getattr(__builtins__, '__imp' + 'ort__')\n"


@pytest.mark.parametrize(("code", "label"), [
    (BYPASS + "s = imp('soc' + 'ket')\ns.create_connection(('1.1.1.1', 443), timeout=3)", "tcp"),
    (BYPASS + "s = imp('soc' + 'ket')\ns.getaddrinfo('example.com', 443)", "dns"),
    (BYPASS + "u = imp('urllib.request', fromlist=['urlopen'])\nu.urlopen('http://market-sql-governor.railway.internal:8080/health')",
     "http"),
    (BYPASS + "p = imp('subpro' + 'cess')\np.run(['/bin/sh', '-c', 'id'])", "subprocess"),
    (BYPASS + "o = imp('os')\ngetattr(o, 'sys' + 'tem')('id > /dev/null')\nraise PermissionError(1, 'x')",
     "os.system"),
    (BYPASS + "o = imp('os')\ngetattr(o, 'fo' + 'rk')()", "fork"),
    (BYPASS + "m = imp('multiprocessing')\nm.Pool(2)", "multiprocessing"),
])
def test_network_and_process_attempts_are_denied_by_the_kernel(make_service, governor, code: str, label: str) -> None:
    ds = governor.add(pd.DataFrame({"x": [1]}))
    service = make_service()
    result = submit(service, [ds], code, request_id=f"deny-{label}")
    assert result["execution_status"] == "FAILED", label
    assert result["error"]["code"] == "FORBIDDEN_OPERATION", (label, result["error"])
    healthy = submit(service, [ds], "from saniti import emit_metrics\nemit_metrics({'ok': 1})",
                     outputs=("METRICS",), request_id=f"after-{label}")
    assert healthy["execution_status"] == "COMPLETED"


def test_runtime_limit_stops_the_process(make_service, governor) -> None:
    ds = governor.add(pd.DataFrame({"x": [1]}))
    service = make_service(PY_SANDBOX_MAX_RUNTIME_SECONDS="5")
    started = time.monotonic()
    result = submit(service, [ds], "while True:\n    pass")
    assert result["execution_status"] == "FAILED" and result["error"]["code"] == "RUNTIME_LIMIT_EXCEEDED"
    assert time.monotonic() - started < 20
    assert submit(service, [ds], "from saniti import emit_metrics\nemit_metrics({'ok': 1})",
                  outputs=("METRICS",), request_id="after")["execution_status"] == "COMPLETED"


def test_memory_limit_stops_the_process(make_service, governor) -> None:
    ds = governor.add(pd.DataFrame({"x": [1]}))
    service = make_service(PY_SANDBOX_MAX_MEMORY_MB="512", PY_SANDBOX_MAX_VIRTUAL_MEMORY_MB="8192")
    code = "import numpy as np\nblocks = []\nfor _ in range(40):\n    blocks.append(np.ones(64 * 1024 * 1024 // 8))"
    result = submit(service, [ds], code)
    assert result["execution_status"] == "FAILED" and result["error"]["code"] == "MEMORY_LIMIT_EXCEEDED"
    assert result["resource_usage"]["max_rss_mb"] >= 400
    virtual = submit(make_service(PY_SANDBOX_MAX_MEMORY_MB="2048"), [ds], "x = bytearray(6 * 1024 ** 3)",
                     request_id="virtual")
    assert virtual["execution_status"] == "FAILED" and virtual["error"]["code"] == "MEMORY_LIMIT_EXCEEDED"


def test_output_row_and_byte_ceilings(make_service, governor) -> None:
    ds = governor.add(pd.DataFrame({"x": [1]}))
    service = make_service(PY_SANDBOX_MAX_TABLE_OUTPUT_ROWS="1000", PY_SANDBOX_MAX_ARTIFACT_BYTES="1048576",
                           PY_SANDBOX_MAX_INTERMEDIATE_BYTES="16777216")
    rows = submit(service, [ds], "import pandas as pd\nfrom saniti import emit_table\n"
                                 "emit_table('big', pd.DataFrame({'x': range(1001)}))", request_id="rows")
    assert rows["error"]["code"] == "OUTPUT_LIMIT_EXCEEDED"
    raw = submit(service, [ds], "open('huge.bin', 'wb').write(b'x' * 20 * 1024 * 1024)", request_id="bytes")
    assert raw["error"]["code"] == "OUTPUT_LIMIT_EXCEEDED"      # RLIMIT_FSIZE -> EFBIG


def test_forged_outputs_are_rejected_by_the_harness(make_service, governor) -> None:
    """Code can skip the helper and write its own index; the harness re-checks everything."""
    ds = governor.add(pd.DataFrame({"x": [1]}))
    service = make_service()
    forged_preview = '''
import json, pandas as pd
pd.DataFrame({"x": range(100)}).to_parquet("../output/table_1.parquet")
json.dump({"outputs": [{"type": "TABLE", "name": "t", "file": "table_1.parquet", "row_count": 100,
           "columns": [{"name": "x", "type": "integer"}], "preview_rows": [[i] for i in range(100)]}]},
          open("../output/index.json", "w"))
'''
    assert submit(service, [ds], forged_preview, request_id="f1")["error"]["code"] == "OUTPUT_INVALID"
    forged_count = forged_preview.replace('"row_count": 100', '"row_count": 5').replace("range(100)]", "range(5)]")
    assert submit(service, [ds], forged_count, request_id="f2")["error"]["code"] == "OUTPUT_INVALID"
    symlink = '''
import json
imp = getattr(__builtins__, '__imp' + 'ort__')
imp('os').symlink('/etc/passwd', '../output/table_1.parquet')
json.dump({"outputs": [{"type": "TABLE", "name": "t", "file": "table_1.parquet", "row_count": 1,
           "columns": [{"name": "x", "type": "integer"}], "preview_rows": []}]}, open("../output/index.json", "w"))
'''
    assert submit(service, [ds], symlink, request_id="f3")["error"]["code"] == "OUTPUT_INVALID"


# ---------------------------------------------------------------- acceptance E: dataset security

def test_acceptance_e_dataset_failures_are_explicit(make_service, governor) -> None:
    service = make_service()
    good = governor.add(pd.DataFrame({"x": [1]}))
    expired = governor.add(pd.DataFrame({"x": [1]}), expired=True)
    tampered = governor.add(pd.DataFrame({"x": [2]}))
    governor.checksum_override[tampered] = "0" * 64
    unknown = "ds_" + "f" * 24
    ok_code = "from saniti import emit_metrics\nemit_metrics({'ok': 1})"
    cases = {unknown: "DATASET_NOT_FOUND", expired: "DATASET_EXPIRED", tampered: "DATASET_INTEGRITY_ERROR"}
    for dataset_id, code in cases.items():
        result = submit(service, [good, dataset_id], ok_code, outputs=("METRICS",), request_id=f"ds-{code}")
        assert result["execution_status"] == "FAILED" and result["error"]["code"] == code
    assert submit(service, [expired], ok_code, ("METRICS",), "x")["next_action"] == "REQUEST_DATA_AGAIN"
    with pytest.raises(ValueError):
        AnalysisRequest(request_id="r", spec_id="spec_" + "0" * 24, python_code="x", expected_outputs=["TABLE"],
                        inputs=[{"name": "data", "dataset_ids": ["../../etc/passwd"]}])
    assert all(call["authorization"] == f"Bearer {ACCESS_KEY}" for call in governor.calls)


SNOOP = '''
imp = getattr(__builtins__, '__imp' + 'ort__')
os = imp('os')
env = dict(getattr(os, 'env' + 'iron'))
found = {}
for path in ('/proc/1/environ', f'/proc/{os.getppid()}/environ', '/proc/self/environ'):
    try:
        found[path] = open(path, 'rb').read().decode(errors='replace')
    except OSError as exc:
        found[path] = f'denied {exc.errno}'
try:
    found['cache'] = str(os.listdir(CACHE))
except OSError as exc:
    found['cache'] = f'denied {exc.errno}'
try:
    found['data'] = str(os.listdir(DATA))
except OSError as exc:
    found['data'] = f'denied {exc.errno}'
from saniti import emit_metrics
emit_metrics({'env': ' '.join(sorted(env)), 'values': ' '.join(env.values())[:400],
              'reads': {k.replace('/', '_').strip('_') or 'x': v[:300] for k, v in found.items()}})
'''


def test_analysis_process_holds_no_credentials(make_service, governor, sandbox_root) -> None:
    ds = governor.add(pd.DataFrame({"x": [1]}))
    service = make_service()
    code = f"CACHE = {service.settings.cache_dir!r}\nDATA = {service.settings.data_dir!r}\n" + SNOOP
    result = submit(service, [ds], code, outputs=("METRICS",))
    assert result["execution_status"] == "COMPLETED", result["error"]
    values = result["outputs"][0]["values"]
    text = json.dumps(values)
    for secret in (API_KEY, ACCESS_KEY, "DATABASE_URL", "PGPASSWORD", "ACCESS_KEY_ID", "SECRET_ACCESS_KEY",
                   "SQL_GOVERNOR", "OPENROUTER"):
        assert secret not in text, secret
    reads = values["reads"]
    assert reads["proc_1_environ"].startswith("denied") and reads["cache"].startswith("denied")
    assert reads["data"].startswith("denied")
    assert next(v for k, v in reads.items() if k.startswith("proc_") and k != "proc_1_environ"
                and "self" not in k).startswith("denied")


def test_logs_never_contain_keys_or_dataset_urls(make_service, governor) -> None:
    records: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())
    logger = logging.getLogger("market_python_sandbox")
    handler = Capture()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        ds = governor.add(pd.DataFrame({"x": [1]}))
        service = make_service()
        submit(service, [ds], "from saniti import emit_metrics\nemit_metrics({'ok': 1})", outputs=("METRICS",))
        submit(service, ["ds_" + "e" * 24], "x = 1", request_id="missing")
    finally:
        logger.removeHandler(handler)
    text = "\n".join(records)
    assert "sandbox_analysis" in text and "code_sha256" in text
    for secret in (API_KEY, ACCESS_KEY, "file://", "/governor/", "download"):
        assert secret not in text, secret
    event = json.loads(next(r for r in records if '"sandbox_analysis"' in r and '"COMPLETED"' in r))
    assert any('"sandbox_spec_review"' in r for r in records)
    for field in ("request_id", "analysis_id", "spec_id", "dataset_ids", "dataset_checksums", "code_sha256",
                  "execution_status", "validation_status", "validation_level", "reason_codes",
                  "runtime_ms", "input_rows", "input_bytes", "output_types", "output_rows", "output_bytes",
                  "error_code"):
        assert field in event, field


# ---------------------------------------------------------------- lifecycle

def test_status_lifecycle_idempotency_and_polling(make_service, governor) -> None:
    ds = governor.add(pd.DataFrame({"x": [1]}))
    service = make_service(PY_SANDBOX_SUBMIT_WAIT_SECONDS="0")
    code = "import time\ntime.sleep(3)\nfrom saniti import emit_metrics\nemit_metrics({'ok': 1})"
    first = submit(service, [ds], code, outputs=("METRICS",))
    assert first["execution_status"] in {"QUEUED", "RUNNING"} and first["next_action"] == "GET_ANALYSIS_RESULT"
    assert first["retry_after_seconds"] == service.settings.retry_after_seconds
    again = submit(service, [ds], code, outputs=("METRICS",))
    assert again["analysis_id"] == first["analysis_id"]                        # idempotent submission
    seen = {first["execution_status"]}
    assert first["validation_status"] == "PENDING"
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        current = service.wait(first["analysis_id"], 1)
        seen.add(current["execution_status"])
        if current["execution_status"] == "COMPLETED":
            break
    assert "RUNNING" in seen and current["execution_status"] == "COMPLETED" and current["retry_after_seconds"] is None
    assert service.wait(first["analysis_id"], 0) == service.wait(first["analysis_id"], 0)   # idempotent lookup


def test_cancel_queued_and_running(make_service, governor) -> None:
    ds = governor.add(pd.DataFrame({"x": [1]}))
    service = make_service(PY_SANDBOX_SUBMIT_WAIT_SECONDS="0")
    running = submit(service, [ds], "import time\ntime.sleep(30)", request_id="c1")
    queued = submit(service, [ds], "import time\ntime.sleep(30)", request_id="c2")
    assert service.cancel(queued["analysis_id"])["execution_status"] == "CANCELLED"
    deadline = time.monotonic() + 20
    while service.records.get(running["analysis_id"])["status"] != "RUNNING" and time.monotonic() < deadline:
        time.sleep(0.2)
    service.cancel(running["analysis_id"])
    final = service.wait(running["analysis_id"], 20)
    assert final["execution_status"] == "CANCELLED" and final["next_action"] == "STOP_OR_REFORMULATE"


def test_restart_marks_unfinished_analyses_failed(make_service, governor) -> None:
    ds = governor.add(pd.DataFrame({"x": [1]}))
    service = make_service(PY_SANDBOX_SUBMIT_WAIT_SECONDS="0")
    pending = submit(service, [ds], "import time\ntime.sleep(20)")
    service.stop()
    restarted = make_service()
    record = restarted.wait(pending["analysis_id"], 0)
    assert record["execution_status"] == "FAILED" and record["error"]["code"] == "SANDBOX_RESTARTED"
    assert record["next_action"] == "REPORT_LIMITATION"
    resubmitted = submit(restarted, [ds], "import time\ntime.sleep(20)")
    assert resubmitted["analysis_id"] != pending["analysis_id"]  # transient failures may be resubmitted


def test_retention_expires_outputs_but_keeps_metadata(make_service, governor) -> None:
    ds = governor.add(pd.DataFrame({"x": np.arange(10)}))
    service = make_service()
    result = submit(service, [ds], f"from saniti import load_dataset, emit_table\nemit_table('t', load_dataset('data'))")
    result_id = result["outputs"][0]["result_id"]
    summary = service.cleanup(datetime.now(timezone.utc) + timedelta(hours=25))
    assert summary["files_removed"] == 2 and summary["analyses_expired"] == 1  # the table + feature definitions
    expired = service.wait(result["analysis_id"], 0)
    assert expired["execution_status"] == "EXPIRED" and expired["outputs"] == []
    assert expired["warnings"][-1]["code"] == "OUTPUTS_EXPIRED" and expired["lineage"]["code_sha256"]
    api = TestClient(create_app(service.settings, service=service, run_workers=False))
    assert api.get(f"/v1/results/{result_id}", headers=HEADERS).status_code == 410


# ---------------------------------------------------------------- HTTP surface

def test_api_requires_the_bearer_key_and_rejects_unknown_fields(make_service, governor) -> None:
    ds = governor.add(pd.DataFrame({"x": [1]}))
    service = make_service()
    api = TestClient(create_app(service.settings, service=service, run_workers=False))
    body = {"request_id": "r", "spec_id": "spec_" + "0" * 24, "inputs": [{"name": "data", "dataset_ids": [ds]}],
            "python_code": "x=1", "expected_outputs": ["TABLE"]}
    assert api.post("/v1/analyses", json=body).status_code == 401
    assert api.post("/v1/analyses", json=body, headers={"Authorization": "Bearer wrong"}).status_code == 401
    bad = api.post("/v1/analyses", json={**body, "max_runtime_seconds": 900}, headers=HEADERS)
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "INVALID_REQUEST"
    unknown_spec = api.post("/v1/analyses", json=body, headers=HEADERS)
    assert unknown_spec.status_code == 422 and unknown_spec.json()["error"]["code"] == "SPEC_NOT_FOUND"
    assert api.get("/v1/analyses/ana_" + "0" * 24, headers=HEADERS).status_code == 404
    assert api.get("/v1/analyses/../../etc", headers=HEADERS).status_code == 404
    for path in ("/docs", "/openapi.json", "/redoc"):
        assert api.get(path).status_code == 404
    runtime = api.get("/v1/runtime", headers=HEADERS).json()
    assert runtime["isolation"]["isolation_enforced"] is True and "not a network namespace" in runtime[
        "network_isolation"]
    assert api.get("/ready").json() == {"status": "ready"}
