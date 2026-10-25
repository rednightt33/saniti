-- EXEC-INCR-1025 I1 (user 2026-10-25: "Jangan sampai data yang baru dihitung dengan formula yang berbeda dengan data
-- sebelumnya. Go."): an incremental Feature 02 v2 refresh. scripts/backfill_feature_02_v2.py can only fill tickers that
-- have no row or rebuild one ticker's whole history; this function recomputes one ticker from a date.
--
-- The INSERT is the SQL of backfill_feature_02_v2.py INSERT_TICKER, copied unchanged except:
-- 1. the daily rows come from Feature 05 instead of the script's staging of IDX_Broker_Summary. Feature 05 holds one
--    row per IDX_Broker_Summary row (same five-column key; buy/sell value and lots equal, checked per year when it was
--    built and for every refreshed range), so the daily grain, values and ticker calendar are the same;
-- 2. the rows read start at the 311th ticker session before p_from: the longest dependency of a row is the 252
--    previous net_value_60d values, each over 60 sessions (252 + 59 = 311 earlier sessions). With fewer earlier sessions
--    the ticker's whole history is read. Every threshold (day_no >= 5/20/60, history count = 252) then has the value
--    of the full calculation for every written row;
-- 3. only rows with date >= p_from are deleted and written (p_from NULL: the ticker's whole history, the script's
--    --rebuild-ticker).
-- The equality with the full calculation is proven before use (EXEC-INCR-1025 T): rewritten historical rows must equal
-- the stored ones in a rolled-back transaction.
BEGIN;
SET LOCAL lock_timeout = '5s';

DO $preflight$
BEGIN
    IF to_regprocedure('public.feature_02_empirical_midrank_percentile(numeric,numeric[])') IS NULL
       AND NOT EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'feature_02_empirical_midrank_percentile') THEN
        RAISE EXCEPTION 'feature_02_empirical_midrank_percentile is missing';
    END IF;
    IF to_regprocedure('public.refresh_feature_02(text,date)') IS NOT NULL THEN
        RAISE EXCEPTION 'refresh_feature_02 already exists';
    END IF;
END
$preflight$;

CREATE FUNCTION public.refresh_feature_02(p_ticker text, p_from date DEFAULT NULL)
RETURNS bigint
LANGUAGE plpgsql
AS $function$
DECLARE
    v_range_start date;
    v_rows bigint;
BEGIN
    IF p_ticker IS NULL THEN
        RAISE EXCEPTION 'refresh_feature_02 needs a ticker';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended('Feature_02_Broker_Rolling:' || p_ticker, 0));

    IF p_from IS NOT NULL THEN
        SELECT CASE WHEN count(*) = 311 THEN min(d) END INTO v_range_start
        FROM (SELECT DISTINCT trade_date AS d FROM public."Feature_05_Foreign_Domestic_Broker_Detail"
              WHERE ticker = p_ticker AND trade_date < p_from ORDER BY d DESC LIMIT 311) AS prior;
    END IF;

    DELETE FROM public."Feature_02_Broker_Rolling"
    WHERE ticker = p_ticker AND (p_from IS NULL OR date >= p_from);

