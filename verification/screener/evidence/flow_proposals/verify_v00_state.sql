SELECT now() db_now, (SELECT max(trade_date) FROM "Feature_05_Foreign_Domestic_Broker_Detail" WHERE trade_date > DATE '2026-10-20') f05_max,
       (SELECT max(date) FROM "Feature_03_Stock_Broker_Daily" WHERE date > DATE '2026-10-20') f03_max;;
SELECT left(execution_id::text, 8) id, mode, status, started_at, finished_at, broker_rows FROM "Monitoring_Stockbit_Update" ORDER BY started_at DESC LIMIT 3
