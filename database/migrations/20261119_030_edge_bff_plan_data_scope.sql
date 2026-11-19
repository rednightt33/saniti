-- EDGE multi-user, re-check of Phases 0-3b, fix round (EXEC-MU-ACCOUNTS; track plans, finding R1-36; user decision
-- 2026-11-19, EXEC.md "Decisions from the fix round" item 1, the extra rule: "2a", agreed, enforced by the catalog;
-- verification/edge_multiuser/fix_round/plans.md): a plan or an override that limits the Terminal's tickers, data sets
-- or history may not also hold the Backtest's or the Screener's own data access, behind the switch EDGE_MULTIUSER (off
-- until Phase 6; with it off edge-bff reads none of these rows).
--
-- Why: the Terminal's data limits (terminal.tickers, terminal.dataset, terminal.history_days) bind the Terminal path
-- only (edge-bff's x-terminal-capabilities to terminal-api). The Backtest and Screener workers read every stock with
-- their own terminal-api service keys, outside those limits. An account holding both (the free plan's one ticker and
-- two years, with a trial of the Screener by an override) would see every ticker's prices and run any ticker over its
-- whole history. The catalog refuses that combination when it is written, so no account can hold it at any time.
--
-- New column edge_bff.capabilities.data_scope (NULL: neither):
--   terminal_limit  a row narrows what the Terminal shows of the stocks: a list or a limit by being there (no row:
--                   every ticker, no limit), an item family unless its value is {"all": true}
--                   (terminal.tickers, terminal.dataset, terminal.history_days)
--   every_stock     a granted value opens a tab whose own data path reads every stock (its worker, its service key)
--                   (backtest.view, backtest.run, screener.view, screener.run)
-- The Terminal quotas (terminal.tickers_per_hour and the others) are rate limits the paid plan holds beside the
-- Backtest, not limits of which stocks: they are not marked. The example flags (backtest.example, screener.example: a
-- fixed page, no live data) are not marked, so the free plan keeps them. A later capability of either kind is marked in
-- its own migration.
--
-- The rule, for every account at every time: never a terminal_limit row that narrows together with a granted
-- every_stock row, unless '*' holds everything (terminal_access sends the admin header: no Terminal limit applies).
-- Checked on what may apply at some time, not only now: an override with an end leaves the plan's value to come back
-- after it; an account may always fall back to the default plan (its subscription ends or is cancelled), so its
-- overrides are checked against the default plan and against its live subscription's plan.
--   edge_bff.data_scope_conflict(plan, user)   the clash on one plan for one account (user NULL: the plan alone), or NULL
--   edge_bff.data_scope_conflicts(plan, user)  every clash in a scope (both NULL: the whole catalog)
--   edge_bff.data_scope_guard()                the trigger: refuses a write that makes a clash, with SQLSTATE 23514
--                                              (check_violation), CONSTRAINT terminal_limit_with_every_stock, a message
--                                              naming the plan or account and the keys, and a hint with the way out
-- Triggers (AFTER ROW, immediate: within one transaction, take the narrowing rows away before adding the Backtest or
-- Screener ones, or the reverse to narrow a plan): plan_capabilities and user_capability_overrides (insert, update,
-- delete), subscriptions (insert, update; an active one), plans (a new default plan), capabilities (data_scope changed).
-- Every check takes one transaction-scoped advisory lock, so two writes racing on the same accounts are judged one after
-- the other. Writes to these tables are rare (migrations, the admin, Phase 4).
--
-- No table grant or index changes. The two read functions are executable by edge_bff_runtime (it writes overrides and
-- subscriptions, and a trigger runs as the role that writes); the trigger function by nobody (triggers need no grant).
-- Refuses a second run and a catalog that already clashes (it names each clash). Forward-only; rollback block at the
-- end (comment).
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF to_regclass('edge_bff.capabilities') IS NULL OR to_regclass('edge_bff.subscriptions') IS NULL
       OR to_regclass('edge_bff.user_capability_overrides') IS NULL THEN
        RAISE EXCEPTION 'the EDGE plan catalog is missing: apply 20261117_003 first';
    END IF;
    IF (SELECT count(*) FROM edge_bff.capabilities WHERE capability_key IN ('terminal.tickers', 'terminal.dataset',
            'terminal.history_days', 'backtest.view', 'backtest.run', 'screener.view', 'screener.run')) <> 7 THEN
        RAISE EXCEPTION 'a Terminal, Backtest or Screener capability of 20261117_003 is missing: reconcile before applying';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'edge_bff' AND table_name = 'capabilities'
               AND column_name = 'data_scope') THEN
        RAISE EXCEPTION 'edge_bff.capabilities already has data_scope: this migration ran already; reconcile before applying';
    END IF;
