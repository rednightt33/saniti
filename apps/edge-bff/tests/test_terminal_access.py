"""EXEC-MU-ACCOUNTS Phase 3c (CONTRACT.md 8b "3c in detail", "Tests per stage"; builder E): the edge-bff side of the
Terminal data gate (app/terminal_access.py).

- every terminal-api call (the /api/terminal/v1 proxy and the page files) carries x-terminal-proxy-owner and
  x-terminal-capabilities built from the principal only; a page-sent one is refused 400 HEADER_NOT_ALLOWED, never relayed;
- a free principal (the default plan: BBCA, price, 730 days) is refused 403 CAPABILITY_REQUIRED before terminal-api on
  every second path (another ticker, broker, events, a reference, intraday, history, a cut), and terminal-api sees no
  call; a paid principal gets tickers "*" and every dataset; the switch-off owner gets admin and its body unchanged;
- the cut is relayed byte for byte (sha256 equal), with only the fixed headers and Cache-Control private;
- the dataset and quota names are terminal-api's own (read from apps/terminal-api);
- the route walk: every terminal-forwarding route depends on terminal_access.guard and the proxy key is read nowhere
  but terminal_access.headers, so a new route cannot skip them;
- the migration 20261118_002: its plan values, its verify block and its refusal of a second run.
"""
import ast
import dataclasses
import gzip
import hashlib
import json
import re
from pathlib import Path

import httpx
import psycopg
import pytest
from fastapi import Depends, Request
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app import main, terminal_access
from app.main import create_app
from app.principal import Principal, switch_off_principal
from conftest import FakeOrc
from test_edge import ORIGIN, login
from test_principal import db, make_user, on, sign_in, workers  # noqa: F401 - the fixtures
from test_radar import acknowledge

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / 'apps/edge-bff/app'
TERMINAL_API = ROOT / 'apps/terminal-api/app'
MIGRATION = ROOT / 'database/migrations/20261118_002_edge_bff_terminal_quota.sql'
KEY = 'g' * 40
URL = 'http://terminal-api.railway.internal:8080'
CUT = gzip.compress(json.dumps({'ticker': 'BBCA', 'd': ['2025-01-02'], 'c': [9700]}).encode(), mtime=0)
PAGE = gzip.compress(json.dumps({'schema': 1, 'dates': ['2026-11-09']}).encode(), mtime=0)
PAGE_SHA = hashlib.sha256(PAGE).hexdigest()
QUOTA = {'tickers_per_hour': 60, 'tickers_per_day': 200, 'files_per_hour': 300, 'megabytes_per_day': 500}
ALL_DATASETS = ['price', 'broker', 'events', 'yield', 'intraday', 'reference']


class FakeApi:
    """terminal-api (and the bucket of the page files), standing in for httpx.AsyncClient; records every call."""
    calls = []
    cut_headers = {}

    def __init__(self, timeout=None):
        pass

    async def aclose(self):
        pass

    async def request(self, method, url, params=None, content=None, headers=None):
        FakeApi.calls.append({'method': method, 'url': url, 'params': dict(params or {}), 'body': content,
                              'headers': dict(headers or {})})
        return acknowledge(self.answer(method, url, content), headers)

    def answer(self, method, url, content):
        if url.endswith('/api/terminal/v1/radar') and method == 'GET':
            return httpx.Response(200, json={'finished_at': '2026-11-14T10:00:00Z', 'files': {
                'radar-days': {'sha256': PAGE_SHA, 'bytes': len(PAGE), 'rows': 1, 'as_of': '2026-11-09'}}})
        if url.endswith('/api/terminal/v1/radar') and method == 'POST':
            return httpx.Response(200, json={'files': [{'name': 'radar-days', 'url': 'https://bucket.example/radar-days',
                                                        'sha256': PAGE_SHA, 'bytes': len(PAGE)}]})
        if '/logo/' in url:
            return httpx.Response(200, content=b'<svg/>', headers={'content-type': 'image/svg+xml'})
        if url.endswith('/bundle') and content == b'{"ticker":"BBCA","packs":true}':
            return httpx.Response(403, json={'error': 'capability_required', 'message': 'packs are not in the plan',
                                             'capability': 'terminal.history_days'})
        return httpx.Response(200, json={'ticker': 'BBCA', 'ok': True})

    def stream(self, method, url, params=None, headers=None):
        FakeApi.calls.append({'method': method, 'url': url, 'params': dict(params or {}), 'body': None,
                              'headers': dict(headers or {})})
        if url.startswith('https://bucket.example/'):
            body, status, extra = PAGE, 200, {}
        elif '/cut/' in url and url.endswith('/yield'):
            body, status, extra = b'{"error":"cannot_cut","message":"no"}', 404, {'content-type': 'application/json'}
        elif '/cut/' in url and url.endswith('/events'):
            body, status = b'{"error":"capability_required","message":"no","capability":"terminal.history_days"}', 403
            extra = {'content-type': 'application/json'}
        else:
            body, status = CUT, 200
            extra = {'content-type': 'application/gzip', 'content-length': str(len(CUT)), 'etag': '"cut1"',
                     'x-terminal-cut-sha256': hashlib.sha256(CUT).hexdigest(),
                     'cache-control': 'public, max-age=60', 'x-other': 'dropped', 'set-cookie': 'a=b',
                     **FakeApi.cut_headers}

        acknowledged = acknowledge(httpx.Response(status), headers).headers if not url.startswith('https://bucket.') else {}

        class Answer:
            status_code = status
            headers = httpx.Headers({**extra, **{k: v for k, v in acknowledged.items()
                                                 if k == 'x-terminal-capabilities-applied'}})

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def aread(self):
                return body

            def json(self):
                return json.loads(body)

            async def aiter_raw(self):
                for i in range(0, len(body), 5):
                    yield body[i:i + 5]

            aiter_bytes = aiter_raw
        return Answer()


