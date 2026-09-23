from __future__ import annotations

import hashlib
import os
import re
import shutil
import sys
import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(1, str(Path(__file__).resolve().parents[1] / "runtime"))  # saniti, seccomp

from app.config import Settings  # noqa: E402
from app.datasets import DatasetProvider  # noqa: E402
from app.service import AnalysisService  # noqa: E402

API_KEY = "test-sandbox-api-key-" + "k" * 24
ACCESS_KEY = "test-governor-access-key-" + "a" * 24
PYTHON = os.environ.get("PY_SANDBOX_TEST_PYTHON", sys.executable)
TEST_ROOT = Path(os.environ.get("PY_SANDBOX_TEST_ROOT", "/srv/sandbox-tests"))
IS_ROOT = os.geteuid() == 0
requires_root = pytest.mark.skipif(not IS_ROOT, reason="isolation tests need root to start analyses as a slot user")


def base_env(root: Path, **overrides: str) -> dict[str, str]:
    return {
        "PY_SANDBOX_API_KEY": API_KEY, "SQL_GOVERNOR_URL": "http://governor.test",
        "SQL_GOVERNOR_DATASET_ACCESS_KEY": ACCESS_KEY, "PY_SANDBOX_DATA_DIR": str(root / "data"),
        "PY_SANDBOX_JOBS_DIR": str(root / "jobs"), "PY_SANDBOX_CACHE_DIR": str(root / "cache"),
        "PY_SANDBOX_PYTHON": PYTHON, "PY_SANDBOX_DATASET_URL_SCHEMES": "file",
        "PY_SANDBOX_CLEANUP_INTERVAL_SECONDS": "0", "PY_SANDBOX_SUBMIT_WAIT_SECONDS": "60",
        "PY_SANDBOX_MAX_POLL_WAIT_SECONDS": "60", "PY_SANDBOX_MAX_RUNTIME_SECONDS": "60", **overrides,
    }


class FakeGovernor:
    """Answers /v1/datasets/{id}/access like market-sql-governor, granting file:// URLs to local Parquet."""

    PATH = re.compile(r"^/v1/datasets/([^/]+)/access$")

    def __init__(self, root: Path) -> None:
        self.root = root / "governor"
        self.root.mkdir(parents=True)
        self.datasets: dict[str, dict] = {}
        self.calls: list[dict] = []
        self.checksum_override: dict[str, str] = {}

    def add(self, data, *, expired: bool = False, numeric: tuple[str, ...] = (), completeness: str = "COMPLETE",
            dataset_id: str | None = None) -> str:
        dataset_id = dataset_id or f"ds_{uuid.uuid4().hex[:24]}"
        table = data if isinstance(data, pa.Table) else pa.Table.from_pandas(data, preserve_index=False)
        path = self.root / f"{dataset_id}.parquet"
        pq.write_table(table, path, compression="zstd")
        raw = path.read_bytes()
        now = datetime.now(timezone.utc)
        self.datasets[dataset_id] = {
            "path": path, "expired": expired, "manifest": {
                "dataset_id": dataset_id, "format": "PARQUET", "source_tables": ["Price_Stock_Indonesia_IDX"],
                "query_id": "qry_test", "row_count": table.num_rows, "column_count": table.num_columns,
                "byte_count": len(raw), "columns": [{"name": n, "type": str(t)} for n, t in
                                                    zip(table.column_names, table.schema.types)],
                "completeness_status": completeness, "missing_entities_count": 0 if completeness == "COMPLETE" else 3,
                "checksum_sha256": hashlib.sha256(raw).hexdigest(), "numeric_float64_columns": list(numeric),
                "created_at": now.isoformat(), "expires_at": (now + timedelta(days=7)).isoformat(),
            }}
        return dataset_id

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append({"path": request.url.path, "authorization": request.headers.get("authorization")})
        if request.headers.get("authorization") != f"Bearer {ACCESS_KEY}":
            return httpx.Response(401, json={"detail": "Unauthorized"})
        match = self.PATH.fullmatch(request.url.path)
        if request.method != "POST" or match is None:
            return httpx.Response(404, json={"detail": "Not Found"})
        dataset_id = match.group(1)
        if not re.fullmatch(r"ds_[0-9a-f]{24}", dataset_id):
            return httpx.Response(422, json={"status": "INVALID_DATASET_ID", "message": "bad id"})
        entry = self.datasets.get(dataset_id)
        if entry is None:
            return httpx.Response(404, json={"status": "DATASET_NOT_FOUND", "message": "No governed dataset exists "
                                                                                       "with this dataset_id.",
                                             "dataset_id": dataset_id})
        if entry["expired"]:
            return httpx.Response(410, json={"status": "DATASET_EXPIRED", "message": "This dataset has expired.",
                                             "dataset_id": dataset_id, "expires_at": "2026-09-01T00:00:00+00:00"})
        manifest = dict(entry["manifest"])
        if dataset_id in self.checksum_override:
            manifest["checksum_sha256"] = self.checksum_override[dataset_id]
        return httpx.Response(200, json={"status": "AVAILABLE", **manifest,
                                         "download": {"url": entry["path"].resolve().as_uri(),
                                                      "expires_in_seconds": 120}})

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


@pytest.fixture
def sandbox_root() -> Iterator[Path]:
    TEST_ROOT.mkdir(parents=True, exist_ok=True)
    os.chmod(TEST_ROOT, 0o711)
    root = TEST_ROOT / uuid.uuid4().hex[:12]
    root.mkdir()
    os.chmod(root, 0o711)
    yield root
    shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
def governor(sandbox_root: Path) -> FakeGovernor:
    return FakeGovernor(sandbox_root)


@pytest.fixture
def make_service(sandbox_root: Path, governor: FakeGovernor):
    services: list[AnalysisService] = []

    def factory(start: bool = True, **overrides: str) -> AnalysisService:
        settings = Settings.from_env(base_env(sandbox_root, **overrides))
        service = AnalysisService(settings, datasets=DatasetProvider(settings, transport=governor.transport()))
        if start:
            service.start()
        services.append(service)
        return service

    yield factory
    for service in services:
        service.stop()
        service.records.close()


def ohlc_frame(tickers: dict[str, int], seed: int = 7):
    """Deterministic multi-ticker daily OHLC, deliberately shuffled (not date-ordered)."""
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(seed)
    frames = []
    for ticker, days in tickers.items():
        dates = pd.bdate_range("2026-01-01", periods=days)
        close = 1000 + np.cumsum(rng.normal(0, 15, days))
        open_ = close + rng.normal(0, 8, days)
        high = np.maximum(open_, close) + rng.uniform(0, 10, days)
        low = np.minimum(open_, close) - rng.uniform(0, 10, days)
        frames.append(pd.DataFrame({"Symbol": ticker, "Date": dates.date, "Open": open_, "High": high, "Low": low,
                                    "Close": close}))
    frame = pd.concat(frames, ignore_index=True)
    return frame.sample(frac=1.0, random_state=seed).reset_index(drop=True)
