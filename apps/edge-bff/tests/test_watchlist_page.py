"""EXEC-WATCHLIST L5: the Watchlist page (apps/edge-bff/watchlist -> static/watchlist-app) and the shell's Watchlist tab,
as tests/test_overview.py does for the Overview: the page's route and policy, the tab right after Overview in the rail
and in the phone's pages menu, the capability that shows it, the frame's edge-nav, the image stage; and, when the page is
built (npm run build), the real page in the frame on a made-up daily file, creating the first list and adding a stock
through /api/v1/watchlist/lists with the session's CSRF token. Needs EDGE_TEST_POSTGRES_URL, as the others."""
import dataclasses
import gzip
import hashlib
import json
import os
import re
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main, pages
from app.main import create_app
from conftest import FakeOrc

ORIGIN = {'Origin': 'http://testserver'}
KEY = 'w' * 40
ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / 'watchlist' / 'tests' / 'fixture' / 'watchlist-stocks.sample.json'
BODY = gzip.compress(SAMPLE.read_bytes(), mtime=0)
SHA = hashlib.sha256(BODY).hexdigest()
NAME = 'watchlist-stocks'
CHROMIUM = os.environ.get('EDGE_TEST_CHROMIUM', '/usr/bin/chromium')


def login(c):
    r = c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'owner', 'password': 'local-test-password'})
    assert r.status_code == 200, r.text
    return {**ORIGIN, 'X-CSRF-Token': r.json()['csrf_token']}


class FakeHttp:
    """terminal-api's GET/POST /watchlist and the bucket's presigned GET; any other terminal route answers 404."""
    calls = []

    def __init__(self, timeout):
        pass

    async def aclose(self):
        pass

    def stream(self, method, url):
        FakeHttp.calls.append((method, url))

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
        FakeHttp.calls.append((method, url))
        files = {NAME: {'sha256': SHA, 'bytes': len(BODY), 'rows': 14, 'as_of': '2026-11-13'}}
        if url.endswith('/api/terminal/v1/watchlist') and method == 'GET':
            return httpx.Response(200, json={'finished_at': '2026-11-16T10:00:00Z', 'files': files})
        if url.endswith('/api/terminal/v1/watchlist') and method == 'POST':
            return httpx.Response(200, json={'files': [{'name': NAME, 'url': 'https://bucket.example/w', 'sha256': SHA, 'bytes': len(BODY)}]})
        return httpx.Response(404, json={'error': 'not_found'})


def configured(settings):
    return dataclasses.replace(settings, terminal_url='http://terminal-api.railway.internal:8080', terminal_proxy_key=KEY)


@pytest.fixture
def frame(monkeypatch, tmp_path):
    (tmp_path / 'assets').mkdir()
    (tmp_path / 'index.html').write_text('<!doctype html><title>Watchlist frame</title><button id="go">Open in Terminal</button>'
                                         '<script src="/watchlist-app/assets/probe-1.js"></script>')
    (tmp_path / 'assets' / 'probe-1.js').write_text(
        "document.getElementById('go').onclick = () => parent.postMessage({type: 'edge-nav', route: 'terminal'}, location.origin);"
        "document.body.dataset.ready = '1';")
    monkeypatch.setattr(main, 'WATCHLIST_APP', tmp_path)
    return tmp_path


def signed_in_page(browser, local, **kw):
    page = browser.new_page(**kw)
    page.route('https://fonts.*/*', lambda route: route.abort())
    page.goto(local.origin + '/monitor')
    page.locator('#auth-login').fill('owner')
    page.locator('#auth-password').fill('local-test-password')
    page.get_by_role('button', name='Sign In', exact=True).click()
    return page


def test_the_watchlist_page_its_policy_and_the_capability(settings, store, frame):
    with TestClient(create_app(configured(settings), store, FakeOrc())) as c:
        page = c.get('/watchlist-app/')
        assert page.status_code == 200
        csp = page.headers['content-security-policy']
        # the Terminal page's policy: no inline script, and the bucket only for the logo list (EXEC-WATCHLIST L5)
        assert csp == main.TERMINAL_CSP and "script-src 'self';" in csp and "img-src 'self' data: blob:;" in csp
        assert c.get('/watchlist-app/assets/probe-1.js').headers['cache-control'].endswith('immutable')
        assert c.get('/watchlist').status_code == 200                                 # the shell's route
        assert c.get('/overview-app/').headers['content-security-policy'] == main.SCREENER_CSP   # unchanged
        login(c)
        assert c.get('/api/v1/auth/session').json()['capabilities']['watchlist'] is True
    with TestClient(create_app(settings, store, FakeOrc())) as plain:
        login(plain)
        assert plain.get('/api/v1/auth/session').json()['capabilities']['watchlist'] is False


