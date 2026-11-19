"""EXEC-MU-ACCOUNTS Phase 1 (CONTRACT.md sections 4, 5 and 6): registration, email codes, password reset and change,
sign-out everywhere, admin MFA, the email outbox and its sender, the Resend webhook. With the switch off every new route
answers 404 and GET /api/v1/auth/config answers {"multiuser": false}."""
import asyncio
import base64
import dataclasses
import hashlib
import hmac
import json
import logging
import threading
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app import auth_flows as flows_module
from app import mfa
from app.config import Settings
from app.mailer import EmailSender
from app.main import create_app
from app.passwords import normal_phone
from conftest import FakeOrc
from test_edge import ORIGIN, login

PASSWORD = 'a long enough password'
SECRET = 'whsec_' + base64.b64encode(b'k' * 32).decode()
NEW_ROUTES = [('POST', '/api/v1/auth/register'), ('POST', '/api/v1/auth/register/verify'),
              ('POST', '/api/v1/auth/code/resend'), ('POST', '/api/v1/auth/password/forgot'),
              ('POST', '/api/v1/auth/password/reset'), ('POST', '/api/v1/auth/password/change'),
              ('POST', '/api/v1/auth/sign-out-all'), ('POST', '/api/v1/auth/mfa/enroll'),
              ('POST', '/api/v1/auth/mfa/verify'), ('POST', '/api/v1/hooks/email/resend')]


def db(store, sql, *args):
    with store.connect() as c:
        cur = c.execute(sql, args)
        return cur.fetchall() if cur.description else cur.rowcount


@pytest.fixture
def on(settings):
    return dataclasses.replace(settings, multiuser=True, code_secret='c' * 40, mfa_key='m' * 40,
                               resend_webhook_secret=SECRET)


@pytest.fixture
def app(on, store):
    application = create_app(on, store, FakeOrc())
    application.state.auth_flows.pwned_fetch = lambda prefix: ''          # never the real API in a test
    with TestClient(application) as c:
        yield c


def register(c, email='ana@example.com', username='ana_putri', password=PASSWORD, **change):
    body = {'username': username, 'first_name': 'Ana', 'last_name': 'Putri', 'email': email, 'phone': '0812 3456 7890',
            'password': password, 'password_repeat': password, **change}
    return c.post('/api/v1/auth/register', headers=ORIGIN, json=body)


def outbox(store, email=None):
    return db(store, 'SELECT * FROM edge_bff.email_outbox' + (' WHERE to_email=%s' if email else '') + ' ORDER BY outbox_id',
              *([email] if email else []))


def last_code(store, email):
    rows = [r for r in outbox(store, email) if r['purpose'] in ('register', 'reset')]
    return rows[-1]['payload']['mask'][0]


def cooldown_over(store):
    db(store, "UPDATE edge_bff.email_outbox SET created_at = created_at - interval '61 seconds'")


def hour_over(store):
    """An hour has passed for the per-address registration limit (one new registration email per hour, N4)."""
    cooldown_over(store)
    db(store, "UPDATE edge_bff.auth_throttle SET window_start = window_start - interval '61 minutes' WHERE scope='send_email'")


def verify(c, code, email='ana@example.com', **extra):
    return c.post('/api/v1/auth/register/verify', headers=ORIGIN, json={'email': email, 'code': code, **extra})


def make_account(c, store, email='ana@example.com', username='ana_putri'):
    assert register(c, email, username).status_code == 202
    r = verify(c, last_code(store, email), email)
    assert r.status_code == 200, r.text
    return r


def error_code(r):
    return r.json()['error']['code']


# ---- the switch -------------------------------------------------------------------------------------------------------

def test_switch_off_every_new_route_answers_404_and_config_says_so(settings, store):
    with TestClient(create_app(settings, store, FakeOrc())) as c:
        assert c.get('/api/v1/auth/config').json() == {'multiuser': False}
        for method, path in NEW_ROUTES:
            assert c.request(method, path, headers=ORIGIN, json={}).status_code == 404, path
        h = login(c)
        for method, path in NEW_ROUTES:
            r = c.request(method, path, headers=h, json={})
            assert r.status_code == 404 and error_code(r) == 'NOT_FOUND', path
        assert db(store, 'SELECT count(*) AS n FROM edge_bff.email_outbox')[0]['n'] == 0
        for page in ('/register', '/verify', '/forgot', '/reset', '/mfa', '/login'):
            r = c.get(page)
            assert r.status_code == 200 and r.headers['content-type'].startswith('text/html'), page


def test_config_with_the_switch_on(app):
    assert app.get('/api/v1/auth/config').json() == {'multiuser': True}


def test_the_settings_need_their_secrets_only_with_the_switch_on(settings):
    dataclasses.replace(settings).validate()                                     # off: nothing new is required
    for change, words in [({'multiuser': True}, 'EDGE_CODE_SECRET'),
                          ({'multiuser': True, 'code_secret': 'c' * 40}, 'EDGE_MFA_KEY'),
                          ({'code_secret': 'short'}, 'EDGE_CODE_SECRET'),
                          ({'email_mode': 'smtp'}, 'EDGE_EMAIL_MODE'),
                          ({'email_mode': 'resend', 'email_from': 'EDGE <a@b.io>'}, 'RESEND_API_KEY'),
                          ({'email_mode': 'resend', 'resend_api_key': 're_x'}, 'EDGE_EMAIL_FROM'),
                          ({'resend_webhook_secret': 'plain'}, 'RESEND_WEBHOOK_SECRET'),
                          ({'multiuser': True, 'code_secret': 'c' * 40, 'mfa_key': 'm' * 40, 'environment': 'prod'},
                           'EDGE_EMAIL_MODE=log is for')]:
        with pytest.raises(ValueError, match=words):
            dataclasses.replace(settings, **change).validate()
    dataclasses.replace(settings, multiuser=True, code_secret='c' * 32, mfa_key='m' * 32, email_mode='resend',
                        resend_api_key='re_x', email_from='EDGE <no-reply@mail.example.com>').validate()


