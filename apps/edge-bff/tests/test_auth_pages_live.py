"""EXEC-MU-ACCOUNTS Phase 1: the account pages of the shell against the real routes of edge-bff with the switch on
(app/auth_flows.py, app/mfa.py; the codes read from the email outbox, as the user reads them in the email). Nothing is
stood in except the Pwned Passwords range API."""
import base64
import dataclasses
import socket
import threading
import time

import pytest
import uvicorn

from app import mfa
from app.main import create_app
from conftest import FakeOrc
from test_auth_pages import page  # noqa: F401 (fixture)

PASSWORD = 'a long enough password'


def db(store, sql, *args):
    with store.connect() as c:
        cur = c.execute(sql, args)
        return cur.fetchall() if cur.description else cur.rowcount


def last_code(store, email):
    rows = [r for r in db(store, 'SELECT * FROM edge_bff.email_outbox WHERE to_email=%s ORDER BY outbox_id', email)
            if r['purpose'] in ('register', 'reset')]
    return rows[-1]['payload']['mask'][0]


@pytest.fixture
def live(settings, store):
    sock = socket.socket(); sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    on = dataclasses.replace(settings, origin=f'http://127.0.0.1:{port}', multiuser=True, code_secret='c' * 40,
                             mfa_key='m' * 40)
    application = create_app(on, store, FakeOrc())
    application.state.auth_flows.pwned_fetch = lambda prefix: ''        # never the real API in a test
    server = uvicorn.Server(uvicorn.Config(application, log_level='critical', access_log=False))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True); thread.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.02)
    assert server.started
    try:
        yield on, store
    finally:
        server.should_exit = True; thread.join(timeout=10); sock.close()


def fill_register(page, phone='0812 3456 7890', username='ana_putri'):
    for label, value in (('Username', username), ('First name', 'Ana'), ('Last name', 'Putri'), ('Email', 'ana@example.com'),
                         ('Phone', phone), ('Password', PASSWORD), ('Repeat password', PASSWORD)):
        page.get_by_label(label, exact=True).fill(value)
    page.get_by_role('button', name='Create account').click()


def test_register_with_the_emailed_code_signs_in_directly(live, page):
    on, store = live
    page.goto(on.origin + '/login')
    page.get_by_role('link', name='Create account').click()              # shown: GET /api/v1/auth/config is on
    assert page.get_by_label('Phone', exact=True).get_attribute('required') is not None   # the phone is mandatory
    fill_register(page, phone='call me')
    page.locator('.field-error').first.wait_for()                         # the server's reason under its field
    assert page.locator('#phone-error').inner_text()
    assert db(store, 'SELECT count(*) AS n FROM edge_bff.email_outbox')[0]['n'] == 0
    page.get_by_label('Phone', exact=True).fill('0812 3456 7890')
    page.get_by_role('button', name='Create account').click()
    page.wait_for_function("() => location.pathname === '/verify'")
    assert page.get_by_text('We sent a code to ana@example.com.').is_visible()
    assert page.get_by_text('You can send a new code in').is_visible()   # resend_after_s of the answer
    page.get_by_label('Code', exact=True).fill(last_code(store, 'ana@example.com'))
    page.get_by_role('button', name='Verify').click()
    page.get_by_placeholder('Ask a research question…').wait_for()       # signed in directly (user decision)
    session = page.evaluate("() => fetch('/api/v1/auth/session').then(r => r.json())")
    assert session['username'] == 'ana_putri' and session['owner_key'].startswith('u_')
    assert page.evaluate("() => localStorage.getItem('edge-last-login')") == 'owner:' + session['owner_key']


def test_forgot_password_resets_and_the_new_password_signs_in(live, page):
    on, store = live
    page.goto(on.origin + '/login')
    page.get_by_role('link', name='Create account').click()
    fill_register(page)
    page.wait_for_function("() => location.pathname === '/verify'")
    page.get_by_label('Code', exact=True).fill(last_code(store, 'ana@example.com'))
    page.get_by_role('button', name='Verify').click()
    page.get_by_placeholder('Ask a research question…').wait_for()
    page.evaluate("() => Edge.signout()")
    # one code per email per 60 s (contract section 4): the registration's code is a minute old here
    db(store, "UPDATE edge_bff.email_outbox SET created_at = created_at - interval '61 seconds'")
    page.goto(on.origin + '/login')
    page.get_by_role('link', name='Forgot password?').click()
    page.get_by_label('Email', exact=True).fill('ana@example.com')
    page.get_by_role('button', name='Send code').click()
    page.wait_for_function("() => location.pathname === '/reset'")
    page.get_by_label('Code', exact=True).fill(last_code(store, 'ana@example.com'))
    page.get_by_label('New password', exact=True).fill('another long password')
    page.get_by_label('Repeat new password', exact=True).fill('another long password')
    page.get_by_role('button', name='Change password').click()
    page.wait_for_function("() => location.pathname === '/login'")
    assert page.get_by_role('status').inner_text() == 'Your password was changed. Sign in with the new password.'
    page.get_by_label('Login', exact=True).fill('ana_putri')
    page.get_by_label('Password', exact=True).fill('another long password')
    page.get_by_role('button', name='Sign In').click()
    page.get_by_placeholder('Ask a research question…').wait_for()


def test_the_admin_enrols_the_authenticator_and_signs_in(live, page):
    on, store = live
    page.goto(on.origin + '/login')
    page.get_by_label('Login', exact=True).fill('owner')
    page.get_by_label('Password', exact=True).fill('local-test-password')
    page.get_by_role('button', name='Sign In').click()
    page.wait_for_function("() => location.pathname === '/mfa'")
    page.locator('svg.auth-qr path').wait_for()                            # details.mfa_enrolled false: the set-up
    assert page.locator('.auth-codes li').count() == 10
    user_id, nonce = (lambda r: (r['user_id'], bytes(r['nonce'])))(db(store, 'SELECT user_id, nonce FROM edge_bff.mfa_totp')[0])
    secret = mfa.secret_of(on.mfa_key, user_id, nonce)
    assert page.get_by_text(base64.b32encode(secret).decode().rstrip('=')).is_visible()
    page.get_by_label('Code', exact=True).fill(mfa.code_at(secret, mfa.step_now()))
    page.get_by_label('I have saved my recovery codes').check()
    page.get_by_role('button', name='Continue').click()
    page.get_by_placeholder('Ask a research question…').wait_for()
