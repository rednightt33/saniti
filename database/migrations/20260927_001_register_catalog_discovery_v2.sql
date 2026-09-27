-- Catalog discovery v2 (market-ai-orc, AI_ENABLE_CATALOG_DISCOVERY_V2; implementation plan 2026-09-27, phases
-- C1-C2). Generated from the market-ai-orc tool definitions at df76c77.
-- Tool_Catalog: discover_catalog v2 (filters, keyset paging, bound cursor) and get_catalog_details v2 (table_metadata,
-- completeness, join semantics, resample rules, formula search) are registered inactive. Tool_Catalog allows one
-- active version per tool (Tool_Catalog_one_active_version_idx) and v1 is the contract served while the flag is off,
-- so v1 stays active and records its flagged successor. No table, column, grant or market-data row is touched.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

DO $preflight$
BEGIN
    IF (SELECT count(*) FROM public."Tool_Catalog"
        WHERE tool_name IN ('discover_catalog', 'get_catalog_details') AND version = 'v1'
          AND tool_specific_limits->>'runtime_service' = 'market-ai-orc') <> 2 THEN
        RAISE EXCEPTION 'Expected discover_catalog v1 and get_catalog_details v1 of market-ai-orc';
    END IF;
    IF EXISTS (SELECT 1 FROM public."Tool_Catalog"
               WHERE tool_name IN ('discover_catalog', 'get_catalog_details') AND version = 'v2') THEN
        RAISE EXCEPTION 'A v2 of discover_catalog or get_catalog_details already exists';
    END IF;
END
$preflight$;

