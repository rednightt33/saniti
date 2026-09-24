-- Least-privilege role for the pgweb browser service: SELECT-only on every current and
-- future table/view in schema public, no INSERT/UPDATE/DELETE/DDL/role/function grants
-- anywhere. The login (pgweb) is provisioned separately by
-- scripts/provision_pgweb_login.py so no credential appears in Git.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

DO $role$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pgweb_reader') THEN
        CREATE ROLE pgweb_reader NOLOGIN;
    END IF;
END
$role$;

GRANT USAGE ON SCHEMA public TO pgweb_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO pgweb_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO pgweb_reader;

DO $verify$
DECLARE
    relation record;
BEGIN
    FOR relation IN
        SELECT c.oid, c.relname
        FROM pg_class AS c
        JOIN pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
    LOOP
        IF NOT has_table_privilege('pgweb_reader', relation.oid, 'SELECT') THEN
            RAISE EXCEPTION 'pgweb_reader SELECT grant missing for %', relation.relname;
        END IF;
        IF has_table_privilege(
            'pgweb_reader', relation.oid, 'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
        ) THEN
            RAISE EXCEPTION 'pgweb_reader unexpectedly may modify %', relation.relname;
        END IF;
    END LOOP;

    IF EXISTS (
        SELECT 1 FROM information_schema.role_routine_grants WHERE grantee = 'pgweb_reader'
    ) THEN
        RAISE EXCEPTION 'pgweb_reader unexpectedly has an EXECUTE grant on a routine';
    END IF;
END
$verify$;

COMMIT;
