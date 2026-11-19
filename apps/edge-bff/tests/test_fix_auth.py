"""EXEC-MU-ACCOUNTS fix round of the ultracode re-check, track auth (verification/edge_multiuser/fix_round/auth.md).
The re-check's own failing tests (test_cp0_reserved_owner, test_cp1a_phase1_auth_check, test_r2_race, test_r2_life,
test_c2_ops_recheck) are the acceptance of their findings; these lock the parts of the fixes they do not reach:

- R1-9: the sign-in limit is per login and client address, so tries from elsewhere do not keep an account out.
- R1-16: at most 100 consecutive failed passwords per account (both logins, every address), then 24 h answered as a
  wrong password; a reset proved by the email code lifts it; after the lock 10 more tries (as the MFA counts).
- R1-7: a re-enrolment waits beside the confirmed authenticator, which keeps working (its recovery codes too) until a
  code of the new one confirms it; then the old codes stop.
- R2-29: new verifiers carry the OWASP cost; a verifier of the old cost still signs in and is replaced at once, and a
  check costs the same whatever the verifier's age.
- R2-24: the outbox purge keeps the rows of an address that has an account, and rows not yet sent.
- R2-37: over the password pool's limit a request is answered 503 with Retry-After at once.
- R1-9 (wording): a sign-in limit's message says its own wait.
"""
import base64
import hashlib
import re
import secrets

import pytest
from fastapi.testclient import TestClient

from app import mfa, security
from app.accounts import PASSWORD_FAILURE_CAP, PASSWORD_RESTART
from app.errors import message_of
from app.main import create_app
from app.passwords import PasswordWork
from conftest import FakeOrc
from test_auth_flows import (PASSWORD, admin_sign_in, app, cooldown_over, db, error_code, last_code,  # noqa: F401
                             make_account, on, outbox)
from test_edge import ORIGIN, login


def sign_in(c, login_, password, address=None):
    headers = {**ORIGIN, **({'X-Forwarded-For': address} if address else {})}
    return c.post('/api/v1/auth/sign-in', headers=headers, json={'login': login_, 'password': password})


# ---- R1-9: per login and client address ----------------------------------------------------------------------------

def test_tries_from_another_address_do_not_keep_the_owner_out(settings, store):
    with TestClient(create_app(settings, store, FakeOrc())) as c:
        for _ in range(10):
            assert sign_in(c, 'owner', 'wrong', '198.51.100.7').status_code == 401
        r = sign_in(c, 'owner', 'wrong', '198.51.100.7')
        assert r.status_code == 429 and error_code(r) == 'SIGN_IN_RATE_LIMIT'
        assert sign_in(c, 'owner', 'local-test-password', '203.0.113.9').status_code == 200


def test_a_sign_in_limit_says_its_own_wait():
    assert message_of('SIGN_IN_RATE_LIMIT', 429, {'retry_after_s': 931}) == (
        'Too many sign-in attempts from here. Wait 16 minutes, then try again.')
    assert message_of('SIGN_IN_RATE_LIMIT', 429, {'retry_after_s': 30}).endswith('Wait less than a minute, then try again.')
    assert 'a few minutes' in message_of('SIGN_IN_RATE_LIMIT', 429, {})


# ---- R1-16: the per-account cap of consecutive failures --------------------------------------------------------------

def fail_across_addresses(c, n, logins=('ana_putri', 'ana@example.com')):
    """n wrong passwords spread over both logins and several client addresses (each under its own 10 per 15 min)."""
    for i in range(n):
        assert sign_in(c, logins[i % len(logins)], 'not the password', f'198.51.100.{i // 9 + 1}').status_code == 401


def failures(store):
    return db(store, "SELECT sign_in_failures, sign_in_locked_until FROM edge_bff.identities i JOIN edge_bff.users u "
                     "USING (user_id) WHERE u.email='ana@example.com'")[0]


def test_the_100th_consecutive_failure_locks_the_password_and_a_reset_lifts_it(app, store):
    make_account(app, store)
    stranger = TestClient(app.app)
    fail_across_addresses(stranger, 3)                       # one count for the account, whatever login and address
    assert failures(store) == {'sign_in_failures': 3, 'sign_in_locked_until': None}
    db(store, 'UPDATE edge_bff.identities SET sign_in_failures = %s WHERE sign_in_failures = 3', PASSWORD_FAILURE_CAP - 4)
    fail_across_addresses(stranger, 3)
    assert failures(store)['sign_in_failures'] == PASSWORD_FAILURE_CAP - 1 and failures(store)['sign_in_locked_until'] is None
    fail_across_addresses(stranger, 1)                       # the 100th: still checked, and it starts the lock
    row = failures(store)
    assert row['sign_in_failures'] == PASSWORD_FAILURE_CAP and row['sign_in_locked_until'] is not None
    # locked: the right password from a fresh address is answered as a wrong one (OWASP: the same answer), uncounted
    r = sign_in(TestClient(app.app), 'ana_putri', PASSWORD, '203.0.113.50')
    assert (r.status_code, error_code(r)) == (401, 'INVALID_CREDENTIALS')
    assert failures(store)['sign_in_failures'] == PASSWORD_FAILURE_CAP
    # the way back: a reset proved by the email code
    cooldown_over(store)
    assert app.post('/api/v1/auth/password/forgot', headers=ORIGIN, json={'email': 'ana@example.com'}).status_code == 202
    body = {'email': 'ana@example.com', 'code': last_code(store, 'ana@example.com'), 'password': 'my new password',
            'password_repeat': 'my new password'}
    assert app.post('/api/v1/auth/password/reset', headers=ORIGIN, json=body).status_code == 200
    assert sign_in(TestClient(app.app), 'ana@example.com', 'my new password', '203.0.113.50').status_code == 200


