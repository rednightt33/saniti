"""A compact summary of the AI catalog for the system prompt (AI_CATALOG_SUMMARY_IN_PROMPT).

It states in brief what discover_catalog, get_catalog_details (COLUMNS, RELATIONSHIPS, COVERAGE) and
get_system_capabilities return, built from those same handlers so the catalog visibility rules apply unchanged. Most
runs then skip three or more discovery round trips (the 2026-09-26 stress test spent 20% of model time and 28% of cost
on them). The text is deterministic for a given catalog and leaves out check timestamps, so the cacheable prompt
prefix changes only when the catalog itself does. A failed refresh keeps the last good text (or none): the model then
uses the discovery tools as before.
"""
from __future__ import annotations

import hashlib
import threading
import time
from typing import Any, Callable

from pydantic import BaseModel

from .tools.catalog import MAX_TABLES_PER_CALL, CatalogDetailsArguments, CatalogTools

DESCRIPTION_CHARS = 90
# About 8,000 tokens. Above it the summary drops column descriptions, then (still above) is left out.
MAX_SUMMARY_CHARS = 24000
HEADER = (
    "CATALOG SUMMARY\n"
    "Written by the application from the AI catalog: documentation only, no observed values or results. It is what "
    "discover_catalog, get_system_capabilities and get_catalog_details (COLUMNS, RELATIONSHIPS, COVERAGE) would "
    "return, in brief, so you do not need to call them to find tables, columns, relationships and coverage. Call "
    "get_catalog_details only for what it leaves out (full column definitions, allowed aggregations, calculations, "
    "research methods, formulas), and get_dimension_values for the exact values of a category column."
)


def _short(text: Any) -> str:
    words = " ".join(str(text or "").split())
    return words if len(words) <= DESCRIPTION_CHARS else words[:DESCRIPTION_CHARS - 1].rstrip() + "…"


def _details(tools: CatalogTools, tables: list[str], sections: list[str]) -> dict[str, Any]:
    arguments = CatalogDetailsArguments.model_validate({"table_names": tables, "sections": sections,
                                                        "column_names": None, "entity_ids": None})
    return tools.details(arguments)["sections"]


def _render(tables: list[dict[str, Any]], columns: dict[str, list[dict[str, Any]]],
            coverage: dict[str, dict[str, Any]], disabled: set[str], relationships: dict[int, dict[str, Any]],
            discovered: dict[str, Any], available_tools: list[str], column_descriptions: bool) -> str:
    lines = [HEADER, "Available tools: " + ", ".join(sorted(available_tools)) + "."]
    research = discovered.get("research_catalog") or {}
    formulas = discovered.get("formula_catalog") or {}
    lines.append(f"Documented research methods: {research.get('method_count', 0)}; documented formulas: "
                 f"{formulas.get('formula_count', 0)} (get_catalog_details RESEARCH or FORMULAS for them).")
    if discovered.get("truncated"):
        lines.append("More tables exist than are listed here: call discover_catalog for the rest.")
    lines.append("Tables:")
    for table in tables:
        name = table["table_name"]
        subject = table.get("subject") or {}
        parts = [f"- {name}: {_short(table.get('description'))}"]
        if table.get("grain"):
            parts.append(f"grain {table['grain']}")
        if table.get("time_column"):
            parts.append(f"time column {table['time_column']}")
        if table.get("entity_column"):
            parts.append(f"entity column {table['entity_column']}")
        if subject.get("supported_frequencies"):
            parts.append("frequencies " + "/".join(subject["supported_frequencies"]))
        found = coverage.get(name)
        if found and found.get("actual_min_date"):
            parts.append(f"data {found['actual_min_date']} to {found.get('actual_max_date')} "
                         f"({found.get('verification_status') or 'UNVERIFIED'})")
        elif found and found.get("expected_min_date"):
            parts.append(f"expected data {found['expected_min_date']} to {found.get('expected_max_date')} "
                         f"(derived, not confirmed)")
        elif name in disabled:
            parts.append("coverage not tracked (current-state reference)")
        cols = [f"{c['column_name']} ({c.get('data_type')}"
                + (f", {c['unit']}" if c.get("unit") else "")
                + (f"; {_short(c.get('description'))}" if column_descriptions and c.get("description") else "")
                + ")"
                for c in columns.get(name) or []]
        lines.append("; ".join(parts) + ". Columns: " + ", ".join(cols) + ".")
    if relationships:
        lines.append("Relationships:")
        for rid in sorted(relationships):
            r = relationships[rid]
            lines.append(f"- {rid}: {r['left_table']}({', '.join(r.get('left_columns') or [])}) -> "
                         f"{r['right_table']}({', '.join(r.get('right_columns') or [])}), "
                         f"{r.get('relationship_type')}, {r.get('temporal_rule')}, output grain "
                         f"{r.get('safe_output_grain')}.")
    return "\n".join(lines)


