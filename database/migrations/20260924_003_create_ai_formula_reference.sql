-- Schema for the reviewed Calculation_Catalog sheet of AI_Calculation_Formula.xlsx.
-- The source workbook is loaded directly into PostgreSQL with scripts/import_ai_formula_reference.py;
-- no workbook records are stored in this public migration. These are documented formula
-- definitions, not verified or executable implementations.
-- Unlike the RESEARCH tools (installed inactive, activated separately per 20260924_002), the three
-- market-ai-orc catalog tools are already active, so this migration activates FORMULAS support
-- immediately in the same transaction, at the user's explicit request.
-- Forward-only migration. No market-data table, SQL Governor permission, or sandbox registry is changed.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

DO $preflight$
BEGIN
    IF to_regclass('public."AI_formula_reference"') IS NOT NULL THEN
        RAISE EXCEPTION 'AI_formula_reference already exists: inspect before applying bootstrap';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'market_ai_catalog_reader') THEN
        RAISE EXCEPTION 'market_ai_catalog_reader role is required';
    END IF;
    IF (SELECT count(*) FROM public."Tool_Catalog"
        WHERE tool_name IN ('discover_catalog', 'get_catalog_details', 'read_catalog_rows')
          AND tool_specific_limits->>'runtime_service' = 'market-ai-orc' AND is_active = true) <> 3 THEN
        RAISE EXCEPTION 'Expected three active market-ai-orc catalog tool rows before extending them';
    END IF;
END
$preflight$;

CREATE TABLE public."AI_formula_reference" (
    calculation_id text PRIMARY KEY,
    calculation_name text NOT NULL,
    description text NOT NULL,
    required_inputs text NOT NULL,
    formula_method text NOT NULL,
    parameters text NOT NULL,
    output text NOT NULL,
    implementation text NOT NULL,
    CONSTRAINT ai_formula_reference_nonempty_id CHECK (calculation_id ~ '^[A-Za-z][A-Za-z0-9_]{0,62}$')
);
COMMENT ON TABLE public."AI_formula_reference" IS
    'Reference calculation formulas for the orchestrator; documented definitions, not verified or executable implementations.';
COMMENT ON COLUMN public."AI_formula_reference".required_inputs IS
    'Semicolon-delimited logical input roles, not actual PostgreSQL column names.';
COMMENT ON COLUMN public."AI_formula_reference".formula_method IS
    'Renamed from the source workbook column "formula / method" to a valid identifier.';

-- The orchestrator catalog login inherits this role. The SQL Governor role gets no new grant.
GRANT SELECT ON public."AI_formula_reference" TO market_ai_catalog_reader;
REVOKE ALL ON public."AI_formula_reference" FROM PUBLIC;