def test_after_the_lock_ends_ten_more_tries_and_a_success_clears_the_count(app, store):
    make_account(app, store)
    db(store, "UPDATE edge_bff.identities SET sign_in_failures = %s, sign_in_locked_until = now() - interval '1 second' "
              "WHERE user_id = (SELECT user_id FROM edge_bff.users WHERE email = 'ana@example.com')", PASSWORD_FAILURE_CAP)
    fail_across_addresses(TestClient(app.app), PASSWORD_FAILURE_CAP - PASSWORD_RESTART - 1, ('ana_putri',))
    assert failures(store) == {'sign_in_failures': PASSWORD_FAILURE_CAP - 1, 'sign_in_locked_until': None}
    # the 10th try after the lock: still checked (it is the 100th), here the right password: signs in and clears
    assert sign_in(TestClient(app.app), 'ana_putri', PASSWORD, '203.0.113.60').status_code == 200
    assert failures(store) == {'sign_in_failures': 0, 'sign_in_locked_until': None}


# ---- R1-7: a re-enrolment waits beside the confirmed authenticator ---------------------------------------------------

def test_the_confirmed_authenticator_works_until_the_new_one_is_proved(app, store, on):
    flows = app.app.state.auth_flows
    now = {'t': 1_800_000_000.0}
    flows.clock = lambda: now['t']
    h = admin_sign_in(app)
    first = app.post('/api/v1/auth/mfa/enroll', headers=h).json()
    old = base64.b32decode(first['secret'] + '=' * (-len(first['secret']) % 8))
    step = int(now['t']) // 30
    ok = app.post('/api/v1/auth/mfa/verify', headers=h, json={'code': mfa.code_at(old, step)})
    assert ok.status_code == 200
    h_ok = {**ORIGIN, 'X-CSRF-Token': ok.json()['csrf_token']}
    second = app.post('/api/v1/auth/mfa/enroll', headers=h_ok).json()
    new = base64.b32decode(second['secret'] + '=' * (-len(second['secret']) % 8))
    # meanwhile the old authenticator and an old recovery code still sign in; a new recovery code does not yet
    other = TestClient(app.app)
    now['t'] += 30
    assert other.post('/api/v1/auth/mfa/verify', headers=admin_sign_in(other),
                      json={'code': mfa.code_at(old, step + 1)}).status_code == 200
    other = TestClient(app.app)
    assert error_code(other.post('/api/v1/auth/mfa/verify', headers=admin_sign_in(other),
                                 json={'recovery_code': second['recovery_codes'][0]})) == 'MFA_CODE_INVALID'
    other = TestClient(app.app)
    assert other.post('/api/v1/auth/mfa/verify', headers=admin_sign_in(other),
                      json={'recovery_code': first['recovery_codes'][0]}).status_code == 200
    # a code of the new authenticator confirms it: from then on the old one and its codes stop
    now['t'] += 30
    assert app.post('/api/v1/auth/mfa/verify', headers=h_ok, json={'code': mfa.code_at(new, step + 2)}).status_code == 200
    assert db(store, 'SELECT pending_nonce FROM edge_bff.mfa_totp') == [{'pending_nonce': None}]
    now['t'] += 30
    other = TestClient(app.app)
    assert error_code(other.post('/api/v1/auth/mfa/verify', headers=admin_sign_in(other),
                                 json={'code': mfa.code_at(old, step + 3)})) == 'MFA_CODE_INVALID'
    other = TestClient(app.app)
    assert error_code(other.post('/api/v1/auth/mfa/verify', headers=admin_sign_in(other),
                                 json={'recovery_code': first['recovery_codes'][1]})) == 'MFA_CODE_INVALID'
    other = TestClient(app.app)
    assert other.post('/api/v1/auth/mfa/verify', headers=admin_sign_in(other),
                      json={'recovery_code': second['recovery_codes'][0]}).status_code == 200


# ---- R2-29: the scrypt cost ------------------------------------------------------------------------------------------

