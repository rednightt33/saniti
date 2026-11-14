"""EXEC-RADAR R2: the Radar step of a round (refresh.refresh_radar). No database needed: the queries are answered by a
fake that records the calls; the SQL itself is rehearsed on PostgreSQL 16 (verification/radar/REHEARSAL.md)."""
from __future__ import annotations

from datetime import date

import pytest

import refresh

D1, D2, D3 = date(2026, 11, 5), date(2026, 11, 6), date(2026, 11, 9)


class Fake:
    """Answers refresh_radar's reads; `calls` keeps every routine it ran, in order."""

    def __init__(self, table=True, first=date(2025, 11, 10), tickers=(), stale=None, days=(D1, D2, D3), recon=None,
                 backfill=False):
        self.table, self.first, self.tickers, self.stale, self.days = table, first, list(tickers), stale, list(days)
        self.recon, self.calls, self.backfill = recon, [], backfill

    def connect(self):
        return Conn(self)

    def run_in(self, sql, args=(), timeout='30min'):
        if sql == refresh.RECON07:
            n = len([d for d in self.days if d >= args['a']])
            return self.recon or (100, 100, n, n, True, 0)
        self.calls.append((sql.split('(')[0].split('.')[-1], args))
        return (1,)


class Conn:
    def __init__(self, fake):
        self.f = fake

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        f = self.f
        if 'to_regclass' in sql:
            return Rows([(refresh.F07 if f.table else None,)])
        if 'pg_try_advisory_lock' in sql:
            return Rows([(not f.backfill,)])
        if 'pg_advisory_unlock' in sql:
            return Rows([(True,)])
        if 'ORDER BY 1 DESC LIMIT' in sql:                 # the oldest of the RADAR_EVENT_DATES newest gate dates
            return Rows([(sorted(f.days)[-params[0]:][0],)])
        if sql.startswith('SELECT min(trade_date)'):
            return Rows([(f.first,)])
        if sql == refresh.RADAR_TICKERS:
            return Rows(f.tickers)
        if sql == refresh.RADAR_STALE_DAY:
            return Rows([(f.stale,)])
        if sql.startswith('SELECT DISTINCT trade_date'):
            return Rows([(d,) for d in f.days if d >= params[0]])
        raise AssertionError(sql)


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0]

    def fetchall(self):
        return self.rows

    def __iter__(self):
        return iter(self.rows)


@pytest.fixture
def fake(monkeypatch):
    def make(**kw):
        f = Fake(**kw)
        monkeypatch.setattr(refresh, 'connect', f.connect)
        monkeypatch.setattr(refresh, 'run_in', f.run_in)
        monkeypatch.setattr(refresh, 'analyze', lambda t: None)
        return f
    return make


def events():
    out = []
    return out, lambda e, **kw: out.append((e, kw))


def test_skipped_until_the_migration_exists(fake):
    f = fake(table=False)
    log, emit = events()
    assert refresh.refresh_radar(emit) == {'skipped': 'Feature 07 is not created yet'}
    assert f.calls == [] and log[0][0] == 'radar_skipped'


def test_skipped_until_the_backfill_wrote_rows(fake):
    f = fake(first=None)
    log, emit = events()
    assert refresh.refresh_radar(emit)['skipped'] == 'not backfilled'
    assert f.calls == []


def test_nothing_newer_means_no_work(fake):
    f = fake()
    log, emit = events()
    assert refresh.refresh_radar(emit)['tickers'] == 0
    assert f.calls == []


def test_changed_tickers_then_every_date_from_the_first_change_in_order(fake):
    f = fake(tickers=[('BBCA', D2), ('DOOH', D3)])
    log, emit = events()
    out = refresh.refresh_radar(emit)
    names = [c[0] for c in f.calls]
    assert names == ['refresh_feature_07', 'refresh_feature_07', 'refresh_feature_07_day', 'refresh_feature_07_day']
    assert [c[1] for c in f.calls[2:]] == [(D2,), (D3,)]        # the run of days needs date order
    assert out['since'] == str(D2) and out['dates'] == [str(D2), str(D3)]
    assert log[-1][0] == 'radar_done'


def test_a_day_step_that_did_not_finish_is_redone_without_ticker_work(fake):
    f = fake(stale=D1)
    log, emit = events()
    out = refresh.refresh_radar(emit)
    assert [c[1] for c in f.calls] == [(D1,), (D2,), (D3,)] and out['tickers'] == 0


def test_the_earlier_of_a_changed_ticker_and_a_stale_day_starts_the_dates(fake):
    f = fake(tickers=[('BBCA', D3)], stale=D2)
    log, emit = events()
    refresh.refresh_radar(emit)
    assert [c[1] for c in f.calls if c[0] == 'refresh_feature_07_day'] == [(D2,), (D3,)]


def test_a_missing_measure_row_or_gate_row_fails_the_step(fake):
    fake(tickers=[('BBCA', D3)], recon=(100, 99, 1, 1, True, 0))
    log, emit = events()
    with pytest.raises(refresh.RefreshFailed, match='measure rows 99'):
        refresh.refresh_radar(emit)
    fake(tickers=[('BBCA', D3)], recon=(100, 100, 0, 1, True, 0))
    with pytest.raises(refresh.RefreshFailed, match='gate rows 0'):
        refresh.refresh_radar(emit)
    fake(tickers=[('BBCA', D3)], recon=(100, 100, 1, 1, False, 0))        # a measure that differs from Feature 06
    with pytest.raises(refresh.RefreshFailed, match='equal to Feature 06 False'):
        refresh.refresh_radar(emit)
    fake(tickers=[('BBCA', D3)], recon=(100, 100, 1, 1, True, 3))         # rows left without their cross-section
    with pytest.raises(refresh.RefreshFailed, match='cross-section 3'):
        refresh.refresh_radar(emit)


def test_changed_corporate_actions_redo_the_newest_board_dates(fake):
    days = [date(2026, 10, d) for d in range(1, 29)]
    f = fake(days=days)
    log, emit = events()
    assert refresh.refresh_radar(emit, events_changed=False)['tickers'] == 0 and f.calls == []
    refresh.refresh_radar(emit, events_changed=True)
    assert [c[1][0] for c in f.calls] == days[-refresh.RADAR_EVENT_DATES:]


def test_a_running_backfill_is_left_alone(fake):
    f = fake(tickers=[('BBCA', D3)], backfill=True)
    log, emit = events()
    assert refresh.refresh_radar(emit) == {'skipped': 'backfill running'} and f.calls == []


def test_the_round_runs_the_radar_after_events_and_keeps_it_in_features():
    src = open(refresh.__file__.replace('refresh.py', 'updater.py')).read()
    assert src.index("steps['events'] = run_events") < src.index("steps['radar'] = refresh.refresh_radar")
    assert src.index("steps['radar'] = refresh.refresh_radar") < src.index("steps['table_status']")
    assert "features={**steps['features'], 'radar': steps['radar']}" in src
    # a Radar failure is a warning of the round (as the stock lists'), never the round's failure
    block = src[src.index("ca = (steps['events']"):src.index("steps['table_status']")]
    assert 'except Exception' in block and "steps['radar'] = {'failed'" in block
