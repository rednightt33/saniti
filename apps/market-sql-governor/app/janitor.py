"""Deletes expired dataset snapshots. Railway buckets do not support lifecycle rules yet, so the
Governor itself removes each dataset once the expires_at in its manifest has passed.

Only keys shaped datasets/ds_<24 hex>/(data.parquet|manifest.json) are ever deleted. A dataset
whose manifest is missing or unreadable (for example an interrupted write) expires
SQL_DATASET_RETENTION_HOURS after its oldest object.

At expiry only data.parquet is deleted. A readable manifest.json stays as a tombstone for
SQL_DATASET_TOMBSTONE_RETENTION_HOURS more, so a later lookup can answer DATASET_EXPIRED rather
than DATASET_NOT_FOUND; then it is deleted too. An unreadable manifest cannot serve as a
tombstone and is deleted with the data.

A manifest is written once (put_immutable) and never changed, so the janitor keeps each readable manifest's
expires_at in memory and downloads only the manifests it has not read yet (ERRORS M215: every pass downloaded every
manifest and tombstone). The first pass after a restart reads them all once; an entry leaves the cache when its
manifest is deleted or no longer listed.
"""
from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from .store import ObjectStore

logger = logging.getLogger("market_sql_governor")
KEY = re.compile(r"^datasets/(ds_[0-9a-f]{24})/(data\.parquet|manifest\.json)$")


def cleanup_expired(store: ObjectStore, *, now: datetime, retention_hours: int,
                    tombstone_hours: int = 0, expires_cache: dict[str, datetime] | None = None) -> dict[str, Any]:
    groups: dict[str, dict[str, datetime]] = {}
    unknown = 0
    for key, modified in store.list_keys("datasets/"):
        match = KEY.fullmatch(key)
        if match is None:
            unknown += 1
            continue
        groups.setdefault(match.group(1), {})[match.group(2)] = modified
    deleted: list[str] = []
    tombstones_deleted = 0
    errors = 0
    fetched = 0
    cache: dict[str, datetime] = {} if expires_cache is None else expires_cache
    for dataset_id in [known for known in cache if "manifest.json" not in groups.get(known, {})]:
        del cache[dataset_id]
    for dataset_id, files in sorted(groups.items()):
        expires: datetime | None = None
        if "manifest.json" in files:
            expires = cache.get(dataset_id)
            if expires is None:
                fetched += 1
                try:
                    raw = json.loads(store.get(f"datasets/{dataset_id}/manifest.json"))
                    expires = datetime.fromisoformat(raw["expires_at"])
                    cache[dataset_id] = expires
                except (ValueError, KeyError, TypeError):
                    expires = None
        readable_manifest = expires is not None
        if expires is None:
            expires = min(files.values()) + timedelta(hours=retention_hours)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires > now:
            continue
        drop_manifest = "manifest.json" in files and (
            not readable_manifest or now >= expires + timedelta(hours=tombstone_hours))
        try:
            if "data.parquet" in files:
                store.delete(f"datasets/{dataset_id}/data.parquet")
                deleted.append(dataset_id)
            if drop_manifest:
                store.delete(f"datasets/{dataset_id}/manifest.json")
                cache.pop(dataset_id, None)
                tombstones_deleted += 1
        except Exception:  # keep going; the next pass retries
            errors += 1
    return {"datasets_seen": len(groups), "datasets_deleted": len(deleted), "deleted_ids": deleted[:50],
            "tombstones_deleted": tombstones_deleted, "unknown_keys": unknown, "errors": errors,
            "manifests_fetched": fetched}


class DatasetJanitor(threading.Thread):
    def __init__(self, store: ObjectStore, *, interval_seconds: int, retention_hours: int,
                 tombstone_hours: int = 0) -> None:
        super().__init__(name="dataset-janitor", daemon=True)
        self.store = store
        self.interval_seconds = interval_seconds
        self.retention_hours = retention_hours
        self.tombstone_hours = tombstone_hours
        self.expires_cache: dict[str, datetime] = {}
        self.stopped = threading.Event()

    def run_once(self) -> dict[str, Any]:
        try:
            summary = cleanup_expired(self.store, now=datetime.now(timezone.utc),
                                      retention_hours=self.retention_hours, tombstone_hours=self.tombstone_hours,
                                      expires_cache=self.expires_cache)
        except Exception as exc:  # storage unreachable: log and retry next interval
            summary = {"error": type(exc).__name__}
        logger.info(json.dumps({"event": "sql_governor_dataset_cleanup", **summary}, separators=(",", ":")))
        return summary

    def run(self) -> None:
        while not self.stopped.is_set():
            self.run_once()
            self.stopped.wait(self.interval_seconds)

    def stop(self) -> None:
        self.stopped.set()
