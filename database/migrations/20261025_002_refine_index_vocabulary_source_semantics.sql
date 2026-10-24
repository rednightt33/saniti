-- Caller-owned transaction. Metadata refinement only, no numeric recalculation or worker change.
UPDATE public."Feature_Catalog" SET definition='Universe-classified index identifier; aggregate source symbols are not copied into the index ticker.',
 calculation='Resolve the requested index ticker from IDX_Stock_Universe where Security Type=index.'
WHERE feature_table IN ('Feature_02_Broker_Rolling_INDEX','Feature_03_Stock_Broker_Daily_INDEX',
 'Feature_05_Foreign_Domestic_Broker_Detail_INDEX','Feature_06_Foreign_Domestic_INDEX')
AND feature_column='ticker' AND is_active;
UPDATE public."Feature_Catalog" SET
 grain=replace(grain,'stock','index'),
 calculation='First aggregate all raw source symbols per date, broker, Investor Type and board. '||calculation,
 source_tables='IDX_Broker_Summary | IDX_Broker_Profile',
 source_columns='IDX_Broker_Summary.Date | IDX_Broker_Summary.Broker | IDX_Broker_Summary.Investor Type | IDX_Broker_Summary.Market Board | IDX_Broker_Summary.Buy Value | IDX_Broker_Summary.Sell Value | IDX_Broker_Summary.Buy Lots | IDX_Broker_Summary.Sell Lots | IDX_Broker_Profile.broker_classification'
WHERE feature_table='Feature_02_Broker_Rolling_INDEX' AND feature_column NOT IN ('ticker','date','calculated_at')
AND is_active AND calculation NOT LIKE 'First aggregate all raw source symbols%';
UPDATE public."Feature_Catalog" SET calculation=
 replace(replace(calculation,'ticker transaction-date calendar','aggregate market-session calendar'),
 'ticker transaction dates','aggregate market sessions')
WHERE feature_table='Feature_02_Broker_Rolling_INDEX' AND is_active;
UPDATE public."Feature_Catalog" SET calculation=CASE feature_column
 WHEN 'buy_value_1d' THEN 'SUM(IDX_Broker_Summary.Buy Value) across all source symbols at date, index, broker, Investor Type and Market Board.'
 WHEN 'sell_value_1d' THEN 'SUM(IDX_Broker_Summary.Sell Value) across all source symbols at date, index, broker, Investor Type and Market Board.'
 WHEN 'net_value_1d' THEN 'buy_value_1d - sell_value_1d after aggregating all raw symbols at date, index, broker, Investor Type and Market Board.'
 WHEN 'buy_lots_1d' THEN 'SUM(IDX_Broker_Summary.Buy Lots) across all source symbols at date, index, broker, Investor Type and Market Board.'
 WHEN 'sell_lots_1d' THEN 'SUM(IDX_Broker_Summary.Sell Lots) across all source symbols at date, index, broker, Investor Type and Market Board.'
 WHEN 'net_lots_1d' THEN 'buy_lots_1d - sell_lots_1d after aggregating all raw symbols at date, index, broker, Investor Type and Market Board.' END
WHERE feature_table='Feature_02_Broker_Rolling_INDEX' AND feature_column IN
 ('buy_value_1d','sell_value_1d','net_value_1d','buy_lots_1d','sell_lots_1d','net_lots_1d') AND is_active;
UPDATE public."Feature_Catalog" SET calculation=CASE feature_column
 WHEN 'buy_value' THEN 'SUM(raw Buy Value) across all source symbols at date, index, broker, Investor Type and Market Board.'
 WHEN 'sell_value' THEN 'SUM(raw Sell Value) across all source symbols at date, index, broker, Investor Type and Market Board.'
 WHEN 'net_value' THEN 'SUM(raw Buy Value) - SUM(raw Sell Value), after index aggregation by date, broker, Investor Type and Market Board.'
 WHEN 'buy_lots' THEN 'SUM(raw Buy Lots) across all source symbols at date, index, broker, Investor Type and Market Board.'
 WHEN 'sell_lots' THEN 'SUM(raw Sell Lots) across all source symbols at date, index, broker, Investor Type and Market Board.'
 WHEN 'net_lots' THEN 'SUM(raw Buy Lots) - SUM(raw Sell Lots), after index aggregation by date, broker, Investor Type and Market Board.' END
WHERE feature_table='Feature_05_Foreign_Domestic_Broker_Detail_INDEX' AND feature_column IN
 ('buy_value','sell_value','net_value','buy_lots','sell_lots','net_lots') AND is_active;
UPDATE public."Feature_Catalog" SET
 calculation='For each raw date/symbol/board test SUM(Buy Value)<>SUM(Sell Value), then BOOL_OR those per-symbol gaps across the contributing index source symbols.',
 definition='True when any contributing source symbol has a buy/sell value imbalance; opposite symbol gaps cannot cancel this flag.'
WHERE feature_table='Feature_05_Foreign_Domestic_Broker_Detail_INDEX' AND feature_column='source_balance_gap' AND is_active;
UPDATE public."Feature_Catalog" SET source_tables='IDX_Broker_Summary',
 source_columns='IDX_Broker_Summary.buy_freq | IDX_Broker_Summary.sell_freq'
WHERE feature_table='Feature_06_Foreign_Domestic_INDEX' AND feature_column IN
 ('frequency_source_rows','buy_freq_known_rows','sell_freq_known_rows','buy_freq_missing_rows','sell_freq_missing_rows') AND is_active;
UPDATE public."Column_Catalog" c SET definition=f.definition,source_column_or_expression=f.calculation,
 unit=f.unit,null_rule=f.null_rule FROM public."Feature_Catalog" f WHERE f.is_active
AND c.table_schema='public' AND c.table_name=f.feature_table AND c.column_name=f.feature_column
AND f.feature_table IN ('Feature_02_Broker_Rolling_INDEX','Feature_03_Stock_Broker_Daily_INDEX',
 'Feature_05_Foreign_Domestic_Broker_Detail_INDEX','Feature_06_Foreign_Domestic_INDEX');
UPDATE public."Table_Catalog" SET source_tables=ARRAY['IDX_Broker_Summary','IDX_Broker_Profile']
WHERE table_schema='public' AND table_name='Feature_02_Broker_Rolling_INDEX';
UPDATE public."Table_Catalog" SET source_tables=ARRAY['Feature_02_Broker_Rolling_INDEX','IDX_Broker_Profile']
WHERE table_schema='public' AND table_name='Feature_03_Stock_Broker_Daily_INDEX';
UPDATE public."Table_Catalog" SET source_tables=ARRAY['Feature_05_Foreign_Domestic_Broker_Detail_INDEX','IDX_Broker_Summary']
WHERE table_schema='public' AND table_name='Feature_06_Foreign_Domestic_INDEX';
DO $comments$
DECLARE t text;
BEGIN
 FOREACH t IN ARRAY ARRAY['Feature_01_Stock_Daily_INDEX','Feature_02_Broker_Rolling_INDEX',
  'Feature_03_Stock_Broker_Daily_INDEX','Feature_04_Technical_Indicator_INDEX',
  'Feature_05_Foreign_Domestic_Broker_Detail_INDEX','Feature_06_Foreign_Domestic_INDEX'] LOOP
  EXECUTE format('COMMENT ON TABLE public.%I IS %L',t,
   'Dedicated universe-index output with validated historical bootstrap. Price and broker source endpoints differ. Broker scope includes all raw source symbols, not official historical constituents. Automatic daily updates are not enabled.');
 END LOOP;
END $comments$;
