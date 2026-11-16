"""EXEC-MU-ACCOUNTS Phase 0 (verification/edge_multiuser/access_tiers/CONTRACT.md section 7; ERRORS M470):
terminal-api without a public domain (private-only), and the EDGE gateway key accepted only on the private host."""
import datetime as dt

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import PRIVATE_HOST, Settings
from app.main import API, create_app
from test_api import (ADMIN, BACKTEST, BACKTEST_KEY, NOW, ORIGIN, PRIVATE, PROXY_KEY, SCREENER_KEY, SETTINGS,
                      FakeBucket, FakeStore)

GATEWAY = {'x-terminal-proxy-key': PROXY_KEY}
GENERIC = {'error': 'gateway_host_not_allowed',
           'message': 'This address does not accept keyed requests. Fix: call terminal-api from inside its own network, '
                      'where your service is configured to reach it; a person opens the Terminal in EDGE.'}
REQUIRED = {'TERMINAL_DATABASE_URL': 'postgresql://terminal_api_login@db/x', 'TERMINAL_ADMIN_KEY': 'k' * 40,
            'TERMINAL_BUCKET_NAME': 'b', 'TERMINAL_BUCKET_ENDPOINT': 'https://e', 'TERMINAL_BUCKET_REGION': 'auto',
            'TERMINAL_BUCKET_ACCESS_KEY_ID': 'a', 'TERMINAL_BUCKET_SECRET_ACCESS_KEY': 's',
            'TERMINAL_PROXY_KEY': PROXY_KEY, 'TERMINAL_PROXY_SUBSCRIBER': 'sub@example.com'}


def app_with(origins, host_url=PRIVATE):
    store = FakeStore()
    settings = Settings(**{**SETTINGS.__dict__, 'allowed_origins': origins, 'proxy_key': PROXY_KEY,
                           'proxy_subscriber': 'sub@example.com',
                           'service_keys': (('backtest-worker', BACKTEST_KEY), ('screener-worker', SCREENER_KEY))})
    settings.validate()
    client = TestClient(create_app(settings, store, FakeBucket()), base_url=host_url)
    r = client.post(f'{API}/admin/subscribers', headers={**ADMIN, 'host': PRIVATE_HOST}, json={
        'email': 'sub@example.com', 'display_name': 'Owner', 'password': 'correct horse battery',
        'expires_at': (NOW + dt.timedelta(days=30)).isoformat()})
    assert r.status_code == 201, r.text
    for name in ('backtest-worker', 'screener-worker'):
        store.add_subscriber(None, f'{name}@terminal.local', name, None, NOW + dt.timedelta(days=30))
        store.subs[len(store.subs)]['kind'] = 'service'
    return client, store


@pytest.fixture()
def private():
    return app_with(())


def test_starts_private_only_without_a_public_domain_or_origins(monkeypatch):
    """The public domain removed: RAILWAY_PUBLIC_DOMAIN and TERMINAL_ALLOWED_ORIGINS unset is a valid start."""
    for name in ('RAILWAY_PUBLIC_DOMAIN', 'TERMINAL_ALLOWED_ORIGINS'):
        monkeypatch.delenv(name, raising=False)
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name, value)
    s = Settings.from_env()
    assert s.allowed_origins == () and s.private_only and s.proxy_hosts == (PRIVATE_HOST,)
    app = create_app(s, FakeStore(), FakeBucket())
    assert TestClient(app).get('/health').json() == {'status': 'ok'}
    monkeypatch.setenv('RAILWAY_PUBLIC_DOMAIN', 'terminal-api-dev.up.railway.app')
    assert not Settings.from_env().private_only                              # the domain still there: as before


def test_private_only_refuses_the_direct_sign_in_with_the_fix(private):
    client, store = private
    for headers in ({}, {'origin': ORIGIN}, GATEWAY):
        r = client.post(f'{API}/auth/sign-in', headers=headers,
                        json={'email': 'sub@example.com', 'password': 'correct horse battery'})
        assert r.status_code == 403 and r.json()['error'] == 'direct_access_closed', r.text
        assert 'private-only' in r.json()['message'] and 'Fix: open the Terminal in EDGE' in r.json()['message']
        assert 'set-cookie' not in r.headers
    assert store.attempts == [] and store.sessions == {}                    # refused before any database work


