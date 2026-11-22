"""Phase 4, the admin page's routes (CONTRACT.md 10; app/admin.py; the user, 2026-11-22: "1A 2A 3A", "1A, 2B, 3A").

- Every /api/v1/admin/* route depends on auth.admin_page (the admin right and the authenticator code), its writes with
  CSRF; only the code step itself rests on auth.admin. The live site answers 404 before any session.
- On the beta (the switch off, one password), the admin page asks for the authenticator code of user #1 (the user's
  "1A"); the session is renewed once it passed; every other route of the beta is as it was.
- The accounts are listed with their address and phone masked; a reveal needs a reason and writes its audit row in the
  same transaction. The audit and its spreadsheet file, whose cells are never formulas. The plans read-only (the
  user's 2A); the settings without a secret.
- The support inbox: a ticket in full, its images served as their own type and sandboxed, marked done or new and
  deleted by hand (the user's 2B), each audited by ids and kinds only."""
import dataclasses
import hashlib
import json
import os

import httpx
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app import admin as admin_module, mfa
from app.admin import IMAGE_CSP, SHOWN_SETTINGS
from app.auth_flows import TOTP_FAILURE_CAP
from app.config import Settings
from app.main import create_app
from app.support import SupportStore
from conftest import FakeOrc
from test_beta_live_site import live_of, sign_in_admin
from test_edge import ORIGIN, login
from test_principal import make_user, sign_in
from test_route_table import calls

PNG = b'\x89PNG\r\n\x1a\n' + bytes(range(256)) * 4
KEY = 'm' * 40


def db(store, sql, *args):
    with store.connect() as c:
        cur = c.execute(sql, args)
        return cur.fetchall() if cur.description else cur.rowcount


def error_of(r):
    return r.json()['error']


def seed_id(store, settings):
    return db(store, 'SELECT user_id FROM edge_bff.users WHERE owner_key = %s', settings.owner)[0]['user_id']


def enrol(store, user_id):
    """user #1's authenticator, as the live site's set-up leaves it (confirmed), and one recovery code."""
    nonce = os.urandom(16)
    db(store, 'INSERT INTO edge_bff.mfa_totp(user_id, nonce, confirmed_at) VALUES (%s, %s, now())', user_id, nonce)
    db(store, 'INSERT INTO edge_bff.mfa_recovery_codes(user_id, code_hash) VALUES (%s, %s)', user_id,
       mfa.recovery_hash(KEY, user_id, 'abcd-efgh-ijkl'))
    return nonce


def code_of(user_id, nonce, step=None):
    return mfa.code_at(mfa.secret_of(KEY, user_id, nonce), mfa.step_now() if step is None else step)


@pytest.fixture
def beta(settings):
    """The beta as it runs: the switch off, the live site's EDGE_MFA_KEY (config.shared_key_marks)."""
    return dataclasses.replace(settings, mfa_key=KEY)


def passed(c, store, settings):
    """The beta's owner past the admin page's code step; returns the write headers of the renewed session."""
    login(c)
    uid = seed_id(store, settings)
    nonce = enrol(store, uid)
    h = {**ORIGIN, 'X-CSRF-Token': c.get('/api/v1/auth/session').json()['csrf_token']}
    r = c.post('/api/v1/admin/step-up', headers=h, json={'code': code_of(uid, nonce)})
    assert r.status_code == 200, r.text
    return {**ORIGIN, 'X-CSRF-Token': r.json()['csrf_token']}


# ---- the gate ---------------------------------------------------------------------------------------------------------

def test_every_admin_route_needs_the_admin_page_gate_and_its_writes_csrf(beta, store):
    app = create_app(beta, store, FakeOrc())
    needs = app.state.auth._needs
    found = []
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith('/api/v1/admin'):
            continue
        for method in route.methods:
            write = method not in ('GET', 'HEAD')
            chain = set(calls(route.dependant))
            if route.path == '/api/v1/admin/step-up':                   # the code step: the admin right, before the code
                assert needs[('admin', 'admin.access', write)] in chain, (method, route.path)
            else:
                assert needs[('admin_page', write)] in chain, (method, route.path)
            found.append((method, route.path))
    assert len(found) >= 16 and ('DELETE', '/api/v1/admin/support/{ticket_id}') in found, found


