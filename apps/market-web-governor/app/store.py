from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


class IdempotencyConflict(RuntimeError):
    pass


class StoreUnavailable(RuntimeError):
    pass


class SqliteStore:
    def __init__(self, path: str, stale_running_seconds: int = 1800):
        self.path = path
        self.stale_running_seconds = stale_running_seconds
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS web_need (
                    web_need_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL UNIQUE,
                    request_fingerprint TEXT NOT NULL,
                    conversation_id TEXT,
                    status TEXT NOT NULL,
                    spec_json TEXT NOT NULL,
                    plan_json TEXT NOT NULL,
                    response_json TEXT,
                    error_code TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS provider_call (
                    provider_call_id TEXT PRIMARY KEY,
                    web_need_id TEXT NOT NULL REFERENCES web_need(web_need_id) ON DELETE CASCADE,
                    criterion_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    adapter_version TEXT NOT NULL,
                    model TEXT,
                    provider_response_id TEXT,
                    status TEXT NOT NULL,
                    usage_json TEXT NOT NULL,
                    error_code TEXT,
                    response_sha256 TEXT,
                    started_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS evidence (
                    evidence_id TEXT PRIMARY KEY,
                    citation_id TEXT NOT NULL UNIQUE,
                    web_need_id TEXT NOT NULL REFERENCES web_need(web_need_id) ON DELETE CASCADE,
                    provider_call_id TEXT NOT NULL REFERENCES provider_call(provider_call_id) ON DELETE CASCADE,
                    canonical_url TEXT NOT NULL,
                    title TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    published_at TEXT,
                    retrieved_at TEXT NOT NULL,
                    source_tier TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    excerpt TEXT,
                    excerpt_kind TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    UNIQUE(web_need_id, canonical_url, content_sha256)
                );
                CREATE TABLE IF NOT EXISTS criterion_evidence (
                    web_need_id TEXT NOT NULL REFERENCES web_need(web_need_id) ON DELETE CASCADE,
                    criterion_id TEXT NOT NULL,
                    evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id) ON DELETE CASCADE,
                    PRIMARY KEY(web_need_id, criterion_id, evidence_id)
                );
                CREATE INDEX IF NOT EXISTS evidence_need_idx ON evidence(web_need_id, retrieved_at);
                CREATE TABLE IF NOT EXISTS fetched_document (
                    document_id TEXT PRIMARY KEY,
                    web_need_id TEXT NOT NULL REFERENCES web_need(web_need_id) ON DELETE CASCADE,
                    requested_url TEXT NOT NULL,
                    final_url TEXT NOT NULL,
                    http_status INTEGER NOT NULL,
                    media_type TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    byte_length INTEGER NOT NULL,
                    raw_sha256 TEXT NOT NULL,
                    text_sha256 TEXT NOT NULL,
                    text TEXT NOT NULL,
                    truncated INTEGER NOT NULL,
                    page_count INTEGER,
                    pages_read INTEGER,
                    title TEXT NOT NULL,
                    redirects_json TEXT NOT NULL,
                    retrieved_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS fetched_document_need_idx ON fetched_document(web_need_id);
                """
            )
            # Columns added after the first release; ALTER keeps existing evidence rows.
            existing = {row["name"] for row in connection.execute("PRAGMA table_info(evidence)")}
            for column, kind in (
                ("document_id", "TEXT"), ("quote_start", "INTEGER"), ("quote_end", "INTEGER"),
                ("published_precision", "TEXT"), ("published_at_source", "TEXT"), ("temporal_status", "TEXT"),
                ("lead_time_days", "INTEGER"), ("source_verified", "INTEGER"), ("source_note", "TEXT"),
                ("copy_of", "TEXT"), ("classification_json", "TEXT"),
            ):
                if column not in existing:
                    connection.execute(f"ALTER TABLE evidence ADD COLUMN {column} {kind}")

    def ping(self) -> None:
        try:
            with self._connect() as connection:
                connection.execute("SELECT 1").fetchone()
        except sqlite3.Error as exc:
            raise StoreUnavailable("evidence store unavailable") from exc

    def create_need(self, row: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    "SELECT * FROM web_need WHERE request_id = ?", (row["request_id"],)
                ).fetchone()
                if existing:
                    connection.execute("ROLLBACK")
                    parsed = self._decode_need(existing)
                    if parsed["request_fingerprint"] != row["request_fingerprint"]:
                        raise IdempotencyConflict("request_id was already used with a different request")
                    return parsed, False
                connection.execute(
                    """INSERT INTO web_need
                       (web_need_id, request_id, request_fingerprint, conversation_id, status, spec_json,
                        plan_json, response_json, error_code, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)""",
                    (
                        row["web_need_id"], row["request_id"], row["request_fingerprint"],
                        row.get("conversation_id"), row["status"], json.dumps(row["spec"], separators=(",", ":")),
                        json.dumps(row["plan"], separators=(",", ":")), row["created_at"], row["updated_at"],
                    ),
                )
                connection.execute("COMMIT")
                return row, True
        except sqlite3.Error as exc:
            raise StoreUnavailable("could not create web need") from exc

    def get_need(self, web_need_id: str) -> dict[str, Any] | None:
        try:
            with self._connect() as connection:
                row = connection.execute("SELECT * FROM web_need WHERE web_need_id = ?", (web_need_id,)).fetchone()
            return self._decode_need(row) if row else None
        except sqlite3.Error as exc:
            raise StoreUnavailable("could not read web need") from exc

    def begin_execution(self, web_need_id: str) -> dict[str, Any]:
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute("SELECT * FROM web_need WHERE web_need_id = ?", (web_need_id,)).fetchone()
                if not row:
                    connection.execute("ROLLBACK")
                    raise KeyError(web_need_id)
                need = self._decode_need(row)
                if need["status"] in {"EVIDENCE_READY", "PARTIAL", "FAILED", "BLOCKED"}:
                    connection.execute("ROLLBACK")
                    return need
                if need["status"] == "RUNNING" and not _stale(need.get("updated_at"), self.stale_running_seconds):
                    connection.execute("ROLLBACK")
                    raise RuntimeError("WEB_NEED_ALREADY_RUNNING")
                # A RUNNING need older than the stale limit belongs to a process that died (e.g. a redeploy);
                # it may be executed again.
                connection.execute(
                    "UPDATE web_need SET status = 'RUNNING', updated_at = CURRENT_TIMESTAMP WHERE web_need_id = ?",
                    (web_need_id,),
                )
                connection.execute("COMMIT")
                need["status"] = "RUNNING"
                return need
        except sqlite3.Error as exc:
            raise StoreUnavailable("could not start web need") from exc

    def complete_execution(
        self,
        web_need_id: str,
        status: str,
        response: dict[str, Any],
        provider_calls: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
        criterion_links: list[tuple[str, str]],
        updated_at: str,
        error_code: str | None = None,
        documents: list[dict[str, Any]] | None = None,
    ) -> None:
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                for document in documents or []:
                    connection.execute(
                        """INSERT OR IGNORE INTO fetched_document
                           (document_id, web_need_id, requested_url, final_url, http_status, media_type, content_type,
                            byte_length, raw_sha256, text_sha256, text, truncated, page_count, pages_read, title,
                            redirects_json, retrieved_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            document["document_id"], web_need_id, document["requested_url"], document["final_url"],
                            document["http_status"], document["media_type"], document["content_type"],
                            document["byte_length"], document["raw_sha256"], document["text_sha256"], document["text"],
                            int(bool(document["truncated"])), document.get("page_count"), document.get("pages_read"),
                            document.get("title") or "", json.dumps(document.get("redirects") or []),
                            document["retrieved_at"],
                        ),
                    )
                for call in provider_calls:
                    connection.execute(
                        """INSERT OR REPLACE INTO provider_call
                           (provider_call_id, web_need_id, criterion_id, operation, provider, adapter_version,
                            model, provider_response_id, status, usage_json, error_code, response_sha256,
                            started_at, completed_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            call["provider_call_id"], web_need_id, call["criterion_id"], call["operation"],
                            call["provider"], call["adapter_version"], call.get("model"),
                            call.get("provider_response_id"), call["status"],
                            json.dumps(call.get("usage", {}), separators=(",", ":")), call.get("error_code"),
                            call.get("response_sha256"), call["started_at"], call["completed_at"],
                        ),
                    )
                for item in evidence:
                    connection.execute(
                        """INSERT OR IGNORE INTO evidence
                           (evidence_id, citation_id, web_need_id, provider_call_id, canonical_url, title, domain,
                            published_at, retrieved_at, source_tier, content_type, excerpt, excerpt_kind, content_sha256,
                            document_id, quote_start, quote_end, published_precision, published_at_source,
                            temporal_status, lead_time_days, source_verified, source_note, copy_of,
                            classification_json)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            item["evidence_id"], item["citation_id"], web_need_id, item["provider_call_id"],
                            item["canonical_url"], item["title"], item["domain"], item.get("published_at"),
                            item["retrieved_at"], item["source_tier"], item["content_type"], item.get("excerpt"),
                            item["excerpt_kind"], item["content_sha256"], item.get("document_id"),
                            item.get("quote_start"), item.get("quote_end"), item.get("published_precision"),
                            item.get("published_at_source"), item.get("temporal_status"), item.get("lead_time_days"),
                            None if item.get("source_verified") is None else int(bool(item["source_verified"])),
                            item.get("source_note"), item.get("copy_of"),
                            json.dumps(item["classification"]) if item.get("classification") else None,
                        ),
                    )
                for criterion_id, evidence_id in criterion_links:
                    connection.execute(
                        "INSERT OR IGNORE INTO criterion_evidence(web_need_id, criterion_id, evidence_id) VALUES (?, ?, ?)",
                        (web_need_id, criterion_id, evidence_id),
                    )
                connection.execute(
                    """UPDATE web_need SET status = ?, response_json = ?, error_code = ?, updated_at = ?
                       WHERE web_need_id = ?""",
                    (status, json.dumps(response, separators=(",", ":")), error_code, updated_at, web_need_id),
                )
                connection.execute("COMMIT")
        except sqlite3.Error as exc:
            raise StoreUnavailable("could not persist web evidence") from exc

    def get_evidence(self, evidence_id: str) -> dict[str, Any] | None:
        try:
            with self._connect() as connection:
                row = connection.execute("SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,)).fetchone()
            if not row:
                return None
            result = dict(row)
            raw = result.pop("classification_json", None)
            result["classification"] = json.loads(raw) if raw else None
            if result.get("source_verified") is not None:
                result["source_verified"] = bool(result["source_verified"])
            return result
        except sqlite3.Error as exc:
            raise StoreUnavailable("could not read evidence") from exc

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM fetched_document WHERE document_id = ?", (document_id,)
                ).fetchone()
        except sqlite3.Error as exc:
            raise StoreUnavailable("could not read document") from exc
        if not row:
            return None
        result = dict(row)
        result["truncated"] = bool(result["truncated"])
        result["redirects"] = json.loads(result.pop("redirects_json"))
        return result

    def cleanup(self, retention_hours: int) -> int:
        cutoff = (datetime.now(UTC) - timedelta(hours=retention_hours)).isoformat()
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    """DELETE FROM web_need
                       WHERE status IN ('EVIDENCE_READY', 'PARTIAL', 'FAILED', 'BLOCKED') AND created_at < ?""",
                    (cutoff,),
                )
                return max(cursor.rowcount, 0)
        except sqlite3.Error as exc:
            raise StoreUnavailable("could not clean expired web evidence") from exc

    @staticmethod
    def _decode_need(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["spec"] = json.loads(result.pop("spec_json"))
        result["plan"] = json.loads(result.pop("plan_json"))
        raw_response = result.pop("response_json")
        result["response"] = json.loads(raw_response) if raw_response else None
        return result


def _stale(updated_at: str | None, seconds: int) -> bool:
    if not updated_at:
        return True
    try:
        value = datetime.fromisoformat(updated_at.replace(" ", "T"))
    except ValueError:
        return True
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)  # SQLite CURRENT_TIMESTAMP is UTC
    return (datetime.now(UTC) - value).total_seconds() > seconds


class EvidenceJanitor:
    def __init__(self, store: SqliteStore, retention_hours: int, interval_seconds: int):
        self.store = store
        self.retention_hours = retention_hours
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self.interval_seconds <= 0:
            return
        self.store.cleanup(self.retention_hours)
        self._thread = threading.Thread(target=self._run, name="web-evidence-janitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                self.store.cleanup(self.retention_hours)
            except StoreUnavailable:
                time.sleep(min(5, self.interval_seconds))
