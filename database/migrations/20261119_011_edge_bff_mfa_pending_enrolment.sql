-- EDGE multi-user, fix round of the ultracode re-check (EXEC-MU-ACCOUNTS; verification/edge_multiuser/fix_round/auth.md;
-- contract verification/edge_multiuser/access_tiers/CONTRACT.md section 4 "Admin MFA"), behind the switch EDGE_MULTIUSER
-- (off until Phase 6; with it off nothing reads these tables).
-- ERRORS R1-7: a new enrolment of an admin's authenticator overwrote the one mfa_totp row at once (confirmed_at NULL,
-- the recovery codes deleted), so from the moment an admin who had passed MFA began setting up a new phone, the account
-- had no confirmed second factor: a password-only session could enrol its own authenticator and take the admin's.
-- Now a confirmed enrolment and a new one wait side by side:
--   mfa_totp.pending_nonce / pending_created_at  the new enrolment's nonce (its TOTP secret is HMAC(EDGE_MFA_KEY,
--                                                user_id || nonce), never stored) while it is not confirmed;
--   mfa_recovery_codes.pending                   the new enrolment's recovery codes, never accepted until it is.
-- The first code of the new authenticator (app/auth_flows.py use_step) moves pending_nonce to nonce and makes its
-- recovery codes the account's; until then the confirmed authenticator, its replay guard (last_step) and its recovery
-- codes keep working. A first enrolment (no confirmed one yet) still uses nonce with confirmed_at NULL.
-- No grant changes (edge_bff_runtime already holds SELECT, INSERT, UPDATE, DELETE on both tables). No index: every read
-- and write is by user_id (mfa_totp's primary key; mfa_recovery_codes' primary key (user_id, code_hash)).
-- Forward-only; refuses a second run; rollback block at the end (comment).
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'edge_bff' AND table_name = 'mfa_totp'
                   AND column_name = 'totp_failures') THEN
        RAISE EXCEPTION 'edge_bff.mfa_totp.totp_failures is missing: apply 20261117_002 first';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'edge_bff'
               AND ((table_name = 'mfa_totp' AND column_name IN ('pending_nonce', 'pending_created_at'))
                    OR (table_name = 'mfa_recovery_codes' AND column_name = 'pending'))) THEN
        RAISE EXCEPTION 'a column of this migration exists: reconcile before applying';
    END IF;
END $preflight$;

ALTER TABLE edge_bff.mfa_totp
    ADD COLUMN pending_nonce bytea CHECK (octet_length(pending_nonce) = 16),
    ADD COLUMN pending_created_at timestamptz,
    -- a new enrolment waits only beside a confirmed one, and never names the confirmed nonce
    ADD CONSTRAINT mfa_totp_pending CHECK ((pending_nonce IS NULL) = (pending_created_at IS NULL)
        AND (pending_nonce IS NULL OR (confirmed_at IS NOT NULL AND pending_nonce <> nonce)));
COMMENT ON COLUMN edge_bff.mfa_totp.pending_nonce IS 'A new enrolment begun by a session that passed MFA, waiting for its first code; the confirmed nonce keeps working until then (use_step makes it the nonce).';
COMMENT ON COLUMN edge_bff.mfa_totp.pending_created_at IS 'When the waiting enrolment (pending_nonce) was begun.';

ALTER TABLE edge_bff.mfa_recovery_codes
    ADD COLUMN pending boolean NOT NULL DEFAULT false;
COMMENT ON COLUMN edge_bff.mfa_recovery_codes.pending IS 'A code of the waiting enrolment (mfa_totp.pending_nonce): never accepted; becomes the account''s (false) when that enrolment is confirmed, and the old codes are deleted then.';

DO $verify$
BEGIN
    IF EXISTS (SELECT 1 FROM edge_bff.mfa_totp WHERE pending_nonce IS NOT NULL)
       OR EXISTS (SELECT 1 FROM edge_bff.mfa_recovery_codes WHERE pending) THEN
        RAISE EXCEPTION 'an enrolment starts as waiting';
    END IF;
    IF NOT has_table_privilege('edge_bff_runtime', 'edge_bff.mfa_totp', 'UPDATE')
       OR NOT has_table_privilege('edge_bff_runtime', 'edge_bff.mfa_recovery_codes', 'UPDATE')
       OR has_table_privilege('public', 'edge_bff.mfa_totp', 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE')
       OR has_table_privilege('public', 'edge_bff.mfa_recovery_codes', 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE') THEN
        RAISE EXCEPTION 'the grants of the MFA tables differ from 20261116_003';
    END IF;
END $verify$;
COMMIT;

-- Rollback (a new forward migration with this body; deploy the previous edge-bff first; a waiting enrolment is lost,
-- its admin begins it again):
-- BEGIN;
-- DELETE FROM edge_bff.mfa_recovery_codes WHERE pending;
-- ALTER TABLE edge_bff.mfa_recovery_codes DROP COLUMN pending;
-- ALTER TABLE edge_bff.mfa_totp DROP CONSTRAINT mfa_totp_pending, DROP COLUMN pending_nonce,
--     DROP COLUMN pending_created_at;
-- COMMIT;
