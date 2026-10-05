"""Research findings v1 in the orchestrator (AI_ENABLE_RESEARCH_FINDINGS): the plan and research_governance carry the
findings values only behind the flag, old plans keep their shape and signature, the approved values bind the
declaration, and an answer's research_findings must repeat the backend verdict with a complete, governed
interpretation that does not overstate it."""
from __future__ import annotations

from app.orchestrator import markdown_prompt  # noqa: E402 - prompt audit C (2026-10-05)

import copy
import re

import httpx
from pydantic import BaseModel, ConfigDict

from app.orchestrator import (FINDINGS_INSTRUCTION, RESEARCH_FINDINGS_RULES, AgentOrchestrator, RunState,
                              build_system_prompt)
from app.research_plan import (ResearchPlan, ResearchPlanFindings, match_governance, parse_plan, plan_sha256)
from app.schemas import FinalResponse, final_response_schema
from app.tools import ToolSpec, build_default_registry
from app.tools.analysis import SandboxClient
from app.tools.request_data import GovernorClient
from conftest import ScriptedClient, make_settings
from test_dataneed_orchestrator import NEED, Tools

EXPERIMENT = {"experiment_id": "experiment_1", "hypothesis_id": "gap_down", "hypothesis": "Falls recover.",
              "objective": "Pattern.", "condition": "A fall of more than five percent in a day.",
              "outcome": "Forward return over five trading days.", "baseline": "All stock-days.",
              "candidate_count": 1, "pairwise_comparisons": 0, "multiple_testing_policy": "NONE",
              "holdout_required": False, "minimum_sample_value": None, "minimum_sample_unit": None}
FINDINGS_VALUES = {"expected_direction": "HIGHER", "outcome_horizon_periods": 5, "outcome_unit": "PERCENT",
                   "success_definition": "The forward return is above zero.", "min_effect": None}
PLAN = {"plan_version": "research_plan/v1", "original_question": "Apakah saham yang turun pulih?",
        "objective": "Pattern.", "universe": "IDX stocks.", "time_scope": "2024 to 2026.",
        "analysis_frequency": "daily", "experiments": [EXPERIMENT], "assumptions": [], "limitations": [],
        "confirmation_question": "Setuju?"}


def findings_plan() -> dict:
    plan = copy.deepcopy(PLAN)
    plan["experiments"][0].update(FINDINGS_VALUES)
    return plan


def registry_defs(findings: bool) -> dict:
    t = httpx.MockTransport(lambda r: httpx.Response(404))
    registry = build_default_registry(
        object(), cursor_secret=b"x" * 32, governor_client=GovernorClient("http://g", "k" * 40, 90, transport=t),
        sandbox_client=SandboxClient("http://s", "s" * 40, 45, 20, transport=t), dataneed_enabled=True,
        plan_feasibility=True, composite_keys=True, point_in_time=True, research_findings=findings)
    return {d["name"]: d["parameters"] for d in registry.definitions()}


# ------------------------------------------------------------------------------------------ flag off / on shape

def test_the_governance_fields_exist_only_behind_the_flag() -> None:
    on, off = registry_defs(True), registry_defs(False)
    governance_on = on["submit_data_need_spec"]["properties"]["research_governance"]["anyOf"][0]
    governance_off = off["submit_data_need_spec"]["properties"]["research_governance"]["anyOf"][0]
    for field in FINDINGS_VALUES:
        assert field in governance_on["required"] and field not in governance_off["properties"]


def test_the_rules_and_the_schema_change_only_when_on() -> None:
    assert markdown_prompt(RESEARCH_FINDINGS_RULES) not in build_system_prompt(False, True, plan_confirmation=True)
    assert build_system_prompt(False, True, plan_confirmation=True, research_findings=True).endswith(
        markdown_prompt(RESEARCH_FINDINGS_RULES))
    # no figure enters the system prompt (list markers are skipped): every threshold comes from the backend
    assert not any(ch.isdigit() for ch in re.sub(r"(?m)^\d+\. ", "", RESEARCH_FINDINGS_RULES))
    assert final_response_schema(True, True) == final_response_schema(True, True, research_findings=False)
    on = final_response_schema(True, True, research_findings=True)
    experiment = on["properties"]["research_plan"]["anyOf"][0]["properties"]["experiments"]["items"]
    assert set(FINDINGS_VALUES) <= set(experiment["required"]) and "research_findings" in on["required"]


