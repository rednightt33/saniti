"""EXEC-MU-ACCOUNTS Phase 1 (CONTRACT.md sections 0, 1, 2, 4 "Sessions", 4b and 13): the principal, the account tables
and the preferences.

- switch off (EDGE_MULTIUSER false): the principal is user #1 = EDGE_OWNER, every capability, version "env"; the
  session answer keeps today's keys and adds username and access; user #1 is seeded once, idempotent across replicas;
- the owner of a request comes only from the principal: app/ reads settings.owner only in principal.py's seed and
  switch-off mapping;
- switch on: a session joins an active account, within the idle timeout; at most 5 sessions per account; two accounts
  see none of each other's owned rows (404 on the other's items, empty lists) and Orc and the workers get the
  principal's owner;
- owner_key is immutable and never a reserved key; usernames follow their rule;
- preferences: GET and PUT with an optimistic version, per-owner limits.
"""
import ast
import dataclasses
from pathlib import Path
import threading

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import accounts as accounts_module
from app import preferences as preferences_module
from app.accounts import AccountStore, MAX_SESSIONS, new_owner_key, seed_identity
from app.main import create_app
from app.principal import Auth, Principal, switch_off_principal
from app.rights import rights_of
from app.security import password_verifier, token_hash
from conftest import FakeOrc
from test_backtest import FakeWorker as FakeBacktestWorker, KEY as BACKTEST_KEY, run_next, single
from test_edge import ORIGIN, login
from test_presets import CONFIG as PRESET_CONFIG
from test_screener import FakeScreenerWorker, KEY as SCREENER_KEY, item_id, screen_item

APP = Path(__file__).resolve().parents[1] / 'app'


def db(store, sql, *args):
    with store.connect() as c:
        cur = c.execute(sql, args)
        return cur.fetchall() if cur.description else cur.rowcount


# ---- switch off: today's behaviour, user #1 -------------------------------------------------------------------------

def test_settings_owner_is_read_only_by_the_seed_and_the_switch_off_mapping():
    """CONTRACT.md section 0: every other route, store, worker or Orc call takes the owner from the principal."""
    allowed = {('principal.py', name) for name in ('switch_off_principal', 'seed_user', 'configured_owner', 'resolve')}

    def settings_owner(node):
        """x.settings.owner, settings.owner, or s.owner with s = self.settings (seed_user)."""
        if not (isinstance(node, ast.Attribute) and node.attr == 'owner'):
            return False
        v = node.value
        return (isinstance(v, ast.Name) and v.id in ('settings', 's')) or (isinstance(v, ast.Attribute) and v.attr == 'settings')

    found = set()
    for path in sorted(APP.glob('*.py')):
        text = path.read_text()
        if path.name != 'principal.py':
            assert 'settings.owner' not in text, path.name               # in code or in a comment
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # the function that holds the use directly (not through a nested function)
                inner = [n for child in node.body for n in ast.walk(child)]
                nested = {id(n) for f in inner if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))
                          for n in ast.walk(f)}
                if any(settings_owner(n) and id(n) not in nested for n in inner):
                    found.add((path.name, node.name))
    assert found and found <= allowed, found - allowed


def test_switch_off_the_principal_is_user_one_and_the_session_keeps_todays_keys(settings, store):
    # an EDGE_ADMIN_OWNERS that does not list the configured owner (the conftest settings list it, as production's
    # default): no capability, as rights.py gave before Phase 1
    with TestClient(create_app(dataclasses.replace(settings, admin_owners=('another-owner',)), store, FakeOrc())) as c:
        login(c)
        answer = c.get('/api/v1/auth/session').json()
        assert {'authenticated', 'login', 'csrf_token', 'capabilities'} <= set(answer)
        assert answer['login'] == settings.login and answer['authenticated'] is True
        seeded = db(store, 'SELECT user_id, owner_key, username, role, status FROM edge_bff.users')
        assert [(r['owner_key'], r['role'], r['status']) for r in seeded] == [(settings.owner, 'admin', 'active')]
        assert answer['username'] == seeded[0]['username'] == 'owner'
        assert answer['access'] == {'plan': None, 'role': 'user', 'status': 'active', 'expires_at': None, 'mfa_ok': True,
                                    'capabilities': [], 'limits': {}, 'version': 'env', 'next': None,
                                    'owner_key': settings.owner, 'mfa_enrolled': False, 'seed': True, 'expired_plan': None}
        assert answer['owner_key'] == settings.owner
    admins = dataclasses.replace(settings, admin_owners=(settings.owner,))
    with TestClient(create_app(admins, store, FakeOrc())) as c:
        login(c)
        access = c.get('/api/v1/auth/session').json()['access']
        assert (access['role'], access['capabilities'], access['version']) == ('admin', ['*'], 'env')
        # a session of another owner stays refused, as before
        db(store, "UPDATE edge_bff.sessions SET owner_key='someone-else'")
        assert c.get('/api/v1/auth/session').status_code == 401
    assert db(store, 'SELECT count(*) AS n FROM edge_bff.users')[0]['n'] == 1          # the second start seeded nothing


