-- Release 1 database foundation for the generic Feature 1-2 AI analyst.
-- This migration creates metadata, readiness and audit contracts only. It does
-- not enable Feature 2 automation or any deferred analytical method.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '20min';

DO $preflight$
BEGIN
    IF to_regclass('public."Feature_02_Broker_Rolling"') IS NULL THEN
        RAISE EXCEPTION 'Feature 02 gate has not completed';
    END IF;
    IF (SELECT count(*) FROM public."Feature_Catalog"
        WHERE feature_table = 'Feature_02_Broker_Rolling'
          AND version = 'v1' AND is_active) <> 38 THEN
        RAISE EXCEPTION 'Feature 02 does not have 38 active v1 definitions';
    END IF;
    IF to_regclass('public."Tool_Catalog"') IS NOT NULL THEN
        RAISE EXCEPTION 'Release 1 market AI foundation already exists';
    END IF;
END
$preflight$;

ALTER TABLE public."Table_Catalog"
    ADD COLUMN readiness_mode text NOT NULL DEFAULT 'NOT_APPLICABLE',
    ADD COLUMN readiness_date_column text;

ALTER TABLE public."Table_Catalog"
    ADD CONSTRAINT "Table_Catalog_readiness_mode_check"
        CHECK (readiness_mode IN ('DATA_DATE', 'REFERENCE_STATE', 'NOT_APPLICABLE')),
    ADD CONSTRAINT "Table_Catalog_readiness_column_check"
        CHECK ((readiness_mode = 'DATA_DATE' AND readiness_date_column IS NOT NULL
                AND btrim(readiness_date_column) <> '')
               OR (readiness_mode <> 'DATA_DATE' AND readiness_date_column IS NULL));

UPDATE public."Table_Catalog"
SET readiness_mode = 'DATA_DATE',
    readiness_date_column = CASE table_name
        WHEN 'Price_Stock_Indonesia_IDX' THEN 'date'
        WHEN 'Feature_01_Stock_Daily' THEN 'date'
        WHEN 'IDX_Broker_Summary' THEN 'Date'
        WHEN 'Feature_02_Broker_Rolling' THEN 'date'
        ELSE readiness_date_column
    END
WHERE table_name IN (
    'Price_Stock_Indonesia_IDX', 'Feature_01_Stock_Daily',
    'IDX_Broker_Summary', 'Feature_02_Broker_Rolling'
);

UPDATE public."Table_Catalog"
SET readiness_mode = 'REFERENCE_STATE', readiness_date_column = NULL
WHERE category = 'Reference';

COMMENT ON COLUMN public."Table_Catalog".readiness_mode IS
    'DATA_DATE uses a registered date column; REFERENCE_STATE reports state without reducing the common analysis date; NOT_APPLICABLE has no readiness contribution.';
COMMENT ON COLUMN public."Table_Catalog".readiness_date_column IS
    'Exact physical date column used for live readiness when readiness_mode is DATA_DATE.';

ALTER TABLE public."Feature_Catalog"
    DROP CONSTRAINT "Feature_Catalog_feature_table_check",
    ADD COLUMN semantic_role text NOT NULL DEFAULT 'MEASURE',
    ADD COLUMN allowed_aggregations text[] NOT NULL DEFAULT '{}',
    ADD COLUMN ranking_interpretation text NOT NULL DEFAULT 'CONTEXTUAL',
    ADD COLUMN is_filterable boolean NOT NULL DEFAULT true,
    ADD COLUMN is_groupable boolean NOT NULL DEFAULT false;

UPDATE public."Feature_Catalog"
SET semantic_role = CASE
        WHEN feature_category = 'Identity' THEN 'IDENTITY'
        WHEN feature_category = 'Metadata' OR feature_category = 'Broker Classification'
            THEN 'DIMENSION'
        ELSE 'MEASURE'
    END,
    allowed_aggregations = CASE
        WHEN feature_category = 'Identity' THEN ARRAY['COUNT']::text[]
        WHEN feature_category = 'Metadata' OR feature_category = 'Broker Classification'
            THEN ARRAY['COUNT','COUNT_DISTINCT']::text[]
        ELSE ARRAY['AVG','MEDIAN','MIN','MAX','COUNT']::text[]
    END,
    ranking_interpretation = CASE
        WHEN feature_category IN ('Identity','Metadata','Broker Classification')
            THEN 'NOT_APPLICABLE'
        ELSE 'CONTEXTUAL'
    END,
    is_groupable = feature_category IN ('Identity','Metadata','Broker Classification');

