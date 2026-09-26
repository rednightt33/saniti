"""DataNeedSpec submission through the sandbox service: the feature flag, revisions (replay, conflict, sequencing),
catalog outages, the Research Governor for mode RESEARCH, and the approved contract read back by need_id."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.dataneed_service import DataNeedService
from app.dataneed_store import DataNeedStore
from app.main import create_app
from conftest import API_KEY
from dataneed_fixtures import data_need_catalog, prices, ytd_spec

HEADERS = {"Authorization": f"Bearer {API_KEY}"}
REFERENCE = "2026-09-25T03:00:00+00:00"
ON = {"PY_SANDBOX_DATANEED_ENABLED": "true"}


@pytest.fixture
def api(make_service, governor):
    governor.catalog = data_need_catalog()
    service = make_service(start=False, **ON)
    client = TestClient(create_app(service.settings, service=service, run_workers=False))
    client.service = service
    return client


def submit(api, spec, governance=None, request_id="req_dataneed_1", **extra):
    body = {"request_id": request_id, "reference_time": REFERENCE, "timezone": "Asia/Jakarta", "spec": spec, **extra}
    if governance is not None:
        body["research_governance"] = governance
    response = api.post("/v1/data-needs", json=body, headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json()


def research(**overrides):
    governance = {"hypothesis_id": "rsi_candles", "hypothesis": "Oversold RSI with a bullish candle precedes gains.",
                  "objective": "Historical pattern of forward returns after the signal.", "candidate_count": 1,
                  "pairwise_comparisons": 0, "holdout": None, "minimum_sample": None,
                  "multiple_testing_policy": "NONE", "followup_of": None}
    governance.update(overrides)
    return governance


def research_spec(group="data_request_2", revision=1, **overrides):
    request = prices(f"{group}_A", time_ranges=[
        {"range_id": "fit", "start": "2021-01-01", "end": "2024-12-31"},
        {"range_id": "holdout", "start": "2025-01-01", "end": "2026-09-25"}],
        history_buffer={"value": 30, "unit": "TRADING_OBSERVATIONS"},
        future_buffer={"value": 20, "unit": "TRADING_OBSERVATIONS"})
    return ytd_spec(request_group_id=group, revision=revision, mode="RESEARCH",
                    question="Apakah RSI oversold dengan candle bullish diikuti kenaikan harga?",
                    data_requests=[request], relationships=[], **overrides)


def test_the_routes_do_not_exist_until_the_flag_is_on(make_service, governor) -> None:
    service = make_service(start=False)
    client = TestClient(create_app(service.settings, service=service, run_workers=False))
    body = {"request_id": "req_dataneed_1", "reference_time": REFERENCE, "spec": ytd_spec()}
    assert client.post("/v1/data-needs", json=body, headers=HEADERS).status_code == 404
    assert client.get("/v1/data-needs/need_" + "0" * 24, headers=HEADERS).status_code == 404
    assert governor.catalog_requests == []
    assert client.app.state.dataneed is None
    assert not (Path(service.settings.data_dir) / "dataneed.sqlite3").exists()


def test_the_routes_require_the_service_key(api) -> None:
    body = {"request_id": "req_dataneed_1", "reference_time": REFERENCE, "spec": ytd_spec()}
    assert api.post("/v1/data-needs", json=body).status_code == 401
    assert api.post("/v1/data-needs", json=body, headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_an_approved_analysis_need_is_readable_by_need_id(api, governor) -> None:
    result = submit(api, ytd_spec())
    assert result["status"] == "APPROVED" and result["extraction_allowed"] is True
    assert result["next_action"] == "PREPARE_DATA_BUNDLE" and result["need_id"].startswith("need_")
    assert result["research_governance"] == {"decision": "NOT_APPLICABLE"}
    assert [w["code"] for w in result["warnings"]] == ["HISTORICAL_REFERENCE_USES_CURRENT_STATE"]
    requests = {r["data_request_id"]: r for r in result["approved"]["requests"]}
    assert requests["data_request_1_A"]["restricted_by"] == [2]
    assert [r["range_id"] for r in requests["data_request_1_A"]["ranges"]] == ["current_ytd", "previous_comparable"]
    # only the spec's tables were asked of the Governor, and only catalog metadata
    assert governor.catalog_requests[-1]["tables"] == ["IDX_Stock_Universe", "Price_Stock_Indonesia_IDX"]
    need = api.get(f"/v1/data-needs/{result['need_id']}", headers=HEADERS).json()
    assert need["request_id"] == "req_dataneed_1" and need["spec_sha256"] == result["approved"]["spec_sha256"]
    assert need["requests"]["data_request_1_A"]["scope"] == {"type": "ALL"}
    assert api.get("/v1/data-needs/need_" + "f" * 24, headers=HEADERS).status_code == 404
    assert api.get("/v1/data-needs/not-a-need", headers=HEADERS).status_code == 404


def test_an_identical_resubmission_is_replayed_and_a_changed_one_conflicts(api) -> None:
    first = submit(api, ytd_spec())
    again = submit(api, ytd_spec())
    assert again["replayed"] is True and again["need_id"] == first["need_id"]
    changed = ytd_spec()
    changed["data_requests"][0]["columns"].remove("volume")
    conflict = submit(api, changed)
    assert conflict["status"] == "REVISION_REQUIRED" and conflict["extraction_allowed"] is False
    assert conflict["issues"] == [{"data_request_id": None, "code": "REVISION_CONFLICT", "field_path": "revision",
                                   "rejected_value": 1}]
    assert submit(api, dict(changed, revision=2))["status"] == "APPROVED"


def test_revisions_are_sequential_and_a_conflict_does_not_consume_a_number(api) -> None:
    broken = ytd_spec()
    broken["data_requests"][0]["columns"].append("adj_clsoe")
    first = submit(api, broken)
    assert first["status"] == "REVISION_REQUIRED" and first["need_id"] is None
    assert first["next_action"] == "REVISE_DATA_NEED_SPEC"
    skipped = submit(api, ytd_spec(revision=3))
    assert skipped["issues"][0]["code"] == "REVISION_CONFLICT" and skipped["expected_revision"] == 2
    fixed = submit(api, ytd_spec(revision=2))
    assert fixed["status"] == "APPROVED" and fixed["revision"] == 2
    assert submit(api, ytd_spec(revision=1, question="Changed."))["issues"][0]["code"] == "REVISION_CONFLICT"
    # a new request group starts at revision 1; another request has its own groups
    assert submit(api, ytd_spec(request_group_id="other", revision=2, data_requests=[
        prices("other_A")], relationships=[]))["issues"][0]["code"] == "REVISION_CONFLICT"
    assert submit(api, ytd_spec(), request_id="req_dataneed_2")["status"] == "APPROVED"


def test_a_catalog_outage_stops_temporarily_and_leaves_the_revision_free(api, governor) -> None:
    governor.catalog_down = True
    down = submit(api, ytd_spec())
    assert down["status"] == "CATALOG_UNAVAILABLE" and down["next_action"] == "STOP_TEMPORARILY"
    assert down["extraction_allowed"] is False and down["need_id"] is None
    governor.catalog_down = False
    assert submit(api, ytd_spec())["status"] == "APPROVED"


def test_governance_belongs_to_research_only(api) -> None:
    mismatch = submit(api, ytd_spec(), research())
    assert mismatch["status"] == "REVISION_REQUIRED"
    assert [i["code"] for i in mismatch["issues"]] == ["MODE_MISMATCH"]
    missing = submit(api, research_spec())
    assert missing["status"] == "REVISION_REQUIRED"
    assert missing["issues"][0]["code"] == "MISSING_REQUIRED_FIELD"
    assert missing["issues"][0]["field_path"] == "research_governance"
    malformed = submit(api, research_spec(revision=2), research(candidate_count=0, method="EVENT_STUDY"))
    assert {(i["code"], i["field_path"]) for i in malformed["issues"]} == {
        ("INVALID_FIELD_VALUE", "research_governance.candidate_count"),
        ("UNKNOWN_FIELD", "research_governance.method")}


def test_an_approved_research_need_reserves_one_experiment_and_its_revisions_reuse_it(api) -> None:
    result = submit(api, research_spec(), research(holdout={"data_request_id": "data_request_2_A",
                                                           "range_id": "holdout"}))
    assert result["status"] == "APPROVED" and result["extraction_allowed"] is True, result
    decision = result["research_governance"]
    assert decision["decision"] == "APPROVED" and decision["constraints"]["reservation_reused"] is False
    assert decision["budget"]["experiments_used"] == 1
    windows = result["approved"]["requests"][0]["ranges"]
    # 30 trading observations of history and 20 of future, the future capped at the reference date
    assert windows[0]["extract_from"] < "2020-12-01" and windows[0]["extract_to"] > "2024-12-31"
    assert windows[1]["extract_to"] == "2026-09-25"
    more = submit(api, research_spec(revision=2), research())
    assert more["research_governance"]["constraints"]["reservation_reused"] is True
    assert more["research_governance"]["budget"]["experiments_used"] == 1
    other = submit(api, research_spec(revision=3), research(hypothesis_id="another"))
    assert other["research_governance"]["reason_code"] == "HYPOTHESIS_CHANGED_IN_REVISION"
    assert other["status"] == "APPROVED" and other["extraction_allowed"] is False
    assert other["next_action"] == "REVISE_DATA_NEED_SPEC" and other["need_id"] is None


def test_condition_outcome_and_baseline_are_optional_bounded_declarations_recorded_and_returned(api) -> None:
    declared = {"condition": "RSI(14) below 30 together with a bullish engulfing candle",
                "outcome": "Return over the next 10 trading days",
                "baseline": "Return over 10 trading days from every other day of the same stocks"}
    result = submit(api, research_spec(), research(**declared))
    assert result["status"] == "APPROVED" and result["extraction_allowed"] is True, result
    constraints = result["research_governance"]["constraints"]
    assert constraints["declarations"] == declared
    # they are declarations only: the governor still says it does not check the analysis code against them
    assert "does not verify the analysis code" in constraints["note"]
    stored = api.app.state.dataneed.store.get_need(result["need_id"])
    assert {k: stored["governance"][k] for k in declared} == declared  # persisted with the need
    assert stored["approved"]["research_governance"]["constraints"]["declarations"] == declared
    # absent or null: accepted and not returned, as before the fields existed
    plain = submit(api, research_spec(group="data_request_3"), research(hypothesis_id="plain", condition=None))
    assert plain["extraction_allowed"] is True and "declarations" not in plain["research_governance"]["constraints"]
    # blank, too long or not text: a structured issue on the field path
    bad = submit(api, research_spec(group="data_request_4"),
                 research(hypothesis_id="bad", condition=" ", outcome="x" * 1001, baseline=7))
    assert bad["status"] == "REVISION_REQUIRED"
    assert {(i["code"], i["field_path"]) for i in bad["issues"]} == {
        ("INVALID_FIELD_VALUE", "research_governance.condition"),
        ("INVALID_FIELD_VALUE", "research_governance.outcome"),
        ("INVALID_FIELD_VALUE", "research_governance.baseline")}


@pytest.mark.parametrize("governance, code", [
    (research(candidate_count=5), "MULTIPLE_TESTING_POLICY_REQUIRED"),
    (research(candidate_count=500, multiple_testing_policy="HOLM"), "CANDIDATE_LIMIT_EXCEEDED"),
    (research(holdout={"data_request_id": "data_request_2_A", "range_id": "later"}), "HOLDOUT_INVALID"),
    (research(minimum_sample={"value": 3, "unit": "EVENTS"}), "MINIMUM_SAMPLE_TOO_LOW"),
    (research(followup_of="data_request_9"), "FOLLOWUP_PARENT_NOT_FOUND"),
])
def test_research_budgets_are_decided_before_extraction(api, governance, code) -> None:
    result = submit(api, research_spec(), governance)
    assert result["research_governance"]["decision"] == "REPLAN_REQUIRED"
    assert result["research_governance"]["reason_code"] == code
    assert result["extraction_allowed"] is False and result["need_id"] is None


def test_a_hypothesis_is_retested_only_as_a_followup(api) -> None:
    assert submit(api, research_spec(), research())["extraction_allowed"] is True
    again = submit(api, research_spec(group="data_request_3"), research())
    assert again["research_governance"]["reason_code"] == "HYPOTHESIS_ALREADY_TESTED"
    followup = submit(api, research_spec(group="data_request_4"), research(followup_of="data_request_2"))
    assert followup["research_governance"]["decision"] == "APPROVED"
    assert followup["research_governance"]["budget"]["experiments_used"] == 2


def test_the_experiment_budget_is_per_request(api) -> None:
    service = api.app.state.dataneed  # its policy comes from the settings' research budgets
    service.policy = type(service.policy)(max_experiments=1)
    assert submit(api, research_spec(), research())["extraction_allowed"] is True
    rejected = submit(api, research_spec(group="data_request_3"), research(hypothesis_id="second"))
    assert rejected["research_governance"]["decision"] == "REJECTED"
    assert rejected["research_governance"]["reason_code"] == "EXPERIMENT_BUDGET_EXCEEDED"
    assert rejected["next_action"] == "REPORT_LIMITATION"
    assert submit(api, research_spec(), research(), request_id="req_dataneed_2")["extraction_allowed"] is True


def test_the_request_body_is_checked_before_the_spec(api) -> None:
    for body in ({"reference_time": REFERENCE, "spec": ytd_spec()},
                 {"request_id": "bad id", "reference_time": REFERENCE, "spec": ytd_spec()},
                 {"request_id": "req_x", "reference_time": "yesterday", "spec": ytd_spec()},
                 {"request_id": "req_x", "reference_time": REFERENCE, "spec": ytd_spec(), "extra": 1}):
        response = api.post("/v1/data-needs", json=body, headers=HEADERS)
        assert response.status_code == 422 and response.json()["error"]["code"] == "INVALID_REQUEST"


def test_the_reference_date_is_the_callers_local_date(api) -> None:
    late = copy.deepcopy(ytd_spec())
    # 2026-09-24T20:00Z is already 2026-09-25 in Jakarta: a range ending on the 25th is not in the future
    body = {"request_id": "req_dataneed_1", "reference_time": "2026-09-24T20:00:00+00:00", "timezone": "Asia/Jakarta",
            "spec": late}
    result = api.post("/v1/data-needs", json=body, headers=HEADERS).json()
    assert result["status"] == "APPROVED" and result["approved"]["reference_date"] == "2026-09-25"
    body = dict(body, request_id="req_dataneed_2", timezone="UTC")
    assert api.post("/v1/data-needs", json=body, headers=HEADERS).json()["issues"][0]["code"] == "INVALID_TIME_RANGE"


def test_records_survive_a_restart_of_the_service(api, make_service) -> None:
    result = submit(api, ytd_spec())
    path = Path(api.service.settings.data_dir) / "dataneed.sqlite3"
    reopened = DataNeedService(api.service, DataNeedStore(path))
    assert reopened.get_need(result["need_id"])["spec_sha256"] == result["approved"]["spec_sha256"]
    rows = reopened.store.needs_for_request("req_dataneed_1")
    assert [r["status"] for r in rows] == ["APPROVED"]


def test_the_run_report_accepts_a_research_plan_confirmation() -> None:
    from pydantic import ValidationError

    from app.models import RunReport

    report = {"status": "AWAITING_CONFIRMATION", "response_type": "RESEARCH_PLAN_CONFIRMATION",
              "validation_gate": "NOT_APPLICABLE", "question_sha256": "a" * 64, "question": "q", "model": "m",
              "tool_call_count": 2, "total_tokens": 10, "duration_ms": 5}
    assert RunReport.model_validate(report).status == "AWAITING_CONFIRMATION"
    with pytest.raises(ValidationError):
        RunReport.model_validate({**report, "status": "APPROVED_BY_MODEL"})
