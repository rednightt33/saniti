"""EXEC-MU-ACCOUNTS fix round, track guest (verification/edge_multiuser/fix_round/guest.md): the guest principal, the
pre-launch mode of the live site and the test-account mark (edge-bff's side).

- A visitor without an account reaches the Terminal's data relay and the catalogs with the guest plan's grants, read
  from the catalog on every request (a change of the plan's rows changes what guests see, no code); every other route
  answers 401 UNAUTHENTICATED; the guest's calls name the guest owner and a visitor key (an HMAC of the client address,
  never the address) to terminal-api; no readable client address, no guest (fail closed); guests never exist with the
  switch off.
- The pre-launch mode closes registration and lets only the admin and the accounts marked as test accounts sign in;
  the mark changes only beside its audit row (migration 20261119_070), which scripts/edge_test_account.py writes.
"""
import dataclasses
import json
import os
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import principal as principal_module, terminal_access
from app.config import BETA, LIVE, Settings
from app.main import create_app
from conftest import FakeOrc
from test_edge import ORIGIN
from test_principal import db, make_user, on, sign_in, workers  # noqa: F401 - the fixtures
from test_terminal_access import FakeApi, URL, KEY, api, sent_caps, subscribe, terminal_calls  # noqa: F401

ROOT = Path(__file__).resolve().parents[3]
MIGRATION = ROOT / 'database/migrations/20261119_070_edge_bff_guest_plan_and_test_accounts.sql'
# Railway's edge sends "<client>, <edge node>" (ERRORS M512, the probe of 2026-11-20); the client is TEST-NET-3
VISITOR = {'x-forwarded-for': '203.0.113.7, 152.233.40.1'}
OTHER_VISITOR = {'x-forwarded-for': '198.51.100.9, 203.0.113.8, 152.233.40.2'}   # a hop the client wrote, the client, the edge


@pytest.fixture
def guests(on, api):
    """The switch on with guests, as the live site has them (a local beta: config.validate takes it locally)."""
    return dataclasses.replace(on, terminal_url=URL, terminal_proxy_key=KEY, guests_enabled=True)


def guest_plan(store):
    return db(store, 'SELECT plan_key FROM edge_bff.plans WHERE for_guests')[0]['plan_key']


# ---- the guest principal ------------------------------------------------------------------------------------------

def test_a_visitor_reads_bbca_and_the_whole_ticker_list_and_is_refused_another_ticker(guests, store):
    with TestClient(create_app(guests, store, FakeOrc())) as c:
        r = c.get('/api/v1/auth/guest', headers=VISITOR)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body['visitor'] is True and body['authenticated'] is False and body['csrf_token'] == ''
        assert body['owner_key'] is None and body['access']['owner_key'] is None
        assert body['access']['capabilities'] == ['terminal.view'] and body['access']['limits']['terminal.tickers'] == ['BBCA']
        assert body['access']['plan'] == guest_plan(store) and r.headers['x-edge-entitlements'].startswith('db-')
        # BBCA's chart and the ticker list go to terminal-api under the guest owner, with the visitor's key
        for method, path, payload in (('GET', 'reference/tickers', None), ('GET', 'manifest/BBCA', None),
                                      ('POST', 'bundle', {'ticker': 'BBCA', 'datasets': ['price'], 'packs': True})):
            r = c.request(method, f'/api/terminal/v1/{path}', headers={**VISITOR, **ORIGIN}, json=payload)
            assert r.status_code == 200, (path, r.text)
            call = terminal_calls()[-1]
            caps = sent_caps(call)
            assert call['headers'][terminal_access.OWNER_HEADER] == principal_module.GUEST_OWNER
            assert caps['admin'] is False and caps['tickers'] == ['BBCA'] and caps['datasets'] == ['price']
            assert caps['history_days'] == 730 and caps['quota'] == {}     # terminal-api's defaults, per visitor
            client = call['headers'][terminal_access.CLIENT_HEADER]
            assert terminal_access.CLIENT.fullmatch(client) and '203.0.113.7' not in json.dumps(call['headers'])
        # another ticker: CAPABILITY_REQUIRED before terminal-api (the page opens the sign-in box for a guest)
        n = len(FakeApi.calls)
        r = c.post('/api/terminal/v1/bundle', headers={**VISITOR, **ORIGIN}, json={'ticker': 'BBRI', 'datasets': ['price']})
        assert r.status_code == 403 and r.json()['error']['code'] == 'CAPABILITY_REQUIRED'
        assert r.json()['error']['details']['capability'] == 'terminal.tickers' and len(FakeApi.calls) == n
        # each visitor has its own key; one visitor keeps its key from call to call
        c.get('/api/terminal/v1/manifest/BBCA', headers=OTHER_VISITOR)
        assert terminal_calls()[-1]['headers'][terminal_access.CLIENT_HEADER] not in (client, '')
        c.get('/api/terminal/v1/manifest/BBCA', headers=VISITOR)
        assert terminal_calls()[-1]['headers'][terminal_access.CLIENT_HEADER] == client
        # the catalogs the Terminal reads: what the guest plan holds (no indicator yet)
        r = c.get('/api/v1/catalog/indicator', headers=VISITOR)
        assert r.status_code == 200 and r.json()['entries'] == []


