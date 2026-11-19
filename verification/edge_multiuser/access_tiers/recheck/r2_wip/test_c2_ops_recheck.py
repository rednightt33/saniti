"""EXEC-MU-ACCOUNTS round-2 re-check, checker C2-OPS (operations, failure modes and performance) of Phases 0-3b.

Each test fails on main as deployed (ae9a1d8f) for the reason its docstring names; the fix round makes it pass.
- F1: the hourly cleanup shares the worker loop's try block with the AI job claim, so a cleanup that fails (any error,
  or the pending-account purge past the connection's 5 s statement_timeout) is retried every poll and no AI job is ever
  claimed again; the purge is slow because six foreign keys to edge_bff.users have no index, so every deleted pending
  registration scans sessions, email_codes, subscriptions and admin_audit.
- F2: the principal's one statement (accounts.py GRANTS, CTE `lapsed`) reads the whole subscriptions table for every
  request of an account without a live subscription (every free user), because only the active rows are indexed.
- F3: the email outbox (never deleted: no DELETE grant, no purge) has no index for the sender's claim or for the
  per-address send check of register, forgot, resend and restart, so each of them reads the whole table.
- F4: an Orc that stops answering holds asyncio's default thread pool (every Orc call waits up to 3900 s in it), and
  the principal of every route is resolved in that same pool, so a hung Orc stalls sign-in and every tab.
- F5: readiness is decided once at start: a Postgres restart while edge-bff starts leaves the AI worker (and, switch
  on, the email sender and every hourly purge) stopped until the next deploy, while /ready answers ready.
"""
import asyncio
import dataclasses
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.accounts import AccountStore
from app.main import create_app
from app.mailer import OutboxStore
from app.store import Store
from app.worker import Worker
from conftest import FakeOrc

ORIGIN = {'Origin': 'http://testserver'}
ROOT = Path(__file__).resolve().parents[3]


def sql(store, statement, *args):
    with store.connect() as c:
        cur = c.execute(statement, args)
        return cur.fetchall() if cur.description else cur.rowcount


def admin_sql(database, statement):
    """A statement as the table owner, without edge-bff's 5 s statement_timeout (bulk fills, ANALYZE)."""
    with psycopg.connect(database, autocommit=True) as c:
        c.execute(statement)


# ---- F1 -------------------------------------------------------------------------------------------------------------

def test_f1_the_worker_claims_ai_jobs_while_the_hourly_cleanup_fails(settings, store, monkeypatch):
    """worker.py run(): `if cleaned_at is None or ...: await cleanup_sessions` sits in the same try block as the claim,
    and cleaned_at is set only after a success. A cleanup that raises (here QueryCanceled, as the pending-account purge
    past the 5 s statement_timeout raises) is retried every poll_seconds and the claim below it is never reached: the
    queued run stays QUEUED forever."""
    def failing_cleanup():
        raise psycopg.errors.QueryCanceled('canceling statement due to statement timeout')
    monkeypatch.setattr(store, 'cleanup_sessions', failing_cleanup)
    job, _ = store.submit(settings.owner, 'ops-f1', {'message': 'Explain GOTO'})
    worker = Worker(settings, store, FakeOrc())

    async def drive():
        task = asyncio.create_task(worker.run())
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and store.job(settings.owner, job['request_id'])['state'] != 'FINISHED':
            await asyncio.sleep(0.05)
        worker.stop()
        await asyncio.gather(task, return_exceptions=True)
    asyncio.run(drive())
    assert store.job(settings.owner, job['request_id'])['state'] == 'FINISHED', \
        'a failing hourly cleanup kept every AI run QUEUED (the claim is never reached)'


def test_f1_every_foreign_key_to_users_has_an_index(store):
    """Deleting a user (the hourly purge_pending, verify_registration's delete of the other pending registrations,
    Phase 4's account deletion) runs one referential action per referencing row set: without an index whose first
    column is the foreign key column, each deleted user is a sequential scan of that table. Measured on 100k sessions,
    202k codes, 51k subscriptions and 100k audit rows: 500 expired registrations took 15.0 s (email_codes 7.0 s,
    sessions 3.8 s, admin_audit 2.7 s, subscriptions 1.4 s), three times the purge's 5 s statement_timeout."""
    rows = sql(store, '''SELECT c.conrelid::regclass::text AS tab, a.attname AS col,
            EXISTS (SELECT 1 FROM pg_index i WHERE i.indrelid = c.conrelid AND i.indkey[0] = c.conkey[1]
                    AND i.indpred IS NULL) AS indexed
        FROM pg_constraint c JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
        WHERE c.contype = 'f' AND c.confrelid = 'edge_bff.users'::regclass ORDER BY 1, 2''')
    missing = sorted(f"{r['tab']}.{r['col']}" for r in rows if not r['indexed'])
    assert not missing, f'foreign keys to edge_bff.users without an index: {missing}'


