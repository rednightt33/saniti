WITH b AS (
  SELECT ticker, broker,
         sum(net_value) FILTER (WHERE trade_date >= DATE '2026-10-14')::float8 n10,
         sum(net_value)::float8 n20,
         sum(buy_value) FILTER (WHERE trade_date >= DATE '2026-10-14')::float8 bv10,
         sum(buy_lots)  FILTER (WHERE trade_date >= DATE '2026-10-14')::float8 bl10,
         sum(buy_value)::float8 bv20, sum(sell_value)::float8 sv20
  FROM "Feature_05_Foreign_Domestic_Broker_Detail"
  WHERE trade_date BETWEEN DATE '2026-09-30' AND DATE '2026-10-27'
  GROUP BY ticker, broker
), r AS (
  SELECT b.*,
    row_number() OVER (PARTITION BY ticker ORDER BY n10 DESC NULLS LAST, broker) b10,
    row_number() OVER (PARTITION BY ticker ORDER BY n10 ASC NULLS LAST, broker) s10,
    row_number() OVER (PARTITION BY ticker ORDER BY n20 DESC, broker) b20,
    row_number() OVER (PARTITION BY ticker ORDER BY n20 ASC, broker) s20
  FROM b
), t AS (
  SELECT ticker,
    sum(bv10) t10, sum(bv20) t20,
    coalesce(sum(n10) FILTER (WHERE b10 <= 5 AND n10 > 0), 0) + coalesce(sum(n10) FILTER (WHERE s10 <= 5 AND n10 < 0), 0) top5_10,
    coalesce(sum(n10) FILTER (WHERE b10 <= 3 AND n10 > 0), 0) buy3_10,
    coalesce(sum(n10) FILTER (WHERE s10 <= 3 AND n10 < 0), 0) sell3_10,
    coalesce(sum(n20) FILTER (WHERE b20 <= 3 AND n20 > 0), 0) + coalesce(sum(n20) FILTER (WHERE s20 <= 3 AND n20 < 0), 0) top3_20,
    sum(greatest(n20, 0) ^ 2) / nullif(sum(greatest(n20, 0)) ^ 2, 0) hhi_netbuy20,
    sum(bv20 ^ 2) / nullif(sum(bv20) ^ 2, 0) hhi_buy20,
    sum(sv20 ^ 2) / nullif(sum(sv20) ^ 2, 0) hhi_sell20,
    count(*) FILTER (WHERE n20 > 0) buyers20, count(*) FILTER (WHERE n20 < 0) sellers20,
    count(*) FILTER (WHERE n10 <> 0) movers10,
    sum(bv10) FILTER (WHERE b10 <= 3 AND n10 > 0) / nullif(100 * sum(bl10) FILTER (WHERE b10 <= 3 AND n10 > 0), 0) vwap3_10
  FROM r GROUP BY ticker
), q AS (
  SELECT t.*, p.close::float8 close,
    100 * buy3_10 / nullif(t10, 0) fl08, 100 * sell3_10 / nullif(t10, 0) sellint,
    100 * (buy3_10 + sell3_10) / nullif(t10, 0) fl09, 100 * top3_20 / nullif(t20, 0) fl09_20,
    hhi_buy20 - hhi_sell20 fl11,
    buyers20::float8 / nullif(buyers20 + sellers20, 0) fl12,
    100 * (p.close / nullif(vwap3_10, 0) - 1) fl13
  FROM t
  JOIN "IDX_Stock_Universe" u ON u."Ticker" = t.ticker AND u."Security Type" = 'stock'
  JOIN "Price_Stock_Indonesia_IDX" p ON p.ticker = t.ticker AND p.date = DATE '2026-10-27' AND p.timeframe = 'Daily'
)
SELECT m.name, count(m.v) n, round(min(m.v)::numeric, 4) mn,
  round(percentile_cont(0.1) WITHIN GROUP (ORDER BY m.v)::numeric, 4) p10,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY m.v)::numeric, 4) p50,
  round(percentile_cont(0.9) WITHIN GROUP (ORDER BY m.v)::numeric, 4) p90,
  round(max(m.v)::numeric, 4) mx,
  round(max(m.v) FILTER (WHERE q.ticker = 'BBCA')::numeric, 4) bbca,
  round(max(m.v) FILTER (WHERE q.ticker = 'ANTM')::numeric, 4) antm,
  round(max(m.v) FILTER (WHERE q.ticker = 'CARE')::numeric, 4) care,
  count(*) FILTER (WHERE m.v IS NULL) nulls
FROM q CROSS JOIN LATERAL (VALUES
  ('FL07 top-5 net accumulation 10 (Rp B)', q.top5_10 / 1e9),
  ('FL08 buy intensity top-3 10 (% value)', q.fl08),
  ('FL08 ref: sell intensity top-3 10 (% value)', q.sellint),
  ('FL09 bandar balance top-3 10 (% value)', q.fl09),
  ('FL09 ref: bandar balance top-3 20 (% value)', q.fl09_20),
  ('FL10 net-buy HHI 20 (0-1)', q.hhi_netbuy20),
  ('FL10 ref: effective net buyers 20 (1/HHI)', 1 / nullif(q.hhi_netbuy20, 0)),
  ('FL11 buy-sell HHI gap 20', q.fl11),
  ('FL11 ref: gross buy HHI 20', q.hhi_buy20),
  ('FL12 breadth 20 (buyers/(buyers+sellers))', q.fl12),
  ('FL13 close vs top-3 buyer VWAP 10 (%)', q.fl13),
  ('ref: brokers with nonzero net 10', q.movers10::float8),
  ('ref: tickers with <= 6 nonzero-net brokers 10 (1=yes)', (q.movers10 <= 6)::int::float8),
  ('ref: bandar balance 10 exactly 0 (1=yes)', (q.fl09 = 0)::int::float8)
) m(name, v)
GROUP BY m.name ORDER BY m.name
