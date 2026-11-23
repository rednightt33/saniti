"""Step 9, the registration test window: the paths around the core rehearsal (tests/test_step9_window.py), carried from
the test-out of 2026-11-23 (workflow wf_4181198a-09f, step9-window, F6). Each runs on the live site's settings against
one database.

Two assert today's residuals and change with the user's decisions (AGENTS.md "Findings and fixes", rule 7):
test_p1 (one client mails any number of addresses while open: UD7, the per-client send limit) and test_p7 (three other
clients push a pending registration out: UD22). test_p2 holds the mask of a window session at close (ERRORS M549, a
carried part); test_p8 the beta's 'Resend code' after close (the same entry).
"""
import dataclasses

import psycopg
from fastapi.testclient import TestClient

from app.main import create_app
from conftest import FakeOrc
from test_a2_stranger import ELSEWHERE, OWNER, STRANGER, at
from test_admin import passed
from test_auth_flows import PASSWORD, cooldown_over, db, error_code, hour_over, last_code, outbox, register, verify
from test_beta_live_site import live_of

CODE = 'c' * 40
KEY = 'm' * 40


def sites(settings):
    beta = dataclasses.replace(settings, mfa_key=KEY, code_secret=CODE)
    live = live_of(beta)
    return beta, dataclasses.replace(live, prelaunch_enabled=False), dataclasses.replace(live, prelaunch_enabled=None)


def client(s, store):
    application = create_app(s, store, FakeOrc())
    application.state.auth_flows.pwned_fetch = lambda prefix: ''
    return TestClient(application)


def body(email, username, password=PASSWORD):
    return {'username': username, 'first_name': 'Ana', 'last_name': 'Putri', 'email': email, 'phone': '0812 3456 7890',
            'password': password, 'password_repeat': password}


def account(c, store, email='ana@example.com', username='ana_putri', ip=OWNER):
    assert c.post('/api/v1/auth/register', headers=at(ip), json=body(email, username)).status_code == 202
    r = c.post('/api/v1/auth/register/verify', headers=at(ip), json={'email': email, 'code': last_code(store, email)})
    assert r.status_code == 200, r.text
    return r


def carry(src, dst):
    for name, value in dict(src.cookies).items():
        dst.cookies.set(name, value)


# 1. mail per client while open ---------------------------------------------------------------------------------------
def test_p1_one_client_mails_any_number_of_addresses_while_open(settings, store):
    _, opened, _ = sites(settings)
    with client(opened, store) as c:
        for n in range(25):
            r = c.post('/api/v1/auth/register', headers=at(STRANGER), json=body(f'victim{n}@example.org', f'victim_{n}'))
            assert r.status_code == 202, r.text
    sent = db(store, "SELECT count(*) AS n FROM edge_bff.email_outbox WHERE purpose='register'")[0]['n']
    pending = db(store, "SELECT count(*) AS n FROM edge_bff.users WHERE status='pending'")[0]['n']
    print(f'P1: one client address, 25 addresses -> {sent} code mails queued, {pending} pending rows')
    assert sent == 25 and pending == 25


