from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from .registry import ToolRegistry, ToolSpec


# A capability is reported true only when the tool that provides it is registered.
CAPABILITY_TOOLS = {
    "catalog_discovery": "discover_catalog",
    "database_query": "request_data",
    "python_analysis": "run_python_analysis",
    "web_search": "search_web",
}


class NoArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


def capabilities_spec(registry: ToolRegistry) -> ToolSpec:
    def handler(_: BaseModel) -> dict[str, Any]:
        available = registry.names()
        return {
            **{capability: tool in available for capability, tool in CAPABILITY_TOOLS.items()},
            "available_tools": available,
        }

    return ToolSpec(
        name="get_system_capabilities",
        description=(
            "Return which backend capabilities (catalog discovery, database query, Python "
            "analysis, web search) and tools are currently available to this agent."
        ),
        arguments_model=NoArguments,
        handler=handler,
        timeout_seconds=2.0,
    )
