-- Subject metadata for the AI table catalog (two-path analysis architecture, SANITI-TWO-PATH-IMPLEMENTATION).
--
-- AI_table_catalog.category describes the technical table category (REFERENCE, TRANSACTIONAL, FEATURE),
-- not what a table is about. An Analysis Spec V2 names its subject (data domain, entity type, optional
-- asset type) and every source table; the sandbox checks those names against these catalog columns, and
-- the SQL Governor carries them into each dataset's internal validator manifest, so no service needs a
-- hardcoded per-table dictionary.
--
--   data_domain            catalog-managed identifier of the subject area (MARKET, MACRO, RATES, ...)
--   entity_type            catalog-managed identifier of what entity_column identifies (STOCK, BROKER, ...)
--   asset_type             nullable: a macro series or a broker is not an asset
--   supported_frequencies  observation frequencies the table supports ('1D', '1W', ...) or {'STATIC'}
--                          for a table without a time column
--   time_semantics         what a time value means (trading date, observation date, current state)
--   subject_metadata_status INFERRED until a person reviews the values; never VERIFIED by this migration
--
-- Values are validated by syntax only (no enum): a new domain or entity type is a catalog row, not code.
-- grain, primary_key_columns, entity_column, time_column and column units are reused, not duplicated.
--
-- Rollback (forward-only policy: write a new migration): drop the six columns and their Column_Catalog rows.
-- market-sql-governor, market-python-sandbox and market-ai-orc versions that read these columns must be
-- rolled back first; older versions never read them.
BEGIN;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = 'AI_table_catalog' AND column_name = 'data_domain') THEN
        RAISE EXCEPTION 'AI_table_catalog.data_domain already exists';
    END IF;
END;
$$;

-- BEGIN subject metadata (tests apply this section to their catalog fixtures)
ALTER TABLE public."AI_table_catalog"
    ADD COLUMN data_domain text,
    ADD COLUMN entity_type text,
    ADD COLUMN asset_type text,
    ADD COLUMN supported_frequencies text[],
    ADD COLUMN time_semantics text,
    ADD COLUMN subject_metadata_status text NOT NULL DEFAULT 'INFERRED';

UPDATE public."AI_table_catalog" AS catalog
SET data_domain = seed.data_domain,
    entity_type = seed.entity_type,
    asset_type = seed.asset_type,
    supported_frequencies = seed.supported_frequencies,
    time_semantics = seed.time_semantics
FROM (
    VALUES
      ('Price_Stock_Indonesia_IDX', 'MARKET', 'STOCK', 'IDX_EQUITY', ARRAY['1D'],
       'Asia/Jakarta exchange trading date'),
      ('Feature_01_Stock_Daily', 'MARKET', 'STOCK', 'IDX_EQUITY', ARRAY['1D'],
       'Asia/Jakarta exchange trading date'),
      ('Feature_02_Broker_Rolling', 'MARKET', 'STOCK', 'IDX_EQUITY', ARRAY['1D'],
       'Asia/Jakarta exchange trading date'),
      ('Feature_03_Stock_Broker_Daily', 'MARKET', 'STOCK', 'IDX_EQUITY', ARRAY['1D'],
       'Asia/Jakarta exchange trading date'),
      ('IDX_Broker_Summary', 'MARKET', 'STOCK', 'IDX_EQUITY', ARRAY['1D'],
       'Asia/Jakarta exchange trading date'),
      ('IDX_Stock_Universe', 'MARKET', 'STOCK', 'IDX_EQUITY', ARRAY['STATIC'],
       'Current-state reference data; not point-in-time'),
      ('IDX_Broker_Profile', 'MARKET', 'BROKER', NULL, ARRAY['STATIC'],
       'Current-state reference data; not point-in-time')
) AS seed (table_name, data_domain, entity_type, asset_type, supported_frequencies, time_semantics)
WHERE catalog.table_name = seed.table_name;

-- Tables registered later (or outside this seed) get a conservative default that a reviewer must replace.
UPDATE public."AI_table_catalog"
SET data_domain = 'UNCLASSIFIED', entity_type = 'UNCLASSIFIED',
    supported_frequencies = CASE WHEN time_column IS NULL THEN ARRAY['STATIC'] ELSE ARRAY['1D'] END
WHERE data_domain IS NULL;

ALTER TABLE public."AI_table_catalog"
    ALTER COLUMN data_domain SET NOT NULL,
    ALTER COLUMN entity_type SET NOT NULL,
    ALTER COLUMN supported_frequencies SET NOT NULL,
    ADD CONSTRAINT "AI_table_catalog_data_domain_check" CHECK (data_domain ~ '^[A-Z][A-Z0-9_]{1,39}$'),
    ADD CONSTRAINT "AI_table_catalog_entity_type_check" CHECK (entity_type ~ '^[A-Z][A-Z0-9_]{1,39}$'),
    ADD CONSTRAINT "AI_table_catalog_asset_type_check" CHECK (asset_type IS NULL OR asset_type ~ '^[A-Z][A-Z0-9_]{1,39}$'),
    ADD CONSTRAINT "AI_table_catalog_frequencies_check" CHECK (
        cardinality(supported_frequencies) BETWEEN 1 AND 8
        AND supported_frequencies <@ ARRAY['STATIC', '1MIN', '5MIN', '15MIN', '1H', '1D', '1W', '1M', '1Q', '1Y']
        AND (time_column IS NULL) = (supported_frequencies = ARRAY['STATIC'])
    ),
    ADD CONSTRAINT "AI_table_catalog_subject_status_check" CHECK (
        subject_metadata_status IN ('INFERRED', 'REVIEWED', 'VERIFIED')
    );

