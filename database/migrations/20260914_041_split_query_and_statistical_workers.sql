-- Release 2 hardening: deterministic routing and physically separate query/statistical workers.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '5min';

DO $preflight$
BEGIN
    IF to_regclass('public."Analytics_Job"') IS NULL
       OR to_regclass('public."Tool_Catalog"') IS NULL
       OR to_regclass('public."Column_Catalog"') IS NULL THEN
        RAISE EXCEPTION 'Migration 040 and Market AI catalogs are required';
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='Analytics_Job'
          AND column_name='execution_class'
    ) THEN
        RAISE EXCEPTION 'Analytics_Job.execution_class already exists';
    END IF;
END
$preflight$;

ALTER TABLE public."Analytics_Job"
    ADD COLUMN execution_class text NOT NULL DEFAULT 'STATISTICAL_VALIDATION';

ALTER TABLE public."Analytics_Job"
    ADD CONSTRAINT "Analytics_Job_execution_class_check"
        CHECK (execution_class IN ('QUERY_SANDBOX','STATISTICAL_VALIDATION'));

ALTER TABLE public."Analytics_Job"
    DROP CONSTRAINT "Analytics_Job_method_check";
ALTER TABLE public."Analytics_Job"
    ADD CONSTRAINT "Analytics_Job_method_check" CHECK (
        (execution_class='QUERY_SANDBOX' AND method='SAFE_DUCKDB_SQL')
        OR
        (execution_class='STATISTICAL_VALIDATION' AND method IN (
            'DESCRIPTIVE_STATISTICS_SQL','EVENT_STUDY_SQL','BACKTEST_SQL',
            'SIGNIFICANCE_TEST_SQL','REGRESSION_SQL','CLUSTERING_SQL','HMM_SQL',
            'PREDICTIVE_VALIDATION_SQL','SAFE_DUCKDB_SQL'
        ))
    );

DROP INDEX public."Analytics_Job_claim_idx";
CREATE INDEX "Analytics_Job_claim_idx"
    ON public."Analytics_Job" (execution_class,status,created_at,lease_expires_at)
    WHERE status IN ('PENDING','PROCESSING');

ALTER TABLE public."Tool_Catalog"
    DROP CONSTRAINT "Tool_Catalog_execution_check";
ALTER TABLE public."Tool_Catalog"
    ADD CONSTRAINT "Tool_Catalog_execution_check" CHECK (
        execution_type IN ('BACKEND','ANALYTICS_WORKER','QUERY_SANDBOX',
                           'STATISTICAL_WORKER','ORCHESTRATOR')
    );

UPDATE public."Tool_Catalog"
SET is_active=false,updated_at=CURRENT_TIMESTAMP
WHERE tool_name='run_analytics_job' AND is_active;

INSERT INTO public."Tool_Catalog" (
    tool_name,tool_family,tool_type,purpose,input_schema,output_schema,
    execution_type,handler_name,default_output_rows,max_output_rows,max_input_rows,
    max_tickers,max_date_range_days,max_estimated_rows,timeout_seconds,
    max_output_bytes,max_llm_result_rows,max_llm_result_bytes,max_llm_result_tokens,
    requires_analytics_worker,requires_feature_catalog,requires_data_readiness,
    tool_specific_limits,version,is_active
) VALUES
(
    'route_analysis','META','ORCHESTRATION',
    'Declare required operation classes once. The backend deterministically selects built-in tools, query sandbox, or statistical validation; this prevents prompt-keyword routing and unnecessary worker use.',
    '{"type":"object","additionalProperties":false}'::jsonb,'{"type":"object"}'::jsonb,
    'ORCHESTRATOR','route_analysis',1,1,NULL,NULL,NULL,NULL,5,
    16384,20,16384,1000,false,false,false,
    '{"priority":["STATISTICAL_VALIDATION","QUERY_SANDBOX","EXISTING_TOOL"],"first_call":true}'::jsonb,
    'v1',true
),
(
    'run_query_sandbox','HISTORICAL_VALIDATION','GENERIC_QUERY_SANDBOX',
    'Run a bounded custom join, window, or descriptive transformation over immutable catalog-approved raw/Feature snapshots. Not for inferential or predictive claims.',
    '{"type":"object","additionalProperties":false}'::jsonb,'{"type":"object"}'::jsonb,
    'QUERY_SANDBOX','run_query_sandbox',100,500,100000,100,7305,3000000,90,
    262144,200,131072,4000,true,true,true,
    '{"max_datasets":6,"input_format":"JSON_GZIP","raw_tables_allowed":true,"worker_database_credentials":false,"sql_policy":"single SELECT/WITH; no external access, DDL, DML, file or network readers"}'::jsonb,
    'v1',true
),
(
    'run_statistical_validation','ADVANCED','STATISTICAL_VALIDATION',
    'Run an explicitly classified event study, backtest, significance test, regression, clustering, HMM, descriptive-statistics, or predictive-validation job over immutable bounded catalog-approved raw/Feature snapshots.',
    '{"type":"object","additionalProperties":false}'::jsonb,'{"type":"object"}'::jsonb,
    'STATISTICAL_WORKER','run_statistical_validation',100,1000,500000,1000,7305,10000000,300,
    524288,200,131072,4000,true,true,true,
    '{"max_datasets":8,"input_format":"JSON_GZIP","allowlisted_methods":["DESCRIPTIVE_STATISTICS","EVENT_STUDY","BACKTEST","SIGNIFICANCE_TEST","REGRESSION","CLUSTERING","HMM","PREDICTIVE_VALIDATION"],"worker_database_credentials":false}'::jsonb,
    'v1',true
);

