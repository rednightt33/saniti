-- Register bounded, catalog-driven consecutive-observation screening.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

DO $preflight$
BEGIN
    IF to_regclass('public."Tool_Catalog"') IS NULL THEN
        RAISE EXCEPTION 'Tool_Catalog is required';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public."Tool_Catalog"
        WHERE tool_name = 'find_condition_runs' AND version = 'v1'
    ) THEN
        RAISE EXCEPTION 'find_condition_runs v1 is already registered';
    END IF;
END
$preflight$;

INSERT INTO public."Tool_Catalog" (
    tool_name, tool_family, tool_type, purpose, input_schema, output_schema,
    execution_type, handler_name, default_output_rows, max_output_rows,
    max_input_rows, max_tickers, max_date_range_days, max_estimated_rows,
    timeout_seconds, max_output_bytes, max_llm_result_rows,
    max_llm_result_bytes, max_llm_result_tokens, requires_analytics_worker,
    requires_feature_catalog, requires_data_readiness, tool_specific_limits,
    version, is_active
) VALUES (
    'find_condition_runs',
    'SCREENING',
    'PATTERN_DETECTION',
    'Find episodes where one or more catalog-approved conditions are true for consecutive trading observations. Conditions use AND semantics; NULL breaks a run. Return compact episode boundaries and optionally exact matching dates without sending the full source time series to the model.',
    '{
      "type":"object",
      "required":["table","tickers","start_date","end_date","conditions","minimum_consecutive_observations","include_matching_dates","order","max_episodes"],
      "properties":{
        "table":{"type":"string"},
        "tickers":{"type":"array","items":{"type":"string"}},
        "start_date":{"type":"string","format":"date"},
        "end_date":{"type":"string","format":"date"},
        "conditions":{"type":"array","items":{"type":"object"}},
        "minimum_consecutive_observations":{"type":"integer","minimum":2},
        "include_matching_dates":{"type":"boolean"},
        "order":{"enum":["start_date_asc","start_date_desc","longest"]},
        "max_episodes":{"type":["integer","null"]}
      }
    }'::jsonb,
    '{
      "type":"object",
      "description":"Episode rows contain ticker, start_date, end_date, observation_count, and optional matching_dates; metadata includes the query hash and trading-observation/null semantics."
    }'::jsonb,
    'BACKEND',
    'find_condition_runs',
    50,
    200,
    100000,
    20,
    7305,
    100000,
    15,
    1048576,
    200,
    131072,
    4000,
    false,
    true,
    true,
    '{
      "condition_join":"AND",
      "consecutive_unit":"trading_observations",
      "calendar_gaps_do_not_break_run":true,
      "null_breaks_run":true,
      "default_max_episodes":50,
      "configurable_limits":["CONDITION_RUNS_MAX_DATE_RANGE_DAYS","CONDITION_RUNS_MAX_EPISODES","QUERY_MAX_TICKERS","QUERY_MAX_ESTIMATED_ROWS","QUERY_TIMEOUT_SECONDS"],
      "predictive_claim_allowed":false,
      "full_source_rows_exposed_to_llm":false
    }'::jsonb,
    'v1',
    true
);

INSERT INTO public."Golden_Analysis_Test" (
    test_id, version, category, question, required_capabilities,
    fixed_start_date, fixed_end_date, expected_features, expected_tools,
    expected_conditions, expected_status
) VALUES (
    'R1B_016_CONDITION_RUNS',
    'v1',
    'RETRIEVAL',
    'List episodes where BBCA return_1d_pct was positive for at least seven consecutive trading observations during August 2026.',
    ARRAY['bounded consecutive-observation screening'],
    DATE '2026-08-01',
    DATE '2026-08-31',
    ARRAY['Feature_01_Stock_Daily.return_1d_pct'],
    ARRAY['find_condition_runs'],
    '{"consecutive_unit":"trading_observations","minimum":7,"condition":"return_1d_pct > 0"}'::jsonb,
    'SUCCESS'
);

UPDATE public."Table_Catalog"
SET related_functions = array_append(related_functions, 'backend:find_condition_runs(v1)'),
    source_code_paths = array_append(source_code_paths, 'apps/market-ai-backend/app/tools.py'),
    updated_at = CURRENT_TIMESTAMP
WHERE table_schema = 'public'
  AND table_name = 'Tool_Catalog'
  AND NOT ('backend:find_condition_runs(v1)' = ANY(related_functions));

UPDATE public."Column_Catalog"
SET source_code_paths = array_append(source_code_paths, 'database/migrations/20260914_033_register_find_condition_runs.sql'),
    updated_at = CURRENT_TIMESTAMP
WHERE table_schema = 'public'
  AND table_name IN ('Tool_Catalog', 'Golden_Analysis_Test')
  AND NOT ('database/migrations/20260914_033_register_find_condition_runs.sql' = ANY(source_code_paths));

DO $validate$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public."Tool_Catalog"
        WHERE tool_name = 'find_condition_runs' AND version = 'v1'
          AND is_active AND execution_type = 'BACKEND'
          AND requires_analytics_worker = false
          AND tool_specific_limits->>'consecutive_unit' = 'trading_observations'
          AND (tool_specific_limits->>'null_breaks_run')::boolean
    ) THEN
        RAISE EXCEPTION 'find_condition_runs catalog contract is incomplete';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public."Golden_Analysis_Test"
        WHERE test_id = 'R1B_016_CONDITION_RUNS' AND version = 'v1' AND is_active
    ) THEN
        RAISE EXCEPTION 'Condition-run golden test is missing';
    END IF;
END
$validate$;

COMMIT;
