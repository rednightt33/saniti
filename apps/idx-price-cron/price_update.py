#!/usr/bin/env python3
"""Update daily IDX OHLCV prices from TradingView into Railway PostgreSQL."""

from __future__ import annotations

import argparse
import json
import os
import random
import socket
import string
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Iterable
from urllib.parse import unquote, urlparse
from zoneinfo import ZoneInfo

import psycopg
from psycopg.types.json import Jsonb
from websocket import WebSocketTimeoutException, create_connection


WS_URL = "wss://data.tradingview.com/socket.io/websocket"
ORIGIN = "https://www.tradingview.com"
JAKARTA = ZoneInfo("Asia/Jakarta")
TIMEFRAME = "1d"
PRICE_TIMEFRAME = "Daily"
PRICE_TABLE = 'public."Price_Stock_Indonesia_IDX"'
UNIVERSE_TABLE = 'public."IDX_Stock_Universe"'
MONITORING_TABLE = 'public."Monitoring_Price_ALL"'
PRINT_LOCK = threading.Lock()
RUN_LOCK_KEY = "saniti.idx-price-cron"
RECOVERY_WINDOW_START_MINUTE = 5 * 60 + 45
RECOVERY_WINDOW_END_MINUTE = 6 * 60 + 30
DAILY_WINDOW_START_MINUTE = 16 * 60 + 45
DAILY_WINDOW_END_MINUTE = 17 * 60 + 30
PRICE_COLUMNS = (
    "company_name",
    "ticker",
    "tradingview_symbol",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "source",
    "query_date",
    "timeframe",
)


@dataclass(frozen=True)
class Symbol:
    ordinal: int
    company_name: str
    ticker: str
    tradingview_symbol: str
    exchange: str
    asset_type: str


@dataclass(frozen=True)
class FetchOutcome:
    symbol: Symbol
    row: dict | None
    latest_date: date | None
    error: str | None


def session_id(prefix: str) -> str:
    suffix = "".join(random.choice(string.ascii_lowercase) for _ in range(12))
    return prefix + suffix


def frame(method: str, params: list) -> str:
    payload = json.dumps({"m": method, "p": params}, separators=(",", ":"))
    return f"~m~{len(payload)}~m~{payload}"


def parse_frames(raw: str | bytes) -> tuple[list[dict], list[str]]:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    objects: list[dict] = []
    heartbeats: list[str] = []
    position = 0
    while True:
        start = raw.find("~m~", position)
        if start < 0:
            break
        marker_end = raw.find("~m~", start + 3)
        if marker_end < 0:
            break
        try:
            size = int(raw[start + 3 : marker_end])
        except ValueError:
            position = marker_end + 3
            continue
        payload_start = marker_end + 3
        payload = raw[payload_start : payload_start + size]
        position = payload_start + size
        if payload.startswith("~h~"):
            heartbeats.append(f"~m~{len(payload)}~m~{payload}")
        elif payload.startswith("{"):
            try:
                objects.append(json.loads(payload))
            except json.JSONDecodeError:
                continue
    return objects, heartbeats


def proxy_options(disable_proxy: bool) -> dict:
    if disable_proxy:
        return {"http_no_proxy": ["data.tradingview.com"]}
    proxy_url = (
        os.environ.get("WSS_PROXY")
        or os.environ.get("HTTPS_PROXY")
        or os.environ.get("https_proxy")
        or os.environ.get("HTTP_PROXY")
        or os.environ.get("http_proxy")
    )
    if not proxy_url:
        return {}
    if "://" not in proxy_url:
        proxy_url = "http://" + proxy_url
    parsed = urlparse(proxy_url)
    if not parsed.hostname:
        raise ValueError("Proxy URL is invalid")
    options: dict = {
        "http_proxy_host": parsed.hostname,
        "http_proxy_port": parsed.port or 80,
        "proxy_type": "http",
    }
    if parsed.username:
        options["http_proxy_auth"] = (
            unquote(parsed.username),
            unquote(parsed.password or ""),
        )
    return options


