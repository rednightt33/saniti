"""Multi-Angle Research in the sandbox (PY_SANDBOX_MULTI_ANGLE_RESEARCH_ENABLED): signed feasibility drafts promoted
into one approved RESEARCH need per bundle group, the research_* wrappers in a real session, the independent
validator at completion (one backend finding per approved angle at the right validation level), fail-closed
contract enforcement, the missing / duplicate / unapproved rules, finalize and NOT_RUN, and the flag-off shape."""
from __future__ import annotations

import copy
import hashlib
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.research_methods import METHODS, angle_signature, sha256_json
from conftest import requires_root
from dataneed_fixtures import data_need_catalog, ytd_spec
from test_dataneed_bundles import HEADERS, REFERENCE, build, ytd_parts

pytestmark = requires_root
ORIGIN, RUN = "req_plan_1", "req_run_1"
PARAMS = ("thresholds", "threshold_operator", "lags", "primary_lag", "buckets", "groups", "comparison",
          "streak_lengths", "rolling_window", "baseline_mode", "correlation_method")


def environment(make_service, governor, **flags):
    governor.catalog = data_need_catalog()
    service = make_service(start=False, PY_SANDBOX_DATANEED_ENABLED="true", **flags)
    client = TestClient(create_app(service.settings, service=service, run_workers=False))
    return {"api": client, "governor": governor, "dataneed": client.app.state.dataneed, "service": service}


@pytest.fixture
def env(make_service, governor):
    env = environment(make_service, governor, PY_SANDBOX_MULTI_ANGLE_RESEARCH_ENABLED="true")
    yield env
    env["dataneed"].sessions.stop()


def draft(env, request_id: str = ORIGIN) -> dict[str, Any]:
    body = {"request_id": request_id, "reference_time": REFERENCE, "timezone": "Asia/Jakarta",
            "spec": ytd_spec(mode="RESEARCH")}
    checked = env["api"].post("/v1/data-needs/check", json=body, headers=HEADERS).json()
    assert checked["status"] == "APPROVED", checked
    return env["api"].get(f"/v1/data-need-drafts/{checked['draft_id']}", headers=HEADERS).json()


def contract(angle_id: str, record: dict[str, Any], columns: list[str] | None = None) -> dict[str, Any]:
    datasets = []
    for rid, request in sorted(record["requests"].items()):
        keys = {request.get("entity_column"), request.get("time_column")}
        datasets.append({"data_request_id": rid, "logical_name": request["logical_name"],
                         "source_table": request["source_table"],
                         "columns": [c for c in (columns if columns and request["time_column"] else
                                                 request["columns"]) if c not in keys],
                         "ranges": [{"range_id": w["range_id"], "start": w["start"], "end": w["end"]}
                                    for w in request.get("windows") or []],
                         "entity_column": request.get("entity_column"), "time_column": request.get("time_column")})
    body = {"contract_version": "angle_data_contract/v1", "angle_id": angle_id, "bundle_group_id": "g1",
            "data_request_ids": [d["data_request_id"] for d in datasets], "datasets": datasets,
            "relationships": [2], "time_basis": "HISTORICAL_DESCRIPTIVE", "local_request_ids": {},
            "local_range_ids": {}, "data_contract_sha256": record["contract_sha256"]}
    return {**body, "angle_data_contract_sha256": sha256_json(body)}


def angle(angle_id: str, method: str, **overrides) -> dict[str, Any]:
    parameters = dict.fromkeys(PARAMS)
    parameters.update({"conditional_distribution": {"baseline_mode": "COMPLEMENT"},
                       "quantile_ranking": {"buckets": 2},
                       "threshold_sensitivity": {"thresholds": [0.0, 0.001], "threshold_operator": ">=",
                                                 "baseline_mode": "ALL"}}.get(method, {}))
    value = {"angle_id": angle_id, "angle_question": f"What does {angle_id} show?", "method_id": method,
             "method_family": METHODS[method], "condition": "An up day.", "outcome": "The next day's return.",
             "baseline_or_comparator": "Other days.", "expected_direction": "HIGHER", "outcome_horizon_periods": 1,
             "outcome_unit": "PERCENT", "min_effect": None, "parameters": parameters,
             "candidate_count": 2 if method == "threshold_sensitivity" else 1, "pairwise_comparisons": 0,
             "multiple_testing_policy": "HOLM" if method == "threshold_sensitivity" else "NONE",
             "holdout_required": False, "minimum_sample": None, "followup_of_angle_id": None,
             "bundle_group_id": "g1"}
    value.update(overrides)
    return value


