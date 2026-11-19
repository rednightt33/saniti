"""EXEC-MU-ACCOUNTS, the beta and live websites on one database (EXEC.md "Production environment", user decisions
2026-11-19; fix round of the round-2 re-check, track site: ERRORS R2-1, R2-7, R2-8, R2-13, R2-23, R2-26, R2-33, R2-38).

- EDGE_SITE: beta (edge-bff, the admin only, EDGE_MULTIUSER off) or live (edge-bff-live, the user's domain, the switch
  on); config.validate refuses the pairings the decision rules out, and the log mode of the email sender outside a
  developer machine.
- Each loop has its own switch: the AI job loop runs on the beta only; each site's backtest loop claims, reaps and
  prunes only its own site's jobs; the email sender runs only with the switch on; the hourly housekeeping is its own
  task, each purge on its own.
- The live site never serves the Monitor, the admin routes, the admin rights or a lab item (principal.live_view):
  404 for the routes, the capabilities masked for every principal, '*' included, while user #1 still needs the second
  factor there. A session is bound to the site that made it: switch-off sessions have no account, switch-on ones do.
- GET /version answers the site and the commit (RAILWAY_GIT_COMMIT_SHA).
"""
import asyncio
import dataclasses
import json
import logging
import os

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import releases
from app.allow import allow_of
from app.backtest import BacktestLoop, BacktestStore
from app.config import Settings
from app.main import create_app
from app.rights import rights_of
from app.security import password_verifier
from app.store import PURGES
from app.worker import Housekeeping
from conftest import FakeOrc
from test_backtest import backtest_tables, configured, lineage_of, single, variant_of, worker  # noqa: F401 - fixtures
from test_edge import ORIGIN, login
from test_phase3a_gates import override, paid_user

PASSWORD = 'local-test-password'
CONV = 'conv_' + '0' * 32


def live_of(settings):
    return dataclasses.replace(settings, site='live', multiuser=True, code_secret='c' * 40, mfa_key='m' * 40)


def db(store, sql, *args):
    with store.connect() as c:
        cur = c.execute(sql, args)
        return cur.fetchall() if cur.description else cur.rowcount


def sign_in_admin(c, store):
    """User #1 on a switch-on site: the password, then the second factor marked passed (as the MFA step does)."""
    r = c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'owner', 'password': PASSWORD})
    assert r.status_code == 403 and r.json()['error']['code'] == 'MFA_REQUIRED', r.text
    db(store, 'UPDATE edge_bff.sessions SET mfa_passed_at = now() WHERE revoked_at IS NULL AND user_id IS NOT NULL')
    return {**ORIGIN, 'X-CSRF-Token': r.json()['error']['details']['csrf_token']}


# ---- the setting ------------------------------------------------------------------------------------------------------

def test_the_site_setting_refuses_the_pairings_the_decision_rules_out(settings):
    assert settings.site == 'beta' and settings.ai_worker is True                     # unset: the running service
    for change, words in [({'site': 'prod'}, 'EDGE_SITE is beta'),
                          ({'site': 'live'}, 'EDGE_SITE=live needs EDGE_MULTIUSER=true'),
                          # a beta with the switch on outside a developer machine (resend, so the log check passes)
                          ({'multiuser': True, 'code_secret': 'c' * 40, 'mfa_key': 'm' * 40, 'environment': 'dev',
                            'email_mode': 'resend'}, 'EDGE_SITE=beta runs with EDGE_MULTIUSER=false'),
                          ({**dataclasses.asdict(live_of(settings)), 'ai_worker_enabled': True},
                           'EDGE_AI_WORKER_ENABLED=true is for the beta only'),
                          # ERRORS R2-26: the Railway environment of both sites is dev; log mode is a local one only
                          ({**dataclasses.asdict(live_of(settings)), 'environment': 'dev'},
                           'EDGE_EMAIL_MODE=log is for EDGE_ENVIRONMENT=local only')]:
        with pytest.raises(ValueError, match=words):
            dataclasses.replace(settings, **change).validate()
    live = live_of(settings)
    live.validate()                                         # a developer machine: log mode and the live site
    # a deliberate test of the live site before its Resend key: only by the explicit switch
    dataclasses.replace(live, environment='dev', email_log_allowed=True, orc_url='http://market-ai-orc.railway.internal:8080',
                        database_url='postgresql://edge_bff_login@db.invalid/edge', origin='https://edge.example',
                        secure_cookie=True).validate()
    assert live.ai_worker is False and dataclasses.replace(settings, ai_worker_enabled=False).ai_worker is False
    dataclasses.replace(settings, multiuser=True, code_secret='c' * 40, mfa_key='m' * 40).validate()   # the tests


