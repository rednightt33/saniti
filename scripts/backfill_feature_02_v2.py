#!/usr/bin/env python3
"""SQL-side resumable backfill for the Investor-Type-preserving Feature 02 shadow."""

from __future__ import annotations

import argparse
import os
import time
from datetime import date

import psycopg


TARGET = 'public."Feature_02_Broker_Rolling_v2"'

CREATE_TEMP = """
CREATE TEMP TABLE feature_02_v2_daily_base (
    date date NOT NULL,
    ticker text NOT NULL,
    broker text NOT NULL,
    investor_type text NOT NULL,
    market_board text NOT NULL,
    buy_value numeric NOT NULL,
    sell_value numeric NOT NULL,
    buy_lots numeric NOT NULL,
    sell_lots numeric NOT NULL,
    net_value numeric NOT NULL,
    net_lots numeric NOT NULL
) ON COMMIT PRESERVE ROWS
"""

STAGE_YEAR = """
INSERT INTO feature_02_v2_daily_base (
    date, ticker, broker, investor_type, market_board,
    buy_value, sell_value, buy_lots, sell_lots, net_value, net_lots
)
SELECT "Date", "Symbol"::text, "Broker"::text, "Investor Type"::text,
       "Market Board"::text,
       sum("Buy Value"), sum("Sell Value"), sum("Buy Lots"), sum("Sell Lots"),
       sum("Buy Value") - sum("Sell Value"),
       sum("Buy Lots") - sum("Sell Lots")
FROM public."IDX_Broker_Summary"
WHERE "Date" >= %s AND "Date" < %s
  AND (%s::text IS NULL OR "Symbol" = %s::text)
  AND (%s::text IS NULL OR "Symbol" >= %s::text)
  AND (%s::text IS NULL OR "Symbol" < %s::text)
GROUP BY "Date", "Symbol", "Broker", "Investor Type", "Market Board"
"""

