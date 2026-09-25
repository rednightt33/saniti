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


# The catalog source contracts the Governor attaches to every dataset (AI_table_catalog subject metadata, migration
# 20260925_001); the sandbox has no table dictionary of its own.
def _contract(table: str, grain: list[str], entity: str, time: str | None, entity_type: str = "STOCK",
              asset_type: str | None = "IDX_EQUITY") -> dict:
    frequencies = ["1D"] if time else ["STATIC"]
    return {"table": table, "grain": grain, "grain_description": " x ".join(grain), "entity_column": entity,
            "time_column": time, "supported_frequencies": frequencies, "frequency": frequencies[0],
            "time_semantics": "Asia/Jakarta exchange trading date" if time else "Current-state reference data",
            "data_domain": "MARKET", "entity_type": entity_type, "asset_type": asset_type,
            "subject_metadata_status": "INFERRED", "catalog_table_sha256": "0" * 63 + str(len(table) % 10)}


SOURCE_CONTRACTS = {
    "Price_Stock_Indonesia_IDX": _contract("Price_Stock_Indonesia_IDX", ["ticker", "date"], "ticker", "date"),
    "Feature_01_Stock_Daily": _contract("Feature_01_Stock_Daily", ["ticker", "date"], "ticker", "date"),
    "Feature_02_Broker_Rolling": _contract("Feature_02_Broker_Rolling",
                                           ["ticker", "market_board", "broker", "investor_type", "date"], "ticker",
                                           "date"),
    "Feature_03_Stock_Broker_Daily": _contract("Feature_03_Stock_Broker_Daily", ["ticker", "market_board", "date"],
                                               "ticker", "date"),
    "IDX_Broker_Summary": _contract("IDX_Broker_Summary", ["Date", "Symbol", "Broker", "Investor Type",
                                                           "Market Board"], "Symbol", "Date"),
    "IDX_Stock_Universe": _contract("IDX_Stock_Universe", ["Ticker"], "Ticker", None),
    "IDX_Broker_Profile": _contract("IDX_Broker_Profile", ["broker_code"], "broker_code", None, "BROKER", None),
}


def _columns(spec: dict[str, tuple[str, bool, bool]]) -> dict[str, dict]:
    """{column: (data_type, filter_allowed, group_by_allowed)} -> catalog contract columns."""
    numeric = ("numeric", "double precision", "bigint", "integer")
    return {name: {"data_type": kind, "semantic_type": "MEASURE" if kind in numeric else "DIMENSION", "unit": None,
                   "filter_allowed": filt, "group_by_allowed": group,
                   "allowed_aggregations": ["AVG", "MAX", "MIN", "SUM"] if kind in numeric else ["COUNT",
                                                                                                "COUNT_DISTINCT"]}
            for name, (kind, filt, group) in spec.items()}


def _catalog_table(contract: dict, description: str) -> dict:
    return {"table_name": contract["table"], "description": description, "grain": contract["grain_description"],
            "primary_key_columns": contract["grain"], "entity_column": contract["entity_column"],
            "time_column": contract["time_column"], "data_domain": contract["data_domain"],
            "entity_type": contract["entity_type"], "asset_type": contract["asset_type"],
            "supported_frequencies": contract["supported_frequencies"], "time_semantics": contract["time_semantics"],
            "subject_metadata_status": "INFERRED", "catalog_table_sha256": contract["catalog_table_sha256"]}


SOURCE_CONTRACTS["Macro_Series_Monthly"] = _contract("Macro_Series_Monthly", ["series_id", "period"], "series_id",
                                                     "period", "SERIES", None)
