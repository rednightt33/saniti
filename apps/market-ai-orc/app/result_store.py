"""R-STORE (round 2026-10-03 phase C2; ROUND_PLAN_2026-10-03_FASE_C.md): released results kept for the life of the
conversation, and put back into a later sandbox session after the sandbox's own copy expired.

The python sandbox keeps a released table for 24 hours (PY_SANDBOX_RESULT_RETENTION_HOURS) and an execution's code
only as a hash. A conversation that came back later could not load its tables or say how they were made. After every
completed analysis or research group the orchestrator copies each released output into AI_conversation_output (the
file up to 20 MB and 50,000 rows in Postgres, a larger one in the bucket market-ai-conversation-outputs), and the code
of every execution into AI_conversation_execution. When a session opens, every stored table of the conversation that
the sandbox no longer holds is uploaded back (user decision 2026-10-03: all of them, at most 40), so load_output works
as before, with the table's original label, definition, units and data date.

Storing never fails an answer: a failure is logged (result_store_failed) and the data record says stored false.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg.rows import dict_row

logger = logging.getLogger("market_ai_orc")

POSTGRES_MAX_BYTES = 20 * 1024 * 1024  # user decision 3 (2026-10-03): a table up to 20 MB and 50,000 rows in Postgres
POSTGRES_MAX_ROWS = 50_000
CONVERSATION_POSTGRES_BUDGET = 200 * 1024 * 1024  # beyond this, a conversation's further tables go to the bucket
MAX_CODE_CHARS = 65_536
RESTORE_MAX_TABLES = 40  # the sandbox's carried limit
RESTORE_MAX_BYTES = 500 * 1024 * 1024  # per session open
EXTENSIONS = {"PARQUET": "parquet", "CSV": "csv", "PNG": "png", "JSON": "json", "TEXT": "txt", "BIN": "bin"}
WRITE_TIMEOUT = "60s"  # the login's default statement_timeout (5 s) is for chat rows, not a 20 MB table


def _log(event: str, **fields: Any) -> None:
    logger.info(json.dumps({"event": event, **fields}, default=str, separators=(",", ":")))


class ResultBucket:
    """The private bucket market-ai-conversation-outputs (RESULT_BUCKET_*), for tables larger than Postgres keeps."""

    def __init__(self, name: str, endpoint: str, region: str, access_key_id: str, secret_access_key: str) -> None:
        import boto3  # only when the bucket is configured
        from botocore.config import Config

        self.name = name
        self.client = boto3.client("s3", endpoint_url=endpoint, region_name=region or None,
                                   aws_access_key_id=access_key_id, aws_secret_access_key=secret_access_key,
                                   config=Config(signature_version="s3v4", retries={"max_attempts": 3}))

    def put(self, key: str, data: bytes) -> None:
        self.client.put_object(Bucket=self.name, Key=key, Body=data, ContentType="application/octet-stream")

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.name, Key=key)["Body"].read()

    def delete(self, keys: list[str]) -> None:
        for start in range(0, len(keys), 1000):
            chunk = keys[start:start + 1000]
            if chunk:
                self.client.delete_objects(Bucket=self.name, Delete={"Objects": [{"Key": k} for k in chunk]})


@dataclass
class StoredOutput:
    output_id: str
    name: str
    format: str
    byte_count: int
    checksum_sha256: str
    storage: str
    object_key: str | None
    label: str | None
    definition: Any
    units: Any
    lineage: Any
    data_as_of: str | None
    request_id: str
    execution_id: str | None


class ResultStore:
    def __init__(self, database_url: str, bucket: ResultBucket | None = None) -> None:
        self.database_url = database_url
        self.bucket = bucket

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self.database_url, row_factory=dict_row, connect_timeout=5)

    # ---------------------------------------------------------------------------------------------------- save

    def save_output(self, conversation_id: str, request_id: str, entry: dict[str, Any], data: bytes) -> str:
        """Keep one released output; returns its storage (POSTGRES or BUCKET). An output already kept is left as is."""
        output_id = str(entry["output_id"])
        fmt = str(entry.get("format") or "BIN").upper()
        checksum = hashlib.sha256(data).hexdigest()
        lineage = entry.get("lineage") if isinstance(entry.get("lineage"), dict) else {}
        rows = entry.get("row_count") if isinstance(entry.get("row_count"), int) else None
        with self._connect() as connection, connection.transaction():
            connection.execute(f"SET LOCAL statement_timeout = '{WRITE_TIMEOUT}'")
            if connection.execute('SELECT 1 FROM public."AI_conversation_output" WHERE output_id = %s',
                                  (output_id,)).fetchone():
                return "ALREADY_STORED"
            used = connection.execute(
                'SELECT coalesce(sum(byte_count), 0) AS used FROM public."AI_conversation_output" '
                "WHERE conversation_id = %s AND storage = 'POSTGRES'", (conversation_id,)).fetchone()["used"]
            in_postgres = len(data) <= POSTGRES_MAX_BYTES and (rows or 0) <= POSTGRES_MAX_ROWS \
                and int(used) + len(data) <= CONVERSATION_POSTGRES_BUDGET
            if not in_postgres and self.bucket is None:
                raise RuntimeError("the table is larger than Postgres keeps and no bucket is configured")
            key = None
            if not in_postgres:
                key = f"outputs/{conversation_id}/{output_id}.{EXTENSIONS.get(fmt, 'bin')}"
                self.bucket.put(key, data)
            try:
                self._insert(connection, conversation_id, request_id, entry, data, fmt, lineage, rows, checksum,
                             in_postgres, key)
            except Exception:
                if key is not None:  # no object without its row
                    self.bucket.delete([key])
                raise
        return "POSTGRES" if in_postgres else "BUCKET"

    @staticmethod
    def _insert(connection: psycopg.Connection, conversation_id: str, request_id: str, entry: dict[str, Any],
                data: bytes, fmt: str, lineage: dict[str, Any], rows: int | None, checksum: str, in_postgres: bool,
                key: str | None) -> None:
        output_id = str(entry["output_id"])
        connection.execute(
            'INSERT INTO public."AI_conversation_output" (output_id, conversation_id, request_id, session_id, '
            "execution_id, name, output_type, format, label, definition, units, lineage, data_as_of, row_count, "
            "columns, byte_count, checksum_sha256, storage, content, object_key) VALUES (%s, %s, %s, %s, %s, %s, "
            "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (output_id, conversation_id, request_id, entry.get("session_id"), lineage.get("execution_id"),
             str(entry.get("name") or output_id)[:80], str(entry.get("type") or "TABLE"), fmt,
             entry.get("label"), _json(entry.get("definition")), _json(entry.get("units")), _json(lineage),
             lineage.get("data_as_of"), rows, _json(entry.get("columns")), len(data), checksum,
             "POSTGRES" if in_postgres else "BUCKET", data if in_postgres else None, key))

    def save_execution(self, conversation_id: str, request_id: str, execution: dict[str, Any]) -> None:
        code = str(execution.get("code") or "")
        with self._connect() as connection, connection.transaction():
            connection.execute(f"SET LOCAL statement_timeout = '{WRITE_TIMEOUT}'")
            connection.execute(
                'INSERT INTO public."AI_conversation_execution" (execution_id, conversation_id, request_id, '
                "session_id, code, code_truncated, code_sha256, modules, access, status) VALUES (%s, %s, %s, %s, %s, "
                "%s, %s, %s, %s, %s) ON CONFLICT (execution_id) DO NOTHING",
                (execution["execution_id"], conversation_id, request_id, execution.get("session_id"),
                 code[:MAX_CODE_CHARS], len(code) > MAX_CODE_CHARS, hashlib.sha256(code.encode()).hexdigest(),
                 _json(execution.get("modules"), list), _json(execution.get("access")), execution.get("status")))

    # --------------------------------------------------------------------------------------------------- read

    def stored_tables(self, conversation_id: str, limit: int = RESTORE_MAX_TABLES) -> list[StoredOutput]:
        """The conversation's stored Parquet tables, newest first (what a new session may carry)."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT output_id, name, format, byte_count, checksum_sha256, storage, object_key, label, definition, "
                "units, lineage, data_as_of::text AS data_as_of, request_id, execution_id "
                'FROM public."AI_conversation_output" WHERE conversation_id = %s AND format = \'PARQUET\' '
                "ORDER BY created_at DESC LIMIT %s", (conversation_id, limit)).fetchall()
        return [StoredOutput(**row) for row in rows]

    def content(self, conversation_id: str, stored: StoredOutput) -> bytes:
        if stored.storage == "BUCKET":
            if self.bucket is None or not stored.object_key:
                raise RuntimeError("the table is in the bucket and no bucket is configured")
            return self.bucket.get(stored.object_key)
        with self._connect() as connection:
            row = connection.execute('SELECT content FROM public."AI_conversation_output" '
                                     "WHERE conversation_id = %s AND output_id = %s",
                                     (conversation_id, stored.output_id)).fetchone()
        if row is None:
            raise RuntimeError("the stored table disappeared")
        return bytes(row["content"])

    def output(self, conversation_id: str, output_id: str) -> StoredOutput | None:
        """One stored output of this conversation (any format), or None; another conversation's never."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT output_id, name, format, byte_count, checksum_sha256, storage, object_key, label, definition, "
                "units, lineage, data_as_of::text AS data_as_of, request_id, execution_id "
                'FROM public."AI_conversation_output" WHERE conversation_id = %s AND output_id = %s',
                (conversation_id, output_id)).fetchone()
        return StoredOutput(**row) if row else None

    def outputs_of_execution(self, conversation_id: str, execution_id: str) -> list[dict[str, Any]]:
        """The outputs one execution released (a chart's tables), without content."""
        with self._connect() as connection:
            return connection.execute(
                "SELECT output_id, name, output_type, format, row_count FROM public.\"AI_conversation_output\" "
                "WHERE conversation_id = %s AND execution_id = %s ORDER BY created_at", (conversation_id,
                                                                                       execution_id)).fetchall()

    def execution(self, conversation_id: str, execution_id: str) -> dict[str, Any] | None:
        """One stored execution of this conversation: code (as stored, at most 65,536 characters), its sha256 of the
        whole code, modules, access (what it read) and status."""
        with self._connect() as connection:
            return connection.execute(
                "SELECT execution_id, request_id, session_id, code, code_truncated, code_sha256, modules, access, "
                'status, created_at::text AS created_at FROM public."AI_conversation_execution" '
                "WHERE conversation_id = %s AND execution_id = %s", (conversation_id, execution_id)).fetchone()

    # ----------------------------------------------------------------------------------------------- evidence

    def save_evidence(self, conversation_id: str, request_id: str, entry: dict[str, Any]) -> None:
        """D6 (round 2026-10-03): one checked claim with at most 200 rows of evidence."""
        with self._connect() as connection, connection.transaction():
            connection.execute(f"SET LOCAL statement_timeout = '{WRITE_TIMEOUT}'")
            connection.execute(
                'INSERT INTO public."AI_conversation_evidence" (evidence_id, conversation_id, request_id, claim, '
                "value_text, kind, recipe, status, backend_value, difference, source, rows, rows_matched) VALUES (%s, "
                "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (entry["evidence_id"], conversation_id, request_id, str(entry["claim"])[:300],
                 str(entry["value_text"])[:40], entry["kind"], _json(entry.get("recipe") or {}), entry["status"],
                 entry.get("backend_value"), entry.get("difference"), _json(entry.get("source") or {}),
                 _json(list(entry.get("rows") or [])[:200], list), entry.get("rows_matched")))

    def evidence(self, conversation_id: str, evidence_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            return connection.execute(
                "SELECT evidence_id, request_id, claim, value_text, kind, recipe, status, backend_value, difference, "
                'source, rows, rows_matched FROM public."AI_conversation_evidence" WHERE conversation_id = %s '
                "AND evidence_id = %s", (conversation_id, evidence_id)).fetchone()

    # ------------------------------------------------------------------------------------------------ exports

    def save_export(self, conversation_id: str, request_id: str, source_ref: str, fmt: str, file_name: str,
                    mime_type: str, data: bytes, includes: dict[str, Any]) -> dict[str, Any]:
        """D4 (round 2026-10-03): a download file, kept in Postgres with the conversation (user decision 2)."""
        import secrets

        export_id = f"exp_{secrets.token_hex(12)}"
        sha = hashlib.sha256(data).hexdigest()
        with self._connect() as connection, connection.transaction():
            connection.execute(f"SET LOCAL statement_timeout = '{WRITE_TIMEOUT}'")
            connection.execute(
                'INSERT INTO public."AI_conversation_export" (export_id, conversation_id, request_id, source_ref, '
                "format, file_name, mime_type, size_bytes, sha256, content, includes) VALUES (%s, %s, %s, %s, %s, %s, "
                "%s, %s, %s, %s, %s)", (export_id, conversation_id, request_id, source_ref[:200], fmt, file_name,
                                       mime_type, len(data), sha, data, _json(includes)))
        return {"export_id": export_id, "file_name": file_name, "format": fmt, "size_bytes": len(data),
                "sha256": sha}

    def export(self, conversation_id: str, export_id: str) -> dict[str, Any] | None:
        """An export's metadata (no content), within its conversation."""
        with self._connect() as connection:
            return connection.execute(
                "SELECT export_id, request_id, source_ref, format, file_name, mime_type, size_bytes, sha256, includes, "
                'created_at::text AS created_at FROM public."AI_conversation_export" '
                "WHERE conversation_id = %s AND export_id = %s", (conversation_id, export_id)).fetchone()

    def owned_export(self, owner: str, export_id: str) -> dict[str, Any] | None:
        """An export's metadata when its conversation belongs to this owner (the download's access rule)."""
        with self._connect() as connection:
            return connection.execute(
                "SELECT e.export_id, e.conversation_id, e.format, e.file_name, e.mime_type, e.size_bytes, e.sha256 "
                'FROM public."AI_conversation_export" e JOIN public."AI_conversation" c '
                "ON c.conversation_id = e.conversation_id WHERE e.export_id = %s AND c.owner_key = %s",
                (export_id, owner)).fetchone()

    def export_chunks(self, conversation_id: str, export_id: str, chunk: int = 1024 * 1024):
        """The file in chunks read with substring, so a 20 MB file is never held whole in memory."""
        position = 1
        with self._connect() as connection:
            while True:
                row = connection.execute(
                    'SELECT substring(content FROM %s FOR %s) AS part FROM public."AI_conversation_export" '
                    "WHERE conversation_id = %s AND export_id = %s", (position, chunk, conversation_id,
                                                                      export_id)).fetchone()
                part = bytes(row["part"]) if row and row["part"] is not None else b""
                if not part:
                    return
                yield part
                position += len(part)

    def object_keys(self, conversation_ids: list[str]) -> list[str]:
        """Bucket keys of these conversations (deleted before their rows by the conversation cleanup)."""
        if not conversation_ids:
            return []
        with self._connect() as connection:
            return [r["object_key"] for r in connection.execute(
                'SELECT object_key FROM public."AI_conversation_output" WHERE conversation_id = ANY(%s) '
                "AND object_key IS NOT NULL", (conversation_ids,)).fetchall()]


def output_bytes(store: ResultStore | None, fetch: Callable[[str, str], bytes] | None, conversation_id: str | None,
                 output_id: str, session_id: str | None) -> tuple[bytes, StoredOutput | None]:
    """D0 (round 2026-10-03): the file of an output, from the sandbox while it still holds it, else from R-STORE
    (Postgres or bucket). Used by get_session_output, export_result and get_evidence. Raises LookupError when neither
    has it."""
    if fetch is not None and session_id:
        try:
            return fetch(session_id, output_id), None
        except Exception:  # noqa: BLE001 - the sandbox's copy expired or the session is gone: try the durable copy
            pass
    if store is None or not conversation_id:
        raise LookupError("the output is no longer in the sandbox and results are not stored for this conversation")
    stored = store.output(conversation_id, output_id)
    if stored is None:
        raise LookupError("the output is not stored for this conversation")
    return store.content(conversation_id, stored), stored


def _json(value: Any, kind: type = dict) -> Any:
    from psycopg.types.json import Jsonb

    if isinstance(value, kind) or (kind is dict and isinstance(value, list)):
        return Jsonb(value)
    return None


# ------------------------------------------------------------------------------------------------ run-level helpers

def store_released(store: ResultStore, fetch: Callable[[str, str], bytes], conversation_id: str, request_id: str,
                   entries: list[dict[str, Any]]) -> dict[str, str]:
    """Copy each released output (fetch(session_id, output_id) -> bytes); output_id -> storage or FAILED."""
    done: dict[str, str] = {}
    for entry in entries:
        output_id = str(entry.get("output_id"))
        if output_id in done or not entry.get("session_id"):
            continue
        started = time.monotonic()
        try:
            data = fetch(str(entry["session_id"]), output_id)
            done[output_id] = store.save_output(conversation_id, request_id, entry, data)
            _log("result_stored", request_id=request_id, output_id=output_id, storage=done[output_id],
                 bytes=len(data), rows=entry.get("row_count"), ms=int((time.monotonic() - started) * 1000))
        except Exception as exc:  # noqa: BLE001 - storing never fails the answer
            done[output_id] = "FAILED"
            _log("result_store_failed", request_id=request_id, output_id=output_id, error=type(exc).__name__,
                 detail=str(exc)[:200])
    return done


def restore_missing(store: ResultStore, upload: Callable[[str, dict[str, Any], bytes], dict[str, Any]],
                    conversation_id: str, request_id: str, session_id: str, view: dict[str, Any],
                    allowed: list[str] | None) -> list[dict[str, Any]]:
    """Upload the conversation's stored tables that the new session does not carry (upload(session_id, meta, data));
    allowed: the research plan's carried tables (None: every table). Returns what was restored or left out."""
    present = set(view.get("carried_output_ids") or []) | {
        str(o.get("output_id")) for o in view.get("carried_outputs") or [] if isinstance(o, dict)}
    started, total, result = time.monotonic(), 0, []
    for stored in store.stored_tables(conversation_id):
        if stored.output_id in present or (allowed is not None and stored.output_id not in allowed):
            continue
        if total + stored.byte_count > RESTORE_MAX_BYTES:
            result.append({"output_id": stored.output_id, "name": stored.name, "status": "STORED_NOT_LOADED"})
            continue
        try:
            data = store.content(conversation_id, stored)
            meta = {"output_id": stored.output_id, "name": stored.name, "format": "PARQUET",
                    "checksum_sha256": stored.checksum_sha256, "definition": stored.definition, "units": stored.units,
                    "data_as_of": stored.data_as_of, "execution_id": stored.execution_id,
                    "origin": {"evidence_label": stored.label, "request_id": stored.request_id,
                               **({"need_id": stored.lineage.get("need_id")} if isinstance(stored.lineage, dict)
                                  else {})}}
            answer = upload(session_id, meta, data)
            total += len(data)
            result.append({"output_id": stored.output_id, "name": stored.name,
                           "status": str(answer.get("status") or answer.get("code") or "FAILED")})
        except Exception as exc:  # noqa: BLE001 - a table that cannot be restored is listed, never fatal
            result.append({"output_id": stored.output_id, "name": stored.name, "status": "RESTORE_FAILED"})
            _log("carried_restore_failed", request_id=request_id, output_id=stored.output_id,
                 error=type(exc).__name__)
    if result:
        _log("carried_restored", request_id=request_id, session_id=session_id, bytes=total,
             ms=int((time.monotonic() - started) * 1000),
             statuses={s: sum(1 for r in result if r["status"] == s) for s in {r["status"] for r in result}})
    return result
