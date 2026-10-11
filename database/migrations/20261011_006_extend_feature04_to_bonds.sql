BEGIN;

SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '15min';

DO $guard$
BEGIN
    IF to_regclass('public."Feature04_Technical_Indicator"') IS NULL
       OR to_regclass('public."Price_Fixed_Income"') IS NULL
       OR to_regclass('public."Universe_Fixed_income"') IS NULL
       OR to_regclass('public."Monitoring_Fixed_Income"') IS NULL THEN
        RAISE EXCEPTION 'Feature04 or fixed-income source objects are absent';
    END IF;
    IF EXISTS(SELECT 1 FROM public."Feature04_Calculation_Queue" WHERE status='PROCESSING') THEN
        RAISE EXCEPTION 'Feature04 worker has an active claim';
    END IF;
    IF EXISTS(
        SELECT 1 FROM public."IDX_Stock_Universe" e
        JOIN public."Universe_Fixed_income" b ON b.ticker=e."Ticker"
    ) THEN
        RAISE EXCEPTION 'A ticker exists in both equity and fixed-income universes';
    END IF;
    IF EXISTS(
        SELECT 1 FROM public."Feature04_Technical_Indicator" f
        WHERE NOT EXISTS(SELECT 1 FROM public."IDX_Stock_Universe" u WHERE u."Ticker"=f.ticker)
    ) THEN
        RAISE EXCEPTION 'An existing Feature04 ticker is absent from IDX_Stock_Universe';
    END IF;
END
$guard$;

CREATE FUNCTION public.feature04_asset_type(p_ticker text)
RETURNS text
LANGUAGE plpgsql
STABLE
AS $function$
DECLARE
    v_equity boolean;
    v_bonds boolean;
BEGIN
    SELECT EXISTS(SELECT 1 FROM public."IDX_Stock_Universe" WHERE "Ticker"=p_ticker),
           EXISTS(SELECT 1 FROM public."Universe_Fixed_income" WHERE ticker=p_ticker)
    INTO v_equity,v_bonds;
    IF v_equity = v_bonds THEN
        RAISE EXCEPTION 'Ticker % must exist in exactly one approved asset universe',p_ticker;
    END IF;
    RETURN CASE WHEN v_equity THEN 'equity' ELSE 'bonds' END;
END
$function$;

CREATE FUNCTION public.feature04_source_min_date(p_asset_type text,p_ticker text)
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
        WHERE ticker=p_ticker AND metric_type='price' AND "Timeframe"='1D';
    ELSE
        RAISE EXCEPTION 'Unsupported Feature04 asset_type %',p_asset_type;
    END IF;
    IF v_date IS NULL THEN RAISE EXCEPTION 'No Feature04 source history for %/%',p_asset_type,p_ticker; END IF;
    RETURN v_date;
END
$function$;

ALTER TABLE public."Feature04_Technical_Indicator" ADD COLUMN asset_type text;
UPDATE public."Feature04_Technical_Indicator" f
SET asset_type=public.feature04_asset_type(f.ticker);
ALTER TABLE public."Feature04_Technical_Indicator"
    ALTER COLUMN asset_type SET NOT NULL,
    ADD CONSTRAINT "Feature04_Technical_Indicator_asset_type_check"
        CHECK(asset_type IN ('equity','bonds')),
    DROP CONSTRAINT "Feature04_Technical_Indicator_pkey",
    ADD CONSTRAINT "Feature04_Technical_Indicator_pkey"
        PRIMARY KEY(ticker,trade_date,timeframe,asset_type);

ALTER TABLE public."Feature04_Calculation_Queue" ADD COLUMN asset_type text;
UPDATE public."Feature04_Calculation_Queue" SET asset_type=public.feature04_asset_type(ticker);
ALTER TABLE public."Feature04_Calculation_Queue"
    ALTER COLUMN asset_type SET NOT NULL,
    ADD CONSTRAINT "Feature04_Calculation_Queue_asset_type_check" CHECK(asset_type IN ('equity','bonds')),
    DROP CONSTRAINT "Feature04_Calculation_Queue_pkey",
    ADD CONSTRAINT "Feature04_Calculation_Queue_pkey" PRIMARY KEY(asset_type,ticker,timeframe);

