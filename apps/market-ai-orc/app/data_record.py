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
import json
import re
from typing import Any

VERSION = 1
MAX_NEEDS = 20
MAX_OUTPUTS = 40
MAX_RESEARCH = 12
MAX_NOTE_CHARS = 8000
MAX_VALUES_SHOWN = 20  # a longer value list is shown as its first values plus how many more there are
MAX_FACTS = 60
MAX_FINDINGS = 30  # E1: research findings and event studies of the conversation, newest kept
# what a finding keeps for later turns: the fields an answer cites and references by path
FINDING_KEYS = ("angle_id", "hypothesis_id", "method_id", "status", "status_reason", "verdict", "verdict_reason",
                "evidence_direction", "validation_level", "sample", "sample_flag", "estimates", "comparator",
                "holdout", "multiple_testing", "angle_a", "angle_b", "confidence_level", "parameters", "units",
                "success_rule", "success_definition")
EVENT_STUDY_PREFIX = "event_study:"  # M99: the id space of recomputed event studies in the findings
MAX_ANSWERS = 30  # R-STORE (C2e): one line per earlier answer, so a turn no longer in the history is not guessed
MAX_MANUALS = 12  # 4b: method guides opened in the conversation, newest kept
MAX_MANUAL_NOTE_CHARS = 16000
# EXEC-C items 5 and 10 (AI_ENABLE_RUN_MEMORY): the note is never cut; the reference sections (column details,
# category values, relationships, coverage) beyond these budgets are named with a pointer to their full text
COLUMN_KEYS = ("description", "unit", "data_type", "semantic_type", "resample_aggregation", "cross_entity_aggregation",
               "value_time_basis", "is_primary_key")
MAX_COLUMN_TABLES = 20
MAX_COLUMNS_PER_TABLE = 150
COLUMNS_NOTE_CHARS = 14000
REFERENCE_NOTE_CHARS = 8000
MAX_READINGS = 30
MAX_SCOPE_SPEC_CHARS = 2000
MANUALS_HEADER = ("METHOD GUIDES OPENED EARLIER IN THIS CONVERSATION (application context from the backend, not from "
                  "the user): the manuals of these methods are already here, current version; do not open them "
                  "again.")

NOTE_HEADER = ("DATA RECORD (application context: the data this conversation has already used and read, kept by the "
               "backend; not from the user). Tables and columns listed here were read from the catalog in this "
               "conversation: reuse them without reading their catalog details again, and read the catalog only for "
               "data that is not listed. Released outputs keep their ref for get_session_output; an output of "
               "another message is referenced only after it is read in this run.")


def empty() -> dict[str, Any]:
    return {"version": VERSION, "tables": {}, "needs": [], "outputs": [], "research": [], "next_alias": 1,
            "values": {}, "relationships": {}, "coverage": {}, "manuals": [], "findings": [], "seq": 0,
            "suggestion": None, "answers": [], "columns": {}, "readings": [], "pause": None}


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
    clean["manuals"] = [dict(m) for m in record.get("manuals") or [] if isinstance(m, dict) and m.get("name")]
    clean["findings"] = [dict(f) for f in record.get("findings") or [] if isinstance(f, dict) and f.get("id")]
    clean["answers"] = [dict(a) for a in record.get("answers") or [] if isinstance(a, dict) and a.get("request_id")]
    clean["columns"] = {str(t): {str(c): dict(v) for c, v in cols.items() if isinstance(v, dict)}
                        for t, cols in (record.get("columns") or {}).items() if isinstance(cols, dict)}
    clean["readings"] = [dict(r) for r in record.get("readings") or [] if isinstance(r, dict) and r.get("request_id")]
    # M64: the order results and research suggestions were produced in (a record written before it has none)
    seq = record.get("seq")
    clean["seq"] = seq if isinstance(seq, int) and seq > 0 else 0
    suggestion = record.get("suggestion")
    clean["suggestion"] = dict(suggestion) if isinstance(suggestion, dict) and suggestion.get("plan_id") else None
    # EXEC-W A1 (M121): the answer that paused and the choices it asked; the next message answers it
    pause = record.get("pause")
    clean["pause"] = dict(pause) if isinstance(pause, dict) and pause.get("cause") else None
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


