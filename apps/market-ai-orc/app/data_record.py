"""M47 (user decision 2026-10-01): the conversation's data record.

What a conversation has used and read of the data: per table the columns its approved data needs extracted and the
catalog columns a run read, the needs themselves, the released outputs (with their short reference alias), and the
research angles' data contracts. It is built from results the runs already receive, carried from step to step of a mode
4 turn and from turn to turn of a server-side conversation (independent of the history budget), offered to the model
as one bounded note, and returned with the response. Nothing in it is a number from the data, so it never becomes a
provenance source.
"""
from __future__ import annotations

import copy
import re
from typing import Any

VERSION = 1
MAX_NEEDS = 20
MAX_OUTPUTS = 40
MAX_RESEARCH = 12
MAX_NOTE_CHARS = 8000
MAX_VALUES_SHOWN = 20  # a longer value list is shown as its first values plus how many more there are
MAX_FACTS = 60

NOTE_HEADER = ("DATA RECORD (application context: the data this conversation has already used and read, kept by the "
               "backend; not from the user). Tables and columns listed here were read from the catalog in this "
               "conversation: reuse them without reading their catalog details again, and read the catalog only for "
               "data that is not listed. Released outputs keep their ref for get_session_output; an output of "
               "another message is referenced only after it is read in this run.")


def empty() -> dict[str, Any]:
    return {"version": VERSION, "tables": {}, "needs": [], "outputs": [], "research": [], "next_alias": 1,
            "values": {}, "relationships": {}, "coverage": {}}


def normalize(record: Any) -> dict[str, Any]:
    """A stored or passed record in the current shape; anything unreadable starts empty."""
    if not isinstance(record, dict) or record.get("version") != VERSION:
        return empty()
    clean = empty()
    for name, table in (record.get("tables") or {}).items():
        if isinstance(table, dict):
            clean["tables"][str(name)] = {"used": sorted({str(c) for c in table.get("used") or []}),
                                          "read": sorted({str(c) for c in table.get("read") or []}),
                                          "time_column": table.get("time_column"),
                                          "entity_column": table.get("entity_column"),
                                          "requests": [str(r) for r in table.get("requests") or []][-5:]}
    for key in ("needs", "outputs", "research"):
        clean[key] = [dict(item) for item in record.get(key) or [] if isinstance(item, dict)]
    for key in ("values", "relationships", "coverage"):
        clean[key] = {str(k): dict(v) for k, v in (record.get(key) or {}).items() if isinstance(v, dict)}
    stored = record.get("next_alias")
    clean["next_alias"] = max(stored if isinstance(stored, int) and stored > 0 else 1,
                              max((_alias_number(o.get("ref")) for o in clean["outputs"]), default=0) + 1)
    return clean


def _alias_number(ref: Any) -> int:
    match = re.fullmatch(r"out\.o(\d+)", str(ref or ""))
    return int(match.group(1)) if match else 0


def aliases(record: dict[str, Any]) -> tuple[dict[str, str], int]:
    """P18: the conversation's alias of each released output (output_id -> o<n>) and the next number to give. The
    numbering never restarts (next_alias outlives outputs dropped past MAX_OUTPUTS), so o1 always names the same
    output; of two outputs a record written before this fix gave the same alias, the newer keeps it."""
    by_alias: dict[str, str] = {}
    for output in record["outputs"]:
        if _alias_number(output.get("ref")) and output.get("output_id"):
            by_alias[str(output["ref"])[4:]] = str(output["output_id"])
    return {output_id: alias for alias, output_id in by_alias.items()}, record["next_alias"]


def copy_of(record: Any) -> dict[str, Any]:
    return copy.deepcopy(normalize(record))


def _table(record: dict[str, Any], name: str) -> dict[str, Any]:
    return record["tables"].setdefault(str(name), {"used": [], "read": [], "time_column": None,
                                                   "entity_column": None, "requests": []})


def _note_request(table: dict[str, Any], request_id: str) -> None:
    if request_id and request_id not in table["requests"]:
        table["requests"] = (table["requests"] + [request_id])[-5:]


