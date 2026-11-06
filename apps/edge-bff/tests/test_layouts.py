"""EXEC-TERMINAL-LAYOUTS (user 2026-11-06: "di akun edge. Tidak usah mengganti saham."): the Terminal's saved chart
layouts, /api/v1/terminal/layouts, edge_bff.terminal_layouts (migration 20261106_001)."""
import importlib.util
import os
from pathlib import Path
import secrets
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import layouts as L
from app.main import create_app
from conftest import FakeOrc

ORIGIN = {'Origin': 'http://testserver'}
MIGRATION = Path(__file__).resolve().parents[3] / 'database/migrations/20261106_001_edge_bff_terminal_layouts.sql'
DROP = 'DROP TABLE IF EXISTS edge_bff.terminal_layouts'
A, B = 'lay_' + 'a' * 32, 'lay_' + 'b' * 32
STATE = {'ml.ind.v1': '[{"def":"RSI","params":{"len":14},"on":true}]', 'ml.tf': 'D', 'ml.vol.on': '1'}


@pytest.fixture
def app(settings, store):
    with TestClient(create_app(settings, store, FakeOrc())) as c:
        r = c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'owner', 'password': 'local-test-password'})
        assert r.status_code == 200, r.text
        c.h = {**ORIGIN, 'X-CSRF-Token': r.json()['csrf_token']}
        yield c


def put(c, lid, **body):
    return c.put(f'/api/v1/terminal/layouts/{lid}', headers=c.h, json={'name': 'Swing', 'state': STATE, **body})


def test_a_layout_is_created_read_replaced_listed_and_deleted(app):
    r = put(app, A, summary='D · 1 indicator')
    assert r.status_code == 201 and r.json()['revision'] == 1 and r.json()['state'] == STATE
    assert app.get(f'/api/v1/terminal/layouts/{A}').json()['state'] == STATE
    r = put(app, A, name='Swing 2', state={**STATE, 'ml.tf': 'W'}, revision=1)
    assert r.status_code == 200 and r.json()['revision'] == 2 and r.json()['name'] == 'Swing 2'
    listed = app.get('/api/v1/terminal/layouts').json()
    assert [x['layout_id'] for x in listed['layouts']] == [A] and 'state' not in listed['layouts'][0] and listed['limit'] == 50
    assert app.delete(f'/api/v1/terminal/layouts/{A}', headers=app.h).status_code == 204
    assert app.get(f'/api/v1/terminal/layouts/{A}').status_code == 404


def test_a_stale_revision_and_a_second_create_are_conflicts(app):
    put(app, A)
    assert put(app, A).json()['error']['code'] == 'REVISION_CONFLICT'                 # create over an existing id
    put(app, A, revision=1)
    r = put(app, A, revision=1)                                                       # another tab saved revision 2
    assert r.status_code == 409 and r.json()['error']['details'] == {'revision': 2}


def test_names_are_unique_per_owner_and_trimmed(app):
    assert put(app, A, name='  Swing   trade ').json()['name'] == 'Swing trade'
    r = put(app, B, name='Swing trade')
    assert r.status_code == 409 and r.json()['error']['code'] == 'NAME_TAKEN'


def test_favorite_and_opened_change_without_a_revision_and_order_the_list(app):
    put(app, A); put(app, B, name='Other')
    assert [x['layout_id'] for x in app.get('/api/v1/terminal/layouts').json()['layouts']] == [B, A]
    r = app.patch(f'/api/v1/terminal/layouts/{A}', headers=app.h, json={'favorite': True, 'opened': True})
    assert r.status_code == 200 and r.json()['favorite'] is True and r.json()['revision'] == 1
    assert [x['layout_id'] for x in app.get('/api/v1/terminal/layouts').json()['layouts']] == [A, B]
    assert app.patch(f'/api/v1/terminal/layouts/{A}', headers=app.h, json={}).status_code == 422
    assert app.patch(f'/api/v1/terminal/layouts/{B[:-1]}c', headers=app.h, json={'opened': True}).status_code == 404


@pytest.mark.parametrize('body, field', [
    ({'name': ''}, 'name'), ({'name': 'x' * 121}, 'name'), ({'state': []}, 'state'), ({'state': {'other': '1'}}, 'state'),
    ({'state': {'ml.tf': 5}}, 'state'), ({'state': {f'ml.k{i}': '1' for i in range(65)}}, 'state'),
    ({'summary': 'x' * 121}, 'summary'), ({'revision': 0}, 'revision'), ({'revision': True}, 'revision'), ({'extra': 1}, 'extra'),
    # QA round 3 (L1): text PostgreSQL cannot store is a 422 by field, not a 503
    ({'name': 'a\x00b'}, 'name'), ({'summary': 'a\x00'}, 'summary'), ({'state': {'ml.tf': 'D\x00'}}, 'state')])
def test_a_body_is_refused_by_field(app, body, field):
    r = put(app, A, **body)
    assert r.status_code == 422 and r.json()['error']['field'] == field, r.text