def test_old_plans_keep_their_shape_and_signature() -> None:
    old = parse_plan(PLAN)
    assert type(old) is ResearchPlan and plan_sha256(old) == plan_sha256(ResearchPlan.model_validate(PLAN))
    new = parse_plan(findings_plan())
    assert isinstance(new, ResearchPlanFindings) and new.experiments[0].outcome_horizon_periods == 5
    response = FinalResponse.model_validate({"response_type": "RESEARCH_PLAN_CONFIRMATION", "answer": "Rencana",
                                             "clarification_question": None, "assumptions": [], "limitations": [],
                                             "research_plan": findings_plan()})
    assert isinstance(response.research_plan, ResearchPlanFindings)
    # a response without findings keeps its exact shape: research_findings is omitted, not null
    plain = FinalResponse.model_validate({"response_type": "ANSWER", "answer": "x", "clarification_question": None,
                                          "assumptions": [], "limitations": []})
    assert "research_findings" not in plain.model_dump()


def test_the_approved_values_bind_the_declaration() -> None:
    plan = parse_plan(findings_plan())
    governance = {"hypothesis_id": "gap_down", "hypothesis": "Falls recover.", "objective": "Pattern.",
                  "condition": EXPERIMENT["condition"], "outcome": EXPERIMENT["outcome"],
                  "baseline": EXPERIMENT["baseline"], "candidate_count": 1, "pairwise_comparisons": 0,
                  "multiple_testing_policy": "NONE", "holdout": None, "minimum_sample": None, **FINDINGS_VALUES}
    assert match_governance(governance, plan) is None
    shorter = {**governance, "outcome_horizon_periods": 1}  # a shorter horizon would inflate the effective sample
    rejection = match_governance(shorter, plan)
    assert rejection is not None and any(i["field_path"].endswith("outcome_horizon_periods")
                                         for i in rejection["error"]["issues"])


# ------------------------------------------------------------------------------------------ the findings gate

class FindingsSpecArgsFindings(BaseModel):
    """Named like the registered findings variant, which switches the feature on."""
    model_config = ConfigDict(extra="forbid")
    mode: str
    research_governance: dict | None = None


def agent() -> AgentOrchestrator:
    registry = Tools([]).registry()
    registry._tools["submit_data_need_spec"] = ToolSpec(
        name="submit_data_need_spec", description="submit_data_need_spec", arguments_model=FindingsSpecArgsFindings,
        handler=lambda a: {"status": "APPROVED", "need_id": NEED})
    orchestrator = AgentOrchestrator(make_settings(AI_ENABLE_DATANEED="true",
                                                   AI_REQUIRE_RESEARCH_PLAN_CONFIRMATION="true",
                                                   AI_RESEARCH_PLAN_SIGNING_KEY="0123456789abcdef" * 4),
                                     ScriptedClient([]), registry)
    assert orchestrator.research_findings
    return orchestrator


BACKEND = {"hypothesis_id": "gap_down", "verdict": "INCONCLUSIVE", "sample_flag": "UNDERPOWERED",
           "sample": {"effective": 37, "minimum_detectable_effect": 4.4, "smallest_effect_of_interest": 0.5},
           "angle_a": {"difference": -0.6086, "ci_low": -1.9, "ci_high": 0.7},
           "angle_b": {"condition_rate": 0.4465, "baseline_rate": 0.4152, "difference": 0.0313}}


def state(orchestrator: AgentOrchestrator) -> RunState:
    s = RunState(request_id="r", started=0.0, input_items=[], history_turns_dropped=0, user_text="x",
                 instructions="")
    s.research_findings = {"gap_down": BACKEND}
    s.analysis_values["findings:cmp_1"] = {"label": "DATA_COVERAGE_VERIFIED",
                                           "values": [37.0, 4.4, 0.5, -0.6086, 0.6086, 0.4465, 0.4152, 0.0313]}
    return s


