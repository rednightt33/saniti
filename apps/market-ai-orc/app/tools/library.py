"""Multi-Angle Research: the research library for the model (get_research_library; C07, 2026-09-29).

The eight methods a multi-angle Research Plan can use are described in public."AI_research_library" (migration
20260930_001, generated from app/research_library.py). market-ai-orc reads the active rows once at startup, enables
multi-angle research only when they equal its own copy of the library and the sandbox's (research_plan_v2.
library_problem and negotiate), and serves them to the plan turn through get_research_library instead of listing the
methods in its system prompt. The library describes; the sandbox engines compute and research_engines.decide sets each
angle's status. AI_research_catalog (18 reference methods, not runnable) is unchanged.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..research_library import ENGINE_VERSION
from ..research_plan_v2 import MethodId
from .registry import ToolSpec

LIBRARY_SQL = '''
SELECT method_id, engine_version, library_version, method_family, question_shape, input_roles,
       required_parameters, optional_parameters, data_requirements, common_requirements, sample_unit,
       secondary_checks, decision_rules_ref, interpretation, misuse_warning, example_question, library_sha256
FROM public."AI_research_library"
WHERE is_active AND engine_version = %s
ORDER BY method_id
'''
SHARED = ("engine_version", "library_version", "common_requirements", "decision_rules_ref", "library_sha256")


def read_research_library(reader: Any) -> list[dict[str, Any]]:
    """The active library rows of this engine version (one short read-only transaction of the catalog login)."""
    with reader.read_only() as run:
        return run(LIBRARY_SQL, (ENGINE_VERSION,))


class ResearchLibraryArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method_ids: list[MethodId] | None = Field(description="null for every method, or the methods to read.")


GET_RESEARCH_LIBRARY_DESCRIPTION = (
    "List the research methods a multi-angle Research Plan can use (the research library). Each method gives its "
    "family, the question it answers, its input roles, required and optional parameters with their rules, its data "
    "requirements (entity column, label, outcome, entities per date), the sample unit, the secondary checks, how to "
    "read the result and how it is misread, and an example question; plus the requirements every method shares. "
    "Choose each angle's method and parameters from it before check_research_feasibility. It describes the methods; "
    "the backend computes them and sets each angle's status.")


def research_library_spec(rows: list[dict[str, Any]], *, timeout_seconds: float = 5.0) -> ToolSpec:
    first = rows[0] if rows else {}
    shared = {key: first.get(key) for key in SHARED}
    methods = [{k: v for k, v in row.items() if k not in SHARED} for row in rows]

    def handler(arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, ResearchLibraryArgs)
        wanted = set(arguments.method_ids or [])
        chosen = [m for m in methods if not wanted or m["method_id"] in wanted]
        return {**shared, "method_count": len(chosen), "methods": chosen,
                "note": "These are the only methods an angle can use; AI_research_catalog lists reference methods "
                        "that cannot run."}

    return ToolSpec(name="get_research_library", description=GET_RESEARCH_LIBRARY_DESCRIPTION,
                    arguments_model=ResearchLibraryArgs, handler=handler, timeout_seconds=timeout_seconds)


__all__ = ["GET_RESEARCH_LIBRARY_DESCRIPTION", "LIBRARY_SQL", "ResearchLibraryArgs", "read_research_library",
           "research_library_spec"]