ALTER TABLE public."Feature_Catalog"
    ADD CONSTRAINT "Feature_Catalog_semantic_role_check"
        CHECK (semantic_role IN ('IDENTITY','DIMENSION','MEASURE')),
    ADD CONSTRAINT "Feature_Catalog_ranking_interpretation_check"
        CHECK (ranking_interpretation IN ('HIGHER','LOWER','CONTEXTUAL','NOT_APPLICABLE')),
    ADD CONSTRAINT "Feature_Catalog_aggregations_check"
        CHECK (allowed_aggregations <@ ARRAY[
            'SUM','AVG','MEDIAN','MIN','MAX','COUNT','COUNT_DISTINCT',
            'PERCENTILE','WEIGHTED_AVG'
        ]::text[]);

CREATE UNIQUE INDEX "Feature_Catalog_one_active_definition_idx"
    ON public."Feature_Catalog" (feature_table, feature_column)
    WHERE is_active;

COMMENT ON TABLE public."Feature_Catalog" IS
    'Machine-readable semantic and usage contract for validated Feature-table columns.';
COMMENT ON COLUMN public."Feature_Catalog".feature_table IS
    'Exact physical name of a verified table registered as category Feature.';
COMMENT ON COLUMN public."Feature_Catalog".semantic_role IS
    'IDENTITY, DIMENSION, or MEASURE role used by generic query tools.';
COMMENT ON COLUMN public."Feature_Catalog".allowed_aggregations IS
    'Allow-list of generic aggregations valid for this column.';
COMMENT ON COLUMN public."Feature_Catalog".ranking_interpretation IS
    'Default analytical direction; CONTEXTUAL requires the request to state direction.';

CREATE OR REPLACE FUNCTION public.validate_feature_catalog_target()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    IF NEW.is_active THEN
        IF NEW.feature_table !~ '^Feature_[0-9]{2}_[A-Za-z0-9_]+$' THEN
            RAISE EXCEPTION 'Active Feature table name % is not governed', NEW.feature_table;
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = NEW.feature_table
              AND column_name = NEW.feature_column
        ) THEN
            RAISE EXCEPTION 'Active catalog target %.% does not exist',
                NEW.feature_table, NEW.feature_column;
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM public."Table_Catalog"
            WHERE table_schema = 'public' AND table_name = NEW.feature_table
              AND category = 'Feature' AND documentation_status = 'VERIFIED'
        ) THEN
            RAISE EXCEPTION 'Active Feature table % is not VERIFIED in Table_Catalog',
                NEW.feature_table;
        END IF;
    END IF;
    RETURN NEW;
END
$function$;

DROP TRIGGER "Feature_Catalog_validate_target" ON public."Feature_Catalog";
CREATE TRIGGER "Feature_Catalog_validate_target"
BEFORE INSERT OR UPDATE OF feature_table, feature_column, is_active
ON public."Feature_Catalog"
FOR EACH ROW EXECUTE FUNCTION public.validate_feature_catalog_target();

CREATE TABLE public."Feature_Relationship_Catalog" (
    left_feature_table text NOT NULL,
    right_feature_table text NOT NULL,
    left_join_columns text[] NOT NULL,
    right_join_columns text[] NOT NULL,
    relationship_type text NOT NULL,
    safe_output_grain text NOT NULL,
    requires_preaggregation boolean NOT NULL,
    definition text NOT NULL,
    version text NOT NULL DEFAULT 'v1',
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Feature_Relationship_Catalog_pkey"
        PRIMARY KEY (left_feature_table, right_feature_table, version),
    CONSTRAINT "Feature_Relationship_Catalog_columns_check"
        CHECK (cardinality(left_join_columns) > 0
               AND cardinality(left_join_columns) = cardinality(right_join_columns)),
    CONSTRAINT "Feature_Relationship_Catalog_type_check"
        CHECK (relationship_type IN ('ONE_TO_ONE','ONE_TO_MANY','MANY_TO_ONE','MANY_TO_MANY')),
    CONSTRAINT "Feature_Relationship_Catalog_version_check"
        CHECK (version ~ '^v[1-9][0-9]*$')
);

CREATE TRIGGER "Feature_Relationship_Catalog_set_updated_at"
BEFORE UPDATE ON public."Feature_Relationship_Catalog"
FOR EACH ROW EXECUTE FUNCTION public.set_database_catalog_updated_at();

