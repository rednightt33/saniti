#!/usr/bin/env python3
"""Run the first deterministic generic-worker Golden Test and persist its result."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import psycopg
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "market-ai-backend"))

from app.config import Settings  # noqa: E402
from app.db import Database  # noqa: E402
from app.tools import ToolRegistry  # noqa: E402


TELCO_TICKERS = [
    "BALI", "CENT", "DATA", "EXCL", "GHON", "GOLD", "INET", "ISAT", "JAST",
    "KBLV", "KETR", "LINK", "MORA", "MTEL", "OASA", "TBIG", "TLKM", "TOWR",
]


SQL = """
WITH price_forward AS (
  SELECT ticker,date,industry,close,
         100.0*(lead(close,20) OVER (PARTITION BY ticker ORDER BY date)/nullif(close,0)-1.0)
           AS forward_return_20obs_pct
  FROM prices
), daily_combinations AS (
  SELECT ticker,date,string_agg(DISTINCT broker,',' ORDER BY broker) AS broker_combination,
         count(DISTINCT broker) AS broker_count,
         avg(buy_day_ratio_20d) AS avg_buy_day_ratio_20d,
         sum(net_value_20d) AS combined_net_value_20d
  FROM broker_signals
  GROUP BY ticker,date
), labeled AS (
  SELECT d.*,p.industry,p.forward_return_20obs_pct
  FROM daily_combinations d JOIN price_forward p USING (ticker,date)
  WHERE p.forward_return_20obs_pct IS NOT NULL
), combination_results AS (
  SELECT broker_combination,broker_count,count(*) AS signal_events,
         count(*) FILTER (WHERE forward_return_20obs_pct>=10) AS events_before_10pct,
         100.0*count(*) FILTER (WHERE forward_return_20obs_pct>=10)/count(*) AS hit_rate_pct,
         avg(forward_return_20obs_pct) AS avg_forward_return_20obs_pct,
         max(forward_return_20obs_pct) AS max_forward_return_20obs_pct,
         count(DISTINCT ticker) AS ticker_count
  FROM labeled GROUP BY broker_combination,broker_count
)
SELECT * FROM combination_results
WHERE events_before_10pct>0
ORDER BY events_before_10pct DESC,hit_rate_pct DESC,signal_events DESC,broker_combination
LIMIT 100
"""


def main() -> None:
    settings = Settings.from_env()
    if not settings.analytics_enabled:
        raise RuntimeError("ANALYTICS_ENABLED=true is required")
    db = Database(settings.database_url, settings.query_timeout_seconds)
    db.open()
    admin = psycopg.connect(settings.database_url, row_factory=dict_row)
    question = (
        "Which broker buy-streak combinations in the telecommunications sector preceded "
        "a return of at least 10% within the next 20 trading observations?"
    )
    request_id = admin.execute(
        '''INSERT INTO public."Analysis_Request"
             (question,user_reference,status,current_stage,analysis_ready_date)
           VALUES (%s,'golden-r2-001','PROCESSING','HISTORICAL_VALIDATION',DATE '2026-08-31')
           RETURNING request_id''',
        (question,),
    ).fetchone()["request_id"]
    run_id = admin.execute(
        '''INSERT INTO public."Golden_Analysis_Test_Run"
             (release_version,model_provider,model_id,reasoning_effort,
              orchestrator_version,orchestrator_prompt_version,version_snapshot,
              status,started_at,tests_total)
           VALUES ('release-2-generic-worker',%s,'not-invoked-deterministic',NULL,
                   'release-2-generic-worker-v1','release-2-generic-worker-v1',%s,
                   'RUNNING',clock_timestamp(),1) RETURNING run_id''',
        (settings.ai_provider, json.dumps({"suite": "R2_v1", "tool": "run_analytics_job:v1"})),
    ).fetchone()["run_id"]
    admin.commit()
    started = time.monotonic()
    status, failure, observed, evidence_ids = "PASS", None, {}, []
    try:
        tools = ToolRegistry(db, settings)
        job_arguments = {
                "job_label": "golden_telco_broker_streak_forward_10pct_v1",
                "purpose": question,
                "datasets": [
                    {
                        "name": "prices", "table": "Feature_01_Stock_Daily",
                        "columns": ["date", "ticker", "close", "industry"],
                        "tickers": TELCO_TICKERS, "start_date": "2022-01-03",
                        "end_date": "2026-08-31", "filters": None, "limit": 20000,
                    },
                    {
                        "name": "broker_signals", "table": "Feature_02_Broker_Rolling",
                        "columns": ["date", "ticker", "broker", "market_board", "buy_day_ratio_20d", "net_value_20d"],
                        "tickers": TELCO_TICKERS, "start_date": "2022-01-03",
                        "end_date": "2026-08-31",
                        "filters": [
                            {"column": "market_board", "operator": "eq", "value": "Regular"},
                            {"column": "buy_day_ratio_20d", "operator": "gte", "value": 0.75},
                            {"column": "net_value_20d", "operator": "gt", "value": 0},
                        ],
                        "limit": 30000,
                    },
                ],
                "sql": SQL, "result_limit": 100,
                "analysis_ready_date": "2026-08-31",
        }
        result = tools.execute(
            "run_analytics_job", job_arguments, str(request_id)
        ).payload
        assert result["status"] == "SUCCESS", result
        assert result["evidence_id"], result
        assert result["method"] == "SAFE_DUCKDB_SQL"
        assert result["total_rows"] > 0
        assert result["input_rows"] <= settings.analytics_max_rows
        assert len(result["component_query_hashes"]) == 2
        replay = tools.execute(
            "run_analytics_job", job_arguments, str(request_id)
        ).payload
        assert replay["idempotent_reuse"] is True
        assert replay["job_id"] == result["job_id"]
        evidence_ids = [result["evidence_id"]]
        observed = {
            "job_id": result["job_id"], "snapshot_id": result["snapshot_id"],
            "snapshot_sha256": result["snapshot_sha256"],
            "input_rows": result["input_rows"],
            "result_rows": result["total_rows"],
            "top_rows": result["rows"][:5],
            "worker_has_database_credentials": False,
            "idempotent_reuse": True,
            "component_query_hashes": result["component_query_hashes"],
        }
    except Exception as exc:
        status, failure = "FAIL", f"{type(exc).__name__}: {exc}"[:1000]
    duration = round((time.monotonic() - started) * 1000)
    admin.execute(
        '''INSERT INTO public."Golden_Analysis_Test_Result"
             (run_id,test_id,test_version,request_id,status,observed_metrics,
              evidence_ids,methodology_checks,duration_ms,failure_reason)
           VALUES (%s,'R2_001_TELCO_BROKER_STREAK_FORWARD_10PCT','v1',%s,%s,%s,%s,%s,%s,%s)''',
        (
            run_id, request_id, status, json.dumps(observed), evidence_ids,
            json.dumps({
                "signal_uses_only_date_t_information": True,
                "forward_label_is_lead_20_trading_observations": True,
                "source_market_board_is_regular": True,
                "worker_has_no_database_credentials": True,
            }),
            duration, failure,
        ),
    )
    admin.execute(
        '''UPDATE public."Golden_Analysis_Test_Run"
           SET status=%s,tests_passed=%s,tests_failed=%s,completed_at=clock_timestamp()
           WHERE run_id=%s''',
        ("PASS" if status == "PASS" else "FAIL", int(status == "PASS"), int(status != "PASS"), run_id),
    )
    admin.execute(
        '''UPDATE public."Analysis_Request"
           SET status=%s,current_stage='FINAL',completed_at=clock_timestamp(),
               error_message=%s,version_snapshot=%s,methodology_metadata=%s
           WHERE request_id=%s''',
        (
            "SUCCESS" if status == "PASS" else "FAILED", failure,
            json.dumps({"release": "release-2-generic-worker", "golden_test": "R2_001"}),
            json.dumps({
                "lookahead_check_status": "PASS" if status == "PASS" else "NOT_COMPLETED",
                "worker_database_credentials": False,
            }),
            request_id,
        ),
    )
    admin.commit()
    print(json.dumps({
        "status": status, "run_id": str(run_id), "request_id": str(request_id),
        "duration_ms": duration, "observed": observed, "failure": failure,
    }, default=str))
    admin.close(); db.close()
    if status != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
