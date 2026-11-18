-- EDGE multi-user Phase 3c (EXEC-MU-ACCOUNTS; user go 2026-11-18 "Ok, lanjutkan fase selanjutnya"; decision D6 of the
-- user 2026-11-17, EXEC.md; contract verification/edge_multiuser/access_tiers/CONTRACT.md 8b "3c in detail", Quotas):
-- the Terminal quota limits per owner that edge-bff sends to terminal-api in x-terminal-capabilities `quota`
-- (app/terminal_access.py QUOTA), behind the switch EDGE_MULTIUSER (off until Phase 6; with it off edge-bff reads none
-- of these rows, the switch-off principal of the configured owner holds '*' and its header is admin, which keeps the
-- gateway subscriber's own limits on terminal-api).
--
-- New capabilities (edge_bff.capabilities, kind limit), each named as terminal-api's quota of the same name
-- (apps/terminal-api/app/quota.py check):
--   terminal.tickers_per_hour   limit  tickers   different tickers opened in a rolling hour      (paid and free 60)
--   terminal.tickers_per_day    limit  tickers   different tickers opened in a rolling 24 hours  (paid and free 200)
--   terminal.files_per_hour     limit  files     data files read in a rolling hour               (paid and free 300)
--   terminal.megabytes_per_day  limit  megabytes data read in a rolling 24 hours                (paid and free 500)
-- The paid values are decision D6 ("the Terminal quota per owner is 60 tickers per hour, 200 per day, 300 files per hour
-- and 500 MB per day"). ASSUMPTION (the user may change it): the free plan gets the same numbers; it reads only BBCA's
-- daily price (decision D3), so the ticker limits do not bind it. history_per_hour has no row: terminal-api keeps its
-- default (20). The admin plan holds '*' and gets no row: its header says admin and terminal-api uses the gateway
-- subscriber's own limits. A limit a plan leaves out is left out of the header, and terminal-api keeps its
-- terminal.quota default for it (never "unlimited").
--
-- No table, grant or index changes (the catalog tables of 20261117_003 are already granted SELECT to edge_bff_runtime,
-- scripts/provision_edge_bff_login.py CATALOG_GRANTS). The capability_value_check trigger of 20261117_003 checks every
-- new value against its kind when it is written. Plan keys appear only in the seed migrations (tests/test_plan_catalog.py
-- greps apps/edge-bff/app for them). Forward-only; refuses a second run; rollback block at the end (comment).
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF to_regclass('edge_bff.capabilities') IS NULL OR to_regclass('edge_bff.plan_capabilities') IS NULL
       OR NOT EXISTS (SELECT 1 FROM pg_trigger WHERE NOT tgisinternal AND tgname = 'plan_capabilities_value_check') THEN
        RAISE EXCEPTION 'the EDGE plan catalog is missing: apply 20261117_003 first';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM edge_bff.capabilities WHERE capability_key = 'terminal.layouts_max') THEN
        RAISE EXCEPTION 'the Phase 3a catalog rows are missing: apply 20261117_004 first';
    END IF;
    IF EXISTS (SELECT 1 FROM edge_bff.capabilities WHERE capability_key IN ('terminal.tickers_per_hour',
                   'terminal.tickers_per_day', 'terminal.files_per_hour', 'terminal.megabytes_per_day')) THEN
        RAISE EXCEPTION 'a Phase 3c Terminal quota capability exists already: reconcile before applying';
    END IF;
    IF (SELECT count(*) FROM edge_bff.plans WHERE plan_key IN ('paid', 'free')) <> 2 THEN
        RAISE EXCEPTION 'the paid or free plan of 20261117_003 is missing: reconcile before applying';
    END IF;
END $preflight$;

-- ---- the new capability rows ------------------------------------------------------------------------------------------
INSERT INTO edge_bff.capabilities(capability_key, kind, unit, means, display_name) VALUES
    ('terminal.tickers_per_hour', 'limit', 'tickers', 'The most different tickers the account may open in the Terminal within a rolling hour.', 'Tickers per hour'),
    ('terminal.tickers_per_day', 'limit', 'tickers', 'The most different tickers the account may open in the Terminal within a rolling 24 hours.', 'Tickers per day'),
    ('terminal.files_per_hour', 'limit', 'files', 'The most market data files the account may load within a rolling hour (the Terminal and the Radar, Overview and Watchlist pages together).', 'Data files per hour'),
    ('terminal.megabytes_per_day', 'limit', 'megabytes', 'The most market data, in megabytes, the account may load within a rolling 24 hours.', 'Data per day');

-- ---- the paid and free plans (decision D6; the free plan's numbers are an assumption, see above) -------------------
INSERT INTO edge_bff.plan_capabilities(plan_key, capability_key, value) VALUES
    ('paid', 'terminal.tickers_per_hour', '60'),
    ('paid', 'terminal.tickers_per_day', '200'),
    ('paid', 'terminal.files_per_hour', '300'),
    ('paid', 'terminal.megabytes_per_day', '500'),
    ('free', 'terminal.tickers_per_hour', '60'),
    ('free', 'terminal.tickers_per_day', '200'),
    ('free', 'terminal.files_per_hour', '300'),
    ('free', 'terminal.megabytes_per_day', '500');

DO $verify$
DECLARE
    quota constant jsonb := '{"terminal.tickers_per_hour": 60, "terminal.tickers_per_day": 200,
        "terminal.files_per_hour": 300, "terminal.megabytes_per_day": 500}';
    units constant jsonb := '{"terminal.tickers_per_hour": "tickers", "terminal.tickers_per_day": "tickers",
        "terminal.files_per_hour": "files", "terminal.megabytes_per_day": "megabytes"}';
    k text;
    p text;