INSERT INTO public."Feature_Relationship_Catalog" (
    left_feature_table, right_feature_table, left_join_columns,
    right_join_columns, relationship_type, safe_output_grain,
    requires_preaggregation, definition
) VALUES (
    'Feature_01_Stock_Daily', 'Feature_02_Broker_Rolling',
    ARRAY['ticker','date'], ARRAY['ticker','date'], 'ONE_TO_MANY',
    'ticker × date after explicit Feature 02 aggregation, or ticker × date × market_board × broker without aggregation',
    true,
    'Feature 1 has one row per ticker/date; Feature 2 can have many broker/board rows. Aggregate Feature 2 to the requested target grain before joining when Feature 1 values must not be duplicated.'
);

CREATE TABLE public."Tool_Catalog" (
    tool_name text NOT NULL,
    tool_family text NOT NULL,
    tool_type text NOT NULL,
    purpose text NOT NULL,
    input_schema jsonb NOT NULL,
    output_schema jsonb NOT NULL,
    execution_type text NOT NULL,
    handler_name text,
    default_output_rows integer,
    max_output_rows integer,
    max_input_rows integer,
    max_tickers integer,
    max_date_range_days integer,
    max_estimated_rows bigint,
    timeout_seconds integer,
    max_output_bytes bigint,
    max_llm_result_rows integer,
    max_llm_result_bytes bigint,
    max_llm_result_tokens integer,
    requires_analytics_worker boolean NOT NULL DEFAULT false,
    requires_feature_catalog boolean NOT NULL DEFAULT true,
    requires_data_readiness boolean NOT NULL DEFAULT true,
    tool_specific_limits jsonb NOT NULL DEFAULT '{}'::jsonb,
    version text NOT NULL DEFAULT 'v1',
    is_active boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Tool_Catalog_pkey" PRIMARY KEY (tool_name, version),
    CONSTRAINT "Tool_Catalog_family_check"
        CHECK (tool_family IN ('META','DISCOVERY','QUALITY','QUERY','SCREENING','HISTORICAL_VALIDATION','ADVANCED','AUDIT')),
    CONSTRAINT "Tool_Catalog_execution_check"
        CHECK (execution_type IN ('BACKEND','ANALYTICS_WORKER','ORCHESTRATOR')),
    CONSTRAINT "Tool_Catalog_positive_limits_check"
        CHECK ((default_output_rows IS NULL OR default_output_rows > 0)
           AND (max_output_rows IS NULL OR max_output_rows > 0)
           AND (max_input_rows IS NULL OR max_input_rows > 0)
           AND (max_tickers IS NULL OR max_tickers > 0)
           AND (max_date_range_days IS NULL OR max_date_range_days > 0)
           AND (max_estimated_rows IS NULL OR max_estimated_rows > 0)
           AND (timeout_seconds IS NULL OR timeout_seconds > 0)
           AND (max_output_bytes IS NULL OR max_output_bytes > 0)
           AND (max_llm_result_rows IS NULL OR max_llm_result_rows > 0)
           AND (max_llm_result_bytes IS NULL OR max_llm_result_bytes > 0)
           AND (max_llm_result_tokens IS NULL OR max_llm_result_tokens > 0))
);

CREATE UNIQUE INDEX "Tool_Catalog_one_active_version_idx"
    ON public."Tool_Catalog" (tool_name) WHERE is_active;
CREATE TRIGGER "Tool_Catalog_set_updated_at"
BEFORE UPDATE ON public."Tool_Catalog"
FOR EACH ROW EXECUTE FUNCTION public.set_database_catalog_updated_at();

COMMENT ON TABLE public."Tool_Catalog" IS
    'Versioned tool registry and advertised operational ceilings. Backend and worker configuration remain the enforcement authority.';
COMMENT ON COLUMN public."Tool_Catalog".max_output_rows IS
    'Backend result ceiling; this is independent of the smaller LLM-facing result limits.';
COMMENT ON COLUMN public."Tool_Catalog".max_llm_result_tokens IS
    'Maximum compact tool-result tokens exposed to the model for one call.';