ALTER TABLE public."Feature04_Column_Status" ADD COLUMN asset_type text;
UPDATE public."Feature04_Column_Status" SET asset_type=public.feature04_asset_type(ticker);
ALTER TABLE public."Feature04_Column_Status"
    ALTER COLUMN asset_type SET NOT NULL,
    ADD CONSTRAINT "Feature04_Column_Status_asset_type_check" CHECK(asset_type IN ('equity','bonds')),
    DROP CONSTRAINT "Feature04_Column_Status_pkey",
    ADD CONSTRAINT "Feature04_Column_Status_pkey" PRIMARY KEY(asset_type,ticker,timeframe,feature_column);

ALTER TABLE public."Feature04_Calculation_Log" ADD COLUMN asset_type text;
UPDATE public."Feature04_Calculation_Log" SET asset_type=public.feature04_asset_type(ticker);
ALTER TABLE public."Feature04_Calculation_Log"
    ALTER COLUMN asset_type SET NOT NULL,
    ADD CONSTRAINT "Feature04_Calculation_Log_asset_type_check" CHECK(asset_type IN ('equity','bonds'));

ALTER TABLE public."Monitoring_Feature04_Ticker" ADD COLUMN asset_type text;
UPDATE public."Monitoring_Feature04_Ticker" SET asset_type=public.feature04_asset_type(ticker);
ALTER TABLE public."Monitoring_Feature04_Ticker"
    ALTER COLUMN asset_type SET NOT NULL,
    ADD CONSTRAINT "Monitoring_Feature04_Ticker_asset_type_check" CHECK(asset_type IN ('equity','bonds')),
    DROP CONSTRAINT "Monitoring_Feature04_Ticker_pkey",
    ADD CONSTRAINT "Monitoring_Feature04_Ticker_pkey" PRIMARY KEY(execution_id,asset_type,ticker,timeframe);

ALTER TABLE public."Feature04_Retry_Request" ADD COLUMN asset_type text;
UPDATE public."Feature04_Retry_Request" SET asset_type=public.feature04_asset_type(ticker);
ALTER TABLE public."Feature04_Retry_Request"
    ADD CONSTRAINT "Feature04_Retry_Request_asset_type_check"
        CHECK(asset_type IS NULL OR asset_type IN ('equity','bonds'));

ALTER TABLE public."Monitoring_Feature04"
    ADD COLUMN source_monitor_table text NOT NULL DEFAULT 'Monitoring_Price_ALL',
    ADD CONSTRAINT "Monitoring_Feature04_source_monitor_table_check"
        CHECK(source_monitor_table IN ('Monitoring_Price_ALL','Monitoring_Fixed_Income'));

DROP INDEX public."Feature04_Column_Status_failure_idx";
CREATE INDEX "Feature04_Column_Status_failure_idx"
    ON public."Feature04_Column_Status"(status,updated_at DESC,asset_type,ticker,feature_column)
    WHERE status IN ('FAILED','BLOCKED');
DROP INDEX public."Feature04_Calculation_Log_ticker_time_idx";
CREATE INDEX "Feature04_Calculation_Log_ticker_time_idx"
    ON public."Feature04_Calculation_Log"(asset_type,ticker,started_at DESC);
DROP INDEX public."Monitoring_Feature04_Ticker_pending_idx";
CREATE INDEX "Monitoring_Feature04_Ticker_pending_idx"
    ON public."Monitoring_Feature04_Ticker"(asset_type,ticker,timeframe,required_generation)
    WHERE status IN ('PENDING','PROCESSING');

DROP TRIGGER "Price_Stock_Indonesia_IDX_enqueue_feature04" ON public."Price_Stock_Indonesia_IDX";
DROP FUNCTION public.enqueue_feature04_price_row();
DROP FUNCTION public.enqueue_feature04_group(text,date,text,text);