# 2. close masks the window session, does not revoke it ---------------------------------------------------------------
def test_p2_close_does_not_revoke_and_the_session_returns_on_reopen_or_test_mark(settings, store):
    _, opened, closed = sites(settings)
    with client(opened, store) as c:
        account(c, store)
        assert c.get('/api/v1/auth/session').status_code == 200
        cookies = dict(c.cookies)
    with client(closed, store) as c:
        for k, v in cookies.items():
            c.cookies.set(k, v)
        assert c.get('/api/v1/auth/session').status_code == 401
        rows = db(store, "SELECT count(*) AS n FROM edge_bff.sessions s JOIN edge_bff.users u USING (user_id) "
                         "WHERE u.username='ana_putri' AND s.revoked_at IS NULL AND s.expires_at > now()")
        print(f'P2: after close, un-revoked unexpired sessions of the window account: {rows[0]["n"]}')
        assert rows[0]['n'] == 1
    with client(opened, store) as c:                          # the window opened again (a retry)
        for k, v in cookies.items():
            c.cookies.set(k, v)
        reopened = c.get('/api/v1/auth/session').status_code
    uid = db(store, "SELECT user_id FROM edge_bff.users WHERE username='ana_putri'")[0]['user_id']
    with psycopg.connect(closed.database_url) as conn:
        conn.execute('''INSERT INTO edge_bff.admin_audit(action, target_user_id, after, reason)
            VALUES ('account.test_mark', %s, '{"test_account": true}', 'operator: probe')''', (uid,))
        conn.execute('UPDATE edge_bff.users SET test_account = true WHERE user_id = %s', (uid,))
    with client(closed, store) as c:
        for k, v in cookies.items():
            c.cookies.set(k, v)
        marked = c.get('/api/v1/auth/session').status_code
    print(f'P2: the old cookie on reopen -> {reopened}; closed and marked test_account, no sign-in -> {marked}')
    assert (reopened, marked) == (200, 200)


# 3. the beta's admin page lists and disables the window's accounts; a pending one rests on the purge ------------------
def test_p3_beta_lists_and_disables_the_window_accounts(settings, store):
    beta, opened, closed = sites(settings)
    with client(opened, store) as c:
        account(c, store)
        window_cookies = dict(c.cookies)
        assert c.post('/api/v1/auth/register', headers=at(ELSEWHERE),
                      json=body('budi@example.com', 'budi_s')).status_code == 202
    with client(beta, store) as b:
        h = passed(b, store, beta)
        listed = b.get('/api/v1/admin/users', headers=h).json()['users']
        top = [(u['status'], u.get('username') or u.get('requested_username')) for u in listed[:3]]
        print('P3: beta list, newest first:', top)
        assert listed[0]['status'] == 'pending' and listed[1]['status'] == 'active'
        r = b.post(f"/api/v1/admin/users/{listed[0]['user_id']}/status", headers=h,
                   json={'status': 'disabled', 'reason': 'window close'})
        print('P3: disable a pending registration ->', r.status_code, r.json().get('error', {}).get('details'))
        assert r.status_code == 400
        r = b.post(f"/api/v1/admin/users/{listed[1]['user_id']}/status", headers=h,
                   json={'status': 'disabled', 'reason': 'window close'})
        assert r.status_code == 200 and r.json()['changed'] is True, r.text
        print('P3: disable the window account ->', r.json())
    with client(closed, store) as c:
        for k, v in window_cookies.items():
            c.cookies.set(k, v)
        assert c.get('/api/v1/auth/session').status_code == 401
        c.cookies.clear()
        r = c.post('/api/v1/auth/sign-in', headers=at(OWNER), json={'login': 'ana_putri', 'password': PASSWORD})
        print('P3: disabled account sign-in after close ->', r.status_code, error_code(r))
    with client(opened, store) as c:                           # and if the window opens again
        r = c.post('/api/v1/auth/sign-in', headers=at(OWNER), json={'login': 'ana_putri', 'password': PASSWORD})
        assert r.status_code == 401
    assert db(store, "SELECT status FROM edge_bff.users WHERE username='ana_putri'")[0]['status'] == 'disabled'


# 4. the pending purge, as the runtime role when EDGE_TEST_APP_ROLE is set ---------------------------------------------
def test_p4_a_pending_registration_is_purged_after_24h(settings, store):
    _, opened, closed = sites(settings)
    with client(opened, store) as c:
        assert c.post('/api/v1/auth/register', headers=at(ELSEWHERE),
                      json=body('budi@example.com', 'budi_s')).status_code == 202
    with psycopg.connect(closed.database_url) as conn:
        conn.execute("UPDATE edge_bff.users SET created_at = now() - interval '23 hours' WHERE email='budi@example.com'")
    assert store.purge('pending', 500) == 0
    with psycopg.connect(closed.database_url) as conn:
        conn.execute("UPDATE edge_bff.users SET created_at = now() - interval '25 hours' WHERE email='budi@example.com'")
    gone = store.purge('pending', 500)
    left = db(store, "SELECT count(*) AS n FROM edge_bff.users WHERE email='budi@example.com'")[0]['n']
    mails = store.purge('outbox', 500)
    print(f'P4: purge pending -> {gone} deleted, {left} left; outbox purge -> {mails}')
    assert gone == 1 and left == 0


