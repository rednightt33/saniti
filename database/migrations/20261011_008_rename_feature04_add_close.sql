BEGIN;

SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '30min';

SELECT pg_advisory_xact_lock(hashtextextended('Feature04_Technical_Indicator',0));
SELECT pg_advisory_xact_lock(hashtextextended('Feature_04_Technical_Indicator',0));

DO $guard$
BEGIN
    IF to_regclass('public."Feature04_Technical_Indicator"') IS NULL THEN
        RAISE EXCEPTION 'Expected source table Feature04_Technical_Indicator is missing';
    END IF;
    IF to_regclass('public."Feature_04_Technical_Indicator"') IS NOT NULL THEN
        RAISE EXCEPTION 'Target table Feature_04_Technical_Indicator already exists';
    END IF;
    IF (SELECT count(*) FROM information_schema.columns
        WHERE table_schema='public' AND table_name='Feature04_Technical_Indicator') <> 56 THEN
        RAISE EXCEPTION 'Expected the 56-column cross-asset Feature04 source schema';
    END IF;
    IF EXISTS(SELECT 1 FROM public."Feature04_Calculation_Queue" WHERE status<>'DONE') THEN
        RAISE EXCEPTION 'Feature04 queue must be fully terminal before table rename';
    END IF;
    IF EXISTS(
        SELECT 1 FROM public."AI_table_catalog" WHERE table_name='Feature04_Technical_Indicator'
        UNION ALL SELECT 1 FROM public."AI_column_catalog" WHERE table_name='Feature04_Technical_Indicator'
        UNION ALL SELECT 1 FROM public."AI_calculation_catalog" WHERE target_table='Feature04_Technical_Indicator'
        UNION ALL SELECT 1 FROM public."AI_catalog_relationships"
          WHERE left_table='Feature04_Technical_Indicator' OR right_table='Feature04_Technical_Indicator'
    ) THEN
        RAISE EXCEPTION 'Feature04 has AI catalog references; migrate them explicitly before rename';
    END IF;
END
$guard$;

ALTER TABLE public."Feature04_Technical_Indicator"
    RENAME TO "Feature_04_Technical_Indicator";

ALTER TABLE public."Feature_04_Technical_Indicator"
    ADD COLUMN close double precision;

UPDATE public."Feature_04_Technical_Indicator" f
SET close=p.close::double precision
FROM public."Price_Stock_Indonesia_IDX" p
WHERE f.asset_type='equity' AND p.ticker=f.ticker AND p.date=f.trade_date
  AND p.timeframe='Daily';

UPDATE public."Feature_04_Technical_Indicator" f
SET close=p.close::double precision
FROM public."Price_Fixed_Income" p
WHERE f.asset_type='bonds' AND p.ticker=f.ticker AND p.date=f.trade_date
  AND p.metric_type='price' AND p."Timeframe"='1D';

DO $close_guard$
BEGIN
    IF EXISTS(SELECT 1 FROM public."Feature_04_Technical_Indicator" WHERE close IS NULL) THEN
        RAISE EXCEPTION 'Close backfill left unmatched Feature04 rows';
    END IF;
    IF EXISTS(
        SELECT 1 FROM public."Feature_04_Technical_Indicator" f
        JOIN public."Price_Stock_Indonesia_IDX" p
          ON f.asset_type='equity' AND p.ticker=f.ticker AND p.date=f.trade_date
         AND p.timeframe='Daily'
        WHERE f.close IS DISTINCT FROM p.close::double precision
    ) OR EXISTS(
        SELECT 1 FROM public."Feature_04_Technical_Indicator" f
        JOIN public."Price_Fixed_Income" p
          ON f.asset_type='bonds' AND p.ticker=f.ticker AND p.date=f.trade_date
         AND p.metric_type='price' AND p."Timeframe"='1D'
        WHERE f.close IS DISTINCT FROM p.close::double precision
    ) THEN
        RAISE EXCEPTION 'Close backfill differs from a classified source close';
    END IF;
