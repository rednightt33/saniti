BEGIN;

UPDATE public."Tool_Catalog"
SET purpose = CASE tool_name
        WHEN 'find_features' THEN
            'Discover exact Feature identifiers using compact searchable catalog summaries. Use get_feature_definition for the complete semantic contract of selected columns.'
        WHEN 'record_evidence' THEN
            'Persist compact evidence for the current request and return the only evidence ID that may be cited in the final answer.'
        ELSE purpose
    END,
    tool_specific_limits = CASE tool_name
        WHEN 'find_features' THEN tool_specific_limits || '{"result_mode":"compact_identifier_discovery","full_semantics_tool":"get_feature_definition"}'::jsonb
        WHEN 'record_evidence' THEN tool_specific_limits || '{"final_citation_requires_recorded_id":true}'::jsonb
        ELSE tool_specific_limits
    END,
    updated_at = clock_timestamp()
WHERE tool_name IN ('find_features', 'record_evidence');

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM public."Tool_Catalog"
        WHERE tool_name = 'find_features'
          AND (
              tool_specific_limits->>'result_mode' <> 'compact_identifier_discovery'
              OR tool_specific_limits->>'full_semantics_tool' <> 'get_feature_definition'
          )
    ) OR EXISTS (
        SELECT 1
        FROM public."Tool_Catalog"
        WHERE tool_name = 'record_evidence'
          AND tool_specific_limits->>'final_citation_requires_recorded_id' <> 'true'
    ) THEN
        RAISE EXCEPTION 'Feature discovery/final evidence tool contract was not updated';
    END IF;
END;
$$;

COMMIT;