UPDATE public."Tool_Catalog"
SET tool_specific_limits = tool_specific_limits || '{"successor_flag":"AI_ENABLE_CATALOG_DISCOVERY_V2","successor_note":"v2 is served when AI_ENABLE_CATALOG_DISCOVERY_V2 is true; v1 remains the active row until the flag is on and a later migration switches is_active.","successor_version":"v2"}'::jsonb, updated_at = CURRENT_TIMESTAMP
WHERE tool_name IN ('discover_catalog', 'get_catalog_details') AND version = 'v1'
  AND tool_specific_limits->>'runtime_service' = 'market-ai-orc';

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
    ('discover_catalog', 'DISCOVERY', 'DISCOVERY', 'Find data tables in Saniti''s AI catalog. Each entry gives the description, category, grain, keys, time and entity columns, subject values (data_domain, entity_type, asset_type, supported_frequencies, time_semantics), documentation status and how much column, calculation and relationship metadata exists; plus the research-method and formula catalog counts. Filter with query and the subject fields; page with next_cursor while has_more is true. Returns catalog metadata only, never data rows.', '{"additionalProperties":false,"properties":{"asset_type":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"Optional exact subject asset_type; null for any."},"cursor":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"Null for the first page, or the exact next_cursor of the previous page with the same filters."},"data_domain":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"Optional exact subject data_domain, for example MARKET; null for any."},"entity_type":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"Optional exact subject entity_type, for example STOCK; null for any."},"page_size":{"anyOf":[{"type":"integer"},{"type":"null"}],"description":"Tables per page, 1-50; null for 20. A page may hold fewer when the byte budget is reached; has_more and next_cursor tell."},"query":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"Optional words matched against table names and descriptions (case-insensitive substring); null for every table."}},"required":["query","data_domain","entity_type","asset_type","page_size","cursor"],"type":"object"}'::jsonb,
     '{"description":"Normalized as {ok, tool, result} or {ok:false, tool, error:{code,message}}. One keyset page of the visible tables matching the filters, ordered by table_name. error.code CURSOR_INVALID for a forged cursor or one issued for other filters; CATALOG_CHANGED_RESTART_DISCOVERY when the table catalog changed since the cursor was issued. With AI_ENABLE_CATALOG_PROTOCOL an identical call in the same run returns the stored result with cache_hit.","properties":{"applied_filters":{},"catalog_fingerprint":{},"formula_catalog":{},"has_more":{},"next_cursor":{},"notice":{},"research_catalog":{},"returned_count":{},"table_count":{},"tables":{},"total_matching":{},"truncated":{}},"type":"object"}'::jsonb,
     'ORCHESTRATOR', NULL, 20, 50, NULL, NULL, NULL, NULL, 27, 32768,
     50, 32768, NULL, false, false, false, '{"cursor":"HMAC-signed; bound to the tool, the filters and a fingerprint of the visible table-catalog rows","default_page_size":20,"error_codes":["CURSOR_INVALID","CATALOG_CHANGED_RESTART_DISCOVERY"],"feature_flag":"AI_ENABLE_CATALOG_DISCOVERY_V2","filters":["query","data_domain","entity_type","asset_type"],"handler":"app/tools/catalog.py","max_page_size":50,"max_query_chars":100,"pagination":"keyset on table_name","payload_budget_bytes":24000,"plan":"implementation plan 2026-09-27, phase C2","query_match":"case-insensitive substring of table_name or description; LIKE wildcards are escaped","registry_state":"Served by market-ai-orc only with AI_ENABLE_CATALOG_DISCOVERY_V2; v1 stays the active row while the flag is off.","runtime_commit":"df76c77","runtime_service":"market-ai-orc","visibility":"AI_* catalog flags applied"}'::jsonb, 'v2', false),
    ('get_catalog_details', 'DISCOVERY', 'DISCOVERY', 'Retrieve catalog metadata for up to 3 tables returned by discover_catalog, with every section you need in one call. The result starts with table_metadata (grain, keys, time/entity columns, subject values). COLUMNS: meanings, types, units, allowed aggregations, filter/group permissions and resample rules, with per-table completeness and recovery_calls when cut. RELATIONSHIPS: join keys, temporal rules, supported join semantics and their time or validity columns, output grain. CALCULATIONS: documented calculation definitions. COVERAGE: recorded date coverage and verification status. RESEARCH: global reference methods (table_names [] for RESEARCH only; method_ids to narrow). FORMULAS: global documented formulas (table_names [] for FORMULAS only); search them by name or description with formula_query, then read chosen ones with formula_ids. Documented definitions are not verified or executable implementations. Large sections are shortened or truncated and say so. Returns documentation only, never observed values.', '{"additionalProperties":false,"properties":{"column_names":{"anyOf":[{"items":{"type":"string"},"type":"array"},{"type":"null"}],"description":"Optional 1-40 exact column names that narrow COLUMNS and CALCULATIONS. Use null for all columns."},"entity_ids":{"anyOf":[{"items":{"type":"string"},"type":"array"},{"type":"null"}],"description":"Optional 1-20 exact entity identifiers such as tickers, adding per-entity rows to COVERAGE. Use null for dataset-level coverage only."},"formula_ids":{"anyOf":[{"items":{"type":"string"},"type":"array"},{"type":"null"}],"description":"Optional 1-40 exact formula calculation_id values; null lists all formulas."},"formula_query":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"FORMULAS only: words to search formula names and descriptions (case-insensitive substring; an exact calculation_id also matches). Returns up to 20 matches with their ids; then pass formula_ids for full definitions. Null when not searching; never together with formula_ids."},"method_ids":{"anyOf":[{"items":{"type":"string"},"type":"array"},{"type":"null"}],"description":"Optional 1-40 exact research method_id values; null lists all methods."},"sections":{"description":"Metadata sections, every one you need in one call: COLUMNS (types, units, permissions, resample rules), COVERAGE (recorded date coverage), RELATIONSHIPS (join keys and join semantics), CALCULATIONS, RESEARCH, FORMULAS.","items":{"enum":["COLUMNS","RELATIONSHIPS","CALCULATIONS","COVERAGE","RESEARCH","FORMULAS"],"type":"string"},"type":"array"},"table_names":{"description":"1-3 exact market table names, or [] for RESEARCH only.","items":{"type":"string"},"type":"array"}},"required":["table_names","sections","column_names","entity_ids","method_ids","formula_ids","formula_query"],"type":"object"}'::jsonb,
     '{"description":"Normalized as {ok, tool, result} or {ok:false, tool, error:{code,message}}. table_metadata per requested table (grain, keys, time/entity columns, subject values). COLUMNS carries per-table completeness {columns_returned, columns_total, complete}, incomplete, recovery_calls, the detail tier and null_meaning; a NULL resample rule is returned as null with resample_rules_recorded, never as a default. RELATIONSHIPS carries supported_join_semantics and the time/validity columns, or join_semantics_recorded false. FORMULAS with formula_query returns ranked matches (EXACT, NAME_PREFIX, NAME_CONTAINS, DESCRIPTION_CONTAINS).","properties":{"notice":{},"sections":{},"table_metadata":{},"tables":{},"unknown_tables":{}},"type":"object"}'::jsonb,
     'ORCHESTRATOR', NULL, NULL, NULL, NULL, NULL, NULL, NULL, 27, 32768, NULL, 32768, NULL, false, false, false,
     '{"added_fields":{"COLUMNS":["resample_aggregation"],"RELATIONSHIPS":["supported_join_semantics","left_time_column","right_time_column","effective_from_column","effective_to_column"],"table_metadata":["grain","primary_key_columns","time_column","entity_column","subject"]},"column_detail_tiers":["FULL","COMPACT","MINIMAL"],"feature_flag":"AI_ENABLE_CATALOG_DISCOVERY_V2","formula_search":{"argument":"formula_query","exclusive_with":"formula_ids","max_query_chars":100,"max_results":20,"ranking":["EXACT","NAME_PREFIX","NAME_CONTAINS","DESCRIPTION_CONTAINS"],"tie_break":"calculation_id"},"handler":"app/tools/catalog.py","max_column_filter":40,"max_entity_ids":20,"max_formula_ids":40,"max_method_ids":40,"max_tables_per_call":3,"null_rule":"a NULL catalog value is returned as null with its meaning, never replaced by a default","payload_budget_bytes":24000,"plan":"implementation plan 2026-09-27, phase C1","registry_state":"Served by market-ai-orc only with AI_ENABLE_CATALOG_DISCOVERY_V2; v1 stays the active row while the flag is off.","row_caps":{"calculations":100,"columns":150,"entities":60,"formulas":50,"relationships":50,"research":50,"status":60},"runtime_commit":"df76c77","runtime_service":"market-ai-orc"}'::jsonb, 'v2', false);

