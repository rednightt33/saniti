"""EDGE backtest in edge-bff (CONTRACT.md sections 8-11): the /api/v1/backtests routes, the job tables (migration
20261026_005, applied here as conftest applies the others), the queue loop against a fake backtest worker that is a real
local HTTP server speaking the worker's private API, and the /backtest page with its frame's CSP.

The fake worker's results are small synthetic BacktestResult-shaped documents built from the request (test data only);
edge-bff does not interpret them beyond meta versions, meta.trials and events, which is what is checked here."""
import asyncio
import dataclasses
import gzip
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import threading
import time

import psycopg
import pytest
from fastapi.testclient import TestClient
import uvicorn

from app import main
from app.backtest import BacktestLoop, split_result
from app.main import create_app
from conftest import FakeOrc

ORIGIN = {'Origin': 'http://testserver'}
KEY = 'w' * 40
MIGRATION = Path(__file__).resolve().parents[3] / 'database/migrations/20261026_005_edge_bff_backtest.sql'
ROLLBACK = '\n'.join(line[3:] for line in MIGRATION.read_text().split('-- Rollback', 1)[1].splitlines()[1:] if line.startswith('-- '))


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def single(ticker='BBCA', **change):
    request = {'schema_version': 1, 'mode': 'single', 'single': {'ticker': ticker, 'benchmark': 'buy_and_hold'},
               'period': {'from': '2024-01-02', 'to': '2026-10-23', 'oos_fraction': 0.2},
               'entry': {'logic': 'all', 'at_least': 1, 'window_bars': 3,
                         'conditions': [{'id': 'c1', 'kind': 'indicator', 'indicator': 'I13', 'lhs': {'type': 'output', 'output': 'rsi'},
                                         'op': 'lt', 'rhs': {'type': 'value', 'value': 30}}]},
               'robustness': {'monte_carlo_runs': 1000, 'seed': 7, 'sensitivity': True}}
    request.update(change)
    return request


def portfolio(**change):
    request = {**single(), 'mode': 'portfolio', 'portfolio': {'universe': 'all', 'max_positions': 3, 'rank_by': 'adx',
                                                              'min_avg_value_20d_idr': 0}}
    del request['single']
    request.update(change)
    return request


def lineage_of(request):
    """The fake worker's strategy line: mode and ticker or universe (the real one is core/hash.ts lineageKey)."""
    return sha(json.dumps([request['mode'], (request.get('single') or {}).get('ticker'),
                           (request.get('portfolio') or {}).get('universe')]))


def variant_of(request):
    return sha(json.dumps({k: v for k, v in request.items() if k != 'robustness'}, sort_keys=True))


def result_of(job_id, request):
    """A BacktestResult-shaped document for the request: two condition tracks and an exit track per ticker, numbers
    that need exact round trips, the run's variant and one sensitivity cell in meta.trials."""
    tickers = [request['single']['ticker']] if request['mode'] == 'single' else ['AAAA', 'BBBB', 'CCCC']
    variant = variant_of(request)
    return {
        'schema_version': 1,
        'meta': {'engine_version': 'engine-test-1', 'registry_version': 'registry-test-1', 'data_version': sha('data'),
                 'request_hash': sha('rh' + job_id), 'lineage_key': lineage_of(request), 'seed': 7, 'duration_ms': 1234,
                 'mode': request['mode'], 'tickers': tickers, 'benchmark': {'kind': 'ihsg', 'ticker': 'IHSG'},
                 'data_through': '2026-10-23', 'warnings': [{'code': 'TICK_NOT_MODELLED', 'message': 'Tick sizes are not modelled'}],
                 'trials': {'prior': 0, 'this_run': 2, 'total': 2,
                            'variants': [{'variant_hash': variant, 'sharpe_daily': 0.1 + 0.2, 'kind': 'run'},
                                         {'variant_hash': sha('cell' + variant), 'sharpe_daily': -0.012345678901234567, 'kind': 'sensitivity'}]}},
        'dates': ['2026-10-21', '2026-10-22', '2026-10-23'], 'equity': [1e8, 100123456.789, 99999999.99],
        'daily_returns': [0.00123456789, -0.0012345], 'trades': [{'trade_id': f'{tickers[0]}-2026-10-22-1', 'ticker': tickers[0]}],
        'robustness': {'monte_carlo': None, 'sensitivity': None, 'deflated': {'sr0': None, 'dsr': None, 'trials': 2, 'sharpe_variance_from': 'trials'}},
        'events': {'conditions': [{'condition_id': c, 'ticker': t, 'track': {'on': [i], 'runs': [i, i + 1]}}
                                  for i, t in enumerate(tickers) for c in ('c1', 'x1')],
                   'entries': {t: {'on': [1], 'runs': [1, 1]} for t in tickers},
                   'exits': {t: {'on': [2], 'runs': [2, 2]} for t in tickers},
                   'skipped': [{'ticker': tickers[0], 'signal_date': '2026-10-21', 'signal_event': 0, 'reason': 'no_slot'}]}}