COMMENT ON COLUMN public."Analytics_Job".execution_class IS
    'Physical worker boundary. QUERY_SANDBOX and STATISTICAL_VALIDATION use different credentials and claim endpoints.';
COMMENT ON TABLE public."Analytics_Dataset_Snapshot" IS
    'Metadata for immutable private bounded raw/Feature analytical input objects. Only the backend reads PostgreSQL; worker input objects expire quickly.';
COMMENT ON COLUMN public."Analytics_Dataset_Snapshot".source_spec_json IS
    'Catalog-validated structured raw/Feature reads created by the backend; never model-written PostgreSQL SQL.';
COMMENT ON TABLE public."Analytics_Job" IS
    'Durable isolated-worker queue. execution_class prevents a query-sandbox credential from claiming statistical jobs and vice versa.';

INSERT INTO public."Column_Catalog" (
    table_schema,table_name,column_name,ordinal_position,data_type,is_nullable,
    default_expression,is_primary_key,definition,source_column_or_expression,
    unit,null_rule,source_code_paths,documentation_status
) VALUES (
    'public','Analytics_Job','execution_class',
    (SELECT ordinal_position FROM information_schema.columns
     WHERE table_schema='public' AND table_name='Analytics_Job' AND column_name='execution_class'),
    'text',false,'''STATISTICAL_VALIDATION''::text',false,
    'Physical execution boundary selecting the separately authenticated query sandbox or statistical validation worker.',
    'Assigned deterministically by market-ai-backend routing','execution class','Never NULL.',
    ARRAY['database/migrations/20260914_041_split_query_and_statistical_workers.sql',
          'apps/market-ai-backend/app/main.py','apps/market-ai-backend/app/tools.py'],
    'VERIFIED'
);

UPDATE public."Table_Catalog"
SET definition='Metadata and retention state for immutable bounded raw or Feature analytical input snapshots stored in a private Railway bucket.',
    source_tables=ARRAY['Analysis_Request','Table_Catalog','Column_Catalog','Feature_Catalog'],
    source_code_paths=array_append(source_code_paths,
        'database/migrations/20260914_041_split_query_and_statistical_workers.sql'),
    updated_at=CURRENT_TIMESTAMP
WHERE table_name='Analytics_Dataset_Snapshot';

UPDATE public."Table_Catalog"
SET definition='Durable queue, lease, resource contract, result, and failure audit for separately authenticated query-sandbox and statistical-validation workers.',
    source_system='market-ai-backend, market-query-sandbox, and market-analytics-worker',
    source_code_paths=array_append(source_code_paths,
        'database/migrations/20260914_041_split_query_and_statistical_workers.sql'),
    updated_at=CURRENT_TIMESTAMP
WHERE table_name='Analytics_Job';

DO $roles$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='market_query_sandbox') THEN
        CREATE ROLE market_query_sandbox NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='market_statistical_worker') THEN
        CREATE ROLE market_statistical_worker NOLOGIN;
    END IF;
END
$roles$;

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM market_query_sandbox;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM market_statistical_worker;

DO $validate$
BEGIN
    IF (SELECT count(*) FROM public."Tool_Catalog"
        WHERE tool_name IN ('route_analysis','run_query_sandbox','run_statistical_validation')
          AND version='v1' AND is_active) <> 3 THEN
        RAISE EXCEPTION 'Three-path tool activation failed';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public."Column_Catalog"
        WHERE table_name='Analytics_Job' AND column_name='execution_class'
          AND documentation_status='VERIFIED'
    ) THEN
        RAISE EXCEPTION 'Analytics_Job.execution_class catalog registration failed';
    END IF;
END
$validate$;

COMMIT;
