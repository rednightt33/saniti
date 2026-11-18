-- EXEC-MU-ACCOUNTS Phase 3c, T2 (user go 2026-11-18: "Ok, lanjutkan fase selanjutnya"; EXEC.md EXEC-MU-ACCOUNTS;
-- verification/edge_multiuser/access_tiers/CONTRACT.md section 7 "terminal-api" Phase 3 and section 8b "3c in detail"):
-- one terminal.subscriber row per EDGE owner, so terminal-api counts usage and writes audit rows per owner instead of
-- on the one gateway account, and the audit row carries the owner's entitlements version.
-- - terminal.subscriber.edge_owner_key: the EDGE owner key edge-bff sends in x-terminal-proxy-owner (the rule of Orc's
--   X-Saniti-Owner, ^[A-Za-z0-9._:@-]{1,128}$), unique; null for every other row (a person, the gateway account, a
--   service account). terminal-api makes the row on first use (apps/terminal-api/app/store.py owner_account,
--   INSERT ... ON CONFLICT DO NOTHING, then a read: race-safe).
-- - kind 'owner' beside 'person' and 'service'; a row is kind owner exactly when it has an edge_owner_key. The columns
--   that stay NOT NULL get: a synthetic address no mail reaches, owner-<first 32 hex of sha256(owner key)>@
--   edge-owner.terminal.local (store.py owner_email), the display name "EDGE owner <key>", the all-zero scrypt verifier
--   no password derives (an owner never signs in: sign-in and sessions take kind person only) and the end
--   2100-01-01 of the service accounts. No quota_override row is made for an owner: an admin owner takes the gateway
--   subscriber's own limits, the others the terminal.quota defaults overlaid by the plan (decision D6, main.py
--   limits_of); the gateway's 1e9 override stays on the gateway's row only.
-- - terminal.access_log.version: the entitlements version of x-terminal-capabilities (edge-bff principal.version, e.g.
--   'env' or 'db-0123456789ab'); null for a call without the owner headers and for every existing row. Its check is
--   added NOT VALID: the existing rows (all null) are not scanned, and every new row is checked.
-- Operational schema terminal: no Table/Column_Catalog row (as 20261025_100, 20261026_100 and 20261028_100). No market
-- table, role, login, grant or existing row changes: terminal_runtime reaches the new columns through its existing
-- table grants (SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA terminal, 20261025_100). Applied once: the
-- preflight refuses a second run. Rollback block at the end (comment).
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF to_regclass('terminal.subscriber') IS NULL OR to_regclass('terminal.access_log') IS NULL
       OR to_regclass('terminal.usage_hour') IS NULL THEN
        RAISE EXCEPTION 'terminal schema or terminal.usage_hour is missing: apply 20261025_100 and 20261028_100 first';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'terminal.subscriber'::regclass
                   AND conname = 'subscriber_kind_check') THEN
        RAISE EXCEPTION 'terminal.subscriber.kind with subscriber_kind_check is missing: apply 20261028_100 first';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'terminal'
               AND table_name = 'subscriber' AND column_name = 'edge_owner_key') THEN
        RAISE EXCEPTION 'terminal.subscriber.edge_owner_key exists: already applied';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'terminal'
               AND table_name = 'access_log' AND column_name = 'version') THEN
        RAISE EXCEPTION 'terminal.access_log.version exists: reconcile before applying';
    END IF;
    -- a person on the synthetic owner domain would look like an owner's row: reconcile first
    IF EXISTS (SELECT 1 FROM terminal.subscriber WHERE email LIKE '%@edge-owner.terminal.local') THEN
        RAISE EXCEPTION 'a subscriber uses the owner address domain edge-owner.terminal.local: reconcile before applying';
    END IF;
END $preflight$;

ALTER TABLE terminal.subscriber
    ADD COLUMN edge_owner_key text
        CONSTRAINT subscriber_edge_owner_key_key UNIQUE
        CONSTRAINT subscriber_edge_owner_key_check CHECK (edge_owner_key ~ '^[A-Za-z0-9._:@-]{1,128}$');
ALTER TABLE terminal.subscriber DROP CONSTRAINT subscriber_kind_check;
ALTER TABLE terminal.subscriber
    ADD CONSTRAINT subscriber_kind_check CHECK (kind IN ('person', 'service', 'owner')),
    ADD CONSTRAINT subscriber_owner_has_key CHECK ((kind = 'owner') = (edge_owner_key IS NOT NULL));

ALTER TABLE terminal.access_log ADD COLUMN version text;
ALTER TABLE terminal.access_log
    ADD CONSTRAINT access_log_version_check CHECK (version IS NULL OR version ~ '^[A-Za-z0-9._:-]{1,64}$') NOT VALID;