def test_switch_off_rights_equal_todays_rights(settings):
    for admins, rights in [((), []), ((settings.owner,), ['flow_point_in_time']), (('another-owner',), [])]:
        s = dataclasses.replace(settings, admin_owners=admins)
        assert rights_of(switch_off_principal(s, s.owner)) == rights
    s = dataclasses.replace(settings, admin_owners=('another-owner',))
    assert rights_of(switch_off_principal(s, 'another-owner')) == ['flow_point_in_time']   # a queued job's admin owner


def test_the_seed_is_made_once_across_replicas_and_follows_the_configured_password(settings, store):
    a, b = AccountStore(store), AccountStore(store)
    results = []
    threads = [threading.Thread(target=lambda s=s: results.append(s.seed(settings.owner, settings.login,
                                                                         settings.password_verifier, False)))
               for s in (a, b, a, b)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len({r['user_id'] for r in results}) == 1
    assert db(store, 'SELECT count(*) AS n FROM edge_bff.users')[0]['n'] == 1
    ident = db(store, 'SELECT subject, verifier FROM edge_bff.identities')
    assert ident == [{'subject': str(results[0]['user_id']), 'verifier': settings.password_verifier}]
    rotated = password_verifier('rotated-password')
    a.seed(settings.owner, settings.login, rotated, False)                 # switch off: the environment is the source
    assert db(store, 'SELECT verifier FROM edge_bff.identities')[0]['verifier'] == rotated
    a.seed(settings.owner, settings.login, settings.password_verifier, True)   # switch on: the account's own, kept
    assert db(store, 'SELECT verifier FROM edge_bff.identities')[0]['verifier'] == rotated
    # another configured owner while accounts exist: no second seed
    assert a.seed('another-owner', 'x', rotated, False) is None
    assert db(store, 'SELECT count(*) AS n FROM edge_bff.users')[0]['n'] == 1


def test_seed_identity_from_the_login():
    assert seed_identity('Owner') == ('owner', None)
    assert seed_identity('admin') == ('admin_1', None)                    # reserved
    assert seed_identity('ab') == ('admin_1', None)                       # too short
    assert seed_identity('Me@Example.com') == ('admin_1', 'me@example.com')
    assert seed_identity('edge-private') == ('admin_1', None)             # a hyphen does not fit the username rule


# ---- the account tables ---------------------------------------------------------------------------------------------

def make_user(store, username, password, role='user', status='active', email=None, everything=None):
    """An account; Phase 2 (CONTRACT.md 8a): the role grants nothing, so an admin account (everything, default: role
    admin) also gets an active subscription to the plan that holds '*' (found by data, as the seed of user #1)."""
    owner = new_owner_key()
    with store.connect() as c:
        row = c.execute('''INSERT INTO edge_bff.users(owner_key, username, email, email_verified_at, role, status)
            VALUES (%s,%s,%s,now(),%s,%s) RETURNING user_id, owner_key, username''',
                        (owner, username, email or f'{username}@example.com', role, status)).fetchone()
        c.execute("INSERT INTO edge_bff.identities(user_id, provider, subject, verifier) VALUES (%s,'password',%s,%s)",
                  (row['user_id'], str(row['user_id']), password_verifier(password)))
        if role == 'admin' if everything is None else everything:
            c.execute('''INSERT INTO edge_bff.subscriptions(user_id, plan_key, status, provider)
                SELECT %s, plan_key, 'active', 'test' FROM edge_bff.plan_capabilities WHERE capability_key = '*' AND value = 'true'::jsonb''',
                      (row['user_id'],))
    return dict(row)


def with_monitor(store, user):
    """EXEC-MU-ACCOUNTS Phase 3a (decision D1): the Monitor is in no plan but the admin's; a test about a plain account's
    Monitor rows gives it the Monitor by overrides (view, chat, every model)."""
    with store.connect() as c:
        for key, value in (('monitor.view', 'true'), ('monitor.chat', 'true'), ('monitor.model', '{"all": true}')):
            c.execute('''INSERT INTO edge_bff.user_capability_overrides(user_id, capability_key, value, reason)
                VALUES (%s, %s, %s::jsonb, 'test: the Monitor for a plain account')''', (user['user_id'], key, value))
    return user


def test_owner_key_is_immutable_and_reserved_keys_are_never_issued(settings, store):
    AccountStore(store).seed(settings.owner, settings.login, settings.password_verifier, False)
    user = make_user(store, 'alice', 'alice-password')
    assert accounts_module.OWNER_KEY.fullmatch(user['owner_key'])
    with pytest.raises(psycopg.errors.CheckViolation, match='never change'):
        db(store, "UPDATE edge_bff.users SET owner_key=%s WHERE user_id=%s", new_owner_key(), user['user_id'])
    with pytest.raises(psycopg.errors.CheckViolation, match='never change'):
        db(store, "UPDATE edge_bff.users SET owner_key='x' WHERE owner_key=%s", settings.owner)
    for key in ('default', 'someone-else', 'golden-1', 'test-runner'):
        with pytest.raises(psycopg.errors.CheckViolation, match='reserved'):
            db(store, "INSERT INTO edge_bff.users(owner_key, username, email) VALUES (%s,'bob','b@x.io')", key)
    with pytest.raises(psycopg.errors.CheckViolation, match='only the seed'):
        db(store, "INSERT INTO edge_bff.users(owner_key, username, email) VALUES ('edge-private','bob','b@x.io')")
    for username in ('admin', 'root', 'support', 'edge', 'system', 'Bob', 'ab', 'bob-1', 'x' * 31):
        with pytest.raises(psycopg.errors.CheckViolation):
            db(store, "INSERT INTO edge_bff.users(owner_key, username, email) VALUES (%s,%s,'b@x.io')", new_owner_key(), username)
    with pytest.raises(psycopg.errors.CheckViolation):
        db(store, "INSERT INTO edge_bff.users(owner_key, username, email) VALUES (%s,'bob','B@x.io')", new_owner_key())
    with pytest.raises(psycopg.errors.CheckViolation):                    # a generated account has an email
        db(store, "INSERT INTO edge_bff.users(owner_key, username) VALUES (%s,'bob')", new_owner_key())
    with pytest.raises(psycopg.errors.UniqueViolation):
        # one account per address (several pending registrations may name it: migration 20261117_002)
        db(store, "INSERT INTO edge_bff.users(owner_key, username, email, status) VALUES (%s,'bob','alice@example.com','active')",
           new_owner_key())
    # names and status may change; the other columns follow their rules
    assert db(store, "UPDATE edge_bff.users SET first_name='Alice', status='disabled' WHERE user_id=%s", user['user_id']) == 1
    with pytest.raises(psycopg.errors.CheckViolation):
        db(store, "UPDATE edge_bff.users SET phone_e164='0812' WHERE user_id=%s", user['user_id'])


def test_the_runtime_role_holds_exactly_the_migrated_grants(store, settings):
    """As edge_bff_runtime: the seed and a code row are written (the sequences by USAGE), the audit cannot be changed."""
    with store.connect() as c:
        c.execute('SET LOCAL ROLE edge_bff_runtime')
        user = c.execute("""INSERT INTO edge_bff.users(owner_key, username, email, status) VALUES (%s,'carol','c@x.io','pending')
            RETURNING user_id""", (new_owner_key(),)).fetchone()['user_id']
        c.execute("""INSERT INTO edge_bff.email_codes(purpose, user_id, code_hash, expires_at)
            VALUES ('register', %s, %s, now() + interval '300 seconds')""", (user, 'a' * 64))
        c.execute("INSERT INTO edge_bff.admin_audit(actor_user_id, action, target_user_id) VALUES (%s,'user.disable',%s)",
                  (user, user))
    for sql in ('UPDATE edge_bff.admin_audit SET reason = %s', 'DELETE FROM edge_bff.admin_audit WHERE reason = %s',
                'DELETE FROM edge_bff.email_outbox WHERE to_email = %s', 'TRUNCATE edge_bff.users'):
        with store.connect() as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute('SET LOCAL ROLE edge_bff_runtime')
            c.execute(sql, ('x',) if '%s' in sql else None)
    with store.connect() as c, pytest.raises(psycopg.errors.CheckViolation):        # a code lives exactly 300 s
        c.execute("""INSERT INTO edge_bff.email_codes(purpose, user_id, code_hash, expires_at)
            VALUES ('reset', %s, %s, now() + interval '600 seconds')""", (user, 'b' * 64))
    with store.connect() as c, pytest.raises(psycopg.errors.UniqueViolation):       # one live code per user and purpose
        c.execute("""INSERT INTO edge_bff.email_codes(purpose, user_id, code_hash, expires_at)
            VALUES ('register', %s, %s, now() + interval '300 seconds')""", (user, 'c' * 64))


def test_the_migration_refuses_a_second_run(database):
    migration = Path(__file__).resolve().parents[3] / 'database/migrations/20261116_003_edge_bff_accounts_users.sql'
    with psycopg.connect(database, autocommit=True) as conn:
        with pytest.raises(psycopg.errors.RaiseException, match='reconcile before applying'):
            conn.execute(migration.read_text())


# ---- switch on --------------------------------------------------------------------------------------------------------

class OwnerOrc(FakeOrc):
    """FakeOrc that records the owner of each read."""
    def __init__(self):
        super().__init__()
        self.owners = []

    def models(self, owner):
        self.owners.append(('models', owner))
        return super().models(owner)

    def messages(self, owner, conv, *args, **kwargs):
        self.owners.append(('messages', owner))
        return super().messages(owner, conv, *args, **kwargs)


@pytest.fixture
def workers():
    bt, sc = FakeBacktestWorker(), FakeScreenerWorker()
    yield bt, sc
    bt.close()
    sc.close()


@pytest.fixture
def on(settings, store, workers):
    bt, sc = workers
    with psycopg.connect(settings.database_url) as c:
        c.execute('TRUNCATE edge_bff.backtest_results, edge_bff.backtest_trials, edge_bff.backtest_jobs')
    return dataclasses.replace(settings, multiuser=True, code_secret='c' * 40, mfa_key='m' * 40, backtest_worker_url=bt.url, backtest_worker_key=BACKTEST_KEY,
                               backtest_timeout_seconds=30, backtest_max_result_bytes=2 ** 20,
                               screener_worker_url=sc.url, screener_worker_key=SCREENER_KEY, screener_timeout_seconds=20)


def sign_in(c, login_name, password):
    r = c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': login_name, 'password': password})
    if r.status_code == 403 and r.json()['error']['code'] == 'MFA_REQUIRED':     # an admin: the pending session
        return {**ORIGIN, 'X-CSRF-Token': r.json()['error']['details']['csrf_token']}
    assert r.status_code == 200, r.text
    return {**ORIGIN, 'X-CSRF-Token': r.json()['csrf_token']}


def test_switch_on_sign_in_reads_the_accounts(on, store):
    orc = OwnerOrc()
    app = create_app(on, store, orc)
    with TestClient(app) as c:
        seeded = db(store, 'SELECT username FROM edge_bff.users')
        assert seeded == [{'username': 'owner'}]
        alice = with_monitor(store, make_user(store, 'alice', 'alice-password'))
        assert c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'alice', 'password': 'wrong'}).status_code == 401
        assert c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'nobody', 'password': 'x'}).status_code == 401
        sign_in(c, 'ALICE@example.com', 'alice-password')                 # the email, any case
        answer = c.get('/api/v1/auth/session').json()
        assert (answer['login'], answer['username']) == ('alice', 'alice')
        assert answer['access']['role'] == 'user' and '*' not in answer['access']['capabilities'] and 'admin.access' not in answer['access']['capabilities'] and answer['access']['next'] is None
        assert answer['access']['version'].startswith('db-')
        c.get('/api/v1/models')
        assert orc.owners[-1] == ('models', alice['owner_key'])
        row = db(store, 'SELECT user_id, created_ip_hash, last_seen_at FROM edge_bff.sessions WHERE revoked_at IS NULL')
        assert row[0]['user_id'] == alice['user_id'] and len(row[0]['created_ip_hash']) == 64 and row[0]['last_seen_at']
        assert db(store, 'SELECT last_sign_in_at FROM edge_bff.users WHERE user_id=%s', alice['user_id'])[0]['last_sign_in_at']
        # user #1 (admin) signs in with today's login; admin routes wait for MFA (B1b), the rest works
        sign_in(c, 'owner', 'local-test-password')
        access = c.get('/api/v1/auth/session').json()['access']
        assert (access['role'], access['capabilities'], access['mfa_ok'], access['next']) == ('admin', ['*'], False, 'mfa')
        r = c.get('/api/v1/dev/manual/steps')
        assert r.status_code == 403 and r.json()['error']['code'] == 'MFA_REQUIRED'
        db(store, "UPDATE edge_bff.sessions SET mfa_passed_at = now() WHERE revoked_at IS NULL")
        assert c.get('/api/v1/auth/session').json()['access']['mfa_ok'] is True
        # a disabled account's sessions are refused at once
        db(store, "UPDATE edge_bff.users SET status='disabled' WHERE username='owner'")
        assert c.get('/api/v1/auth/session').status_code == 401
        assert c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'owner', 'password': 'local-test-password'}).status_code == 401


