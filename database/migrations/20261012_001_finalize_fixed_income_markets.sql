BEGIN;

SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '15min';

SELECT pg_advisory_xact_lock(hashtextextended('fixed-income-finality-v1',0));

DO $guard$
BEGIN
    IF to_regclass('public."Universe_Fixed_income"') IS NULL
       OR to_regclass('public."Price_Fixed_Income"') IS NULL
       OR to_regclass('public."Monitoring_Fixed_Income"') IS NULL
       OR to_regclass('public."Feature_04_Technical_Indicator"') IS NULL THEN
        RAISE EXCEPTION 'Required fixed-income/Feature04 objects are absent';
    END IF;
    IF EXISTS(SELECT 1 FROM public."Feature04_Calculation_Queue" WHERE status='PROCESSING') THEN
        RAISE EXCEPTION 'Feature04 worker has an active claim';
    END IF;
    IF EXISTS(
        SELECT ticker,metric_type
        FROM public."Price_Fixed_Income"
        GROUP BY ticker,metric_type
        HAVING count(DISTINCT tradingview_symbol)<>1 OR count(DISTINCT value_unit)<>1
    ) THEN
        RAISE EXCEPTION 'Historical fixed-income symbol/unit mapping is ambiguous';
    END IF;
END
$guard$;

CREATE TABLE public."Fixed_Income_Market_Schedule" (
    market_code text PRIMARY KEY,
    country text NOT NULL UNIQUE,
    timezone_name text NOT NULL,
    session_close_local time without time zone NOT NULL,
    finality_delay_minutes integer NOT NULL,
    enabled boolean NOT NULL DEFAULT true,
    updated_at timestamptz NOT NULL DEFAULT statement_timestamp(),
    CONSTRAINT "Fixed_Income_Market_Schedule_code_check"
        CHECK(market_code=upper(btrim(market_code)) AND market_code<>''),
    CONSTRAINT "Fixed_Income_Market_Schedule_timezone_check"
        CHECK(timezone_name=btrim(timezone_name) AND timezone_name<>''),
    CONSTRAINT "Fixed_Income_Market_Schedule_delay_check"
        CHECK(finality_delay_minutes BETWEEN 0 AND 360)
);

INSERT INTO public."Fixed_Income_Market_Schedule"(
    market_code,country,timezone_name,session_close_local,finality_delay_minutes
) VALUES
    ('ID','Indonesia','Asia/Jakarta','16:00',60),
    ('US','United States','America/New_York','17:00',60);

ALTER TABLE public."Universe_Fixed_income"
    ADD COLUMN tradingview_symbol text,
    ADD COLUMN value_unit text;

WITH latest_mapping AS (
    SELECT DISTINCT ON (ticker,metric_type)
           ticker,metric_type,tradingview_symbol,value_unit
    FROM public."Price_Fixed_Income"
    ORDER BY ticker,metric_type,ingestion_time DESC,date DESC
)
UPDATE public."Universe_Fixed_income" u
SET tradingview_symbol=m.tradingview_symbol,
    value_unit=m.value_unit
FROM latest_mapping m
WHERE m.ticker=u.ticker AND m.metric_type=u.metric_type;

DO $mapping_guard$
BEGIN
    IF EXISTS(
        SELECT 1 FROM public."Universe_Fixed_income"
        WHERE tradingview_symbol IS NULL OR btrim(tradingview_symbol)=''
           OR value_unit IS NULL OR btrim(value_unit)=''
    ) THEN
        RAISE EXCEPTION 'Every fixed-income universe series needs a source symbol and unit';
    END IF;
    IF EXISTS(
        SELECT 1 FROM public."Universe_Fixed_income" u
        WHERE NOT EXISTS(
            SELECT 1 FROM public."Fixed_Income_Market_Schedule" s
            WHERE s.country=u.country
        )
    ) THEN
        RAISE EXCEPTION 'Every fixed-income universe country needs a market schedule';
    END IF;
END
$mapping_guard$;

