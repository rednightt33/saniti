"""EXEC-C (EXEC.md; user decisions 2026-10-06: "Seharusnya AI membawa semuanya tanpa terkecuali", Q1 "pakai MEMO",
Q2 "BACKEND + AI"; AI_ENABLE_RUN_MEMORY): every run of a server-side conversation leaves a memory for the runs after
it, its turns and the steps of a mode 4 turn alike.

One row per run (run_id = the run's request id; a mode 4 step has its own, <request_id>-m4a ...) in
"AI_conversation_run_memory" (migration 20261006_003), deleted with its conversation:
- memo: the run's block for the prompt of later runs, written by the backend from what the run recorded (tools, the
  results it released, the design values with their origin, every refusal of a gate or a tool, the web facts, the
  code it ran, the catalog it read) plus the note the run's own model wrote in its final response (memo_note, Q2).
  It is rendered once, when the run ends, and never changes, so the note of later runs grows only at its end
  (oldest first): the prompt prefix of run N+1 is that of run N up to the end of run N's memos (EXEC-S cache).
- content: the full texts the memo names (the message, the answer with its assumptions, limitations and methodology,
  each refusal message and the draft it refused, the plan, the web entries, the design values, the catalog details).
- sources: what the run registered as citable (fact, metric, reference, web, and the content of a JSON output), so a
  later run registers it again under the same address and cites it without reading it again (item 11). A figure
  typed from a memo or an earlier answer is still not a source.
- reasoning: the run's full reasoning text (Q1 b: the memo goes into the prompt; the reasoning is kept and read on
  request). It stays out of the prompt and out of the audit store (audit_outbox refuses reasoning).

read_conversation_memory (READS, on every desk) returns a run's sections in pages of PAGE_CHARS (offset and
next_offset): nothing is cut without a pointer to the rest. Storing never fails an answer: a failure is logged
(run_memory_failed) and the run's answer is unchanged.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger("market_ai_orc")

VERSION = 1
PAGE_CHARS = 20_000  # one page of a section read with read_conversation_memory
MAX_REASONING_CHARS = 400_000  # per run; a longer reasoning keeps its start and says how long it was
MAX_DRAFT_CHARS = 60_000  # a refused draft kept with its refusal
MAX_ARGUMENT_CHARS = 8_000  # the arguments of a refused tool call
MAX_SOURCES_BYTES = 512_000  # the citable values one run keeps for later runs (JSON)
MAX_JSON_OUTPUT_BYTES = 64_000  # a JSON output's content kept as a source
MAX_MEMO_NOTE_CHARS = 120_000  # the memos given to one run; older memos beyond it are named with a pointer
NOTE_CHARS = 3_000  # the model's own note (a few sentences are asked for)
SHOWN = 200  # characters of a message, a refusal or a quote in a memo line; the full text is in content
ANSWER_SHOWN = 300
SOURCE_NAMESPACES = ("fact", "metric", "reference", "web")
RUN_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,200}$")
SECTIONS = ("memo", "message", "answer", "note", "plan", "refusals", "decisions", "web", "code", "catalog", "sources",
            "reasoning")
RECORD_SECTIONS = ("catalog", "data_record")  # read without run_id: from the conversation's data record

MEMORY_HEADER = (
    "CONVERSATION MEMORY (application context kept by the backend, not from the user): one memo per earlier run of "
    "this conversation (its earlier turns and the steps of this turn), oldest first; a memo is added when a run ends "
    "and never changes. A memo lists what the run did, decided (and where each value came from), was refused (the "
    "gate or tool, the code and the start of the message), released and found, and the note its model left for later "
    "runs. The addresses a memo lists as citable are registered in this run under the same address: cite them "
    "directly, without reading them again. A figure copied from a memo or an earlier answer is not a source. The full "
    "texts (the message, the answer with its assumptions, limitations and methodology, each refusal with the draft it "
    "refused, the plan, the code, the reasoning, the web quotes and the catalog details) are read with "
    "read_conversation_memory(run_id, section).")
MEMO_NOTE_CONTRACT = (
    "memo_note: a note for your own later runs of this conversation, never shown to the user: what you concluded and "
    "why, what you tried that failed and why, the choices you made and what is still open, in a few short sentences; "
    "null for a CLARIFICATION. ")
MEMO_NOTE_PROPERTY: dict[str, Any] = {
    "type": ["string", "null"],
    "description": ("A note for your own later runs of this conversation, never shown to the user: what you "
                    "concluded and why, what failed and why, your choices and what is still open; null for a "
                    "CLARIFICATION."),
}
DESCRIPTION = (
    "Read what an earlier run of this conversation kept: its memo, the message, the full answer (with assumptions, "
    "limitations and methodology), the model's note, the plan, every refusal with the draft it refused, the design "
    "values and their origin, the web facts with quotes and links, the code it ran, the catalog details it read, the "
    "values it made citable, or its reasoning. Without run_id: the list of runs. Long texts come in pages: call again "
    "with next_offset. No new data is read.")


def clip(text: Any, limit: int = SHOWN) -> str:
    """One line of at most limit characters; a longer text ends with … (the memo names where the full text is)."""
    flat = " ".join(str(text or "").split())
    return flat if len(flat) <= limit else flat[:limit - 1].rstrip() + "…"


# ------------------------------------------------------------------------------------------------ the memo block


def _counts(counts: dict[str, int]) -> str:
    return ", ".join(f"{name}×{count}" for name, count in counts.items())


def memo_block(run: dict[str, Any]) -> str:
    """The run's memo as later runs read it. run: the facts the orchestrator collected (see AgentOrchestrator
    ._run_memory_facts). Lines without content are left out; every shortened text names its section."""
    head = f"## {run['run_id']} ({run.get('step') or 'RUN'}; {run.get('status')}"
    head += f", {run['response_type']}" if run.get("response_type") else ""
    head += f", error {run['error_code']}" if run.get("error_code") else ""
    head += f"; {run['at']})" if run.get("at") else ")"
    lines = [head]
    if run.get("message"):
        lines.append(f"- message: \"{clip(run['message'])}\"" + (" (full: message)" if len(run["message"]) > SHOWN
                                                                 else ""))
    if run.get("tools"):
        refused = run.get("tools_refused") or {}
        lines.append("- tools: " + _counts(run["tools"]) + (f" (refused: {_counts(refused)})" if refused else ""))
    if run.get("released"):
        lines.append("- released: " + "; ".join(run["released"]))
    if run.get("findings"):
        lines.append("- findings: " + "; ".join(run["findings"]))
    if run.get("decisions"):
        lines.append("- design values (origin): " + "; ".join(
            f"{d.get('name')} = {clip(d.get('value'), 120)} ({d.get('origin')})" for d in run["decisions"])
            + " (full: decisions)")
    refusals = run.get("refusals") or []
    if refusals:
        lines.append(f"- refused ×{len(refusals)} (full messages and drafts: refusals): " + "; ".join(
            f"[{r.get('stage')} {r.get('name')} {r.get('code') or ''}".rstrip() + f" → {r.get('outcome')}] "
            f"\"{clip(r.get('message'))}\"" for r in refusals))
    if run.get("web"):
        lines.append("- web facts (quotes: web): " + "; ".join(
            f"web.{w.get('id')} {clip(w.get('subject') or w.get('statement'), 80)}: "
            f"{clip(w.get('value_as_written') or w.get('value'), 80)} ({w.get('domain') or 'unknown source'}"
            + (f", {w['url']}" if w.get("url") else "") + ")" for w in run["web"]))
    if run.get("citable"):
        lines.append("- citable in later runs under the same address: " + ", ".join(run["citable"]))
    if run.get("code"):
        lines.append("- code (text: code): " + ", ".join(f"{c.get('execution_id')} ({c.get('status')})"
                                                          for c in run["code"]))
    if run.get("catalog"):
        lines.append("- catalog read (details: catalog): " + ", ".join(run["catalog"]))
    if run.get("answer"):
        lines.append(f"- answer: \"{clip(run['answer'], ANSWER_SHOWN)}\"" + (
            " (full, with assumptions, limitations and methodology: answer)"))
    if run.get("note"):
        lines.append(f"- note from this run's model: {clip(run['note'], NOTE_CHARS)}")
    if run.get("reasoning_chars"):
        lines.append(f"- reasoning: {run['reasoning_chars']} characters (reasoning)")
    return "\n".join(lines)


def memory_note(memos: list[dict[str, Any]]) -> str | None:
    """The memos as one application note, oldest first. Beyond MAX_MEMO_NOTE_CHARS the oldest memos are named with a
    pointer instead of their text (never cut silently)."""
    blocks = [str(m.get("memo") or "") for m in memos if m.get("memo")]
    if not blocks:
        return None
    total = sum(len(b) + 2 for b in blocks)
    folded = 0
    while total > MAX_MEMO_NOTE_CHARS and folded < len(blocks) - 1:
        total -= len(blocks[folded]) + 2
        folded += 1
    lines = [MEMORY_HEADER]
    if folded:
        lines.append(f"Earlier runs whose memos are not shown here (read them with read_conversation_memory(run_id, "
                     f"\"memo\")): {', '.join(str(m.get('run_id')) for m in memos[:folded])}.")
    return "\n\n".join(lines + blocks[folded:])


# ------------------------------------------------------------------------------------------------ sources


def serialize_sources(sources: Any, skip: set[tuple[str, str]], json_outputs: dict[str, Any]) -> dict[str, Any]:
    """The values this run made citable (fact, metric, reference, web) and the content of its JSON outputs, with their
    label, declared units and origin; what the run itself received from earlier runs (skip) is not kept again."""
    kept: dict[str, Any] = {}
    size = 0
    for namespace in SOURCE_NAMESPACES:
        for key, (value, label) in sorted((sources.objects.get(namespace) or {}).items()):
            if (namespace, key) in skip:
                continue
            entry = {"value": value, "label": label,
                     **({"units": sources.units[(namespace, key)]} if (namespace, key) in sources.units else {}),
                     **({"origin": sources.origins[(namespace, key)]} if (namespace, key) in sources.origins else {})}
            try:
                text = json.dumps(entry, ensure_ascii=False, default=str)
            except (TypeError, ValueError):
                continue
            if size + len(text) > MAX_SOURCES_BYTES:
                kept.setdefault("_not_kept", []).append(f"{namespace}.{key}")
                continue
            size += len(text)
            kept.setdefault(namespace, {})[key] = json.loads(text)
    for output_id, entry in json_outputs.items():
        text = json.dumps(entry, ensure_ascii=False, default=str)
        if len(text) > MAX_JSON_OUTPUT_BYTES or size + len(text) > MAX_SOURCES_BYTES:
            kept.setdefault("_not_kept", []).append(f"out.{output_id}")
            continue
        size += len(text)
        kept.setdefault("out", {})[output_id] = json.loads(text)
    return kept


def citable_addresses(sources: dict[str, Any], aliases: dict[str, str]) -> list[str]:
    """The addresses a memo lists as citable (an output by its alias)."""
    found = [f"{namespace}.{key}" for namespace in SOURCE_NAMESPACES for key in sorted(sources.get(namespace) or {})]
    found += [f"out.{aliases.get(output_id, output_id)}" for output_id in sorted(sources.get("out") or {})]
    return found


# ------------------------------------------------------------------------------------------------ the store


class MemoryStore:
    """"AI_conversation_run_memory" through the conversation login (CONVERSATION_DATABASE_URL)."""

    def __init__(self, url: str, connect_timeout_seconds: int = 5) -> None:
        self.url = url
        self.connect_timeout_seconds = connect_timeout_seconds

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self.url, row_factory=dict_row, connect_timeout=self.connect_timeout_seconds)

    def available(self) -> bool:
        """True when the table exists and the login can read it (checked at startup; fail closed)."""
        try:
            with self._connect() as connection:
                connection.execute('SELECT run_id FROM public."AI_conversation_run_memory" LIMIT 0')
            return True
        except psycopg.Error:
            return False

    def save(self, conversation_id: str, turn_request_id: str, run_id: str, *, status: str,
             response_type: str | None, error_code: str | None, memo: str, content: dict[str, Any],
             sources: dict[str, Any], note: str | None, reasoning: str | None) -> bool:
        """One run's memory; a run id kept before is left as it is (a retried run never replaces it)."""
        with self._connect() as connection:
            inserted = connection.execute(
                '''INSERT INTO public."AI_conversation_run_memory" (run_id, conversation_id, turn_request_id, status,
                       response_type, error_code, memo, content, sources, note, reasoning)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (run_id) DO NOTHING''',
                (run_id, conversation_id, turn_request_id, status, response_type, error_code, memo, Jsonb(content),
                 Jsonb(sources), note, reasoning)).rowcount
        return inserted == 1

    def load(self, conversation_id: str) -> list[dict[str, Any]]:
        """Every run of the conversation, oldest first: run_id, memo and sources (not the full texts)."""
        with self._connect() as connection:
            return connection.execute(
                '''SELECT run_id, turn_request_id, status, memo, sources FROM public."AI_conversation_run_memory"
                   WHERE conversation_id = %s ORDER BY seq''', (conversation_id,)).fetchall()

    def runs(self, conversation_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return connection.execute(
                '''SELECT run_id, turn_request_id, status, response_type, error_code, created_at::text AS created_at,
                          length(reasoning) AS reasoning_chars
                   FROM public."AI_conversation_run_memory" WHERE conversation_id = %s ORDER BY seq''',
                (conversation_id,)).fetchall()

    def read(self, conversation_id: str, run_id: str) -> dict[str, Any] | None:
        """One run's memory; for a turn's own request id (a mode 4 turn's runs are its steps) the turn as the
        conversation store keeps it: its message and its whole answer (the history may show it shortened)."""
        with self._connect() as connection:
            row = connection.execute(
                '''SELECT run_id, turn_request_id, status, response_type, error_code, memo, content, sources, note,
                          reasoning, created_at::text AS created_at
                   FROM public."AI_conversation_run_memory" WHERE conversation_id = %s AND run_id = %s''',
                (conversation_id, run_id)).fetchone()
            if row is not None:
                return row
            turn = connection.execute(
                '''SELECT request_id, status, run_status, response_type, error_code, user_message, response,
                          completed_at::text AS created_at
                   FROM public."AI_conversation_turn" WHERE conversation_id = %s AND request_id = %s''',
                (conversation_id, run_id)).fetchone()
        if turn is None:
            return None
        response = (turn.get("response") or {}).get("response") if isinstance(turn.get("response"), dict) else None
        steps = [s.get("request_id") for s in ((turn.get("response") or {}).get("mode4") or {}).get("steps") or []
                 if isinstance(s, dict)] if isinstance(turn.get("response"), dict) else []
        return {"run_id": run_id, "turn_request_id": run_id, "status": turn.get("run_status") or turn.get("status"),
                "response_type": turn.get("response_type"), "error_code": turn.get("error_code"),
                "memo": "A turn of the conversation; its runs have their own memos" + (
                    f" ({', '.join(str(x) for x in steps)})." if steps else "."),
                "content": {"message": turn.get("user_message"),
                            "answer": {k: response.get(k) for k in ("response_type", "answer", "clarification_question",
                                                                    "assumptions", "limitations", "methodology")}
                            if isinstance(response, dict) else None},
                "sources": {}, "note": None, "reasoning": None, "created_at": turn.get("created_at")}


# ------------------------------------------------------------------------------------------------ the tool


class ReadMemoryArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str | None = Field(description=(
        "The run as its memo names it (## <run_id>); null lists the runs, or with section catalog or data_record "
        "reads the conversation's data record."))
    section: Literal["memo", "message", "answer", "note", "plan", "refusals", "decisions", "web", "code", "catalog",
                     "sources", "reasoning", "data_record"] | None = Field(
        description="What to read of the run; null: its memo and the sections it has.")
    item: str | None = Field(description="For code: an execution_id (exe_...); for catalog: a table name; else null.")
    offset: int | None = Field(ge=0, description="Where a long text continues (next_offset of the previous page).")


def _page(value: Any, offset: int) -> dict[str, Any]:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str, indent=1)
    part = text[offset:offset + PAGE_CHARS]
    end = offset + len(part)
    return {"text": part, "offset": offset, "total_chars": len(text),
            "next_offset": end if end < len(text) else None}


