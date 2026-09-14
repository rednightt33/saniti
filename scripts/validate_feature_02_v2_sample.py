#!/usr/bin/env python3
"""Validate a shadow ticker and independently recalculate both Investor Types."""

from __future__ import annotations

import argparse
import os
import statistics
from datetime import date
from decimal import Decimal

import psycopg
from psycopg.rows import dict_row


NUMERIC_FIELDS = (
    "buy_value_1d", "sell_value_1d", "net_value_1d",
    "buy_lots_1d", "sell_lots_1d", "net_lots_1d",
    "net_value_5d", "net_value_20d", "net_value_60d",
    "net_lots_5d", "net_lots_20d", "net_lots_60d",
    "buy_days_20d", "sell_days_20d", "active_days_20d",
    "stock_trading_days_20d", "buy_day_ratio_20d", "buy_share_active_days_20d",
    "buy_days_60d", "sell_days_60d", "active_days_60d",
    "stock_trading_days_60d", "buy_day_ratio_60d", "buy_share_active_days_60d",
    "net_value_zscore_20d", "net_value_zscore_60d",
    "net_value_percentile_20d", "net_value_percentile_60d",
    "positive_net_value_20d", "largest_buy_day_20d",
    "largest_buy_day_share_20d",
)


def equal(expected: object, actual: object) -> tuple[bool, object]:
    if expected is None or actual is None:
        return expected is None and actual is None, None
    if isinstance(expected, float):
        difference = abs(expected - float(actual))
        return difference <= 1e-8 * max(1.0, abs(expected)), difference
    difference = expected - actual
    return difference == 0, difference


