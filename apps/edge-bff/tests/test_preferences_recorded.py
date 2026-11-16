"""EXEC-MU-ACCOUNTS Phase 1 (contract 4b; AGENTS.md M68: a client is tested against recorded real answers): the answers
of the real preferences routes (app/preferences.py) to the requests the page's client sends
(shared/edge-session.ts preferences()), kept in terminal/tests/data/preferences.recorded.json. The page's test
(terminal/tests/data/edge_session_prefs_recorded.test.ts) replays them through the client. This test fails when the
server's answers no longer equal the recording: re-record with EDGE_RECORD_PREFERENCES=1 and run the page's test."""
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from conftest import FakeOrc
from test_edge import login

RECORDING = Path(__file__).resolve().parents[1] / 'terminal' / 'tests' / 'data' / 'preferences.recorded.json'

# (name, method, key, body): what the client sends, in order (a value is the page's storage text, a JSON string)
SCENARIO = [
    ('empty', 'GET', None, None),
    ('created', 'PUT', 'ml.my', {'value': '[{"id":"m1"}]', 'version': None}),
    ('replaced', 'PUT', 'ml.my', {'value': '[{"id":"m2"}]', 'version': 1}),
    ('stale', 'PUT', 'ml.my', {'value': '[]', 'version': 1}),
    ('created_elsewhere', 'PUT', 'scr.last', {'value': '{"name":"Mine"}', 'version': None}),
    ('missing_version', 'PUT', 'scr.last', {'value': '{"name":"Other"}', 'version': None}),
    ('filled', 'GET', None, None),
    ('too_large', 'PUT', 'ml.ind.v1', {'value': 'x' * 70000, 'version': None}),
]


def normalised(body):
    """updated_at is a time of the run: kept as a placeholder"""
    if isinstance(body, dict):
        return {k: ('<updated_at>' if k == 'updated_at' else normalised(v)) for k, v in body.items()}
    if isinstance(body, list):
        return [normalised(v) for v in body]
    return body


def record(client):
    out = []
    for name, method, key, body in SCENARIO:
        path = '/api/v1/preferences' + (f'/{key}' if key else '')
        r = client.get(path) if method == 'GET' else client.put(path, headers=client.h, json=body)
        shown = {**body, 'value': body['value'][:40] + '…'} if body and len(body['value']) > 1000 else body
        out.append({'name': name, 'request': {'method': method, 'path': path, 'body': shown}, 'status': r.status_code,
                    'body': normalised(r.json())})
    return out


@pytest.fixture
def signed(settings, store):
    with TestClient(create_app(settings, store, FakeOrc())) as c:
        c.h = login(c)
        yield c


def test_the_recorded_preference_answers_are_the_servers(signed):
    got = record(signed)
    if os.environ.get('EDGE_RECORD_PREFERENCES') == '1':
        RECORDING.write_text(json.dumps(got, indent=1, ensure_ascii=False) + '\n')
    assert json.loads(RECORDING.read_text()) == got, ('the preferences routes answer differently from '
        'terminal/tests/data/preferences.recorded.json: re-record with EDGE_RECORD_PREFERENCES=1, then run the page test')
