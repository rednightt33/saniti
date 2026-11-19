"""EXEC-MU-ACCOUNTS ultracode re-check, round 2, checker C2-OPS (operations, failure modes and performance; 2026-11-19;
user: "Jangan sampai fase 3C di bangun dari broken block fase2 sebelumnya"). Failing tests of VERIFIED findings in what
Phases 0-3b deployed (switch EDGE_MULTIUSER off on dev):

1. The worker loop runs the hourly cleanup (Store.cleanup_sessions) in the same try block as the job claim. When the
   cleanup fails, cleaned_at is not set, so the next turn runs the cleanup again and never reaches the claim: one
   failing purge stops every AI run. Phases 0 and 1 added two purges to that one transaction (auth_throttle,
   pending accounts), each bounded by the store's 5 s statement timeout.
2. No foreign key to edge_bff.users has an index on its column except identities, mfa_* and the overrides' own key:
   the pending-account purge runs one sequential scan of sessions, email_codes, subscriptions and twice admin_audit per
   deleted account (measured: 200 accounts = 5.0 s with 100k sessions, 107k codes, 50k audit rows, 20k
   subscriptions, so the purge times out and rolls back the whole cleanup), and the per-request resolve of an account
   without a live subscription scans all of subscriptions (the `lapsed` CTE).
3. The email outbox is never purged and has no index for the reads that run on every unauthenticated register / resend
   / forgot (_may_send: by to_email) and every 5 s in the sender (claim: by status): each is a full scan of every email
   ever sent (measured: 30-54 ms and 8367 buffers each at 500k rows).
4. A database error while edge-bff starts (a deploy during the planned 09:45 / 20:45 WIB Postgres restart) leaves the
   AI worker, the email sender and the hourly purges unstarted for the life of the process, while /ready, which reads
   the tables again on every call, answers 200 (the deploy succeeds). EDGE_EMAIL_ENABLED and EDGE_WORKER_ENABLED take
   any value but 'true' as off, so a typo silently stops them too (EDGE_MULTIUSER refuses a typo).
5. Every password check runs on the event loop's default thread pool, the pool every database call of every route
   uses (asyncio.to_thread). Since Phase 0 nothing bounds sign-ins per client (SIGNIN_IP is recorded, not enforced;
   the per-login limit is passed by typing other logins), so a burst of sign-ins with made-up logins holds every
   thread in scrypt and the signed-in users' requests wait behind them.
"""
import asyncio
import dataclasses
import os
import threading
import time
from contextlib import contextmanager

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from app import security
from app.auth_flows import FlowStore
from app.config import Settings
from app.mailer import OutboxStore
from app.main import create_app
from app.store import Store
from app.throttle import Throttle
from app.worker import Worker
from conftest import FakeOrc
from test_auth_flows import on, register  # noqa: F401 - the fixture `on`
from test_edge import ORIGIN, login


def db(store, sql, *args):
    with store.connect() as c:
        cur = c.execute(sql, args)
        return cur.fetchall() if cur.description else cur.rowcount


# ---- 1. a failing cleanup stops the run queue ---------------------------------------------------------------------

def test_a_failing_hourly_cleanup_does_not_stop_the_run_queue(settings):
    """The purge times out (the store's statement_timeout of 5 s): the loop must still claim the queued runs."""
    calls = []

    class FailingCleanup:
        def cleanup_sessions(self):
            calls.append('cleanup')
            raise psycopg.errors.QueryCanceled('canceling statement due to statement timeout')

        def claim(self, lease):
            calls.append('claim')
            loop.stop()
            return None

    loop = Worker(dataclasses.replace(settings, poll_seconds=0.001), FailingCleanup(), FakeOrc())

    async def bounded():
        try:
            await asyncio.wait_for(loop.run(), timeout=2)
        except asyncio.TimeoutError:
            loop.stop()
    asyncio.run(bounded())
    assert 'claim' in calls, f'{calls.count("cleanup")} cleanups in 2 s and no claim: no queued run is ever dispatched'


# ---- 2. the references to an account have no index -----------------------------------------------------------------

