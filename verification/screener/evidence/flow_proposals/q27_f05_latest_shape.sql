SELECT market_board, count(*) rows, count(DISTINCT ticker) tickers, count(DISTINCT broker) brokers,
       count(*) FILTER (WHERE buy_value = 0 AND sell_value = 0) zero_rows,
       count(*) FILTER (WHERE buy_freq IS NULL OR sell_freq IS NULL) freq_null,
       count(*) FILTER (WHERE source_balance_gap) gap_rows,
       round(sum(buy_value)::numeric / 1e12, 3) buy_value_t
FROM "Feature_05_Foreign_Domestic_Broker_Detail" WHERE trade_date = DATE '2026-10-27' GROUP BY 1 ORDER BY 1
