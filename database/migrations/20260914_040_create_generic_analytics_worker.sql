-- Release 2: immutable bounded datasets and one generic isolated analytics worker.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '10min';

DO $preflight$
BEGIN
    IF to_regclass('public."Analytics_Job"') IS NOT NULL
       OR to_regclass('public."Analytics_Dataset_Snapshot"') IS NOT NULL THEN
        RAISE EXCEPTION 'Generic analytics worker tables already exist';
    END IF;
    IF to_regclass('public."Analysis_Request"') IS NULL
       OR to_regclass('public."Tool_Catalog"') IS NULL THEN
        RAISE EXCEPTION 'Market AI foundation is required';
    END IF;
END
$preflight$;

CREATE TABLE public."Analytics_Dataset_Snapshot" (
    snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id uuid NOT NULL REFERENCES public."Analysis_Request"(request_id) ON DELETE CASCADE,
    object_key text NOT NULL UNIQUE,
    content_sha256 text NOT NULL UNIQUE,
    format text NOT NULL,
    row_count integer NOT NULL,
    column_count integer NOT NULL,
    byte_count integer NOT NULL,
    compressed_byte_count integer NOT NULL,
    schema_json jsonb NOT NULL,
    source_spec_json jsonb NOT NULL,
    source_tables text[] NOT NULL,
    query_hashes text[] NOT NULL,
    analysis_ready_date date,
    status text NOT NULL DEFAULT 'AVAILABLE',
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at timestamptz NOT NULL,
    deleted_at timestamptz,
    CONSTRAINT "Analytics_Dataset_Snapshot_format_check" CHECK (format='JSON_GZIP'),
    CONSTRAINT "Analytics_Dataset_Snapshot_status_check" CHECK (status IN ('AVAILABLE','EXPIRED','DELETED')),
    CONSTRAINT "Analytics_Dataset_Snapshot_counts_check" CHECK (
        row_count > 0 AND column_count > 0 AND byte_count > 0 AND compressed_byte_count > 0),
    CONSTRAINT "Analytics_Dataset_Snapshot_hash_check" CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT "Analytics_Dataset_Snapshot_json_check" CHECK (
        jsonb_typeof(schema_json)='object' AND jsonb_typeof(source_spec_json)='array'),
    CONSTRAINT "Analytics_Dataset_Snapshot_expiry_check" CHECK (expires_at > created_at)
);

CREATE INDEX "Analytics_Dataset_Snapshot_expiry_idx"
    ON public."Analytics_Dataset_Snapshot" (expires_at, snapshot_id)
    WHERE status='AVAILABLE';
CREATE INDEX "Analytics_Dataset_Snapshot_request_idx"
    ON public."Analytics_Dataset_Snapshot" (request_id, created_at DESC);

CREATE TABLE public."Analytics_Job" (
    job_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id uuid NOT NULL REFERENCES public."Analysis_Request"(request_id) ON DELETE CASCADE,
    snapshot_id uuid NOT NULL REFERENCES public."Analytics_Dataset_Snapshot"(snapshot_id) ON DELETE RESTRICT,
    job_label text NOT NULL,
    purpose text NOT NULL,
    method text NOT NULL,
    analysis_spec_json jsonb NOT NULL,
    status text NOT NULL DEFAULT 'PENDING',
    attempt_count smallint NOT NULL DEFAULT 0,
    max_attempts smallint NOT NULL DEFAULT 3,
    worker_id text,
    lease_token uuid,
    lease_expires_at timestamptz,
    max_runtime_seconds integer NOT NULL,
    max_memory_mb integer NOT NULL,
    max_result_rows integer NOT NULL,
    max_result_bytes integer NOT NULL,
    result_json jsonb,
    evidence_id uuid REFERENCES public."Analysis_Evidence"(evidence_id) ON DELETE SET NULL,
    error_class text,
    error_message text,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at timestamptz,
    completed_at timestamptz,
    result_expires_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Analytics_Job_request_label_key" UNIQUE (request_id,job_label),
    CONSTRAINT "Analytics_Job_method_check" CHECK (method='SAFE_DUCKDB_SQL'),
    CONSTRAINT "Analytics_Job_status_check" CHECK (status IN ('PENDING','PROCESSING','SUCCESS','FAILED','CANCELLED')),
    CONSTRAINT "Analytics_Job_attempts_check" CHECK (attempt_count >= 0 AND max_attempts BETWEEN 1 AND 10),
    CONSTRAINT "Analytics_Job_limits_check" CHECK (
        max_runtime_seconds > 0 AND max_memory_mb > 0 AND max_result_rows > 0 AND max_result_bytes > 0),
    CONSTRAINT "Analytics_Job_spec_check" CHECK (jsonb_typeof(analysis_spec_json)='object'),
    CONSTRAINT "Analytics_Job_result_check" CHECK (result_json IS NULL OR jsonb_typeof(result_json)='object'),
    CONSTRAINT "Analytics_Job_lease_check" CHECK (
        (status='PROCESSING' AND worker_id IS NOT NULL AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)
        OR status <> 'PROCESSING'),
    CONSTRAINT "Analytics_Job_terminal_check" CHECK (
        (status IN ('SUCCESS','FAILED','CANCELLED') AND completed_at IS NOT NULL)
        OR status IN ('PENDING','PROCESSING'))
);

