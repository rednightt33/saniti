BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '5min';

DO $preflight$
BEGIN
    IF to_regclass('public."Feature_Calculation_Queue"') IS NOT NULL
       OR to_regclass('public."Feature_Status"') IS NOT NULL
       OR to_regclass('public."Feature_Calculation_Log"') IS NOT NULL THEN
        RAISE EXCEPTION 'Feature calculation control table already exists';
    END IF;
    IF to_regclass('public."Price_Stock_Indonesia_IDX"') IS NULL
       OR to_regclass('public."Feature_01_Stock_Daily"') IS NULL
       OR to_regclass('public."Table_Catalog"') IS NULL
       OR to_regclass('public."Column_Catalog"') IS NULL THEN
        RAISE EXCEPTION 'Required price, Feature 01, or catalog table is missing';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'Price_Stock_Indonesia_IDX'
          AND column_name = 'ingestion_time'
    ) THEN
        RAISE EXCEPTION 'Price source ingestion_time is missing';
    END IF;
END
$preflight$;

CREATE TABLE public."Feature_Calculation_Queue" (
    feature_table text NOT NULL DEFAULT 'Feature_01_Stock_Daily',
    ticker text NOT NULL,
    price_date date NOT NULL,
    source_ingestion_time timestamptz NOT NULL,
    source_execution_id text,
    status text NOT NULL DEFAULT 'PENDING',
    attempt_count integer NOT NULL DEFAULT 0,
    next_attempt_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    claimed_at timestamptz,
    claim_token uuid,
    claim_expires_at timestamptz,
    last_error text,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at timestamptz,
    CONSTRAINT "Feature_Calculation_Queue_pkey"
        PRIMARY KEY (feature_table, ticker, price_date),
    CONSTRAINT "Feature_Calculation_Queue_price_fkey"
        FOREIGN KEY (ticker, price_date)
        REFERENCES public."Price_Stock_Indonesia_IDX" (ticker, date),
    CONSTRAINT "Feature_Calculation_Queue_feature_check"
        CHECK (feature_table = 'Feature_01_Stock_Daily'),
    CONSTRAINT "Feature_Calculation_Queue_status_check"
        CHECK (status IN ('PENDING', 'PROCESSING', 'DONE', 'FAILED')),
    CONSTRAINT "Feature_Calculation_Queue_attempt_check"
        CHECK (attempt_count >= 0),
    CONSTRAINT "Feature_Calculation_Queue_claim_check"
        CHECK (
            (status = 'PROCESSING') =
            (claimed_at IS NOT NULL AND claim_token IS NOT NULL
             AND claim_expires_at IS NOT NULL)
        ),
    CONSTRAINT "Feature_Calculation_Queue_completion_check"
        CHECK ((status = 'DONE') = (completed_at IS NOT NULL)),
    CONSTRAINT "Feature_Calculation_Queue_timestamps_check"
        CHECK (updated_at >= created_at)
);

CREATE INDEX "Feature_Calculation_Queue_ready_idx"
    ON public."Feature_Calculation_Queue" (next_attempt_at, created_at)
    WHERE status IN ('PENDING', 'FAILED');
CREATE INDEX "Feature_Calculation_Queue_lease_idx"
    ON public."Feature_Calculation_Queue" (claim_expires_at)
    WHERE status = 'PROCESSING';
CREATE INDEX "Feature_Calculation_Queue_ticker_state_idx"
    ON public."Feature_Calculation_Queue" (feature_table, ticker, status, price_date);

CREATE TABLE public."Feature_Status" (
    feature_table text NOT NULL DEFAULT 'Feature_01_Stock_Daily',
    ticker text NOT NULL,
    latest_price_date date NOT NULL,
    latest_source_ingestion_time timestamptz NOT NULL,
    last_successful_source_ingestion_time timestamptz,
    last_successful_price_date date,
    last_calculated_at timestamptz,
    pending_count integer NOT NULL DEFAULT 0,
    processing_count integer NOT NULL DEFAULT 0,
    failed_count integer NOT NULL DEFAULT 0,
    status text NOT NULL DEFAULT 'PENDING',
    last_error text,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Feature_Status_pkey" PRIMARY KEY (feature_table, ticker),
    CONSTRAINT "Feature_Status_feature_check"
        CHECK (feature_table = 'Feature_01_Stock_Daily'),
    CONSTRAINT "Feature_Status_status_check"
        CHECK (status IN ('PENDING', 'PROCESSING', 'SUCCESS', 'FAILED')),
    CONSTRAINT "Feature_Status_counts_check"
        CHECK (pending_count >= 0 AND processing_count >= 0 AND failed_count >= 0),
    CONSTRAINT "Feature_Status_success_check"
        CHECK (
            status <> 'SUCCESS'
            OR (
                pending_count = 0 AND processing_count = 0 AND failed_count = 0
                AND last_successful_source_ingestion_time IS NOT NULL
                AND last_successful_source_ingestion_time >= latest_source_ingestion_time
            )
        )
);

CREATE INDEX "Feature_Status_state_idx"
    ON public."Feature_Status" (feature_table, status, updated_at);