def test_the_live_site_answers_404_to_every_admin_route_before_any_session(settings, store):
    live = live_of(settings)
    app = create_app(live, store, FakeOrc())
    with TestClient(app) as c:
        paths = [(m, r.path.replace('{user_id}', '1').replace('{ticket_id}', '1').replace('{position}', '1'))
                 for r in app.routes if isinstance(r, APIRoute) and r.path.startswith('/api/v1/admin') for m in r.methods]
        for method, path in paths:
            r = c.request(method, path, headers=ORIGIN, json={} if method != 'GET' else None)
            assert (r.status_code, error_of(r)['code']) == (404, 'NOT_FOUND'), (method, path, r.text)
        h = sign_in_admin(c, store)                                       # the admin too, past its second factor
        assert c.get('/api/v1/admin/overview').status_code == 404
        assert c.post('/api/v1/admin/step-up', headers=h, json={'code': '000000'}).status_code == 404


def test_on_the_beta_the_admin_page_asks_for_the_authenticator_code_and_nothing_else_does(beta, store):
    with TestClient(create_app(dataclasses.replace(beta, admin_owners=(beta.owner,)), store, FakeOrc())) as c:
        assert c.get('/api/v1/admin/overview').status_code == 401                          # no session
        h = login(c)
        uid = seed_id(store, beta)
        r = c.get('/api/v1/admin/overview')
        assert (r.status_code, error_of(r)['code'], error_of(r)['details']) == (403, 'MFA_REQUIRED',
                                                                             {'mfa_enrolled': True, 'step_up': True})
        assert 'authenticator code' in error_of(r)['message'] and 'recovery' not in error_of(r)['message']
        assert c.get('/api/v1/admin/step-up').json() == {'needed': True, 'enrolled': False, 'available': True}
        r = c.post('/api/v1/admin/step-up', headers=h, json={'code': '123456'})
        assert (r.status_code, error_of(r)['code']) == (400, 'MFA_NOT_ENROLLED')
        nonce = enrol(store, uid)
        assert c.get('/api/v1/admin/step-up').json()['enrolled'] is True
        r = c.post('/api/v1/admin/step-up', headers=h, json={'code': '000000' if code_of(uid, nonce) != '000000' else '111111'})
        assert (r.status_code, error_of(r)['code']) == (400, 'MFA_CODE_INVALID')
        assert c.post('/api/v1/admin/step-up', headers=ORIGIN, json={'code': code_of(uid, nonce)}).status_code == 403  # CSRF
        old = c.cookies.get('edge_session')
        r = c.post('/api/v1/admin/step-up', headers=h, json={'code': code_of(uid, nonce)})
        assert r.status_code == 200 and r.json()['step_up'] is True, r.text
        assert c.cookies.get('edge_session') != old                                        # a new session token
        assert c.get('/api/v1/admin/overview').status_code == 200
        assert c.get('/api/v1/admin/step-up').json()['needed'] is False
        revoked = db(store, 'SELECT revoked_at FROM edge_bff.sessions WHERE token_hash = %s',
                     hashlib.sha256(old.encode()).hexdigest())
        assert revoked and revoked[0]['revoked_at'] is not None
        # the beta's other pages ask nothing new: the owner's Monitor manual steps, the runs, the session
        assert c.get('/api/v1/auth/session').status_code == 200
        # a code is used once: the same step again, on a second session of the owner, is refused
        with TestClient(create_app(beta, store, FakeOrc())) as other:
            h2 = login(other)
            r = other.post('/api/v1/admin/step-up', headers=h2, json={'code': code_of(uid, nonce)})
            assert (r.status_code, error_of(r)['code']) == (400, 'MFA_CODE_INVALID')
            # a recovery code is refused unchecked (the user's "1A" names the 6-digit code; one spent here would be
            # gone on the live site): it stays unused
            r = other.post('/api/v1/admin/step-up', headers=h2, json={'recovery_code': 'abcd-efgh-ijkl'})
            assert (r.status_code, error_of(r)['details']['fields']) == (400, ['recovery_code']), r.text
            assert 'recovery codes for signing in on the live site' in error_of(r)['details']['reasons']['recovery_code']
            assert db(store, 'SELECT used_at FROM edge_bff.mfa_recovery_codes WHERE user_id = %s', uid) == [{'used_at': None}]
            r = other.post('/api/v1/admin/step-up', headers=h2, json={'code': code_of(uid, nonce), 'recovery_code': 'x'})
            assert (r.status_code, error_of(r)['details']['fields']) == (400, ['recovery_code'])
            assert other.get('/api/v1/admin/overview').status_code == 403
            # the codes locked (one count with the live site): the page is told to wait, never to use a recovery code
            db(store, "UPDATE edge_bff.mfa_totp SET totp_failures = %s, "
                      "totp_locked_until = extract(epoch FROM now() + interval '1 hour')::bigint WHERE user_id = %s",
               TOTP_FAILURE_CAP, uid)
            r = other.post('/api/v1/admin/step-up', headers=h2, json={'code': code_of(uid, nonce)})
            assert (r.status_code, error_of(r)['code']) == (403, 'MFA_LOCKED'), r.text
            assert error_of(r)['details']['step_up'] is True and 'use' not in error_of(r)['details']
            assert 'locked on both sites' in error_of(r)['message'] and 'recovery code' not in error_of(r)['message']


