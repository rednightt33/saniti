"""EXEC-MU-ACCOUNTS 3e, the example mode as the user set it on 2026-11-21 (ERRORS M527; app/examples.py, static/edge-app.js
ExampleTabPage, shared/example-view.ts), in a real browser with EDGE_MULTIUSER on and visitors (tests/e2e_people.py):

- a visitor opens the Radar tab and gets its example: the page in its frame with ?example=1, under the note naming the
  example's date, drawn from the example's files only (no live Radar route is asked);
- the page is a view of that day: a click on it opens the shell's sign-in box (a visitor) or the paywall (a free
  account), the page's own handlers never run, no title is left to show as a tooltip, and the page still scrolls;
- without the example (no rows, or the plan without radar.example) the locked page shows as before; a paid account opens
  the live Radar.

The example's files are made by the publisher's own Radar builders (apps/terminal-publisher/radar.py) from a few
made-up rows, so they have the shapes the page reads. Needs EDGE_TEST_POSTGRES_URL, Playwright with EDGE_TEST_CHROMIUM,
the built Terminal page and the built Radar page (cd apps/edge-bff/radar && npm run build)."""
import dataclasses
import re

import pytest

playwright = pytest.importorskip('playwright.sync_api')

from e2e_people import CHROMIUM, PASSWORD, ROOT, Live, browser_context, shell_navigate, sign_in, signed_in_workspace  # noqa: E402
from test_examples import put  # noqa: E402
from test_guest_browser import CONTACT  # noqa: E402
from test_principal import db, make_user  # noqa: E402

from example_docs import (RADAR_AS_OF as AS_OF, BACKTEST_AS_OF, OVERVIEW_DAYS, SCREENER_AS_OF,  # noqa: E402
                          WATCHLIST_AS_OF, backtest_example, overview_files, radar_example, screener_example,
                          watchlist_example)
from test_examples import gz, examples_module  # noqa: E402


@pytest.fixture
def site(settings, store, monkeypatch):
    """The live site with visitors (registration open, so a test account can be made), and the example stored."""
    if not (ROOT / 'radar' / 'dist' / 'index.html').is_file():
        pytest.skip('the Radar page is not built (cd apps/edge-bff/radar && npm run build)')
    on = Live(dataclasses.replace(settings, site='live', guests_enabled=True, prelaunch_enabled=False, orc_url='',
                                  orc_key='', upgrade_contact=CONTACT), store, monkeypatch)
    put(store, 'radar', radar_example(), as_of=AS_OF)
    put(store, 'watchlist', watchlist_example(), as_of=WATCHLIST_AS_OF)
    on.terminal.pages['overview'] = {n: gz(doc) for n, doc in overview_files().items()}     # the live publication
    try:
        yield on
    finally:
        on.close()
        db(store, 'DELETE FROM edge_bff.example_files')


@pytest.fixture
def chromium(site):
    if not (ROOT / 'static' / 'terminal-app' / 'index.html').is_file():
        pytest.skip('the Terminal page is not built (cd apps/edge-bff/terminal && npm run build)')
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROMIUM, headless=True, args=site.terminal.browser_args())
        try:
            yield browser
        finally:
            browser.close()


def open_example(page, path='/radar'):
    """The example page of the tab: its note and its frame drawn (the board's rows)."""
    if page.url.startswith('http'):
        shell_navigate(page, path)
    frame_el = page.locator('main.example-page[data-example-tab="radar"] iframe.terminal-frame')
    frame_el.wait_for(timeout=20000)
    assert frame_el.get_attribute('src').endswith('/radar-app/?example=1')
    frame = page.frame_locator('main.example-page iframe.terminal-frame')
    frame.locator('text=T000').first.wait_for(timeout=20000)
    return frame


def no_title_after_hover(page, frame):
    """3e: a native tooltip needs the pointer on its element and shows only after a delay; once the pointer is on the page,
    no title attribute and no SVG <title> is left in it (shared/example-view.ts sweeps them on every pointer entry, with
    no observer or timer: the Screener's bundle forbids both)."""
    box = page.locator('main.example-page iframe.terminal-frame').bounding_box()
    page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
    page.mouse.move(box['x'] + box['width'] / 3, box['y'] + box['height'] / 3)
    page.wait_for_timeout(100)
    assert frame.locator('[title], svg title').count() == 0


def asked(requests):
    return sorted({r.split('?')[0] for r in requests if '/api/v1/' in r})


