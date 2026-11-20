-- EDGE multi-user, the A2 fix, its checker's finding CW-2 (EXEC.md option A, the next execution, item 2; ERRORS M517):
-- the client address a pending registration came from. A sign-in compares its password with the newest
-- PENDING_CHECKED (3) pending registrations of the address only (app/accounts.py, so every sign-in costs the same), and
-- since the A2 fix a registration's hourly and daily counts are the address's from one client: one stranger on one
-- client could register an address three times and push its owner's pending registration out of those three, so the
-- owner's sign-in no longer moved its registration to the browser it signs in on (ERRORS M478, C1 P1-M1). edge-bff now
-- writes registration_client_hash, the HMAC of the client address a registration came from (the same keyed hash as
-- sessions.created_ip_hash, app/throttle.py), and a sign-in compares the newest registration of each client
-- (accounts.pending_logins): one stranger on one client fills one of the three places, so the owner's stays among them
-- unless three or more other clients registered the address since (the residual ERRORS M517 states). No registration
-- is changed or removed by it (ERRORS M478, R1-11).
--
-- Expand only: a nullable column without a default (no row is rewritten). An older edge-bff never writes or reads it;
-- rows it makes keep NULL, each counts as a client of its own, and they are purged 24 h after they were made. No query of
-- edge-bff reads edge_bff.users with `*` (ERRORS M511). No grant changes: edge_bff_runtime already reads and writes
-- users (20261116_003). Refuses a second run. Forward-only; rollback block at the end.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF to_regclass('edge_bff.users') IS NULL THEN
        RAISE EXCEPTION 'edge_bff.users is missing: apply 20261116_003 first';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'edge_bff' AND table_name = 'users'
               AND column_name = 'registration_client_hash') THEN
        RAISE EXCEPTION 'edge_bff.users.registration_client_hash exists: this migration ran already';
    END IF;
END $preflight$;

ALTER TABLE edge_bff.users ADD COLUMN registration_client_hash text
    CONSTRAINT users_registration_client_hash CHECK (registration_client_hash ~ '^[0-9a-f]{64}$');
COMMENT ON COLUMN edge_bff.users.registration_client_hash IS
    'pending only: HMAC-SHA256 (EDGE_SESSION_SECRET, the client-address label of app/throttle.py) of the client address '
    'the registration came from (20261120_002, the A2 fix); a sign-in compares the newest pending registration of each '
    'client. NULL for a registration made before 20261120_002.';

DO $verify$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'edge_bff' AND table_name = 'users'
                   AND column_name = 'registration_client_hash' AND is_nullable = 'YES' AND column_default IS NULL) THEN
        RAISE EXCEPTION 'verify: edge_bff.users.registration_client_hash is missing or not a nullable column without a default';
    END IF;
    IF NOT has_table_privilege('edge_bff_runtime', 'edge_bff.users', 'INSERT, UPDATE, SELECT, DELETE') THEN
        RAISE EXCEPTION 'verify: edge_bff_runtime lost a grant on edge_bff.users';
    END IF;
END $verify$;
COMMIT;

-- Rollback (a new forward migration with this body, once no edge-bff that writes the column runs):
-- BEGIN;
-- ALTER TABLE edge_bff.users DROP COLUMN registration_client_hash;
-- COMMIT;
