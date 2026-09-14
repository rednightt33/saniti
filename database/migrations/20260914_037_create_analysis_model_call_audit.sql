-- Add one durable audit row per provider model call and document the global
-- conditional-QC / compact-semantics orchestration policy.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '5min';

DO $preflight$
BEGIN
    IF to_regclass('public."Analysis_Request"') IS NULL
       OR to_regclass('public."Tool_Catalog"') IS NULL THEN
        RAISE EXCEPTION 'Market AI foundation is required';
    END IF;
    IF to_regclass('public."Analysis_Model_Call"') IS NOT NULL THEN
        RAISE EXCEPTION 'Analysis_Model_Call already exists';
    END IF;
END
$preflight$;

CREATE TABLE public."Analysis_Model_Call" (
    model_call_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id uuid NOT NULL
        REFERENCES public."Analysis_Request" (request_id) ON DELETE CASCADE,
    iteration_number integer NOT NULL,
    provider text NOT NULL,
    model text NOT NULL,
    reasoning_effort text NOT NULL,
    stage text NOT NULL,
    exposed_tool_families text[] NOT NULL DEFAULT '{}',
    provider_response_id text,
    decision_summary text,
    decision_summary_source text NOT NULL,
    reasoning_format text NOT NULL DEFAULT 'NONE',
    reasoning_details jsonb NOT NULL DEFAULT '[]'::jsonb,
    input_tokens integer NOT NULL DEFAULT 0,
    output_tokens integer NOT NULL DEFAULT 0,
    reasoning_tokens integer NOT NULL DEFAULT 0,
    active_context_tokens integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reasoning_expires_at timestamptz NOT NULL,
    reasoning_purged_at timestamptz,
    CONSTRAINT "Analysis_Model_Call_request_iteration_key"
        UNIQUE (request_id, iteration_number),
    CONSTRAINT "Analysis_Model_Call_iteration_check"
        CHECK (iteration_number > 0),
    CONSTRAINT "Analysis_Model_Call_provider_check"
        CHECK (provider IN ('openai','openrouter')),
    CONSTRAINT "Analysis_Model_Call_stage_check"
        CHECK (stage IN ('DISCOVERY','SCREENING','HISTORICAL_VALIDATION','ADVANCED','FINAL')),
    CONSTRAINT "Analysis_Model_Call_decision_source_check"
        CHECK (decision_summary_source IN ('PROVIDER_REASONING','DERIVED_ACTION')),
    CONSTRAINT "Analysis_Model_Call_reasoning_format_check"
        CHECK (reasoning_format IN ('NONE','TEXT','SUMMARY','ENCRYPTED','MIXED','PURGED')),
    CONSTRAINT "Analysis_Model_Call_reasoning_array_check"
        CHECK (jsonb_typeof(reasoning_details) = 'array'),
    CONSTRAINT "Analysis_Model_Call_token_counts_check"
        CHECK (input_tokens >= 0 AND output_tokens >= 0 AND reasoning_tokens >= 0
               AND active_context_tokens >= 0),
    CONSTRAINT "Analysis_Model_Call_retention_check"
        CHECK (reasoning_expires_at >= created_at
               AND (reasoning_purged_at IS NULL OR reasoning_purged_at >= created_at))
);

CREATE INDEX "Analysis_Model_Call_retention_idx"
    ON public."Analysis_Model_Call" (reasoning_expires_at)
    WHERE reasoning_format NOT IN ('NONE','PURGED');

COMMENT ON TABLE public."Analysis_Model_Call" IS
    'One durable audit row per provider model call. Provider-returned reasoning is retained temporarily; concise decision summary and usage remain for long-term audit.';
