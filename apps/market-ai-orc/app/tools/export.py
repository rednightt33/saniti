"""export_result (round 2026-10-03 D4; ROUND_PLAN_2026-10-03_FASE_D.md): a download file of an output.

The file is written by the sandbox from the output's stored file (CSV, Parquet, or XLSX with a 'definisi' and a
'lineage' sheet), kept in AI_conversation_export with the conversation (user decision 2: Postgres, at most 20 MB, no
bucket and no public URL), and downloaded through market-ai-orc's own API with the same authorization and owner.
The model sees only the export's id, name, size and format; the file never enters its context.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .. import user_texts as texts
from .analysis import SandboxClient
from .data_planner import sha256_json
from .artifacts import (current_results, record_source_tables, resolve_ref, short_lineage, source_bytes,
                        stored_op)
from .registry import ToolError, ToolSpec

DESCRIPTION = (
    "Write an output as a file the user downloads (CSV, XLSX with definition and lineage sheets, or PARQUET), at most "
    "20 MB. Give ref (out.o3), output_id, or evidence_id (a checked claim's evidence rows). Returns export_id, file "
    "name, size and format only; the answer names the file, the user downloads it. For XLSX give column_labels: the "
    "title of each column in the user's language, as the reader should see it. The backend adds to the XLSX "
    "definition sheet what one row is and how complete each group is against the source table."
)
MAX_COLUMNS = 60  # the column sheet travels in the request header with the definition and lineage
# The sandbox's HTTP server reads at most 16 KiB of request headers (h11); the metadata header stays below this, its
# column meanings shortened first and the completeness groups dropped next (M133).
META_HEADER_BYTES = 14_000  # leaves about 2 KiB for the other headers
MEANING_STEPS = (300, 160, 120, 80, 0)
MAX_COMPLETENESS_GROUPS = 50


class ColumnLabel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: str = Field(description="The column's name in the output.")
    label: str = Field(description="Its title in the user's language.")


class ExportResultArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str | None = Field(pattern=r"^(out\.)?o[1-9][0-9]{0,3}$", description="The output's value reference.")
    output_id: str | None = Field(pattern=r"^out_[0-9a-f]{24}$")
    evidence_id: str | None = Field(pattern=r"^evd_[0-9a-f]{24}$", description="A checked claim's evidence rows.")
    format: Literal["CSV", "XLSX", "PARQUET"]
    include_definition: bool | None = Field(description="XLSX: a sheet with the output's definition (default true).")
    include_lineage: bool | None = Field(description="XLSX: a sheet with where the data came from (default true).")
    column_labels: list[ColumnLabel] | None = Field(
        description="XLSX: the title the reader sees for each column, in the user's language; a column not named "
                    "keeps its name made readable.")

    @model_validator(mode="after")
    def _one_source(self) -> "ExportResultArgs":
        if sum(v is not None for v in (self.ref, self.output_id, self.evidence_id)) != 1:
            raise ValueError("give exactly one of ref, output_id or evidence_id")
        return self


def file_name(name: Any, output_id: str, extension: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", str(name or output_id)).strip("._-")[:100] or output_id
    return f"{stem}.{extension}"


def export_specs(client: SandboxClient, *, timeout_seconds: float, max_result_bytes: int,
                 column_meanings: Callable[[list[str], list[str]], dict[str, dict]] | None = None,
                 table_facts: Callable[[list[str], list[str]], dict[str, dict]] | None = None,
                 governor: Any = None) -> list[ToolSpec]:
    """column_meanings(tables, columns): the catalog's meaning and unit of each column a source table has (M128b).
    table_facts(tables, columns) and governor: the source counts behind the XLSX completeness rows (EXEC-Y Fase 3)."""
    def handler(arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, ExportResultArgs)
        results = current_results.get()
        if results is None or results.store is None or not results.conversation_id:
            return {"status": "REJECTED", "code": "EXPORT_NOT_AVAILABLE", "next_action": "REPORT_LIMITATION",
                    "message": "Exports are kept with a conversation; this request has none."}
        if arguments.evidence_id is not None:
            return _export_evidence(client, results, arguments, timeout_seconds)
        entry = resolve_ref(results.record, arguments.ref) if arguments.ref else next(
            (o for o in results.record.get("outputs") or [] if o.get("output_id") == arguments.output_id), None)
        if arguments.ref and entry is None:
            return {"status": "REJECTED", "code": "REF_NOT_FOUND", "next_action": "FIX_ARGUMENTS",
                    "message": "No output of this conversation has this reference; the data record lists them."}
        output_id = str((entry or {}).get("output_id") or arguments.output_id)
        data, stored = source_bytes(results, output_id, (entry or {}).get("session_id"))
        kind = stored.format if stored is not None else (
            "PARQUET" if str((entry or {}).get("type") or "TABLE") in ("TABLE", "PARQUET") else str(entry.get("type")))
        if kind not in ("PARQUET", "CSV", "JSON"):
            return {"status": "REJECTED", "code": "EXPORT_NOT_TABULAR", "next_action": "FIX_ARGUMENTS",
                    "message": f"A {kind} output is not a table; export a table output."}
        definition = (entry or {}).get("definition") or (stored.definition if stored else None)
        lineage = {"output_id": output_id, "ref": (entry or {}).get("ref"),
                   "name": (entry or {}).get("name") or (stored.name if stored else None),
                   **(short_lineage((entry or {}).get("lineage") or (stored.lineage if stored else None)) or {}),
                   "source_tables": record_source_tables(results.record, ((entry or {}).get("lineage") or (
                       stored.lineage if stored else None) or {}).get("need_id"))}
        includes = {"definition": arguments.include_definition is not False and bool(definition),
                    "lineage": arguments.include_lineage is not False}
        meta = {"format": kind, "checksum_sha256": hashlib.sha256(data).hexdigest(), "target": arguments.format,
                **({"definition": texts.export_definition(definition)}
                   if includes["definition"] and arguments.format == "XLSX" else {}),
                **({"lineage": texts.export_lineage(lineage)}
                   if includes["lineage"] and arguments.format == "XLSX" else {})}
        names = [str(n) for n in (entry or {}).get("columns") or []][:MAX_COLUMNS]
        if arguments.format == "XLSX" and names:
            # M128b: the titles the reader sees and what each column means; the CSV keeps the machine names
            meanings = {}
            if column_meanings is not None and lineage.get("source_tables"):
                try:
                    meanings = column_meanings(list(lineage["source_tables"]), names)
                except Exception:  # noqa: BLE001 - a catalog failure leaves the meanings out, never the file
                    meanings = {}
            labels = {item.column: item.label[:80] for item in arguments.column_labels or []
                      if item.column in names and item.label.strip()}
            meta["columns"] = texts.export_columns(names, labels, meanings)
            meta["headers"] = {row["name"]: row["label"] for row in meta["columns"]}
        if arguments.format == "XLSX":
            # E1(1), E1(3): how to read the file (one row per ..., the days per group against the source)
            meta["texts"] = texts.EXPORT_READING
            meta["completeness"] = completeness(client, governor, table_facts, results.record,
                                                ((entry or {}).get("lineage") or (stored.lineage if stored else None)
                                                 or {}).get("need_id"), names, data, kind, timeout_seconds)
            meta = fit_header(meta)
        status, body, headers = stored_op(client, "export", data, meta, timeout=timeout_seconds)
        if status != 200:
            return _refused(status, body)
        return _kept(results, arguments.format, (entry or {}).get("ref") or output_id,
                     file_name(lineage["name"], output_id,
                               headers.get("x-saniti-extension") or arguments.format.lower()),
                     headers, body, includes)

    return [ToolSpec(name="export_result", effect="OWN_ARTIFACT", description=DESCRIPTION, arguments_model=ExportResultArgs,
                     handler=handler, timeout_seconds=timeout_seconds + 30, max_result_bytes=max_result_bytes)]


UNCHECKED = {"status": "UNCHECKED"}


def completeness(client: SandboxClient, governor: Any, table_facts: Any, record: dict[str, Any], need_id: Any,
                 names: list[str], data: bytes, kind: str, timeout: float) -> dict[str, Any]:
    """EXEC-Y Fase 3 E1(1) (user decision 2026-10-09 "E1 ok 2-4"): the days the source table has, per group, over the
    file's own period, for the sandbox to set against the file's days. Derived, so a new table needs no code:
      - the source is a request of the output's data need whose table's time column is a column of the file, with the
        canonical filter kept in the data record and no restriction to another table;
      - the groups are the file's columns that the table can be grouped by (its grain keys and the catalog's
        group_by_allowed columns); the request with the most of them is used;
      - the file's period is its first and last date (sandbox recount), the counts one Governor summary (COUNT).
    UNCHECKED when any of this is missing or fails: the file then says it was not checked, never a guess."""
    try:
        need = next((n for n in record.get("needs") or [] if isinstance(n, dict) and n.get("need_id") == need_id), None)
        if governor is None or table_facts is None or need is None:
            return UNCHECKED
        requests = [r for r in need.get("requests") or [] if isinstance(r, dict) and r.get("source_table")]
        facts = table_facts(sorted({r["source_table"] for r in requests}), names) if requests else {}
        best = None
        for request in requests:
            table = facts.get(request["source_table"]) or {}
            time_column = table.get("time_column")
            if not time_column or time_column not in names or request.get("restrictions") \
                    or not isinstance(request.get("scope_spec"), dict):
                continue
            groups = [c for c in names if c != time_column and c in table.get("groupable", set())]
            if best is None or len(groups) > len(best[2]):
                best = (request, table, groups, time_column)
        if best is None or len(best[2]) > 6:
            return UNCHECKED
        request, table, groups, time_column = best
        meta = {"format": kind, "checksum_sha256": hashlib.sha256(data).hexdigest(), "column": time_column,
                "columns": [time_column]}
        ends = []
        for measure in ("MIN", "MAX"):
            status, body, _ = stored_op(client, "recount", data, {**meta, "measure": measure}, timeout=timeout)
            value = body.get("value") if status == 200 and isinstance(body, dict) else None
            if not isinstance(value, str) or len(value) < 10:
                return UNCHECKED
            ends.append(value[:10])
        spec = {"summary_version": "summary_spec/v1", "source_table": request["source_table"],
                "scope": request["scope_spec"], "restrictions": [], "group_by": groups,
                "measures": [{"column": None, "function": "COUNT", "as": "row_count"}],
                "period": {"from": ends[0], "to": ends[1]}}
        answer = governor.summary(spec, {"purpose": "EVIDENCE", "recipe_sha256": sha256_json(spec)}, timeout=timeout)
        rows = answer.get("rows") or []
        if answer.get("status") != "OK" or len(rows) > MAX_COMPLETENESS_GROUPS:
            return UNCHECKED
        return {"status": "CHECKED", "time_column": time_column, "group_columns": groups, "from": ends[0],
                "to": ends[1], "calendar_dates": (answer.get("period") or {}).get("calendar_dates"),
                "row_presence": table.get("row_presence"),
                "groups": [{"key": [row.get(g) for g in groups], "days": row.get("days_present")} for row in rows]}
    except Exception:  # noqa: BLE001 - the check never blocks the file; the file says it was not checked
        return UNCHECKED


def _header_bytes(meta: dict[str, Any]) -> int:
    return len(base64.urlsafe_b64encode(json.dumps(meta, default=str).encode()))


def fit_header(meta: dict[str, Any]) -> dict[str, Any]:
    """M133: the metadata within META_HEADER_BYTES; column meanings shortened step by step, then the completeness
    groups dropped (the file then says it was not checked)."""
    for limit in MEANING_STEPS:
        if _header_bytes(meta) <= META_HEADER_BYTES:
            return meta
        if meta.get("columns"):
            meta = {**meta, "columns": [{**c, "meaning": (c.get("meaning") or "")[:limit] or None}
                                        for c in meta["columns"]]}
    if _header_bytes(meta) > META_HEADER_BYTES and meta.get("completeness"):
        meta = {**meta, "completeness": UNCHECKED}
    return meta


def _refused(status: int, body: Any) -> dict[str, Any]:
    error = body.get("error") if isinstance(body, dict) and isinstance(body.get("error"), dict) else {}
    return {"status": "REJECTED", "code": error.get("code") or f"HTTP_{status}",
            "message": str(error.get("message") or "")[:600],
            "next_action": (body.get("next_action") if isinstance(body, dict) else None) or "REPORT_LIMITATION"}


def _kept(results: Any, fmt: str, source_ref: str, name: str, headers: dict[str, str], body: bytes,
          includes: dict[str, Any]) -> dict[str, Any]:
    mime = headers.get("content-type", "application/octet-stream").split(";")[0]
    try:
        saved = results.store.save_export(results.conversation_id, results.request_id, source_ref, fmt, name, mime,
                                          body, includes)
    except Exception as exc:  # noqa: BLE001 - the model gets a plain refusal, the log the cause
        raise ToolError(f"The export could not be kept ({type(exc).__name__}).", code="EXPORT_NOT_SAVED") from None
    return {"status": "EXPORTED", **saved, "download": f"/v1/exports/{saved['export_id']}/download",
            "note": "The user downloads the file from the answer's artifacts; never paste its content."}


def _export_evidence(client: SandboxClient, results: Any, arguments: ExportResultArgs, timeout: float
                     ) -> dict[str, Any]:
    """D6: a checked claim's evidence rows as a file, with the claim and its recipe as the definition sheet."""
    import json

    found = results.store.evidence(results.conversation_id, arguments.evidence_id)
    if found is None:
        return {"status": "REJECTED", "code": "EVIDENCE_NOT_FOUND", "next_action": "FIX_ARGUMENTS",
                "message": "No checked claim with this id belongs to this conversation."}
    if not found.get("rows"):
        return {"status": "REJECTED", "code": "EXPORT_NOT_TABULAR", "next_action": "FIX_ARGUMENTS",
                "message": "This claim has no evidence rows to export."}
    data = json.dumps({"rows": found["rows"]}, default=str).encode()
    meta = {"format": "JSON", "checksum_sha256": hashlib.sha256(data).hexdigest(), "target": arguments.format,
            **({"definition": {"claim": found["claim"], "value_text": found["value_text"], "status": found["status"],
                               "backend_value": found.get("backend_value"), "recipe": found.get("recipe")}}
               if arguments.include_definition is not False and arguments.format == "XLSX" else {}),
            **({"lineage": found.get("source") or {}}
               if arguments.include_lineage is not False and arguments.format == "XLSX" else {})}
    status, body, headers = stored_op(client, "export", data, meta, timeout=timeout)
    if status != 200:
        return _refused(status, body)
    return _kept(results, arguments.format, arguments.evidence_id,
                 file_name(f"bukti_{arguments.evidence_id}", arguments.evidence_id,
                           headers.get("x-saniti-extension") or arguments.format.lower()),
                 headers, body, {"definition": "definition" in meta, "lineage": "lineage" in meta})
