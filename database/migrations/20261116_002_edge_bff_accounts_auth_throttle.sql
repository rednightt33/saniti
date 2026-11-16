-- EDGE multi-user Phase 0 (EXEC-MU-ACCOUNTS; contract verification/edge_multiuser/access_tiers/CONTRACT.md sections 1
-- and 4 "Throttle"): the sign-in throttle moves from edge-bff's process memory (app/main.py, a dict per client address,
-- lost at every restart and not shared between app instances) into PostgreSQL, so every instance counts the same
-- failures. One new table in the operational schema edge_bff, used by edge_bff_runtime only. It holds no login, email or
-- address in clear: key_hash is HMAC-SHA256 with EDGE_SESSION_SECRET of the normalised key (app/throttle.py). No other
-- table, role or grant changes. Forward-only; rollback block at the end (comment).
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'edge_bff') OR
       NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'edge_bff_runtime') THEN
        RAISE EXCEPTION 'edge_bff schema/role is missing: apply 20261008_002 first';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'edge_bff' AND table_name = 'auth_throttle') THEN
        RAISE EXCEPTION 'edge_bff.auth_throttle exists: reconcile before applying';
    END IF;
END $preflight$;

-- One row per (scope, key, one-minute bucket): count is the failures (or sends) of that key in the bucket. A limit sums
-- the buckets of its window (sign-in: 10 failures per login in 15 minutes), so the window slides by the minute. Every
-- write is one atomic UPSERT (INSERT ... ON CONFLICT DO UPDATE SET count = count + 1), so several app instances never
-- lose a count. Scopes (contract section 1): signin_email (the login typed at sign-in, a username or an email; enforced),
-- signin_ip (the client address; recorded, not enforced until the Railway address probe, contract section 4), and the
-- Phase 1 scopes code_user, send_email, send_ip. Rows older than 2 days are deleted by edge-bff's worker loop.
CREATE TABLE edge_bff.auth_throttle (
    scope text NOT NULL CHECK (scope IN ('signin_email', 'signin_ip', 'code_user', 'send_email', 'send_ip')),
    key_hash text NOT NULL CHECK (key_hash ~ '^[0-9a-f]{64}$'),
    window_start timestamptz NOT NULL,
    count integer NOT NULL DEFAULT 1 CHECK (count > 0),
    PRIMARY KEY (scope, key_hash, window_start)
);
-- No other index: a limit reads one (scope, key_hash) prefix of the primary key, and the purge (window_start older
-- than 2 days) reads a table of at most a few thousand rows (AGENTS.md: no speculative index).

COMMENT ON TABLE edge_bff.auth_throttle IS 'EDGE sign-in and email throttle (EXEC-MU-ACCOUNTS Phase 0): failures or sends per scope, hashed key and one-minute bucket; shared by every edge-bff instance; rows older than 2 days are purged by the worker loop.';
COMMENT ON COLUMN edge_bff.auth_throttle.scope IS 'signin_email (login typed at sign-in; enforced), signin_ip (client address; recorded only until the Railway address probe), code_user, send_email, send_ip (Phase 1).';
COMMENT ON COLUMN edge_bff.auth_throttle.key_hash IS 'HMAC-SHA256 with EDGE_SESSION_SECRET of the normalised key (app/throttle.py); never the login, email or address itself.';
COMMENT ON COLUMN edge_bff.auth_throttle.window_start IS 'Start of the one-minute bucket the counts fall in; a limit sums the buckets of its window.';
COMMENT ON COLUMN edge_bff.auth_throttle.count IS 'Failures (or sends) of the key in the bucket, raised by one atomic UPSERT per event.';

-- What edge-bff (apps/edge-bff/app/throttle.py, store.py cleanup_sessions) does to it and no more: read, counted
-- (insert or update) and purged.
REVOKE ALL ON edge_bff.auth_throttle FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON edge_bff.auth_throttle TO edge_bff_runtime;
DO $verify$
BEGIN
    -- one privilege per call: has_table_privilege with a list is true when any one of them is held
    IF EXISTS (SELECT 1 FROM unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE']) AS needed(privilege)
               WHERE NOT has_table_privilege('edge_bff_runtime', 'edge_bff.auth_throttle', privilege)) THEN
        RAISE EXCEPTION 'edge_bff_runtime cannot use edge_bff.auth_throttle';
    END IF;
    -- and nothing else: TRUNCATE would reset every throttle at once
    IF has_table_privilege('edge_bff_runtime', 'edge_bff.auth_throttle', 'TRUNCATE, REFERENCES, TRIGGER') THEN
        RAISE EXCEPTION 'edge_bff_runtime has more than edge_bff.auth_throttle needs';
    END IF;
    IF has_table_privilege('public', 'edge_bff.auth_throttle', 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER') THEN
        RAISE EXCEPTION 'PUBLIC can use edge_bff.auth_throttle';
    END IF;
END $verify$;
COMMIT;

-- Rollback (a new forward migration with this body; edge-bff from this migration on needs the table, so deploy the
-- previous edge-bff first):
-- BEGIN;
-- DROP TABLE edge_bff.auth_throttle;
-- COMMIT;
