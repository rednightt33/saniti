"""Persistent analysis sessions: namespace persistence, structured errors, timeouts that keep the session,
confinement (no network, no processes, read-only input, no other bundles), helpers, outputs, budgets, capacity,
restart."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from conftest import requires_root
from test_dataneed_bundles import HEADERS, approve, build, env, ytd_parts  # noqa: F401 - env is a fixture

pytestmark = requires_root


@pytest.fixture
def session(env):  # noqa: F811
    need = approve(env)
    bundle = build(env, need, ytd_parts(env, need)).json()
    assert bundle["status"] == "READY", bundle
    opened = env["api"].post("/v1/sessions", json={"request_id": "req_bundle_1", "bundle_id": bundle["input_bundle_id"]},
                             headers=HEADERS)
    assert opened.status_code == 200, opened.text
    env["bundle_id"] = bundle["input_bundle_id"]
    env["session_id"] = opened.json()["session_id"]
    env["opened"] = opened.json()
    yield env
    env["dataneed"].sessions.stop()


def run(env, code: str, request_id: str = "req_bundle_1"):  # noqa: F811
    return env["api"].post(f"/v1/sessions/{env['session_id']}/execute", json={"request_id": request_id, "code": code},
                           headers=HEADERS)


def ok(env, code: str) -> dict:  # noqa: F811
    response = run(env, code)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "OK", body
    return body


def test_the_namespace_persists_and_helpers_read_the_whole_bundle(session) -> None:
    opened = session["opened"]
    assert {d["logical_name"] for d in opened["datasets"]} == {"prices", "stock_classification"}
    assert "load(request, columns=None)" in opened["helpers"] and opened["next_action"] == "RUN_PYTHON"
    first = ok(session, "prices = saniti.load('prices')\nbanks = load('data_request_1_B')\nprint(prices.shape)")
    assert set(first["variables"]) == {"prices", "banks"} and first["stdout"].strip().startswith("(")
    second = ok(session, "def ytd(frame):\n    return frame.groupby('ticker')['close'].last()\nlast = ytd(prices)")
    assert set(second["variables"]) == {"ytd", "last"}
    third = ok(session, "print(len(last), int(prices['ticker'].nunique()))")
    assert third["stdout"].split() == ["3", "3"]
    execution = session["dataneed"].store.executions_for(session["session_id"])[0]
    assert {(a["call"], a["data_request_id"]) for a in execution["access"]} == {
        ("load", "data_request_1_A"), ("load", "data_request_1_B")}
    assert all(a["full"] for a in execution["access"])


def test_a_script_error_names_the_line_and_the_missing_field_and_the_session_survives(session) -> None:
    ok(session, "prices = load('prices')")
    body = run(session, "x = 1\ny = prices['adjusted_close']\n").json()
    assert (body["status"], body["error_type"], body["line"], body["field"], body["next_action"]) == (
        "SCRIPT_ERROR", "KeyError", 2, "adjusted_close", "REVISE_PYTHON_CODE")
    assert body["traceback"][-1]["code"] == "y = prices['adjusted_close']"
    assert body["session"]["failed_used"] == 1
    assert ok(session, "print(prices.shape[1])")["stdout"].strip() == "7"


def test_ranges_joins_sql_and_resampling(session) -> None:
    body = ok(session, """
cur = saniti.range('prices', 'current_ytd')
wide = saniti.range('prices', 'current_ytd', include_buffers=True)
joined = saniti.join(2)
counted = saniti.sql("SELECT ticker, count(*) AS n FROM prices GROUP BY 1 ORDER BY 1")
weekly = saniti.resample(load('prices', columns=['ticker', 'date', 'close', 'volume']), 'prices', '1W')
print(str(cur['date'].min()), str(cur['date'].max()), len(wide) > len(cur), 'Industry' in joined.columns,
      int(counted['n'].sum()) == len(load('prices')), sorted(weekly.columns))
