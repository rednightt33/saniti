"""EXEC-MU-ACCOUNTS Phase 3b, fix round after the checkers C1-C3 (CONTRACT.md 8b; ERRORS M482).

- C3 F3: each worker gets the allow of its own capability families (allow.FAMILIES): a plan that holds an item family of
  one worker but not the same family of the other sends the ids to the one and none to the other, on every call site
  (the Backtest's validate, signals and dispatch; the Screener's run and validate). A swap of the worker name at a call
  site fails here. Since the 3b follow-up (user decision 2026-11-18) the candlestick patterns are the kind with a family
  per worker, and the Terminal's indicator family reaches both workers.
- C3 F4: a worker's 403 CAPABILITY_REQUIRED reaches the page with its display_name on the two paths no test held: a job
  the worker ends FAILED while it runs (the status poll) and the signals preview.
C2's probes are in test_screener.py (the catalog's preset counts per allow, the review per plan); C1 F1 (built-in options
of the Backtest that compute an item) was decided 2026-11-18 (O3b-1, CONTRACT.md 8b "3b follow-up") and is held by
apps/backtest-worker/tests/c1-phase3b.test.ts.
"""
from fastapi.testclient import TestClient

from app.main import create_app
from conftest import FakeOrc
from test_backtest import REFUSED_ITEM, named_refusal, paid_allow, preview_of, run_next, single
from test_backtest import app, backtest_tables, configured, worker  # noqa: F401 - the fixtures
from test_phase3a_gates import override, paid_user
from test_principal import on, sign_in, workers  # noqa: F401 - the fixtures
from test_screener import run_body


def test_each_worker_gets_the_allow_of_its_own_families(on, store, workers):
    bt, sc = workers
    with TestClient(create_app(on, store, FakeOrc())) as c:
        alice = paid_user(store, 'alice')
        released = paid_allow()
        one = released['candle_pattern'][0]
        override(store, alice['user_id'], 'terminal.indicator', '{"ids": []}')          # the Terminal's indicators taken
        override(store, alice['user_id'], 'backtest.candle_pattern', '{"ids": []}')     # the Backtest's patterns taken
        override(store, alice['user_id'], 'screener.candle_pattern', '{"ids": ["%s"]}' % one)   # one Screener pattern
        c.headers_for = sign_in(c, 'alice', 'alice-password')
        # the Terminal's indicator grant reaches both workers (3b follow-up); each worker its own candlestick family
        backtest_allow = {**released, 'indicator': [], 'candle_pattern': []}
        screener_allow = {**released, 'indicator': [], 'candle_pattern': [one]}
        assert c.post('/api/v1/backtests/signals', headers=c.headers_for, json=preview_of()).status_code == 200
        assert bt.posted('/v1/signals')[-1]['body']['context']['allow'] == backtest_allow
        assert c.post('/api/v1/backtests', headers=c.headers_for, json={**single(), 'client_request_id': 'f3'}).status_code == 202
        assert bt.posted('/v1/validate')[-1]['body']['context']['allow'] == backtest_allow
        run_next(c)
        assert bt.posted('/v1/jobs')[-1]['body']['context']['allow'] == backtest_allow          # read at dispatch
        c.post('/api/v1/screener/run', headers=c.headers_for, json=run_body(seq=1))
        assert sc.called('/v1/run')[-1]['body']['context']['allow'] == screener_allow
        c.post('/api/v1/screener/validate', headers=c.headers_for, json={'schema_version': 1, 'definition': run_body()['definition']})
        assert sc.called('/v1/validate')[-1]['body']['context']['allow'] == screener_allow
    assert released['indicator'] and released['candle_pattern']                  # the two families are not empty anyway


def test_a_job_the_worker_ends_failed_on_an_item_while_it_runs_keeps_the_display_name(app, worker):
    """The worker accepted the job, then refused an item on its job thread (run.ts runJob checks the request again):
    the status poll reads FAILED with the worker's CAPABILITY_REQUIRED, and the job ends with it and its display_name."""
    c = app
    worker.fail_with = REFUSED_ITEM
    try:
        job = c.post('/api/v1/backtests', headers=c.headers_for, json={**single(), 'client_request_id': 'f4-poll'}).json()['request_id']
        run_next(c)
    finally:
        worker.fail_with = None
    status = c.get(f'/api/v1/backtests/{job}').json()
    assert status['state'] == 'FAILED' and status['error'] == named_refusal()


def test_a_signals_capability_refusal_is_relayed_with_its_display_name(app, worker):
    """The signals preview relays the worker's 403 CAPABILITY_REQUIRED as /v1/validate does: status, code, field,
    message and details unchanged, details.display_name added."""
    c = app
    worker.signals_error = (403, REFUSED_ITEM)
    try:
        r = c.post('/api/v1/backtests/signals', headers=c.headers_for, json=preview_of())
    finally:
        worker.signals_error = None
    assert r.status_code == 403 and r.json() == {'error': named_refusal()}
