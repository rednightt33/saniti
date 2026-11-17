-- EDGE multi-user Phase 2 (EXEC-MU-ACCOUNTS; go 2026-11-16 and user 2026-11-17 "sudah ada, pls continue"; contract
-- verification/edge_multiuser/access_tiers/CONTRACT.md sections 1, 2, 8, 8a and 9): the plan catalog of edge-bff, behind
-- the switch EDGE_MULTIUSER (off until Phase 6; with it off edge-bff reads none of these tables for access, the
-- switch-off principal keeps every capability and version "env").
--
-- New tables in the operational schema edge_bff: plans, capabilities, plan_capabilities, user_capability_overrides,
-- subscriptions. With the switch on, edge-bff resolves a session in one statement (app/accounts.py): the user's active,
-- unexpired subscription, else the default plan; that plan's plan_capabilities; the user's unexpired overrides, each
-- replacing the plan's value of its key. Expiry is decided at read time (expires_at > now()), never by a cron.
--
-- The seed below is the only place plan keys appear (a test greps apps/edge-bff/app for them): plans admin, paid and
-- free (the default), the capability rows with their plain-English meaning, and each plan's grants (CONTRACT.md 8a).
-- Value shapes by capabilities.kind, checked by edge-bff on read (a value of the wrong shape is ignored and logged):
--   flag: true; limit: a non-negative integer (no row = no limit); list: an array of strings;
--   items: {"ids": [...], "stages": [...], "all": bool}, each key optional; an item <family>:<id> is held when its id
--   is in ids, its release stage (apps/edge-bff/catalog/releases.json) is in stages, or all is true.
--
-- Grants to edge_bff_runtime only: the catalog (plans, capabilities, plan_capabilities) is read only (it is changed by
-- a migration or an operator, never by edge-bff); overrides and subscriptions are read, added and updated (admin,
-- Phase 4; the seed subscription of user #1), never deleted. Nothing to PUBLIC. Indexes beyond the keys: none (the
-- tables hold a few rows per user; AGENTS.md no speculative index). Forward-only; rollback block at the end (comment).
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'edge_bff' AND table_name = 'users'
                   AND column_name = 'registration_hash') THEN
        RAISE EXCEPTION 'edge_bff.users.registration_hash is missing: apply 20261117_002 first';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'edge_bff' AND table_name IN (
                   'plans', 'capabilities', 'plan_capabilities', 'user_capability_overrides', 'subscriptions')) THEN
        RAISE EXCEPTION 'an EDGE plan catalog table exists: reconcile before applying';
    END IF;
END $preflight$;

