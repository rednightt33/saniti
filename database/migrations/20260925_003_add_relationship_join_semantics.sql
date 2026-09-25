-- Point-in-time join semantics and resampling rules in the AI catalogs (DataNeed architecture).
--
-- A DataNeedSpec relationship names a catalog relationship_id and the join semantics it wants. The catalog is the
-- only source of truth for which semantics a relationship supports, and for the time columns a temporal join uses:
--
--   supported_join_semantics  subset of CURRENT_STATE, EXACT_DATE, AS_OF, EFFECTIVE_DATED; empty = not joinable
--                             by the DataNeed planner (the relationship stays available to request_data joins)
--   left_time_column          time column of left_table used by EXACT_DATE / AS_OF
--   right_time_column         time column of right_table used by EXACT_DATE / AS_OF (for AS_OF: the column whose
--                             latest value at or before the observation date is used)
--   effective_from_column     inclusive start of validity of a right_table row (EFFECTIVE_DATED)
--   effective_to_column       exclusive end of validity of a right_table row, NULL = still valid (EFFECTIVE_DATED)
--
-- AI_column_catalog.resample_aggregation (FIRST, LAST, MAX, MIN, SUM) is the exact rule for aggregating a column to
-- a coarser frequency. NULL means the rule is not established: the planner then never pushes resampling down and
-- the sandbox receives source-frequency data. This migration seeds no rule.
--
-- Seeds: the two current-state reference relationships support CURRENT_STATE; the three same-date relationships
-- support EXACT_DATE with their date columns. No relationship is AS_OF or EFFECTIVE_DATED today, because no
-- catalog table carries history of reference values yet.
--
-- Rollback (forward-only policy: write a new migration): drop the six columns, their constraints and their
-- Column_Catalog rows. market-sql-governor, market-python-sandbox and market-ai-orc versions that read them must
-- be rolled back first; older versions never read them.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '2min';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = 'AI_catalog_relationships'
                 AND column_name = 'supported_join_semantics') THEN
        RAISE EXCEPTION 'AI_catalog_relationships.supported_join_semantics already exists';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = 'AI_column_catalog'
                 AND column_name = 'resample_aggregation') THEN
        RAISE EXCEPTION 'AI_column_catalog.resample_aggregation already exists';
    END IF;
END;
$$;

-- BEGIN join semantics (tests apply this section to their catalog fixtures)
ALTER TABLE public."AI_catalog_relationships"
    ADD COLUMN supported_join_semantics text[] NOT NULL DEFAULT '{}'::text[],
    ADD COLUMN left_time_column text,
    ADD COLUMN right_time_column text,
    ADD COLUMN effective_from_column text,
    ADD COLUMN effective_to_column text;

ALTER TABLE public."AI_catalog_relationships"
    ADD CONSTRAINT "AI_catalog_relationships_join_semantics_check" CHECK (
        supported_join_semantics <@ ARRAY['CURRENT_STATE', 'EXACT_DATE', 'AS_OF', 'EFFECTIVE_DATED']::text[]
    ),
    ADD CONSTRAINT "AI_catalog_relationships_temporal_columns_check" CHECK (
        NOT (supported_join_semantics && ARRAY['EXACT_DATE', 'AS_OF']::text[])
        OR (left_time_column IS NOT NULL AND right_time_column IS NOT NULL)
    ),
    ADD CONSTRAINT "AI_catalog_relationships_effective_columns_check" CHECK (
        NOT ('EFFECTIVE_DATED' = ANY(supported_join_semantics))
        OR (effective_from_column IS NOT NULL AND effective_to_column IS NOT NULL)
    );

COMMENT ON COLUMN public."AI_catalog_relationships".supported_join_semantics IS
    'Join semantics a DataNeedSpec may request for this relationship: CURRENT_STATE, EXACT_DATE, AS_OF, EFFECTIVE_DATED.';
COMMENT ON COLUMN public."AI_catalog_relationships".left_time_column IS
    'Time column of left_table that EXACT_DATE and AS_OF joins align on.';
COMMENT ON COLUMN public."AI_catalog_relationships".right_time_column IS
    'Time column of right_table that EXACT_DATE and AS_OF joins align on (AS_OF: latest value at or before the observation).';
COMMENT ON COLUMN public."AI_catalog_relationships".effective_from_column IS
    'Inclusive start of validity of a right_table row for EFFECTIVE_DATED joins.';
COMMENT ON COLUMN public."AI_catalog_relationships".effective_to_column IS
    'Exclusive end of validity of a right_table row for EFFECTIVE_DATED joins; NULL means still valid.';

UPDATE public."AI_catalog_relationships"
SET supported_join_semantics = ARRAY['CURRENT_STATE']
WHERE left_table = 'IDX_Stock_Universe' AND right_table = 'Price_Stock_Indonesia_IDX';

UPDATE public."AI_catalog_relationships"
SET supported_join_semantics = ARRAY['CURRENT_STATE']
WHERE left_table = 'IDX_Broker_Profile' AND right_table = 'IDX_Broker_Summary';

UPDATE public."AI_catalog_relationships"
SET supported_join_semantics = ARRAY['EXACT_DATE'], left_time_column = 'date', right_time_column = 'date'
WHERE left_table = 'Price_Stock_Indonesia_IDX' AND right_table = 'Feature_01_Stock_Daily';

