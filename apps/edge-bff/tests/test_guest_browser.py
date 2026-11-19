"""EXEC-MU-ACCOUNTS fix round, track guest (verification/edge_multiuser/fix_round/guest.md), in a real browser with
EDGE_MULTIUSER on (harness: tests/e2e_people.py; terminal-api's answers come from its own code, apply_header):

- a visitor without an account opens the Terminal, sees BBCA drawn and the whole ticker list in the search, and a
  ticker the guest plan does not hold opens the sign-in box (sign in goes to the sign-in page);
- a free account gets the upgrade box instead ("Coming soon" and the upgrade contact);
- in the pre-launch mode the register page says registration opens soon, and the sign-in page offers the Terminal.

Needs EDGE_TEST_POSTGRES_URL, Playwright with EDGE_TEST_CHROMIUM and the built Terminal page."""
import dataclasses
import time

import pytest

playwright = pytest.importorskip('playwright.sync_api')

from e2e_people import CHROMIUM, ROOT, Live, browser_context, register, shell_navigate, terminal_drawn  # noqa: E402

CONTACT = 'sales@example.com'


@pytest.fixture
def live(settings, store, monkeypatch):
    on = Live(dataclasses.replace(settings, guests_enabled=True, upgrade_contact=CONTACT), store, monkeypatch)
    on.terminal.apply_header = True
    try:
        yield on
    finally:
        on.close()


@pytest.fixture
def chromium(live):
    if not (ROOT / 'static' / 'terminal-app' / 'index.html').is_file():
        pytest.skip('the Terminal page is not built (cd apps/edge-bff/terminal && npm run build)')
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROMIUM, headless=True, args=live.terminal.browser_args())
        try:
            yield browser
        finally:
            browser.close()


def search_and_choose(page, ticker):
    """The Terminal's search (its search button), the ticker typed and chosen with Enter; the rows it listed."""
    frame = page.frame_locator('iframe.terminal-frame')
    frame.locator('#symSearch').click()
    box = frame.locator('.gp-dialog input')
    box.fill(ticker)
    rows = frame.locator('.gp-row .gp-ticker').all_inner_texts()
    box.press('Enter')
    return rows


def locked_box(page, seconds=10):
    dialog = page.locator('.dialog.locked-dialog')
    dialog.wait_for(timeout=seconds * 1000)
    return dialog


def test_a_visitor_sees_bbca_and_every_ticker_and_another_ticker_asks_to_sign_in(live, chromium):
    page = browser_context(chromium).new_page()
    page.goto(live.origin + '/terminal')
    drawn, text = terminal_drawn(page)
    assert drawn, f'the guest Terminal did not draw: {text[:300]}'
    assert page.evaluate('() => location.pathname') == '/terminal' and page.evaluate('() => Edge.auth') is None
    frame = page.frame_locator('iframe.terminal-frame')
    assert frame.locator('#symText').inner_text() == 'BBCA'
    # the whole ticker list is searched; the tickers the guest plan does not hold carry the lock
    frame.locator('#symSearch').click()
    listed = frame.locator('.gp-row .gp-ticker').all_inner_texts()
    assert {'BBCA', 'BBRI'} <= {t.split()[0] for t in listed}, listed
    assert frame.locator('.gp-row:has-text("BBRI") .gp-lock').count() == 1
    assert frame.locator('.gp-row:has-text("BBCA") .gp-lock').count() == 0
    frame.locator('.gp-dialog input').press('Escape')
    search_and_choose(page, 'BBRI')
    dialog = locked_box(page)
    assert 'Sign in to open' in dialog.inner_text() and 'Bank Rakyat Indonesia' in dialog.inner_text()
    assert dialog.get_by_role('button', name='Create account').count() == 1       # registration is open here
    # the chart stays on BBCA (no other ticker's data was asked for)
    assert not [c for c in live.terminal.calls if 'BBRI' in c['body'] or '/BBRI' in c['path']]
    dialog.get_by_role('button', name='Sign in').click()
    page.wait_for_function("() => location.pathname === '/login'")
    # no call of the guest ever reached an account route (they answer 401: the page never asks them)
    assert page.evaluate('() => Edge.auth') is None


def test_a_free_account_gets_the_upgrade_box_with_the_contact(live, chromium):
    page = browser_context(chromium).new_page()
    register(page, live, 'free_user', 'free@example.com')
    shell_navigate(page, '/terminal')
    drawn, text = terminal_drawn(page)
    assert drawn, f'the free plan\'s Terminal did not draw: {text[:300]}'
    search_and_choose(page, 'TLKM')
    dialog = locked_box(page)
    words = dialog.inner_text()
    assert 'is not in your plan' in words and 'Coming soon' in words and CONTACT in words, words
    assert dialog.get_by_role('button', name='Sign in').count() == 0
    dialog.locator('.locked-actions').get_by_role('button', name='Close').click()
    assert page.locator('.dialog.locked-dialog').count() == 0


def test_an_indicator_the_plan_does_not_hold_opens_the_box(live, chromium):
    page = browser_context(chromium).new_page()
    page.goto(live.origin + '/terminal')
    drawn, text = terminal_drawn(page)
    assert drawn, text[:300]
    frame = page.frame_locator('iframe.terminal-frame')
    frame.locator('#indBtn').click()
    row = frame.locator('.im-row.locked').first
    row.wait_for(timeout=10000)
    assert row.locator('.im-lock').count() == 1
    row.locator('.im-add').click()
    assert 'Sign in to open' in locked_box(page).inner_text()


def test_prelaunch_shows_registration_closed_and_offers_the_terminal(settings, store, monkeypatch, chromium, live):
    pre = Live(dataclasses.replace(settings, guests_enabled=True, prelaunch_enabled=True), store, monkeypatch)
    try:
        page = browser_context(chromium).new_page()
        page.goto(pre.origin + '/login')
        page.get_by_role('link', name='Open the Terminal without an account').wait_for(timeout=10000)
        assert page.get_by_role('link', name='Create account').count() == 0
        page.goto(pre.origin + '/register')
        page.get_by_text('Registration opens soon').wait_for(timeout=10000)
        assert page.get_by_label('Username', exact=True).count() == 0
        time.sleep(0.2)
    finally:
        pre.close()