def open_socket(timeout: float, disable_proxy: bool):
    return create_connection(
        WS_URL,
        origin=ORIGIN,
        timeout=timeout,
        **proxy_options(disable_proxy),
    )


def start_chart_session(ws) -> str:
    chart_session = session_id("cs_")
    ws.send(frame("set_auth_token", ["unauthorized_user_token"]))
    ws.send(frame("chart_create_session", [chart_session, ""]))
    return chart_session


def as_decimal(value: object, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {field}: {value!r}") from exc
    if not result.is_finite() or result < 0:
        raise ValueError(f"Invalid {field}: {value!r}")
    return result


def validate_price_row(row: dict) -> dict:
    for field in ("open", "high", "low", "close", "volume"):
        row[field] = as_decimal(row[field], field)
    if not row["low"] <= row["open"] <= row["high"]:
        raise ValueError("OHLC validation failed for open")
    if not row["low"] <= row["close"] <= row["high"]:
        raise ValueError("OHLC validation failed for close")
    return row


def candle_for_target(rows: list[dict], target_date: date) -> dict | None:
    """Return only a candle whose TradingView timestamp resolves to target_date."""
    matching = [row for row in rows if row["date"] == target_date]
    if not matching:
        return None
    return validate_price_row(matching[-1])


def request_symbol(
    ws,
    chart_session: str,
    symbol: Symbol,
    bars_requested: int,
    timeout: float,
    query_date: date,
) -> list[dict]:
    alias = f"symbol_{symbol.ordinal}_{random.randrange(1_000_000)}"
    series_id = f"s{symbol.ordinal}"
    definition = "=" + json.dumps(
        {
            "symbol": symbol.tradingview_symbol,
            "adjustment": "splits",
            "session": "regular",
        },
        separators=(",", ":"),
    )
    ws.send(frame("resolve_symbol", [chart_session, alias, definition]))
    ws.send(
        frame(
            "create_series",
            [chart_session, series_id, series_id, alias, "1D", bars_requested],
        )
    )

    received: dict[int, dict] = {}
    completed = False
    deadline = time.monotonic() + timeout
    while not completed and time.monotonic() < deadline:
        ws.settimeout(max(0.2, min(5.0, deadline - time.monotonic())))
        try:
            raw = ws.recv()
        except (WebSocketTimeoutException, socket.timeout):
            continue
        objects, heartbeats = parse_frames(raw)
        for heartbeat in heartbeats:
            ws.send(heartbeat)
        for obj in objects:
            method = obj.get("m")
            params = obj.get("p", [])
            if method == "timescale_update" and len(params) >= 2:
                series = params[1].get(series_id, {})
                for point in series.get("s", []):
                    values = point.get("v", [])
                    if len(values) < 6 or not isinstance(values[0], (int, float)):
                        continue
                    timestamp = int(values[0])
                    local_date = datetime.fromtimestamp(
                        timestamp, timezone.utc
                    ).astimezone(JAKARTA).date()
                    received[timestamp] = {
                        "company_name": symbol.company_name,
                        "ticker": symbol.ticker,
                        "tradingview_symbol": symbol.tradingview_symbol,
                        "date": local_date,
                        "open": values[1],
                        "high": values[2],
                        "low": values[3],
                        "close": values[4],
                        "volume": values[5],
                        "source": "TradingView",
                        "query_date": query_date,
                        "timeframe": PRICE_TIMEFRAME,
                    }
            elif method == "series_completed" and series_id in params:
                completed = True
            elif method in {"critical_error", "series_error"}:
                raise RuntimeError(json.dumps(params, ensure_ascii=False))

    try:
        ws.send(frame("remove_series", [chart_session, series_id]))
    except Exception:
        pass
    if not completed:
        raise TimeoutError(f"Timed out after {timeout:g}s")
    return [received[key] for key in sorted(received)]


def read_universe(connection: psycopg.Connection) -> list[Symbol]:
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT "Company Name", "Ticker", "TradingView Symbol",
                   "Exchange", "Security Type"
            FROM {UNIVERSE_TABLE}
            ORDER BY "Ticker"
            """
        )
        rows = cursor.fetchall()

    symbols: list[Symbol] = []
    seen_tickers: set[str] = set()
    for company_name, ticker, tv_symbol, exchange, asset_type in rows:
        ticker_text = str(ticker).strip().upper()
        tv_text = str(tv_symbol).strip().upper()
        if not ticker_text or not tv_text or ticker_text in seen_tickers:
            continue
        seen_tickers.add(ticker_text)
        symbols.append(
            Symbol(
                ordinal=len(symbols) + 1,
                company_name=str(company_name).strip(),
                ticker=ticker_text,
                tradingview_symbol=tv_text,
                exchange=str(exchange).strip() or "IDX",
                asset_type=str(asset_type).strip() or "UNSPECIFIED",
            )
        )
    if not symbols:
        raise RuntimeError("IDX_Stock_Universe contains no usable symbols")
    return symbols


def partition(items: list[Symbol], count: int) -> list[list[Symbol]]:
    count = min(count, len(items))
    base, extra = divmod(len(items), count)
    chunks: list[list[Symbol]] = []
    start = 0
    for index in range(count):
        size = base + (1 if index < extra else 0)
        chunks.append(items[start : start + size])
        start += size
    return chunks


def fetch_worker(
    worker_id: int,
    assignments: list[Symbol],
    target_date: date,
    query_date: date,
    bars_requested: int,
    timeout: float,
    delay: float,
    disable_proxy: bool,
) -> list[FetchOutcome]:
    outcomes: list[FetchOutcome] = []
    ws = None
    chart_session = None
    for index, symbol in enumerate(assignments, start=1):
        try:
            if ws is None:
                ws = open_socket(timeout, disable_proxy)
                chart_session = start_chart_session(ws)
            result = request_symbol(
                ws,
                chart_session,
                symbol,
                bars_requested,
                timeout,
                query_date,
            )
            latest_date = max((row["date"] for row in result), default=None)
            row = candle_for_target(result, target_date)
            if row is not None:
                outcomes.append(FetchOutcome(symbol, row, latest_date, None))
            else:
                outcomes.append(
                    FetchOutcome(
                        symbol,
                        None,
                        latest_date,
                        f"No 1D candle for {target_date.isoformat()}",
                    )
                )
        except Exception as exc:
            outcomes.append(
                FetchOutcome(symbol, None, None, f"{type(exc).__name__}: {exc}")
            )
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass
            ws = None
            chart_session = None

        if index % 50 == 0 or index == len(assignments):
            with PRINT_LOCK:
                print(
                    json.dumps(
                        {
                            "event": "worker_progress",
                            "worker": worker_id,
                            "processed": index,
                            "assigned": len(assignments),
                        }
                    ),
                    flush=True,
                )
        if delay:
            time.sleep(delay)

    if ws is not None:
        try:
            ws.close()
        except Exception:
            pass
    return outcomes


def fetch_all(
    symbols: list[Symbol],
    target_date: date,
    query_date: date,
    args: argparse.Namespace,
) -> list[FetchOutcome]:
    chunks = partition(symbols, args.workers)
    outcomes: list[FetchOutcome] = []
    with ThreadPoolExecutor(max_workers=len(chunks)) as executor:
        futures = [
            executor.submit(
                fetch_worker,
                worker_id,
                chunk,
                target_date,
                query_date,
                args.request_bars,
                args.timeout,
                args.delay,
                args.no_proxy,
            )
            for worker_id, chunk in enumerate(chunks, start=1)
        ]
        for future in as_completed(futures):
            outcomes.extend(future.result())
    outcomes.sort(key=lambda outcome: outcome.symbol.ordinal)
    return outcomes


def group_symbols(symbols: Iterable[Symbol]) -> dict[tuple[str, str], list[Symbol]]:
    grouped: dict[tuple[str, str], list[Symbol]] = {}
    for symbol in symbols:
        grouped.setdefault((symbol.exchange, symbol.asset_type), []).append(symbol)
    return grouped


def summarize_errors(outcomes: Iterable[FetchOutcome]) -> str | None:
    errors = [f"{item.symbol.ticker}: {item.error}" for item in outcomes if item.error]
    if not errors:
        return None
    shown = errors[:5]
    suffix = f"; plus {len(errors) - len(shown)} more" if len(errors) > len(shown) else ""
    return "; ".join(shown)[:3900] + suffix


def bulk_upsert_prices(
    connection: psycopg.Connection,
    rows: Iterable[dict],
    target_date: date,
) -> int:
    deduplicated = {(row["ticker"], row["date"]): row for row in rows}
    if not deduplicated:
        return 0

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            CREATE TEMP TABLE price_stock_stage
            (LIKE {PRICE_TABLE} INCLUDING DEFAULTS)
            ON COMMIT DROP
            """
        )
        columns_sql = ", ".join(PRICE_COLUMNS)
        with cursor.copy(f"COPY price_stock_stage ({columns_sql}) FROM STDIN") as copy:
            for row in deduplicated.values():
                copy.write_row(tuple(row[column] for column in PRICE_COLUMNS))

        updates = ", ".join(
            f"{column} = EXCLUDED.{column}"
            for column in PRICE_COLUMNS
            if column not in {"ticker", "date"}
        )
        cursor.execute(
            f"""
            INSERT INTO {PRICE_TABLE} ({columns_sql})
            SELECT {columns_sql}
            FROM price_stock_stage
            ON CONFLICT (ticker, date) DO UPDATE SET {updates}
            """
        )
        cursor.execute(
            f"""
            SELECT COUNT(DISTINCT ticker)
            FROM {PRICE_TABLE}
            WHERE date = %s
              AND ticker = ANY(%s)
            """,
            (target_date, [key[0] for key in deduplicated]),
        )
        verified = cursor.fetchone()[0]
    if verified != len(deduplicated):
        raise RuntimeError(
            f"Database verification failed: expected {len(deduplicated)}, found {verified}"
        )
    return verified