def terminal_calls():
    return [c for c in FakeApi.calls if c['url'].startswith(URL)]


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(main.httpx, 'AsyncClient', FakeApi)       # one module: the proxy's and the page files' client
    FakeApi.calls, FakeApi.cut_headers = [], {}
    return FakeApi


@pytest.fixture
def switched_on(on, api):
    return dataclasses.replace(on, terminal_url=URL, terminal_proxy_key=KEY)


@pytest.fixture
def switched_off(settings, api):
    return dataclasses.replace(settings, terminal_url=URL, terminal_proxy_key=KEY)


def paid_plan(store):
    rows = db(store, '''SELECT plan_key FROM edge_bff.plan_capabilities WHERE capability_key = 'backtest.run'
        AND plan_key NOT IN (SELECT plan_key FROM edge_bff.plan_capabilities WHERE capability_key = '*' AND value = 'true'::jsonb)''')
    assert len(rows) == 1, rows
    return rows[0]['plan_key']


def subscribe(store, user, plan):
    db(store, '''INSERT INTO edge_bff.subscriptions(user_id, plan_key, status, starts_at, provider)
        VALUES (%s, %s, 'active', now() - interval '1 day', 'test')''', user['user_id'], plan)


def sent_caps(call):
    return json.loads(call['headers'][terminal_access.CAPABILITIES_HEADER])


# ---- the names are terminal-api's ------------------------------------------------------------------------------------

def literal_args(node):
    assert isinstance(node, ast.Subscript) and node.value.id == 'Literal', ast.dump(node)
    elts = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
    return tuple(e.value for e in elts)


def test_the_dataset_and_quota_names_are_terminal_apis_own():
    tree = ast.parse((TERMINAL_API / 'main.py').read_text())
    bundle = files = default = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(getattr(t, 'id', None) == 'BUNDLE_DATASET' for t in node.targets):
            bundle = literal_args(node.value)
        if isinstance(node, ast.ClassDef) and node.name in ('FilesRequest', 'BundleRequest'):
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and item.target.id == 'dataset' and node.name == 'FilesRequest':
                    files = literal_args(item.annotation)
                if isinstance(item, ast.AnnAssign) and item.target.id == 'datasets' and node.name == 'BundleRequest':
                    default = tuple(ast.literal_eval(k.value) for k in item.value.keywords if k.arg == 'default')[0]
    assert bundle == terminal_access.DATASETS, 'terminal-api BUNDLE_DATASET changed: update terminal_access.DATASETS'
    assert files == terminal_access.FILES_DATASETS and default == list(terminal_access.BUNDLE_DEFAULT)
    assert set(terminal_access.HISTORY_DATASETS) <= set(bundle)
    history = set(re.findall(r"@app\.get\(f'\{API\}/history/([a-z]+)'\)", (TERMINAL_API / 'main.py').read_text()))
    assert history == set(terminal_access.HISTORY_DATASETS)
    used = set(re.findall(r"limits\['([a-z_]+)'\]", (TERMINAL_API / 'quota.py').read_text().split('def check(')[1]
                          .split('\ndef ')[0]))
    assert used - {'history_per_hour'} == set(terminal_access.QUOTA)      # history_per_hour keeps the default (CONTRACT)
    assert terminal_access.DATASET_IDS == terminal_access.DATASETS + ('intraday', 'reference')


