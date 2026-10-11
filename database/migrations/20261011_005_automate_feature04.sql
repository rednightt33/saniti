BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '10min';

DO $guard$
BEGIN
    IF to_regclass('public."Feature04_Calculation_Queue"') IS NOT NULL
       OR to_regclass('public."Feature04_Column_Status"') IS NOT NULL
       OR to_regclass('public."Monitoring_Feature04"') IS NOT NULL THEN
        RAISE EXCEPTION 'Feature04 automation control objects already exist';
    END IF;
    IF to_regclass('public."Price_Stock_Indonesia_IDX"') IS NULL
       OR to_regclass('public."Feature04_Technical_Indicator"') IS NULL
       OR to_regclass('public."Telegram_Command_Log"') IS NULL THEN
        RAISE EXCEPTION 'Required price, Feature04, or Telegram command table is absent';
    END IF;
END
$guard$;

CREATE TABLE public."Feature04_Calculation_Queue" (
    ticker text NOT NULL,
    timeframe text NOT NULL DEFAULT 'Daily',
    dirty_from_date date NOT NULL,
    requested_generation bigint NOT NULL DEFAULT 1,
    completed_generation bigint NOT NULL DEFAULT 0,
    work_revision bigint NOT NULL DEFAULT 1,
    requested_columns text[],
    origin_execution_id text,
    status text NOT NULL DEFAULT 'PENDING',
    attempt_count bigint NOT NULL DEFAULT 0,
    source_attempt_count integer NOT NULL DEFAULT 0,
    next_attempt_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    claimed_at timestamptz,
    claim_token uuid,
    claim_expires_at timestamptz,
    last_error_code text,
    last_error text,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at timestamptz,
    PRIMARY KEY (ticker, timeframe),
    CHECK (ticker = upper(btrim(ticker)) AND ticker <> ''),
    CHECK (timeframe = 'Daily'),
    CHECK (requested_generation >= completed_generation AND completed_generation >= 0),
    CHECK (work_revision > 0 AND attempt_count >= 0 AND source_attempt_count >= 0),
    CHECK (requested_columns IS NULL OR cardinality(requested_columns) > 0),
    CHECK (status IN ('PENDING','PROCESSING','DONE','FAILED')),
    CHECK ((status = 'PROCESSING') =
           (claimed_at IS NOT NULL AND claim_token IS NOT NULL AND claim_expires_at IS NOT NULL))
);

CREATE INDEX "Feature04_Calculation_Queue_ready_idx"
    ON public."Feature04_Calculation_Queue" (next_attempt_at, updated_at)
    WHERE status IN ('PENDING','FAILED');
CREATE INDEX "Feature04_Calculation_Queue_lease_idx"
    ON public."Feature04_Calculation_Queue" (claim_expires_at)
    WHERE status = 'PROCESSING';

CREATE TABLE public."Feature04_Column_Status" (
    ticker text NOT NULL,
    timeframe text NOT NULL DEFAULT 'Daily',
    feature_column text NOT NULL,
    requested_generation bigint NOT NULL DEFAULT 0,
    completed_generation bigint NOT NULL DEFAULT 0,
    calculation_version text NOT NULL,
    status text NOT NULL,
    dirty_from_date date,
    validated_through date,
    latest_value_available boolean,
    null_reason text,
    last_attempt_id bigint,
    last_error_code text,
    last_error text,
    last_calculated_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, timeframe, feature_column),
    CHECK (ticker = upper(btrim(ticker)) AND ticker <> ''),
    CHECK (timeframe = 'Daily'),
    CHECK (btrim(feature_column) <> '' AND btrim(calculation_version) <> ''),
    CHECK (requested_generation >= completed_generation AND completed_generation >= 0),
    CHECK (status IN ('PENDING','PROCESSING','SUCCESS','FAILED','BLOCKED'))
);

CREATE INDEX "Feature04_Column_Status_failure_idx"
    ON public."Feature04_Column_Status" (status, updated_at DESC, ticker, feature_column)
    WHERE status IN ('FAILED','BLOCKED');

