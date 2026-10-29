-- M157 share of Regular rows with total buy <> total sell (= foreign + domestic net <> 0), 2016-2020, from Feature 03
-- (bounded by date; the report says "about 7 %").
SELECT extract(year FROM date)::int yr, count(*) rows, count(*) FILTER (WHERE total_buy_value <> total_sell_value) unequal,
       round(100.0 * count(*) FILTER (WHERE total_buy_value <> total_sell_value) / count(*), 2) pct
FROM "Feature_03_Stock_Broker_Daily" WHERE date BETWEEN DATE '2016-01-01' AND DATE '2020-12-31' AND market_board = 'Regular'
GROUP BY ROLLUP (1) ORDER BY 1 NULLS LAST