-- ---- plans ------------------------------------------------------------------------------------------------------------
CREATE TABLE edge_bff.plans (
    plan_key text PRIMARY KEY CHECK (plan_key ~ '^[a-z][a-z0-9_]{1,31}$'),
    display_name text NOT NULL CHECK (display_name = btrim(display_name) AND char_length(display_name) BETWEEN 1 AND 100),
    is_default boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
-- one default plan: the plan of a user with no active, unexpired subscription
CREATE UNIQUE INDEX plans_one_default ON edge_bff.plans ((true)) WHERE is_default;
COMMENT ON TABLE edge_bff.plans IS 'EDGE plans (EXEC-MU-ACCOUNTS Phase 2). Data, not code: edge-bff never names a plan; the default plan (one, is_default) is the plan of a user without an active, unexpired subscription.';
COMMENT ON COLUMN edge_bff.plans.is_default IS 'True for exactly one plan (plans_one_default): what a user without a live subscription, or whose subscription expired, receives.';

-- ---- capabilities -----------------------------------------------------------------------------------------------------
CREATE TABLE edge_bff.capabilities (
    capability_key text PRIMARY KEY CHECK (capability_key ~ '^[a-z*][a-z0-9_.*]{0,63}$'),
    kind text NOT NULL CHECK (kind IN ('flag', 'limit', 'list', 'items')),
    unit text CHECK (char_length(unit) BETWEEN 1 AND 40),
    means text NOT NULL CHECK (char_length(means) BETWEEN 1 AND 500),
    display_name text NOT NULL CHECK (char_length(display_name) BETWEEN 1 AND 100)
);
COMMENT ON TABLE edge_bff.capabilities IS 'What a plan can grant (the shape of terminal.quota): a flag (true), a limit (a non-negative integer; no row = no limit), a list (strings) or an item family (items: {ids, stages, all}; an item is <family>:<id>).';
COMMENT ON COLUMN edge_bff.capabilities.kind IS 'flag, limit, list or items; edge-bff checks each value against it on read and ignores (and logs) a value of the wrong shape.';
COMMENT ON COLUMN edge_bff.capabilities.means IS 'Plain-English meaning of the capability, for the admin page and the documentation.';

-- ---- plan_capabilities ------------------------------------------------------------------------------------------------
CREATE TABLE edge_bff.plan_capabilities (
    plan_key text NOT NULL REFERENCES edge_bff.plans(plan_key) ON DELETE CASCADE,
    capability_key text NOT NULL REFERENCES edge_bff.capabilities(capability_key) ON DELETE CASCADE,
    value jsonb NOT NULL,
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (plan_key, capability_key)
);
COMMENT ON TABLE edge_bff.plan_capabilities IS 'What each plan grants: one value per (plan, capability) in the shape of the capability kind. A change takes effect on the next request (no restart); raise version with it, it is part of the X-Edge-Entitlements fingerprint.';

-- ---- user_capability_overrides ----------------------------------------------------------------------------------------
CREATE TABLE edge_bff.user_capability_overrides (
    user_id bigint NOT NULL REFERENCES edge_bff.users(user_id) ON DELETE CASCADE,
    capability_key text NOT NULL REFERENCES edge_bff.capabilities(capability_key) ON DELETE CASCADE,
    value jsonb NOT NULL,
    reason text NOT NULL CHECK (char_length(btrim(reason)) BETWEEN 1 AND 1000),
    expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by_user_id bigint REFERENCES edge_bff.users(user_id) ON DELETE SET NULL,
    PRIMARY KEY (user_id, capability_key)
);
COMMENT ON TABLE edge_bff.user_capability_overrides IS 'One user''s value of a capability, replacing the plan''s value for that key (or adding it); set by an admin with a reason (audited, Phase 4). An override whose expires_at has passed is ignored at read time.';

-- ---- subscriptions ----------------------------------------------------------------------------------------------------
CREATE TABLE edge_bff.subscriptions (
    subscription_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES edge_bff.users(user_id) ON DELETE CASCADE,
    plan_key text NOT NULL REFERENCES edge_bff.plans(plan_key),
    status text NOT NULL CHECK (status IN ('pending', 'active', 'past_due', 'cancelled', 'expired', 'refunded')),
    starts_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at timestamptz,
    provider text NOT NULL CHECK (provider IN ('manual', 'test')),
    provider_ref text CHECK (char_length(provider_ref) BETWEEN 1 AND 200),
    last_event_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (expires_at IS NULL OR expires_at > starts_at)
);
-- one active subscription per user (it may still have expired: expiry is decided at read time)
CREATE UNIQUE INDEX subscriptions_one_active ON edge_bff.subscriptions(user_id) WHERE status = 'active';
COMMENT ON TABLE edge_bff.subscriptions IS 'A user''s plan over time. The live one is status active with starts_at <= now() and (expires_at IS NULL or expires_at > now()), decided at read time, never by a cron; without one the user has the default plan. provider manual at launch (the admin activates a plan), test for the tests.';
COMMENT ON COLUMN edge_bff.subscriptions.expires_at IS 'When the plan ends; NULL = no end. Past it the user resolves to the default plan and the session answer names the ended plan (access.expired_plan).';

-- ---- value shapes (C1 Phase 2 F1): a value that does not fit its capability's kind is refused when written --------
-- edge-bff also reads a wrong shape as the most restrictive value (app/principal.py read_grants), so a value that slips
-- past this check (a kind changed later) still never widens access. flag: true or false (false takes a plan's flag
-- away in an override); limit: a non-negative integer; list: an array of strings; items: an object with only ids
-- (strings), stages ("lab" or "released") and all (a boolean).
CREATE FUNCTION edge_bff.capability_value_check() RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
DECLARE
    k text;
    v jsonb := NEW.value;
    ok boolean;
BEGIN
    SELECT kind INTO k FROM edge_bff.capabilities WHERE capability_key = NEW.capability_key;
    ok := CASE k
        WHEN 'flag' THEN v IN ('true'::jsonb, 'false'::jsonb)
        WHEN 'limit' THEN jsonb_typeof(v) = 'number' AND v::text ~ '^[0-9]+$'
        WHEN 'list' THEN jsonb_typeof(v) = 'array'
            AND NOT EXISTS (SELECT 1 FROM jsonb_array_elements(v) e WHERE jsonb_typeof(e) <> 'string')
        WHEN 'items' THEN jsonb_typeof(v) = 'object'
            AND NOT EXISTS (SELECT 1 FROM jsonb_object_keys(v) x WHERE x NOT IN ('ids', 'stages', 'all'))
            AND (NOT v ? 'ids' OR (jsonb_typeof(v -> 'ids') = 'array'
                 AND NOT EXISTS (SELECT 1 FROM jsonb_array_elements(v -> 'ids') e WHERE jsonb_typeof(e) <> 'string')))
            AND (NOT v ? 'stages' OR (jsonb_typeof(v -> 'stages') = 'array'
                 AND NOT EXISTS (SELECT 1 FROM jsonb_array_elements(v -> 'stages') e
                                 WHERE e NOT IN ('"lab"'::jsonb, '"released"'::jsonb))))
            AND (NOT v ? 'all' OR jsonb_typeof(v -> 'all') = 'boolean')
        ELSE false END;
    IF NOT coalesce(ok, false) THEN
        RAISE EXCEPTION 'edge_bff.%: the value % does not fit capability % (kind %)', TG_TABLE_NAME, v, NEW.capability_key,
            coalesce(k, 'unknown')
            USING HINT = 'flag: true or false; limit: a non-negative integer such as 730; list: an array of strings '
                         'such as ["BBCA"]; items: {"ids": ["I01"], "stages": ["released"], "all": false}, each key optional';
    END IF;
    RETURN NEW;
END $fn$;
REVOKE ALL ON FUNCTION edge_bff.capability_value_check() FROM PUBLIC;
CREATE TRIGGER plan_capabilities_value_check BEFORE INSERT OR UPDATE ON edge_bff.plan_capabilities
    FOR EACH ROW EXECUTE FUNCTION edge_bff.capability_value_check();
CREATE TRIGGER user_capability_overrides_value_check BEFORE INSERT OR UPDATE ON edge_bff.user_capability_overrides
    FOR EACH ROW EXECUTE FUNCTION edge_bff.capability_value_check();
COMMENT ON FUNCTION edge_bff.capability_value_check() IS 'Refuses a plan_capabilities or user_capability_overrides value that does not fit its capability kind (flag true/false, limit non-negative integer, list of strings, items {ids, stages lab/released, all}); C1 Phase 2 F1.';
-- a capability's kind cannot change while a plan or an override holds a value of it (C1 Phase 2 re-check): the values
-- were checked against the old kind, and a limit read as another kind would be no limit
CREATE FUNCTION edge_bff.capability_kind_fixed() RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
BEGIN
    IF NEW.kind <> OLD.kind AND (
           EXISTS (SELECT 1 FROM edge_bff.plan_capabilities WHERE capability_key = OLD.capability_key)
        OR EXISTS (SELECT 1 FROM edge_bff.user_capability_overrides WHERE capability_key = OLD.capability_key)) THEN
        RAISE EXCEPTION 'edge_bff.capabilities: % is % and values of it exist; it cannot become %', OLD.capability_key,
            OLD.kind, NEW.kind
            USING HINT = 'Add a new capability with the new kind and move the plans and overrides to it in the same migration.';
    END IF;
    RETURN NEW;
END $fn$;
REVOKE ALL ON FUNCTION edge_bff.capability_kind_fixed() FROM PUBLIC;
CREATE TRIGGER capabilities_kind_fixed BEFORE UPDATE OF kind ON edge_bff.capabilities
    FOR EACH ROW EXECUTE FUNCTION edge_bff.capability_kind_fixed();
COMMENT ON FUNCTION edge_bff.capability_kind_fixed() IS 'Refuses a change of capabilities.kind while plan_capabilities or user_capability_overrides hold values of that capability (they were checked against the old kind).';

-- the role grants nothing from Phase 2 on (the Phase 1 comment said admin holds every capability)
COMMENT ON COLUMN edge_bff.users.role IS 'admin or user: the kind of account only. With EDGE_MULTIUSER on, what it may do comes from its plan (subscriptions, plan_capabilities) and overrides; MFA is required when those hold * or admin.access.';

-- ---- the seed (CONTRACT.md 8a): the only place plan keys appear --------------------------------------------------------
INSERT INTO edge_bff.plans(plan_key, display_name, is_default) VALUES
    ('admin', 'Admin', false),
    ('paid', 'Paid', false),
    ('free', 'Free', true);

INSERT INTO edge_bff.capabilities(capability_key, kind, unit, means, display_name) VALUES
    ('*', 'flag', NULL, 'Every capability, every item at any release stage (lab included). Meant for the operators of EDGE only.', 'Everything'),
    ('admin.access', 'flag', NULL, 'Opens the admin page and the admin routes; the account must pass two-step sign-in first.', 'Admin access'),
    ('backtest.flow_point_in_time', 'flag', NULL, 'Lets the Backtest and the Screener use the point-in-time versions of the Flow indicators.', 'Point-in-time Flow indicators'),
    ('monitor.view', 'flag', NULL, 'Opens the real Monitor (assistant) tab.', 'Monitor'),
    ('terminal.view', 'flag', NULL, 'Opens the real Terminal tab with live chart data.', 'Terminal'),
    ('backtest.view', 'flag', NULL, 'Opens the real Backtest tab.', 'Backtest'),
    ('screener.view', 'flag', NULL, 'Opens the real Screener tab.', 'Screener'),
    ('overview.view', 'flag', NULL, 'Opens the real Market Overview tab.', 'Market Overview'),
    ('radar.view', 'flag', NULL, 'Opens the real Radar tab.', 'Radar'),
    ('watchlist.view', 'flag', NULL, 'Opens the real Watchlist tab.', 'Watchlist'),
    ('monitor.example', 'flag', NULL, 'Shows a fixed example of the Monitor tab (no live data); every action asks to upgrade.', 'Monitor example'),
    ('terminal.example', 'flag', NULL, 'Shows a fixed example of the Terminal tab (no live data); every action asks to upgrade.', 'Terminal example'),
    ('backtest.example', 'flag', NULL, 'Shows a fixed example of the Backtest tab (no live data); every action asks to upgrade.', 'Backtest example'),
    ('screener.example', 'flag', NULL, 'Shows a fixed example of the Screener tab (no live data); every action asks to upgrade.', 'Screener example'),
    ('overview.example', 'flag', NULL, 'Shows a fixed example of the Market Overview tab (no live data); every action asks to upgrade.', 'Market Overview example'),
    ('radar.example', 'flag', NULL, 'Shows a fixed example of the Radar tab (no live data); every action asks to upgrade.', 'Radar example'),
    ('watchlist.example', 'flag', NULL, 'Shows a fixed example of the Watchlist tab (no live data); every action asks to upgrade.', 'Watchlist example'),
    ('monitor.chat', 'flag', NULL, 'Lets the account ask the assistant questions in the Monitor tab.', 'Ask the assistant'),
    ('backtest.run', 'flag', NULL, 'Lets the account run backtests.', 'Run backtests'),
    ('screener.run', 'flag', NULL, 'Lets the account run screens.', 'Run screens'),
    ('terminal.drawings', 'flag', NULL, 'Lets the account draw on Terminal charts and keep the drawings in the account.', 'Chart drawings'),
    ('terminal.layouts', 'flag', NULL, 'Lets the account save and reopen Terminal chart layouts.', 'Saved layouts'),
    ('terminal.compare', 'flag', NULL, 'Lets the account compare several tickers on one Terminal chart.', 'Compare tickers'),
    ('terminal.assets', 'flag', NULL, 'Lets the account add other assets (indices, cross-asset series) to Terminal charts.', 'Other assets'),
    ('watchlist.lists', 'limit', 'lists', 'The most watchlists the account may keep.', 'Watchlists'),
    ('watchlist.per_list', 'limit', 'tickers', 'The most tickers one watchlist may hold.', 'Tickers per watchlist'),
    ('watchlist.indicators', 'limit', 'indicators', 'The most indicator columns one watchlist may show.', 'Watchlist indicators'),
    ('terminal.tickers', 'list', 'tickers', 'The only tickers the Terminal shows to the account (no row: every ticker).', 'Terminal tickers'),
    ('terminal.history_days', 'limit', 'days', 'How many calendar days of history back from today the Terminal shows to the account.', 'Terminal history'),
    ('terminal.indicator', 'items', NULL, 'Which chart indicators the Terminal offers the account.', 'Terminal indicators'),
    ('terminal.flow_indicator', 'items', NULL, 'Which Flow (broker and investor flow) indicators the Terminal offers the account.', 'Terminal Flow indicators'),
    ('terminal.dataset', 'items', NULL, 'Which data sets (price, broker flow and others) the Terminal may load for the account.', 'Terminal data sets'),
    ('backtest.indicator', 'items', NULL, 'Which indicators a backtest of the account may use.', 'Backtest indicators'),
    ('backtest.flow_indicator', 'items', NULL, 'Which Flow indicators a backtest of the account may use.', 'Backtest Flow indicators'),
    ('backtest.candle_pattern', 'items', NULL, 'Which candlestick patterns a backtest of the account may use.', 'Backtest candle patterns'),
    ('screener.indicator', 'items', NULL, 'Which indicators a screen of the account may use.', 'Screener indicators'),
    ('screener.flow_indicator', 'items', NULL, 'Which Flow indicators a screen of the account may use.', 'Screener Flow indicators'),
    ('screener.candle_pattern', 'items', NULL, 'Which candlestick patterns a screen of the account may use.', 'Screener candle patterns'),
    ('screener.metric', 'items', NULL, 'Which Screener metrics (columns and conditions) the account may use.', 'Screener metrics'),
    ('screener.preset', 'items', NULL, 'Which ready-made Screener presets the account may open.', 'Screener presets'),
    ('monitor.model', 'items', NULL, 'Which AI models the account may choose in the Monitor tab.', 'Assistant models');

-- admin: every capability, every stage
INSERT INTO edge_bff.plan_capabilities(plan_key, capability_key, value) VALUES ('admin', '*', 'true');

-- paid: every real tab, every released item, every data set and model, the working flags and today's watchlist limits
INSERT INTO edge_bff.plan_capabilities(plan_key, capability_key, value)
SELECT 'paid', capability_key, 'true'::jsonb FROM edge_bff.capabilities
WHERE capability_key IN ('monitor.view', 'terminal.view', 'backtest.view', 'screener.view', 'overview.view', 'radar.view',
                         'watchlist.view', 'monitor.chat', 'backtest.run', 'screener.run', 'terminal.drawings',
                         'terminal.layouts', 'terminal.compare', 'terminal.assets');
INSERT INTO edge_bff.plan_capabilities(plan_key, capability_key, value)
SELECT 'paid', capability_key, '{"stages": ["released"]}'::jsonb FROM edge_bff.capabilities
WHERE kind = 'items' AND capability_key NOT IN ('terminal.dataset', 'monitor.model');
INSERT INTO edge_bff.plan_capabilities(plan_key, capability_key, value) VALUES
    ('paid', 'terminal.dataset', '{"all": true}'),
    ('paid', 'monitor.model', '{"all": true}'),
    ('paid', 'watchlist.lists', '20'),
    ('paid', 'watchlist.per_list', '50'),
    ('paid', 'watchlist.indicators', '8');

-- free (CONTRACT.md section 9): the Terminal on one ticker and the price data, two years back, no indicator yet (the
-- user picks two later); a static example of every other tab
INSERT INTO edge_bff.plan_capabilities(plan_key, capability_key, value) VALUES
    ('free', 'terminal.view', 'true'),
    ('free', 'terminal.dataset', '{"ids": ["price"]}'),
    ('free', 'terminal.tickers', '["BBCA"]'),
    ('free', 'terminal.history_days', '730'),
    ('free', 'terminal.indicator', '{"ids": []}'),
    ('free', 'monitor.example', 'true'),
    ('free', 'backtest.example', 'true'),
    ('free', 'screener.example', 'true'),
    ('free', 'overview.example', 'true'),
    ('free', 'radar.example', 'true'),
    ('free', 'watchlist.example', 'true');

-- ---- grants -----------------------------------------------------------------------------------------------------------
REVOKE ALL ON edge_bff.plans, edge_bff.capabilities, edge_bff.plan_capabilities, edge_bff.user_capability_overrides,
    edge_bff.subscriptions FROM PUBLIC;
GRANT SELECT ON edge_bff.plans, edge_bff.capabilities, edge_bff.plan_capabilities TO edge_bff_runtime;
GRANT SELECT, INSERT, UPDATE ON edge_bff.user_capability_overrides, edge_bff.subscriptions TO edge_bff_runtime;
REVOKE ALL ON SEQUENCE edge_bff.subscriptions_subscription_id_seq FROM PUBLIC;
GRANT USAGE ON SEQUENCE edge_bff.subscriptions_subscription_id_seq TO edge_bff_runtime;

DO $verify$
DECLARE
    expected constant jsonb := '{"plans": ["SELECT"], "capabilities": ["SELECT"], "plan_capabilities": ["SELECT"],
        "user_capability_overrides": ["SELECT","INSERT","UPDATE"], "subscriptions": ["SELECT","INSERT","UPDATE"]}';
    t text;
    p text;
