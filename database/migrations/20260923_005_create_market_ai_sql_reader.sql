-- Database role for market-sql-governor.
-- NOLOGIN role market_ai_sql_reader gets USAGE on schema public and SELECT on exactly five AI
-- catalogs (the governance source) and seven approved market-data tables. It gets no write,
-- DDL, or function privilege. The login market_sql_governor is created by
-- scripts/provision_market_sql_governor_login.py and is a member of this role only.
-- The Governor applies the AI catalog policy on top (layer 1); this role is layer 2.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

DO $preflight$
DECLARE
    target_name text;
BEGIN
    FOREACH target_name IN ARRAY ARRAY[
        'AI_table_catalog', 'AI_column_catalog', 'AI_catalog_relationships', 'AI_calculation_catalog',
        'AI_data_coverage', 'Feature_01_Stock_Daily', 'Feature_02_Broker_Rolling',
        'Feature_03_Stock_Broker_Daily', 'IDX_Broker_Profile', 'IDX_Broker_Summary',
        'IDX_Stock_Universe', 'Price_Stock_Indonesia_IDX'
    ]
    LOOP
        IF to_regclass(format('public.%I', target_name)) IS NULL THEN
            RAISE EXCEPTION 'Required table is missing: %', target_name;
        END IF;
    END LOOP;
END
$preflight$;

DO $role$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'market_ai_sql_reader') THEN
        CREATE ROLE market_ai_sql_reader NOLOGIN;
    END IF;
END
$role$;

GRANT USAGE ON SCHEMA public TO market_ai_sql_reader;
GRANT SELECT ON
    public."AI_table_catalog", public."AI_column_catalog", public."AI_catalog_relationships",
    public."AI_calculation_catalog", public."AI_data_coverage",
    public."Feature_01_Stock_Daily", public."Feature_02_Broker_Rolling",
    public."Feature_03_Stock_Broker_Daily", public."IDX_Broker_Profile", public."IDX_Broker_Summary",
    public."IDX_Stock_Universe", public."Price_Stock_Indonesia_IDX"
TO market_ai_sql_reader;

DO $verify$
DECLARE
    relation record;
    approved text[] := ARRAY[
        'AI_table_catalog', 'AI_column_catalog', 'AI_catalog_relationships', 'AI_calculation_catalog',
        'AI_data_coverage', 'Feature_01_Stock_Daily', 'Feature_02_Broker_Rolling',
        'Feature_03_Stock_Broker_Daily', 'IDX_Broker_Profile', 'IDX_Broker_Summary',
        'IDX_Stock_Universe', 'Price_Stock_Indonesia_IDX'
    ];
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname = 'market_ai_sql_reader'
          AND (rolcanlogin OR rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls)
    ) THEN
        RAISE EXCEPTION 'market_ai_sql_reader must be a NOLOGIN role without elevated attributes';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_auth_members WHERE member = 'market_ai_sql_reader'::regrole) THEN
        RAISE EXCEPTION 'market_ai_sql_reader must not inherit other roles';
    END IF;
    IF has_schema_privilege('market_ai_sql_reader', 'public', 'CREATE') THEN
        RAISE EXCEPTION 'market_ai_sql_reader must not create objects in public';
    END IF;
    FOR relation IN
        SELECT c.oid, c.relname
        FROM pg_class AS c
        JOIN pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
    LOOP
        IF has_table_privilege('market_ai_sql_reader', relation.oid, 'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') THEN
            RAISE EXCEPTION 'market_ai_sql_reader unexpectedly has write access to %', relation.relname;
        END IF;
        IF has_table_privilege('market_ai_sql_reader', relation.oid, 'SELECT') <> (relation.relname = ANY(approved)) THEN
            RAISE EXCEPTION 'market_ai_sql_reader SELECT on % does not match the approved list', relation.relname;
        END IF;
    END LOOP;
END
$verify$;

COMMIT;