def legacy_verifier(password):
    salt = secrets.token_bytes(16)
    value = hashlib.scrypt(security.normal_password(password).encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    return f'scrypt${salt.hex()}${value.hex()}'


def test_new_verifiers_carry_the_owasp_cost_and_old_ones_still_check():
    made = security.password_verifier('a long enough password')
    assert made.startswith('scrypt$n=16384,r=8,p=5$') and security.verifier_parts(made)[0] == security.COST
    assert security.verify_password('a long enough password', made)
    old = legacy_verifier('a long enough password')
    assert security.verify_password('a long enough password', old) and security.needs_rehash(old)
    assert not security.needs_rehash(made)
    # an unknown cost is never derived (a verifier cannot ask for an unbounded derivation)
    assert not security.verify_password('x', made.replace('p=5', 'p=9'))
    assert not security.is_verifier('scrypt$n=1048576,r=8,p=1$' + '0' * 32 + '$' + '0' * 64)


def test_a_check_costs_the_same_whatever_the_verifiers_age(monkeypatch):
    work = []
    real = security._derive
    monkeypatch.setattr(security, '_derive', lambda text, salt, cost: work.append(cost[2]) or real(text, salt, cost))
    security.verify_password('a long enough password', security.password_verifier('a long enough password'))
    new, work[:] = sum(work[1:]), []                      # the first derivation made the verifier
    security.verify_password('a long enough password', legacy_verifier('a long enough password'))
    assert new == sum(work) == security.COST[2]


def test_a_sign_in_replaces_a_verifier_of_the_old_cost(app, store):
    make_account(app, store)
    db(store, "UPDATE edge_bff.identities SET verifier = %s WHERE user_id = (SELECT user_id FROM edge_bff.users "
              "WHERE email = 'ana@example.com')", legacy_verifier(PASSWORD))
    assert sign_in(TestClient(app.app), 'ana_putri', PASSWORD).status_code == 200
    stored = db(store, "SELECT verifier FROM edge_bff.identities i JOIN edge_bff.users u USING (user_id) "
                       "WHERE u.email = 'ana@example.com'")[0]['verifier']
    assert stored.startswith('scrypt$n=16384,r=8,p=5$') and security.verify_password(PASSWORD, stored)
    assert sign_in(TestClient(app.app), 'ana_putri', PASSWORD).status_code == 200


def test_the_configured_verifier_may_be_of_either_cost(settings):
    import dataclasses
    for verifier in (legacy_verifier('local-test-password'), security.password_verifier('local-test-password')):
        dataclasses.replace(settings, password_verifier=verifier).validate()
    with pytest.raises(ValueError, match='EDGE_PASSWORD_VERIFIER'):
        dataclasses.replace(settings, password_verifier='scrypt$n=16384,r=8,p=7$' + '0' * 32 + '$' + '0' * 64).validate()


# ---- R2-24: what the outbox purge keeps ------------------------------------------------------------------------------

def test_the_outbox_purge_keeps_an_accounts_rows_and_unsent_rows(store):
    db(store, "INSERT INTO edge_bff.users(owner_key, username, email, status) VALUES ('u_' || repeat('a', 24), "
              "'kept_one', 'kept@example.com', 'active')")
    for key, to, status in (('a', 'kept@example.com', 'sent'), ('b', 'gone@example.com', 'sent'),
                            ('c', 'gone@example.com', 'failed'), ('d', 'gone@example.com', 'pending'),
                            ('e', 'fresh@example.com', 'sent')):
        db(store, "INSERT INTO edge_bff.email_outbox(idempotency_key, purpose, to_email, status, sent_at, created_at) "
                  "VALUES (%s, 'reset', %s, %s, CASE WHEN %s = 'sent' THEN now() END, now() - interval '25 hours')",
           key, to, status, status)
    db(store, "UPDATE edge_bff.email_outbox SET created_at = now() WHERE idempotency_key = 'e'")
    store.cleanup_sessions()
    assert sorted(r['idempotency_key'] for r in outbox(store)) == ['a', 'd', 'e']


# ---- R2-10: the 60-second gap reads the purposes of the email codes ------------------------------------------------

def test_the_code_purposes_of_the_send_gap_are_those_of_the_email_codes_table(store):
    from app.auth_flows import CODE_PURPOSES
    check = db(store, "SELECT pg_get_constraintdef(oid) AS d FROM pg_constraint WHERE conrelid = "
                      "'edge_bff.email_codes'::regclass AND contype = 'c' "
                      "AND pg_get_constraintdef(oid) LIKE '%%purpose = ANY%%'")
    assert len(check) == 1
    assert sorted(re.findall(r"'([a-z_]+)'::text", check[0]['d'])) == sorted(CODE_PURPOSES)


# ---- R2-37: the password pool's admission --------------------------------------------------------------------------

def test_a_request_over_the_password_pools_limit_is_answered_503_at_once(settings, store, monkeypatch):
    monkeypatch.setattr(PasswordWork, 'LIMIT', 0)
    with TestClient(create_app(settings, store, FakeOrc())) as c:
        r = sign_in(c, 'owner', 'local-test-password')
        assert (r.status_code, error_code(r), r.headers['retry-after']) == (503, 'SERVICE_UNAVAILABLE', '5')
        assert db(store, 'SELECT count(*) AS n FROM edge_bff.auth_throttle')[0]['n'] == 0    # no try was counted
    monkeypatch.setattr(PasswordWork, 'LIMIT', 16)
    with TestClient(create_app(settings, store, FakeOrc())) as c:
        login(c)
