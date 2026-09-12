BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '5min';

DO $migration$
DECLARE
    expected_columns text[] := ARRAY[
        'date', 'ticker', 'close', 'volume', 'sector', 'industry',
        'close_1d_ago', 'close_5d_ago', 'close_20d_ago', 'close_60d_ago',
        'return_1d_pct', 'return_5d_pct', 'return_20d_pct', 'return_60d_pct',
        'abs_return_1d_pct',
        'volatility_5d_ann_pct', 'volatility_20d_ann_pct', 'volatility_60d_ann_pct',
        'volatility_5d_change_pct', 'volatility_20d_change_pct',
        'volatility_60d_change_pct',
        'volume_avg_20d', 'volume_std_20d', 'volume_ratio_20d',
        'volume_zscore_20d', 'high_20d', 'high_60d',
        'drawdown_20d_pct', 'drawdown_60d_pct'
    ];
    actual_columns text[];
BEGIN
    IF to_regclass('public."Feature_Catalog"') IS NOT NULL THEN
        RAISE EXCEPTION
            'public."Feature_Catalog" already exists; migration was not applied';
    END IF;

    IF to_regclass('public."Feature_01_Stock_Daily"') IS NULL THEN
        RAISE EXCEPTION
            'Required validated table public."Feature_01_Stock_Daily" is missing';
    END IF;

    SELECT array_agg(column_name::text ORDER BY ordinal_position)
    INTO actual_columns
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'Feature_01_Stock_Daily';

    IF actual_columns IS DISTINCT FROM expected_columns THEN
        RAISE EXCEPTION
            'Feature_01_Stock_Daily columns differ from the validated v1 contract';
    END IF;
END
$migration$;

CREATE TABLE public."Feature_Catalog" (
    feature_table text NOT NULL,
    feature_column text NOT NULL,
    grain text NOT NULL,
    feature_category text NOT NULL,
    definition text NOT NULL,
    calculation text NOT NULL,
    source_tables text NOT NULL,
    source_columns text NOT NULL,
    lookback_window text NOT NULL,
    minimum_history text NOT NULL,
    unit text NOT NULL,
    null_rule text NOT NULL,
    refresh_trigger text NOT NULL,
    dependency_rule text NOT NULL,
    version text NOT NULL DEFAULT 'v1',
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Feature_Catalog_pkey"
        PRIMARY KEY (feature_table, feature_column, version),
    CONSTRAINT "Feature_Catalog_feature_table_check"
        CHECK (feature_table = ANY (ARRAY[
            'Feature_01_Stock_Daily',
            'Feature_02_Broker_Rolling',
            'Feature_03_Stock_Broker_Daily',
            'Feature_04_Broker_Behavior_Profile'
        ])),
    CONSTRAINT "Feature_Catalog_feature_category_check"
        CHECK (feature_category = ANY (ARRAY[
            'Identity', 'Metadata', 'Price', 'Return', 'Volatility', 'Volume',
            'Price Positioning', 'Broker Flow', 'Broker Persistence',
            'Broker Abnormality', 'Broker Concentration',
            'Broker Classification', 'Historical Outcome', 'Smart Money',
            'Data Quality'
        ])),
    CONSTRAINT "Feature_Catalog_required_text_check"
        CHECK (
            btrim(feature_table) <> ''
            AND btrim(feature_column) <> ''
            AND btrim(grain) <> ''
            AND btrim(feature_category) <> ''
            AND btrim(definition) <> ''
            AND btrim(calculation) <> ''
            AND btrim(source_tables) <> ''
            AND btrim(source_columns) <> ''
            AND btrim(lookback_window) <> ''
            AND btrim(minimum_history) <> ''
            AND btrim(unit) <> ''
            AND btrim(null_rule) <> ''
            AND btrim(refresh_trigger) <> ''
            AND btrim(dependency_rule) <> ''
            AND btrim(version) <> ''
        ),
    CONSTRAINT "Feature_Catalog_version_check"
        CHECK (version ~ '^v[1-9][0-9]*$'),
    CONSTRAINT "Feature_Catalog_timestamps_check"
        CHECK (updated_at >= created_at)
);

COMMENT ON TABLE public."Feature_Catalog" IS
    'Machine-readable semantic contract for validated columns in the four locked Feature tables.';
