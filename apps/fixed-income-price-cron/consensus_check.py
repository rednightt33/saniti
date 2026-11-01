"""Weekly consensus check of Price_Fixed_Income against the source (EXEC-FI-DATE B, ERRORS M324).

User go 2026-11-01 ("Usulan B", report only): every stored series is compared with PULLS fresh TradingView pulls taken
with the loader's own client and date rule, and the result goes to Telegram. Nothing is written.

Why several pulls: TVC:US10Y yield answers two different 2016-2024 histories by turn (measured 2026-11-01: a dry run at
10:54 UTC saw both, three pulls at 11:14 UTC all gave the other one), so one pull, or three back to back, is not "the
source". The pulls are taken in rounds over the whole market (round 1 every series, then round 2, ...), so the pulls of
one series lie minutes apart.

Per date, inside [the series' first stored date, the market's latest completed session]:
  - kept      the stored bar equals one of the pulled versions;
  - revised   stored, unlike every version, and all pulls agree on one bar;
  - missing   not stored, and all pulls have it with one bar;
  - extra     stored, and no pull has it (inside the range every pull covers);
  - unstable  anything else: the pulls disagree, or only some have the date.
Only "revised", "missing" and "extra" ask for a correction; that stays a decision of the user
(verification/fixed_income_audit/correct_job.py with the approved list).

Runs from the recovery role on the market's local Saturday (`WEEKDAY`; no session to load, the week is complete), or on
demand with `fixed_income_update.py --market ID --mode consensus`. The loader module is passed in, not imported, so the
check uses exactly the client and rules of the run that calls it.
"""

from __future__ import annotations

import json
import time
from datetime import date, datetime, timezone

PULLS = 3
WEEKDAY = 5                      # Saturday, in the market's own zone
MAX_ITEMS = 25                   # series/kind lines in one Telegram report
KINDS = ("revised", "missing", "extra", "unstable")
SOURCE_TABLE = "Fixed_Income_Consensus_Check"


def same_bar(a: tuple, b: tuple) -> bool:
    return all(abs(float(x) - float(y)) <= max(1e-9, abs(float(y)) * 1e-9) for x, y in zip(a, b))


def compare_series(stored: dict[date, tuple], pulls: list[dict[date, tuple]], last: date) -> dict[str, list[date]]:
    """Dates of one series by kind (module docstring). `stored` and each pull map a date to (open, high, low, close)."""
    found: dict[str, list[date]] = {kind: [] for kind in KINDS}
    if not stored or not pulls or not all(pulls):
        return found
    first = min(stored)
    covered_from = max(min(pull) for pull in pulls)
    for day in sorted(set(stored) | set().union(*pulls)):
        if day < first or day > last:
            continue
        versions = [pull[day] for pull in pulls if day in pull]
        bar = stored.get(day)
        if bar is not None and any(same_bar(bar, version) for version in versions):
            continue
        agree = len(versions) == len(pulls) and all(same_bar(v, versions[0]) for v in versions)
        if bar is None and agree:
            found["missing"].append(day)
        elif bar is not None and agree:
            found["revised"].append(day)
        elif bar is not None and not versions and day >= covered_from:
            found["extra"].append(day)
        elif bar is not None and not versions:
            continue                                    # older than what every pull reaches: not checked
        else:
            found["unstable"].append(day)
    return found


def summarize(market: str, results: dict[str, dict[str, list[date]]], failed: list[str], series_count: int) -> dict:
    """The Telegram details of one market: counts per kind and one line per series and kind (first, last, count)."""
    totals = {kind: sum(len(r[kind]) for r in results.values()) for kind in KINDS}
    items = []
    for name in sorted(results):
        for kind in KINDS:
            days = results[name][kind]
            if days:
                items.append({"series": name, "kind": kind, "count": len(days),
                              "first": days[0].isoformat(), "last": days[-1].isoformat()})
    # what asks for a correction first, then the largest
    items.sort(key=lambda item: (item["kind"] == "unstable", -item["count"], item["series"]))
    return {"market": market, "series": series_count, **totals, "items": items[:MAX_ITEMS],
            "more_items": max(0, len(items) - MAX_ITEMS), "failed_series": failed[:20]}