def test_the_code_step_names_a_missing_key_and_is_not_offered_with_the_switch_on(settings, store, caplog):
    with TestClient(create_app(settings, store, FakeOrc())) as c:                    # the beta without EDGE_MFA_KEY
        h = login(c)
        assert c.get('/api/v1/admin/step-up').json()['available'] is False
        caplog.set_level('WARNING', logger='edge_bff.admin')
        r = c.post('/api/v1/admin/step-up', headers=h, json={'code': '123456'})
        # the page says what to do in plain words; the log names the missing setting for the operator
        assert (r.status_code, error_of(r)['code']) == (503, 'MFA_UNAVAILABLE') and 'operator' in error_of(r)['message']
        assert 'EDGE_MFA_KEY' not in error_of(r)['message']
        assert any('admin_step_up_unavailable' in m and 'EDGE_MFA_KEY' in m for m in caplog.messages), caplog.messages
    on = dataclasses.replace(settings, multiuser=True, code_secret='c' * 40, mfa_key=KEY)
    with TestClient(create_app(on, store, FakeOrc())) as c:
        h = sign_in_admin(c, store)                                       # the sign-in itself passed the code
        assert c.get('/api/v1/admin/overview').status_code == 200
        assert c.post('/api/v1/admin/step-up', headers=h, json={'code': '123456'}).status_code == 404
        c.cookies.clear()
        make_user(store, 'alice', 'alice-password')
        sign_in(c, 'alice', 'alice-password')
        r = c.get('/api/v1/admin/overview')
        assert (r.status_code, error_of(r)['code']) == (403, 'CAPABILITY_REQUIRED')


# ---- the accounts, the audit, the plans, the settings ----------------------------------------------------------------