def test_every_other_route_answers_401_to_a_visitor(guests, store):
    with TestClient(create_app(guests, store, FakeOrc())) as c:
        for method, path in (('GET', '/api/v1/auth/session'), ('GET', '/api/v1/preferences'),
                             ('GET', '/api/v1/terminal/layouts'), ('GET', '/api/v1/terminal/drawings?ticker=BBCA'),
                             ('GET', '/api/v1/terminal/presets'), ('GET', '/api/v1/watchlist/lists'),
                             ('GET', '/api/v1/backtests'), ('GET', '/api/v1/screener/catalog'),
                             ('GET', '/api/v1/overview/index'), ('GET', '/api/v1/runs'), ('GET', '/api/v1/models')):
            r = c.request(method, path, headers={**VISITOR, **ORIGIN})
            assert r.status_code == 401 and r.json()['error']['code'] == 'UNAUTHENTICATED', (path, r.status_code, r.text)
        assert terminal_calls() == []


def test_a_change_of_the_guest_plans_rows_changes_what_a_visitor_sees_without_code(guests, store):
    plan = guest_plan(store)
    with TestClient(create_app(guests, store, FakeOrc())) as c:
        before = c.get('/api/v1/auth/guest', headers=VISITOR).json()['access']
        assert c.post('/api/terminal/v1/bundle', headers={**VISITOR, **ORIGIN},
                      json={'ticker': 'TLKM', 'datasets': ['price']}).status_code == 403
        try:
            db(store, '''UPDATE edge_bff.plan_capabilities SET value = '["BBCA", "TLKM"]' WHERE plan_key = %s
                AND capability_key = 'terminal.tickers' ''', plan)
            db(store, '''UPDATE edge_bff.plan_capabilities SET value = '{"ids": ["I01"]}' WHERE plan_key = %s
                AND capability_key = 'terminal.indicator' ''', plan)
            after = c.get('/api/v1/auth/guest', headers=VISITOR).json()['access']
            assert after['limits']['terminal.tickers'] == ['BBCA', 'TLKM'] and after['version'] != before['version']
            r = c.post('/api/terminal/v1/bundle', headers={**VISITOR, **ORIGIN}, json={'ticker': 'TLKM', 'datasets': ['price']})
            assert r.status_code == 200 and sent_caps(terminal_calls()[-1])['tickers'] == ['BBCA', 'TLKM']
            assert [e['id'] for e in c.get('/api/v1/catalog/indicator', headers=VISITOR).json()['entries']] == ['I01']
        finally:
            db(store, '''UPDATE edge_bff.plan_capabilities SET value = '["BBCA"]' WHERE plan_key = %s
                AND capability_key = 'terminal.tickers' ''', plan)
            db(store, '''UPDATE edge_bff.plan_capabilities SET value = '{"ids": []}' WHERE plan_key = %s
                AND capability_key = 'terminal.indicator' ''', plan)


