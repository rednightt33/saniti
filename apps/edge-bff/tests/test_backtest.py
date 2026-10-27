"""EDGE backtest in edge-bff (CONTRACT.md sections 8-11): the /api/v1/backtests routes, the job tables (migration
20261026_005, applied by conftest with the others), the queue loop against a fake backtest worker that is a real
local HTTP server speaking the worker's private API, and the /backtest page with its frame's CSP.

The fake worker's results are small synthetic BacktestResult-shaped documents built from the request (test data only);
edge-bff does not interpret them beyond meta versions, meta.trials and events, which is what is checked here."""
import asyncio
import concurrent.futures
import dataclasses
import gzip
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import posixpath
import re
import select
import socket
import threading
import time
import zlib

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient
import uvicorn

from app import backtest, main
from app.backtest import BacktestLoop, ResultTooLarge, WorkerClient, WorkerTimeout, WorkerUnavailable, loads, split_result
from app.main import create_app
from conftest import FakeOrc

ORIGIN = {'Origin': 'http://testserver'}
KEY = 'w' * 40
MIGRATION = Path(__file__).resolve().parents[3] / 'database/migrations/20261026_005_edge_bff_backtest.sql'
ERROR_COMMENT = Path(__file__).resolve().parents[3] / 'database/migrations/20261027_005_edge_bff_backtest_error_comment.sql'
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


PICKED = ['BMRI', 'BBCA', 'BBRI']     # a portfolio's stocks in the order they were picked, which is not ticker order


def portfolio(tickers=PICKED, **change):
    request = {**single(), 'mode': 'portfolio', 'portfolio': {'tickers': list(tickers), 'max_positions': 3, 'rank_by': 'adx',
                                                              'min_avg_value_20d_idr': 0}}
    del request['single']
    request.update(change)
    return request


def preview_of(tickers=('BMRI', 'BBCA'), **change):
    """A SignalsPreviewRequest (contract.ts) of these picked stocks."""
    return {'schema_version': 1, 'tickers': list(tickers), 'period': {'from': '2024-01-02', 'to': '2026-10-23'},
            'entry': single()['entry'], **change}


def tickers_of(request):
    """The run's tickers as the worker gives them: the single ticker, or the picked stocks in ticker order (PF3)."""
    return [request['single']['ticker']] if request['mode'] == 'single' else sorted(request['portfolio']['tickers'])


def lineage_of(request):
    """The fake worker's strategy line: the mode and the single ticker; a portfolio's picked stocks are in its variant,
    not in its line (PF4; the real one is core/hash.ts lineageKey)."""
    return sha(json.dumps([request['mode'], (request.get('single') or {}).get('ticker')]))


def variant_of(request):
    """The fake worker's variant: the request without robustness, the picked stocks as a set (PF3: their order is no
    part of the request; the real one is core/hash.ts variantHash)."""
    if request['mode'] == 'portfolio':
        request = {**request, 'portfolio': {**request['portfolio'], 'tickers': tickers_of(request)}}
    return sha(json.dumps({k: v for k, v in request.items() if k != 'robustness'}, sort_keys=True))


def result_of(job_id, request, sharpe=0.1 + 0.2):
    """A BacktestResult-shaped document for the request: two condition tracks and an exit track per ticker, numbers
    that need exact round trips, the run's variant (daily Sharpe `sharpe`) and two sensitivity cells in meta.trials,
    the cells not in hash order (edge-bff keeps the run's order)."""
    tickers = tickers_of(request)
    variant = variant_of(request)
    cells = sorted((sha(f'cell{k}' + variant) for k in (1, 2)), reverse=True)
    return {
        'schema_version': 1,
        'meta': {'engine_version': 'engine-test-1', 'registry_version': 'registry-test-1', 'data_version': sha('data'),
                 'request_hash': sha('rh' + job_id), 'lineage_key': lineage_of(request), 'seed': 7, 'duration_ms': 1234,
                 'mode': request['mode'], 'tickers': tickers, 'benchmark': {'kind': 'ihsg', 'ticker': 'IHSG'},
                 'data_through': '2026-10-23', 'warnings': [{'code': 'TICK_NOT_MODELLED', 'message': 'Tick sizes are not modelled'}],
                 'trials': {'prior': 0, 'this_run': 3, 'total': 3,
                            'variants': [{'variant_hash': variant, 'sharpe_daily': sharpe, 'kind': 'run'},
                                         {'variant_hash': cells[0], 'sharpe_daily': -0.012345678901234567, 'kind': 'sensitivity'},
                                         {'variant_hash': cells[1], 'sharpe_daily': 1e-300, 'kind': 'sensitivity'}]}},
        'dates': ['2026-10-21', '2026-10-22', '2026-10-23'], 'equity': [1e8, 100123456.789, 99999999.99],
        'daily_returns': [0.00123456789, -0.0012345], 'trades': [{'trade_id': f'{tickers[0]}-2026-10-22-1', 'ticker': tickers[0]}],
        'robustness': {'monte_carlo': None, 'sensitivity': None, 'deflated': {'sr0': None, 'dsr': None, 'trials': 3, 'sharpe_variance_from': 'trials'}},
        'events': {'conditions': [{'condition_id': c, 'ticker': t, 'track': {'on': [i], 'runs': [i, i + 1]}}
                                  for i, t in enumerate(tickers) for c in ('c1', 'x1')],
                   'entries': {t: {'on': [1], 'runs': [1, 1]} for t in tickers},
                   'exits': {t: {'on': [2], 'runs': [2, 2]} for t in tickers},
                   'skipped': [{'ticker': tickers[0], 'signal_date': '2026-10-21', 'signal_event': 0, 'reason': 'no_slot'}]}}


