"""Expired dataset deletion (Railway buckets have no lifecycle rules yet)."""
from __future__ import annotations

import io
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.config import Settings
from app.janitor import DatasetJanitor, cleanup_expired
from app.main import create_app
from app.store import LocalStore, S3Store
from conftest import base_env

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
EXPIRED, LIVE, ORPHAN, BROKEN = ("ds_" + c * 24 for c in "abcd")


def manifest(expires: datetime) -> bytes:
    return json.dumps({"expires_at": expires.isoformat()}).encode()


def seed_local(store: LocalStore) -> None:
    store.put_immutable(f"datasets/{EXPIRED}/data.parquet", b"x", "", "c")
    store.put_immutable(f"datasets/{EXPIRED}/manifest.json", manifest(NOW - timedelta(minutes=1)), "", "c")
    store.put_immutable(f"datasets/{LIVE}/data.parquet", b"y", "", "c")
    store.put_immutable(f"datasets/{LIVE}/manifest.json", manifest(NOW + timedelta(days=6)), "", "c")
    store.put_immutable(f"datasets/{ORPHAN}/data.parquet", b"z", "", "c")           # manifest never written
    store.put_immutable(f"datasets/{BROKEN}/manifest.json", b"not json", "", "c")    # unreadable manifest
    store.put_immutable("datasets/not-a-dataset/secret.txt", b"keep", "", "c")
    store.put_immutable("other/keep.parquet", b"keep", "", "c")


def age(root, relative: str, days: int) -> None:
    stamp = (NOW - timedelta(days=days)).timestamp()
    os.utime(root / relative, (stamp, stamp))


def test_only_expired_datasets_are_deleted(tmp_path) -> None:
    store = LocalStore(str(tmp_path))
    seed_local(store)
    age(tmp_path, f"datasets/{ORPHAN}/data.parquet", days=8)   # older than 7-day retention
    age(tmp_path, f"datasets/{BROKEN}/manifest.json", days=2)  # younger than retention
    summary = cleanup_expired(store, now=NOW, retention_hours=168)
    assert summary["datasets_deleted"] == 2 and sorted(summary["deleted_ids"]) == sorted([EXPIRED, ORPHAN])
    assert summary["unknown_keys"] == 1 and summary["errors"] == 0
    assert not (tmp_path / "datasets" / EXPIRED / "data.parquet").exists()
    assert not (tmp_path / "datasets" / EXPIRED / "manifest.json").exists()
    assert not (tmp_path / "datasets" / ORPHAN / "data.parquet").exists()
    for kept in (f"datasets/{LIVE}/data.parquet", f"datasets/{LIVE}/manifest.json",
                 f"datasets/{BROKEN}/manifest.json", "datasets/not-a-dataset/secret.txt", "other/keep.parquet"):
        assert (tmp_path / kept).exists(), kept


def test_second_pass_is_idempotent(tmp_path) -> None:
    store = LocalStore(str(tmp_path))
    seed_local(store)
    cleanup_expired(store, now=NOW, retention_hours=168)
    assert cleanup_expired(store, now=NOW, retention_hours=168)["datasets_deleted"] == 0


class FakeS3:
    def __init__(self, objects: dict[str, tuple[bytes, datetime]]) -> None:
        self.objects = dict(objects)
        self.deleted: list[str] = []

    def get_paginator(self, name: str):
        assert name == "list_objects_v2"
        outer = self

        class Paginator:
            def paginate(self, Bucket: str, Prefix: str):
                keys = sorted(k for k in outer.objects if k.startswith(Prefix))
                for start in range(0, len(keys), 2):  # small pages to exercise pagination
                    yield {"Contents": [{"Key": k, "LastModified": outer.objects[k][1]} for k in keys[start:start + 2]]}
        return Paginator()

    def get_object(self, Bucket: str, Key: str):
        return {"Body": io.BytesIO(self.objects[Key][0])}

    def delete_object(self, Bucket: str, Key: str) -> None:
        self.deleted.append(Key)
        self.objects.pop(Key)


def test_s3_store_deletes_only_expired_objects_across_pages() -> None:
    store = S3Store.__new__(S3Store)
    store.bucket = "b"
    store.client = FakeS3({
        f"datasets/{EXPIRED}/data.parquet": (b"x", NOW), f"datasets/{EXPIRED}/manifest.json": (manifest(NOW - timedelta(seconds=1)), NOW),
        f"datasets/{LIVE}/data.parquet": (b"y", NOW), f"datasets/{LIVE}/manifest.json": (manifest(NOW + timedelta(hours=1)), NOW),
        "datasets/other.txt": (b"k", NOW - timedelta(days=30)),
    })
    summary = cleanup_expired(store, now=NOW, retention_hours=168)
    assert summary["deleted_ids"] == [EXPIRED]
    assert store.client.deleted == [f"datasets/{EXPIRED}/data.parquet", f"datasets/{EXPIRED}/manifest.json"]


def test_janitor_runs_with_the_app_and_logs_a_summary(tmp_path) -> None:
    store = LocalStore(str(tmp_path))
    seed_local(store)
    past = "ds_" + "e" * 24  # expired relative to the real clock
    store.put_immutable(f"datasets/{past}/data.parquet", b"x", "", "c")
    store.put_immutable(f"datasets/{past}/manifest.json",
                        manifest(datetime.now(timezone.utc) - timedelta(minutes=1)), "", "c")
    records: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())
    logger = logging.getLogger("market_sql_governor")
    handler, previous_level = Capture(), logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        settings = Settings.from_env(base_env(SQL_DATASET_LOCAL_DIR=str(tmp_path)))
        with TestClient(create_app(settings)) as client:
            assert client.get("/health").status_code == 200
            for _ in range(50):
                if any("sql_governor_dataset_cleanup" in r for r in records):
                    break
                time.sleep(0.05)
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
    event = json.loads(next(r for r in records if "sql_governor_dataset_cleanup" in r))
    assert event["datasets_seen"] == 5 and event["errors"] == 0 and past in event["deleted_ids"]
    assert not (tmp_path / "datasets" / past / "data.parquet").exists()
    assert (tmp_path / "datasets" / LIVE / "data.parquet").exists()


def test_janitor_survives_storage_errors() -> None:
    class Broken:
        def list_keys(self, prefix):
            raise ConnectionError("unreachable")
    assert DatasetJanitor(Broken(), interval_seconds=1, retention_hours=168).run_once() == {"error": "ConnectionError"}
