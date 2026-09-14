-- Remove avoidable model retries while keeping Feature_Catalog authoritative.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

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
          "auto_loads_compact_feature_semantics":true,
          "full_definition_lookup_optional":true,
          "missing_model_preload_does_not_reject":true,
          "catalog_remains_authoritative":true
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
        'Retrieve complete Feature definitions when detailed formula, methodology, interpretation, null, or misuse context is needed. Routine data execution auto-loads compact semantics for only the referenced columns, so a separate model call is optional.',
    tool_specific_limits = tool_specific_limits ||
        '{"routine_query_preload_required":false,"full_definition_on_demand":true}'::jsonb,
    updated_at = CURRENT_TIMESTAMP
WHERE tool_name = 'get_feature_definition' AND version = 'v1' AND is_active;

UPDATE public."Tool_Catalog"
SET purpose =
        'Find episodes where one or more catalog-approved conditions are true for consecutive trading observations. The backend auto-loads compact semantics for referenced columns, applies AND conditions, treats NULL as a run break, and returns episode boundaries plus optional exact matching dates without exposing the full source series.',
    updated_at = CURRENT_TIMESTAMP
WHERE tool_name = 'find_condition_runs' AND version = 'v1' AND is_active;

UPDATE public."Table_Catalog"
SET related_functions = array_append(related_functions, 'orchestrator:auto_load_compact_feature_semantics(v1)'),
    source_code_paths = array_append(source_code_paths, 'apps/market-ai-backend/app/orchestrator.py'),
    updated_at = CURRENT_TIMESTAMP
WHERE table_schema = 'public'
  AND table_name = 'Feature_Catalog'
  AND NOT ('orchestrator:auto_load_compact_feature_semantics(v1)' = ANY(related_functions));

UPDATE public."Column_Catalog"
SET source_code_paths = array_remove(
        source_code_paths,
        'database/migrations/20260914_034_auto_load_compact_feature_semantics.sql'
    ),
    updated_at = CURRENT_TIMESTAMP
WHERE table_schema = 'public'
  AND table_name = 'Tool_Catalog'
  AND 'database/migrations/20260914_034_auto_load_compact_feature_semantics.sql'
      = ANY(source_code_paths);

UPDATE public."Column_Catalog"
SET source_code_paths = array_append(
        source_code_paths,
        'database/migrations/20260914_035_auto_load_compact_feature_semantics.sql'
    ),
    updated_at = CURRENT_TIMESTAMP
WHERE table_schema = 'public'
  AND table_name = 'Tool_Catalog'
  AND NOT (
      'database/migrations/20260914_035_auto_load_compact_feature_semantics.sql'
      = ANY(source_code_paths)
  );

DO $validate$
DECLARE
    configured integer;
BEGIN
    SELECT count(*) INTO configured
    FROM public."Tool_Catalog"
    WHERE is_active
      AND tool_name IN (
          'query_features', 'get_timeseries', 'compare_periods', 'screen_features',
          'rank_features', 'aggregate_features', 'compare_groups',
          'find_condition_runs'
      )
      AND (tool_specific_limits->>'auto_loads_compact_feature_semantics')::boolean
      AND (tool_specific_limits->>'missing_model_preload_does_not_reject')::boolean;
    IF configured <> 8 THEN
        RAISE EXCEPTION 'Expected 8 auto-semantic data tools, found %', configured;
    END IF;
END
$validate$;

COMMIT;
