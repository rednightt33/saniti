BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '5min';

DO $preflight$
BEGIN
    IF to_regprocedure('public.refresh_feature_01_control_status(text,boolean)') IS NOT NULL
       OR to_regprocedure('public.enqueue_feature_01_price_row()') IS NOT NULL THEN
        RAISE EXCEPTION 'Feature 01 queue routines already exist';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgrelid = 'public."Price_Stock_Indonesia_IDX"'::regclass
          AND tgname = 'Price_Stock_Indonesia_IDX_enqueue_feature_01'
          AND NOT tgisinternal
    ) THEN
        RAISE EXCEPTION 'Feature 01 price enqueue trigger already exists';
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'Feature_Calculation_Queue'
          AND column_name = 'source_attempt_count'
    ) THEN
        RAISE EXCEPTION 'source_attempt_count already exists';
    END IF;
END
$preflight$;

ALTER TABLE public."Feature_Calculation_Queue"
    ADD COLUMN source_attempt_count integer NOT NULL DEFAULT 0,
    ADD CONSTRAINT "Feature_Calculation_Queue_source_attempt_check"
        CHECK (source_attempt_count >= 0 AND source_attempt_count <= attempt_count);

COMMENT ON COLUMN public."Feature_Calculation_Queue".source_attempt_count IS
    'Worker claims for the current price ingestion version; resets on source re-ingestion while attempt_count remains lifetime-monotonic.';

CREATE FUNCTION public.refresh_feature_01_control_status(
    p_ticker text,
    p_calculation_succeeded boolean DEFAULT false
)
RETURNS text
LANGUAGE plpgsql
AS $function$
DECLARE
    current_status public."Feature_Status"%ROWTYPE;
    v_latest_price_date date;
    v_latest_source_version timestamptz;
    v_last_done_version timestamptz;
    v_last_done_date date;
    v_pending_items integer;
    v_processing_items integer;
    v_failed_items integer;
    v_successful_version timestamptz;
    v_successful_date date;
    v_new_status text;
BEGIN
    IF p_ticker IS NULL OR btrim(p_ticker) = '' THEN
        RAISE EXCEPTION 'Ticker is required to reconcile Feature 01 status';
    END IF;

    INSERT INTO public."Feature_Status" (
        feature_table, ticker, latest_price_date, latest_source_ingestion_time
    )
    SELECT
        'Feature_01_Stock_Daily', p_ticker,
        max(price_date), max(source_ingestion_time)
    FROM public."Feature_Calculation_Queue"
    WHERE feature_table = 'Feature_01_Stock_Daily' AND ticker = p_ticker
    HAVING count(*) > 0
    ON CONFLICT (feature_table, ticker) DO NOTHING;

    SELECT * INTO current_status
    FROM public."Feature_Status"
    WHERE feature_table = 'Feature_01_Stock_Daily' AND ticker = p_ticker
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'No Feature 01 queue rows exist for ticker %', p_ticker;
    END IF;

    SELECT
        max(price_date), max(source_ingestion_time),
        max(source_ingestion_time) FILTER (WHERE status = 'DONE'),
        max(price_date) FILTER (WHERE status = 'DONE'),
        count(*) FILTER (WHERE status = 'PENDING'),
        count(*) FILTER (WHERE status = 'PROCESSING'),
        count(*) FILTER (WHERE status = 'FAILED')
    INTO v_latest_price_date, v_latest_source_version,
         v_last_done_version, v_last_done_date,
         v_pending_items, v_processing_items, v_failed_items
    FROM public."Feature_Calculation_Queue"
    WHERE feature_table = 'Feature_01_Stock_Daily' AND ticker = p_ticker;

    v_successful_version := current_status.last_successful_source_ingestion_time;
    v_successful_date := current_status.last_successful_price_date;
    IF p_calculation_succeeded AND v_last_done_version IS NOT NULL THEN
        v_successful_version := coalesce(
            greatest(v_successful_version, v_last_done_version), v_last_done_version
        );
        v_successful_date := coalesce(
            greatest(v_successful_date, v_last_done_date), v_last_done_date
        );
    END IF;

    v_new_status := CASE
        WHEN v_pending_items > 0 THEN 'PENDING'
        WHEN v_processing_items > 0 THEN 'PROCESSING'
        WHEN v_failed_items > 0 THEN 'FAILED'
        WHEN v_successful_version IS NOT NULL
         AND v_successful_version >= v_latest_source_version THEN 'SUCCESS'
        ELSE 'PENDING'
    END;

    UPDATE public."Feature_Status"
    SET latest_price_date = v_latest_price_date,
        latest_source_ingestion_time = v_latest_source_version,
        last_successful_source_ingestion_time = v_successful_version,
        last_successful_price_date = v_successful_date,
        last_calculated_at = CASE
            WHEN p_calculation_succeeded THEN CURRENT_TIMESTAMP
            ELSE current_status.last_calculated_at
        END,
        pending_count = v_pending_items,
        processing_count = v_processing_items,
        failed_count = v_failed_items,
        status = v_new_status,
        last_error = CASE
            WHEN v_new_status = 'FAILED' THEN (
                SELECT last_error
                FROM public."Feature_Calculation_Queue"
                WHERE feature_table = 'Feature_01_Stock_Daily'
                  AND ticker = p_ticker AND status = 'FAILED'
                ORDER BY updated_at DESC
                LIMIT 1
            )
            ELSE NULL
        END,
        updated_at = CURRENT_TIMESTAMP
    WHERE feature_table = 'Feature_01_Stock_Daily' AND ticker = p_ticker;

    RETURN v_new_status;
