BEGIN;

DO $$
DECLARE
    target_name text;
BEGIN
    FOREACH target_name IN ARRAY ARRAY[
        'AI_table_catalog',
        'AI_column_catalog',
        'AI_catalog_relationships',
        'AI_calculation_catalog',
        'AI_data_coverage'
    ]
    LOOP
        IF to_regclass(format('public.%I', target_name)) IS NOT NULL THEN
            RAISE EXCEPTION 'Migration target public.% already exists', target_name;
        END IF;
    END LOOP;
END;
$$;

CREATE TABLE public."AI_table_catalog" (
    table_name text PRIMARY KEY,
    description text NOT NULL,
    category text NOT NULL,
    grain text NOT NULL,
    primary_key_columns text[] NOT NULL,
    time_column text,
    entity_column text NOT NULL,
    owner text NOT NULL DEFAULT 'Saniti',
    is_active boolean NOT NULL DEFAULT true,
    ai_access_level text NOT NULL DEFAULT 'BOUNDED_READ',
    freshness_sla interval,
    coverage_enabled boolean NOT NULL DEFAULT true,
    documentation_status text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "AI_table_catalog_name_check" CHECK (btrim(table_name) <> ''),
    CONSTRAINT "AI_table_catalog_category_check" CHECK (
        category IN ('REFERENCE', 'TRANSACTIONAL', 'FEATURE')
    ),
    CONSTRAINT "AI_table_catalog_access_check" CHECK (
        ai_access_level IN ('BOUNDED_READ', 'DENIED')
    ),
    CONSTRAINT "AI_table_catalog_documentation_check" CHECK (
        documentation_status IN ('VERIFIED', 'PARTIAL', 'NEEDS_REVIEW')
    ),
    CONSTRAINT "AI_table_catalog_timestamp_check" CHECK (updated_at >= created_at)
);

CREATE TABLE public."AI_column_catalog" (
    table_name text NOT NULL,
    column_name text NOT NULL,
    ordinal_position integer NOT NULL,
    description text,
    data_type text NOT NULL,
    semantic_type text NOT NULL,
    unit text,
    nullable boolean NOT NULL,
    is_primary_key boolean NOT NULL,
    source_column_or_expression text,
    is_sensitive boolean NOT NULL DEFAULT false,
    ai_allowed boolean NOT NULL DEFAULT true,
    allowed_aggregations text[] NOT NULL DEFAULT '{}',
    filter_allowed boolean NOT NULL DEFAULT true,
    group_by_allowed boolean NOT NULL DEFAULT false,
    example_value text,
    coverage_required boolean NOT NULL DEFAULT false,
    documentation_status text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "AI_column_catalog_pkey" PRIMARY KEY (table_name, column_name),
    CONSTRAINT "AI_column_catalog_table_fkey" FOREIGN KEY (table_name)
        REFERENCES public."AI_table_catalog"(table_name) ON DELETE CASCADE,
    CONSTRAINT "AI_column_catalog_position_check" CHECK (ordinal_position > 0),
    CONSTRAINT "AI_column_catalog_semantic_check" CHECK (
        semantic_type IN ('IDENTIFIER', 'TIME', 'DIMENSION', 'MEASURE')
    ),
    CONSTRAINT "AI_column_catalog_aggregations_check" CHECK (
        allowed_aggregations <@ ARRAY[
            'SUM','AVG','MEDIAN','MIN','MAX','COUNT','COUNT_DISTINCT',
            'PERCENTILE','WEIGHTED_AVG'
        ]::text[]
    ),
    CONSTRAINT "AI_column_catalog_documentation_check" CHECK (
        documentation_status IN ('VERIFIED', 'PARTIAL', 'NEEDS_REVIEW')
    ),
    CONSTRAINT "AI_column_catalog_timestamp_check" CHECK (updated_at >= created_at)
);

