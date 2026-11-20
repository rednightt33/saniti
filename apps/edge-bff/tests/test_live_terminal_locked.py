"""The live checker after the switch-on (2026-11-20, ERRORS M515 F1; TEMPORARY until 3e builds a lock prompt on each
panel): a visitor's Terminal on the live site never shows data that is closed to it as if it were empty. /bundle answers
broker, events and intraday as {locked, capability} for the guest plan and cuts the price to its history window; the
page (terminal/src/main.ts lockedPage, historyNote; data/live.ts bundle) then leaves out the Flow Timeline, the broker
panel and the Events menu (as for a bond), says the history window on the chart, and a locked intraday timeframe opens
the lock box instead of "No 1H data is published". The test fails on "Rp 0", "No broker data", "No flow matches", an
event count or "is published". Needs EDGE_TEST_POSTGRES_URL, Playwright with EDGE_TEST_CHROMIUM and the built Terminal
page (cd apps/edge-bff/terminal && npm run build)."""
import dataclasses

import pytest

playwright = pytest.importorskip('playwright.sync_api')

from e2e_people import CHROMIUM, ROOT, Live, browser_context  # noqa: E402

MISLEADING = ('Rp 0', 'No broker data', 'No flow matches', 'is published', 'Dividend 0')


@pytest.fixture
def live_site(settings, store, monkeypatch):
    if not (ROOT / 'static' / 'terminal-app' / 'index.html').is_file():
        pytest.skip('the Terminal page is not built (cd apps/edge-bff/terminal && npm run build)')
    on = Live(dataclasses.replace(settings, site='live', guests_enabled=True, prelaunch_enabled=True, orc_url='',
                                  orc_key=''), store, monkeypatch)
    on.terminal.apply_header = True
    try:
        yield on
    finally:
        on.close()


def terminal_frame(page):
    page.wait_for_function("() => [...document.querySelectorAll('iframe')].some(f => f.contentDocument && "
                           "f.contentDocument.querySelector('#chart canvas'))", timeout=30000)
    return next(f for f in page.frames if f.url and '/terminal-app/' in f.url)


def visible_text(frame):
    return frame.evaluate("() => document.body.innerText")


def test_a_visitor_sees_no_closed_data_as_empty_and_reads_the_history_window(live_site):
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROMIUM, headless=True, args=live_site.terminal.browser_args())
        try:
            page = browser_context(browser).new_page()
            page.goto(live_site.origin + '/terminal')
            frame = terminal_frame(page)
            frame.wait_for_timeout(1500)
            text = visible_text(frame)
            assert not [w for w in MISLEADING if w in text], text[:2000]
            # the broker panels and the Events menu are left out, as for a bond
            assert frame.evaluate("() => document.body.classList.contains('locked-broker') "
                                  "&& document.body.classList.contains('locked-events')")
            for sel in ('.main-col > .bottom', '.side.right', '#evBtn'):
                assert not frame.locator(sel).first.is_visible(), sel
            # the history window the server cut the price to is said on the chart
            note = frame.locator('.history-note')
            assert note.is_visible() and 'Last 730 days of history' in note.inner_text()
        finally:
            browser.close()


def test_a_locked_intraday_timeframe_opens_the_lock_box_not_a_not_published_note(live_site):
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROMIUM, headless=True, args=live_site.terminal.browser_args())
        try:
            page = browser_context(browser).new_page()
            page.goto(live_site.origin + '/terminal')
            frame = terminal_frame(page)
            frame.evaluate("() => localStorage.setItem('ml.tf', '1h')")      # the visitor chose 1H
            page.reload()
            frame = terminal_frame(page)
            dialog = page.get_by_role('dialog')
            dialog.wait_for(timeout=15000)                                 # the shell's lock box (sign in)
            assert 'Sign in' in dialog.inner_text()
            assert 'is published' not in visible_text(frame)
            assert frame.evaluate("() => localStorage.getItem('ml.tf')") == 'D'   # the next load is daily
        finally:
            browser.close()
