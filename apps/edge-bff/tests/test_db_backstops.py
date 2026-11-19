"""EXEC-MU-ACCOUNTS fix round (records track): the database backstops behind the application's own checks.

Each test writes past the application, so it fails when the constraint itself is dropped or loosened even while the
application's check still holds (re-check R1-46: three such constraints passed the whole suite when replaced by no-ops):
- users_registration_pending (20261117_002): a registration token only on a pending account;
- the email-code tries cap (20261116_003: attempts BETWEEN 0 AND 5);
- users_one_seed (20261116_003): at most one account with a key edge-bff did not generate, even when the owner-key
  trigger does not run (session_replication_role = replica, as tests/test_c1_phase2_fail_closed.py bypasses triggers).
And the rules of migration 20261119_040 (re-check R1-42, R1-43): audit and provenance user ids survive the deletion of
their account, and a change of a plan grant or an override leaves its trace (version, updated_at).
"""
import secrets

import psycopg
import pytest

from app.accounts import new_owner_key
from test_principal import make_user


def pending_user(c, registration_hash=None):
    return c.execute('''INSERT INTO edge_bff.users(owner_key, email, requested_username, status, registration_hash)
        VALUES (%s, %s, %s, 'pending', %s) RETURNING user_id''',
                     (new_owner_key(), f'p{secrets.token_hex(4)}@example.com', 'pending_' + secrets.token_hex(3),
                      registration_hash)).fetchone()['user_id']


def test_a_registration_token_stays_only_on_a_pending_account(store):
    with store.connect() as c:
        user = pending_user(c, secrets.token_hex(32))
    with pytest.raises(psycopg.errors.CheckViolation, match='users_registration_pending'):
        with store.connect() as c:
            c.execute('''UPDATE edge_bff.users SET status = 'active', username = 'now_active', email_verified_at = now()
                WHERE user_id = %s''', (user,))


def test_an_email_code_takes_at_most_five_tries(store):
    with store.connect() as c:
        user = pending_user(c)
        code = c.execute('''INSERT INTO edge_bff.email_codes(purpose, user_id, code_hash, created_at, expires_at)
            VALUES ('register', %s, %s, now(), now() + interval '300 seconds') RETURNING code_id''',
                         (user, secrets.token_hex(32))).fetchone()['code_id']
        c.execute('UPDATE edge_bff.email_codes SET attempts = 5 WHERE code_id = %s', (code,))
    with pytest.raises(psycopg.errors.CheckViolation, match='attempts'):
        with store.connect() as c:
            c.execute('UPDATE edge_bff.email_codes SET attempts = 6 WHERE code_id = %s', (code,))


def test_one_seed_row_at_most_even_past_the_owner_key_trigger(store):
    with store.connect() as c:
        c.execute('SET LOCAL session_replication_role = replica')
        c.execute("INSERT INTO edge_bff.users(owner_key, username, status) VALUES ('seed-one', 'seed_one', 'active')")
    try:
        with pytest.raises(psycopg.errors.UniqueViolation, match='users_one_seed'):
            with store.connect() as c:
                c.execute('SET LOCAL session_replication_role = replica')
                c.execute("INSERT INTO edge_bff.users(owner_key, username, status) VALUES ('seed-two', 'seed_two', 'active')")
    finally:
        with store.connect() as c:
            c.execute("DELETE FROM edge_bff.users WHERE owner_key IN ('seed-one', 'seed-two')")


