-- market-ai-orc commit c1b4e93 lowers the read_catalog_rows page budget (CATALOG_PAGE_MAX_BYTES
-- default 32000 -> 16000). Its tool result cap is page budget + 8192, so 40192 -> 24192. Input
-- schemas and descriptions of all five tools are unchanged (compared from the registry at
-- 456081d and c1b4e93). Rows stay is_active = false; see
-- 20260923_003_register_market_ai_orc_catalog_metadata.sql.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

DO $preflight$
BEGIN
    IF (SELECT count(*) FROM public."Tool_Catalog"
        WHERE execution_type = 'ORCHESTRATOR' AND version = 'v1' AND NOT is_active
          AND tool_specific_limits->>'runtime_service' = 'market-ai-orc'
          AND tool_specific_limits->>'runtime_commit' = '456081d') <> 5 THEN
        RAISE EXCEPTION 'Expected the five market-ai-orc rows from migration 003 (runtime_commit 456081d)';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public."Tool_Catalog"
        WHERE tool_name = 'read_catalog_rows' AND version = 'v1'
          AND max_output_bytes = 40192 AND (tool_specific_limits->>'page_max_bytes')::integer = 32000
    ) THEN
        RAISE EXCEPTION 'read_catalog_rows does not carry the expected previous limits';
    END IF;
END
$preflight$;

UPDATE public."Tool_Catalog"
SET max_output_bytes = 24192,
    max_llm_result_bytes = 24192,
    tool_specific_limits = tool_specific_limits || '{"page_max_bytes": 16000}'::jsonb,
    updated_at = CURRENT_TIMESTAMP
WHERE tool_name = 'read_catalog_rows' AND version = 'v1';

UPDATE public."Tool_Catalog"
SET tool_specific_limits = tool_specific_limits || '{"runtime_commit": "c1b4e93"}'::jsonb,
    updated_at = CURRENT_TIMESTAMP
WHERE execution_type = 'ORCHESTRATOR' AND version = 'v1' AND NOT is_active
  AND tool_specific_limits->>'runtime_service' = 'market-ai-orc';

DO $verify$
BEGIN
    IF (SELECT count(*) FROM public."Tool_Catalog"
        WHERE tool_specific_limits->>'runtime_service' = 'market-ai-orc' AND NOT is_active
          AND tool_specific_limits->>'runtime_commit' = 'c1b4e93') <> 5 THEN
        RAISE EXCEPTION 'Expected five market-ai-orc rows at runtime_commit c1b4e93';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public."Tool_Catalog"
        WHERE tool_name = 'read_catalog_rows' AND version = 'v1' AND max_output_bytes = 24192
          AND max_llm_result_bytes = 24192 AND (tool_specific_limits->>'page_max_bytes')::integer = 16000
    ) THEN
        RAISE EXCEPTION 'read_catalog_rows limits were not updated';
    END IF;
END
$verify$;

COMMIT;
