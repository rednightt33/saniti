-- Add point-in-time, data-availability, reproducibility and context-accounting
-- contracts to the already-applied Release 1 market AI foundation.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '10min';

DO $preflight$
BEGIN
    IF to_regclass('public."Tool_Catalog"') IS NULL
       OR to_regclass('public."Analysis_Request"') IS NULL THEN
        RAISE EXCEPTION 'Market AI foundation migration 009 is required';
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'Analysis_Request'
          AND column_name = 'version_snapshot'
    ) THEN
        RAISE EXCEPTION 'Historical-integrity migration is already applied';
    END IF;
END
$preflight$;

ALTER TABLE public."Table_Catalog"
    ADD COLUMN observation_date_column text,
    ADD COLUMN data_available_at_column text,
    ADD COLUMN availability_rule text NOT NULL DEFAULT 'Not applicable.',
    ADD COLUMN point_in_time_status text NOT NULL DEFAULT 'NOT_APPLICABLE',
    ADD COLUMN historical_metadata_method text;

ALTER TABLE public."Table_Catalog"
    ADD CONSTRAINT "Table_Catalog_point_in_time_status_check"
        CHECK (point_in_time_status IN ('AVAILABLE','PARTIAL','UNAVAILABLE','NOT_APPLICABLE')),
    ADD CONSTRAINT "Table_Catalog_availability_rule_check"
        CHECK (btrim(availability_rule) <> '');

COMMENT ON COLUMN public."Table_Catalog".observation_date_column IS
    'Exact physical column representing the market or source observation date.';
COMMENT ON COLUMN public."Table_Catalog".data_available_at_column IS
    'Exact physical timestamp column representing proven decision-time availability; NULL when unavailable or not applicable.';
COMMENT ON COLUMN public."Table_Catalog".availability_rule IS
    'Conservative rule for when observations may be used by historical decisions.';
COMMENT ON COLUMN public."Table_Catalog".point_in_time_status IS
    'AVAILABLE, PARTIAL, UNAVAILABLE, or NOT_APPLICABLE status for historical universe and metadata.';
COMMENT ON COLUMN public."Table_Catalog".historical_metadata_method IS
    'Method used to select historical universe/classification metadata, including explicit current-state fallback.';

CREATE FUNCTION public.validate_table_catalog_temporal_metadata()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    IF NEW.observation_date_column IS NOT NULL
       AND NOT EXISTS (
           SELECT 1 FROM information_schema.columns
           WHERE table_schema = NEW.table_schema AND table_name = NEW.table_name
             AND column_name = NEW.observation_date_column
       ) THEN
        RAISE EXCEPTION 'Observation-date target %.%.% does not exist',
            NEW.table_schema, NEW.table_name, NEW.observation_date_column;
    END IF;
    IF NEW.data_available_at_column IS NOT NULL
       AND NOT EXISTS (
           SELECT 1 FROM information_schema.columns
           WHERE table_schema = NEW.table_schema AND table_name = NEW.table_name
             AND column_name = NEW.data_available_at_column
       ) THEN
        RAISE EXCEPTION 'Availability-time target %.%.% does not exist',
            NEW.table_schema, NEW.table_name, NEW.data_available_at_column;
    END IF;
    RETURN NEW;
END
$function$;

CREATE TRIGGER "Table_Catalog_validate_temporal_metadata"
BEFORE INSERT OR UPDATE OF table_schema, table_name, observation_date_column,
    data_available_at_column
ON public."Table_Catalog"
FOR EACH ROW EXECUTE FUNCTION public.validate_table_catalog_temporal_metadata();

UPDATE public."Table_Catalog"
SET observation_date_column = 'date',
    data_available_at_column = 'ingestion_time',
    availability_rule = 'Use the close-of-day observation no earlier than the next valid trading observation t+1. Historical ingestion_time can be NULL and does not prove same-day availability.',
    point_in_time_status = 'PARTIAL',
    historical_metadata_method = 'Historical OHLCV is retained, but current-universe construction and incomplete historical ingestion timestamps require survivorship and availability disclosure.'
WHERE table_schema = 'public' AND table_name = 'Price_Stock_Indonesia_IDX';

UPDATE public."Table_Catalog"
SET observation_date_column = 'date',
    data_available_at_column = NULL,
    availability_rule = 'Signal uses information through close t; earliest permitted simulated entry is the next valid trading observation t+1.',
    point_in_time_status = 'PARTIAL',
    historical_metadata_method = 'Price features are historical, but sector/industry are current classifications and the table may omit securities absent from the current IDX_Stock_Universe.'
WHERE table_schema = 'public' AND table_name = 'Feature_01_Stock_Daily';

UPDATE public."Table_Catalog"
SET observation_date_column = 'Date',
    data_available_at_column = NULL,
    availability_rule = 'Historical source availability timestamp is not retained. Use complete close-of-day activity no earlier than the next valid trading observation t+1.',
    point_in_time_status = 'PARTIAL',
    historical_metadata_method = 'Source symbols are retained even when absent from the current universe; listing history and historical classifications are not available.'