def test_size_and_count_limits(app, monkeypatch):
    r = put(app, A, state={'ml.ind.v1': 'x' * 70000})
    assert r.status_code == 422 and r.json()['error']['details']['limit'] == 'layout_bytes'
    monkeypatch.setattr(L, 'LAYOUT_LIMIT', 1)
    put(app, A)
    r = put(app, B, name='Two')
    assert r.status_code == 422 and r.json()['error']['details'] == {'limit': 'layouts', 'allowed': 1, 'needed': 2}


def test_session_and_csrf_are_required(app):
    assert app.put(f'/api/v1/terminal/layouts/{A}', headers=ORIGIN, json={'name': 'x', 'state': {}}).status_code == 403
    assert app.delete(f'/api/v1/terminal/layouts/{A}', headers=ORIGIN).status_code == 403
    app.cookies.clear()
    assert app.get('/api/v1/terminal/layouts').status_code == 401
    assert app.get('/api/v1/terminal/layouts/bad').status_code == 401


def test_a_bad_id_is_refused_and_rows_are_the_owners_own(app):
    assert put(app, 'lay_XYZ').status_code == 422
    put(app, A)
    with app.app.state.store.connect() as c:
        c.execute("UPDATE edge_bff.terminal_layouts SET owner_key='someone-else'")
    assert app.get(f'/api/v1/terminal/layouts/{A}').status_code == 404
    assert app.get('/api/v1/terminal/layouts').json()['layouts'] == []
    assert put(app, A).json()['error']['code'] == 'REVISION_CONFLICT'                 # the id is another owner's
    assert app.delete(f'/api/v1/terminal/layouts/{A}', headers=app.h).status_code == 404


def test_a_missing_table_is_503_with_retry_after(app):
    with app.app.state.store.connect() as c:
        c.execute('ALTER TABLE edge_bff.terminal_layouts RENAME TO terminal_layouts_off')
    try:
        r = app.get('/api/v1/terminal/layouts')
        assert r.status_code == 503 and r.json()['error']['code'] == 'LAYOUTS_NOT_READY' and r.headers['retry-after'] == '30'
    finally:
        with app.app.state.store.connect() as c:
            c.execute('ALTER TABLE edge_bff.terminal_layouts_off RENAME TO terminal_layouts')


def test_an_unpaired_surrogate_or_a_deep_body_is_refused_with_422(app):
    for raw in ('{"name": "a\\ud800", "state": {}}', '{"name": "n", "state": {"ml.tf": "\\udfff"}}', '[' * 60000 + ']' * 60000):
        r = app.put(f'/api/v1/terminal/layouts/{A}', headers={**app.h, 'content-type': 'application/json'}, content=raw)
        assert r.status_code == 422 and r.json()['error']['code'] == 'INVALID_INPUT', (raw[:30], r.text)


# ---- migration and provisioning (the screener precedent, tests/test_screener.py) ----------------------------------

def test_the_migration_refuses_a_runtime_role_with_more_than_the_code_does(database):
    """The verify block holds edge_bff_runtime to SELECT, INSERT, UPDATE and DELETE: TRUNCATE, REFERENCES or TRIGGER given
    through the schema's default privileges fails the migration, which then leaves no table."""
    with psycopg.connect(database, autocommit=True) as conn:
        conn.execute(DROP)
        try:
            for extra in ('TRUNCATE', 'REFERENCES', 'TRIGGER'):
                conn.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA edge_bff GRANT {extra} ON TABLES TO edge_bff_runtime')
                with pytest.raises(psycopg.errors.RaiseException, match='more than edge_bff.terminal_layouts needs'):
                    conn.execute(MIGRATION.read_text())
                conn.execute('ROLLBACK')
                assert conn.execute("SELECT to_regclass('edge_bff.terminal_layouts')").fetchone()[0] is None, extra
                conn.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA edge_bff REVOKE {extra} ON TABLES FROM edge_bff_runtime')
        finally:
            conn.execute('ROLLBACK')
            for extra in ('TRUNCATE', 'REFERENCES', 'TRIGGER'):
                conn.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA edge_bff REVOKE {extra} ON TABLES FROM edge_bff_runtime')
            conn.execute(DROP)
            conn.execute(MIGRATION.read_text())


