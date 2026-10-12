#!/usr/bin/env python3
"""Build recent Feature04 checkpoints and prove suffix parity before rollout."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "features" / "feature04"))

from engine import FEATURE_COLUMNS, calculate
from incremental import calculate_incremental, build_recent_checkpoints
from worker import Job, connect, load_history, replace_checkpoints


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def equal_value(left, right) -> bool:
    if left is None or right is None:
        return left is right
    if isinstance(left, (int, bool)) and isinstance(right, (int, bool)):
        return left == right
    try:
        left_value, right_value = float(left), float(right)
    except (TypeError, ValueError):
        return left == right
    return abs(left_value - right_value) <= 1e-10 + 1e-12 * abs(right_value)


def validate_recent(
    connection, asset_type: str, ticker: str, history: list[dict], states: list[dict],
    lookback_sessions: int,
) -> None:
    if len(history) < 2:
        return
    suffix_size = min(lookback_sessions, len(history) - 1)
    checkpoint = states[-suffix_size - 1]
    suffix = history[-suffix_size:]
    stamp = datetime.now(timezone.utc)
    reference = calculate(history, calculated_at=stamp)[-suffix_size:]
    calculated, outcomes, _, _ = calculate_incremental(
        suffix, checkpoint=checkpoint, calculated_at=stamp
    )
    if any(value["status"] != "SUCCESS" for value in outcomes.values()):
        raise RuntimeError(f"Incremental shadow formula failure for {asset_type}/{ticker}")
    for actual, expected in zip(calculated, reference):
        if actual["trade_date"] != expected["trade_date"]:
            raise RuntimeError(f"Incremental/full date mismatch for {asset_type}/{ticker}")
        for column in FEATURE_COLUMNS:
            if not equal_value(actual[column], expected[column]):
                raise RuntimeError(
                    f"Incremental/full mismatch {asset_type}/{ticker}/"
                    f"{actual['trade_date']}/{column}: {actual[column]!r} != "
                    f"{expected[column]!r}"
                )
    stored = connection.execute(
        'SELECT * FROM public."Feature_04_Technical_Indicator" '
        "WHERE asset_type=%s AND ticker=%s AND timeframe='Daily' AND trade_date>= %s "
        "ORDER BY trade_date",
        (asset_type, ticker, suffix[0]["date"]),
    ).fetchall()
    if len(stored) != len(calculated):
        raise RuntimeError(
            f"Shadow row-count mismatch for {asset_type}/{ticker}: "
            f"{len(calculated)} calculated vs {len(stored)} stored"
        )
    for expected, actual in zip(reference, stored):
        if expected["trade_date"] != actual["trade_date"]:
            raise RuntimeError(f"Shadow date mismatch for {asset_type}/{ticker}")
        for column in FEATURE_COLUMNS:
            if not equal_value(expected[column], actual[column]):
                raise RuntimeError(
                    f"Stored/full mismatch {asset_type}/{ticker}/{actual['trade_date']}/{column}: "
                    f"{actual[column]!r} != {expected[column]!r}"
                )


def main() -> int:
    args = parse_args()
    with connect() as connection:
        if connection.execute(
            'SELECT EXISTS(SELECT 1 FROM public."Feature04_Calculation_Queue" '
            "WHERE status='PROCESSING')"
        ).fetchone()["exists"]:
            raise RuntimeError("Feature04 worker has an active claim")
        instruments = connection.execute(
            """
            SELECT 'equity'::text AS asset_type,u."Ticker" AS ticker
            FROM public."IDX_Stock_Universe" u
            WHERE EXISTS(
              SELECT 1 FROM public."Price_Stock_Indonesia_IDX" p
              WHERE p.ticker=u."Ticker" AND p.timeframe='Daily' AND p.is_final
            )
            UNION ALL
            SELECT 'bonds',u.ticker
            FROM public."Universe_Fixed_income" u
            WHERE u.metric_type='price' AND EXISTS(
              SELECT 1 FROM public."Price_Fixed_Income" p
              WHERE p.ticker=u.ticker AND p.metric_type='price'
                AND p."Timeframe"='1D' AND p.is_final
            )
            ORDER BY asset_type,ticker
            """
        ).fetchall()
    if args.ticker:
        instruments = [row for row in instruments if row["ticker"] == args.ticker.upper()]
    if args.limit:
        instruments = instruments[: args.limit]
    completed = 0
    for instrument in instruments:
        asset_type, ticker = instrument["asset_type"], instrument["ticker"]
        with connect() as connection:
            history = load_history(connection, asset_type, ticker)
            if asset_type == "equity":
                policy = connection.execute(
                    'SELECT correction_lookback_sessions FROM public."Equity_Market_Schedule" '
                    "WHERE market_code='IDX' AND enabled"
                ).fetchone()
            else:
                policy = connection.execute(
                    'SELECT DISTINCT s.correction_lookback_sessions '
                    'FROM public."Universe_Fixed_income" u '
                    'JOIN public."Fixed_Income_Market_Schedule" s ON s.country=u.country '
                    "WHERE u.ticker=%s AND u.metric_type='price' AND s.enabled",
                    (ticker,),
                ).fetchone()
            if policy is None:
                raise RuntimeError(f"No correction policy for {asset_type}/{ticker}")
            lookback_sessions = int(policy["correction_lookback_sessions"])
            retention = lookback_sessions + 2
            states = build_recent_checkpoints(history, retain=retention)
            validate_recent(
                connection, asset_type, ticker, history, states, lookback_sessions
            )
        if not args.dry_run:
            dummy = Job(
                asset_type=asset_type, ticker=ticker, dirty_from_date=history[-1]["date"],
                requested_generation=0, work_revision=0, requested_columns=None,
                origin_execution_id=None, attempt_no=0, source_attempt_count=0,
                claim_token=None, started_at=datetime.now(timezone.utc),
            )
            with connect() as connection, connection.transaction():
                replace_checkpoints(connection, dummy, states, retention)
        completed += 1
        if completed % 50 == 0 or completed == len(instruments):
            print(json.dumps({"event": "checkpoint_progress", "completed": completed,
                              "total": len(instruments), "ticker": ticker}), flush=True)
    print(json.dumps({"event": "checkpoint_bootstrap_completed", "instruments": completed,
                      "dry_run": args.dry_run}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
