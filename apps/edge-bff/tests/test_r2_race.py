"""EXEC-MU-ACCOUNTS re-check, round 2 (checker C2-RACE, lens: concurrency and races). Failing tests of verified findings.

Each test runs the requests concurrently in threads against the real Postgres cluster (EDGE_TEST_POSTGRES_URL). A
threading.Event holds one request at the point a real request spends its time (the Pwned Passwords range call, the
scrypt derivation) while the other request runs, so the interleaving a burst or a slow network gives is reproduced
every time.

R2-RACE-1: a credential or session write authorised by a proof read before a concurrent password reset lands after it.
  - a password change in flight (its current password proved, its new password at the Pwned check) overwrites the
    password a reset set a moment later, although the reset revoked the changing session;
  - a sign-in in flight with the old password (its verifier read, its derivations running) makes a live session after
    the reset revoked every session, so the reset does not end the access of someone who held the old password.
R2-RACE-2: the MFA consecutive-failure cap and its lock are read outside any lock of the account: every try of a burst
  reaches the code check, past the 100-failure cap (TOTP) or past the restart allowance after a lock ended (recovery).
"""
import hashlib
import threading

import pytest
from fastapi.testclient import TestClient

from app import auth_flows as flows_module
from app import main as main_module
from app import mfa
from app.security import normal_password
from test_auth_flows import (PASSWORD, admin_sign_in, app, cooldown_over, db, error_code, hour_over,  # noqa: F401
                             last_code, make_account, on, outbox)
from test_edge import ORIGIN

ATTACKER_PASSWORD = 'the attacker chose this one'
RESET_PASSWORD = 'the owner reset to this one'
WAIT = 20


def range_prefix(password):
    return hashlib.sha1(normal_password(password).encode('utf-8', 'surrogatepass')).hexdigest().upper()[:5]


def reset_by_email(client, store, email, password):
    """The owner's "Forgot password?" and reset, from a browser with no session."""
    cooldown_over(store)
    assert client.post('/api/v1/auth/password/forgot', headers=ORIGIN, json={'email': email}).status_code == 202
    body = {'email': email, 'code': last_code(store, email), 'password': password, 'password_repeat': password}
    r = client.post('/api/v1/auth/password/reset', headers=ORIGIN, json=body)
    assert r.status_code == 200, r.text


def sign_in_status(client, password):
    return client.post('/api/v1/auth/sign-in', headers=ORIGIN,
                       json={'login': 'ana_putri', 'password': password}).status_code


def run_in_thread(fn):
    out = {}

    def target():
        try:
            out['value'] = fn()
        except BaseException as e:                     # noqa: BLE001 - re-raised in the test thread
            out['error'] = e
    t = threading.Thread(target=target, daemon=True)
    t.start()
    return t, out


# ---- R2-RACE-1 ---------------------------------------------------------------------------------------------------------

def test_a_password_change_in_flight_does_not_undo_a_password_reset(app, store):
    """CONTRACT.md section 4: a reset revokes every session, and the reset's password is the account's. A change whose
    current password was proved before the reset, and whose write lands after it, must not replace the reset's
    password: its session was revoked by the reset. Today store.change writes the verifier unconditionally
    (auth_flows.py:290-307), so the holder of a stolen session and the old password keeps the account through a reset."""
    r = make_account(app, store)                       # the stolen session: its holder also knows PASSWORD
    stolen = {**ORIGIN, 'X-CSRF-Token': r.json()['csrf_token']}
    flows = app.app.state.auth_flows
    reached, release = threading.Event(), threading.Event()

    def pwned_range(prefix):                           # the range API call of the change's new password is slow
        if prefix == range_prefix(ATTACKER_PASSWORD):
            reached.set()
            release.wait(WAIT)
        return ''
    flows.pwned_fetch = pwned_range
    body = {'current_password': PASSWORD, 'password': ATTACKER_PASSWORD, 'password_repeat': ATTACKER_PASSWORD}
    thread, out = run_in_thread(lambda: app.post('/api/v1/auth/password/change', headers=stolen, json=body))
    try:
        assert reached.wait(WAIT), 'the change never reached the Pwned check'
        owner = TestClient(app.app)                    # the account's owner, in another browser
        reset_by_email(owner, store, 'ana@example.com', RESET_PASSWORD)
        assert db(store, 'SELECT count(*) AS n FROM edge_bff.sessions WHERE revoked_at IS NULL')[0]['n'] == 0
    finally:
        release.set()
        thread.join(WAIT)
    assert 'error' not in out, out.get('error')
    probe = TestClient(app.app)
    assert (sign_in_status(probe, RESET_PASSWORD), sign_in_status(probe, ATTACKER_PASSWORD)) == (200, 401), (
        'the change that began before the reset replaced the reset password: '
        f'change answered {out["value"].status_code} {out["value"].text}')


