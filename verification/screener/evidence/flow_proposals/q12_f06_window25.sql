WITH d AS (
  SELECT ticker, trade_date,
         sum(foreign_buy_1d + foreign_sell_1d) fg, sum(foreign_buy_1d + domestic_buy_1d) t,
         sum(foreign_buy_freq_1d + domestic_buy_freq_1d) tr,
         sum(foreign_buy_1d + domestic_buy_1d) FILTER (WHERE market_board = 'Regular') t_reg,
         sum(foreign_buy_freq_1d + domestic_buy_freq_1d) FILTER (WHERE market_board = 'Regular') tr_reg
  FROM "Feature_06_Foreign_Domestic"
  WHERE trade_date BETWEEN DATE '2026-09-23' AND DATE '2026-10-27'
  GROUP BY ticker, trade_date
), cal AS (
  SELECT trade_date, row_number() OVER (ORDER BY trade_date DESC) k FROM (SELECT DISTINCT trade_date FROM d) x
), g AS (
  SELECT u.ticker, c.k, coalesce(d.fg,0) fg, coalesce(d.t,0) t, coalesce(d.tr,0) tr, coalesce(d.t_reg,0) t_reg, coalesce(d.tr_reg,0) tr_reg,
         d.ticker IS NOT NULL traded
  FROM (SELECT DISTINCT ticker FROM d) u CROSS JOIN cal c LEFT JOIN d ON d.ticker = u.ticker AND d.trade_date = c.trade_date
), q AS (
  SELECT ticker,
    bool_or(traded) FILTER (WHERE k = 1) traded_today,
    50 * sum(fg) FILTER (WHERE k <= 20) / nullif(sum(t) FILTER (WHERE k <= 20), 0) fl03_20,
    sum(tr) FILTER (WHERE k = 1) / nullif(avg(tr) FILTER (WHERE k BETWEEN 2 AND 21), 0) fl16,
    sum(tr_reg) FILTER (WHERE k = 1) / nullif(avg(tr_reg) FILTER (WHERE k BETWEEN 2 AND 21), 0) fl16_reg,
    100 * ((sum(t) FILTER (WHERE k <= 5) / nullif(sum(tr) FILTER (WHERE k <= 5), 0))
         / nullif(sum(t) FILTER (WHERE k BETWEEN 6 AND 25) / nullif(sum(tr) FILTER (WHERE k BETWEEN 6 AND 25), 0), 0) - 1) fl17,
    100 * ((sum(t_reg) FILTER (WHERE k <= 5) / nullif(sum(tr_reg) FILTER (WHERE k <= 5), 0))
         / nullif(sum(t_reg) FILTER (WHERE k BETWEEN 6 AND 25) / nullif(sum(tr_reg) FILTER (WHERE k BETWEEN 6 AND 25), 0), 0) - 1) fl17_reg,
    sum(t) FILTER (WHERE k <= 20) / nullif(sum(tr) FILTER (WHERE k <= 20), 0) / 1e6 ticket20_m,
    sum(t_reg) FILTER (WHERE k <= 20) / nullif(sum(tr_reg) FILTER (WHERE k <= 20), 0) / 1e6 ticket20_reg_m
  FROM g GROUP BY ticker
), r AS (
  SELECT q.* FROM q JOIN "IDX_Stock_Universe" u ON u."Ticker" = q.ticker AND u."Security Type" = 'stock' WHERE q.traded_today
)
SELECT m.name, count(m.v) n, round(min(m.v)::numeric, 3) mn,
  round(percentile_cont(0.1) WITHIN GROUP (ORDER BY m.v)::numeric, 3) p10,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY m.v)::numeric, 3) p50,
  round(percentile_cont(0.9) WITHIN GROUP (ORDER BY m.v)::numeric, 3) p90,
  round(max(m.v)::numeric, 3) mx,
  round(max(m.v) FILTER (WHERE r.ticker = 'BBCA')::numeric, 3) bbca,
  round(max(m.v) FILTER (WHERE r.ticker = 'ANTM')::numeric, 3) antm,
  round(max(m.v) FILTER (WHERE r.ticker = 'CARE')::numeric, 3) care,
  count(*) FILTER (WHERE m.v IS NULL) nulls
FROM r CROSS JOIN LATERAL (VALUES
  ('FL03 foreign participation % 20 (all boards)', r.fl03_20),
  ('FL16 trade-count spike x (all boards)', r.fl16),
  ('FL16 ref: trade-count spike x (Regular)', r.fl16_reg),
  ('FL17 avg trade size change % 5 vs prior 20 (all boards)', r.fl17),
  ('FL17 ref: avg trade size change % (Regular)', r.fl17_reg),
  ('ref: avg trade size 20 (Rp M, all boards)', r.ticket20_m),
  ('ref: avg trade size 20 (Rp M, Regular)', r.ticket20_reg_m)
) m(name, v)
GROUP BY m.name ORDER BY m.name
