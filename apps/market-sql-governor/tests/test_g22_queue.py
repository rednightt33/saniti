"""G22 (PLAN_FINAL_2026-10-04.md Fase 5): one count timeout per data order (G22-3) and the heavy-query queue
(G22-4). In-process, without a database."""
from __future__ import annotations

import threading
import time
import types

import pytest

from app.config import Settings
from app.governor import Extractor, GovernorUnavailable
from conftest import base_env


def extractor(**env) -> Extractor:
    settings = Settings.from_env(base_env(GOVERNOR_DATABASE_URL="postgresql://x/y", **env))
    return Extractor(types.SimpleNamespace(settings=settings))


def test_a_timed_out_order_is_remembered_for_its_other_parts_only() -> None:
    ext = extractor()
    order, other = ("need_" + "a" * 24, "prices_g1"), ("need_" + "a" * 24, "flow_g2")
    assert not ext._count_timed_out(order)
    ext._note_count_timeout(order)
    assert ext._count_timed_out(order) and not ext._count_timed_out(other)


def test_the_memory_expires() -> None:
    ext = extractor(SQL_COUNT_TIMEOUT_MEMORY_SECONDS="0")
    order = ("need_" + "b" * 24, "prices_g1")
    ext._note_count_timeout(order)
    time.sleep(0.01)
    assert not ext._count_timed_out(order)


def test_no_queue_by_default() -> None:
    ext = extractor()
    assert ext._heavy is None
    with ext._heavy_slot("r"):
        pass


def test_the_queue_admits_n_and_the_next_waits_then_gets_busy() -> None:
    ext = extractor(SQL_HEAVY_QUERY_CONCURRENCY="2", SQL_HEAVY_QUERY_WAIT_SECONDS="1")
    release = threading.Event()
    entered = []

    def hold():
        with ext._heavy_slot("r"):
            entered.append(1)
            release.wait(5)

    threads = [threading.Thread(target=hold) for _ in range(2)]
    for t in threads:
        t.start()
    while len(entered) < 2:
        time.sleep(0.01)
    started = time.monotonic()
    with pytest.raises(GovernorUnavailable):
        with ext._heavy_slot("r3"):
            pass
    assert time.monotonic() - started >= 0.9  # it waited for a slot first
    release.set()
    for t in threads:
        t.join()
    with ext._heavy_slot("r4"):  # slots are given back
        pass


def test_settings_are_bounded() -> None:
    from app.config import ConfigError
    with pytest.raises(ConfigError):
        Settings.from_env(base_env(GOVERNOR_DATABASE_URL="postgresql://x/y", SQL_HEAVY_QUERY_CONCURRENCY="65"))
