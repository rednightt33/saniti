#!/usr/bin/env python3
"""Reverify the latest completed IDX sessions, oldest first, and report older sessions short of stocks; and the
session audit (`audit_sessions`) that the scheduled recovery runs after `price_update.py --mode recovery`.

ERRORS M238: 2026-09-17 and 2026-09-18 were never refilled because the window was read from the dates already stored,
so a session without a single stored row never became a target. The sessions now come from TradingView's own daily
candles of the universe's index symbols (the calendar as traded), with the stored dates as the fallback:
- inside the correction window (`correction_lookback_sessions`) every calendar session is reverified for the full
  universe, so a wholly missing session is filled like a stored one;
- an older session of the audit window (AUDIT_SESSIONS) whose stored stock count is below SHORT_SESSION_RATIO of the
  median count is not written here, because a back-dated insert older than the window needs the Feature 04 repair
  (ERRORS D26). It is reported once instead: a RECOVERY row with status NEEDS_REVIEW in Monitoring_Price_ALL and its
  Telegram notice.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import psycopg

from price_update import (
    JAKARTA,
    commit_monitoring_and_notify,
    latest_completed_session,
    monitoring_records,
    open_socket,
    read_market_schedule,
    read_universe,
    request_symbol,
    resolve_trigger_source,
    start_chart_session,
)


PRICE_TABLE = 'public."Price_Stock_Indonesia_IDX"'
MONITORING_TABLE = 'public."Monitoring_Price_ALL"'
# Sessions the recovery audits for short stock coverage (about three months); only the reported ones, never written.
AUDIT_SESSIONS = 60
# A session is short when its stored stock count is below this share of the median count of the audited sessions
# (a normal day misses only the stocks without a candle, about 2 % on 2026-09 to 10).
SHORT_SESSION_RATIO = 0.9
SHORT_SESSION_ERROR = "SHORT_SESSION"


def correction_target_dates(
    observed: list[date], latest_candidate: date, session_count: int
) -> list[date]:
    """Return recent observed sessions plus an unobserved latest candidate."""
    selected = sorted(set(item for item in observed if item <= latest_candidate))[-session_count:]
    if latest_candidate not in selected:
        selected.append(latest_candidate)
    return sorted(set(selected))


def calendar_window(calendar: list[date], latest: date, session_count: int) -> list[date]:
    """The latest `session_count` calendar sessions on or before `latest`."""
    return sorted(day for day in set(calendar) if day <= latest)[-session_count:]


def recovery_targets(
    observed: list[date], calendar: list[date], latest: date, session_count: int
) -> list[date]:
    """The stored-dates window (correction_target_dates) plus every calendar session of the window, oldest first."""
    return sorted(
        set(correction_target_dates(observed, latest, session_count))
        | set(calendar_window(calendar, latest, session_count))
    )


def short_sessions(
    calendar: list[date], counts: dict[date, int], window: set[date], ratio: float = SHORT_SESSION_RATIO
) -> list[tuple[date, int, int]]:
    """Calendar sessions outside `window` whose stored stock count is below `ratio` of the median count over the
    calendar sessions, as (session, stored, median)."""
    sessions = sorted(set(calendar))
    if not sessions:
        return []
    values = sorted(counts.get(day, 0) for day in sessions)
    median = values[len(values) // 2]
    return [
        (day, counts.get(day, 0), median)
        for day in sessions
        if day not in window and counts.get(day, 0) < ratio * median
    ]


def refill_sessions(
    calendar: list[date], counts: dict[date, int], window: set[date], latest: date,
    ratio: float = SHORT_SESSION_RATIO,
) -> list[date]:
    """Short calendar sessions inside the correction window other than `latest` (the recovery run itself takes the
    latest session): the audit recovers their missing stocks."""
    return [day for day, _, _ in short_sessions(calendar, counts, set(), ratio) if day in window and day != latest]


def tradingview_bars(symbol, bars: int) -> list[dict]:
    ws = open_socket(30.0, False)
    try:
        chart = start_chart_session(ws)
        return request_symbol(ws, chart, symbol, bars, 30.0, datetime.now(JAKARTA).date())
    finally:
        ws.close()


def index_calendar(symbols, latest: date, bars: int, fetch=tradingview_bars) -> list[date]:
    """Session dates on or before `latest` from the daily candles of the first index symbol that answers; [] when
    none does."""
    for symbol in symbols:
        try:
            dates = sorted({row["date"] for row in fetch(symbol, bars) if row["date"] <= latest})
        except Exception as exc:  # noqa: BLE001 - the next index, then the stored dates, stand in
            print(json.dumps({"event": "calendar_index_failed", "ticker": symbol.ticker,
                              "error": f"{type(exc).__name__}: {exc}"[:300]}), flush=True)
            continue
        if dates:
            return dates
    return []


def load_plan(database_url: str, fetch=tradingview_bars) -> dict:
    now = datetime.now(timezone.utc)
    with psycopg.connect(database_url) as connection:
        schedule = read_market_schedule(connection)
        latest = latest_completed_session(schedule, now)
        lookback = schedule.correction_lookback_sessions
        observed = [row[0] for row in connection.execute(
            f"""
            SELECT DISTINCT date
            FROM {PRICE_TABLE}
            WHERE timeframe='Daily' AND is_final AND date <= %s
            ORDER BY date DESC
            LIMIT %s
            """,
            (latest, max(lookback, AUDIT_SESSIONS)),
        ).fetchall()]
        universe = read_universe(connection)
        calendar = index_calendar(
            [s for s in universe if s.asset_type == "index"], latest, AUDIT_SESSIONS + lookback + 5, fetch
        )
        source = "tradingview_index"
        if not calendar:
            calendar, source = sorted(observed), "stored_dates"
        calendar = sorted(calendar)[-AUDIT_SESSIONS:]
        window = calendar_window(calendar, latest, lookback)
        targets = recovery_targets(observed, calendar, latest, lookback)
        counts = dict(connection.execute(
            f"""
            SELECT date, count(*)
            FROM {PRICE_TABLE}
            WHERE timeframe='Daily' AND is_final AND date >= %s AND NOT public.is_universe_index(ticker)
            GROUP BY date
            """,
            (calendar[0],),
        ).fetchall()) if calendar else {}
        short = short_sessions(calendar, counts, set(window))
        reported = {row[0] for row in connection.execute(
            f"""
            SELECT DISTINCT update_for_date
            FROM {MONITORING_TABLE}
            WHERE run_type='RECOVERY' AND status='NEEDS_REVIEW' AND last_error LIKE %s
              AND update_for_date = ANY(%s)
            """,
            (SHORT_SESSION_ERROR + "%", [day for day, _, _ in short]),
        ).fetchall()} if short else set()
    return {
        "targets": targets, "lookback": lookback, "calendar": calendar, "calendar_source": source,
        "short": [item for item in short if item[0] not in reported], "already_reported": sorted(reported),
        "universe": universe, "latest": latest,
        "refill": refill_sessions(calendar, counts, set(window), latest),
    }


def report_short_sessions(database_url: str, plan: dict) -> None:
    """One NEEDS_REVIEW monitoring row (and its Telegram notice) per newly found short session."""
    stocks = [s for s in plan["universe"] if s.asset_type != "index"]
    with psycopg.connect(database_url) as connection:
        for day, stored, median in plan["short"]:
            now = datetime.now(timezone.utc)
            execution_id = str(uuid.uuid4())
            records = monitoring_records(
                stocks, [], [], "RECOVERY", day, now, now, execution_id,
                resolve_trigger_source("recovery", now.astimezone(JAKARTA)), now,
                forced_status="NEEDS_REVIEW",
                forced_error=(
                    f"{SHORT_SESSION_ERROR}: {stored} stocks stored, about {median} on a normal session; "
                    f"older than the {plan['lookback']}-session correction window, so not written automatically "
                    "(a back-dated insert needs the Feature 04 repair, ERRORS D26 and M238)"
                ),
            )
            commit_monitoring_and_notify(connection, records, execution_id)


def audit_sessions(database_url: str) -> int:
    """S7, run after the scheduled `price_update.py --mode recovery` (the live recovery start command since
    2026-10-13, which recovers the latest session only): a short session inside the correction window gets the same
    recovery for its missing stocks; an older short session is reported once. Returns 1 when a recovery run failed."""
    plan = load_plan(database_url)
    print(json.dumps({
        "event": "session_audit", "calendar_source": plan["calendar_source"], "calendar_sessions": len(plan["calendar"]),
        "refill": plan["refill"], "short_sessions": plan["short"], "short_already_reported": plan["already_reported"],
    }, default=str), flush=True)
    script = Path(__file__).with_name("price_update.py")
    failed = []
    for target in plan["refill"]:
        result = subprocess.run(
            [sys.executable, str(script), "--mode", "recovery", "--target-date", target.isoformat(),
             "--request-bars", str(max(plan["lookback"] + 2, 7))],
            check=False,
        )
        if result.returncode:
            failed.append(target.isoformat())
    if plan["short"]:
        report_short_sessions(database_url, plan)
    if failed:
        print(f"IDX session audit recovery failed for sessions: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")
    plan = load_plan(database_url)
    print(json.dumps({
        "event": "recovery_plan", "targets": plan["targets"], "calendar_source": plan["calendar_source"],
        "calendar_sessions": len(plan["calendar"]),
        "calendar_first": plan["calendar"][0] if plan["calendar"] else None,
        "short_sessions": plan["short"], "short_already_reported": plan["already_reported"],
        "audit_refill": plan["refill"], "latest": plan["latest"],
    }, default=str), flush=True)
    if "--plan-only" in sys.argv[1:]:   # read-only check: no price run, no report
        return 0
    script = Path(__file__).with_name("price_update.py")
    request_bars = max(plan["lookback"] + 2, 7)
    failures: list[str] = []
    for target in plan["targets"]:
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
    if plan["short"]:
        report_short_sessions(database_url, plan)
    if failures:
        print(f"IDX recovery failed for sessions: {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
