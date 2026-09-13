-- Feature 02 is one table for all broker-summary symbols and three separate boards.
-- Data is populated and validated by scripts/backfill_feature_02.py after this migration.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '5min';

DO $preflight$
BEGIN
    IF to_regclass('public."Feature_02_Broker_Rolling"') IS NOT NULL THEN
        RAISE EXCEPTION 'Feature_02_Broker_Rolling already exists';
    END IF;
    IF to_regclass('public."IDX_Broker_Summary"') IS NULL
       OR to_regclass('public."IDX_Broker_Profile"') IS NULL
       OR to_regclass('public."Table_Catalog"') IS NULL
       OR to_regclass('public."Column_Catalog"') IS NULL THEN
        RAISE EXCEPTION 'Feature 02 source or catalog table is missing';
    END IF;
END
$preflight$;

CREATE TABLE public."Feature_02_Broker_Rolling" (
    date date NOT NULL,
    ticker text NOT NULL,
    broker text NOT NULL,
    market_board text NOT NULL,
    broker_type text,
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
    CONSTRAINT "Feature_02_Broker_Rolling_pkey"
        PRIMARY KEY (ticker, market_board, broker, date),
    CONSTRAINT "Feature_02_Broker_Rolling_board_check"
        CHECK (market_board IN ('Regular', 'Nego', 'Tunai')),
    CONSTRAINT "Feature_02_Broker_Rolling_identity_check"
        CHECK (btrim(ticker) <> '' AND btrim(broker) <> ''),
    CONSTRAINT "Feature_02_Broker_Rolling_gross_check"
        CHECK (buy_value_1d >= 0 AND sell_value_1d >= 0
           AND buy_lots_1d >= 0 AND sell_lots_1d >= 0),
    CONSTRAINT "Feature_02_Broker_Rolling_net_check"
        CHECK (net_value_1d = buy_value_1d - sell_value_1d
           AND net_lots_1d = buy_lots_1d - sell_lots_1d),
    CONSTRAINT "Feature_02_Broker_Rolling_percentile_check"
        CHECK ((net_value_percentile_20d IS NULL OR net_value_percentile_20d BETWEEN 0 AND 100)
           AND (net_value_percentile_60d IS NULL OR net_value_percentile_60d BETWEEN 0 AND 100)),
    CONSTRAINT "Feature_02_Broker_Rolling_ratio_check"
        CHECK ((buy_day_ratio_20d IS NULL OR buy_day_ratio_20d BETWEEN 0 AND 1)
           AND (buy_share_active_days_20d IS NULL OR buy_share_active_days_20d BETWEEN 0 AND 1)
           AND (buy_day_ratio_60d IS NULL OR buy_day_ratio_60d BETWEEN 0 AND 1)
           AND (buy_share_active_days_60d IS NULL OR buy_share_active_days_60d BETWEEN 0 AND 1)
           AND (largest_buy_day_share_20d IS NULL OR largest_buy_day_share_20d BETWEEN 0 AND 1))
);

COMMENT ON TABLE public."Feature_02_Broker_Rolling" IS
    'Broker flow, persistence, abnormality and quiet accumulation for each source ticker, broker, board and transaction date; board calculations never mix.';