def test_a_visitor_sees_the_radar_example_as_a_view_of_its_day(site, chromium):
    page = browser_context(chromium).new_page()
    page.set_viewport_size({'width': 1152, 'height': 640})
    requests = []
    page.on('request', lambda r: requests.append(r.url))
    page.goto(site.origin + '/radar')
    frame = open_example(page)
    note = page.locator('.example-bar').inner_text()
    assert 'Example' in note and 'Radar with the data of Fri 6 Nov 2026' in note and 'Sign in to use Radar itself' in note
    # the page's data came from the example's files only
    urls = asked(requests)
    assert [u for u in urls if '/api/v1/radar/' in u] == []
    files = {u.rsplit('/', 1)[1] for u in urls if '/api/v1/examples/radar/file/' in u}
    assert files == set(radar_example()), urls
    # no tooltip to show: no title attribute and no SVG <title> in the page
    no_title_after_hover(page, frame)
    # it scrolls: the wheel over the board's list moves the element that scrolls it (the page's own scroller)
    frame.locator('text=T000').first.hover()
    scrolled = """() => [...document.querySelectorAll('*')].filter(e => e.scrollHeight > e.clientHeight + 2
        && /(auto|scroll)/.test(getComputedStyle(e).overflowY)).map(e => e.scrollTop)
        .concat([document.scrollingElement.scrollTop])"""
    before = frame.locator('body').evaluate(scrolled)
    page.mouse.wheel(0, 600)
    page.wait_for_timeout(400)
    after = frame.locator('body').evaluate(scrolled)
    assert len(before) > 1 and sum(after) > sum(before), (before, after)
    # a click on the page asks to sign in, and the page's own handler did not run (the board stays the board)
    hash_before = frame.locator('body').evaluate('() => location.hash')
    frame.locator('button').first.click()
    box = page.locator('.locked-dialog')
    box.wait_for(timeout=10000)
    text = box.inner_text()
    assert 'Sign in to open Radar' in text and 'This is an example of Radar' in text, text
    assert box.get_by_role('button', name='Sign in').count() == 1
    assert frame.locator('body').evaluate('() => location.hash') == hash_before
    box.locator('.dialog-head button[aria-label="Close"]').click()
    box.wait_for(state='detached', timeout=10000)
    # Enter on a control asks too (after the layer's pause between two asks)
    page.wait_for_timeout(500)
    frame.locator('button').first.press('Enter')
    page.locator('.locked-dialog').wait_for(timeout=10000)
    assert frame.locator('body').evaluate('() => location.hash') == hash_before


def test_a_free_account_gets_the_paywall_and_a_paid_one_the_live_radar(site, chromium):
    make_user(site.store, 'freda_example', PASSWORD)
    page = browser_context(chromium).new_page()
    sign_in(page, site, 'freda_example', PASSWORD)
    signed_in_workspace(page)
    frame = open_example(page)
    note = page.locator('.example-bar').inner_text()
    assert 'Your plan does not include Radar itself yet' in note and CONTACT in note, note
    frame.locator('button').first.click()
    box = page.locator('.locked-dialog')
    box.wait_for(timeout=10000)
    assert 'Radar is not in your plan' in box.inner_text() and 'This is an example of Radar' in box.inner_text()
    site.subscribe('freda_example', 'paid')
    page.reload()
    signed_in_workspace(page) if page.url.endswith('/terminal') else None
    page.locator('iframe.terminal-frame[src$="/radar-app/"]').wait_for(timeout=20000)
    assert page.locator('.example-bar').count() == 0


def test_without_its_example_the_tab_is_locked_as_before(site, chromium, store):
    rows = db(store, "SELECT value FROM edge_bff.plan_capabilities WHERE plan_key = 'guest' AND capability_key = 'radar.example'")
    db(store, "DELETE FROM edge_bff.plan_capabilities WHERE plan_key = 'guest' AND capability_key = 'radar.example'")
    try:
        page = browser_context(chromium).new_page()
        page.goto(site.origin + '/radar')
        page.locator('main.locked-tab[data-locked-tab="radar"] .locked-tab-card').wait_for(timeout=20000)
        assert page.locator('iframe.terminal-frame').count() == 0
    finally:
        if rows:
            db(store, "INSERT INTO edge_bff.plan_capabilities(plan_key, capability_key, value) VALUES ('guest', 'radar.example', 'true')")
    db(store, 'DELETE FROM edge_bff.example_files')
    page = browser_context(chromium).new_page()
    page.goto(site.origin + '/radar')
    page.locator('main.locked-tab[data-locked-tab="radar"] .locked-tab-card').wait_for(timeout=20000)


