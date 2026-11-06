"""EXEC-TERMINAL-LAYOUTS (user 2026-11-06: "di akun edge. Tidak usah mengganti saham."): the Terminal's saved chart
layouts, /api/v1/terminal/layouts, edge_bff.terminal_layouts (migration 20261106_001)."""
import pytest
from fastapi.testclient import TestClient

from app import layouts as L
from app.main import create_app
from conftest import FakeOrc

ORIGIN = {'Origin': 'http://testserver'}
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
    ({'summary': 'x' * 121}, 'summary'), ({'revision': 0}, 'revision'), ({'revision': True}, 'revision'), ({'extra': 1}, 'extra')])
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
