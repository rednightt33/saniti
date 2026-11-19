"""EXEC-MU-ACCOUNTS fix round, track plans (re-check R1-36; user decision 2026-11-19 "2a", EXEC.md "Decisions from the
fix round" item 1): a plan or an override that limits the Terminal's tickers, data sets or history may not also hold the
Backtest's or the Screener's own data access, since their workers read every stock. Enforced by the plan catalog
(migration 20261119_030, edge_bff.data_scope_guard: SQLSTATE 23514, CONSTRAINT terminal_limit_with_every_stock); the
free plan's example flags stay allowed."""
import threading
import time
from pathlib import Path

import psycopg
import pytest

from test_principal import db, make_user
from test_phase3a_gates import override, paid_plan, subscribe

MIGRATION = Path(__file__).resolve().parents[3] / 'database/migrations/20261119_030_edge_bff_plan_data_scope.sql'
CONSTRAINT = 'terminal_limit_with_every_stock'
TERMINAL_LIMITS = ['terminal.dataset', 'terminal.history_days', 'terminal.tickers']
EVERY_STOCK = ['backtest.run', 'backtest.view', 'screener.run', 'screener.view']


def default_plan(store):
    return db(store, 'SELECT plan_key FROM edge_bff.plans WHERE is_default')[0]['plan_key']


def refused(fn, *names):
    """The write is refused by the rule, and its message names every given plan, account and key."""
    with pytest.raises(psycopg.errors.CheckViolation) as e:
        fn()
    assert e.value.diag.constraint_name == CONSTRAINT, e.value
    text = str(e.value)
    for name in names:
        assert name in text, (name, text)
    assert 'read every stock' in (e.value.diag.message_hint or '')
    return text


def test_the_marks_come_from_the_catalog_and_the_seed_plans_hold_no_clash(store):
    rows = db(store, 'SELECT capability_key, data_scope FROM edge_bff.capabilities WHERE data_scope IS NOT NULL')
    assert {r['capability_key']: r['data_scope'] for r in rows} == {
        **{k: 'terminal_limit' for k in TERMINAL_LIMITS}, **{k: 'every_stock' for k in EVERY_STOCK}}
    assert db(store, 'SELECT * FROM edge_bff.data_scope_conflicts(NULL, NULL)') == []
    # the free plan limits the Terminal and keeps the example of every other tab (its rows, read from the catalog)
    free = {r['capability_key']: r['value'] for r in db(store, '''SELECT capability_key, value
        FROM edge_bff.plan_capabilities WHERE plan_key = %s''', default_plan(store))}
    assert set(TERMINAL_LIMITS) <= set(free) and free['backtest.example'] is True and free['screener.example'] is True
    # the Terminal quotas (rate limits) are not limits of which stocks: the paid plan holds them beside the Backtest
    assert db(store, '''SELECT count(*) AS n FROM edge_bff.plan_capabilities WHERE plan_key = %s
        AND capability_key LIKE 'terminal.%%_per_%%' ''', paid_plan(store))[0]['n'] == 4


@pytest.mark.parametrize('key', EVERY_STOCK)
def test_a_plan_that_limits_the_terminal_is_refused_the_backtest_and_the_screener(store, key):
    free = default_plan(store)
    refused(lambda: db(store, '''INSERT INTO edge_bff.plan_capabilities(plan_key, capability_key, value)
        VALUES (%s, %s, 'true')''', free, key), f'plan {free}', key, 'terminal.tickers')
    assert not db(store, 'SELECT 1 FROM edge_bff.plan_capabilities WHERE plan_key = %s AND capability_key = %s', free, key)
    # false grants nothing: refused by no rule (an override may take a flag away)
    assert db(store, 'SELECT edge_bff.data_scope_conflict(%s, NULL) AS f', free)[0]['f'] is None


@pytest.mark.parametrize('key,value', [('terminal.tickers', '["BBCA"]'), ('terminal.history_days', '730'),
                                       ('terminal.dataset', '{"ids": ["price"]}'), ('terminal.dataset', '{"stages": ["released"]}')])