END
$close_guard$;

ALTER TABLE public."Feature_04_Technical_Indicator"
    ALTER COLUMN close SET NOT NULL,
    ADD CONSTRAINT "Feature_04_Technical_Indicator_close_finite_check"
        CHECK (close > '-Infinity'::double precision AND close < 'Infinity'::double precision),
    ADD CONSTRAINT "Feature_04_Technical_Indicator_close_nonnegative_check"
        CHECK (close >= 0);

DO $rename_objects$
DECLARE item record; new_name text;
BEGIN
    FOR item IN
        SELECT conname FROM pg_constraint
        WHERE conrelid='public."Feature_04_Technical_Indicator"'::regclass
          AND conname LIKE 'Feature04_Technical_Indicator%'
    LOOP
        new_name := replace(item.conname,'Feature04_Technical_Indicator','Feature_04_Technical_Indicator');
        EXECUTE format('ALTER TABLE public."Feature_04_Technical_Indicator" RENAME CONSTRAINT %I TO %I',item.conname,new_name);
    END LOOP;
    FOR item IN
        SELECT indexname FROM pg_indexes
        WHERE schemaname='public' AND tablename='Feature_04_Technical_Indicator'
          AND indexname LIKE 'Feature04_Technical_Indicator%'
    LOOP
        new_name := replace(item.indexname,'Feature04_Technical_Indicator','Feature_04_Technical_Indicator');
        EXECUTE format('ALTER INDEX public.%I RENAME TO %I',item.indexname,new_name);
    END LOOP;
END
$rename_objects$;

COMMENT ON TABLE public."Feature_04_Technical_Indicator" IS
'57-column cross-asset Daily technical Feature04. Identity is asset_type/ticker/trade_date/timeframe; close is copied from the exact classified source row and the other measures are calculated per asset/ticker history.';
COMMENT ON COLUMN public."Feature_04_Technical_Indicator".close IS
'Daily closing price copied from the exact equity or bonds source row matched on ticker and trade_date.';

INSERT INTO public."Table_Catalog"(
 table_schema,table_name,category,definition,grain,primary_key_columns,source_system,
 source_tables,source_code_paths,update_rule,related_functions,documentation_status,
 created_at,updated_at,readiness_mode,readiness_date_column,observation_date_column,
 data_available_at_column,availability_rule,point_in_time_status,historical_metadata_method
)
SELECT table_schema,'Feature_04_Technical_Indicator',category,
 'Cross-asset Daily closing price and causal technical indicators from universe-classified equity or bonds OHLC.',
 grain,primary_key_columns,source_system,source_tables,
 ARRAY(SELECT DISTINCT x FROM unnest(source_code_paths||ARRAY['database/migrations/20261011_008_rename_feature04_add_close.sql']) x ORDER BY x),
 update_rule,
 ARRAY(SELECT DISTINCT x FROM unnest(related_functions||ARRAY['public.validate_feature_catalog_target()']) x ORDER BY x),
 documentation_status,created_at,CURRENT_TIMESTAMP,readiness_mode,readiness_date_column,
 observation_date_column,data_available_at_column,availability_rule,point_in_time_status,
 historical_metadata_method
FROM public."Table_Catalog"
WHERE table_schema='public' AND table_name='Feature04_Technical_Indicator';

UPDATE public."Column_Catalog"
SET table_name='Feature_04_Technical_Indicator',updated_at=CURRENT_TIMESTAMP
WHERE table_schema='public' AND table_name='Feature04_Technical_Indicator';

UPDATE public."Feature_Catalog"
SET feature_table='Feature_04_Technical_Indicator',
    source_tables=replace(source_tables,'Feature04_Technical_Indicator','Feature_04_Technical_Indicator'),
    updated_at=CURRENT_TIMESTAMP