ALTER TABLE public."Universe_Fixed_income"
    ALTER COLUMN tradingview_symbol SET NOT NULL,
    ALTER COLUMN value_unit SET NOT NULL,
    ADD CONSTRAINT "Universe_Fixed_income_symbol_metric_key"
        UNIQUE(tradingview_symbol,metric_type),
    ADD CONSTRAINT "Universe_Fixed_income_country_schedule_fkey"
        FOREIGN KEY(country) REFERENCES public."Fixed_Income_Market_Schedule"(country);

ALTER TABLE public."Price_Fixed_Income"
    ADD COLUMN source_bar_time timestamptz,
    ADD COLUMN market_close_at timestamptz,
    ADD COLUMN is_final boolean NOT NULL DEFAULT false,
    ADD COLUMN finalized_at timestamptz;

UPDATE public."Price_Fixed_Income" p
SET market_close_at=(p.date+s.session_close_local) AT TIME ZONE s.timezone_name,
    is_final=true,
    finalized_at=greatest(p.ingestion_time,(p.date+s.session_close_local) AT TIME ZONE s.timezone_name)
FROM public."Fixed_Income_Market_Schedule" s
WHERE s.country=p."Country";

ALTER TABLE public."Price_Fixed_Income"
    ALTER COLUMN market_close_at SET NOT NULL,
    ALTER COLUMN finalized_at SET NOT NULL,
    ALTER COLUMN is_final SET DEFAULT false,
    ADD CONSTRAINT "Price_Fixed_Income_finality_check"
        CHECK(NOT is_final OR finalized_at>=market_close_at),
    ADD CONSTRAINT "Price_Fixed_Income_universe_fkey"
        FOREIGN KEY(ticker,metric_type)
        REFERENCES public."Universe_Fixed_income"(ticker,metric_type);

ALTER TABLE public."Monitoring_Fixed_Income"
    ADD COLUMN market_code text,
    ADD COLUMN final_series integer NOT NULL DEFAULT 0,
    ADD COLUMN changed_series integer NOT NULL DEFAULT 0,
    ADD CONSTRAINT "Monitoring_Fixed_Income_market_fkey"
        FOREIGN KEY(market_code) REFERENCES public."Fixed_Income_Market_Schedule"(market_code),
    ADD CONSTRAINT "Monitoring_Fixed_Income_final_counts_check"
        CHECK(final_series>=0 AND changed_series>=0
              AND final_series<=queried_series AND changed_series<=final_series);

CREATE INDEX "Monitoring_Fixed_Income_market_target_idx"
    ON public."Monitoring_Fixed_Income"(market_code,target_date DESC,started_at DESC);
CREATE INDEX "Price_Fixed_Income_final_market_idx"
    ON public."Price_Fixed_Income"("Country",date DESC,ticker,metric_type)
    WHERE is_final AND "Timeframe"='1D';

CREATE OR REPLACE FUNCTION public.feature04_source_min_date(p_asset_type text,p_ticker text)
RETURNS date
LANGUAGE plpgsql
STABLE
AS $function$
DECLARE v_date date;
BEGIN
    IF p_asset_type='equity' THEN
        SELECT min(date) INTO v_date FROM public."Price_Stock_Indonesia_IDX"
        WHERE ticker=p_ticker AND timeframe='Daily';
    ELSIF p_asset_type='bonds' THEN
        SELECT min(date) INTO v_date FROM public."Price_Fixed_Income"
        WHERE ticker=p_ticker AND metric_type='price' AND "Timeframe"='1D' AND is_final;
    ELSE
        RAISE EXCEPTION 'Unsupported Feature04 asset_type %',p_asset_type;
    END IF;
    IF v_date IS NULL THEN RAISE EXCEPTION 'No Feature04 source history for %/%',p_asset_type,p_ticker; END IF;
    RETURN v_date;
END
$function$;

