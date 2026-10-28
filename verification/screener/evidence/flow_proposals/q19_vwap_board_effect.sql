WITH b AS (
  SELECT ticker, broker, sum(net_value)::float8 n10,
         sum(buy_value)::float8 bv, sum(buy_lots)::float8 bl,
         sum(buy_value) FILTER (WHERE market_board = 'Regular')::float8 bv_reg, sum(buy_lots) FILTER (WHERE market_board = 'Regular')::float8 bl_reg
  FROM "Feature_05_Foreign_Domestic_Broker_Detail"
  WHERE trade_date BETWEEN DATE '2026-10-14' AND DATE '2026-10-27'
  GROUP BY ticker, broker
), r AS (SELECT b.*, row_number() OVER (PARTITION BY ticker ORDER BY n10 DESC, broker) rb FROM b),
t AS (
  SELECT ticker, sum(bv) FILTER (WHERE rb <= 3 AND n10 > 0) / nullif(100 * sum(bl) FILTER (WHERE rb <= 3 AND n10 > 0), 0) vwap_all,
         sum(bv_reg) FILTER (WHERE rb <= 3 AND n10 > 0) / nullif(100 * sum(bl_reg) FILTER (WHERE rb <= 3 AND n10 > 0), 0) vwap_reg
  FROM r GROUP BY ticker
), q AS (
  SELECT t.ticker, p.close::float8 c, 100 * (p.close / nullif(vwap_all, 0) - 1) d_all, 100 * (p.close / nullif(vwap_reg, 0) - 1) d_reg
  FROM t JOIN "IDX_Stock_Universe" u ON u."Ticker" = t.ticker AND u."Security Type" = 'stock'
  JOIN "Price_Stock_Indonesia_IDX" p ON p.ticker = t.ticker AND p.date = DATE '2026-10-27' AND p.timeframe = 'Daily'
)
SELECT 'summary' k, count(*) n, count(*) FILTER (WHERE abs(d_all - d_reg) > 1) diff_gt_1pt, count(*) FILTER (WHERE abs(d_all - d_reg) > 5) diff_gt_5pt,
       count(*) FILTER (WHERE d_reg IS NULL) reg_null, NULL::text ticker, NULL::numeric d_all, NULL::numeric d_reg
FROM q
UNION ALL
SELECT * FROM (SELECT 'largest gaps', NULL::bigint, NULL::bigint, NULL::bigint, NULL::bigint, ticker, round(d_all::numeric, 2), round(d_reg::numeric, 2) FROM q ORDER BY abs(d_all - coalesce(d_reg, 0)) DESC NULLS LAST LIMIT 6) x