def final(verdict="INCONCLUSIVE", evidence="Sampel efektif 37 tanggal (UNDERPOWERED); efek terkecil yang dapat "
                                           "dideteksi 4,4 poin persen.", answer="Belum dapat disimpulkan.",
          hypothesis="gap_down") -> FinalResponse:
    return FinalResponse.model_validate({
        "response_type": "ANSWER", "answer": answer, "clarification_question": None, "assumptions": [],
        "limitations": [], "research_findings": [{"hypothesis_id": hypothesis, "verdict": verdict, "interpretation": {
            "answer": "Hasilnya belum dapat disimpulkan.", "evidence": evidence,
            "usefulness": "Selisihnya lebih kecil dari yang dapat dibedakan dari nol.",
            "follow_up": "Perpanjang periode untuk menambah tanggal independen."}}]})


def test_a_consistent_interpretation_passes() -> None:
    orchestrator = agent()
    _, problems = orchestrator._findings_problems(state(orchestrator), final())
    assert problems == []


def test_a_changed_or_missing_verdict_is_a_problem() -> None:
    orchestrator = agent()
    _, problems = orchestrator._findings_problems(state(orchestrator), final(verdict="SUPPORTED"))
    assert any("differs from the backend's INCONCLUSIVE" in p for p in problems)
    _, problems = orchestrator._findings_problems(state(orchestrator), final(hypothesis="other"))
    assert "no entry for gap_down" in problems and "other is not a completed experiment" in problems


def test_overstated_wording_and_an_unnamed_sample_are_problems() -> None:
    orchestrator = agent()
    _, problems = orchestrator._findings_problems(state(orchestrator), final(answer="Hipotesis terbukti."))
    assert any("terbukti" in p for p in problems)
    _, problems = orchestrator._findings_problems(state(orchestrator), final(answer="Tidak ada efek."))
    assert any("no effect" in p for p in problems)
    # a negated form is fine
    _, problems = orchestrator._findings_problems(state(orchestrator), final(answer="Hipotesis tidak terbukti."))
    assert problems == []
    _, problems = orchestrator._findings_problems(state(orchestrator), final(evidence="Hasilnya lemah."))
    assert any("neither the effective sample" in p for p in problems)


def test_ungoverned_numbers_and_the_magnitude_of_a_difference() -> None:
    orchestrator = agent()
    evidence = "Sampel efektif 37; rata-rata lebih rendah sekitar 0,61 poin persen, CI sampai 9,9."
    _, problems = orchestrator._findings_problems(state(orchestrator), final(evidence=evidence))
    assert any("9,9" in p for p in problems) and not any("0,61" in p for p in problems)


def test_without_backend_findings_the_field_is_dropped() -> None:
    orchestrator = agent()
    empty = state(orchestrator)
    empty.research_findings = {}
    kept, problems = orchestrator._findings_problems(empty, final())
    assert problems == [] and kept.research_findings is None
    assert "{problems}" in FINDINGS_INSTRUCTION


def test_the_success_threshold_is_the_users_number() -> None:
    """M28 / H2: success_rule is the user's threshold (their question or this message); an invented one is sent back,
    and a REVISE message such as "ubah jadi 5%" supplies the new one."""
    import pytest

    from app.orchestrator import GateRejection

    orchestrator = agent()
    orchestrator.audit_outbox = None

    def plan_with(value: float, question: str) -> FinalResponse:
        plan = findings_plan()
        plan["original_question"] = question
        plan["experiments"][0]["success_rule"] = {"operator": ">=", "value": value}
        return FinalResponse.model_validate({"response_type": "RESEARCH_PLAN_CONFIRMATION", "answer": "Rencana uji.",
                                             "clarification_question": None, "assumptions": [], "limitations": [],
                                             "research_plan": plan})

    s = state(orchestrator)
    s.user_text = "Naik minimal 3%?"
    with pytest.raises(GateRejection, match="success_rule value 7"):
        orchestrator._plan_gate(s, plan_with(7.0, "Naik minimal 3%?"))
    s = state(orchestrator)
    s.user_text = "ubah jadi 5%"
    passed = orchestrator._plan_gate(s, plan_with(5.0, "Naik minimal 3%?"))
    assert passed.research_plan.experiments[0].success_rule.value == 5.0