def env_of(monkeypatch, **extra):
    for key in list(os.environ):
        if key.startswith(('EDGE_', 'RESEND_', 'BACKTEST_', 'SCREENER_', 'TERMINAL_', 'RAILWAY_')):
            monkeypatch.delenv(key, raising=False)
    env = {'EDGE_DATABASE_URL': 'postgresql://edge_bff_login@db.invalid/edge', 'EDGE_ORC_URL': 'http://orc.invalid',
           'MARKET_AI_ORC_API_KEY': 'k', 'EDGE_OWNER': 'edge-private', 'EDGE_LOGIN': 'owner',
           'EDGE_PASSWORD_VERIFIER': password_verifier(PASSWORD), 'EDGE_SESSION_SECRET': 's' * 40,
           'EDGE_PUBLIC_ORIGIN': 'http://testserver', 'EDGE_ENVIRONMENT': 'local', 'EDGE_SECURE_COOKIE': 'false', **extra}
    for key, value in env.items():
        monkeypatch.setenv(key, value)


def test_the_site_and_each_loop_switch_are_read_from_the_environment(monkeypatch):
    env_of(monkeypatch)
    s = Settings.from_env()
    assert (s.site, s.ai_worker, s.backtest_loop_enabled, s.housekeeping_enabled, s.email_enabled, s.commit_sha) == \
        ('beta', True, True, True, True, '')
    env_of(monkeypatch, EDGE_SITE='live', EDGE_MULTIUSER='true', EDGE_CODE_SECRET='c' * 40, EDGE_MFA_KEY='m' * 40,
           EDGE_HOUSEKEEPING_ENABLED='false', RAILWAY_GIT_COMMIT_SHA='0123abc')
    s = Settings.from_env()
    assert (s.site, s.ai_worker, s.housekeeping_enabled, s.commit_sha) == ('live', False, False, '0123abc')


@pytest.mark.parametrize('name', ['EDGE_AI_WORKER_ENABLED', 'EDGE_BACKTEST_LOOP_ENABLED', 'EDGE_HOUSEKEEPING_ENABLED'])
def test_a_typo_in_a_loop_switch_stops_the_start(monkeypatch, name):
    env_of(monkeypatch, **{name: 'yes'})
    with pytest.raises(ValueError, match=name):
        Settings.from_env()


def test_the_start_line_shows_whether_both_sites_hold_the_same_shared_secrets(settings, store, caplog):
    """ERRORS R2-8, R2-26: what can be checked from one process. Each start logs a mark of each secret that keys shared
    rows; the same secrets give the same marks, another one another mark, and no mark carries the secret."""
    beta, live = settings, live_of(settings)
    assert beta.shared_key_marks()['EDGE_SESSION_SECRET'] == live.shared_key_marks()['EDGE_SESSION_SECRET']
    assert beta.shared_key_marks()['EDGE_CODE_SECRET'] is None and live.shared_key_marks()['EDGE_CODE_SECRET']
    rotated = dataclasses.replace(live, mfa_key='n' * 40).shared_key_marks()
    assert rotated['EDGE_MFA_KEY'] != live.shared_key_marks()['EDGE_MFA_KEY']
    assert not any(secret in json.dumps(live.shared_key_marks()) for secret in (live.session_secret, live.mfa_key))
    with caplog.at_level(logging.INFO, logger='edge_bff.startup'):
        with TestClient(create_app(live, store, FakeOrc())):
            pass
    done = [json.loads(r.getMessage()) for r in caplog.records if 'startup_done' in r.getMessage()]
    assert done and done[0]['site'] == 'live' and done[0]['shared_keys'] == live.shared_key_marks()


