"""G22-5 (PLAN_FINAL_2026-10-04.md Fase 5): a conversation save that fails on the database is tried once more; a lost
lease is never retried. Without a database (the Postgres-backed behaviour is in test_conversations.py)."""
from __future__ import annotations

import types

import psycopg

from app.conversations import ConversationStore


def store(outcomes):
    s = ConversationStore("postgresql://unused", retention_days=1, lease_seconds=60, save_retry_seconds=0.0)
    calls = []

    def once(start, request_id, result, *, retry):
        calls.append(retry)
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
    s._finish_once = once
    return s, calls


def test_a_database_failure_is_tried_once_more() -> None:
    s, calls = store([psycopg.OperationalError("busy"), True])
    assert s.finish(types.SimpleNamespace(conversation_id="c1"), "r1", object()) is True and calls == [False, True]


def test_two_failures_report_not_saved() -> None:
    s, calls = store([psycopg.OperationalError("busy"), psycopg.OperationalError("busy")])
    assert s.finish(types.SimpleNamespace(conversation_id="c1"), "r1", object()) is False and calls == [False, True]


def test_a_lost_lease_is_not_retried() -> None:
    s, calls = store([False])
    assert s.finish(types.SimpleNamespace(conversation_id="c1"), "r1", object()) is False and calls == [False]