CREATE TABLE public."AI_catalog_relationships" (
    relationship_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    left_table text NOT NULL,
    left_columns text[] NOT NULL,
    right_table text NOT NULL,
    right_columns text[] NOT NULL,
    relationship_type text NOT NULL,
    temporal_rule text NOT NULL,
    safe_output_grain text NOT NULL,
    requires_preaggregation boolean NOT NULL DEFAULT false,
    description text NOT NULL,
    version text NOT NULL DEFAULT 'v1',
    is_allowed boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "AI_catalog_relationships_left_fkey" FOREIGN KEY (left_table)
        REFERENCES public."AI_table_catalog"(table_name),
    CONSTRAINT "AI_catalog_relationships_right_fkey" FOREIGN KEY (right_table)
        REFERENCES public."AI_table_catalog"(table_name),
    CONSTRAINT "AI_catalog_relationships_columns_check" CHECK (
        cardinality(left_columns) > 0
        AND cardinality(left_columns) = cardinality(right_columns)
    ),
    CONSTRAINT "AI_catalog_relationships_type_check" CHECK (
        relationship_type IN ('ONE_TO_ONE','ONE_TO_MANY','MANY_TO_ONE','MANY_TO_MANY')
    ),
    CONSTRAINT "AI_catalog_relationships_version_check" CHECK (version ~ '^v[1-9][0-9]*$'),
    CONSTRAINT "AI_catalog_relationships_unique" UNIQUE (left_table, right_table, version),
    CONSTRAINT "AI_catalog_relationships_timestamp_check" CHECK (updated_at >= created_at)
);

CREATE TABLE public."AI_calculation_catalog" (
    calculation_name text NOT NULL,
    version text NOT NULL,
    target_table text NOT NULL,
    target_columns text[] NOT NULL,
    definition text NOT NULL,
    required_inputs jsonb NOT NULL,
    parameters jsonb NOT NULL DEFAULT '{}',
    defaults jsonb NOT NULL DEFAULT '{}',
    implementation_ref text[] NOT NULL,
    alignment_rules text NOT NULL,
    missing_data_policy text NOT NULL,
    output_definition jsonb NOT NULL,
    validation_evidence text[] NOT NULL,
    status text NOT NULL DEFAULT 'ACTIVE',
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "AI_calculation_catalog_pkey" PRIMARY KEY (
        target_table, calculation_name, version
    ),
    CONSTRAINT "AI_calculation_catalog_table_fkey" FOREIGN KEY (target_table)
        REFERENCES public."AI_table_catalog"(table_name) ON DELETE CASCADE,
    CONSTRAINT "AI_calculation_catalog_version_check" CHECK (version ~ '^v[1-9][0-9]*$'),
    CONSTRAINT "AI_calculation_catalog_status_check" CHECK (
        status IN ('ACTIVE', 'INACTIVE')
    ),
    CONSTRAINT "AI_calculation_catalog_json_check" CHECK (
        jsonb_typeof(required_inputs) = 'object'
        AND jsonb_typeof(parameters) = 'object'
        AND jsonb_typeof(defaults) = 'object'
        AND jsonb_typeof(output_definition) = 'object'
    ),
    CONSTRAINT "AI_calculation_catalog_timestamp_check" CHECK (updated_at >= created_at)
);

CREATE TABLE public."AI_data_coverage" (
    coverage_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dataset_name text NOT NULL,
    coverage_scope text NOT NULL,
    entity_id text,
    reference_dataset_name text,
    coverage_mode text NOT NULL,
    actual_min_date date,
    actual_max_date date,
    expected_min_date date,
    expected_max_date date,
    source_row_count bigint,
    source_key_count bigint,
    pipeline_status text NOT NULL,
    verification_status text NOT NULL,
    quality_status text NOT NULL,
    check_error text,
    last_checked_at timestamptz NOT NULL,
    last_full_checked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "AI_data_coverage_dataset_fkey" FOREIGN KEY (dataset_name)
        REFERENCES public."AI_table_catalog"(table_name) ON DELETE CASCADE,
    CONSTRAINT "AI_data_coverage_reference_fkey" FOREIGN KEY (reference_dataset_name)
        REFERENCES public."AI_table_catalog"(table_name),
    CONSTRAINT "AI_data_coverage_scope_check" CHECK (
        coverage_scope IN ('DATASET', 'ENTITY')
    ),
    CONSTRAINT "AI_data_coverage_entity_check" CHECK (
        (coverage_scope = 'DATASET' AND entity_id IS NULL)
        OR (coverage_scope = 'ENTITY' AND entity_id IS NOT NULL AND btrim(entity_id) <> '')
    ),
    CONSTRAINT "AI_data_coverage_mode_check" CHECK (
        coverage_mode IN ('ACTUAL_SOURCE', 'EXPECTED_DERIVED', 'SNAPSHOT')
    ),
    CONSTRAINT "AI_data_coverage_verification_check" CHECK (
        verification_status IN ('VERIFIED', 'PIPELINE_CONFIRMED', 'UNVERIFIED')
    ),
    CONSTRAINT "AI_data_coverage_quality_check" CHECK (
        quality_status IN ('HEALTHY', 'WARNING', 'FAILED', 'ERROR')
    ),
    CONSTRAINT "AI_data_coverage_counts_check" CHECK (
        (source_row_count IS NULL OR source_row_count >= 0)
        AND (source_key_count IS NULL OR source_key_count >= 0)
    ),
    CONSTRAINT "AI_data_coverage_actual_dates_check" CHECK (
        actual_min_date IS NULL OR actual_max_date IS NULL OR actual_max_date >= actual_min_date
    ),
    CONSTRAINT "AI_data_coverage_expected_dates_check" CHECK (
        expected_min_date IS NULL OR expected_max_date IS NULL OR expected_max_date >= expected_min_date
    ),
    CONSTRAINT "AI_data_coverage_timestamp_check" CHECK (updated_at >= created_at)
);

