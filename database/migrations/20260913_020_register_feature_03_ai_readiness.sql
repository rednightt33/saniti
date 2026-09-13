-- Register the concurrently completed Feature 03 with the generic AI readiness,
-- point-in-time and least-privilege contracts. No Feature calculation changes.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '10min';

DO $preflight$
BEGIN
    IF to_regclass('public."Feature_03_Stock_Broker_Daily"') IS NULL THEN
        RAISE EXCEPTION 'Feature 03 table is missing';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public."Table_Catalog"
        WHERE table_schema='public' AND table_name='Feature_03_Stock_Broker_Daily'
          AND category='Feature' AND documentation_status='VERIFIED'
    ) THEN
        RAISE EXCEPTION 'Feature 03 is not VERIFIED in Table_Catalog';
    END IF;
    IF (SELECT count(*) FROM public."Feature_Catalog"
        WHERE feature_table='Feature_03_Stock_Broker_Daily'
          AND version='v1' AND is_active) <> 24 THEN
        RAISE EXCEPTION 'Feature 03 requires exactly 24 active v1 definitions';
    END IF;
END
$preflight$;

UPDATE public."Table_Catalog"
SET readiness_mode='DATA_DATE',
    readiness_date_column='date',
    observation_date_column='date',
    data_available_at_column=NULL,
    availability_rule='Signal uses complete Feature 02-derived broker activity through close t; earliest permitted simulated entry is the next valid trading observation t+1.',
    point_in_time_status='PARTIAL',
    historical_metadata_method='Source symbols are retained, but broker-type and broker-classification aggregates use current IDX_Broker_Profile rather than point-in-time classifications.',
    related_functions=CASE
      WHEN 'check_analysis_data_readiness(text[])'=ANY(related_functions)
        THEN related_functions
      ELSE array_append(related_functions,'check_analysis_data_readiness(text[])')
    END,
    source_code_paths=CASE
      WHEN 'database/migrations/20260913_020_register_feature_03_ai_readiness.sql'=ANY(source_code_paths)
        THEN source_code_paths
      ELSE array_append(source_code_paths,'database/migrations/20260913_020_register_feature_03_ai_readiness.sql')
    END
WHERE table_schema='public' AND table_name='Feature_03_Stock_Broker_Daily';

UPDATE public."Feature_Catalog"
SET availability_rule='Complete daily broker aggregation is treated as available after close t; earliest simulated entry is next valid trading observation t+1.',
    point_in_time_safe=feature_column NOT IN (
      'foreign_net_value','domestic_net_value','institutional_net_value',
      'retail_net_value','mixed_net_value','niche_net_value','calculated_at'
    ),
    historical_metadata_warning=CASE
      WHEN feature_column IN (
        'foreign_net_value','domestic_net_value','institutional_net_value',
        'retail_net_value','mixed_net_value','niche_net_value'
      ) THEN 'Aggregate uses current broker reference classification, not point-in-time historical classification.'
      WHEN feature_column='calculated_at'
        THEN 'Materialization timestamp is not historical data availability time.'
      ELSE NULL
    END
WHERE feature_table='Feature_03_Stock_Broker_Daily' AND version='v1' AND is_active;

GRANT SELECT ON public."Feature_03_Stock_Broker_Daily" TO market_ai_reader;

DO $validate$
DECLARE
    readiness_status text;
    ready_date date;
BEGIN
    SELECT r.status,r.safe_analysis_date INTO readiness_status,ready_date
    FROM public.check_analysis_data_readiness(ARRAY['Feature_03_Stock_Broker_Daily']) r;
    IF readiness_status <> 'READY' OR ready_date <> DATE '2026-08-31' THEN
        RAISE EXCEPTION 'Feature 03 readiness failed: status %, date %',
          readiness_status,ready_date;
    END IF;
    IF NOT has_table_privilege('market_ai_reader',
        'public."Feature_03_Stock_Broker_Daily"','SELECT') THEN
        RAISE EXCEPTION 'market_ai_reader Feature 03 grant is missing';
    END IF;
    IF has_table_privilege('market_ai_reader',
        'public."IDX_Broker_Summary"','SELECT') THEN
        RAISE EXCEPTION 'market_ai_reader unexpectedly gained raw broker access';
    END IF;
END
$validate$;

COMMIT;
