"""G23 (PLAN_FINAL_2026-10-04.md Fase 2): one source for the tools a step can call (the desk), read by the tools sent
to the model, every gate that asks for a repair and get_system_capabilities; evidence asked only for the model's own
figures; every one-time gate request says so (K2); no total failure when the step limit or the time runs out (K3)."""
from __future__ import annotations

import json
import logging

import pytest

from app import conversation_router as router
from app.orchestrator import (DATANEED_ANALYSIS_TOOLS, DISCOVERY_TOOLS, EVIDENCE_BACKEND_LINE, GATE_ONCE_NOTE,
                              LEGACY_ANALYSIS_TOOLS, RESEARCH_RUN_TOOLS, AgentOrchestrator, GateRejection, RunState)
from app.schemas import FinalResponse
from app.tools.system import current_step_tools
from conftest import ANSWER, ScriptedClient, final_response, make_settings, tool_call_response
from test_evidence import Governor, registry as evidence_registry
from test_artifacts import FakeSandbox
from test_orchestrator import ListHandler, counting_registry, orchestrator, request

FIGURES = FinalResponse(response_type="ANSWER", answer="RB beli bersih 116 dari 132 hari.",
                        clarification_question=None, assumptions=[], limitations=[])

# every desk a step can have: the router's read-only set, an approved research run, the analysis path, none
DESKS = {
    "read_only": router.READ_ONLY_TOOLS - {"get_evidence"},
    "read_only_with_evidence": router.READ_ONLY_TOOLS,
    "research_run": DISCOVERY_TOOLS | RESEARCH_RUN_TOOLS | {"inspect_session", "get_session_output", "get_lineage"},
    "analysis": DATANEED_ANALYSIS_TOOLS | DISCOVERY_TOOLS | {"get_evidence"},
    "none": frozenset(),
}
NEEDS = {"EVIDENCE": frozenset({"get_evidence"}), "ANALYSIS": DATANEED_ANALYSIS_TOOLS,
         "LEGACY_ANALYSIS": LEGACY_ANALYSIS_TOOLS, "RESEARCH_RUN_INCOMPLETE": frozenset({"complete_research_run"}),
         "PLAN_FEASIBILITY": frozenset({"check_data_feasibility"})}


def evidence_orchestrator() -> AgentOrchestrator:
    return AgentOrchestrator(make_settings(), ScriptedClient([]), evidence_registry(FakeSandbox(), Governor()))


def state_with(desk: frozenset[str] | None) -> RunState:
    state = RunState(request_id="req_g23", started=0.0, input_items=[])
    state.tool_filter = desk
    return state


@pytest.mark.parametrize("desk_name", sorted(DESKS))
@pytest.mark.parametrize("kind", sorted(NEEDS))
def test_a_gate_never_asks_for_a_tool_the_step_does_not_have(desk_name: str, kind: str) -> None:
    orc = evidence_orchestrator()
    state = state_with(frozenset(DESKS[desk_name]))
    repairable = bool(NEEDS[kind] & DESKS[desk_name])
    if repairable:
        with pytest.raises(GateRejection) as raised:
            orc._gate_once(state, kind, "fix it.", needs=NEEDS[kind])
        assert str(raised.value).endswith(GATE_ONCE_NOTE)  # K2: asked once, and the way out
    else:
        orc._gate_once(state, kind, "fix it.", needs=NEEDS[kind])  # the gate's own outcome applies at once
        assert kind not in state.gate_kinds_rejected


def test_the_evidence_gate_on_a_re_read_without_the_tool_labels_instead_of_asking() -> None:
    """g9.2 (ma-golden-20261004a): the gate asked for get_evidence on a step without it, 57 times."""
    orc = evidence_orchestrator()
    state = state_with(frozenset(DESKS["read_only"]))
    out = orc._evidence_gate(state, FIGURES, ["DATA_COVERAGE_VERIFIED"])
    assert any("Bukti klaim tidak dihitung" in line for line in out.limitations)
    assert "EVIDENCE" not in state.gate_kinds_rejected


def test_the_analysis_step_is_still_asked_once() -> None:
    """The case this change leaves as it was: the model's own figures, get_evidence on the desk."""
    orc = evidence_orchestrator()
    state = state_with(None)
    with pytest.raises(GateRejection):
        orc._evidence_gate(state, FIGURES, ["DATA_COVERAGE_VERIFIED"])
    second = orc._evidence_gate(state, FIGURES, ["DATA_COVERAGE_VERIFIED"])
    assert any("Bukti klaim tidak dihitung" in line for line in second.limitations)


@pytest.mark.parametrize("kinds", [["CALCULATION_VERIFIED"], ["DATABASE_AGGREGATE", "FACT"]])
def test_backend_figures_are_labelled_not_sent_back(kinds: list[str]) -> None:
    """G23 B: research findings, Governor summaries and query_metric are computed by the backend."""
    orc = evidence_orchestrator()
    out = orc._evidence_gate(state_with(None), FIGURES, kinds)
    assert EVIDENCE_BACKEND_LINE in out.limitations