INSERT INTO public."Table_Catalog" (
    table_schema, table_name, category, definition, grain,
    primary_key_columns, source_system, source_tables, source_code_paths,
    update_rule, related_functions, documentation_status,
    readiness_mode, readiness_date_column, observation_date_column,
    data_available_at_column, availability_rule, point_in_time_status,
    historical_metadata_method
) VALUES (
    'public', 'AI_formula_reference', 'Reference',
    'Global reference catalog of calculation formulas for the orchestrator; entries document a '
    'formula, not a verified or executable implementation.',
    'One row per calculation formula', ARRAY['calculation_id'],
    'Reviewed AI_Calculation_Formula.xlsx, Calculation_Catalog sheet',
    ARRAY[]::text[], ARRAY['database/migrations/20260924_003_create_ai_formula_reference.sql'],
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
       columns.data_type, false, columns.column_default, columns.column_name = 'calculation_id',
       CASE columns.column_name
        WHEN 'calculation_id' THEN 'Stable unique formula ID.'
        WHEN 'calculation_name' THEN 'Display name for agent and human review.'
        WHEN 'description' THEN 'What the formula computes.'
        WHEN 'required_inputs' THEN 'Semicolon-delimited logical input roles, NOT actual Postgres column names.'
        WHEN 'formula_method' THEN 'The documented formula or method text; renamed from source column "formula / method".'
        WHEN 'parameters' THEN 'Documented parameter names/defaults as free text; enforcement belongs in code.'
        WHEN 'output' THEN 'Name of the documented output value.'
        WHEN 'implementation' THEN 'Suggested implementation stack; NOT evidence of installed/registered tooling.'
       END,
       'AI_Calculation_Formula.xlsx / Calculation_Catalog', NULL, 'NULL is not permitted.',
       ARRAY['database/migrations/20260924_003_create_ai_formula_reference.sql'], 'PARTIAL'
FROM information_schema.columns AS columns
WHERE columns.table_schema = 'public' AND columns.table_name = 'AI_formula_reference';

-- Extend the three already-active market-ai-orc catalog tools with FORMULAS support.
UPDATE public."Tool_Catalog" SET
    purpose = 'List the data tables available in Saniti''s AI catalog with their descriptions, category, grain, keys, documentation status, and how much column, calculation, and relationship metadata each has, plus the global research-method and formula-reference catalog counts. Returns catalog metadata only, never data rows.',
    tool_specific_limits = '{"handler": "app/tools/catalog.py", "max_tables": 50, "visibility": "AI_* catalog flags applied", "registry_state": "Registered in market-ai-orc; is_active=true makes it available to market-ai-backend tool lists.", "runtime_commit": "cb97fac", "runtime_service": "market-ai-orc"}'::jsonb,
    updated_at = CURRENT_TIMESTAMP
WHERE tool_name = 'discover_catalog' AND tool_specific_limits->>'runtime_service' = 'market-ai-orc';

UPDATE public."Tool_Catalog" SET
    purpose = 'Retrieve catalog metadata for up to 3 tables returned by discover_catalog. COLUMNS: column meanings, types, units, and allowed aggregations. RELATIONSHIPS: documented join keys, temporal rules, and output grain. CALCULATIONS: documented calculation definitions, required inputs, alignment and missing-data rules. COVERAGE: recorded date coverage and verification status. RESEARCH: global reference methods, independent of market tables; use table_names=[] for RESEARCH only and method_ids to narrow. FORMULAS: global documented calculation formulas, independent of market tables; use table_names=[] for FORMULAS only and formula_ids to narrow; these are documented definitions, not verified or executable implementations. Large sections are summarized or truncated and say so. Returns documentation only, never observed values.',
    input_schema = '{"type": "object", "required": ["table_names", "sections", "column_names", "entity_ids", "method_ids", "formula_ids"], "properties": {"sections": {"type": "array", "items": {"enum": ["COLUMNS", "RELATIONSHIPS", "CALCULATIONS", "COVERAGE", "RESEARCH", "FORMULAS"], "type": "string"}, "description": "Metadata sections: COLUMNS, RELATIONSHIPS, CALCULATIONS, COVERAGE, RESEARCH, FORMULAS."}, "entity_ids": {"anyOf": [{"type": "array", "items": {"type": "string"}}, {"type": "null"}], "description": "Optional 1-20 exact entity identifiers such as tickers, adding per-entity rows to COVERAGE. Use null for dataset-level coverage only."}, "method_ids": {"anyOf": [{"type": "array", "items": {"type": "string"}}, {"type": "null"}], "description": "Optional 1-40 exact research method_id values; null lists all methods."}, "formula_ids": {"anyOf": [{"type": "array", "items": {"type": "string"}}, {"type": "null"}], "description": "Optional 1-40 exact formula calculation_id values; null lists all formulas."}, "table_names": {"type": "array", "items": {"type": "string"}, "description": "1-3 exact market table names, or [] for RESEARCH/FORMULAS only."}, "column_names": {"anyOf": [{"type": "array", "items": {"type": "string"}}, {"type": "null"}], "description": "Optional 1-40 exact column names that narrow COLUMNS and CALCULATIONS. Use null for all columns."}}, "additionalProperties": false}'::jsonb,
    tool_specific_limits = '{"handler": "app/tools/catalog.py", "row_caps": {"columns": 150, "research": 50, "formulas": 50, "entity_rows": 60, "calculations": 100, "relationships": 50, "status_groups": 60}, "max_entity_ids": 20, "max_method_ids": 40, "max_formula_ids": 40, "registry_state": "Registered in market-ai-orc; is_active=true makes it available to market-ai-backend tool lists.", "runtime_commit": "cb97fac", "runtime_service": "market-ai-orc", "max_column_filter": 40, "max_tables_per_call": 3, "payload_budget_bytes": 24000}'::jsonb,
    updated_at = CURRENT_TIMESTAMP
WHERE tool_name = 'get_catalog_details' AND tool_specific_limits->>'runtime_service' = 'market-ai-orc';

UPDATE public."Tool_Catalog" SET
    input_schema = '{"type": "object", "required": ["catalog_name", "page_size", "cursor"], "properties": {"cursor": {"anyOf": [{"type": "string"}, {"type": "null"}], "description": "null for the first page, or the exact next_cursor from the previous page."}, "page_size": {"anyOf": [{"type": "integer"}, {"type": "null"}], "description": "Rows per page; null for the default."}, "catalog_name": {"enum": ["AI_table_catalog", "AI_column_catalog", "AI_catalog_relationships", "AI_calculation_catalog", "AI_data_coverage", "AI_research_catalog", "AI_formula_reference"], "type": "string", "description": "One of the seven AI catalog tables."}}, "additionalProperties": false}'::jsonb,
    tool_specific_limits = '{"cursor": "HMAC-signed, catalog-bound", "handler": "app/tools/catalog_rows.py", "catalogs": ["AI_table_catalog", "AI_column_catalog", "AI_catalog_relationships", "AI_calculation_catalog", "AI_data_coverage", "AI_research_catalog", "AI_formula_reference"], "pagination": "keyset on primary key", "page_max_bytes": 16000, "registry_state": "Registered in market-ai-orc; is_active=true makes it available to market-ai-backend tool lists.", "runtime_commit": "cb97fac", "runtime_service": "market-ai-orc", "visibility_filter": "none"}'::jsonb,
    updated_at = CURRENT_TIMESTAMP
WHERE tool_name = 'read_catalog_rows' AND tool_specific_limits->>'runtime_service' = 'market-ai-orc';

DO $verify$
BEGIN
    IF (SELECT count(*) FROM information_schema.columns
           WHERE table_schema='public' AND table_name='AI_formula_reference') <> 8 THEN
        RAISE EXCEPTION 'Formula reference column count does not match reviewed workbook';
    END IF;
    IF NOT has_table_privilege('market_ai_catalog_reader', 'public."AI_formula_reference"', 'SELECT')
       OR has_table_privilege('market_ai_catalog_reader', 'public."AI_formula_reference"', 'INSERT,UPDATE,DELETE') THEN
        RAISE EXCEPTION 'market_ai_catalog_reader privileges do not match read-only contract';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='market_ai_sql_reader')
       AND has_table_privilege('market_ai_sql_reader', 'public."AI_formula_reference"', 'SELECT') THEN
        RAISE EXCEPTION 'SQL Governor unexpectedly has formula reference SELECT';
    END IF;
    IF (SELECT count(*) FROM public."Tool_Catalog"
        WHERE tool_name IN ('discover_catalog', 'get_catalog_details', 'read_catalog_rows')
          AND tool_specific_limits->>'runtime_service' = 'market-ai-orc'
          AND tool_specific_limits->>'runtime_commit' = 'cb97fac') <> 3 THEN
        RAISE EXCEPTION 'Expected three market-ai-orc catalog tool rows stamped at the deployed commit';
    END IF;
    IF NOT ((SELECT input_schema->'properties'->'catalog_name'->'enum' ? 'AI_formula_reference'
             FROM public."Tool_Catalog" WHERE tool_name = 'read_catalog_rows'
               AND tool_specific_limits->>'runtime_service' = 'market-ai-orc')) THEN
        RAISE EXCEPTION 'read_catalog_rows input_schema was not extended with AI_formula_reference';
    END IF;
END
$verify$;

COMMIT;
