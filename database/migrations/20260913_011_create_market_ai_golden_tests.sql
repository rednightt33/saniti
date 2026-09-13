-- Permanent analytical regression-test registry and result history.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '10min';

DO $preflight$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'Analysis_Request'
          AND column_name = 'version_snapshot'
    ) THEN
        RAISE EXCEPTION 'Historical-integrity migration 010 is required';
    END IF;
    IF to_regclass('public."Golden_Analysis_Test"') IS NOT NULL THEN
        RAISE EXCEPTION 'Golden test tables already exist';
    END IF;
END
$preflight$;

CREATE TABLE public."Golden_Analysis_Test" (
    test_id text NOT NULL,
    version text NOT NULL DEFAULT 'v1',
    category text NOT NULL,
    question text NOT NULL,
    required_capabilities text[] NOT NULL DEFAULT '{}',
    fixed_start_date date,
    fixed_end_date date,
    expected_features text[] NOT NULL DEFAULT '{}',
    expected_tools text[] NOT NULL DEFAULT '{}',
    expected_conditions jsonb NOT NULL DEFAULT '{}'::jsonb,
    tolerance jsonb NOT NULL DEFAULT '{}'::jsonb,
    expected_warnings text[] NOT NULL DEFAULT '{}',
    expected_status text NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Golden_Analysis_Test_pkey" PRIMARY KEY (test_id, version),
    CONSTRAINT "Golden_Analysis_Test_version_check" CHECK (version ~ '^v[1-9][0-9]*$'),
    CONSTRAINT "Golden_Analysis_Test_category_check" CHECK (category IN (
        'RETRIEVAL','BROKER_ACCUMULATION','CROSS_FEATURE','PERIOD_COMPARISON',
        'READINESS','EVENT_STUDY','SIGNAL_VALIDATION','BACKTEST','SAFETY',
        'DATA_QUALITY','POINT_IN_TIME','NO_LOOKAHEAD','REPRODUCIBILITY',
        'TOKEN_CONTEXT'
    )),
    CONSTRAINT "Golden_Analysis_Test_dates_check"
        CHECK (fixed_start_date IS NULL OR fixed_end_date IS NULL
               OR fixed_end_date >= fixed_start_date),
    CONSTRAINT "Golden_Analysis_Test_status_check"
        CHECK (expected_status IN ('SUCCESS','WARNING','REJECTED')),
    CONSTRAINT "Golden_Analysis_Test_json_check"
        CHECK (jsonb_typeof(expected_conditions) = 'object'
               AND jsonb_typeof(tolerance) = 'object'),
    CONSTRAINT "Golden_Analysis_Test_required_text_check"
        CHECK (btrim(test_id) <> '' AND btrim(category) <> '' AND btrim(question) <> '')
);

CREATE UNIQUE INDEX "Golden_Analysis_Test_one_active_version_idx"
    ON public."Golden_Analysis_Test" (test_id) WHERE is_active;

CREATE TRIGGER "Golden_Analysis_Test_set_updated_at"
BEFORE UPDATE ON public."Golden_Analysis_Test"
FOR EACH ROW EXECUTE FUNCTION public.set_database_catalog_updated_at();

CREATE TABLE public."Golden_Analysis_Test_Run" (
    run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    release_version text NOT NULL,
    model_provider text NOT NULL,
    model_id text NOT NULL,
    reasoning_effort text,
    orchestrator_version text NOT NULL,
    orchestrator_prompt_version text NOT NULL,
    version_snapshot jsonb NOT NULL,
    status text NOT NULL DEFAULT 'PENDING',
    tests_total integer NOT NULL DEFAULT 0,
    tests_passed integer NOT NULL DEFAULT 0,
    tests_failed integer NOT NULL DEFAULT 0,
    cumulative_input_tokens integer NOT NULL DEFAULT 0,
    cumulative_output_tokens integer NOT NULL DEFAULT 0,
    cumulative_total_tokens integer NOT NULL DEFAULT 0,
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Golden_Analysis_Test_Run_status_check"
        CHECK (status IN ('PENDING','RUNNING','PASS','FAIL','ERROR')),
    CONSTRAINT "Golden_Analysis_Test_Run_counts_check"
        CHECK (tests_total >= 0 AND tests_passed >= 0 AND tests_failed >= 0
               AND tests_passed + tests_failed <= tests_total
               AND cumulative_input_tokens >= 0
               AND cumulative_output_tokens >= 0
               AND cumulative_total_tokens >= 0),
    CONSTRAINT "Golden_Analysis_Test_Run_snapshot_check"
        CHECK (jsonb_typeof(version_snapshot) = 'object'),
    CONSTRAINT "Golden_Analysis_Test_Run_times_check"
        CHECK (completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at)
);