WITH tools(tool_name, family, tool_type, purpose, execution_type, active,
           needs_worker, needs_feature, needs_readiness) AS (
    VALUES
    ('list_tools','META','DISCOVERY','List currently available and expandable tool capabilities.','ORCHESTRATOR',true,false,false,false),
    ('validate_query_request','META','SAFETY','Validate a structured request against catalog and effective limits.','BACKEND',true,false,true,false),
    ('estimate_query_size','META','SAFETY','Estimate planned rows and recommend execute, aggregate, reduce, filter, split, or worker.','BACKEND',true,false,true,false),
    ('find_features','DISCOVERY','DISCOVERY','Search feature metadata without loading the full catalog.','BACKEND',true,false,true,false),
    ('get_feature_definition','DISCOVERY','DISCOVERY','Retrieve definitions only for relevant feature columns.','BACKEND',true,false,true,false),
    ('list_feature_tables','DISCOVERY','DISCOVERY','List verified feature tables and their grain/readiness metadata.','BACKEND',true,false,true,false),
    ('check_data_freshness','QUALITY','QUALITY','Find the common safe analysis date and stale dependencies.','BACKEND',true,false,true,true),
    ('check_data_quality','QUALITY','QUALITY','Classify impossible data as FAIL, suspicious/incomplete data as WARNING, and source-valid extremes as PASS with anomaly flags.','BACKEND',true,false,true,true),
    ('query_features','QUERY','RETRIEVAL','Retrieve bounded feature observations using structured filters.','BACKEND',true,false,true,true),
    ('get_timeseries','QUERY','RETRIEVAL','Retrieve a bounded ticker or entity feature time series.','BACKEND',true,false,true,true),
    ('compare_periods','QUERY','COMPARISON','Compare up to six explicit bounded periods.','BACKEND',true,false,true,true),
    ('screen_features','SCREENING','SCREENING','Screen candidates using catalog-approved conditions.','BACKEND',true,false,true,true),
    ('rank_features','SCREENING','RANKING','Rank entities using explicit direction and explicit weights.','BACKEND',true,false,true,true),
    ('aggregate_features','SCREENING','AGGREGATION','Aggregate only with Feature_Catalog-approved operations.','BACKEND',true,false,true,true),
    ('compare_groups','SCREENING','COMPARISON','Compare bounded registered groups at an explicit grain.','BACKEND',true,false,true,true),
    ('record_evidence','AUDIT','AUDIT','Persist compact evidence and reproducibility references.','BACKEND',true,false,false,false),
    ('get_analysis_history','AUDIT','AUDIT','Retrieve only relevant prior analyses within the history token budget.','BACKEND',true,false,false,false),
    ('run_event_study','HISTORICAL_VALIDATION','ANALYTICS','Evaluate outcomes after point-in-time signals.','ANALYTICS_WORKER',false,true,true,true),
    ('run_signal_validation','HISTORICAL_VALIDATION','ANALYTICS','Test quantiles, rank IC, monotonicity and chronological out-of-sample evidence.','ANALYTICS_WORKER',false,true,true,true),
    ('run_backtest','HISTORICAL_VALIDATION','ANALYTICS','Run an explicit no-look-ahead long-only historical simulation.','ANALYTICS_WORKER',false,true,true,true),
    ('detect_anomalies','HISTORICAL_VALIDATION','ANALYTICS','Surface source-valid extreme observations without treating them as invalid data.','ANALYTICS_WORKER',false,true,true,true),
    ('run_forward_return_analysis','HISTORICAL_VALIDATION','ANALYTICS','Measure matured forward returns following a signal.','ANALYTICS_WORKER',false,true,true,true),
    ('run_statistics','HISTORICAL_VALIDATION','ANALYTICS','Compute bounded descriptive and inferential statistics.','ANALYTICS_WORKER',false,true,true,true),
    ('run_correlation','HISTORICAL_VALIDATION','ANALYTICS','Measure descriptive association without implying causation.','ANALYTICS_WORKER',false,true,true,true),
    ('run_regression','ADVANCED','ANALYTICS','Deferred generic regression analysis.','ANALYTICS_WORKER',false,true,true,true),
    ('run_clustering','ADVANCED','ANALYTICS','Deferred generic clustering analysis.','ANALYTICS_WORKER',false,true,true,true),
    ('run_hmm','ADVANCED','ANALYTICS','Deferred hidden Markov regime analysis.','ANALYTICS_WORKER',false,true,true,true),
    ('run_pca','ADVANCED','ANALYTICS','Deferred principal-component analysis.','ANALYTICS_WORKER',false,true,true,true)
)
INSERT INTO public."Tool_Catalog" (
    tool_name, tool_family, tool_type, purpose, input_schema, output_schema,
    execution_type, handler_name, default_output_rows, max_output_rows,
    max_input_rows, max_tickers, max_date_range_days, max_estimated_rows,
    timeout_seconds, max_output_bytes, max_llm_result_rows,
    max_llm_result_bytes, max_llm_result_tokens,
    requires_analytics_worker, requires_feature_catalog,
    requires_data_readiness, tool_specific_limits, is_active
)
SELECT tool_name, family, tool_type, purpose,
       '{"type":"object","additionalProperties":false}'::jsonb,
       '{"type":"object"}'::jsonb,
       execution_type,
       CASE WHEN active THEN tool_name ELSE NULL END,
       CASE WHEN family IN ('QUERY','SCREENING') THEN 100 ELSE NULL END,
       CASE WHEN family IN ('QUERY','SCREENING') THEN 5000 ELSE NULL END,
       CASE WHEN needs_worker THEN 50000 ELSE NULL END,
       CASE WHEN needs_feature THEN 20 ELSE NULL END,
       CASE WHEN needs_feature THEN 1825 ELSE NULL END,
       CASE WHEN needs_feature THEN 100000 ELSE NULL END,
       CASE WHEN needs_worker THEN 120 ELSE 15 END,
       CASE WHEN needs_worker THEN 20971520 ELSE 1048576 END,
       200, 131072, 4000,
       needs_worker, needs_feature, needs_readiness,
       CASE
         WHEN tool_name = 'compare_periods' THEN '{"max_periods":6}'::jsonb
         WHEN tool_name = 'screen_features' THEN '{"max_candidates":500}'::jsonb
         WHEN tool_name = 'record_evidence' THEN '{"max_evidence_per_request":25}'::jsonb
         WHEN needs_worker THEN '{"analytics_max_columns":30,"analytics_max_events":20000,"analytics_max_horizons":4}'::jsonb
         ELSE '{}'::jsonb
       END,
       active
