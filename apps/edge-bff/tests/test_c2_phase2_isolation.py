"""Checker C2 (EDGE multi-user Phase 2): isolation between users and between plans (CONTRACT.md sections 2, 8a, 12).

Each test names the contract line it holds the code to."""
import dataclasses
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from conftest import FakeOrc
from test_principal import db, make_user, sign_in
from test_plan_catalog import HEADER, access, on, subscribe  # noqa: F401 - the fixture `on`


def paid_plan(store):
    return db(store, '''SELECT plan_key FROM edge_bff.plan_capabilities WHERE capability_key = 'backtest.run' ''')[0]['plan_key']


def test_one_users_subscription_and_override_never_reach_another(on, store):
    """CONTRACT.md 8a: the join keys of the subscription and the overrides are the session's own user."""
    with TestClient(create_app(on, store, FakeOrc())) as c:
        alice = make_user(store, 'alice', 'alice-password')
        make_user(store, 'bob', 'bob-password')
        sign_in(c, 'bob', 'bob-password')
        bob_before, bob_header = access(c)
        subscribe(store, alice['user_id'], paid_plan(store))
        db(store, '''INSERT INTO edge_bff.user_capability_overrides(user_id, capability_key, value, reason)
            VALUES (%s, 'terminal.indicator', '{"all": true}', 'c2 probe')''', alice['user_id'])
        bob_after, bob_header_after = access(c)
        assert (bob_after, bob_header_after) == (bob_before, bob_header)
        assert c.get('/api/v1/catalog/indicator').json()['entries'] == []
        sign_in(c, 'alice', 'alice-password')
        alice_access, alice_header = access(c)
        assert alice_access['plan'] != bob_before['plan'] and alice_header != bob_header
        assert c.get('/api/v1/catalog/indicator').json()['entries'] != []


def test_two_users_on_the_same_plan_share_a_version_and_an_override_splits_it(on, store):
    """CONTRACT.md 8a: the version is a hash of what the principal may do; equal access, equal version (no needless
    reloads); an override is part of the access."""
    with TestClient(create_app(on, store, FakeOrc())) as c:
        a = make_user(store, 'anna', 'anna-password')
        make_user(store, 'bert', 'bert-password')
        sign_in(c, 'anna', 'anna-password')
        _, va = access(c)
        sign_in(c, 'bert', 'bert-password')
        _, vb = access(c)
        assert va == vb
        db(store, '''INSERT INTO edge_bff.user_capability_overrides(user_id, capability_key, value, reason)
            VALUES (%s, 'terminal.history_days', '3650', 'c2 probe')''', a['user_id'])
        sign_in(c, 'anna', 'anna-password')
        got, va2 = access(c)
        assert va2 != vb and got['limits']['terminal.history_days'] == 3650


def test_a_disabled_user_and_a_session_with_another_users_id_are_unauthenticated(on, store):
    """CONTRACT.md section 2: a disabled user or a session that does not join its own account answers 401."""
    with TestClient(create_app(on, store, FakeOrc())) as c:
        a = make_user(store, 'carl', 'carl-password')
        b = make_user(store, 'dora', 'dora-password')
        subscribe(store, b['user_id'], paid_plan(store))
        sign_in(c, 'carl', 'carl-password')
        assert c.get('/api/v1/catalog/indicator').status_code == 200
        # carl's session pointed at dora's user_id (owner_key stays carl's): no join, no dora grants
        db(store, 'UPDATE edge_bff.sessions SET user_id = %s WHERE user_id = %s', b['user_id'], a['user_id'])
        r = c.get('/api/v1/catalog/indicator')
        assert r.status_code == 401 and HEADER not in r.headers
        db(store, 'UPDATE edge_bff.sessions SET user_id = %s WHERE owner_key = %s', a['user_id'], a['owner_key'])
        assert c.get('/api/v1/catalog/indicator').status_code == 200
        db(store, "UPDATE edge_bff.users SET status = 'disabled' WHERE user_id = %s", a['user_id'])
        r = c.get('/api/v1/catalog/indicator')
        assert r.status_code == 401 and HEADER not in r.headers


def test_the_terminal_proxy_answer_carries_the_entitlements_version(on, store, monkeypatch):
    """CONTRACT.md 8a "version": it is sent as X-Edge-Entitlements on EVERY authenticated API answer. The Terminal
    reads its data through /api/terminal/v1/* with the shared session module's send() (terminal/src/data/live.ts:72),
    which re-reads the session only when an answer carries a new version. The middleware (app/main.py, 'startswith
    /api/v1/') leaves the Terminal's authenticated data answers without the header, so a Terminal page never sees a
    plan change through its own data calls."""
    terminal = dataclasses.replace(on, terminal_url='http://terminal.test', terminal_proxy_key='k' * 32)

    class Answer:
        status_code = 200
        headers = {'content-type': 'application/json'}

        @staticmethod
        def json():
            return {'ok': True}

    async def fake_request(self, method, url, **kw):
        # terminal-api (Phase 3c, EXEC-MU-ACCOUNTS re-check R2-4) acknowledges the owner header it applied, without
        # which edge-bff relays no answer for a capped principal
        answer = Answer()
        answer.headers = {**Answer.headers, 'x-terminal-capabilities-applied':
                          f"1 {json.loads(kw['headers']['x-terminal-capabilities'])['version']}"}
        return answer
    monkeypatch.setattr(httpx.AsyncClient, 'request', fake_request)
    with TestClient(create_app(terminal, store, FakeOrc())) as c:
        make_user(store, 'erin', 'erin-password')
        sign_in(c, 'erin', 'erin-password')
        _, version = access(c)
        path = 'manifest/BBCA'
        r = c.get(f'/api/terminal/v1/{path}')
        assert r.status_code == 200, r.text
        assert r.headers.get(HEADER) == version


def test_the_seed_on_a_live_like_database_with_the_switch_off_gives_one_subscription(settings, store):
    """CONTRACT.md 8a "User #1" with the switch off, on a database where user #1 already exists (owner edge-private,
    username admin_1): restarts give one subscription, nothing else changes."""
    live = dataclasses.replace(settings, owner='edge-private')
    with store.connect() as c:
        c.execute('''INSERT INTO edge_bff.users(owner_key, username, role, status) VALUES ('edge-private', 'admin_1',
            'admin', 'active')''')
    for _ in range(3):
        with TestClient(create_app(live, store, FakeOrc())) as c:
            pass
    subs = db(store, 'SELECT u.owner_key, s.plan_key, s.status, s.expires_at FROM edge_bff.subscriptions s JOIN edge_bff.users u USING (user_id)')
    assert len(subs) == 1 and subs[0]['owner_key'] == 'edge-private' and subs[0]['expires_at'] is None
    assert db(store, 'SELECT count(*) AS n FROM edge_bff.users')[0]['n'] == 1
