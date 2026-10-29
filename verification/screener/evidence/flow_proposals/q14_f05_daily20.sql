WITH d AS (
  SELECT ticker, trade_date, broker, sum(net_value)::float8 n, sum(buy_value)::float8 bv
  FROM "Feature_05_Foreign_Domestic_Broker_Detail"
  WHERE trade_date BETWEEN DATE '2026-09-30' AND DATE '2026-10-27'
  GROUP BY ticker, trade_date, broker
), dr AS (
  SELECT d.*, row_number() OVER (PARTITION BY ticker, trade_date ORDER BY n DESC, broker) rb,
              row_number() OVER (PARTITION BY ticker, trade_date ORDER BY n ASC, broker) rs
  FROM d
), day AS (
  SELECT ticker, trade_date,
    100 * (coalesce(sum(n) FILTER (WHERE rb <= 3 AND n > 0), 0) + coalesce(sum(n) FILTER (WHERE rs <= 3 AND n < 0), 0)) / nullif(sum(bv), 0) bal3
  FROM dr GROUP BY ticker, trade_date
), w AS (
  SELECT ticker, broker, sum(n) n20, count(*) FILTER (WHERE n > 0) buy_days,
         row_number() OVER (PARTITION BY ticker ORDER BY sum(n) DESC, broker) rk
  FROM d GROUP BY ticker, broker
), q AS (
  SELECT a.ticker,
    count(*) FILTER (WHERE a.bal3 > 0)::float8 / 20 fl15_sign,
    count(*) FILTER (WHERE a.bal3 >= 5)::float8 acc_days5,
    count(*) FILTER (WHERE a.bal3 <= -5)::float8 dist_days5,
    max(w1.buy_days)::float8 / 20 fl14_top1,
    max(w1.broker) top1
  FROM day a JOIN w w1 ON w1.ticker = a.ticker AND w1.rk = 1 AND w1.n20 > 0
  GROUP BY a.ticker
), r AS (
  SELECT q.* FROM q JOIN "IDX_Stock_Universe" u ON u."Ticker" = q.ticker AND u."Security Type" = 'stock'
  WHERE EXISTS (SELECT 1 FROM "Feature_03_Stock_Broker_Daily" f WHERE f.ticker = q.ticker AND f.date = DATE '2026-10-27')
)
SELECT m.name, count(m.v) n, round(min(m.v)::numeric, 3) mn,
  round(percentile_cont(0.1) WITHIN GROUP (ORDER BY m.v)::numeric, 3) p10,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY m.v)::numeric, 3) p50,
  round(percentile_cont(0.9) WITHIN GROUP (ORDER BY m.v)::numeric, 3) p90,
  round(max(m.v)::numeric, 3) mx,
  round(max(m.v) FILTER (WHERE r.ticker = 'BBCA')::numeric, 3) bbca,
  round(max(m.v) FILTER (WHERE r.ticker = 'ANTM')::numeric, 3) antm,
  round(max(m.v) FILTER (WHERE r.ticker = 'CARE')::numeric, 3) care,
  max(r.top1) FILTER (WHERE r.ticker = 'BBCA') || '/' || max(r.top1) FILTER (WHERE r.ticker = 'ANTM') || '/' || max(r.top1) FILTER (WHERE r.ticker = 'CARE') top1_bbca_antm_care
FROM r CROSS JOIN LATERAL (VALUES
  ('FL14 top-1 20d net buyer: buy-day ratio 20', r.fl14_top1),
  ('FL15 accumulation-day ratio 20 (daily top-3 balance > 0)', r.fl15_sign),
  ('FL15 ref: days with daily top-3 balance >= +5% (of 20)', r.acc_days5),
  ('FL15 ref: days with daily top-3 balance <= -5% (of 20)', r.dist_days5)
) m(name, v)
GROUP BY m.name ORDER BY m.name
