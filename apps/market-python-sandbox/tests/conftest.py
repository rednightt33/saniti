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

    FRIENDLY = {"double": "float64", "float": "float32", "date32[day]": "date", "timestamp[us]": "timestamp",
                "timestamp[ns]": "timestamp", "bool": "boolean", "string": "string", "large_string": "string",
                "int64": "int64", "int32": "int32"}

    def add(self, data, *, expired: bool = False, numeric: tuple[str, ...] = (), completeness: str = "COMPLETE",
            dataset_id: str | None = None, source_table: str = "Price_Stock_Indonesia_IDX",
            requested_from: str | None = None, requested_to: str | None = None, entities: list[str] | None = None,
            missing: list[str] | None = None, created_at: datetime | None = None,
            aggregation: dict[str, str] | None = None, source_columns: dict[str, str] | None = None,
            units: dict[str, str] | None = None) -> str:
        dataset_id = dataset_id or f"ds_{uuid.uuid4().hex[:24]}"
        table = data if isinstance(data, pa.Table) else pa.Table.from_pandas(data, preserve_index=False)
        path = self.root / f"{dataset_id}.parquet"
        pq.write_table(table, path, compression="zstd")
        raw = path.read_bytes()
        now = created_at or datetime.now(timezone.utc)
        columns = [{"name": n, "type": self.FRIENDLY.get(str(t), str(t)), "source_type": None,
                    "source_table": source_table, "source_column": (source_columns or {}).get(n, n),
                    "aggregation": (aggregation or {}).get(n), "unit": (units or {}).get(n)}
                   for n, t in zip(table.column_names, table.schema.types)]
        date_column = next((c["name"] for c in columns if c["type"] == "date"), None)
        entity_column = "ticker" if "ticker" in table.column_names else None
        dates = table.column(date_column).to_pylist() if date_column else []
        present = sorted(set(table.column(entity_column).to_pylist())) if entity_column else []
        self.datasets[dataset_id] = {
            "path": path, "expired": expired, "manifest": {
                "dataset_id": dataset_id, "format": "PARQUET", "source_tables": [source_table],
                "query_id": "qry_test", "row_count": table.num_rows, "column_count": table.num_columns,
                "byte_count": len(raw), "columns": columns,
                "requested_scope": {"date_range": {"from": requested_from, "to": requested_to},
                                    "entities": entities, "entities_count": len(entities) if entities else None},
                "actual_date_range": {"from": str(min(dates)), "to": str(max(dates))} if dates else None,
                "entities_present_count": len(present) if entity_column else None,
                "missing_entities": missing or [], "missing_entities_count": len(missing or []),
                "completeness_status": completeness if not missing else "MISSING_REQUESTED_ENTITIES",
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
        service.datasets_governor = governor  # lets tests look up the fake manifests
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


def price_frame(tickers: dict[str, tuple[str, int]], seed: int = 11):
    """Deterministic daily closes per ticker: {ticker: (first business day, number of days)}, shuffled."""
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(seed)
    frames = []
    for ticker, (start, days) in tickers.items():
        dates = pd.bdate_range(start, periods=days)
        close = 1000 + np.cumsum(rng.normal(0, 15, days))
        frames.append(pd.DataFrame({"ticker": ticker, "date": dates.date, "close": close,
                                    "volume": rng.integers(1000, 100000, days).astype(float)}))
    frame = pd.concat(frames, ignore_index=True)
    return frame.sample(frac=1.0, random_state=seed).reset_index(drop=True)


def zscore_spec(*, window: int = 20, universe: str = "ALL_IN_SOURCE", tickers: list[str] | None = None,
                period: dict | None = None, output_grain: str = "ENTITY_DATE", selection: list | None = None,
                question: str = "Calculate rolling 20-day z-scores for all IDX stocks over the last three months.",
                window_provenance: str = "USER_EXPLICIT", exclusions: list | None = None) -> dict:
    return {
        "question": question,
        "universe": {"type": universe, "tickers": tickers, "provenance": "USER_EXPLICIT",
                     "default_id": "DEFAULT_UNIVERSE_ALL_IN_SOURCE" if universe == "ALL_IN_SOURCE" else None},
        "analysis_period": period or {"mode": "TRAILING", "unit": "MONTH", "count": 3, "provenance": "USER_EXPLICIT",
                                      "default_id": "DEFAULT_TRAILING_CALENDAR_WINDOW"},
        "frequency": {"value": "1D", "provenance": "APPROVED_DEFAULT", "default_id": "DEFAULT_FREQUENCY_DAILY"},
        "inputs": [{"name": "prices", "source_table": "Price_Stock_Indonesia_IDX", "entity_column": "ticker",
                    "date_column": "date", "columns": ["ticker", "date", "close"]}],
        "calculations": [{"id": "z20", "method": "ROLLING_ZSCORE", "dataset": "prices", "columns": ["close"],
                          "params": [{"name": "window", "value": window, "provenance": window_provenance}],
                          "output_column": f"zscore_{window}", "provenance": "USER_EXPLICIT"}],
        "outputs": [{"name": "zscores", "grain": output_grain,
                     "coverage": "SELECTION" if selection else "FULL", "calculations": ["z20"],
                     "selection": selection}],
        "exclusion_rules": exclusions or [],
    }
