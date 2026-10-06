"""O3 (PLAN_BE_OPTIMIZATION_2026-10-04.md, M77): a read-only step's tools are derived from each tool's effect class, not
from a hand-written list, so an action on an existing result (export, lineage) is offered where reading is, and a tool
that fetches data or runs code never is."""
from __future__ import annotations

import importlib.util
from functools import cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from app import conversation_router as router
from app.tools.registry import READ_EFFECTS, ToolRegistry, ToolSpec

ROOT = Path(__file__).resolve().parents[3]


@cache
def production_effects() -> dict[str, str]:
    """Every production tool (every switch on) and its effect; the generator refuses an unclassed tool."""
    spec = importlib.util.spec_from_file_location("generate_ai_tools_doc", ROOT / "scripts/generate_ai_tools_doc.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    effects = dict(module._effects())
    for switch in module.SWITCHES:
        effects.update(module._effects((switch,)))
    return effects


def production_read_only() -> frozenset[str]:
    return frozenset(name for name, effect in production_effects().items() if effect in router.READ_EFFECTS)


def test_every_production_tool_has_an_effect_class() -> None:
    assert all(effect is not None for effect in production_effects().values())


def test_the_read_only_set_keeps_actions_on_existing_results_and_nothing_that_fetches_or_runs() -> None:
    read_only = production_read_only()
    # M77: export of an existing result; plus the reads the hand-written list had
    assert {"export_result", "get_session_output", "get_lineage", "discover_catalog", "get_method_guide"} <= read_only
    assert "get_evidence" not in production_effects()  # EXEC-E (2026-10-06): the tool is removed
    assert not read_only & {"run_python", "prepare_data_bundle", "submit_data_need_spec", "query_metric",
                            "find_web_fact", "open_analysis_session", "request_data", "start_research_run"}


class Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


def test_an_unclassed_tool_is_never_read_only() -> None:
    registry = ToolRegistry()
    registry.register(ToolSpec(name="new_reader", description="x", arguments_model=Args, handler=lambda a: {},
                               effect="READS"))
    registry.register(ToolSpec(name="unclassed", description="x", arguments_model=Args, handler=lambda a: {}))
    assert registry.names_with_effect(READ_EFFECTS) == {"new_reader"}
