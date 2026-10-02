"""G3 (AI_ENABLE_HYPOTHESIS_PLAN, user decision 2026-10-02): the hypothesis plan (research plan v1 with findings v1)
beside the multi-angle plan (v2). With the switch and both capabilities the prompt, the final schema and the tools
offer both plan forms; a hypothesis plan is issued after check_data_feasibility, its approval runs RESEARCH data
needs, and mode 4 still proposes multi-angle plans only. Without the switch nothing changes."""
from __future__ import annotations

import copy
import json
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.orchestrator import (DUAL_RESEARCH_SENTENCE, HYPOTHESIS_PLAN_RULES, MULTI_ANGLE_ONLY_SENTENCE,
                              RESEARCH_FINDINGS_RULES, AgentOrchestrator, build_system_prompt)
from app.research_plan import ResearchPlanFindings
from app.research_plan_v2 import current_angle_bounds
from app.schemas import AgentRunRequest, final_response_schema
from app.tools import ToolSpec
from conftest import ScriptedClient, final_response, make_settings
from test_multi_angle import MA, QUESTION, RunSandbox, call, ma_registry
from test_research_findings import findings_plan
from test_research_plan import Clock, continuation as continuation_v1, signer as signer_v1

DRAFT = "draft_" + "7" * 24


class SpecArgsFindings(BaseModel):
    """Named like the registered findings variant of submit_data_need_spec, which switches findings v1 on."""
    model_config = ConfigDict(extra="forbid")
    mode: str
    research_governance: dict | None = None


class FeasibilityArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    data_need_spec: dict


def dual_registry(submitted: list[dict[str, Any]], *, check: bool = True):
    registry = ma_registry(RunSandbox())
    registry._tools["submit_data_need_spec"] = ToolSpec(
        name="submit_data_need_spec", description="submit_data_need_spec", arguments_model=SpecArgsFindings,
        handler=lambda a: submitted.append(a.model_dump()) or {"status": "APPROVED", "need_id": "need_" + "1" * 24,
                                                               "research_governance": {"decision": "APPROVED"}})
    if check:
        registry.register(ToolSpec(name="check_data_feasibility", description="check", arguments_model=FeasibilityArgs,
                                   handler=lambda a: {"status": "FEASIBLE", "draft_id": DRAFT, "requests": []}))
    return registry


def agent(script: list, *, switch: bool = True, check: bool = True):
    submitted: list[dict[str, Any]] = []
    scripted = ScriptedClient(script)
    settings = make_settings(**MA, **({"AI_ENABLE_HYPOTHESIS_PLAN": "true"} if switch else {}))
    runner = AgentOrchestrator(settings, scripted, dual_registry(submitted, check=check), wall_clock=Clock(),
                               draft_reader=lambda draft_id: None)
    return runner, scripted, submitted


def v1_response() -> dict[str, Any]:
    return {"response_type": "RESEARCH_PLAN_CONFIRMATION", "answer": "Rencana: satu hipotesis. Setujui?",
            "clarification_question": None, "assumptions": [], "limitations": [], "research_plan": findings_plan(),
            "research_findings": None}


def test_the_switch_needs_multi_angle_research_findings_and_the_data_check() -> None:
    on, _, _ = agent([])
    assert on.multi_angle and on.hypothesis_plans and on.research_findings
    assert {"check_data_feasibility", "check_research_feasibility"} <= on.plan_tools
    off, _, _ = agent([], switch=False)
    assert off.multi_angle and not off.hypothesis_plans and not off.research_findings
    unchecked, _, _ = agent([], check=False)
    assert not unchecked.hypothesis_plans  # no check_data_feasibility registered: fail closed