def test_a_mixed_answer_still_checks_the_models_own_figures() -> None:
    with pytest.raises(GateRejection):
        evidence_orchestrator()._evidence_gate(state_with(None), FIGURES, ["CALCULATION_VERIFIED", "SCOPE_VERIFIED"])


def test_capabilities_report_the_tools_of_the_step() -> None:
    orc = evidence_orchestrator()
    spec = orc.registry.get("get_system_capabilities").handler
    everything = spec(None)
    assert "other_tools_not_in_this_step" not in everything
    token = current_step_tools.set(frozenset(DESKS["read_only"]))
    try:
        step = spec(None)
    finally:
        current_step_tools.reset(token)
    assert set(step["available_tools"]) <= DESKS["read_only"]
    assert "get_evidence" in step["other_tools_not_in_this_step"]
    assert set(step["available_tools"]) | set(step["other_tools_not_in_this_step"]) == set(everything["available_tools"])


def test_capabilities_called_in_a_run_see_the_runs_desk() -> None:
    agent, client = orchestrator([tool_call_response("get_system_capabilities", call_id="c1"),
                                  final_response(ANSWER)])
    agent.run(request())
    result = [i for i in client.payloads[1]["input"] if i.get("type") == "function_call_output"][0]
    body = json.loads(result["output"])
    reported = body.get("result", body).get("available_tools")
    assert sorted(reported) == sorted(agent.registry.names())


def run_logged(agent, run_request):
    logger = logging.getLogger("market_ai_orc")
    handler, previous = ListHandler(), logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        return agent.run(run_request), [json.loads(m) for m in handler.messages]
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous)


def test_the_step_limit_without_a_draft_says_what_happened_with_the_request_id() -> None:
    registry, _ = counting_registry()
    responses = [tool_call_response("lookup", json.dumps({"ticker": f"T{i}"}), call_id=f"c{i}") for i in range(5)]
    agent, _ = orchestrator(responses, registry=registry, AI_MAX_TOOL_ITERATIONS="3")
    result, events = run_logged(agent, request())
    assert result.status == "LIMITED" and result.error.code == "MAX_ITERATIONS"
    assert "Tidak bisa dihitung" in result.response.answer and "req-1" in result.response.answer
    assert any(e["event"] == "ai_run_exhausted" and e["delivered"] is False for e in events)


def test_the_step_limit_delivers_the_last_draft_through_every_gate() -> None:
    """K3: a draft the gate sent back, then the steps ran out: the draft reaches the user, its unsourced figure still
    marked by the provenance gate, with the request id."""
    registry, _ = counting_registry()
    draft = {**ANSWER, "answer": "Harga penutupan BBCA 4.321 rupiah."}
    responses = [final_response(draft), tool_call_response("lookup", '{"ticker": "BBCA"}', call_id="c1"),
                 tool_call_response("lookup", '{"ticker": "BBRI"}', call_id="c2")]
    agent, _ = orchestrator(responses, registry=registry, AI_MAX_TOOL_ITERATIONS="3")
    result, events = run_logged(agent, request("Berapa harga penutupan BBCA?"))
    assert result.status == "LIMITED" and result.error.code == "MAX_ITERATIONS"
    text = " ".join(result.response.limitations)
    assert "req-1" in text and "batas langkah" in text
    assert "4.321" in text  # the unsourced figure is named, never passed silently
    assert any(e["event"] == "ai_run_exhausted" and e["delivered"] is True for e in events)


def test_a_clean_draft_after_the_time_ran_out_keeps_its_answer() -> None:
    now = [0.0]
    registry, _ = counting_registry()
    responses = [final_response({**ANSWER, "answer": "Belum ada data."}),
                 tool_call_response("lookup", '{"ticker": "BBCA"}', call_id="c1")]
    agent, _ = orchestrator(responses, registry=registry, clock=lambda: now[0], AI_MAX_ANALYSIS_SECONDS="60",
                            AI_REQUEST_TIMEOUT_SECONDS="30")

    original = agent._validation_gate
    calls = {"n": 0}

    def gate_once_then_pass(state, final):
        calls["n"] += 1
        if calls["n"] == 1:
            state.gate_kinds_rejected.add("TEST")
            raise GateRejection("first draft sent back")
        return original(state, final)
    agent._validation_gate = gate_once_then_pass
    real_handle = agent._handle_call

    def slow_handle(state, call, truncated=False):
        now[0] += 120.0
        return real_handle(state, call, truncated=truncated)
    agent._handle_call = slow_handle
    result = agent.run(request("Ada data?"))
    assert result.status == "LIMITED" and result.error.code == "ANALYSIS_TIMEOUT"
    assert result.response.answer == "Belum ada data."
    assert any("batas waktu" in line and "req-1" in line for line in result.response.limitations)