BEGIN
    FOR t IN SELECT jsonb_object_keys(expected) LOOP
        FOREACH p IN ARRAY ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'] LOOP
            IF has_table_privilege('edge_bff_runtime', 'edge_bff.' || t, p) <> (expected -> t ? p) THEN
                RAISE EXCEPTION 'edge_bff_runtime % on edge_bff.%: expected %', p, t, (expected -> t ? p);
            END IF;
            IF has_table_privilege('public', 'edge_bff.' || t, p) THEN
                RAISE EXCEPTION 'PUBLIC holds % on edge_bff.%', p, t;
            END IF;
        END LOOP;
    END LOOP;
    IF NOT has_sequence_privilege('edge_bff_runtime', 'edge_bff.subscriptions_subscription_id_seq', 'USAGE')
       OR has_sequence_privilege('edge_bff_runtime', 'edge_bff.subscriptions_subscription_id_seq', 'SELECT')
       OR has_sequence_privilege('edge_bff_runtime', 'edge_bff.subscriptions_subscription_id_seq', 'UPDATE')
       OR has_sequence_privilege('public', 'edge_bff.subscriptions_subscription_id_seq', 'USAGE, SELECT, UPDATE') THEN
        RAISE EXCEPTION 'sequence edge_bff.subscriptions_subscription_id_seq grants differ from USAGE for edge_bff_runtime only';
    END IF;
    -- the seed: three plans, one default, exactly one plan holding every capability, every grant of its kind's shape
    IF (SELECT count(*) FROM edge_bff.plans) <> 3 OR (SELECT count(*) FROM edge_bff.plans WHERE is_default) <> 1 THEN
        RAISE EXCEPTION 'the seed plans differ from three with one default';
    END IF;
    IF (SELECT count(DISTINCT plan_key) FROM edge_bff.plan_capabilities WHERE capability_key = '*') <> 1 THEN
        RAISE EXCEPTION 'exactly one plan must hold *';
    END IF;
    IF (SELECT count(*) FROM edge_bff.capabilities) <> 41 THEN
        RAISE EXCEPTION 'the seed capabilities differ from the 41 of CONTRACT.md 8a';
    END IF;
    IF EXISTS (SELECT 1 FROM edge_bff.plan_capabilities pc JOIN edge_bff.capabilities c USING (capability_key)
               WHERE NOT CASE c.kind
                   WHEN 'flag' THEN pc.value = 'true'::jsonb
                   WHEN 'limit' THEN jsonb_typeof(pc.value) = 'number' AND pc.value::text ~ '^[0-9]+$'
                   WHEN 'list' THEN jsonb_typeof(pc.value) = 'array'
                   ELSE jsonb_typeof(pc.value) = 'object' END) THEN
        RAISE EXCEPTION 'a seed grant does not have the shape of its capability kind';
    END IF;
    IF (SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal AND tgname IN ('plan_capabilities_value_check',
            'user_capability_overrides_value_check', 'capabilities_kind_fixed')) <> 3 THEN
        RAISE EXCEPTION 'the three value-shape triggers are missing';
    END IF;
    IF EXISTS (SELECT 1 FROM edge_bff.subscriptions) OR EXISTS (SELECT 1 FROM edge_bff.user_capability_overrides) THEN
        RAISE EXCEPTION 'subscriptions or overrides are not empty after their creation';
    END IF;
END $verify$;
COMMIT;

-- Rollback (a new forward migration with this body; deploy the previous edge-bff first, which reads none of these, or
-- keep EDGE_MULTIUSER off; the subscriptions and overrides are lost):
-- BEGIN;
-- DROP TABLE edge_bff.subscriptions, edge_bff.user_capability_overrides, edge_bff.plan_capabilities,
--     edge_bff.capabilities, edge_bff.plans;
-- DROP FUNCTION edge_bff.capability_value_check(), edge_bff.capability_kind_fixed();
-- COMMIT;