class FakeWorker:
    """The backtest worker's private API (CONTRACT.md section 8, the lead's route list) on 127.0.0.1. Jobs finish after
    `finish_after` status reads; switches make it refuse, forget, hang, fail or stop answering."""

    def __init__(self):
        self.lock = threading.Lock()
        self.calls, self.jobs = [], {}
        self.finish_after = 2
        self.hang = False              # jobs never finish
        self.down = False              # every answer is 503
        self.forget = False            # status reads answer 404 UNKNOWN_JOB
        self.busy = 0                  # the next n POST /v1/jobs answer 409 BUSY (another job)
        self.lose_post_answer = False  # POST /v1/jobs takes the job but answers 503 (an answer lost on the way)
        self.fail_with = None          # jobs end FAILED with this error
        self.garbage = False           # the result is not JSON
        self.validate_error = None     # (status, error) for /v1/validate
        self.on_poll = None            # hook(job_id, polls) on each status read
        self.catalog = {'schema_version': 1, 'engine_version': 'engine-test-1', 'registry_version': 'registry-test-1',
                        'data_through': '2026-10-23', 'first_date': '2019-01-02',
                        'tickers': [{'ticker': 'BBCA', 'name': 'Bank Central Asia', 'type': 'stock', 'sector': 'Finance'}],
                        'universes': [{'id': 'all', 'label': 'All stocks', 'tickers': 1}],
                        'flow': {'available': False, 'reason': 'not verified', 'brokers': []},
                        'limits': {'max_positions': 10, 'window_bars': {'min': 1, 'max': 20}, 'monte_carlo_runs': 1000,
                                   'max_download_bytes': 1, 'max_broker_rows': 1, 'timeout_seconds': 600, 'queued_per_owner': 3}}
        worker = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def answer(self, status, body=None, raw=None, gz=False):
                data = raw if raw is not None else (json.dumps(body).encode() if body is not None else b'')
                if gz:
                    data = gzip.compress(data)
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                if gz:
                    self.send_header('Content-Encoding', 'gzip')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def handle_one(self, method):
                length = int(self.headers.get('content-length') or 0)
                body = json.loads(self.rfile.read(length)) if length else None
                with worker.lock:
                    worker.calls.append({'method': method, 'path': self.path, 'body': body,
                                         'key': self.headers.get('x-backtest-worker-key')})
                if self.path == '/health':
                    return self.answer(200, {'ok': True})
                if self.headers.get('x-backtest-worker-key') != KEY:
                    return self.answer(401, {'error': {'code': 'UNAUTHORIZED'}})
                if worker.down:
                    return self.answer(503, {'error': {'code': 'UNAVAILABLE'}})
                route = (method, self.path)
                if route == ('GET', '/v1/catalog'):
                    return self.answer(200, worker.catalog)
                if route == ('POST', '/v1/validate'):
                    if worker.validate_error:
                        return self.answer(worker.validate_error[0], {'error': worker.validate_error[1]})
                    request = body['request']
                    return self.answer(200, {'ok': True, 'lineage_key': lineage_of(request), 'variant_hash': variant_of(request),
                                             'tickers': [request['single']['ticker']] if request['mode'] == 'single' else ['AAAA', 'BBBB', 'CCCC']})
                if route == ('POST', '/v1/signals'):
                    if body.get('universe') == 'sector:Nope':
                        return self.answer(422, {'error': {'code': 'INVALID_UNIVERSE', 'field': 'universe', 'message': 'Unknown universe'}})
                    return self.answer(200, {'data_version': sha('data'), 'rows': [{'ticker': 'BBCA', 'entry_signals': 4, 'last_signal': '2026-10-20'}]})
                if route == ('POST', '/v1/jobs'):
                    with worker.lock:
                        if worker.busy:
                            worker.busy -= 1
                            return self.answer(409, {'error': {'code': 'BUSY'}})
                        worker.jobs[body['job_id']] = {'request': body['request'], 'context': body['context'], 'polls': 0,
                                                       'cancelled': False}
                    if worker.lose_post_answer:
                        return self.answer(503, {'error': {'code': 'LOST'}})
                    return self.answer(202, {'job_id': body['job_id']})
                parts = self.path.split('/')
                if len(parts) >= 4 and parts[1:3] == ['v1', 'jobs']:
                    job_id = parts[3]
                    job = worker.jobs.get(job_id)
                    if job is None or (worker.forget and len(parts) == 4):
                        return self.answer(404, {'error': {'code': 'UNKNOWN_JOB'}})
                    if method == 'POST' and parts[4:] == ['cancel']:
                        job['cancelled'] = True
                        return self.answer(202)
                    if method == 'GET' and len(parts) == 4:
                        job['polls'] += 1
                        if worker.on_poll:
                            worker.on_poll(job_id, job['polls'])
                        state = ('CANCELLED' if job['cancelled'] else 'FAILED' if worker.fail_with
                                 else 'FINISHED' if not worker.hang and job['polls'] > worker.finish_after else 'RUNNING')
                        return self.answer(200, {'request_id': job_id, 'state': state,
                                                 'progress': {'phase': 'backtest', 'done': min(job['polls'], worker.finish_after), 'total': worker.finish_after},
                                                 'error': worker.fail_with if state == 'FAILED' else None,
                                                 'created_at': '2026-10-26T00:00:00Z', 'started_at': '2026-10-26T00:00:00Z',
                                                 'finished_at': None, 'duration_ms': 55 if state in ('FAILED', 'CANCELLED') else None,
                                                 'result_bytes': None})
                    if method == 'GET' and parts[4:] == ['result']:
                        if worker.garbage:
                            return self.answer(200, raw=b'{"schema_version": 1, "meta": NaN}', gz=True)
                        return self.answer(200, raw=json.dumps(result_of(job_id, job['request'])).encode(), gz=True)
                return self.answer(404, {'error': {'code': 'NOT_FOUND'}})

            def do_GET(self):
                self.handle_one('GET')

            def do_POST(self):
                self.handle_one('POST')

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.url = f'http://127.0.0.1:{self.server.server_address[1]}'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def posted(self, path):
        return [c for c in self.calls if c['method'] == 'POST' and c['path'] == path]

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture(scope='module')
def backtest_tables(database):
    """The migration applied to the disposable database, as conftest applies the edge_bff ones. Taken out again with
    its rollback block after this module when it was applied here: scripts/provision_edge_bff_login.py still allows
    only the three original edge_bff tables, so test_edge's provisioning check fails while these tables exist."""
    with psycopg.connect(database, autocommit=True) as c:
        applied = c.execute("SELECT to_regclass('edge_bff.backtest_jobs')").fetchone()[0] is None
        if applied:
            c.execute(MIGRATION.read_text())
    yield database
    if applied:
        with psycopg.connect(database, autocommit=True) as c:
            c.execute(ROLLBACK)