SOURCE_CONTRACTS["Macro_Series_Monthly"].update(data_domain="MACRO", supported_frequencies=["1M"], frequency="1M")
CATALOG = {
    "catalog_version": "ai_catalog_contract/v1", "subject_metadata": True,
    "tables": {name: _catalog_table(SOURCE_CONTRACTS[name], "Synthetic catalog table.") for name in (
        "Price_Stock_Indonesia_IDX", "IDX_Stock_Universe", "IDX_Broker_Profile", "Feature_01_Stock_Daily",
        "Macro_Series_Monthly")},
    "columns": {
        "Price_Stock_Indonesia_IDX": _columns({"ticker": ("text", True, True), "date": ("date", True, True),
                                               "open": ("numeric", True, False), "high": ("numeric", True, False),
                                               "low": ("numeric", True, False), "close": ("numeric", True, False),
                                               "volume": ("numeric", True, False),
                                               "query_date": ("date", False, False)}),
        "IDX_Stock_Universe": _columns({"Ticker": ("text", True, True), "Sector": ("text", True, True),
                                        "Industry": ("text", True, True), "Name": ("text", True, False),
                                        "Shares": ("bigint", True, False)}),
        "IDX_Broker_Profile": _columns({"broker_code": ("text", True, True), "broker_name": ("text", True, False)}),
        "Feature_01_Stock_Daily": _columns({"ticker": ("text", True, True), "date": ("date", True, True),
                                            "return_20d_pct": ("numeric", True, False)}),
        "Macro_Series_Monthly": _columns({"series_id": ("text", True, True), "period": ("date", True, True),
                                          "value": ("numeric", True, False)}),
    },
    "relationships": [
        {"relationship_id": 1, "left_table": "Price_Stock_Indonesia_IDX", "left_columns": ["ticker", "date"],
         "right_table": "Feature_01_Stock_Daily", "right_columns": ["ticker", "date"], "relationship_type": "ONE_TO_ONE",
         "temporal_rule": "Exact trading date", "safe_output_grain": "date x ticker", "requires_preaggregation": False,
         "is_allowed": True, "version": "v1"},
        {"relationship_id": 2, "left_table": "IDX_Stock_Universe", "left_columns": ["Ticker"],
         "right_table": "Price_Stock_Indonesia_IDX", "right_columns": ["ticker"], "relationship_type": "ONE_TO_MANY",
         "temporal_rule": "Current-state reference metadata", "safe_output_grain": "date x ticker",
         "requires_preaggregation": False, "is_allowed": True, "version": "v1"},
    ],
    "catalog_sha256": "c" * 64,
}


def catalog_subset(tables: list[str]) -> dict:
    found = [t for t in tables if t in CATALOG["tables"]]
    return {**CATALOG, "tables": {t: CATALOG["tables"][t] for t in found},
            "columns": {t: CATALOG["columns"][t] for t in found},
            "relationships": [r for r in CATALOG["relationships"] if r["left_table"] in found or r["right_table"] in found],
            "unknown_tables": [t for t in tables if t not in CATALOG["tables"]]}


class FakeGovernor:
    """Answers /v1/datasets/{id}/access like market-sql-governor, granting file:// URLs to local Parquet."""

    PATH = re.compile(r"^/v1/datasets/([^/]+)/access$")

    def __init__(self, root: Path) -> None:
        self.root = root / "governor"
        self.root.mkdir(parents=True)
        self.datasets: dict[str, dict] = {}
        self.calls: list[dict] = []
        self.checksum_override: dict[str, str] = {}
        self.catalog_requests: list[dict] = []

    FRIENDLY = {"double": "float64", "float": "float32", "date32[day]": "date", "timestamp[us]": "timestamp",
                "timestamp[ns]": "timestamp", "bool": "boolean", "string": "string", "large_string": "string",
                "int64": "int64", "int32": "int32"}

    def add(self, data, *, expired: bool = False, numeric: tuple[str, ...] = (), completeness: str = "COMPLETE",
            dataset_id: str | None = None, source_table: str = "Price_Stock_Indonesia_IDX",
            requested_from: str | None = None, requested_to: str | None = None, entities: list[str] | None = None,
            missing: list[str] | None = None, created_at: datetime | None = None,
            aggregation: dict[str, str] | None = None, source_columns: dict[str, str] | None = None,
            units: dict[str, str] | None = None, lineage: dict | None = None,
            executed_scope: dict | None = None, source_contracts: dict | None = None) -> str:
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
                "validator_manifest": {
                    "manifest_version": "v2", "dataset_id": dataset_id, "lineage": lineage,
                    "executed_scope": executed_scope,
                    "source_contracts": source_contracts if source_contracts is not None else (
                        {source_table: SOURCE_CONTRACTS[source_table]} if source_table in SOURCE_CONTRACTS else {}),
                    "query_hash": "q" * 64, "request_sha256": (lineage or {}).get("request_sha256", "r" * 64),
                    "checksum_sha256": hashlib.sha256(raw).hexdigest(), "requested_entities": entities,
                    "entities_present": present if entity_column else None,
                    "entities_present_count": len(present) if entity_column else None},
            }}
        return dataset_id

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append({"path": request.url.path, "authorization": request.headers.get("authorization")})
        if request.headers.get("authorization") != f"Bearer {ACCESS_KEY}":
            return httpx.Response(401, json={"detail": "Unauthorized"})
        if request.method == "POST" and request.url.path == "/v1/catalog/contract":
            import json as _json

            body = _json.loads(request.content)
            self.catalog_requests.append(body)
            return httpx.Response(200, json=catalog_subset(body["tables"]))
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