def test_settings_read_from_the_environment(monkeypatch):
    for name, value in {'EDGE_DATABASE_URL': 'postgresql://edge_bff_login@db/x', 'EDGE_ORC_URL': 'http://orc',
                        'MARKET_AI_ORC_API_KEY': 'k', 'EDGE_OWNER': 'edge-private', 'EDGE_LOGIN': 'owner',
                        'EDGE_PASSWORD_VERIFIER': 'scrypt$' + '0' * 32 + '$' + '0' * 64, 'EDGE_SESSION_SECRET': 's' * 40,
                        'EDGE_PUBLIC_ORIGIN': 'http://localhost', 'EDGE_ENVIRONMENT': 'local'}.items():
        monkeypatch.setenv(name, value)
    assert Settings.from_env().multiuser is False                               # no new variable needed
    monkeypatch.setenv('EDGE_MULTIUSER', 'true')
    with pytest.raises(ValueError, match='EDGE_CODE_SECRET'):
        Settings.from_env()
    monkeypatch.setenv('EDGE_CODE_SECRET', 'c' * 40)
    monkeypatch.setenv('EDGE_MFA_KEY', 'm' * 40)
    s = Settings.from_env()
    assert (s.multiuser, s.email_mode, s.email_enabled) == (True, 'log', True)


# ---- registration -----------------------------------------------------------------------------------------------------

def test_register_sends_a_code_and_verify_signs_in_directly(app, store):
    r = register(app)
    assert (r.status_code, r.json()) == (202, {'status': 'CODE_SENT', 'resend_after_s': 60})
    user = db(store, 'SELECT * FROM edge_bff.users WHERE email=%s', 'ana@example.com')[0]
    assert (user['status'], user['username'], user['requested_username'], user['phone_e164'], user['role']) == \
        ('pending', None, 'ana_putri', '+6281234567890', 'user')
    (mail,) = outbox(store, 'ana@example.com')
    code = mail['payload']['mask'][0]
    stored = db(store, 'SELECT * FROM edge_bff.email_codes')[0]
    assert mail['payload']['subject'] == f'Your EDGE code: {code}' and mail['expires_at'] == stored['expires_at']
    assert code not in stored['code_hash'] and len(stored['code_hash']) == 64
    assert error_code(verify(app, '000000' if code != '000000' else '111111')) == 'CODE_INVALID_OR_EXPIRED'
    r = verify(app, code)
    assert r.status_code == 200 and r.json()['username'] == 'ana_putri' and r.json()['access']['role'] == 'user'
    assert r.json()['owner_key'] == user['owner_key'] and 'edge_session' in r.headers['set-cookie']
    session = app.get('/api/v1/auth/session').json()
    # a registered account is never user #1: its browser never adopts state left before the last-login mark (C3 B1)
    assert session['login'] == 'ana_putri' and session['access']['seed'] is False and r.json()['access']['seed'] is False
    user = db(store, 'SELECT * FROM edge_bff.users WHERE email=%s', 'ana@example.com')[0]
    assert (user['status'], user['username'], user['requested_username']) == ('active', 'ana_putri', None)
    assert user['email_verified_at'] and user['last_sign_in_at']
    assert error_code(verify(app, code)) == 'CODE_INVALID_OR_EXPIRED'            # used


def test_existing_and_new_addresses_and_usernames_answer_alike(app, store, monkeypatch):
    make_account(app, store)
    hour_over(store)
    hashed = []
    real = flows_module.password_verifier
    monkeypatch.setattr(flows_module, 'password_verifier', lambda p: (hashed.append(1), real(p))[1])
    answers = []
    for email, username in [('ana@example.com', 'someone_new'),          # existing address
                            ('bob@example.com', 'bob_b'),                 # new address, new username
                            ('cia@example.com', 'ana_putri')]:            # new address, taken username
        t = time.monotonic()
        r = register(app, email, username)
        answers.append((r.status_code, r.json(), round(time.monotonic() - t, 1) < 2.0))
    assert answers[0] == answers[1] == answers[2] == (202, {'status': 'CODE_SENT', 'resend_after_s': 60}, True)
    assert len(hashed) == 3                                                # the same hashing on every path
    assert outbox(store, 'ana@example.com')[-1]['purpose'] == 'account_exists'
    assert db(store, "SELECT count(*) AS n FROM edge_bff.users WHERE email='ana@example.com'")[0]['n'] == 1
    # the taken username is said only after the code is proved, and another one may be chosen with the same code
    code = last_code(store, 'cia@example.com')
    r = verify(app, code, 'cia@example.com')
    assert r.status_code == 409 and error_code(r) == 'USERNAME_TAKEN' and r.json()['error']['message']
    assert error_code(verify(app, '999999' if code != '999999' else '888888', 'cia@example.com')) == 'CODE_INVALID_OR_EXPIRED'
    assert verify(app, code, 'cia@example.com', username='cia_new').json()['username'] == 'cia_new'


def test_a_code_lives_300_seconds(app, store):
    register(app)
    code = last_code(store, 'ana@example.com')
    db(store, "UPDATE edge_bff.email_codes SET created_at = created_at - interval '299 seconds', "
              "expires_at = expires_at - interval '299 seconds'")
    assert verify(app, code).status_code == 200                                     # 299 s old: still valid
    register(app, 'bob@example.com', 'bob_b')
    code = last_code(store, 'bob@example.com')
    db(store, "UPDATE edge_bff.email_codes SET created_at = created_at - interval '301 seconds', "
              "expires_at = expires_at - interval '301 seconds' WHERE consumed_at IS NULL")
    assert error_code(verify(app, code, 'bob@example.com')) == 'CODE_INVALID_OR_EXPIRED'


def test_five_tries_per_code_and_twenty_per_day_whatever_the_codes(app, store):
    register(app)
    code = last_code(store, 'ana@example.com')
    wrong = '000000' if code != '000000' else '111111'
    for _ in range(5):
        assert error_code(verify(app, wrong)) == 'CODE_INVALID_OR_EXPIRED'
    assert error_code(verify(app, code)) == 'CODE_INVALID_OR_EXPIRED'                 # the code died at its 5th try
    for _ in range(3):                                                              # 15 more wrong tries, 3 new codes
        cooldown_over(store)
        app.post('/api/v1/auth/code/resend', headers=ORIGIN, json={'email': 'ana@example.com', 'purpose': 'register'})
        fresh = last_code(store, 'ana@example.com')
        for _ in range(5):
            verify(app, '000000' if fresh != '000000' else '111111')
    cooldown_over(store)
    app.post('/api/v1/auth/code/resend', headers=ORIGIN, json={'email': 'ana@example.com', 'purpose': 'register'})
    r = verify(app, last_code(store, 'ana@example.com'))                            # the right code of a new one
    assert r.status_code == 429 and error_code(r) == 'LIMIT_REACHED' and int(r.headers['retry-after']) > 0
    assert r.json()['error']['details']['limit'] == 'code_tries'