def plan(record: dict[str, Any], angles: list[dict[str, Any]], columns: dict[str, list[str]] | None = None
         ) -> tuple[dict[str, Any], dict[str, Any]]:
    contracts = {a["angle_id"]: contract(a["angle_id"], record, (columns or {}).get(a["angle_id"])) for a in angles}
    spec_sha = sha256_json(record["spec"])
    data_plan = {"data_plan_version": "research_data_plan/v1", "strategy": "SINGLE_BUNDLE",
                 "bundle_groups": [{"bundle_group_id": "g1", "request_group_id": "data_request_1",
                                    "angle_ids": [a["angle_id"] for a in angles], "draft_id": record["draft_id"],
                                    "spec_sha256": spec_sha, "data_contract_sha256": record["contract_sha256"],
                                    "data_request_ids": sorted(record["requests"])}],
                 "angle_to_bundle_group": {a["angle_id"]: "g1" for a in angles}, "angle_data_contracts": contracts}
    data_plan["research_data_plan_sha256"] = sha256_json(data_plan)
    for a in angles:
        a["angle_data_contract_sha256"] = contracts[a["angle_id"]]["angle_data_contract_sha256"]
        a["angle_signature"] = angle_signature(a)
    governance = {"governance_version": "research_governance/v2", "plan_id": "rp_" + "b" * 24,
                  "root_hypothesis_id": "up_days", "root_hypothesis": "Up days are followed by gains.",
                  "angles": angles, "angle_to_bundle_group": data_plan["angle_to_bundle_group"],
                  "totals": {"candidates": sum(a["candidate_count"] for a in angles),
                             "pairwise_comparisons": sum(a["pairwise_comparisons"] for a in angles)},
                  "hashes": {"plan_sha256": "e" * 64, "research_data_plan_sha256": data_plan["research_data_plan_sha256"],
                             "spec_sha256s": [spec_sha], "draft_ids": [record["draft_id"]],
                             "angle_data_contract_sha256s": {k: v["angle_data_contract_sha256"]
                                                             for k, v in contracts.items()}}}
    return governance, data_plan


def promote(env, governance, data_plan, request_id: str = RUN) -> dict[str, Any]:
    body = {"request_id": request_id, "origin_request_id": ORIGIN, "research_governance": governance,
            "research_data_plan": data_plan}
    return env["api"].post("/v1/research-runs", json=body, headers=HEADERS).json()


def session(env, run: dict[str, Any]) -> str:
    need = env["dataneed"].get_need(run["groups"][0]["need_id"])
    bundle = build(env, need, ytd_parts(env, need), request_id=RUN).json()
    assert bundle["status"] == "READY", bundle
    opened = env["api"].post("/v1/sessions", json={"request_id": RUN, "bundle_id": bundle["input_bundle_id"]},
                             headers=HEADERS).json()
    assert opened["research"]["bundle_group_id"] == "g1", opened
    return opened["session_id"]


def run_code(env, session_id: str, code: str) -> dict[str, Any]:
    return env["api"].post(f"/v1/sessions/{session_id}/execute", json={"request_id": RUN, "code": code},
                           headers=HEADERS).json()


def complete(env, session_id: str, finalize: bool = False) -> dict[str, Any]:
    body = {"request_id": RUN, **({"finalize": True} if finalize else {})}
    return env["api"].post(f"/v1/sessions/{session_id}/complete", json=body, headers=HEADERS).json()


READ_ALL = "saniti.load('stock_classification')\n"
DECLARATIVE = ("r1 = saniti.research_conditional('a1', request='data_request_1_A', condition='close > lag(close, 1)', "
               "outcome={'forward_return': 'close'})\n")
FRAME = """
p = saniti.load('prices').sort_values(['ticker', 'date'])
p['signal'] = p.groupby('ticker')['close'].pct_change()
p['outcome'] = (p.groupby('ticker')['close'].shift(-1) / p['close'] - 1) * 100
r2 = saniti.research_quantiles('a2', p.rename(columns={'ticker': 'entity'})[['date', 'entity', 'signal', 'outcome']])
"""
CUSTOM = "r3 = saniti.research_custom('a3', {'note': 'a hand-made table'}, 'no helper fits this question')\n"


def three_angles(env):
    record = draft(env)
    angles = [angle("a1", "conditional_distribution"), angle("a2", "quantile_ranking"),
              angle("a3", "threshold_sensitivity")]
    governance, data_plan = plan(record, angles)
    run = promote(env, governance, data_plan)
    assert run["status"] == "APPROVED", run
    return run, session(env, run)


