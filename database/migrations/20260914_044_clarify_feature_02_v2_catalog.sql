-- Clarify the already-active v2 semantic catalog; formulas and stored rows do not change.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='2min';

DO $preflight$
BEGIN
    IF (SELECT count(*) FROM public."Feature_Catalog"
        WHERE feature_table='Feature_02_Broker_Rolling' AND version='v2' AND is_active) <> 38 THEN
        RAISE EXCEPTION 'Expected all 38 Feature 02 v2 definitions to be active';
    END IF;
END
$preflight$;

COMMENT ON COLUMN public."Feature_02_Broker_Rolling".calculated_at IS
    'Database statement timestamp when this canonical v2 row was materialized; not source event time or data availability time.';

UPDATE public."Feature_Catalog"
SET definition=CASE feature_column
      WHEN 'net_value_1d' THEN
        'Buy value minus sell value for this date, ticker, broker, source Investor Type and board. Positive means net buying; negative means net selling.'
      WHEN 'net_lots_1d' THEN
        'Buy lots minus sell lots for this date, ticker, broker, source Investor Type and board. Positive means net buying; negative means net selling.'
      WHEN 'calculated_at' THEN
        'Database statement timestamp when this canonical v2 row was materialized; not source event time or data availability time.'
      ELSE definition END,
    calculation=CASE feature_column
      WHEN 'net_value_1d' THEN
        'net_value_1d = buy_value_1d - sell_value_1d within the same date, ticker, broker, Investor Type and Market Board. Positive is net buy; negative is net sell.'
      WHEN 'net_lots_1d' THEN
        'net_lots_1d = buy_lots_1d - sell_lots_1d within the same date, ticker, broker, Investor Type and Market Board. Positive is net buy; negative is net sell.'
      WHEN 'calculated_at' THEN 'PostgreSQL statement_timestamp() at insert or ticker rebuild.'
      ELSE replace(calculation,
        ' All broker windows partition by Broker, Investor Type and Market Board on the ticker transaction-date calendar; missing broker activity contributes zero.',
        CASE WHEN feature_category IN ('Identity','Metadata','Broker Classification')
               OR feature_column IN ('buy_value_1d','sell_value_1d','buy_lots_1d','sell_lots_1d')
             THEN ''
             ELSE ' All broker windows partition by Broker, Investor Type and Market Board on the ticker transaction-date calendar; missing activity contributes zero.' END)
      END,
    analytical_interpretation=CASE feature_column
      WHEN 'net_value_1d' THEN
        'Signed daily IDR flow for this exact broker and investor identity: positive is net buying, negative is net selling, zero is balanced.'
      WHEN 'net_lots_1d' THEN
        'Signed daily lots for this exact broker and investor identity: positive is net buying, negative is net selling, zero is balanced.'
      WHEN 'calculated_at' THEN
        'Materialization timestamp, not transaction time; never use it to infer when a historical broker signal was knowable.'
      ELSE analytical_interpretation END,
    source_columns=CASE
      WHEN feature_column='calculated_at' THEN 'PostgreSQL.statement_timestamp()'
      WHEN source_tables LIKE '%IDX_Broker_Summary%'
           AND source_columns NOT LIKE '%IDX_Broker_Summary."Investor Type"%'
        THEN source_columns || ' | IDX_Broker_Summary."Investor Type"'
      ELSE source_columns END
WHERE feature_table='Feature_02_Broker_Rolling' AND version='v2' AND is_active;

UPDATE public."Column_Catalog" c
SET definition=f.definition, source_column_or_expression='Feature_Catalog active semantic version',
    documentation_status='VERIFIED'
FROM public."Feature_Catalog" f
WHERE c.table_schema='public' AND c.table_name='Feature_02_Broker_Rolling'
  AND f.feature_table=c.table_name AND f.feature_column=c.column_name
  AND f.version='v2' AND f.is_active;

COMMIT;