FROM tools;

CREATE TABLE public."Analysis_Request" (
    request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_reference text,
    question text NOT NULL,
    status text NOT NULL DEFAULT 'PENDING',
    current_stage text NOT NULL DEFAULT 'DISCOVERY',
    exposed_tool_families text[] NOT NULL DEFAULT ARRAY['META','DISCOVERY','QUALITY'],
    model text,
    openai_response_id text,
    analysis_ready_date date,
    features_used text[] NOT NULL DEFAULT '{}',
    input_tokens integer NOT NULL DEFAULT 0,
    output_tokens integer NOT NULL DEFAULT 0,
    total_tokens integer NOT NULL DEFAULT 0,
    tool_result_tokens integer NOT NULL DEFAULT 0,
    history_tokens integer NOT NULL DEFAULT 0,
    feature_metadata_tokens integer NOT NULL DEFAULT 0,
    tool_call_count integer NOT NULL DEFAULT 0,
    tool_iteration_count integer NOT NULL DEFAULT 0,
    context_compaction_count integer NOT NULL DEFAULT 0,
    answer jsonb,
    recommended_next_analysis jsonb NOT NULL DEFAULT '[]'::jsonb,
    error_message text,
    attempt_count integer NOT NULL DEFAULT 0,
    lease_owner text,
    lease_expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at timestamptz,
    completed_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Analysis_Request_status_check"
        CHECK (status IN ('PENDING','PROCESSING','SUCCESS','FAILED','CANCELLED')),
    CONSTRAINT "Analysis_Request_stage_check"
        CHECK (current_stage IN ('DISCOVERY','SCREENING','HISTORICAL_VALIDATION','ADVANCED','FINAL')),
    CONSTRAINT "Analysis_Request_token_counts_check"
        CHECK (input_tokens >= 0 AND output_tokens >= 0 AND total_tokens >= 0
           AND tool_result_tokens >= 0 AND history_tokens >= 0
           AND feature_metadata_tokens >= 0 AND tool_call_count >= 0
           AND tool_iteration_count >= 0 AND context_compaction_count >= 0
           AND attempt_count >= 0)
);

CREATE INDEX "Analysis_Request_pending_idx"
    ON public."Analysis_Request" (status, created_at)
    WHERE status IN ('PENDING','PROCESSING');
CREATE TRIGGER "Analysis_Request_set_updated_at"
BEFORE UPDATE ON public."Analysis_Request"
FOR EACH ROW EXECUTE FUNCTION public.set_database_catalog_updated_at();

CREATE TABLE public."Analysis_Step_Log" (
    step_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id uuid NOT NULL REFERENCES public."Analysis_Request" (request_id) ON DELETE CASCADE,
    step_number integer NOT NULL,
    stage text NOT NULL,
    tool_name text,
    sanitized_arguments jsonb NOT NULL DEFAULT '{}'::jsonb,
    estimated_rows bigint,
    processed_rows bigint,
    returned_rows bigint,
    returned_bytes bigint,
    llm_result_tokens integer,
    duration_ms integer,
    query_hash text,
    evidence_references jsonb NOT NULL DEFAULT '[]'::jsonb,
    result_summary jsonb,
    status text NOT NULL,
    error_message text,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Analysis_Step_Log_request_step_key" UNIQUE (request_id, step_number),
    CONSTRAINT "Analysis_Step_Log_status_check" CHECK (status IN ('STARTED','SUCCESS','WARNING','FAILED','COMPACTED')),
    CONSTRAINT "Analysis_Step_Log_counts_check" CHECK (
        (estimated_rows IS NULL OR estimated_rows >= 0)
        AND (processed_rows IS NULL OR processed_rows >= 0)
        AND (returned_rows IS NULL OR returned_rows >= 0)
        AND (returned_bytes IS NULL OR returned_bytes >= 0)
        AND (llm_result_tokens IS NULL OR llm_result_tokens >= 0)
        AND (duration_ms IS NULL OR duration_ms >= 0))
);

