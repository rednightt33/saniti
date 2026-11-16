"""EXEC-MU-ACCOUNTS Phase 1 (contract sections 4 and 12; user decisions: English labels, registration fields, password at
least 8, a 5-minute code that signs in directly, forgot password -> code -> new password -> sign in, admin MFA with an
authenticator app): the account pages of the shell, in a browser. The account routes are B1b's: they are stood in for
here with Playwright routes, so the page is checked against the contract's shapes. The real server answers
/api/v1/auth/config with 404 until B1b adds it, which the page reads as "registration closed"."""
import json
import os
import re

import pytest

from test_answer_view import fixture_server  # noqa: F401 (fixture)


@pytest.fixture
def page():
    playwright = pytest.importorskip('playwright.sync_api')
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.environ.get('EDGE_TEST_CHROMIUM', '/usr/bin/chromium'), headless=True, args=['--no-sandbox'])
        page = browser.new_page(viewport={'width': 1280, 'height': 900})
        page.set_default_timeout(5000)
        page.route('https://fonts.*/*', lambda route: route.abort())
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        try:
            yield page
            assert not errors, errors
        finally:
            browser.close()


def answer(route, status, body):
    route.fulfill(status=status, content_type='application/json', body=json.dumps(body))


def test_without_open_registration_the_sign_in_page_is_as_before(fixture_server, page):
    origin, _ = fixture_server
    page.goto(origin + '/login')
    page.get_by_label('Login', exact=True).wait_for()
    assert page.get_by_role('heading', name='Welcome to Edge').is_visible()
    assert page.get_by_text('Create account').count() == 0 and page.get_by_text('Forgot password?').count() == 0


def test_register_then_the_code_page(fixture_server, page):
    origin, _ = fixture_server
    sent = []
    page.route('**/api/v1/auth/config', lambda r: answer(r, 200, {'multiuser': True}))
    page.route('**/api/v1/auth/register', lambda r: (sent.append(r.request.post_data_json), answer(r, 202, {'status': 'CODE_SENT'})))
    page.route('**/api/v1/auth/register/verify', lambda r: (sent.append(r.request.post_data_json),
               answer(r, 400, {'error': {'code': 'CODE_INVALID_OR_EXPIRED', 'message': 'That code is not valid or has expired.', 'details': {}}})))
    page.goto(origin + '/login')
    page.get_by_role('link', name='Create account').click()
    page.wait_for_function("() => location.pathname === '/register' && document.title === 'EDGE — Create Account'")
    for label, value in (('Username', 'new_user'), ('First name', 'Ana'), ('Last name', 'Putri'), ('Email', 'ana@example.com'),
                         ('Phone', '0812 3456 7890'), ('Password', 'longenough1'), ('Repeat password', 'longenough2')):
        page.get_by_label(label, exact=True).fill(value)
    page.get_by_role('button', name='Create account').click()
    assert page.get_by_role('alert').inner_text() == 'The two passwords are not the same.'
    assert sent == []                                            # checked here before anything is sent
    page.get_by_label('Repeat password', exact=True).fill('longenough1')
    page.get_by_role('button', name='Create account').click()
    page.wait_for_function("() => location.pathname === '/verify'")
    assert sent[0] == {'username': 'new_user', 'first_name': 'Ana', 'last_name': 'Putri', 'email': 'ana@example.com',
                       'phone': '0812 3456 7890', 'password': 'longenough1', 'password_repeat': 'longenough1'}
    # the same page whatever the server knows (no account enumeration): the code was sent to the address given
    assert page.get_by_text('We sent a code to ana@example.com.').is_visible()
    assert re.fullmatch(r'The code expires in (5:00|4:5\d)\.', page.get_by_role('timer').inner_text())
    assert page.get_by_text('You can send a new code in').is_visible()
    assert page.get_by_role('button', name='Send a new code').count() == 0    # resend only after 60 s
    code = page.get_by_label('Code', exact=True)
    assert code.get_attribute('autocomplete') == 'one-time-code' and code.get_attribute('inputmode') == 'numeric'
    code.fill('12a3456')
    assert code.input_value() == '123456'
    page.get_by_role('button', name='Verify').click()
    page.get_by_role('alert').wait_for()
    assert page.get_by_role('alert').inner_text() == 'That code is not valid or has expired.'   # the server's message
    assert sent[1] == {'email': 'ana@example.com', 'code': '123456'}
    # the username was taken meanwhile (decided only after the code is proved): the page asks for another one
    page.unroute('**/api/v1/auth/register/verify')
    page.route('**/api/v1/auth/register/verify', lambda r: (sent.append(r.request.post_data_json),
               answer(r, 409, {'error': {'code': 'USERNAME_TAKEN', 'message': 'That username is taken. Choose another one.', 'details': {}}})
               if 'username' not in r.request.post_data_json else answer(r, 200, {'authenticated': True, 'login': 'ana_p', 'csrf_token': 't'})))
    page.get_by_role('button', name='Verify').click()
    page.get_by_label('New username', exact=True).wait_for()
    assert page.get_by_role('alert').inner_text() == 'That username is taken. Choose another one.'
    page.get_by_label('New username', exact=True).fill('ana_p')
    page.get_by_role('button', name='Verify').click()
    page.wait_for_function("() => location.pathname !== '/verify'")
    assert sent[2:] == [{'email': 'ana@example.com', 'code': '123456'}, {'email': 'ana@example.com', 'code': '123456', 'username': 'ana_p'}]