CREATE INDEX "Analytics_Job_claim_idx"
    ON public."Analytics_Job" (status, created_at, lease_expires_at)
    WHERE status IN ('PENDING','PROCESSING');
CREATE INDEX "Analytics_Job_request_idx"
    ON public."Analytics_Job" (request_id, created_at DESC);

CREATE TRIGGER "Analytics_Job_set_updated_at"
BEFORE UPDATE ON public."Analytics_Job"
FOR EACH ROW EXECUTE FUNCTION public.set_database_catalog_updated_at();

COMMENT ON TABLE public."Analytics_Dataset_Snapshot" IS
    'Metadata for an immutable, private, bounded Feature-only analytical input object; raw payload is stored outside PostgreSQL and expires quickly.';
COMMENT ON TABLE public."Analytics_Job" IS
    'Durable lease queue and compact result for generic isolated analytical SQL; the worker has no PostgreSQL credentials.';
COMMENT ON COLUMN public."Analytics_Dataset_Snapshot".content_sha256 IS
    'SHA-256 of the exact compressed object; the worker verifies it before execution.';
COMMENT ON COLUMN public."Analytics_Dataset_Snapshot".source_spec_json IS
    'Catalog-validated structured Feature query specifications; never model-written PostgreSQL SQL.';
COMMENT ON COLUMN public."Analytics_Job".analysis_spec_json IS
    'Worker computation specification. v1 contains one allowlisted SELECT/WITH DuckDB statement over snapshot dataset names only.';
COMMENT ON COLUMN public."Analytics_Job".result_json IS
    'Compact bounded analytical output; the full snapshot is never copied here or sent to the LLM.';

INSERT INTO public."Table_Catalog" (
    table_name,category,definition,grain,primary_key_columns,source_system,
    source_tables,source_code_paths,update_rule,related_functions,
    documentation_status,readiness_mode
) VALUES
('Analytics_Dataset_Snapshot','System',
 'Metadata and retention state for immutable bounded analytical input snapshots stored in a private Railway bucket.',
 'One row per immutable analytical dataset snapshot',ARRAY['snapshot_id'],
 'market-ai-backend',ARRAY['Analysis_Request','Feature_Catalog'],
 ARRAY['database/migrations/20260914_040_create_generic_analytics_worker.sql','apps/market-ai-backend/app/tools.py'],
 'Created only after catalog, row, byte and query-plan validation; expires within the configured short retention window.',
 ARRAY[]::text[],'VERIFIED','NOT_APPLICABLE'),
('Analytics_Job','System',
 'Durable generic analytics queue, lease, bounded resource contract, result and failure audit.',
 'One row per generic analytics job',ARRAY['job_id'],
 'market-ai-backend and market-analytics-worker',ARRAY['Analytics_Dataset_Snapshot','Analysis_Request'],
 ARRAY['database/migrations/20260914_040_create_generic_analytics_worker.sql','apps/market-ai-backend','apps/market-analytics-worker'],
 'Backend submits idempotently by request/job label; isolated worker leases and completes or fails the job.',
 ARRAY[]::text[],'VERIFIED','NOT_APPLICABLE');

