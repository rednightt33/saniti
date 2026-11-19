"""EXEC-MU-ACCOUNTS fix round, track "plans" (the re-check of Phases 0-3b, findings R1-* and R2-* named per test): the
tests the fix round adds beside the re-check's own failing tests, which are the acceptance of each finding."""
from fastapi.testclient import TestClient

from app import preferences
from app.main import create_app
from conftest import FakeOrc
from test_principal import db, on, sign_in, workers  # noqa: F401 (fixtures)
from test_phase3a_gates import override, paid_user


def test_every_preference_capability_is_a_flag_of_the_catalog(store):
    """R1-18: the capability a sync key needs (catalog/storage_sync.json, from the registry) is a flag the plan catalog
    defines, so no key can name a capability nobody can hold."""
    named = {cap for cap in preferences.CAPABILITY_OF.values() if cap}
    rows = db(store, 'SELECT capability_key, kind FROM edge_bff.capabilities WHERE capability_key = ANY(%s)', list(named))
    assert {r['capability_key']: r['kind'] for r in rows} == {cap: 'flag' for cap in named}


def test_a_preference_of_a_tab_the_plan_holds_is_served_and_one_of_a_shared_key_always(on, store):
    """R1-18: a paid plan without the Watchlist keeps its Terminal and shared preferences; only the Watchlist's key is
    left out and refused, and its row is kept (D5: back when the plan holds the tab again)."""
    with TestClient(create_app(on, store, FakeOrc())) as c:
        paula = paid_user(store, 'paula')
        h = sign_in(c, 'paula', 'paula-password')
        for key in ('ml.symbol', 'ml.tf', 'edge.watchlist.view'):
            assert c.put(f'/api/v1/preferences/{key}', headers=h, json={'value': 'x', 'version': None}).status_code == 201
        override(store, paula['user_id'], 'watchlist.view', 'false')
        held = set(c.get('/api/v1/preferences').json()['preferences'])
        assert held == {'ml.symbol', 'ml.tf'}
        refused = c.put('/api/v1/preferences/edge.watchlist.view', headers=h, json={'value': 'y', 'version': 1})
        assert refused.status_code == 403 and refused.json()['error']['code'] == 'CAPABILITY_REQUIRED'
        assert refused.json()['error']['details']['capability'] == 'watchlist.view'
        assert db(store, 'SELECT value FROM edge_bff.user_preferences WHERE pref_key = %s', 'edge.watchlist.view')[0]['value'] == 'x'
        db(store, 'DELETE FROM edge_bff.user_capability_overrides WHERE user_id = %s', paula['user_id'])
        assert 'edge.watchlist.view' in c.get('/api/v1/preferences').json()['preferences']