WHERE feature_table='Feature04_Technical_Indicator';

UPDATE public."Feature_Relationship_Catalog"
SET left_feature_table=CASE WHEN left_feature_table='Feature04_Technical_Indicator'
                            THEN 'Feature_04_Technical_Indicator' ELSE left_feature_table END,
    right_feature_table=CASE WHEN right_feature_table='Feature04_Technical_Indicator'
                             THEN 'Feature_04_Technical_Indicator' ELSE right_feature_table END,
    safe_output_grain=CASE WHEN left_feature_table='Feature04_Technical_Indicator'
                           THEN 'equity ticker x trade_date x Daily timeframe' ELSE safe_output_grain END,
    definition=CASE WHEN left_feature_table='Feature04_Technical_Indicator'
                    THEN 'Exact observed-date join on ticker and trade_date=date after filtering Feature04 to asset_type=equity and timeframe=Daily; retain unmatched rows.'
                    ELSE definition END,
    updated_at=CURRENT_TIMESTAMP
WHERE left_feature_table='Feature04_Technical_Indicator'
   OR right_feature_table='Feature04_Technical_Indicator';

UPDATE public."Table_Catalog"
SET source_tables=array_replace(source_tables,'Feature04_Technical_Indicator','Feature_04_Technical_Indicator'),
    updated_at=CURRENT_TIMESTAMP
WHERE 'Feature04_Technical_Indicator'=ANY(source_tables);

INSERT INTO public."Database_Table_Status"(
 "Table Name","Last Checked At","Table Category","Update Pattern","Latest Data Date",
 "Last Changed At","Tracking Status","Last Operation"
)
VALUES(
 'Feature_04_Technical_Indicator',CURRENT_TIMESTAMP,'Feature',
 'Event-driven after committed classified equity or bonds price changes',
 (SELECT max(trade_date) FROM public."Feature_04_Technical_Indicator"),CURRENT_TIMESTAMP,
 'Renamed table and source-exact close backfill verified','ALTER/UPDATE'
)
ON CONFLICT("Table Name") DO UPDATE SET
 "Last Checked At"=EXCLUDED."Last Checked At","Table Category"=EXCLUDED."Table Category",
 "Update Pattern"=EXCLUDED."Update Pattern","Latest Data Date"=EXCLUDED."Latest Data Date",
 "Last Changed At"=EXCLUDED."Last Changed At","Tracking Status"=EXCLUDED."Tracking Status",
 "Last Operation"=EXCLUDED."Last Operation";

DELETE FROM public."Database_Table_Status" WHERE "Table Name"='Feature04_Technical_Indicator';
DELETE FROM public."Table_Catalog"
WHERE table_schema='public' AND table_name='Feature04_Technical_Indicator';

INSERT INTO public."Column_Catalog"(
 table_schema,table_name,column_name,ordinal_position,data_type,is_nullable,default_expression,
 is_primary_key,definition,source_column_or_expression,unit,null_rule,source_code_paths,documentation_status
)
SELECT 'public','Feature_04_Technical_Indicator','close',c.ordinal_position,c.data_type,false,
       c.column_default,false,
       'Daily closing price copied from the exact classified source row on ticker and trade_date.',
       'Price_Stock_Indonesia_IDX.close for equity; Price_Fixed_Income.close where metric_type=price and Timeframe=1D for bonds',
       'source price unit','Never NULL for a stored Feature04 row.',
       ARRAY['features/feature04/engine.py','apps/feature-04-worker/worker.py','FEATURE04_COLUMN_DEFINITIONS.md','verification/feature04/RENAME_CLOSE.md'],
       'VERIFIED'
FROM information_schema.columns c
WHERE c.table_schema='public' AND c.table_name='Feature_04_Technical_Indicator' AND c.column_name='close';

