"""Checker C1 (security), EDGE multi-user Phase 2 (CONTRACT.md 8a "Value shapes" and "Resolution").

A limit or list is a restriction: "No row = no limit" (8a). A row that exists but holds a value of the wrong shape is
"ignored and logged" (principal.py read_grants), so the key disappears from the principal and p.limit() answers None,
which every caller reads as "no limit". A typo in one catalog row or override therefore widens access instead of
narrowing it: a free account with terminal.tickers ["BBCA"] gets every ticker, terminal.history_days 730 becomes
unlimited history. Flags and items fail closed (a malformed value grants nothing); limits and lists must fail closed
too (the plan's own value, or nothing allowed), never open.

These tests fail on 8a55980b (principal.py:73-83 read_grants, 189 limits; accounts.py GRANTS `merged`).

Fix round (main agent): the migration now refuses such values when they are written (capability_value_check,
tests/test_phase2_fix_round.py), and read_grants reads a wrong shape as the most restrictive value. The values below are
written past the write-time check (`unchecked`) so these tests keep testing the read-time defence on its own (defence
in depth; a change of a capability's kind while values of it exist is refused too, capabilities_kind_fixed); the
assertions are as the checker wrote them.
"""
import dataclasses

import pytest

from app.principal import Auth
from test_principal import db, make_user


@pytest.fixture
def on(settings, store):
    return dataclasses.replace(settings, multiuser=True, code_secret='c' * 40, mfa_key='m' * 40)


def unchecked(store, sql, *args):
    """A write past the write-time value check (the triggers do not fire for this transaction; superuser test DB)."""
    with store.connect() as c:
        c.execute('SET LOCAL session_replication_role = replica')
        c.execute(sql, args)


def default_plan(store):
    return db(store, 'SELECT plan_key FROM edge_bff.plans WHERE is_default')[0]['plan_key']


@pytest.mark.parametrize('value', ['"BBCA"', '[1]', 'null', '{"ids": ["BBCA"]}', '["BBCA", 2]'])
def test_a_malformed_list_override_never_lifts_the_restriction(on, store, value):
    alice = make_user(store, 'alice', 'alice-password')
    auth = Auth(on, store)
    before = auth.owner_principal(alice['owner_key']).limit('terminal.tickers')
    assert before == ['BBCA']
    unchecked(store, '''INSERT INTO edge_bff.user_capability_overrides(user_id, capability_key, value, reason)
        VALUES (%s, 'terminal.tickers', %s::jsonb, 'typo')''', alice['user_id'], value)
    after = auth.owner_principal(alice['owner_key']).limit('terminal.tickers')
    # None means "every ticker" to every reader of p.limit (and to the page's limit(), shared/edge-session.ts)
    assert isinstance(after, list) and set(after) <= {'BBCA'}, f'override {value} lifted the ticker list: {after!r}'


@pytest.mark.parametrize('value', ['-1', '730.5', '"730"', 'true', 'null'])
def test_a_malformed_plan_limit_never_becomes_no_limit(on, store, value):
    plan = default_plan(store)
    try:
        unchecked(store, '''UPDATE edge_bff.plan_capabilities SET value = %s::jsonb
            WHERE plan_key = %s AND capability_key = 'terminal.history_days' ''', value, plan)
        alice = make_user(store, 'alice', 'alice-password')
        got = Auth(on, store).owner_principal(alice['owner_key']).limit('terminal.history_days')
        assert isinstance(got, int) and 0 <= got <= 730, f'plan value {value} gave history_days {got!r} (no limit)'
    finally:
        db(store, '''UPDATE edge_bff.plan_capabilities SET value = '730'
            WHERE plan_key = %s AND capability_key = 'terminal.history_days' ''', plan)
