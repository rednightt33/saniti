#!/usr/bin/env python3
"""Load final daily fixed-income candles from TradingView into PostgreSQL."""

from __future__ import annotations

import argparse
import json
import os
import random
import socket
import string
import sys
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, time as clock_time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import psycopg
from psycopg.types.json import Jsonb
from websocket import WebSocketTimeoutException, create_connection


WS_URL = "wss://data.tradingview.com/socket.io/websocket"
ORIGIN = "https://www.tradingview.com"
TIMEFRAME = "1D"
DATE_MAPPING_VERSION = "verified-provider-session-label-v4"
PRICE_TABLE = 'public."Price_Fixed_Income"'
UNIVERSE_TABLE = 'public."Universe_Fixed_income"'
SCHEDULE_TABLE = 'public."Fixed_Income_Market_Schedule"'
MONITORING_TABLE = 'public."Monitoring_Fixed_Income"'
RUN_LOCK_NAMESPACE = "saniti.fixed-income-price-cron"
PRINT_LOCK = threading.Lock()
PRICE_COLUMNS = (
    "Country",
    "instrument_name",
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
    "metric_type",
    "value_unit",
    "Timeframe",
    "source_bar_time",
    "market_close_at",
    "is_final",
    "finalized_at",
)


@dataclass(frozen=True)
class MarketSchedule:
    market_code: str
    country: str
    timezone_name: str
    session_close_local: clock_time
    finality_delay_minutes: int
    source_date_mapping: str
    enabled: bool
    correction_lookback_sessions: int
    provider_timezone_name: str | None = None
    provider_session: str | None = None

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)


@dataclass(frozen=True)
class Series:
    ordinal: int
    country: str
    instrument_name: str
    ticker: str
    tradingview_symbol: str
    metric_type: str
    value_unit: str


@dataclass(frozen=True)
class FetchOutcome:
    series: Series
    row: dict | None
    available_dates: tuple[date, ...]
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
    verify_tls = os.environ.get("TRADINGVIEW_VERIFY_TLS", "true").strip().lower()
    if verify_tls not in {"1", "true", "yes", "on"}:
        raise RuntimeError("TRADINGVIEW_VERIFY_TLS must remain enabled")
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


def as_decimal(value: object, field: str, *, nullable: bool = False) -> Decimal | None:
    if value is None and nullable:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {field}: {value!r}") from exc
    if not result.is_finite() or result < 0:
        raise ValueError(f"Invalid {field}: {value!r}")
    return result


def validate_price_row(row: dict) -> dict:
    for field in ("open", "high", "low", "close"):
        row[field] = as_decimal(row[field], field)
    row["volume"] = as_decimal(row.get("volume"), "volume", nullable=True)
    if not row["low"] <= row["open"] <= row["high"]:
        raise ValueError("OHLC validation failed for open")
    if not row["low"] <= row["close"] <= row["high"]:
        raise ValueError("OHLC validation failed for close")
    return row


def previous_business_day(value: date) -> date:
    candidate = value - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def market_close_at(schedule: MarketSchedule, session_date: date) -> datetime:
    return datetime.combine(
        session_date, schedule.session_close_local, schedule.timezone
    ).astimezone(timezone.utc)


def latest_completed_session(schedule: MarketSchedule, now: datetime) -> date:
    local_now = now.astimezone(schedule.timezone)
    candidate = local_now.date()
    if candidate.weekday() >= 5:
        while candidate.weekday() >= 5:
            candidate -= timedelta(days=1)
        return candidate
    final_after = datetime.combine(
        candidate, schedule.session_close_local, schedule.timezone
    ) + timedelta(minutes=schedule.finality_delay_minutes)
    if local_now < final_after:
        return previous_business_day(candidate)
    return candidate


