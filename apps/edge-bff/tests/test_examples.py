"""EXEC-MU-ACCOUNTS 3e, the example mode as the user set it on 2026-11-21 (app/examples.py; ERRORS M527): each data
page's example files, for a principal holding <tab>.example (the free plan; the guest plan, a visitor who is not signed
in, where the site has guests), served from memory; the table's checks and grants (migrations 20261121_001 and _002)."""
import dataclasses
import gzip
import hashlib
import json

import psycopg
import psycopg.types.json
import pytest
from fastapi.testclient import TestClient

from app import examples as examples_module, terminal_access
from app.config import LIVE
from app.main import create_app
from conftest import FakeOrc
from test_guest import VISITOR, guests  # noqa: F401 - the fixture
from test_plan_catalog import subscribe
from test_principal import db, make_user, on, sign_in, workers  # noqa: F401 - the fixtures
from test_terminal_access import api  # noqa: F401 - the fixture

AS_OF = '2026-10-30'
RADAR = {'radar-meta': {'schema': 1, 'filters': [{'id': 'S1'}]},
         'radar-days': {'schema': 1, 'dates': [AS_OF], 'boards': [AS_OF]},
         f'radar-board-{AS_OF}': {'schema': 1, 'date': AS_OF, 'rows': {'filter': ['S1']}}}


def gz(doc):
    return gzip.compress(json.dumps(doc, separators=(',', ':')).encode(), mtime=0)


def put(store, tab, files, as_of=AS_OF):
    db(store, 'DELETE FROM edge_bff.example_files WHERE tab = %s', tab)
    for name, doc in files.items():
        b = gz(doc)
        db(store, 'INSERT INTO edge_bff.example_files(tab, name, as_of, rows, bytes, sha256, body) '
                  'VALUES (%s, %s, %s, %s, %s, %s, %s)', tab, name, as_of, 1, len(b), hashlib.sha256(b).hexdigest(), b)


@pytest.fixture
def stored(store):
    put(store, 'radar', RADAR)
    yield
    db(store, 'DELETE FROM edge_bff.example_files')


def live(guests):
    """The live site's configuration, registration closed or not (pre-launch off, so a free account signs in)."""
    return dataclasses.replace(guests, site=LIVE, prelaunch_enabled=False, orc_url='', orc_key='')


def read_example(c, headers=None):
    """The index and every file it lists, checked against what is stored; the answers' headers."""
    r = c.get('/api/v1/examples/radar/index', headers=headers or {})
    assert r.status_code == 200, r.text
    index = r.json()
    assert r.headers['cache-control'] == 'private, no-cache'
    assert set(index['files']) == set(RADAR) and index['as_of'] == AS_OF and index['finished_at']
    for name, e in index['files'].items():
        f = c.get(f'/api/v1/examples/radar/file/{name}?sha={e["sha256"]}', headers=headers or {})
        assert f.status_code == 200 and f.json() == RADAR[name], name
        assert (f.headers['content-encoding'], f.headers['cache-control']) == ('gzip', 'private, no-cache')
        assert f.headers['etag'] == f'"{e["sha256"][:32]}"' and e['bytes'] == len(gz(RADAR[name]))
    return index


def test_a_visitor_reads_the_radar_example_and_nothing_else(guests, store, stored):
    put(store, 'watchlist', {'watchlist-meta': {'as_of': AS_OF}})             # another tab's rows: not the Radar's
    with TestClient(create_app(guests, store, FakeOrc())) as c:
        index = read_example(c, VISITOR)
        assert c.get('/api/v1/examples/radar/file/watchlist-meta', headers=VISITOR).status_code == 404
        e = index['files']['radar-meta']
        r = c.get(f'/api/v1/examples/radar/file/radar-meta?sha={e["sha256"]}',
                  headers={**VISITOR, 'if-none-match': f'"{e["sha256"][:32]}"'})
        assert r.status_code == 304 and r.headers['etag'] == f'"{e["sha256"][:32]}"'
        refused = {
            'radar-f-s1': (404, 'EXAMPLE_FILE_NOT_FOUND'),            # a click's file: not part of the example
            'radar-board-2026-10-29': (404, 'EXAMPLE_FILE_NOT_FOUND'),
            'Radar-meta': (400, 'EXAMPLE_INVALID_NAME'),
        }
        for name, (status, code) in refused.items():
            r = c.get(f'/api/v1/examples/radar/file/{name}', headers=VISITOR)
            assert (r.status_code, r.json()['error']['code']) == (status, code), name
            assert r.json()['error']['message'] and r.json()['error']['details']['tab'] == 'radar'
        r = c.get(f'/api/v1/examples/radar/file/radar-meta?sha={"0" * 64}', headers=VISITOR)
        assert r.status_code == 409 and r.json()['error']['details']['sha256'] == e['sha256']
        assert c.get('/api/v1/examples/radar/file/radar-meta?sha=XYZ', headers=VISITOR).status_code == 400
        # the Radar's live routes and the other tabs' examples stay closed to the visitor
        assert c.get('/api/v1/radar/index', headers=VISITOR).status_code == 401
        for tab in ('monitor', 'terminal', 'overview', 'watchlist', 'screener', 'backtest'):
            if tab not in examples_module.TABS:
                assert c.get(f'/api/v1/examples/{tab}/index', headers=VISITOR).status_code == 404, tab


@pytest.fixture
def plan_rows(store):
    """The plans' rows as the migrations left them, put back after the test (the plans live as long as the database)."""
    rows = db(store, 'SELECT plan_key, capability_key, value FROM edge_bff.plan_capabilities')
    yield
    for r in rows:
        db(store, 'INSERT INTO edge_bff.plan_capabilities(plan_key, capability_key, value) VALUES (%s, %s, %s) '
                  'ON CONFLICT DO NOTHING', r['plan_key'], r['capability_key'], psycopg.types.json.Jsonb(r['value']))


