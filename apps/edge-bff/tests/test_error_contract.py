"""EXEC-MU-ACCOUNTS Phase 0 (CONTRACT.md sections 3 and 6; ERRORS M471): FastAPI's own refusals answer
{"error": {"code", "message", "details"}} with the status unchanged, and the Origin check skips exactly /api/v1/hooks/.

Rule (a): the front-end decides by error.code. How to pass (b): UNAUTHENTICATED -> sign in; CSRF_INVALID -> read the
session again and retry once. Right (c): a write with the session's X-CSRF-Token passes. Wrong (c): the same write
without it answers 403 CSRF_INVALID. Messages (d): app/errors.py MESSAGES, plain Indonesian.
"""
from fastapi.testclient import TestClient

from app.errors import MESSAGES
from app.main import create_app
from conftest import FakeOrc
from test_edge import ORIGIN, login

INTERNAL = ('csrf', 'token', 'edge_', 'fastapi', 'detail', 'owner', 'http')


def shape(r, status, code):
    assert r.status_code == status, r.text
    body = r.json()
    assert set(body) == {'error'} and set(body['error']) == {'code', 'message', 'details'}, body
    assert body['error']['code'] == code and body['error']['message'] == MESSAGES[code]
    return body['error']


def test_every_message_is_plain_and_names_no_internal_word():
    for code, message in MESSAGES.items():
        assert message.endswith('.') and not any(word in message.lower() for word in INTERNAL), code


def test_fastapi_refusals_use_the_contract_shape(settings, store):
    with TestClient(create_app(settings, store, FakeOrc())) as c:
        assert shape(c.get('/api/v1/conversations'), 401, 'UNAUTHENTICATED')['details'] == {}
        shape(c.get('/api/v1/auth/session'), 401, 'UNAUTHENTICATED')
        h = login(c)
        shape(c.post('/api/v1/runs', headers=ORIGIN, json={'message': 'Hello', 'submission_key': 'x'}), 403, 'CSRF_INVALID')
        shape(c.post('/api/v1/runs', headers={**ORIGIN, 'X-CSRF-Token': 'f' * 64},
                     json={'message': 'Hello', 'submission_key': 'x'}), 403, 'CSRF_INVALID')
        bad = shape(c.post('/api/v1/runs', headers=h, json={'message': 'Hello', 'submission_key': 'x', 'owner': 'x'}),
                    422, 'INVALID_INPUT')
        assert bad['details'] == {'fields': ['owner']}
        bad = shape(c.get('/api/v1/conversations?limit=0'), 422, 'INVALID_INPUT')
        assert bad['details'] == {'fields': ['limit']}
        shape(c.get('/api/v1/no-such-route'), 404, 'NOT_FOUND')
        refused = shape(c.put('/api/v1/runs', headers=h, json={}), 405, 'METHOD_NOT_ALLOWED')
        assert refused['details'] == {}
        assert 'POST' in c.put('/api/v1/runs', headers=h, json={}).headers['allow']
        run = c.post('/api/v1/runs', headers=h, json={'message': 'Hello', 'submission_key': 'cursor'}).json()
        shape(c.get(f"/api/v1/runs/{run['request_id']}/events", headers={'Last-Event-ID': 'x'}), 400, 'INVALID_INPUT')
        # the existing codes keep their status and code
        assert c.post('/api/v1/runs', json={}).json()['error']['code'] == 'ORIGIN_REJECTED'
        assert c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'owner', 'password': 'x'}).json() == \
            {'error': {'code': 'INVALID_CREDENTIALS'}}
        assert c.get('/api/v1/runs/edge_unknown').status_code == 404


def test_the_origin_check_skips_exactly_the_hooks_prefix(settings, store):
    """CONTRACT.md section 6: a hook needs no Origin (it proves itself by a signature); the body cap and the security
    headers stay; any other path, a look-alike prefix included, keeps the Origin check."""
    with TestClient(create_app(settings, store, FakeOrc())) as c:
        hook = c.post('/api/v1/hooks/payments/test', content=b'{}')
        shape(hook, 404, 'NOT_FOUND')                                      # no hook route in Phase 0; not ORIGIN_REJECTED
        assert hook.headers['x-content-type-options'] == 'nosniff' and 'frame-ancestors' in hook.headers['content-security-policy']
        assert c.post('/api/v1/hooks/payments/test', content=b'x' * 140000).json()['error']['code'] == 'REQUEST_TOO_LARGE'
        for path in ('/api/v1/hooksx/a', '/api/v1/hook/a', '/api/v1/runs', '/api/v2/hooks/a', '/hooks/a', '/api/v1/hooks'):
            r = c.post(path, content=b'{}')
            assert (r.status_code, r.json()['error']['code']) == (403, 'ORIGIN_REJECTED'), path
