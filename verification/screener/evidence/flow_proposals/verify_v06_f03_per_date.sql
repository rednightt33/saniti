EXPLAIN (ANALYZE, BUFFERS) SELECT ticker, market_board, foreign_net_value, total_buy_value, institutional_net_value, retail_net_value
FROM "Feature_03_Stock_Broker_Daily" WHERE date = DATE '2025-09-15';;
EXPLAIN (ANALYZE, BUFFERS) SELECT ticker, market_board, foreign_net_value, total_buy_value, institutional_net_value, retail_net_value
FROM "Feature_03_Stock_Broker_Daily" WHERE date = DATE '2025-12-10';;
EXPLAIN (ANALYZE, BUFFERS) SELECT ticker, market_board, foreign_net_value, total_buy_value, institutional_net_value, retail_net_value
FROM "Feature_03_Stock_Broker_Daily" WHERE date = DATE '2026-05-20';;
EXPLAIN (ANALYZE, BUFFERS) SELECT ticker, market_board, foreign_net_value, total_buy_value, institutional_net_value, retail_net_value
FROM "Feature_03_Stock_Broker_Daily" WHERE date = DATE '2026-08-20'
