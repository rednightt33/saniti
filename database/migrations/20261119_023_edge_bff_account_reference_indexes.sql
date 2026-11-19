-- EDGE accounts (EXEC-MU-ACCOUNTS; ERRORS R2-34, R2-33): an index on every column that references edge_bff.users.
-- 20261116_003 and 20261117_003 added these foreign keys with no index on the referencing column ("indexes beyond the
-- keys: none", CONTRACT.md section 1, on the assumption that users and sessions number in the thousands). But Postgres
-- checks each referencing table once per deleted account (ON DELETE CASCADE / SET NULL), so without an index every
-- deleted account scans sessions, email_codes, admin_audit (twice), subscriptions and user_capability_overrides in full:
-- the hourly purge of registrations never verified (app/accounts.py purge_pending) took 5.0 s for 200 accounts with 100k
-- sessions and 107k codes (the store's statement_timeout), and its cost grew with the square of the pending backlog. The
-- same columns serve the principal's reads by account: the sign-in's session cap and revoke_all (sessions.user_id), the
-- resolve's live and lapsed subscriptions (subscriptions.user_id; the partial subscriptions_one_active serves neither the
-- cascade nor the lapsed read, nor does the partial email_codes_one_live serve the cascade).
--
-- Plain btree indexes, measured with bounded EXPLAIN (ANALYZE, BUFFERS) before and after (the fix-round notes,
-- verification/edge_multiuser/fix_round/site.md). The tables are small today (the switch is off on dev: one account),
-- so CREATE INDEX in the migration's transaction holds each table's write lock for milliseconds. No grant changes.
-- Rule from here on (CONTRACT.md section 1, recorded with this fix): every foreign key to edge_bff.users has an index
-- whose leading column is the referencing column (tests/test_c2_ops_recheck.py test_every_reference_to_an_account_has_an_index).
-- Forward-only; refuses a second run; rollback block at the end (comment).
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '5min';
DO $preflight$
BEGIN
    IF to_regclass('edge_bff.users') IS NULL OR to_regclass('edge_bff.subscriptions') IS NULL
       OR to_regclass('edge_bff.user_capability_overrides') IS NULL THEN
        RAISE EXCEPTION 'the EDGE account tables or the plan catalog are missing: apply 20261116_003 and 20261117_003 first';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'edge_bff'
               AND c.relname IN ('sessions_user_id', 'email_codes_user_id', 'admin_audit_actor_user_id',
                                 'admin_audit_target_user_id', 'subscriptions_user_id_starts',
                                 'user_capability_overrides_created_by')) THEN
        RAISE EXCEPTION 'an index of this migration exists: reconcile before applying';
    END IF;
END $preflight$;

CREATE INDEX sessions_user_id ON edge_bff.sessions(user_id);
CREATE INDEX email_codes_user_id ON edge_bff.email_codes(user_id);
CREATE INDEX admin_audit_actor_user_id ON edge_bff.admin_audit(actor_user_id);
CREATE INDEX admin_audit_target_user_id ON edge_bff.admin_audit(target_user_id);
-- the resolve's live and lapsed subscriptions: by account, the most recent start first
CREATE INDEX subscriptions_user_id_starts ON edge_bff.subscriptions(user_id, starts_at DESC);
CREATE INDEX user_capability_overrides_created_by ON edge_bff.user_capability_overrides(created_by_user_id);

DO $verify$
DECLARE
    missing text;
BEGIN
    -- every single-column foreign key to edge_bff.users has a non-partial index led by its column
    SELECT string_agg(c.conrelid::regclass::text || '.' || a.attname, ', ') INTO missing
    FROM pg_constraint c JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
    WHERE c.contype = 'f' AND c.confrelid = 'edge_bff.users'::regclass AND cardinality(c.conkey) = 1
      AND NOT EXISTS (SELECT 1 FROM pg_index i WHERE i.indrelid = c.conrelid AND i.indkey[0] = c.conkey[1]
                      AND i.indpred IS NULL);
    IF missing IS NOT NULL THEN
        RAISE EXCEPTION 'foreign keys to edge_bff.users without an index on their column: %', missing;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid JOIN pg_namespace n ON n.oid = c.relnamespace
               WHERE n.nspname = 'edge_bff' AND c.relname IN ('sessions_user_id', 'email_codes_user_id',
                   'admin_audit_actor_user_id', 'admin_audit_target_user_id', 'subscriptions_user_id_starts',
                   'user_capability_overrides_created_by') AND NOT i.indisvalid) THEN
        RAISE EXCEPTION 'an index of this migration is not valid';
    END IF;
END $verify$;
COMMIT;

-- Rollback (a new forward migration with this body; the purge and the principal's reads by account scan again):
-- BEGIN;
-- DROP INDEX edge_bff.sessions_user_id, edge_bff.email_codes_user_id, edge_bff.admin_audit_actor_user_id,
--     edge_bff.admin_audit_target_user_id, edge_bff.subscriptions_user_id_starts,
--     edge_bff.user_capability_overrides_created_by;
-- COMMIT;
