-- Catalog discovery v2 becomes the active Tool_Catalog contract (market-ai-orc). The user decided on 2026-09-27 to keep
-- AI_ENABLE_CATALOG_DISCOVERY_V2 on in dev and to turn AI_ENABLE_CATALOG_PROTOCOL off (the 20-question stress test
-- measured no discovery saving from the protocol). 20260927_001 registered discover_catalog v2 and get_catalog_details
-- v2 inactive and said a later migration switches is_active once the flag is on; this is that migration.
-- Tool_Catalog_one_active_version_idx allows one active version per tool, so v1 is deactivated first. v1 stays
-- registered: market-ai-orc serves it again when AI_ENABLE_CATALOG_DISCOVERY_V2 is off (the rollback). The served
-- code is unchanged since runtime_commit 35e5db0. No table, column, grant or market-data row is touched.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

DO $preflight$
BEGIN
    IF (SELECT count(*) FROM public."Tool_Catalog"
        WHERE tool_name IN ('discover_catalog', 'get_catalog_details') AND version = 'v1' AND is_active
          AND tool_specific_limits->>'runtime_service' = 'market-ai-orc'
          AND tool_specific_limits->>'successor_version' = 'v2') <> 2 THEN
        RAISE EXCEPTION 'Expected discover_catalog v1 and get_catalog_details v1 active with their v2 successor';
    END IF;
    IF (SELECT count(*) FROM public."Tool_Catalog"
        WHERE tool_name IN ('discover_catalog', 'get_catalog_details') AND version = 'v2' AND NOT is_active
          AND tool_specific_limits->>'runtime_commit' = '35e5db0') <> 2 THEN
        RAISE EXCEPTION 'Expected discover_catalog v2 and get_catalog_details v2 inactive at runtime_commit 35e5db0';
    END IF;
END
$preflight$;

UPDATE public."Tool_Catalog"
SET is_active = false,
    tool_specific_limits = (tool_specific_limits - 'successor_note')
        || '{"superseded_by":"v2","registry_state":"Superseded by v2 (migration 20260927_003). market-ai-orc still serves v1 when AI_ENABLE_CATALOG_DISCOVERY_V2 is off (rollback)."}'::jsonb,
    updated_at = CURRENT_TIMESTAMP
WHERE tool_name IN ('discover_catalog', 'get_catalog_details') AND version = 'v1'
  AND tool_specific_limits->>'runtime_service' = 'market-ai-orc';

UPDATE public."Tool_Catalog"
SET is_active = true,
    tool_specific_limits = tool_specific_limits
        || '{"registry_state":"Active (migration 20260927_003): served by market-ai-orc while AI_ENABLE_CATALOG_DISCOVERY_V2 is on (on in dev since 2026-09-27). AI_ENABLE_CATALOG_PROTOCOL, which adds the per-run result cache, is off."}'::jsonb,
    updated_at = CURRENT_TIMESTAMP
WHERE tool_name IN ('discover_catalog', 'get_catalog_details') AND version = 'v2'
  AND tool_specific_limits->>'runtime_service' = 'market-ai-orc';

DO $verify$
BEGIN
    IF (SELECT count(*) FROM public."Tool_Catalog"
        WHERE tool_name IN ('discover_catalog', 'get_catalog_details') AND version = 'v2' AND is_active
          AND tool_specific_limits->>'runtime_commit' = '35e5db0') <> 2 THEN
        RAISE EXCEPTION 'The two v2 rows are not active';
    END IF;
    IF (SELECT count(*) FROM public."Tool_Catalog"
        WHERE tool_name IN ('discover_catalog', 'get_catalog_details') AND version = 'v1' AND NOT is_active
          AND tool_specific_limits->>'superseded_by' = 'v2'
          AND NOT tool_specific_limits ? 'successor_note') <> 2 THEN
        RAISE EXCEPTION 'The two v1 rows are not inactive and superseded by v2';
    END IF;
    IF (SELECT count(*) FROM public."Tool_Catalog"
        WHERE tool_name IN ('discover_catalog', 'get_catalog_details') AND is_active) <> 2 THEN
        RAISE EXCEPTION 'Expected exactly one active version of each tool';
    END IF;
END
$verify$;

COMMIT;