# ---- the Market Overview: the latest market date, clickable but for its time controls (the user, 2026-11-21) ---------
def open_overview(page):
    frame_el = page.locator('main.example-page[data-example-tab="overview"] iframe.terminal-frame')
    frame_el.wait_for(timeout=20000)
    assert frame_el.get_attribute('src').endswith('/overview-app/?example=1')
    frame = page.frame_locator('main.example-page iframe.terminal-frame')
    frame.locator('body[data-ready="1"]').wait_for(timeout=20000)
    return frame


def box_text(page):
    box = page.locator('.locked-dialog')
    box.wait_for(timeout=10000)
    text = box.inner_text()
    box.locator('.dialog-head button[aria-label="Close"]').click()      # its own button: a key could land in the page's frame
    box.wait_for(state='detached', timeout=10000)
    page.wait_for_timeout(450)                                     # the layer's pause between two asks
    return text


def test_a_visitor_sees_the_latest_overview_and_only_its_time_controls_are_locked(site, chromium):
    if not (ROOT / 'overview' / 'dist' / 'index.html').is_file():
        pytest.skip('the Overview page is not built (cd apps/edge-bff/overview && npm run build)')
    page = browser_context(chromium).new_page()
    requests = []
    page.on('request', lambda r: requests.append(r.url))
    page.goto(site.origin + '/overview')
    frame = open_overview(page)
    assert 'Overview with the data of Fri 20 Nov 2026' in page.locator('.example-bar').inner_text()
    assert [u for u in requests if '/api/v1/overview/' in u] == []
    asked = {u.split('?')[0].rsplit('/', 1)[1] for u in requests if '/api/v1/examples/overview/file/' in u}
    assert asked == {'overview-meta', 'overview-series', f'overview-day-{OVERVIEW_DAYS[-1]}'}, asked
    # what is not time works: the EMA, the index and group filter
    frame.locator('#brpk button[data-k="EMA200"]').click()
    assert frame.locator('#brpk button[data-k="EMA200"]').get_attribute('aria-pressed') == 'true'
    frame.locator('#uni').click()
    frame.locator('#unipop .menu-item').filter(has_text='Big group').first.click()
    assert page.locator('.locked-dialog').count() == 0
    # every group of the page whose choices are all periods (read from the page, not listed here) asks to sign in on
    # each of its other choices, and keeps its own; every other group just works
    groups = frame.locator('.seg').evaluate_all('''gs => gs.map((g, n) => ({n, id: g.id, k: g.dataset.k || '',
        vals: [...g.querySelectorAll('button')].map(b => b.dataset.v || b.dataset.p || b.dataset.k || '')}))''')
    period = re.compile(r'\d+[DMY]|YTD|C')
    timed = [g for g in groups if g['vals'] and all(period.fullmatch(v) for v in g['vals'])]
    assert len(timed) >= 6, groups                              # the map, IHSG, sectors, breadth, movers, flow
    for g in timed:
        seg = frame.locator('.seg').nth(g['n'])
        before = seg.evaluate("g => [...g.querySelectorAll('button')].map(b => b.getAttribute('aria-pressed'))")
        others = [i for i, x in enumerate(before) if x != 'true']
        assert others, g
        for i in others:
            seg.locator('button').nth(i).click()
            assert 'Sign in to open Overview' in box_text(page), (g, i)
        after = frame.locator('.seg').nth(g['n']).evaluate("g => [...g.querySelectorAll('button')].map(b => b.getAttribute('aria-pressed'))")
        assert after == before, g
    for g in (g for g in groups if g not in timed):
        frame.locator('.seg').nth(g['n']).locator('button').last.click()
        page.wait_for_timeout(450)
        assert page.locator('.locked-dialog').count() == 0, g
    frame.locator('#datebtn').click()
    assert 'Sign in to open Overview' in box_text(page)
    assert frame.locator('.cpop').evaluate('n => n.hidden') and frame.locator('#datepop').evaluate('n => n.hidden')
    # a stock opens the Terminal, as on the live page
    frame.locator('.tmv-r').first.click()
    page.wait_for_function("() => location.pathname === '/terminal'", timeout=10000)


def test_a_free_account_meets_the_paywall_on_the_overviews_time_controls(site, chromium):
    if not (ROOT / 'overview' / 'dist' / 'index.html').is_file():
        pytest.skip('the Overview page is not built (cd apps/edge-bff/overview && npm run build)')
    make_user(site.store, 'freda_overview', PASSWORD)
    page = browser_context(chromium).new_page()
    sign_in(page, site, 'freda_overview', PASSWORD)
    signed_in_workspace(page)
    shell_navigate(page, '/overview')
    frame = open_overview(page)
    frame.locator('#spp button').first.click()
    assert 'Overview is not in your plan' in box_text(page)