# M68: a predicate's values are shown in full up to this many characters; beyond it the count of the rest is stated
SCOPE_VALUES_MAX_CHARS = 400


def _scope_values(scope: dict[str, Any]) -> list[Any] | None:
    """The values of a predicate in either form: the sandbox's canonical scope carries ``values`` (a list; M68), the
    model's DataNeed and definition filters carry ``value`` (a scalar or a list); None when the predicate has none."""
    if "values" in scope and scope["values"] is not None:
        values = scope["values"]
        return list(values) if isinstance(values, (list, tuple)) else [values]
    value = scope.get("value")
    if value is None:
        return None
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _values_text(values: list[Any]) -> str:
    shown: list[str] = []
    used = 0
    for item in values:
        text = str(item)
        if shown and used + len(text) + 2 > SCOPE_VALUES_MAX_CHARS:
            return ", ".join(shown) + f", … (+{len(values) - len(shown)} more of {len(values)} values)"
        shown.append(text)
        used += len(text) + 2
    return ", ".join(shown)


def scope_text(scope: Any) -> str:
    """A DataNeed scope (ALL / PREDICATE / AND / OR / NOT) as one readable line, e.g. "Industry EQ Banks". Reads both
    the model's form (``value``, NOT with ``child``) and the sandbox's canonical form (``values``, NOT with
    ``children``), so a scope read back from the sandbox keeps its values (M68)."""
    if not isinstance(scope, dict):
        return "all rows"
    kind = scope.get("type")
    if kind == "PREDICATE":
        values = _scope_values(scope)
        shown = "" if values is None else " " + _values_text(values)
        return f"{scope.get('column')} {scope.get('operator')}{shown}"
    if kind in ("AND", "OR"):
        return "(" + f" {kind} ".join(scope_text(c) for c in scope.get("children") or []) + ")"
    if kind == "NOT":
        child = scope.get("child")
        if child is None and scope.get("children"):
            child = scope["children"][0]
        return f"NOT {scope_text(child)}"
    return "all rows"


def definition_text(definition: Any) -> str:
    """A released output's definition (filters in the DataNeed grammar, period, entities, thresholds, notes) as one
    readable line; {} reads as no filter beyond the data request."""
    if not isinstance(definition, dict):
        return "NOT STATED"
    parts = []
    filters = [scope_text({"type": "PREDICATE", **f}) for f in definition.get("filters") or [] if isinstance(f, dict)]
    parts.append("filters: " + ("; ".join(filters) if filters else "none beyond the data request"))
    period = definition.get("period")
    if isinstance(period, dict) and (period.get("start") or period.get("end")):
        parts.append(f"period {period.get('start')}..{period.get('end')}")
    if definition.get("entities"):
        parts.append(f"entities {definition['entities']}")
    if isinstance(definition.get("thresholds"), dict) and definition["thresholds"]:
        parts.append("thresholds " + ", ".join(f"{k}={v}" for k, v in definition["thresholds"].items()))
    if definition.get("notes"):
        parts.append(f"notes: {definition['notes']}")
    return "; ".join(parts)


MAX_NEED_RELATIONSHIPS = 8


def _subject_text(subject: Any) -> str | None:
    """EXEC-D P-h: the need's subject as data_domain/entity_type/asset_type."""
    if not isinstance(subject, dict):
        return None
    parts = [str(subject[k]) for k in ("data_domain", "entity_type", "asset_type") if subject.get(k)]
    return "/".join(parts) or None


def _relationship_text(relation: dict[str, Any]) -> str:
    """EXEC-D P-h: one relationship the need declared, compact (data_need_spec v1 or v2)."""
    left = relation.get("left_columns") or ([relation["left_column"]] if relation.get("left_column") else [])
    right = relation.get("right_columns") or ([relation["right_column"]] if relation.get("right_column") else [])
    return (f"{relation.get('left_request_id')}.{'+'.join(map(str, left))} = "
            f"{relation.get('right_request_id')}.{'+'.join(map(str, right))} ({relation.get('join_type')}, "
            f"{relation.get('join_semantics')}, relationship {relation.get('relationship_id')})")


