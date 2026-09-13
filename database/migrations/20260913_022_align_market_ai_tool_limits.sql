-- Align Tool_Catalog's advertised Release 1B ceilings with the configurable
-- enforcement defaults used by market-ai-backend. Metadata remains non-authoritative.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '5min';

DO $preflight$
BEGIN
    IF (SELECT count(*) FROM public."Golden_Analysis_Test"
        WHERE is_active AND version='v1' AND test_id LIKE 'R1B_%') <> 15 THEN
        RAISE EXCEPTION 'Release 1B golden definitions are required';
    END IF;
END
$preflight$;

UPDATE public."Tool_Catalog"
SET default_output_rows = 500,
    max_output_rows = 5000,
    max_tickers = 20,
    max_date_range_days = 1825,
    max_estimated_rows = 100000,
    timeout_seconds = 15,
    max_output_bytes = 1048576,
    max_llm_result_rows = 200,
    max_llm_result_bytes = 131072,
    max_llm_result_tokens = 4000,
    tool_specific_limits = tool_specific_limits || jsonb_build_object(
        'query_max_columns',20,
        'query_max_unfiltered_date_range_days',31,
        'query_max_groups',1000,
        'enforcement_authority','Railway variables plus market-ai-backend validation'
    )
WHERE is_active AND tool_family IN ('QUERY','SCREENING');

UPDATE public."Tool_Catalog"
SET max_tickers = 20,
    max_date_range_days = 1825,
    max_estimated_rows = 100000,
    timeout_seconds = 15,
    max_output_bytes = 1048576,
    max_llm_result_rows = 200,
    max_llm_result_bytes = 131072,
    max_llm_result_tokens = 4000,
    tool_specific_limits = tool_specific_limits || jsonb_build_object(
        'query_max_columns',20,
        'enforcement_authority','Railway variables plus market-ai-backend validation'
    )
WHERE is_active AND tool_name IN ('check_data_quality','get_feature_definition','find_features');

UPDATE public."Tool_Catalog"
SET max_llm_result_rows = 200,
    max_llm_result_bytes = 131072,
    max_llm_result_tokens = 4000,
    tool_specific_limits = tool_specific_limits || jsonb_build_object(
        'enforcement_authority','Railway variables plus market-ai-backend validation'
    )
WHERE is_active;

UPDATE public."Table_Catalog"
SET source_code_paths = CASE
        WHEN 'database/migrations/20260913_022_align_market_ai_tool_limits.sql'=ANY(source_code_paths)
            THEN source_code_paths
        ELSE array_append(source_code_paths,'database/migrations/20260913_022_align_market_ai_tool_limits.sql')
    END
WHERE table_name='Tool_Catalog';

DO $validate$
DECLARE mismatch_count integer;
BEGIN
    SELECT count(*) INTO mismatch_count
    FROM public."Tool_Catalog"
    WHERE is_active AND tool_family IN ('QUERY','SCREENING')
      AND (default_output_rows <> 500 OR max_output_rows <> 5000
           OR max_tickers <> 20 OR max_date_range_days <> 1825
           OR max_estimated_rows <> 100000 OR timeout_seconds <> 15
           OR max_output_bytes <> 1048576 OR max_llm_result_rows <> 200
           OR max_llm_result_bytes <> 131072 OR max_llm_result_tokens <> 4000);
    IF mismatch_count <> 0 THEN
        RAISE EXCEPTION 'Tool limit alignment mismatch: %',mismatch_count;
    END IF;
END
$validate$;

COMMIT;
