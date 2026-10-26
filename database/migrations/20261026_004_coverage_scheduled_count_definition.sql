-- EXEC-M224 follow-up (2026-10-26): the Column_Catalog definition of AI_data_coverage.scheduled_row_count written by
-- 20261026_003 said a nightly check keeps the last full count. The coverage job (main 831c52b) writes the count on every
-- run: rows after the check date always fall inside the nightly window, so the nightly count is complete
-- (apps/ai-data-coverage/coverage_job.py raw_coverage_rows). The definition now says what the code does.
BEGIN;
SET LOCAL lock_timeout = '5s';

UPDATE public."Column_Catalog"
SET definition = 'Number of source rows dated after the check date (announced schedules), counted on every run: rows after the check date always fall inside the nightly window, so a nightly count is complete.',
    updated_at = CURRENT_TIMESTAMP
WHERE table_schema = 'public' AND table_name = 'AI_data_coverage' AND column_name = 'scheduled_row_count';

DO $verify$
BEGIN
    IF (SELECT definition FROM public."Column_Catalog" WHERE table_schema = 'public' AND table_name = 'AI_data_coverage'
        AND column_name = 'scheduled_row_count') NOT LIKE '%counted on every run%' THEN
        RAISE EXCEPTION 'scheduled_row_count definition was not corrected';
    END IF;
END
$verify$;
COMMIT;