@pytest.fixture
def worker():
    fake = FakeWorker()
    yield fake
    fake.close()


@pytest.fixture
def configured(settings, store, backtest_tables, worker):
    with psycopg.connect(backtest_tables) as c:
        c.execute('TRUNCATE edge_bff.backtest_results, edge_bff.backtest_trials, edge_bff.backtest_jobs')
    return dataclasses.replace(settings, backtest_worker_url=worker.url, backtest_worker_key=KEY, backtest_timeout_seconds=30)


@pytest.fixture
def app(configured, store):
    application = create_app(configured, store, FakeOrc())
    with TestClient(application) as c:
        c.headers_for = login(c)
        yield c


def login(c):
    r = c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'owner', 'password': 'local-test-password'})
    assert r.status_code == 200, r.text
    return {**ORIGIN, 'X-CSRF-Token': r.json()['csrf_token']}


def submit(c, request, key=None):
    body = {**request, **({'client_request_id': key} if key else {})}
    return c.post('/api/v1/backtests', headers=c.headers_for, json=body)


def run_next(c, settings=None):
    """One turn of the queue loop, as the in-process loop takes it (claim, hand over, follow to the end)."""
    bt = c.app.state.backtests
    loop = BacktestLoop(settings or bt.settings, bt.store, bt.worker)
    row = bt.store.claim(90)
    assert row is not None
    asyncio.run(loop.process(row))
    return row['request_id']


def db(c, sql, *args):
    with c.app.state.store.connect() as conn:
        cur = conn.execute(sql, args)
        return cur.fetchall() if cur.description else cur.rowcount


def test_single_run_progress_result_and_events(app, worker):
    c = app
    seen = []
    worker.on_poll = lambda job_id, polls: seen.append(db(c, 'SELECT progress FROM edge_bff.backtest_jobs WHERE request_id=%s', job_id)[0]['progress'])
    r = submit(c, single(), 'first')
    assert r.status_code == 202 and r.json()['state'] == 'QUEUED' and r.json()['created'] is True
    job_id = r.json()['request_id']
    status = c.get(f'/api/v1/backtests/{job_id}').json()
    assert status['state'] == 'QUEUED' and status['progress'] is None and status['started_at'] is None
    assert c.get(f'/api/v1/backtests/{job_id}/result').json()['error']['code'] == 'NOT_FINISHED'
    run_next(c)
    handed = worker.posted('/v1/jobs')[0]['body']
    assert handed == {'job_id': job_id, 'request': single(), 'context': {'job_id': job_id, 'prior_trials': []}}
    assert all(call['key'] == KEY for call in worker.calls)
    # progress of the previous read is stored while the job runs (the hook reads before the answer is stored)
    assert seen[1] == {'phase': 'backtest', 'done': 1, 'total': 2}
    status = c.get(f'/api/v1/backtests/{job_id}').json()
    assert status['state'] == 'FINISHED' and status['duration_ms'] == 1234 and status['error'] is None
    assert status['started_at'] and status['finished_at'] and status['result_bytes'] > 0
    expected = result_of(job_id, single())
    got = c.get(f'/api/v1/backtests/{job_id}/result')
    assert got.status_code == 200 and got.headers['content-encoding'] == 'gzip' and got.headers['content-type'] == 'application/json'
    assert got.json() == expected                         # the worker's result as it was: events merged back, numbers exact
    assert got.json()['meta']['trials']['variants'][0]['sharpe_daily'] == 0.1 + 0.2
    plain = c.get(f'/api/v1/backtests/{job_id}/result', headers={'Accept-Encoding': 'identity'})
    assert 'content-encoding' not in plain.headers and json.loads(plain.content) == expected
    events = c.get(f'/api/v1/backtests/{job_id}/events?ticker=BBCA').json()
    assert events == {'conditions': expected['events']['conditions'], 'exits': expected['events']['exits']}
    rows = db(c, 'SELECT part, bytes, sha256, payload FROM edge_bff.backtest_results WHERE request_id=%s ORDER BY part', job_id)
    assert [r['part'] for r in rows] == ['core', 'events:BBCA']
    core = json.loads(gzip.decompress(bytes(rows[0]['payload'])))
    assert set(core['events']) == {'entries', 'skipped'} and core['meta'] == expected['meta']
    assert all(r['bytes'] == len(r['payload']) and r['sha256'] == hashlib.sha256(bytes(r['payload'])).hexdigest() for r in rows)
    job = db(c, 'SELECT * FROM edge_bff.backtest_jobs WHERE request_id=%s', job_id)[0]
    assert (job['engine_version'], job['registry_version'], job['data_version']) == ('engine-test-1', 'registry-test-1', sha('data'))
    assert job['result_bytes'] == sum(r['bytes'] for r in rows) and job['lease_token'] is None
    listed = c.get('/api/v1/backtests').json()['items']
    assert [i['request_id'] for i in listed] == [job_id] and listed[0]['request'] == single() and listed[0]['state'] == 'FINISHED'