def resolve_bar_date(
    timestamp: int, provider_timezone: str, source_date_mapping: str
) -> date:
    try:
        ZoneInfo(provider_timezone)
    except Exception as exc:
        raise ValueError(f"TradingView returned invalid timezone {provider_timezone!r}") from exc
    # TradingView's fixed-income 1D protocol uses the UTC calendar component as
    # its raw chart label. Markets encode that label differently, so the mapping
    # is stored with the market schedule instead of being selected by ticker.
    source_label_date = datetime.fromtimestamp(timestamp, timezone.utc).date()
    if source_date_mapping == "CURRENT_OR_PREVIOUS_BUSINESS_DAY":
        while source_label_date.weekday() >= 5:
            source_label_date -= timedelta(days=1)
        return source_label_date
    if source_date_mapping == "NEXT_BUSINESS_DAY":
        source_label_date += timedelta(days=1)
        while source_label_date.weekday() >= 5:
            source_label_date += timedelta(days=1)
        return source_label_date
    raise ValueError(f"Unsupported source date mapping {source_date_mapping!r}")


def request_series(
    ws,
    chart_session: str,
    series: Series,
    bars_requested: int,
    timeout: float,
    query_date: date,
    target_date: date,
    close_at: datetime,
    finalized_at: datetime,
    source_date_mapping: str,
    expected_timezone: str | None = None,
    expected_session: str | None = None,
) -> tuple[list[dict], str]:
    alias = f"symbol_{series.ordinal}_{random.randrange(1_000_000)}"
    series_id = f"s{series.ordinal}"
    definition = "=" + json.dumps(
        {
            "symbol": series.tradingview_symbol,
            "adjustment": "splits",
            "session": "regular",
        },
        separators=(",", ":"),
    )
    ws.send(frame("resolve_symbol", [chart_session, alias, definition]))
    ws.send(
        frame(
            "create_series",
            [chart_session, series_id, series_id, alias, TIMEFRAME, bars_requested],
        )
    )

    received: dict[int, list] = {}
    provider_timezone: str | None = None
    provider_session: str | None = None
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
            if method == "symbol_resolved" and alias in params:
                payload = params[-1] if params else {}
                if isinstance(payload, dict):
                    provider_timezone = payload.get("timezone")
                    provider_session = payload.get("session")
            elif method == "timescale_update" and len(params) >= 2:
                payload = params[1]
                if not isinstance(payload, dict):
                    continue
                tv_series = payload.get(series_id, {})
                for point in tv_series.get("s", []):
                    values = point.get("v", [])
                    if len(values) >= 5 and isinstance(values[0], (int, float)):
                        received[int(values[0])] = values
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
    if not provider_timezone:
        raise RuntimeError("TradingView did not return the resolved symbol timezone")
    if expected_timezone is not None and provider_timezone != expected_timezone:
        raise RuntimeError(
            f"SOURCE_SESSION_MISMATCH: timezone {provider_timezone!r}; expected {expected_timezone!r}"
        )
    if expected_session is not None and provider_session != expected_session:
        raise RuntimeError(
            f"SOURCE_SESSION_MISMATCH: session {provider_session!r}; expected {expected_session!r}"
        )

    rows: list[dict] = []
    for timestamp in sorted(received):
        values = received[timestamp]
        candle_date = resolve_bar_date(
            timestamp, provider_timezone, source_date_mapping
        )
        rows.append(
            {
                "Country": series.country,
                "instrument_name": series.instrument_name,
                "ticker": series.ticker,
                "tradingview_symbol": series.tradingview_symbol,
                "date": candle_date,
                "open": values[1],
                "high": values[2],
                "low": values[3],
                "close": values[4],
                "volume": values[5] if len(values) > 5 else None,
                "source": "TradingView",
                "query_date": query_date,
                "metric_type": series.metric_type,
                "value_unit": series.value_unit,
                "Timeframe": TIMEFRAME,
                "source_bar_time": datetime.fromtimestamp(timestamp, timezone.utc),
                "market_close_at": close_at,
                "is_final": True,
                "finalized_at": finalized_at,
            }
        )
    if rows:
        print(json.dumps({
            "event": "source_session_verified", "symbol": series.tradingview_symbol,
            "provider_timezone": provider_timezone, "provider_session": provider_session,
            "source_date_mapping": source_date_mapping, "target_date": target_date.isoformat(),
            "latest_source_bar_time": rows[-1]["source_bar_time"].isoformat(),
            "latest_observation_date": rows[-1]["date"].isoformat(),
            "date_mapping_version": DATE_MAPPING_VERSION,
        }), flush=True)
    return rows, provider_timezone


