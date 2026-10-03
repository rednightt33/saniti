"""Research findings v1 end to end in a real confined session: with the flag on, a RESEARCH need declares the
findings fields, event_summary() is pre-bound, the completion carries the backend's sample category and verdict, and
a research session without the released aggregates is not completed."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from conftest import requires_root
from dataneed_fixtures import data_need_catalog, ytd_spec
from test_dataneed_bundles import HEADERS, REFERENCE, build, ytd_parts

pytestmark = requires_root

GOVERNANCE = {"hypothesis_id": "bank_gain", "hypothesis": "Bank days are followed by higher closes.",
              "objective": "Historical pattern.", "candidate_count": 1, "pairwise_comparisons": 0, "holdout": None,
              "minimum_sample": {"value": 5, "unit": "EVENTS"}, "multiple_testing_policy": "NONE",
              "followup_of": None, "expected_direction": "HIGHER", "outcome_horizon_periods": 1,
              "outcome_unit": "PERCENT", "success_definition": "next-day return > 0"}

CODE = """
load('stock_classification')
daily = load('prices').sort_values(['ticker', 'date'])
daily['ret'] = daily.groupby('ticker')['close'].pct_change() * 100
daily = daily.dropna(subset=['ret'])
condition = daily[daily['ticker'] == daily['ticker'].iloc[0]]
baseline = daily[daily['ticker'] != daily['ticker'].iloc[0]]
result = event_summary(condition, baseline, hypothesis_id='bank_gain', outcome_column='ret', date_column='date')
print(result['sample']['flag'], result['verdict'])
"""


@pytest.fixture
def research(make_service, governor):
    governor.catalog = data_need_catalog()
    service = make_service(start=False, PY_SANDBOX_DATANEED_ENABLED="true",
                           PY_SANDBOX_RESEARCH_FINDINGS_ENABLED="true")
    client = TestClient(create_app(service.settings, service=service, run_workers=False))
    env = {"api": client, "governor": governor, "dataneed": client.app.state.dataneed, "service": service}
    body = {"request_id": "req_bundle_1", "reference_time": REFERENCE, "timezone": "Asia/Jakarta",
            "spec": ytd_spec(mode="RESEARCH"), "research_governance": GOVERNANCE}
    result = client.post("/v1/data-needs", json=body, headers=HEADERS).json()
    assert result["status"] == "APPROVED" and result["research_governance"]["decision"] == "APPROVED", result
    need = env["dataneed"].get_need(result["need_id"])
    bundle = build(env, need, ytd_parts(env, need)).json()
    assert bundle["status"] == "READY", bundle
    opened = client.post("/v1/sessions", json={"request_id": "req_bundle_1", "bundle_id": bundle["input_bundle_id"]},
                         headers=HEADERS)
    assert opened.status_code == 200, opened.text
    env.update(need=need, session_id=opened.json()["session_id"])
    yield env
    env["dataneed"].sessions.stop()


def run(env, code):
    return env["api"].post(f"/v1/sessions/{env['session_id']}/execute", json={"request_id": "req_bundle_1",
                                                                               "code": code}, headers=HEADERS).json()


def complete(env):
    return env["api"].post(f"/v1/sessions/{env['session_id']}/complete", json={"request_id": "req_bundle_1"},
                           headers=HEADERS).json()


def test_a_research_session_reports_the_backend_verdict(research) -> None:
    runtime = research["api"].get("/v1/runtime", headers=HEADERS).json()
    assert runtime["research_findings"] == {"enabled": True, "version": 1}
    # the fixed minimum sample (30) no longer refuses a plan that declared 5
    assert research["need"]["research_governance"]["constraints"]["findings"]["expected_direction"] == "HIGHER"
    body = run(research, "emit_text('note', 'reading first')\nx = load('prices')\ny = load('stock_classification')")
    assert body["status"] == "OK", body
    first = complete(research)
    assert first["status"] == "INCOMPLETE" and first["next_action"] == "RUN_PYTHON"
    assert first["research_findings_status"] == "MISSING" and "event_summary" in first["message"]
    body = run(research, CODE)
    assert body["status"] == "OK", body
    names = {o["name"] for o in body["outputs"]}
    assert {"research_events_bank_gain", "research_summary_bank_gain"} <= names
    result = complete(research)
    assert result["status"] == "COMPLETED", result
    [finding] = result["final_status"]["research_findings"]
    assert finding["hypothesis_id"] == "bank_gain" and finding["version"] == 1
    assert finding["sample_flag"] in ("INSUFFICIENT", "ANECDOTAL", "UNDERPOWERED", "ADEQUATE")
    assert finding["verdict"] in ("SUPPORTED", "NOT_SUPPORTED", "INCONCLUSIVE", "NOT_EVALUATED")
    assert finding["parameters"]["expected_direction"] == "HIGHER"
    assert finding["success_definition"] == "next-day return > 0"
    # P23: each figure carries its unit (angle A in the approved outcome unit, angle B's rates are shares)
    unit = {"PERCENT": "PERCENT", "DECIMAL": "FRACTION"}.get(finding["parameters"]["outcome_unit"])
    assert finding["units"]["angle_b.difference"] == "FRACTION" and finding["units"]["p_value"] == "P_VALUE"
    assert finding["units"].get("angle_a.difference") == unit
    assert body["stdout"].split()[:2] == [finding["sample_flag"], finding["verdict"]]


def test_without_the_flag_event_summary_is_not_pre_bound_and_the_old_floor_applies(make_service, governor) -> None:
    governor.catalog = data_need_catalog()
    service = make_service(start=False, PY_SANDBOX_DATANEED_ENABLED="true")
    client = TestClient(create_app(service.settings, service=service, run_workers=False))
    runtime = client.get("/v1/runtime", headers=HEADERS).json()
    assert runtime["research_findings"] == {"enabled": False, "version": 1}
    body = {"request_id": "req_bundle_1", "reference_time": REFERENCE, "timezone": "Asia/Jakarta",
            "spec": ytd_spec(mode="RESEARCH"), "research_governance": GOVERNANCE}
    result = client.post("/v1/data-needs", json=body, headers=HEADERS).json()
    assert result["research_governance"]["reason_code"] == "MINIMUM_SAMPLE_TOO_LOW"


# G3 (2026-10-02): the hypothesis plan runs beside Multi-Angle Research, and an event study (G2) can feed it

CHAINED = """
banks = load('stock_classification')
study = event_study('prices', 'close / lag(close, 1) - 1 <= -0.01', {'forward_return': 'close'}, 1, name='drops',
                    min_events=1)