class FakeWorker:
    """The backtest worker's private API (CONTRACT.md section 8, the lead's route list) on 127.0.0.1. Jobs finish after
    `finish_after` status reads; switches make it refuse, forget, hang, fail, wait, time out or stop answering. A finished
    job's result is served as often as it is asked for (the worker keeps it until its next job starts)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.calls, self.jobs = [], {}
        self.finish_after = 2
        self.hang = False              # jobs never finish
        self.down = False              # every answer is 503
        self.forget = False            # status reads answer 404 UNKNOWN_JOB
        self.busy = 0                  # the next n POST /v1/jobs answer 409 BUSY (another job)
        self.lose_post_answer = False  # POST /v1/jobs takes the job but answers 503 (an answer lost on the way)
        self.unstarted = 0             # the next n POST /v1/jobs answer 503 and take no job (review V1: their caller left
                                       # while the worker read the reference lists)
        self.fail_with = None          # jobs end FAILED with this error
        self.refuse_with = None        # POST /v1/jobs answers 422 with this error (a refusal at hand-over)
        self.garbage = False           # the result is not JSON
        self.result_gone = False       # the result answers 410 RESULT_GONE (a newer job started there and replaced it)
        self.validate_error = None     # (status, error) for /v1/validate
        self.timeout_paths = set()     # these routes answer the worker's 504 TIMEOUT ...
        self.timeout_after = 0.0       # ... after this many seconds
        self.timeout_error = True      # False: that 504 carries no error body (not the worker's own answer)
        self.delay = {}                # path -> seconds the route waits before its usual answer
        self.abandoned = []            # routes whose caller closed the connection while they waited (then not answered)
        self.run_sharpe = 0.1 + 0.2    # the daily Sharpe of the run's own variant in the results
        self.on_poll = None            # hook(job_id, polls) on each status read
        self.catalog = {'schema_version': 1, 'engine_version': 'engine-test-1', 'registry_version': 'registry-test-1',
                        'data_through': '2026-10-23', 'first_date': '2019-01-02',
                        # PF6 (test values): each ticker's groups, the groupings of the reference file's columns
                        # after ticker, name and type (sector, industry), stocks counted, an index not
                        'tickers': [{'ticker': 'BBCA', 'name': 'Bank Central Asia', 'type': 'stock',
                                     'groups': {'sector': 'Finance', 'industry': 'Banks'}},
                                    {'ticker': 'TLKM', 'name': 'Telkom Indonesia', 'type': 'stock',
                                     'groups': {'sector': 'Infrastructure', 'industry': None}},
                                    {'ticker': 'IHSG', 'name': 'Composite', 'type': 'index', 'groups': {'sector': None, 'industry': None}}],
                        'groupings': [{'key': 'sector', 'values': [{'value': 'Finance', 'tickers': 1}, {'value': 'Infrastructure', 'tickers': 1}],
                                       'unclassified': 0},
                                      {'key': 'industry', 'values': [{'value': 'Banks', 'tickers': 1}], 'unclassified': 1}],
                        'flow': {'available': False, 'reason': 'not verified', 'brokers': [], 'data_through': None},
                        'limits': {'max_positions': 12, 'window_bars': {'min': 1, 'max': 20}, 'monte_carlo_runs': 1000,
                                   'max_portfolio_tickers': 12, 'max_download_bytes': 1, 'max_broker_rows': 1,
                                   'timeout_seconds': 600, 'queued_per_owner': 3, 'max_conditions': 20}}
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

            def held(self, seconds):
                """Waits, and stops when the caller closes its connection first (the worker's preview does that):
                False then, the route not answered."""
                end = time.monotonic() + seconds
                while (left := end - time.monotonic()) > 0:
                    ready, _, _ = select.select([self.connection], [], [], min(left, 0.02))
                    if ready and self.connection.recv(1, socket.MSG_PEEK) == b'':
                        with worker.lock:
                            worker.abandoned.append(self.path)
                        return False
                return True

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
                if self.path in worker.delay and not self.held(worker.delay[self.path]):
                    return
                if self.path in worker.timeout_paths:
                    if not self.held(worker.timeout_after):
                        return
                    if not worker.timeout_error:
                        return self.answer(504, raw=b'<html>Gateway Timeout</html>')
                    return self.answer(504, {'error': {'code': 'TIMEOUT', 'message': f'{self.path} took longer than 600 s.'}})
                route = (method, self.path)
                if route == ('GET', '/v1/catalog'):
                    return self.answer(200, worker.catalog)
                if route == ('POST', '/v1/validate'):
                    if worker.validate_error:
                        return self.answer(worker.validate_error[0], {'error': worker.validate_error[1]})
                    request = body['request']
                    return self.answer(200, {'ok': True, 'lineage_key': lineage_of(request), 'variant_hash': variant_of(request),
                                             'tickers': tickers_of(request)})
                if route == ('POST', '/v1/signals'):
                    for k, t in enumerate(body.get('tickers') or []):
                        if t == 'NOPE':           # the worker's refusal of a picked stock it does not publish (validate.ts)
                            return self.answer(422, {'error': {'code': 'UNKNOWN_TICKER', 'field': f'tickers[{k}]',
                                                               'message': 'NOPE is not a published stock.'}})
                    return self.answer(200, {'data_version': sha('data'), 'rows': [{'ticker': 'BBCA', 'entry_signals': 4, 'last_signal': '2026-10-20'}]})
                if route == ('POST', '/v1/jobs'):
                    with worker.lock:
                        if worker.unstarted:
                            worker.unstarted -= 1
                            return self.answer(503, {'error': {'code': 'LOST'}})
                        if worker.busy:
                            worker.busy -= 1
                            return self.answer(409, {'error': {'code': 'BUSY'}})
                        if worker.refuse_with:
                            return self.answer(422, {'error': worker.refuse_with})
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
                        # FINISHED: the worker's final progress (server.ts sets finalizing 1/1 when the result is packed)
                        progress = ({'phase': 'finalizing', 'done': 1, 'total': 1} if state == 'FINISHED' else
                                    {'phase': 'backtest', 'done': min(job['polls'], worker.finish_after), 'total': worker.finish_after})
                        return self.answer(200, {'request_id': job_id, 'state': state, 'progress': progress,
                                                 'error': worker.fail_with if state == 'FAILED' else None,
                                                 'created_at': '2026-10-26T00:00:00Z', 'started_at': '2026-10-26T00:00:00Z',
                                                 'finished_at': None, 'duration_ms': 55 if state in ('FAILED', 'CANCELLED') else None,
                                                 'result_bytes': None})
                    if method == 'GET' and parts[4:] == ['result']:
                        if worker.result_gone:
                            return self.answer(410, {'error': {'code': 'RESULT_GONE', 'message': 'A newer backtest has started on the worker; this result is no longer kept.'}})
                        if worker.garbage:
                            return self.answer(200, raw=b'{"schema_version": 1, "meta": NaN}', gz=True)
                        return self.answer(200, raw=json.dumps(result_of(job_id, job['request'], worker.run_sharpe)).encode(), gz=True)
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
    """The migration on the disposable database: conftest applies it with the other edge_bff migrations; on a database
    without it, it is applied here and taken out again with its rollback block after this module."""
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
    # test values: the fake worker answers at once and its results are a few KB
    return dataclasses.replace(settings, backtest_worker_url=worker.url, backtest_worker_key=KEY, backtest_timeout_seconds=30,
                               backtest_max_result_bytes=2 ** 20)


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
    # the ended job reports the worker's final progress, not the one of the last poll while it ran
    assert status['progress'] == {'phase': 'finalizing', 'done': 1, 'total': 1}
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
    assert core['meta']['tickers'] == ['BBCA', 'BBRI', 'BMRI']           # the worker's ticker order, whatever the picked order
    for ticker in ('BBCA', 'BBRI', 'BMRI'):
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


def test_the_picked_stocks_in_another_order_are_the_same_submission(app, worker):
    """PF3: the order of a portfolio's picked stocks is no part of the request (the worker sorts them before it hashes,
    records the lineage or runs), so the same client_request_id with the same stocks in another order returns the job it
    made, also when the two arrive together (BacktestStore.submit); another set under it, a stock repeated included, is
    another request (409 SUBMISSION_CONFLICT). The job keeps the request as it was first sent."""
    c = app
    first = submit(c, portfolio(), 'picked')
    assert first.status_code == 202 and first.json()['created'] is True
    job_id = first.json()['request_id']
    for order in (['BBCA', 'BBRI', 'BMRI'], ['BBRI', 'BMRI', 'BBCA']):
        again = submit(c, portfolio(order), 'picked')
        assert again.status_code == 202 and again.json() == {'request_id': job_id, 'state': 'QUEUED', 'created': False}, order
    store = c.app.state.backtests.store
    row, created = store.submit(c.app.state.backtests.settings.owner, 'picked', portfolio(['BBRI', 'BBCA', 'BMRI']),
                                lineage_of(portfolio()), variant_of(portfolio()), 3)
    assert (row['request_id'], created) == (job_id, False)
    for other in (['BBCA', 'BBRI'], ['BBCA', 'BBRI', 'BMRI', 'TLKM'], ['BBCA', 'BBRI', 'BBRI'], ['BBCA', 'BBRI', 'BMRI', 'BMRI']):
        r = submit(c, portfolio(other), 'picked')
        assert r.status_code == 409 and r.json() == {'error': {'code': 'SUBMISSION_CONFLICT'}}, other
    moved = portfolio(['BBCA', 'BBRI', 'BMRI'])
    moved['portfolio']['max_positions'] = 4
    assert submit(c, moved, 'picked').status_code == 409                     # the order aside, another request
    with pytest.raises(backtest.StoreError, match='SUBMISSION_CONFLICT'):
        store.submit(c.app.state.backtests.settings.owner, 'picked', portfolio(['BBCA', 'BBRI']), lineage_of(portfolio()),
                     variant_of(portfolio()), 3)
    assert len(worker.posted('/v1/validate')) == 1 and len(db(c, 'SELECT 1 FROM edge_bff.backtest_jobs')) == 1
    run_next(c)
    assert handed(worker, job_id)['request'] == portfolio()                 # as first sent, the picked order kept
    assert c.get('/api/v1/backtests').json()['items'][0]['request'] == portfolio()


def test_a_resubmission_with_a_stock_utf8_cannot_encode_is_no_service_error(app, worker):
    """Review PF3-reg: same_request sorted the picked stocks by their UTF-8 JSON, which a lone surrogate has none of, so
    a resubmission under an existing client_request_id with such a stock answered 503 SERVICE_UNAVAILABLE (409
    SUBMISSION_CONFLICT before PF3). The body is 422 INVALID_INPUT (loads, review V2b); same_request, in the route and in
    BacktestStore.submit, compares such a request without raising: another request, SUBMISSION_CONFLICT."""
    c = app
    assert submit(c, portfolio(), 'lone').status_code == 202
    raw = json.dumps({**portfolio(['BBCA', 'BBRI', '\ud800']), 'client_request_id': 'lone'}).encode()   # as "\ud800"
    r = c.post('/api/v1/backtests', headers={**c.headers_for, 'content-type': 'application/json'}, content=raw)
    assert (r.status_code, r.json()) == (422, {'error': {'code': 'INVALID_INPUT'}})
    bt = c.app.state.backtests
    with pytest.raises(backtest.StoreError, match='SUBMISSION_CONFLICT'):
        bt.store.submit(bt.settings.owner, 'lone', portfolio(['BBCA', 'BBRI', '\ud800']), lineage_of(portfolio()),
                        variant_of(portfolio()), 3)
    assert not backtest.same_request(portfolio(), portfolio(['\ud800', 'BBCA', 'BBRI']))
    assert backtest.same_request(portfolio(['\ud800', 'BBCA']), portfolio(['BBCA', '\ud800']))   # any order still
    assert len(worker.posted('/v1/validate')) == 1 and len(db(c, 'SELECT 1 FROM edge_bff.backtest_jobs')) == 1


def test_a_body_nested_deeper_than_the_parser_takes_is_invalid_input(app, worker):
    """CONTRACT section 11: a body edge-bff cannot read as JSON is a validation error (422 INVALID_INPUT), also when it
    nests deeper than the parser's recursion limit (RecursionError), within the 128 KiB body limit."""
    c = app
    deep = b'{"x":' + b'[' * 60000 + b']' * 60000 + b'}'
    assert len(deep) < 131072
    for path in ('/api/v1/backtests', '/api/v1/backtests/signals'):
        r = c.post(path, headers={**c.headers_for, 'content-type': 'application/json'}, content=deep)
        assert r.status_code == 422 and r.json() == {'error': {'code': 'INVALID_INPUT'}}, path
    assert worker.calls == []
    with pytest.raises(ValueError):          # every caller of loads (a worker answer too) refuses it as malformed JSON
        loads(deep)


def test_a_number_beyond_a_double_is_invalid_input_and_reaches_no_worker(configured, store, worker):
    """Review V2, CONTRACT section 11: 1e400 is JSON text but no double, as NaN and Infinity are not. It used to load as
    inf, which the relay cannot send (httpx's JSON refuses it), so both routes answered 503 SERVICE_UNAVAILABLE; it is
    422 INVALID_INPUT, as every body edge-bff cannot carry, and reaches no worker. So is an integer beyond a double
    (review V2a): 1 and 400 zeros loaded as a Python int and went on, and the worker's JSON.parse reads it as Infinity,
    as it reads 1e400. A double's own extremes pass."""
    # The least integer that rounds to Infinity, in Python's float() as in JSON.parse: half way between the largest
    # double (2^1024 - 2^971) and 2^1024, which rounds to the even 2^1024.
    least = 2 ** 1024 - 2 ** 970
    with TestClient(create_app(configured, store, FakeOrc()), raise_server_exceptions=False) as c:
        headers = {**login(c), 'content-type': 'application/json'}
        for path in ('/api/v1/backtests', '/api/v1/backtests/signals'):
            for raw in (b'{"tickers":["BBCA"],"x":1e400}', b'{"x":[-1e999]}', b'{"x":{"y":0.5E+309}}',
                        b'{"tickers":["BBCA"],"x":1' + b'0' * 400 + b'}', b'{"x":[-%d]}' % least,
                        b'{"portfolio":{"min_avg_value_20d_idr":%d}}' % least):
                r = c.post(path, headers=headers, content=raw)
                assert (r.status_code, r.json()) == (422, {'error': {'code': 'INVALID_INPUT'}}), (path, raw)
        assert worker.calls == []
        edges = b'{"tickers":["BBCA"],"x":[1.7976931348623157e308,-5e-324,%d,-%d]}' % (least - 1, least - 1)
        assert c.post('/api/v1/backtests/signals', headers=headers, content=edges).status_code == 200
        assert worker.posted('/v1/signals')[0]['body'] == loads(edges)
    for raw in (b'1e400', b'-1e999', b'[1E400]', b'1' + b'0' * 400, b'[-%d]' % least):   # every caller of loads (a
        with pytest.raises(ValueError):                                                    # worker answer too) refuses it
            loads(raw)


def test_a_string_utf8_cannot_encode_is_invalid_input_and_reaches_no_worker(configured, store, worker):
    """Review V2b, CONTRACT section 11: a lone UTF-16 surrogate ("\\ud800", or the three bytes that would encode it,
    which Python's json reads as well) is JSON text but no string UTF-8 can encode, so the relay cannot send it (httpx's
    JSON refuses it): both routes answered 503 SERVICE_UNAVAILABLE. In a value or a key it is 422 INVALID_INPUT, as
    every body edge-bff cannot carry, and reaches no worker. A surrogate pair (one character beyond the BMP) passes."""
    with TestClient(create_app(configured, store, FakeOrc()), raise_server_exceptions=False) as c:
        headers = {**login(c), 'content-type': 'application/json'}
        for path in ('/api/v1/backtests', '/api/v1/backtests/signals'):
            for raw in (rb'{"tickers":["BBCA"],"x":"\ud800"}', rb'{"x":["a\udfffb"]}', rb'{"x":"\ud800\u0041"}',
                        rb'{"\udbff":1}', b'{"x":"\xed\xa0\x80"}', rb'{"portfolio":{"tickers":["BBCA","\ud800"]}}'):
                r = c.post(path, headers=headers, content=raw)
                assert (r.status_code, r.json()) == (422, {'error': {'code': 'INVALID_INPUT'}}), (path, raw)
        assert worker.calls == []
        pair = rb'{"tickers":["BBCA"],"x":"\ud83d\ude00"}'
        assert c.post('/api/v1/backtests/signals', headers=headers, content=pair).status_code == 200
        assert worker.posted('/v1/signals')[0]['body'] == loads(pair) == {'tickers': ['BBCA'], 'x': '\U0001f600'}
    for raw in (rb'"\ud800"', rb'["\udc00"]', b'"\xed\xb0\x80"'):   # every caller of loads (a worker answer too) refuses it
        with pytest.raises(ValueError):
            loads(raw)


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