def test_portfolio_result_is_core_and_events_come_per_ticker(app, worker):
    c = app
    job_id = submit(c, portfolio()).json()['request_id']
    run_next(c)
    expected = result_of(job_id, portfolio())
    core = c.get(f'/api/v1/backtests/{job_id}/result').json()
    assert core['events'] == {'entries': expected['events']['entries'], 'skipped': expected['events']['skipped']}
    assert {k: v for k, v in core.items() if k != 'events'} == {k: v for k, v in expected.items() if k != 'events'}
    for ticker in ('AAAA', 'BBBB', 'CCCC'):
        part = c.get(f'/api/v1/backtests/{job_id}/events?ticker={ticker}').json()
        assert part['exits'] == {ticker: expected['events']['exits'][ticker]}
        assert part['conditions'] == [x for x in expected['events']['conditions'] if x['ticker'] == ticker]
    missing = c.get(f'/api/v1/backtests/{job_id}/events?ticker=ZZZZ')
    assert missing.status_code == 404 and missing.json() == {'error': {'code': 'EVENTS_NOT_FOUND', 'field': 'ticker'}}
    assert c.get(f'/api/v1/backtests/{job_id}/events?ticker=bbca').status_code == 422
    assert c.get(f'/api/v1/backtests/{job_id}/events').status_code == 422
    assert c.get('/api/v1/backtests/bt_' + '0' * 32).json()['error']['code'] == 'BACKTEST_NOT_FOUND'
    assert c.get('/api/v1/backtests/../../etc').status_code == 404


def test_idempotent_resubmit_conflict_and_bad_key(app, worker):
    c = app
    first = submit(c, single(), 'same-key')
    again = submit(c, single(), 'same-key')
    assert first.status_code == again.status_code == 202
    assert again.json() == {'request_id': first.json()['request_id'], 'state': 'QUEUED', 'created': False}
    assert len(worker.posted('/v1/validate')) == 1       # the second answer came from the job table
    changed = submit(c, single('TLKM'), 'same-key')
    assert changed.status_code == 409 and changed.json() == {'error': {'code': 'SUBMISSION_CONFLICT'}}
    bad = submit(c, single(), 'not a key!')
    assert bad.status_code == 422 and bad.json()['error'] == {'code': 'INVALID_INPUT', 'field': 'client_request_id'}
    assert c.post('/api/v1/backtests', headers=c.headers_for, content=b'[1]').json()['error']['code'] == 'INVALID_INPUT'
    assert c.post('/api/v1/backtests', headers=c.headers_for, content=b'{"x": NaN}').json()['error']['code'] == 'INVALID_INPUT'
    assert len(db(c, 'SELECT 1 FROM edge_bff.backtest_jobs')) == 1
    # without a client_request_id every submission is a new job
    assert submit(c, single()).json()['request_id'] != submit(c, single()).json()['request_id']


def test_queue_limit_one_running_and_three_queued(app, worker):
    c = app
    ids = [submit(c, single(), f'k{i}').json()['request_id'] for i in range(3)]
    full = submit(c, single(), 'k3')
    assert full.status_code == 429 and full.json() == {'error': {'code': 'QUEUE_FULL'}}
    assert submit(c, single(), 'k0').json()['request_id'] == ids[0]   # a known submission still answers
    store = c.app.state.backtests.store
    running = store.claim(90)
    assert running['request_id'] == ids[0] and running['state'] == 'RUNNING'
    assert store.claim(90) is None                       # one running job per owner: the others wait
    assert submit(c, single(), 'k3').status_code == 202  # the running one is not in the queue
    assert submit(c, single(), 'k4').status_code == 429
    with pytest.raises(psycopg.errors.UniqueViolation):  # the database rule behind it
        db(c, "UPDATE edge_bff.backtest_jobs SET state='RUNNING',lease_token='x',lease_expires_at=now(),started_at=now() WHERE request_id=%s", ids[1])


def test_validation_error_is_relayed_as_it_is(app, worker):
    c = app
    worker.validate_error = (422, {'code': 'NO_ACTIVE_CONDITION', 'field': 'entry.conditions', 'message': 'Enable at least one entry condition',
                                   'details': {'enabled': 0}})
    r = submit(c, single(), 'v')
    assert r.status_code == 422 and r.json() == {'error': worker.validate_error[1]}
    worker.validate_error = (424, {'code': 'DATA_UNAVAILABLE', 'message': 'see http://terminal-api.railway.internal:8080/x'})
    r = submit(c, single(), 'v')
    assert r.status_code == 424 and r.json()['error'] == {'code': 'DATA_UNAVAILABLE', 'message': 'see [internal address]'}
    assert db(c, 'SELECT count(*) AS n FROM edge_bff.backtest_jobs')[0]['n'] == 0
    worker.down = True
    assert submit(c, single(), 'v').json() == {'error': {'code': 'BACKTEST_UNAVAILABLE'}}


