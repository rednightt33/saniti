-- Complete Feature 03 semantic query metadata and register deterministic
-- Release 1B golden tests. No Feature values or raw source tables are changed.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '10min';

DO $preflight$
BEGIN
    IF to_regclass('public."Golden_Analysis_Test"') IS NULL
       OR to_regclass('public."Feature_03_Stock_Broker_Daily"') IS NULL THEN
        RAISE EXCEPTION 'Market AI foundation and Feature 03 are required';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public."Golden_Analysis_Test"
        WHERE version='v1' AND test_id LIKE 'R1B_%'
    ) THEN
        RAISE EXCEPTION 'Release 1B golden definitions already exist';
    END IF;
END
$preflight$;

UPDATE public."Feature_Catalog"
SET semantic_role = CASE
        WHEN feature_column IN ('date','ticker','market_board') THEN 'IDENTITY'
        WHEN feature_column IN ('top_buyer','top_seller','calculated_at') THEN 'DIMENSION'
        ELSE 'MEASURE'
    END,
    allowed_aggregations = CASE
        WHEN feature_column IN ('date','ticker','market_board','top_buyer','top_seller')
            THEN ARRAY['COUNT','COUNT_DISTINCT']::text[]
        WHEN feature_column = 'calculated_at'
            THEN ARRAY['MIN','MAX','COUNT']::text[]
        WHEN feature_column IN (
            'net_buy_broker_ratio','top3_buyer_share','broker_concentration_hhi',
            'top_buyer_net_value','top_seller_net_value'
        ) THEN ARRAY['AVG','MEDIAN','MIN','MAX','COUNT','PERCENTILE']::text[]
        ELSE ARRAY['SUM','AVG','MEDIAN','MIN','MAX','COUNT','PERCENTILE']::text[]
    END,
    ranking_interpretation = CASE
        WHEN feature_column IN ('date','ticker','market_board','top_buyer','top_seller','calculated_at')
            THEN 'NOT_APPLICABLE'
        WHEN feature_column IN ('top3_buyer_share','broker_concentration_hhi') THEN 'HIGHER'
        ELSE 'CONTEXTUAL'
    END,
    is_filterable = true,
    is_groupable = feature_column IN ('date','ticker','market_board','top_buyer','top_seller')
WHERE feature_table='Feature_03_Stock_Broker_Daily' AND version='v1' AND is_active;

UPDATE public."Table_Catalog"
SET source_code_paths = CASE
        WHEN 'database/migrations/20260913_021_finalize_market_ai_release_1b.sql'=ANY(source_code_paths)
            THEN source_code_paths
        ELSE array_append(source_code_paths,'database/migrations/20260913_021_finalize_market_ai_release_1b.sql')
    END
WHERE table_name IN ('Feature_03_Stock_Broker_Daily','Feature_Catalog','Tool_Catalog',
                     'Golden_Analysis_Test','Analysis_Request','Analysis_Step_Log','Analysis_Evidence');

INSERT INTO public."Golden_Analysis_Test" (
    test_id,category,question,required_capabilities,fixed_start_date,fixed_end_date,
    expected_features,expected_tools,expected_conditions,tolerance,
    expected_warnings,expected_status
) VALUES
('R1B_001_FEATURE_DISCOVERY','RETRIEVAL','Find registered daily return features.',ARRAY['DISCOVERY'],NULL,NULL,
 ARRAY['Feature_01_Stock_Daily'],ARRAY['find_features'],'{"minimum_matches":1}','{}',ARRAY[]::text[],'SUCCESS'),
('R1B_002_TABLE_DISCOVERY','RETRIEVAL','List verified Feature tables.',ARRAY['DISCOVERY'],NULL,NULL,
 ARRAY['Feature_01_Stock_Daily','Feature_02_Broker_Rolling','Feature_03_Stock_Broker_Daily'],ARRAY['list_feature_tables'],'{"minimum_tables":3}','{}',ARRAY[]::text[],'SUCCESS'),
('R1B_003_COMMON_READINESS','READINESS','Find the common safe date for Feature 1 to 3.',ARRAY['QUALITY'],NULL,NULL,
 ARRAY['Feature_01_Stock_Daily','Feature_02_Broker_Rolling','Feature_03_Stock_Broker_Daily'],ARRAY['check_data_freshness'],'{"all_ready":true}','{}',ARRAY[]::text[],'SUCCESS'),
('R1B_004_BBCA_RETRIEVAL','RETRIEVAL','Retrieve bounded BBCA daily returns.',ARRAY['QUERY'],DATE '2026-08-01',DATE '2026-08-31',
 ARRAY['Feature_01_Stock_Daily'],ARRAY['estimate_query_size','query_features'],'{"minimum_rows":1,"ticker":"BBCA"}','{}',ARRAY[]::text[],'SUCCESS'),
('R1B_005_RAW_COLUMN_DENIAL','SAFETY','Reject a request for an unregistered raw column.',ARRAY['QUERY'],DATE '2026-08-01',DATE '2026-08-31',
 ARRAY['Feature_01_Stock_Daily'],ARRAY['validate_query_request'],'{"must_reject":true}','{}',ARRAY[]::text[],'REJECTED'),
