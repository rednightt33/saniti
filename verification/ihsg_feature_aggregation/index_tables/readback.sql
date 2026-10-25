SELECT json_build_object(
'feature1',(SELECT json_agg(x) FROM (SELECT * FROM public."Feature_01_Stock_Daily_INDEX" WHERE ticker='IHSG')x),
'feature2',(SELECT json_agg(x) FROM (SELECT * FROM public."Feature_02_Broker_Rolling_INDEX" WHERE ticker='IHSG')x),
'feature3',(SELECT json_agg(x) FROM (SELECT * FROM public."Feature_03_Stock_Broker_Daily_INDEX" WHERE ticker='IHSG')x),
'feature4',(SELECT json_agg(x) FROM (SELECT * FROM public."Feature_04_Technical_Indicator_INDEX" WHERE ticker='IHSG')x),
'feature5',(SELECT json_agg(x) FROM (SELECT * FROM public."Feature_05_Foreign_Domestic_Broker_Detail_INDEX" WHERE ticker='IHSG')x),
'feature6',(SELECT json_agg(x) FROM (SELECT * FROM public."Feature_06_Foreign_Domestic_INDEX" WHERE ticker='IHSG')x),
'legacy_counts',json_build_object('feature1',(SELECT count(*) FROM public."Feature_01_Stock_Daily" WHERE ticker='IHSG'),'feature2',(SELECT count(*) FROM public."Feature_02_Broker_Rolling" WHERE ticker='IHSG'),'feature3',(SELECT count(*) FROM public."Feature_03_Stock_Broker_Daily" WHERE ticker='IHSG'),'feature4',(SELECT count(*) FROM public."Feature_04_Technical_Indicator" WHERE ticker='IHSG'),'feature5',(SELECT count(*) FROM public."Feature_05_Foreign_Domestic_Broker_Detail" WHERE ticker='IHSG'),'feature6',(SELECT count(*) FROM public."Feature_06_Foreign_Domestic" WHERE ticker='IHSG')),
'source_prices',(SELECT json_build_object('rows',count(*),'first',min(date),'last',max(date)) FROM public."Price_Stock_Indonesia_IDX" WHERE ticker='IHSG'),
'catalog_counts',(SELECT json_agg(x ORDER BY feature_table) FROM(SELECT feature_table,count(*) AS active_columns FROM public."Feature_Catalog" WHERE is_active AND feature_table IN ('Feature_01_Stock_Daily_INDEX','Feature_02_Broker_Rolling_INDEX','Feature_03_Stock_Broker_Daily_INDEX','Feature_04_Technical_Indicator_INDEX','Feature_05_Foreign_Domestic_Broker_Detail_INDEX','Feature_06_Foreign_Domestic_INDEX') GROUP BY 1)x));
