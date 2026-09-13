#!/usr/bin/env python3
"""Read-only aggregate checks for the historical Feature 02 broker backfill.

The source and Feature tables are scanned inside PostgreSQL; no row-level data is
transferred to Python. This is a reconciliation aid, not a substitute for
independent sample recalculation of rolling formulas.
"""

from __future__ import annotations

import argparse
import os
import time
from datetime import date

import psycopg
from psycopg import sql


CALCULATED_COLUMNS = (
    "net_value_5d", "net_value_20d", "net_value_60d",
    "net_lots_5d", "net_lots_20d", "net_lots_60d",
    "buy_days_20d", "sell_days_20d", "active_days_20d",
    "stock_trading_days_20d", "buy_day_ratio_20d",
    "buy_share_active_days_20d",
    "buy_days_60d", "sell_days_60d", "active_days_60d",
    "stock_trading_days_60d", "buy_day_ratio_60d",
    "buy_share_active_days_60d",
    "net_value_zscore_20d", "net_value_zscore_60d",
    "net_value_percentile_20d", "net_value_percentile_60d",
    "positive_net_value_20d", "largest_buy_day_20d",
    "largest_buy_day_share_20d",
)

SOURCE_TOTALS = """
SELECT market_board, count(*) AS daily_grains,
       count(DISTINCT ticker), count(DISTINCT broker), min(date), max(date),
       sum(buy_value), sum(sell_value), sum(buy_lots), sum(sell_lots)
FROM feature_02_validation_source GROUP BY market_board ORDER BY market_board
"""

FEATURE_TOTALS = """
SELECT market_board, count(*) AS feature_rows,
       count(DISTINCT ticker), count(DISTINCT broker),
       min(date), max(date),
       sum(buy_value_1d), sum(sell_value_1d),
       sum(buy_lots_1d), sum(sell_lots_1d)
FROM public."Feature_02_Broker_Rolling"
GROUP BY market_board ORDER BY market_board
"""

FEATURE_COVERAGE = """
SELECT count(*), count(DISTINCT ticker), count(DISTINCT broker),
       min(date), max(date),
       count(*) FILTER (WHERE broker_type IS NULL),
       count(*) FILTER (WHERE broker_classification IS NULL),
       count(*) FILTER (WHERE buy_days_20d > active_days_20d
                        OR sell_days_20d > active_days_20d
                        OR active_days_20d > stock_trading_days_20d
                        OR buy_days_60d > active_days_60d
                        OR sell_days_60d > active_days_60d
                        OR active_days_60d > stock_trading_days_60d),
       count(*) FILTER (WHERE net_value_5d IS NOT NULL
                        AND net_value_20d IS NULL
                        AND stock_trading_days_20d IS NOT NULL)
FROM public."Feature_02_Broker_Rolling"
"""

