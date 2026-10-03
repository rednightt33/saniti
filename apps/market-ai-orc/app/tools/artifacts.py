"""Results of earlier answers opened again (round 2026-10-03 D2; ROUND_PLAN_2026-10-03_FASE_D.md).

get_session_output read an output only from the sandbox, which deletes it after 24 hours, and needed the session id;
an execution's code could not be opened at all. Every released output and execution is kept with the conversation
(R-STORE), so this module opens them from there when the sandbox no longer has them:

- an output by its value reference (out.o3), its output_id, or session_id + output_id as before;
- the code of an execution (execution_id), with what it read and the outputs it released.

The orchestrator sets the run's results context (conversation, store, data record, the sandbox file fetch); without
it (no conversation, or the result store off) only the sandbox is read, exactly as before. orc cannot read Parquet:
a stored table is paged by the sandbox's stored-table operation on the uploaded file.
"""
from __future__ import annotations

import base64
import contextvars
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..result_store import ResultStore, StoredOutput, output_bytes
from .analysis import SandboxClient
from .registry import ToolError

STORED_TABLES_VERSION = 1  # the sandbox's POST /v1/stored-tables/{page,export,recount}
SCRIPT_MAX_CHARS = 20_000
ACCESS_MAX_ENTRIES = 20
REF_RE = re.compile(r"^(?:out\.)?(o[1-9][0-9]{0,3})$")
TABULAR = ("PARQUET", "CSV")


@dataclass
class RunResults:
    """What a run may open of its conversation: set by the orchestrator per run."""
    conversation_id: str | None
    request_id: str
    store: ResultStore | None
    record: dict[str, Any] = field(default_factory=dict)  # the conversation's data record (live)
    fetch: Callable[[str, str], bytes] | None = None  # (session_id, output_id) -> the sandbox's released file
    pending: list[dict[str, Any]] = field(default_factory=list)  # this run's executions, kept when it ends (live)
    evidence: list[dict[str, Any]] = field(default_factory=list)  # D6: this run's checked claims (live)


current_results: contextvars.ContextVar[RunResults | None] = contextvars.ContextVar("current_results", default=None)


def resolve_ref(record: dict[str, Any], ref: str) -> dict[str, Any] | None:
    """The data record's entry of a value reference (out.o3 or o3), or None."""
    match = REF_RE.match(ref.strip())
    if not match:
        return None
    wanted = f"out.{match.group(1)}"
    return next((o for o in record.get("outputs") or [] if isinstance(o, dict) and o.get("ref") == wanted), None)


def stored_op(client: SandboxClient, op: str, data: bytes, meta: dict[str, Any], timeout: float = 120.0
              ) -> tuple[int, Any, dict[str, str]]:
    """(HTTP status, JSON body or file bytes, headers) of POST /v1/stored-tables/{op} on an uploaded stored file."""
    encoded = base64.urlsafe_b64encode(json.dumps(meta, default=str).encode()).decode().rstrip("=")
    response = client._call("POST", f"/v1/stored-tables/{op}", timeout=timeout, content=data,
                            headers={"X-Saniti-Output-Meta": encoded, "Content-Type": "application/octet-stream"})
    if response.status_code == 200 and op == "export":
        return 200, response.content, dict(response.headers)
    return response.status_code, client._json(response), dict(response.headers)


def _rejected(body: Any, status: int) -> dict[str, Any]:
    error = body.get("error") if isinstance(body, dict) and isinstance(body.get("error"), dict) else {}
    return {"status": "REJECTED", "code": error.get("code") or f"HTTP_{status}",
            "message": str(error.get("message") or "")[:600],
            "next_action": (body.get("next_action") if isinstance(body, dict) else None) or "REPORT_LIMITATION",
            **{k: v for k, v in error.items() if k in ("columns", "size_bytes", "limit_bytes")}}


def short_lineage(lineage: Any) -> dict[str, Any] | None:
    if not isinstance(lineage, dict):
        return None
    return {k: lineage[k] for k in ("execution_id", "need_id", "bundle_id", "data_as_of", "code_sha256")
            if lineage.get(k)}


def read_stored(client: SandboxClient, results: RunResults, output_id: str, offset: int, limit: int
                ) -> dict[str, Any]:
    """One page of a stored output (R-STORE), in the shape of a sandbox read of a released output."""
    if results.store is None or not results.conversation_id:
        return {"status": "REJECTED", "code": "OUTPUT_NOT_AVAILABLE", "next_action": "REPORT_LIMITATION",
                "message": "The sandbox no longer holds this output and results are not kept for this conversation."}
    stored = results.store.output(results.conversation_id, output_id)
    if stored is None:
        return {"status": "REJECTED", "code": "OUTPUT_NOT_FOUND", "next_action": "FIX_ARGUMENTS",
                "message": "No output with this id belongs to this conversation."}
    base = _stored_base(stored)
    if stored.format not in ("PARQUET", "CSV", "JSON", "TEXT"):
        return {**base, "note": "Binary output (chart or file): metadata only."}
    data = results.store.content(results.conversation_id, stored)
    status, body, _ = stored_op(client, "page", data, {"format": stored.format,
                                                       "checksum_sha256": stored.checksum_sha256,
                                                       "offset": offset, "limit": limit})
    if status != 200:
        return _rejected(body, status)
    return {**base, **{k: v for k, v in body.items() if k in ("row_count", "offset", "rows", "content",
                                                               "next_offset")}}


