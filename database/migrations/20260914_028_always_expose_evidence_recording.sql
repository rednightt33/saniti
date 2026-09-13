BEGIN;

UPDATE public."Tool_Catalog"
SET purpose =
        'Persist compact evidence for the current request and return the only evidence ID that may be cited in the final answer. This capability remains exposed throughout every analytical stage.',
    tool_specific_limits = tool_specific_limits || '{"final_citation_requires_recorded_id":true,"always_exposed":true}'::jsonb,
    updated_at = clock_timestamp()
WHERE tool_name = 'record_evidence';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM public."Tool_Catalog"
        WHERE tool_name = 'record_evidence'
          AND is_active
          AND tool_specific_limits->>'always_exposed' = 'true'
    ) THEN
        RAISE EXCEPTION 'record_evidence always-exposed contract was not updated';
    END IF;
END;
$$;

COMMIT;