def candle_for_target(rows: list[dict], target_date: date) -> dict | None:
    matching = [row for row in rows if row["date"] == target_date]
    if not matching:
        return None
    return validate_price_row(matching[-1])


def read_schedule(connection: psycopg.Connection, market_code: str) -> MarketSchedule:
    row = connection.execute(
        f"""
        SELECT market_code,country,timezone_name,session_close_local,
               finality_delay_minutes,source_date_mapping,enabled,
               correction_lookback_sessions,provider_timezone_name,provider_session
        FROM {SCHEDULE_TABLE} WHERE market_code=%s
        """,
        (market_code,),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Unknown fixed-income market {market_code!r}")
    schedule = MarketSchedule(*row)
    if not schedule.enabled:
        raise RuntimeError(f"Fixed-income market {market_code!r} is disabled")
    _ = schedule.timezone
    return schedule


def read_universe(
    connection: psycopg.Connection, schedule: MarketSchedule
) -> list[Series]:
    rows = connection.execute(
        f"""
        SELECT country,instrument_name,ticker,tradingview_symbol,metric_type,value_unit
        FROM {UNIVERSE_TABLE}
        WHERE country=%s
        ORDER BY ticker,metric_type
        """,
        (schedule.country,),
    ).fetchall()
    result: list[Series] = []
    seen: set[tuple[str, str]] = set()
    for country, name, ticker, symbol, metric_type, value_unit in rows:
        key = (str(ticker).strip().upper(), str(metric_type).strip())
        if key in seen:
            raise RuntimeError(f"Duplicate fixed-income universe series {key}")
        seen.add(key)
        result.append(
            Series(
                ordinal=len(result) + 1,
                country=str(country),
                instrument_name=str(name),
                ticker=key[0],
                tradingview_symbol=str(symbol).strip().upper(),
                metric_type=key[1],
                value_unit=str(value_unit).strip(),
            )
        )
    if not result:
        raise RuntimeError(f"No enabled series for fixed-income market {schedule.market_code}")
    return result


def partition(items: list[Series], count: int) -> list[list[Series]]:
    count = min(count, len(items))
    base, extra = divmod(len(items), count)
    chunks: list[list[Series]] = []
    start = 0
    for index in range(count):
        size = base + (1 if index < extra else 0)
        chunks.append(items[start : start + size])
        start += size
    return chunks


def fetch_worker(
    worker_id: int,
    assignments: list[Series],
    target_date: date,
    query_date: date,
    close_at: datetime,
    finalized_at: datetime,
    source_date_mapping: str,
    bars_requested: int,
    timeout: float,
    delay: float,
    disable_proxy: bool,
    expected_timezone: str | None = None,
    expected_session: str | None = None,
) -> list[FetchOutcome]:
    outcomes: list[FetchOutcome] = []
    ws = None
    chart_session = None
    for index, item in enumerate(assignments, start=1):
        try:
            if ws is None:
                ws = open_socket(timeout, disable_proxy)
                chart_session = start_chart_session(ws)
            rows, _ = request_series(
                ws,
                chart_session,
                item,
                bars_requested,
                timeout,
                query_date,
                target_date,
                close_at,
                finalized_at,
                source_date_mapping,
                expected_timezone,
                expected_session,
            )
            dates = tuple(sorted({row["date"] for row in rows}))
            row = candle_for_target(rows, target_date)
            outcomes.append(
                FetchOutcome(
                    item,
                    row,
                    dates,
                    None if row else f"No final 1D candle for {target_date.isoformat()}",
                )
            )
        except Exception as exc:
            outcomes.append(FetchOutcome(item, None, (), f"{type(exc).__name__}: {exc}"))
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass
            ws = None
            chart_session = None
        if index % 12 == 0 or index == len(assignments):
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
    universe: list[Series],
    target_date: date,
    query_date: date,
    close_at: datetime,
    finalized_at: datetime,
    source_date_mapping: str,
    args: argparse.Namespace,
    expected_timezone: str | None = None,
    expected_session: str | None = None,
) -> list[FetchOutcome]:
    chunks = partition(universe, args.workers)
    outcomes: list[FetchOutcome] = []
    with ThreadPoolExecutor(max_workers=len(chunks)) as executor:
        futures = [
            executor.submit(
                fetch_worker,
                worker_id,
                chunk,
                target_date,
                query_date,
                close_at,
                finalized_at,
                source_date_mapping,
                args.request_bars,
                args.timeout,
                args.delay,
                args.no_proxy,
                expected_timezone,
                expected_session,
            )
            for worker_id, chunk in enumerate(chunks, start=1)
        ]
        for future in as_completed(futures):
            outcomes.extend(future.result())
    outcomes.sort(key=lambda outcome: outcome.series.ordinal)
    return outcomes


