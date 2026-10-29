-- FL16 from Feature 05 buy_freq (independent of the F06 path of q12); the same ratio evaluated at 2026-10-23 (k = 3) to
-- test whether a median below 1 is a property of the ratio or of a quiet day; market-wide trades per session.
WITH d AS (
  SELECT ticker, trade_date, sum(buy_freq)::float8 tr, sum(sell_freq)::float8 trs, count(*) FILTER (WHERE buy_freq IS NULL) nullf
  FROM "Feature_05_Foreign_Domestic_Broker_Detail"
  WHERE trade_date BETWEEN DATE '2026-09-25' AND DATE '2026-10-27'
  GROUP BY ticker, trade_date
), cal AS (SELECT trade_date, row_number() OVER (ORDER BY trade_date DESC) k FROM (SELECT DISTINCT trade_date FROM d) x),
g AS (
  SELECT u.ticker, c.k, coalesce(d.tr, 0) tr, d.ticker IS NOT NULL traded
  FROM (SELECT DISTINCT ticker FROM d) u CROSS JOIN cal c LEFT JOIN d ON d.ticker = u.ticker AND d.trade_date = c.trade_date
), r AS (
  SELECT g.ticker,
    bool_or(traded) FILTER (WHERE k = 1) t1, bool_or(traded) FILTER (WHERE k = 3) t3,
    sum(tr) FILTER (WHERE k = 1) / nullif(avg(tr) FILTER (WHERE k BETWEEN 2 AND 21), 0) fl16_1027,
    sum(tr) FILTER (WHERE k = 3) / nullif(avg(tr) FILTER (WHERE k BETWEEN 4 AND 23), 0) fl16_1023
  FROM g JOIN "IDX_Stock_Universe" u ON u."Ticker" = g.ticker AND u."Security Type" = 'stock' GROUP BY g.ticker
)
SELECT 'FL16 at 2026-10-27 (F05)' k, count(fl16_1027) n, round(min(fl16_1027)::numeric, 3) mn,
  round(percentile_cont(0.1) WITHIN GROUP (ORDER BY fl16_1027)::numeric, 3) p10, round(percentile_cont(0.5) WITHIN GROUP (ORDER BY fl16_1027)::numeric, 3) p50,
  round(percentile_cont(0.9) WITHIN GROUP (ORDER BY fl16_1027)::numeric, 3) p90, round(max(fl16_1027)::numeric, 3) mx,
  round(max(fl16_1027) FILTER (WHERE ticker = 'BBCA')::numeric, 3) bbca, round(max(fl16_1027) FILTER (WHERE ticker = 'CARE')::numeric, 3) care
FROM r WHERE t1
UNION ALL
SELECT 'FL16 at 2026-10-23 (F05)', count(fl16_1023), round(min(fl16_1023)::numeric, 3),
  round(percentile_cont(0.1) WITHIN GROUP (ORDER BY fl16_1023)::numeric, 3), round(percentile_cont(0.5) WITHIN GROUP (ORDER BY fl16_1023)::numeric, 3),
  round(percentile_cont(0.9) WITHIN GROUP (ORDER BY fl16_1023)::numeric, 3), round(max(fl16_1023)::numeric, 3),
  round(max(fl16_1023) FILTER (WHERE ticker = 'BBCA')::numeric, 3), round(max(fl16_1023) FILTER (WHERE ticker = 'CARE')::numeric, 3)
FROM r WHERE t3;;
SELECT trade_date::date, round((sum(buy_freq) / 1e3)::numeric, 1) k_trades, sum(buy_freq) = sum(sell_freq) balanced,
       count(*) FILTER (WHERE buy_freq IS NULL OR sell_freq IS NULL) null_rows
FROM "Feature_05_Foreign_Domestic_Broker_Detail" WHERE trade_date BETWEEN DATE '2026-09-29' AND DATE '2026-10-27'
GROUP BY 1 ORDER BY 1 DESC