def test_a_research_run_records_one_backend_finding_per_angle(env) -> None:
    run, session_id = three_angles(env)
    result = run_code(env, session_id, READ_ALL + DECLARATIVE + FRAME + CUSTOM)
    assert result["status"] == "OK", result
    completion = complete(env, session_id)
    assert completion["status"] == "COMPLETED", completion
    final = completion["final_status"]
    findings = {f["angle_id"]: f for f in final["research_findings_v2"]}
    assert findings["a1"]["validation_level"] == "FORMULA_AND_STATISTICS_VERIFIED"
    assert findings["a2"]["validation_level"] == "STATISTICS_VERIFIED"
    assert findings["a3"]["validation_level"] == "EXECUTION_ONLY"
    assert findings["a3"]["status"] == "INSUFFICIENT_EVIDENCE"  # custom code cannot support the hypothesis
    assert final["calculation_validation"] == "EXECUTION_ONLY"  # the weakest level relied upon
    for finding in findings.values():
        assert finding["findings_version"] == "research_findings/v2" and finding["bundle_group_id"] == "g1"
        assert finding["hashes"]["research_data_plan_sha256"] and finding["released_output_ids"]
        assert finding["status"] in ("SUPPORTED", "PARTIALLY_SUPPORTED", "INSUFFICIENT_EVIDENCE")
        # P23: each estimate's unit, derived from its kind and the angle's outcome unit
        assert finding["estimates"]["units"]["p_adjusted"] == "P_VALUE"
    assert findings["a1"]["input"]["declaration"]["roles"]["outcome"] == {"forward_return": "close"}
    view = env["api"].get(f"/v1/research-runs/{run['research_run_id']}", params={"request_id": RUN},
                          headers=HEADERS).json()
    assert view["groups"][0]["status"] == "COMPLETED" and len(view["findings"]) == 3


def test_three_findings_of_the_same_family_complete(env) -> None:
    record = draft(env)
    angles = [angle("a1", "conditional_distribution", angle_question="Up days, next day?"),
              angle("a2", "conditional_distribution", angle_question="Up days, two days?", outcome_horizon_periods=2),
              angle("a3", "threshold_sensitivity", angle_question="Which size of rise?")]
    run = promote(env, *plan(record, angles))
    session_id = session(env, run)
    code = READ_ALL + DECLARATIVE + (
        "saniti.research_conditional('a2', request='data_request_1_A', condition='close > lag(close, 1)', "
        "outcome={'forward_return': 'close'})\n"
        "saniti.research_conditional('a3', request='data_request_1_A', signal='close / lag(close, 1) - 1', "
        "outcome={'forward_return': 'close'})\n")
    assert run_code(env, session_id, code)["status"] == "OK"
    completion = complete(env, session_id)
    assert completion["status"] == "COMPLETED", completion
    levels = {f["validation_level"] for f in completion["final_status"]["research_findings_v2"]}
    assert levels == {"FORMULA_AND_STATISTICS_VERIFIED"}


def test_the_wrappers_fail_closed(env) -> None:
    record = draft(env)
    angles = [angle("a1", "conditional_distribution"), angle("a2", "quantile_ranking"),
              angle("a3", "threshold_sensitivity")]
    run = promote(env, *plan(record, angles, columns={"a1": ["close"]}))
    session_id = session(env, run)

    def error(code: str) -> str:
        result = run_code(env, session_id, code)
        assert result["status"] == "SCRIPT_ERROR", result
        return result["message"]

    assert "not an approved angle" in error("saniti.research_conditional('zz', request='prices', "
                                            "condition='close > 1', outcome={'forward_return': 'close'})")
    assert "record it with saniti.research_quantiles" in error(
        "saniti.research_conditional('a2', request='prices', condition='close > 1', "
        "outcome={'forward_return': 'close'})")
    # found live (golden run 2026-09-29): a contract entry passed as request= names the expected string
    assert "data_request_id string" in error("saniti.research_conditional('a1', request={'data_request_id': "
                                             "'data_request_1_A'}, condition='close > 1', "
                                             "outcome={'forward_return': 'close'})")
    # a1's contract has only close: volume is outside it
    assert "EXPRESSION_INVALID" in error("saniti.research_conditional('a1', request='prices', condition='volume > 1', "
                                         "outcome={'forward_return': 'close'})")
    assert "CONTRACT_ENTITY_OUTSIDE" in error(
        "import pandas as pd\n"
        "f = pd.DataFrame({'date': ['2026-02-02'] * 2, 'entity': ['BBCA', 'ZZZZ'], 'signal': [1.0, 2.0], "
        "'outcome': [0.1, 0.2]})\n"
        "saniti.research_quantiles('a2', f)")
    assert "CONTRACT_DATE_OUTSIDE" in error(
        "import pandas as pd\n"
        "f = pd.DataFrame({'date': ['2019-01-02'] * 2, 'entity': ['BBCA', 'BBRI'], 'signal': [1.0, 2.0], "
        "'outcome': [0.1, 0.2]})\n"
        "saniti.research_quantiles('a2', f)")
    assert "written only by the research_* and event_study helpers" in error(
        "import pandas as pd\nsaniti.emit_table('research_input_a1', pd.DataFrame({'x': [1]}))")
    assert run_code(env, session_id, DECLARATIVE)["status"] == "OK"
    assert "already recorded" in error(DECLARATIVE)
    # a failed execution does not record: the fixed code can record the angle afterwards
    assert error("saniti.research_quantiles('a2', frame=None, request='prices', signal='close', "
                 "outcome={'forward_return': 'close'})\nraise ValueError('late failure')")
    assert run_code(env, session_id, FRAME)["status"] == "OK"


