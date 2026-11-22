"""Phase 4 (the advisor's check of 2026-11-22): every test connects as the superuser, so a grant the runtime role lacks
never shows in a test and becomes a 500 once deployed. Here the app's every connection acts as edge_bff_runtime (the role
edge-bff's login holds on Railway; conftest.RoleStore), the setup as the superuser, and every admin route and the support
upload run their real write and read paths. The routes come from the app itself: a new admin route fails this test until
it is called here, so its grants are checked from its first commit."""
import dataclasses

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.main import create_app
from app.support import SupportStore
from conftest import FakeOrc, RoleStore
from test_admin import KEY, PNG, db, passed
from test_principal import make_user

RUNTIME = 'edge_bff_runtime'


def test_every_admin_route_and_the_support_upload_work_as_the_runtime_role(settings, store, database):
    beta = dataclasses.replace(settings, mfa_key=KEY, code_secret='c' * 40)
    app = create_app(beta, RoleStore(database, RUNTIME), FakeOrc())
    with TestClient(app) as c:
        h = passed(c, store, beta)
        alice = make_user(store, 'alice_role', 'alice-password', email='alice.role@example.com')
        pending = make_user(store, 'pat_role', 'pat-password', status='pending', email='pat.role@example.com')
        p = type('P', (), {'user_id': alice['user_id'], 'plan_key': 'free'})()
        ticket = SupportStore(store, beta).create(p, 'bug', 'The chart', 'Text', {}, [('s.png', 'image/png', PNG)])['ticket_id']
        u, t = alice['user_id'], ticket
        # (method, route) -> (the concrete path, the body, the status it answers); the order acts as an admin would
        calls = {
            ('GET', '/api/v1/admin/step-up'): ('/api/v1/admin/step-up', None, 200),
            ('GET', '/api/v1/admin/overview'): ('/api/v1/admin/overview', None, 200),
            ('GET', '/api/v1/admin/users'): ('/api/v1/admin/users?q=alice', None, 200),
            ('GET', '/api/v1/admin/users/{user_id}'): (f'/api/v1/admin/users/{u}', None, 200),
            ('POST', '/api/v1/admin/users/{user_id}/reveal'): (f'/api/v1/admin/users/{u}/reveal',
                                                               {'field': 'email', 'reason': 'role check'}, 200),
            ('POST', '/api/v1/admin/users/{user_id}/plan'): (f'/api/v1/admin/users/{u}/plan',
                                                             {'plan_key': 'paid', 'reason': 'role check'}, 200),
            ('POST', '/api/v1/admin/users/{user_id}/sessions/revoke'): (f'/api/v1/admin/users/{u}/sessions/revoke',
                                                                        {'reason': 'role check'}, 200),
            ('POST', '/api/v1/admin/users/{user_id}/status'): (f'/api/v1/admin/users/{u}/status',
                                                               {'status': 'disabled', 'reason': 'role check'}, 200),
            ('POST', '/api/v1/admin/users/{user_id}/resend-code'): (f"/api/v1/admin/users/{pending['user_id']}/resend-code",
                                                                    {'reason': 'role check'}, 200),
            ('GET', '/api/v1/admin/audit'): ('/api/v1/admin/audit', None, 200),
            ('GET', '/api/v1/admin/audit.csv'): ('/api/v1/admin/audit.csv', None, 200),
            ('GET', '/api/v1/admin/plans'): ('/api/v1/admin/plans', None, 200),
            ('GET', '/api/v1/admin/settings'): ('/api/v1/admin/settings', None, 200),
            ('GET', '/api/v1/admin/support'): ('/api/v1/admin/support?status=all', None, 200),
            ('GET', '/api/v1/admin/support/{ticket_id}'): (f'/api/v1/admin/support/{t}', None, 200),
            ('GET', '/api/v1/admin/support/{ticket_id}/images/{position}'): (f'/api/v1/admin/support/{t}/images/1', None, 200),
            ('POST', '/api/v1/admin/support/{ticket_id}/status'): (f'/api/v1/admin/support/{t}/status',
                                                                   {'status': 'done', 'reason': 'role check'}, 200),
            # no Telegram on this site: the route reads the ticket, then says so (503)
            ('POST', '/api/v1/admin/support/{ticket_id}/telegram'): (f'/api/v1/admin/support/{t}/telegram', None, 503),
            ('DELETE', '/api/v1/admin/support/{ticket_id}'): (f'/api/v1/admin/support/{t}', {'reason': 'role check'}, 200),
        }
        routes = {(m, r.path) for r in app.routes if isinstance(r, APIRoute) and r.path.startswith('/api/v1/admin')
                  for m in r.methods - {'HEAD'}} - {('POST', '/api/v1/admin/step-up')}      # (passed() posts it)
        assert routes == set(calls), ('call every admin route here, with what would act: '
                                      f'{sorted(routes - set(calls))} missing, {sorted(set(calls) - routes)} gone')
        for (method, _route), (path, body, status) in calls.items():
            r = c.request(method, path, headers=h if method != 'GET' else None, json=body)
            assert r.status_code == status, (method, path, r.status_code, r.text[:300])
        assert {a['action'] for a in db(store, 'SELECT action FROM edge_bff.admin_audit')} == {
            'account.reveal', 'account.plan', 'account.sessions_revoke', 'account.status', 'account.resend_code',
            'support.status', 'support.delete'}
        # the support upload as the runtime role (the beta's owner holds support.send through '*'), with an image
        import base64
        r = c.post('/api/v1/support', headers=h, json={'kind': 'question', 'subject': 'Role check', 'body': 'As runtime',
                                                        'details': {}, 'images': [{'name': 's.png', 'type': 'image/png',
                                                                                   'data': base64.b64encode(PNG).decode()}]})
        assert r.status_code == 201, r.text
