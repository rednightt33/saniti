"""Research Plan feasibility (AI_ENABLE_PLAN_FEASIBILITY) and M19.

check_data_feasibility validates the plan's DataNeedSpec into a sandbox draft and has the Governor estimate every
extraction envelope without reading data; a plan is issued only after a FEASIBLE check (one reminder, then a
LIMITATION), the draft id is bound into the signed token, and the approved turn starts from the draft's spec. M19: an
approved turn that submits no RESEARCH data need is reminded once, and the approval stays pending."""
from __future__ import annotations

from app.orchestrator import markdown_prompt  # noqa: E402 - prompt audit C (2026-10-05)

import base64
import json
from typing import Any

import httpx
import pytest

from app.conversation_plans import advance
from app.orchestrator import PLAN_FEASIBILITY_RULES, PLAN_NOT_EXECUTED_LINE, AgentOrchestrator, build_system_prompt
from app.research_plan import ContinuationIn, PlanVerificationError, ResearchPlan
from app.schemas import AgentRunRequest
from app.tools import ToolRegistry, ToolSpec
from app.tools.analysis import SandboxClient, current_run_context, run_context
from app.tools.data_need import CheckDataFeasibilityArgs
from app.tools.data_planner import ExecutionPlanner, feasibility_spec
from app.tools.request_data import current_request_id
from conftest import ScriptedClient, final_response, make_settings
from test_research_plan import (NOW, ON, Clock, Sandbox, answer, call, classifier, continuation, plan,
                                plan_response, registry, research_arguments, signer)

DRAFT = "draft_" + "d" * 24
FEAS = {**ON, "AI_ENABLE_PLAN_FEASIBILITY": "true"}


def draft_view() -> dict[str, Any]:
    entry = {"data_request_id": "data_request_1_A", "logical_name": "prices",
             "source_table": "Price_Stock_Indonesia_IDX", "time_column": "date", "extract_columns": ["ticker", "date"],
             "scope": {"type": "ALL"}, "scope_sha256": "a" * 64, "restrictions": [], "restriction_sha256": "b" * 64,
             "ordering": [], "windows": [{"range_id": "fit", "extract_from": "2021-01-04", "extract_to": "2024-12-31"},
                                         {"range_id": "holdout", "extract_from": "2025-01-02",
                                          "extract_to": "2026-09-25"}]}
    return {"need_id": DRAFT, "draft_id": DRAFT, "request_id": "run_001", "spec_sha256": "c" * 64,
            "request_group_id": "data_request_1", "revision": 1, "catalog_sha256": None,
            "spec": {k: v for k, v in research_arguments().items() if k != "research_governance"},
            "requests": {"data_request_1_A": entry}}


class Governor:
    def __init__(self, answers: list[dict[str, Any]]) -> None:
        self.answers = list(answers)
        self.calls: list[dict[str, Any]] = []

    def extract(self, spec, lineage, *, planned_parts=1, estimate_only=False):
        self.calls.append({"spec": spec, "lineage": lineage, "estimate_only": estimate_only})
        return self.answers.pop(0)


def fits(rows: int = 1000) -> dict[str, Any]:
    return {"status": "WITHIN_LIMITS", "estimate_only": True, "estimates": {"result_rows": rows}}


def test_the_planner_estimates_every_envelope_without_extracting() -> None:
    governor = Governor([fits(1200), {"status": "APPROVED_WITH_PARTITIONING", "partitioning": {"kind": "DATE",
                                                                                               "parts": 3},
                                      "estimates": {"result_rows": 2_500_000}}])
    result = ExecutionPlanner(sandbox=None, governor=governor).estimate(draft_view())
    assert result["feasible"] is True
    # fit and holdout are separate envelopes (a day apart): one fits, the other needs three date partitions
    assert result["requests"] == [{"data_request_id": "data_request_1_A", "source_table": "Price_Stock_Indonesia_IDX",
                                   "envelopes": 2, "estimated_rows": 2_501_200, "extraction_parts": 4,
                                   "governor_status": "NEEDS_PARTITIONING"}]
    assert all(c["estimate_only"] and c["lineage"]["need_id"] == DRAFT for c in governor.calls)
    refused = Governor([{"status": "REJECTED_SCAN_SIZE", "code": "SCAN_LIMIT", "message": "too large"}])
    blocked = ExecutionPlanner(sandbox=None, governor=refused).estimate(draft_view())
    assert blocked["feasible"] is False
    assert blocked["requests"][0]["governor_status"] == "REJECTED_SCAN_SIZE"
    too_many = Governor([{"status": "APPROVED_WITH_PARTITIONING", "partitioning": {"parts": 80},
                          "estimates": {"result_rows": 9}}, fits()])
    assert ExecutionPlanner(sandbox=None, governor=too_many).estimate(draft_view())["requests"][0]["code"] == \
        "TOO_MANY_PARTS"