def test_a_visitor_never_holds_everything_whatever_the_guest_plans_rows_say(guests, store, caplog):
    plan = guest_plan(store)
    with TestClient(create_app(guests, store, FakeOrc())) as c:
        try:
            db(store, '''INSERT INTO edge_bff.plan_capabilities(plan_key, capability_key, value) VALUES
                (%s, '*', 'true'), (%s, 'admin.access', 'true')''', plan, plan)
            with caplog.at_level('WARNING', 'edge_bff.principal'):
                access = c.get('/api/v1/auth/guest', headers=VISITOR).json()['access']
            assert '*' not in access['capabilities'] and 'admin.access' not in access['capabilities']
            assert 'guest_capability_dropped' in caplog.text
            c.get('/api/terminal/v1/manifest/BBCA', headers=VISITOR)
            assert sent_caps(terminal_calls()[-1])['admin'] is False
            r = c.get('/api/terminal/v1/manifest/TLKM', headers=VISITOR)
            assert r.status_code == 403
        finally:
            db(store, "DELETE FROM edge_bff.plan_capabilities WHERE plan_key = %s AND capability_key IN ('*', 'admin.access')", plan)


def test_no_readable_client_address_means_no_guest(guests, store):
    """Fail closed: a request that did not pass Railway's edge (no X-Forwarded-For) or whose client hop (the one left of
    the edge node's, ERRORS M512) is not an address gets no guest principal; the socket peer counts only on a developer
    machine."""
    # the test client's socket peer is 'testclient', not an address: even locally it gives no guest
    with TestClient(create_app(guests, store, FakeOrc())) as c:
        for headers in ({}, {'x-forwarded-for': 'not-an-address'}, {'x-forwarded-for': 'unknown, 152.233.40.1'}):
            r = c.get('/api/terminal/v1/manifest/BBCA', headers=headers)
            assert r.status_code == 401 and r.json()['error']['code'] == 'UNAUTHENTICATED', (headers, r.text)
        assert terminal_calls() == []
    from starlette.requests import Request
    request = lambda h, peer='127.0.0.1': Request({'type': 'http', 'headers': [(k.encode(), v.encode()) for k, v in h.items()],
                                                  'client': (peer, 5000)})
    assert principal_module.client_of(request({'x-forwarded-for': '198.51.100.9, 203.0.113.7, 152.233.40.1'})) == '203.0.113.7'
    assert principal_module.client_of(request({})) is None
    assert principal_module.client_of(request({}), local=True) == '127.0.0.1'
    assert principal_module.client_of(request({'x-forwarded-for': 'junk'}), local=True) is None


def test_guests_are_refused_with_the_switch_off_and_off_on_the_beta_by_default(settings, on, store, api):
    with pytest.raises(ValueError, match='EDGE_GUESTS=true needs EDGE_MULTIUSER=true'):
        dataclasses.replace(settings, guests_enabled=True).validate()
    assert not dataclasses.replace(settings, guests_enabled=None).guests                 # switch off: never
    assert not on.guests                                                                # a switch-on beta: off by default
    assert dataclasses.replace(on, site=LIVE).guests and dataclasses.replace(on, site=LIVE).prelaunch
    assert not dataclasses.replace(on, site=LIVE, guests_enabled=False).guests           # configurable on the live site
    with TestClient(create_app(dataclasses.replace(settings, terminal_url=URL, terminal_proxy_key=KEY), store,
                               FakeOrc())) as c:
        r = c.get('/api/terminal/v1/manifest/BBCA', headers=VISITOR)
        assert r.status_code == 401 and c.get('/api/v1/auth/guest', headers=VISITOR).status_code == 401
        assert c.get('/api/v1/auth/config').json() == {'multiuser': False}
    with TestClient(create_app(dataclasses.replace(on, terminal_url=URL, terminal_proxy_key=KEY), store,
                               FakeOrc())) as c:
        assert c.get('/api/terminal/v1/manifest/BBCA', headers=VISITOR).status_code == 401
        assert c.get('/api/v1/auth/config').json()['guests'] is False
    assert terminal_calls() == []