def test_a_sign_in_in_flight_does_not_outlive_a_password_reset(app, store, monkeypatch):
    """CONTRACT.md section 4 ("Revoke all on password change or reset"): after a reset no session of the account is
    live. A sign-in with the old password whose verifier was read before the reset, and whose session is made after it
    (main.py:610-641: find_login, then 1 + PENDING_CHECKED derivations, then create_session with no check that the
    verifier it proved is still the account's), leaves a live session the reset never revoked."""
    make_account(app, store)
    real = main_module.verify_password
    reached, release = threading.Event(), threading.Event()
    armed = {'on': True}

    def slow_verify(password, verifier):              # the derivations of the in-flight sign-in take their time
        if armed['on'] and password == PASSWORD:
            armed['on'] = False
            reached.set()
            release.wait(WAIT)
        return real(password, verifier)
    monkeypatch.setattr(main_module, 'verify_password', slow_verify)
    holder = TestClient(app.app)                       # someone who holds the old password
    thread, out = run_in_thread(lambda: holder.post('/api/v1/auth/sign-in', headers=ORIGIN,
                                                    json={'login': 'ana_putri', 'password': PASSWORD}))
    try:
        assert reached.wait(WAIT), 'the sign-in never reached its password derivation'
        reset_by_email(TestClient(app.app), store, 'ana@example.com', RESET_PASSWORD)
    finally:
        release.set()
        thread.join(WAIT)
    assert 'error' not in out, out.get('error')
    live = db(store, 'SELECT count(*) AS n FROM edge_bff.sessions WHERE revoked_at IS NULL')[0]['n']
    session = holder.get('/api/v1/auth/session').status_code
    assert (live, session) == (0, 401), (
        f'a sign-in proved by the replaced password made a live session after the reset (sign-in answered '
        f'{out["value"].status_code}; live sessions {live}; its session read answers {session})')


