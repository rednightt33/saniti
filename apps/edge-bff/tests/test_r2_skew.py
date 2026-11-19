"""EXEC-MU-ACCOUNTS re-check, round 2, checker C2-SKEW (version skew and deploy order). Failing tests of the verified
findings; the fix round makes them pass.

- F1: a switch-on session that has not passed MFA (or is idle, or of a disabled account) is a full admin session under
  any edge-bff that runs with EDGE_MULTIUSER off: the switch's way back, an older rollback build, or a second edge-bff
  service with the switch off on the same database. The switch-off resolution reads only token, revoked and expiry
  (store.session), although the column comment says a switch-off session is the one with user_id NULL.
- F2: a start with the switch off copies EDGE_PASSWORD_VERIFIER over user #1's password identity, so a password the
  admin changed with the switch on is undone by the switch's way back or by every start of a switch-off edge-bff on the
  same database, and the old password signs in again.
- F3: the start decides once, from one readiness read, which background loops run, while /ready is read again on every
  healthcheck: a start during a database outage (a Postgres restart) or before its migration (then applied within the
  healthcheck window) serves traffic with no AI job worker; and a start that never becomes ready still runs the backtest
  job loop, which claims and dispatches queued jobs.
"""
import dataclasses
import time

import psycopg
from fastapi.testclient import TestClient

from app.main import create_app
from app.store import Store
from conftest import FakeOrc
from test_backtest import backtest_tables, configured, single, submit, worker  # noqa: F401 - fixtures and helpers
from test_edge import ORIGIN, login

PASSWORD = 'local-test-password'


def switched_on(settings):
    return dataclasses.replace(settings, multiuser=True, code_secret='c' * 40, mfa_key='m' * 40)


def db(store, sql, *args):
    with store.connect() as c:
        cur = c.execute(sql, args)
        return cur.fetchall() if cur.description else cur.rowcount


# ---- F1 ---------------------------------------------------------------------------------------------------------------

def test_a_switch_on_session_that_has_not_passed_mfa_opens_nothing_with_the_switch_off(settings, store):
    on = switched_on(settings)
    with TestClient(create_app(on, store, FakeOrc())) as c:
        r = c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'owner', 'password': PASSWORD})
        assert r.status_code == 403 and r.json()['error']['code'] == 'MFA_REQUIRED'      # the password only
        token = c.cookies.get('edge_session')
        assert c.get('/api/v1/conversations').json()['error']['code'] == 'MFA_REQUIRED'
    pending = db(store, 'SELECT user_id, owner_key, mfa_passed_at FROM edge_bff.sessions WHERE revoked_at IS NULL')
    assert len(pending) == 1 and pending[0]['user_id'] is not None and pending[0]['mfa_passed_at'] is None
    assert pending[0]['owner_key'] == settings.owner                                   # user #1 keeps EDGE_OWNER

    # the same database under an edge-bff with the switch off (EDGE_MULTIUSER back to false, a rollback build, or the
    # second edge-bff service of the beta/live plan)
    with TestClient(create_app(settings, store, FakeOrc())) as c:
        c.cookies.set('edge_session', token)
        r = c.get('/api/v1/auth/session')
        assert r.status_code == 401, ('a password-only switch-on session became a switch-off admin session: '
                                      f'{r.status_code} {r.json().get("access")}')
        # control: a session made by the switch-off sign-in itself still works
        c.cookies.clear()
        login(c)
        assert c.get('/api/v1/auth/session').json()['access']['capabilities'] == ['*']


# ---- F2 ---------------------------------------------------------------------------------------------------------------