def build_summary(tools: CatalogTools, available_tools: list[str], max_chars: int = MAX_SUMMARY_CHARS) -> str:
    """The summary text, or "" when even the form without column descriptions exceeds max_chars (the model then
    uses the discovery tools)."""
    discovered = tools.discover(_NoArguments())
    tables = discovered.get("tables") or []
    names = [t["table_name"] for t in tables]
    columns: dict[str, list[dict[str, Any]]] = {}
    for name in names:  # one table per call, so the column section is never summarized away by the result budget
        section = _details(tools, [name], ["COLUMNS"]).get("COLUMNS") or {}
        columns.update(section.get("by_table") or {})
    relationships: dict[int, dict[str, Any]] = {}
    coverage: dict[str, dict[str, Any]] = {}
    disabled: set[str] = set()
    for start in range(0, len(names), MAX_TABLES_PER_CALL):
        sections = _details(tools, names[start:start + MAX_TABLES_PER_CALL], ["RELATIONSHIPS", "COVERAGE"])
        for entry in (sections.get("RELATIONSHIPS") or {}).get("entries") or []:
            relationships[int(entry["relationship_id"])] = entry
        cov = sections.get("COVERAGE") or {}
        coverage.update(cov.get("datasets") or {})
        disabled.update(cov.get("coverage_disabled_tables") or [])
    for column_descriptions in (True, False):
        text = _render(tables, columns, coverage, disabled, relationships, discovered, available_tools,
                       column_descriptions)
        if len(text) <= max_chars:
            return text
    return ""


class _NoArguments(BaseModel):
    pass


def _in_thread(task: Callable[[], None]) -> None:
    threading.Thread(target=task, name="catalog-summary", daemon=True).start()


class CatalogSummary:
    """The current summary text; thread-safe. The first call builds it; after that a stale summary is served while a
    background refresh runs, so a request never waits for one. A failed refresh keeps the last good text and is
    retried after retry_seconds."""

    def __init__(self, tools: CatalogTools, available_tools: Callable[[], list[str]], ttl_seconds: int, *,
                 retry_seconds: float = 60.0, max_chars: int = MAX_SUMMARY_CHARS,
                 clock: Callable[[], float] = time.monotonic,
                 background: Callable[[Callable[[], None]], None] = _in_thread,
                 on_refresh: Callable[..., None] | None = None) -> None:
        self.tools = tools
        self.available_tools = available_tools
        self.ttl = ttl_seconds
        self.retry = min(retry_seconds, ttl_seconds)
        self.max_chars = max_chars
        self.clock = clock
        self.background = background
        self.on_refresh = on_refresh
        self._text = ""
        self._next_refresh: float | None = None  # None: never built
        self._refreshing = False
        self._lock = threading.Lock()

    def text(self) -> str:
        with self._lock:
            first = self._next_refresh is None
            start = not self._refreshing and (first or self.clock() >= self._next_refresh)
            if start:
                self._refreshing = True
        if start:
            if first:
                self._refresh()
            else:
                self.background(self._refresh)
        with self._lock:
            return self._text

    def _refresh(self) -> None:
        try:
            text = build_summary(self.tools, self.available_tools(), self.max_chars)
        except Exception as exc:  # noqa: BLE001 - the model falls back to the discovery tools
            with self._lock:
                self._next_refresh = self.clock() + self.retry
                self._refreshing = False
            if self.on_refresh:
                self.on_refresh(ok=False, error=type(exc).__name__)
            return
        with self._lock:
            changed = text != self._text
            self._text = text
            self._next_refresh = self.clock() + self.ttl
            self._refreshing = False
        if self.on_refresh:
            self.on_refresh(ok=True, changed=changed, chars=len(text), empty=not text,
                            sha256=hashlib.sha256(text.encode()).hexdigest()[:16])
