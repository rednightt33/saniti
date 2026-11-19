-- EXEC-MU-ACCOUNTS fix round, track guest (decision 1 of 2026-11-19, the user: "1a - bukan hanya chart, nanti ada
-- indikator dll yg juga mungkin di show ke user. jadi design harus plug and play dan fluid, karna ticker dan indikatornya
-- bisa berubah"; EXEC.md EXEC-MU-ACCOUNTS "Decisions from the fix round"; verification/edge_multiuser/fix_round/
-- guest.md): a visitor without an account opens the Terminal. Every visitor reaches terminal-api under one EDGE owner
-- (edge-bff's guest owner, one terminal.subscriber row of kind owner, 20261118_100), and the per-owner quota of Phase 3c
-- cannot hold one row per visitor, so edge-bff names each visitor by an opaque key of its client address
-- (x-terminal-client: an HMAC edge-bff makes, 32 hex; never the address) and terminal-api counts that owner's quotas per
-- visitor.
-- - terminal.access_log.client_key: the visitor key of a guest's call; null for every other call and every existing
--   row. Its check is added NOT VALID: the existing rows (all null) are not scanned, and every new row is checked.
-- - index access_log_client_at (subscriber_id, client_key, at DESC) WHERE client_key IS NOT NULL: the usage read of each
--   guest grant (app/store.py usage, frees_in) is per visitor; without it every grant would read every visitor's rows of
--   the day under the one guest row (EXPLAIN evidence: guest.md "EXPLAIN evidence"). Partial: no other row is indexed,
--   so the build reads the table once and writes only the rows of guests (none yet).
-- Operational schema terminal: no Table/Column_Catalog row (as 20261025_100 ... 20261118_100). No market table, role,
-- login, grant or existing row changes: terminal_runtime reaches the column through its existing table grants (SELECT,
-- INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA terminal, 20261025_100). Applied once: the preflight refuses a second
-- run. The index build reads terminal.access_log once (90 days of audit rows): AGENTS.md "Postgres memory after large
-- updates" (an index on a large table) applies after it. Rollback block at the end (comment).
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '10min';
DO $preflight$
BEGIN
    IF to_regclass('terminal.access_log') IS NULL THEN
        RAISE EXCEPTION 'terminal.access_log is missing: apply 20261025_100 first';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'terminal'
                   AND table_name = 'access_log' AND column_name = 'version') THEN
        RAISE EXCEPTION 'terminal.access_log.version is missing: apply 20261118_100 first';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'terminal'
               AND table_name = 'access_log' AND column_name = 'client_key') THEN
        RAISE EXCEPTION 'terminal.access_log.client_key exists: already applied';
    END IF;
    IF to_regclass('terminal.access_log_client_at') IS NOT NULL THEN
        RAISE EXCEPTION 'the index terminal.access_log_client_at exists: reconcile before applying';
    END IF;
END $preflight$;

ALTER TABLE terminal.access_log ADD COLUMN client_key text;
ALTER TABLE terminal.access_log
    ADD CONSTRAINT access_log_client_key_check CHECK (client_key IS NULL OR client_key ~ '^[0-9a-f]{32}$') NOT VALID;
CREATE INDEX access_log_client_at ON terminal.access_log (subscriber_id, client_key, at DESC)
    WHERE client_key IS NOT NULL;

COMMENT ON COLUMN terminal.access_log.client_key IS
    'EXEC-MU-ACCOUNTS track guest: the visitor key (x-terminal-client, 32 hex, an HMAC edge-bff makes of the client address; never the address) of a call for a visitor of the guest plan, whose quotas are counted per visitor under the guest owner row; null for every other call and for rows before 20261119_170.';
COMMENT ON INDEX terminal.access_log_client_at IS
    'Track guest: the usage read of a guest grant, per visitor of the one guest owner row (app/store.py usage, frees_in).';

DO $verify$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'terminal' AND table_name = 'access_log'
                   AND column_name = 'client_key' AND is_nullable = 'YES' AND data_type = 'text')
       OR NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'terminal.access_log'::regclass
                      AND conname = 'access_log_client_key_check' AND contype = 'c') THEN
        RAISE EXCEPTION 'terminal.access_log.client_key or its check is missing';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
                   WHERE c.oid = 'terminal.access_log_client_at'::regclass AND i.indisvalid
                   AND pg_get_expr(i.indpred, i.indrelid) LIKE '%client_key IS NOT NULL%') THEN
        RAISE EXCEPTION 'the partial index terminal.access_log_client_at is missing or not valid';
    END IF;
    IF EXISTS (SELECT 1 FROM terminal.access_log WHERE client_key IS NOT NULL) THEN
        RAISE EXCEPTION 'an existing audit row has a visitor key';
    END IF;
    -- terminal-api reads and writes the column through its existing table grants
    IF NOT (has_column_privilege('terminal_runtime', 'terminal.access_log', 'client_key', 'SELECT')
            AND has_column_privilege('terminal_runtime', 'terminal.access_log', 'client_key', 'INSERT')) THEN
        RAISE EXCEPTION 'terminal_runtime cannot use terminal.access_log.client_key';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'terminal_api_login')
       AND NOT has_column_privilege('terminal_api_login', 'terminal.access_log', 'client_key', 'INSERT') THEN
        RAISE EXCEPTION 'terminal_api_login does not reach terminal.access_log.client_key';
    END IF;
END $verify$;
COMMIT;

-- Rollback (a new forward migration with this body), only after terminal-api runs code that does not read client_key
-- (its /ready lists it, app/store.py READY) and edge-bff no longer sends x-terminal-client:
-- BEGIN;
-- DROP INDEX terminal.access_log_client_at;
-- ALTER TABLE terminal.access_log DROP CONSTRAINT access_log_client_key_check, DROP COLUMN client_key;
-- COMMIT;
