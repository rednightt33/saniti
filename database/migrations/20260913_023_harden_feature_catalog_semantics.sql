-- Add an analyst-facing semantic contract to every validated Feature column.
-- The existing definition/calculation fields remain the formula authority.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '10min';

DO $preflight$
BEGIN
    IF (SELECT count(*) FROM public."Feature_Catalog" WHERE is_active) <> 91 THEN
        RAISE EXCEPTION 'Expected exactly 91 active Feature definitions before semantic hardening';
    END IF;
END
$preflight$;

ALTER TABLE public."Feature_Catalog"
    ADD COLUMN analytical_interpretation text,
    ADD COLUMN recommended_use text,
    ADD COLUMN misuse_warning text,
    ADD COLUMN semantic_review_status text,
    ADD COLUMN validation_evidence text[];

-- These four fields passed formula validation but were not sufficiently explicit
-- for an analyst reading the catalog without opening the source migration.
UPDATE public."Feature_Catalog"
SET definition = CASE feature_column
        WHEN 'net_value_1d' THEN
            'Net broker traded value for this ticker, board and transaction date: buy_value_1d minus sell_value_1d. Positive means the broker was a net buyer; negative means it was a net seller; zero means balanced value.'
        WHEN 'net_lots_1d' THEN
            'Net broker traded lots for this ticker, board and transaction date: buy_lots_1d minus sell_lots_1d. Positive means net bought lots; negative means net sold lots; zero means balanced lots.'
        ELSE definition
    END
WHERE feature_table = 'Feature_02_Broker_Rolling'
  AND feature_column IN ('net_value_1d','net_lots_1d')
  AND is_active;

UPDATE public."Feature_Catalog"
SET null_rule = CASE feature_column
        WHEN 'ticker' THEN
            'Never NULL. A row exists only for a nonblank source symbol present in Feature_02_Broker_Rolling; symbols are not restricted to the current IDX stock universe.'
        WHEN 'market_board' THEN
            'Never NULL. Exactly one source board label is stored: Regular, Nego, or Tunai; boards are separate analytical populations and are never implicitly combined.'
        ELSE null_rule
    END
WHERE feature_table = 'Feature_03_Stock_Broker_Daily'
  AND feature_column IN ('ticker','market_board')
  AND is_active;

