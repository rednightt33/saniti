"""EXEC-SECTOR-ANALYSIS S1: the worker refreshes Feature 08 after an equity run of Feature 04 is finalized.

The engine and incremental modules (TA-Lib) are replaced by stubs: these tests touch only finalize_runs, the
Feature08Refresher and the main loop's order. The SQL itself runs against PostgreSQL in the rehearsal
(verification/sector_analysis/db/rehearsal/rehearse.py, section "worker")."""
from __future__ import annotations

import datetime as dt
import sys
import types
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
for name, attrs in {
    "engine": {"COLUMNS": (), "FEATURE_COLUMNS": (), "TABLE": "Feature_04_Technical_Indicator", "VERSION": "v4",
               "dependency_closure": lambda columns: tuple(columns or ())},
    "incremental": {"STATE_VERSION": 1, "calculate_incremental": None, "validate_incremental_availability": None},
}.items():
    sys.modules.setdefault(name, types.SimpleNamespace(**attrs))
sys.path.insert(0, str(HERE))
import worker  # noqa: E402


class Result:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)


class FakeConnection:
    """Answers the refresher's statements by their text; records every statement."""

    def __init__(self, ready=True, due=(), lock_free=True, lookback=5, dates=(), fail_on=None):
        self.ready, self.due, self.lock_free, self.lookback = ready, list(due), lock_free, lookback
        self.dates, self.fail_on, self.calls = list(dates), fail_on, []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, statement, params=None):
        text = statement if isinstance(statement, str) else "SET statement_timeout"
        self.calls.append((text, params))
        if text == worker.FEATURE08_READY_SQL:
            return Result([{"ready": self.ready}])
        if text == worker.FEATURE08_DUE_SQL:
            return Result([{"anchor": d, "finished_at": None} for d in self.due])
        if text == worker.FEATURE08_LOCK_SQL:
            return Result([{"free": self.lock_free}])
        if text == worker.FEATURE08_UNLOCK_SQL:
            return Result([{"pg_advisory_unlock": True}])
        if text == worker.FEATURE08_LOOKBACK_SQL:
            return Result([{"correction_lookback_sessions": self.lookback}] if self.lookback else [])
        if text == worker.FEATURE08_DATES_SQL:
            return Result([{"date": d} for d in self.dates])
        if text == worker.FEATURE08_REFRESH_SQL:
            if self.fail_on is not None and params[0] == self.fail_on:
                raise RuntimeError("refresh_feature_08_day failed")
            return Result([{"rows": 70}])
        if text.startswith("SET statement_timeout"):
            return Result([])
        raise AssertionError(f"unexpected statement {text[:80]}")

    def refreshed(self):
        return [p[0] for t, p in self.calls if t == worker.FEATURE08_REFRESH_SQL]


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


D = [dt.date(2026, 11, 20) + dt.timedelta(days=k) for k in range(7)]


def refresher(conn, clock=None):
    return worker.Feature08Refresher(clock=clock or Clock(), connector=lambda: conn)


def events(capsys):
    import json
    return [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]


def test_a_due_run_refreshes_its_window_in_date_order_through_the_newest_date(capsys):
    conn = FakeConnection(due=[D[4], D[6]], dates=[D[0], D[1], D[2], D[3], D[4], D[5], D[6]])
    r = refresher(conn)
    assert r.maybe_run() == "refreshed"
    assert conn.refreshed() == D                                      # one statement per date, oldest first
    dates_call = next(p for t, p in conn.calls if t == worker.FEATURE08_DATES_SQL)
    assert dates_call == (D[4], 5)                                    # the oldest due anchor and the correction window
    assert any(t.startswith("SET statement_timeout") for t, _ in conn.calls)
    done = [e for e in events(capsys) if e["event"] == "feature08_refreshed"]
    assert done and done[0]["rows"] == 70 * 7 and done[0]["anchors"] == [str(D[4]), str(D[6])]


def test_nothing_due_and_not_created_write_nothing(capsys):
    for conn, outcome in ((FakeConnection(due=[]), "nothing_due"), (FakeConnection(ready=False), "unavailable")):
        assert refresher(conn).maybe_run() == outcome
        assert conn.refreshed() == []
    said = [e for e in events(capsys) if e["event"] == "feature08_refresh_unavailable"]
    assert len(said) == 1


def test_the_refresh_waits_while_the_backfill_holds_its_lock(capsys):
    conn = FakeConnection(due=[D[6]], lock_free=False, dates=D)
    assert refresher(conn).maybe_run() == "waiting"
    assert conn.refreshed() == []
    assert any(e["event"] == "feature08_refresh_waiting" for e in events(capsys))


