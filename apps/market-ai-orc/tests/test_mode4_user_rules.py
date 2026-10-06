"""M69 tahap 1 (golden g6_revise 2026-10-02): in mode 4 the user's success threshold is tested by a hypothesis plan
(the multi-angle methods have none), the outcome horizon the user stated binds every experiment and angle, and both
are read from the user's own messages, not from the application context a mode-4 step adds to its message."""
from __future__ import annotations

import copy

import pytest

from app.mode4 import Mode4Orchestrator
from app.orchestrator import AgentOrchestrator, GateRejection
from app.research_plan import ContinuationIn, ContinuationOut, parse_plan
from app.research_plan_v2 import current_angle_bounds
from app.schemas import AgentRunRequest, FinalResponse
from app.user_words import allowed_periods, current_user_words, stated_horizons
from test_mode4 import first_round_script, m4, response, run_result, stub
from test_research_findings import agent, findings_plan, state

G6 = ("Apakah saham bank yang RSI 14-nya di bawah 30 naik minimal 3% dalam 10 hari berikutnya? Anggap berhasil kalau "
      "naik ≥ 3%. Selisih di bawah 1 poin persen tidak penting buat saya.")


# ------------------------------------------------------------------------------------------ stated horizons

def test_the_horizon_is_read_from_forward_spans_only() -> None:
    assert stated_horizons(G6) == {(10, "DAY")}
    assert stated_horizons("MA 20 hari dan RSI 14 hari, apakah naik?") == set()  # lookbacks, no forward cue
    assert stated_horizons("what happens over the next 2 weeks?") == {(2, "WEEK")}
    assert stated_horizons("return 5 hari ke depan") == {(5, "DAY")}
    assert allowed_periods({(2, "WEEK")}, "daily") == {10}
    assert allowed_periods({(2, "WEEK")}, "weekly") == {2}
    assert allowed_periods({(3, "MONTH")}, "daily") == set()  # months in trading days are not fixed: not locked


# ------------------------------------------------------------------------------------------ the plan gate

def _plan(horizon: int, **experiment) -> FinalResponse:
    plan = findings_plan()
    plan["original_question"] = G6
    plan["experiments"][0].update(outcome_horizon_periods=horizon, **experiment)
    return FinalResponse.model_validate({"response_type": "RESEARCH_PLAN_CONFIRMATION", "answer": "Rencana uji.",
                                         "clarification_question": None, "assumptions": [], "limitations": [],
                                         "research_plan": plan})


def test_a_plan_keeps_the_users_horizon() -> None:
    orchestrator = agent()
    orchestrator.audit_outbox = None
    s = state(orchestrator)
    s.user_text = G6
    with pytest.raises(GateRejection, match="outcome horizon") as raised:
        orchestrator._plan_gate(s, _plan(5))
    assert "Fields: research_plan.experiments[0].outcome_horizon_periods." in str(raised.value)  # EXEC-R R1
    s = state(orchestrator)
    s.user_text = G6
    assert orchestrator._plan_gate(s, _plan(10)).research_plan.experiments[0].outcome_horizon_periods == 10
    s = state(orchestrator)
    s.user_text = "Kalau horizonnya 5 hari ke depan bagaimana?"  # the user's own later request
    assert orchestrator._plan_gate(s, _plan(5)).research_plan.experiments[0].outcome_horizon_periods == 5


def test_a_revised_horizon_replaces_the_first_one() -> None:
    """Stress test s3 (2026-10-05): "ubah horizonnya jadi 10 hari" on a plan for 5 days was locked back to 5 by this
    gate; the newest statement wins, in a plan reply (original question + this message) and in mode 4's user words."""
    from app.user_words import MESSAGE_SEPARATOR

    orchestrator = agent()
    orchestrator.audit_outbox = None
    five = G6.replace("10 hari berikutnya", "5 hari berikutnya")

    def plan(horizon: int) -> FinalResponse:
        final = _plan(horizon)
        final.research_plan.original_question = five
        return final
    s = state(orchestrator)
    s.user_text = "ubah horizonnya jadi 10 hari"
    assert orchestrator._plan_gate(s, plan(10)).research_plan.experiments[0].outcome_horizon_periods == 10
    s = state(orchestrator)
    s.user_text = "ubah horizonnya jadi 10 hari"
    with pytest.raises(GateRejection, match="outcome horizon"):
        orchestrator._plan_gate(s, plan(5))
    token = current_user_words.set(MESSAGE_SEPARATOR.join([G6, "setuju", "pakai 5 hari ke depan saja"]))
    try:
        s = state(orchestrator)
        s.user_text = "x"
        assert orchestrator._plan_gate(s, _plan(5)).research_plan.experiments[0].outcome_horizon_periods == 5
    finally:
        current_user_words.reset(token)


