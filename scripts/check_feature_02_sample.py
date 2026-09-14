#!/usr/bin/env python3
"""Independently recalculate one Feature 02 row from raw Broker Summary.

At most 312 ticker transaction dates and one broker-board's daily source sums
leave PostgreSQL. This deliberately does not reuse the Feature 02 SQL routine.
"""

from __future__ import annotations

import argparse
import os
import statistics
from datetime import date
from decimal import Decimal

import psycopg


COMPARE_FIELDS = (
    "buy_value_1d", "sell_value_1d", "net_value_1d",
    "buy_lots_1d", "sell_lots_1d", "net_lots_1d",
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


def compare(expected: object, stored: object) -> tuple[bool, object]:
    if expected is None or stored is None:
        return expected is None and stored is None, None
    if isinstance(expected, float):
        difference = abs(expected - float(stored))
        return difference <= 1e-8 * max(1.0, abs(expected)), difference
    difference = expected - stored
    return difference == 0, difference


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--broker", required=True)
    parser.add_argument("--board", choices=("Regular", "Nego", "Tunai"), required=True)
    parser.add_argument("--date", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    with psycopg.connect(
        host=args.host, port=args.port,
        dbname=os.environ["PGDATABASE"], user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"], sslmode="require",
        application_name="feature-02-sample-check", autocommit=True,
    ) as db:
        if db.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_schema='public' "
            "AND table_name='Feature_02_Broker_Rolling' AND column_name='investor_type'"
        ).fetchone():
            raise RuntimeError(
                "This sample checker assumes merged investor types and is retired for v2; "
                "use scripts/validate_feature_02_v2_sample.py"
            )
        db.execute("SET statement_timeout = '10min'")
        days = [row[0] for row in db.execute(
            'SELECT DISTINCT "Date" FROM public."IDX_Broker_Summary" '
            'WHERE "Symbol"=%s AND "Date"<=%s '
            'ORDER BY "Date" DESC LIMIT 312',
            (args.ticker, args.date),
        )]
        if not days or days[0] != args.date:
            raise RuntimeError("Ticker has no source transaction date at the requested date")
        days.reverse()
        raw = {row[0]: row[1:] for row in db.execute(
            'SELECT "Date", sum("Buy Value"), sum("Sell Value"), '
            'sum("Buy Lots"), sum("Sell Lots") '
            'FROM public."IDX_Broker_Summary" '
            'WHERE "Symbol"=%s AND "Broker"=%s AND "Market Board"=%s '
            'AND "Date">=%s AND "Date"<=%s GROUP BY "Date"',
            (args.ticker, args.broker, args.board, days[0], args.date),
        )}
        if args.date not in raw:
            raise RuntimeError("No broker-board source row at the requested date")
        zero = Decimal(0)
        daily = [raw.get(day, (zero, zero, zero, zero)) for day in days]
        net_values = [item[0] - item[1] for item in daily]
        net_lots = [item[2] - item[3] for item in daily]
        active = [int(any(value > 0 for value in item)) for item in daily]
        n = len(days)
        expected: dict[str, object] = dict(zip(
            COMPARE_FIELDS[:6],
            (daily[-1][0], daily[-1][1], net_values[-1],
             daily[-1][2], daily[-1][3], net_lots[-1]),
        ))
        for window in (5, 20, 60):
            expected[f"net_value_{window}d"] = sum(net_values[-window:], zero) if n >= window else None
            expected[f"net_lots_{window}d"] = sum(net_lots[-window:], zero) if n >= window else None
        for window in (20, 60):
            enough = n >= window
            values = net_values[-window:]
            buys = sum(value > 0 for value in values)
            sells = sum(value < 0 for value in values)
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
                sum(net_values[pos-window+1:pos+1], zero)
                for pos in range(window-1, n-1)
            ][-252:]
            if len(history) == 252:
                current = expected[f"net_value_{window}d"]
                history_floats = [float(value) for value in history]
                std = statistics.stdev(history_floats)
                mean = statistics.mean(history_floats)
                expected[f"net_value_zscore_{window}d"] = (
                    (float(current) - mean) / std if std > 0 else None
                )
                expected[f"net_value_percentile_{window}d"] = 100 * (
                    sum(value < current for value in history)
                    + 0.5 * sum(value == current for value in history)
                ) / 252
            else:
                expected[f"net_value_zscore_{window}d"] = None
                expected[f"net_value_percentile_{window}d"] = None
        if n >= 20:
            positives = [value for value in net_values[-20:] if value > 0]
            positive_total = sum(positives, zero)
            largest = max(positives) if positives else None
            expected["positive_net_value_20d"] = positive_total
            expected["largest_buy_day_20d"] = largest
            expected["largest_buy_day_share_20d"] = (
                float(largest) / float(positive_total) if positive_total else None
            )
        else:
            expected.update({
                "positive_net_value_20d": None,
                "largest_buy_day_20d": None,
                "largest_buy_day_share_20d": None,
            })
        stored = db.execute(
            'SELECT buy_value_1d, sell_value_1d, net_value_1d, '
            'buy_lots_1d, sell_lots_1d, net_lots_1d, '
            'net_value_5d, net_value_20d, net_value_60d, '
            'net_lots_5d, net_lots_20d, net_lots_60d, '
            'buy_days_20d, sell_days_20d, active_days_20d, '
            'stock_trading_days_20d, buy_day_ratio_20d, '
            'buy_share_active_days_20d, '
            'buy_days_60d, sell_days_60d, active_days_60d, '
            'stock_trading_days_60d, buy_day_ratio_60d, '
            'buy_share_active_days_60d, '
            'net_value_zscore_20d, net_value_zscore_60d, '
            'net_value_percentile_20d, net_value_percentile_60d, '
            'positive_net_value_20d, largest_buy_day_20d, '
            'largest_buy_day_share_20d '
            'FROM public."Feature_02_Broker_Rolling" '
            'WHERE ticker=%s AND broker=%s AND market_board=%s AND date=%s',
            (args.ticker, args.broker, args.board, args.date),
        ).fetchone()
        if stored is None:
            raise RuntimeError("Feature row is missing")
        failures = 0
        for name, actual in zip(COMPARE_FIELDS, stored):
            passed, difference = compare(expected[name], actual)
            failures += not passed
            print(
                f"{name}: expected={expected[name]} stored={actual} "
                f"difference={difference} {'PASS' if passed else 'FAIL'}",
                flush=True,
            )
        print(
            f"ticker={args.ticker} broker={args.broker} board={args.board} "
            f"date={args.date} source_calendar_days_fetched={n} "
            f"fields={len(COMPARE_FIELDS)} failures={failures}",
            flush=True,
        )
        if failures:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