CREATE UNIQUE INDEX "AI_data_coverage_identity_idx"
    ON public."AI_data_coverage" (
        dataset_name,
        coverage_scope,
        COALESCE(entity_id, '')
    );
CREATE INDEX "AI_data_coverage_status_idx"
    ON public."AI_data_coverage" (quality_status, verification_status, dataset_name);
CREATE INDEX "AI_data_coverage_reference_idx"
    ON public."AI_data_coverage" (reference_dataset_name, entity_id)
    WHERE reference_dataset_name IS NOT NULL;

CREATE TRIGGER "AI_table_catalog_set_updated_at"
BEFORE UPDATE ON public."AI_table_catalog"
FOR EACH ROW EXECUTE FUNCTION public.set_database_catalog_updated_at();

CREATE TRIGGER "AI_column_catalog_set_updated_at"
BEFORE UPDATE ON public."AI_column_catalog"
FOR EACH ROW EXECUTE FUNCTION public.set_database_catalog_updated_at();

CREATE TRIGGER "AI_catalog_relationships_set_updated_at"
BEFORE UPDATE ON public."AI_catalog_relationships"
FOR EACH ROW EXECUTE FUNCTION public.set_database_catalog_updated_at();

CREATE TRIGGER "AI_calculation_catalog_set_updated_at"
BEFORE UPDATE ON public."AI_calculation_catalog"
FOR EACH ROW EXECUTE FUNCTION public.set_database_catalog_updated_at();

CREATE TRIGGER "AI_data_coverage_set_updated_at"
BEFORE UPDATE ON public."AI_data_coverage"
FOR EACH ROW EXECUTE FUNCTION public.set_database_catalog_updated_at();

COMMENT ON TABLE public."AI_table_catalog" IS
    'AI-facing master list for the seven approved Indonesian equity data tables.';
COMMENT ON TABLE public."AI_column_catalog" IS
    'AI-facing column meanings and bounded-query permissions for approved tables.';
COMMENT ON TABLE public."AI_catalog_relationships" IS
    'AI-facing safe join and output-grain contracts across approved tables.';
COMMENT ON TABLE public."AI_calculation_catalog" IS
    'AI-facing calculation contracts derived from active Feature Catalog definitions.';
COMMENT ON TABLE public."AI_data_coverage" IS
    'Automated raw-source coverage and explicitly inferred derived-table expectations; Feature 01-03 are never scanned by the coverage job.';

WITH requested(table_name, time_column, entity_column, freshness_sla) AS (
    VALUES
      ('IDX_Broker_Summary', 'Date', 'Symbol', interval '1 day'),
      ('IDX_Stock_Universe', NULL, 'Ticker', interval '30 days'),
      ('IDX_Broker_Profile', NULL, 'broker_code', interval '365 days'),
      ('Feature_01_Stock_Daily', 'date', 'ticker', interval '1 day'),
      ('Feature_02_Broker_Rolling', 'date', 'ticker', interval '1 day'),
      ('Feature_03_Stock_Broker_Daily', 'date', 'ticker', interval '1 day'),
      ('Price_Stock_Indonesia_IDX', 'date', 'ticker', interval '1 day')
)
INSERT INTO public."AI_table_catalog" (
    table_name, description, category, grain, primary_key_columns,
    time_column, entity_column, owner, is_active, ai_access_level,
    freshness_sla, coverage_enabled, documentation_status
)
SELECT
    catalog.table_name,
    catalog.definition,
    upper(catalog.category),
    catalog.grain,
    catalog.primary_key_columns,
    requested.time_column,
    requested.entity_column,
    'Saniti',
    true,
    'BOUNDED_READ',
    requested.freshness_sla,
    true,
    catalog.documentation_status
