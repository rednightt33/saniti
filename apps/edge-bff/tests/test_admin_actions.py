"""Phase 4 slice 5, the admin's actions on an account (app/admin.py; CONTRACT.md 10; the user, 2026-11-22: "A, lanjut
slice 5"): disable or enable, a plan given or extended, every session ended, a registration code sent again.

- Each writes its change and exactly one audit row (the field it changed, the reason), or nothing at all when refused.
- None acts on the admin's own account; the account's answer says which are open and why the others are closed, and the
  routes refuse alike.
- An account's admin right never changes here, and an active admin always remains; each check runs after the write, in
  its transaction, so a refusal leaves nothing behind.
- A disabled account's session answers 401 at once on the live site; the database's own rules (the restricted-plan rule,
  23514) come back as the field's reason in their words.
- A code sent again from the beta is one the live site takes, with the registration's own browser."""
import dataclasses
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import admin as admin_module
from app.main import create_app
from conftest import FakeOrc
from test_admin import KEY, code_of, db, enrol, error_of, login, passed, seed_id
from test_auth_flows import last_code, register, verify
from test_beta_live_site import live_of
from test_edge import ORIGIN
from test_principal import make_user, sign_in

CODE = 'c' * 40


def open_live(beta):
    """The live site after the launch (no pre-launch mode): any active account signs in."""
    return dataclasses.replace(live_of(beta), prelaunch_enabled=False)


@pytest.fixture
def beta(settings):
    """The beta as it runs: the switch off, the live site's EDGE_MFA_KEY and EDGE_CODE_SECRET."""
    return dataclasses.replace(settings, mfa_key=KEY, code_secret=CODE)


def audit_rows(store, action=None):
    return db(store, 'SELECT action, target_user_id, before, after, reason FROM edge_bff.admin_audit'
              + (' WHERE action = %s' if action else '') + ' ORDER BY audit_id', *([action] if action else []))


def plan_rows(store, user_id):
    return [(r['plan_key'], r['status']) for r in db(store, '''SELECT plan_key, status FROM edge_bff.subscriptions
        WHERE user_id = %s ORDER BY subscription_id''', user_id)]


def admin_by_override(store, user):
    db(store, '''INSERT INTO edge_bff.user_capability_overrides(user_id, capability_key, value, reason)
        VALUES (%s, 'admin.access', 'true'::jsonb, 'a second admin')''', user['user_id'])


def later(days=30):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def test_disable_signs_out_everywhere_and_enable_returns_each_with_one_audit_row(beta, store):
    with TestClient(create_app(beta, store, FakeOrc())) as c:
        h = passed(c, store, beta)
        alice = make_user(store, 'alice_act', 'alice-password')
        # alice signed in on the live site: its session ends the moment it is disabled
        with TestClient(create_app(open_live(beta), store, FakeOrc())) as live:
            sign_in(live, 'alice_act', 'alice-password')
            assert live.get('/api/v1/auth/session').status_code == 200
            r = c.post(f"/api/v1/admin/users/{alice['user_id']}/status", headers=h, json={'status': 'disabled'})
            assert (r.status_code, error_of(r)['details']['fields']) == (400, ['reason'])    # a reason first
            r = c.post(f"/api/v1/admin/users/{alice['user_id']}/status", headers=h,
                       json={'status': 'disabled', 'reason': 'Asked to close it for a month'})
            assert r.json() == {'status': 'disabled', 'changed': True, 'sessions_revoked': 1}, r.text
            assert live.get('/api/v1/auth/session').status_code == 401
            r = live.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'alice_act', 'password': 'alice-password'})
            assert r.status_code == 401
        trail = audit_rows(store, 'account.status')
        assert trail == [{'action': 'account.status', 'target_user_id': alice['user_id'], 'before': {'status': 'active'},
                          'after': {'status': 'disabled', 'sessions_revoked': 1}, 'reason': 'Asked to close it for a month'}]
        # the same status again changes nothing and writes nothing
        r = c.post(f"/api/v1/admin/users/{alice['user_id']}/status", headers=h, json={'status': 'disabled', 'reason': 'x'})
        assert r.json()['changed'] is False and len(audit_rows(store, 'account.status')) == 1
        r = c.post(f"/api/v1/admin/users/{alice['user_id']}/status", headers=h, json={'status': 'active', 'reason': 'Back'})
        assert r.json()['changed'] is True
        assert db(store, 'SELECT status FROM edge_bff.users WHERE user_id = %s', alice['user_id'])[0]['status'] == 'active'
        assert [t['after']['status'] for t in audit_rows(store, 'account.status')] == ['disabled', 'active']
        for body, field in (({'status': 'gone', 'reason': 'x'}, 'status'), ({'status': 'pending', 'reason': 'x'}, 'status')):
            r = c.post(f"/api/v1/admin/users/{alice['user_id']}/status", headers=h, json=body)
            assert (r.status_code, error_of(r)['details']['fields']) == (400, [field])
        assert c.post('/api/v1/admin/users/999999/status', headers=h, json={'status': 'disabled', 'reason': 'x'}).status_code == 404


