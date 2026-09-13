#!/usr/bin/env python3
"""Run the PostgreSQL-side full historical Feature 03 refresh."""

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

    started = time.monotonic()
    with psycopg.connect(
        host=args.host,
        port=args.port,
        dbname=os.environ["PGDATABASE"],
        user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
        sslmode="require",
        application_name="feature-03-backfill",
    ) as connection:
        connection.execute("SET statement_timeout = '30min'")
        rows = connection.execute(
            "SELECT public.refresh_feature_03_stock_broker_daily(NULL, NULL)"
        ).fetchone()[0]
        connection.commit()
    print(f"backfill_complete rows={rows} seconds={time.monotonic()-started:.1f}")


if __name__ == "__main__":
    main()
