"""ERRORS M413: a round's RUNNING row must not outlive its process, and its end is always written and sent.

Postgres killed for memory (2026-11-09) dropped the round's connection: the final record failed on the dead
connection, the row stayed RUNNING, nothing was sent, and terminal-publisher waited on it. No database needed."""
from __future__ import annotations

import time

import psycopg
import pytest

import updater


class Conn:
    """A connection that records every statement; `dead` makes every statement fail as a dropped connection does."""

    def __init__(self, log, dead=False):
        self.log, self.dead, self.closed = log, dead, False

    def execute(self, sql, params=None):
        if self.dead:
            raise psycopg.OperationalError('server closed the connection unexpectedly')
        self.log.append((sql, params))
        return Rows(self.live if sql == updater.LIVE_ROUND_SQL else [])

    live: list = []

    def close(self):
        self.closed = True


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


def ended(log):
    return [p for sql, p in log if 'finished_at' in sql]


def started(log):
    return [p for sql, p in log if sql.lstrip().startswith('INSERT')]


def test_the_end_is_written_on_a_new_connection_when_the_rounds_connection_died():
    log, opened = [], []
    def open_conn():
        opened.append(Conn(log)); return opened[-1]
    assert updater.finish(Conn(log, dead=True), 'r1', open_conn, sleep=lambda s: None, status='FAILED',
                          last_error='x', finished_at='t')
    assert ended(log) == [{'status': 'FAILED', 'last_error': 'x', 'finished_at': 't', 'id': 'r1'}]
    assert len(opened) == 1 and opened[0].closed


def test_the_end_waits_for_postgres_to_recover():
    """Postgres in crash recovery refuses connections for a while: the end is tried again over FINISH_WAITS."""
    log, tries, slept = [], [], []
    def open_conn():
        tries.append(1)
        if len(tries) < 3:
            raise psycopg.OperationalError('the database system is in recovery mode')
        return Conn(log)
    assert updater.finish(Conn(log, dead=True), 'r1', open_conn, sleep=slept.append, status='SUCCESS',
                          last_error=None, finished_at='t')
    assert len(ended(log)) == 1 and slept == list(updater.FINISH_WAITS[:2])


def test_the_end_gives_up_after_every_wait_and_says_so():
    slept = []
    def open_conn():
        raise psycopg.OperationalError('connection refused')
    assert not updater.finish(Conn([], dead=True), 'r1', open_conn, sleep=slept.append, status='FAILED',
                              last_error='x', finished_at='t')
    assert slept == list(updater.FINISH_WAITS)


def test_a_live_connection_writes_the_end_at_once():
    log = []
    def open_conn():
        raise AssertionError('no new connection while the round\'s own works')
    assert updater.finish(Conn(log), 'r1', open_conn, status='SUCCESS', last_error=None, finished_at='t')
    assert len(ended(log)) == 1


def test_the_heartbeat_stamps_only_a_running_row_and_reconnects_after_a_failure():
    log, opened = [], []
    def open_conn():
        opened.append(Conn(log, dead=not opened))          # the first connection dies (Postgres restarted)
        return opened[-1]
    beat = updater.Heartbeat('r1', open_conn, every=0.01).start()
    deadline = time.monotonic() + 5
    while len(log) < 3 and time.monotonic() < deadline:
        time.sleep(0.01)
    beat.stop()
    assert not beat.thread.is_alive() and len(opened) == 2 and len(log) >= 3 and opened[1].closed
    assert log and all(sql == updater.HEARTBEAT_SQL and p == ('r1',) for sql, p in log)
    assert "status = 'RUNNING'" in updater.HEARTBEAT_SQL and 'updated_at = now()' in updater.HEARTBEAT_SQL


@pytest.fixture
def round_env(monkeypatch, tmp_path):
    """main() with its connections, the notify call and the heartbeat replaced; the token check fails at once."""
    log, sent, conns = [], [], []
    def connect(purpose='stockbit-updater', timeout_ms=900000):
        conns.append(Conn(log)); return conns[-1]
    monkeypatch.setattr(updater, 'connect', connect)
    monkeypatch.setattr(updater, 'notify', sent.append)
    monkeypatch.setattr(updater, 'HEARTBEAT_SECONDS', 3600)
    monkeypatch.setattr(updater, 'FINISH_WAITS', (0,))
    monkeypatch.setenv('STATE_DIR', str(tmp_path))
    monkeypatch.setenv('STOCKBIT_TOKEN', 'not-a-jwt')
    return log, sent, conns


