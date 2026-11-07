"""EXEC-DRAW-PANES (user 2026-11-07: "semua gambar harus di simpan di akun EDGE, sama seperti trading view"; "3 jalankan
dulu"): the Terminal's drawings, /api/v1/terminal/drawings, edge_bff.terminal_drawings (migration 20261107_001)."""
import importlib.util
import os
from pathlib import Path
import secrets
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import drawings as D
from app.main import create_app
from conftest import FakeOrc

ORIGIN = {'Origin': 'http://testserver'}
MIGRATION = Path(__file__).resolve().parents[3] / 'database/migrations/20261107_001_edge_bff_terminal_drawings.sql'
DROP = 'DROP TABLE IF EXISTS edge_bff.terminal_drawings'
PANE = 'pane_' + 'a' * 16
LINE = {'id': 'd1', 'kind': 'trend-line', 'points': [{'time': '2026-10-01', 'price': 58.6}, {'time': '2026-11-03', 'price': 61.2}],
        'style': {'color': '#171717', 'width': 2}}


@pytest.fixture
def app(settings, store):
    with TestClient(create_app(settings, store, FakeOrc())) as c:
        r = c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'owner', 'password': 'local-test-password'})
        assert r.status_code == 200, r.text
        c.h = {**ORIGIN, 'X-CSRF-Token': r.json()['csrf_token']}
        yield c


def put(c, ticker='BBRI', set_id='chart', **body):
    return c.put(f'/api/v1/terminal/drawings/{ticker}/{set_id}', headers=c.h, json={'drawings': [LINE], **body})


def test_sets_are_created_replaced_listed_per_ticker_and_deleted(app):
    r = put(app)
    assert r.status_code == 201 and r.json()['revision'] == 1 and r.json()['drawings'] == [LINE]
    assert put(app, set_id='flow').status_code == 201 and put(app, set_id=PANE).status_code == 201
    assert put(app, ticker='TLKM').status_code == 201
    r = put(app, drawings=[LINE, {**LINE, 'id': 'd2'}], revision=1)
    assert r.status_code == 200 and r.json()['revision'] == 2 and len(r.json()['drawings']) == 2
    listed = app.get('/api/v1/terminal/drawings', params={'ticker': 'BBRI'}).json()
    assert [s['set_id'] for s in listed['sets']] == ['chart', 'flow', PANE] and listed['limits'] == {'set_bytes': 100000, 'sets': 5000}
    assert [s['ticker'] for s in app.get('/api/v1/terminal/drawings', params={'ticker': 'TLKM'}).json()['sets']] == ['TLKM']
    assert app.delete(f'/api/v1/terminal/drawings/BBRI/{PANE}', headers=app.h).status_code == 204
    assert app.delete(f'/api/v1/terminal/drawings/BBRI/{PANE}', headers=app.h).status_code == 404
    assert [s['set_id'] for s in app.get('/api/v1/terminal/drawings', params={'ticker': 'BBRI'}).json()['sets']] == ['chart', 'flow']
    # an empty list is a set too (everything erased, the revision still counts)
    assert put(app, drawings=[], revision=2).json()['drawings'] == []


def test_revisions(app):
    put(app)
    r = put(app)
    assert r.status_code == 409 and r.json()['error']['code'] == 'REVISION_CONFLICT' and r.json()['error']['details'] == {'revision': 1}
    put(app, revision=1)
    r = put(app, revision=1)
    assert r.status_code == 409 and r.json()['error']['details'] == {'revision': 2}
    assert put(app, set_id='flow', revision=1).status_code == 404


@pytest.mark.parametrize('path, body, field', [
    ('bbri/chart', None, 'ticker'), ('BBRI-X/chart', None, 'ticker'), ('ABCDEFGHIJKLM/chart', None, 'ticker'),
    ('BBRI/price', None, 'set_id'), ('BBRI/pane_123', None, 'set_id'), ('BBRI/pane_' + 'A' * 16, None, 'set_id'),
    ('BBRI/chart', {'drawings': {}}, 'drawings'), ('BBRI/chart', {'drawings': [1]}, 'drawings'),
    ('BBRI/chart', {'drawings': [{'text': 'a\x00'}]}, 'drawings'), ('BBRI/chart', {'drawings': [], 'revision': 0}, 'revision'),
    ('BBRI/chart', {'drawings': [], 'extra': 1}, 'extra')])
def test_a_request_is_refused_by_field(app, path, body, field):
    r = app.put(f'/api/v1/terminal/drawings/{path}', headers=app.h, json=body or {'drawings': [LINE]})
    assert r.status_code == 422 and r.json()['error']['field'] == field, r.text


def test_size_depth_and_count_limits(app, monkeypatch):
    r = put(app, drawings=[{'id': 'b', 'kind': 'brush', 'points': [{'time': '2026-10-01', 'price': 1.123456789}] * 3000}])
    assert r.status_code == 422 and r.json()['error']['details']['limit'] == 'set_bytes'
    deep = {}; node = deep
    for _ in range(11):
        node['n'] = {}; node = node['n']
    assert put(app, drawings=[deep]).json()['error']['field'] == 'drawings'
    assert app.get('/api/v1/terminal/drawings', params={'ticker': 'bad!'}).json()['error']['field'] == 'ticker'
    monkeypatch.setattr(D, 'SET_LIMIT', 1)
    put(app)
    r = put(app, set_id='flow')
    assert r.status_code == 422 and r.json()['error']['details'] == {'limit': 'sets', 'allowed': 1, 'needed': 2}


