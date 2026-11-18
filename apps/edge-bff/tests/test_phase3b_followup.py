"""EXEC-MU-ACCOUNTS Phase 3b follow-up (CONTRACT.md 8b "3b follow-up"; user decision 2026-11-18, O3b-1: "Pokoknya
gate-nya adalah terminal"): migration 20261118_001 removes the four tab families of the indicator and Flow kinds, so
the Terminal's grants decide the Backtest and Screener items (app/allow.py FAMILIES).

- the migration refuses a second run, and refuses (naming the count and how to fix it) when an override names a removed
  family, which would be lost; without one it applies and leaves what the conftest database holds;
- the paid plan keeps terminal.indicator and terminal.flow_indicator at {"stages": ["released"]}, so a paid account's
  Backtest and Screener get every released item, the broker-data built-ins (broker, top5) included;
- an override of the Terminal's family reaches both workers' allow.
"""
from pathlib import Path

import psycopg
import pytest

from app import releases
from app.allow import allow_of
from test_phase3a_gates import override, paid_plan, paid_user
from test_plan_catalog import principal_of
from test_principal import db, make_user, on, workers  # noqa: F401 - the fixtures

ROOT = Path(__file__).resolve().parents[3]
MIGRATION = ROOT / 'database/migrations/20261118_001_edge_bff_item_families_from_terminal.sql'
REMOVED = ('backtest.indicator', 'backtest.flow_indicator', 'screener.indicator', 'screener.flow_indicator')


def test_the_migration_refuses_a_second_run(database):
    with psycopg.connect(database, autocommit=True) as conn:
        with pytest.raises(psycopg.errors.RaiseException, match='ran already'):
            conn.execute(MIGRATION.read_text())


def test_an_override_of_a_removed_family_is_reported_and_refused_then_the_migration_applies(database, store):
    user, plan = make_user(store, 'followup', 'followup-password'), paid_plan(store)
    with psycopg.connect(database, autocommit=True) as conn:
        before = conn.execute('SELECT count(*) FROM edge_bff.capabilities').fetchone()[0]   # with every later migration
        # the catalog as before 20261118_001: the four rows, the paid plan's grants and one user's override
        conn.execute('''INSERT INTO edge_bff.capabilities(capability_key, kind, unit, means, display_name)
            SELECT k, 'items', NULL, 'A test row of a removed family, restored by this test.', k
            FROM unnest(%s::text[]) AS k''', (list(REMOVED),))
        conn.execute('''INSERT INTO edge_bff.plan_capabilities(plan_key, capability_key, value)
            SELECT %s, k, '{"stages": ["released"]}' FROM unnest(%s::text[]) AS k''', (plan, list(REMOVED)))
        conn.execute('''INSERT INTO edge_bff.user_capability_overrides(user_id, capability_key, value, reason)
            VALUES (%s, 'screener.flow_indicator', '{"ids": ["FL11"]}', 'followup test')''', (user['user_id'],))
        notices = []
        conn.add_notice_handler(lambda n: notices.append(n.message_primary))
        with pytest.raises(psycopg.errors.RaiseException, match='1 user override') as caught:
            conn.execute(MIGRATION.read_text())
        assert 'Move each to terminal.indicator or terminal.flow_indicator first' in str(caught.value)
        assert 'user_capability_overrides rows of the removed families: 1' in notices
        conn.execute('ROLLBACK')                                  # the migration's own transaction, ended by the error
        assert conn.execute('SELECT count(*) FROM edge_bff.capabilities WHERE capability_key = ANY(%s)',
                            (list(REMOVED),)).fetchone()[0] == 4  # nothing was removed
        # without the override it applies: the database is as the conftest left it
        conn.execute("DELETE FROM edge_bff.user_capability_overrides WHERE reason = 'followup test'")
        conn.execute(MIGRATION.read_text())
        assert conn.execute('SELECT count(*) FROM edge_bff.capabilities').fetchone()[0] == before
        for table in ('capabilities', 'plan_capabilities', 'user_capability_overrides'):
            assert conn.execute(f'SELECT count(*) FROM edge_bff.{table} WHERE capability_key = ANY(%s)',
                                (list(REMOVED),)).fetchone()[0] == 0, table


def test_the_paid_plan_holds_the_terminal_families_and_both_workers_read_them(on, store):
    rows = {r['capability_key']: r['value'] for r in db(store, '''SELECT capability_key, value FROM edge_bff.plan_capabilities
        WHERE plan_key = %s''', paid_plan(store))}
    assert rows['terminal.indicator'] == rows['terminal.flow_indicator'] == {'stages': ['released']}
    assert not set(REMOVED) & set(rows)
    means = {r['capability_key']: r['means'] for r in db(store, '''SELECT capability_key, means FROM edge_bff.capabilities
        WHERE capability_key IN ('terminal.indicator', 'terminal.flow_indicator')''')}
    assert all('Backtest and the Screener' in m for m in means.values()), means
    alice = paid_user(store, 'alice')
    p = principal_of(on, store, alice['owner_key'])
    released = {k: sorted(e['id'] for e in releases.entries(k) if e['stage'] == 'released') for k in ('indicator', 'flow_indicator')}
    for worker in ('backtest', 'screener'):
        a = allow_of(p, worker)
        assert a['indicator'] == released['indicator'] and a['flow_indicator'] == released['flow_indicator']
        assert {'fnet', 'broker', 'top5'} <= set(a['flow_indicator'])
    # the Terminal's grant narrowed for this account: both workers follow it
    override(store, alice['user_id'], 'terminal.flow_indicator', '{"ids": ["fnet"]}')
    p = principal_of(on, store, alice['owner_key'])
    assert allow_of(p, 'backtest')['flow_indicator'] == allow_of(p, 'screener')['flow_indicator'] == ['fnet']
