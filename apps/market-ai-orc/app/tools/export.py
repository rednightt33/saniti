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
    "title of each column in the user's language, as the reader should see it, and source_columns: for each column "
    "copied from a source table (renamed or not), that table's column name; never for a computed column. The backend "
    "adds to the XLSX definition sheet what one row is and how complete each group is against the source table."
)
DATA_DESCRIPTION = (
    " The data behind a result (E9): data_request (with need_id when several needs share it) exports the rows a data "
    "request of an approved need delivered, as listed in the data record ([data_request_1_A]): the approved ranges, no "
    "code and no session needed; a ref of a supporting table (the data record's Supporting tables: working tables and "
    "steps) exports that table. data_status says where the file came from: STORED (kept copy), REBUILT (the same "
    "approved need extracted again, or after its 30 days a supporting table rebuilt by running the stored code again; "
    "a rebuilt supporting table is exported only when it matches the original exactly), EXPIRED_NOT_REBUILDABLE "
    "(refused, with the reason: say so and offer to compute it again). same_rows_as_original false means the source "
    "data changed since: say so. An XLSX of a result also gets one sheet per input whose rows the file does not span "
    "(warm-up and base rows included); inputs lists each one (INCLUDED, COVERED, NOT_INCLUDED with the reason)."
)
SUPPORTING_DATA_VERSION = 1  # the sandbox's supporting_data capability (bundle dataset file, need carry)
REBUILD_FAILED = "EXPIRED_NOT_REBUILDABLE"
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


class SourceColumn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: str = Field(description="The column's name in the output.")
    source_column: str = Field(description="The source table's column it was copied from, exactly as the catalog "
                                           "names it (for example Date for trading_date).")


class ExportResultArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str | None = Field(pattern=r"^(out\.)?o[1-9][0-9]{0,3}$", description="The output's value reference.")
    output_id: str | None = Field(pattern=r"^out_[0-9a-f]{24}$")
    evidence_id: str | None = Field(pattern=r"^evd_[0-9a-f]{24}$", description="A checked claim's evidence rows.")
    data_request: str | None = Field(
        pattern=r"^[A-Za-z0-9_]{1,80}$",
        description="A data request of an approved need in the data record (data_request_1_A): the rows it delivered.")
    need_id: str | None = Field(pattern=r"^need_[0-9a-f]{24}$",
                                description="With data_request: the need it belongs to (default: the newest).")
    format: Literal["CSV", "XLSX", "PARQUET"]
    include_definition: bool | None = Field(description="XLSX: a sheet with the output's definition (default true).")
    include_lineage: bool | None = Field(description="XLSX: a sheet with where the data came from (default true).")
    column_labels: list[ColumnLabel] | None = Field(
        description="XLSX: the title the reader sees for each column, in the user's language; a column not named "
                    "keeps its name made readable.")
    source_columns: list[SourceColumn] | None = Field(
        description="XLSX: the source table's column of each column copied from it (renamed or not); a computed "
                    "column is not listed.")

    @model_validator(mode="after")
    def _one_source(self) -> "ExportResultArgs":
        if sum(v is not None for v in (self.ref, self.output_id, self.evidence_id, self.data_request)) != 1:
            raise ValueError("give exactly one of ref, output_id, evidence_id or data_request")
        if self.need_id is not None and self.data_request is None:
            raise ValueError("need_id goes with data_request")
        return self


def _today() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).date().isoformat()


