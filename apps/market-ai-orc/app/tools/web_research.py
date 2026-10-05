"""research_web (PLAN_2026-10-05.md item 12, user decisions 2026-10-05): information that is not in the market
database, from market-web-governor POST /v1/orc/web, for context or when the database lacks it ("help a friend").

The golden test ma-qa-20261005b showed the limits of find_web_fact: a list question became 34 single facts run one
by one, and a series of yearly exports was read as one fact whose periods "conflicted". This tool sends one need, its
purpose and, when known, its expected shape (fact, number, event, series, list) and its subjects; the web governor
searches, escalates to wider research when the quick reading falls short, keeps only items quoted verbatim, names
false and real conflicts, and bounds calls and cost per user turn (budget_key). Every item comes back in a citable
envelope (label WEB_FACT): the orchestrator registers it as a value reference (web.<id>), shows it as a web fact with
its domain, and keeps its numbers out of calculations. find_web_fact and this tool are never offered together
(AI_ENABLE_WEB_FACT and AI_ENABLE_WEB_RESEARCH are exclusive).
"""
from __future__ import annotations

import time
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from .registry import ToolError, ToolSpec
from .request_data import current_request_id, current_run_deadline, current_turn_id

DESCRIPTION = (
    "Information that is not in the market database, from the web, for context or when the database lacks it: a "
    "fact, a figure, an event with its dates, a series over periods (for example yearly exports) or a list (for "
    "example the banks a group controls). Give one need in words, its purpose (CITE a value in the answer, CONTEXT "
    "for an analysis) and the expected shape when you know it; the same need about several companies is one call "
    "with them as subjects. The web governor searches, keeps only items quoted verbatim from their sources, labels "
    "false conflicts (different periods, definitions, units or releases) and, for a real conflict, the version it "
    "prefers (chosen_by_ai) with every version kept. Never use it for prices, volumes, flows or any figure the "
    "database holds; a web number describes and is never an input of a calculation, while an event date may set an "
    "analysis period. A run has a limited web budget: ask for what the answer needs.")
# added only when value references are on (a description never promises what the run cannot do; P31)
REFERENCE_SENTENCE = (" Each item has a ref: cite a number as {{<ref>.value_as_written}} (as its source writes it) or "
                      "{{<ref>.value}} (the value at full scale, or the text of a fact or list); it is shown as a web "
                      "fact with its domain.")
# P34: added only when lookup_reference is offered
DATABASE_SENTENCE = (" An attribute the database's reference tables hold (sector, industry, company profile) is read "
                     "with lookup_reference; this tool is refused for it until those tables have been read.")
NOTE = ("Web facts: state them as web facts with their source. A conflict of kind DIFFERENT_PERIOD, "
        "DIFFERENT_DEFINITION, DIFFERENT_UNIT or DIFFERENT_RELEASE is not a disagreement: give each value with its "
        "period, definition or release. REAL: say which version was preferred and why, or that the sources disagree "
        "(CONFLICTING). PARTIAL or NOT_FOUND: say what was not found; never fill it in from memory.")
MAX_SUBJECTS = 30
MAX_SECONDS = 150.0
MIN_SECONDS = 20.0
RESERVE_SECONDS = 15.0  # the run's time kept for the answer after a lookup
ENTRY_KEYS = ("id", "shape", "subject", "statement", "series_name", "value", "value_as_written", "unit", "currency",
              "scale", "kind", "compared_with", "period", "frequency", "release_date", "revision", "coverage", "event",
              "members", "quote", "confidence", "conflict", "chosen_by_ai", "label")


class ResearchWebArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    need: str = Field(min_length=3, max_length=500,
                      description="What to find, in words, e.g. 'nilai ekspor Indonesia per tahun sejak 2018'.")
    purpose: Literal["CITE", "CONTEXT"] = Field(
        description="CITE: values to state in the answer; CONTEXT: background for an analysis of the data.")
    expected_shape: Literal["FACT", "NUMBER", "EVENT", "SERIES", "LIST"] | None = Field(
        description="The shape the answer should have, or null when not known.")
    subjects: list[str] = Field(max_length=MAX_SUBJECTS, description=(
        "Companies or entities the same need is asked about, one lookup each; empty for one need."))