# 5. a password reset across the close -----------------------------------------------------------------------------------
def test_p5_reset_asked_while_open_used_after_close_and_asked_after_close(settings, store):
    _, opened, closed = sites(settings)
    with client(opened, store) as c:
        account(c, store)
        c.cookies.clear()
        assert c.post('/api/v1/auth/password/forgot', headers=at(OWNER), json={'email': 'ana@example.com'}).status_code == 202
        code = last_code(store, 'ana@example.com')
        browser = dict(c.cookies)
    with client(closed, store) as c:
        for k, v in browser.items():
            c.cookies.set(k, v)
        r = c.post('/api/v1/auth/password/reset', headers=at(OWNER), json={'email': 'ana@example.com', 'code': code,
                   'password': 'a brand new password', 'password_repeat': 'a brand new password'})
        set_cookie = r.headers.get_list('set-cookie') if hasattr(r.headers, 'get_list') else r.headers.get('set-cookie')
        print('P5: reset after close with the open-time code ->', r.status_code, r.json())
        assert r.status_code == 200 and r.json() == {'next': 'sign_in'}
        r = c.post('/api/v1/auth/sign-in', headers=at(OWNER), json={'login': 'ana_putri', 'password': 'a brand new password'})
        assert (r.status_code, error_code(r)) == (403, 'SIGN_IN_CLOSED')
        cooldown_over(store)
        before = len(outbox(store, 'ana@example.com'))
        assert c.post('/api/v1/auth/password/forgot', headers=at(OWNER), json={'email': 'ana@example.com'}).status_code == 202
        queued = len(outbox(store, 'ana@example.com')) - before
        print(f'P5: forgot after close -> {queued} mail queued; set-cookie of the reset: {set_cookie}')
        assert queued == 1


# 6. the same address twice ---------------------------------------------------------------------------------------------
def test_p6_same_address_twice(settings, store):
    _, opened, _ = sites(settings)
    with client(opened, store) as c:
        assert c.post('/api/v1/auth/register', headers=at(OWNER), json=body('ana@example.com', 'ana_putri')).status_code == 202
        first = last_code(store, 'ana@example.com')
        cooldown_over(store)
        r = c.post('/api/v1/auth/register', headers=at(OWNER), json=body('ana@example.com', 'ana_other'))
        same_client = (r.status_code, len(outbox(store, 'ana@example.com')),
                       db(store, "SELECT count(*) AS n FROM edge_bff.users WHERE email='ana@example.com'")[0]['n'])
        print('P6: same client again in the hour -> (status, mails, rows)', same_client)
        assert same_client == (202, 1, 1)
        other = client(opened, store)
        with other:
            hour_over(store)
            assert other.post('/api/v1/auth/register', headers=at(STRANGER),
                              json=body('ana@example.com', 'eve_x', 'the strangers password')).status_code == 202
        rows = db(store, "SELECT count(*) AS n FROM edge_bff.users WHERE email='ana@example.com'")[0]['n']
        r = c.post('/api/v1/auth/register/verify', headers=at(OWNER), json={'email': 'ana@example.com', 'code': first})
        after = db(store, "SELECT username, status FROM edge_bff.users WHERE email='ana@example.com'")
        print(f'P6: another client -> {rows} rows; the owner verifies its first code -> {r.status_code}; left {after}')
        assert rows == 2 and r.status_code == 200 and after == [{'username': 'ana_putri', 'status': 'active'}]
        hour_over(store)
        before = len(outbox(store, 'ana@example.com'))
        third = client(opened, store)
        with third:
            assert third.post('/api/v1/auth/register', headers=at(ELSEWHERE),
                              json=body('ana@example.com', 'eve_y')).status_code == 202
        kinds = [m['purpose'] for m in outbox(store, 'ana@example.com')][before:]
        print('P6: an address with an account -> mails', kinds)


