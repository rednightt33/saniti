"""Dataset manifest lookup and short-lived dataset access.

market-ai-orc reads a bounded, safe subset of a dataset manifest (get_dataset_manifest).
market-python-sandbox additionally obtains a presigned GET URL for exactly one dataset's
Parquet file and the internal validator manifest (executed scope, data-plan lineage, source
contracts). Neither caller ever receives an object key, a bucket credential, SQL text, or the
full manifest.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .config import Settings
from .store import ObjectStore

logger = logging.getLogger("market_sql_governor")
DATASET_ID = re.compile(r"^ds_[0-9a-f]{24}$")
LIST_LIMIT = 200
FRIENDLY_TYPES = {
    "double": "float64", "float": "float32", "date32[day]": "date", "timestamp[us]": "timestamp",
    "timestamp[us, tz=UTC]": "timestamp_utc", "bool": "boolean", "string": "string",
    "int64": "int64", "int32": "int32", "int16": "int16",
}
NUMERIC_WARNING = ("NUMERIC_AS_FLOAT64: PostgreSQL numeric columns are stored as float64 in this dataset; "
                   "values are not decimal-exact.")


class DatasetError(Exception):
    def __init__(self, http_status: int, status: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.status = status
        self.message = message
        self.details = details

    def body(self) -> dict[str, Any]:
        return {"status": self.status, "message": self.message, **self.details}


def _bounded(values: list[Any] | None) -> tuple[list[Any] | None, int | None]:
    if values is None:
        return None, None
    return values[:LIST_LIMIT], len(values)


def safe_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """The only manifest fields that leave the Governor. Lists are bounded to LIST_LIMIT items."""
    columns = []
    numeric = []
    for column in manifest.get("schema") or []:
        parquet_type = str(column.get("parquet_type", "string"))
        entry = {
            "name": column.get("name"),
            "type": FRIENDLY_TYPES.get(parquet_type, parquet_type),
            "source_type": column.get("postgres_type"),
            "source_table": column.get("source_table"),
            "source_column": column.get("source_column"),
            "aggregation": column.get("aggregation"),
            "unit": column.get("unit"),
        }
        if column.get("encoding_note"):
            entry["encoding_note"] = column["encoding_note"]
            numeric.append(column.get("name"))
        columns.append(entry)
    scope = manifest.get("requested_scope") or {}
    entities, entities_count = _bounded(scope.get("entities"))
    missing, missing_count = _bounded(manifest.get("missing_entities"))
    return {
        "dataset_id": manifest["dataset_id"],
        "format": manifest.get("format", "PARQUET"),
        "source_tables": manifest.get("source_tables") or [],
        "query_id": manifest.get("query_id"),
        "row_count": manifest.get("row_count"),
        "column_count": manifest.get("column_count"),
        "byte_count": manifest.get("byte_count"),
        "columns": columns,
        "requested_scope": {"date_range": scope.get("date_range"), "entities": entities,
                            "entities_count": entities_count},
        "actual_date_range": manifest.get("actual_date_range"),
        "entities_present_count": manifest.get("entities_present_count"),
        "missing_entities": missing,
        "missing_entities_count": missing_count,
        "completeness_status": manifest.get("completeness_status"),
        "checksum_sha256": manifest.get("checksum_sha256"),
        "created_at": manifest.get("created_at"),
        "expires_at": manifest.get("expires_at"),
        "numeric_float64_columns": numeric,
        "warnings": [NUMERIC_WARNING] if numeric else [],
    }


def validator_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """The internal manifest the sandbox validator checks an approved spec against. Returned only with a dataset
    access grant (sandbox key), never through /manifest or to market-ai-orc: it carries the executed scope
    (filters with their values, relationships), the data-plan lineage, and the source contracts. It holds no SQL
    text, object key, credential, or row."""
    scope = manifest.get("requested_scope") or {}
    return {
        "manifest_version": manifest.get("manifest_version", "v1"),
        "dataset_id": manifest["dataset_id"],
        "lineage": manifest.get("lineage"),
        "executed_scope": manifest.get("executed_scope"),
        "source_contracts": manifest.get("source_contracts") or {},
        "query_hash": manifest.get("query_hash"),
        "request_sha256": manifest.get("request_sha256"),
        "checksum_sha256": manifest.get("checksum_sha256"),
        "requested_entities": scope.get("entities"),
        "entities_present": manifest.get("entities_present"),
        "entities_present_count": manifest.get("entities_present_count"),
    }


@dataclass
class DatasetService:
    settings: Settings
    store: ObjectStore | None

    def _manifest(self, dataset_id: str, now: datetime) -> dict[str, Any]:
        if not isinstance(dataset_id, str) or not DATASET_ID.fullmatch(dataset_id):
            raise DatasetError(422, "INVALID_DATASET_ID", "dataset_id must match ^ds_[0-9a-f]{24}$.")
        if self.store is None:
            raise DatasetError(503, "DATASET_STORAGE_UNAVAILABLE", "Dataset storage is not configured.")
        raw = self.store.get_optional(f"datasets/{dataset_id}/manifest.json")
        if raw is None:
            raise DatasetError(404, "DATASET_NOT_FOUND", "No governed dataset exists with this dataset_id.",
                               dataset_id=dataset_id)
        try:
            manifest = json.loads(raw)
            expires = datetime.fromisoformat(manifest["expires_at"])
        except (ValueError, KeyError, TypeError):
            raise DatasetError(503, "DATASET_UNAVAILABLE", "The dataset manifest is unreadable.",
                               dataset_id=dataset_id)
        if manifest.get("dataset_id") != dataset_id:
            raise DatasetError(503, "DATASET_UNAVAILABLE", "The dataset manifest does not match its id.",
                               dataset_id=dataset_id)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if now >= expires:
            raise DatasetError(410, "DATASET_EXPIRED",
                               "This dataset has expired and its data are no longer available. Request the "
                               "data again with request_data if still needed.",
                               dataset_id=dataset_id, expires_at=manifest["expires_at"])
        return manifest

    def manifest(self, dataset_id: str, *, now: datetime | None = None) -> dict[str, Any]:
        manifest = self._manifest(dataset_id, now or datetime.now(timezone.utc))
        return {"status": "AVAILABLE", **safe_manifest(manifest)}

    def access(self, dataset_id: str, *, request_id: str, analysis_id: str,
               now: datetime | None = None) -> dict[str, Any]:
        outcome = "ERROR"
        byte_count = None
        try:
            manifest = self._manifest(dataset_id, now or datetime.now(timezone.utc))
            key = f"datasets/{dataset_id}/data.parquet"
            size = self.store.size(key)
            if size is None:
                raise DatasetError(503, "DATASET_UNAVAILABLE", "The dataset file is missing.", dataset_id=dataset_id)
            if size != manifest.get("byte_count"):
                raise DatasetError(503, "DATASET_INTEGRITY_ERROR",
                                   "The dataset file size does not match its manifest.", dataset_id=dataset_id)
            ttl = self.settings.dataset_access_url_ttl_seconds
            url = self.store.presigned_get(key, ttl)
            outcome, byte_count = "GRANTED", size
            return {"status": "AVAILABLE", **safe_manifest(manifest), "validator_manifest": validator_manifest(manifest),
                    "download": {"url": url, "expires_in_seconds": ttl}}
        except DatasetError as exc:
            outcome = exc.status
            raise
        finally:
            # The URL is a bearer grant for its lifetime: it is never logged.
            logger.info(json.dumps({"event": "sql_governor_dataset_access", "request_id": request_id,
                                    "analysis_id": analysis_id, "dataset_id": dataset_id, "outcome": outcome,
                                    "byte_count": byte_count}, separators=(",", ":")))
