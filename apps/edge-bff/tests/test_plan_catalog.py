"""EXEC-MU-ACCOUNTS Phase 2 (CONTRACT.md section 8a, acceptance tests of builder B1): the plan catalog.

- switch on: one statement resolves the session, the account, its live subscription (else the default plan), the
  plan's plan_capabilities and the account's unexpired overrides (an override replaces the plan's value);
- a catalog-only change (an UPDATE of plan_capabilities) changes the next request's access and X-Edge-Entitlements,
  with no restart;
- expiry is decided at read time: a subscription that ended a second ago resolves to the default plan, and
  access.expired_plan names the ended plan; a capability only the ended plan held is refused PLAN_EXPIRED;
- items: `<family>:<id>` by ids, release stages or all; a plan holding the stage 'released' is refused a 'lab' item;
  '*' holds both;
- user #1 gets the plan holding '*' once (idempotent); two such plans give none (account_seed_plan_ambiguous);
- MFA follows the resolved capabilities ('*' or admin.access), not the role;
- no plan key appears in apps/edge-bff/app;
- switch off: the access object gains only expired_plan (None) and the header is 'env'.

The catalog tables are not emptied between tests (conftest truncates the accounts only), so a test that changes the
seed puts it back in `finally`.
"""
import ast
import dataclasses
import json
import logging
from pathlib import Path
import re
import time

import psycopg
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from app import principal as principal_module
from app.accounts import AccountStore
from app.main import create_app
from app.principal import Auth, Principal, holds, read_grants, role_needs_mfa, valid_value
from conftest import FakeOrc
from test_edge import ORIGIN, login
from test_principal import db, make_user, sign_in

ROOT = Path(__file__).resolve().parents[3]
APP = Path(__file__).resolve().parents[1] / 'app'
MIGRATION = ROOT / 'database/migrations/20261117_003_edge_bff_accounts_catalog.sql'
HEADER = 'X-Edge-Entitlements'


@pytest.fixture
def on(settings, store):
    return dataclasses.replace(settings, multiuser=True, code_secret='c' * 40, mfa_key='m' * 40)


def subscribe(store, user_id, plan, starts="now() - interval '1 day'", expires='NULL', status='active'):
    db(store, f'''INSERT INTO edge_bff.subscriptions(user_id, plan_key, status, starts_at, expires_at, provider)
        VALUES (%s, %s, %s, {starts}, {expires}, 'test')''', user_id, plan, status)


def principal_of(on, store, owner_key):
    return Auth(on, store).owner_principal(owner_key)


def access(c):
    r = c.get('/api/v1/auth/session')
    assert r.status_code == 200, r.text
    return r.json()['access'], r.headers.get(HEADER)


# ---- resolution ---------------------------------------------------------------------------------------------------

def test_the_default_plan_without_a_subscription(on, store):
    with TestClient(create_app(on, store, FakeOrc())) as c:
        make_user(store, 'alice', 'alice-password')
        sign_in(c, 'alice', 'alice-password')
        got, header = access(c)
        default = db(store, 'SELECT plan_key FROM edge_bff.plans WHERE is_default')[0]['plan_key']
        assert (got['plan'], got['expires_at'], got['expired_plan']) == (default, None, None)
        flags = {r['capability_key'] for r in db(store, '''SELECT pc.capability_key FROM edge_bff.plan_capabilities pc
            JOIN edge_bff.capabilities c USING (capability_key) WHERE plan_key = %s AND kind = 'flag' ''', default)}
        assert set(got['capabilities']) == flags and 'terminal.view' in flags and 'backtest.run' not in flags
        assert got['limits'] == {'terminal.tickers': ['BBCA'], 'terminal.history_days': 730}
        assert header == got['version'] and header.startswith('db-')