def test_version_names_the_site_and_the_commit(settings, store):
    with TestClient(create_app(dataclasses.replace(settings, commit_sha='0123abc'), store, FakeOrc())) as c:
        assert c.get('/version').json() == {'site': 'beta', 'commit': '0123abc'}
    with TestClient(create_app(live_of(settings), store, FakeOrc())) as c:
        assert c.get('/version').json() == {'site': 'live', 'commit': None}


# ---- the live site serves no beta-only route -------------------------------------------------------------------------

def test_the_live_site_answers_404_to_the_monitor_and_the_admin_routes(settings, store):
    with TestClient(create_app(live_of(settings), store, FakeOrc())) as c:
        for method, path in [('GET', '/api/v1/conversations'), ('GET', '/api/v1/models'), ('GET', '/api/v1/runs'),
                             ('POST', '/api/v1/runs'), ('GET', '/api/v1/dev/manual/steps'), ('GET', '/monitor'),
                             ('GET', f'/c/{CONV}')]:
            r = c.request(method, path, headers=ORIGIN, json={'message': 'x', 'submission_key': 'k'}
                          if method == 'POST' else None)
            assert r.status_code == 404 and r.json()['error']['code'] == 'NOT_FOUND', (method, path, r.text)
        assert c.get('/terminal').status_code == 200                      # the other pages are served
        assert c.get('/api/v1/preferences').status_code == 401            # a route the site has: the session first
    with TestClient(create_app(settings, store, FakeOrc())) as c:          # the beta: the Monitor is there
        assert c.get('/api/v1/conversations').status_code == 401 and c.get('/monitor').status_code == 200


def test_user_one_on_the_live_site_holds_no_beta_only_capability_and_still_needs_the_second_factor(settings, store):
    app = create_app(live_of(settings), store, FakeOrc())
    with TestClient(app) as c:
        sign_in_admin(c, store)
        access = c.get('/api/v1/auth/session').json()['access']
        caps = access['capabilities']
        assert '*' not in caps and 'terminal.view' in caps and 'backtest.run' in caps, caps
        assert not [k for k in caps if k.split('.')[0] in ('monitor', 'admin') or k == 'backtest.flow_point_in_time']
        assert access['mfa_ok'] is True and access['version'].startswith('db-')
        assert c.get('/api/v1/conversations').status_code == 404
        p = app.state.auth.owner_principal(settings.owner)
        assert not p.can('monitor.view') and not p.can('admin.access') and rights_of(p) == []
        assert all(v != '*' for v in allow_of(p, 'backtest').values())
        assert allow_of(p, 'backtest')['indicator']                        # the released items are held


def test_a_lab_item_is_never_held_on_the_live_site(settings, store, monkeypatch):
    entries = releases.entries('indicator')
    lab = entries[0]['id']
    items = [{'kind': kind, 'id': e['id'], 'stage': 'lab' if (kind, e['id']) == ('indicator', lab) else e['stage']}
             for kind in releases.KINDS for e in releases.entries(kind)]
    monkeypatch.setattr(releases, 'CURRENT', releases.Releases({'schema_version': 1, 'items': items}))
    live = create_app(live_of(settings), store, FakeOrc())
    with TestClient(live) as c:
        sign_in_admin(c, store)
        held = [e['id'] for e in c.get('/api/v1/catalog/indicator').json()['entries']]
        assert lab not in held and len(held) == len(entries) - 1
        assert lab not in allow_of(live.state.auth.owner_principal(settings.owner), 'backtest')['indicator']
        # an account whose family value is {"all": true} (every id, lab included) holds no lab item there either
        alice = paid_user(store, 'alice')
        override(store, alice['user_id'], 'terminal.indicator', '{"all": true}')
        p = live.state.auth.owner_principal(alice['owner_key'])
        assert not p.can(f'terminal.indicator:{lab}') and p.can(f'terminal.indicator:{entries[1]["id"]}')
        assert lab not in allow_of(p, 'backtest')['indicator']
    with TestClient(create_app(settings, store, FakeOrc())) as c:          # the beta: '*' holds the lab item
        login(c)
        assert lab in [e['id'] for e in c.get('/api/v1/catalog/indicator').json()['entries']]