DO $verify$
BEGIN
    IF (SELECT count(*) FROM public."Tool_Catalog"
        WHERE tool_name IN ('discover_catalog', 'get_catalog_details') AND version = 'v2' AND NOT is_active
          AND tool_specific_limits->>'runtime_commit' = 'df76c77'
          AND tool_specific_limits->>'feature_flag' = 'AI_ENABLE_CATALOG_DISCOVERY_V2') <> 2 THEN
        RAISE EXCEPTION 'The two inactive v2 rows were not registered';
    END IF;
    IF NOT (SELECT input_schema #> '{properties}' ?& array['query', 'data_domain', 'entity_type', 'asset_type',
                                                             'page_size', 'cursor']
            FROM public."Tool_Catalog" WHERE tool_name = 'discover_catalog' AND version = 'v2')
       OR NOT (SELECT input_schema #> '{properties}' ? 'formula_query'
               FROM public."Tool_Catalog" WHERE tool_name = 'get_catalog_details' AND version = 'v2') THEN
        RAISE EXCEPTION 'The v2 input schemas lack the discovery filters or formula_query';
    END IF;
    IF (SELECT count(*) FROM public."Tool_Catalog"
        WHERE tool_name IN ('discover_catalog', 'get_catalog_details') AND version = 'v1'
          AND tool_specific_limits->>'successor_version' = 'v2') <> 2 THEN
        RAISE EXCEPTION 'v1 rows do not record their v2 successor';
    END IF;
END
$verify$;

COMMIT;