def test_client_request_id_stays_here_and_every_other_key_reaches_the_worker_as_sent(app, worker):
    c = app
    sent = {**single(), 'extra': {'list': [1, 2.5, None, True, 'Rp ✓'], 'big': 12345678901234567890, 'tiny': 5e-324,
                                  'sum': 0.1 + 0.2, 'empty': {}}}
    job_id = submit(c, sent, 'strip-1').json()['request_id']
    assert worker.posted('/v1/validate')[0]['body'] == {'request': sent}       # sent without client_request_id
    run_next(c)
    assert handed(worker, job_id)['request'] == sent                           # the stored request, as sent
    assert c.get('/api/v1/backtests').json()['items'][0]['request'] == sent
    # an explicit null key is taken out too (a new job under a generated key)
    r = c.post('/api/v1/backtests', headers=c.headers_for, json={**single(), 'client_request_id': None})
    assert r.status_code == 202 and worker.posted('/v1/validate')[1]['body'] == {'request': single()}
    assert all('client_request_id' not in json.dumps(x['body']) for x in worker.calls if x['body'])


def test_a_worker_timeout_of_a_relayed_call_is_its_504(app, worker):
    """The worker's 504 TIMEOUT for the catalog, a validation or a preview reaches the page as it gave it; it is
    awaited past edge-bff's own BACKTEST_TIMEOUT_SECONDS (0.3 s here, the worker answering at 0.6 s)."""
    c = app
    bt = c.app.state.backtests
    bt.settings = dataclasses.replace(bt.settings, backtest_timeout_seconds=0.3)
    preview = preview_of()
    calls = {'/v1/catalog': lambda: c.get('/api/v1/backtests/catalog'), '/v1/validate': lambda: submit(c, single(), 'slow'),
             '/v1/signals': lambda: c.post('/api/v1/backtests/signals', headers=c.headers_for, json=preview)}
    worker.timeout_paths, worker.timeout_after = set(calls), 0.6
    for path, call in calls.items():
        r = call()
        assert r.status_code == 504 and r.json() == {'error': {'code': 'TIMEOUT', 'message': f'{path} took longer than 600 s.'}}, path
    assert db(c, 'SELECT count(*) AS n FROM edge_bff.backtest_jobs')[0]['n'] == 0
    # a 504 that is not the worker's own answer (no error body) is the worker unavailable, as every other 5xx
    worker.timeout_after, worker.timeout_error = 0.0, False
    for path, call in calls.items():
        assert call().json() == {'error': {'code': 'BACKTEST_UNAVAILABLE'}}, path
    # the catalog the page already has is kept through a timeout, as through any other failure
    worker.timeout_paths = set()
    assert c.get('/api/v1/backtests/catalog').status_code == 200
    worker.timeout_paths, worker.timeout_error = {'/v1/catalog'}, True
    bt.catalog['at'] -= 3600
    assert c.get('/api/v1/backtests/catalog').json() == worker.catalog
    # the loop's hand-over is no relayed call: a 504 there is an unanswered POST (three, then WORKER_LOST, as now)
    job_id = submit(c, single(), 'handover').json()['request_id']
    worker.timeout_paths = {'/v1/jobs'}
    run_next(c, dataclasses.replace(bt.settings, backtest_timeout_seconds=30))
    assert c.get(f'/api/v1/backtests/{job_id}').json()['error'] == {'code': 'WORKER_LOST'}
    assert len(worker.posted('/v1/jobs')) == 3


LOST_CONNECTION = 'connection to postgresql://edge_bff_login:secret@db lost'


def logged(caplog, event):
    return [json.loads(r.getMessage()) for r in caplog.records if f'"{event}"' in r.getMessage()]


def test_a_failed_store_is_stored_again_until_the_deadline(app, worker, monkeypatch, caplog):
    """A store that failed in a way a retry may mend (OperationalError: one transaction, nothing kept) keeps the
    fetched result and stores it again at every poll until the job's deadline (BACKTEST_TIMEOUT_SECONDS): a database
    failure is no unanswered worker call, so it is not counted in WORKER_RETRIES, and the result is fetched once.
    Past the deadline the job ends FAILED RESULT_NOT_STORED (the dev E2E 2026-10-27: three store failures in a row
    ended a computed job WORKER_LOST in 4 s)."""
    c = app
    bt = c.app.state.backtests
    store = bt.store
    real, failed = store.finish, []
    def failing(times):
        def finish(row, split):
            if len(failed) < times:
                failed.append(row['request_id'])
                raise psycopg.OperationalError(LOST_CONNECTION)
            return real(row, split)
        return finish
    fetches = lambda job_id: len([x for x in worker.calls if x['path'] == f'/v1/jobs/{job_id}/result'])
    # more failures in a row than WORKER_RETRIES, then a store that works: FINISHED, the result fetched once
    monkeypatch.setattr(store, 'finish', failing(backtest.WORKER_RETRIES + 2))
    job_id = submit(c, single(), 'store-retried').json()['request_id']
    run_next(c)
    assert failed == [job_id] * (backtest.WORKER_RETRIES + 2)
    assert c.get(f'/api/v1/backtests/{job_id}').json()['state'] == 'FINISHED' and fetches(job_id) == 1
    assert c.get(f'/api/v1/backtests/{job_id}/result').json() == result_of(job_id, single())
    # a store that never works: RESULT_NOT_STORED at the deadline, nothing stored, the finished job not cancelled
    def never(row, split):
        raise psycopg.OperationalError(LOST_CONNECTION)
    monkeypatch.setattr(store, 'finish', never)
    lost = submit(c, single(), 'store-never').json()['request_id']
    run_next(c, dataclasses.replace(bt.settings, backtest_timeout_seconds=2))
    status = c.get(f'/api/v1/backtests/{lost}').json()
    assert status['state'] == 'FAILED' and status['error'] == backtest.NOT_STORED
    assert fetches(lost) == 1 and not worker.posted(f'/v1/jobs/{lost}/cancel')
    assert db(c, 'SELECT count(*) AS n FROM edge_bff.backtest_results WHERE request_id=%s', lost)[0]['n'] == 0
    assert db(c, 'SELECT count(*) AS n FROM edge_bff.backtest_trials WHERE request_id=%s', lost)[0]['n'] == 0
    # each failure is logged with what tells the failures apart, never the credentials. The detail is failure_of's
    # for the loop's own database URL (its password is redacted wherever it occurs, so the exact text depends on the
    # test database's URL; failure_of itself is checked with a fixed URL below)
    found = logged(caplog, 'backtest_result_store_failed')
    expected = backtest.failure_of(psycopg.OperationalError(LOST_CONNECTION), store.store.url)
    assert found and all(e == {'event': 'backtest_result_store_failed', 'request_id': e['request_id'], **expected}
                         for e in found)
    assert all('edge_bff_login' not in e.get('detail', '') for e in found) and 'secret' not in caplog.text


def test_a_store_no_retry_mends_ends_the_job_at_once(app, worker, monkeypatch, caplog):
    """A store that failed in a way no retry mends (any error but OperationalError: the data, an integrity or schema
    error, a bug) ends the job FAILED RESULT_NOT_STORED at the first failure, well before the deadline, and logs a
    server error by its SQLSTATE only (its text carries the row)."""
    c = app
    store = c.app.state.backtests.store
    calls = []
    def broken(row, split):
        calls.append(row['request_id'])
        raise psycopg.errors.CheckViolation('new row violates check constraint\nDETAIL:  Failing row contains (owner-7)')
    monkeypatch.setattr(store, 'finish', broken)
    job_id = submit(c, single(), 'store-broken').json()['request_id']
    started = time.monotonic()
    run_next(c, dataclasses.replace(c.app.state.backtests.settings, backtest_timeout_seconds=30))
    assert time.monotonic() - started < 10 and calls == [job_id]
    assert c.get(f'/api/v1/backtests/{job_id}').json()['error'] == backtest.NOT_STORED
    assert logged(caplog, 'backtest_result_store_failed')[-1] == {
        'event': 'backtest_result_store_failed', 'request_id': job_id, 'error': 'psycopg.errors.CheckViolation',
        'sqlstate': '23514'}
    assert 'owner-7' not in caplog.text


def test_a_database_failure_around_a_job_is_tried_again(app, worker, monkeypatch, caplog):
    """Every database call of the loop around a job, not only the result's store, that fails in a way a retry may
    mend is made again at the next poll or beat and not counted as an unanswered worker call: the hand-over's job read
    and prior trials, the follower's job read and progress, the heartbeat, more failures of each than WORKER_RETRIES,
    and the job still finishes, handed over once; the end after a worker's refusal is made again the same way, so the
    job keeps the worker's error."""
    c = app
    bt = c.app.state.backtests
    store = bt.store
    many = backtest.WORKER_RETRIES + 1
    def flaky(name, times):
        """the first `times` calls fail before the worker has the job (the hand-over), and again after (the follower)"""
        real, n = getattr(store, name), {'dispatch': 0, 'follow': 0}
        def call(*args):
            phase = 'follow' if worker.jobs else 'dispatch'
            n[phase] += 1
            if n[phase] <= times:
                raise psycopg.OperationalError('consuming input failed: server closed the connection unexpectedly')
            return real(*args)
        monkeypatch.setattr(store, name, call)
    for name in ('current', 'prior_trials', 'progress', 'heartbeat'):
        flaky(name, many)
    worker.finish_after = 3 * many
    job_id = submit(c, single(), 'db-flaky').json()['request_id']
    run_next(c, dataclasses.replace(bt.settings, heartbeat_seconds=0.001))
    assert c.get(f'/api/v1/backtests/{job_id}').json()['state'] == 'FINISHED'
    assert len([x for x in worker.posted('/v1/jobs') if x['body']['job_id'] == job_id]) == 1
    found = logged(caplog, 'backtest_job_store_failed')
    assert {e['step'] for e in found} == {'dispatch', 'follow', 'heartbeat'}
    assert all(e['error'] == 'psycopg.OperationalError' and e['request_id'] == job_id for e in found)
    # the worker refuses the job and the end fails twice: the job ends with the worker's error, not WORKER_LOST
    worker.refuse_with = {'code': 'DATA_MISSING', 'message': 'no price file for MAPI'}
    worker.jobs.clear()
    flaky('end', 2)
    refused = submit(c, single(), 'db-refused').json()['request_id']
    run_next(c)
    assert c.get(f'/api/v1/backtests/{refused}').json()['error'] == worker.refuse_with
    assert [e['step'] for e in logged(caplog, 'backtest_job_store_failed') if e['request_id'] == refused] == ['end', 'end']