def write_monitoring_rows(
    connection: psycopg.Connection,
    records: list[dict],
) -> None:
    sql = f"""
        INSERT INTO {MONITORING_TABLE} (
            execution_id, trigger_source, query_time,
            exchange, asset_type, timeframe, run_type,
            expected_symbols, queried_symbols, updated_symbols, missing_symbols,
            missing_symbol_list, update_for_date, run_time, finished_at,
            attempt_count, status, last_error, updated_at
        )
        VALUES (
            %(execution_id)s, %(trigger_source)s, %(query_time)s,
            %(exchange)s, %(asset_type)s, %(timeframe)s, %(run_type)s,
            %(expected_symbols)s, %(queried_symbols)s, %(updated_symbols)s,
            %(missing_symbols)s, %(missing_symbol_list)s, %(update_for_date)s,
            %(run_time)s, %(finished_at)s, %(attempt_count)s, %(status)s,
            %(last_error)s, CURRENT_TIMESTAMP
        )
        ON CONFLICT (execution_id, exchange, asset_type, timeframe)
        DO UPDATE SET
            expected_symbols = EXCLUDED.expected_symbols,
            queried_symbols = EXCLUDED.queried_symbols,
            updated_symbols = EXCLUDED.updated_symbols,
            missing_symbols = EXCLUDED.missing_symbols,
            missing_symbol_list = EXCLUDED.missing_symbol_list,
            query_time = EXCLUDED.query_time,
            run_time = EXCLUDED.run_time,
            finished_at = EXCLUDED.finished_at,
            attempt_count = EXCLUDED.attempt_count,
            status = EXCLUDED.status,
            last_error = EXCLUDED.last_error,
            updated_at = CURRENT_TIMESTAMP
    """
    with connection.cursor() as cursor:
        cursor.executemany(
            sql,
            [
                {
                    **record,
                    "missing_symbol_list": Jsonb(record["missing_symbol_list"]),
                }
                for record in records
            ],
        )