def test_a_failure_is_logged_backed_off_and_asked_again_never_raised(capsys):
    clock = Clock()
    conn = FakeConnection(due=[D[6]], dates=D[2:], fail_on=D[4])
    r = refresher(conn, clock)
    assert r.maybe_run() == "failed"                                  # no exception reaches the loop
    assert conn.refreshed() == [D[2], D[3], D[4]]                     # stopped at the failing date: no later level
    failed = [e for e in events(capsys) if e["event"] == "feature08_refresh_failed"]
    assert failed and failed[0]["attempt"] == 1 and failed[0]["retry_in_seconds"] == worker.FEATURE08_RETRY_BASE_SECONDS
    assert "refresh_feature_08_day failed" in failed[0]["error"]
    r.poke()                                                          # a finalized run does not cut the backoff short
    assert r.maybe_run() is None
    clock.now += worker.FEATURE08_RETRY_BASE_SECONDS
    assert r.maybe_run() == "failed" and r.failures == 2
    assert r.next_at == clock.now + 2 * worker.FEATURE08_RETRY_BASE_SECONDS
    conn.fail_on = None
    clock.now = r.next_at
    assert r.maybe_run() == "refreshed" and r.failures == 0          # idempotent: the same dates again, then done
    assert r.next_at == clock.now + worker.FEATURE08_SCAN_SECONDS


def test_the_backoff_is_capped():
    clock = Clock()
    r = refresher(FakeConnection(due=[D[6]], dates=[D[6]], fail_on=D[6]), clock)
    for _ in range(12):
        clock.now = r.next_at
        r.maybe_run()
    assert r.next_at - clock.now == worker.FEATURE08_RETRY_CAP_SECONDS


def test_a_missing_market_schedule_row_uses_the_default_window():
    conn = FakeConnection(due=[D[6]], lookback=None, dates=[D[6]])
    refresher(conn).maybe_run()
    assert next(p for t, p in conn.calls if t == worker.FEATURE08_DATES_SQL) == (D[6], worker.FEATURE08_DEFAULT_LOOKBACK)


class FinalizeConnection:
    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def execute(self, statement, params=None):
        self.calls.append(statement)
        return Result(self.rows if "RETURNING" in statement else [])


@pytest.mark.parametrize("status,source,poked", [
    ("SUCCESS", "Monitoring_Price_ALL", True), ("PARTIAL", "Monitoring_Price_ALL", True),
    ("FAILED", "Monitoring_Price_ALL", False), ("SUCCESS", "Monitoring_Fixed_Income", False),
    ("PROCESSING", "Monitoring_Price_ALL", False)])
def test_finalize_runs_pokes_the_refresher_for_a_finished_equity_run(monkeypatch, status, source, poked):
    pokes = []
    monkeypatch.setattr(worker.FEATURE08, "poke", lambda: pokes.append(1))
    rows = [{"execution_id": "f04-x", "status": status, "source_monitor_table": source}]
    conn = FinalizeConnection(rows)
    assert worker.finalize_runs(conn) == rows
    assert bool(pokes) is poked
    assert "RETURNING m.execution_id,m.status,m.source_monitor_table" in conn.calls[0]


def test_finalize_runs_never_refreshes_inside_the_feature04_transaction(monkeypatch):
    """The refresh is not called from finalize_runs (it runs inside process_one's transaction): a failing refresh could
    otherwise roll Feature 04 back. finalize_runs only pokes; main runs the refresh after the commit."""
    monkeypatch.setattr(worker.FEATURE08, "run", lambda: pytest.fail("refresh inside the Feature 04 transaction"))
    worker.finalize_runs(FinalizeConnection([{"execution_id": "f04-x", "status": "SUCCESS",
                                               "source_monitor_table": "Monitoring_Price_ALL"}]))


def test_main_refreshes_after_the_job_and_before_the_telegram_dispatch(monkeypatch):
    order = []
    jobs = iter([worker.Job("equity", "BBCA", D[6], 1, 1, None, None, 1, 1, None, None), None])
    monkeypatch.setattr(worker, "claim_one", lambda: next(jobs))
    monkeypatch.setattr(worker, "process_one", lambda job: order.append("job"))
    monkeypatch.setattr(worker.FEATURE08, "maybe_run", lambda: order.append("feature08"))

    def dispatch():
        order.append("dispatch")
        return False
    monkeypatch.setattr(worker, "dispatch_one", dispatch)

    class Stop(Exception):
        pass

    def stop(_):
        raise Stop
    monkeypatch.setattr(worker.time, "sleep", stop)
    with pytest.raises(Stop):
        worker.main()
    assert order == ["job", "feature08", "feature08", "dispatch"]