def test_trials_are_recorded_and_passed_to_the_next_run_of_the_line(app, worker):
    c = app
    first = submit(c, single()).json()['request_id']
    run_next(c)
    trials = db(c, 'SELECT * FROM edge_bff.backtest_trials ORDER BY kind')
    assert [(t['kind'], t['sharpe_daily'], t['request_id']) for t in trials] == [('run', 0.1 + 0.2, first), ('sensitivity', -0.012345678901234567, first)]
    assert all(t['lineage_key'] == lineage_of(single()) for t in trials)
    # the same line with another number: a new variant; it gets the line's trials, then adds its own
    second = submit(c, {**single(), 'entry': {**single()['entry'], 'window_bars': 5}}).json()['request_id']
    run_next(c)
    context = [x for x in worker.posted('/v1/jobs') if x['body']['job_id'] == second][0]['body']['context']
    assert context == {'job_id': second, 'prior_trials': [{'variant_hash': t['variant_hash'], 'sharpe_daily': t['sharpe_daily']}
                                                          for t in sorted(trials, key=lambda t: (t['created_at'], t['variant_hash']))]}
    assert db(c, 'SELECT count(*) AS n FROM edge_bff.backtest_trials')[0]['n'] == 4
    # the first variant again: nothing new is counted and the first recorded Sharpe stays (on conflict do nothing)
    third = submit(c, single()).json()['request_id']
    run_next(c)
    assert db(c, 'SELECT count(*) AS n FROM edge_bff.backtest_trials')[0]['n'] == 4
    assert db(c, "SELECT request_id FROM edge_bff.backtest_trials WHERE kind='run' AND variant_hash=%s", variant_of(single()))[0]['request_id'] == first
    assert third != first
    # another line starts with no trials
    other = submit(c, single('TLKM')).json()['request_id']
    run_next(c)
    assert [x for x in worker.posted('/v1/jobs') if x['body']['job_id'] == other][0]['body']['context']['prior_trials'] == []


def test_cancel_queued_and_running(app, worker):
    c = app
    queued = submit(c, single(), 'q').json()['request_id']
    r = c.post(f'/api/v1/backtests/{queued}/cancel', headers=c.headers_for)
    assert r.status_code == 202 and r.json()['state'] == 'CANCELLED' and r.json()['finished_at']
    again = c.post(f'/api/v1/backtests/{queued}/cancel', headers=c.headers_for)
    assert again.status_code == 409 and again.json() == {'error': {'code': 'NOT_RUNNING'}}
    assert c.app.state.backtests.store.claim(90) is None and worker.posted('/v1/jobs') == []
    # running, not yet handed to the worker: it ends here and never reaches it
    before = submit(c, single(), 'b').json()['request_id']
    store = c.app.state.backtests.store
    row = store.claim(90)
    marked = c.post(f'/api/v1/backtests/{before}/cancel', headers=c.headers_for)
    assert marked.status_code == 202 and marked.json()['state'] == 'RUNNING'
    asyncio.run(BacktestLoop(c.app.state.backtests.settings, store, c.app.state.backtests.worker).process(row))
    assert c.get(f'/api/v1/backtests/{before}').json()['state'] == 'CANCELLED' and worker.posted('/v1/jobs') == []
    # running at the worker: the loop asks it to stop and records the cancellation it reports
    running = submit(c, single(), 'r').json()['request_id']
    worker.hang = True
    worker.on_poll = lambda job_id, polls: polls == 1 and store.cancel(c.app.state.backtests.settings.owner, job_id)
    run_next(c)
    assert worker.posted(f'/v1/jobs/{running}/cancel')
    status = c.get(f'/api/v1/backtests/{running}').json()
    assert status['state'] == 'CANCELLED' and status['error'] is None and status['duration_ms'] == 55
    assert db(c, 'SELECT count(*) AS n FROM edge_bff.backtest_trials')[0]['n'] == 0
    assert c.get(f'/api/v1/backtests/{running}/result').json()['error']['code'] == 'NOT_FINISHED'


def test_worker_lost_unreachable_and_failed(app, worker):
    c = app
    forgotten = submit(c, single(), 'f').json()['request_id']
    worker.forget = True
    run_next(c)
    assert c.get(f'/api/v1/backtests/{forgotten}').json()['error'] == {'code': 'WORKER_LOST'}
    worker.forget = False
    gone = submit(c, single(), 'g').json()['request_id']
    worker.on_poll = lambda job_id, polls: setattr(worker, 'down', True)
    run_next(c)
    status = c.get(f'/api/v1/backtests/{gone}').json()
    assert status['state'] == 'FAILED' and status['error'] == {'code': 'WORKER_LOST'}
    assert len([x for x in worker.calls if x['path'] == f'/v1/jobs/{gone}']) == 1 + 3   # one answered read, then 3 unanswered
    worker.down, worker.on_poll = False, None
    worker.fail_with = {'code': 'DATA_INTEGRITY', 'message': 'price BBCA 2024: sha256 differs from the manifest'}
    failed = submit(c, single(), 'd').json()['request_id']
    run_next(c)
    status = c.get(f'/api/v1/backtests/{failed}').json()
    assert status['state'] == 'FAILED' and status['error'] == worker.fail_with and status['duration_ms'] == 55
    worker.fail_with, worker.garbage = None, True
    invalid = submit(c, single(), 'i').json()['request_id']
    run_next(c)
    assert c.get(f'/api/v1/backtests/{invalid}').json()['error'] == {'code': 'RESULT_INVALID'}
    assert db(c, 'SELECT count(*) AS n FROM edge_bff.backtest_results')[0]['n'] == 0
    # a worker that stops answering before the hand-over: three attempts, then WORKER_LOST
    worker.garbage = False
    unreachable = submit(c, single(), 'u').json()['request_id']
    worker.down = True
    run_next(c)
    assert c.get(f'/api/v1/backtests/{unreachable}').json()['error'] == {'code': 'WORKER_LOST'}
    assert len(worker.posted('/v1/jobs')) == 4 + 3