COMMENT ON COLUMN public."AI_table_catalog".data_domain IS
    'Catalog-managed subject area of the table (MARKET, MACRO, RATES, FUNDAMENTAL, ...); syntax-checked, not an enum.';
COMMENT ON COLUMN public."AI_table_catalog".entity_type IS
    'Catalog-managed type of the entity that entity_column identifies (STOCK, BROKER, SERIES, ...).';
COMMENT ON COLUMN public."AI_table_catalog".asset_type IS
    'Asset type of the entities when they are assets (IDX_EQUITY, ...); NULL for non-asset entities.';
COMMENT ON COLUMN public."AI_table_catalog".supported_frequencies IS
    'Observation frequencies the table supports; {STATIC} exactly when the table has no time_column.';
COMMENT ON COLUMN public."AI_table_catalog".time_semantics IS
    'What a value of time_column means (trading date, observation date) or that the table is current state.';
COMMENT ON COLUMN public."AI_table_catalog".subject_metadata_status IS
    'INFERRED until a person reviews the subject values; REVIEWED or VERIFIED only after review.';
-- END subject metadata

INSERT INTO public."Column_Catalog" (
    table_schema, table_name, column_name, ordinal_position, data_type,
    is_nullable, default_expression, is_primary_key, definition,
    source_column_or_expression, unit, null_rule, source_code_paths,
    documentation_status
)
SELECT columns.table_schema, columns.table_name, columns.column_name, columns.ordinal_position,
       columns.data_type, columns.is_nullable = 'YES', columns.column_default, false,
       CASE columns.column_name
        WHEN 'data_domain' THEN 'Catalog-managed subject area of the table (MARKET, MACRO, RATES, FUNDAMENTAL, ...); '
                                'validated by syntax, resolved from catalog rows, never a code enum.'
        WHEN 'entity_type' THEN 'Catalog-managed type of the entity identified by entity_column (STOCK, BROKER, ...).'
        WHEN 'asset_type' THEN 'Asset type of the entities when they are assets (IDX_EQUITY); NULL for non-asset '
                               'entities such as brokers or macro series.'
        WHEN 'supported_frequencies' THEN 'Observation frequencies the table supports; {STATIC} exactly when '
                                          'time_column is NULL.'
        WHEN 'time_semantics' THEN 'Meaning of time_column values (exchange trading date, observation date) or '
                                   'that the table holds current-state reference data.'
        WHEN 'subject_metadata_status' THEN 'Review state of the subject values: INFERRED (seeded by migration '
                                            '20260925_001), REVIEWED, or VERIFIED after a person confirms them.'
       END,
       'Curated by migration 20260925_001', NULL,
       CASE WHEN columns.is_nullable = 'YES' THEN 'NULL when the concept does not apply to the table.'
            ELSE 'NULL is not permitted.' END,
       ARRAY['database/migrations/20260925_001_add_ai_table_subject_metadata.sql',
             'apps/market-sql-governor/app/catalog_contract.py'],
       'NEEDS_REVIEW'
FROM information_schema.columns AS columns
WHERE columns.table_schema = 'public' AND columns.table_name = 'AI_table_catalog'
  AND columns.column_name IN ('data_domain', 'entity_type', 'asset_type', 'supported_frequencies',
                              'time_semantics', 'subject_metadata_status');

UPDATE public."Table_Catalog"
SET source_code_paths = array_append(source_code_paths,
                                     'database/migrations/20260925_001_add_ai_table_subject_metadata.sql')
WHERE table_schema = 'public' AND table_name = 'AI_table_catalog'
  AND NOT ('database/migrations/20260925_001_add_ai_table_subject_metadata.sql' = ANY(source_code_paths));

DO $verify$
BEGIN
    IF EXISTS (SELECT 1 FROM public."AI_table_catalog" WHERE data_domain = 'UNCLASSIFIED') THEN
        RAISE NOTICE 'Some AI_table_catalog rows need subject metadata review (UNCLASSIFIED).';
    END IF;
    IF (SELECT count(*) FROM public."AI_table_catalog" WHERE subject_metadata_status = 'INFERRED')
       <> (SELECT count(*) FROM public."AI_table_catalog") THEN
        RAISE EXCEPTION 'Seeded subject metadata must start as INFERRED';
    END IF;
    IF (SELECT count(*) FROM public."Column_Catalog" WHERE table_name = 'AI_table_catalog'
          AND column_name IN ('data_domain', 'entity_type', 'asset_type', 'supported_frequencies',
                              'time_semantics', 'subject_metadata_status')) <> 6 THEN
        RAISE EXCEPTION 'Every new AI_table_catalog column needs a Column_Catalog definition';
    END IF;
END;
$verify$;

COMMIT;
