#!/usr/bin/env python3
"""Full SQL-side reconciliation and sanity validation for Feature 03."""

from __future__ import annotations

import argparse
import os
import time

import psycopg


EXPECTED_SQL_V1 = """
CREATE TEMP TABLE feature_03_validation_expected ON COMMIT DROP AS
WITH broker_daily AS (
    SELECT f.date, f.ticker, f.market_board, f.broker,
           p.broker_type, p.broker_classification,
           f.buy_value_1d, f.sell_value_1d, f.net_value_1d,
           (f.buy_value_1d <> 0 OR f.sell_value_1d <> 0
            OR f.buy_lots_1d <> 0 OR f.sell_lots_1d <> 0) AS is_active,
           row_number() OVER (
               PARTITION BY f.date, f.ticker, f.market_board
               ORDER BY f.net_value_1d DESC, f.broker ASC
           ) AS buy_rank
    FROM public."Feature_02_Broker_Rolling" AS f
    LEFT JOIN public."IDX_Broker_Profile" AS p ON p.broker_code = f.broker
), aggregated AS (
    SELECT date, ticker, market_board,
           sum(buy_value_1d) AS total_buy_value,
           sum(sell_value_1d) AS total_sell_value,
           count(*) FILTER (WHERE is_active)::smallint AS active_broker_count,
           count(*) FILTER (WHERE net_value_1d > 0)::smallint AS net_buy_broker_count,
           count(*) FILTER (WHERE net_value_1d < 0)::smallint AS net_sell_broker_count,
           coalesce(sum(net_value_1d) FILTER (WHERE broker_type='Foreign'),0) AS foreign_net_value,
           coalesce(sum(net_value_1d) FILTER (WHERE broker_type='Domestic'),0) AS domestic_net_value,
           coalesce(sum(net_value_1d) FILTER (WHERE broker_classification='Institutional-heavy'),0) AS institutional_net_value,
           coalesce(sum(net_value_1d) FILTER (WHERE broker_classification='Retail-heavy'),0) AS retail_net_value,
           coalesce(sum(net_value_1d) FILTER (WHERE broker_classification='Mixed'),0) AS mixed_net_value,
           coalesce(sum(net_value_1d) FILTER (WHERE broker_classification='Niche'),0) AS niche_net_value,
           (array_agg(broker ORDER BY net_value_1d DESC, broker ASC)
                FILTER (WHERE net_value_1d > 0))[1] AS top_buyer,
           max(net_value_1d) FILTER (WHERE net_value_1d > 0) AS top_buyer_net_value,
           (array_agg(broker ORDER BY net_value_1d ASC, broker ASC)
                FILTER (WHERE net_value_1d < 0))[1] AS top_seller,
           min(net_value_1d) FILTER (WHERE net_value_1d < 0) AS top_seller_net_value,
           coalesce(sum(net_value_1d) FILTER (WHERE net_value_1d > 0 AND buy_rank <= 3),0) AS top3_buyer_net_value,
           coalesce(sum(net_value_1d) FILTER (WHERE net_value_1d > 0),0) AS positive_net_value_total,
           sum(abs(net_value_1d)) AS absolute_net_value_total,
           sum(net_value_1d * net_value_1d) AS squared_net_value_total
    FROM broker_daily GROUP BY date, ticker, market_board
)
SELECT date, ticker, market_board, total_buy_value, total_sell_value,
       active_broker_count, net_buy_broker_count, net_sell_broker_count,
       net_buy_broker_count::double precision / NULLIF(active_broker_count,0) AS net_buy_broker_ratio,
       foreign_net_value, domestic_net_value, institutional_net_value,
       retail_net_value, mixed_net_value, niche_net_value,
       top_buyer, top_buyer_net_value, top_seller, top_seller_net_value,
       top3_buyer_net_value, positive_net_value_total,
       top3_buyer_net_value::double precision / NULLIF(positive_net_value_total,0) AS top3_buyer_share,
       squared_net_value_total::double precision
         / NULLIF(absolute_net_value_total::double precision
                  * absolute_net_value_total::double precision,0) AS broker_concentration_hhi
FROM aggregated
"""