def test_busy_worker_and_a_lost_hand_over_answer_never_resubmit(app, worker):
    c = app
    worker.busy = 2
    waited = submit(c, single(), 'busy').json()['request_id']
    run_next(c)
    assert c.get(f'/api/v1/backtests/{waited}').json()['state'] == 'FINISHED' and len(worker.posted('/v1/jobs')) == 3
    worker.lose_post_answer = True
    lost = submit(c, single(), 'lost').json()['request_id']
    run_next(c)
    assert c.get(f'/api/v1/backtests/{lost}').json()['state'] == 'FINISHED'
    assert len([x for x in worker.posted('/v1/jobs') if x['body']['job_id'] == lost]) == 1   # found by its id, not sent again


def test_restart_with_an_expired_lease_fails_worker_lost_without_resubmitting(app, worker):
    c = app
    job_id = submit(c, single(), 'restart').json()['request_id']
    bt = c.app.state.backtests
    row = bt.store.claim(90)
    worker.jobs[job_id] = {'request': single(), 'context': {}, 'polls': 0, 'cancelled': False}   # handed over before the stop
    db(c, "UPDATE edge_bff.backtest_jobs SET lease_expires_at=now()-interval '1 second' WHERE request_id=%s", job_id)
    assert not bt.store.heartbeat(row, 90) and bt.store.end(row, 'FAILED', {'code': 'TIMEOUT'}) is None   # the old holder is fenced
    loop = BacktestLoop(bt.settings, bt.store, bt.worker)

    async def one_turn():
        task = asyncio.create_task(loop.run())
        for _ in range(400):
            await asyncio.sleep(0.005)
            if db(c, 'SELECT state FROM edge_bff.backtest_jobs WHERE request_id=%s', job_id)[0]['state'] != 'RUNNING':
                break
        loop.stop()
        await task
    asyncio.run(one_turn())
    status = c.get(f'/api/v1/backtests/{job_id}').json()
    assert status['state'] == 'FAILED' and status['error'] == {'code': 'WORKER_LOST'}
    assert worker.jobs[job_id]['cancelled'] and worker.posted('/v1/jobs') == []


def test_timeout_cancels_at_the_worker(app, worker):
    c = app
    worker.hang = True
    job_id = submit(c, single(), 'slow').json()['request_id']
    started = time.monotonic()
    run_next(c, dataclasses.replace(c.app.state.backtests.settings, backtest_timeout_seconds=0.3))
    assert 0.3 <= time.monotonic() - started < 10
    assert c.get(f'/api/v1/backtests/{job_id}').json()['error'] == {'code': 'TIMEOUT'}
    assert worker.jobs[job_id]['cancelled']


def test_in_process_loop_end_to_end_and_result_retention(configured, store, worker):
    loop_on = dataclasses.replace(configured, worker_enabled=True)
    with TestClient(create_app(loop_on, store, FakeOrc())) as c:
        c.headers_for = login(c)
        job_id = submit(c, single(), 'e2e').json()['request_id']
        for _ in range(2000):
            if c.get(f'/api/v1/backtests/{job_id}').json()['state'] in ('FINISHED', 'FAILED', 'CANCELLED'):
                break
            time.sleep(0.005)
        assert c.get(f'/api/v1/backtests/{job_id}').json()['state'] == 'FINISHED'
        assert c.get(f'/api/v1/backtests/{job_id}/result').json() == result_of(job_id, single())
    # results older than 30 days are deleted by the loop (once an hour, and at its start); the job stays, its result is gone
    db_url = configured.database_url
    with psycopg.connect(db_url) as conn:
        conn.execute("UPDATE edge_bff.backtest_results SET created_at=now()-interval '31 days'")
    with TestClient(create_app(loop_on, store, FakeOrc())) as c:
        c.headers_for = login(c)
        for _ in range(2000):
            with psycopg.connect(db_url) as conn:
                if not conn.execute('SELECT 1 FROM edge_bff.backtest_results').fetchone():
                    break
            time.sleep(0.005)
        r = c.get(f'/api/v1/backtests/{job_id}/result')
        assert r.status_code == 410 and r.json() == {'error': {'code': 'RESULT_EXPIRED'}}
        assert c.get(f'/api/v1/backtests/{job_id}/events?ticker=BBCA').json()['error']['code'] == 'RESULT_EXPIRED'
        assert c.get(f'/api/v1/backtests/{job_id}').json()['state'] == 'FINISHED'


def test_catalog_is_cached_and_signals_are_proxied_without_a_trial(app, worker):
    c = app
    first = c.get('/api/v1/backtests/catalog')
    assert first.status_code == 200 and first.json() == worker.catalog
    assert c.get('/api/v1/backtests/catalog').json() == worker.catalog
    assert len([x for x in worker.calls if x['path'] == '/v1/catalog']) == 1
    worker.down = True
    c.app.state.backtests.catalog['at'] -= 3600          # stale, and the worker does not answer: the last one is kept
    assert c.get('/api/v1/backtests/catalog').json() == worker.catalog
    worker.down = False
    preview = {'schema_version': 1, 'universe': 'all', 'period': {'from': '2024-01-02', 'to': '2026-10-23'}, 'entry': single()['entry']}
    r = c.post('/api/v1/backtests/signals', headers=c.headers_for, json=preview)
    assert r.status_code == 200 and r.json()['rows'][0] == {'ticker': 'BBCA', 'entry_signals': 4, 'last_signal': '2026-10-20'}
    assert worker.posted('/v1/signals')[0]['body'] == preview
    refused = c.post('/api/v1/backtests/signals', headers=c.headers_for, json={**preview, 'universe': 'sector:Nope'})
    assert refused.status_code == 422 and refused.json()['error']['field'] == 'universe'
    assert db(c, 'SELECT count(*) AS n FROM edge_bff.backtest_jobs')[0]['n'] == 0
    assert db(c, 'SELECT count(*) AS n FROM edge_bff.backtest_trials')[0]['n'] == 0


