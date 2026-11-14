"""EXEC-RADAR R6: the Radar page's data through this gateway (app/radar.py), the owner's EDGE session only."""
import dataclasses
import gzip
import hashlib
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main, radar
from app.main import create_app
from conftest import FakeOrc

ORIGIN = {'Origin': 'http://testserver'}
KEY = 'g' * 40
BODY = gzip.compress(json.dumps({'schema': 1, 'dates': ['2026-11-09']}).encode(), mtime=0)
SHA = hashlib.sha256(BODY).hexdigest()


def login(c):
    r = c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'owner', 'password': 'local-test-password'})
    assert r.status_code == 200, r.text
    return {**ORIGIN, 'X-CSRF-Token': r.json()['csrf_token']}


class FakeHttp:
    """terminal-api's GET/POST /radar and the bucket's presigned GET, recorded."""
    calls, files, stored = [], {}, {}

    def __init__(self, timeout):
        pass

    async def request(self, method, url, params=None, content=None, headers=None):
        FakeHttp.calls.append((method, url, dict(headers or {}), content))
        if url.endswith('/api/terminal/v1/radar') and method == 'GET':
            return httpx.Response(200, json={'finished_at': '2026-11-14T10:00:00Z', 'files': FakeHttp.files})
        if url.endswith('/api/terminal/v1/radar') and method == 'POST':
            name = json.loads(content)['names'][0]
            if name not in FakeHttp.files:
                return httpx.Response(404, json={'error': 'radar_not_published'})
            return httpx.Response(200, json={'files': [{'name': name, 'url': f'https://bucket.example/{name}',
                                                        'sha256': FakeHttp.files[name]['sha256']}]})
        if url.startswith('https://bucket.example/'):
            return httpx.Response(200, content=FakeHttp.stored.get(url.rsplit('/', 1)[1], b''))
        return httpx.Response(404, json={})


@pytest.fixture
def gw(settings, store, monkeypatch, tmp_path):
    (tmp_path / 'assets').mkdir()
    (tmp_path / 'index.html').write_text('<!doctype html><title>radar</title>')
    (tmp_path / 'assets' / 'index-abc123.js').write_text('void 0')
    monkeypatch.setattr(main, 'RADAR_APP', tmp_path)
    monkeypatch.setattr(radar.httpx, 'AsyncClient', FakeHttp)
    FakeHttp.calls = []
    FakeHttp.files = {'radar-days': {'sha256': SHA, 'bytes': len(BODY), 'rows': 1, 'as_of': '2026-11-09'}}
    FakeHttp.stored = {'radar-days': BODY}
    configured = dataclasses.replace(settings, terminal_url='http://terminal-api.railway.internal:8080', terminal_proxy_key=KEY)
    with TestClient(create_app(configured, store, FakeOrc())) as c:
        yield c


def test_the_radar_needs_the_owner_session(gw):
    for path in ('/api/v1/radar/index', '/api/v1/radar/file/radar-days'):
        assert gw.get(path).status_code == 401
    assert FakeHttp.calls == []


def test_index_and_file_bytes_are_relayed_with_the_gateway_key(gw):
    login(gw)
    r = gw.get('/api/v1/radar/index')
    assert r.status_code == 200 and r.json()['files']['radar-days']['sha256'] == SHA
    r = gw.get(f'/api/v1/radar/file/radar-days?sha={SHA}')
    assert r.status_code == 200 and r.json() == {'schema': 1, 'dates': ['2026-11-09']}       # gzip decoded by the client
    assert r.headers['content-encoding'] == 'gzip' and r.headers['etag'] == f'"{SHA[:32]}"'
    assert r.headers['cache-control'] == 'private, max-age=31536000, immutable'
    terminal = [c for c in FakeHttp.calls if '/api/terminal/v1/radar' in c[1]]
    assert terminal and all(c[2]['x-terminal-proxy-key'] == KEY for c in terminal)
    assert all('bucket.example' not in json.dumps(r.json()) for r in [gw.get('/api/v1/radar/index')])  # no URL to the page
    assert gw.get('/api/v1/radar/file/radar-days').headers['cache-control'] == 'private, no-cache'


def test_refusals_name_the_cause_and_the_way_out(gw):
    login(gw)
    for path, status, code in (('/api/v1/radar/file/secrets', 400, 'RADAR_INVALID_NAME'),
                               ('/api/v1/radar/file/radar-days?sha=xyz', 400, 'RADAR_INVALID_NAME'),
                               ('/api/v1/radar/file/radar-meta', 404, 'RADAR_FILE_NOT_PUBLISHED'),
                               (f'/api/v1/radar/file/radar-days?sha={"0" * 64}', 409, 'RADAR_FILE_REPLACED')):
        r = gw.get(path)
        assert r.status_code == status and r.json()['error']['code'] == code, (path, r.text)
        assert 'GET /api/v1/radar/index' in r.json()['error']['message'] or code == 'RADAR_INVALID_NAME'
    FakeHttp.stored['radar-days'] = b'other bytes'
    r = gw.get('/api/v1/radar/file/radar-days')
    assert r.status_code == 502 and r.json()['error']['code'] == 'RADAR_FILE_DAMAGED'