EXACT_RECONCILIATION = """
SELECT
    count(*) FILTER (WHERE source.date IS NULL) AS extra_feature_rows,
    count(*) FILTER (WHERE feature.date IS NULL) AS missing_feature_rows,
    count(*) FILTER (
        WHERE source.date IS NOT NULL AND feature.date IS NOT NULL
          AND (source.buy_value <> feature.buy_value_1d
            OR source.sell_value <> feature.sell_value_1d
            OR source.buy_lots <> feature.buy_lots_1d
            OR source.sell_lots <> feature.sell_lots_1d)
    ) AS value_mismatches
FROM feature_02_validation_source AS source
FULL JOIN public."Feature_02_Broker_Rolling" AS feature
  ON feature.date=source.date AND feature.ticker=source.ticker
 AND feature.broker=source.broker AND feature.market_board=source.market_board
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args()
    with psycopg.connect(
        host=args.host, port=args.port,
        dbname=os.environ["PGDATABASE"], user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"], sslmode="require",
        application_name="feature-02-validation", autocommit=True,
    ) as db:
        db.execute("SET statement_timeout = '30min'")
        db.execute("SET work_mem = '64MB'")
        db.execute("""
            CREATE TEMP TABLE feature_02_validation_source (
                date date NOT NULL, ticker text NOT NULL, broker text NOT NULL,
                market_board text NOT NULL, buy_value numeric NOT NULL,
                sell_value numeric NOT NULL, buy_lots numeric NOT NULL,
                sell_lots numeric NOT NULL
            ) ON COMMIT PRESERVE ROWS
        """)
        minimum, maximum = db.execute(
            'SELECT min("Date"), max("Date") FROM public."IDX_Broker_Summary"'
        ).fetchone()
        if minimum is None:
            raise RuntimeError("Broker Summary is empty")
        for year in range(minimum.year, maximum.year + 1):
            begun = time.monotonic()
            cursor = db.execute("""
                INSERT INTO feature_02_validation_source
                SELECT "Date", "Symbol"::text, "Broker"::text,
                       "Market Board"::text,
                       sum("Buy Value"), sum("Sell Value"),
                       sum("Buy Lots"), sum("Sell Lots")
                FROM public."IDX_Broker_Summary"
                WHERE "Date">=%s AND "Date"<%s
                GROUP BY "Date", "Symbol", "Broker", "Market Board"
            """, (date(year, 1, 1), date(year + 1, 1, 1)))
            print(
                f"validation_stage year={year} rows={cursor.rowcount} "
                f"seconds={time.monotonic()-begun:.1f}", flush=True,
            )
        begun = time.monotonic()
        db.execute(
            "CREATE UNIQUE INDEX feature_02_validation_source_key "
            "ON feature_02_validation_source(ticker,market_board,broker,date)"
        )
        db.execute("ANALYZE feature_02_validation_source")
        print(f"validation_stage_index_seconds={time.monotonic()-begun:.1f}", flush=True)
        begun = time.monotonic()
        source = {row[0]: row for row in db.execute(SOURCE_TOTALS)}
        print(f"source_totals_seconds={time.monotonic()-begun:.1f}", flush=True)
        begun = time.monotonic()
        feature = {row[0]: row for row in db.execute(FEATURE_TOTALS)}
        print(f"feature_totals_seconds={time.monotonic()-begun:.1f}", flush=True)
        failed = False
        for board in sorted(set(source) | set(feature)):
            s, f = source.get(board), feature.get(board)
            passed = bool(s and f and s[1:] == f[1:])
            print(
                f"board={board} source_daily_grains={s[1] if s else None} "
                f"feature_rows={f[1] if f else None} "
                f"distinct_ids_min_max_and_gross_totals={'PASS' if passed else 'FAIL'}",
                flush=True,
            )
            if not passed:
                failed = True
                print(f"  source={s} feature={f}", flush=True)
        begun = time.monotonic()
        reconciliation = db.execute(EXACT_RECONCILIATION).fetchone()
        print(
            f"exact_reconciliation extra={reconciliation[0]} "
            f"missing={reconciliation[1]} value_mismatches={reconciliation[2]} "
            f"{'PASS' if reconciliation == (0, 0, 0) else 'FAIL'} "
            f"seconds={time.monotonic()-begun:.1f}", flush=True,
        )
        failed = failed or reconciliation != (0, 0, 0)
        begun = time.monotonic()
        coverage = db.execute(FEATURE_COVERAGE).fetchone()
        print(f"feature_coverage={coverage} seconds={time.monotonic()-begun:.1f}", flush=True)
        failed = failed or any(coverage[index] != 0 for index in (5, 6, 7, 8))
        fields = sql.SQL(", ").join(
            sql.SQL("count(*) FILTER (WHERE {} IS NULL)").format(sql.Identifier(name))
            for name in CALCULATED_COLUMNS
        )
        begun = time.monotonic()
        null_counts = db.execute(
            sql.SQL('SELECT {} FROM public."Feature_02_Broker_Rolling"').format(fields)
        ).fetchone()
        total = coverage[0]
        for name, count in zip(CALCULATED_COLUMNS, null_counts):
            print(f"null {name} count={count} rate={100*count/total:.4f}%", flush=True)
        print(f"null_scan_seconds={time.monotonic()-begun:.1f}", flush=True)
        print(f"overall={'FAIL' if failed else 'PASS'}", flush=True)
        if failed:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
