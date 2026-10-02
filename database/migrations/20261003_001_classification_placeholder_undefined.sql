-- D02 (ERRORS_AND_SOLUTIONS.md; user decisions 2026-10-02: keep "Undefined" for now, cover Sector and Industry in
-- every table): the source wrote the text '0' as Sector and Industry for XCID, XCIS and XSPI, and the value reached the
-- answers as a fake category. It becomes the text 'Undefined' in the current universe, its description source and the
-- Feature 01 rows that copied it. IDX_Stock_Universe_History is not edited: the capture trigger
-- (reference_history_capture, migration 20260927_006) records the new version, and the earlier version keeps '0' as
-- history. Exception to Part A A1.4 (unknown = NULL plus reason), recorded there.
-- Preflight counts are those read on dev 2026-10-02 (temporary job d02-check-job, read only): 3, 3 and 3,365 rows.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '5min';

DO $preflight$
DECLARE
    expected text[] := ARRAY['XCID', 'XCIS', 'XSPI'];
BEGIN
    IF (SELECT count(*) FROM public."IDX_Stock_Universe" WHERE "Sector" = '0' OR "Industry" = '0') <> 3
       OR EXISTS (SELECT 1 FROM public."IDX_Stock_Universe"
                  WHERE ("Sector" = '0' OR "Industry" = '0') AND NOT ("Ticker" = ANY(expected))) THEN
        RAISE EXCEPTION 'IDX_Stock_Universe: expected exactly XCID, XCIS and XSPI with the placeholder 0';
    END IF;
    IF (SELECT count(*) FROM public."Universe_Equity_Description" WHERE "Sector" = '0' OR "Industry" = '0') <> 3
       OR EXISTS (SELECT 1 FROM public."Universe_Equity_Description"
                  WHERE ("Sector" = '0' OR "Industry" = '0') AND NOT ("Ticker" = ANY(expected))) THEN
        RAISE EXCEPTION 'Universe_Equity_Description: expected exactly XCID, XCIS and XSPI with the placeholder 0';
    END IF;
    IF (SELECT count(*) FROM public."Feature_01_Stock_Daily" WHERE sector = '0' OR industry = '0') <> 3365
       OR EXISTS (SELECT 1 FROM public."Feature_01_Stock_Daily"
                  WHERE (sector = '0' OR industry = '0') AND NOT (ticker = ANY(expected))) THEN
        RAISE EXCEPTION 'Feature_01_Stock_Daily: expected 3365 rows of XCID, XCIS and XSPI with the placeholder 0';
    END IF;
END
$preflight$;

UPDATE public."IDX_Stock_Universe"
SET "Sector" = CASE WHEN "Sector" = '0' THEN 'Undefined' ELSE "Sector" END,
    "Industry" = CASE WHEN "Industry" = '0' THEN 'Undefined' ELSE "Industry" END
WHERE "Sector" = '0' OR "Industry" = '0';

UPDATE public."Universe_Equity_Description"
SET "Sector" = CASE WHEN "Sector" = '0' THEN 'Undefined' ELSE "Sector" END,
    "Industry" = CASE WHEN "Industry" = '0' THEN 'Undefined' ELSE "Industry" END
WHERE "Sector" = '0' OR "Industry" = '0';

UPDATE public."Feature_01_Stock_Daily"
SET sector = CASE WHEN sector = '0' THEN 'Undefined' ELSE sector END,
    industry = CASE WHEN industry = '0' THEN 'Undefined' ELSE industry END
WHERE sector = '0' OR industry = '0';

-- What the value means, for people (Column_Catalog) and for the model (AI_column_catalog)
UPDATE public."Column_Catalog"
SET definition = definition || ' ''Undefined'' means the source gives no classification for the security '
                 || '(D02, migration 20261003_001; it replaced the placeholder ''0''). It is not a real sector or '
                 || 'industry: count it apart, never as a category of its own.'
WHERE table_schema = 'public'
  AND ((table_name IN ('IDX_Stock_Universe', 'Universe_Equity_Description') AND column_name IN ('Sector', 'Industry'))
       OR (table_name = 'Feature_01_Stock_Daily' AND column_name IN ('sector', 'industry')))
  AND definition IS NOT NULL AND definition NOT LIKE '%20261003_001%';

UPDATE public."AI_column_catalog"
SET description = coalesce(description || ' ', '')
                  || '''Undefined'' means the source gives no classification for the security (not a real '
                  || 'sector or industry); report those securities apart, never as a category of their own.',
    updated_at = CURRENT_TIMESTAMP
WHERE ((table_name IN ('IDX_Stock_Universe', 'Universe_Equity_Description') AND column_name IN ('Sector', 'Industry'))
       OR (table_name = 'Feature_01_Stock_Daily' AND column_name IN ('sector', 'industry')))
  AND coalesce(description, '') NOT LIKE '%''Undefined'' means%';

DO $postcheck$
BEGIN
    IF EXISTS (SELECT 1 FROM public."IDX_Stock_Universe" WHERE "Sector" = '0' OR "Industry" = '0')
       OR EXISTS (SELECT 1 FROM public."Universe_Equity_Description" WHERE "Sector" = '0' OR "Industry" = '0')
       OR EXISTS (SELECT 1 FROM public."Feature_01_Stock_Daily" WHERE sector = '0' OR industry = '0') THEN
        RAISE EXCEPTION 'A placeholder 0 remains';
    END IF;
    IF (SELECT count(*) FROM public."IDX_Stock_Universe" WHERE "Sector" = 'Undefined') <> 3 THEN
        RAISE EXCEPTION 'Expected 3 securities with Sector Undefined';
    END IF;
END
$postcheck$;

COMMIT;