def test_no_action_touches_the_admins_own_account_and_the_answer_says_which_are_open(beta, store):
    with TestClient(create_app(beta, store, FakeOrc())) as c:
        h = passed(c, store, beta)
        own = seed_id(store, beta)
        pending = make_user(store, 'pat_pending', 'pat-password', status='pending')
        alice = make_user(store, 'alice_open', 'alice-password')
        second = make_user(store, 'second_admin', 'second-password')
        admin_by_override(store, second)
        answers = {u: c.get(f'/api/v1/admin/users/{u}').json() for u in (own, pending['user_id'], alice['user_id'],
                                                                           second['user_id'])}
        assert all(not a['open'] and 'your own account' in a['why'] for a in answers[own]['actions'].values())
        assert {k: a['open'] for k, a in answers[pending['user_id']]['actions'].items()} == {
            'status': False, 'plan': False, 'sessions': False, 'resend_code': True}
        assert {k: a['open'] for k, a in answers[alice['user_id']]['actions'].items()} == {
            'status': True, 'plan': True, 'sessions': True, 'resend_code': False}
        assert answers[second['user_id']]['holds_admin'] is True and answers[alice['user_id']]['holds_admin'] is False
        assert not answers[second['user_id']]['actions']['plan']['open']
        # every route refuses what the answer closes (in the answer's words, writing nothing) and does what it opens
        calls = {'status': ('status', {'status': 'disabled'}, 'account.status'),
                 'plan': ('plan', {'plan_key': 'paid'}, 'account.plan'),
                 'sessions': ('sessions/revoke', {}, 'account.sessions_revoke'),
                 'resend_code': ('resend-code', {}, 'account.resend_code')}
        opened = []
        for user, answer in answers.items():
            for name, state in answer['actions'].items():
                path, body, action = calls[name]
                r = c.post(f'/api/v1/admin/users/{user}/{path}', headers=h, json={**body, 'reason': 'try'})
                if state['open']:
                    assert r.status_code == 200, (user, name, r.text)
                    opened.append((user, action))
                else:
                    assert r.status_code == 400 and state['why'] in error_of(r)['details']['reasons'].values(), (user, name, r.text)
        assert sorted((a['target_user_id'], a['action']) for a in audit_rows(store)) == sorted(opened)


