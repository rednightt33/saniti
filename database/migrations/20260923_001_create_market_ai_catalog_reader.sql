-- Least-privilege catalog-metadata role for market-ai-orc: SELECT on exactly the five
-- AI_* catalog tables; no market-data, legacy-catalog, audit, function, or write access.
-- The login (market_ai_orc) is provisioned separately by
-- scripts/provision_market_ai_orc_login.py so no credential appears in Git.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

DO $preflight$
DECLARE
    target_name text;
BEGIN
    FOREACH target_name IN ARRAY ARRAY[
        'AI_table_catalog', 'AI_column_catalog', 'AI_catalog_relationships',
        'AI_calculation_catalog', 'AI_data_coverage'
    ]
    LOOP
        IF to_regclass(format('public.%I', target_name)) IS NULL THEN
            RAISE EXCEPTION 'Required catalog table is missing: %', target_name;
        END IF;
    END LOOP;
END
$preflight$;

DO $role$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'market_ai_catalog_reader') THEN
        CREATE ROLE market_ai_catalog_reader NOLOGIN;
    END IF;
END
$role$;

GRANT USAGE ON SCHEMA public TO market_ai_catalog_reader;
GRANT SELECT ON
    public."AI_table_catalog",
    public."AI_column_catalog",
    public."AI_catalog_relationships",
    public."AI_calculation_catalog",
    public."AI_data_coverage"
TO market_ai_catalog_reader;

DO $verify$
DECLARE
    relation record;
    catalog_tables text[] := ARRAY[
        'AI_table_catalog', 'AI_column_catalog', 'AI_catalog_relationships',
        'AI_calculation_catalog', 'AI_data_coverage'
    ];
BEGIN
    FOR relation IN
        SELECT c.oid, c.relname
        FROM pg_class AS c
        JOIN pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
    LOOP
        IF relation.relname = ANY(catalog_tables) THEN
            IF NOT has_table_privilege('market_ai_catalog_reader', relation.oid, 'SELECT') THEN
                RAISE EXCEPTION 'market_ai_catalog_reader SELECT grant missing for %', relation.relname;
            END IF;
            IF has_table_privilege(
                'market_ai_catalog_reader', relation.oid, 'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
            ) THEN
                RAISE EXCEPTION 'market_ai_catalog_reader unexpectedly may modify %', relation.relname;
            END IF;
        ELSIF has_table_privilege(
            'market_ai_catalog_reader', relation.oid, 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE'
        ) THEN
            RAISE EXCEPTION 'market_ai_catalog_reader unexpectedly has access to %', relation.relname;
        END IF;
    END LOOP;
END
$verify$;

COMMIT;
