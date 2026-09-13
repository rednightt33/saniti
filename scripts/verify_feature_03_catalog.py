#!/usr/bin/env python3
"""Read-only final catalog, size, index, and query-plan checks for Feature 03."""

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
        host=args.host, port=args.port, dbname=os.environ["PGDATABASE"],
        user=os.environ["PGUSER"], password=os.environ["PGPASSWORD"],
        sslmode="require", application_name="feature-03-final-verification",
    ) as connection:
        statements = {
            "catalog_counts": """
                SELECT
                  (SELECT count(*) FROM public."Table_Catalog"),
                  (SELECT count(*) FROM public."Column_Catalog"),
                  (SELECT count(*) FROM public."Feature_Catalog" WHERE is_active),
                  (SELECT count(*) FROM public."Feature_Catalog"
                   WHERE feature_table='Feature_03_Stock_Broker_Daily' AND is_active),
                  (SELECT count(*) FROM public."Column_Catalog"
                   WHERE table_name='Feature_03_Stock_Broker_Daily'
                     AND documentation_status='VERIFIED')
            """,
            "registered_tables": """
                SELECT table_name, documentation_status
                FROM public."Table_Catalog" ORDER BY table_name
            """,
            "feature_relationships": """
                SELECT left_feature_table, right_feature_table, left_join_columns,
                       right_join_columns, relationship_type, safe_output_grain,
                       requires_preaggregation, version, is_active
                FROM public."Feature_Relationship_Catalog"
                ORDER BY left_feature_table, right_feature_table, version
            """,
            "table_size": """
                SELECT pg_size_pretty(pg_total_relation_size(
                  'public."Feature_03_Stock_Broker_Daily"'::regclass))
            """,
            "null_and_zero_counts": """
                SELECT
                  count(*) FILTER (WHERE active_broker_count=0),
                  count(*) FILTER (WHERE net_buy_broker_ratio IS NULL),
                  count(*) FILTER (WHERE top_buyer IS NULL),
                  count(*) FILTER (WHERE top_seller IS NULL),
                  count(*) FILTER (WHERE top3_buyer_share IS NULL),
                  count(*) FILTER (WHERE broker_concentration_hhi IS NULL)
                FROM public."Feature_03_Stock_Broker_Daily"
            """,
            "indexes": """
                SELECT indexname FROM pg_indexes
                WHERE schemaname='public' AND tablename='Feature_03_Stock_Broker_Daily'
                ORDER BY indexname
            """,
            "history_plan": """
                EXPLAIN (COSTS OFF)
                SELECT * FROM public."Feature_03_Stock_Broker_Daily"
                WHERE ticker='BBCA' AND market_board='Regular'
                  AND date >= DATE '2026-01-01' ORDER BY date
            """,
            "daily_plan": """
                EXPLAIN (COSTS OFF)
                SELECT ticker, broker_concentration_hhi
                FROM public."Feature_03_Stock_Broker_Daily"
                WHERE date=DATE '2026-08-31' AND market_board='Regular'
            """,
        }
        with connection.cursor() as cursor:
            for label, statement in statements.items():
                cursor.execute(statement)
                print(f"{label}={cursor.fetchall()}")


if __name__ == "__main__":
    main()
