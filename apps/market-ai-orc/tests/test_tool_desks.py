"""EXEC-T and EXEC-A (user decisions 2026-10-06; rule: a tool that must not be in a process is locked by code and
cannot be found there): every process has its desk (app/tool_desks.py); no NEVER tool is offered; a NEVER tool called
anyway is refused in every process; a gate only asks for a repair whose tool is on the desk of the process where it can
fire; the application notes and the manuals name only the step's tools; the capability report names only them."""
from __future__ import annotations

import re

import pytest
from pydantic import BaseModel, ConfigDict

from app import conversation_router as router
from app import data_record as records
from app import orchestrator as orc
from app import tool_desks as desks
from app.orchestrator import AgentOrchestrator, RunState
from app.schemas import AgentRunRequest
from app.tools import ToolRegistry
from app.tools.registry import ToolSpec

# the dev deployment's tools and their effects (AI_TOOLS.md, 2026-10-06), plus the legacy and the old web tool
DEV = {"get_system_capabilities": "READS", "discover_catalog": "READS", "get_catalog_details": "READS",
       "read_catalog_rows": "READS", "preview_table_rows": "FETCHES_DATA", "get_dimension_values": "READS",
       "lookup_reference": "READS", "submit_data_need_spec": "FETCHES_DATA", "prepare_data_bundle": "FETCHES_DATA",
       "complete_analysis": "COMPUTES", "open_analysis_session": "COMPUTES", "run_python": "COMPUTES",
       "inspect_session": "READS", "get_session_output": "READS", "export_result": "OWN_ARTIFACT",
       "get_lineage": "READS", "check_data_feasibility": "FETCHES_DATA", "get_research_library": "READS",
       "check_research_feasibility": "FETCHES_DATA", "start_research_run": "COMPUTES",
       "run_research_code": "COMPUTES", "complete_research_run": "COMPUTES", "query_metric": "FETCHES_DATA",
       "research_web": "FETCHES_WEB", "check_references": "READS", "get_method_guide": "READS"}
WITH_OLD = {**DEV, "find_web_fact": "FETCHES_WEB", "request_data": "FETCHES_DATA"}
REGISTERED = frozenset(WITH_OLD)


def offered(process: str, registered: frozenset[str] = REGISTERED) -> frozenset[str]:
    return desks.tools(process, registered, WITH_OLD.get)


@pytest.mark.parametrize("process", list(desks.DESKS))
def test_no_never_tool_is_offered_and_every_must_tool_is(process: str) -> None:
    tools = offered(process)
    assert not tools & desks.never(process, REGISTERED), process
    assert desks.DESKS[process].must & REGISTERED <= tools, process
    assert "find_web_fact" not in tools and "request_data" not in tools  # research_web is there; DataNeed runs


def test_the_matrix_rows_of_the_exec() -> None:
    """The ⚠ cells of EXEC-T: the plan desk reads earlier results and checks references, the approved multi-angle run
    checks references, CONTINUE and the approved hypothesis run never get the research run tools, no read step gets
    warehouse data."""
    assert {"get_session_output", "check_references"} <= offered("PLAN")
    assert not offered("PLAN") & (desks.DATA_FLOW | desks.WAREHOUSE_READS)
    assert "check_references" in offered("RESEARCH_V2") and not offered("RESEARCH_V2") & desks.DATA_FLOW
    assert not (offered("CONTINUE") | offered("RESEARCH_V1")) & desks.RESEARCH_RUN
    for process in ("CHAT", "FACT", "READ"):
        assert not offered(process) & (desks.DATA_FLOW | desks.WAREHOUSE_READS | desks.PLAN_CHECKS), process
    assert "research_web" in offered("FACT") and "research_web" not in offered("READ")
    assert not offered("ANALYSIS") & (desks.PLAN_CHECKS | desks.RESEARCH_RUN)


def test_the_old_web_tool_is_offered_only_without_research_web() -> None:
    without = REGISTERED - {"research_web"}
    assert "find_web_fact" in offered("FACT", without) and "find_web_fact" in offered("ANALYSIS", without)


# ---------------------------------------------------------------- gates ask only for tools on the desk (EXEC-A)

# where each gate that names a repair tool can fire, with the tools it asks for (the orchestrator's own constants)
GATE_NEEDS = {
    "PLAN_NOT_EXECUTED": {"RESEARCH_V1": orc.DATANEED_ANALYSIS_TOOLS, "RESEARCH_V2": orc.RESEARCH_RUN_TOOLS},
    "RESEARCH_RUN_INCOMPLETE": {"RESEARCH_V2": frozenset({"complete_research_run"})},
    "ANALYSIS": {p: orc.DATANEED_ANALYSIS_TOOLS for p in ("ANALYSIS", "CONTINUE", "RESEARCH_V1")},
    "ROUTING": {p: orc.DATANEED_ANALYSIS_TOOLS for p in ("ANALYSIS", "CONTINUE", "RESEARCH_V1")},
    "PLAN_FEASIBILITY": {p: frozenset({"check_data_feasibility"}) for p in ("PLAN", "CONTINUE")},
}