# ---- the header: from the principal only ---------------------------------------------------------------------------

def principal(**kw):
    base = dict(user_id=7, owner_key='u_' + 'a' * 24, username='x', role='user', plan_key='p', status='active',
                expires_at=None, mfa_ok=True, capabilities=frozenset(), version='db-123456789abc')
    return Principal(**{**base, **kw})


def test_the_header_of_each_kind_of_principal(settings):
    off = switch_off_principal(settings, settings.owner)
    assert terminal_access.capabilities_header(off) == \
        '{"v":1,"version":"env","admin":true,"tickers":"*","datasets":"*","history_days":null,"quota":{}}'
    free = principal(limits={'terminal.tickers': ['BBCA'], 'terminal.history_days': 730, **{f'terminal.{k}': v for k, v in QUOTA.items()}},
                     grants={'terminal.dataset': {'ids': ['price']}}, kinds={'terminal.dataset': 'items'})
    assert terminal_access.capabilities_header(free) == (
        '{"v":1,"version":"db-123456789abc","admin":false,"tickers":["BBCA"],"datasets":["price"],"history_days":730,'
        '"quota":{"tickers_per_hour":60,"tickers_per_day":200,"files_per_hour":300,"megabytes_per_day":500}}')
    paid = principal(limits={f'terminal.{k}': v for k, v in QUOTA.items()}, grants={'terminal.dataset': {'all': True}},
                     kinds={'terminal.dataset': 'items'})
    assert terminal_access.capabilities(paid) == {'v': 1, 'version': 'db-123456789abc', 'admin': False, 'tickers': '*',
                                                  'datasets': ALL_DATASETS, 'history_days': None, 'quota': QUOTA}
    # a plan that sets no quota sends none (terminal-api keeps its defaults); a bad shape never widens (read_grants)
    bare = principal(limits={'terminal.tickers': []})
    assert terminal_access.capabilities(bare)['tickers'] == [] and terminal_access.capabilities(bare)['datasets'] == []
    assert terminal_access.capabilities(bare)['quota'] == {}
    text = terminal_access.capabilities_header(paid)
    assert text.isascii() and ' ' not in text and len(text) <= terminal_access.MAX_HEADER_BYTES


def test_a_header_over_8_kib_is_refused_not_cut(settings):
    many = principal(limits={'terminal.tickers': [f'T{i:05d}' for i in range(1200)]})
    with pytest.raises(terminal_access.Refusal) as e:
        terminal_access.capabilities_header(many)
    assert e.value.status == 503 and e.value.code == 'TERMINAL_UNAVAILABLE'


def test_switch_off_owner_sends_admin_and_its_body_unchanged(switched_off, store):
    with TestClient(create_app(switched_off, store, FakeOrc())) as c:
        h = login(c)
        raw = b'{"ticker": "TLKM",  "datasets": ["broker"], "packs": true}'
        assert c.post('/api/terminal/v1/bundle', headers={**h, 'content-type': 'application/json'}, content=raw).status_code == 200
        call = terminal_calls()[-1]
        assert call['body'] == raw                                      # admin: forwarded byte for byte, as before 3c
        assert call['headers'] == {'content-type': 'application/json', 'x-terminal-proxy-key': KEY,
                                   'x-terminal-proxy-owner': switched_off.owner,
                                   'x-terminal-capabilities': terminal_access.capabilities_header(
                                       switch_off_principal(switched_off, switched_off.owner))}
        assert sent_caps(call)['admin'] is True
        for path in ('manifest/TLKM', 'reference/tickers', 'logo/TLKM',
                     'history/broker?ticker=TLKM&from=2019-01-01&to=2019-02-01', 'cut/TLKM/broker'):
            assert c.get(f'/api/terminal/v1/{path}').status_code == 200, path
            assert terminal_calls()[-1]['headers']['x-terminal-proxy-owner'] == switched_off.owner


