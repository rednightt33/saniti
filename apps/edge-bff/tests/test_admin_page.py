"""Phase 4, the admin page (apps/edge-bff/admin -> static/admin-app; app/main.py /admin and page_app admin_only; the
shell's /admin; CONTRACT.md 10; the user, 2026-11-22: "1A, 2B, 3A").

- Its files reach the admin on the beta only: a visitor, an account without admin.access and the admin before its second
  factor (the switch on) get 404 for the page and its assets; the live site answers 404 to everyone, /admin included.
  The beta's owner gets them before the page's code step (its screen is in them); the data stay behind the step.
- The shell: /admin opens the page in its frame with the ticket of its address; a sign-in shown at /admin?ticket=<id>
  stays there (a sign-in stays at a workspace page the account can open); the rail's shield and the account menu's
  "Admin page" for the admin only.
- The built page in a browser: the code step, the ticket of the Telegram link with its image, marked done, a write of the
  shell after the step (its session was renewed), the delete with a reason; every view at 1440, 1152, 390 and 360 px,
  light and dark, without sideways scroll.
Needs EDGE_TEST_POSTGRES_URL; the browser tests the page's build (npm run build in admin/; CI builds it first)."""
import dataclasses
import os
import re
import struct
import zlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main, releases
from app.main import SCREENER_CSP, create_app
from app.support import SupportStore
from conftest import FakeOrc
from test_3f_lab_pages import admin_access_account, beta_on
from test_admin import KEY, code_of, db, enrol, seed_id
from test_beta_live_site import live_of, sign_in_admin
from test_edge import ORIGIN, login
from test_phase3a_gates import paid_user
from test_principal import make_user

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'admin' / 'dist'
SHELL = ROOT / 'static'
CHROMIUM = os.environ.get('EDGE_TEST_CHROMIUM', '/usr/bin/chromium')
REQUIRE_NODE = os.environ.get('EDGE_TEST_REQUIRE_NODE') == '1'


@pytest.fixture
def built(tmp_path, monkeypatch):
    """A stand-in build of the admin page (its index and one asset)."""
    (tmp_path / 'assets').mkdir()
    (tmp_path / 'index.html').write_text('<!doctype html><title>ADMIN BUILD</title>')
    (tmp_path / 'assets' / 'index-admin01.js').write_text('void 0')
    monkeypatch.setattr(main, 'ADMIN_APP', tmp_path)
    return tmp_path


def statuses(c):
    return c.get('/admin-app/').status_code, c.get('/admin-app/assets/index-admin01.js').status_code


def test_the_page_files_reach_the_beta_admin_only_before_its_code_step(settings, store, built):
    beta = dataclasses.replace(settings, mfa_key=KEY)
    with TestClient(create_app(beta, store, FakeOrc())) as c:
        assert statuses(c) == (404, 404)                                    # a visitor
        assert c.get('/admin').status_code == 200                           # the shell, which asks to sign in
        login(c)
        assert statuses(c) == (200, 200)                                    # the owner, before the code step
        page = c.get('/admin-app/')
        assert 'ADMIN BUILD' in page.text and page.headers['content-security-policy'] == SCREENER_CSP
        asset = c.get('/admin-app/assets/index-admin01.js')
        assert asset.headers['cache-control'] == 'private, max-age=31536000, immutable'
        r = c.get('/api/v1/admin/overview')                                 # the data wait for the code
        assert (r.status_code, r.json()['error']['details'].get('step_up')) == (403, True)
        for bad in ('../index.html', 'index-admin01.js.map', '%2e%2e%2fmain.py'):
            assert c.get(f'/admin-app/assets/{bad}').status_code == 404, bad
    # the switch on (the beta's way later): an account without admin.access, then the admin before and after its code
    with TestClient(create_app(beta_on(settings), store, FakeOrc())) as c:
        alice = paid_user(store, 'alice_admin_page')
        r = c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': alice['username'], 'password': 'alice_admin_page-password'})
        assert r.status_code == 200, r.text
        assert statuses(c) == (404, 404)
    with TestClient(create_app(beta_on(settings), store, FakeOrc())) as c:
        r = c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'owner', 'password': 'local-test-password'})
        assert r.status_code == 403 and r.json()['error']['code'] == 'MFA_REQUIRED', r.text
        assert statuses(c) == (404, 404)
        sign_in_admin(c, store)
        assert statuses(c) == (200, 200)
    with TestClient(create_app(beta_on(settings), store, FakeOrc())) as c:
        admin_access_account(c, store, 'ops_admin_page')                    # admin.access by an override, no '*'
        assert statuses(c) == (200, 200)