def monitoring_records(
    universe: list[Symbol],
    queried: list[Symbol],
    outcomes: list[FetchOutcome],
    run_type: str,
    target_date: date,
    started_at: datetime,
    finished_at: datetime,
    execution_id: str,
    trigger_source: str,
    query_time: datetime,
    forced_status: str | None = None,
    forced_error: str | None = None,
) -> list[dict]:
    universe_groups = group_symbols(universe)
    queried_groups = group_symbols(queried)
    outcome_groups: dict[tuple[str, str], list[FetchOutcome]] = {}
    for outcome in outcomes:
        key = (outcome.symbol.exchange, outcome.symbol.asset_type)
        outcome_groups.setdefault(key, []).append(outcome)

    records: list[dict] = []
    for (exchange, asset_type), expected_group in sorted(universe_groups.items()):
        group_outcomes = outcome_groups.get((exchange, asset_type), [])
        updated = [item for item in group_outcomes if item.row is not None]
        missing = [item for item in group_outcomes if item.row is None]
        queried_count = len(queried_groups.get((exchange, asset_type), []))

        if forced_status:
            status = forced_status
        elif not queried_count:
            status = "SKIPPED"
        elif not missing:
            status = "SUCCESS"
        elif not updated:
            status = "FAILED" if run_type == "DAILY" else "NEEDS_REVIEW"
        else:
            status = "PARTIAL" if run_type == "DAILY" else "NEEDS_REVIEW"

        records.append(
            {
                "execution_id": execution_id,
                "trigger_source": trigger_source,
                "query_time": query_time,
                "exchange": exchange,
                "asset_type": asset_type,
                "timeframe": TIMEFRAME,
                "run_type": run_type,
                "expected_symbols": len(expected_group),
                "queried_symbols": queried_count,
                "updated_symbols": len(updated),
                "missing_symbols": len(missing),
                "missing_symbol_list": [item.symbol.ticker for item in missing],
                "update_for_date": target_date,
                "run_time": started_at,
                "finished_at": finished_at,
                "attempt_count": 1 if run_type == "DAILY" else 2,
                "status": status,
                "last_error": forced_error or summarize_errors(missing),
            }
        )
    return records


