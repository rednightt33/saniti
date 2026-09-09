#!/usr/bin/env python3
"""Receive trusted Telegram commands and invoke allowlisted Railway cron jobs."""

from __future__ import annotations

import hmac
import json
import os
import socket
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import psycopg


COMMAND_LOG_TABLE = 'public."Telegram_Command_Log"'
MAX_REQUEST_BYTES = 65_536
RAILWAY_API_URL = "https://backboard.railway.com/graphql/v2"
RAILWAY_RUN_MUTATION = """
mutation RunCronNow($input: DeploymentInstanceExecutionCreateInput!) {
  deploymentInstanceExecutionCreate(input: $input)
}
""".strip()


@dataclass(frozen=True)
class CommandSpec:
    command: str
    service_name: str
    service_instance_id: str
    label: str


@dataclass(frozen=True)
class IncomingCommand:
    update_id: int
    chat_id: str
    command: str
    callback_query_id: str | None


def normalize_command(value: str) -> str | None:
    text = value.strip().split()[0].split("@", 1)[0].lower() if value.strip() else ""
    mapping = {
        "/run_price": "RUN_PRICE",
        "/run_recovery": "RUN_RECOVERY",
        "run_price": "RUN_PRICE",
        "run_recovery": "RUN_RECOVERY",
        "RUN_PRICE": "RUN_PRICE",
        "RUN_RECOVERY": "RUN_RECOVERY",
    }
    return mapping.get(value) or mapping.get(text)


def extract_incoming_command(update: dict) -> IncomingCommand | None:
    try:
        update_id = int(update["update_id"])
    except (KeyError, TypeError, ValueError):
        return None

    callback = update.get("callback_query")
    if isinstance(callback, dict):
        message = callback.get("message") or {}
        chat = message.get("chat") or {}
        command = normalize_command(str(callback.get("data", "")))
        if command and chat.get("id") is not None:
            return IncomingCommand(
                update_id=update_id,
                chat_id=str(chat["id"]),
                command=command,
                callback_query_id=str(callback.get("id", "")) or None,
            )

    message = update.get("message")
    if isinstance(message, dict):
        chat = message.get("chat") or {}
        text = str(message.get("text", ""))
        command = normalize_command(text)
        if command and chat.get("id") is not None:
            return IncomingCommand(update_id, str(chat["id"]), command, None)
    return None


def is_start_command(update: dict) -> tuple[bool, str | None]:
    message = update.get("message")
    if not isinstance(message, dict):
        return False, None
    chat = message.get("chat") or {}
    text = str(message.get("text", "")).strip().split()[0].split("@", 1)[0].lower()
    return text == "/start", str(chat.get("id")) if chat.get("id") is not None else None


def menu_markup() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "▶️ Run IDX Price", "callback_data": "run_price"}],
            [{"text": "🛠 Run IDX Recovery", "callback_data": "run_recovery"}],
        ]
    }


def telegram_api_call(
    token: str,
    method: str,
    payload: dict,
    *,
    opener=urlopen,
) -> dict:
    request = Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=json.dumps(payload).encode("utf-8"),
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
        raise RuntimeError(f"Telegram rejected request: {result}")
    return result


def send_message(token: str, chat_id: str, text: str, reply_markup: dict | None = None) -> int:
    payload: dict = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    result = telegram_api_call(token, "sendMessage", payload)
    return int(result["result"]["message_id"])


def answer_callback(token: str, callback_query_id: str, text: str) -> None:
    telegram_api_call(
        token,
        "answerCallbackQuery",
        {"callback_query_id": callback_query_id, "text": text, "show_alert": False},
    )


