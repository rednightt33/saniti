"""EDGE screener in edge-bff (EXEC-SCREENER; report API CONTRACT section 8, TEST PLAN 10b.11): the /api/v1/screener
routes against a fake screener-worker that is a real local HTTP server speaking the worker's private API (report 8.11),
the saved items and watchlist tables (migration 20261028_001, applied by conftest with the others), the provisioning
script's reach, and the /screener page with its frame's CSP.

The fake worker's answers are small documents in the contract's shape (apps/edge-bff/screener/src/core/contract.ts)
built for the test (test data only, not market data); edge-bff reads of them only their versions, a validation's
definition_hash and an error, which is what is checked here."""
import concurrent.futures
import dataclasses
import gzip
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
from pathlib import Path
import select
import socket
import threading
import time

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient
import uvicorn

from app import main, screener
from app.main import create_app
from conftest import FakeOrc

ORIGIN = {'Origin': 'http://testserver'}
KEY = 's' * 40
MIGRATION = Path(__file__).resolve().parents[3] / 'database/migrations/20261028_001_edge_bff_screener.sql'
ROLLBACK = '\n'.join(line[3:] for line in MIGRATION.read_text().split('-- Rollback', 1)[1].splitlines()[1:] if line.startswith('-- '))
WRITE_ROUTES = (('POST', '/api/v1/screener/run'), ('POST', '/api/v1/screener/preview'), ('POST', '/api/v1/screener/validate'),
                ('POST', '/api/v1/screener/counts'), ('PUT', '/api/v1/screener/items/scr_' + '1' * 32),
                ('DELETE', '/api/v1/screener/items/scr_' + '1' * 32), ('PUT', '/api/v1/screener/watchlist/BBCA'),
                ('DELETE', '/api/v1/screener/watchlist/BBCA'))
READ_ROUTES = ('/api/v1/screener/catalog', '/api/v1/screener/universe', '/api/v1/screener/items', '/api/v1/screener/watchlist')


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def versions(tag='a', **change):
    """Versions (contract.ts) of the fake worker's snapshot `tag`."""
    return {'screener_engine': '0a1b2c3d4e5f6071', 'registry': 'registry-' + tag, 'screener_registry': 'sregistry-' + tag,
            'price_data': sha('price-' + tag), 'flow_data': None, **change}


def definition(length=7, **change):
    """A portable screen definition (contract.ts Definition): RSI(length) below 30 on the default universe."""
    return {'universe': {'security_types': ['stock'], 'price_min': 50, 'adv20_min_idr': 1e9, 'traded_on_eval_date': True,
                         'exclude_price_breaks': True},
            'conditions': [{'id': 'a', 'enabled': True, 'test': rsi_test(length)}], 'logic': 'all', **change}


def rsi_test(length=7):
    return {'kind': 'value', 'op': 'lt', 'value': 30,
            'metric': {'kind': 'indicator', 'indicator': 'I13', 'params': {'length': length}, 'output': 'rsi'}}


def run_body(seq=1, page='pg_1', **change):
    return {'schema_version': 1, 'client_order': {'page': page, 'seq': seq}, 'definition': definition(**change),
            'options': {'exhaustive': False, 'explain': False}}


def preview_body(seq=1, page='pg_1', ticker='BBCA'):
    return {'schema_version': 1, 'client_order': {'page': page, 'seq': seq}, 'definition': definition(), 'ticker': ticker,
            'data_version': sha('price-a')}


def screen_item(name='Oversold', length=7, revision=None):
    return {'kind': 'screen', 'name': name, 'definition': {'definition': definition(length), 'view': {'show_near': True}},
            **({'revision': revision} if revision is not None else {})}


def metric_item(name='RSI 7 low', length=7, revision=None):
    return {'kind': 'metric', 'name': name, 'definition': {'test': rsi_test(length)},
            **({'revision': revision} if revision is not None else {})}


class FakeScreenerWorker:
    """The screener-worker's private API (report 8.11) on 127.0.0.1. /health needs no key, every other route the key.
    Switches make it fail, time out, answer outside its API or not be ready."""

    def __init__(self):
        self.lock = threading.Lock()
        self.calls = []
        self.versions = versions('a')
        self.refresh = 'ready'
        self.down = False              # every route but /health answers 503 without the worker's error
        self.not_ready = None          # seconds: /v1/* answer the worker's 503 SCREENER_NOT_READY naming them
        self.garbage = set()           # these routes answer 200 with a body that is not JSON
        self.timeout_paths = set()     # these routes answer the worker's 504 TIMEOUT (timeout_error False: a bare 504)
        self.timeout_error = True
        self.delay = {}                # path -> seconds the route waits (and stops if its caller left first)
        self.abandoned = []            # routes whose caller closed the connection while they waited
        self.refuse = {}               # path -> (status, error) answered instead
        self.max_length = 1000         # /v1/validate refuses an indicator length above it (PARAM_OUT_OF_RANGE)
        self.validate_versions = True  # /v1/validate answers carry versions (report 8.3: every worker answer)
        self.rows = 3                  # rows of a run answer
        self.published = '2026-10-27T13:03:23Z'   # data.published_at of every answer (state.json finished_at)
        self.pending = {}              # path -> how many more calls answer the worker-only 409 DATA_VERSION_PENDING
        self.sent = {}                 # path -> the last body bytes the route sent (gzip when it packed them)
        self.limits = [{'name': 'max_conditions', 'value': 20, 'unit': 'conditions', 'rule': 'at most 20 enabled conditions',
                        'example_ok': 'a screen with 20 enabled conditions', 'example_refused': 'a screen with 21 enabled conditions'}]
        worker = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'    # keep-alive, as the worker's Node server: edge-bff's pooled connection is reused

            def log_message(self, *args):
                pass

            def answer(self, status, body=None, raw=None, headers=None):
                data = raw if raw is not None else json.dumps(body).encode()
                packed = 'gzip' in self.headers.get('accept-encoding', '') and raw is None
                tag = '"' + hashlib.sha256(data).hexdigest() + '"'
                if packed:
                    data = gzip.compress(data)
                with worker.lock:
                    worker.sent[self.path] = data
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                if packed:
                    self.send_header('Content-Encoding', 'gzip')
                if packed and 200 <= status < 300:
                    self.send_header('ETag', tag)       # report 6d.5: the worker's ETag of the JSON bytes
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def held(self, seconds):
                end = time.monotonic() + seconds
                while (left := end - time.monotonic()) > 0:
                    ready, _, _ = select.select([self.connection], [], [], min(left, 0.02))
                    if ready and self.connection.recv(1, socket.MSG_PEEK) == b'':
                        with worker.lock:
                            worker.abandoned.append(self.path)
                        return False
                return True

            def data(self):
                return {'evaluation_date': '2026-10-27', 'price_through': '2026-10-27', 'flow_through': None,
                        'broker_behind_sessions': 0, 'published_at': worker.published}

            def handle_one(self, method):
                length = int(self.headers.get('content-length') or 0)
                body = json.loads(self.rfile.read(length)) if length else None
                with worker.lock:
                    worker.calls.append({'method': method, 'path': self.path, 'body': body,
                                         'key': self.headers.get('x-screener-worker-key'),
                                         'owner': self.headers.get('x-screener-owner'), 'port': self.client_address[1]})
                v = worker.versions
                if self.path == '/health':
                    return self.answer(200, {'ok': True, 'versions': v, 'published_at': worker.published,
                                             'snapshot_age_seconds': 5, 'refresh': worker.refresh})
                if self.headers.get('x-screener-worker-key') != KEY:
                    return self.answer(401, {'error': {'code': 'UNAUTHORIZED'}})
                if worker.down:
                    return self.answer(503, raw=b'<html>Service Unavailable</html>')
                if worker.not_ready:
                    return self.answer(503, {'error': {'code': 'SCREENER_NOT_READY', 'message': 'No snapshot is loaded yet.',
                                                       'details': {'retry_after_seconds': worker.not_ready}}})
                if self.path in worker.delay and not self.held(worker.delay[self.path]):
                    return
                if self.path in worker.timeout_paths:
                    if not worker.timeout_error:
                        return self.answer(504, raw=b'<html>Gateway Timeout</html>')
                    return self.answer(504, {'error': {'code': 'TIMEOUT', 'message': 'The screen took longer than 20 s.',
                                                       'details': {'costliest': 'a'}}})
                if self.path in worker.garbage:
                    return self.answer(200, raw=b'{"versions": NaN')
                if self.path in worker.refuse:
                    status, error = worker.refuse[self.path]
                    return self.answer(status, {'error': error})
                with worker.lock:
                    pending = worker.pending.get(self.path, 0)
                    if pending:
                        worker.pending[self.path] = pending - 1
                if pending:
                    return self.answer(409, {'error': {'code': 'DATA_VERSION_PENDING',
                                                       'message': 'This replica has not loaded that publication yet.'}})
                route = (method, self.path)
                if route == ('GET', '/v1/catalog'):
                    return self.answer(200, {'versions': v, 'data': {**self.data(), 'refresh': worker.refresh},
                                             'limits': worker.limits, 'indicators': [], 'metrics': [], 'fundamentals': [],
                                             'periods': {'1M': 21, '3M': 63, '6M': 126, '1Y': 252}, 'groupings': [],
                                             'presets': []})
                if route == ('GET', '/v1/universe'):
                    return self.answer(200, {'versions': v, 'data': self.data(), 'rows': [
                        {'ticker': 'BBCA', 'name': 'Example Tbk', 'sector': 'Financials', 'industry': 'Banks', 'last': 1234,
                         'chg_1d_pct': -1.2, 'adv20_idr': 4.56e10, 'first_bar': '2018-01-02', 'last_bar': '2026-10-27',
                         'bars': 2000, 'stale': False, 'remarks': []}]})
                if route == ('POST', '/v1/run'):
                    return self.answer(200, {'schema_version': 1, 'versions': {**v, 'definition_hash': sha('run')},
                                             'data': self.data(), 'mode': 'screen', 'echo': body, 'need': 1,
                                             'match_count': worker.rows, 'near_count': 0,
                                             'rows': [{'ticker': f'T{k:04d}', 'status': 'match', 'cells': []}
                                                      for k in range(worker.rows)], 'warnings': []})
                if route == ('POST', '/v1/preview'):
                    return self.answer(200, {'versions': v, 'data': self.data(), 'ticker': body['ticker'], 'status': 'match'})
                if route == ('POST', '/v1/counts'):
                    return self.answer(200, {'versions': {**v, 'definition_hash': sha('counts')}, 'data': self.data(),
                                             'counts': [{'item_id': d['item_id'], 'match_count': 1, 'near_count': 0}
                                                        for d in body['definitions']]})
                if route == ('POST', '/v1/validate'):
                    for k, condition in enumerate(body['definition'].get('conditions') or []):
                        params = ((condition.get('test') or {}).get('metric') or {}).get('params') or {}
                        if params.get('length', 0) > worker.max_length:
                            return self.answer(422, {'error': {
                                'code': 'PARAM_OUT_OF_RANGE', 'field': f'conditions[{k}].test.metric.params.length',
                                'message': f'length is at most {worker.max_length}.',
                                'details': {'field': 'length', 'min': 1, 'max': worker.max_length}}})
                    return self.answer(200, {'valid': True, 'definition_hash': sha(json.dumps(body['definition'], sort_keys=True)),
                                             'normalized': body['definition'], **({'versions': v} if worker.validate_versions else {})})
                return self.answer(404, {'error': {'code': 'NOT_FOUND'}})

            def do_GET(self):
                self.handle_one('GET')

            def do_POST(self):
                self.handle_one('POST')

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.url = f'http://127.0.0.1:{self.server.server_address[1]}'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def called(self, path, method=None):
        return [c for c in self.calls if c['path'] == path and (method is None or c['method'] == method)]

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def worker():
    fake = FakeScreenerWorker()
    yield fake
    fake.close()


