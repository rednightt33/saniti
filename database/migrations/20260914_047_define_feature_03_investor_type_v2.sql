-- Feature 03 v2: investor flows use the point-in-time source Investor Type.
-- Broker breadth, ranks, concentration, and broker-profile classifications keep
-- their broker-level grain by aggregating both Investor Types per broker first.
BEGIN;
SET LOCAL lock_timeout='10s';
SET LOCAL statement_timeout='5min';

DO $preflight$
BEGIN
    IF to_regclass('public."Feature_02_Broker_Rolling"') IS NULL
       OR to_regclass('public."Feature_03_Stock_Broker_Daily"') IS NULL
       OR NOT EXISTS (
          SELECT 1 FROM information_schema.columns
          WHERE table_schema='public' AND table_name='Feature_02_Broker_Rolling'
            AND column_name='investor_type'
       ) THEN
        RAISE EXCEPTION 'Feature 03 v2 requires canonical Investor-Type Feature 02';
    END IF;
    IF (SELECT count(*) FROM public."Feature_Catalog"
        WHERE feature_table='Feature_03_Stock_Broker_Daily' AND version='v1' AND is_active) <> 24 THEN
        RAISE EXCEPTION 'Expected 24 active Feature 03 v1 definitions before v2';
    END IF;
    IF EXISTS (SELECT 1 FROM public."Feature_Catalog"
               WHERE feature_table='Feature_03_Stock_Broker_Daily' AND version='v2') THEN
        RAISE EXCEPTION 'Feature 03 v2 catalog already exists';
    END IF;
END
$preflight$;

CREATE OR REPLACE FUNCTION public.refresh_feature_03_stock_broker_daily(
    p_changed_date date DEFAULT NULL,
    p_tickers text[] DEFAULT NULL
)
RETURNS bigint
LANGUAGE plpgsql
AS $function$
DECLARE
    v_rows bigint;
