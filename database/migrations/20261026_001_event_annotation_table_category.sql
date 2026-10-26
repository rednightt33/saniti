-- EXEC-M225 (user go 2026-10-26: "Jalankan untuk ke 3 exec tersebut"; ERRORS M225): idx_event_annotation is
-- Transactional, not Feature. 20261025_013 registered it as 'Feature', so scripts/audit_feature_catalog_semantics.py
-- demanded a Feature_Catalog definition for each of its columns and failed (job 71673659). AI_table_catalog already
-- calls it TRANSACTIONAL, like its two source tables.
--
-- Evidence, read-only job 87e18813 (2026-10-26): Table_Catalog category 'Feature' for idx_event_annotation; the
-- Feature-category objects without an own Feature_Catalog row are idx_event_annotation and the two *_Stock views
-- (covered through their base columns, view_column_usage).
--
-- The closing check is the audit's own rule, for every object of category Feature (not only this table): each column
-- has an active Feature_Catalog definition, directly or through the base column a view reads. A table registered as
-- Feature by mistake later fails here and in the audit, not silently.
-- Rollback (forward-only): set the category back by a later migration (documentation only; no data changes).
BEGIN;
SET LOCAL lock_timeout = '5s';

DO $preflight$
BEGIN
    IF (SELECT category FROM public."Table_Catalog"
        WHERE table_schema = 'public' AND table_name = 'idx_event_annotation') IS DISTINCT FROM 'Feature' THEN
        RAISE EXCEPTION 'idx_event_annotation is not registered as Feature; nothing to correct';
    END IF;
END
$preflight$;

UPDATE public."Table_Catalog"
SET category = 'Transactional',
    source_code_paths = CASE WHEN 'database/migrations/20261026_001_event_annotation_table_category.sql' = ANY (source_code_paths)
                             THEN source_code_paths
                             ELSE array_append(source_code_paths, 'database/migrations/20261026_001_event_annotation_table_category.sql') END,
    updated_at = CURRENT_TIMESTAMP
WHERE table_schema = 'public' AND table_name = 'idx_event_annotation';

DO $check$
DECLARE missing text;
BEGIN
    SELECT string_agg(c.table_name || '.' || c.column_name, ', ' ORDER BY c.table_name, c.ordinal_position)
    INTO missing
    FROM information_schema.columns c
    JOIN public."Table_Catalog" t ON t.table_schema = c.table_schema AND t.table_name = c.table_name
    WHERE t.category = 'Feature'
      AND NOT EXISTS (SELECT 1 FROM public."Feature_Catalog" f
                      WHERE f.feature_table = c.table_name AND f.feature_column = c.column_name AND f.is_active)
      AND NOT EXISTS (SELECT 1 FROM information_schema.view_column_usage u
                      JOIN public."Feature_Catalog" f
                        ON f.feature_table = u.table_name AND f.feature_column = u.column_name AND f.is_active
                      WHERE u.view_schema = c.table_schema AND u.view_name = c.table_name
                        AND u.table_schema = 'public' AND u.column_name = c.column_name);
    IF missing IS NOT NULL THEN
        RAISE EXCEPTION 'Feature-category columns without a Feature_Catalog definition: %', left(missing, 500);
    END IF;
END
$check$;

COMMIT;
