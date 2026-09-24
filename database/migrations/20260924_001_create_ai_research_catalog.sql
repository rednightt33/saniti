-- Schema for the reviewed AI_Research_Catalog sheet of Saniti_DB_AI_Research_Catalog.xlsx.
-- The source workbook is loaded directly into PostgreSQL with scripts/import_ai_research_catalog.py;
-- no workbook records are stored in this public migration. REFERENCE_ONLY is documentation, not execution.
-- Forward-only migration. No market-data table, SQL Governor permission, or sandbox registry is changed.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

DO $preflight$
BEGIN
    IF to_regclass('public."AI_research_catalog"') IS NOT NULL THEN
        RAISE EXCEPTION 'AI_research_catalog already exists: inspect before applying bootstrap';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'market_ai_catalog_reader') THEN
        RAISE EXCEPTION 'market_ai_catalog_reader role is required';
    END IF;
END
$preflight$;

CREATE TABLE public."AI_research_catalog" (
    method_id text PRIMARY KEY,
    method_name text NOT NULL,
    category text NOT NULL,
    purpose text NOT NULL,
    example_question text NOT NULL,
    analysis_kind text NOT NULL,
    input_grain text NOT NULL,
    required_inputs_json jsonb NOT NULL,
    optional_inputs_json jsonb NOT NULL,
    future_outcome_required boolean NOT NULL,
    supports_numeric_directly boolean NOT NULL,
    preprocessing text NOT NULL,
    parameter_keys_json jsonb NOT NULL,
    expected_outputs_json jsonb NOT NULL,
    validation_requirements_json jsonb NOT NULL,
    main_risks text NOT NULL,
    compute_strategy text NOT NULL,
    tool_or_library_examples text NOT NULL,
    implementation_status text NOT NULL,
    CONSTRAINT ai_research_json_arrays CHECK (
        jsonb_typeof(required_inputs_json) = 'array'
        AND jsonb_typeof(optional_inputs_json) = 'array'
        AND jsonb_typeof(parameter_keys_json) = 'array'
        AND jsonb_typeof(expected_outputs_json) = 'array'
        AND jsonb_typeof(validation_requirements_json) = 'array'
    ),
    CONSTRAINT ai_research_nonempty_id CHECK (method_id ~ '^[A-Za-z][A-Za-z0-9_]{0,62}$'),
    CONSTRAINT ai_research_nonempty_status CHECK (length(trim(implementation_status)) > 0)
);
COMMENT ON TABLE public."AI_research_catalog" IS
    'Reference methods for the orchestrator; REFERENCE_ONLY does not imply installed sandbox code or validation.';
COMMENT ON COLUMN public."AI_research_catalog".required_inputs_json IS
    'Logical input roles, not PostgreSQL table or column identifiers.';

-- The orchestrator catalog login inherits this role. The SQL Governor role gets no new grant.
GRANT SELECT ON public."AI_research_catalog" TO market_ai_catalog_reader;
REVOKE ALL ON public."AI_research_catalog" FROM PUBLIC;

INSERT INTO public."Table_Catalog" (
    table_schema, table_name, category, definition, grain,
    primary_key_columns, source_system, source_tables, source_code_paths,
    update_rule, related_functions, documentation_status,
    readiness_mode, readiness_date_column, observation_date_column,
    data_available_at_column, availability_rule, point_in_time_status,
    historical_metadata_method
) VALUES (
    'public', 'AI_research_catalog', 'Reference',
    'Global reference catalog of research methods for the orchestrator; entries do not enable sandbox execution.',
    'One row per research method', ARRAY['method_id'],
    'Reviewed Saniti_DB_AI_Research_Catalog.xlsx, AI_Research_Catalog sheet',
    ARRAY[]::text[], ARRAY['database/migrations/20260924_001_create_ai_research_catalog.sql'],
    'Controlled migration and separately audited workbook import.',
    ARRAY[]::text[], 'PARTIAL', 'NOT_APPLICABLE', NULL, NULL, NULL,
    'Metadata only; check sandbox registry and execution validation separately.',
    'NOT_APPLICABLE', NULL
);

