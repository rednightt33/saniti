"""Durable records of the DataNeed flow (SQLite on the service's private volume, root only).

data_needs   every submitted DataNeedSpec revision with its validation result (approved ones carry the immutable
             approved contract the planner, profiler and coverage validator work from)
bundles      immutable governed data bundles (manifest + checksum); files live in the dataset cache
sessions     persistent analysis sessions bound to one request and one bundle
executions   one row per code execution in a session (status, error, data access log, outputs)
outputs      outputs emitted by sessions; released only after a coverage PASS
completions  ExecutionManifest + coverage result + final status of a completed session

Analysis processes never reach this database. Hidden model reasoning is never stored.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

JSON_FIELDS = {"submitted", "result", "approved", "governance", "research", "manifest", "error", "access", "outputs",
               "meta", "execution_manifest", "coverage", "final_status", "usage", "columns"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS data_needs (
    need_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    request_group_id TEXT,
    revision INTEGER,
    mode TEXT,
    status TEXT NOT NULL,
    spec_sha256 TEXT NOT NULL,
    submitted TEXT NOT NULL,
    result TEXT NOT NULL,
    approved TEXT,
    governance TEXT,
    research TEXT,
    extraction_allowed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS data_needs_group ON data_needs (request_id, request_group_id, revision);
CREATE TABLE IF NOT EXISTS bundles (
    bundle_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    need_id TEXT NOT NULL,
    request_group_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    status TEXT NOT NULL,
    checksum_sha256 TEXT,
    manifest TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT
);
CREATE INDEX IF NOT EXISTS bundles_request ON bundles (request_id);
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    bundle_id TEXT NOT NULL,
    status TEXT NOT NULL,
    slot INTEGER,
    created_at TEXT NOT NULL,
    last_active_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    closed_at TEXT,
    close_reason TEXT,
    executions INTEGER NOT NULL DEFAULT 0,
    failed_executions INTEGER NOT NULL DEFAULT 0,
    usage TEXT
);
CREATE INDEX IF NOT EXISTS sessions_request ON sessions (request_id);
CREATE TABLE IF NOT EXISTS executions (
    execution_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    kind TEXT NOT NULL,
    code_sha256 TEXT,
    idempotency_key TEXT,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    runtime_ms INTEGER,
    cpu_seconds REAL,
    error TEXT,
    access TEXT,
    outputs TEXT
);
CREATE INDEX IF NOT EXISTS executions_session ON executions (session_id, seq);
CREATE TABLE IF NOT EXISTS outputs (
    output_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    format TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    byte_count INTEGER NOT NULL,
    row_count INTEGER,
    columns TEXT,
    checksum_sha256 TEXT NOT NULL,
    meta TEXT,
    released INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS outputs_session ON outputs (session_id);
CREATE TABLE IF NOT EXISTS completions (
    completion_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    bundle_id TEXT NOT NULL,
    need_id TEXT NOT NULL,
    coverage_status TEXT NOT NULL,
    execution_manifest TEXT NOT NULL,
    coverage TEXT NOT NULL,
    final_status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS completions_request ON completions (request_id);
"""


class DataNeedStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(SCHEMA)

    @staticmethod
    def _encode(fields: dict[str, Any]) -> dict[str, Any]:
        return {k: (json.dumps(v, separators=(",", ":"), default=str) if k in JSON_FIELDS and v is not None else v)
                for k, v in fields.items()}

    @staticmethod
    def _decode(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {k: (json.loads(row[k]) if k in JSON_FIELDS and row[k] is not None else row[k]) for k in row.keys()}

    def _insert(self, table: str, record: dict[str, Any]) -> None:
        data = self._encode(record)
        with self._lock:
            self._db.execute(f"INSERT INTO {table} ({', '.join(data)}) VALUES ({', '.join('?' * len(data))})",
                             tuple(data.values()))

    def _update(self, table: str, key: str, value: str, fields: dict[str, Any]) -> None:
        data = self._encode(fields)
        with self._lock:
            self._db.execute(f"UPDATE {table} SET {', '.join(f'{k} = ?' for k in data)} WHERE {key} = ?",
                             (*data.values(), value))

    def _one(self, sql: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
        with self._lock:
            return self._decode(self._db.execute(sql, params).fetchone())

    def _all(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        with self._lock:
            return [self._decode(row) for row in self._db.execute(sql, params).fetchall()]

    # data needs
    def insert_need(self, record: dict[str, Any]) -> None:
        self._insert("data_needs", record)

    def get_need(self, need_id: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM data_needs WHERE need_id = ?", (need_id,))

    def needs_for_group(self, request_id: str, group: str) -> list[dict[str, Any]]:
        return self._all("SELECT * FROM data_needs WHERE request_id = ? AND request_group_id = ? ORDER BY revision, "
                         "created_at", (request_id, group))

    def needs_for_request(self, request_id: str) -> list[dict[str, Any]]:
        return self._all("SELECT * FROM data_needs WHERE request_id = ? ORDER BY created_at", (request_id,))

    # bundles
    def insert_bundle(self, record: dict[str, Any]) -> None:
        self._insert("bundles", record)

    def get_bundle(self, bundle_id: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM bundles WHERE bundle_id = ?", (bundle_id,))

    def bundles_for(self, request_id: str) -> list[dict[str, Any]]:
        return self._all("SELECT * FROM bundles WHERE request_id = ? ORDER BY created_at", (request_id,))

    def all_bundles(self) -> list[dict[str, Any]]:
        return self._all("SELECT * FROM bundles ORDER BY created_at", ())

    def set_bundle_status(self, bundle_id: str, status: str) -> None:
        self._update("bundles", "bundle_id", bundle_id, {"status": status})

    def bundle_for_need(self, need_id: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM bundles WHERE need_id = ? AND status = 'READY' ORDER BY created_at DESC "
                         "LIMIT 1", (need_id,))

    # sessions
    def insert_session(self, record: dict[str, Any]) -> None:
        self._insert("sessions", record)

    def update_session(self, session_id: str, **fields: Any) -> None:
        self._update("sessions", "session_id", session_id, fields)

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM sessions WHERE session_id = ?", (session_id,))

    def sessions_for(self, request_id: str) -> list[dict[str, Any]]:
        return self._all("SELECT * FROM sessions WHERE request_id = ? ORDER BY created_at", (request_id,))

    def open_sessions(self) -> list[dict[str, Any]]:
        return self._all("SELECT * FROM sessions WHERE status IN ('ACTIVE', 'BUSY') ORDER BY created_at", ())

    def close_orphans(self, now: str) -> int:
        with self._lock:
            cursor = self._db.execute("UPDATE sessions SET status = 'CLOSED', closed_at = ?, "
                                      "close_reason = 'SANDBOX_RESTARTED' WHERE status IN ('ACTIVE', 'BUSY')", (now,))
            return cursor.rowcount

    # executions
    def insert_execution(self, record: dict[str, Any]) -> None:
        self._insert("executions", record)

    def update_execution(self, execution_id: str, **fields: Any) -> None:
        self._update("executions", "execution_id", execution_id, fields)

    def get_execution(self, execution_id: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM executions WHERE execution_id = ?", (execution_id,))

    def executions_for(self, session_id: str) -> list[dict[str, Any]]:
        return self._all("SELECT * FROM executions WHERE session_id = ? ORDER BY seq", (session_id,))

    def find_execution(self, session_id: str, key: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM executions WHERE session_id = ? AND idempotency_key = ? ORDER BY seq DESC "
                         "LIMIT 1", (session_id, key))

    # outputs
    def insert_output(self, record: dict[str, Any]) -> None:
        self._insert("outputs", record)

    def get_output(self, output_id: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM outputs WHERE output_id = ?", (output_id,))

    def outputs_for(self, session_id: str) -> list[dict[str, Any]]:
        return self._all("SELECT * FROM outputs WHERE session_id = ? ORDER BY created_at", (session_id,))

    def release_outputs(self, output_ids: list[str]) -> None:
        with self._lock:
            self._db.executemany("UPDATE outputs SET released = 1 WHERE output_id = ?", [(i,) for i in output_ids])

    def expired_outputs(self, now: str) -> list[dict[str, Any]]:
        return self._all("SELECT * FROM outputs WHERE expires_at <= ?", (now,))

    def delete_output(self, output_id: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM outputs WHERE output_id = ?", (output_id,))

    # completions
    def insert_completion(self, record: dict[str, Any]) -> None:
        self._insert("completions", record)

    def completions_for(self, request_id: str) -> list[dict[str, Any]]:
        return self._all("SELECT * FROM completions WHERE request_id = ? ORDER BY created_at", (request_id,))

    def completion_for_session(self, session_id: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM completions WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
                         (session_id,))

    def close(self) -> None:
        with self._lock:
            self._db.close()
