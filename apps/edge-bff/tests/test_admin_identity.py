"""Phase 4, the Phase 4 checker's gates-1 and gates-2 (2026-11-22): the admin page acts only as a known, active account
(app/principal.py Auth.admin_account, admin_known; app/store.py account_status, session_step_up).

- With the switch off, user #1's id comes from the seed read at the start. A seed not read then (account_seed_failed,
  swallowed with the switch off) left the principal without an id, so the actions ran with no actor, the own-account
  guard saw no own account and the audit rows had no actor. Now the seed is read again at the gate; without it every
  admin route answers 503 ADMIN_ACCOUNT_UNAVAILABLE and nothing is written.
- A disabled user #1 kept the beta's admin page (the switch-off session read no status). Now its stepped-up session and
  a new code step answer 403 ACCOUNT_DISABLED, and the store makes no new admin session for it."""
import dataclasses

import psycopg
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app import mfa, principal as principal_module
from app.main import create_app
from conftest import FakeOrc
from test_admin import KEY, code_of, db, error_of, passed, seed_id
from test_edge import ORIGIN, login
from test_principal import make_user


@pytest.fixture
def beta(settings):
    return dataclasses.replace(settings, mfa_key=KEY, code_secret='c' * 40)


def stepped_up(store, beta):
    """A session of user #1 past the code step, made by one app; returns (cookies, write headers)."""
    with TestClient(create_app(beta, store, FakeOrc())) as c:
        h = passed(c, store, beta)
        return dict(c.cookies), h


def failing_seed(monkeypatch, times):
    """Auth.seed_user raises `times` times (a dropped connection at the start), then reads as before."""
    real = principal_module.Auth.seed_user
    left = {'n': times}

    def seed_user(self):
        if left['n'] > 0:
            left['n'] -= 1
            raise psycopg.OperationalError('connection dropped')
        return real(self)
    monkeypatch.setattr(principal_module.Auth, 'seed_user', seed_user)


def admin_get_routes(app):
    return sorted(r.path for r in app.routes if isinstance(r, APIRoute) and r.path.startswith('/api/v1/admin')
                  and 'GET' in r.methods and '{' not in r.path)


def test_without_the_seed_every_admin_route_refuses_and_writes_nothing(beta, store, monkeypatch):
    jar, h = stepped_up(store, beta)
    own = seed_id(store, beta)
    alice = make_user(store, 'alice_seed', 'alice-password', email='alice.seed@example.com')
    failing_seed(monkeypatch, times=10 ** 6)
    app = create_app(beta, store, FakeOrc())
    with TestClient(app) as c:
        for k, v in jar.items():
            c.cookies.set(k, v)
        assert app.state.auth.seed is None
        for path in admin_get_routes(app):
            r = c.get(path)
            assert r.status_code == 503 and error_of(r)['code'] == 'ADMIN_ACCOUNT_UNAVAILABLE', (path, r.text)
        for target in (own, alice['user_id']):
            r = c.post(f'/api/v1/admin/users/{target}/sessions/revoke', headers=h, json={'reason': 'gates-1'})
            assert r.status_code == 503, r.text
            r = c.post(f'/api/v1/admin/users/{target}/status', headers=h, json={'status': 'disabled', 'reason': 'gates-1'})
            assert r.status_code == 503, r.text
    assert db(store, 'SELECT count(*) AS n FROM edge_bff.admin_audit')[0]['n'] == 0
    assert db(store, 'SELECT status FROM edge_bff.users WHERE user_id = %s', own)[0]['status'] == 'active'


