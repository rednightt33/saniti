-- EDGE beta and live websites (EXEC-MU-ACCOUNTS "Production environment", user decisions 2026-11-19: one Railway
-- environment, two edge-bff services on one database; ERRORS R2-7, R2-13, R2-23, R2-38). The backtest queue
-- edge_bff.backtest_jobs gains `site`: the website a backtest was queued on, 'beta' (the service edge-bff, the admin
-- only) or 'live' (edge-bff-live, the user's domain). Both websites run a backtest loop; each claims, reaps and prunes
-- only its own site's jobs (app/backtest.py BacktestStore, EDGE_SITE), so a paid account's backtest queued on the live
-- site is dispatched under the live site's principal and release file, never by the beta's loop (the probe of R2-7:
-- a switch-off loop ended a switch-on account's job FAILED CAPABILITY_REQUIRED). One running job per owner stays one
-- rule over both sites (backtest_jobs_one_running_owner). Every row that exists is the beta's (the admin's backtests on
-- edge-bff), so the default is 'beta'; edge-bff writes the column explicitly from now on.
--
-- A constant default and a CHECK on the new column: added without a table rewrite (PG 11+), the CHECK validated in one
-- scan. No index: the claim reads the existing partial index backtest_jobs_claim (created_at, QUEUED and RUNNING
-- only), whose rows are a handful; the site filter is applied on them (EXPLAIN in the fix-round notes,
-- verification/edge_multiuser/fix_round/site.md). No grant changes. Separate from 20261119_020 so that a test which
-- takes 20261026_005 out and puts it back can put this column back too. Forward-only; refuses a second run; rollback
-- block at the end (comment).
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF to_regclass('edge_bff.backtest_jobs') IS NULL THEN
        RAISE EXCEPTION 'edge_bff.backtest_jobs is missing: apply 20261026_005 first';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'edge_bff' AND table_name = 'backtest_jobs'
               AND column_name = 'site') THEN
        RAISE EXCEPTION 'edge_bff.backtest_jobs.site exists: reconcile before applying';
    END IF;
END $preflight$;

ALTER TABLE edge_bff.backtest_jobs ADD COLUMN site text NOT NULL DEFAULT 'beta'
    CONSTRAINT backtest_jobs_site CHECK (site IN ('beta', 'live'));
COMMENT ON COLUMN edge_bff.backtest_jobs.site IS 'The website the backtest was queued on: beta (edge-bff, the admin only) or live (edge-bff-live). Only that site''s loop claims, reaps and prunes it (EDGE_SITE); rows before 2026-11-19 are the beta''s.';

DO $verify$
BEGIN
    IF (SELECT column_default FROM information_schema.columns WHERE table_schema = 'edge_bff'
        AND table_name = 'backtest_jobs' AND column_name = 'site' AND is_nullable = 'NO') IS DISTINCT FROM '''beta''::text' THEN
        RAISE EXCEPTION 'edge_bff.backtest_jobs.site is not NOT NULL DEFAULT beta';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'edge_bff.backtest_jobs'::regclass
                   AND conname = 'backtest_jobs_site' AND convalidated) THEN
        RAISE EXCEPTION 'the check backtest_jobs_site is missing or not validated';
    END IF;
    IF EXISTS (SELECT 1 FROM edge_bff.backtest_jobs WHERE site <> 'beta') THEN
        RAISE EXCEPTION 'a backtest that existed before this migration is not the beta''s';
    END IF;
    -- what app/backtest.py does to the jobs and no more (20261026_005): jobs are never deleted
    IF NOT (has_table_privilege('edge_bff_runtime', 'edge_bff.backtest_jobs', 'SELECT')
            AND has_table_privilege('edge_bff_runtime', 'edge_bff.backtest_jobs', 'INSERT')
            AND has_table_privilege('edge_bff_runtime', 'edge_bff.backtest_jobs', 'UPDATE'))
       OR has_table_privilege('edge_bff_runtime', 'edge_bff.backtest_jobs', 'DELETE') THEN
        RAISE EXCEPTION 'edge_bff_runtime does not hold exactly SELECT, INSERT and UPDATE on edge_bff.backtest_jobs';
    END IF;
END $verify$;
COMMIT;

-- Rollback (a new forward migration with this body, after every edge-bff runs a build that does not read the column):
-- BEGIN;
-- ALTER TABLE edge_bff.backtest_jobs DROP COLUMN site;
-- COMMIT;
