from __future__ import annotations

from dataclasses import dataclass

import boto3
from botocore.exceptions import ClientError

from .config import Settings


@dataclass(frozen=True)
class SnapshotObject:
    key: str
    compressed_bytes: int


class AnalyticsSnapshotStore:
    """Private S3-compatible storage used only by the credentialed backend."""

    def __init__(self, settings: Settings) -> None:
        self.bucket = settings.analytics_bucket_name
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.analytics_bucket_endpoint,
            aws_access_key_id=settings.analytics_bucket_access_key_id,
            aws_secret_access_key=settings.analytics_bucket_secret_access_key,
            region_name=settings.analytics_bucket_region,
        )

    def put_immutable(self, key: str, payload: bytes, checksum: str) -> SnapshotObject:
        # A random request/job/hash path is write-once by contract. HEAD protects
        # against an accidental retry overwriting a different payload.
        try:
            existing = self.client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            status = int(exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0))
            if status not in {404, 403}:
                raise
        else:
            metadata = existing.get("Metadata") or {}
            if metadata.get("sha256") != checksum:
                raise RuntimeError("Immutable analytics snapshot key already contains different data")
            return SnapshotObject(key=key, compressed_bytes=int(existing["ContentLength"]))

        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=payload,
            ContentType="application/gzip",
            Metadata={"sha256": checksum},
        )
        return SnapshotObject(key=key, compressed_bytes=len(payload))

    def presigned_download(self, key: str, expires_seconds: int = 300) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)