def test_resend_waits_60_seconds_and_sends_at_most_10_a_day(app, store):
    register(app)
    first = last_code(store, 'ana@example.com')
    r = app.post('/api/v1/auth/code/resend', headers=ORIGIN, json={'email': 'ana@example.com', 'purpose': 'register'})
    assert r.status_code == 202 and len(outbox(store, 'ana@example.com')) == 1            # within 60 s: nothing new
    cooldown_over(store)
    app.post('/api/v1/auth/code/resend', headers=ORIGIN, json={'email': 'ana@example.com', 'purpose': 'register'})
    assert len(outbox(store, 'ana@example.com')) == 2
    assert error_code(verify(app, first)) == 'CODE_INVALID_OR_EXPIRED'                    # the new code replaced it
    # ERRORS R1-13 (fix round): one pending registration is mailed at most 3 times a day (its code and two resends),
    # so the registrations of others cannot use up the address's emails
    for _ in range(12):
        cooldown_over(store)
        app.post('/api/v1/auth/code/resend', headers=ORIGIN, json={'email': 'ana@example.com', 'purpose': 'register'})
    assert len(outbox(store, 'ana@example.com')) == 3
    # the address's own budget (SEND_EMAIL): 10 a day, here through the reset codes of an account
    make_account(TestClient(app.app), store, 'bea@example.com', 'bea_sari')
    for _ in range(12):
        cooldown_over(store)
        app.post('/api/v1/auth/code/resend', headers=ORIGIN, json={'email': 'bea@example.com', 'purpose': 'reset'})
    assert len(outbox(store, 'bea@example.com')) == 10
    for body in ({'email': 'nobody@example.com', 'purpose': 'register'}, {'email': 'nobody@example.com', 'purpose': 'reset'}):
        r = app.post('/api/v1/auth/code/resend', headers=ORIGIN, json=body)
        assert (r.status_code, r.json()) == (202, flows_module.ACCEPTED)
    assert outbox(store, 'nobody@example.com') == []
    r = app.post('/api/v1/auth/code/resend', headers=ORIGIN, json={'email': 'ana@example.com', 'purpose': 'other'})
    assert r.status_code == 400 and r.json()['error']['details']['fields'] == ['purpose']


@pytest.mark.parametrize('change,field', [
    ({'username': 'ab'}, 'username'), ({'username': 'admin'}, 'username'), ({'email': 'not-an-email'}, 'email'),
    ({'first_name': ' '}, 'first_name'), ({'phone': 'call me'}, 'phone'), ({'phone': ''}, 'phone'), ({'phone': None}, 'phone'), ({'password': 'short', 'password_repeat': 'short'}, 'password'),
    ({'password_repeat': 'different'}, 'password_repeat'), ({'extra': 'x'}, 'extra'), ({'username': 5}, 'username')])
def test_register_refuses_malformed_input_by_field(app, store, change, field):
    r = register(app, **change)
    assert r.status_code == 400 and error_code(r) == 'INVALID_INPUT'
    assert field in r.json()['error']['details']['fields'] and r.json()['error']['details']['reasons'][field]
    assert outbox(store) == []


def test_passwords_found_in_breaches_are_refused_and_an_unavailable_check_accepts(app, store, caplog):
    digest = hashlib.sha1(PASSWORD.encode()).hexdigest().upper()
    app.app.state.auth_flows.pwned_fetch = lambda prefix: f'{"0" * 35}:0\r\n{digest[5:]}:42\r\n' if prefix == digest[:5] else ''
    r = register(app)
    assert r.status_code == 400 and error_code(r) == 'PASSWORD_BREACHED' and r.json()['error']['message']
    app.app.state.auth_flows.pwned_fetch = lambda prefix: f'{digest[5:]}:0'           # a padding row never matches
    assert register(app).status_code == 202
    cooldown_over(store)
    app.app.state.auth_flows.pwned_fetch = lambda prefix: None                        # the API did not answer
    with caplog.at_level(logging.WARNING, logger='edge_bff.passwords'):
        assert register(app, 'bob@example.com', 'bob_b').status_code == 202
    assert 'PWNED_CHECK_UNAVAILABLE' in caplog.text


def test_the_range_api_is_asked_with_five_hex_and_padding(monkeypatch):
    from app import passwords
    seen = {}

    def get(url, headers, timeout):
        seen.update(url=url, headers=headers, timeout=timeout)
        return httpx.Response(200, text='ABC:1')
    monkeypatch.setattr(passwords.httpx, 'get', get)
    passwords.pwned('x')
    assert seen['url'] == passwords.RANGE_URL + hashlib.sha1(b'x').hexdigest().upper()[:5]
    assert seen['headers']['Add-Padding'] == 'true' and seen['timeout'] == 2.0
    monkeypatch.setattr(passwords.httpx, 'get', lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectTimeout('x')))
    assert passwords.pwned('x') is False


def test_phone_numbers_become_e164():
    assert normal_phone('0812 3456 7890') == '+6281234567890'
    assert normal_phone('+62 812-3456-7890') == '+6281234567890'
    assert normal_phone('6281234567890') == '+6281234567890'
    assert normal_phone('+1 (415) 555-0100') == '+14155550100'
    assert normal_phone('0044 20 7946 0958') == '+442079460958'
    assert normal_phone('call me') is None and normal_phone('+0123') is None


def test_a_pending_registration_signing_in_gets_the_generic_401_and_a_fresh_code_on_this_browser(app, store):
    """ERRORS M478 (C1 P1-M1): the right password of a pending registration answers exactly the wrong password's 401,
    both set a registration cookie; within the send limits a fresh code is mailed and this browser can finish."""
    register(app)
    other = TestClient(app.app)                                  # another device of the same person
    wrong = other.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'ana@example.com', 'password': 'wrong one'})
    assert len(outbox(store, 'ana@example.com')) == 1
    cooldown_over(store)
    right = other.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'ana@example.com', 'password': PASSWORD})
    assert (wrong.status_code, wrong.json()) == (right.status_code, right.json()) == (
        401, {'error': {'code': 'INVALID_CREDENTIALS', 'message': wrong.json()['error']['message'], 'details': {}}})
    assert 'edge_registration=' in wrong.headers['set-cookie'] and 'edge_registration=' in right.headers['set-cookie']
    assert 'HttpOnly' in right.headers['set-cookie'] and 'SameSite=strict' in right.headers['set-cookie']
    assert len(outbox(store, 'ana@example.com')) == 2                 # a fresh code for this browser
    code = last_code(store, 'ana@example.com')
    assert verify(app, code).status_code == 400                       # the first browser's cookie no longer names it
    r = verify(other, code)
    assert r.status_code == 200 and r.json()['username'] == 'ana_putri'