def test_a_plan_that_opens_the_backtest_is_refused_a_terminal_limit(store, key, value):
    paid = paid_plan(store)
    refused(lambda: db(store, '''INSERT INTO edge_bff.plan_capabilities(plan_key, capability_key, value)
        VALUES (%s, %s, %s::jsonb) ON CONFLICT (plan_key, capability_key) DO UPDATE SET value = EXCLUDED.value''',
                       paid, key, value), f'plan {paid}', key, 'backtest.view')
    # every data set is no limit: the paid plan's own row
    assert db(store, '''SELECT value FROM edge_bff.plan_capabilities WHERE plan_key = %s
        AND capability_key = 'terminal.dataset' ''', paid)[0]['value'] == {'all': True}


def test_an_override_on_either_side_is_refused_for_the_edge_bff_role_too(store):
    """edge-bff's own role (the Phase 4 admin actions) writes overrides: the rule refuses it the same way, and a right
    override passes (the read functions are granted to it, the trigger needs no grant)."""
    free_user = make_user(store, 'fran', 'fran-password')
    paid_user = make_user(store, 'pete', 'pete-password')
    subscribe(store, paid_user['user_id'], paid_plan(store))

    def as_runtime(sql, *args):
        with store.connect() as c:
            c.execute('SET LOCAL ROLE edge_bff_runtime')
            c.execute(sql, args)

    insert = '''INSERT INTO edge_bff.user_capability_overrides(user_id, capability_key, value, reason)
        VALUES (%s, %s, %s::jsonb, 'trial')'''
    text = refused(lambda: as_runtime(insert, free_user['user_id'], 'screener.view', 'true'),
                   f"user {free_user['user_id']} on plan {default_plan(store)}", 'screener.view')
    assert 'terminal.tickers' in text
    refused(lambda: as_runtime(insert, paid_user['user_id'], 'terminal.tickers', '["BBCA"]'),
            f"user {paid_user['user_id']} on plan {paid_plan(store)}", 'terminal.tickers', 'backtest.view')
    as_runtime(insert, free_user['user_id'], 'terminal.history_days', '365')          # narrower still: no clash
    as_runtime(insert, paid_user['user_id'], 'screener.saved_items', '10')            # not a data scope
    assert db(store, 'SELECT count(*) AS n FROM edge_bff.user_capability_overrides')[0]['n'] == 2


def test_the_admin_narrows_a_paid_account_only_after_closing_its_backtest_and_screener(store):
    user = make_user(store, 'nora', 'nora-password')
    subscribe(store, user['user_id'], paid_plan(store))
    narrow = lambda: override(store, user['user_id'], 'terminal.dataset', '{"ids": ["price"]}')   # noqa: E731
    refused(narrow, 'terminal.dataset')
    for key in EVERY_STOCK[:-1]:
        override(store, user['user_id'], key, 'false')
    refused(narrow, 'screener.view')                                  # one tab still open
    override(store, user['user_id'], 'screener.view', 'false')
    narrow()
    # an end on a closing override brings the plan's value back after it: refused while the Terminal stays narrowed
    refused(lambda: db(store, '''UPDATE edge_bff.user_capability_overrides SET expires_at = now() + interval '1 day'
        WHERE user_id = %s AND capability_key = 'backtest.run' ''', user['user_id']), 'backtest.run')
    # opening a tab again is refused the same way
    refused(lambda: override(store, user['user_id'], 'screener.view', 'true'), 'screener.view')


