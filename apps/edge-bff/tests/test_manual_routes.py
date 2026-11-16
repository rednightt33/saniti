"""EXEC-MANUAL (user 2026-10-17, troubleshooting only): the BFF passes Claude's step reads and replies to Orc for a
signed-in session, and passes Orc's own answer through (404 while Orc's switch is off).

EXEC-MU-ACCOUNTS Phase 0 (M259, M474): both routes are an admin owner's only (settings.admin_owners, EDGE_ADMIN_OWNERS,
default the one owner), else 403 CAPABILITY_REQUIRED admin.manual; the reply is a write (CSRF, 403 CSRF_INVALID)."""
import dataclasses

from fastapi.testclient import TestClient

from app.main import create_app
from conftest import FakeOrc
from test_edge import ORIGIN, login


class ManualOrc(FakeOrc):
    def __init__(self, on=True):
        super().__init__(); self.on = on; self.manual_calls = []

    def manual(self, owner, method, path, body=None):
        self.manual_calls.append((method, path, body))
        if not self.on:
            return 404, {'detail': 'Not Found'}
        if method == 'GET':
            return 200, {'steps': [{'step_id': 's1', 'request_id': 'edge_x', 'payload': {'model': 'saniti/claude-manual'}}]}
        return (200, {'status': 'ANSWERED'}) if path == '/s1' else (409, {'status': 'NOT_WAITING'})


def admin(settings):
    return dataclasses.replace(settings, admin_owners=(settings.owner,))


def test_manual_steps_need_a_session_and_are_passed_to_orc(settings, store):
    orc = ManualOrc()
    with TestClient(create_app(admin(settings), store, orc)) as c:
        assert c.get('/api/v1/dev/manual/steps').status_code == 401
        h = login(c)
        steps = c.get('/api/v1/dev/manual/steps')
        assert steps.status_code == 200 and steps.json()['steps'][0]['step_id'] == 's1'
        reply = {'response': {'output': [{'type': 'function_call', 'name': 'get_system_capabilities',
                                          'arguments': '{}', 'call_id': 'c1'}]}}
        assert c.post('/api/v1/dev/manual/steps/s1', headers=h, json=reply).json() == {'status': 'ANSWERED'}
        assert c.post('/api/v1/dev/manual/steps/s9', headers=h, json=reply).status_code == 409
        # M259: the reply needs the CSRF token; sent with EDGE's Origin, so the refusal is the CSRF check's own
        refused = c.post('/api/v1/dev/manual/steps/s1', headers=ORIGIN, json=reply)
        assert refused.status_code == 403 and refused.json()['error']['code'] == 'CSRF_INVALID'
        assert c.post('/api/v1/dev/manual/steps/s1', json=reply).status_code == 403  # no Origin either
        assert orc.manual_calls[1] == ('POST', '/s1', reply) and len(orc.manual_calls) == 3


def test_manual_routes_refuse_an_owner_who_is_not_an_admin(settings, store):
    """M474 (edge-bff side): an owner outside EDGE_ADMIN_OWNERS reaches neither route, and Orc is never asked."""
    orc = ManualOrc()
    with TestClient(create_app(dataclasses.replace(settings, admin_owners=('someone-else',)), store, orc)) as c:
        h = login(c)
        for r in (c.get('/api/v1/dev/manual/steps'), c.post('/api/v1/dev/manual/steps/s1', headers=h, json={})):
            assert r.status_code == 403, r.text
            error = r.json()['error']
            assert error['code'] == 'CAPABILITY_REQUIRED' and error['details']['capability'] == 'admin.manual'
            assert error['message'] and error['details']['display_name']
        assert orc.manual_calls == []


def test_with_orcs_switch_off_the_routes_answer_404(settings, store):
    with TestClient(create_app(admin(settings), store, ManualOrc(on=False))) as c:
        login(c)
        assert c.get('/api/v1/dev/manual/steps').status_code == 404