CREATE INDEX "Analysis_Step_Log_request_idx"
    ON public."Analysis_Step_Log" (request_id, step_number);

CREATE TABLE public."Analysis_Evidence" (
    evidence_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id uuid NOT NULL REFERENCES public."Analysis_Request" (request_id) ON DELETE CASCADE,
    step_id bigint REFERENCES public."Analysis_Step_Log" (step_id) ON DELETE SET NULL,
    evidence_type text NOT NULL,
    claim text NOT NULL,
    compact_payload jsonb NOT NULL,
    query_hash text,
    source_tables text[] NOT NULL DEFAULT '{}',
    source_row_count bigint,
    analysis_ready_date date,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Analysis_Evidence_type_check"
        CHECK (evidence_type IN ('OBSERVATION','QUALITY','ANOMALY','STATISTIC','HISTORICAL_TEST','WARNING')),
    CONSTRAINT "Analysis_Evidence_row_count_check" CHECK (source_row_count IS NULL OR source_row_count >= 0)
);

CREATE INDEX "Analysis_Evidence_request_idx"
    ON public."Analysis_Evidence" (request_id, created_at);

CREATE FUNCTION public.check_analysis_data_readiness(requested_feature_tables text[])
RETURNS TABLE (
    feature_table text,
    latest_feature_date date,
    latest_source_date date,
    status text,
    lag_calendar_days integer,
    safe_analysis_date date,
    source_details jsonb
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    requested_table text;
    feature_date_column text;
    source_table text;
    source_mode text;
    source_date_column text;
    source_latest date;
    common_source_date date;
    details jsonb;
BEGIN
    IF requested_feature_tables IS NULL OR cardinality(requested_feature_tables) = 0 THEN
        RAISE EXCEPTION 'At least one Feature table is required';
    END IF;

    FOREACH requested_table IN ARRAY requested_feature_tables LOOP
        SELECT c.readiness_date_column
        INTO feature_date_column
        FROM public."Table_Catalog" c
        WHERE c.table_schema = 'public' AND c.table_name = requested_table
          AND c.category = 'Feature' AND c.documentation_status = 'VERIFIED'
          AND c.readiness_mode = 'DATA_DATE'
          AND EXISTS (SELECT 1 FROM public."Feature_Catalog" f
                      WHERE f.feature_table = requested_table AND f.is_active);

        IF feature_date_column IS NULL THEN
            RAISE EXCEPTION 'Feature table % is not active, VERIFIED and DATA_DATE-ready', requested_table;
        END IF;

        EXECUTE format('SELECT max(%I)::date FROM public.%I', feature_date_column, requested_table)
        INTO latest_feature_date;
        common_source_date := NULL;
        details := '[]'::jsonb;

        FOR source_table IN
            SELECT DISTINCT unnest(c.source_tables)
            FROM public."Table_Catalog" c
            WHERE c.table_schema = 'public' AND c.table_name = requested_table
        LOOP
            SELECT c.readiness_mode, c.readiness_date_column
            INTO source_mode, source_date_column
            FROM public."Table_Catalog" c
            WHERE c.table_schema = 'public' AND c.table_name = source_table;

            source_latest := NULL;
            IF source_mode = 'DATA_DATE' AND source_date_column IS NOT NULL THEN
                EXECUTE format('SELECT max(%I)::date FROM public.%I', source_date_column, source_table)
                INTO source_latest;
                common_source_date := CASE WHEN common_source_date IS NULL THEN source_latest
                    ELSE least(common_source_date, source_latest) END;
            END IF;

            details := details || jsonb_build_array(jsonb_build_object(
                'table', source_table, 'readiness_mode', coalesce(source_mode, 'UNKNOWN'),
                'latest_date', source_latest
            ));
        END LOOP;

        latest_source_date := common_source_date;
        safe_analysis_date := CASE
            WHEN latest_feature_date IS NULL THEN NULL
            WHEN latest_source_date IS NULL THEN latest_feature_date
            ELSE least(latest_feature_date, latest_source_date)
        END;
        lag_calendar_days := CASE
            WHEN latest_feature_date IS NULL OR latest_source_date IS NULL THEN NULL
            ELSE latest_source_date - latest_feature_date
        END;
        status := CASE
            WHEN latest_feature_date IS NULL THEN 'UNKNOWN'
            WHEN latest_source_date IS NULL THEN 'READY'
            WHEN latest_feature_date >= latest_source_date THEN 'READY'
            ELSE 'LAGGING'
        END;
        feature_table := requested_table;
        source_details := details;
        RETURN NEXT;
    END LOOP;
END
$function$;

COMMENT ON FUNCTION public.check_analysis_data_readiness(text[]) IS
    'Controlled live freshness check for active verified Feature tables. Reference-state dependencies are reported but do not reduce the common safe date.';
REVOKE ALL ON FUNCTION public.check_analysis_data_readiness(text[]) FROM PUBLIC;

DO $roles$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'market_ai_reader') THEN
        CREATE ROLE market_ai_reader NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'market_ai_logger') THEN
        CREATE ROLE market_ai_logger NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'market_analytics_worker') THEN
        CREATE ROLE market_analytics_worker NOLOGIN;
    END IF;
