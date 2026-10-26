WITH source AS MATERIALIZED (
 SELECT f.trade_date,f.ticker,f.market_board,f.foreign_net_1d,f.domestic_net_1d,f.foreign_buy_1d,f.domestic_buy_1d,
 f.foreign_cumulative_net,f.domestic_cumulative_net,
 f.foreign_net_5d,f.foreign_net_10d,f.foreign_net_20d,f.foreign_net_40d,f.foreign_net_60d,
 f.domestic_net_5d,f.domestic_net_10d,f.domestic_net_20d,f.domestic_net_60d,f.foreign_net_turnover_ratio_1d
 FROM public."Feature_06_Foreign_Domestic" f WHERE f.trade_date<=DATE '2026-08-31' AND f.ticker<>'IHSG'
), calendar AS (
 SELECT trade_date,row_number() OVER(ORDER BY trade_date DESC) AS age FROM (SELECT DISTINCT trade_date FROM source)x
), expected AS (
 SELECT s.market_board,
 SUM(s.foreign_net_1d) AS foreign_cumulative_net,SUM(s.domestic_net_1d) AS domestic_cumulative_net,
 SUM(s.foreign_net_1d) FILTER(WHERE c.age<=5) AS foreign_net_5d,
 SUM(s.foreign_net_1d) FILTER(WHERE c.age<=10) AS foreign_net_10d,
 SUM(s.foreign_net_1d) FILTER(WHERE c.age<=20) AS foreign_net_20d,
 SUM(s.foreign_net_1d) FILTER(WHERE c.age<=40) AS foreign_net_40d,
 SUM(s.foreign_net_1d) FILTER(WHERE c.age<=60) AS foreign_net_60d,
 SUM(s.domestic_net_1d) FILTER(WHERE c.age<=5) AS domestic_net_5d,
 SUM(s.domestic_net_1d) FILTER(WHERE c.age<=10) AS domestic_net_10d,
 SUM(s.domestic_net_1d) FILTER(WHERE c.age<=20) AS domestic_net_20d,
 SUM(s.domestic_net_1d) FILTER(WHERE c.age<=60) AS domestic_net_60d,
 100*SUM(s.foreign_net_1d) FILTER(WHERE c.age=1) / NULLIF(SUM(s.foreign_buy_1d+s.domestic_buy_1d) FILTER(WHERE c.age=1),0) AS foreign_net_turnover_ratio_1d
 FROM source s JOIN calendar c USING(trade_date) GROUP BY 1
), sum_on_date AS (
 SELECT market_board,COUNT(*) AS symbols_on_date,
 SUM(foreign_cumulative_net) AS foreign_cumulative_net,SUM(domestic_cumulative_net) AS domestic_cumulative_net,
 SUM(foreign_net_5d) AS foreign_net_5d,SUM(foreign_net_10d) AS foreign_net_10d,SUM(foreign_net_20d) AS foreign_net_20d,
 SUM(foreign_net_40d) AS foreign_net_40d,SUM(foreign_net_60d) AS foreign_net_60d,
 SUM(domestic_net_5d) AS domestic_net_5d,SUM(domestic_net_10d) AS domestic_net_10d,SUM(domestic_net_20d) AS domestic_net_20d,
 SUM(domestic_net_60d) AS domestic_net_60d,SUM(foreign_net_turnover_ratio_1d) AS sum_turnover_ratios
 FROM source WHERE trade_date=DATE '2026-08-31' GROUP BY 1
), latest_per_symbol AS (
 SELECT DISTINCT ON(ticker,market_board) ticker,market_board,trade_date,foreign_cumulative_net,domestic_cumulative_net
 FROM source ORDER BY ticker,market_board,trade_date DESC
)
SELECT json_build_object(
 'expected_common_calendar',(SELECT json_agg(x ORDER BY market_board) FROM expected x),
 'stored',(SELECT json_agg(x ORDER BY market_board) FROM public."Feature_06_Foreign_Domestic" x WHERE ticker='IHSG' AND trade_date=DATE '2026-08-31'),
 'sum_ticker_rows_on_date',(SELECT json_agg(x ORDER BY market_board) FROM sum_on_date x),
 'sum_latest_cumulative',(SELECT json_agg(x ORDER BY market_board) FROM (
 SELECT market_board,COUNT(*) AS historical_symbols,SUM(foreign_cumulative_net) AS foreign_cumulative_net,
 SUM(domestic_cumulative_net) AS domestic_cumulative_net,
 COUNT(*) FILTER(WHERE trade_date<DATE '2026-08-31') AS symbols_without_row_on_target,
 SUM(foreign_cumulative_net) FILTER(WHERE trade_date<DATE '2026-08-31') AS omitted_foreign_cumulative,
 SUM(domestic_cumulative_net) FILTER(WHERE trade_date<DATE '2026-08-31') AS omitted_domestic_cumulative
 FROM latest_per_symbol GROUP BY 1)x),
 'window_bounds',(SELECT json_agg(x ORDER BY n) FROM (SELECT n,MIN(c.trade_date) AS start_date,MAX(c.trade_date) AS end_date,COUNT(*) AS sessions
 FROM (VALUES(5),(10),(20),(40),(60)) w(n) JOIN calendar c ON c.age<=w.n GROUP BY n)x));
