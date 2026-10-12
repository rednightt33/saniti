#!/usr/bin/env python3
"""Event-driven Telegram notifications for completed Railway data jobs."""

from __future__ import annotations

import hmac
import json
import os
import re
import socket
from dataclasses import dataclass
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import psycopg
from psycopg.types.json import Jsonb


MONITORING_TABLE = 'public."Monitoring_Price_ALL"'
LOG_TABLE = 'public."Telegram_Notification_Log"'
PRICE_MONITORING_SOURCES = {"Monitoring_Price_ALL", "Monitoring_Fixed_Income"}
SUPPORTED_SOURCES = PRICE_MONITORING_SOURCES | {"Monitoring_Feature04"}
MAX_REQUEST_BYTES = 16_384
MAX_TELEGRAM_TEXT = 4_000
JAKARTA_TZ = ZoneInfo("Asia/Jakarta")
EXECUTION_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,200}$")
STATUS_PRIORITY = {
    "FAILED": 5,
    "NEEDS_REVIEW": 4,
    "PARTIAL": 3,
    "SKIPPED": 2,
    "SUCCESS": 1,
}
STATUS_EMOJI = {
    "SUCCESS": "✅",
    "PARTIAL": "⚠️",
    "FAILED": "❌",
    "NEEDS_REVIEW": "❌",
    "SKIPPED": "⏭️",
}


@dataclass(frozen=True)
class MonitoringSummary:
    execution_id: str
    exchange: str
    run_type: str
    trigger_source: str
    update_for_date: date
    expected_symbols: int
    queried_symbols: int
    updated_symbols: int
    missing_symbols: int
    missing_tickers: tuple[str, ...]
    status: str
    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    last_error: str | None


@dataclass(frozen=True)
class Feature04Summary:
    execution_id: str
    delivery_key: str
    market_key: str
    run_type: str
    trigger_source: str
    update_for_date: date | None
    eligible_tickers: int
    completed_tickers: int
    failed_tickers: int
    blocked_tickers: int
    failed_details: tuple[str, ...]
    status: str
    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    last_error: str | None
    retry_ack_message_id: int | None = None


def env_flag(name: str, default: bool = True) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def aggregate_status(statuses: list[str]) -> str:
    if not statuses:
        return "FAILED"
    return max(statuses, key=lambda item: STATUS_PRIORITY.get(item, 99))


def fetch_monitoring_summary(
    connection: psycopg.Connection, execution_id: str
) -> MonitoringSummary | None:
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT exchange, run_type, trigger_source, update_for_date,
                   expected_symbols, queried_symbols, updated_symbols,
                   missing_symbols, missing_symbol_list, status,
                   run_time, finished_at, last_error
            FROM {MONITORING_TABLE}
            WHERE execution_id = %s
            ORDER BY exchange, asset_type, timeframe
            """,
            (execution_id,),
        )
        rows = cursor.fetchall()

    if not rows:
        return None

    missing_tickers = sorted(
        {
            str(ticker).strip().upper()
            for row in rows
            for ticker in (row[8] or [])
            if str(ticker).strip()
        }
    )
    started_at = min(row[10] for row in rows if row[10] is not None)
    finished_at = max((row[11] or datetime.now(timezone.utc)) for row in rows)
    errors = [str(row[12]).strip() for row in rows if row[12]]

    return MonitoringSummary(
        execution_id=execution_id,
        exchange="/".join(sorted({str(row[0]) for row in rows})),
        run_type=str(rows[0][1]),
        trigger_source=str(rows[0][2]),
        update_for_date=rows[0][3],
        expected_symbols=sum(int(row[4]) for row in rows),
        queried_symbols=sum(int(row[5]) for row in rows),
        updated_symbols=sum(int(row[6]) for row in rows),
        missing_symbols=sum(int(row[7]) for row in rows),
        missing_tickers=tuple(missing_tickers),
        status=aggregate_status([str(row[9]) for row in rows]),
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=max(0.0, (finished_at - started_at).total_seconds()),
        last_error=errors[0] if errors else None,
    )


def fetch_fixed_income_summary(
    connection: psycopg.Connection, execution_id: str
) -> MonitoringSummary | None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT run_type,trigger_source,target_date,expected_series,queried_series,
                   updated_series,missing_series,missing_series_list,status,
                   started_at,finished_at,last_error,market_code
            FROM public."Monitoring_Fixed_Income" WHERE execution_id=%s::uuid
            """,
            (execution_id,),
        )
        row = cursor.fetchone()
    if row is None:
        return None
    missing = tuple(sorted(
        f"{item.get('ticker', '?')}/{item.get('metric_type', '?')}"
        for item in (row[7] or []) if isinstance(item, dict)
    ))
    return MonitoringSummary(
        execution_id=execution_id,
        exchange=f"FIXED INCOME/{row[12] or 'LEGACY'}",
        run_type=str(row[0]),
        trigger_source=str(row[1]), update_for_date=row[2], expected_symbols=int(row[3]),
        queried_symbols=int(row[4]), updated_symbols=int(row[5]), missing_symbols=int(row[6]),
        missing_tickers=missing, status=str(row[8]), started_at=row[9], finished_at=row[10],
        duration_seconds=max(0.0, (row[10] - row[9]).total_seconds()), last_error=row[11],
    )


