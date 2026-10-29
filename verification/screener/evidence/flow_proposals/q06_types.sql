SELECT table_name, column_name, data_type FROM information_schema.columns
WHERE (table_name = 'Feature_05_Foreign_Domestic_Broker_Detail' AND column_name IN ('buy_value','net_value','buy_lots','buy_freq'))
   OR (table_name = 'Price_Stock_Indonesia_IDX' AND column_name IN ('ticker','date','timeframe','close','volume','is_final'))
   OR (table_name = 'IDX_Broker_Profile') ORDER BY 1,2