def test_a_signed_in_account_keeps_its_own_principal_on_the_guest_routes(guests, store):
    with TestClient(create_app(guests, store, FakeOrc())) as c:
        make_user(store, 'freda', 'freda-password')
        h = sign_in(c, 'freda', 'freda-password')
        r = c.get('/api/v1/auth/guest', headers={**h, **VISITOR})
        assert r.status_code == 200 and r.json()['visitor'] is False and r.json()['csrf_token']
        c.get('/api/terminal/v1/manifest/BBCA', headers={**h, **VISITOR})
        call = terminal_calls()[-1]
        assert call['headers'][terminal_access.OWNER_HEADER].startswith('u_')
        assert terminal_access.CLIENT_HEADER not in call['headers']
        # a write of the account still needs its CSRF token; a guest's write needs none (it has no session)
        r = c.post('/api/terminal/v1/bundle', headers={**ORIGIN, **VISITOR}, json={'ticker': 'BBCA', 'datasets': ['price']})
        assert r.status_code == 403 and r.json()['error']['code'] == 'CSRF_INVALID'
    with TestClient(create_app(guests, store, FakeOrc())) as fresh:
        r = fresh.post('/api/terminal/v1/bundle', headers={**ORIGIN, **VISITOR}, json={'ticker': 'BBCA', 'datasets': ['price']})
        assert r.status_code == 200
        r = fresh.post('/api/terminal/v1/bundle', headers={'origin': 'https://elsewhere.example', **VISITOR},
                       json={'ticker': 'BBCA', 'datasets': ['price']})
        assert r.status_code == 403 and r.json()['error']['code'] == 'ORIGIN_REJECTED'


def test_a_page_sent_visitor_key_is_refused(guests, store):
    with TestClient(create_app(guests, store, FakeOrc())) as c:
        r = c.get('/api/terminal/v1/manifest/BBCA', headers={**VISITOR, terminal_access.CLIENT_HEADER: 'a' * 32})
        assert r.status_code == 400 and r.json()['error']['code'] == 'HEADER_NOT_ALLOWED'
        assert terminal_calls() == []


def test_the_guest_owner_is_never_an_account_or_the_configured_owner(settings):
    from app.accounts import reserved_owner
    assert reserved_owner(principal_module.GUEST_OWNER)
    for change in ({'owner': principal_module.GUEST_OWNER, 'admin_owners': (principal_module.GUEST_OWNER,)},
                   {'admin_owners': (settings.owner, principal_module.GUEST_OWNER)}):
        with pytest.raises(ValueError, match='owner key of every visitor'):
            dataclasses.replace(settings, **change).validate()


# ---- the pre-launch mode ------------------------------------------------------------------------------------------

@pytest.fixture
def prelaunch(guests):
    return dataclasses.replace(guests, prelaunch_enabled=True, upgrade_contact='sales@example.com')


def test_prelaunch_closes_registration_with_a_plain_sentence(prelaunch, store):
    with TestClient(create_app(prelaunch, store, FakeOrc())) as c:
        config = c.get('/api/v1/auth/config').json()
        assert config == {'multiuser': True, 'registration': False, 'prelaunch': True, 'guests': True,
                          'upgrade_contact': 'sales@example.com',
                          # live checker S1 (stated reason): the tabs this site does not offer; none here (the beta's
                          # tabs: this harness is not the live site), ['admin', 'monitor'] on it (tests/test_live_rail.py)
                          'hidden_tabs': [], 'legal': {'privacy': None, 'terms': None}}
        for path, body in (('/api/v1/auth/register', {'username': 'newbie', 'first_name': 'New', 'last_name': 'Bie',
                                                      'email': 'newbie@example.com', 'phone': '+6281234567890',
                                                      'password': 'long enough pw', 'password_repeat': 'long enough pw'}),
                           ('/api/v1/auth/register/verify', {'email': 'newbie@example.com', 'code': '123456'}),
                           ('/api/v1/auth/code/resend', {'email': 'newbie@example.com', 'purpose': 'register'})):
            r = c.post(path, headers=ORIGIN, json=body)
            assert r.status_code == 403, (path, r.text)
            error = r.json()['error']
            assert error['code'] == 'REGISTRATION_CLOSED' and error['message'].startswith('Registration opens soon')
        assert db(store, "SELECT count(*) AS n FROM edge_bff.users WHERE status = 'pending'")[0]['n'] == 0
        assert db(store, 'SELECT count(*) AS n FROM edge_bff.email_outbox')[0]['n'] == 0
        # the reset of an account's password stays open (the test accounts set theirs with it)
        r = c.post('/api/v1/auth/password/forgot', headers=ORIGIN, json={'email': 'someone@example.com'})
        assert r.status_code == 202
        # visitors still open the Terminal (the website is open)
        assert c.get('/api/terminal/v1/manifest/BBCA', headers=VISITOR).status_code == 200


