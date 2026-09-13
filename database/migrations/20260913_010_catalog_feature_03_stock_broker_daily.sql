-- Apply only after Feature 03 full reconciliation and independent samples pass.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '10min';

DO $preflight$
BEGIN
    IF to_regclass('public."Feature_03_Stock_Broker_Daily"') IS NULL THEN
        RAISE EXCEPTION 'Feature 03 table is missing';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public."Feature_Catalog"
        WHERE feature_table='Feature_03_Stock_Broker_Daily' AND version='v1'
    ) THEN
        RAISE EXCEPTION 'Feature 03 v1 catalog already exists';
    END IF;
END
$preflight$;

CREATE INDEX "Feature_03_Stock_Broker_Daily_date_board_ticker_idx"
    ON public."Feature_03_Stock_Broker_Daily" (date, market_board, ticker);

-- The governance trigger permits active Feature definitions only for a VERIFIED
-- table. These promotions are in the same transaction and roll back if any
-- definition or coverage check fails.
UPDATE public."Table_Catalog"
SET documentation_status='VERIFIED',
    definition='Validated stock-level daily broker breadth, classified flows, dominant brokers and net-flow concentration, separated by source market board.',
    update_rule='Initial full backfill via scripts/backfill_feature_03.py. Refresh the affected date/tickers after Feature 02 is refreshed; no automatic Feature 03 worker is deployed.',
    source_code_paths=ARRAY[
      'database/migrations/20260913_009_create_feature_03_stock_broker_daily.sql',
      'database/migrations/20260913_010_catalog_feature_03_stock_broker_daily.sql',
      'scripts/backfill_feature_03.py'
    ]
WHERE table_schema='public' AND table_name='Feature_03_Stock_Broker_Daily';

UPDATE public."Column_Catalog"
SET documentation_status='VERIFIED'
WHERE table_schema='public' AND table_name='Feature_03_Stock_Broker_Daily';