CREATE OR REPLACE FUNCTION public.enqueue_feature04_bond_price_row()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    IF TG_OP IN ('UPDATE','DELETE')
       AND OLD.metric_type='price' AND OLD."Timeframe"='1D' AND OLD.is_final THEN
        IF TG_OP='DELETE'
           OR ROW(OLD.ticker,OLD.date,OLD.open,OLD.high,OLD.low,OLD.close,OLD.source,
                  OLD.tradingview_symbol,OLD.is_final)
              IS DISTINCT FROM
              ROW(NEW.ticker,NEW.date,NEW.open,NEW.high,NEW.low,NEW.close,NEW.source,
                  NEW.tradingview_symbol,NEW.is_final)
           OR NEW.metric_type<>'price' OR NEW."Timeframe"<>'1D' OR NOT NEW.is_final THEN
            PERFORM public.enqueue_feature04_group(
                public.feature04_asset_type(OLD.ticker),OLD.ticker,OLD.date,'Daily',NULL
            );
        END IF;
    END IF;
    IF TG_OP IN ('INSERT','UPDATE')
       AND NEW.metric_type='price' AND NEW."Timeframe"='1D' AND NEW.is_final THEN
        IF TG_OP='INSERT'
           OR ROW(NEW.ticker,NEW.date,NEW.open,NEW.high,NEW.low,NEW.close,NEW.source,
                  NEW.tradingview_symbol,NEW.is_final)
              IS DISTINCT FROM
              ROW(OLD.ticker,OLD.date,OLD.open,OLD.high,OLD.low,OLD.close,OLD.source,
                  OLD.tradingview_symbol,OLD.is_final)
           OR OLD.metric_type<>'price' OR OLD."Timeframe"<>'1D' OR NOT OLD.is_final THEN
            PERFORM public.enqueue_feature04_group(
                public.feature04_asset_type(NEW.ticker),NEW.ticker,NEW.date,'Daily',NULL
            );
        END IF;
    END IF;
    RETURN NULL;
END
$function$;

CREATE OR REPLACE FUNCTION public.open_feature04_fixed_income_run()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_feature_execution_id text := 'f04-fi-'||NEW.execution_id::text;
    v_ticker text;
    v_members integer;
BEGIN
    INSERT INTO public."Monitoring_Feature04"(
        execution_id,source_execution_id,source_monitor_table,run_type,trigger_source,update_for_date,
        price_notification_required,eligible_tickers,status,started_at,updated_at
    ) VALUES(v_feature_execution_id,NEW.execution_id::text,'Monitoring_Fixed_Income',NEW.run_type,
             NEW.trigger_source,NEW.target_date,true,0,'OPEN',NEW.started_at,CURRENT_TIMESTAMP)
    ON CONFLICT(execution_id) DO NOTHING;

    FOR v_ticker IN
        SELECT DISTINCT p.ticker
        FROM public."Price_Fixed_Income" p
        WHERE p.metric_type='price' AND p."Timeframe"='1D' AND p.is_final
          AND p.date=NEW.target_date
          AND p.ingestion_time BETWEEN NEW.started_at AND NEW.finished_at
          AND (NEW.market_code IS NULL OR EXISTS(
              SELECT 1 FROM public."Universe_Fixed_income" u
              JOIN public."Fixed_Income_Market_Schedule" s ON s.country=u.country
              WHERE u.ticker=p.ticker AND u.metric_type='price'
                AND s.market_code=NEW.market_code
          ))
        ORDER BY p.ticker
    LOOP
        PERFORM public.enqueue_feature04_group('bonds',v_ticker,NEW.target_date,'Daily',v_feature_execution_id);
    END LOOP;

    SELECT count(*)::integer INTO v_members
    FROM public."Monitoring_Feature04_Ticker" WHERE execution_id=v_feature_execution_id;
    UPDATE public."Monitoring_Feature04" SET
        eligible_tickers=v_members,status=CASE WHEN v_members=0 THEN 'SKIPPED' ELSE 'READY' END,
        sealed_at=CURRENT_TIMESTAMP,finished_at=CASE WHEN v_members=0 THEN CURRENT_TIMESTAMP ELSE NULL END,
        updated_at=CURRENT_TIMESTAMP
    WHERE execution_id=v_feature_execution_id;
    INSERT INTO public."Feature04_Notification_Outbox"(
        event_id,execution_id,notification_type
    ) VALUES(gen_random_uuid(),v_feature_execution_id,'PRICE_FIXED_INCOME')
    ON CONFLICT(execution_id,notification_type) DO NOTHING;
    RETURN NULL;