def test_prelaunch_lets_only_the_admin_and_test_accounts_sign_in(prelaunch, store):
    with TestClient(create_app(prelaunch, store, FakeOrc())) as c:
        make_user(store, 'paula', 'paula-password')                    # an account like any other: refused
        tess = make_user(store, 'tessa', 'tessa-password')
        make_user(store, 'adele', 'adele-password', role='admin')      # holds '*' by the catalog: the admin
        r = c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'paula', 'password': 'paula-password'})
        assert r.status_code == 403 and r.json()['error']['code'] == 'SIGN_IN_CLOSED', r.text
        assert 'only test accounts' in r.json()['error']['message'] and 'set-cookie' not in r.headers
        assert db(store, 'SELECT count(*) AS n FROM edge_bff.sessions')[0]['n'] == 0
        # a wrong password still answers as a wrong password
        r = c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'paula', 'password': 'wrong password'})
        assert r.status_code == 401 and r.json()['error']['code'] == 'INVALID_CREDENTIALS'
        # the admin signs in (and is asked for its second factor, as always)
        r = c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'adele', 'password': 'adele-password'})
        assert r.status_code == 403 and r.json()['error']['code'] == 'MFA_REQUIRED'
        # a test account, marked by an audited step, signs in
        with psycopg.connect(prelaunch.database_url) as conn:
            conn.execute('''INSERT INTO edge_bff.admin_audit(action, target_user_id, after, reason)
                VALUES ('account.test_mark', %s, '{"test_account": true}', 'operator: test')''', (tess['user_id'],))
            conn.execute('UPDATE edge_bff.users SET test_account = true WHERE user_id = %s', (tess['user_id'],))
        r = c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'tessa', 'password': 'tessa-password'})
        assert r.status_code == 200, r.text
    with TestClient(create_app(dataclasses.replace(prelaunch, prelaunch_enabled=False), store, FakeOrc())) as c:
        assert c.post('/api/v1/auth/sign-in', headers=ORIGIN,
                      json={'login': 'paula', 'password': 'paula-password'}).status_code == 200


def test_a_closed_accounts_right_password_never_counts_as_a_failure(prelaunch, store):
    """The live checker after the switch-on (ACC-5): in the pre-launch mode a closed account's right password is answered
    SIGN_IN_CLOSED every time (more than the 10 tries per login and address, never the rate limit), and it adds nothing
    to the account's consecutive failures, which would outlive the launch toward the lock."""
    with TestClient(create_app(prelaunch, store, FakeOrc())) as c:
        paula = make_user(store, 'paula', 'paula-password')
        for _ in range(12):
            r = c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'paula', 'password': 'paula-password'})
            assert r.status_code == 403 and r.json()['error']['code'] == 'SIGN_IN_CLOSED', r.text
        assert db(store, 'SELECT sign_in_failures FROM edge_bff.identities WHERE user_id = %s',
                  paula['user_id']) == [{'sign_in_failures': 0}]