END $preflight$;

ALTER TABLE edge_bff.capabilities
    ADD COLUMN data_scope text CONSTRAINT capabilities_data_scope CHECK (data_scope IN ('terminal_limit', 'every_stock'));
COMMENT ON COLUMN edge_bff.capabilities.data_scope IS 'terminal_limit: a row narrows what the Terminal shows of the stocks (a list or limit by being there, an item family unless {"all": true}); every_stock: a granted value opens a tab whose own data path reads every stock (the Backtest and Screener workers). No account may hold both at any time unless * holds everything (edge_bff.data_scope_guard, CONSTRAINT terminal_limit_with_every_stock); NULL: neither. Re-check R1-36, user decision 2026-11-19 "2a".';

-- ---- the clash on one plan for one account ----------------------------------------------------------------------------
-- What may apply at some time: the plan's row of a key, unless the account has an override of it without an end; and
-- every override of the account that has not ended. '*' counts only when it holds everything at every time (the value
-- after every end is true, and no value that may apply is false).
CREATE FUNCTION edge_bff.data_scope_conflict(p_plan text, p_user bigint) RETURNS text
    LANGUAGE sql STABLE SET search_path = pg_catalog, pg_temp AS $fn$
    WITH o AS (
        SELECT capability_key, value, expires_at FROM edge_bff.user_capability_overrides
        WHERE user_id = p_user AND (expires_at IS NULL OR expires_at > now())
    ), may AS (
        SELECT pc.capability_key, pc.value FROM edge_bff.plan_capabilities pc
        WHERE pc.plan_key = p_plan
          AND NOT EXISTS (SELECT 1 FROM o WHERE o.capability_key = pc.capability_key AND o.expires_at IS NULL)
        UNION ALL
        SELECT capability_key, value FROM o
    ), star AS (
        SELECT coalesce(coalesce((SELECT value FROM o WHERE capability_key = '*' AND expires_at IS NULL),
                                 (SELECT value FROM edge_bff.plan_capabilities WHERE plan_key = p_plan
                                  AND capability_key = '*')) = 'true'::jsonb, false)
               AND NOT EXISTS (SELECT 1 FROM may WHERE capability_key = '*' AND value <> 'true'::jsonb) AS always
    ), scoped AS (
        SELECT m.capability_key, c.data_scope FROM may m JOIN edge_bff.capabilities c USING (capability_key)
        WHERE c.data_scope IS NOT NULL AND CASE
            WHEN c.data_scope = 'terminal_limit' THEN CASE c.kind
                WHEN 'items' THEN m.value -> 'all' IS DISTINCT FROM 'true'::jsonb
                WHEN 'flag' THEN m.value = 'true'::jsonb
                ELSE true END
            ELSE CASE c.kind
                WHEN 'flag' THEN m.value = 'true'::jsonb
                WHEN 'limit' THEN m.value <> '0'::jsonb
                WHEN 'list' THEN m.value <> '[]'::jsonb
                ELSE m.value -> 'all' = 'true'::jsonb OR coalesce(m.value -> 'ids', '[]'::jsonb) <> '[]'::jsonb
                     OR coalesce(m.value -> 'stages', '[]'::jsonb) <> '[]'::jsonb END END
    )
    SELECT string_agg(DISTINCT capability_key, ', ' ORDER BY capability_key) FILTER (WHERE data_scope = 'terminal_limit')
           || ' with '
           || string_agg(DISTINCT capability_key, ', ' ORDER BY capability_key) FILTER (WHERE data_scope = 'every_stock')
    FROM scoped
    WHERE NOT (SELECT always FROM star)
    HAVING count(*) FILTER (WHERE data_scope = 'terminal_limit') > 0
       AND count(*) FILTER (WHERE data_scope = 'every_stock') > 0
