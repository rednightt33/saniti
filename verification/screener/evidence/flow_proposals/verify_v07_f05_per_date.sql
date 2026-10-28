EXPLAIN (ANALYZE, BUFFERS) SELECT ticker, broker, investor_type, market_board, buy_value, sell_value, buy_lots, sell_lots, buy_freq, sell_freq
FROM "Feature_05_Foreign_Domestic_Broker_Detail" WHERE trade_date = DATE '2026-06-10'
