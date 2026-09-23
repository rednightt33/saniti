"""Governed dataset input: authorization by market-sql-governor, then a verified local copy.

For each dataset the harness asks the Governor (with a key that cannot submit queries) for a
short-lived read grant. The grant's presigned URL covers exactly one Parquet object and is used
only here: it is never logged, stored in a record, returned to market-ai-orc, or visible to the
analysis process, which receives only a read-only local file path.

Verified copies are cached (root-only directory) by dataset id and checksum. The Governor is still
asked for a grant on every analysis, so an expired dataset is never served from the cache.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import httpx

from .config import Settings

CHUNK = 1 << 20


class DatasetFailure(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Grant:
    dataset_id: str
    manifest: dict[str, Any]  # the Governor's bounded safe manifest subset
    url: str
    checksum: str
    byte_count: int
    row_count: int


class DatasetProvider:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None,
                 download_transport: httpx.BaseTransport | None = None) -> None:
        self.settings = settings
        self.cache = Path(settings.cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)
        os.chmod(self.cache, 0o700)
        self._lock = threading.Lock()
        # Called for every newly cached file so the service can expire it with its Governor snapshot.
        self.on_cached: Callable[[str, str, str, int, str | None], None] | None = None
        self.governor = httpx.Client(
            base_url=settings.governor_url, transport=transport, timeout=httpx.Timeout(15.0),
            headers={"Authorization": f"Bearer {settings.governor_access_key}"})
        self.downloads = httpx.Client(transport=download_transport, follow_redirects=False,
                                      timeout=httpx.Timeout(float(settings.download_timeout_seconds)))

    def grant(self, dataset_id: str, *, request_id: str, analysis_id: str) -> Grant:
        try:
            response = self.governor.post(f"/v1/datasets/{dataset_id}/access",
                                          json={"request_id": request_id, "analysis_id": analysis_id})
        except httpx.HTTPError:
            raise DatasetFailure("DATASET_UNAVAILABLE", "The SQL Governor could not be reached for dataset access.")
        try:
            body = response.json()
        except ValueError:
            body = {}
        if response.status_code != 200 or body.get("status") != "AVAILABLE":
            status = body.get("status") if isinstance(body, dict) else None
            code = status if status in {"DATASET_NOT_FOUND", "DATASET_EXPIRED", "INVALID_DATASET_ID",
                                        "DATASET_INTEGRITY_ERROR", "DATASET_STORAGE_UNAVAILABLE"} \
                else "DATASET_UNAVAILABLE"
            message = str(body.get("message") or f"Dataset access was refused (HTTP {response.status_code}).")
            if code == "DATASET_EXPIRED" and body.get("expires_at"):
                message = f"{message} (expired at {body['expires_at']})"
            raise DatasetFailure(code, f"{dataset_id}: {message}"[:500])
        download = body.pop("download", None) or {}
        body.pop("status", None)
        url = download.get("url")
        if not isinstance(url, str) or body.get("dataset_id") != dataset_id:
            raise DatasetFailure("DATASET_UNAVAILABLE", f"{dataset_id}: the Governor returned an invalid grant.")
        return Grant(dataset_id=dataset_id, manifest=body, url=url, checksum=str(body.get("checksum_sha256")),
                     byte_count=int(body.get("byte_count") or 0), row_count=int(body.get("row_count") or 0))

    def fetch(self, grant: Grant) -> Path:
        """Return a verified, read-only local copy of the granted dataset."""
        target = self.cache / f"{grant.dataset_id}-{grant.checksum}.parquet"
        with self._lock:
            if target.is_file() and target.stat().st_size == grant.byte_count:
                os.utime(target)  # LRU touch
                return target
        partial = self.cache / f".{grant.dataset_id}-{os.getpid()}-{threading.get_ident()}.part"
        digest = hashlib.sha256()
        written = 0
        try:
            with open(partial, "wb") as sink:
                for chunk in self._stream(grant):
                    written += len(chunk)
                    if written > grant.byte_count:
                        raise DatasetFailure("DATASET_INTEGRITY_ERROR",
                                             f"{grant.dataset_id}: the download is larger than its manifest.")
                    digest.update(chunk)
                    sink.write(chunk)
            if written != grant.byte_count or digest.hexdigest() != grant.checksum:
                raise DatasetFailure("DATASET_INTEGRITY_ERROR",
                                     f"{grant.dataset_id}: the downloaded file does not match its manifest checksum.")
            os.chmod(partial, 0o444)
            with self._lock:
                os.replace(partial, target)
                self._evict(keep=target)
            if self.on_cached is not None:
                self.on_cached(target.name, grant.dataset_id, grant.checksum, grant.byte_count,
                               grant.manifest.get("expires_at"))
            return target
        finally:
            if partial.exists():
                partial.unlink()

    def _stream(self, grant: Grant):
        parts = urlsplit(grant.url)
        if parts.scheme not in self.settings.dataset_url_schemes:
            raise DatasetFailure("DATASET_UNAVAILABLE",
                                 f"{grant.dataset_id}: the dataset URL scheme is not permitted.")
        if parts.scheme == "file":
            path = Path(unquote(parts.path))
            with open(path, "rb") as source:
                while chunk := source.read(CHUNK):
                    yield chunk
            return
        started = time.monotonic()
        try:
            with self.downloads.stream("GET", grant.url) as response:
                if response.status_code != 200:
                    raise DatasetFailure("DATASET_UNAVAILABLE",
                                         f"{grant.dataset_id}: the dataset download failed (HTTP {response.status_code}).")
                for chunk in response.iter_bytes(CHUNK):
                    if time.monotonic() - started > self.settings.download_timeout_seconds:
                        raise DatasetFailure("DATASET_UNAVAILABLE", f"{grant.dataset_id}: the dataset download timed out.")
                    yield chunk
        except httpx.HTTPError:
            # httpx messages can contain the URL; never propagate them.
            raise DatasetFailure("DATASET_UNAVAILABLE", f"{grant.dataset_id}: the dataset download failed.")

    def _evict(self, keep: Path) -> None:
        files = sorted((p for p in self.cache.glob("ds_*.parquet") if p != keep), key=lambda p: p.stat().st_mtime)
        total = sum(p.stat().st_size for p in files) + keep.stat().st_size
        while files and total > self.settings.dataset_cache_bytes:
            oldest = files.pop(0)
            total -= oldest.stat().st_size
            oldest.unlink(missing_ok=True)

    def evict_expired(self, records, now: datetime) -> int:
        """Delete cached copies whose Governor snapshot has expired, and cache files nobody recorded.

        Only the sandbox's own working copies are removed; the Governor's snapshots are never touched."""
        removed = 0
        known = set()
        with self._lock:
            for entry in records.cache_entries():
                path = self.cache / entry["file_name"]
                known.add(entry["file_name"])
                expires = entry.get("expires_at")
                try:
                    expired = expires is not None and datetime.fromisoformat(expires) <= now
                except ValueError:
                    expired = True
                if expired or not path.exists():
                    if path.exists():
                        path.unlink()
                        removed += 1
                    records.cache_remove(entry["file_name"])
            for path in self.cache.glob("ds_*.parquet"):
                if path.name not in known and time.time() - path.stat().st_mtime > 3600:
                    path.unlink(missing_ok=True)
                    removed += 1
        return removed

    @staticmethod
    def link(source: Path, destination: Path) -> None:
        """Place a cached dataset into a job's read-only input directory."""
        try:
            os.link(source, destination)
        except OSError:
            shutil.copyfile(source, destination)
            os.chmod(destination, 0o444)

    def close(self) -> None:
        self.governor.close()
        self.downloads.close()