def test_a_subscription_with_the_backtest_is_refused_for_an_account_with_its_own_terminal_limit(store):
    user = make_user(store, 'otto', 'otto-password')
    override(store, user['user_id'], 'terminal.tickers', '["BBCA", "BBRI"]')       # on the default plan: no clash
    refused(lambda: subscribe(store, user['user_id'], paid_plan(store)), f"user {user['user_id']} on plan {paid_plan(store)}")
    # a subscription that is not active resolves to nothing: taken
    db(store, '''INSERT INTO edge_bff.subscriptions(user_id, plan_key, status, provider) VALUES (%s, %s, 'cancelled', 'test')''',
       user['user_id'], paid_plan(store))
    refused(lambda: db(store, "UPDATE edge_bff.subscriptions SET status = 'active' WHERE user_id = %s", user['user_id']))
    # without its own limit the account takes the plan
    db(store, 'DELETE FROM edge_bff.user_capability_overrides WHERE user_id = %s', user['user_id'])
    db(store, "UPDATE edge_bff.subscriptions SET status = 'active' WHERE user_id = %s", user['user_id'])


def test_an_override_with_an_end_is_judged_on_both_values_and_the_default_plan(store):
    """An account falls back to the default plan when its subscription ends, and an override's plan value comes back
    after its end: what may apply at some time is judged, not only what applies now."""
    user = make_user(store, 'ines', 'ines-password')
    subscribe(store, user['user_id'], paid_plan(store), expires="now() + interval '30 days'")
    # redundant on the paid plan, but a clash on the default plan the account returns to
    refused(lambda: override(store, user['user_id'], 'backtest.view', 'true'),
            f"user {user['user_id']} on plan {default_plan(store)}", 'backtest.view')
    # an override that ended already applies never again: not judged
    db(store, '''INSERT INTO edge_bff.user_capability_overrides(user_id, capability_key, value, reason, expires_at)
        VALUES (%s, 'terminal.tickers', '["BBCA"]', 'ended', now() - interval '1 second')''', user['user_id'])
    refused(lambda: db(store, '''UPDATE edge_bff.user_capability_overrides SET expires_at = now() + interval '1 day'
        WHERE user_id = %s''', user['user_id']), 'terminal.tickers')


@pytest.fixture
def scope_plan(store):
    """A plan of this test only (the catalog is shared by the session's tests): removed afterwards."""
    db(store, "INSERT INTO edge_bff.plans(plan_key, display_name) VALUES ('scope_test', 'Scope test')")
    try:
        yield 'scope_test'
    finally:
        default = default_plan(store)
        db(store, 'DELETE FROM edge_bff.subscriptions WHERE plan_key = %s', 'scope_test')
        if default == 'scope_test':
            raise AssertionError('the test plan became the default plan')
        db(store, 'DELETE FROM edge_bff.plans WHERE plan_key = %s', 'scope_test')


def test_everything_lifts_every_terminal_limit_so_it_holds_no_clash(store, scope_plan):
    """'*' holds everything and terminal_access sends the admin header (no Terminal limit applies under it), unless an
    override may take it away."""
    db(store, '''INSERT INTO edge_bff.plan_capabilities(plan_key, capability_key, value) VALUES
        (%s, '*', 'true'), (%s, 'terminal.tickers', '["BBCA"]'), (%s, 'backtest.view', 'true')''',
       scope_plan, scope_plan, scope_plan)
    user = make_user(store, 'rhea', 'rhea-password')
    subscribe(store, user['user_id'], scope_plan)
    refused(lambda: override(store, user['user_id'], '*', 'false'), f"user {user['user_id']} on plan {scope_plan}")
    refused(lambda: db(store, "DELETE FROM edge_bff.plan_capabilities WHERE plan_key = %s AND capability_key = '*'",
                       scope_plan), f'plan {scope_plan}')


