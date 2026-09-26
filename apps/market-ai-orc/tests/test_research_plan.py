"""Research Plan confirmation (AI_REQUIRE_RESEARCH_PLAN_CONFIRMATION, DataNeed flow).

The plan model and FinalResponse contract; the signed continuation (HMAC-SHA256 over canonical claims, injected clock);
the research execution guard inside submit_data_need_spec (a real tool with a mock sandbox transport, so "no sandbox
call" is observed at the HTTP boundary); the plan turns of the orchestrator (propose, approve, revise, re-plan,
cancel, unrelated) with explicit actions and the natural-language reply classifier; and the flag off."""
from __future__ import annotations

import copy
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from app.config import ConfigError
from app.orchestrator import (APPROVED_NOTE, CLASSIFIER_INSTRUCTIONS, DISCOVERY_TOOLS, PLAN_NOTE_PREFIX,
                              AgentOrchestrator, build_system_prompt)
from app.research_plan import (ContinuationIn, PlanSigner, PlanVerificationError, ResearchGuard, ResearchPlan,
                               canonical_json, current_research_guard, match_governance, plan_sha256)
from app.schemas import AgentRunRequest, FinalResponse
from app.tools import ToolRegistry, ToolSpec
from app.tools.analysis import SandboxClient, current_run_context, run_context
from app.tools.data_need import data_need_specs
from app.tools.request_data import current_request_id
from conftest import ScriptedClient, final_response, make_settings, tool_call_response, usage
from test_data_need_tool import ytd_arguments

KEY = "0f3c9a7e5b1d4c2a8e6f0b9d7c5a3e1f2b4d6c8a0e9f7b5d3c1a2e4f6b8d0c9a"
NOW = datetime(2026, 9, 26, 5, 0, tzinfo=timezone.utc)
NEED = "need_" + "1" * 24
BUNDLE = "bundle_" + "2" * 24
SESSION = "sess_" + "3" * 24
ON = {"AI_ENABLE_DATANEED": "true", "AI_REQUIRE_RESEARCH_PLAN_CONFIRMATION": "true",
      "AI_RESEARCH_PLAN_SIGNING_KEY": KEY, "AI_MAX_TOOL_ITERATIONS": "12", "AI_MAX_TOOL_CALLS": "12"}


def experiment(**overrides: Any) -> dict[str, Any]:
    body = {"experiment_id": "experiment_1", "hypothesis_id": "rsi_hammer",
            "hypothesis": "RSI(14) below 30 together with a hammer candle precedes a higher 5-day return.",
            "objective": "Measure the 5-day forward return after the signal against the baseline.",
            "condition": "RSI(14) below 30 and a hammer candle on the same day",
            "outcome": "Return over the next 5 trading days from the next open",
            "baseline": "The 5-day forward return of all other days of the same stocks",
            "candidate_count": 1, "pairwise_comparisons": 1, "multiple_testing_policy": "NONE",
            "holdout_required": True, "minimum_sample_value": 30, "minimum_sample_unit": "EVENTS"}
    body.update(overrides)
    return body


def plan(**overrides: Any) -> dict[str, Any]:
    body = {"plan_version": "research_plan/v1",
            "original_question": "Apakah RSI di bawah 30 dan hammer menghasilkan return lebih tinggi?",
            "objective": "Test whether the signal historically precedes higher returns.",
            "universe": "All IDX stocks with daily prices", "time_scope": "2021 to the latest date",
            "analysis_frequency": "daily", "experiments": [experiment()],
            "assumptions": ["Prices are as stored."], "limitations": ["A historical pattern, not a prediction."],
            "confirmation_question": "Setujui, ubah, atau batalkan rencana ini?"}
    body.update(overrides)
    return body


def governance(**overrides: Any) -> dict[str, Any]:
    e = experiment()
    body = {key: e[key] for key in ("hypothesis_id", "hypothesis", "objective", "condition", "outcome", "baseline",
                                    "candidate_count", "pairwise_comparisons", "multiple_testing_policy")}
    body.update(holdout={"data_request_id": "data_request_1_A", "range_id": "holdout"},
                minimum_sample={"value": 30, "unit": "EVENTS"}, followup_of=None)
    body.update(overrides)
    return body


def plan_response(answer: str = "Rencana riset: hipotesis RSI(14) di bawah 30 dan hammer, minimal 30 event.",
                  **overrides: Any) -> dict[str, Any]:
    return {"response_type": "RESEARCH_PLAN_CONFIRMATION", "answer": answer, "clarification_question": None,
            "assumptions": [], "limitations": [], "research_plan": plan(**overrides)}


def answer(text: str, kind: str = "ANSWER") -> dict[str, Any]:
    return {"response_type": kind, "answer": text, "clarification_question": None, "assumptions": [],
            "limitations": [] if kind == "ANSWER" else ["x"], "research_plan": None}


def clarification(question: str) -> dict[str, Any]:
    return {"response_type": "CLARIFICATION", "answer": "", "clarification_question": question, "assumptions": [],
            "limitations": [], "research_plan": None}


