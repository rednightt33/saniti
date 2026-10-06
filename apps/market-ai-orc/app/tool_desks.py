"""EXEC-T and EXEC-A (user decisions 2026-10-06): the tools of each process, one source for the tools the model is
offered, the tools a gate may ask for, the capability report and what a manual may name.

User rule (2026-10-06): a tool that must not be in a process is locked by code and cannot be found there. Each desk
lists the tools it offers (MUST: required by the matrix; MAY: allowed and offered) and the tools it never offers
(NEVER: the matrix's X, a breach of the process's contract). The orchestrator keeps three locks for every NEVER tool:
(a) it is not offered, (b) a call to it is refused in every process (TOOL_NOT_AVAILABLE_IN_THIS_TURN, "not available in
this step"), (c) the special guards stay as a second line (ResearchGuard, the research run executor, the exclusive web
switches). It cannot be found: get_system_capabilities reports only the step's tools, and a method manual opened in a
step loses the sentences that name a registered tool the step does not have.

The matrix (EXEC.md, EXEC-T) and why each X:
- PLAN: no data is fetched or computed before the user approves the plan.
- CHAT, FACT, READ (CLARIFY and CONVERSATIONAL): no warehouse data and no new computation (M63), FACT reads the web.
- ANALYSIS: the caller fixed one analysis step, so no plan check and no research run.
- RESEARCH_V2: the backend's executor runs the approved plan; the model never orders data or runs free code.
- CONTINUE and RESEARCH_V1: the research run tools need an approved multi-angle plan of their own run.
- every desk: the legacy tools of the flow before DataNeed, and find_web_fact while research_web is offered.
The analysis tools stay behind ResearchGuard in CONTINUE (a RESEARCH data need waits for an approved plan).
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

CATALOG = frozenset({"discover_catalog", "get_catalog_details", "read_catalog_rows", "get_dimension_values"})
DATA_FLOW = frozenset({"submit_data_need_spec", "prepare_data_bundle", "open_analysis_session", "run_python",
                       "complete_analysis"})
PLAN_CHECKS = frozenset({"check_data_feasibility", "check_research_feasibility"})
RESEARCH_RUN = frozenset({"start_research_run", "run_research_code", "complete_research_run"})
WAREHOUSE_READS = frozenset({"preview_table_rows", "query_metric"})
LEGACY = frozenset({"request_data", "lookup_fact", "create_analysis_spec", "prepare_analysis_data",
                    "run_python_analysis", "get_analysis_result", "get_dataset_manifest"})
RESULT_READS = frozenset({"inspect_session", "get_session_output", "get_lineage", "check_references"})
# EXEC-C (2026-10-06): what earlier runs of the conversation kept; required on every desk (H)
MEMORY = frozenset({"read_conversation_memory"})
READ_EFFECTS = frozenset({"READS", "OWN_ARTIFACT"})


@dataclass(frozen=True)
class Desk:
    """One process's tools. offered: "ALL" (every registered tool not in never), "EFFECTS" (the registered tools with
    one of effects) or "LISTED" (must | may); must: the tools the matrix requires (H); never: the matrix's X."""
    process: str
    offered: str
    must: frozenset[str] = frozenset()
    may: frozenset[str] = frozenset()
    never: frozenset[str] = frozenset()
    effects: frozenset[str] = frozenset()