BEGIN
    IF p_tickers IS NOT NULL AND cardinality(p_tickers) = 0 THEN
        RETURN 0;
    END IF;

    PERFORM pg_advisory_xact_lock(hashtextextended('refresh_feature_03_stock_broker_daily', 0));

    DELETE FROM public."Feature_03_Stock_Broker_Daily" AS target
    WHERE (p_changed_date IS NULL OR target.date = p_changed_date)
      AND (p_tickers IS NULL OR target.ticker = ANY(p_tickers));

    WITH investor_flow AS (
        SELECT f.date, f.ticker, f.market_board,
               coalesce(sum(f.net_value_1d) FILTER (WHERE f.investor_type='Foreign'), 0) AS foreign_net_value,
               coalesce(sum(f.net_value_1d) FILTER (WHERE f.investor_type='Domestic'), 0) AS domestic_net_value
        FROM public."Feature_02_Broker_Rolling" AS f
        WHERE (p_changed_date IS NULL OR f.date=p_changed_date)
          AND (p_tickers IS NULL OR f.ticker=ANY(p_tickers))
        GROUP BY f.date, f.ticker, f.market_board
    ), broker_daily AS (
        SELECT f.date, f.ticker, f.market_board, f.broker,
               sum(f.buy_value_1d) AS buy_value_1d,
               sum(f.sell_value_1d) AS sell_value_1d,
               sum(f.net_value_1d) AS net_value_1d,
               bool_or(f.buy_value_1d<>0 OR f.sell_value_1d<>0
                       OR f.buy_lots_1d<>0 OR f.sell_lots_1d<>0) AS is_active
        FROM public."Feature_02_Broker_Rolling" AS f
        WHERE (p_changed_date IS NULL OR f.date=p_changed_date)
          AND (p_tickers IS NULL OR f.ticker=ANY(p_tickers))
        GROUP BY f.date, f.ticker, f.market_board, f.broker
    ), ranked_broker_daily AS (
        SELECT b.*, p.broker_classification,
               row_number() OVER (
                   PARTITION BY b.date,b.ticker,b.market_board
                   ORDER BY b.net_value_1d DESC,b.broker ASC
               ) AS buy_rank
        FROM broker_daily AS b
        LEFT JOIN public."IDX_Broker_Profile" AS p ON p.broker_code=b.broker
    ), aggregated AS (
        SELECT b.date,b.ticker,b.market_board,
               sum(b.buy_value_1d) AS total_buy_value,
               sum(b.sell_value_1d) AS total_sell_value,
               count(*) FILTER (WHERE b.is_active)::smallint AS active_broker_count,
               count(*) FILTER (WHERE b.net_value_1d>0)::smallint AS net_buy_broker_count,
               count(*) FILTER (WHERE b.net_value_1d<0)::smallint AS net_sell_broker_count,
               max(i.foreign_net_value) AS foreign_net_value,
               max(i.domestic_net_value) AS domestic_net_value,
               coalesce(sum(b.net_value_1d) FILTER (WHERE b.broker_classification='Institutional-heavy'),0) AS institutional_net_value,
               coalesce(sum(b.net_value_1d) FILTER (WHERE b.broker_classification='Retail-heavy'),0) AS retail_net_value,
               coalesce(sum(b.net_value_1d) FILTER (WHERE b.broker_classification='Mixed'),0) AS mixed_net_value,
               coalesce(sum(b.net_value_1d) FILTER (WHERE b.broker_classification='Niche'),0) AS niche_net_value,
               (array_agg(b.broker ORDER BY b.net_value_1d DESC,b.broker ASC)
                  FILTER (WHERE b.net_value_1d>0))[1] AS top_buyer,
               max(b.net_value_1d) FILTER (WHERE b.net_value_1d>0) AS top_buyer_net_value,
               (array_agg(b.broker ORDER BY b.net_value_1d ASC,b.broker ASC)
                  FILTER (WHERE b.net_value_1d<0))[1] AS top_seller,
               min(b.net_value_1d) FILTER (WHERE b.net_value_1d<0) AS top_seller_net_value,
               coalesce(sum(b.net_value_1d) FILTER (WHERE b.net_value_1d>0 AND b.buy_rank<=3),0) AS top3_buyer_net_value,
               coalesce(sum(b.net_value_1d) FILTER (WHERE b.net_value_1d>0),0) AS positive_net_value_total,
               sum(abs(b.net_value_1d)) AS absolute_net_value_total,
               sum(b.net_value_1d*b.net_value_1d) AS squared_net_value_total
        FROM ranked_broker_daily AS b
        JOIN investor_flow AS i USING (date,ticker,market_board)
        GROUP BY b.date,b.ticker,b.market_board
    )
    INSERT INTO public."Feature_03_Stock_Broker_Daily" (
        date,ticker,market_board,total_buy_value,total_sell_value,
        active_broker_count,net_buy_broker_count,net_sell_broker_count,
        net_buy_broker_ratio,foreign_net_value,domestic_net_value,
        institutional_net_value,retail_net_value,mixed_net_value,niche_net_value,
        top_buyer,top_buyer_net_value,top_seller,top_seller_net_value,
        top3_buyer_net_value,positive_net_value_total,top3_buyer_share,
        broker_concentration_hhi,calculated_at
    )
    SELECT date,ticker,market_board,total_buy_value,total_sell_value,
           active_broker_count,net_buy_broker_count,net_sell_broker_count,
           net_buy_broker_count::double precision/NULLIF(active_broker_count,0),
           foreign_net_value,domestic_net_value,
           institutional_net_value,retail_net_value,mixed_net_value,niche_net_value,
           top_buyer,top_buyer_net_value,top_seller,top_seller_net_value,
           top3_buyer_net_value,positive_net_value_total,
           top3_buyer_net_value::double precision/NULLIF(positive_net_value_total,0),
           squared_net_value_total::double precision/NULLIF(
             absolute_net_value_total::double precision*absolute_net_value_total::double precision,0),
           statement_timestamp()
    FROM aggregated;

    GET DIAGNOSTICS v_rows=ROW_COUNT;
    RETURN v_rows;