def get_recovery_symbols(
    connection: psycopg.Connection,
    universe: list[Symbol],
    target_date: date,
) -> list[Symbol]:
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            WITH latest_scheduled_daily AS (
                SELECT execution_id
                FROM {MONITORING_TABLE}
                WHERE update_for_date = %s
                  AND run_type = 'DAILY'
                  AND trigger_source = 'SCHEDULED'
                ORDER BY run_time DESC
                LIMIT 1
            )
            SELECT status, missing_symbol_list
            FROM {MONITORING_TABLE}
            WHERE execution_id = (SELECT execution_id FROM latest_scheduled_daily)
            """,
            (target_date,),
        )
        rows = cursor.fetchall()

        if rows and all(status in {"SUCCESS", "SKIPPED"} for status, _ in rows):
            return []

        if rows:
            requested = {
                str(ticker).strip().upper()
                for status, tickers in rows
                if status in {"PARTIAL", "FAILED"}
                for ticker in (tickers or [])
            }
        else:
            # If the DAILY process died before it could write monitoring, every
            # universe ticker without a stored target-date row is unverified.
            requested = {symbol.ticker for symbol in universe}

        if not requested:
            return []
        cursor.execute(
            f"""
            SELECT DISTINCT ticker
            FROM {PRICE_TABLE}
            WHERE date = %s
              AND ticker = ANY(%s)
            """,
            (target_date, list(requested)),
        )
        already_present = {str(row[0]).strip().upper() for row in cursor.fetchall()}

    return [
        symbol
        for symbol in universe
        if symbol.ticker in requested and symbol.ticker not in already_present
    ]


def is_already_successful(
    connection: psycopg.Connection,
    target_date: date,
    run_type: str,
    trigger_source: str,
) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            WITH latest_execution AS (
                SELECT execution_id
                FROM {MONITORING_TABLE}
                WHERE update_for_date = %s
                  AND run_type = %s
                  AND trigger_source = %s
                ORDER BY run_time DESC
                LIMIT 1
            )
            SELECT COUNT(*) FILTER (WHERE status = 'SUCCESS'), COUNT(*)
            FROM {MONITORING_TABLE}
            WHERE execution_id = (SELECT execution_id FROM latest_execution)
            """,
            (target_date, run_type, trigger_source),
        )
        successful, total = cursor.fetchone()
    return total > 0 and successful == total