CREATE FUNCTION public.enqueue_feature04_group(
    p_asset_type text,p_ticker text,p_dirty_date date,p_timeframe text,
    p_execution_id text DEFAULT NULL
)
RETURNS bigint
LANGUAGE plpgsql
AS $function$
DECLARE v_generation bigint;
BEGIN
    IF p_asset_type<>public.feature04_asset_type(p_ticker) THEN
        RAISE EXCEPTION 'asset_type does not match approved universe for %',p_ticker;
    END IF;
    IF p_dirty_date IS NULL OR p_timeframe<>'Daily' THEN
        RAISE EXCEPTION 'Valid date and Daily timeframe are required';
    END IF;
    INSERT INTO public."Feature04_Calculation_Queue"(
        asset_type,ticker,timeframe,dirty_from_date,requested_generation,completed_generation,
        work_revision,requested_columns,origin_execution_id,status,next_attempt_at
    ) VALUES(p_asset_type,p_ticker,p_timeframe,p_dirty_date,1,0,1,NULL,p_execution_id,'PENDING',CURRENT_TIMESTAMP)
    ON CONFLICT(asset_type,ticker,timeframe) DO UPDATE SET
        dirty_from_date=least(public."Feature04_Calculation_Queue".dirty_from_date,EXCLUDED.dirty_from_date),
        requested_generation=public."Feature04_Calculation_Queue".requested_generation+1,
        work_revision=public."Feature04_Calculation_Queue".work_revision+1,
        requested_columns=NULL,origin_execution_id=EXCLUDED.origin_execution_id,status='PENDING',
        source_attempt_count=0,next_attempt_at=CURRENT_TIMESTAMP,claimed_at=NULL,claim_token=NULL,
        claim_expires_at=NULL,last_error_code=NULL,last_error=NULL,completed_at=NULL,
        updated_at=CURRENT_TIMESTAMP
    RETURNING requested_generation INTO v_generation;
    IF p_execution_id IS NOT NULL THEN
        INSERT INTO public."Monitoring_Feature04_Ticker"(
            execution_id,asset_type,ticker,timeframe,required_generation,requested_columns,status
        ) VALUES(p_execution_id,p_asset_type,p_ticker,p_timeframe,v_generation,NULL,'PENDING')
        ON CONFLICT(execution_id,asset_type,ticker,timeframe) DO UPDATE SET
            required_generation=greatest(public."Monitoring_Feature04_Ticker".required_generation,EXCLUDED.required_generation),
            requested_columns=NULL,status='PENDING',updated_at=CURRENT_TIMESTAMP;
    END IF;
    RETURN v_generation;
END
$function$;

CREATE FUNCTION public.enqueue_feature04_equity_price_row()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE v_execution_id text := nullif(current_setting('saniti.feature04_execution_id',true),'');
BEGIN
    IF TG_OP='DELETE' THEN
        PERFORM public.enqueue_feature04_group(public.feature04_asset_type(OLD.ticker),OLD.ticker,OLD.date,'Daily',v_execution_id);
        RETURN NULL;
    END IF;
    IF TG_OP='INSERT' OR ROW(NEW.ticker,NEW.date,NEW.open,NEW.high,NEW.low,NEW.close,NEW.volume,NEW.source,NEW.tradingview_symbol)
                         IS DISTINCT FROM ROW(OLD.ticker,OLD.date,OLD.open,OLD.high,OLD.low,OLD.close,OLD.volume,OLD.source,OLD.tradingview_symbol) THEN
        IF TG_OP='UPDATE' AND ROW(OLD.ticker,OLD.date) IS DISTINCT FROM ROW(NEW.ticker,NEW.date) THEN
            PERFORM public.enqueue_feature04_group(public.feature04_asset_type(OLD.ticker),OLD.ticker,OLD.date,'Daily',v_execution_id);
        END IF;
        PERFORM public.enqueue_feature04_group(public.feature04_asset_type(NEW.ticker),NEW.ticker,NEW.date,'Daily',v_execution_id);
    END IF;
    RETURN NULL;
