-- EDGE multi-user, 3c check fixes (EXEC-MU-ACCOUNTS; the user, 2026-11-19, on an overall ceiling for every visitor of
-- the guest plan: "2A tapi harus bisa di set dibackend variable ya batasannya"): no ceiling now, but one that a backend
-- variable sets. edge-bff counts every Terminal call of every visitor together in edge_bff.auth_throttle under the new
-- scope 'guest_total', only while EDGE_GUEST_CALLS_PER_HOUR is set above 0 (app/config.py; unset: nothing is counted),
-- and answers a call beyond it 429 LIMIT_REACHED (details.limit 'guest_total', the visitor's words).
--
-- Expand only: the scope CHECK of 20261116_002 gains one value; no row changes, and an older edge-bff never writes the
-- new scope. No grant changes: edge_bff_runtime already reads and writes auth_throttle (20261116_002). Refuses a second
-- run. Forward-only; rollback block at the end (comment).
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF to_regclass('edge_bff.auth_throttle') IS NULL THEN
        RAISE EXCEPTION 'edge_bff.auth_throttle is missing: apply 20261116_002 first';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'edge_bff.auth_throttle'::regclass
                   AND conname = 'auth_throttle_scope_check') THEN
        RAISE EXCEPTION 'edge_bff.auth_throttle has no auth_throttle_scope_check: this migration ran already or the '
                        'table differs from 20261116_002';
    END IF;
    IF pg_get_constraintdef((SELECT oid FROM pg_constraint WHERE conrelid = 'edge_bff.auth_throttle'::regclass
                             AND conname = 'auth_throttle_scope_check')) LIKE '%guest_total%' THEN
        RAISE EXCEPTION 'auth_throttle_scope_check already holds guest_total: this migration ran already';
    END IF;
END $preflight$;

ALTER TABLE edge_bff.auth_throttle DROP CONSTRAINT auth_throttle_scope_check;
ALTER TABLE edge_bff.auth_throttle ADD CONSTRAINT auth_throttle_scope_check
    CHECK (scope IN ('signin_email', 'signin_ip', 'code_user', 'send_email', 'send_ip', 'guest_total'));
COMMENT ON CONSTRAINT auth_throttle_scope_check ON edge_bff.auth_throttle IS
    'The throttle scopes; guest_total (20261119_071) counts every visitor''s Terminal calls together while '
    'EDGE_GUEST_CALLS_PER_HOUR is set.';

DO $verify$
BEGIN
    IF pg_get_constraintdef((SELECT oid FROM pg_constraint WHERE conrelid = 'edge_bff.auth_throttle'::regclass
                             AND conname = 'auth_throttle_scope_check')) NOT LIKE '%guest_total%' THEN
        RAISE EXCEPTION 'verify: auth_throttle_scope_check does not hold guest_total';
    END IF;
    IF NOT has_table_privilege('edge_bff_runtime', 'edge_bff.auth_throttle', 'INSERT, UPDATE, SELECT, DELETE') THEN
        RAISE EXCEPTION 'verify: edge_bff_runtime lost a grant on edge_bff.auth_throttle';
    END IF;
END $verify$;
COMMIT;

-- Rollback (a new forward migration with this body; edge-bff counts nothing while EDGE_GUEST_CALLS_PER_HOUR is unset):
-- BEGIN;
-- DELETE FROM edge_bff.auth_throttle WHERE scope = 'guest_total';
-- ALTER TABLE edge_bff.auth_throttle DROP CONSTRAINT auth_throttle_scope_check;
-- ALTER TABLE edge_bff.auth_throttle ADD CONSTRAINT auth_throttle_scope_check
--     CHECK (scope IN ('signin_email', 'signin_ip', 'code_user', 'send_email', 'send_ip'));
-- COMMIT;