UPDATE public."Feature_Catalog" AS f
SET analytical_interpretation = CASE
        WHEN f.semantic_role = 'IDENTITY' THEN format(
            '%s is an identity key at grain "%s". It locates an observation and is not itself an investment signal. Definition: %s',
            f.feature_column, f.grain, f.definition)
        WHEN f.semantic_role = 'DIMENSION' THEN format(
            '%s is a contextual dimension used to segment or label observations. Category membership changes comparison context but does not by itself imply expected return. Definition: %s',
            f.feature_column, f.definition)
        WHEN f.ranking_interpretation = 'HIGHER' THEN format(
            'A larger %s means more of the measured %s quantity under this exact formula; it is not automatically bullish or superior. Definition: %s',
            f.feature_column, lower(f.feature_category), f.definition)
        WHEN f.ranking_interpretation = 'LOWER' THEN format(
            'A smaller %s is the preferred ranking direction only for the documented analytical use; sign, scale and market context still matter. Definition: %s',
            f.feature_column, f.definition)
        WHEN f.ranking_interpretation = 'CONTEXTUAL' THEN format(
            'Interpret %s by its sign, magnitude, null state, own history, peer distribution and market regime; no universal high-is-good rule applies. Definition: %s',
            f.feature_column, f.definition)
        ELSE format(
            '%s is operational or descriptive metadata, not a numeric ranking signal. Definition: %s',
            f.feature_column, f.definition)
    END,
    recommended_use = CASE
        WHEN f.semantic_role = 'IDENTITY' THEN format(
            'Use %s for exact filtering, ordering, grouping, joins, deduplication or evidence labeling only where the registered grain and relationship contract permit it.',
            f.feature_column)
        WHEN f.semantic_role = 'DIMENSION' THEN format(
            'Use %s to create explicit peer groups or filters, and disclose the selected population in the result.',
            f.feature_column)
        WHEN f.feature_category = 'Return' THEN format(
            'Use %s to describe realized trailing price performance, rank comparable observations, or combine with separately validated risk and flow evidence.',
            f.feature_column)
        WHEN f.feature_category = 'Volatility' THEN format(
            'Use %s for realized-risk comparison, regime context, anomaly review, or risk-adjusted screening; compare like windows and units.',
            f.feature_column)
        WHEN f.feature_category = 'Volume' THEN format(
            'Use %s to assess participation or abnormal activity relative to the documented volume window and available history.',
            f.feature_column)
        WHEN f.feature_category = 'Price Positioning' THEN format(
            'Use %s to locate price relative to its documented prior high or drawdown reference; combine with liquidity and regime context.',
            f.feature_column)
        WHEN f.feature_category IN ('Broker Flow','Broker Persistence','Broker Abnormality','Broker Concentration') THEN format(
            'Use %s to compare broker activity at the exact ticker, board, broker and transaction-date grain documented here; aggregate only with approved operations.',
            f.feature_column)
        ELSE format(
            'Use %s only for the operational or descriptive purpose stated in its definition and availability rule.',
            f.feature_column)
    END,
    misuse_warning = concat_ws(' ',
        CASE
            WHEN f.feature_table IN ('Feature_02_Broker_Rolling','Feature_03_Stock_Broker_Daily') THEN
                'Do not combine Regular, Nego and Tunai implicitly; board must remain explicit or be deliberately aggregated.'
            ELSE NULL
        END,
        CASE
            WHEN f.lookback_window ILIKE '%transaction date%' OR f.lookback_window ILIKE '%trading observation%' THEN
                'Window counts are observed transaction/trading dates, not calendar days.'
            ELSE NULL
        END,
        CASE
            WHEN NOT f.point_in_time_safe THEN coalesce(nullif(btrim(f.historical_metadata_warning),''),
                'This field is not point-in-time safe for historical inference.')
            ELSE NULL
        END,
        format('Respect the NULL contract: %s', f.null_rule),
        CASE
            WHEN f.semantic_role = 'MEASURE' THEN
                'Do not treat a single high, low, positive, negative or extreme observation as predictive evidence without historical validation and appropriate benchmarks.'
            ELSE
                'Do not reinterpret this identifier or dimension as a numeric investment score.'
        END
    ),
    semantic_review_status = 'CALCULATION_VERIFIED',
    validation_evidence = CASE f.feature_table
        WHEN 'Feature_01_Stock_Daily' THEN ARRAY[
            'database/migrations/20260912_001_create_feature_01_stock_daily.sql',
            'database/migrations/20260913_001_create_feature_catalog.sql',
            'DATABASE_CHANGELOG.md#2026-09-12-create-and-backfill-feature-01-stock-daily'
        ]
        WHEN 'Feature_02_Broker_Rolling' THEN ARRAY[
            'database/migrations/20260913_007_create_feature_02_broker_rolling.sql',
            'scripts/validate_feature_02.py',
            'FEATURE_02_BROKER_ROLLING.md'
        ]
        WHEN 'Feature_03_Stock_Broker_Daily' THEN ARRAY[
            'database/migrations/20260913_009_create_feature_03_stock_broker_daily.sql',
            'scripts/validate_feature_03.py',
            'FEATURE_03_STOCK_BROKER_DAILY.md'
        ]
        ELSE ARRAY['DATABASE_CHANGELOG.md']
    END
WHERE f.is_active;

ALTER TABLE public."Feature_Catalog"
    ALTER COLUMN analytical_interpretation SET NOT NULL,
    ALTER COLUMN recommended_use SET NOT NULL,
    ALTER COLUMN misuse_warning SET NOT NULL,
    ALTER COLUMN semantic_review_status SET NOT NULL,
    ALTER COLUMN validation_evidence SET NOT NULL,
    ADD CONSTRAINT "Feature_Catalog_semantic_guidance_check" CHECK (
        btrim(analytical_interpretation) <> ''
        AND btrim(recommended_use) <> ''
        AND btrim(misuse_warning) <> ''
    ),
    ADD CONSTRAINT "Feature_Catalog_semantic_review_status_check" CHECK (
        semantic_review_status IN ('NEEDS_REVIEW','SOURCE_VERIFIED','CALCULATION_VERIFIED')
    ),
    ADD CONSTRAINT "Feature_Catalog_validation_evidence_check" CHECK (
        cardinality(validation_evidence) > 0
        AND array_position(validation_evidence, '') IS NULL
    );

COMMENT ON COLUMN public."Feature_Catalog".analytical_interpretation IS
    'Plain-language interpretation of sign, magnitude, category and analytical context; not a formula substitute.';
COMMENT ON COLUMN public."Feature_Catalog".recommended_use IS
    'Approved analyst use cases for this exact Feature column and grain.';
COMMENT ON COLUMN public."Feature_Catalog".misuse_warning IS
    'Column-specific analytical traps, null/board/window caveats and claims that must not be inferred.';