class DraftSandbox:
    """The sandbox boundary of check_data_feasibility: /v1/data-needs/check and /v1/data-need-drafts/{id}."""

    def __init__(self, status: str = "APPROVED") -> None:
        self.status = status
        self.calls: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request.url.path)
        if request.url.path == "/v1/data-needs/check":
            body = json.loads(request.content)
            assert "research_governance" not in body["spec"]
            if self.status != "APPROVED":
                return httpx.Response(200, json={"status": "REVISION_REQUIRED", "draft_id": None, "warnings": [],
                                                 "issues": [{"code": "UNKNOWN_RELATIONSHIP"}],
                                                 "next_action": "REVISE_DATA_NEED_SPEC"})
            return httpx.Response(200, json={"status": "APPROVED", "draft_id": DRAFT, "issues": [], "warnings": [],
                                             "next_action": "ESTIMATE_EXTRACTION"})
        if request.url.path == f"/v1/data-need-drafts/{DRAFT}":
            return httpx.Response(200, json=draft_view())
        return httpx.Response(404, json={})


def check_tool(sandbox: DraftSandbox, governor: Governor):
    client = SandboxClient("http://sandbox.test", "s" * 40, 10, 0, transport=httpx.MockTransport(sandbox.handler))
    registry = ToolRegistry()
    registry.register(feasibility_spec(client, ExecutionPlanner(client, governor), timeout_seconds=10,
                                       max_result_bytes=40000))
    arguments = {k: v for k, v in research_arguments().items() if k != "research_governance"}
    tokens = (current_request_id.set("run_001"), current_run_context.set(run_context(NOW, "Asia/Jakarta", [], "q")))
    try:
        return registry.execute("c1", "check_data_feasibility", json.dumps(arguments)).output["result"]
    finally:
        current_request_id.reset(tokens[0])
        current_run_context.reset(tokens[1])


def test_the_tool_validates_then_estimates_and_never_extracts() -> None:
    sandbox, governor = DraftSandbox(), Governor([fits(), fits()])
    result = check_tool(sandbox, governor)
    assert result["status"] == "FEASIBLE" and result["draft_id"] == DRAFT
    assert result["next_action"] == "PRESENT_RESEARCH_PLAN" and result["requests"][0]["extraction_parts"] == 2
    assert sandbox.calls == ["/v1/data-needs/check", f"/v1/data-need-drafts/{DRAFT}"]
    assert [c["estimate_only"] for c in governor.calls] == [True, True]
    refused = check_tool(DraftSandbox("REVISION_REQUIRED"), Governor([]))
    assert refused["status"] == "REVISION_REQUIRED" and refused["draft_id"] is None
    assert refused["issues"][0]["code"] == "UNKNOWN_RELATIONSHIP"


def test_a_draft_id_is_bound_by_the_signature() -> None:
    s = signer()
    issued = s.issue(ResearchPlan.model_validate(plan()),
                     "run_001", "conv_1", DRAFT)
    verified = s.verify(ContinuationIn.model_validate(continuation(issued)), "conv_1")
    assert verified.draft_id == DRAFT
    plain = s.issue(ResearchPlan.model_validate(plan()),
                    "run_001", "conv_1")
    assert s.verify(ContinuationIn.model_validate(continuation(plain)), "conv_1").draft_id is None
    # a token whose draft id was altered no longer verifies
    version, payload, signature = issued.token.split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    claims["did"] = "draft_" + "e" * 24
    forged = base64.urlsafe_b64encode(json.dumps(claims, sort_keys=True, separators=(",", ":")).encode()
                                      ).rstrip(b"=").decode()
    with pytest.raises(PlanVerificationError):
        s.verify(ContinuationIn.model_validate(continuation(issued, token=f"{version}.{forged}.{signature}")),
                 "conv_1")