END
$function$;

COMMENT ON TABLE public."Fixed_Income_Market_Schedule" IS
'Data-driven fixed-income market clock used to identify completed sessions before final daily candles are accepted.';
COMMENT ON COLUMN public."Universe_Fixed_income".tradingview_symbol IS
'Exact TradingView symbol for this ticker and metric series; maintained as universe data, never derived from a ticker list in application code.';
COMMENT ON COLUMN public."Universe_Fixed_income".value_unit IS
'Source unit stored on Price_Fixed_Income for this ticker and metric series.';
COMMENT ON COLUMN public."Price_Fixed_Income".source_bar_time IS
'Original timezone-aware TradingView bar timestamp; NULL only for legacy rows loaded before finality metadata existed.';
COMMENT ON COLUMN public."Price_Fixed_Income".market_close_at IS
'UTC instant of the configured local market close for this observation date.';
COMMENT ON COLUMN public."Price_Fixed_Income".is_final IS
'True only when the loader accepted the exact completed 1D source candle after the configured market-close delay.';
COMMENT ON COLUMN public."Price_Fixed_Income".finalized_at IS
'UTC time when this exact completed source candle was verified and stored.';
COMMENT ON COLUMN public."Monitoring_Fixed_Income".market_code IS
'Market partition processed by this execution; NULL only for monitoring history created by the legacy combined cron.';
COMMENT ON COLUMN public."Monitoring_Fixed_Income".final_series IS
'Exact-date source series verified as final during this execution.';
COMMENT ON COLUMN public."Monitoring_Fixed_Income".changed_series IS
'Final series whose material stored payload changed; only these writes can enqueue Feature04.';
COMMENT ON FUNCTION public.enqueue_feature04_bond_price_row() IS
'Enqueue a bonds ticker only when a final price/1D source row is inserted, corrected, deleted, or loses final status.';
COMMENT ON FUNCTION public.open_feature04_fixed_income_run() IS
'Bind materially changed final price/1D rows from one market execution to its Feature04 run and preserve price-before-Feature04 Telegram ordering.';

INSERT INTO public."Table_Catalog"(
 table_schema,table_name,category,definition,grain,primary_key_columns,source_system,
 source_tables,source_code_paths,update_rule,related_functions,documentation_status,
 readiness_mode,readiness_date_column,observation_date_column,data_available_at_column,
 availability_rule,point_in_time_status,historical_metadata_method
) VALUES (
 'public','Fixed_Income_Market_Schedule','Reference',
 'Fixed-income market timezone, closing clock and final-candle delay.',
 'one market',ARRAY['market_code'],'Operator-approved configuration',ARRAY[]::text[],
 ARRAY['database/migrations/20261012_001_finalize_fixed_income_markets.sql','apps/fixed-income-price-cron/fixed_income_update.py'],
 'Edit a market row when the official session clock changes; cron UTC schedules are maintained in Railway.',
 ARRAY[]::text[],'VERIFIED','NOT_APPLICABLE',NULL,NULL,'updated_at',
 'Current enabled row controls when a session may be finalized.','PARTIAL',
 'Current configuration is retained; historical configuration versions are not yet stored.'
)
ON CONFLICT(table_schema,table_name) DO UPDATE SET
 definition=EXCLUDED.definition,grain=EXCLUDED.grain,primary_key_columns=EXCLUDED.primary_key_columns,
 source_system=EXCLUDED.source_system,source_code_paths=EXCLUDED.source_code_paths,
 update_rule=EXCLUDED.update_rule,documentation_status=EXCLUDED.documentation_status,
 availability_rule=EXCLUDED.availability_rule,point_in_time_status=EXCLUDED.point_in_time_status,
 historical_metadata_method=EXCLUDED.historical_metadata_method,updated_at=CURRENT_TIMESTAMP;