END
$roles$;

GRANT USAGE ON SCHEMA public TO market_ai_reader, market_ai_logger;
GRANT SELECT ON public."Table_Catalog", public."Column_Catalog",
    public."Feature_Catalog", public."Feature_Relationship_Catalog",
    public."Tool_Catalog", public."Feature_01_Stock_Daily",
    public."Feature_02_Broker_Rolling" TO market_ai_reader;
GRANT EXECUTE ON FUNCTION public.check_analysis_data_readiness(text[]) TO market_ai_reader;
GRANT SELECT, INSERT, UPDATE ON public."Analysis_Request",
    public."Analysis_Step_Log", public."Analysis_Evidence" TO market_ai_logger;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO market_ai_logger;

-- Register all new tables before adding their physical columns to Column_Catalog.
INSERT INTO public."Table_Catalog" (
    table_name, category, definition, grain, primary_key_columns,
    source_system, source_tables, source_code_paths, update_rule,
    related_functions, documentation_status, readiness_mode
) VALUES
('Feature_Relationship_Catalog','Reference','Versioned safe-join and grain contracts between verified Feature tables.','One row per left Feature, right Feature, and version',ARRAY['left_feature_table','right_feature_table','version'],'PostgreSQL metadata',ARRAY['Feature_Catalog'],ARRAY['database/migrations/20260913_009_create_market_ai_foundation.sql'],'Updated by forward-only migration when a safe Feature relationship is validated.',ARRAY[]::text[],'VERIFIED','REFERENCE_STATE'),
('Tool_Catalog','Reference','Versioned generic AI tool metadata, activation state, schemas, and advertised operational ceilings.','One row per tool and version',ARRAY['tool_name','version'],'PostgreSQL metadata',ARRAY['Feature_Catalog','Feature_Relationship_Catalog'],ARRAY['database/migrations/20260913_009_create_market_ai_foundation.sql'],'Updated with backend/worker releases; runtime configuration is the enforcement authority.',ARRAY[]::text[],'VERIFIED','REFERENCE_STATE'),
('Analysis_Request','System','Durable AI analysis request lifecycle, structured result, progressive tool exposure state, and token usage.','One row per analysis request',ARRAY['request_id'],'market-ai-backend',ARRAY['Tool_Catalog','Feature_Catalog'],ARRAY['database/migrations/20260913_009_create_market_ai_foundation.sql','apps/market-ai-backend'],'Written and leased by market-ai-backend.',ARRAY[]::text[],'VERIFIED','NOT_APPLICABLE'),
('Analysis_Step_Log','System','Audit record for every query, tool, compaction, or analytical step in an AI request.','One row per request step',ARRAY['step_id'],'market-ai-backend',ARRAY['Analysis_Request','Tool_Catalog'],ARRAY['database/migrations/20260913_009_create_market_ai_foundation.sql','apps/market-ai-backend'],'Appended for each analysis step; large raw results and secrets are never stored.',ARRAY[]::text[],'VERIFIED','NOT_APPLICABLE'),
('Analysis_Evidence','System','Compact reproducible evidence supporting material AI analysis claims.','One row per evidence item',ARRAY['evidence_id'],'market-ai-backend',ARRAY['Analysis_Request','Analysis_Step_Log'],ARRAY['database/migrations/20260913_009_create_market_ai_foundation.sql','apps/market-ai-backend'],'Appended by evidence tools, with at most 25 items per request enforced by the backend.',ARRAY[]::text[],'VERIFIED','NOT_APPLICABLE');

