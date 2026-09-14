-- Shadow replacement for Feature 02. It is intentionally not activated or swapped here.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '5min';

DO $preflight$
BEGIN
    IF to_regclass('public."Feature_02_Broker_Rolling"') IS NULL THEN
        RAISE EXCEPTION 'Canonical Feature 02 is missing';
    END IF;
    IF to_regclass('public."Feature_02_Broker_Rolling_v2"') IS NOT NULL THEN
        RAISE EXCEPTION 'Feature 02 v2 shadow already exists';
    END IF;
    IF to_regclass('public."IDX_Broker_Summary"') IS NULL
       OR to_regclass('public."IDX_Broker_Profile"') IS NULL THEN
        RAISE EXCEPTION 'Feature 02 source table is missing';
    END IF;
END
$preflight$;

CREATE TABLE public."Feature_02_Broker_Rolling_v2" (
    date date NOT NULL,
    ticker text NOT NULL,
    broker text NOT NULL,
    investor_type text NOT NULL,
    market_board text NOT NULL,
    broker_classification text,
    buy_value_1d numeric NOT NULL,
    sell_value_1d numeric NOT NULL,
    net_value_1d numeric NOT NULL,
    buy_lots_1d numeric NOT NULL,
    sell_lots_1d numeric NOT NULL,
    net_lots_1d numeric NOT NULL,
    net_value_5d numeric,
    net_value_20d numeric,
    net_value_60d numeric,
    net_lots_5d numeric,
    net_lots_20d numeric,
    net_lots_60d numeric,
    buy_days_20d smallint,
    sell_days_20d smallint,
    active_days_20d smallint,
    stock_trading_days_20d smallint,
    buy_day_ratio_20d double precision,
    buy_share_active_days_20d double precision,
    buy_days_60d smallint,
    sell_days_60d smallint,
    active_days_60d smallint,
    stock_trading_days_60d smallint,
    buy_day_ratio_60d double precision,
    buy_share_active_days_60d double precision,
    net_value_zscore_20d double precision,
    net_value_zscore_60d double precision,
    net_value_percentile_20d double precision,
    net_value_percentile_60d double precision,
    positive_net_value_20d numeric,
    largest_buy_day_20d numeric,
    largest_buy_day_share_20d double precision,
    calculated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Feature_02_Broker_Rolling_v2_pkey"
        PRIMARY KEY (ticker, market_board, broker, investor_type, date),
    CONSTRAINT "Feature_02_Broker_Rolling_v2_investor_type_check"
        CHECK (investor_type IN ('Domestic', 'Foreign')),
    CONSTRAINT "Feature_02_Broker_Rolling_v2_board_check"
        CHECK (market_board IN ('Regular', 'Nego', 'Tunai')),
    CONSTRAINT "Feature_02_Broker_Rolling_v2_identity_check"
        CHECK (btrim(ticker) <> '' AND btrim(broker) <> ''),
    CONSTRAINT "Feature_02_Broker_Rolling_v2_gross_check"
        CHECK (buy_value_1d >= 0 AND sell_value_1d >= 0
           AND buy_lots_1d >= 0 AND sell_lots_1d >= 0),
    CONSTRAINT "Feature_02_Broker_Rolling_v2_net_check"
        CHECK (net_value_1d = buy_value_1d - sell_value_1d
           AND net_lots_1d = buy_lots_1d - sell_lots_1d),
    CONSTRAINT "Feature_02_Broker_Rolling_v2_percentile_check"
        CHECK ((net_value_percentile_20d IS NULL OR net_value_percentile_20d BETWEEN 0 AND 100)
           AND (net_value_percentile_60d IS NULL OR net_value_percentile_60d BETWEEN 0 AND 100)),
    CONSTRAINT "Feature_02_Broker_Rolling_v2_ratio_check"
        CHECK ((buy_day_ratio_20d IS NULL OR buy_day_ratio_20d BETWEEN 0 AND 1)
           AND (buy_share_active_days_20d IS NULL OR buy_share_active_days_20d BETWEEN 0 AND 1)
           AND (buy_day_ratio_60d IS NULL OR buy_day_ratio_60d BETWEEN 0 AND 1)
           AND (buy_share_active_days_60d IS NULL OR buy_share_active_days_60d BETWEEN 0 AND 1)
           AND (largest_buy_day_share_20d IS NULL OR largest_buy_day_share_20d BETWEEN 0 AND 1))
);

COMMENT ON TABLE public."Feature_02_Broker_Rolling_v2" IS
    'Unreleased Feature 02 shadow: broker rolling signals are separated by source Investor Type and Market Board. Do not use as the canonical Feature 02 until full validation and atomic cutover pass.';

