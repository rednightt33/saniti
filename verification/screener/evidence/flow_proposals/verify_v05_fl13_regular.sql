-- FL13 board effect, re-done: q19's "Regular" ranks the top-3 buyers on ALL-board nets and only takes their Regular VWAP.
-- Here: (a) all boards end to end; (b) q19 mixed; (c) Regular end to end (ranking on Regular nets, Regular VWAP).
WITH b AS (
  SELECT ticker, broker, sum(net_value)::float8 n, sum(buy_value)::float8 bv, sum(buy_lots)::float8 bl,
         coalesce(sum(net_value) FILTER (WHERE market_board = 'Regular'), 0)::float8 n_r,
         sum(buy_value) FILTER (WHERE market_board = 'Regular')::float8 bv_r, sum(buy_lots) FILTER (WHERE market_board = 'Regular')::float8 bl_r
  FROM "Feature_05_Foreign_Domestic_Broker_Detail"
  WHERE trade_date BETWEEN DATE '2026-10-14' AND DATE '2026-10-27'
  GROUP BY ticker, broker
), r AS (
  SELECT b.*, row_number() OVER (PARTITION BY ticker ORDER BY n DESC, broker) ra, row_number() OVER (PARTITION BY ticker ORDER BY n_r DESC, broker) rr FROM b
), t AS (
  SELECT ticker,
    sum(bv) FILTER (WHERE ra <= 3 AND n > 0) / nullif(100 * sum(bl) FILTER (WHERE ra <= 3 AND n > 0), 0) vw_all,
    sum(bv_r) FILTER (WHERE ra <= 3 AND n > 0) / nullif(100 * sum(bl_r) FILTER (WHERE ra <= 3 AND n > 0), 0) vw_mixed,
    sum(bv_r) FILTER (WHERE rr <= 3 AND n_r > 0) / nullif(100 * sum(bl_r) FILTER (WHERE rr <= 3 AND n_r > 0), 0) vw_reg
  FROM r GROUP BY ticker
), q AS (
  SELECT t.ticker, 100 * (p.close / nullif(vw_all, 0) - 1)::float8 d_all, 100 * (p.close / nullif(vw_mixed, 0) - 1)::float8 d_mixed,
         100 * (p.close / nullif(vw_reg, 0) - 1)::float8 d_reg
  FROM t JOIN "IDX_Stock_Universe" u ON u."Ticker" = t.ticker AND u."Security Type" = 'stock'
  JOIN "Price_Stock_Indonesia_IDX" p ON p.ticker = t.ticker AND p.date = DATE '2026-10-27' AND p.timeframe = 'Daily'
)
SELECT count(*) n, count(d_reg) reg_n,
  count(*) FILTER (WHERE abs(d_all - d_mixed) > 1) all_vs_mixed_gt1, count(*) FILTER (WHERE abs(d_all - d_mixed) > 5) all_vs_mixed_gt5,
  count(*) FILTER (WHERE abs(d_all - d_reg) > 1) all_vs_reg_gt1, count(*) FILTER (WHERE abs(d_all - d_reg) > 5) all_vs_reg_gt5,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY d_reg)::numeric, 2) reg_p50, round(min(d_reg)::numeric, 2) reg_min, round(max(d_reg)::numeric, 2) reg_max,
  round(percentile_cont(0.1) WITHIN GROUP (ORDER BY d_reg)::numeric, 2) reg_p10, round(percentile_cont(0.9) WITHIN GROUP (ORDER BY d_reg)::numeric, 2) reg_p90,
  round(max(d_reg) FILTER (WHERE ticker = 'BYAN')::numeric, 2) byan_reg, round(max(d_reg) FILTER (WHERE ticker = 'CARE')::numeric, 2) care_reg,
  round(max(d_reg) FILTER (WHERE ticker = 'BBCA')::numeric, 2) bbca_reg
FROM q