def test_the_shell_wording_and_routes_name_the_watchlist():
    page = (main.STATIC / 'index.html').read_text()
    labels = (main.STATIC / 'edge-labels.js').read_text()
    assert 'watchlist: { nav:"Watchlist", frameTitle:"Watchlist" }' in labels and 'watchlist:"EDGE — Watchlist"' in labels
    assert '[[EdgeLabels.overview.nav, "overview"], [EdgeLabels.watchlist.nav, "watchlist"], ["Monitor", "monitor"]' in page
    assert 'const OWNER_PAGES = ["overview", "watchlist", "radar"];' in page
    assert '"radar", "overview", "watchlist"].includes(e.data.route)' in page
    assert 'src: "/watchlist-app/", title: EdgeLabels.watchlist.frameTitle' in page
    assert 'navWatchlist:' in page


def test_the_shell_puts_watchlist_after_overview_and_opens_its_frame(settings, store, frame):
    """The real shell in Chromium: the rail starts Overview, Watchlist; the tab opens /watchlist with the page's frame and
    title; the page's edge-nav message (Open in Terminal) switches the shell to the Terminal."""
    playwright = pytest.importorskip('playwright.sync_api')
    from test_screener import serve
    local, stop = serve(configured(settings), store)
    try:
        with playwright.sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=CHROMIUM, headless=True, args=['--no-sandbox'])
            try:
                page = signed_in_page(browser, local)
                tabs = page.locator('.side-nav > button[class*="nav-"]')
                tabs.first.wait_for()
                labels = [tabs.nth(k).get_attribute('aria-label') for k in range(tabs.count())]
                assert labels[:3] == ['Overview', 'Watchlist', 'Monitor'], labels
                page.locator('.side-nav button.nav-watchlist').click()
                page.wait_for_url(local.origin + '/watchlist')
                frame_el = page.locator('iframe.terminal-frame')
                assert frame_el.get_attribute('src').endswith('/watchlist-app/') and frame_el.get_attribute('title') == 'Watchlist'
                assert page.title() == 'EDGE — Watchlist'
                assert page.locator('.side-nav button.nav-watchlist').get_attribute('aria-current') == 'page'
                page.frame_locator('iframe.terminal-frame').locator('body[data-ready="1"]').wait_for()
                page.frame_locator('iframe.terminal-frame').locator('#go').click()
                page.wait_for_url(local.origin + '/terminal')
                page.goto(local.origin + '/watchlist')                               # the address opens the page
                page.locator('iframe.terminal-frame[src$="/watchlist-app/"]').wait_for()
                assert page.title() == 'EDGE — Watchlist'
            finally:
                browser.close()
    finally:
        stop()


def test_the_watchlist_tab_is_hidden_when_its_data_cannot_be_read(settings, store, frame):
    playwright = pytest.importorskip('playwright.sync_api')
    from test_screener import serve
    local, stop = serve(settings, store)                                        # no terminal service: watchlist false
    try:
        with playwright.sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=CHROMIUM, headless=True, args=['--no-sandbox'])
            try:
                page = signed_in_page(browser, local)
                page.locator('.side-nav button.nav-monitor').wait_for()
                assert page.locator('.side-nav button.nav-watchlist').count() == 0
            finally:
                browser.close()
    finally:
        stop()