def second_factor(c, store, settings, h):
    """An admin's pending session past its second factor (tests/test_auth_flows.py: enrol, then a code of now)."""
    import time
    from app import mfa
    assert c.post('/api/v1/auth/mfa/enroll', headers=h).status_code == 200
    row = db(store, 'SELECT user_id, nonce FROM edge_bff.mfa_totp ORDER BY user_id DESC LIMIT 1')[0]
    secret = mfa.secret_of(settings.mfa_key, row['user_id'], bytes(row['nonce']))
    r = c.post('/api/v1/auth/mfa/verify', headers=h, json={'code': mfa.code_at(secret, int(time.time()) // 30)})
    assert r.status_code == 200 and r.json()['access']['mfa_ok'] is True, r.text


def test_the_example_needs_the_tabs_example_capability_for_a_visitor_and_an_account(guests, store, stored, plan_rows):
    with TestClient(create_app(guests, store, FakeOrc())) as c:
        free = make_user(store, 'freda', 'freda-password')                  # the default plan: free
        paid = make_user(store, 'pablo', 'pablo-password')
        subscribe(store, paid['user_id'], 'paid')
        make_user(store, 'ada', 'ada-password', role='admin')
        # the admin: before its second factor, refused as every capability route refuses it; with it ('*' holds every
        # capability, radar.example too) it reads the example, while the shell opens the live page for it, which holds
        # radar.view (static/edge-app.js App: the example only without <tab>.view)
        admin = sign_in(c, 'ada', 'ada-password')
        r = c.get('/api/v1/examples/radar/index', headers=admin)
        assert (r.status_code, r.json()['error']['code']) == (403, 'MFA_REQUIRED')
        second_factor(c, store, guests, admin)
        read_example(c, admin)
        held = c.get('/api/v1/auth/session', headers=admin).json()['access']['capabilities']
        assert '*' in held
        c.post('/api/v1/auth/sign-out', headers=admin)
        read_example(c, sign_in(c, 'freda', 'freda-password'))
        c.post('/api/v1/auth/sign-out', headers=sign_in(c, 'freda', 'freda-password'))
        r = c.get('/api/v1/examples/radar/index', headers=sign_in(c, 'pablo', 'pablo-password'))
        assert r.status_code == 403 and r.json()['error']['code'] == 'CAPABILITY_REQUIRED'   # the live Radar instead
        assert r.json()['error']['details']['capability'] == 'radar.example'
        c.post('/api/v1/auth/sign-out', headers=sign_in(c, 'pablo', 'pablo-password'))
        c.cookies.clear()
        # the plan's rows, read on every request: without the guest plan's row the visitor is asked to sign in
        db(store, "DELETE FROM edge_bff.plan_capabilities WHERE plan_key = 'guest' AND capability_key = 'radar.example'")
        r = c.get('/api/v1/examples/radar/index', headers=VISITOR)
        assert r.status_code == 403 and r.json()['error']['details'] == {'capability': 'radar.example', 'visitor': True,
                                                                        'display_name': 'Radar example'}
        assert 'Sign in' in r.json()['error']['message'] and 'Upgrade' not in r.json()['error']['message']
        db(store, "DELETE FROM edge_bff.plan_capabilities WHERE plan_key = 'free' AND capability_key = 'radar.example'")
        r = c.get('/api/v1/examples/radar/index', headers=sign_in(c, 'freda', 'freda-password'))
        assert r.status_code == 403 and r.json()['error']['code'] == 'CAPABILITY_REQUIRED'
    assert free['user_id'] != paid['user_id']


def test_on_the_live_site_the_visitor_and_the_free_plan_read_it_and_the_beta_has_no_visitor(guests, on, store, stored):
    with TestClient(create_app(live(guests), store, FakeOrc())) as c:
        read_example(c, VISITOR)
        guest = c.get('/api/v1/auth/guest', headers=VISITOR).json()['access']['capabilities']
        assert 'radar.example' in guest and not [k for k in guest if k.startswith('monitor.')]
        make_user(store, 'freda', 'freda-password')
        h = sign_in(c, 'freda', 'freda-password')
        read_example(c, h)
        held = c.get('/api/v1/auth/session', headers=h).json()['access']['capabilities']
        # the live view keeps the data pages' examples and drops the Monitor's (beta only), which the free plan holds
        assert {'radar.example', 'overview.example', 'watchlist.example', 'screener.example', 'backtest.example'} <= set(held)
        assert 'monitor.example' not in held
        assert db(store, "SELECT 1 FROM edge_bff.plan_capabilities WHERE plan_key = 'free' AND capability_key = 'monitor.example'")
    with TestClient(create_app(on, store, FakeOrc())) as c:                # the beta: no visitor without an account
        assert c.get('/api/v1/examples/radar/index', headers=VISITOR).status_code == 401


def test_the_files_are_served_from_memory_and_read_again_after_the_refresh(guests, store, stored, monkeypatch):
    reads = []
    real = examples_module.Stored.read

    def counted(self, held):
        reads.append(self.tab)
        return real(self, held)
    monkeypatch.setattr(examples_module.Stored, 'read', counted)
    with TestClient(create_app(guests, store, FakeOrc())) as c:
        for _ in range(3):
            read_example(c, VISITOR)
        assert reads == ['radar']                                             # one read for every request since
        db(store, 'DELETE FROM edge_bff.example_files')
        read_example(c, VISITOR)                                              # within REFRESH_SECONDS: as kept
        monkeypatch.setattr(examples_module, 'REFRESH_SECONDS', 0)
        r = c.get('/api/v1/examples/radar/index', headers=VISITOR)
        assert r.status_code == 404 and r.json()['error']['code'] == 'EXAMPLE_NOT_READY'
        put(store, 'radar', RADAR)
        read_example(c, VISITOR)

        # a capture made again with other content (the example-mode checker, ERRORS M527): after REFRESH_SECONDS the
        # changed file is served with its new bytes and sha, the old sha is answered as replaced
        old = c.get('/api/v1/examples/radar/index', headers=VISITOR).json()['files']['radar-meta']['sha256']
        RADAR['radar-meta'] = {**RADAR['radar-meta'], 'filters': [{'id': 'S1'}, {'id': 'S2'}]}
        try:
            put(store, 'radar', RADAR)
            index = read_example(c, VISITOR)
            assert index['files']['radar-meta']['sha256'] != old
            r = c.get(f'/api/v1/examples/radar/file/radar-meta?sha={old}', headers=VISITOR)
            assert r.status_code == 409 and r.json()['error']['code'] == 'EXAMPLE_FILE_REPLACED'
        finally:
            RADAR['radar-meta'] = {'schema': 1, 'filters': [{'id': 'S1'}]}
        put(store, 'radar', RADAR)
        read_example(c, VISITOR)

        def broken(self, held):
            raise psycopg.OperationalError('connection to server at "secret-host" failed')
        monkeypatch.setattr(examples_module.Stored, 'read', broken)
        read_example(c, VISITOR)                                              # the last good copy stands
    with TestClient(create_app(guests, store, FakeOrc())) as c:              # nothing kept and the read fails
        r = c.get('/api/v1/examples/radar/index', headers=VISITOR)
        assert r.status_code == 503 and r.json()['error']['code'] == 'EXAMPLE_UNAVAILABLE'
        assert 'secret-host' not in r.text


@pytest.mark.parametrize('query, was, now', [
    ('BODIES_SQL', 'SELECT name, sha256, body', "SELECT name, sha256, body || '\\x00'::bytea AS body"),   # one byte more
    ('BODIES_SQL', 'SELECT name, sha256, body', "SELECT name, sha256, overlay(body placing '\\x00'::bytea from 1 for 1) AS body"),
    ('LIST_SQL', 'rows, bytes,', 'rows, bytes + 1 AS bytes,'),        # the row's size not the body's (the index lists it)
], ids=['longer', 'same-size-other-hash', 'row-size'])
def test_a_body_read_from_the_table_that_does_not_match_its_sha_is_never_served(guests, store, stored, monkeypatch, query, was, now):
    """The example-mode checker (ERRORS M527): Stored.read checks every body it reads against its row's sha256 and size
    (the table's CHECKs make a mismatch impossible to write; this is the second line). A body that comes back other
    than its sha is refused: nothing is served from it, and nothing kept stands in on the first read. Each half of the
    check is held by one case (the re-check: a longer body alone left the hash half free)."""
    assert was in getattr(examples_module, query)
    monkeypatch.setattr(examples_module, query, getattr(examples_module, query).replace(was, now))
    with TestClient(create_app(guests, store, FakeOrc())) as c:
        r = c.get('/api/v1/examples/radar/index', headers=VISITOR)
        assert r.status_code == 503 and r.json()['error']['code'] == 'EXAMPLE_UNAVAILABLE'
        r = c.get('/api/v1/examples/radar/file/radar-meta', headers=VISITOR)
        assert r.status_code == 503 and r.json()['error']['code'] == 'EXAMPLE_UNAVAILABLE'


def test_the_table_keeps_only_rows_whose_bytes_and_name_match_and_edge_bff_only_reads_it(database, store):
    b = gz({'date': AS_OF})
    good = ('radar', 'radar-meta', AS_OF, 1, len(b), hashlib.sha256(b).hexdigest(), b)
    bad = {'sha256': good[:5] + ('0' * 64, b), 'bytes': good[:4] + (len(b) + 1,) + good[5:],
           'name of another tab': ('radar', 'overview-meta') + good[2:], 'name form': ('radar', 'radar meta') + good[2:]}
    sql = ('INSERT INTO edge_bff.example_files(tab, name, as_of, rows, bytes, sha256, body) '
           'VALUES (%s, %s, %s, %s, %s, %s, %s)')
    with psycopg.connect(database) as c:
        for why, row in bad.items():
            with pytest.raises(psycopg.errors.CheckViolation), c.transaction():
                c.execute(sql, row)
        c.execute('SET ROLE edge_bff_runtime')
        assert c.execute('SELECT count(*) FROM edge_bff.example_files').fetchone()[0] == 0
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute(sql, good)


def test_the_provisioned_login_only_reads_the_example_table(database, monkeypatch):
    """scripts/provision_edge_bff_login.py knows the table of 20261121_001 (EXAMPLE_GRANTS): the login it provisions reads
    the stored examples and writes none of them (the capture job writes as the owner); a write grant is refused."""
    import importlib.util
    import os
    import secrets
    from urllib.parse import urlsplit, urlunsplit
    helper = Path(__file__).resolve().parents[3] / 'scripts/provision_edge_bff_login.py'
    spec = importlib.util.spec_from_file_location('edge_provision_examples', helper)
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
            conn.execute('SELECT * FROM edge_bff.example_files LIMIT 0')
            for statement in ("DELETE FROM edge_bff.example_files", "UPDATE edge_bff.example_files SET rows = 0",
                              'TRUNCATE edge_bff.example_files'):
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    conn.execute(statement)
                conn.rollback()
        with psycopg.connect(database, autocommit=True) as conn:
            conn.execute('GRANT INSERT ON edge_bff.example_files TO edge_bff_runtime')
        with pytest.raises(RuntimeError, match='Unexpected EDGE grants'):
            module.main()
    finally:
        with psycopg.connect(database, autocommit=True) as conn:
            conn.execute('REVOKE INSERT ON edge_bff.example_files FROM edge_bff_runtime')
            conn.execute('DROP OWNED BY edge_bff_login')
            conn.execute('DROP ROLE IF EXISTS edge_bff_login')


# ---- the Market Overview: its latest market date, trimmed to the opening view (the user: "1. tetap seperti itu 2. ok") -
import httpx  # noqa: E402
import re  # noqa: E402
from pathlib import Path  # noqa: E402

from app import principal as principal_module  # noqa: E402
from example_docs import OVERVIEW_DATES, OVERVIEW_DAYS, overview_files  # noqa: E402
from test_terminal_access import FakeApi, terminal_calls  # noqa: E402

NEWEST = OVERVIEW_DAYS[-1]
OPENING = {'overview-meta', 'overview-series', f'overview-day-{NEWEST}'}


class OverviewApi(FakeApi):
    """terminal-api's /overview routes and the bucket, serving a made-up publication (example_docs.overview_files)."""
    files = {}

    def answer(self, method, url, content):
        if url.endswith('/api/terminal/v1/overview') and method == 'GET':
            return httpx.Response(200, json={'finished_at': '2026-11-20T11:00:00Z', 'files': {
                n: {'sha256': hashlib.sha256(b).hexdigest(), 'bytes': len(b), 'rows': 1, 'as_of': NEWEST}
                for n, b in OverviewApi.files.items()}})
        if url.endswith('/api/terminal/v1/overview') and method == 'POST':
            name = json.loads(content)['names'][0]
            b = OverviewApi.files[name]
            return httpx.Response(200, json={'files': [{'name': name, 'url': f'https://bucket.example/overview/{name}',
                                                        'sha256': hashlib.sha256(b).hexdigest(), 'bytes': len(b)}]})
        return super().answer(method, url, content)

    def stream(self, method, url, params=None, headers=None):
        if not url.startswith('https://bucket.example/overview/'):
            return super().stream(method, url, params, headers)
        body = OverviewApi.files[url.rsplit('/', 1)[1]]

        class Answer:
            status_code = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def aiter_bytes(self):
                yield body
        return Answer()


@pytest.fixture
def overview_api(api, monkeypatch):
    monkeypatch.setattr(httpx, 'AsyncClient', OverviewApi)
    OverviewApi.files = {n: gz(doc) for n, doc in overview_files().items()}
    return OverviewApi


def overview_example(c, headers):
    r = c.get('/api/v1/examples/overview/index', headers=headers)
    assert r.status_code == 200, r.text
    index = r.json()
    files = {}
    for name, e in index['files'].items():
        f = c.get(f'/api/v1/examples/overview/file/{name}?sha={e["sha256"]}', headers=headers)
        assert f.status_code == 200 and f.headers['etag'] == f'"{e["sha256"][:32]}"', name
        files[name] = f.json()
    return index, files


def test_a_visitor_reads_the_latest_overview_trimmed_to_its_opening_view(guests, store, overview_api):
    live = overview_files()
    with TestClient(create_app(guests, store, FakeOrc())) as c:
        index, files = overview_example(c, VISITOR)
        assert set(index['files']) == OPENING and index['as_of'] == NEWEST
        meta, series, day = files['overview-meta'], files['overview-series'], files[f'overview-day-{NEWEST}']
        # the date picker holds the example's day; the rest of meta is the publication's (the index and group filter)
        assert meta['dates'] == [NEWEST] and {k: v for k, v in meta.items() if k != 'dates'} == \
            {k: v for k, v in live['overview-meta'].items() if k != 'dates'}
        # the series: breadth's 120 sessions and their start (the dates, the EMA shares); the index and sector lines in
        # their own 60 sessions and start, null before (read by position); the KPI strip's 30 turnover sessions; no daily
        # foreign buy or sell (5 or 20 of them sum to the locked 5D and 1M flow periods) and no breadth_n
        n, w = examples_module.OVERVIEW_SESSIONS, examples_module.OVERVIEW_INDEX_SESSIONS
        assert series['dates'] == OVERVIEW_DATES[-n:] and len(OVERVIEW_DATES) > n > w
        for k in ('index', 'sector'):
            assert {t: v for t, v in series[k].items()} == {t: [None] * (n - w) + v[-w:] for t, v in live['overview-series'][k].items()}
        for k in ('above_ema50', 'above_ema200'):
            assert series[k] == live['overview-series'][k][-n:]
        assert 'breadth_n' not in series
        m = examples_module.OVERVIEW_FLOW_SESSIONS
        flow = live['overview-series']['flow']
        assert series['flow'] == {'dates': flow['dates'][-m:], 'turnover': flow['turnover'][-m:]}
        # the day: its 1D figures; every other period's values null; the 1D flow period; the session's 5-minute bars
        stocks, was = day['stocks'], live[f'overview-day-{NEWEST}']['stocks']
        for k in ('i', 'close', 'r1d', 'size', 'above_ema50', 'above_ema200', 'fnet_1d'):
            assert stocks[k] == was[k], k
        for k in ('r5d', 'r1m', 'fnet_5d', 'fnet_1m', 'fnet_3m'):
            assert any(v is not None for v in was[k]) and stocks[k] == [None] * len(was[k]), k
        assert day['market']['periods'] == {'1D': live[f'overview-day-{NEWEST}']['market']['periods']['1D']}
        assert day['market']['foreign_net_10d'] == live[f'overview-day-{NEWEST}']['market']['foreign_net_10d']
        assert list(day['intraday']) == ['5m'] and day['intraday']['5m'] == live[f'overview-day-{NEWEST}']['intraday']['5m']
        # the files behind other views stay with overview.view
        for name in ('overview-stocks', *(f'overview-day-{d}' for d in OVERVIEW_DAYS[:-1])):
            r = c.get(f'/api/v1/examples/overview/file/{name}', headers=VISITOR)
            assert (r.status_code, r.json()['error']['code']) == (404, 'EXAMPLE_FILE_NOT_FOUND'), name
        assert c.get('/api/v1/overview/index', headers=VISITOR).status_code == 401
        # terminal-api was asked as the visitor (the guest owner, the gateway key), once per file and publication
        calls = [x for x in terminal_calls() if x['url'].endswith('/api/terminal/v1/overview')]
        assert calls and all(x['headers'][terminal_access.OWNER_HEADER] == principal_module.GUEST_OWNER for x in calls)
        before = len(calls)
        overview_example(c, VISITOR)
        assert len([x for x in terminal_calls() if x['url'].endswith('/api/terminal/v1/overview')]) <= before + 1


def test_a_field_the_opening_view_does_not_read_is_left_out_or_null(guests, store, overview_api):
    """Fail closed at every depth (the example-mode checker, ERRORS M527): a field the publisher adds later, at the top
    of a file or inside any of its blocks, is not in the example until this module names it; a value that turns into
    an object where a value was is null."""
    docs = overview_files()
    meta, series, day = docs['overview-meta'], docs['overview-series'], docs[f'overview-day-{NEWEST}']
    planted = 'PLANTED-' + '9' * 12                        # a value that must not reach the example, wherever it is put
    meta['secret_history'] = list(range(300))
    meta['stocks']['free_float'] = [planted] * len(meta['stocks']['ticker'])
    meta['sectors'][0]['history'] = planted
    meta['lists'][0]['added_on'] = planted
    meta['periods']['other'] = [planted]
    series['new_history'] = [1.0] * len(OVERVIEW_DATES)
    series['flow']['foreign_net_5d'] = [planted] * len(series['flow']['dates'])
    series['index']['IHSG'][-1] = {'close': planted}       # an object where a value was
    day['new_block'] = {'x': 1}
    day['index']['IHSG']['r5d'] = planted
    day['index']['IHSG']['history_1y'] = [planted]
    day['index']['IHSG']['close'] = {'deep': planted}       # a named value that turns into an object: null
    meta['lists'][0]['members'] = [{'ticker': planted}]
    day['volatility']['history'] = [planted]
    day['breadth']['by_period'] = {'5D': planted}
    day['stocks']['r3m'] = [5.0] * len(day['stocks']['i'])
    day['stocks']['close'][0] = {'v': planted}             # a kept column that holds an object: null
    day['market']['periods']['6M'] = {'buy': 1, 'sell': 1, 'net': 0, 'from': OVERVIEW_DATES[0]}
    day['market']['periods']['1D']['r5d'] = planted
    day['market']['by_period'] = {'5D': planted}
    series['flow']['turnover'][-1] = {'deep': planted}     # a named flow series whose value turns into an object
    day['market']['turnover_avg20'] = {'deep': planted}     # a named market value that turns into an object
    day['intraday']['1m'] = {'t': [1], 'c': [1.0]}
    day['intraday']['5m']['v'] = [planted]
    OverviewApi.files = {n: gz(doc) for n, doc in docs.items()}
    with TestClient(create_app(guests, store, FakeOrc())) as c:
        _, files = overview_example(c, VISITOR)
    shown = files[f'overview-day-{NEWEST}']
    assert planted not in json.dumps(files)
    assert 'secret_history' not in files['overview-meta'] and 'new_history' not in files['overview-series']
    assert 'new_block' not in shown and set(shown['market']['periods']) == {'1D'} and list(shown['intraday']) == ['5m']
    assert shown['stocks']['r3m'] == [None] * len(shown['stocks']['i']) and shown['stocks']['close'][0] is None
    assert files['overview-series']['index']['IHSG'] == [] and 'by_period' not in shown['market']
    assert shown['index']['IHSG']['close'] is None and files['overview-meta']['lists'][0]['members'] is None
    assert files['overview-series']['flow']['turnover'] == [] and shown['market']['turnover_avg20'] is None


def leaf_values(doc, at=''):
    """{path: value} of every value holding no object (leaf_paths' paths; a list of objects read item by item)."""
    if isinstance(doc, dict):
        out = {}
        for k, v in doc.items():
            out.update(leaf_values(v, f'{at}.{k}' if at else k))
        return out or {at: doc}
    if isinstance(doc, list) and not examples_module.flat(doc):
        out = {}
        for k, x in enumerate(doc):
            out.update({f'{p}[{k}]': v for p, v in leaf_values(x, at).items()})
        return out
    return {at: doc}


def leaf_paths(doc, at=''):
    """Every path of a JSON document to a value holding no object: object keys joined by '.', a list of objects read
    item by item (its items' paths share the list's)."""
    if isinstance(doc, dict):
        return {p for k, v in doc.items() for p in leaf_paths(v, f'{at}.{k}' if at else k)} or {at}
    if isinstance(doc, list) and not examples_module.flat(doc):
        return {p for x in doc for p in leaf_paths(x, at)}
    return {at}


def test_every_field_the_publisher_writes_is_kept_by_name_or_left_out_by_name():
    """Every path the publisher's own builders write (overview.py meta_doc, series_doc, day_doc, through
    example_docs.overview_files) is either in the example as it was written or named in OVERVIEW_LEFT_OUT (out, or null
    where the page reads by position), and every name there is one the publisher writes: a new field of the publisher
    fails here until the trim decides on it."""
    docs = overview_files()
    trimmed = {n: doc for n, doc, _ in examples_module.overview_view(docs['overview-meta'], docs['overview-series'],
                                                                      docs[f'overview-day-{NEWEST}'])}
    under = lambda p, names: any(p == n or p.startswith(n + '.') for n in names)
    for name, family in (('overview-meta', 'overview-meta'), ('overview-series', 'overview-series'),
                         (f'overview-day-{NEWEST}', 'overview-day')):
        left = examples_module.OVERVIEW_LEFT_OUT.get(family, ())
        written, shown = leaf_paths(docs[name]), leaf_paths(trimmed[name])
        assert {p for p in written - shown if not under(p, left)} == set(), name
        for n in left:
            assert any(under(p, (n,)) for p in written), f'{n}: not a field the publisher writes'
            value = trimmed[name]
            for k in n.split('.'):
                value = value.get(k) if isinstance(value, dict) else None
            assert value is None or (isinstance(value, list) and all(v is None for v in value)), n
        # every value kept is the one written: whole, or (a series of the opening view's window, the date picker) the
        # written list's last points, null before the window; a value emptied that was not empty is named above
        wv, sv = leaf_values(docs[name]), leaf_values(trimmed[name])
        for p, v in sv.items():
            if under(p, left) or v is None:
                continue
            w = wv[p]
            if v == w:
                continue
            assert isinstance(v, list) and isinstance(w, list) and len(v) <= len(w), (name, p)
            tail = w[len(w) - len(v):]
            assert all(x is None or x == y for x, y in zip(v, tail)) and any(x is not None for x in v), (name, p)
            assert family == 'overview-series' or p == 'dates', (name, p, 'cut, but not a windowed series')
        emptied = [p for p, v in sv.items() if not under(p, left) and wv.get(p) not in (None, [])
                   and (v is None or (isinstance(v, list) and all(x is None for x in v)))]
        assert emptied == [], (name, 'emptied but not named in OVERVIEW_LEFT_OUT', emptied)


def test_the_trim_follows_the_overview_pages_opening_view():
    """The windows and the period the server keeps are the page's own defaults (overview/src/app.ts): the widest window
    a panel opens on (and its start), the KPI strip's last30, and 1D for every period control."""
    app_ts = (Path(__file__).resolve().parents[1] / 'overview' / 'src' / 'app.ts').read_text()
    default = dict(re.findall(r"(\w+): '([^']+)'", re.search(r'const DEFAULT[^=]*= \{([^}]*)\}', app_ts).group(1)))
    window = {k: int(v) for k, v in re.findall(r"'(\d+D)': (\d+)", re.search(r'const WINDOW[^=]*= \{([^}]*)\}', app_ts).group(1))}
    windows = [int(v[:-1]) for v in default.values() if v.endswith('D') and v != '1D']
    assert windows and max(windows) + 1 == examples_module.OVERVIEW_SESSIONS and set(windows) <= {60, 120} | set(window.values())
    assert {v for v in default.values() if not (v.endswith('D') and v != '1D')} == {examples_module.OVERVIEW_PERIOD}
    assert re.search(r"pick\('per', '1D'\)", app_ts) and examples_module.OVERVIEW_PERIOD == '1D'
    assert re.search(r'const last30 = .*e - 29', app_ts) and examples_module.OVERVIEW_FLOW_SESSIONS == 30
    # each line kept for the panel that reads it: breadth (brp) the dates and the EMA shares, Sector Performance (sp) the
    # index and sector lines, whose last 30 the KPI strip's sparkline reads too
    assert int(default['brp'][:-1]) + 1 == examples_module.OVERVIEW_SESSIONS
    assert int(default['sp'][:-1]) + 1 == examples_module.OVERVIEW_INDEX_SESSIONS >= 30


def test_the_overview_example_is_the_free_plans_and_follows_a_new_publication(guests, store, overview_api):
    with TestClient(create_app(guests, store, FakeOrc())) as c:
        make_user(store, 'freda', 'freda-password')
        h = sign_in(c, 'freda', 'freda-password')
        index, _ = overview_example(c, h)
        assert index['as_of'] == NEWEST
        paid = make_user(store, 'pablo', 'pablo-password')
        subscribe(store, paid['user_id'], 'paid')
        c.post('/api/v1/auth/sign-out', headers=h)
        r = c.get('/api/v1/examples/overview/index', headers=sign_in(c, 'pablo', 'pablo-password'))
        assert r.status_code == 403 and r.json()['error']['details']['capability'] == 'overview.example'
    # the next publication's newest day is the example's (the relay's index is read again after INDEX_SECONDS)
    docs = overview_files()
    later = dict(docs[f'overview-day-{NEWEST}'], date='2026-11-23')
    OverviewApi.files['overview-day-2026-11-23'] = gz(later)
    with TestClient(create_app(guests, store, FakeOrc())) as c:
        index, files = overview_example(c, VISITOR)
        assert index['as_of'] == '2026-11-23' and 'overview-day-2026-11-23' in index['files']


@pytest.mark.parametrize('tab', sorted(examples_module.LATEST))
def test_a_principals_own_terminal_refusal_on_a_latest_example_keeps_its_code(guests, store, watchlist_api, monkeypatch, tab):
    """The example-mode checker (ERRORS M527): the Overview example builds the principal's terminal-api headers first
    (terminal_access.headers: a guest without a well-formed visitor key, a ticker list too long for the header, a limit
    of 0 where the database allows one); such a refusal of the principal itself is answered with its own status, code
    and way on, as the Terminal's relay answers it (app/pages.py), not as the example's outage EXAMPLE_UNAVAILABLE."""
    from app.errors import Refusal
    own = Refusal(403, 'CAPABILITY_REQUIRED', {'capability': 'terminal.files_per_hour'})

    def refused(settings, p):
        raise own
    with TestClient(create_app(guests, store, FakeOrc())) as c:
        (overview_example if tab == 'overview' else watchlist_example)(c, VISITOR)   # it opens; then the principal is refused
        monkeypatch.setattr(examples_module.terminal_access, 'headers', refused)
        for path in (f'/api/v1/examples/{tab}/index', f'/api/v1/examples/{tab}/file/{tab}-meta'):
            r = c.get(path, headers=VISITOR)
            assert r.status_code == 403, (path, r.text)
            error = r.json()['error']
            assert (error['code'], error['details'].get('capability')) == ('CAPABILITY_REQUIRED', 'terminal.files_per_hour'), error


def test_a_request_carrying_a_header_edge_bff_sets_itself_is_refused_on_the_overview_example(guests, store, stored, overview_api):
    """The example-mode re-check (ERRORS M527): the Overview's example calls terminal-api for the principal, so its routes
    pass terminal_access.guard: a reserved header is refused before any cache or terminal-api."""
    with TestClient(create_app(guests, store, FakeOrc())) as c:
        for tab in examples_module.LATEST:
            for path in (f'/api/v1/examples/{tab}/index', f'/api/v1/examples/{tab}/file/{tab}-meta'):
                for name in (terminal_access.OWNER_HEADER, terminal_access.CAPABILITIES_HEADER):
                    r = c.get(path, headers={**VISITOR, name: 'someone-else'})
                    assert (r.status_code, r.json()['error']['code']) == (400, 'HEADER_NOT_ALLOWED'), (path, name, r.text)
        index, _ = overview_example(c, VISITOR)                  # without it, the example opens
        assert index['as_of'] == NEWEST


# ---- the Watchlist: its latest price date, the list's stocks with the default indicators (the user, 2026-11-21: "Untuk
# table watchlist nggak apa-apa pakai data latest saja"; "Benar opsi B") ------------------------------------------------
from example_docs import WATCHLIST_AS_OF, WATCHLIST_BROKER, watchlist_files  # noqa: E402

WATCHLIST_OPENING = {'watchlist-stocks', 'watchlist-lists'}


def streamed(body):
    """A bucket object's answer, as httpx's stream gives it."""
    class Answer:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def aiter_bytes(self):
            yield body
    return Answer()


class PagesApi(OverviewApi):
    """OverviewApi, and terminal-api's /watchlist routes and bucket serving a made-up Watchlist publication
    (example_docs.watchlist_files)."""
    watchlist = {}

    def answer(self, method, url, content):
        if url.endswith('/api/terminal/v1/watchlist') and method == 'GET':
            return httpx.Response(200, json={'finished_at': '2026-11-20T11:05:00Z', 'files': {
                n: {'sha256': hashlib.sha256(b).hexdigest(), 'bytes': len(b), 'rows': 1, 'as_of': WATCHLIST_AS_OF}
                for n, b in PagesApi.watchlist.items()}})
        if url.endswith('/api/terminal/v1/watchlist') and method == 'POST':
            name = json.loads(content)['names'][0]
            b = PagesApi.watchlist[name]
            return httpx.Response(200, json={'files': [{'name': name, 'url': f'https://bucket.example/watchlist/{name}',
                                                        'sha256': hashlib.sha256(b).hexdigest(), 'bytes': len(b)}]})
        return super().answer(method, url, content)

    def stream(self, method, url, params=None, headers=None):
        if url.startswith('https://bucket.example/watchlist/'):
            return streamed(PagesApi.watchlist[url.rsplit('/', 1)[1]])
        return super().stream(method, url, params, headers)


@pytest.fixture
def watchlist_api(overview_api, monkeypatch):
    monkeypatch.setattr(httpx, 'AsyncClient', PagesApi)
    PagesApi.watchlist = {n: gz(doc) for n, doc in watchlist_files().items()}
    return PagesApi


def watchlist_example(c, headers):
    r = c.get('/api/v1/examples/watchlist/index', headers=headers)
    assert r.status_code == 200, r.text
    index = r.json()
    files = {}
    for name, e in index['files'].items():
        f = c.get(f'/api/v1/examples/watchlist/file/{name}?sha={e["sha256"]}', headers=headers)
        assert f.status_code == 200 and f.headers['etag'] == f'"{e["sha256"][:32]}"', name
        files[name] = f.json()
    return index, files


def lq45(meta):
    return next(x['members'] for x in meta['lists'] if (x['kind'], x['code']) == examples_module.WATCHLIST_LIST)


def test_a_visitor_reads_the_latest_watchlist_cut_to_the_lists_stocks_with_the_default_indicators(guests, store, watchlist_api):
    live, meta = watchlist_files()['watchlist-stocks'], overview_files()['overview-meta']
    members = lq45(meta)
    assert 0 < len(members) < len(live['ticker'])               # the list is a part of the file: the cut checks something
    with TestClient(create_app(guests, store, FakeOrc())) as c:
        index, files = watchlist_example(c, VISITOR)
        assert set(index['files']) == WATCHLIST_OPENING and index['as_of'] == WATCHLIST_AS_OF
        assert all(e['as_of'] == WATCHLIST_AS_OF for e in index['files'].values())
        s, at = files['watchlist-stocks'], {t: i for i, t in enumerate(live['ticker'])}
        # the list's stocks, every column of the table as published, in the list's order
        assert s['ticker'] == members
        for k in examples_module.WATCHLIST_COLUMNS:
            assert s[k] == [live[k][at[t]] for t in members], k
        # the four default indicators as published; every other one null (adding one is a click), filled in the file
        assert s['default'] == live['default'] == ['rsi', 'volr', 'dd60', 'fn5']
        for k, v in live['values'].items():
            want = [v[at[t]] for t in members]
            if k in live['default']:
                assert s['values'][k] == want and any(x is not None for x in want), k
            else:
                assert any(x is not None for x in want) and s['values'][k] == [None] * len(members), k
        # the dates of the data as published: prices to the latest date, broker data to its own (later than none)
        assert (s['prices_through'], s['broker_through'], s['dates']) == (WATCHLIST_AS_OF, WATCHLIST_BROKER, live['dates'])
        assert (s['catalog'], s['schema'], s['event_days']) == (live['catalog'], live['schema'], live['event_days'])
        # no upcoming corporate action, though the file holds one of a member; no Radar file (radar.view)
        assert any(t in live['events'] for t in members) and s['events'] == {} and s['events_loaded'] is None
        assert files['watchlist-lists'] == {'limits': [], 'lists': [{
            'id': examples_module.WATCHLIST_LIST_ID, 'name': 'LQ45', 'position': 0, 'indicators': None,
            'tickers': [{'ticker': t, 'position': i} for i, t in enumerate(members)]}]}
        r = c.get('/api/v1/examples/watchlist/file/watchlist-radar', headers=VISITOR)
        assert (r.status_code, r.json()['error']['code']) == (404, 'EXAMPLE_FILE_NOT_FOUND')
        assert c.get('/api/v1/watchlist/index', headers=VISITOR).status_code == 401
        # terminal-api was asked as the visitor (the guest owner, the gateway key), for both publications
        for family in ('watchlist', 'overview'):
            calls = [x for x in terminal_calls() if x['url'].endswith(f'/api/terminal/v1/{family}')]
            assert calls and all(x['headers'][terminal_access.OWNER_HEADER] == principal_module.GUEST_OWNER for x in calls), family


def test_a_field_the_watchlist_example_does_not_read_is_left_out_or_null(guests, store, watchlist_api):
    """Fail closed at every depth (as the Overview's): a field the publisher adds later, at the top of the file, in the
    catalog, or a value of a member that turns into an object, is not in the example."""
    docs, meta = watchlist_files(), overview_files()['overview-meta']
    s, members = docs['watchlist-stocks'], lq45(meta)
    i = s['ticker'].index(members[0])
    planted = 'PLANTED-' + '7' * 12
    s['secret_history'] = [[planted] * 300] * len(s['ticker'])
    s['catalog'][0]['formula'] = planted
    s['radar'] = {members[0]: [planted]}
    s['last'][i] = {'v': planted}                                # a kept column whose value turns into an object: null
    s['trend'][i] = [{'c': planted}]
    s['values']['rsi'][i] = {'deep': planted}
    s['values']['r5d'] = [planted] * len(s['ticker'])           # an indicator not shown at opening
    s['values']['new_flow'] = [planted] * len(s['ticker'])      # a new indicator of the publisher
    s['events'][members[0]] = [['DIVIDEND', '2026-11-30', planted]]
    s['prices_through'] = WATCHLIST_AS_OF
    PagesApi.watchlist = {n: gz(doc) for n, doc in docs.items()}
    with TestClient(create_app(guests, store, FakeOrc())) as c:
        _, files = watchlist_example(c, VISITOR)
    shown = files['watchlist-stocks']
    assert planted not in json.dumps(files)
    assert 'secret_history' not in shown and 'radar' not in shown and 'formula' not in shown['catalog'][0]
    assert shown['last'][0] is None and shown['trend'][0] is None and shown['values']['rsi'][0] is None
    assert shown['values']['new_flow'] == [None] * len(members) and shown['events'] == {}


def test_every_field_the_watchlist_publisher_writes_is_kept_by_name_or_left_out_by_name():
    """Every path the publisher's own watchlist.build writes (through example_docs.watchlist_files) is in the example
    as written, for the list's stocks, or is left out by WATCHLIST_LEFT_OUT or by the rule on an indicator that is not a
    default one; every name there is one the publisher writes. A new field of the publisher fails here until the cut
    decides on it."""
    live, meta = watchlist_files()['watchlist-stocks'], overview_files()['overview-meta']
    (_, s, _), (_, lists, _) = examples_module.watchlist_view(live, meta)
    members, at = lq45(meta), {t: i for i, t in enumerate(live['ticker'])}
    left = (*examples_module.WATCHLIST_LEFT_OUT, *(f'values.{k}' for k in live['values'] if k not in live['default']))
    under = lambda p, names: any(p == n or p.startswith(n + '.') for n in names)
    written, shown = leaf_paths(live), leaf_paths(s)
    assert {p for p in written - shown if not under(p, left)} == set()
    assert shown <= written | set(examples_module.WATCHLIST_LEFT_OUT)
    for n in examples_module.WATCHLIST_LEFT_OUT:
        assert any(under(p, (n,)) for p in written), f'{n}: not a field the publisher writes'
        assert s[n] in ({}, None), n
    per_stock = {*examples_module.WATCHLIST_COLUMNS, *(f'values.{k}' for k in live['default'])}
    wv, sv = leaf_values(live), leaf_values(s)
    for p, v in sv.items():
        if under(p, left):
            assert v in ({}, None) or v == [None] * len(members), p
        elif p in per_stock:
            assert v == [wv[p][at[t]] for t in members] and any(x is not None for x in v), p
        else:
            assert v == wv[p], p
    assert per_stock <= set(sv)
    assert [t['ticker'] for t in lists['lists'][0]['tickers']] == members


@pytest.mark.parametrize('change, reason', [
    ('no_list', 'list_missing'), ('two_lists', 'list_twice'), ('no_members', 'list_members_invalid'),
    ('outside', 'member_outside_file'), ('no_date', 'stocks_unreadable')])
def test_the_watchlist_example_never_shows_another_list(guests, store, watchlist_api, change, reason, caplog):
    """The example names its list (LQ45 as the Overview publishes it): without it, with it twice, without members, with
    a member the file does not hold, or a file without its price date, it answers EXAMPLE_UNAVAILABLE and logs why
    (a fixed word, no data), rather than a list of other stocks (the lesson of the 30 October list, ERRORS M527)."""
    docs = overview_files()
    meta, s = docs['overview-meta'], watchlist_files()
    stocks = s['watchlist-stocks']
    lq = next(x for x in meta['lists'] if x['code'] == 'LQ45')
    if change == 'no_list':
        meta['lists'] = [x for x in meta['lists'] if x is not lq]
    elif change == 'two_lists':
        meta['lists'].append(dict(lq, key='lq45-2'))
    elif change == 'no_members':
        lq['members'] = []
    elif change == 'outside':
        lq['members'] = [*lq['members'], 'ZZZZ']
    else:
        stocks['prices_through'] = None
    OverviewApi.files = {n: gz(doc) for n, doc in docs.items()}
    PagesApi.watchlist = {n: gz(doc) for n, doc in s.items()}
    with TestClient(create_app(guests, store, FakeOrc())) as c, caplog.at_level('WARNING', logger='edge_bff.examples'):
        r = c.get('/api/v1/examples/watchlist/index', headers=VISITOR)
    assert (r.status_code, r.json()['error']['code']) == (503, 'EXAMPLE_UNAVAILABLE'), r.text
    logged = [json.loads(m) for m in caplog.messages if 'example_unavailable' in m]
    assert logged and logged[-1]['tab'] == 'watchlist' and logged[-1]['reason'] == reason, logged


def test_the_watchlist_example_waits_for_its_files_and_follows_a_new_publication(guests, store, watchlist_api, monkeypatch):
    from app import pages as pages_module
    monkeypatch.setattr(pages_module, 'INDEX_SECONDS', 0)                 # the relays read their index on every call
    saved = dict(PagesApi.watchlist)
    PagesApi.watchlist = {'watchlist-radar': saved['watchlist-radar']}        # no watchlist-stocks published yet
    with TestClient(create_app(guests, store, FakeOrc())) as c:
        r = c.get('/api/v1/examples/watchlist/index', headers=VISITOR)
        assert (r.status_code, r.json()['error']['code']) == (404, 'EXAMPLE_NOT_READY')
        PagesApi.watchlist = saved
        make_user(store, 'freda', 'freda-password')
        h = sign_in(c, 'freda', 'freda-password')
        index, _ = watchlist_example(c, h)                                     # the free plan's too
        assert index['as_of'] == WATCHLIST_AS_OF
        # the next publications, in the same process: a later price date and a changed list, both followed
        docs, s = overview_files(), watchlist_files()
        s['watchlist-stocks']['prices_through'] = '2026-11-23'
        lq = next(x for x in docs['overview-meta']['lists'] if x['code'] == 'LQ45')
        lq['members'] = sorted([*lq['members'][1:], s['watchlist-stocks']['ticker'][-1]])
        OverviewApi.files = {n: gz(doc) for n, doc in docs.items()}
        PagesApi.watchlist = {n: gz(doc) for n, doc in s.items()}
        index, files = watchlist_example(c, h)
        assert index['as_of'] == '2026-11-23' and files['watchlist-stocks']['ticker'] == lq['members']
        c.post('/api/v1/auth/sign-out', headers=h)
        paid = make_user(store, 'pablo', 'pablo-password')
        subscribe(store, paid['user_id'], 'paid')
        c.cookies.clear()
        r = c.get('/api/v1/examples/watchlist/index', headers=sign_in(c, 'pablo', 'pablo-password'))
        assert r.status_code == 403 and r.json()['error']['details']['capability'] == 'watchlist.example'


# ---- the Screener: the stored catalog is the live site's for the released items (3e; ERRORS M527) -------------------
def test_the_screener_examples_catalog_is_what_catalog_for_gives_the_released_items(settings, store):
    """terminal-publisher examples.py narrowest_catalog (its copy of the catalog's item lists and the preset rules) gives
    the catalog edge-bff's own catalog_for gives a principal holding the released items and no right (p None: no lab
    item), on the made-up worker catalog; and catalog_for changes nothing more on what the example stores. Red when
    either side's rules move without the other."""
    import json as _json
    from app import screener as sc
    import example_docs
    releases = _json.loads((Path(__file__).resolve().parents[1] / 'catalog' / 'releases.json').read_text())
    raw = example_docs.screener_made_up()['catalog']
    allow = example_docs.examples.released_allow(releases)
    screeners = sc.Screeners(settings, store, worker=object())

    def as_edge_bff_shows(doc):
        b = _json.dumps(doc, separators=(',', ':')).encode()
        d = sc.Doc(key='catalog', raw=b, gz=gzip.compress(b), etag='"' + hashlib.sha256(b).hexdigest() + '"', price_data='p')
        return _json.loads(screeners.catalog_for(d, (), allow, None).raw)
    narrowed = example_docs.examples.narrowest_catalog(raw, releases)
    assert as_edge_bff_shows(raw) == narrowed
    assert as_edge_bff_shows(narrowed) == narrowed
    assert len(narrowed['presets']) < len(raw['presets']) or any(e.get('access') == 'admin' for e in raw.get('metrics', []))
    assert example_docs.examples.SCREENER_PRESET in {p['id'] for p in narrowed['presets']}


def test_the_backtest_examples_catalog_shows_what_catalog_for_gives_the_narrowest_principal():
    """The example-mode checker (ERRORS M527): terminal-publisher examples.py released_entries (its copy of
    catalog.tab_list for no principal) gives the Flow indicators edge-bff's rights.catalog_for gives a principal with no
    right and no lab item, on the made-up worker catalog with an admin-only version and an unlisted (lab) id planted; and
    catalog_for changes nothing on the catalog the example stores. Red when either side's rule moves without the other."""
    import example_docs
    from app import rights
    releases = json.loads((example_docs.ROOT / 'catalog' / 'releases.json').read_text())
    raw = example_docs.backtest_made_up()['raw']
    first = raw['flow_indicators'][0]
    planted = {**raw, 'flow_indicators': [*raw['flow_indicators'], {**first, 'id': 'FL_LAB_NOT_LISTED'},
                                           {**first, 'id': first['id'] + '_PIT', 'access': 'admin'}, {'note': 'no id'}]}
    shown = example_docs.examples.released_entries(planted['flow_indicators'], 'flow_indicator', releases)
    assert rights.catalog_for(planted, (), None)['flow_indicators'] == shown
    assert {'FL_LAB_NOT_LISTED', first['id'] + '_PIT'}.isdisjoint(e.get('id') for e in shown) and {'note': 'no id'} in shown
    stored = example_docs.backtest_example()['backtest-catalog']
    assert rights.catalog_for(stored, (), None) == stored and stored['flow_indicators']
