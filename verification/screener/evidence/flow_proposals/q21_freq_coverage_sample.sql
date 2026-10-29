SELECT trade_date, count(*) rows, count(*) FILTER (WHERE foreign_buy_freq_1d IS NULL OR domestic_buy_freq_1d IS NULL) freq_null,
       count(*) FILTER (WHERE (foreign_buy_freq_1d IS NULL OR domestic_buy_freq_1d IS NULL) AND length(ticker) = 4) freq_null_4letter
FROM "Feature_06_Foreign_Domestic"
WHERE trade_date IN (DATE '2016-06-15', DATE '2018-06-13', DATE '2020-06-15', DATE '2022-06-15', DATE '2024-06-14', DATE '2025-06-13', DATE '2026-03-16')
  AND market_board = 'Regular'
GROUP BY trade_date ORDER BY trade_date;;
SELECT broker_classification, count(*) n, string_agg(broker_code, ',' ORDER BY broker_code) FILTER (WHERE broker_code IN ('YP','XL','CC','PD','KK','YU','ZP','AK','BK','RX','DX','MG','LG','CS','KZ','SQ','AP','NI','OD','DR','EP','XC','GR')) sample
FROM "IDX_Broker_Profile" GROUP BY 1 ORDER BY 1