def add_need(record: dict[str, Any], request_id: str, result: dict[str, Any], mode: str | None = None,
             subject: Any = None, relationships: Any = None) -> None:
    """An approved data need (submit_data_need_spec): its tables and extracted columns, and the need itself. EXEC-D P-h
    (M106): with the subject and the relationships it declared (from its arguments; the approved view has neither), so a
    later run does not look them up in the catalog again."""
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
                         "scope_sha256": entry.get("scope_sha256"),
                         # H1 (M63): the row filter the backend applied, readable (DERIVED)
                         **({"scope": scope_text(entry["scope"])} if entry.get("scope") else {}),
                         # EXEC-Y Fase 3 E1(1): the canonical filter itself, so an export can count the same rows in
                         # the source (a long filter is left out and the file says it was not checked)
                         **({"scope_spec": entry["scope"]} if isinstance(entry.get("scope"), dict)
                            and len(json.dumps(entry["scope"], default=str)) <= MAX_SCOPE_SPEC_CHARS else {}),
                         **({"restrictions": [f"{x.get('right_table')}: {scope_text(x.get('right_scope'))}"
                                              for x in entry["restrictions"] if isinstance(x, dict)]}
                            if entry.get("restrictions") else {})})
    needs = [n for n in record["needs"] if n.get("need_id") != result["need_id"]]
    entry: dict[str, Any] = {"need_id": result["need_id"], "request_id": request_id, "mode": mode,
                             "spec_sha256": approved.get("spec_sha256"),
                             "catalog_sha256": approved.get("catalog_sha256"), "requests": requests}
    if _subject_text(subject):
        entry["subject"] = _subject_text(subject)
    joins = [_relationship_text(r) for r in relationships or [] if isinstance(r, dict)][:MAX_NEED_RELATIONSHIPS]
    if joins:
        entry["relationships"] = joins
    needs.append(entry)
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


def _next_seq(record: dict[str, Any]) -> int:
    record["seq"] = int(record.get("seq") or 0) + 1
    return record["seq"]


def add_output(record: dict[str, Any], request_id: str, *, alias: str, output_id: str, session_id: str | None,
               name: Any, columns: list[str], row_count: Any, label: str | None = None,
               kind: str | None = None, definition: dict[str, Any] | None = None,
               lineage: dict[str, Any] | None = None) -> None:
    earlier = next((o for o in record["outputs"] if o.get("output_id") == output_id), None)
    outputs = [o for o in record["outputs"] if o.get("output_id") != output_id]
    # M64: an output read again keeps the place it was produced at; only a new output is newer than what came before
    seq = earlier.get("seq") if earlier is not None and isinstance(earlier.get("seq"), int) else _next_seq(record)
    outputs.append({"ref": f"out.{alias}", "output_id": output_id, "session_id": session_id, "name": name,
                    "columns": columns[:30], "row_count": row_count, "request_id": request_id, "seq": seq,
                    **({"label": label} if label else {}), **({"type": kind} if kind else {}),
                    # H1: how it was made and what produced it (an output read again keeps what it had)
                    **({"definition": definition} if isinstance(definition, dict)
                       else {"definition": earlier["definition"]} if earlier and "definition" in earlier else {}),
                    **({"lineage": lineage} if isinstance(lineage, dict)
                       else {"lineage": earlier["lineage"]} if earlier and "lineage" in earlier else {}),
                    # R-STORE: the last date of the data it was computed from, and whether the conversation keeps it
                    **({"data_as_of": d} if (d := (lineage or {}).get("data_as_of") if isinstance(lineage, dict)
                                              else (earlier or {}).get("data_as_of")) else {}),
                    **({"stored": earlier["stored"]} if earlier and "stored" in earlier else {})})
    record["outputs"] = outputs[-MAX_OUTPUTS:]
    record["next_alias"] = max(record.get("next_alias") or 1, _alias_number(f"out.{alias}") + 1)


def add_answer(record: dict[str, Any], request_id: str, *, question: str, response_type: str | None, answer: str,
               data_as_of: str | None) -> None:
    """R-STORE (C2e): one line per answer of the conversation (what was asked, the start of the answer, the outputs
    it released and its data date), so a later turn knows what an answer that left the history said instead of
    guessing it. Kept only for a conversation that used data (the record is the data record)."""
    refs = [o.get("ref") for o in record["outputs"] if o.get("request_id") == request_id and o.get("ref")]
    findings = [f.get("id") for f in record.get("findings") or [] if f.get("request_id") == request_id]
    answers = [a for a in record.get("answers") or [] if a.get("request_id") != request_id]
    answers.append({"request_id": request_id, "seq": _next_seq(record), "question": " ".join(question.split())[:200],
                    "response_type": response_type, "summary": " ".join((answer or "").split())[:300],
                    "outputs": refs[:10], "findings": findings[:10],
                    **({"data_as_of": data_as_of} if data_as_of else {})})
    record["answers"] = answers[-MAX_ANSWERS:]