FROM requested
JOIN public."Table_Catalog" AS catalog
  ON catalog.table_schema = 'public'
 AND catalog.table_name = requested.table_name;

DO $$
BEGIN
    IF (SELECT count(*) FROM public."AI_table_catalog") <> 7 THEN
        RAISE EXCEPTION 'AI_table_catalog seed expected 7 rows';
    END IF;
END;
$$;

INSERT INTO public."AI_column_catalog" (
    table_name, column_name, ordinal_position, description, data_type,
    semantic_type, unit, nullable, is_primary_key,
    source_column_or_expression, is_sensitive, ai_allowed,
    allowed_aggregations, filter_allowed, group_by_allowed,
    example_value, coverage_required, documentation_status
)
SELECT
    columns.table_name,
    columns.column_name,
    columns.ordinal_position,
    columns.definition,
    columns.data_type,
    CASE
      WHEN feature.semantic_role = 'IDENTITY' THEN 'IDENTIFIER'
      WHEN feature.semantic_role IN ('DIMENSION', 'MEASURE') THEN feature.semantic_role
      WHEN columns.column_name = master.time_column THEN 'TIME'
      WHEN columns.is_primary_key THEN 'IDENTIFIER'
      WHEN columns.data_type IN (
          'smallint','integer','bigint','numeric','real','double precision'
      ) THEN 'MEASURE'
      ELSE 'DIMENSION'
    END,
    COALESCE(feature.unit, columns.unit),
    columns.is_nullable,
    columns.is_primary_key,
    COALESCE(feature.source_columns, columns.source_column_or_expression),
    false,
    true,
    CASE
      WHEN feature.feature_column IS NOT NULL THEN feature.allowed_aggregations
      WHEN columns.data_type IN (
          'smallint','integer','bigint','numeric','real','double precision'
      ) AND NOT columns.is_primary_key THEN ARRAY['SUM','AVG','MIN','MAX']::text[]
      ELSE ARRAY['COUNT','COUNT_DISTINCT']::text[]
    END,
    true,
    CASE
      WHEN feature.feature_column IS NOT NULL THEN feature.is_groupable
      ELSE COALESCE(
        columns.is_primary_key
        OR columns.column_name = master.time_column
        OR columns.column_name = master.entity_column
        OR columns.data_type NOT IN (
            'smallint','integer','bigint','numeric','real','double precision'
        ),
        false
      )
    END,
    NULL,
    COALESCE(
        columns.is_primary_key
        OR columns.column_name = master.time_column
        OR columns.column_name = master.entity_column,
        false
    ),
    columns.documentation_status
FROM public."AI_table_catalog" AS master
JOIN public."Column_Catalog" AS columns
  ON columns.table_schema = 'public'
 AND columns.table_name = master.table_name
LEFT JOIN public."Feature_Catalog" AS feature
  ON feature.feature_table = columns.table_name
 AND feature.feature_column = columns.column_name
 AND feature.is_active;

INSERT INTO public."AI_catalog_relationships" (
    left_table, left_columns, right_table, right_columns,
    relationship_type, temporal_rule, safe_output_grain,
    requires_preaggregation, description, version, is_allowed
)
VALUES
  (
    'Price_Stock_Indonesia_IDX', ARRAY['ticker','date'],
    'Feature_01_Stock_Daily', ARRAY['ticker','date'],
    'ONE_TO_ONE', 'Exact trading date', 'date x ticker', false,
    'Source price candle to the corresponding daily stock feature row.', 'v1', true
  ),
  (
    'IDX_Stock_Universe', ARRAY['Ticker'],
    'Price_Stock_Indonesia_IDX', ARRAY['ticker'],
    'ONE_TO_MANY', 'Current-state reference metadata', 'date x ticker', false,
    'Current stock-universe identity and classification joined to price history.', 'v1', true
  ),
  (
    'IDX_Broker_Profile', ARRAY['broker_code'],
    'IDX_Broker_Summary', ARRAY['Broker'],
    'ONE_TO_MANY', 'Current-state broker metadata',
    'Broker Summary primary-key grain', false,
    'Current broker identity and classification joined to broker activity.', 'v1', true
  ),
  (
    'IDX_Broker_Summary',
    ARRAY['Date','Symbol','Broker','Investor Type','Market Board'],
    'Feature_02_Broker_Rolling',
    ARRAY['date','ticker','broker','investor_type','market_board'],
    'ONE_TO_ONE', 'Exact source trading date',
    'date x ticker x broker x investor_type x market_board', false,
    'Broker Summary source row to its canonical Feature 02 daily identity.', 'v1', true
  ),
  (
    'Feature_02_Broker_Rolling', ARRAY['ticker','date','market_board'],
    'Feature_03_Stock_Broker_Daily', ARRAY['ticker','date','market_board'],
    'MANY_TO_ONE', 'Exact trading date and market board',
    'date x ticker x market_board', true,
    'Feature 02 must be aggregated across broker and investor type before joining Feature 03.',
    'v1', true
  );