def test_switch_on_idle_timeout_and_the_session_limit(on, store):
    app = create_app(dataclasses.replace(on, session_idle_seconds=600), store, FakeOrc())
    with TestClient(app) as c:
        make_user(store, 'alice', 'alice-password')
        sign_in(c, 'alice', 'alice-password')
        assert c.get('/api/v1/auth/session').status_code == 200
        db(store, "UPDATE edge_bff.sessions SET last_seen_at = now() - interval '601 seconds', created_at = now() - interval '1 hour'")
        assert c.get('/api/v1/auth/session').status_code == 401              # idle beyond EDGE_SESSION_IDLE_SECONDS
        db(store, "UPDATE edge_bff.sessions SET last_seen_at = now() - interval '599 seconds'")
        assert c.get('/api/v1/auth/session').status_code == 200
        # last_seen_at is written at most once per 60 s
        before = db(store, 'SELECT last_seen_at FROM edge_bff.sessions')[0]['last_seen_at']
        c.get('/api/v1/auth/session')
        assert db(store, 'SELECT last_seen_at FROM edge_bff.sessions')[0]['last_seen_at'] == before
        # at most MAX_SESSIONS live sessions per account: the oldest are revoked
        clients = [TestClient(app) for _ in range(MAX_SESSIONS + 1)]
        for other in clients:
            sign_in(other, 'alice', 'alice-password')
        assert db(store, 'SELECT count(*) AS n FROM edge_bff.sessions WHERE revoked_at IS NULL')[0]['n'] == MAX_SESSIONS
        assert c.get('/api/v1/auth/session').status_code == 401                   # the oldest
        assert clients[0].get('/api/v1/auth/session').status_code == 401
        assert all(x.get('/api/v1/auth/session').status_code == 200 for x in clients[1:])


