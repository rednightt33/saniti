SELECT (SELECT max(trade_date) FROM "Feature_05_Foreign_Domestic_Broker_Detail" WHERE trade_date > DATE '2026-10-01') f05_max,
       (SELECT max(trade_date) FROM "Feature_06_Foreign_Domestic" WHERE trade_date > DATE '2026-10-01') f06_max,
       (SELECT max(date) FROM "Feature_03_Stock_Broker_Daily" WHERE date > DATE '2026-10-01') f03_max,
       (SELECT max("Date") FROM "IDX_Broker_Summary" WHERE "Date" > DATE '2026-10-01') bs_max;;
SELECT id, status, started_at, finished_at, token_expires_at FROM "Monitoring_Stockbit_Update" ORDER BY started_at DESC LIMIT 4;;
SELECT d, row_number() OVER (ORDER BY d DESC) k FROM (SELECT DISTINCT date d FROM "Feature_03_Stock_Broker_Daily" WHERE date BETWEEN DATE '2026-06-01' AND DATE '2026-10-31' AND market_board='Regular') x ORDER BY d DESC LIMIT 64
