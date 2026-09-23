"""Dataset manifest lookup, short-lived dataset access, and expiry tombstones."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from app.config import ConfigError, Settings
from app.datasets import LIST_LIMIT, DatasetService, safe_manifest
from app.janitor import cleanup_expired
from app.main import create_app
from app.store import LocalStore, S3Store
from conftest import API_KEY, base_env

ACCESS_KEY = "test-dataset-access-key-" + "a" * 24
NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
LIVE, OLD, GONE = ("ds_" + c * 24 for c in "123")
PAYLOAD = b"PAR1-fake-parquet-bytes"


def manifest(dataset_id: str, expires: datetime, **extra) -> dict:
    return {
        "manifest_version": "v1", "dataset_id": dataset_id, "format": "PARQUET", "compression": "zstd",
        "checksum_sha256": "c" * 64, "row_count": 3, "column_count": 3, "byte_count": len(PAYLOAD),
        "schema": [
            {"name": "Symbol", "type": "character varying", "source_table": "Price_Stock_Indonesia_IDX",
             "source_column": "Symbol", "aggregation": None, "postgres_type": "character varying",
             "parquet_type": "string"},
            {"name": "Date", "type": "date", "source_table": "Price_Stock_Indonesia_IDX", "source_column": "Date",
             "aggregation": None, "postgres_type": "date", "parquet_type": "date32[day]"},
            {"name": "Close", "type": "numeric", "source_table": "Price_Stock_Indonesia_IDX",
             "source_column": "Close", "aggregation": None, "postgres_type": "numeric", "parquet_type": "double",
             "encoding_note": "numeric stored as float64"},
        ],
        "source_tables": ["Price_Stock_Indonesia_IDX"], "query_id": "qry_1", "query_hash": "h" * 64,
        "request_id": "req-1", "request_spec": {"purpose": "secret-ish spec"},
        "requested_scope": {"date_range": {"from": "2026-01-01", "to": "2026-09-01"}, "entities": None},
        "actual_date_range": {"from": "2026-01-02", "to": "2026-08-29"}, "entities_present_count": 2,
        "entities_present": ["BBCA", "BBRI"], "missing_entities": [], "truncated": False,
        "completeness_status": "COMPLETE", "created_at": (expires - timedelta(days=7)).isoformat(),
        "expires_at": expires.isoformat(), "governor_version": "market-sql-governor/v1", **extra,
    }


def seed(store: LocalStore, now: datetime = NOW) -> None:
    for dataset_id, expires in ((LIVE, now + timedelta(days=1)), (OLD, now - timedelta(hours=1))):
        store.put_immutable(f"datasets/{dataset_id}/data.parquet", PAYLOAD, "", "c")
        store.put_immutable(f"datasets/{dataset_id}/manifest.json",
                            json.dumps(manifest(dataset_id, expires)).encode(), "", "c")


def service(tmp_path) -> DatasetService:
    store = LocalStore(str(tmp_path))
    seed(store)
    settings = Settings.from_env(base_env(SQL_DATASET_LOCAL_DIR=str(tmp_path), SQL_GOVERNOR_DATASET_ACCESS_KEY=ACCESS_KEY))
    return DatasetService(settings, store)


def test_manifest_is_a_bounded_safe_subset(tmp_path) -> None:
    result = service(tmp_path).manifest(LIVE, now=NOW)
    assert result["status"] == "AVAILABLE" and result["dataset_id"] == LIVE and result["row_count"] == 3
    assert [c["type"] for c in result["columns"]] == ["string", "date", "float64"]
    assert result["numeric_float64_columns"] == ["Close"] and result["warnings"][0].startswith("NUMERIC_AS_FLOAT64")
    text = json.dumps(result)
    for hidden in ("request_spec", "secret-ish", "entities_present\"", "datasets/", "manifest.json", "data.parquet"):
        assert hidden not in text


def test_long_entity_lists_are_bounded(tmp_path) -> None:
    many = [f"T{i:04d}" for i in range(LIST_LIMIT + 50)]
    raw = manifest(LIVE, NOW + timedelta(days=1), missing_entities=many)
    raw["requested_scope"]["entities"] = many
    result = safe_manifest(raw)
    assert len(result["missing_entities"]) == LIST_LIMIT and result["missing_entities_count"] == LIST_LIMIT + 50
    assert len(result["requested_scope"]["entities"]) == LIST_LIMIT
    assert result["requested_scope"]["entities_count"] == LIST_LIMIT + 50


@pytest.mark.parametrize(("dataset_id", "status"), [
    (OLD, "DATASET_EXPIRED"), (GONE, "DATASET_NOT_FOUND"), ("ds_123", "INVALID_DATASET_ID"),
    ("../../etc/passwd", "INVALID_DATASET_ID"), ("DS_" + "A" * 24, "INVALID_DATASET_ID"),
])
def test_unusable_datasets_fail_explicitly(tmp_path, dataset_id: str, status: str) -> None:
    svc = service(tmp_path)
    for call in (lambda: svc.manifest(dataset_id, now=NOW),
                 lambda: svc.access(dataset_id, request_id="r", analysis_id="a", now=NOW)):
        with pytest.raises(Exception) as caught:
            call()
        assert caught.value.status == status
    if status == "DATASET_EXPIRED":
        assert caught.value.http_status == 410 and caught.value.details["expires_at"]


def test_access_returns_a_url_for_the_one_dataset_and_checks_its_size(tmp_path) -> None:
    svc = service(tmp_path)
    granted = svc.access(LIVE, request_id="r1", analysis_id="ana_1", now=NOW)
    assert granted["download"]["expires_in_seconds"] == 120
    assert granted["download"]["url"].endswith(f"/datasets/{LIVE}/data.parquet")
    (tmp_path / "datasets" / LIVE / "data.parquet").write_bytes(PAYLOAD + b"tampered")
    with pytest.raises(Exception) as caught:
        svc.access(LIVE, request_id="r1", analysis_id="ana_1", now=NOW)
    assert caught.value.status == "DATASET_INTEGRITY_ERROR"
    (tmp_path / "datasets" / LIVE / "data.parquet").unlink()
    with pytest.raises(Exception) as caught:
        svc.access(LIVE, request_id="r1", analysis_id="ana_1", now=NOW)
    assert caught.value.status == "DATASET_UNAVAILABLE"


def test_s3_presigned_url_is_a_short_sigv4_get_for_one_key() -> None:
    import boto3
    from botocore.config import Config

    store = S3Store.__new__(S3Store)
    store.bucket = "market-sql-datasets-x"
    store.client = boto3.client("s3", endpoint_url="https://storage.example.test", region_name="auto",
                                aws_access_key_id="AKIDEXAMPLE", aws_secret_access_key="never-in-url-" + "s" * 20,
                                config=Config(signature_version="s3v4"))
    url = store.presigned_get(f"datasets/{LIVE}/data.parquet", 120)
    parts = urlsplit(url)
    query = parse_qs(parts.query)
    assert parts.scheme == "https" and parts.path.endswith(f"/datasets/{LIVE}/data.parquet")
    assert query["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"] and query["X-Amz-Expires"] == ["120"]
    assert query["X-Amz-SignedHeaders"] == ["host"] and "never-in-url" not in url


def client(tmp_path) -> TestClient:
    store = LocalStore(str(tmp_path))
    seed(store, datetime.now(timezone.utc))  # the app uses the real clock
    settings = Settings.from_env(base_env(SQL_DATASET_LOCAL_DIR=str(tmp_path), SQL_GOVERNOR_DATASET_ACCESS_KEY=ACCESS_KEY,
                                          SQL_DATASET_CLEANUP_INTERVAL_SECONDS="0"))
    return TestClient(create_app(settings))


def test_endpoint_keys_have_disjoint_purposes(tmp_path) -> None:
    api = client(tmp_path)
    orc, sandbox = {"Authorization": f"Bearer {API_KEY}"}, {"Authorization": f"Bearer {ACCESS_KEY}"}
    body = {"request_id": "r1", "analysis_id": "ana_1"}
    assert api.get(f"/v1/datasets/{LIVE}/manifest").status_code == 401
    assert api.get(f"/v1/datasets/{LIVE}/manifest", headers=orc).json()["status"] == "AVAILABLE"
    assert api.get(f"/v1/datasets/{LIVE}/manifest", headers=sandbox).json()["status"] == "AVAILABLE"
    assert api.post(f"/v1/datasets/{LIVE}/access", json=body, headers=orc).status_code == 401  # orc gets no URLs
    granted = api.post(f"/v1/datasets/{LIVE}/access", json=body, headers=sandbox)
    assert granted.status_code == 200 and granted.json()["download"]["url"]
    assert api.post("/v1/query", json={"request_id": "r1", "spec": {}}, headers=sandbox).status_code == 401
    expired = api.get(f"/v1/datasets/{OLD}/manifest", headers=orc)
    assert expired.status_code == 410 and expired.json()["status"] == "DATASET_EXPIRED"
    assert api.get(f"/v1/datasets/{GONE}/manifest", headers=orc).status_code == 404
    for bad in ({"request_id": "r1"}, {**body, "url": "x"}, {"request_id": "bad id!", "analysis_id": "a"}):
        assert api.post(f"/v1/datasets/{LIVE}/access", json=bad, headers=sandbox).status_code == 422


def test_access_is_disabled_without_its_key(tmp_path) -> None:
    store = LocalStore(str(tmp_path))
    seed(store)
    api = TestClient(create_app(Settings.from_env(base_env(SQL_DATASET_LOCAL_DIR=str(tmp_path)))))
    for key in (API_KEY, "", "None"):
        response = api.post(f"/v1/datasets/{LIVE}/access", json={"request_id": "r", "analysis_id": "a"},
                            headers={"Authorization": f"Bearer {key}"})
        assert response.status_code == 401


def test_access_log_never_contains_the_url(tmp_path) -> None:
    records: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())
    logger = logging.getLogger("market_sql_governor")
    handler, level = Capture(), logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        granted = service(tmp_path).access(LIVE, request_id="r1", analysis_id="ana_1", now=NOW)
    finally:
        logger.removeHandler(handler)
        logger.setLevel(level)
    event = json.loads(next(r for r in records if "sql_governor_dataset_access" in r))
    assert event["outcome"] == "GRANTED" and event["dataset_id"] == LIVE and event["analysis_id"] == "ana_1"
    assert granted["download"]["url"] not in "".join(records) and "datasets/" not in "".join(records)


@pytest.mark.parametrize(("overrides", "message"), [
    ({"SQL_GOVERNOR_DATASET_ACCESS_KEY": "short"}, "at least 32"),
    ({"SQL_GOVERNOR_DATASET_ACCESS_KEY": API_KEY}, "must differ"),
    ({"SQL_DATASET_ACCESS_URL_TTL_SECONDS": "3600"}, "between 30 and 900"),
    ({"SQL_DATASET_TOMBSTONE_RETENTION_HOURS": "-1"}, "between 0 and 8760"),
])
def test_dataset_access_configuration_is_validated(overrides: dict, message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        Settings.from_env(base_env(**overrides))


def test_janitor_keeps_the_manifest_as_a_tombstone_then_removes_it(tmp_path) -> None:
    store = LocalStore(str(tmp_path))
    seed(store)
    first = cleanup_expired(store, now=NOW, retention_hours=168, tombstone_hours=720)
    assert first["deleted_ids"] == [OLD] and first["tombstones_deleted"] == 0
    assert not (tmp_path / "datasets" / OLD / "data.parquet").exists()
    assert (tmp_path / "datasets" / OLD / "manifest.json").exists()
    svc = DatasetService(Settings.from_env(base_env(SQL_DATASET_LOCAL_DIR=str(tmp_path))), store)
    with pytest.raises(Exception) as caught:
        svc.manifest(OLD, now=NOW)
    assert caught.value.status == "DATASET_EXPIRED"       # not DATASET_NOT_FOUND after deletion
    again = cleanup_expired(store, now=NOW + timedelta(days=29), retention_hours=168, tombstone_hours=720)
    assert again["deleted_ids"] == [LIVE] and again["tombstones_deleted"] == 0  # OLD's data already gone
    later = NOW + timedelta(days=30, hours=1)  # past OLD's tombstone window, inside LIVE's
    last = cleanup_expired(store, now=later, retention_hours=168, tombstone_hours=720)
    assert last["datasets_deleted"] == 0 and last["tombstones_deleted"] == 1
    assert not (tmp_path / "datasets" / OLD / "manifest.json").exists()
    assert (tmp_path / "datasets" / LIVE / "manifest.json").exists()
    with pytest.raises(Exception) as caught:
        svc.manifest(OLD, now=later)
    assert caught.value.status == "DATASET_NOT_FOUND"


def test_unreadable_manifest_is_not_kept_as_a_tombstone(tmp_path) -> None:
    store = LocalStore(str(tmp_path))
    store.put_immutable(f"datasets/{GONE}/data.parquet", b"x", "", "c")
    store.put_immutable(f"datasets/{GONE}/manifest.json", b"not json", "", "c")
    stamp = (NOW - timedelta(days=8)).timestamp()
    for name in ("data.parquet", "manifest.json"):
        os.utime(tmp_path / "datasets" / GONE / name, (stamp, stamp))
    summary = cleanup_expired(store, now=NOW, retention_hours=168, tombstone_hours=720)
    assert summary["deleted_ids"] == [GONE] and summary["tombstones_deleted"] == 1


def test_s3_store_missing_objects_are_none() -> None:
    from botocore.exceptions import ClientError

    class Missing:
        def get_object(self, Bucket, Key):
            raise ClientError({"Error": {"Code": "NoSuchKey"}, "ResponseMetadata": {"HTTPStatusCode": 404}}, "GetObject")

        def head_object(self, Bucket, Key):
            raise ClientError({"Error": {"Code": "404"}, "ResponseMetadata": {"HTTPStatusCode": 404}}, "HeadObject")

    store = S3Store.__new__(S3Store)
    store.bucket, store.client = "b", Missing()
    assert store.get_optional("datasets/x/manifest.json") is None and store.size("datasets/x/data.parquet") is None

    class Denied(Missing):
        def get_object(self, Bucket, Key):
            raise ClientError({"Error": {"Code": "AccessDenied"}, "ResponseMetadata": {"HTTPStatusCode": 403}}, "GetObject")
    store.client = Denied()
    with pytest.raises(ClientError):
        store.get_optional("datasets/x/manifest.json")