UPDATE public."Table_Catalog" SET
    definition=CASE table_name
      WHEN 'Universe_Fixed_income' THEN 'Approved fixed-income series with explicit source symbol, unit and market-country membership.'
      WHEN 'Price_Fixed_Income' THEN 'Final daily fixed-income OHLC observations with source-bar and market-close finality evidence.'
      WHEN 'Monitoring_Fixed_Income' THEN 'One market-specific fixed-income daily or recovery execution summary.'
      ELSE definition END,
    grain=CASE table_name
      WHEN 'Monitoring_Fixed_Income' THEN 'one market execution'
      ELSE grain END,
    source_code_paths=ARRAY(
      SELECT DISTINCT x FROM unnest(source_code_paths||ARRAY[
        'database/migrations/20261012_001_finalize_fixed_income_markets.sql',
        'apps/fixed-income-price-cron/fixed_income_update.py'
      ]) x ORDER BY x
    ),
    update_rule=CASE table_name
      WHEN 'Universe_Fixed_income' THEN 'Universe rows supply every source symbol and unit; the loader contains no ticker roster.'
      WHEN 'Price_Fixed_Income' THEN 'Market-specific daily and recovery jobs re-query the latest completed session; only exact final candles are material-upserted.'
      WHEN 'Monitoring_Fixed_Income' THEN 'One row is inserted after every market-specific daily/recovery attempt.'
      ELSE update_rule END,
    related_functions=CASE table_name
      WHEN 'Price_Fixed_Income' THEN ARRAY['enqueue_feature04_bond_price_row()']
      WHEN 'Monitoring_Fixed_Income' THEN ARRAY['open_feature04_fixed_income_run()']
      ELSE related_functions END,
    documentation_status='VERIFIED',updated_at=CURRENT_TIMESTAMP
WHERE table_schema='public'
  AND table_name IN ('Universe_Fixed_income','Price_Fixed_Income','Monitoring_Fixed_Income');

INSERT INTO public."Column_Catalog"(
 table_schema,table_name,column_name,ordinal_position,data_type,is_nullable,default_expression,
 is_primary_key,definition,source_column_or_expression,unit,null_rule,source_code_paths,documentation_status
)
SELECT c.table_schema,c.table_name,c.column_name,c.ordinal_position,c.data_type,c.is_nullable='YES',
       c.column_default,EXISTS(
         SELECT 1 FROM pg_constraint k,unnest(k.conkey) key(attnum)
         WHERE k.conrelid=(quote_ident(c.table_schema)||'.'||quote_ident(c.table_name))::regclass
           AND k.contype='p' AND key.attnum=(SELECT attnum FROM pg_attribute
             WHERE attrelid=k.conrelid AND attname=c.column_name)
       ),
       CASE c.table_name||'.'||c.column_name
         WHEN 'Universe_Fixed_income.tradingview_symbol' THEN 'Exact TradingView symbol for the universe series.'
         WHEN 'Universe_Fixed_income.value_unit' THEN 'Source unit for the universe series.'
         WHEN 'Price_Fixed_Income.source_bar_time' THEN 'Original TradingView daily bar timestamp.'
         WHEN 'Price_Fixed_Income.market_close_at' THEN 'Configured market close instant for the observation date.'
         WHEN 'Price_Fixed_Income.is_final' THEN 'Whether the exact daily candle was accepted after market close.'
         WHEN 'Price_Fixed_Income.finalized_at' THEN 'Time this exact final candle was verified.'
         WHEN 'Monitoring_Fixed_Income.market_code' THEN 'Market processed by the execution.'
         WHEN 'Monitoring_Fixed_Income.final_series' THEN 'Number of exact-date final series verified.'
         WHEN 'Monitoring_Fixed_Income.changed_series' THEN 'Number of material source payload changes.'
         ELSE 'Fixed-income market schedule configuration.' END,
       CASE c.column_name
         WHEN 'market_close_at' THEN '(date + session_close_local) AT TIME ZONE timezone_name'
         WHEN 'is_final' THEN 'exact target candle and current time >= market_close_at + finality delay'
         ELSE c.column_name END,
       CASE WHEN c.column_name LIKE '%minutes' THEN 'minutes'
            WHEN c.column_name LIKE '%_at' OR c.column_name LIKE '%time%' THEN 'timestamp/time'
            ELSE NULL END,
       CASE WHEN c.table_name='Price_Fixed_Income' AND c.column_name='source_bar_time'
              THEN 'NULL only for legacy rows loaded before this metadata existed.'
            WHEN c.table_name='Monitoring_Fixed_Income' AND c.column_name='market_code'
              THEN 'NULL only for legacy combined-cron monitoring rows.'
            WHEN c.is_nullable='YES' THEN 'May be NULL under the documented lifecycle.'
            ELSE 'Required.' END,
       ARRAY['database/migrations/20261012_001_finalize_fixed_income_markets.sql',
             'apps/fixed-income-price-cron/fixed_income_update.py'],'VERIFIED'
