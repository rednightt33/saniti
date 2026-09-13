BEGIN;

UPDATE public."Tool_Catalog"
SET purpose = CASE tool_name
        WHEN 'query_features' THEN
            'Execute a catalog-validated bounded Feature query. The handler enforces request and size limits itself; an obviously bounded single-ticker/single-date query does not need a separate estimate call.'
        WHEN 'estimate_query_size' THEN
            'Validate and estimate a structured query when row cost is genuinely uncertain. Do not call before an obviously bounded single-ticker/single-date query, and do not also call validate_query_request for the same payload.'
        WHEN 'list_tools' THEN
            'Expose only additional tool families justified by the current analytical need. Ordinary Feature retrieval needs QUERY/SCREENING, not ADVANCED.'
        ELSE purpose
    END,
    tool_specific_limits = CASE tool_name
        WHEN 'query_features' THEN tool_specific_limits || '{"includes_request_validation":true,"estimate_optional_for_obviously_bounded_query":true}'::jsonb
        WHEN 'estimate_query_size' THEN tool_specific_limits || '{"skip_for_obviously_bounded_query":true}'::jsonb
        WHEN 'list_tools' THEN tool_specific_limits || '{"minimum_necessary_family_only":true}'::jsonb
        ELSE tool_specific_limits
    END,
    updated_at = clock_timestamp()
WHERE tool_name IN ('query_features', 'estimate_query_size', 'list_tools');

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM public."Tool_Catalog"
        WHERE tool_name = 'query_features'
          AND tool_specific_limits->>'estimate_optional_for_obviously_bounded_query' <> 'true'
    ) OR EXISTS (
        SELECT 1
        FROM public."Tool_Catalog"
        WHERE tool_name = 'estimate_query_size'
          AND tool_specific_limits->>'skip_for_obviously_bounded_query' <> 'true'
    ) OR EXISTS (
        SELECT 1
        FROM public."Tool_Catalog"
        WHERE tool_name = 'list_tools'
          AND tool_specific_limits->>'minimum_necessary_family_only' <> 'true'
    ) THEN
        RAISE EXCEPTION 'Bounded retrieval routing contract was not updated';
    END IF;
END;
$$;

COMMIT;