COMMENT ON COLUMN public."Analysis_Model_Call".model_call_id IS 'Generated model-call audit identifier.';
COMMENT ON COLUMN public."Analysis_Model_Call".request_id IS 'Analysis request that caused this provider call.';
COMMENT ON COLUMN public."Analysis_Model_Call".iteration_number IS 'One-based provider-call number within the analysis request.';
COMMENT ON COLUMN public."Analysis_Model_Call".provider IS 'Allowlisted provider selected by runtime configuration.';
COMMENT ON COLUMN public."Analysis_Model_Call".model IS 'Exact configured provider model identifier.';
COMMENT ON COLUMN public."Analysis_Model_Call".reasoning_effort IS 'Configured reasoning effort sent to the provider.';
COMMENT ON COLUMN public."Analysis_Model_Call".stage IS 'Progressive analytical stage active for this call.';
COMMENT ON COLUMN public."Analysis_Model_Call".exposed_tool_families IS 'Tool families exposed to this specific model call.';
COMMENT ON COLUMN public."Analysis_Model_Call".provider_response_id IS 'Provider response identifier when returned.';
COMMENT ON COLUMN public."Analysis_Model_Call".decision_summary IS 'Concise provider reasoning summary when supplied; otherwise a deterministic summary of the requested tool or final-answer action.';
COMMENT ON COLUMN public."Analysis_Model_Call".decision_summary_source IS 'PROVIDER_REASONING or DERIVED_ACTION; never an invented chain-of-thought reconstruction.';
COMMENT ON COLUMN public."Analysis_Model_Call".reasoning_format IS 'NONE, TEXT, SUMMARY, ENCRYPTED, MIXED, or PURGED representation actually stored.';
COMMENT ON COLUMN public."Analysis_Model_Call".reasoning_details IS 'Bounded provider-returned reasoning blocks only; prompts and tool results are not copied here and expired details are replaced by an empty array.';
COMMENT ON COLUMN public."Analysis_Model_Call".input_tokens IS 'Provider-reported input tokens for this one call.';
COMMENT ON COLUMN public."Analysis_Model_Call".output_tokens IS 'Provider-reported output tokens for this one call.';
COMMENT ON COLUMN public."Analysis_Model_Call".reasoning_tokens IS 'Provider-reported reasoning-token subset when available; zero means unavailable or zero, not an estimate.';
COMMENT ON COLUMN public."Analysis_Model_Call".active_context_tokens IS 'Backend estimate of active instructions, input items, and tool schemas for this call.';
COMMENT ON COLUMN public."Analysis_Model_Call".created_at IS 'UTC database timestamp when the audit row was written.';
COMMENT ON COLUMN public."Analysis_Model_Call".reasoning_expires_at IS 'UTC deadline after which raw provider-returned reasoning is purged.';
COMMENT ON COLUMN public."Analysis_Model_Call".reasoning_purged_at IS 'UTC timestamp when reasoning_details was cleared; NULL while retained or absent.';

GRANT SELECT, INSERT, UPDATE ON public."Analysis_Model_Call" TO market_ai_logger;
GRANT USAGE, SELECT ON SEQUENCE public."Analysis_Model_Call_model_call_id_seq"
    TO market_ai_logger;

INSERT INTO public."Table_Catalog" (
    table_name, category, definition, grain, primary_key_columns,
    source_system, source_tables, source_code_paths, update_rule,
    related_functions, documentation_status, readiness_mode,
    availability_rule, point_in_time_status
) VALUES (
    'Analysis_Model_Call', 'System',
    'Per-provider-call audit containing usage, progressive tool exposure, a concise decision summary, and temporarily retained provider-returned reasoning.',
    'One row per Analysis_Request and model-call iteration',
    ARRAY['model_call_id'], 'market-ai-backend', ARRAY['Analysis_Request'],
    ARRAY['database/migrations/20260914_037_create_analysis_model_call_audit.sql',
          'apps/market-ai-backend/app/orchestrator.py',
          'apps/market-ai-backend/app/openai_client.py'],
    'Inserted after every provider response; expired reasoning_details are cleared opportunistically while the audit row and decision summary remain.',
    ARRAY['backend:purge_expired_reasoning_details(v1)'],
    'VERIFIED', 'NOT_APPLICABLE', 'Not applicable; this is an operational audit table.',
    'NOT_APPLICABLE'
);

