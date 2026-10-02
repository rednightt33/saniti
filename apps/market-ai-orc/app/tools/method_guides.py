"""Method guides (G2_G3_REACTIVATION_PLAN.md 4b, user decision 2026-10-02): the menu of analysis methods and the
manual of each (get_method_guide).

The guides are written in app/method_guides.py (byte-identical in market-python-sandbox), stored by migration
20261002_001 in public."AI_method_guide" and reported by the sandbox in GET /v1/runtime (method_guides). market-ai-orc
reads the active rows once at startup and serves them only when the table, the sandbox and its own copy carry the same
hash (guides_problem); otherwise the menu and the tool stay off (method_guides_inactive). A guide is offered only when
its method is active in this deployment (active_guides), so the menu never lists a method the model cannot use.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .. import method_guides as G
from .registry import ToolSpec

GUIDE_SQL = '''
SELECT name, guides_version, kind, g, guide, guide_sha256, guides_sha256
FROM public."AI_method_guide"
WHERE is_active AND guides_version = %s
ORDER BY name
'''


def read_method_guides(reader: Any) -> list[dict[str, Any]]:
    """The active guide rows of this version (one short read-only transaction of the catalog login)."""
    with reader.read_only() as run:
        return run(GUIDE_SQL, (G.GUIDES_VERSION,))


def guides_problem(rows: list[dict[str, Any]], capability: dict[str, Any] | None) -> str | None:
    """None when the table, the sandbox and this service carry the same guides; else the reason (fail closed)."""
    if not isinstance(capability, dict) or capability.get("enabled") is not True:
        return "the sandbox does not report method_guides"
    if capability.get("version") != G.GUIDES_VERSION or capability.get("sha256") != G.GUIDES_SHA256:
        return (f"the sandbox's method guides ({capability.get('version')}, {capability.get('sha256')}) differ from "
                f"market-ai-orc's ({G.GUIDES_VERSION}, {G.GUIDES_SHA256})")
    expected = {row["name"]: row["guide_sha256"] for row in G.rows()}
    stored = {str(row.get("name")): row.get("guide_sha256") for row in rows}
    if stored != expected or any(row.get("guides_sha256") != G.GUIDES_SHA256 for row in rows):
        return "AI_method_guide does not hold market-ai-orc's method guides (apply its forward migration)"
    if any(row.get("guide") != G.by_name()[str(row["name"])] for row in rows):
        return "an AI_method_guide row differs from its hash"
    return None


def active_guides(*, dataneed: bool, event_study: bool, hypothesis_plan: bool, multi_angle: bool,
                  period_return: bool) -> list[str]:
    """The guides whose method this deployment offers, in the guides' order."""
    offered = {"free_code": dataneed, "reading_data": dataneed, "resample": dataneed,
               "join_and_preaggregate": dataneed, "event_study": dataneed and event_study,
               "hypothesis_plan": dataneed and hypothesis_plan, "multi_angle": dataneed and multi_angle,
               "period_return": dataneed and period_return}
    return [g["name"] for g in G.GUIDES if offered.get(g["name"])]


def menu(names: list[str]) -> list[dict[str, Any]]:
    guides = G.by_name()
    return [G.menu_entry(guides[name]) for name in names]


class MethodGuideArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64,
                      description="A name from analysis_methods (for example event_study), or a research library "
                                  "method_id while multi-angle research is offered.")


GET_METHOD_GUIDE_DESCRIPTION = (
    "Open the manual of one analysis method or helper listed in analysis_methods (the menu at the start of the run and "
    "in get_system_capabilities): what it is for and when not to use it, its inputs with their defaults, its limits, "
    "what the backend checks and what it does not, its results and how to cite them, common errors from earlier runs "
    "and tested examples. Open it before using a method the first time in a conversation; a manual opened earlier in "
    "the conversation is already in the context and need not be opened again.")


def method_guide_spec(names: list[str], *, library_rows: list[dict[str, Any]] | None = None,
                      timeout_seconds: float = 5.0) -> ToolSpec:
    guides = G.by_name()
    offered = {name: guides[name] for name in names}
    library = {str(row.get("method_id")): row for row in library_rows or []}

    def handler(arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, MethodGuideArgs)
        name = arguments.name.strip()
        if name in offered:
            return {"name": name, "version": G.GUIDES_VERSION, "sha256": G.guide_sha256(offered[name]),
                    "verification_levels": {offered[name]["verification"]["level"]:
                                            G.VERIFICATION_LEVELS[offered[name]["verification"]["level"]]},
                    "guide": offered[name]}
        if name in library:
            # a multi-angle angle's method: its research library entry is its manual
            return {"name": name, "research_library_method": {k: v for k, v in library[name].items()
                                                              if k != "library_sha256"},
                    "note": "A method of the research library: an angle of a multi-angle plan uses it (see "
                            "multi_angle)."}
        return {"status": "REJECTED", "code": "UNKNOWN_METHOD",
                "message": f"{name!r} is not an analysis method of this deployment.",
                "available": sorted(offered) + sorted(library), "next_action": "CALL_WITH_A_LISTED_NAME"}

    return ToolSpec(name="get_method_guide", description=GET_METHOD_GUIDE_DESCRIPTION, arguments_model=MethodGuideArgs,
                    handler=handler, timeout_seconds=timeout_seconds)


__all__ = ["GET_METHOD_GUIDE_DESCRIPTION", "GUIDE_SQL", "MethodGuideArgs", "active_guides", "guides_problem", "menu",
           "method_guide_spec", "read_method_guides"]
