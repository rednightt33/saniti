-- Clarify tool descriptions consumed by the model so bounded analyses avoid
-- redundant validation and incorrect abbreviated identifiers.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '5min';

UPDATE public."Tool_Catalog"
SET purpose = CASE tool_name
        WHEN 'list_feature_tables' THEN
            'List exact case-sensitive verified Feature table identifiers and grains. Copy identifiers verbatim; never abbreviate them.'
        WHEN 'find_features' THEN
            'Discover relevant Feature columns. Whitespace-separated search keywords use OR matching across column, category, definition and analytical interpretation; then load selected definitions.'
        WHEN 'validate_query_request' THEN
            'Validate one structured query without estimating or executing it. Do not call this when estimate_query_size will be called for the same payload.'
        WHEN 'estimate_query_size' THEN
            'Validate and estimate one structured query before execution. This already includes request validation; do not also call validate_query_request for the same payload.'
        WHEN 'record_evidence' THEN
            'Persist one compact decisive evidence item after a material result so final claims can cite its evidence ID.'
        ELSE purpose
    END,
    tool_specific_limits = tool_specific_limits || CASE tool_name
        WHEN 'find_features' THEN '{"search_mode":"whitespace_keywords_or","max_keywords":8}'::jsonb
        WHEN 'estimate_query_size' THEN '{"includes_request_validation":true}'::jsonb
        WHEN 'validate_query_request' THEN '{"skip_when_estimate_is_used":true}'::jsonb
        ELSE '{}'::jsonb
    END
WHERE is_active AND tool_name IN (
    'list_feature_tables','find_features','validate_query_request',
    'estimate_query_size','record_evidence'
);

UPDATE public."Table_Catalog"
SET source_code_paths = CASE
        WHEN 'database/migrations/20260914_025_clarify_market_ai_tool_workflow.sql'=ANY(source_code_paths)
            THEN source_code_paths
        ELSE array_append(source_code_paths,
            'database/migrations/20260914_025_clarify_market_ai_tool_workflow.sql')
    END
WHERE table_schema='public' AND table_name='Tool_Catalog';

DO $validate$
DECLARE bad_count integer;
BEGIN
    SELECT count(*) INTO bad_count
    FROM public."Tool_Catalog"
    WHERE is_active AND (
        (tool_name='find_features' AND tool_specific_limits->>'search_mode' <> 'whitespace_keywords_or')
        OR (tool_name='estimate_query_size' AND tool_specific_limits->>'includes_request_validation' <> 'true')
        OR (tool_name='validate_query_request' AND tool_specific_limits->>'skip_when_estimate_is_used' <> 'true')
    );
    IF bad_count <> 0 THEN
        RAISE EXCEPTION 'Tool workflow clarification failed for % active rows', bad_count;
    END IF;
END
$validate$;

COMMIT;