INSERT INTO public."Column_Catalog" (
    table_schema,table_name,column_name,ordinal_position,data_type,is_nullable,
    default_expression,is_primary_key,definition,source_column_or_expression,
    unit,null_rule,source_code_paths,documentation_status
)
SELECT c.table_schema,c.table_name,c.column_name,c.ordinal_position,c.data_type,
       c.is_nullable='YES',c.column_default,
       EXISTS (
         SELECT 1 FROM information_schema.table_constraints tc
         JOIN information_schema.key_column_usage kcu USING (constraint_catalog,constraint_schema,constraint_name,table_catalog,table_schema,table_name)
         WHERE tc.constraint_type='PRIMARY KEY' AND tc.table_schema=c.table_schema
           AND tc.table_name=c.table_name AND kcu.column_name=c.column_name),
       CASE c.column_name
         WHEN 'snapshot_id' THEN 'Immutable snapshot metadata identifier.'
         WHEN 'request_id' THEN 'Analysis request that owns this snapshot or job.'
         WHEN 'object_key' THEN 'Private bucket path; never returned to the model.'
         WHEN 'content_sha256' THEN 'Checksum of exact compressed input bytes.'
         WHEN 'format' THEN 'Serialized snapshot format and compression contract.'
         WHEN 'row_count' THEN 'Total observations across all snapshot datasets.'
         WHEN 'column_count' THEN 'Sum of selected columns across snapshot datasets.'
         WHEN 'byte_count' THEN 'Uncompressed serialized input size in bytes.'
         WHEN 'compressed_byte_count' THEN 'Private object size in bytes.'
         WHEN 'schema_json' THEN 'Dataset names and their exact ordered column names.'
         WHEN 'source_spec_json' THEN 'Structured catalog-validated Feature query requests used to build the snapshot.'
         WHEN 'source_tables' THEN 'Exact Feature tables contributing observations.'
         WHEN 'query_hashes' THEN 'Reproducible hashes of controlled PostgreSQL reads.'
         WHEN 'analysis_ready_date' THEN 'Common safe source date supplied for this analysis.'
         WHEN 'status' THEN 'Current lifecycle state under the table-specific status constraint.'
         WHEN 'expires_at' THEN 'Deadline after which the private input object must be removed.'
         WHEN 'deleted_at' THEN 'Time the private input object was confirmed deleted.'
         WHEN 'job_id' THEN 'Generic analytics job identifier.'
         WHEN 'job_label' THEN 'Stable per-request idempotency label chosen for one analytical hypothesis.'
         WHEN 'purpose' THEN 'Human-readable analytical question addressed by the job.'
         WHEN 'method' THEN 'Versioned safe execution surface; v1 is SAFE_DUCKDB_SQL.'
         WHEN 'analysis_spec_json' THEN 'Bounded worker computation over named snapshot datasets.'
         WHEN 'attempt_count' THEN 'Number of successful worker lease claims.'
         WHEN 'max_attempts' THEN 'Retry ceiling after expired worker leases.'
         WHEN 'worker_id' THEN 'Ephemeral identifier of the worker holding the lease.'
         WHEN 'lease_token' THEN 'Random token required to complete or fail the current lease.'
         WHEN 'lease_expires_at' THEN 'Expiry of the current worker lease.'
         WHEN 'max_runtime_seconds' THEN 'Per-job worker execution timeout copied from configuration.'
         WHEN 'max_memory_mb' THEN 'Per-job DuckDB memory ceiling copied from configuration.'
         WHEN 'max_result_rows' THEN 'Maximum analytical result rows accepted by the backend.'
         WHEN 'max_result_bytes' THEN 'Maximum serialized analytical result bytes accepted by the backend.'
         WHEN 'result_json' THEN 'Compact successful result; never the full analytical input.'
         WHEN 'evidence_id' THEN 'Evidence record automatically created for a successful analytical job.'
         WHEN 'error_class' THEN 'Bounded machine-readable failure category.'
         WHEN 'error_message' THEN 'Bounded failure explanation without credentials or raw snapshot content.'
         WHEN 'result_expires_at' THEN 'Retention deadline for compact job result detail.'
         WHEN 'started_at' THEN 'Time of first worker lease.'
         WHEN 'completed_at' THEN 'Terminal completion, failure or cancellation time.'
         WHEN 'created_at' THEN 'Row creation time.'
         WHEN 'updated_at' THEN 'Last lifecycle update time.'
         ELSE 'Governed analytics control metadata.'
       END,
       'Defined by database/migrations/20260914_040_create_generic_analytics_worker.sql',
       CASE WHEN c.column_name LIKE '%bytes' THEN 'bytes' WHEN c.column_name LIKE '%rows' OR c.column_name LIKE '%count' THEN 'count' ELSE NULL END,
       CASE WHEN c.is_nullable='NO' THEN 'Never NULL.' ELSE 'NULL until not applicable or the corresponding lifecycle event occurs.' END,
       ARRAY['database/migrations/20260914_040_create_generic_analytics_worker.sql'],
       'VERIFIED'
FROM information_schema.columns c
WHERE c.table_schema='public'
  AND c.table_name IN ('Analytics_Dataset_Snapshot','Analytics_Job');

UPDATE public."Tool_Catalog"
SET is_active=false,updated_at=CURRENT_TIMESTAMP
WHERE requires_analytics_worker;

