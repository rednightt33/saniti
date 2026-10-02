"""The conversation router (G2_G3_REACTIVATION_PLAN.md 4d, MODE4_CONVERSATION_PLAN.md; AI_ENABLE_CONVERSATION_ROUTER):
a later mode 4 turn is classified and handled by backend rules, so a question about a result never runs the research
again; CLARIFY reads only; a pending suggestion survives; findings of earlier turns are cited (E1)."""
from __future__ import annotations

import json
from typing import Any

from app import conversation_router as router
from app import data_record as records
from app.conversation_plans import advance
from app.orchestrator import AgentOrchestrator
from app.schemas import AgentRunRequest, HistoryMessage
from conftest import ScriptedClient, final_response, make_settings, tool_call_response
from test_dataneed_orchestrator import Tools, answer, completed, flow
from test_mode4 import (FakeInner, fake_continuation, first_round_script, follow_up_script, m4, response, run_result,
                        stub)

HISTORY = [HistoryMessage(role="user", content="Siapa broker yang membeli saham bank?"),
           HistoryMessage(role="assistant", content="Broker XL tertinggi.")]


class RoutedInner(FakeInner):
    def __init__(self, script: dict[str, Any], kind: str | None, **kwargs: Any) -> None:
        super().__init__(script, **kwargs)
        self.kind, self.contexts = kind, []

    def classify_turn(self, request_id: str, message: str, context: dict[str, Any]):
        self.contexts.append(context)
        return self.kind, "pakai 5 tahun" if self.kind == "REVISE" else None, {"status": "COMPLETED", "cost": 0.0005}


def routed(script: dict[str, Any], kind: str | None):
    wrapper, _ = stub({})
    inner = RoutedInner(script, kind)
    wrapper.inner, wrapper.router = inner, True
    return wrapper, inner


def single(suffix: str, final=None) -> dict[str, Any]:
    return {suffix: run_result(f"q3-{suffix}", final or response("ANSWER", "XL membeli saat harga turun."))}


def test_the_backend_rules() -> None:
    assert router.apply_rules("APPROVE", pending=True) == "APPROVE"
    assert router.apply_rules("APPROVE", pending=False) == "CONTINUE"
    assert router.apply_rules("REVISE", pending=False) == "CONTINUE"
    assert router.apply_rules("CANCEL", pending=False) == "CONVERSATIONAL"
    assert router.apply_rules(None, pending=True) == "INSIGHT"  # a failed classification: the cheap direction
    assert router.apply_rules("SOMETHING", pending=False) == "INSIGHT"
    assert set(router.RESEARCH_KINDS) == {"CONTINUE", "APPROVE", "NEW_TOPIC"}


def test_a_question_about_a_result_never_runs_the_research_and_keeps_the_suggestion() -> None:
    wrapper, inner = routed(single("m4q"), "CLARIFY")
    result = wrapper.run(m4(request_id="q3", message="68,9% itu artinya apa?", history=HISTORY,
                            continuation=fake_continuation()))
    assert [r.request_id for r in inner.requests] == ["q3-m4q"]  # no analysis, plan or research round
    assert inner.requests[0].analysis_path is None and inner.requests[0].continuation is None
    assert result.mode4["turn_kind"] == "CLARIFY" and result.mode4["round"] == "CLARIFY"
    assert inner.contexts[0]["pending_suggestion"] is not None
    assert any("masih menunggu" in line for line in result.response.limitations)
    state = advance({"research_plan": {"plan_id": "rp_d", "status": "PENDING"}}, result, "q3", 3)
    assert state["research_plan"]["status"] == "PENDING"  # rule 4: the suggestion survives


def test_an_insight_is_one_analysis_step() -> None:
    wrapper, inner = routed(single("m4i"), "INSIGHT")
    result = wrapper.run(m4(request_id="q3", message="Kenapa XL paling tinggi?", history=HISTORY))
    assert [(r.request_id, r.analysis_path) for r in inner.requests] == [("q3-m4i", "ANALYSIS")]
    assert result.status == "COMPLETED" and result.mode4["turn_kind"] == "INSIGHT"


def test_a_failed_classification_is_an_insight_and_continue_is_one_free_step() -> None:
    wrapper, inner = routed(single("m4i"), None)
    wrapper.run(m4(request_id="q3", message="hmm", history=HISTORY))
    assert [r.request_id for r in inner.requests] == ["q3-m4i"]
    wrapper, inner = routed(single("m4n"), "APPROVE")  # no pending suggestion: CONTINUE
    result = wrapper.run(m4(request_id="q3", message="Ok coba event study", history=HISTORY))
    assert [(r.request_id, r.analysis_path) for r in inner.requests] == [("q3-m4n", None)]
    assert result.mode4["turn_kind"] == "CONTINUE"