FROM information_schema.columns c
WHERE c.table_schema='public' AND (
  c.table_name='Fixed_Income_Market_Schedule'
  OR (c.table_name='Universe_Fixed_income' AND c.column_name IN ('tradingview_symbol','value_unit'))
  OR (c.table_name='Price_Fixed_Income' AND c.column_name IN ('source_bar_time','market_close_at','is_final','finalized_at'))
  OR (c.table_name='Monitoring_Fixed_Income' AND c.column_name IN ('market_code','final_series','changed_series'))
)
ON CONFLICT(table_schema,table_name,column_name) DO UPDATE SET
 ordinal_position=EXCLUDED.ordinal_position,data_type=EXCLUDED.data_type,is_nullable=EXCLUDED.is_nullable,
 default_expression=EXCLUDED.default_expression,definition=EXCLUDED.definition,
 source_column_or_expression=EXCLUDED.source_column_or_expression,unit=EXCLUDED.unit,
 null_rule=EXCLUDED.null_rule,source_code_paths=EXCLUDED.source_code_paths,
 documentation_status=EXCLUDED.documentation_status,updated_at=CURRENT_TIMESTAMP;

UPDATE public."Feature_Catalog" SET
    refresh_trigger='Committed final source price change through the Feature04 queue',
    dependency_rule='Full available chronological final price history per asset_type/ticker through output end; no future bars; partitions remain isolated',
    source_columns=replace(source_columns,'bonds volume may be NULL','bonds volume may be NULL; bonds require is_final=true'),
    validation_evidence=ARRAY(
      SELECT DISTINCT x FROM unnest(validation_evidence||ARRAY[
        'apps/fixed-income-price-cron/test_fixed_income_update.py',
        'verification/feature04/FIXED_INCOME_FINALITY.md'
      ]) x ORDER BY x
    ),
    updated_at=CURRENT_TIMESTAMP
WHERE feature_table='Feature_04_Technical_Indicator' AND is_active;

DO $verify$
BEGIN
    IF (SELECT count(*) FROM public."Fixed_Income_Market_Schedule" WHERE enabled)<>2 THEN
        RAISE EXCEPTION 'Expected two enabled fixed-income markets';
    END IF;
    IF EXISTS(SELECT 1 FROM public."Universe_Fixed_income" WHERE tradingview_symbol IS NULL OR value_unit IS NULL) THEN
        RAISE EXCEPTION 'Fixed-income source mapping remains incomplete';
    END IF;
    IF EXISTS(SELECT 1 FROM public."Price_Fixed_Income" WHERE NOT is_final OR market_close_at IS NULL OR finalized_at IS NULL) THEN
        RAISE EXCEPTION 'Legacy fixed-income rows were not initialized as completed sessions';
    END IF;
    IF NOT EXISTS(
      SELECT 1 FROM pg_indexes
      WHERE schemaname='public' AND indexname='Price_Fixed_Income_final_market_idx'
    ) THEN RAISE EXCEPTION 'Final fixed-income market index is absent'; END IF;
END
$verify$;

COMMIT;
