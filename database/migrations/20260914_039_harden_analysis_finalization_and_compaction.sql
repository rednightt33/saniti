-- Register the v2 stopping/finalization policy and evidence-preserving context contract.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '2min';

DO $preflight$
BEGIN
    IF to_regclass('public."Tool_Catalog"') IS NULL THEN
        RAISE EXCEPTION 'Tool_Catalog is required';
    END IF;
END
$preflight$;

UPDATE public."Tool_Catalog"
SET tool_specific_limits = tool_specific_limits ||
        '{
          "stopping_policy_version":"v2",
          "blocked_after_sufficient_evidence_gate":true,
          "finalization_budget_reserved":true
        }'::jsonb,
    updated_at = CURRENT_TIMESTAMP
WHERE is_active
  AND tool_name IN (
      'query_features', 'get_timeseries', 'compare_periods', 'screen_features',
      'rank_features', 'aggregate_features', 'compare_groups',
      'find_condition_runs'
  );

UPDATE public."Tool_Catalog"
SET purpose =
        'Run a scoped quality check only when missing coverage, NULL/gap concerns, stale or cross-feature state, anomaly validation, or material conclusion risk justifies it. Impossible or invalid data returns FAIL and blocks the affected conclusion. WARNING and source-valid PASS anomalies explicitly permit analysis and finalization to continue.',
    tool_specific_limits = tool_specific_limits ||
        '{
          "stopping_policy_version":"v2",
          "pass_or_warning_allows_analysis":true,
          "returns_explicit_continuation_status":true,
          "fail_blocks_affected_conclusion":true
        }'::jsonb,
    updated_at = CURRENT_TIMESTAMP
WHERE tool_name='check_data_quality' AND version='v1' AND is_active;

UPDATE public."Tool_Catalog"
SET purpose =
        'Persist one compact decisive evidence package after all necessary follow-ups. When the configured minimum distinct analytical-query requirement is satisfied and no quality FAIL exists, this activates the evidence gate: further data tools are locked and complete_analysis is the only allowed next tool.',
    tool_specific_limits = tool_specific_limits ||
        '{
          "stopping_policy_version":"v2",
          "locks_data_tools_when_minimum_satisfied":true,
          "has_reserved_tool_result_budget":true,
          "preserves_query_hashes_and_decisive_values":true
        }'::jsonb,
    updated_at = CURRENT_TIMESTAMP
WHERE tool_name='record_evidence' AND version='v1' AND is_active;

UPDATE public."Tool_Catalog"
SET purpose =
        'Accept the explicit stopping checklist after sufficient evidence has locked further data work. A successful call removes every tool schema from the next model call, which may only produce the strict final response. Invalid final responses receive exact validation feedback with at most two retries.',
    tool_specific_limits = tool_specific_limits ||
        '{
          "stopping_policy_version":"v2",
          "only_tool_after_evidence_gate":true,
          "removes_all_tools_after_success":true,
          "final_response_retry_limit_variable":"AI_FINAL_RESPONSE_MAX_RETRIES",
          "has_reserved_tool_result_budget":true
        }'::jsonb,
    updated_at = CURRENT_TIMESTAMP
WHERE tool_name='complete_analysis' AND version='v1' AND is_active;

UPDATE public."Table_Catalog"
SET source_code_paths = CASE
        WHEN 'database/migrations/20260914_039_harden_analysis_finalization_and_compaction.sql'=ANY(source_code_paths)
            THEN source_code_paths
        ELSE array_append(
            source_code_paths,
            'database/migrations/20260914_039_harden_analysis_finalization_and_compaction.sql'
        )
    END,
    updated_at = CURRENT_TIMESTAMP
WHERE table_schema='public'
  AND table_name IN ('Tool_Catalog','Analysis_Request','Analysis_Step_Log','Analysis_Evidence');

UPDATE public."Column_Catalog"
SET source_code_paths = CASE
        WHEN 'database/migrations/20260914_039_harden_analysis_finalization_and_compaction.sql'=ANY(source_code_paths)
            THEN source_code_paths
        ELSE array_append(
            source_code_paths,
            'database/migrations/20260914_039_harden_analysis_finalization_and_compaction.sql'
        )
    END,
    updated_at = CURRENT_TIMESTAMP
WHERE table_schema='public' AND table_name='Tool_Catalog'
  AND column_name IN ('purpose','tool_specific_limits','updated_at');

DO $validate$
DECLARE
    gated_data_tools integer;
BEGIN
    SELECT count(*) INTO gated_data_tools
    FROM public."Tool_Catalog"
    WHERE is_active
      AND tool_name IN (
          'query_features', 'get_timeseries', 'compare_periods', 'screen_features',
          'rank_features', 'aggregate_features', 'compare_groups',
          'find_condition_runs'
      )
      AND tool_specific_limits->>'stopping_policy_version'='v2'
      AND (tool_specific_limits->>'blocked_after_sufficient_evidence_gate')::boolean;
    IF gated_data_tools <> 8 THEN
        RAISE EXCEPTION 'Expected 8 evidence-gated analytical tools, found %', gated_data_tools;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM public."Tool_Catalog"
        WHERE tool_name='record_evidence' AND version='v1' AND is_active
          AND (tool_specific_limits->>'locks_data_tools_when_minimum_satisfied')::boolean
          AND (tool_specific_limits->>'has_reserved_tool_result_budget')::boolean
    ) THEN
        RAISE EXCEPTION 'record_evidence v2 gate metadata is incomplete';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM public."Tool_Catalog"
        WHERE tool_name='complete_analysis' AND version='v1' AND is_active
          AND (tool_specific_limits->>'only_tool_after_evidence_gate')::boolean
          AND (tool_specific_limits->>'removes_all_tools_after_success')::boolean
    ) THEN
        RAISE EXCEPTION 'complete_analysis v2 finalization metadata is incomplete';
    END IF;
END
$validate$;

COMMIT;
