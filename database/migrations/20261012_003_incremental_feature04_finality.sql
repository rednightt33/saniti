BEGIN;

SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '30min';

SELECT pg_advisory_xact_lock(hashtextextended('feature04-incremental-finality-v1',0));

DO $guard$
BEGIN
    IF to_regclass('public."Feature04_Calculation_State"') IS NOT NULL THEN
        RAISE EXCEPTION 'Feature04 incremental state already exists';
    END IF;
    IF EXISTS(SELECT 1 FROM public."Feature04_Calculation_Queue" WHERE status='PROCESSING') THEN
        RAISE EXCEPTION 'Feature04 worker has an active claim';
    END IF;
    IF to_regclass('public."Price_Stock_Indonesia_IDX"') IS NULL
       OR to_regclass('public."Fixed_Income_Market_Schedule"') IS NULL THEN
        RAISE EXCEPTION 'Required price/schedule tables are absent';
    END IF;
END
$guard$;

ALTER TABLE public."Fixed_Income_Market_Schedule"
    ADD COLUMN correction_lookback_sessions integer NOT NULL DEFAULT 5,
    ADD CONSTRAINT "Fixed_Income_Market_Schedule_correction_window_check"
        CHECK(correction_lookback_sessions BETWEEN 1 AND 20);

CREATE TABLE public."Equity_Market_Schedule" (
    market_code text PRIMARY KEY,
    exchange text NOT NULL UNIQUE,
    timezone_name text NOT NULL,
    session_close_local time without time zone NOT NULL,
    finality_delay_minutes integer NOT NULL,
    correction_lookback_sessions integer NOT NULL DEFAULT 5,
    enabled boolean NOT NULL DEFAULT true,
    updated_at timestamptz NOT NULL DEFAULT statement_timestamp(),
    CONSTRAINT "Equity_Market_Schedule_code_check"
        CHECK(market_code=upper(btrim(market_code)) AND market_code<>''),
    CONSTRAINT "Equity_Market_Schedule_exchange_check"
        CHECK(exchange=upper(btrim(exchange)) AND exchange<>''),
    CONSTRAINT "Equity_Market_Schedule_timezone_check"
        CHECK(timezone_name=btrim(timezone_name) AND timezone_name<>''),
    CONSTRAINT "Equity_Market_Schedule_delay_check"
        CHECK(finality_delay_minutes BETWEEN 0 AND 360),
    CONSTRAINT "Equity_Market_Schedule_correction_window_check"
        CHECK(correction_lookback_sessions BETWEEN 1 AND 20)
);

INSERT INTO public."Equity_Market_Schedule"(
    market_code,exchange,timezone_name,session_close_local,
    finality_delay_minutes,correction_lookback_sessions
) VALUES('IDX','IDX','Asia/Jakarta','16:00',60,5);

ALTER TABLE public."Price_Stock_Indonesia_IDX"
    ADD COLUMN market_code text,
    ADD COLUMN source_bar_time timestamptz,
    ADD COLUMN market_close_at timestamptz,
    ADD COLUMN is_final boolean NOT NULL DEFAULT false,
    ADD COLUMN finalized_at timestamptz;

UPDATE public."Price_Stock_Indonesia_IDX" p
SET market_code='IDX',
    market_close_at=(p.date+s.session_close_local) AT TIME ZONE s.timezone_name,
    is_final=true,
    finalized_at=greatest(
        p.ingestion_time,
        (p.date+s.session_close_local) AT TIME ZONE s.timezone_name
    )
FROM public."Equity_Market_Schedule" s
WHERE s.market_code='IDX';

ALTER TABLE public."Price_Stock_Indonesia_IDX"
    ALTER COLUMN market_code SET NOT NULL,
    ALTER COLUMN market_close_at SET NOT NULL,
    ALTER COLUMN finalized_at SET NOT NULL,
    ADD CONSTRAINT "Price_Stock_Indonesia_IDX_market_fkey"
        FOREIGN KEY(market_code) REFERENCES public."Equity_Market_Schedule"(market_code),
    ADD CONSTRAINT "Price_Stock_Indonesia_IDX_finality_check"
        CHECK(NOT is_final OR finalized_at>=market_close_at);