DO $comments$
DECLARE item record;
BEGIN
    FOR item IN
        SELECT * FROM (VALUES
            ('date','Ticker transaction date from IDX_Broker_Summary; the rolling calendar uses all observed dates for the ticker across investor types and boards.'),
            ('ticker','Exact IDX_Broker_Summary Symbol; no Stock Universe filter is applied.'),
            ('broker','Exact source Broker code identifying the executing broker.'),
            ('investor_type','Exact source Investor Type: Domestic or Foreign. This describes the investor represented by the source row, not the broker domicile.'),
            ('market_board','Exact source Market Board: Regular, Nego or Tunai; boards never mix in rolling calculations.'),
            ('broker_classification','Current broker usage classification from IDX_Broker_Profile; metadata only and not point-in-time history.'),
            ('buy_value_1d','Source Buy Value for this date, ticker, broker, investor type and board.'),
            ('sell_value_1d','Source Sell Value for this date, ticker, broker, investor type and board.'),
            ('net_value_1d','buy_value_1d minus sell_value_1d for the same investor type and board.'),
            ('buy_lots_1d','Source Buy Lots for this date, ticker, broker, investor type and board.'),
            ('sell_lots_1d','Source Sell Lots for this date, ticker, broker, investor type and board.'),
            ('net_lots_1d','buy_lots_1d minus sell_lots_1d for the same investor type and board.'),
            ('net_value_5d','Sum of net_value_1d over 5 ticker transaction dates within broker, investor type and board; missing activity contributes zero.'),
            ('net_value_20d','Sum of net_value_1d over 20 ticker transaction dates within broker, investor type and board; missing activity contributes zero.'),
            ('net_value_60d','Sum of net_value_1d over 60 ticker transaction dates within broker, investor type and board; missing activity contributes zero.'),
            ('net_lots_5d','Sum of net_lots_1d over 5 ticker transaction dates within broker, investor type and board.'),
            ('net_lots_20d','Sum of net_lots_1d over 20 ticker transaction dates within broker, investor type and board.'),
            ('net_lots_60d','Sum of net_lots_1d over 60 ticker transaction dates within broker, investor type and board.'),
            ('buy_days_20d','Number of positive net-value dates in the complete 20-date window for this broker, investor type and board.'),
            ('sell_days_20d','Number of negative net-value dates in the complete 20-date window for this broker, investor type and board.'),
            ('active_days_20d','Number of dates with nonzero gross activity in the complete 20-date window for this broker, investor type and board.'),
            ('stock_trading_days_20d','20 after the ticker has 20 observed transaction dates across any investor type or board; otherwise NULL.'),
            ('buy_day_ratio_20d','buy_days_20d divided by 20; for example 12 positive dates produces 0.60.'),
            ('buy_share_active_days_20d','buy_days_20d divided by active_days_20d; NULL when there are no active dates.'),
            ('buy_days_60d','Number of positive net-value dates in the complete 60-date window for this broker, investor type and board.'),
            ('sell_days_60d','Number of negative net-value dates in the complete 60-date window for this broker, investor type and board.'),
            ('active_days_60d','Number of dates with nonzero gross activity in the complete 60-date window for this broker, investor type and board.'),
            ('stock_trading_days_60d','60 after the ticker has 60 observed transaction dates across any investor type or board; otherwise NULL.'),
            ('buy_day_ratio_60d','buy_days_60d divided by 60.'),
            ('buy_share_active_days_60d','buy_days_60d divided by active_days_60d; NULL when there are no active dates.'),
            ('net_value_zscore_20d','Current 20-date net value minus the mean of the preceding 252 complete 20-date values, divided by their sample standard deviation; current date excluded.'),
            ('net_value_zscore_60d','Current 60-date net value minus the mean of the preceding 252 complete 60-date values, divided by their sample standard deviation; current date excluded.'),
            ('net_value_percentile_20d','Empirical midrank percentile of current 20-date net value against the preceding 252 complete values in the same broker, investor type and board partition.'),
            ('net_value_percentile_60d','Empirical midrank percentile of current 60-date net value against the preceding 252 complete values in the same broker, investor type and board partition.'),
            ('positive_net_value_20d','Sum of positive daily net values in the complete 20-date window; zero when the complete window has no positive date.'),
            ('largest_buy_day_20d','Largest positive daily net value in the complete 20-date window; NULL when no positive date exists.'),
            ('largest_buy_day_share_20d','largest_buy_day_20d divided by positive_net_value_20d; for example 40 of 100 total positive flow produces 0.40.'),
            ('calculated_at','Database statement timestamp when this shadow row was materialized.')
        ) AS definitions(column_name, definition)
    LOOP
        EXECUTE format('COMMENT ON COLUMN public.%I.%I IS %L',
            'Feature_02_Broker_Rolling_v2', item.column_name, item.definition);
    END LOOP;
END
$comments$;

INSERT INTO public."Table_Catalog" (
    table_name, category, definition, grain, primary_key_columns,
    source_system, source_tables, source_code_paths, update_rule,
    related_functions, documentation_status, readiness_mode,
    observation_date_column, availability_rule, point_in_time_status,
    historical_metadata_method
) VALUES (
    'Feature_02_Broker_Rolling_v2', 'Feature',
    'Unreleased shadow replacement for Feature 02 with Investor Type preserved as an analytical dimension.',
    'One row per date, source ticker, broker, Investor Type and Market Board',
    ARRAY['ticker','market_board','broker','investor_type','date'],
    'Stockbit broker summary and current broker profile',
    ARRAY['IDX_Broker_Summary','IDX_Broker_Profile'],
    ARRAY['database/migrations/20260914_034_create_feature_02_investor_type_shadow.sql',
          'scripts/backfill_feature_02_v2.py'],
    'Shadow backfill only; not production-ready until full validation and atomic cutover.',
    ARRAY['feature_02_empirical_midrank_percentile(numeric,numeric[])'],
    'PARTIAL', 'NOT_APPLICABLE', 'date',
    'Unreleased shadow data must not be used for production analysis.',
    'PARTIAL',
    'broker_classification is current-state metadata; investor_type is point-in-time source data.'
);

COMMIT;