def test_a_missing_angle_keeps_the_group_incomplete_until_finalized(env) -> None:
    run, session_id = three_angles(env)
    assert run_code(env, session_id, READ_ALL + DECLARATIVE + FRAME)["status"] == "OK"
    first = complete(env, session_id)
    assert first["status"] == "INCOMPLETE" and first["next_action"] == "RUN_PYTHON"
    assert first["final_status"]["research_group"]["missing"] == ["a3"] and "a3" in first["message"]
    final = complete(env, session_id, finalize=True)
    assert final["status"] == "COMPLETED", final
    findings = {f["angle_id"]: f for f in final["final_status"]["research_findings_v2"]}
    assert findings["a3"]["status"] == "NOT_RUN" and findings["a3"]["status_reason"] == "NOT_RECORDED"


def test_a_tampered_recorded_input_is_invalid(env) -> None:
    run, session_id = three_angles(env)
    assert run_code(env, session_id, READ_ALL + DECLARATIVE + FRAME + CUSTOM)["status"] == "OK"
    store = env["dataneed"].store
    stored = next(o for o in store.outputs_for(session_id) if o["name"] == "research_input_a1")
    path = env["dataneed"].sessions.outputs_root / stored["relative_path"]
    import pandas as pd

    frame = pd.read_parquet(path)
    frame.loc[0, "outcome"] = 999.0
    path.chmod(0o600)
    frame.to_parquet(path)
    completion = complete(env, session_id)
    assert completion["status"] == "INCOMPLETE"
    findings = {f["angle_id"]: f for f in completion["research_findings_v2"]}
    assert findings["a1"]["status"] == "INVALID" and findings["a1"]["status_reason"] == "INPUT_CHECKSUM_MISMATCH"
    # with the checksum rewritten too, the declarative input is rebuilt from the bundle and still does not match
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with store._lock:
        store._db.execute("UPDATE outputs SET checksum_sha256 = ? WHERE output_id = ?", (digest, stored["output_id"]))
    call = next(o for o in store.outputs_for(session_id) if o["name"] == "research_call_a1")
    call_path = env["dataneed"].sessions.outputs_root / call["relative_path"]
    import json

    record = json.loads(call_path.read_text())
    record["input"]["sha256"] = digest
    call_path.chmod(0o600)
    call_path.write_text(json.dumps(record))
    completion = complete(env, session_id)
    findings = {f["angle_id"]: f for f in completion["research_findings_v2"]}
    assert findings["a1"]["status_reason"] == "INPUT_NOT_REPRODUCED"
    accepted = complete(env, session_id, finalize=True)
    assert accepted["status"] == "COMPLETED"  # finalize accepts INVALID as the group's terminal state