WHERE table_schema = 'public' AND table_name = 'IDX_Broker_Summary';

UPDATE public."Table_Catalog"
SET observation_date_column = 'date',
    data_available_at_column = NULL,
    availability_rule = 'Signal uses complete broker activity through close t; earliest permitted simulated entry is the next valid trading observation t+1. calculated_at is materialization time, not historical availability.',
    point_in_time_status = 'PARTIAL',
    historical_metadata_method = 'Flow history retains source symbols; broker_type and broker_classification are current reference values rather than point-in-time history.'
WHERE table_schema = 'public' AND table_name = 'Feature_02_Broker_Rolling';

UPDATE public."Table_Catalog"
SET availability_rule = 'Current reference snapshot only; never reinterpret it as historical state.',
    point_in_time_status = 'UNAVAILABLE',
    historical_metadata_method = 'CURRENT_STATE_FALLBACK; historical use requires SURVIVORSHIP_BIAS_WARNING or historical-metadata warning.'
WHERE table_schema = 'public'
  AND table_name IN ('IDX_Stock_Universe','Universe_Equity_Description','IDX_Broker_Profile');

ALTER TABLE public."Feature_Catalog"
    ADD COLUMN availability_rule text NOT NULL DEFAULT
        'Use no earlier than the next valid trading observation after observation date unless earlier source availability is documented.',
    ADD COLUMN point_in_time_safe boolean NOT NULL DEFAULT false,
    ADD COLUMN historical_metadata_warning text;

ALTER TABLE public."Feature_Catalog"
    ADD CONSTRAINT "Feature_Catalog_availability_rule_check"
        CHECK (btrim(availability_rule) <> '');

COMMENT ON COLUMN public."Feature_Catalog".availability_rule IS
    'Decision-time rule used by historical validation and no-look-ahead checks.';
COMMENT ON COLUMN public."Feature_Catalog".point_in_time_safe IS
    'True only when the value itself is time-indexed and usable under its documented availability rule; analysis-level universe limitations still apply.';
COMMENT ON COLUMN public."Feature_Catalog".historical_metadata_warning IS
    'Required warning when a definition uses current state or otherwise incomplete historical metadata.';

UPDATE public."Feature_Catalog"
SET availability_rule = 'Observation is treated as available after close t; earliest simulated entry is next valid trading observation t+1.',
    point_in_time_safe = feature_column NOT IN ('sector','industry'),
    historical_metadata_warning = CASE
        WHEN feature_column IN ('sector','industry')
            THEN 'Current classification is not point-in-time historical metadata.'
        ELSE 'Historical cross-sectional use requires SURVIVORSHIP_BIAS_WARNING because Feature 1 was constructed through the current stock universe.'
    END
WHERE feature_table = 'Feature_01_Stock_Daily' AND is_active;

UPDATE public."Feature_Catalog"
SET availability_rule = 'Complete broker activity is treated as available after close t; earliest simulated entry is next valid trading observation t+1.',
    point_in_time_safe = feature_column NOT IN ('broker_type','broker_classification'),
    historical_metadata_warning = CASE
        WHEN feature_column IN ('broker_type','broker_classification')
            THEN 'Current broker reference classification is not point-in-time historical metadata.'
        ELSE NULL
    END
WHERE feature_table = 'Feature_02_Broker_Rolling' AND is_active;

ALTER TABLE public."Analysis_Request"
    ADD COLUMN version_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN methodology_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN current_context_tokens integer NOT NULL DEFAULT 0,
    ADD COLUMN peak_context_tokens integer NOT NULL DEFAULT 0;

ALTER TABLE public."Analysis_Request"
    ADD CONSTRAINT "Analysis_Request_snapshot_object_check"
        CHECK (jsonb_typeof(version_snapshot) = 'object'
               AND jsonb_typeof(methodology_metadata) = 'object'),
    ADD CONSTRAINT "Analysis_Request_context_tokens_check"
        CHECK (current_context_tokens >= 0 AND peak_context_tokens >= 0
               AND peak_context_tokens >= current_context_tokens),
    ADD CONSTRAINT "Analysis_Request_success_audit_check"
        CHECK (status <> 'SUCCESS'
               OR (version_snapshot <> '{}'::jsonb
                   AND methodology_metadata <> '{}'::jsonb));

COMMENT ON COLUMN public."Analysis_Request".input_tokens IS
    'Cumulative OpenAI input tokens across every model call in this request.';
COMMENT ON COLUMN public."Analysis_Request".output_tokens IS
    'Cumulative OpenAI output tokens across every model call in this request.';
COMMENT ON COLUMN public."Analysis_Request".total_tokens IS
    'Cumulative input plus output tokens across every model call in this request.';
COMMENT ON COLUMN public."Analysis_Request".version_snapshot IS
    'Immutable completed-request snapshot of provider/model, orchestrator/prompt, Feature, tool, analytics methodology, query hash, and evidence versions.';