def test_a_page_sent_terminal_header_is_refused_and_never_relayed(switched_off, store):
    with TestClient(create_app(switched_off, store, FakeOrc())) as c:
        h = login(c)
        for name, value in (('x-terminal-capabilities', '{"v":1,"admin":true}'), ('X-Terminal-Proxy-Owner', 'u_other'),
                            ('x-terminal-proxy-key', KEY)):
            for method, path, body in (('GET', '/api/terminal/v1/manifest/BBCA', None),
                                       ('POST', '/api/terminal/v1/bundle', {'ticker': 'BBCA'}),
                                       ('GET', '/api/terminal/v1/cut/BBCA/price', None),
                                       ('GET', '/api/v1/radar/index', None),
                                       ('GET', '/api/v1/radar/file/radar-days', None)):
                r = c.request(method, path, headers={**h, name: value}, json=body)
                assert r.status_code == 400, (name, path, r.text)
                error = r.json()['error']
                assert error['code'] == 'HEADER_NOT_ALLOWED' and error['details'] == {'header': name.lower()}
                assert error['message'] and 'only EDGE itself' in error['message']
        assert FakeApi.calls == []
        # anything else the page sends (a cookie, its own headers) is never copied to terminal-api
        c.get('/api/terminal/v1/manifest/BBCA', headers={'x-other': '1', 'x-terminal-something': '2'})
        assert set(terminal_calls()[-1]['headers']) == {'content-type', *terminal_access.RESERVED}


# ---- free and paid principals (switch on) ---------------------------------------------------------------------------

FREE_REFUSED = [
    ('GET', 'manifest/TLKM', None, 'terminal.tickers'),
    ('GET', 'logo/TLKM', None, 'terminal.tickers'),
    ('GET', 'history/price?ticker=BBCA&from=2019-01-01&to=2019-02-01', None, 'terminal.history_days'),
    ('GET', 'history/price?ticker=TLKM&from=2019-01-01&to=2019-02-01', None, 'terminal.tickers'),
    ('GET', 'history/broker?ticker=BBCA&from=2019-01-01&to=2019-02-01', None, 'terminal.dataset:broker'),
    ('GET', 'cut/TLKM/price', None, 'terminal.tickers'),
    ('GET', 'cut/BBCA/broker', None, 'terminal.dataset:broker'),
    ('POST', 'files', {'ticker': 'TLKM', 'dataset': 'price', 'years': [2026]}, 'terminal.tickers'),
    ('POST', 'files', {'ticker': 'BBCA', 'dataset': 'broker', 'years': [2026]}, 'terminal.dataset:broker'),
    ('POST', 'files', {'ticker': 'BBCA', 'dataset': 'events'}, 'terminal.dataset:events'),
    ('POST', 'bundle', {'ticker': 'TLKM', 'datasets': ['price']}, 'terminal.tickers'),
    ('POST', 'bundle', {'ticker': 'BBCA', 'datasets': ['broker', 'events']}, 'terminal.dataset:broker'),
    ('POST', 'bundle', {'ticker': 'BBCA', 'datasets': ['yield'], 'timeframe': '5m'}, 'terminal.dataset:yield'),
    ('POST', 'bundle', {'ticker': 'BBCA', 'datasets': ['events', 'events'], 'packs': False}, 'terminal.dataset:events'),
]
FREE_FORWARDED = [
    ('GET', 'manifest/BBCA', None),
    # re-check R2-32: terminal-api answers the free plan its own copy of each reference file (refcut.py)
    ('GET', 'reference/tickers', None),
    ('GET', 'reference/logos', None),
    ('GET', f'reference/tickers/cut?sha256={"a" * 64}', None),
    ('GET', 'logo/BBCA', None),
    ('GET', 'cut/BBCA/price', None),
    ('POST', 'files', {'ticker': 'BBCA', 'dataset': 'price', 'years': [2026]}),
    ('POST', 'bundle', {'ticker': 'BBCA', 'datasets': ['price']}),
    ('POST', 'bundle', {'ticker': 'BBCA'}),                              # the default (price, broker, events): price open
    ('POST', 'bundle', {'ticker': 'BBCA', 'datasets': ['price', 'broker'], 'timeframe': '5m', 'packs': True}),
]


