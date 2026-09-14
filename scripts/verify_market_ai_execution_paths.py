#!/usr/bin/env python3
"""Run one live built-in, query-sandbox, and statistical-validation acceptance."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "market-ai-backend"))

from app.config import Settings  # noqa: E402
from app.db import Database  # noqa: E402
from app.tools import ToolRegistry  # noqa: E402


def public_database_url(url: str, host: str, port: int) -> str:
    parsed = urlsplit(url)
    credentials = parsed.netloc.rsplit("@", 1)[0]
    return urlunsplit((parsed.scheme, f"{credentials}@{host}:{port}", parsed.path, parsed.query, ""))


def create_request(db: Database, question: str) -> str:
    with db.connection() as connection, connection.transaction():
        row = connection.execute(
            '''INSERT INTO public."Analysis_Request" (question,user_reference)
               VALUES (%s,'three-path-live-acceptance') RETURNING request_id''',
            (question,),
        ).fetchone()
    return str(row["request_id"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args()
    os.environ["DATABASE_URL"] = public_database_url(
        os.environ["DATABASE_URL"], args.host, args.port
    )
    settings = Settings.from_env()
    database = Database(settings.database_url, settings.query_timeout_seconds)
    database.open()
    tools = ToolRegistry(database, settings)
    try:
        direct_request = create_request(database, "Latest BBCA Feature 01 observation")
        direct_route = tools.execute(
            "route_analysis",
            {"required_operations": ["FILTER"], "candidate_tables": ["Feature_01_Stock_Daily"],
             "reason": "One bounded ticker/date retrieval"},
            direct_request,
        )
        direct = tools.execute(
            "query_features",
            {"table": "Feature_01_Stock_Daily", "columns": ["date", "ticker", "close"],
             "tickers": ["BBCA"], "start_date": "2026-08-31", "end_date": "2026-08-31",
             "filters": None, "order_by": None, "limit": 5},
            direct_request,
        )
        assert direct_route.payload["selected_path"] == "EXISTING_TOOL"
        assert direct.payload["total_rows"] == 1

        sandbox_request = create_request(database, "Describe BBCA raw August price activity")
        sandbox_route = tools.execute(
            "route_analysis",
            {"required_operations": ["CUSTOM_TRANSFORM"],
             "candidate_tables": ["Price_Stock_Indonesia_IDX"],
             "reason": "Custom summary over controlled raw OHLCV"},
            sandbox_request,
        )
        sandbox = tools.execute(
            "run_query_sandbox",
            {
                "job_label": "accept_raw_bbca_august_summary",
                "purpose": "Summarize bounded raw BBCA closes and volume",
                "datasets": [{
                    "name": "prices", "table": "Price_Stock_Indonesia_IDX",
                    "columns": ["ticker", "date", "close", "volume"],
                    "date_column": "date", "ticker_column": "ticker", "tickers": ["BBCA"],
                    "start_date": "2026-08-01", "end_date": "2026-08-31",
                    "filters": None, "limit": 100,
                }],
                "sql": (
                    "SELECT ticker,count(*) AS observations,min(close) AS min_close,"
                    "max(close) AS max_close,avg(close) AS avg_close,sum(volume) AS total_volume "
                    "FROM prices GROUP BY ticker"
                ),
                "result_limit": 10, "analysis_ready_date": "2026-08-31",
            },
            sandbox_request,
        )
        assert sandbox_route.payload["selected_path"] == "QUERY_SANDBOX"
        assert sandbox.payload["status"] == "SUCCESS" and sandbox.payload["execution_class"] == "QUERY_SANDBOX"
        assert sandbox.payload["source_tables"] == ["Price_Stock_Indonesia_IDX"]

        statistical_request = create_request(database, "What followed positive BBCA days in August?")
        statistical_route = tools.execute(
            "route_analysis",
            {"required_operations": ["EVENT_STUDY"],
             "candidate_tables": ["Feature_01_Stock_Daily"],
             "reason": "Forward outcome requires statistical validation"},
            statistical_request,
        )
        statistical = tools.execute(
            "run_statistical_validation",
            {
                "job_label": "accept_bbca_positive_day_event_study",
                "purpose": "Measure next-five-observation returns after positive BBCA days",
                "datasets": [{
                    "name": "features", "table": "Feature_01_Stock_Daily",
                    "columns": ["ticker", "date", "close", "return_1d_pct"],
                    "date_column": "date", "ticker_column": "ticker", "tickers": ["BBCA"],
                    "start_date": "2026-06-01", "end_date": "2026-08-31",
                    "filters": None, "limit": 100,
                }],
                "method": "EVENT_STUDY",
                "sql": (
                    "WITH outcomes AS (SELECT ticker,date,return_1d_pct,"
                    "(lead(close,5) OVER (PARTITION BY ticker ORDER BY date)/nullif(close,0)-1)*100 "
                    "AS forward_5obs_pct FROM features) "
                    "SELECT count(*) FILTER (WHERE return_1d_pct>0 AND forward_5obs_pct IS NOT NULL) "
                    "AS event_count,avg(forward_5obs_pct) FILTER (WHERE return_1d_pct>0) "
                    "AS avg_forward_5obs_pct FROM outcomes"
                ),
                "result_limit": 10, "analysis_ready_date": "2026-08-31",
            },
            statistical_request,
        )
        assert statistical_route.payload["selected_path"] == "STATISTICAL_VALIDATION"
        assert statistical.payload["status"] == "SUCCESS"
        assert statistical.payload["execution_class"] == "STATISTICAL_VALIDATION"
        with database.query_transaction() as connection:
            job_audit = connection.execute(
                '''SELECT method,analysis_spec_json->>'method' AS spec_method,
                          result_json->>'method' AS result_method,worker_id
                   FROM public."Analytics_Job" WHERE job_id=%s''',
                (statistical.payload["job_id"],),
            ).fetchone()
        assert statistical.payload["method"] == "EVENT_STUDY_SQL", dict(job_audit)

        print(
            "PASS: built-in rows=1; query sandbox raw rows="
            f"{sandbox.payload['input_rows']} job={sandbox.payload['job_id']}; "
            "statistical Feature rows="
            f"{statistical.payload['input_rows']} job={statistical.payload['job_id']}"
        )
    finally:
        database.close()


if __name__ == "__main__":
    main()
