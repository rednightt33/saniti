BEGIN;

UPDATE public."Tool_Catalog"
SET purpose =
        'Persist compact evidence only after the current answer has sufficient support. Return the only evidence ID that may be cited in the final answer and signal that the next model call must finalize without data tools.',
    tool_specific_limits = tool_specific_limits || '{"final_citation_requires_recorded_id":true,"always_exposed":true,"signals_finalization":true}'::jsonb,
    updated_at = clock_timestamp()
WHERE tool_name = 'record_evidence';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM public."Tool_Catalog"
        WHERE tool_name = 'record_evidence'
          AND is_active
          AND tool_specific_limits->>'signals_finalization' = 'true'
    ) THEN
        RAISE EXCEPTION 'record_evidence finalization transition was not documented';
    END IF;
END;
$$;

COMMIT;
