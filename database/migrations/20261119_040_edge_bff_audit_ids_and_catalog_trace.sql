-- EDGE multi-user fix round (EXEC-MU-ACCOUNTS; user 2026-11-19 "A": fix the re-check's findings now; contract
-- verification/edge_multiuser/access_tiers/CONTRACT.md sections 1 and 8a; findings R1-41, R1-42, R1-43 and R1-45 of
-- verification/edge_multiuser/access_tiers/recheck/r1_findings.json, each confirmed by three refuters).
--
-- 1. Audit and provenance user ids keep their value when an account is deleted (R1-42). edge_bff.admin_audit is
--    append-only for edge-bff (SELECT and INSERT only, CONTRACT section 1), but its actor_user_id and target_user_id
--    were foreign keys ON DELETE SET NULL: a referential action runs as the table owner, so the hourly purge of
--    never-verified registrations (app/accounts.py purge_pending, run as edge_bff_runtime) rewrote every audit row that
--    named the purged account. The same held for user_capability_overrides.created_by_user_id (who granted the
--    override). The foreign keys are dropped: the columns keep the user_id as a plain number, which names no row once
--    the account is gone (pseudonymous, never rewritten). The class rule (CONTRACT section 1): a provenance or audit
--    column that names a user carries no ON DELETE SET NULL or CASCADE.
-- 2. A change of the plan catalog leaves a trace (R1-43). plan_capabilities.version and updated_at were only column
--    defaults, so an operator's UPDATE of a value (CONTRACT 8a: a catalog-only change takes effect with no deploy) left
--    version 1 and the insert time. A BEFORE UPDATE trigger now raises version by one and sets updated_at when the
--    value changes. user_capability_overrides gains updated_at, set the same way when its value, reason or expiry
--    changes; who changed it is the Phase 4 admin_audit row written in the same transaction (CONTRACT section 10).
-- 3. Two live texts frozen in 20261117_003 are brought to the code and the decisions (R1-45): the comment of
--    capabilities.kind said a value of the wrong shape is "ignored", while edge-bff reads it as the most restrictive
--    value (ERRORS M480, app/principal.py read_grants: a limit reads 0, a list [], a flag or item family is not held);
--    the means of terminal.history_days said "back from today", while decision D2 = A counts back from the newest
--    published date of each dataset.
-- 4. The grant guard sees column privileges (R1-41): has_table_privilege is false for a privilege held on columns only,
--    so every earlier verify block missed one. This file's verify block refuses any column-level privilege held by
--    edge_bff_runtime, edge_bff_login or PUBLIC on any relation outside the system schemas (edge-bff's grants are
--    table-level only), as scripts/provision_edge_bff_login.py does.
--
-- No grant changes; the new column takes the table's grants. No index (the tables are small; AGENTS.md no speculative
-- index). Forward-only; refuses a second run; rollback block at the end (comment).
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF to_regclass('edge_bff.admin_audit') IS NULL OR to_regclass('edge_bff.plan_capabilities') IS NULL
       OR to_regclass('edge_bff.user_capability_overrides') IS NULL THEN
        RAISE EXCEPTION 'the EDGE account tables or plan catalog are missing: apply 20261116_003 and 20261117_003 first';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM edge_bff.capabilities WHERE capability_key = 'terminal.history_days') THEN
        RAISE EXCEPTION 'the capability terminal.history_days of 20261117_003 is missing: reconcile before applying';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_trigger WHERE NOT tgisinternal
               AND tgname IN ('plan_capabilities_trace', 'user_capability_overrides_trace'))
       OR EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'edge_bff'
                  AND table_name = 'user_capability_overrides' AND column_name = 'updated_at') THEN
        RAISE EXCEPTION 'this migration has run already (a trace trigger or overrides.updated_at exists): reconcile first';
    END IF;
END $preflight$;

-- ---- 1. audit and provenance user ids without a referential action --------------------------------------------------
DO $drop_fks$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT c.relname AS table_name, k.conname
        FROM pg_constraint k
        JOIN pg_class c ON c.oid = k.conrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_attribute a ON a.attrelid = k.conrelid AND a.attnum = ANY (k.conkey)
        WHERE n.nspname = 'edge_bff' AND k.contype = 'f' AND k.confrelid = 'edge_bff.users'::regclass
          AND ((c.relname = 'admin_audit' AND a.attname IN ('actor_user_id', 'target_user_id'))
            OR (c.relname = 'user_capability_overrides' AND a.attname = 'created_by_user_id'))
    LOOP
        EXECUTE format('ALTER TABLE edge_bff.%I DROP CONSTRAINT %I', r.table_name, r.conname);
    END LOOP;
