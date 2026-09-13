#!/usr/bin/env python3
"""Verify live market-AI catalogs, readiness, audit and least-privilege gates."""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

import psycopg
from psycopg.rows import dict_row


FEATURE_MIN_DATES = {
    "Feature_01_Stock_Daily": "2026-09-11",
    "Feature_02_Broker_Rolling": "2026-08-31",
    "Feature_03_Stock_Broker_Daily": "2026-08-31",
}


def assert_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise RuntimeError(f"{label}: expected {expected!r}, got {actual!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args()

    result: dict[str, Any] = {}
    connection = psycopg.connect(
        host=args.host,
        port=args.port,
        dbname=os.environ["PGDATABASE"],
        user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
        sslmode="require",
        application_name="market-ai-foundation-verification",
        row_factory=dict_row,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT count(*) FILTER (WHERE is_active) AS active,
                       count(*) FILTER (WHERE NOT is_active) AS inactive
                FROM public."Tool_Catalog"
                """
            )
            result["tools"] = cursor.fetchone()
            assert_equal(result["tools"], {"active": 18, "inactive": 11}, "tool counts")

            cursor.execute(
                """
                SELECT tool_name, execution_type,
                       tool_specific_limits->>'signals_finalization' AS signals_finalization
                FROM public."Tool_Catalog"
                WHERE tool_name IN ('record_evidence','complete_analysis') AND is_active
                ORDER BY tool_name
                """
            )
            stopping_tools = cursor.fetchall()
            assert_equal(
                stopping_tools,
                [
                    {
                        "tool_name": "complete_analysis",
                        "execution_type": "ORCHESTRATOR",
                        "signals_finalization": "true",
                    },
                    {
                        "tool_name": "record_evidence",
                        "execution_type": "BACKEND",
                        "signals_finalization": "false",
                    },
                ],
                "stopping tools",
            )
            result["stopping_tools"] = stopping_tools

            cursor.execute(
                """
                SELECT * FROM public.check_analysis_data_readiness(
                    ARRAY['Feature_01_Stock_Daily','Feature_02_Broker_Rolling',
                          'Feature_03_Stock_Broker_Daily'])
                ORDER BY feature_table
                """
            )
            readiness = cursor.fetchall()
            for row in readiness:
                assert_equal(row["status"], "READY", f"{row['feature_table']} readiness")
                safe_date = row["safe_analysis_date"].isoformat()
                if safe_date < FEATURE_MIN_DATES[row["feature_table"]]:
                    raise RuntimeError(
                        f"{row['feature_table']} safe date regressed below validated "
                        f"baseline {FEATURE_MIN_DATES[row['feature_table']]}: {safe_date}"
                    )
            result["readiness"] = readiness

            cursor.execute(
                """
                SELECT
                  has_table_privilege('market_ai_reader',
                    'public."Feature_01_Stock_Daily"','SELECT') AS f1,
                  has_table_privilege('market_ai_reader',
                    'public."Feature_02_Broker_Rolling"','SELECT') AS f2,
                  has_table_privilege('market_ai_reader',
                    'public."Feature_03_Stock_Broker_Daily"','SELECT') AS f3,
                  has_table_privilege('market_ai_reader',
                    'public."Price_Stock_Indonesia_IDX"','SELECT') AS raw_price,
                  has_table_privilege('market_ai_reader',
                    'public."IDX_Broker_Summary"','SELECT') AS raw_broker,
                  has_table_privilege('market_analytics_worker',
                    'public."Feature_01_Stock_Daily"','SELECT') AS worker_feature
                """
            )
            privileges = cursor.fetchone()
            assert_equal(
                privileges,
                {
                    "f1": True,
                    "f2": True,
                    "f3": True,
                    "raw_price": False,
                    "raw_broker": False,
                    "worker_feature": False,
                },
                "least privileges",
            )
            result["privileges"] = privileges

            cursor.execute(
                """
                SELECT
                  (SELECT count(*) FROM information_schema.columns
                   WHERE table_schema='public'
                     AND table_name LIKE 'Golden_Analysis_Test%') AS physical,
                  (SELECT count(*) FROM public."Column_Catalog"
                   WHERE table_schema='public'
                     AND table_name LIKE 'Golden_Analysis_Test%') AS cataloged
                """
            )
            golden = cursor.fetchone()
            assert_equal(golden, {"physical": 50, "cataloged": 50}, "golden coverage")
            result["golden_columns"] = golden

            cursor.execute("SAVEPOINT immutable_audit")
            cursor.execute("SET LOCAL ROLE market_ai_logger")
            cursor.execute(
                """
                INSERT INTO public."Analysis_Request" (question)
                VALUES ('rollback-only audit verification') RETURNING request_id
                """
            )
            request_id = cursor.fetchone()["request_id"]
            cursor.execute(
                """
                UPDATE public."Analysis_Request"
                SET status='SUCCESS',
                    version_snapshot='{"model_provider":"OpenAI","model_id":"test"}'::jsonb,
                    methodology_metadata='{"lookahead_check_status":"PASS"}'::jsonb,
                    answer='{}'::jsonb
                WHERE request_id=%s
                """,
                (request_id,),
            )
            cursor.execute("SAVEPOINT immutable_update")
            try:
                cursor.execute(
                    """
                    UPDATE public."Analysis_Request"
                    SET version_snapshot='{"changed":true}'::jsonb
                    WHERE request_id=%s
                    """,
                    (request_id,),
                )
            except psycopg.Error:
                cursor.execute("ROLLBACK TO SAVEPOINT immutable_update")
                result["completed_snapshot_immutability"] = "PASS"
            else:
                raise RuntimeError("completed analysis snapshot mutation was not blocked")
            cursor.execute("RESET ROLE")
            cursor.execute("ROLLBACK TO SAVEPOINT immutable_audit")
            connection.rollback()
    finally:
        connection.close()

    print(json.dumps(result, default=str, indent=2))
    print("overall=PASS")


if __name__ == "__main__":
    main()