result = event_summary(study['events'], study['baseline'], hypothesis_id='bank_gain', outcome_column='outcome',
                       date_column='date')
print(len(study['events']), len(study['baseline']), result['verdict'])
"""


def test_a_hypothesis_plan_runs_beside_multi_angle_research_and_takes_an_event_studys_rows(make_service,
                                                                                           governor) -> None:
    governor.catalog = data_need_catalog()
    service = make_service(start=False, PY_SANDBOX_DATANEED_ENABLED="true",
                           PY_SANDBOX_RESEARCH_FINDINGS_ENABLED="true",
                           PY_SANDBOX_MULTI_ANGLE_RESEARCH_ENABLED="true")
    client = TestClient(create_app(service.settings, service=service, run_workers=False))
    env = {"api": client, "governor": governor, "dataneed": client.app.state.dataneed, "service": service}
    try:
        runtime = client.get("/v1/runtime", headers=HEADERS).json()
        assert runtime["research_findings"]["enabled"] is True
        assert runtime["multi_angle_research"]["enabled"] is True
        body = {"request_id": "req_bundle_1", "reference_time": REFERENCE, "timezone": "Asia/Jakarta",
                "spec": ytd_spec(mode="RESEARCH"), "research_governance": GOVERNANCE}
        result = client.post("/v1/data-needs", json=body, headers=HEADERS).json()
        assert result["status"] == "APPROVED" and result["research_governance"]["decision"] == "APPROVED", result
        need = env["dataneed"].get_need(result["need_id"])
        bundle = build(env, need, ytd_parts(env, need)).json()
        opened = client.post("/v1/sessions", json={"request_id": "req_bundle_1",
                                                   "bundle_id": bundle["input_bundle_id"]}, headers=HEADERS).json()
        env["session_id"] = opened["session_id"]
        executed = run(env, CHAINED)
        assert executed["status"] == "OK", executed
        events, baseline, verdict = executed["stdout"].split()[:3]
        assert int(events) > 0 and int(baseline) > int(events)
        done = complete(env)
        assert done["status"] == "COMPLETED", done
        final = done["final_status"]
        [finding] = final["research_findings"]
        assert finding["hypothesis_id"] == "bank_gain" and finding["verdict"] == verdict
        assert final["event_studies"][0]["status"] == "PASS"
        # the research findings are recomputed statistics (v1), the event study tables a recomputed formula
        assert "research_group" not in final and final["calculation_validation"] == "PARTIAL"
    finally:
        env["dataneed"].sessions.stop()


RULE = {"operator": ">=", "value": 0.5}


@pytest.fixture
def ruled(make_service, governor):
    """A hypothesis plan whose success is a number (M28): next-day return >= 0.5 percent."""
    governor.catalog = data_need_catalog()
    service = make_service(start=False, PY_SANDBOX_DATANEED_ENABLED="true",
                           PY_SANDBOX_RESEARCH_FINDINGS_ENABLED="true")
    client = TestClient(create_app(service.settings, service=service, run_workers=False))
    env = {"api": client, "governor": governor, "dataneed": client.app.state.dataneed, "service": service}
    governance = {**GOVERNANCE, "success_definition": "next-day return of at least 0.5 percent", "success_rule": RULE}
    body = {"request_id": "req_bundle_1", "reference_time": REFERENCE, "timezone": "Asia/Jakarta",
            "spec": ytd_spec(mode="RESEARCH"), "research_governance": governance}
    result = client.post("/v1/data-needs", json=body, headers=HEADERS).json()
    assert result["status"] == "APPROVED", result
    need = env["dataneed"].get_need(result["need_id"])
    assert need["research_governance"]["constraints"]["findings"]["success_rule"] == RULE
    bundle = build(env, need, ytd_parts(env, need)).json()
    opened = client.post("/v1/sessions", json={"request_id": "req_bundle_1", "bundle_id": bundle["input_bundle_id"]},
                         headers=HEADERS)
    env.update(need=need, session_id=opened.json()["session_id"])
    yield env
    env["dataneed"].sessions.stop()


def test_the_approved_success_rule_is_applied_by_the_engine(ruled) -> None:
    """M28 (golden g6 2026-10-02): the plan said >= 3 percent and the engine used > 0 because the model did not pass
    the threshold. The engine reads the approved rule itself and refuses another one."""
    other = run(ruled, CODE.replace("date_column='date')", "date_column='date', success_above=0.0)"))
    assert other["status"] == "SCRIPT_ERROR" and "approved success rule is outcome >= 0.5" in other["message"]
    body = run(ruled, CODE + "print(result['success_rule'])")
    assert body["status"] == "OK", body
    result = complete(ruled)
    assert result["status"] == "COMPLETED", result
    [finding] = result["final_status"]["research_findings"]
    assert finding["success_rule"] == RULE


def test_a_summary_built_with_another_rule_is_invalid(ruled) -> None:
    body = run(ruled, CODE + "result['success_rule'] = {'operator': '>', 'value': 0.0}\n"
                             "emit_json('research_summary_bank_gain', result, definition={})")
    assert body["status"] == "OK", body
    result = complete(ruled)
    assert result["status"] == "INCOMPLETE" and result["research_findings_status"] == "INVALID"
    assert "approved success rule is outcome >= 0.5" in result["message"]


@pytest.fixture
def decimal(make_service, governor):
    """P26: a hypothesis plan whose outcome unit is DECIMAL."""
    governor.catalog = data_need_catalog()
    service = make_service(start=False, PY_SANDBOX_DATANEED_ENABLED="true",
                           PY_SANDBOX_RESEARCH_FINDINGS_ENABLED="true")
    client = TestClient(create_app(service.settings, service=service, run_workers=False))
    env = {"api": client, "governor": governor, "dataneed": client.app.state.dataneed, "service": service}
    body = {"request_id": "req_bundle_1", "reference_time": REFERENCE, "timezone": "Asia/Jakarta",
            "spec": ytd_spec(mode="RESEARCH"), "research_governance": {**GOVERNANCE, "outcome_unit": "DECIMAL"}}
    result = client.post("/v1/data-needs", json=body, headers=HEADERS).json()
    assert result["status"] == "APPROVED", result
    need = env["dataneed"].get_need(result["need_id"])
    bundle = build(env, need, ytd_parts(env, need)).json()
    opened = client.post("/v1/sessions", json={"request_id": "req_bundle_1", "bundle_id": bundle["input_bundle_id"]},
                         headers=HEADERS)
    env.update(need=need, session_id=opened.json()["session_id"])
    yield env
    env["dataneed"].sessions.stop()


def test_the_helpers_use_the_approved_outcome_unit(decimal) -> None:
    """P26 (golden g6 2026-10-02): event_summary defaulted to PERCENT under a DECIMAL plan. It now takes the
    approved unit and refuses another one."""
    other = run(decimal, CODE.replace("date_column='date')", "date_column='date', outcome_unit='PERCENT')"))
    assert other["status"] == "SCRIPT_ERROR" and "approved outcome unit is DECIMAL" in other["message"]
    body = run(decimal, CODE.replace("* 100", "") + "print('UNIT', result['parameters']['outcome_unit'])")
    assert body["status"] == "OK", body
    assert "UNIT DECIMAL" in body.get("stdout", "")
    assert complete(decimal)["status"] == "COMPLETED"
