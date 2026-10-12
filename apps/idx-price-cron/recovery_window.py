#!/usr/bin/env python3
"""Reverify the five latest completed IDX sessions, oldest first."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import psycopg

from price_update import latest_completed_session, read_market_schedule


PRICE_TABLE = 'public."Price_Stock_Indonesia_IDX"'


def correction_target_dates(
    observed: list[date], latest_candidate: date, session_count: int
) -> list[date]:
    """Return recent observed sessions plus an unobserved latest candidate."""
    selected = sorted(set(item for item in observed if item <= latest_candidate))[-session_count:]
    if latest_candidate not in selected:
        selected.append(latest_candidate)
    return sorted(set(selected))


def load_targets(database_url: str) -> tuple[list[date], int]:
    now = datetime.now(timezone.utc)
    with psycopg.connect(database_url) as connection:
        schedule = read_market_schedule(connection)
        latest = latest_completed_session(schedule, now)
        rows = connection.execute(
            f"""
            SELECT DISTINCT date
            FROM {PRICE_TABLE}
            WHERE timeframe='Daily' AND is_final AND date <= %s
            ORDER BY date DESC
            LIMIT %s
            """,
            (latest, schedule.correction_lookback_sessions),
        ).fetchall()
    return (
        correction_target_dates(
            [row[0] for row in rows], latest, schedule.correction_lookback_sessions
        ),
        schedule.correction_lookback_sessions,
    )


def main() -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")
    targets, lookback = load_targets(database_url)
    script = Path(__file__).with_name("price_update.py")
    request_bars = max(lookback + 2, 7)
    failures: list[str] = []
    for target in targets:
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "--mode",
                "recovery",
                "--target-date",
                target.isoformat(),
                "--request-bars",
                str(request_bars),
                "--reverify-all",
            ],
            check=False,
        )
        if result.returncode:
            failures.append(target.isoformat())
    if failures:
        print(f"IDX recovery failed for sessions: {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