def test_feature_off_without_a_worker(settings, store, backtest_tables):
    with TestClient(create_app(settings, store, FakeOrc())) as c:
        h = login(c)
        for method, path in (('GET', '/api/v1/backtests/catalog'), ('GET', '/api/v1/backtests'),
                             ('GET', '/api/v1/backtests/bt_' + '1' * 32), ('POST', '/api/v1/backtests'),
                             ('POST', '/api/v1/backtests/signals'), ('POST', '/api/v1/backtests/bt_' + '1' * 32 + '/cancel')):
            r = c.request(method, path, headers=h, json={})
            assert r.status_code == 503 and r.json() == {'error': {'code': 'BACKTEST_DISABLED'}}, path
        assert c.app.state.backtests.loop is None


def test_session_and_csrf_are_required(app, worker):
    c = app
    job_id = submit(c, single(), 'auth').json()['request_id']
    c.cookies.clear()
    for path in ('/api/v1/backtests/catalog', '/api/v1/backtests', f'/api/v1/backtests/{job_id}',
                 f'/api/v1/backtests/{job_id}/result', f'/api/v1/backtests/{job_id}/events?ticker=BBCA'):
        assert c.get(path).status_code == 401, path
    h = login(c)
    calls = len(worker.calls)
    for path in ('/api/v1/backtests', '/api/v1/backtests/signals', f'/api/v1/backtests/{job_id}/cancel'):
        assert c.post(path, headers=ORIGIN, json=single()).status_code == 403, path                       # no CSRF token
        assert c.post(path, headers={'X-CSRF-Token': h['X-CSRF-Token']}, json=single()).status_code == 403, path   # no Origin
        assert c.post(path, headers={**h, 'X-CSRF-Token': '0' * 64}, json=single()).status_code == 403, path
    assert len(worker.calls) == calls and c.get(f'/api/v1/backtests/{job_id}').json()['state'] == 'QUEUED'
    # another owner's job is not found
    db(c, "UPDATE edge_bff.backtest_jobs SET owner_key='someone-else' WHERE request_id=%s", job_id)
    assert c.get(f'/api/v1/backtests/{job_id}').status_code == 404
    assert c.post(f'/api/v1/backtests/{job_id}/cancel', headers=h).status_code == 404
    assert c.get('/api/v1/backtests').json() == {'items': []}


def test_ready_does_not_depend_on_the_backtest_tables(app, worker, backtest_tables):
    c = app
    with psycopg.connect(backtest_tables, autocommit=True) as conn:
        conn.execute(ROLLBACK)          # the migration's own rollback block
    try:
        c.app.state.backtests.ready = False
        assert c.get('/ready').json() == {'status': 'ready'}
        r = submit(c, single(), 'nr')
        assert r.status_code == 503 and r.json() == {'error': {'code': 'BACKTEST_NOT_READY'}}
        assert c.get('/api/v1/backtests').json() == {'error': {'code': 'BACKTEST_NOT_READY'}}
        assert c.get('/api/v1/backtests/catalog').status_code == 503
        assert worker.calls == []
        assert c.get('/api/v1/conversations').status_code == 200        # the rest of EDGE is unaffected
    finally:
        with psycopg.connect(backtest_tables, autocommit=True) as conn:
            conn.execute(MIGRATION.read_text())
    assert submit(c, single(), 'nr').status_code == 202
    with psycopg.connect(backtest_tables, autocommit=True) as conn:
        with pytest.raises(psycopg.errors.RaiseException, match='backtest table exists'):
            conn.execute(MIGRATION.read_text())                          # a rerun is refused by the preflight
        conn.execute('ROLLBACK')
        grants = conn.execute("""SELECT table_name, string_agg(privilege_type, ',' ORDER BY privilege_type) AS p
            FROM information_schema.role_table_grants WHERE grantee='edge_bff_runtime' AND table_name LIKE 'backtest_%'
            GROUP BY table_name ORDER BY table_name""").fetchall()
    assert grants == [(t, 'DELETE,INSERT,SELECT,UPDATE') for t in ('backtest_jobs', 'backtest_results', 'backtest_trials')]


def test_backtest_tab_page_and_its_frame_csp(app, monkeypatch, tmp_path):
    c = app
    (tmp_path / 'assets').mkdir()
    (tmp_path / 'index.html').write_text('<!doctype html><title>Market Lab Backtest</title>')
    (tmp_path / 'assets' / 'index-abc123.js').write_text('void 0')
    monkeypatch.setattr(main, 'BACKTEST_APP', tmp_path)
    page = c.get('/backtest')
    assert page.status_code == 200 and 'EDGE' in page.text and 'function BacktestPage' in page.text and '"/backtest-app/"' in page.text
    assert page.headers['content-security-policy'] == c.get('/terminal').headers['content-security-policy']   # EDGE's own policy
    frame = c.get('/backtest-app/')
    assert frame.status_code == 200 and 'Market Lab Backtest' in frame.text
    csp = frame.headers['content-security-policy']
    assert csp == main.TERMINAL_CSP and "script-src 'self';" in csp and 'unsafe-eval' not in csp
    assert "connect-src 'self' https://*.t3.storageapi.dev;" in csp and "frame-ancestors 'self'" in csp
    asset = c.get('/backtest-app/assets/index-abc123.js')
    assert asset.status_code == 200 and 'immutable' in asset.headers['cache-control'] and asset.headers['content-security-policy'] == csp
    assert c.get('/backtest-app/assets/..%2F..%2Fapp%2Fmain.py').status_code == 404
    assert c.get('/backtest-app/assets/missing.js').status_code == 404
    monkeypatch.setattr(main, 'BACKTEST_APP', tmp_path / 'not-built')
    assert c.get('/backtest-app/').status_code == 404


