"""G23 (PLAN_FINAL_2026-10-04.md Fase 2): one source for the tools a step can call (the desk), read by the tools sent
to the model, every gate that asks for a repair and get_system_capabilities; the model's own typed figures asked for by
address (EXEC-E, 2026-10-06: the get_evidence gate removed), a figure equal to exactly one released value taken as its
reference (EXEC-R R3); every one-time gate request says so (K2); no total failure when the step limit or the time runs
out (K3)."""
from __future__ import annotations

import json
import logging

import httpx
import pytest

from app import conversation_router as router
from app import stop_policy
from app.orchestrator import (DATANEED_ANALYSIS_TOOLS, DISCOVERY_TOOLS, EVIDENCE_BACKEND_LINE,
                              EVIDENCE_REFERENCED_LINE, GATE_ONCE_NOTE, GATE_ONCE_NOTES, TYPED_FIGURES_LINE,
                              LEGACY_ANALYSIS_TOOLS, RESEARCH_RUN_TOOLS, AgentOrchestrator, GateRejection, RunState)
from app.schemas import FinalResponse
from app.tools import build_default_registry
from app.tools.analysis import SandboxClient
from app.tools.request_data import GovernorClient
from app.tools.system import current_step_tools
from app.value_refs import ReferenceSources, TableRows
from conftest import ANSWER, ScriptedClient, final_response, make_settings, tool_call_response
from test_analysis_tools import SANDBOX_KEY
from test_artifacts import FakeSandbox
from test_orchestrator import ListHandler, counting_registry, orchestrator, request
from test_tool_effects import production_read_only

FIGURES = FinalResponse(response_type="ANSWER", answer="RB beli bersih 116 dari 132 hari.",
                        clarification_question=None, assumptions=[], limitations=[])

# every desk a step can have: the router's read-only set, an approved research run, the analysis path, none
DESKS = {
    "read_only": production_read_only(),
    "research_run": DISCOVERY_TOOLS | RESEARCH_RUN_TOOLS | {"inspect_session", "get_session_output", "get_lineage"},
    "analysis": DATANEED_ANALYSIS_TOOLS | DISCOVERY_TOOLS,
    "none": frozenset(),
}
NEEDS = {"ANALYSIS": DATANEED_ANALYSIS_TOOLS, "LEGACY_ANALYSIS": LEGACY_ANALYSIS_TOOLS,
         "RESEARCH_RUN_INCOMPLETE": frozenset({"complete_research_run"}),
         "PLAN_FEASIBILITY": frozenset({"check_data_feasibility"})}


def governor_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"status": "OK", "rows": [], "row_count": 0})


def evidence_orchestrator() -> AgentOrchestrator:
    sandbox = FakeSandbox()
    client = SandboxClient("http://sandbox.test", SANDBOX_KEY, 10, 0, transport=httpx.MockTransport(sandbox.handler))
    governor = GovernorClient("http://governor.test", "g" * 40, 10, transport=httpx.MockTransport(governor_handler))
    registry = build_default_registry(sandbox_client=client, governor_client=governor, dataneed_enabled=True)
    return AgentOrchestrator(make_settings(AI_ENABLE_DATANEED="true", AI_ENABLE_VALUE_REFERENCES="true"),
                             ScriptedClient([]), registry)


def state_with(desk: frozenset[str] | None, label: str = "DATA_COVERAGE_VERIFIED") -> RunState:
    """A step whose analysis released the figures of FIGURES (116 and 132) under label."""
    state = RunState(request_id="req_g23", started=0.0, input_items=[])
    state.tool_filter = desk
    state.analysis_values["exe_1"] = {"label": label, "values": [116.0, 132.0]}
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
        # K2: asked once, and the way out (EXEC-W A1: what happens to a kept response is the kind's outcome)
        assert GATE_ONCE_NOTES[stop_policy.cause_of(kind).outcome] in str(raised.value)
    else:
        orc._gate_once(state, kind, "fix it.", needs=NEEDS[kind])  # the gate's own outcome applies at once
        assert kind not in state.gate_kinds_rejected