def test_a_catalog_only_update_changes_the_next_request_without_restart(on, store):
    default = db(store, 'SELECT plan_key FROM edge_bff.plans WHERE is_default')[0]['plan_key']
    try:
        with TestClient(create_app(on, store, FakeOrc())) as c:
            make_user(store, 'alice', 'alice-password')
            sign_in(c, 'alice', 'alice-password')
            before, header_before = access(c)
            db(store, '''UPDATE edge_bff.plan_capabilities SET value = '365', version = version + 1, updated_at = now()
                WHERE plan_key = %s AND capability_key = 'terminal.history_days' ''', default)
            after, header_after = access(c)
            assert before['limits']['terminal.history_days'] == 730 and after['limits']['terminal.history_days'] == 365
            assert header_after == after['version'] != before['version'] == header_before
            # a version bump alone (the same value) is a change of the fingerprint too
            db(store, '''UPDATE edge_bff.plan_capabilities SET version = version + 1
                WHERE plan_key = %s AND capability_key = 'terminal.history_days' ''', default)
            assert access(c)[1] != header_after
            # a refusal carries the header too, so the page re-reads the session on it
            r = c.get('/api/v1/conversations')
            assert r.headers.get(HEADER, '').startswith('db-')
    finally:
        db(store, '''UPDATE edge_bff.plan_capabilities SET value = '730', version = 1
            WHERE plan_key = %s AND capability_key = 'terminal.history_days' ''', default)


def test_a_subscription_that_expired_a_second_ago_resolves_to_the_default_plan(on, store):
    app = create_app(on, store, FakeOrc())
    auth = app.state.auth

    @app.post('/api/v1/example/run')
    async def run(p: Principal = Depends(auth.need('backtest.run', write=True))):
        return {'ok': True}

    with TestClient(app) as c:
        alice = make_user(store, 'alice', 'alice-password')
        default = db(store, 'SELECT plan_key FROM edge_bff.plans WHERE is_default')[0]['plan_key']
        # the plan that grants backtest.run (found by data, as the code does)
        plan = db(store, '''SELECT plan_key FROM edge_bff.plan_capabilities WHERE capability_key = 'backtest.run' ''')[0]['plan_key']
        h = sign_in(c, 'alice', 'alice-password')
        assert c.post('/api/v1/example/run', headers=h).json()['error']['code'] == 'CAPABILITY_REQUIRED'
        subscribe(store, alice['user_id'], plan, expires="now() + interval '1 second'")
        live, _ = access(c)
        assert live['plan'] == plan and live['expires_at'] and live['expired_plan'] is None
        assert 'backtest.run' in live['capabilities']
        assert c.post('/api/v1/example/run', headers=h).json() == {'ok': True}
        # no cron: the read after the end decides (database time)
        end = db(store, 'SELECT extract(epoch FROM expires_at - now()) AS s FROM edge_bff.subscriptions WHERE user_id = %s',
                 alice['user_id'])[0]['s']
        time.sleep(max(float(end), 0) + 0.05)
        ended, _ = access(c)
        assert (ended['plan'], ended['expires_at'], ended['expired_plan']) == (default, None, plan)
        assert 'backtest.run' not in ended['capabilities'] and ended['version'] != live['version']
        r = c.post('/api/v1/example/run', headers=h)
        assert r.status_code == 403 and r.json()['error']['code'] == 'PLAN_EXPIRED'
        assert r.json()['error']['details'] == {'capability': 'backtest.run', 'display_name': 'backtest.run',
                                                'expired_plan': plan}
        assert 'Renew' in r.json()['error']['message']
        # a capability neither plan held stays CAPABILITY_REQUIRED
        assert principal_of(on, store, alice['owner_key']).refusal('admin.access').code == 'CAPABILITY_REQUIRED'
        # ended a second ago, written directly: the same
        db(store, "UPDATE edge_bff.subscriptions SET expires_at = now() - interval '1 second' WHERE user_id = %s",
           alice['user_id'])
        assert principal_of(on, store, alice['owner_key']).plan_key == default


