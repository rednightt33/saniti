"""IP2 solution 2 (SQL_GOVERNOR_AUDIT_STORE_ENABLED): archive each extracted dataset to market-audit-store.

Durable outbox in the Governor's existing persistence, the dataset bucket (its PostgreSQL role stays read-only):
- when a dataset is written, a marker audit-outbox/<dataset_id>.json (dataset id, request id) is written next to it;
- a background thread drains the markers: it streams data.parquet (RAW_INPUT_PARQUET) and manifest.json
  (EXTRACTION_MANIFEST) of the dataset to single-object upload URLs of the audit store, links both to the request's
  run (label = dataset id), records a bounded dataset.archived event with checksum and lineage, and deletes the
  marker;
- every step is idempotent (request id, content address, link key, event key), so a retry after a crash repeats
  nothing; a failure keeps the marker with backoff (FAILED_RETRYABLE), and after SQL_GOVERNOR_AUDIT_MAX_ATTEMPTS
  (or when the dataset already expired) the marker moves to audit-outbox-failed/ (INCOMPLETE) and the run records
  why, so the missing archive is visible, never silent.
The audit store never gets access to the dataset bucket; the Governor pushes the bytes it already holds."""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any

from .audit_client import AuditClient, AuditRejected, AuditUnavailable
from .store import ObjectStore

logger = logging.getLogger("market_sql_governor")
PREFIX = "audit-outbox/"
FAILED_PREFIX = "audit-outbox-failed/"
MARKER = re.compile(r"^audit-outbox/(ds_[0-9a-f]{24})\.json$")
LINEAGE_KEYS = ("dataset_id", "checksum_sha256", "byte_count", "row_count", "column_count", "source_tables",
                "query_id", "query_hash", "request_sha256", "completeness_status", "actual_date_range",
                "entities_present_count", "created_at", "expires_at", "governor_version")


def _log(event: str, **fields: Any) -> None:
    logger.info(json.dumps({"event": event, **fields}, default=str, separators=(",", ":")))


def enqueue(store: ObjectStore, dataset_id: str, request_id: str) -> None:
    """Called right after a dataset is stored; a failure is logged and never fails the extraction."""
    body = json.dumps({"dataset_id": dataset_id, "request_id": request_id,
                       "enqueued_at": datetime.now(timezone.utc).isoformat()}, sort_keys=True).encode()
    try:
        import hashlib

        store.put_immutable(f"{PREFIX}{dataset_id}.json", body, "application/json", hashlib.sha256(body).hexdigest())
    except Exception as exc:  # noqa: BLE001 - audit is best effort while AUDIT_STORE_REQUIRED is false
        _log("sql_governor_audit_enqueue_failed", dataset_id=dataset_id, request_id=request_id,
             error=type(exc).__name__)