def test_the_gate_does_not_rest_on_the_release_file(settings, store, built, monkeypatch):
    """admin is in no tab list of catalog/releases.json (a beta-only tab); were it listed as released one day, its page
    would still reach the admin only and stay out of shared caches (main.py page_app admin_only, not the stage)."""
    real = releases.tab_stage
    monkeypatch.setattr(releases, 'tab_stage', lambda tab: 'released' if tab == 'admin' else real(tab))
    with TestClient(create_app(dataclasses.replace(settings, mfa_key=KEY), store, FakeOrc())) as c:
        assert statuses(c) == (404, 404)                                    # a visitor
        login(c)
        assert statuses(c) == (200, 200)
        assert c.get('/admin-app/assets/index-admin01.js').headers['cache-control'] == 'private, max-age=31536000, immutable'


def test_the_live_site_serves_no_admin_page_to_anyone(settings, store, built):
    with TestClient(create_app(live_of(settings), store, FakeOrc())) as c:
        assert c.get('/admin').status_code == 404 and statuses(c) == (404, 404)
        sign_in_admin(c, store)                                             # the admin past its second factor
        assert c.get('/admin').status_code == 404 and statuses(c) == (404, 404)
        assert 'admin' in c.get('/api/v1/auth/config').json()['hidden_tabs']


def test_the_shell_names_the_page_its_route_and_its_entries_but_none_of_its_words():
    app_js, labels = (SHELL / 'edge-app.js').read_text(), (SHELL / 'edge-labels.js').read_text()
    assert '{path:"/admin", names:["admin"], auth:true, title:"admin", needs:"admin.access"}' in app_js
    assert 'src: `/admin-app/${ticket ? `?ticket=${ticket}` : ""}`' in app_js
    assert 'adminOpen() && element("button", { type: "button", className: `side-admin' in app_js
    assert 'openAdmin: adminOpen() ? () => go("admin") : null' in app_js and app_js.count('openAdmin: adminOpen()') == 2
    assert re.search(r'admin: \{ nav:"Admin", menu:"Admin page", frameTitle:"Admin", closed:"[^"]+" \}', labels)
    # the page's own words and data paths are in its build only, never in the public shell (3f's rule for lab code)
    for word in ('/api/v1/admin', 'Enter your authenticator code', 'Delete ticket', 'Download CSV'):
        assert word not in app_js and word not in labels, word


# ---- the built page in a browser ------------------------------------------------------------------------------------

def need_build():
    if not (DIST / 'index.html').is_file():
        if REQUIRE_NODE:
            pytest.fail('admin/dist is not built (npm run build in apps/edge-bff/admin; CI builds it before the tests)')
        pytest.skip('the admin page is not built (npm run build)')


def open_browser(pw):
    return pw.chromium.launch(executable_path=CHROMIUM, headless=True, args=['--no-sandbox'])


class Watch:
    """What went wrong in the page and its frame: an uncaught error, a console error (a policy refusal is one), a request
    that failed, and every answer of 400 or more (method, path, status), so a test names the ones it expects."""
    def __init__(self, page):
        self.errors, self.failed, self.answers = [], [], []
        page.on('pageerror', lambda e: self.errors.append(str(e)))
        # an answer of 400 or more is also logged as "Failed to load resource"; it is judged below, by its request
        page.on('console', lambda m: m.type == 'error' and 'Failed to load resource' not in m.text and self.errors.append(m.text))
        page.on('requestfailed', lambda r: self.failed.append((r.method, r.url, r.failure)))
        page.on('response', lambda r: r.status >= 400 and self.answers.append(
            (r.request.method, re.sub(r'^https?://[^/]+', '', r.url).split('?')[0], r.status)))

    def check(self, expected=()):
        unexpected = [a for a in self.answers if a not in expected]
        assert (self.errors, self.failed, unexpected) == ([], [], []), (self.errors, self.failed, unexpected)