$fn$;
COMMENT ON FUNCTION edge_bff.data_scope_conflict(text, bigint) IS 'The clash of the data_scope rule on one plan for one account (NULL account: the plan alone): "<terminal_limit keys> with <every_stock keys>" of the values that may apply at some time, or NULL. Re-check R1-36.';

-- ---- every clash in a scope -------------------------------------------------------------------------------------------
-- plan given: that plan alone and every account with an override that may resolve to it; account given: that account
-- on each plan it may resolve to (its live subscription's and the default); neither: every plan and every account.
CREATE FUNCTION edge_bff.data_scope_conflicts(p_plan text, p_user bigint)
    RETURNS TABLE (plan_key text, user_id bigint, found text)
    LANGUAGE sql STABLE SET search_path = pg_catalog, pg_temp AS $fn$
    WITH accounts AS (
        SELECT DISTINCT o.user_id FROM edge_bff.user_capability_overrides o
        WHERE (o.expires_at IS NULL OR o.expires_at > now()) AND (p_user IS NULL OR o.user_id = p_user)
    ), cases AS (
        SELECT p.plan_key, NULL::bigint AS user_id FROM edge_bff.plans p
        WHERE p_user IS NULL AND (p_plan IS NULL OR p.plan_key = p_plan)
        UNION
        SELECT x.plan_key, a.user_id FROM accounts a
        CROSS JOIN LATERAL (
            SELECT s.plan_key FROM edge_bff.subscriptions s
            WHERE s.user_id = a.user_id AND s.status = 'active' AND (s.expires_at IS NULL OR s.expires_at > now())
            UNION
            SELECT d.plan_key FROM edge_bff.plans d WHERE d.is_default) x
        WHERE p_plan IS NULL OR x.plan_key = p_plan
    )
    SELECT c.plan_key, c.user_id, f.found FROM cases c
    CROSS JOIN LATERAL (SELECT edge_bff.data_scope_conflict(c.plan_key, c.user_id) AS found) f
    WHERE f.found IS NOT NULL
    ORDER BY c.plan_key, c.user_id NULLS FIRST
$fn$;
COMMENT ON FUNCTION edge_bff.data_scope_conflicts(text, bigint) IS 'Every clash of the data_scope rule in a scope (a plan with the accounts that may resolve to it; an account on each plan it may resolve to; both NULL: the whole catalog). Re-check R1-36.';

REVOKE ALL ON FUNCTION edge_bff.data_scope_conflict(text, bigint), edge_bff.data_scope_conflicts(text, bigint) FROM PUBLIC;
-- the trigger runs as the role that writes (edge_bff_runtime writes overrides and subscriptions): both are read-only
GRANT EXECUTE ON FUNCTION edge_bff.data_scope_conflict(text, bigint), edge_bff.data_scope_conflicts(text, bigint)
    TO edge_bff_runtime;

-- ---- the trigger ------------------------------------------------------------------------------------------------------
CREATE FUNCTION edge_bff.data_scope_guard() RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
DECLARE
    plans text[] := ARRAY[NULL]::text[];
    users bigint[] := ARRAY[NULL]::bigint[];
    p text;
    u bigint;
    hit record;
BEGIN
    IF TG_TABLE_NAME = 'plan_capabilities' THEN
        plans := CASE TG_OP WHEN 'INSERT' THEN ARRAY[NEW.plan_key] WHEN 'DELETE' THEN ARRAY[OLD.plan_key]
                 ELSE ARRAY[OLD.plan_key, NEW.plan_key] END;
    ELSIF TG_TABLE_NAME = 'user_capability_overrides' THEN
        users := CASE TG_OP WHEN 'INSERT' THEN ARRAY[NEW.user_id] WHEN 'DELETE' THEN ARRAY[OLD.user_id]
                 ELSE ARRAY[OLD.user_id, NEW.user_id] END;
    ELSIF TG_TABLE_NAME = 'subscriptions' THEN
        IF NEW.status <> 'active' THEN
            RETURN NULL;
        END IF;
        users := ARRAY[NEW.user_id];
    END IF;
    -- plans (a new default plan) and capabilities (a changed data_scope): every plan and every account
    PERFORM pg_advisory_xact_lock(hashtextextended('edge_bff.data_scope_guard', 0));
    FOREACH p IN ARRAY plans LOOP
        FOREACH u IN ARRAY users LOOP
            SELECT * INTO hit FROM edge_bff.data_scope_conflicts(p, u) LIMIT 1;
            IF FOUND THEN
                RAISE EXCEPTION 'edge_bff.%: % would both limit the Terminal and open the Backtest or the Screener (%)',
                    TG_TABLE_NAME, CASE WHEN hit.user_id IS NULL THEN 'plan ' || hit.plan_key
                                        ELSE 'user ' || hit.user_id || ' on plan ' || hit.plan_key END, hit.found
                    USING ERRCODE = 'check_violation', CONSTRAINT = 'terminal_limit_with_every_stock',
                          HINT = 'A plan or an override that limits the Terminal''s tickers, data sets or history '
                                 '(capabilities.data_scope terminal_limit) may not also hold the Backtest''s or the '
                                 'Screener''s own data access (data_scope every_stock): their workers read every stock. '
                                 'Give the account a plan without those Terminal limits (a subscription; ended, it falls '
                                 'back to the default plan), or leave backtest.view, backtest.run, screener.view and '
                                 'screener.run out. Right: a plan with terminal.tickers ["BBCA"] and backtest.example; '
                                 'wrong: the same plan with backtest.view.';
            END IF;
        END LOOP;
    END LOOP;
    RETURN NULL;
END $fn$;
REVOKE ALL ON FUNCTION edge_bff.data_scope_guard() FROM PUBLIC;
COMMENT ON FUNCTION edge_bff.data_scope_guard() IS 'Refuses a write to the plan catalog after which an account could hold a Terminal limit (data_scope terminal_limit) together with the Backtest''s or the Screener''s own data access (data_scope every_stock), with SQLSTATE 23514 and CONSTRAINT terminal_limit_with_every_stock. Re-check R1-36, user decision 2026-11-19 "2a".';

-- ---- the marks (before the triggers: the verify block below checks the whole catalog once) ---------------------------
UPDATE edge_bff.capabilities SET data_scope = 'terminal_limit'
    WHERE capability_key IN ('terminal.tickers', 'terminal.dataset', 'terminal.history_days');
UPDATE edge_bff.capabilities SET data_scope = 'every_stock'
    WHERE capability_key IN ('backtest.view', 'backtest.run', 'screener.view', 'screener.run');

CREATE TRIGGER plan_capabilities_data_scope AFTER INSERT OR UPDATE OR DELETE ON edge_bff.plan_capabilities
    FOR EACH ROW EXECUTE FUNCTION edge_bff.data_scope_guard();
CREATE TRIGGER user_capability_overrides_data_scope AFTER INSERT OR UPDATE OR DELETE ON edge_bff.user_capability_overrides
    FOR EACH ROW EXECUTE FUNCTION edge_bff.data_scope_guard();
CREATE TRIGGER subscriptions_data_scope AFTER INSERT OR UPDATE ON edge_bff.subscriptions
    FOR EACH ROW EXECUTE FUNCTION edge_bff.data_scope_guard();
CREATE TRIGGER plans_data_scope AFTER INSERT OR UPDATE OF is_default ON edge_bff.plans
    FOR EACH ROW WHEN (NEW.is_default) EXECUTE FUNCTION edge_bff.data_scope_guard();
CREATE TRIGGER capabilities_data_scope AFTER UPDATE OF data_scope ON edge_bff.capabilities
    FOR EACH ROW WHEN (NEW.data_scope IS DISTINCT FROM OLD.data_scope) EXECUTE FUNCTION edge_bff.data_scope_guard();

DO $verify$
DECLARE
    want constant jsonb := '{"terminal.tickers": "terminal_limit", "terminal.dataset": "terminal_limit",
        "terminal.history_days": "terminal_limit", "backtest.view": "every_stock", "backtest.run": "every_stock",
        "screener.view": "every_stock", "screener.run": "every_stock"}';
    got jsonb;
    bad text;
    cname text;
    refused boolean;