def test_the_migration_refuses_public_with_any_privilege(database):
    """Without its REVOKE and with PUBLIC given one privilege at a time through default privileges, every privilege is
    refused (by the runtime check where the runtime role would then hold more than its grants)."""
    revoke = 'REVOKE ALL ON edge_bff.terminal_layouts FROM PUBLIC;\n'
    assert MIGRATION.read_text().count(revoke) == 1
    unguarded = MIGRATION.read_text().replace(revoke, '')
    privileges = ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER')
    with psycopg.connect(database, autocommit=True) as conn:
        conn.execute(DROP)
        try:
            for privilege in privileges:
                conn.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA edge_bff GRANT {privilege} ON TABLES TO PUBLIC')
                message = 'PUBLIC can use edge_bff.terminal_layouts' if privilege in ('SELECT', 'INSERT', 'UPDATE', 'DELETE') \
                    else 'more than edge_bff.terminal_layouts needs'
                with pytest.raises(psycopg.errors.RaiseException, match=message):
                    conn.execute(unguarded)
                conn.execute('ROLLBACK')
                assert conn.execute("SELECT to_regclass('edge_bff.terminal_layouts')").fetchone()[0] is None, privilege
                conn.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA edge_bff REVOKE {privilege} ON TABLES FROM PUBLIC')
        finally:
            conn.execute('ROLLBACK')
            for privilege in privileges:
                conn.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA edge_bff REVOKE {privilege} ON TABLES FROM PUBLIC')
            conn.execute(DROP)
            conn.execute(MIGRATION.read_text())


def test_the_table_holds_its_rules(database):
    """The migration's checks as the database applies them: ids, trimmed names of 1-120 characters, a JSON object of at
    most 65,536 bytes, a summary of at most 120 characters, a positive revision and schema version, one name per owner;
    a second run of the file is refused."""
    good = {'layout_id': 'lay_' + '1' * 32, 'owner_key': 'o', 'name': 'n', 'state': '{}', 'summary': '', 'schema_version': 1, 'revision': 1}
    def insert(conn, **change):
        row = {**good, **change}
        conn.execute(f"INSERT INTO edge_bff.terminal_layouts({','.join(row)}) VALUES ({','.join(['%s'] * len(row))})", list(row.values()))
    with psycopg.connect(database) as conn:
        insert(conn)
        for change in ({'layout_id': 'lay_1'}, {'name': ''}, {'name': ' n'}, {'name': 'x' * 121}, {'state': '[]'},
                       {'state': '{"ml.ind.v1": "' + 'y' * 65530 + '"}'}, {'summary': 's' * 121}, {'schema_version': 0},
                       {'revision': 0}):
            with pytest.raises(psycopg.errors.CheckViolation):
                insert(conn, **{'layout_id': 'lay_' + '2' * 32, 'name': 'm', **change})
            conn.rollback()
            insert(conn)
        with pytest.raises(psycopg.errors.UniqueViolation):
            insert(conn, layout_id='lay_' + '3' * 32)
        conn.rollback()
    with psycopg.connect(database, autocommit=True) as conn:
        with pytest.raises(psycopg.errors.RaiseException, match='terminal_layouts exists'):
            conn.execute(MIGRATION.read_text())
        conn.execute('ROLLBACK')


def test_provisioned_login_reaches_the_layouts_table_with_its_grants(database, monkeypatch):
    """scripts/provision_edge_bff_login.py: the login lists, creates, replaces, marks and deletes layouts, and nothing
    more; an extra grant, or PUBLIC holding any privilege on an EDGE table, is refused."""
    helper = Path(__file__).resolve().parents[3] / 'scripts/provision_edge_bff_login.py'
    spec = importlib.util.spec_from_file_location('edge_provision_layouts', helper)
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
            conn.execute("INSERT INTO edge_bff.terminal_layouts(layout_id,owner_key,name,state,schema_version) VALUES (%s,'o','n','{}',1)", (A,))
            conn.execute('UPDATE edge_bff.terminal_layouts SET revision=2, favorite=true')
            conn.execute('DELETE FROM edge_bff.terminal_layouts')
            conn.rollback()
            for sql in ('TRUNCATE edge_bff.terminal_layouts', 'SELECT * FROM public.market_private'):
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    conn.execute(sql)
                conn.rollback()
        for extra in ('TRUNCATE', 'REFERENCES', 'TRIGGER'):
            with psycopg.connect(database, autocommit=True) as conn:
                conn.execute(f'GRANT {extra} ON edge_bff.terminal_layouts TO edge_bff_runtime')
            with pytest.raises(RuntimeError, match='Unexpected EDGE grants'):
                module.main()
            with psycopg.connect(database, autocommit=True) as conn:
                conn.execute(f'REVOKE {extra} ON edge_bff.terminal_layouts FROM edge_bff_runtime')
        with psycopg.connect(database, autocommit=True) as conn:
            conn.execute('GRANT SELECT ON edge_bff.terminal_layouts TO PUBLIC')
        with pytest.raises(RuntimeError, match='PUBLIC can use an EDGE table'):
            module.main()
        with psycopg.connect(database, autocommit=True) as conn:
            conn.execute('REVOKE ALL ON edge_bff.terminal_layouts FROM PUBLIC')
        module.main()
    finally:
        with psycopg.connect(database, autocommit=True) as conn:
            conn.execute('REVOKE ALL ON edge_bff.terminal_layouts FROM PUBLIC')
            conn.execute('DROP OWNED BY edge_bff_login')
            conn.execute('DROP ROLE edge_bff_login')