WITH definitions (
    feature_column, feature_category, calculation, source_tables,
    source_columns, lookback_window, minimum_history, unit, null_rule
) AS (
    VALUES
    ('date','Identity','Copy Feature_02_Broker_Rolling.date for the daily ticker-board grain.','Feature_02_Broker_Rolling','Feature_02_Broker_Rolling.date','1 source date','1 Feature 02 row','Date','Never NULL; no row exists without a Feature 02 ticker-board observation.'),
    ('ticker','Identity','Copy Feature_02_Broker_Rolling.ticker without filtering to the current stock universe.','Feature_02_Broker_Rolling','Feature_02_Broker_Rolling.ticker','1 source date','1 Feature 02 row','Ticker or instrument symbol','Never NULL.'),
    ('market_board','Identity','Copy Feature_02_Broker_Rolling.market_board; Regular, Nego and Tunai remain separate.','Feature_02_Broker_Rolling','Feature_02_Broker_Rolling.market_board','1 source date','1 Feature 02 row','Board label','Never NULL.'),
    ('total_buy_value','Broker Flow','SUM(Feature_02_Broker_Rolling.buy_value_1d) across brokers at date, ticker and board.','Feature_02_Broker_Rolling','Feature_02_Broker_Rolling.buy_value_1d','1 source date','1 Feature 02 row','IDR','Never NULL for a stored row.'),
    ('total_sell_value','Broker Flow','SUM(Feature_02_Broker_Rolling.sell_value_1d) across brokers at date, ticker and board.','Feature_02_Broker_Rolling','Feature_02_Broker_Rolling.sell_value_1d','1 source date','1 Feature 02 row','IDR','Never NULL for a stored row.'),
    ('active_broker_count','Broker Flow','COUNT of brokers with nonzero buy/sell value or lots at date, ticker and board.','Feature_02_Broker_Rolling','Feature_02_Broker_Rolling.broker | Feature_02_Broker_Rolling.buy_value_1d | Feature_02_Broker_Rolling.sell_value_1d | Feature_02_Broker_Rolling.buy_lots_1d | Feature_02_Broker_Rolling.sell_lots_1d','1 source date','1 Feature 02 row','Count','Never NULL; zero is valid when source rows contain only zero gross activity.'),
    ('net_buy_broker_count','Broker Flow','COUNT of brokers where net_value_1d > 0.','Feature_02_Broker_Rolling','Feature_02_Broker_Rolling.broker | Feature_02_Broker_Rolling.net_value_1d','1 source date','1 Feature 02 row','Count','Never NULL; zero is valid.'),
    ('net_sell_broker_count','Broker Flow','COUNT of brokers where net_value_1d < 0.','Feature_02_Broker_Rolling','Feature_02_Broker_Rolling.broker | Feature_02_Broker_Rolling.net_value_1d','1 source date','1 Feature 02 row','Count','Never NULL; zero is valid.'),
    ('net_buy_broker_ratio','Broker Flow','net_buy_broker_count / active_broker_count. Zero-net active brokers remain in the denominator.','Feature_02_Broker_Rolling','Feature_02_Broker_Rolling.net_value_1d | Feature_02_Broker_Rolling.buy_value_1d | Feature_02_Broker_Rolling.sell_value_1d | Feature_02_Broker_Rolling.buy_lots_1d | Feature_02_Broker_Rolling.sell_lots_1d','1 source date','1 active broker','Fraction','NULL when active_broker_count is zero.'),
    ('foreign_net_value','Broker Flow','SUM(net_value_1d) for brokers whose current IDX_Broker_Profile.broker_type is Foreign.','Feature_02_Broker_Rolling | IDX_Broker_Profile','Feature_02_Broker_Rolling.net_value_1d | Feature_02_Broker_Rolling.broker | IDX_Broker_Profile.broker_code | IDX_Broker_Profile.broker_type','1 source date','1 Feature 02 row','IDR','Never NULL; zero when no matching Foreign broker flow. Unmatched profiles are excluded.'),
    ('domestic_net_value','Broker Flow','SUM(net_value_1d) for brokers whose current IDX_Broker_Profile.broker_type is Domestic.','Feature_02_Broker_Rolling | IDX_Broker_Profile','Feature_02_Broker_Rolling.net_value_1d | Feature_02_Broker_Rolling.broker | IDX_Broker_Profile.broker_code | IDX_Broker_Profile.broker_type','1 source date','1 Feature 02 row','IDR','Never NULL; zero when no matching Domestic broker flow. Unmatched profiles are excluded.'),
    ('institutional_net_value','Broker Flow','SUM(net_value_1d) for current broker_classification Institutional-heavy.','Feature_02_Broker_Rolling | IDX_Broker_Profile','Feature_02_Broker_Rolling.net_value_1d | Feature_02_Broker_Rolling.broker | IDX_Broker_Profile.broker_code | IDX_Broker_Profile.broker_classification','1 source date','1 Feature 02 row','IDR','Never NULL; zero when no matching category flow. Unmatched profiles are excluded.'),
    ('retail_net_value','Broker Flow','SUM(net_value_1d) for current broker_classification Retail-heavy.','Feature_02_Broker_Rolling | IDX_Broker_Profile','Feature_02_Broker_Rolling.net_value_1d | Feature_02_Broker_Rolling.broker | IDX_Broker_Profile.broker_code | IDX_Broker_Profile.broker_classification','1 source date','1 Feature 02 row','IDR','Never NULL; zero when no matching category flow. Unmatched profiles are excluded.'),
    ('mixed_net_value','Broker Flow','SUM(net_value_1d) for current broker_classification Mixed.','Feature_02_Broker_Rolling | IDX_Broker_Profile','Feature_02_Broker_Rolling.net_value_1d | Feature_02_Broker_Rolling.broker | IDX_Broker_Profile.broker_code | IDX_Broker_Profile.broker_classification','1 source date','1 Feature 02 row','IDR','Never NULL; zero when no matching category flow. Unmatched profiles are excluded.'),
    ('niche_net_value','Broker Flow','SUM(net_value_1d) for current broker_classification Niche.','Feature_02_Broker_Rolling | IDX_Broker_Profile','Feature_02_Broker_Rolling.net_value_1d | Feature_02_Broker_Rolling.broker | IDX_Broker_Profile.broker_code | IDX_Broker_Profile.broker_classification','1 source date','1 Feature 02 row','IDR','Never NULL; zero when no matching category flow. Unmatched profiles are excluded.'),
    ('top_buyer','Broker Concentration','Broker with greatest positive net_value_1d; equal values break by broker code ascending.','Feature_02_Broker_Rolling','Feature_02_Broker_Rolling.broker | Feature_02_Broker_Rolling.net_value_1d','1 source date','1 positive-net broker','Broker code','NULL when no broker has positive net value.'),
    ('top_buyer_net_value','Broker Concentration','MAX(net_value_1d) where net_value_1d > 0.','Feature_02_Broker_Rolling','Feature_02_Broker_Rolling.net_value_1d','1 source date','1 positive-net broker','IDR','NULL when no broker has positive net value.'),
    ('top_seller','Broker Concentration','Broker with lowest negative net_value_1d; equal values break by broker code ascending.','Feature_02_Broker_Rolling','Feature_02_Broker_Rolling.broker | Feature_02_Broker_Rolling.net_value_1d','1 source date','1 negative-net broker','Broker code','NULL when no broker has negative net value.'),
    ('top_seller_net_value','Broker Concentration','MIN(net_value_1d) where net_value_1d < 0; stored with its negative sign.','Feature_02_Broker_Rolling','Feature_02_Broker_Rolling.net_value_1d','1 source date','1 negative-net broker','IDR','NULL when no broker has negative net value.'),
    ('top3_buyer_net_value','Broker Concentration','SUM of the three greatest positive net_value_1d values; rank ties use broker code ascending.','Feature_02_Broker_Rolling','Feature_02_Broker_Rolling.broker | Feature_02_Broker_Rolling.net_value_1d','1 source date','1 positive-net broker','IDR','Never NULL; zero when no positive-net broker exists.'),
    ('positive_net_value_total','Broker Concentration','SUM(net_value_1d) where net_value_1d > 0 across all brokers.','Feature_02_Broker_Rolling','Feature_02_Broker_Rolling.net_value_1d','1 source date','1 positive-net broker','IDR','Never NULL; zero when no positive-net broker exists.'),
    ('top3_buyer_share','Broker Concentration','top3_buyer_net_value / positive_net_value_total.','Feature_02_Broker_Rolling','Feature_02_Broker_Rolling.broker | Feature_02_Broker_Rolling.net_value_1d','1 source date','1 positive-net broker','Fraction','NULL when positive_net_value_total is zero.'),
    ('broker_concentration_hhi','Broker Concentration','For each broker weight=ABS(net_value_1d)/SUM(ABS(net_value_1d)); result is SUM(weight^2).','Feature_02_Broker_Rolling','Feature_02_Broker_Rolling.broker | Feature_02_Broker_Rolling.net_value_1d','1 source date','1 nonzero-net broker','HHI ratio 0-1','NULL when total absolute broker net value is zero.'),
    ('calculated_at','Metadata','statement_timestamp() of the PostgreSQL refresh that materialized the row.','Feature_02_Broker_Rolling','Feature_02_Broker_Rolling.date','None','1 inserted row','Timestamp with time zone','Never NULL for a stored row.')
)
INSERT INTO public."Feature_Catalog" (
    feature_table, feature_column, grain, feature_category, definition,
    calculation, source_tables, source_columns, lookback_window,
    minimum_history, unit, null_rule, refresh_trigger, dependency_rule,
    version, is_active
)
SELECT 'Feature_03_Stock_Broker_Daily', d.feature_column,
       'Date × source ticker × market board', d.feature_category,
       pg_catalog.col_description(rel.oid, att.attnum), d.calculation,
       d.source_tables, d.source_columns, d.lookback_window,
       d.minimum_history, d.unit, d.null_rule,
       'Valid Broker Summary load after Feature 02 refresh; current Broker Profile classification change.',
       'Requires validated Feature 02 daily rows for the affected date/tickers. Regular, Nego and Tunai never mix. No automatic Feature 03 worker is deployed in v1.',
       'v1', true
