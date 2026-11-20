"""The live checker after the switch-on (2026-11-20, ERRORS M515 ACC-1, ACC-2, ACC-3): the admin's authenticator on the
live site, through the real routes and the page in Chromium (site live, pre-launch, guests).

- ACC-1: a new phone. The /mfa page asks for a code (the current authenticator's or a recovery code) before a new
  authenticator may be set up; the verify answers a fresh session, and the page must then show the new QR code and
  recovery codes (it used to leave for the workspace, so a lost phone could only spend recovery codes). Confirmed, the
  new authenticator signs in and the old one no longer does. A signed-in admin starts the same from "Password and
  sign-in".
- ACC-2: with the recovery codes locked, the page keeps the authenticator path open (Continue enabled, the words name
  the way still open) and the authenticator's code signs in.
- ACC-3: the phone and every recovery code lost: the operator removes the enrolment (scripts/edge_mfa_unlock.py
  --remove-enrolment, audited, the sessions ended); the next sign-in starts the first set-up again.
The test that stubbed the verify's answer (tests/test_decisions_small.py) could not see ACC-1: the real route answers a
session, which re-routes the page."""
import dataclasses
import importlib.util
import json
import socket
import time
from pathlib import Path

import pytest

from app import mfa
from app.auth_flows import RECOVERY_FAILURE_CAP
from test_auth_pages import page  # noqa: F401 (fixture)
from test_auth_pages_live import db, serve
from test_beta_live_site import PASSWORD, live_of


@pytest.fixture
def livesite(settings, store):
    sock = socket.socket(); sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    on = dataclasses.replace(live_of(settings), origin=f'http://127.0.0.1:{port}', guests_enabled=True,
                             prelaunch_enabled=True)
    server, thread = serve(on, store, port, sock)
    try:
        yield on, store
    finally:
        server.should_exit = True; thread.join(timeout=10); sock.close()


def sign_in(page, on):
    page.goto(on.origin + '/login')
    page.get_by_label('Login', exact=True).fill('owner')
    page.get_by_label('Password', exact=True).fill(PASSWORD)
    page.get_by_role('button', name='Sign In').click()
    page.wait_for_function("() => location.pathname === '/mfa'")


def secrets_of(on, store):
    """The secret of the confirmed enrolment and of a set-up waiting beside it (None when none)."""
    r = db(store, 'SELECT user_id, nonce, pending_nonce FROM edge_bff.mfa_totp')[0]
    return (mfa.secret_of(on.mfa_key, r['user_id'], bytes(r['nonce'])),
            mfa.secret_of(on.mfa_key, r['user_id'], bytes(r['pending_nonce'])) if r['pending_nonce'] else None)


def confirm(page, secret, step):
    """The set-up page: the QR code and the recovery codes are shown; the new code confirms it."""
    page.locator('svg.auth-qr path').first.wait_for()
    codes = page.locator('.auth-codes li').all_inner_texts()
    assert len(codes) == 10, codes
    page.get_by_label('Code', exact=True).fill(mfa.code_at(secret, step))
    page.get_by_label('I have saved my recovery codes').check()
    page.get_by_role('button', name='Continue').click()
    page.wait_for_function("() => window.Edge && Edge.auth && Edge.auth.access && Edge.auth.access.mfa_ok "
                           "&& location.pathname !== '/mfa'")
    return codes


def first_enrolment(page, on, store):
    sign_in(page, on)
    page.locator('svg.auth-qr path').first.wait_for()
    codes = confirm(page, secrets_of(on, store)[0], mfa.step_now())
    page.evaluate('() => Edge.signout()')
    return secrets_of(on, store)[0], codes


def new_set_up_after(page, on, store, enter):
    """Signed in up to /mfa, "Set up an authenticator app", the refusal asks for a recent code, `enter` gives it; the
    page must then show the new authenticator's set-up (ACC-1)."""
    sign_in(page, on)
    page.get_by_role('button', name='Set up an authenticator app').click()
    page.get_by_role('alert').wait_for()
    enter()
    page.wait_for_function("() => location.pathname === '/mfa' && document.querySelector('svg.auth-qr path')")
    old, new = secrets_of(on, store)
    assert new is not None                          # the new authenticator waits on the server
    return old, new


