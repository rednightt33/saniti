from __future__ import annotations

import gzip
import hashlib
import json
import os

os.environ.setdefault("MARKET_AI_BACKEND_URL", "http://backend")
os.environ.setdefault("QUERY_SANDBOX_API_KEY", "test-token")

import pytest

from worker import execute_job, validate_sql


def test_query_sandbox_executes_only_its_own_safe_job() -> None:
    package = {
        "datasets": [{
            "name": "prices", "columns": ["ticker", "value"], "row_count": 2,
            "rows": [{"ticker": "A", "value": 1}, {"ticker": "A", "value": 2}],
        }]
    }
    compressed = gzip.compress(json.dumps(package).encode(), mtime=0)
    claim = {
        "execution_class": "QUERY_SANDBOX",
        "snapshot_sha256": hashlib.sha256(compressed).hexdigest(),
        "snapshot_compressed_bytes": len(compressed),
        "analysis_spec": {
            "method": "SAFE_DUCKDB_SQL",
            "sql": "SELECT ticker,sum(value) total FROM prices GROUP BY ticker",
        },
        "limits": {"runtime_seconds": 5, "memory_mb": 128, "result_rows": 10, "result_bytes": 10000},
    }
    result = execute_job(claim, compressed)
    assert result["rows"] == [{"ticker": "A", "total": 3.0}]


def test_query_sandbox_rejects_external_and_statistical_jobs() -> None:
    with pytest.raises(ValueError, match="Forbidden"):
        validate_sql("SELECT * FROM read_parquet('x')", {"prices"})
    with pytest.raises(ValueError, match="wrong execution class"):
        execute_job({"execution_class": "STATISTICAL_VALIDATION"}, b"")