def test_overrides_replace_the_plan_value_and_an_expired_override_is_ignored(on, store):
    alice = make_user(store, 'alice', 'alice-password')
    p = principal_of(on, store, alice['owner_key'])
    assert p.limit('terminal.history_days') == 730 and not p.can('monitor.chat')

    def override(key, value, expires='NULL'):
        db(store, f'''INSERT INTO edge_bff.user_capability_overrides(user_id, capability_key, value, reason, expires_at)
            VALUES (%s, %s, %s, 'test', {expires}) ON CONFLICT (user_id, capability_key)
            DO UPDATE SET value = EXCLUDED.value, expires_at = EXCLUDED.expires_at''', alice['user_id'], key,
           json.dumps(value))

    override('terminal.history_days', 30)
    override('monitor.chat', True)
    override('terminal.indicator', {'ids': ['I01']})
    p = principal_of(on, store, alice['owner_key'])
    assert p.limit('terminal.history_days') == 30 and p.can('monitor.chat') and p.can('terminal.indicator:I01')
    assert not p.can('terminal.indicator:I02')
    override('terminal.history_days', 30, "now() - interval '1 second'")
    override('monitor.chat', True, "now() - interval '1 second'")
    p2 = principal_of(on, store, alice['owner_key'])
    assert p2.limit('terminal.history_days') == 730 and not p2.can('monitor.chat') and p2.version != p.version
    override('monitor.chat', True, "now() + interval '1 hour'")
    assert principal_of(on, store, alice['owner_key']).can('monitor.chat')


def test_released_versus_lab_items_and_everything(on, store, monkeypatch):
    monkeypatch.setattr(principal_module, 'stage_of',
                        lambda kind, item: 'released' if (kind, item) in {('indicator', 'I01'), ('flow_indicator', 'FL24')} else 'lab')
    released_plan = db(store, '''SELECT plan_key FROM edge_bff.plan_capabilities WHERE capability_key = 'terminal.indicator'
        AND value = '{"stages": ["released"]}' ''')[0]['plan_key']
    everything_plan = db(store, "SELECT plan_key FROM edge_bff.plan_capabilities WHERE capability_key = '*'")[0]['plan_key']
    paid, admin = make_user(store, 'paul', 'paul-password'), make_user(store, 'ada', 'ada-password')
    subscribe(store, paid['user_id'], released_plan)
    subscribe(store, admin['user_id'], everything_plan)
    p, a = principal_of(on, store, paid['owner_key']), principal_of(on, store, admin['owner_key'])
    assert p.can('terminal.indicator:I01') and not p.can('terminal.indicator:I99')           # released held, lab refused
    assert p.can('backtest.flow_indicator:FL24') and not p.can('backtest.flow_indicator:FL99')
    assert p.can('terminal.dataset:anything') and p.can('monitor.model:x/y')                   # {"all": true}
    assert p.limit('watchlist.lists') == 20 and p.limit('watchlist.per_list') == 50 and p.limit('watchlist.indicators') == 8
    assert not p.can('admin.access') and not p.can('backtest.flow_point_in_time') and not p.can('terminal.view:I01')
    assert not p.can('unknown.family:I01') and not p.can('terminal.indicator') and not p.can('terminal.indicator:')
    for key in ('terminal.indicator:I01', 'terminal.indicator:I99', 'admin.access', 'anything.at:all'):
        assert a.can(key)
    assert a.capabilities == frozenset({'*'}) and a.plan_key == everything_plan
    free = principal_of(on, store, make_user(store, 'fred', 'fred-password')['owner_key'])
    assert free.can('terminal.dataset:price') and not free.can('terminal.dataset:broker')
    assert not free.can('terminal.indicator:I01')                                              # {"ids": []}


def test_value_shapes_are_checked_on_read(caplog):
    assert valid_value('flag', True) and not valid_value('flag', 1) and not valid_value('flag', False)
    assert valid_value('limit', 0) and not valid_value('limit', -1) and not valid_value('limit', True)
    assert valid_value('list', ['a']) and not valid_value('list', 'a') and not valid_value('list', [1])
    assert valid_value('items', {}) and valid_value('items', {'ids': ['x'], 'stages': ['released'], 'all': False})
    assert not valid_value('items', {'ids': 'x'}) and not valid_value('items', {'other': []}) \
        and not valid_value('items', {'all': 'yes'})
    with caplog.at_level(logging.WARNING, 'edge_bff.principal'):
        grants, kinds = read_grants({'a.b': {'kind': 'limit', 'value': 'x'}, 'c.d': {'kind': 'flag', 'value': True}})
    assert grants == {'c.d': True} and holds(grants, kinds, 'c.d') and not holds(grants, kinds, 'a.b')
    assert 'capability_value_invalid' in caplog.text


