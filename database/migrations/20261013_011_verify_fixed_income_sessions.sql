BEGIN;

SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '2min';
SELECT pg_advisory_xact_lock(hashtextextended('fixed-income-verified-sessions-v4',0));

DO $guard$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM public."Fixed_Income_Market_Schedule"
                  WHERE market_code='ID' AND source_date_mapping='CURRENT_OR_PREVIOUS_BUSINESS_DAY')
       OR NOT EXISTS(SELECT 1 FROM public."Fixed_Income_Market_Schedule"
                     WHERE market_code='US' AND source_date_mapping='NEXT_BUSINESS_DAY') THEN
        RAISE EXCEPTION 'Unexpected fixed-income source mapping; inspect before migration';
    END IF;
END
$guard$;

ALTER TABLE public."Fixed_Income_Market_Schedule"
    ADD COLUMN provider_timezone_name text,
    ADD COLUMN provider_session text;

UPDATE public."Fixed_Income_Market_Schedule"
SET source_date_mapping='NEXT_BUSINESS_DAY',
    provider_timezone_name='America/New_York',
    provider_session=CASE market_code WHEN 'ID' THEN '1700-1700' WHEN 'US' THEN '1900-1730' END,
    updated_at=clock_timestamp()
WHERE market_code IN ('ID','US');

ALTER TABLE public."Fixed_Income_Market_Schedule"
    ALTER COLUMN provider_timezone_name SET NOT NULL,
    ALTER COLUMN provider_session SET NOT NULL,
    ADD CONSTRAINT "Fixed_Income_Market_Schedule_provider_timezone_check"
        CHECK(provider_timezone_name=btrim(provider_timezone_name) AND provider_timezone_name<>''),
    ADD CONSTRAINT "Fixed_Income_Market_Schedule_provider_session_check"
        CHECK(provider_session ~ '^[0-9]{4}-[0-9]{4}$');

COMMENT ON COLUMN public."Fixed_Income_Market_Schedule".provider_timezone_name IS
    'Verified TradingView symbol timezone; ingestion rejects unexpected provider metadata.';
COMMENT ON COLUMN public."Fixed_Income_Market_Schedule".provider_session IS
    'Verified TradingView daily session anchor, distinct from the economic-market close clock.';

UPDATE public."Table_Catalog"
SET definition='Fixed-income market close/finality policy and verified provider timezone, session and observation-date mapping.',
    source_code_paths=ARRAY(SELECT DISTINCT value FROM unnest(source_code_paths||ARRAY[
        'database/migrations/20261013_011_verify_fixed_income_sessions.sql',
        'apps/fixed-income-price-cron/fixed_income_update.py']) value ORDER BY value),
    updated_at=clock_timestamp()
WHERE table_schema='public' AND table_name='Fixed_Income_Market_Schedule';

INSERT INTO public."Column_Catalog"(
    table_schema,table_name,column_name,ordinal_position,data_type,is_nullable,
    default_expression,is_primary_key,definition,source_column_or_expression,unit,null_rule,
    source_code_paths,documentation_status
)
SELECT c.table_schema,c.table_name,c.column_name,c.ordinal_position,c.data_type,
       c.is_nullable='YES',c.column_default,false,
       CASE c.column_name
         WHEN 'provider_timezone_name' THEN 'Verified TradingView symbol timezone; reject a source metadata mismatch.'
         WHEN 'provider_session' THEN 'Verified TradingView session string; not the local economic-market closing clock.'
         ELSE 'Rule mapping the provider daily-session anchor to its observation date; both verified ID and US anchors currently map to the next business day.'
       END,
       'Verified TradingView symbol metadata and observation-date inspection',NULL,'Required.',
       ARRAY['database/migrations/20261013_011_verify_fixed_income_sessions.sql',
             'apps/fixed-income-price-cron/fixed_income_update.py'],'VERIFIED'
FROM information_schema.columns c
WHERE c.table_schema='public' AND c.table_name='Fixed_Income_Market_Schedule'
  AND c.column_name IN ('source_date_mapping','provider_timezone_name','provider_session')
ON CONFLICT(table_schema,table_name,column_name) DO UPDATE SET
    ordinal_position=EXCLUDED.ordinal_position,data_type=EXCLUDED.data_type,
    is_nullable=EXCLUDED.is_nullable,definition=EXCLUDED.definition,
    source_column_or_expression=EXCLUDED.source_column_or_expression,
    null_rule=EXCLUDED.null_rule,source_code_paths=EXCLUDED.source_code_paths,
    documentation_status=EXCLUDED.documentation_status,updated_at=clock_timestamp();

COMMIT;