def test_application_context_is_not_the_users_words() -> None:
    """A mode-4 step's message carries the model's own research text ("e.g. a shorter 5-day horizon"); with the
    pipeline's user words set, neither the horizon nor the success threshold may come from it."""
    orchestrator = agent()
    orchestrator.audit_outbox = None
    context = G6 + "\n\nApplication context (mode 4): coba horizon lebih pendek, 5 hari ke depan, naik 7%."
    token = current_user_words.set(G6)
    try:
        s = state(orchestrator)
        s.user_text = context
        with pytest.raises(GateRejection, match="outcome horizon"):
            orchestrator._plan_gate(s, _plan(5))
        s = state(orchestrator)
        s.user_text = context
        with pytest.raises(GateRejection, match="success_rule value 7"):
            orchestrator._plan_gate(s, _plan(10, success_rule={"operator": ">=", "value": 7.0, "unit": "PERCENT"}))
    finally:
        current_user_words.reset(token)


# ------------------------------------------------------------------------------------------ the plan form in mode 4

def test_mode4_accepts_a_hypothesis_plan_only_with_a_success_rule() -> None:
    orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)
    orchestrator.multi_angle, orchestrator.hypothesis_plans = True, True
    with_rule = parse_plan({**findings_plan(), "experiments": [
        {**findings_plan()["experiments"][0], "success_rule": {"operator": ">=", "value": 3.0, "unit": "PERCENT"}}]})
    without = parse_plan(findings_plan())
    token = current_angle_bounds.set((2, 6))
    try:
        assert orchestrator._plan_form_runs(False, presenting=True, plan=with_rule)
        assert not orchestrator._plan_form_runs(False, presenting=True, plan=without)
        orchestrator.hypothesis_plans = False
        assert not orchestrator._plan_form_runs(False, presenting=True, plan=with_rule)
    finally:
        current_angle_bounds.reset(token)


def test_mode4_runs_a_hypothesis_plan_and_passes_the_users_words() -> None:
    plan = parse_plan({**findings_plan(), "original_question": G6, "experiments": [
        {**findings_plan()["experiments"][0], "outcome_horizon_periods": 10,
         "success_rule": {"operator": ">=", "value": 3.0, "unit": "PERCENT"}}]})
    proposed = run_result("q-m4b", response("RESEARCH_PLAN_CONFIRMATION", "Rencana hipotesis.",
                                            research_plan=plan.model_dump(mode="json")), turn="PROPOSE")
    proposed = proposed.model_copy(update={"continuation": ContinuationOut(
        plan_id="rp_v1", origin_request_id="q-m4b", token="t", expires_at="2026-10-03T12:00:00+00:00")})
    captured: dict = {"words": []}

    def step(name):
        def run(request: AgentRunRequest):
            captured["words"].append(current_user_words.get())
            if name == "m4c":
                captured["continuation"] = request.continuation
            return copy.deepcopy(first_round_script(m4b=proposed)[name])
        return run

    wrapper, inner = stub({k: step(k) for k in ("m4a", "m4b", "m4c", "m4d")})
    wrapper.run(m4(request_id="q", conversation_id="conv", message=G6))
    approval = captured["continuation"]
    assert isinstance(approval, ContinuationIn) and approval.action == "APPROVE" and approval.plan_id == "rp_v1"
    assert approval.plan.experiments[0].success_rule.value == 3.0
    # every step's gates read the user's question, never the analysis or research text added to the step's message
    assert captured["words"] == [G6] * 4
    assert "Application context" in inner.requests[1].message