""")
    words = body["stdout"].split()
    assert words[0] >= "2026-01-01" and words[1] <= "2026-09-25" and words[2:5] == ["True", "True", "True"]
    access = session["dataneed"].store.executions_for(session["session_id"])[-1]["access"]
    calls = {(a["call"], a["data_request_id"], a.get("range_id")) for a in access}
    assert ("range", "data_request_1_A", "current_ytd") in calls and ("sql", "data_request_1_A", None) in calls


def test_outputs_are_stored_with_checksums_and_readable_back_unreleased(session) -> None:
    body = ok(session, """
import matplotlib.pyplot as plt
prices = load('prices')
last = prices.groupby('ticker', as_index=False)['close'].last()
t = emit_table('last_close', last, description='last close per ticker')
emit_json('summary', {'tickers': int(len(last)), 'max': float(last['close'].max())})
emit_text('note', 'computed from the governed bundle')
plt.plot([1, 2, 3])
emit_chart(name='line', title='test')
emit_file('csv_copy', last, format='CSV')
""")
    outputs = {o["name"]: o for o in body["outputs"]}
    assert set(outputs) == {"last_close", "summary", "note", "line", "csv_copy"}
    table = outputs["last_close"]
    assert table["type"] == "TABLE" and table["row_count"] == 3 and table["columns"] == ["ticker", "close"]
    base = f"/v1/sessions/{session['session_id']}/outputs"
    page = session["api"].get(f"{base}/{table['output_id']}", params={"request_id": "req_bundle_1", "limit": 2},
                              headers=HEADERS).json()
    assert len(page["rows"]) == 2 and page["next_offset"] == 2 and page["released"] is False
    summary = session["api"].get(f"{base}/{outputs['summary']['output_id']}", params={"request_id": "req_bundle_1"},
                                 headers=HEADERS).json()
    assert summary["content"]["tickers"] == 3
    chart = session["api"].get(f"{base}/{outputs['line']['output_id']}", params={"request_id": "req_bundle_1"},
                               headers=HEADERS).json()
    assert chart["type"] == "CHART" and "note" in chart
    other = session["api"].get(f"{base}/{table['output_id']}", params={"request_id": "req_other"}, headers=HEADERS)
    assert other.status_code == 404


def test_a_timeout_interrupts_the_execution_and_keeps_the_session(session) -> None:
    session["service"].settings.__dict__["session_execution_seconds"] = 3
    ok(session, "kept = 41")
    body = run(session, "while True:\n    pass\n").json()
    assert body["status"] == "TIMEOUT" and body["next_action"] == "REVISE_PYTHON_CODE"
    assert ok(session, "print(kept + 1)")["stdout"].strip() == "42"


def test_code_that_ignores_the_interrupt_is_killed_and_the_session_ends(session) -> None:
    session["service"].settings.__dict__["session_execution_seconds"] = 2
    response = run(session, "import signal\nsignal.signal(signal.SIGINT, signal.SIG_IGN)\nwhile True:\n    pass\n")
    assert response.status_code == 409 and response.json()["error"]["code"] == "SESSION_ENDED"
    assert response.json()["next_action"] == "OPEN_ANALYSIS_SESSION"
    again = run(session, "print(1)")
    assert again.status_code == 409 and again.json()["error"]["code"] == "SESSION_CLOSED"


@pytest.mark.parametrize("code, error_type", [
    ("import socket\nsocket.socket()", "PermissionError"),
    ("import subprocess\nsubprocess.run(['id'])", "PermissionError"),
    ("x = bytearray(6 * 1024 ** 3)", "MemoryError"),
])
def test_the_session_is_confined(session, code, error_type) -> None:
    body = run(session, code).json()
    assert body["status"] == "SCRIPT_ERROR" and body["error_type"] == error_type, body
    assert ok(session, "print('still here')")["stdout"].strip() == "still here"


def test_inputs_are_read_only_and_the_bundle_store_is_out_of_reach(session) -> None:
    bundle_dir = session["service"].settings.bundle_dir
    body = ok(session, f"""
import os, glob
results = []
for path in glob.glob(os.path.join(os.getcwd(), '..', 'input', '*.parquet'))[:1]:
    try:
        open(path, 'ab').write(b'x'); results.append('wrote')
    except OSError as exc:
        results.append(type(exc).__name__)