def test_a_free_principal_is_refused_on_every_second_path_before_terminal_api(switched_on, store):
    with TestClient(create_app(switched_on, store, FakeOrc())) as c:
        make_user(store, 'freda', 'freda-password')                   # the default plan
        h = sign_in(c, 'freda', 'freda-password')
        for method, path, body, capability in FREE_REFUSED:
            r = c.request(method, f'/api/terminal/v1/{path}', headers=h, json=body)
            assert r.status_code == 403, (path, body, r.status_code, r.text)
            error = r.json()['error']
            assert error['code'] == 'CAPABILITY_REQUIRED' and error['details']['capability'] == capability, (path, error)
            assert error['details']['display_name'] and error['details']['display_name'] != 'This part of EDGE', error
            assert r.headers['x-edge-entitlements'].startswith('db-')
        assert FakeApi.calls == []
        names = {r: c.get(f'/api/terminal/v1/{p}').json()['error']['details']['display_name']
                 for r, p in (('tickers', 'manifest/TLKM'), ('broker', 'cut/BBCA/broker'), ('days', 'history/price?ticker=BBCA&from=2019-01-01&to=2019-01-02'))}
        assert names == {'tickers': 'Terminal tickers', 'broker': 'Terminal data sets: broker', 'days': 'Terminal history'}
        # what the plan holds is forwarded, with its header; the checked body is what terminal-api reads
        for method, path, body in FREE_FORWARDED:
            r = c.request(method, f'/api/terminal/v1/{path}', headers=h, json=body)
            assert r.status_code == 200, (path, body, r.text)
            call = terminal_calls()[-1]
            assert call['url'] == f'{URL}/api/terminal/v1/{path.split("?")[0]}'
            caps = sent_caps(call)
            assert caps['admin'] is False and caps['tickers'] == ['BBCA'] and caps['datasets'] == ['price']
            assert caps['history_days'] == 730 and caps['quota'] == QUOTA and caps['version'].startswith('db-')
            if body is not None:
                assert json.loads(call['body']) == body
        # a body or query edge-bff cannot read is refused, never forwarded on a guess
        n = len(FakeApi.calls)
        for method, path, kw in (('POST', 'bundle', {'content': b'{"ticker": "BBCA", "ticker": "TLKM"'}),
                                 ('POST', 'files', {'json': ['BBCA']}),
                                 ('POST', 'files', {'json': {'ticker': 5, 'dataset': 'price'}}),
                                 ('POST', 'bundle', {'json': {'ticker': 'BBCA', 'datasets': 'price'}}),
                                 ('GET', 'history/price?ticker=BBCA&ticker=TLKM&from=2019-01-01&to=2019-01-02', {})):
            r = c.request(method, f'/api/terminal/v1/{path}', headers={**h, 'content-type': 'application/json'}, **kw)
            assert r.status_code == 422 and r.json()['error']['code'] == 'INVALID_INPUT', (path, kw, r.text)
        assert len(FakeApi.calls) == n
        # duplicate JSON keys: the last one is checked, and only the checked body is sent
        r = c.post('/api/terminal/v1/bundle', headers={**h, 'content-type': 'application/json'},
                   content=b'{"ticker": "TLKM", "ticker": "BBCA", "datasets": ["price"]}')
        assert r.status_code == 200 and terminal_calls()[-1]['body'] == b'{"ticker":"BBCA","datasets":["price"]}'


def test_a_paid_principal_gets_every_ticker_and_dataset(switched_on, store):
    with TestClient(create_app(switched_on, store, FakeOrc())) as c:
        user = make_user(store, 'pat', 'pat-password')
        subscribe(store, user, paid_plan(store))
        h = sign_in(c, 'pat', 'pat-password')
        for method, path, body, _ in FREE_REFUSED:
            r = c.request(method, f'/api/terminal/v1/{path}', headers=h, json=body)
            assert r.status_code == 200, (path, r.text)
            call = terminal_calls()[-1]
            assert call['headers']['x-terminal-proxy-owner'] == user['owner_key']
            assert sent_caps(call) == {'v': 1, 'version': r.headers['x-edge-entitlements'], 'admin': False, 'tickers': '*',
                                       'datasets': ALL_DATASETS, 'history_days': None, 'quota': QUOTA}
        # a plan narrowed by an override: refused at once, on the next request. The catalog takes a Terminal limit
        # only once the account's Backtest and Screener are closed, since their workers read every stock (re-check
        # R1-36, user decision 2026-11-19 "2a", migration 20261119_030: the capabilities marked every_stock)
        db(store, '''INSERT INTO edge_bff.user_capability_overrides(user_id, capability_key, value, reason)
            SELECT %s, capability_key, 'false', 'test' FROM edge_bff.capabilities WHERE data_scope = 'every_stock' ''',
           user['user_id'])
        db(store, '''INSERT INTO edge_bff.user_capability_overrides(user_id, capability_key, value, reason)
            VALUES (%s, 'terminal.dataset', '{"ids": ["price"]}', 'test')''', user['user_id'])
        r = c.get('/api/terminal/v1/cut/BBCA/broker')
        assert r.status_code == 403 and r.json()['error']['details']['capability'] == 'terminal.dataset:broker'