def test_backtest_settings_are_paired_strong_private_and_bounded(settings):
    on = dict(backtest_worker_url='http://backtest-worker.railway.internal:8080', backtest_worker_key=KEY, backtest_timeout_seconds=600)
    dataclasses.replace(settings, **on).validate()
    for bad, message in (({'backtest_worker_key': ''}, 'set together'), ({'backtest_worker_key': 'short'}, 'at least 32'),
                         ({'backtest_timeout_seconds': 0}, 'BACKTEST_TIMEOUT_SECONDS'),
                         ({'backtest_queued_per_owner': 0}, 'BACKTEST_QUEUED_PER_OWNER')):
        with pytest.raises(ValueError, match=message):
            dataclasses.replace(settings, **{**on, **bad}).validate()
    deployed = dataclasses.replace(settings, environment='dev', orc_url='http://market-ai-orc.railway.internal:8080',
                                   database_url='postgresql://edge_bff_login@db.internal/railway',
                                   origin='https://edge.example', secure_cookie=True, **on)
    deployed.validate()
    with pytest.raises(ValueError, match='BACKTEST_WORKER_URL'):
        dataclasses.replace(deployed, backtest_worker_url='https://backtest-worker.up.railway.app').validate()
    dataclasses.replace(settings).validate()          # off: nothing required


def test_split_result_refuses_what_the_contract_does_not_carry():
    request = single()
    good = result_of('bt_' + '2' * 32, request)
    split = split_result(good, 'BBCA')
    assert [name for name, _ in split['parts']] == ['core', 'events:BBCA'] and len(split['trials']) == 2
    for broken in ({**good, 'schema_version': 2}, {**good, 'events': {**good['events'], 'exits': []}},
                   {**good, 'meta': {**good['meta'], 'data_version': 'not-a-hash'}},
                   {**good, 'meta': {**good['meta'], 'tickers': ['bad ticker']}},
                   {**good, 'meta': {**good['meta'], 'trials': {'variants': [{'variant_hash': 'x', 'sharpe_daily': 1, 'kind': 'run'}]}}}):
        with pytest.raises(ValueError):
            split_result(broken)
    without_sharpe = {**good, 'meta': {**good['meta'], 'trials': {**good['meta']['trials'], 'variants': [
        {'variant_hash': sha('v'), 'sharpe_daily': None, 'kind': 'run'}]}}}
    assert split_result(without_sharpe)['trials'] == []     # logged, never counted as 0


def test_backtest_tab_in_the_browser(configured, store, worker, monkeypatch, tmp_path):
    """The real page in Chromium: the Backtest tab next to Terminal opens /backtest with the frame, and the framed page
    (a stand-in for the built one, script from its own assets as the CSP requires) reads the catalog with the EDGE
    session; a reload keeps the tab."""
    playwright = pytest.importorskip('playwright.sync_api')
    (tmp_path / 'assets').mkdir()
    (tmp_path / 'index.html').write_text('<!doctype html><title>Backtest frame</title><p id="out">loading</p>'
                                         '<script src="/backtest-app/assets/probe-1.js"></script>')
    (tmp_path / 'assets' / 'probe-1.js').write_text(
        "fetch('/api/v1/backtests/catalog').then(r => r.json()).then(c => { document.getElementById('out').textContent = "
        "'data through ' + c.data_through }, e => { document.getElementById('out').textContent = 'failed ' + e })")
    monkeypatch.setattr(main, 'BACKTEST_APP', tmp_path)
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    local = dataclasses.replace(configured, origin=f'http://127.0.0.1:{sock.getsockname()[1]}')
    server = uvicorn.Server(uvicorn.Config(create_app(local, store, FakeOrc()), log_level='critical', access_log=False))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.02)
    assert server.started
    try:
        with playwright.sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.environ.get('EDGE_TEST_CHROMIUM', '/usr/bin/chromium'),
                                         headless=True, args=['--no-sandbox'])
            try:
                page = browser.new_page()
                page.route('https://fonts.*/*', lambda route: route.abort())
                errors = []
                page.on('console', lambda m: m.type == 'error' and errors.append(m.text))
                page.goto(local.origin + '/monitor')
                page.locator('#auth-login').fill('owner')
                page.locator('#auth-password').fill('local-test-password')
                page.get_by_role('button', name='Sign In', exact=True).click()
                tabs = page.locator('.topbar nav button')
                tabs.first.wait_for()
                assert tabs.all_inner_texts() == ['Monitor', 'Terminal', 'Backtest']
                page.locator('.topbar nav button.nav-backtest').click()
                page.wait_for_url(local.origin + '/backtest')
                assert page.locator('.topbar nav button.nav-backtest').get_attribute('aria-current') == 'page'
                frame = page.frame_locator('iframe.terminal-frame')
                frame.get_by_text('data through 2026-10-23', exact=True).wait_for()
                assert page.locator('iframe.terminal-frame').get_attribute('title') == 'Backtest'
                page.reload()
                page.frame_locator('iframe.terminal-frame').get_by_text('data through 2026-10-23', exact=True).wait_for()
                page.locator('.topbar nav button.nav-terminal').click()
                page.wait_for_url(local.origin + '/terminal')
                assert page.locator('iframe.terminal-frame').get_attribute('src').endswith('/terminal-app/')
                assert not [e for e in errors if 'Content Security Policy' in e]
            finally:
                browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
    assert [c['path'] for c in worker.calls] == ['/v1/catalog']     # the reload was served from the catalog cache
