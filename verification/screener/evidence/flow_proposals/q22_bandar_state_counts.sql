WITH b AS (
  SELECT ticker, broker,
         sum(net_value) FILTER (WHERE trade_date >= DATE '2026-10-14')::float8 n10,
         sum(buy_value) FILTER (WHERE trade_date >= DATE '2026-10-14')::float8 bv10, sum(buy_value)::float8 bv20, sum(net_value)::float8 n20
  FROM "Feature_05_Foreign_Domestic_Broker_Detail"
  WHERE trade_date BETWEEN DATE '2026-09-30' AND DATE '2026-10-27'
  GROUP BY ticker, broker
), r AS (
  SELECT b.*, row_number() OVER (PARTITION BY ticker ORDER BY n10 DESC NULLS LAST, broker) b10,
              row_number() OVER (PARTITION BY ticker ORDER BY n10 ASC NULLS LAST, broker) s10 FROM b
), t AS (
  SELECT ticker, sum(bv20) / 20 adv20,
    100 * (coalesce(sum(n10) FILTER (WHERE b10 <= 3 AND n10 > 0), 0) + coalesce(sum(n10) FILTER (WHERE s10 <= 3 AND n10 < 0), 0)) / nullif(sum(bv10), 0) fl09,
    count(*) FILTER (WHERE n20 > 0)::float8 / nullif(count(*) FILTER (WHERE n20 <> 0), 0) fl12
  FROM r GROUP BY ticker
), q AS (
  SELECT t.* FROM t JOIN "IDX_Stock_Universe" u ON u."Ticker" = t.ticker AND u."Security Type" = 'stock'
  WHERE EXISTS (SELECT 1 FROM "Feature_03_Stock_Broker_Daily" f WHERE f.ticker = t.ticker AND f.date = DATE '2026-10-27')
)
SELECT count(*) n,
  count(*) FILTER (WHERE fl09 >= 10) big_acc, count(*) FILTER (WHERE fl09 >= 6 AND fl09 < 10) acc,
  count(*) FILTER (WHERE fl09 > -6 AND fl09 < 6) neutral, count(*) FILTER (WHERE fl09 <= -6 AND fl09 > -10) dist, count(*) FILTER (WHERE fl09 <= -10) big_dist,
  count(*) FILTER (WHERE fl09 >= 6 AND adv20 >= 1e9) acc_or_big_adv1b, count(*) FILTER (WHERE adv20 >= 1e9) adv1b,
  count(*) FILTER (WHERE fl09 >= 6 AND fl12 < 0.5) acc_and_narrow, count(*) FILTER (WHERE fl09 >= 6 AND fl12 < 0.5 AND adv20 >= 1e9) acc_narrow_adv1b
FROM q
