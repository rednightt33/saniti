BEGIN;

SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '5min';

DO $guard$
BEGIN
    IF to_regclass('public."Feature_04_Technical_Indicator"') IS NULL THEN
        RAISE EXCEPTION 'Feature_04_Technical_Indicator is missing';
    END IF;
    IF EXISTS(SELECT 1 FROM public."Feature_04_Technical_Indicator" WHERE close IS NULL) THEN
        RAISE EXCEPTION 'Feature04 close must be complete before status bootstrap';
    END IF;
END
$guard$;

WITH instrument_status AS (
    SELECT asset_type,ticker,timeframe,
           max(requested_generation) AS requested_generation,
           max(completed_generation) AS completed_generation,
           max(calculation_version) AS calculation_version
    FROM public."Feature04_Column_Status"
    GROUP BY asset_type,ticker,timeframe
), target AS (
    SELECT f.asset_type,f.ticker,f.timeframe,max(f.trade_date) AS validated_through,
           max(f.calculated_at) AS existing_calculated_at
    FROM public."Feature_04_Technical_Indicator" f
    GROUP BY f.asset_type,f.ticker,f.timeframe
)
INSERT INTO public."Feature04_Column_Status"(
 asset_type,ticker,timeframe,feature_column,requested_generation,completed_generation,
 calculation_version,status,dirty_from_date,validated_through,latest_value_available,
 null_reason,last_attempt_id,last_error_code,last_error,last_calculated_at,updated_at
)
SELECT t.asset_type,t.ticker,t.timeframe,'close',s.requested_generation,
       s.requested_generation,s.calculation_version,'SUCCESS',NULL,t.validated_through,
       true,NULL,NULL,NULL,NULL,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP
FROM target t
JOIN instrument_status s USING(asset_type,ticker,timeframe)
ON CONFLICT(asset_type,ticker,timeframe,feature_column) DO UPDATE SET
 requested_generation=EXCLUDED.requested_generation,
 completed_generation=EXCLUDED.completed_generation,
 calculation_version=EXCLUDED.calculation_version,status='SUCCESS',dirty_from_date=NULL,
 validated_through=EXCLUDED.validated_through,latest_value_available=true,null_reason=NULL,
 last_error_code=NULL,last_error=NULL,last_calculated_at=EXCLUDED.last_calculated_at,
 updated_at=CURRENT_TIMESTAMP;

DO $verify$
DECLARE target_instruments bigint; close_statuses bigint;
BEGIN
    SELECT count(*) INTO target_instruments FROM (
        SELECT DISTINCT asset_type,ticker,timeframe
        FROM public."Feature_04_Technical_Indicator"
    ) instruments;
    SELECT count(*) INTO close_statuses
    FROM public."Feature04_Column_Status" WHERE feature_column='close';
    IF close_statuses<>target_instruments THEN
        RAISE EXCEPTION 'Close status coverage mismatch: % status rows for % instruments',
            close_statuses,target_instruments;
    END IF;
    IF EXISTS(
        SELECT 1 FROM public."Feature04_Column_Status" s
        WHERE s.feature_column='close'
          AND (s.status<>'SUCCESS' OR s.completed_generation<>s.requested_generation
               OR s.validated_through IS NULL OR s.latest_value_available IS DISTINCT FROM true)
    ) THEN
        RAISE EXCEPTION 'At least one close status is not a complete successful baseline';
    END IF;
END
$verify$;

COMMIT;