def summarize_errors(outcomes: Iterable[FetchOutcome]) -> str | None:
    errors = [
        f"{item.series.ticker}/{item.series.metric_type}: {item.error}"
        for item in outcomes
        if item.error
    ]
    if not errors:
        return None
    shown = errors[:5]
    suffix = f"; plus {len(errors) - len(shown)} more" if len(errors) > len(shown) else ""
    return ("; ".join(shown) + suffix)[:4000]


def bulk_upsert_prices(connection: psycopg.Connection, rows: list[dict]) -> tuple[int, int]:
    deduplicated = {
        (row["tradingview_symbol"], row["date"], row["metric_type"], row["Timeframe"]): row
        for row in rows
    }
    if not deduplicated:
        return 0, 0
    with connection.cursor() as cursor:
        columns_sql = ", ".join(f'"{name}"' for name in PRICE_COLUMNS)
        # The source table has required lifecycle columns such as ingestion_time.
        # Stage only the explicit loader payload so COPY does not inherit source
        # constraints for columns that the final INSERT computes itself.
        cursor.execute(
            f"CREATE TEMP TABLE fixed_income_stage ON COMMIT DROP AS "
            f"SELECT {columns_sql} FROM {PRICE_TABLE} WITH NO DATA"
        )
        with cursor.copy(f"COPY fixed_income_stage ({columns_sql}) FROM STDIN") as copy:
            for row in deduplicated.values():
                copy.write_row(tuple(row[column] for column in PRICE_COLUMNS))
        cursor.execute(
            f"""
            WITH changed AS (
              INSERT INTO {PRICE_TABLE} AS target ({columns_sql},ingestion_time)
              SELECT {columns_sql},statement_timestamp() FROM fixed_income_stage
              ON CONFLICT(tradingview_symbol,date,metric_type,"Timeframe") DO UPDATE SET
                "Country"=EXCLUDED."Country",instrument_name=EXCLUDED.instrument_name,
                ticker=EXCLUDED.ticker,open=EXCLUDED.open,high=EXCLUDED.high,
                low=EXCLUDED.low,close=EXCLUDED.close,volume=EXCLUDED.volume,
                source=EXCLUDED.source,query_date=EXCLUDED.query_date,
                value_unit=EXCLUDED.value_unit,source_bar_time=EXCLUDED.source_bar_time,
                market_close_at=EXCLUDED.market_close_at,is_final=EXCLUDED.is_final,
                finalized_at=EXCLUDED.finalized_at,ingestion_time=statement_timestamp()
              WHERE ROW(target."Country",target.instrument_name,target.ticker,target.open,
                        target.high,target.low,target.close,target.volume,target.source,
                        target.value_unit,target.source_bar_time,target.market_close_at,target.is_final)
                    IS DISTINCT FROM
                    ROW(EXCLUDED."Country",EXCLUDED.instrument_name,EXCLUDED.ticker,EXCLUDED.open,
                        EXCLUDED.high,EXCLUDED.low,EXCLUDED.close,EXCLUDED.volume,EXCLUDED.source,
                        EXCLUDED.value_unit,EXCLUDED.source_bar_time,EXCLUDED.market_close_at,EXCLUDED.is_final)
              RETURNING 1
            ) SELECT count(*) FROM changed
            """
        )
        changed = int(cursor.fetchone()[0])
        cursor.execute(
            f"""
            SELECT count(*) FROM {PRICE_TABLE} p
            JOIN fixed_income_stage s USING(tradingview_symbol,date,metric_type,"Timeframe")
            WHERE p.is_final
              AND ROW(p.open,p.high,p.low,p.close,p.volume,p.source_bar_time,p.market_close_at)
                  IS NOT DISTINCT FROM
                  ROW(s.open,s.high,s.low,s.close,s.volume,s.source_bar_time,s.market_close_at)
            """
        )
        verified = int(cursor.fetchone()[0])
    if verified != len(deduplicated):
        raise RuntimeError(
            f"Database verification failed: expected {len(deduplicated)}, found {verified}"
        )
    return verified, changed