FROM definitions AS d
JOIN pg_catalog.pg_class AS rel ON rel.oid='public."Feature_03_Stock_Broker_Daily"'::regclass
JOIN pg_catalog.pg_attribute AS att
  ON att.attrelid=rel.oid AND att.attname=d.feature_column
WHERE att.attnum > 0 AND NOT att.attisdropped;

DO $coverage$
DECLARE v_physical integer; v_catalog integer;
BEGIN
    SELECT count(*) INTO v_physical FROM information_schema.columns
    WHERE table_schema='public' AND table_name='Feature_03_Stock_Broker_Daily';
    SELECT count(*) INTO v_catalog FROM public."Feature_Catalog"
    WHERE feature_table='Feature_03_Stock_Broker_Daily' AND version='v1' AND is_active;
    IF v_physical <> 24 OR v_catalog <> v_physical THEN
        RAISE EXCEPTION 'Feature 03 catalog coverage mismatch: physical %, active %', v_physical, v_catalog;
    END IF;
END
$coverage$;

UPDATE public."Table_Catalog"
SET documentation_status='VERIFIED',
    definition='Validated stock-level daily broker breadth, classified flows, dominant brokers and net-flow concentration, separated by source market board.',
    update_rule='Initial full backfill via scripts/backfill_feature_03.py. Refresh the affected date/tickers after Feature 02 is refreshed; no automatic Feature 03 worker is deployed.',
    source_code_paths=ARRAY[
      'database/migrations/20260913_009_create_feature_03_stock_broker_daily.sql',
      'database/migrations/20260913_010_catalog_feature_03_stock_broker_daily.sql',
      'scripts/backfill_feature_03.py'
    ]
WHERE table_schema='public' AND table_name='Feature_03_Stock_Broker_Daily';

UPDATE public."Column_Catalog"
SET documentation_status='VERIFIED'
WHERE table_schema='public' AND table_name='Feature_03_Stock_Broker_Daily';

COMMIT;
