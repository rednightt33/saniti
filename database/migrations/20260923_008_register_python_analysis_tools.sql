-- Register the governed Python analysis tools (market-ai-orc -> market-sql-governor /
-- market-python-sandbox) in Tool_Catalog and move the six existing market-ai-orc rows to runtime
-- commit 81475ae. Like migrations 003 and 006 the rows are is_active = false so market-ai-backend
-- does not list tools it cannot execute; activation is owned by the market-ai-orc registry
-- (get_dataset_manifest with SQL_GOVERNOR_URL; the analysis tools with PY_SANDBOX_URL and a ready
-- sandbox). Input schemas are generated from the registry; advertised ceilings mirror defaults and
-- the Governor/sandbox configuration remains the enforcement layer.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

DO $preflight$
BEGIN
    IF EXISTS (SELECT 1 FROM public."Tool_Catalog"
               WHERE tool_name IN ('get_dataset_manifest', 'run_python_analysis', 'get_analysis_result')) THEN
        RAISE EXCEPTION 'A python analysis tool is already registered in Tool_Catalog';
    END IF;
    IF (SELECT count(*) FROM public."Tool_Catalog"
        WHERE tool_specific_limits->>'runtime_service' = 'market-ai-orc' AND NOT is_active
          AND tool_specific_limits->>'runtime_commit' = 'f63bebc') <> 6 THEN
        RAISE EXCEPTION 'Expected the six market-ai-orc rows at runtime_commit f63bebc (migration 006)';
    END IF;
END
$preflight$;

