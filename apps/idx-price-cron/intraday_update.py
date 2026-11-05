#!/usr/bin/env python3
"""EXEC-INTRADAY-IDX: intraday bars (5m, 15m, 1h, 4h) of the IDX_Stock_Universe stocks and the universe index (IHSG)
from TradingView into public.price_stock_idx_intraday, then one quality row per timeframe and session
(public.remark_intraday_sessions). The daily Price_Stock_Indonesia_IDX and the Feature tables are not touched.

--mode backfill  everything TradingView gives (its own limit, about 5,000-6,200 bars a series without an account), from --since
                 (default 2020-01-01, the user's "dari 2020").
--mode daily     the sessions since the newest stored bar of each series plus DAILY_OVERLAP_SESSIONS (a revised bar is
                 updated); a series never stored is asked in full.
Only bars of completed sessions are written: the session date is at most latest_completed_session (close plus the
finality delay of Equity_Market_Schedule). A bar that fails the OHLC check is skipped and counted, never repaired.

A series whose stored bars all differ from TradingView by one ratio other than 1 (TradingView re-adjusted the history
after a split or rights issue, ERRORS D22) is not written and is reported as SCALE_CHANGED: its stored history is
rescaled first (EXEC-PRICE-GAP-0917 procedure), so two scales never mix in one series.

Usage: python intraday_update.py --mode daily|backfill [--timeframes 5m,15m,1h,4h] [--tickers BBCA,IHSG]
                                 [--since 2020-01-01] [--workers 4] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone

import psycopg

import price_update as pu

TIMEFRAMES = {"5m": "5", "15m": "15", "1h": "60", "4h": "240"}
# Upper bounds of bars in one session (09:00-16:15 Asia/Jakarta; measured 2026-10-31: 67, 23, 6-7 and 2), used only to
# size a daily request.
BARS_PER_SESSION = {"5m": 90, "15m": 30, "1h": 8, "4h": 2}
# TradingView caps a series at its own limit (about 5,000-6,200 bars without an account); asking more returns that
# limit, asking exactly 5,000 returns 5,000 (15m: 2025-11-19 instead of 2025-11-03, measured 2026-10-31).
MAX_BARS = 20000
DAILY_OVERLAP_SESSIONS = 3
CHUNK_SYMBOLS = 40
COLUMNS = ("ticker", "timeframe", "bar_time", "session_date", "open", "high", "low", "close", "volume",
           "adjustment", "tradingview_symbol", "source", "query_date")
TABLE = 'public.price_stock_idx_intraday'
QUEUE = "public.intraday_feature_queue"
PUBLISH_CHANGE = "public.intraday_publish_change"   # terminal-publisher reads it (migration 20261101_001)
PUBLISH_MERGE_DAYS = 14
LOCK_KEY = "saniti.idx-intraday-cron"


def emit(event: str, **fields) -> None:
    print(json.dumps({"event": event, **fields}, default=str), flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=("daily", "backfill"), required=True)
    parser.add_argument("--timeframes", default=",".join(TIMEFRAMES))
    parser.add_argument("--tickers", default="")
    parser.add_argument("--since", type=date.fromisoformat, default=date(2020, 1, 1))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-features", action="store_true",
                        help="load the bars only; the queue waits for the next run (intraday_features.py --mode queue)")
    args = parser.parse_args()
    args.timeframes = [t.strip() for t in args.timeframes.split(",") if t.strip()]
    if not args.timeframes or any(t not in TIMEFRAMES for t in args.timeframes):
        parser.error(f"--timeframes takes {', '.join(TIMEFRAMES)}")
    if not 1 <= args.workers <= 8:
        parser.error("--workers must be between 1 and 8")
    return args


def requested_bars(timeframe: str, sessions_behind: int | None) -> int:
    """Bars to ask for a series: everything when it was never stored, else the missing sessions plus the overlap."""
    if sessions_behind is None:
        return MAX_BARS
    return min(MAX_BARS, BARS_PER_SESSION[timeframe] * (sessions_behind + DAILY_OVERLAP_SESSIONS))


def scale_check(stored: dict, fetched: dict) -> tuple[str, float | None, int]:
    """Compare the stored closes with TradingView's on the bars both have: ('SAME', 1, 0) when equal, ('SCALE_CHANGED',
    ratio, n) when every bar differs by one ratio != 1, ('REVISED', None, n_differing) otherwise."""
    common = [t for t in stored if t in fetched and fetched[t]]
    ratios = [float(stored[t]) / float(fetched[t]) for t in common]
    differing = sum(1 for r in ratios if abs(r - 1) > 1e-9)
    if not differing:
        return "SAME", 1.0, 0
    if len(ratios) >= 3 and max(ratios) - min(ratios) <= 1e-6 * max(ratios):
        return "SCALE_CHANGED", round(ratios[0], 6), len(ratios)
    return "REVISED", None, differing


class Fetcher:
    """One TradingView socket per worker thread (the price job's client)."""

    def __init__(self, query_date: date):
        self.local, self.query_date = threading.local(), query_date

    def bars(self, symbol, resolution: str, count: int) -> list[dict]:
        for attempt in range(3):
            try:
                if getattr(self.local, "ws", None) is None:
                    self.local.ws = pu.open_socket(60.0, False)
                    self.local.chart = pu.start_chart_session(self.local.ws)
                return pu.request_symbol(self.local.ws, self.local.chart, symbol, count, 90.0, self.query_date,
                                         resolution=resolution)
            except Exception:
                try:
                    self.local.ws.close()
                except Exception:
                    pass
                self.local.ws = None
                if attempt == 2:
                    raise
                time.sleep(2 * (attempt + 1))
        return []


def rows_of(symbol, timeframe: str, bars: list[dict], since: date, latest: date, query_date: date):
    """The bars to write: completed sessions from `since`, OHLC checked. Returns (rows, invalid)."""
    out, invalid = [], 0
    for bar in bars:
        if not since <= bar["date"] <= latest:
            continue
        try:
            bar = pu.validate_price_row(dict(bar))
        except ValueError:
            invalid += 1
            continue
        out.append({
            "ticker": symbol.ticker, "timeframe": timeframe, "bar_time": bar["source_bar_time"],
            "session_date": bar["date"], "open": bar["open"], "high": bar["high"], "low": bar["low"],
            "close": bar["close"], "volume": bar["volume"],
            "adjustment": "none" if symbol.asset_type == "index" else "splits",
            "tradingview_symbol": symbol.tradingview_symbol, "source": "TradingView", "query_date": query_date,
        })
    return out, invalid


def write_rows(conn: psycopg.Connection, rows: list[dict]) -> int:
    """Upsert on (ticker, timeframe, bar_time); an unchanged bar keeps its ingestion_time. Returns rows written."""
    if not rows:
        return 0
    cols = ", ".join(COLUMNS)
    changed = ", ".join(f"{c} = EXCLUDED.{c}" for c in COLUMNS if c not in ("ticker", "timeframe", "bar_time"))
    compared = ("session_date", "open", "high", "low", "close", "volume")
    with conn.transaction():
        conn.execute(f"CREATE TEMP TABLE intraday_stage (LIKE {TABLE} INCLUDING DEFAULTS) ON COMMIT DROP")
        with conn.cursor().copy(f"COPY intraday_stage ({cols}) FROM STDIN") as copy:
            for row in rows:
                copy.write_row(tuple(row[c] for c in COLUMNS))
        # EXEC-INTRADAY-FEATURES: the bars that were inserted or changed come back, and the first one of every
        # (ticker, timeframe) is queued for the features in the same transaction (an index has no stock features: D4)
        n = conn.execute(
            f"""WITH written AS (
                    INSERT INTO {TABLE} AS t ({cols}, ingestion_time)
                    SELECT {cols}, statement_timestamp() FROM intraday_stage
                    ON CONFLICT (ticker, timeframe, bar_time) DO UPDATE SET {changed},
                        ingestion_time = EXCLUDED.ingestion_time
                    WHERE ({", ".join("t." + c for c in compared)}) IS DISTINCT FROM
                          ({", ".join("EXCLUDED." + c for c in compared)})
                    RETURNING t.ticker, t.timeframe, t.bar_time),
                queued AS (
                    INSERT INTO {QUEUE} AS q (ticker, timeframe, dirty_from)
                    SELECT ticker, timeframe, min(bar_time) FROM written
                     WHERE NOT public.is_universe_index(ticker) GROUP BY ticker, timeframe
                    ON CONFLICT (ticker, timeframe) DO UPDATE SET
                        dirty_from = CASE WHEN q.status = 'DONE' THEN EXCLUDED.dirty_from
                                          ELSE least(q.dirty_from, EXCLUDED.dirty_from) END,
                        attempts = CASE WHEN q.status = 'DONE' THEN 0 ELSE q.attempts END,
                        status = 'PENDING', enqueued_at = statement_timestamp()),
                published AS (
                    -- EXEC-INTRADAY-FEATURES C7.4 A (user 2026-11-01): the publisher's change record, IHSG included;
                    -- the earliest bar written within PUBLISH_MERGE_DAYS is kept (the publisher runs twice a day and
                    -- republishes everything when its last run is older than half that window)
                    INSERT INTO {PUBLISH_CHANGE} AS p (ticker, timeframe, changed_from)
                    SELECT ticker, timeframe, min(bar_time) FROM written GROUP BY ticker, timeframe
                    ON CONFLICT (ticker, timeframe) DO UPDATE SET
                        changed_from = CASE WHEN p.changed_at >= statement_timestamp() - interval '{PUBLISH_MERGE_DAYS} days'
                                            THEN least(p.changed_from, EXCLUDED.changed_from)
                                            ELSE EXCLUDED.changed_from END,
                        changed_at = statement_timestamp())
                SELECT count(*) FROM written"""
        ).fetchone()[0]
        return n


def sessions_behind(conn, universe, timeframe: str, latest: date) -> dict[str, int | None]:
    """Per ticker: calendar sessions (dates of the universe index daily candles) after its newest stored bar, up to
    `latest`; None when the series has no bar."""
    newest = dict(conn.execute(
        f"SELECT ticker, max(session_date) FROM {TABLE} WHERE timeframe = %s GROUP BY ticker", (timeframe,)
    ).fetchall())
    if not newest:
        return {s.ticker: None for s in universe}
    calendar = [r[0] for r in conn.execute(
        """SELECT DISTINCT p.date FROM public."Price_Stock_Indonesia_IDX" p
           WHERE public.is_universe_index(p.ticker) AND p.timeframe = 'Daily' AND p.is_final
             AND p.date > %s AND p.date <= %s ORDER BY 1""",
        (min(newest.values()), latest),
    ).fetchall()]
    return {s.ticker: (None if s.ticker not in newest else sum(1 for d in calendar if d > newest[s.ticker]))
            for s in universe}


def load_timeframe(conn, fetcher: Fetcher, universe, timeframe: str, args, latest: date, query_date: date) -> dict:
    behind = (sessions_behind(conn, universe, timeframe, latest) if args.mode == "daily"
              else {s.ticker: None for s in universe})
    stats = {"timeframe": timeframe, "symbols": len(universe), "bars_fetched": 0, "rows_written": 0, "invalid": 0,
             "no_bars": [], "errors": [], "scale_changed": [], "revised_bars": 0, "first": None, "last": None}
    started = time.monotonic()
    with ThreadPoolExecutor(args.workers) as pool:
        for i in range(0, len(universe), CHUNK_SYMBOLS):
            chunk = universe[i:i + CHUNK_SYMBOLS]

            def fetch(symbol):
                try:
                    return symbol, fetcher.bars(symbol, TIMEFRAMES[timeframe],
                                                requested_bars(timeframe, behind.get(symbol.ticker))), None
                except Exception as exc:  # noqa: BLE001 - one series fails, the run goes on and reports it
                    return symbol, [], f"{type(exc).__name__}: {exc}"[:200]

            fetched = list(pool.map(fetch, chunk))
            rows = []
            stored = {}
            # stored bars of the chunk in the fetched span (none on a first backfill), for the scale check
            first_bar = min((b["source_bar_time"] for _, bars, _ in fetched for b in bars), default=None)
            if first_bar is not None:
                for ticker, bar_time, close in conn.execute(
                    f"SELECT ticker, bar_time, close FROM {TABLE} WHERE timeframe = %s AND ticker = ANY(%s) "
                    "AND bar_time >= %s", (timeframe, [s.ticker for s, _, _ in fetched], first_bar)
                ).fetchall():
                    stored.setdefault(ticker, {})[bar_time] = close
            for symbol, bars, error in fetched:
                if error:
                    stats["errors"].append([symbol.ticker, error]); continue
                own, invalid = rows_of(symbol, timeframe, bars, args.since, latest, query_date)
                stats["bars_fetched"] += len(bars); stats["invalid"] += invalid
                if not own:
                    stats["no_bars"].append(symbol.ticker); continue
                verdict, ratio, n = scale_check(stored.get(symbol.ticker, {}),
                                                {r["bar_time"]: r["close"] for r in own})
                if verdict == "SCALE_CHANGED":
                    stats["scale_changed"].append([symbol.ticker, ratio, n]); continue
                stats["revised_bars"] += n if verdict == "REVISED" else 0
                rows += own
            if rows:
                first, last = min(r["session_date"] for r in rows), max(r["session_date"] for r in rows)
                stats["first"] = min(filter(None, (stats["first"], first)))
                stats["last"] = max(filter(None, (stats["last"], last)))
                if not args.dry_run:
                    stats["rows_written"] += write_rows(conn, rows)
            emit("intraday_chunk", timeframe=timeframe, done=min(i + CHUNK_SYMBOLS, len(universe)),
                 of=len(universe), rows=len(rows), seconds=round(time.monotonic() - started, 1))
    if stats["first"] and not args.dry_run:
        stats["quality_sessions"] = conn.execute(
            "SELECT public.remark_intraday_sessions(%s, %s, %s)", (timeframe, stats["first"], stats["last"])
        ).fetchone()[0]
        stats["quality"] = dict(conn.execute(
            "SELECT status, count(*) FROM public.price_stock_idx_intraday_quality "
            "WHERE timeframe = %s AND session_date BETWEEN %s AND %s GROUP BY status",
            (timeframe, stats["first"], stats["last"]),
        ).fetchall())
    stats["seconds"] = round(time.monotonic() - started, 1)
    stats["no_bars"] = stats["no_bars"][:60]
    return stats


def main() -> int:
    args = parse_args()
    now = datetime.now(timezone.utc)
    query_date = now.astimezone(pu.JAKARTA).date()
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True,
                         application_name="idx-intraday-cron") as conn:
        schedule = pu.read_market_schedule(conn)
        latest = pu.latest_completed_session(schedule, now)
        universe = pu.read_universe(conn)
        wanted = {t.strip().upper() for t in args.tickers.split(",") if t.strip()}
        if wanted:
            universe = [s for s in universe if s.ticker in wanted]
        if not conn.execute("SELECT pg_try_advisory_lock(hashtext(%s))", (LOCK_KEY,)).fetchone()[0]:
            emit("run_skipped", reason="another intraday run holds the lock")
            return 0
        emit("run_started", mode=args.mode, timeframes=args.timeframes, symbols=len(universe), latest_session=latest,
             since=args.since, dry_run=args.dry_run)
        fetcher = Fetcher(query_date)
        problems = []
        if not args.dry_run:
            pu.hold_publish_write_lock(conn)              # EXEC-PUBLISH-FLOW: the publisher waits while the bars are written
        written = 0
        for timeframe in args.timeframes:
            stats = load_timeframe(conn, fetcher, universe, timeframe, args, latest, query_date)
            emit("timeframe_done", **stats)
            written += int(stats.get("rows_written") or 0)
            if stats["scale_changed"]:
                problems.append(f"{timeframe}: skala berubah (perlu tarik ulang riwayat): "
                                + ", ".join(t for t, _, _ in stats["scale_changed"][:20]))
            if stats["errors"]:
                problems.append(f"{timeframe}: {len(stats['errors'])} saham gagal ditarik")
        if not args.dry_run:
            # the bars are committed (autocommit): the publisher may start; it does not read the intraday features
            pu.release_publish_write_lock(conn)
            if written:
                request_publication(f"intraday-{latest.isoformat()}-{query_date.isoformat()}-{os.getpid()}", written)
        if not args.dry_run and not args.skip_features:
            import intraday_features  # noqa: PLC0415 - TA-Lib lives only in the intraday image (M318 build check)
            features = intraday_features.run_queue(conn, args.timeframes)
            if features["failed"]:
                problems.append(f"fitur intraday gagal untuk {len(features['failed'])} deret, dicoba lagi run "
                                "berikutnya: " + ", ".join(f"{t} {tf}" for t, tf, _ in features["failed"][:20]))
        if problems and not args.dry_run:
            report_problems(conn, universe, latest, now, problems)
    emit("run_completed", problems=len(problems))
    return 0