INSERT INTO public."Tool_Catalog" (
    tool_name,tool_family,tool_type,purpose,input_schema,output_schema,
    execution_type,handler_name,default_output_rows,max_output_rows,max_input_rows,
    max_tickers,max_date_range_days,max_estimated_rows,timeout_seconds,
    max_output_bytes,max_llm_result_rows,max_llm_result_bytes,max_llm_result_tokens,
    requires_analytics_worker,requires_feature_catalog,requires_data_readiness,
    tool_specific_limits,version,is_active
) VALUES (
    'run_analytics_job','HISTORICAL_VALIDATION','GENERIC_ANALYTICS',
    'Create one or more bounded Feature-only datasets and run one safe SELECT/WITH analytical query in the isolated worker. Use for joins, windows, forward outcomes, event studies, statistics, or niche computation; reuse job_label for idempotent polling.',
    '{"type":"object","additionalProperties":false}'::jsonb,
    '{"type":"object"}'::jsonb,
    'ANALYTICS_WORKER','run_analytics_job',100,500,50000,20,3653,2000000,150,
    262144,200,131072,4000,true,true,true,
    '{"max_datasets":4,"max_columns":30,"input_format":"JSON_GZIP","sql_policy":"single SELECT/WITH; no external access, DDL, DML, COPY, ATTACH, INSTALL, LOAD, PRAGMA or file/network readers","snapshot_retention_hours":24,"result_retention_days":90,"worker_database_credentials":false}'::jsonb,
    'v1',true
);

UPDATE public."Tool_Catalog"
SET purpose='List only active capabilities in the current or justified next tool families; do not dump the full deferred catalog.',
    updated_at=CURRENT_TIMESTAMP
WHERE tool_name='list_tools' AND is_active;

-- This Release 1 invariant is superseded by the isolated Release 2 worker gate.
UPDATE public."Golden_Analysis_Test"
SET is_active=false,updated_at=CURRENT_TIMESTAMP
WHERE test_id='R1B_014_WORKER_FAMILY_DENIAL' AND version='v1' AND is_active;

INSERT INTO public."Golden_Analysis_Test" (
    test_id,version,category,question,required_capabilities,fixed_start_date,
    fixed_end_date,expected_features,expected_tools,expected_conditions,
    tolerance,expected_warnings,expected_status,is_active
) VALUES (
    'R2_001_TELCO_BROKER_STREAK_FORWARD_10PCT','v1','EVENT_STUDY',
    'Which broker buy-streak combinations in the telecommunications sector preceded a return of at least 10% within the next 20 trading observations?',
    ARRAY['catalog-driven snapshot','forward-return window','broker combination grouping','no-look-ahead','isolated generic computation'],
    DATE '2022-01-03',DATE '2026-08-31',
    ARRAY['Feature_01_Stock_Daily','Feature_02_Broker_Rolling'],
    ARRAY['run_analytics_job'],
    '{"market_board":"Regular","minimum_buy_day_ratio_20d":0.75,"minimum_forward_return_pct":10,"forward_observations":20,"entry_rule":"close t to close t+20 descriptive outcome"}'::jsonb,
    '{"numeric_absolute":0.000001}'::jsonb,
    ARRAY['Current industry and broker classifications are not point-in-time history.'],
    'SUCCESS',true
);

GRANT SELECT,INSERT,UPDATE ON public."Analytics_Dataset_Snapshot",public."Analytics_Job"
    TO market_ai_logger;
REVOKE ALL ON public."Analytics_Dataset_Snapshot",public."Analytics_Job"
    FROM market_analytics_worker;

DO $validate$
DECLARE missing_columns integer;
BEGIN
    SELECT count(*) INTO missing_columns
    FROM information_schema.columns c
    WHERE c.table_schema='public'
      AND c.table_name IN ('Analytics_Dataset_Snapshot','Analytics_Job')
      AND NOT EXISTS (
        SELECT 1 FROM public."Column_Catalog" cc
        WHERE cc.table_schema=c.table_schema AND cc.table_name=c.table_name
          AND cc.column_name=c.column_name);
    IF missing_columns <> 0 THEN
        RAISE EXCEPTION 'Generic analytics catalog coverage missing % columns',missing_columns;
    END IF;
    IF (SELECT count(*) FROM public."Tool_Catalog"
        WHERE tool_name='run_analytics_job' AND is_active AND version='v1') <> 1 THEN
        RAISE EXCEPTION 'Generic analytics tool activation failed';
    END IF;
END
$validate$;

COMMIT;
