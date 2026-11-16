"""EXEC-WATCHLIST L3: the Watchlist's lists (app/watchlist.py, migration 20261116_001 applied by conftest) and the star of
the Screener on the first list (decision 2A). Needs EDGE_TEST_POSTGRES_URL (a disposable Postgres), as the others."""
import psycopg
import pytest
from fastapi.testclient import TestClient

from app import main, watchlist as W

ORIGIN = {'Origin': 'http://testserver'}
LISTS = '/api/v1/watchlist/lists'


@pytest.fixture
def app(settings, store):
    from conftest import FakeOrc
    with TestClient(main.create_app(settings, store, FakeOrc())) as c:
        r = c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'owner', 'password': 'local-test-password'})
        assert r.status_code == 200, r.text
        c.h = {**ORIGIN, 'X-CSRF-Token': r.json()['csrf_token']}
        yield c


def db(c, sql, *args):
    with c.app.state.store.connect() as conn:
        cur = conn.execute(sql, args)
        return cur.fetchall() if cur.description else cur.rowcount


def make(c, name, **kw):
    r = c.post(LISTS, headers=c.h, json={'name': name, **kw})
    assert r.status_code == 201, r.text
    return r.json()['list']


def names(c):
    return [(x['name'], [t['ticker'] for t in x['tickers']]) for x in c.get(LISTS).json()['lists']]


def test_no_session_no_lists_and_writes_need_the_csrf_token(app):
    with TestClient(app.app) as anon:
        assert anon.get(LISTS).status_code == 401
    assert app.post(LISTS, headers=ORIGIN, json={'name': 'A'}).status_code == 403
    assert app.post(LISTS, headers={'Origin': 'https://elsewhere.example'}, json={'name': 'A'}).status_code == 403


def test_create_rename_choose_indicators_delete_and_restore(app):
    c = app
    core = make(c, 'Core', tickers=['BBCA', 'BMRI', 'BBCA'])
    assert core['tickers'] == [{'ticker': 'BBCA', 'position': 0}, {'ticker': 'BMRI', 'position': 1}] and core['indicators'] is None
    banks = make(c, 'Banks')
    assert names(c) == [('Core', ['BBCA', 'BMRI']), ('Banks', [])]
    assert c.patch(f'{LISTS}/{banks["id"]}', headers=c.h, json={'name': '  Big banks '}).json()['list']['name'] == 'Big banks'
    assert c.patch(f'{LISTS}/{core["id"]}', headers=c.h, json={'indicators': ['rsi', 'fn5']}).json()['list']['indicators'] == ['rsi', 'fn5']
    every = c.put('/api/v1/watchlist/indicators', headers=c.h, json={'indicators': ['volr']}).json()['lists']
    assert [x['indicators'] for x in every] == [['volr'], ['volr']]
    # delete, then Undo: the page creates it again with what it held, at its old place
    assert c.delete(f'{LISTS}/{core["id"]}', headers=c.h).status_code == 204
    back = make(c, 'Core', tickers=['BBCA', 'BMRI'], indicators=['volr'], position=0)
    assert names(c) == [('Core', ['BBCA', 'BMRI']), ('Big banks', [])] and back['indicators'] == ['volr']


def test_tickers_add_many_keep_their_place_and_undo_puts_one_back(app):
    c = app
    l = make(c, 'Core')
    r = c.post(f'{LISTS}/{l["id"]}/tickers', headers=c.h, json={'tickers': ['ADRO', 'ITMG', 'ADRO']}).json()
    assert r['added'] == ['ADRO', 'ITMG'] and r['already'] == []
    r = c.post(f'{LISTS}/{l["id"]}/tickers', headers=c.h, json={'tickers': ['ITMG', 'MEDC']}).json()
    assert r['added'] == ['MEDC'] and r['already'] == ['ITMG']
    assert c.delete(f'{LISTS}/{l["id"]}/tickers/ADRO', headers=c.h).status_code == 204
    c.post(f'{LISTS}/{l["id"]}/tickers', headers=c.h, json={'tickers': ['ADRO'], 'position': 0})
    assert names(c) == [('Core', ['ADRO', 'ITMG', 'MEDC'])]


