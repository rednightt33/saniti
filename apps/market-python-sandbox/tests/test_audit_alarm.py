"""EXEC-M334-ALERT (user go 2026-11-02: "OK A, Jalankan"; ERRORS M334): the sandbox audit outbox tells its alarm what
the SQLite queue holds after each pass (app/queue_alarm.py has the rules). No analysis process is started here."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.audit import AuditOutbox
from app.audit_client import AuditUnavailable
from app.queue_alarm import QueueAlarm


class Client:
    def __init__(self) -> None:
        self.down = True

    def register_run(self, request_id):
        if self.down:
            raise AuditUnavailable("upload HTTP 403")
        return "run_" + "1" * 32

    def expect(self, run_id, expected):
        return None

    def append_events(self, run_id, events):
        return None


def outbox(tmp_path, posted, attempts=5):
    settings = SimpleNamespace(data_dir=str(tmp_path), audit_store_url="http://audit", audit_store_key="k" * 40,
                               audit_timeout_seconds=5, audit_spool_max_bytes=10_000_000, audit_max_attempts=attempts,
                               audit_poll_seconds=1)
    box = AuditOutbox(settings, client=Client())
    box.alarm = QueueAlarm("sandbox", "http://monitor/notify", "s" * 32, post=lambda u, s, p: posted.append(p) or "sent")
    return box


def queue(box, key, *, hours_ago):
    created = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    payload = {"output_sha256": [], "completion_id": key, "status": "COMPLETE"}
    box._db.execute("""INSERT INTO items (idempotency_key, kind, request_id, payload, files, created_at)
                       VALUES (?, 'COMPLETION', 'req-1', ?, '[]', ?)""", (key, json.dumps(payload), created))


def due(box):
    box._db.execute("UPDATE items SET next_attempt_at = 0")


def test_a_stuck_item_alarms_once_and_the_recovery_is_reported(tmp_path):
    posted = []
    box = outbox(tmp_path, posted)
    queue(box, "c1", hours_ago=2)
    box.drain()
    due(box)
    box.drain()                                          # still stuck: no second message
    assert [p["details"]["status"] for p in posted] == ["stuck"]
    assert posted[0]["details"]["error"] == "AuditUnavailable" and posted[0]["details"]["waiting"] == 1
    box.client.down = False
    due(box)
    assert box.drain()["complete"] == 1
    assert [p["details"]["status"] for p in posted] == ["stuck", "recovered"]


def test_an_item_that_stops_retrying_is_reported(tmp_path):
    posted = []
    box = outbox(tmp_path, posted, attempts=1)
    queue(box, "c1", hours_ago=0)
    assert box.drain()["incomplete"] == 1
    assert [(p["details"]["status"], p["details"]["gave_up"]) for p in posted] == [("gave_up", 1)]


def test_a_healthy_queue_sends_nothing(tmp_path):
    posted = []
    box = outbox(tmp_path, posted)
    box.client.down = False
    queue(box, "c1", hours_ago=0)
    assert box.drain()["complete"] == 1
    assert posted == []
