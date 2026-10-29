WITH x AS (
  SELECT ticker, sum(net_value) FILTER (WHERE trade_date >= DATE '2026-10-21')::float8 / 1e9 n5_b, sum(net_value)::float8 / 1e9 n20_b
  FROM "Feature_05_Foreign_Domestic_Broker_Detail"
  WHERE trade_date BETWEEN DATE '2026-09-30' AND DATE '2026-10-27' AND broker = 'YP'
  GROUP BY ticker
), r AS (
  SELECT u."Ticker" ticker, coalesce(x.n5_b, 0) n5_b, coalesce(x.n20_b, 0) n20_b
  FROM "IDX_Stock_Universe" u LEFT JOIN x ON x.ticker = u."Ticker"
  WHERE u."Security Type" = 'stock'
    AND EXISTS (SELECT 1 FROM "Feature_03_Stock_Broker_Daily" f WHERE f.ticker = u."Ticker" AND f.date = DATE '2026-10-27')
)
SELECT m.name, count(m.v) n, round(min(m.v)::numeric, 3) mn,
  round(percentile_cont(0.1) WITHIN GROUP (ORDER BY m.v)::numeric, 3) p10,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY m.v)::numeric, 3) p50,
  round(percentile_cont(0.9) WITHIN GROUP (ORDER BY m.v)::numeric, 3) p90,
  round(max(m.v)::numeric, 3) mx,
  round(max(m.v) FILTER (WHERE r.ticker = 'BBCA')::numeric, 3) bbca,
  round(max(m.v) FILTER (WHERE r.ticker = 'ANTM')::numeric, 3) antm,
  round(max(m.v) FILTER (WHERE r.ticker = 'CARE')::numeric, 3) care,
  count(*) FILTER (WHERE m.v = 0) zero
FROM r CROSS JOIN LATERAL (VALUES ('FL06 broker YP net 5 (Rp B, all boards)', r.n5_b), ('FL06 broker YP net 20 (Rp B, all boards)', r.n20_b)) m(name, v)
GROUP BY m.name ORDER BY m.name