def test_mfa_follows_the_resolved_capabilities_not_the_role(on, store):
    assert role_needs_mfa(frozenset({'*'})) and role_needs_mfa(frozenset({'admin.access'}))
    assert not role_needs_mfa(frozenset({'terminal.view'}))
    with TestClient(create_app(on, store, FakeOrc())) as c:
        make_user(store, 'adm', 'admin-password', role='admin', everything=False)   # role admin, default plan
        sign_in(c, 'adm', 'admin-password')
        got, _ = access(c)
        assert got['mfa_ok'] is True and got['next'] is None and '*' not in got['capabilities']
        bob = make_user(store, 'bob', 'bob-password')
        db(store, '''INSERT INTO edge_bff.user_capability_overrides(user_id, capability_key, value, reason)
            VALUES (%s, 'admin.access', 'true', 'test')''', bob['user_id'])
        r = c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'bob', 'password': 'bob-password'})
        assert r.status_code == 403 and r.json()['error']['code'] == 'MFA_REQUIRED'


# ---- user #1 ------------------------------------------------------------------------------------------------------

def test_the_seed_subscription_is_idempotent(on, store):
    for _ in range(2):
        with TestClient(create_app(on, store, FakeOrc())) as c:
            pass
    rows = db(store, '''SELECT s.plan_key, s.status, s.expires_at, s.provider, u.owner_key FROM edge_bff.subscriptions s
        JOIN edge_bff.users u USING (user_id)''')
    everything_plan = db(store, "SELECT plan_key FROM edge_bff.plan_capabilities WHERE capability_key = '*'")[0]['plan_key']
    assert rows == [{'plan_key': everything_plan, 'status': 'active', 'expires_at': None, 'provider': 'manual',
                     'owner_key': on.owner}]
    seed_id = db(store, 'SELECT user_id FROM edge_bff.users WHERE owner_key = %s', on.owner)[0]['user_id']
    assert AccountStore(store).seed_subscription(seed_id) == everything_plan
    assert db(store, 'SELECT count(*) AS n FROM edge_bff.subscriptions')[0]['n'] == 1
    with TestClient(create_app(on, store, FakeOrc())) as c:
        sign_in(c, 'owner', 'local-test-password')
        got, _ = access(c)
        assert got['capabilities'] == ['*'] and got['plan'] == everything_plan and got['mfa_ok'] is False
        assert got['seed'] is True


def test_the_seed_subscription_refuses_an_ambiguous_plan(on, store, caplog):
    other = db(store, "SELECT plan_key FROM edge_bff.plans WHERE plan_key NOT IN (SELECT plan_key FROM edge_bff.plan_capabilities WHERE capability_key = '*') ORDER BY plan_key LIMIT 1")[0]['plan_key']
    db(store, "INSERT INTO edge_bff.plan_capabilities(plan_key, capability_key, value) VALUES (%s, '*', 'true')", other)
    try:
        with caplog.at_level(logging.WARNING, 'edge_bff.accounts'):
            with TestClient(create_app(on, store, FakeOrc())):
                pass
        assert 'account_seed_plan_ambiguous' in caplog.text
        assert db(store, 'SELECT count(*) AS n FROM edge_bff.subscriptions')[0]['n'] == 0
        assert db(store, 'SELECT count(*) AS n FROM edge_bff.users')[0]['n'] == 1     # the seed user itself is made
    finally:
        db(store, "DELETE FROM edge_bff.plan_capabilities WHERE plan_key = %s AND capability_key = '*'", other)
    # no plan holding '*' is the same refusal
    held = db(store, "DELETE FROM edge_bff.plan_capabilities WHERE capability_key = '*' RETURNING plan_key")[0]['plan_key']
    try:
        caplog.clear()
        with caplog.at_level(logging.WARNING, 'edge_bff.accounts'):
            seed_id = db(store, 'SELECT user_id FROM edge_bff.users')[0]['user_id']
            assert AccountStore(store).seed_subscription(seed_id) is None
        assert 'account_seed_plan_ambiguous' in caplog.text
    finally:
        db(store, "INSERT INTO edge_bff.plan_capabilities(plan_key, capability_key, value) VALUES (%s, '*', 'true')", held)


