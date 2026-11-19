"""EXEC-MU-ACCOUNTS 3c check, lens guest (checker c3c-guest): failing tests of the verified findings about the guest
Terminal in a real browser with EDGE_MULTIUSER on (harness tests/e2e_people.py; verification/edge_multiuser/fix_round/
guest.md).

- A visitor's Terminal runs on the browser state of the account whose session ended there without a sign-out, and
  what the visitor changes is uploaded into that account at its next sign-in (shared/edge-session.ts: a visitor
  "holds nothing of the browser's storage: no last-login mark, nothing cleared", while the Terminal writes its `user`
  keys for the visitor all the same).
- An indicator the plan no longer holds stays drawn: the lock (live.ts lockRules) gates the menu's Add only, the
  indicators restored from storage (indicators.ts, ml.ind.v1) are drawn whatever the catalog now says.
- A visitor at its per-visitor quota is told to "upgrade the plan": the refusal words assume an account.

Needs EDGE_TEST_POSTGRES_URL, Playwright with EDGE_TEST_CHROMIUM and the built Terminal page."""
import dataclasses
import json
import time

import pytest

playwright = pytest.importorskip('playwright.sync_api')

from e2e_people import (CHROMIUM, PASSWORD, ROOT, Live, browser_context, db, register, shell_navigate,  # noqa: E402
                        sign_in, signed_in_workspace, terminal_drawn)


@pytest.fixture
def live(settings, store, monkeypatch):
    on = Live(dataclasses.replace(settings, guests_enabled=True), store, monkeypatch)
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


def test_a_visitors_choice_never_joins_the_account_whose_session_ended_on_this_browser(live, chromium):
    page = browser_context(chromium).new_page()
    register(page, live, 'ana_free', 'anaf@example.com')
    shell_navigate(page, '/terminal')
    drawn, text = terminal_drawn(page)
    assert drawn, text[:300]
    owner = db(live.store, "SELECT owner_key FROM edge_bff.users WHERE username = 'ana_free'")[0]['owner_key']
    # the account's session ends without a sign-out (idle 8 h, the 24 h lifetime, a sign-out everywhere elsewhere)
    db(live.store, 'UPDATE edge_bff.sessions SET revoked_at = now() WHERE revoked_at IS NULL')
    # another person at this browser opens the Terminal as a visitor and stars an indicator
    page.goto(live.origin + '/terminal')
    drawn, text = terminal_drawn(page)
    assert drawn, text[:300]
    frame = page.frame_locator('iframe.terminal-frame')
    frame.locator('#indBtn').click()
    star = frame.locator('.im-row[data-id="I05"] .im-star')
    star.wait_for(timeout=10000)
    star.click()
    time.sleep(1)
    # the account signs in again on this browser
    sign_in(page, live, 'ana_free', PASSWORD)
    signed_in_workspace(page)
    time.sleep(3)
    prefs = db(live.store, 'SELECT pref_key, value FROM edge_bff.user_preferences WHERE owner_key = %s', owner)
    assert not [p for p in prefs if p['pref_key'] == 'ml.ind.favs' and 'I05' in json.dumps(p['value'])], \
        f"a visitor's choice was uploaded into the account: {prefs}"


def test_an_indicator_the_guest_plan_no_longer_holds_is_not_drawn(live, chromium):
    """The guest plan (catalog data) grants I01; a visitor adds it; the catalog takes it back: the next load must not
    draw it (the menu already shows it locked)."""
    def guest_indicators(ids):
        db(live.store, '''UPDATE edge_bff.plan_capabilities SET value = %s::jsonb
            WHERE plan_key = (SELECT plan_key FROM edge_bff.plans WHERE for_guests)
              AND capability_key = 'terminal.indicator' ''', json.dumps({'ids': ids}))
    guest_indicators(['I01'])
    try:
        page = browser_context(chromium).new_page()
        page.goto(live.origin + '/terminal')
        drawn, text = terminal_drawn(page)
        assert drawn, text[:300]
        frame = page.frame_locator('iframe.terminal-frame')
        frame.locator('#indBtn').click()
        row = frame.locator('.im-row[data-id="I01"]')
        row.wait_for(timeout=10000)
        row.locator('.im-add').click()
        time.sleep(1)
        page.keyboard.press('Escape')
        assert 'SMA' in frame.locator('.chart-legend').inner_text()
        guest_indicators([])
        page.reload()
        drawn, text = terminal_drawn(page)
        assert drawn, text[:300]
        time.sleep(1)
        frame.locator('#indBtn').click()
        locked = frame.locator('.im-row.locked[data-id="I01"]')
        locked.wait_for(timeout=10000)                       # the menu says the plan does not hold it
        assert 'SMA' not in frame.locator('.chart-legend').inner_text(), \
            'an indicator the plan no longer holds is still drawn'
    finally:
        guest_indicators([])


def test_a_visitor_at_its_quota_is_not_told_to_upgrade_a_plan(live, chromium):
    """terminal-api's per-visitor quota refusal (429 quota_exceeded) as edge-bff relays it to a visitor: a visitor has
    no plan to upgrade; the way on is to wait or to sign in."""
    live.terminal.refuse['bundle'] = (429, {'error': 'quota_exceeded', 'quota': 'files_per_hour', 'limit': 60,
                                            'window': 'hour', 'retry_after_s': 1200, 'message': 'quota'})
    page = browser_context(chromium).new_page()
    page.goto(live.origin + '/terminal')
    terminal_drawn(page, seconds=12)
    text = page.frame_locator('iframe.terminal-frame').locator('body').inner_text()
    said = [line for line in text.split('\n') if 'limit' in line.lower()]
    assert said, text[:300]
    assert not [line for line in said if 'upgrade the plan' in line.lower() or 'your plan' in line.lower()], said