def test_every_reference_to_an_account_has_an_index(store):
    """A delete of edge_bff.users (the hourly pending purge; Phase 4 account deletion) checks each referencing column,
    and the principal's reads go by user_id (sessions: the sign-in's cap, revoke_all, reset, change; subscriptions:
    the resolve's live and lapsed CTEs). A partial index (email_codes_one_live, subscriptions_one_active) serves
    neither the cascade nor the lapsed read."""
    missing = db(store, '''
        SELECT c.conrelid::regclass::text AS tbl, a.attname AS col
        FROM pg_constraint c JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
        WHERE c.contype = 'f' AND c.confrelid = 'edge_bff.users'::regclass AND cardinality(c.conkey) = 1
          AND NOT EXISTS (SELECT 1 FROM pg_index i WHERE i.indrelid = c.conrelid AND i.indkey[0] = c.conkey[1]
                          AND i.indpred IS NULL)
        ORDER BY 1, 2''')
    assert missing == [], f'foreign keys to edge_bff.users without an index on their column: {missing}'


# ---- 3. the email outbox's hot reads scan every email ever sent ---------------------------------------------------

class Recording:
    """The store, recording every statement its connections run (the outbox's and the flows' own SQL)."""

    def __init__(self, store):
        self.store, self.sql = store, []

    @contextmanager
    def connect(self):
        with self.store.connect() as c:
            yield RecordingConnection(c, self.sql)


class RecordingConnection:
    def __init__(self, c, log):
        self.c, self.log = c, log

    def execute(self, sql, params=None):
        self.log.append((sql, params))
        return self.c.execute(sql, params)

    def __getattr__(self, name):
        return getattr(self.c, name)


def seq_scans(plan, relation):
    found = []

    def walk(node):
        if node.get('Node Type') == 'Seq Scan' and node.get('Relation Name') == relation:
            found.append(node)
        for child in node.get('Plans', []):
            walk(child)
    walk(plan[0]['Plan'])
    return found


def test_the_outbox_reads_of_every_send_and_every_sender_turn_use_an_index(on, store):
    db(store, '''INSERT INTO edge_bff.email_outbox(idempotency_key, purpose, to_email, status, attempts, next_at,
                     created_at, sent_at, provider_id)
                 SELECT 'code:' || g, 'reset', 'user' || (g %% 2000) || '@example.com', 'sent', 1, t, t,
                        t + interval '1 second', 'prov_' || g
                 FROM generate_series(1, 20000) g, LATERAL (SELECT now() - (g %% 365) * interval '1 day' AS t) x''')
    db(store, 'ANALYZE edge_bff.email_outbox')
    recording = Recording(store)
    OutboxStore(recording).claim()
    flows = FlowStore(on, recording, Throttle(recording, on.session_secret))
    with recording.connect() as c:
        flows._may_send(c, 'nobody@example.com', '203.0.113.7')
    statements = [(sql, params) for sql, params in recording.sql if 'edge_bff.email_outbox' in sql]
    assert len(statements) >= 4                     # claim: two UPDATEs and the SELECT; _may_send: the cooldown read
    scanned = []
    with store.connect() as c:
        for sql, params in statements:
            plan = c.execute('EXPLAIN (FORMAT JSON) ' + sql, params).fetchone()['QUERY PLAN']
            if seq_scans(plan, 'email_outbox'):
                scanned.append(' '.join(sql.split())[:90])
    assert scanned == [], f'full scans of the outbox (20k sent rows) on hot paths: {scanned}'


# ---- 4. the loops stay unstarted after a database error at start, while /ready answers 200 --------------------------

class BlipStore(Store):
    """Postgres restarting while edge-bff starts: the first readiness read fails, later ones answer."""

    def __init__(self, url):
        super().__init__(url)
        self.failures = 1

    def ready(self, multiuser=False):
        if self.failures:
            self.failures -= 1
            raise psycopg.OperationalError('the database system is starting up')
        return super().ready(multiuser)


def test_the_email_sender_runs_once_ready_answers_after_a_database_error_at_start(on, store):
    application = create_app(dataclasses.replace(on, worker_enabled=True), BlipStore(store.url), FakeOrc())
    application.state.auth_flows.pwned_fetch = lambda prefix: ''
    with TestClient(application) as c:
        assert c.get('/ready').status_code == 200                 # the deploy's health check passes
        assert register(c).status_code == 202
        deadline = time.monotonic() + 5
        while True:
            rows = db(store, "SELECT status FROM edge_bff.email_outbox WHERE to_email = 'ana@example.com'")
            if (rows and rows[0]['status'] == 'sent') or time.monotonic() > deadline:
                break
            time.sleep(0.05)
        assert [r['status'] for r in rows] == ['sent'], (
            '/ready answered 200 but the registration code was never sent: the sender loop did not start')