INSERT INTO public."Tool_Catalog" (
    tool_name, tool_family, tool_type, purpose, input_schema, output_schema,
    execution_type, handler_name, default_output_rows, max_output_rows,
    max_input_rows, max_tickers, max_date_range_days, max_estimated_rows,
    timeout_seconds, max_output_bytes, max_llm_result_rows,
    max_llm_result_bytes, max_llm_result_tokens,
    requires_analytics_worker, requires_feature_catalog, requires_data_readiness,
    tool_specific_limits, version, is_active
)
VALUES
    ('get_dataset_manifest', 'DISCOVERY', 'RETRIEVAL', 'Describe exactly what one governed dataset contains (a dataset_id from a DATASET_READY request_data result): columns and types, row count, source tables, requested versus actual date range, entities present and missing, completeness, checksum, numeric-precision warnings, and expiry. This is the extracted dataset itself, not the catalog''s coverage estimate. status is AVAILABLE, or explicitly DATASET_EXPIRED or DATASET_NOT_FOUND.', '{"additionalProperties":false,"properties":{"dataset_id":{"description":"dataset_id from a DATASET_READY result.","type":"string"}},"required":["dataset_id"],"type":"object"}'::jsonb, '{"description":"Bounded safe subset of the SQL Governor dataset manifest.","properties":{"actual_date_range":{},"byte_count":{},"checksum_sha256":{},"column_count":{},"columns":{},"completeness_status":{},"created_at":{},"dataset_id":{},"entities_present_count":{},"expires_at":{},"format":{},"message":{},"missing_entities":{},"missing_entities_count":{},"numeric_float64_columns":{},"query_id":{},"requested_scope":{},"row_count":{},"source_tables":{},"status":{},"warnings":{}},"type":"object"}'::jsonb,
     'ORCHESTRATOR', NULL, NULL, NULL, NULL, NULL, NULL, NULL, 20, 40000, NULL, 40000, NULL,
     false, false, false, '{"executor_service":"market-sql-governor","handler":"app/tools/analysis.py","list_limit":200,"registry_state":"Registered in market-ai-orc; is_active=false keeps it out of market-ai-backend tool lists.","runtime_commit":"81475ae","runtime_service":"market-ai-orc","statuses":["AVAILABLE","DATASET_EXPIRED","DATASET_NOT_FOUND","INVALID_DATASET_ID"]}'::jsonb, 'v1', false),
    ('run_python_analysis', 'ADVANCED', 'COMPUTATION', 'Run Python analysis in an isolated sandbox over 1-4 governed datasets (dataset_ids from DATASET_READY results). The code runs as a script without network, subprocess, or file access outside its inputs. Inputs: DATASETS maps each dataset_id to a local Parquet path, e.g. pd.read_parquet(DATASETS[id]), pl.scan_parquet(DATASETS[id]), or duckdb.sql(''SELECT ... FROM read_parquet(?)'', params=[DATASETS[id]]); never write your own file paths. Libraries: numpy, pandas, polars, pyarrow, duckdb, scipy, statsmodels, matplotlib, and TA-Lib (import talib: RSI, SMA, STDDEV, MACD, BBANDS, candlestick patterns such as CDLENGULFING, which returns positive values for bullish and negative for bearish patterns). Helper module saniti: load_dataset(id, columns=None) returns a pandas DataFrame; iter_series(df, entity, date, min_history) yields (entity, its history sorted by date) and records entities excluded for short history; prepare_panel(df, entity, date, on_duplicate=''error''|''keep_last''|''keep_first'') sorts and handles duplicate observations explicitly; panel_check(df, entity, date) reports duplicates, ordering, and nulls; add_warning(code, message) records a limitation; SEED is the fixed seed. Official results must be emitted, not printed: emit_table(name, dataframe, description=''''), emit_metrics(dict), emit_chart(figure, name, title, description), emit_artifact(name, data, format=''PARQUET''|''CSV''|''JSON''); only types listed in expected_outputs may be emitted. Compute indicators per entity on date-sorted history, never across a multi-entity frame, and do not fill missing values silently. The call waits briefly; if status is QUEUED or RUNNING, call get_analysis_result after retry_after_seconds. A TABLE returns row_count, columns, a bounded preview, and a result_id for the complete table.', '{"additionalProperties":false,"properties":{"dataset_ids":{"description":"dataset_ids from DATASET_READY results to use as inputs (1 to 4, unique).","items":{"type":"string"},"type":"array"},"expected_outputs":{"description":"Output types the code will emit (unique).","items":{"enum":["TABLE","METRICS","CHART","ARTIFACT"],"type":"string"},"type":"array"},"purpose":{"description":"The calculation this code performs and why.","type":"string"},"python_code":{"description":"Python source to run in the sandbox.","type":"string"}},"required":["purpose","dataset_ids","python_code","expected_outputs"],"type":"object"}'::jsonb, '{"description":"The market-python-sandbox analysis record (model view).","properties":{"analysis_id":{},"dataset_ids":{},"diagnostics":{},"error":{},"expected_outputs":{},"lineage":{},"next_action":{},"outputs":{},"outputs_expire_at":{},"purpose":{},"retry_after_seconds":{},"runtime_ms":{},"status":{},"warnings":{}},"type":"object"}'::jsonb,
     'ORCHESTRATOR', NULL, NULL, NULL, NULL, NULL, NULL, NULL, 50, 40000, 50, 40000, NULL,
     false, false, false, '{"executor_service":"market-python-sandbox","handler":"app/tools/analysis.py","isolation":"fresh process, non-root slot user, rlimits, seccomp (no sockets/exec/fork); not a network namespace","max_code_chars":20000,"max_datasets":4,"max_purpose_chars":1000,"output_types":["TABLE","METRICS","CHART","ARTIFACT"],"registry_state":"Registered in market-ai-orc; is_active=false keeps it out of market-ai-backend tool lists.","runtime_commit":"81475ae","runtime_service":"market-ai-orc","sandbox_limits_source":"market-python-sandbox PY_SANDBOX_* configuration (not model-controlled)","table_preview_rows":50}'::jsonb, 'v1', false),
    ('get_analysis_result', 'ADVANCED', 'RETRIEVAL', 'Get the status and structured outputs of a run_python_analysis job. Waits briefly while it runs. Returns status (QUEUED, RUNNING, COMPLETED, FAILED, CANCELLED, EXPIRED), next_action, outputs, warnings, and a structured error.', '{"additionalProperties":false,"properties":{"analysis_id":{"description":"analysis_id from run_python_analysis.","type":"string"}},"required":["analysis_id"],"type":"object"}'::jsonb, '{"description":"The market-python-sandbox analysis record (model view).","properties":{"analysis_id":{},"dataset_ids":{},"diagnostics":{},"error":{},"expected_outputs":{},"lineage":{},"next_action":{},"outputs":{},"outputs_expire_at":{},"purpose":{},"retry_after_seconds":{},"runtime_ms":{},"status":{},"warnings":{}},"type":"object"}'::jsonb,
     'ORCHESTRATOR', NULL, NULL, NULL, NULL, NULL, NULL, NULL, 50, 40000, 50, 40000, NULL,
     false, false, false, '{"executor_service":"market-python-sandbox","handler":"app/tools/analysis.py","poll_wait_seconds":20,"registry_state":"Registered in market-ai-orc; is_active=false keeps it out of market-ai-backend tool lists.","runtime_commit":"81475ae","runtime_service":"market-ai-orc","statuses":["QUEUED","RUNNING","COMPLETED","FAILED","CANCELLED","EXPIRED"]}'::jsonb, 'v1', false);

UPDATE public."Tool_Catalog"
SET tool_specific_limits = tool_specific_limits || '{"runtime_commit": "81475ae"}'::jsonb,
    updated_at = CURRENT_TIMESTAMP
WHERE tool_specific_limits->>'runtime_service' = 'market-ai-orc' AND NOT is_active
  AND tool_specific_limits->>'runtime_commit' = 'f63bebc';

DO $verify$
BEGIN
    IF (SELECT count(*) FROM public."Tool_Catalog"
        WHERE tool_specific_limits->>'runtime_service' = 'market-ai-orc' AND NOT is_active
          AND tool_specific_limits->>'runtime_commit' = '81475ae') <> 9 THEN
        RAISE EXCEPTION 'Expected nine inactive market-ai-orc rows at runtime_commit 81475ae';
    END IF;
    IF EXISTS (SELECT 1 FROM public."Tool_Catalog"
               WHERE is_active AND tool_specific_limits->>'runtime_service' = 'market-ai-orc') THEN
        RAISE EXCEPTION 'market-ai-orc rows must stay inactive';
    END IF;
END
$verify$;

COMMIT;