def test_each_registration_is_bound_to_its_browser_and_the_verified_one_removes_the_others(app, store):
    """ERRORS M478 (C1 P1-H1, C2 #1): a later registration of the address is its own pending row; a code activates
    only the row whose cookie comes with it; verifying one deletes the other pending rows of the address."""
    assert register(app).status_code == 202
    mine = last_code(store, 'ana@example.com')
    other = TestClient(app.app)
    hour_over(store)
    assert register(other, username='other_one', password='the other password').status_code == 202
    theirs = last_code(store, 'ana@example.com')
    rows = db(store, "SELECT requested_username, registration_hash FROM edge_bff.users WHERE email='ana@example.com' ORDER BY user_id")
    assert [r['requested_username'] for r in rows] == ['ana_putri', 'other_one'] and all(len(r['registration_hash']) == 64 for r in rows)
    assert error_code(verify(app, theirs)) == 'CODE_INVALID_OR_EXPIRED'      # another browser's code
    assert error_code(TestClient(app.app).post('/api/v1/auth/register/verify', headers=ORIGIN,
                                              json={'email': 'ana@example.com', 'code': mine})) == 'CODE_INVALID_OR_EXPIRED'
    r = verify(app, mine)
    assert r.status_code == 200 and r.json()['username'] == 'ana_putri'
    assert 'edge_registration=""' in r.headers['set-cookie'] or 'edge_registration=;' in r.headers['set-cookie']
    assert db(store, "SELECT status, registration_hash FROM edge_bff.users WHERE email='ana@example.com'") == [
        {'status': 'active', 'registration_hash': None}]
    assert error_code(verify(other, theirs)) == 'CODE_INVALID_OR_EXPIRED'
    assert other.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'ana@example.com',
                                                                   'password': 'the other password'}).status_code == 401
    # a resend without this browser's registration cookie sends nothing
    cooldown_over(store)
    register(app, 'bob@example.com', 'bob_b')
    cooldown_over(store)
    stranger = TestClient(app.app)
    stranger.post('/api/v1/auth/code/resend', headers=ORIGIN, json={'email': 'bob@example.com', 'purpose': 'register'})
    assert len(outbox(store, 'bob@example.com')) == 1


def test_pending_sessions_have_their_own_cap(on, store):
    from app.accounts import AccountStore, MAX_PENDING_SESSIONS, MAX_SESSIONS
    from app.security import token_hash
    accounts = AccountStore(store)
    user = accounts.seed(on.owner, on.login, on.password_verifier, True)
    user = {'user_id': user['user_id'], 'owner_key': on.owner}
    for i in range(MAX_SESSIONS):
        accounts.create_session(token_hash(f'real{i}'), user, 3600, None, True, True)
    for i in range(MAX_PENDING_SESSIONS + 4):
        accounts.create_session(token_hash(f'pending{i}'), user, 3600, None, False, True)
    live = db(store, 'SELECT mfa_passed_at IS NOT NULL AS real FROM edge_bff.sessions WHERE revoked_at IS NULL')
    assert sum(r['real'] for r in live) == MAX_SESSIONS and sum(not r['real'] for r in live) == MAX_PENDING_SESSIONS