BEGIN
    FOR k IN SELECT jsonb_object_keys(quota) LOOP
        IF NOT EXISTS (SELECT 1 FROM edge_bff.capabilities WHERE capability_key = k AND kind = 'limit'
                       AND unit = units ->> k AND length(means) > 0 AND length(display_name) > 0) THEN
            RAISE EXCEPTION 'the capability % is not a limit in % with its means and display name', k, units ->> k;
        END IF;
        FOREACH p IN ARRAY ARRAY['paid', 'free'] LOOP
            IF (SELECT value FROM edge_bff.plan_capabilities WHERE plan_key = p AND capability_key = k)
               IS DISTINCT FROM quota -> k THEN
                RAISE EXCEPTION 'the % plan does not hold % = %', p, k, quota -> k;
            END IF;
        END LOOP;
        IF EXISTS (SELECT 1 FROM edge_bff.plan_capabilities WHERE capability_key = k AND plan_key NOT IN ('paid', 'free')) THEN
            RAISE EXCEPTION 'a plan other than paid and free holds % (the plan holding * needs no row)', k;
        END IF;
    END LOOP;
    IF EXISTS (SELECT 1 FROM edge_bff.plan_capabilities pc JOIN edge_bff.plan_capabilities star
               ON star.plan_key = pc.plan_key AND star.capability_key = '*'
               WHERE pc.capability_key IN (SELECT jsonb_object_keys(quota))) THEN
        RAISE EXCEPTION 'the plan holding * holds a Terminal quota row';
    END IF;
    IF (SELECT count(DISTINCT plan_key) FROM edge_bff.plan_capabilities WHERE capability_key = '*') <> 1 THEN
        RAISE EXCEPTION 'exactly one plan must hold *';
    END IF;
    IF EXISTS (SELECT 1 FROM edge_bff.capabilities WHERE kind = 'limit' AND unit IS NULL) THEN
        RAISE EXCEPTION 'a limit capability has no unit';
    END IF;
END $verify$;
COMMIT;

-- Rollback (a new forward migration with this body; edge-bff then sends no quota in the header and terminal-api keeps
-- its terminal.quota defaults for every owner; with EDGE_MULTIUSER off the switch-off principal reads no catalog row):
-- BEGIN;
-- DELETE FROM edge_bff.capabilities WHERE capability_key IN ('terminal.tickers_per_hour', 'terminal.tickers_per_day',
--     'terminal.files_per_hour', 'terminal.megabytes_per_day');  -- cascades to plan_capabilities and overrides
-- COMMIT;
