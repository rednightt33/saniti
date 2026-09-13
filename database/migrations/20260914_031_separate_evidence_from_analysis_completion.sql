-- Separate durable evidence recording from the explicit stopping-policy gate.
-- This lets INSIGHT mode perform necessary follow-up analysis after recording
-- an initial result while retaining bounded, deterministic finalization.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '5min';

UPDATE public."Tool_Catalog"
SET purpose =
        'Persist one compact decisive evidence item for the current request and return the only evidence ID that may be cited. Recording evidence does not end the investigation; call complete_analysis only after necessary follow-ups are complete.',
    tool_specific_limits =
        (tool_specific_limits - 'signals_finalization') ||
        '{"final_citation_requires_recorded_id":true,"always_exposed":true,"signals_finalization":false}'::jsonb,
    updated_at = clock_timestamp()
WHERE tool_name = 'record_evidence' AND version = 'v1';

INSERT INTO public."Tool_Catalog" (
    tool_name, tool_family, tool_type, purpose, input_schema, output_schema,
    execution_type, handler_name, requires_analytics_worker,
    requires_feature_catalog, requires_data_readiness, tool_specific_limits,
    version, is_active
) VALUES (
    'complete_analysis',
    'META',
    'ORCHESTRATION',
    'Apply the explicit stopping checklist after evidence is recorded. In INSIGHT mode, necessary follow-up analysis must be complete and the configured minimum number of distinct successful analytical queries must be met before this tool can signal strict finalization.',
    '{"type":"object","additionalProperties":false,"required":["evidence_sufficient","necessary_followups_completed","completion_reason","remaining_uncertainties","optional_next_analysis"]}'::jsonb,
    '{"type":"object"}'::jsonb,
    'ORCHESTRATOR',
    'complete_analysis',
    false,
    false,
    false,
    '{"always_exposed":true,"requires_recorded_evidence":true,"signals_finalization":true,"analysis_modes":["QUICK","INSIGHT"],"insight_min_distinct_analytical_queries_variable":"AI_MIN_INSIGHT_DATA_CALLS","optional_work_must_be_deferred":true}'::jsonb,
    'v1',
    true
)
ON CONFLICT (tool_name, version) DO UPDATE
SET tool_family = EXCLUDED.tool_family,
    tool_type = EXCLUDED.tool_type,
    purpose = EXCLUDED.purpose,
    input_schema = EXCLUDED.input_schema,
    output_schema = EXCLUDED.output_schema,
    execution_type = EXCLUDED.execution_type,
    handler_name = EXCLUDED.handler_name,
    requires_analytics_worker = EXCLUDED.requires_analytics_worker,
    requires_feature_catalog = EXCLUDED.requires_feature_catalog,
    requires_data_readiness = EXCLUDED.requires_data_readiness,
    tool_specific_limits = EXCLUDED.tool_specific_limits,
    is_active = EXCLUDED.is_active,
    updated_at = clock_timestamp();

UPDATE public."Table_Catalog"
SET source_code_paths = CASE
        WHEN 'database/migrations/20260914_031_separate_evidence_from_analysis_completion.sql'=ANY(source_code_paths)
            THEN source_code_paths
        ELSE array_append(source_code_paths,
            'database/migrations/20260914_031_separate_evidence_from_analysis_completion.sql')
    END
WHERE table_schema='public' AND table_name='Tool_Catalog';

DO $validate$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public."Tool_Catalog"
        WHERE tool_name='record_evidence' AND version='v1' AND is_active
          AND tool_specific_limits->>'signals_finalization'='false'
    ) THEN
        RAISE EXCEPTION 'record_evidence remains a finalization signal';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public."Tool_Catalog"
        WHERE tool_name='complete_analysis' AND version='v1' AND is_active
          AND execution_type='ORCHESTRATOR'
          AND tool_specific_limits->>'signals_finalization'='true'
          AND tool_specific_limits->>'requires_recorded_evidence'='true'
    ) THEN
        RAISE EXCEPTION 'complete_analysis stopping-policy contract is incomplete';
    END IF;
END
$validate$;

COMMIT;