# Feature 03 v2 uses source Investor Type only for the two investor-flow
# columns. Broker counts, ranks, HHI, and profile classifications first merge
# Domestic and Foreign flow per broker to preserve their broker-level meaning.
EXPECTED_SQL_V2 = """
CREATE TEMP TABLE feature_03_validation_expected ON COMMIT DROP AS
WITH investor_flow AS (
    SELECT f.date,f.ticker,f.market_board,
           coalesce(sum(f.net_value_1d) FILTER (WHERE f.investor_type='Foreign'),0) AS foreign_net_value,
           coalesce(sum(f.net_value_1d) FILTER (WHERE f.investor_type='Domestic'),0) AS domestic_net_value
    FROM public."Feature_02_Broker_Rolling" AS f
    GROUP BY f.date,f.ticker,f.market_board
), broker_daily AS (
    SELECT f.date,f.ticker,f.market_board,f.broker,
           sum(f.buy_value_1d) AS buy_value_1d,
           sum(f.sell_value_1d) AS sell_value_1d,
           sum(f.net_value_1d) AS net_value_1d,
           bool_or(f.buy_value_1d<>0 OR f.sell_value_1d<>0
                   OR f.buy_lots_1d<>0 OR f.sell_lots_1d<>0) AS is_active
    FROM public."Feature_02_Broker_Rolling" AS f
    GROUP BY f.date,f.ticker,f.market_board,f.broker
), ranked_broker_daily AS (
    SELECT b.*,p.broker_classification,
           row_number() OVER (PARTITION BY b.date,b.ticker,b.market_board
                              ORDER BY b.net_value_1d DESC,b.broker ASC) AS buy_rank
    FROM broker_daily AS b
    LEFT JOIN public."IDX_Broker_Profile" AS p ON p.broker_code=b.broker
), aggregated AS (
    SELECT b.date,b.ticker,b.market_board,
           sum(b.buy_value_1d) AS total_buy_value,
           sum(b.sell_value_1d) AS total_sell_value,
           count(*) FILTER (WHERE b.is_active)::smallint AS active_broker_count,
           count(*) FILTER (WHERE b.net_value_1d>0)::smallint AS net_buy_broker_count,
           count(*) FILTER (WHERE b.net_value_1d<0)::smallint AS net_sell_broker_count,
           max(i.foreign_net_value) AS foreign_net_value,
           max(i.domestic_net_value) AS domestic_net_value,
           coalesce(sum(b.net_value_1d) FILTER (WHERE b.broker_classification='Institutional-heavy'),0) AS institutional_net_value,
           coalesce(sum(b.net_value_1d) FILTER (WHERE b.broker_classification='Retail-heavy'),0) AS retail_net_value,
           coalesce(sum(b.net_value_1d) FILTER (WHERE b.broker_classification='Mixed'),0) AS mixed_net_value,
           coalesce(sum(b.net_value_1d) FILTER (WHERE b.broker_classification='Niche'),0) AS niche_net_value,
           (array_agg(b.broker ORDER BY b.net_value_1d DESC,b.broker ASC) FILTER (WHERE b.net_value_1d>0))[1] AS top_buyer,
           max(b.net_value_1d) FILTER (WHERE b.net_value_1d>0) AS top_buyer_net_value,
           (array_agg(b.broker ORDER BY b.net_value_1d ASC,b.broker ASC) FILTER (WHERE b.net_value_1d<0))[1] AS top_seller,
           min(b.net_value_1d) FILTER (WHERE b.net_value_1d<0) AS top_seller_net_value,
           coalesce(sum(b.net_value_1d) FILTER (WHERE b.net_value_1d>0 AND b.buy_rank<=3),0) AS top3_buyer_net_value,
           coalesce(sum(b.net_value_1d) FILTER (WHERE b.net_value_1d>0),0) AS positive_net_value_total,
           sum(abs(b.net_value_1d)) AS absolute_net_value_total,
           sum(b.net_value_1d*b.net_value_1d) AS squared_net_value_total
    FROM ranked_broker_daily AS b
    JOIN investor_flow AS i USING (date,ticker,market_board)
    GROUP BY b.date,b.ticker,b.market_board
)
SELECT date,ticker,market_board,total_buy_value,total_sell_value,
       active_broker_count,net_buy_broker_count,net_sell_broker_count,
       net_buy_broker_count::double precision/NULLIF(active_broker_count,0) AS net_buy_broker_ratio,
       foreign_net_value,domestic_net_value,institutional_net_value,retail_net_value,
       mixed_net_value,niche_net_value,top_buyer,top_buyer_net_value,top_seller,
       top_seller_net_value,top3_buyer_net_value,positive_net_value_total,
       top3_buyer_net_value::double precision/NULLIF(positive_net_value_total,0) AS top3_buyer_share,
       squared_net_value_total::double precision/NULLIF(
         absolute_net_value_total::double precision*absolute_net_value_total::double precision,0) AS broker_concentration_hhi
FROM aggregated
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args()
    failures = 0

    with psycopg.connect(
        host=args.host, port=args.port, dbname=os.environ["PGDATABASE"],
        user=os.environ["PGUSER"], password=os.environ["PGPASSWORD"],
        sslmode="require", application_name="feature-03-validation",
    ) as connection:
        connection.execute("SET statement_timeout = '30min'")
        connection.execute("SET work_mem = '64MB'")
        started = time.monotonic()
        connection.execute(EXPECTED_SQL_V2)
        print(f"expected_stage_seconds={time.monotonic()-started:.1f}")
        started = time.monotonic()
        connection.execute("""
            ALTER TABLE feature_03_validation_expected
            ADD PRIMARY KEY (ticker, market_board, date)
        """)
        print(f"expected_index_seconds={time.monotonic()-started:.1f}")

        expected_boards = connection.execute("""
            SELECT market_board, count(*), count(DISTINCT ticker), min(date), max(date)
            FROM feature_03_validation_expected GROUP BY market_board ORDER BY market_board
        """).fetchall()
        feature_boards = connection.execute("""
            SELECT market_board, count(*), count(DISTINCT ticker), min(date), max(date)
            FROM public."Feature_03_Stock_Broker_Daily"
            GROUP BY market_board ORDER BY market_board
        """).fetchall()
        board_pass = expected_boards == feature_boards
        failures += not board_pass
        print(f"board_coverage_expected={expected_boards}")
        print(f"board_coverage_feature={feature_boards} {'PASS' if board_pass else 'FAIL'}")

        started = time.monotonic()
        extra, missing, mismatch = connection.execute("""
            SELECT
              count(*) FILTER (WHERE e.date IS NULL),
              count(*) FILTER (WHERE f.date IS NULL),
              count(*) FILTER (
                WHERE e.date IS NOT NULL AND f.date IS NOT NULL AND (
                  e.total_buy_value <> f.total_buy_value OR
                  e.total_sell_value <> f.total_sell_value OR
                  e.active_broker_count <> f.active_broker_count OR
                  e.net_buy_broker_count <> f.net_buy_broker_count OR
                  e.net_sell_broker_count <> f.net_sell_broker_count OR
                  e.net_buy_broker_ratio IS DISTINCT FROM f.net_buy_broker_ratio OR
                  e.foreign_net_value <> f.foreign_net_value OR
                  e.domestic_net_value <> f.domestic_net_value OR
                  e.institutional_net_value <> f.institutional_net_value OR
                  e.retail_net_value <> f.retail_net_value OR
                  e.mixed_net_value <> f.mixed_net_value OR
                  e.niche_net_value <> f.niche_net_value OR
                  e.top_buyer IS DISTINCT FROM f.top_buyer OR
                  e.top_buyer_net_value IS DISTINCT FROM f.top_buyer_net_value OR
                  e.top_seller IS DISTINCT FROM f.top_seller OR
                  e.top_seller_net_value IS DISTINCT FROM f.top_seller_net_value OR
                  e.top3_buyer_net_value <> f.top3_buyer_net_value OR
                  e.positive_net_value_total <> f.positive_net_value_total OR
                  e.top3_buyer_share IS DISTINCT FROM f.top3_buyer_share OR
                  e.broker_concentration_hhi IS DISTINCT FROM f.broker_concentration_hhi
                ))
            FROM feature_03_validation_expected AS e
            FULL JOIN public."Feature_03_Stock_Broker_Daily" AS f
              USING (ticker, market_board, date)
        """).fetchone()
        exact_pass = (extra, missing, mismatch) == (0, 0, 0)
        failures += not exact_pass
        print(f"exact_reconciliation extra={extra} missing={missing} mismatches={mismatch} "
              f"{'PASS' if exact_pass else 'FAIL'} seconds={time.monotonic()-started:.1f}")

        sanity = connection.execute("""
            SELECT
              count(*) FILTER (WHERE net_buy_broker_count + net_sell_broker_count > active_broker_count),
              count(*) FILTER (WHERE net_buy_broker_ratio IS NOT NULL
                               AND net_buy_broker_ratio NOT BETWEEN 0 AND 1),
              count(*) FILTER (WHERE top3_buyer_share IS NOT NULL
                               AND top3_buyer_share NOT BETWEEN 0 AND 1),
              count(*) FILTER (WHERE broker_concentration_hhi IS NOT NULL
                               AND broker_concentration_hhi NOT BETWEEN 0 AND 1),
              count(*) FILTER (WHERE foreign_net_value + domestic_net_value
                               <> total_buy_value - total_sell_value),
              count(*) FILTER (WHERE institutional_net_value + retail_net_value
                                   + mixed_net_value + niche_net_value
                               <> total_buy_value - total_sell_value),
              count(*) FILTER (WHERE top_buyer_net_value IS NULL),
              count(*) FILTER (WHERE top_seller_net_value IS NULL),
              count(*) FILTER (WHERE top3_buyer_share IS NULL),
              count(*) FILTER (WHERE broker_concentration_hhi IS NULL)
            FROM public."Feature_03_Stock_Broker_Daily"
        """).fetchone()
        violation_count = sum(sanity[:6])
        failures += violation_count != 0
        print(f"sanity_violations={sanity[:6]} null_counts_top_buyer_top_seller_top3_hhi={sanity[6:]} "
              f"{'PASS' if violation_count == 0 else 'FAIL'}")

        connection.rollback()

    print(f"overall={'PASS' if failures == 0 else 'FAIL'} failures={failures}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