class Clock:
    def __init__(self, moment: datetime = NOW) -> None:
        self.moment = moment

    def __call__(self) -> datetime:
        return self.moment


def signer(clock: Clock | None = None, key: str = KEY, ttl: int = 3600) -> PlanSigner:
    return PlanSigner(key, ttl, clock or Clock())


def continuation(issued, the_plan: dict[str, Any] | None = None, **overrides: Any) -> dict[str, Any]:
    body = {"kind": "RESEARCH_PLAN", "plan_id": issued.plan_id, "origin_request_id": issued.origin_request_id,
            "plan": the_plan or plan(), "token": issued.token, "action": None, "revision_instruction": None}
    body.update(overrides)
    return body


# ---------------------------------------------------------------- the plan and the response contract

def test_a_plan_has_one_to_four_distinct_experiments() -> None:
    ResearchPlan.model_validate(plan())
    four = [experiment(experiment_id=f"experiment_{i}", hypothesis_id=f"h{i}") for i in range(4)]
    assert len(ResearchPlan.model_validate(plan(experiments=four)).experiments) == 4
    for bad in ([], four + [experiment(experiment_id="experiment_9", hypothesis_id="h9")],
                [experiment(), experiment(experiment_id="experiment_2")]):
        with pytest.raises(ValidationError):
            ResearchPlan.model_validate(plan(experiments=bad))


