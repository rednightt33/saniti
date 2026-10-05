"""M26 option B (user decision 2026-10-05, PLAN_2026-10-05.md item 8), orchestrator side: the backend may return
PARTIALLY_SUPPORTED with reason BELOW_USER_MINIMUM_EFFECT when an effect in the expected direction is smaller than the
minimum effect the user named. The verdict is accepted, its reason is shown in the user's words, the answer may call it
supported in part but never plainly supported, and the minimum effect of a plan is the user's number (PLAN_MIN_EFFECT,
like PLAN_SUCCESS_RULE)."""
from __future__ import annotations

import pytest

from app.orchestrator import (BELOW_USER_MINIMUM, AgentOrchestrator, GateRejection, backend_summary,
                              evidence_sentence)
from app.schemas import FinalResponse
from test_research_findings import BACKEND, agent, final, findings_plan, state

PARTIAL = {**BACKEND, "verdict": "PARTIALLY_SUPPORTED", "verdict_reason": BELOW_USER_MINIMUM}


def partial_state(orchestrator: AgentOrchestrator):
    s = state(orchestrator)
    s.research_findings = {"gap_down": PARTIAL}
    return s


def test_the_partial_verdict_is_accepted_and_may_be_called_supported_in_part() -> None:
    orchestrator = agent()
    _, problems = orchestrator._findings_problems(partial_state(orchestrator), final(
        verdict="PARTIALLY_SUPPORTED", answer="Hipotesis didukung sebagian: arahnya sesuai, tetapi efeknya lebih kecil "
                                              "dari batas minimal Anda."))
    assert problems == []


def test_a_plain_supported_claim_is_refused_with_the_reason() -> None:
    orchestrator = agent()
    _, problems = orchestrator._findings_problems(partial_state(orchestrator), final(
        verdict="PARTIALLY_SUPPORTED", answer="Hipotesis didukung oleh data."))
    assert any("\"didukung\" states a supported verdict" in p and "didukung sebagian" in p for p in problems)
    # a plain claim beside a qualified one is still a plain claim
    _, problems = orchestrator._findings_problems(partial_state(orchestrator), final(
        verdict="PARTIALLY_SUPPORTED", answer="Didukung sebagian. Jadi hipotesis terbukti."))
    assert any("terbukti" in p for p in problems)


def test_a_supported_verdict_still_allows_both_wordings() -> None:
    assert AgentOrchestrator._verdict_wording("Didukung sebagian, bahkan didukung penuh.", {"SUPPORTED"}) == []
    assert AgentOrchestrator._verdict_wording("Hipotesis didukung sebagian.", set()) != []


def test_angle_wording_depends_on_the_reason_of_a_partial_status() -> None:
    below = {"status": "PARTIALLY_SUPPORTED", "status_reason": BELOW_USER_MINIMUM}
    other = {"status": "PARTIALLY_SUPPORTED", "status_reason": "MULTIPLE_TESTING_NOT_PASSED"}
    assert AgentOrchestrator._supported_claims(below) == {"PARTIALLY_SUPPORTED"}
    assert AgentOrchestrator._supported_claims(other) == {"SUPPORTED"}  # unchanged for the other reasons
    assert AgentOrchestrator._supported_claims({"status": "SUPPORTED"}) == {"SUPPORTED"}
    assert AgentOrchestrator._supported_claims({"status": "INSUFFICIENT_EVIDENCE"}) == set()


def test_the_backend_evidence_names_the_reason_in_the_users_words() -> None:
    sentence = evidence_sentence(backend_summary({"status": "PARTIALLY_SUPPORTED",
                                                  "status_reason": BELOW_USER_MINIMUM}))
    assert "searah, tetapi lebih kecil dari batas minimal yang Anda sebut" in sentence
    assert BELOW_USER_MINIMUM not in sentence
    other = evidence_sentence(backend_summary({"status": "PARTIALLY_SUPPORTED",
                                               "status_reason": "MULTIPLE_TESTING_NOT_PASSED"}))
    assert "MULTIPLE_TESTING_NOT_PASSED" in other


def plan_with(min_effect: float | None, question: str, unit: str | None = "PERCENT") -> FinalResponse:
    plan = findings_plan()
    plan["original_question"] = question
    plan["experiments"][0].update(min_effect=min_effect, min_effect_unit=unit if min_effect is not None else None)
    return FinalResponse.model_validate({"response_type": "RESEARCH_PLAN_CONFIRMATION", "answer": "Rencana uji.",
                                         "clarification_question": None, "assumptions": [], "limitations": [],
                                         "research_plan": plan})


def test_the_minimum_effect_is_the_users_number_or_null() -> None:
    orchestrator = agent()
    orchestrator.audit_outbox = None
    question = "Efeknya baru berarti kalau selisihnya minimal 1 poin persen."
    s = state(orchestrator)
    s.user_text = question
    assert orchestrator._plan_gate(s, plan_with(1.0, question)).research_plan.experiments[0].min_effect == 1.0
    s = state(orchestrator)
    s.user_text = question
    assert orchestrator._plan_gate(s, plan_with(0.01, question, "DECIMAL")).research_plan.experiments[0].min_effect \
        == 0.01  # the same number in another unit
    s = state(orchestrator)
    s.user_text = question
    assert orchestrator._plan_gate(s, plan_with(None, question)).research_plan.experiments[0].min_effect is None
    s = state(orchestrator)
    s.user_text = "Apakah saham yang turun pulih?"
    with pytest.raises(GateRejection, match="min_effect value 0.5"):
        orchestrator._plan_gate(s, plan_with(0.5, "Apakah saham yang turun pulih?"))