def frame_of(page):
    page.locator('iframe.terminal-frame').wait_for()
    return page.frame_locator('iframe.terminal-frame')


def columns_match(frame):
    """[(visible header cells, visible cells of the first row)] of every table in the view with a row: each header sits
    over its column, a phone's hidden column hidden in both (admin/src/app.ts table)"""
    return frame.locator('#view').evaluate('''v => [...v.querySelectorAll('table')].filter(t => t.tBodies[0] && t.tBodies[0].rows[0])
        .map(t => [[...t.tHead.rows[0].cells].filter(c => c.offsetParent !== null).length,
                   [...t.tBodies[0].rows[0].cells].filter(c => c.offsetParent !== null).length])''')


def no_sideways(page):
    """(shell, frame): each document's scroll width against its own width"""
    inner = page.frame_locator('iframe.terminal-frame').locator('html')
    return (page.evaluate('() => document.documentElement.scrollWidth - innerWidth'),
            inner.evaluate('e => e.scrollWidth - e.ownerDocument.defaultView.innerWidth'))


def png(width=24, height=16):
    """A real PNG a browser draws (test_admin's PNG has the signature only, enough for the server's check)."""
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    rows = b''.join(b'\x00' + bytes([120, 140, 160]) * width for _ in range(height))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


PNG = png()


@pytest.fixture
def ticket_of_alice(store, settings):
    def make(subject='The chart does not load', images=(('screen.png', 'image/png', PNG),)):
        alice = make_user(store, 'alice_page', 'alice-password', email='alice.page@example.com')
        p = type('P', (), {'user_id': alice['user_id'], 'plan_key': 'free'})()
        return SupportStore(store, settings).create(p, 'bug', subject, 'I open BBCA and\nthe chart stays empty.',
                                                    {'page': '/terminal'}, list(images))['ticket_id']
    return make