@pytest.fixture
def configured(settings, store, worker):
    # test values: the fake worker answers at once
    return dataclasses.replace(settings, screener_worker_url=worker.url, screener_worker_key=KEY, screener_timeout_seconds=20)


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


def db(c, sql, *args):
    with c.app.state.store.connect() as conn:
        cur = conn.execute(sql, args)
        return cur.fetchall() if cur.description else cur.rowcount


def item_id(n):
    return 'scr_' + f'{n:032x}'


def put(c, n, body):
    return c.put(f'/api/v1/screener/items/{item_id(n)}', headers=c.headers_for, json=body)


def error(code, field=None, message=None, details=None):
    return {'error': {'code': code, **({'field': field} if field else {}),
                      'message': message or screener.MESSAGES[code], **({'details': details} if details else {})}}


# ---- catalog and universe ------------------------------------------------------------------------------------------

def test_catalog_and_universe_are_kept_per_worker_state_with_an_etag(app, worker):
    """Report 8.4 and PAGE LOAD SEQUENCE 6c.5: the catalog and the universe are fetched once per worker state (its
    /health versions and refresh, read at most every 60 s), answered with ETag = sha256 of the JSON bytes and 304 for
    If-None-Match, gzip when the client takes it, under the house no-store. edge-bff adds its own limits to the
    catalog's limits[] (rule and examples generated from the values); a limit the worker lists is kept as it is."""
    c = app
    first = c.get('/api/v1/screener/catalog')
    assert first.status_code == 200 and first.headers['content-encoding'] == 'gzip'
    assert first.headers['etag'] == '"' + hashlib.sha256(first.content).hexdigest() + '"'
    assert first.headers['cache-control'] == 'no-store' and first.headers['x-content-type-options'] == 'nosniff'
    body = first.json()
    assert body['versions'] == worker.versions and body['data']['refresh'] == 'ready'
    names = [x['name'] for x in body['limits']]
    assert names == ['max_conditions', 'saved_items', 'watchlist', 'saved_definition_bytes', 'request_bytes',
                     'inflight_per_page']
    assert all(set(x) == {'name', 'value', 'unit', 'rule', 'example_ok', 'example_refused'} and all(x.values())
               for x in body['limits'])
    saved = body['limits'][1]
    assert saved == {'name': 'saved_items', 'value': 50, 'unit': 'saved items',
                     'rule': 'at most 50 saved screens and 50 My metrics',
                     'example_ok': 'saving a new screen while 49 are saved',
                     'example_refused': 'saving a new screen while 50 are saved (delete one first)'}
    plain = c.get('/api/v1/screener/catalog', headers={'Accept-Encoding': 'identity'})
    assert 'content-encoding' not in plain.headers and plain.content == first.content and plain.headers['etag'] == first.headers['etag']
    same = c.get('/api/v1/screener/catalog', headers={'If-None-Match': first.headers['etag']})
    assert same.status_code == 304 and same.content == b'' and same.headers['etag'] == first.headers['etag']
    assert same.headers['cache-control'] == 'no-store'
    assert c.get('/api/v1/screener/catalog', headers={'If-None-Match': 'W/' + first.headers['etag'] + ', "x"'}).status_code == 304
    assert c.get('/api/v1/screener/catalog', headers={'If-None-Match': '"other"'}).status_code == 200
    universe = c.get('/api/v1/screener/universe')
    assert universe.status_code == 200 and universe.json()['rows'][0]['ticker'] == 'BBCA'
    assert universe.headers['etag'] == '"' + hashlib.sha256(universe.content).hexdigest() + '"'
    assert c.get('/api/v1/screener/universe', headers={'If-None-Match': universe.headers['etag']}).status_code == 304
    assert len(worker.called('/v1/catalog')) == 1 and len(worker.called('/v1/universe')) == 1
    assert len(worker.called('/health')) == 1 and worker.called('/health')[0]['key'] is None   # /health takes no key
    # the worker's state changes: seen at the next /health read (at most 60 s later), then fetched again
    sc = c.app.state.screeners
    worker.versions = versions('b')
    assert c.get('/api/v1/screener/catalog').headers['etag'] == first.headers['etag']        # within the 60 s
    sc.health['at'] = None
    newer = c.get('/api/v1/screener/catalog', headers={'If-None-Match': first.headers['etag']})
    assert newer.status_code == 200 and newer.json()['versions'] == versions('b') and newer.headers['etag'] != first.headers['etag']
    # the refresh state alone changes the catalog's data.refresh: fetched again too
    worker.refresh = 'failed_keeping_previous'
    sc.health['at'] = None
    assert c.get('/api/v1/screener/catalog').json()['data']['refresh'] == 'failed_keeping_previous'
    assert len(worker.called('/v1/catalog')) == 3
    # the worker down: the last ones are kept
    worker.down, sc.health['at'] = True, None
    worker.versions = versions('c')
    assert c.get('/api/v1/screener/catalog').json()['versions'] == versions('b')
    # a limit the worker lists itself is not replaced
    worker.down, worker.limits = False, [{'name': 'watchlist', 'value': 7, 'unit': 'tickers', 'rule': 'x', 'example_ok': 'y',
                                          'example_refused': 'z'}]
    sc.health['at'] = None
    limits = c.get('/api/v1/screener/catalog').json()['limits']
    assert [x['name'] for x in limits] == ['watchlist', 'saved_items', 'saved_definition_bytes', 'request_bytes',
                                           'inflight_per_page']
    assert limits[0]['value'] == 7


def test_own_limits_are_plain_words_and_equal_the_page_tests_copy():
    """The words of edge-bff's limits are shown as they are (Method & sources; a refusal quotes the rule, "this one
    needs N <unit>" and the fix in the closing parenthesis of example_refused), so they name no limit or code; the
    page tests read them from screener/tests/fixture/edge-bff-limits.json, which must equal own_limits() (its walk,
    screener/tests/page/plain-words.test.ts, checks the words with the page's pattern)."""
    copy = json.loads((Path(__file__).resolve().parents[1] / 'screener/tests/fixture/edge-bff-limits.json').read_text())
    assert screener.own_limits() == copy
    for x in screener.own_limits():
        for k in ('unit', 'rule', 'example_ok', 'example_refused'):
            assert '_' not in x[k] and 'replica' not in x[k], (x['name'], k, x[k])
        assert x['example_refused'].rstrip().endswith(')'), x['name']   # the fix the page takes (texts.ts fixOf)


def test_a_newer_publication_seen_in_a_run_drops_the_cached_catalog_at_once(app, worker):
    """PAGE LOAD SEQUENCE 6c.5 item 4: a worker answer at another price_data than the cached catalog's means the
    worker swapped its snapshot; the cached catalog and universe are dropped then, not up to 60 s later."""
    c = app
    first = c.get('/api/v1/screener/catalog').headers['etag']
    c.get('/api/v1/screener/universe')
    worker.versions = versions('b')
    assert c.post('/api/v1/screener/run', headers=c.headers_for, json=run_body()).status_code == 200
    again = c.get('/api/v1/screener/catalog', headers={'If-None-Match': first})
    assert again.status_code == 200 and again.json()['versions']['price_data'] == sha('price-b')
    assert c.get('/api/v1/screener/universe').json()['versions']['price_data'] == sha('price-b')
    assert len(worker.called('/v1/catalog')) == 2 and len(worker.called('/v1/universe')) == 2
    # an answer at the same price_data drops nothing
    assert c.post('/api/v1/screener/preview', headers=c.headers_for, json=preview_body()).status_code == 200
    c.get('/api/v1/screener/catalog')
    assert len(worker.called('/v1/catalog')) == 2


# ---- run, preview, validate, counts ---------------------------------------------------------------------------------

