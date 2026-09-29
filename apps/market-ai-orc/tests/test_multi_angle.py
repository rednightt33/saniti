"""Multi-Angle Research in market-ai-orc (AI_ENABLE_MULTI_ANGLE_RESEARCH; MULTI_ANGLE_RESEARCH.md).

research_plan/v2 and its angle signature (pinned with the sandbox), the rpc2 continuation that binds the research data
plan, the startup negotiation, the deterministic research data planner (merge, dedup, split), the grouped run
executor, and the orchestrator turns: a v2 plan is issued only after a FEASIBLE check of exactly its angles, a RESEARCH
data need is refused, the approved turn runs through the executor, and the answer carries one finding per angle with
the backend status unchanged. With the flag off every prompt, schema and tool definition is unchanged."""
from __future__ import annotations

import copy
import json
import re
from typing import Any

import httpx
import pytest

from app.conversation_plans import advance, continuation_for
from app.orchestrator import (MULTI_ANGLE_FINDINGS_RULES, MULTI_ANGLE_PLAN_RULES, RESEARCH_PLAN_RULES,
                              AgentOrchestrator, build_system_prompt)
from app.research_plan import PlanVerificationError
from app.research_plan_v2 import (ContinuationInV2, PlanSignerV2, ResearchPlanV2, angle_signature, contract_sha256,
                                  data_plan_sha256, governance_v2, negotiate, registry as method_registry)
from app.research_run_executor import (ResearchContext, ResearchRunExecutor, current_research_context,
                                       executor_specs, remember_feasibility, synthesis_map)
from app.schemas import AgentRunRequest, FinalResponse, final_response_schema
from app.tools import ToolRegistry, ToolSpec, build_default_registry
from app.tools.analysis import SandboxClient, current_run_context, run_context
from app.tools.data_need import data_need_specs
from app.tools.request_data import current_request_id
from app.tools.research_planner import ResearchDataPlanner, research_feasibility_spec
from conftest import ScriptedClient, final_response, make_settings, tool_call_response
from test_data_need_tool import node
from test_research_plan import KEY, NOW, Clock, NoArgs

MA = {"AI_ENABLE_DATANEED": "true", "AI_REQUIRE_RESEARCH_PLAN_CONFIRMATION": "true",
      "AI_RESEARCH_PLAN_SIGNING_KEY": KEY, "AI_MAX_TOOL_ITERATIONS": "14", "AI_MAX_TOOL_CALLS": "14",
      "AI_ENABLE_PLAN_FEASIBILITY": "true", "AI_ENABLE_MULTI_ANGLE_RESEARCH": "true"}
RUN = "rr_" + "5" * 24
BUNDLE = "bundle_" + "2" * 24
QUESTION = "Apakah saham yang turun tajam cenderung memberi return lebih tinggi sesudahnya?"


# ---------------------------------------------------------------- fixtures

def parameters(**values: Any) -> dict[str, Any]:
    body = {k: None for k in ("thresholds", "threshold_operator", "lags", "primary_lag", "buckets", "groups",
                              "comparison", "streak_lengths", "rolling_window", "baseline_mode", "correlation_method")}
    body.update(values)
    return body


def angle(angle_id: str, method: str, family: str, params: dict[str, Any], question: str, **overrides: Any) -> dict:
    body = {"angle_id": angle_id, "title": question[:60], "angle_question": question, "method_id": method,
            "method_family": family, "objective": "Measure the outcome against its comparator.",
            "condition": "A daily fall of more than five percent.", "outcome": "Forward return over five days.",
            "baseline_or_comparator": "Every other day of the same stocks.", "expected_direction": "HIGHER",
            "outcome_horizon_periods": 5, "outcome_unit": "PERCENT", "min_effect": None,
            "parameters": parameters(**params), "candidate_count": 1, "pairwise_comparisons": 0,
            "multiple_testing_policy": "NONE", "holdout_required": False, "minimum_sample_value": None,
            "minimum_sample_unit": None, "why_distinct": "It asks a different question of the same hypothesis."}
    body.update(overrides)
    return body


def angles() -> list[dict[str, Any]]:
    return [angle("a_fall", "conditional_distribution", "CONDITIONAL_OUTCOME", {"baseline_mode": "COMPLEMENT"},
                  "Do large falls precede higher five-day returns?"),
            angle("a_rank", "quantile_ranking", "QUANTILE_RANKING", {"buckets": 5},
                  "Do the deepest fallers rank highest by later return?", condition="The size of the daily fall."),
            angle("a_lag", "lead_lag", "TEMPORAL_DEPENDENCY",
                  {"lags": [1, 2, 3], "primary_lag": 2, "correlation_method": "PEARSON"},
                  "Does the market fall lead the stock's return?", candidate_count=3,
                  multiple_testing_policy="BONFERRONI", condition="The market's daily return.")]


def plan_v2(**overrides: Any) -> dict[str, Any]:
    body = {"plan_version": "research_plan/v2", "original_question": QUESTION,
            "objective": "Test whether large falls historically precede higher returns.",
            "root_hypothesis_id": "fall_rebound", "root_hypothesis": "Large falls precede higher returns.",
            "universe": "All IDX stocks with daily prices", "time_scope": "2021 to the latest date",
            "analysis_frequency": "daily", "angles": angles(), "assumptions": ["Prices are as stored."],
            "limitations": ["A historical pattern, not a prediction."],
            "confirmation_question": "Setujui, ubah, atau batalkan rencana ini?"}
    body.update(overrides)
    return body


def request(rid: str, *, table: str = "Price_Stock_Indonesia_IDX", columns: tuple[str, ...] = ("ticker", "date", "close"),
            ranges: tuple[tuple[str, str, str], ...] = (("history", "2021-01-04", "2026-09-25"),),
            name: str = "prices") -> dict[str, Any]:
    return {"data_request_id": rid, "logical_name": name, "source_table": table, "entity_column": "ticker",
            "time_column": "date", "columns": list(columns), "scope": node("ALL"),
            "time_ranges": [{"range_id": r, "start": s, "end": e} for r, s, e in ranges],
            "source_frequency": "1D", "analysis_frequency": "1D", "resample": None, "history_buffer": None,
            "future_buffer": {"value": 5, "unit": "TRADING_OBSERVATIONS"},
            "ordering": [{"column": "ticker", "direction": "ASC"}, {"column": "date", "direction": "ASC"}],
            "sampling_allowed": False}