CREATE TABLE public."Feature_Calculation_Log" (
    id bigint GENERATED ALWAYS AS IDENTITY,
    feature_table text NOT NULL,
    ticker text NOT NULL,
    price_date date NOT NULL,
    source_ingestion_time timestamptz NOT NULL,
    attempt_no integer NOT NULL,
    result text NOT NULL,
    started_at timestamptz NOT NULL,
    finished_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    rows_refreshed integer,
    detail text,
    CONSTRAINT "Feature_Calculation_Log_pkey" PRIMARY KEY (id),
    CONSTRAINT "Feature_Calculation_Log_queue_fkey"
        FOREIGN KEY (feature_table, ticker, price_date)
        REFERENCES public."Feature_Calculation_Queue"
            (feature_table, ticker, price_date),
    CONSTRAINT "Feature_Calculation_Log_attempt_key"
        UNIQUE (feature_table, ticker, price_date, attempt_no),
    CONSTRAINT "Feature_Calculation_Log_attempt_check" CHECK (attempt_no > 0),
    CONSTRAINT "Feature_Calculation_Log_result_check"
        CHECK (result IN ('SUCCESS', 'FAILED', 'SUPERSEDED')),
    CONSTRAINT "Feature_Calculation_Log_time_check"
        CHECK (finished_at >= started_at),
    CONSTRAINT "Feature_Calculation_Log_rows_check"
        CHECK (rows_refreshed IS NULL OR rows_refreshed >= 0)
);

CREATE INDEX "Feature_Calculation_Log_ticker_time_idx"
    ON public."Feature_Calculation_Log"
        (feature_table, ticker, started_at DESC);

COMMENT ON TABLE public."Feature_Calculation_Queue" IS
    'Durable Feature 01 work item per changed price candle; DONE means feature calculation succeeded, not price ingestion.';
COMMENT ON TABLE public."Feature_Status" IS
    'Current per-ticker Feature 01 calculation state; SUCCESS requires all committed source changes to be processed.';
COMMENT ON TABLE public."Feature_Calculation_Log" IS
    'Completed attempt history for Feature 01 calculation queue items, including retries and superseded claims.';

DO $comments$
DECLARE
    item record;
BEGIN
    FOR item IN
        SELECT * FROM (VALUES
            ('Feature_Calculation_Queue','feature_table','Target Feature table; currently restricted to Feature_01_Stock_Daily.'),
            ('Feature_Calculation_Queue','ticker','Ticker of the changed source candle.'),
            ('Feature_Calculation_Queue','price_date','Trading date of the changed source candle.'),
            ('Feature_Calculation_Queue','source_ingestion_time','Source candle ingestion timestamp captured when the work item is enqueued.'),
            ('Feature_Calculation_Queue','source_execution_id','Optional source price-run execution identifier.'),
            ('Feature_Calculation_Queue','status','Work state: PENDING, PROCESSING, DONE, or FAILED.'),
            ('Feature_Calculation_Queue','attempt_count','Number of worker claims made for this queue key.'),
            ('Feature_Calculation_Queue','next_attempt_at','Earliest time when a pending or failed item may be claimed.'),
            ('Feature_Calculation_Queue','claimed_at','Time the active worker claim began.'),
            ('Feature_Calculation_Queue','claim_token','Unique token of the active worker claim.'),
            ('Feature_Calculation_Queue','claim_expires_at','Lease expiry of the active worker claim.'),
            ('Feature_Calculation_Queue','last_error','Concise error from the most recent failed attempt.'),
            ('Feature_Calculation_Queue','created_at','Time this queue key was first created.'),
            ('Feature_Calculation_Queue','updated_at','Time the queue row was last changed by the writer or worker.'),
            ('Feature_Calculation_Queue','completed_at','Time the current source version completed Feature calculation.'),
            ('Feature_Status','feature_table','Target Feature table; currently restricted to Feature_01_Stock_Daily.'),
            ('Feature_Status','ticker','Ticker summarized by this status row.'),
            ('Feature_Status','latest_price_date','Latest trading date observed for this ticker by the enqueue flow.'),
            ('Feature_Status','latest_source_ingestion_time','Latest source ingestion timestamp observed by the enqueue flow.'),
            ('Feature_Status','last_successful_source_ingestion_time','Latest source version covered by a validated Feature calculation.'),
            ('Feature_Status','last_successful_price_date','Latest trading date covered by a validated Feature calculation.'),
            ('Feature_Status','last_calculated_at','Time of the latest validated Feature calculation.'),
            ('Feature_Status','pending_count','Number of PENDING queue rows for this ticker.'),
            ('Feature_Status','processing_count','Number of PROCESSING queue rows for this ticker.'),
            ('Feature_Status','failed_count','Number of FAILED queue rows for this ticker.'),
            ('Feature_Status','status','Current ticker state: PENDING, PROCESSING, SUCCESS, or FAILED.'),
            ('Feature_Status','last_error','Concise most recent calculation error for this ticker.'),
            ('Feature_Status','updated_at','Time this status summary was last changed.'),
            ('Feature_Calculation_Log','id','Unique completed-attempt record identifier.'),
            ('Feature_Calculation_Log','feature_table','Target Feature table of the attempted work item.'),
            ('Feature_Calculation_Log','ticker','Ticker of the attempted work item.'),
            ('Feature_Calculation_Log','price_date','Source trading date of the attempted work item.'),
            ('Feature_Calculation_Log','source_ingestion_time','Source version captured by this worker attempt.'),
            ('Feature_Calculation_Log','attempt_no','Monotonic attempt number for this queue key.'),
            ('Feature_Calculation_Log','result','Attempt outcome: SUCCESS, FAILED, or SUPERSEDED by newer source data.'),
            ('Feature_Calculation_Log','started_at','Time the worker attempt began.'),
            ('Feature_Calculation_Log','finished_at','Time the worker attempt finished.'),
            ('Feature_Calculation_Log','rows_refreshed','Number of Feature rows refreshed, if measured by the worker.'),
            ('Feature_Calculation_Log','detail','Concise outcome or error detail without credentials.')
        ) AS descriptions(table_name, column_name, definition)
    LOOP
        EXECUTE format('COMMENT ON COLUMN public.%I.%I IS %L',
                       item.table_name, item.column_name, item.definition);
    END LOOP;