def test_a_tampered_or_foreign_plan_is_refused(env) -> None:
    record = draft(env)
    angles = [angle("a1", "conditional_distribution"), angle("a2", "quantile_ranking"),
              angle("a3", "threshold_sensitivity")]
    governance, data_plan = plan(record, angles)
    tampered = copy.deepcopy(data_plan)
    tampered["angle_data_contracts"]["a1"]["datasets"][0]["columns"].append("secret")
    result = promote(env, governance, tampered)
    assert result["status"] == "REJECTED"
    assert {"DATA_PLAN_HASH_MISMATCH", "ANGLE_CONTRACT_HASH_MISMATCH"} <= {i["code"] for i in
                                                                          result["error"]["issues"]}
    foreign = draft(env, request_id="req_other_1")
    governance, data_plan = plan(foreign, [angle("a1", "conditional_distribution"),
                                           angle("a2", "quantile_ranking"), angle("a3", "threshold_sensitivity")])
    result = promote(env, governance, data_plan)
    assert "DRAFT_OTHER_REQUEST" in {i["code"] for i in result["error"]["issues"]}
    one = plan(record, [angle("a1", "conditional_distribution")])  # the minimum is 2 since 2026-09-29
    assert "ANGLE_COUNT_INVALID" in {i["code"] for i in promote(env, *one)["error"]["issues"]}


def test_the_same_plan_again_replays_and_a_failed_group_records_not_run(env) -> None:
    record = draft(env)
    governance, data_plan = plan(record, [angle("a1", "conditional_distribution"), angle("a2", "quantile_ranking"),
                                          angle("a3", "threshold_sensitivity")])
    run = promote(env, governance, data_plan)
    again = promote(env, governance, data_plan)
    assert again["replayed"] is True and again["research_run_id"] == run["research_run_id"]
    closed = env["api"].post(f"/v1/research-runs/{run['research_run_id']}/groups/g1/close",
                             json={"request_id": RUN, "reason": "BUNDLE_TOO_LARGE"}, headers=HEADERS).json()
    assert closed["groups"][0]["status"] == "FAILED"
    assert {f["status"] for f in closed["findings"]} == {"NOT_RUN"} and len(closed["findings"]) == 3
    assert {f["status_reason"] for f in closed["findings"]} == {"BUNDLE_TOO_LARGE"}


def test_without_the_flag_nothing_changes(make_service, governor) -> None:
    env = environment(make_service, governor)
    try:
        runtime = env["api"].get("/v1/runtime", headers=HEADERS).json()
        assert runtime["multi_angle_research"]["enabled"] is False
        record = draft(env)
        governance, data_plan = plan(record, [angle("a1", "conditional_distribution"),
                                              angle("a2", "quantile_ranking"), angle("a3", "threshold_sensitivity")])
        response = env["api"].post("/v1/research-runs", json={
            "request_id": RUN, "origin_request_id": ORIGIN, "research_governance": governance,
            "research_data_plan": data_plan}, headers=HEADERS)
        assert response.status_code == 404
    finally:
        env["dataneed"].sessions.stop()


def test_the_runtime_reports_the_capability(env) -> None:
    capability = env["api"].get("/v1/runtime", headers=HEADERS).json()["multi_angle_research"]
    assert capability["enabled"] is True and capability["version"] == 2
    assert capability["min_angles"] == 2 and capability["max_angles"] == 6
    assert capability["supports_grouped_execution"] is True and len(capability["method_ids"]) == 8
    assert capability["findings_version"] == "research_findings/v2"
    from app.research_library import LIBRARY_SHA256
    assert capability["library_sha256"] == LIBRARY_SHA256