def read_memory(store: MemoryStore | None, conversation_id: str | None, arguments: ReadMemoryArgs, *,
                record: dict[str, Any] | None = None, code_reader: Any = None) -> dict[str, Any]:
    """The tool's answer (see DESCRIPTION). code_reader(execution_id) -> the stored execution, for section code."""
    if store is None or not conversation_id:
        return {"status": "REJECTED", "code": "MEMORY_NOT_AVAILABLE", "next_action": "REPORT_LIMITATION",
                "message": "This request has no server-side conversation, so no run memory is kept."}
    offset = arguments.offset or 0
    if arguments.run_id is None and arguments.section in RECORD_SECTIONS:
        # the data record's full reference sections (the note summarizes them; EXEC-C items 5 and 10)
        record = record or {}
        if arguments.section == "catalog":
            columns = record.get("columns") or {}
            value = columns.get(arguments.item) if arguments.item else columns
            if arguments.item and value is None:
                return {"status": "REJECTED", "code": "TABLE_NOT_READ", "next_action": "FIX_ARGUMENTS",
                        "message": "The conversation has not read this table's column details; read them with "
                                   "get_catalog_details.", "tables": sorted(columns)}
            return {"status": "OK", "section": "catalog", "table": arguments.item, **_page(value or {}, offset)}
        value = {k: record.get(k) for k in ("tables", "values", "relationships", "coverage", "needs", "research")}
        return {"status": "OK", "section": "data_record", **_page(value, offset)}
    if arguments.run_id is None:
        runs = store.runs(conversation_id)
        return {"status": "OK", "runs": runs, "sections": list(SECTIONS),
                "record_sections": "catalog and data_record are read without run_id"}
    if not RUN_ID_RE.fullmatch(arguments.run_id):
        return {"status": "REJECTED", "code": "RUN_NOT_FOUND", "next_action": "FIX_ARGUMENTS",
                "message": "No run of this conversation has this run_id; call without run_id for the list."}
    row = store.read(conversation_id, arguments.run_id)
    if row is None:
        return {"status": "REJECTED", "code": "RUN_NOT_FOUND", "next_action": "FIX_ARGUMENTS",
                "message": "No run of this conversation has this run_id; call without run_id for the list."}
    content = row.get("content") if isinstance(row.get("content"), dict) else {}
    section = arguments.section
    head = {"status": "OK", "run_id": row["run_id"], "turn_request_id": row.get("turn_request_id"),
            "run_status": row.get("status"), "response_type": row.get("response_type"),
            "error_code": row.get("error_code"), "created_at": row.get("created_at")}
    if section is None or section == "memo":
        available = [name for name in SECTIONS if name in ("memo", "sources", "reasoning", "note")
                     or content.get(name) not in (None, "", [], {})]
        return {**head, "section": "memo", **_page(row.get("memo") or "", offset), "sections": available}
    if section == "note":
        return {**head, "section": section, **_page(row.get("note") or "", offset)}
    if section == "reasoning":
        return {**head, "section": section, **_page(row.get("reasoning") or "", offset),
                **({"reasoning_kept": content["reasoning"]} if isinstance(content.get("reasoning"), dict) else {})}
    if section == "sources":
        return {**head, "section": section, **_page(row.get("sources") or {}, offset)}
    if section == "code":
        code = content.get("code") or []
        if arguments.item:
            stored = code_reader(arguments.item) if code_reader is not None else None
            entry = next((c for c in code if c.get("execution_id") == arguments.item), None)
            text = (stored or {}).get("code") or (entry or {}).get("code")
            if text is None:
                return {"status": "REJECTED", "code": "CODE_NOT_FOUND", "next_action": "FIX_ARGUMENTS",
                        "message": "This run has no stored code with this execution_id; its memo lists them."}
            return {**head, "section": section, "execution_id": arguments.item,
                    "execution_status": (stored or entry or {}).get("status"),
                    "code_truncated": bool((stored or {}).get("code_truncated")), **_page(text, offset)}
        return {**head, "section": section, **_page([{k: c.get(k) for k in ("execution_id", "status")}
                                                     for c in code], offset),
                "next_step": "Give item=<execution_id> for the code text."}
    if section == "catalog":
        catalog = content.get("catalog") or {}
        if arguments.item:
            if arguments.item not in catalog and record is not None:
                kept = (record.get("columns") or {}).get(arguments.item)
                if kept:
                    return {**head, "section": section, "table": arguments.item, **_page(kept, offset)}
            return {**head, "section": section, "table": arguments.item, **_page(catalog.get(arguments.item) or {},
                                                                                offset)}
        return {**head, "section": section, **_page(catalog, offset)}
    return {**head, "section": section, **_page(content.get(section) if content.get(section) is not None else "",
                                               offset)}