@pytest.mark.parametrize("gate", list(GATE_NEEDS))
def test_a_gate_only_asks_for_a_tool_the_process_has(gate: str) -> None:
    for process, needs in GATE_NEEDS[gate].items():
        assert needs & offered(process), (gate, process)


def test_the_orchestrators_repair_tools_are_the_desks_groups() -> None:
    assert orc.RESEARCH_RUN_TOOLS == desks.RESEARCH_RUN and orc.DATANEED_ANALYSIS_TOOLS == desks.DATA_FLOW


# ---------------------------------------------------------------- the notes name only the step's tools

TOOL_NAME = re.compile(r"\b(" + "|".join(sorted(WITH_OLD, key=len, reverse=True)) + r")\b")


def named(text: str) -> set[str]:
    return set(TOOL_NAME.findall(text))


@pytest.mark.parametrize("note, processes", [
    (orc.METHOD_MENU_HEADER, list(desks.DESKS)),
    (records.NOTE_HEADER, list(desks.DESKS)),
    (router.NOTES["CLARIFY"], ["READ"]),
    (router.NOTES["CONVERSATIONAL"], ["READ", "CHAT"]),
    (router.NOTES["FACT"], ["FACT"]),
    (router.NOTES["INSIGHT"], ["ANALYSIS"]),
    (router.NOTES["CONTINUE"], ["CONTINUE"]),
    (router.NOTES["QUICK_SUMMARY"], ["ANALYSIS"]),
    (orc.APPROVED_NOTE_V2, ["RESEARCH_V2"]),
    (orc.ANGLE_COUNT_NOTE, ["PLAN"]),
    (orc.FEASIBLE_DRAFT_NOTE, ["RESEARCH_V1"]),
    (orc.CONTENTS_NOT_SHOWN_NOTE, ["ANALYSIS", "CONTINUE", "RESEARCH_V1", "RESEARCH_V2"]),
    (orc.VARIANT_NOTE, ["ANALYSIS", "PLAN", "CONTINUE"]),
])
def test_an_application_note_names_only_tools_of_the_steps_it_is_given_to(note: str, processes: list[str]) -> None:
    for process in processes:
        assert named(note) <= offered(process), (process, named(note) - offered(process))


def test_a_manual_loses_the_sentences_that_name_a_hidden_tool() -> None:
    guide = {"title": "Event study", "steps": ["Load the bundle. Then call complete_analysis; it releases the table.",
                                               "Call complete_analysis."],
             "cite": "Cite it with get_session_output. Values are rounded."}
    kept = desks.scrub(guide, frozenset({"complete_analysis"}))
    assert kept == {"title": "Event study", "steps": ["Load the bundle."],
                    "cite": "Cite it with get_session_output. Values are rounded."}
    assert desks.scrub(guide, frozenset()) is guide


# ---------------------------------------------------------------- the locks in the orchestrator

class Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


def dev_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for name, effect in WITH_OLD.items():
        registry.register(ToolSpec(name=name, description=name, arguments_model=Args, handler=lambda a: {"ok": True},
                                   effect=effect))
    return registry


@pytest.mark.parametrize("process", list(desks.DESKS))
def test_a_never_tool_called_anyway_is_refused_in_every_process(process: str) -> None:
    from conftest import make_settings

    agent = AgentOrchestrator(make_settings(), object(), dev_registry())
    for name in sorted(desks.never(process, REGISTERED)):
        state = RunState(request_id="q", started=0.0, input_items=[])
        state.tools_offered, state.tool_filter = True, offered(process)
        outcome = agent._execute(state, "c1", name, {})
        assert outcome.output["error"]["code"] == "TOOL_NOT_AVAILABLE_IN_THIS_TURN", (process, name)
        message = outcome.output["error"]["message"]
        assert message.startswith(f"{name} is not available in this step;") and "awaits" not in message


def test_with_the_dataneed_flow_every_plan_turn_has_a_desk() -> None:
    """Perangkat C (EXEC-T): the AUTO turn without a plan, CONTINUE and the approved hypothesis run were offered every
    registered tool (tool_filter None)."""
    from test_research_findings import agent

    orchestrator = agent()
    state = RunState(request_id="q", started=0.0, input_items=[{"role": "user", "content": "m"}])
    orchestrator._prepare_plan_turn(AgentRunRequest(request_id="q", message="m"), state)
    assert state.plan_turn == "PROPOSE" and state.tool_filter is not None
    assert state.tool_filter == orchestrator._process_tools("CONTINUE")
    assert not state.tool_filter & desks.RESEARCH_RUN
    assert orchestrator.plan_tools <= orchestrator._process_tools("PLAN")


def test_every_plan_path_can_read_earlier_results_and_offer_edits() -> None:
    """EXEC-A 3: 10.6 and the edits on every plan path (forced RESEARCH, REVISE, REPLAN, m4b and m4d use the plan desk;
    CONTINUE proposes from its own): each desk has get_session_output, and tools, so an edit is offered."""
    from test_research_findings import agent

    orchestrator = agent()
    registered = frozenset(orchestrator.registry.names())
    for tools in (orchestrator.plan_tools, orchestrator._process_tools("CONTINUE")):
        assert tools and ("get_session_output" in tools or "get_session_output" not in registered)