def requirement(angle_id: str, *requests: dict[str, Any]) -> dict[str, Any]:
    return {"angle_id": angle_id, "data_requests": list(requests), "relationships": []}


def feasibility_args(requirements: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"spec_version": "data_need_spec/v2", "question": QUESTION,
            "subject": {"data_domain": "MARKET", "entity_type": "STOCK", "asset_type": "IDX_EQUITY"},
            "angles": requirements or [
                requirement("a_fall", request("a_fall_A", columns=("ticker", "date", "close"))),
                requirement("a_rank", request("a_rank_A", columns=("ticker", "date", "close", "volume"),
                                              ranges=(("fit", "2021-01-04", "2026-09-25"),))),
                requirement("a_lag", request("a_lag_A", table="Index_Price_IDX", name="index_prices",
                                             columns=("ticker", "date", "close")))]}


class PlannerSandbox:
    """The sandbox side of the planner: every group spec is validated into a draft."""

    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []
        self.drafts: dict[str, dict[str, Any]] = {}

    def _request_id(self) -> str:
        return "run_001"

    def check_data_need(self, body: dict[str, Any]) -> dict[str, Any]:
        spec = body["spec"]
        self.checks.append(spec)
        from app.research_plan_v2 import sha256_json

        draft_id = "draft_" + sha256_json(spec)[:24]
        requests = {r["data_request_id"]: {k: r.get(k) for k in (
            "logical_name", "source_table", "entity_column", "time_column", "source_frequency", "analysis_frequency",
            "resample", "history_buffer", "future_buffer")} | {"scope_sha256": sha256_json(r["scope"])}
            for r in spec["data_requests"]}
        self.drafts[draft_id] = {"draft_id": draft_id, "spec": spec, "requests": requests,
                                 "contract_sha256": sha256_json(requests), "time_basis": "HISTORICAL_DESCRIPTIVE"}
        return {"status": "APPROVED", "draft_id": draft_id, "issues": [], "warnings": []}

    def get_draft(self, draft_id: str) -> dict[str, Any] | None:
        return self.drafts.get(draft_id)


class Estimator:
    def __init__(self, rows: dict[str, int] | None = None, refuse: str | None = None) -> None:
        self.rows = rows or {}
        self.refuse = refuse

    def estimate(self, draft: dict[str, Any]) -> dict[str, Any]:
        return {"requests": [{"data_request_id": k, "source_table": e["source_table"],
                              "estimated_rows": self.rows.get(e["source_table"], 1000), "extraction_parts": 1,
                              "governor_status": "REJECTED_SCAN_SIZE" if e["source_table"] == self.refuse
                              else "WITHIN_LIMITS"} for k, e in draft["requests"].items()]}


def planner(rows: dict[str, int] | None = None, max_rows: int = 2_000_000, max_groups: int = 3,
            refuse: str | None = None) -> tuple[ResearchDataPlanner, PlannerSandbox]:
    sandbox = PlannerSandbox()
    return ResearchDataPlanner(sandbox, Estimator(rows, refuse), max_groups=max_groups,
                               limits={"bundle_max_rows": max_rows, "bundle_max_parts": 128,
                                       "max_requests_per_spec": 8}), sandbox


def run_plan(planner_: ResearchDataPlanner, args: dict[str, Any] | None = None) -> dict[str, Any]:
    tokens = (current_request_id.set("run_001"), current_run_context.set(run_context(NOW, "Asia/Jakarta", [], "q")))
    try:
        return planner_.plan(args or feasibility_args())
    finally:
        current_request_id.reset(tokens[0])
        current_run_context.reset(tokens[1])


def data_plan(**kwargs: Any) -> dict[str, Any]:
    outcome = run_plan(planner(**kwargs)[0])
    assert outcome["status"] == "FEASIBLE", outcome["view"]
    return outcome["data_plan"]


def signer(clock: Clock | None = None) -> PlanSignerV2:
    return PlanSignerV2(KEY, 3600, clock or Clock())


def continuation(issued, the_plan: dict[str, Any] | None = None, the_data_plan: dict[str, Any] | None = None,
                 **overrides: Any) -> dict[str, Any]:
    body = {"kind": "RESEARCH_PLAN", "plan_id": issued.plan_id, "origin_request_id": issued.origin_request_id,
            "plan": the_plan or plan_v2(), "research_data_plan": the_data_plan or issued.research_data_plan,
            "token": issued.token, "action": None, "revision_instruction": None}
    body.update(overrides)
    return body


# ---------------------------------------------------------------- contracts

def test_the_signature_vector_and_the_registry_are_pinned_with_the_sandbox() -> None:
    vector = {"angle_question": "Do falls recover?", "method_id": "lead_lag", "condition": "A fall.",
              "outcome": "Return.", "baseline_or_comparator": "All days.", "outcome_horizon_periods": 5,
              "outcome_unit": "PERCENT", "expected_direction": "HIGHER",
              "parameters": {"lags": [3, 1, 2], "primary_lag": 2, "correlation_method": "PEARSON", "thresholds": None}}
    # the same vector is pinned in market-python-sandbox's tests/test_research_governance_v2.py
    assert angle_signature(vector) == "507cc31407e8ab03ae8e49c10f454bf2f9744ce9e6b510b018a27d7821b70955"
    assert method_registry()["sha256"] == "1321ca8f8ee3e3dcf44d3c9a6d43f89d5bf67d39e31ed584c550d39f6a8a048a"