def test_an_expired_lease_is_its_followers_until_reap_takes_it(app, worker, monkeypatch, caplog):
    """The lease token fences the follower; the expiry decides only when reap may end a job: a lease that expired
    while the database was away (heartbeats failing) is renewed by its heartbeat and the job finishes; once reap took
    the job (FAILED WORKER_LOST, the token cleared), the follower is fenced, and a result it held is dropped and
    logged once, whether its own job read or its heartbeat finds the job gone first."""
    c = app
    bt = c.app.state.backtests
    store = bt.store
    expire = lambda job_id: db(c, "UPDATE edge_bff.backtest_jobs SET lease_expires_at=now()-interval '1 second' "
                                  "WHERE request_id=%s", job_id)
    renewed = lambda job_id: db(c, 'SELECT lease_expires_at > now() AS ok FROM edge_bff.backtest_jobs '
                                   'WHERE request_id=%s', job_id)[0]['ok']
    # the store: a heartbeat renews an expired lease nobody reaped, and is refused once reap took the job
    held = submit(c, single(), 'expired-heartbeat').json()['request_id']
    row = store.claim(90)
    expire(held)
    assert store.heartbeat(row, 90) and renewed(held)
    expire(held)
    assert store.reap() == [held] and not store.heartbeat(row, 90)
    # the loop: the lease expires while the job runs; its heartbeat renews it before the job finishes
    seen = []
    def on_poll(job_id, polls):
        if polls == 1:
            expire(job_id)
        elif polls == 2:
            until = time.monotonic() + 5
            while not renewed(job_id) and time.monotonic() < until:
                time.sleep(0.01)
            seen.append(renewed(job_id))
    worker.on_poll = on_poll
    job_id = submit(c, single(), 'expired-not-reaped').json()['request_id']
    run_next(c, dataclasses.replace(bt.settings, heartbeat_seconds=0.001))
    assert c.get(f'/api/v1/backtests/{job_id}').json()['state'] == 'FINISHED' and seen == [True]
    worker.on_poll = None
    # reap takes a job whose store keeps failing: the follower finds its lease gone and stops. With a heartbeat far
    # slower than the polls the follower's job read finds it; with one far faster, the heartbeat does, and the
    # follower, not cancelled, still finds it at its next poll and logs it. (The lease is made to expire and reaped
    # while no heartbeat runs: one between the two would renew it, as it should, and reap would find nothing.)
    between, real_heartbeat, beats = threading.Lock(), store.heartbeat, []
    def heartbeat(row, seconds):
        with between:
            beats.append(real_heartbeat(row, seconds))
            return beats[-1]
    def reaped(row, split):
        with between:
            expire(row['request_id'])
            assert store.reap() == [row['request_id']]
        raise psycopg.OperationalError(LOST_CONNECTION)
    monkeypatch.setattr(store, 'heartbeat', heartbeat)
    monkeypatch.setattr(store, 'finish', reaped)
    for name, every, poll in (('reaped', 20, 0.005), ('reaped-beat-first', 0.001, 0.2)):
        caplog.clear()
        beats.clear()
        taken = submit(c, single(), name).json()['request_id']
        run_next(c, dataclasses.replace(bt.settings, heartbeat_seconds=every, poll_seconds=poll))
        assert c.get(f'/api/v1/backtests/{taken}').json()['error'] == {'code': 'WORKER_LOST'}
        assert (False in beats) == (every < poll) and not logged(caplog, 'backtest_job_store_failed'), name
        assert logged(caplog, 'backtest_lease_lost') == [{'event': 'backtest_lease_lost', 'request_id': taken,
                                                          'step': 'follow', 'result_held': True, 'state': 'FAILED',
                                                          'code': 'WORKER_LOST'}], name


def test_a_follower_that_no_longer_holds_its_job_logs_why_once(app, worker, monkeypatch, caplog):
    """Every fenced call of the follower that matches no row (the job read at the hand-over or while following, the
    progress, the result's store, an end) stops it and logs backtest_lease_lost once, with the step that found it and
    the job's state and error code read then: reap's FAILED WORKER_LOST, or what an earlier write of this follower
    committed although the database's answer was lost (FINISHED with the result stored, or the end it made)."""
    c = app
    bt = c.app.state.backtests
    store = bt.store
    lost_answer = 'consuming input failed: server closed the connection unexpectedly'
    reaped = []
    def reap(job_id):
        """another edge-bff's reap of this job (its lease made to expire first); checked after each case"""
        db(c, "UPDATE edge_bff.backtest_jobs SET lease_expires_at=now()-interval '1 second' WHERE request_id=%s", job_id)
        reaped.append(store.reap())
    def wrap(name, before=None, after=None, times=1):
        """store.<name>, with `before` run ahead of the real call and `after` (raising) behind it, `times` times"""
        real, n = getattr(store, name), [0]
        def call(row, *args):
            n[0] += 1
            if n[0] <= times and before:
                before(row['request_id'])
            out = real(row, *args)
            if n[0] <= times and after:
                after()
            return out
        monkeypatch.setattr(store, name, call)
    def lost_line(job_id):
        return [e for e in logged(caplog, 'backtest_lease_lost') if e['request_id'] == job_id]
    def raise_lost():
        raise psycopg.OperationalError(lost_answer)
    # reaped while the worker is busy, before the hand-over: the job read at the hand-over finds it
    worker.busy = 1
    real_current, reads = store.current, []
    def current(row):
        reads.append(row['request_id'])
        if len(reads) == 2:
            reap(row['request_id'])
        return real_current(row)
    monkeypatch.setattr(store, 'current', current)
    busy = submit(c, single(), 'lost-at-hand-over').json()['request_id']
    run_next(c)
    monkeypatch.setattr(store, 'current', real_current)
    assert reaped.pop() == [busy]
    assert lost_line(busy) == [{'event': 'backtest_lease_lost', 'request_id': busy, 'step': 'dispatch',
                                'result_held': False, 'state': 'FAILED', 'code': 'WORKER_LOST'}]
    assert worker.posted('/v1/jobs')[-1]['body']['job_id'] == busy and busy not in worker.jobs
    # reaped just before the result's store: the store is refused, the fetched result is dropped
    wrap('finish', before=reap)
    before_store = submit(c, single(), 'lost-at-store').json()['request_id']
    run_next(c)
    assert reaped.pop() == [before_store]
    assert lost_line(before_store) == [{'event': 'backtest_lease_lost', 'request_id': before_store, 'step': 'finish',
                                        'result_held': True, 'state': 'FAILED', 'code': 'WORKER_LOST'}]
    # the store committed, its answer was lost: the job read at the next poll finds the job FINISHED, result stored
    monkeypatch.undo()
    wrap('finish', after=raise_lost)
    committed = submit(c, single(), 'committed-answer-lost').json()['request_id']
    run_next(c)
    assert c.get(f'/api/v1/backtests/{committed}').json()['state'] == 'FINISHED'
    assert c.get(f'/api/v1/backtests/{committed}/result').json() == result_of(committed, single())
    assert lost_line(committed) == [{'event': 'backtest_lease_lost', 'request_id': committed, 'step': 'follow',
                                     'result_held': True, 'state': 'FINISHED', 'code': None}]
    # an end committed, its answer lost: made again, refused by the fence, the job keeps that end
    monkeypatch.undo()
    worker.refuse_with = {'code': 'DATA_MISSING', 'message': 'no price file for MAPI'}
    wrap('end', after=raise_lost)
    refused = submit(c, single(), 'end-answer-lost').json()['request_id']
    run_next(c)
    assert c.get(f'/api/v1/backtests/{refused}').json()['error'] == worker.refuse_with
    assert lost_line(refused) == [{'event': 'backtest_lease_lost', 'request_id': refused, 'step': 'end',
                                   'result_held': False, 'state': 'FAILED', 'code': 'DATA_MISSING'}]
    worker.refuse_with = None
    # reaped while it runs: the progress write is refused (the job read before it still held)
    monkeypatch.undo()
    worker.on_poll = lambda job_id, polls: polls == 1 and reap(job_id)
    running = submit(c, single(), 'lost-at-progress').json()['request_id']
    run_next(c)
    worker.on_poll = None
    assert reaped == [[running]]
    assert lost_line(running) == [{'event': 'backtest_lease_lost', 'request_id': running, 'step': 'progress',
                                   'result_held': False, 'state': 'FAILED', 'code': 'WORKER_LOST'}]


def test_a_hand_over_past_its_deadline_ends_timeout_while_the_database_fails(app, worker, monkeypatch, caplog):
    """The hand-over checks the deadline before its job read, as the follower checks it before its own: a worker busy
    past BACKTEST_TIMEOUT_SECONDS while every job read fails ends the job FAILED TIMEOUT, its end made again while it
    fails, never left RUNNING for reap to end WORKER_LOST."""
    c = app
    bt = c.app.state.backtests
    store = bt.store
    worker.busy = 10 ** 6
    real_current, real_end, started, ends = store.current, store.end, [], []
    def current(row):
        if time.monotonic() - started[0] > 0.2:
            raise psycopg.OperationalError('consuming input failed: server closed the connection unexpectedly')
        return real_current(row)
    def end(row, *args):
        ends.append(args)
        if len(ends) == 1:
            raise psycopg.OperationalError('consuming input failed: server closed the connection unexpectedly')
        return real_end(row, *args)
    monkeypatch.setattr(store, 'current', current)
    monkeypatch.setattr(store, 'end', end)
    job_id = submit(c, single(), 'busy-past-deadline').json()['request_id']
    started.append(time.monotonic())
    run_next(c, dataclasses.replace(bt.settings, backtest_timeout_seconds=0.5))
    assert c.get(f'/api/v1/backtests/{job_id}').json()['error'] == {'code': 'TIMEOUT'}
    assert ends == [('FAILED', {'code': 'TIMEOUT'})] * 2 and job_id not in worker.jobs
    steps = [e['step'] for e in logged(caplog, 'backtest_job_store_failed') if e['request_id'] == job_id]
    assert 'dispatch' in steps and steps[-1] == 'end' and steps.count('end') == 1


