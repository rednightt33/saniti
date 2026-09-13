BEGIN;

UPDATE public."Tool_Catalog"
SET purpose =
        'Persist compact evidence only after the current answer has sufficient support. Required fields are evidence_type, claim, compact_payload_json, and source_tables; malformed calls return a recoverable validation error. A successful call returns the only evidence ID that may be cited and signals strict finalization.',
    tool_specific_limits = tool_specific_limits ||
        '{"backend_required_fields":["evidence_type","claim","compact_payload_json","source_tables"],"malformed_request_recoverable":true}'::jsonb,
    updated_at = clock_timestamp()
WHERE tool_name = 'record_evidence';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM public."Tool_Catalog"
        WHERE tool_name = 'record_evidence'
          AND tool_specific_limits->>'malformed_request_recoverable' = 'true'
          AND tool_specific_limits->'backend_required_fields' ?&
              ARRAY['evidence_type','claim','compact_payload_json','source_tables']
    ) THEN
        RAISE EXCEPTION 'record_evidence backend validation contract was not documented';
    END IF;
END;
$$;

COMMIT;