def test_a_plan_is_given_or_extended_and_never_changes_an_admin_right(beta, store):
    with TestClient(create_app(beta, store, FakeOrc())) as c:
        h = passed(c, store, beta)
        alice = make_user(store, 'alice_plan', 'alice-password')
        uid = alice['user_id']
        end = later(30)
        r = c.post(f'/api/v1/admin/users/{uid}/plan', headers=h, json={'plan_key': 'paid', 'expires_at': end,
                                                                        'reason': 'Paid by bank transfer'})
        assert r.status_code == 200 and r.json()['plan'] == 'paid', r.text
        assert plan_rows(store, uid) == [('paid', 'active')]
        # extended: the same plan to a later end; the one it had ends (cancelled), the history keeps both
        r = c.post(f'/api/v1/admin/users/{uid}/plan', headers=h, json={'plan_key': 'paid', 'expires_at': later(60),
                                                                        'reason': 'One more month'})
        assert r.status_code == 200 and plan_rows(store, uid) == [('paid', 'cancelled'), ('paid', 'active')]
        detail = c.get(f'/api/v1/admin/users/{uid}').json()
        assert detail['account']['plan'] == 'paid' and detail['account']['plan_ends'] is not None
        trail = audit_rows(store, 'account.plan')
        assert [(t['before']['plan'], t['after']['plan']) for t in trail] == [('free', 'paid'), ('paid', 'paid')]
        assert trail[0]['before']['expires_at'] is None and trail[0]['after']['expires_at'].startswith(end[:10])
        # refused, nothing written: an end in the past or without its zone, an unknown plan, the visitors' plan, the
        # admin's plan (it would give the admin right)
        before = (plan_rows(store, uid), len(audit_rows(store)))
        for body, field in (({'plan_key': 'paid', 'expires_at': '2000-01-01T00:00:00+00:00'}, 'expires_at'),
                            ({'plan_key': 'paid', 'expires_at': '2099-01-01'}, 'expires_at'),
                            ({'plan_key': 'gold'}, 'plan_key'), ({'plan_key': 'guest'}, 'plan_key'),
                            ({'plan_key': 'Paid Plan'}, 'plan_key')):
            r = c.post(f'/api/v1/admin/users/{uid}/plan', headers=h, json={**body, 'reason': 'try'})
            assert (r.status_code, error_of(r)['details']['fields']) == (400, [field]), (body, r.text)
        r = c.post(f'/api/v1/admin/users/{uid}/plan', headers=h, json={'plan_key': 'admin', 'reason': 'try'})
        assert (r.status_code, error_of(r)['details']['fields']) == (400, ['account']), r.text
        assert 'give the admin right' in error_of(r)['details']['reasons']['account']
        assert (plan_rows(store, uid), len(audit_rows(store))) == before
        # another admin's plan is the operator's
        second = make_user(store, 'second_plan', 'second-password')
        admin_by_override(store, second)
        r = c.post(f"/api/v1/admin/users/{second['user_id']}/plan", headers=h, json={'plan_key': 'paid', 'reason': 'x'})
        assert (r.status_code, error_of(r)['details']['fields']) == (400, ['plan_key'])
        assert plan_rows(store, second['user_id']) == []
        # the plans answer marks the plan that gives the admin right (the page leaves it out of its choice)
        assert {p['plan_key']: p['gives_admin'] for p in c.get('/api/v1/admin/plans').json()['plans']} == {
            'admin': True, 'free': False, 'guest': False, 'paid': False}


def test_the_restricted_plan_rule_comes_back_as_the_plans_reason_in_its_own_words(beta, store):
    """23514 (terminal_limit_with_every_stock): an account whose override narrows the Terminal's tickers cannot be given
    a plan that opens the Backtest; the refusal is the plan field's reason, with the rule's hint, and nothing is written."""
    with TestClient(create_app(beta, store, FakeOrc())) as c:
        h = passed(c, store, beta)
        alice = make_user(store, 'alice_rule', 'alice-password')
        db(store, '''INSERT INTO edge_bff.user_capability_overrides(user_id, capability_key, value, reason)
            VALUES (%s, 'terminal.tickers', '["BBCA"]'::jsonb, 'a narrowed Terminal')''', alice['user_id'])
        r = c.post(f"/api/v1/admin/users/{alice['user_id']}/plan", headers=h, json={'plan_key': 'paid', 'reason': 'x'})
        assert (r.status_code, error_of(r)['details']['fields']) == (400, ['plan_key']), r.text
        words = error_of(r)['details']['reasons']['plan_key']
        assert 'would both limit the Terminal and open the Backtest or the Screener' in words and 'Right:' in words
        assert not words.startswith('edge_bff.')
        assert plan_rows(store, alice['user_id']) == [] and audit_rows(store, 'account.plan') == []


def test_the_last_admin_is_never_disabled(beta, store):
    """The beta's owner holds '*' by its settings; its account's own plan may not (the seed subscription ended). Then
    disabling the one other admin would leave no active account with the admin right: refused, nothing written."""
    with TestClient(create_app(beta, store, FakeOrc())) as c:
        h = passed(c, store, beta)
        db(store, "UPDATE edge_bff.subscriptions SET status = 'cancelled' WHERE user_id = %s", seed_id(store, beta))
        second = make_user(store, 'second_last', 'second-password')
        admin_by_override(store, second)
        r = c.post(f"/api/v1/admin/users/{second['user_id']}/status", headers=h, json={'status': 'disabled', 'reason': 'x'})
        assert (r.status_code, error_of(r)['details']['fields']) == (400, ['status']), r.text
        assert 'at least one active account' in error_of(r)['details']['reasons']['status']
        assert db(store, 'SELECT status FROM edge_bff.users WHERE user_id = %s', second['user_id'])[0]['status'] == 'active'
        assert audit_rows(store) == []


