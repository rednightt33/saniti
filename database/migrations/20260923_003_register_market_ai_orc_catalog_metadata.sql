-- Register market-ai-orc metadata required by AGENTS.md:
-- 1. The five market-ai-orc tools in Tool_Catalog (execution_type ORCHESTRATOR, schemas generated from
--    the deployed registry at commit 456081d). They are registered with is_active = false on purpose:
--    market-ai-backend lists every active META/DISCOVERY/QUALITY row to its own model and cannot
--    execute these tools. Runtime activation is owned by the market-ai-orc registry and recorded in
--    tool_specific_limits.runtime_service.
-- 2. public.ai_preview_table_rows(text) in Table_Catalog.related_functions of the seven tables it serves.
-- Requires migration 20260923_002_create_market_ai_preview_interface.sql.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

DO $preflight$
BEGIN
    IF to_regprocedure('public.ai_preview_table_rows(text)') IS NULL THEN
        RAISE EXCEPTION 'Apply 20260923_002_create_market_ai_preview_interface.sql first';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public."Tool_Catalog"
        WHERE tool_name IN ('get_system_capabilities', 'discover_catalog', 'get_catalog_details',
                            'read_catalog_rows', 'preview_table_rows')
    ) THEN
        RAISE EXCEPTION 'A market-ai-orc tool name is already registered in Tool_Catalog';
    END IF;
    IF (SELECT count(*) FROM public."Table_Catalog"
        WHERE table_schema = 'public' AND table_name IN (
            'Feature_01_Stock_Daily', 'Feature_02_Broker_Rolling', 'Feature_03_Stock_Broker_Daily',
            'IDX_Broker_Profile', 'IDX_Broker_Summary', 'IDX_Stock_Universe', 'Price_Stock_Indonesia_IDX')) <> 7 THEN
        RAISE EXCEPTION 'All seven preview tables must be registered in Table_Catalog';
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
    ('get_system_capabilities', 'META', 'DISCOVERY', 'Return which backend capabilities (catalog discovery, full catalog read, market-data preview, database query, Python analysis, web search) and tools are currently available to this agent.', '{"additionalProperties":false,"properties":{},"required":[],"type":"object"}'::jsonb, '{"description":"Normalized as {ok, tool, result} or {ok:false, tool, error:{code,message}}.","properties":{"available_tools":{},"catalog_discovery":{},"database_query":{},"full_catalog_read":{},"market_data_preview":{},"python_analysis":{},"web_search":{}},"type":"object"}'::jsonb, 'ORCHESTRATOR', NULL, NULL, NULL, NULL, NULL, NULL, NULL, 2, 32768, NULL, 32768, NULL, false, false, false, '{"handler":"app/tools/system.py","registry_state":"Registered in market-ai-orc; is_active=false keeps it out of market-ai-backend tool lists.","runtime_commit":"456081d","runtime_service":"market-ai-orc"}'::jsonb, 'v1', false),
    ('discover_catalog', 'DISCOVERY', 'DISCOVERY', 'List the data tables available in Saniti''s AI catalog with their descriptions, category, grain, keys, documentation status, and how much column, calculation, and relationship metadata each has. Returns catalog metadata only, never data rows.', '{"additionalProperties":false,"properties":{},"required":[],"type":"object"}'::jsonb, '{"description":"Normalized as {ok, tool, result} or {ok:false, tool, error:{code,message}}.","properties":{"notice":{},"tables":{},"truncated":{}},"type":"object"}'::jsonb, 'ORCHESTRATOR', NULL, NULL, 50, NULL, NULL, NULL, NULL, 27, 32768, 50, 32768, NULL, false, false, false, '{"handler":"app/tools/catalog.py","max_tables":50,"registry_state":"Registered in market-ai-orc; is_active=false keeps it out of market-ai-backend tool lists.","runtime_commit":"456081d","runtime_service":"market-ai-orc","visibility":"AI_* catalog flags applied"}'::jsonb, 'v1', false),
    ('get_catalog_details', 'DISCOVERY', 'DISCOVERY', 'Retrieve catalog metadata for up to 3 tables returned by discover_catalog. COLUMNS: column meanings, types, units, and allowed aggregations. RELATIONSHIPS: documented join keys, temporal rules, and output grain. CALCULATIONS: documented calculation definitions, required inputs, alignment and missing-data rules. COVERAGE: recorded date coverage and verification status. Large sections are summarized or truncated and say so; narrow them with column_names. Returns documentation only, never observed values.', '{"additionalProperties":false,"properties":{"column_names":{"anyOf":[{"items":{"type":"string"},"type":"array"},{"type":"null"}],"description":"Optional 1-40 exact column names that narrow COLUMNS and CALCULATIONS. Use null for all columns."},"entity_ids":{"anyOf":[{"items":{"type":"string"},"type":"array"},{"type":"null"}],"description":"Optional 1-20 exact entity identifiers such as tickers, adding per-entity rows to COVERAGE. Use null for dataset-level coverage only."},"sections":{"description":"Metadata sections to return: COLUMNS, RELATIONSHIPS, CALCULATIONS, COVERAGE.","items":{"enum":["COLUMNS","RELATIONSHIPS","CALCULATIONS","COVERAGE"],"type":"string"},"type":"array"},"table_names":{"description":"1-3 exact table_name values returned by discover_catalog.","items":{"type":"string"},"type":"array"}},"required":["table_names","sections","column_names","entity_ids"],"type":"object"}'::jsonb, '{"description":"Normalized as {ok, tool, result} or {ok:false, tool, error:{code,message}}.","properties":{"notice":{},"sections":{},"tables":{},"unknown_columns":{},"unknown_entities":{},"unknown_tables":{}},"type":"object"}'::jsonb, 'ORCHESTRATOR', NULL, NULL, NULL, NULL, NULL, NULL, NULL, 27, 32768, NULL, 32768, NULL, false, false, false, '{"handler":"app/tools/catalog.py","max_column_filter":40,"max_entity_ids":20,"max_tables_per_call":3,"payload_budget_bytes":24000,"registry_state":"Registered in market-ai-orc; is_active=false keeps it out of market-ai-backend tool lists.","row_caps":{"calculations":100,"columns":150,"entity_rows":60,"relationships":50,"status_groups":60},"runtime_commit":"456081d","runtime_service":"market-ai-orc"}'::jsonb, 'v1', false),
    ('read_catalog_rows', 'DISCOVERY', 'RETRIEVAL', 'Read the complete records of one AI catalog table (every column and row, in primary-key order), one page at a time. Default page_size 100, maximum 200; a page can end earlier to stay within the output limit. Continue with next_cursor while has_more is true. Returns catalog documentation, not market data.', '{"additionalProperties":false,"properties":{"catalog_name":{"description":"One of the five AI catalog tables.","enum":["AI_table_catalog","AI_column_catalog","AI_catalog_relationships","AI_calculation_catalog","AI_data_coverage"],"type":"string"},"cursor":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"null for the first page, or the exact next_cursor from the previous page."},"page_size":{"anyOf":[{"type":"integer"},{"type":"null"}],"description":"Rows per page; null for the default."}},"required":["catalog_name","page_size","cursor"],"type":"object"}'::jsonb, '{"description":"Normalized as {ok, tool, result} or {ok:false, tool, error:{code,message}}.","properties":{"catalog_name":{},"columns":{},"has_more":{},"next_cursor":{},"notice":{},"order_by":{},"page_limited_by":{},"page_size":{},"returned_rows":{},"rows":{},"rows_before_this_page":{},"total_rows":{}},"type":"object"}'::jsonb, 'ORCHESTRATOR', NULL, 100, 200, NULL, NULL, NULL, NULL, 27, 40192, 200, 40192, NULL, false, false, false, '{"catalogs":["AI_table_catalog","AI_column_catalog","AI_catalog_relationships","AI_calculation_catalog","AI_data_coverage"],"cursor":"HMAC-signed, catalog-bound","handler":"app/tools/catalog_rows.py","page_max_bytes":32000,"pagination":"keyset on primary key","registry_state":"Registered in market-ai-orc; is_active=false keeps it out of market-ai-backend tool lists.","runtime_commit":"456081d","runtime_service":"market-ai-orc","visibility_filter":"none"}'::jsonb, 'v1', false),
    ('preview_table_rows', 'DISCOVERY', 'RETRIEVAL', 'Return up to 20 example rows (all columns) from one of seven approved market-data tables, in a fixed deterministic order stated in the result. No filters, offsets, custom limits, or pagination. Example records only, not a complete or representative dataset and not an analysis.', '{"additionalProperties":false,"properties":{"table_name":{"description":"One of the seven approved market-data tables.","enum":["Feature_01_Stock_Daily","Feature_02_Broker_Rolling","Feature_03_Stock_Broker_Daily","IDX_Broker_Profile","IDX_Broker_Summary","IDX_Stock_Universe","Price_Stock_Indonesia_IDX"],"type":"string"}},"required":["table_name"],"type":"object"}'::jsonb, '{"description":"Normalized as {ok, tool, result} or {ok:false, tool, error:{code,message}}.","properties":{"columns":{},"is_sample":{},"notice":{},"ordering":{},"returned_rows":{},"row_limit":{},"rows":{},"table_name":{}},"type":"object"}'::jsonb, 'ORCHESTRATOR', NULL, 20, 20, NULL, NULL, NULL, NULL, 27, 52096, 20, 52096, NULL, false, false, false, '{"db_function":"public.ai_preview_table_rows(text)","filters_offsets_pagination":false,"handler":"app/tools/preview.py","ordering":{"Feature_01_Stock_Daily":"date DESC, ticker DESC","Feature_02_Broker_Rolling":"date DESC, market_board DESC, ticker DESC, broker DESC, investor_type DESC","Feature_03_Stock_Broker_Daily":"date DESC, market_board DESC, ticker DESC","IDX_Broker_Profile":"broker_code ASC","IDX_Broker_Summary":"\"Date\" DESC, \"Symbol\" DESC, \"Broker\" DESC, \"Investor Type\" DESC, \"Market Board\" DESC","IDX_Stock_Universe":"\"Ticker\" ASC","Price_Stock_Indonesia_IDX":"date DESC, ticker DESC"},"preview_payload_max_bytes":48000,"registry_state":"Registered in market-ai-orc; is_active=false keeps it out of market-ai-backend tool lists.","row_limit":20,"runtime_commit":"456081d","runtime_service":"market-ai-orc"}'::jsonb, 'v1', false);

