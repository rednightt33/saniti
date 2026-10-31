#!/usr/bin/env python3
"""EXEC-INTRADAY-FEATURES (user go 2026-10-31; D1 A, D2 a, D3 W1, D4 later): Feature 01 and Feature 04 of the intraday
bars in public.price_stock_idx_intraday, written to public."Feature_01_Stock_Intraday" and
public."Feature_04_Technical_Indicator_Intraday" (migration 20261031_004).

Feature 01 is the SQL function refresh_feature_01_stock_intraday (the daily function with the bar key). Feature 04 is
features/feature04/engine.py and incremental.py, unchanged: the daily worker uses them too, and they accept only daily
dates. Each bar is therefore handed to them with a synthetic date, the n-th weekday after 1970-01-05 for the n-th bar of
its series (zero-based). The engine reads only the order of its rows, never the dates themselves, so the values are
the daily formulas with one period = one bar. They are mapped back to bar_time by the same position.
- A series without state, with another engine VERSION, or changed at or before its last calculated bar: full
  calculation (engine.calculate for the rows, incremental state_only for the state; both equal the chained calculation,
  verification/intraday_features/README.md).
- Otherwise: the new bars from the stored state (incremental.calculate_incremental), the daily worker's method.

The loader (intraday_update.py) enqueues the first changed bar of every (ticker, timeframe) in public.
intraday_feature_queue in the transaction that writes the bars; run_queue works the queue: Feature 01 per timeframe in
chunks of tickers, then Feature 04 per series in its own transaction; an item that fails stays FAILED with its error and
is tried again by the next run.

Usage (normally called by intraday_update.py after a load):
  python intraday_features.py --mode queue [--timeframes 5m,15m,1h,4h]
  python intraday_features.py --mode backfill [--timeframes ...] [--tickers BBCA,...] [--workers 4]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import psycopg

TIMEFRAMES = ("5m", "15m", "1h", "4h")
F04 = 'public."Feature_04_Technical_Indicator_Intraday"'
STATE = "public.feature04_intraday_state"
QUEUE = "public.intraday_feature_queue"
F01_CHUNK = 50                       # tickers per refresh_feature_01_stock_intraday call (5m: about 11 s, dry run)
ORIGIN = date(1970, 1, 5)            # a Monday: synthetic date of the first bar of every series
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
LOCK_KEY = "saniti.idx-intraday-cron"  # the loader's advisory lock: one writer of the bars and the features at a time
IDENTITY = ("ticker", "timeframe", "bar_time", "session_date")
NOT_STORED = ("ticker", "trade_date", "timeframe", "asset_type", "calculation_version", "calculated_at")

BARS_SQL = """SELECT bar_time, session_date, open, high, low, close, volume, tradingview_symbol
                FROM public.price_stock_idx_intraday
               WHERE ticker = %s AND timeframe = %s AND bar_time > %s ORDER BY bar_time"""


def emit(event: str, **fields) -> None:
    print(json.dumps({"event": event, **fields}, default=str), flush=True)


_ENGINE = None


def load_engine():
    """(engine, incremental) of features/feature04, imported on first use. The price crons share this folder's image
    without TA-Lib, and its build imports every module (M318), so nothing here imports TA-Lib at module level."""
    global _ENGINE
    if _ENGINE is None:
        here = Path(__file__).resolve().parent
        # next to this file (the intraday image), as a staged folder (a runner job), or in an ancestor (the repository)
        for base in [here / "feature04"] + [p / "features" / "feature04" for p in (here, *here.parents)]:
            if (base / "engine.py").exists():
                sys.path.insert(0, str(base))
                break
        import engine  # noqa: PLC0415
        import incremental  # noqa: PLC0415
        _ENGINE = (engine, incremental)
    return _ENGINE


def synthetic_date(position: int) -> date:
    """The weekday the engine sees for the bar at `position` (zero-based) of its series."""
    weeks, day = divmod(position, 5)
    return ORIGIN + timedelta(days=7 * weeks + day)


def position_of(day: date) -> int:
    weeks, day_of_week = divmod((day - ORIGIN).days, 7)
    if day_of_week > 4:
        raise ValueError(f"{day} is not a synthetic bar date")
    return 5 * weeks + day_of_week


def engine_rows(ticker: str, bars, first_position: int) -> list[dict]:
    """Bars (BARS_SQL rows) as the engine's daily source rows, from position `first_position`."""
    return [dict(ticker=ticker, date=synthetic_date(first_position + i), open=b[2], high=b[3], low=b[4], close=b[5],
                 volume=b[6], timeframe="Daily", asset_type="equity", tradingview_symbol=b[7], source="TradingView")
            for i, b in enumerate(bars)]