COMMENT ON COLUMN public."Feature_Catalog".semantic_review_status IS
    'Evidence grade for semantic guidance: NEEDS_REVIEW, SOURCE_VERIFIED, or CALCULATION_VERIFIED.';
COMMENT ON COLUMN public."Feature_Catalog".validation_evidence IS
    'Repository evidence paths supporting the formula and semantic review status.';

UPDATE public."Tool_Catalog"
SET tool_specific_limits = tool_specific_limits || jsonb_build_object(
        'feature_metadata_tokens_per_analysis', 5000,
        'semantic_preflight', 'Relevant definitions must be loaded before data retrieval or aggregation'
    )
WHERE is_active AND tool_name = 'get_feature_definition';

UPDATE public."Table_Catalog"
SET definition = 'Versioned, machine-readable formula, interpretation, recommended-use, misuse, availability, point-in-time safety and validation-evidence contract for every validated Feature column.',
    source_code_paths = CASE
        WHEN 'database/migrations/20260913_023_harden_feature_catalog_semantics.sql' = ANY(source_code_paths)
            THEN source_code_paths
        ELSE array_append(source_code_paths,
            'database/migrations/20260913_023_harden_feature_catalog_semantics.sql')
    END
WHERE table_schema = 'public' AND table_name = 'Feature_Catalog';

INSERT INTO public."Column_Catalog" (
    table_schema, table_name, column_name, ordinal_position, data_type,
    is_nullable, default_expression, is_primary_key, definition,
    source_column_or_expression, unit, null_rule, source_code_paths,
    documentation_status
)
SELECT c.table_schema, c.table_name, c.column_name, c.ordinal_position,
       c.data_type, false, c.column_default, false,
       pg_catalog.col_description(pc.oid, pa.attnum),
       'Defined by database/migrations/20260913_023_harden_feature_catalog_semantics.sql',
       NULL, 'Never NULL; every Feature definition must carry complete semantic guidance.',
       ARRAY['database/migrations/20260913_023_harden_feature_catalog_semantics.sql'],
       'VERIFIED'
FROM information_schema.columns AS c
JOIN pg_catalog.pg_class AS pc
  ON pc.oid = format('%I.%I', c.table_schema, c.table_name)::regclass
JOIN pg_catalog.pg_attribute AS pa
  ON pa.attrelid = pc.oid AND pa.attname = c.column_name
LEFT JOIN public."Column_Catalog" AS existing
  ON existing.table_schema=c.table_schema AND existing.table_name=c.table_name
 AND existing.column_name=c.column_name
WHERE c.table_schema='public' AND c.table_name='Feature_Catalog'
  AND c.column_name IN (
      'analytical_interpretation','recommended_use','misuse_warning',
      'semantic_review_status','validation_evidence'
  )
  AND existing.column_name IS NULL;

DO $validate$
DECLARE
    active_count integer;
    incomplete_count integer;
    missing_physical_count integer;
    missing_generic_catalog_count integer;
BEGIN
    SELECT count(*) INTO active_count
    FROM public."Feature_Catalog" WHERE is_active;

    SELECT count(*) INTO incomplete_count
    FROM public."Feature_Catalog"
    WHERE is_active AND (
        btrim(analytical_interpretation) = '' OR btrim(recommended_use) = ''
        OR btrim(misuse_warning) = ''
        OR semantic_review_status <> 'CALCULATION_VERIFIED'
        OR cardinality(validation_evidence) < 3
    );

    SELECT count(*) INTO missing_physical_count
    FROM public."Feature_Catalog" AS f
    LEFT JOIN information_schema.columns AS c
      ON c.table_schema='public' AND c.table_name=f.feature_table
     AND c.column_name=f.feature_column
    WHERE f.is_active AND c.column_name IS NULL;

    SELECT count(*) INTO missing_generic_catalog_count
    FROM information_schema.columns AS c
    WHERE c.table_schema='public' AND c.table_name='Feature_Catalog'
      AND NOT EXISTS (
          SELECT 1 FROM public."Column_Catalog" AS cc
          WHERE cc.table_schema=c.table_schema AND cc.table_name=c.table_name
            AND cc.column_name=c.column_name
      );

    IF active_count <> 91 OR incomplete_count <> 0
       OR missing_physical_count <> 0 OR missing_generic_catalog_count <> 0 THEN
        RAISE EXCEPTION
            'Feature semantic validation failed: active %, incomplete %, missing physical %, missing generic catalog %',
            active_count, incomplete_count, missing_physical_count, missing_generic_catalog_count;
    END IF;
END
$validate$;

COMMIT;
