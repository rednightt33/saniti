SELECT broker_code, broker_type, broker_classification FROM "IDX_Broker_Profile"
WHERE broker_code IN ('YP','ZP','YU','KK','DR','XL','XC','PD','GR','EP','CC','SQ','AK','AP') ORDER BY broker_classification, broker_code;;
SELECT broker_type, broker_classification, count(*) FROM "IDX_Broker_Profile" GROUP BY 1,2 ORDER BY 1,2;;
SELECT d, count(DISTINCT f.broker) brokers, count(DISTINCT f.broker) FILTER (WHERE p.broker_code IS NULL) not_in_profile,
       string_agg(DISTINCT f.broker, ',') FILTER (WHERE p.broker_code IS NULL) codes,
       round(100 * sum(f.buy_value) FILTER (WHERE p.broker_code IS NULL) / sum(f.buy_value), 3) pct_value_not_in_profile
FROM (SELECT DATE '2026-10-27' d UNION ALL SELECT DATE '2019-06-14') x
JOIN "Feature_05_Foreign_Domestic_Broker_Detail" f ON f.trade_date = x.d
LEFT JOIN "IDX_Broker_Profile" p ON p.broker_code = f.broker
GROUP BY d ORDER BY d
