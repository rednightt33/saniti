-- EXEC-M219 (user 2026-10-25, "Fix M219 ... seharusnya di feature 1 tidak ada IHSG karena IHSG sudah punya table
-- sendiri"): a universe index (IDX_Stock_Universe."Security Type" = 'index', today IHSG) never enters the stock Feature
-- tables; it has the dedicated *_INDEX tables. Class: the price-derived Feature pipelines (Feature 01 and 04) treated
-- every universe ticker as a stock.
-- - is_universe_index(): derived from the universe, so a second index needs no code.
-- - enqueue_feature_01_price_row and enqueue_feature04_group (every Feature 04 enqueue path calls it) skip an index; the
--   bodies are the live ones (md5 checked first) plus that test.
-- - stock_feature_index_guard on Feature_01_Stock_Daily and Feature_04_Technical_Indicator refuses an index row.
--   refresh_feature_01_stock_daily is unchanged: the INDEX bootstrap clones it to compute IHSG
--   (scripts/backfill_index_features.py:151) into its own staging tables.
-- - cleanup: the index rows of the stock Feature 01 table and the Feature 01 status row; the open Feature 04 queue and
--   status rows of the index. The DONE Feature 01 queue rows stay: Feature_Calculation_Log references them
--   (Feature_Calculation_Log_queue_fkey) and the worker claims only PENDING and FAILED rows.
-- Not included: the daily refresh of the *_INDEX tables (open INDEX routing item).
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '5min';

DO $preflight$
BEGIN
    IF (SELECT md5(prosrc) FROM pg_proc WHERE oid = 'public.enqueue_feature_01_price_row()'::regprocedure)
       <> 'ab3524eaf713676748fa41da6dee1afb' THEN
        RAISE EXCEPTION 'enqueue_feature_01_price_row differs from 20260913_006: reconcile first';
    END IF;
    IF (SELECT md5(prosrc) FROM pg_proc
        WHERE oid = 'public.enqueue_feature04_group(text,text,date,text,text)'::regprocedure)
       <> '21c8482f7be91634c2685a5e13127785' THEN
        RAISE EXCEPTION 'enqueue_feature04_group differs from 20261012_003: reconcile first';
    END IF;
    IF EXISTS (SELECT 1 FROM public."Feature_Calculation_Queue" q JOIN public."IDX_Stock_Universe" u
               ON u."Ticker" = q.ticker AND u."Security Type" = 'index' WHERE q.status <> 'DONE') THEN
        RAISE EXCEPTION 'An index Feature 01 queue row is open: let it finish, then rerun';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public."IDX_Stock_Universe" WHERE "Security Type" = 'index') THEN
        RAISE EXCEPTION 'No universe index found: nothing to separate';
    END IF;
    IF to_regclass('public."Feature_01_Stock_Daily_INDEX"') IS NULL
       OR to_regclass('public."Feature_04_Technical_Indicator_INDEX"') IS NULL THEN
        RAISE EXCEPTION 'The dedicated INDEX tables are missing';
    END IF;
END
$preflight$;

CREATE FUNCTION public.is_universe_index(p_ticker text)
RETURNS boolean
LANGUAGE sql
STABLE
AS $function$
    SELECT EXISTS (SELECT 1 FROM public."IDX_Stock_Universe" WHERE "Ticker" = p_ticker AND "Security Type" = 'index')
$function$;
COMMENT ON FUNCTION public.is_universe_index(text) IS
'EXEC-M219: true for a ticker the universe classifies as an index; such a ticker belongs to the *_INDEX Feature tables.';

CREATE OR REPLACE FUNCTION public.enqueue_feature_01_price_row()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    -- EXEC-M219: a universe index has its own Feature table (Feature_01_Stock_Daily_INDEX)
    IF public.is_universe_index(NEW.ticker) THEN
        RETURN NULL;
    END IF;
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

CREATE OR REPLACE FUNCTION public.enqueue_feature04_group(
    p_asset_type text,p_ticker text,p_dirty_date date,p_timeframe text,
    p_execution_id text DEFAULT NULL
)
RETURNS bigint
LANGUAGE plpgsql
AS $function$
DECLARE v_generation bigint;
BEGIN
    -- EXEC-M219: a universe index has its own Feature table (Feature_04_Technical_Indicator_INDEX)
    IF p_asset_type='equity' AND public.is_universe_index(p_ticker) THEN
        RETURN NULL;
    END IF;
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