def test_mfa_lock_after_consecutive_failures_and_its_clearing(app, store, on):
    flows = app.app.state.auth_flows
    now = {'t': 1_800_000_000.0}
    flows.clock = lambda: now['t']
    h = admin_sign_in(app)
    enrolled = app.post('/api/v1/auth/mfa/enroll', headers=h).json()
    db(store, 'UPDATE edge_bff.mfa_totp SET totp_failures = 99, confirmed_at = now()')
    assert error_code(app.post('/api/v1/auth/mfa/verify', headers=h, json={'code': '000000'})) == 'MFA_CODE_INVALID'
    r = app.post('/api/v1/auth/mfa/verify', headers=h, json={'code': '000000'})
    assert (r.status_code, error_code(r)) == (403, 'MFA_LOCKED')
    assert r.json()['error']['message'] == ('Too many wrong codes, so this way of signing in is locked. Wait 24 hours or '
                                            'reset your password by email; an operator can also unlock it.')
    assert r.json()['error']['details']['use'] == 'recovery_code' and r.json()['error']['details']['unlock_at'].startswith('2027-')
    db(store, "DELETE FROM edge_bff.auth_throttle")
    user_id, nonce = (lambda r: (r['user_id'], bytes(r['nonce'])))(db(store, 'SELECT user_id, nonce FROM edge_bff.mfa_totp')[0])
    good = mfa.code_at(mfa.secret_of(on.mfa_key, user_id, nonce), int(now['t']) // 30)
    assert error_code(app.post('/api/v1/auth/mfa/verify', headers=h, json={'code': good})) == 'MFA_LOCKED'   # even right
    db(store, "DELETE FROM edge_bff.auth_throttle")                                  # the 15-min throttle apart
    for _ in range(10):
        app.post('/api/v1/auth/mfa/verify', headers=h, json={'recovery_code': 'wrong-codes'})
    db(store, "DELETE FROM edge_bff.auth_throttle")
    r = app.post('/api/v1/auth/mfa/verify', headers=h, json={'recovery_code': enrolled['recovery_codes'][0]})
    assert error_code(r) == 'MFA_LOCKED'                                            # 10 recovery failures
    db(store, 'UPDATE edge_bff.mfa_totp SET recovery_failures = 9')
    r = app.post('/api/v1/auth/mfa/verify', headers=h, json={'recovery_code': enrolled['recovery_codes'][0]})
    assert r.status_code == 200                                                     # a success clears both counts
    assert db(store, 'SELECT totp_failures, recovery_failures FROM edge_bff.mfa_totp') == [
        {'totp_failures': 0, 'recovery_failures': 0}]


def test_mfa_verify_gives_a_new_session_token_and_revokes_the_pending_one(app, store, on):
    flows = app.app.state.auth_flows
    now = {'t': 1_800_000_000.0}
    flows.clock = lambda: now['t']
    h = admin_sign_in(app)
    pending = app.cookies.get('edge_session')
    app.post('/api/v1/auth/mfa/enroll', headers=h)
    user_id, nonce = (lambda r: (r['user_id'], bytes(r['nonce'])))(db(store, 'SELECT user_id, nonce FROM edge_bff.mfa_totp')[0])
    r = app.post('/api/v1/auth/mfa/verify', headers=h, json={'code': mfa.code_at(mfa.secret_of(on.mfa_key, user_id, nonce), int(now['t']) // 30)})
    fresh = app.cookies.get('edge_session')
    assert r.status_code == 200 and fresh != pending and r.json()['csrf_token'] != h['X-CSRF-Token']
    old = TestClient(app.app)
    old.cookies.set('edge_session', pending)
    assert old.get('/api/v1/auth/session').status_code == 401
    assert app.get('/api/v1/terminal/layouts').status_code == 200


def test_a_legacy_raw_verifier_still_signs_in_and_new_ones_are_nfkc(settings):
    import hashlib as _h
    import secrets as _s
    from app.security import password_verifier, verify_password
    raw = 'cafe\u0301 au lait'
    salt = _s.token_bytes(16)
    legacy = f"scrypt${salt.hex()}${_h.scrypt(raw.encode(), salt=salt, n=16384, r=8, p=1, dklen=32).hex()}"
    assert verify_password(raw, legacy)                                              # the raw text still works
    assert verify_password('café au lait', password_verifier(raw))                   # NFC and NFD alike
    assert verify_password(settings.login and 'local-test-password', settings.password_verifier)


def test_pending_registrations_are_deleted_after_24_hours(app, store):
    register(app)
    register(app, 'bob@example.com', 'bob_b')
    db(store, "UPDATE edge_bff.users SET created_at = now() - interval '25 hours' WHERE email='ana@example.com'")
    store.cleanup_sessions()
    assert [r['email'] for r in db(store, "SELECT email FROM edge_bff.users WHERE status='pending'")] == ['bob@example.com']


# ---- passwords ----------------------------------------------------------------------------------------------------------

def test_reset_revokes_every_session_and_signs_nobody_in(app, store, on):
    make_account(app, store)
    other = TestClient(app.app)
    assert other.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'ana_putri', 'password': PASSWORD}).status_code == 200
    cooldown_over(store)
    assert app.post('/api/v1/auth/password/forgot', headers=ORIGIN, json={'email': 'ana@example.com'}).json() == flows_module.ACCEPTED
    assert app.post('/api/v1/auth/password/forgot', headers=ORIGIN, json={'email': 'nobody@example.com'}).status_code == 202
    assert outbox(store, 'nobody@example.com') == []
    code = last_code(store, 'ana@example.com')
    body = {'email': 'ana@example.com', 'code': code, 'password': 'my new password', 'password_repeat': 'my new password'}
    assert error_code(app.post('/api/v1/auth/password/reset', headers=ORIGIN, json={**body, 'code': 'abcdef'})) == 'CODE_INVALID_OR_EXPIRED'
    r = app.post('/api/v1/auth/password/reset', headers=ORIGIN, json=body)
    assert (r.status_code, r.json()) == (200, {'next': 'sign_in'})
    assert 'Max-Age=0' in r.headers['set-cookie'] or 'expires=' in r.headers['set-cookie'].lower()   # only a removal
    assert app.get('/api/v1/auth/session').status_code == 401 and other.get('/api/v1/auth/session').status_code == 401
    assert db(store, 'SELECT count(*) AS n FROM edge_bff.sessions WHERE revoked_at IS NULL')[0]['n'] == 0
    assert outbox(store, 'ana@example.com')[-1]['purpose'] == 'password_changed'
    sign = lambda pw: app.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'ana_putri', 'password': pw}).status_code
    assert (sign(PASSWORD), sign('my new password')) == (401, 200)
    assert error_code(app.post('/api/v1/auth/password/reset', headers=ORIGIN, json=body)) == 'CODE_INVALID_OR_EXPIRED'


def test_change_keeps_this_session_revokes_the_others_and_sign_out_all(app, store):
    r = make_account(app, store)
    h = {**ORIGIN, 'X-CSRF-Token': r.json()['csrf_token']}
    other = TestClient(app.app)
    other.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'ana_putri', 'password': PASSWORD})
    body = {'current_password': 'not it', 'password': 'another password', 'password_repeat': 'another password'}
    r = app.post('/api/v1/auth/password/change', headers=h, json=body)
    assert (r.status_code, error_code(r)) == (400, 'CURRENT_PASSWORD_INVALID')
    assert app.post('/api/v1/auth/password/change', headers=ORIGIN, json=body).status_code == 403     # CSRF
    r = app.post('/api/v1/auth/password/change', headers=h, json={**body, 'current_password': PASSWORD})
    assert r.json() == {'status': 'PASSWORD_CHANGED'}
    assert app.get('/api/v1/auth/session').status_code == 200 and other.get('/api/v1/auth/session').status_code == 401
    assert outbox(store, 'ana@example.com')[-1]['purpose'] == 'password_changed'
    h2 = {**ORIGIN, 'X-CSRF-Token': other.post('/api/v1/auth/sign-in', headers=ORIGIN, json={
        'login': 'ana_putri', 'password': 'another password'}).json()['csrf_token']}
    assert other.post('/api/v1/auth/sign-out-all', headers=h2).json() == {'authenticated': False}
    assert app.get('/api/v1/auth/session').status_code == 401 and other.get('/api/v1/auth/session').status_code == 401


# ---- MFA ----------------------------------------------------------------------------------------------------------------

def admin_sign_in(c):
    r = c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'owner', 'password': 'local-test-password'})
    assert r.status_code == 403 and error_code(r) == 'MFA_REQUIRED' and 'edge_session' in r.headers['set-cookie']
    return {**ORIGIN, 'X-CSRF-Token': r.json()['error']['details']['csrf_token']}