UPDATE public."Table_Catalog"
SET related_functions = array_append(related_functions, 'public.ai_preview_table_rows(text)')
WHERE table_schema = 'public'
  AND table_name IN (
      'Feature_01_Stock_Daily', 'Feature_02_Broker_Rolling', 'Feature_03_Stock_Broker_Daily',
      'IDX_Broker_Profile', 'IDX_Broker_Summary', 'IDX_Stock_Universe', 'Price_Stock_Indonesia_IDX')
  AND NOT ('public.ai_preview_table_rows(text)' = ANY(related_functions));

DO $verify$
BEGIN
    IF (SELECT count(*) FROM public."Tool_Catalog"
        WHERE execution_type = 'ORCHESTRATOR' AND NOT is_active
          AND tool_specific_limits->>'runtime_service' = 'market-ai-orc') <> 5 THEN
        RAISE EXCEPTION 'Expected five inactive market-ai-orc Tool_Catalog rows';
    END IF;
    IF (SELECT count(*) FROM public."Table_Catalog"
        WHERE table_schema = 'public'
          AND 'public.ai_preview_table_rows(text)' = ANY(related_functions)) <> 7 THEN
        RAISE EXCEPTION 'Expected ai_preview_table_rows in related_functions of exactly seven tables';
    END IF;
END
$verify$;

COMMIT;