CREATE FUNCTION public.validate_stock_feature_identity()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    IF public.is_universe_index(NEW.ticker) THEN
        RAISE EXCEPTION '% is a universe index: its rows belong to %_INDEX, not to %', NEW.ticker, TG_TABLE_NAME,
            TG_TABLE_NAME USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$function$;
COMMENT ON FUNCTION public.validate_stock_feature_identity() IS
'EXEC-M219: refuses a universe-index row in a stock Feature table (its own table is the *_INDEX one).';

-- the stock tables lose their index rows and queue state before the guard is attached
DELETE FROM public."Feature_01_Stock_Daily" WHERE public.is_universe_index(ticker);
DELETE FROM public."Feature_04_Technical_Indicator" WHERE public.is_universe_index(ticker);
DELETE FROM public."Feature_Status" WHERE public.is_universe_index(ticker);
DELETE FROM public."Feature04_Column_Status" WHERE asset_type = 'equity' AND public.is_universe_index(ticker);
DELETE FROM public."Feature04_Calculation_State" WHERE asset_type = 'equity' AND public.is_universe_index(ticker);
DELETE FROM public."Feature04_Calculation_Queue" WHERE asset_type = 'equity' AND public.is_universe_index(ticker);

CREATE TRIGGER stock_feature_index_guard
BEFORE INSERT OR UPDATE OF ticker ON public."Feature_01_Stock_Daily"
FOR EACH ROW EXECUTE FUNCTION public.validate_stock_feature_identity();
CREATE TRIGGER stock_feature_index_guard
BEFORE INSERT OR UPDATE OF ticker ON public."Feature_04_Technical_Indicator"
FOR EACH ROW EXECUTE FUNCTION public.validate_stock_feature_identity();

UPDATE public."Table_Catalog" SET
 definition = replace(definition, ' Includes universe-classified benchmark indices: missing index volume is NULL, and index price levels are in points.',
                      ' Universe-classified indices are not included: their rows are in Feature_01_Stock_Daily_INDEX (EXEC-M219).'),
 related_functions = related_functions || ARRAY['is_universe_index(text)', 'validate_stock_feature_identity()'],
 source_code_paths = source_code_paths || ARRAY['database/migrations/20261025_011_exclude_index_from_stock_features.sql'],
 updated_at = CURRENT_TIMESTAMP
WHERE table_schema = 'public' AND table_name = 'Feature_01_Stock_Daily';
UPDATE public."Table_Catalog" SET
 related_functions = related_functions || ARRAY['is_universe_index(text)', 'validate_stock_feature_identity()'],
 source_code_paths = source_code_paths || ARRAY['database/migrations/20261025_011_exclude_index_from_stock_features.sql'],
 updated_at = CURRENT_TIMESTAMP
WHERE table_schema = 'public' AND table_name = 'Feature_04_Technical_Indicator';

DO $verify$
BEGIN
    IF EXISTS (SELECT 1 FROM public."Feature_01_Stock_Daily" WHERE public.is_universe_index(ticker))
       OR EXISTS (SELECT 1 FROM public."Feature_04_Technical_Indicator" WHERE public.is_universe_index(ticker))
       OR EXISTS (SELECT 1 FROM public."Feature_Calculation_Queue" WHERE public.is_universe_index(ticker) AND status <> 'DONE')
       OR EXISTS (SELECT 1 FROM public."Feature04_Calculation_Queue" WHERE public.is_universe_index(ticker)) THEN
        RAISE EXCEPTION 'An index row is still in a stock Feature table or queue';
    END IF;
    IF (SELECT count(*) FROM pg_trigger WHERE tgname = 'stock_feature_index_guard') <> 2 THEN
        RAISE EXCEPTION 'The guard is not on both stock tables';
    END IF;
    IF (SELECT count(*) FROM public."Feature_01_Stock_Daily_INDEX") = 0 THEN
        RAISE EXCEPTION 'Feature_01_Stock_Daily_INDEX is empty: the index rows would have no home';
    END IF;
END
$verify$;
COMMIT;