try:
    os.listdir({bundle_dir!r}); results.append('listed')
except OSError as exc:
    results.append(type(exc).__name__)
try:
    os.listdir(os.path.join(os.getcwd(), '..', '..')); results.append('listed jobs')
except OSError as exc:
    results.append(type(exc).__name__)
print(results)
""")
    assert body["stdout"].strip() == "['PermissionError', 'PermissionError', 'PermissionError']"
    uid = ok(session, "import os\nprint(os.getuid(), os.getgid(), os.getgroups())")["stdout"].split()
    assert uid[0] == str(session["service"].settings.session_uid_base) and uid[0] != "0"


def test_insufficient_data_asks_for_a_new_revision(session) -> None:
    body = run(session, "saniti.insufficient_data('prices', 'current_ytd', value=120, "
                        "reason='RSI-14 warm-up needs 120 observations')").json()
    assert body["status"] == "INSUFFICIENT_INPUT_DATA" and body["next_action"] == "REVISE_DATA_NEED_SPEC"
    assert body["data_request_id"] == "data_request_1_A" and body["range_id"] == "current_ytd"
    assert body["requirement"] == {"type": "ADDITIONAL_HISTORY", "value": 120, "unit": "TRADING_OBSERVATIONS"}


def test_inspect_describes_variables_with_bounded_previews(session) -> None:
    ok(session, "prices = load('prices')\ndef f(x):\n    'double it'\n    return 2 * x\nn = 3")
    everything = session["api"].post(f"/v1/sessions/{session['session_id']}/inspect",
                                     json={"request_id": "req_bundle_1"}, headers=HEADERS).json()
    assert {v["name"] for v in everything["variables"]} == {"prices", "f", "n"}
    detail = session["api"].post(f"/v1/sessions/{session['session_id']}/inspect",
                                 json={"request_id": "req_bundle_1", "names": ["prices", "f", "gone"], "max_rows": 2},
                                 headers=HEADERS).json()["variables"]
    frame = next(v for v in detail if v["name"] == "prices")
    assert frame["shape"][1] == 7 and len(frame["head"]) == 2 and frame["dtypes"]["ticker"]
    assert next(v for v in detail if v["name"] == "f")["doc"] == "double it"
    assert next(v for v in detail if v["name"] == "gone")["missing"] is True


def test_budgets_capacity_and_closing(session) -> None:
    settings = session["service"].settings
    settings.__dict__["session_max_executions"] = 2
    ok(session, "a = 1")
    ok(session, "b = 2")
    assert run(session, "c = 3").json()["error"]["code"] == "SESSION_EXECUTION_LIMIT"
    settings.__dict__["max_sessions"] = 1
    session["dataneed"].sessions.slots = session["dataneed"].sessions.slots[:1]
    second = session["api"].post("/v1/sessions", json={"request_id": "req_bundle_1",
                                                       "bundle_id": session["bundle_id"]}, headers=HEADERS)
    assert second.status_code == 429 and second.json()["error"]["code"] == "SESSION_CAPACITY_EXCEEDED"
    closed = session["api"].post(f"/v1/sessions/{session['session_id']}/close", json={"request_id": "req_bundle_1"},
                                 headers=HEADERS).json()
    assert closed["status"] == "CLOSED"
    assert run(session, "print(1)").json()["error"]["code"] == "SESSION_CLOSED"
    again = session["api"].post("/v1/sessions", json={"request_id": "req_bundle_1",
                                                      "bundle_id": session["bundle_id"]}, headers=HEADERS)
    assert again.status_code == 200
    state = session["api"].get(f"/v1/sessions/{session['session_id']}", params={"request_id": "req_bundle_1"},
                               headers=HEADERS).json()
    assert state["status"] == "CLOSED" and state["close_reason"] == "CLOSED_BY_CALLER"
    assert len(state["execution_log"]) == 2


def test_a_session_belongs_to_its_request_and_a_restart_closes_it(session) -> None:
    assert run(session, "print(1)", request_id="req_other").status_code == 404
    other_bundle = session["api"].post("/v1/sessions", json={"request_id": "req_other",
                                                             "bundle_id": session["bundle_id"]}, headers=HEADERS)
    assert other_bundle.status_code == 404 and other_bundle.json()["next_action"] == "PREPARE_DATA_BUNDLE"
    from app.dataneed_service import DataNeedService

    restarted = DataNeedService(session["service"], session["dataneed"].store)
    restarted.start(run_janitor=False)
    record = session["dataneed"].store.get_session(session["session_id"])
    assert record["status"] == "CLOSED" and record["close_reason"] == "SANDBOX_RESTARTED"


# ---------------------------------------------------------------- join semantics (pure pandas)

@pytest.fixture
def helpers():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))
    import saniti_session

    saniti_session._BUNDLE.clear()
    saniti_session.REQUESTS.clear()
    saniti_session.REQUESTS.update({
        "g_A": {"data_request_id": "g_A", "logical_name": "prices", "time_column": "date", "entity_column": "ticker"},
        "g_B": {"data_request_id": "g_B", "logical_name": "reference", "time_column": None, "entity_column": "ticker"}})
    return saniti_session


def relationship(semantics: str, how: str = "INNER", **extra) -> dict:
    return {"relationship_id": 9, "left_request_id": "g_A", "right_request_id": "g_B", "join_type": how,
            "join_semantics": semantics, "left_column": "ticker", "right_column": "ticker",
            "left_time_column": "date", "right_time_column": extra.get("right_time_column"),
            "effective_from_column": extra.get("start"), "effective_to_column": extra.get("end")}


PRICES = pd.DataFrame({"ticker": ["A", "A", "A", "B"], "date": [date(2026, 1, 5), date(2026, 2, 5), date(2026, 3, 5),
                                                                  date(2026, 1, 5)], "close": [1.0, 2.0, 3.0, 4.0]})


def test_as_of_joins_take_the_latest_row_at_or_before_each_date(helpers) -> None:
    helpers._BUNDLE["relationships"] = [relationship("AS_OF", right_time_column="effective_date")]
    shares = pd.DataFrame({"ticker": ["A", "A"], "effective_date": [date(2026, 1, 1), date(2026, 2, 10)],
                           "shares": [100, 300]})
    joined = helpers.join(9, PRICES, shares)
    assert list(joined.sort_values("date")["shares"]) == [100, 100, 300]  # B has no shares row: dropped (INNER)
    left = helpers.join(9, PRICES, shares, how="left")
    assert len(left) == 4 and left[left["ticker"] == "B"]["shares"].isna().all()


def test_effective_dated_joins_use_the_row_valid_on_each_date(helpers) -> None:
    helpers._BUNDLE["relationships"] = [relationship("EFFECTIVE_DATED", start="valid_from", end="valid_to")]
    sectors = pd.DataFrame({"ticker": ["A", "A"], "sector": ["Banks", "Finance"],
                            "valid_from": [date(2026, 1, 1), date(2026, 2, 1)],
                            "valid_to": [date(2026, 2, 1), None]})
    joined = helpers.join(9, PRICES, sectors)
    assert list(joined.sort_values("date")["sector"]) == ["Banks", "Finance", "Finance"]
    assert len(helpers.join(9, PRICES, sectors, how="left")) == 4


def test_exact_date_and_current_state_joins(helpers) -> None:
    helpers._BUNDLE["relationships"] = [relationship("EXACT_DATE", right_time_column="date")]
    features = pd.DataFrame({"ticker": ["A"], "date": [date(2026, 2, 5)], "rsi": [55.0]})
    assert list(helpers.join(9, PRICES, features)["close"]) == [2.0]
    helpers._BUNDLE["relationships"] = [relationship("CURRENT_STATE")]
    universe = pd.DataFrame({"ticker": ["A"], "industry": ["Banks"]})
    assert len(helpers.join(9, PRICES, universe)) == 3 and len(helpers.join(9, PRICES, universe, how="left")) == 4