def test_admin_mfa_enrol_verify_replay_and_recovery(app, store, on):
    flows = app.app.state.auth_flows
    now = {'t': 1_800_000_000.0}
    flows.clock = lambda: now['t']
    h = admin_sign_in(app)
    s = app.get('/api/v1/auth/session').json()
    assert s['access']['next'] == 'mfa' and s['access']['mfa_enrolled'] is False and s['csrf_token'] == h['X-CSRF-Token']
    assert s['access']['seed'] is True                     # the seed row (owner key EDGE_OWNER) is user #1, switch on too
    for method, path in (('GET', '/api/v1/terminal/layouts'), ('GET', '/api/v1/preferences'), ('GET', '/api/v1/dev/manual/steps')):
        r = app.request(method, path)
        assert (r.status_code, error_code(r)) == (403, 'MFA_REQUIRED'), path
    r = app.post('/api/v1/auth/mfa/verify', headers=h, json={'code': '123456'})
    assert error_code(r) == 'MFA_NOT_ENROLLED'
    enrolled = app.post('/api/v1/auth/mfa/enroll', headers=h).json()
    assert enrolled['otpauth_uri'].startswith('otpauth://totp/EDGE%3Aowner?') and 'issuer=EDGE' in enrolled['otpauth_uri']
    assert len(enrolled['recovery_codes']) == 10 and len(set(enrolled['recovery_codes'])) == 10
    user_id, nonce = (lambda r: (r['user_id'], bytes(r['nonce'])))(db(store, 'SELECT user_id, nonce FROM edge_bff.mfa_totp')[0])
    secret = mfa.secret_of(on.mfa_key, user_id, nonce)
    assert base64.b32encode(secret).decode().rstrip('=') in enrolled['otpauth_uri']
    hashes = {r['code_hash'] for r in db(store, 'SELECT code_hash FROM edge_bff.mfa_recovery_codes')}
    assert not hashes & set(enrolled['recovery_codes']) and len(hashes) == 10
    step = int(now['t']) // 30
    assert error_code(app.post('/api/v1/auth/mfa/verify', headers=h, json={'code': mfa.code_at(secret, step + 3)})) == 'MFA_CODE_INVALID'
    r = app.post('/api/v1/auth/mfa/verify', headers=h, json={'code': mfa.code_at(secret, step - 1)})      # one step late
    assert r.status_code == 200 and r.json()['access']['mfa_ok'] is True and r.json()['access']['mfa_enrolled'] is True
    assert app.get('/api/v1/terminal/layouts').status_code == 200
    # the same step again, from a new sign-in: refused (replay); the next step passes
    h = admin_sign_in(app)
    assert app.get('/api/v1/auth/session').json()['access']['mfa_enrolled'] is True
    assert error_code(app.post('/api/v1/auth/mfa/verify', headers=h, json={'code': mfa.code_at(secret, step - 1)})) == 'MFA_CODE_INVALID'
    # a pending session cannot replace a confirmed enrolment (a password alone never resets the second factor)
    assert error_code(app.post('/api/v1/auth/mfa/enroll', headers=h)) == 'MFA_REQUIRED'
    assert app.post('/api/v1/auth/mfa/verify', headers=h, json={'code': mfa.code_at(secret, step)}).status_code == 200
    # a recovery code works once
    recovery = enrolled['recovery_codes'][0]
    h = admin_sign_in(app)
    assert app.post('/api/v1/auth/mfa/verify', headers=h, json={'recovery_code': recovery.upper()}).status_code == 200
    h = admin_sign_in(app)
    assert error_code(app.post('/api/v1/auth/mfa/verify', headers=h, json={'recovery_code': recovery})) == 'MFA_CODE_INVALID'
    r = app.post('/api/v1/auth/mfa/verify', headers=h, json={'code': '1', 'recovery_code': '2'})
    assert r.status_code == 400 and error_code(r) == 'INVALID_INPUT'


def test_mfa_tries_are_limited_and_a_user_cannot_enrol(app, store):
    r = make_account(app, store)
    h = {**ORIGIN, 'X-CSRF-Token': r.json()['csrf_token']}
    r = app.post('/api/v1/auth/mfa/enroll', headers=h)
    assert (r.status_code, error_code(r)) == (403, 'CAPABILITY_REQUIRED')
    h = admin_sign_in(app)
    app.post('/api/v1/auth/mfa/enroll', headers=h)
    codes = [app.post('/api/v1/auth/mfa/verify', headers=h, json={'code': '000000'}).status_code for _ in range(11)]
    assert codes[:10] == [400] * 10 and codes[10] == 429


# ---- email outbox and sender ------------------------------------------------------------------------------------------

def resend_settings(on):
    return dataclasses.replace(on, email_mode='resend', resend_api_key='re_test_key', email_from='EDGE <no-reply@mail.example.com>')


def test_resend_500_then_200_sends_once_with_one_idempotency_key(app, store, on):
    register(app)
    seen = []
    replies = iter([httpx.Response(500, json={'message': 'down'}), httpx.Response(200, json={'id': 'em_123'})])

    def handler(request):
        seen.append((request.url, request.headers['idempotency-key'], request.headers['authorization'], json.loads(request.content)))
        return next(replies)
    sender = EmailSender(resend_settings(on), store, transport=httpx.MockTransport(handler))

    async def go():
        assert await sender.step() is True
        row = outbox(store)[0]
        assert (row['status'], row['attempts']) == ('pending', 1) and row['next_at'] > row['created_at']
        assert await sender.step() is False                                     # waits its 5 s
        db(store, 'UPDATE edge_bff.email_outbox SET next_at = now()')
        assert await sender.step() is True
        await sender.aclose()
    asyncio.run(go())
    row = outbox(store)[0]
    assert (row['status'], row['provider_id'], row['payload'], row['attempts']) == ('sent', 'em_123', None, 2)
    assert len(seen) == 2 and seen[0][1] == seen[1][1] == row['idempotency_key']
    assert str(seen[0][0]) == 'https://api.resend.com/emails' and seen[0][2] == 'Bearer re_test_key'
    assert seen[0][3]['to'] == ['ana@example.com'] and seen[0][3]['subject'].startswith('Your EDGE code: ')


def test_failures_back_off_then_fail_and_expired_or_suppressed_mail_is_never_sent(app, store, on):
    register(app)
    seen = []
    sender = EmailSender(resend_settings(on), store, transport=httpx.MockTransport(lambda r: (seen.append(1), httpx.Response(503))[1]))

    async def tries(n):
        for _ in range(n):
            db(store, 'UPDATE edge_bff.email_outbox SET next_at = now()')
            await sender.step()
    delays = []
    for _ in range(4):
        asyncio.run(tries(1))
        row = outbox(store)[0]
        delays.append((row['status'], round((row['next_at'] - db(store, 'SELECT now() AS n')[0]['n']).total_seconds())))
    assert [d[0] for d in delays] == ['pending', 'pending', 'pending', 'failed'] and outbox(store)[0]['payload'] is None
    assert [d[1] for d in delays[:3]] == [5, 30, 120]
    seen.clear()
    cooldown_over(store)
    app.post('/api/v1/auth/code/resend', headers=ORIGIN, json={'email': 'ana@example.com', 'purpose': 'register'})
    db(store, "UPDATE edge_bff.email_outbox SET expires_at = now() - interval '1 second' WHERE status='pending'")
    asyncio.run(tries(1))
    assert outbox(store)[-1]['status'] == 'expired' and outbox(store)[-1]['payload'] is None and seen == []
    register(app, 'bob@example.com', 'bob_b')
    db(store, "INSERT INTO edge_bff.email_suppression(email, reason) VALUES ('bob@example.com', 'bounce')")
    asyncio.run(tries(1))
    assert outbox(store, 'bob@example.com')[0]['status'] == 'suppressed' and seen == []


