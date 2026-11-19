-- EDGE beta and live websites (EXEC-MU-ACCOUNTS "Production environment", user decisions 2026-11-19; ERRORS R2-2,
-- R2-13, R2-38): the seed of user #1 copies EDGE_PASSWORD_VERIFIER onto user #1's password identity at every start with
-- EDGE_MULTIUSER off (app/accounts.py AccountStore.seed), so that sign-in works the same the moment the switch goes on.
-- With the beta (switch off) and the live site (switch on) on one database, every beta deploy undid a password the admin
-- changed or reset on the live site, and the replaced password signed in again.
--
-- edge_bff.identities gains seed_verifier_sha256: the SHA-256 (hex) of the verifier the seed last wrote, never the
-- verifier itself. The seed copies the environment's verifier only while the identity still holds that copy
-- (sha256(verifier) = seed_verifier_sha256); a change or a reset (app/auth_flows.py) writes a new verifier, so the
-- identity is the account's own from then on and no start overwrites it. The switch-off sign-in still reads
-- EDGE_PASSWORD_VERIFIER itself (app/main.py), as before.
--
-- Filled here for the seed's own identity: the switch has never been on outside the test suites (EXEC.md, EDGE_MULTIUSER
-- off on dev), so the verifier user #1 holds today is the one the seed copied. Every other identity keeps NULL (the seed
-- never wrote it). No grant changes (a new column of a table edge_bff_runtime already reads and writes). Forward-only;
-- refuses a second run; rollback block at the end (comment).
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF to_regclass('edge_bff.identities') IS NULL OR to_regclass('edge_bff.users') IS NULL THEN
        RAISE EXCEPTION 'the EDGE account tables are missing: apply 20261116_003 first';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'edge_bff' AND table_name = 'identities'
               AND column_name = 'seed_verifier_sha256') THEN
        RAISE EXCEPTION 'edge_bff.identities.seed_verifier_sha256 exists: reconcile before applying';
    END IF;
END $preflight$;

ALTER TABLE edge_bff.identities ADD COLUMN seed_verifier_sha256 text
    CONSTRAINT identities_seed_verifier_sha256 CHECK (seed_verifier_sha256 ~ '^[0-9a-f]{64}$');
COMMENT ON COLUMN edge_bff.identities.seed_verifier_sha256 IS 'SHA-256 (hex) of the verifier the seed of user #1 last copied from EDGE_PASSWORD_VERIFIER; the seed copies again only while sha256(verifier) equals it (a password the account set itself is never overwritten). NULL: the seed never wrote this identity.';

-- the seed's identity: user #1 is the one account whose owner key is not of the 'u_' form (users_one_seed)
UPDATE edge_bff.identities i SET seed_verifier_sha256 = encode(sha256(convert_to(i.verifier, 'UTF8')), 'hex')
FROM edge_bff.users u
WHERE u.user_id = i.user_id AND i.provider = 'password' AND u.owner_key !~ '^u_[0-9a-f]{24}$';

DO $verify$
BEGIN
    IF EXISTS (SELECT 1 FROM edge_bff.identities i JOIN edge_bff.users u ON u.user_id = i.user_id
               WHERE i.provider = 'password' AND u.owner_key !~ '^u_[0-9a-f]{24}$'
                 AND i.seed_verifier_sha256 IS DISTINCT FROM encode(sha256(convert_to(i.verifier, 'UTF8')), 'hex')) THEN
        RAISE EXCEPTION 'the seed''s password identity does not carry the mark of its verifier';
    END IF;
    IF EXISTS (SELECT 1 FROM edge_bff.identities i JOIN edge_bff.users u ON u.user_id = i.user_id
               WHERE u.owner_key ~ '^u_[0-9a-f]{24}$' AND i.seed_verifier_sha256 IS NOT NULL) THEN
        RAISE EXCEPTION 'an account other than the seed carries a seed mark';
    END IF;
    IF NOT (has_table_privilege('edge_bff_runtime', 'edge_bff.identities', 'SELECT')
            AND has_table_privilege('edge_bff_runtime', 'edge_bff.identities', 'UPDATE')) THEN
        RAISE EXCEPTION 'edge_bff_runtime lost a grant on edge_bff.identities';
    END IF;
END $verify$;
COMMIT;

-- Rollback (a new forward migration with this body, after every edge-bff runs a build that does not read the column;
-- the seed then copies the environment's verifier at every switch-off start again):
-- BEGIN;
-- ALTER TABLE edge_bff.identities DROP COLUMN seed_verifier_sha256;
-- COMMIT;
