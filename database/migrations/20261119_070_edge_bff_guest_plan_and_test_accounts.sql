-- EDGE multi-user fix round, track guest (EXEC-MU-ACCOUNTS; verification/edge_multiuser/fix_round/guest.md), behind the
-- switch EDGE_MULTIUSER (off on the beta; with it off edge-bff reads none of these rows or columns):
--
-- 1. The guest plan (decision 1 of 2026-11-19, the user: "1a - bukan hanya chart, nanti ada indikator dll yg juga
--    mungkin di show ke user. jadi design harus plug and play dan fluid, karna ticker dan indikatornya bisa berubah"):
--    a visitor without an account opens the Terminal and sees what the guest plan grants. edge_bff.plans.for_guests marks
--    the one plan whose grants a visitor gets (partial UNIQUE plans_one_guest; never the default plan, CHECK
--    plans_guest_not_default), read through the same plan_capabilities, value checks and principal as every other plan
--    (app/principal.py guest_principal), so a change of its rows changes what visitors see on the next request, without
--    code. Seed: plan 'guest' ("Guest") with the free plan's Terminal grants (terminal.view, terminal.tickers
--    ["BBCA"], terminal.dataset {"ids": ["price"]}, terminal.history_days 730, terminal.indicator {"ids": []}: no
--    indicator yet). No Terminal quota row: terminal-api's terminal.quota defaults apply to each visitor on its own
--    (x-terminal-client, 20261119_170); a quota row added to this plan later overlays them, as for every plan. The
--    restricted-plan rule (20261119_030) applies to it as to every plan: it holds no Backtest or Screener access.
-- 2. Test accounts for the live site's pre-launch mode (the user, 2026-11-19: "Terbuka, tapi belum bisa mendaftar",
--    "Dan hanya admin yang bisa login (saya)", then "A": besides the admin only accounts marked as test accounts):
--    edge_bff.users.test_account (false by default). A change of the mark is accepted only beside its admin_audit row
--    of the same transaction (action 'account.test_mark', the account as target, after = {"test_account": <value>}):
--    a deferred constraint trigger (users_test_account_audited) refuses it otherwise with SQLSTATE 23514, so the mark is
--    set only by an audited step (scripts/edge_test_account.py today, the Phase 4 admin API later).
--
-- No table grant changes: edge_bff_runtime reads plans (SELECT) and reads and writes users and admin_audit through its
-- existing grants (20261116_003, 20261117_003). The trigger function is executable by nobody (a trigger needs no
-- grant). Refuses a second run. Forward-only; rollback block at the end (comment).
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF to_regclass('edge_bff.plans') IS NULL OR to_regclass('edge_bff.plan_capabilities') IS NULL
       OR to_regclass('edge_bff.users') IS NULL OR to_regclass('edge_bff.admin_audit') IS NULL THEN
        RAISE EXCEPTION 'the EDGE accounts or the plan catalog are missing: apply 20261116_003 and 20261117_003 first';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'edge_bff'
               AND ((table_name = 'plans' AND column_name = 'for_guests')
                    OR (table_name = 'users' AND column_name = 'test_account'))) THEN
        RAISE EXCEPTION 'edge_bff.plans.for_guests or edge_bff.users.test_account exists: already applied';
    END IF;
    IF EXISTS (SELECT 1 FROM edge_bff.plans WHERE plan_key = 'guest') THEN
        RAISE EXCEPTION 'a plan guest exists: reconcile before applying';
    END IF;
    IF (SELECT count(*) FROM edge_bff.capabilities WHERE capability_key IN ('terminal.view', 'terminal.tickers',
            'terminal.dataset', 'terminal.history_days', 'terminal.indicator')) <> 5 THEN
        RAISE EXCEPTION 'a Terminal capability of 20261117_003 is missing: apply it first';
    END IF;
END $preflight$;

-- ---- 1. the guest plan -----------------------------------------------------------------------------------------------
ALTER TABLE edge_bff.plans
    ADD COLUMN for_guests boolean NOT NULL DEFAULT false,
    ADD CONSTRAINT plans_guest_not_default CHECK (NOT (for_guests AND is_default));
CREATE UNIQUE INDEX plans_one_guest ON edge_bff.plans ((true)) WHERE for_guests;
COMMENT ON COLUMN edge_bff.plans.for_guests IS
    'EXEC-MU-ACCOUNTS track guest: the one plan whose grants a visitor without an account gets on the live site (EDGE_GUESTS), read like any plan; never the default plan.';