def test_run_preview_validate_and_counts_are_relayed_as_sent(app, worker):
    """The page's body reaches the worker as it was sent (client_order included: contract.ts RunRequest and
    PreviewRequest carry it); the worker's JSON comes back as its bytes, gzip when taken; its 4xx refusals are relayed
    with their status, code, field, message and details. A large answer is parsed and packed off the event loop."""
    c = app
    body = run_body()
    r = c.post('/api/v1/screener/run', headers=c.headers_for, json=body)
    assert r.status_code == 200 and r.headers['content-encoding'] == 'gzip' and r.json()['echo'] == body
    assert worker.called('/v1/run')[0]['body'] == body and worker.called('/v1/run')[0]['key'] == KEY
    p = c.post('/api/v1/screener/preview', headers=c.headers_for, json=preview_body(ticker='TLKM'))
    assert p.status_code == 200 and p.json()['ticker'] == 'TLKM'
    v = c.post('/api/v1/screener/validate', headers=c.headers_for, json={'schema_version': 1, 'definition': definition()})
    assert v.status_code == 200 and v.json()['valid'] is True
    n = c.post('/api/v1/screener/counts', headers=c.headers_for,
               json={'schema_version': 1, 'definitions': [{'item_id': item_id(1), 'definition': definition()}]})
    assert n.status_code == 200 and n.json()['counts'] == [{'item_id': item_id(1), 'match_count': 1, 'near_count': 0}]
    worker.rows = 2000                                                       # about 0.1 MB of JSON
    big = c.post('/api/v1/screener/run', headers=c.headers_for, json=run_body(seq=2))
    assert big.status_code == 200 and len(big.json()['rows']) == 2000 and big.headers['content-encoding'] == 'gzip'
    assert len(big.content) > screener.INLINE_BYTES
    # the worker's refusals, as it gave them
    refusals = {'/v1/run': (422, {'code': 'INVALID_CONDITION', 'field': 'definition.conditions[0].test.value2',
                                  'message': 'between needs value <= value2.', 'details': {'allowed': ['gt', 'lt', 'between']}}),
                '/v1/preview': (409, {'code': 'DATA_VERSION_CHANGED', 'message': 'New data was published; the screen is re-run.'}),
                '/v1/counts': (409, {'code': 'BUSY', 'message': 'The screener is busy; retry in a few seconds'}),
                '/v1/validate': (424, {'code': 'DATA_UNAVAILABLE', 'message': 'No published data is loaded yet.'})}
    worker.refuse = refusals
    for path, payload in (('/v1/run', run_body(seq=3)), ('/v1/preview', preview_body(seq=2)),
                          ('/v1/counts', {'schema_version': 1, 'definitions': []}),
                          ('/v1/validate', {'schema_version': 1, 'definition': definition()})):
        status, found = refusals[path]
        r = c.post('/api/v1/screener/' + path.rsplit('/', 1)[1], headers=c.headers_for, json=payload)
        assert r.status_code == status and r.json() == {'error': found}, path
    # bodies edge-bff refuses itself: never relayed
    calls = len(worker.calls)
    for raw in (b'[1]', b'{"x": 1e400}', b'{"x": NaN}', rb'{"x": "\ud800"}', b'not json'):
        bad = c.post('/api/v1/screener/run', headers={**c.headers_for, 'content-type': 'application/json'}, content=raw)
        assert bad.status_code == 422 and bad.json()['error']['code'] == 'INVALID_INPUT' and bad.json()['error']['message'], raw
    for order in ({'page': 'pg_1'}, {'page': 'pg_1', 'seq': -1}, {'page': 'pg_1', 'seq': True}, {'page': 'a page', 'seq': 1}, [1]):
        bad = c.post('/api/v1/screener/run', headers=c.headers_for, json={**run_body(), 'client_order': order})
        assert bad.status_code == 422 and bad.json()['error']['field'] == 'client_order', order
    assert len(worker.calls) == calls


def test_worker_failures_map_to_the_contract(app, worker, caplog):
    """Report 8.1 and 8.8: the worker's own 504 TIMEOUT is relayed as 504 with its error; its 503 SCREENER_NOT_READY as
    503 with Retry-After from the seconds it names; anything else outside its API (a server error, a bare 504, an answer
    that is not JSON, our key refused) is 503 SCREENER_UNAVAILABLE, each with the message naming the fix."""
    c = app
    post = lambda: c.post('/api/v1/screener/run', headers=c.headers_for, json=run_body())
    worker.timeout_paths = {'/v1/run'}
    r = post()
    assert r.status_code == 504 and r.json() == {'error': {'code': 'TIMEOUT', 'message': 'The screen took longer than 20 s.',
                                                           'details': {'costliest': 'a'}}}
    worker.timeout_error = False
    assert post().json() == error('SCREENER_UNAVAILABLE') and post().status_code == 503
    worker.timeout_paths = set()
    worker.not_ready = 7
    r = post()
    assert r.status_code == 503 and r.headers['retry-after'] == '7' and r.json()['error']['code'] == 'SCREENER_NOT_READY'
    worker.not_ready = None
    worker.down = True
    r = post()
    assert r.status_code == 503 and r.json() == error('SCREENER_UNAVAILABLE')
    assert c.get('/api/v1/screener/catalog').json() == error('SCREENER_UNAVAILABLE')       # nothing kept yet
    worker.down = False
    worker.garbage = {'/v1/run'}
    assert post().json() == error('SCREENER_UNAVAILABLE')
    worker.garbage = set()
    c.app.state.screeners.worker.settings = dataclasses.replace(c.app.state.screeners.worker.settings, screener_worker_key='k' * 40)
    with caplog.at_level(logging.ERROR, logger='edge_bff.screener'):
        assert post().json() == error('SCREENER_UNAVAILABLE')
    assert 'screener_worker_key_refused' in caplog.text and 'k' * 40 not in caplog.text and KEY not in caplog.text


def test_every_worker_call_but_health_carries_the_owner_tag(app, worker):
    """Report 8.11 and 6d.6: edge-bff sends x-screener-owner, the first 16 hex of HMAC-SHA256(SCREENER_WORKER_KEY,
    owner_key), with the key on every worker call except /health, so the worker can share its threads fairly per owner
    without learning the owner's key."""
    c = app
    c.get('/api/v1/screener/catalog')
    c.get('/api/v1/screener/universe')
    c.post('/api/v1/screener/run', headers=c.headers_for, json=run_body())
    c.post('/api/v1/screener/preview', headers=c.headers_for, json=preview_body())
    c.post('/api/v1/screener/counts', headers=c.headers_for, json={'schema_version': 1, 'definitions': []})
    assert put(c, 1, screen_item()).status_code == 200
    tag = hmac.new(KEY.encode(), c.app.state.screeners.settings.owner.encode(), hashlib.sha256).hexdigest()[:16]
    assert {x['path'] for x in worker.calls} == {'/health', '/v1/catalog', '/v1/universe', '/v1/run', '/v1/preview',
                                                 '/v1/counts', '/v1/validate'}
    for call in worker.calls:
        expected = (None, None) if call['path'] == '/health' else (KEY, tag)
        assert (call['key'], call['owner']) == expected, call['path']
    assert c.app.state.screeners.settings.owner not in tag


def test_relayed_answers_are_the_workers_gzip_bytes_never_parsed(app, worker, monkeypatch):
    """Report 6d.5 and 8.11: a run, preview, counts or validate answer the worker sent gzip goes to a browser as the
    worker's bytes with its ETag, without being inflated or parsed here (only its versions are read from its head); a
    client that takes no gzip gets the JSON bytes inflated. A gzip stream that is broken is an answer outside the
    worker's API."""
    c = app
    parses = []
    real = screener.parsed
    async def counted(raw):
        parses.append(len(raw))
        return await real(raw)
    monkeypatch.setattr(screener, 'parsed', counted)
    worker.rows = 2000
    with c.stream('POST', '/api/v1/screener/run', headers=c.headers_for, json=run_body()) as r:
        assert r.status_code == 200 and r.headers['content-encoding'] == 'gzip'
        assert b''.join(r.iter_raw()) == worker.sent['/v1/run']                 # the worker's own gzip bytes
        etag = r.headers['etag']
    assert parses == []
    inflated = gzip.decompress(worker.sent['/v1/run'])
    assert etag == '"' + hashlib.sha256(inflated).hexdigest() + '"'
    plain = c.post('/api/v1/screener/run', headers={**c.headers_for, 'Accept-Encoding': 'identity'}, json=run_body(seq=2))
    assert plain.status_code == 200 and 'content-encoding' not in plain.headers
    assert plain.content == gzip.decompress(worker.sent['/v1/run'])          # inflated for a client without gzip
    assert plain.headers['etag'] == '"' + hashlib.sha256(plain.content).hexdigest() + '"'
    for path, body in (('preview', preview_body()), ('counts', {'schema_version': 1, 'definitions': []}),
                       ('validate', {'schema_version': 1, 'definition': definition()})):
        r = c.post('/api/v1/screener/' + path, headers=c.headers_for, json=body)
        assert r.status_code == 200 and r.headers['content-encoding'] == 'gzip', path
    assert parses == []
    # a newer publication in a relayed answer is still seen (its head): the catalog is fetched again
    c.get('/api/v1/screener/catalog')
    worker.versions, worker.published = versions('b'), '2026-10-28T00:03:00Z'
    assert c.post('/api/v1/screener/run', headers=c.headers_for, json=run_body(seq=3)).status_code == 200
    assert c.get('/api/v1/screener/catalog').json()['versions']['price_data'] == sha('price-b')
    # a broken gzip stream from the worker
    monkeypatch.setattr(screener, 'peeked', lambda gz: (_ for _ in ()).throw(ValueError('broken')))
    assert c.post('/api/v1/screener/run', headers=c.headers_for, json=run_body(seq=4)).json() == error('SCREENER_UNAVAILABLE')


def test_a_pending_data_version_is_asked_once_more_on_a_new_connection_then_not_ready(app, worker):
    """Report 8.8 and 6d.4 rule 3: the worker-only 409 DATA_VERSION_PENDING (a replica that has not loaded the requested
    publication yet) never reaches the page: edge-bff asks once more on a new connection (another replica where the
    private network spreads connections); a second one is 503 SCREENER_NOT_READY with Retry-After 2."""
    c = app
    assert c.post('/api/v1/screener/run', headers=c.headers_for, json=run_body()).status_code == 200
    worker.calls.clear()
    worker.pending = {'/v1/run': 1}
    r = c.post('/api/v1/screener/run', headers=c.headers_for, json=run_body(seq=2))
    assert r.status_code == 200 and r.json()['echo']['client_order']['seq'] == 2
    ports = [x['port'] for x in worker.called('/v1/run')]
    assert len(ports) == 2 and ports[0] != ports[1]                          # the retry: a new connection
    worker.calls.clear()
    worker.pending = {'/v1/preview': 2}
    r = c.post('/api/v1/screener/preview', headers=c.headers_for, json=preview_body())
    assert r.status_code == 503 and r.headers['retry-after'] == '2'
    assert r.json()['error']['code'] == 'SCREENER_NOT_READY' and 'retry' in r.json()['error']['message']
    assert len(worker.called('/v1/preview')) == 2
    worker.pending = {'/v1/counts': 1}
    assert c.post('/api/v1/screener/counts', headers=c.headers_for, json={'schema_version': 1, 'definitions': []}).status_code == 200


