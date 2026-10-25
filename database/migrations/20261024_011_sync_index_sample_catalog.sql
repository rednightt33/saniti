-- Forward-only metadata synchronization after validated INDEX sample initialization.
BEGIN;
UPDATE public."Column_Catalog" c SET definition=f.definition,source_column_or_expression=f.calculation,
 unit=f.unit,null_rule=f.null_rule,updated_at=statement_timestamp()
FROM public."Feature_Catalog" f
WHERE c.table_schema='public' AND c.table_name=f.feature_table AND c.column_name=f.feature_column
AND f.is_active AND f.feature_table IN ('Feature_01_Stock_Daily_INDEX','Feature_02_Broker_Rolling_INDEX','Feature_03_Stock_Broker_Daily_INDEX',
 'Feature_04_Technical_Indicator_INDEX','Feature_05_Foreign_Domestic_Broker_Detail_INDEX','Feature_06_Foreign_Domestic_INDEX');
UPDATE public."Table_Catalog" SET source_tables=ARRAY['Price_Stock_Indonesia_IDX','IDX_Stock_Universe']
WHERE table_schema='public' AND table_name IN ('Feature_01_Stock_Daily_INDEX','Feature_04_Technical_Indicator_INDEX');
UPDATE public."Table_Catalog" SET source_tables=ARRAY['IDX_Broker_Summary','Feature_05_Foreign_Domestic_Broker_Detail','IDX_Broker_Profile']
WHERE table_schema='public' AND table_name='Feature_02_Broker_Rolling_INDEX';
UPDATE public."Table_Catalog" SET source_tables=ARRAY['IDX_Broker_Summary','IDX_Broker_Profile','Feature_02_Broker_Rolling_INDEX']
WHERE table_schema='public' AND table_name='Feature_03_Stock_Broker_Daily_INDEX';
UPDATE public."Table_Catalog" SET source_tables=ARRAY['IDX_Broker_Summary']
WHERE table_schema='public' AND table_name='Feature_05_Foreign_Domestic_Broker_Detail_INDEX';
UPDATE public."Table_Catalog" SET source_tables=ARRAY['IDX_Broker_Summary','Feature_05_Foreign_Domestic_Broker_Detail','Feature_05_Foreign_Domestic_Broker_Detail_INDEX']
WHERE table_schema='public' AND table_name='Feature_06_Foreign_Domestic_INDEX';
COMMIT;