CREATE TABLE public."Feature04_Calculation_Log" (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ticker text NOT NULL,
    timeframe text NOT NULL,
    source_generation bigint NOT NULL,
    work_revision bigint NOT NULL,
    retry_request_id uuid,
    requested_columns text[],
    successful_columns text[] NOT NULL DEFAULT '{}',
    failed_columns text[] NOT NULL DEFAULT '{}',
    group_outcomes jsonb NOT NULL DEFAULT '{}'::jsonb,
    result text NOT NULL,
    source_start date,
    source_end date,
    source_rows integer,
    source_sha256 text,
    changed_rows integer,
    calculation_version text NOT NULL,
    started_at timestamptz NOT NULL,
    finished_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    error_code text,
    detail text,
    CHECK (timeframe = 'Daily'),
    CHECK (source_generation >= 0 AND work_revision > 0),
    CHECK (result IN ('SUCCESS','PARTIAL','FAILED','SUPERSEDED')),
    CHECK (source_rows IS NULL OR source_rows >= 0),
    CHECK (changed_rows IS NULL OR changed_rows >= 0),
    CHECK (finished_at >= started_at)
);
CREATE INDEX "Feature04_Calculation_Log_ticker_time_idx"
    ON public."Feature04_Calculation_Log" (ticker, started_at DESC);
ALTER TABLE public."Feature04_Column_Status"
    ADD CONSTRAINT "Feature04_Column_Status_attempt_fkey"
    FOREIGN KEY (last_attempt_id) REFERENCES public."Feature04_Calculation_Log"(id);

CREATE TABLE public."Monitoring_Feature04" (
    execution_id text PRIMARY KEY,
    source_execution_id text,
    run_type text NOT NULL,
    trigger_source text NOT NULL,
    update_for_date date,
    price_notification_required boolean NOT NULL DEFAULT true,
    price_notification_sent_at timestamptz,
    eligible_tickers integer NOT NULL DEFAULT 0,
    completed_tickers integer NOT NULL DEFAULT 0,
    failed_tickers integer NOT NULL DEFAULT 0,
    blocked_tickers integer NOT NULL DEFAULT 0,
    status text NOT NULL DEFAULT 'OPEN',
    started_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sealed_at timestamptz,
    finished_at timestamptz,
    last_error text,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (btrim(execution_id) <> ''),
    CHECK (run_type IN ('DAILY','RECOVERY','RETRY_TICKER','RETRY_COLUMN','ADHOC','RECONCILIATION')),
    CHECK (trigger_source IN ('SCHEDULED','MANUAL','TELEGRAM','DATABASE','RECONCILIATION')),
    CHECK (status IN ('OPEN','READY','PROCESSING','SUCCESS','PARTIAL','NEEDS_REVIEW','FAILED','SKIPPED')),
    CHECK (eligible_tickers >= 0 AND completed_tickers >= 0 AND failed_tickers >= 0 AND blocked_tickers >= 0)
);
CREATE INDEX "Monitoring_Feature04_status_idx"
    ON public."Monitoring_Feature04" (status, updated_at);

CREATE TABLE public."Monitoring_Feature04_Ticker" (
    execution_id text NOT NULL REFERENCES public."Monitoring_Feature04"(execution_id) ON DELETE CASCADE,
    ticker text NOT NULL,
    timeframe text NOT NULL DEFAULT 'Daily',
    required_generation bigint NOT NULL,
    requested_columns text[],
    status text NOT NULL DEFAULT 'PENDING',
    completed_generation bigint,
    retry_request_id uuid,
    last_error_code text,
    last_error text,
    started_at timestamptz,
    finished_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (execution_id, ticker, timeframe),
    CHECK (timeframe = 'Daily'),
    CHECK (required_generation >= 0),
    CHECK (status IN ('PENDING','PROCESSING','SUCCESS','FAILED','BLOCKED','SUPERSEDED'))
);
CREATE INDEX "Monitoring_Feature04_Ticker_pending_idx"
    ON public."Monitoring_Feature04_Ticker" (ticker, timeframe, required_generation)
    WHERE status IN ('PENDING','PROCESSING');