def mark_stored(record: dict[str, Any], stored: dict[str, str]) -> None:
    """R-STORE: which outputs the conversation keeps (output_id -> POSTGRES, BUCKET, ALREADY_STORED or FAILED)."""
    for output in record["outputs"]:
        if output.get("output_id") in stored:
            output["stored"] = stored[output["output_id"]] != "FAILED"


def data_as_of(record: dict[str, Any]) -> str | None:
    """The conversation's data date: the latest data_as_of of its released outputs (None before any)."""
    dates = [str(o["data_as_of"]) for o in record.get("outputs") or [] if o.get("data_as_of")]
    return max(dates) if dates else None


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
    columns = sections.get("COLUMNS") if isinstance(sections.get("COLUMNS"), dict) else {}
    by_table = columns.get("by_table") if isinstance(columns.get("by_table"), dict) else {}
    if not by_table:
        for entry in columns.get("entries") or []:
            if isinstance(entry, dict) and entry.get("table_name"):
                by_table.setdefault(str(entry["table_name"]), []).append(entry)
    for table, entries in by_table.items():
        # EXEC-C item 10: the meaning, unit and aggregation rules of each column read, not only its name
        kept = record["columns"].pop(str(table), {})
        for entry in entries or []:
            if isinstance(entry, dict) and entry.get("column_name"):
                kept[str(entry["column_name"])] = {k: entry[k] for k in COLUMN_KEYS if entry.get(k) is not None}
        record["columns"][str(table)] = dict(list(kept.items())[-MAX_COLUMNS_PER_TABLE:])
    if len(record["columns"]) > MAX_COLUMN_TABLES:
        record["columns"] = dict(list(record["columns"].items())[-MAX_COLUMN_TABLES:])
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


def has_data(record: dict[str, Any] | None) -> bool:
    return bool(record) and any(record.get(k) for k in ("tables", "needs", "outputs", "values", "relationships",
                                                         "findings"))


def add_finding(record: dict[str, Any], request_id: str, *, kind: str, finding_id: str, finding: dict[str, Any],
                recorded_at: str | None = None) -> None:
    """E1 (MODE4_CONVERSATION_PLAN.md): a backend finding of this conversation (ANGLE of a multi-angle run,
    HYPOTHESIS of a hypothesis plan, EVENT_STUDY of a recomputed event study), kept so a later turn can explain and
    cite it as finding.<id> without running the research again; the newest of one id replaces the older. The
    findings are also the conversation's trial ledger: every test that ran, in order."""
    kept = {k: copy.deepcopy(finding[k]) for k in (*FINDING_KEYS, "in_sample") if k in finding}
    for key, value in finding.items():
        if kind == "EVENT_STUDY" and key not in kept:
            kept[key] = copy.deepcopy(value)
    findings = record.get("findings") or []
    if kind == "EVENT_STUDY" and not finding_id.startswith(EVENT_STUDY_PREFIX):
        # M99 (re-test ma-qa-20261006f): an event study the model named like its hypothesis ("vol2x_up3d") took the
        # hypothesis's id, which was archived as vol2x_up3d@1, so finding.vol2x_up3d no longer was the test; an event
        # study is cited from its tables, so its id has its own prefix and never displaces a finding's
        finding_id = EVENT_STUDY_PREFIX + finding_id
    earlier = next((f for f in findings if f.get("id") == finding_id), None)
    if earlier is not None and any((earlier.get("finding") or {}).get(k) != kept.get(k)
                                   for k in ("success_rule", "parameters")):
        # H2 (user decision 2026-10-02): a test run again with another rule (e.g. "ubah jadi 5%") does not erase the
        # earlier result; it stays as <id>@<n> so the answer can show both
        archived = sum(1 for f in findings if str(f.get("id") or "").startswith(f"{finding_id}@"))
        earlier["id"] = f"{finding_id}@{archived + 1}"
    else:
        findings = [f for f in findings if f.get("id") != finding_id]
    record["findings"] = findings
    record["findings"].append({"id": finding_id, "kind": kind, "request_id": request_id, "recorded_at": recorded_at,
                               "seq": _next_seq(record), "finding": kept})
    del record["findings"][:-MAX_FINDINGS]


