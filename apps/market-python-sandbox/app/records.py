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
               "lineage", "resource_usage", "research_context", "logical_inputs", "reason_codes", "expected_scope",
               "actual_scope", "validation_evidence", "derived_features", "database_features", "self_reported",
               "execution_report", "feature_artifact"}
# Columns added for the Execution Validation Gate; existing databases are migrated in place.
ADDED_COLUMNS = {
    "spec_id": "TEXT", "spec_sha256": "TEXT", "logical_inputs": "TEXT", "validation_status": "TEXT",
    "validation_level": "TEXT", "reason_codes": "TEXT", "expected_scope": "TEXT", "actual_scope": "TEXT",
    "validation_evidence": "TEXT", "derived_features": "TEXT", "database_features": "TEXT", "self_reported": "TEXT",
    "execution_report": "TEXT", "cpu_seconds": "REAL", "reproducible_until": "TEXT", "feature_artifact": "TEXT",
}

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
CREATE INDEX IF NOT EXISTS analyses_request ON analyses (request_id);
CREATE TABLE IF NOT EXISTS specs (
    spec_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    spec_sha256 TEXT NOT NULL,
    status TEXT NOT NULL,
    contract TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS specs_request ON specs (request_id);
CREATE TABLE IF NOT EXISTS derived_features (
    feature_id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL,
    analysis_id TEXT NOT NULL,
    spec_id TEXT NOT NULL,
    name TEXT NOT NULL,
    definition_sha256 TEXT NOT NULL,
    definition TEXT NOT NULL,
    validation_level TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS derived_features_analysis ON derived_features (analysis_id);
CREATE TABLE IF NOT EXISTS dataset_cache (
    file_name TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL,
    checksum_sha256 TEXT NOT NULL,
    byte_count INTEGER NOT NULL,
    expires_at TEXT,
    cached_at TEXT NOT NULL
);
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
        existing = {row["name"] for row in self._db.execute("PRAGMA table_info(analyses)").fetchall()}
        for column, kind in ADDED_COLUMNS.items():
            if column not in existing:
                self._db.execute(f"ALTER TABLE analyses ADD COLUMN {column} {kind}")

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
                "UPDATE analyses SET status = 'FAILED', validation_status = 'UNVERIFIED', "
                "reason_codes = '[\"SANDBOX_RESTARTED\"]', error_code = 'SANDBOX_RESTARTED', "
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
            self._db.execute("DELETE FROM specs WHERE created_at < ?", (before,))
            self._db.execute("DELETE FROM derived_features WHERE created_at < ?", (before,))
            return cursor.rowcount

    # ------------------------------------------------------------ specs (immutable once stored)

    def insert_spec(self, spec_id: str, request_id: str, created_at: str, sha256: str, status: str,
                    contract: dict[str, Any]) -> None:
        with self._lock:
            self._db.execute("INSERT INTO specs (spec_id, request_id, created_at, spec_sha256, status, contract) "
                             "VALUES (?, ?, ?, ?, ?, ?)",
                             (spec_id, request_id, created_at, sha256, status, json.dumps(contract, sort_keys=True)))

    def get_spec(self, spec_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM specs WHERE spec_id = ?", (spec_id,)).fetchone()
        if row is None:
            return None
        return {**dict(row), "contract": json.loads(row["contract"])}

    def count_specs(self, request_id: str) -> int:
        with self._lock:
            return int(self._db.execute("SELECT count(*) FROM specs WHERE request_id = ?", (request_id,)).fetchone()[0])

    # ------------------------------------------------------------ request-level budget

    def request_usage(self, request_id: str) -> dict[str, float]:
        with self._lock:
            row = self._db.execute(
                "SELECT count(*) AS analyses, coalesce(sum(cpu_seconds), 0) AS cpu, "
                "coalesce(sum(input_bytes), 0) AS bytes FROM analyses WHERE request_id = ? AND NOT "
                "(status = 'FAILED' AND error_code IN ('QUEUE_FULL', 'REQUEST_BUDGET_EXCEEDED'))",
                (request_id,)).fetchone()
        return {"analyses": int(row["analyses"]), "cpu_seconds": float(row["cpu"]), "input_bytes": int(row["bytes"])}

    # ------------------------------------------------------------ derived features (for a future Research Governor)

    def add_derived_features(self, request_id: str, analysis_id: str, spec_id: str, created_at: str,
                             features: list[dict[str, Any]]) -> None:
        with self._lock:
            for feature in features:
                self._db.execute(
                    "INSERT INTO derived_features (request_id, analysis_id, spec_id, name, definition_sha256, "
                    "definition, validation_level, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (request_id, analysis_id, spec_id, feature["name"], feature["definition_sha256"],
                     json.dumps(feature, sort_keys=True), feature.get("validation_level"), created_at))

    def derived_features_for(self, analysis_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM derived_features WHERE analysis_id = ? ORDER BY feature_id",
                                    (analysis_id,)).fetchall()
        return [{**dict(r), "definition": json.loads(r["definition"])} for r in rows]

    # ------------------------------------------------------------ dataset cache index

    def cache_add(self, file_name: str, dataset_id: str, checksum: str, byte_count: int, expires_at: str | None,
                  cached_at: str) -> None:
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO dataset_cache (file_name, dataset_id, checksum_sha256, "
                             "byte_count, expires_at, cached_at) VALUES (?, ?, ?, ?, ?, ?)",
                             (file_name, dataset_id, checksum, byte_count, expires_at, cached_at))

    def cache_entries(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._db.execute("SELECT * FROM dataset_cache").fetchall()]

    def cache_remove(self, file_name: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM dataset_cache WHERE file_name = ?", (file_name,))

    def close(self) -> None:
        with self._lock:
            self._db.close()