def fetch_feature04_summary(
    connection: psycopg.Connection, execution_id: str
) -> Feature04Summary | None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT run_type,trigger_source,update_for_date,eligible_tickers,completed_tickers,
                   failed_tickers,blocked_tickers,status,started_at,finished_at,last_error,
                   source_monitor_table,source_execution_id
            FROM public."Monitoring_Feature04" WHERE execution_id=%s
            """,
            (execution_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        cursor.execute(
            """SELECT acknowledgement_message_id
               FROM public."Feature04_Retry_Request" WHERE child_execution_id=%s""",
            (execution_id,),
        )
        retry = cursor.fetchone()
        retry_ack = int(retry[0]) if retry and retry[0] is not None else None

        market_key = "ADHOC"
        if row[11] == "Monitoring_Fixed_Income" and row[12]:
            cursor.execute(
                """SELECT market_code FROM public."Monitoring_Fixed_Income"
                   WHERE execution_id=%s::uuid""",
                (row[12],),
            )
            market = cursor.fetchone()
            market_key = f"{market[0]}_BONDS" if market and market[0] else "BONDS"
        else:
            cursor.execute(
                """SELECT array_agg(DISTINCT asset_type ORDER BY asset_type)
                   FROM public."Monitoring_Feature04_Ticker" WHERE execution_id=%s""",
                (execution_id,),
            )
            asset_types = (cursor.fetchone() or [None])[0] or []
            market_key = "IDX_EQUITY" if asset_types == ["equity"] else (
                "BONDS" if asset_types == ["bonds"] else "ADHOC"
            )

        aggregate = row[1] == "SCHEDULED" and row[2] is not None and market_key != "ADHOC"
        if aggregate:
            if row[11] == "Monitoring_Fixed_Income":
                cursor.execute(
                    """
                    SELECT m.execution_id,m.run_type,m.status,m.started_at,m.finished_at,m.last_error
                    FROM public."Monitoring_Feature04" m
                    JOIN public."Monitoring_Fixed_Income" f
                      ON m.source_monitor_table='Monitoring_Fixed_Income'
                     AND m.source_execution_id=f.execution_id::text
                    WHERE m.trigger_source='SCHEDULED' AND m.update_for_date=%s
                      AND f.market_code=%s
                      AND m.status IN ('SUCCESS','PARTIAL','FAILED','SKIPPED','NEEDS_REVIEW')
                    """,
                    (row[2], market_key.removesuffix("_BONDS")),
                )
            else:
                cursor.execute(
                    """
                    SELECT m.execution_id,m.run_type,m.status,m.started_at,m.finished_at,m.last_error
                    FROM public."Monitoring_Feature04" m
                    WHERE m.trigger_source='SCHEDULED' AND m.update_for_date=%s
                      AND m.source_monitor_table='Monitoring_Price_ALL'
                      AND m.status IN ('SUCCESS','PARTIAL','FAILED','SKIPPED','NEEDS_REVIEW')
                    """,
                    (row[2],),
                )
            executions = cursor.fetchall()
        else:
            executions = [(execution_id,row[0],row[7],row[8],row[9],row[10])]

        execution_ids = [item[0] for item in executions]
        cursor.execute(
            """
            SELECT execution_id,asset_type,ticker,requested_columns,status,last_error_code,
                   required_generation,updated_at
            FROM public."Monitoring_Feature04_Ticker"
            WHERE execution_id=ANY(%s)
            ORDER BY asset_type,ticker,required_generation DESC,updated_at DESC
            """,
            (execution_ids,),
        )
        latest: dict[tuple[str, str], tuple] = {}
        for member in cursor.fetchall():
            latest.setdefault((str(member[1]), str(member[2])), member)

    statuses = [str(member[4]) for member in latest.values()]
    completed = sum(status == "SUCCESS" for status in statuses)
    failed = sum(status == "FAILED" for status in statuses)
    blocked = sum(status == "BLOCKED" for status in statuses)
    if latest:
        status = "SUCCESS" if failed + blocked == 0 else ("PARTIAL" if completed else "FAILED")
    else:
        status = aggregate_status([str(item[2]) for item in executions])
    failures = tuple(
        f"{member[1]}/{member[2]}"
        + (f" [{','.join(member[3])}]" if member[3] else "")
        + (f" ({member[5]})" if member[5] else "")
        for member in latest.values() if member[4] in ("FAILED", "BLOCKED")
    )
    started = min(item[3] for item in executions if item[3] is not None)
    finished = max((item[4] or datetime.now(timezone.utc)) for item in executions)
    run_types = [name for name in ("DAILY", "RECOVERY", "RETRY_TICKER", "RETRY_COLUMN", "ADHOC", "RECONCILIATION")
                 if any(str(item[1]) == name for item in executions)]
    delivery_key = (
        f"scheduled:{market_key}:{row[2].isoformat()}" if aggregate else execution_id
    )
    return Feature04Summary(
        execution_id=execution_id, delivery_key=delivery_key, market_key=market_key,
        run_type="+".join(run_types) or str(row[0]), trigger_source=str(row[1]),
        update_for_date=row[2], eligible_tickers=len(latest), completed_tickers=completed,
        failed_tickers=failed, blocked_tickers=blocked, failed_details=failures,
        status=status, started_at=started, finished_at=finished,
        duration_seconds=max(0.0, (finished-started).total_seconds()),
        last_error=next((str(item[5]) for item in executions if item[5]), None),
        retry_ack_message_id=retry_ack,
    )


def format_duration(seconds: float) -> str:
    total = max(0, round(seconds))
    minutes, remainder = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{remainder:02d}s"
    if minutes:
        return f"{minutes}m{remainder:02d}s"
    return f"{remainder}s"


def format_header(summary: MonitoringSummary) -> str:
    emoji = STATUS_EMOJI.get(summary.status, "ℹ️")
    source = summary.run_type
    if summary.trigger_source == "MANUAL":
        source += " MANUAL"
    date_text = summary.update_for_date.strftime("%d %b %Y")
    duration = format_duration(summary.duration_seconds)

    if summary.run_type == "RECOVERY":
        denominator = summary.queried_symbols
        progress = f"{summary.updated_symbols}/{denominator} recovered"
        missing = f"{summary.missing_symbols} still missing"
    else:
        progress = f"{summary.updated_symbols}/{summary.expected_symbols} updated"
        missing = f"{summary.missing_symbols} missing"

    header = (
        f"{emoji} {summary.exchange} {source} {summary.status} • {date_text} • "
        f"{progress} • {missing} • {duration}"
    )
    if summary.status == "SKIPPED" and summary.last_error:
        reason = summary.last_error.split(":", 1)[-1].strip()
        header += f" • {reason[:180]}"
    return header


def format_timing(summary: MonitoringSummary) -> str:
    started = summary.started_at.astimezone(JAKARTA_TZ).strftime("%d %b %Y %H:%M")
    finished = summary.finished_at.astimezone(JAKARTA_TZ).strftime("%d %b %Y %H:%M")
    return f"Triggered at: {started} WIB • Finished at: {finished} WIB"


def build_messages(
    summary: MonitoringSummary, max_length: int = MAX_TELEGRAM_TEXT
) -> list[str]:
    header = format_header(summary)
    header_with_timing = header + "\n\n" + format_timing(summary)
    if not summary.missing_tickers:
        return [header_with_timing]

    prefixes = ["Missing: ", "Missing (cont.): "]
    messages: list[str] = []
    remaining = list(summary.missing_tickers)
    first = True
    while remaining:
        prefix = prefixes[0] if first else prefixes[1]
        base = header_with_timing + "\n\n" + prefix if first else prefix
        included: list[str] = []
        while remaining:
            candidate = ", ".join(included + [remaining[0]])
            if len(base) + len(candidate) > max_length and included:
                break
            if len(base) + len(candidate) > max_length:
                candidate = remaining[0][: max(1, max_length - len(base))]
                included.append(candidate)
                remaining.pop(0)
                break
            included.append(remaining.pop(0))
        messages.append(base + ", ".join(included))
        first = False
    return messages


def build_feature04_messages(
    summary: Feature04Summary, max_length: int = MAX_TELEGRAM_TEXT
) -> list[str]:
    emoji = STATUS_EMOJI.get(summary.status, "ℹ️")
    date_text = summary.update_for_date.strftime("%d %b %Y") if summary.update_for_date else "ad hoc"
    header = (
        f"{emoji} Feature04 {summary.market_key} {summary.run_type} {summary.status} • {date_text} • FINAL\n"
        f"Eligible: {summary.eligible_tickers} • Success: {summary.completed_tickers} • "
        f"Failed: {summary.failed_tickers} • Blocked: {summary.blocked_tickers} • "
        f"{format_duration(summary.duration_seconds)}"
    )
    timing = (
        f"Triggered at: {summary.started_at.astimezone(JAKARTA_TZ).strftime('%d %b %Y %H:%M')} WIB • "
        f"Finished at: {summary.finished_at.astimezone(JAKARTA_TZ).strftime('%d %b %Y %H:%M')} WIB"
    )
    base = header + "\n\n" + timing
    if summary.failed_details:
        shown = list(summary.failed_details[:10])
        suffix = f"\n…and {len(summary.failed_details)-10} more" if len(summary.failed_details) > 10 else ""
        base += "\n\nFailed:\n" + "\n".join(f"• {item}" for item in shown) + suffix
    return [base[:max_length]]


def feature04_markup(summary: Feature04Summary) -> dict | None:
    if summary.failed_tickers + summary.blocked_tickers == 0:
        return None
    return {"inline_keyboard": [[{
        "text": "📊 View / Retry failures", "callback_data": "f04:status"
    }]]}


def send_telegram_message(
    token: str,
    chat_id: str,
    text: str,
    reply_markup: dict | None = None,
    *,
    opener=urlopen,
) -> int:
    body = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if reply_markup is not None:
        body["reply_markup"] = reply_markup
    payload = json.dumps(body).encode("utf-8")
    request = Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with opener(request, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Telegram HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Telegram connection failed: {exc}") from exc
    if not result.get("ok"):
        raise RuntimeError(f"Telegram rejected message: {result}")
    return int(result["result"]["message_id"])


def edit_telegram_message(
    token: str, chat_id: str, message_id: int, text: str,
    reply_markup: dict | None = None, *, opener=urlopen,
) -> int:
    body = {
        "chat_id": chat_id, "message_id": message_id, "text": text,
        "disable_web_page_preview": True,
    }
    if reply_markup is not None:
        body["reply_markup"] = reply_markup
    request = Request(
        f"https://api.telegram.org/bot{token}/editMessageText",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with opener(request, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Telegram HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Telegram connection failed: {exc}") from exc
    if not result.get("ok"):
        raise RuntimeError(f"Telegram rejected edit: {result}")
    return int(result["result"]["message_id"])


def claim_delivery(
    connection: psycopg.Connection, source_table: str, execution_id: str
) -> tuple[str, int]:
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            INSERT INTO {LOG_TABLE} (
                source_table, source_execution_id, notification_type,
                send_status, attempt_count, updated_at
            )
            VALUES (%s, %s, 'COMPLETED', 'SENDING', 1, CURRENT_TIMESTAMP)
            ON CONFLICT (source_table, source_execution_id, notification_type)
            DO NOTHING
            RETURNING id
            """,
            (source_table, execution_id),
        )
        inserted = cursor.fetchone()
        if inserted:
            connection.commit()
            return "claimed", int(inserted[0])

        cursor.execute(
            f"""
            SELECT id, send_status,
                   updated_at > CURRENT_TIMESTAMP - INTERVAL '10 minutes' AS is_fresh
            FROM {LOG_TABLE}
            WHERE source_table = %s
              AND source_execution_id = %s
              AND notification_type = 'COMPLETED'
            FOR UPDATE
            """,
            (source_table, execution_id),
        )
        log_id, status, is_fresh = cursor.fetchone()
        if status == "SENT":
            connection.commit()
            return "duplicate", int(log_id)
        if status == "SENDING" and is_fresh:
            connection.commit()
            return "in_progress", int(log_id)
        cursor.execute(
            f"""
            UPDATE {LOG_TABLE}
            SET send_status = 'SENDING',
                attempt_count = attempt_count + 1,
                last_error = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (log_id,),
        )
        connection.commit()
        return "claimed", int(log_id)


def claim_feature04_delivery(
    connection: psycopg.Connection, delivery_key: str
) -> tuple[str, int, int | None]:
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            INSERT INTO {LOG_TABLE}(
                source_table,source_execution_id,notification_type,
                send_status,attempt_count,updated_at
            ) VALUES('Monitoring_Feature04',%s,'COMPLETED','SENDING',1,CURRENT_TIMESTAMP)
            ON CONFLICT(source_table,source_execution_id,notification_type) DO NOTHING
            RETURNING id
            """,
            (delivery_key,),
        )
        inserted = cursor.fetchone()
        if inserted:
            connection.commit()
            return "send", int(inserted[0]), None
        cursor.execute(
            f"""
            SELECT id,send_status,telegram_message_ids,
                   updated_at>CURRENT_TIMESTAMP-INTERVAL '10 minutes' AS is_fresh
            FROM {LOG_TABLE}
            WHERE source_table='Monitoring_Feature04' AND source_execution_id=%s
              AND notification_type='COMPLETED' FOR UPDATE
            """,
            (delivery_key,),
        )
        log_id,status,message_ids,is_fresh = cursor.fetchone()
        if status == "SENDING" and is_fresh:
            connection.commit()
            return "in_progress",int(log_id),None
        target = int(message_ids[-1]) if message_ids else None
        cursor.execute(
            f"""UPDATE {LOG_TABLE} SET send_status='SENDING',attempt_count=attempt_count+1,
                last_error=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=%s""",
            (log_id,),
        )
        connection.commit()
        return ("edit" if target is not None else "send"),int(log_id),target


