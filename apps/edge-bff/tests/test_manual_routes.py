"""EXEC-MANUAL (user 2026-10-17, troubleshooting only): the BFF passes Claude's step reads and replies to Orc for a
signed-in session, and passes Orc's own answer through (404 while Orc's switch is off)."""
from fastapi.testclient import TestClient

from app.main import create_app
from conftest import FakeOrc
from test_edge import login


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


def test_manual_steps_need_a_session_and_are_passed_to_orc(settings, store):
    orc = ManualOrc()
    with TestClient(create_app(settings, store, orc)) as c:
        assert c.get('/api/v1/dev/manual/steps').status_code == 401
        h = login(c)
        steps = c.get('/api/v1/dev/manual/steps')
        assert steps.status_code == 200 and steps.json()['steps'][0]['step_id'] == 's1'
        reply = {'response': {'output': [{'type': 'function_call', 'name': 'get_system_capabilities',
                                          'arguments': '{}', 'call_id': 'c1'}]}}
        assert c.post('/api/v1/dev/manual/steps/s1', headers=h, json=reply).json() == {'status': 'ANSWERED'}
        assert c.post('/api/v1/dev/manual/steps/s9', headers=h, json=reply).status_code == 409
        assert c.post('/api/v1/dev/manual/steps/s1', json=reply).status_code == 403  # no CSRF token
        assert orc.manual_calls[1] == ('POST', '/s1', reply)


def test_with_orcs_switch_off_the_routes_answer_404(settings, store):
    with TestClient(create_app(settings, store, ManualOrc(on=False))) as c:
        login(c)
        assert c.get('/api/v1/dev/manual/steps').status_code == 404