INSERT INTO public."Column_Catalog" (
    table_schema, table_name, column_name, ordinal_position, data_type,
    is_nullable, default_expression, is_primary_key, definition,
    source_column_or_expression, unit, null_rule, source_code_paths,
    documentation_status
)
SELECT columns.table_schema, columns.table_name, columns.column_name, columns.ordinal_position,
       columns.data_type, false, columns.column_default, columns.column_name = 'method_id',
       CASE columns.column_name
        WHEN 'method_id' THEN 'Stable unique method ID.'
        WHEN 'method_name' THEN 'Display name for agent and human review.'
        WHEN 'category' THEN 'Broad method family.'
        WHEN 'purpose' THEN 'Method objective, not proof of enabled tooling.'
        WHEN 'example_question' THEN 'Illustrative natural-language request.'
        WHEN 'analysis_kind' THEN 'Evidence type: descriptive, exploratory, conditional_outcome or inference.'
        WHEN 'input_grain' THEN 'Observation granularity required by analysis.'
        WHEN 'required_inputs_json' THEN 'JSON array of logical input roles, NOT actual Postgres column names.'
        WHEN 'optional_inputs_json' THEN 'JSON array of additional logical input roles.'
        WHEN 'future_outcome_required' THEN 'True if a forward or outcome variable is part of this method.'
        WHEN 'supports_numeric_directly' THEN 'False if categorical/binary encoding is required.'
        WHEN 'preprocessing' THEN 'Preparation, time alignment and signal availability requirements.'
        WHEN 'parameter_keys_json' THEN 'JSON array of unresolved analysis parameter names; no silently imposed numeric defaults.'
        WHEN 'expected_outputs_json' THEN 'JSON array of expected result field names.'
        WHEN 'validation_requirements_json' THEN 'JSON array of method-specific checks; enforcement belongs in code.'
        WHEN 'main_risks' THEN 'Likely data, model or interpretation failure modes.'
        WHEN 'compute_strategy' THEN 'Execution hint, not a resource guarantee.'
        WHEN 'tool_or_library_examples' THEN 'Potential libraries; NOT evidence of installed/registered tools.'
        WHEN 'implementation_status' THEN 'REFERENCE_ONLY until developer implements, tests and registers a usable tool.'
       END,
       'Saniti_DB_AI_Research_Catalog.xlsx / Field_Dictionary', NULL, 'NULL is not permitted.',
       ARRAY['database/migrations/20260924_001_create_ai_research_catalog.sql'], 'PARTIAL'
FROM information_schema.columns AS columns
WHERE columns.table_schema = 'public' AND columns.table_name = 'AI_research_catalog';

-- Tool_Catalog rows document the orchestrator registry; they stay inactive for market-ai-backend.
DO $tool_preflight$
BEGIN
    IF (SELECT count(*) FROM public."Tool_Catalog"
        WHERE tool_name IN ('discover_catalog', 'get_catalog_details', 'read_catalog_rows')
          AND tool_specific_limits->>'runtime_service' = 'market-ai-orc' AND is_active = false) <> 3 THEN
        RAISE EXCEPTION 'Expected three inactive market-ai-orc catalog tool metadata rows';
    END IF;
END
$tool_preflight$;

UPDATE public."Tool_Catalog" SET purpose = 'List the data tables available in Saniti''s AI catalog with their descriptions, category, grain, keys, documentation status, and how much column, calculation, and relationship metadata each has, plus the global research-method catalog count. Returns catalog metadata only, never data rows.',
    input_schema = '{"type":"object","properties":{},"required":[],"additionalProperties":false}'::jsonb,
    output_schema = jsonb_set(output_schema, '{properties,research_catalog}', '{}'::jsonb, true),
    updated_at = CURRENT_TIMESTAMP
WHERE tool_name = 'discover_catalog' AND tool_specific_limits->>'runtime_service' = 'market-ai-orc'
  AND is_active = false;