DESKS: dict[str, Desk] = {
    "CHAT": Desk("CHAT", "EFFECTS", must=MEMORY, effects=READ_EFFECTS,
                 never=WAREHOUSE_READS | DATA_FLOW | PLAN_CHECKS | RESEARCH_RUN),
    "FACT": Desk("FACT", "EFFECTS", must=CATALOG | MEMORY | {"lookup_reference", "research_web"},
                 effects=READ_EFFECTS | {"FETCHES_WEB"}, never=WAREHOUSE_READS | DATA_FLOW | PLAN_CHECKS | RESEARCH_RUN),
    "READ": Desk("READ", "EFFECTS", must=MEMORY | {"get_session_output", "export_result", "get_lineage",
                                                    "check_references"},
                 effects=READ_EFFECTS, never=WAREHOUSE_READS | DATA_FLOW | PLAN_CHECKS | RESEARCH_RUN),
    "ANALYSIS": Desk("ANALYSIS", "ALL", must=CATALOG | DATA_FLOW | MEMORY | {"lookup_reference", "get_method_guide",
                                                                  "query_metric", "inspect_session",
                                                                  "get_session_output"},
                     never=PLAN_CHECKS | RESEARCH_RUN),
    "PLAN": Desk("PLAN", "LISTED", must=CATALOG | PLAN_CHECKS | MEMORY | {"get_method_guide", "get_session_output",
                                                                 "check_references", "get_research_library"},
                 may=frozenset({"get_system_capabilities"}), never=WAREHOUSE_READS | DATA_FLOW | RESEARCH_RUN),
    "CONTINUE": Desk("CONTINUE", "ALL", must=CATALOG | PLAN_CHECKS | MEMORY | {"lookup_reference", "get_method_guide",
                                                                      "inspect_session", "get_session_output",
                                                                      "get_research_library"},
                     never=RESEARCH_RUN),
    "RESEARCH_V1": Desk("RESEARCH_V1", "ALL", must=DATA_FLOW | MEMORY | {"get_method_guide", "inspect_session",
                                                                 "get_session_output"},
                        never=RESEARCH_RUN),
    "RESEARCH_V2": Desk("RESEARCH_V2", "LISTED", must=RESEARCH_RUN | RESULT_READS | MEMORY | {"get_method_guide",
                                                                                     "get_research_library"},
                        may=CATALOG | {"get_system_capabilities"},
                        never=WAREHOUSE_READS | DATA_FLOW),
}
# the processes as AI_TOOLS.md names them (the steps each covers)
DESK_LABELS = {"CHAT": "Obrolan (CHAT)", "FACT": "Fakta (FACT)", "READ": "Baca (CLARIFY, CONVERSATIONAL)",
               "ANALYSIS": "Analisis (pesan pertama, m4a, INSIGHT)",
               "PLAN": "Rencana (jalur RESEARCH, REVISE, REPLAN, m4b, m4d)",
               "CONTINUE": "CONTINUE, AUTO tanpa rencana", "RESEARCH_V1": "Riset hipotesis disetujui",
               "RESEARCH_V2": "Riset multi-sudut disetujui"}
# the process of each step the orchestrator runs (its plan turn, the router's class, the caller's path)
STEP_DESK = {"PROPOSE": "CONTINUE", "REVISE": "PLAN", "REPLAN": "PLAN", "FORCED_PROPOSE": "PLAN",
             "FORCED_ANALYSIS": "ANALYSIS", "EXECUTE_APPROVED": "RESEARCH_V1", "EXECUTE_APPROVED_V2": "RESEARCH_V2",
             "CONVERSATIONAL": "READ", "CLARIFY": "READ", "FACT": "FACT", "CHAT": "CHAT"}


def always_never(registered: frozenset[str]) -> frozenset[str]:
    """The tools no desk offers: the legacy flow, and find_web_fact while research_web is registered."""
    return LEGACY | ({"find_web_fact"} if "research_web" in registered else frozenset())


def tools(process: str, registered: frozenset[str], effect_of: Callable[[str], str | None]) -> frozenset[str]:
    """The tools a process offers on this deployment (registered ones only)."""
    desk = DESKS[process]
    never = desk.never | always_never(registered)
    if desk.offered == "ALL":
        offered = registered
    elif desk.offered == "EFFECTS":
        offered = frozenset(name for name in registered if effect_of(name) in desk.effects)
    else:
        offered = (desk.must | desk.may) & registered
    return frozenset(offered - never)


def never(process: str, registered: frozenset[str]) -> frozenset[str]:
    return (DESKS[process].never | always_never(registered)) & registered


# ---------------------------------------------------------------- not discoverable: the manuals

_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def scrub(value: Any, hidden: frozenset[str]) -> Any:
    """A manual without the sentences that name a hidden tool (strings split at sentence ends; lists and objects kept,
    an item that becomes empty dropped)."""
    if not hidden:
        return value
    if isinstance(value, str):
        pattern = re.compile(r"\b(" + "|".join(sorted(map(re.escape, hidden))) + r")\b")
        if not pattern.search(value):
            return value
        return " ".join(s for s in _SENTENCE.split(value) if not pattern.search(s)).strip()
    if isinstance(value, list):
        kept = [scrub(item, hidden) for item in value]
        return [item for item in kept if item not in ("", [], {})]
    if isinstance(value, dict):
        return {key: scrub(item, hidden) for key, item in value.items()}
    return value


def matrix(registered: frozenset[str], effect_of: Callable[[str], str | None]) -> dict[str, dict[str, str]]:
    """{tool: {process: "H" | "B" | "X" | ""}} of this deployment: H a required tool the desk offers, B another tool it
    offers, X a tool it never offers, "" a tool it does not offer (allowed, not chosen)."""
    table: dict[str, dict[str, str]] = {}
    for name in sorted(registered):
        row = {}
        for process, desk in DESKS.items():
            offered = tools(process, registered, effect_of)
            if name in offered:
                row[process] = "H" if name in desk.must else "B"
            elif name in never(process, registered):
                row[process] = "X"
            else:
                row[process] = ""
        table[name] = row
    return table
