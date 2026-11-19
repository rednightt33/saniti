-- EDGE beta and live websites (EXEC-MU-ACCOUNTS "Production environment", user decisions 2026-11-19: one Railway
-- environment, two edge-bff services on one database; ERRORS R2-7, R2-13, R2-23, R2-38). The AI job queue
-- edge_bff.jobs gains `site`: the website a run was queued on, 'beta' (the service edge-bff, its Railway address, the
-- admin only) or 'live' (edge-bff-live, the user's domain). Each edge-bff claims only the runs of its own site
-- (app/store.py claim, EDGE_SITE), so a run is dispatched by the code and the rules of the site that took it, never by
-- the other website's loop. Every row that exists is the beta's (the admin's runs on edge-bff), so the default is
-- 'beta'; edge-bff writes the column explicitly from now on.
--
-- A constant default and a CHECK on the new column: Postgres adds the column without rewriting the table (PG 11+) and
-- validates the CHECK in one scan. No index: the claim reads the existing partial index edge_bff_claim (created_at,
-- the active states only), whose rows are a handful at any time; the site filter is applied on them (EXPLAIN in the
-- fix-round notes, verification/edge_multiuser/fix_round/site.md). No grant changes (a new column of a table
-- edge_bff_runtime already reads and writes). Forward-only; refuses a second run; rollback block at the end (comment).
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF to_regclass('edge_bff.jobs') IS NULL THEN
        RAISE EXCEPTION 'edge_bff.jobs is missing: apply 20261008_002 first';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'edge_bff' AND table_name = 'jobs'
               AND column_name = 'site') THEN
        RAISE EXCEPTION 'edge_bff.jobs.site exists: reconcile before applying';
    END IF;
END $preflight$;

ALTER TABLE edge_bff.jobs ADD COLUMN site text NOT NULL DEFAULT 'beta' CONSTRAINT jobs_site CHECK (site IN ('beta', 'live'));
COMMENT ON COLUMN edge_bff.jobs.site IS 'The website the run was queued on: beta (edge-bff, the admin only) or live (edge-bff-live). Only that site''s worker claims it (EDGE_SITE); rows before 2026-11-19 are the beta''s.';

DO $verify$
BEGIN
    IF (SELECT column_default FROM information_schema.columns WHERE table_schema = 'edge_bff' AND table_name = 'jobs'
        AND column_name = 'site' AND is_nullable = 'NO') IS DISTINCT FROM '''beta''::text' THEN
        RAISE EXCEPTION 'edge_bff.jobs.site is not NOT NULL DEFAULT beta';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'edge_bff.jobs'::regclass AND conname = 'jobs_site'
                   AND convalidated) THEN
        RAISE EXCEPTION 'the check jobs_site is missing or not validated';
    END IF;
    IF EXISTS (SELECT 1 FROM edge_bff.jobs WHERE site <> 'beta') THEN
        RAISE EXCEPTION 'a run that existed before this migration is not the beta''s';
    END IF;
    IF NOT (has_table_privilege('edge_bff_runtime', 'edge_bff.jobs', 'SELECT')
            AND has_table_privilege('edge_bff_runtime', 'edge_bff.jobs', 'INSERT')
            AND has_table_privilege('edge_bff_runtime', 'edge_bff.jobs', 'UPDATE')) THEN
        RAISE EXCEPTION 'edge_bff_runtime lost a grant on edge_bff.jobs';
    END IF;
END $verify$;
COMMIT;

-- Rollback (a new forward migration with this body, after every edge-bff runs a build that does not read the column:
-- edge-bff's readiness reads edge_bff.jobs.site, app/store.py ready):
-- BEGIN;
-- ALTER TABLE edge_bff.jobs DROP COLUMN site;
-- COMMIT;