COMMENT ON COLUMN public."Feature_Catalog".feature_table IS
    'Exact physical name of one of the four locked Feature tables.';
COMMENT ON COLUMN public."Feature_Catalog".feature_column IS
    'Exact physical PostgreSQL column name.';
COMMENT ON COLUMN public."Feature_Catalog".grain IS
    'Business grain represented by one row in the Feature table.';
COMMENT ON COLUMN public."Feature_Catalog".feature_category IS
    'Controlled semantic category for the feature.';
COMMENT ON COLUMN public."Feature_Catalog".definition IS
    'Human-readable meaning of the feature value.';
COMMENT ON COLUMN public."Feature_Catalog".calculation IS
    'Exact formula or ordered calculation logic used by the implementation.';
COMMENT ON COLUMN public."Feature_Catalog".source_tables IS
    'Pipe-delimited exact source-table names required by the calculation.';
COMMENT ON COLUMN public."Feature_Catalog".source_columns IS
    'Pipe-delimited exact source-column references used by the calculation.';
COMMENT ON COLUMN public."Feature_Catalog".lookback_window IS
    'Effective observation-based historical window.';
COMMENT ON COLUMN public."Feature_Catalog".minimum_history IS
    'Minimum valid observation history required for a usable value.';
COMMENT ON COLUMN public."Feature_Catalog".unit IS
    'Semantic unit of the feature value.';
COMMENT ON COLUMN public."Feature_Catalog".null_rule IS
    'Conditions under which the feature is NULL.';
COMMENT ON COLUMN public."Feature_Catalog".refresh_trigger IS
    'Upstream event that requires the feature to be recalculated.';
COMMENT ON COLUMN public."Feature_Catalog".dependency_rule IS
    'Upstream availability conditions required before the feature is valid.';
COMMENT ON COLUMN public."Feature_Catalog".version IS
    'Semantic-definition version; material formula changes require a new version.';
COMMENT ON COLUMN public."Feature_Catalog".is_active IS
    'Whether AI analytics may use this catalog definition.';
COMMENT ON COLUMN public."Feature_Catalog".created_at IS
    'Timestamp when this semantic version was created.';
COMMENT ON COLUMN public."Feature_Catalog".updated_at IS
    'Timestamp of the latest metadata change, maintained by trigger.';

CREATE FUNCTION public.set_feature_catalog_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    NEW.updated_at := CURRENT_TIMESTAMP;
    RETURN NEW;
END
$function$;

CREATE FUNCTION public.validate_feature_catalog_target()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    IF NEW.is_active
       AND NOT EXISTS (
           SELECT 1
           FROM information_schema.columns
           WHERE table_schema = 'public'
             AND table_name = NEW.feature_table
             AND column_name = NEW.feature_column
       ) THEN
        RAISE EXCEPTION
            'Active catalog target %.% does not exist in schema public',
            NEW.feature_table,
            NEW.feature_column;
    END IF;

    RETURN NEW;
END
$function$;

CREATE TRIGGER "Feature_Catalog_set_updated_at"
BEFORE UPDATE ON public."Feature_Catalog"
FOR EACH ROW
EXECUTE FUNCTION public.set_feature_catalog_updated_at();

CREATE TRIGGER "Feature_Catalog_validate_target"
BEFORE INSERT OR UPDATE OF feature_table, feature_column, is_active
ON public."Feature_Catalog"
FOR EACH ROW
EXECUTE FUNCTION public.validate_feature_catalog_target();

