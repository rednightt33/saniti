EXPLAIN (ANALYZE, BUFFERS) SELECT ticker, broker, investor_type, market_board, buy_value, sell_value, buy_lots, sell_lots, buy_freq, sell_freq
FROM "Feature_05_Foreign_Domestic_Broker_Detail" WHERE trade_date = DATE '2026-08-20';;
EXPLAIN (ANALYZE, BUFFERS) SELECT ticker, market_board, foreign_buy_1d, foreign_sell_1d, domestic_buy_1d, domestic_sell_1d, foreign_buy_freq_1d, domestic_buy_freq_1d
FROM "Feature_06_Foreign_Domestic" WHERE trade_date = DATE '2026-08-20'