def test_log_mode_masks_the_code_outside_local(app, store, on, caplog):
    register(app)
    code = last_code(store, 'ana@example.com')
    sender = EmailSender(dataclasses.replace(on, environment='dev'), store)
    with caplog.at_level(logging.INFO, logger='edge_bff.email'):
        asyncio.run(sender.step())
    assert code not in caplog.text and 'Your EDGE code: ••••••' in caplog.text and 'ana@example.com' not in caplog.text
    row = outbox(store)[0]
    assert row['status'] == 'sent' and row['provider_id'] == 'log' and row['payload']['mask'] == [code]


class SlowOrc(FakeOrc):
    def __init__(self):
        super().__init__()
        self.release, self.started = threading.Event(), threading.Event()

    def run(self, owner, id, payload):
        self.started.set()
        self.release.wait(20)
        return super().run(owner, id, payload)


def test_the_sender_sends_while_an_ai_run_holds_the_worker(on, store):
    orc = SlowOrc()
    application = create_app(dataclasses.replace(on, worker_enabled=True), store, orc)
    application.state.auth_flows.pwned_fetch = lambda prefix: ''
    try:
        with TestClient(application) as c:
            h = login_admin_free(c, store)
            assert c.post('/api/v1/runs', headers=h, json={'message': 'Explain GOTO', 'submission_key': 'one'}).status_code == 202
            assert orc.started.wait(10)
            assert register(c, 'bob@example.com', 'bob_b').status_code == 202
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and outbox(store, 'bob@example.com')[0]['status'] != 'sent':
                time.sleep(0.05)
            assert outbox(store, 'bob@example.com')[0]['status'] == 'sent'
            assert not orc.release.is_set()                                         # the AI run is still running
            orc.release.set()
    finally:
        orc.release.set()


def login_admin_free(c, store):
    """A plain user signed in (an admin's pending session reaches no run route). EXEC-MU-ACCOUNTS Phase 3a (decision
    D1): the Monitor is not in the default plan, so this account is given it by overrides (view, chat, every model)."""
    make_account(c, store)
    with store.connect() as conn:
        for key, value in (('monitor.view', 'true'), ('monitor.chat', 'true'), ('monitor.model', '{"all": true}')):
            conn.execute("""INSERT INTO edge_bff.user_capability_overrides(user_id, capability_key, value, reason)
                SELECT user_id, %s, %s::jsonb, 'test: the Monitor for a plain user' FROM edge_bff.users
                WHERE username = 'ana_putri'""", (key, value))
    r = c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'ana_putri', 'password': PASSWORD})
    return {**ORIGIN, 'X-CSRF-Token': r.json()['csrf_token']}


# ---- the Resend webhook -------------------------------------------------------------------------------------------------

def signed(body, svix_id='msg_1', stamp=None, secret=SECRET):
    stamp = str(int(time.time()) if stamp is None else stamp)
    raw = json.dumps(body).encode()
    key = base64.b64decode(secret[len('whsec_'):])
    sig = base64.b64encode(hmac.new(key, f'{svix_id}.{stamp}.'.encode() + raw, hashlib.sha256).digest()).decode()
    return raw, {'svix-id': svix_id, 'svix-timestamp': stamp, 'svix-signature': f'v1,bogus v1,{sig}',
                 'content-type': 'application/json'}


def test_the_webhook_suppresses_bounces_once_and_ignores_bad_signatures(app, store):
    hook = '/api/v1/hooks/email/resend'
    bounce = {'type': 'email.bounced', 'data': {'to': ['Ana@Example.com']}}
    raw, headers = signed(bounce, 'msg_bad', secret='whsec_' + base64.b64encode(b'x' * 32).decode())
    assert (app.post(hook, content=raw, headers=headers).status_code, db(store, 'SELECT * FROM edge_bff.email_suppression')) == (401, [])
    raw, headers = signed(bounce, 'msg_old', stamp=int(time.time()) - 301)
    assert app.post(hook, content=raw, headers=headers).status_code == 401
    raw, headers = signed(bounce, 'msg_1')
    assert app.post(hook, content=raw + b' ', headers=headers).status_code == 401          # the body was changed
    r = app.post(hook, content=raw, headers=headers)                                       # no Origin: a hook
    assert (r.status_code, r.json()) == (200, {'status': 'applied'})
    assert [(x['email'], x['reason']) for x in db(store, 'SELECT * FROM edge_bff.email_suppression')] == [('ana@example.com', 'bounce')]
    raw, headers = signed({'type': 'email.complained', 'data': {'to': ['bob@example.com']}}, 'msg_1')
    assert app.post(hook, content=raw, headers=headers).json() == {'status': 'duplicate'}     # the same svix-id
    assert len(db(store, 'SELECT * FROM edge_bff.email_suppression')) == 1
    raw, headers = signed({'type': 'email.delivered', 'data': {'to': ['bob@example.com']}}, 'msg_2')
    assert app.post(hook, content=raw, headers=headers).json() == {'status': 'applied'}
    assert len(db(store, 'SELECT * FROM edge_bff.email_suppression')) == 1


# ---- second fix round (ERRORS M478 re-check: N1-N4) ---------------------------------------------------------------------

def test_every_sign_in_runs_the_same_number_of_derivations(app, store, monkeypatch):
    """N1: 1 + PENDING_CHECKED derivations whatever the address holds: an account, 0 to 3+ pending rows, nothing."""
    from app import main as main_module
    from app.accounts import PENDING_CHECKED
    make_account(app, store, 'acct@example.com', 'acct_1')
    for n in range(4):
        hour_over(store)
        register(TestClient(app.app), 'many@example.com', f'many_{n}')
    hour_over(store)
    register(TestClient(app.app), 'one@example.com', 'one_1')
    assert db(store, "SELECT count(*) AS n FROM edge_bff.users WHERE email='many@example.com'")[0]['n'] == 3
    calls = []
    real = main_module.verify_password
    monkeypatch.setattr(main_module, 'verify_password', lambda pw, v: calls.append(1) or real(pw, v))
    counts = {}
    for login in ('acct@example.com', 'acct_1', 'many@example.com', 'one@example.com', 'none@example.com', 'nobody'):
        calls.clear()
        TestClient(app.app).post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': login, 'password': 'wrong password'})
        counts[login] = len(calls)
    assert set(counts.values()) == {1 + PENDING_CHECKED}, counts
    calls.clear()
    assert TestClient(app.app).post('/api/v1/auth/sign-in', headers=ORIGIN,
                                    json={'login': 'acct_1', 'password': PASSWORD}).status_code == 200
    assert len(calls) == 1 + PENDING_CHECKED


