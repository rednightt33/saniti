-- FL04 by a different method (sign of today, then the newest session whose sign differs), market sessions 2026-07-31..10-27
-- (61), all boards from F03; plus how many stocks have |FL02 D20| < 1 %. (First attempt with a correlated subquery hit
-- the 30 s statement timeout; this version uses a window function.)
WITH d AS (
  SELECT ticker, date, sum(foreign_net_value)::float8 f, sum(total_buy_value)::float8 v
  FROM "Feature_03_Stock_Broker_Daily" WHERE date BETWEEN DATE '2026-07-31' AND DATE '2026-10-27' GROUP BY ticker, date
), cal AS (SELECT date, row_number() OVER (ORDER BY date DESC) k FROM (SELECT DISTINCT date FROM d) x),
tk AS (SELECT DISTINCT d.ticker FROM d JOIN "IDX_Stock_Universe" u ON u."Ticker" = d.ticker AND u."Security Type" = 'stock' WHERE d.date = DATE '2026-10-27'),
g AS (SELECT tk.ticker, c.k, sign(coalesce(d.f, 0)) s, coalesce(d.f, 0) f, coalesce(d.v, 0) v FROM tk CROSS JOIN cal c LEFT JOIN d ON d.ticker = tk.ticker AND d.date = c.date),
g1 AS (SELECT g.*, first_value(s) OVER (PARTITION BY ticker ORDER BY k) s1 FROM g),
s AS (
  SELECT ticker, max(s1) s1, min(k) FILTER (WHERE s <> s1) brk,
         100 * sum(f) FILTER (WHERE k <= 20) / nullif(sum(v) FILTER (WHERE k <= 20), 0) fl02
  FROM g1 GROUP BY ticker
), r AS (SELECT ticker, fl02, CASE WHEN s1 = 0 THEN 0 ELSE s1 * least(coalesce(brk, 62) - 1, 60) END fl04 FROM s)
SELECT count(*) n, min(fl04) mn, percentile_cont(0.1) WITHIN GROUP (ORDER BY fl04) p10, percentile_cont(0.5) WITHIN GROUP (ORDER BY fl04) p50,
  percentile_cont(0.9) WITHIN GROUP (ORDER BY fl04) p90, max(fl04) mx,
  max(fl04) FILTER (WHERE ticker = 'BBCA') bbca, max(fl04) FILTER (WHERE ticker = 'ANTM') antm, max(fl04) FILTER (WHERE ticker = 'CARE') care,
  count(*) FILTER (WHERE fl04 = 0) fl04_zero, count(*) FILTER (WHERE abs(fl02) < 1) abs_fl02_lt1, count(*) FILTER (WHERE abs(fl02) < 0.1) abs_fl02_lt01
FROM r