def test_private_only_refuses_every_cookie_route(private):
    client, store = private
    store.open_session(None, 1, 'h', None, 24, 2)                           # a session left from before
    client.cookies.set('terminal_session', 'anything')
    for method, path, body in (('get', '/manifest/BBCA', None), ('get', '/state', None), ('get', '/auth/session', None),
                               ('get', '/reference/tickers', None), ('get', '/logo/BBCA', None),
                               ('post', '/auth/sign-out', None),
                               ('post', '/files', {'ticker': 'BBCA', 'dataset': 'price', 'years': [2026]}),
                               ('post', '/bundle', {'ticker': 'BBCA', 'datasets': ['price']}),
                               ('post', '/auth/change-password', {'current_password': 'correct horse battery',
                                                                  'new_password': 'another long password'})):
        r = getattr(client, method)(f'{API}{path}', headers={'origin': ORIGIN}, **({'json': body} if body else {}))
        assert r.status_code == 403 and r.json()['error'] == 'direct_access_closed', (path, r.text)
    assert store.access == []


def test_private_only_sends_no_cors_answer(private):
    client, _ = private
    r = client.options(f'{API}/bundle', headers={'origin': ORIGIN, 'access-control-request-method': 'POST'})
    assert 'access-control-allow-origin' not in r.headers
    assert 'access-control-allow-credentials' not in r.headers


def test_private_only_keeps_the_gateway_the_services_and_the_admin(private):
    client, store = private
    assert client.get(f'{API}/manifest/BBCA', headers=GATEWAY).status_code == 200
    r = client.post(f'{API}/bundle', headers=GATEWAY, json={'ticker': 'BBCA', 'datasets': ['price']})
    assert r.status_code == 200 and store.access[-1]['sid'] == 1
    assert client.get(f'{API}/state', headers=BACKTEST).status_code == 200
    assert client.get(f'{API}/admin/subscribers', headers=ADMIN).status_code == 200


def test_gateway_key_accepted_on_the_host_edge_bff_sends():
    """edge-bff calls EDGE_TERMINAL_URL=http://terminal-api.railway.internal:8080 with httpx (app/main.py
    forward_terminal, app/pages.py): the Host it sends is accepted, with and without a port."""
    sent = httpx.Request('GET', f'{PRIVATE}{API}/state',
                         headers={'content-type': 'application/json', 'x-terminal-proxy-key': PROXY_KEY})
    assert sent.headers['host'] == 'terminal-api.railway.internal:8080'
    for origins in ((), (ORIGIN,)):
        client, _ = app_with(origins)
        assert client.get(f'{API}/state', headers={**GATEWAY, 'host': sent.headers['host']}).status_code == 200
        assert client.get(f'{API}/state', headers={**GATEWAY, 'host': PRIVATE_HOST}).status_code == 200
        assert client.get(f'{API}/state', headers={**GATEWAY, 'host': 'TERMINAL-API.railway.internal'}).status_code == 200


@pytest.mark.parametrize('origins', [(), (ORIGIN,)])
@pytest.mark.parametrize('host, extra', [
    ('terminal-api-dev.up.railway.app', {}),                                # the public domain
    ('terminal-api-dev.up.railway.app:443', {}),
    ('testserver', {}),                                                     # any other host
    ('terminal-api.railway.internal.evil.example', {}),
    ('', {}),
    (PRIVATE_HOST, {'x-forwarded-for': '203.0.113.9'}),                     # the private name through the public edge
    (PRIVATE_HOST, {'x-railway-edge': 'railway/asia-southeast1'}),
    (PRIVATE_HOST, {'x-forwarded-host': 'terminal-api-dev.up.railway.app'}),
])
def test_gateway_key_refused_on_a_public_or_other_host(origins, host, extra):
    client, store = app_with(origins)
    r = client.get(f'{API}/manifest/BBCA', headers={**GATEWAY, 'host': host, **extra})
    assert r.status_code == 403 and r.json()['error'] == 'gateway_host_not_allowed', r.text
    assert r.json() == GENERIC                                              # nothing about the key, host or names
    r = client.post(f'{API}/bundle', headers={**GATEWAY, 'host': host, **extra},
                    json={'ticker': 'BBCA', 'datasets': ['price']})
    assert r.status_code == 403 and store.access == []                      # nothing granted, nothing counted


