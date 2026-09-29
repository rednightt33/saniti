"""Durable records of the DataNeed flow (SQLite on the service's private volume, root only).

data_needs   every submitted DataNeedSpec revision with its validation result (approved ones carry the immutable
             approved contract the planner, profiler and coverage validator work from)
bundles      immutable governed data bundles (manifest + checksum); files live in the dataset cache
sessions     persistent analysis sessions bound to one request and one bundle
executions   one row per code execution in a session (status, error, data access log, outputs)
outputs      outputs emitted by sessions; released only after a coverage PASS
completions  ExecutionManifest + coverage result + final status of a completed session
bundle_bindings   (conversation reuse) an approved need of a later request bound to an earlier, immutable bundle with
                  the same data contract; the bundle's manifest and checksum are never changed
session_epochs    (conversation reuse) each request a session served: epoch, request, approved need, first execution
data_need_drafts  (Research Plan feasibility) a DataNeedSpec the validator approved before any plan was approved; it
                  is never extracted (the Governor only estimates it) and is kept seven days
research_runs     (Multi-Angle Research) one approved research_governance/v2 declaration: the plan, its research data
                  plan and the Research Governor's decision
research_groups   the bundle groups of a research run: the need promoted from each feasibility draft, its angles and its
                  terminal state
research_findings one backend-authored finding per approved angle (research_findings/v2)

Analysis processes never reach this database. Hidden model reasoning is never stored.

Schema versions (PRAGMA user_version): 0 is the original layout (CREATE TABLE IF NOT EXISTS); 1 adds the conversation
reuse columns and tables of the implementation plan 2026-09-27 (S1/S2); 2 adds data_need_drafts; 3 adds executions.modules
(the modules each execution's code imports, EXTRACTION_AND_AUDIT_PLAN.md item C); 4 adds research_runs, research_groups and
research_findings (MULTI_ANGLE_RESEARCH.md). Upgrades only add nullable or defaulted columns
and new tables, so code without them still reads and writes the database.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

JSON_FIELDS = {"submitted", "result", "approved", "governance", "research", "manifest", "error", "access", "outputs",
               "meta", "execution_manifest", "coverage", "final_status", "usage", "columns", "modules", "decision",
               "data_plan", "angle_ids", "finding"}

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


SCHEMA_VERSION = 4
DRAFT_RETENTION_DAYS = 7
# version -> (table, column, declaration) additions and statements; applied in order, each column only when missing
UPGRADES: dict[int, tuple[list[tuple[str, str, str]], list[str]]] = {
    1: ([("data_needs", "conversation_key", "TEXT"), ("data_needs", "contract_sha256", "TEXT"),
         ("bundles", "conversation_key", "TEXT"),
         ("sessions", "origin_request_id", "TEXT"), ("sessions", "conversation_key", "TEXT"),
         ("sessions", "need_id", "TEXT"), ("sessions", "epoch", "INTEGER NOT NULL DEFAULT 1"),
         ("sessions", "epoch_start_seq", "INTEGER NOT NULL DEFAULT 0"),
         ("executions", "epoch", "INTEGER NOT NULL DEFAULT 1"), ("executions", "request_id", "TEXT"),
         ("completions", "epoch", "INTEGER NOT NULL DEFAULT 1"), ("completions", "parent_completion_id", "TEXT")],
        ["""CREATE TABLE IF NOT EXISTS bundle_bindings (
               need_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, bundle_id TEXT NOT NULL,
               source_need_id TEXT NOT NULL, source_request_id TEXT NOT NULL, conversation_key TEXT NOT NULL,
               created_at TEXT NOT NULL)""",
         "CREATE INDEX IF NOT EXISTS bundle_bindings_request ON bundle_bindings (request_id, bundle_id)",
         """CREATE TABLE IF NOT EXISTS session_epochs (
               session_id TEXT NOT NULL, epoch INTEGER NOT NULL, request_id TEXT NOT NULL, need_id TEXT,
               start_seq INTEGER NOT NULL, attached_at TEXT NOT NULL, PRIMARY KEY (session_id, epoch))""",
         "CREATE INDEX IF NOT EXISTS session_epochs_request ON session_epochs (request_id)",
         "CREATE INDEX IF NOT EXISTS bundles_conversation ON bundles (conversation_key)",
         "CREATE INDEX IF NOT EXISTS sessions_conversation ON sessions (conversation_key)"]),
    2: ([], ["""CREATE TABLE IF NOT EXISTS data_need_drafts (
                   draft_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, submitted TEXT NOT NULL, approved TEXT NOT NULL,
                   result TEXT NOT NULL, contract_sha256 TEXT, created_at TEXT NOT NULL)""",
             "CREATE INDEX IF NOT EXISTS data_need_drafts_created ON data_need_drafts (created_at)"]),
    3: ([("executions", "modules", "TEXT")], []),
    4: ([], ["""CREATE TABLE IF NOT EXISTS research_runs (
                   research_run_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, origin_request_id TEXT NOT NULL,
                   plan_id TEXT NOT NULL, plan_sha256 TEXT NOT NULL, data_plan_sha256 TEXT NOT NULL,
                   governance TEXT NOT NULL, data_plan TEXT NOT NULL, decision TEXT NOT NULL, status TEXT NOT NULL,
                   created_at TEXT NOT NULL)""",
             "CREATE INDEX IF NOT EXISTS research_runs_request ON research_runs (request_id)",
             """CREATE TABLE IF NOT EXISTS research_groups (
                   research_run_id TEXT NOT NULL, bundle_group_id TEXT NOT NULL, need_id TEXT, draft_id TEXT NOT NULL,
                   spec_sha256 TEXT NOT NULL, angle_ids TEXT NOT NULL, status TEXT NOT NULL, reason TEXT,
                   session_id TEXT, completion_id TEXT, updated_at TEXT NOT NULL,
                   PRIMARY KEY (research_run_id, bundle_group_id))""",
             "CREATE INDEX IF NOT EXISTS research_groups_need ON research_groups (need_id)",
             """CREATE TABLE IF NOT EXISTS research_findings (
                   research_run_id TEXT NOT NULL, angle_id TEXT NOT NULL, bundle_group_id TEXT NOT NULL,
                   session_id TEXT, completion_id TEXT, status TEXT NOT NULL, validation_level TEXT,
                   finding TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY (research_run_id, angle_id))"""]),
}


class DataNeedStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(SCHEMA)
        self.schema_version = self._upgrade()

    def _upgrade(self) -> int:
        """Bring an existing database to SCHEMA_VERSION in one transaction per version; never drops or rewrites."""
        with self._lock:
            version = int(self._db.execute("PRAGMA user_version").fetchone()[0])
            for target in sorted(v for v in UPGRADES if v > version):
                columns, statements = UPGRADES[target]
                self._db.execute("BEGIN IMMEDIATE")
                try:
                    for table, column, declaration in columns:
                        present = {row[1] for row in self._db.execute(f"PRAGMA table_info({table})")}
                        if column not in present:
                            self._db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
                    for statement in statements:
                        self._db.execute(statement)
                    self._db.execute(f"PRAGMA user_version = {target}")
                    self._db.execute("COMMIT")
                except Exception:
                    self._db.execute("ROLLBACK")
                    raise
                version = target
            return version

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

    # feasibility drafts
    def insert_draft(self, record: dict[str, Any], purge_before: str) -> None:
        self._insert("data_need_drafts", record)
        with self._lock:
            self._db.execute("DELETE FROM data_need_drafts WHERE created_at < ?", (purge_before,))

    def get_draft(self, draft_id: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM data_need_drafts WHERE draft_id = ?", (draft_id,))

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

    def set_bundle_conversation(self, bundle_id: str, conversation_key: str) -> None:
        self._update("bundles", "bundle_id", bundle_id, {"conversation_key": conversation_key})

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
        return self._all("SELECT * FROM sessions WHERE status IN ('ACTIVE', 'BUSY', 'WARM_IDLE') ORDER BY created_at",
                         ())

    def warm_sessions(self, conversation_key: str | None = None) -> list[dict[str, Any]]:
        """WARM_IDLE sessions, least recently used first (all of them, or those of one conversation)."""
        if conversation_key is None:
            return self._all("SELECT * FROM sessions WHERE status = 'WARM_IDLE' ORDER BY last_active_at", ())
        return self._all("SELECT * FROM sessions WHERE status = 'WARM_IDLE' AND conversation_key = ? "
                         "ORDER BY last_active_at", (conversation_key,))

    def close_orphans(self, now: str) -> int:
        with self._lock:
            cursor = self._db.execute("UPDATE sessions SET status = 'CLOSED', closed_at = ?, "
                                      "close_reason = 'SANDBOX_RESTARTED' "
                                      "WHERE status IN ('ACTIVE', 'BUSY', 'WARM_IDLE')", (now,))
            return cursor.rowcount

    # conversation reuse (schema version 1)
    def insert_epoch(self, record: dict[str, Any]) -> None:
        self._insert("session_epochs", record)

    def epochs_for(self, session_id: str) -> list[dict[str, Any]]:
        return self._all("SELECT * FROM session_epochs WHERE session_id = ? ORDER BY epoch", (session_id,))

    def insert_binding(self, record: dict[str, Any]) -> None:
        self._insert("bundle_bindings", record)

    def get_binding(self, need_id: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM bundle_bindings WHERE need_id = ?", (need_id,))

    def binding_for(self, request_id: str, bundle_id: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM bundle_bindings WHERE request_id = ? AND bundle_id = ? ORDER BY created_at "
                         "DESC LIMIT 1", (request_id, bundle_id))

    def conversation_bundles(self, conversation_key: str) -> list[dict[str, Any]]:
        """READY bundles of one conversation with their need's data contract hash, newest first."""
        return self._all("SELECT b.*, n.contract_sha256 AS contract_sha256, n.mode AS mode FROM bundles b "
                         "JOIN data_needs n ON n.need_id = b.need_id "
                         "WHERE b.conversation_key = ? AND b.status = 'READY' ORDER BY b.created_at DESC",
                         (conversation_key,))

    def conversation_sessions(self, conversation_key: str) -> list[dict[str, Any]]:
        return self._all("SELECT * FROM sessions WHERE conversation_key = ? ORDER BY created_at DESC",
                         (conversation_key,))

    def released_outputs(self, conversation_key: str, limit: int) -> list[dict[str, Any]]:
        """Released outputs of the conversation's sessions, newest first."""
        return self._all("SELECT o.* FROM outputs o JOIN sessions s ON s.session_id = o.session_id "
                         "WHERE s.conversation_key = ? AND o.released = 1 ORDER BY o.created_at DESC LIMIT ?",
                         (conversation_key, limit))

    def completion_for_epoch(self, session_id: str, epoch: int) -> dict[str, Any] | None:
        return self._one("SELECT * FROM completions WHERE session_id = ? AND epoch = ? ORDER BY created_at DESC "
                         "LIMIT 1", (session_id, epoch))

    def passed_completions(self, session_id: str) -> list[dict[str, Any]]:
        return self._all("SELECT * FROM completions WHERE session_id = ? AND coverage_status = 'PASS' "
                         "ORDER BY epoch, created_at", (session_id,))

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

    # multi-angle research (schema version 4)
    def insert_research_run(self, run: dict[str, Any], groups: list[dict[str, Any]]) -> None:
        """The run and its groups in one transaction."""
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                for table, record in [("research_runs", run)] + [("research_groups", g) for g in groups]:
                    data = self._encode(record)
                    self._db.execute(f"INSERT INTO {table} ({', '.join(data)}) VALUES "
                                     f"({', '.join('?' * len(data))})", tuple(data.values()))
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise

    def get_research_run(self, research_run_id: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM research_runs WHERE research_run_id = ?", (research_run_id,))

    def research_runs_for(self, request_id: str) -> list[dict[str, Any]]:
        return self._all("SELECT * FROM research_runs WHERE request_id = ? ORDER BY created_at", (request_id,))

    def research_groups(self, research_run_id: str) -> list[dict[str, Any]]:
        return self._all("SELECT * FROM research_groups WHERE research_run_id = ? ORDER BY bundle_group_id",
                         (research_run_id,))

    def research_group_for_need(self, need_id: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM research_groups WHERE need_id = ?", (need_id,))

    def update_research_group(self, research_run_id: str, bundle_group_id: str, **fields: Any) -> None:
        data = self._encode(fields)
        with self._lock:
            self._db.execute(f"UPDATE research_groups SET {', '.join(f'{k} = ?' for k in data)} "
                             "WHERE research_run_id = ? AND bundle_group_id = ?",
                             (*data.values(), research_run_id, bundle_group_id))

    def upsert_research_finding(self, record: dict[str, Any]) -> None:
        data = self._encode(record)
        with self._lock:
            self._db.execute(f"INSERT OR REPLACE INTO research_findings ({', '.join(data)}) VALUES "
                             f"({', '.join('?' * len(data))})", tuple(data.values()))

    def research_findings(self, research_run_id: str) -> list[dict[str, Any]]:
        return self._all("SELECT * FROM research_findings WHERE research_run_id = ? ORDER BY angle_id",
                         (research_run_id,))

    def close(self) -> None:
        with self._lock:
            self._db.close()