def test_the_session_limit_holds_when_sessions_are_made_at_once(on, store):
    user = make_user(store, 'alice', 'alice-password')
    accounts = AccountStore(store)
    threads = [threading.Thread(target=accounts.create_session, args=(token_hash(str(i)), user, 3600)) for i in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert db(store, 'SELECT count(*) AS n FROM edge_bff.sessions WHERE revoked_at IS NULL')[0]['n'] == MAX_SESSIONS


def test_two_users_see_none_of_each_others_rows(on, store, workers):
    """CONTRACT.md 13.3: user B gets 404 on every owned kind of user A, and B's lists are empty."""
    orc = OwnerOrc()
    app = create_app(on, store, orc)
    with TestClient(app) as a:
        b = TestClient(app)
        alice, bob = make_user(store, 'alice', 'alice-password'), make_user(store, 'bob_b', 'bob-password')
        # Phase 3a (CONTRACT.md 8b): the tabs need their capabilities, so both hold the plan that grants backtest.run
        # (found by data) and the Monitor by override (admin only in the seed, decisions D1 and D8)
        plan = db(store, '''SELECT plan_key FROM edge_bff.plan_capabilities WHERE capability_key = 'backtest.run'
            AND plan_key NOT IN (SELECT plan_key FROM edge_bff.plan_capabilities WHERE capability_key = '*' AND value = 'true'::jsonb)''')[0]['plan_key']
        for user in (alice, bob):
            db(store, '''INSERT INTO edge_bff.subscriptions(user_id, plan_key, status, provider) VALUES (%s, %s, 'active', 'test')''',
               user['user_id'], plan)
            for key, value in (('monitor.view', 'true'), ('monitor.chat', 'true'), ('monitor.model', '{"all": true}')):
                db(store, '''INSERT INTO edge_bff.user_capability_overrides(user_id, capability_key, value, reason)
                    VALUES (%s, %s, %s::jsonb, 'test')''', user['user_id'], key, value)
        ha, hb = sign_in(a, 'alice', 'alice-password'), sign_in(b, 'bob_b', 'bob-password')
        lay, pre = 'lay_' + 'a' * 32, 'ipr_' + 'a' * 32
        # A's rows of every owned kind, made through the routes
        run = a.post('/api/v1/runs', headers=ha, json={'message': 'Explain GOTO', 'submission_key': 'one'}).json()
        conv = 'conv_' + 'c' * 32
        db(store, "INSERT INTO edge_bff.conversation_ui(owner_key, conversation_id, title) VALUES (%s,%s,'Mine')",
           alice['owner_key'], conv)
        assert a.put(f'/api/v1/terminal/layouts/{lay}', headers=ha, json={'name': 'Swing', 'state': {'ml.tf': 'D'}}).status_code == 201
        assert a.put(f'/api/v1/terminal/presets/{pre}', headers=ha, json={'name': 'P', 'def_id': 'FL03', 'config': PRESET_CONFIG}).status_code == 201
        line = {'id': 'd1', 'kind': 'trend-line', 'points': [{'time': '2026-10-01', 'price': 58.6}, {'time': '2026-11-03', 'price': 61.2}]}
        assert a.put('/api/v1/terminal/drawings/BBRI/chart', headers=ha, json={'drawings': [line]}).status_code in (200, 201)
        made = a.post('/api/v1/watchlist/lists', headers=ha, json={'name': 'Banks', 'tickers': ['BBCA']})
        assert made.status_code == 201, made.text
        list_id = made.json()['list']['id']
        a.headers_for = ha
        assert a.put(f'/api/v1/screener/items/{item_id(1)}', headers=ha, json=screen_item()).status_code == 200
        assert a.put('/api/v1/screener/watchlist/BBCA', headers=ha).status_code == 204
        bt = a.post('/api/v1/backtests', headers=ha, json={**single(), 'client_request_id': 'mine'})
        assert bt.status_code == 202, bt.text
        assert a.put('/api/v1/preferences/ml.my', headers=ha, json={'value': {'x': 1}, 'version': None}).status_code == 201

        # B: every item of A is not found, every list is empty
        rid, bid = run['request_id'], bt.json()['request_id']
        for path in (f'/api/v1/runs/{rid}', f'/api/v1/runs/{rid}/progress', f'/api/v1/runs/{rid}/events',
                     f'/api/v1/conversations/{conv}/messages', f'/api/v1/terminal/layouts/{lay}',
                     f'/api/v1/backtests/{bid}', f'/api/v1/backtests/{bid}/result'):
            assert b.get(path).status_code == 404, path
        for method, path in (('POST', f'/api/v1/runs/{rid}/stop'), ('DELETE', f'/api/v1/terminal/layouts/{lay}'),
                             ('DELETE', f'/api/v1/terminal/presets/{pre}'), ('DELETE', '/api/v1/terminal/drawings/BBRI/chart'),
                             ('PATCH', f'/api/v1/watchlist/lists/{list_id}'), ('DELETE', f'/api/v1/screener/items/{item_id(1)}'),
                             ('PATCH', f'/api/v1/conversations/{conv}/preferences'), ('DELETE', f'/api/v1/conversations/{conv}')):
            r = b.request(method, path, headers=hb, json={'name': 'Mine now'} if 'watchlist' in path else {'title': 'x'} if 'preferences' in path else None)
            assert r.status_code == 404, (method, path, r.status_code, r.text)
        assert b.get('/api/v1/runs').json() == {'active': None}
        assert b.get('/api/v1/conversations').json()['items'] == []
        assert b.get('/api/v1/terminal/layouts').json()['layouts'] == []
        assert b.get('/api/v1/terminal/presets').json()['presets'] == []
        assert b.get('/api/v1/terminal/drawings?ticker=BBRI').json()['sets'] == []
        assert b.get('/api/v1/watchlist/lists').json()['lists'] == []
        assert b.get('/api/v1/screener/items').json()['items'] == []
        assert b.get('/api/v1/screener/watchlist').json()['tickers'] == []
        assert b.get('/api/v1/backtests').json()['items'] == []
        assert b.get('/api/v1/preferences').json()['preferences'] == {}
        # A still has everything, and the services were told the principal's owner
        assert a.get(f'/api/v1/terminal/layouts/{lay}').status_code == 200
        assert len(a.get('/api/v1/backtests').json()['items']) == 1
        assert a.get(f'/api/v1/conversations/{conv}/messages').status_code in (200, 410)
        assert ('messages', alice['owner_key']) in orc.owners and all(o != bob['owner_key'] for k, o in orc.owners)
        screener_owners = {call['owner'] for call in workers[1].calls if call['path'] != '/health'}
        import hashlib
        import hmac
        assert screener_owners == {hmac.new(SCREENER_KEY.encode(), alice['owner_key'].encode(), hashlib.sha256).hexdigest()[:16]}
        assert {r['owner_key'] for r in db(store, 'SELECT owner_key FROM edge_bff.backtest_jobs')} == {alice['owner_key']}
        # the queued backtest is dispatched with its owner's rights now (a user: none)
        run_next(a)
        assert workers[0].posted('/v1/jobs')[-1]['body']['context']['rights'] == []


def test_the_backtest_loop_reads_the_owners_account_when_it_dispatches(on, store):
    app = create_app(on, store, FakeOrc())
    with TestClient(app):
        admin = make_user(store, 'adm', 'admin-password', role='admin')
        user = make_user(store, 'usr', 'user-password')
        auth = Auth(on, store)
        assert rights_of(auth.owner_principal(admin['owner_key'])) == ['flow_point_in_time']
        assert rights_of(auth.owner_principal(user['owner_key'])) == []
        assert rights_of(auth.owner_principal('unknown-owner')) == []
        db(store, "UPDATE edge_bff.users SET status='disabled' WHERE user_id=%s", admin['user_id'])
        assert rights_of(auth.owner_principal(admin['owner_key'])) == []


def test_need_and_admin_dependencies(on, store):
    from fastapi import Depends
    app = create_app(on, store, FakeOrc())
    auth = app.state.auth

    @app.get('/api/v1/example/needs')
    async def needs(p: Principal = Depends(auth.need('example.thing'))):
        return {'owner': p.owner_key}

    @app.post('/api/v1/example/admin')
    async def admin_route(p: Principal = Depends(auth.admin(write=True))):
        return {'ok': True}

    with TestClient(app) as c:
        make_user(store, 'alice', 'alice-password')
        h = sign_in(c, 'alice', 'alice-password')
        r = c.get('/api/v1/example/needs')
        assert r.status_code == 403 and r.json()['error']['code'] == 'CAPABILITY_REQUIRED'
        assert r.json()['error']['details']['capability'] == 'example.thing'
        assert c.post('/api/v1/example/admin', headers=h).json()['error']['code'] == 'CAPABILITY_REQUIRED'
        assert c.post('/api/v1/example/admin', headers=ORIGIN).json()['error']['code'] == 'CSRF_INVALID'
        make_user(store, 'boss', 'boss-password', role='admin')
        h = sign_in(c, 'boss', 'boss-password')
        # a pending admin session reaches no route but the session and the MFA steps
        assert c.get('/api/v1/example/needs').json()['error']['code'] == 'MFA_REQUIRED'
        assert c.post('/api/v1/example/admin', headers=h).json()['error']['code'] == 'MFA_REQUIRED'
        db(store, "UPDATE edge_bff.sessions SET mfa_passed_at = now() WHERE revoked_at IS NULL")
        assert c.get('/api/v1/example/needs').status_code == 200
        assert c.post('/api/v1/example/admin', headers=h).json() == {'ok': True}


# ---- preferences ------------------------------------------------------------------------------------------------------

@pytest.fixture
def signed(settings, store):
    with TestClient(create_app(settings, store, FakeOrc())) as c:
        c.h = login(c)
        yield c


def test_preferences_are_written_with_an_optimistic_version(signed):
    c = signed
    assert c.get('/api/v1/preferences').json() == {'preferences': {}, 'limits': preferences_module.LIMITS}
    r = c.put('/api/v1/preferences/ml.my', headers=c.h, json={'value': [{'id': 'm1'}], 'version': None})
    assert r.status_code == 201 and r.json()['version'] == 1 and r.json()['value'] == [{'id': 'm1'}]
    r = c.put('/api/v1/preferences/ml.my', headers=c.h, json={'value': [{'id': 'm2'}], 'version': 1})
    assert r.status_code == 200 and r.json()['version'] == 2
    stale = c.put('/api/v1/preferences/ml.my', headers=c.h, json={'value': [], 'version': 1})   # another device wrote 2
    assert stale.status_code == 409
    error = stale.json()['error']
    assert error['code'] == 'PREFERENCE_CONFLICT' and error['message']
    assert error['details']['current']['value'] == [{'id': 'm2'}] and error['details']['current']['version'] == 2
    again = c.put('/api/v1/preferences/ml.my', headers=c.h, json={'value': 'x'})          # a create over an existing key
    assert again.status_code == 409
    assert c.put('/api/v1/preferences/edge-model-choice', headers=c.h, json={'value': {'m': 'x'}, 'version': 3}).status_code == 409
    got = c.get('/api/v1/preferences').json()['preferences']
    assert set(got) == {'ml.my'} and got['ml.my']['version'] == 2
    # the write needs CSRF and a session
    assert c.put('/api/v1/preferences/ml.my', headers=ORIGIN, json={'value': 1, 'version': 2}).status_code == 403


@pytest.mark.parametrize('key,body,field', [
    ('bad key', {'value': 1}, 'key'), ('.x', {'value': 1}, 'key'), ('k' * 65, {'value': 1}, 'key'),
    ('ok', {'version': 1}, 'body'), ('ok', {'value': 1, 'extra': 2}, 'body'), ('ok', {'value': 1, 'version': 0}, 'version'),
    ('ok', {'value': 1, 'version': True}, 'version'), ('ok', {'value': 'a\u0000b'}, 'value')])
def test_a_preference_is_refused_by_field(signed, key, body, field):
    r = signed.put(f'/api/v1/preferences/{key}', headers=signed.h, json=body)
    assert r.status_code in (404, 422), r.text
    if r.status_code == 422:
        assert r.json()['error']['code'] == 'INVALID_INPUT' and r.json()['error']['details']['fields'] == [field]


def test_preference_limits(signed, monkeypatch):
    c = signed
    big = 'x' * 70000
    r = c.put('/api/v1/preferences/big', headers=c.h, json={'value': big})
    assert r.status_code == 422 and r.json()['error']['details']['limit'] == 'value_bytes'
    monkeypatch.setattr(preferences_module, 'KEYS', 2)
    for n in range(2):
        assert c.put(f'/api/v1/preferences/k{n}', headers=c.h, json={'value': n}).status_code == 201
    r = c.put('/api/v1/preferences/k9', headers=c.h, json={'value': 9})
    assert r.status_code == 422 and r.json()['error']['details']['limit'] == 'keys'
    assert c.put('/api/v1/preferences/k1', headers=c.h, json={'value': 5, 'version': 1}).status_code == 200   # a replace
    monkeypatch.setattr(preferences_module, 'TOTAL_BYTES', 10)
    r = c.put('/api/v1/preferences/k1', headers=c.h, json={'value': 'y' * 20, 'version': 2})
    assert r.status_code == 422 and r.json()['error']['details']['limit'] == 'total_bytes'


# ---- the route walk and the login's grants ------------------------------------------------------------------------------

def test_the_route_walk_sees_need_and_admin_and_refuses_a_write_on_need_without_csrf(on, store):
    from fastapi import Depends
    from test_route_table import configured, problems
    app = create_app(configured(on), store, FakeOrc())
    auth = app.state.auth
    assert problems(app) == []

    @app.get('/api/v1/example/read')
    async def read(p: Principal = Depends(auth.need('example.read'))):
        return {}

    @app.post('/api/v1/example/write')
    async def write_ok(p: Principal = Depends(auth.admin(write=True))):
        return {}
    assert problems(app) == []

    @app.post('/api/v1/example/unsafe')
    async def unsafe(p: Principal = Depends(auth.need('example.write'))):
        return {}
    assert [f for f in problems(app) if '/api/v1/example/unsafe' in f and 'CSRF' in f]


def test_the_provisioned_login_reaches_the_account_tables_with_their_grants(database, monkeypatch):
    import importlib.util
    import os
    import secrets
    from urllib.parse import urlsplit, urlunsplit
    helper = Path(__file__).resolve().parents[3] / 'scripts/provision_edge_bff_login.py'
    spec = importlib.util.spec_from_file_location('edge_provision_accounts', helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv('DATABASE_URL', database)
    monkeypatch.setenv('EDGE_DB_PASSWORD', secrets.token_hex(24))
    p = urlsplit(database)
    restricted = urlunsplit((p.scheme, 'edge_bff_login:' + os.environ['EDGE_DB_PASSWORD'] + '@' + p.netloc.split('@')[-1],
                             p.path, p.query, p.fragment))
    try:
        module.main()
        with psycopg.connect(restricted) as conn:
            user = conn.execute("""INSERT INTO edge_bff.users(owner_key, username, email) VALUES (%s,'dave','d@x.io')
                RETURNING user_id""", (new_owner_key(),)).fetchone()[0]
            conn.execute("INSERT INTO edge_bff.admin_audit(action, target_user_id) VALUES ('user.enable', %s)", (user,))
            conn.execute("INSERT INTO edge_bff.user_preferences(owner_key, pref_key, value) VALUES ('o','k','1')")
            conn.rollback()
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute("UPDATE edge_bff.admin_audit SET reason='x'")
        for grant, revoke in (('GRANT UPDATE ON edge_bff.admin_audit TO edge_bff_runtime',
                               'REVOKE UPDATE ON edge_bff.admin_audit FROM edge_bff_runtime'),
                              ('GRANT UPDATE ON SEQUENCE edge_bff.users_user_id_seq TO edge_bff_runtime',
                               'REVOKE UPDATE ON SEQUENCE edge_bff.users_user_id_seq FROM edge_bff_runtime')):
            with psycopg.connect(database, autocommit=True) as conn:
                conn.execute(grant)
            with pytest.raises(RuntimeError, match='Unexpected EDGE'):
                module.main()
            with psycopg.connect(database, autocommit=True) as conn:
                conn.execute(revoke)
        module.main()
    finally:
        with psycopg.connect(database, autocommit=True) as conn:
            conn.execute('DROP OWNED BY edge_bff_login')
            conn.execute('DROP ROLE edge_bff_login')
