"""EXEC-IND-PRESETS (user 2026-11-06: "men-save indikator beserta dengan filternya"; "Q1 A", "Q2 A"): the Terminal's
indicator presets, /api/v1/terminal/presets, edge_bff.indicator_presets (migration 20261106_002)."""
import importlib.util
import os
from pathlib import Path
import secrets
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import presets as P
from app.main import create_app
from conftest import FakeOrc

ORIGIN = {'Origin': 'http://testserver'}
MIGRATION = Path(__file__).resolve().parents[3] / 'database/migrations/20261106_002_edge_bff_indicator_presets.sql'
DROP = 'DROP TABLE IF EXISTS edge_bff.indicator_presets'
A, B = 'ipr_' + 'a' * 32, 'ipr_' + 'b' * 32
CONFIG = {'params': {'scope': 'topn', 'top': 3, 'boards': ['Regular']}, 'style': {'color': '#12a594'}, 'on': True}


@pytest.fixture
def app(settings, store):
    with TestClient(create_app(settings, store, FakeOrc())) as c:
        r = c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'owner', 'password': 'local-test-password'})
        assert r.status_code == 200, r.text
        c.h = {**ORIGIN, 'X-CSRF-Token': r.json()['csrf_token']}
        yield c


def put(c, pid, **body):
    return c.put(f'/api/v1/terminal/presets/{pid}', headers=c.h, json={'name': 'Share Top 3', 'def_id': 'FL03', 'config': CONFIG, **body})


def test_a_preset_is_created_replaced_listed_and_deleted(app):
    r = put(app, A, summary='Top 3 net buyers · Regular')
    assert r.status_code == 201 and r.json()['revision'] == 1 and r.json()['config'] == CONFIG and r.json()['def_id'] == 'FL03'
    r = put(app, A, name='Share Top 5', config={**CONFIG, 'params': {'top': 5}}, revision=1)
    assert r.status_code == 200 and r.json()['revision'] == 2 and r.json()['config']['params'] == {'top': 5}
    listed = app.get('/api/v1/terminal/presets').json()
    assert [x['preset_id'] for x in listed['presets']] == [A] and listed['presets'][0]['config']['params'] == {'top': 5} and listed['limit'] == 100
    assert app.delete(f'/api/v1/terminal/presets/{A}', headers=app.h).status_code == 204
    assert app.get('/api/v1/terminal/presets').json()['presets'] == []
    assert app.delete(f'/api/v1/terminal/presets/{A}', headers=app.h).status_code == 404


def test_conflicts_names_and_order(app):
    put(app, A)
    assert put(app, A).json()['error']['code'] == 'REVISION_CONFLICT'
    put(app, A, revision=1)
    r = put(app, A, revision=1)
    assert r.status_code == 409 and r.json()['error']['details'] == {'revision': 2}
    r = put(app, B, name='Share Top 3')
    assert r.status_code == 409 and r.json()['error']['code'] == 'NAME_TAKEN'
    put(app, B, name='Other')
    assert [x['preset_id'] for x in app.get('/api/v1/terminal/presets').json()['presets']] == [B, A]
    r = app.patch(f'/api/v1/terminal/presets/{A}', headers=app.h, json={'favorite': True})
    assert r.status_code == 200 and r.json()['favorite'] is True and r.json()['revision'] == 2
    assert [x['preset_id'] for x in app.get('/api/v1/terminal/presets').json()['presets']] == [A, B]   # favourites first
    assert app.patch(f'/api/v1/terminal/presets/{B}', headers=app.h, json={'used': True}).status_code == 200
    assert app.patch(f'/api/v1/terminal/presets/{B}', headers=app.h, json={}).status_code == 422


@pytest.mark.parametrize('body, field', [
    ({'name': ''}, 'name'), ({'def_id': 'FL-03'}, 'def_id'), ({'def_id': 3}, 'def_id'), ({'config': []}, 'config'),
    ({'config': {'params': {}, 'other': 1}}, 'config'), ({'config': {'style': {}}}, 'config'), ({'config': {'params': {}, 'on': 'yes'}}, 'config'),
    ({'config': {'params': {'x': 'a\x00'}}}, 'config'), ({'summary': 'x' * 301}, 'summary'), ({'revision': 0}, 'revision'), ({'extra': 1}, 'extra')])
def test_a_body_is_refused_by_field(app, body, field):
    r = put(app, A, **body)
    assert r.status_code == 422 and r.json()['error']['field'] == field, r.text


def test_size_count_and_depth_limits(app, monkeypatch):
    r = put(app, A, config={'params': {'x': 'y' * 17000}})
    assert r.status_code == 422 and r.json()['error']['details']['limit'] == 'preset_bytes'
    deep = {'params': {}}; node = deep['params']
    for _ in range(10):
        node['n'] = {}; node = node['n']
    assert put(app, A, config=deep).json()['error']['field'] == 'config'
    monkeypatch.setattr(P, 'PRESET_LIMIT', 1)
    put(app, A)
    r = put(app, B, name='Two')
    assert r.status_code == 422 and r.json()['error']['details'] == {'limit': 'presets', 'allowed': 1, 'needed': 2}