def test_every_limit_is_published_and_a_refusal_names_the_limit_and_the_fix(app, monkeypatch):
    c = app
    published = {x['name']: x for x in c.get(LISTS).json()['limits']}
    assert set(published) == {'lists', 'tickers', 'indicators', 'name'}
    assert all(x['rule'] and x['example_ok'] and x['example_refused'].endswith(')') for x in published.values())
    monkeypatch.setattr(W, 'LISTS', 2)
    monkeypatch.setattr(W, 'PER_LIST', 3)
    a = make(c, 'A', tickers=['AAAA', 'BBBB'])
    make(c, 'B')
    r = c.post(LISTS, headers=c.h, json={'name': 'C'})
    assert r.status_code == 422 and r.json()['error']['details'] == {'limit': 'lists', 'allowed': 2, 'needed': 3}
    assert 'Delete one first' in r.json()['error']['message']
    r = c.post(f'{LISTS}/{a["id"]}/tickers', headers=c.h, json={'tickers': ['CCCC', 'DDDD']})
    assert r.status_code == 422 and r.json()['error']['details'] == {'limit': 'tickers', 'allowed': 3, 'needed': 4}
    assert names(c)[0] == ('A', ['AAAA', 'BBBB'])                      # refused whole: nothing half-added
    r = c.patch(f'{LISTS}/{a["id"]}', headers=c.h, json={'indicators': [f'k{n}' for n in range(9)]})
    assert r.status_code == 422 and r.json()['error']['details']['limit'] == 'indicators'
    assert c.patch(f'{LISTS}/{a["id"]}', headers=c.h, json={'indicators': []}).status_code == 422
    r = c.patch(f'{LISTS}/{a["id"]}', headers=c.h, json={'name': 'b'})
    assert r.status_code == 409 and r.json()['error']['code'] == 'NAME_TAKEN'
    for bad in ({'name': ''}, {'name': 'x' * 41}, {'name': 'Z', 'tickers': ['bbca']}, {'name': 'Z', 'indicators': ['RSI']}):
        r = c.post(LISTS, headers=c.h, json=bad)
        assert r.status_code == 422 and r.json()['error']['field'] in ('name', 'tickers', 'indicators'), bad


def test_the_last_list_stays_and_an_unknown_list_is_not_found(app):
    c = app
    only = make(c, 'Only')
    r = c.delete(f'{LISTS}/{only["id"]}', headers=c.h)
    assert r.status_code == 409 and r.json()['error']['code'] == 'LAST_LIST'
    for bad in ('not-a-uuid', '00000000-0000-0000-0000-000000000000'):
        assert c.patch(f'{LISTS}/{bad}', headers=c.h, json={'name': 'X'}).status_code == 404
        assert c.delete(f'{LISTS}/{bad}/tickers/BBCA', headers=c.h).status_code == 404


def test_one_account_never_reads_or_changes_another_accounts_lists(app):
    c = app
    theirs = db(c, "INSERT INTO edge_bff.watchlist_lists(owner_key,name,position) VALUES ('someone-else','Core',0) "
                   'RETURNING list_id::text AS id')[0]['id']
    db(c, "INSERT INTO edge_bff.watchlist_items(owner_key,list_id,ticker,position) VALUES ('someone-else',%s,'TLKM',0)", theirs)
    assert c.get(LISTS).json()['lists'] == []
    assert make(c, 'Core')['name'] == 'Core'                           # names are per account
    assert c.patch(f'{LISTS}/{theirs}', headers=c.h, json={'name': 'Mine'}).status_code == 404
    assert c.post(f'{LISTS}/{theirs}/tickers', headers=c.h, json={'tickers': ['BBCA']}).status_code == 404
    assert c.delete(f'{LISTS}/{theirs}', headers=c.h).status_code == 404
    assert c.delete(f'{LISTS}/{theirs}/tickers/TLKM', headers=c.h).status_code == 404
    assert db(c, "SELECT name FROM edge_bff.watchlist_lists WHERE owner_key='someone-else'") == [{'name': 'Core'}]
    assert db(c, "SELECT count(*) AS n FROM edge_bff.watchlist_items WHERE owner_key='someone-else'")[0]['n'] == 1