def test_the_accounts_are_masked_and_a_reveal_is_audited_with_its_reason(beta, store):
    with TestClient(create_app(beta, store, FakeOrc())) as c:
        h = passed(c, store, beta)
        alice = make_user(store, 'alice', 'alice-password', email='alice.wonder@example.com')
        db(store, "UPDATE edge_bff.users SET first_name = 'Alice', last_name = 'Wonder', phone_e164 = '+6281234567890' "
                  'WHERE user_id = %s', alice['user_id'])
        bob = make_user(store, 'bob', 'bob-password', status='disabled')
        listed = c.get('/api/v1/admin/users').json()
        row = next(u for u in listed['users'] if u['username'] == 'alice')
        assert (row['email'], row['phone'], row['plan'], row['status']) == ('a***@example.com', '+62••••••••890', 'free', 'active')
        assert 'alice.wonder' not in json.dumps(listed) and '6281234567890' not in json.dumps(listed)
        assert [u['username'] for u in c.get('/api/v1/admin/users', params={'q': 'wonder'}).json()['users']] == ['alice']
        # an address is found in full only (any case), never by a part, so a masked one cannot be narrowed unaudited
        assert [u['username'] for u in c.get('/api/v1/admin/users', params={'q': 'ALICE.Wonder@example.com'}).json()['users']] == ['alice']
        assert c.get('/api/v1/admin/users', params={'q': 'alice.w'}).json()['users'] == []
        assert c.get('/api/v1/admin/users', params={'q': '@example.com'}).json()['users'] == []
        assert [u['username'] for u in c.get('/api/v1/admin/users', params={'status': 'disabled'}).json()['users']] == ['bob']
        assert [u['username'] for u in c.get('/api/v1/admin/users', params={'q': '%'}).json()['users']] == []   # % is a %
        first = c.get('/api/v1/admin/users', params={'limit': 1}).json()
        assert len(first['users']) == 1 and first['next'] == first['users'][0]['user_id']
        assert c.get('/api/v1/admin/users', params={'before': first['next'], 'limit': 1}).json()['users'][0]['user_id'] < first['next']
        for params, field in (({'status': 'gone'}, 'status'), ({'limit': '0'}, 'limit'), ({'plan': 'Free plan'}, 'plan'),
                              ({'before': 'x'}, 'before'), ({'q': 'a\u202eb'}, 'q')):
            r = c.get('/api/v1/admin/users', params=params)
            assert (r.status_code, error_of(r)['details']['fields']) == (400, [field]), (params, r.text)
        detail = c.get(f"/api/v1/admin/users/{alice['user_id']}").json()
        assert detail['account']['email'] == 'a***@example.com' and detail['mfa'] == 'none'
        assert set(detail['usage']) >= {'backtest_jobs', 'screener_items', 'support_tickets'}
        assert c.get('/api/v1/admin/users/999999').status_code == 404
        # a reveal: its reason, then the value, and the audit row in the same transaction (the field, never the value)
        r = c.post(f"/api/v1/admin/users/{alice['user_id']}/reveal", headers=h, json={'field': 'email'})
        assert (r.status_code, error_of(r)['details']['fields']) == (400, ['reason'])
        r = c.post(f"/api/v1/admin/users/{alice['user_id']}/reveal", headers=h,
                   json={'field': 'phone', 'reason': 'She asked for a call back'})
        assert r.json() == {'field': 'phone', 'value': '+6281234567890'}
        trail = db(store, 'SELECT action, actor_user_id, target_user_id, after, reason FROM edge_bff.admin_audit')
        assert trail == [{'action': 'account.reveal', 'actor_user_id': seed_id(store, beta), 'target_user_id': alice['user_id'],
                          'after': {'field': 'phone'}, 'reason': 'She asked for a call back'}]
        assert c.get(f"/api/v1/admin/users/{alice['user_id']}").json()['audit'][0]['action'] == 'account.reveal'
        assert c.post(f"/api/v1/admin/users/{bob['user_id']}/reveal", headers=h,
                      json={'field': 'password', 'reason': 'x'}).status_code == 400
        # an account without the value: nothing is shown, so nothing is audited (and it is no 404)
        r = c.post(f"/api/v1/admin/users/{bob['user_id']}/reveal", headers=h, json={'field': 'phone', 'reason': 'check'})
        assert (r.status_code, r.json()) == (200, {'field': 'phone', 'value': None}), r.text
        assert len(db(store, 'SELECT 1 FROM edge_bff.admin_audit')) == 1
        r = c.post('/api/v1/admin/users/999999/reveal', headers=h, json={'field': 'phone', 'reason': 'check'})
        assert (r.status_code, error_of(r)['code']) == (404, 'NOT_FOUND')