def test_a_switch_off_start_keeps_the_password_user_one_changed_with_the_switch_on(settings, store):
    on = switched_on(settings)
    new_password = 'a-fresh-long-password-2026'
    app = create_app(on, store, FakeOrc())
    app.state.auth_flows.pwned_fetch = lambda prefix: ''                 # never the real range API in a test
    with TestClient(app) as c:
        r = c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'owner', 'password': PASSWORD})
        headers = {**ORIGIN, 'X-CSRF-Token': r.json()['error']['details']['csrf_token']}
        db(store, 'UPDATE edge_bff.sessions SET mfa_passed_at = now() WHERE revoked_at IS NULL')   # MFA passed
        r = c.post('/api/v1/auth/password/change', headers=headers,
                   json={'current_password': PASSWORD, 'password': new_password, 'password_repeat': new_password})
        assert r.status_code == 200, r.text
    changed = db(store, "SELECT verifier FROM edge_bff.identities WHERE provider = 'password'")[0]['verifier']

    # one start with the switch off on the same database (the switch's way back, or the other edge-bff service)
    with TestClient(create_app(settings, store, FakeOrc())):
        pass

    assert db(store, "SELECT verifier FROM edge_bff.identities WHERE provider = 'password'")[0]['verifier'] == changed, \
        'the switch-off start overwrote the password the account set itself with EDGE_PASSWORD_VERIFIER'
    with TestClient(create_app(on, store, FakeOrc())) as c:
        old = c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'owner', 'password': PASSWORD})
        assert old.status_code == 401, 'the password the admin replaced signs in again'
        new = c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'owner', 'password': new_password})
        assert new.status_code == 403 and new.json()['error']['code'] == 'MFA_REQUIRED'


# ---- F3 ---------------------------------------------------------------------------------------------------------------

class OutageAtStart(Store):
    """A store whose first `failures` readiness reads fail, as when edge-bff starts while Postgres restarts (about 12 s,
    scripts/restart_postgres.py) or before its migration is applied; later reads succeed."""

    def __init__(self, url, failures=1):
        super().__init__(url)
        self.failures = failures

    def ready(self, multiuser=False):
        if self.failures:
            self.failures -= 1
            raise psycopg.OperationalError('the database system is starting up')
        return super().ready(multiuser)


def test_a_start_during_a_database_outage_runs_the_ai_worker_once_it_is_ready(settings, store):
    on_worker = dataclasses.replace(settings, worker_enabled=True)
    with TestClient(create_app(on_worker, OutageAtStart(settings.database_url), FakeOrc())) as c:
        assert c.get('/ready').status_code == 200          # Railway's healthcheck passes: the deployment takes traffic
        h = login(c)
        r = c.post('/api/v1/runs', headers=h, json={'message': 'Explain GOTO', 'submission_key': 'after-outage'})
        assert r.status_code == 202, r.text
        request_id = r.json()['request_id']
        state = None
        for _ in range(400):
            state = c.get(f'/api/v1/runs/{request_id}').json()['state']
            if state in ('FINISHED', 'FAILED', 'INTERRUPTED'):
                break
            time.sleep(0.01)
        assert state == 'FINISHED', f'a ready deployment never dispatched the run (state {state}): no job worker runs'


class NeverReady(Store):
    """A store whose readiness read always fails: an edge-bff build deployed before its migration."""

    def ready(self, multiuser=False):
        raise psycopg.errors.UndefinedTable('relation "edge_bff.auth_throttle" does not exist')


def test_a_build_that_is_not_ready_claims_no_backtest_job(configured, store, worker):  # noqa: F811 - fixtures
    with TestClient(create_app(configured, store, FakeOrc())) as c:                    # the serving build, no loop
        c.headers_for = login(c)
        job_id = submit(c, single(), 'queued-before-the-deploy').json()['request_id']
    assert db(store, 'SELECT state FROM edge_bff.backtest_jobs WHERE request_id=%s', job_id)[0]['state'] == 'QUEUED'

    new_build = dataclasses.replace(configured, worker_enabled=True)
    with TestClient(create_app(new_build, NeverReady(configured.database_url), FakeOrc())) as c:
        assert c.get('/ready').status_code == 503          # never takes traffic (EXEC.md Phase 0 and 1 "Order")
        time.sleep(1.0)
    state = db(store, 'SELECT state FROM edge_bff.backtest_jobs WHERE request_id=%s', job_id)[0]['state']
    assert not worker.posted('/v1/jobs') and state == 'QUEUED', \
        f'a build that never became ready claimed the queued job (state {state}) and handed it to the worker'
