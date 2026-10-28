WITH d AS (
  SELECT ticker, date,
         sum(foreign_net_value) f, sum(total_buy_value) t,
         sum(foreign_net_value) FILTER (WHERE market_board = 'Regular') f_reg,
         sum(total_buy_value)  FILTER (WHERE market_board = 'Regular') t_reg,
         sum(total_buy_value)  FILTER (WHERE market_board <> 'Regular') tx,
         sum(institutional_net_value) inst, sum(retail_net_value) ret
  FROM "Feature_03_Stock_Broker_Daily"
  WHERE date BETWEEN DATE '2026-07-31' AND DATE '2026-10-27'
  GROUP BY ticker, date
), cal AS (
  SELECT date, row_number() OVER (ORDER BY date DESC) k FROM (SELECT DISTINCT date FROM d) x
), g AS (
  SELECT u.ticker, c.k, coalesce(d.f,0) f, coalesce(d.t,0) t, coalesce(d.f_reg,0) f_reg, coalesce(d.t_reg,0) t_reg,
         coalesce(d.tx,0) tx, coalesce(d.inst,0) inst, coalesce(d.ret,0) ret, d.ticker IS NOT NULL traded
  FROM (SELECT DISTINCT ticker FROM d) u CROSS JOIN cal c LEFT JOIN d ON d.ticker = u.ticker AND d.date = c.date
), q AS (
  SELECT g.ticker,
    bool_or(traded) FILTER (WHERE k = 1) traded_today,
    count(*) FILTER (WHERE k <= 20 AND traded) sess20,
    sum(f) FILTER (WHERE k <= 5) / 1e9 fl01_5_b,
    sum(f) FILTER (WHERE k <= 20) / 1e9 fl01_20_b,
    sum(f_reg) FILTER (WHERE k <= 20) / 1e9 fl01_20_reg_b,
    100 * sum(f) FILTER (WHERE k <= 20) / nullif(sum(t) FILTER (WHERE k <= 20), 0) fl02_20,
    100 * sum(f_reg) FILTER (WHERE k <= 20) / nullif(sum(t_reg) FILTER (WHERE k <= 20), 0) fl02_20_reg,
    coalesce(min(k) FILTER (WHERE NOT f > 0), 62) - 1 pos_run,
    coalesce(min(k) FILTER (WHERE NOT f < 0), 62) - 1 neg_run,
    100 * sum(tx) FILTER (WHERE k <= 20) / nullif(sum(t) FILTER (WHERE k <= 20), 0) fl18_20,
    100 * sum(tx) FILTER (WHERE k = 1) / nullif(sum(t) FILTER (WHERE k = 1), 0) fl18_1,
    100 * (sum(inst) FILTER (WHERE k <= 20) - sum(ret) FILTER (WHERE k <= 20)) / nullif(sum(t) FILTER (WHERE k <= 20), 0) fl19_20,
    sum(t) FILTER (WHERE k <= 20) / 20 / 1e9 adv20_all_b
  FROM g GROUP BY g.ticker
), r AS (
  SELECT q.*, CASE WHEN pos_run > 0 THEN least(pos_run, 60) WHEN neg_run > 0 THEN -least(neg_run, 60) ELSE 0 END fl04
  FROM q JOIN "IDX_Stock_Universe" u ON u."Ticker" = q.ticker AND u."Security Type" = 'stock'
  WHERE q.traded_today
)
SELECT m.name, count(m.v) n, round(min(m.v)::numeric, 3) mn,
  round(percentile_cont(0.1) WITHIN GROUP (ORDER BY m.v)::numeric, 3) p10,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY m.v)::numeric, 3) p50,
  round(percentile_cont(0.9) WITHIN GROUP (ORDER BY m.v)::numeric, 3) p90,
  round(max(m.v)::numeric, 3) mx,
  round(max(m.v) FILTER (WHERE r.ticker = 'BBCA')::numeric, 3) bbca,
  round(max(m.v) FILTER (WHERE r.ticker = 'ANTM')::numeric, 3) antm,
  round(max(m.v) FILTER (WHERE r.ticker = 'CARE')::numeric, 3) care
FROM r CROSS JOIN LATERAL (VALUES
  ('FL01 foreign net 5 (Rp B, all boards)', r.fl01_5_b),
  ('FL01 foreign net 20 (Rp B, all boards)', r.fl01_20_b),
  ('FL01 ref: foreign net 20 (Rp B, Regular)', r.fl01_20_reg_b),
  ('FL02 foreign net % value 20 (all boards)', r.fl02_20),
  ('FL02 ref: foreign net % value 20 (Regular)', r.fl02_20_reg),
  ('FL04 foreign streak signed (all boards)', r.fl04::float8),
  ('FL18 crossing share % 20 (Nego+Tunai)', r.fl18_20),
  ('FL18 crossing share % 1d (Nego+Tunai)', r.fl18_1),
  ('FL19 inst-heavy minus retail-heavy net % value 20', r.fl19_20),
  ('ref: sessions traded in 20', r.sess20::float8),
  ('ref: ADV20 all boards (Rp B)', r.adv20_all_b)
) m(name, v)
GROUP BY m.name ORDER BY m.name
