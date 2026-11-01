-- EXEC-FI-DATE (ERRORS M323, user go 2026-11-01: "Ok untuk koreksi 323 324"): the fixed-income date rule
-- PROVIDER_SESSION_START. A TradingView daily bar is labelled with the start of its session in the provider's zone
-- (provider_session, e.g. US 1900-1730: 19:00 New York the evening before, 23:00 UTC in EDT and 00:00 UTC of the
-- trading day in EST). NEXT_BUSINESS_DAY (UTC calendar date + 1 business day) was right only in EDT, so from
-- 2026-11-01 every US bar would have been dated one business day late (verification/fixed_income_audit/REPORT.md).
-- apps/fixed-income-price-cron/fixed_income_update.py resolve_bar_date reads the label in the provider zone against the
-- session start. Both markets move to it; the older values stay valid for a rollback.
-- Rollback: UPDATE public."Fixed_Income_Market_Schedule" SET source_date_mapping = 'NEXT_BUSINESS_DAY'; then restore the
-- CHECK of 20261012_002 (only after no row uses PROVIDER_SESSION_START).
BEGIN;

SET LOCAL lock_timeout = '10s';

DO $guard$
BEGIN
    IF EXISTS (SELECT 1 FROM public."Fixed_Income_Market_Schedule"
               WHERE provider_session IS NULL OR provider_session !~ '^[0-9]{4}-[0-9]{4}$'
                  OR provider_timezone_name IS NULL) THEN
        RAISE EXCEPTION 'every market needs provider_timezone_name and provider_session for PROVIDER_SESSION_START';
    END IF;
END
$guard$;

ALTER TABLE public."Fixed_Income_Market_Schedule"
    DROP CONSTRAINT "Fixed_Income_Market_Schedule_source_date_mapping_check",
    ADD CONSTRAINT "Fixed_Income_Market_Schedule_source_date_mapping_check"
        CHECK (source_date_mapping IN ('CURRENT_OR_PREVIOUS_BUSINESS_DAY', 'NEXT_BUSINESS_DAY', 'PROVIDER_SESSION_START'));

UPDATE public."Fixed_Income_Market_Schedule"
   SET source_date_mapping = 'PROVIDER_SESSION_START', updated_at = statement_timestamp()
 WHERE source_date_mapping <> 'PROVIDER_SESSION_START';

COMMENT ON COLUMN public."Fixed_Income_Market_Schedule".source_date_mapping IS
'Rule mapping a TradingView daily-bar label to the market observation date. PROVIDER_SESSION_START (in use since 2026-11-01): the label is the session start in provider_timezone_name; a label at or after the provider_session start opens the next day, weekends roll forward; independent of daylight saving. CURRENT_OR_PREVIOUS_BUSINESS_DAY and NEXT_BUSINESS_DAY read the UTC calendar date and are kept for rollback only (NEXT_BUSINESS_DAY is wrong in EST, ERRORS M323).';

UPDATE public."Column_Catalog"
   SET definition = 'Rule mapping a TradingView daily-bar label to the market observation date: PROVIDER_SESSION_START (in use) reads the label in provider_timezone_name against the provider_session start, so daylight saving cannot shift it; CURRENT_OR_PREVIOUS_BUSINESS_DAY and NEXT_BUSINESS_DAY (UTC calendar date) are kept for rollback only.',
       source_code_paths = ARRAY(SELECT DISTINCT x FROM unnest(coalesce(source_code_paths, ARRAY[]::text[]) || ARRAY[
           'database/migrations/20261101_002_fixed_income_session_start.sql', 'apps/fixed-income-price-cron/fixed_income_update.py']) x ORDER BY x)
 WHERE table_schema = 'public' AND table_name = 'Fixed_Income_Market_Schedule' AND column_name = 'source_date_mapping';

COMMIT;
