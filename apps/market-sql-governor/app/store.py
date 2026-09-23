"""Private immutable object storage for dataset snapshots (S3-compatible bucket, or a local
directory for development and tests). Object keys are never returned to market-ai-orc.

A presigned URL is the only form of dataset access that leaves this service: a SigV4 GET for
one exact object key, expiring after SQL_DATASET_ACCESS_URL_TTL_SECONDS, handed only to
market-python-sandbox. It cannot list, write, or read any other key."""
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

    # Used by dataset manifest/access lookups (app/datasets.py).
    def get_optional(self, key: str) -> bytes | None: ...

    def size(self, key: str) -> int | None: ...

    def presigned_get(self, key: str, expires_seconds: int) -> str: ...

    def delete(self, key: str) -> None: ...


class S3Store:
    def __init__(self, settings: Settings) -> None:
        import boto3  # imported lazily so the service starts without storage configured
        from botocore.config import Config

        self.bucket = settings.bucket_name
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.bucket_endpoint,
            aws_access_key_id=settings.bucket_access_key_id,
            aws_secret_access_key=settings.bucket_secret_access_key,
            region_name=settings.bucket_region,
            config=Config(signature_version="s3v4"),  # presigned URLs carry no secret, only a signature
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

    @staticmethod
    def _missing(exc: Exception) -> bool:
        response = getattr(exc, "response", None) or {}
        code = str((response.get("Error") or {}).get("Code", ""))
        status = int((response.get("ResponseMetadata") or {}).get("HTTPStatusCode", 0) or 0)
        return code in {"NoSuchKey", "404", "NotFound"} or status == 404

    def get_optional(self, key: str) -> bytes | None:
        from botocore.exceptions import ClientError

        try:
            return self.get(key)
        except ClientError as exc:
            if self._missing(exc):
                return None
            raise

    def size(self, key: str) -> int | None:
        from botocore.exceptions import ClientError

        try:
            return int(self.client.head_object(Bucket=self.bucket, Key=key)["ContentLength"])
        except ClientError as exc:
            if self._missing(exc):
                return None
            raise

    def presigned_get(self, key: str, expires_seconds: int) -> str:
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires_seconds)

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

    def get_optional(self, key: str) -> bytes | None:
        path = self.root / key
        return path.read_bytes() if path.is_file() else None

    def size(self, key: str) -> int | None:
        path = self.root / key
        return path.stat().st_size if path.is_file() else None

    def presigned_get(self, key: str, expires_seconds: int) -> str:
        # Development/tests only: a file:// URI. market-python-sandbox accepts it only when
        # PY_SANDBOX_DATASET_URL_SCHEMES explicitly includes "file"; production accepts https only.
        return (self.root / key).resolve().as_uri()

    def delete(self, key: str) -> None:
        (self.root / key).unlink(missing_ok=True)


def build_store(settings: Settings) -> ObjectStore | None:
    if settings.bucket_name:
        return S3Store(settings)
    if settings.dataset_local_dir:
        return LocalStore(settings.dataset_local_dir)
    return None