# ---- switch off ---------------------------------------------------------------------------------------------------

def test_switch_off_access_gains_only_expired_plan_and_the_header_is_env(settings, store):
    with TestClient(create_app(dataclasses.replace(settings, admin_owners=(settings.owner,)), store, FakeOrc())) as c:
        login(c)
        got, header = access(c)
        assert got == {'plan': None, 'role': 'admin', 'status': 'active', 'expires_at': None, 'mfa_ok': True,
                       'capabilities': ['*'], 'limits': {}, 'version': 'env', 'next': None, 'owner_key': settings.owner,
                       'mfa_enrolled': False, 'seed': True, 'expired_plan': None}
        assert header == 'env'
        assert c.get('/api/v1/conversations').headers[HEADER] == 'env'
        # a subscription row changes nothing with the switch off
        seed_id = db(store, 'SELECT user_id FROM edge_bff.users')[0]['user_id']
        assert db(store, 'SELECT count(*) AS n FROM edge_bff.subscriptions WHERE user_id = %s', seed_id)[0]['n'] == 1
        assert access(c)[0] == got
        # no header on an answer without a principal
        assert HEADER not in c.get('/health').headers
        assert HEADER not in c.post('/api/v1/auth/sign-in', headers=ORIGIN,
                                    json={'login': 'owner', 'password': 'wrong'}).headers


# ---- the migration ------------------------------------------------------------------------------------------------

def test_the_catalog_migration_refuses_a_second_run(database):
    with psycopg.connect(database, autocommit=True) as conn:
        with pytest.raises(psycopg.errors.RaiseException, match='reconcile before applying'):
            conn.execute(MIGRATION.read_text())


def test_the_runtime_role_reads_the_catalog_and_never_deletes_a_subscription(store, settings):
    user = make_user(store, 'alice', 'alice-password')
    with store.connect() as c:
        c.execute('SET LOCAL ROLE edge_bff_runtime')
        assert c.execute('SELECT count(*) AS n FROM edge_bff.plan_capabilities').fetchone()['n'] > 0
        c.execute('''INSERT INTO edge_bff.subscriptions(user_id, plan_key, status, provider)
            SELECT %s, plan_key, 'active', 'manual' FROM edge_bff.plans WHERE is_default''', (user['user_id'],))
        c.execute("UPDATE edge_bff.subscriptions SET status = 'cancelled' WHERE user_id = %s", (user['user_id'],))
        c.execute('''INSERT INTO edge_bff.user_capability_overrides(user_id, capability_key, value, reason)
            VALUES (%s, 'monitor.chat', 'true', 'test')''', (user['user_id'],))
    for sql in ("UPDATE edge_bff.plan_capabilities SET value = 'true' WHERE capability_key = %s",
                'DELETE FROM edge_bff.subscriptions WHERE provider_ref = %s',
                'DELETE FROM edge_bff.user_capability_overrides WHERE reason = %s',
                "INSERT INTO edge_bff.plans(plan_key, display_name) VALUES (%s, 'X')",
                'TRUNCATE edge_bff.capabilities'):
        with store.connect() as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute('SET LOCAL ROLE edge_bff_runtime')
            c.execute(sql, ('x',) if '%s' in sql else None)
    with store.connect() as c, pytest.raises(psycopg.errors.UniqueViolation):       # one active subscription per user
        for _ in range(2):
            c.execute('''INSERT INTO edge_bff.subscriptions(user_id, plan_key, status, provider)
                SELECT %s, plan_key, 'active', 'manual' FROM edge_bff.plans WHERE is_default''', (user['user_id'],))
    with store.connect() as c, pytest.raises(psycopg.errors.UniqueViolation):       # one default plan
        c.execute("INSERT INTO edge_bff.plans(plan_key, display_name, is_default) VALUES ('second', 'Second', true)")