INSERT_TICKER = f"""
INSERT INTO {TARGET} (
    date, ticker, broker, investor_type, market_board, broker_classification,
    buy_value_1d, sell_value_1d, net_value_1d,
    buy_lots_1d, sell_lots_1d, net_lots_1d,
    net_value_5d, net_value_20d, net_value_60d,
    net_lots_5d, net_lots_20d, net_lots_60d,
    buy_days_20d, sell_days_20d, active_days_20d,
    stock_trading_days_20d, buy_day_ratio_20d, buy_share_active_days_20d,
    buy_days_60d, sell_days_60d, active_days_60d,
    stock_trading_days_60d, buy_day_ratio_60d, buy_share_active_days_60d,
    net_value_zscore_20d, net_value_zscore_60d,
    net_value_percentile_20d, net_value_percentile_60d,
    positive_net_value_20d, largest_buy_day_20d,
    largest_buy_day_share_20d, calculated_at
)
WITH daily AS MATERIALIZED (
    SELECT * FROM feature_02_v2_daily_base WHERE ticker = %s
),
calendar AS (
    SELECT date, row_number() OVER (ORDER BY date) AS day_no
    FROM (SELECT DISTINCT date FROM daily) AS available
),
pairs AS (
    SELECT DISTINCT broker, investor_type, market_board FROM daily
),
dense AS (
    SELECT calendar.date, calendar.day_no, pairs.broker,
           pairs.investor_type, pairs.market_board,
           coalesce(daily.net_value, 0) AS net_value,
           coalesce(daily.net_lots, 0) AS net_lots,
           CASE WHEN daily.date IS NOT NULL
                     AND (daily.buy_value > 0 OR daily.sell_value > 0
                          OR daily.buy_lots > 0 OR daily.sell_lots > 0)
                THEN 1 ELSE 0 END AS active
    FROM calendar CROSS JOIN pairs
    LEFT JOIN daily
      ON daily.date = calendar.date
     AND daily.broker = pairs.broker
     AND daily.investor_type = pairs.investor_type
     AND daily.market_board = pairs.market_board
),
rolling AS (
    SELECT dense.*,
           sum(net_value) OVER w5 AS net_value_5_raw,
           sum(net_value) OVER w20 AS net_value_20_raw,
           sum(net_value) OVER w60 AS net_value_60_raw,
           sum(net_lots) OVER w5 AS net_lots_5_raw,
           sum(net_lots) OVER w20 AS net_lots_20_raw,
           sum(net_lots) OVER w60 AS net_lots_60_raw,
           count(*) FILTER (WHERE net_value > 0) OVER w20 AS buy_days_20_raw,
           count(*) FILTER (WHERE net_value < 0) OVER w20 AS sell_days_20_raw,
           sum(active) OVER w20 AS active_days_20_raw,
           count(*) FILTER (WHERE net_value > 0) OVER w60 AS buy_days_60_raw,
           count(*) FILTER (WHERE net_value < 0) OVER w60 AS sell_days_60_raw,
           sum(active) OVER w60 AS active_days_60_raw,
           sum(greatest(net_value, 0)) OVER w20 AS positive_net_20_raw,
           max(net_value) FILTER (WHERE net_value > 0) OVER w20 AS largest_buy_20_raw
    FROM dense
    WINDOW w5 AS (PARTITION BY broker, investor_type, market_board ORDER BY day_no
                  ROWS BETWEEN 4 PRECEDING AND CURRENT ROW),
           w20 AS (PARTITION BY broker, investor_type, market_board ORDER BY day_no
                   ROWS BETWEEN 19 PRECEDING AND CURRENT ROW),
           w60 AS (PARTITION BY broker, investor_type, market_board ORDER BY day_no
                   ROWS BETWEEN 59 PRECEDING AND CURRENT ROW)
),
complete AS (
    SELECT rolling.*,
           CASE WHEN day_no >= 5 THEN net_value_5_raw END AS net_value_5d,
           CASE WHEN day_no >= 20 THEN net_value_20_raw END AS net_value_20d,
           CASE WHEN day_no >= 60 THEN net_value_60_raw END AS net_value_60d,
           CASE WHEN day_no >= 5 THEN net_lots_5_raw END AS net_lots_5d,
           CASE WHEN day_no >= 20 THEN net_lots_20_raw END AS net_lots_20d,
           CASE WHEN day_no >= 60 THEN net_lots_60_raw END AS net_lots_60d
    FROM rolling
),
history AS (
    SELECT complete.*,
           count(net_value_20d) OVER h AS history_20_count,
           avg(net_value_20d::double precision) OVER h AS history_20_mean,
           stddev_samp(net_value_20d::double precision) OVER h AS history_20_std,
           array_agg(net_value_20d) FILTER (WHERE net_value_20d IS NOT NULL)
               OVER h AS history_20_values,
           count(net_value_60d) OVER h AS history_60_count,
           avg(net_value_60d::double precision) OVER h AS history_60_mean,
           stddev_samp(net_value_60d::double precision) OVER h AS history_60_std,
           array_agg(net_value_60d) FILTER (WHERE net_value_60d IS NOT NULL)
               OVER h AS history_60_values
    FROM complete
    WINDOW h AS (PARTITION BY broker, investor_type, market_board ORDER BY day_no
                 ROWS BETWEEN 252 PRECEDING AND 1 PRECEDING)
)
SELECT daily.date, daily.ticker, daily.broker, daily.investor_type,
       daily.market_board, profile.broker_classification,
       daily.buy_value, daily.sell_value, daily.net_value,
       daily.buy_lots, daily.sell_lots, daily.net_lots,
       history.net_value_5d, history.net_value_20d, history.net_value_60d,
       history.net_lots_5d, history.net_lots_20d, history.net_lots_60d,
       CASE WHEN day_no >= 20 THEN buy_days_20_raw::smallint END,
       CASE WHEN day_no >= 20 THEN sell_days_20_raw::smallint END,
       CASE WHEN day_no >= 20 THEN active_days_20_raw::smallint END,
       CASE WHEN day_no >= 20 THEN 20::smallint END,
       CASE WHEN day_no >= 20 THEN buy_days_20_raw::double precision / 20 END,
       CASE WHEN day_no >= 20 AND active_days_20_raw > 0
            THEN buy_days_20_raw::double precision / active_days_20_raw END,
       CASE WHEN day_no >= 60 THEN buy_days_60_raw::smallint END,
       CASE WHEN day_no >= 60 THEN sell_days_60_raw::smallint END,
       CASE WHEN day_no >= 60 THEN active_days_60_raw::smallint END,
       CASE WHEN day_no >= 60 THEN 60::smallint END,
       CASE WHEN day_no >= 60 THEN buy_days_60_raw::double precision / 60 END,
       CASE WHEN day_no >= 60 AND active_days_60_raw > 0
            THEN buy_days_60_raw::double precision / active_days_60_raw END,
       CASE WHEN history_20_count = 252 AND history_20_std > 0
            THEN (history.net_value_20d::double precision - history_20_mean)
                 / history_20_std END,
       CASE WHEN history_60_count = 252 AND history_60_std > 0
            THEN (history.net_value_60d::double precision - history_60_mean)
                 / history_60_std END,
       CASE WHEN history_20_count = 252
            THEN public.feature_02_empirical_midrank_percentile(
                history.net_value_20d, history_20_values) END,
       CASE WHEN history_60_count = 252
            THEN public.feature_02_empirical_midrank_percentile(
                history.net_value_60d, history_60_values) END,
       CASE WHEN day_no >= 20 THEN positive_net_20_raw END,
       CASE WHEN day_no >= 20 THEN largest_buy_20_raw END,
       CASE WHEN day_no >= 20 AND positive_net_20_raw > 0
            THEN largest_buy_20_raw::double precision
                 / positive_net_20_raw::double precision END,
       statement_timestamp()
FROM history
JOIN daily
  ON daily.date = history.date
 AND daily.broker = history.broker
 AND daily.investor_type = history.investor_type
 AND daily.market_board = history.market_board
LEFT JOIN public."IDX_Broker_Profile" AS profile
  ON profile.broker_code = daily.broker
"""


