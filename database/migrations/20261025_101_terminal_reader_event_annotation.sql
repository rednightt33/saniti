-- EXEC-TERMINAL-API T6 (user 2026-10-25: "boleh, masukan EXEC"): the terminal publisher and API may read
-- public.idx_event_annotation (created by 20261025_013 on main) to publish per-ticker event files.
-- Numbered 101 so it cannot collide with the sequential 20261025 migrations of other sessions.
-- Rollback: REVOKE SELECT ON public.idx_event_annotation FROM terminal_market_reader;
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'terminal_market_reader') THEN
        RAISE EXCEPTION 'terminal_market_reader missing: apply 20261025_001 first';
    END IF;
    IF to_regclass('public.idx_event_annotation') IS NULL THEN
        RAISE EXCEPTION 'public.idx_event_annotation missing: apply 20261025_013 first';
    END IF;
END $preflight$;
GRANT SELECT ON public.idx_event_annotation TO terminal_market_reader;
COMMIT;