def test_worker_refusals_outside_the_contract_are_unavailable(app, worker, caplog):
    """Only the worker's refusals of report 8.8, each at its status, are passed on; a route the worker does not have,
    a code outside the contract or a code at another status is an answer outside its API: 503 SCREENER_UNAVAILABLE,
    logged with its status and code only (never its message)."""
    c = app
    post = lambda: c.post('/api/v1/screener/run', headers=c.headers_for, json=run_body())
    for status, found in ((404, {'code': 'NOT_FOUND', 'message': 'no route /v1/run on http://x.railway.internal:8080'}),
                          (422, {'code': 'SOMETHING_ELSE', 'message': 'secret detail'}),
                          (400, {'code': 'INVALID_INPUT', 'message': 'wrong status'}),
                          (409, {'code': 'REVISION_CONFLICT'})):
        worker.refuse = {'/v1/run': (status, found)}
        with caplog.at_level(logging.WARNING, logger='edge_bff.screener'):
            r = post()
        assert r.status_code == 503 and r.json() == error('SCREENER_UNAVAILABLE'), found
        assert found['code'] in caplog.text and 'secret detail' not in caplog.text and 'railway.internal' not in caplog.text
    worker.refuse = {'/v1/run': (413, {'code': 'REQUEST_TOO_LARGE', 'message': 'at most 65536 bytes'})}
    assert post().status_code == 413
    # a refusal of the contract is passed on, with any internal address in it redacted, and never the key
    worker.refuse = {'/v1/run': (422, {'code': 'INVALID_CONDITION', 'field': 'definition.logic',
                                       'message': 'see http://screener-worker.railway.internal:8080/v1/run',
                                       'details': {'allowed': ['all', 'any', 'at_least'], 'from': 'screener-worker.railway.internal'}})}
    r = post()
    assert r.status_code == 422 and r.json()['error']['field'] == 'definition.logic'
    assert 'railway.internal' not in r.text and KEY not in r.text and '[internal address]' in r.json()['error']['message']


def test_an_answer_over_the_read_cap_is_unavailable(app, worker, monkeypatch, caplog):
    """edge-bff reads at most WORKER_ANSWER_BYTES of one worker answer, as received and inflated (report 6d.5)."""
    c = app
    worker.rows = 2000
    monkeypatch.setattr(screener, 'WORKER_ANSWER_BYTES', 4096)
    with caplog.at_level(logging.ERROR, logger='edge_bff.screener'):
        r = c.post('/api/v1/screener/run', headers={**c.headers_for, 'Accept-Encoding': 'identity'}, json=run_body())
    assert r.status_code == 503 and r.json() == error('SCREENER_UNAVAILABLE')
    assert 'screener_worker_answer_too_large' in caplog.text
    with pytest.raises(ValueError):
        screener.inflate(gzip.compress(b'x' * 5000))                       # small as received, too large inflated


def test_the_catalog_never_goes_back_and_ignores_transient_refresh_states(app, worker):
    """Report 6d.5 and 8.10: the catalog is replaced only by a later publication (a replica that has not swapped yet
    may answer), the transient refresh states of /health (refreshing, loading) change no catalog byte and fetch nothing,
    and an answer at an older publication (the previous snapshot in its grace window, 6d.4 rule 2) drops nothing."""
    c = app
    sc = c.app.state.screeners
    worker.versions, worker.published = versions('b'), '2026-10-28T00:03:00Z'
    newer = c.get('/api/v1/screener/catalog')
    assert newer.json()['data']['published_at'] == '2026-10-28T00:03:00Z'
    worker.refresh, sc.health['at'] = 'refreshing', None
    assert c.get('/api/v1/screener/catalog').headers['etag'] == newer.headers['etag']
    assert len(worker.called('/v1/catalog')) == 1
    # a replica at the previous publication answers /health and the catalog: the newer one stays
    worker.versions, worker.published, worker.refresh, sc.health['at'] = versions('a'), '2026-10-27T13:03:23Z', 'ready', None
    assert c.get('/api/v1/screener/catalog').headers['etag'] == newer.headers['etag']
    assert len(worker.called('/v1/catalog')) == 2
    assert c.get('/api/v1/screener/catalog').headers['etag'] == newer.headers['etag']
    assert len(worker.called('/v1/catalog')) == 2                            # kept for this state: no fetch storm
    # a run answered at that previous publication drops nothing
    assert c.post('/api/v1/screener/run', headers=c.headers_for, json=run_body()).status_code == 200
    assert c.get('/api/v1/screener/catalog').headers['etag'] == newer.headers['etag']
    assert len(worker.called('/v1/catalog')) == 2


def test_the_catalog_and_universe_follow_a_publication_that_keeps_the_versions(app, worker):
    """A publication with the same files keeps the worker's snapshot and its versions (an advance, 6.5 rule 3) while the
    worker answers from the new one: its published_at and broker lag, and its availability (ERRORS M299: taken again at
    every advance). /health names that published_at, so the catalog and the universe edge-bff keeps are fetched again,
    never served at the publication before; the same state again fetches nothing (review of the last guards)."""
    c = app
    sc = c.app.state.screeners
    assert c.get('/api/v1/screener/catalog').json()['data']['published_at'] == '2026-10-27T13:03:23Z'
    assert c.get('/api/v1/screener/universe').json()['data']['published_at'] == '2026-10-27T13:03:23Z'
    worker.published, sc.health['at'] = '2026-10-27T23:00:00Z', None          # the same versions, a later publication
    for path in ('catalog', 'universe'):
        assert c.get(f'/api/v1/screener/{path}').json()['data']['published_at'] == '2026-10-27T23:00:00Z', path
    assert [len(worker.called('/v1/catalog')), len(worker.called('/v1/universe'))] == [2, 2]
    sc.health['at'] = None
    assert c.get('/api/v1/screener/catalog').json()['data']['published_at'] == '2026-10-27T23:00:00Z'
    assert len(worker.called('/v1/catalog')) == 2


# ---- latest wins per owner ------------------------------------------------------------------------------------------

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
    with httpx.Client(base_url=local.origin, timeout=60) as h:
        r = h.post('/api/v1/auth/sign-in', headers={'Origin': local.origin}, json={'login': 'owner', 'password': 'local-test-password'})
        return {'Origin': local.origin, 'X-CSRF-Token': r.json()['csrf_token']}, dict(h.cookies)


def wait_for(check, seconds=5):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if check():
            return True
        time.sleep(0.01)
    return False


def test_a_newer_run_of_the_page_ends_its_one_in_flight_and_other_pages_and_previews_are_their_own(configured, store, worker):
    """Report 8.1, 8.9 and 6d.6 (one screen and one preview in flight per (owner, page), latest wins; backtest.py
    latest_preview): a run that arrives while an older one of the same page still waits at the worker ends that one at
    once (its worker call is closed, it answers 409 SCREEN_REPLACED) and is sent once that call has ended. A run of
    another page (a second tab, or another person on today's one login) and a preview in flight are not ended by it."""
    wait = 2.0
    worker.delay = {'/v1/run': wait, '/v1/preview': wait}
    local, stop = serve(configured, store)
    try:
        headers, cookies = sign_in(local)
        def post(path, body):
            with httpx.Client(base_url=local.origin, timeout=60, cookies=cookies) as h:
                return h.post(path, headers=headers, json=body)
        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            shown = pool.submit(post, '/api/v1/screener/preview', preview_body(page='pg_a'))
            first = pool.submit(post, '/api/v1/screener/run', run_body(seq=1, page='pg_a'))
            other = pool.submit(post, '/api/v1/screener/run', run_body(seq=1, page='pg_b'))
            assert wait_for(lambda: len(worker.called('/v1/run')) == 2 and worker.called('/v1/preview'))
            arrived = time.monotonic()
            second = pool.submit(post, '/api/v1/screener/run', run_body(seq=2, page='pg_a'))
            ended = first.result()
            assert time.monotonic() - arrived < wait / 2
            assert ended.status_code == 409 and ended.json() == error('SCREEN_REPLACED')
            answered = second.result()
            assert answered.status_code == 200 and answered.json()['echo']['client_order'] == {'page': 'pg_a', 'seq': 2}
            assert other.result().status_code == 200                            # another page: never replaced
            assert shown.result().status_code == 200                            # the preview's own lane
        assert sorted((x['body']['client_order']['page'], x['body']['client_order']['seq']) for x in worker.called('/v1/run')) == [
            ('pg_a', 1), ('pg_a', 2), ('pg_b', 1)]
        assert worker.abandoned == ['/v1/run']                                 # the older run's call, closed by edge-bff
    finally:
        stop()


def test_a_call_its_page_sent_before_a_newer_one_that_arrived_first_never_reaches_the_worker(app, worker, monkeypatch):
    """client_order is the page's own order (ERRORS M247): a run or preview its page had already sent a newer one of
    answers 409 at once and is never relayed; the same seq again (a retry) and another page are relayed; the order is
    kept per lane, for the PREVIEW_PAGES pages whose calls arrived last."""
    c = app
    run = lambda seq, page='pg_1': c.post('/api/v1/screener/run', headers=c.headers_for, json=run_body(seq, page))
    preview = lambda seq, page='pg_1': c.post('/api/v1/screener/preview', headers=c.headers_for, json=preview_body(seq, page))
    assert run(5).status_code == 200
    late = run(4)
    assert late.status_code == 409 and late.json() == error('SCREEN_REPLACED')
    assert [run(5).status_code, run(6).status_code, run(1, 'pg_2').status_code] == [200, 200, 200]
    assert preview(1).status_code == 200                                     # the preview lane keeps its own order
    late = preview(0)
    assert late.status_code == 409 and late.json() == error('PREVIEW_REPLACED')
    no_order = {k: v for k, v in run_body().items() if k != 'client_order'}
    assert c.post('/api/v1/screener/run', headers=c.headers_for, json=no_order).status_code == 200
    assert len(worker.called('/v1/run')) == 5 and len(worker.called('/v1/preview')) == 1
    sc = c.app.state.screeners
    assert sc.flight == {} and sc.pages[(sc.settings.owner, 'run')] == {'pg_1': 6, 'pg_2': 1}
    monkeypatch.setattr(screener, 'PREVIEW_PAGES', 1)
    assert run(1, 'pg_3').status_code == 200                                 # pg_1 and pg_2 forgotten
    assert run(1).status_code == 200                                         # relayed: its order is not known any more


