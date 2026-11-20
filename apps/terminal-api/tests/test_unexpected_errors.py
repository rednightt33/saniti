"""ERRORS M500 (the open part, closed before the live site opens): an exception no handler expected is answered 503
service_unavailable in this service's error shape, and the log names its class and SQLSTATE only, never its text (a
database error's DETAIL can name a subscriber's email or an owner key). It never reaches the server's own log: nothing
re-raises it (TestClient raises a server exception by default, so the test would fail on one)."""
import json
import logging

from fastapi.testclient import TestClient

from app.main import create_app
from test_api import API, ORIGIN, PRIVATE, SETTINGS, FakeBucket, FakeStore


class RowError(Exception):
    sqlstate = '23505'


def test_an_unexpected_error_is_answered_503_and_logged_by_its_class_only(caplog):
    app = create_app(SETTINGS, FakeStore(), FakeBucket())

    @app.get(f'{API}/m500-boom')
    def boom():
        raise RowError('Key (email)=(someone@example.com) already exists')

    client = TestClient(app, base_url=PRIVATE, headers={'origin': ORIGIN})
    with caplog.at_level(logging.ERROR):
        r = client.get(f'{API}/m500-boom')
    assert r.status_code == 503 and r.json()['error'] == 'service_unavailable', r.text
    assert 'someone@example.com' not in r.text
    lines = [rec.getMessage() for rec in caplog.records]
    assert not any('someone@example.com' in line for line in lines), lines
    failed = [json.loads(line) for line in lines if '"request_failed"' in line]
    assert failed == [{'event': 'request_failed', 'method': 'GET', 'path': f'{API}/m500-boom',
                       'error': 'test_unexpected_errors.RowError', 'sqlstate': '23505'}]


def test_an_expected_refusal_keeps_its_own_answer():
    client = TestClient(create_app(SETTINGS, FakeStore(), FakeBucket()), base_url=PRIVATE, headers={'origin': ORIGIN})
    r = client.get(f'{API}/admin/subscribers', headers={'x-terminal-admin-key': 'wrong'})
    assert r.status_code == 401 and r.json()['error'] == 'admin_key_required'
