"""C2 probes (Phase 3a): cross-principal answers of the shared caches."""
from fastapi.testclient import TestClient

from app.main import create_app
from conftest import FakeOrc
from test_principal import db, make_user, on, sign_in, workers  # noqa: F401
from test_phase3a_gates import paid_user, override, SC, WL


def test_screener_catalog_etag_of_one_principal_is_not_a_304_for_another(on, store):
    with TestClient(create_app(on, store, FakeOrc())) as a:
        b, adm = TestClient(a.app), TestClient(a.app)
        paid_user(store, 'alice')
        bob = paid_user(store, 'bobby')
        override(store, bob['user_id'], 'screener.saved_items', '1')
        make_user(store, 'admin_x', 'admin_x-password', role='admin')
        sign_in(a, 'alice', 'alice-password')
        sign_in(b, 'bobby', 'bobby-password')
        sign_in(adm, 'admin_x', 'admin_x-password')
        db(store, 'UPDATE edge_bff.sessions SET mfa_passed_at = now() WHERE revoked_at IS NULL')
        ra, radm = a.get(f'{SC}/catalog'), adm.get(f'{SC}/catalog')
        assert ra.status_code == radm.status_code == 200
        for tag in (ra.headers['etag'], radm.headers['etag']):
            rb = b.get(f'{SC}/catalog', headers={'If-None-Match': tag})
            assert rb.status_code == 200, tag
            assert {x['name']: x['value'] for x in rb.json()['limits']}['saved_items'] == 1
            assert rb.headers['etag'] != tag
        print('alice', ra.headers['etag'], 'admin', radm.headers['etag'])
        # upgrade of bob: the next request gets the HARD numbers and alice's document
        db(store, 'DELETE FROM edge_bff.user_capability_overrides WHERE user_id = %s', bob['user_id'])
        assert b.get(f'{SC}/catalog').headers['etag'] == ra.headers['etag']


def test_screener_star_reads_and_writes_the_watchlist_without_watchlist_view(on, store):
    with TestClient(create_app(on, store, FakeOrc())) as c:
        alice = paid_user(store, 'alice')
        override(store, alice['user_id'], 'watchlist.view', 'false')
        h = sign_in(c, 'alice', 'alice-password')
        assert c.get(f'{WL}/lists').status_code == 403
        put = c.put(f'{SC}/watchlist/BBCA', headers=h)
        got = c.get(f'{SC}/watchlist')
        print('PUT', put.status_code, 'GET', got.status_code, got.text)
        assert put.status_code == 403 and got.status_code == 403


def test_screener_star_does_not_create_a_list_beyond_the_lists_cap(on, store):
    with TestClient(create_app(on, store, FakeOrc())) as c:
        alice = paid_user(store, 'alice')
        override(store, alice['user_id'], 'watchlist.lists', '0')
        h = sign_in(c, 'alice', 'alice-password')
        assert c.post(f'{WL}/lists', headers=h, json={'name': 'Mine'}).status_code == 403     # re-check R2-39
        put = c.put(f'{SC}/watchlist/BBCA', headers=h)
        lists = c.get(f'{WL}/lists').json()['lists']
        print('PUT', put.status_code, 'lists', len(lists))
        assert put.status_code == 403 and lists == []                                       # re-check R2-39
