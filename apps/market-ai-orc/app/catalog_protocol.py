"""The catalog discovery protocol (AI_ENABLE_CATALOG_PROTOCOL, implementation plan 2026-09-27, phase C3).

Three parts, all per run (nothing is kept across runs or conversations):
- a ledger of the catalog metadata this run actually received from tool results: table contracts (subject, time and
  entity columns), columns with their permissions, and relationships;
- reuse of successful results of the catalog tools: an identical call (after canonicalizing set-valued arguments,
  whitespace and nulls) returns the stored result marked cache_hit, without a database query. It still counts toward
  the tool-call budget and the REPEATED_TOOL_CALL guard;
- the metadata guard: submit_data_need_spec is refused with CATALOG_DETAILS_REQUIRED, before any sandbox call, when a
  table contract, a used column or a relationship it names was not received in this run. The DataNeedValidator still
  decides whether the values are right: having read the catalog does not prove the model understood it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .compaction import stable_hash
from .tools.catalog import MAX_COLUMN_FILTER, MAX_TABLES_PER_CALL

CACHEABLE_TOOLS = frozenset({"discover_catalog", "get_catalog_details", "read_catalog_rows", "get_dimension_values",
                             "get_system_capabilities"})
SET_ARGUMENTS = frozenset({"table_names", "sections", "column_names", "entity_ids", "method_ids", "formula_ids"})
CACHE_NOTE = "Same result as the identical earlier call in this run; the catalog was not read again."


@dataclass
class TableSeen:
    contract: bool = False                      # grain, time/entity columns and subject values were received
    time_column: str | None = None
    entity_column: str | None = None
    columns: set[str] = field(default_factory=set)


@dataclass
class CatalogLedger:
    tables: dict[str, TableSeen] = field(default_factory=dict)
    relationships: set[int] = field(default_factory=set)
    cache: dict[str, dict[str, Any]] = field(default_factory=dict)
    calls: dict[str, int] = field(default_factory=dict)
    cache_hits: int = 0
    refusals: int = 0

    def table(self, name: str) -> TableSeen:
        return self.tables.setdefault(name, TableSeen())


def cache_key(name: str, arguments: Any) -> str:
    """Identical requests share a key; different filters or sections never do. Order of set-valued arguments,
    whitespace in text and null against omitted do not matter."""
    if not isinstance(arguments, dict):
        return stable_hash({"tool": name, "raw": arguments})
    canonical: dict[str, Any] = {}
    for key, value in arguments.items():
        if value is None:
            continue
        if key in SET_ARGUMENTS and isinstance(value, list):
            value = sorted({str(item).strip() for item in value})
        elif isinstance(value, str):
            value = " ".join(value.split())
        canonical[key] = value
    return stable_hash({"tool": name, "arguments": canonical})


def _contract(ledger: CatalogLedger, table: str, entry: dict[str, Any]) -> None:
    seen = ledger.table(table)
    seen.contract = True
    seen.time_column = entry.get("time_column") or seen.time_column
    seen.entity_column = entry.get("entity_column") or seen.entity_column


def record(ledger: CatalogLedger, name: str, result: dict[str, Any]) -> None:
    """Add what a successful catalog result contained to the ledger (exact records only)."""
    if name == "discover_catalog":
        for entry in result.get("tables") or []:
            if isinstance(entry, dict) and entry.get("table_name"):
                _contract(ledger, str(entry["table_name"]), entry)
    elif name == "get_catalog_details":
        for table, entry in (result.get("table_metadata") or {}).items():
            if isinstance(entry, dict):
                _contract(ledger, str(table), entry)
        sections = result.get("sections") or {}
        for table, columns in ((sections.get("COLUMNS") or {}).get("by_table") or {}).items():
            ledger.table(str(table)).columns.update(
                str(c["column_name"]) for c in columns or [] if isinstance(c, dict) and c.get("column_name"))
        for entry in (sections.get("RELATIONSHIPS") or {}).get("entries") or []:
            if isinstance(entry, dict) and isinstance(entry.get("relationship_id"), int):
                ledger.relationships.add(entry["relationship_id"])
    elif name == "read_catalog_rows":
        names = [c.get("name") for c in result.get("columns") or [] if isinstance(c, dict)]
        rows = [dict(zip(names, row)) for row in result.get("rows") or [] if isinstance(row, list)]
        catalog = result.get("catalog_name")
        for row in rows:
            if catalog == "AI_column_catalog" and row.get("table_name") and row.get("column_name"):
                ledger.table(str(row["table_name"])).columns.add(str(row["column_name"]))
            elif catalog == "AI_table_catalog" and row.get("table_name"):
                _contract(ledger, str(row["table_name"]), row)
            elif catalog == "AI_catalog_relationships" and isinstance(row.get("relationship_id"), int):
                ledger.relationships.add(row["relationship_id"])


def _scope_columns(node: Any) -> set[str]:
    if not isinstance(node, dict):
        return set()
    found = {str(node["column"])} if node.get("type") == "PREDICATE" and node.get("column") else set()
    for child in node.get("children") or []:
        found |= _scope_columns(child)
    return found | _scope_columns(node.get("child"))


def gaps(ledger: CatalogLedger, arguments: Any) -> dict[str, Any] | None:
    """What a DataNeedSpec uses that this run has not read, with the calls that read it; None when complete or when
    the arguments are not a spec (the tool's own validation then answers)."""
    if not isinstance(arguments, dict) or not isinstance(arguments.get("data_requests"), list):
        return None
    missing: dict[str, dict[str, Any]] = {}
    for request in arguments["data_requests"]:
        if not isinstance(request, dict) or not request.get("source_table"):
            continue
        table = str(request["source_table"])
        seen = ledger.tables.get(table, TableSeen())
        used = {str(c) for c in request.get("columns") or [] if isinstance(c, str)}
        used |= _scope_columns(request.get("scope"))
        used |= {str(o["column"]) for o in request.get("ordering") or [] if isinstance(o, dict) and o.get("column")}
        for key in ("entity_column", "time_column"):
            if request.get(key):
                used.add(str(request[key]))
        known = seen.columns | {c for c in (seen.time_column, seen.entity_column) if c}
        unseen = sorted(used - known)
        if not seen.contract or unseen:
            entry = missing.setdefault(table, {"table": table, "needs": [], "columns": []})
            if not seen.contract and "table contract (subject, grain, time and entity columns)" not in entry["needs"]:
                entry["needs"].append("table contract (subject, grain, time and entity columns)")
            entry["columns"] = sorted(set(entry["columns"]) | set(unseen))
    relationships = sorted({int(r["relationship_id"]) for r in arguments.get("relationships") or []
                            if isinstance(r, dict) and isinstance(r.get("relationship_id"), int)}
                           - ledger.relationships)
    if not missing and not relationships:
        return None
    tables = list(missing) or []
    related = {str(r.get(side)) for r in arguments.get("relationships") or [] if isinstance(r, dict)
               for side in ("left_request_id", "right_request_id")}
    if relationships:
        for request in arguments["data_requests"]:
            if isinstance(request, dict) and request.get("data_request_id") in related and request.get("source_table"):
                if request["source_table"] not in tables:
                    tables.append(str(request["source_table"]))
    calls = []
    for start in range(0, len(tables), MAX_TABLES_PER_CALL):
        chunk = tables[start:start + MAX_TABLES_PER_CALL]
        sections = ["COLUMNS"] + (["RELATIONSHIPS"] if relationships else [])
        columns = sorted({c for t in chunk for c in (missing.get(t) or {}).get("columns", [])})
        needs_contract = any((missing.get(t) or {}).get("needs") for t in chunk)
        calls.append({"tool": "get_catalog_details", "arguments": {
            "table_names": chunk, "sections": sections,
            # all columns when a table contract is missing too; otherwise only the unread ones
            "column_names": None if needs_contract or not columns else columns[:MAX_COLUMN_FILTER],
            "entity_ids": None}})
    for entry in missing.values():
        for key in ("needs", "columns"):
            if not entry[key]:
                entry.pop(key)
    return {"tables": list(missing.values()), "relationship_ids": relationships, "calls": calls}
