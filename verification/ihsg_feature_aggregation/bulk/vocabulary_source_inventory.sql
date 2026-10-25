SELECT jsonb_build_object('checked_at',clock_timestamp(),'read_only',current_setting('default_transaction_read_only'),
 'columns',jsonb_agg(to_jsonb(f)||jsonb_build_object('ordinal_position',c.ordinal_position)
 ORDER BY f.feature_table,c.ordinal_position))
FROM public."Feature_Catalog" f JOIN information_schema.columns c
ON c.table_schema='public' AND c.table_name=f.feature_table AND c.column_name=f.feature_column
WHERE f.is_active AND f.feature_table IN (
 'Feature_01_Stock_Daily','Feature_02_Broker_Rolling','Feature_03_Stock_Broker_Daily',
 'Feature_05_Foreign_Domestic_Broker_Detail','Feature_06_Foreign_Domestic',
 'Feature_01_Stock_Daily_INDEX','Feature_02_Broker_Rolling_INDEX','Feature_03_Stock_Broker_Daily_INDEX',
 'Feature_05_Foreign_Domestic_Broker_Detail_INDEX','Feature_06_Foreign_Domestic_INDEX');
