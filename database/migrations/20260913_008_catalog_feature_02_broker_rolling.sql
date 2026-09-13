-- Apply only after Feature 02 source reconciliation and formula validation pass.
-- The semantic version is v1; this migration never changes historical migrations.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '20min';

DO $preflight$
BEGIN
    IF to_regclass('public."Feature_02_Broker_Rolling"') IS NULL THEN
        RAISE EXCEPTION 'Feature 02 table is missing';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public."Feature_Catalog"
        WHERE feature_table = 'Feature_02_Broker_Rolling' AND version = 'v1'
    ) THEN
        RAISE EXCEPTION 'Feature 02 v1 catalog already exists';
    END IF;
END
$preflight$;

-- Daily cross-ticker consumers can filter date/board without scanning all history.
-- The ticker-first primary key remains the path for ticker/broker histories.
CREATE INDEX "Feature_02_Broker_Rolling_date_board_ticker_idx"
    ON public."Feature_02_Broker_Rolling" (date, market_board, ticker);

WITH definitions (
    feature_column, feature_category, calculation, source_columns,
    lookback_window, minimum_history, unit, null_rule
) AS (
    VALUES
    ('date','Identity','Copy source "Date" for the active daily grain.','IDX_Broker_Summary."Date"','None','1 source row','Date','Never NULL; no row without source activity.'),
    ('ticker','Identity','Copy source "Symbol" without a stock-universe filter.','IDX_Broker_Summary."Symbol"','None','1 source row','Ticker or instrument symbol','Never NULL; no row without source activity.'),
    ('broker','Identity','Copy source "Broker"; aggregate Domestic and Foreign investor rows together.','IDX_Broker_Summary."Broker" | IDX_Broker_Summary."Investor Type"','None','1 source row','Broker code','Never NULL; no row without source activity.'),
    ('market_board','Identity','Copy source "Market Board"; Regular, Nego and Tunai are separate partitions.','IDX_Broker_Summary."Market Board"','None','1 source row','Board label','Never NULL; no row without source activity.'),
    ('broker_type','Broker Classification','Current IDX_Broker_Profile.broker_type matched on broker_code; not point-in-time history.','IDX_Broker_Profile.broker_code | IDX_Broker_Profile.broker_type','None','Matching current profile','Domestic/Foreign label','NULL if no current broker profile or the profile value is NULL.'),
    ('broker_classification','Broker Classification','Current IDX_Broker_Profile.broker_classification matched on broker_code; not point-in-time history.','IDX_Broker_Profile.broker_code | IDX_Broker_Profile.broker_classification','None','Matching current profile','Broker usage label','NULL if no current broker profile or the profile value is NULL.'),
    ('buy_value_1d','Broker Flow','SUM("Buy Value") across investor types at date, ticker, broker and board.','IDX_Broker_Summary."Buy Value" | IDX_Broker_Summary."Investor Type"','1 source date','1 source row','IDR','Never NULL for a stored row.'),
    ('sell_value_1d','Broker Flow','SUM("Sell Value") across investor types at date, ticker, broker and board.','IDX_Broker_Summary."Sell Value" | IDX_Broker_Summary."Investor Type"','1 source date','1 source row','IDR','Never NULL for a stored row.'),
    ('net_value_1d','Broker Flow','buy_value_1d - sell_value_1d.','IDX_Broker_Summary."Buy Value" | IDX_Broker_Summary."Sell Value"','1 source date','1 source row','IDR','Never NULL for a stored row.'),
    ('buy_lots_1d','Broker Flow','SUM("Buy Lots") across investor types at date, ticker, broker and board.','IDX_Broker_Summary."Buy Lots" | IDX_Broker_Summary."Investor Type"','1 source date','1 source row','Lots','Never NULL for a stored row.'),
    ('sell_lots_1d','Broker Flow','SUM("Sell Lots") across investor types at date, ticker, broker and board.','IDX_Broker_Summary."Sell Lots" | IDX_Broker_Summary."Investor Type"','1 source date','1 source row','Lots','Never NULL for a stored row.'),
    ('net_lots_1d','Broker Flow','buy_lots_1d - sell_lots_1d.','IDX_Broker_Summary."Buy Lots" | IDX_Broker_Summary."Sell Lots"','1 source date','1 source row','Lots','Never NULL for a stored row.'),
    ('net_value_5d','Broker Flow','SUM(net_value_1d) over the latest 5 ticker transaction dates, with absent broker-board days as zero.','IDX_Broker_Summary."Date" | IDX_Broker_Summary."Buy Value" | IDX_Broker_Summary."Sell Value"','5 ticker transaction dates','5 ticker transaction dates','IDR','NULL until ticker has 5 transaction dates.'),
    ('net_value_20d','Broker Flow','SUM(net_value_1d) over the latest 20 ticker transaction dates, with absent broker-board days as zero.','IDX_Broker_Summary."Date" | IDX_Broker_Summary."Buy Value" | IDX_Broker_Summary."Sell Value"','20 ticker transaction dates','20 ticker transaction dates','IDR','NULL until ticker has 20 transaction dates.'),
    ('net_value_60d','Broker Flow','SUM(net_value_1d) over the latest 60 ticker transaction dates, with absent broker-board days as zero.','IDX_Broker_Summary."Date" | IDX_Broker_Summary."Buy Value" | IDX_Broker_Summary."Sell Value"','60 ticker transaction dates','60 ticker transaction dates','IDR','NULL until ticker has 60 transaction dates.'),
    ('net_lots_5d','Broker Flow','SUM(net_lots_1d) over the latest 5 ticker transaction dates, with absent broker-board days as zero.','IDX_Broker_Summary."Date" | IDX_Broker_Summary."Buy Lots" | IDX_Broker_Summary."Sell Lots"','5 ticker transaction dates','5 ticker transaction dates','Lots','NULL until ticker has 5 transaction dates.'),
    ('net_lots_20d','Broker Flow','SUM(net_lots_1d) over the latest 20 ticker transaction dates, with absent broker-board days as zero.','IDX_Broker_Summary."Date" | IDX_Broker_Summary."Buy Lots" | IDX_Broker_Summary."Sell Lots"','20 ticker transaction dates','20 ticker transaction dates','Lots','NULL until ticker has 20 transaction dates.'),
    ('net_lots_60d','Broker Flow','SUM(net_lots_1d) over the latest 60 ticker transaction dates, with absent broker-board days as zero.','IDX_Broker_Summary."Date" | IDX_Broker_Summary."Buy Lots" | IDX_Broker_Summary."Sell Lots"','60 ticker transaction dates','60 ticker transaction dates','Lots','NULL until ticker has 60 transaction dates.'),
    ('buy_days_20d','Broker Persistence','COUNT of dates with net_value_1d > 0 in the latest 20 ticker transaction dates.','IDX_Broker_Summary."Date" | IDX_Broker_Summary."Buy Value" | IDX_Broker_Summary."Sell Value"','20 ticker transaction dates','20 ticker transaction dates','Days','NULL until ticker has 20 transaction dates.'),
    ('sell_days_20d','Broker Persistence','COUNT of dates with net_value_1d < 0 in the latest 20 ticker transaction dates.','IDX_Broker_Summary."Date" | IDX_Broker_Summary."Buy Value" | IDX_Broker_Summary."Sell Value"','20 ticker transaction dates','20 ticker transaction dates','Days','NULL until ticker has 20 transaction dates.'),
    ('active_days_20d','Broker Persistence','COUNT of dates with any nonzero gross buy/sell value or lots for this broker-board in the latest 20 ticker transaction dates.','IDX_Broker_Summary."Date" | IDX_Broker_Summary."Buy Value" | IDX_Broker_Summary."Sell Value" | IDX_Broker_Summary."Buy Lots" | IDX_Broker_Summary."Sell Lots"','20 ticker transaction dates','20 ticker transaction dates','Days','NULL until ticker has 20 transaction dates.'),
    ('stock_trading_days_20d','Broker Persistence','20 when the ticker has at least 20 distinct source dates on any board.','IDX_Broker_Summary."Date" | IDX_Broker_Summary."Symbol"','20 ticker transaction dates','20 ticker transaction dates','Days','NULL until ticker has 20 transaction dates.'),
    ('buy_day_ratio_20d','Broker Persistence','buy_days_20d / 20.','IDX_Broker_Summary."Date" | IDX_Broker_Summary."Buy Value" | IDX_Broker_Summary."Sell Value"','20 ticker transaction dates','20 ticker transaction dates','Fraction','NULL until ticker has 20 transaction dates.'),
    ('buy_share_active_days_20d','Broker Persistence','buy_days_20d / active_days_20d.','IDX_Broker_Summary."Date" | IDX_Broker_Summary."Buy Value" | IDX_Broker_Summary."Sell Value" | IDX_Broker_Summary."Buy Lots" | IDX_Broker_Summary."Sell Lots"','20 ticker transaction dates','20 ticker transaction dates','Fraction','NULL until full 20-date window or active_days_20d = 0.'),
    ('buy_days_60d','Broker Persistence','COUNT of dates with net_value_1d > 0 in the latest 60 ticker transaction dates.','IDX_Broker_Summary."Date" | IDX_Broker_Summary."Buy Value" | IDX_Broker_Summary."Sell Value"','60 ticker transaction dates','60 ticker transaction dates','Days','NULL until ticker has 60 transaction dates.'),
    ('sell_days_60d','Broker Persistence','COUNT of dates with net_value_1d < 0 in the latest 60 ticker transaction dates.','IDX_Broker_Summary."Date" | IDX_Broker_Summary."Buy Value" | IDX_Broker_Summary."Sell Value"','60 ticker transaction dates','60 ticker transaction dates','Days','NULL until ticker has 60 transaction dates.'),
    ('active_days_60d','Broker Persistence','COUNT of dates with any nonzero gross buy/sell value or lots for this broker-board in the latest 60 ticker transaction dates.','IDX_Broker_Summary."Date" | IDX_Broker_Summary."Buy Value" | IDX_Broker_Summary."Sell Value" | IDX_Broker_Summary."Buy Lots" | IDX_Broker_Summary."Sell Lots"','60 ticker transaction dates','60 ticker transaction dates','Days','NULL until ticker has 60 transaction dates.'),
    ('stock_trading_days_60d','Broker Persistence','60 when the ticker has at least 60 distinct source dates on any board.','IDX_Broker_Summary."Date" | IDX_Broker_Summary."Symbol"','60 ticker transaction dates','60 ticker transaction dates','Days','NULL until ticker has 60 transaction dates.'),
    ('buy_day_ratio_60d','Broker Persistence','buy_days_60d / 60.','IDX_Broker_Summary."Date" | IDX_Broker_Summary."Buy Value" | IDX_Broker_Summary."Sell Value"','60 ticker transaction dates','60 ticker transaction dates','Fraction','NULL until ticker has 60 transaction dates.'),
    ('buy_share_active_days_60d','Broker Persistence','buy_days_60d / active_days_60d.','IDX_Broker_Summary."Date" | IDX_Broker_Summary."Buy Value" | IDX_Broker_Summary."Sell Value" | IDX_Broker_Summary."Buy Lots" | IDX_Broker_Summary."Sell Lots"','60 ticker transaction dates','60 ticker transaction dates','Fraction','NULL until full 60-date window or active_days_60d = 0.'),
    ('net_value_zscore_20d','Broker Abnormality','(current net_value_20d - sample mean of preceding 252 complete net_value_20d observations) / sample standard deviation of those 252 values; current date excluded.','IDX_Broker_Summary."Date" | IDX_Broker_Summary."Buy Value" | IDX_Broker_Summary."Sell Value"','20 current + 252 prior complete ticker-date observations','272 ticker transaction dates','Standard deviations','NULL unless 252 prior complete 20-date values exist or if sample standard deviation = 0.'),
    ('net_value_zscore_60d','Broker Abnormality','(current net_value_60d - sample mean of preceding 252 complete net_value_60d observations) / sample standard deviation of those 252 values; current date excluded.','IDX_Broker_Summary."Date" | IDX_Broker_Summary."Buy Value" | IDX_Broker_Summary."Sell Value"','60 current + 252 prior complete ticker-date observations','312 ticker transaction dates','Standard deviations','NULL unless 252 prior complete 60-date values exist or if sample standard deviation = 0.'),
    ('net_value_percentile_20d','Broker Abnormality','100 * (number of preceding 252 complete net_value_20d values less than current + 0.5 * number equal to current) / 252.','IDX_Broker_Summary."Date" | IDX_Broker_Summary."Buy Value" | IDX_Broker_Summary."Sell Value"','20 current + 252 prior complete ticker-date observations','272 ticker transaction dates','Percentile 0-100','NULL unless 252 prior complete 20-date values exist.'),
    ('net_value_percentile_60d','Broker Abnormality','100 * (number of preceding 252 complete net_value_60d values less than current + 0.5 * number equal to current) / 252.','IDX_Broker_Summary."Date" | IDX_Broker_Summary."Buy Value" | IDX_Broker_Summary."Sell Value"','60 current + 252 prior complete ticker-date observations','312 ticker transaction dates','Percentile 0-100','NULL unless 252 prior complete 60-date values exist.'),
    ('positive_net_value_20d','Broker Concentration','SUM(GREATEST(net_value_1d,0)) over the latest 20 ticker transaction dates.','IDX_Broker_Summary."Date" | IDX_Broker_Summary."Buy Value" | IDX_Broker_Summary."Sell Value"','20 ticker transaction dates','20 ticker transaction dates','IDR','NULL until ticker has 20 transaction dates; zero is a valid complete-window result.'),
    ('largest_buy_day_20d','Broker Concentration','MAX(net_value_1d) for positive-net dates in the latest 20 ticker transaction dates.','IDX_Broker_Summary."Date" | IDX_Broker_Summary."Buy Value" | IDX_Broker_Summary."Sell Value"','20 ticker transaction dates','20 ticker transaction dates','IDR','NULL until full 20-date window or if there are no positive-net dates.'),
    ('largest_buy_day_share_20d','Broker Concentration','largest_buy_day_20d / positive_net_value_20d.','IDX_Broker_Summary."Date" | IDX_Broker_Summary."Buy Value" | IDX_Broker_Summary."Sell Value"','20 ticker transaction dates','20 ticker transaction dates','Fraction','NULL until full 20-date window or positive_net_value_20d = 0.'),
    ('calculated_at','Metadata','statement_timestamp() of the PostgreSQL insert statement that materialized the row.','IDX_Broker_Summary."Date"','None','1 inserted row','Timestamp with time zone','Never NULL for a stored row.')
)
INSERT INTO public."Feature_Catalog" (
    feature_table, feature_column, grain, feature_category, definition,
    calculation, source_tables, source_columns, lookback_window,
    minimum_history, unit, null_rule, refresh_trigger, dependency_rule,
    version, is_active
)
SELECT 'Feature_02_Broker_Rolling', d.feature_column,
       'Date × source ticker × broker × market board', d.feature_category,
       pg_catalog.col_description(rel.oid, att.attnum), d.calculation,
       CASE WHEN d.feature_column IN ('broker_type','broker_classification')
            THEN 'IDX_Broker_Summary | IDX_Broker_Profile'
            ELSE 'IDX_Broker_Summary' END,
       d.source_columns, d.lookback_window, d.minimum_history, d.unit,
       d.null_rule,
       'Broker Summary load or correction; current Broker Profile change for metadata.',
       'Requires the source ticker transaction-date calendar across any board. Output rows require broker-board activity on that date. No automatic Feature 02 worker is deployed in v1.',
       'v1', true