DO $comments$
DECLARE item record;
BEGIN
    FOR item IN
        SELECT * FROM (VALUES
            ('date','Ticker transaction date observed in IDX_Broker_Summary on at least one board.'),
            ('ticker','Source Symbol, including instruments not present in the current stock universe.'),
            ('broker','Source Broker code; Domestic/Foreign investor rows are combined.'),
            ('market_board','Exact source Market Board: Regular, Nego or Tunai; rolling partitions never mix boards.'),
            ('broker_type','Current Domestic/Foreign type from IDX_Broker_Profile; not point-in-time history.'),
            ('broker_classification','Current usage classification from IDX_Broker_Profile; not point-in-time history.'),
            ('buy_value_1d','Sum of source Buy Value across Investor Type on this date, ticker, broker and board.'),
            ('sell_value_1d','Sum of source Sell Value across Investor Type on this date, ticker, broker and board.'),
            ('net_value_1d','buy_value_1d minus sell_value_1d.'),
            ('buy_lots_1d','Sum of source Buy Lots across Investor Type on this date, ticker, broker and board.'),
            ('sell_lots_1d','Sum of source Sell Lots across Investor Type on this date, ticker, broker and board.'),
            ('net_lots_1d','buy_lots_1d minus sell_lots_1d.'),
            ('net_value_5d','Sum of daily net value over five ticker transaction dates; absent broker-board activity contributes zero.'),
            ('net_value_20d','Sum of daily net value over twenty ticker transaction dates; absent broker-board activity contributes zero.'),
            ('net_value_60d','Sum of daily net value over sixty ticker transaction dates; absent broker-board activity contributes zero.'),
            ('net_lots_5d','Sum of daily net lots over five ticker transaction dates.'),
            ('net_lots_20d','Sum of daily net lots over twenty ticker transaction dates.'),
            ('net_lots_60d','Sum of daily net lots over sixty ticker transaction dates.'),
            ('buy_days_20d','Count of positive daily net-value days for this broker and board in twenty ticker transaction dates.'),
            ('sell_days_20d','Count of negative daily net-value days for this broker and board in twenty ticker transaction dates.'),
            ('active_days_20d','Count of days with nonzero gross broker-board activity in twenty ticker transaction dates.'),
            ('stock_trading_days_20d','Twenty observed ticker transaction dates across any board; null before a full window exists.'),
            ('buy_day_ratio_20d','buy_days_20d divided by stock_trading_days_20d.'),
            ('buy_share_active_days_20d','buy_days_20d divided by active_days_20d; null when no active days.'),
            ('buy_days_60d','Count of positive daily net-value days in sixty ticker transaction dates.'),
            ('sell_days_60d','Count of negative daily net-value days in sixty ticker transaction dates.'),
            ('active_days_60d','Count of days with nonzero gross broker-board activity in sixty ticker transaction dates.'),
            ('stock_trading_days_60d','Sixty observed ticker transaction dates across any board; null before a full window exists.'),
            ('buy_day_ratio_60d','buy_days_60d divided by stock_trading_days_60d.'),
            ('buy_share_active_days_60d','buy_days_60d divided by active_days_60d; null when no active days.'),
            ('net_value_zscore_20d','Current twenty-date net flow versus the preceding 252 complete twenty-date flow observations, excluding current date.'),
            ('net_value_zscore_60d','Current sixty-date net flow versus the preceding 252 complete sixty-date flow observations, excluding current date.'),
            ('net_value_percentile_20d','Empirical midrank percentile of current twenty-date net flow against the preceding 252 complete observations.'),
            ('net_value_percentile_60d','Empirical midrank percentile of current sixty-date net flow against the preceding 252 complete observations.'),
            ('positive_net_value_20d','Sum of positive daily net values in the twenty-date window; zero when there are no positive days.'),
            ('largest_buy_day_20d','Largest positive daily net value in the twenty-date window; null when none exists.'),
            ('largest_buy_day_share_20d','Largest positive daily net value divided by positive_net_value_20d; null when denominator is zero.'),
            ('calculated_at','Database timestamp when this validated Feature row was calculated.')
        ) AS definitions(column_name, definition)
    LOOP
        EXECUTE format('COMMENT ON COLUMN public.%I.%I IS %L',
            'Feature_02_Broker_Rolling', item.column_name, item.definition);
    END LOOP;
END
$comments$;

CREATE FUNCTION public.feature_02_empirical_midrank_percentile(
    p_current numeric, p_history numeric[]
)
RETURNS double precision
LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE
AS $function$
DECLARE
    v numeric;
    below_count integer := 0;
    equal_count integer := 0;
BEGIN
    IF cardinality(p_history) <> 252 THEN RETURN NULL; END IF;
    FOREACH v IN ARRAY p_history LOOP
        IF v IS NULL THEN RETURN NULL; END IF;
        IF v < p_current THEN
            below_count := below_count + 1;
        ELSIF v = p_current THEN
            equal_count := equal_count + 1;
        END IF;
    END LOOP;
    RETURN 100.0 * (below_count + equal_count / 2.0) / 252.0;
END
$function$;
COMMENT ON FUNCTION public.feature_02_empirical_midrank_percentile(numeric,numeric[]) IS
    '100*(count(previous < current)+0.5*count(previous = current))/252; returns null without 252 complete prior values.';

INSERT INTO public."Table_Catalog" (
    table_name, category, definition, grain, primary_key_columns,
    source_system, source_tables, source_code_paths, update_rule,
    related_functions, documentation_status
) VALUES (
    'Feature_02_Broker_Rolling', 'Feature',
    'Broker flow, persistence, abnormality and quiet accumulation by ticker, broker, board and transaction date.',
    'One row per date, source Symbol, Broker and Market Board',
    ARRAY['ticker','market_board','broker','date'],
    'Stockbit broker summary and current broker profile',
    ARRAY['IDX_Broker_Summary','IDX_Broker_Profile'],
    ARRAY['database/migrations/20260913_007_create_feature_02_broker_rolling.sql',
          'scripts/backfill_feature_02.py'],
    'Backfilled from all source dates; refresh needed after Broker Summary or Broker Profile changes.',
    ARRAY['feature_02_empirical_midrank_percentile(numeric,numeric[])'],
    'PARTIAL'
);

INSERT INTO public."Column_Catalog" (
    table_schema, table_name, column_name, ordinal_position, data_type,
    is_nullable, default_expression, is_primary_key, definition,
    source_code_paths, documentation_status
)
SELECT c.table_schema, c.table_name, c.column_name, c.ordinal_position,
       c.data_type, c.is_nullable = 'YES', c.column_default,
       c.column_name = ANY(ARRAY['ticker','market_board','broker','date']),
       pg_catalog.col_description(rel.oid, att.attnum),
       ARRAY['database/migrations/20260913_007_create_feature_02_broker_rolling.sql',
             'scripts/backfill_feature_02.py'],
       'PARTIAL'
FROM information_schema.columns c
JOIN pg_catalog.pg_namespace n ON n.nspname = c.table_schema
JOIN pg_catalog.pg_class rel ON rel.relnamespace = n.oid AND rel.relname = c.table_name
JOIN pg_catalog.pg_attribute att ON att.attrelid = rel.oid AND att.attname = c.column_name
WHERE c.table_schema = 'public' AND c.table_name = 'Feature_02_Broker_Rolling';

COMMIT;