def add_need(record: dict[str, Any], request_id: str, result: dict[str, Any], mode: str | None = None) -> None:
    """An approved data need (submit_data_need_spec): its tables and extracted columns, and the need itself."""
    approved = result.get("approved")
    if not isinstance(approved, dict) or not result.get("need_id"):
        return
    requests = []
    for entry in approved.get("requests") or []:
        if not isinstance(entry, dict) or not entry.get("source_table"):
            continue
        table = _table(record, entry["source_table"])
        table["used"] = sorted(set(table["used"]) | {str(c) for c in entry.get("extract_columns") or []})
        _note_request(table, request_id)
        requests.append({"data_request_id": entry.get("data_request_id"), "logical_name": entry.get("logical_name"),
                         "source_table": entry["source_table"], "columns": list(entry.get("extract_columns") or []),
                         "ranges": [{k: r.get(k) for k in ("range_id", "start", "end")}
                                    for r in entry.get("ranges") or [] if isinstance(r, dict)][:6],
                         "scope_sha256": entry.get("scope_sha256")})
    needs = [n for n in record["needs"] if n.get("need_id") != result["need_id"]]
    needs.append({"need_id": result["need_id"], "request_id": request_id, "mode": mode,
                  "spec_sha256": approved.get("spec_sha256"), "catalog_sha256": approved.get("catalog_sha256"),
                  "requests": requests})
    record["needs"] = needs[-MAX_NEEDS:]


def add_catalog(record: dict[str, Any], tables: dict[str, Any], request_id: str) -> None:
    """Catalog details a run read (the run's catalog ledger: table -> TableSeen)."""
    for name, seen in tables.items():
        columns = getattr(seen, "columns", None) or set()
        if not columns and not getattr(seen, "contract", False):
            continue
        table = _table(record, name)
        table["read"] = sorted(set(table["read"]) | {str(c) for c in columns})
        table["time_column"] = getattr(seen, "time_column", None) or table["time_column"]
        table["entity_column"] = getattr(seen, "entity_column", None) or table["entity_column"]
        _note_request(table, request_id)


def add_output(record: dict[str, Any], request_id: str, *, alias: str, output_id: str, session_id: str | None,
               name: Any, columns: list[str], row_count: Any) -> None:
    outputs = [o for o in record["outputs"] if o.get("output_id") != output_id]
    outputs.append({"ref": f"out.{alias}", "output_id": output_id, "session_id": session_id, "name": name,
                    "columns": columns[:30], "row_count": row_count, "request_id": request_id})
    record["outputs"] = outputs[-MAX_OUTPUTS:]
    record["next_alias"] = max(record.get("next_alias") or 1, _alias_number(f"out.{alias}") + 1)


def add_research(record: dict[str, Any], request_id: str, feasible: dict[str, Any]) -> None:
    """The data contracts of a FEASIBLE research data plan, per angle."""
    for angle_id, contract in sorted((feasible.get("angle_data_contracts") or {}).items()):
        if not isinstance(contract, dict):
            continue
        datasets = []
        for dataset in contract.get("datasets") or []:
            if isinstance(dataset, dict) and dataset.get("source_table"):
                table = _table(record, dataset["source_table"])
                table["used"] = sorted(set(table["used"]) | {str(c) for c in dataset.get("columns") or []})
                _note_request(table, request_id)
                datasets.append({"source_table": dataset["source_table"],
                                 "columns": list(dataset.get("columns") or [])[:30]})
        research = [r for r in record["research"] if r.get("angle_id") != angle_id]
        research.append({"angle_id": angle_id, "request_id": request_id, "datasets": datasets})
        record["research"] = research[-MAX_RESEARCH:]


def add_catalog_facts(record: dict[str, Any], tool: str, arguments: dict[str, Any] | None, result: dict[str, Any],
                      request_id: str, checked_at: str) -> None:
    """P5 (2026-10-01, ma-steps m01): the later steps read the catalog again for what the record did not hold:
    category values (Industry "Banks"), relationships and data coverage. They are kept from the results the run already
    received, with when they were read; nothing is typed by hand."""
    if tool == "get_dimension_values" and result.get("status") == "VALUES_READY" and result.get("table"):
        key = f"{result['table']}.{result.get('column')}"
        entry = record["values"].get(key) or {"values": [], "complete": False}
        entry["values"] = sorted(set(entry["values"]) | {str(v) for v in result.get("values") or []})
        entry["complete"] = bool(entry["complete"] or (result.get("match") is None and not result.get("truncated")))
        entry.update(checked_at=checked_at, request_id=request_id)
        record["values"][key] = entry
    if tool != "get_catalog_details":
        return
    sections = result.get("sections") if isinstance(result.get("sections"), dict) else {}
    for rel in ((sections.get("RELATIONSHIPS") or {}).get("entries") or []):
        if isinstance(rel, dict) and rel.get("relationship_id") is not None:
            record["relationships"][str(rel["relationship_id"])] = {
                k: rel.get(k) for k in ("left_table", "left_columns", "right_table", "right_columns", "temporal_rule",
                                        "relationship_type", "supported_join_semantics") if rel.get(k) is not None}
    for name, cov in (((sections.get("COVERAGE") or {}).get("datasets")) or {}).items():
        if isinstance(cov, dict):
            record["coverage"][str(name)] = {
                **{k: cov.get(k) for k in ("actual_min_date", "actual_max_date", "expected_min_date",
                                           "expected_max_date", "last_checked_at") if cov.get(k) is not None},
                "read_at": checked_at}
    for key in ("relationships", "coverage", "values"):
        if len(record[key]) > MAX_FACTS:
            record[key] = dict(list(record[key].items())[-MAX_FACTS:])


