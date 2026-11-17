"""Checker C1 (security), EDGE multi-user Phase 3a (257a1e4c): failing tests for the findings.

F1 CONTRACT.md 8b "Saved-item caps": "`limits()` and the answers report the principal's own numbers"; AGENTS.md "Gates
   and evidence" (a). The Backtest catalog publishes the worker's queued_per_owner (the HARD constant) to every
   principal, while the submit refuses at the principal's backtest.queued_jobs.
F2 CONTRACT.md section 3: a plan limit answers 429 LIMIT_REACHED (details.limit, retry_after_s) and "Retry-After is set
   on every 429". The backtest queue cap (now the plan's backtest.queued_jobs) answers 429 QUEUE_FULL without either.
F3 CONTRACT.md section 3: CAPABILITY_REQUIRED carries details.display_name, the name the person sees, and messages hold
   no internal names (AGENTS.md "Gates and evidence" (d)). Every Phase 3a gate answers display_name = the internal key
   (errors.py CAPABILITY_NAMES knows only admin.manual), though edge_bff.capabilities.display_name holds the name.
"""
from fastapi.testclient import TestClient

from app.main import create_app
from conftest import FakeOrc
from test_backtest import single
from test_phase3a_gates import BT, override, paid_user
from test_principal import db, make_user, on, sign_in, workers  # noqa: F401 - the fixtures


def test_f1_the_backtest_catalog_reports_the_principals_own_queue_limit(on, store):
    with TestClient(create_app(on, store, FakeOrc())) as c:
        alice = paid_user(store, 'alice')
        override(store, alice['user_id'], 'backtest.queued_jobs', '1')
        h = sign_in(c, 'alice', 'alice-password')
        published = c.get(f'{BT}/catalog').json()['limits']['queued_per_owner']
        assert c.post(BT, headers=h, json={**single(), 'client_request_id': 'one'}).status_code == 202
        refused = c.post(BT, headers=h, json={**single('BBRI'), 'client_request_id': 'two'})
        assert refused.status_code == 429
        # the rule shown before the write must be the one the write is refused by
        assert published == 1, f'the catalog says {published} queued backtests, the submit refused the second'


def test_f2_the_plan_queue_cap_refusal_follows_the_error_contract(on, store):
    with TestClient(create_app(on, store, FakeOrc())) as c:
        alice = paid_user(store, 'alice')
        override(store, alice['user_id'], 'backtest.queued_jobs', '1')
        h = sign_in(c, 'alice', 'alice-password')
        assert c.post(BT, headers=h, json={**single(), 'client_request_id': 'one'}).status_code == 202
        r = c.post(BT, headers=h, json={**single('BBRI'), 'client_request_id': 'two'})
        assert r.status_code == 429
        assert 'retry-after' in r.headers, 'CONTRACT.md 3: Retry-After is set on every 429'
        error = r.json()['error']
        assert error['code'] == 'LIMIT_REACHED' and error['details'].get('limit'), error


def test_f3_a_capability_refusal_names_the_capability_as_the_person_sees_it(on, store):
    with TestClient(create_app(on, store, FakeOrc())) as c:
        make_user(store, 'alice', 'alice-password')
        sign_in(c, 'alice', 'alice-password')
        shown = {r['capability_key']: r['display_name'] for r in db(store, 'SELECT capability_key, display_name FROM edge_bff.capabilities')}
        for path, capability in ((BT, 'backtest.view'), ('/api/v1/terminal/presets', 'terminal.presets'),
                                 ('/api/v1/watchlist/lists', 'watchlist.view')):
            details = c.get(path).json()['error']['details']
            assert details['capability'] == capability
            assert details['display_name'] == shown[capability], (path, details)