def test_prelaunch_needs_the_switch_and_the_contact_is_one_plain_line(settings, on):
    with pytest.raises(ValueError, match='EDGE_PRELAUNCH=true needs EDGE_MULTIUSER=true'):
        dataclasses.replace(settings, prelaunch_enabled=True).validate()
    assert not dataclasses.replace(on, prelaunch_enabled=False, site=LIVE).prelaunch
    for bad in ('<a href=x>x</a>', 'line\nbreak', 'x' * 201):
        with pytest.raises(ValueError, match='EDGE_UPGRADE_CONTACT'):
            dataclasses.replace(on, upgrade_contact=bad).validate()
    dataclasses.replace(on, upgrade_contact='WhatsApp +62 812 3456 7890 or sales@example.com').validate()


def test_the_settings_read_the_three_new_variables(monkeypatch):
    base = {'EDGE_DATABASE_URL': 'postgresql://u@h/db', 'EDGE_ORC_URL': 'http://orc', 'MARKET_AI_ORC_API_KEY': 'k',
            'EDGE_OWNER': 'edge-private', 'EDGE_LOGIN': 'owner', 'EDGE_SESSION_SECRET': 's' * 40,
            'EDGE_PUBLIC_ORIGIN': 'http://localhost', 'EDGE_ENVIRONMENT': 'local', 'EDGE_SECURE_COOKIE': 'false',
            'EDGE_PASSWORD_VERIFIER': __import__('app.security', fromlist=['x']).password_verifier('pw'),
            'EDGE_MULTIUSER': 'true', 'EDGE_CODE_SECRET': 'c' * 40, 'EDGE_MFA_KEY': 'm' * 40}
    for k, v in base.items():
        monkeypatch.setenv(k, v)
    for k in ('EDGE_GUESTS', 'EDGE_PRELAUNCH', 'EDGE_UPGRADE_CONTACT', 'EDGE_SITE'):
        monkeypatch.delenv(k, raising=False)
    s = Settings.from_env()
    assert (s.site, s.guests, s.prelaunch, s.upgrade_contact) == (BETA, False, False, '')
    monkeypatch.setenv('EDGE_GUESTS', 'true')
    monkeypatch.setenv('EDGE_PRELAUNCH', 'true')
    monkeypatch.setenv('EDGE_UPGRADE_CONTACT', '  sales@example.com ')
    s = Settings.from_env()
    assert (s.guests, s.prelaunch, s.upgrade_contact) == (True, True, 'sales@example.com')
    monkeypatch.setenv('EDGE_GUESTS', 'yes')
    with pytest.raises(ValueError, match='EDGE_GUESTS is true or false'):
        Settings.from_env()


# ---- the test-account mark and its script ----------------------------------------------------------------------------

def test_the_mark_changes_only_beside_its_audit_row(database, store):
    user = make_user(store, 'markus', 'markus-password')
    with psycopg.connect(database) as conn:
        with pytest.raises(psycopg.errors.CheckViolation, match='without its audit row') as e:
            conn.execute('UPDATE edge_bff.users SET test_account = true WHERE user_id = %s', (user['user_id'],))
            conn.commit()                                                # deferred: refused at the commit
        assert e.value.diag.constraint_name == 'users_test_account_audited'
        assert 'scripts/edge_test_account.py' in e.value.diag.message_hint
        conn.rollback()
        with pytest.raises(psycopg.errors.CheckViolation):              # an audit row of another value is not its row
            conn.execute("INSERT INTO edge_bff.admin_audit(action, target_user_id, after, reason) "
                         "VALUES ('account.test_mark', %s, '{\"test_account\": false}', 'operator: wrong value')",
                         (user['user_id'],))
            conn.execute('UPDATE edge_bff.users SET test_account = true WHERE user_id = %s', (user['user_id'],))
            conn.commit()
        conn.rollback()
        conn.execute("INSERT INTO edge_bff.admin_audit(action, target_user_id, after, reason) "
                     "VALUES ('account.test_mark', %s, '{\"test_account\": true}', 'operator: right')", (user['user_id'],))
        conn.execute('UPDATE edge_bff.users SET test_account = true WHERE user_id = %s', (user['user_id'],))
        conn.commit()
    assert db(store, 'SELECT test_account FROM edge_bff.users WHERE user_id = %s', user['user_id'])[0]['test_account']