# ---- the Watchlist: one example list on its date, a view of that day ---------------------------------------------------
def test_a_visitor_sees_the_watchlist_example_and_a_click_asks_to_sign_in(site, chromium):
    if not (ROOT / 'watchlist' / 'dist' / 'index.html').is_file():
        pytest.skip('the Watchlist page is not built (cd apps/edge-bff/watchlist && npm run build)')
    page = browser_context(chromium).new_page()
    requests = []
    page.on('request', lambda r: requests.append(r.url))
    page.goto(site.origin + '/watchlist')
    frame_el = page.locator('main.example-page[data-example-tab="watchlist"] iframe.terminal-frame')
    frame_el.wait_for(timeout=20000)
    assert frame_el.get_attribute('src').endswith('/watchlist-app/?example=1')
    frame = page.frame_locator('main.example-page iframe.terminal-frame')
    tickers = watchlist_example()['watchlist-stocks']['ticker']
    frame.locator(f'text={tickers[0]}').first.wait_for(timeout=20000)
    body = frame.locator('body').inner_text()
    assert 'LQ45' in body and all(t in body for t in tickers), body[:400]
    assert 'Watchlist with the data of Fri 13 Nov 2026' in page.locator('.example-bar').inner_text()
    # the page's data came from the example's files only: no account list, no live figures, no logo list
    urls = sorted({u.split('?')[0].replace(site.origin, '') for u in requests if '/api/' in u})
    assert [u for u in urls if not u.startswith(('/api/v1/examples/watchlist/', '/api/v1/auth/'))] == [], urls
    assert {u.rsplit('/', 1)[1] for u in urls if '/file/' in u} == {'watchlist-stocks', 'watchlist-lists'}
    frame.locator('button').first.click()
    box = page.locator('.locked-dialog')
    box.wait_for(timeout=10000)
    assert 'Sign in to open Watchlist' in box.inner_text() and 'This is an example of Watchlist' in box.inner_text()
    no_title_after_hover(page, frame)


@pytest.mark.parametrize('slow', [False, True], ids=['quick', 'slow'])
def test_a_visitor_sees_the_backtests_stored_run_and_a_click_asks_to_sign_in(site, chromium, store, monkeypatch, slow):
    """The Backtest's example: the page opens on the stored run of its own default setup (its request equals the stored
    one, the cards' ids aside, so the stored result is shown: the header's figures and the results view), reads only the
    example's files (no catalog, bars, job or Terminal route), shows no toast, no title, and a click asks to sign in.
    slow: every example answer comes half a second late, as on a visitor's network: the page draws on its provisional
    catalog first (its quick wait is 60 ms, backtest/src/app.ts QUICK_MS), and its run still waits for the example's
    catalog, so the request is the stored one and the same run shows."""
    if not (ROOT / 'backtest' / 'dist' / 'index.html').is_file():
        pytest.skip('the Backtest page is not built (cd apps/edge-bff/backtest && npm run build)')
    files = backtest_example()
    put(store, 'backtest', files, as_of=BACKTEST_AS_OF)
    if slow:
        import asyncio
        quick = examples_module.Stored.current

        async def late(self, p):
            if self.tab == 'backtest':
                await asyncio.sleep(0.5)
            return await quick(self, p)
        monkeypatch.setattr(examples_module.Stored, 'current', late)
    page = browser_context(chromium).new_page()
    page.set_viewport_size({'width': 1152, 'height': 640})
    requests, errors = [], []
    page.on('request', lambda r: requests.append(r.url))
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(site.origin + '/backtest')
    frame_el = page.locator('main.example-page[data-example-tab="backtest"] iframe.terminal-frame')
    frame_el.wait_for(timeout=20000)
    assert frame_el.get_attribute('src').endswith('/backtest-app/?example=1')
    frame = page.frame_locator('main.example-page iframe.terminal-frame')
    # the header's result line (hidden at this width) is written once the run is in: the stored run's figures
    head = frame.locator('#lastRun .xh-k')
    head.wait_for(state='attached', timeout=30000)
    trades = len(files['backtest-result']['trades'])
    assert 'Sharpe' in head.text_content() and f'{trades} trades' in head.text_content(), head.text_content()
    assert frame.locator('#vcRes').inner_text() == f'{trades} trades'
    assert frame.locator('#main.vres').count() == 1 and frame.locator('#eqChart canvas').count() > 0
    assert frame.locator('#ctxTicker').inner_text() == files['backtest-request']['single']['ticker']
    assert 'Backtest with the data of Fri 23 Oct 2026' in page.locator('.example-bar').inner_text()
    # the page's data came from the example's files only; nothing was refused or failed on the way
    urls = sorted({u.split('?')[0].replace(site.origin, '') for u in requests if '/api/' in u})
    assert [u for u in urls if not u.startswith(('/api/v1/examples/backtest/', '/api/v1/auth/'))] == [], urls
    assert {u.rsplit('/', 1)[1] for u in urls if '/file/' in u} == set(files), urls
    assert frame.locator('#toast').text_content() == '' and errors == [], (frame.locator('#toast').text_content(), errors)
    no_title_after_hover(page, frame)
    # a click on the page asks to sign in, and the page's own handler did not run (no second run, the results stay)
    frame.locator('.js-run').first.click()
    box = page.locator('.locked-dialog')
    box.wait_for(timeout=10000)
    assert 'Sign in to open Backtest' in box.inner_text() and 'This is an example of Backtest' in box.inner_text()
    assert frame.locator('#main.vres').count() == 1 and frame.locator('#toast').text_content() == ''
    assert sum('/file/backtest-request' in u for u in requests) == 1


