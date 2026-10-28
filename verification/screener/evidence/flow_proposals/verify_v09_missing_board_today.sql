-- 16.3 "Windows" rule: stocks whose Nego/Tunai boards had foreign net inside the 20 sessions but no row on 2026-10-27, so
-- adding the stored per-board 20-day columns of the latest rows silently drops that flow; and a cross-check of the stored
-- F06 sum for one example.
WITH w AS (
  SELECT ticker,
    sum(foreign_net_value) FILTER (WHERE market_board <> 'Regular')::float8 fx20,
    bool_or(market_board <> 'Regular' AND date = DATE '2026-10-27') x_today,
    sum(foreign_net_value)::float8 f20
  FROM "Feature_03_Stock_Broker_Daily" WHERE date BETWEEN DATE '2026-09-30' AND DATE '2026-10-27' GROUP BY ticker
), u AS (SELECT w.* FROM w JOIN "IDX_Stock_Universe" s ON s."Ticker" = w.ticker AND s."Security Type" = 'stock')
SELECT count(*) FILTER (WHERE fx20 <> 0 AND NOT x_today) n_dropped, count(*) FILTER (WHERE abs(fx20) >= 1e9 AND NOT x_today) n_dropped_ge_1b,
  (SELECT string_agg(ticker || ' ' || round((fx20 / 1e9)::numeric, 2) || ' of ' || round((f20 / 1e9)::numeric, 2), '; ' ORDER BY abs(fx20) DESC)
   FROM (SELECT * FROM u WHERE NOT x_today AND fx20 <> 0 ORDER BY abs(fx20) DESC LIMIT 4) e) top_examples_rpb
FROM u
