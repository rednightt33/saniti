-- Coverage metadata only: formulas, columns, grants, routines and relationships unchanged.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='60s';
SELECT pg_advisory_xact_lock(hashtextextended('Feature04_Technical_Indicator',0));

DO $guard$ BEGIN
 IF (SELECT count(*) FROM information_schema.columns
     WHERE table_schema='public' AND table_name='Feature04_Technical_Indicator')<>55
 OR (SELECT count(*) FROM public."Feature_Catalog"
     WHERE feature_table='Feature04_Technical_Indicator' AND is_active AND version='v3')<>55
 OR EXISTS(SELECT 1 FROM public."Feature04_Technical_Indicator"
     WHERE calculation_version<>'feature04-v3-smi14-5-5-th40-talib0.6.8-c0.6.4') THEN
  RAISE EXCEPTION 'Expected completed v3 source-universe backfill; stop for inspection';
 END IF;
 IF NOT EXISTS(SELECT 1 FROM public."Table_Catalog"
     WHERE table_schema='public' AND table_name='Feature04_Technical_Indicator'
       AND definition LIKE '%Initial SMI extension calculated for BBCA only%') THEN
  RAISE EXCEPTION 'Expected inspected initial coverage metadata; stop for inspection';
 END IF;
END $guard$;

COMMENT ON TABLE public."Feature04_Technical_Indicator" IS
 '55-column daily technical Feature04: unchanged TA-Lib indicators plus Pine SMI14/5/5 +/-40 and post-bar swing state. Authorized full-history replay completed for every actual price-source ticker. Closed-bar trigger INTEGER 1/0; no backdating, scheduler or TradingView-export parity claim.';

UPDATE public."Table_Catalog"
SET definition='55-column causal daily indicators, native candlestick codes, strict inside bar and Pine SMI/swing state. Authorized v3 full-history replay completed for all actual price-source tickers. TradingView chart parity NOT VERIFIED.',
    update_rule='Manual scoped or explicitly authorized all-source serial chronological replay; source corrections require full history through output end. No scheduler.',
    source_code_paths=array_append(source_code_paths,'verification/feature04/SMI_ALL_TICKERS.md'),
    updated_at=clock_timestamp()
WHERE table_schema='public' AND table_name='Feature04_Technical_Indicator';

UPDATE public."Column_Catalog"
SET source_code_paths=array_append(source_code_paths,'verification/feature04/SMI_ALL_TICKERS.md'),
    updated_at=clock_timestamp()
WHERE table_schema='public' AND table_name='Feature04_Technical_Indicator'
  AND column_name IN ('smi','tracking_high','tracking_low','temp_high','temp_high_bar',
                      'temp_low','temp_low_bar','last_swing_high','break_swing_high');

UPDATE public."Feature_Catalog"
SET validation_evidence=array_append(validation_evidence,'verification/feature04/SMI_ALL_TICKERS.md'),
    updated_at=clock_timestamp()
WHERE feature_table='Feature04_Technical_Indicator' AND is_active AND version='v3';

UPDATE public."Feature_Catalog"
SET availability_rule='Available after current Daily close, with confirmation-date state only; v3 replay completed for all actual price-source tickers. A later uncomputed or invalid row stays NULL. Prediction timestamp/horizon and training point-in-time eligibility NOT VERIFIED.',
    updated_at=clock_timestamp()
WHERE feature_table='Feature04_Technical_Indicator' AND is_active AND version='v3'
  AND feature_column IN ('smi','tracking_high','tracking_low','temp_high','temp_high_bar',
                         'temp_low','temp_low_bar','last_swing_high','break_swing_high');

COMMIT;
