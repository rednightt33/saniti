"""Phase 4, the checker's page-tests-records-3 (2026-11-22): every admin action writes its admin_audit row in the same
transaction as its change (CONTRACT 10; README "Admin page"). The other tests only saw the row afterwards; here the audit
insert runs and then fails inside the action, and each action must leave nothing behind: no change, no audit row, no
value returned (a reveal shows nothing)."""
import dataclasses

import pytest
from fastapi.testclient import TestClient

from app import admin as admin_module
from app.main import create_app
from app.support import SupportStore
from conftest import FakeOrc
from test_admin import KEY, PNG, db, passed
from test_principal import make_user


@pytest.fixture
def beta(settings):
    return dataclasses.replace(settings, mfa_key=KEY, code_secret='c' * 40)


class AuditFails(Exception):
    pass


def snapshot(store, uid, ticket):
    return {
        'user': db(store, 'SELECT status FROM edge_bff.users WHERE user_id = %s', uid),
        'subscriptions': db(store, 'SELECT plan_key, status, expires_at FROM edge_bff.subscriptions WHERE user_id = %s '
                                   'ORDER BY subscription_id', uid),
        'sessions': db(store, 'SELECT token_hash, revoked_at FROM edge_bff.sessions WHERE user_id = %s ORDER BY token_hash', uid),
        'outbox': db(store, 'SELECT count(*) AS n FROM edge_bff.email_outbox')[0]['n'],
        'ticket': db(store, 'SELECT status FROM edge_bff.support_tickets WHERE ticket_id = %s', ticket),
        'attachments': db(store, 'SELECT count(*) AS n FROM edge_bff.support_attachments WHERE ticket_id = %s', ticket)[0]['n'],
        'codes': db(store, 'SELECT count(*) AS n FROM edge_bff.email_codes')[0]['n'],
        'audit': db(store, 'SELECT count(*) AS n FROM edge_bff.admin_audit')[0]['n'],
    }


def test_an_audit_that_fails_rolls_its_action_back(beta, store, monkeypatch):
    real = admin_module.audit

    def failing(c, *args, **kwargs):
        real(c, *args, **kwargs)                         # the row is written, then the transaction fails
        raise AuditFails('the audit insert failed')
    with TestClient(create_app(beta, store, FakeOrc()), raise_server_exceptions=False) as c:
        h = passed(c, store, beta)
        alice = make_user(store, 'alice_atomic', 'alice-password', email='alice.atomic@example.com')
        uid = alice['user_id']
        db(store, '''INSERT INTO edge_bff.sessions(token_hash, owner_key, user_id, expires_at)
            SELECT %s, owner_key, user_id, now() + interval '1 day' FROM edge_bff.users WHERE user_id = %s''',
           'a' * 64, uid)                                    # a live session of hers to end
        pat = make_user(store, 'pat_atomic', 'pat-password', status='pending', email='pat.atomic@example.com')
        p = type('P', (), {'user_id': uid, 'plan_key': 'free'})()
        ticket = SupportStore(store, beta).create(p, 'bug', 'The chart', 'Text', {}, [('s.png', 'image/png', PNG)])['ticket_id']
        monkeypatch.setattr(admin_module, 'audit', failing)
        before = snapshot(store, uid, ticket)
        calls = [
            ('POST', f'/api/v1/admin/users/{uid}/reveal', {'field': 'email', 'reason': 'atomic'}),
            ('POST', f'/api/v1/admin/users/{uid}/status', {'status': 'disabled', 'reason': 'atomic'}),
            ('POST', f'/api/v1/admin/users/{uid}/plan', {'plan_key': 'paid', 'reason': 'atomic'}),
            ('POST', f'/api/v1/admin/users/{uid}/sessions/revoke', {'reason': 'atomic'}),
            ('POST', f'/api/v1/admin/support/{ticket}/status', {'status': 'done', 'reason': 'atomic'}),
            ('DELETE', f'/api/v1/admin/support/{ticket}', {'reason': 'atomic'}),
            ('POST', f"/api/v1/admin/users/{pat['user_id']}/resend-code", {'reason': 'atomic'}),
        ]
        for method, path, body in calls:
            r = c.request(method, path, headers=h, json=body)
            assert r.status_code >= 500, (path, r.status_code, r.text[:200])
            assert 'alice.atomic@example.com' not in r.text, path
            assert snapshot(store, uid, ticket) == before, path