def test_the_telegram_link_opens_its_ticket_after_sign_in_and_the_code(settings, store, monkeypatch, ticket_of_alice):
    """/admin?ticket=<id> signed out: the sign-in page at that address; signed in, the shell stays there and the frame
    asks for the code; with it, the ticket in full with its image. Marked done, then a write of the shell (Contact
    support) still works with the renewed session, then the ticket deleted with a reason."""
    need_build()
    playwright = pytest.importorskip('playwright.sync_api')
    from test_screener import serve
    monkeypatch.setattr(main, 'ADMIN_APP', DIST)
    beta = dataclasses.replace(settings, mfa_key=KEY)
    local, stop = serve(beta, store)                    # first: the app seeds user #1 into an empty users table
    try:
        ticket = ticket_of_alice()
        uid = seed_id(store, beta)
        nonce = enrol(store, uid)
        with playwright.sync_playwright() as pw:
            browser = open_browser(pw)
            try:
                page = browser.new_page(viewport={'width': 1440, 'height': 900})
                watch = Watch(page)
                page.goto(f'{local.origin}/admin?ticket={ticket}')
                page.locator('#auth-login').fill('owner')
                page.locator('#auth-password').fill('local-test-password')
                page.get_by_role('button', name='Sign In', exact=True).click()
                f = frame_of(page)
                assert page.evaluate('() => location.pathname + location.search') == f'/admin?ticket={ticket}'
                src = page.evaluate('() => { const u = new URL(document.querySelector("iframe.terminal-frame").src); return u.pathname + u.search }')
                assert src == f'/admin-app/?ticket={ticket}'
                assert page.locator('.side-nav .side-admin').get_attribute('aria-current') == 'page'
                # the code step: a wrong code says so under the field, the right one opens the ticket
                f.locator('#code').fill('000000' if code_of(uid, nonce) != '000000' else '111111')
                f.get_by_role('button', name='Open the admin page').click()
                f.locator('#code-error').filter(has_text=re.compile(r'\w')).wait_for()
                f.locator('#code').fill(code_of(uid, nonce))
                f.get_by_role('button', name='Open the admin page').click()
                f.locator('#ticket-subject').filter(has_text='The chart does not load').wait_for()
                assert 'the chart stays empty.' in f.locator('.message').inner_text()
                img = f.locator('.images img').first
                img.wait_for()
                page.wait_for_function('() => { const d = document.querySelector("iframe.terminal-frame").contentDocument;'
                                       ' const i = d && d.querySelector(".images img"); return i && i.complete && i.naturalWidth > 0 }')
                # done: the pill, the images' deletion day, the row
                f.get_by_role('button', name='Mark done').click()
                f.locator('.ticket .pill', has_text='Done').wait_for()
                assert 'deleted on' in f.locator('.images').inner_text()
                assert db(store, 'SELECT status FROM edge_bff.support_tickets WHERE ticket_id = %s', ticket)[0]['status'] == 'done'
                # the shell's own write after the step: its CSRF token was the old session's; the send repeats once
                page.locator('.side-nav .side-support').click()
                dialog = page.get_by_role('dialog')
                dialog.get_by_label('Subject').fill('From the admin page')
                dialog.get_by_label('Description').fill('A message after the code step.')
                dialog.get_by_role('button', name='Submit issue').click()
                dialog.get_by_text('Your message was sent').wait_for()
                dialog.get_by_role('button', name='Close').first.click()
                # the delete by hand (2B): a reason, then the list without it
                f.get_by_role('button', name='Delete ticket').click()
                box = f.get_by_role('dialog')
                box.get_by_role('button', name='Delete ticket').click()
                box.locator('#reason-error').filter(has_text='Write why').wait_for()
                box.get_by_label('Why delete it').fill('Answered by email')
                box.get_by_role('button', name='Delete ticket').click()
                f.locator('table.tickets, .empty').first.wait_for()
                assert db(store, 'SELECT count(*) AS n FROM edge_bff.support_tickets WHERE ticket_id = %s', ticket)[0]['n'] == 0
                trail = db(store, "SELECT action, reason FROM edge_bff.admin_audit WHERE action LIKE 'support.%%' ORDER BY audit_id")
                assert [(t['action'], t['reason']) for t in trail] == [('support.status', None), ('support.delete', 'Answered by email')]
                # expected: the shell's session read before the sign-in (401), the wrong code (400), the shell's first
                # write after the renewal (403 CSRF, repeated once with the renewed session)
                watch.check({('GET', '/api/v1/auth/session', 401), ('POST', '/api/v1/admin/step-up', 400),
                             ('POST', '/api/v1/support', 403)})
            finally:
                browser.close()
    finally:
        stop()