END
$function$;

COMMENT ON FUNCTION public.refresh_feature_03_stock_broker_daily(date,text[]) IS
  'Feature 03 v2 refresh: source Investor Type determines domestic/foreign daily flow; types are first summed per broker for broker breadth, rankings, HHI, and broker-profile classifications.';
COMMENT ON TABLE public."Feature_03_Stock_Broker_Daily" IS
  'Feature 03 v2 stock-level broker structure by ticker and board. Domestic/Foreign flows use source Investor Type; broker-profile classifications are current metadata. Boards never mix.';
COMMENT ON COLUMN public."Feature_03_Stock_Broker_Daily".foreign_net_value IS
  'Sum of Feature 02 net_value_1d where source investor_type is Foreign, across all brokers for this date, ticker and board. It is investor identity, not broker domicile.';
COMMENT ON COLUMN public."Feature_03_Stock_Broker_Daily".domestic_net_value IS
  'Sum of Feature 02 net_value_1d where source investor_type is Domestic, across all brokers for this date, ticker and board. It is investor identity, not broker domicile.';

UPDATE public."Feature_Catalog" SET is_active=false
WHERE feature_table='Feature_03_Stock_Broker_Daily' AND version='v1' AND is_active;

UPDATE public."Table_Catalog"
SET definition='Validated stock-level daily broker breadth, source-Investor-Type flows, current broker-profile classified flows, dominant brokers and net-flow concentration; Market Boards remain separate.',
    source_system='Validated Investor-Type Feature 02 daily flows and current IDX broker profile',
    source_tables=ARRAY['Feature_02_Broker_Rolling','IDX_Broker_Profile'],
    source_code_paths=ARRAY[
      'database/migrations/20260913_009_create_feature_03_stock_broker_daily.sql',
      'database/migrations/20260914_047_define_feature_03_investor_type_v2.sql',
      'scripts/backfill_feature_03.py','scripts/validate_feature_03.py',
      'scripts/check_feature_03_sample.py'
    ],
    update_rule='Full v2 rebuild after Feature 02 Investor-Type cutover. Refresh affected date/tickers after valid Feature 02 refresh; no automatic Feature 03 worker is deployed.',
    related_functions=ARRAY['refresh_feature_03_stock_broker_daily(date,text[])'],
    documentation_status='VERIFIED',readiness_mode='DATA_DATE',
    availability_rule='Only through the last validated Feature 02 date. Domestic/Foreign use source Investor Type; broker_classification is current metadata.',
    point_in_time_status='PARTIAL',
    historical_metadata_method='Investor Type is source point-in-time data; broker_classification is current-state profile metadata.'
WHERE table_schema='public' AND table_name='Feature_03_Stock_Broker_Daily';