def seed_ledger(record: dict[str, Any], ledger: Any) -> None:
    """Tables and columns of the record count as read in this run (the catalog protocol and the prompt agree)."""
    for name, table in record["tables"].items():
        seen = ledger.table(name)
        seen.contract = True
        seen.time_column = seen.time_column or table.get("time_column")
        seen.entity_column = seen.entity_column or table.get("entity_column")
        seen.columns.update(table.get("used") or [])
        seen.columns.update(table.get("read") or [])


def is_empty(record: dict[str, Any] | None) -> bool:
    return not record or not any(record.get(k) for k in ("tables", "needs", "outputs", "values", "relationships"))


def note(record: dict[str, Any]) -> str:
    """The record as one prompt note, newest first, within MAX_NOTE_CHARS: tables and their columns always come
    first; needs, outputs and research angles are listed while they fit."""
    lines = [NOTE_HEADER, "Tables (columns used; columns read from the catalog):"]
    for name, table in sorted(record["tables"].items()):
        extra = sorted(set(table["read"]) - set(table["used"]))
        keys = ", ".join(f"{k}={table[k]}" for k in ("entity_column", "time_column") if table.get(k))
        lines.append(f"- {name}" + (f" [{keys}]" if keys else "") + f": used {', '.join(table['used']) or 'none'}"
                     + (f"; also read {', '.join(extra)}" if extra else ""))
    def shown(values: list[str]) -> str:
        more = len(values) - MAX_VALUES_SHOWN
        return ", ".join(values[:MAX_VALUES_SHOWN]) + (f" … and {more} more (not shown)" if more > 0 else "")

    sections = [("Category values read (exact stored values; complete = every value of the column):", [
        f"- {key}: {shown(v.get('values') or [])}" + (" [complete]" if v.get("complete") else " [only those read]")
        + f" (read {v.get('checked_at')})" for key, v in sorted(record.get("values", {}).items())]),
        ("Relationships read:", [
            f"- {rid}: {r.get('left_table')}({', '.join(r.get('left_columns') or [])}) -> {r.get('right_table')}("
            f"{', '.join(r.get('right_columns') or [])}) {r.get('temporal_rule') or ''}".rstrip()
            for rid, r in sorted(record.get("relationships", {}).items())]),
        ("Approved data needs (newest first):", [
        f"- {n.get('need_id')} ({n.get('mode') or 'ANALYSIS'}, {n.get('request_id')}): " + "; ".join(
            f"{r.get('logical_name')}={r.get('source_table')}({', '.join(r.get('columns') or [])})"
            for r in n.get("requests") or []) for n in reversed(record["needs"])]),
        ("Released outputs (newest first):", [
            f"- {o.get('ref')} = {o.get('output_id')} \"{o.get('name')}\" ({o.get('row_count')} rows; "
            f"{', '.join(o.get('columns') or [])}) session {o.get('session_id')}, {o.get('request_id')}"
            for o in reversed(record["outputs"])]),
        ("Research angles (newest first):", [
            f"- {r.get('angle_id')} ({r.get('request_id')}): " + "; ".join(
                f"{d['source_table']}({', '.join(d['columns'])})" for d in r.get("datasets") or [])
            for r in reversed(record["research"])]),
        ("Data coverage read (dates may have moved since; check again when it matters):", [
            f"- {name}: " + " ".join(f"{k}={v}" for k, v in c.items()) for name, c in sorted(record.get("coverage",
                                                                                                    {}).items())])]
    text = "\n".join(lines)
    for title, items in sections:
        if not items:
            continue
        block = [title]
        for count, item in enumerate(items):
            if len(text) + len("\n".join(block + [item])) + 120 > MAX_NOTE_CHARS:
                # P5: never cut silently; the full record is in the API response and the audit
                block.append(f"- … {len(items) - count} more not shown (the full record is kept by the backend)")
                break
            block.append(item)
        if len(block) > 1:
            text += "\n" + "\n".join(block)
    return text[:MAX_NOTE_CHARS]


def public(record: dict[str, Any] | None) -> dict[str, Any] | None:
    """The record as the API response carries it (absent when empty)."""
    return None if is_empty(record) else copy.deepcopy(record)