def test_every_session_ends_with_its_count(beta, store):
    with TestClient(create_app(beta, store, FakeOrc())) as c:
        h = passed(c, store, beta)
        alice = make_user(store, 'alice_out', 'alice-password')
        with TestClient(create_app(open_live(beta), store, FakeOrc())) as one, \
                TestClient(create_app(open_live(beta), store, FakeOrc())) as two:
            sign_in(one, 'alice_out', 'alice-password')
            sign_in(two, 'alice_out', 'alice-password')
            r = c.post(f"/api/v1/admin/users/{alice['user_id']}/sessions/revoke", headers=h,
                       json={'reason': 'Lost her phone'})
            assert r.json() == {'revoked': 2}, r.text
            assert one.get('/api/v1/auth/session').status_code == 401 and two.get('/api/v1/auth/session').status_code == 401
        assert audit_rows(store, 'account.sessions_revoke')[0]['after'] == {'revoked': 2}


def test_a_code_sent_again_from_the_beta_finishes_the_registration_on_the_live_site(beta, store):
    with TestClient(create_app(open_live(beta), store, FakeOrc())) as person:
        person.app.state.auth_flows.pwned_fetch = lambda prefix: ''
        assert register(person, email='rina@example.com', username='rina_new').status_code == 202
        first = last_code(store, 'rina@example.com')
        pending = db(store, "SELECT user_id FROM edge_bff.users WHERE email = 'rina@example.com'")[0]['user_id']
        with TestClient(create_app(beta, store, FakeOrc())) as c:
            h = passed(c, store, beta)
            r = c.post(f'/api/v1/admin/users/{pending}/resend-code', headers=h, json={'reason': 'She lost the email'})
            assert r.json() == {'sent': True}, r.text
            again = last_code(store, 'rina@example.com')
            assert again != first
            assert verify(person, first, email='rina@example.com').status_code == 400        # the old code ended
            r = verify(person, again, email='rina@example.com')
            assert r.status_code == 200, r.text
            assert db(store, 'SELECT status FROM edge_bff.users WHERE user_id = %s', pending)[0]['status'] == 'active'
            assert audit_rows(store, 'account.resend_code')[0]['after'] == {'purpose': 'register'}


def pending_on_live(beta, store, email, username):
    with TestClient(create_app(open_live(beta), store, FakeOrc())) as person:
        person.app.state.auth_flows.pwned_fetch = lambda prefix: ''
        assert register(person, email=email, username=username).status_code == 202
    return db(store, 'SELECT user_id FROM edge_bff.users WHERE email = %s', email)[0]['user_id']


def test_a_resent_code_keeps_the_registrations_mail_cap(beta, store):
    pending = pending_on_live(beta, store, 'tia@example.com', 'tia_new')
    with TestClient(create_app(beta, store, FakeOrc())) as c:
        h = passed(c, store, beta)
        sent = [c.post(f'/api/v1/admin/users/{pending}/resend-code', headers=h, json={'reason': 'x'}) for _ in range(3)]
        assert [s.status_code for s in sent] == [200, 200, 429]                      # the registration's 3 mails a day
        assert '3 times today' in error_of(sent[2])['message'] and 'Send the code again in ' in error_of(sent[2])['message']
        wait = error_of(sent[2])['details']['retry_after_s']
        assert 0 < wait <= 2 * 86400 and sent[2].headers['retry-after'] == str(wait)        # the throttle's own window
    assert len(audit_rows(store, 'account.resend_code')) == 2


def test_a_resent_code_needs_the_live_sites_code_key(beta, store, caplog):
    pending = pending_on_live(beta, store, 'uli@example.com', 'uli_new')
    with TestClient(create_app(dataclasses.replace(beta, code_secret=''), store, FakeOrc())) as c:
        h = passed(c, store, beta)
        caplog.set_level('WARNING', logger='edge_bff.admin')
        r = c.post(f'/api/v1/admin/users/{pending}/resend-code', headers=h, json={'reason': 'x'})
        assert (r.status_code, error_of(r)['code']) == (503, 'CODE_UNAVAILABLE')
        assert 'EDGE_CODE_SECRET' not in error_of(r)['message'] and 'operator' in error_of(r)['message']
        assert any('admin_resend_unavailable' in m and 'EDGE_CODE_SECRET' in m for m in caplog.messages)
    assert audit_rows(store) == []


# ---- the Phase 4 checker's actions-1 to actions-5 and page-tests-records-6 (2026-11-22) ------------------------------

@pytest.mark.parametrize('route,body', [('status', {'status': 'disabled'}), ('plan', {'plan_key': 'paid'}),
                                        ('sessions/revoke', {}), ('resend-code', {})])