def test_a_forward_return_reads_the_price_of_another_request_and_a_price_level_outcome_is_refused(env) -> None:
    """S15 (suite20 r09, 2026-09-29): the condition's request had no price, the model built a frame with the closing
    price level as a PERCENT outcome, and three angles were SUPPORTED on it. Now the forward return can read the price
    of another contract request (declarative, reproduced by the harness), and a price-level outcome is refused in the
    session and INVALID in the harness."""
    from dataneed_fixtures import classification, prices
    from test_dataneed_bundles import extract_part, price_rows, universe_rows, window_of
    from test_dataneed_bundles import TICKERS

    spec = ytd_spec(mode="RESEARCH", data_requests=[
        prices(columns=["ticker", "date", "volume"]), classification(),
        prices("data_request_1_C", logical_name="closes", columns=["ticker", "date", "close"])])
    body = {"request_id": ORIGIN, "reference_time": REFERENCE, "timezone": "Asia/Jakarta", "spec": spec}
    checked = env["api"].post("/v1/data-needs/check", json=body, headers=HEADERS).json()
    assert checked["status"] == "APPROVED", checked
    record = env["api"].get(f"/v1/data-need-drafts/{checked['draft_id']}", headers=HEADERS).json()
    angles = [angle("a1", "conditional_distribution"), angle("a2", "quantile_ranking"),
              angle("a3", "threshold_sensitivity")]
    run = promote(env, *plan(record, angles))
    assert run["status"] == "APPROVED", run
    need = env["dataneed"].get_need(run["groups"][0]["need_id"])

    def parts(rid: str) -> list[dict[str, Any]]:
        return [extract_part(env, need, rid, price_rows(TICKERS, window_of(need, rid, r)["from"],
                                                          window_of(need, rid, r)["to"]),
                             f"{rid}__{r}__part_001", window=window_of(need, rid, r))
                for r in ("current_ytd", "previous_comparable")]

    requests = [{"data_request_id": "data_request_1_A", "envelopes": [], "parts": parts("data_request_1_A")},
                {"data_request_id": "data_request_1_B", "envelopes": [], "parts": [
                    extract_part(env, need, "data_request_1_B", universe_rows(), "data_request_1_B__static__part_001")]},
                {"data_request_id": "data_request_1_C", "envelopes": [], "parts": parts("data_request_1_C")}]
    bundle = build(env, need, requests, request_id=RUN).json()
    assert bundle["status"] == "READY", bundle
    opened = env["api"].post("/v1/sessions", json={"request_id": RUN, "bundle_id": bundle["input_bundle_id"]},
                             headers=HEADERS).json()
    session_id = opened["session_id"]
    examples = {a["angle_id"]: a["example"] for a in opened["research"]["angles"]}
    assert "'request': 'data_request_1_C'" in examples["a1"]  # the example names the request holding the price

    refused = run_code(env, session_id, (
        "p = saniti.load('prices').merge(saniti.load('closes'), on=['ticker', 'date'])\n"
        "p['signal'] = p['volume']\np['outcome'] = p['close']\n"
        "saniti.research_quantiles('a2', p.rename(columns={'ticker': 'entity'})[['date', 'entity', 'signal', "
        "'outcome']])"))
    assert refused["status"] == "SCRIPT_ERROR" and "OUTCOME_NOT_APPROVED" in refused["message"], refused

    code = (READ_ALL +
            "saniti.research_conditional('a1', request='data_request_1_A', condition='volume > lag(volume, 1)', "
            "outcome={'forward_return': 'close', 'request': 'closes'})\n"
            "saniti.research_quantiles('a2', request='data_request_1_A', signal='volume', "
            "outcome={'forward_return': 'close', 'request': 'data_request_1_C'})\n"
            "saniti.research_conditional('a3', request='data_request_1_A', signal='volume / lag(volume, 1) - 1', "
            "outcome={'forward_return': 'close', 'request': 'data_request_1_C'})\n")
    result = run_code(env, session_id, code)
    assert result["status"] == "OK", result
    completion = complete(env, session_id)
    assert completion["status"] == "COMPLETED", completion
    findings = {f["angle_id"]: f for f in completion["final_status"]["research_findings_v2"]}
    for finding in findings.values():
        assert finding["validation_level"] == "FORMULA_AND_STATISTICS_VERIFIED", finding
        assert finding["input"]["outcome_source"] == "FORWARD_RETURN"
        assert finding["status"] in ("SUPPORTED", "PARTIALLY_SUPPORTED", "INSUFFICIENT_EVIDENCE")
    assert findings["a1"]["input"]["declaration"]["roles"]["outcome"] == {"forward_return": "close",
                                                                           "request": "data_request_1_C"}


def test_research_needs_belong_to_the_conversation(make_service, governor) -> None:
    """M47 (2026-10-01): research needs were stored without the conversation key, so their bundles and outputs were
    never offered or reused in later messages of the conversation."""
    env = environment(make_service, governor, PY_SANDBOX_MULTI_ANGLE_RESEARCH_ENABLED="true",
                      PY_SANDBOX_ENABLE_CONVERSATION_REUSE="true")
    try:
        key = "ck_" + "c" * 32
        record = draft(env)
        governance, data_plan = plan(record, [angle("a1", "conditional_distribution"),
                                              angle("a2", "quantile_ranking"), angle("a3", "threshold_sensitivity")])
        body = {"request_id": RUN, "origin_request_id": ORIGIN, "research_governance": governance,
                "research_data_plan": data_plan}
        run = env["api"].post("/v1/research-runs", json=body,
                              headers={**HEADERS, "X-Saniti-Conversation-Key": key}).json()
        assert run["status"] == "APPROVED", run
        need = env["dataneed"].store.get_need(run["groups"][0]["need_id"])
        assert need["conversation_key"] == key
    finally:
        env["dataneed"].sessions.stop()