def add_reading(record: dict[str, Any], request_id: str, reading: dict[str, Any] | None) -> None:
    """EXEC-C item 13: how the router read a message of the conversation (its class or route, what it refers to, the
    design values it named and the understood intent), kept for the turns after it."""
    if not isinstance(reading, dict):
        return
    kept = {k: reading[k] for k in ("route", "turn_kind", "choice", "referent", "design_value_changes",
                                     "understood_intent", "status") if reading.get(k) not in (None, "", [], {})}
    if not kept:
        return
    readings = [r for r in record.get("readings") or [] if r.get("request_id") != request_id]
    readings.append({"request_id": request_id, **copy.deepcopy(kept)})
    record["readings"] = readings[-MAX_READINGS:]


def mark_suggestion(record: dict[str, Any], plan_id: str, request_id: str) -> None:
    """M64: a research suggestion (a plan waiting for the user's decision) was issued now; results produced later are
    newer than it. Issuing the same plan again keeps its place."""
    current = record.get("suggestion")
    if isinstance(current, dict) and current.get("plan_id") == plan_id:
        return
    record["suggestion"] = {"plan_id": plan_id, "request_id": request_id, "seq": int(record.get("seq") or 0)}


def results_after_suggestion(record: dict[str, Any] | None, plan_id: str | None) -> list[str] | None:
    """M64: the results (released outputs and findings, newest last) produced after the pending suggestion was issued;
    None when the record does not know when it was issued (an older record, or another plan)."""
    suggestion = (record or {}).get("suggestion")
    if not plan_id or not isinstance(suggestion, dict) or suggestion.get("plan_id") != plan_id:
        return None
    issued = int(suggestion.get("seq") or 0)
    later = [(o["seq"], f"{o.get('ref')} {o.get('name')}") for o in (record or {}).get("outputs") or []
             if isinstance(o.get("seq"), int) and o["seq"] > issued]
    later += [(f["seq"], f"finding.{str(f.get('id')).removeprefix(EVENT_STUDY_PREFIX)} ({f.get('kind')})")
              for f in (record or {}).get("findings") or [] if isinstance(f.get("seq"), int) and f["seq"] > issued]
    return [name for _, name in sorted(later)]


def is_empty(record: dict[str, Any] | None) -> bool:
    return not has_data(record) and not (record or {}).get("manuals") and not (record or {}).get("suggestion") \
        and not (record or {}).get("readings") and not (record or {}).get("pause")


