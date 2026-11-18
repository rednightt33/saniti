"""C-P1S independent check (EXEC-MU-ACCOUNTS, ultracode re-check of Phases 0-3b): Phase 1's account preferences
(CONTRACT.md 4b, app/preferences.py) against Phase 3a's decision D5 (CONTRACT.md 8b, user 2026-11-17: "user yang
paketnya turun kehilangan akses baca ke isi lamanya (percakapan, hasil backtest, screen tersimpan, watchlist, layout,
drawing, preset) sampai upgrade lagi"; "Reads need <tab>.view or the item's own capability, writes need the run or save
capability") and 13.7 ("a free principal is refused on every second path to the same content").

GET and PUT /api/v1/preferences need only the principal (`auth.principal`, `auth.writer`): no tab capability. The keys
they carry are the saved items and the content of the tabs (shared/edge-session.ts STORAGE `sync`; contract 4b names
them "preferences or saved items"): the Backtest's My conditions (`ml.my`), the Screener's last screen definition and
its extra columns (`scr.last`, `scr.extraCols`), the Monitor's model choice, the Watchlist's open list. A principal whose
plan no longer holds the Backtest or the Screener is refused every route of those tabs, yet reads (and writes) their
saved items here. The same class as M481 C2 1 (the Screener star writing the Watchlist's data with only
screener.view): a route that reads or writes another tab's data needs that tab's capability.
"""
from fastapi.testclient import TestClient

from app.main import create_app
from conftest import FakeOrc
from test_principal import db, make_user, on, sign_in, workers  # noqa: F401
from test_phase3a_gates import BT, SC, paid_user

PREFS = '/api/v1/preferences'
MY_CONDITIONS = [{'name': 'RSI under 30', 'condition': {'indicator': 'I13', 'op': 'lt', 'value': 30}}]
LAST_SCREEN = {'name': 'Golden Cross', 'definition': {'conditions': [{'metric': 'macd_divergence'}]}}


def test_a_plan_without_the_backtest_and_the_screener_neither_reads_nor_writes_their_saved_items(on, store):
    with TestClient(create_app(on, store, FakeOrc())) as c:
        alice = paid_user(store, 'alice')
        h = sign_in(c, 'alice', 'alice-password')
        # on the paid plan: the Backtest's My conditions and the Screener's last screen are saved to the account
        assert c.put(f'{PREFS}/ml.my', headers=h, json={'value': MY_CONDITIONS, 'version': None}).status_code == 201
        assert c.put(f'{PREFS}/scr.last', headers=h, json={'value': LAST_SCREEN, 'version': None}).status_code == 201
        assert c.get(f'{BT}/catalog').status_code != 403 and c.get(f'{SC}/items').status_code != 403

        # the plan is lowered (the subscription ends: the default plan, which holds neither tab)
        db(store, "UPDATE edge_bff.subscriptions SET status = 'cancelled' WHERE user_id = %s", alice['user_id'])
        h = sign_in(c, 'alice', 'alice-password')
        assert c.get(BT).status_code == 403 and c.get(f'{SC}/items').status_code == 403      # D5 holds on the tabs

        held = c.get(PREFS)
        assert held.status_code == 200
        keys = set(held.json()['preferences'])
        assert 'ml.my' not in keys, ('the Backtest\'s My conditions are read through /api/v1/preferences by a plan that '
                                     'holds no backtest.view (D5)')
        assert 'scr.last' not in keys, ('the Screener\'s last screen is read through /api/v1/preferences by a plan that '
                                        'holds no screener.view (D5)')
        wrote = c.put(f'{PREFS}/ml.my', headers=h, json={'value': MY_CONDITIONS + MY_CONDITIONS, 'version': 1})
        assert wrote.status_code == 403 and wrote.json()['error']['code'] in ('CAPABILITY_REQUIRED', 'PLAN_EXPIRED'), (
            'a plan without the Backtest saves Backtest conditions through /api/v1/preferences', wrote.status_code, wrote.text)