def run_script(database, *args):
    env = {**os.environ, 'DATABASE_URL': database}
    r = subprocess.run([sys.executable, str(ROOT / 'scripts/edge_test_account.py'), *args], env=env,
                       capture_output=True, text=True, timeout=60)
    return r.returncode, (json.loads(r.stdout) if r.stdout.strip() else None), r.stdout + r.stderr


def test_the_script_makes_a_test_account_for_an_address_and_a_plan_without_printing_secrets(database, store, prelaunch):
    from test_terminal_access import paid_plan
    paid = paid_plan(store)
    code, out, text = run_script(database, '--email', 'Tester.One@Example.com', '--plan', paid, '--reason', 'the user asked')
    assert code == 0 and out['outcome'] == 'created' and out['plan'] == paid and out['test_account'] is True, text
    assert 'example.com' not in text.lower() and 'scrypt' not in text and 'postgresql' not in text
    row = db(store, """SELECT u.username, u.status, u.test_account, u.email_verified_at IS NOT NULL AS verified,
            s.plan_key, s.provider, a.action, a.reason FROM edge_bff.users u
        JOIN edge_bff.subscriptions s ON s.user_id = u.user_id JOIN edge_bff.admin_audit a ON a.target_user_id = u.user_id
        WHERE u.email = 'tester.one@example.com' """)
    assert row == [{'username': 'tester_one', 'status': 'active', 'test_account': True, 'verified': True,
                    'plan_key': paid, 'provider': 'test', 'action': 'account.test_mark',
                    'reason': 'operator: the user asked'}]
    # nobody signs in before the user sets a password with "Forgot password" (a verifier no password opens)
    with TestClient(create_app(prelaunch, store, FakeOrc())) as c:
        r = c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'tester_one', 'password': 'any password at all'})
        assert r.status_code == 401
    # a second run changes nothing; another plan while one is active is refused; the default plan needs no subscription
    again = run_script(database, '--email', 'tester.one@example.com', '--plan', paid, '--reason', 'again')
    assert again[1]['outcome'] == 'marked'
    free = db(store, 'SELECT plan_key FROM edge_bff.plans WHERE is_default')[0]['plan_key']
    code, out, _ = run_script(database, '--email', 'tester.one@example.com', '--plan', free, '--reason', 'down')
    assert code == 1 and out['outcome'] == 'refused_other_subscription'
    code, out, _ = run_script(database, '--email', 'tester.two@example.com', '--plan', free, '--reason', 'the user asked')
    assert code == 0 and out['outcome'] == 'created'
    assert db(store, """SELECT count(*) AS n FROM edge_bff.subscriptions s JOIN edge_bff.users u USING (user_id)
        WHERE u.email = 'tester.two@example.com' """)[0]['n'] == 0
    # the admin's plan and the guest plan are never a test account's; --off removes the mark only
    admin_plan = db(store, "SELECT plan_key FROM edge_bff.plan_capabilities WHERE capability_key = '*' "
                           "AND value = 'true'::jsonb")[0]['plan_key']
    for plan in (admin_plan, guest_plan(store), 'no_such_plan'):
        code, out, _ = run_script(database, '--email', 'tester.three@example.com', '--plan', plan, '--reason', 'x')
        assert code == 1 and out['outcome'].startswith('refused'), (plan, out)
    code, out, _ = run_script(database, '--email', 'tester.one@example.com', '--plan', paid, '--reason', 'done', '--off')
    assert code == 0 and out['outcome'] == 'unmarked'
    assert db(store, "SELECT test_account FROM edge_bff.users WHERE email = 'tester.one@example.com'")[0]['test_account'] is False
    assert db(store, """SELECT count(*) AS n FROM edge_bff.admin_audit WHERE action = 'account.test_mark'
        AND target_user_id IN (SELECT user_id FROM edge_bff.users WHERE email LIKE 'tester.%%')""")[0]['n'] == 3


def test_the_migration_refuses_a_second_run(database):
    with psycopg.connect(database, autocommit=True) as conn:
        with pytest.raises(psycopg.errors.RaiseException, match='already applied'):
            conn.execute(MIGRATION.read_text())