def test_approve_and_new_topic_act_on_the_suggestion() -> None:
    wrapper, inner = routed(follow_up_script(), "APPROVE")
    result = wrapper.run(m4(request_id="q2", message="jalankan", history=HISTORY, continuation=fake_continuation()))
    assert [r.request_id for r in inner.requests] == ["q2-m4c", "q2-m4d"]
    assert inner.requests[0].continuation.action == "APPROVE" and result.mode4["turn_kind"] == "APPROVE"
    wrapper, inner = routed(first_round_script(), "NEW_TOPIC")
    result = wrapper.run(m4(request_id="q", message="Sekarang saham telko?", history=HISTORY,
                            continuation=fake_continuation()))
    assert [r.request_id for r in inner.requests] == ["q-m4a", "q-m4b", "q-m4c", "q-m4d"]
    assert result.mode4["cancelled_plan_id"] == "rp_d"


def test_the_first_turn_is_not_routed_and_the_switch_off_keeps_the_old_flow() -> None:
    wrapper, inner = routed(first_round_script(), "CLARIFY")
    wrapper.run(m4(request_id="q", message="Siapa broker?"))
    assert inner.contexts == [] and len(inner.requests) == 4
    wrapper, inner = stub(first_round_script(), classify="UNRELATED")
    wrapper.run(m4(request_id="q", message="Kenapa XL?", history=HISTORY, continuation=fake_continuation()))
    assert [r.request_id for r in inner.requests] == ["q-m4a", "q-m4b", "q-m4c", "q-m4d"]  # M56 without the switch


# ---------------------------------------------------------------- the orchestrator side


def test_a_clarify_turn_offers_only_read_only_tools_and_no_plan() -> None:
    scripted = ScriptedClient([tool_call_response("run_python", json.dumps({"session_id": "s"}), call_id="c1"),
                               final_response(answer("Artinya porsi beli."))])
    orchestrator = AgentOrchestrator(make_settings(AI_ENABLE_DATANEED="true"), scripted, Tools([]).registry())
    token = router.current_turn_kind.set("CLARIFY")
    try:
        result = orchestrator.run(AgentRunRequest(request_id="q3-m4q", message="Artinya apa?"))
    finally:
        router.current_turn_kind.reset(token)
    offered = {t["name"] for t in scripted.payloads[0]["tools"]}
    assert offered <= router.READ_ONLY_TOOLS and "run_python" not in offered
    refused = json.loads(scripted.payloads[1]["input"][-1]["output"])
    assert refused["error"]["code"] == "TOOL_NOT_AVAILABLE_IN_THIS_TURN"
    assert any(router.NOTES["CLARIFY"] == i.get("content") for i in scripted.payloads[0]["input"])
    assert result.status == "COMPLETED"


def test_findings_of_an_earlier_turn_are_cited_again_without_running_the_research() -> None:
    finding = {"hypothesis_id": "gap_down", "verdict": "INCONCLUSIVE", "sample_flag": "UNDERPOWERED",
               "sample": {"effective": 37, "minimum_detectable_effect": 4.4},
               "angle_a": {"difference": -0.6086, "ci_low": -1.9, "ci_high": 0.7}}
    first_completion = completed(research_findings=[finding], event_studies=[
        {"name": "drops", "status": "PASS", "summary_output_id": "out_" + "6" * 24, "events_output_id": None}])
    scripted = ScriptedClient([*flow(), final_response(answer("Return YTD BBCA 12,35%."))])
    first = AgentOrchestrator(make_settings(AI_ENABLE_DATANEED="true"), scripted,
                              Tools([first_completion]).registry()).run(AgentRunRequest(request_id="q1", message="x"))
    kinds = {f["id"]: f["kind"] for f in first.data_record["findings"]}
    assert kinds == {"gap_down": "HYPOTHESIS", "drops": "EVENT_STUDY"}
    assert "finding.gap_down (HYPOTHESIS" in records.note(first.data_record)
    # a later turn: no tool call, the figure comes from the recorded finding
    text = "Selisihnya {{finding.gap_down.angle_a.difference|dec:2}} poin persen, sampel efektif 37 tanggal."
    scripted = ScriptedClient([final_response(answer(text))])
    second = AgentOrchestrator(make_settings(AI_ENABLE_DATANEED="true", AI_ENABLE_VALUE_REFERENCES="true"), scripted,
                               Tools([]).registry()).run(AgentRunRequest(request_id="q2", message="Jelaskan hasil uji "
                                                                         "tadi."), data_record=first.data_record)
    assert second.status == "COMPLETED", second.response
    assert "−0,61" in second.response.answer and second.execution.number_provenance.unsupported == []