@pytest.mark.parametrize('origins', [(), (ORIGIN,)])
def test_off_the_private_host_a_valid_and_a_wrong_key_get_the_same_answer(origins, caplog):
    """C1 M3: every key (gateway, service, admin) off the private host gets one generic answer, whether it is valid,
    wrong or absent; the reason and the credential kind are in the server log, never the key."""
    client, store = app_with(origins)
    public = {'host': 'terminal-api-dev.up.railway.app', 'x-forwarded-for': '203.0.113.9'}
    answers = []
    for key in (GATEWAY, {'x-terminal-proxy-key': 'x' * 40}, BACKTEST, {'x-terminal-proxy-key': SCREENER_KEY}):
        r = client.get(f'{API}/state', headers={**key, **public})
        answers.append((r.status_code, r.json()))
    for admin_key in (ADMIN, {'x-terminal-admin-key': 'z' * 40}, {}):
        r = client.get(f'{API}/admin/subscribers', headers={**admin_key, **public})
        answers.append((r.status_code, r.json()))
    assert answers == [(403, GENERIC)] * 7
    for text in (str(answers),):
        for name in (PRIVATE_HOST, 'TERMINAL_', 'EDGE_TERMINAL_URL', 'gateway key', 'service key', 'backtest'):
            assert name not in text
    logged = caplog.text
    assert 'credential: gateway' in logged and 'credential: admin' in logged and 'service backtest-worker' in logged
    assert PROXY_KEY not in logged and BACKTEST_KEY not in logged and 'k' * 40 not in logged
    assert store.access == []
    # on the private host the admin key works, a wrong one keeps its own 401
    assert client.get(f'{API}/admin/subscribers', headers={**ADMIN, 'host': PRIVATE_HOST}).status_code == 200
    r = client.get(f'{API}/admin/subscribers', headers={'x-terminal-admin-key': 'z' * 40, 'host': PRIVATE_HOST})
    assert r.status_code == 401 and r.json()['error'] == 'admin_key_required'


def test_the_host_rule_reads_only_a_plain_name_and_port():
    client, _ = app_with(())
    for ok in (PRIVATE_HOST, f'{PRIVATE_HOST}:8080', 'Terminal-Api.Railway.Internal:1'):
        assert client.get(f'{API}/state', headers={**GATEWAY, 'host': ok}).status_code == 200, ok
    for bad in (f'{PRIVATE_HOST}.', f'{PRIVATE_HOST}:', f'{PRIVATE_HOST}:80a', f'{PRIVATE_HOST}:123456',
                f'u@{PRIVATE_HOST}', f'{PRIVATE_HOST}/x', f'{PRIVATE_HOST}?x', f'{PRIVATE_HOST}#x', f' {PRIVATE_HOST}',
                f'[{PRIVATE_HOST}]', f'{PRIVATE_HOST}:8080:1'):
        r = client.get(f'{API}/state', headers={**GATEWAY, 'host': bad})
        assert r.status_code == 403 and r.json() == GENERIC, bad


def test_proxy_hosts_never_name_a_public_domain():
    base = {**SETTINGS.__dict__, 'proxy_key': PROXY_KEY, 'proxy_subscriber': 'sub@example.com'}
    for bad in (('terminal-api-dev.up.railway.app',), ('',), ('Terminal-API.railway.internal',),
                ('terminal-api.railway.internal:8080',)):
        with pytest.raises(ValueError, match='private host name'):
            Settings(**{**base, 'proxy_hosts': bad}).validate()
    Settings(**base).validate()


def test_with_an_origin_the_direct_sign_in_still_works():
    """While a browser origin is configured (before the domain is removed) the direct sign-in is unchanged."""
    client, _ = app_with((ORIGIN,), host_url='https://terminal-api-dev.up.railway.app')
    r = client.post(f'{API}/auth/sign-in', headers={'origin': ORIGIN},
                    json={'email': 'sub@example.com', 'password': 'correct horse battery'})
    assert r.status_code == 200 and client.get(f'{API}/auth/session').status_code == 200