def test_a_new_default_plan_and_a_new_mark_are_judged_against_every_account(store, scope_plan):
    db(store, "INSERT INTO edge_bff.plan_capabilities(plan_key, capability_key, value) VALUES (%s, 'backtest.view', 'true')",
       scope_plan)
    user = make_user(store, 'vera', 'vera-password')
    override(store, user['user_id'], 'terminal.history_days', '90')
    free = default_plan(store)

    def move_default():
        with store.connect() as c:
            c.execute('UPDATE edge_bff.plans SET is_default = false WHERE plan_key = %s', (free,))
            c.execute('UPDATE edge_bff.plans SET is_default = true WHERE plan_key = %s', (scope_plan,))

    refused(move_default, f"user {user['user_id']} on plan {scope_plan}", 'terminal.history_days', 'backtest.view')
    assert default_plan(store) == free
    # a capability the free plan holds marked as reading every stock: refused, naming the plan
    refused(lambda: db(store, "UPDATE edge_bff.capabilities SET data_scope = 'every_stock' WHERE capability_key = 'monitor.example'"),
            f'plan {free}', 'monitor.example')
    assert db(store, "SELECT data_scope FROM edge_bff.capabilities WHERE capability_key = 'monitor.example'")[0]['data_scope'] is None


def test_two_writes_racing_on_one_account_are_judged_one_after_the_other(store, database):
    """Each check takes one advisory lock for its transaction: the second write waits for the first to commit and then
    sees it (no write skew between an override and a subscription)."""
    user = make_user(store, 'walt', 'walt-password')
    first = psycopg.connect(database)
    try:
        first.execute('''INSERT INTO edge_bff.user_capability_overrides(user_id, capability_key, value, reason)
            VALUES (%s, 'terminal.tickers', '["BBCA"]', 'race')''', (user['user_id'],))
        outcome = {}

        def second():
            try:
                subscribe(store, user['user_id'], paid_plan(store))
                outcome['error'] = None
            except psycopg.Error as e:            # noqa: PERF203
                outcome['error'] = e

        t = threading.Thread(target=second)
        t.start()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not db(store, '''SELECT 1 FROM pg_locks
                WHERE locktype = 'advisory' AND NOT granted'''):
            time.sleep(0.02)
        assert t.is_alive(), outcome
        first.commit()
        t.join(10)
        assert isinstance(outcome.get('error'), psycopg.errors.CheckViolation), outcome
        assert outcome['error'].diag.constraint_name == CONSTRAINT
    finally:
        first.close()


def test_the_migration_refuses_a_second_run(database):
    with psycopg.connect(database, autocommit=True) as conn:
        with pytest.raises(psycopg.errors.RaiseException, match='ran already'):
            conn.execute(MIGRATION.read_text())


def test_the_migrations_verify_block_names_a_catalog_that_clashes_already(database):
    text = MIGRATION.read_text().replace('BEGIN;', '', 1).replace('COMMIT;', '', 1)
    undo = '''DROP TRIGGER plan_capabilities_data_scope ON edge_bff.plan_capabilities;
        DROP TRIGGER user_capability_overrides_data_scope ON edge_bff.user_capability_overrides;
        DROP TRIGGER subscriptions_data_scope ON edge_bff.subscriptions;
        DROP TRIGGER plans_data_scope ON edge_bff.plans;
        DROP TRIGGER capabilities_data_scope ON edge_bff.capabilities;
        DROP FUNCTION edge_bff.data_scope_guard(), edge_bff.data_scope_conflicts(text, bigint),
            edge_bff.data_scope_conflict(text, bigint);
        ALTER TABLE edge_bff.capabilities DROP COLUMN data_scope;'''
    with psycopg.connect(database) as conn:
        free = conn.execute('SELECT plan_key FROM edge_bff.plans WHERE is_default').fetchone()[0]
        conn.execute(undo)
        conn.execute(text)                                              # the file itself passes its own verify
        conn.rollback()
        conn.execute(undo)
        conn.execute("INSERT INTO edge_bff.plan_capabilities(plan_key, capability_key, value) VALUES (%s, 'screener.run', 'true')",
                     (free,))
        with pytest.raises(psycopg.errors.RaiseException, match=f'already clashes.*plan {free}: .*terminal.tickers.* with screener.run'):
            conn.execute(text)
        conn.rollback()
    with psycopg.connect(database) as conn:
        assert conn.execute("SELECT count(*) FROM pg_trigger WHERE tgname LIKE '%%_data_scope'").fetchone()[0] == 5
