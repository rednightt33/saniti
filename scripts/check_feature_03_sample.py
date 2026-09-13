#!/usr/bin/env python3
"""Independently calculate one Feature 03 row from raw Broker Summary."""

from __future__ import annotations

import argparse
import os
from collections import defaultdict
from decimal import Decimal

import psycopg
from psycopg.rows import dict_row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--board", required=True, choices=("Regular", "Nego", "Tunai"))
    parser.add_argument("--date", required=True)
    args = parser.parse_args()

    with psycopg.connect(
        host=args.host, port=args.port, dbname=os.environ["PGDATABASE"],
        user=os.environ["PGUSER"], password=os.environ["PGPASSWORD"],
        sslmode="require", row_factory=dict_row,
        application_name="feature-03-independent-sample",
    ) as connection:
        source = connection.execute("""
            SELECT s."Broker" AS broker,
                   p.broker_type, p.broker_classification,
                   sum(s."Buy Value") AS buy_value,
                   sum(s."Sell Value") AS sell_value,
                   sum(s."Buy Lots") AS buy_lots,
                   sum(s."Sell Lots") AS sell_lots
            FROM public."IDX_Broker_Summary" AS s
            LEFT JOIN public."IDX_Broker_Profile" AS p
              ON p.broker_code = s."Broker"
            WHERE s."Date"=%s AND s."Symbol"=%s AND s."Market Board"=%s
            GROUP BY s."Broker", p.broker_type, p.broker_classification
        """, (args.date, args.ticker, args.board)).fetchall()
        stored = connection.execute("""
            SELECT * FROM public."Feature_03_Stock_Broker_Daily"
            WHERE date=%s AND ticker=%s AND market_board=%s
        """, (args.date, args.ticker, args.board)).fetchone()

    if not source or stored is None:
        raise SystemExit("Source or stored sample row is missing")

    brokers = []
    type_flow = defaultdict(Decimal)
    class_flow = defaultdict(Decimal)
    for row in source:
        net = row["buy_value"] - row["sell_value"]
        active = any(row[name] != 0 for name in ("buy_value", "sell_value", "buy_lots", "sell_lots"))
        brokers.append((row["broker"], net, active, row["buy_value"], row["sell_value"]))
        type_flow[row["broker_type"]] += net
        class_flow[row["broker_classification"]] += net

    positive = sorted(((code, net) for code, net, *_ in brokers if net > 0), key=lambda x: (-x[1], x[0]))
    negative = sorted(((code, net) for code, net, *_ in brokers if net < 0), key=lambda x: (x[1], x[0]))
    active_count = sum(active for _, _, active, _, _ in brokers)
    buy_count = len(positive)
    sell_count = len(negative)
    positive_total = sum((net for _, net in positive), Decimal(0))
    top3 = sum((net for _, net in positive[:3]), Decimal(0))
    absolute_total = sum((abs(net) for _, net, *_ in brokers), Decimal(0))
    squared_total = sum((net * net for _, net, *_ in brokers), Decimal(0))

    expected = {
        "total_buy_value": sum((buy for *_, buy, _ in brokers), Decimal(0)),
        "total_sell_value": sum((sell for *_, sell in brokers), Decimal(0)),
        "active_broker_count": active_count,
        "net_buy_broker_count": buy_count,
        "net_sell_broker_count": sell_count,
        "net_buy_broker_ratio": buy_count / active_count if active_count else None,
        "foreign_net_value": type_flow["Foreign"],
        "domestic_net_value": type_flow["Domestic"],
        "institutional_net_value": class_flow["Institutional-heavy"],
        "retail_net_value": class_flow["Retail-heavy"],
        "mixed_net_value": class_flow["Mixed"],
        "niche_net_value": class_flow["Niche"],
        "top_buyer": positive[0][0] if positive else None,
        "top_buyer_net_value": positive[0][1] if positive else None,
        "top_seller": negative[0][0] if negative else None,
        "top_seller_net_value": negative[0][1] if negative else None,
        "top3_buyer_net_value": top3,
        "positive_net_value_total": positive_total,
        "top3_buyer_share": float(top3 / positive_total) if positive_total else None,
        "broker_concentration_hhi": float(squared_total / (absolute_total * absolute_total)) if absolute_total else None,
    }
    failures = 0
    for field, wanted in expected.items():
        actual = stored[field]
        if isinstance(wanted, float):
            difference = None if actual is None else abs(float(actual) - wanted)
            passed = difference is not None and difference <= 1e-12
        else:
            difference = None if wanted is None or actual is None else actual - wanted if isinstance(wanted, Decimal) else None
            passed = actual == wanted
        failures += not passed
        print(f"{field}: expected={wanted} stored={actual} difference={difference} {'PASS' if passed else 'FAIL'}")

    print(f"ticker={args.ticker} board={args.board} date={args.date} brokers={len(source)} "
          f"fields={len(expected)} failures={failures}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