def expected_for_key(db, ticker: str, broker: str, investor_type: str,
                     board: str, target_date: date) -> dict[str, object]:
    days = [row["date"] for row in db.execute(
        'SELECT DISTINCT "Date" AS date FROM public."IDX_Broker_Summary" '
        'WHERE "Symbol"=%s AND "Date"<=%s ORDER BY "Date" DESC LIMIT 312',
        (ticker, target_date),
    )]
    if not days or days[0] != target_date:
        raise RuntimeError("Ticker has no source transaction date at sample date")
    days.reverse()
    raw = {row["date"]: (
        row["buy_value"], row["sell_value"], row["buy_lots"], row["sell_lots"]
    ) for row in db.execute(
        'SELECT "Date" AS date, sum("Buy Value") AS buy_value, '
        'sum("Sell Value") AS sell_value, sum("Buy Lots") AS buy_lots, '
        'sum("Sell Lots") AS sell_lots '
        'FROM public."IDX_Broker_Summary" '
        'WHERE "Symbol"=%s AND "Broker"=%s AND "Investor Type"=%s '
        'AND "Market Board"=%s AND "Date">=%s AND "Date"<=%s GROUP BY "Date"',
        (ticker, broker, investor_type, board, days[0], target_date),
    )}
    if target_date not in raw:
        raise RuntimeError(f"No source sample for Investor Type {investor_type}")
    zero = Decimal(0)
    daily = [raw.get(day, (zero, zero, zero, zero)) for day in days]
    values = [item[0] - item[1] for item in daily]
    lots = [item[2] - item[3] for item in daily]
    active = [int(any(value > 0 for value in item)) for item in daily]
    n = len(days)
    expected: dict[str, object] = {
        "buy_value_1d": daily[-1][0], "sell_value_1d": daily[-1][1],
        "net_value_1d": values[-1], "buy_lots_1d": daily[-1][2],
        "sell_lots_1d": daily[-1][3], "net_lots_1d": lots[-1],
    }
    for window in (5, 20, 60):
        expected[f"net_value_{window}d"] = sum(values[-window:], zero) if n >= window else None
        expected[f"net_lots_{window}d"] = sum(lots[-window:], zero) if n >= window else None
    for window in (20, 60):
        enough = n >= window
        current_values = values[-window:]
        buys = sum(value > 0 for value in current_values)
        sells = sum(value < 0 for value in current_values)
        active_days = sum(active[-window:])
        expected[f"buy_days_{window}d"] = buys if enough else None
        expected[f"sell_days_{window}d"] = sells if enough else None
        expected[f"active_days_{window}d"] = active_days if enough else None
        expected[f"stock_trading_days_{window}d"] = window if enough else None
        expected[f"buy_day_ratio_{window}d"] = buys / window if enough else None
        expected[f"buy_share_active_days_{window}d"] = (
            buys / active_days if enough and active_days else None
        )
        history = [
            sum(values[pos-window+1:pos+1], zero)
            for pos in range(window-1, n-1)
        ][-252:]
        if len(history) == 252:
            current = expected[f"net_value_{window}d"]
            history_floats = [float(value) for value in history]
            std = statistics.stdev(history_floats)
            expected[f"net_value_zscore_{window}d"] = (
                (float(current) - statistics.mean(history_floats)) / std if std > 0 else None
            )
            expected[f"net_value_percentile_{window}d"] = 100 * (
                sum(value < current for value in history)
                + 0.5 * sum(value == current for value in history)
            ) / 252
        else:
            expected[f"net_value_zscore_{window}d"] = None
            expected[f"net_value_percentile_{window}d"] = None
    if n >= 20:
        positives = [value for value in values[-20:] if value > 0]
        total = sum(positives, zero)
        largest = max(positives) if positives else None
        expected["positive_net_value_20d"] = total
        expected["largest_buy_day_20d"] = largest
        expected["largest_buy_day_share_20d"] = float(largest / total) if total else None
    else:
        expected.update({
            "positive_net_value_20d": None,
            "largest_buy_day_20d": None,
            "largest_buy_day_share_20d": None,
        })
    return expected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--ticker", default="BBCA")
    parser.add_argument("--broker", default="AK")
    parser.add_argument("--board", default="Regular", choices=("Regular", "Nego", "Tunai"))
    parser.add_argument("--date", default="2026-08-31", type=date.fromisoformat)
    args = parser.parse_args()
    failures = 0
    with psycopg.connect(
        host=args.host, port=args.port, dbname=os.environ["PGDATABASE"],
        user=os.environ["PGUSER"], password=os.environ["PGPASSWORD"],
        sslmode="require", row_factory=dict_row,
        application_name="feature-02-v2-sample-validation",
    ) as db:
        db.execute("SET statement_timeout = '10min'")
        reconciliation = db.execute(
            '''
            WITH source AS (
              SELECT "Date" AS date, "Symbol"::text AS ticker,
                     "Broker"::text AS broker, "Investor Type"::text AS investor_type,
                     "Market Board"::text AS market_board,
                     sum("Buy Value") AS buy_value_1d,
                     sum("Sell Value") AS sell_value_1d,
                     sum("Buy Lots") AS buy_lots_1d,
                     sum("Sell Lots") AS sell_lots_1d
              FROM public."IDX_Broker_Summary" WHERE "Symbol"=%s
              GROUP BY 1,2,3,4,5
            )
            SELECT count(*) FILTER (WHERE s.date IS NULL) AS extra,
                   count(*) FILTER (WHERE f.date IS NULL) AS missing,
                   count(*) FILTER (WHERE s.date IS NOT NULL AND f.date IS NOT NULL
                     AND (s.buy_value_1d<>f.buy_value_1d OR s.sell_value_1d<>f.sell_value_1d
                       OR s.buy_lots_1d<>f.buy_lots_1d OR s.sell_lots_1d<>f.sell_lots_1d)) AS mismatch
            FROM source s FULL JOIN public."Feature_02_Broker_Rolling_v2" f
              USING (date,ticker,broker,investor_type,market_board)
            WHERE coalesce(s.ticker,f.ticker)=%s
            ''', (args.ticker, args.ticker),
        ).fetchone()
        reconciliation_pass = tuple(reconciliation.values()) == (0, 0, 0)
        failures += not reconciliation_pass
        print(f"ticker_reconciliation={dict(reconciliation)} "
              f"{'PASS' if reconciliation_pass else 'FAIL'}")
        types = [row["investor_type"] for row in db.execute(
            '''SELECT DISTINCT investor_type FROM public."Feature_02_Broker_Rolling_v2"
               WHERE ticker=%s AND broker=%s AND market_board=%s AND date=%s
               ORDER BY investor_type''',
            (args.ticker, args.broker, args.board, args.date),
        )]
        for investor_type in types:
            expected = expected_for_key(
                db, args.ticker, args.broker, investor_type, args.board, args.date
            )
            stored = db.execute(
                'SELECT * FROM public."Feature_02_Broker_Rolling_v2" '
                'WHERE ticker=%s AND broker=%s AND investor_type=%s '
                'AND market_board=%s AND date=%s',
                (args.ticker, args.broker, investor_type, args.board, args.date),
            ).fetchone()
            type_failures = 0
            for field in NUMERIC_FIELDS:
                passed, difference = equal(expected[field], stored[field])
                type_failures += not passed
                print(f"investor_type={investor_type} field={field} "
                      f"expected={expected[field]} stored={stored[field]} "
                      f"difference={difference} {'PASS' if passed else 'FAIL'}")
            failures += type_failures
            print(f"investor_type={investor_type} fields={len(NUMERIC_FIELDS)} "
                  f"failures={type_failures}")
        expected_types = {"Domestic", "Foreign"}
        type_coverage_pass = set(types) == expected_types
        failures += not type_coverage_pass
        print(f"sample_investor_types={types} "
              f"{'PASS' if type_coverage_pass else 'FAIL'}")
        db.rollback()
    print(f"overall={'PASS' if failures == 0 else 'FAIL'} failures={failures}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