def test_the_screener_star_is_the_first_list(app, monkeypatch):
    """Decision 2A: the star creates the first list when there is none, adds to and removes from the first list only."""
    c = app
    async def no_worker_needed():                                       # the star never asks the screener-worker
        return None
    monkeypatch.setattr(c.app.state.screeners, 'guard', no_worker_needed)
    assert c.put('/api/v1/screener/watchlist/BBCA', headers=c.h).status_code == 204
    assert names(c) == [('Watchlist', ['BBCA'])]
    second = make(c, 'Second', tickers=['TLKM'])
    assert c.put('/api/v1/screener/watchlist/TLKM', headers=c.h).status_code == 204     # into the first, not the second
    assert names(c) == [('Watchlist', ['BBCA', 'TLKM']), ('Second', ['TLKM'])]
    assert [x['ticker'] for x in c.get('/api/v1/screener/watchlist').json()['tickers']] == ['BBCA', 'TLKM']
    assert c.delete('/api/v1/screener/watchlist/TLKM', headers=c.h).status_code == 204
    assert names(c) == [('Watchlist', ['BBCA']), ('Second', ['TLKM'])] and second


def test_the_migration_moves_todays_stars_into_the_first_list_and_refuses_more_than_a_list_holds(database):
    """20261116_001 on watchlist_items as 20261028_001 left them: each owner's stars become its list "Watchlist" in the
    order they were starred; more than 50 for one owner stops the migration before any change."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[3] / 'database/migrations'
    old, new = (root / '20261028_001_edge_bff_screener.sql').read_text(), (root / '20261116_001_edge_bff_watchlist_lists.sql').read_text()
    drop = 'DROP TABLE IF EXISTS edge_bff.watchlist_lists CASCADE; DROP TABLE edge_bff.watchlist_items; DROP TABLE edge_bff.screener_items;'
    with psycopg.connect(database, autocommit=True) as conn:
        try:
            conn.execute(drop)
            conn.execute(old)
            conn.execute("""INSERT INTO edge_bff.watchlist_items(owner_key,ticker,added_at) VALUES
                ('o','TLKM','2026-01-02'),('o','BBCA','2026-01-01'),('p','ASII','2026-01-03')""")
            conn.execute(new)
            got = conn.execute("""SELECT l.owner_key, l.name, l.position, i.ticker, i.position AS p FROM edge_bff.watchlist_items i
                JOIN edge_bff.watchlist_lists l USING (owner_key, list_id) ORDER BY 1, 5""").fetchall()
            assert [tuple(r) for r in got] == [('o', 'Watchlist', 0, 'BBCA', 0), ('o', 'Watchlist', 0, 'TLKM', 1), ('p', 'Watchlist', 0, 'ASII', 0)]
            conn.execute(drop)
            conn.execute(old)
            conn.execute("INSERT INTO edge_bff.watchlist_items(owner_key,ticker) SELECT 'o', 'T' || n FROM generate_series(1, 51) n")
            with pytest.raises(psycopg.errors.RaiseException, match='more than 50'):
                conn.execute(new)
            conn.execute('ROLLBACK')
            assert conn.execute("SELECT to_regclass('edge_bff.watchlist_lists')").fetchone()[0] is None
        finally:
            conn.execute('ROLLBACK') if conn.info.transaction_status else None
            conn.execute(drop)
            conn.execute(old)
            conn.execute(new)