def test_a_run_its_caller_left_is_stopped_at_the_worker(configured, store, worker):
    """A run whose caller went away before the worker answered (the page aborted it for a newer edit) is cancelled
    here, which closes its connection to the worker, and leaves its owner's place free."""
    worker.delay = {'/v1/run': 5.0}
    local, stop = serve(configured, store)
    try:
        headers, cookies = sign_in(local)
        with httpx.Client(base_url=local.origin, timeout=60, cookies=cookies) as h:
            with pytest.raises(httpx.ReadTimeout):
                h.post('/api/v1/screener/run', headers=headers, json=run_body(), timeout=httpx.Timeout(60, read=0.3))
        assert wait_for(lambda: worker.abandoned)
        assert worker.abandoned == ['/v1/run']
        worker.delay = {}
        with httpx.Client(base_url=local.origin, timeout=60, cookies=cookies) as h:
            assert h.post('/api/v1/screener/run', headers=headers, json=run_body(seq=2)).status_code == 200
    finally:
        stop()


# ---- authentication, CSRF, feature switches -------------------------------------------------------------------------

def test_session_origin_and_csrf_are_required_and_every_write_route_checks_them(app, worker):
    """Every screener route needs the session; every POST, PUT and DELETE also the exact Origin and the CSRF token
    (report 8.1; the class of ERRORS M259): a route list walk fails on a write route without the write dependency."""
    c = app
    writes = [r for r in c.app.routes if getattr(r, 'path', '').startswith('/api/v1/screener/')
              and set(getattr(r, 'methods', ())) & {'POST', 'PUT', 'PATCH', 'DELETE'}]
    assert len(writes) == len(WRITE_ROUTES)
    assert [r.path for r in writes if 'write' not in {d.call.__name__ for d in r.dependant.dependencies}] == []
    assert sorted((m, r.path) for r in writes for m in r.methods) == sorted(
        (m, p.replace('scr_' + '1' * 32, '{item_id}').replace('/BBCA', '/{ticker}')) for m, p in WRITE_ROUTES)
    h = c.headers_for
    c.cookies.clear()
    for path in READ_ROUTES:
        assert c.get(path).status_code == 401, path
    for method, path in WRITE_ROUTES:
        assert c.request(method, path, headers=h, json={}).status_code == 401, path
    h = login(c)
    for method, path in WRITE_ROUTES:
        assert c.request(method, path, headers=ORIGIN, json={}).status_code == 403, path                       # no token
        assert c.request(method, path, headers={'X-CSRF-Token': h['X-CSRF-Token']}, json={}).status_code == 403, path   # no Origin
        assert c.request(method, path, headers={**h, 'X-CSRF-Token': '0' * 64}, json={}).status_code == 403, path
        assert c.request(method, path, headers={**h, 'Origin': 'https://evil.example'}, json={}).status_code == 403, path
    assert worker.calls == [] and db(c, 'SELECT count(*) AS n FROM edge_bff.watchlist_items')[0]['n'] == 0


def test_feature_off_without_a_worker(settings, store):
    with TestClient(create_app(settings, store, FakeOrc())) as c:
        h = login(c)
        for path in READ_ROUTES:
            r = c.get(path)
            assert r.status_code == 503 and r.json() == error('SCREENER_DISABLED'), path
        for method, path in WRITE_ROUTES:
            r = c.request(method, path, headers=h, json={})
            assert r.status_code == 503 and r.json() == error('SCREENER_DISABLED'), path


def test_tables_missing_is_not_ready_and_the_rest_of_edge_is_unaffected(app, worker, database):
    """A missing screener table (the migration not applied yet) switches off only the screener: 503 SCREENER_NOT_READY
    with Retry-After, before any worker call; /ready and the rest of EDGE answer. A rerun of the migration is refused
    by its preflight, and the runtime role holds exactly what screener.py does to each table."""
    c = app
    with psycopg.connect(database, autocommit=True) as conn:
        conn.execute(ROLLBACK)
    try:
        c.app.state.screeners.ready = False
        assert c.get('/ready').json() == {'status': 'ready'}
        for r in (c.get('/api/v1/screener/items'), c.get('/api/v1/screener/catalog'),
                  c.post('/api/v1/screener/run', headers=c.headers_for, json=run_body())):
            assert r.status_code == 503 and r.headers['retry-after'] == '60'
            assert r.json()['error']['code'] == 'SCREENER_NOT_READY' and 'retry' in r.json()['error']['message']
        assert worker.calls == []
        assert c.get('/api/v1/conversations').status_code == 200
    finally:
        with psycopg.connect(database, autocommit=True) as conn:
            conn.execute(MIGRATION.read_text())
    assert c.get('/api/v1/screener/items').json() == {'items': []}
    with psycopg.connect(database, autocommit=True) as conn:
        with pytest.raises(psycopg.errors.RaiseException, match='screener table exists'):
            conn.execute(MIGRATION.read_text())
        conn.execute('ROLLBACK')
        grants = conn.execute("""SELECT table_name, string_agg(privilege_type, ',' ORDER BY privilege_type) AS p
            FROM information_schema.role_table_grants WHERE grantee='edge_bff_runtime'
            AND table_name IN ('screener_items', 'watchlist_items') GROUP BY table_name ORDER BY table_name""").fetchall()
        public = conn.execute("""SELECT count(*) FROM information_schema.role_table_grants WHERE grantee='PUBLIC'
            AND table_name IN ('screener_items', 'watchlist_items')""").fetchone()[0]
    assert grants == [('screener_items', 'DELETE,INSERT,SELECT,UPDATE'), ('watchlist_items', 'DELETE,INSERT,SELECT')]
    assert public == 0


def test_a_body_over_the_house_cap_names_the_fix(app, worker):
    c = app
    r = c.post('/api/v1/screener/run', headers={**c.headers_for, 'content-type': 'application/json'},
               content=b'{"x":"' + b'a' * 131072 + b'"}')
    assert r.status_code == 413 and r.json() == {'error': {'code': 'REQUEST_TOO_LARGE', 'message': screener.MESSAGES['REQUEST_TOO_LARGE'],
                                                           'details': {'limit': 'request_bytes', 'allowed': 131072}}}
    assert worker.calls == []
    other = c.post('/api/v1/backtests/signals', headers={**c.headers_for, 'content-type': 'application/json'},
                   content=b'{"x":"' + b'a' * 131072 + b'"}')
    assert other.json() == {'error': {'code': 'REQUEST_TOO_LARGE'}}                # the house answer elsewhere


# ---- saved items ----------------------------------------------------------------------------------------------------

def test_saved_items_are_validated_created_replaced_and_deleted(app, worker):
    """Report 8.7: PUT without revision creates, with the revision it was read with replaces (revision + 1), a stale one
    is 409 REVISION_CONFLICT; a name another item of the kind has is 409 NAME_TAKEN; an item keeps its kind; DELETE is
    204 then 404 NOT_FOUND. Every definition is validated by the worker first, and stored as sent with the versions
    and definition_hash of that validation."""
    c = app
    r = put(c, 1, screen_item())
    assert r.status_code == 200, r.text
    item = r.json()
    sent = worker.called('/v1/validate')[0]['body']
    assert sent == {'schema_version': 1, 'definition': definition()}
    assert item['definition'] == screen_item()['definition'] and item['revision'] == 1 and item['needs_review'] == []
    assert (item['registry_version'], item['screener_registry_version']) == ('registry-a', 'sregistry-a')
    assert item['definition_hash'] == sha(json.dumps(definition(), sort_keys=True)) and item['schema_version'] == 1
    m = put(c, 2, metric_item())
    assert m.status_code == 200 and m.json()['kind'] == 'metric'
    assert worker.called('/v1/validate')[1]['body'] == {'schema_version': 1, 'definition': {
        'universe': screener.METRIC_UNIVERSE, 'conditions': [{'id': 'm', 'enabled': True, 'test': rsi_test()}], 'logic': 'all'}}
    listed = c.get('/api/v1/screener/items?kind=screen').json()['items']
    assert [x['item_id'] for x in listed] == [item_id(1)] and listed[0] == item
    assert {x['item_id'] for x in c.get('/api/v1/screener/items').json()['items']} == {item_id(1), item_id(2)}
    assert put(c, 1, screen_item()).json() == error('REVISION_CONFLICT', details={'revision': 1})
    replaced = put(c, 1, screen_item('Oversold 2', 9, revision=1))
    assert replaced.status_code == 200 and replaced.json()['revision'] == 2 and replaced.json()['name'] == 'Oversold 2'
    assert replaced.json()['definition']['definition'] == definition(9) and replaced.json()['created_at'] == item['created_at']
    stale = put(c, 1, screen_item(revision=1))
    assert stale.status_code == 409 and stale.json() == error('REVISION_CONFLICT', 'revision', details={'revision': 2})
    taken = put(c, 3, screen_item('Oversold 2'))
    assert taken.status_code == 409 and taken.json() == error('NAME_TAKEN', 'name')
    assert put(c, 3, metric_item('Oversold 2')).status_code == 200            # a name is unique per kind
    kind = put(c, 2, screen_item('x', revision=1))
    assert kind.status_code == 422 and kind.json()['error']['field'] == 'kind'
    assert put(c, 9, screen_item(revision=1)).json() == error('NOT_FOUND')
    assert c.delete(f'/api/v1/screener/items/{item_id(1)}', headers=c.headers_for).status_code == 204
    gone = c.delete(f'/api/v1/screener/items/{item_id(1)}', headers=c.headers_for)
    assert gone.status_code == 404 and gone.json() == error('NOT_FOUND')
    assert c.delete('/api/v1/screener/items/scr_x', headers=c.headers_for).status_code == 404
    assert c.get('/api/v1/screener/items?kind=both').json()['error']['field'] == 'kind'


