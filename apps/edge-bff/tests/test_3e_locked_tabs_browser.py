"""3e (CONTRACT.md 8b "The rail and the frames"; EXEC option A, the next execution, item 3), in a real browser with
EDGE_MULTIUSER on (harness: tests/e2e_people.py, the fixtures of tests/test_guest_browser.py):

- every tab of the site stays in the rail, a visitor's too (the owner pages were hidden from a visitor);
- a tab the principal cannot open shows LockedTabPage in place of its app, the rail kept: a visitor is asked to sign in
  (or to create an account while registration is open), a free account is told the tab is not in its plan, with
  "Coming soon" and the upgrade contact; no frame of the tab's app is loaded, so none of its data routes is asked;
- the Terminal, which both hold, opens as before.

Needs EDGE_TEST_POSTGRES_URL, Playwright with EDGE_TEST_CHROMIUM and the built Terminal page."""
import dataclasses

import pytest

playwright = pytest.importorskip('playwright.sync_api')

from e2e_people import (CHROMIUM, ROOT, Live, browser_context, register, shell_navigate, sign_in,  # noqa: E402
                        terminal_drawn)
from test_guest_browser import CONTACT, chromium, live  # noqa: E402,F401
from test_principal import make_user  # noqa: E402

TABS = ('Overview', 'Watchlist', 'Terminal', 'Backtest', 'Screener', 'Radar')


def rail(page):
    """The names of the rail's buttons (icons only on a wide screen: the name is the button's aria-label)."""
    page.locator('nav.side-nav').first.wait_for(timeout=15000)
    return ' | '.join(page.locator('nav.side-nav button, nav.side-nav a').evaluate_all(
        'ns => ns.map(n => n.getAttribute("aria-label") || n.innerText || "")'))


def locked_tab(page, tab, seconds=15):
    card = page.locator(f'main.locked-tab[data-locked-tab="{tab}"] .locked-tab-card')
    card.wait_for(timeout=seconds * 1000)
    return card


def test_a_visitor_sees_every_tab_and_a_tab_it_cannot_open_asks_to_sign_in(live, chromium):
    page = browser_context(chromium).new_page()
    page.goto(live.origin + '/terminal')
    drawn, text = terminal_drawn(page)
    assert drawn, f'the guest Terminal did not draw: {text[:300]}'
    words = rail(page)
    assert all(tab in words for tab in TABS), words
    for path, tab, name in (('/backtest', 'backtest', 'Backtest'), ('/radar', 'radar', 'Radar')):
        shell_navigate(page, path)
        card = locked_tab(page, tab)
        assert f'Sign in to open {name}' in card.inner_text(), card.inner_text()
        assert card.get_by_role('button', name='Create account').count() == 1        # registration is open here
        assert page.locator('iframe.terminal-frame').count() == 0                     # no app, no data route asked
        assert all(t in rail(page) for t in TABS)                                      # the rail is kept
    card.get_by_role('button', name='Open the Terminal').click()
    page.wait_for_function("() => location.pathname === '/terminal'")
    shell_navigate(page, '/screener')
    locked_tab(page, 'screener').get_by_role('button', name='Sign in').click()
    page.wait_for_function("() => location.pathname === '/login'")


def test_a_free_account_is_told_a_tab_is_not_in_its_plan_and_keeps_its_terminal(live, chromium):
    page = browser_context(chromium).new_page()
    register(page, live, 'free_tabs', 'free.tabs@example.com')
    shell_navigate(page, '/watchlist')
    card = locked_tab(page, 'watchlist')
    words = card.inner_text()
    assert 'Watchlist is not in your plan' in words and 'Coming soon' in words and CONTACT in words, words
    assert card.get_by_role('button', name='Sign in').count() == 0
    assert page.locator('iframe.terminal-frame').count() == 0
    card.get_by_role('button', name='Open the Terminal').click()
    page.wait_for_function("() => location.pathname === '/terminal'")
    drawn, text = terminal_drawn(page)
    assert drawn, f'the free plan\'s Terminal did not draw: {text[:300]}'