CREATE TABLE public."Feature04_Retry_Request" (
    request_id uuid PRIMARY KEY,
    telegram_update_id bigint,
    chat_id bigint,
    request_scope text NOT NULL,
    source_execution_id text,
    ticker text,
    requested_columns text[],
    source_generation bigint NOT NULL,
    work_revision bigint NOT NULL,
    status text NOT NULL DEFAULT 'PENDING',
    child_execution_id text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at timestamptz,
    finished_at timestamptz,
    last_error text,
    UNIQUE (telegram_update_id),
    CHECK (request_scope IN ('TICKER','COLUMN')),
    CHECK ((request_scope = 'TICKER' AND requested_columns IS NULL)
        OR (request_scope = 'COLUMN' AND requested_columns IS NOT NULL AND cardinality(requested_columns) > 0)),
    CHECK (source_generation >= 0 AND work_revision > 0),
    CHECK (status IN ('PENDING','PROCESSING','SUCCESS','PARTIAL','FAILED','SUPERSEDED','CANCELLED'))
);
ALTER TABLE public."Feature04_Calculation_Log"
    ADD CONSTRAINT "Feature04_Calculation_Log_retry_fkey"
    FOREIGN KEY (retry_request_id) REFERENCES public."Feature04_Retry_Request"(request_id);
ALTER TABLE public."Monitoring_Feature04_Ticker"
    ADD CONSTRAINT "Monitoring_Feature04_Ticker_retry_fkey"
    FOREIGN KEY (retry_request_id) REFERENCES public."Feature04_Retry_Request"(request_id);

CREATE TABLE public."Feature04_Notification_Outbox" (
    event_id uuid PRIMARY KEY,
    execution_id text NOT NULL REFERENCES public."Monitoring_Feature04"(execution_id) ON DELETE CASCADE,
    notification_type text NOT NULL DEFAULT 'COMPLETED',
    status text NOT NULL DEFAULT 'PENDING',
    attempt_count integer NOT NULL DEFAULT 0,
    next_attempt_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    claimed_at timestamptz,
    claim_token uuid,
    claim_expires_at timestamptz,
    sent_at timestamptz,
    last_error text,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (execution_id, notification_type),
    CHECK (status IN ('PENDING','SENDING','SENT','FAILED')),
    CHECK (attempt_count >= 0),
    CHECK ((status = 'SENDING') =
           (claimed_at IS NOT NULL AND claim_token IS NOT NULL AND claim_expires_at IS NOT NULL))
);
CREATE INDEX "Feature04_Notification_Outbox_ready_idx"
    ON public."Feature04_Notification_Outbox" (next_attempt_at, created_at)
    WHERE status IN ('PENDING','FAILED');

ALTER TABLE public."Telegram_Command_Log"
    ADD COLUMN feature04_request_id uuid,
    ADD CONSTRAINT "Telegram_Command_Log_feature04_request_fkey"
        FOREIGN KEY (feature04_request_id) REFERENCES public."Feature04_Retry_Request"(request_id);

CREATE FUNCTION public.feature04_output_columns()
RETURNS text[]
LANGUAGE sql
IMMUTABLE
AS $function$
SELECT ARRAY[
 'sma_20','sma_50','ema_12','ema_26','rsi_14','macd','macd_signal','macd_histogram',
 'atr_14','bb_upper_20','bb_middle_20','bb_lower_20','cdl_piercing','cdl_morning_star',
 'cdl_morning_doji_star','cdl_engulfing','cdl_3_white_soldiers','cdl_hammer','cdl_inverted_hammer',
 'cdl_3_inside','cdl_3_outside','cdl_harami','cdl_harami_cross','cdl_dark_cloud_cover',
 'cdl_evening_star','cdl_evening_doji_star','cdl_3_black_crows','cdl_shooting_star','cdl_hanging_man',
 'cdl_doji','cdl_dragonfly_doji','cdl_gravestone_doji','cdl_marubozu','cdl_kicking',
 'cdl_rise_fall_3_methods','cdl_mat_hold','cdl_hikkake','adx_14','ema_50','ema_200','inside_bar',
 'smi','tracking_high','tracking_low','temp_high','temp_high_bar','temp_low','temp_low_bar',
 'last_swing_high','break_swing_high']::text[]
