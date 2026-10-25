-- Caller owns the transaction and snapshots the accepted INDEX rows before this migration.
-- User approved 2026-10-25. F06 coverage and all numerical frequency semantics are retained.
ALTER TABLE public."Feature_05_Foreign_Domestic_Broker_Detail_INDEX"
 DROP COLUMN IF EXISTS frequency_source_rows,
 DROP COLUMN IF EXISTS buy_freq_known_rows,
 DROP COLUMN IF EXISTS sell_freq_known_rows,
 DROP COLUMN IF EXISTS buy_freq_missing_rows,
 DROP COLUMN IF EXISTS sell_freq_missing_rows;

UPDATE public."Feature_Catalog" SET is_active=false
WHERE feature_table='Feature_05_Foreign_Domestic_Broker_Detail_INDEX'
AND feature_column IN ('frequency_source_rows','buy_freq_known_rows','sell_freq_known_rows',
 'buy_freq_missing_rows','sell_freq_missing_rows') AND is_active;
DELETE FROM public."Column_Catalog"
WHERE table_schema='public' AND table_name='Feature_05_Foreign_Domestic_Broker_Detail_INDEX'
AND column_name IN ('frequency_source_rows','buy_freq_known_rows','sell_freq_known_rows',
 'buy_freq_missing_rows','sell_freq_missing_rows');
COMMENT ON COLUMN public."Feature_05_Foreign_Domestic_Broker_Detail_INDEX".buy_freq IS
 'SUM of known raw buy frequencies across source symbols; all unknown -> NULL. Partial coverage is checked internally and in Feature06 INDEX coverage, not stored as five extra Feature05 columns.';
COMMENT ON COLUMN public."Feature_05_Foreign_Domestic_Broker_Detail_INDEX".sell_freq IS
 'SUM of known raw sell frequencies across source symbols; all unknown -> NULL. Never fill unknown frequency with zero.';

-- Correct copied prose before it is used in the frontend vocabulary.
UPDATE public."Feature_Catalog" SET misuse_warning=
 'Missing index volume is NULL, never a synthetic zero. Ordinary stock volume must exist. Volume-dependent metrics remain NULL when their required observations are unavailable.'
WHERE feature_table IN ('Feature_01_Stock_Daily','Feature_01_Stock_Daily_INDEX')
AND feature_column='volume' AND is_active;
UPDATE public."Feature_Catalog" SET
 definition=CASE feature_column WHEN 'foreign_cumulative_net' THEN
 'Running total of aggregate foreign net value from the first available broker-source session, including historical symbols absent on the output date.' ELSE
 'Running total of aggregate domestic net value from the first available broker-source session, including historical symbols absent on the output date.' END,
 analytical_interpretation='Aggregate historical net balance over the declared all-source-symbol broker universe and one board, not just symbols trading on the current date.',
 misuse_warning='Baseline is available broker history (currently 2016-01-04), independent of index price history. Do not sum only same-date per-symbol cumulative rows or label this official historical IHSG constituent flow. Raw source imbalances remain flagged.'
WHERE feature_table='Feature_06_Foreign_Domestic_INDEX'
AND feature_column IN ('foreign_cumulative_net','domestic_cumulative_net') AND is_active;

-- Translate cloned references to the dedicated destinations without altering formulas.
UPDATE public."Feature_Catalog" SET
 source_tables=replace(replace(source_tables,'Feature_02_Broker_Rolling','Feature_02_Broker_Rolling_INDEX'),'Feature_05_Foreign_Domestic_Broker_Detail','Feature_05_Foreign_Domestic_Broker_Detail_INDEX'),
 source_columns=replace(replace(source_columns,'Feature_02_Broker_Rolling.','Feature_02_Broker_Rolling_INDEX.'),'Feature_05_Foreign_Domestic_Broker_Detail.','Feature_05_Foreign_Domestic_Broker_Detail_INDEX.')
WHERE feature_table IN ('Feature_03_Stock_Broker_Daily_INDEX','Feature_06_Foreign_Domestic_INDEX')
AND is_active AND source_tables NOT LIKE '%_INDEX%';
UPDATE public."Feature_Catalog" SET null_rule=
 'SUM available source frequencies; all contributing inputs unknown -> NULL. Missingness is validated internally; incomplete source data is never zero-imputed.'
WHERE feature_table='Feature_05_Foreign_Domestic_Broker_Detail_INDEX'
AND feature_column IN ('buy_freq','sell_freq') AND is_active;
UPDATE public."Column_Catalog" c SET definition=f.definition,
 source_column_or_expression=f.calculation,unit=f.unit,null_rule=f.null_rule
FROM public."Feature_Catalog" f WHERE f.is_active AND c.table_schema='public'
AND c.table_name=f.feature_table AND c.column_name=f.feature_column
AND f.feature_table IN ('Feature_01_Stock_Daily','Feature_01_Stock_Daily_INDEX',
 'Feature_03_Stock_Broker_Daily_INDEX','Feature_05_Foreign_Domestic_Broker_Detail_INDEX',
 'Feature_06_Foreign_Domestic_INDEX');
