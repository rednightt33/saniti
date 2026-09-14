from __future__ import annotations

import gzip
import hashlib
import json
import os

os.environ.setdefault("MARKET_AI_BACKEND_URL", "http://backend")
os.environ.setdefault("ANALYTICS_WORKER_API_KEY", "test-token")

import pytest

from worker import execute_job, validate_sql


def test_sql_policy_allows_window_query_and_blocks_external_access() -> None:
    sql = validate_sql(
        "WITH x AS (SELECT ticker, lag(value) OVER (PARTITION BY ticker ORDER BY date) p FROM prices) SELECT * FROM x",
        {"prices"},
    )
    assert sql.startswith("WITH")
    with pytest.raises(ValueError, match="Forbidden"):
        validate_sql("SELECT * FROM read_csv('https://example.com/a.csv')", {"prices"})
    with pytest.raises(ValueError, match="Only SELECT"):
        validate_sql("DROP TABLE prices", {"prices"})


def test_executes_generic_snapshot_query() -> None:
    package = {
        "datasets": [{
            "name": "prices", "columns": ["ticker", "value"], "row_count": 3,
            "rows": [{"ticker": "A", "value": 1}, {"ticker": "A", "value": 2}, {"ticker": "B", "value": 7}],
        }]
    }
    compressed = gzip.compress(json.dumps(package).encode(), mtime=0)
    claim = {
        "snapshot_sha256": hashlib.sha256(compressed).hexdigest(),
        "snapshot_compressed_bytes": len(compressed),
        "analysis_spec": {"sql": "SELECT ticker,sum(value) total FROM prices GROUP BY ticker ORDER BY ticker"},
        "limits": {"runtime_seconds": 5, "memory_mb": 128, "result_rows": 10, "result_bytes": 10000},
    }
    result = execute_job(claim, compressed)
    assert result["row_count"] == 2
    assert result["rows"][0] == {"ticker": "A", "total": 3.0}

