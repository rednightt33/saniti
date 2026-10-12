BEGIN;

SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '5min';

SELECT pg_advisory_xact_lock(hashtextextended('fixed-income-source-date-mapping-v1',0));

DO $guard$
BEGIN
    IF to_regclass('public."Fixed_Income_Market_Schedule"') IS NULL THEN
        RAISE EXCEPTION 'Fixed_Income_Market_Schedule is absent';
    END IF;
    IF EXISTS(
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public'
          AND table_name='Fixed_Income_Market_Schedule'
          AND column_name='source_date_mapping'
    ) THEN
        RAISE EXCEPTION 'source_date_mapping already exists';
    END IF;
END
$guard$;

ALTER TABLE public."Fixed_Income_Market_Schedule"
    ADD COLUMN source_date_mapping text;

UPDATE public."Fixed_Income_Market_Schedule"
SET source_date_mapping=CASE market_code
    WHEN 'ID' THEN 'CURRENT_OR_PREVIOUS_BUSINESS_DAY'
    WHEN 'US' THEN 'NEXT_BUSINESS_DAY'
END;

ALTER TABLE public."Fixed_Income_Market_Schedule"
    ALTER COLUMN source_date_mapping SET NOT NULL,
    ADD CONSTRAINT "Fixed_Income_Market_Schedule_source_date_mapping_check"
        CHECK(source_date_mapping IN (
            'CURRENT_OR_PREVIOUS_BUSINESS_DAY',
            'NEXT_BUSINESS_DAY'
        ));

COMMENT ON COLUMN public."Fixed_Income_Market_Schedule".source_date_mapping IS
'Data-driven rule that maps a TradingView UTC daily-bar label to the market observation date.';

UPDATE public."Table_Catalog"
SET definition='Fixed-income market timezone, closing clock, final-candle delay and source-label date mapping.',
    source_code_paths=ARRAY(
      SELECT DISTINCT x FROM unnest(source_code_paths||ARRAY[
        'database/migrations/20261012_002_configure_fixed_income_source_dates.sql',
        'apps/fixed-income-price-cron/fixed_income_update.py'
      ]) x ORDER BY x
    ),
    update_rule='Edit a market row when its official session clock or provider daily-bar label convention changes; cron UTC schedules are maintained in Railway.',
    updated_at=CURRENT_TIMESTAMP
WHERE table_schema='public' AND table_name='Fixed_Income_Market_Schedule';

INSERT INTO public."Column_Catalog"(
 table_schema,table_name,column_name,ordinal_position,data_type,is_nullable,default_expression,
 is_primary_key,definition,source_column_or_expression,unit,null_rule,source_code_paths,
 documentation_status
)
SELECT c.table_schema,c.table_name,c.column_name,c.ordinal_position,c.data_type,false,
       c.column_default,false,
       'Rule that maps the raw TradingView UTC daily-bar label to this market session date.',
       'Operator-approved market configuration',NULL,'Required.',
       ARRAY[
         'database/migrations/20261012_002_configure_fixed_income_source_dates.sql',
         'apps/fixed-income-price-cron/fixed_income_update.py'
       ],'VERIFIED'
FROM information_schema.columns c
WHERE c.table_schema='public'
  AND c.table_name='Fixed_Income_Market_Schedule'
  AND c.column_name='source_date_mapping'
ON CONFLICT(table_schema,table_name,column_name) DO UPDATE SET
 ordinal_position=EXCLUDED.ordinal_position,data_type=EXCLUDED.data_type,
 is_nullable=EXCLUDED.is_nullable,default_expression=EXCLUDED.default_expression,
 definition=EXCLUDED.definition,source_column_or_expression=EXCLUDED.source_column_or_expression,
 unit=EXCLUDED.unit,null_rule=EXCLUDED.null_rule,
 source_code_paths=EXCLUDED.source_code_paths,
 documentation_status=EXCLUDED.documentation_status,updated_at=CURRENT_TIMESTAMP;

DO $verify$
BEGIN
    IF (SELECT count(*) FROM public."Fixed_Income_Market_Schedule"
        WHERE source_date_mapping='CURRENT_OR_PREVIOUS_BUSINESS_DAY')<>1 THEN
        RAISE EXCEPTION 'Expected one current/previous-business-day market';
    END IF;
    IF (SELECT count(*) FROM public."Fixed_Income_Market_Schedule"
        WHERE source_date_mapping='NEXT_BUSINESS_DAY')<>1 THEN
        RAISE EXCEPTION 'Expected one next-business-day market';
    END IF;
END
$verify$;

COMMIT;