INSERT INTO public."AI_calculation_catalog" (
    calculation_name, version, target_table, target_columns, definition,
    required_inputs, parameters, defaults, implementation_ref,
    alignment_rules, missing_data_policy, output_definition,
    validation_evidence, status
)
SELECT
    feature.feature_column,
    feature.version,
    feature.feature_table,
    ARRAY[feature.feature_column],
    feature.definition,
    jsonb_build_object(
        'source_tables', string_to_array(feature.source_tables, ' | '),
        'source_columns', string_to_array(feature.source_columns, ' | ')
    ),
    jsonb_build_object(
        'lookback_window', feature.lookback_window,
        'minimum_history', feature.minimum_history
    ),
    '{}'::jsonb,
    table_catalog.source_code_paths,
    feature.dependency_rule,
    feature.null_rule,
    jsonb_build_object(
        'unit', feature.unit,
        'semantic_role', feature.semantic_role,
        'allowed_aggregations', feature.allowed_aggregations,
        'availability_rule', feature.availability_rule,
        'point_in_time_safe', feature.point_in_time_safe
    ),
    feature.validation_evidence,
    'ACTIVE'
FROM public."Feature_Catalog" AS feature
JOIN public."Table_Catalog" AS table_catalog
  ON table_catalog.table_schema = 'public'
 AND table_catalog.table_name = feature.feature_table
WHERE feature.is_active
  AND feature.feature_table IN (
      'Feature_01_Stock_Daily',
      'Feature_02_Broker_Rolling',
      'Feature_03_Stock_Broker_Daily'
  );

INSERT INTO public."Table_Catalog" (
    table_schema, table_name, category, definition, grain,
    primary_key_columns, source_system, source_tables, source_code_paths,
    update_rule, related_functions, documentation_status,
    readiness_mode, readiness_date_column, observation_date_column,
    data_available_at_column, availability_rule, point_in_time_status,
    historical_metadata_method
)
VALUES
  (
    'public','AI_table_catalog','Reference',
    'AI-facing master list and bounded-access contract for seven approved source and Feature tables.',
    'One row per approved table', ARRAY['table_name'],
    'Curated from Table_Catalog', ARRAY['Table_Catalog'],
    ARRAY['database/migrations/20260922_001_create_ai_catalogs.sql'],
    'Controlled migration or reviewed metadata change only.',
    ARRAY['set_database_catalog_updated_at()'], 'VERIFIED',
    'NOT_APPLICABLE', NULL, NULL, NULL,
    'Metadata only; it does not represent historical observations.',
    'NOT_APPLICABLE', NULL
  ),
  (
    'public','AI_column_catalog','Reference',
    'AI-facing column semantics and bounded-query permissions for the seven approved tables.',
    'One row per approved physical column', ARRAY['table_name','column_name'],
    'Curated from Column_Catalog and active Feature_Catalog definitions',
    ARRAY['Column_Catalog','Feature_Catalog'],
    ARRAY['database/migrations/20260922_001_create_ai_catalogs.sql'],
    'Controlled migration or reviewed metadata change only.',
    ARRAY['set_database_catalog_updated_at()'], 'VERIFIED',
    'NOT_APPLICABLE', NULL, NULL, NULL,
    'Metadata only; it does not represent historical observations.',
    'NOT_APPLICABLE', NULL
  ),
  (
    'public','AI_catalog_relationships','Reference',
    'AI-facing safe join, temporal alignment, preaggregation, and output-grain contracts.',
    'One row per table relationship and version', ARRAY['relationship_id'],
    'Curated relationship contracts',
    ARRAY['Feature_Relationship_Catalog'],
    ARRAY['database/migrations/20260922_001_create_ai_catalogs.sql'],
    'Controlled migration or reviewed relationship change only.',
    ARRAY['set_database_catalog_updated_at()'], 'VERIFIED',
    'NOT_APPLICABLE', NULL, NULL, NULL,
    'Metadata only; it does not represent historical observations.',
    'NOT_APPLICABLE', NULL
  ),
  (
    'public','AI_calculation_catalog','Reference',
    'AI-facing calculation contracts derived from active, validated Feature definitions.',
    'One row per target table, calculated column, and version',
    ARRAY['target_table','calculation_name','version'],
    'Active Feature_Catalog definitions', ARRAY['Feature_Catalog'],
    ARRAY['database/migrations/20260922_001_create_ai_catalogs.sql'],
    'Controlled migration after validated Feature definition changes.',
    ARRAY['set_database_catalog_updated_at()'], 'VERIFIED',
    'NOT_APPLICABLE', NULL, NULL, NULL,
    'Metadata only; use the underlying Feature availability contract for historical analysis.',
    'NOT_APPLICABLE', NULL
  ),
  (
    'public','AI_data_coverage','System',
    'Automated actual raw-source coverage plus explicitly inferred expectations for derived Feature tables.',
    'One row per dataset scope or dataset/entity pair', ARRAY['coverage_id'],
    'ai-data-coverage cron',
    ARRAY[
      'AI_table_catalog','Price_Stock_Indonesia_IDX','IDX_Broker_Summary',
      'IDX_Stock_Universe','IDX_Broker_Profile','Feature_Status'
    ],
    ARRAY[
      'database/migrations/20260922_001_create_ai_catalogs.sql',
      'apps/ai-data-coverage/coverage_job.py'
    ],
    'Nightly raw/control-table coverage upsert; Feature 01-03 physical tables are never scanned.',
    ARRAY['set_database_catalog_updated_at()'], 'VERIFIED',
    'NOT_APPLICABLE', NULL, NULL, 'last_checked_at',
    'Operational coverage metadata; derived Feature rows are expectations unless pipeline-confirmed.',
    'NOT_APPLICABLE', NULL
  );