def test_a_round_whose_connection_dies_still_ends_failed_and_is_sent(round_env, monkeypatch):
    log, sent, conns = round_env
    def die(token):
        conns[0].dead = True                                # the round's connection drops with the failure
        raise psycopg.OperationalError('terminating connection because of crash of another server process')
    monkeypatch.setattr(updater, 'token_expiry', die)
    assert updater.main() == 1
    (end,) = ended(log)
    assert end['status'] == 'FAILED' and 'crash of another server process' in end['last_error']
    assert len(sent) == 1 and conns[0].closed


def test_a_stop_from_railway_ends_the_round_failed_and_is_sent(round_env, monkeypatch):
    """SIGTERM (a redeploy, a removal, a usage-limit stop) becomes Stopped; the round ends FAILED with the reason."""
    log, sent, _ = round_env
    def stopped(token):
        updater._on_sigterm(15, None)
    monkeypatch.setattr(updater, 'token_expiry', stopped)
    assert updater.main() == 1
    (end,) = ended(log)
    assert end['status'] == 'FAILED' and end['last_error'].startswith('Stopped: Round dihentikan')
    assert len(sent) == 1


def test_notify_is_sent_even_when_the_end_cannot_be_written(round_env, monkeypatch):
    log, sent, conns = round_env
    def down(purpose='stockbit-updater', timeout_ms=900000):
        if conns:
            raise psycopg.OperationalError('connection refused')
        conns.append(Conn(log)); return conns[-1]
    monkeypatch.setattr(updater, 'connect', down)
    def die(token):
        conns[0].dead = True
        raise psycopg.OperationalError('server closed the connection unexpectedly')
    monkeypatch.setattr(updater, 'token_expiry', die)
    assert updater.main() == 1
    assert ended(log) == [] and len(sent) == 1


def test_a_round_does_not_start_while_another_rounds_heartbeat_is_fresh(round_env, monkeypatch):
    """Run Now is not held back by Railway while a round runs (cron docs): the second run refuses, writes no row and
    calls nothing."""
    log, sent, conns = round_env
    monkeypatch.setattr(Conn, 'live', [('fc71e483',)])
    monkeypatch.setattr(updater, 'token_expiry', lambda t: pytest.fail('a refused round reads no token'))
    assert updater.main() == 0
    assert started(log) == [] and sent == [] and conns[0].closed
    assert [p for sql, p in log if sql == updater.LIVE_ROUND_SQL] == [(updater.LIVE_ROUND_MINUTES,)]


def test_check_mode_reports_the_volume_and_writes_nothing(round_env, monkeypatch, tmp_path, capsys):
    import json, sqlite3
    log, sent, conns = round_env
    with sqlite3.connect(tmp_path / 'checkpoint.sqlite') as db:
        db.execute('CREATE TABLE fetched (day text, symbol text, manifest text, payload text, updated_at text)')
        db.execute("INSERT INTO fetched VALUES ('2026-11-09', 'BBCA', 'm', '{}', 't')")
    (tmp_path / 'before_2026-11-06.json.gz').write_bytes(b'')
    monkeypatch.setenv('UPDATER_MODE', 'CHECK')
    monkeypatch.setattr(updater.os.path, 'ismount', lambda p: True)
    assert updater.main() == 0
    out = [json.loads(l) for l in capsys.readouterr().out.splitlines() if '"check"' in l][0]
    assert out['writable'] and out['database'] and out['checkpoint_rows'] == 1 and out['before_files'] == 1
    assert out['checkpoint_last_day'] == '2026-11-09' and out['token_valid'] is False
    assert started(log) == [] and sent == [] and not (tmp_path / '.check_probe').exists()


def test_check_mode_fails_when_the_volume_is_not_mounted(round_env, monkeypatch):
    monkeypatch.setenv('UPDATER_MODE', 'CHECK')
    monkeypatch.setattr(updater.os.path, 'ismount', lambda p: False)
    assert updater.main() == 1
