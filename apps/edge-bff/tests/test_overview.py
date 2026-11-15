"""EXEC-OVERVIEW O4: the Market Overview page's data through this gateway (app/overview.py on app/pages.py), the owner's
EDGE session only; its page and the shell's Overview tab."""
import dataclasses
import gzip
import hashlib
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main, pages
from app.main import create_app
from conftest import FakeOrc

ORIGIN = {'Origin': 'http://testserver'}
KEY = 'g' * 40
BODY = gzip.compress(json.dumps({'schema': 1, 'date': '2026-11-13'}).encode(), mtime=0)
SHA = hashlib.sha256(BODY).hexdigest()
NAME = 'overview-day-2026-11-13'


def login(c):
    r = c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'owner', 'password': 'local-test-password'})
    assert r.status_code == 200, r.text
    return {**ORIGIN, 'X-CSRF-Token': r.json()['csrf_token']}


class FakeHttp:
    """terminal-api's GET/POST /<family> and the bucket's presigned GET, recorded."""
    calls, files = [], {}

    def __init__(self, timeout):
        pass

    async def aclose(self):
        pass

    def stream(self, method, url):
        FakeHttp.calls.append((method, url, {}, None))

        class Answer:
            status_code = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def aiter_bytes(self):
                yield BODY
        return Answer()

    async def request(self, method, url, params=None, content=None, headers=None):
        FakeHttp.calls.append((method, url, dict(headers or {}), content))
        if url.endswith('/api/terminal/v1/overview') and method == 'GET':
            return httpx.Response(200, json={'finished_at': '2026-11-15T10:00:00Z', 'files': FakeHttp.files})
        if url.endswith('/api/terminal/v1/overview') and method == 'POST':
            name = json.loads(content)['names'][0]
            return httpx.Response(200, json={'files': [{'name': name, 'url': f'https://bucket.example/{name}',
                                                        'sha256': FakeHttp.files[name]['sha256'],
                                                        'bytes': FakeHttp.files[name]['bytes']}]})
        return httpx.Response(404, json={})


@pytest.fixture
def gw(settings, store, monkeypatch, tmp_path):
    (tmp_path / 'assets').mkdir()
    (tmp_path / 'index.html').write_text('<!doctype html><title>overview</title>')
    (tmp_path / 'assets' / 'index-abc123.js').write_text('void 0')
    monkeypatch.setattr(main, 'OVERVIEW_APP', tmp_path)
    monkeypatch.setattr(pages.httpx, 'AsyncClient', FakeHttp)
    FakeHttp.calls = []
    FakeHttp.files = {NAME: {'sha256': SHA, 'bytes': len(BODY), 'rows': 836, 'as_of': '2026-11-13'}}
    configured = dataclasses.replace(settings, terminal_url='http://terminal-api.railway.internal:8080', terminal_proxy_key=KEY)
    with TestClient(create_app(configured, store, FakeOrc())) as c:
        yield c


def test_the_overview_needs_the_owner_session(gw):
    for path in ('/api/v1/overview/index', f'/api/v1/overview/file/{NAME}'):
        assert gw.get(path).status_code == 401
    assert FakeHttp.calls == []


def test_its_index_and_files_come_from_terminal_apis_overview_routes_with_the_gateway_key(gw):
    login(gw)
    r = gw.get('/api/v1/overview/index')
    assert r.status_code == 200 and r.json()['files'][NAME]['sha256'] == SHA
    r = gw.get(f'/api/v1/overview/file/{NAME}?sha={SHA}')
    assert r.status_code == 200 and r.json() == {'schema': 1, 'date': '2026-11-13'}
    assert r.headers['cache-control'] == 'private, max-age=31536000, immutable'
    terminal = [c for c in FakeHttp.calls if '/api/terminal/v1/' in c[1]]
    assert terminal and all(c[1].endswith('/api/terminal/v1/overview') and c[2]['x-terminal-proxy-key'] == KEY
                            for c in terminal)


def test_refusals_carry_the_overviews_own_codes_and_way_out(gw):
    login(gw)
    for path, status, code in (('/api/v1/overview/file/radar-meta', 400, 'OVERVIEW_INVALID_NAME'),
                               ('/api/v1/overview/file/overview-meta', 404, 'OVERVIEW_FILE_NOT_PUBLISHED'),
                               (f'/api/v1/overview/file/{NAME}?sha={"0" * 64}', 409, 'OVERVIEW_FILE_REPLACED')):
        r = gw.get(path)
        assert r.status_code == status and r.json()['error']['code'] == code, (path, r.text)
        assert 'Market Overview' in r.json()['error']['message']
    assert 'overview-meta, overview-series' in gw.get('/api/v1/overview/file/x').json()['error']['message']


def test_the_overview_page_its_csp_and_the_capability(gw, settings, store):
    page = gw.get('/overview-app/')
    assert page.status_code == 200 and "connect-src 'self'" in page.headers['content-security-policy']
    assert gw.get('/overview-app/assets/index-abc123.js').headers['cache-control'].endswith('immutable')
    assert gw.get('/overview').status_code == 200                                 # the shell's route
    login(gw)
    caps = gw.get('/api/v1/auth/session').json()['capabilities']
    assert caps['overview'] is True and caps['radar'] is True
    with TestClient(create_app(settings, store, FakeOrc())) as plain:
        login(plain)
        assert plain.get('/api/v1/auth/session').json()['capabilities']['overview'] is False
        r = plain.get('/api/v1/overview/index')
        assert r.status_code == 503 and r.json()['error']['code'] == 'OVERVIEW_NOT_CONFIGURED'


