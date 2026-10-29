WITH d AS (
  SELECT ticker, date, sum(foreign_net_value)::float8 f, bool_or(market_board <> 'Regular') has_x
  FROM "Feature_03_Stock_Broker_Daily"
  WHERE date BETWEEN DATE '2025-08-29' AND DATE '2026-10-27'
  GROUP BY ticker, date
), r AS (
  SELECT ticker, date, has_x,
    sum(f) OVER w20 r20, count(*) OVER w20 c20
  FROM d WINDOW w20 AS (PARTITION BY ticker ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)
), z AS (
  SELECT ticker, date, r20, c20,
    avg(r20) FILTER (WHERE c20 = 20) OVER wp mu, stddev_samp(r20) FILTER (WHERE c20 = 20) OVER wp sd,
    count(*) FILTER (WHERE c20 = 20) OVER wp n_prior,
    bool_or(has_x) OVER (PARTITION BY ticker) any_x
  FROM r WINDOW wp AS (PARTITION BY ticker ORDER BY date ROWS BETWEEN 252 PRECEDING AND 1 PRECEDING)
), q AS (
  SELECT z.ticker, CASE WHEN z.c20 = 20 AND z.n_prior = 252 AND z.sd > 0 THEN (z.r20 - z.mu) / z.sd END fl05, z.any_x,
         s.foreign_net_zscore_20d_base252d::float8 stored_reg
  FROM z
  JOIN "IDX_Stock_Universe" u ON u."Ticker" = z.ticker AND u."Security Type" = 'stock'
  LEFT JOIN "Feature_06_Foreign_Domestic" s ON s.ticker = z.ticker AND s.trade_date = DATE '2026-10-27' AND s.market_board = 'Regular'
  WHERE z.date = DATE '2026-10-27'
)
SELECT 'FL05 foreign net 20 z-score vs prior 252 (all boards, ticker sessions)' name, count(fl05) n, round(min(fl05)::numeric,3) mn,
  round(percentile_cont(0.1) WITHIN GROUP (ORDER BY fl05)::numeric,3) p10, round(percentile_cont(0.5) WITHIN GROUP (ORDER BY fl05)::numeric,3) p50,
  round(percentile_cont(0.9) WITHIN GROUP (ORDER BY fl05)::numeric,3) p90, round(max(fl05)::numeric,3) mx,
  round(max(fl05) FILTER (WHERE ticker='BBCA')::numeric,3) bbca, round(max(fl05) FILTER (WHERE ticker='ANTM')::numeric,3) antm, round(max(fl05) FILTER (WHERE ticker='CARE')::numeric,3) care,
  count(*) FILTER (WHERE fl05 IS NULL) nulls,
  count(*) FILTER (WHERE NOT any_x AND fl05 IS NOT NULL AND stored_reg IS NOT NULL) parity_pop,
  count(*) FILTER (WHERE NOT any_x AND abs(fl05 - stored_reg) < 1e-6) parity_equal,
  count(*) FILTER (WHERE any_x AND fl05 IS NOT NULL AND stored_reg IS NOT NULL AND abs(fl05 - stored_reg) >= 0.5) board_diff_ge_half_sigma,
  round(max(stored_reg) FILTER (WHERE ticker='CARE')::numeric,3) care_stored_regular
FROM q
