-- Allow MIN and MAX on date columns of the seven Governor-approved market-data tables.
-- The live seed (20260922_001) gave non-numeric columns only COUNT/COUNT_DISTINCT, so the SQL
-- Governor rejected MIN/MAX(date), e.g. "first and last available date per ticker". Existing
-- aggregations are kept in order; MIN/MAX are appended only where missing. No other column,
-- flag, or table changes. Timestamp columns are intentionally not included.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

DO $preflight$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public."AI_column_catalog"
        WHERE data_type = 'date' AND table_name IN (
            'Feature_01_Stock_Daily', 'Feature_02_Broker_Rolling', 'Feature_03_Stock_Broker_Daily',
            'IDX_Broker_Profile', 'IDX_Broker_Summary', 'IDX_Stock_Universe', 'Price_Stock_Indonesia_IDX')
    ) THEN
        RAISE EXCEPTION 'No date columns found for the approved market-data tables';
    END IF;
END
$preflight$;

UPDATE public."AI_column_catalog"
SET allowed_aggregations = allowed_aggregations || ARRAY(
        SELECT aggregation FROM unnest(ARRAY['MIN', 'MAX']::text[]) AS aggregation
        WHERE NOT aggregation = ANY(allowed_aggregations)
    ),
    updated_at = CURRENT_TIMESTAMP
WHERE data_type = 'date'
  AND table_name IN (
      'Feature_01_Stock_Daily', 'Feature_02_Broker_Rolling', 'Feature_03_Stock_Broker_Daily',
      'IDX_Broker_Profile', 'IDX_Broker_Summary', 'IDX_Stock_Universe', 'Price_Stock_Indonesia_IDX')
  AND NOT allowed_aggregations @> ARRAY['MIN', 'MAX']::text[];

DO $verify$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public."AI_column_catalog"
        WHERE data_type = 'date' AND NOT allowed_aggregations @> ARRAY['MIN', 'MAX']::text[]
          AND table_name IN (
              'Feature_01_Stock_Daily', 'Feature_02_Broker_Rolling', 'Feature_03_Stock_Broker_Daily',
              'IDX_Broker_Profile', 'IDX_Broker_Summary', 'IDX_Stock_Universe', 'Price_Stock_Indonesia_IDX')
    ) THEN
        RAISE EXCEPTION 'A date column still lacks MIN/MAX';
    END IF;
END
$verify$;

COMMIT;
