#!/usr/bin/env python3
"""Read-only final catalog, index, and query-plan checks for Feature 02."""

from __future__ import annotations

import argparse
import os

import psycopg


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args()

    with psycopg.connect(
        host=args.host,
        port=args.port,
        dbname=os.environ["PGDATABASE"],
        user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
        sslmode="require",
        application_name="feature-02-final-verification",
    ) as connection:
        queries = {
            "catalog_counts": """
                SELECT
                  (SELECT count(*) FROM public."Table_Catalog"),
                  (SELECT count(*) FROM public."Column_Catalog"),
                  (SELECT count(*) FROM public."Feature_Catalog" WHERE is_active),
                  (SELECT count(*) FROM public."Feature_Catalog"
                   WHERE feature_table='Feature_02_Broker_Rolling' AND is_active),
                  (SELECT count(*) FROM public."Column_Catalog"
                   WHERE table_name='Feature_02_Broker_Rolling'
                     AND documentation_status='VERIFIED')
            """,
            "feature_table_size": """
                SELECT pg_size_pretty(pg_total_relation_size(
                  'public."Feature_02_Broker_Rolling"'::regclass))
            """,
            "feature_indexes": """
                SELECT indexname FROM pg_indexes
                WHERE schemaname='public'
                  AND tablename='Feature_02_Broker_Rolling'
                ORDER BY indexname
            """,
            "history_plan": """
                EXPLAIN (COSTS OFF)
                SELECT * FROM public."Feature_02_Broker_Rolling"
                WHERE ticker='BBCA' AND market_board='Regular'
                  AND broker='AK' AND date >= DATE '2026-01-01'
                ORDER BY date
            """,
            "date_board_plan": """
                EXPLAIN (COSTS OFF)
                SELECT ticker, broker, net_value_20d
                FROM public."Feature_02_Broker_Rolling"
                WHERE date=DATE '2026-08-31' AND market_board='Regular'
                  AND ticker='BBCA'
            """,
        }
        with connection.cursor() as cursor:
            for label, statement in queries.items():
                cursor.execute(statement)
                rows = cursor.fetchall()
                print(f"{label}={rows}")


if __name__ == "__main__":
    main()