def test_principal_capped_and_limit_read_the_quota_rows(switched_on, store):
    from app.principal import owner_principal
    user = make_user(store, 'quinn', 'quinn-password')
    subscribe(store, user, paid_plan(store))
    app = create_app(switched_on, store, FakeOrc())
    p = owner_principal(switched_on, app.state.auth.accounts, user['owner_key'])
    for name, value in QUOTA.items():
        assert p.limit(f'terminal.{name}') == value and p.capped(f'terminal.{name}', 10 ** 9) == value
    free = owner_principal(switched_on, app.state.auth.accounts, make_user(store, 'fay', 'fay-password')['owner_key'])
    assert terminal_access.capabilities(free)['quota'] == QUOTA


# ---- the cut relay -----------------------------------------------------------------------------------------------------

def test_the_cut_is_relayed_byte_for_byte(switched_on, store):
    with TestClient(create_app(switched_on, store, FakeOrc())) as c:
        make_user(store, 'freda', 'freda-password')
        sign_in(c, 'freda', 'freda-password')
        r = c.get(f'/api/terminal/v1/cut/BBCA/price?sha256={hashlib.sha256(CUT).hexdigest()}')
        assert r.status_code == 200
        assert hashlib.sha256(r.content).hexdigest() == hashlib.sha256(CUT).hexdigest() and r.content == CUT
        assert r.headers['content-type'] == 'application/gzip' and r.headers['content-length'] == str(len(CUT))
        assert r.headers['etag'] == '"cut1"' and r.headers['cache-control'] == 'private, max-age=60'
        assert r.headers['x-terminal-cut-sha256'] == hashlib.sha256(CUT).hexdigest()
        assert 'content-encoding' not in r.headers and 'x-other' not in r.headers and 'set-cookie' not in r.headers
        call = terminal_calls()[-1]
        assert call['url'] == f'{URL}/api/terminal/v1/cut/BBCA/price'
        assert call['params'] == {'sha256': hashlib.sha256(CUT).hexdigest()}
        assert sent_caps(call)['history_days'] == 730
        # no Content-Encoding reaches the page, whatever terminal-api sends: the raw gzip bytes are the file
        FakeApi.cut_headers = {'content-encoding': 'gzip', 'cache-control': 'no-store'}
        with c.stream('GET', '/api/terminal/v1/cut/BBCA/price') as s:
            raw = b''.join(s.iter_raw())
            assert 'content-encoding' not in s.headers and s.headers['cache-control'] == 'private, no-store'
        assert raw == CUT
        # a short read is never relayed as whole; another status passes through as JSON
        FakeApi.cut_headers = {'content-length': str(len(CUT) + 1)}
        assert c.get('/api/terminal/v1/cut/BBCA/price').json()['error']['code'] == 'TERMINAL_UNAVAILABLE'
        FakeApi.cut_headers = {}
        for bad in ('cut/BBCA/secrets', 'cut/bbca/price', 'cut/BBCA', 'cut/BBCA/price/2026', 'cut/BBCA/intraday'):
            assert c.get(f'/api/terminal/v1/{bad}').status_code == 404, bad


def test_a_cut_terminal_api_refuses_reaches_the_page_in_the_contract_shape(switched_off, store):
    """Re-check R1-1 (CONTRACT.md section 3): terminal-api's status passes, its code as details.reason, never its prose
    (its messages name internal routes); before, its flat body passed through."""
    with TestClient(create_app(switched_off, store, FakeOrc())) as c:
        login(c)
        r = c.get('/api/terminal/v1/cut/BBCA/yield')
        assert r.status_code == 404 and r.json()['error']['code'] == 'NOT_FOUND', r.text
        assert r.json()['error']['details'] == {'reason': 'cannot_cut'} and 'no' != r.json()['error']['message']


def test_terminal_apis_own_capability_refusal_is_relayed_in_edges_shape(switched_off, store):
    with TestClient(create_app(switched_off, store, FakeOrc())) as c:
        h = login(c)
        for r in (c.post('/api/terminal/v1/bundle', headers={**h, 'content-type': 'application/json'},
                         content=b'{"ticker":"BBCA","packs":true}'),
                  c.get('/api/terminal/v1/cut/BBCA/events')):
            assert r.status_code == 403, r.text
            error = r.json()['error']
            assert error['code'] == 'CAPABILITY_REQUIRED' and error['details'] == {
                'capability': 'terminal.history_days', 'display_name': 'Terminal history'}, error


