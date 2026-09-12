BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30min';

DO $migration$
BEGIN
    IF to_regclass('public."Feature_01_Stock_Daily"') IS NOT NULL THEN
        RAISE EXCEPTION
            'public."Feature_01_Stock_Daily" already exists; migration was not applied';
    END IF;

    IF to_regclass('public."Price_Stock_Indonesia_IDX"') IS NULL
       OR to_regclass('public."IDX_Stock_Universe"') IS NULL THEN
        RAISE EXCEPTION
            'Required source table Price_Stock_Indonesia_IDX or IDX_Stock_Universe is missing';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM public."Price_Stock_Indonesia_IDX" AS price
        LEFT JOIN public."IDX_Stock_Universe" AS universe
          ON universe."Ticker" = price.ticker
        WHERE universe."Ticker" IS NULL
    ) THEN
        RAISE EXCEPTION
            'Price source contains ticker(s) missing from IDX_Stock_Universe';
    END IF;
END
$migration$;

CREATE TABLE public."Feature_01_Stock_Daily" (
    date date NOT NULL,
    ticker text NOT NULL,
    close numeric NOT NULL,
    volume numeric NOT NULL,
    sector text NOT NULL,
    industry text NOT NULL,
    close_1d_ago numeric,
    close_5d_ago numeric,
    close_20d_ago numeric,
    close_60d_ago numeric,
    return_1d_pct double precision,
    return_5d_pct double precision,
    return_20d_pct double precision,
    return_60d_pct double precision,
    abs_return_1d_pct double precision,
    volatility_5d_ann_pct double precision,
    volatility_20d_ann_pct double precision,
    volatility_60d_ann_pct double precision,
    volatility_5d_change_pct double precision,
    volatility_20d_change_pct double precision,
    volatility_60d_change_pct double precision,
    volume_avg_20d double precision,
    volume_std_20d double precision,
    volume_ratio_20d double precision,
    volume_zscore_20d double precision,
    high_20d numeric,
    high_60d numeric,
    drawdown_20d_pct double precision,
    drawdown_60d_pct double precision,
    CONSTRAINT "Feature_01_Stock_Daily_pkey" PRIMARY KEY (ticker, date),
    CONSTRAINT "Feature_01_Stock_Daily_ticker_not_blank"
        CHECK (btrim(ticker) <> ''),
    CONSTRAINT "Feature_01_Stock_Daily_close_nonnegative"
        CHECK (close >= 0),
    CONSTRAINT "Feature_01_Stock_Daily_volume_nonnegative"
        CHECK (volume >= 0)
);

COMMENT ON TABLE public."Feature_01_Stock_Daily" IS
    'Daily ticker-level price, return, volatility, volume, and price-position features derived from IDX prices and the current stock universe.';
COMMENT ON COLUMN public."Feature_01_Stock_Daily".date IS
    'Trading observation date from Price_Stock_Indonesia_IDX.';
COMMENT ON COLUMN public."Feature_01_Stock_Daily".ticker IS
    'IDX ticker; feature grain is one row per ticker and trading date.';
COMMENT ON COLUMN public."Feature_01_Stock_Daily".sector IS
    'Current Sector value inherited exactly from IDX_Stock_Universe.';
COMMENT ON COLUMN public."Feature_01_Stock_Daily".industry IS
    'Current Industry value inherited exactly from IDX_Stock_Universe.';