def test_an_mfa_code_confirms_only_the_enrolment_it_was_checked_against(app, store, on, monkeypatch):
    """auth_flows.py:553-574: mfa/verify reads the enrolment (store.totp), checks the code against that row's nonce, then
    use_step confirms whatever row the account holds now (WHERE user_id AND last_step < step: no nonce in it). An enrol
    of another pending session landing in between (store.enroll upserts a new nonce with last_step NULL) is confirmed
    by the admin's code: the admin sees 200 and mfa_ok, the authenticator the admin scanned no longer works, and the
    confirmed second factor is the other session's (it has the password, and now the factor)."""
    flows = app.app.state.auth_flows
    now = {'t': 1_800_000_000.0}
    flows.clock = lambda: now['t']
    admin = admin_sign_in(app)
    mine = app.post('/api/v1/auth/mfa/enroll', headers=admin).json()['secret']
    other = TestClient(app.app)                        # another pending session of the account (the password only)
    other_h = admin_sign_in(other)
    real_use = flows.store.use_step
    reached, release = threading.Event(), threading.Event()

    def use_step(user_id, step):                       # the admin's code was checked; its confirmation is on its way
        reached.set()
        release.wait(WAIT)
        return real_use(user_id, step)
    monkeypatch.setattr(flows.store, 'use_step', use_step)
    import base64
    secret = base64.b32decode(mine + '=' * (-len(mine) % 8))
    step = int(now['t']) // 30
    thread, out = run_in_thread(lambda: app.post('/api/v1/auth/mfa/verify', headers=admin,
                                                 json={'code': mfa.code_at(secret, step)}))
    try:
        assert reached.wait(WAIT), 'the verify never reached its confirmation'
        # today 200: the enrolment was not confirmed yet when this enrol was checked (a fix may refuse it instead)
        theirs = other.post('/api/v1/auth/mfa/enroll', headers=other_h)
    finally:
        release.set()
        thread.join(WAIT)
    monkeypatch.setattr(flows.store, 'use_step', real_use)
    assert 'error' not in out, out.get('error')
    if out['value'].status_code != 200:
        return                                         # the admin was told the code did not confirm: nothing to check
    # the admin's verify answered 200 (mfa_ok): the factor confirmed must be the one the admin's code was checked against
    fresh = TestClient(app.app)
    now['t'] += 30                                     # a later step: no replay of the step used above
    h = admin_sign_in(fresh)
    admin_code = fresh.post('/api/v1/auth/mfa/verify', headers=h,
                            json={'code': mfa.code_at(secret, step + 1)}).status_code
    their_code = None
    if theirs.status_code == 200:
        their_secret = base64.b32decode(theirs.json()['secret'] + '=' * (-len(theirs.json()['secret']) % 8))
        now['t'] += 30
        h = admin_sign_in(fresh)
        their_code = fresh.post('/api/v1/auth/mfa/verify', headers=h,
                                json={'code': mfa.code_at(their_secret, step + 2)}).status_code
    assert admin_code == 200 and their_code != 200, (
        "the admin's verify answered 200, but it confirmed the enrolment another session made after the admin's code "
        f"was checked: the admin's authenticator now answers {admin_code}, the other session's answers {their_code}")



# ---- R2-RACE-2 ---------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('field, failures, locked_until, allowed', [
    # the 100th consecutive TOTP failure starts the 24-hour lock (NIST SP 800-63B-4: at most 100 consecutive failures)
    ('code', flows_module.TOTP_FAILURE_CAP - 1, None, 1),
    # a recovery lock that ended a second ago leaves RECOVERY_FAILURE_CAP - RECOVERY_RESTART tries (N2)
    ('recovery_code', flows_module.RECOVERY_FAILURE_CAP, 1_800_000_000 - 1,
     flows_module.RECOVERY_FAILURE_CAP - flows_module.RECOVERY_RESTART)])
def test_a_burst_at_the_mfa_cap_checks_only_the_tries_left(app, store, on, monkeypatch, field, failures, locked_until,
                                                            allowed):
    """auth_flows.py:553-579: the consecutive-failure count and its lock are read (store.totp) in one transaction,
    lock_over restarts the count in a second and mfa_failed adds the failure in a third, none under a lock of the
    account. Tries sent together all read the same count, so every try of a burst reaches the code check (up to
    MFA_USER, 10 per 15 minutes): past the 100-failure cap (TOTP at 99: all 5 checked, 104 consecutive failures) or
    past the restart allowance after a lock ended (recovery: 5 checked where 2 are left)."""
    flows = app.app.state.auth_flows
    now = {'t': 1_800_000_000.0}
    flows.clock = lambda: now['t']
    h = admin_sign_in(app)
    app.post('/api/v1/auth/mfa/enroll', headers=h)
    kind = 'totp' if field == 'code' else 'recovery'
    db(store, f'UPDATE edge_bff.mfa_totp SET confirmed_at = now(), {kind}_failures = %s, {kind}_locked_until = %s',
       failures, locked_until)
    burst = 5
    # the tries of the burst arrive together: each has read the row before any of them goes on. A build that reads the
    # row under a lock of the account never fills the barrier; its tries then go on one by one after the short timeout
    gate = threading.Barrier(burst, timeout=3)
    real_totp = flows.store.totp

    def totp(user_id):
        row = real_totp(user_id)
        try:
            gate.wait()
        except threading.BrokenBarrierError:
            pass
        return row
    monkeypatch.setattr(flows.store, 'totp', totp)
    db(store, 'DELETE FROM edge_bff.auth_throttle')
    wrong = '000000' if field == 'code' else 'aaaaa-aaaaa'
    threads = [run_in_thread(lambda: app.post('/api/v1/auth/mfa/verify', headers=h, json={field: wrong}))
               for _ in range(burst)]
    for t, _ in threads:
        t.join(WAIT)
    assert all('error' not in out for _, out in threads), [out.get('error') for _, out in threads]
    answers = sorted(error_code(out['value']) for _, out in threads)
    checked = answers.count('MFA_CODE_INVALID')       # a try whose wrong code was checked (MFA_LOCKED: not checked)
    row = db(store, f'SELECT {kind}_failures AS n FROM edge_bff.mfa_totp')[0]
    assert checked == allowed, (
        f'{checked} of {burst} parallel {field} tries were checked (allowed {allowed}); answers {answers}; '
        f'consecutive failures now {row["n"]}')


