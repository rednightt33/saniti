from __future__ import annotations

import contextvars
from typing import Any

from pydantic import BaseModel, ConfigDict

from .registry import ToolRegistry, ToolSpec


# G23 A (PLAN_FINAL_2026-10-04.md): the tools of the current step, set by the orchestrator before it runs a step's
# calls. None outside a run (every registered tool).
current_step_tools: contextvars.ContextVar[frozenset[str] | None] = contextvars.ContextVar(
    "current_step_tools", default=None)

# P31 (stress test 2026-10-05): what the agent can do is derived from the effect of each tool it can call in this step
# (ToolSpec.effect), never from a list of tool names: the old list named tools that did not exist ("search_web",
# "lookup_fact") and reported no web capability while find_web_fact was offered. One plain name per effect class; a
# class with no callable tool is listed under not_available. tests/test_tools.py checks every ToolEffect has a name.
EFFECT_CAPABILITIES: dict[str, str] = {
    "READS": "read_catalog_and_earlier_results",
    "OWN_ARTIFACT": "act_on_own_results",
    "FETCHES_DATA": "fetch_market_data_from_database",
    "FETCHES_WEB": "look_up_public_information_on_the_web",
    "COMPUTES": "run_python_analysis",
}


class NoArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


def capabilities_spec(registry: ToolRegistry) -> ToolSpec:
    def handler(_: BaseModel) -> dict[str, Any]:
        registered = registry.names()
        step = current_step_tools.get()
        available = registered if step is None else [name for name in registered if name in step]
        offered = {name: registry.get(name) for name in available}
        capabilities = {label: sorted(name for name, spec in offered.items()
                                      if spec is not None and spec.effect == effect)
                        for effect, label in EFFECT_CAPABILITIES.items()}
        return {
            "capabilities": {label: tools for label, tools in capabilities.items() if tools},
            "not_available": [label for label, tools in capabilities.items() if not tools],
            "available_tools": available,
            # G23 A: registered tools this step cannot call (absent outside a run and when every tool is offered)
            **({"other_tools_not_in_this_step": [name for name in registered if name not in available]}
               if len(available) < len(registered) else {}),
            # 4b: the menu of analysis methods (G1-G4 and the main helpers), when the method guides are served
            **({"analysis_methods": registry.method_guides["menu"]}
               if getattr(registry, "method_guides", None) else {}),
        }

    return ToolSpec(
        name="get_system_capabilities", effect="READS",
        description=(
            "Return what this agent can do in this step, derived from the tools it can call: each capability "
            "(read the catalog and earlier results, act on its own results, fetch market data from the database, "
            "look up public information on the web, run Python analysis) with the tools that provide it, the "
            "capabilities with no tool in this step, and the available tools."
        ),
        arguments_model=NoArguments,
        handler=handler,
        timeout_seconds=2.0,
    )