UPDATE public."Table_Catalog"
SET source_code_paths = array_append(source_code_paths,
        'database/migrations/20260913_009_create_market_ai_foundation.sql'),
    related_functions = CASE WHEN table_name IN ('Feature_01_Stock_Daily','Feature_02_Broker_Rolling')
        THEN array_append(related_functions, 'check_analysis_data_readiness(text[])')
        ELSE related_functions END
WHERE table_name IN ('Table_Catalog','Feature_Catalog','Feature_01_Stock_Daily','Feature_02_Broker_Rolling');

-- Add missing catalog rows for newly created/altered columns. The sync utility
-- enriches physical facts later; these descriptions are evidence-based here.
INSERT INTO public."Column_Catalog" (
    table_schema, table_name, column_name, ordinal_position, data_type,
    is_nullable, default_expression, is_primary_key, definition,
    source_column_or_expression, unit, null_rule, source_code_paths,
    documentation_status
)
SELECT c.table_schema, c.table_name, c.column_name, c.ordinal_position,
       c.data_type, c.is_nullable = 'YES', c.column_default,
       EXISTS (
           SELECT 1 FROM information_schema.table_constraints tc
           JOIN information_schema.key_column_usage kcu
             ON kcu.constraint_schema = tc.constraint_schema
            AND kcu.constraint_name = tc.constraint_name
            AND kcu.table_schema = tc.table_schema
            AND kcu.table_name = tc.table_name
           WHERE tc.constraint_type = 'PRIMARY KEY'
             AND tc.table_schema = c.table_schema AND tc.table_name = c.table_name
             AND kcu.column_name = c.column_name
       ),
       coalesce(pg_catalog.col_description(pc.oid, pa.attnum),
                'Physical ' || c.column_name || ' field for ' || c.table_name || '.'),
       'Defined by database/migrations/20260913_009_create_market_ai_foundation.sql',
       NULL,
       CASE WHEN c.is_nullable = 'NO' THEN 'Never NULL.' ELSE 'May be NULL when not applicable or not yet available.' END,
       ARRAY['database/migrations/20260913_009_create_market_ai_foundation.sql'],
       'VERIFIED'
FROM information_schema.columns c
JOIN public."Table_Catalog" tc
  ON tc.table_schema = c.table_schema AND tc.table_name = c.table_name
JOIN pg_catalog.pg_class pc ON pc.oid = format('%I.%I', c.table_schema, c.table_name)::regclass
JOIN pg_catalog.pg_attribute pa ON pa.attrelid = pc.oid AND pa.attname = c.column_name
LEFT JOIN public."Column_Catalog" existing
  ON existing.table_schema = c.table_schema AND existing.table_name = c.table_name
 AND existing.column_name = c.column_name
WHERE existing.column_name IS NULL;

DO $validate$
DECLARE
    unregistered integer;
    missing_columns integer;
    active_feature_count integer;
    active_tool_count integer;
BEGIN
    SELECT count(*) INTO unregistered
    FROM information_schema.tables t
    WHERE t.table_schema = 'public' AND t.table_type = 'BASE TABLE'
      AND t.table_name NOT IN ('Database_Table_Status','Table_Catalog','Column_Catalog')
      AND NOT EXISTS (SELECT 1 FROM public."Table_Catalog" c
                      WHERE c.table_schema=t.table_schema AND c.table_name=t.table_name);
    SELECT count(*) INTO missing_columns
    FROM information_schema.columns c
    JOIN public."Table_Catalog" t
      ON t.table_schema=c.table_schema AND t.table_name=c.table_name
    WHERE NOT EXISTS (SELECT 1 FROM public."Column_Catalog" cc
                      WHERE cc.table_schema=c.table_schema AND cc.table_name=c.table_name
                        AND cc.column_name=c.column_name);
    SELECT count(*) INTO active_feature_count FROM public."Feature_Catalog" WHERE is_active;
    SELECT count(*) INTO active_tool_count FROM public."Tool_Catalog" WHERE is_active;
    IF unregistered <> 0 OR missing_columns <> 0
       OR active_feature_count <> 67 OR active_tool_count <> 17 THEN
        RAISE EXCEPTION 'Foundation validation failed: unregistered %, missing columns %, active features %, active tools %',
            unregistered, missing_columns, active_feature_count, active_tool_count;
    END IF;
END
$validate$;

COMMIT;
