"""The private audit bucket (S3-compatible), or a local directory for development and tests.

Objects are content-addressed: objects/sha256/<first two hex>/<sha256>. A producer never receives that key. It gets
a short-lived presigned PUT for one staging key (staging/<artifact_id>/<nonce>) that nothing reads; this service then
hashes the staged bytes itself and only a verified object is copied to its content address and becomes READY. A
still-valid upload URL can therefore never replace a READY object, and a producer can neither list nor read the
bucket. Reads leave only as a short-lived presigned GET granted (and logged) by the access endpoint."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path
from typing import Protocol

from .config import Settings

CHUNK = 1024 * 1024


def object_key(sha256: str) -> str:
    return f"objects/sha256/{sha256[:2]}/{sha256}"


def staging_key(artifact_id: str) -> str:
    return f"staging/{artifact_id}/{secrets.token_hex(16)}"


class ObjectStore(Protocol):
    def presigned_put(self, key: str, media_type: str, expires_seconds: int) -> tuple[str, dict[str, str]]: ...

    def presigned_get(self, key: str, expires_seconds: int) -> str: ...

    def size(self, key: str) -> int | None: ...

    def digest(self, key: str) -> tuple[str, int] | None: ...

    def put(self, key: str, payload: bytes, media_type: str) -> None: ...

    def promote(self, source: str, target: str) -> None: ...

    def delete(self, key: str) -> None: ...

    def ping(self) -> None: ...


class S3Store:
    def __init__(self, settings: Settings) -> None:
        import boto3  # imported lazily so the tests run without it
        from botocore.config import Config

        self.bucket = settings.bucket_name
        self.client = boto3.client(
            "s3", endpoint_url=settings.bucket_endpoint, aws_access_key_id=settings.bucket_access_key_id,
            aws_secret_access_key=settings.bucket_secret_access_key, region_name=settings.bucket_region,
            config=Config(signature_version="s3v4"))

    @staticmethod
    def _missing(exc: Exception) -> bool:
        response = getattr(exc, "response", None) or {}
        code = str((response.get("Error") or {}).get("Code", ""))
        status = int((response.get("ResponseMetadata") or {}).get("HTTPStatusCode", 0) or 0)
        return code in {"NoSuchKey", "404", "NotFound"} or status == 404

    def presigned_put(self, key: str, media_type: str, expires_seconds: int) -> tuple[str, dict[str, str]]:
        url = self.client.generate_presigned_url(
            "put_object", Params={"Bucket": self.bucket, "Key": key, "ContentType": media_type},
            ExpiresIn=expires_seconds)
        return url, {"Content-Type": media_type}

    def presigned_get(self, key: str, expires_seconds: int) -> str:
        return self.client.generate_presigned_url("get_object", Params={"Bucket": self.bucket, "Key": key},
                                                  ExpiresIn=expires_seconds)

    def size(self, key: str) -> int | None:
        from botocore.exceptions import ClientError

        try:
            return int(self.client.head_object(Bucket=self.bucket, Key=key)["ContentLength"])
        except ClientError as exc:
            if self._missing(exc):
                return None
            raise

    def digest(self, key: str) -> tuple[str, int] | None:
        from botocore.exceptions import ClientError

        try:
            body = self.client.get_object(Bucket=self.bucket, Key=key)["Body"]
        except ClientError as exc:
            if self._missing(exc):
                return None
            raise
        hasher, size = hashlib.sha256(), 0
        for chunk in iter(lambda: body.read(CHUNK), b""):
            hasher.update(chunk)
            size += len(chunk)
        return hasher.hexdigest(), size

    def put(self, key: str, payload: bytes, media_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=payload, ContentType=media_type)

    def promote(self, source: str, target: str) -> None:
        self.client.copy_object(Bucket=self.bucket, Key=target, CopySource={"Bucket": self.bucket, "Key": source})

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def ping(self) -> None:
        self.client.head_bucket(Bucket=self.bucket)


class LocalStore:
    """Development and tests: objects in a directory; upload and download URLs point at this service's own
    /v1/local/objects/{token} endpoints, signed with AUDIT_LOCAL_SIGNING_KEY and expiring like presigned URLs."""

    def __init__(self, directory: str, signing_key: str, base_url: str) -> None:
        self.root = Path(directory)
        self.root.mkdir(parents=True, exist_ok=True)
        self.key = signing_key.encode()
        self.base_url = base_url.rstrip("/")

    def token(self, key: str, method: str, expires_seconds: int, media_type: str | None = None) -> str:
        body = json.dumps({"k": key, "m": method, "e": int(time.time()) + expires_seconds, "t": media_type},
                          separators=(",", ":")).encode()
        mac = hmac.new(self.key, body, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(body).decode().rstrip("=") + "." + \
            base64.urlsafe_b64encode(mac).decode().rstrip("=")

    def check(self, token: str, method: str) -> dict | None:
        try:
            raw, mac = token.split(".", 1)
            body = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
            given = base64.urlsafe_b64decode(mac + "=" * (-len(mac) % 4))
            claims = json.loads(body)
        except (ValueError, json.JSONDecodeError):
            return None
        if not hmac.compare_digest(hmac.new(self.key, body, hashlib.sha256).digest(), given):
            return None
        if claims.get("m") != method or int(claims.get("e", 0)) < time.time():
            return None
        return claims

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError("key escapes the object directory")
        return path

    def presigned_put(self, key: str, media_type: str, expires_seconds: int) -> tuple[str, dict[str, str]]:
        return (f"{self.base_url}/v1/local/objects/{self.token(key, 'PUT', expires_seconds, media_type)}",
                {"Content-Type": media_type})

    def presigned_get(self, key: str, expires_seconds: int) -> str:
        return f"{self.base_url}/v1/local/objects/{self.token(key, 'GET', expires_seconds)}"

    def size(self, key: str) -> int | None:
        path = self._path(key)
        return path.stat().st_size if path.is_file() else None

    def digest(self, key: str) -> tuple[str, int] | None:
        path = self._path(key)
        if not path.is_file():
            return None
        hasher, size = hashlib.sha256(), 0
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(CHUNK), b""):
                hasher.update(chunk)
                size += len(chunk)
        return hasher.hexdigest(), size

    def read(self, key: str) -> bytes | None:
        path = self._path(key)
        return path.read_bytes() if path.is_file() else None

    def put(self, key: str, payload: bytes, media_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_name(path.name + ".partial")
        partial.write_bytes(payload)
        partial.replace(path)

    def promote(self, source: str, target: str) -> None:
        data = self._path(source).read_bytes()
        self.put(target, data, "application/octet-stream")

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def ping(self) -> None:
        if not self.root.is_dir():
            raise RuntimeError("local object directory is missing")


def build_store(settings: Settings) -> ObjectStore:
    if settings.bucket_name:
        return S3Store(settings)
    return LocalStore(settings.local_object_dir or "", settings.local_signing_key or "", settings.public_base_url or "")