def _stored_base(stored: StoredOutput) -> dict[str, Any]:
    return {"output_id": stored.output_id, "name": stored.name, "type": "TABLE" if stored.format in TABULAR
            else stored.format, "format": stored.format, "byte_count": stored.byte_count,
            "checksum_sha256": stored.checksum_sha256, "released": True, "read_mode": "READ_RELEASED",
            "origin": {"request_id": stored.request_id, "evidence_label": stored.label, "source": "STORE"},
            "label": stored.label or "DATA_COVERAGE_VERIFIED",
            "meta": {"definition": stored.definition, "units": stored.units},
            "data_as_of": stored.data_as_of, "lineage": short_lineage(stored.lineage)}


def record_source_tables(record: dict[str, Any], need_id: Any) -> list[str]:
    """The tables an output's data need read, from the data record: each request's source table and the tables of its
    restrictions."""
    need = next((n for n in record.get("needs") or [] if isinstance(n, dict) and n.get("need_id") == need_id), {})
    tables: list[str] = []
    for request in need.get("requests") or []:
        names = [request.get("source_table")] + [str(r).split(":", 1)[0] for r in request.get("restrictions") or []]
        tables += [n for n in names if n and n not in tables]
    return tables


def read_output_any(client: SandboxClient, session_id: str | None, output_id: str, request_id: str, offset: int,
                    limit: int, timeout: float = 15.0) -> dict[str, Any]:
    """The sandbox's copy while it has it, else the conversation's stored copy (the value references' row reader
    and get_session_output both use this)."""
    from .session import read_output

    body: dict[str, Any] = {"status": "REJECTED", "code": "OUTPUT_NOT_AVAILABLE"}
    if session_id:
        body = read_output(client, session_id, output_id, request_id, offset, limit, timeout)
        if body.get("status") != "REJECTED":
            return body
    results = current_results.get()
    if results is None or results.store is None:
        return body
    return read_stored(client, results, output_id, offset, limit)


def read_execution(results: RunResults | None, execution_id: str, include_content: bool) -> dict[str, Any]:
    """SCRIPT: the stored code of an execution (20,000 characters at most when asked), what it read and released."""
    if results is None or results.store is None or not results.conversation_id:
        return {"status": "REJECTED", "code": "OUTPUT_NOT_AVAILABLE", "next_action": "REPORT_LIMITATION",
                "message": "Executions are not kept for this conversation."}
    row = results.store.execution(results.conversation_id, execution_id) or pending_execution(results, execution_id)
    if row is None:
        return {"status": "REJECTED", "code": "EXECUTION_NOT_FOUND", "next_action": "FIX_ARGUMENTS",
                "message": "No execution with this id belongs to this conversation (it may still be running in "
                           "this answer: executions are kept when the answer ends)."}
    access = row.get("access")
    reads = access.get("reads") if isinstance(access, dict) else access if isinstance(access, list) else []
    out = {"kind": "SCRIPT", "execution_id": execution_id, "request_id": row["request_id"],
           "status": row.get("status"), "code_sha256": row["code_sha256"], "code_chars": len(row["code"]),
           "code_truncated_at_storage": bool(row.get("code_truncated")), "modules": row.get("modules") or [],
           "reads": (reads or [])[:ACCESS_MAX_ENTRIES],
           "outputs": results.store.outputs_of_execution(results.conversation_id, execution_id)
           or [{k: o.get(k) for k in ("output_id", "name", "type", "ref")} for o in results.record.get("outputs") or []
               if isinstance(o, dict) and (o.get("lineage") or {}).get("execution_id") == execution_id]}
    if include_content:
        code = str(row["code"])
        out["code"] = code[:SCRIPT_MAX_CHARS]
        out["code_shown_chars"] = min(len(code), SCRIPT_MAX_CHARS)
        if len(code) > SCRIPT_MAX_CHARS:
            out["note"] = "Only the first characters of the code are shown."
    return out


def pending_execution(results: RunResults, execution_id: str) -> dict[str, Any] | None:
    """An execution of this answer, not kept yet (executions are stored when the answer ends)."""
    import hashlib

    for item in results.pending:
        if item.get("execution_id") == execution_id:
            code = str(item.get("code") or "")
            return {**item, "request_id": results.request_id, "code": code, "code_truncated": False,
                    "code_sha256": hashlib.sha256(code.encode()).hexdigest()}
    return None


def source_bytes(results: RunResults | None, output_id: str, session_id: str | None
                 ) -> tuple[bytes, StoredOutput | None]:
    """The file of an output for export or evidence: the sandbox's while it has it, else the stored copy."""
    if results is None:
        raise ToolError("Results of this conversation are not available.", code="OUTPUT_NOT_AVAILABLE")
    try:
        return output_bytes(results.store, results.fetch, results.conversation_id, output_id, session_id)
    except LookupError as exc:
        raise ToolError(str(exc), code="OUTPUT_NOT_AVAILABLE") from None
