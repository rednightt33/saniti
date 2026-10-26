-- Bounds below are copied from verified source-session window_bounds in feature6_net_windows.json.
WITH bounds(n,start_date) AS (VALUES
(5,DATE '2026-08-24'),
(10,DATE '2026-08-14'),
(20,DATE '2026-07-31'),
(40,DATE '2026-07-03'),
(60,DATE '2026-06-04')
), context AS MATERIALIZED (
 SELECT ticker,market_board,trade_date,foreign_net_1d,domestic_net_1d,
 foreign_net_5d,foreign_net_10d,foreign_net_20d,foreign_net_40d,foreign_net_60d
 FROM public."Feature_06_Foreign_Domestic"
 WHERE trade_date BETWEEN DATE '2026-06-04' AND DATE '2026-08-31' AND ticker<>'IHSG'
), by_symbol AS (
 SELECT w.n,f.ticker,f.market_board,SUM(f.foreign_net_1d) AS foreign_common
 FROM bounds w JOIN context f ON f.trade_date>=w.start_date GROUP BY 1,2,3
), joined AS (
 SELECT b.*,t.ticker IS NOT NULL AS on_date,
 CASE n WHEN 5 THEN t.foreign_net_5d WHEN 10 THEN t.foreign_net_10d WHEN 20 THEN t.foreign_net_20d WHEN 40 THEN t.foreign_net_40d WHEN 60 THEN t.foreign_net_60d END AS ticker_rolling
 FROM by_symbol b LEFT JOIN (SELECT * FROM context WHERE trade_date=DATE '2026-08-31')t ON t.ticker=b.ticker AND t.market_board=b.market_board
)
SELECT n,market_board,SUM(foreign_common) AS market_common_rolling,
 COALESCE(SUM(foreign_common) FILTER(WHERE NOT on_date),0) AS omitted_from_date_contribution,
 SUM(foreign_common) FILTER(WHERE on_date) AS present_tickers_common_rolling,
 SUM(ticker_rolling) AS sum_present_ticker_rolling,
 SUM(foreign_common) FILTER(WHERE on_date)-SUM(ticker_rolling) AS present_calendar_and_warmup_difference,
 COUNT(*) FILTER(WHERE on_date AND ticker_rolling IS NULL) AS present_tickers_in_warmup,
 COALESCE(SUM(foreign_common) FILTER(WHERE on_date AND ticker_rolling IS NULL),0) AS warmup_common_flow
FROM joined GROUP BY 1,2 ORDER BY 2,1;