UPDATE public."Tool_Catalog" SET purpose = 'Retrieve catalog metadata for up to 3 tables returned by discover_catalog. COLUMNS: column meanings, types, units, and allowed aggregations. RELATIONSHIPS: documented join keys, temporal rules, and output grain. CALCULATIONS: documented calculation definitions, required inputs, alignment and missing-data rules. COVERAGE: recorded date coverage and verification status. RESEARCH: global reference methods, independent of market tables; use table_names=[] for RESEARCH only and method_ids to narrow. Large sections are summarized or truncated and say so. Returns documentation only, never observed values.',
    input_schema = '{"type":"object","properties":{"table_names":{"description":"1-3 exact market table names, or [] for RESEARCH only.","items":{"type":"string"},"type":"array"},"sections":{"description":"Metadata sections: COLUMNS, RELATIONSHIPS, CALCULATIONS, COVERAGE, RESEARCH.","items":{"enum":["COLUMNS","RELATIONSHIPS","CALCULATIONS","COVERAGE","RESEARCH"],"type":"string"},"type":"array"},"column_names":{"anyOf":[{"items":{"type":"string"},"type":"array"},{"type":"null"}],"description":"Optional 1-40 exact column names that narrow COLUMNS and CALCULATIONS. Use null for all columns."},"entity_ids":{"anyOf":[{"items":{"type":"string"},"type":"array"},{"type":"null"}],"description":"Optional 1-20 exact entity identifiers such as tickers, adding per-entity rows to COVERAGE. Use null for dataset-level coverage only."},"method_ids":{"anyOf":[{"items":{"type":"string"},"type":"array"},{"type":"null"}],"description":"Optional 1-40 exact research method_id values; null lists all methods."}},"required":["table_names","sections","column_names","entity_ids","method_ids"],"additionalProperties":false}'::jsonb,
    tool_specific_limits = jsonb_set(tool_specific_limits, '{row_caps,research}', '50'::jsonb, true),
    updated_at = CURRENT_TIMESTAMP
WHERE tool_name = 'get_catalog_details' AND tool_specific_limits->>'runtime_service' = 'market-ai-orc'
  AND is_active = false;

UPDATE public."Tool_Catalog" SET purpose = 'Read the complete records of one AI catalog table (every column and row, in primary-key order), one page at a time. Default page_size 100, maximum 200; a page can end earlier to stay within the output limit. Continue with next_cursor while has_more is true. Returns catalog documentation, not market data.',
    input_schema = '{"type":"object","properties":{"catalog_name":{"description":"One of the six AI catalog tables.","enum":["AI_table_catalog","AI_column_catalog","AI_catalog_relationships","AI_calculation_catalog","AI_data_coverage","AI_research_catalog"],"type":"string"},"page_size":{"anyOf":[{"type":"integer"},{"type":"null"}],"description":"Rows per page; null for the default."},"cursor":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"null for the first page, or the exact next_cursor from the previous page."}},"required":["catalog_name","page_size","cursor"],"additionalProperties":false}'::jsonb,
    tool_specific_limits = jsonb_set(tool_specific_limits, '{catalogs}', (tool_specific_limits->'catalogs') || '["AI_research_catalog"]'::jsonb, false),
    updated_at = CURRENT_TIMESTAMP
WHERE tool_name = 'read_catalog_rows' AND tool_specific_limits->>'runtime_service' = 'market-ai-orc'
  AND is_active = false;

DO $verify$
BEGIN
    IF (SELECT count(*) FROM information_schema.columns
           WHERE table_schema='public' AND table_name='AI_research_catalog') <> 19 THEN
        RAISE EXCEPTION 'Research catalog column count does not match reviewed workbook';
    END IF;
    IF NOT has_table_privilege('market_ai_catalog_reader', 'public."AI_research_catalog"', 'SELECT')
       OR has_table_privilege('market_ai_catalog_reader', 'public."AI_research_catalog"', 'INSERT,UPDATE,DELETE') THEN
        RAISE EXCEPTION 'market_ai_catalog_reader privileges do not match read-only contract';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='market_ai_sql_reader')
       AND has_table_privilege('market_ai_sql_reader', 'public."AI_research_catalog"', 'SELECT') THEN
        RAISE EXCEPTION 'SQL Governor unexpectedly has research catalog SELECT';
    END IF;
END
$verify$;
COMMIT;