def test_an_admins_deletion_never_rewrites_what_the_audit_and_the_overrides_say_it_did(store):
    """R1-42's class: every provenance or audit column naming a user keeps its id when that account is deleted."""
    admin = make_user(store, 'adminone', 'adminone-password', role='admin')
    alice = make_user(store, 'alice', 'alice-password')
    with store.connect() as c:
        audit = c.execute('''INSERT INTO edge_bff.admin_audit(actor_user_id, action, target_user_id, reason)
            VALUES (%s, 'user.plan', %s, 'by phone') RETURNING audit_id''',
                          (admin['user_id'], alice['user_id'])).fetchone()['audit_id']
        c.execute('''INSERT INTO edge_bff.user_capability_overrides(user_id, capability_key, value, reason,
            created_by_user_id) VALUES (%s, 'terminal.history_days', '30', 'trial', %s)''',
                  (alice['user_id'], admin['user_id']))
        c.execute('DELETE FROM edge_bff.users WHERE user_id = %s', (admin['user_id'],))
    with store.connect() as c:
        row = c.execute('SELECT actor_user_id, target_user_id FROM edge_bff.admin_audit WHERE audit_id = %s',
                        (audit,)).fetchone()
        made_by = c.execute('''SELECT created_by_user_id FROM edge_bff.user_capability_overrides WHERE user_id = %s
            AND capability_key = 'terminal.history_days' ''', (alice['user_id'],)).fetchone()['created_by_user_id']
    assert (row['actor_user_id'], row['target_user_id'], made_by) == (admin['user_id'], alice['user_id'], admin['user_id'])


def test_no_audit_or_provenance_column_references_the_users_with_a_referential_action(database):
    """Derived from the catalog, not listed: a foreign key to edge_bff.users from a column named *_by_user_id,
    actor_user_id or target_user_id (who did something, or to whom) is the class R1-42 removed."""
    with psycopg.connect(database) as c:
        rows = c.execute('''SELECT c.relname, a.attname, k.confdeltype FROM pg_constraint k
            JOIN pg_class c ON c.oid = k.conrelid JOIN pg_attribute a ON a.attrelid = k.conrelid AND a.attnum = ANY (k.conkey)
            WHERE k.contype = 'f' AND k.confrelid = 'edge_bff.users'::regclass
              AND (a.attname ~ '_by_user_id$' OR a.attname IN ('actor_user_id', 'target_user_id'))''').fetchall()
    assert rows == [], f'{rows}: keep the user id as a plain number (migration 20261119_040, CONTRACT section 1)'


def test_an_override_change_sets_updated_at_and_a_plan_change_raises_version_once(store):
    alice = make_user(store, 'alice', 'alice-password')
    with store.connect() as c:
        c.execute('''INSERT INTO edge_bff.user_capability_overrides(user_id, capability_key, value, reason)
            VALUES (%s, 'terminal.history_days', '30', 'trial')''', (alice['user_id'],))
    with store.connect() as c:
        assert c.execute('SELECT updated_at FROM edge_bff.user_capability_overrides WHERE user_id = %s',
                         (alice['user_id'],)).fetchone()['updated_at'] is None
        c.execute("UPDATE edge_bff.user_capability_overrides SET value = '60' WHERE user_id = %s", (alice['user_id'],))
    with store.connect() as c:
        assert c.execute('SELECT updated_at FROM edge_bff.user_capability_overrides WHERE user_id = %s',
                         (alice['user_id'],)).fetchone()['updated_at'] is not None
        key = ('free', 'terminal.history_days')
        before = c.execute('''SELECT value, version FROM edge_bff.plan_capabilities WHERE plan_key = %s
            AND capability_key = %s''', key).fetchone()
        # an UPDATE that does not change the value leaves the version alone
        c.execute('UPDATE edge_bff.plan_capabilities SET value = value WHERE plan_key = %s AND capability_key = %s', key)
        same = c.execute('SELECT version FROM edge_bff.plan_capabilities WHERE plan_key = %s AND capability_key = %s',
                         key).fetchone()['version']
        c.execute('''UPDATE edge_bff.plan_capabilities SET value = '100' WHERE plan_key = %s AND capability_key = %s''',
                  key)
        raised = c.execute('SELECT version FROM edge_bff.plan_capabilities WHERE plan_key = %s AND capability_key = %s',
                           key).fetchone()['version']
        c.execute('UPDATE edge_bff.plan_capabilities SET value = %s::jsonb WHERE plan_key = %s AND capability_key = %s',
                  (str(before['value']), *key))
    assert (same, raised) == (before['version'], before['version'] + 1)
