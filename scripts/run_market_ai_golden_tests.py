#!/usr/bin/env python3
"""Run deterministic Release 1B safety/query golden tests and persist results."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import psycopg
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "market-ai-backend"))

from app.compaction import compact_result  # noqa: E402
from app.config import Settings  # noqa: E402
from app.db import Database  # noqa: E402
from app.tools import ToolError, ToolRegistry  # noqa: E402


def role_url(url: str, role: str) -> str:
    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    query.append(("options", f"-c role={role}"))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query, quote_via=quote), parts.fragment))


def expect_rejected(callback) -> dict:
    try:
        callback()
    except ToolError as exc:
        return {"rejected": True, "reason": str(exc)}
    raise AssertionError("Expected ToolError rejection")


def main() -> None:
    admin_url = os.environ.get("DATABASE_URL", "")
    if not admin_url:
        raise RuntimeError("DATABASE_URL is required")
    os.environ["DATABASE_URL"] = role_url(admin_url, "market_ai_reader")
    settings = Settings.from_env(require_runtime_secrets=False)
    reader_db = Database(settings.database_url, settings.query_timeout_seconds)
    reader_db.open()
    admin = psycopg.connect(admin_url, row_factory=dict_row)
    tools = ToolRegistry(reader_db, settings)
    run_id = admin.execute(
        '''INSERT INTO public."Golden_Analysis_Test_Run"
             (release_version,model_provider,model_id,reasoning_effort,
              orchestrator_version,orchestrator_prompt_version,version_snapshot,
              status,started_at)
           VALUES ('release-1b','openai','not-invoked-deterministic',NULL,
                   'release-1b-v1','release-1b-v1',%s,'RUNNING',clock_timestamp())
           RETURNING run_id''',
        (json.dumps({"feature_catalog": "v1", "tool_catalog": "v1", "suite": "R1B_v1"}),),
    ).fetchone()["run_id"]
    admin.commit()
    start_date, end_date = "2026-08-01", "2026-08-31"
    base_query = {
        "table": "Feature_01_Stock_Daily", "columns": ["date", "ticker", "return_1d_pct"],
        "tickers": ["BBCA"], "start_date": start_date, "end_date": end_date,
        "filters": None, "order_by": [{"column": "date", "direction": "asc"}], "limit": 100,
    }

    def cases() -> dict[str, object]:
        return {
            "R1B_001_FEATURE_DISCOVERY": lambda: {"matches": tools.execute("find_features", {"search_text": "return", "tables": ["Feature_01_Stock_Daily"], "limit": 20}, "golden").payload["total_rows"]},
            "R1B_002_TABLE_DISCOVERY": lambda: {"tables": [r["table_name"] for r in tools.execute("list_feature_tables", {"include_columns": False}, "golden").payload["rows"]]},
            "R1B_003_COMMON_READINESS": lambda: tools.execute("check_data_freshness", {"tables": ["Feature_01_Stock_Daily", "Feature_02_Broker_Rolling", "Feature_03_Stock_Broker_Daily"]}, "golden").payload,
            "R1B_004_BBCA_RETRIEVAL": lambda: {"rows": tools.execute("query_features", base_query, "golden").payload["total_rows"]},
            "R1B_005_RAW_COLUMN_DENIAL": lambda: expect_rejected(lambda: tools.execute("validate_query_request", {**base_query, "columns": ["raw_price"]}, "golden")),
            "R1B_006_UNBOUNDED_DENIAL": lambda: expect_rejected(lambda: tools.execute("validate_query_request", {**base_query, "tickers": None, "start_date": None, "end_date": None}, "golden")),
            "R1B_007_TICKER_LIMIT": lambda: expect_rejected(lambda: tools.execute("validate_query_request", {**base_query, "tickers": [f"T{i}" for i in range(21)]}, "golden")),
            "R1B_008_QUALITY_EXTREMES": lambda: tools.execute("check_data_quality", {"table": "Feature_01_Stock_Daily", "tickers": ["BBCA"], "start_date": "2026-01-01", "end_date": end_date}, "golden").payload,
            "R1B_009_FEATURE3_GROUPING": lambda: tools.execute("aggregate_features", {"table": "Feature_03_Stock_Broker_Daily", "group_by": ["market_board"], "metrics": [{"column": "total_buy_value", "aggregation": "SUM"}], "tickers": ["BBCA"], "start_date": start_date, "end_date": end_date, "limit": 10}, "golden").payload,
            "R1B_010_QUERY_HASH": lambda: {"equal": tools.execute("estimate_query_size", base_query, "golden").query_hash == tools.execute("query_features", base_query, "golden").query_hash},
            "R1B_011_POINT_IN_TIME_WARNING": lambda: tools.execute("get_feature_definition", {"features": [{"table": "Feature_02_Broker_Rolling", "column": "broker_classification"}]}, "golden").payload,
            "R1B_012_LLM_COMPACTION": lambda: {"semantic": compact_result({"rows": [{"x": i, "text": "z" * 500} for i in range(500)]}, max_rows=20, max_bytes=2000, max_tokens=600)[0]["selection"]["method"]},
            "R1B_013_PROGRESSIVE_EXPOSURE": lambda: {"initial_core_only": "QUERY" not in tools.STAGE_FAMILIES["DISCOVERY"], "query_expandable": "QUERY" in tools.STAGE_FAMILIES["SCREENING"]},
            "R1B_014_WORKER_FAMILY_DENIAL": inactive_worker_tools,
            "R1B_015_LEAST_PRIVILEGE": privilege_check,
        }

    def inactive_worker_tools() -> dict:
        row = admin.execute(
            '''SELECT count(*)::integer AS count FROM public."Tool_Catalog"
               WHERE requires_analytics_worker AND is_active'''
        ).fetchone()
        assert row["count"] == 0
        return {"active_worker_tools": 0}

    def privilege_check() -> dict:
        row = admin.execute(
            '''SELECT
               has_table_privilege('market_ai_reader','public."Feature_01_Stock_Daily"','SELECT')
               AND has_table_privilege('market_ai_reader','public."Feature_02_Broker_Rolling"','SELECT')
               AND has_table_privilege('market_ai_reader','public."Feature_03_Stock_Broker_Daily"','SELECT') AS feature_select,
               has_table_privilege('market_ai_reader','public."Price_Stock_Indonesia_IDX"','SELECT')
               OR has_table_privilege('market_ai_reader','public."IDX_Broker_Summary"','SELECT') AS raw_select'''
        ).fetchone()
        assert row["feature_select"] is True and row["raw_select"] is False
        return dict(row)

    passed = failed = 0
    definitions = admin.execute(
        '''SELECT test_id,version FROM public."Golden_Analysis_Test"
           WHERE is_active AND version='v1' AND test_id LIKE 'R1B_%' ORDER BY test_id'''
    ).fetchall()
    case_map = cases()
    for definition in definitions:
        test_id = definition["test_id"]
        started = time.monotonic()
        status, metrics, reason = "PASS", {}, None
        try:
            metrics = case_map[test_id]()
            # Assertions that are clearer after generic handler execution.
            if test_id == "R1B_001_FEATURE_DISCOVERY": assert metrics["matches"] >= 1
            if test_id == "R1B_002_TABLE_DISCOVERY": assert len(metrics["tables"]) >= 3
            if test_id == "R1B_003_COMMON_READINESS": assert metrics["analysis_ready_date"] == "2026-08-31"
            if test_id == "R1B_004_BBCA_RETRIEVAL": assert metrics["rows"] >= 1
            if test_id == "R1B_008_QUALITY_EXTREMES": assert metrics["classification"] in {"PASS", "WARNING"}
            if test_id == "R1B_009_FEATURE3_GROUPING": assert metrics["total_rows"] >= 1
            if test_id == "R1B_010_QUERY_HASH": assert metrics["equal"] is True
            if test_id == "R1B_011_POINT_IN_TIME_WARNING": assert metrics["rows"][0]["historical_metadata_warning"]
            if test_id == "R1B_012_LLM_COMPACTION": assert metrics["semantic"] == "semantic_summary"
            if test_id == "R1B_013_PROGRESSIVE_EXPOSURE": assert all(metrics.values())
            passed += 1
        except Exception as exc:
            status, reason = "FAIL", f"{type(exc).__name__}: {exc}"[:1000]
            failed += 1
        duration = round((time.monotonic() - started) * 1000)
        admin.execute(
            '''INSERT INTO public."Golden_Analysis_Test_Result"
                 (run_id,test_id,test_version,status,observed_metrics,duration_ms,failure_reason)
               VALUES (%s,%s,%s,%s,%s,%s,%s)''',
            (run_id, test_id, definition["version"], status, json.dumps(metrics, default=str), duration, reason),
        )
        admin.commit()
    final_status = "PASS" if failed == 0 and passed == len(definitions) else "FAIL"
    admin.execute(
        '''UPDATE public."Golden_Analysis_Test_Run" SET status=%s,tests_total=%s,
             tests_passed=%s,tests_failed=%s,completed_at=clock_timestamp() WHERE run_id=%s''',
        (final_status, len(definitions), passed, failed, run_id),
    )
    admin.commit()
    print(json.dumps({"status": final_status, "run_id": str(run_id), "total": len(definitions), "passed": passed, "failed": failed}))
    reader_db.close()
    admin.close()
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