@pytest.mark.parametrize('reason', [None, '', '   '])
def test_every_action_needs_a_reason(beta, store, route, body, reason):
    """actions-5: each action route refuses without a reason (missing, empty or blank) and leaves nothing behind."""
    with TestClient(create_app(beta, store, FakeOrc())) as c:
        h = passed(c, store, beta)
        target = make_user(store, 'rhea_reason', 'rhea-password', status='pending' if route == 'resend-code' else 'active')
        before = (plan_rows(store, target['user_id']), db(store, 'SELECT status FROM edge_bff.users WHERE user_id = %s',
                                                           target['user_id']))
        r = c.post(f"/api/v1/admin/users/{target['user_id']}/{route}", headers=h,
                   json={**body, **({} if reason is None else {'reason': reason})})
        assert r.status_code == 400 and 'reason' in error_of(r)['details']['fields'], r.text
        assert (plan_rows(store, target['user_id']), db(store, 'SELECT status FROM edge_bff.users WHERE user_id = %s',
                                                         target['user_id'])) == before
    assert audit_rows(store) == [] and db(store, 'SELECT count(*) AS n FROM edge_bff.email_codes')[0]['n'] == 0


def test_an_admin_right_that_ends_later_still_counts_for_the_plan_and_for_the_last_admin(beta, store):
    """actions-1: an admin right with an end is judged at every moment it may apply. Bob holds admin.access until a
    date: his plan stays the operator's. The owner's own right ends in two days while Dana's lasts: Dana is the last
    lasting admin, so she is not disabled, and the account answer says so."""
    with TestClient(create_app(beta, store, FakeOrc())) as c:
        h = passed(c, store, beta)
        own = seed_id(store, beta)
        bob = make_user(store, 'bob_ends', 'bob-password')
        db(store, '''INSERT INTO edge_bff.user_capability_overrides(user_id, capability_key, value, reason, expires_at)
            VALUES (%s, 'admin.access', 'true'::jsonb, 'until a date', now() + interval '2 days')''', bob['user_id'])
        detail = c.get(f"/api/v1/admin/users/{bob['user_id']}").json()
        assert detail['actions']['plan'] == {'open': False, 'why': admin_module.ADMINS_OWN}
        r = c.post(f"/api/v1/admin/users/{bob['user_id']}/plan", headers=h, json={'plan_key': 'paid', 'reason': 'x'})
        assert r.status_code == 400 and error_of(r)['details']['reasons']['plan_key'] == admin_module.ADMINS_OWN
        # Carol's right comes back later (an admin plan from tomorrow): she counts as an admin already
        carol = make_user(store, 'carol_later', 'carol-password')
        db(store, '''INSERT INTO edge_bff.subscriptions(user_id, plan_key, status, starts_at, provider)
            SELECT %s, plan_key, 'active', now() + interval '1 day', 'test' FROM edge_bff.plan_capabilities
            WHERE capability_key = '*' AND value = 'true'::jsonb''', carol['user_id'])
        assert not c.get(f"/api/v1/admin/users/{carol['user_id']}").json()['actions']['plan']['open']
        r = c.post(f"/api/v1/admin/users/{carol['user_id']}/plan", headers=h, json={'plan_key': 'paid', 'reason': 'x'})
        assert r.status_code == 400 and error_of(r)['details']['reasons']['plan_key'] == admin_module.ADMINS_OWN
        dana = make_user(store, 'dana_lasts', 'dana-password')
        admin_by_override(store, dana)                                       # no end
        db(store, "UPDATE edge_bff.subscriptions SET expires_at = now() + interval '2 days' WHERE user_id = %s", own)
        detail = c.get(f"/api/v1/admin/users/{dana['user_id']}").json()
        assert detail['actions']['status'] == {'open': False, 'why': admin_module.LAST_ADMIN}
        r = c.post(f"/api/v1/admin/users/{dana['user_id']}/status", headers=h, json={'status': 'disabled', 'reason': 'x'})
        assert r.status_code == 400 and error_of(r)['details']['reasons']['status'] == admin_module.LAST_ADMIN
        assert db(store, 'SELECT status FROM edge_bff.users WHERE user_id = %s', dana['user_id'])[0]['status'] == 'active'
        # Bob, whose right ends, may be disabled: Dana keeps it for good
        r = c.post(f"/api/v1/admin/users/{bob['user_id']}/status", headers=h, json={'status': 'disabled', 'reason': 'x'})
        assert r.status_code == 200, r.text