UPDATE public."AI_catalog_relationships"
SET supported_join_semantics = ARRAY['EXACT_DATE'], left_time_column = 'Date', right_time_column = 'date'
WHERE left_table = 'IDX_Broker_Summary' AND right_table = 'Feature_02_Broker_Rolling';

UPDATE public."AI_catalog_relationships"
SET supported_join_semantics = ARRAY['EXACT_DATE'], left_time_column = 'date', right_time_column = 'date'
WHERE left_table = 'Feature_02_Broker_Rolling' AND right_table = 'Feature_03_Stock_Broker_Daily';

ALTER TABLE public."AI_column_catalog"
    ADD COLUMN resample_aggregation text,
    ADD CONSTRAINT "AI_column_catalog_resample_aggregation_check" CHECK (
        resample_aggregation IS NULL OR resample_aggregation IN ('FIRST', 'LAST', 'MAX', 'MIN', 'SUM')
    );

COMMENT ON COLUMN public."AI_column_catalog".resample_aggregation IS
    'Exact rule for aggregating this column to a coarser frequency (FIRST, LAST, MAX, MIN, SUM); NULL = not established, never pushed down.';
-- END join semantics

INSERT INTO public."Column_Catalog" (
    table_schema, table_name, column_name, ordinal_position, data_type,
    is_nullable, default_expression, is_primary_key, definition,
    source_column_or_expression, unit, null_rule, source_code_paths,
    documentation_status
)
SELECT columns.table_schema, columns.table_name, columns.column_name, columns.ordinal_position,
       columns.data_type, columns.is_nullable = 'YES', columns.column_default, false,
       CASE columns.column_name
        WHEN 'supported_join_semantics' THEN 'Join semantics a DataNeedSpec may request for this relationship '
                                             '(CURRENT_STATE, EXACT_DATE, AS_OF, EFFECTIVE_DATED); empty means the '
                                             'DataNeed planner cannot use it.'
        WHEN 'left_time_column' THEN 'Time column of left_table used by EXACT_DATE and AS_OF joins.'
        WHEN 'right_time_column' THEN 'Time column of right_table used by EXACT_DATE and AS_OF joins.'
        WHEN 'effective_from_column' THEN 'Inclusive validity start of a right_table row for EFFECTIVE_DATED joins.'
        WHEN 'effective_to_column' THEN 'Exclusive validity end of a right_table row for EFFECTIVE_DATED joins; '
                                        'NULL in the data means still valid.'
        WHEN 'resample_aggregation' THEN 'Exact aggregation rule to a coarser frequency (FIRST, LAST, MAX, MIN, '
                                         'SUM); NULL means no established rule, so resampling is never pushed down.'
       END,
       'Curated by migration 20260925_003', NULL,
       CASE WHEN columns.is_nullable = 'YES' THEN 'NULL when the concept does not apply.'
            ELSE 'NULL is not permitted.' END,
       ARRAY['database/migrations/20260925_003_add_relationship_join_semantics.sql',
             'apps/market-sql-governor/app/catalog_contract.py'],
       'PARTIAL'
FROM information_schema.columns AS columns
WHERE columns.table_schema = 'public'
  AND ((columns.table_name = 'AI_catalog_relationships'
        AND columns.column_name IN ('supported_join_semantics', 'left_time_column', 'right_time_column',
                                    'effective_from_column', 'effective_to_column'))
       OR (columns.table_name = 'AI_column_catalog' AND columns.column_name = 'resample_aggregation'));

UPDATE public."Table_Catalog"
SET source_code_paths = array_append(source_code_paths,
                                     'database/migrations/20260925_003_add_relationship_join_semantics.sql')
WHERE table_schema = 'public' AND table_name IN ('AI_catalog_relationships', 'AI_column_catalog')
  AND NOT ('database/migrations/20260925_003_add_relationship_join_semantics.sql' = ANY(source_code_paths));

DO $verify$
BEGIN
    IF EXISTS (SELECT 1 FROM public."AI_catalog_relationships"
               WHERE cardinality(supported_join_semantics) = 0
                 AND left_table IN ('IDX_Stock_Universe', 'IDX_Broker_Profile', 'Price_Stock_Indonesia_IDX',
                                    'IDX_Broker_Summary', 'Feature_02_Broker_Rolling')) THEN
        RAISE EXCEPTION 'Every seeded relationship needs its join semantics';
    END IF;
    IF EXISTS (SELECT 1 FROM public."AI_column_catalog" WHERE resample_aggregation IS NOT NULL) THEN
        RAISE EXCEPTION 'This migration seeds no resample rule';
    END IF;
    IF (SELECT count(*) FROM public."Column_Catalog"
        WHERE (table_name = 'AI_catalog_relationships'
               AND column_name IN ('supported_join_semantics', 'left_time_column', 'right_time_column',
                                   'effective_from_column', 'effective_to_column'))
           OR (table_name = 'AI_column_catalog' AND column_name = 'resample_aggregation')) <> 6 THEN
        RAISE EXCEPTION 'Every new catalog column needs a Column_Catalog definition';
    END IF;
END;
$verify$;

COMMIT;