def test_a_session_opens_only_the_site_that_made_it(settings, store):
    """ERRORS R2-1 for the two websites: a live session (an account's, its second factor passed) never opens the beta,
    and a beta session (no account) never opens the live site."""
    with TestClient(create_app(live_of(settings), store, FakeOrc())) as c:
        sign_in_admin(c, store)
        live_token = c.cookies.get('edge_session')
        assert c.get('/api/v1/auth/session').status_code == 200
    with TestClient(create_app(settings, store, FakeOrc())) as c:
        c.cookies.set('edge_session', live_token)
        assert c.get('/api/v1/auth/session').status_code == 401
        c.cookies.clear()
        login(c)
        beta_token = c.cookies.get('edge_session')
    with TestClient(create_app(live_of(settings), store, FakeOrc())) as c:
        c.cookies.set('edge_session', beta_token)
        assert c.get('/api/v1/auth/session').status_code == 401


# ---- each site's queues ----------------------------------------------------------------------------------------------

def test_each_site_claims_only_the_runs_it_queued(settings, store):
    first, _ = store.submit(settings.owner, 'live-one', {'message': 'One'}, site='live')
    assert first['site'] == 'live' and store.claim(90) is None                       # the beta's claim takes nothing
    app = create_app(live_of(settings), store, FakeOrc())
    row = app.state.worker.claim(90)                                                  # the live site's worker claim
    assert row['request_id'] == first['request_id']
    waiting, _ = store.submit(settings.owner, 'live-two', {'message': 'Two'}, after_stop=True, site='live')
    store.transition(row, 'FINISHED')                                                 # the waiting message becomes a job
    promoted = db(store, 'SELECT site, state FROM edge_bff.jobs WHERE request_id = %s', waiting['request_id'])
    assert promoted == [{'site': 'live', 'state': 'QUEUED'}]
    assert store.claim(90) is None and store.claim(90, site='live')['request_id'] == waiting['request_id']


def test_the_beta_backtest_loop_neither_reaps_nor_prunes_the_live_sites_jobs(configured, store):
    live, beta = BacktestStore(store, 'live'), BacktestStore(store, 'beta')
    request = single()
    job, _ = live.submit(configured.owner, 'live-job', request, lineage_of(request), variant_of(request), 3)
    assert job['site'] == 'live' and beta.claim(90) is None
    claimed = live.claim(90)
    db(store, "UPDATE edge_bff.backtest_jobs SET lease_expires_at = now() - interval '1 second' WHERE request_id = %s",
       claimed['request_id'])
    db(store, '''INSERT INTO edge_bff.backtest_results(request_id, part, payload, bytes, sha256, created_at)
        VALUES (%s, 'core', '\\x00', 1, %s, now() - interval '40 days')''', claimed['request_id'], '0' * 64)
    assert beta.reap() == [] and beta.prune() == 0
    assert live.reap() == [claimed['request_id']] and live.prune() == 1