END
$comments$;

INSERT INTO public."Table_Catalog" (
    table_name, category, definition, grain, primary_key_columns,
    source_system, source_tables, source_code_paths, update_rule,
    related_functions, documentation_status
)
VALUES
    ('Feature_Calculation_Queue', 'System',
     'Durable pending and completed Feature 01 calculation work per changed source candle.',
     'One row per feature table, ticker, and source trading date',
     ARRAY['feature_table','ticker','price_date'], 'Price ingestion and Feature worker',
     ARRAY['Price_Stock_Indonesia_IDX'],
     ARRAY['database/migrations/20260913_004_create_feature_calculation_control.sql'],
     'Writer must enqueue in the same transaction as a price upsert; worker later claims and completes. No writer or worker is activated by this migration.',
     ARRAY[]::text[], 'PARTIAL'),
    ('Feature_Status', 'System',
     'Current Feature 01 calculation freshness and outstanding-work summary per ticker.',
     'One row per feature table and ticker',
     ARRAY['feature_table','ticker'], 'Feature worker',
     ARRAY['Feature_Calculation_Queue','Feature_01_Stock_Daily'],
     ARRAY['database/migrations/20260913_004_create_feature_calculation_control.sql'],
     'Maintained by future enqueue and worker transitions; empty until integration is activated.',
     ARRAY[]::text[], 'PARTIAL'),
    ('Feature_Calculation_Log', 'System',
     'Completed attempt and retry history for Feature 01 calculation work.',
     'One row per queue key and attempt number', ARRAY['id'],
     'Feature worker', ARRAY['Feature_Calculation_Queue'],
     ARRAY['database/migrations/20260913_004_create_feature_calculation_control.sql'],
     'Future worker inserts one immutable result per completed attempt.',
     ARRAY[]::text[], 'PARTIAL');

INSERT INTO public."Column_Catalog" (
    table_schema, table_name, column_name, ordinal_position, data_type,
    is_nullable, default_expression, is_primary_key, definition,
    source_code_paths, documentation_status
)
SELECT
    columns.table_schema, columns.table_name, columns.column_name,
    columns.ordinal_position, columns.data_type, columns.is_nullable = 'YES',
    columns.column_default,
    EXISTS (
        SELECT 1
        FROM information_schema.table_constraints AS constraint_definition
        JOIN information_schema.key_column_usage AS key_column
          ON key_column.constraint_catalog = constraint_definition.constraint_catalog
         AND key_column.constraint_schema = constraint_definition.constraint_schema
         AND key_column.constraint_name = constraint_definition.constraint_name
         AND key_column.table_schema = constraint_definition.table_schema
         AND key_column.table_name = constraint_definition.table_name
        WHERE constraint_definition.constraint_type = 'PRIMARY KEY'
          AND constraint_definition.table_schema = columns.table_schema
          AND constraint_definition.table_name = columns.table_name
          AND key_column.column_name = columns.column_name
    ),
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
  AND columns.table_name IN (
      'Feature_Calculation_Queue', 'Feature_Status', 'Feature_Calculation_Log'
  );

DO $validate$
DECLARE
    physical_count integer;
    catalog_count integer;
BEGIN
    SELECT count(*) INTO physical_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name IN (
          'Feature_Calculation_Queue', 'Feature_Status', 'Feature_Calculation_Log'
      );
    SELECT count(*) INTO catalog_count
    FROM public."Column_Catalog"
    WHERE table_schema = 'public'
      AND table_name IN (
          'Feature_Calculation_Queue', 'Feature_Status', 'Feature_Calculation_Log'
      );
    IF physical_count <> 39 OR catalog_count <> physical_count THEN
        RAISE EXCEPTION 'Feature control catalog mismatch: physical %, catalog %',
            physical_count, catalog_count;
    END IF;
END
$validate$;

COMMIT;