def monitoring_status(queried: int, verified: int) -> str:
    if queried == 0:
        return "SKIPPED"
    if verified == queried:
        return "SUCCESS"
    if verified == 0:
        return "FAILED"
    return "PARTIAL"


def write_monitoring(
    connection: psycopg.Connection,
    *,
    execution_id: str,
    run_type: str,
    trigger_source: str,
    target_date: date,
    market_code: str,
    service_name: str,
    started_at: datetime,
    finished_at: datetime,
    universe: list[Series],
    outcomes: list[FetchOutcome],
    verified: int,
    changed: int,
    forced_status: str | None = None,
    forced_error: str | None = None,
) -> str:
    missing = [item for item in outcomes if item.row is None]
    queried = len(outcomes)
    status = forced_status or monitoring_status(queried, verified)
    missing_payload = [
        {"ticker": item.series.ticker, "metric_type": item.series.metric_type}
        for item in missing
    ]
    connection.execute(
        f"""
        INSERT INTO {MONITORING_TABLE}(
          execution_id,run_type,trigger_source,target_date,timeframe,started_at,finished_at,
          expected_series,queried_series,updated_series,missing_series,missing_series_list,
          status,last_error,service_name,market_code,final_series,changed_series
        ) VALUES(
          %s::uuid,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
        )
        """,
        (
            execution_id,
            run_type,
            trigger_source,
            target_date,
            TIMEFRAME,
            started_at,
            finished_at,
            len(universe),
            queried,
            verified,
            len(missing),
            Jsonb(missing_payload),
            status,
            forced_error or summarize_errors(missing),
            service_name,
            market_code,
            verified,
            changed,
        ),
    )
    connection.commit()
    return status