def connection_kwargs(args: argparse.Namespace) -> dict[str, object]:
    return {
        "host": args.host,
        "port": args.port,
        "dbname": os.environ["PGDATABASE"],
        "user": os.environ["PGUSER"],
        "password": os.environ["PGPASSWORD"],
        "sslmode": "require",
        "application_name": "feature-02-v2-shadow-backfill",
        "autocommit": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--ticker", help="Only one source symbol; controlled validation run")
    parser.add_argument("--ticker-from", help="Inclusive ticker lower bound")
    parser.add_argument("--ticker-to", help="Exclusive ticker upper bound")
    parser.add_argument("--rebuild-ticker", action="store_true")
    parser.add_argument("--max-tickers", type=int)
    args = parser.parse_args()
    if args.rebuild_ticker and not args.ticker:
        parser.error("--rebuild-ticker requires --ticker")
    if args.ticker and (args.ticker_from or args.ticker_to):
        parser.error("--ticker cannot be combined with ticker bounds")
    if args.ticker_from and args.ticker_to and args.ticker_from >= args.ticker_to:
        parser.error("--ticker-from must sort before --ticker-to")
    if args.max_tickers is not None and args.max_tickers <= 0:
        parser.error("--max-tickers must be positive")

    with psycopg.connect(**connection_kwargs(args)) as db:
        db.execute("SET statement_timeout = '20min'")
        db.execute("SET lock_timeout = '5s'")
        db.execute("SET work_mem = '64MB'")
        db.execute("SET maintenance_work_mem = '256MB'")
        if db.execute(f"SELECT to_regclass('{TARGET}')").fetchone()[0] is None:
            raise RuntimeError("Feature 02 v2 shadow migration is not applied")
        db.execute(CREATE_TEMP)
        bounds = db.execute(
            'SELECT min("Date"), max("Date") FROM public."IDX_Broker_Summary"'
        ).fetchone()
        if bounds[0] is None:
            raise RuntimeError("Broker Summary is empty")
        for year in range(bounds[0].year, bounds[1].year + 1):
            start = date(year, 1, 1)
            end = date(year + 1, 1, 1)
            begun = time.monotonic()
            cursor = db.execute(
                STAGE_YEAR,
                (start, end, args.ticker, args.ticker,
                 args.ticker_from, args.ticker_from,
                 args.ticker_to, args.ticker_to),
            )
            print(
                f"staged year={year} daily_grains={cursor.rowcount} "
                f"seconds={time.monotonic() - begun:.1f}", flush=True,
            )
        begun = time.monotonic()
        db.execute(
            "CREATE UNIQUE INDEX feature_02_v2_daily_base_key "
            "ON feature_02_v2_daily_base "
            "(ticker, broker, investor_type, market_board, date)"
        )
        db.execute("ANALYZE feature_02_v2_daily_base")
        staged = db.execute("SELECT count(*) FROM feature_02_v2_daily_base").fetchone()[0]
        print(f"stage_ready rows={staged} index_seconds={time.monotonic()-begun:.1f}", flush=True)
        tickers = [row[0] for row in db.execute(
            "SELECT DISTINCT ticker FROM feature_02_v2_daily_base ORDER BY ticker"
        )]
        completed = skipped = inserted_total = 0
        for ticker in tickers:
            begun = time.monotonic()
            with db.transaction():
                db.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    ("Feature_02_Broker_Rolling_v2:" + ticker,),
                )
                if not args.rebuild_ticker and db.execute(
                    f"SELECT 1 FROM {TARGET} WHERE ticker=%s LIMIT 1", (ticker,)
                ).fetchone():
                    skipped += 1
                    continue
                if args.rebuild_ticker:
                    db.execute(f"DELETE FROM {TARGET} WHERE ticker=%s", (ticker,))
                cursor = db.execute(INSERT_TICKER, (ticker,))
                expected = db.execute(
                    "SELECT count(*) FROM feature_02_v2_daily_base WHERE ticker=%s",
                    (ticker,),
                ).fetchone()[0]
                if cursor.rowcount != expected:
                    raise RuntimeError(
                        f"Ticker {ticker}: inserted {cursor.rowcount}, expected {expected}"
                    )
            completed += 1
            inserted_total += expected
            elapsed = time.monotonic() - begun
            if completed % 25 == 0 or elapsed >= 30 or args.ticker:
                print(
                    f"progress completed={completed} skipped={skipped} ticker={ticker} "
                    f"rows={expected} inserted_total={inserted_total} "
                    f"ticker_seconds={elapsed:.1f}", flush=True,
                )
            if args.max_tickers is not None and completed >= args.max_tickers:
                break
        print(
            f"run_complete staged_rows={staged} inserted_rows={inserted_total} "
            f"completed_tickers={completed} skipped_tickers={skipped} "
            f"total_tickers={len(tickers)}", flush=True,
        )


if __name__ == "__main__":
    main()