def test_typed_figures_are_asked_for_once_on_any_desk_with_tools_then_labelled() -> None:
    """EXEC-E: the repair is an edit (write the address or remove the figure), so a read-only step is asked too; the
    second time the answer is delivered with the line naming the typed figures."""
    orc = evidence_orchestrator()
    state = state_with(frozenset(DESKS["read_only"]))
    with pytest.raises(GateRejection) as raised:
        orc._evidence_gate(state, FIGURES, ["DATA_COVERAGE_VERIFIED"])
    assert "116, 132" in str(raised.value) and GATE_ONCE_NOTE in str(raised.value)
    second = orc._evidence_gate(state, FIGURES, ["DATA_COVERAGE_VERIFIED"])
    assert TYPED_FIGURES_LINE.format(numbers="116, 132") in second.limitations


def test_a_step_without_tools_is_asked_once_to_edit_typed_figures_then_labels_them() -> None:
    """EXEC-D P-f (M107): the repair is an edit, which needs no tool, so an empty desk is asked once too."""
    orc = evidence_orchestrator()
    state = state_with(frozenset())
    with pytest.raises(GateRejection):
        orc._evidence_gate(state, FIGURES, ["DATA_COVERAGE_VERIFIED"])
    out = orc._evidence_gate(state, FIGURES, ["DATA_COVERAGE_VERIFIED"])
    assert TYPED_FIGURES_LINE.format(numbers="116, 132") in out.limitations
    assert "TYPED_FIGURES" not in out.limitations


def test_a_spent_repair_budget_still_labels_at_once() -> None:
    orc = evidence_orchestrator()
    state = state_with(frozenset())
    state.tools_locked = True
    out = orc._evidence_gate(state, FIGURES, ["DATA_COVERAGE_VERIFIED"])
    assert TYPED_FIGURES_LINE.format(numbers="116, 132") in out.limitations


def test_the_gate_names_asking_back_only_where_a_question_is_allowed() -> None:
    """EXEC-D P-e (user decision 2026-10-07): the model may ask back when the user's intent is unclear."""
    from app.orchestrator import GATE_ASK_NOTE

    orc = evidence_orchestrator()
    state = state_with(frozenset(DESKS["read_only"]))
    with pytest.raises(GateRejection) as asked:
        orc._gate_once(state, "PROVENANCE", "fix it.")
    assert str(asked.value).endswith(GATE_ONCE_NOTES[stop_policy.PAUSE] + GATE_ASK_NOTE)
    state = state_with(frozenset(DESKS["read_only"]))
    state.allowed_types = frozenset({"ANSWER", "LIMITATION"})
    with pytest.raises(GateRejection) as plain:
        orc._gate_once(state, "PROVENANCE", "fix it.")
    assert str(plain.value).endswith(GATE_ONCE_NOTES[stop_policy.PAUSE])


@pytest.mark.parametrize("kinds", [["CALCULATION_VERIFIED"], ["DATABASE_AGGREGATE", "FACT"]])
def test_backend_figures_are_labelled_not_sent_back(kinds: list[str]) -> None:
    """G23 B: research findings, Governor summaries and query_metric are computed by the backend."""
    orc = evidence_orchestrator()
    out = orc._evidence_gate(state_with(None, kinds[0]), FIGURES, kinds)
    assert EVIDENCE_BACKEND_LINE in out.limitations


def test_a_mixed_answer_still_checks_the_models_own_figures() -> None:
    state = state_with(None)
    state.analysis_values["exe_2"] = {"label": "CALCULATION_VERIFIED", "values": [132.0]}
    with pytest.raises(GateRejection):
        evidence_orchestrator()._evidence_gate(state, FIGURES, ["CALCULATION_VERIFIED", "SCOPE_VERIFIED"])


