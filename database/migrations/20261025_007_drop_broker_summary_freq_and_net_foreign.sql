-- EXEC-INDEX-1 D (user 2026-10-25, screenshot of the idx_broker_summary_freq_* and idx_net_foreign_summary_* partitions:
-- "Boleh lakukan pengecekan sekali lagi apakah tesis saya screenshot ini dipakai atau tidak. Jika tidak dipakai,
-- dihapus saja."): drop the two unused Stockbit staging families. IDX_Broker_Profile_History, also marked in the
-- screenshot, is used (AI_table_catalog, Governor login, 5 relationships, point-in-time functions) and is kept.
--
-- Read-only check 2026-10-25 (job run_job.sh, ERRORS M215):
-- - IDX_Broker_Summary_Freq (12 yearly partitions): emptied by 20261025_004. Its only reader is
--   sync_broker_summary_freq, and the re-downloaded IDX_Broker_Summary dates (2026-09-01 to 2026-10-23) already carry
--   buy_freq/sell_freq on every row: the loader writes the frequency directly, so the staging and its sync are retired.
-- - IDX_Net_Foreign_Summary (12 yearly partitions, 2,713,314 rows, 2016-01-04 to 2026-10-09, about 540 MB): no view, FK,
--   function, AI catalog row, AI grant or repository code reads it; Feature 06 is computed from Feature 05.
-- The enum types of their columns are left in place. Forward-only; a rollback recreates them from the Stockbit loader.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '5min';

DO $preflight$
BEGIN
    IF to_regclass('public."IDX_Broker_Summary_Freq"') IS NULL OR to_regclass('public."IDX_Net_Foreign_Summary"') IS NULL THEN
        RAISE EXCEPTION 'A table to drop is missing: reconcile first';
    END IF;
    IF EXISTS (SELECT 1 FROM public."IDX_Broker_Summary_Freq") THEN
        RAISE EXCEPTION 'IDX_Broker_Summary_Freq holds rows again: a loader writes it; ask before dropping';
    END IF;
    IF EXISTS (SELECT 1 FROM public."IDX_Broker_Summary" WHERE "Date" >= DATE '2026-09-01' AND buy_freq IS NULL) THEN
        RAISE EXCEPTION 'Re-downloaded Broker Summary rows lack frequency: the staging may still be needed';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_depend d JOIN pg_rewrite r ON r.oid = d.objid
               WHERE r.ev_class <> d.refobjid AND d.refobjid IN (
                   SELECT c.oid FROM pg_class c LEFT JOIN pg_inherits i ON i.inhrelid = c.oid
                   WHERE c.oid IN ('public."IDX_Broker_Summary_Freq"'::regclass, 'public."IDX_Net_Foreign_Summary"'::regclass)
                      OR i.inhparent IN ('public."IDX_Broker_Summary_Freq"'::regclass, 'public."IDX_Net_Foreign_Summary"'::regclass)))
       OR EXISTS (SELECT 1 FROM pg_constraint WHERE contype = 'f'
                  AND confrelid IN ('public."IDX_Broker_Summary_Freq"'::regclass, 'public."IDX_Net_Foreign_Summary"'::regclass))
       OR EXISTS (SELECT 1 FROM public."AI_table_catalog" WHERE table_name IN ('IDX_Broker_Summary_Freq', 'IDX_Net_Foreign_Summary'))
       OR EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                  WHERE n.nspname = 'public' AND p.prosrc ILIKE '%net_foreign_summary%') THEN
        RAISE EXCEPTION 'An object depends on a table to drop';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_stat_activity WHERE pid <> pg_backend_pid() AND state <> 'idle'
               AND (query ILIKE '%net_foreign_summary%' OR query ILIKE '%broker_summary_freq%')) THEN
        RAISE EXCEPTION 'A session is using a table to drop now: retry later';
    END IF;
END
$preflight$;

DROP FUNCTION public.sync_broker_summary_freq(date, date);
DROP TABLE public."IDX_Broker_Summary_Freq";
DROP TABLE public."IDX_Net_Foreign_Summary";

