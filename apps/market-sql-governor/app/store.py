"""Private immutable object storage for dataset snapshots (S3-compatible bucket, or a local
directory for development and tests). Object keys are never returned to market-ai-orc."""
from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from .config import Settings


class ObjectStore(Protocol):
    def put_immutable(self, key: str, payload: bytes, content_type: str, checksum: str) -> None: ...

    # Used only by the expiry janitor (app/janitor.py).
    def list_keys(self, prefix: str) -> Iterator[tuple[str, datetime]]: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...


class S3Store:
    def __init__(self, settings: Settings) -> None:
        import boto3  # imported lazily so the service starts without storage configured

        self.bucket = settings.bucket_name
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.bucket_endpoint,
            aws_access_key_id=settings.bucket_access_key_id,
            aws_secret_access_key=settings.bucket_secret_access_key,
            region_name=settings.bucket_region,
        )

    def put_immutable(self, key: str, payload: bytes, content_type: str, checksum: str) -> None:
        from botocore.exceptions import ClientError

        try:
            existing = self.client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            status = int(exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0))
            if status not in {403, 404}:
                raise
        else:
            if (existing.get("Metadata") or {}).get("sha256") != checksum:
                raise RuntimeError("Immutable dataset key already holds different content")
            return
        self.client.put_object(Bucket=self.bucket, Key=key, Body=payload, ContentType=content_type,
                               Metadata={"sha256": checksum})

    def list_keys(self, prefix: str) -> Iterator[tuple[str, datetime]]:
        for page in self.client.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=prefix):
            for item in page.get("Contents") or []:
                yield item["Key"], item["LastModified"]

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


class LocalStore:
    def __init__(self, directory: str) -> None:
        self.root = Path(directory)

    def put_immutable(self, key: str, payload: bytes, content_type: str, checksum: str) -> None:
        path = self.root / key
        if path.exists():
            if path.read_bytes() != payload:
                raise RuntimeError("Immutable dataset key already holds different content")
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

    def list_keys(self, prefix: str) -> Iterator[tuple[str, datetime]]:
        base = self.root / prefix
        if not base.exists():
            return
        for path in sorted(p for p in base.rglob("*") if p.is_file()):
            modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            yield path.relative_to(self.root).as_posix(), modified

    def get(self, key: str) -> bytes:
        return (self.root / key).read_bytes()

    def delete(self, key: str) -> None:
        (self.root / key).unlink(missing_ok=True)


def build_store(settings: Settings) -> ObjectStore | None:
    if settings.bucket_name:
        return S3Store(settings)
    if settings.dataset_local_dir:
        return LocalStore(settings.dataset_local_dir)
    return None
