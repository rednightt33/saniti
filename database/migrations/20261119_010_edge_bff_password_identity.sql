-- EDGE multi-user, fix round of the ultracode re-check (EXEC-MU-ACCOUNTS; verification/edge_multiuser/fix_round/auth.md;
-- contract verification/edge_multiuser/access_tiers/CONTRACT.md section 4). The password identity of an account
-- (edge_bff.identities, 20261116_003), behind the switch EDGE_MULTIUSER (off until Phase 6: with it off edge-bff only
-- copies EDGE_PASSWORD_VERIFIER into user #1's identity and reads none of the new columns). Two changes:
-- 1. ERRORS R2-29 (OWASP Password Storage Cheat Sheet: scrypt N=2^17, r=8, p=1, or an equivalent such as N=2^14, r=8,
--    p=5): a verifier may name its cost, 'scrypt$n=16384,r=8,p=5$<salt hex 32>$<hash hex 64>' (app/security.py, every
--    new verifier). The form before it, 'scrypt$<salt>$<hash>' (N=2^14, r=8, p=1), stays valid: edge-bff reads both and
--    replaces the old one at the account's next sign-in (accounts.py create_session `rehash`). The CHECK
--    identities_password is replaced by one that accepts both; edge-bff accepts only the costs it lists (security.py
--    COSTS), the CHECK only the shape.
-- 2. ERRORS R1-16 (NIST SP 800-63B-4 3.2.2: at most 100 consecutive failed attempts per subscriber account): the
--    consecutive failed passwords of the account over both its logins (username and email) and every client address
--    (sign_in_failures), and the end of the lock the 100th starts (sign_in_locked_until, 24 h). A success, a password
--    reset proved by the email code or a change sets them back to 0 and NULL (ERRORS R1-9: the way back); after a lock
--    the count restarts at 90 (as the MFA counts of 20261117_002, decision N2 of ERRORS M478).
-- No grant changes (edge_bff_runtime already holds SELECT, INSERT, UPDATE, DELETE on identities). No index: every read
-- and write of these columns is by the primary key's user_id (UNIQUE (user_id, provider)). Forward-only; refuses a
-- second run; rollback block at the end (comment).
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF to_regclass('edge_bff.identities') IS NULL OR NOT EXISTS (SELECT 1 FROM pg_constraint
            WHERE conrelid = 'edge_bff.identities'::regclass AND conname = 'identities_password') THEN
        RAISE EXCEPTION 'edge_bff.identities or its identities_password check is missing: apply 20261116_003 first';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'edge_bff' AND table_name = 'identities'
               AND column_name IN ('sign_in_failures', 'sign_in_locked_until')) THEN
        RAISE EXCEPTION 'a column of this migration exists: reconcile before applying';
    END IF;
END $preflight$;

ALTER TABLE edge_bff.identities
    DROP CONSTRAINT identities_password,
    -- a password identity: its subject is the user_id and its verifier one of the two scrypt forms of app/security.py
    ADD CONSTRAINT identities_password CHECK (provider <> 'password' OR (subject = user_id::text
        AND verifier ~ '^scrypt\$(n=[0-9]{1,7},r=[0-9]{1,2},p=[0-9]{1,2}\$)?[0-9a-f]{32}\$[0-9a-f]{64}$')),
    ADD COLUMN sign_in_failures integer NOT NULL DEFAULT 0 CHECK (sign_in_failures >= 0),
    ADD COLUMN sign_in_locked_until timestamptz;
COMMENT ON COLUMN edge_bff.identities.verifier IS 'Password: scrypt$n=<N>,r=<r>,p=<p>$<salt hex>$<hash hex> (app/security.py COST, N=2^14 r=8 p=5), or the form before 20261119_010, scrypt$<salt>$<hash> (N=2^14 r=8 p=1), replaced at the next sign-in.';
COMMENT ON COLUMN edge_bff.identities.sign_in_failures IS 'Consecutive failed passwords of the account (both logins, every client address), counted before each check; at 100 sign-in is locked 24 h (answered as a wrong password); a success, a reset by email code or a change sets 0 (NIST SP 800-63B-4).';
COMMENT ON COLUMN edge_bff.identities.sign_in_locked_until IS 'When the password lock the 100th consecutive failure started ends; NULL = no lock. After it the count restarts at 90.';

DO $verify$
BEGIN
    IF EXISTS (SELECT 1 FROM edge_bff.identities WHERE provider = 'password' AND sign_in_failures <> 0) THEN
        RAISE EXCEPTION 'an identity starts with failures';
    END IF;
    -- the existing verifiers (the form before this migration) still satisfy the new check: it was re-validated by the
    -- ADD CONSTRAINT above; both forms are accepted, nothing else is
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'edge_bff.identities'::regclass
                   AND conname = 'identities_password' AND convalidated) THEN
        RAISE EXCEPTION 'identities_password is missing or not validated';
    END IF;
    IF NOT has_table_privilege('edge_bff_runtime', 'edge_bff.identities', 'UPDATE')
       OR has_table_privilege('public', 'edge_bff.identities', 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE') THEN
        RAISE EXCEPTION 'the grants of edge_bff.identities differ from 20261116_003';
    END IF;
END $verify$;
COMMIT;

-- Rollback (a new forward migration with this body; deploy an edge-bff that writes only the old form first). The old
-- check is added NOT VALID (3c check C3-24: the block runs as written on a database that holds verifiers of the new
-- form): it binds every new write, and the rows of the new form stay; those accounts cannot sign in on the old code
-- (the old form cannot hold their cost) until a reset writes them a verifier of the old form:
-- BEGIN;
-- ALTER TABLE edge_bff.identities DROP COLUMN sign_in_failures, DROP COLUMN sign_in_locked_until,
--     DROP CONSTRAINT identities_password,
--     ADD CONSTRAINT identities_password CHECK (provider <> 'password' OR (subject = user_id::text
--         AND verifier ~ '^scrypt\$[0-9a-f]{32}\$[0-9a-f]{64}$')) NOT VALID;
-- COMMIT;