INSERT INTO public."Feature_02_Broker_Rolling" (
    date, ticker, broker, investor_type, market_board, broker_classification,
    buy_value_1d, sell_value_1d, net_value_1d,
    buy_lots_1d, sell_lots_1d, net_lots_1d,
    net_value_5d, net_value_20d, net_value_60d,
    net_lots_5d, net_lots_20d, net_lots_60d,
    buy_days_20d, sell_days_20d, active_days_20d,
    stock_trading_days_20d, buy_day_ratio_20d, buy_share_active_days_20d,
    buy_days_60d, sell_days_60d, active_days_60d,
    stock_trading_days_60d, buy_day_ratio_60d, buy_share_active_days_60d,
    net_value_zscore_20d, net_value_zscore_60d,
    net_value_percentile_20d, net_value_percentile_60d,
    positive_net_value_20d, largest_buy_day_20d,
    largest_buy_day_share_20d, calculated_at
)
WITH daily AS MATERIALIZED (
    -- the daily grain of backfill_feature_02_v2.py STAGE_YEAR (one IDX_Broker_Summary row per key), read from Feature 05,
    -- which holds one row per IDX_Broker_Summary row with the same key and values and a ticker-first key
    SELECT f.trade_date AS date, f.ticker, f.broker, f.investor_type, f.market_board,
           f.buy_value, f.sell_value, f.buy_lots, f.sell_lots,
           f.buy_value - f.sell_value AS net_value, f.buy_lots - f.sell_lots AS net_lots
    FROM public."Feature_05_Foreign_Domestic_Broker_Detail" AS f
    WHERE f.ticker = p_ticker AND (v_range_start IS NULL OR f.trade_date >= v_range_start)
),
calendar AS (
    SELECT date, row_number() OVER (ORDER BY date) AS day_no
    FROM (SELECT DISTINCT date FROM daily) AS available
),
pairs AS (
    SELECT DISTINCT broker, investor_type, market_board FROM daily
),
dense AS (
    SELECT calendar.date, calendar.day_no, pairs.broker,
           pairs.investor_type, pairs.market_board,
           coalesce(daily.net_value, 0) AS net_value,
           coalesce(daily.net_lots, 0) AS net_lots,
           CASE WHEN daily.date IS NOT NULL
                     AND (daily.buy_value > 0 OR daily.sell_value > 0
                          OR daily.buy_lots > 0 OR daily.sell_lots > 0)
                THEN 1 ELSE 0 END AS active
    FROM calendar CROSS JOIN pairs
    LEFT JOIN daily
      ON daily.date = calendar.date
     AND daily.broker = pairs.broker
     AND daily.investor_type = pairs.investor_type
     AND daily.market_board = pairs.market_board
),
rolling AS (
    SELECT dense.*,
           sum(net_value) OVER w5 AS net_value_5_raw,
           sum(net_value) OVER w20 AS net_value_20_raw,
           sum(net_value) OVER w60 AS net_value_60_raw,
           sum(net_lots) OVER w5 AS net_lots_5_raw,
           sum(net_lots) OVER w20 AS net_lots_20_raw,
           sum(net_lots) OVER w60 AS net_lots_60_raw,
           count(*) FILTER (WHERE net_value > 0) OVER w20 AS buy_days_20_raw,
           count(*) FILTER (WHERE net_value < 0) OVER w20 AS sell_days_20_raw,
           sum(active) OVER w20 AS active_days_20_raw,
           count(*) FILTER (WHERE net_value > 0) OVER w60 AS buy_days_60_raw,
           count(*) FILTER (WHERE net_value < 0) OVER w60 AS sell_days_60_raw,
           sum(active) OVER w60 AS active_days_60_raw,
           sum(greatest(net_value, 0)) OVER w20 AS positive_net_20_raw,
           max(net_value) FILTER (WHERE net_value > 0) OVER w20 AS largest_buy_20_raw
    FROM dense
    WINDOW w5 AS (PARTITION BY broker, investor_type, market_board ORDER BY day_no
                  ROWS BETWEEN 4 PRECEDING AND CURRENT ROW),
           w20 AS (PARTITION BY broker, investor_type, market_board ORDER BY day_no
                   ROWS BETWEEN 19 PRECEDING AND CURRENT ROW),
           w60 AS (PARTITION BY broker, investor_type, market_board ORDER BY day_no
                   ROWS BETWEEN 59 PRECEDING AND CURRENT ROW)
),
complete AS (
    SELECT rolling.*,
           CASE WHEN day_no >= 5 THEN net_value_5_raw END AS net_value_5d,
           CASE WHEN day_no >= 20 THEN net_value_20_raw END AS net_value_20d,
           CASE WHEN day_no >= 60 THEN net_value_60_raw END AS net_value_60d,
           CASE WHEN day_no >= 5 THEN net_lots_5_raw END AS net_lots_5d,
           CASE WHEN day_no >= 20 THEN net_lots_20_raw END AS net_lots_20d,
           CASE WHEN day_no >= 60 THEN net_lots_60_raw END AS net_lots_60d
    FROM rolling
),
history AS (
    SELECT complete.*,
           count(net_value_20d) OVER h AS history_20_count,
           avg(net_value_20d::double precision) OVER h AS history_20_mean,
           stddev_samp(net_value_20d::double precision) OVER h AS history_20_std,
           array_agg(net_value_20d) FILTER (WHERE net_value_20d IS NOT NULL)
               OVER h AS history_20_values,
           count(net_value_60d) OVER h AS history_60_count,
           avg(net_value_60d::double precision) OVER h AS history_60_mean,
           stddev_samp(net_value_60d::double precision) OVER h AS history_60_std,
           array_agg(net_value_60d) FILTER (WHERE net_value_60d IS NOT NULL)
               OVER h AS history_60_values
    FROM complete
    WINDOW h AS (PARTITION BY broker, investor_type, market_board ORDER BY day_no
                 ROWS BETWEEN 252 PRECEDING AND 1 PRECEDING)
)
SELECT daily.date, daily.ticker, daily.broker, daily.investor_type,
       daily.market_board, profile.broker_classification,
       daily.buy_value, daily.sell_value, daily.net_value,
       daily.buy_lots, daily.sell_lots, daily.net_lots,
       history.net_value_5d, history.net_value_20d, history.net_value_60d,
       history.net_lots_5d, history.net_lots_20d, history.net_lots_60d,
       CASE WHEN day_no >= 20 THEN buy_days_20_raw::smallint END,
       CASE WHEN day_no >= 20 THEN sell_days_20_raw::smallint END,
       CASE WHEN day_no >= 20 THEN active_days_20_raw::smallint END,
       CASE WHEN day_no >= 20 THEN 20::smallint END,
       CASE WHEN day_no >= 20 THEN buy_days_20_raw::double precision / 20 END,
       CASE WHEN day_no >= 20 AND active_days_20_raw > 0
            THEN buy_days_20_raw::double precision / active_days_20_raw END,
       CASE WHEN day_no >= 60 THEN buy_days_60_raw::smallint END,
       CASE WHEN day_no >= 60 THEN sell_days_60_raw::smallint END,
       CASE WHEN day_no >= 60 THEN active_days_60_raw::smallint END,
       CASE WHEN day_no >= 60 THEN 60::smallint END,
       CASE WHEN day_no >= 60 THEN buy_days_60_raw::double precision / 60 END,
       CASE WHEN day_no >= 60 AND active_days_60_raw > 0
            THEN buy_days_60_raw::double precision / active_days_60_raw END,
       CASE WHEN history_20_count = 252 AND history_20_std > 0
            THEN (history.net_value_20d::double precision - history_20_mean)
                 / history_20_std END,
       CASE WHEN history_60_count = 252 AND history_60_std > 0
            THEN (history.net_value_60d::double precision - history_60_mean)
                 / history_60_std END,
       CASE WHEN history_20_count = 252
            THEN public.feature_02_empirical_midrank_percentile(
                history.net_value_20d, history_20_values) END,
       CASE WHEN history_60_count = 252
            THEN public.feature_02_empirical_midrank_percentile(
                history.net_value_60d, history_60_values) END,
       CASE WHEN day_no >= 20 THEN positive_net_20_raw END,
       CASE WHEN day_no >= 20 THEN largest_buy_20_raw END,
       CASE WHEN day_no >= 20 AND positive_net_20_raw > 0
            THEN largest_buy_20_raw::double precision
                 / positive_net_20_raw::double precision END,
       statement_timestamp()
FROM history
JOIN daily
  ON daily.date = history.date
 AND daily.broker = history.broker
 AND daily.investor_type = history.investor_type
 AND daily.market_board = history.market_board
LEFT JOIN public."IDX_Broker_Profile" AS profile
  ON profile.broker_code = daily.broker
WHERE p_from IS NULL OR daily.date >= p_from;
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RETURN v_rows;
END
$function$;

COMMENT ON FUNCTION public.refresh_feature_02(text, date) IS
    'EXEC-INCR-1025: Feature 02 v2 for one ticker from p_from (NULL: whole history), the SQL of scripts/backfill_feature_02_v2.py over the ticker''s Feature 05 rows from the 311th session before p_from; equal to the full calculation.';

UPDATE public."Table_Catalog"
SET related_functions = CASE WHEN 'public.refresh_feature_02(text, date)' = ANY (related_functions) THEN related_functions
                             ELSE related_functions || ARRAY['public.refresh_feature_02(text, date)'] END,
    source_code_paths = source_code_paths || ARRAY['database/migrations/20261025_008_refresh_feature_02_incremental.sql']
WHERE table_schema = 'public' AND table_name = 'Feature_02_Broker_Rolling';
COMMIT;
