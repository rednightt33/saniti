"""C1 re-check of the EXEC-MU-ACCOUNTS Phase 1 fix round (53da005b, migration 20261117_002): failing tests for what the
fixes left open or added (no fix here)."""
from fastapi.testclient import TestClient

from app import main as main_module
from app import mfa
from test_auth_flows import (admin_sign_in, app, cooldown_over, db, error_code, last_code, on,  # noqa: F401
                             register, verify)
from test_edge import ORIGIN

PROBE_PASSWORD = 'attacker chose this one'


def sign_in(c, login, password):
    return c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': login, 'password': password})


def test_c1_p1r_sign_in_costs_the_same_whether_or_not_an_address_has_an_account(app, store, monkeypatch):
    """Enumeration by timing (OWASP Authentication: same response time). main.py sign_in runs one scrypt for an active
    account but one per pending registration (up to PENDING_CHECKED = 3) when the address has none. Anyone makes those
    pending registrations: register the address from two browsers 61 s apart. Then a sign-in with any password costs
    two scrypts (about 2 x 50-100 ms) when the address is free and one when it has an account. Run the same number of
    password derivations in every case (always PENDING_CHECKED, padding with the configured verifier)."""
    assert register(app, 'taken@example.com', 'taken_1').status_code == 202
    assert verify(app, last_code(store, 'taken@example.com'), 'taken@example.com').status_code == 200
    calls = []
    real = main_module.verify_password
    monkeypatch.setattr(main_module, 'verify_password', lambda pw, v: calls.append(1) or real(pw, v))
    cost = {}
    for email in ('taken@example.com', 'free@example.com'):
        for n in range(2):
            cooldown_over(store)
            assert register(TestClient(app.app), email, f'probe{n}_' + email[:4], password=PROBE_PASSWORD).status_code == 202
        calls.clear()
        assert sign_in(TestClient(app.app), email, 'not the password at all').status_code == 401
        cost[email] = len(calls)
    assert cost['taken@example.com'] == cost['free@example.com'], cost


def test_c1_p1r_a_failed_sign_in_does_not_lose_this_browsers_registration(app, store):
    """Every switch-on 401 sets a new registration cookie (flows.restart_registration), replacing the one this browser
    got from its own registration a moment earlier. One mistyped sign-in (or a sign-in to another account) between
    "register" and "enter the code" orphans the registration: the correct code then answers 400
    CODE_INVALID_OR_EXPIRED and the person must register again. Keep an existing valid registration cookie on a 401
    that restarted nothing (the answer can still always carry a Set-Cookie)."""
    assert register(app, 'ana@example.com', 'ana_putri').status_code == 202
    code = last_code(store, 'ana@example.com')
    assert sign_in(app, 'someone_else', 'a wrong password here').status_code == 401
    r = verify(app, code, 'ana@example.com')
    assert r.status_code == 200, r.text


def test_c1_p1r_the_mfa_lock_has_a_way_back_for_the_real_admin(app, store, on):
    """MFA_LOCKED (100 wrong codes, 10 wrong recovery codes) is cleared only by a success, which the lock itself
    refuses; nothing else resets totp_failures or recovery_failures (no time limit, no admin route, not a password
    reset). Whoever holds the admin's password can lock the only admin out for good in about three hours (the 15-minute
    throttle allows 10 tries each), and the real admin, with the right password and authenticator, cannot get back in
    without editing the database. NIST SP 800-63B-4 rate limiting expects a path back (a delay that ends, or account
    recovery). Give the lock an end (e.g. 24 h) or clear it by a proved recovery (password reset by email, an admin)."""
    flows = app.app.state.auth_flows
    now = {'t': 1_800_000_000.0}
    flows.clock = lambda: now['t']
    h = admin_sign_in(app)
    app.post('/api/v1/auth/mfa/enroll', headers=h)
    # what a password holder reaches after 100 wrong codes and 10 wrong recovery codes
    db(store, 'UPDATE edge_bff.mfa_totp SET confirmed_at = now(), totp_failures = 100, recovery_failures = 10')
    row = db(store, 'SELECT user_id, nonce FROM edge_bff.mfa_totp')[0]
    good = mfa.code_at(mfa.secret_of(on.mfa_key, row['user_id'], bytes(row['nonce'])), int(now['t']) // 30 + 2880)
    now['t'] += 86400                                                  # a day later, the real admin signs in
    db(store, 'DELETE FROM edge_bff.auth_throttle')
    h = admin_sign_in(app)
    r = app.post('/api/v1/auth/mfa/verify', headers=h, json={'code': good})
    assert r.status_code == 200, f'the real admin stays locked out: {r.status_code} {r.text}'