def test_the_audit_file_never_holds_a_formula_and_follows_the_filters(beta, store, monkeypatch):
    with TestClient(create_app(beta, store, FakeOrc())) as c:
        h = passed(c, store, beta)
        alice = make_user(store, 'alice', 'alice-password')
        for reason in ('=HYPERLINK("http://example.com")', '+1 call', 'plain'):
            c.post(f"/api/v1/admin/users/{alice['user_id']}/reveal", headers=h, json={'field': 'email', 'reason': reason})
        rows = c.get('/api/v1/admin/audit', params={'action': 'account.reveal'}).json()['audit']
        assert [r['reason'] for r in rows] == ['plain', '+1 call', '=HYPERLINK("http://example.com")']
        assert c.get('/api/v1/admin/audit', params={'action': 'support.delete'}).json()['audit'] == []
        r = c.get('/api/v1/admin/audit.csv')
        assert r.headers['content-type'].startswith('text/csv') and 'attachment' in r.headers['content-disposition']
        text = r.text
        assert text.splitlines()[0].startswith('audit_id,at,action') and "'=HYPERLINK" in text and "'+1 call" in text
        assert ',=HYPERLINK' not in text
        r = c.get('/api/v1/admin/audit', params={'since': 'yesterday'})
        assert (r.status_code, error_of(r)['details']['fields']) == (400, ['since'])
        # more rows than the file holds: refused, naming the dates to narrow, never a file cut short
        monkeypatch.setattr(admin_module, 'CSV_ROWS', 2)
        r = c.get('/api/v1/admin/audit.csv')
        assert (r.status_code, error_of(r)['details']['fields']) == (400, ['since']), r.text
        assert 'More than 2 rows match' in error_of(r)['details']['reasons']['since']
        assert c.get('/api/v1/admin/audit.csv', params={'action': 'account.reveal', 'since': '2000-01-01',
                                                         'until': '2000-01-02'}).status_code == 200


def test_the_plans_are_read_only_and_the_settings_hold_no_secret(beta, store):
    with TestClient(create_app(beta, store, FakeOrc())) as c:
        passed(c, store, beta)
        plans = c.get('/api/v1/admin/plans').json()
        assert {'free', 'paid'} <= {p['plan_key'] for p in plans['plans']}
        assert any(v['plan_key'] == 'free' and v['capability_key'] == 'support.send' for v in plans['values'])
        shown = c.get('/api/v1/admin/settings').json()
        assert set(shown['settings']) == set(SHOWN_SETTINGS)
        secrets = {f.name for f in dataclasses.fields(Settings) if not f.repr}
        assert secrets and not secrets & set(SHOWN_SETTINGS), secrets & set(SHOWN_SETTINGS)
        text = json.dumps(shown)
        for value in (beta.session_secret, beta.mfa_key, beta.database_url, beta.orc_key):
            assert value not in text
        assert set(SHOWN_SETTINGS) <= {f.name for f in dataclasses.fields(Settings)}
        # read-only: no write route on the plans
        assert c.post('/api/v1/admin/plans', headers=ORIGIN, json={}).status_code in (404, 405)


# ---- the support inbox -----------------------------------------------------------------------------------------------

class Telegram:
    def __init__(self):
        self.seen = []

    def __call__(self, request):
        self.seen.append(json.loads(request.content))
        return httpx.Response(200, json={'status': 'sent'})