def request_publication(execution_id: str, changed: int) -> bool:
    """EXEC-PUBLISH-FLOW: tell telegram-monitor (source Terminal_Publish_Request) that the intraday bars are written,
    so it presses Run Now on terminal-publisher. A clean run sends no Telegram message (EXEC-INTRADAY-IDX), so this is
    the run's own completion signal. Three tries; a failure is logged only (the 07:30 WIB safety run publishes it)."""
    url = os.environ.get("TELEGRAM_NOTIFY_URL", "").strip()
    secret = os.environ.get("TELEGRAM_NOTIFY_SECRET", "").strip()
    if not url or not secret:
        emit("publish_request_skipped", reason="not_configured")
        return False
    import urllib.request  # noqa: PLC0415
    body = json.dumps({"source_table": "Terminal_Publish_Request", "execution_id": execution_id,
                       "details": {"loader": "idx-intraday-cron", "changed": int(changed)}}).encode()
    for attempt in range(1, 4):
        try:
            request = urllib.request.Request(url, data=body, method="POST",
                                             headers={"Content-Type": "application/json", "X-Notify-Secret": secret})
            with urllib.request.urlopen(request, timeout=20) as response:
                emit("publish_requested", status=json.loads(response.read() or b"{}").get("status"), changed=changed,
                     attempt=attempt)
                return True
        except Exception as exc:  # noqa: BLE001 - the URL and the secret are never printed
            emit("publish_request_failed", attempt=attempt, error=type(exc).__name__)
            time.sleep(2 ** attempt)
    return False


def report_problems(conn, universe, latest: date, now: datetime, problems: list[str]) -> None:
    """One NEEDS_REVIEW monitoring row and its Telegram notice when the load or the features need attention (the
    price cron's channel, price_update.monitoring_records); a clean run sends nothing."""
    import uuid  # noqa: PLC0415
    execution_id = str(uuid.uuid4())
    stocks = [s for s in universe if s.asset_type != "index"]
    records = pu.monitoring_records(
        stocks, [], [], "RECOVERY", latest, now, datetime.now(timezone.utc), execution_id, "SCHEDULED", now,
        forced_status="NEEDS_REVIEW", forced_error=("INTRADAY: " + "; ".join(problems))[:1900])
    try:
        pu.commit_monitoring_and_notify(conn, records, execution_id)
    except Exception as exc:  # noqa: BLE001 - a notice that fails must not undo the bars or the features
        emit("problem_report_failed", error=f"{type(exc).__name__}: {exc}"[:300], problems=problems)


if __name__ == "__main__":
    pu.run_entrypoint(main)
