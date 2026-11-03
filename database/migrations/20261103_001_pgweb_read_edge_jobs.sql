-- EXEC-PG-RESTART-CRON (user go 2026-11-03: "Go langkah 1–9, tafsiran toggle benar, setuju"), step 4.
-- scripts/restart_postgres.py refuses a restart while a user run is active (ERRORS M340: edge_bff.jobs QUEUED, RUNNING
-- or RECOVERING). An agent session reads the database only through pgweb (role pgweb, read-only), which was refused
-- ("permission denied for schema edge_bff"). Grant it the two columns the guard reads, nothing else of edge_bff.
BEGIN;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pgweb') THEN
    RAISE EXCEPTION 'role pgweb is missing';
  END IF;
  IF to_regclass('edge_bff.jobs') IS NULL THEN
    RAISE EXCEPTION 'table edge_bff.jobs is missing';
  END IF;
END $$;

GRANT USAGE ON SCHEMA edge_bff TO pgweb;
GRANT SELECT (state, updated_at) ON edge_bff.jobs TO pgweb;

COMMIT;