def finding_line(entry: dict[str, Any]) -> str:
    """P3 (2026-10-02): a finding as the model reads it in later turns: what was tested, its status and how it was
    checked, and its key figures (to interpret, not to cite: an answer cites them as finding.<id>)."""
    f = entry.get("finding") or {}
    parts = [f"{k}={f[k]}" for k in ("method_id", "status", "verdict", "sample_flag", "validation_level")
             if f.get(k) is not None]
    estimates = f.get("estimates") or {}
    primary = estimates.get("primary") or {}
    if primary:
        # M65 (golden test rerun 2026-10-02): an interval and a p-value are printed in the pair they belong to,
        # labelled; the unadjusted interval once went out beside the adjusted p and the answer paired them
        unit = (estimates.get("units") or {}).get("estimate")
        parts.append(f"estimate={primary.get('estimate')}" + (f" ({unit})" if unit else ""))
        adjusted = primary.get("p_adjusted") is not None or primary.get("ci_adjusted") is not None
        if adjusted:
            parts.append(f"adjusted for multiple testing: ci={primary.get('ci_adjusted')}, "
                         f"p={primary.get('p_adjusted')}")
        parts.append(("unadjusted: " if adjusted else "") + f"ci={primary.get('ci')}, p={primary.get('p_value')}")
    angle_a = f.get("angle_a") or {}
    if angle_a:
        # research findings v1: the interval is at the adjusted confidence level, the p-value is unadjusted
        alpha = (f.get("parameters") or {}).get("alpha_adjusted")
        unit = (f.get("units") or {}).get("angle_a.difference")
        parts += [f"difference={angle_a.get('difference')}" + (f" ({unit})" if unit else ""),
                  f"ci=[{angle_a.get('ci_low')}, {angle_a.get('ci_high')}]"
                  + (f" (at alpha {alpha})" if alpha is not None else ""),
                  f"unadjusted p={angle_a.get('p_value')}"]
    rule = f.get("success_rule")
    if isinstance(rule, dict) and rule.get("operator"):
        # M28: the rule the engine applied, from the approved plan (not the plan's wording)
        parts.append(f"success rule applied: outcome {rule['operator']} {rule.get('value')}")
    sample = f.get("sample") or {}
    if sample.get("effective") is not None:
        parts.append(f"effective_sample={sample['effective']}")
    if f.get("summary_output_id"):
        parts.append(f"tables={', '.join(str(f[k]) for k in ('summary_output_id', 'events_output_id') if f.get(k))}")
    if f.get("in_sample"):
        parts.append("IN_SAMPLE (tested on data an earlier step already read)")
    return (f"- finding.{entry.get('id')} ({entry.get('kind')}, {entry.get('request_id')}"
            + (f", {entry.get('recorded_at')}" if entry.get("recorded_at") else "") + "): " + "; ".join(parts))


def add_manual(record: dict[str, Any], request_id: str, *, name: str, version: Any, sha256: str,
               guide: dict[str, Any]) -> None:
    """4b: a method guide the model opened; one entry per name (the newest replaces the older), newest last."""
    record["manuals"] = [m for m in record.get("manuals") or [] if m.get("name") != name]
    record["manuals"].append({"name": name, "version": version, "sha256": sha256, "guide": guide,
                              "request_id": request_id})
    del record["manuals"][:-MAX_MANUALS]


def manuals_note(record: dict[str, Any], current: dict[str, dict[str, Any]]) -> tuple[str | None, list[str]]:
    """The opened guides in their current version (current: name -> {sha256, version, guide}; a guide no longer offered
    is left out), newest first within MAX_MANUAL_NOTE_CHARS; the rest are named with a marker (P5). Returns the note
    and the names whose stored version was replaced by the current one (the record is updated)."""
    refreshed, shown, omitted = [], [], []
    entries = [m for m in record.get("manuals") or [] if m.get("name") in current]
    for entry in entries:
        now = current[entry["name"]]
        if entry.get("sha256") != now["sha256"]:
            entry.update(version=now["version"], sha256=now["sha256"], guide=now["guide"])
            refreshed.append(entry["name"])
    if not entries:
        return None, refreshed
    import json

    text = MANUALS_HEADER
    for entry in reversed(entries):
        block = f"\n- {entry['name']} (version {entry['version']}): " + json.dumps(
            entry["guide"], ensure_ascii=False, separators=(",", ":"))
        if len(text) + len(block) + 200 > MAX_MANUAL_NOTE_CHARS:
            omitted.append(entry["name"])
            continue
        text += block
        shown.append(entry["name"])
    if omitted:
        text += (f"\n- … {len(omitted)} more opened earlier, not shown here: {', '.join(omitted)}; open again with "
                 "get_method_guide when needed")
    return text, refreshed


# EXEC-C (AI_ENABLE_RUN_MEMORY): the header of the full note (item 10: the column details read are in it; item 11:
# an earlier output is cited by its ref, its rows read when the answer is rendered)
FULL_NOTE_HEADER = ("DATA RECORD (application context: the data this conversation has already used and read, kept by "
                    "the backend; not from the user). Tables and columns listed here were read from the catalog in "
                    "this conversation, with each column's meaning, unit and aggregation rules: reuse them without "
                    "reading their catalog details again, and read the catalog only for data that is not listed. "
                    "Released outputs keep their ref: cite an output of an earlier message by that ref directly (its "
                    "rows are read when the answer is rendered); open it with get_session_output only to see rows you "
                    "need to choose from. A section summarized here names where its full text is.")
FULL_POINTER = "read_conversation_memory(section=\"catalog\", item=\"<table>\") or section=\"data_record\""