def test_a_visitor_sees_the_screeners_stored_screen_and_its_results_and_the_browser_keeps_nothing(site, chromium, store):
    """The Screener's example: the page opens on the stored screen (the preset brk52, its two cards) with the stored run's
    results, reads only the example's files (no catalog, universe, run or watchlist route of the live page), keeps
    nothing in the browser's storage and shows nothing a visitor kept there (a last screen of their own), shows no
    toast and no title, and a click asks to sign in."""
    if not (ROOT / 'screener' / 'dist' / 'index.html').is_file():
        pytest.skip('the Screener page is not built (cd apps/edge-bff/screener && npm run build)')
    files = screener_example()
    put(store, 'screener', files, as_of=SCREENER_AS_OF)
    context = browser_context(chromium)
    page = context.new_page()
    page.set_viewport_size({'width': 1440, 'height': 900})
    requests, errors = [], []
    page.on('request', lambda r: requests.append(r.url))
    page.on('pageerror', lambda e: errors.append(str(e)))
    # a visitor's own last screen and panels from an earlier session on this browser: not shown, not changed
    mine = '{"name":"Visitor own screen","definition":{"universe":{"security_types":["stock"]},"conditions":[],"logic":"all"}}'
    page.goto(site.origin + '/favicon.svg')
    page.evaluate("""m => { localStorage.setItem('scr.last', m); localStorage.setItem('scr.panel', '{"preview":true}') }""", mine)
    page.goto(site.origin + '/screener')
    frame_el = page.locator('main.example-page[data-example-tab="screener"] iframe.terminal-frame')
    frame_el.wait_for(timeout=20000)
    assert frame_el.get_attribute('src').endswith('/screener-app/?example=1')
    frame = page.frame_locator('main.example-page iframe.terminal-frame')
    tickers = [r['ticker'] for r in files['screener-run']['rows']]
    assert tickers, 'the made-up run has matches to show'
    frame.locator(f'text={tickers[0]}').first.wait_for(timeout=30000)
    body = frame.locator('body').inner_text()
    assert all(t in body for t in tickers), body[:600]
    assert frame.locator('#titleIn').input_value() == files['screener-screen']['name'] and 'Visitor own screen' not in body
    assert 'Screener with the data of Tue 27 Oct 2026' in page.locator('.example-bar').inner_text()
    urls = sorted({u.split('?')[0].replace(site.origin, '') for u in requests if '/api/' in u})
    assert [u for u in urls if not u.startswith(('/api/v1/examples/screener/', '/api/v1/auth/'))] == [], urls
    assert {u.rsplit('/', 1)[1] for u in urls if '/file/' in u} == set(files), urls
    assert frame.locator('#toast').text_content() == '' and errors == [], (frame.locator('#toast').text_content(), errors)
    assert frame.locator('[title]').count() > 0                 # the page draws titles (its cells) ...
    no_title_after_hover(page, frame)                           # ... and none is left once the pointer is on it
    kept = page.evaluate("() => [localStorage.getItem('scr.last'), localStorage.getItem('scr.panel'), localStorage.getItem('scr.boot')]")
    assert kept == [mine, '{"preview":true}', None], kept
    frame.locator('button:visible:not([disabled]):not([aria-disabled="true"])').first.click()
    box = page.locator('.locked-dialog')
    box.wait_for(timeout=10000)
    assert 'Sign in to open Screener' in box.inner_text() and 'This is an example of Screener' in box.inner_text()