END
$function$;

CREATE TRIGGER "Price_Stock_Indonesia_IDX_enqueue_feature04"
AFTER INSERT OR UPDATE OR DELETE ON public."Price_Stock_Indonesia_IDX"
FOR EACH ROW EXECUTE FUNCTION public.enqueue_feature04_equity_price_row();

CREATE FUNCTION public.enqueue_feature04_bond_price_row()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    IF TG_OP IN ('UPDATE','DELETE') AND OLD.metric_type='price' AND OLD."Timeframe"='1D' THEN
        IF TG_OP='DELETE' OR ROW(OLD.ticker,OLD.date,OLD.open,OLD.high,OLD.low,OLD.close,OLD.source,OLD.tradingview_symbol)
                            IS DISTINCT FROM ROW(NEW.ticker,NEW.date,NEW.open,NEW.high,NEW.low,NEW.close,NEW.source,NEW.tradingview_symbol)
           OR NEW.metric_type<>'price' OR NEW."Timeframe"<>'1D' THEN
            PERFORM public.enqueue_feature04_group(public.feature04_asset_type(OLD.ticker),OLD.ticker,OLD.date,'Daily',NULL);
        END IF;
    END IF;
    IF TG_OP IN ('INSERT','UPDATE') AND NEW.metric_type='price' AND NEW."Timeframe"='1D' THEN
        IF TG_OP='INSERT' OR ROW(NEW.ticker,NEW.date,NEW.open,NEW.high,NEW.low,NEW.close,NEW.source,NEW.tradingview_symbol)
                            IS DISTINCT FROM ROW(OLD.ticker,OLD.date,OLD.open,OLD.high,OLD.low,OLD.close,OLD.source,OLD.tradingview_symbol)
           OR OLD.metric_type<>'price' OR OLD."Timeframe"<>'1D' THEN
            PERFORM public.enqueue_feature04_group(public.feature04_asset_type(NEW.ticker),NEW.ticker,NEW.date,'Daily',NULL);
        END IF;
    END IF;
    RETURN NULL;
END
$function$;

CREATE TRIGGER "Price_Fixed_Income_enqueue_feature04"
AFTER INSERT OR UPDATE OR DELETE ON public."Price_Fixed_Income"
FOR EACH ROW EXECUTE FUNCTION public.enqueue_feature04_bond_price_row();

