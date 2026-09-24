-- Activates the three market-ai-orc catalog tools (discover_catalog, get_catalog_details,
-- read_catalog_rows) whose RESEARCH-section definitions were installed by
-- 20260924_001_create_ai_research_catalog.sql. That migration only updated purpose/schema
-- text and deliberately left is_active untouched; this migration flips it on at the user's
-- explicit request so AI_research_catalog becomes usable through the three tools, and
-- stamps the deployed commit. No table, column, grant, or market-data row is touched.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

DO $preflight$
BEGIN
    IF to_regclass('public."AI_research_catalog"') IS NULL THEN
        RAISE EXCEPTION 'AI_research_catalog does not exist; apply 20260924_001 first';
    END IF;
    IF (SELECT count(*) FROM public."Tool_Catalog"
        WHERE tool_name IN ('discover_catalog', 'get_catalog_details', 'read_catalog_rows')
          AND tool_specific_limits->>'runtime_service' = 'market-ai-orc' AND is_active = false) <> 3 THEN
        RAISE EXCEPTION 'Expected three inactive market-ai-orc catalog tool rows before activation';
    END IF;
END
$preflight$;

UPDATE public."Tool_Catalog"
SET is_active = true,
    tool_specific_limits = tool_specific_limits || '{"runtime_commit": "aa7b231"}'::jsonb,
    updated_at = CURRENT_TIMESTAMP
WHERE tool_name IN ('discover_catalog', 'get_catalog_details', 'read_catalog_rows')
  AND tool_specific_limits->>'runtime_service' = 'market-ai-orc'
  AND is_active = false;

DO $verify$
BEGIN
    IF (SELECT count(*) FROM public."Tool_Catalog"
        WHERE tool_name IN ('discover_catalog', 'get_catalog_details', 'read_catalog_rows')
          AND tool_specific_limits->>'runtime_service' = 'market-ai-orc'
          AND is_active = true AND tool_specific_limits->>'runtime_commit' = 'aa7b231') <> 3 THEN
        RAISE EXCEPTION 'Expected three active market-ai-orc catalog tool rows at runtime_commit aa7b231';
    END IF;
END
$verify$;

COMMIT;