def test_a_saved_item_body_is_refused_by_field(app, worker):
    """Each refusal names the field and the fix; nothing is relayed or stored for it."""
    c = app
    cases = [
        ({**screen_item(), 'extra': 1}, 'extra'),
        ({**screen_item(), 'kind': 'list'}, 'kind'),
        ({**screen_item(), 'name': ''}, 'name'), ({**screen_item(), 'name': ' x'}, 'name'),
        ({**screen_item(), 'name': 'x' * 121}, 'name'), ({**screen_item(), 'name': 'a\nb'}, 'name'), ({**screen_item(), 'name': 5}, 'name'),
        ({**screen_item(), 'definition': []}, 'definition'),
        ({**screen_item(), 'definition': {'definition': definition(), 'other': 1}}, 'definition.other'),
        ({**screen_item(), 'definition': {'view': {}}}, 'definition.definition'),
        ({**screen_item(), 'definition': {'definition': definition(), 'view': []}}, 'definition.view'),
        ({**metric_item(), 'definition': {'test': rsi_test(), 'x': 1}}, 'definition.test'),
        ({**metric_item(), 'definition': {'test': 'rsi'}}, 'definition.test'),
        ({**screen_item(), 'definition': {'definition': {**definition(), 'logic': 'a\x00'}}}, 'definition'),
        ({**screen_item(), 'revision': True}, 'revision'), ({**screen_item(), 'revision': 0}, 'revision'),
        ({**screen_item(), 'revision': '1'}, 'revision'), ({**screen_item(), 'revision': 2 ** 63}, 'revision'),
    ]
    for body, field in cases:
        r = put(c, 1, body)
        assert r.status_code == 422 and r.json()['error']['code'] == 'INVALID_INPUT', body
        assert r.json()['error']['field'] == field and r.json()['error']['message'], body
    r = c.put('/api/v1/screener/items/scr_ABC', headers=c.headers_for, json=screen_item())
    assert r.status_code == 422 and r.json()['error']['field'] == 'item_id'
    assert worker.calls == [] and c.get('/api/v1/screener/items').json() == {'items': []}


def test_a_definition_the_worker_refuses_is_not_saved_and_names_its_field(app, worker):
    """The worker's 422 is relayed as it gave it; for a My metric (validated as the one condition of a screen) its
    field is named from the metric's own test, not from that screen."""
    c = app
    worker.max_length = 500
    r = put(c, 1, screen_item(length=600))
    assert r.status_code == 422 and r.json() == {'error': {'code': 'PARAM_OUT_OF_RANGE', 'field': 'conditions[0].test.metric.params.length',
                                                           'message': 'length is at most 500.',
                                                           'details': {'field': 'length', 'min': 1, 'max': 500}}}
    m = put(c, 2, metric_item(length=600))
    assert m.status_code == 422 and m.json()['error']['field'] == 'test.metric.params.length'
    assert c.get('/api/v1/screener/items').json() == {'items': []}
    worker.down = True
    assert put(c, 1, screen_item()).json() == error('SCREENER_UNAVAILABLE')
    assert c.get('/api/v1/screener/items').json() == {'items': []}


def test_saved_items_limits(app, worker, monkeypatch):
    """SCREEN_LIMIT per owner and kind, 422 LIMIT_EXCEEDED {limit: saved_items, allowed, needed}; a replace is no new
    item; a definition over 65,536 bytes of JSON is 422 LIMIT_EXCEEDED {limit: saved_definition_bytes}, before the
    worker and also as the database measures it (jsonb text, the migration's CHECK)."""
    c = app
    monkeypatch.setattr(screener, 'SCREEN_LIMIT', 2)
    assert [put(c, k, screen_item(f's{k}')).status_code for k in (1, 2)] == [200, 200]
    over = put(c, 3, screen_item('s3'))
    assert over.status_code == 422 and over.json() == error('LIMIT_EXCEEDED', message='At most 2 saved screens: delete one before saving another.',
                                                             details={'limit': 'saved_items', 'allowed': 2, 'needed': 3})
    assert put(c, 1, screen_item('s1b', revision=1)).status_code == 200      # a replace is no new item
    assert put(c, 4, metric_item('m1')).status_code == 200                   # the limit is per kind
    calls = len(worker.called('/v1/validate'))
    large = screen_item('large')
    large['definition']['view'] = {'note': 'x' * 70000}
    r = put(c, 5, large)
    assert r.status_code == 422 and r.json()['error']['code'] == 'LIMIT_EXCEEDED' and r.json()['error']['field'] == 'definition'
    assert r.json()['error']['details']['limit'] == 'saved_definition_bytes' and r.json()['error']['details']['allowed'] == 65536
    assert len(worker.called('/v1/validate')) == calls                      # refused before the worker
    # edge-bff counts the bytes as the table's CHECK does (jsonb text: a space after each ':' and ','; UTF-8): exactly
    # 65,536 is saved and the database holds that many, one more is refused here with what it needed
    monkeypatch.setattr(screener, 'SCREEN_LIMIT', 50)
    spaced = screen_item('spaced')
    spaced['definition']['view'] = {'keys': {f'k{k}': k for k in range(4000)}, 'note': 'é'}
    size = screener.stored_bytes(spaced['definition'])
    assert size > len(json.dumps(spaced['definition'], separators=(',', ':')).encode()) + 7000
    spaced['definition']['view']['pad'] = 'x' * (65536 - size - len(', "pad": ""'))
    assert screener.stored_bytes(spaced['definition']) == 65536
    r = put(c, 6, spaced)
    assert r.status_code == 200, r.text
    assert db(c, 'SELECT octet_length(definition::text) AS n FROM edge_bff.screener_items WHERE item_id=%s', item_id(6))[0]['n'] == 65536
    spaced['definition']['view']['pad'] += 'x'
    calls = len(worker.called('/v1/validate'))
    r = put(c, 7, {**spaced, 'name': 'spaced 2'})
    assert r.status_code == 422 and r.json()['error']['details'] == {'limit': 'saved_definition_bytes', 'allowed': 65536,
                                                                     'needed': 65537}
    assert len(worker.called('/v1/validate')) == calls                      # refused before the worker
    # a number the database writes out longer than JSON does (1e+300: 301 digits) passes here and is refused by the
    # table's CHECK, with the same code
    wide = screen_item('wide')
    wide['definition']['view'] = {'big': 1e300, 'pad': ''}
    wide['definition']['view']['pad'] = 'x' * (65536 - screener.stored_bytes(wide['definition']))
    r = put(c, 8, wide)
    assert r.status_code == 422 and r.json()['error']['details'] == {'limit': 'saved_definition_bytes', 'allowed': 65536}
    assert db(c, 'SELECT count(*) AS n FROM edge_bff.screener_items')[0]['n'] == 4


def test_items_and_watchlist_are_the_owners_own(app, worker):
    """Every statement names the owner: another owner's rows are never listed, replaced or deleted, and an id another
    owner holds answers as one's own existing id would (409), so nothing is learned about it."""
    c = app
    db(c, """INSERT INTO edge_bff.screener_items(item_id,owner_key,kind,name,definition,schema_version,registry_version,
             screener_registry_version,definition_hash) VALUES (%s,'someone-else','screen','Theirs','{}',1,'r','s',%s)""",
       item_id(7), sha('x'))
    db(c, "INSERT INTO edge_bff.watchlist_items(owner_key,ticker) VALUES ('someone-else','TLKM')")
    assert c.get('/api/v1/screener/items').json() == {'items': []} and c.get('/api/v1/screener/watchlist').json() == {'tickers': []}
    assert put(c, 7, screen_item(revision=1)).json() == error('NOT_FOUND')
    assert put(c, 7, screen_item()).json() == error('REVISION_CONFLICT')
    assert c.delete(f'/api/v1/screener/items/{item_id(7)}', headers=c.headers_for).status_code == 404
    assert put(c, 8, screen_item('Theirs')).status_code == 200               # names are per owner
    assert c.delete('/api/v1/screener/watchlist/TLKM', headers=c.headers_for).status_code == 204
    rows = db(c, "SELECT owner_key, name FROM edge_bff.screener_items ORDER BY owner_key")
    assert [(r['owner_key'], r['name']) for r in rows] == [('local-test-owner', 'Theirs'), ('someone-else', 'Theirs')]
    assert db(c, "SELECT ticker FROM edge_bff.watchlist_items WHERE owner_key='someone-else'") == [{'ticker': 'TLKM'}]


def test_an_item_saved_under_other_registry_versions_is_validated_again_on_load(app, worker):
    """Report 8.7 and 6c.5 item 6: on load, an item saved under the registry versions the worker has now needs no
    review; one saved under others is validated again and each refusal is listed with its field (cached per definition
    and versions); nothing is adjusted. While the worker cannot answer, the list still loads, unreviewed."""
    c = app
    assert put(c, 1, screen_item(length=600)).status_code == 200
    assert put(c, 2, metric_item(length=600)).status_code == 200
    assert put(c, 3, screen_item('fine', length=7)).status_code == 200
    calls = len(worker.called('/v1/validate'))
    assert all(x['needs_review'] == [] for x in c.get('/api/v1/screener/items').json()['items'])
    assert len(worker.called('/v1/validate')) == calls                     # same versions: no new validation
    worker.versions, worker.max_length = versions('b', price_data=sha('price-a')), 500
    c.app.state.screeners.health['at'] = None
    items = {x['item_id']: x for x in c.get('/api/v1/screener/items').json()['items']}
    flag = {'reason': 'PARAM_OUT_OF_RANGE', 'message': 'length is at most 500.', 'details': {'field': 'length', 'min': 1, 'max': 500}}
    assert items[item_id(1)]['needs_review'] == [{'field': 'conditions[0].test.metric.params.length', **flag}]
    assert items[item_id(2)]['needs_review'] == [{'field': 'test.metric.params.length', **flag}]
    assert items[item_id(3)]['needs_review'] == []
    assert items[item_id(1)]['definition']['definition'] == definition(600)   # never adjusted
    assert items[item_id(1)]['screener_registry_version'] == 'sregistry-a'
    calls = len(worker.called('/v1/validate'))
    again = {x['item_id']: x for x in c.get('/api/v1/screener/items').json()['items']}
    assert again == items and len(worker.called('/v1/validate')) == calls   # kept per definition and versions
    c.app.state.screeners.reviews.clear()
    worker.down = True
    calls = len(worker.called('/v1/validate'))
    unreviewed = c.get('/api/v1/screener/items')
    assert unreviewed.status_code == 200 and all(x['needs_review'] == [] for x in unreviewed.json()['items'])
    assert c.app.state.screeners.reviews == {}                              # nothing kept from an unanswered question
    # review 2026-10-28: one unanswered question ends the reviews of this load (the three items asked once, not thrice)
    assert len(worker.called('/v1/validate')) == calls + 1
    # saving again under the new versions clears the review
    worker.down, worker.max_length = False, 1000
    assert put(c, 1, screen_item(length=600, revision=1)).json()['screener_registry_version'] == 'sregistry-b'