CREATE OR REPLACE FUNCTION public.request_feature04_retry(
    p_chat_id bigint,p_telegram_update_id bigint,p_ticker text,
    p_columns text[] DEFAULT NULL,p_source_execution_id text DEFAULT NULL
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path=public,pg_temp
AS $function$
DECLARE
    v_request_id uuid := gen_random_uuid();
    v_child_execution_id text := 'f04-retry-'||v_request_id::text;
    v_asset_type text;
    v_generation bigint;
    v_revision bigint;
    v_invalid text[];
    v_scope text := CASE WHEN p_columns IS NULL THEN 'TICKER' ELSE 'COLUMN' END;
BEGIN
    IF p_ticker IS NULL OR p_ticker<>upper(btrim(p_ticker)) OR p_ticker='' THEN
        RAISE EXCEPTION 'A canonical ticker is required';
    END IF;
    v_asset_type := public.feature04_asset_type(p_ticker);
    PERFORM public.feature04_source_min_date(v_asset_type,p_ticker);
    IF p_columns IS NOT NULL THEN
        SELECT array_agg(value) INTO v_invalid FROM unnest(p_columns) value
        WHERE NOT value=ANY(public.feature04_output_columns());
        IF v_invalid IS NOT NULL THEN RAISE EXCEPTION 'Unsupported Feature04 columns: %',v_invalid; END IF;
        IF NOT EXISTS(
            SELECT 1 FROM public."Feature04_Column_Status"
            WHERE asset_type=v_asset_type AND ticker=p_ticker AND timeframe='Daily'
              AND feature_column=ANY(p_columns) AND status IN ('FAILED','BLOCKED')
        ) THEN RAISE EXCEPTION 'Selected columns have no active failure for %/%',v_asset_type,p_ticker; END IF;
    ELSIF NOT EXISTS(
        SELECT 1 FROM public."Feature04_Calculation_Queue"
        WHERE asset_type=v_asset_type AND ticker=p_ticker AND timeframe='Daily' AND status='FAILED'
        UNION ALL
        SELECT 1 FROM public."Feature04_Column_Status"
        WHERE asset_type=v_asset_type AND ticker=p_ticker AND timeframe='Daily' AND status IN ('FAILED','BLOCKED')
    ) THEN RAISE EXCEPTION 'Ticker %/% has no active Feature04 failure',v_asset_type,p_ticker;
    END IF;
    INSERT INTO public."Feature04_Calculation_Queue"(
        asset_type,ticker,timeframe,dirty_from_date,requested_generation,completed_generation,
        work_revision,requested_columns,status,next_attempt_at
    ) VALUES(v_asset_type,p_ticker,'Daily',public.feature04_source_min_date(v_asset_type,p_ticker),
             1,0,1,p_columns,'PENDING',CURRENT_TIMESTAMP)
    ON CONFLICT(asset_type,ticker,timeframe) DO UPDATE SET
        dirty_from_date=least(public."Feature04_Calculation_Queue".dirty_from_date,EXCLUDED.dirty_from_date),
        work_revision=public."Feature04_Calculation_Queue".work_revision+1,
        requested_columns=CASE
          WHEN public."Feature04_Calculation_Queue".requested_columns IS NULL OR EXCLUDED.requested_columns IS NULL THEN NULL
          ELSE ARRAY(SELECT DISTINCT value FROM unnest(public."Feature04_Calculation_Queue".requested_columns||EXCLUDED.requested_columns) value ORDER BY value)
        END,status='PENDING',source_attempt_count=0,next_attempt_at=CURRENT_TIMESTAMP,
        claimed_at=NULL,claim_token=NULL,claim_expires_at=NULL,last_error_code=NULL,last_error=NULL,
        completed_at=NULL,updated_at=CURRENT_TIMESTAMP
    RETURNING requested_generation,work_revision INTO v_generation,v_revision;
    INSERT INTO public."Feature04_Retry_Request"(
        request_id,telegram_update_id,chat_id,request_scope,source_execution_id,asset_type,ticker,
        requested_columns,source_generation,work_revision,status,child_execution_id
    ) VALUES(v_request_id,p_telegram_update_id,p_chat_id,v_scope,p_source_execution_id,v_asset_type,p_ticker,
             p_columns,v_generation,v_revision,'PENDING',v_child_execution_id);
    INSERT INTO public."Monitoring_Feature04"(
        execution_id,source_execution_id,source_monitor_table,run_type,trigger_source,
        price_notification_required,price_notification_sent_at,eligible_tickers,status
    ) VALUES(v_child_execution_id,p_source_execution_id,'Monitoring_Price_ALL',
             CASE WHEN p_columns IS NULL THEN 'RETRY_TICKER' ELSE 'RETRY_COLUMN' END,
             'TELEGRAM',false,CURRENT_TIMESTAMP,1,'READY');
    INSERT INTO public."Monitoring_Feature04_Ticker"(
        execution_id,asset_type,ticker,timeframe,required_generation,requested_columns,status,retry_request_id
    ) VALUES(v_child_execution_id,v_asset_type,p_ticker,'Daily',v_generation,p_columns,'PENDING',v_request_id);
    RETURN v_request_id;
END
$function$;

CREATE FUNCTION public.open_feature04_fixed_income_run()
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
        WHERE p.metric_type='price' AND p."Timeframe"='1D' AND p.date=NEW.target_date
          AND p.ingestion_time BETWEEN NEW.started_at AND NEW.finished_at
          AND EXISTS(SELECT 1 FROM public."Universe_Fixed_income" u WHERE u.ticker=p.ticker)
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

CREATE TRIGGER "Monitoring_Fixed_Income_open_feature04"
AFTER INSERT ON public."Monitoring_Fixed_Income"
FOR EACH ROW EXECUTE FUNCTION public.open_feature04_fixed_income_run();

COMMENT ON COLUMN public."Feature04_Technical_Indicator".asset_type IS
'Universe-derived asset class: equity from IDX_Stock_Universe; bonds from Universe_Fixed_income.';
COMMENT ON FUNCTION public.feature04_asset_type(text) IS
'Classify one ticker from live universe membership; raises when absent or present in both universes.';
COMMENT ON FUNCTION public.open_feature04_fixed_income_run() IS
'Open and seal a bonds Feature04 run from one committed Monitoring_Fixed_Income row and enqueue price notification first.';

UPDATE public."Table_Catalog" SET
    definition='Cross-asset daily causal technical indicators from classified equity or bonds price OHLC.',
    grain='asset_type x ticker x observed trading date x Daily timeframe',
    primary_key_columns=ARRAY['ticker','trade_date','timeframe','asset_type'],
    source_tables=ARRAY['Price_Stock_Indonesia_IDX','IDX_Stock_Universe','Price_Fixed_Income','Universe_Fixed_income'],
    update_rule='Committed source price changes enqueue a universe-classified full-history ticker replay.',
    related_functions=ARRAY['feature04_asset_type(text)','feature04_source_min_date(text,text)'],
    updated_at=CURRENT_TIMESTAMP
WHERE table_schema='public' AND table_name='Feature04_Technical_Indicator';

UPDATE public."Table_Catalog" SET
    grain=CASE table_name
      WHEN 'Feature04_Calculation_Queue' THEN 'asset_type x ticker x timeframe'
      WHEN 'Feature04_Column_Status' THEN 'asset_type x ticker x timeframe x feature_column'
      WHEN 'Monitoring_Feature04_Ticker' THEN 'execution x asset_type x ticker x timeframe'
      ELSE grain END,
    primary_key_columns=CASE table_name
      WHEN 'Feature04_Calculation_Queue' THEN ARRAY['asset_type','ticker','timeframe']
      WHEN 'Feature04_Column_Status' THEN ARRAY['asset_type','ticker','timeframe','feature_column']
      WHEN 'Monitoring_Feature04_Ticker' THEN ARRAY['execution_id','asset_type','ticker','timeframe']
      ELSE primary_key_columns END,
    source_tables=ARRAY(SELECT DISTINCT x FROM unnest(source_tables||ARRAY['Price_Fixed_Income','Universe_Fixed_income']) x ORDER BY x),
    source_code_paths=ARRAY(SELECT DISTINCT x FROM unnest(source_code_paths||ARRAY['database/migrations/20261011_006_extend_feature04_to_bonds.sql']) x ORDER BY x),
    updated_at=CURRENT_TIMESTAMP
WHERE table_schema='public' AND table_name IN (
 'Feature04_Calculation_Queue','Feature04_Column_Status','Feature04_Calculation_Log',
 'Monitoring_Feature04','Monitoring_Feature04_Ticker','Feature04_Retry_Request','Feature04_Notification_Outbox'
);

INSERT INTO public."Table_Catalog"(
 table_schema,table_name,category,definition,grain,primary_key_columns,source_system,
 source_tables,source_code_paths,update_rule,related_functions,documentation_status,
 readiness_mode,readiness_date_column,observation_date_column,data_available_at_column,
 availability_rule,point_in_time_status,historical_metadata_method
)
VALUES
('public','Universe_Fixed_income','Reference','Fixed-income instrument universe including price and yield series.','ticker x metric_type',ARRAY[]::text[],'TradingView',ARRAY[]::text[],ARRAY[]::text[],'Maintained by the fixed-income loader.',ARRAY[]::text[],'NEEDS_REVIEW','NOT_APPLICABLE',NULL,NULL,'updated_at','Current universe membership; historical membership is not preserved.','PARTIAL','Current-state universe only.'),
('public','Price_Fixed_Income','Source','Daily fixed-income OHLC observations for price and yield metrics.','tradingview_symbol x date x metric_type x Timeframe',ARRAY['tradingview_symbol','date','metric_type','Timeframe'],'TradingView',ARRAY['Universe_Fixed_income'],ARRAY[]::text[],'Updated by fixed-income daily and recovery cron services.',ARRAY['enqueue_feature04_bond_price_row()'],'NEEDS_REVIEW','DATA_DATE','date','date','ingestion_time','Observed date is date; ingestion_time records current load availability.','PARTIAL','Source revision history is not immutable.'),
('public','Monitoring_Fixed_Income','Monitoring','One fixed-income cron execution summary.','one execution',ARRAY['execution_id'],'fixed-income cron',ARRAY['Price_Fixed_Income'],ARRAY[]::text[],'One row per daily/recovery execution.',ARRAY['open_feature04_fixed_income_run()'],'NEEDS_REVIEW','NOT_APPLICABLE',NULL,'target_date','finished_at','Operational run record available after finish.','NOT_APPLICABLE',NULL)
ON CONFLICT(table_schema,table_name) DO UPDATE SET
 definition=EXCLUDED.definition,grain=EXCLUDED.grain,primary_key_columns=EXCLUDED.primary_key_columns,
 source_tables=EXCLUDED.source_tables,update_rule=EXCLUDED.update_rule,
 related_functions=EXCLUDED.related_functions,updated_at=CURRENT_TIMESTAMP;

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
       CASE WHEN c.column_name='asset_type' THEN
         'Universe-derived asset class: equity from IDX_Stock_Universe; bonds from Universe_Fixed_income.'
       WHEN c.column_name='source_monitor_table' THEN
         'Monitoring table whose Telegram delivery must precede this Feature04 result.'
       ELSE 'Physical source or operational column; source-specific semantic review remains open.' END,
       CASE WHEN c.column_name='asset_type' THEN 'feature04_asset_type(ticker)'
            ELSE c.column_name END,NULL,
       CASE WHEN c.is_nullable='YES' THEN 'May be NULL under the documented source/lifecycle contract.' ELSE 'Required.' END,
       ARRAY['database/migrations/20261011_006_extend_feature04_to_bonds.sql'],
       CASE WHEN c.column_name IN ('asset_type','source_monitor_table') THEN 'VERIFIED' ELSE 'NEEDS_REVIEW' END
FROM information_schema.columns c
WHERE c.table_schema='public' AND (
 (c.table_name IN ('Feature04_Technical_Indicator','Feature04_Calculation_Queue',
  'Feature04_Column_Status','Feature04_Calculation_Log','Monitoring_Feature04',
  'Monitoring_Feature04_Ticker','Feature04_Retry_Request')
  AND c.column_name IN ('asset_type','source_monitor_table'))
 OR c.table_name IN ('Universe_Fixed_income','Price_Fixed_Income','Monitoring_Fixed_Income')
)
ON CONFLICT(table_schema,table_name,column_name) DO UPDATE SET
 ordinal_position=EXCLUDED.ordinal_position,data_type=EXCLUDED.data_type,is_nullable=EXCLUDED.is_nullable,
 default_expression=EXCLUDED.default_expression,is_primary_key=EXCLUDED.is_primary_key,
 definition=EXCLUDED.definition,source_column_or_expression=EXCLUDED.source_column_or_expression,
 null_rule=EXCLUDED.null_rule,source_code_paths=EXCLUDED.source_code_paths,
 documentation_status=EXCLUDED.documentation_status,updated_at=CURRENT_TIMESTAMP;

UPDATE public."Feature_Catalog" SET
    grain='asset_type x ticker x trade_date x Daily timeframe',
    source_tables='Price_Stock_Indonesia_IDX + IDX_Stock_Universe; Price_Fixed_Income(metric_type=price) + Universe_Fixed_income',
    source_columns='Universe-classified ticker, date, normalized Daily timeframe, open, high, low, close; equity volume required, bonds volume may be NULL',
    refresh_trigger='Committed classified equity or bonds price change through the Feature04 queue',
    dependency_rule='Full available chronological history per asset_type/ticker through output end; no future bars; partitions remain isolated',
    version='v4',updated_at=CURRENT_TIMESTAMP
WHERE feature_table='Feature04_Technical_Indicator' AND is_active;

INSERT INTO public."Feature_Catalog"(
 feature_table,feature_column,grain,feature_category,definition,calculation,source_tables,
 source_columns,lookback_window,minimum_history,unit,null_rule,refresh_trigger,dependency_rule,
 version,is_active,semantic_role,allowed_aggregations,ranking_interpretation,is_filterable,
 is_groupable,availability_rule,point_in_time_safe,historical_metadata_warning,
 analytical_interpretation,recommended_use,misuse_warning,semantic_review_status,validation_evidence
)
VALUES(
 'Feature04_Technical_Indicator','asset_type','asset_type x ticker x trade_date x Daily timeframe',
 'Identity','Universe-derived asset class.','feature04_asset_type(ticker)',
 'IDX_Stock_Universe; Universe_Fixed_income','IDX_Stock_Universe.Ticker; Universe_Fixed_income.ticker',
 'Current universe lookup','Exactly one universe membership','category','Never NULL; ambiguous or absent membership aborts processing.',
 'Re-evaluated by every enqueue/load path','Ticker must occur in exactly one approved universe','v4',true,
 'DIMENSION',ARRAY['COUNT','COUNT_DISTINCT']::text[],'NOT_APPLICABLE',true,true,
 'Available when current universe membership is available.',false,
 'Universe membership is current state and does not prove historical membership.',
 'Separates otherwise identical ticker/date technical histories by asset class.',
 'Filter or group Feature04 results by equity versus bonds.',
 'Do not infer historical membership from the current universe lookup.',
 'CALCULATION_VERIFIED',ARRAY['features/feature04/tests/test_engine.py','verification/feature04/cross_asset_validation.json']::text[]
)
ON CONFLICT(feature_table,feature_column,version) DO UPDATE SET
 definition=EXCLUDED.definition,calculation=EXCLUDED.calculation,source_tables=EXCLUDED.source_tables,
 source_columns=EXCLUDED.source_columns,version=EXCLUDED.version,is_active=true,
 analytical_interpretation=EXCLUDED.analytical_interpretation,recommended_use=EXCLUDED.recommended_use,
 misuse_warning=EXCLUDED.misuse_warning,semantic_review_status=EXCLUDED.semantic_review_status,
 validation_evidence=EXCLUDED.validation_evidence,updated_at=CURRENT_TIMESTAMP;

DO $verify$
BEGIN
    IF EXISTS(SELECT 1 FROM public."Feature04_Technical_Indicator" WHERE asset_type<>'equity') THEN
        RAISE EXCEPTION 'Existing Feature04 rows were not classified as equity';
    END IF;
    IF EXISTS(
      SELECT 1 FROM public."Feature04_Technical_Indicator" f
      WHERE f.asset_type<>public.feature04_asset_type(f.ticker)
    ) THEN RAISE EXCEPTION 'Feature04 asset classification mismatch'; END IF;
    IF NOT EXISTS(
      SELECT 1 FROM pg_trigger WHERE tgrelid='public."Price_Fixed_Income"'::regclass
        AND tgname='Price_Fixed_Income_enqueue_feature04' AND tgenabled='O'
    ) THEN RAISE EXCEPTION 'Bond price enqueue trigger is not active'; END IF;
END
$verify$;

COMMIT;