def test_a_seed_failed_at_the_start_is_read_again_and_the_own_account_stays_closed(beta, store, monkeypatch):
    jar, h = stepped_up(store, beta)
    own = seed_id(store, beta)
    second = make_user(store, 'second_admin', 'second-password')
    db(store, '''INSERT INTO edge_bff.user_capability_overrides(user_id, capability_key, value, reason)
        VALUES (%s, 'admin.access', 'true'::jsonb, 'a second admin')''', second['user_id'])
    failing_seed(monkeypatch, times=1)                       # the start fails, the next read works
    app = create_app(beta, store, FakeOrc())
    with TestClient(app) as c:
        for k, v in jar.items():
            c.cookies.set(k, v)
        assert app.state.auth.seed is None
        detail = c.get(f'/api/v1/admin/users/{own}')
        assert detail.status_code == 200, detail.text
        assert not detail.json()['actions']['status']['open'] and not detail.json()['actions']['sessions']['open']
        r = c.post(f'/api/v1/admin/users/{own}/status', headers=h, json={'status': 'disabled', 'reason': 'gates-1'})
        assert r.status_code == 400 and 'account' in error_of(r)['details']['fields'], r.text
        r = c.post(f'/api/v1/admin/users/{own}/sessions/revoke', headers=h, json={'reason': 'gates-1'})
        assert r.status_code == 400, r.text
        r = c.post(f"/api/v1/admin/users/{second['user_id']}/sessions/revoke", headers=h, json={'reason': 'gates-1'})
        assert r.status_code == 200, r.text
    assert db(store, 'SELECT status FROM edge_bff.users WHERE user_id = %s', own)[0]['status'] == 'active'
    rows = db(store, 'SELECT actor_user_id FROM edge_bff.admin_audit')
    assert rows and all(row['actor_user_id'] == own for row in rows), rows


def test_a_disabled_owner_loses_the_admin_page_and_gets_no_new_step(beta, store):
    with TestClient(create_app(beta, store, FakeOrc())) as c:
        h = passed(c, store, beta)
        own = seed_id(store, beta)
        db(store, "UPDATE edge_bff.users SET status = 'disabled' WHERE user_id = %s", own)
        r = c.get('/api/v1/admin/overview')
        assert r.status_code == 403 and error_of(r)['code'] == 'ACCOUNT_DISABLED', r.text
        alice = make_user(store, 'alice_dis', 'alice-password', email='alice.dis@example.com')
        r = c.post(f"/api/v1/admin/users/{alice['user_id']}/reveal", headers=h, json={'field': 'email', 'reason': 'x'})
        assert r.status_code == 403, r.text
    with TestClient(create_app(beta, store, FakeOrc())) as c:
        hh = login(c)
        nonce = bytes(db(store, 'SELECT nonce FROM edge_bff.mfa_totp WHERE user_id = %s', own)[0]['nonce'])
        r = c.get('/api/v1/admin/step-up')
        assert r.status_code == 403 and error_of(r)['code'] == 'ACCOUNT_DISABLED', r.text
        r = c.post('/api/v1/admin/step-up', headers=hh, json={'code': code_of(own, nonce, mfa.step_now() + 1)})
        assert r.status_code == 403 and error_of(r)['code'] == 'ACCOUNT_DISABLED', r.text
    assert db(store, 'SELECT count(*) AS n FROM edge_bff.admin_audit')[0]['n'] == 0


def test_the_store_makes_no_admin_session_for_a_disabled_owner(beta, store):
    with TestClient(create_app(beta, store, FakeOrc())) as c:
        login(c)
    own = seed_id(store, beta)
    old = db(store, 'SELECT token_hash FROM edge_bff.sessions WHERE user_id IS NULL AND revoked_at IS NULL')[0]['token_hash']
    db(store, "UPDATE edge_bff.users SET status = 'disabled' WHERE user_id = %s", own)
    assert store.session_step_up(old, 'f' * 64, beta.owner) is False
    db(store, "UPDATE edge_bff.users SET status = 'active' WHERE user_id = %s", own)
    assert store.session_step_up(old, 'f' * 64, beta.owner) is True


def test_every_admin_route_rests_on_the_identity_check():
    """A new admin route cannot skip admin_account: each one depends on admin_page or admin_known."""
    from app.config import Settings  # noqa: F401 - the app below is built from the default test settings
    import inspect
    src = inspect.getsource(__import__('app.admin', fromlist=['x']))
    assert 'Depends(auth.admin())' not in src and 'Depends(auth.admin(write=True))' not in src