def feasibility_registry(sandbox: Sandbox, status: str = "FEASIBLE"):
    registry_ = registry(sandbox)
    registry_.register(ToolSpec(
        name="check_data_feasibility", description="check", arguments_model=CheckDataFeasibilityArgs,
        handler=lambda a: {"status": status, "draft_id": DRAFT if status == "FEASIBLE" else None,
                           "requests": [] if status == "FEASIBLE" else [
                               {"data_request_id": "data_request_1_A", "governor_status": "REJECTED_SCAN_SIZE",
                                "code": "SCAN_LIMIT"}], "warnings": []}))
    return registry_


def agent(script: list, sandbox: Sandbox, status: str = "FEASIBLE", drafts: dict | None = None):
    scripted = ScriptedClient(script)
    reader = (lambda draft_id: (drafts or {}).get(draft_id))
    return AgentOrchestrator(make_settings(**FEAS), scripted, feasibility_registry(sandbox, status),
                             wall_clock=Clock(), draft_reader=reader), scripted


CHECK = {k: v for k, v in research_arguments().items() if k != "research_governance"}
QUESTION = "Apakah RSI di bawah 30 dan hammer menghasilkan return lebih tinggi?"


def test_the_prompt_and_tools_carry_the_rule_only_when_on() -> None:
    assert markdown_prompt(PLAN_FEASIBILITY_RULES) in build_system_prompt(False, True, True, plan_feasibility=True)
    assert markdown_prompt(PLAN_FEASIBILITY_RULES) not in build_system_prompt(False, True, True)
    on, _ = agent([], Sandbox())
    assert on.plan_feasibility and "check_data_feasibility" in on.plan_tools
    off = AgentOrchestrator(make_settings(**FEAS), ScriptedClient([]), registry(Sandbox()), wall_clock=Clock())
    assert off.plan_feasibility is False  # no draft reader: the sandbox did not report the capability


def test_a_plan_is_issued_only_after_a_feasible_check_and_binds_the_draft() -> None:
    sandbox = Sandbox()
    unchecked, scripted = agent([final_response(plan_response()), call("check_data_feasibility", CHECK, "c1"),
                                 final_response(plan_response())], sandbox)
    result = unchecked.run(AgentRunRequest(request_id="run_001", conversation_id="conv_1", message=QUESTION))
    assert "check_data_feasibility" in str(scripted.payloads[1]["input"][-1])  # the reminder
    assert result.response.response_type == "RESEARCH_PLAN_CONFIRMATION"
    assert result.execution.research_plan.draft_id == DRAFT
    verified = signer().verify(ContinuationIn.model_validate(continuation(result.continuation)), "conv_1")
    assert verified.draft_id == DRAFT and sandbox.calls == []


def test_a_plan_whose_data_cannot_pass_becomes_a_limitation_without_a_token() -> None:
    blocked, _ = agent([call("check_data_feasibility", CHECK, "c1"), final_response(plan_response()),
                        final_response(plan_response())], Sandbox(), status="NOT_FEASIBLE")
    result = blocked.run(AgentRunRequest(request_id="run_001", conversation_id="conv_1", message=QUESTION))
    assert result.response.response_type == "LIMITATION" and result.continuation is None
    assert "REJECTED_SCAN_SIZE" in result.response.answer and result.response.research_plan is None
    assert result.execution.validation_gate == "FORCED_LIMITATION"


def approve(sandbox: Sandbox, script: list, draft_id: str | None = DRAFT, drafts: dict | None = None):
    issued = signer().issue(ResearchPlan.model_validate(plan()), "run_001", "conv_1", draft_id)
    runner, scripted = agent([classifier("APPROVE"), *script], sandbox, drafts=drafts)
    result = runner.run(AgentRunRequest(request_id="run_002", conversation_id="conv_1", message="Setuju, lanjutkan.",
                                        history=[{"role": "user", "content": QUESTION},
                                                 {"role": "assistant", "content": "Rencana riset: ... Setujui?"}],
                                        continuation=continuation(issued)))
    return result, scripted, issued


def test_the_approved_turn_starts_from_the_draft_spec() -> None:
    sandbox = Sandbox()
    result, scripted, _ = approve(sandbox, [call("submit_data_need_spec", research_arguments(), "c1"),
                                            final_response(answer("Dijalankan.", "LIMITATION"))],
                                  drafts={DRAFT: draft_view()})
    note = next(i["content"] for i in scripted.payloads[1]["input"]
                if i.get("role") == "user" and "passed check_data_feasibility" in str(i.get("content")))
    assert DRAFT in note and '"source_table":"Price_Stock_Indonesia_IDX"' in note.replace(" ", "")
    assert result.execution.research_plan.draft_id == DRAFT
    assert result.execution.research_plan.research_submitted is True
    assert [c["path"] for c in sandbox.calls] == ["/v1/data-needs"]


