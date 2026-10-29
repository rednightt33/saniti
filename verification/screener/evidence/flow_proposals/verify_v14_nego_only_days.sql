-- Stock-days with broker rows but no price bar (2026-09-30..10-27): which boards, and the foreign net the Backtest's
-- flowData would skip (unmatched_rows) on its price-bar calendar.
WITH s AS (SELECT "Ticker" t FROM "IDX_Stock_Universe" WHERE "Security Type" = 'stock'),
b AS (SELECT ticker, date, string_agg(market_board, '+' ORDER BY market_board) boards, sum(foreign_net_value)::float8 f, sum(total_buy_value)::float8 v
      FROM "Feature_03_Stock_Broker_Daily" WHERE date BETWEEN DATE '2026-09-30' AND DATE '2026-10-27' AND ticker IN (SELECT t FROM s) GROUP BY 1, 2),
x AS (SELECT b.* FROM b WHERE NOT EXISTS (SELECT 1 FROM "Price_Stock_Indonesia_IDX" p WHERE p.ticker = b.ticker AND p.date = b.date AND p.timeframe = 'Daily'))
SELECT boards, count(*) stock_days, count(DISTINCT ticker) tickers, round((sum(abs(f)) / 1e9)::numeric, 2) abs_fnet_b, round((sum(v) / 1e9)::numeric, 2) value_b,
  (SELECT string_agg(ticker || ' ' || round((ff / 1e9)::numeric, 2), '; ') FROM (SELECT ticker, sum(f) ff FROM x x2 WHERE x2.boards = x.boards GROUP BY 1 ORDER BY abs(sum(f)) DESC LIMIT 3) z) top_fnet_b
FROM x GROUP BY boards ORDER BY stock_days DESC