def test_a_validation_answer_without_versions_takes_the_workers_health_versions(app, worker):
    """Report 8.3 gives every worker answer its versions; a validation without them takes the worker's /health ones.
    An answer that is no validation (no valid: true and definition_hash) stores nothing."""
    c = app
    worker.validate_versions = False
    r = put(c, 1, screen_item())
    assert r.status_code == 200 and r.json()['registry_version'] == 'registry-a'
    worker.refuse = {'/v1/validate': (200, {'code': 'x'})}         # a 200 that is no validation: outside the worker's API
    r = put(c, 2, screen_item('b'))
    assert r.status_code == 503 and r.json() == error('SCREENER_UNAVAILABLE')
    assert [x['name'] for x in c.get('/api/v1/screener/items').json()['items']] == ['Oversold']


# ---- watchlist ------------------------------------------------------------------------------------------------------

def test_watchlist_add_list_remove_and_its_limit(app, worker, monkeypatch):
    c = app
    h = c.headers_for
    assert [c.put(f'/api/v1/screener/watchlist/{t}', headers=h).status_code for t in ('BBCA', 'TLKM', 'BBCA')] == [204] * 3
    listed = c.get('/api/v1/screener/watchlist').json()['tickers']
    assert [x['ticker'] for x in listed] == ['BBCA', 'TLKM'] and all(x['added_at'] for x in listed)
    for bad in ('bbca', 'BB-CA', 'A' * 13):
        r = c.put(f'/api/v1/screener/watchlist/{bad}', headers=h)
        assert r.status_code == 422 and r.json()['error']['field'] == 'ticker' and r.json()['error']['message'], bad
        assert c.delete(f'/api/v1/screener/watchlist/{bad}', headers=h).status_code == 422
    monkeypatch.setattr(screener, 'WATCHLIST_LIMIT', 2)
    over = c.put('/api/v1/screener/watchlist/BMRI', headers=h)
    assert over.status_code == 422 and over.json() == error(
        'LIMIT_EXCEEDED', 'ticker', 'At most 2 tickers in the watchlist: remove one before adding another.',
        {'limit': 'watchlist', 'allowed': 2, 'needed': 3})
    assert c.put('/api/v1/screener/watchlist/TLKM', headers=h).status_code == 204     # a watched one: no new row
    assert [c.delete('/api/v1/screener/watchlist/TLKM', headers=h).status_code for _ in range(2)] == [204, 204]
    assert [x['ticker'] for x in c.get('/api/v1/screener/watchlist').json()['tickers']] == ['BBCA']
    assert worker.calls == []                                                # the watchlist never asks the worker


# ---- migration and provisioning -------------------------------------------------------------------------------------

def test_the_migration_refuses_a_runtime_role_with_more_than_the_code_does(database):
    """The verify block holds edge_bff_runtime to exactly the grants of each table: TRUNCATE, REFERENCES or TRIGGER on
    either, or UPDATE on the watchlist, given through the schema's default privileges, fails the migration, which then
    leaves nothing applied."""
    with psycopg.connect(database, autocommit=True) as conn:
        conn.execute(ROLLBACK)
        try:
            for extra in ('UPDATE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'):
                conn.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA edge_bff GRANT {extra} ON TABLES TO edge_bff_runtime')
                with pytest.raises(psycopg.errors.RaiseException, match='more than the screener tables need'):
                    conn.execute(MIGRATION.read_text())
                conn.execute('ROLLBACK')
                assert conn.execute("SELECT to_regclass('edge_bff.screener_items')").fetchone()[0] is None, extra
                conn.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA edge_bff REVOKE {extra} ON TABLES FROM edge_bff_runtime')
        finally:
            conn.execute('ROLLBACK')
            for extra in ('UPDATE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'):
                conn.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA edge_bff REVOKE {extra} ON TABLES FROM edge_bff_runtime')
            if conn.execute("SELECT to_regclass('edge_bff.screener_items')").fetchone()[0] is not None:
                conn.execute(ROLLBACK)
            conn.execute(MIGRATION.read_text())


def test_the_migration_refuses_public_with_any_privilege_on_the_screener_tables(database):
    """The verify block also holds PUBLIC to nothing on both tables: run without its REVOKE, with the schema's default
    privileges granting PUBLIC one privilege at a time, every privilege is refused (by the runtime check where the
    runtime role would then hold more than its grants)."""
    revoke = 'REVOKE ALL ON edge_bff.screener_items, edge_bff.watchlist_items FROM PUBLIC;\n'
    assert MIGRATION.read_text().count(revoke) == 1
    unguarded = MIGRATION.read_text().replace(revoke, '')
    privileges = ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER')
    with psycopg.connect(database, autocommit=True) as conn:
        conn.execute(ROLLBACK)
        try:
            conn.execute(unguarded)
            conn.execute(ROLLBACK)
            for privilege in privileges:
                conn.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA edge_bff GRANT {privilege} ON TABLES TO PUBLIC')
                message = 'PUBLIC can use the screener tables' if privilege in ('SELECT', 'INSERT', 'DELETE') else 'more than the screener tables need'
                with pytest.raises(psycopg.errors.RaiseException, match=message):
                    conn.execute(unguarded)
                conn.execute('ROLLBACK')
                assert conn.execute("SELECT to_regclass('edge_bff.screener_items')").fetchone()[0] is None, privilege
                conn.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA edge_bff REVOKE {privilege} ON TABLES FROM PUBLIC')
        finally:
            conn.execute('ROLLBACK')
            for privilege in privileges:
                conn.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA edge_bff REVOKE {privilege} ON TABLES FROM PUBLIC')
            if conn.execute("SELECT to_regclass('edge_bff.screener_items')").fetchone()[0] is not None:
                conn.execute(ROLLBACK)
            conn.execute(MIGRATION.read_text())


def test_the_tables_hold_their_rules(database):
    """The migration's checks, as the database applies them: item ids, kinds, trimmed names of 1-120 characters, a JSON
    object of at most 65,536 bytes, one name per owner and kind, a positive revision, hashes; tickers by terminal-api's
    rule, one row per owner and ticker."""
    good = {'item_id': item_id(1), 'owner_key': 'o', 'kind': 'screen', 'name': 'n', 'definition': '{}', 'schema_version': 1,
            'registry_version': 'r', 'screener_registry_version': 's', 'definition_hash': sha('d'), 'revision': 1}
    def insert(conn, **change):
        row = {**good, **change}
        conn.execute(f"INSERT INTO edge_bff.screener_items({','.join(row)}) VALUES ({','.join(['%s'] * len(row))})", list(row.values()))
    with psycopg.connect(database) as conn:
        insert(conn)
        for change in ({'item_id': 'scr_1'}, {'kind': 'list'}, {'name': ''}, {'name': ' n'}, {'name': 'x' * 121},
                       {'definition': '[]'}, {'definition': json.dumps({'x': 'y' * 65530})}, {'schema_version': 0},
                       {'registry_version': ''}, {'definition_hash': 'x'}, {'revision': 0}):
            with pytest.raises(psycopg.errors.CheckViolation):
                insert(conn, **{'item_id': item_id(2), 'name': 'm', **change})
            conn.rollback()
            insert(conn)
        with pytest.raises(psycopg.errors.UniqueViolation):
            insert(conn, item_id=item_id(3))
        conn.rollback()
        conn.execute("INSERT INTO edge_bff.watchlist_items(owner_key,ticker) VALUES ('o','BBCA')")
        for ticker in ('bbca', 'B-B', 'A' * 13):
            with pytest.raises(psycopg.errors.CheckViolation):
                conn.execute("INSERT INTO edge_bff.watchlist_items(owner_key,ticker) VALUES ('o',%s)", (ticker,))
            conn.rollback()
        conn.rollback()


def test_provisioned_login_reaches_the_screener_tables_with_their_migration(database, monkeypatch):
    """scripts/provision_edge_bff_login.py: the two screener tables are allowed once their migration is applied, both or
    none, each with exactly the privileges the migration grants it; without it the login reaches the others only."""
    import importlib.util
    import secrets
    from urllib.parse import urlsplit, urlunsplit
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
            conn.execute("""INSERT INTO edge_bff.screener_items(item_id,owner_key,kind,name,definition,schema_version,
                registry_version,screener_registry_version,definition_hash) VALUES (%s,'o','metric','m','{}',1,'r','s',%s)""",
                (item_id(1), sha('d')))
            conn.execute("UPDATE edge_bff.screener_items SET revision=2")
            conn.execute("DELETE FROM edge_bff.screener_items")
            conn.execute("INSERT INTO edge_bff.watchlist_items(owner_key,ticker) VALUES ('o','BBCA') ON CONFLICT DO NOTHING")
            conn.execute("DELETE FROM edge_bff.watchlist_items")
            conn.rollback()
            for sql in ("UPDATE edge_bff.watchlist_items SET ticker='X'", 'TRUNCATE edge_bff.screener_items',
                        'TRUNCATE edge_bff.watchlist_items', 'SELECT * FROM public.market_private'):
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    conn.execute(sql)
                conn.rollback()
        for extra in ('TRUNCATE', 'REFERENCES', 'TRIGGER'):
            with psycopg.connect(database, autocommit=True) as conn:
                conn.execute(f'GRANT {extra} ON edge_bff.screener_items TO edge_bff_runtime')
            with pytest.raises(RuntimeError, match='Unexpected EDGE grants'):
                module.main()
            with psycopg.connect(database, autocommit=True) as conn:
                conn.execute(f'REVOKE {extra} ON edge_bff.screener_items FROM edge_bff_runtime')
        with psycopg.connect(database, autocommit=True) as conn:
            conn.execute('GRANT UPDATE ON edge_bff.watchlist_items TO edge_bff_runtime')
        with pytest.raises(RuntimeError, match='Unexpected EDGE grants'):
            module.main()
        with psycopg.connect(database, autocommit=True) as conn:
            conn.execute('REVOKE ALL ON edge_bff.watchlist_items FROM edge_bff_runtime')
        with pytest.raises(RuntimeError, match='unexpected reachable relations'):
            module.main()                                     # one of the two: refused
        with psycopg.connect(database, autocommit=True) as conn:
            conn.execute(ROLLBACK)
        module.main()                                         # none of the two: the others only
        with psycopg.connect(restricted) as conn:
            conn.execute('SELECT * FROM edge_bff.jobs LIMIT 0')
    finally:
        with psycopg.connect(database, autocommit=True) as conn:
            if conn.execute("SELECT to_regclass('edge_bff.screener_items')").fetchone()[0] is None:
                conn.execute(MIGRATION.read_text())
            else:
                conn.execute('GRANT SELECT, INSERT, DELETE ON edge_bff.watchlist_items TO edge_bff_runtime')
            conn.execute('DROP OWNED BY edge_bff_login')
            conn.execute('DROP ROLE edge_bff_login')