def test_a_heartbeat_failure_no_retry_mends_is_logged_and_leaves_the_follower(app, worker, monkeypatch, caplog):
    """A heartbeat that fails in a way no retry mends (any error but OperationalError) is logged by its SQLSTATE and
    not made again (the lease is left to expire); the follower goes on, and the job finishes."""
    c = app
    bt = c.app.state.backtests
    calls = []
    def refused(row, seconds):
        calls.append(row['request_id'])
        raise psycopg.errors.InsufficientPrivilege('permission denied for table backtest_jobs')
    monkeypatch.setattr(bt.store, 'heartbeat', refused)
    worker.finish_after = 6
    job_id = submit(c, single(), 'beat-refused').json()['request_id']
    run_next(c, dataclasses.replace(bt.settings, heartbeat_seconds=0.001))
    assert c.get(f'/api/v1/backtests/{job_id}').json()['state'] == 'FINISHED' and calls == [job_id]
    assert logged(caplog, 'backtest_job_store_failed') == [{
        'event': 'backtest_job_store_failed', 'step': 'heartbeat', 'request_id': job_id,
        'error': 'psycopg.errors.InsufficientPrivilege', 'sqlstate': '42501'}]


def test_a_database_failure_is_logged_without_credentials_or_row_values():
    """failure_of: the class always; a server error by its SQLSTATE only (its text can carry row values); an error of
    psycopg or libpq itself by its first line without the configured password (decoded or as the URL spells it), its
    user, host and database names, URL user info, password= pairs or IP addresses, redacted before it is cut; a
    connection string conninfo_to_dict cannot read and any other exception: the class only."""
    url = 'postgresql://edge_bff_login:s3cr%40t@postgres.railway.internal:5432/railway'
    server = psycopg.errors.CheckViolation('new row violates check constraint\nDETAIL:  Failing row contains (owner-7, 42)')
    assert backtest.failure_of(server, url) == {'error': 'psycopg.errors.CheckViolation', 'sqlstate': '23514'}
    client = psycopg.OperationalError('consuming input failed: SSL error: bad length (s3cr@t, s3cr%40t)\n\tmore lines')
    assert backtest.failure_of(client, url) == {'error': 'psycopg.OperationalError',
                                                 'detail': 'consuming input failed: SSL error: bad length ([redacted], [redacted])'}
    reach = psycopg.OperationalError('connection to server at "postgres.railway.internal" (fd12:3456::1a), port 5432 '
                                     'failed: FATAL: role "edge_bff_login" does not exist; db railway; 10.250.1.7')
    assert backtest.failure_of(reach, url)['detail'] == ('connection to server at "[redacted]" ([address]), port 5432 '
                                                        'failed: FATAL: role "[redacted]" does not exist; db [redacted]; [address]')
    pair = psycopg.OperationalError("options password='a b c' and password=other")
    assert backtest.failure_of(pair, url)['detail'] == 'options password=[redacted] and password=[redacted]'
    long = psycopg.OperationalError('x' * 295 + 's3cr@t' + 'y' * 50)
    detail = backtest.failure_of(long, url)['detail']
    assert 's3cr' not in detail and len(detail) == 300
    assert backtest.failure_of(ValueError('owner-7 row'), url) == {'error': 'builtins.ValueError'}
    unreadable = psycopg.ProgrammingError('invalid percent-encoded token: "p%zzsecret"')
    assert backtest.failure_of(unreadable, 'postgresql://edge:p%zzsecret@db/railway') == {'error': 'psycopg.ProgrammingError'}
    assert backtest.failure_of(client, 'host=db password=se cret') == {'error': 'psycopg.OperationalError'}


