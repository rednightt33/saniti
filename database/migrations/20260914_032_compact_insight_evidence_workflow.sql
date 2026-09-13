-- Reduce avoidable model iterations by documenting consolidated evidence and
-- the explicit transition to complete_analysis.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '5min';

UPDATE public."Tool_Catalog"
SET purpose =
        'Persist compact decisive evidence without ending the investigation. After necessary follow-ups, prefer one consolidated evidence item containing the material observations, quality result, and query hashes; use separate items only for genuinely independent claims. Then call complete_analysis.',
    tool_specific_limits = tool_specific_limits ||
        '{"prefer_consolidated_evidence":true,"returns_completion_policy_hint":true}'::jsonb,
    updated_at = clock_timestamp()
WHERE tool_name='record_evidence' AND version='v1' AND is_active;

UPDATE public."Table_Catalog"
SET source_code_paths = CASE
        WHEN 'database/migrations/20260914_032_compact_insight_evidence_workflow.sql'=ANY(source_code_paths)
            THEN source_code_paths
        ELSE array_append(source_code_paths,
            'database/migrations/20260914_032_compact_insight_evidence_workflow.sql')
    END
WHERE table_schema='public' AND table_name='Tool_Catalog';

DO $validate$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public."Tool_Catalog"
        WHERE tool_name='record_evidence' AND version='v1' AND is_active
          AND tool_specific_limits->>'prefer_consolidated_evidence'='true'
          AND tool_specific_limits->>'returns_completion_policy_hint'='true'
    ) THEN
        RAISE EXCEPTION 'record_evidence compact workflow metadata was not updated';
    END IF;
END
$validate$;

COMMIT;