def trigger_railway_run(
    project_token: str,
    service_instance_id: str,
    *,
    opener=urlopen,
    attempts: int = 3,
) -> bool:
    payload = json.dumps(
        {
            "query": RAILWAY_RUN_MUTATION,
            "variables": {"input": {"serviceInstanceId": service_instance_id}},
        }
    ).encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        request = Request(
            RAILWAY_API_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Project-Access-Token": project_token,
                "User-Agent": "Saniti-Telegram-Trigger/1.0",
            },
            method="POST",
        )
        try:
            with opener(request, timeout=20) as response:
                result = json.loads(response.read().decode("utf-8"))
            if result.get("errors"):
                raise RuntimeError(f"Railway API error: {result['errors']}")
            return bool(result.get("data", {}).get("deploymentInstanceExecutionCreate"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            if exc.code != 429 and exc.code < 500:
                raise RuntimeError(f"Railway HTTP {exc.code}: {detail}") from exc
            last_error = exc
            if attempt < attempts:
                time.sleep(attempt)
        except (URLError, TimeoutError, OSError, ValueError, RuntimeError) as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(attempt)
    raise RuntimeError(f"Railway trigger failed after {attempts} attempts: {last_error}")


def claim_command(
    database_url: str,
    incoming: IncomingCommand,
    spec: CommandSpec,
    cooldown_seconds: int,
) -> tuple[str, int]:
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (spec.service_name,))
            cursor.execute(
                f"SELECT id, status FROM {COMMAND_LOG_TABLE} WHERE telegram_update_id = %s",
                (incoming.update_id,),
            )
            existing = cursor.fetchone()
            if existing:
                connection.commit()
                return "duplicate", int(existing[0])

            cursor.execute(
                f"""
                SELECT id
                FROM {COMMAND_LOG_TABLE}
                WHERE target_service = %s
                  AND status IN ('RECEIVED', 'TRIGGERED')
                  AND requested_at > CURRENT_TIMESTAMP - (%s * INTERVAL '1 second')
                ORDER BY requested_at DESC
                LIMIT 1
                """,
                (spec.service_name, cooldown_seconds),
            )
            recent = cursor.fetchone()
            status = "BLOCKED" if recent else "RECEIVED"
            last_error = "A recent request is still inside the safety cooldown." if recent else None
            cursor.execute(
                f"""
                INSERT INTO {COMMAND_LOG_TABLE} (
                    telegram_update_id, chat_id, command, target_service,
                    status, railway_reference, last_error
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    incoming.update_id,
                    int(incoming.chat_id),
                    spec.command,
                    spec.service_name,
                    status,
                    spec.service_instance_id,
                    last_error,
                ),
            )
            command_id = int(cursor.fetchone()[0])
        connection.commit()
        return ("blocked" if recent else "claimed"), command_id


def finish_command(
    database_url: str,
    command_id: int,
    status: str,
    error: str | None = None,
) -> None:
    triggered_at = datetime.now(timezone.utc) if status == "TRIGGERED" else None
    finished_at = datetime.now(timezone.utc) if status == "FAILED" else None
    with psycopg.connect(database_url) as connection:
        connection.execute(
            f"""
            UPDATE {COMMAND_LOG_TABLE}
            SET status = %s,
                triggered_at = COALESCE(%s, triggered_at),
                finished_at = COALESCE(%s, finished_at),
                last_error = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (status, triggered_at, finished_at, error[:4000] if error else None, command_id),
        )
        connection.commit()


class TelegramTrigger:
    def __init__(
        self,
        database_url: str,
        bot_token: str,
        allowed_chat_id: str,
        project_token: str,
        commands: dict[str, CommandSpec],
        cooldown_seconds: int = 900,
        claim: Callable[[str, IncomingCommand, CommandSpec, int], tuple[str, int]] = claim_command,
        finish: Callable[[str, int, str, str | None], None] = finish_command,
        railway_trigger: Callable[[str, str], bool] = trigger_railway_run,
        messenger: Callable[[str, str, str, dict | None], int] = send_message,
        callback_answer: Callable[[str, str, str], None] = answer_callback,
    ) -> None:
        self.database_url = database_url
        self.bot_token = bot_token
        self.allowed_chat_id = allowed_chat_id
        self.project_token = project_token
        self.commands = commands
        self.cooldown_seconds = cooldown_seconds
        self.claim = claim
        self.finish = finish
        self.railway_trigger = railway_trigger
        self.messenger = messenger
        self.callback_answer = callback_answer

    def best_effort_message(
        self, chat_id: str, text: str, reply_markup: dict | None = None
    ) -> None:
        try:
            self.messenger(self.bot_token, chat_id, text, reply_markup)
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "event": "telegram_ack_failed",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                ),
                flush=True,
            )

    def best_effort_callback(self, callback_query_id: str | None, text: str) -> None:
        if not callback_query_id:
            return
        try:
            self.callback_answer(self.bot_token, callback_query_id, text)
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "event": "telegram_callback_ack_failed",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                ),
                flush=True,
            )

    def handle_update(self, update: dict) -> str:
        is_start, start_chat_id = is_start_command(update)
        if is_start:
            if start_chat_id != self.allowed_chat_id:
                return "unauthorized"
            self.messenger(
                self.bot_token,
                start_chat_id,
                "Saniti Railway controls:",
                menu_markup(),
            )
            return "menu_sent"

        incoming = extract_incoming_command(update)
        if incoming is None:
            return "ignored"
        if incoming.chat_id != self.allowed_chat_id:
            return "unauthorized"
        spec = self.commands[incoming.command]

        state, command_id = self.claim(
            self.database_url, incoming, spec, self.cooldown_seconds
        )
        if state == "duplicate":
            self.best_effort_callback(incoming.callback_query_id, "Already processed")
            return "duplicate"
        if state == "blocked":
            text = f"⚠️ {spec.label} was not started because it was triggered recently."
            self.best_effort_callback(
                incoming.callback_query_id, "Already running/recently triggered"
            )
            self.best_effort_message(incoming.chat_id, text)
            return "blocked"

        self.best_effort_callback(incoming.callback_query_id, "Starting Railway job…")
        try:
            if not self.railway_trigger(self.project_token, spec.service_instance_id):
                raise RuntimeError("Railway did not accept the Run Now request")
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            self.finish(self.database_url, command_id, "FAILED", error)
            self.best_effort_message(
                incoming.chat_id,
                f"❌ {spec.label} could not be started. Please check Railway.",
            )
            print(json.dumps({"event": "trigger_failed", "command_id": command_id, "error": error}), flush=True)
            return "failed"

        self.finish(self.database_url, command_id, "TRIGGERED", None)
        self.best_effort_message(
            incoming.chat_id,
            f"⏳ {spec.label} started from Telegram. Final result will follow.",
        )
        return "triggered"


