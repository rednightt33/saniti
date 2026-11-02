"""EXEC-M334-ALERT (user go 2026-11-02: "OK A, Jalankan"; ERRORS M334): the audit queue alarm (app/queue_alarm.py).
The same test file is in market-audit-store, market-python-sandbox and market-sql-governor."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.queue_alarm import QueueAlarm, error_class

NOW = datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc)


def alarm(posted, *, url="http://telegram-monitor.railway.internal:8080/notify", secret="s" * 32, fail=False,
          service="audit-store"):
    def post(u, s, payload):
        if fail:
            raise OSError("refused")
        posted.append(payload)
        return "sent"
    return QueueAlarm(service, url, secret, limit_minutes=60, post=post, now=lambda: NOW)


def test_a_healthy_queue_sends_nothing():
    posted = []
    a = alarm(posted)
    assert a.observe(oldest=None, waiting=0) == []
    assert a.observe(oldest=NOW - timedelta(minutes=59), waiting=3, error="QueryCanceled") == []   # under the limit
    assert a.observe(oldest=None, waiting=0, recovered_minutes=12) == []                            # a short wait
    assert posted == []


def test_stuck_past_the_limit_is_one_message_a_day():
    posted = []
    a = alarm(posted)
    for _ in range(3):                                   # every pass sees it; one POST
        assert a.observe(oldest=NOW - timedelta(hours=121), waiting=566, error="ClientError") == ["stuck"]
    assert len(posted) == 1
    p = posted[0]
    assert p["source_table"] == "Audit_Queue_Health"
    assert p["execution_id"] == "audit-queue-audit-store-stuck-2026-11-02"
    assert p["details"] == {"service": "audit-store", "status": "stuck", "waiting": 566, "oldest_minutes": 7260,
                            "gave_up": 0, "error": "ClientError", "limit_minutes": 60}


def test_given_up_items_and_the_recovery_are_reported():
    posted = []
    a = alarm(posted, service="sandbox")
    a.observe(oldest=None, waiting=0, gave_up=2, error="AuditUnavailable")
    a.observe(oldest=None, waiting=0, recovered_minutes=95)
    assert [p["execution_id"] for p in posted] == ["audit-queue-sandbox-gaveup-2026-11-02",
                                                   "audit-queue-sandbox-recovered-2026-11-02"]
    assert posted[0]["details"]["gave_up"] == 2 and posted[1]["details"]["status"] == "recovered"


def test_no_recovery_while_another_item_is_still_stuck():
    posted = []
    a = alarm(posted)
    assert a.observe(oldest=NOW - timedelta(hours=2), waiting=5, recovered_minutes=180) == ["stuck"]
    assert [p["details"]["status"] for p in posted] == ["stuck"]


def test_a_failed_post_is_tried_again_on_the_next_pass_and_never_raises():
    posted = []
    a = alarm(posted, fail=True)
    assert a.observe(oldest=NOW - timedelta(hours=2), waiting=1) == ["stuck"]
    assert a.sent == set()
    a.post = lambda u, s, payload: posted.append(payload) or "sent"
    a.observe(oldest=NOW - timedelta(hours=2), waiting=1)
    assert len(posted) == 1


def test_without_the_telegram_variables_it_only_logs(caplog):
    posted = []
    a = alarm(posted, url="", secret="")
    assert a.observe(oldest=NOW - timedelta(hours=2), waiting=1) == ["stuck"]
    assert posted == []


def test_only_an_error_class_leaves_the_service():
    assert error_class("ClientError: An error occurred (403) when calling PutObject on bucket x") == "ClientError"
    assert error_class("QueryCanceled") == "QueryCanceled"
    assert error_class("DATASET_EXPIRED_BEFORE_ARCHIVE") == "DATASET_EXPIRED_BEFORE_ARCHIVE"
    assert error_class("(403) forbidden") == "Error"
    assert error_class(None) is None
    posted = []
    alarm(posted).observe(oldest=NOW - timedelta(hours=2), waiting=1, error="ClientError: secret https://x/y?sig=z")
    assert posted[0]["details"]["error"] == "ClientError"


def test_the_limit_comes_from_the_environment_within_bounds():
    assert QueueAlarm.from_env("audit-store", {"AUDIT_QUEUE_ALARM_MINUTES": "90"}).limit == 90
    assert QueueAlarm.from_env("audit-store", {"AUDIT_QUEUE_ALARM_MINUTES": "1"}).limit == 60      # too short
    assert QueueAlarm.from_env("audit-store", {}).limit == 60
    with pytest.raises(ValueError):
        QueueAlarm("orc", None, None)


def test_the_three_copies_are_identical():
    apps = Path(__file__).resolve().parents[2]
    copies = {name: (apps / name / "app" / "queue_alarm.py") for name in
              ("market-audit-store", "market-python-sandbox", "market-sql-governor")}
    present = {name: path.read_bytes() for name, path in copies.items() if path.is_file()}
    if len(present) < 3:
        pytest.skip("only this service's directory is present (a service build context)")
    assert len(set(present.values())) == 1, "app/queue_alarm.py differs between the audit services"
    tests = {(apps / name / "tests" / "test_queue_alarm.py").read_bytes() for name in copies}
    assert len(tests) == 1, "tests/test_queue_alarm.py differs between the audit services"