# ---- R2-RACE-4 ---------------------------------------------------------------------------------------------------------

def reset_codes(store, email):
    return [r for r in outbox(store, email) if r['purpose'] == 'reset']


def test_a_password_changed_email_does_not_hold_back_the_reset_it_asks_for(app, store):
    """email_texts.py:42-47: the password_changed email says 'If you did not, use "Forgot password?" ... at once'. The
    send rule of every code email (auth_flows.py:137-143, _may_send) refuses when ANY outbox row to the address is
    younger than 60 s, and the notification is such a row (enqueue, auth_flows.py:286, 307). So the reset asked for at
    once answers 202 CODE_SENT and mails nothing; whoever holds a session and the password (it set it) keeps every
    reset email of the owner back by changing the password at least once a minute (a successful change clears its own
    throttle, auth_flows.py:516)."""
    r = make_account(app, store)
    h = {**ORIGIN, 'X-CSRF-Token': r.json()['csrf_token']}
    cooldown_over(store)                               # the registration code email is older than a minute
    body = {'current_password': PASSWORD, 'password': ATTACKER_PASSWORD, 'password_repeat': ATTACKER_PASSWORD}
    assert app.post('/api/v1/auth/password/change', headers=h, json=body).status_code == 200
    assert outbox(store, 'ana@example.com')[-1]['purpose'] == 'password_changed'
    owner = TestClient(app.app)
    answer = owner.post('/api/v1/auth/password/forgot', headers=ORIGIN, json={'email': 'ana@example.com'})
    assert answer.json() == flows_module.ACCEPTED      # the page tells the owner a code was sent
    assert len(reset_codes(store, 'ana@example.com')) == 1, (
        'the reset the password_changed email asks for was answered CODE_SENT but no reset code was queued')


def test_a_strangers_registration_does_not_hold_back_the_owners_reset(app, store):
    """The same rule from another user: anyone who registers with the owner's address (the 'account exists' email,
    once an hour, REGISTER_HOUR) holds the owner's "Forgot password?" back for the next 60 s, with the same 202
    CODE_SENT. That email too tells the owner to use "Forgot password?"."""
    make_account(app, store)
    hour_over(store)                                   # the account's own registration is more than an hour old
    stranger = TestClient(app.app)
    body = {'username': 'someone_else', 'first_name': 'S', 'last_name': 'T', 'email': 'ana@example.com',
            'phone': '0812 0000 0000', 'password': 'a stranger password', 'password_repeat': 'a stranger password'}
    assert stranger.post('/api/v1/auth/register', headers=ORIGIN, json=body).status_code == 202
    assert outbox(store, 'ana@example.com')[-1]['purpose'] == 'account_exists'
    owner = TestClient(app.app)
    assert owner.post('/api/v1/auth/password/forgot', headers=ORIGIN,
                      json={'email': 'ana@example.com'}).json() == flows_module.ACCEPTED
    assert len(reset_codes(store, 'ana@example.com')) == 1, (
        "a stranger's registration held back the owner's reset code: 202 CODE_SENT and no code queued")