def test_f1_the_hourly_cleanup_purges_expired_registrations_within_its_statement_timeout(database, store):
    """The real trigger of F1: Store.cleanup_sessions purges sessions, throttle rows and pending registrations in one
    transaction of a connection with statement_timeout 5 s. With 60k sessions, 120k email codes and 30k audit rows (a
    year of a few thousand accounts; codes are never purged) and 600 registrations never verified (no per-address
    limit stops 600 addresses; the per-IP send limit is recorded, not enforced), the purge's unindexed cascades exceed
    the timeout and the whole cleanup rolls back, every hour, for ever (the pending rows only grow)."""
    admin_sql(database, '''
        INSERT INTO edge_bff.users(owner_key, username, email, email_verified_at, role, status)
        SELECT 'u_' || substr(md5('ops-a' || g), 1, 24), 'ops_a' || g, 'ops-a' || g || '@example.com', now(), 'user',
               'active' FROM generate_series(1, 3000) g;
        INSERT INTO edge_bff.users(owner_key, requested_username, email, role, status, created_at)
        SELECT 'u_' || substr(md5('ops-p' || g), 1, 24), 'ops_p' || g, 'ops-p' || g || '@example.org', 'user', 'pending',
               now() - interval '25 hours' FROM generate_series(1, 600) g;
        INSERT INTO edge_bff.sessions(token_hash, owner_key, user_id, created_at, expires_at)
        SELECT md5('ops-t' || g) || md5('ops-u' || g), u.owner_key, u.user_id, now(), now() + interval '1 day'
        FROM generate_series(1, 60000) g
        JOIN (SELECT user_id, owner_key, row_number() OVER (ORDER BY user_id) AS n FROM edge_bff.users
              WHERE status = 'active') u ON u.n = 1 + g % 3000;
        INSERT INTO edge_bff.email_codes(purpose, user_id, code_hash, created_at, expires_at, consumed_at)
        SELECT 'reset', u.user_id, md5('ops-c' || g) || md5('ops-d' || g), now() - interval '1 day',
               now() - interval '1 day' + interval '300 seconds', now() - interval '1 day'
        FROM generate_series(1, 120000) g
        JOIN (SELECT user_id, row_number() OVER (ORDER BY user_id) AS n FROM edge_bff.users
              WHERE status = 'active') u ON u.n = 1 + g % 3000;
        INSERT INTO edge_bff.admin_audit(action, target_user_id)
        SELECT 'user.update', (SELECT min(user_id) FROM edge_bff.users) FROM generate_series(1, 30000);
        ANALYZE edge_bff.users; ANALYZE edge_bff.sessions; ANALYZE edge_bff.email_codes; ANALYZE edge_bff.admin_audit;''')
    try:
        started = time.monotonic()
        try:
            store.cleanup_sessions()
        except psycopg.errors.QueryCanceled as e:
            pytest.fail(f'the hourly cleanup was cancelled by its statement_timeout after '
                        f'{time.monotonic() - started:.1f} s: {str(e).splitlines()[0]}; CONTEXT: {e.diag.context}')
        took = time.monotonic() - started
        left = sql(store, "SELECT count(*) AS n FROM edge_bff.users WHERE status = 'pending'")[0]['n']
        assert left == 0 and took < 5, (left, took)
    finally:
        admin_sql(database, 'TRUNCATE edge_bff.admin_audit, edge_bff.email_codes, edge_bff.sessions, edge_bff.users CASCADE')


# ---- helpers for the plan checks ----------------------------------------------------------------------------------

class Recording:
    """A Store stand-in whose connections record every statement (to EXPLAIN it after) and run it unchanged."""

    def __init__(self, store):
        self.inner, self.statements = store, []

    @contextmanager
    def connect(self):
        with self.inner.connect() as c:
            outer = self

            class Wrapped:
                def __init__(self, conn):
                    self.conn = conn

                def execute(self, statement, params=None):
                    outer.statements.append((statement, params))
                    return self.conn.execute(statement, params)

                def __getattr__(self, name):
                    return getattr(self.conn, name)
            yield Wrapped(c)


def plan_of(database, statement, params):
    with psycopg.connect(database) as c:
        lines = [r[0] for r in c.execute('EXPLAIN (ANALYZE, BUFFERS, COSTS OFF) ' + statement, params).fetchall()]
        c.rollback()
    return '\n'.join(lines)


# ---- F2 -------------------------------------------------------------------------------------------------------------