BEGIN
    SELECT jsonb_object_agg(capability_key, data_scope) INTO got FROM edge_bff.capabilities WHERE data_scope IS NOT NULL;
    IF got IS DISTINCT FROM want THEN
        RAISE EXCEPTION 'the data_scope marks are %, not %', got, want;
    END IF;
    -- the catalog as it stands holds no clash (on dev: three plans, no override on 2026-11-18)
    SELECT string_agg(coalesce('user ' || x.user_id || ' on ', '') || 'plan ' || x.plan_key || ': ' || x.found, '; ')
        INTO bad FROM edge_bff.data_scope_conflicts(NULL, NULL) x;
    IF bad IS NOT NULL THEN
        RAISE EXCEPTION 'the plan catalog already clashes with the data_scope rule: %', bad
            USING HINT = 'Take the Backtest and Screener rows away from the plans and overrides named, or their '
                         'Terminal limits, in a migration before this one.';
    END IF;
    IF (SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal AND tgname IN ('plan_capabilities_data_scope',
            'user_capability_overrides_data_scope', 'subscriptions_data_scope', 'plans_data_scope',
            'capabilities_data_scope')) <> 5 THEN
        RAISE EXCEPTION 'the five data_scope triggers are not all in place';
    END IF;
    IF NOT has_function_privilege('edge_bff_runtime', 'edge_bff.data_scope_conflicts(text, bigint)', 'EXECUTE')
       OR NOT has_function_privilege('edge_bff_runtime', 'edge_bff.data_scope_conflict(text, bigint)', 'EXECUTE')
       OR has_function_privilege('public', 'edge_bff.data_scope_guard()', 'EXECUTE')
       OR has_function_privilege('public', 'edge_bff.data_scope_conflicts(text, bigint)', 'EXECUTE') THEN
        RAISE EXCEPTION 'the data_scope functions do not have the privileges of this migration';
    END IF;
    -- its own examples, rolled back: a plan with one Terminal ticker keeps the example flags, and is refused the
    -- Screener's run; the same plan with every data set and '*' takes it
    BEGIN
        INSERT INTO edge_bff.plans(plan_key, display_name) VALUES ('data_scope_check', 'Data scope check');
        INSERT INTO edge_bff.plan_capabilities(plan_key, capability_key, value) VALUES
            ('data_scope_check', 'terminal.tickers', '["BBCA"]'), ('data_scope_check', 'terminal.dataset', '{"all": true}'),
            ('data_scope_check', 'backtest.example', 'true'), ('data_scope_check', 'screener.example', 'true');
        refused := false;
        BEGIN
            INSERT INTO edge_bff.plan_capabilities(plan_key, capability_key, value)
                VALUES ('data_scope_check', 'screener.run', 'true');
        EXCEPTION WHEN check_violation THEN
            GET STACKED DIAGNOSTICS cname = CONSTRAINT_NAME;
            refused := cname = 'terminal_limit_with_every_stock';
        END;
        IF NOT refused THEN
            RAISE EXCEPTION 'data_scope_guard took screener.run on a plan with terminal.tickers';
        END IF;
        INSERT INTO edge_bff.plan_capabilities(plan_key, capability_key, value)
            VALUES ('data_scope_check', '*', 'true'), ('data_scope_check', 'screener.run', 'true');
        RAISE EXCEPTION USING ERRCODE = 'EDG30', MESSAGE = 'the examples hold';
    EXCEPTION WHEN SQLSTATE 'EDG30' THEN
        NULL;
    END;
    IF EXISTS (SELECT 1 FROM edge_bff.plans WHERE plan_key = 'data_scope_check') THEN
        RAISE EXCEPTION 'the example plan of this check was not rolled back';
    END IF;
END $verify$;
COMMIT;

-- Rollback (a new forward migration with this body; edge-bff reads none of it):
-- BEGIN;
-- DROP TRIGGER plan_capabilities_data_scope ON edge_bff.plan_capabilities;
-- DROP TRIGGER user_capability_overrides_data_scope ON edge_bff.user_capability_overrides;
-- DROP TRIGGER subscriptions_data_scope ON edge_bff.subscriptions;
-- DROP TRIGGER plans_data_scope ON edge_bff.plans;
-- DROP TRIGGER capabilities_data_scope ON edge_bff.capabilities;
-- DROP FUNCTION edge_bff.data_scope_guard(), edge_bff.data_scope_conflicts(text, bigint),
--     edge_bff.data_scope_conflict(text, bigint);
-- ALTER TABLE edge_bff.capabilities DROP COLUMN data_scope;
-- COMMIT;
