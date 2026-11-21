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


def test_a_body_read_from_the_table_that_does_not_match_its_sha_is_never_served(guests, store, stored, monkeypatch):
    """The example-mode checker (ERRORS M527): Stored.read checks every body it reads against its row's sha256 and size
    (the table's CHECKs make a mismatch impossible to write; this is the second line). A body that comes back other
    than its sha is refused: nothing is served from it, and nothing kept stands in on the first read."""
    monkeypatch.setattr(examples_module, 'BODIES_SQL', examples_module.BODIES_SQL.replace(
        'SELECT name, sha256, body', "SELECT name, sha256, body || '\\x00'::bytea AS body"))
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
        # the series: breadth's 120 sessions and their start, the KPI strip's 30 broker sessions, as published
        n = examples_module.OVERVIEW_SESSIONS
        assert series['dates'] == OVERVIEW_DATES[-n:] and len(OVERVIEW_DATES) > n
        for k in ('index', 'sector'):
            assert {t: v for t, v in series[k].items()} == {t: v[-n:] for t, v in live['overview-series'][k].items()}
        for k in ('above_ema50', 'above_ema200', 'breadth_n'):
            assert series[k] == live['overview-series'][k][-n:]
        m = examples_module.OVERVIEW_FLOW_SESSIONS
        assert series['flow'] == {k: v[-m:] for k, v in live['overview-series']['flow'].items()}
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


def test_a_principals_own_terminal_refusal_on_the_overview_example_keeps_its_code(guests, store, overview_api, monkeypatch):
    """The example-mode checker (ERRORS M527): the Overview example builds the principal's terminal-api headers first
    (terminal_access.headers: a guest without a well-formed visitor key, a ticker list too long for the header, a limit
    of 0 where the database allows one); such a refusal of the principal itself is answered with its own status, code
    and way on, as the Terminal's relay answers it (app/pages.py), not as the example's outage EXAMPLE_UNAVAILABLE."""
    from app.errors import Refusal
    own = Refusal(403, 'CAPABILITY_REQUIRED', {'capability': 'terminal.files_per_hour'})

    def refused(settings, p):
        raise own
    with TestClient(create_app(guests, store, FakeOrc())) as c:
        index, _ = overview_example(c, VISITOR)                 # the example opens; then the principal is refused
        monkeypatch.setattr(examples_module.terminal_access, 'headers', refused)
        for path in ('/api/v1/examples/overview/index', '/api/v1/examples/overview/file/overview-meta'):
            r = c.get(path, headers=VISITOR)
            assert r.status_code == 403, (path, r.text)
            error = r.json()['error']
            assert (error['code'], error['details'].get('capability')) == ('CAPABILITY_REQUIRED', 'terminal.files_per_hour'), error


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