def test_f2_the_principal_of_a_free_user_reads_no_other_accounts_subscriptions(database, store):
    """accounts.py GRANTS: `lapsed` (evaluated whenever the account has no live subscription, i.e. every request of a
    free user) filters subscriptions on (status = 'active' AND expires_at <= now()) OR status = 'expired' joined to the
    account; the only user_id index (subscriptions_one_active) is partial on status = 'active', so the statement scans
    every subscription row of every account. Measured: 51k rows, 11-20 ms per request (690 buffers) against 1 ms for a
    paid user; the table grows by one row per account and paid period (Phase 5)."""
    admin_sql(database, '''
        INSERT INTO edge_bff.users(owner_key, username, email, email_verified_at, role, status)
        SELECT 'u_' || substr(md5('ops-s' || g), 1, 24), 'ops_s' || g, 'ops-s' || g || '@example.com', now(), 'user',
               'active' FROM generate_series(1, 3000) g;
        INSERT INTO edge_bff.subscriptions(user_id, plan_key, status, starts_at, expires_at, provider, provider_ref)
        SELECT u.user_id, 'paid', 'expired', now() - (k + 1) * interval '30 days', now() - k * interval '30 days', 'manual',
               'ops-' || u.user_id || '-' || k
        FROM (SELECT user_id FROM edge_bff.users ORDER BY user_id LIMIT 2500) u, generate_series(1, 8) k;
        ANALYZE edge_bff.subscriptions; ANALYZE edge_bff.users;''')
    try:
        free = sql(store, '''SELECT user_id, owner_key FROM edge_bff.users WHERE user_id NOT IN
            (SELECT user_id FROM edge_bff.subscriptions) ORDER BY user_id LIMIT 1''')[0]
        hashed = 'f' * 64
        sql(store, '''INSERT INTO edge_bff.sessions(token_hash, owner_key, user_id, expires_at, last_seen_at)
            VALUES (%s, %s, %s, now() + interval '1 day', now())''', hashed, free['owner_key'], free['user_id'])
        recording = Recording(store)
        assert AccountStore(recording).resolve(hashed, 28800)['plan_key'] == 'free'
        statement, params = recording.statements[-1]
        plan = plan_of(database, statement, params)
        assert 'Seq Scan on subscriptions' not in plan, plan
    finally:
        admin_sql(database, 'TRUNCATE edge_bff.subscriptions, edge_bff.sessions, edge_bff.users CASCADE')


# ---- F3 -------------------------------------------------------------------------------------------------------------

def fill_outbox(database, rows=60000):
    admin_sql(database, f'''
        INSERT INTO edge_bff.email_outbox(idempotency_key, purpose, to_email, status, attempts, next_at, provider_id,
                                          expires_at, created_at, sent_at)
        SELECT 'ops:' || g, 'reset', 'ops' || (g % 5000) || '@example.com', 'sent', 1, now() - g * interval '90 seconds',
               're_' || g, now() - g * interval '90 seconds' + interval '300 seconds', now() - g * interval '90 seconds',
               now() - g * interval '90 seconds' + interval '2 seconds'
        FROM generate_series(1, {rows}) g;
        ANALYZE edge_bff.email_outbox;''')


def test_f3_the_sender_claim_reads_no_whole_outbox(database, store):
    """mailer.py OutboxStore.claim runs, for every email and every POLL_SECONDS (5 s) per edge-bff instance while idle,
    two UPDATEs (expired, suppressed) and a SELECT over email_outbox filtered on status, next_at, lease_expires_at and
    expires_at, none of them indexed; rows are never deleted (no DELETE grant, no purge; to_email kept for ever).
    Measured on 300k sent rows: 30 ms per statement, three per claim, rising linearly with every email ever sent."""
    fill_outbox(database)
    try:
        recording = Recording(store)
        assert OutboxStore(recording).claim() is None
        plans = [plan_of(database, s, p) for s, p in recording.statements]
        scans = [p for p in plans if 'Seq Scan on email_outbox' in p]
        assert not scans, scans[0]
    finally:
        admin_sql(database, 'TRUNCATE edge_bff.email_outbox')


def test_f3_the_per_address_send_check_reads_no_whole_outbox(database, store, settings):
    """auth_flows.py _may_send (register, resend, restart; forgot through resend's path) asks the outbox for the
    address's last minute: `WHERE to_email=%s AND created_at > now() - 60 s`, with no index on to_email or created_at,
    so each unauthenticated call scans every email ever queued (measured 19 ms at 300k rows, a parallel seq scan)."""
    fill_outbox(database)
    try:
        on = dataclasses.replace(settings, multiuser=True, code_secret='c' * 40, mfa_key='m' * 40)
        app = create_app(on, store, FakeOrc())
        flows = app.state.auth_flows.store                                   # auth_flows.py FlowStore
        recording = Recording(store)
        with recording.connect() as c:
            flows._may_send(c, 'ops7@example.com', '203.0.113.9')
            c.rollback()
        statement, params = next((s, p) for s, p in recording.statements if 'email_outbox' in s)
        plan = plan_of(database, statement, params)
        assert 'Seq Scan on email_outbox' not in plan, plan
    finally:
        admin_sql(database, 'TRUNCATE edge_bff.email_outbox, edge_bff.auth_throttle')