def test_a_phone_reaches_the_watchlist_through_the_pages_menu(settings, store, frame):
    playwright = pytest.importorskip('playwright.sync_api')
    from test_screener import serve
    local, stop = serve(configured(settings), store)
    try:
        with playwright.sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=CHROMIUM, headless=True, args=['--no-sandbox'])
            try:
                page = signed_in_page(browser, local, viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
                button = page.locator('.topbar .pages-btn')
                button.wait_for()
                button.tap()
                items = page.locator('.pages-menu [role=menuitem]')
                assert items.all_text_contents()[:3] == ['Overview', 'Watchlist', 'Monitor']
                assert page.locator('.pages-menu .pages-watchlist').bounding_box()['height'] >= 44
                page.locator('.pages-menu [role=menuitem]', has_text='Watchlist').tap()
                page.wait_for_url(local.origin + '/watchlist')
                button.tap()
                assert page.locator('.pages-menu [aria-current=page]').inner_text() == 'Watchlist'
            finally:
                browser.close()
    finally:
        stop()


def test_the_image_builds_the_watchlist_page_on_its_own():
    """apps/edge-bff/Dockerfile: the watchlist stage installs from its lock file and builds; the final image takes only
    its dist/ as static/watchlist-app; the page imports nothing outside its folder and no package."""
    text = (ROOT / 'Dockerfile').read_text()
    stage = text.split('FROM node:22-slim AS watchlist', 1)[1].split('\nFROM ', 1)[0]
    assert [line for line in stage.strip().splitlines() if line.strip() and not line.startswith('#')] == [
        'WORKDIR /build/watchlist', 'COPY watchlist/package.json watchlist/package-lock.json ./', 'RUN npm ci --no-audit --no-fund',
        'COPY watchlist/ ./', 'RUN npm run build']
    assert 'COPY --from=watchlist /build/watchlist/dist ./static/watchlist-app\n' in text
    src = ROOT / 'watchlist' / 'src'
    for f in src.rglob('*.ts'):
        found = re.findall(r"""^\s*import\s+['"]([^'"]+)['"]|^\s*(?:import|export)\b[^'"\n]*\sfrom\s+['"]([^'"]+)['"]""",
                           f.read_text(), re.M)
        for spec in [a or b for a, b in found]:
            assert spec.startswith('./') or spec.startswith('../') and (f.parent / spec).resolve().is_relative_to(src), (f, spec)
    pkg = json.loads((ROOT / 'watchlist' / 'package.json').read_text())
    assert 'dependencies' not in pkg and set(pkg['devDependencies']) == {'typescript', 'vite', 'vitest'}


def test_the_sample_file_has_the_shape_the_publisher_writes():
    """The fixture's made-up file carries every field of apps/terminal-publisher/watchlist.py build() and its catalog."""
    doc = json.loads(SAMPLE.read_text())
    assert set(doc) == {'schema', 'prices_through', 'broker_through', 'radar_date', 'events_loaded', 'event_days', 'radar_board',
                        'dates', 'catalog', 'default', 'radar_filters', 'ticker', 'name', 'sector', 'last', 'r1d', 'r1m',
                        'trend', 'values', 'events', 'radar'}
    n = len(doc['ticker'])
    assert all(len(doc[k]) == n for k in ('name', 'sector', 'last', 'r1d', 'r1m', 'trend'))
    assert set(doc['values']) == {c['key'] for c in doc['catalog']} and all(len(v) == n for v in doc['values'].values())
    assert all(len(t) == len(doc['dates']) == 30 for t in doc['trend'])
    assert any(x is None for x in doc['last']) and doc['events'] and doc['radar']   # a stock without values, events, radar


@pytest.mark.skipif(not (ROOT / 'watchlist' / 'dist' / 'index.html').is_file(), reason='the page is not built (npm run build)')
def test_the_built_page_creates_the_first_list_and_adds_a_stock(settings, store, monkeypatch):
    """The production build in the shell's frame, on the made-up file relayed by /api/v1/watchlist: a first visit creates
    the list "Watchlist" for the account, Add ticker writes to it with the CSRF token, and the stock's card shows."""
    playwright = pytest.importorskip('playwright.sync_api')
    from test_screener import serve
    monkeypatch.setattr(main, 'WATCHLIST_APP', ROOT / 'watchlist' / 'dist')
    monkeypatch.setattr(pages.httpx, 'AsyncClient', FakeHttp)
    with store.connect() as c:
        c.execute('DELETE FROM edge_bff.watchlist_lists WHERE owner_key=%s', (settings.owner,))
    local, stop = serve(configured(settings), store)
    try:
        with playwright.sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=CHROMIUM, headless=True, args=['--no-sandbox'])
            try:
                page = signed_in_page(browser, local)
                errors = []
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.locator('.side-nav button.nav-watchlist').click()
                f = page.frame_locator('iframe.terminal-frame')
                f.locator('.bar1 [role=tab][aria-selected=true]', has_text='Watchlist').wait_for()
                assert 'Prices to Fri 13 Nov' in f.locator('.pills').inner_text()
                f.locator('.wlh [data-act=open-add]').click()
                f.locator('#adQ').fill('INTQ')
                f.locator('.ar[data-row=INTQ] [data-act=ad-one]').click()
                f.locator('.cg .wc[data-t=INTQ]').wait_for()
                assert f.locator('.cg .wc[data-t=INTQ] .chip').count() == 4                 # the file's default indicators
                assert errors == []
            finally:
                browser.close()
    finally:
        stop()
    with store.connect() as c:
        rows = c.execute('''SELECT l.name, i.ticker FROM edge_bff.watchlist_lists l JOIN edge_bff.watchlist_items i
            USING (owner_key, list_id) WHERE l.owner_key=%s''', (settings.owner,)).fetchall()
    assert [(r['name'], r['ticker']) for r in rows] == [('Watchlist', 'INTQ')]