def test_a_recovery_code_then_the_new_authenticator_is_set_up_and_signs_in(livesite, page):
    on, store = livesite
    old, codes = first_enrolment(page, on, store)

    def recovery():
        page.get_by_role('button', name='Use a recovery code instead').click()
        page.get_by_label('Recovery code', exact=True).fill(codes[0])
        page.get_by_role('button', name='Continue').click()
    _, new = new_set_up_after(page, on, store, recovery)
    confirm(page, new, mfa.step_now())
    assert secrets_of(on, store) == (new, None)     # the new one is the account's; nothing waits
    page.evaluate('() => Edge.signout()')
    sign_in(page, on)                               # the old phone's code is refused, the new one signs in
    page.get_by_label('Code', exact=True).fill(mfa.code_at(old, mfa.step_now() + 1))
    page.get_by_role('button', name='Continue').click()
    page.get_by_role('alert').wait_for()
    assert page.evaluate('location.pathname') == '/mfa'
    page.get_by_label('Code', exact=True).fill(mfa.code_at(new, mfa.step_now() + 1))
    page.get_by_role('button', name='Continue').click()
    page.wait_for_function("() => Edge.auth && Edge.auth.access && Edge.auth.access.mfa_ok && location.pathname !== '/mfa'")


def test_the_old_phones_code_then_the_new_authenticator_is_set_up(livesite, page):
    on, store = livesite
    old, _ = first_enrolment(page, on, store)

    def old_code():
        page.get_by_label('Code', exact=True).fill(mfa.code_at(old, mfa.step_now() + 1))    # the next step: no replay
        page.get_by_role('button', name='Continue').click()
    _, new = new_set_up_after(page, on, store, old_code)
    confirm(page, new, mfa.step_now())             # a new secret: its own steps (use_step checks none for it)
    assert secrets_of(on, store) == (new, None)


def test_a_signed_in_admin_sets_up_a_new_authenticator_from_password_and_sign_in(livesite, page):
    on, store = livesite
    sign_in(page, on)
    page.locator('svg.auth-qr path').first.wait_for()
    confirm(page, secrets_of(on, store)[0], mfa.step_now())     # signed in, the second factor passed just now
    page.get_by_role('button', name='Account menu').first.click()
    page.get_by_role('menuitem', name='Password and sign-in').click()
    page.get_by_role('button', name='Set up a new authenticator').click()
    page.wait_for_function("() => location.pathname === '/mfa' && document.querySelector('svg.auth-qr path')")
    _, new = secrets_of(on, store)
    assert new is not None
    confirm(page, new, mfa.step_now() + 1)
    assert secrets_of(on, store) == (new, None)


def test_locked_recovery_codes_leave_the_authenticator_open(livesite, page):
    on, store = livesite
    old, _ = first_enrolment(page, on, store)
    db(store, 'UPDATE edge_bff.mfa_totp SET recovery_failures = %s', RECOVERY_FAILURE_CAP - 1)
    sign_in(page, on)
    page.get_by_role('button', name='Use a recovery code instead').click()
    for _ in range(2):                              # the cap's try, then a try while locked
        page.get_by_label('Recovery code', exact=True).fill('not-a-recovery-code')
        page.get_by_role('button', name='Continue').click()
        page.get_by_role('alert').wait_for()
        time.sleep(0.3)
    words = page.get_by_role('alert').inner_text()
    assert 'recovery codes are locked' in words and 'authenticator app' in words, words
    assert page.get_by_label('Code', exact=True).count() == 1           # back on the authenticator's code
    assert page.get_by_role('button', name='Continue').is_enabled()
    page.get_by_label('Code', exact=True).fill(mfa.code_at(old, mfa.step_now() + 1))
    page.get_by_role('button', name='Continue').click()
    page.wait_for_function("() => Edge.auth && Edge.auth.access && Edge.auth.access.mfa_ok && location.pathname !== '/mfa'")


def test_the_operator_removes_a_lost_authenticator_and_the_next_sign_in_sets_up_anew(livesite, page, database,
                                                                                       monkeypatch, capsys):
    on, store = livesite
    first_enrolment(page, on, store)
    spec = importlib.util.spec_from_file_location('edge_mfa_unlock',
                                                  Path(__file__).resolve().parents[3] / 'scripts/edge_mfa_unlock.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv('DATABASE_URL', database)
    capsys.readouterr()
    assert module.main(['--username', 'owner', '--reason', 'lost phone and codes, the owner asked',
                        '--remove-enrolment']) == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out['outcome'] == 'removed' and out['before']['enrolled'] is True and out['after']['enrolled'] is False
    assert db(store, 'SELECT count(*) AS n FROM edge_bff.mfa_totp') == [{'n': 0}]
    assert db(store, 'SELECT count(*) AS n FROM edge_bff.mfa_recovery_codes') == [{'n': 0}]
    assert db(store, 'SELECT count(*) AS n FROM edge_bff.sessions WHERE revoked_at IS NULL') == [{'n': 0}]
    assert [r['action'] for r in db(store, 'SELECT action FROM edge_bff.admin_audit')] == ['mfa.remove']
    sign_in(page, on)                               # the first set-up again
    page.locator('svg.auth-qr path').first.wait_for()
    confirm(page, secrets_of(on, store)[0], mfa.step_now() + 1)
