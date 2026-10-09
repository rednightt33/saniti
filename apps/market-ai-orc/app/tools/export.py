"""export_result (round 2026-10-03 D4; ROUND_PLAN_2026-10-03_FASE_D.md): a download file of an output.

The file is written by the sandbox from the output's stored file (CSV, Parquet, or XLSX with a 'definisi' and a
'lineage' sheet), kept in AI_conversation_export with the conversation (user decision 2: Postgres, at most 20 MB, no
bucket and no public URL), and downloaded through market-ai-orc's own API with the same authorization and owner.
The model sees only the export's id, name, size and format; the file never enters its context.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .. import user_texts as texts
from .analysis import SandboxClient
from .artifacts import (current_results, record_source_tables, resolve_ref, short_lineage, source_bytes,
                        stored_op)
from .registry import ToolError, ToolSpec

DESCRIPTION = (
    "Write an output as a file the user downloads (CSV, XLSX with definition and lineage sheets, or PARQUET), at most "
    "20 MB. Give ref (out.o3), output_id, or evidence_id (a checked claim's evidence rows). Returns export_id, file "
    "name, size and format only; the answer names the file, the user downloads it. For XLSX give column_labels: the "
    "title of each column in the user's language, as the reader should see it."
)
MAX_COLUMNS = 60  # the column sheet travels in the request header with the definition and lineage


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
                 column_meanings: Callable[[list[str], list[str]], dict[str, dict]] | None = None) -> list[ToolSpec]:
    """column_meanings(tables, columns): the catalog's meaning and unit of each column a source table has (M128b)."""
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
        status, body, headers = stored_op(client, "export", data, meta, timeout=timeout_seconds)
        if status != 200:
            return _refused(status, body)
        return _kept(results, arguments.format, (entry or {}).get("ref") or output_id,
                     file_name(lineage["name"], output_id,
                               headers.get("x-saniti-extension") or arguments.format.lower()),
                     headers, body, includes)

    return [ToolSpec(name="export_result", effect="OWN_ARTIFACT", description=DESCRIPTION, arguments_model=ExportResultArgs,
                     handler=handler, timeout_seconds=timeout_seconds + 30, max_result_bytes=max_result_bytes)]


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