def test_a_v2_plan_needs_three_to_six_distinct_valid_angles() -> None:
    assert len(ResearchPlanV2.model_validate(plan_v2()).angles) == 3
    with pytest.raises(ValueError):
        ResearchPlanV2.model_validate(plan_v2(angles=angles()[:2]))
    twin = angles()
    twin[1] = {**twin[0], "angle_id": "a_twin", "angle_question": "Do large falls precede higher returns, again?"}
    assert ResearchPlanV2.model_validate(plan_v2(angles=twin))  # a reworded question is a different question
    same = angles()
    same[1] = {**same[0], "angle_id": "a_twin", "angle_question": "  DO LARGE FALLS precede higher five-day returns? "}
    with pytest.raises(ValueError, match="angle_question"):
        ResearchPlanV2.model_validate(plan_v2(angles=same))
    wrong = angles()
    wrong[2]["parameters"]["primary_lag"] = 7
    with pytest.raises(ValueError, match="primary_lag must be one of lags"):
        ResearchPlanV2.model_validate(plan_v2(angles=wrong))
    family = angles()
    family[0]["method_family"] = "PERSISTENCE"
    with pytest.raises(ValueError, match="belongs to method_family"):
        ResearchPlanV2.model_validate(plan_v2(angles=family))


def test_rpc2_binds_the_plan_and_every_part_of_the_data_plan() -> None:
    plan, dp = ResearchPlanV2.model_validate(plan_v2()), data_plan()
    s = signer()
    issued = s.issue(plan, dp, "run_001", "conv_1")
    assert issued.token.startswith("rpc2.") and issued.research_data_plan == dp
    verified = s.verify(ContinuationInV2.model_validate(continuation(issued)), "conv_1")
    assert verified.data_plan_sha256 == dp["research_data_plan_sha256"]

    def reason(body: dict[str, Any], conversation: str | None = "conv_1") -> str:
        with pytest.raises(PlanVerificationError) as caught:
            s.verify(ContinuationInV2.model_validate(body), conversation)
        return caught.value.reason

    changed = plan_v2(objective="Another objective.")
    assert reason(continuation(issued, the_plan=changed)) == "PLAN_HASH"
    tampered = copy.deepcopy(dp)
    tampered["angle_data_contracts"]["a_fall"]["datasets"][0]["columns"].append("volume")
    assert reason(continuation(issued, the_data_plan=tampered)) == "DATA_PLAN_HASH"
    # a consistent re-hash of a tampered data plan still differs from what the token bound
    rehashed = copy.deepcopy(tampered)
    contract = rehashed["angle_data_contracts"]["a_fall"]
    contract["angle_data_contract_sha256"] = contract_sha256(contract)
    rehashed["research_data_plan_sha256"] = data_plan_sha256(rehashed)
    assert reason(continuation(issued, the_data_plan=rehashed)) == "DATA_PLAN_HASH"
    assert reason(continuation(issued), conversation="conv_2") == "CONVERSATION"
    # an rpc1 token is never read as rpc2
    assert reason(continuation(issued, token="rpc1." + issued.token[5:])) == "FORMAT"
    later = PlanSignerV2(KEY, 3600, Clock(NOW.replace(hour=7)))
    with pytest.raises(PlanVerificationError) as expired:
        later.verify(ContinuationInV2.model_validate(continuation(issued)), "conv_1")
    assert expired.value.code == "RESEARCH_PLAN_TOKEN_EXPIRED"


def test_governance_v2_is_built_from_the_verified_plan_only() -> None:
    dp = data_plan()
    s = signer()
    issued = s.issue(ResearchPlanV2.model_validate(plan_v2()), dp, "run_001", None)
    governance = governance_v2(s.verify(ContinuationInV2.model_validate(continuation(issued)), None))
    assert governance["governance_version"] == "research_governance/v2" and governance["plan_id"] == issued.plan_id
    assert [a["angle_id"] for a in governance["angles"]] == ["a_fall", "a_rank", "a_lag"]
    assert governance["totals"] == {"candidates": 5, "pairwise_comparisons": 0}
    assert governance["hashes"]["research_data_plan_sha256"] == dp["research_data_plan_sha256"]
    assert governance["hashes"]["draft_ids"] == [g["draft_id"] for g in dp["bundle_groups"]]
    for a in governance["angles"]:
        assert a["angle_data_contract_sha256"] == dp["angle_data_contracts"][a["angle_id"]][
            "angle_data_contract_sha256"]
        assert a["bundle_group_id"] == dp["angle_to_bundle_group"][a["angle_id"]]


def capability(**overrides: Any) -> dict[str, Any]:
    reg = method_registry()
    body = {"enabled": True, "version": 2, "supports_grouped_execution": True,
            "findings_version": "research_findings/v2", "governance_version": "research_governance/v2",
            "method_registry_sha256": reg["sha256"], "method_ids": [m["method_id"] for m in reg["methods"]],
            "min_angles": 3, "max_angles": 6,
            "limits": {"bundle_max_rows": 2_000_000, "bundle_max_parts": 128, "max_requests_per_spec": 8}}
    body.update(overrides)
    return body


def test_the_startup_negotiation_fails_closed() -> None:
    kwargs = dict(min_angles=3, max_angles=6, max_groups=3, feasibility=True, composite=True)
    settings, reason = negotiate(capability(), **kwargs)
    assert reason is None and settings["limits"]["bundle_max_rows"] == 2_000_000 and settings["max_groups"] == 3
    assert negotiate(capability(method_registry_sha256="0" * 64), **kwargs)[1].endswith(
        "(method_registry_sha256)")
    assert negotiate(capability(enabled=False), **kwargs)[0] is None
    assert negotiate(None, **kwargs)[0] is None
    assert "AI_ENABLE_COMPOSITE_KEYS" in negotiate(capability(), **{**kwargs, "composite": False})[1]
    assert "outside the sandbox policy" in negotiate(capability(max_angles=4), **kwargs)[1]


# ---------------------------------------------------------------- the research data planner

