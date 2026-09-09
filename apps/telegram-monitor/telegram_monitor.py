#!/usr/bin/env python3
"""Event-driven Telegram notifications for completed Railway data jobs."""

from __future__ import annotations

import hmac
import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import psycopg
from psycopg.types.json import Jsonb


MONITORING_TABLE = 'public."Monitoring_Price_ALL"'
LOG_TABLE = 'public."Telegram_Notification_Log"'
SUPPORTED_SOURCE = "Monitoring_Price_ALL"
MAX_REQUEST_BYTES = 16_384
MAX_TELEGRAM_TEXT = 4_000
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
    duration_seconds: float
    last_error: str | None


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
        duration_seconds=max(0.0, (finished_at - started_at).total_seconds()),
        last_error=errors[0] if errors else None,
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


def build_messages(
    summary: MonitoringSummary, max_length: int = MAX_TELEGRAM_TEXT
) -> list[str]:
    header = format_header(summary)
    if not summary.missing_tickers:
        return [header]

    prefixes = ["Missing: ", "Missing (cont.): "]
    messages: list[str] = []
    remaining = list(summary.missing_tickers)
    first = True
    while remaining:
        prefix = prefixes[0] if first else prefixes[1]
        base = header + "\n" + prefix if first else prefix
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


def send_telegram_message(
    token: str,
    chat_id: str,
    text: str,
    *,
    opener=urlopen,
) -> int:
    payload = json.dumps(
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
    ).encode("utf-8")
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
        send_message: Callable[[str, str, str], int] = send_telegram_message,
    ) -> None:
        self.database_url = database_url
        self.token = token
        self.chat_id = chat_id
        self.send_message = send_message

    def notify(self, source_table: str, execution_id: str) -> tuple[str, int]:
        if source_table != SUPPORTED_SOURCE:
            raise ValueError("unsupported source_table")
        if not EXECUTION_ID_PATTERN.fullmatch(execution_id):
            raise ValueError("invalid execution_id")

        with psycopg.connect(self.database_url) as connection:
            summary = fetch_monitoring_summary(connection, execution_id)
            if summary is None:
                raise KeyError("execution_id not found")
            state, log_id = claim_delivery(connection, source_table, execution_id)
            if state != "claimed":
                return state, log_id

            message_ids: list[int] = []
            try:
                if summary.status != "SUCCESS" or env_flag("TELEGRAM_NOTIFY_SUCCESS"):
                    for message in build_messages(summary):
                        message_ids.append(
                            self.send_message(self.token, self.chat_id, message)
                        )
                mark_sent(connection, log_id, message_ids)
                return "sent", log_id
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
    server = ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8080"))), Handler)
    server.monitor = monitor
    server.notify_secret = required_env("TELEGRAM_NOTIFY_SECRET")
    print(json.dumps({"event": "server_started", "port": server.server_port}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