CREATE INDEX "Price_Stock_Indonesia_IDX_final_idx"
    ON public."Price_Stock_Indonesia_IDX"(ticker,date DESC)
    WHERE is_final AND timeframe='Daily';

CREATE TABLE public."Feature04_Calculation_State" (
    asset_type text NOT NULL,
    ticker text NOT NULL,
    timeframe text NOT NULL DEFAULT 'Daily',
    checkpoint_date date NOT NULL,
    state_version text NOT NULL,
    calculation_version text NOT NULL,
    source_position integer NOT NULL,
    source_chain_sha256 text NOT NULL,
    state_payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(asset_type,ticker,timeframe,checkpoint_date),
    CHECK(asset_type IN ('equity','bonds')),
    CHECK(ticker=upper(btrim(ticker)) AND ticker<>''),
    CHECK(timeframe='Daily'),
    CHECK(btrim(state_version)<>'' AND btrim(calculation_version)<>''),
    CHECK(source_position>0),
    CHECK(source_chain_sha256~'^[0-9a-f]{64}$'),
    CHECK(state_payload->>'last_date'=checkpoint_date::text),
    CHECK(state_payload->>'source_chain_sha256'=source_chain_sha256)
);

CREATE INDEX "Feature04_Calculation_State_latest_idx"
    ON public."Feature04_Calculation_State"(asset_type,ticker,timeframe,checkpoint_date DESC);

ALTER TABLE public."Feature04_Calculation_Log"
    ADD COLUMN checkpoint_date date,
    ADD COLUMN dirty_from_date date,
    ADD CONSTRAINT "Feature04_Calculation_Log_incremental_range_check"
        CHECK(checkpoint_date IS NULL OR dirty_from_date IS NULL OR checkpoint_date<dirty_from_date);

CREATE OR REPLACE FUNCTION public.feature04_source_min_date(p_asset_type text,p_ticker text)
RETURNS date
LANGUAGE plpgsql
STABLE
AS $function$
DECLARE v_date date;
BEGIN
    IF p_asset_type='equity' THEN
        SELECT min(date) INTO v_date FROM public."Price_Stock_Indonesia_IDX"
        WHERE ticker=p_ticker AND timeframe='Daily' AND is_final;
    ELSIF p_asset_type='bonds' THEN
        SELECT min(date) INTO v_date FROM public."Price_Fixed_Income"
        WHERE ticker=p_ticker AND metric_type='price' AND "Timeframe"='1D' AND is_final;
    ELSE
        RAISE EXCEPTION 'Unsupported Feature04 asset_type %',p_asset_type;
    END IF;
    IF v_date IS NULL THEN
        RAISE EXCEPTION 'No final Feature04 source history for %/%',p_asset_type,p_ticker;
    END IF;
    RETURN v_date;
END
$function$;

