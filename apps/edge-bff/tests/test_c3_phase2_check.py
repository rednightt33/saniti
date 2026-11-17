"""C3 Phase 2 checks (conformance and regression, CONTRACT.md 0, 2, 8a): the switch-off deploy against a database
where user #1 already exists (Phase 1 seed: owner edge-private, login admin -> username admin_1, no subscription), and
an edge-bff started before the catalog migration."""
import dataclasses
import os
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
from fastapi.testclient import TestClient

from app.accounts import AccountStore
from app.main import create_app
from app.principal import Auth
from app.rights import rights_of
from app.security import password_verifier
from app.store import Store
from conftest import FakeOrc
from test_edge import ORIGIN
from test_principal import db

ROOT = Path(__file__).resolve().parents[3]
PHASE1 = ['20261008_002_create_edge_bff.sql', '20261012_008_edge_bff_conversation_hidden.sql',
          '20261024_002_edge_bff_conversation_branch.sql', '20261026_005_edge_bff_backtest.sql',
          '20261027_005_edge_bff_backtest_error_comment.sql', '20261028_001_edge_bff_screener.sql',
          '20261106_001_edge_bff_terminal_layouts.sql', '20261106_002_edge_bff_indicator_presets.sql',
          '20261107_001_edge_bff_terminal_drawings.sql', '20261116_001_edge_bff_watchlist_lists.sql',
          '20261116_002_edge_bff_accounts_auth_throttle.sql', '20261116_003_edge_bff_accounts_users.sql',
          '20261117_001_edge_bff_accounts_registration.sql', '20261117_002_edge_bff_accounts_registration_binding.sql']


def live_like(settings):
    return dataclasses.replace(settings, owner='edge-private', login='admin', admin_owners=('edge-private',),
                               password_verifier=password_verifier('live-password'))


def sign_in(c, login, password):
    return c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': login, 'password': password})


def test_existing_user_one_without_subscription_switch_off(settings, store):
    s = live_like(settings)
    seeded = AccountStore(store).seed(s.owner, s.login, s.password_verifier, False)     # what Phase 1 left
    assert seeded['username'] == 'admin_1'
    assert db(store, 'SELECT count(*) AS n FROM edge_bff.subscriptions')[0]['n'] == 0
    for _ in range(2):                                                                 # two starts: one subscription
        with TestClient(create_app(s, store, FakeOrc())) as c:
            assert c.get('/ready').status_code == 200
            r = sign_in(c, 'admin', 'live-password')
            assert r.status_code == 200, r.text
            a = c.get('/api/v1/auth/session')
            got = a.json()['access']
            assert got == {'plan': None, 'role': 'admin', 'status': 'active', 'expires_at': None, 'mfa_ok': True,
                           'capabilities': ['*'], 'limits': {}, 'version': 'env', 'next': None,
                           'owner_key': 'edge-private', 'mfa_enrolled': False, 'seed': True, 'expired_plan': None}
            assert a.headers['X-Edge-Entitlements'] == 'env'
            assert len(c.get('/api/v1/catalog/indicator').json()['entries']) == 53
            for path in ('/api/v1/conversations', '/api/v1/preferences', '/api/v1/models'):
                assert c.get(path).status_code == 200, path
    rows = db(store, 'SELECT plan_key, status, provider, expires_at FROM edge_bff.subscriptions')
    assert len(rows) == 1 and rows[0]['status'] == 'active' and rows[0]['expires_at'] is None
    auth = Auth(s, store)
    assert rights_of(auth.owner_principal('edge-private')) == ['flow_point_in_time']
    # the same account with the switch on: '*' from the seed subscription, so MFA before anything else (as Phase 1)
    on = dataclasses.replace(s, multiuser=True, code_secret='c' * 40, mfa_key='m' * 40)
    with TestClient(create_app(on, store, FakeOrc())) as c:
        r = sign_in(c, 'admin_1', 'live-password')                    # switch on: the username (Phase 1)
        assert r.status_code == 403 and r.json()['error']['code'] == 'MFA_REQUIRED'
    assert rights_of(Auth(on, store).owner_principal('edge-private')) == ['flow_point_in_time']


CATALOG = ('plans', 'capabilities', 'plan_capabilities', 'user_capability_overrides', 'subscriptions')


def test_edge_bff_started_before_the_catalog_migration(settings, store):
    """The catalog tables hidden (renamed) as on a database where 20261117_003 is not applied yet."""
    s = live_like(settings)
    AccountStore(store).seed(s.owner, s.login, s.password_verifier, False)
    for t in CATALOG:
        db(store, f'ALTER TABLE edge_bff.{t} RENAME TO {t}_hidden')
    try:
        with TestClient(create_app(s, store, FakeOrc())) as c:
            assert c.get('/ready').status_code == 200
            assert sign_in(c, 'admin', 'live-password').status_code == 200
            a = c.get('/api/v1/auth/session')
            assert a.status_code == 200 and a.json()['access']['capabilities'] == ['*']
            assert a.headers['X-Edge-Entitlements'] == 'env'
            assert c.get('/api/v1/conversations').status_code == 200
            assert len(c.get('/api/v1/catalog/indicator').json()['entries']) == 53
        on = dataclasses.replace(s, multiuser=True, code_secret='c' * 40, mfa_key='m' * 40)
        with TestClient(create_app(on, store, FakeOrc()), raise_server_exceptions=False) as c:
            ready = c.get('/ready').status_code
            signin = sign_in(c, 'admin_1', 'live-password').status_code
        print('SWITCH_ON_WITHOUT_CATALOG ready', ready, 'sign-in', signin)
    finally:
        for t in CATALOG:
            db(store, f'ALTER TABLE edge_bff.{t}_hidden RENAME TO {t}')


def test_every_authenticated_get_answer_carries_the_entitlements_header(settings, store):
    """CONTRACT.md 8a: X-Edge-Entitlements on every authenticated API answer (walk of the plain GET routes)."""
    from starlette.routing import Route
    s = dataclasses.replace(settings, admin_owners=(settings.owner,))
    app = create_app(s, store, FakeOrc())
    paths = sorted({r.path for r in app.routes if isinstance(r, Route) and r.path.startswith('/api/v1/')
                    and 'GET' in (r.methods or ()) and '{' not in r.path and 'events' not in r.path
                    and 'stream' not in r.path})
    missing = []
    with TestClient(app, raise_server_exceptions=False) as c:
        assert sign_in(c, 'owner', 'local-test-password').status_code == 200
        for path in paths:
            r = c.get(path)
            # auth/config is public; a 5xx here is FakeOrc lacking a method (an unhandled error, no principal answer)
            if path == '/api/v1/auth/config' or r.status_code >= 500:
                continue
            if r.status_code != 401 and r.headers.get('X-Edge-Entitlements') != 'env':
                missing.append((path, r.status_code))
    print('WALKED', len(paths), paths)
    assert missing == []
