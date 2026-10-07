"""EXEC-V stage 3 (M110, user decision 2026-10-07: "1 data ... di sandbox yang sama"): the experiments of one approved
hypothesis plan that read the same data share one data need (research_experiments), one bundle and one session. Each
stays one experiment for the Research Governor's budgets and rules, event_summary reads each one's approved values,
and complete_analysis releases one backend finding per experiment, passing only when every experiment has one."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.research_governance import GovernancePolicy, review, review_experiments
from conftest import requires_root
from dataneed_fixtures import data_need_catalog, ytd_spec
from test_dataneed_bundles import HEADERS, REFERENCE, build, ytd_parts
from test_research_findings_session import CODE, GOVERNANCE

SECOND = {**GOVERNANCE, "hypothesis_id": "bank_drop", "hypothesis": "Bank days are followed by lower closes.",
          "expected_direction": "LOWER", "success_definition": "next-day return < 0",
          "success_rule": {"operator": "<", "value": 0.0}}
POLICY = GovernancePolicy(enforce_minimum_sample=False, findings_fields_required=True)


def spec(group: str = "data_request_1") -> dict:
    return {"request_group_id": group, "data_requests": []}


def test_each_experiment_of_one_need_counts_for_every_budget() -> None:
    decision = review_experiments([GOVERNANCE, SECOND], spec(), [], 0, POLICY)
    assert decision["decision"] == "APPROVED", decision
    assert decision["budget"]["experiments_used"] == 2 and decision["budget"]["hypotheses_used"] == 2
    constraints = decision["constraints"]
    assert [c["hypothesis_id"] for c in constraints["experiments"]] == ["bank_gain", "bank_drop"]
    assert constraints["hypothesis_id"] == "bank_gain"  # what a one-experiment need carried
    assert constraints["compute_seconds"] == 2 * POLICY.compute_seconds_per_experiment
    assert constraints["experiments"][1]["findings"]["expected_direction"] == "LOWER"
    # the same hypothesis twice in one need is a second experiment of a tested hypothesis
    twice = review_experiments([GOVERNANCE, GOVERNANCE], spec(), [], 0, POLICY)
    assert twice["decision"] == "REPLAN_REQUIRED" and twice["reason_code"] == "HYPOTHESIS_ALREADY_TESTED"
    assert twice["hypothesis_id"] == "bank_gain" and twice["message"].startswith("Experiment bank_gain:")


def test_the_run_budget_counts_experiments_not_data_needs() -> None:
    history = [{"request_group_id": f"data_request_{i}", "revision": 1,
                "governance": {**GOVERNANCE, "hypothesis_id": f"h{i}"}} for i in range(1, 4)]
    tight = GovernancePolicy(max_experiments=4, max_hypotheses=6, enforce_minimum_sample=False)
    over = review_experiments([GOVERNANCE, SECOND], spec("data_request_9"), history, 0, tight)
    assert over["decision"] == "REJECTED" and over["reason_code"] == "EXPERIMENT_BUDGET_EXCEEDED"
    assert over["hypothesis_id"] == "bank_drop"  # the first fits, the second is the fifth experiment
    # a stored need with several experiments counts each of them for a later need
    stored = [{"request_group_id": "data_request_1", "revision": 1, "governance": [GOVERNANCE, SECOND]}]
    later = review({**GOVERNANCE, "hypothesis_id": "third"}, spec("data_request_2"), stored, 0, POLICY)
    assert later["decision"] == "APPROVED" and later["budget"]["experiments_used"] == 3


def test_a_revision_keeps_its_experiments() -> None:
    stored = [{"request_group_id": "data_request_1", "revision": 1, "governance": [GOVERNANCE, SECOND]}]
    again = review_experiments([GOVERNANCE, SECOND], spec(), stored, 1, POLICY)
    assert again["decision"] == "APPROVED" and again["constraints"]["reservation_reused"] is True
    assert again["budget"]["experiments_used"] == 2  # reservations reused, not counted again
    fewer = review(SECOND, spec(), stored, 1, POLICY)
    assert fewer["decision"] == "APPROVED"
    added = review_experiments([GOVERNANCE, {**SECOND, "hypothesis_id": "other"}], spec(), stored, 1, POLICY)
    assert added["decision"] == "REPLAN_REQUIRED" and added["reason_code"] == "HYPOTHESIS_CHANGED_IN_REVISION"


# ------------------------------------------------------------------------------------------------ sandbox (root)

SECOND_CODE = CODE.replace("bank_gain", "bank_drop")


@pytest.fixture
def research(make_service, governor):
    governor.catalog = data_need_catalog()
    service = make_service(start=False, PY_SANDBOX_DATANEED_ENABLED="true",
                           PY_SANDBOX_RESEARCH_FINDINGS_ENABLED="true")
    client = TestClient(create_app(service.settings, service=service, run_workers=False))
    env = {"api": client, "governor": governor, "dataneed": client.app.state.dataneed, "service": service}
    yield env
    env["dataneed"].sessions.stop()


def submit(env, experiments, request_id: str = "req_bundle_1"):
    body = {"request_id": request_id, "reference_time": REFERENCE, "timezone": "Asia/Jakarta",
            "spec": ytd_spec(mode="RESEARCH"), "research_experiments": experiments}
    return env["api"].post("/v1/data-needs", json=body, headers=HEADERS)


def call(env, path: str, body: dict) -> dict:
    return env["api"].post(path, json={"request_id": "req_bundle_1", **body}, headers=HEADERS).json()


@requires_root
def test_two_experiments_share_one_bundle_and_one_session_with_a_finding_each(research) -> None:
    runtime = research["api"].get("/v1/runtime", headers=HEADERS).json()
    assert runtime["research_multi_experiment"] == {"enabled": True, "version": 1, "max_experiments": 4}
    result = submit(research, [GOVERNANCE, SECOND]).json()
    assert result["status"] == "APPROVED" and result["research_governance"]["decision"] == "APPROVED", result
    need = research["dataneed"].get_need(result["need_id"])
    bundle = build(research, need, ytd_parts(research, need)).json()
    opened = call(research, "/v1/sessions", {"bundle_id": bundle["input_bundle_id"]})
    session = opened["session_id"]
    unknown = call(research, f"/v1/sessions/{session}/execute", {"code": CODE.replace("bank_gain", "elsewhere")})
    assert unknown["status"] == "SCRIPT_ERROR" and "not an approved experiment" in str(unknown), unknown
    assert call(research, f"/v1/sessions/{session}/execute", {"code": CODE})["status"] == "OK"
    one = call(research, f"/v1/sessions/{session}/complete", {})
    assert one["status"] == "INCOMPLETE" and one["next_action"] == "RUN_PYTHON", one
    assert "Experiment bank_drop" in one["message"] and "Experiment bank_gain" not in one["message"]
    # the second experiment's own approved success rule (outcome < 0) is applied in the same session
    assert call(research, f"/v1/sessions/{session}/execute", {"code": SECOND_CODE})["status"] == "OK"
    done = call(research, f"/v1/sessions/{session}/complete", {})
    assert done["status"] == "COMPLETED", done
    findings = {f["hypothesis_id"]: f for f in done["final_status"]["research_findings"]}
    assert set(findings) == {"bank_gain", "bank_drop"}
    assert findings["bank_gain"]["parameters"]["expected_direction"] == "HIGHER"
    assert findings["bank_drop"]["parameters"]["expected_direction"] == "LOWER"


@requires_root
def test_research_experiments_need_findings_v1_two_to_four_distinct_hypotheses(research, make_service,
                                                                               governor) -> None:
    one = submit(research, [GOVERNANCE], "req_check_1").json()
    assert one["status"] == "REVISION_REQUIRED" and one["issues"][-1]["field_path"] == "research_experiments"
    five = submit(research, [{**GOVERNANCE, "hypothesis_id": f"h{i}"} for i in range(5)], "req_check_2").json()
    assert five["issues"][-1]["code"] == "TOO_MANY_ITEMS"
    twice = submit(research, [GOVERNANCE, GOVERNANCE], "req_check_3").json()
    assert "DUPLICATE_HYPOTHESIS" in [i["code"] for i in twice["issues"]]
    both = research["api"].post("/v1/data-needs", json={
        "request_id": "req_bundle_1", "reference_time": REFERENCE, "spec": ytd_spec(mode="RESEARCH"),
        "research_governance": GOVERNANCE, "research_experiments": [GOVERNANCE, SECOND]}, headers=HEADERS)
    assert both.status_code == 422
    service = make_service(start=False, PY_SANDBOX_DATANEED_ENABLED="true")
    client = TestClient(create_app(service.settings, service=service, run_workers=False))
    off = client.post("/v1/data-needs", json={
        "request_id": "req_bundle_2", "reference_time": REFERENCE, "timezone": "Asia/Jakarta",
        "spec": ytd_spec(mode="RESEARCH"), "research_experiments": [GOVERNANCE, SECOND]}, headers=HEADERS).json()
    assert off["issues"][-1]["code"] == "MULTI_EXPERIMENT_UNAVAILABLE"
    assert client.get("/v1/runtime", headers=HEADERS).json()["research_multi_experiment"]["enabled"] is False