def test_the_ai_worker_runs_once_ready_answers_after_a_database_error_at_start(settings, store):
    application = create_app(dataclasses.replace(settings, worker_enabled=True), BlipStore(store.url), FakeOrc())
    with TestClient(application) as c:
        assert c.get('/ready').status_code == 200
        h = login(c)
        r = c.post('/api/v1/runs', headers=h, json={'message': 'Explain GOTO', 'submission_key': 'blip'})
        assert r.status_code == 202, r.text
        request_id = r.json()['request_id']
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and c.get('/api/v1/runs/' + request_id).json()['state'] != 'FINISHED':
            time.sleep(0.05)
        assert c.get('/api/v1/runs/' + request_id).json()['state'] == 'FINISHED', (
            '/ready answered 200 but the queued run was never dispatched: the AI worker did not start')


@pytest.mark.parametrize('name', ['EDGE_EMAIL_ENABLED', 'EDGE_WORKER_ENABLED'])
def test_a_typo_in_a_loop_switch_stops_the_start(monkeypatch, name):
    """As EDGE_MULTIUSER (config.switch_of: "a typo must not turn accounts on"): a typo must not turn a loop off."""
    env = {'EDGE_DATABASE_URL': 'postgresql://edge_bff_login@db.invalid/edge', 'EDGE_ORC_URL': 'http://orc.invalid',
           'MARKET_AI_ORC_API_KEY': 'k', 'EDGE_OWNER': 'edge-private', 'EDGE_LOGIN': 'owner',
           'EDGE_PASSWORD_VERIFIER': security.password_verifier('local-test-password'),
           'EDGE_SESSION_SECRET': 's' * 40, 'EDGE_PUBLIC_ORIGIN': 'http://testserver', 'EDGE_ENVIRONMENT': 'local',
           'EDGE_SECURE_COOKIE': 'false', 'EDGE_MULTIUSER': 'true', 'EDGE_CODE_SECRET': 'c' * 40,
           'EDGE_MFA_KEY': 'm' * 40, name: 'ture'}
    for key in list(os.environ):
        if key.startswith(('EDGE_', 'RESEND_', 'BACKTEST_', 'SCREENER_', 'TERMINAL_')):
            monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(ValueError, match=name):
        Settings.from_env()


# ---- 5. password checks hold every thread the database calls need ----------------------------------------------------

def test_a_burst_of_sign_ins_with_made_up_logins_does_not_hold_the_signed_in_users_requests(settings, store,
                                                                                            monkeypatch):
    release, entered = threading.Event(), []
    real = security._scrypt

    def held(text, salt):                     # a password derivation that takes as long as the burst lasts
        entered.append(1)
        release.wait(15)
        return real(text, salt)

    application = create_app(settings, store, FakeOrc())

    async def scenario():
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url='http://testserver') as c:
            r = await c.post('/api/v1/auth/sign-in', headers=ORIGIN,
                             json={'login': 'owner', 'password': 'local-test-password'})
            assert r.status_code == 200, r.text
            monkeypatch.setattr(security, '_scrypt', held)
            threads = min(32, (os.cpu_count() or 1) + 4)          # asyncio's default executor
            async with httpx.AsyncClient(transport=transport, base_url='http://testserver') as stranger:
                burst = [asyncio.create_task(stranger.post('/api/v1/auth/sign-in', headers=ORIGIN, json={
                    'login': f'made-up-{i}', 'password': 'not the password'})) for i in range(threads + 2)]
                for _ in range(100):                               # until every thread is inside a password check
                    if len(entered) >= threads:                    # (or 5 s, when fewer can be: a bounded pool)
                        break
                    await asyncio.sleep(0.05)
                try:
                    answer = await asyncio.wait_for(c.get('/api/v1/auth/session'), timeout=3)
                except asyncio.TimeoutError:
                    answer = None
                finally:
                    release.set()
                    await asyncio.gather(*burst, return_exceptions=True)
            return answer
    answer = asyncio.run(scenario())
    assert answer is not None and answer.status_code == 200, (
        'a signed-in user\'s session read waited more than 3 s behind sign-ins with made-up logins')
