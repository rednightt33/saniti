"""EXEC-MU-ACCOUNTS Phase 2, fix round after the checkers C1-C3 (CONTRACT.md 8a; ERRORS M480).

- A value that does not fit its capability's kind is refused when written (capability_value_check) and, should one be
  read anyway, never widens access (C1 F1; the read side is tests/test_c1_phase2_fail_closed.py).
- A flag override of false takes the plan's flag away without logging it as invalid (C1 N3, C3 N4).
- The seed subscription is given once, to the seed account only (C1 N1, C2 N1, C3 N3).
- An admin route always needs admin.access, so MFA always applies to it (C1 N2).
- A subscription marked expired without an end names the ended plan (C1 N3).
- The version covers the plan's end and the release stages (C1 N3, C2 N3, C3 N5).
- With the switch on, readiness needs the plan catalog (C3 N1).
"""
import asyncio
import json
import logging

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import releases
from app.accounts import AccountStore
from app.errors import Refusal
from app.main import create_app
from app.principal import Auth, Principal
from conftest import FakeOrc
from test_plan_catalog import on, subscribe  # noqa: F401 - the fixture `on`
from test_principal import db, make_user


def plan_without_star(store, default):
    return db(store, '''SELECT plan_key FROM edge_bff.plans WHERE is_default = %s AND plan_key NOT IN
        (SELECT plan_key FROM edge_bff.plan_capabilities WHERE capability_key = '*')''', default)[0]['plan_key']


# ---- write-time value shapes ----------------------------------------------------------------------------------------

@pytest.mark.parametrize('key,value', [
    ('terminal.history_days', '-1'), ('terminal.history_days', '730.5'), ('terminal.history_days', '"730"'),
    ('terminal.history_days', 'true'), ('terminal.history_days', 'null'),
    ('terminal.tickers', '"BBCA"'), ('terminal.tickers', '[1]'), ('terminal.tickers', '{"ids": ["BBCA"]}'),
    ('terminal.view', '"true"'), ('terminal.view', '1'), ('*', '{"all": true}'),
    ('terminal.indicator', '{"ids": "I01"}'), ('terminal.indicator', '{"all": "true"}'),
    ('terminal.indicator', '{"stages": ["relesed"]}'), ('terminal.indicator', '{"ids": [], "extra": 1}'),
])
def test_a_value_of_the_wrong_shape_is_refused_when_written(store, key, value):
    free = plan_without_star(store, True)
    with pytest.raises(psycopg.errors.RaiseException, match='does not fit capability') as caught:
        db(store, '''INSERT INTO edge_bff.plan_capabilities(plan_key, capability_key, value) VALUES (%s, %s, %s::jsonb)
            ON CONFLICT (plan_key, capability_key) DO UPDATE SET value = excluded.value''', free, key, value)
    assert 'non-negative integer' in (caught.value.diag.message_hint or '')        # how to pass, with an example
    alice = make_user(store, 'alice', 'alice-password')
    with pytest.raises(psycopg.errors.RaiseException, match='does not fit capability'):
        db(store, '''INSERT INTO edge_bff.user_capability_overrides(user_id, capability_key, value, reason)
            VALUES (%s, %s, %s::jsonb, 'typo')''', alice['user_id'], key, value)


@pytest.mark.parametrize('key,value', [
    ('terminal.history_days', '0'), ('terminal.history_days', '365'), ('terminal.tickers', '[]'),
    ('terminal.tickers', '["BBCA", "BBRI"]'), ('terminal.view', 'true'), ('terminal.view', 'false'),
    ('terminal.indicator', '{}'), ('terminal.indicator', '{"ids": ["I01"], "stages": ["lab", "released"], "all": false}'),
])
def test_a_value_of_the_right_shape_is_written(store, key, value):
    alice = make_user(store, 'alice', 'alice-password')
    db(store, '''INSERT INTO edge_bff.user_capability_overrides(user_id, capability_key, value, reason)
        VALUES (%s, %s, %s::jsonb, 'ok')''', alice['user_id'], key, value)


def test_a_flag_override_of_false_takes_the_plans_flag_away_quietly(on, store, caplog):
    alice = make_user(store, 'alice', 'alice-password')
    auth = Auth(on, store)
    assert auth.owner_principal(alice['owner_key']).can('terminal.view')                # the default plan's flag
    db(store, '''INSERT INTO edge_bff.user_capability_overrides(user_id, capability_key, value, reason)
        VALUES (%s, 'terminal.view', 'false', 'taken away')''', alice['user_id'])
    with caplog.at_level(logging.WARNING, 'edge_bff.principal'):
        p = auth.owner_principal(alice['owner_key'])
    assert not p.can('terminal.view') and 'terminal.view' not in p.access()['capabilities']
    assert 'capability_value_invalid' not in caplog.text


# ---- the seed subscription ------------------------------------------------------------------------------------------

