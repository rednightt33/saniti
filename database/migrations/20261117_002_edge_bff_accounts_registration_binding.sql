-- EDGE multi-user Phase 1, fix round after the independent checkers (EXEC-MU-ACCOUNTS; ERRORS M478: C1 P1-H1, C2 #1,
-- C1 P1-M2). Two changes to the account tables of 20261116_003 / 20261117_001:
-- 1. Pending-registration takeover: a registration of an address whose account was still pending replaced that
--    account's password, so whoever registered last owned the account once the mailbox owner entered the newest code.
--    Now every registration is its own pending row, bound to the browser that started it: registration_hash is the
--    SHA-256 of a random token in that browser's HttpOnly registration cookie, and a code activates only the row whose
--    cookie comes with it (app/auth_flows.py). An address may therefore have several pending rows; it still has at most
--    one account that is not pending (the unique email index below replaces the column's UNIQUE).
-- 2. MFA guessing (NIST SP 800-63B-4, at most 100 consecutive failures per account): mfa_totp counts consecutive failed
--    TOTP codes and failed recovery codes; only a success (or an admin, later) resets them; at 100 TOTP failures the
--    authenticator code is refused (MFA_LOCKED), at 10 recovery failures the recovery codes are.
-- Forward-only; rollback block at the end (comment).
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'edge_bff' AND table_name = 'users'
                   AND column_name = 'requested_username') THEN
        RAISE EXCEPTION 'edge_bff.users.requested_username is missing: apply 20261117_001 first';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'edge_bff'
               AND ((table_name = 'users' AND column_name = 'registration_hash')
                    OR (table_name = 'mfa_totp' AND column_name IN ('totp_failures', 'recovery_failures')))) THEN
        RAISE EXCEPTION 'a column of this migration exists: reconcile before applying';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'edge_bff.users'::regclass AND conname = 'users_email_key') THEN
        RAISE EXCEPTION 'edge_bff.users_email_key is missing: reconcile before applying';
    END IF;
END $preflight$;

ALTER TABLE edge_bff.users
    ADD COLUMN registration_hash text UNIQUE CHECK (registration_hash ~ '^[0-9a-f]{64}$'),
    ADD CONSTRAINT users_registration_pending CHECK (registration_hash IS NULL OR status = 'pending'),
    DROP CONSTRAINT users_email_key;
-- one account per address among the active and disabled ones; pending registrations of an address may be several
CREATE UNIQUE INDEX users_email_one_account ON edge_bff.users(email) WHERE status <> 'pending';
COMMENT ON COLUMN edge_bff.users.registration_hash IS 'Pending registration only: SHA-256 of the random token in the HttpOnly registration cookie of the browser that registered; the email code activates this row only with that cookie. NULL once active.';
COMMENT ON COLUMN edge_bff.users.email IS 'Lower-cased; one active or disabled account per address (users_email_one_account); several pending registrations may name it until one is verified (the others are then deleted). Optional for the seed.';

ALTER TABLE edge_bff.mfa_totp
    ADD COLUMN totp_failures integer NOT NULL DEFAULT 0 CHECK (totp_failures >= 0),
    ADD COLUMN recovery_failures integer NOT NULL DEFAULT 0 CHECK (recovery_failures >= 0);
COMMENT ON COLUMN edge_bff.mfa_totp.totp_failures IS 'Consecutive wrong authenticator codes; reset only by a correct code or recovery code; at 100 the authenticator code is refused (MFA_LOCKED).';
COMMENT ON COLUMN edge_bff.mfa_totp.recovery_failures IS 'Consecutive wrong recovery codes; reset only by a success; at 10 the recovery codes are refused (MFA_LOCKED).';

DO $verify$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'edge_bff.users'::regclass AND conname = 'users_email_key') THEN
        RAISE EXCEPTION 'users_email_key is still there';
    END IF;
    IF EXISTS (SELECT email FROM edge_bff.users WHERE status <> 'pending' AND email IS NOT NULL GROUP BY email HAVING count(*) > 1) THEN
        RAISE EXCEPTION 'two accounts share an address';
    END IF;
END $verify$;
COMMIT;

-- Rollback (a new forward migration with this body; deploy the previous edge-bff first; extra pending registrations of
-- an address are deleted):
-- BEGIN;
-- DELETE FROM edge_bff.users u WHERE status = 'pending' AND EXISTS (SELECT 1 FROM edge_bff.users o WHERE o.email = u.email
--     AND o.user_id <> u.user_id AND (o.status <> 'pending' OR o.user_id > u.user_id));
-- DROP INDEX edge_bff.users_email_one_account;
-- ALTER TABLE edge_bff.users DROP CONSTRAINT users_registration_pending, DROP COLUMN registration_hash,
--     ADD CONSTRAINT users_email_key UNIQUE (email);
-- ALTER TABLE edge_bff.mfa_totp DROP COLUMN totp_failures, DROP COLUMN recovery_failures;
-- COMMIT;
