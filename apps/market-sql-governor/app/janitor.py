"""Deletes expired dataset snapshots. Railway buckets do not support lifecycle rules yet, so the
Governor itself removes each dataset once the expires_at in its manifest has passed.

Only keys shaped datasets/ds_<24 hex>/(data.parquet|manifest.json) are ever deleted. A dataset
whose manifest is missing or unreadable (for example an interrupted write) expires
SQL_DATASET_RETENTION_HOURS after its oldest object. The data file is deleted before the
manifest, so an interrupted cleanup leaves a manifest that the next pass removes.
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


def cleanup_expired(store: ObjectStore, *, now: datetime, retention_hours: int) -> dict[str, Any]:
    groups: dict[str, dict[str, datetime]] = {}
    unknown = 0
    for key, modified in store.list_keys("datasets/"):
        match = KEY.fullmatch(key)
        if match is None:
            unknown += 1
            continue
        groups.setdefault(match.group(1), {})[match.group(2)] = modified
    deleted: list[str] = []
    errors = 0
    for dataset_id, files in sorted(groups.items()):
        expires: datetime | None = None
        if "manifest.json" in files:
            try:
                raw = json.loads(store.get(f"datasets/{dataset_id}/manifest.json"))
                expires = datetime.fromisoformat(raw["expires_at"])
            except (ValueError, KeyError, TypeError):
                expires = None
        if expires is None:
            expires = min(files.values()) + timedelta(hours=retention_hours)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires > now:
            continue
        try:
            for name in ("data.parquet", "manifest.json"):
                if name in files:
                    store.delete(f"datasets/{dataset_id}/{name}")
            deleted.append(dataset_id)
        except Exception:  # keep going; the next pass retries
            errors += 1
    return {"datasets_seen": len(groups), "datasets_deleted": len(deleted), "deleted_ids": deleted[:50],
            "unknown_keys": unknown, "errors": errors}


class DatasetJanitor(threading.Thread):
    def __init__(self, store: ObjectStore, *, interval_seconds: int, retention_hours: int) -> None:
        super().__init__(name="dataset-janitor", daemon=True)
        self.store = store
        self.interval_seconds = interval_seconds
        self.retention_hours = retention_hours
        self.stopped = threading.Event()

    def run_once(self) -> dict[str, Any]:
        try:
            summary = cleanup_expired(self.store, now=datetime.now(timezone.utc),
                                      retention_hours=self.retention_hours)
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
