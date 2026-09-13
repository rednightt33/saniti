#!/usr/bin/env python3
"""Read-only Feature 03 dependency, freshness, and expected-grain inspection."""

from __future__ import annotations

import argparse
import os
import time

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
        application_name="feature-03-inspection",
        autocommit=True,
    ) as connection:
        connection.execute("SET statement_timeout = '30min'")
        checks = {
            "freshness": """
                SELECT
                  (SELECT count(*) FROM public."IDX_Broker_Summary"),
                  (SELECT min("Date") FROM public."IDX_Broker_Summary"),
                  (SELECT max("Date") FROM public."IDX_Broker_Summary"),
                  (SELECT count(*) FROM public."Feature_02_Broker_Rolling"),
                  (SELECT min(date) FROM public."Feature_02_Broker_Rolling"),
                  (SELECT max(date) FROM public."Feature_02_Broker_Rolling"),
                  (SELECT count(*) FROM public."IDX_Broker_Profile"),
                  (SELECT count(*) FROM public."IDX_Stock_Universe"),
                  (SELECT max(date) FROM public."Price_Stock_Indonesia_IDX")
            """,
            "profile_values": """
                SELECT 'broker_type', broker_type, count(*)
                FROM public."IDX_Broker_Profile" GROUP BY broker_type
                UNION ALL
                SELECT 'broker_classification', broker_classification, count(*)
                FROM public."IDX_Broker_Profile" GROUP BY broker_classification
                ORDER BY 1, 2
            """,
            "expected_grains": """
                SELECT market_board, count(*) AS rows, count(DISTINCT ticker) AS tickers,
                       min(date), max(date)
                FROM (
                  SELECT date, ticker, market_board
                  FROM public."Feature_02_Broker_Rolling"
                  GROUP BY date, ticker, market_board
                ) AS daily
                GROUP BY market_board ORDER BY market_board
            """,
        }
        with connection.cursor() as cursor:
            for label, statement in checks.items():
                started = time.monotonic()
                cursor.execute(statement)
                print(f"{label}={cursor.fetchall()} seconds={time.monotonic()-started:.1f}")


if __name__ == "__main__":
    main()