def test_an_approval_without_any_research_submission_stays_pending() -> None:
    # M19: the approved turn answered "no statistics yet" after reading the catalog only
    result, scripted, issued = approve(Sandbox(), [final_response(answer("Belum ada statistik.", "LIMITATION")),
                                                   final_response(answer("Belum ada statistik.", "LIMITATION"))])
    assert "no RESEARCH data need was submitted" in str(scripted.payloads[-1]["input"][-1])
    assert result.execution.research_plan.research_submitted is False
    assert PLAN_NOT_EXECUTED_LINE in result.response.limitations
    # the same continuation goes back, and the server-side plan stays PENDING
    assert result.continuation.plan_id == issued.plan_id and result.continuation.token == issued.token
    state = {"research_plan": {"plan_id": issued.plan_id, "status": "PENDING", "expires_at": issued.expires_at}}
    assert advance(state, result, "run_002", 1)["research_plan"]["status"] == "PENDING"


def test_an_approval_is_consumed_when_its_research_completes_and_stays_resumable_otherwise() -> None:
    """EXEC-W A3 (M121 c, user decision 2026-10-08): the approval was consumed by any submission; a research that did
    not complete now leaves the plan pending (the attempt is recorded), so "lanjutkan" runs it again."""
    result, _, issued = approve(Sandbox(), [call("submit_data_need_spec", research_arguments(), "c1"),
                                            final_response(answer("Data tidak cukup.", "LIMITATION"))])
    plan_exec = result.execution.research_plan
    assert plan_exec.research_submitted is True and plan_exec.research_completed is False
    assert result.continuation is None
    state = {"research_plan": {"plan_id": issued.plan_id, "status": "PENDING", "expires_at": issued.expires_at}}
    kept = advance(state, result, "run_002", 1)["research_plan"]
    assert kept["status"] == "PENDING" and kept["attempts"] == 1 and kept["last_attempt_request_id"] == "run_002"
    done = result.model_copy(update={"execution": result.execution.model_copy(update={
        "research_plan": plan_exec.model_copy(update={"research_completed": True})})})
    assert advance(state, done, "run_003", 2)["research_plan"]["status"] == "EXECUTED"


def test_the_governor_client_accepts_an_estimate_only_answer_only_for_an_estimate() -> None:
    # found live (suite3): WITHIN_LIMITS was refused as an invalid Governor response, so every check failed
    from app.tools import ToolError
    from app.tools.request_data import GovernorClient

    sent: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=fits())

    client = GovernorClient("http://governor.test", "k" * 40, 10, transport=httpx.MockTransport(handler))
    assert client.extract({"x": 1}, {"y": 2}, estimate_only=True)["status"] == "WITHIN_LIMITS"
    assert sent[-1]["estimate_only"] is True
    with pytest.raises(ToolError):
        client.extract({"x": 1}, {"y": 2})  # a real extraction never answers WITHIN_LIMITS
    assert "estimate_only" not in sent[-1]


def test_composite_keys_switch_both_tools_to_data_need_spec_v2() -> None:
    # IP1 Stage B: with AI_ENABLE_COMPOSITE_KEYS the model names every key pair; off, the v1 schema is unchanged
    from app.tools import build_default_registry
    from app.tools.request_data import GovernorClient

    t = httpx.MockTransport(lambda r: httpx.Response(404))
    kwargs = dict(cursor_secret=b"x" * 32, governor_client=GovernorClient("http://g", "k" * 40, 90, transport=t),
                  sandbox_client=SandboxClient("http://s", "s" * 40, 45, 20, transport=t), dataneed_enabled=True,
                  plan_feasibility=True)
    for composite in (False, True):
        defs = {d["name"]: d["parameters"] for d in build_default_registry(object(), composite_keys=composite,
                                                                           **kwargs).definitions()}
        for name in ("submit_data_need_spec", "check_data_feasibility"):
            rel = defs[name]["properties"]["relationships"]["items"]["properties"]
            version = defs[name]["properties"]["spec_version"]["enum"]
            if composite:
                assert "left_columns" in rel and "left_column" not in rel and version == ["data_need_spec/v2"]
            else:
                assert "left_column" in rel and "left_columns" not in rel and version == ["data_need_spec/v1"]
