"""EXEC-M334-ALERT (user go 2026-11-02: "OK A, Jalankan"; ERRORS M334): a Telegram alarm for an audit archive queue that
keeps failing. The same file is in market-audit-store, market-python-sandbox and market-sql-governor (app/queue_alarm.py;
each service's tests check that the three copies are identical).

M334: market-audit-store failed every bucket write for five days (credentials of an older deploy) and every queue only
logged it; nobody knew until the sandbox, retrying, could no longer sleep. A queue that cannot deliver must say so.

The queue owner calls observe() after each drain pass with what its own store says:
- oldest: when the oldest item still waiting was queued (None when none waits);
- waiting: how many items wait (None when the queue itself could not be read);
- gave_up: items that stopped retrying in this pass (their archive is lost);
- recovered_minutes: how long the oldest item archived in this pass had waited (None when none was archived);
- error: the class of the last failure.
Rules, with the limit AUDIT_QUEUE_ALARM_MINUTES (default 60, the user's 1 hour):
- stuck: the oldest item has waited longer than the limit;
- gave_up: an item stopped retrying;
- recovered: an item that had waited longer than the limit is archived and none waits longer than the limit any more.
Each is one Telegram message per service per UTC day: telegram-monitor keeps an execution_id to one message
(Telegram_Notification_Log), and this process remembers what it sent, so a stuck queue costs one POST a day, not one per
pass. A healthy queue sends nothing, so a service that may sleep stays quiet. A failed POST is logged and tried on the
next pass; the queue's own work never waits on it longer than the POST timeout."""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from datetime import datetime, timezone
from typing import Callable

logger = logging.getLogger("audit_queue_alarm")
SOURCE = "Audit_Queue_Health"
SERVICES = ("audit-store", "sandbox", "sql-governor")
ERROR_CLASS = re.compile(r"[A-Za-z_][A-Za-z0-9_.]{0,80}")
TIMEOUT_SECONDS = 10


def error_class(text: object) -> str | None:
    """'ClientError: An error occurred (403) ...' -> 'ClientError'; anything that is not a class name -> 'Error'."""
    if not text:
        return None
    head = str(text).split(":", 1)[0].split(" ", 1)[0].strip()
    return head if ERROR_CLASS.fullmatch(head) else "Error"


def _minutes(since: datetime, now: datetime) -> int:
    return max(0, int((now - since).total_seconds() // 60))


def _post(url: str, secret: str, payload: dict) -> str:
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "X-Notify-Secret": secret})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return str(json.loads(response.read() or b"{}").get("status"))


class QueueAlarm:
    def __init__(self, service: str, url: str | None, secret: str | None, *, limit_minutes: int = 60,
                 post: Callable[[str, str, dict], str] = _post,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> None:
        if service not in SERVICES:
            raise ValueError(f"unknown audit queue {service!r}")
        self.service, self.url, self.secret = service, (url or "").strip(), (secret or "").strip()
        self.limit, self.post, self.now = limit_minutes, post, now
        self.sent: set[str] = set()

    @classmethod
    def from_env(cls, service: str, env: dict | None = None) -> "QueueAlarm":
        env = os.environ if env is None else env
        raw = str(env.get("AUDIT_QUEUE_ALARM_MINUTES") or "60").strip()
        limit = int(raw) if raw.isdigit() and 5 <= int(raw) <= 10_080 else 60
        return cls(service, env.get("TELEGRAM_NOTIFY_URL"), env.get("TELEGRAM_NOTIFY_SECRET"), limit_minutes=limit)

    def observe(self, *, oldest: datetime | None, waiting: int | None, gave_up: int = 0,
                recovered_minutes: int | None = None, error: str | None = None) -> list[str]:
        """The alarms this pass raised (sent or not); never raises."""
        now = self.now()
        oldest_minutes = _minutes(oldest, now) if oldest is not None else None
        stuck = oldest_minutes is not None and oldest_minutes >= self.limit
        raised = []
        if stuck:
            raised.append(self._raise("stuck", now, waiting, oldest_minutes, 0, error))
        if gave_up > 0:
            raised.append(self._raise("gave_up", now, waiting, oldest_minutes, gave_up, error))
        if recovered_minutes is not None and recovered_minutes >= self.limit and not stuck:
            raised.append(self._raise("recovered", now, waiting, oldest_minutes, 0, None))
        return raised

    def _raise(self, status: str, now: datetime, waiting: int | None, oldest_minutes: int | None, gave_up: int,
               error: str | None) -> str:
        execution_id = f"audit-queue-{self.service}-{status.replace('_', '')}-{now:%Y-%m-%d}"
        if execution_id in self.sent:
            return status
        fields = {"service": self.service, "status": status, "execution_id": execution_id, "waiting": waiting,
                  "oldest_minutes": oldest_minutes, "gave_up": gave_up, "error": error_class(error),
                  "limit_minutes": self.limit}
        if not self.url or not self.secret:
            logger.warning(json.dumps({"event": "audit_queue_alarm_not_configured", **fields}))
            self.sent.add(execution_id)                # logged once a day; nothing to send it with
            return status
        details = {"service": self.service, "status": status, "waiting": waiting, "oldest_minutes": oldest_minutes,
                   "gave_up": gave_up, "error": fields["error"], "limit_minutes": self.limit}
        try:
            answer = self.post(self.url, self.secret, {"source_table": SOURCE, "execution_id": execution_id,
                                                       "details": details})
        except Exception as exc:  # noqa: BLE001 - the URL and secret are never printed; tried on the next pass
            logger.warning(json.dumps({"event": "audit_queue_alarm_failed", **fields, "post_error": type(exc).__name__}))
            return status
        self.sent.add(execution_id)
        logger.warning(json.dumps({"event": "audit_queue_alarm", **fields, "answer": answer}))
        return status


if not logger.hasHandlers():                            # the rule of edge-bff app/wake.py: a line nobody prints is lost
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