def test_the_prompt_and_schema_offer_both_forms_only_with_the_switch() -> None:
    args = dict(plan_feasibility=True, final_contract=True, research_findings=True, multi_angle=True)
    base = build_system_prompt(False, True, True, **args)
    dual = build_system_prompt(False, True, True, **args, hypothesis_plans=True)
    assert build_system_prompt(False, True, True, **args, hypothesis_plans=False) == base
    assert HYPOTHESIS_PLAN_RULES not in base and HYPOTHESIS_PLAN_RULES in dual and RESEARCH_FINDINGS_RULES in dual
    assert DUAL_RESEARCH_SENTENCE in dual and MULTI_ANGLE_ONLY_SENTENCE.split(":")[0] not in dual
    assert "The hypothesis plan: " in dual and '"experiments": [' in dual and '"angles": [' in dual
    refs = build_system_prompt(False, True, True, **args, value_references=True, hypothesis_plans=True)
    assert "{{finding.<hypothesis_id>.<path>}}" in refs
    schema = final_response_schema(True, False, True, multi_angle=True, hypothesis_plans=True)
    plans = schema["properties"]["research_plan"]["anyOf"]
    assert "angles" in plans[0]["properties"] and "experiments" in plans[1]["properties"] and plans[2] == \
        {"type": "null"}
    findings = schema["properties"]["research_findings"]["anyOf"]
    assert "angle_id" in findings[0]["items"]["properties"] and "verdict" in findings[1]["items"]["properties"]
    assert final_response_schema(True, False, True, multi_angle=True) == \
        final_response_schema(True, False, True, multi_angle=True, hypothesis_plans=False)


def test_a_hypothesis_plan_is_issued_after_the_data_check() -> None:
    runner, scripted, _ = agent([call("check_data_feasibility", {"data_need_spec": {"mode": "RESEARCH"}}, "c1"),
                                 final_response(v1_response())])
    result = runner.run(AgentRunRequest(request_id="run_001", conversation_id="conv_1", message=QUESTION))
    assert result.response.response_type == "RESEARCH_PLAN_CONFIRMATION", result.response
    assert isinstance(result.response.research_plan, ResearchPlanFindings)
    assert result.continuation is not None and result.continuation.token.startswith("rpc1.")


def test_without_the_switch_a_hypothesis_plan_is_still_refused() -> None:
    runner, scripted, _ = agent([final_response(v1_response()), final_response(v1_response())], switch=False)
    result = runner.run(AgentRunRequest(request_id="run_001", conversation_id="conv_1", message=QUESTION))
    assert "multi-angle form" in str(scripted.payloads[1]["input"][-1])
    assert result.continuation is None


def test_mode_four_proposes_multi_angle_plans_only() -> None:
    runner, scripted, _ = agent([call("check_data_feasibility", {"data_need_spec": {"mode": "RESEARCH"}}, "c1"),
                                 final_response(v1_response()), final_response(v1_response())])
    token = current_angle_bounds.set((2, 6))
    try:
        result = runner.run(AgentRunRequest(request_id="run_001", conversation_id="conv_1", message=QUESTION,
                                            analysis_path="RESEARCH"))
    finally:
        current_angle_bounds.reset(token)
    assert "multi-angle form" in str(scripted.payloads[2]["input"][-1])
    assert result.continuation is None


def test_an_approved_hypothesis_plan_runs_its_research_data_need() -> None:
    plan = findings_plan()
    issued = signer_v1().issue(ResearchPlanFindings.model_validate(plan), "run_001", "conv_1")
    experiment = plan["experiments"][0]
    governance = {k: experiment[k] for k in ("hypothesis_id", "hypothesis", "objective", "condition", "outcome",
                                             "baseline", "multiple_testing_policy", "candidate_count",
                                             "pairwise_comparisons")}
    runner, scripted, submitted = agent([
        call("submit_data_need_spec", {"mode": "RESEARCH", "research_governance": governance}, "c1"),
        final_response({"response_type": "LIMITATION", "answer": "Data belum lengkap.", "clarification_question":
                        None, "assumptions": [], "limitations": ["x"], "research_plan": None,
                        "research_findings": None})])
    result = runner.run(AgentRunRequest(request_id="run_002", conversation_id="conv_1", message="Setuju.",
                                        continuation=continuation_v1(issued, the_plan=copy.deepcopy(plan),
                                                                     action="APPROVE")))
    assert result.execution.research_plan.turn == "EXECUTE_APPROVED"
    assert result.execution.research_plan.verification == "VERIFIED"
    output = json.loads(scripted.payloads[1]["input"][-1]["output"])
    assert output["result"]["status"] == "APPROVED"  # not refused with MULTI_ANGLE_PLAN_REQUIRED
    assert [s["research_governance"]["hypothesis_id"] for s in submitted] == ["gap_down"]