$function$;

CREATE FUNCTION public.enqueue_feature04_group(
    p_ticker text, p_dirty_date date, p_timeframe text, p_execution_id text DEFAULT NULL
)
RETURNS bigint
LANGUAGE plpgsql
AS $function$
DECLARE v_generation bigint;
BEGIN
    IF p_ticker IS NULL OR p_dirty_date IS NULL OR p_timeframe <> 'Daily' THEN
        RAISE EXCEPTION 'Valid ticker/date and Daily timeframe are required';
    END IF;
    INSERT INTO public."Feature04_Calculation_Queue"(
        ticker,timeframe,dirty_from_date,requested_generation,completed_generation,
        work_revision,requested_columns,origin_execution_id,status,next_attempt_at
    ) VALUES (p_ticker,p_timeframe,p_dirty_date,1,0,1,NULL,p_execution_id,'PENDING',CURRENT_TIMESTAMP)
    ON CONFLICT(ticker,timeframe) DO UPDATE SET
        dirty_from_date=least(public."Feature04_Calculation_Queue".dirty_from_date,EXCLUDED.dirty_from_date),
        requested_generation=public."Feature04_Calculation_Queue".requested_generation+1,
        work_revision=public."Feature04_Calculation_Queue".work_revision+1,
        requested_columns=NULL,
        origin_execution_id=EXCLUDED.origin_execution_id,
        status='PENDING',source_attempt_count=0,next_attempt_at=CURRENT_TIMESTAMP,
        claimed_at=NULL,claim_token=NULL,claim_expires_at=NULL,
        last_error_code=NULL,last_error=NULL,completed_at=NULL,updated_at=CURRENT_TIMESTAMP
    RETURNING requested_generation INTO v_generation;

    IF p_execution_id IS NOT NULL THEN
        INSERT INTO public."Monitoring_Feature04_Ticker"(
            execution_id,ticker,timeframe,required_generation,requested_columns,status
        ) VALUES(p_execution_id,p_ticker,p_timeframe,v_generation,NULL,'PENDING')
        ON CONFLICT(execution_id,ticker,timeframe) DO UPDATE SET
            required_generation=greatest(public."Monitoring_Feature04_Ticker".required_generation,EXCLUDED.required_generation),
            requested_columns=NULL,status='PENDING',updated_at=CURRENT_TIMESTAMP;
    END IF;
    RETURN v_generation;
END
$function$;

CREATE FUNCTION public.enqueue_feature04_price_row()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE v_execution_id text := nullif(current_setting('saniti.feature04_execution_id',true),'');
BEGIN
    IF TG_OP = 'DELETE' THEN
        PERFORM public.enqueue_feature04_group(OLD.ticker,OLD.date,OLD.timeframe,v_execution_id);
        RETURN NULL;
    END IF;
    IF TG_OP = 'INSERT' THEN
        PERFORM public.enqueue_feature04_group(NEW.ticker,NEW.date,NEW.timeframe,v_execution_id);
        RETURN NULL;
    END IF;
    IF ROW(NEW.ticker,NEW.date,NEW.timeframe,NEW.open,NEW.high,NEW.low,NEW.close,NEW.volume,NEW.source,NEW.tradingview_symbol)
       IS DISTINCT FROM
       ROW(OLD.ticker,OLD.date,OLD.timeframe,OLD.open,OLD.high,OLD.low,OLD.close,OLD.volume,OLD.source,OLD.tradingview_symbol) THEN
        IF ROW(OLD.ticker,OLD.date,OLD.timeframe) IS DISTINCT FROM ROW(NEW.ticker,NEW.date,NEW.timeframe) THEN
            PERFORM public.enqueue_feature04_group(OLD.ticker,OLD.date,OLD.timeframe,v_execution_id);
        END IF;
        PERFORM public.enqueue_feature04_group(NEW.ticker,NEW.date,NEW.timeframe,v_execution_id);
    END IF;
    RETURN NULL;
