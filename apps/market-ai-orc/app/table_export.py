"""The table download of an answer (user 2026-10-20: "tambah ICON download ... excel", "hanya kolom yang tampil di
jawaban dengan judulnya, ditambah sheet definisi", "Ok, opsi A", "Ok gapapa").

EDGE's download icon on an answer table asks POST /v1/conversations/{conversation_id}/outputs/{output_id}/export with
the columns and titles the answer shows. No model is called: the export_result tool's own handler writes the XLSX from
the conversation's kept copy of the table (every row, through the sandbox's stored-table export, no session), adds the
definition sheet and the input sheets, extracts the inputs again with the same approved data need when the sandbox no
longer keeps them, and keeps the file in AI_conversation_export for the existing download route. One download of a
table runs at a time.
"""
from __future__ import annotations

import re
import secrets
import threading
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from . import data_record as records
from .conversations import ConversationError, reuse_key
from .tools.analysis import current_conversation_key
from .tools.artifacts import RunResults, current_results
from .tools.export import ColumnLabel, TableExportArgs
from .tools.registry import ToolError
from .tools.request_data import current_request_id

OUTPUT_ID_RE = re.compile(r"^out_[0-9a-f]{24}$")
MAX_COLUMNS = 60
_guard = threading.Lock()
_running: set[tuple[str, str]] = set()


class TableExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    columns: list[str] | None = Field(default=None, max_length=MAX_COLUMNS,
                                      description="The table's columns as the answer shows them, in order.")
    titles: list[str] | None = Field(default=None, max_length=MAX_COLUMNS,
                                     description="The title of each column, in the same order.")


class TableExportError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def export_table(*, registry: Any, result_store: Any, conversations: Any, owner: str, conversation_id: str,
                 output_id: str, request: TableExportRequest) -> dict[str, Any]:
    """The kept export (export_id, file name, size, download path, the input sheets' statuses), or TableExportError."""
    spec = registry.get("export_result") if registry is not None else None
    if result_store is None or conversations is None or spec is None:
        raise TableExportError(404, "EXPORT_NOT_AVAILABLE", "Table downloads need the conversation and result "
                                                            "stores and the export tool.")
    if not OUTPUT_ID_RE.fullmatch(output_id):
        raise TableExportError(404, "OUTPUT_NOT_FOUND", "No such table in this conversation.")
    try:
        record = conversations.data_record(owner, conversation_id)
    except ConversationError as error:
        raise TableExportError(error.http_status, error.code, str(error)) from None
    record = records.copy_of(record)
    if not any(o.get("output_id") == output_id for o in record.get("outputs") or []) \
            and result_store.output(conversation_id, output_id) is None:
        raise TableExportError(404, "OUTPUT_NOT_FOUND", "No such table in this conversation.")
    columns = [str(c) for c in request.columns or []]
    titles = [str(t) for t in request.titles or []]
    labels = [ColumnLabel(column=c, label=t[:80]) for c, t in zip(columns, titles) if c and t.strip()]
    key = (conversation_id, output_id)
    with _guard:
        if key in _running:
            raise TableExportError(409, "EXPORT_IN_PROGRESS", "This table's file is being prepared.")
        _running.add(key)
    request_id = f"export_{secrets.token_hex(12)}"
    tokens = [(current_results, current_results.set(RunResults(conversation_id=conversation_id, request_id=request_id,
                                                                store=result_store, record=record))),
              (current_request_id, current_request_id.set(request_id)),
              (current_conversation_key, current_conversation_key.set(reuse_key(owner, conversation_id)))]
    try:
        result = spec.handler(TableExportArgs(
            ref=None, output_id=output_id, evidence_id=None, data_request=None, need_id=None, format="XLSX",
            include_definition=True, include_lineage=True, column_labels=labels or None, source_columns=None,
            select=columns or None))
    except ToolError as exc:
        raise TableExportError(503, exc.code or "EXPORT_FAILED", str(exc)) from None
    finally:
        for variable, token in reversed(tokens):
            variable.reset(token)
        with _guard:
            _running.discard(key)
    if not isinstance(result, dict) or result.get("status") != "EXPORTED":
        error = result if isinstance(result, dict) else {}
        raise TableExportError(422, str(error.get("code") or "EXPORT_FAILED"),
                               str(error.get("message") or "The file could not be written."))
    return {k: result.get(k) for k in ("export_id", "file_name", "size_bytes", "format", "download", "inputs",
                                       "inputs_data_status") if result.get(k) is not None}
