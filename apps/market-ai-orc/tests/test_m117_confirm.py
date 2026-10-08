"""EXEC-W A2 (M117, user decision 2026-10-08 "Oke untuk M117"): a design value is the user's when the router quotes the
user's own words for it; a value read from the words without a number ("naik" is above 0) or proposed by the AI never
drops the plan: the plan is issued and the backend lists the value for the user to confirm before anything runs."""
from __future__ import annotations

import pytest

from app.orchestrator import CONFIRM_LINE, CONFIRM_TITLE, GateRejection
from app.schemas import FinalResponse
from app.user_words import current_design_changes, quoted_in, user_values
from test_research_findings import agent, findings_plan, state


def plan_with(value: float, question: str, operator: str = ">") -> FinalResponse:
    plan = findings_plan()
    plan["original_question"] = question
    plan["experiments"][0]["success_rule"] = {"operator": operator, "value": value}
    plan["experiments"][0]["min_effect"] = None
    plan["experiments"][0]["min_effect_unit"] = None
    return FinalResponse.model_validate({"response_type": "RESEARCH_PLAN_CONFIRMATION", "answer": "Rencana uji.",
                                         "clarification_question": None, "assumptions": [], "limitations": [],
                                         "research_plan": plan})


def reading(value: float, text: str | None, basis: str = "STATED", name: str = "SUCCESS_THRESHOLD") -> list[dict]:
    return [{"name": name, "value": value, "unit": "PERCENT", "text": text, "basis": basis, "action": "ADD"}]


def gate(question: str, plan: FinalResponse, changes: list[dict] | None) -> tuple[FinalResponse, object]:
    orchestrator = agent()
    orchestrator.audit_outbox = None
    orchestrator.ask_back = True
    s = state(orchestrator)
    s.user_text = question
    token = current_design_changes.set(changes)
    try:
        return orchestrator._plan_gate(s, plan), s
    finally:
        current_design_changes.reset(token)


def test_a_rise_read_as_above_zero_is_listed_for_confirmation_without_a_repair() -> None:
    """The GT2 case (2026-10-08): "apakah harganya naik" planned as > 0 used to become a LIMITATION with no plan."""
    question = "apakah harganya naik dalam 5 hari"
    out, s = gate(question, plan_with(0.0, question), reading(0, "naik", "IMPLIED"))
    assert out.response_type == "RESEARCH_PLAN_CONFIRMATION" and out.research_plan is not None
    assert CONFIRM_TITLE in out.answer and 'saya tafsirkan dari "naik"' in out.answer and CONFIRM_LINE in out.answer
    assert "Ambang sukses experiment_1: > 0%" in out.answer or ": > 0" in out.answer  # operator and unit shown (GT-A)
    assert "PLAN_SUCCESS_RULE" not in s.gate_kinds_rejected  # no repair turn: the user decides
    assert s.plan_meta["values_to_confirm"] and s.pause is None


def test_a_value_in_words_is_the_users_when_its_quote_is_in_the_message() -> None:
    question = "apakah harga naik minimal setengah persen dalam 5 hari"
    out, s = gate(question, plan_with(0.5, question, ">="), reading(0.5, "setengah persen"))
    assert CONFIRM_TITLE not in out.answer and not s.gate_kinds_rejected


def test_a_quote_that_is_not_in_the_message_is_not_the_users() -> None:
    question = "apakah harga naik dalam 5 hari"
    with pytest.raises(GateRejection, match="success_rule value 2"):
        gate(question, plan_with(2.0, question), reading(2, "minimal 2 persen"))


def test_an_invented_value_is_asked_once_then_listed_as_the_ais_proposal() -> None:
    question = "uji apakah return 5 hari setelah gap down lebih tinggi"
    orchestrator = agent()
    orchestrator.audit_outbox = None
    orchestrator.ask_back = True
    s = state(orchestrator)
    s.user_text = question
    token = current_design_changes.set([])
    try:
        with pytest.raises(GateRejection, match="keep it: the plan then lists it"):
            orchestrator._plan_gate(s, plan_with(1.5, question))
        out = orchestrator._plan_gate(s, plan_with(1.5, question))  # the model kept it
    finally:
        current_design_changes.reset(token)
    assert out.response_type == "RESEARCH_PLAN_CONFIRMATION"
    assert "usulan AI, belum Anda sebut" in out.answer and "1.5" in out.answer


def test_a_fall_with_its_sign_is_the_users_and_a_sign_read_otherwise_is_an_interpretation() -> None:
    """The 2026-10-08 benchmark: "turun lebih dari 2%" planned as -2 was refused (the digits carry no sign)."""
    question = "apakah harganya turun lebih dari 2% dalam 5 hari"
    out, s = gate(question, plan_with(-2.0, question, "<"), reading(-2, "turun lebih dari 2%"))
    assert CONFIRM_TITLE not in out.answer and not s.gate_kinds_rejected
    out, s = gate(question, plan_with(-2.0, question, "<"), reading(2, "turun lebih dari 2%"))
    assert 'saya tafsirkan dari "turun lebih dari 2%"' in out.answer and not s.gate_kinds_rejected


def test_quotes_are_matched_without_word_lists() -> None:
    assert quoted_in("Naik ", ["apakah harganya NAIK dalam 3 hari?"])
    assert quoted_in('"lima  persen"', ["naik lebih dari lima persen"])
    assert not quoted_in("", ["naik"]) and not quoted_in(None, ["naik"])
    assert not quoted_in("dua kali lipat", ["volume 2x rata-rata"])
    assert user_values(reading(5, "lima persen") + reading(9, "sembilan"), "SUCCESS_THRESHOLD",
                       ["naik lebih dari lima persen"]) == [(5.0, "STATED", "lima persen")]


def test_a_horizon_that_differs_after_the_repair_is_listed_not_dropped() -> None:
    question = "apakah harganya naik dalam 10 hari"
    plan = plan_with(0.0, question)
    plan.research_plan.experiments[0].outcome_horizon_periods = 3
    changes = reading(0, "naik", "IMPLIED") + [{"name": "OUTCOME_HORIZON", "value": 10, "unit": "DAY",
                                                "text": "10 hari", "basis": "STATED", "action": "ADD"}]
    orchestrator = agent()
    orchestrator.audit_outbox = None
    orchestrator.ask_back = True
    s = state(orchestrator)
    s.user_text = question
    token = current_design_changes.set(changes)
    try:
        with pytest.raises(GateRejection, match="outcome horizon"):
            orchestrator._plan_gate(s, plan)
        out = orchestrator._plan_gate(s, plan)
    finally:
        current_design_changes.reset(token)
    assert out.response_type == "RESEARCH_PLAN_CONFIRMATION"
    assert "rencana memakai 3 periode, padahal Anda menyebut 10 days" in out.answer
