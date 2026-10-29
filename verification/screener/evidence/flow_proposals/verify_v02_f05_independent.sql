-- Independent recomputation from Feature 05 only (not F03/F06): FL01, FL02, FL03, FL18 at D20; FL08, FL09 (via the
-- identity -(rest)/V) at D10 N3; FL10 effective buyers and FL12 at D20. Window = the 20 market sessions 2026-09-30..10-27.
WITH bt AS (
  SELECT ticker, broker,
    sum(CASE WHEN trade_date >= DATE '2026-10-14' THEN net_value ELSE 0 END)::float8 n10,
    sum(CASE WHEN trade_date >= DATE '2026-10-14' THEN buy_value ELSE 0 END)::float8 v10,
    bool_or(trade_date >= DATE '2026-10-14') act10,
    sum(net_value)::float8 n20, sum(buy_value)::float8 v20,
    sum(CASE WHEN investor_type = 'Foreign' THEN net_value ELSE 0 END)::float8 fn20,
    sum(CASE WHEN investor_type = 'Foreign' THEN buy_value + sell_value ELSE 0 END)::float8 fg20,
    sum(CASE WHEN market_board <> 'Regular' THEN buy_value ELSE 0 END)::float8 x20,
    bool_or(trade_date = DATE '2026-10-27') today
  FROM "Feature_05_Foreign_Domestic_Broker_Detail"
  WHERE trade_date BETWEEN DATE '2026-09-30' AND DATE '2026-10-27'
  GROUP BY ticker, broker
), rk AS (
  SELECT bt.*, rank() OVER (PARTITION BY ticker ORDER BY n10 DESC, broker) rd, rank() OVER (PARTITION BY ticker ORDER BY n10, broker) ra FROM bt
), tk AS (
  SELECT ticker, bool_or(today) today,
    sum(fn20) / 1e9 fl01, 100 * sum(fn20) / nullif(sum(v20), 0) fl02, 50 * sum(fg20) / nullif(sum(v20), 0) fl03,
    100 * sum(x20) / nullif(sum(v20), 0) fl18,
    100 * sum(n10) FILTER (WHERE rd <= 3 AND n10 > 0) / nullif(sum(v10), 0) fl08,
    -100 * coalesce(sum(n10) FILTER (WHERE NOT ((rd <= 3 AND n10 > 0) OR (ra <= 3 AND n10 < 0))), 0) / nullif(sum(v10), 0) fl09_identity,
    abs(sum(n10)) / nullif(sum(v10), 0) all_net_resid10,
    sum(greatest(n20, 0)) ^ 2 / nullif(sum(greatest(n20, 0) ^ 2), 0) fl10_eff,
    avg((n20 > 0)::int) FILTER (WHERE n20 <> 0) fl12
  FROM rk GROUP BY ticker
), pop AS (
  SELECT tk.*, EXISTS (SELECT 1 FROM "Price_Stock_Indonesia_IDX" p WHERE p.ticker = tk.ticker AND p.date = DATE '2026-10-27' AND p.timeframe = 'Daily') has_px
  FROM tk JOIN "IDX_Stock_Universe" u ON u."Ticker" = tk.ticker AND u."Security Type" = 'stock' WHERE tk.today
)
SELECT m.k, count(m.v) n, round(min(m.v)::numeric, 3) mn, round(percentile_cont(0.1) WITHIN GROUP (ORDER BY m.v)::numeric, 3) p10,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY m.v)::numeric, 3) p50, round(percentile_cont(0.9) WITHIN GROUP (ORDER BY m.v)::numeric, 3) p90,
  round(max(m.v)::numeric, 3) mx, round(max(m.v) FILTER (WHERE pop.ticker = 'BBCA')::numeric, 3) bbca,
  round(max(m.v) FILTER (WHERE pop.ticker = 'ANTM')::numeric, 3) antm, round(max(m.v) FILTER (WHERE pop.ticker = 'CARE')::numeric, 3) care,
  count(*) FILTER (WHERE m.v = 0) exact_zero
FROM pop CROSS JOIN LATERAL (VALUES
  ('FL01 D20 Rp B (F05, 832)', fl01, true), ('FL02 D20 % (F05, 832)', fl02, true), ('FL03 D20 % (F05, 832)', fl03, true),
  ('FL18 D20 % (F05, 832)', fl18, true), ('FL08 N3 D10 % (828 with price)', fl08, has_px),
  ('FL09 N3 D10 % via identity (828)', fl09_identity, has_px), ('FL10 effective buyers D20 (828)', fl10_eff, has_px),
  ('FL12 breadth D20 (828)', fl12, has_px), ('check: |sum of all broker nets| / V, D10', all_net_resid10, true)
) m(k, v, inpop)
WHERE m.inpop
GROUP BY m.k ORDER BY m.k
