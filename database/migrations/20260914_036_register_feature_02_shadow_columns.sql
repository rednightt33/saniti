-- Register the unreleased shadow as staging infrastructure, not an active Feature table.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '5min';

DO $preflight$
BEGIN
    IF to_regclass('public."Feature_02_Broker_Rolling_v2"') IS NULL THEN
        RAISE EXCEPTION 'Feature 02 v2 shadow is missing';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public."Table_Catalog"
        WHERE table_schema='public' AND table_name='Feature_02_Broker_Rolling_v2'
    ) THEN
        RAISE EXCEPTION 'Feature 02 v2 Table_Catalog row is missing';
    END IF;
END
$preflight$;

UPDATE public."Table_Catalog"
SET category='System',
    definition='Unreleased shadow replacement for Feature 02 with source Investor Type preserved. It is staging infrastructure and must not be queried as a production Feature until full validation and atomic cutover.',
    documentation_status='PARTIAL',
    updated_at=CURRENT_TIMESTAMP
WHERE table_schema='public' AND table_name='Feature_02_Broker_Rolling_v2';

INSERT INTO public."Column_Catalog" (
    table_schema, table_name, column_name, ordinal_position, data_type,
    is_nullable, default_expression, is_primary_key, definition,
    source_column_or_expression, source_code_paths, documentation_status
)
SELECT c.table_schema, c.table_name, c.column_name, c.ordinal_position,
       c.data_type, c.is_nullable='YES', c.column_default,
       EXISTS (
           SELECT 1
           FROM pg_catalog.pg_constraint con
           JOIN unnest(con.conkey) AS key(attnum) ON true
           JOIN pg_catalog.pg_attribute att
             ON att.attrelid=con.conrelid AND att.attnum=key.attnum
           WHERE con.conrelid='public."Feature_02_Broker_Rolling_v2"'::regclass
             AND con.contype='p' AND att.attname=c.column_name
       ),
       pg_catalog.col_description(
           'public."Feature_02_Broker_Rolling_v2"'::regclass, c.ordinal_position
       ),
       'Unreleased Feature 02 v2 shadow; detailed active semantics will be registered as Feature_Catalog v2 only after full validation and cutover.',
       ARRAY[
         'database/migrations/20260914_034_create_feature_02_investor_type_shadow.sql',
         'database/migrations/20260914_036_register_feature_02_shadow_columns.sql',
         'scripts/backfill_feature_02_v2.py',
         'scripts/validate_feature_02_v2_sample.py'
       ],
       'PARTIAL'
FROM information_schema.columns c
WHERE c.table_schema='public' AND c.table_name='Feature_02_Broker_Rolling_v2'
ON CONFLICT (table_schema, table_name, column_name) DO NOTHING;

DO $coverage$
DECLARE v_physical integer; v_catalog integer;
BEGIN
    SELECT count(*) INTO v_physical FROM information_schema.columns
    WHERE table_schema='public' AND table_name='Feature_02_Broker_Rolling_v2';
    SELECT count(*) INTO v_catalog FROM public."Column_Catalog"
    WHERE table_schema='public' AND table_name='Feature_02_Broker_Rolling_v2';
    IF v_physical <> 38 OR v_catalog <> v_physical THEN
        RAISE EXCEPTION 'Feature 02 v2 shadow catalog coverage mismatch: physical %, catalog %',
            v_physical, v_catalog;
    END IF;
END
$coverage$;

COMMIT;
