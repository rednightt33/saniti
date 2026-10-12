BEGIN;

SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '10min';

SELECT pg_advisory_xact_lock(hashtextextended('feature04-telegram-monitor-v1',0));

ALTER TABLE public."Feature04_Retry_Request"
    ADD COLUMN acknowledgement_message_id bigint,
    ADD CONSTRAINT "Feature04_Retry_Request_ack_message_check"
        CHECK(acknowledgement_message_id IS NULL OR acknowledgement_message_id >= 0);

COMMENT ON COLUMN public."Feature04_Retry_Request".acknowledgement_message_id IS
'Telegram acknowledgement message to edit with the terminal retry result; zero records that acknowledgement delivery failed.';

CREATE OR REPLACE FUNCTION public.feature04_retry_dirty_date(
    p_asset_type text,p_ticker text
)
RETURNS date
LANGUAGE plpgsql
STABLE
SET search_path=public,pg_temp
AS $function$
DECLARE
    v_sessions integer;
    v_dirty_date date;
BEGIN
    IF p_asset_type='equity' THEN
        SELECT correction_lookback_sessions INTO v_sessions
        FROM public."Equity_Market_Schedule"
        WHERE market_code='IDX' AND enabled;
        SELECT min(source_date) INTO v_dirty_date FROM (
            SELECT date AS source_date
            FROM public."Price_Stock_Indonesia_IDX"
            WHERE ticker=p_ticker AND timeframe='Daily' AND is_final
            ORDER BY date DESC LIMIT v_sessions
        ) recent;
    ELSIF p_asset_type='bonds' THEN
        SELECT DISTINCT s.correction_lookback_sessions INTO v_sessions
        FROM public."Universe_Fixed_income" u
        JOIN public."Fixed_Income_Market_Schedule" s ON s.country=u.country
        WHERE u.ticker=p_ticker AND u.metric_type='price' AND s.enabled;
        SELECT min(source_date) INTO v_dirty_date FROM (
            SELECT date AS source_date
            FROM public."Price_Fixed_Income"
            WHERE ticker=p_ticker AND metric_type='price' AND "Timeframe"='1D' AND is_final
            ORDER BY date DESC LIMIT v_sessions
        ) recent;
    ELSE
        RAISE EXCEPTION 'Unsupported Feature04 asset_type %',p_asset_type;
    END IF;
    IF v_sessions IS NULL OR v_dirty_date IS NULL THEN
        RAISE EXCEPTION 'No enabled correction policy or final history for %/%',p_asset_type,p_ticker;
    END IF;
    RETURN v_dirty_date;
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

    PERFORM 1 FROM public."Feature04_Calculation_Queue"
    WHERE asset_type=v_asset_type AND ticker=p_ticker AND timeframe='Daily'
    FOR UPDATE;

    IF p_columns IS NOT NULL THEN
        SELECT array_agg(value) INTO v_invalid FROM unnest(p_columns) value
        WHERE NOT value=ANY(public.feature04_output_columns());
        IF v_invalid IS NOT NULL THEN
            RAISE EXCEPTION 'Unsupported Feature04 columns: %',v_invalid;
        END IF;
        IF NOT EXISTS(
            SELECT 1 FROM public."Feature04_Column_Status"
            WHERE asset_type=v_asset_type AND ticker=p_ticker AND timeframe='Daily'
              AND feature_column=ANY(p_columns) AND status IN ('FAILED','BLOCKED')
        ) THEN
            RAISE EXCEPTION 'Selected columns have no active failure for %/%',v_asset_type,p_ticker;
        END IF;
    ELSIF NOT EXISTS(
        SELECT 1 FROM public."Feature04_Calculation_Queue"
        WHERE asset_type=v_asset_type AND ticker=p_ticker AND timeframe='Daily' AND status='FAILED'
        UNION ALL
        SELECT 1 FROM public."Feature04_Column_Status"
        WHERE asset_type=v_asset_type AND ticker=p_ticker AND timeframe='Daily'
          AND status IN ('FAILED','BLOCKED')
    ) THEN
        RAISE EXCEPTION 'Ticker %/% has no active Feature04 failure',v_asset_type,p_ticker;
    END IF;

    v_dirty_date := public.feature04_retry_dirty_date(v_asset_type,p_ticker);
    DELETE FROM public."Feature04_Calculation_State"
    WHERE asset_type=v_asset_type AND ticker=p_ticker AND timeframe='Daily'
      AND checkpoint_date>=v_dirty_date;

    INSERT INTO public."Feature04_Calculation_Queue"(
        asset_type,ticker,timeframe,dirty_from_date,requested_generation,completed_generation,
        work_revision,requested_columns,status,next_attempt_at
    ) VALUES(v_asset_type,p_ticker,'Daily',v_dirty_date,1,0,1,p_columns,'PENDING',CURRENT_TIMESTAMP)
    ON CONFLICT(asset_type,ticker,timeframe) DO UPDATE SET
        dirty_from_date=EXCLUDED.dirty_from_date,
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

REVOKE ALL ON FUNCTION public.feature04_retry_dirty_date(text,text) FROM PUBLIC;

UPDATE public."Table_Catalog"
SET definition='Audited owner Telegram failure-only retry request with editable acknowledgement and bounded five-session replay.',
    update_rule='telegram-trigger stores the acknowledgement message ID; the worker records terminal status and telegram-monitor edits the same message.',
    related_functions=ARRAY['request_feature04_retry(bigint,bigint,text,text[],text)','feature04_retry_dirty_date(text,text)'],
    source_code_paths=ARRAY['database/migrations/20261012_004_feature04_telegram_monitor.sql','apps/telegram-trigger/telegram_trigger.py','apps/telegram-monitor/telegram_monitor.py','apps/feature-04-worker/worker.py'],
    updated_at=clock_timestamp()
WHERE table_schema='public' AND table_name='Feature04_Retry_Request';

INSERT INTO public."Column_Catalog"(
    table_schema,table_name,column_name,ordinal_position,data_type,is_nullable,
    default_expression,is_primary_key,definition,source_column_or_expression,
    unit,null_rule,source_code_paths,documentation_status
)
SELECT c.table_schema,c.table_name,c.column_name,c.ordinal_position,c.data_type,
       c.is_nullable='YES',c.column_default,false,
       'Telegram message ID for the retry acknowledgement that is edited with the terminal result.',
       'Telegram Bot API sendMessage result.message_id',NULL,
       'NULL until acknowledgement delivery is recorded; zero means acknowledgement delivery failed.',
       ARRAY['database/migrations/20261012_004_feature04_telegram_monitor.sql','apps/telegram-trigger/telegram_trigger.py','apps/telegram-monitor/telegram_monitor.py'],
       'VERIFIED'
FROM information_schema.columns c
WHERE c.table_schema='public' AND c.table_name='Feature04_Retry_Request'
  AND c.column_name='acknowledgement_message_id'
ON CONFLICT(table_schema,table_name,column_name) DO UPDATE SET
    ordinal_position=EXCLUDED.ordinal_position,data_type=EXCLUDED.data_type,
    is_nullable=EXCLUDED.is_nullable,default_expression=EXCLUDED.default_expression,
    definition=EXCLUDED.definition,source_column_or_expression=EXCLUDED.source_column_or_expression,
    null_rule=EXCLUDED.null_rule,source_code_paths=EXCLUDED.source_code_paths,
    documentation_status=EXCLUDED.documentation_status,updated_at=clock_timestamp();

COMMIT;