# ---------------------------------------------------------------- O4: only typed figures are asked for

def referenced_state(typed_answer: str) -> RunState:
    state = state_with(None)
    state.referenced = ["out.o3.net_days[0]", "out.o3.days[0]"]
    state.typed_answer = typed_answer
    return state


def test_an_answer_whose_figures_are_all_value_references_is_labelled_not_sent_back() -> None:
    """O4 (final golden test: 54 of 65 table checks re-read the one cell the answer referenced)."""
    out = evidence_orchestrator()._evidence_gate(referenced_state("RB beli bersih   dari   hari."), FIGURES,
                                                 ["DATA_COVERAGE_VERIFIED"])
    assert EVIDENCE_REFERENCED_LINE in out.limitations


def test_a_typed_figure_beside_references_is_asked_for_by_its_number() -> None:
    state = referenced_state("RB beli bersih   dari 132 hari.")
    with pytest.raises(GateRejection) as raised:
        evidence_orchestrator()._evidence_gate(state, FIGURES, ["DATA_COVERAGE_VERIFIED"])
    assert "132" in str(raised.value) and "116" not in str(raised.value)


def test_a_number_the_user_wrote_is_not_a_claim_to_check() -> None:
    """Another case than the observed one: "10 saham bank" repeats the question, it is no figure from the code."""
    state = referenced_state("Untuk 10 saham bank, RB beli bersih   hari.")
    state.analysis_values["exe_3"] = {"label": "DATA_COVERAGE_VERIFIED", "values": [10.0]}
    state.context_numbers = [10.0]
    out = evidence_orchestrator()._evidence_gate(state, FIGURES, ["DATA_COVERAGE_VERIFIED"])
    assert EVIDENCE_REFERENCED_LINE in out.limitations


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
    # EXEC-T (2026-10-06): a tool the step cannot call is not named anywhere in the report, only its capability
    named = set(step["available_tools"]) | {t for tools in step["capabilities"].values() for t in tools}
    assert "other_tools_not_in_this_step" not in step and "run_python" not in named
    assert "run_python_analysis" in step["not_available"]


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


# ---------------------------------------------------------------- EXEC-R R3: a unique match is taken as the reference

def released_state(rows: list[dict], typed_answer: str) -> RunState:
    """A released table as a run holds it (TableRows, rows identified by their broker column)."""
    state = state_with(None)
    table = TableRows(len(rows))
    table.add(0, [dict(row) for row in rows])
    state.ref_sources = ReferenceSources()
    state.ref_sources.add("out", "o3", {"rows": table}, "DATA_COVERAGE_VERIFIED")
    state.typed_answer = typed_answer
    return state


def test_a_typed_figure_equal_to_exactly_one_released_value_counts_as_its_reference() -> None:
    rows = [{"broker": "RB", "net_days": 116.0, "days": 132.0}, {"broker": "YP", "net_days": 50.0, "days": 60.0}]
    state = released_state(rows, "RB beli bersih 116 dari 132 hari.")
    out = evidence_orchestrator()._evidence_gate(state, FIGURES, ["DATA_COVERAGE_VERIFIED"])
    assert not state.gate_kinds_rejected and EVIDENCE_REFERENCED_LINE in out.limitations
    assert sorted(state.referenced) == ["out.o3.rows[broker=RB].days", "out.o3.rows[broker=RB].net_days"]


def test_a_typed_figure_equal_to_two_released_values_is_still_asked_for() -> None:
    rows = [{"broker": "RB", "net_days": 116.0, "days": 132.0}, {"broker": "YP", "net_days": 116.0, "days": 140.0}]
    state = released_state(rows, "RB beli bersih 116 dari 132 hari.")
    with pytest.raises(GateRejection) as raised:
        evidence_orchestrator()._evidence_gate(state, FIGURES, ["DATA_COVERAGE_VERIFIED"])
    assert "116" in str(raised.value) and "132" not in str(raised.value)