def test_a_failing_prune_or_reap_does_not_stop_the_backtest_claims(settings):
    """ERRORS R2-33 (BacktestLoop.run): the prune and the reap ran before the claim in one try, so one that failed
    stopped every backtest."""
    calls = []

    class Failing:
        def prune(self):
            calls.append('prune')
            raise psycopg.errors.QueryCanceled('canceling statement due to statement timeout')

        def reap(self):
            calls.append('reap')
            raise psycopg.errors.LockNotAvailable('lock timeout')

        def claim(self, lease):
            calls.append('claim')
            if calls.count('claim') == 3:
                loop.stop()
            return None

    loop = BacktestLoop(dataclasses.replace(settings, poll_seconds=0.001), Failing(), None)
    asyncio.run(asyncio.wait_for(loop.run(), timeout=5))
    assert calls.count('claim') == 3 and calls[:3] == ['prune', 'reap', 'claim']


# ---- the housekeeping ------------------------------------------------------------------------------------------------

def test_a_failing_purge_stops_neither_the_others_nor_its_own_next_try(settings, caplog):
    calls, fails = [], {'throttle': 2}

    class Store:
        def purge(self, name, limit):
            calls.append(name)
            if fails.get(name):
                fails[name] -= 1
                raise psycopg.errors.QueryCanceled('canceling statement due to statement timeout')
            return 0

    loop = Housekeeping(dataclasses.replace(settings, poll_seconds=0.001), Store())

    async def scenario():
        task = asyncio.create_task(loop.run())
        for _ in range(2000):
            if calls.count('throttle') >= 3:
                break
            await asyncio.sleep(0.002)
        loop.stop()
        await task
    with caplog.at_level(logging.ERROR, logger='edge_bff.worker'):
        asyncio.run(scenario())
    assert calls.count('sessions') == 1 and calls.count('pending') == 1               # each made once, at the start
    assert calls.count('throttle') == 3                                               # failed twice, then made
    failed = [json.loads(r.getMessage()) for r in caplog.records if 'housekeeping_failed' in r.getMessage()]
    assert [(f['purge'], f['error'], f['failures']) for f in failed] == [('throttle', 'QueryCanceled', 1),
                                                                        ('throttle', 'QueryCanceled', 2)]
    assert failed[1]['retry_s'] > failed[0]['retry_s']                                # the backoff doubles


def test_a_purge_another_instance_runs_is_skipped_and_every_purge_is_bounded(store):
    db(store, "INSERT INTO edge_bff.sessions(token_hash, owner_key, created_at, expires_at) SELECT md5(g::text) || "
              "md5(g::text), 'o', now() - interval '2 hours', now() - interval '1 hour' FROM generate_series(1, 7) g")
    with psycopg.connect(store.url, autocommit=True) as other:
        other.execute("SELECT pg_advisory_lock(hashtextextended('housekeeping:sessions', 0))")
        assert store.purge('sessions', 3) is None                                    # the other website purges now
        other.execute("SELECT pg_advisory_unlock(hashtextextended('housekeeping:sessions', 0))")
    assert [store.purge('sessions', 3) for _ in range(4)] == [3, 3, 1, 0]
    assert set(PURGES) == {'sessions', 'throttle', 'pending'}


# ---- the start-up ----------------------------------------------------------------------------------------------------

def test_a_seed_that_fails_with_the_switch_on_keeps_the_site_not_ready(settings, store, monkeypatch):
    """With the switch on nothing can sign in without user #1 and its plan: /ready stays 503 and no loop starts while
    the seed fails (it is tried again); with the switch off the sign-in needs no account, so the site starts."""
    for site, ready in ((live_of(settings), 503), (settings, 200)):
        app = create_app(dataclasses.replace(site, worker_enabled=True), store, FakeOrc())
        failing = {'n': 0}

        def fail():
            failing['n'] += 1
            raise psycopg.OperationalError('the database system is starting up')
        monkeypatch.setattr(app.state.auth, 'seed_user', fail)
        with TestClient(app) as c:
            assert c.get('/ready').status_code == ready
        assert failing['n'] >= (2 if ready == 503 else 1)