INSERT INTO public."Feature_Catalog" (
 feature_table,feature_column,grain,feature_category,definition,calculation,
 source_tables,source_columns,lookback_window,minimum_history,unit,null_rule,
 refresh_trigger,dependency_rule,version,is_active,semantic_role,allowed_aggregations,
 ranking_interpretation,is_filterable,is_groupable,availability_rule,point_in_time_safe,
 historical_metadata_warning,analytical_interpretation,recommended_use,misuse_warning,
 semantic_review_status,validation_evidence
)
SELECT old.feature_table,old.feature_column,old.grain,old.feature_category,
 CASE old.feature_column
   WHEN 'foreign_net_value' THEN 'Sum of daily net value for source Foreign Investor Type across all brokers. Investor Type identifies the source investor, not broker domicile.'
   WHEN 'domestic_net_value' THEN 'Sum of daily net value for source Domestic Investor Type across all brokers. Investor Type identifies the source investor, not broker domicile.'
   ELSE col_description('public."Feature_03_Stock_Broker_Daily"'::regclass,att.attnum) END,
 CASE old.feature_column
   WHEN 'foreign_net_value' THEN 'SUM(Feature_02.net_value_1d) where Feature_02.investor_type = Foreign at date, ticker and Market Board; no IDX_Broker_Profile.broker_type is used.'
   WHEN 'domestic_net_value' THEN 'SUM(Feature_02.net_value_1d) where Feature_02.investor_type = Domestic at date, ticker and Market Board; no IDX_Broker_Profile.broker_type is used.'
   WHEN 'active_broker_count' THEN 'First SUM both Investor Types per date, ticker, board and broker; COUNT broker aggregates with nonzero gross buy/sell value or lots.'
   WHEN 'net_buy_broker_count' THEN 'First SUM both Investor Types per date, ticker, board and broker; COUNT broker aggregates where net_value_1d > 0.'
   WHEN 'net_sell_broker_count' THEN 'First SUM both Investor Types per date, ticker, board and broker; COUNT broker aggregates where net_value_1d < 0.'
   WHEN 'net_buy_broker_ratio' THEN 'First calculate broker-level counts after summing both Investor Types per broker; divide net_buy_broker_count by active_broker_count.'
   WHEN 'top_buyer' THEN 'First SUM both Investor Types per broker; choose greatest positive broker net value, ties broker code ascending.'
   WHEN 'top_seller' THEN 'First SUM both Investor Types per broker; choose lowest negative broker net value, ties broker code ascending.'
   WHEN 'top3_buyer_net_value' THEN 'First SUM both Investor Types per broker; SUM the three greatest positive broker net values.'
   WHEN 'positive_net_value_total' THEN 'First SUM both Investor Types per broker; SUM every positive broker net value.'
   WHEN 'broker_concentration_hhi' THEN 'First SUM both Investor Types per broker; SUM((ABS(broker net value)/SUM ABS(broker net value))^2).'
   WHEN 'institutional_net_value' THEN 'First SUM both Investor Types per broker; SUM broker net values where current IDX_Broker_Profile.broker_classification is Institutional-heavy.'
   WHEN 'retail_net_value' THEN 'First SUM both Investor Types per broker; SUM broker net values where current IDX_Broker_Profile.broker_classification is Retail-heavy.'
   WHEN 'mixed_net_value' THEN 'First SUM both Investor Types per broker; SUM broker net values where current IDX_Broker_Profile.broker_classification is Mixed.'
   WHEN 'niche_net_value' THEN 'First SUM both Investor Types per broker; SUM broker net values where current IDX_Broker_Profile.broker_classification is Niche.'
   ELSE old.calculation END,
 CASE WHEN old.feature_column IN ('foreign_net_value','domestic_net_value') THEN 'Feature_02_Broker_Rolling' ELSE old.source_tables END,
 CASE old.feature_column
   WHEN 'foreign_net_value' THEN 'Feature_02_Broker_Rolling.net_value_1d | Feature_02_Broker_Rolling.investor_type'
   WHEN 'domestic_net_value' THEN 'Feature_02_Broker_Rolling.net_value_1d | Feature_02_Broker_Rolling.investor_type'
   ELSE old.source_columns END,
 old.lookback_window,old.minimum_history,old.unit,
 CASE old.feature_column
   WHEN 'foreign_net_value' THEN 'Never NULL; zero when no Foreign Investor Type source flow exists.'
   WHEN 'domestic_net_value' THEN 'Never NULL; zero when no Domestic Investor Type source flow exists.'
   ELSE old.null_rule END,
 'Feature 02 refresh after Broker Summary load or correction; current broker profile change affects classification fields only.',
 'Requires validated Investor-Type Feature 02. Aggregate both Investor Types per broker before broker counts, ranks, HHI or broker-profile classified flows.',
 'v2',true,old.semantic_role,old.allowed_aggregations,old.ranking_interpretation,
 old.is_filterable,old.is_groupable,
 'Use only through the last validated Feature 02 date; do not treat current broker classification as historical investor identity.',
 CASE WHEN old.feature_column IN ('foreign_net_value','domestic_net_value') THEN true ELSE old.point_in_time_safe END,
 CASE WHEN old.feature_column IN ('foreign_net_value','domestic_net_value') THEN 'Source Investor Type is point-in-time data.' ELSE old.historical_metadata_warning END,
 CASE old.feature_column
   WHEN 'foreign_net_value' THEN 'Net flow by source Foreign investor identity, independent of the executing broker domicile.'
   WHEN 'domestic_net_value' THEN 'Net flow by source Domestic investor identity, independent of the executing broker domicile.'
   ELSE old.analytical_interpretation END,
 CASE old.feature_column
   WHEN 'foreign_net_value' THEN 'Compare foreign investor net flow with total or domestic flow within the identical ticker, date and board.'
   WHEN 'domestic_net_value' THEN 'Compare domestic investor net flow with total or foreign flow within the identical ticker, date and board.'
   ELSE old.recommended_use END,
 CASE old.feature_column
   WHEN 'foreign_net_value' THEN 'Do not call this foreign-broker flow or infer broker domicile; it is source investor identity.'
   WHEN 'domestic_net_value' THEN 'Do not call this domestic-broker flow or infer broker domicile; it is source investor identity.'
   ELSE old.misuse_warning END,
 'CALCULATION_VERIFIED',ARRAY[
  'database/migrations/20260914_047_define_feature_03_investor_type_v2.sql',
  'scripts/validate_feature_03.py','scripts/check_feature_03_sample.py','DATABASE_CHANGELOG.md'
 ]
