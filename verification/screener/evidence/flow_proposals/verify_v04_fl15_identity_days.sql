-- FL15: how often the daily top-3 balance is 0 by construction (at most 3 net buyers and at most 3 net sellers that day,
-- so B3 + S3 = total net = 0), by liquidity third; re-check of the q14 FL15 distribution.
WITH d AS (
  SELECT ticker, trade_date, broker, sum(net_value)::float8 n, sum(buy_value)::float8 bv
  FROM "Feature_05_Foreign_Domestic_Broker_Detail"
  WHERE trade_date BETWEEN DATE '2026-09-30' AND DATE '2026-10-27'
  GROUP BY ticker, trade_date, broker
), day AS (
  SELECT ticker, trade_date, count(*) FILTER (WHERE n > 0) nb, count(*) FILTER (WHERE n < 0) ns, sum(bv) v
  FROM d GROUP BY ticker, trade_date
), tk AS (
  SELECT day.ticker, sum(v) / 20 adv20, count(*) days_traded,
         count(*) FILTER (WHERE nb <= 3 AND ns <= 3) days_zero_by_construction
  FROM day JOIN "IDX_Stock_Universe" u ON u."Ticker" = day.ticker AND u."Security Type" = 'stock'
  WHERE EXISTS (SELECT 1 FROM "Feature_03_Stock_Broker_Daily" f WHERE f.ticker = day.ticker AND f.date = DATE '2026-10-27')
  GROUP BY day.ticker
), q AS (SELECT tk.*, ntile(3) OVER (ORDER BY adv20) liq FROM tk)
SELECT liq, count(*) n, round(avg(days_traded)::numeric, 2) avg_days_traded,
       round(avg(days_zero_by_construction)::numeric, 2) avg_zero_days,
       count(*) FILTER (WHERE days_zero_by_construction >= 5) stocks_with_ge5_zero_days,
       sum(days_zero_by_construction) zero_stock_days, sum(days_traded) traded_stock_days
FROM q GROUP BY ROLLUP (liq) ORDER BY liq NULLS LAST
