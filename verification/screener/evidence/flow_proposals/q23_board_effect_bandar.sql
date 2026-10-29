WITH b AS (
  SELECT ticker, broker,
         sum(net_value)::float8 n_all, sum(buy_value)::float8 bv_all,
         coalesce(sum(net_value) FILTER (WHERE market_board = 'Regular'), 0)::float8 n_reg,
         coalesce(sum(buy_value) FILTER (WHERE market_board = 'Regular'), 0)::float8 bv_reg
  FROM "Feature_05_Foreign_Domestic_Broker_Detail"
  WHERE trade_date BETWEEN DATE '2026-10-14' AND DATE '2026-10-27'
  GROUP BY ticker, broker
), r AS (
  SELECT b.*,
    row_number() OVER (PARTITION BY ticker ORDER BY n_all DESC, broker) ba, row_number() OVER (PARTITION BY ticker ORDER BY n_all ASC, broker) sa,
    row_number() OVER (PARTITION BY ticker ORDER BY n_reg DESC, broker) br, row_number() OVER (PARTITION BY ticker ORDER BY n_reg ASC, broker) sr
  FROM b
), t AS (
  SELECT ticker,
    100 * (coalesce(sum(n_all) FILTER (WHERE ba <= 3 AND n_all > 0), 0) + coalesce(sum(n_all) FILTER (WHERE sa <= 3 AND n_all < 0), 0)) / nullif(sum(bv_all), 0) fl09_all,
    100 * (coalesce(sum(n_reg) FILTER (WHERE br <= 3 AND n_reg > 0), 0) + coalesce(sum(n_reg) FILTER (WHERE sr <= 3 AND n_reg < 0), 0)) / nullif(sum(bv_reg), 0) fl09_reg,
    (array_agg(broker ORDER BY n_all DESC, broker))[1] top_all, (array_agg(broker ORDER BY n_reg DESC, broker))[1] top_reg
  FROM r GROUP BY ticker
), q AS (
  SELECT t.*,
    CASE WHEN fl09_all >= 10 THEN 2 WHEN fl09_all >= 6 THEN 1 WHEN fl09_all <= -10 THEN -2 WHEN fl09_all <= -6 THEN -1 ELSE 0 END st_all,
    CASE WHEN fl09_reg >= 10 THEN 2 WHEN fl09_reg >= 6 THEN 1 WHEN fl09_reg <= -10 THEN -2 WHEN fl09_reg <= -6 THEN -1 ELSE 0 END st_reg
  FROM t JOIN "IDX_Stock_Universe" u ON u."Ticker" = t.ticker AND u."Security Type" = 'stock'
  WHERE EXISTS (SELECT 1 FROM "Feature_03_Stock_Broker_Daily" f WHERE f.ticker = t.ticker AND f.date = DATE '2026-10-27')
)
SELECT count(*) n, count(*) FILTER (WHERE st_all <> st_reg) state_differs, count(*) FILTER (WHERE sign(st_all) * sign(st_reg) < 0) state_flips,
       count(*) FILTER (WHERE abs(fl09_all - coalesce(fl09_reg, 0)) > 2) diff_gt_2pt, count(*) FILTER (WHERE top_all <> top_reg) top_buyer_differs,
       max(fl09_all) FILTER (WHERE ticker = 'CARE') care_all, max(fl09_reg) FILTER (WHERE ticker = 'CARE') care_reg,
       max(top_all) FILTER (WHERE ticker = 'CARE') || '/' || max(top_reg) FILTER (WHERE ticker = 'CARE') care_top_all_reg
FROM q