CREATE INDEX "Golden_Analysis_Test_Run_status_created_idx"
    ON public."Golden_Analysis_Test_Run" (status, created_at DESC);

CREATE TABLE public."Golden_Analysis_Test_Result" (
    run_id uuid NOT NULL REFERENCES public."Golden_Analysis_Test_Run" (run_id) ON DELETE CASCADE,
    test_id text NOT NULL,
    test_version text NOT NULL,
    request_id uuid REFERENCES public."Analysis_Request" (request_id) ON DELETE SET NULL,
    status text NOT NULL,
    observed_metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
    deviation jsonb NOT NULL DEFAULT '{}'::jsonb,
    observed_warnings text[] NOT NULL DEFAULT '{}',
    evidence_ids uuid[] NOT NULL DEFAULT '{}',
    methodology_checks jsonb NOT NULL DEFAULT '{}'::jsonb,
    input_tokens integer NOT NULL DEFAULT 0,
    output_tokens integer NOT NULL DEFAULT 0,
    total_tokens integer NOT NULL DEFAULT 0,
    duration_ms integer,
    failure_reason text,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Golden_Analysis_Test_Result_pkey"
        PRIMARY KEY (run_id, test_id, test_version),
    CONSTRAINT "Golden_Analysis_Test_Result_test_fkey"
        FOREIGN KEY (test_id, test_version)
        REFERENCES public."Golden_Analysis_Test" (test_id, version),
    CONSTRAINT "Golden_Analysis_Test_Result_status_check"
        CHECK (status IN ('PASS','FAIL','ERROR','SKIPPED')),
    CONSTRAINT "Golden_Analysis_Test_Result_metrics_check"
        CHECK (jsonb_typeof(observed_metrics) = 'object'
               AND jsonb_typeof(deviation) = 'object'
               AND jsonb_typeof(methodology_checks) = 'object'),
    CONSTRAINT "Golden_Analysis_Test_Result_usage_check"
        CHECK (input_tokens >= 0 AND output_tokens >= 0 AND total_tokens >= 0
               AND (duration_ms IS NULL OR duration_ms >= 0))
);

CREATE INDEX "Golden_Analysis_Test_Result_test_idx"
    ON public."Golden_Analysis_Test_Result" (test_id, test_version, created_at DESC);

COMMENT ON TABLE public."Golden_Analysis_Test" IS
    'Versioned analytical correctness and safety expectations; evaluation compares data and methodology rather than exact prose.';
COMMENT ON TABLE public."Golden_Analysis_Test_Run" IS
    'One complete regression-suite execution with immutable release/model/prompt/tool/Feature version context.';
COMMENT ON TABLE public."Golden_Analysis_Test_Result" IS
    'Per-test observed metrics, warnings, methodology checks, evidence and token usage.';