def test_the_support_inbox_shows_a_ticket_serves_its_images_and_audits_each_change(beta, store):
    on = dataclasses.replace(beta, telegram_notify_url='http://telegram-monitor.invalid/notify',
                             telegram_support_secret='s' * 40, admin_origin='https://admin.example.test')
    app = create_app(on, store, FakeOrc())
    telegram = Telegram()
    app.state.support.transport = httpx.MockTransport(telegram)
    with TestClient(app) as c:
        h = passed(c, store, on)
        alice = make_user(store, 'alice', 'alice-password', email='alice@example.com')
        p = type('P', (), {'user_id': alice['user_id'], 'plan_key': 'free'})()
        tickets = SupportStore(store, on)
        first = tickets.create(p, 'bug', 'The chart does not load', 'I open BBCA.', {'page': '/terminal'},
                               [('screen.png', 'image/png', PNG)])['ticket_id']
        second = tickets.create(p, 'question', 'A question', 'How?', {}, [])['ticket_id']
        listed = c.get('/api/v1/admin/support').json()['tickets']
        assert [t['ticket_id'] for t in listed] == [second, first] and listed[1]['username'] == 'alice'
        one = c.get(f'/api/v1/admin/support/{first}').json()
        assert (one['body'], one['details'], one['sender']['email'], one['files']) == (
            'I open BBCA.', {'page': '/terminal'}, 'a***@example.com',
            [{'position': 1, 'filename': 'screen.png', 'content_type': 'image/png', 'bytes': len(PNG)}])
        img = c.get(f'/api/v1/admin/support/{first}/images/1')
        assert img.content == PNG and img.headers['content-type'] == 'image/png'
        assert img.headers['content-security-policy'] == IMAGE_CSP and img.headers['x-content-type-options'] == 'nosniff'
        assert img.headers['cache-control'] == 'private, no-store' and img.headers['content-disposition'].startswith('inline')
        assert c.get(f'/api/v1/admin/support/{first}/images/2').status_code == 404
        assert c.get('/api/v1/admin/support/999999').status_code == 404
        # done: the 90 days of its images start (the user's 2B), audited by ids and status
        r = c.post(f'/api/v1/admin/support/{first}/status', headers=h, json={'status': 'done'})
        assert r.status_code == 200 and r.json()['status'] == 'done' and r.json()['done_by'] == 'owner'
        assert [t['ticket_id'] for t in c.get('/api/v1/admin/support', params={'status': 'done'}).json()['tickets']] == [first]
        c.post(f'/api/v1/admin/support/{first}/status', headers=h, json={'status': 'new'})
        assert db(store, 'SELECT done_at FROM edge_bff.support_tickets WHERE ticket_id = %s', first)[0]['done_at'] is None
        assert c.post(f'/api/v1/admin/support/{first}/status', headers=h, json={'status': 'gone'}).status_code == 400
        # the Telegram summary sent again (one not delivered); one sent already is not sent twice
        assert c.post(f'/api/v1/admin/support/{second}/telegram', headers=h).json() == {'sent': True}
        assert telegram.seen[-1]['execution_id'] == f'support-{second}'
        count = len(telegram.seen)
        assert c.post(f'/api/v1/admin/support/{second}/telegram', headers=h).json() == {'sent': True}
        assert len(telegram.seen) == count
        # deleted by hand (the user's 2B): a reason, the ticket and its images gone, the audit holds ids and kinds only
        r = c.request('DELETE', f'/api/v1/admin/support/{first}', headers=h, json={})
        assert (r.status_code, error_of(r)['details']['fields']) == (400, ['reason'])
        assert c.request('DELETE', f'/api/v1/admin/support/{first}', headers=h,
                         json={'reason': 'Answered by email'}).json() == {'deleted': True}
        assert db(store, 'SELECT count(*) AS n FROM edge_bff.support_attachments')[0]['n'] == 0
        trail = db(store, 'SELECT action, before, after, reason FROM edge_bff.admin_audit ORDER BY audit_id')
        assert [t['action'] for t in trail] == ['support.status', 'support.status', 'support.delete']
        assert trail[2]['before'] == {'ticket_id': first, 'kind': 'bug', 'status': 'new', 'images': 1, 'images_purged': False}
        assert 'chart' not in json.dumps(trail) and 'BBCA' not in json.dumps(trail)
        assert c.request('DELETE', f'/api/v1/admin/support/{first}', headers=h,
                         json={'reason': 'again'}).status_code == 404
        overview = c.get('/api/v1/admin/overview').json()
        assert overview['support']['new'] == 1 and overview['site'] == 'beta'


def test_the_telegram_summary_names_no_setting_to_the_page_and_each_missing_one_to_the_log(beta, store, caplog):
    with TestClient(create_app(dataclasses.replace(beta, telegram_notify_url='http://telegram-monitor.invalid/notify'),
                               store, FakeOrc())) as c:
        h = passed(c, store, beta)
        alice = make_user(store, 'alice', 'alice-password')
        p = type('P', (), {'user_id': alice['user_id'], 'plan_key': 'free'})()
        ticket = SupportStore(store, beta).create(p, 'question', 'A question', 'How?', {}, [])['ticket_id']
        caplog.set_level('WARNING', logger='edge_bff.admin')
        r = c.post(f'/api/v1/admin/support/{ticket}/telegram', headers=h)
        assert (r.status_code, error_of(r)['code']) == (503, 'TELEGRAM_UNAVAILABLE'), r.text
        assert 'TELEGRAM' not in error_of(r)['message'] and 'email' in error_of(r)['message']
        logged = [m for m in caplog.messages if 'support_telegram_unavailable' in m]
        assert logged and json.loads(logged[-1])['missing'] == ['TELEGRAM_SUPPORT_SECRET'], caplog.messages
        assert c.post('/api/v1/admin/support/999999/telegram', headers=h).status_code == 404