@pytest.mark.parametrize('width,height', [(1440, 900), (1152, 800), (390, 844), (360, 740)])
def test_every_view_fits_each_width_in_both_themes(settings, store, monkeypatch, ticket_of_alice, width, height):
    need_build()
    playwright = pytest.importorskip('playwright.sync_api')
    from test_screener import serve
    monkeypatch.setattr(main, 'ADMIN_APP', DIST)
    beta = dataclasses.replace(settings, mfa_key=KEY)
    local, stop = serve(beta, store)                    # first: the app seeds user #1 into an empty users table
    try:
        ticket_of_alice('A subject long enough to wrap on a phone screen without pushing the page sideways at all')
        uid = seed_id(store, beta)
        nonce = enrol(store, uid)
        with playwright.sync_playwright() as pw:
            browser = open_browser(pw)
            try:
                page = browser.new_page(viewport={'width': width, 'height': height})
                watch = Watch(page)
                page.goto(f'{local.origin}/login')
                page.locator('#auth-login').fill('owner')
                page.locator('#auth-password').fill('local-test-password')
                page.get_by_role('button', name='Sign In', exact=True).click()
                page.wait_for_function("() => window.Edge && Edge.auth !== null")
                if width > 640:
                    page.locator('.side-nav .side-admin').click()                 # the rail's shield
                else:                                                             # the phone: the account menu
                    page.get_by_role('button', name='Account menu').filter(visible=True).first.click()
                    page.get_by_role('menuitem', name='Admin page').click()
                f = frame_of(page)
                f.locator('#code').wait_for()
                assert no_sideways(page) == (0, 0)
                f.locator('#code').fill(code_of(uid, nonce))
                f.get_by_role('button', name='Open the admin page').click()
                f.locator('table.tickets').wait_for()
                inner = page.frame_locator('iframe.terminal-frame').locator('html')
                for theme in ('light', 'dark'):
                    if theme == 'dark':                                           # the shell's own theme button
                        page.get_by_role('button', name='Switch to dark theme').filter(visible=True).first.click()
                        page.wait_for_function("() => document.documentElement.classList.contains('dark')")
                        page.wait_for_function('() => document.querySelector("iframe.terminal-frame").contentDocument'
                                               '.documentElement.dataset.theme === "dark"')
                    assert inner.get_attribute('data-theme') == theme
                    for view in ('support', 'overview', 'accounts', 'audit', 'plans', 'settings'):
                        f.locator(f'#tab-{view}').click()
                        f.locator(f'#tab-{view}[aria-selected=true]').wait_for()
                        f.locator('#view .loading').wait_for(state='detached')
                        assert no_sideways(page) == (0, 0), (width, theme, view)
                        assert not re.search(r'\b(null|undefined|NaN)\b', f.locator('#view').inner_text()), (theme, view)
                        assert all(h == d for h, d in columns_match(f)), (width, theme, view, columns_match(f))
                    f.locator('#tab-support').click()
                    f.locator('table.tickets .linklike').first.click()
                    f.locator('#ticket-subject').wait_for()
                    assert no_sideways(page) == (0, 0), (width, theme, 'ticket')
                    box = f.locator('.ticket').bounding_box()
                    assert box['x'] >= 0 and box['x'] + box['width'] <= width, (width, theme, box)
                    if theme == 'light':
                        f.get_by_role('button', name='All tickets').click()
                    else:                                                         # the shown tab leads back to its list
                        f.locator('#tab-support').click()
                    f.locator('table.tickets').wait_for()
                watch.check({('GET', '/api/v1/auth/session', 401)})          # the session read before the sign-in
            finally:
                browser.close()
    finally:
        stop()