def test_a_refused_sign_in_points_a_new_account_to_its_code(fixture_server, page):
    """A pending account's sign-in answers the generic 401 INVALID_CREDENTIALS (no enumeration; the server emails a new
    code and sets the registration cookie): with registration open the page adds where to enter the code."""
    origin, _ = fixture_server
    refused = {'error': {'code': 'INVALID_CREDENTIALS', 'message': 'The login or the password is not right.', 'details': {}}}
    page.route('**/api/v1/auth/sign-in', lambda r: answer(r, 401, refused))
    page.goto(origin + '/login')
    page.get_by_label('Login', exact=True).fill('ana@example.com')
    page.get_by_label('Password', exact=True).fill('a long enough password')
    page.get_by_role('button', name='Sign In').click()
    page.get_by_role('alert').wait_for()
    assert page.get_by_role('link', name='Verify page').count() == 0       # registration closed: the message only
    page.route('**/api/v1/auth/config', lambda r: answer(r, 200, {'multiuser': True}))
    page.goto(origin + '/login')
    page.get_by_label('Login', exact=True).fill('ana@example.com')
    page.get_by_label('Password', exact=True).fill('a long enough password')
    page.get_by_role('button', name='Sign In').click()
    page.get_by_role('alert').wait_for()
    assert page.get_by_role('alert').inner_text() == 'The login or the password is not right.'
    assert 'If you have just registered, check your email for a code' in page.locator('.auth-note').inner_text()
    page.get_by_role('link', name='Verify page').click()
    page.wait_for_function("() => location.pathname === '/verify'")
    assert page.get_by_text('Enter the code in the same browser where you registered.').is_visible()
    assert page.get_by_text('We sent a code to ana@example.com.').is_visible()


def test_forgot_password_code_new_password_back_to_sign_in(fixture_server, page):
    origin, _ = fixture_server
    sent = []
    page.route('**/api/v1/auth/config', lambda r: answer(r, 200, {'multiuser': True}))
    page.route('**/api/v1/auth/password/forgot', lambda r: (sent.append(r.request.post_data_json), answer(r, 202, {'status': 'CODE_SENT'})))
    page.route('**/api/v1/auth/password/reset', lambda r: (sent.append(r.request.post_data_json), answer(r, 200, {'next': 'sign_in'})))
    page.goto(origin + '/login')
    page.get_by_role('link', name='Forgot password?').click()
    page.get_by_label('Email', exact=True).fill('ana@example.com')
    page.get_by_role('button', name='Send code').click()
    page.wait_for_function("() => location.pathname === '/reset'")
    page.get_by_label('Code', exact=True).fill('654321')
    page.get_by_label('New password', exact=True).fill('short')
    page.get_by_label('Repeat new password', exact=True).fill('short')
    page.get_by_role('button', name='Change password').click()
    assert page.get_by_role('alert').inner_text() == 'The password needs at least 8 characters.'
    page.get_by_label('New password', exact=True).fill('a new password')
    page.get_by_label('Repeat new password', exact=True).fill('a new password')
    page.get_by_role('button', name='Change password').click()
    page.wait_for_function("() => location.pathname === '/login'")
    assert page.get_by_role('status').inner_text() == 'Your password was changed. Sign in with the new password.'
    assert sent == [{'email': 'ana@example.com'}, {'email': 'ana@example.com', 'code': '654321', 'password': 'a new password',
                                                   'password_repeat': 'a new password'}]


def test_admin_mfa_enrol_shows_a_local_qr_code_and_the_recovery_codes_once(fixture_server, page):
    origin, _ = fixture_server
    calls, outside = [], []
    page.route(re.compile(r'^https?://(?!127\.0\.0\.1).*'), lambda r: (outside.append(r.request.url), r.abort()))
    page.route('**/api/v1/auth/sign-in', lambda r: answer(r, 403, {'error': {'code': 'MFA_REQUIRED', 'message': 'Enter your authenticator code.', 'details': {'csrf_token': 'pending-token'}}}))
    codes = [f'code-{i:02d}' for i in range(10)]
    page.route('**/api/v1/auth/mfa/enroll', lambda r: (calls.append(('enroll', r.request.headers.get('x-csrf-token'))),
               answer(r, 200, {'otpauth_uri': 'otpauth://totp/EDGE:owner?secret=JBSWY3DPEHPK3PXP&issuer=EDGE', 'recovery_codes': codes})))
    page.route('**/api/v1/auth/mfa/verify', lambda r: (calls.append(('verify', r.request.headers.get('x-csrf-token'), r.request.post_data_json)), answer(r, 200, {'ok': True})))
    page.goto(origin + '/login')
    page.get_by_label('Login', exact=True).fill('owner')
    page.get_by_label('Password', exact=True).fill('local-test-password')
    page.get_by_role('button', name='Sign In').click()
    page.wait_for_function("() => location.pathname === '/mfa' && document.title === 'EDGE — Authenticator'")
    page.get_by_role('button', name='Set up an authenticator app').click()
    qr = page.locator('svg.auth-qr path')
    qr.wait_for()
    assert len(qr.get_attribute('d')) > 1000                    # drawn here from the URI, by static/qrcode-generator.js
    assert page.get_by_text('JBSWY3DPEHPK3PXP').is_visible()
    assert page.locator('.auth-codes li').all_inner_texts() == codes
    continue_button = page.get_by_role('button', name='Continue')
    page.get_by_label('Code', exact=True).fill('123456')
    assert continue_button.is_disabled()                        # the codes are confirmed saved first
    page.get_by_label('I have saved my recovery codes').check()
    continue_button.click()
    page.wait_for_function("() => location.pathname !== '/mfa'")
    assert calls == [('enroll', 'pending-token'), ('verify', 'pending-token', {'code': '123456'})]
    assert [u for u in outside if not u.startswith('https://fonts.')] == []    # no QR service is asked