class Handler(BaseHTTPRequestHandler):
    server_version = "SanitiTelegramTrigger/1.0"

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
        if self.path != "/telegram/webhook":
            self.send_json(404, {"error": "not_found"})
            return
        supplied = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not supplied or not hmac.compare_digest(supplied, self.server.webhook_secret):
            self.send_json(401, {"error": "unauthorized"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_REQUEST_BYTES:
                raise ValueError("invalid request size")
            update = json.loads(self.rfile.read(length).decode("utf-8"))
            result = self.server.trigger.handle_update(update)
            self.send_json(200, {"status": result})
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_json(400, {"error": str(exc)})
        except Exception as exc:
            print(json.dumps({"event": "webhook_failed", "error": f"{type(exc).__name__}: {exc}"}), flush=True)
            self.send_json(500, {"error": "webhook_failed"})


class RailwayHTTPServer(ThreadingHTTPServer):
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
    commands = {
        "RUN_PRICE": CommandSpec(
            "RUN_PRICE",
            "idx-price-cron",
            required_env("RAILWAY_DAILY_SERVICE_INSTANCE_ID"),
            "IDX DAILY",
        ),
        "RUN_RECOVERY": CommandSpec(
            "RUN_RECOVERY",
            "idx-price-recovery-cron",
            required_env("RAILWAY_RECOVERY_SERVICE_INSTANCE_ID"),
            "IDX RECOVERY",
        ),
    }
    trigger = TelegramTrigger(
        required_env("DATABASE_URL"),
        required_env("TELEGRAM_BOT_TOKEN"),
        required_env("TELEGRAM_ALLOWED_CHAT_ID"),
        required_env("RAILWAY_PROJECT_TOKEN"),
        commands,
        int(os.environ.get("COMMAND_COOLDOWN_SECONDS", "900")),
    )
    server = RailwayHTTPServer(("::", int(os.environ.get("PORT", "8080"))), Handler)
    server.trigger = trigger
    server.webhook_secret = required_env("TELEGRAM_WEBHOOK_SECRET")
    print(json.dumps({"event": "server_started", "port": server.server_port}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
