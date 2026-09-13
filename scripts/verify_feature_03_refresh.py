#!/usr/bin/env python3
"""Verify a committed scoped Feature 03 refresh preserves its expected grain."""

from __future__ import annotations

import argparse
import os
import time

import psycopg


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--date", required=True)
    args = parser.parse_args()

    with psycopg.connect(
        host=args.host, port=args.port, dbname=os.environ["PGDATABASE"],
        user=os.environ["PGUSER"], password=os.environ["PGPASSWORD"],
        sslmode="require", application_name="feature-03-refresh-verification",
    ) as connection:
        before = connection.execute("""
            SELECT count(*) FROM public."Feature_03_Stock_Broker_Daily"
            WHERE ticker=%s AND date=%s
        """, (args.ticker, args.date)).fetchone()[0]
        started = time.monotonic()
        refreshed = connection.execute(
            "SELECT public.refresh_feature_03_stock_broker_daily(%s, ARRAY[%s])",
            (args.date, args.ticker),
        ).fetchone()[0]
        connection.commit()
        after = connection.execute("""
            SELECT count(*) FROM public."Feature_03_Stock_Broker_Daily"
            WHERE ticker=%s AND date=%s
        """, (args.ticker, args.date)).fetchone()[0]
    passed = before == refreshed == after
    print(f"ticker={args.ticker} date={args.date} before={before} refreshed={refreshed} "
          f"after={after} seconds={time.monotonic()-started:.1f} {'PASS' if passed else 'FAIL'}")
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