INSERT INTO public."Table_Catalog" (
    table_name, category, definition, grain, primary_key_columns,
    source_system, source_tables, source_code_paths, update_rule,
    related_functions, documentation_status, readiness_mode,
    availability_rule, point_in_time_status, historical_metadata_method
) VALUES
(
    'Golden_Analysis_Test','System',
    'Versioned analytical regression-test definitions with reproducible conditions and tolerances.',
    'One row per test ID and test version',ARRAY['test_id','version'],
    'Forward-only database migrations',ARRAY['Feature_Catalog','Tool_Catalog'],
    ARRAY['database/migrations/20260913_011_create_market_ai_golden_tests.sql'],
    'Definitions are added or versioned by forward-only migrations; material expectations are never overwritten.',
    ARRAY[]::text[],'VERIFIED','NOT_APPLICABLE','Not applicable.','NOT_APPLICABLE',NULL
),
(
    'Golden_Analysis_Test_Run','System',
    'Historical execution record for one complete golden analytical regression suite.',
    'One row per golden-suite run',ARRAY['run_id'],
    'market-ai golden-test runner',ARRAY['Golden_Analysis_Test'],
    ARRAY['database/migrations/20260913_011_create_market_ai_golden_tests.sql','apps/market-ai-backend'],
    'Inserted at suite start and finalized after all selected tests reach terminal status.',
    ARRAY[]::text[],'VERIFIED','NOT_APPLICABLE','Not applicable.','NOT_APPLICABLE',NULL
),
(
    'Golden_Analysis_Test_Result','System',
    'Per-test correctness, methodology, evidence, warning, latency and token outcome.',
    'One row per golden run, test ID and test version',ARRAY['run_id','test_id','test_version'],
    'market-ai golden-test runner',ARRAY['Golden_Analysis_Test_Run','Golden_Analysis_Test','Analysis_Request'],
    ARRAY['database/migrations/20260913_011_create_market_ai_golden_tests.sql','apps/market-ai-backend'],
    'Inserted after each golden test and retained for regression trend comparison.',
    ARRAY[]::text[],'VERIFIED','NOT_APPLICABLE','Not applicable.','NOT_APPLICABLE',NULL
);

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
            AND kcu.table_schema = tc.table_schema AND kcu.table_name = tc.table_name
           WHERE tc.constraint_type = 'PRIMARY KEY'
             AND tc.table_schema = c.table_schema AND tc.table_name = c.table_name
             AND kcu.column_name = c.column_name
       ),
       CASE c.table_name
           WHEN 'Golden_Analysis_Test' THEN
               'Versioned golden-test definition field: ' || c.column_name || '.'
           WHEN 'Golden_Analysis_Test_Run' THEN
               'Golden-suite execution field: ' || c.column_name || '.'
           ELSE 'Per-golden-test result field: ' || c.column_name || '.'
       END,
       'Defined by database/migrations/20260913_011_create_market_ai_golden_tests.sql',
       CASE WHEN c.column_name LIKE '%tokens' THEN 'Tokens'
            WHEN c.column_name = 'duration_ms' THEN 'Milliseconds' ELSE NULL END,
       CASE WHEN c.is_nullable = 'NO' THEN 'Never NULL.'
            ELSE 'NULL when not applicable or not available for this test state.' END,
       ARRAY['database/migrations/20260913_011_create_market_ai_golden_tests.sql'],
       'VERIFIED'
FROM information_schema.columns c
JOIN public."Table_Catalog" tc
  ON tc.table_schema = c.table_schema AND tc.table_name = c.table_name
WHERE c.table_schema = 'public'
  AND c.table_name IN ('Golden_Analysis_Test','Golden_Analysis_Test_Run',
                       'Golden_Analysis_Test_Result');

GRANT SELECT ON public."Golden_Analysis_Test" TO market_ai_reader, market_ai_logger;
GRANT SELECT, INSERT, UPDATE ON public."Golden_Analysis_Test_Run",
    public."Golden_Analysis_Test_Result" TO market_ai_logger;

DO $validate$
DECLARE
    physical_columns integer;
    catalog_columns integer;
BEGIN
    SELECT count(*) INTO physical_columns
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name IN ('Golden_Analysis_Test','Golden_Analysis_Test_Run',
                         'Golden_Analysis_Test_Result');
    SELECT count(*) INTO catalog_columns
    FROM public."Column_Catalog"
    WHERE table_schema = 'public'
      AND table_name IN ('Golden_Analysis_Test','Golden_Analysis_Test_Run',
                         'Golden_Analysis_Test_Result');
    IF physical_columns <> catalog_columns OR physical_columns <> 50 THEN
        RAISE EXCEPTION 'Golden catalog coverage mismatch: physical %, catalog %',
            physical_columns, catalog_columns;
    END IF;
END
$validate$;

COMMIT;
