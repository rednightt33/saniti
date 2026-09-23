"""Immutable Parquet snapshots: the only delivery form of an approved data request.

Rows are streamed into a zstd-compressed Parquet file in record batches, so the extracted
dataset is never held as Python rows in full. PostgreSQL numeric is stored as float64 (the
manifest records the source type); lookup_fact values keep exact decimal strings.
"""
from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from .decisions import narrowing

GOVERNOR_VERSION = "market-sql-governor/v1"
ENTITY_LIST_LIMIT = 5000

# PostgreSQL type OID -> Arrow type. Anything else is written as its text representation.
ARROW_TYPES: dict[int, pa.DataType] = {
    16: pa.bool_(), 20: pa.int64(), 21: pa.int16(), 23: pa.int32(), 700: pa.float32(),
    701: pa.float64(), 1700: pa.float64(), 1082: pa.date32(), 1114: pa.timestamp("us"),
    1184: pa.timestamp("us", tz="UTC"), 25: pa.string(), 1042: pa.string(), 1043: pa.string(),
}
TYPE_NAMES = {16: "boolean", 20: "bigint", 21: "smallint", 23: "integer", 700: "real",
              701: "double precision", 1700: "numeric", 1082: "date", 1114: "timestamp",
              1184: "timestamp with time zone", 25: "text", 1042: "character", 1043: "character varying"}


def _convert(values: list[Any], oid: int) -> list[Any]:
    if oid == 1700:
        return [None if value is None else float(value) for value in values]
    if oid in ARROW_TYPES:
        return values
    return [None if value is None else str(value) for value in values]


@dataclass
class ResultStats:
    time_index: int | None
    entity_index: int | None
    rows: int = 0
    min_time: Any = None
    max_time: Any = None
    entities: set[str] = field(default_factory=set)

    def add(self, batch: list[tuple[Any, ...]]) -> None:
        self.rows += len(batch)
        for row in batch:
            if self.time_index is not None and row[self.time_index] is not None:
                value = row[self.time_index]
                self.min_time = value if self.min_time is None or value < self.min_time else self.min_time
                self.max_time = value if self.max_time is None or value > self.max_time else self.max_time
            if self.entity_index is not None and row[self.entity_index] is not None:
                self.entities.add(str(row[self.entity_index]))


class ParquetBuilder:
    def __init__(self, names: list[str], oids: list[int], max_bytes: int, metadata: dict[str, str]) -> None:
        self.names = names
        self.oids = oids
        self.max_bytes = max_bytes
        self.schema = pa.schema(
            [pa.field(name, ARROW_TYPES.get(oid, pa.string())) for name, oid in zip(names, oids)],
            metadata={key.encode(): value.encode() for key, value in metadata.items()},
        )
        self.sink = io.BytesIO()
        self.writer = pq.ParquetWriter(self.sink, self.schema, compression="zstd")

    def write(self, batch: list[tuple[Any, ...]]) -> None:
        if not batch:
            return
        columns = list(zip(*batch))
        arrays = [pa.array(_convert(list(values), oid), type=self.schema.field(index).type)
                  for index, (values, oid) in enumerate(zip(columns, self.oids))]
        self.writer.write_batch(pa.record_batch(arrays, schema=self.schema))
        if self.sink.tell() > self.max_bytes:
            self.writer.close()
            raise narrowing("DATASET_TOO_LARGE",
                            f"The approved dataset exceeds the {self.max_bytes}-byte snapshot limit.",
                            limit_bytes=self.max_bytes)

    def finish(self) -> bytes:
        self.writer.close()
        payload = self.sink.getvalue()
        if len(payload) > self.max_bytes:
            raise narrowing("DATASET_TOO_LARGE",
                            f"The approved dataset exceeds the {self.max_bytes}-byte snapshot limit.",
                            limit_bytes=self.max_bytes)
        return payload


def iso(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if isinstance(value, (date, datetime)) else str(value)


def build_manifest(
    *,
    dataset_id: str,
    payload: bytes,
    checksum: str,
    columns: list[dict[str, Any]],
    oids: list[int],
    stats: ResultStats,
    source_tables: list[str],
    query_id: str,
    query_hash: str,
    request_id: str,
    spec: dict[str, Any],
    requested_range: dict[str, str | None] | None,
    requested_entities: list[str] | None,
    retention_hours: int,
) -> dict[str, Any]:
    created = datetime.now(timezone.utc).replace(microsecond=0)
    missing = None
    if requested_entities is not None and stats.entity_index is not None:
        missing = sorted(set(requested_entities) - stats.entities)
    entities = sorted(stats.entities) if stats.entity_index is not None else None
    completeness = "COMPLETE" if not missing else "MISSING_REQUESTED_ENTITIES"
    return {
        "manifest_version": "v1",
        "dataset_id": dataset_id,
        "format": "PARQUET",
        "compression": "zstd",
        "checksum_sha256": checksum,
        "row_count": stats.rows,
        "column_count": len(columns),
        "byte_count": len(payload),
        "schema": [
            {**column, "postgres_type": TYPE_NAMES.get(oid, "other"),
             "parquet_type": str(ARROW_TYPES.get(oid, pa.string())),
             **({"encoding_note": "numeric stored as float64"} if oid == 1700 else {})}
            for column, oid in zip(columns, oids)
        ],
        "source_tables": source_tables,
        "query_id": query_id,
        "query_hash": query_hash,
        "request_id": request_id,
        "request_spec": spec,
        "requested_scope": {"date_range": requested_range, "entities": requested_entities},
        "actual_date_range": {"from": iso(stats.min_time), "to": iso(stats.max_time)}
        if stats.time_index is not None else None,
        "entities_present_count": len(stats.entities) if stats.entity_index is not None else None,
        "entities_present": entities if entities is not None and len(entities) <= ENTITY_LIST_LIMIT else None,
        "missing_entities": missing,
        "truncated": False,
        "completeness_status": completeness,
        "created_at": created.isoformat(),
        "expires_at": (created + timedelta(hours=retention_hours)).isoformat(),
        "governor_version": GOVERNOR_VERSION,
    }


def manifest_bytes(manifest: dict[str, Any]) -> tuple[bytes, str]:
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return raw, hashlib.sha256(raw).hexdigest()