def test_the_shell_puts_the_overview_tab_first_and_opens_its_frame(settings, store, monkeypatch, tmp_path):
    """The real shell in Chromium: with the capability the rail starts with Overview; its tab opens /overview with the
    page's frame and title; the page's edge-nav message (Open Terminal) switches the shell to the Terminal."""
    import os
    playwright = pytest.importorskip('playwright.sync_api')
    from test_screener import serve
    (tmp_path / 'assets').mkdir()
    (tmp_path / 'index.html').write_text('<!doctype html><title>Overview frame</title><button id="go">Open Terminal</button>'
                                         '<script src="/overview-app/assets/probe-1.js"></script>')
    (tmp_path / 'assets' / 'probe-1.js').write_text(
        "document.getElementById('go').onclick = () => parent.postMessage({type: 'edge-nav', route: 'terminal'}, location.origin);"
        "document.body.dataset.ready = '1';")
    monkeypatch.setattr(main, 'OVERVIEW_APP', tmp_path)
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
                assert tabs.first.get_attribute('aria-label') == 'Overview'
                page.locator('.side-nav button.nav-overview').click()
                page.wait_for_url(local.origin + '/overview')
                frame = page.locator('iframe.terminal-frame')
                assert frame.get_attribute('src').endswith('/overview-app/') and frame.get_attribute('title') == 'Market overview'
                assert page.title() == 'EDGE — Overview'
                page.frame_locator('iframe.terminal-frame').locator('body[data-ready="1"]').wait_for()   # its script ran
                page.frame_locator('iframe.terminal-frame').locator('#go').click()
                page.wait_for_url(local.origin + '/terminal')
            finally:
                browser.close()
    finally:
        stop()


def test_the_image_builds_the_overview_page_on_its_own():
    """apps/edge-bff/Dockerfile: the overview stage installs from its lock file, builds, and the final image takes only its
    dist/ as static/overview-app; the page imports nothing outside its folder and no package (it computes no figure: every
    number is the publisher's)."""
    import re
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / 'Dockerfile').read_text()
    stage = text.split('FROM node:22-slim AS overview', 1)[1].split('\nFROM ', 1)[0]
    assert [line for line in stage.strip().splitlines() if line.strip() and not line.startswith('#')] == [
        'WORKDIR /build/overview', 'COPY overview/package.json overview/package-lock.json ./', 'RUN npm ci --no-audit --no-fund',
        'COPY overview/ ./', 'RUN npm run build']
    assert 'COPY --from=overview /build/overview/dist ./static/overview-app\n' in text
    page = Path(__file__).resolve().parents[1] / 'overview' / 'src'
    for f in page.rglob('*.ts'):
        for spec in re.findall(r"""(?:\bfrom|\bimport)\s*\(?\s*['"]([^'"]+)['"]""", f.read_text()):
            assert spec.startswith('./') or spec.startswith('../') and (f.parent / spec).resolve().is_relative_to(page), (f, spec)


def test_a_phone_reaches_every_page_through_the_pages_menu(settings, store, monkeypatch, tmp_path):
    """EXEC-OVERVIEW QA (user 2026-11-15: "1B"): at 720 px or less the left menu is hidden; the EDGE bar's menu button
    lists the same pages (Overview first for the owner), switches to the one picked and closes on Escape."""
    import os
    playwright = pytest.importorskip('playwright.sync_api')
    from test_screener import serve
    (tmp_path / 'index.html').write_text('<!doctype html><title>Overview frame</title><body data-ready="1">')
    monkeypatch.setattr(main, 'OVERVIEW_APP', tmp_path)
    configured = dataclasses.replace(settings, terminal_url='http://terminal-api.railway.internal:8080', terminal_proxy_key=KEY)
    local, stop = serve(configured, store)
    try:
        with playwright.sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.environ.get('EDGE_TEST_CHROMIUM', '/usr/bin/chromium'),
                                         headless=True, args=['--no-sandbox'])
            try:
                page = browser.new_page(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
                page.route('https://fonts.*/*', lambda route: route.abort())
                page.goto(local.origin + '/monitor')
                page.locator('#auth-login').fill('owner')
                page.locator('#auth-password').fill('local-test-password')
                page.get_by_role('button', name='Sign In', exact=True).click()
                button = page.locator('.topbar .pages-btn')
                button.wait_for()
                assert not page.locator('.side-nav').is_visible()
                button.tap()
                items = page.locator('.pages-menu [role=menuitem]')
                assert items.all_text_contents()[:3] == ['Overview', 'Monitor', 'Terminal'] and 'Radar' in items.all_text_contents()
                assert button.get_attribute('aria-expanded') == 'true'
                for item in items.all():                                     # every item is a 44 px touch target
                    assert item.bounding_box()['height'] >= 44
                page.locator('.pages-menu [role=menuitem]', has_text='Overview').tap()
                page.wait_for_url(local.origin + '/overview')
                assert page.locator('.pages-menu').count() == 0
                button.tap()
                assert page.locator('.pages-menu [aria-current=page]').inner_text() == 'Overview'
                page.keyboard.press('Escape')
                assert page.locator('.pages-menu').count() == 0
                button.tap()
                page.locator('.topbar .brand').tap()                         # a tap outside closes it
                assert page.locator('.pages-menu').count() == 0
            finally:
                browser.close()
    finally:
        stop()