@pytest.mark.parametrize("change", [
    {"hypothesis_id": "Bad-Id"}, {"multiple_testing_policy": "NONE", "candidate_count": 3},
    {"minimum_sample_value": 30, "minimum_sample_unit": None}, {"candidate_count": 51}, {"condition": " "},
    {"condition": "SELECT close FROM Price_Stock_Indonesia_IDX"}, {"outcome": "df['close'].pct_change(5)"},
    {"baseline": "saniti.load('prices')"},
])
def test_an_invalid_or_code_bearing_experiment_is_rejected(change: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ResearchPlan.model_validate(plan(experiments=[experiment(**change)]))


def test_the_final_response_ties_the_plan_to_its_response_type() -> None:
    parsed = FinalResponse.model_validate(plan_response())
    assert parsed.research_plan is not None and parsed.research_plan.experiments[0].hypothesis_id == "rsi_hammer"
    with pytest.raises(ValidationError):
        FinalResponse.model_validate({**plan_response(), "research_plan": None})
    with pytest.raises(ValidationError):
        FinalResponse.model_validate({**answer("ok"), "research_plan": plan()})
    for kind in ("ANSWER", "CLARIFICATION", "LIMITATION"):
        body = answer("ok", kind) if kind != "CLARIFICATION" else clarification("Periode apa?")
        assert FinalResponse.model_validate(body).research_plan is None


# ---------------------------------------------------------------- signing and verification

def verify(sign: PlanSigner, issued, the_plan=None, conversation_id=None, **overrides):
    return sign.verify(ContinuationIn.model_validate(continuation(issued, the_plan, **overrides)), conversation_id)


def test_a_valid_token_verifies_and_carries_its_bindings() -> None:
    sign = signer()
    issued = sign.issue(ResearchPlan.model_validate(plan()), "run_001", "conv_1")
    assert issued.plan_id.startswith("rp_") and issued.kind == "RESEARCH_PLAN"
    assert issued.expires_at == (NOW + timedelta(seconds=3600)).isoformat()
    verified = verify(sign, issued, conversation_id="conv_1")
    assert verified.plan_id == issued.plan_id and verified.origin_request_id == "run_001"
    assert verified.plan_sha256 == plan_sha256(ResearchPlan.model_validate(plan()))


def test_canonical_json_is_order_independent() -> None:
    one = ResearchPlan.model_validate(plan())
    reordered = ResearchPlan.model_validate(json.loads(json.dumps(dict(reversed(list(plan().items()))))))
    assert plan_sha256(one) == plan_sha256(reordered)
    assert canonical_json({"b": 1, "a": "é"}) == '{"a":"é","b":1}'.encode()


@pytest.mark.parametrize("case, reason", [
    ("modified_plan", "PLAN_HASH"), ("modified_signature", "SIGNATURE"), ("modified_payload", "SIGNATURE"),
    ("wrong_origin", "ORIGIN"), ("wrong_plan_id", "PLAN_ID"), ("wrong_conversation", "CONVERSATION"),
    ("missing_bound_conversation", "CONVERSATION"), ("other_key", "SIGNATURE"), ("malformed", "FORMAT"),
    ("oversized", "FORMAT"),
])
def test_tampered_or_wrongly_bound_continuations_are_invalid(case: str, reason: str) -> None:
    sign = signer()
    issued = sign.issue(ResearchPlan.model_validate(plan()), "run_001", "conv_1")
    head, payload, signature = issued.token.split(".")
    kwargs: dict[str, Any] = {"conversation_id": "conv_1"}
    if case == "modified_plan":
        kwargs["the_plan"] = plan(experiments=[experiment(candidate_count=2, multiple_testing_policy="HOLM")])
    elif case == "modified_signature":
        kwargs["token"] = f"{head}.{payload}.{('A' if signature[0] != 'A' else 'B')}{signature[1:]}"
    elif case == "modified_payload":
        kwargs["token"] = f"{head}.{payload[:-2]}{'AA' if payload[-2:] != 'AA' else 'BB'}.{signature}"
    elif case == "wrong_origin":
        kwargs["origin_request_id"] = "run_999"
    elif case == "wrong_plan_id":
        kwargs["plan_id"] = "rp_" + "0" * 24
    elif case == "wrong_conversation":
        kwargs["conversation_id"] = "conv_2"
    elif case == "missing_bound_conversation":
        kwargs["conversation_id"] = None
    elif case == "other_key":
        kwargs["token"] = signer(key="f" * 20 + KEY[20:]).issue(ResearchPlan.model_validate(plan()), "run_001",
                                                                 "conv_1").token
    elif case == "malformed":
        kwargs["token"] = "rpc1.not-a-token"
    elif case == "oversized":
        kwargs["token"] = "rpc1." + "A" * 1990 + "." + "B" * 43
    with pytest.raises(PlanVerificationError) as raised:
        verify(sign, issued, **kwargs)
    assert raised.value.code == "RESEARCH_PLAN_TOKEN_INVALID" and raised.value.reason == reason
    assert issued.token not in str(raised.value) and KEY not in str(raised.value)


def test_a_token_beyond_the_request_limit_is_refused_by_the_request_schema() -> None:
    issued = signer().issue(ResearchPlan.model_validate(plan()), "run_001", None)
    with pytest.raises(ValidationError):
        ContinuationIn.model_validate(continuation(issued, token="rpc1." + "A" * 3000))


def test_expiry_uses_the_injected_clock() -> None:
    clock = Clock()
    sign = signer(clock, ttl=600)
    issued = sign.issue(ResearchPlan.model_validate(plan()), "run_001", None)
    clock.moment = NOW + timedelta(seconds=599)
    assert verify(sign, issued).plan_id == issued.plan_id
    clock.moment = NOW + timedelta(seconds=600)
    with pytest.raises(PlanVerificationError) as raised:
        verify(sign, issued)
    assert raised.value.code == "RESEARCH_PLAN_TOKEN_EXPIRED"
    clock.moment = NOW - timedelta(hours=1)  # issued "in the future" beyond the allowed skew
    with pytest.raises(PlanVerificationError) as raised:
        verify(sign, issued)
    assert raised.value.reason == "NOT_YET_VALID"


def test_no_conversation_bound_and_none_presented_is_valid() -> None:
    sign = signer()
    issued = sign.issue(ResearchPlan.model_validate(plan()), "run_001", None)
    assert verify(sign, issued, conversation_id=None).conversation_id is None
    with pytest.raises(PlanVerificationError):
        verify(sign, issued, conversation_id="conv_late")  # exact equality, including None


def test_a_stateless_token_can_be_replayed_until_it_expires() -> None:
    """Documented limitation: without persistence a still-valid token is not revoked by a later plan."""
    sign = signer()
    first = sign.issue(ResearchPlan.model_validate(plan()), "run_001", None)
    sign.issue(ResearchPlan.model_validate(plan(objective="A revised objective.")), "run_002", None)
    assert verify(sign, first).plan_id == first.plan_id
    assert verify(sign, first).plan_id == first.plan_id


@pytest.mark.parametrize("env, message", [
    ({}, "is required"), ({"AI_RESEARCH_PLAN_SIGNING_KEY": "short"}, "at least 32"),
    ({"AI_RESEARCH_PLAN_SIGNING_KEY": "ab" * 32}, "too weak"),
    ({"AI_RESEARCH_PLAN_SIGNING_KEY": " " + KEY}, "surrounding whitespace"),
    ({"AI_RESEARCH_PLAN_SIGNING_KEY": KEY, "AI_RESEARCH_PLAN_TTL_SECONDS": "90000"}, "at most"),
    ({"AI_RESEARCH_PLAN_SIGNING_KEY": KEY, "AI_RESEARCH_PLAN_TTL_SECONDS": "30"}, "at least 60"),
])
def test_startup_fails_without_a_usable_signing_key_or_ttl(env: dict[str, str], message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        make_settings(AI_REQUIRE_RESEARCH_PLAN_CONFIRMATION="true", **env)


def test_the_flags_default_off_and_the_key_never_appears_in_reprs() -> None:
    settings = make_settings()
    assert settings.ai_require_research_plan_confirmation is False and settings.ai_enable_standard_period_return is False
    assert settings.ai_research_plan_ttl_seconds == 3600
    configured = make_settings(**ON)
    assert KEY not in repr(configured) and KEY not in repr(signer())


# ---------------------------------------------------------------- the guard (declaration matching)

APPROVED = ResearchPlan.model_validate(plan())


@pytest.mark.parametrize("field", ["hypothesis", "objective", "condition", "outcome", "baseline"])
def test_a_changed_declaration_is_a_mismatch(field: str) -> None:
    refused = match_governance(governance(**{field: "Something else entirely."}), APPROVED, "rp_x")
    assert refused["status"] == "REJECTED" and refused["error"]["code"] == "RESEARCH_PLAN_MISMATCH"
    [issue] = refused["error"]["issues"]
    assert issue["field_path"] == f"research_governance.{field}" and issue["experiment_id"] == "experiment_1"
    assert issue["rule"] == "EXACT_MATCH" and refused["extraction_allowed"] is False


def test_a_missing_declaration_is_a_mismatch_but_case_and_spacing_are_not() -> None:
    assert match_governance(governance(condition=None), APPROVED)["error"]["issues"][0]["field_path"] == \
        "research_governance.condition"
    relaxed = governance(hypothesis="  rsi(14) BELOW 30 together   with a hammer candle precedes a higher 5-day "
                                    "return.  ")
    assert match_governance(relaxed, APPROVED) is None


def test_an_unknown_hypothesis_requires_reapproval() -> None:
    refused = match_governance(governance(hypothesis_id="momentum"), APPROVED)
    assert refused["error"]["code"] == "RESEARCH_PLAN_REAPPROVAL_REQUIRED"
    assert refused["next_action"] == "RETURN_RESEARCH_PLAN_CONFIRMATION"
    assert refused["error"]["issues"][0]["approved_value"] == ["rsi_hammer"]


@pytest.mark.parametrize("changes, accepted", [
    ({"candidate_count": 2, "multiple_testing_policy": "NONE"}, False),        # more candidates
    ({"pairwise_comparisons": 2}, False),                                      # more comparisons
    ({"pairwise_comparisons": 0}, True),                                       # fewer comparisons
    ({"multiple_testing_policy": "BONFERRONI"}, False),                        # no policy ordering is assumed
    ({"minimum_sample": {"value": 20, "unit": "EVENTS"}}, False),               # smaller sample
    ({"minimum_sample": {"value": 30, "unit": "OBSERVATIONS"}}, False),         # another unit
    ({"minimum_sample": None}, False),                                         # sample removed
    ({"minimum_sample": {"value": 100, "unit": "EVENTS"}}, True),               # larger sample
    ({"holdout": None}, False),                                                # required holdout removed
])
def test_only_conservative_tightening_passes_without_reapproval(changes: dict[str, Any], accepted: bool) -> None:
    result = match_governance(governance(**changes), APPROVED)
    assert (result is None) is accepted, result


def test_fewer_candidates_and_an_added_holdout_pass() -> None:
    wide = ResearchPlan.model_validate(plan(experiments=[experiment(candidate_count=5, pairwise_comparisons=5,
                                                                    multiple_testing_policy="HOLM",
                                                                    holdout_required=False)]))
    assert match_governance(governance(candidate_count=3, pairwise_comparisons=3, multiple_testing_policy="HOLM"),
                            wide) is None
    assert match_governance(governance(candidate_count=6, multiple_testing_policy="HOLM"), wide) is not None
    assert match_governance(governance(multiple_testing_policy="HOLM", holdout=None), wide) is None  # not required


# ---------------------------------------------------------------- the guard inside the real tool

class Sandbox:
    """The sandbox HTTP boundary of submit_data_need_spec: every call is recorded."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b"null")
        self.calls.append({"path": request.url.path, "body": body})
        mode = body["spec"]["mode"]
        return httpx.Response(200, json={
            "status": "APPROVED", "need_id": NEED, "request_group_id": body["spec"]["request_group_id"],
            "revision": body["spec"]["revision"], "issues": [], "warnings": [], "extraction_allowed": True,
            "next_action": "PREPARE_DATA_BUNDLE", "research_governance": {"decision": "APPROVED"} if mode == "RESEARCH"
            else {"decision": "NOT_APPLICABLE"}})


def research_arguments(**overrides: Any) -> dict[str, Any]:
    arguments = ytd_arguments(mode="RESEARCH", research_governance=governance(**overrides))
    arguments["data_requests"][0]["time_ranges"].append({"range_id": "holdout", "start": "2026-07-01",
                                                          "end": "2026-09-25"})
    return arguments


def tool_call(sandbox: Sandbox, arguments: dict[str, Any], guard: ResearchGuard | None):
    registry = ToolRegistry()
    client = SandboxClient("http://sandbox.test", "s" * 40, 10, 0, transport=httpx.MockTransport(sandbox.handler))
    for spec in data_need_specs(client, timeout_seconds=10, max_result_bytes=40000):
        registry.register(spec)
    tokens = (current_request_id.set("run_2"), current_research_guard.set(guard),
              current_run_context.set(run_context(NOW, "Asia/Jakarta", [], "q")))
    try:
        return registry.execute("c1", "submit_data_need_spec", json.dumps(arguments))
    finally:
        current_request_id.reset(tokens[0])
        current_research_guard.reset(tokens[1])
        current_run_context.reset(tokens[2])


def test_research_without_an_approved_plan_never_reaches_the_sandbox() -> None:
    sandbox = Sandbox()
    outcome = tool_call(sandbox, research_arguments(), ResearchGuard(required=True))
    result = outcome.output["result"]
    assert result["status"] == "REJECTED" and result["error"]["code"] == "RESEARCH_PLAN_REQUIRED"
    assert result["next_action"] == "RETURN_RESEARCH_PLAN_CONFIRMATION" and sandbox.calls == []
    expired = tool_call(sandbox, research_arguments(),
                        ResearchGuard(required=True, verification="RESEARCH_PLAN_TOKEN_EXPIRED"))
    assert expired.output["result"]["error"]["code"] == "RESEARCH_PLAN_TOKEN_EXPIRED" and sandbox.calls == []


def test_an_approved_matching_experiment_reaches_the_data_need_endpoint_with_its_declarations() -> None:
    sandbox = Sandbox()
    outcome = tool_call(sandbox, research_arguments(), ResearchGuard(required=True, plan=APPROVED, plan_id="rp_1"))
    assert outcome.output["result"]["need_id"] == NEED
    [sent] = sandbox.calls
    assert sent["path"] == "/v1/data-needs"
    assert sent["body"]["research_governance"]["condition"] == experiment()["condition"]
    mismatched = tool_call(sandbox, research_arguments(outcome="The 20-day return instead."),
                           ResearchGuard(required=True, plan=APPROVED, plan_id="rp_1"))
    assert mismatched.output["result"]["error"]["code"] == "RESEARCH_PLAN_MISMATCH" and len(sandbox.calls) == 1


def test_analysis_mode_and_the_flag_off_are_unaffected() -> None:
    sandbox = Sandbox()
    assert tool_call(sandbox, ytd_arguments(), ResearchGuard(required=True)).output["result"]["need_id"] == NEED
    off = research_arguments(condition=None, outcome=None, baseline=None)
    assert tool_call(sandbox, off, ResearchGuard(required=False)).output["result"]["need_id"] == NEED
    assert tool_call(sandbox, off, None).output["result"]["need_id"] == NEED
    assert len(sandbox.calls) == 3
    # null declarations are not sent, so a sandbox without them accepts the request unchanged
    assert set(sandbox.calls[-1]["body"]["research_governance"]) & {"condition", "outcome", "baseline"} == set()


# ---------------------------------------------------------------- the orchestrator turns

class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoArgs(Strict):
    pass


class NeedArgs(Strict):
    need_id: str


class BundleArgs(Strict):
    input_bundle_id: str


def registry(sandbox: Sandbox) -> ToolRegistry:
    registry = ToolRegistry()
    client = SandboxClient("http://sandbox.test", "s" * 40, 10, 0, transport=httpx.MockTransport(sandbox.handler))
    for spec in data_need_specs(client, timeout_seconds=10, max_result_bytes=40000):
        registry.register(spec)
    registry.register(ToolSpec(name="discover_catalog", description="discover", arguments_model=NoArgs,
                               handler=lambda a: {"tables": ["Price_Stock_Indonesia_IDX"]}))
    registry.register(ToolSpec(name="prepare_data_bundle", description="bundle", arguments_model=NeedArgs,
                               handler=lambda a: {"status": "READY", "input_bundle_id": BUNDLE, "datasets": []}))
    registry.register(ToolSpec(name="open_analysis_session", description="open", arguments_model=BundleArgs,
                               handler=lambda a: {"session_id": SESSION, "status": "ACTIVE", "need_id": NEED}))
    return registry


def call(name: str, arguments: dict[str, Any], call_id: str) -> dict[str, Any]:
    return tool_call_response(name, json.dumps(arguments), call_id=call_id)


def classifier(action: str, instruction: str | None = None) -> dict[str, Any]:
    return final_response({"action": action, "revision_instruction": instruction}, response_id="resp_classifier")


def orchestrator(script: list, sandbox: Sandbox, clock: Clock | None = None, auditor: Any = None, **env: str):
    scripted = ScriptedClient(script)
    settings = make_settings(**{**ON, **env})
    return AgentOrchestrator(settings, scripted, registry(sandbox), wall_clock=clock or Clock(),
                             auditor=auditor), scripted


def first_turn(sandbox: Sandbox, clock: Clock | None = None):
    agent, scripted = orchestrator([call("discover_catalog", {}, "c1"), final_response(plan_response())], sandbox,
                                   clock)
    result = agent.run(AgentRunRequest(request_id="run_001", conversation_id="conv_1",
                                       message="Apakah RSI di bawah 30 dan hammer menghasilkan return lebih tinggi?"))
    return result, scripted


def reply(sandbox: Sandbox, issued, script: list, message: str = "Setuju, lanjutkan.", clock: Clock | None = None,
          request_id: str = "run_002", conversation_id: str | None = "conv_1", **continuation_fields: Any):
    agent, scripted = orchestrator(script, sandbox, clock)
    body = continuation(issued, **continuation_fields)
    result = agent.run(AgentRunRequest(request_id=request_id, conversation_id=conversation_id, message=message,
                                       history=[{"role": "user", "content": "Apakah RSI di bawah 30?"},
                                                {"role": "assistant", "content": "Rencana riset: ... Setujui?"}],
                                       continuation=body))
    return result, scripted


def test_a_research_question_returns_a_signed_plan_and_touches_no_data() -> None:
    sandbox = Sandbox()
    result, scripted = first_turn(sandbox)
    assert result.status == "AWAITING_CONFIRMATION" and result.response.response_type == "RESEARCH_PLAN_CONFIRMATION"
    assert result.response.research_plan.experiments[0].hypothesis_id == "rsi_hammer"
    issued = result.continuation
    assert issued is not None and issued.plan_id.startswith("rp_") and issued.origin_request_id == "run_001"
    assert issued.conversation_id == "conv_1" and issued.token.startswith("rpc1.")
    assert sandbox.calls == [] and "submit_data_need_spec" not in json.dumps(
        [item for payload in scripted.payloads for item in payload["input"] if item.get("type") == "function_call"])
    meta = result.execution.research_plan
    assert meta.turn == "PROPOSE" and meta.verification == "NOT_PRESENTED" and meta.issued_plan_id == issued.plan_id
    assert result.evidence_label is None
    # the model never produced the id or token: they are not in anything it was sent or returned
    assert issued.token not in json.dumps(scripted.payloads)
    assert "RESEARCH PLAN CONFIRMATION" in scripted.payloads[0]["instructions"]


def test_a_normal_analysis_response_has_no_continuation() -> None:
    sandbox = Sandbox()
    agent, _ = orchestrator([call("submit_data_need_spec", ytd_arguments(), "c1"),
                             final_response(answer("Data siap."))], sandbox)
    result = agent.run(AgentRunRequest(request_id="run_a", message="Ambil data YTD bank."))
    assert result.status == "COMPLETED" and result.continuation is None and len(sandbox.calls) == 1
    assert result.response.research_plan is None and result.execution.research_plan.turn == "PROPOSE"


def test_a_direct_research_call_before_approval_is_refused_without_a_sandbox_call() -> None:
    sandbox = Sandbox()
    agent, scripted = orchestrator([call("submit_data_need_spec", research_arguments(), "c1"),
                                    final_response(plan_response())], sandbox)
    result = agent.run(AgentRunRequest(request_id="run_b", message="Uji RSI < 30 + hammer."))
    output = json.loads(next(item["output"] for item in scripted.payloads[1]["input"]
                             if item.get("type") == "function_call_output"))
    assert output["result"]["error"]["code"] == "RESEARCH_PLAN_REQUIRED" and sandbox.calls == []
    assert result.status == "AWAITING_CONFIRMATION" and result.execution.research_plan.guard_rejections == 1


def test_an_explicit_approval_runs_the_approved_experiment_without_a_classifier_call() -> None:
    sandbox = Sandbox()
    issued = first_turn(sandbox)[0].continuation
    result, scripted = reply(sandbox, issued, [
        call("submit_data_need_spec", research_arguments(), "c1"),
        call("prepare_data_bundle", {"need_id": NEED}, "c2"),
        final_response(answer("Data riset sudah disiapkan; analisis belum dijalankan.", "LIMITATION"))],
        action="APPROVE")
    assert len(sandbox.calls) == 1 and sandbox.calls[0]["body"]["spec"]["mode"] == "RESEARCH"
    assert scripted.payloads[0]["instructions"] != CLASSIFIER_INSTRUCTIONS and "tools" in scripted.payloads[0]
    notes = [item["content"] for item in scripted.payloads[0]["input"] if isinstance(item.get("content"), str)
             and item["content"].startswith(PLAN_NOTE_PREFIX)]
    assert len(notes) == 1 and issued.plan_id in notes[0] and "approved" in notes[0]
    meta = result.execution.research_plan
    assert (meta.turn, meta.verification, meta.action, meta.action_source, meta.approved_plan_id) == (
        "EXECUTE_APPROVED", "VERIFIED", "APPROVE", "EXPLICIT", issued.plan_id)
    assert meta.classifier is None and result.continuation is None


def test_an_approved_run_still_refuses_a_hypothesis_outside_the_plan() -> None:
    sandbox = Sandbox()
    issued = first_turn(sandbox)[0].continuation
    result, scripted = reply(sandbox, issued, [
        call("submit_data_need_spec", research_arguments(hypothesis_id="momentum"), "c1"),
        final_response(answer("Hipotesis itu tidak ada di rencana yang disetujui.", "LIMITATION"))],
        action="APPROVE")
    assert sandbox.calls == [] and result.execution.research_plan.guard_rejections == 1


@pytest.mark.parametrize("case", ["tampered", "expired", "wrong_conversation"])
def test_an_unverifiable_approval_authorizes_nothing_and_asks_again(case: str) -> None:
    sandbox, clock = Sandbox(), Clock()
    issued = first_turn(sandbox, clock)[0].continuation
    fields: dict[str, Any] = {"action": "APPROVE"}
    conversation = "conv_1"
    if case == "tampered":
        fields["the_plan"] = plan(experiments=[experiment(candidate_count=40, multiple_testing_policy="HOLM")])
    elif case == "expired":
        clock.moment = NOW + timedelta(hours=2)
    else:
        conversation = "conv_other"
    result, scripted = reply(sandbox, issued, [
        call("submit_data_need_spec", research_arguments(), "c1"),
        final_response(plan_response())], clock=clock, conversation_id=conversation, **fields)
    outputs = [json.loads(item["output"]) for payload in scripted.payloads for item in payload["input"]
               if item.get("type") == "function_call_output"]
    assert outputs[0]["error"]["code"] == "TOOL_NOT_AVAILABLE_IN_THIS_TURN" and sandbox.calls == []
    offered = {tool["name"] for tool in scripted.payloads[0]["tools"]}
    assert offered <= DISCOVERY_TOOLS and "submit_data_need_spec" not in offered
    meta = result.execution.research_plan
    expected = "RESEARCH_PLAN_TOKEN_EXPIRED" if case == "expired" else "RESEARCH_PLAN_TOKEN_INVALID"
    assert (meta.turn, meta.verification) == ("REPLAN", expected)
    # a new plan is issued for a new approval
    assert result.status == "AWAITING_CONFIRMATION" and result.continuation.plan_id != issued.plan_id


def test_revise_returns_a_new_signed_plan_without_data_tools() -> None:
    sandbox = Sandbox()
    issued = first_turn(sandbox)[0].continuation
    revised = plan_response(time_scope="Lima tahun terakhir")
    result, scripted = reply(sandbox, issued, [final_response(revised)], message="Ubah periodenya.",
                             action="REVISE", revision_instruction="Ubah periode menjadi lima tahun.")
    assert {t["name"] for t in scripted.payloads[0]["tools"]} <= DISCOVERY_TOOLS
    note = next(item["content"] for item in scripted.payloads[0]["input"] if isinstance(item.get("content"), str)
                and item["content"].startswith(PLAN_NOTE_PREFIX))
    assert "Ubah periode menjadi lima tahun." in note and issued.plan_id in note
    assert result.status == "AWAITING_CONFIRMATION" and result.continuation.plan_id != issued.plan_id
    assert result.response.research_plan.time_scope == "Lima tahun terakhir" and sandbox.calls == []


def test_cancel_stops_without_tools_and_without_a_plan() -> None:
    sandbox = Sandbox()
    issued = first_turn(sandbox)[0].continuation
    result, scripted = reply(sandbox, issued, [final_response(plan_response()),
                                               final_response(answer("Baik, rencana riset dibatalkan."))],
                             message="Batal.", action="CANCEL")
    assert "tools" not in scripted.payloads[0] and scripted.payloads[0]["text"]["format"]["strict"] is True
    assert result.status == "COMPLETED" and result.response.answer == "Baik, rencana riset dibatalkan."
    assert result.continuation is None and sandbox.calls == []
    assert "not allowed here" in json.dumps(scripted.payloads[1]["input"])  # a plan in a cancel turn is refused


@pytest.mark.parametrize("action, instruction, expected_turn", [
    ("APPROVE", None, "EXECUTE_APPROVED"), ("REVISE", "Pakai lima tahun.", "REVISE"), ("CANCEL", None, "CANCEL"),
    ("UNRELATED", None, "UNRELATED")])
def test_a_free_text_reply_is_classified_by_a_small_tool_free_call(action: str, instruction: str | None,
                                                                    expected_turn: str) -> None:
    sandbox = Sandbox()
    issued = first_turn(sandbox)[0].continuation
    final = {"EXECUTE_APPROVED": answer("Siap.", "LIMITATION"), "REVISE": plan_response(),
             "CANCEL": answer("Dibatalkan."), "UNRELATED": clarification("Setujui, ubah, atau batalkan rencananya?")}
    result, scripted = reply(sandbox, issued, [classifier(action, instruction), final_response(final[expected_turn])],
                             message="Oke, tetapi ubah periodenya." if action == "REVISE" else "hmm")
    first = scripted.payloads[0]
    assert first["instructions"] == CLASSIFIER_INSTRUCTIONS and "tools" not in first
    assert first["text"]["format"]["schema"]["properties"]["action"]["enum"] == ["APPROVE", "REVISE", "CANCEL",
                                                                                 "UNRELATED"]
    assert issued.token not in json.dumps(first)  # the classifier sees the plan digest and the reply only
    meta = result.execution.research_plan
    assert meta.turn == expected_turn and meta.action_source == "CLASSIFIER" and meta.classifier.status == "COMPLETED"
    assert meta.classifier.input_tokens == usage()["input_tokens"]
    assert result.execution.input_tokens == 2 * usage()["input_tokens"]  # the classifier is in the run totals
    if expected_turn == "UNRELATED":
        assert result.status == "NEEDS_CLARIFICATION"
        # the same continuation comes back unchanged: asking again never extends the plan
        assert result.continuation.token == issued.token and result.continuation.expires_at == issued.expires_at


def test_a_failed_classification_never_approves() -> None:
    sandbox = Sandbox()
    issued = first_turn(sandbox)[0].continuation
    result, _ = reply(sandbox, issued, [final_response("not json", response_id="resp_classifier"),
                                        final_response(clarification("Setujui, ubah, atau batalkan?"))],
                      message="ya mungkin")
    meta = result.execution.research_plan
    assert meta.turn == "UNRELATED" and meta.classifier.status == "FAILED" and sandbox.calls == []


def test_a_plan_answer_may_cite_only_the_plan_and_the_user() -> None:
    sandbox = Sandbox()
    agent, scripted = orchestrator([final_response(plan_response(answer="Rencana: minimal 30 event, target 12,5%.")),
                                    final_response(plan_response())], sandbox)
    result = agent.run(AgentRunRequest(request_id="run_c", message="Uji RSI < 30 + hammer."))
    assert "12,5" in json.dumps(scripted.payloads[1]["input"])  # rejected once with the unsupported number
    assert result.status == "AWAITING_CONFIRMATION" and result.execution.number_provenance.unsupported == []


def test_plan_confirmation_is_audited_with_its_status() -> None:
    class Auditor:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def record(self, request_id, question, result, experiments, used_sandbox):
            self.calls.append({"status": result.status, "type": result.response.response_type,
                               "used_sandbox": used_sandbox})

    sandbox, auditor = Sandbox(), Auditor()
    agent, _ = orchestrator([final_response(plan_response())], sandbox, auditor=auditor)
    agent.run(AgentRunRequest(request_id="run_d", message="Uji RSI < 30 + hammer."))
    assert auditor.calls == [{"status": "AWAITING_CONFIRMATION", "type": "RESEARCH_PLAN_CONFIRMATION",
                              "used_sandbox": False}]


def test_logs_never_contain_the_key_or_a_token() -> None:
    records: list[str] = []

    class Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    logger = logging.getLogger("market_ai_orc")
    handler, level = Collect(), logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        sandbox = Sandbox()
        issued = first_turn(sandbox)[0].continuation
        reply(sandbox, issued, [final_response(plan_response())], action="APPROVE",
              the_plan=plan(objective="tampered"))
    finally:
        logger.removeHandler(handler)
        logger.setLevel(level)
    text = "\n".join(records)
    assert KEY not in text and issued.token not in text and issued.token.split(".")[2] not in text
    assert "research_plan_verification_failed" in text and "PLAN_HASH" in text
    assert "research_plan_issued" in text


# ---------------------------------------------------------------- flag off

def test_without_the_flag_research_runs_as_before_and_a_continuation_is_ignored() -> None:
    sandbox = Sandbox()
    off = {"AI_REQUIRE_RESEARCH_PLAN_CONFIRMATION": "false", "AI_RESEARCH_PLAN_SIGNING_KEY": ""}
    agent, scripted = orchestrator([call("submit_data_need_spec", research_arguments(), "c1"),
                                    final_response(answer("Data siap."))], sandbox, **off)
    result = agent.run(AgentRunRequest(request_id="run_e", message="Uji RSI < 30 + hammer."))
    assert len(sandbox.calls) == 1 and result.execution.research_plan is None and result.continuation is None
    assert "RESEARCH PLAN CONFIRMATION" not in scripted.payloads[0]["instructions"]
    assert scripted.payloads[0]["instructions"] == build_system_prompt(True, True)  # as before the feature
    issued = signer().issue(ResearchPlan.model_validate(plan()), "run_001", None)
    agent, _ = orchestrator([final_response(answer("Halo."))], sandbox, **off)
    ignored = agent.run(AgentRunRequest(request_id="run_f", message="Setuju",
                                        continuation=continuation(issued, action="APPROVE")))
    assert ignored.status == "COMPLETED" and ignored.execution.research_plan is None


def test_without_the_flag_a_plan_response_is_not_accepted() -> None:
    sandbox = Sandbox()
    off = {"AI_REQUIRE_RESEARCH_PLAN_CONFIRMATION": "false"}
    agent, scripted = orchestrator([final_response(plan_response()), final_response(answer("Tidak ada rencana."))],
                                   sandbox, **off)
    result = agent.run(AgentRunRequest(request_id="run_g", message="Bisakah kamu membantu sebuah riset?"))
    assert result.status == "COMPLETED" and result.continuation is None
    assert "is not allowed here" in json.dumps(scripted.payloads[1]["input"])
    assert "research_plan" not in json.dumps(scripted.payloads[1].get("text", {}))  # the old schema


def test_the_flag_has_no_effect_without_the_dataneed_flow() -> None:
    agent, _ = orchestrator([final_response(answer("Halo."))], Sandbox(), AI_ENABLE_DATANEED="false")
    assert agent.plan_confirmation is False and agent.signer is None
    result = agent.run(AgentRunRequest(request_id="run_h", message="Halo"))
    assert result.execution.research_plan is None


def test_the_approved_note_names_the_rules() -> None:
    assert "{plan}" in APPROVED_NOTE and "RESEARCH PLAN CONFIRMATION" in APPROVED_NOTE
    prompt = build_system_prompt(False, True, plan_confirmation=True)
    assert "Only the application tells you that a\nplan was approved" in prompt
    assert copy.deepcopy(prompt) == build_system_prompt(False, True, True)