COMMENT ON COLUMN public."Analysis_Request".methodology_metadata IS
    'Point-in-time universe, survivorship, historical metadata, signal availability, entry time, and look-ahead validation metadata.';
COMMENT ON COLUMN public."Analysis_Request".current_context_tokens IS
    'Estimated active tokens sent on the latest model call; distinct from cumulative input usage.';
COMMENT ON COLUMN public."Analysis_Request".peak_context_tokens IS
    'Maximum active context tokens observed in any single model call for this request.';

CREATE FUNCTION public.protect_completed_analysis_snapshot()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    IF OLD.status = 'SUCCESS'
       AND (NEW.version_snapshot IS DISTINCT FROM OLD.version_snapshot
            OR NEW.methodology_metadata IS DISTINCT FROM OLD.methodology_metadata
            OR NEW.answer IS DISTINCT FROM OLD.answer
            OR NEW.analysis_ready_date IS DISTINCT FROM OLD.analysis_ready_date
            OR NEW.features_used IS DISTINCT FROM OLD.features_used) THEN
        RAISE EXCEPTION 'Completed analysis audit snapshot is immutable';
    END IF;
    RETURN NEW;
END
$function$;

CREATE TRIGGER "Analysis_Request_protect_completed_snapshot"
BEFORE UPDATE ON public."Analysis_Request"
FOR EACH ROW EXECUTE FUNCTION public.protect_completed_analysis_snapshot();

UPDATE public."Table_Catalog"
SET source_code_paths = CASE
        WHEN 'database/migrations/20260913_010_add_market_ai_historical_integrity.sql'
             = ANY(source_code_paths) THEN source_code_paths
        ELSE array_append(source_code_paths,
            'database/migrations/20260913_010_add_market_ai_historical_integrity.sql')
    END,
    related_functions = CASE
        WHEN table_name = 'Analysis_Request'
             AND NOT ('protect_completed_analysis_snapshot()' = ANY(related_functions))
            THEN array_append(related_functions, 'protect_completed_analysis_snapshot()')
        WHEN table_name = 'Feature_Catalog'
             AND NOT ('validate_feature_catalog_target()' = ANY(related_functions))
            THEN array_append(related_functions, 'validate_feature_catalog_target()')
        ELSE related_functions
    END
WHERE table_schema = 'public'
  AND table_name IN ('Feature_Catalog','Analysis_Request',
                     'Feature_01_Stock_Daily','Feature_02_Broker_Rolling');

INSERT INTO public."Column_Catalog" (
    table_schema, table_name, column_name, ordinal_position, data_type,
    is_nullable, default_expression, is_primary_key, definition,
    source_column_or_expression, unit, null_rule, source_code_paths,
    documentation_status
)
SELECT c.table_schema, c.table_name, c.column_name, c.ordinal_position,
       c.data_type, c.is_nullable = 'YES', c.column_default, false,
       pg_catalog.col_description(pc.oid, pa.attnum),
       'Defined by database/migrations/20260913_010_add_market_ai_historical_integrity.sql',
       CASE WHEN c.column_name LIKE '%tokens' THEN 'Tokens' ELSE NULL END,
       CASE WHEN c.is_nullable = 'NO' THEN 'Never NULL.'
            ELSE 'NULL when not applicable or when historical evidence is unavailable.' END,
       ARRAY['database/migrations/20260913_010_add_market_ai_historical_integrity.sql'],
       'VERIFIED'
FROM information_schema.columns c
JOIN public."Table_Catalog" tc
  ON tc.table_schema = c.table_schema AND tc.table_name = c.table_name
JOIN pg_catalog.pg_class pc
  ON pc.oid = format('%I.%I', c.table_schema, c.table_name)::regclass
JOIN pg_catalog.pg_attribute pa
  ON pa.attrelid = pc.oid AND pa.attname = c.column_name
LEFT JOIN public."Column_Catalog" existing
  ON existing.table_schema = c.table_schema AND existing.table_name = c.table_name
 AND existing.column_name = c.column_name
WHERE existing.column_name IS NULL
  AND c.table_name IN ('Feature_Catalog','Analysis_Request');

DO $validate$
DECLARE
    missing_catalog_columns integer;
    unsafe_active_fields integer;
BEGIN
    SELECT count(*) INTO missing_catalog_columns
    FROM information_schema.columns c
    WHERE c.table_schema = 'public'
      AND c.table_name IN ('Feature_Catalog','Analysis_Request')
      AND NOT EXISTS (
          SELECT 1 FROM public."Column_Catalog" cc
          WHERE cc.table_schema = c.table_schema AND cc.table_name = c.table_name
            AND cc.column_name = c.column_name
      );
    SELECT count(*) INTO unsafe_active_fields
    FROM public."Feature_Catalog"
    WHERE is_active AND btrim(availability_rule) = '';
    IF missing_catalog_columns <> 0 OR unsafe_active_fields <> 0 THEN
        RAISE EXCEPTION 'Historical-integrity validation failed: missing catalog columns %, blank availability rules %',
            missing_catalog_columns, unsafe_active_fields;
    END IF;
END
$validate$;

COMMIT;
