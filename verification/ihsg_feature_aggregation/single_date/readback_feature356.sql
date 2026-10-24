SELECT json_build_object(
 'feature3',(SELECT json_agg(x ORDER BY market_board) FROM (SELECT * FROM public."Feature_03_Stock_Broker_Daily" WHERE ticker='IHSG' ORDER BY date,market_board)x),
 'feature5',(SELECT json_agg(x ORDER BY market_board,broker,investor_type) FROM (SELECT * FROM public."Feature_05_Foreign_Domestic_Broker_Detail" WHERE ticker='IHSG' ORDER BY trade_date,market_board,broker,investor_type)x),
 'feature6',(SELECT json_agg(x ORDER BY market_board) FROM (SELECT * FROM public."Feature_06_Foreign_Domestic" WHERE ticker='IHSG' ORDER BY trade_date,market_board)x),
 'feature2',(SELECT count(*) FROM public."Feature_02_Broker_Rolling" WHERE ticker='IHSG'),
 'feature4',(SELECT json_build_object('count',count(*),'fingerprint',md5(string_agg(row_to_json(x)::text,'|' ORDER BY trade_date,asset_type))) FROM (SELECT * FROM public."Feature_04_Technical_Indicator" WHERE ticker='IHSG')x));