def test_equal_requests_of_different_angles_merge_into_one_bundle_with_per_angle_contracts() -> None:
    args = feasibility_args([
        requirement("a_fall", request("a_fall_A", columns=("ticker", "date", "close"))),
        requirement("a_rank", request("a_rank_A", columns=("ticker", "date", "volume"),
                                      ranges=(("fit", "2021-01-04", "2026-09-25"),))),
        requirement("a_lag", request("a_lag_A", columns=("ticker", "date", "close"),
                                     ranges=(("recent", "2025-01-02", "2026-09-25"),)))])
    planner_, sandbox = planner()
    outcome = run_plan(planner_, args)
    dp = outcome["data_plan"]
    assert outcome["status"] == "FEASIBLE" and dp["strategy"] == "SINGLE_BUNDLE" and len(sandbox.checks) == 1
    [spec] = sandbox.checks
    [merged] = spec["data_requests"]
    assert merged["columns"] == ["close", "date", "ticker", "volume"]
    # the same dates under two names are one range; a different range is added
    assert [(r["start"], r["end"]) for r in merged["time_ranges"]] == [("2021-01-04", "2026-09-25"),
                                                                      ("2025-01-02", "2026-09-25")]
    assert dp["angle_data_contracts"]["a_rank"]["local_range_ids"] == {"a_rank_A:fit": "history"}
    assert dp["angle_data_contracts"]["a_rank"]["datasets"][0]["columns"] == ["volume"]
    assert len(dp["merge_decisions"]) == 1 and len(dp["merge_decisions"][0]["merged_from"]) == 3
    assert dp["research_data_plan_sha256"] == data_plan_sha256(dp)
    for contract in dp["angle_data_contracts"].values():
        assert contract["angle_data_contract_sha256"] == contract_sha256(contract)
    assert "angle_data_contracts" not in outcome["view"]  # the model sees a compact view


def test_angles_split_into_bundle_groups_only_when_one_bundle_does_not_fit() -> None:
    rows = {"Price_Stock_Indonesia_IDX": 900_000, "Index_Price_IDX": 900_000, "Broker_Table": 900_000}
    args = feasibility_args([
        requirement("a_fall", request("a_fall_A")),
        requirement("a_rank", request("a_rank_A", table="Index_Price_IDX", name="index_prices")),
        requirement("a_lag", request("a_lag_A", table="Broker_Table", name="brokers"))])
    outcome = run_plan(planner(rows=rows, max_rows=2_000_000)[0], args)
    dp = outcome["data_plan"]
    assert outcome["status"] == "FEASIBLE" and dp["strategy"] == "MULTI_BUNDLE"
    assert [g["angle_ids"] for g in dp["bundle_groups"]] == [["a_fall", "a_rank"], ["a_lag"]]
    assert dp["angle_to_bundle_group"] == {"a_fall": "g1", "a_lag": "g2", "a_rank": "g1"}
    capped = run_plan(planner(rows=rows, max_rows=2_000_000, max_groups=1)[0], args)
    assert capped["status"] == "NOT_FEASIBLE" and capped["view"]["issues"][0]["code"] == "TOO_MANY_BUNDLE_GROUPS"
    refused = run_plan(planner(refuse="Broker_Table")[0], args)
    assert refused["status"] == "NOT_FEASIBLE" and refused["view"]["uncovered_angle_ids"] == ["a_lag"]
    few = run_plan(planner()[0], feasibility_args(feasibility_args()["angles"][:2]))
    assert few["status"] == "REVISION_REQUIRED" and few["view"]["issues"][0]["code"] == "ANGLE_COUNT_INVALID"


# ---------------------------------------------------------------- the orchestrator

class BundlePlanner:
    def __init__(self, fail: set[str] | None = None) -> None:
        self.fail = fail or set()
        self.prepared: list[str] = []

    def prepare(self, need_id: str) -> dict[str, Any]:
        self.prepared.append(need_id)
        if need_id in self.fail:
            return {"status": "REJECTED", "code": "SCAN_LIMIT"}
        return {"status": "READY", "input_bundle_id": BUNDLE, "datasets": []}


def finding(angle_id: str, status: str, level: str | None, direction: str = "EXPECTED", **extra: Any) -> dict:
    return {"findings_version": "research_findings/v2", "angle_id": angle_id, "status": status,
            "status_reason": {"SUPPORTED": "EFFECT_CI_EXCLUDES_ZERO", "NOT_RUN": "NOT_RECORDED"}.get(
                status, "CI_INCLUDES_ZERO"), "evidence_direction": direction, "validation_level": level,
            "sample": {"effective": 120, "flag": "ADEQUATE"} if status != "NOT_RUN" else None,
            "estimates": {"kind": "MEAN_DIFFERENCE", "primary": {"estimate": 1.25, "ci_adjusted": [0.4, 2.1]}}
            if status != "NOT_RUN" else {"primary": {}}, "session_id": "sess_" + "3" * 24, **extra}


FINDINGS = [finding("a_fall", "SUPPORTED", "FORMULA_AND_STATISTICS_VERIFIED"),
            finding("a_rank", "INSUFFICIENT_EVIDENCE", "STATISTICS_VERIFIED", "OPPOSITE"),
            finding("a_lag", "NOT_RUN", None, "NONE")]


class RunSandbox:
    """The sandbox HTTP boundary of the executor: research runs, sessions, executions, completions."""

    def __init__(self, findings: list[dict[str, Any]] | None = None, complete_status: str = "COMPLETED") -> None:
        self.findings = findings if findings is not None else FINDINGS
        self.complete_status = complete_status
        self.calls: list[tuple[str, str, Any]] = []
        self.governance: dict[str, Any] | None = None
        self.sessions = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b"null")
        path = request.url.path
        self.calls.append((request.method, path, body))
        if path == "/v1/research-runs":
            self.governance = body["research_governance"]
            groups = [{"bundle_group_id": g["bundle_group_id"], "angle_ids": g["angle_ids"],
                       "need_id": f"need_{n:024d}"} for n, g in enumerate(body["research_data_plan"]["bundle_groups"])]
            return httpx.Response(200, json={"status": "APPROVED", "research_run_id": RUN, "groups": groups})
        if path == "/v1/sessions":
            self.sessions += 1
            return httpx.Response(200, json={"session_id": f"sess_{self.sessions:024d}", "status": "ACTIVE",
                                             "datasets": [], "research": {"angles": []}})
        if path.endswith("/execute"):
            return httpx.Response(200, json={"status": "OK", "execution_id": f"exec_{len(self.calls)}",
                                             "session_id": path.split("/")[3]})
        if path.endswith("/complete"):
            return httpx.Response(200, json={"status": self.complete_status, "completion_id": "cmp_1",
                                             "final_status": {"research_group": {"missing": ["a_lag"]}},
                                             "released_outputs": [], "message": "a_lag has no record"})
        if path == f"/v1/research-runs/{RUN}":
            return httpx.Response(200, json={"research_run_id": RUN, "findings": self.findings})
        if path.endswith("/close"):
            return httpx.Response(200, json={"status": "CLOSED"})
        return httpx.Response(404, json={"error": {"code": "NOT_FOUND", "message": path}})


