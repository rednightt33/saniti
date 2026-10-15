-- EXEC-IMPL-1016 Fase 3 (O1 dictionary, user decisions 2026-10-15: "user bilang BRI, tapi kode tickernya BBRI ... How
-- we handle this?"; matching "Alias + persis + potongan", no pg_trgm; go "Next lanjutkan" for Fase 2-5).
-- 1. AI_column_catalog.entity_name marks the column that holds an entity's display name in a static reference table
--    (a company name, a broker name). The SQL Governor derives the names and their generated aliases (initials,
--    the name without its legal form) from the marked columns at run time, so a new reference table needs only the
--    flag, never code. The four existing name columns are marked; a history table's names give former names.
-- 2. AI_entity_alias holds the curated aliases the names cannot give (a brand, a former code, a common short form):
--    MANUAL and FORMER_CODE rows, written by forward migrations or a reviewed load, never by the model. Generated
--    aliases (ACRONYM, SHORT_NAME) are derived, not stored. Empty at creation.
-- Read by the SQL Governor (market_ai_sql_reader) and market-ai-orc's catalog login (market_ai_catalog_reader).
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

DO $preflight$
BEGIN
    IF to_regclass('public."AI_entity_alias"') IS NOT NULL THEN
        RAISE EXCEPTION 'AI_entity_alias already exists';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public'
               AND table_name = 'AI_column_catalog' AND column_name = 'entity_name') THEN
        RAISE EXCEPTION 'AI_column_catalog.entity_name already exists';
    END IF;
    IF (SELECT count(*) FROM public."AI_column_catalog"
        WHERE (table_name, column_name) IN (('IDX_Stock_Universe', 'Company Name'),
                                            ('IDX_Stock_Universe_History', 'Company Name'),
                                            ('IDX_Broker_Profile', 'broker_name'),
                                            ('IDX_Broker_Profile_History', 'broker_name'))) <> 4 THEN
        RAISE EXCEPTION 'Expected the four name columns in AI_column_catalog';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'market_ai_sql_reader')
       OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'market_ai_catalog_reader') THEN
        RAISE EXCEPTION 'market_ai_sql_reader and market_ai_catalog_reader are required';
    END IF;
END
$preflight$;

ALTER TABLE public."AI_column_catalog" ADD COLUMN entity_name boolean NOT NULL DEFAULT false;
COMMENT ON COLUMN public."AI_column_catalog".entity_name IS
    'True for the column that holds an entity''s display name in a static reference table; the SQL Governor derives '
    'names and generated aliases from it (search-values).';
UPDATE public."AI_column_catalog" SET entity_name = true
WHERE (table_name, column_name) IN (('IDX_Stock_Universe', 'Company Name'), ('IDX_Stock_Universe_History', 'Company Name'),
                                    ('IDX_Broker_Profile', 'broker_name'), ('IDX_Broker_Profile_History', 'broker_name'));

CREATE TABLE public."AI_entity_alias" (
    table_name text NOT NULL,
    column_name text NOT NULL,
    code text NOT NULL,
    alias text NOT NULL,
    alias_folded text NOT NULL,
    alias_type text NOT NULL,
    note text,
    source_decision text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT statement_timestamp(),
    CONSTRAINT "AI_entity_alias_pkey" PRIMARY KEY (table_name, column_name, alias_folded, code),
    CONSTRAINT ai_entity_alias_type CHECK (alias_type IN ('MANUAL', 'FORMER_CODE')),
    CONSTRAINT ai_entity_alias_folded CHECK (alias_folded = lower(regexp_replace(btrim(alias), '\s+', ' ', 'g'))
                                             AND alias_folded <> ''),
    CONSTRAINT ai_entity_alias_code CHECK (code = upper(btrim(code)) AND code <> '')
);
COMMENT ON TABLE public."AI_entity_alias" IS
    'Curated aliases of entity codes (a brand, a former code) the display names cannot give; generated aliases '
    '(initials, the name without its legal form) are derived by the SQL Governor, not stored.';

GRANT SELECT ON public."AI_entity_alias" TO market_ai_sql_reader, market_ai_catalog_reader;
DO $grant$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pgweb_reader') THEN
        GRANT SELECT ON public."AI_entity_alias" TO pgweb_reader;
    END IF;
END
$grant$;
REVOKE ALL ON public."AI_entity_alias" FROM PUBLIC;

