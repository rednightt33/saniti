"""3e (CONTRACT.md 8b "The rail and the frames"; EXEC option A, the next execution, item 3), in a real browser with
EDGE_MULTIUSER on (harness: tests/e2e_people.py, the fixtures of tests/test_guest_browser.py):

- every tab of the site stays in the rail, a visitor's too (the owner pages were hidden from a visitor);
- a tab the principal cannot open shows LockedTabPage in place of its app, the rail kept: a visitor is asked to sign in
  (or to create an account while registration is open), a free account is told the tab is not in its plan, with
  "Coming soon" and the upgrade contact; no frame of the tab's app is loaded, so none of its data routes is asked;
- the Terminal, which both hold, opens as before.

Needs EDGE_TEST_POSTGRES_URL, Playwright with EDGE_TEST_CHROMIUM and the built Terminal page."""
import pytest

pytest.importorskip('playwright.sync_api')

from e2e_people import browser_context, register, shell_navigate, terminal_drawn  # noqa: E402
from test_guest_browser import CONTACT, chromium, live  # noqa: E402,F401

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