def file_name(name: Any, output_id: str, extension: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", str(name or output_id)).strip("._-")[:100] or output_id
    return f"{stem}.{extension}"


def export_specs(client: SandboxClient, *, timeout_seconds: float, max_result_bytes: int,
                 column_meanings: Callable[[list[str], list[str]], dict[str, dict]] | None = None,
                 table_facts: Callable[[list[str], list[str]], dict[str, dict]] | None = None,
                 governor: Any = None, rebuild: Callable[[str], dict[str, Any]] | None = None) -> list[ToolSpec]:
    """column_meanings(tables, columns): the catalog's meaning and unit of each column a source table has (M128b).
    table_facts(tables, columns) and governor: the source counts behind the XLSX completeness rows (EXEC-Y Fase 3).
    rebuild(need_id): the Execution Planner's prepare, which extracts an approved need's bundle (E9 d/f)."""
    def handler(arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, (ExportResultArgs, ExportResultArgsBasic))
        results = current_results.get()
        if results is None or results.store is None or not results.conversation_id:
            return {"status": "REJECTED", "code": "EXPORT_NOT_AVAILABLE", "next_action": "REPORT_LIMITATION",
                    "message": "Exports are kept with a conversation; this request has none."}
        if arguments.evidence_id is not None:
            return _export_evidence(client, results, arguments, timeout_seconds)
        if getattr(arguments, "data_request", None) is not None:
            return _export_data_request(client, results, arguments, timeout_seconds, rebuild)
        entry = resolve_ref(results.record, arguments.ref) if arguments.ref else next(
            (o for o in results.record.get("outputs") or [] if o.get("output_id") == arguments.output_id), None)
        if arguments.ref and entry is None:
            return {"status": "REJECTED", "code": "REF_NOT_FOUND", "next_action": "FIX_ARGUMENTS",
                    "message": "No output of this conversation has this reference; the data record lists them."}
        output_id = str((entry or {}).get("output_id") or arguments.output_id)
        data_status = "STORED"
        try:
            data, stored = source_bytes(results, output_id, (entry or {}).get("session_id"))
        except ToolError:
            if not (entry or {}).get("support"):
                raise
            # E9(f): a supporting table past its 30 days is rebuilt from the stored code, exported only on a match
            rebuilt = rebuild_support(client, results, entry, rebuild, timeout_seconds)
            if rebuilt.get("status") == "REJECTED":
                return rebuilt
            data, stored, data_status = rebuilt["data"], None, "REBUILT"
        kind = stored.format if stored is not None else (
            "PARQUET" if str((entry or {}).get("type") or "TABLE") in ("TABLE", "PARQUET", "SUPPORT")
            else str(entry.get("type")))
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
        # the table download of an answer (TableExportArgs.select): only the columns the answer shows, in its order
        chosen = [c for c in getattr(arguments, "select", None) or [] if c in names]
        if chosen:
            names = list(dict.fromkeys(chosen))
            meta["select"] = names
        # EXEC-Y Fase 3: a renamed source column (trading_date for Date) keeps its catalog meaning and its count; the
        # mapping is the model's reading of its own code, the catalog and the Governor check that the column exists
        copied = {item.column: item.source_column for item in arguments.source_columns or []
                  if item.column in names and item.source_column.strip()}
        if arguments.format == "XLSX" and names:
            # M128b: the titles the reader sees and what each column means; the CSV keeps the machine names
            meanings = {}
            if column_meanings is not None and lineage.get("source_tables"):
                try:
                    found = column_meanings(list(lineage["source_tables"]), sorted(set(names) | set(copied.values())))
                    meanings = {name: found.get(copied.get(name, name)) or found.get(name) for name in names}
                    meanings = {k: v for k, v in meanings.items() if v}
                except Exception:  # noqa: BLE001 - a catalog failure leaves the meanings out, never the file
                    meanings = {}
            labels = {item.column: item.label[:80] for item in arguments.column_labels or []
                      if item.column in names and item.label.strip()}
            meta["columns"] = texts.export_columns(names, labels, meanings)
            meta["headers"] = {row["name"]: row["label"] for row in meta["columns"]}
        need = next((n for n in results.record.get("needs") or []
                     if n.get("need_id") == ((entry or {}).get("lineage") or (stored.lineage if stored else None)
                                             or {}).get("need_id")), None)
        if arguments.format == "XLSX" and need and need.get("bundle_id") and getattr(client, "supporting_data", False):
            # E1 (EXEC-1018B): every input of the result the file does not span gets its own sheet (warm-up rows
            # included); the sandbox decides from the file and the bundle, and reports each input
            meta["request_id"] = results.request_id
            meta["inputs"] = [{"bundle_id": need["bundle_id"], "data_request_id": r.get("data_request_id"),
                               "sheet": r.get("logical_name") or r.get("data_request_id")}
                              for r in need.get("requests") or [] if r.get("data_request_id")][:6]
        if arguments.format == "XLSX":
            # E1(1), E1(3): how to read the file (one row per ..., the days per group against the source)
            meta["texts"] = texts.EXPORT_READING
            meta["completeness"] = completeness(client, governor, table_facts, results.record,
                                                ((entry or {}).get("lineage") or (stored.lineage if stored else None)
                                                 or {}).get("need_id"), names, data, kind, timeout_seconds, copied)
            meta = fit_header(meta)
        status, body, headers = stored_op(client, "export", data, meta, timeout=timeout_seconds)
        if status != 200:
            return _refused(status, body)
        rebuilt_inputs = None
        if isinstance(arguments, TableExportArgs) and meta.get("inputs") and need is not None:
            # the table download (user 2026-10-20 "Ok, opsi A"): inputs whose bundle the sandbox no longer keeps are
            # extracted again with the same approved need, and the file is written once more with them
            gone = [i for i in _input_statuses(headers) if i.get("status") == "NOT_INCLUDED"
                    and str(i.get("reason")) in ("BUNDLE_EXPIRED", "BUNDLE_NOT_FOUND")]
            if gone:
                fresh = _fresh_bundle(client, results, str(need["need_id"]), rebuild)
                rebuilt_inputs = {"status": "REBUILT" if fresh.get("bundle_id") else REBUILD_FAILED,
                                  **({"message": fresh.get("message")} if not fresh.get("bundle_id") else {})}
                if fresh.get("bundle_id"):
                    meta["inputs"] = [{**i, "bundle_id": fresh["bundle_id"]} for i in meta["inputs"]]
                    # the file says its input sheets were extracted again, and when
                    meta["definition"] = {**(meta.get("definition") or {}), texts.INPUTS_REBUILT_FIELD:
                                          texts.INPUTS_REBUILT.format(date=_today())}
                    again = stored_op(client, "export", data, meta, timeout=timeout_seconds)
                    if again[0] == 200:
                        status, body, headers = again
                    else:
                        rebuilt_inputs = {"status": REBUILD_FAILED, "message": "the file could not be written again"}
        kept = _kept(results, arguments.format, (entry or {}).get("ref") or output_id,
                     file_name(lineage["name"], output_id,
                               headers.get("x-saniti-extension") or arguments.format.lower()),
                     headers, body, includes)
        if (entry or {}).get("support") and kept.get("status") == "EXPORTED":
            kept["data_status"] = data_status
        if rebuilt_inputs is not None and kept.get("status") == "EXPORTED":
            kept["inputs_data_status"] = rebuilt_inputs
        inputs = _input_statuses(headers)
        if inputs and kept.get("status") == "EXPORTED":
            kept["inputs"] = inputs
            missing = [i["data_request_id"] for i in inputs if i.get("status") == "NOT_INCLUDED"]
            if missing:
                kept["inputs_note"] = (f"Inputs {missing} are not in the file ({', '.join(sorted({str(i.get('reason')) for i in inputs if i.get('status') == 'NOT_INCLUDED'}))}); "
                                       "export_result(data_request=...) exports their rows as their own file.")
        return kept

    supporting = rebuild is not None
    return [ToolSpec(name="export_result", effect="OWN_ARTIFACT",
                     description=DESCRIPTION + (DATA_DESCRIPTION if supporting else ""),
                     arguments_model=ExportResultArgs if supporting else ExportResultArgsBasic,
                     handler=handler, timeout_seconds=timeout_seconds * (8 if supporting else 1) + 30,
                     max_result_bytes=max_result_bytes)]


class TableExportArgs(ExportResultArgs):
    """The table download of an answer (user 2026-10-20, POST /v1/conversations/{id}/outputs/{output_id}/export):
    export_result's arguments, never offered to the model, plus the columns the answer shows."""
    select: list[str] | None = None


class ExportResultArgsBasic(BaseModel):
    """export_result without E9 (no rebuild path): the arguments it had before."""
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
    source_columns: list[SourceColumn] | None = Field(
        description="XLSX: the source table's column of each column copied from it (renamed or not); a computed "
                    "column is not listed.")

    @model_validator(mode="after")
    def _one_source(self) -> "ExportResultArgsBasic":
        if sum(v is not None for v in (self.ref, self.output_id, self.evidence_id)) != 1:
            raise ValueError("give exactly one of ref, output_id or evidence_id")
        return self


def _input_statuses(headers: dict[str, str]) -> list[dict[str, Any]]:
    """E1: the sandbox's report of each input sheet (INCLUDED, COVERED or NOT_INCLUDED with the reason)."""
    encoded = headers.get("x-saniti-inputs") or ""
    if not encoded:
        return []
    try:
        value = json.loads(base64.urlsafe_b64decode(encoded.encode() + b"==="))
    except ValueError:
        return []
    return [v for v in value if isinstance(v, dict)][:6] if isinstance(value, list) else []


def _rebuild_refused(reason: str, **details: Any) -> dict[str, Any]:
    return {"status": "REJECTED", "code": REBUILD_FAILED, "data_status": REBUILD_FAILED,
            "next_action": "REPORT_LIMITATION", "message": reason[:600], **details}


def _need_of(record: dict[str, Any], data_request: str, need_id: str | None) -> dict[str, Any] | None:
    for need in reversed(record.get("needs") or []):
        if need_id is not None and need.get("need_id") != need_id:
            continue
        if any(r.get("data_request_id") == data_request for r in need.get("requests") or []):
            return need
    return None


def _fresh_bundle(client: SandboxClient, results: Any, need_id: str,
                  rebuild: Callable[[str], dict[str, Any]] | None) -> dict[str, Any]:
    """E9(d/f): the same approved need registered for this request and its bundle prepared (parts the conversation
    still keeps are reused, the rest extracted again with the same Governor SQL). {bundle_id} or a refusal."""
    if rebuild is None or not getattr(client, "supporting_data", False):
        return _rebuild_refused("Rebuilding data is not available in this deployment (the sandbox does not report "
                                f"supporting_data version {SUPPORTING_DATA_VERSION}).")
    carried = client.carry_need(need_id, results.request_id)
    if carried.get("status") == "REJECTED":
        return _rebuild_refused(f"The approved need {need_id} can no longer be used: {carried.get('message')}",
                                reason_code=carried.get("code"))
    bundle = rebuild(str(carried["need_id"]))
    if bundle.get("status") != "READY" or not bundle.get("input_bundle_id"):
        return _rebuild_refused("Extracting the data again failed: " + str(
            bundle.get("message") or bundle.get("code") or bundle.get("status")), reason_code=bundle.get("code"))
    return {"bundle_id": str(bundle["input_bundle_id"]), "need_id": str(carried["need_id"])}


def _export_data_request(client: SandboxClient, results: Any, arguments: ExportResultArgs, timeout: float,
                         rebuild: Callable[[str], dict[str, Any]] | None) -> dict[str, Any]:
    """E9(d) (EXEC-1018B): the rows a data request delivered, from its bundle while the sandbox keeps it (24 hours),
    else from the same approved need extracted again; no model code."""
    need = _need_of(results.record, str(arguments.data_request), arguments.need_id)
    if need is None:
        known = sorted({str(r.get("data_request_id")) for n in results.record.get("needs") or []
                        for r in n.get("requests") or [] if r.get("data_request_id")})
        return {"status": "REJECTED", "code": "DATA_REQUEST_NOT_FOUND", "next_action": "FIX_ARGUMENTS",
                "message": f"No approved need of this conversation has data request {arguments.data_request!r}; "
                           f"the data record lists {known or 'none'}."}
    request = next(r for r in need.get("requests") or [] if r.get("data_request_id") == arguments.data_request)
    if not getattr(client, "supporting_data", False):
        return {"status": "REJECTED", "code": "SUPPORTING_DATA_UNAVAILABLE", "next_action": "REPORT_LIMITATION",
                "message": "Exporting a data request needs the sandbox's supporting_data capability."}
    data_status, original, status, data, meta = "STORED", None, 0, b"", {}
    if need.get("bundle_id"):
        status, data, meta = client.dataset_file(str(need["bundle_id"]), str(arguments.data_request),
                                                 results.request_id)
        error = meta.get("error") if status != 200 and isinstance(meta.get("error"), dict) else {}
        original = error.get("rows_identity") if error else None
        if status != 200 and error.get("code") not in ("BUNDLE_EXPIRED", "BUNDLE_NOT_FOUND"):
            return {"status": "REJECTED", "code": error.get("code") or f"HTTP_{status}",
                    "next_action": "REPORT_LIMITATION", "message": str(error.get("message") or "")[:600]}
    if status != 200:
        fresh = _fresh_bundle(client, results, str(need["need_id"]), rebuild)
        if fresh.get("status") == "REJECTED":
            return fresh
        status, data, meta = client.dataset_file(fresh["bundle_id"], str(arguments.data_request), results.request_id)
        if status != 200:
            error = meta.get("error") if isinstance(meta.get("error"), dict) else {}
            return _rebuild_refused(f"The extracted data could not be read: {error.get('message') or status}")
        data_status = "REBUILT"
    definition = {"data_request": arguments.data_request, "source_table": request.get("source_table"),
                  "columns": request.get("columns"), "ranges": meta.get("ranges") or request.get("ranges"),
                  "filter": request.get("scope"), "rows": meta.get("rows"),
                  "notes": "Rows the approved data need delivered, inside the approved ranges (warm-up rows left out)."}
    lineage = {"need_id": need.get("need_id"), "data_request": arguments.data_request,
               "source_table": request.get("source_table"), "data_status": data_status,
               **({"same_rows_as_original": meta.get("rows_identity") == original} if original else {})}
    includes = {"definition": arguments.include_definition is not False, "lineage": arguments.include_lineage is not False}
    export_meta = {"format": "PARQUET", "checksum_sha256": hashlib.sha256(data).hexdigest(), "target": arguments.format,
                   **({"definition": texts.export_definition(definition)}
                      if includes["definition"] and arguments.format == "XLSX" else {}),
                   **({"lineage": texts.export_lineage(lineage)}
                      if includes["lineage"] and arguments.format == "XLSX" else {})}
    names = [str(c) for c in meta.get("columns") or []][:MAX_COLUMNS]
    if arguments.format == "XLSX" and names:
        labels = {item.column: item.label[:80] for item in arguments.column_labels or []
                  if item.column in names and item.label.strip()}
        export_meta["columns"] = texts.export_columns(names, labels, {})
        export_meta["headers"] = {row["name"]: row["label"] for row in export_meta["columns"]}
        export_meta["texts"] = texts.EXPORT_READING
        export_meta = fit_header(export_meta)
    status, body, headers = stored_op(client, "export", data, export_meta, timeout=timeout)
    if status != 200:
        return _refused(status, body)
    kept = _kept(results, arguments.format, f"{need.get('need_id')}:{arguments.data_request}",
                 file_name(f"data_{request.get('logical_name') or arguments.data_request}", str(arguments.data_request),
                           headers.get("x-saniti-extension") or arguments.format.lower()), headers, body, includes)
    if kept.get("status") == "EXPORTED":
        kept.update(data_status=data_status, rows=meta.get("rows"),
                    **({"same_rows_as_original": lineage["same_rows_as_original"]}
                       if "same_rows_as_original" in lineage else {}))
    return kept


def rebuild_support(client: SandboxClient, results: Any, entry: dict[str, Any],
                    rebuild: Callable[[str], dict[str, Any]] | None, timeout: float) -> dict[str, Any]:
    """E9(f) (user decision 2026-10-16 "lewat 1 bulan ... go for option F"): a supporting table no longer kept is made
    again without the model: the same approved need extracted again, a new session, the stored code of the session
    run in its order, the analysis completed; the file is returned only when it equals the original byte for byte
    (its checksum). Anything else is refused with the reason."""
    support = entry.get("support") if isinstance(entry.get("support"), dict) else {}
    lineage = entry.get("lineage") if isinstance(entry.get("lineage"), dict) else {}
    checksum, need_id, session_id = support.get("checksum_sha256"), lineage.get("need_id"), entry.get("session_id")
    if not (checksum and need_id and session_id) or results.store is None:
        return _rebuild_refused("The table's need, session or checksum is not recorded, so it cannot be rebuilt.")
    executions = [e for e in results.store.executions_of_session(results.conversation_id, str(session_id))]
    last = max((i for i, e in enumerate(executions) if e.get("request_id") == entry.get("request_id")), default=-1)
    executions = [e for e in executions[:last + 1] if e.get("status") == "OK"]
    if not executions:
        return _rebuild_refused("No stored code of the session that made this table is kept.")
    if any(e.get("code_truncated") for e in executions):
        return _rebuild_refused("The stored code of the session was cut (longer than the store keeps).")
    fresh = _fresh_bundle(client, results, str(need_id), rebuild)
    if fresh.get("status") == "REJECTED":
        return fresh
    from .session import _call  # the session routes, called directly: no model, no refs, no answer outputs

    opened = _call(client, "POST", "/v1/sessions", timeout=timeout + 30,
                   json={"request_id": results.request_id, "bundle_id": fresh["bundle_id"]})
    new_session = opened.get("session_id")
    if not new_session:
        return _rebuild_refused("A session for the rebuild could not be opened: " + str(
            (opened.get("error") or {}).get("message") or opened.get("message") or opened.get("status")))
    for execution in executions:
        ran = _call(client, "POST", f"/v1/sessions/{new_session}/execute", timeout=timeout * 4,
                    json={"request_id": results.request_id, "code": execution["code"]})
        if ran.get("status") != "OK":
            return _rebuild_refused(f"Running the stored code again failed at {execution.get('execution_id')}: "
                                    + str(ran.get("error_message") or ran.get("status")))
    done = _call(client, "POST", f"/v1/sessions/{new_session}/complete", timeout=timeout * 2,
                 json={"request_id": results.request_id})
    match = next((o for o in done.get("released_outputs") or []
                  if o.get("support") and o.get("name") == entry.get("name")), None)
    if done.get("status") != "COMPLETED" or match is None:
        return _rebuild_refused(f"The rerun did not release a supporting table named {entry.get('name')!r}.")
    if match.get("checksum_sha256") != checksum:
        return _rebuild_refused("The rebuilt table differs from the original (the source data or the code's result "
                                "changed), so it is not exported.", rebuilt_rows=match.get("row_count"),
                                original_rows=entry.get("row_count"))
    if results.fetch is None:
        return _rebuild_refused("The rebuilt file cannot be read from the sandbox.")
    return {"status": "REBUILT", "data": results.fetch(new_session, str(match["output_id"]))}


UNCHECKED = {"status": "UNCHECKED"}


def completeness(client: SandboxClient, governor: Any, table_facts: Any, record: dict[str, Any], need_id: Any,
                 names: list[str], data: bytes, kind: str, timeout: float,
                 copied: dict[str, str] | None = None) -> dict[str, Any]:
    """EXEC-Y Fase 3 E1(1) (user decision 2026-10-09 "E1 ok 2-4"): the days the source table has, per group, over the
    file's own period, for the sandbox to set against the file's days. Derived, so a new table needs no code:
      - a file column stands for the source column of the same name, or the one the model named for it (copied);
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
        source_of = {name: (copied or {}).get(name, name) for name in names}
        requests = [r for r in need.get("requests") or [] if isinstance(r, dict) and r.get("source_table")]
        facts = table_facts(sorted({r["source_table"] for r in requests}), sorted(set(source_of.values()))) \
            if requests else {}
        best = None
        for request in requests:
            table = facts.get(request["source_table"]) or {}
            time_column = table.get("time_column")
            file_time = next((n for n in names if source_of[n] == time_column), None)
            if not time_column or file_time is None or request.get("restrictions") \
                    or not isinstance(request.get("scope_spec"), dict):
                continue
            groups = [n for n in names if n != file_time and source_of[n] in table.get("groupable", set())]
            if best is None or len(groups) > len(best[2]):
                best = (request, table, groups, file_time)
        if best is None or len(best[2]) > 6:
            return UNCHECKED
        request, table, groups, file_time = best
        meta = {"format": kind, "checksum_sha256": hashlib.sha256(data).hexdigest(), "column": file_time,
                "columns": [file_time]}
        ends = []
        for measure in ("MIN", "MAX"):
            status, body, _ = stored_op(client, "recount", data, {**meta, "measure": measure}, timeout=timeout)
            value = body.get("value") if status == 200 and isinstance(body, dict) else None
            if not isinstance(value, str) or len(value) < 10:
                return UNCHECKED
            ends.append(value[:10])
        spec = {"summary_version": "summary_spec/v1", "source_table": request["source_table"],
                "scope": request["scope_spec"], "restrictions": [], "group_by": [source_of[g] for g in groups],
                "measures": [{"column": None, "function": "COUNT", "as": "row_count"}],
                "period": {"from": ends[0], "to": ends[1]}}
        answer = governor.summary(spec, {"purpose": "EVIDENCE", "recipe_sha256": sha256_json(spec)}, timeout=timeout)
        rows = answer.get("rows") or []
        if answer.get("status") != "OK" or len(rows) > MAX_COMPLETENESS_GROUPS:
            return UNCHECKED
        return {"status": "CHECKED", "time_column": file_time, "group_columns": groups, "from": ends[0],
                "to": ends[1], "calendar_dates": (answer.get("period") or {}).get("calendar_dates"),
                "row_presence": table.get("row_presence"),
                "groups": [{"key": [row.get(source_of[g]) for g in groups], "days": row.get("days_present")}
                           for row in rows]}
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