INSERT INTO public."Feature_Catalog" (
    feature_table,
    feature_column,
    grain,
    feature_category,
    definition,
    calculation,
    source_tables,
    source_columns,
    lookback_window,
    minimum_history,
    unit,
    null_rule,
    refresh_trigger,
    dependency_rule,
    version,
    is_active
)
VALUES
    (
        'Feature_01_Stock_Daily', 'date', 'Date × Ticker', 'Identity',
        'Trading date of the source candle represented by the feature row.',
        'Direct copy of Price_Stock_Indonesia_IDX.date after matching the price ticker to IDX_Stock_Universe.',
        'Price_Stock_Indonesia_IDX | IDX_Stock_Universe',
        'Price_Stock_Indonesia_IDX.date | Price_Stock_Indonesia_IDX.ticker | IDX_Stock_Universe."Ticker"',
        'None', '1 valid price candle with a matching stock-universe ticker',
        'Date',
        'Never NULL for a stored row; no row is created without a valid source candle and matching universe ticker.',
        'Price feed update',
        'Requires Price_Stock_Indonesia_IDX and a matching current IDX_Stock_Universe ticker.',
        'v1', true
    ),
    (
        'Feature_01_Stock_Daily', 'ticker', 'Date × Ticker', 'Identity',
        'Exact IDX ticker identifying the security represented by the feature row.',
        'Direct copy of Price_Stock_Indonesia_IDX.ticker after an exact match to IDX_Stock_Universe."Ticker".',
        'Price_Stock_Indonesia_IDX | IDX_Stock_Universe',
        'Price_Stock_Indonesia_IDX.ticker | IDX_Stock_Universe."Ticker"',
        'None', '1 valid price candle with a matching stock-universe ticker',
        'Ticker',
        'Never NULL for a stored row; blank tickers and source tickers without a universe match are rejected.',
        'Price feed update',
        'Requires Price_Stock_Indonesia_IDX and a matching current IDX_Stock_Universe ticker.',
        'v1', true
    ),
    (
        'Feature_01_Stock_Daily', 'close', 'Date × Ticker', 'Price',
        'Closing price for the ticker on the trading date.',
        'Direct copy of Price_Stock_Indonesia_IDX.close.',
        'Price_Stock_Indonesia_IDX',
        'Price_Stock_Indonesia_IDX.ticker | Price_Stock_Indonesia_IDX.date | Price_Stock_Indonesia_IDX.close',
        'Current trading observation', '1 valid trading observation',
        'IDR',
        'Never NULL for a stored row; source close must exist and be nonnegative.',
        'Price feed update',
        'Requires Price_Stock_Indonesia_IDX through the feature date and a matching current IDX_Stock_Universe ticker.',
        'v1', true
    ),
    (
        'Feature_01_Stock_Daily', 'volume', 'Date × Ticker', 'Volume',
        'Trading volume reported for the ticker on the trading date.',
        'Direct copy of Price_Stock_Indonesia_IDX.volume.',
        'Price_Stock_Indonesia_IDX',
        'Price_Stock_Indonesia_IDX.ticker | Price_Stock_Indonesia_IDX.date | Price_Stock_Indonesia_IDX.volume',
        'Current trading observation', '1 valid trading observation',
        'Shares',
        'Never NULL for a stored row; source volume must exist and be nonnegative.',
        'Price feed update',
        'Requires Price_Stock_Indonesia_IDX through the feature date and a matching current IDX_Stock_Universe ticker.',
        'v1', true
    ),
    (
        'Feature_01_Stock_Daily', 'sector', 'Date × Ticker', 'Metadata',
        'Current Sector classification for the ticker; it is not point-in-time historical classification.',
        'Direct copy of IDX_Stock_Universe."Sector" using Feature ticker = IDX_Stock_Universe."Ticker".',
        'IDX_Stock_Universe',
        'IDX_Stock_Universe."Ticker" | IDX_Stock_Universe."Sector"',
        'None', '1 matching current stock-universe row',
        'Category',
        'Never NULL for a stored row; the current universe ticker and Sector must exist.',
        'Stock Universe update',
        'Requires a matching current IDX_Stock_Universe row; a universe classification change requires refresh of affected Feature rows.',
        'v1', true
    ),
    (
        'Feature_01_Stock_Daily', 'industry', 'Date × Ticker', 'Metadata',
        'Current Industry classification for the ticker; it is not point-in-time historical classification.',
        'Direct copy of IDX_Stock_Universe."Industry" using Feature ticker = IDX_Stock_Universe."Ticker".',
        'IDX_Stock_Universe',
        'IDX_Stock_Universe."Ticker" | IDX_Stock_Universe."Industry"',
        'None', '1 matching current stock-universe row',
        'Category',
        'Never NULL for a stored row; the current universe ticker and Industry must exist.',
        'Stock Universe update',
        'Requires a matching current IDX_Stock_Universe row; a universe classification change requires refresh of affected Feature rows.',
        'v1', true
    ),
    (
        'Feature_01_Stock_Daily', 'close_1d_ago', 'Date × Ticker', 'Price',
        'Closing price one prior valid trading observation earlier for the same ticker.',
        'LAG(close, 1) OVER (PARTITION BY ticker ORDER BY date).',
        'Price_Stock_Indonesia_IDX',
        'Price_Stock_Indonesia_IDX.ticker | Price_Stock_Indonesia_IDX.date | Price_Stock_Indonesia_IDX.close',
        '1 prior trading observation', '2 valid trading observations including current observation',
        'IDR',
        'NULL when fewer than 2 valid trading observations exist for the ticker.',
        'Price feed update',
        'Requires complete ordered Price_Stock_Indonesia_IDX history through the feature date and a matching current universe ticker.',
        'v1', true
    ),
    (
        'Feature_01_Stock_Daily', 'close_5d_ago', 'Date × Ticker', 'Price',
        'Closing price five prior valid trading observations earlier for the same ticker.',
        'LAG(close, 5) OVER (PARTITION BY ticker ORDER BY date).',
        'Price_Stock_Indonesia_IDX',
        'Price_Stock_Indonesia_IDX.ticker | Price_Stock_Indonesia_IDX.date | Price_Stock_Indonesia_IDX.close',
        '5 prior trading observations', '6 valid trading observations including current observation',
        'IDR',
        'NULL when fewer than 6 valid trading observations exist for the ticker.',
        'Price feed update',
        'Requires complete ordered Price_Stock_Indonesia_IDX history through the feature date and a matching current universe ticker.',
        'v1', true
    ),
    (
        'Feature_01_Stock_Daily', 'close_20d_ago', 'Date × Ticker', 'Price',
        'Closing price twenty prior valid trading observations earlier for the same ticker.',
        'LAG(close, 20) OVER (PARTITION BY ticker ORDER BY date).',
        'Price_Stock_Indonesia_IDX',
        'Price_Stock_Indonesia_IDX.ticker | Price_Stock_Indonesia_IDX.date | Price_Stock_Indonesia_IDX.close',
        '20 prior trading observations', '21 valid trading observations including current observation',
        'IDR',
        'NULL when fewer than 21 valid trading observations exist for the ticker.',
        'Price feed update',
        'Requires complete ordered Price_Stock_Indonesia_IDX history through the feature date and a matching current universe ticker.',
        'v1', true
    ),
    (
        'Feature_01_Stock_Daily', 'close_60d_ago', 'Date × Ticker', 'Price',
        'Closing price sixty prior valid trading observations earlier for the same ticker.',
        'LAG(close, 60) OVER (PARTITION BY ticker ORDER BY date).',
        'Price_Stock_Indonesia_IDX',
        'Price_Stock_Indonesia_IDX.ticker | Price_Stock_Indonesia_IDX.date | Price_Stock_Indonesia_IDX.close',
        '60 prior trading observations', '61 valid trading observations including current observation',
        'IDR',
        'NULL when fewer than 61 valid trading observations exist for the ticker.',
        'Price feed update',
        'Requires complete ordered Price_Stock_Indonesia_IDX history through the feature date and a matching current universe ticker.',
        'v1', true
    ),
    (
        'Feature_01_Stock_Daily', 'return_1d_pct', 'Date × Ticker', 'Return',
        'Percentage price return between the current close and the close one valid trading observation earlier for the same ticker.',
        '(close / NULLIF(close_1d_ago, 0) - 1) * 100.',
        'Price_Stock_Indonesia_IDX',
        'Price_Stock_Indonesia_IDX.ticker | Price_Stock_Indonesia_IDX.date | Price_Stock_Indonesia_IDX.close',
        '1 prior trading observation', '2 valid trading observations including current observation',
        'Percent',
        'NULL when the prior close is unavailable or equals zero.',
        'Price feed update',
        'Requires complete ordered Price_Stock_Indonesia_IDX history through the feature date and a matching current universe ticker.',
        'v1', true
    ),
    (
        'Feature_01_Stock_Daily', 'return_5d_pct', 'Date × Ticker', 'Return',
        'Percentage price return between the current close and the close five valid trading observations earlier for the same ticker.',
        '(close / NULLIF(close_5d_ago, 0) - 1) * 100.',
        'Price_Stock_Indonesia_IDX',
        'Price_Stock_Indonesia_IDX.ticker | Price_Stock_Indonesia_IDX.date | Price_Stock_Indonesia_IDX.close',
        '5 prior trading observations', '6 valid trading observations including current observation',
        'Percent',
        'NULL when the five-observation-prior close is unavailable or equals zero.',
        'Price feed update',
        'Requires complete ordered Price_Stock_Indonesia_IDX history through the feature date and a matching current universe ticker.',
        'v1', true
    ),
    (
        'Feature_01_Stock_Daily', 'return_20d_pct', 'Date × Ticker', 'Return',
        'Percentage price return between the current close and the close twenty valid trading observations earlier for the same ticker.',
        '(close / NULLIF(close_20d_ago, 0) - 1) * 100.',
        'Price_Stock_Indonesia_IDX',
        'Price_Stock_Indonesia_IDX.ticker | Price_Stock_Indonesia_IDX.date | Price_Stock_Indonesia_IDX.close',
        '20 prior trading observations', '21 valid trading observations including current observation',
        'Percent',
        'NULL when the twenty-observation-prior close is unavailable or equals zero.',
        'Price feed update',
        'Requires complete ordered Price_Stock_Indonesia_IDX history through the feature date and a matching current universe ticker.',
        'v1', true
    ),
    (
        'Feature_01_Stock_Daily', 'return_60d_pct', 'Date × Ticker', 'Return',
        'Percentage price return between the current close and the close sixty valid trading observations earlier for the same ticker.',
        '(close / NULLIF(close_60d_ago, 0) - 1) * 100.',
        'Price_Stock_Indonesia_IDX',
        'Price_Stock_Indonesia_IDX.ticker | Price_Stock_Indonesia_IDX.date | Price_Stock_Indonesia_IDX.close',
        '60 prior trading observations', '61 valid trading observations including current observation',
        'Percent',
        'NULL when the sixty-observation-prior close is unavailable or equals zero.',
        'Price feed update',
        'Requires complete ordered Price_Stock_Indonesia_IDX history through the feature date and a matching current universe ticker.',
        'v1', true
    ),
    (
        'Feature_01_Stock_Daily', 'abs_return_1d_pct', 'Date × Ticker', 'Return',
        'Absolute magnitude of the one-trading-observation percentage return, without direction.',
        'ABS(return_1d_pct).',
        'Price_Stock_Indonesia_IDX',
        'Price_Stock_Indonesia_IDX.ticker | Price_Stock_Indonesia_IDX.date | Price_Stock_Indonesia_IDX.close',
        '1 prior trading observation', '2 valid trading observations including current observation',
        'Percent',
        'NULL when return_1d_pct is NULL because the prior close is unavailable or equals zero.',
        'Price feed update',
        'Requires complete ordered Price_Stock_Indonesia_IDX history through the feature date and a matching current universe ticker.',
        'v1', true
    ),
    (
        'Feature_01_Stock_Daily', 'volatility_5d_ann_pct', 'Date × Ticker', 'Volatility',
        'Annualized sample standard deviation of the latest five valid daily decimal returns for the ticker, expressed as percent.',
        'When 5 daily returns exist: STDDEV_SAMP(close / LAG(close, 1) - 1) over the current and 4 preceding return rows * SQRT(252) * 100.',
        'Price_Stock_Indonesia_IDX',
        'Price_Stock_Indonesia_IDX.ticker | Price_Stock_Indonesia_IDX.date | Price_Stock_Indonesia_IDX.close',
        '5 daily returns ending at current observation', '6 valid trading observations including current observation',
        'Percent',
        'NULL when fewer than 5 valid daily returns exist in the window.',
        'Price feed update',
        'Requires complete ordered Price_Stock_Indonesia_IDX history through the feature date and a matching current universe ticker.',
        'v1', true
    ),
    (
        'Feature_01_Stock_Daily', 'volatility_20d_ann_pct', 'Date × Ticker', 'Volatility',
        'Annualized sample standard deviation of the latest twenty valid daily decimal returns for the ticker, expressed as percent.',
        'When 20 daily returns exist: STDDEV_SAMP(close / LAG(close, 1) - 1) over the current and 19 preceding return rows * SQRT(252) * 100.',
        'Price_Stock_Indonesia_IDX',
        'Price_Stock_Indonesia_IDX.ticker | Price_Stock_Indonesia_IDX.date | Price_Stock_Indonesia_IDX.close',
        '20 daily returns ending at current observation', '21 valid trading observations including current observation',
        'Percent',
        'NULL when fewer than 20 valid daily returns exist in the window.',
        'Price feed update',
        'Requires complete ordered Price_Stock_Indonesia_IDX history through the feature date and a matching current universe ticker.',
        'v1', true
    ),
    (
        'Feature_01_Stock_Daily', 'volatility_60d_ann_pct', 'Date × Ticker', 'Volatility',
        'Annualized sample standard deviation of the latest sixty valid daily decimal returns for the ticker, expressed as percent.',
        'When 60 daily returns exist: STDDEV_SAMP(close / LAG(close, 1) - 1) over the current and 59 preceding return rows * SQRT(252) * 100.',
        'Price_Stock_Indonesia_IDX',
        'Price_Stock_Indonesia_IDX.ticker | Price_Stock_Indonesia_IDX.date | Price_Stock_Indonesia_IDX.close',
        '60 daily returns ending at current observation', '61 valid trading observations including current observation',
        'Percent',
        'NULL when fewer than 60 valid daily returns exist in the window.',
        'Price feed update',
        'Requires complete ordered Price_Stock_Indonesia_IDX history through the feature date and a matching current universe ticker.',
        'v1', true
    ),
    (
        'Feature_01_Stock_Daily', 'volatility_5d_change_pct', 'Date × Ticker', 'Volatility',
        'Percentage change in annualized five-return volatility versus its value five valid trading observations earlier.',
        '(volatility_5d_ann_pct / NULLIF(LAG(volatility_5d_ann_pct, 5) OVER (PARTITION BY ticker ORDER BY date), 0) - 1) * 100.',
        'Price_Stock_Indonesia_IDX',
        'Price_Stock_Indonesia_IDX.ticker | Price_Stock_Indonesia_IDX.date | Price_Stock_Indonesia_IDX.close',
        'Current 5-return window plus the comparable volatility 5 observations earlier',
        '11 valid trading observations including current observation',
        'Percent',
        'NULL when current or five-observation-prior volatility is unavailable, or prior volatility equals zero.',
        'Price feed update',
        'Requires complete ordered Price_Stock_Indonesia_IDX history through the feature date and a matching current universe ticker.',
        'v1', true
    ),
    (
        'Feature_01_Stock_Daily', 'volatility_20d_change_pct', 'Date × Ticker', 'Volatility',
        'Percentage change in annualized twenty-return volatility versus its value twenty valid trading observations earlier.',
        '(volatility_20d_ann_pct / NULLIF(LAG(volatility_20d_ann_pct, 20) OVER (PARTITION BY ticker ORDER BY date), 0) - 1) * 100.',
        'Price_Stock_Indonesia_IDX',
        'Price_Stock_Indonesia_IDX.ticker | Price_Stock_Indonesia_IDX.date | Price_Stock_Indonesia_IDX.close',
        'Current 20-return window plus the comparable volatility 20 observations earlier',
        '41 valid trading observations including current observation',
        'Percent',
        'NULL when current or twenty-observation-prior volatility is unavailable, or prior volatility equals zero.',
        'Price feed update',
        'Requires complete ordered Price_Stock_Indonesia_IDX history through the feature date and a matching current universe ticker.',
        'v1', true
    ),
    (
        'Feature_01_Stock_Daily', 'volatility_60d_change_pct', 'Date × Ticker', 'Volatility',
        'Percentage change in annualized sixty-return volatility versus its value sixty valid trading observations earlier.',
        '(volatility_60d_ann_pct / NULLIF(LAG(volatility_60d_ann_pct, 60) OVER (PARTITION BY ticker ORDER BY date), 0) - 1) * 100.',
        'Price_Stock_Indonesia_IDX',
        'Price_Stock_Indonesia_IDX.ticker | Price_Stock_Indonesia_IDX.date | Price_Stock_Indonesia_IDX.close',
        'Current 60-return window plus the comparable volatility 60 observations earlier',
        '121 valid trading observations including current observation',
        'Percent',
        'NULL when current or sixty-observation-prior volatility is unavailable, or prior volatility equals zero.',
        'Price feed update',
        'Requires complete ordered Price_Stock_Indonesia_IDX history through the feature date and a matching current universe ticker.',
        'v1', true
    ),
    (
        'Feature_01_Stock_Daily', 'volume_avg_20d', 'Date × Ticker', 'Volume',
        'Average source trading volume over the latest twenty valid trading observations for the ticker.',
        'When 20 volume observations exist: AVG(volume) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW).',
        'Price_Stock_Indonesia_IDX',
        'Price_Stock_Indonesia_IDX.ticker | Price_Stock_Indonesia_IDX.date | Price_Stock_Indonesia_IDX.volume',
        '20 trading observations including current observation', '20 valid trading observations including current observation',
        'Shares',
        'NULL when fewer than 20 valid volume observations exist in the window.',
        'Price feed update',
        'Requires complete ordered Price_Stock_Indonesia_IDX history through the feature date and a matching current universe ticker.',
        'v1', true
    ),
    (
        'Feature_01_Stock_Daily', 'volume_std_20d', 'Date × Ticker', 'Volume',
        'Sample standard deviation of source trading volume over the latest twenty valid trading observations for the ticker.',
        'When 20 volume observations exist: STDDEV_SAMP(volume) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW).',
        'Price_Stock_Indonesia_IDX',
        'Price_Stock_Indonesia_IDX.ticker | Price_Stock_Indonesia_IDX.date | Price_Stock_Indonesia_IDX.volume',
        '20 trading observations including current observation', '20 valid trading observations including current observation',
        'Shares',
        'NULL when fewer than 20 valid volume observations exist in the window.',
        'Price feed update',
        'Requires complete ordered Price_Stock_Indonesia_IDX history through the feature date and a matching current universe ticker.',
        'v1', true
    ),
    (
        'Feature_01_Stock_Daily', 'volume_ratio_20d', 'Date × Ticker', 'Volume',
        'Current trading volume divided by the average volume of the latest twenty valid trading observations.',
        'volume / NULLIF(volume_avg_20d, 0).',
        'Price_Stock_Indonesia_IDX',
        'Price_Stock_Indonesia_IDX.ticker | Price_Stock_Indonesia_IDX.date | Price_Stock_Indonesia_IDX.volume',
        '20 trading observations including current observation', '20 valid trading observations including current observation',
        'Ratio',
        'NULL when fewer than 20 valid volume observations exist or the 20-observation average volume equals zero.',
        'Price feed update',
        'Requires complete ordered Price_Stock_Indonesia_IDX history through the feature date and a matching current universe ticker.',
        'v1', true
    ),
    (
        'Feature_01_Stock_Daily', 'volume_zscore_20d', 'Date × Ticker', 'Volume',
        'Current trading-volume deviation from its latest twenty-observation average, measured in sample standard deviations.',
        '(volume - volume_avg_20d) / NULLIF(volume_std_20d, 0).',
        'Price_Stock_Indonesia_IDX',
        'Price_Stock_Indonesia_IDX.ticker | Price_Stock_Indonesia_IDX.date | Price_Stock_Indonesia_IDX.volume',
        '20 trading observations including current observation', '20 valid trading observations including current observation',
        'Z-score',
        'NULL when fewer than 20 valid volume observations exist or the 20-observation sample standard deviation equals zero.',
        'Price feed update',
        'Requires complete ordered Price_Stock_Indonesia_IDX history through the feature date and a matching current universe ticker.',
        'v1', true
    ),
    (
        'Feature_01_Stock_Daily', 'high_20d', 'Date × Ticker', 'Price Positioning',
        'Highest closing price among the latest twenty valid trading observations for the ticker.',
        'When 20 close observations exist: MAX(close) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW).',
        'Price_Stock_Indonesia_IDX',
        'Price_Stock_Indonesia_IDX.ticker | Price_Stock_Indonesia_IDX.date | Price_Stock_Indonesia_IDX.close',
        '20 trading observations including current observation', '20 valid trading observations including current observation',
        'IDR',
        'NULL when fewer than 20 valid close observations exist in the window.',
        'Price feed update',
        'Requires complete ordered Price_Stock_Indonesia_IDX history through the feature date and a matching current universe ticker.',
        'v1', true
    ),
    (
        'Feature_01_Stock_Daily', 'high_60d', 'Date × Ticker', 'Price Positioning',
        'Highest closing price among the latest sixty valid trading observations for the ticker.',
        'When 60 close observations exist: MAX(close) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW).',
        'Price_Stock_Indonesia_IDX',
        'Price_Stock_Indonesia_IDX.ticker | Price_Stock_Indonesia_IDX.date | Price_Stock_Indonesia_IDX.close',
        '60 trading observations including current observation', '60 valid trading observations including current observation',
        'IDR',
        'NULL when fewer than 60 valid close observations exist in the window.',
        'Price feed update',
        'Requires complete ordered Price_Stock_Indonesia_IDX history through the feature date and a matching current universe ticker.',
        'v1', true
    ),
    (
        'Feature_01_Stock_Daily', 'drawdown_20d_pct', 'Date × Ticker', 'Price Positioning',
        'Percentage position of the current close below the highest close in the latest twenty valid trading observations.',
        '(close / NULLIF(high_20d, 0) - 1) * 100.',
        'Price_Stock_Indonesia_IDX',
        'Price_Stock_Indonesia_IDX.ticker | Price_Stock_Indonesia_IDX.date | Price_Stock_Indonesia_IDX.close',
        '20 trading observations including current observation', '20 valid trading observations including current observation',
        'Percent',
        'NULL when fewer than 20 valid close observations exist or high_20d equals zero.',
        'Price feed update',
        'Requires complete ordered Price_Stock_Indonesia_IDX history through the feature date and a matching current universe ticker.',
        'v1', true
    ),
    (
        'Feature_01_Stock_Daily', 'drawdown_60d_pct', 'Date × Ticker', 'Price Positioning',
        'Percentage position of the current close below the highest close in the latest sixty valid trading observations.',
        '(close / NULLIF(high_60d, 0) - 1) * 100.',
        'Price_Stock_Indonesia_IDX',
        'Price_Stock_Indonesia_IDX.ticker | Price_Stock_Indonesia_IDX.date | Price_Stock_Indonesia_IDX.close',
        '60 trading observations including current observation', '60 valid trading observations including current observation',
        'Percent',
        'NULL when fewer than 60 valid close observations exist or high_60d equals zero.',
        'Price feed update',
        'Requires complete ordered Price_Stock_Indonesia_IDX history through the feature date and a matching current universe ticker.',
        'v1', true
    );

