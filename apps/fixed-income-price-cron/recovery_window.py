#!/usr/bin/env python3
"""Reverify the five latest completed fixed-income sessions, oldest first."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import psycopg

from fixed_income_update import latest_completed_session, read_schedule


PRICE_TABLE = 'public."Price_Fixed_Income"'


def correction_target_dates(
    observed: list[date], latest_candidate: date, session_count: int
) -> list[date]:
    if session_count < 1:
        raise ValueError("session_count must be positive")
    selected = {item for item in observed if item <= latest_candidate}
    latest_observed = max(selected, default=None)
    candidate = latest_candidate
    # Include missing recent weekday candidates, not only dates already stored.
    # A provider holiday is reported as NO_CURRENT_CANDLE, never filled by old data.
    for _ in range(session_count):
        while candidate.weekday() >= 5:
            candidate -= timedelta(days=1)
        if latest_observed is None or candidate > latest_observed:
            selected.add(candidate)
        candidate -= timedelta(days=1)
    return sorted(selected)[-session_count:]


def load_targets(database_url: str, market_code: str) -> tuple[list[date], int]:
    now = datetime.now(timezone.utc)
    with psycopg.connect(database_url) as connection:
        schedule = read_schedule(connection, market_code)
        latest = latest_completed_session(schedule, now)
        rows = connection.execute(
            f"""
            SELECT DISTINCT date
            FROM {PRICE_TABLE}
            WHERE "Country"=%s AND metric_type='price' AND is_final AND date <= %s
            ORDER BY date DESC
            LIMIT %s
            """,
            (schedule.country, latest, schedule.correction_lookback_sessions),
        ).fetchall()
    return (
        correction_target_dates(
            [row[0] for row in rows], latest, schedule.correction_lookback_sessions
        ),
        schedule.correction_lookback_sessions,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market", required=True)
    args = parser.parse_args()
    market_code = args.market.strip().upper()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")
    targets, lookback = load_targets(database_url, market_code)
    script = Path(__file__).with_name("fixed_income_update.py")
    request_bars = max(lookback + 2, 7)
    failures: list[str] = []
    for target in targets:
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "--market",
                market_code,
                "--mode",
                "recovery",
                "--target-date",
                target.isoformat(),
                "--request-bars",
                str(request_bars),
            ],
            check=False,
        )
        if result.returncode:
            failures.append(target.isoformat())
    if failures:
        print(
            f"{market_code} fixed-income recovery failed for sessions: "
            f"{', '.join(failures)}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