def ma_registry(run_sandbox: RunSandbox, bundles: BundlePlanner | None = None,
                planner_: ResearchDataPlanner | None = None, calls: list | None = None) -> ToolRegistry:
    registry = ToolRegistry()
    client = SandboxClient("http://sandbox.test", "s" * 40, 10, 0, transport=httpx.MockTransport(run_sandbox.handler))
    for spec in data_need_specs(client, timeout_seconds=10, max_result_bytes=40000, composite_keys=True):
        registry.register(spec)
    registry.register(ToolSpec(name="discover_catalog", description="discover", arguments_model=NoArgs,
                               handler=lambda a: {"tables": ["Price_Stock_Indonesia_IDX"]}))
    registry.register(research_feasibility_spec(planner_ or planner()[0], timeout_seconds=10, max_result_bytes=120000,
                                                on_result=remember_feasibility))
    for spec in executor_specs(timeout_seconds=10, execution_timeout_seconds=10, max_result_bytes=120000):
        registry.register(spec)
    bundles = bundles or BundlePlanner()

    def factory(verified, request_id: str) -> ResearchRunExecutor:
        if calls is not None:
            calls.append(request_id)
        return ResearchRunExecutor(client, bundles, verified, request_id, execution_timeout=10, timeout=10,
                                   max_result_bytes=120000)

    registry.multi_angle = {"max_groups": 3, "min_angles": 3, "max_angles": 6, "limits": {}, "factory": factory}
    return registry


def agent(script: list, run_sandbox: RunSandbox | None = None, **kwargs: Any):
    scripted = ScriptedClient(script)
    run_sandbox = run_sandbox or RunSandbox()
    runner = AgentOrchestrator(make_settings(**MA), scripted, ma_registry(run_sandbox, **kwargs),
                               wall_clock=Clock(), draft_reader=lambda draft_id: None)
    return runner, scripted, run_sandbox


def call(name: str, arguments: dict[str, Any], call_id: str) -> dict[str, Any]:
    return tool_call_response(name, json.dumps(arguments), call_id=call_id)


def plan_response(**overrides: Any) -> dict[str, Any]:
    return {"response_type": "RESEARCH_PLAN_CONFIRMATION",
            "answer": "Rencana riset dengan tiga sudut: penurunan besar, peringkat, dan lead-lag. Setujui?",
            "clarification_question": None, "assumptions": [], "limitations": [], "research_plan": plan_v2(**overrides),
            "research_findings": None}


def test_the_flag_off_keeps_every_prompt_schema_and_tool_unchanged() -> None:
    for args in ((False, True, True), (True, True, True)):
        base = build_system_prompt(*args, plan_feasibility=True, final_contract=True)
        assert build_system_prompt(*args, plan_feasibility=True, final_contract=True, multi_angle=False) == base
        assert MULTI_ANGLE_PLAN_RULES not in base and RESEARCH_PLAN_RULES in base
    assert final_response_schema(True, True, True) == final_response_schema(True, True, True, multi_angle=False)
    assert final_response_schema(False, multi_angle=True) == final_response_schema(False)
    t = httpx.MockTransport(lambda r: httpx.Response(404))
    from app.tools.request_data import GovernorClient

    kwargs = dict(cursor_secret=b"x" * 32, governor_client=GovernorClient("http://g", "k" * 40, 90, transport=t),
                  sandbox_client=SandboxClient("http://s", "s" * 40, 45, 20, transport=t), dataneed_enabled=True,
                  plan_feasibility=True, composite_keys=True)
    off = build_default_registry(object(), **kwargs)
    on = build_default_registry(object(), multi_angle={"max_groups": 3, "min_angles": 3, "max_angles": 6,
                                                       "limits": {}}, **kwargs)
    assert getattr(off, "multi_angle", None) is None
    assert set(on.names()) - set(off.names()) == {"check_research_feasibility", "start_research_run",
                                                  "run_research_code", "complete_research_run"}
    assert set(off.names()) - set(on.names()) == {"check_data_feasibility"}
    shared = set(on.names()) & set(off.names())
    assert [d for d in off.definitions() if d["name"] in shared] == [d for d in on.definitions() if d["name"] in shared]


def test_the_multi_angle_prompt_replaces_the_plan_rules_and_names_no_figures() -> None:
    prompt = build_system_prompt(False, True, True, plan_feasibility=True, final_contract=True, research_findings=True,
                                 multi_angle=True)
    assert MULTI_ANGLE_PLAN_RULES in prompt and MULTI_ANGLE_FINDINGS_RULES in prompt
    assert RESEARCH_PLAN_RULES not in prompt and "check_data_feasibility" not in prompt
    # no digits except the list numbering (the system prompt is a number source for the provenance check)
    assert not re.search(r"\d", re.sub(r"(?m)^\d\. ", "", MULTI_ANGLE_PLAN_RULES + MULTI_ANGLE_FINDINGS_RULES))
    assert '"plan_version": "research_plan/v2"' in prompt and '"angles": [' in prompt
    schema = final_response_schema(True, False, True, multi_angle=True)
    plan_schema = schema["properties"]["research_plan"]["anyOf"][0]
    assert "angles" in plan_schema["properties"] and "experiments" not in plan_schema["properties"]
    assert "angle_id" in schema["properties"]["research_findings"]["anyOf"][0]["items"]["properties"]


