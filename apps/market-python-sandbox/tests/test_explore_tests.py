"""EXEC-FASTLANE B3 (PY_SANDBOX_EXPLORE_TESTS_ENABLED): saniti.explore_test in an analysis session, the records of an
answer's exploratory tests and their Benjamini-Hochberg correction at complete_analysis (app/explore_tests.py).

Without the flag a session's namespace and outputs are unchanged; a research session never gets the helper."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))

import research_engines as E  # noqa: E402

from app import explore_tests  # noqa: E402
from app.main import create_app  # noqa: E402
from conftest import requires_root  # noqa: E402
from dataneed_fixtures import data_need_catalog  # noqa: E402
from test_dataneed_bundles import HEADERS, approve, build, ytd_parts  # noqa: E402

# ------------------------------------------------------------------------------------------ the correction (no session)


def records(tmp_path: Path, rows: list[dict], failed: set[str] = frozenset()) -> tuple[list, list]:
    outputs, executions = [], [{"execution_id": "exe_ok", "status": "OK"}, {"execution_id": "exe_bad",
                                                                            "status": "SCRIPT_ERROR"}]
    for i, row in enumerate(rows):
        name = f"{explore_tests.PREFIX}{row['name']}"
        path = tmp_path / f"{i:04d}.json"
        path.write_text(json.dumps(row), encoding="utf-8")
        outputs.append({"output_id": f"out_{i}", "name": name, "relative_path": path.name,
                        "execution_id": "exe_bad" if row["name"] in failed else "exe_ok"})
    return outputs, executions


def test_the_answers_tests_are_corrected_together_with_benjamini_hochberg(tmp_path) -> None:
    p_values = [0.001, 0.025, 0.035, 0.4, 0.9]
    rows = [{"name": f"t{i}", "method_id": "conditional_distribution", "p_value": p, "estimate": 1.0,
             "sample_flag": "ADEQUATE", "stability": None} for i, p in enumerate(p_values)]
    outputs, executions = records(tmp_path, rows)
    summary = explore_tests.summarize(outputs=outputs, executions=executions, outputs_root=tmp_path)
    expected = E.adjust_p_values(p_values, "BENJAMINI_HOCHBERG", len(p_values))
    assert [t["p_adjusted"] for t in summary["tests"]] == pytest.approx(expected)
    assert summary["count"] == 5 and summary["policy"] == "BENJAMINI_HOCHBERG" and summary["alpha"] == E.ALPHA
    # 0.025 and 0.035 pass alone, not after the correction over five tests (both adjust to about 0.058)
    assert [t["holds"] for t in summary["tests"]] == [True, False, False, False, False] and summary["held"] == 1


def test_a_small_sample_never_holds_and_unstable_and_small_tests_are_counted(tmp_path) -> None:
    rows = [{"name": "tiny", "p_value": 0.0001, "sample_flag": "ANECDOTAL", "stability": "UNSTABLE"},
            {"name": "big", "p_value": 0.0001, "sample_flag": "ADEQUATE", "stability": "STABLE"}]
    outputs, executions = records(tmp_path, rows)
    summary = explore_tests.summarize(outputs=outputs, executions=executions, outputs_root=tmp_path)
    assert [t["holds"] for t in summary["tests"]] == [False, True]
    assert summary["unstable"] == 1 and summary["small_samples"] == 1


def test_tests_of_a_failed_execution_do_not_count_and_none_recorded_is_none(tmp_path) -> None:
    rows = [{"name": "kept", "p_value": 0.01, "sample_flag": "ADEQUATE"},
            {"name": "lost", "p_value": 0.01, "sample_flag": "ADEQUATE"}]
    outputs, executions = records(tmp_path, rows, failed={"lost"})
    summary = explore_tests.summarize(outputs=outputs, executions=executions, outputs_root=tmp_path)
    assert [t["name"] for t in summary["tests"]] == ["kept"]
    assert explore_tests.summarize(outputs=[], executions=executions, outputs_root=tmp_path) is None


# ------------------------------------------------------------------------------------------ in a confined session

FRAME = """
import pandas as pd
banks = load('stock_classification')
daily = load('prices').sort_values(['ticker', 'date'])
daily['outcome'] = forward_return(daily, 3, value_column='close', entity_column='ticker', date_column='date')
daily['condition'] = daily.groupby('ticker')['close'].pct_change() <= -0.01
frame = daily.rename(columns={'ticker': 'entity'})[['date', 'entity', 'condition', 'outcome']].dropna()
"""


def open_session(make_service, governor, **flags):
    governor.catalog = data_need_catalog()
    service = make_service(start=False, PY_SANDBOX_DATANEED_ENABLED="true", **flags)
    client = TestClient(create_app(service.settings, service=service, run_workers=False))
    env = {"api": client, "governor": governor, "dataneed": client.app.state.dataneed, "service": service}
    need = approve(env)
    bundle = build(env, need, ytd_parts(env, need)).json()
    assert bundle["status"] == "READY", bundle
    opened = client.post("/v1/sessions", json={"request_id": "req_bundle_1", "bundle_id": bundle["input_bundle_id"]},
                         headers=HEADERS)
    assert opened.status_code == 200, opened.text
    env.update(session_id=opened.json()["session_id"])
    return env


@pytest.fixture
def explored(make_service, governor):
    env = open_session(make_service, governor, PY_SANDBOX_EXPLORE_TESTS_ENABLED="true")
    yield env
    env["dataneed"].sessions.stop()


@pytest.fixture
def plain(make_service, governor):
    env = open_session(make_service, governor)
    yield env
    env["dataneed"].sessions.stop()


def run(env, code: str) -> dict:
    response = env["api"].post(f"/v1/sessions/{env['session_id']}/execute",
                               json={"request_id": "req_bundle_1", "code": code}, headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json()


def complete(env) -> dict:
    response = env["api"].post(f"/v1/sessions/{env['session_id']}/complete", json={"request_id": "req_bundle_1"},
                               headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json()


@requires_root
def test_explore_tests_are_released_recorded_and_corrected_at_completion(explored) -> None:
    capability = explored["api"].get("/v1/runtime", headers=HEADERS).json()["explore_tests"]
    assert capability == {"enabled": True, "version": explore_tests.EXPLORE_TESTS_VERSION}
    body = run(explored, FRAME + "first = explore_test('conditional_distribution', frame, horizon=3, name='drops', "
                                 "stability=True)\n"
                                 "second = explore_test('conditional_distribution', frame.assign(condition="
                                 "frame['outcome'].shift(1) > 0), horizon=3)\n"
                                 "study = event_study('prices', 'close / lag(close, 1) - 1 <= -0.01', "
                                 "{'forward_return': 'close'}, 3, name='dips', min_events=1)\n"
                                 "print(first['effective'], first['stability'], second['name'])")
    assert body["status"] == "OK", body
    effective, stability, second = body["stdout"].split()
    # rows on one date are one observation and outcomes three days long overlap: far fewer than the rows
    assert 0 < int(effective) < 60 and stability in ("STABLE", "UNSTABLE", "INSUFFICIENT") and second == "test_2"
    names = [o["name"] for o in body["outputs"]]
    assert {"explore_drops", "explore_test_2", "explore_test_call_drops", "explore_test_call_test_2",
            "explore_test_call_es_dips"} <= set(names)
    released = {o["name"]: o for o in body["outputs"]}
    assert released["explore_drops"]["units"]["p_value"] == "P_VALUE"
    result = complete(explored)
    assert result["status"] == "COMPLETED", result
    summary = result["final_status"]["explore_tests"]
    assert summary["count"] == 3 and {t["name"] for t in summary["tests"]} == {"drops", "test_2", "es_dips"}
    adjusted = E.adjust_p_values([t["p_value"] for t in summary["tests"]], "BENJAMINI_HOCHBERG", 3)
    assert [t["p_adjusted"] for t in summary["tests"]] == pytest.approx(adjusted)
    assert result["final_status"]["event_studies"][0]["status"] == "PASS"  # the recomputation is unchanged
    released_names = [o["name"] for o in result["released_outputs"]]
    assert "explore_drops" in released_names and not any(n.startswith(explore_tests.PREFIX) for n in released_names)


@requires_root
def test_a_bad_frame_and_a_price_as_outcome_are_script_errors_and_names_are_unique(explored) -> None:
    missing = run(explored, FRAME + "explore_test('conditional_distribution', frame[['date', 'outcome']])")
    assert missing["status"] == "SCRIPT_ERROR" and "lacks the columns ['condition']" in json.dumps(missing)
    price = run(explored, FRAME + "explore_test('conditional_distribution', frame.assign(outcome=1400.0))")
    assert price["status"] == "SCRIPT_ERROR" and "OUTCOME_NOT_A_RETURN" in json.dumps(price)
    run(explored, FRAME + "explore_test('conditional_distribution', frame, horizon=3, name='same')")
    again = run(explored, "explore_test('conditional_distribution', frame, horizon=3, name='same')")
    assert again["status"] == "SCRIPT_ERROR" and "already recorded" in json.dumps(again)


@requires_root
def test_without_the_flag_nothing_changes(plain) -> None:
    assert plain["api"].get("/v1/runtime", headers=HEADERS).json()["explore_tests"]["enabled"] is False
    unbound = run(plain, FRAME + "explore_test('conditional_distribution', frame)")
    assert unbound["status"] == "SCRIPT_ERROR" and unbound["error_type"] == "NameError"
    module = run(plain, FRAME + "saniti.explore_test('conditional_distribution', frame)")
    assert module["status"] == "SCRIPT_ERROR" and "only on the fast lane" in json.dumps(module)
    body = run(plain, "study = event_study('prices', 'close / lag(close, 1) - 1 <= -0.01', {'forward_return': "
                      "'close'}, 3, name='dips', min_events=1)")
    assert body["status"] == "OK" and not any(o["name"].startswith(explore_tests.PREFIX) for o in body["outputs"])
    assert "explore_tests" not in complete(plain)["final_status"]
