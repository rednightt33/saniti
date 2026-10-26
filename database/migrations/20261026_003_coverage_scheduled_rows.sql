-- EXEC-M224 (user go 2026-10-26: "Jalankan untuk ke 3 exec tersebut"; ERRORS M224): coverage keeps rows dated after
-- the check date (announced schedules, for example idx_event_annotation up to 2026-12-18) apart from the last date that
-- has already happened, so freshness is measured from the past. apps/ai-data-coverage/coverage_job.py writes the two
-- new columns; actual_max_date becomes the last date on or before the check date (Asia/Jakarta).
--
-- Evidence, read-only job 87e18813 (2026-10-26): idx_event_annotation DATASET actual_max_date 2026-12-18; 97 rows
-- after 2026-10-26 (all corporate actions); 89 of 1,020 ticker rows have actual_max_date in the future; every other
-- dataset has none. AI_data_coverage is read through column grants (20 columns each for market_ai_app,
-- market_ai_catalog_reader, market_ai_reader, market_ai_sql_reader, pgweb_reader), so the new columns are granted to
-- the roles that may read actual_max_date, read from the catalog rather than listed.
-- Rollback (forward-only): deploy the previous coverage job; the columns stay NULL.
BEGIN;
SET LOCAL lock_timeout = '5s';

ALTER TABLE public."AI_data_coverage"
    ADD COLUMN scheduled_max_date date,
    ADD COLUMN scheduled_row_count bigint,
    ADD CONSTRAINT "AI_data_coverage_scheduled_check" CHECK (
        (scheduled_row_count IS NULL OR scheduled_row_count >= 0)
        AND (scheduled_max_date IS NULL OR actual_max_date IS NULL OR scheduled_max_date > actual_max_date)
    );

DO $grant$
DECLARE r record;
BEGIN
    FOR r IN SELECT DISTINCT grantee FROM information_schema.column_privileges
             WHERE table_schema = 'public' AND table_name = 'AI_data_coverage' AND column_name = 'actual_max_date'
               AND privilege_type = 'SELECT' AND grantee NOT IN ('postgres', 'PUBLIC')
    LOOP
        EXECUTE format('GRANT SELECT (scheduled_max_date, scheduled_row_count) ON public."AI_data_coverage" TO %I',
                       r.grantee);
    END LOOP;
END
$grant$;

WITH d(column_name, definition, unit, null_rule) AS (VALUES
 ('scheduled_max_date', 'Latest date of the rows dated after the check date (announced schedules such as corporate action dates); actual_max_date is the last date on or before the check date (Asia/Jakarta), so freshness is measured from data that has happened.', NULL, 'NULL when the source has no row after the check date, and for derived and snapshot rows.'),
 ('scheduled_row_count', 'Number of source rows dated after the check date (full check; a nightly check keeps the last full count).', 'rows', 'NULL for derived and snapshot rows and before the first check that counted them; 0 when none.'))
INSERT INTO public."Column_Catalog"(table_schema, table_name, column_name, ordinal_position, data_type, is_nullable,
 default_expression, is_primary_key, definition, source_column_or_expression, unit, null_rule, source_code_paths,
 documentation_status)
SELECT 'public', c.table_name, c.column_name, c.ordinal_position, c.data_type, c.is_nullable = 'YES', c.column_default,
 false, d.definition, 'apps/ai-data-coverage/coverage_job.py', d.unit, d.null_rule,
 ARRAY['apps/ai-data-coverage/coverage_job.py', 'database/migrations/20261026_003_coverage_scheduled_rows.sql'], 'VERIFIED'
FROM information_schema.columns c JOIN d USING (column_name)
WHERE c.table_schema = 'public' AND c.table_name = 'AI_data_coverage'
ON CONFLICT (table_schema, table_name, column_name) DO NOTHING;

DO $verify$
BEGIN
    IF (SELECT count(*) FROM public."Column_Catalog" WHERE table_schema = 'public' AND table_name = 'AI_data_coverage'
        AND column_name IN ('scheduled_max_date', 'scheduled_row_count')) <> 2 THEN
        RAISE EXCEPTION 'The new coverage columns lack their Column_Catalog rows';
    END IF;
    IF EXISTS (SELECT grantee FROM information_schema.column_privileges
               WHERE table_schema = 'public' AND table_name = 'AI_data_coverage' AND column_name = 'actual_max_date'
                 AND privilege_type = 'SELECT' AND grantee NOT IN ('postgres', 'PUBLIC')
               EXCEPT
               SELECT grantee FROM information_schema.column_privileges
               WHERE table_schema = 'public' AND table_name = 'AI_data_coverage' AND column_name = 'scheduled_max_date'
                 AND privilege_type = 'SELECT') THEN
        RAISE EXCEPTION 'A reader of actual_max_date cannot read scheduled_max_date';
    END IF;
END
$verify$;
COMMIT;