def stored_columns(conn) -> list[str]:
    """The value columns of the Feature 04 intraday table, in table order (derived, not listed)."""
    rows = conn.execute(
        """SELECT column_name FROM information_schema.columns WHERE table_schema = 'public'
             AND table_name = 'Feature_04_Technical_Indicator_Intraday' ORDER BY ordinal_position""").fetchall()
    return [r[0] for r in rows if r[0] not in IDENTITY + ("calculated_at",)]


def check_columns(engine, cols: list[str]) -> None:
    """The table holds every engine output except the daily identity; a drift is a failure, never a silent NULL."""
    expected = [c for c in engine.COLUMNS if c not in NOT_STORED]
    if sorted(expected) != sorted(cols):
        raise RuntimeError(f"Feature 04 intraday columns differ from engine.COLUMNS: table-only "
                           f"{sorted(set(cols) - set(expected))}, engine-only {sorted(set(expected) - set(cols))}")


def failed_groups(outcomes: dict) -> dict:
    return {k: v for k, v in outcomes.items() if v.get("status") == "FAILED"}


def calculate_series(conn, ticker: str, timeframe: str, dirty_from, cols: list[str], *, force_full: bool = False):
    """Feature 04 of one series; returns (bars written, full calculation?). Writes rows and state in one transaction."""
    engine, incremental = load_engine()
    st = conn.execute(f"SELECT last_bar_time, bars, state, calculation_version FROM {STATE} "
                      "WHERE ticker = %s AND timeframe = %s", (ticker, timeframe)).fetchone()
    full = (force_full or st is None or st[3] != engine.VERSION or dirty_from is None or dirty_from <= st[0])
    stamp = datetime.now(timezone.utc)
    bars = conn.execute(BARS_SQL, (ticker, timeframe, EPOCH - timedelta(days=1) if full else st[0])).fetchall()
    if full:
        source = engine_rows(ticker, bars, 0)
        outputs, outcomes = engine.calculate_with_diagnostics(source, calculated_at=stamp) if source else ([], {})
        if failed_groups(outcomes):
            raise RuntimeError(f"engine groups failed: {failed_groups(outcomes)}")
        state = None
        if source:
            _, outcomes, state, _ = incremental.calculate_incremental(source, state_only=True, checkpoint_limit=1)
            if failed_groups(outcomes):
                raise RuntimeError(f"state groups failed: {failed_groups(outcomes)}")
        first_position = 0
    else:
        if not bars:
            return 0, False
        first_position = int(st[2]["position"])
        if first_position != st[1]:
            raise RuntimeError(f"state position {first_position} differs from its bar count {st[1]}")
        source = engine_rows(ticker, bars, first_position)
        outputs, outcomes, state, _ = incremental.calculate_incremental(source, checkpoint=st[2], checkpoint_limit=1,
                                                                        calculated_at=stamp)
        if failed_groups(outcomes):
            raise RuntimeError(f"incremental groups failed: {failed_groups(outcomes)}")
    if len(outputs) != len(bars):
        raise RuntimeError(f"{len(outputs)} outputs for {len(bars)} bars")
    rows = []
    for out in outputs:
        bar = bars[position_of(out["trade_date"]) - first_position]
        rows.append((ticker, timeframe, bar[0], bar[1], *(out.get(c) for c in cols), stamp))
    names = ", ".join(IDENTITY + tuple(cols) + ("calculated_at",))
    with conn.transaction():
        if full:
            conn.execute(f"DELETE FROM {F04} WHERE ticker = %s AND timeframe = %s", (ticker, timeframe))
            with conn.cursor().copy(f"COPY {F04} ({names}) FROM STDIN") as copy:
                for row in rows:
                    copy.write_row(row)
        else:
            conn.execute(f"CREATE TEMP TABLE f04i_stage (LIKE {F04} INCLUDING DEFAULTS) ON COMMIT DROP")
            with conn.cursor().copy(f"COPY f04i_stage ({names}) FROM STDIN") as copy:
                for row in rows:
                    copy.write_row(row)
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols + ["session_date", "calculated_at"])
            conn.execute(f"INSERT INTO {F04} ({names}) SELECT {names} FROM f04i_stage "
                         f"ON CONFLICT (ticker, timeframe, bar_time) DO UPDATE SET {updates}")
        if state is None:
            conn.execute(f"DELETE FROM {STATE} WHERE ticker = %s AND timeframe = %s", (ticker, timeframe))
        else:
            conn.execute(
                f"""INSERT INTO {STATE} (ticker, timeframe, last_bar_time, bars, state, calculation_version, updated_at)
                    VALUES (%s, %s, %s, %s, %s::jsonb, %s, statement_timestamp())
                    ON CONFLICT (ticker, timeframe) DO UPDATE SET last_bar_time = EXCLUDED.last_bar_time,
                        bars = EXCLUDED.bars, state = EXCLUDED.state,
                        calculation_version = EXCLUDED.calculation_version, updated_at = EXCLUDED.updated_at""",
                (ticker, timeframe, bars[-1][0], first_position + len(bars), json.dumps(state, default=str),
                 engine.VERSION))
    return len(rows), full