-- catalogs: the frequency now comes with the Broker Summary load; the sync function is gone
UPDATE public."Table_Catalog"
SET related_functions = coalesce((SELECT array_agg(f ORDER BY o) FROM unnest(related_functions) WITH ORDINALITY AS x(f, o)
                                  WHERE f NOT LIKE '%sync_broker_summary_freq%'), '{}'::text[])
WHERE table_schema = 'public' AND array_to_string(related_functions, ',') LIKE '%sync_broker_summary_freq%';
UPDATE public."Table_Catalog"
SET source_code_paths = source_code_paths || ARRAY['database/migrations/20261025_007_drop_broker_summary_freq_and_net_foreign.sql']
WHERE table_schema = 'public' AND table_name = 'IDX_Broker_Summary';

UPDATE public."Column_Catalog" AS c
SET definition = v.definition, source_column_or_expression = 'Stockbit broker summary source (loaded with the row)'
FROM (VALUES
    ('buy_freq', 'Number of buy transactions for the key (Date, Symbol, Broker, Investor Type, Market Board), loaded with the Broker Summary row; up to 2026-08-31 copied from the former staging table IDX_Broker_Summary_Freq (dropped 2026-10-25). NULL when the source has no frequency.'),
    ('sell_freq', 'Number of sell transactions for the key, loaded with the Broker Summary row; up to 2026-08-31 copied from the former staging table IDX_Broker_Summary_Freq (dropped 2026-10-25). NULL when the source has no frequency.')
) AS v(column_name, definition)
WHERE c.table_schema = 'public' AND c.table_name = 'IDX_Broker_Summary' AND c.column_name = v.column_name;

UPDATE public."AI_column_catalog" AS a
SET description = c.definition, source_column_or_expression = c.source_column_or_expression
FROM public."Column_Catalog" AS c
WHERE c.table_schema = 'public' AND c.table_name = 'IDX_Broker_Summary' AND a.table_name = 'IDX_Broker_Summary'
  AND a.column_name = c.column_name AND c.column_name IN ('buy_freq', 'sell_freq');

COMMENT ON COLUMN public."IDX_Broker_Summary".buy_freq IS
    'Number of buy transactions for the key, loaded with the Broker Summary row (up to 2026-08-31 copied from the former IDX_Broker_Summary_Freq, dropped 2026-10-25); NULL when the source has no frequency.';
COMMENT ON COLUMN public."IDX_Broker_Summary".sell_freq IS
    'Number of sell transactions for the key, loaded with the Broker Summary row (up to 2026-08-31 copied from the former IDX_Broker_Summary_Freq, dropped 2026-10-25); NULL when the source has no frequency.';

DO $verify$
BEGIN
    IF to_regclass('public."IDX_Broker_Summary_Freq"') IS NOT NULL OR to_regclass('public."IDX_Net_Foreign_Summary"') IS NOT NULL
       OR EXISTS (SELECT 1 FROM pg_class WHERE relname LIKE 'idx\_broker\_summary\_freq\_%' OR relname LIKE 'idx\_net\_foreign\_summary\_%')
       OR to_regprocedure('public.sync_broker_summary_freq(date,date)') IS NOT NULL THEN
        RAISE EXCEPTION 'A dropped object is still present';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public."IDX_Broker_Summary" WHERE "Date" = DATE '2026-08-31' AND buy_freq IS NOT NULL)
       OR to_regclass('public."IDX_Broker_Profile_History"') IS NULL THEN
        RAISE EXCEPTION 'Kept data is missing';
    END IF;
    IF EXISTS (SELECT 1 FROM public."Table_Catalog" WHERE array_to_string(related_functions, ',') LIKE '%sync_broker_summary_freq%') THEN
        RAISE EXCEPTION 'Table_Catalog still names the dropped sync function';
    END IF;
    IF EXISTS (SELECT 1 FROM public."AI_column_catalog" WHERE table_name = 'IDX_Broker_Summary'
               AND column_name IN ('buy_freq', 'sell_freq') AND description NOT LIKE '%loaded with the Broker Summary row%') THEN
        RAISE EXCEPTION 'The AI description of the frequency columns was not updated';
    END IF;
END
$verify$;
COMMIT;