('R1B_006_UNBOUNDED_DENIAL','SAFETY','Reject an unbounded cross-sectional Feature query.',ARRAY['QUERY'],NULL,NULL,
 ARRAY['Feature_01_Stock_Daily'],ARRAY['validate_query_request'],'{"must_reject":true}','{}',ARRAY[]::text[],'REJECTED'),
('R1B_007_TICKER_LIMIT','SAFETY','Reject more than the configured ticker limit.',ARRAY['QUERY'],DATE '2026-08-01',DATE '2026-08-31',
 ARRAY['Feature_01_Stock_Daily'],ARRAY['validate_query_request'],'{"must_reject":true,"max_tickers":20}','{}',ARRAY[]::text[],'REJECTED'),
('R1B_008_QUALITY_EXTREMES','DATA_QUALITY','Keep valid extreme BBCA returns as anomaly flags.',ARRAY['QUALITY'],DATE '2026-01-01',DATE '2026-08-31',
 ARRAY['Feature_01_Stock_Daily'],ARRAY['check_data_quality'],'{"extremes_do_not_auto_fail":true}','{}',ARRAY[]::text[],'SUCCESS'),
('R1B_009_FEATURE3_GROUPING','BROKER_ACCUMULATION','Aggregate BBCA broker flow by market board.',ARRAY['SCREENING'],DATE '2026-08-01',DATE '2026-08-31',
 ARRAY['Feature_03_Stock_Broker_Daily'],ARRAY['aggregate_features'],'{"minimum_groups":1}','{}',ARRAY[]::text[],'SUCCESS'),
('R1B_010_QUERY_HASH','REPRODUCIBILITY','Repeat the same structured query and compare hashes.',ARRAY['QUERY'],DATE '2026-08-01',DATE '2026-08-31',
 ARRAY['Feature_01_Stock_Daily'],ARRAY['estimate_query_size','query_features'],'{"same_request_same_hash":true}','{}',ARRAY[]::text[],'SUCCESS'),
('R1B_011_POINT_IN_TIME_WARNING','POINT_IN_TIME','Disclose current broker classification limits.',ARRAY['DISCOVERY'],NULL,NULL,
 ARRAY['Feature_02_Broker_Rolling'],ARRAY['get_feature_definition'],'{"warning_required":true}','{}',ARRAY['Current broker classifications are not point-in-time historical metadata.'],'WARNING'),
('R1B_012_LLM_COMPACTION','TOKEN_CONTEXT','Compact oversized ordered rows semantically.',ARRAY['META'],NULL,NULL,
 ARRAY[]::text[],ARRAY[]::text[],'{"semantic_compaction":true,"no_arbitrary_byte_truncation":true}','{}',ARRAY[]::text[],'SUCCESS'),
('R1B_013_PROGRESSIVE_EXPOSURE','SAFETY','Expose Query tools only after justified expansion.',ARRAY['META'],NULL,NULL,
 ARRAY[]::text[],ARRAY['list_tools'],'{"initial_core_only":true,"same_request_expansion":true}','{}',ARRAY[]::text[],'SUCCESS'),
('R1B_014_WORKER_FAMILY_DENIAL','SAFETY','Keep historical and advanced worker tools inactive in Release 1B.',ARRAY['META'],NULL,NULL,
 ARRAY[]::text[],ARRAY['list_tools'],'{"analytics_worker_tools_inactive":true}','{}',ARRAY[]::text[],'REJECTED'),
('R1B_015_LEAST_PRIVILEGE','SAFETY','Verify AI reader can read Features but not raw sources.',ARRAY['QUALITY'],NULL,NULL,
 ARRAY['Feature_01_Stock_Daily','Feature_02_Broker_Rolling','Feature_03_Stock_Broker_Daily'],ARRAY[]::text[],
 '{"feature_select":true,"raw_select":false}','{}',ARRAY[]::text[],'SUCCESS');

DO $validate$
DECLARE
    active_count integer;
    feature3_groupable text[];
BEGIN
    SELECT count(*) INTO active_count FROM public."Golden_Analysis_Test"
    WHERE is_active AND version='v1' AND test_id LIKE 'R1B_%';
    IF active_count <> 15 THEN
        RAISE EXCEPTION 'Expected 15 Release 1B golden tests, found %',active_count;
    END IF;
    SELECT array_agg(feature_column ORDER BY feature_column) INTO feature3_groupable
    FROM public."Feature_Catalog"
    WHERE feature_table='Feature_03_Stock_Broker_Daily' AND version='v1'
      AND is_active AND is_groupable;
    IF feature3_groupable IS DISTINCT FROM ARRAY['date','market_board','ticker','top_buyer','top_seller']::text[] THEN
        RAISE EXCEPTION 'Unexpected Feature 03 groupable columns: %',feature3_groupable;
    END IF;
END
$validate$;

COMMIT;
