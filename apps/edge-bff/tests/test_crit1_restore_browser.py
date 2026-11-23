"""3f round 2 CRIT-1 and its test-out (wf_c72ae04c-a73, terminal-shell round:CRIT-1 "partly"): the Terminal's restore of
its saved indicators (src/app/indicators.ts restore -> data/inputs.ts restoreList) parks an entry whose definition this
build lacks, at its place, and the list it saves keeps it. The preferences are shared by owner, not by site, so the live
site's public build must keep the admin's lab indicators for the beta's lab build.

The repository holds no lab indicator (an indicator may be lab since 2026-11-23, tests/test_releases.py LAB_KIND_HELD),
so no lab build here can draw a real one: the public Terminal gets a saved list with a stand-in id no build knows between
two it draws, as the lab build's list would reach it (the test-out of 2026-11-23 ran the same check with a planted I54 on
its public build); the round trip on the real sites is INDICATOR_BETA_TO_LIVE.md Part A step 12, at the first lab
indicator, and the saved list after the load (the restore's save, then a change, then a reload) must
still hold it at its place. That the lab build draws it again from that list is restoreList's unit test
(terminal/tests/data/inputs.test.ts). Needs EDGE_TEST_POSTGRES_URL, Playwright with EDGE_TEST_CHROMIUM and the built
Terminal page."""
import json

import pytest

pytest.importorskip('playwright.sync_api')

from e2e_people import browser_context, db, terminal_drawn  # noqa: E402
from test_c3c_guest_recheck_browser import chromium, live  # noqa: E402,F401 - the fixtures

LAB = {'def': 'I_LAB_STANDIN', 'params': {'k': 3}, 'on': True}


def saved_list(page):
    return json.loads(page.evaluate("() => localStorage.getItem('ml.ind.v1') || '[]'"))


def test_the_public_terminal_keeps_a_saved_indicator_its_build_lacks(live, chromium):
    def guest_indicators(ids):
        db(live.store, '''UPDATE edge_bff.plan_capabilities SET value = %s::jsonb
            WHERE plan_key = (SELECT plan_key FROM edge_bff.plans WHERE for_guests)
              AND capability_key = 'terminal.indicator' ''', json.dumps({'ids': ids}))
    guest_indicators(['I01', 'I02'])
    try:
        context = browser_context(chromium)
        page = context.new_page()
        page.goto(live.origin + '/login')                              # the origin, before the Terminal ever loads
        seeded = [{'def': 'sma', 'params': {}, 'on': True}, LAB, {'def': 'ema', 'params': {}, 'on': True}]   # I01, I02
        page.evaluate("v => localStorage.setItem('ml.ind.v1', v)", json.dumps(seeded))
        page.goto(live.origin + '/terminal')
        drawn, text = terminal_drawn(page)
        assert drawn, text[:300]
        after_load = saved_list(page)                                  # the restore's own save
        assert [o['def'] for o in after_load] == ['sma', 'I_LAB_STANDIN', 'ema'], after_load
        assert after_load[1] == LAB
        frame = page.frame_locator('iframe.terminal-frame')
        frame.locator('.chart-legend', has_text='SMA').wait_for(timeout=15000)
        legend = frame.locator('.chart-legend').inner_text()
        assert 'I_LAB_STANDIN' not in legend                              # drawn: the known two; parked: the stand-in
        # a change saves the list again (an indicator's eye): the stand-in stays at its place
        frame.locator('.chart-legend [data-act="eye"]').first.dispatch_event('click')     # shown on hover
        page.wait_for_function("() => JSON.parse(localStorage.getItem('ml.ind.v1') || '[]')[0].on === false")
        assert [o['def'] for o in saved_list(page)] == ['sma', 'I_LAB_STANDIN', 'ema']
        page.reload()
        drawn, text = terminal_drawn(page)
        assert drawn, text[:300]
        assert [o['def'] for o in saved_list(page)] == ['sma', 'I_LAB_STANDIN', 'ema'] and saved_list(page)[1] == LAB
    finally:
        guest_indicators([])