def test_quota_bounds_and_the_owner_key_rule(settings):
    huge = principal(limits={'terminal.files_per_hour': 5 * 10 ** 9})
    assert terminal_access.capabilities(huge)['quota'] == {'files_per_hour': 10 ** 9}      # never wider than the plan
    # re-check R1-22: a limit of 0 allows none of it, so waiting would not help: 403 naming it, not a 429
    none = principal(limits={'terminal.files_per_hour': 0})
    with pytest.raises(terminal_access.Refusal) as e:
        terminal_access.capabilities_header(none)
    assert (e.value.status, e.value.code, e.value.details['capability']) == (403, 'CAPABILITY_REQUIRED',
                                                                             'terminal.files_per_hour')
    assert e.value.headers is None
    with pytest.raises(terminal_access.Refusal) as e:
        terminal_access.headers(settings, principal(owner_key='has space'))
    assert e.value.code == 'TERMINAL_UNAVAILABLE'
    sent = terminal_access.headers(settings, principal())
    assert set(sent) == {'content-type', *terminal_access.RESERVED}                       # both headers, always


# ---- the page files ---------------------------------------------------------------------------------------------------

def test_page_files_send_the_headers(switched_on, store):
    with TestClient(create_app(switched_on, store, FakeOrc())) as c:
        user = make_user(store, 'pat', 'pat-password')
        subscribe(store, user, paid_plan(store))
        sign_in(c, 'pat', 'pat-password')
        assert c.get('/api/v1/radar/index').status_code == 200
        r = c.get(f'/api/v1/radar/file/radar-days?sha={PAGE_SHA}')
        assert r.status_code == 200, r.text
        calls = terminal_calls()
        assert [(x['method'], x['url'].rsplit('/', 1)[1]) for x in calls] == [('GET', 'radar'), ('POST', 'radar')]
        for call in calls:
            assert call['headers']['x-terminal-proxy-key'] == KEY
            assert call['headers']['x-terminal-proxy-owner'] == user['owner_key']
            assert sent_caps(call)['datasets'] == ALL_DATASETS and sent_caps(call)['admin'] is False
        # the bucket's presigned GET carries none of them
        bucket = [x for x in FakeApi.calls if x['url'].startswith('https://bucket.example/')]
        assert bucket and all(not set(x['headers']) & set(terminal_access.RESERVED) for x in bucket)


# ---- the route walk ---------------------------------------------------------------------------------------------------

def dependency_calls(dependant):
    for dependency in dependant.dependencies:
        yield dependency.call
        yield from dependency_calls(dependency)


def forwarding_routes(app):
    """The routes that call terminal-api: the proxy's, the page files' and the examples' (their handlers are main.py
    terminal_read and terminal_write, pages.py page_index and page_file, and examples.py example_index and example_file:
    the Market Overview's example reads terminal-api for the principal: examples.LATEST)."""
    from app import examples
    for route in app.routes:
        if isinstance(route, APIRoute) and (route.endpoint.__name__ in ('terminal_read', 'terminal_write', 'page_index', 'page_file')
                                            or route.endpoint.__name__ in ('example_index', 'example_file')
                                            and route.path.split('/')[4] in examples.LATEST):
            yield route


def unguarded(app):
    return [f'{sorted(r.methods)} {r.path}' for r in forwarding_routes(app)
            if not any(getattr(call, 'terminal_guard', False) for call in dependency_calls(r.dependant))]


def test_every_terminal_forwarding_route_passes_the_guard(switched_off, store):
    app = create_app(switched_off, store, FakeOrc())
    paths = {(m, r.path) for r in forwarding_routes(app) for m in r.methods}
    from app import examples
    assert paths == {('GET', '/api/terminal/v1/{path:path}'), ('POST', '/api/terminal/v1/{path:path}'),
                     *{('GET', f'/api/v1/{f}/{p}') for f in ('radar', 'overview', 'watchlist', 'sector') for p in ('index', 'file/{name}')},
                     *{('GET', f'/api/v1/examples/{t}/{p}') for t in examples.LATEST for p in ('index', 'file/{name}')}}
    assert unguarded(app) == []
    # a route that forgets the guard is found
    auth = app.state.auth

    async def page_index(request: Request, p: Principal = Depends(auth.need('radar.view'))):
        return {}
    app.get('/api/v1/example/index')(page_index)
    assert unguarded(app) == ["['GET'] /api/v1/example/index"]