INSERT INTO public."Feature_Catalog"(
 feature_table,feature_column,grain,feature_category,definition,calculation,source_tables,
 source_columns,lookback_window,minimum_history,unit,null_rule,refresh_trigger,dependency_rule,
 version,is_active,semantic_role,allowed_aggregations,ranking_interpretation,is_filterable,
 is_groupable,availability_rule,point_in_time_safe,historical_metadata_warning,
 analytical_interpretation,recommended_use,misuse_warning,semantic_review_status,validation_evidence
)
VALUES(
 'Feature_04_Technical_Indicator','close','asset_type x ticker x trade_date x Daily timeframe','Price',
 'Daily closing price copied from the matching universe-classified price source row.',
 'Equity: Price_Stock_Indonesia_IDX.close; bonds: Price_Fixed_Income.close where metric_type=price and Timeframe=1D; exact ticker and trade_date match.',
 'Price_Stock_Indonesia_IDX + IDX_Stock_Universe; Price_Fixed_Income(metric_type=price) + Universe_Fixed_income',
 'asset_type, ticker, date, close, timeframe/Timeframe, metric_type','1 source row','1 source row',
 'source price unit','Never NULL for a stored Feature04 row.',
 'Committed classified equity or bonds price change through the Feature04 queue',
 'Ticker must resolve to exactly one approved universe and an exact source ticker/date row must exist.',
 'v4',true,'MEASURE',ARRAY['MIN','MAX','AVG','MEDIAN']::text[],'CONTEXTUAL',true,false,
 'Close-t observation; actual decision availability still follows the source ingestion contract.',false,
 'Source revision history and historical universe membership are incomplete.',
 'Observed Daily closing level on this row trade_date in its source price unit.',
 'Use as the contemporaneous price level and as the source value behind close-based indicators.',
 'Do not compare raw levels across instruments or asset classes, treat close as a return, or infer historical availability from trade_date alone.',
 'CALCULATION_VERIFIED',ARRAY['features/feature04/tests/test_engine.py','verification/feature04/RENAME_CLOSE.md']::text[]
);

CREATE OR REPLACE FUNCTION public.feature04_output_columns()
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
 'last_swing_high','break_swing_high','close']::text[]
$function$;

INSERT INTO public."Feature04_Column_Status"(
 asset_type,ticker,timeframe,feature_column,requested_generation,completed_generation,
 calculation_version,status,dirty_from_date,validated_through,latest_value_available,
 null_reason,last_attempt_id,last_error_code,last_error,last_calculated_at,updated_at
)
SELECT q.asset_type,q.ticker,q.timeframe,'close',q.requested_generation,q.requested_generation,
       'feature04-v3-smi14-5-5-th40-talib0.6.8-c0.6.4','SUCCESS',NULL,
       max(f.trade_date),true,NULL,NULL,NULL,NULL,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP
FROM public."Feature04_Calculation_Queue" q
JOIN public."Feature_04_Technical_Indicator" f
  ON f.asset_type=q.asset_type AND f.ticker=q.ticker AND f.timeframe=q.timeframe
GROUP BY q.asset_type,q.ticker,q.timeframe,q.requested_generation
ON CONFLICT(asset_type,ticker,timeframe,feature_column) DO UPDATE SET
 requested_generation=EXCLUDED.requested_generation,
 completed_generation=EXCLUDED.completed_generation,
 calculation_version=EXCLUDED.calculation_version,status='SUCCESS',dirty_from_date=NULL,
 validated_through=EXCLUDED.validated_through,latest_value_available=true,null_reason=NULL,
 last_error_code=NULL,last_error=NULL,last_calculated_at=EXCLUDED.last_calculated_at,
 updated_at=CURRENT_TIMESTAMP;