def mark_sent(
    connection: psycopg.Connection, log_id: int, message_ids: list[int]
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            UPDATE {LOG_TABLE}
            SET send_status = 'SENT', telegram_message_ids = %s,
                sent_at = CURRENT_TIMESTAMP, last_error = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (Jsonb(message_ids), log_id),
        )
    connection.commit()


def mark_failed(connection: psycopg.Connection, log_id: int, error: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            UPDATE {LOG_TABLE}
            SET send_status = 'FAILED', last_error = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (error[:4000], log_id),
        )
    connection.commit()


class TelegramMonitor:
    def __init__(
        self,
        database_url: str,
        token: str,
        chat_id: str,
        send_message: Callable[..., int] = send_telegram_message,
        edit_message: Callable[..., int] = edit_telegram_message,
    ) -> None:
        self.database_url = database_url
        self.token = token
        self.chat_id = chat_id
        self.send_message = send_message
        self.edit_message = edit_message

    def notify(self, source_table: str, execution_id: str) -> tuple[str, int]:
        if source_table not in SUPPORTED_SOURCES:
            raise ValueError("unsupported source_table")
        if not EXECUTION_ID_PATTERN.fullmatch(execution_id):
            raise ValueError("invalid execution_id")

        with psycopg.connect(self.database_url) as connection:
            if source_table == "Monitoring_Price_ALL":
                summary = fetch_monitoring_summary(connection, execution_id)
            elif source_table == "Monitoring_Fixed_Income":
                summary = fetch_fixed_income_summary(connection, execution_id)
            else:
                summary = fetch_feature04_summary(connection, execution_id)
            if summary is None:
                raise KeyError("execution_id not found")
            if isinstance(summary, Feature04Summary):
                state, log_id, edit_target = claim_feature04_delivery(
                    connection, summary.delivery_key
                )
                if state == "in_progress":
                    return state, log_id
                if summary.retry_ack_message_id is not None:
                    edit_target = summary.retry_ack_message_id or None
                    state = "edit" if edit_target is not None else "send"
            else:
                state, log_id = claim_delivery(connection, source_table, execution_id)
                edit_target = None
            if state not in ("claimed", "send", "edit"):
                if state == "duplicate" and source_table in PRICE_MONITORING_SOURCES:
                    connection.execute(
                        """UPDATE public."Monitoring_Feature04"
                           SET price_notification_sent_at=coalesce(price_notification_sent_at,CURRENT_TIMESTAMP),
                               updated_at=CURRENT_TIMESTAMP
                           WHERE source_monitor_table=%s AND source_execution_id=%s""",
                        (source_table, execution_id),
                    )
                    connection.commit()
                return state, log_id

            message_ids: list[int] = []
            try:
                if (summary.status != "SUCCESS" or env_flag("TELEGRAM_NOTIFY_SUCCESS")
                        or (isinstance(summary, Feature04Summary) and state == "edit")):
                    if isinstance(summary, Feature04Summary):
                        message = build_feature04_messages(summary)[0]
                        markup = feature04_markup(summary)
                        if state == "edit" and edit_target is not None:
                            message_ids.append(self.edit_message(
                                self.token,self.chat_id,edit_target,message,markup
                            ))
                        else:
                            message_ids.append(self.send_message(
                                self.token,self.chat_id,message,markup
                            ))
                    else:
                        for message in build_messages(summary):
                            message_ids.append(
                                self.send_message(self.token, self.chat_id, message)
                            )
                mark_sent(connection, log_id, message_ids)
                if source_table in PRICE_MONITORING_SOURCES:
                    connection.execute(
                        """UPDATE public."Monitoring_Feature04"
                           SET price_notification_sent_at=coalesce(price_notification_sent_at,CURRENT_TIMESTAMP),
                               updated_at=CURRENT_TIMESTAMP
                           WHERE source_monitor_table=%s AND source_execution_id=%s""",
                        (source_table, execution_id),
                    )
                    connection.commit()
                return ("edited" if state == "edit" else "sent"), log_id
            except Exception as exc:
                mark_failed(connection, log_id, f"{type(exc).__name__}: {exc}")
                raise