def test_an_account_is_shown_in_full_only_with_a_reason_and_the_audit_file_downloads(settings, store, monkeypatch):
    """An account's detail: its address and phone masked; Show asks why (refused without), then puts the value in place
    and writes one audit row with the field and the reason. The audit view lists it and Download CSV saves the file (the
    page's blob path under its policy)."""
    need_build()
    playwright = pytest.importorskip('playwright.sync_api')
    from test_screener import serve
    monkeypatch.setattr(main, 'ADMIN_APP', DIST)
    beta = dataclasses.replace(settings, mfa_key=KEY)
    local, stop = serve(beta, store)
    try:
        alice = make_user(store, 'alice_shown', 'alice-password', email='alice.shown@example.com')
        db(store, "UPDATE edge_bff.users SET phone_e164 = '+6281234567890' WHERE user_id = %s", alice['user_id'])
        asker = type('P', (), {'user_id': alice['user_id'], 'plan_key': 'free'})()
        for subject in ('First question', 'Second question'):          # two tickets: her usage in the list
            SupportStore(store, settings).create(asker, 'question', subject, 'How do I read this?', {'page': '/terminal'}, [])
        uid = seed_id(store, beta)
        nonce = enrol(store, uid)
        with playwright.sync_playwright() as pw:
            browser = open_browser(pw)
            try:
                page = sign_in_page(browser, local, '/admin', 'owner', 'local-test-password')
                watch = Watch(page)
                f = frame_of(page)
                f.locator('#code').fill(code_of(uid, nonce))
                f.get_by_role('button', name='Open the admin page').click()
                f.locator('#tab-accounts').click()
                # CONTRACT 10's usage counters in the list (the checker's page-tests-records-6): a column over its
                # numbers, each account's total, each kind named in the cell's title
                row = f.locator('table.accounts tbody tr').filter(has=f.locator('.linklike', has_text='alice_shown'))
                row.wait_for()
                heads = f.locator('table.accounts thead th').all_inner_texts()
                usage = row.locator('td.usage')
                assert 'Usage' in heads and heads.index('Usage') == row.locator('td').evaluate_all(
                    'cells => cells.findIndex(c => c.classList.contains("usage"))')
                assert usage.inner_text() == '2' and usage.get_attribute('title') == '2 support tickets'
                f.locator('table.accounts .linklike', has_text='alice_shown').click()
                f.locator('#account-name', has_text='alice_shown').wait_for()
                email_row = f.locator('.account .kv').filter(has=f.get_by_text('Email', exact=True))
                assert 'alice.shown@example.com' not in f.locator('.account').inner_text()
                assert 'a***@example.com' in email_row.inner_text()
                email_row.get_by_role('button', name='Show').click()
                box = f.get_by_role('dialog')
                box.get_by_role('button', name='Show').click()
                box.locator('#reason-error').filter(has_text='Write why').wait_for()
                box.get_by_label('Why you need it').fill('She asked to change her address')
                box.get_by_role('button', name='Show').click()
                email_row.filter(has_text='alice.shown@example.com').wait_for()
                assert email_row.get_by_role('button', name='Show').count() == 0
                phone = f.locator('.account .kv').filter(has=f.get_by_text('Phone', exact=True)).inner_text()
                assert '+62' in phone and '1234567' not in phone                               # still masked
                trail = db(store, "SELECT action, target_user_id, after, reason FROM edge_bff.admin_audit")
                assert trail == [{'action': 'account.reveal', 'target_user_id': alice['user_id'], 'after': {'field': 'email'},
                                  'reason': 'She asked to change her address'}]
                f.locator('#tab-audit').click()
                f.locator('table.audit td', has_text='account.reveal').wait_for()
                with page.expect_download() as got:
                    f.get_by_role('button', name='Download CSV').click()
                saved = got.value
                assert re.fullmatch(r'edge-audit-\d{4}-\d{2}-\d{2}\.csv', saved.suggested_filename)
                text = Path(saved.path()).read_text()
                assert text.startswith('audit_id,at,action') and 'account.reveal' in text and 'She asked' in text
                watch.check()
            finally:
                browser.close()
    finally:
        stop()


def sign_in_page(browser, local, path, login, password, width=1440, height=900):
    """The page signed in at `path`, with page.watch (Watch) attached before it opens (the checker's
    page-tests-records-5: every browser test here fails on an error or an answer it does not name)."""
    page = browser.new_page(viewport={'width': width, 'height': height})
    page.watch = Watch(page)
    page.goto(local.origin + path)
    page.locator('#auth-login').fill(login)
    page.locator('#auth-password').fill(password)
    page.get_by_role('button', name='Sign In', exact=True).click()
    page.wait_for_function("() => window.Edge && Edge.auth !== null")
    return page


def test_a_sign_in_stays_at_a_page_the_account_opens_and_lands_as_before_elsewhere(settings, store):
    """The rule beyond the admin page (switch on, the beta's way later): a paid account signing in at /backtest stays
    there (it holds backtest.view), at /admin it lands on its landing page, the Terminal (no admin.access), never on the
    closed admin page; at /login it lands as before."""
    playwright = pytest.importorskip('playwright.sync_api')
    from test_screener import serve
    local, stop = serve(beta_on(settings), store)
    try:
        paula = paid_user(store, 'paula_sign_in')
        with playwright.sync_playwright() as pw:
            browser = open_browser(pw)
            try:
                for path, lands in (('/backtest?run=bt_1', '/backtest?run=bt_1'), ('/admin?ticket=5', '/terminal'), ('/login', '/terminal')):
                    page = sign_in_page(browser, local, path, paula['username'], 'paula_sign_in-password')
                    page.wait_for_function('want => location.pathname + location.search === want', arg=lands)
                    assert page.locator('.admin-closed').count() == 0 and page.locator('.side-admin').count() == 0
                    page.watch.check(expected={('GET', '/api/v1/auth/session', 401)})
                    page.close()
            finally:
                browser.close()
    finally:
        stop()


