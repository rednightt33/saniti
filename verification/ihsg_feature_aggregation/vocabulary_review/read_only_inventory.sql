WITH target AS (
 SELECT table_name FROM information_schema.tables WHERE table_schema='public'
 AND table_name IN ('Feature_01_Stock_Daily','Feature_02_Broker_Rolling','Feature_03_Stock_Broker_Daily','Feature_05_Foreign_Domestic_Broker_Detail','Feature_06_Foreign_Domestic',
 'Feature_01_Stock_Daily_INDEX','Feature_02_Broker_Rolling_INDEX','Feature_03_Stock_Broker_Daily_INDEX','Feature_05_Foreign_Domestic_Broker_Detail_INDEX','Feature_06_Foreign_Domestic_INDEX')
), cols AS (
 SELECT c.table_name,c.column_name,c.ordinal_position,c.data_type,c.is_nullable,
 f.version,f.definition,f.calculation,f.unit,f.null_rule,f.lookback_window,f.minimum_history,
 to_jsonb(f)->>'analytical_interpretation' AS analytical_interpretation,
 to_jsonb(f)->>'recommended_use' AS recommended_use,
 to_jsonb(f)->>'misuse_warning' AS misuse_warning,
 to_jsonb(f)->>'semantic_review_status' AS semantic_review_status,
 f.source_tables,f.source_columns,
 to_jsonb(f)->>'validation_evidence' AS validation_evidence
 FROM information_schema.columns c JOIN target t USING(table_name)
 LEFT JOIN public."Feature_Catalog" f ON f.feature_table=c.table_name AND f.feature_column=c.column_name AND f.is_active
 WHERE c.table_schema='public'
)
SELECT jsonb_build_object(
 'checked_at',clock_timestamp(),'read_only',current_setting('default_transaction_read_only'),
 'columns',(SELECT jsonb_agg(to_jsonb(c) ORDER BY table_name,ordinal_position) FROM cols c),
 'catalog_fields',(SELECT jsonb_agg(column_name ORDER BY ordinal_position) FROM information_schema.columns WHERE table_schema='public' AND table_name='Feature_Catalog'),
 'possible_vocabulary_tables',(SELECT jsonb_agg(table_name) FROM information_schema.tables WHERE table_schema='public' AND table_name ~* '(vocab|glossary|dictionary)'),
 'index_counts',jsonb_build_object(
 'Feature01',(SELECT jsonb_build_object('rows',count(*),'first',min(date),'last',max(date)) FROM public."Feature_01_Stock_Daily_INDEX" WHERE ticker='IHSG'),
 'Feature02',(SELECT jsonb_build_object('rows',count(*),'first',min(date),'last',max(date)) FROM public."Feature_02_Broker_Rolling_INDEX" WHERE ticker='IHSG'),
 'Feature03',(SELECT jsonb_build_object('rows',count(*),'first',min(date),'last',max(date)) FROM public."Feature_03_Stock_Broker_Daily_INDEX" WHERE ticker='IHSG'),
 'Feature04',(SELECT jsonb_build_object('rows',count(*),'first',min(trade_date),'last',max(trade_date)) FROM public."Feature_04_Technical_Indicator_INDEX" WHERE ticker='IHSG'),
 'Feature05',(SELECT jsonb_build_object('rows',count(*),'first',min(trade_date),'last',max(trade_date)) FROM public."Feature_05_Foreign_Domestic_Broker_Detail_INDEX" WHERE ticker='IHSG'),
 'Feature06',(SELECT jsonb_build_object('rows',count(*),'first',min(trade_date),'last',max(trade_date)) FROM public."Feature_06_Foreign_Domestic_INDEX" WHERE ticker='IHSG')),
 'price_range',(SELECT jsonb_build_object('rows',count(*),'first',min(date),'last',max(date)) FROM public."Price_Stock_Indonesia_IDX" WHERE ticker='IHSG')
);