def test_a_cancelled_seed_subscription_is_never_given_back(on, store):
    with TestClient(create_app(on, store, FakeOrc())):
        pass
    db(store, "UPDATE edge_bff.subscriptions SET status = 'cancelled'")
    for _ in range(2):
        with TestClient(create_app(on, store, FakeOrc())):
            pass
    assert [r['status'] for r in db(store, 'SELECT status FROM edge_bff.subscriptions')] == ['cancelled']
    seed = db(store, 'SELECT owner_key FROM edge_bff.users WHERE owner_key = %s', on.owner)[0]['owner_key']
    assert not Auth(on, store).owner_principal(seed).can('*')


def test_the_seed_subscription_is_never_given_to_a_registered_account(store, caplog):
    alice = make_user(store, 'alice', 'alice-password', everything=False)              # an owner key of the u_ form
    with caplog.at_level(logging.WARNING, 'edge_bff.accounts'):
        assert AccountStore(store).seed_subscription(alice['user_id']) is None
    assert 'account_seed_plan_refused' in caplog.text
    assert db(store, 'SELECT count(*) AS n FROM edge_bff.subscriptions')[0]['n'] == 0


# ---- admin routes ---------------------------------------------------------------------------------------------------

def test_an_admin_route_needs_admin_access_whatever_its_own_capability(on, store):
    narrow = Principal(user_id=7, owner_key='u_' + '0' * 24, username='narrow', role='user', plan_key='x',
                       status='active', expires_at=None, mfa_ok=True, capabilities=frozenset({'admin.manual'}))
    check = Auth(on, store).admin(capability='admin.manual')
    with pytest.raises(Refusal) as refused:
        asyncio.run(check(narrow))
    assert refused.value.code == 'CAPABILITY_REQUIRED'
    everything = Principal(user_id=1, owner_key='edge-private', username='admin_1', role='admin', plan_key='x',
                           status='active', expires_at=None, mfa_ok=True, capabilities=frozenset({'*'}))
    assert asyncio.run(check(everything)) is everything
    pending = Principal(user_id=1, owner_key='edge-private', username='admin_1', role='admin', plan_key='x',
                        status='active', expires_at=None, mfa_ok=False, capabilities=frozenset({'*'}))
    with pytest.raises(Refusal) as refused:
        asyncio.run(check(pending))
    assert refused.value.code == 'MFA_REQUIRED'


# ---- ended plans and the version ------------------------------------------------------------------------------------

def test_a_subscription_marked_expired_without_an_end_names_the_ended_plan(on, store):
    alice = make_user(store, 'alice', 'alice-password')
    paid = plan_without_star(store, False)
    subscribe(store, alice['user_id'], paid, status='expired')
    p = Auth(on, store).owner_principal(alice['owner_key'])
    assert p.expired_plan == paid and p.plan_key == plan_without_star(store, True)
    assert p.refusal('monitor.chat').code == 'PLAN_EXPIRED'


def test_the_version_follows_the_plans_end_and_the_release_stages(on, store, monkeypatch):
    alice = make_user(store, 'alice', 'alice-password')
    paid = plan_without_star(store, False)
    subscribe(store, alice['user_id'], paid, expires="now() + interval '1 day'")
    auth = Auth(on, store)
    first = auth.owner_principal(alice['owner_key']).version
    db(store, "UPDATE edge_bff.subscriptions SET expires_at = expires_at + interval '30 days'")
    extended = auth.owner_principal(alice['owner_key']).version
    assert extended != first                                                          # an extension reaches open pages
    data = json.loads(releases.PATH.read_text(encoding='utf-8'))
    data['items'][0]['stage'] = 'lab' if data['items'][0]['stage'] == 'released' else 'released'
    monkeypatch.setattr(releases, 'CURRENT', releases.Releases(data))
    assert auth.owner_principal(alice['owner_key']).version != extended               # a stage change too


# ---- readiness ------------------------------------------------------------------------------------------------------

def test_with_the_switch_on_readiness_needs_the_plan_catalog(store):
    store.ready(False)
    store.ready(True)
    db(store, 'ALTER TABLE edge_bff.subscriptions RENAME TO subscriptions_hidden')
    try:
        store.ready(False)                                       # the switch off reads no plan table
        with pytest.raises(psycopg.errors.UndefinedTable):
            store.ready(True)
    finally:
        db(store, 'ALTER TABLE edge_bff.subscriptions_hidden RENAME TO subscriptions')


def test_the_runtime_role_writes_an_override_through_the_value_check(store):
    """edge-bff's own role (as the Phase 4 admin actions will) passes the check for a right value and is refused a
    wrong one: the trigger fires for it without any grant on the function."""
    alice = make_user(store, 'alice', 'alice-password')
    with store.connect() as c:
        c.execute('SET LOCAL ROLE edge_bff_runtime')
        c.execute('''INSERT INTO edge_bff.user_capability_overrides(user_id, capability_key, value, reason)
            VALUES (%s, 'terminal.history_days', '365', 'trial')''', (alice['user_id'],))
    with pytest.raises(psycopg.errors.RaiseException, match='does not fit capability'):
        with store.connect() as c:
            c.execute('SET LOCAL ROLE edge_bff_runtime')
            c.execute('''UPDATE edge_bff.user_capability_overrides SET value = '"365"' WHERE user_id = %s''',
                      (alice['user_id'],))
    assert db(store, 'SELECT value FROM edge_bff.user_capability_overrides')[0]['value'] == 365