INSERT INTO public."Column_Catalog" (
    table_schema, table_name, column_name, ordinal_position, data_type,
    is_nullable, default_expression, is_primary_key, definition,
    source_column_or_expression, unit, null_rule, source_code_paths,
    documentation_status
)
SELECT
    columns.table_schema,
    columns.table_name,
    columns.column_name,
    columns.ordinal_position,
    columns.data_type,
    columns.is_nullable = 'YES',
    columns.column_default,
    EXISTS (
        SELECT 1
        FROM information_schema.table_constraints AS constraints
        JOIN information_schema.key_column_usage AS keys
          ON keys.constraint_catalog = constraints.constraint_catalog
         AND keys.constraint_schema = constraints.constraint_schema
         AND keys.constraint_name = constraints.constraint_name
         AND keys.table_schema = constraints.table_schema
         AND keys.table_name = constraints.table_name
        WHERE constraints.constraint_type = 'PRIMARY KEY'
          AND constraints.table_schema = columns.table_schema
          AND constraints.table_name = columns.table_name
          AND keys.column_name = columns.column_name
    ),
    format(
        'Governed %s field of %s; see the creating migration for its exact contract.',
        columns.column_name, columns.table_name
    ),
    'database/migrations/20260922_001_create_ai_catalogs.sql',
    NULL,
    CASE WHEN columns.is_nullable = 'YES'
         THEN 'NULL means not applicable, not measured, or not yet verified as defined by the table contract.'
         ELSE 'NULL is not permitted.' END,
    ARRAY['database/migrations/20260922_001_create_ai_catalogs.sql'],
    'PARTIAL'
FROM information_schema.columns AS columns
WHERE columns.table_schema = 'public'
  AND columns.table_name IN (
      'AI_table_catalog','AI_column_catalog','AI_catalog_relationships',
      'AI_calculation_catalog','AI_data_coverage'
  );

DO $$
DECLARE
    role_name text;
BEGIN
    FOREACH role_name IN ARRAY ARRAY['market_ai_reader','market_ai_app']
    LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
            EXECUTE format(
                'GRANT SELECT ON TABLE public.%I, public.%I, public.%I, public.%I, public.%I TO %I',
                'AI_table_catalog','AI_column_catalog','AI_catalog_relationships',
                'AI_calculation_catalog','AI_data_coverage',role_name
            );
        END IF;
    END LOOP;
END;
$$;

COMMIT;