def test_the_radar_page_and_its_csp_and_the_capability(gw, settings, store):
    page = gw.get('/radar-app/')
    assert page.status_code == 200 and "connect-src 'self'" in page.headers['content-security-policy']
    assert gw.get('/radar-app/assets/index-abc123.js').headers['cache-control'].endswith('immutable')
    assert gw.get('/radar-app/assets/..%2Fsecret.js').status_code == 404
    login(gw)
    assert gw.get('/api/v1/auth/session').json()['capabilities']['radar'] is True
    with TestClient(create_app(settings, store, FakeOrc())) as plain:
        login(plain)
        assert plain.get('/api/v1/auth/session').json()['capabilities']['radar'] is False
        r = plain.get('/api/v1/radar/index')
        assert r.status_code == 503 and r.json()['error']['code'] == 'RADAR_NOT_CONFIGURED'


def test_the_shell_has_the_radar_tab_and_follows_edge_nav_only_from_its_frames(settings, store, monkeypatch, tmp_path):
    """The real shell in Chromium (ERRORS M425): the Radar tab after Screener opens /radar with its frame; the framed
    page's edge-nav message switches the shell to the Terminal; the same message from the top page itself, or for a
    route that is not a rail page, does nothing."""
    import os
    playwright = pytest.importorskip('playwright.sync_api')
    from test_screener import serve
    (tmp_path / 'assets').mkdir()
    (tmp_path / 'index.html').write_text('<!doctype html><title>Radar frame</title><button id="go">Open in Terminal</button>'
                                         '<button id="bad">Bad</button><script src="/radar-app/assets/probe-1.js"></script>')
    (tmp_path / 'assets' / 'probe-1.js').write_text(
        "document.getElementById('go').onclick = () => parent.postMessage({type: 'edge-nav', route: 'terminal'}, location.origin);"
        "document.getElementById('bad').onclick = () => parent.postMessage({type: 'edge-nav', route: 'login'}, location.origin);")
    monkeypatch.setattr(main, 'RADAR_APP', tmp_path)
    configured = dataclasses.replace(settings, terminal_url='http://terminal-api.railway.internal:8080', terminal_proxy_key=KEY)
    local, stop = serve(configured, store)
    try:
        with playwright.sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.environ.get('EDGE_TEST_CHROMIUM', '/usr/bin/chromium'),
                                         headless=True, args=['--no-sandbox'])
            try:
                page = browser.new_page()
                page.route('https://fonts.*/*', lambda route: route.abort())
                page.goto(local.origin + '/monitor')
                page.locator('#auth-login').fill('owner')
                page.locator('#auth-password').fill('local-test-password')
                page.get_by_role('button', name='Sign In', exact=True).click()
                tabs = page.locator('.side-nav > button[class*="nav-"]')
                tabs.first.wait_for()
                assert [tabs.nth(k).get_attribute('aria-label') for k in range(tabs.count())] == ['Monitor', 'Terminal', 'Backtest', 'Screener', 'Radar']
                page.locator('.side-nav button.nav-radar').click()
                page.wait_for_url(local.origin + '/radar')
                frame = page.locator('iframe.terminal-frame')
                assert frame.get_attribute('src').endswith('/radar-app/') and frame.get_attribute('title') == 'Radar'
                assert page.title() == 'EDGE — Radar'
                page.evaluate("postMessage({type: 'edge-nav', route: 'terminal'}, location.origin)")   # not from a frame
                page.frame_locator('iframe.terminal-frame').locator('#bad').click()                  # not a rail page
                page.wait_for_timeout(300)
                assert page.url == local.origin + '/radar'
                page.frame_locator('iframe.terminal-frame').locator('#go').click()
                page.wait_for_url(local.origin + '/terminal')
                page.reload()
                page.locator('.side-nav button.nav-radar').wait_for()                               # kept after a reload
            finally:
                browser.close()
    finally:
        stop()


def test_the_radar_tab_is_hidden_when_its_data_cannot_be_read(settings, store):
    """Without the terminal service the session says radar false, at sign-in already, and the shell hides the tab."""
    with TestClient(create_app(settings, store, FakeOrc())) as c:
        r = c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'owner', 'password': 'local-test-password'})
        assert r.json()['capabilities']['radar'] is False
    page = (main.STATIC / 'index.html').read_text()
    assert 'Edge.auth?.capabilities?.radar === true' in page and 'nav.filter(navShown)' in page


def test_the_image_builds_the_radar_page_on_its_own():
    """apps/edge-bff/Dockerfile: the radar stage installs from its lock file, builds, and the final image takes only its
    dist/ as static/radar-app; the page imports nothing outside its folder and no package."""
    import re
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / 'Dockerfile').read_text()
    stage = text.split('FROM node:22-slim AS radar', 1)[1].split('\nFROM ', 1)[0]
    assert [line for line in stage.strip().splitlines() if line.strip() and not line.startswith('#')] == [
        'WORKDIR /build/radar', 'COPY radar/package.json radar/package-lock.json ./', 'RUN npm ci --no-audit --no-fund',
        'COPY radar/ ./', 'RUN npm run build']
    assert 'COPY --from=radar /build/radar/dist ./static/radar-app\n' in text
    page = Path(__file__).resolve().parents[1] / 'radar' / 'src'
    for f in page.rglob('*.ts'):
        for spec in re.findall(r"""(?:\bfrom|\bimport)\s*\(?\s*['"]([^'"]+)['"]""", f.read_text()):
            assert spec.startswith('./') or spec.startswith('../') and (f.parent / spec).resolve().is_relative_to(page), (f, spec)