DO $validation$
DECLARE
    physical_count integer;
    active_count integer;
    missing_count integer;
    broken_count integer;
BEGIN
    SELECT count(*)
    INTO physical_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'Feature_01_Stock_Daily';

    SELECT count(*)
    INTO active_count
    FROM public."Feature_Catalog"
    WHERE feature_table = 'Feature_01_Stock_Daily'
      AND version = 'v1'
      AND is_active;

    SELECT count(*)
    INTO missing_count
    FROM information_schema.columns AS columns
    WHERE columns.table_schema = 'public'
      AND columns.table_name = 'Feature_01_Stock_Daily'
      AND NOT EXISTS (
          SELECT 1
          FROM public."Feature_Catalog" AS catalog
          WHERE catalog.feature_table = columns.table_name
            AND catalog.feature_column = columns.column_name
            AND catalog.is_active
      );

    SELECT count(*)
    INTO broken_count
    FROM public."Feature_Catalog" AS catalog
    WHERE catalog.is_active
      AND NOT EXISTS (
          SELECT 1
          FROM information_schema.columns AS columns
          WHERE columns.table_schema = 'public'
            AND columns.table_name = catalog.feature_table
            AND columns.column_name = catalog.feature_column
      );

    IF physical_count <> 29
       OR active_count <> 29
       OR missing_count <> 0
       OR broken_count <> 0 THEN
        RAISE EXCEPTION
            'Feature Catalog validation failed: physical %, active %, missing %, broken %',
            physical_count,
            active_count,
            missing_count,
            broken_count;
    END IF;
END
$validation$;

COMMIT;