class WebResearchClient:
    def __init__(self, base_url: str, api_key: str, timeout_seconds: float = MAX_SECONDS,
                 transport: httpx.BaseTransport | None = None) -> None:
        self.timeout_seconds = timeout_seconds
        self.client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout_seconds, transport=transport,
                                   headers={"Authorization": f"Bearer {api_key}"})

    def research(self, body: dict[str, Any], timeout_seconds: float | None = None) -> dict[str, Any]:
        try:
            response = self.client.post("/v1/orc/web", json=body, timeout=timeout_seconds or self.timeout_seconds)
        except httpx.HTTPError as exc:
            raise ToolError(f"the web governor did not answer ({type(exc).__name__})",
                            code="WEB_RESEARCH_UNAVAILABLE") from None
        if response.status_code != 200:
            raise ToolError(f"the web governor returned HTTP {response.status_code}", code="WEB_RESEARCH_UNAVAILABLE")
        return response.json()


def wait_seconds(now: float | None = None) -> float:
    """How long a lookup may take: the run's time left less a reserve for the answer, between MIN_SECONDS and
    MAX_SECONDS (MAX_SECONDS outside a run)."""
    deadline = current_run_deadline.get()
    if deadline is None:
        return MAX_SECONDS
    left = deadline - (time.monotonic() if now is None else now) - RESERVE_SECONDS
    return max(MIN_SECONDS, min(MAX_SECONDS, left))


def model_view(result: dict[str, Any]) -> dict[str, Any]:
    """What the model reads: each citable item without empty fields, the conflicts by item id, the sources' domains,
    the budget left and the warnings (no excerpts)."""
    citable = [entry for entry in result.get("citable") or [] if isinstance(entry, dict) and entry.get("id")]
    items = []
    for entry in citable:
        item = {k: entry[k] for k in ENTRY_KEYS if entry.get(k) not in (None, "", [], {})}
        source = entry.get("source") if isinstance(entry.get("source"), dict) else {}
        item["source"] = {k: source.get(k) for k in ("domain", "tier", "official", "date", "url") if source.get(k)}
        items.append(item)
    ids = [entry["id"] for entry in citable]

    def named(index: Any) -> str | None:
        return ids[index] if isinstance(index, int) and 0 <= index < len(ids) else None

    budget = result.get("budget") or {}
    return {
        "status": result.get("status"), "result_id": result.get("result_id"), "depth": result.get("depth"),
        "escalated": result.get("escalated"), "cached": result.get("cached"), "citable": items,
        "conflicts": [{"about": c.get("about"), "kind": c.get("kind"),
                       "items": [named(i) for i in c.get("items") or [] if named(i)], "chosen": named(c.get("chosen")),
                       "reason": c.get("reason")} for c in result.get("conflicts") or [] if isinstance(c, dict)],
        "sources": [{k: s.get(k) for k in ("n", "domain", "tier", "date")} for s in (result.get("sources") or [])[:20]
                    if isinstance(s, dict)],
        "budget": {"calls_left": budget.get("calls_left"), "usd_left": budget.get("usd_left")},
        "warnings": [{"code": w.get("code"), "message": w.get("message")} for w in result.get("warnings") or []
                     if isinstance(w, dict)],
        "note": NOTE,
    }


def web_research_spec(client: WebResearchClient, *, value_references: bool = False,
                      reference_lookup: bool = False) -> ToolSpec:
    def handler(arguments: ResearchWebArguments) -> dict[str, Any]:
        request_id = current_request_id.get() or "unknown"
        body = {"request_id": request_id[:200], "budget_key": (current_turn_id.get() or request_id)[:200],
                "need": arguments.need, "purpose": arguments.purpose, "expected_shape": arguments.expected_shape,
                "subjects": [s.strip() for s in arguments.subjects if s.strip()]}
        return model_view(client.research(body, wait_seconds()))

    description = DESCRIPTION + (REFERENCE_SENTENCE if value_references else "") \
        + (DATABASE_SENTENCE if reference_lookup else "")
    return ToolSpec(name="research_web", effect="FETCHES_WEB", description=description,
                    arguments_model=ResearchWebArguments, handler=handler, timeout_seconds=MAX_SECONDS + 10)