# ---- F4 -------------------------------------------------------------------------------------------------------------

class HungOrc(FakeOrc):
    """An Orc that accepts the progress read and never answers (the 3900 s client timeout, client.py)."""

    def __init__(self):
        super().__init__()
        self.release = threading.Event()

    def progress(self, owner, request_id):
        self.release.wait(30)
        return None


def test_f4_a_hung_orc_does_not_stall_the_session_of_every_tab(settings, store):
    """Every Orc call of a route (progress, messages, request, models, manual, branch, export) and every Store call of
    the principal (store.session switch off, accounts.resolve switch on), the throttle and the worker run in asyncio's
    one default ThreadPoolExecutor (min(32, cpu + 4) threads). Orc calls wait up to EDGE_ORC_TIMEOUT_SECONDS (3900 s),
    so as many open Monitor tabs as the pool has threads, polling a run's progress while Orc hangs, stop sign-in, the
    Terminal and every other tab: GET /api/v1/auth/session waits behind them."""
    orc = HungOrc()
    pool = min(32, (os.cpu_count() or 1) + 4)
    try:
        with TestClient(create_app(settings, store, orc)) as c:
            r = c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'owner', 'password': 'local-test-password'})
            assert r.status_code == 200
            job, _ = store.submit(settings.owner, 'ops-f4', {'message': 'Explain GOTO'})
            with ThreadPoolExecutor(pool + 2) as browsers:
                for _ in range(pool + 2):
                    browsers.submit(c.get, f"/api/v1/runs/{job['request_id']}/progress")
                time.sleep(1.0)
                with ThreadPoolExecutor(1) as probe:
                    answer = probe.submit(c.get, '/api/v1/auth/session')
                    started = time.monotonic()
                    while not answer.done() and time.monotonic() - started < 3:
                        time.sleep(0.05)
                    stalled = not answer.done()
                    orc.release.set()
                    assert answer.result(30).status_code == 200
            assert not stalled, f'the session read waited behind {pool + 2} hung Orc progress reads (pool of {pool})'
    finally:
        orc.release.set()


# ---- F5 -------------------------------------------------------------------------------------------------------------

class RestartingAtBoot(Store):
    """The house Store whose first readiness check fails as during the 12 s of a Postgres restart."""

    def __init__(self, url):
        super().__init__(url)
        self.first = True

    def ready(self, multiuser=False):
        if self.first:
            self.first = False
            raise psycopg.OperationalError('the database system is starting up')
        return super().ready(multiuser)


def test_f5_a_postgres_restart_during_the_start_does_not_leave_the_worker_stopped(settings, store):
    """main.py lifespan: ready['value'] is read once; False keeps the worker task (and, switch on, the email sender)
    from ever starting, while GET /ready checks the database again on every call and answers ready, so Railway routes
    traffic to an edge-bff whose AI runs stay QUEUED and whose hourly purges never run until the next deploy."""
    flaky = RestartingAtBoot(settings.database_url)
    try:
        with TestClient(create_app(dataclasses.replace(settings, worker_enabled=True), flaky, FakeOrc())) as c:
            assert c.get('/ready').status_code == 200
            job, _ = store.submit(settings.owner, 'ops-f5', {'message': 'Explain GOTO'})
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and store.job(settings.owner, job['request_id'])['state'] != 'FINISHED':
                time.sleep(0.05)
            assert store.job(settings.owner, job['request_id'])['state'] == 'FINISHED', \
                '/ready answers ready, yet the worker never started: the run stays QUEUED'
    finally:
        flaky.close()


# ---- F6 -------------------------------------------------------------------------------------------------------------

def test_f6_the_postgres_restart_guard_sees_running_backtests():
    """AGENTS.md and ERRORS M340: a Postgres restart waits while a user run is active. scripts/restart_postgres.py
    user_runs() counts edge_bff.jobs and AI_conversation_turn only; a queued or running backtest
    (edge_bff.backtest_jobs QUEUED/RUNNING, the backtest loop's lease, progress and result writes) is a user run the
    guard never sees, and with EDGE_MULTIUSER on it is another account's run the operator cannot see either."""
    source = (ROOT / 'scripts' / 'restart_postgres.py').read_text()
    body = source[source.index('def user_runs'):source.index('def checks')]
    assert re.search(r'edge_bff\.backtest_jobs', body), 'user_runs() does not count edge_bff.backtest_jobs'