def test_provisioned_login_reaches_the_backtest_tables_with_their_migration(backtest_tables, monkeypatch):
    """scripts/provision_edge_bff_login.py: the three backtest tables are allowed once their migration is applied, all
    three or none (the migration grants them together), each with the privileges the migration grants it; without it
    the login reaches the three original tables."""
    import importlib.util
    import secrets
    from urllib.parse import urlsplit, urlunsplit
    database = backtest_tables
    helper = Path(__file__).resolve().parents[3] / 'scripts/provision_edge_bff_login.py'
    spec = importlib.util.spec_from_file_location('edge_provision', helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv('DATABASE_URL', database)
    monkeypatch.setenv('EDGE_DB_PASSWORD', secrets.token_hex(24))
    p = urlsplit(database)
    restricted = urlunsplit((p.scheme, 'edge_bff_login:' + os.environ['EDGE_DB_PASSWORD'] + '@' + p.netloc.split('@')[-1],
                             p.path, p.query, p.fragment))
    try:
        module.main()
        with psycopg.connect(restricted) as conn:
            for table in ('backtest_jobs', 'backtest_results', 'backtest_trials'):
                conn.execute(f'SELECT * FROM edge_bff.{table} LIMIT 0')
            # recorded_seq is an identity: the table grants are enough to record a trial
            conn.execute("""INSERT INTO edge_bff.backtest_trials(owner_key,lineage_key,variant_hash,sharpe_daily,kind,request_id)
                VALUES ('o',%s,%s,0.5,'run',%s)""", (sha('line'), sha('variant'), 'bt_' + '3' * 32))
            conn.rollback()
            # K3's trial history cannot be wiped by the runtime login, nor a job deleted or a stored part rewritten
            for sql in ('DELETE FROM edge_bff.backtest_trials', 'DELETE FROM edge_bff.backtest_jobs',
                        "UPDATE edge_bff.backtest_results SET part='core'"):
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    conn.execute(sql)
                conn.rollback()
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute('SELECT * FROM public.market_private')
        # a backtest table granted more than the migration grants it is refused, as a missing one is: DELETE or
        # TRUNCATE (either empties the K3 trials), REFERENCES or TRIGGER
        for extra in ('DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'):
            with psycopg.connect(database, autocommit=True) as conn:
                conn.execute(f'GRANT {extra} ON edge_bff.backtest_trials TO edge_bff_runtime')
            with pytest.raises(RuntimeError, match='Unexpected EDGE grants'):
                module.main()
            with psycopg.connect(database, autocommit=True) as conn:
                conn.execute(f'REVOKE {extra} ON edge_bff.backtest_trials FROM edge_bff_runtime')
        with psycopg.connect(database, autocommit=True) as conn:
            conn.execute('REVOKE ALL ON edge_bff.backtest_trials FROM edge_bff_runtime')
        with pytest.raises(RuntimeError, match='unexpected reachable relations'):
            module.main()
        with psycopg.connect(database, autocommit=True) as conn:
            conn.execute(ROLLBACK)
        module.main()
        with psycopg.connect(restricted) as conn:
            conn.execute('SELECT * FROM edge_bff.jobs LIMIT 0')
    finally:
        with psycopg.connect(database, autocommit=True) as conn:
            if conn.execute("SELECT to_regclass('edge_bff.backtest_trials')").fetchone()[0] is None:
                conn.execute(MIGRATION.read_text())
            else:
                conn.execute('GRANT SELECT, INSERT, UPDATE ON edge_bff.backtest_trials TO edge_bff_runtime')
            conn.execute('DROP OWNED BY edge_bff_login')
            conn.execute('DROP ROLE edge_bff_login')


def test_each_job_error_code_is_in_the_one_list_the_column_points_to(backtest_tables):
    """Every code the loop writes to backtest_jobs.error (found in its own source, and NOT_STORED) is in the list of
    them, CONTRACT.md section 11; the column's comment (migration 20261027_005) points there and repeats none, so a new
    code needs no migration (20261026_005's own list went stale when RESULT_NOT_STORED was added)."""
    import inspect
    source = inspect.getsource(backtest.BacktestStore) + inspect.getsource(backtest.BacktestLoop)
    codes = set(re.findall(r"'code': '([A-Z_]+)'", source)) | {backtest.NOT_STORED['code']}
    contract = (Path(backtest.__file__).resolve().parents[1] / 'backtest/CONTRACT.md').read_text()
    errors = contract.split('\n## 11. ', 1)[1].split('\n## 12. ', 1)[0]
    assert {'WORKER_LOST', 'TIMEOUT', 'RESULT_NOT_STORED'} <= codes
    assert [code for code in sorted(codes) if f'`{code}`' not in errors] == []
    with psycopg.connect(backtest_tables, autocommit=True) as c:
        c.execute(ERROR_COMMENT.read_text())       # again: a test above may have taken 20261026_005 out and put it back
        comment = c.execute("SELECT col_description('edge_bff.backtest_jobs'::regclass, attnum) FROM pg_attribute "
                            "WHERE attrelid='edge_bff.backtest_jobs'::regclass AND attname='error'").fetchone()[0]
    assert 'CONTRACT.md section 11' in comment and [code for code in sorted(codes) if code in comment] == []


def test_the_migration_refuses_a_runtime_role_with_more_than_the_code_does(backtest_tables):
    """The migration's verify block holds edge_bff_runtime to exactly the grants of each table. A privilege it would get
    beyond them on the new tables (here through the schema's default privileges): DELETE of jobs or trials, UPDATE of
    results, TRUNCATE (it empties the trials as DELETE does), REFERENCES or TRIGGER, fails the migration, which then
    leaves nothing applied."""
    extras = ('DELETE', 'UPDATE', 'TRUNCATE', 'REFERENCES', 'TRIGGER')
    with psycopg.connect(backtest_tables, autocommit=True) as conn:
        conn.execute(ROLLBACK)
        try:
            for extra in extras:
                conn.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA edge_bff GRANT {extra} ON TABLES TO edge_bff_runtime')
                with pytest.raises(psycopg.errors.RaiseException, match='more than the backtest tables need'):
                    conn.execute(MIGRATION.read_text())
                conn.execute('ROLLBACK')                    # the migration's own transaction, aborted by its verify block
                assert conn.execute("SELECT to_regclass('edge_bff.backtest_jobs')").fetchone()[0] is None, extra
                conn.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA edge_bff REVOKE {extra} ON TABLES FROM edge_bff_runtime')
        finally:
            conn.execute('ROLLBACK')
            for extra in extras:
                conn.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA edge_bff REVOKE {extra} ON TABLES FROM edge_bff_runtime')
            if conn.execute("SELECT to_regclass('edge_bff.backtest_jobs')").fetchone()[0] is not None:
                conn.execute(ROLLBACK)                      # applied with an extra privilege: taken out again
            conn.execute(MIGRATION.read_text())


def test_the_migration_refuses_public_with_any_privilege_on_the_backtest_tables(backtest_tables):
    """The verify block also holds PUBLIC (every role) to nothing on all three tables, not only to no SELECT on the jobs.
    The migration revokes PUBLIC's grants just before it, so it is run here without that REVOKE, the verify block being
    the guard, with the schema's default privileges granting PUBLIC one privilege at a time on the new tables. A
    privilege edge_bff_runtime would then hold beyond its grants is refused by the runtime check first; SELECT and
    INSERT, which it holds anyway, by the PUBLIC check."""
    revoke = 'REVOKE ALL ON edge_bff.backtest_jobs, edge_bff.backtest_results, edge_bff.backtest_trials FROM PUBLIC;\n'
    assert MIGRATION.read_text().count(revoke) == 1
    unguarded = MIGRATION.read_text().replace(revoke, '')
    privileges = ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER')
    with psycopg.connect(backtest_tables, autocommit=True) as conn:
        conn.execute(ROLLBACK)
        try:
            conn.execute(unguarded)                         # without any default privilege PUBLIC has nothing: applied
            conn.execute(ROLLBACK)
            for privilege in privileges:
                conn.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA edge_bff GRANT {privilege} ON TABLES TO PUBLIC')
                message = 'PUBLIC can use the backtest tables' if privilege in ('SELECT', 'INSERT') else 'more than the backtest tables need'
                with pytest.raises(psycopg.errors.RaiseException, match=message):
                    conn.execute(unguarded)
                conn.execute('ROLLBACK')
                assert conn.execute("SELECT to_regclass('edge_bff.backtest_jobs')").fetchone()[0] is None, privilege
                conn.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA edge_bff REVOKE {privilege} ON TABLES FROM PUBLIC')
        finally:
            conn.execute('ROLLBACK')
            for privilege in privileges:
                conn.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA edge_bff REVOKE {privilege} ON TABLES FROM PUBLIC')
            if conn.execute("SELECT to_regclass('edge_bff.backtest_jobs')").fetchone()[0] is not None:
                conn.execute(ROLLBACK)
            conn.execute(MIGRATION.read_text())


def handed(worker, job_id):
    return [x for x in worker.posted('/v1/jobs') if x['body']['job_id'] == job_id][0]['body']


def as_prior(variants):
    return [{'variant_hash': v['variant_hash'], 'sharpe_daily': v['sharpe_daily']} for v in variants]


def test_trials_are_the_reported_variants_and_go_to_the_next_run_in_first_recorded_order(app, worker):
    c = app
    first = submit(c, single()).json()['request_id']
    run_next(c)
    reported = result_of(first, single())['meta']['trials']['variants']
    trials = db(c, 'SELECT * FROM edge_bff.backtest_trials ORDER BY recorded_seq')
    assert [(t['variant_hash'], t['sharpe_daily'], t['kind'], t['request_id']) for t in trials] == \
        [(v['variant_hash'], v['sharpe_daily'], v['kind'], first) for v in reported]          # exactly, in the run's order
    assert all(t['lineage_key'] == lineage_of(single()) for t in trials)
    assert reported[1]['variant_hash'] > reported[2]['variant_hash']                          # that order is not hash order
    # the same line with another number: a new variant; it gets the line's trials as recorded, then adds its own
    second_request = {**single(), 'entry': {**single()['entry'], 'window_bars': 5}}
    second = submit(c, second_request).json()['request_id']
    run_next(c)
    assert handed(worker, second)['context'] == {'job_id': second, 'prior_trials': as_prior(reported)}
    assert db(c, 'SELECT count(*) AS n FROM edge_bff.backtest_trials')[0]['n'] == 6
    # the first variant again on other data: nothing new is counted; the row holds what this run reported (its Sharpe,
    # kind and request) and keeps its first-recorded place
    worker.run_sharpe = 0.5
    third = submit(c, single()).json()['request_id']
    run_next(c)
    assert db(c, 'SELECT count(*) AS n FROM edge_bff.backtest_trials')[0]['n'] == 6
    again = db(c, 'SELECT * FROM edge_bff.backtest_trials WHERE variant_hash=%s', reported[0]['variant_hash'])[0]
    assert (again['sharpe_daily'], again['kind'], again['request_id']) == (0.5, 'run', third)
    assert (again['recorded_seq'], again['created_at']) == (trials[0]['recorded_seq'], trials[0]['created_at'])
    assert again['updated_at'] > again['created_at'] and third != first
    fourth = submit(c, {**single(), 'entry': {**single()['entry'], 'window_bars': 7}}).json()['request_id']
    run_next(c)
    assert handed(worker, fourth)['context']['prior_trials'] == \
        as_prior([{**reported[0], 'sharpe_daily': 0.5}, *reported[1:], *result_of(second, second_request)['meta']['trials']['variants']])
    # a variant first recorded as a cell and reported later as a run's own variant takes that kind, in its place
    store = c.app.state.backtests.store
    own = submit(c, single(), 'cell-as-run').json()['request_id']
    row = store.claim(90)
    result = result_of(own, single())
    result['meta']['trials']['variants'] = [{'variant_hash': reported[1]['variant_hash'], 'sharpe_daily': 0.25, 'kind': 'run'}]
    assert store.finish(row, split_result(result, 'BBCA'))
    cell = db(c, 'SELECT kind, sharpe_daily, request_id, recorded_seq FROM edge_bff.backtest_trials WHERE variant_hash=%s',
              reported[1]['variant_hash'])[0]
    assert cell == {'kind': 'run', 'sharpe_daily': 0.25, 'request_id': own, 'recorded_seq': trials[1]['recorded_seq']}
    # another line starts with no trials
    other = submit(c, single('TLKM')).json()['request_id']
    run_next(c)
    assert handed(worker, other)['context']['prior_trials'] == []


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
    assert status['progress'] == {'phase': 'backtest', 'done': 2, 'total': 2}      # the worker's, as it stopped (poll 2)
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
    assert status['progress'] == {'phase': 'backtest', 'done': 1, 'total': 2}      # an end of ours keeps the last one read
    assert len([x for x in worker.calls if x['path'] == f'/v1/jobs/{gone}']) == 1 + 3   # one answered read, then 3 unanswered
    worker.down, worker.on_poll = False, None
    worker.fail_with = {'code': 'DATA_INTEGRITY', 'message': 'price BBCA 2024: sha256 differs from the manifest'}
    failed = submit(c, single(), 'd').json()['request_id']
    run_next(c)
    status = c.get(f'/api/v1/backtests/{failed}').json()
    assert status['state'] == 'FAILED' and status['error'] == worker.fail_with and status['duration_ms'] == 55
    assert status['progress'] == {'phase': 'backtest', 'done': 1, 'total': 2}      # the worker's at its end (its first read)
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


def test_a_result_the_worker_no_longer_keeps_ends_the_job_at_once(app, worker):
    """410 RESULT_GONE: a newer job started at the worker (another edge-bff, during a deploy) and replaced the finished
    one, whose result no later fetch can get. The job ends FAILED WORKER_LOST at the first such answer, as for a job
    the worker forgot (404), not after WORKER_RETRIES fetches; nothing of it is stored."""
    c = app
    worker.result_gone = True
    job_id = submit(c, single(), 'gone').json()['request_id']
    run_next(c)
    status = c.get(f'/api/v1/backtests/{job_id}').json()
    assert status['state'] == 'FAILED' and status['error'] == {'code': 'WORKER_LOST'} and status['result_bytes'] is None
    assert len([x for x in worker.calls if x['path'] == f'/v1/jobs/{job_id}/result']) == 1
    assert db(c, 'SELECT count(*) AS n FROM edge_bff.backtest_results')[0]['n'] == 0
    assert db(c, 'SELECT count(*) AS n FROM edge_bff.backtest_trials')[0]['n'] == 0


def test_the_loop_prunes_at_its_start_whatever_the_clock_reads(settings, monkeypatch):
    """Expired result parts are deleted when the loop starts, then every PRUNE_SECONDS. time.monotonic() counts from an
    unspecified point (on Linux the host's boot): on a host up for 5 s the start's prune is still made."""
    import types
    now, calls = {'t': 5.0}, []

    class Store:
        def prune(self):
            calls.append('prune')

        def reap(self):
            return []

        def claim(self, lease):
            calls.append('claim')
            n = calls.count('claim')
            now['t'] += {1: 1.0, 2: float(backtest.PRUNE_SECONDS)}.get(n, 0.0)
            if n == 3:
                loop.stop()
            return None

    monkeypatch.setattr(backtest, 'time', types.SimpleNamespace(monotonic=lambda: now['t']))
    loop = BacktestLoop(settings, Store(), None)
    asyncio.run(loop.run())
    assert calls == ['prune', 'claim', 'claim', 'prune', 'claim']


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


def test_a_hand_over_the_worker_did_not_take_is_handed_over_again(app, worker):
    """CONTRACT section 8, review V1: a POST /v1/jobs whose caller left while the worker read the reference lists
    starts no job there. Its answer is lost here as any unanswered call's; the worker does not know the id, so the job
    is handed over again (WORKER_RETRIES attempts in all) and runs once."""
    c = app
    worker.unstarted = 2
    job_id = submit(c, single(), 'unstarted').json()['request_id']
    run_next(c)
    assert c.get(f'/api/v1/backtests/{job_id}').json()['state'] == 'FINISHED'
    assert len(worker.posted('/v1/jobs')) == 3 and list(worker.jobs) == [job_id]
    worker.unstarted = 3                                  # never taken: WORKER_LOST after the third attempt, as now
    lost = submit(c, single(), 'never-started').json()['request_id']
    run_next(c)
    assert c.get(f'/api/v1/backtests/{lost}').json()['error'] == {'code': 'WORKER_LOST'} and lost not in worker.jobs


def test_restart_with_an_expired_lease_fails_worker_lost_without_resubmitting(app, worker):
    c = app
    job_id = submit(c, single(), 'restart').json()['request_id']
    bt = c.app.state.backtests
    row = bt.store.claim(90)
    worker.jobs[job_id] = {'request': single(), 'context': {}, 'polls': 0, 'cancelled': False}   # handed over before the stop
    db(c, "UPDATE edge_bff.backtest_jobs SET lease_expires_at=now()-interval '1 second' WHERE request_id=%s", job_id)
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
    # reap cleared the lease token: the old holder is fenced
    assert not bt.store.heartbeat(row, 90) and bt.store.end(row, 'FAILED', {'code': 'TIMEOUT'}) is None


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
    preview = preview_of()
    r = c.post('/api/v1/backtests/signals', headers=c.headers_for, json=preview)
    assert r.status_code == 200 and r.json()['rows'][0] == {'ticker': 'BBCA', 'entry_signals': 4, 'last_signal': '2026-10-20'}
    assert worker.posted('/v1/signals')[0]['body'] == preview               # as sent: the picked order is the worker's to drop
    refused = c.post('/api/v1/backtests/signals', headers=c.headers_for, json=preview_of(['BBCA', 'NOPE']))
    assert refused.status_code == 422 and refused.json() == {'error': {'code': 'UNKNOWN_TICKER', 'field': 'tickers[1]',
                                                                       'message': 'NOPE is not a published stock.'}}
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
    # what app/backtest.py does to each table and no more: jobs are never deleted, results never updated (pruned after
    # 30 days), trials never deleted (K3: the trial count is never reset)
    assert grants == [('backtest_jobs', 'INSERT,SELECT,UPDATE'), ('backtest_results', 'DELETE,INSERT,SELECT'),
                      ('backtest_trials', 'INSERT,SELECT,UPDATE')]


def test_backtest_tab_page_and_its_frame_csp(app, monkeypatch, tmp_path):
    c = app
    (tmp_path / 'assets').mkdir()
    (tmp_path / 'index.html').write_text('<!doctype html><title>Market Lab Backtest</title>')
    (tmp_path / 'assets' / 'index-abc123.js').write_text('void 0')
    monkeypatch.setattr(main, 'BACKTEST_APP', tmp_path)
    page = c.get('/backtest')
    assert page.status_code == 200 and 'EDGE' in page.text and 'function BacktestPage' in page.text and '"/backtest-app/"' in page.text
    # the tab's wording is in edge-labels.js (AGENTS.md), used like the Terminal tab's
    assert 'backtest: { nav:"Backtest", frameTitle:"Backtest" }' in c.get('/edge-labels.js').text
    assert '[EdgeLabels.backtest.nav, "backtest"]' in page.text and 'title: EdgeLabels.backtest.frameTitle' in page.text
    assert '"Backtest"' not in page.text
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


def docker_ignored(patterns, path):
    """Whether the Docker build leaves `path` (relative to the context, '/'-separated) out of the context: moby/patternmatcher
    MatchesOrParentMatches, which the Docker CLI and BuildKit apply to .dockerignore. Each pattern is matched from the
    context root ('*' and '?' stop at '/', '**/' spans any folders), against the path and each of its parent folders;
    the last pattern that matches decides, a '!' exception keeping the path."""
    parents = path.split('/')[:-1]
    left_out = False
    for exception, rx in patterns:
        if exception != left_out:
            continue
        if rx.fullmatch(path) or any(rx.fullmatch('/'.join(parents[:k + 1])) for k in range(len(parents))):
            left_out = not exception
    return left_out


def dockerignore(text):
    patterns = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        exception = line.startswith('!')
        line = posixpath.normpath(line.lstrip('!').strip()).lstrip('/')
        assert not set('[\\') & set(line), line         # classes and escapes: not in the file, not in this matcher
        rx, i = '', 0
        while i < len(line):
            if line.startswith('**', i):
                i += 2 + (line[i + 2:i + 3] == '/')
                rx += '.*' if i >= len(line) else '(.*/)?'
                continue
            rx += {'*': '[^/]*', '?': '[^/]'}.get(line[i], re.escape(line[i]))
            i += 1
        patterns.append((exception, re.compile(rx)))
    return patterns


def test_the_image_context_leaves_out_caches_tests_and_build_output_at_any_depth():
    """apps/edge-bff/.dockerignore: a pattern matches from the context root only, so caches that appear in any folder
    need '**/' (a bare '__pycache__' left app/__pycache__ in the image). Local builds, dependencies and tests of the
    two pages stay out (the Dockerfile installs and builds them itself); every file its COPY lines take is kept."""
    root = Path(__file__).resolve().parents[1]
    patterns = dockerignore((root / '.dockerignore').read_text())
    for path in ('app/__pycache__/main.cpython-312.pyc', 'app/x.pyc', 'tests/__pycache__/conftest.cpython-312.pyc',
                 'backtest/tests/visual/__pycache__/diff.cpython-312.pyc', 'terminal/src/__pycache__/x.pyc',
                 '.pytest_cache/v/cache', 'app/.pytest_cache/v/cache', '.env', 'app/.env.local', 'backtest/.env',
                 'tests/test_backtest.py', 'preview/edge_preview.py', 'terminal/node_modules/vite/package.json',
                 'terminal/tests/calc.test.ts', 'static/terminal-app/index.html', 'backtest/node_modules/vite/package.json',
                 'backtest/tests/fixture/api.ts', 'backtest/dist/index.html', 'backtest/dist-smoke/index.html',
                 'backtest/dist-fixture/index.html', 'static/backtest-app/index.html'):
        assert docker_ignored(patterns, path), path
    copied = [source for line in (root / 'Dockerfile').read_text().splitlines() if line.startswith('COPY ') and '--from' not in line
              for source in line.split()[1:-1]]
    assert copied == ['terminal/package.json', 'terminal/package-lock.json', 'terminal/', 'backtest/package.json',
                      'backtest/package-lock.json', 'terminal/src', 'backtest/', 'requirements.txt', 'app', 'static']
    # the copied sources, the files at the top of each copied folder (configuration, package files, index.html, the app's
    # modules, the static files) and the two pages' sources
    top = [f'{folder}/{p.name}' for folder in ('app', 'static', 'terminal', 'backtest') for p in (root / folder).iterdir()
           if p.is_file() and not p.name.startswith('.env') and p.suffix != '.pyc']
    sources = [p.relative_to(root).as_posix() for folder in ('terminal/src', 'backtest/src') for p in (root / folder).rglob('*')
               if p.is_file() and '__pycache__' not in p.parts]
    needed = [*copied, *top, *sources]
    assert 'backtest/src/core/engine.ts' in needed and 'backtest/vite.config.ts' in needed and 'app/backtest.py' in needed
    assert [p for p in needed if docker_ignored(patterns, p.rstrip('/'))] == []


def test_backtest_settings_are_paired_strong_private_and_bounded(settings):
    on = dict(backtest_worker_url='http://backtest-worker.railway.internal:8080', backtest_worker_key=KEY, backtest_timeout_seconds=600,
              backtest_max_result_bytes=10 ** 8)
    dataclasses.replace(settings, **on).validate()
    for bad, message in (({'backtest_worker_key': ''}, 'set together'), ({'backtest_worker_key': 'short'}, 'at least 32'),
                         ({'backtest_timeout_seconds': 0}, 'BACKTEST_TIMEOUT_SECONDS'),
                         ({'backtest_max_result_bytes': 0}, 'BACKTEST_MAX_RESULT_BYTES'),
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
    assert [name for name, _ in split['parts']] == ['core', 'events:BBCA']
    assert split['trials'] == [(v['variant_hash'], v['sharpe_daily'], v['kind']) for v in good['meta']['trials']['variants']]
    def variants(*entries):
        return {**good, 'meta': {**good['meta'], 'trials': {**good['meta']['trials'], 'variants': list(entries)}}}
    run = good['meta']['trials']['variants'][0]
    for broken in ({**good, 'schema_version': 2}, {**good, 'events': {**good['events'], 'exits': []}},
                   {**good, 'meta': {**good['meta'], 'data_version': 'not-a-hash'}},
                   {**good, 'meta': {**good['meta'], 'tickers': ['bad ticker']}},
                   {**good, 'meta': {**good['meta'], 'duration_ms': 10 ** 400}},
                   variants({'variant_hash': 'x', 'sharpe_daily': 1, 'kind': 'run'}),
                   # a variant the contract cannot carry is no result: never skipped or counted as 0 (stored exactly)
                   variants({**run, 'sharpe_daily': None}), variants({**run, 'sharpe_daily': True}),
                   variants({**run, 'sharpe_daily': 10 ** 400}), variants({**run, 'kind': 'grid'}),
                   variants(run, {**run, 'kind': 'sensitivity'})):            # the variants are distinct
        with pytest.raises(ValueError):
            split_result(broken)
    for beyond in (float('inf'), float('-inf')):            # a result not read through loads (which refuses 1e400) too
        with pytest.raises(ValueError):
            split_result(variants({**run, 'sharpe_daily': beyond}))
    assert split_result(variants())['trials'] == []


JOB = 'bt_' + '4' * 32


class Chunks(httpx.SyncByteStream):
    """A body that arrives in 64 KiB pieces, as from the network (httpx reads a bytes body at once)."""
    def __init__(self, data):
        self.data = data

    def __iter__(self):
        for k in range(0, len(self.data), 65536):
            yield self.data[k:k + 65536]


def result_client(settings, content, encoding='gzip', limit=1000, status=200):
    """A WorkerClient whose worker answers the result call with these bytes."""
    headers = {'content-type': 'application/json', **({'content-encoding': encoding} if encoding else {})}
    transport = httpx.MockTransport(lambda request: httpx.Response(status, headers=headers, stream=Chunks(content)))
    s = dataclasses.replace(settings, backtest_worker_url='http://worker.test', backtest_worker_key=KEY,
                            backtest_timeout_seconds=30, backtest_max_result_bytes=limit)
    return WorkerClient(s, client=httpx.Client(base_url='http://worker.test', transport=transport))


def test_the_result_is_unpacked_as_it_arrives_and_never_past_its_limit(settings, monkeypatch):
    """WorkerClient.result unpacks the worker's gzip itself: exactly BACKTEST_MAX_RESULT_BYTES of JSON is taken, one
    byte more is ResultTooLarge, and a body that compresses 1000:1 stops there with at most one byte past the limit
    unpacked (httpx used to unpack the whole body into memory). A body that is not the worker's gzip is an
    unanswered call, as httpx's decoding error was."""
    body = json.dumps({'schema_version': 1, 'pad': 'x' * 5000}).encode()
    packed_body = gzip.compress(body)
    assert result_client(settings, packed_body, limit=len(body)).result(JOB) == (200, body)
    with pytest.raises(ResultTooLarge):
        result_client(settings, packed_body, limit=len(body) - 1).result(JOB)
    for plain in ('identity', None):
        assert result_client(settings, body, encoding=plain, limit=len(body)).result(JOB) == (200, body)
        with pytest.raises(ResultTooLarge):
            result_client(settings, body, encoding=plain, limit=len(body) - 1).result(JOB)
    unpacked = []
    real = zlib.decompressobj
    class Counting:
        def __init__(self, **kw):
            self.inner = real(**kw)
        def decompress(self, data, max_length=0):
            out = self.inner.decompress(data, max_length)
            unpacked.append(len(out))
            return out
        def flush(self):
            out = self.inner.flush()
            unpacked.append(len(out))
            return out
        def __getattr__(self, name):
            return getattr(self.inner, name)
    monkeypatch.setattr(backtest.zlib, 'decompressobj', Counting)
    packer = zlib.compressobj(9, zlib.DEFLATED, 31)
    bomb = b''.join(packer.compress(b' ' * 2 ** 20) for _ in range(64)) + packer.flush()   # 64 MiB of JSON whitespace
    assert len(bomb) < 2 ** 17
    with pytest.raises(ResultTooLarge):
        result_client(settings, bomb, limit=10 ** 6).result(JOB)
    assert sum(unpacked) == 10 ** 6 + 1
    monkeypatch.setattr(backtest.zlib, 'decompressobj', real)
    for broken in (dict(content=packed_body[:-12]), dict(content=packed_body, encoding='br'), dict(content=b'not gzip'),
                   dict(content=b'', status=503)):
        with pytest.raises(WorkerUnavailable):
            result_client(settings, limit=len(body), **broken).result(JOB)
    with pytest.raises(WorkerTimeout):
        result_client(settings, json.dumps({'error': {'code': 'TIMEOUT'}}).encode(), encoding=None, status=504).result(JOB)
    assert result_client(settings, b'{"error":{"code":"UNKNOWN_JOB"}}', encoding=None, status=404).result(JOB) == (404, b'')


def test_a_result_past_its_limit_ends_the_job_without_storing_it(app, worker):
    """Over BACKTEST_MAX_RESULT_BYTES the job is FAILED LIMIT_EXCEEDED at once (fetching it again would give the same
    result) and nothing of it is stored; at the limit it is taken."""
    c = app
    bt = c.app.state.backtests
    size = len(json.dumps(result_of(JOB, single())).encode())    # the fake's result of single() for any job id
    bt.worker.settings = dataclasses.replace(bt.worker.settings, backtest_max_result_bytes=size - 1)
    over = submit(c, single(), 'over').json()['request_id']
    run_next(c, bt.worker.settings)
    status = c.get(f'/api/v1/backtests/{over}').json()
    assert status['state'] == 'FAILED' and status['error'] == {'code': 'LIMIT_EXCEEDED', 'message':
        f'The backtest result is larger than {size - 1} bytes of JSON, the most edge-bff stores (BACKTEST_MAX_RESULT_BYTES).'}
    assert len([x for x in worker.calls if x['path'] == f'/v1/jobs/{over}/result']) == 1
    assert db(c, 'SELECT count(*) AS n FROM edge_bff.backtest_results')[0]['n'] == 0
    assert db(c, 'SELECT count(*) AS n FROM edge_bff.backtest_trials')[0]['n'] == 0
    bt.worker.settings = dataclasses.replace(bt.worker.settings, backtest_max_result_bytes=size)
    at = submit(c, single(), 'at').json()['request_id']
    run_next(c, bt.worker.settings)
    assert c.get(f'/api/v1/backtests/{at}/result').json() == result_of(at, single())


def serve(settings, store):
    """The app on a real local server (uvicorn on 127.0.0.1), as it runs deployed; (settings, stop)."""
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    local = dataclasses.replace(settings, origin=f'http://127.0.0.1:{sock.getsockname()[1]}')
    server = uvicorn.Server(uvicorn.Config(create_app(local, store, FakeOrc()), log_level='critical', access_log=False))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.02)
    assert server.started
    def stop():
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
    return local, stop


def sign_in(local):
    """(headers, cookies) of the owner's session on a served app."""
    with httpx.Client(base_url=local.origin, timeout=60) as h:
        r = h.post('/api/v1/auth/sign-in', headers={'Origin': local.origin}, json={'login': 'owner', 'password': 'local-test-password'})
        return {'Origin': local.origin, 'X-CSRF-Token': r.json()['csrf_token']}, dict(h.cookies)


def at_the_worker(monkeypatch):
    """How many signals calls edge-bff has open to the worker: now, and the most at any time. A call is open from its
    start until it answered or its cancellation closed its connection (WorkerClient.acall returned)."""
    seen, real = {'open': 0, 'most': 0}, WorkerClient.acall
    async def counted(self, method, path, body=None, timeout=None):
        if path != '/v1/signals':
            return await real(self, method, path, body, timeout)
        seen['open'] += 1
        seen['most'] = max(seen['most'], seen['open'])
        try:
            return await real(self, method, path, body, timeout)
        finally:
            seen['open'] -= 1
    monkeypatch.setattr(WorkerClient, 'acall', counted)
    return seen


REPLACED = {'error': {'code': 'PREVIEW_REPLACED', 'message': 'A newer signals preview replaced this one.'}}
ROWS = [{'ticker': 'BBCA', 'entry_signals': 4, 'last_signal': '2026-10-20'}]     # the fake worker's preview


def test_a_newer_preview_of_the_owner_ends_the_one_in_flight(configured, store, worker, monkeypatch):
    """CONTRACT.md P8, latest wins: a preview of the owner that arrives while an older one still waits at the worker ends
    that one early (its worker call is closed, so the worker stops it, and it answers 409 PREVIEW_REPLACED) and is sent
    once that call has ended, then answers as usual: never two previews of the owner at the worker. A body edge-bff
    refuses itself (422 INVALID_INPUT) is no preview and replaces none."""
    seen = at_the_worker(monkeypatch)
    wait = 2.0
    worker.delay = {'/v1/signals': wait}
    local, stop = serve(configured, store)
    try:
        headers, cookies = sign_in(local)
        def preview(body):
            with httpx.Client(base_url=local.origin, timeout=60, cookies=cookies) as p:
                return p.post('/api/v1/backtests/signals', headers=headers, json=body)
        older, newer = preview_of(), preview_of(period={'from': '2025-01-02', 'to': '2026-10-23'})
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            first = pool.submit(preview, older)
            for _ in range(500):
                if worker.posted('/v1/signals'):
                    break
                time.sleep(0.01)
            with httpx.Client(base_url=local.origin, timeout=60, cookies=cookies) as h:
                # not an object; a number beyond a double (V2, an integer V2a); a lone surrogate (V2b)
                for raw in (b'[1]', b'{"tickers":["BBCA"],"x":1e400}', b'{"tickers":["BBCA"],"x":1' + b'0' * 400 + b'}',
                            rb'{"tickers":["BBCA"],"x":"\ud800"}'):
                    bad = h.post('/api/v1/backtests/signals', headers={**headers, 'content-type': 'application/json'}, content=raw)
                    assert bad.status_code == 422 and bad.json() == {'error': {'code': 'INVALID_INPUT'}}, raw
            assert not first.done()
            arrived = time.monotonic()
            second = pool.submit(preview, newer)
            ended = first.result()
            assert time.monotonic() - arrived < wait / 2                     # early, not when the worker would answer
            assert ended.status_code == 409 and ended.json() == REPLACED
            answered = second.result()
            assert answered.status_code == 200 and answered.json()['rows'] == ROWS
        assert [c['body'] for c in worker.posted('/v1/signals')] == [older, newer]
        assert worker.abandoned == ['/v1/signals']                           # the older one's call, closed by edge-bff
        assert seen == {'open': 0, 'most': 1}
    finally:
        stop()


def test_overlapping_previews_of_the_owner_leave_one_in_flight_and_hold_up_nothing(configured, store, worker, monkeypatch):
    """SEC-1 and P8: as many previews of the owner at once as asyncio's default thread pool has threads (where every
    session check runs, main.py session; they all used to wait at the worker) leave one in flight, the latest to
    arrive: every other one answers 409 PREVIEW_REPLACED at once, and those that had reached the worker are stopped
    there. While the one left waits (on the event loop, WorkerClient.acall), the owner's other requests are answered."""
    seen = at_the_worker(monkeypatch)
    threads = min(32, (getattr(os, 'process_cpu_count', os.cpu_count)() or 1) + 4)   # ThreadPoolExecutor's default size
    worker.delay = {'/v1/signals': 3.0}
    local, stop = serve(configured, store)
    try:
        headers, cookies = sign_in(local)
        def preview(k):
            with httpx.Client(base_url=local.origin, timeout=60, cookies=cookies) as p:
                return p.post('/api/v1/backtests/signals', headers=headers, json={**preview_of(), 'k': k})
        with concurrent.futures.ThreadPoolExecutor(threads) as pool:
            pending = [pool.submit(preview, k) for k in range(threads)]
            for _ in range(500):
                if sum(f.done() for f in pending) == threads - 1:
                    break
                time.sleep(0.01)
            replaced = [f.result() for f in pending if f.done()]
            assert len(replaced) == threads - 1 and all(r.status_code == 409 and r.json() == REPLACED for r in replaced)
            with httpx.Client(base_url=local.origin, timeout=60, cookies=cookies) as h:
                listed = h.get('/api/v1/backtests')
                catalog = h.get('/api/v1/backtests/catalog')
            assert listed.status_code == 200 and catalog.status_code == 200
            [latest] = [k for k, f in enumerate(pending) if not f.done()]
            assert seen['open'] == 1 and pending[latest].result().json()['rows'] == ROWS
        sent = [x['body']['k'] for x in worker.posted('/v1/signals')]
        assert latest in sent and len(worker.abandoned) == len(sent) - 1 and seen == {'open': 0, 'most': 1}
    finally:
        stop()


def test_a_stopped_call_ends_even_when_a_cancellation_is_absorbed_inside_it():
    """unless_gone stops the call through an anyio cancel scope, which delivers its cancellation until the call has left
    it. A single task.cancel() can be lost: when it lands as one of httpx's own anyio scopes cancels itself (anyio
    connect_tcp's, once connected), that scope takes it for its own, and the replaced preview went on to the worker's
    answer while the newer one waited for it. Modelled by a call that absorbs the first cancellation it gets."""
    class Staying:                                   # a caller that does not leave
        async def receive(self):
            await asyncio.Event().wait()

    async def scenario():
        replaced, absorbed = asyncio.Event(), []
        async def call():
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                absorbed.append(True)                # taken for its own, as such an inner scope does
            await asyncio.sleep(30)                  # the rest of the call: the worker's answer
            return 'answered'
        asyncio.get_running_loop().call_later(0.05, replaced.set)
        started = time.monotonic()
        with pytest.raises(backtest.PreviewReplaced):
            await asyncio.wait_for(backtest.Backtests.unless_gone(Staying(), call(), replaced), 5)
        return absorbed, time.monotonic() - started
    absorbed, took = asyncio.run(scenario())
    assert absorbed == [True] and took < 1


def test_previews_of_the_owner_in_sequence_are_unaffected(app, worker):
    """Latest wins only among previews in flight: one that answered, was refused by the worker or by edge-bff frees its
    owner's place, so each preview after it is relayed as before and none is replaced."""
    c = app
    bt = c.app.state.backtests
    preview = preview_of()
    for body in (preview, preview_of(['NOPE']), preview, preview_of(['TLKM', 'BBCA'])):
        r = c.post('/api/v1/backtests/signals', headers=c.headers_for, json=body)
        if body['tickers'] == ['NOPE']:
            assert r.status_code == 422 and r.json()['error']['code'] == 'UNKNOWN_TICKER'
        else:
            assert r.status_code == 200 and r.json()['rows'] == ROWS
        assert bt.previews == {}
    assert c.post('/api/v1/backtests/signals', headers=c.headers_for, content=b'not json').status_code == 422
    assert c.post('/api/v1/backtests/signals', headers=c.headers_for, json=preview).status_code == 200
    assert len(worker.posted('/v1/signals')) == 5 and worker.abandoned == [] and bt.previews == {}


def test_a_preview_its_caller_left_is_stopped_at_the_worker(configured, store, worker):
    """A preview whose caller went away before the worker answered (the page dropped it for newer settings) is
    cancelled here, which closes its connection to the worker, so the worker stops computing it."""
    worker.timeout_paths, worker.timeout_after = {'/v1/signals'}, 5.0
    local, stop = serve(configured, store)
    try:
        headers, cookies = sign_in(local)
        with httpx.Client(base_url=local.origin, timeout=60, cookies=cookies) as h:
            with pytest.raises(httpx.ReadTimeout):         # the page gives up on it
                h.post('/api/v1/backtests/signals', headers=headers, json=preview_of(), timeout=httpx.Timeout(60, read=0.3))
        for _ in range(400):
            if worker.abandoned:
                break
            time.sleep(0.01)
        assert worker.abandoned == ['/v1/signals']             # closed by edge-bff before the worker's answer (5 s)
        worker.timeout_paths = set()
        with httpx.Client(base_url=local.origin, timeout=60, cookies=cookies) as h:   # it left its owner's place free
            assert h.post('/api/v1/backtests/signals', headers=headers, json=preview_of()).json()['rows'] == ROWS
    finally:
        stop()


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
