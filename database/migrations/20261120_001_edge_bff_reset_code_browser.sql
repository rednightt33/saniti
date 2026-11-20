-- EDGE multi-user, the A2 fix (EXEC.md option A, the next execution, item 2; the user, 2026-11-20: "perbaikan A2",
-- then "Go"; ERRORS M513 A2 and M517): a password reset's code is bound to the browser that asked for it, so a stranger
-- who knows an account's address can neither use up the owner's code with wrong tries nor replace it with a request of
-- its own. edge-bff writes binding_hash, the SHA-256 of the browser's HttpOnly reset cookie (app/auth_flows.py
-- RESET_COOKIE), on every reset code it makes, and checks a code only against the browser's own (or one without a
-- binding, made before this change); a registration's codes stay bound by its own cookie and keep binding_hash NULL.
--
-- One live code per account, purpose AND browser binding: the unique index email_codes_one_live (user_id, purpose) is
-- replaced by email_codes_one_live_per_browser (user_id, purpose, coalesce(binding_hash, '')), so the owner's reset code
-- stays live beside a stranger's.
--
-- Expand only: a nullable column without a default (no row is rewritten) and an index that admits what the old one
-- admitted. An older edge-bff writes binding_hash NULL and consumes every live code of an account and purpose before it
-- makes one, so it keeps one live code per account and purpose under the new index too. No query of edge-bff reads
-- email_codes with `*`, so no running plan changes its result type (ERRORS M511). No grant changes: edge_bff_runtime
-- already reads and writes email_codes (20261116_003). Refuses a second run. Forward-only; rollback block at the end.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF to_regclass('edge_bff.email_codes') IS NULL THEN
        RAISE EXCEPTION 'edge_bff.email_codes is missing: apply 20261116_003 first';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'edge_bff' AND table_name = 'email_codes'
               AND column_name = 'binding_hash') THEN
        RAISE EXCEPTION 'edge_bff.email_codes.binding_hash exists: this migration ran already';
    END IF;
    IF to_regclass('edge_bff.email_codes_one_live') IS NULL THEN
        RAISE EXCEPTION 'edge_bff.email_codes_one_live is missing: the table differs from 20261116_003';
    END IF;
END $preflight$;

ALTER TABLE edge_bff.email_codes ADD COLUMN binding_hash text
    CONSTRAINT email_codes_binding_hash CHECK (binding_hash ~ '^[0-9a-f]{64}$');
COMMENT ON COLUMN edge_bff.email_codes.binding_hash IS
    'reset only: SHA-256 of the HttpOnly reset cookie of the browser that asked for the code (20261120_001, the A2 fix); '
    'the code is checked only from that browser. NULL: a registration''s or an email change''s code (bound by its own '
    'cookie or session), or a reset code made before 20261120_001.';
CREATE UNIQUE INDEX email_codes_one_live_per_browser ON edge_bff.email_codes (user_id, purpose, coalesce(binding_hash, ''))
    WHERE consumed_at IS NULL;
DROP INDEX edge_bff.email_codes_one_live;
COMMENT ON TABLE edge_bff.email_codes IS
    'Six-digit email codes (register, reset, email_change): HMAC-SHA256 with EDGE_CODE_SECRET, valid 300 s, at most 5 '
    'tries, one live code per user, purpose and browser binding (binding_hash, 20261120_001).';

DO $verify$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'edge_bff' AND table_name = 'email_codes'
                   AND column_name = 'binding_hash' AND is_nullable = 'YES' AND column_default IS NULL) THEN
        RAISE EXCEPTION 'verify: edge_bff.email_codes.binding_hash is missing or not a nullable column without a default';
    END IF;
    IF to_regclass('edge_bff.email_codes_one_live_per_browser') IS NULL
       OR to_regclass('edge_bff.email_codes_one_live') IS NOT NULL THEN
        RAISE EXCEPTION 'verify: the one-live-code index was not replaced';
    END IF;
    IF NOT (SELECT indisunique FROM pg_index WHERE indexrelid = 'edge_bff.email_codes_one_live_per_browser'::regclass) THEN
        RAISE EXCEPTION 'verify: email_codes_one_live_per_browser is not unique';
    END IF;
    IF NOT has_table_privilege('edge_bff_runtime', 'edge_bff.email_codes', 'INSERT, UPDATE, SELECT, DELETE') THEN
        RAISE EXCEPTION 'verify: edge_bff_runtime lost a grant on edge_bff.email_codes';
    END IF;
END $verify$;
COMMIT;

-- Rollback (a new forward migration with this body, once no edge-bff that writes binding_hash runs; a reset code of
-- another browser is then live beside the account's, so the bound ones are ended first):
-- BEGIN;
-- UPDATE edge_bff.email_codes SET consumed_at = now() WHERE binding_hash IS NOT NULL AND consumed_at IS NULL;
-- CREATE UNIQUE INDEX email_codes_one_live ON edge_bff.email_codes (user_id, purpose) WHERE consumed_at IS NULL;
-- DROP INDEX edge_bff.email_codes_one_live_per_browser;
-- ALTER TABLE edge_bff.email_codes DROP COLUMN binding_hash;
-- COMMIT;