def refresh_f01(conn, timeframe: str, items: list[tuple[str, object]]) -> int:
    """Feature 01 for (ticker, dirty_from) items of one timeframe; dirty_from None = the whole series."""
    written = 0
    for i in range(0, len(items), F01_CHUNK):
        chunk = items[i:i + F01_CHUNK]
        froms = [d for _, d in chunk]
        p_from = None if any(d is None for d in froms) else min(froms)
        written += conn.execute("SELECT public.refresh_feature_01_stock_intraday(%s, %s, %s)",
                                (timeframe, [t for t, _ in chunk], p_from)).fetchone()[0]
    return written


def mark(conn, ticker, timeframe, dirty_from, error=None) -> None:
    """DONE (or FAILED with the error) for the item as it was read: a later enqueue keeps it PENDING."""
    conn.execute(
        f"""UPDATE {QUEUE} SET status = %s, attempts = attempts + 1, last_error = %s,
                done_at = CASE WHEN %s::text IS NULL THEN statement_timestamp() ELSE done_at END
             WHERE ticker = %s AND timeframe = %s AND dirty_from = %s AND status <> 'DONE'""",
        ("FAILED" if error else "DONE", error, error, ticker, timeframe, dirty_from))


def run_queue(conn, timeframes=TIMEFRAMES) -> dict:
    """Work every open queue item (PENDING or FAILED) of the timeframes. Returns the summary (also emitted)."""
    engine, _ = load_engine()
    cols = stored_columns(conn)
    check_columns(engine, cols)
    summary = {"items": 0, "done": 0, "failed": [], "full": 0, "f01_rows": 0, "f04_rows": 0}
    started = time.monotonic()
    for timeframe in timeframes:
        items = conn.execute(f"SELECT ticker, dirty_from FROM {QUEUE} WHERE status <> 'DONE' AND timeframe = %s "
                             "ORDER BY ticker", (timeframe,)).fetchall()
        if not items:
            continue
        summary["items"] += len(items)
        f01_failed = {}
        for i in range(0, len(items), F01_CHUNK):
            chunk = items[i:i + F01_CHUNK]
            try:
                summary["f01_rows"] += refresh_f01(conn, timeframe, chunk)
            except Exception as exc:  # noqa: BLE001 - the chunk fails, the run goes on and reports it
                f01_failed.update({t: f"Feature 01: {type(exc).__name__}: {exc}"[:500] for t, _ in chunk})
        for ticker, dirty_from in items:
            error = f01_failed.get(ticker)
            if not error:
                try:
                    n, full = calculate_series(conn, ticker, timeframe, dirty_from, cols)
                    summary["f04_rows"] += n
                    summary["full"] += int(full)
                except Exception as exc:  # noqa: BLE001
                    error = f"Feature 04: {type(exc).__name__}: {exc}"[:500]
            mark(conn, ticker, timeframe, dirty_from, error)
            if error:
                summary["failed"].append([ticker, timeframe, error])
            else:
                summary["done"] += 1
        emit("intraday_features_timeframe", timeframe=timeframe, items=len(items),
             seconds=round(time.monotonic() - started, 1))
    summary["seconds"] = round(time.monotonic() - started, 1)
    emit("intraday_features_done", **{**summary, "failed": summary["failed"][:40], "failed_count": len(summary["failed"])})
    return summary