INSERT INTO edge_bff.plans(plan_key, display_name, is_default, for_guests) VALUES ('guest', 'Guest', false, true);
INSERT INTO edge_bff.plan_capabilities(plan_key, capability_key, value) VALUES
    ('guest', 'terminal.view', 'true'),
    ('guest', 'terminal.tickers', '["BBCA"]'),
    ('guest', 'terminal.dataset', '{"ids": ["price"]}'),
    ('guest', 'terminal.history_days', '730'),
    ('guest', 'terminal.indicator', '{"ids": []}');

-- ---- 2. test accounts ------------------------------------------------------------------------------------------------
ALTER TABLE edge_bff.users ADD COLUMN test_account boolean NOT NULL DEFAULT false;
COMMENT ON COLUMN edge_bff.users.test_account IS
    'EXEC-MU-ACCOUNTS track guest: an account the pre-launch mode of the live site (EDGE_PRELAUNCH) lets sign in beside the admin; changed only beside its admin_audit row (action account.test_mark) of the same transaction (trigger users_test_account_audited).';

CREATE FUNCTION edge_bff.test_account_audited() RETURNS trigger LANGUAGE plpgsql
SET search_path = pg_catalog, edge_bff AS $fn$
BEGIN
    -- the audit row of this transaction (admin_audit.at defaults to the transaction's start, CURRENT_TIMESTAMP)
    IF NOT EXISTS (SELECT 1 FROM edge_bff.admin_audit a WHERE a.action = 'account.test_mark'
                   AND a.target_user_id = NEW.user_id AND a.at = CURRENT_TIMESTAMP
                   AND jsonb_typeof(a.after -> 'test_account') = 'boolean'
                   AND (a.after ->> 'test_account')::boolean = NEW.test_account) THEN
        RAISE EXCEPTION USING ERRCODE = 'check_violation', CONSTRAINT = 'users_test_account_audited',
            MESSAGE = format('the test-account mark of user %s changed to %s without its audit row', NEW.user_id,
                             NEW.test_account),
            HINT = 'Change edge_bff.users.test_account only with an edge_bff.admin_audit row in the same transaction: '
                   || 'action account.test_mark, target_user_id the account, after {"test_account": <the new value>}. '
                   || 'Use scripts/edge_test_account.py. Right: INSERT INTO edge_bff.admin_audit(action, '
                   || 'target_user_id, after, reason) VALUES (''account.test_mark'', 7, ''{"test_account": true}'', '
                   || '''operator: ...'') then UPDATE edge_bff.users SET test_account = true WHERE user_id = 7. '
                   || 'Wrong: the UPDATE alone.';
    END IF;
    RETURN NULL;
END $fn$;
REVOKE ALL ON FUNCTION edge_bff.test_account_audited() FROM PUBLIC;
COMMENT ON FUNCTION edge_bff.test_account_audited() IS
    'EXEC-MU-ACCOUNTS track guest: refuses a change of edge_bff.users.test_account without its admin_audit row of the same transaction (deferred to the commit).';
CREATE CONSTRAINT TRIGGER users_test_account_audited AFTER INSERT ON edge_bff.users
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW WHEN (NEW.test_account)
    EXECUTE FUNCTION edge_bff.test_account_audited();
CREATE CONSTRAINT TRIGGER users_test_account_audited_change AFTER UPDATE OF test_account ON edge_bff.users
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW WHEN (OLD.test_account IS DISTINCT FROM NEW.test_account)
    EXECUTE FUNCTION edge_bff.test_account_audited();

DO $verify$
DECLARE
    probe bigint;
BEGIN
    IF (SELECT count(*) FROM edge_bff.plans WHERE for_guests) <> 1
       OR NOT EXISTS (SELECT 1 FROM edge_bff.plans WHERE plan_key = 'guest' AND for_guests AND NOT is_default)
       OR (SELECT count(*) FROM edge_bff.plans WHERE is_default) <> 1 THEN
        RAISE EXCEPTION 'the guest plan is not the one plan for guests, or the default plan changed';
    END IF;
    -- the guest plan holds the five Terminal grants and nothing else; where the free plan holds the same key, the
    -- same value (seeded like the free plan's Terminal grants)
    IF (SELECT count(*) FROM edge_bff.plan_capabilities WHERE plan_key = 'guest') <> 5
       OR EXISTS (SELECT 1 FROM edge_bff.plan_capabilities g JOIN edge_bff.plan_capabilities f
                  ON f.capability_key = g.capability_key AND f.plan_key = 'free'
                  WHERE g.plan_key = 'guest' AND f.value <> g.value) THEN
        RAISE EXCEPTION 'the guest plan''s rows are not the free plan''s five Terminal grants';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM edge_bff.plan_capabilities WHERE plan_key = 'guest' AND capability_key = 'terminal.tickers'
                   AND value = '["BBCA"]'::jsonb)
       OR NOT EXISTS (SELECT 1 FROM edge_bff.plan_capabilities WHERE plan_key = 'guest'
                      AND capability_key = 'terminal.history_days' AND value = '730'::jsonb)
       OR EXISTS (SELECT 1 FROM edge_bff.plan_capabilities WHERE plan_key = 'guest' AND capability_key = '*') THEN
        RAISE EXCEPTION 'the guest plan''s Terminal rows are not BBCA, 730 days and no *';
    END IF;
    IF to_regprocedure('edge_bff.data_scope_conflicts(text, bigint)') IS NOT NULL THEN
        IF EXISTS (SELECT 1 FROM edge_bff.data_scope_conflicts('guest', NULL)) THEN
            RAISE EXCEPTION 'the guest plan clashes with the restricted-plan rule (20261119_030)';
        END IF;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'edge_bff' AND table_name = 'users'
                   AND column_name = 'test_account' AND is_nullable = 'NO' AND column_default = 'false')
       OR EXISTS (SELECT 1 FROM edge_bff.users WHERE test_account) THEN
        RAISE EXCEPTION 'edge_bff.users.test_account is not a NOT NULL false column, or an existing account is marked';
    END IF;
    IF (SELECT count(*) FROM pg_trigger WHERE tgrelid = 'edge_bff.users'::regclass AND tgconstraint <> 0
        AND tgdeferrable AND tginitdeferred
        AND tgname IN ('users_test_account_audited', 'users_test_account_audited_change')) <> 2 THEN
        RAISE EXCEPTION 'the two deferred triggers of the test-account mark are missing';
    END IF;
    IF has_function_privilege('public', 'edge_bff.test_account_audited()', 'EXECUTE') THEN
        RAISE EXCEPTION 'PUBLIC may execute edge_bff.test_account_audited()';
    END IF;
    -- the runtime reaches the new columns through its existing grants
    IF NOT (has_column_privilege('edge_bff_runtime', 'edge_bff.plans', 'for_guests', 'SELECT')
            AND has_column_privilege('edge_bff_runtime', 'edge_bff.users', 'test_account', 'SELECT')) THEN
        RAISE EXCEPTION 'edge_bff_runtime cannot read edge_bff.plans.for_guests or edge_bff.users.test_account';
    END IF;
    -- its own examples, rolled back: the mark with its audit row is accepted, without it refused at the commit point
    BEGIN
        INSERT INTO edge_bff.users(owner_key, username, email, status) VALUES
            ('u_' || substr(md5(random()::text), 1, 24), 'guestprobe_' || substr(md5(random()::text), 1, 8),
             'probe-' || substr(md5(random()::text), 1, 8) || '@example.invalid', 'active') RETURNING user_id INTO probe;
        INSERT INTO edge_bff.admin_audit(action, target_user_id, after, reason)
            VALUES ('account.test_mark', probe, '{"test_account": true}', 'operator: migration probe');
        UPDATE edge_bff.users SET test_account = true WHERE user_id = probe;
        SET CONSTRAINTS edge_bff.users_test_account_audited_change IMMEDIATE;
        SET CONSTRAINTS edge_bff.users_test_account_audited_change DEFERRED;
        BEGIN
            UPDATE edge_bff.users SET test_account = false WHERE user_id = probe;
            SET CONSTRAINTS edge_bff.users_test_account_audited_change IMMEDIATE;
            RAISE EXCEPTION 'probe: an unaudited change of the mark was accepted';
        EXCEPTION WHEN check_violation THEN
            NULL;
        END;
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'probe done';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM <> 'probe done' THEN
            RAISE;
        END IF;
    END;
    SET CONSTRAINTS edge_bff.users_test_account_audited, edge_bff.users_test_account_audited_change DEFERRED;
END $verify$;
COMMIT;

-- Rollback (a new forward migration with this body), only after edge-bff runs code that reads neither column (its
-- /ready lists both with the switch on, app/store.py ready):
-- BEGIN;
-- DROP TRIGGER users_test_account_audited ON edge_bff.users;
-- DROP TRIGGER users_test_account_audited_change ON edge_bff.users;
-- DROP FUNCTION edge_bff.test_account_audited();
-- ALTER TABLE edge_bff.users DROP COLUMN test_account;
-- DELETE FROM edge_bff.plan_capabilities WHERE plan_key = 'guest';
-- DELETE FROM edge_bff.plans WHERE plan_key = 'guest';
-- DROP INDEX edge_bff.plans_one_guest;
-- ALTER TABLE edge_bff.plans DROP CONSTRAINT plans_guest_not_default, DROP COLUMN for_guests;
-- COMMIT;