def test_a_v2_plan_is_issued_only_after_a_feasible_check_of_exactly_its_angles() -> None:
    runner, scripted, _ = agent([final_response(plan_response()), call("check_research_feasibility",
                                                                       feasibility_args(), "c1"),
                                 final_response(plan_response())])
    assert runner.multi_angle and "check_research_feasibility" in runner.plan_tools
    result = runner.run(AgentRunRequest(request_id="run_001", conversation_id="conv_1", message=QUESTION))
    assert "check_research_feasibility" in str(scripted.payloads[1]["input"][-1])  # the reminder
    assert result.response.response_type == "RESEARCH_PLAN_CONFIRMATION"
    issued = result.continuation
    assert issued.plan_version == "research_plan/v2" and issued.token.startswith("rpc2.")
    assert result.execution.research_plan.plan_version == "research_plan/v2"
    assert result.execution.research_plan.research_data_plan_sha256 == \
        issued.research_data_plan["research_data_plan_sha256"]
    verified = signer().verify(ContinuationInV2.model_validate(continuation(issued)), "conv_1")
    assert sorted(verified.research_data_plan["angle_to_bundle_group"]) == ["a_fall", "a_lag", "a_rank"]


def test_a_plan_with_other_angles_than_checked_or_in_the_v1_form_is_not_issued() -> None:
    other = angles()
    other[2] = angle("a_other", "streak_persistence", "PERSISTENCE", {"streak_lengths": [2, 3]},
                     "Do losing streaks reverse?", candidate_count=2, multiple_testing_policy="HOLM")
    runner, scripted, _ = agent([call("check_research_feasibility", feasibility_args(), "c1"),
                                 final_response(plan_response(angles=other)), final_response(plan_response(angles=other))])
    result = runner.run(AgentRunRequest(request_id="run_001", conversation_id="conv_1", message=QUESTION))
    assert "differ from the angles checked" in str(scripted.payloads[2]["input"][-1])
    assert result.response.response_type == "LIMITATION" and result.continuation is None
    from test_research_plan import plan as plan_v1

    v1 = {**plan_response(), "research_plan": plan_v1()}
    runner, scripted, _ = agent([call("check_research_feasibility", feasibility_args(), "c1"), final_response(v1),
                                 final_response(v1)])
    result = runner.run(AgentRunRequest(request_id="run_001", conversation_id="conv_1", message=QUESTION))
    assert "multi-angle form" in str(scripted.payloads[2]["input"][-1])
    assert result.response.response_type == "LIMITATION" and result.continuation is None


def test_a_research_data_need_is_refused_before_it_reaches_the_sandbox() -> None:
    from test_data_need_tool import ytd_arguments

    research = ytd_arguments(mode="RESEARCH", spec_version="data_need_spec/v2", research_governance=None)
    runner, scripted, sandbox = agent([call("submit_data_need_spec", research, "c1"),
                                       final_response({"response_type": "LIMITATION", "answer": "Butuh rencana.",
                                                       "clarification_question": None, "assumptions": [],
                                                       "limitations": ["x"], "research_plan": None,
                                                       "research_findings": None})])
    result = runner.run(AgentRunRequest(request_id="run_001", conversation_id="conv_1", message=QUESTION))
    output = json.loads(scripted.payloads[1]["input"][-1]["output"])
    assert output["error"]["code"] == "MULTI_ANGLE_PLAN_REQUIRED" and sandbox.calls == []
    assert result.status == "LIMITED"


def issued_continuation(action: str | None = None) -> tuple[Any, dict[str, Any]]:
    issued = signer().issue(ResearchPlanV2.model_validate(plan_v2()), data_plan(), "run_001", "conv_1")
    return issued, continuation(issued, action=action)


def findings_answer(statuses: dict[str, str] | None = None, text: str | None = None) -> dict[str, Any]:
    statuses = statuses or {"a_fall": "SUPPORTED", "a_rank": "INSUFFICIENT_EVIDENCE", "a_lag": "NOT_RUN"}
    return {"response_type": "ANSWER",
            "answer": text or ("Dari tiga sudut, hanya a_fall mendukung hipotesis: return 1.25 persen lebih tinggi "
                               "(sampel efektif 120); a_rank belum cukup bukti dan arahnya berlawanan; a_lag tidak "
                               "dijalankan."),
            "clarification_question": None, "assumptions": [], "limitations": [], "research_plan": None,
            "research_findings": [
                {"angle_id": a, "status": s, "interpretation": {
                    "answer": f"{a}: {s.lower()}.", "evidence": "Sampel efektif 120 tanggal." if s != "NOT_RUN"
                    else "Tidak ada data yang dijalankan.", "usefulness": "Perlu dibandingkan dengan biaya transaksi.",
                    "follow_up": "Uji periode lain."}} for a, s in statuses.items()]}


def approved_run(script: list, run_sandbox: RunSandbox | None = None, **kwargs: Any):
    issued, body = issued_continuation("APPROVE")
    runner, scripted, sandbox = agent(script, run_sandbox, **kwargs)
    result = runner.run(AgentRunRequest(request_id="run_002", conversation_id="conv_1", message="Setuju.",
                                        continuation=body))
    return result, scripted, sandbox, issued


RUN_SCRIPT = [call("start_research_run", {}, "c1"),
              call("run_research_code", {"bundle_group_id": "g1", "code": "saniti.research_conditional(...)"}, "c2"),
              call("complete_research_run", {"finalize": True}, "c3")]


