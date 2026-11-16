"""C1 adversarial security check of EXEC-MU-ACCOUNTS Phase 1 (accounts): failing tests for the findings (no fix here).
Contract: verification/edge_multiuser/access_tiers/CONTRACT.md sections 0-6; OWASP Authentication / Forgot Password /
Session Management cheat sheets; NIST SP 800-63B-4."""
import base64
import dataclasses
import re
import time

from app import mfa
from test_auth_flows import (PASSWORD, admin_sign_in, app, cooldown_over, db, error_code, last_code, on,  # noqa: F401
                             register, verify)
from test_edge import ORIGIN

VICTIM = 'victim@example.com'
ATTACKER_PASSWORD = 'attacker chose this one'


def sign_in(c, login, password):
    return c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': login, 'password': password})


def test_c1_p1_a_second_registration_cannot_set_the_password_of_a_pending_one(app, store):
    """Pre-verification account takeover. FlowStore.register (auth_flows.py) answers a new registration for an address
    that has a *pending* account by replacing that account's password verifier (and requested username) and mailing a
    new code to the address. The victim registers, the attacker registers the victim's address 61 s later with a
    password of its own, the victim enters the code it receives (the newest one), is signed in, and the account's
    password is now the attacker's: the attacker signs in to the victim's account with the victim's email.
    The code proves the mailbox, not who chose the password; keep the first password until the code is proved, or
    bind the code to the registration (verifier) that asked for it."""
    assert register(app, VICTIM, 'victim_1').status_code == 202
    cooldown_over(store)
    assert register(app, VICTIM, 'attacker_1', password=ATTACKER_PASSWORD).status_code == 202
    r = verify(app, last_code(store, VICTIM), VICTIM)                 # the victim enters the code it just received
    assert r.status_code == 200, r.text
    app.cookies.clear()
    taken = sign_in(app, VICTIM, ATTACKER_PASSWORD)
    assert taken.status_code == 401, f'the attacker signed in to the victim account: {taken.status_code} {taken.text}'


def test_c1_p1_register_then_sign_in_does_not_tell_whether_an_email_has_an_account(app, store):
    """Enumeration. register answers 202 alike (CONTRACT.md section 4), but for a free address it makes a pending
    account with the caller's password, and for a taken one it makes nothing. The caller then signs in with that address
    and its own password: 403 EMAIL_NOT_VERIFIED means "no account here", 401 INVALID_CREDENTIALS means "an account
    exists". Both answers must be the same (for example 401 for a pending account whose password is right, or the
    unverified message only together with a new code mailed to the address)."""
    assert register(app, 'taken@example.com', 'taken_1').status_code == 202
    assert verify(app, last_code(store, 'taken@example.com'), 'taken@example.com').status_code == 200
    app.cookies.clear()
    answers = {}
    for email in ('taken@example.com', 'free@example.com'):
        assert register(app, email, 'probe_' + email[:4], password=ATTACKER_PASSWORD).status_code == 202
        r = sign_in(app, email, ATTACKER_PASSWORD)
        answers[email] = (r.status_code, error_code(r))
    assert answers['taken@example.com'] == answers['free@example.com'], answers


def test_c1_p1_mfa_failures_are_capped_across_windows(app, store):
    """NIST SP 800-63B-4 (rate limiting): no more than 100 consecutive failed authentication attempts on one account.
    MFA_USER allows 10 failures per 15 minutes and the count only lapses with time, never accumulates: 960 TOTP guesses
    a day (about 3 in 10^6 each, with the +-1 step window), so a password holder breaks the second factor in weeks.
    After 100 consecutive failures the account's TOTP must stay refused until something else (a success, an admin)
    clears it."""
    h = admin_sign_in(app)
    app.post('/api/v1/auth/mfa/enroll', headers=h)
    failures = 0
    for window in range(12):
        for _ in range(10):
            r = app.post('/api/v1/auth/mfa/verify', headers=h, json={'code': '000000'})
            if r.status_code == 400:
                failures += 1
        # the window lapses (each window's rows moved back by a distinct amount, so no two land in one bucket)
        db(store, "UPDATE edge_bff.auth_throttle SET window_start = window_start - %s * interval '16 minutes' "
                  "WHERE window_start > now() - interval '15 minutes'", window + 1)
    assert failures <= 100, f'{failures} consecutive MFA failures were evaluated'


def test_c1_p1_the_session_token_changes_when_mfa_is_passed(app, store, on):
    """OWASP Session Management: renew the session ID after any privilege level change. The pending admin session
    (password only) becomes a full admin session by mfa_passed (UPDATE ... SET mfa_passed_at) with the same token, so a
    token observed while pending (before the second factor) is the full admin session afterwards."""
    flows = app.app.state.auth_flows
    now = {'t': 1_800_000_000.0}
    flows.clock = lambda: now['t']
    h = admin_sign_in(app)
    pending = app.cookies.get('edge_session')
    app.post('/api/v1/auth/mfa/enroll', headers=h)
    row = db(store, 'SELECT user_id, nonce FROM edge_bff.mfa_totp')[0]
    secret = mfa.secret_of(on.mfa_key, row['user_id'], bytes(row['nonce']))
    r = app.post('/api/v1/auth/mfa/verify', headers=h, json={'code': mfa.code_at(secret, int(now['t']) // 30)})
    assert r.status_code == 200
    assert app.cookies.get('edge_session') != pending, 'the pending token became the full admin session'


def test_c1_p1_secrets_are_not_in_the_settings_repr(on):
    """The new secrets are plain dataclass fields (config.py: code_secret, mfa_key, resend_api_key,
    resend_webhook_secret), so repr(settings), in a traceback, a debug log or an error report, prints them. Orc marks its
    keys field(repr=False); edge-bff should too (session_secret, orc_key, password_verifier included)."""
    s = dataclasses.replace(on, resend_api_key='re_secret_value_1234567890')
    text = repr(s)
    for secret in (s.code_secret, s.mfa_key, s.resend_api_key, s.resend_webhook_secret, s.session_secret):
        assert secret not in text


def test_c1_p1_a_password_is_normalised_before_hashing(app, store):
    """NIST SP 800-63B-4 (password verifiers): a password of Unicode characters SHOULD be normalised (NFKC or NFKD)
    before hashing, so the same password typed on another keyboard (é as one code point or as e + combining accent, as
    macOS and iOS may send it) signs in. passwords.py and security.py hash the text as received."""
    composed, decomposed = 'café au lait every day', 'café au lait every day'
    assert register(app, 'nfc@example.com', 'nfc_user', password=composed).status_code == 202
    assert verify(app, last_code(store, 'nfc@example.com'), 'nfc@example.com').status_code == 200
    app.cookies.clear()
    assert sign_in(app, 'nfc@example.com', decomposed).status_code == 200


def test_c1_p1_a_non_ascii_hook_signature_is_refused_not_a_server_error(app):
    """svix_verify compares str with hmac.compare_digest, which raises TypeError for non-ASCII text; a latin-1 byte in
    svix-signature turns the public webhook's 401 into an unhandled 503 (and any caller can trigger it)."""
    stamp = str(int(time.time()))
    r = app.post('/api/v1/hooks/email/resend', content=b'{}', headers={
        'svix-id': 'msg_1', 'svix-timestamp': stamp, 'svix-signature': 'v1,\xe9'.encode('latin-1')})
    assert (r.status_code, error_code(r)) == (401, 'HOOK_SIGNATURE_INVALID'), r.text
