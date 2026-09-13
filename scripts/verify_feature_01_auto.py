#!/usr/bin/env python3
"""Rollback-only verification of Feature 01 price enqueue and status reconciliation."""

from __future__ import annotations

import argparse
import os

import psycopg
from psycopg.rows import dict_row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()

    with psycopg.connect(
        host=args.host,
        port=args.port,
        dbname=os.environ["PGDATABASE"],
        user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
        sslmode="require",
        row_factory=dict_row,
    ) as connection:
        price = connection.execute(
            'SELECT price.ticker, price.date, price.ingestion_time '
            'FROM public."Price_Stock_Indonesia_IDX" AS price '
            "WHERE price.ticker = 'BBCA' "
            'AND NOT EXISTS ('
            'SELECT 1 FROM public."Feature_Calculation_Queue" AS queue '
            'WHERE queue.ticker = price.ticker AND queue.price_date = price.date) '
            'ORDER BY price.date DESC LIMIT 1'
        ).fetchone()
        assert price is not None
        before = connection.execute(
            'SELECT count(*) AS queue_rows FROM public."Feature_Calculation_Queue" '
            'WHERE ticker = %s AND price_date = %s',
            (price["ticker"], price["date"]),
        ).fetchone()["queue_rows"]
        assert before == 0, "Rollback-only probe requires an unqueued BBCA date"
        connection.execute(
            'UPDATE public."Price_Stock_Indonesia_IDX" '
            'SET ingestion_time = statement_timestamp() '
            'WHERE ticker = %s AND date = %s',
            (price["ticker"], price["date"]),
        )
        queue = connection.execute(
            'SELECT status, source_ingestion_time, source_attempt_count '
            'FROM public."Feature_Calculation_Queue" '
            'WHERE ticker = %s AND price_date = %s',
            (price["ticker"], price["date"]),
        ).fetchone()
        status = connection.execute(
            'SELECT status, pending_count, processing_count, failed_count '
            'FROM public."Feature_Status" WHERE ticker = %s',
            (price["ticker"],),
        ).fetchone()
        assert queue is not None and queue["status"] == "PENDING"
        assert queue["source_ingestion_time"] is not None
        assert queue["source_attempt_count"] == 0
        assert status is not None and status["status"] == "PENDING"
        assert (status["pending_count"], status["processing_count"],
                status["failed_count"]) == (1, 0, 0)
        connection.rollback()

        after = connection.execute(
            'SELECT count(*) AS queue_rows FROM public."Feature_Calculation_Queue" '
            'WHERE ticker = %s AND price_date = %s',
            (price["ticker"], price["date"]),
        ).fetchone()["queue_rows"]
        assert after == 0
        print("PASS rollback-only trigger: price update -> PENDING queue/status -> rollback")


if __name__ == "__main__":
    main()