def notify_telegram_monitor(execution_id: str, *, opener=urlopen, sleep_fn=time.sleep) -> bool:
    notify_url = os.environ.get("TELEGRAM_NOTIFY_URL", "").strip()
    notify_secret = os.environ.get("TELEGRAM_NOTIFY_SECRET", "").strip()
    if not notify_url or not notify_secret:
        print(json.dumps({"event": "telegram_notify_skipped", "reason": "not_configured"}))
        return False
    payload = json.dumps(
        {"source_table": "Monitoring_Fixed_Income", "execution_id": execution_id}
    ).encode()
    attempts = max(1, int(os.environ.get("TELEGRAM_NOTIFY_ATTEMPTS", "4")))
    timeout = max(1.0, float(os.environ.get("TELEGRAM_NOTIFY_TIMEOUT", "20")))
    last_error = "unknown"
    for attempt in range(1, attempts + 1):
        request = Request(
            notify_url,
            data=payload,
            headers={"Content-Type": "application/json", "X-Notify-Secret": notify_secret},
            method="POST",
        )
        try:
            with opener(request, timeout=timeout) as response:
                response.read()
                if 200 <= response.status < 300:
                    print(json.dumps({"event": "telegram_notify_accepted", "attempt": attempt}))
                    return True
                last_error = f"HTTP {response.status}"
        except HTTPError as exc:
            last_error = f"HTTP {exc.code}"
            if 400 <= exc.code < 500 and exc.code not in {408, 429}:
                break
        except (URLError, TimeoutError, OSError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        if attempt < attempts:
            sleep_fn(min(2 ** (attempt - 1), 8))
    print(json.dumps({"event": "telegram_notify_failed", "error": last_error[:500]}))
    return False


def resolve_trigger_source(
    mode: str, schedule: MarketSchedule, now: datetime, scheduled_tolerance_minutes: int = 90
) -> str:
    local_now = now.astimezone(schedule.timezone)
    scheduled_delay = schedule.finality_delay_minutes + (60 if mode == "recovery" else 0)
    expected = datetime.combine(
        local_now.date(), schedule.session_close_local, schedule.timezone
    ) + timedelta(minutes=scheduled_delay)
    delta = abs((local_now - expected).total_seconds()) / 60
    return "SCHEDULED" if delta <= scheduled_tolerance_minutes else "MANUAL"


def try_acquire_run_lock(connection: psycopg.Connection, market_code: str) -> bool:
    return bool(
        connection.execute(
            "SELECT pg_try_advisory_lock(hashtext(%s))",
            (f"{RUN_LOCK_NAMESPACE}.{market_code}",),
        ).fetchone()[0]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market", required=True)
    parser.add_argument("--mode", choices=("daily", "recovery", "manual"), required=True)
    parser.add_argument("--target-date", type=date.fromisoformat)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--request-bars", type=int, default=7)
    parser.add_argument("--timeout", type=float, default=45)
    parser.add_argument("--delay", type=float, default=0.10)
    parser.add_argument("--no-proxy", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    if not 1 <= args.workers <= 16:
        parser.error("--workers must be between 1 and 16")
    if args.request_bars < 2 or args.timeout <= 0 or args.delay < 0 or args.limit < 0:
        parser.error("invalid numeric argument")
    if args.limit and not args.dry_run:
        parser.error("--limit is allowed only with --dry-run")
    args.market = args.market.strip().upper()
    return args


def main() -> int:
    args = parse_args()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")
    now = datetime.now(timezone.utc)
    started_at = now
    execution_id = str(uuid.uuid4())
    run_type = "RECOVERY" if args.mode == "recovery" else "DAILY"
    service_name = os.environ.get("RAILWAY_SERVICE_NAME", "fixed-income-price-cron")

    with psycopg.connect(database_url) as connection:
        schedule = read_schedule(connection, args.market)
        universe = read_universe(connection, schedule)
        if args.limit:
            universe = universe[: args.limit]
        target_date = args.target_date or latest_completed_session(schedule, now)
        close_at = market_close_at(schedule, target_date)
        final_after = close_at + timedelta(minutes=schedule.finality_delay_minutes)
        trigger_source = resolve_trigger_source(args.mode, schedule, now)
        if now < final_after:
            raise RuntimeError(
                f"Target session {target_date} is not final until {final_after.isoformat()}"
            )
        print(
            json.dumps(
                {
                    "event": "run_started",
                    "execution_id": execution_id,
                    "market": schedule.market_code,
                    "country": schedule.country,
                    "mode": args.mode,
                    "trigger_source": trigger_source,
                    "target_date": target_date.isoformat(),
                    "market_close_at": close_at.isoformat(),
                    "date_mapping_version": DATE_MAPPING_VERSION,
                    "series": len(universe),
                }
            ),
            flush=True,
        )
        if not try_acquire_run_lock(connection, schedule.market_code):
            status = write_monitoring(
                connection,
                execution_id=execution_id,
                run_type=run_type,
                trigger_source=trigger_source,
                target_date=target_date,
                market_code=schedule.market_code,
                service_name=service_name,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                universe=universe,
                outcomes=[],
                verified=0,
                changed=0,
                forced_status="SKIPPED",
                forced_error="SKIPPED_BUSY: another run for this market is active",
            )
            notify_telegram_monitor(execution_id)
            return 0 if status == "SKIPPED" else 1

        finalized_at = datetime.now(timezone.utc)
        outcomes = fetch_all(
            universe,
            target_date,
            now.astimezone(schedule.timezone).date(),
            close_at,
            finalized_at,
            schedule.source_date_mapping,
            args,
            schedule.provider_timezone_name,
            schedule.provider_session,
        )
        rows = [item.row for item in outcomes if item.row is not None]
        if args.dry_run:
            available_date_counts: dict[str, int] = {}
            for item in outcomes:
                for available_date in item.available_dates:
                    key = available_date.isoformat()
                    available_date_counts[key] = available_date_counts.get(key, 0) + 1
            print(
                json.dumps(
                    {
                        "event": "dry_run_completed",
                        "market": schedule.market_code,
                        "target_date": target_date.isoformat(),
                        "queried": len(outcomes),
                        "final": len(rows),
                        "available_date_counts": dict(sorted(available_date_counts.items())),
                        "errors": summarize_errors(outcomes),
                    }
                ),
                flush=True,
            )
            return 0 if rows else 1

        prior_only = [
            item
            for item in outcomes
            if item.available_dates and max(item.available_dates) < target_date
        ]
        if not rows and len(prior_only) >= max(1, int(len(outcomes) * 0.90)):
            status = write_monitoring(
                connection,
                execution_id=execution_id,
                run_type=run_type,
                trigger_source=trigger_source,
                target_date=target_date,
                market_code=schedule.market_code,
                service_name=service_name,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                universe=universe,
                outcomes=outcomes,
                verified=0,
                changed=0,
                forced_status="SKIPPED",
                forced_error=(
                    "NO_CURRENT_CANDLE: no source bar resolved to the target session; "
                    f"no row was written for {target_date.isoformat()}"
                ),
            )
            notify_telegram_monitor(execution_id)
            print(json.dumps({"event": "run_skipped", "reason": "no_current_candle"}))
            return 0

        try:
            verified, changed = bulk_upsert_prices(connection, rows)
            status = write_monitoring(
                connection,
                execution_id=execution_id,
                run_type=run_type,
                trigger_source=trigger_source,
                target_date=target_date,
                market_code=schedule.market_code,
                service_name=service_name,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                universe=universe,
                outcomes=outcomes,
                verified=verified,
                changed=changed,
            )
        except Exception as exc:
            connection.rollback()
            status = write_monitoring(
                connection,
                execution_id=execution_id,
                run_type=run_type,
                trigger_source=trigger_source,
                target_date=target_date,
                market_code=schedule.market_code,
                service_name=service_name,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                universe=universe,
                outcomes=outcomes,
                verified=0,
                changed=0,
                forced_status="FAILED",
                forced_error=f"{type(exc).__name__}: {exc}"[:4000],
            )
            notify_telegram_monitor(execution_id)
            raise
        notify_telegram_monitor(execution_id)
        print(
            json.dumps(
                {
                    "event": "run_completed",
                    "execution_id": execution_id,
                    "market": schedule.market_code,
                    "target_date": target_date.isoformat(),
                    "verified_final_series": verified,
                    "changed_series": changed,
                    "missing_series": len(outcomes) - verified,
                    "status": status,
                }
            ),
            flush=True,
        )
        return 1 if status == "FAILED" else 0


def run_entrypoint(main_fn=main, exit_fn=os._exit) -> None:
    exit_code = 1
    try:
        exit_code = main_fn()
    except SystemExit as exc:
        exit_code = exc.code if isinstance(exc.code, int) else 1
    except BaseException:
        traceback.print_exc()
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        exit_fn(exit_code)


if __name__ == "__main__":
    run_entrypoint()