# 7. UD22 under the window's settings ------------------------------------------------------------------------------------
def test_p7_ud22_reachable_on_the_window_settings(settings, store):
    _, opened, _ = sites(settings)
    with client(opened, store) as c:
        assert c.post('/api/v1/auth/register', headers=at(OWNER), json=body('ana@example.com', 'ana_putri')).status_code == 202
        for n, ip in enumerate(('198.51.100.71', '198.51.100.72', '198.51.100.73')):
            hour_over(store)
            r = client(opened, store).post('/api/v1/auth/register', headers=at(ip),
                                           json=body('ana@example.com', f'eve_{n}', 'the strangers password'))
            assert r.status_code == 202
        cooldown_over(store)
        mails = len(outbox(store, 'ana@example.com'))
        r = client(opened, store).post('/api/v1/auth/sign-in', headers=at(ELSEWHERE),
                                       json={'login': 'ana@example.com', 'password': PASSWORD})
        print('P7: owner sign-in to restart its pending registration ->', r.status_code, 'restart mails',
              len(outbox(store, 'ana@example.com')) - mails)
        assert (r.status_code, len(outbox(store, 'ana@example.com')) - mails) == (401, 0)


# 8. after close, the beta still offers and sends "Resend code" for a pending window registration --------------------------
def test_p8_beta_resend_code_after_close(settings, store):
    beta, opened, closed = sites(settings)
    with client(opened, store) as c:
        assert c.post('/api/v1/auth/register', headers=at(ELSEWHERE),
                      json=body('budi@example.com', 'budi_s')).status_code == 202
        browser = dict(c.cookies)
    cooldown_over(store)
    with client(beta, store) as b:
        h = passed(b, store, beta)
        uid = db(store, "SELECT user_id FROM edge_bff.users WHERE email='budi@example.com'")[0]['user_id']
        offered = b.get(f'/api/v1/admin/users/{uid}', headers=h).json()['actions']['resend_code']
        before = len(outbox(store, 'budi@example.com'))
        r = b.post(f'/api/v1/admin/users/{uid}/resend-code', headers=h, json={'reason': 'after close'})
        queued = len(outbox(store, 'budi@example.com')) - before
    with client(closed, store) as c:
        for k, v in browser.items():
            c.cookies.set(k, v)
        v = c.post('/api/v1/auth/register/verify', headers=at(ELSEWHERE),
                   json={'email': 'budi@example.com', 'code': last_code(store, 'budi@example.com')})
    print(f'P8: beta offers resend {offered}; resend -> {r.status_code}, {queued} mail queued; live verify -> '
          f'{v.status_code} {error_code(v)}')


# 9. after close, every GET route answers the masked window cookie as it answers no cookie ----------------------------------
def test_p9_every_get_route_treats_the_masked_cookie_as_no_cookie(settings, store):
    _, opened, closed = sites(settings)
    with client(opened, store) as c:
        account(c, store)
        cookies = dict(c.cookies)
    app = create_app(closed, store, FakeOrc())
    paths = sorted({r.path for r in app.routes if 'GET' in getattr(r, 'methods', set()) and '{' not in r.path
                    and r.path.startswith('/api/')})
    differ = []
    with TestClient(app) as anon, TestClient(app) as masked:
        for k, v in cookies.items():
            masked.cookies.set(k, v)
        for p in paths:
            a = anon.get(p, headers=at(OWNER)); m = masked.get(p, headers=at(OWNER))
            if (a.status_code, a.content) != (m.status_code, m.content):
                differ.append((p, a.status_code, m.status_code))
    print(f'P9: {len(paths)} GET /api routes walked; differing answers: {differ}')
    assert not [d for d in differ if d[1] != d[2]]