def test_session_csrf_and_owner(app):
    assert app.put('/api/v1/terminal/drawings/BBRI/chart', headers=ORIGIN, json={'drawings': []}).status_code == 403
    put(app)
    with app.app.state.store.connect() as c:
        c.execute("UPDATE edge_bff.terminal_drawings SET owner_key='someone-else'")
    assert app.get('/api/v1/terminal/drawings', params={'ticker': 'BBRI'}).json()['sets'] == []
    assert put(app, revision=1).status_code == 404                       # another owner's set is not this owner's
    assert put(app).status_code == 201                                   # and this owner has its own
    assert app.delete('/api/v1/terminal/drawings/BBRI/flow', headers=app.h).status_code == 404
    app.cookies.clear()
    assert app.get('/api/v1/terminal/drawings', params={'ticker': 'BBRI'}).status_code == 401


def test_a_missing_table_is_503_with_retry_after(app):
    with app.app.state.store.connect() as c:
        c.execute('ALTER TABLE edge_bff.terminal_drawings RENAME TO terminal_drawings_off')
    try:
        r = app.get('/api/v1/terminal/drawings', params={'ticker': 'BBRI'})
        assert r.status_code == 503 and r.json()['error']['code'] == 'DRAWINGS_NOT_READY' and r.headers['retry-after'] == '30'
    finally:
        with app.app.state.store.connect() as c:
            c.execute('ALTER TABLE edge_bff.terminal_drawings_off RENAME TO terminal_drawings')


# ---- migration and provisioning ---------------------------------------------------------------------------------------

def test_the_migration_refuses_extra_runtime_or_public_grants(database):
    revoke = 'REVOKE ALL ON edge_bff.terminal_drawings FROM PUBLIC;\n'
    assert MIGRATION.read_text().count(revoke) == 1
    unguarded = MIGRATION.read_text().replace(revoke, '')
    with psycopg.connect(database, autocommit=True) as conn:
        conn.execute(DROP)
        try:
            for grantee, privilege, message in [('edge_bff_runtime', 'TRUNCATE', 'more than'), ('edge_bff_runtime', 'TRIGGER', 'more than'),
                                                ('PUBLIC', 'SELECT', 'PUBLIC can use'), ('PUBLIC', 'DELETE', 'PUBLIC can use')]:
                conn.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA edge_bff GRANT {privilege} ON TABLES TO {grantee}')
                with pytest.raises(psycopg.errors.RaiseException, match=message):
                    conn.execute(unguarded if grantee == 'PUBLIC' else MIGRATION.read_text())
                conn.execute('ROLLBACK')
                assert conn.execute("SELECT to_regclass('edge_bff.terminal_drawings')").fetchone()[0] is None
                conn.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA edge_bff REVOKE {privilege} ON TABLES FROM {grantee}')
        finally:
            conn.execute('ROLLBACK')
            for grantee, privilege in [('edge_bff_runtime', 'TRUNCATE'), ('edge_bff_runtime', 'TRIGGER'), ('PUBLIC', 'SELECT'), ('PUBLIC', 'DELETE')]:
                conn.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA edge_bff REVOKE {privilege} ON TABLES FROM {grantee}')
            conn.execute(DROP)
            conn.execute(MIGRATION.read_text())


def test_the_table_holds_its_rules(database):
    good = {'owner_key': 'o', 'ticker': 'BBRI', 'set_id': 'chart', 'drawings': '[]', 'schema_version': 1}
    def insert(conn, **change):
        row = {**good, **change}
        conn.execute(f"INSERT INTO edge_bff.terminal_drawings({','.join(row)}) VALUES ({','.join(['%s'] * len(row))})", list(row.values()))
    with psycopg.connect(database) as conn:
        insert(conn)
        for change in ({'ticker': 'bbri'}, {'set_id': 'pane_1'}, {'drawings': '{}'}, {'drawings': '["' + 'y' * 100001 + '"]'},
                       {'schema_version': 0}):
            with pytest.raises(psycopg.errors.CheckViolation):
                insert(conn, **{'set_id': 'flow', **change})
            conn.rollback()
            insert(conn)
        with pytest.raises(psycopg.errors.UniqueViolation):
            insert(conn)
        conn.rollback()
    with psycopg.connect(database, autocommit=True) as conn:
        with pytest.raises(psycopg.errors.RaiseException, match='terminal_drawings exists'):
            conn.execute(MIGRATION.read_text())
        conn.execute('ROLLBACK')


def test_provisioned_login_reaches_the_drawings_table_with_its_grants(database, monkeypatch):
    helper = Path(__file__).resolve().parents[3] / 'scripts/provision_edge_bff_login.py'
    spec = importlib.util.spec_from_file_location('edge_provision_drawings', helper)
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
            conn.execute("INSERT INTO edge_bff.terminal_drawings(owner_key,ticker,set_id,drawings,schema_version) VALUES ('o','BBRI','chart','[]',1)")
            conn.execute("UPDATE edge_bff.terminal_drawings SET drawings='[{}]'")
            conn.execute('DELETE FROM edge_bff.terminal_drawings')
            conn.rollback()
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute('TRUNCATE edge_bff.terminal_drawings')
        with psycopg.connect(database, autocommit=True) as conn:
            conn.execute('GRANT TRUNCATE ON edge_bff.terminal_drawings TO edge_bff_runtime')
        with pytest.raises(RuntimeError, match='Unexpected EDGE grants'):
            module.main()
        with psycopg.connect(database, autocommit=True) as conn:
            conn.execute('REVOKE TRUNCATE ON edge_bff.terminal_drawings FROM edge_bff_runtime')
        module.main()
    finally:
        with psycopg.connect(database, autocommit=True) as conn:
            conn.execute('DROP OWNED BY edge_bff_login')
            conn.execute('DROP ROLE edge_bff_login')