def _column_line(name: str, info: dict[str, Any]) -> str:
    rules = ", ".join(f"{k}={info[k]}" for k in ("resample_aggregation", "cross_entity_aggregation", "value_time_basis")
                      if info.get(k))
    return (f"  - {name}" + (f" [{info['unit']}]" if info.get("unit") else "")
            + (f" ({info['data_type']})" if info.get("data_type") else "")
            + (f": {_clip(info['description'], 160)}" if info.get("description") else "")
            + (f"; {rules}" if rules else ""))


def _clip(text: Any, limit: int) -> str:
    flat = " ".join(str(text or "").split())
    return flat if len(flat) <= limit else flat[:limit - 1].rstrip() + "…"


def _need_line(need: dict[str, Any]) -> str:
    """One approved data need as the notes show it: its requests with their filters, then (EXEC-D P-h) its subject and
    the relationships it declared."""
    line = f"- {need.get('need_id')} ({need.get('mode') or 'ANALYSIS'}, {need.get('request_id')}): " + "; ".join(
        f"{r.get('logical_name')}={r.get('source_table')}({', '.join(r.get('columns') or [])})"
        + (f" where {r['scope']}" if r.get("scope") else "")
        + (f" restricted to {'; '.join(r['restrictions'])}" if r.get("restrictions") else "")
        for r in need.get("requests") or [])
    if need.get("subject"):
        line += f"; subject {need['subject']}"
    if need.get("relationships"):
        line += "; relationships " + "; ".join(need["relationships"])
    return line