def test_every_seed_capability_has_a_plain_meaning(store):
    rows = db(store, 'SELECT capability_key, kind, means, display_name FROM edge_bff.capabilities')
    assert len(rows) == 41
    for r in rows:
        assert len(r['means']) >= 20 and r['means'].endswith('.') and not re.search(r'[A-Z]{2,}_', r['means']), r


# ---- no plan key in code ------------------------------------------------------------------------------------------

def plan_keys():
    """The plan keys of the seed, read from the migration (the only place they may appear)."""
    block = re.search(r'INSERT INTO edge_bff\.plans\(plan_key, display_name, is_default\) VALUES(.*?);',
                      MIGRATION.read_text(), re.S).group(1)
    return set(re.findall(r"\('([a-z][a-z0-9_]*)',", block))


def role_names():
    """The account roles (edge_bff.users.role CHECK): a role may share its word with a plan key ('admin')."""
    text = (ROOT / 'database/migrations/20261116_003_edge_bff_accounts_users.sql').read_text()
    return set(re.findall(r"'([a-z]+)'", re.search(r'role text NOT NULL[^\n]*', text).group(0)))


def plan_key_uses(source, keys, roles):
    """Where a source uses a plan key as a plan. The rule:
    - a plan key that is not also a role name ('paid', 'free') may not appear as a string literal at all, nor quoted
      inside one (SQL);
    - a plan key that is also a role name ('admin': the role, and the prefix of capabilities such as admin.access, which
      are different literals) is a plan use when it is compared with, assigned to, passed as or keyed by something whose
      text names a plan (plan, plan_key, expired_plan, ...), or quoted inside a literal that mentions plan (SQL such as
      "WHERE plan_key = 'admin'"). The role literal role='admin' and the capability 'admin.access' are not uses."""
    found = []
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            s = node.value
            if s in keys - roles:
                found.append((node.lineno, s))
            for key in keys:
                if re.search(rf"'{re.escape(key)}'", s) and (key not in roles or 'plan' in s.lower()):
                    found.append((node.lineno, s[:60]))
        pairs = []
        if isinstance(node, ast.Compare):
            sides = [node.left, *node.comparators]
            pairs += [(a, b) for a in sides for b in sides if a is not b]
        elif isinstance(node, ast.keyword) and node.arg:
            pairs.append((ast.Name(id=node.arg), node.value))
        elif isinstance(node, ast.Assign):
            pairs += [(t, node.value) for t in node.targets]
        elif isinstance(node, ast.Dict):
            pairs += [(k, v) for k, v in zip(node.keys, node.values) if k is not None]
        elif isinstance(node, ast.Subscript):
            pairs.append((node.value, node.slice))
        for named, value in pairs:
            if isinstance(value, ast.Constant) and value.value in keys and 'plan' in ast.unparse(named).lower():
                found.append((value.lineno, ast.unparse(named)))
    return found


def test_the_rule_catches_a_planted_plan_key():
    keys, roles = {'admin', 'paid', 'free'}, {'admin', 'user'}
    assert plan_key_uses("x = 'paid'", keys, roles)
    assert plan_key_uses("if p.plan_key == 'admin': pass", keys, roles)
    assert plan_key_uses("f(plan='admin')", keys, roles)
    assert plan_key_uses("d = {'plan': 'admin'}", keys, roles)
    assert plan_key_uses('q = "SELECT 1 FROM edge_bff.plans WHERE plan_key = \'admin\'"', keys, roles)
    assert plan_key_uses('q = "WHERE x = \'free\'"', keys, roles)
    assert not plan_key_uses("p = P(role='admin' if a else 'user')", keys, roles)
    assert not plan_key_uses("need('admin.access'); r = {'role': 'admin'}", keys, roles)
    assert not plan_key_uses("# free it for the next job\nx = 1", keys, roles)


def test_no_plan_key_in_edge_bff_app():
    """CONTRACT.md section 0 and 8a: plan keys are data (the catalog seed migration), never code."""
    keys, roles = plan_keys(), role_names()
    assert keys == {'admin', 'paid', 'free'} and 'admin' in roles
    found = {path.name: uses for path in sorted(APP.rglob('*.py'))
             if (uses := plan_key_uses(path.read_text(), keys, roles))}
    assert found == {}
