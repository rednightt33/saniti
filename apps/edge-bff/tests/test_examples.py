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

from app import examples as examples_module
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


def test_the_example_needs_the_tabs_example_capability_for_a_visitor_and_an_account(guests, store, stored, plan_rows):
    with TestClient(create_app(guests, store, FakeOrc())) as c:
        free = make_user(store, 'freda', 'freda-password')                  # the default plan: free
        paid = make_user(store, 'pablo', 'pablo-password')
        subscribe(store, paid['user_id'], 'paid')
        make_user(store, 'ada', 'ada-password', role='admin')
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
    real = examples_module.Examples.read

    def counted(self, tab, held):
        reads.append(tab)
        return real(self, tab, held)
    monkeypatch.setattr(examples_module.Examples, 'read', counted)
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

        def broken(self, tab, held):
            raise psycopg.OperationalError('connection to server at "secret-host" failed')
        monkeypatch.setattr(examples_module.Examples, 'read', broken)
        read_example(c, VISITOR)                                              # the last good copy stands
    with TestClient(create_app(guests, store, FakeOrc())) as c:              # nothing kept and the read fails
        r = c.get('/api/v1/examples/radar/index', headers=VISITOR)
        assert r.status_code == 503 and r.json()['error']['code'] == 'EXAMPLE_UNAVAILABLE'
        assert 'secret-host' not in r.text


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