CREATE OR REPLACE FUNCTION public.validate_feature_catalog_target()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    IF NEW.is_active THEN
        IF NEW.feature_table !~ '^Feature_[0-9]{2}_[A-Za-z0-9_]+$' THEN
            RAISE EXCEPTION 'Active Feature table name % is not governed', NEW.feature_table;
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='public' AND table_name=NEW.feature_table
              AND column_name=NEW.feature_column
        ) THEN
            RAISE EXCEPTION 'Active catalog target %.% does not exist',
                NEW.feature_table,NEW.feature_column;
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM public."Table_Catalog"
            WHERE table_schema='public' AND table_name=NEW.feature_table
              AND category='Feature' AND documentation_status='VERIFIED'
        ) THEN
            RAISE EXCEPTION 'Active Feature table % is not VERIFIED in Table_Catalog',NEW.feature_table;
        END IF;
    END IF;
    RETURN NEW;
END
$function$;

DO $verify$
BEGIN
    IF to_regclass('public."Feature04_Technical_Indicator"') IS NOT NULL
       OR to_regclass('public."Feature_04_Technical_Indicator"') IS NULL THEN
        RAISE EXCEPTION 'Physical Feature04 rename verification failed';
    END IF;
    IF (SELECT count(*) FROM information_schema.columns
        WHERE table_schema='public' AND table_name='Feature_04_Technical_Indicator') <> 57 THEN
        RAISE EXCEPTION 'Feature04 must contain exactly 57 physical columns';
    END IF;
    IF EXISTS(SELECT 1 FROM public."Feature_04_Technical_Indicator"
              WHERE close IS NULL OR close='Infinity'::double precision
                 OR close='-Infinity'::double precision OR close<0) THEN
        RAISE EXCEPTION 'Feature04 close constraint verification failed';
    END IF;
    IF (SELECT count(*) FROM public."Column_Catalog"
        WHERE table_schema='public' AND table_name='Feature_04_Technical_Indicator') <> 57 THEN
        RAISE EXCEPTION 'Feature04 Column_Catalog coverage must be 57/57';
    END IF;
    IF (SELECT count(*) FROM public."Feature_Catalog"
        WHERE feature_table='Feature_04_Technical_Indicator' AND is_active) <> 57 THEN
        RAISE EXCEPTION 'Feature04 active Feature_Catalog coverage must be 57/57';
    END IF;
    IF cardinality(public.feature04_output_columns()) <> 51 THEN
        RAISE EXCEPTION 'Feature04 selectable output list must contain 51 columns';
    END IF;
    IF (SELECT count(*) FROM public."Feature04_Column_Status" WHERE feature_column='close')
       <> (SELECT count(*) FROM public."Feature04_Calculation_Queue") THEN
        RAISE EXCEPTION 'Close readiness was not bootstrapped for every queued instrument';
    END IF;
    IF EXISTS(SELECT 1 FROM public."Column_Catalog" WHERE table_name='Feature04_Technical_Indicator')
       OR EXISTS(SELECT 1 FROM public."Feature_Catalog" WHERE feature_table='Feature04_Technical_Indicator')
       OR EXISTS(SELECT 1 FROM public."Feature_Relationship_Catalog"
                 WHERE left_feature_table='Feature04_Technical_Indicator'
                    OR right_feature_table='Feature04_Technical_Indicator')
       OR EXISTS(SELECT 1 FROM public."Table_Catalog"
                 WHERE 'Feature04_Technical_Indicator'=ANY(source_tables)) THEN
        RAISE EXCEPTION 'Stale active catalog reference to the old table name remains';
    END IF;
    IF EXISTS(SELECT 1 FROM pg_constraint
              WHERE conrelid='public."Feature_04_Technical_Indicator"'::regclass
                AND conname LIKE 'Feature04_Technical_Indicator%')
       OR EXISTS(SELECT 1 FROM pg_indexes
                 WHERE schemaname='public' AND tablename='Feature_04_Technical_Indicator'
                   AND indexname LIKE 'Feature04_Technical_Indicator%') THEN
        RAISE EXCEPTION 'Stale physical constraint/index name remains';
    END IF;
END
$verify$;

COMMIT;