def test_a_sign_in_through_the_authenticator_code_keeps_the_page_it_was_shown_at(settings, store):
    """The Phase 4 checker's page-tests-records-2: the admin needs the authenticator code at sign-in (switch on), which
    goes through /mfa; the page it was shown at, its address and query, is kept (authFlow.from) and reached after the
    code, as the user's "A" says for every tab; a sign-in at /login still lands on the landing page."""
    playwright = pytest.importorskip('playwright.sync_api')
    from app import mfa
    from test_screener import serve
    local, stop = serve(beta_on(settings), store)
    try:
        uid = seed_id(store, settings)
        nonce = enrol(store, uid)
        with playwright.sync_playwright() as pw:
            browser = open_browser(pw)
            try:
                cases = (('/backtest?run=bt_1', '/backtest?run=bt_1'), ('/admin?ticket=5', '/admin?ticket=5'),
                         ('/login', '/monitor'))
                for step, (path, lands) in enumerate(cases):
                    page = browser.new_page(viewport={'width': 1440, 'height': 900})
                    watch = Watch(page)
                    page.goto(local.origin + path)
                    page.locator('#auth-login').fill('owner')
                    page.locator('#auth-password').fill('local-test-password')
                    page.get_by_role('button', name='Sign In', exact=True).click()
                    page.locator('#auth-code').fill(code_of(uid, nonce, mfa.step_now() - 1 + step))
                    page.locator('#auth-code').press('Enter')
                    page.wait_for_function('want => location.pathname + location.search === want', arg=lands)
                    watch.check(expected={('GET', '/api/v1/auth/session', 401), ('POST', '/api/v1/auth/sign-in', 403)})
                    page.close()
            finally:
                browser.close()
    finally:
        stop()


def test_the_code_step_says_why_it_cannot_run(settings, store, monkeypatch):
    """Without the live site's key the page says to ask the operator; without an authenticator set up, to set it up on
    the live site first; neither shows the code field."""
    need_build()
    playwright = pytest.importorskip('playwright.sync_api')
    from test_screener import serve
    monkeypatch.setattr(main, 'ADMIN_APP', DIST)
    for beta, words in ((settings, 'cannot be checked here yet'), (dataclasses.replace(settings, mfa_key=KEY),
                                                                   'Set up your authenticator on the live site first')):
        local, stop = serve(beta, store)
        try:
            with playwright.sync_playwright() as pw:
                browser = open_browser(pw)
                try:
                    page = sign_in_page(browser, local, '/admin', 'owner', 'local-test-password')
                    f = frame_of(page)
                    f.locator('#step-title', has_text=words).wait_for()
                    assert f.locator('#code').count() == 0
                    page.watch.check(expected={('GET', '/api/v1/auth/session', 401)})
                finally:
                    browser.close()
        finally:
            stop()


