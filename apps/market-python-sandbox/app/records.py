"""Durable analysis records and stored outputs (SQLite on the service's private volume).

Only the harness (root) reads or writes this database; analysis processes cannot reach it.
The record keeps metadata for reproducibility and later research-governance controls: inputs and
their checksums, code hash (and source when PY_SANDBOX_RETAIN_CODE), runtime and library versions,
seed, limits, resource usage, outputs, warnings, and errors. Hidden model reasoning is never stored.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

JSON_FIELDS = {"dataset_ids", "expected_outputs", "inputs", "outputs", "warnings", "error_frames", "diagnostics",
               "lineage", "resource_usage", "research_context"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
    analysis_id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL,
    request_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('QUEUED','RUNNING','COMPLETED','FAILED','CANCELLED','EXPIRED')),
    purpose TEXT NOT NULL,
    dataset_ids TEXT NOT NULL,
    expected_outputs TEXT NOT NULL,
    code_sha256 TEXT NOT NULL,
    code TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    runtime_ms INTEGER,
    inputs TEXT,
    input_rows INTEGER,
    input_bytes INTEGER,
    outputs TEXT,
    warnings TEXT,
    error_code TEXT,
    error_message TEXT,
    error_frames TEXT,
    diagnostics TEXT,
    lineage TEXT,
    resource_usage TEXT,
    outputs_expire_at TEXT,
    research_context TEXT
);
CREATE INDEX IF NOT EXISTS analyses_idempotency ON analyses (idempotency_key);
CREATE INDEX IF NOT EXISTS analyses_status ON analyses (status);
CREATE INDEX IF NOT EXISTS analyses_created ON analyses (created_at);
CREATE TABLE IF NOT EXISTS stored_files (
    file_id TEXT PRIMARY KEY,
    analysis_id TEXT NOT NULL REFERENCES analyses (analysis_id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('TABLE','CHART','ARTIFACT')),
    format TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    byte_count INTEGER NOT NULL,
    row_count INTEGER,
    checksum_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS stored_files_analysis ON stored_files (analysis_id);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Records:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.executescript(SCHEMA)

    @staticmethod
    def _encode(fields: dict[str, Any]) -> dict[str, Any]:
        return {k: (json.dumps(v, separators=(",", ":")) if k in JSON_FIELDS and v is not None else v)
                for k, v in fields.items()}

    @staticmethod
    def _decode(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {k: (json.loads(row[k]) if k in JSON_FIELDS and row[k] is not None else row[k]) for k in row.keys()}

    def insert(self, record: dict[str, Any]) -> None:
        data = self._encode(record)
        columns = ", ".join(data)
        with self._lock:
            self._db.execute(f"INSERT INTO analyses ({columns}) VALUES ({', '.join('?' * len(data))})",
                             tuple(data.values()))

    def update(self, analysis_id: str, **fields: Any) -> None:
        data = self._encode(fields)
        assignments = ", ".join(f"{k} = ?" for k in data)
        with self._lock:
            self._db.execute(f"UPDATE analyses SET {assignments} WHERE analysis_id = ?",
                             (*data.values(), analysis_id))

    def transition(self, analysis_id: str, from_status: set[str], **fields: Any) -> bool:
        """Update only if the current status is one of from_status (atomic)."""
        data = self._encode(fields)
        assignments = ", ".join(f"{k} = ?" for k in data)
        marks = ", ".join("?" * len(from_status))
        with self._lock:
            cursor = self._db.execute(
                f"UPDATE analyses SET {assignments} WHERE analysis_id = ? AND status IN ({marks})",
                (*data.values(), analysis_id, *sorted(from_status)))
            return cursor.rowcount == 1

    def get(self, analysis_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM analyses WHERE analysis_id = ?", (analysis_id,)).fetchone()
        return self._decode(row)

    def find_by_key(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM analyses WHERE idempotency_key = ? ORDER BY created_at DESC "
                                   "LIMIT 1", (key,)).fetchone()
        return self._decode(row)

    def interrupt_unfinished(self, now: str) -> int:
        with self._lock:
            cursor = self._db.execute(
                "UPDATE analyses SET status = 'FAILED', error_code = 'SANDBOX_RESTARTED', "
                "error_message = 'The sandbox restarted before this analysis finished. Submit it again.', "
                "completed_at = ? WHERE status IN ('QUEUED', 'RUNNING')", (now,))
            return cursor.rowcount

    # ------------------------------------------------------------ stored output files

    def add_file(self, entry: dict[str, Any]) -> None:
        columns = ", ".join(entry)
        with self._lock:
            self._db.execute(f"INSERT INTO stored_files ({columns}) VALUES ({', '.join('?' * len(entry))})",
                             tuple(entry.values()))

    def get_file(self, file_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM stored_files WHERE file_id = ?", (file_id,)).fetchone()
        return dict(row) if row else None

    def files_for(self, analysis_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM stored_files WHERE analysis_id = ?", (analysis_id,)).fetchall()
        return [dict(r) for r in rows]

    def expired_files(self, now: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM stored_files WHERE expires_at <= ?", (now,)).fetchall()
        return [dict(r) for r in rows]

    def delete_file(self, file_id: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM stored_files WHERE file_id = ?", (file_id,))

    def expire_outputs(self, now: str) -> list[str]:
        """COMPLETED analyses whose outputs passed retention become EXPIRED (metadata is kept)."""
        with self._lock:
            rows = self._db.execute("SELECT analysis_id FROM analyses WHERE status = 'COMPLETED' "
                                    "AND outputs_expire_at IS NOT NULL AND outputs_expire_at <= ?", (now,)).fetchall()
            ids = [r["analysis_id"] for r in rows]
            for analysis_id in ids:
                self._db.execute("UPDATE analyses SET status = 'EXPIRED' WHERE analysis_id = ?", (analysis_id,))
        return ids

    def purge_records(self, before: str) -> int:
        with self._lock:
            cursor = self._db.execute("DELETE FROM analyses WHERE created_at < ? AND status IN "
                                      "('COMPLETED','FAILED','CANCELLED','EXPIRED')", (before,))
            return cursor.rowcount

    def close(self) -> None:
        with self._lock:
            self._db.close()
