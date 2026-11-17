"""C3 (conformance) check of EXEC-MU-ACCOUNTS Phase 3a (integrated 257a1e4c) against CONTRACT.md sections 3 and 8b.

F1: the queued-backtest cap became a plan limit (backtest.queued_jobs, min(plan, BACKTEST_QUEUED_PER_OWNER)), but its
refusal is still the old 429 QUEUE_FULL with no Retry-After and no details naming the limit and the allowed number.
CONTRACT.md section 3: "Retry-After is set on every 429" and a limit refusal carries `details.limit`; 8b: "limits() and
the answers report the principal's own numbers". AGENTS.md "Gates and evidence" (a)/(d): the account cannot see its
own number before it acts, and the refusal does not name it. Blocking before the switch goes on (not before the 3a
deploy with the switch off: the configured owner's cap is today's constant).
"""
from fastapi.testclient import TestClient

from app.main import create_app
from conftest import FakeOrc
from test_backtest import single
from test_phase3a_gates import BT, override, paid_user
from test_principal import db, make_user, on, sign_in, workers  # noqa: F401 - the fixtures


def test_the_queued_backtest_refusal_names_the_plans_limit_and_sets_retry_after(on, store):
    with TestClient(create_app(on, store, FakeOrc())) as c:
        alice = paid_user(store, 'alice')
        override(store, alice['user_id'], 'backtest.queued_jobs', '1')
        h = sign_in(c, 'alice', 'alice-password')
        assert c.post(BT, headers=h, json={**single(), 'client_request_id': 'one'}).status_code == 202
        r = c.post(BT, headers=h, json={**single('BBRI'), 'client_request_id': 'two'})
        assert r.status_code == 429, r.text
        assert r.headers.get('retry-after'), 'CONTRACT.md 3: Retry-After is set on every 429'
        details = r.json()['error']['details']
        assert details.get('limit') and details.get('allowed') == 1, \
            f'CONTRACT.md 3/8b: the refusal names the limit and the principal\'s own number, got {details}'