def test_the_account_view_runs_each_action_it_offers_and_says_why_of_the_others(settings, store, monkeypatch):
    """Slice 5 in the page: an account's Actions as its answer opens them. Disable (a reason first), change the plan with
    an end (a past end refused under its field), sign out everywhere, enable again; an account still registering offers
    Resend code and says why the rest are closed; the admin's own account offers nothing and says why."""
    need_build()
    playwright = pytest.importorskip('playwright.sync_api')
    from datetime import date, timedelta
    from test_screener import serve
    monkeypatch.setattr(main, 'ADMIN_APP', DIST)
    beta = dataclasses.replace(settings, mfa_key=KEY, code_secret='c' * 40)
    local, stop = serve(beta, store)
    try:
        alice = make_user(store, 'alice_acts', 'alice-password', email='alice.acts@example.com')
        pat = make_user(store, 'pat_acts', 'pat-password', status='pending', email='pat.acts@example.com')
        uid = seed_id(store, beta)
        nonce = enrol(store, uid)
        with playwright.sync_playwright() as pw:
            browser = open_browser(pw)
            try:
                page = sign_in_page(browser, local, '/admin', 'owner', 'local-test-password')
                watch = Watch(page)
                f = frame_of(page)
                f.locator('#code').fill(code_of(uid, nonce))
                f.get_by_role('button', name='Open the admin page').click()

                def open_account(name):
                    f.locator('#tab-accounts').click()
                    f.locator('#tab-accounts').click()                              # the shown tab: back to the list
                    f.locator('table.accounts .linklike', has_text=name).click()
                    f.locator('#account-name', has_text=name).wait_for()

                def act(button, reason, **fields):
                    f.locator('.acts').get_by_role('button', name=button).click()
                    box = f.get_by_role('dialog')
                    for name, value in fields.items():                          # the dialog's own fields, by their ids
                        control = box.locator(f'#field-{name}')
                        control.select_option(value) if name == 'plan_key' else control.fill(value)
                    box.get_by_label('Why', exact=True).fill(reason)
                    return box

                open_account('alice_acts')
                f.locator('.acts').get_by_role('button', name='Disable account').click()
                box = f.get_by_role('dialog')
                box.get_by_role('button', name='Disable account').click()
                box.locator('#reason-error').filter(has_text='Write why').wait_for()        # a reason first, nothing sent
                box.get_by_label('Why', exact=True).fill('Asked to pause it')
                box.get_by_role('button', name='Disable account').click()
                f.locator('.account .pill', has_text='disabled').wait_for()
                assert f.locator('.acts').get_by_role('button', name='Enable account').count() == 1
                # a plan with an end in the past: the server's reason under Ends, the dialog stays open
                past, later = (date.today() - timedelta(days=2)).isoformat(), (date.today() + timedelta(days=30)).isoformat()
                box = act('Change plan', 'Paid by transfer', plan_key='paid', expires_at=past)
                box.get_by_role('button', name='Change plan').click()
                box.locator('#expires_at-error').filter(has_text='A day after today').wait_for()
                box.locator('#field-expires_at').fill(later)
                box.get_by_role('button', name='Change plan').click()
                f.locator('.account .kv', has_text='Plan').filter(has_text='paid').first.wait_for()
                box = act('Sign out everywhere', 'Lost her phone')
                box.get_by_role('button', name='Sign out everywhere').click()
                f.locator('.acts').get_by_role('button', name='Enable account').wait_for()
                box = act('Enable account', 'Back from the pause')
                box.get_by_role('button', name='Enable account').click()
                f.locator('.account .pill', has_text='active').wait_for()
                assert db(store, 'SELECT status FROM edge_bff.users WHERE user_id = %s', alice['user_id'])[0]['status'] == 'active'
                assert [(r['plan_key'], r['status']) for r in db(store, '''SELECT plan_key, status FROM edge_bff.subscriptions
                    WHERE user_id = %s''', alice['user_id'])] == [('paid', 'active')]
                trail = [r['action'] for r in db(store, 'SELECT action FROM edge_bff.admin_audit WHERE target_user_id = %s '
                                                         'ORDER BY audit_id', alice['user_id'])]
                assert trail == ['account.status', 'account.plan', 'account.sessions_revoke', 'account.status']
                # still registering: Resend code, and the why of the closed ones
                open_account('pat_acts')
                acts = f.locator('.acts')
                assert acts.get_by_role('button').all_inner_texts() == ['Resend code']
                assert 'still registering' in acts.inner_text()
                box = act('Resend code', 'She lost the email')
                box.get_by_role('button', name='Send code').click()
                f.locator('#toast', has_text='A new code was sent').wait_for()
                assert db(store, "SELECT count(*) AS n FROM edge_bff.email_codes WHERE user_id = %s AND purpose = 'register'",
                          pat['user_id'])[0]['n'] == 1
                # the admin's own account: nothing offered, and why
                open_account('owner')
                assert f.locator('.acts').get_by_role('button').count() == 0
                assert 'your own account' in f.locator('.acts').inner_text()
                watch.check({('POST', f"/api/v1/admin/users/{alice['user_id']}/plan", 400)})
            finally:
                browser.close()
    finally:
        stop()
