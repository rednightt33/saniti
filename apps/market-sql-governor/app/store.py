"""Private immutable object storage for dataset snapshots (S3-compatible bucket, or a local
directory for development and tests). Object keys are never returned to market-ai-orc."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .config import Settings


class ObjectStore(Protocol):
    def put_immutable(self, key: str, payload: bytes, content_type: str, checksum: str) -> None: ...


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


def build_store(settings: Settings) -> ObjectStore | None:
    if settings.bucket_name:
        return S3Store(settings)
    if settings.dataset_local_dir:
        return LocalStore(settings.dataset_local_dir)
    return None