FROM definitions d
JOIN pg_catalog.pg_class rel ON rel.oid = 'public."Feature_02_Broker_Rolling"'::regclass
JOIN pg_catalog.pg_attribute att
  ON att.attrelid = rel.oid AND att.attname = d.feature_column
WHERE att.attnum > 0 AND NOT att.attisdropped;

DO $coverage$
DECLARE v_physical integer; v_catalog integer;
BEGIN
    SELECT count(*) INTO v_physical FROM information_schema.columns
    WHERE table_schema='public' AND table_name='Feature_02_Broker_Rolling';
    SELECT count(*) INTO v_catalog FROM public."Feature_Catalog"
    WHERE feature_table='Feature_02_Broker_Rolling' AND version='v1' AND is_active;
    IF v_physical <> 38 OR v_catalog <> v_physical THEN
        RAISE EXCEPTION 'Feature 02 catalog coverage mismatch: physical %, active %', v_physical, v_catalog;
    END IF;
END
$coverage$;

UPDATE public."Table_Catalog"
SET documentation_status='VERIFIED',
    definition='Validated broker flow, persistence, abnormality and quiet accumulation by source ticker, broker, board and transaction date. All source symbols are in scope.',
    update_rule='Initial full backfill via scripts/backfill_feature_02.py. No automatic Feature 02 refresh worker is deployed; rerun/rebuild is required after source corrections or new loads.',
    source_code_paths=ARRAY[
      'database/migrations/20260913_007_create_feature_02_broker_rolling.sql',
      'database/migrations/20260913_008_catalog_feature_02_broker_rolling.sql',
      'scripts/backfill_feature_02.py'
    ]
WHERE table_schema='public' AND table_name='Feature_02_Broker_Rolling';

UPDATE public."Column_Catalog" AS c
SET documentation_status='VERIFIED'
WHERE c.table_schema='public' AND c.table_name='Feature_02_Broker_Rolling';

COMMIT;