def test_with_no_admin_in_the_database_an_ordinary_account_is_still_disabled_and_enabled(beta, store):
    """actions-2: the last-admin rule refuses only an action that takes the last holder away; when the database holds
    none (the owner's seed plan ended; the beta's owner keeps the page by its settings) other accounts' actions go on,
    and the account answer shows them open."""
    with TestClient(create_app(beta, store, FakeOrc())) as c:
        h = passed(c, store, beta)
        own = seed_id(store, beta)
        db(store, '''UPDATE edge_bff.subscriptions SET starts_at = now() - interval '2 days',
            expires_at = now() - interval '1 second' WHERE user_id = %s''', own)
        alice = make_user(store, 'alice_none', 'alice-password')
        detail = c.get(f"/api/v1/admin/users/{alice['user_id']}").json()
        assert detail['actions']['status']['open'] and detail['actions']['plan']['open']
        for status in ('disabled', 'active'):
            r = c.post(f"/api/v1/admin/users/{alice['user_id']}/status", headers=h, json={'status': status, 'reason': 'x'})
            assert r.status_code == 200, r.text
        r = c.post(f"/api/v1/admin/users/{alice['user_id']}/plan", headers=h, json={'plan_key': 'paid', 'reason': 'x'})
        assert r.status_code == 200, r.text


def test_a_registration_is_listed_and_found_by_the_name_it_asked_for(beta, store):
    """actions-3: an account still registering has no username yet; the list and the detail carry the name it asked
    for, and a search finds it by that name."""
    from app.accounts import new_owner_key
    with TestClient(create_app(beta, store, FakeOrc())) as c:
        passed(c, store, beta)
        uid = db(store, '''INSERT INTO edge_bff.users(owner_key, username, requested_username, email, role, status)
            VALUES (%s, NULL, 'pat_asked', 'pat.asked@example.com', 'user', 'pending') RETURNING user_id''',
                 new_owner_key())[0]['user_id']
        found = c.get('/api/v1/admin/users?q=pat_ask').json()['users']
        assert [(u['user_id'], u['username'], u['requested_username']) for u in found] == [(uid, None, 'pat_asked')]
        assert c.get(f'/api/v1/admin/users/{uid}').json()['account']['requested_username'] == 'pat_asked'


def test_resend_code_is_closed_where_no_code_can_be_sent(beta, store):
    """actions-4: without EDGE_CODE_SECRET every Resend code answers 503; the account answer says so beforehand."""
    from app.errors import MESSAGES
    keyless = dataclasses.replace(beta, code_secret='')
    with TestClient(create_app(keyless, store, FakeOrc())) as c:
        h = passed(c, store, keyless)
        pat = make_user(store, 'pat_keyless', 'pat-password', status='pending')
        detail = c.get(f"/api/v1/admin/users/{pat['user_id']}").json()
        assert detail['actions']['resend_code'] == {'open': False, 'why': MESSAGES['CODE_UNAVAILABLE']}
        r = c.post(f"/api/v1/admin/users/{pat['user_id']}/resend-code", headers=h, json={'reason': 'x'})
        assert r.status_code == 503 and error_of(r)['code'] == 'CODE_UNAVAILABLE'
    db(store, 'DELETE FROM edge_bff.mfa_recovery_codes'); db(store, 'DELETE FROM edge_bff.mfa_totp')   # enrolled again below
    with TestClient(create_app(beta, store, FakeOrc())) as c:
        passed(c, store, beta)
        assert c.get(f"/api/v1/admin/users/{pat['user_id']}").json()['actions']['resend_code'] == {'open': True, 'why': None}


def test_the_account_list_carries_each_accounts_usage(beta, store):
    """page-tests-records-6 (CONTRACT 10's list): the usage counters of each listed account, as its detail counts them."""
    from app.support import SupportStore
    from test_admin import PNG
    with TestClient(create_app(beta, store, FakeOrc())) as c:
        passed(c, store, beta)
        alice = make_user(store, 'alice_usage', 'alice-password')
        p = type('P', (), {'user_id': alice['user_id'], 'plan_key': 'free'})()
        SupportStore(store, beta).create(p, 'bug', 'S', 'B', {}, [('s.png', 'image/png', PNG)])
        listed = {u['user_id']: u for u in c.get('/api/v1/admin/users').json()['users']}
        detail = c.get(f"/api/v1/admin/users/{alice['user_id']}").json()
        assert listed[alice['user_id']]['usage'] == detail['usage'] and detail['usage']['support_tickets'] == 1