COMMENT ON COLUMN terminal.subscriber.edge_owner_key IS
    'EXEC-MU-ACCOUNTS Phase 3c: the EDGE owner key of a kind owner row (x-terminal-proxy-owner from edge-bff, beside the gateway key); made by terminal-api on first use, unique; null for every other row.';
COMMENT ON COLUMN terminal.subscriber.kind IS
    'person: a subscriber or the EDGE gateway account (rolling quotas from terminal.access_log); service: a worker''s own account, reached only with its TERMINAL_SERVICE_KEY_<NAME>, never signed into, counted per clock hour in terminal.usage_hour (EXEC-MU-RUNTIME T1); owner: one EDGE owner behind the gateway key (edge_owner_key), never signed into, its own rolling usage and audit (EXEC-MU-ACCOUNTS Phase 3c).';
COMMENT ON COLUMN terminal.access_log.version IS
    'EXEC-MU-ACCOUNTS Phase 3c: the entitlements version of x-terminal-capabilities the row was granted under; null without the owner headers and for rows before 20261118_100.';

DO $verify$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'terminal' AND table_name = 'subscriber'
                   AND column_name = 'edge_owner_key' AND is_nullable = 'YES' AND data_type = 'text') THEN
        RAISE EXCEPTION 'terminal.subscriber.edge_owner_key is not a nullable text column';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'terminal.subscriber'::regclass
                   AND conname = 'subscriber_edge_owner_key_key' AND contype = 'u') THEN
        RAISE EXCEPTION 'terminal.subscriber.edge_owner_key is not unique';
    END IF;
    IF (SELECT count(*) FROM pg_constraint WHERE conrelid = 'terminal.subscriber'::regclass AND contype = 'c'
        AND conname IN ('subscriber_kind_check', 'subscriber_owner_has_key', 'subscriber_edge_owner_key_check')) <> 3
       OR pg_get_constraintdef((SELECT oid FROM pg_constraint WHERE conrelid = 'terminal.subscriber'::regclass
                                AND conname = 'subscriber_kind_check')) NOT LIKE '%owner%' THEN
        RAISE EXCEPTION 'the kind and owner key checks of terminal.subscriber are not in place';
    END IF;
    -- every existing row keeps its kind and gets no owner key
    IF EXISTS (SELECT 1 FROM terminal.subscriber WHERE kind = 'owner' OR edge_owner_key IS NOT NULL) THEN
        RAISE EXCEPTION 'an existing subscriber became an owner row';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'terminal' AND table_name = 'access_log'
                   AND column_name = 'version' AND is_nullable = 'YES' AND data_type = 'text')
       OR NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'terminal.access_log'::regclass
                      AND conname = 'access_log_version_check' AND contype = 'c') THEN
        RAISE EXCEPTION 'terminal.access_log.version or its check is missing';
    END IF;
    -- terminal-api reads and writes the new columns through its existing table grants
    IF NOT (has_column_privilege('terminal_runtime', 'terminal.subscriber', 'edge_owner_key', 'SELECT')
            AND has_column_privilege('terminal_runtime', 'terminal.subscriber', 'edge_owner_key', 'INSERT')
            AND has_column_privilege('terminal_runtime', 'terminal.access_log', 'version', 'SELECT')
            AND has_column_privilege('terminal_runtime', 'terminal.access_log', 'version', 'INSERT')) THEN
        RAISE EXCEPTION 'terminal_runtime cannot use terminal.subscriber.edge_owner_key or terminal.access_log.version';
    END IF;
    -- and its login inherits it, where the login exists (scripts/provision_terminal_logins.py)
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'terminal_api_login')
       AND NOT (has_column_privilege('terminal_api_login', 'terminal.subscriber', 'edge_owner_key', 'INSERT')
                AND has_column_privilege('terminal_api_login', 'terminal.access_log', 'version', 'INSERT')) THEN
        RAISE EXCEPTION 'terminal_api_login does not reach terminal.subscriber.edge_owner_key and terminal.access_log.version';
    END IF;
END $verify$;
COMMIT;

-- Rollback (a new forward migration with this body), only after terminal-api runs code that does not read
-- edge_owner_key or version (its /ready lists both, app/store.py READY) and edge-bff no longer sends the owner headers:
-- BEGIN;
-- DELETE FROM terminal.subscriber WHERE kind = 'owner';   -- cascades their audit rows, sessions and overrides
-- ALTER TABLE terminal.access_log DROP CONSTRAINT access_log_version_check, DROP COLUMN version;
-- ALTER TABLE terminal.subscriber DROP CONSTRAINT subscriber_owner_has_key, DROP CONSTRAINT subscriber_kind_check;
-- ALTER TABLE terminal.subscriber ADD CONSTRAINT subscriber_kind_check CHECK (kind IN ('person', 'service'));
-- ALTER TABLE terminal.subscriber DROP COLUMN edge_owner_key;
-- COMMIT;