INSERT INTO public."Column_Catalog" (
    table_schema, table_name, column_name, ordinal_position, data_type,
    is_nullable, default_expression, is_primary_key, definition,
    source_column_or_expression, unit, null_rule, source_code_paths,
    documentation_status
)
SELECT c.table_schema, c.table_name, c.column_name, c.ordinal_position,
       c.data_type, c.is_nullable = 'YES', c.column_default,
       c.column_name = 'model_call_id',
       pg_catalog.col_description(pc.oid, pa.attnum),
       'Written from the exact provider response or deterministic orchestrator state; defined by migration 037.',
       CASE WHEN c.column_name LIKE '%tokens' THEN 'Tokens' ELSE NULL END,
       CASE WHEN c.is_nullable = 'NO' THEN 'Never NULL.'
            ELSE 'NULL when the provider does not supply this value or the lifecycle event has not occurred.' END,
       ARRAY['database/migrations/20260914_037_create_analysis_model_call_audit.sql',
             'apps/market-ai-backend/app/orchestrator.py',
             'apps/market-ai-backend/app/openai_client.py'],
       'VERIFIED'
FROM information_schema.columns c
JOIN pg_catalog.pg_class pc
  ON pc.oid = format('%I.%I', c.table_schema, c.table_name)::regclass
JOIN pg_catalog.pg_attribute pa
  ON pa.attrelid = pc.oid AND pa.attname = c.column_name
WHERE c.table_schema='public' AND c.table_name='Analysis_Model_Call';

UPDATE public."Tool_Catalog"
SET purpose =
        'Run a scoped quality check only when missing coverage, NULL/gap concerns, stale or cross-feature state, anomaly validation, or material conclusion risk justifies it. FAIL blocks the affected conclusion; WARNING and source-valid PASS anomalies continue analysis.',
    tool_specific_limits = tool_specific_limits ||
        '{"conditional_execution":true,"full_period_scan_by_default":false,"warning_continues_analysis":true,"valid_anomaly_continues_analysis":true,"invalid_fail_blocks_affected_conclusion":true}'::jsonb,
    updated_at = CURRENT_TIMESTAMP
WHERE tool_name='check_data_quality' AND version='v1' AND is_active;

UPDATE public."Table_Catalog"
SET source_code_paths = CASE
        WHEN 'database/migrations/20260914_037_create_analysis_model_call_audit.sql'=ANY(source_code_paths)
            THEN source_code_paths
        ELSE array_append(source_code_paths,
            'database/migrations/20260914_037_create_analysis_model_call_audit.sql')
    END,
    updated_at = CURRENT_TIMESTAMP
WHERE table_schema='public' AND table_name IN ('Analysis_Request','Analysis_Step_Log','Tool_Catalog');

DO $validate$
DECLARE
    missing_columns integer;
BEGIN
    SELECT count(*) INTO missing_columns
    FROM information_schema.columns c
    WHERE c.table_schema='public' AND c.table_name='Analysis_Model_Call'
      AND NOT EXISTS (
          SELECT 1 FROM public."Column_Catalog" cc
          WHERE cc.table_schema=c.table_schema AND cc.table_name=c.table_name
            AND cc.column_name=c.column_name
      );
    IF missing_columns <> 0 THEN
        RAISE EXCEPTION 'Analysis_Model_Call has % uncataloged columns', missing_columns;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public."Tool_Catalog"
        WHERE tool_name='check_data_quality' AND version='v1' AND is_active
          AND tool_specific_limits->>'conditional_execution'='true'
          AND tool_specific_limits->>'invalid_fail_blocks_affected_conclusion'='true'
    ) THEN
        RAISE EXCEPTION 'Conditional data-quality policy was not registered';
    END IF;
END
$validate$;

COMMIT;