def test_the_proxy_key_and_the_terminal_headers_live_in_one_builder():
    """No module but terminal_access builds a terminal-api header: the proxy key (without which terminal-api answers
    nothing) is read only there, so a call that skips headers(settings, p) cannot reach terminal-api."""
    for path in sorted(APP.glob('*.py')):
        text = path.read_text()
        if path.name not in ('terminal_access.py', 'config.py'):
            assert 'terminal_proxy_key' not in text, path.name
        if path.name != 'terminal_access.py':
            # a header name written as a string (a comment or a docstring may name it)
            assert not re.search(r'''['"]x-terminal-(?:proxy|capabilities)''', text, re.I), path.name
    callers = {p.name for p in APP.glob('*.py') if '/api/terminal/v1/' in p.read_text() and 'terminal_url' in p.read_text()}
    assert callers == {'main.py', 'pages.py'}
    for name in callers:
        assert 'terminal_access.headers(' in (APP / name).read_text(), name


def test_every_forwarded_get_route_is_known_to_the_check():
    """terminal_access.check refuses a GET it does not know (fail closed); every GET route the proxy forwards is one it
    knows, so a new route regex without its check is a failing request, not an open one."""
    alternatives = main.TERMINAL_ROUTES['GET'].pattern.split('|')
    heads = {a.split('/')[0] for a in alternatives if '/' in a}
    assert heads == {'manifest', 'reference', 'history', 'logo', 'cut'}, heads
    assert main.TERMINAL_ROUTES['POST'].pattern == 'files|bundle'
    free = principal(limits={'terminal.tickers': ['BBCA']}, grants={'terminal.dataset': {'all': True}},
                     kinds={'terminal.dataset': 'items'})
    with pytest.raises(terminal_access.Refusal):
        terminal_access.check(free, 'GET', 'state', httpx.QueryParams(), None)
    with pytest.raises(terminal_access.Refusal):
        terminal_access.check(free, 'POST', 'xsection', httpx.QueryParams(), b'{"ticker": "BBCA"}')


# ---- the migration -------------------------------------------------------------------------------------------------

def test_the_quota_migration_holds_d6s_numbers_for_paid_and_free(store):
    rows = db(store, '''SELECT p.plan_key, pc.capability_key, pc.value, c.kind, c.unit, c.display_name
        FROM edge_bff.plan_capabilities pc JOIN edge_bff.capabilities c USING (capability_key)
        JOIN edge_bff.plans p USING (plan_key) WHERE pc.capability_key LIKE 'terminal.%%_per_%%' ''')
    by_plan = {}
    for r in rows:
        assert r['kind'] == 'limit' and r['unit'] and r['display_name'], r
        by_plan.setdefault(r['plan_key'], {})[r['capability_key'].removeprefix('terminal.')] = r['value']
    assert by_plan == {paid_plan(store): QUOTA, db(store, 'SELECT plan_key FROM edge_bff.plans WHERE is_default')[0]['plan_key']: QUOTA}
    assert not db(store, '''SELECT 1 FROM edge_bff.plan_capabilities WHERE capability_key LIKE 'terminal.%%_per_%%'
        AND plan_key IN (SELECT plan_key FROM edge_bff.plan_capabilities WHERE capability_key = '*' AND value = 'true'::jsonb)''')


def test_the_quota_migration_refuses_a_second_run(database):
    with psycopg.connect(database, autocommit=True) as conn:
        with pytest.raises(psycopg.errors.RaiseException, match='reconcile before applying'):
            conn.execute(MIGRATION.read_text())


def test_the_quota_migrations_verify_block_refuses_a_wrong_value(database):
    text = MIGRATION.read_text().replace('BEGIN;', '', 1).replace('COMMIT;', '', 1)
    wrong = text.replace("('free', 'terminal.files_per_hour', '300')", "('free', 'terminal.files_per_hour', '299')")
    assert wrong != text
    with psycopg.connect(database) as conn:
        conn.execute('''DELETE FROM edge_bff.capabilities WHERE capability_key IN ('terminal.tickers_per_hour',
            'terminal.tickers_per_day', 'terminal.files_per_hour', 'terminal.megabytes_per_day')''')
        conn.execute(text)                                              # the file itself passes its own verify
        conn.rollback()
        conn.execute('''DELETE FROM edge_bff.capabilities WHERE capability_key IN ('terminal.tickers_per_hour',
            'terminal.tickers_per_day', 'terminal.files_per_hour', 'terminal.megabytes_per_day')''')
        with pytest.raises(psycopg.errors.RaiseException, match='does not hold terminal.files_per_hour'):
            conn.execute(wrong)
        conn.rollback()
    assert len(db_rows(database)) == 8


def db_rows(database):
    with psycopg.connect(database) as conn:
        return conn.execute("SELECT 1 FROM edge_bff.plan_capabilities WHERE capability_key LIKE 'terminal.%_per_%'").fetchall()