END
$function$;

CREATE TRIGGER "Price_Stock_Indonesia_IDX_enqueue_feature04"
AFTER INSERT OR UPDATE OR DELETE ON public."Price_Stock_Indonesia_IDX"
FOR EACH ROW EXECUTE FUNCTION public.enqueue_feature04_price_row();

CREATE FUNCTION public.request_feature04_retry(
    p_chat_id bigint, p_telegram_update_id bigint, p_ticker text,
    p_columns text[] DEFAULT NULL, p_source_execution_id text DEFAULT NULL
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $function$
DECLARE
    v_request_id uuid := gen_random_uuid();
    v_child_execution_id text := 'f04-retry-' || v_request_id::text;
    v_generation bigint;
    v_revision bigint;
    v_invalid text[];
    v_scope text := CASE WHEN p_columns IS NULL THEN 'TICKER' ELSE 'COLUMN' END;
BEGIN
    IF p_ticker IS NULL OR p_ticker <> upper(btrim(p_ticker)) OR p_ticker = '' THEN
        RAISE EXCEPTION 'A canonical ticker is required';
    END IF;
    IF NOT EXISTS(SELECT 1 FROM public."Price_Stock_Indonesia_IDX" WHERE ticker=p_ticker) THEN
        RAISE EXCEPTION 'Ticker % has no price source',p_ticker;
    END IF;
    IF p_columns IS NOT NULL THEN
        SELECT array_agg(value) INTO v_invalid
        FROM unnest(p_columns) value
        WHERE NOT value = ANY(public.feature04_output_columns());
        IF v_invalid IS NOT NULL THEN RAISE EXCEPTION 'Unsupported Feature04 columns: %',v_invalid; END IF;
        IF NOT EXISTS(
            SELECT 1 FROM public."Feature04_Column_Status"
            WHERE ticker=p_ticker AND timeframe='Daily' AND feature_column=ANY(p_columns)
              AND status IN ('FAILED','BLOCKED')
        ) THEN RAISE EXCEPTION 'Selected columns have no active failure for %',p_ticker; END IF;
    ELSIF NOT EXISTS(
        SELECT 1 FROM public."Feature04_Calculation_Queue" WHERE ticker=p_ticker AND timeframe='Daily' AND status='FAILED'
        UNION ALL
        SELECT 1 FROM public."Feature04_Column_Status" WHERE ticker=p_ticker AND timeframe='Daily' AND status IN ('FAILED','BLOCKED')
    ) THEN RAISE EXCEPTION 'Ticker % has no active Feature04 failure',p_ticker;
    END IF;

    INSERT INTO public."Feature04_Calculation_Queue"(
        ticker,timeframe,dirty_from_date,requested_generation,completed_generation,
        work_revision,requested_columns,status,next_attempt_at
    ) VALUES(
        p_ticker,'Daily',(SELECT min(date) FROM public."Price_Stock_Indonesia_IDX" WHERE ticker=p_ticker),
        1,0,1,p_columns,'PENDING',CURRENT_TIMESTAMP
    )
    ON CONFLICT(ticker,timeframe) DO UPDATE SET
        dirty_from_date=least(public."Feature04_Calculation_Queue".dirty_from_date,EXCLUDED.dirty_from_date),
        work_revision=public."Feature04_Calculation_Queue".work_revision+1,
        requested_columns=CASE
            WHEN public."Feature04_Calculation_Queue".requested_columns IS NULL OR EXCLUDED.requested_columns IS NULL THEN NULL
            ELSE ARRAY(SELECT DISTINCT value FROM unnest(public."Feature04_Calculation_Queue".requested_columns||EXCLUDED.requested_columns) value ORDER BY value)
        END,
        status='PENDING',source_attempt_count=0,next_attempt_at=CURRENT_TIMESTAMP,
        claimed_at=NULL,claim_token=NULL,claim_expires_at=NULL,
        last_error_code=NULL,last_error=NULL,completed_at=NULL,updated_at=CURRENT_TIMESTAMP
    RETURNING requested_generation,work_revision INTO v_generation,v_revision;

    INSERT INTO public."Feature04_Retry_Request"(
        request_id,telegram_update_id,chat_id,request_scope,source_execution_id,ticker,
        requested_columns,source_generation,work_revision,status,child_execution_id
    ) VALUES(v_request_id,p_telegram_update_id,p_chat_id,v_scope,p_source_execution_id,p_ticker,
             p_columns,v_generation,v_revision,'PENDING',v_child_execution_id);
    INSERT INTO public."Monitoring_Feature04"(
        execution_id,source_execution_id,run_type,trigger_source,price_notification_required,
        price_notification_sent_at,eligible_tickers,status
    ) VALUES(v_child_execution_id,p_source_execution_id,
             CASE WHEN p_columns IS NULL THEN 'RETRY_TICKER' ELSE 'RETRY_COLUMN' END,
             'TELEGRAM',false,CURRENT_TIMESTAMP,1,'READY');
    INSERT INTO public."Monitoring_Feature04_Ticker"(
        execution_id,ticker,timeframe,required_generation,requested_columns,status,retry_request_id
    ) VALUES(v_child_execution_id,p_ticker,'Daily',v_generation,p_columns,'PENDING',v_request_id);
    RETURN v_request_id;
END
$function$;

REVOKE ALL ON FUNCTION public.request_feature04_retry(bigint,bigint,text,text[],text) FROM PUBLIC;

-- The full historical v3 replay is the generation-zero baseline.
INSERT INTO public."Feature04_Column_Status"(
    ticker,timeframe,feature_column,requested_generation,completed_generation,
    calculation_version,status,validated_through,latest_value_available,null_reason,last_calculated_at
)
SELECT latest.ticker,'Daily',column_name,0,0,latest.calculation_version,'SUCCESS',latest.trade_date,
       CASE column_name
           WHEN 'ema_200' THEN latest.ema_200 IS NOT NULL
           WHEN 'smi' THEN latest.smi IS NOT NULL
           ELSE true
       END,
       CASE WHEN column_name='ema_200' AND latest.ema_200 IS NULL THEN 'INSUFFICIENT_HISTORY'
            WHEN column_name='smi' AND latest.smi IS NULL THEN 'ZERO_RANGE'
            ELSE NULL END,
       latest.calculated_at
FROM (
    SELECT DISTINCT ON(ticker) * FROM public."Feature04_Technical_Indicator"
    WHERE timeframe='Daily' ORDER BY ticker,trade_date DESC
) latest
CROSS JOIN LATERAL unnest(public.feature04_output_columns()) column_name;

COMMENT ON TABLE public."Feature04_Calculation_Queue" IS 'Durable coalesced Feature04 work per ticker/timeframe; generation tracks source change and work_revision tracks retry scope.';
COMMENT ON TABLE public."Feature04_Column_Status" IS 'Current readiness/failure state for each Feature04 output column per ticker; expected NULL is a successful availability outcome.';
COMMENT ON TABLE public."Feature04_Calculation_Log" IS 'Immutable Feature04 worker attempt history with per-group success/failure and retry lineage.';
COMMENT ON TABLE public."Monitoring_Feature04" IS 'Feature04 batch/retry run summary and price-notification ordering gate.';
COMMENT ON TABLE public."Monitoring_Feature04_Ticker" IS 'Per-ticker membership and terminal result for one Feature04 run.';
COMMENT ON TABLE public."Feature04_Retry_Request" IS 'Audited owner Telegram retry request for one failed ticker or failed indicator bundle.';
COMMENT ON TABLE public."Feature04_Notification_Outbox" IS 'Durable Feature04 completion delivery request; calculation success never depends on Telegram availability.';

INSERT INTO public."Table_Catalog"(
    table_schema,table_name,category,definition,grain,primary_key_columns,
    source_system,source_tables,source_code_paths,update_rule,related_functions,documentation_status
)
VALUES
('public','Feature04_Calculation_Queue','System','Durable coalesced Feature04 work and lease state.','ticker x timeframe',ARRAY['ticker','timeframe'],'PostgreSQL price trigger / Feature04 worker',ARRAY['Price_Stock_Indonesia_IDX'],ARRAY['database/migrations/20261011_005_automate_feature04.sql','apps/feature-04-worker/worker.py'],'Relevant price changes enqueue full refresh; Telegram retry reopens failed ticker/column scope.',ARRAY['enqueue_feature04_group(text,date,text,text)','enqueue_feature04_price_row()','request_feature04_retry(bigint,bigint,text,text[],text)'],'VERIFIED'),
('public','Feature04_Column_Status','System','Per-ticker per-output Feature04 readiness and failure state.','ticker x timeframe x feature_column',ARRAY['ticker','timeframe','feature_column'],'Feature04 worker',ARRAY['Feature04_Technical_Indicator'],ARRAY['database/migrations/20261011_005_automate_feature04.sql','apps/feature-04-worker/worker.py'],'Worker advances only validated output bundles; expected NULL remains SUCCESS.',ARRAY[]::text[],'VERIFIED'),
('public','Feature04_Calculation_Log','System','Immutable Feature04 calculation attempt audit.','one worker attempt',ARRAY['id'],'Feature04 worker',ARRAY['Feature04_Calculation_Queue'],ARRAY['database/migrations/20261011_005_automate_feature04.sql','apps/feature-04-worker/worker.py'],'One terminal attempt row per claim, including partial and superseded results.',ARRAY[]::text[],'VERIFIED'),
('public','Monitoring_Feature04','Monitoring','Feature04 automatic/retry batch summary and notification ordering gate.','one execution',ARRAY['execution_id'],'Price cron / Feature04 worker',ARRAY['Monitoring_Price_ALL','Feature04_Calculation_Queue'],ARRAY['database/migrations/20261011_005_automate_feature04.sql','apps/idx-price-cron/price_update.py','apps/feature-04-worker/worker.py','apps/telegram-monitor/telegram_monitor.py'],'Price writer opens/seals automatic runs; worker finalizes; monitor records price delivery.',ARRAY[]::text[],'VERIFIED'),
('public','Monitoring_Feature04_Ticker','Monitoring','Per-ticker membership and outcome of a Feature04 execution.','execution x ticker x timeframe',ARRAY['execution_id','ticker','timeframe'],'Price trigger / Feature04 worker',ARRAY['Monitoring_Feature04','Feature04_Calculation_Queue'],ARRAY['database/migrations/20261011_005_automate_feature04.sql','apps/feature-04-worker/worker.py'],'Trigger records required generation; worker records terminal result.',ARRAY[]::text[],'VERIFIED'),
('public','Feature04_Retry_Request','System','Audited Telegram failure-only retry request.','one owner retry request',ARRAY['request_id'],'telegram-trigger',ARRAY['Feature04_Calculation_Queue','Feature04_Column_Status'],ARRAY['database/migrations/20261011_005_automate_feature04.sql','apps/telegram-trigger/telegram_trigger.py'],'Owner command selects an active failure and atomically opens a child run.',ARRAY['request_feature04_retry(bigint,bigint,text,text[],text)'],'VERIFIED'),
('public','Feature04_Notification_Outbox','System','Durable Feature04 completion-notification work.','one execution x notification type',ARRAY['event_id'],'Feature04 worker',ARRAY['Monitoring_Feature04'],ARRAY['database/migrations/20261011_005_automate_feature04.sql','apps/feature-04-worker/worker.py','apps/telegram-monitor/telegram_monitor.py'],'Worker inserts after terminal run; dispatcher retries independently of calculations.',ARRAY[]::text[],'VERIFIED');

INSERT INTO public."Column_Catalog"(
    table_schema,table_name,column_name,ordinal_position,data_type,is_nullable,
    default_expression,is_primary_key,definition,source_column_or_expression,
    unit,null_rule,source_code_paths,documentation_status
)
SELECT c.table_schema,c.table_name,c.column_name,c.ordinal_position,c.data_type,
       c.is_nullable='YES',c.column_default,
       EXISTS(SELECT 1 FROM pg_constraint k
              WHERE k.conrelid=(quote_ident(c.table_schema)||'.'||quote_ident(c.table_name))::regclass
                AND k.contype='p' AND EXISTS(
                    SELECT 1 FROM unnest(k.conkey) key(attnum)
                    JOIN pg_attribute a ON a.attrelid=k.conrelid AND a.attnum=key.attnum
                    WHERE a.attname=c.column_name)),
       'Operational '||replace(c.column_name,'_',' ')||' field for '||c.table_name||'.',
       'Written by the documented Feature04 automation flow.',NULL,
       CASE WHEN c.is_nullable='YES' THEN 'NULL only when the lifecycle state does not require this field.' ELSE 'Required.' END,
       ARRAY['database/migrations/20261011_005_automate_feature04.sql'], 'VERIFIED'
FROM information_schema.columns c
WHERE c.table_schema='public' AND c.table_name IN (
 'Feature04_Calculation_Queue','Feature04_Column_Status','Feature04_Calculation_Log',
 'Monitoring_Feature04','Monitoring_Feature04_Ticker','Feature04_Retry_Request','Feature04_Notification_Outbox'
);

UPDATE public."Table_Catalog"
SET related_functions=array_append(related_functions,'enqueue_feature04_price_row()'),
    source_code_paths=array_append(source_code_paths,'database/migrations/20261011_005_automate_feature04.sql'),
    update_rule='DAILY/RECOVERY upserts exact-date prices; relevant committed source changes transactionally enqueue Feature01 and Feature04.'
WHERE table_schema='public' AND table_name='Price_Stock_Indonesia_IDX'
  AND NOT 'enqueue_feature04_price_row()'=ANY(related_functions);

UPDATE public."Table_Catalog"
SET source_code_paths=array_append(source_code_paths,'apps/feature-04-worker/worker.py'),
    update_rule='The Feature04 worker writes full or dependency-closed column bundles after source-generation validation; Telegram retries only active failures.'
WHERE table_schema='public' AND table_name='Feature04_Technical_Indicator'
  AND NOT 'apps/feature-04-worker/worker.py'=ANY(source_code_paths);

UPDATE public."Table_Catalog"
SET related_functions=array_append(related_functions,'request_feature04_retry(bigint,bigint,text,text[],text)'),
    source_code_paths=array_append(source_code_paths,'database/migrations/20261011_005_automate_feature04.sql')
WHERE table_schema='public' AND table_name='Telegram_Command_Log'
  AND NOT 'request_feature04_retry(bigint,bigint,text,text[],text)'=ANY(related_functions);

INSERT INTO public."Column_Catalog"(
 table_schema,table_name,column_name,ordinal_position,data_type,is_nullable,default_expression,
 is_primary_key,definition,source_column_or_expression,unit,null_rule,source_code_paths,documentation_status
)
SELECT 'public','Telegram_Command_Log',c.column_name,c.ordinal_position,c.data_type,true,c.column_default,false,
       'Optional Feature04 retry request created by this Telegram command.',
       'request_feature04_retry(...) result',NULL,'NULL for price/recovery commands.',
       ARRAY['database/migrations/20261011_005_automate_feature04.sql','apps/telegram-trigger/telegram_trigger.py'],'VERIFIED'
FROM information_schema.columns c
WHERE c.table_schema='public' AND c.table_name='Telegram_Command_Log' AND c.column_name='feature04_request_id';

COMMIT;
