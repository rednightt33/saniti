WITH b AS (
  SELECT ticker, broker,
         sum(net_value) FILTER (WHERE trade_date >= DATE '2026-10-14')::float8 n10,
         sum(buy_value) FILTER (WHERE trade_date >= DATE '2026-10-14')::float8 bv10,
         sum(net_value)::float8 n20, sum(buy_value)::float8 bv20, sum(sell_value)::float8 sv20
  FROM "Feature_05_Foreign_Domestic_Broker_Detail"
  WHERE trade_date BETWEEN DATE '2026-09-30' AND DATE '2026-10-27'
  GROUP BY ticker, broker
), r AS (
  SELECT b.*, row_number() OVER (PARTITION BY ticker ORDER BY n10 DESC NULLS LAST, broker) b10,
              row_number() OVER (PARTITION BY ticker ORDER BY n10 ASC NULLS LAST, broker) s10 FROM b
), t AS (
  SELECT ticker, sum(bv20) / 20 adv20,
    100 * coalesce(sum(n10) FILTER (WHERE b10 <= 3 AND n10 > 0), 0) / nullif(sum(bv10), 0) fl08,
    100 * (coalesce(sum(n10) FILTER (WHERE b10 <= 3 AND n10 > 0), 0) + coalesce(sum(n10) FILTER (WHERE s10 <= 3 AND n10 < 0), 0)) / nullif(sum(bv10), 0) fl09,
    sum(greatest(n20, 0) ^ 2) / nullif(sum(greatest(n20, 0)) ^ 2, 0) fl10,
    sum(bv20 ^ 2) / nullif(sum(bv20) ^ 2, 0) hhi_buy,
    sum(bv20 ^ 2) / nullif(sum(bv20) ^ 2, 0) - sum(sv20 ^ 2) / nullif(sum(sv20) ^ 2, 0) fl11,
    count(*) FILTER (WHERE n20 > 0)::float8 / nullif(count(*) FILTER (WHERE n20 <> 0), 0) fl12
  FROM r GROUP BY ticker
), q AS (
  SELECT t.*, ntile(3) OVER (ORDER BY adv20) liq FROM t JOIN "IDX_Stock_Universe" u ON u."Ticker" = t.ticker AND u."Security Type" = 'stock'
  WHERE EXISTS (SELECT 1 FROM "Feature_03_Stock_Broker_Daily" f WHERE f.ticker = t.ticker AND f.date = DATE '2026-10-27')
)
SELECT liq, count(*) n, round((min(adv20)/1e9)::numeric, 3) adv_min_b, round((max(adv20)/1e9)::numeric, 3) adv_max_b,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY fl08)::numeric, 2) fl08_med,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY abs(fl09))::numeric, 2) abs_fl09_med,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY fl10)::numeric, 3) fl10_med,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY hhi_buy)::numeric, 3) hhi_buy_med,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY abs(fl11))::numeric, 4) abs_fl11_med,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY fl12)::numeric, 3) fl12_med,
  round(corr(fl09, fl11)::numeric, 3) corr_fl09_fl11, round(corr(fl09, fl12)::numeric, 3) corr_fl09_fl12
FROM q GROUP BY liq ORDER BY liq