def test_the_approved_turn_runs_the_plan_through_the_executor_and_reports_every_angle() -> None:
    result, scripted, sandbox, issued = approved_run([*RUN_SCRIPT, final_response(findings_answer())])
    offered = {t["name"] for t in scripted.payloads[0]["tools"]}
    assert offered >= {"start_research_run", "run_research_code", "complete_research_run", "discover_catalog"}
    assert not offered & {"submit_data_need_spec", "check_research_feasibility", "prepare_data_bundle"}
    assert sandbox.governance["plan_id"] == issued.plan_id and len(sandbox.governance["angles"]) == 3
    assert result.status == "COMPLETED" and result.response.response_type == "ANSWER"
    assert [f.status for f in result.response.research_findings] == ["SUPPORTED", "INSUFFICIENT_EVIDENCE", "NOT_RUN"]
    plan_exec = result.execution.research_plan
    assert plan_exec.turn == "EXECUTE_APPROVED" and plan_exec.research_submitted is True
    assert plan_exec.research_run_id == RUN and plan_exec.plan_version == "research_plan/v2"
    experiments = result.execution.research.experiments
    assert [(e.angle_id, e.status, e.payload_version) for e in experiments] == [
        ("a_fall", "SUPPORTED", "research_findings/v2"), ("a_rank", "INSUFFICIENT_EVIDENCE", "research_findings/v2"),
        ("a_lag", "NOT_RUN", "research_findings/v2")]
    assert experiments[0].retained == "RETAINED" and experiments[2].retained == "NOT_RUN"
    assert result.execution.analysis_final_status["calculation_validation"] == "STATISTICS_VERIFIED"
    assert any("calculation validation STATISTICS_VERIFIED" in line for line in result.response.limitations)
    assert any("Angles not run: a_lag" in line for line in result.response.limitations)
    assert result.continuation is None
    dumped = result.model_dump(mode="json")
    assert dumped["execution"]["research"]["experiments"][0]["method_id"] == "conditional_distribution"


def test_a_changed_status_or_an_agreement_claim_the_map_does_not_allow_is_rejected() -> None:
    wrong = findings_answer({"a_fall": "SUPPORTED", "a_rank": "SUPPORTED", "a_lag": "NOT_RUN"})
    result, scripted, _, _ = approved_run([*RUN_SCRIPT, final_response(wrong), final_response(wrong)])
    assert "a_rank: status SUPPORTED differs from the backend's INSUFFICIENT_EVIDENCE" in \
        str(scripted.payloads[4]["input"][-1])
    assert result.response.response_type == "LIMITATION" and result.execution.validation_gate == "FORCED_LIMITATION"
    agree = findings_answer(text="Semua sudut mendukung hipotesis: return 1.25 persen lebih tinggi (sampel efektif "
                                 "120).")
    result, scripted, _, _ = approved_run([*RUN_SCRIPT, final_response(agree), final_response(findings_answer())])
    assert "claims the angles agree" in str(scripted.payloads[4]["input"][-1])
    assert result.response.response_type == "ANSWER" and result.execution.validation_gate in ("PASSED", "ANNOTATED")


def test_an_approval_without_a_research_run_is_reminded_and_stays_pending() -> None:
    limitation = {"response_type": "LIMITATION", "answer": "Belum dijalankan.", "clarification_question": None,
                  "assumptions": [], "limitations": ["x"], "research_plan": None, "research_findings": None}
    result, scripted, sandbox, issued = approved_run([final_response(limitation), final_response(limitation)])
    assert "start_research_run" in str(scripted.payloads[1]["input"][-1])
    assert result.execution.research_plan.research_submitted is False and sandbox.calls == []
    assert result.continuation.token == issued.token and result.continuation.research_data_plan == \
        issued.research_data_plan
    state = {"research_plan": {"plan_id": issued.plan_id, "status": "PENDING", "expires_at": issued.expires_at}}
    assert advance(state, result, "run_002", 1)["research_plan"]["status"] == "PENDING"


def test_a_v1_continuation_is_never_executed_while_multi_angle_is_active() -> None:
    from test_research_plan import continuation as continuation_v1, plan as plan_v1, signer as signer_v1
    from app.research_plan import ResearchPlan

    issued = signer_v1().issue(ResearchPlan.model_validate(plan_v1()), "run_001", "conv_1")
    runner, _, sandbox = agent([final_response(plan_response())])
    result = runner.run(AgentRunRequest(request_id="run_002", conversation_id="conv_1", message="Setuju.",
                                        continuation=continuation_v1(issued, action="APPROVE")))
    assert result.execution.research_plan.turn == "REPLAN"
    assert result.execution.research_plan.verification == "RESEARCH_PLAN_TOKEN_INVALID" and sandbox.calls == []


def test_the_server_keeps_a_v2_plan_with_its_data_plan() -> None:
    runner, _, _ = agent([call("check_research_feasibility", feasibility_args(), "c1"), final_response(plan_response())])
    result = runner.run(AgentRunRequest(request_id="run_001", conversation_id="conv_1", message=QUESTION))
    state = advance({}, result, "run_001", 0)
    stored = state["research_plan"]
    assert stored["research_data_plan"] == result.continuation.research_data_plan
    request = AgentRunRequest(request_id="run_002", conversation_id="conv_1", message="Setuju.",
                              history_mode="SERVER")
    rebuilt = continuation_for(state, request, now=NOW)
    assert isinstance(rebuilt, ContinuationInV2)
    assert signer().verify(rebuilt, "conv_1").plan_id == result.continuation.plan_id


# ---------------------------------------------------------------- the executor

def executor(run_sandbox: RunSandbox, bundles: BundlePlanner | None = None, dp: dict[str, Any] | None = None):
    dp = dp or data_plan()
    s = signer()
    issued = s.issue(ResearchPlanV2.model_validate(plan_v2()), dp, "run_001", None)
    verified = s.verify(ContinuationInV2.model_validate(continuation(issued)), None)
    client = SandboxClient("http://sandbox.test", "s" * 40, 10, 0, transport=httpx.MockTransport(run_sandbox.handler))
    return ResearchRunExecutor(client, bundles or BundlePlanner(), verified, "run_002", execution_timeout=10,
                               timeout=10, max_result_bytes=120000)


