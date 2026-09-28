"""IP2 solution 2 in the Governor: the audit outbox in the dataset bucket and its archiver.

A fake market-audit-store (httpx.MockTransport) records every call. The Governor's own bucket is a LocalStore."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import pytest

from app.audit_archive import FAILED_PREFIX, PREFIX, DatasetArchiver, enqueue
from app.audit_client import AuditClient
from app.config import ConfigError, Settings
from app.store import LocalStore
from conftest import base_env

DATASET = "ds_" + "a" * 24


class FakeAuditStore:
    def __init__(self, *, down: bool = False, ready: bool = False, reject: bool = False) -> None:
        self.down, self.ready, self.reject = down, ready, reject
        self.calls: list[tuple[str, str, object]] = []
        self.uploads: dict[str, bytes] = {}
        self.pending: dict[str, str] = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("audit store down", request=request)
        body = json.loads(request.content) if request.method == "POST" and request.content else None
        self.calls.append((request.method, request.url.path, body))
        path = request.url.path
        if request.method == "PUT":
            self.uploads[path.rsplit("/", 1)[1]] = request.content
            return httpx.Response(200)
        assert request.headers["Authorization"] == "Bearer " + "g" * 40
        if path == "/v1/internal/runs":
            return httpx.Response(200, json={"run_id": "run_" + "1" * 32, "request_id": body["request_id"],
                                             "status": "OPEN"})
        if path == "/v1/internal/artifacts":
            artifact = "art_" + body["sha256"][:32]
            if self.ready:
                return httpx.Response(200, json={"artifact_id": artifact, "state": "READY", "deduplicated": True,
                                                 "upload": None})
            self.pending[artifact] = body["sha256"]
            return httpx.Response(200, json={"artifact_id": artifact, "state": "PENDING", "deduplicated": False,
                                             "upload": {"method": "PUT", "url": f"https://bucket.test/staging/{artifact}",
                                                        "headers": {"Content-Type": body["media_type"]},
                                                        "expires_at": "2026-09-28T12:00:00Z"}})
        if path.endswith("/verify"):
            artifact = path.split("/")[-2]
            data = self.uploads.get(artifact, b"")
            ok = not self.reject and hashlib.sha256(data).hexdigest() == self.pending[artifact]
            return httpx.Response(200, json={"artifact_id": artifact, "state": "READY" if ok else "REJECTED",
                                             "rejected_reason": None if ok else "CHECKSUM_MISMATCH"})
        return httpx.Response(200, json={"run_id": "run_" + "1" * 32, "appended": [], "linked": 1,
                                          "duplicates": 0})

    def posted(self, suffix: str) -> list:
        return [body for method, path, body in self.calls if method == "POST" and path.endswith(suffix)]


def dataset(store: LocalStore) -> tuple[bytes, dict]:
    parquet = b"PAR1" + b"x" * 100
    manifest = {"dataset_id": DATASET, "checksum_sha256": hashlib.sha256(parquet).hexdigest(), "byte_count": 104,
                "row_count": 3, "source_tables": ["Price_Stock_Indonesia_IDX"], "query_hash": "q" * 64,
                "request_id": "req-1", "lineage": {"plan_id": "plan_x"}, "request_spec": {"secret": "no"}}
    store.put_immutable(f"datasets/{DATASET}/data.parquet", parquet, "application/vnd.apache.parquet", "x")
    store.put_immutable(f"datasets/{DATASET}/manifest.json", json.dumps(manifest).encode(), "application/json", "y")
    return parquet, manifest


def archiver(store: LocalStore, fake: FakeAuditStore, attempts: int = 3) -> DatasetArchiver:
    client = AuditClient("https://audit.test", "g" * 40, transport=httpx.MockTransport(fake))
    return DatasetArchiver(store, client, interval_seconds=1, max_attempts=attempts)


def markers(store: LocalStore, prefix: str = PREFIX) -> list[str]:
    return [key for key, _ in store.list_keys(prefix)]


def test_a_dataset_is_archived_linked_and_its_marker_removed(tmp_path: Path) -> None:
    store, fake = LocalStore(str(tmp_path)), FakeAuditStore()
    parquet, manifest = dataset(store)
    enqueue(store, DATASET, "req-1")
    assert markers(store) == [f"{PREFIX}{DATASET}.json"]
    assert archiver(store, fake).drain() == {"archived": 1, "retry": 0, "incomplete": 0}
    assert markers(store) == [] and parquet in fake.uploads.values()
    [links] = fake.posted("/artifacts")[-1:]
    assert {(link["role"], link["label"]) for link in links["links"]} == {("RAW_INPUT_PARQUET", DATASET),
                                                                           ("EXTRACTION_MANIFEST", DATASET)}
    [event] = fake.posted("/events")[0]["events"]
    assert event["event_type"] == "dataset.archived" and event["idempotency_key"] == f"dataset:{DATASET}"
    assert event["payload"]["checksum_sha256"] == manifest["checksum_sha256"]
    assert "request_spec" not in event["payload"]  # lineage summary only; the full manifest is the artifact
    assert fake.posted("/finalize")[0] == {"expected": {"dataset_ids": [DATASET]}}
    # the dataset itself is untouched: the Governor's retention stays as it was
    assert store.get_optional(f"datasets/{DATASET}/data.parquet") == parquet


def test_an_already_archived_object_is_not_uploaded_again(tmp_path: Path) -> None:
    store, fake = LocalStore(str(tmp_path)), FakeAuditStore(ready=True)
    dataset(store)
    enqueue(store, DATASET, "req-1")
    archiver(store, fake).drain()
    assert fake.uploads == {} and not [c for c in fake.calls if c[1].endswith("/verify")]


def test_an_outage_keeps_the_marker_and_gives_up_visibly(tmp_path: Path) -> None:
    store, fake = LocalStore(str(tmp_path)), FakeAuditStore(down=True)
    dataset(store)
    enqueue(store, DATASET, "req-1")
    worker = archiver(store, fake, attempts=2)
    assert worker.drain() == {"archived": 0, "retry": 1, "incomplete": 0}
    assert markers(store) == [f"{PREFIX}{DATASET}.json"]  # durable: nothing lost while the store is down
    worker.not_before.clear()
    assert worker.drain() == {"archived": 0, "retry": 0, "incomplete": 1}
    [failed] = markers(store, FAILED_PREFIX)
    assert json.loads(store.get(failed))["status"] == "INCOMPLETE" and markers(store) == []


def test_a_retry_after_recovery_is_idempotent(tmp_path: Path) -> None:
    store, fake = LocalStore(str(tmp_path)), FakeAuditStore(down=True)
    dataset(store)
    enqueue(store, DATASET, "req-1")
    worker = archiver(store, fake, attempts=5)
    worker.drain()
    fake.down = False
    worker.not_before.clear()
    assert worker.drain()["archived"] == 1
    keys = [e["idempotency_key"] for body in fake.posted("/events") for e in body["events"]]
    assert keys == [f"dataset:{DATASET}"]


def test_an_expired_dataset_is_recorded_as_incomplete(tmp_path: Path) -> None:
    store, fake = LocalStore(str(tmp_path)), FakeAuditStore()
    enqueue(store, DATASET, "req-1")  # the dataset objects are already gone
    assert archiver(store, fake).drain()["incomplete"] == 1
    [event] = fake.posted("/events")[0]["events"]
    assert event["event_type"] == "dataset.archive_incomplete"
    assert event["payload"]["reason"] == "DATASET_EXPIRED_BEFORE_ARCHIVE"
    assert fake.posted("/finalize") == [{"expected": {"dataset_ids": [DATASET]}}]  # the run cannot complete


def test_a_failed_verification_is_not_retried_forever(tmp_path: Path) -> None:
    store, fake = LocalStore(str(tmp_path)), FakeAuditStore(reject=True)
    dataset(store)
    enqueue(store, DATASET, "req-1")
    assert archiver(store, fake).drain()["incomplete"] == 1


def test_enqueue_never_fails_the_extraction() -> None:
    class Broken:
        def put_immutable(self, *args):
            raise OSError("bucket down")

    enqueue(Broken(), DATASET, "req-1")  # logged, not raised


def test_audit_settings_are_required_only_while_on(tmp_path: Path) -> None:
    off = Settings.from_env(base_env())
    assert off.audit_store_enabled is False and off.audit_store_url is None
    with pytest.raises(ConfigError):
        Settings.from_env(base_env(SQL_GOVERNOR_AUDIT_STORE_ENABLED="true", SQL_DATASET_LOCAL_DIR=str(tmp_path)))
    on = Settings.from_env(base_env(SQL_GOVERNOR_AUDIT_STORE_ENABLED="true", SQL_DATASET_LOCAL_DIR=str(tmp_path),
                                    AUDIT_STORE_URL="http://market-audit-store.railway.internal:8080",
                                    AUDIT_STORE_GOVERNOR_KEY="g" * 40))
    assert on.audit_store_enabled and "g" * 40 not in repr(on)