class DatasetArchiver(threading.Thread):
    def __init__(self, store: ObjectStore, client: AuditClient, *, interval_seconds: int = 30,
                 max_attempts: int = 12) -> None:
        super().__init__(name="audit-archiver", daemon=True)
        self.store, self.client = store, client
        self.interval_seconds, self.max_attempts = interval_seconds, max_attempts
        self.attempts: dict[str, int] = {}
        self.not_before: dict[str, float] = {}
        self.stopped = threading.Event()

    def run(self) -> None:
        while not self.stopped.is_set():
            self.drain()
            self.stopped.wait(self.interval_seconds)

    def stop(self) -> None:
        self.stopped.set()

    def drain(self) -> dict[str, int]:
        counts = {"archived": 0, "retry": 0, "incomplete": 0}
        try:
            keys = [key for key, _ in self.store.list_keys(PREFIX)]
        except Exception as exc:  # noqa: BLE001 - storage unreachable: next interval
            _log("sql_governor_audit_drain_failed", error=type(exc).__name__)
            return counts
        for key in sorted(keys):
            match = MARKER.fullmatch(key)
            if match is None or self.not_before.get(key, 0) > time.monotonic():
                continue
            counts[self.archive_one(key, match.group(1))] += 1
        return counts

    def archive_one(self, key: str, dataset_id: str) -> str:
        marker: dict[str, Any] = {}
        try:
            marker = json.loads(self.store.get(key))
            request_id = marker["request_id"]
            parquet = self.store.get_optional(f"datasets/{dataset_id}/data.parquet")
            manifest_raw = self.store.get_optional(f"datasets/{dataset_id}/manifest.json")
            run_id = self.client.register_run(request_id)
            if parquet is None or manifest_raw is None:
                return self._give_up(key, marker, run_id, "DATASET_EXPIRED_BEFORE_ARCHIVE")
            manifest = json.loads(manifest_raw)
            data_id = self.client.store_artifact(parquet, "application/vnd.apache.parquet")
            manifest_id = self.client.store_artifact(manifest_raw, "application/json")
            self.client.link(run_id, [{"artifact_id": data_id, "role": "RAW_INPUT_PARQUET", "label": dataset_id},
                                      {"artifact_id": manifest_id, "role": "EXTRACTION_MANIFEST",
                                       "label": dataset_id}])
            lineage = {k: manifest.get(k) for k in LINEAGE_KEYS}
            lineage["lineage"] = _bounded(manifest.get("lineage"))
            self.client.append_events(run_id, [{
                "idempotency_key": f"dataset:{dataset_id}", "event_type": "dataset.archived",
                "occurred_at": datetime.now(timezone.utc).isoformat(), "payload": lineage}])
            self.client.expect(run_id, {"dataset_ids": [dataset_id]})
            self.store.delete(key)
            self.attempts.pop(key, None)
            _log("sql_governor_audit_archived", dataset_id=dataset_id, request_id=request_id,
                 bytes=len(parquet), status="COMPLETE")
            return "archived"
        except (AuditUnavailable, OSError, ValueError, KeyError, TimeoutError) as exc:
            return self._retry(key, marker, exc)
        except AuditRejected as exc:
            return self._give_up(key, marker, None, f"REJECTED: {exc}"[:300])
        except Exception as exc:  # noqa: BLE001 - e.g. a storage client error; retried with backoff
            return self._retry(key, marker, exc)

    def _retry(self, key: str, marker: dict[str, Any], exc: Exception) -> str:
        attempts = self.attempts.get(key, 0) + 1
        self.attempts[key] = attempts
        if attempts >= self.max_attempts:
            return self._give_up(key, marker, None, f"{type(exc).__name__} after {attempts} attempts")
        self.not_before[key] = time.monotonic() + min(3600, 30 * 2 ** attempts)
        _log("sql_governor_audit_archive_failed", marker=key, attempts=attempts, status="FAILED_RETRYABLE",
             error=type(exc).__name__)
        return "retry"

    def _give_up(self, key: str, marker: dict[str, Any], run_id: str | None, reason: str) -> str:
        """INCOMPLETE: the marker moves to audit-outbox-failed/ and, when reachable, the run records why."""
        dataset_id = str(marker.get("dataset_id") or key)
        try:
            if run_id is None and marker.get("request_id"):
                run_id = self.client.register_run(marker["request_id"])
            if run_id is not None:
                self.client.append_events(run_id, [{
                    "idempotency_key": f"dataset:{dataset_id}:incomplete", "event_type": "dataset.archive_incomplete",
                    "occurred_at": datetime.now(timezone.utc).isoformat(),
                    "payload": {"dataset_id": dataset_id, "reason": reason}}])
                self.client.expect(run_id, {"dataset_ids": [dataset_id]})  # the run cannot report COMPLETE
        except Exception:  # noqa: BLE001 - the failed marker below still records it
            pass
        try:
            body = json.dumps({**marker, "status": "INCOMPLETE", "reason": reason}, sort_keys=True).encode()
            import hashlib

            self.store.put_immutable(key.replace(PREFIX, FAILED_PREFIX, 1), body, "application/json",
                                     hashlib.sha256(body).hexdigest())
            self.store.delete(key)
        except Exception:  # noqa: BLE001 - keep the marker; it will be retried
            pass
        self.attempts.pop(key, None)
        _log("sql_governor_audit_archive_incomplete", marker=key, status="INCOMPLETE", reason=reason)
        return "incomplete"


def _bounded(value: Any, limit: int = 8000) -> Any:
    text = json.dumps(value, default=str, separators=(",", ":"))
    return value if len(text) <= limit else {"truncated": True, "chars": len(text)}
