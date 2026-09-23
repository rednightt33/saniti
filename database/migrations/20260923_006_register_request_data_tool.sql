-- Register request_data (market-ai-orc -> market-sql-governor) in Tool_Catalog and move the five
-- existing market-ai-orc rows to runtime commit f63bebc. Like migration 003, the row is
-- is_active = false so market-ai-backend does not list a tool it cannot execute; activation is
-- owned by the market-ai-orc registry (registered when SQL_GOVERNOR_URL is set). The input schema
-- is generated from the deployed registry. Advertised ceilings mirror the Governor defaults;
-- the Governor configuration remains the enforcement layer.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

DO $preflight$
BEGIN
    IF EXISTS (SELECT 1 FROM public."Tool_Catalog" WHERE tool_name = 'request_data') THEN
        RAISE EXCEPTION 'request_data is already registered in Tool_Catalog';
    END IF;
    IF (SELECT count(*) FROM public."Tool_Catalog"
        WHERE tool_specific_limits->>'runtime_service' = 'market-ai-orc' AND NOT is_active
          AND tool_specific_limits->>'runtime_commit' = 'c1b4e93') <> 5 THEN
        RAISE EXCEPTION 'Expected the five market-ai-orc rows at runtime_commit c1b4e93 (migration 004)';
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
    ('request_data', 'QUERY', 'RETRIEVAL', 'Request actual database observations with a structured data request (never SQL). Use exact table and column names from the catalog tools. Joins name only the table (and optionally a catalog relationship_id); join keys come from the catalog. Filters use EQ, NEQ, GT, GTE, LT, LTE, IN, BETWEEN, IS_NULL, IS_NOT_NULL with typed values. Aggregations must be allowed by the column catalog; when aggregating, every returned column must be in group_by. The SQL Governor validates, cost-checks, and executes the request and returns a decision: INLINE_RESULT (rows included), DATASET_READY (a dataset_id reference only), NEEDS_NARROWING, or REJECTED, with next_action and reason_code.', '{"additionalProperties":false,"properties":{"aggregations":{"items":{"additionalProperties":false,"properties":{"column":{"type":"string"},"function":{"enum":["SUM","AVG","MEDIAN","MIN","MAX","COUNT","COUNT_DISTINCT"],"type":"string"},"table":{"type":"string"}},"required":["table","column","function"],"type":"object"},"type":"array"},"columns":{"description":"Columns to return (group-by columns when aggregating).","items":{"additionalProperties":false,"properties":{"column":{"description":"Exact column_name from the catalog.","type":"string"},"table":{"description":"Exact table_name from the catalog.","type":"string"}},"required":["table","column"],"type":"object"},"type":"array"},"filters":{"items":{"additionalProperties":false,"properties":{"column":{"type":"string"},"operator":{"enum":["EQ","NEQ","GT","GTE","LT","LTE","IN","BETWEEN","IS_NULL","IS_NOT_NULL"],"type":"string"},"table":{"type":"string"},"value":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"},{"type":"boolean"},{"items":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"}]},"type":"array"},{"type":"null"}],"description":"Scalar for EQ/NEQ/GT/GTE/LT/LTE; list for IN; [low, high] for BETWEEN; null for IS_NULL/IS_NOT_NULL. Dates as YYYY-MM-DD strings. Values are bound as parameters."}},"required":["table","column","operator","value"],"type":"object"},"type":"array"},"from_table":{"description":"Primary table from the catalog.","type":"string"},"group_by":{"items":{"additionalProperties":false,"properties":{"column":{"description":"Exact column_name from the catalog.","type":"string"},"table":{"description":"Exact table_name from the catalog.","type":"string"}},"required":["table","column"],"type":"object"},"type":"array"},"joins":{"items":{"additionalProperties":false,"properties":{"relationship_id":{"anyOf":[{"type":"integer"},{"type":"null"}],"description":"Catalog relationship_id to use, or null when exactly one approved relationship applies."},"table":{"description":"Table to join; join keys come from the catalog.","type":"string"}},"required":["table","relationship_id"],"type":"object"},"type":"array"},"order_by":{"items":{"additionalProperties":false,"properties":{"column":{"type":"string"},"direction":{"enum":["ASC","DESC"],"type":"string"},"function":{"anyOf":[{"enum":["SUM","AVG","MEDIAN","MIN","MAX","COUNT","COUNT_DISTINCT"],"type":"string"},{"type":"null"}],"description":"null to order by the column itself, or the aggregation function listed in aggregations."},"table":{"type":"string"}},"required":["table","column","function","direction"],"type":"object"},"type":"array"},"purpose":{"description":"Why the data is needed.","type":"string"},"requested_limit":{"anyOf":[{"type":"integer"},{"type":"null"}],"description":"Optional row limit; null for none."}},"required":["purpose","from_table","columns","joins","filters","group_by","aggregations","order_by","requested_limit"],"type":"object"}'::jsonb, '{"description":"The SQL Governor response, returned unchanged.","properties":{"columns":{},"dataset":{},"decision":{},"details":{},"estimated_plan_cost":{},"estimated_scan_rows":{},"message":{},"next_action":{},"output_bytes":{},"query_hash":{},"query_id":{},"reason_code":{},"request_id":{},"returned_rows":{},"rows":{},"runtime_ms":{},"source_tables":{},"warnings":{}},"type":"object"}'::jsonb,
     'ORCHESTRATOR', NULL, NULL, 500000, NULL, NULL, 3660, 2000000, 95, 40000, 200, 40000, NULL,
     false, false, false, '{"dataset_format":"PARQUET","decisions":["INLINE_RESULT","DATASET_READY","NEEDS_NARROWING","REJECTED"],"executor_service":"market-sql-governor","governor_limits_source":"market-sql-governor SQL_* configuration (not model-controlled)","handler":"app/tools/request_data.py","registry_state":"Registered in market-ai-orc; is_active=false keeps it out of market-ai-backend tool lists.","runtime_commit":"f63bebc","runtime_service":"market-ai-orc"}'::jsonb, 'v1', false);

UPDATE public."Tool_Catalog"
SET tool_specific_limits = tool_specific_limits || '{"runtime_commit": "f63bebc"}'::jsonb,
    updated_at = CURRENT_TIMESTAMP
WHERE tool_specific_limits->>'runtime_service' = 'market-ai-orc' AND NOT is_active
  AND tool_name <> 'request_data';

DO $verify$
BEGIN
    IF (SELECT count(*) FROM public."Tool_Catalog"
        WHERE tool_specific_limits->>'runtime_service' = 'market-ai-orc' AND NOT is_active
          AND tool_specific_limits->>'runtime_commit' = 'f63bebc') <> 6 THEN
        RAISE EXCEPTION 'Expected six inactive market-ai-orc rows at runtime_commit f63bebc';
    END IF;
    IF EXISTS (SELECT 1 FROM public."Tool_Catalog"
               WHERE is_active AND tool_specific_limits->>'runtime_service' = 'market-ai-orc') THEN
        RAISE EXCEPTION 'market-ai-orc rows must stay inactive';
    END IF;
END
$verify$;

COMMIT;