CREATE OR REPLACE FUNCTION public.refresh_feature_01_stock_daily(
    p_changed_date date DEFAULT NULL,
    p_tickers text[] DEFAULT NULL
)
RETURNS bigint
LANGUAGE plpgsql
AS $function$
DECLARE
    affected_rows bigint := 0;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtext('public.Feature_01_Stock_Daily.refresh'));

    IF p_tickers IS NOT NULL
       AND EXISTS (
           SELECT 1
           FROM unnest(p_tickers) AS requested(ticker)
           WHERE requested.ticker IS NULL OR btrim(requested.ticker) = ''
       ) THEN
        RAISE EXCEPTION 'p_tickers cannot contain NULL or blank values';
    END IF;

    IF p_tickers IS NOT NULL AND cardinality(p_tickers) = 0 THEN
        RETURN 0;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM public."Price_Stock_Indonesia_IDX" AS price
        LEFT JOIN public."IDX_Stock_Universe" AS universe
          ON universe."Ticker" = price.ticker
        WHERE (p_tickers IS NULL OR price.ticker = ANY(p_tickers))
          AND universe."Ticker" IS NULL
    ) THEN
        RAISE EXCEPTION
            'Selected price ticker(s) are missing from IDX_Stock_Universe';
    END IF;

    INSERT INTO public."Feature_01_Stock_Daily" (
        date,
        ticker,
        close,
        volume,
        sector,
        industry,
        close_1d_ago,
        close_5d_ago,
        close_20d_ago,
        close_60d_ago,
        return_1d_pct,
        return_5d_pct,
        return_20d_pct,
        return_60d_pct,
        abs_return_1d_pct,
        volatility_5d_ann_pct,
        volatility_20d_ann_pct,
        volatility_60d_ann_pct,
        volatility_5d_change_pct,
        volatility_20d_change_pct,
        volatility_60d_change_pct,
        volume_avg_20d,
        volume_std_20d,
        volume_ratio_20d,
        volume_zscore_20d,
        high_20d,
        high_60d,
        drawdown_20d_pct,
        drawdown_60d_pct
    )
    WITH source_rows AS (
        SELECT
            price.date,
            price.ticker::text AS ticker,
            price.close,
            price.volume,
            universe."Sector" AS sector,
            universe."Industry" AS industry
        FROM public."Price_Stock_Indonesia_IDX" AS price
        JOIN public."IDX_Stock_Universe" AS universe
          ON universe."Ticker" = price.ticker
        WHERE p_tickers IS NULL OR price.ticker = ANY(p_tickers)
    ),
    lagged AS (
        SELECT
            source_rows.*,
            row_number() OVER ticker_window AS observation_number,
            lag(close, 1) OVER ticker_window AS close_1d_ago,
            lag(close, 5) OVER ticker_window AS close_5d_ago,
            lag(close, 20) OVER ticker_window AS close_20d_ago,
            lag(close, 60) OVER ticker_window AS close_60d_ago
        FROM source_rows
        WINDOW ticker_window AS (PARTITION BY ticker ORDER BY date)
    ),
    return_metrics AS (
        SELECT
            lagged.*,
            close::double precision
                / NULLIF(close_1d_ago::double precision, 0.0) - 1.0
                AS daily_return_decimal,
            (close::double precision
                / NULLIF(close_1d_ago::double precision, 0.0) - 1.0) * 100.0
                AS return_1d_pct,
            (close::double precision
                / NULLIF(close_5d_ago::double precision, 0.0) - 1.0) * 100.0
                AS return_5d_pct,
            (close::double precision
                / NULLIF(close_20d_ago::double precision, 0.0) - 1.0) * 100.0
                AS return_20d_pct,
            (close::double precision
                / NULLIF(close_60d_ago::double precision, 0.0) - 1.0) * 100.0
                AS return_60d_pct
        FROM lagged
    ),
    rolling AS (
        SELECT
            return_metrics.*,
            count(daily_return_decimal) OVER return_window_5d AS return_count_5d,
            count(daily_return_decimal) OVER return_window_20d AS return_count_20d,
            count(daily_return_decimal) OVER return_window_60d AS return_count_60d,
            stddev_samp(daily_return_decimal) OVER return_window_5d
                AS daily_return_std_5d,
            stddev_samp(daily_return_decimal) OVER return_window_20d
                AS daily_return_std_20d,
            stddev_samp(daily_return_decimal) OVER return_window_60d
                AS daily_return_std_60d,
            count(volume) OVER return_window_20d AS volume_count_20d,
            avg(volume::double precision) OVER return_window_20d AS volume_avg_20d_raw,
            stddev_samp(volume::double precision) OVER return_window_20d
                AS volume_std_20d_raw,
            count(close) OVER return_window_20d AS close_count_20d,
            count(close) OVER return_window_60d AS close_count_60d,
            max(close) OVER return_window_20d AS high_20d_raw,
            max(close) OVER return_window_60d AS high_60d_raw
        FROM return_metrics
        WINDOW
            return_window_5d AS (
                PARTITION BY ticker ORDER BY date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
            ),
            return_window_20d AS (
                PARTITION BY ticker ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
            ),
            return_window_60d AS (
                PARTITION BY ticker ORDER BY date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW
            )
    ),
    window_metrics AS (
        SELECT
            rolling.*,
            CASE WHEN return_count_5d = 5
                 THEN daily_return_std_5d * sqrt(252.0::double precision) * 100.0
            END AS volatility_5d_ann_pct,
            CASE WHEN return_count_20d = 20
                 THEN daily_return_std_20d * sqrt(252.0::double precision) * 100.0
            END AS volatility_20d_ann_pct,
            CASE WHEN return_count_60d = 60
                 THEN daily_return_std_60d * sqrt(252.0::double precision) * 100.0
            END AS volatility_60d_ann_pct,
            CASE WHEN volume_count_20d = 20 THEN volume_avg_20d_raw END
                AS volume_avg_20d,
            CASE WHEN volume_count_20d = 20 THEN volume_std_20d_raw END
                AS volume_std_20d,
            CASE WHEN close_count_20d = 20 THEN high_20d_raw END AS high_20d,
            CASE WHEN close_count_60d = 60 THEN high_60d_raw END AS high_60d
        FROM rolling
    ),
    with_volatility_history AS (
        SELECT
            window_metrics.*,
            lag(volatility_5d_ann_pct, 5) OVER ticker_window
                AS volatility_5d_ago,
            lag(volatility_20d_ann_pct, 20) OVER ticker_window
                AS volatility_20d_ago,
            lag(volatility_60d_ann_pct, 60) OVER ticker_window
                AS volatility_60d_ago
        FROM window_metrics
        WINDOW ticker_window AS (PARTITION BY ticker ORDER BY date)
    ),
    target_bounds AS (
        SELECT ticker, min(observation_number) AS first_target_observation
        FROM with_volatility_history
        WHERE p_changed_date IS NOT NULL AND date >= p_changed_date
        GROUP BY ticker
    )
    SELECT
        metrics.date,
        metrics.ticker,
        metrics.close,
        metrics.volume,
        metrics.sector,
        metrics.industry,
        metrics.close_1d_ago,
        metrics.close_5d_ago,
        metrics.close_20d_ago,
        metrics.close_60d_ago,
        metrics.return_1d_pct,
        metrics.return_5d_pct,
        metrics.return_20d_pct,
        metrics.return_60d_pct,
        abs(metrics.return_1d_pct),
        metrics.volatility_5d_ann_pct,
        metrics.volatility_20d_ann_pct,
        metrics.volatility_60d_ann_pct,
        CASE
            WHEN metrics.volatility_5d_ann_pct IS NOT NULL
             AND metrics.volatility_5d_ago IS NOT NULL
             AND metrics.volatility_5d_ago <> 0.0
            THEN (metrics.volatility_5d_ann_pct / metrics.volatility_5d_ago - 1.0) * 100.0
        END,
        CASE
            WHEN metrics.volatility_20d_ann_pct IS NOT NULL
             AND metrics.volatility_20d_ago IS NOT NULL
             AND metrics.volatility_20d_ago <> 0.0
            THEN (metrics.volatility_20d_ann_pct / metrics.volatility_20d_ago - 1.0) * 100.0
        END,
        CASE
            WHEN metrics.volatility_60d_ann_pct IS NOT NULL
             AND metrics.volatility_60d_ago IS NOT NULL
             AND metrics.volatility_60d_ago <> 0.0
            THEN (metrics.volatility_60d_ann_pct / metrics.volatility_60d_ago - 1.0) * 100.0
        END,
        metrics.volume_avg_20d,
        metrics.volume_std_20d,
        CASE
            WHEN metrics.volume_avg_20d IS NOT NULL
             AND metrics.volume_avg_20d <> 0.0
            THEN metrics.volume::double precision / metrics.volume_avg_20d
        END,
        CASE
            WHEN metrics.volume_std_20d IS NOT NULL
             AND metrics.volume_std_20d <> 0.0
            THEN (metrics.volume::double precision - metrics.volume_avg_20d)
                 / metrics.volume_std_20d
        END,
        metrics.high_20d,
        metrics.high_60d,
        CASE
            WHEN metrics.high_20d IS NOT NULL AND metrics.high_20d <> 0
            THEN (metrics.close::double precision
                  / metrics.high_20d::double precision - 1.0) * 100.0
        END,
        CASE
            WHEN metrics.high_60d IS NOT NULL AND metrics.high_60d <> 0
            THEN (metrics.close::double precision
                  / metrics.high_60d::double precision - 1.0) * 100.0
        END
    FROM with_volatility_history AS metrics
    LEFT JOIN target_bounds
      ON target_bounds.ticker = metrics.ticker
    WHERE p_changed_date IS NULL
       OR metrics.observation_number BETWEEN
            target_bounds.first_target_observation
            AND target_bounds.first_target_observation + 120
    ON CONFLICT (ticker, date) DO UPDATE
    SET
        close = EXCLUDED.close,
        volume = EXCLUDED.volume,
        sector = EXCLUDED.sector,
        industry = EXCLUDED.industry,
        close_1d_ago = EXCLUDED.close_1d_ago,
        close_5d_ago = EXCLUDED.close_5d_ago,
        close_20d_ago = EXCLUDED.close_20d_ago,
        close_60d_ago = EXCLUDED.close_60d_ago,
        return_1d_pct = EXCLUDED.return_1d_pct,
        return_5d_pct = EXCLUDED.return_5d_pct,
        return_20d_pct = EXCLUDED.return_20d_pct,
        return_60d_pct = EXCLUDED.return_60d_pct,
        abs_return_1d_pct = EXCLUDED.abs_return_1d_pct,
        volatility_5d_ann_pct = EXCLUDED.volatility_5d_ann_pct,
        volatility_20d_ann_pct = EXCLUDED.volatility_20d_ann_pct,
        volatility_60d_ann_pct = EXCLUDED.volatility_60d_ann_pct,
        volatility_5d_change_pct = EXCLUDED.volatility_5d_change_pct,
        volatility_20d_change_pct = EXCLUDED.volatility_20d_change_pct,
        volatility_60d_change_pct = EXCLUDED.volatility_60d_change_pct,
        volume_avg_20d = EXCLUDED.volume_avg_20d,
        volume_std_20d = EXCLUDED.volume_std_20d,
        volume_ratio_20d = EXCLUDED.volume_ratio_20d,
        volume_zscore_20d = EXCLUDED.volume_zscore_20d,
        high_20d = EXCLUDED.high_20d,
        high_60d = EXCLUDED.high_60d,
        drawdown_20d_pct = EXCLUDED.drawdown_20d_pct,
        drawdown_60d_pct = EXCLUDED.drawdown_60d_pct;

    GET DIAGNOSTICS affected_rows = ROW_COUNT;
    RETURN affected_rows;
END
$function$;

COMMENT ON FUNCTION public.refresh_feature_01_stock_daily(date, text[]) IS
    'Full refresh when changed date is NULL; otherwise recomputes the changed observation and up to 120 following trading observations for selected tickers.';

SELECT public.refresh_feature_01_stock_daily(NULL, NULL);

CREATE INDEX "Feature_01_Stock_Daily_date_idx"
    ON public."Feature_01_Stock_Daily" (date);

COMMIT;