def test_a_plan_raised_meanwhile_opens_the_tab_without_a_reload(live, chromium):
    """The locked-tab page decides from the access the shell holds and asks the server nothing, so it reads the session
    again when it shows (Edge.refresh): a plan raised meanwhile (here the subscription row, as Phase 4's admin page
    will) opens the tab at the next visit, without a reload."""
    page = browser_context(chromium).new_page()
    register(page, live, 'raised_user', 'raised@example.com')
    shell_navigate(page, '/backtest')
    locked_tab(page, 'backtest')
    live.subscribe('raised_user', 'paid')
    shell_navigate(page, '/terminal')
    shell_navigate(page, '/backtest')
    page.locator('iframe.terminal-frame[src$="/backtest-app/"]').wait_for(timeout=15000)
    assert page.locator('main.locked-tab').count() == 0


@pytest.fixture
def live_prelaunch(settings, store, monkeypatch):
    """The live site as it runs now: EDGE_SITE=live, the pre-launch mode, visitors on the Terminal, no assistant."""
    if not (ROOT / 'static' / 'terminal-app' / 'index.html').is_file():
        pytest.skip('the Terminal page is not built (cd apps/edge-bff/terminal && npm run build)')
    on = Live(dataclasses.replace(settings, site='live', guests_enabled=True, prelaunch_enabled=True, orc_url='',
                                  orc_key='', upgrade_contact=CONTACT), store, monkeypatch)
    on.terminal.apply_header = True
    try:
        yield on
    finally:
        on.close()


def test_on_the_live_site_the_rail_has_no_monitor_and_a_test_account_meets_the_locked_tab(live_prelaunch, store):
    """The live site (the advisor's review of 3e, 2026-11-20): a visitor's rail has every tab but the Monitor; a tab it
    cannot open asks it to sign in, without "Create account" while registration is closed; a test account, the only
    kind besides the admin that signs in during the pre-launch mode, gets the plan's words on a tab of the paid plan."""
    tess = make_user(store, 'tess_live', 'a long enough password')
    with store.connect() as c:
        c.execute("""INSERT INTO edge_bff.admin_audit(action, target_user_id, after, reason)
            VALUES ('account.test_mark', %s, '{"test_account": true}', 'test: the pre-launch test account')""", (tess['user_id'],))
        c.execute('UPDATE edge_bff.users SET test_account = true WHERE user_id = %s', (tess['user_id'],))
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROMIUM, headless=True, args=live_prelaunch.terminal.browser_args())
        try:
            page = browser_context(browser).new_page()
            page.goto(live_prelaunch.origin + '/terminal')
            drawn, text = terminal_drawn(page)
            assert drawn, f'the guest Terminal did not draw: {text[:300]}'
            words = rail(page)
            assert 'Monitor' not in words and all(tab in words for tab in TABS), words
            shell_navigate(page, '/overview')
            card = locked_tab(page, 'overview')
            assert 'Sign in to open Overview' in card.inner_text() or 'Sign in to open Market Overview' in card.inner_text(), card.inner_text()
            assert card.get_by_role('button', name='Create account').count() == 0           # registration is closed
            sign_in(page, live_prelaunch, 'tess_live', 'a long enough password')
            drawn, text = terminal_drawn(page)                 # the account's landing: its Terminal, signed in
            assert drawn, f'the test account\'s Terminal did not draw: {text[:300]}'
            shell_navigate(page, '/screener')
            card = locked_tab(page, 'screener')
            card.get_by_text('Screener is not in your plan').wait_for(timeout=15000)
            assert CONTACT in card.inner_text() and card.get_by_role('button', name='Sign in').count() == 0, card.inner_text()
            assert 'Monitor' not in rail(page)
        finally:
            browser.close()