def _backfill_series(args):
    """One process: Feature 04 of a list of (ticker, timeframe) series, full calculation."""
    database_url, series = args
    out = []
    with psycopg.connect(database_url, autocommit=True, application_name="intraday-features-backfill") as conn:
        cols = stored_columns(conn)
        for ticker, timeframe in series:
            started = time.monotonic()
            try:
                n, _ = calculate_series(conn, ticker, timeframe, None, cols, force_full=True)
                out.append((ticker, timeframe, n, round(time.monotonic() - started, 2), None))
            except Exception as exc:  # noqa: BLE001
                out.append((ticker, timeframe, 0, round(time.monotonic() - started, 2), f"{type(exc).__name__}: {exc}"[:300]))
    return out


def backfill(database_url: str, timeframes=TIMEFRAMES, tickers=None, workers: int = 4) -> int:
    """Every stock series of the timeframes in full: Feature 01 by chunks, Feature 04 in `workers` processes."""
    engine, _ = load_engine()
    failures = 0
    with psycopg.connect(database_url, autocommit=True, application_name="intraday-features-backfill") as conn:
        check_columns(engine, stored_columns(conn))
        for timeframe in timeframes:
            started = time.monotonic()
            names = [r[0] for r in conn.execute(
                "SELECT DISTINCT ticker FROM public.price_stock_idx_intraday WHERE timeframe = %s "
                "AND NOT public.is_universe_index(ticker) ORDER BY 1", (timeframe,)).fetchall()]
            if tickers:
                names = [t for t in names if t in tickers]
            f01 = refresh_f01(conn, timeframe, [(t, None) for t in names])
            emit("backfill_f01", timeframe=timeframe, tickers=len(names), rows=f01,
                 seconds=round(time.monotonic() - started, 1))
            batches = [[(t, timeframe) for t in names[i::workers * 4]] for i in range(workers * 4)]
            rows = done = 0
            # spawn: a forked child would share the parent's open database connection
            with ProcessPoolExecutor(workers, mp_context=multiprocessing.get_context("spawn")) as pool:
                for fut in as_completed([pool.submit(_backfill_series, (database_url, b)) for b in batches if b]):
                    for ticker, tf, n, seconds, error in fut.result():
                        if error:
                            failures += 1
                            emit("backfill_f04_failed", ticker=ticker, timeframe=tf, error=error)
                        rows += n
                        done += 1
                    emit("backfill_f04_progress", timeframe=timeframe, series=done, of=len(names), rows=rows,
                         seconds=round(time.monotonic() - started, 1))
            emit("backfill_timeframe_done", timeframe=timeframe, series=len(names), f01_rows=f01, f04_rows=rows,
                 failures=failures, seconds=round(time.monotonic() - started, 1))
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=("queue", "backfill"), required=True)
    parser.add_argument("--timeframes", default=",".join(TIMEFRAMES))
    parser.add_argument("--tickers", default="")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    timeframes = [t for t in args.timeframes.split(",") if t]
    if any(t not in TIMEFRAMES for t in timeframes):
        parser.error(f"--timeframes takes {', '.join(TIMEFRAMES)}")
    url = os.environ["DATABASE_URL"]
    if args.mode == "backfill":
        tickers = {t.strip().upper() for t in args.tickers.split(",") if t.strip()} or None
        return 1 if backfill(url, timeframes, tickers, args.workers) else 0
    with psycopg.connect(url, autocommit=True, application_name="idx-intraday-features") as conn:
        if not conn.execute("SELECT pg_try_advisory_lock(hashtext(%s))", (LOCK_KEY,)).fetchone()[0]:
            emit("run_skipped", reason="another intraday run holds the lock")
            return 0
        return 1 if run_queue(conn, timeframes)["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
