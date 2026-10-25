"""EXEC-TERMINAL-API T3-T5: the Terminal tab's page, its stricter CSP and the /api/terminal gateway to terminal-api."""
import dataclasses
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main
from app.main import create_app
from conftest import FakeOrc

ORIGIN = {'Origin': 'http://testserver'}
KEY = 'g' * 40


def login(c):
    r = c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'owner', 'password': 'local-test-password'})
    assert r.status_code == 200, r.text
    return {**ORIGIN, 'X-CSRF-Token': r.json()['csrf_token']}


class FakeTerminal:
    """Stands in for httpx.AsyncClient: records what the gateway forwards and answers like terminal-api."""
    calls = []

    def __init__(self, timeout):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def request(self, method, url, params=None, content=None, headers=None):
        FakeTerminal.calls.append({'method': method, 'url': url, 'params': dict(params or {}), 'body': content,
                                   'headers': dict(headers or {})})
        if url.endswith('/files'):
            return httpx.Response(429, json={'error': 'quota_exceeded', 'message': 'files per hour'})
        return httpx.Response(200, json={'ticker': 'BBCA', 'window': {'first_year': 2021}})


@pytest.fixture
def gateway(settings, store, monkeypatch, tmp_path):
    (tmp_path / 'assets').mkdir()
    (tmp_path / 'index.html').write_text('<!doctype html><title>terminal</title>')
    (tmp_path / 'assets' / 'index-abc123.js').write_text('void 0')
    monkeypatch.setattr(main, 'TERMINAL_APP', tmp_path)
    monkeypatch.setattr(main.httpx, 'AsyncClient', FakeTerminal)
    FakeTerminal.calls = []
    configured = dataclasses.replace(settings, terminal_url='http://terminal-api.railway.internal:8080', terminal_proxy_key=KEY)
    with TestClient(create_app(configured, store, FakeOrc())) as c:
        yield c


def test_terminal_tab_route_and_page_with_its_own_csp(gateway):
    c = gateway
    assert c.get('/terminal').status_code == 200 and 'EDGE' in c.get('/terminal').text
    page = c.get('/terminal-app/')
    assert page.status_code == 200 and 'terminal' in page.text
    csp = page.headers['content-security-policy']
    assert "script-src 'self';" in csp and 'unsafe-eval' not in csp and 'https://*.t3.storageapi.dev' in csp
    assert "frame-ancestors 'self'" in csp
    assert "connect-src 'self';" in c.get('/terminal').headers['content-security-policy']   # EDGE itself unchanged
    asset = c.get('/terminal-app/assets/index-abc123.js')
    assert asset.status_code == 200 and 'immutable' in asset.headers['cache-control']
    assert c.get('/terminal-app/assets/..%2F..%2Fapp%2Fmain.py').status_code == 404


def test_gateway_needs_the_edge_session_and_csrf_for_writes(gateway):
    c = gateway
    assert c.get('/api/terminal/v1/manifest/BBCA').status_code == 401
    h = login(c)
    assert c.post('/api/terminal/v1/files', headers=ORIGIN, json={'ticker': 'BBCA'}).status_code == 403
    assert c.post('/api/terminal/v1/files', json={'ticker': 'BBCA'}).status_code == 403   # no Origin
    assert FakeTerminal.calls == []
    r = c.post('/api/terminal/v1/files', headers=h, json={'ticker': 'BBCA', 'dataset': 'price', 'years': [2026]})
    assert r.status_code == 429 and r.json()['error'] == 'quota_exceeded'           # terminal-api's answer passes through
    sent = FakeTerminal.calls[-1]
    assert sent['url'] == 'http://terminal-api.railway.internal:8080/api/terminal/v1/files'
    assert sent['headers']['x-terminal-proxy-key'] == KEY and json.loads(sent['body'])['ticker'] == 'BBCA'
    assert 'cookie' not in {k.lower() for k in sent['headers']}


def test_gateway_forwards_only_the_data_routes(gateway):
    c = gateway
    login(c)
    assert c.get('/api/terminal/v1/manifest/BBCA').json()['ticker'] == 'BBCA'
    assert c.get('/api/terminal/v1/history/price?ticker=BBCA&from=2019-01-01&to=2019-02-01').status_code == 200
    assert FakeTerminal.calls[-1]['params'] == {'ticker': 'BBCA', 'from': '2019-01-01', 'to': '2019-02-01'}
    n = len(FakeTerminal.calls)
    for path in ('admin/subscribers', 'auth/session', 'manifest/bbca', 'manifest/../admin', 'reference/secrets'):
        assert c.get(f'/api/terminal/v1/{path}').status_code == 404, path
    assert len(FakeTerminal.calls) == n


def test_gateway_off_when_not_configured(settings, store):
    with TestClient(create_app(settings, store, FakeOrc())) as c:
        login(c)
        r = c.get('/api/terminal/v1/manifest/BBCA')
        assert r.status_code == 503 and r.json()['error']['code'] == 'TERMINAL_UNAVAILABLE'


def test_gateway_settings_are_paired_strong_and_private(settings):
    with pytest.raises(ValueError):
        dataclasses.replace(settings, terminal_url='http://terminal-api.railway.internal:8080').validate()
    with pytest.raises(ValueError):
        dataclasses.replace(settings, terminal_url='http://terminal-api.railway.internal:8080', terminal_proxy_key='short').validate()
    deployed = dataclasses.replace(settings, environment='dev', orc_url='http://market-ai-orc.railway.internal:8080',
                                   database_url='postgresql://edge_bff_login@db.internal/railway',
                                   origin='https://edge.example', secure_cookie=True, terminal_proxy_key=KEY)
    dataclasses.replace(deployed, terminal_url='http://terminal-api.railway.internal:8080').validate()
    with pytest.raises(ValueError, match='EDGE_TERMINAL_URL'):
        dataclasses.replace(deployed, terminal_url='https://terminal-api-dev.up.railway.app').validate()