def test_session_csrf_and_owner(app):
    assert app.put(f'/api/v1/terminal/presets/{A}', headers=ORIGIN, json={}).status_code == 403
    put(app, A)
    with app.app.state.store.connect() as c:
        c.execute("UPDATE edge_bff.indicator_presets SET owner_key='someone-else'")
    assert app.get('/api/v1/terminal/presets').json()['presets'] == []
    assert put(app, A).json()['error']['code'] == 'REVISION_CONFLICT'
    assert app.delete(f'/api/v1/terminal/presets/{A}', headers=app.h).status_code == 404
    app.cookies.clear()
    assert app.get('/api/v1/terminal/presets').status_code == 401


def test_a_missing_table_is_503_with_retry_after(app):
    with app.app.state.store.connect() as c:
        c.execute('ALTER TABLE edge_bff.indicator_presets RENAME TO indicator_presets_off')
    try:
        r = app.get('/api/v1/terminal/presets')
        assert r.status_code == 503 and r.json()['error']['code'] == 'PRESETS_NOT_READY' and r.headers['retry-after'] == '30'
    finally:
        with app.app.state.store.connect() as c:
            c.execute('ALTER TABLE edge_bff.indicator_presets_off RENAME TO indicator_presets')


# ---- migration and provisioning ---------------------------------------------------------------------------------------

def test_the_migration_refuses_extra_runtime_or_public_grants(database):
    revoke = 'REVOKE ALL ON edge_bff.indicator_presets FROM PUBLIC;\n'
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
                assert conn.execute("SELECT to_regclass('edge_bff.indicator_presets')").fetchone()[0] is None
                conn.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA edge_bff REVOKE {privilege} ON TABLES FROM {grantee}')
        finally:
            conn.execute('ROLLBACK')
            for grantee, privilege in [('edge_bff_runtime', 'TRUNCATE'), ('edge_bff_runtime', 'TRIGGER'), ('PUBLIC', 'SELECT'), ('PUBLIC', 'DELETE')]:
                conn.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA edge_bff REVOKE {privilege} ON TABLES FROM {grantee}')
            conn.execute(DROP)
            conn.execute(MIGRATION.read_text())


def test_the_table_holds_its_rules(database):
    good = {'preset_id': 'ipr_' + '1' * 32, 'owner_key': 'o', 'name': 'n', 'def_id': 'FL03', 'config': '{}', 'summary': '', 'schema_version': 1}
    def insert(conn, **change):
        row = {**good, **change}
        conn.execute(f"INSERT INTO edge_bff.indicator_presets({','.join(row)}) VALUES ({','.join(['%s'] * len(row))})", list(row.values()))
    with psycopg.connect(database) as conn:
        insert(conn)
        for change in ({'preset_id': 'ipr_1'}, {'name': ' n'}, {'def_id': 'FL-3'}, {'config': '[]'},
                       {'config': '{"x": "' + 'y' * 16400 + '"}'}, {'summary': 's' * 301}, {'schema_version': 0}):
            with pytest.raises(psycopg.errors.CheckViolation):
                insert(conn, **{'preset_id': 'ipr_' + '2' * 32, 'name': 'm', **change})
            conn.rollback()
            insert(conn)
        with pytest.raises(psycopg.errors.UniqueViolation):
            insert(conn, preset_id='ipr_' + '3' * 32)
        conn.rollback()
    with psycopg.connect(database, autocommit=True) as conn:
        with pytest.raises(psycopg.errors.RaiseException, match='indicator_presets exists'):
            conn.execute(MIGRATION.read_text())
        conn.execute('ROLLBACK')


def test_provisioned_login_reaches_the_presets_table_with_its_grants(database, monkeypatch):
    helper = Path(__file__).resolve().parents[3] / 'scripts/provision_edge_bff_login.py'
    spec = importlib.util.spec_from_file_location('edge_provision_presets', helper)
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
            conn.execute("INSERT INTO edge_bff.indicator_presets(preset_id,owner_key,name,def_id,config,schema_version) VALUES (%s,'o','n','FL03','{}',1)", (A,))
            conn.execute('UPDATE edge_bff.indicator_presets SET favorite=true')
            conn.execute('DELETE FROM edge_bff.indicator_presets')
            conn.rollback()
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute('TRUNCATE edge_bff.indicator_presets')
        with psycopg.connect(database, autocommit=True) as conn:
            conn.execute('GRANT TRUNCATE ON edge_bff.indicator_presets TO edge_bff_runtime')
        with pytest.raises(RuntimeError, match='Unexpected EDGE grants'):
            module.main()
        with psycopg.connect(database, autocommit=True) as conn:
            conn.execute('REVOKE TRUNCATE ON edge_bff.indicator_presets FROM edge_bff_runtime')
        module.main()
    finally:
        with psycopg.connect(database, autocommit=True) as conn:
            conn.execute('DROP OWNED BY edge_bff_login')
            conn.execute('DROP ROLE edge_bff_login')