# ---- settings, page, image ------------------------------------------------------------------------------------------

def test_screener_settings_are_paired_strong_private_and_bounded(settings):
    on = dict(screener_worker_url='http://screener-worker.railway.internal:8080', screener_worker_key=KEY,
              screener_timeout_seconds=20)
    dataclasses.replace(settings, **on).validate()
    # the timeout is what its refusal says, 1 s to 3600 s, bounds included (a value in (0, 1) was let through)
    for seconds in (1, 1.5, 3600):
        dataclasses.replace(settings, **{**on, 'screener_timeout_seconds': seconds}).validate()
    for bad, message in (({'screener_worker_key': ''}, 'set together'), ({'screener_worker_key': 'short'}, 'at least 32'),
                         ({'screener_timeout_seconds': 0}, 'SCREENER_TIMEOUT_SECONDS'),
                         ({'screener_timeout_seconds': 0.5}, r'1 s to 3600 s'), ({'screener_timeout_seconds': 0.999}, r'1 s to 3600 s'),
                         ({'screener_timeout_seconds': -1}, 'SCREENER_TIMEOUT_SECONDS'),
                         ({'screener_timeout_seconds': float('nan')}, 'SCREENER_TIMEOUT_SECONDS'),
                         ({'screener_timeout_seconds': 3601}, 'SCREENER_TIMEOUT_SECONDS')):
        with pytest.raises(ValueError, match=message):
            dataclasses.replace(settings, **{**on, **bad}).validate()
    with pytest.raises(ValueError, match='set together'):
        dataclasses.replace(settings, screener_worker_key=KEY).validate()
    deployed = dataclasses.replace(settings, environment='dev', orc_url='http://market-ai-orc.railway.internal:8080',
                                   database_url='postgresql://edge_bff_login@db.internal/railway',
                                   origin='https://edge.example', secure_cookie=True, **on)
    deployed.validate()
    for url in ('https://screener-worker.up.railway.app', 'https://screener-worker.railway.internal:8080',
                'http://backtest-worker.railway.internal:8080'):
        with pytest.raises(ValueError, match='SCREENER_WORKER_URL'):
            dataclasses.replace(deployed, screener_worker_url=url).validate()
    dataclasses.replace(settings).validate()          # off: nothing required


def test_settings_from_the_environment(monkeypatch):
    from app.config import Settings
    from app.security import password_verifier
    env = {'EDGE_DATABASE_URL': 'postgresql://x@db/railway', 'EDGE_ORC_URL': 'http://orc.invalid', 'MARKET_AI_ORC_API_KEY': 'k',
           'EDGE_OWNER': 'o', 'EDGE_LOGIN': 'l', 'EDGE_PASSWORD_VERIFIER': password_verifier('p'),
           'EDGE_SESSION_SECRET': 'x' * 40, 'EDGE_PUBLIC_ORIGIN': 'http://testserver', 'EDGE_ENVIRONMENT': 'local',
           'EDGE_SECURE_COOKIE': 'false', 'SCREENER_WORKER_URL': 'http://127.0.0.1:9/', 'SCREENER_WORKER_KEY': KEY,
           'SCREENER_TIMEOUT_SECONDS': '20'}
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    s = Settings.from_env()
    assert (s.screener_worker_url, s.screener_worker_key, s.screener_timeout_seconds) == ('http://127.0.0.1:9', KEY, 20)
    monkeypatch.delenv('SCREENER_TIMEOUT_SECONDS')
    with pytest.raises(ValueError, match='SCREENER_TIMEOUT_SECONDS'):
        Settings.from_env()


def test_screener_tab_page_and_its_frame_csp(app, monkeypatch, tmp_path):
    c = app
    (tmp_path / 'assets').mkdir()
    (tmp_path / 'index.html').write_text('<!doctype html><title>EDGE Screener</title>')
    (tmp_path / 'assets' / 'index-abc123.js').write_text('void 0')
    monkeypatch.setattr(main, 'SCREENER_APP', tmp_path)
    page = c.get('/screener')
    assert page.status_code == 200 and 'function ScreenerPage' in page.text and '"/screener-app/"' in page.text
    # the tab's wording is in edge-labels.js (AGENTS.md), used like the other tabs'
    assert 'screener: { nav:"Screener", frameTitle:"Stock screener" }' in c.get('/edge-labels.js').text
    assert '[EdgeLabels.screener.nav, "screener"]' in page.text and 'title: EdgeLabels.screener.frameTitle' in page.text
    assert '"Screener"' not in page.text and '"Stock screener"' not in page.text
    assert page.headers['content-security-policy'] == c.get('/terminal').headers['content-security-policy']   # EDGE's own policy
    frame = c.get('/screener-app/')
    assert frame.status_code == 200 and 'EDGE Screener' in frame.text and frame.headers['cache-control'] == 'no-store'
    csp = frame.headers['content-security-policy']
    assert csp == main.SCREENER_CSP and "script-src 'self';" in csp and 'unsafe-eval' not in csp
    # the page reads nothing from the bucket (its preview is computed by the worker): connect-src is this origin only
    assert "connect-src 'self';" in csp and 'storageapi' not in csp and "frame-ancestors 'self'" in csp
    assert csp == main.TERMINAL_CSP.replace(" https://*.t3.storageapi.dev", '')
    asset = c.get('/screener-app/assets/index-abc123.js')
    assert asset.status_code == 200 and 'immutable' in asset.headers['cache-control'] and asset.headers['content-security-policy'] == csp
    assert c.get('/screener-app/assets/..%2F..%2Fapp%2Fmain.py').status_code == 404
    assert c.get('/screener-app/assets/data.json').status_code == 404
    assert c.get('/screener-app/assets/missing.js').status_code == 404
    monkeypatch.setattr(main, 'SCREENER_APP', tmp_path / 'not-built')
    assert c.get('/screener-app/').status_code == 404


def test_the_image_builds_the_screener_page_beside_the_sources_it_imports():
    """apps/edge-bff/Dockerfile: the screener stage installs from its lock file, places the Terminal source and the
    Backtest source beside it as in the repository (its core imports the Backtest core and the Terminal's formulas, the
    page reuses Terminal and Backtest page helpers), builds, and the final image takes only its dist/ as
    static/screener-app. Every file the page reaches outside its folder is in those copied trees, and none of them
    imports a package (no node_modules is beside them in the stage)."""
    import re
    text = (Path(__file__).resolve().parents[1] / 'Dockerfile').read_text()
    stage = text.split('FROM node:22-slim AS screener', 1)[1].split('\nFROM ', 1)[0]
    assert [line for line in stage.strip().splitlines() if not line.startswith('#')] == [
        'WORKDIR /build/screener', 'COPY screener/package.json screener/package-lock.json ./',
        'RUN npm ci --no-audit --no-fund', 'COPY terminal/src /build/terminal/src',
        'COPY backtest/src /build/backtest/src', 'COPY screener/ ./', 'RUN npm run build']
    assert 'COPY --from=screener /build/screener/dist ./static/screener-app\n' in text
    root = Path(__file__).resolve().parents[1].resolve()
    page = root / 'screener'
    spec_rx = re.compile(r"""(?:\bfrom|\bimport)\s*\(?\s*['"]([^'"]+)['"]""")
    todo, seen, outside, packages = list((page / 'src').rglob('*.ts')), set(), set(), set()
    while todo:
        f = todo.pop().resolve()
        if f in seen or not f.is_file():
            continue
        seen.add(f)
        mine = f.is_relative_to(page)
        if not mine:
            outside.add(f.relative_to(root).as_posix())
        for spec in spec_rx.findall(f.read_text()):
            if spec.startswith('.'):
                if spec.endswith(('.ts', '.json')):
                    todo.append(f.parent / spec)
            elif not mine:
                packages.add((f.relative_to(root).as_posix(), spec))
    assert outside, 'the screener page imports nothing outside its folder: is the walk broken?'
    assert [p for p in sorted(outside) if not (p.startswith('terminal/src/') or p.startswith('backtest/src/'))] == []
    assert packages == set()


def test_screener_tab_in_the_browser(configured, store, worker, monkeypatch, tmp_path):
    """The real page in Chromium: the Screener tab after Backtest opens /screener with the frame, and the framed page
    (a stand-in for the built one, its script from its own assets as the CSP requires) reads the catalog with the EDGE
    session; a reload keeps the tab and is answered from edge-bff's catalog kept per worker state."""
    playwright = pytest.importorskip('playwright.sync_api')
    (tmp_path / 'assets').mkdir()
    (tmp_path / 'index.html').write_text('<!doctype html><title>Screener frame</title><p id="out">loading</p>'
                                         '<script src="/screener-app/assets/probe-1.js"></script>')
    (tmp_path / 'assets' / 'probe-1.js').write_text(
        "fetch('/api/v1/screener/catalog').then(r => r.json()).then(c => { document.getElementById('out').textContent = "
        "'evaluated ' + c.data.evaluation_date }, e => { document.getElementById('out').textContent = 'failed ' + e })")
    monkeypatch.setattr(main, 'SCREENER_APP', tmp_path)
    local, stop = serve(configured, store)
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
                assert tabs.all_inner_texts() == ['Monitor', 'Terminal', 'Backtest', 'Screener']
                page.locator('.topbar nav button.nav-screener').click()
                page.wait_for_url(local.origin + '/screener')
                assert page.locator('.topbar nav button.nav-screener').get_attribute('aria-current') == 'page'
                page.frame_locator('iframe.terminal-frame').get_by_text('evaluated 2026-10-27', exact=True).wait_for()
                assert page.locator('iframe.terminal-frame').get_attribute('title') == 'Stock screener'
                page.reload()
                page.frame_locator('iframe.terminal-frame').get_by_text('evaluated 2026-10-27', exact=True).wait_for()
                page.locator('.topbar nav button.nav-backtest').click()
                page.wait_for_url(local.origin + '/backtest')
                assert page.locator('iframe.terminal-frame').get_attribute('src').endswith('/backtest-app/')
                page.go_back()
                page.wait_for_url(local.origin + '/screener')
                assert page.locator('iframe.terminal-frame').get_attribute('src').endswith('/screener-app/')
                assert not [e for e in errors if 'Content Security Policy' in e]
            finally:
                browser.close()
    finally:
        stop()
    assert [c['path'] for c in worker.calls] == ['/health', '/v1/catalog']   # the reload: from edge-bff's kept catalog