FROM public."Feature_Catalog" old
JOIN pg_attribute att ON att.attrelid='public."Feature_03_Stock_Broker_Daily"'::regclass
 AND att.attname=old.feature_column
WHERE old.feature_table='Feature_03_Stock_Broker_Daily' AND old.version='v1';

UPDATE public."Column_Catalog" c
SET definition=f.definition,source_column_or_expression='Feature_Catalog active semantic version',
    source_code_paths=ARRAY['database/migrations/20260914_047_define_feature_03_investor_type_v2.sql',
                            'scripts/backfill_feature_03.py','scripts/validate_feature_03.py'],
    documentation_status='VERIFIED'
FROM public."Feature_Catalog" f
WHERE c.table_schema='public' AND c.table_name='Feature_03_Stock_Broker_Daily'
  AND f.feature_table=c.table_name AND f.feature_column=c.column_name
  AND f.version='v2' AND f.is_active;

UPDATE public."Feature_Relationship_Catalog" SET is_active=false
WHERE left_feature_table='Feature_02_Broker_Rolling'
  AND right_feature_table='Feature_03_Stock_Broker_Daily' AND is_active;
INSERT INTO public."Feature_Relationship_Catalog" (
 left_feature_table,right_feature_table,left_join_columns,right_join_columns,
 relationship_type,safe_output_grain,requires_preaggregation,definition,version,is_active
) VALUES (
 'Feature_02_Broker_Rolling','Feature_03_Stock_Broker_Daily',
 ARRAY['ticker','market_board','date'],ARRAY['ticker','market_board','date'],
 'MANY_TO_ONE','ticker × date × market_board after explicit Investor-Type aggregation',true,
 'Feature 03 v2 aggregates Feature 02 Investor Types per broker for broker-level metrics and directly by Investor Type for Domestic/Foreign flow. Aggregate Feature 02 before joining it to Feature 03 to avoid row multiplication.','v3',true
);

DO $coverage$
BEGIN
 IF (SELECT count(*) FROM public."Feature_Catalog"
     WHERE feature_table='Feature_03_Stock_Broker_Daily' AND version='v2' AND is_active) <> 24 THEN
    RAISE EXCEPTION 'Feature 03 v2 catalog coverage failed';
 END IF;
END
$coverage$;
COMMIT;