def pull_series(loader, series, schedule, now: datetime, last: date, attempts: int = 3) -> dict[date, tuple]:
    """One full pull (5000 daily bars) on a new socket, with the loader's client and date rule."""
    for attempt in range(attempts):
        ws = None
        try:
            ws = loader.open_socket(30, False)
            chart_session = loader.start_chart_session(ws)
            rows, _ = loader.request_series(
                ws, chart_session, series, 5000, 90, now.date(), last, now, now, schedule.source_date_mapping,
                schedule.provider_timezone_name, schedule.provider_session)
            return {row["date"]: tuple(float(row[k]) for k in ("open", "high", "low", "close")) for row in rows}
        except Exception:
            if attempt == attempts - 1:
                raise
            time.sleep(3)
        finally:
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass
    return {}


def check_market(loader, connection, market_code: str, now: datetime, pulls: int = PULLS, pause: float = 0.3) -> dict:
    schedule = loader.read_schedule(connection, market_code)
    last = loader.latest_completed_session(schedule, now)
    universe = loader.read_universe(connection, schedule)
    taken: dict[str, list[dict]] = {}
    failed: list[str] = []
    for _ in range(pulls):                                       # rounds over the market: a series' pulls lie apart
        for series in universe:
            name = f"{series.ticker}/{series.metric_type}"
            if name in failed:
                continue
            try:
                taken.setdefault(name, []).append(pull_series(loader, series, schedule, now, last))
            except Exception as exc:
                failed.append(name)
                print(json.dumps({"event": "consensus_pull_failed", "series": name,
                                  "error": f"{type(exc).__name__}: {exc}"[:300]}), flush=True)
            time.sleep(pause)
    results: dict[str, dict[str, list[date]]] = {}
    for series in universe:
        name = f"{series.ticker}/{series.metric_type}"
        if name in failed:
            continue
        stored = {
            day: tuple(float(x) for x in values)
            for day, *values in connection.execute(
                f'SELECT date, open, high, low, close FROM {loader.PRICE_TABLE} '
                'WHERE tradingview_symbol = %s AND metric_type = %s AND "Timeframe" = %s',
                (series.tradingview_symbol, series.metric_type, loader.TIMEFRAME),
            ).fetchall()
        }
        results[name] = compare_series(stored, taken[name], last)
        flagged = {kind: len(days) for kind, days in results[name].items() if days}
        if flagged:
            print(json.dumps({"event": "consensus_series", "series": name, **flagged,
                              "samples": {k: [d.isoformat() for d in v[:5]] for k, v in results[name].items() if v}}),
                  flush=True)
    return summarize(schedule.market_code, results, failed, len(universe))


def execution_id(market_code: str, now: datetime, manual: bool) -> str:
    return f"fi-consensus-{'manual-' if manual else ''}{market_code}-{now.strftime('%Y-%m-%d-%H%M')}"


def run(loader, database_url: str, market_code: str, now: datetime | None = None, *, manual: bool, connect=None,
        notify=None) -> dict:
    """Check one market, print the report and send it to Telegram. A failure is reported too, with its error class."""
    import psycopg

    now = now or datetime.now(timezone.utc)
    connect = connect or psycopg.connect
    notify = notify or loader.notify_telegram_monitor
    run_id = execution_id(market_code, now, manual)
    started = time.monotonic()
    try:
        with connect(database_url) as connection:
            details = check_market(loader, connection, market_code, now)
    except Exception as exc:
        details = {"market": market_code, "error": type(exc).__name__}
        print(json.dumps({"event": "consensus_failed", "error": f"{type(exc).__name__}: {exc}"[:500]}), flush=True)
    details["pulls"] = PULLS
    details["minutes"] = round((time.monotonic() - started) / 60)
    details["run_time"] = now.astimezone(loader.ZoneInfo("Asia/Jakarta")).strftime("%Y-%m-%d %H:%M")
    print(json.dumps({"event": "consensus_report", "execution_id": run_id, **details}), flush=True)
    notify(run_id, source_table=SOURCE_TABLE, details=details)
    return details


def due(schedule_timezone, now: datetime) -> bool:
    return now.astimezone(schedule_timezone).weekday() == WEEKDAY