class Handler(BaseHTTPRequestHandler):
    server_version = "SanitiTelegramMonitor/1.0"

    def log_message(self, format: str, *args) -> None:
        print(json.dumps({"event": "http", "message": format % args}), flush=True)

    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_json(200, {"status": "ok"})
        else:
            self.send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        if self.path != "/notify":
            self.send_json(404, {"error": "not_found"})
            return
        expected_secret = self.server.notify_secret
        supplied_secret = self.headers.get("X-Notify-Secret", "")
        if not supplied_secret or not hmac.compare_digest(supplied_secret, expected_secret):
            self.send_json(401, {"error": "unauthorized"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_REQUEST_BYTES:
                raise ValueError("invalid request size")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            state, log_id = self.server.monitor.notify(
                str(payload.get("source_table", "")),
                str(payload.get("execution_id", "")),
            )
            code = 202 if state == "in_progress" else 200
            self.send_json(code, {"status": state, "log_id": log_id})
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)})
        except KeyError as exc:
            self.send_json(404, {"error": str(exc)})
        except Exception as exc:
            print(
                json.dumps(
                    {"event": "notification_failed", "error": f"{type(exc).__name__}: {exc}"}
                ),
                flush=True,
            )
            self.send_json(500, {"error": "notification_failed"})


class RailwayPrivateHTTPServer(ThreadingHTTPServer):
    """Listen on Railway private IPv6 networking, with IPv4 compatibility."""

    address_family = socket.AF_INET6

    def server_bind(self) -> None:
        try:
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        except OSError:
            pass
        super().server_bind()


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"{name} is required")
    return value


def main() -> None:
    monitor = TelegramMonitor(
        required_env("DATABASE_URL"),
        required_env("TELEGRAM_BOT_TOKEN"),
        required_env("TELEGRAM_CHAT_ID"),
    )
    server = RailwayPrivateHTTPServer(("::", int(os.environ.get("PORT", "8080"))), Handler)
    server.monitor = monitor
    server.notify_secret = required_env("TELEGRAM_NOTIFY_SECRET")
    print(json.dumps({"event": "server_started", "port": server.server_port}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
