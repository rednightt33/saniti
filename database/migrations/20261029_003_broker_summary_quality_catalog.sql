-- EXEC-LOADER-M217: the catalog text of broker_summary_date_quality follows 20261029_002, which dropped the stock row
-- check (a row count measures activity, not completeness); stock_rows stays recorded. Read back in the same job.
BEGIN;

UPDATE public."Table_Catalog"
SET definition = 'Completeness of each IDX_Broker_Summary trade date after every write: brokers, stocks and frequency share of the stock rows against the 20 earlier dates whose check passed, and whether the non-stock symbols vanished; status COMPLETE, INCOMPLETE or UNCHECKED with a plain Indonesian remark. Row counts are recorded, not checked (they move with activity). Loads are never refused.',
    source_code_paths = ARRAY['database/migrations/20261029_001_broker_summary_date_quality.sql',
                              'database/migrations/20261029_002_broker_summary_quality_checks.sql']
WHERE table_schema = 'public' AND table_name = 'broker_summary_date_quality';

UPDATE public."Column_Catalog"
SET definition = 'Rows of four-letter symbols (stocks) on the date; recorded, not checked (it moves with activity).'
WHERE table_schema = 'public' AND table_name = 'broker_summary_date_quality' AND column_name = 'stock_rows';

DO $check$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM public."Table_Catalog" WHERE table_name = 'broker_summary_date_quality'
                   AND definition LIKE '%Row counts are recorded, not checked%') THEN
        RAISE EXCEPTION 'Table_Catalog definition not updated';
    END IF;
END $check$;

COMMIT;