INSERT INTO public."Table_Catalog" (
    table_schema, table_name, category, definition, grain,
    primary_key_columns, source_system, source_tables, source_code_paths,
    update_rule, related_functions, documentation_status,
    readiness_mode, readiness_date_column, observation_date_column,
    data_available_at_column, availability_rule, point_in_time_status,
    historical_metadata_method
) VALUES (
    'public', 'AI_entity_alias', 'System',
    'Curated aliases of entity codes (tickers, broker codes) that the display names cannot give, for the SQL Governor''s search-values: MANUAL (a brand or common short form) and FORMER_CODE. Generated aliases are derived from the AI_column_catalog.entity_name columns at run time and not stored.',
    'One row per entity column, folded alias and code', ARRAY['table_name', 'column_name', 'alias_folded', 'code'],
    'Forward migrations or a reviewed load (EXEC-IMPL-1016 Fase 3)',
    ARRAY['AI_column_catalog', 'IDX_Stock_Universe', 'IDX_Broker_Profile']::text[],
    ARRAY['database/migrations/20261015_014_entity_names_and_aliases.sql',
          'apps/market-sql-governor/app/value_dictionary.py'],
    'Rows are added by forward migrations or a reviewed load; the model never writes them.',
    ARRAY[]::text[], 'VERIFIED', 'NOT_APPLICABLE', NULL, NULL, 'created_at',
    'Metadata, not market data.', 'NOT_APPLICABLE', NULL
);

INSERT INTO public."Column_Catalog" (
    table_schema, table_name, column_name, ordinal_position, data_type,
    is_nullable, default_expression, is_primary_key, definition,
    source_column_or_expression, unit, null_rule, source_code_paths,
    documentation_status
)
SELECT columns.table_schema, columns.table_name, columns.column_name, columns.ordinal_position,
       columns.data_type, columns.is_nullable = 'YES', columns.column_default,
       columns.column_name IN ('table_name', 'column_name', 'alias_folded', 'code'),
       CASE columns.column_name
        WHEN 'table_name' THEN 'The catalog table whose entity column the alias belongs to.'
        WHEN 'column_name' THEN 'The entity column (a ticker or broker code column) the alias resolves to.'
        WHEN 'code' THEN 'The stored entity code the alias stands for, upper-case and trimmed.'
        WHEN 'alias' THEN 'The alias as written (a brand, a common short form, a former code).'
        WHEN 'alias_folded' THEN 'The alias in lower case with single spaces, the form search-values matches on.'
        WHEN 'alias_type' THEN 'MANUAL (a curated alias) or FORMER_CODE (a code the entity used before).'
        WHEN 'note' THEN 'Why the alias exists, in plain words.'
        WHEN 'source_decision' THEN 'The decision or review the alias comes from.'
        WHEN 'created_at' THEN 'When the row was inserted.'
       END,
       columns.column_name, NULL, CASE WHEN columns.column_name = 'note' THEN 'NULL when no note is needed.' END,
       ARRAY['database/migrations/20261015_014_entity_names_and_aliases.sql'], 'VERIFIED'
FROM information_schema.columns
WHERE columns.table_schema = 'public' AND columns.table_name = 'AI_entity_alias'
UNION ALL
SELECT columns.table_schema, columns.table_name, columns.column_name, columns.ordinal_position,
       columns.data_type, columns.is_nullable = 'YES', columns.column_default, false,
       'True for the column that holds an entity''s display name in a static reference table (a company name, a broker name); the SQL Governor derives names and generated aliases from it for search-values.',
       columns.column_name, NULL, 'Never NULL; false by default.',
       ARRAY['database/migrations/20261015_014_entity_names_and_aliases.sql'], 'VERIFIED'
FROM information_schema.columns
WHERE columns.table_schema = 'public' AND columns.table_name = 'AI_column_catalog'
  AND columns.column_name = 'entity_name';

DO $verify$
BEGIN
    IF (SELECT count(*) FROM public."AI_column_catalog" WHERE entity_name) <> 4 THEN
        RAISE EXCEPTION 'Expected four entity name columns';
    END IF;
    IF (SELECT count(*) FROM public."Column_Catalog"
        WHERE table_name = 'AI_entity_alias' AND definition IS NOT NULL) <> 9
       OR NOT EXISTS (SELECT 1 FROM public."Column_Catalog"
                      WHERE table_name = 'AI_column_catalog' AND column_name = 'entity_name') THEN
        RAISE EXCEPTION 'Every new column needs a Column_Catalog definition';
    END IF;
    IF NOT has_table_privilege('market_ai_sql_reader', 'public."AI_entity_alias"', 'SELECT')
       OR has_table_privilege('market_ai_sql_reader', 'public."AI_entity_alias"', 'INSERT,UPDATE,DELETE')
       OR NOT has_table_privilege('market_ai_catalog_reader', 'public."AI_entity_alias"', 'SELECT') THEN
        RAISE EXCEPTION 'The readers must read AI_entity_alias only';
    END IF;
    IF NOT has_column_privilege('market_ai_sql_reader', 'public."AI_column_catalog"', 'entity_name', 'SELECT') THEN
        RAISE EXCEPTION 'market_ai_sql_reader must read AI_column_catalog.entity_name';
    END IF;
END
$verify$;

COMMIT;