END
$function$;

CREATE FUNCTION public.enqueue_feature_01_price_row()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    INSERT INTO public."Feature_Calculation_Queue" (
        feature_table, ticker, price_date, source_ingestion_time,
        source_execution_id, status, next_attempt_at
    ) VALUES (
        'Feature_01_Stock_Daily', NEW.ticker, NEW.date,
        NEW.ingestion_time, NULL, 'PENDING', CURRENT_TIMESTAMP
    )
    ON CONFLICT (feature_table, ticker, price_date) DO UPDATE
    SET source_ingestion_time = EXCLUDED.source_ingestion_time,
        source_execution_id = NULL,
        status = 'PENDING',
        source_attempt_count = 0,
        next_attempt_at = CURRENT_TIMESTAMP,
        claimed_at = NULL,
        claim_token = NULL,
        claim_expires_at = NULL,
        last_error = NULL,
        completed_at = NULL,
        updated_at = CURRENT_TIMESTAMP;

    PERFORM public.refresh_feature_01_control_status(NEW.ticker, false);
    RETURN NULL;
END
$function$;

CREATE TRIGGER "Price_Stock_Indonesia_IDX_enqueue_feature_01"
AFTER INSERT OR UPDATE ON public."Price_Stock_Indonesia_IDX"
FOR EACH ROW
WHEN (NEW.ingestion_time IS NOT NULL)
EXECUTE FUNCTION public.enqueue_feature_01_price_row();

UPDATE public."Table_Catalog"
SET related_functions = ARRAY[
        'enqueue_feature_01_price_row()'
    ],
    update_rule = 'DAILY and RECOVERY price runs upsert exact-date candles; committed inserts/updates with non-null ingestion_time transactionally enqueue Feature 01 work.'
WHERE table_schema = 'public' AND table_name = 'Price_Stock_Indonesia_IDX';

UPDATE public."Table_Catalog"
SET related_functions = ARRAY[
        'enqueue_feature_01_price_row()',
        'refresh_feature_01_control_status(text,boolean)'
    ],
    update_rule = 'A price-row trigger transactionally creates/reopens work; a separate worker claims, calculates, retries, and completes it.',
    source_code_paths = ARRAY[
        'database/migrations/20260913_004_create_feature_calculation_control.sql',
        'database/migrations/20260913_006_activate_feature_01_queue.sql',
        'apps/feature-01-worker/worker.py'
    ]
WHERE table_schema = 'public' AND table_name = 'Feature_Calculation_Queue';

UPDATE public."Table_Catalog"
SET related_functions = ARRAY[
        'refresh_feature_01_control_status(text,boolean)'
    ],
    update_rule = 'Price enqueue and worker transitions reconcile the per-ticker summary; SUCCESS follows validated completion only.',
    source_code_paths = ARRAY[
        'database/migrations/20260913_004_create_feature_calculation_control.sql',
        'database/migrations/20260913_006_activate_feature_01_queue.sql',
        'apps/feature-01-worker/worker.py'
    ]
WHERE table_schema = 'public' AND table_name = 'Feature_Status';

UPDATE public."Table_Catalog"
SET update_rule = 'The Feature 01 worker records one completed result for every claim, including retries and expired leases.',
    source_code_paths = ARRAY[
        'database/migrations/20260913_004_create_feature_calculation_control.sql',
        'apps/feature-01-worker/worker.py'
    ]
WHERE table_schema = 'public' AND table_name = 'Feature_Calculation_Log';

INSERT INTO public."Column_Catalog" (
    table_schema, table_name, column_name, ordinal_position,
    data_type, is_nullable, default_expression, is_primary_key,
    definition, source_code_paths, documentation_status
)
SELECT
    columns.table_schema, columns.table_name, columns.column_name,
    columns.ordinal_position, columns.data_type, columns.is_nullable = 'YES',
    columns.column_default, false,
    pg_catalog.col_description(class.oid, attributes.attnum),
    catalog.source_code_paths, 'PARTIAL'
FROM information_schema.columns AS columns
JOIN public."Table_Catalog" AS catalog
  ON catalog.table_schema = columns.table_schema
 AND catalog.table_name = columns.table_name
JOIN pg_catalog.pg_namespace AS namespace
  ON namespace.nspname = columns.table_schema
JOIN pg_catalog.pg_class AS class
  ON class.relnamespace = namespace.oid
 AND class.relname = columns.table_name
JOIN pg_catalog.pg_attribute AS attributes
  ON attributes.attrelid = class.oid
 AND attributes.attname = columns.column_name
WHERE columns.table_schema = 'public'
  AND columns.table_name = 'Feature_Calculation_Queue'
  AND columns.column_name = 'source_attempt_count';

COMMIT;
