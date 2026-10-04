from __future__ import annotations

import contextvars
from typing import Any

from pydantic import BaseModel, ConfigDict

from .registry import ToolRegistry, ToolSpec


# G23 A (PLAN_FINAL_2026-10-04.md): the tools of the current step, set by the orchestrator before it runs a step's
# calls. None outside a run (every registered tool).
current_step_tools: contextvars.ContextVar[frozenset[str] | None] = contextvars.ContextVar(
    "current_step_tools", default=None)

# A capability is reported true only when the tool that provides it can be called in this step.
CAPABILITY_TOOLS = {
    "catalog_discovery": "discover_catalog",
    "full_catalog_read": "read_catalog_rows",
    "market_data_preview": "preview_table_rows",
    "database_query": "request_data",
    "analysis_data_preparation": ("prepare_analysis_data", "prepare_data_bundle"),
    "fact_lookup": "lookup_fact",
    "python_analysis": ("run_python_analysis", "run_python"),
    "web_search": "search_web",
    # No external data provider is connected (see market-sql-governor app/external.py): always false.
    "external_data": "request_external_data",
}


class NoArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


def capabilities_spec(registry: ToolRegistry) -> ToolSpec:
    def handler(_: BaseModel) -> dict[str, Any]:
        registered = registry.names()
        step = current_step_tools.get()
        available = registered if step is None else [name for name in registered if name in step]
        return {
            **{capability: any(t in available for t in ((tool,) if isinstance(tool, str) else tool))
               for capability, tool in CAPABILITY_TOOLS.items()},
            "available_tools": available,
            # G23 A: registered tools this step cannot call (absent outside a run and when every tool is offered)
            **({"other_tools_not_in_this_step": [name for name in registered if name not in available]}
               if len(available) < len(registered) else {}),
            # 4b: the menu of analysis methods (G1-G4 and the main helpers), when the method guides are served
            **({"analysis_methods": registry.method_guides["menu"]}
               if getattr(registry, "method_guides", None) else {}),
        }

    return ToolSpec(
        name="get_system_capabilities",
        description=(
            "Return which backend capabilities (catalog discovery, full catalog read, market-data "
            "preview, database query, fact lookup, Python analysis, web search, external data) and tools are currently "
            "available to this agent."
        ),
        arguments_model=NoArguments,
        handler=handler,
        timeout_seconds=2.0,
    )
