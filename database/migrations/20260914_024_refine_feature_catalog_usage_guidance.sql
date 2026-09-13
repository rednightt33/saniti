-- Correct overly generic recommended-use text found by post-migration review.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '5min';

UPDATE public."Feature_Catalog"
SET recommended_use = CASE
        WHEN feature_column = 'close' THEN
            'Use close as the observed nominal closing-price level for the ticker/date, as an input to validated return or drawdown comparisons, and for exact source-to-Feature reconciliation. Compare cross-ticker nominal prices only when that scale difference is analytically intended.'
        ELSE format(
            'Use %s as the documented prior trading-observation price reference to verify or explain the corresponding trailing return, volatility or drawdown calculation; do not rank different tickers by nominal price alone.',
            feature_column)
    END
WHERE is_active AND feature_table='Feature_01_Stock_Daily'
  AND feature_category='Price';

UPDATE public."Feature_Catalog"
SET recommended_use =
        'Use calculated_at only to audit when the Feature row was materialized or refreshed and to investigate pipeline freshness. It is not the observation date, source ingestion time, or historical decision-time availability timestamp.',
    misuse_warning = concat_ws(' ',
        CASE WHEN feature_table IN ('Feature_02_Broker_Rolling','Feature_03_Stock_Broker_Daily')
             THEN 'Do not combine Regular, Nego and Tunai implicitly; board must remain explicit or be deliberately aggregated.' END,
        'Do not use calculated_at for event timing, point-in-time joins, signal entry timing, or market chronology. Backfills can assign a recent materialization timestamp to old observations.',
        format('Respect the NULL contract: %s', null_rule)
    )
WHERE is_active AND feature_column='calculated_at';

UPDATE public."Feature_Catalog"
SET recommended_use = CASE feature_column
        WHEN 'top_buyer' THEN
            'Use top_buyer to identify the broker with the greatest positive daily net value for the exact ticker and board, then investigate repetition or concentration with separate historical observations.'
        WHEN 'top_seller' THEN
            'Use top_seller to identify the broker with the most negative daily net value for the exact ticker and board, then investigate repetition or concentration with separate historical observations.'
    END
WHERE is_active AND feature_table='Feature_03_Stock_Broker_Daily'
  AND feature_column IN ('top_buyer','top_seller');

UPDATE public."Table_Catalog"
SET source_code_paths = CASE
        WHEN 'database/migrations/20260914_024_refine_feature_catalog_usage_guidance.sql'=ANY(source_code_paths)
            THEN source_code_paths
        ELSE array_append(source_code_paths,
            'database/migrations/20260914_024_refine_feature_catalog_usage_guidance.sql')
    END
WHERE table_schema='public' AND table_name='Feature_Catalog';

DO $validate$
DECLARE bad_count integer;
BEGIN
    SELECT count(*) INTO bad_count
    FROM public."Feature_Catalog"
    WHERE is_active AND (
        (feature_category='Price' AND recommended_use ILIKE '%only for the operational%')
        OR (feature_column='calculated_at' AND recommended_use ILIKE '%peer group%')
        OR (feature_table='Feature_03_Stock_Broker_Daily'
            AND feature_column IN ('top_buyer','top_seller')
            AND recommended_use NOT ILIKE '%exact ticker and board%')
    );
    IF bad_count <> 0 THEN
        RAISE EXCEPTION 'Feature recommended-use refinement failed for % rows', bad_count;
    END IF;
END
$validate$;

COMMIT;