def test_a_failed_sign_in_keeps_this_browsers_registration_cookie(app, store):
    """N3: a 401 that restarted nothing sets the browser's own registration cookie again (or an unused one)."""
    register(app)
    held = app.cookies.get('edge_registration')
    r = app.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'nobody', 'password': 'wrong password'})
    assert r.status_code == 401 and f'edge_registration={held}' in r.headers['set-cookie']
    fresh = TestClient(app.app)
    r = fresh.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'nobody', 'password': 'wrong password'})
    assert 'edge_registration=' in r.headers['set-cookie'] and fresh.cookies.get('edge_registration') != held
    assert verify(app, last_code(store, 'ana@example.com')).status_code == 200


def test_new_registrations_of_an_address_mail_it_once_an_hour_and_three_times_a_day(app, store):
    """N4: a second registration of the address within the hour (any browser) answers the same 202, creates nothing
    and mails nothing; at most three such emails a day."""
    assert register(app).status_code == 202
    cooldown_over(store)
    other = TestClient(app.app)
    r = register(other, username='other_one')
    assert (r.status_code, r.json()) == (202, flows_module.ACCEPTED) and 'edge_registration=' in r.headers['set-cookie']
    assert len(outbox(store, 'ana@example.com')) == 1
    assert db(store, "SELECT count(*) AS n FROM edge_bff.users WHERE email='ana@example.com'")[0]['n'] == 1
    for n in range(4):
        hour_over(store)
        register(TestClient(app.app), username=f'later_{n}')
    assert len(outbox(store, 'ana@example.com')) == 3
    # the first browser can still finish, and ask again for its own code
    cooldown_over(store)
    app.post('/api/v1/auth/code/resend', headers=ORIGIN, json={'email': 'ana@example.com', 'purpose': 'register'})
    assert len(outbox(store, 'ana@example.com')) == 4
    assert verify(app, last_code(store, 'ana@example.com')).json()['username'] == 'ana_putri'


def mfa_locked_admin(app, store, on, now):
    flows = app.app.state.auth_flows
    flows.clock = lambda: now['t']
    h = admin_sign_in(app)
    app.post('/api/v1/auth/mfa/enroll', headers=h)
    row = db(store, 'SELECT user_id, nonce FROM edge_bff.mfa_totp')[0]
    secret = mfa.secret_of(on.mfa_key, row['user_id'], bytes(row['nonce']))
    db(store, 'UPDATE edge_bff.mfa_totp SET confirmed_at = now(), totp_failures = 99')
    app.post('/api/v1/auth/mfa/verify', headers=h, json={'code': '000000'})           # the 100th: locked for 24 h
    return h, secret


def test_the_mfa_lock_ends_after_24_hours_with_few_tries_left(app, store, on):
    now = {'t': 1_800_000_000.0}
    h, secret = mfa_locked_admin(app, store, on, now)
    lock = db(store, 'SELECT totp_failures, totp_locked_until FROM edge_bff.mfa_totp')[0]
    assert (lock['totp_failures'], lock['totp_locked_until']) == (100, 1_800_000_000 + 86400)
    db(store, 'DELETE FROM edge_bff.auth_throttle')
    now['t'] += 86399
    r = app.post('/api/v1/auth/mfa/verify', headers=h, json={'code': mfa.code_at(secret, int(now['t']) // 30)})
    assert error_code(r) == 'MFA_LOCKED' and r.json()['error']['details']['unlock_at'] == '2027-01-16T08:00:00+00:00'
    now['t'] += 1                                                                       # the lock has ended
    db(store, 'DELETE FROM edge_bff.auth_throttle')
    for _ in range(10):
        assert error_code(app.post('/api/v1/auth/mfa/verify', headers=h, json={'code': '000000'})) == 'MFA_CODE_INVALID'
    db(store, 'DELETE FROM edge_bff.auth_throttle')
    assert error_code(app.post('/api/v1/auth/mfa/verify', headers=h, json={'code': '000000'})) == 'MFA_LOCKED'   # 90 + 10


def test_a_password_reset_by_email_clears_the_mfa_lock(app, store, on):
    now = {'t': 1_800_000_000.0}
    mfa_locked_admin(app, store, on, now)
    db(store, "UPDATE edge_bff.users SET email='owner@example.com' WHERE owner_key=%s", on.owner)
    cooldown_over(store)
    app.post('/api/v1/auth/password/forgot', headers=ORIGIN, json={'email': 'owner@example.com'})
    body = {'email': 'owner@example.com', 'code': last_code(store, 'owner@example.com'), 'password': 'a fresh password',
            'password_repeat': 'a fresh password'}
    assert app.post('/api/v1/auth/password/reset', headers=ORIGIN, json=body).status_code == 200
    assert db(store, 'SELECT totp_failures, recovery_failures, totp_locked_until FROM edge_bff.mfa_totp') == [
        {'totp_failures': 0, 'recovery_failures': 0, 'totp_locked_until': None}]


def test_the_operator_unlock_clears_the_lock_and_writes_the_audit(app, store, on, database, monkeypatch, capsys):
    import importlib.util
    from pathlib import Path
    now = {'t': 1_800_000_000.0}
    mfa_locked_admin(app, store, on, now)
    spec = importlib.util.spec_from_file_location('edge_mfa_unlock', Path(__file__).resolve().parents[3] / 'scripts/edge_mfa_unlock.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv('DATABASE_URL', database)
    assert module.main(['--username', 'nobody_here', '--reason', 'test']) == 1
    assert module.main(['--username', 'owner', '--reason', 'locked by a password holder, ticket 12']) == 0
    out = capsys.readouterr().out
    assert database not in out and 'unlocked' in out
    assert db(store, 'SELECT totp_failures, totp_locked_until FROM edge_bff.mfa_totp') == [
        {'totp_failures': 0, 'totp_locked_until': None}]
    (audit,) = db(store, 'SELECT * FROM edge_bff.admin_audit')
    assert (audit['action'], audit['actor_user_id'], audit['after']['actor'], audit['before']['totp_failures']) == (
        'mfa.unlock', None, 'operator', 100)
    assert audit['reason'] == 'operator: locked by a password holder, ticket 12'