END $drop_fks$;
COMMENT ON COLUMN edge_bff.admin_audit.actor_user_id IS 'user_id of the admin who acted, kept as a plain number with no foreign key: deleting an account never rewrites the audit (append-only; fix round R1-42).';
COMMENT ON COLUMN edge_bff.admin_audit.target_user_id IS 'user_id of the account acted on, kept as a plain number with no foreign key: deleting or purging that account never rewrites the audit (append-only; fix round R1-42).';
COMMENT ON COLUMN edge_bff.user_capability_overrides.created_by_user_id IS 'user_id of the admin who set the override, kept as a plain number with no foreign key (provenance; fix round R1-42).';

-- ---- 2. a trace of every catalog change -----------------------------------------------------------------------------
CREATE FUNCTION edge_bff.plan_capability_trace() RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
BEGIN
    IF NEW.value IS DISTINCT FROM OLD.value THEN
        NEW.version := greatest(NEW.version, OLD.version + 1);
        NEW.updated_at := now();
    END IF;
    RETURN NEW;
END $fn$;
REVOKE ALL ON FUNCTION edge_bff.plan_capability_trace() FROM PUBLIC;
CREATE TRIGGER plan_capabilities_trace BEFORE UPDATE ON edge_bff.plan_capabilities
    FOR EACH ROW EXECUTE FUNCTION edge_bff.plan_capability_trace();
COMMENT ON FUNCTION edge_bff.plan_capability_trace() IS 'On a change of plan_capabilities.value: version rises by one and updated_at is set (fix round R1-43), so the table tells when a grant changed.';

ALTER TABLE edge_bff.user_capability_overrides ADD COLUMN updated_at timestamptz;
COMMENT ON COLUMN edge_bff.user_capability_overrides.updated_at IS 'When the value, reason or expiry last changed (NULL: never changed since created_at); set by a trigger. Who changed it: the Phase 4 admin_audit row of the same transaction.';
CREATE FUNCTION edge_bff.capability_override_trace() RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
BEGIN
    IF (NEW.value, NEW.reason, NEW.expires_at) IS DISTINCT FROM (OLD.value, OLD.reason, OLD.expires_at) THEN
        NEW.updated_at := now();
    END IF;
    RETURN NEW;
END $fn$;
REVOKE ALL ON FUNCTION edge_bff.capability_override_trace() FROM PUBLIC;
CREATE TRIGGER user_capability_overrides_trace BEFORE UPDATE ON edge_bff.user_capability_overrides
    FOR EACH ROW EXECUTE FUNCTION edge_bff.capability_override_trace();
COMMENT ON FUNCTION edge_bff.capability_override_trace() IS 'On a change of a user_capability_overrides value, reason or expiry: updated_at is set (fix round R1-43).';
COMMENT ON TABLE edge_bff.plan_capabilities IS 'What each plan grants: one value per (plan, capability) in the shape of the capability kind. A change takes effect on the next request (no restart); the trigger plan_capabilities_trace raises version and sets updated_at with it (version is part of the X-Edge-Entitlements fingerprint).';

-- ---- 3. the live texts brought to the code and decision D2 ------------------------------------------------------------
COMMENT ON COLUMN edge_bff.capabilities.kind IS 'flag, limit, list or items. A value that does not fit its kind is refused when written (trigger capability_value_check); one that is read in the wrong shape all the same is read as the most restrictive value: a limit as 0, a list as [], a flag or an item family as not held (ERRORS M480). It never widens access.';
UPDATE edge_bff.capabilities
SET means = 'How many calendar days of history the Terminal serves to the account, counted back from the newest published date of each dataset (decision D2).'
WHERE capability_key = 'terminal.history_days';

DO $verify$
DECLARE
    bad text;