CREATE OR REPLACE FUNCTION public.enqueue_feature04_group(
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
    DELETE FROM public."Feature04_Calculation_State"
    WHERE asset_type=p_asset_type AND ticker=p_ticker AND timeframe=p_timeframe
      AND checkpoint_date>=p_dirty_date;
    INSERT INTO public."Feature04_Calculation_Queue"(
        asset_type,ticker,timeframe,dirty_from_date,requested_generation,completed_generation,
        work_revision,requested_columns,origin_execution_id,status,next_attempt_at
    ) VALUES(p_asset_type,p_ticker,p_timeframe,p_dirty_date,1,0,1,NULL,p_execution_id,'PENDING',CURRENT_TIMESTAMP)
    ON CONFLICT(asset_type,ticker,timeframe) DO UPDATE SET
        dirty_from_date=CASE
          WHEN public."Feature04_Calculation_Queue".status='DONE'
           AND public."Feature04_Calculation_Queue".completed_generation=
               public."Feature04_Calculation_Queue".requested_generation
          THEN EXCLUDED.dirty_from_date
          ELSE least(public."Feature04_Calculation_Queue".dirty_from_date,EXCLUDED.dirty_from_date)
        END,
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
    v_dirty_date date;
    v_scope text := CASE WHEN p_columns IS NULL THEN 'TICKER' ELSE 'COLUMN' END;
BEGIN
    IF p_ticker IS NULL OR p_ticker<>upper(btrim(p_ticker)) OR p_ticker='' THEN
        RAISE EXCEPTION 'A canonical ticker is required';
    END IF;
    v_asset_type := public.feature04_asset_type(p_ticker);
    IF p_columns IS NOT NULL THEN
        SELECT array_agg(value) INTO v_invalid FROM unnest(p_columns) value
        WHERE NOT value=ANY(public.feature04_output_columns());
        IF v_invalid IS NOT NULL THEN
            RAISE EXCEPTION 'Unsupported Feature04 columns: %',v_invalid;
        END IF;
        SELECT min(dirty_from_date) INTO v_dirty_date
        FROM public."Feature04_Column_Status"
        WHERE asset_type=v_asset_type AND ticker=p_ticker AND timeframe='Daily'
          AND feature_column=ANY(p_columns) AND status IN ('FAILED','BLOCKED');
        IF v_dirty_date IS NULL THEN
            RAISE EXCEPTION 'Selected columns have no active failure for %/%',v_asset_type,p_ticker;
        END IF;
    ELSE
        SELECT dirty_from_date INTO v_dirty_date
        FROM public."Feature04_Calculation_Queue"
        WHERE asset_type=v_asset_type AND ticker=p_ticker AND timeframe='Daily'
          AND status='FAILED';
        IF v_dirty_date IS NULL THEN
            SELECT min(dirty_from_date) INTO v_dirty_date
            FROM public."Feature04_Column_Status"
            WHERE asset_type=v_asset_type AND ticker=p_ticker AND timeframe='Daily'
              AND status IN ('FAILED','BLOCKED');
        END IF;
        IF v_dirty_date IS NULL THEN
            RAISE EXCEPTION 'Ticker %/% has no active Feature04 failure',v_asset_type,p_ticker;
        END IF;
    END IF;
    DELETE FROM public."Feature04_Calculation_State"
    WHERE asset_type=v_asset_type AND ticker=p_ticker AND timeframe='Daily'
      AND checkpoint_date>=v_dirty_date;
    INSERT INTO public."Feature04_Calculation_Queue"(
        asset_type,ticker,timeframe,dirty_from_date,requested_generation,completed_generation,
        work_revision,requested_columns,status,next_attempt_at
    ) VALUES(v_asset_type,p_ticker,'Daily',v_dirty_date,1,0,1,p_columns,'PENDING',CURRENT_TIMESTAMP)
    ON CONFLICT(asset_type,ticker,timeframe) DO UPDATE SET
        dirty_from_date=least(public."Feature04_Calculation_Queue".dirty_from_date,EXCLUDED.dirty_from_date),
        work_revision=public."Feature04_Calculation_Queue".work_revision+1,
        requested_columns=CASE
          WHEN public."Feature04_Calculation_Queue".requested_columns IS NULL
            OR EXCLUDED.requested_columns IS NULL THEN NULL
          ELSE ARRAY(
            SELECT DISTINCT value
            FROM unnest(public."Feature04_Calculation_Queue".requested_columns||EXCLUDED.requested_columns) value
            ORDER BY value
          )
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

CREATE OR REPLACE FUNCTION public.enqueue_feature04_equity_price_row()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE v_execution_id text := nullif(current_setting('saniti.feature04_execution_id',true),'');
BEGIN
    IF TG_OP IN ('UPDATE','DELETE') AND OLD.timeframe='Daily' AND OLD.is_final THEN
        IF TG_OP='DELETE'
           OR ROW(OLD.ticker,OLD.date,OLD.open,OLD.high,OLD.low,OLD.close,OLD.volume,
                  OLD.source,OLD.tradingview_symbol,OLD.is_final)
              IS DISTINCT FROM
              ROW(NEW.ticker,NEW.date,NEW.open,NEW.high,NEW.low,NEW.close,NEW.volume,
                  NEW.source,NEW.tradingview_symbol,NEW.is_final)
           OR NEW.timeframe<>'Daily' OR NOT NEW.is_final THEN
            PERFORM public.enqueue_feature04_group(
                public.feature04_asset_type(OLD.ticker),OLD.ticker,OLD.date,'Daily',v_execution_id
            );
        END IF;
    END IF;
    IF TG_OP IN ('INSERT','UPDATE') AND NEW.timeframe='Daily' AND NEW.is_final THEN
        IF TG_OP='INSERT'
           OR ROW(NEW.ticker,NEW.date,NEW.open,NEW.high,NEW.low,NEW.close,NEW.volume,
                  NEW.source,NEW.tradingview_symbol,NEW.is_final)
              IS DISTINCT FROM
              ROW(OLD.ticker,OLD.date,OLD.open,OLD.high,OLD.low,OLD.close,OLD.volume,
                  OLD.source,OLD.tradingview_symbol,OLD.is_final)
           OR OLD.timeframe<>'Daily' OR NOT OLD.is_final THEN
            PERFORM public.enqueue_feature04_group(
                public.feature04_asset_type(NEW.ticker),NEW.ticker,NEW.date,'Daily',v_execution_id
            );
        END IF;
    END IF;
    RETURN NULL;
END
$function$;

COMMENT ON TABLE public."Equity_Market_Schedule" IS
'Data-driven equity market close, finality delay and correction-session policy.';
COMMENT ON COLUMN public."Fixed_Income_Market_Schedule".correction_lookback_sessions IS
'Number of completed provider sessions re-verified by scheduled recovery.';
COMMENT ON COLUMN public."Price_Stock_Indonesia_IDX".source_bar_time IS
'Original TradingView bar timestamp; NULL for legacy rows loaded before finality evidence.';
COMMENT ON COLUMN public."Price_Stock_Indonesia_IDX".market_close_at IS
'Configured UTC market-close instant for this observation date.';
COMMENT ON COLUMN public."Price_Stock_Indonesia_IDX".is_final IS
'True only for an exact completed Daily candle accepted after configured close and delay.';
COMMENT ON COLUMN public."Price_Stock_Indonesia_IDX".finalized_at IS
'Time the completed candle was verified and stored.';
COMMENT ON TABLE public."Feature04_Calculation_State" IS
'Recent versioned per-ticker checkpoints used to calculate only the affected Feature04 suffix.';
COMMENT ON FUNCTION public.enqueue_feature04_group(text,text,date,text,text) IS
'Invalidate checkpoints on/after the earliest changed final source date and coalesce one Feature04 generation per ticker.';

INSERT INTO public."Table_Catalog"(
 table_schema,table_name,category,definition,grain,primary_key_columns,source_system,
 source_tables,source_code_paths,update_rule,related_functions,documentation_status,
 readiness_mode,readiness_date_column,observation_date_column,data_available_at_column,
 availability_rule,point_in_time_status,historical_metadata_method
) VALUES
('public','Equity_Market_Schedule','Reference',
 'Equity market timezone, close, finality delay and correction-session policy.',
 'one market',ARRAY['market_code'],'Operator-approved configuration',ARRAY[]::text[],
 ARRAY['database/migrations/20261012_003_incremental_feature04_finality.sql','apps/idx-price-cron/price_update.py'],
 'Edit when the official market clock or correction policy changes.',ARRAY[]::text[],'VERIFIED',
 'NOT_APPLICABLE',NULL,NULL,'updated_at','Current enabled configuration controls finality.','PARTIAL',
 'Current configuration is retained; historical versions are not yet stored.'),
('public','Feature04_Calculation_State','System',
 'Recent versioned Feature04 recursive and rolling state checkpoints.',
 'asset_type x ticker x Daily x checkpoint date',
 ARRAY['asset_type','ticker','timeframe','checkpoint_date'],'Feature04 worker',
 ARRAY['Price_Stock_Indonesia_IDX','Price_Fixed_Income'],
 ARRAY['database/migrations/20261012_003_incremental_feature04_finality.sql','features/feature04/incremental.py','apps/feature-04-worker/worker.py'],
 'Written transactionally after a validated suffix; invalidated on/after a changed source date.',
 ARRAY['enqueue_feature04_group(text,text,date,text,text)'],'VERIFIED',
 'DATA_DATE','checkpoint_date','checkpoint_date','updated_at',
 'A checkpoint is usable only with matching state/calculation versions and source chain digest.',
 'PARTIAL','Recent operational checkpoints only; older explicit repairs rebuild state.')
ON CONFLICT(table_schema,table_name) DO UPDATE SET
 definition=EXCLUDED.definition,grain=EXCLUDED.grain,primary_key_columns=EXCLUDED.primary_key_columns,
 source_system=EXCLUDED.source_system,source_tables=EXCLUDED.source_tables,
 source_code_paths=EXCLUDED.source_code_paths,update_rule=EXCLUDED.update_rule,
 related_functions=EXCLUDED.related_functions,documentation_status=EXCLUDED.documentation_status,
 readiness_mode=EXCLUDED.readiness_mode,readiness_date_column=EXCLUDED.readiness_date_column,
 observation_date_column=EXCLUDED.observation_date_column,data_available_at_column=EXCLUDED.data_available_at_column,
 availability_rule=EXCLUDED.availability_rule,point_in_time_status=EXCLUDED.point_in_time_status,
 historical_metadata_method=EXCLUDED.historical_metadata_method,updated_at=CURRENT_TIMESTAMP;

UPDATE public."Table_Catalog" SET
 definition=CASE table_name
   WHEN 'Price_Stock_Indonesia_IDX' THEN 'Final daily Indonesian equity OHLCV observations with market-close finality evidence.'
   WHEN 'Feature_04_Technical_Indicator' THEN 'Cross-asset Daily close and technical indicators calculated from final source prices with exact checkpointed suffix refresh.'
   ELSE definition END,
 source_code_paths=ARRAY(
   SELECT DISTINCT x FROM unnest(source_code_paths||ARRAY[
     'database/migrations/20261012_003_incremental_feature04_finality.sql',
     'features/feature04/incremental.py'
   ]) x ORDER BY x
 ),
 update_rule=CASE table_name
   WHEN 'Price_Stock_Indonesia_IDX' THEN 'Market-aware daily/recovery jobs material-upsert exact final candles; recovery re-verifies configured recent sessions.'
   WHEN 'Feature_04_Technical_Indicator' THEN 'Committed final source changes recalculate only the affected suffix from a compatible prior checkpoint.'
   WHEN 'Feature04_Calculation_Queue' THEN 'Final source changes coalesce the earliest dirty date per ticker and invalidate dependent checkpoints.'
   ELSE update_rule END,
 related_functions=CASE WHEN table_name='Price_Stock_Indonesia_IDX'
   THEN ARRAY['enqueue_feature04_equity_price_row()'] ELSE related_functions END,
 updated_at=CURRENT_TIMESTAMP
WHERE table_schema='public' AND table_name IN (
 'Price_Stock_Indonesia_IDX','Feature_04_Technical_Indicator','Feature04_Calculation_Queue'
);

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
         WHEN 'Price_Stock_Indonesia_IDX.market_code' THEN 'Configured equity market partition.'
         WHEN 'Price_Stock_Indonesia_IDX.source_bar_time' THEN 'Original TradingView daily bar timestamp.'
         WHEN 'Price_Stock_Indonesia_IDX.market_close_at' THEN 'Configured close instant for the observation date.'
         WHEN 'Price_Stock_Indonesia_IDX.is_final' THEN 'Whether the exact Daily candle was accepted after finality delay.'
         WHEN 'Price_Stock_Indonesia_IDX.finalized_at' THEN 'Time this completed candle was verified.'
         WHEN 'Feature04_Calculation_Log.checkpoint_date' THEN 'Trusted state date immediately before the calculated suffix.'
         WHEN 'Feature04_Calculation_Log.dirty_from_date' THEN 'Earliest changed source session for this attempt.'
         ELSE 'Operational checkpoint or market-policy field.' END,
       c.column_name,
       CASE WHEN c.column_name LIKE '%minutes' THEN 'minutes'
            WHEN c.column_name LIKE '%_at' THEN 'timestamp'
            WHEN c.column_name LIKE '%date' THEN 'date' ELSE NULL END,
       CASE WHEN c.table_name='Price_Stock_Indonesia_IDX' AND c.column_name='source_bar_time'
              THEN 'NULL only for legacy rows without retained provider timestamp.'
            WHEN c.is_nullable='YES' THEN 'NULL only when the documented lifecycle does not require it.'
            ELSE 'Required.' END,
       ARRAY['database/migrations/20261012_003_incremental_feature04_finality.sql',
             'features/feature04/incremental.py','apps/feature-04-worker/worker.py'],
       'VERIFIED'
FROM information_schema.columns c
WHERE c.table_schema='public' AND (
 c.table_name IN ('Equity_Market_Schedule','Feature04_Calculation_State')
 OR (c.table_name='Fixed_Income_Market_Schedule' AND c.column_name='correction_lookback_sessions')
 OR (c.table_name='Price_Stock_Indonesia_IDX' AND c.column_name IN (
   'market_code','source_bar_time','market_close_at','is_final','finalized_at'))
 OR (c.table_name='Feature04_Calculation_Log' AND c.column_name IN ('checkpoint_date','dirty_from_date'))
)
ON CONFLICT(table_schema,table_name,column_name) DO UPDATE SET
 ordinal_position=EXCLUDED.ordinal_position,data_type=EXCLUDED.data_type,is_nullable=EXCLUDED.is_nullable,
 default_expression=EXCLUDED.default_expression,is_primary_key=EXCLUDED.is_primary_key,
 definition=EXCLUDED.definition,source_column_or_expression=EXCLUDED.source_column_or_expression,
 unit=EXCLUDED.unit,null_rule=EXCLUDED.null_rule,source_code_paths=EXCLUDED.source_code_paths,
 documentation_status=EXCLUDED.documentation_status,updated_at=CURRENT_TIMESTAMP;

UPDATE public."Feature_Catalog" SET
 refresh_trigger='Committed final source price change through the Feature04 queue',
 dependency_rule='Compatible checkpoint immediately before earliest changed recent session, then chronological suffix through output end; no future bars; partitions remain isolated',
 validation_evidence=ARRAY(
   SELECT DISTINCT x FROM unnest(validation_evidence||ARRAY[
     'features/feature04/tests/test_incremental.py',
     'verification/feature04/INCREMENTAL_FINALITY.md'
   ]) x ORDER BY x
 ),
 updated_at=CURRENT_TIMESTAMP
WHERE feature_table='Feature_04_Technical_Indicator' AND is_active;

DO $verify$
BEGIN
    IF (SELECT correction_lookback_sessions FROM public."Equity_Market_Schedule" WHERE market_code='IDX')<>5 THEN
        RAISE EXCEPTION 'IDX correction window is not five sessions';
    END IF;
    IF EXISTS(SELECT 1 FROM public."Price_Stock_Indonesia_IDX" WHERE NOT is_final OR market_close_at IS NULL OR finalized_at IS NULL) THEN
        RAISE EXCEPTION 'Legacy equity prices were not initialized as completed sessions';
    END IF;
    IF NOT EXISTS(
      SELECT 1 FROM pg_indexes WHERE schemaname='public'
        AND indexname='Feature04_Calculation_State_latest_idx'
    ) THEN RAISE EXCEPTION 'Feature04 checkpoint index is absent'; END IF;
END
$verify$;

COMMIT;