def resolve_mode(requested_mode: str, now_jakarta: datetime) -> str:
    if requested_mode != "auto":
        return requested_mode
    minute_of_day = now_jakarta.hour * 60 + now_jakarta.minute
    if RECOVERY_WINDOW_START_MINUTE <= minute_of_day <= RECOVERY_WINDOW_END_MINUTE:
        return "recovery"
    if DAILY_WINDOW_START_MINUTE <= minute_of_day <= DAILY_WINDOW_END_MINUTE:
        return "daily"
    return "manual"


def resolve_trigger_source(mode: str, now_jakarta: datetime) -> str:
    """Infer Run now outside each service's narrow scheduled execution window."""
    minute_of_day = now_jakarta.hour * 60 + now_jakarta.minute
    if mode == "recovery":
        scheduled = RECOVERY_WINDOW_START_MINUTE <= minute_of_day <= RECOVERY_WINDOW_END_MINUTE
    else:
        scheduled = DAILY_WINDOW_START_MINUTE <= minute_of_day <= DAILY_WINDOW_END_MINUTE
    return "SCHEDULED" if scheduled else "MANUAL"


def previous_weekday(current_date: date) -> date:
    candidate = current_date - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def try_acquire_run_lock(connection: psycopg.Connection) -> bool:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(hashtext(%s))", (RUN_LOCK_KEY,))
        return bool(cursor.fetchone()[0])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=("auto", "daily", "recovery", "manual"), default="auto"
    )
    parser.add_argument("--target-date", type=date.fromisoformat)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--request-bars", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=45)
    parser.add_argument("--delay", type=float, default=0.10)
    parser.add_argument("--no-proxy", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    if not 1 <= args.workers <= 16:
        parser.error("--workers must be between 1 and 16")
    if args.request_bars < 1 or args.timeout <= 0 or args.delay < 0 or args.limit < 0:
        parser.error("invalid numeric argument")
    if args.limit and not args.dry_run:
        parser.error("--limit is allowed only with --dry-run")
    return args


def main() -> int:
    args = parse_args()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")

    now_jakarta = datetime.now(JAKARTA)
    mode = resolve_mode(args.mode, now_jakarta)
    trigger_source = resolve_trigger_source(mode, now_jakarta)
    run_type = "RECOVERY" if mode == "recovery" else "DAILY"
    target_date = args.target_date or (
        now_jakarta.date()
        if mode in {"daily", "manual"}
        else previous_weekday(now_jakarta.date())
    )
    started_at = datetime.now(timezone.utc)
    query_date = now_jakarta.date()
    query_time = started_at
    execution_id = str(uuid.uuid4())

    with psycopg.connect(database_url) as connection:
        universe = read_universe(connection)
        if args.limit:
            universe = universe[: args.limit]

        print(
            json.dumps(
                {
                    "event": "run_started",
                    "mode": mode,
                    "trigger_source": trigger_source,
                    "execution_id": execution_id,
                    "target_date": target_date.isoformat(),
                    "universe_symbols": len(universe),
                    "scheduled_time_zone": "Asia/Jakarta",
                }
            ),
            flush=True,
        )

        if not try_acquire_run_lock(connection):
            records = monitoring_records(
                universe,
                [],
                [],
                run_type,
                target_date,
                started_at,
                datetime.now(timezone.utc),
                execution_id,
                trigger_source,
                query_time,
                forced_status="SKIPPED",
                forced_error="SKIPPED_BUSY: another IDX price update is still running",
            )
            if not args.dry_run:
                write_monitoring_rows(connection, records)
                connection.commit()
            print(json.dumps({"event": "run_skipped", "reason": "busy"}))
            return 0

        if target_date.weekday() >= 5:
            records = monitoring_records(
                universe,
                [],
                [],
                run_type,
                target_date,
                started_at,
                datetime.now(timezone.utc),
                execution_id,
                trigger_source,
                query_time,
                forced_status="SKIPPED",
                forced_error="Weekend: IDX daily prices were not queried",
            )
            if not args.dry_run:
                write_monitoring_rows(connection, records)
                connection.commit()
            print(json.dumps({"event": "run_skipped", "reason": "weekend"}))
            return 0

        if mode == "recovery" and not args.dry_run and is_already_successful(
            connection, target_date, run_type, trigger_source
        ):
            print(json.dumps({"event": "run_skipped", "reason": "already_successful"}))
            return 0

        queried = (
            universe
            if mode in {"daily", "manual"}
            else get_recovery_symbols(connection, universe, target_date)
        )

        if not queried:
            records = monitoring_records(
                universe,
                [],
                [],
                run_type,
                target_date,
                started_at,
                datetime.now(timezone.utc),
                execution_id,
                trigger_source,
                query_time,
                forced_status="SKIPPED",
                forced_error="No missing symbols from the preceding DAILY run",
            )
            if not args.dry_run:
                write_monitoring_rows(connection, records)
                connection.commit()
            print(json.dumps({"event": "run_skipped", "reason": "no_missing_symbols"}))
            return 0

        query_time = datetime.now(timezone.utc)
        outcomes = fetch_all(queried, target_date, query_date, args)
        rows = [outcome.row for outcome in outcomes if outcome.row is not None]

        if mode in {"daily", "manual"} and not rows:
            valid_prior_bars = [
                outcome
                for outcome in outcomes
                if outcome.latest_date is not None and outcome.latest_date < target_date
            ]
            if len(valid_prior_bars) >= max(1, int(len(outcomes) * 0.90)):
                records = monitoring_records(
                    universe,
                    queried,
                    outcomes,
                    run_type,
                    target_date,
                    started_at,
                    datetime.now(timezone.utc),
                    execution_id,
                    trigger_source,
                    query_time,
                    forced_status="SKIPPED",
                    forced_error=(
                        "NO_CURRENT_CANDLE: TradingView returned no candle dated "
                        f"{target_date.isoformat()}; older candles were ignored"
                    ),
                )
                if not args.dry_run:
                    write_monitoring_rows(connection, records)
                    connection.commit()
                print(json.dumps({"event": "run_skipped", "reason": "non_trading_day"}))
                return 0

        finished_at = datetime.now(timezone.utc)
        records = monitoring_records(
            universe,
            queried,
            outcomes,
            run_type,
            target_date,
            started_at,
            finished_at,
            execution_id,
            trigger_source,
            query_time,
        )

        if args.dry_run:
            print(
                json.dumps(
                    {
                        "event": "dry_run_completed",
                        "records": records,
                    },
                    default=str,
                )
            )
            return 0

        try:
            verified = bulk_upsert_prices(connection, rows, target_date)
            write_monitoring_rows(connection, records)
            connection.commit()
        except Exception as exc:
            connection.rollback()
            failure_records = monitoring_records(
                universe,
                queried,
                [FetchOutcome(symbol, None, None, "Database write failed") for symbol in queried],
                run_type,
                target_date,
                started_at,
                datetime.now(timezone.utc),
                execution_id,
                trigger_source,
                query_time,
                forced_status="FAILED",
                forced_error=f"{type(exc).__name__}: {exc}"[:4000],
            )
            write_monitoring_rows(connection, failure_records)
            connection.commit()
            raise

        statuses = sorted({record["status"] for record in records})
        summary = {
            "event": "run_completed",
            "mode": mode,
            "trigger_source": trigger_source,
            "execution_id": execution_id,
            "target_date": target_date.isoformat(),
            "expected_symbols": len(universe),
            "queried_symbols": len(queried),
            "updated_symbols": verified,
            "missing_symbols": len(queried) - verified,
            "statuses": statuses,
        }
        print(json.dumps(summary), flush=True)
        if "FAILED" in statuses:
            return 1
        if "NEEDS_REVIEW" in statuses:
            return 2
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