BEGIN
    -- 1: no referential action left on the audit and provenance columns
    IF EXISTS (SELECT 1 FROM pg_constraint k JOIN pg_attribute a ON a.attrelid = k.conrelid AND a.attnum = ANY (k.conkey)
               WHERE k.contype = 'f' AND k.confrelid = 'edge_bff.users'::regclass
                 AND ((k.conrelid = 'edge_bff.admin_audit'::regclass AND a.attname IN ('actor_user_id', 'target_user_id'))
                   OR (k.conrelid = 'edge_bff.user_capability_overrides'::regclass AND a.attname = 'created_by_user_id'))) THEN
        RAISE EXCEPTION 'an audit or provenance user column still references edge_bff.users';
    END IF;
    -- 2: both trace triggers exist and run their functions
    IF (SELECT count(*) FROM pg_trigger t JOIN pg_proc p ON p.oid = t.tgfoid WHERE NOT t.tgisinternal
        AND ((t.tgname = 'plan_capabilities_trace' AND t.tgrelid = 'edge_bff.plan_capabilities'::regclass
              AND p.proname = 'plan_capability_trace')
          OR (t.tgname = 'user_capability_overrides_trace' AND t.tgrelid = 'edge_bff.user_capability_overrides'::regclass
              AND p.proname = 'capability_override_trace'))) <> 2 THEN
        RAISE EXCEPTION 'a catalog trace trigger is missing';
    END IF;
    IF has_function_privilege('public', 'edge_bff.plan_capability_trace()', 'EXECUTE')
       OR has_function_privilege('public', 'edge_bff.capability_override_trace()', 'EXECUTE') THEN
        RAISE EXCEPTION 'PUBLIC may execute a catalog trace function';
    END IF;
    -- 3: the texts
    IF (SELECT means FROM edge_bff.capabilities WHERE capability_key = 'terminal.history_days') ~* 'from today'
       OR col_description('edge_bff.capabilities'::regclass,
                          (SELECT attnum FROM pg_attribute WHERE attrelid = 'edge_bff.capabilities'::regclass
                           AND attname = 'kind')) ~* 'ignores' THEN
        RAISE EXCEPTION 'the history_days means or the capabilities.kind comment still holds the old text';
    END IF;
    -- 4: the grants of the tables touched are what they were (table level) ...
    IF NOT has_table_privilege('edge_bff_runtime', 'edge_bff.admin_audit', 'SELECT')
       OR NOT has_table_privilege('edge_bff_runtime', 'edge_bff.admin_audit', 'INSERT')
       OR has_table_privilege('edge_bff_runtime', 'edge_bff.admin_audit', 'UPDATE')
       OR has_table_privilege('edge_bff_runtime', 'edge_bff.admin_audit', 'DELETE')
       OR has_table_privilege('edge_bff_runtime', 'edge_bff.plan_capabilities', 'UPDATE')
       OR NOT has_table_privilege('edge_bff_runtime', 'edge_bff.user_capability_overrides', 'UPDATE')
       OR has_table_privilege('edge_bff_runtime', 'edge_bff.user_capability_overrides', 'DELETE') THEN
        RAISE EXCEPTION 'the grants of admin_audit, plan_capabilities or user_capability_overrides changed';
    END IF;
    -- ... and no EDGE role (edge_bff_runtime, edge_bff_login when it exists) or PUBLIC holds a privilege on columns
    -- only, anywhere: has_table_privilege does not see one (R1-41), and edge-bff's grants are table-level only
    SELECT string_agg(format('%s.%s (%s) %s to %s', n.nspname, c.relname, a.attname, x.privilege_type,
                             CASE WHEN x.grantee = 0 THEN 'PUBLIC' ELSE x.grantee::regrole::text END), '; ')
    INTO bad
    FROM pg_attribute a
    JOIN pg_class c ON c.oid = a.attrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    CROSS JOIN LATERAL aclexplode(a.attacl) x
    WHERE a.attacl IS NOT NULL AND NOT a.attisdropped AND a.attnum > 0
      AND n.nspname NOT IN ('pg_catalog', 'information_schema') AND n.nspname NOT LIKE 'pg_toast%'
      AND (x.grantee = 0 OR x.grantee IN (SELECT oid FROM pg_roles WHERE rolname IN ('edge_bff_runtime', 'edge_bff_login')));
    IF bad IS NOT NULL THEN
        RAISE EXCEPTION 'a column-level privilege is held by an EDGE role or PUBLIC: %', bad
            USING HINT = 'edge-bff grants are table-level only; revoke the column privilege (REVOKE <privilege> (<column>) ON <table> FROM <role>) and grant at table level in a migration if it is meant';
    END IF;
END $verify$;
COMMIT;

-- Rollback (a new forward migration with this body; nothing reads the triggers or the new column). The foreign keys come
-- back NOT VALID (3c check C3-24: the block runs as written on the data this migration leaves): they bind every new
-- write, and the audit rows that kept the id of a deleted account keep it (the history this migration is for):
-- BEGIN;
-- DROP TRIGGER plan_capabilities_trace ON edge_bff.plan_capabilities;
-- DROP TRIGGER user_capability_overrides_trace ON edge_bff.user_capability_overrides;
-- DROP FUNCTION edge_bff.plan_capability_trace(), edge_bff.capability_override_trace();
-- ALTER TABLE edge_bff.user_capability_overrides DROP COLUMN updated_at;
-- ALTER TABLE edge_bff.admin_audit
--     ADD FOREIGN KEY (actor_user_id) REFERENCES edge_bff.users(user_id) ON DELETE SET NULL NOT VALID,
--     ADD FOREIGN KEY (target_user_id) REFERENCES edge_bff.users(user_id) ON DELETE SET NULL NOT VALID;
-- ALTER TABLE edge_bff.user_capability_overrides
--     ADD FOREIGN KEY (created_by_user_id) REFERENCES edge_bff.users(user_id) ON DELETE SET NULL NOT VALID;
-- COMMIT;