def two_groups() -> dict[str, Any]:
    rows = {"Price_Stock_Indonesia_IDX": 900_000, "Index_Price_IDX": 900_000, "Broker_Table": 900_000}
    args = feasibility_args([
        requirement("a_fall", request("a_fall_A")),
        requirement("a_rank", request("a_rank_A", table="Index_Price_IDX", name="index_prices")),
        requirement("a_lag", request("a_lag_A", table="Broker_Table", name="brokers"))])
    return run_plan(planner(rows=rows)[0], args)["data_plan"]


def test_the_executor_runs_groups_one_at_a_time_and_records_unrun_groups_as_not_run() -> None:
    sandbox = RunSandbox(complete_status="INCOMPLETE")
    run = executor(sandbox, dp=two_groups())
    token = current_request_id.set("run_002")
    try:
        started = run.start()
        assert started["status"] == "STARTED" and [g["status"] for g in started["groups"]] == ["RUNNING", "READY"]
        assert run.run("g1", "x")["status"] == "OK"
        # moving to g2 completes g1 first; an incomplete g1 refuses the switch
        refused = run.run("g2", "y")
        assert refused["code"] == "OPEN_GROUP_INCOMPLETE" and refused["open_bundle_group_id"] == "g1"
        assert run.complete(False)["status"] == "INCOMPLETE"
        sandbox.complete_status = "COMPLETED"
        pending = run.complete(False)
        assert pending["status"] == "INCOMPLETE" and pending["groups_not_run"] == ["g2"]
        done = run.complete(True)
    finally:
        current_request_id.reset(token)
    closes = [path for method, path, _ in sandbox.calls if path.endswith("/close")]
    assert closes == [f"/v1/research-runs/{RUN}/groups/g2/close"]
    assert [c[2]["reason"] for c in sandbox.calls if c[1].endswith("/close")] == ["NOT_RUN_BY_MODEL"]
    assert done["status"] == "COMPLETED" and done["angle_completion"] == {"planned": 3, "validated": 2, "missing": 0,
                                                                          "invalid": 0, "not_run": 1}
    assert done["calculation_validation"] == "STATISTICS_VERIFIED"
    assert sandbox.sessions == 1 and run.open_sessions() == []


def test_a_group_whose_bundle_fails_is_closed_and_the_next_group_opens() -> None:
    sandbox = RunSandbox()
    run = executor(sandbox, bundles=BundlePlanner(fail={"need_" + "0" * 24}), dp=two_groups())
    token = current_request_id.set("run_002")
    try:
        started = run.start()
    finally:
        current_request_id.reset(token)
    assert [g["status"] for g in started["groups"]] == ["FAILED", "RUNNING"]
    assert started["groups"][0]["reason"] == "SCAN_LIMIT"


def test_the_synthesis_map_is_an_evidence_map_not_a_vote() -> None:
    plan = ResearchPlanV2.model_validate(plan_v2())
    same_outcome = synthesis_map(plan, data_plan(), [
        finding("a_fall", "SUPPORTED", "STATISTICS_VERIFIED"),
        finding("a_rank", "INSUFFICIENT_EVIDENCE", "STATISTICS_VERIFIED", "OPPOSITE"),
        finding("a_lag", "SUPPORTED", "STATISTICS_VERIFIED")], [])
    assert same_outcome["supported"] == ["a_fall", "a_lag"] and same_outcome["agreement"]["allowed"] is True
    assert same_outcome["direction_conflicts"][0]["angles"] == ["a_fall", "a_rank"]
    one_family = synthesis_map(plan, data_plan(), [finding("a_fall", "SUPPORTED", "STATISTICS_VERIFIED")], [])
    assert one_family["agreement"]["allowed"] is False and one_family["not_run"] == ["a_rank", "a_lag"]


def test_the_context_callback_keeps_only_a_feasible_data_plan() -> None:
    context = ResearchContext()
    token = current_research_context.set(context)
    try:
        remember_feasibility({"status": "NOT_FEASIBLE", "data_plan": None, "view": {"status": "NOT_FEASIBLE"}})
        assert context.feasible is None
        remember_feasibility({"status": "FEASIBLE", "data_plan": {"x": 1}, "view": {"status": "FEASIBLE"}})
        remember_feasibility({"status": "REVISION_REQUIRED", "data_plan": None, "view": {}})
    finally:
        current_research_context.reset(token)
    assert context.feasible == {"x": 1} and len(context.checks) == 3


def test_the_final_response_accepts_both_plan_and_findings_versions() -> None:
    v2 = FinalResponse.model_validate(plan_response())
    assert isinstance(v2.research_plan, ResearchPlanV2)
    answer = FinalResponse.model_validate(findings_answer())
    assert answer.research_findings[0].angle_id == "a_fall"
    too_many = findings_answer({f"a{i}": "NOT_RUN" for i in range(7)})
    with pytest.raises(ValueError):
        FinalResponse.model_validate(too_many)


def test_the_catalog_migration_adds_no_method_rows_and_matches_the_tool_definitions() -> None:
    from pathlib import Path

    from app.tools.request_data import GovernorClient

    sql = (Path(__file__).resolve().parents[3]
           / "database/migrations/20260929_001_multi_angle_research_catalog.sql").read_text()
    assert 'INSERT INTO public."AI_research_catalog"' not in sql and "RAISE EXCEPTION 'AI_research_catalog has no row" in sql
    t = httpx.MockTransport(lambda r: httpx.Response(404))
    registry = build_default_registry(
        object(), cursor_secret=b"x" * 32, governor_client=GovernorClient("http://g", "k" * 40, 90, transport=t),
        sandbox_client=SandboxClient("http://s", "s" * 40, 45, 20, transport=t), dataneed_enabled=True,
        plan_feasibility=True, composite_keys=True,
        multi_angle={"max_groups": 3, "min_angles": 3, "max_angles": 6, "limits": {}})
    for definition in registry.definitions():
        if definition["name"] in ("check_research_feasibility", "start_research_run", "run_research_code",
                                  "complete_research_run"):
            schema = json.dumps(definition["parameters"], sort_keys=True, separators=(",", ":")).replace("'", "''")
            assert f"'{schema}'::jsonb" in sql, f"{definition['name']} drifted from the migration"
