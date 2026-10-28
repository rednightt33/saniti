EXPLAIN (ANALYZE, BUFFERS) SELECT ticker, market_board, foreign_net_value, total_buy_value, institutional_net_value, retail_net_value
FROM "Feature_03_Stock_Broker_Daily" WHERE date = DATE '2025-03-14'