def full_note(record: dict[str, Any]) -> str:
    """EXEC-C items 5 and 10: the record as one prompt note that is never cut. Tables, column details, needs,
    outputs, research angles, earlier answers, findings and the routing of earlier messages always appear in full;
    the reference sections (column details beyond COLUMNS_NOTE_CHARS, category values, relationships, coverage beyond
    REFERENCE_NOTE_CHARS) are summarized with a pointer to their full text."""
    lines = [FULL_NOTE_HEADER, "Tables (columns used; columns read from the catalog):"]
    for name, table in sorted(record["tables"].items()):
        extra = sorted(set(table["read"]) - set(table["used"]))
        keys = ", ".join(f"{k}={table[k]}" for k in ("entity_column", "time_column") if table.get(k))
        lines.append(f"- {name}" + (f" [{keys}]" if keys else "") + f": used {', '.join(table['used']) or 'none'}"
                     + (f"; also read {', '.join(extra)}" if extra else ""))
    columns = record.get("columns") or {}
    if columns:
        block, used, folded = ["Column details read (meaning, unit, type, aggregation rules):"], 0, []
        for table, entries in sorted(columns.items()):
            rows = [_column_line(name, info) for name, info in entries.items()]
            size = sum(len(r) + 1 for r in rows) + len(table) + 4
            if used + size > COLUMNS_NOTE_CHARS:
                folded.append(f"{table} ({', '.join(entries)})")
                continue
            used += size
            block += [f"- {table}:"] + rows
        if folded:
            block.append("- details not shown here (read them with " + FULL_POINTER + "): " + "; ".join(folded))
        lines += block

    def shown(values: list[str]) -> str:
        more = len(values) - MAX_VALUES_SHOWN
        return ", ".join(values[:MAX_VALUES_SHOWN]) + (f" … and {more} more (all in section data_record)"
                                                       if more > 0 else "")

    reference = [("Category values read (exact stored values; complete = every value of the column):", [
        f"- {key}: {shown(v.get('values') or [])}" + (" [complete]" if v.get("complete") else " [only those read]")
        + f" (read {v.get('checked_at')})" for key, v in sorted(record.get("values", {}).items())]),
        ("Relationships read:", [
            f"- {rid}: {r.get('left_table')}({', '.join(r.get('left_columns') or [])}) -> {r.get('right_table')}("
            f"{', '.join(r.get('right_columns') or [])}) {r.get('temporal_rule') or ''}".rstrip()
            for rid, r in sorted(record.get("relationships", {}).items())]),
        ("Data coverage read (dates may have moved since; check again when it matters):", [
            f"- {name}: " + " ".join(f"{k}={v}" for k, v in c.items()) for name, c in sorted(record.get("coverage",
                                                                                                    {}).items())])]
    used = 0
    for title, items in reference:
        if not items:
            continue
        block = [title]
        for count, item in enumerate(items):
            if used + len(item) + 1 > REFERENCE_NOTE_CHARS:
                block.append(f"- … {len(items) - count} more, not shown here (read them with "
                             "read_conversation_memory(section=\"data_record\"))")
                break
            used += len(item) + 1
            block.append(item)
        lines += block
    always = [
        ("Approved data needs (newest first; the filter each request applied):", [
            _need_line(n) for n in reversed(record["needs"])]),
        ("Released outputs (newest first):", [
            f"- {o.get('ref')} = {o.get('output_id')} \"{o.get('name')}\" "
            + (f"{o['type']} " if o.get("type") not in (None, "TABLE") else "")
            + f"({o.get('row_count')} rows; "
            f"{', '.join(o.get('columns') or [])}) session {o.get('session_id')}, {o.get('request_id')}"
            + (f", label {o['label']}" if o.get("label") else "")
            + (f", data to {o['data_as_of']}" if o.get("data_as_of") else "")
            + f"; definition: {definition_text(o.get('definition'))}"
            for o in reversed(record["outputs"])]),
        ("Research angles (newest first):", [
            f"- {r.get('angle_id')} ({r.get('request_id')}): " + "; ".join(
                f"{d['source_table']}({', '.join(d['columns'])})" for d in r.get("datasets") or [])
            for r in reversed(record["research"])]),
        ("Earlier answers of this conversation (newest first; the full texts are in the history and the conversation "
         "memory):", [
            f"- {a.get('request_id')} [{a.get('response_type')}] Q: {a.get('question')} | A: {a.get('summary')}"
            + (f" | outputs {', '.join(a['outputs'])}" if a.get("outputs") else "")
            + (f" | data to {a['data_as_of']}" if a.get("data_as_of") else "")
            for a in reversed(record.get("answers") or [])]),
        ("Findings of this conversation (newest first; cite as finding.<id>, they are not run again unless the user "
         "asks):", [finding_line(f) for f in reversed(record.get("findings") or [])]),
        ("How the router read earlier messages (newest first):", [
            f"- {r.get('request_id')}: " + "; ".join(
                f"{k}={r[k]}" for k in ("route", "turn_kind", "choice", "referent", "understood_intent", "status")
                if r.get(k))
            + (f"; design values {r['design_value_changes']}" if r.get("design_value_changes") else "")
            for r in reversed(record.get("readings") or [])])]
    for title, items in always:
        if items:
            lines += [title] + items
    return "\n".join(lines)


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
        ("Approved data needs (newest first; the filter each request applied):", [
            _need_line(n) for n in reversed(record["needs"])]),
        ("Released outputs (newest first):", [
            f"- {o.get('ref')} = {o.get('output_id')} \"{o.get('name')}\" "
            + (f"{o['type']} " if o.get("type") not in (None, "TABLE") else "")
            + f"({o.get('row_count')} rows; "
            f"{', '.join(o.get('columns') or [])}) session {o.get('session_id')}, {o.get('request_id')}"
            + (f", label {o['label']}" if o.get("label") else "")
            + (f", data to {o['data_as_of']}" if o.get("data_as_of") else "")
            + f"; definition: {definition_text(o.get('definition'))}"
            for o in reversed(record["outputs"])]),
        ("Research angles (newest first):", [
            f"- {r.get('angle_id')} ({r.get('request_id')}): " + "; ".join(
                f"{d['source_table']}({', '.join(d['columns'])})" for d in r.get("datasets") or [])
            for r in reversed(record["research"])]),
        ("Earlier answers of this conversation (newest first; a turn no longer in the history is known only from "
         "this line: never guess what else it said):", [
            f"- {a.get('request_id')} [{a.get('response_type')}] Q: {a.get('question')} | A: {a.get('summary')}"
            + (f" | outputs {', '.join(a['outputs'])}" if a.get("outputs") else "")
            + (f" | data to {a['data_as_of']}" if a.get("data_as_of") else "")
            for a in reversed(record.get("answers") or [])]),
        ("Findings of this conversation (newest first; cite as finding.<id>, they are not run again unless the user asks):", [
            finding_line(f) for f in reversed(record.get("findings") or [])]),
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
