"""C-DB re-check of EXEC-MU-ACCOUNTS Phases 0-3b (2026-11-18, lens: migrations, grants, records, CI). Failing tests of
verified findings; the fix round makes them pass.

1. Column privileges slip past every grant guard. The migrations' $verify$ blocks, scripts/provision_edge_bff_login.py
   and the apply jobs' runtime_grants/login_grants probes all ask has_table_privilege, which is false for a privilege
   held on columns only. A column grant therefore lets the runtime rewrite the audit (no UPDATE on admin_audit, CONTRACT
   section 1) or read a market table, while the provisioning script still prints "only the N operational tables
   reachable".
2. plan_capabilities keeps no trace of a change: an UPDATE of a plan's value (the "catalog-only change" of CONTRACT 8a,
   made by an operator) leaves updated_at and version as they were, so the table cannot tell when or whether a grant
   changed.
"""
import importlib.util
import secrets
from pathlib import Path

import psycopg
import pytest

ROOT = Path(__file__).resolve().parents[3]


def provisioning():
    spec = importlib.util.spec_from_file_location('edge_provision_cdb', ROOT / 'scripts/provision_edge_bff_login.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def drop_login(database):
    with psycopg.connect(database, autocommit=True) as conn:
        conn.execute("""DO $$BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'edge_bff_login') THEN
            DROP OWNED BY edge_bff_login; DROP ROLE edge_bff_login; END IF; END$$""")


@pytest.mark.parametrize('grant, revoke', [
    # the audit is read and added to only (20261116_003; CONTRACT section 1 "no UPDATE or DELETE grant")
    ('GRANT UPDATE (reason) ON edge_bff.admin_audit TO edge_bff_runtime',
     'REVOKE UPDATE (reason) ON edge_bff.admin_audit FROM edge_bff_runtime'),
    # a market table is never reachable from the EDGE login (test_edge.py's public.market_private)
    ('GRANT SELECT (secret) ON public.market_private TO edge_bff_runtime',
     'REVOKE SELECT (secret) ON public.market_private FROM edge_bff_runtime'),
])
def test_provisioning_refuses_a_privilege_held_on_columns_only(database, monkeypatch, grant, revoke):
    module = provisioning()
    monkeypatch.setenv('DATABASE_URL', database)
    monkeypatch.setenv('EDGE_DB_PASSWORD', secrets.token_hex(24))
    with psycopg.connect(database, autocommit=True) as conn:
        conn.execute(grant)
        # the privilege is real: has_any_column_privilege sees it, has_table_privilege (every guard's check) does not
        role, table, privilege = ('edge_bff_runtime', grant.split(' ON ')[1].split(' TO ')[0], grant.split()[1])
        assert conn.execute('SELECT has_any_column_privilege(%s, %s, %s)', (role, table, privilege)).fetchone()[0]
        assert not conn.execute('SELECT has_table_privilege(%s, %s, %s)', (role, table, privilege)).fetchone()[0]
    try:
        with pytest.raises(RuntimeError, match='Unexpected EDGE|unexpected reachable'):
            module.main()
    finally:
        with psycopg.connect(database, autocommit=True) as conn:
            conn.execute(revoke)
        drop_login(database)


def test_the_migration_verify_block_refuses_an_audit_column_update(database):
    """20261116_003's own $verify$ block, run again on the migrated database with a column UPDATE on the audit."""
    text = (ROOT / 'database/migrations/20261116_003_edge_bff_accounts_users.sql').read_text()
    block = text[text.index('DO $verify$'):text.index('END $verify$;') + len('END $verify$;')]
    with psycopg.connect(database, autocommit=True) as conn:
        conn.execute('TRUNCATE edge_bff.users CASCADE')
        conn.execute('GRANT UPDATE (reason) ON edge_bff.admin_audit TO edge_bff_runtime')
        try:
            with pytest.raises(psycopg.errors.RaiseException):
                conn.execute(block)
        finally:
            conn.execute('REVOKE UPDATE (reason) ON edge_bff.admin_audit FROM edge_bff_runtime')


def test_a_changed_plan_value_leaves_a_trace(database):
    """An operator's UPDATE of a plan grant (CONTRACT 8a: a catalog-only change takes effect with no deploy) must move
    updated_at, and version (the column the X-Edge-Entitlements fingerprint names), so the change can be found."""
    with psycopg.connect(database, autocommit=True) as conn:
        before = conn.execute("""SELECT value, version, updated_at FROM edge_bff.plan_capabilities
            WHERE plan_key = 'free' AND capability_key = 'terminal.history_days'""").fetchone()
        conn.execute("""UPDATE edge_bff.plan_capabilities SET value = '365'
            WHERE plan_key = 'free' AND capability_key = 'terminal.history_days'""")
        try:
            after = conn.execute("""SELECT value, version, updated_at FROM edge_bff.plan_capabilities
                WHERE plan_key = 'free' AND capability_key = 'terminal.history_days'""").fetchone()
            assert after[0] == 365
            assert after[2] > before[2], 'plan_capabilities.updated_at did not move with the change'
            assert after[1] > before[1], 'plan_capabilities.version did not rise with the change'
        finally:
            conn.execute("""UPDATE edge_bff.plan_capabilities SET value = %s::jsonb, version = %s, updated_at = %s
                WHERE plan_key = 'free' AND capability_key = 'terminal.history_days'""",
                         (str(before[0]), before[1], before[2]))
