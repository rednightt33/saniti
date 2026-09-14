-- Promote the validated Investor-Type shadow and remove the redundant v1 heap.
-- Feature 03 keeps its existing broker-level semantics by collapsing investor
-- types before its existing broker-level aggregation.
BEGIN;
SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '10min';

DO $preflight$
DECLARE
    v_old bigint;
    v_new bigint;
    v_bad integer;
BEGIN
    IF to_regclass('public."Feature_02_Broker_Rolling"') IS NULL
       OR to_regclass('public."Feature_02_Broker_Rolling_v2"') IS NULL THEN
        RAISE EXCEPTION 'Expected canonical v1 and validated v2 shadow';
    END IF;
    SELECT reltuples::bigint INTO v_old FROM pg_class
      WHERE oid='public."Feature_02_Broker_Rolling"'::regclass;
    SELECT reltuples::bigint INTO v_new FROM pg_class
      WHERE oid='public."Feature_02_Broker_Rolling_v2"'::regclass;
    IF v_old < 40000000 OR v_new < 40000000 THEN
        RAISE EXCEPTION 'Unexpected Feature 02 row estimates: v1 %, v2 %', v_old, v_new;
    END IF;
    IF (SELECT count(*) FROM public."Feature_Catalog"
        WHERE feature_table='Feature_02_Broker_Rolling' AND version='v1' AND is_active) <> 38
       OR (SELECT count(*) FROM public."Column_Catalog"
        WHERE table_schema='public' AND table_name='Feature_02_Broker_Rolling_v2') <> 38 THEN
        RAISE EXCEPTION 'Feature 02 catalogs are not in the validated pre-cutover state';
    END IF;
    -- A bounded independent check of the compatibility contract for Feature 03.
    WITH keys AS (
        SELECT ticker, market_board, broker, date
        FROM public."Feature_02_Broker_Rolling"
        WHERE ticker='BBCA' ORDER BY date DESC LIMIT 50
    ), compared AS (
        SELECT old.buy_value_1d, old.sell_value_1d, old.net_value_1d,
               old.buy_lots_1d, old.sell_lots_1d, old.net_lots_1d,
               sum(new.buy_value_1d) AS buy_value_new,
               sum(new.sell_value_1d) AS sell_value_new,
               sum(new.net_value_1d) AS net_value_new,
               sum(new.buy_lots_1d) AS buy_lots_new,
               sum(new.sell_lots_1d) AS sell_lots_new,
               sum(new.net_lots_1d) AS net_lots_new
        FROM keys k
        JOIN public."Feature_02_Broker_Rolling" old
          ON (old.ticker,old.market_board,old.broker,old.date)
           = (k.ticker,k.market_board,k.broker,k.date)
        LEFT JOIN public."Feature_02_Broker_Rolling_v2" new
          ON (new.ticker,new.market_board,new.broker,new.date)
           = (k.ticker,k.market_board,k.broker,k.date)
        GROUP BY old.buy_value_1d,old.sell_value_1d,old.net_value_1d,
                 old.buy_lots_1d,old.sell_lots_1d,old.net_lots_1d,
                 old.ticker,old.market_board,old.broker,old.date
    )
    SELECT count(*) INTO v_bad FROM compared
    WHERE (buy_value_1d,sell_value_1d,net_value_1d,buy_lots_1d,sell_lots_1d,net_lots_1d)
       IS DISTINCT FROM
          (buy_value_new,sell_value_new,net_value_new,buy_lots_new,sell_lots_new,net_lots_new);
    IF v_bad <> 0 THEN
        RAISE EXCEPTION 'v2 cannot reproduce v1 broker daily totals for BBCA: % mismatches', v_bad;
    END IF;
END
$preflight$;

UPDATE public."Feature_Catalog" SET is_active=false
WHERE feature_table='Feature_02_Broker_Rolling' AND version='v1' AND is_active;

-- No CASCADE: unexpected external dependencies must abort this transaction.
DROP TABLE public."Feature_02_Broker_Rolling" RESTRICT;
ALTER TABLE public."Feature_02_Broker_Rolling_v2" RENAME TO "Feature_02_Broker_Rolling";
ALTER TABLE public."Feature_02_Broker_Rolling"
    RENAME CONSTRAINT "Feature_02_Broker_Rolling_v2_pkey" TO "Feature_02_Broker_Rolling_pkey";
COMMENT ON TABLE public."Feature_02_Broker_Rolling" IS
    'Canonical Feature 02 v2: one source ticker, broker, investor type, board and transaction date per row. Investor type is source investor identity, not broker domicile.';
GRANT SELECT ON public."Feature_02_Broker_Rolling" TO market_ai_reader;

-- Replace only the FROM source of the existing Feature 03 routine. Collapsing
-- investor types by broker first preserves its v1 count/rank/HHI semantics.
DO $feature03$
DECLARE
    v_definition text;
    v_old text := 'FROM public."Feature_02_Broker_Rolling" AS f';
    v_new text := 'FROM (SELECT date, ticker, market_board, broker, '
        || 'sum(buy_value_1d) AS buy_value_1d, '
        || 'sum(sell_value_1d) AS sell_value_1d, '
        || 'sum(net_value_1d) AS net_value_1d, '
        || 'sum(buy_lots_1d) AS buy_lots_1d, '
        || 'sum(sell_lots_1d) AS sell_lots_1d '
        || 'FROM public."Feature_02_Broker_Rolling" '
        || 'WHERE ($1 IS NULL OR date = $1) '
        || 'AND ($2 IS NULL OR ticker = ANY($2)) '
        || 'GROUP BY date, ticker, market_board, broker) AS f';
BEGIN
    SELECT pg_get_functiondef('public.refresh_feature_03_stock_broker_daily(date,text[])'::regprocedure)
      INTO v_definition;
    IF length(v_definition) - length(replace(v_definition,v_old,'')) <> length(v_old) THEN
        RAISE EXCEPTION 'Feature 03 routine source does not match reviewed v1 definition';
    END IF;
    EXECUTE replace(v_definition,v_old,v_new);
END
$feature03$;
COMMENT ON FUNCTION public.refresh_feature_03_stock_broker_daily(date,text[]) IS
    'Refreshes existing broker-level Feature 03 semantics; first sums Feature 02 investor types per broker/date/board. Broker domicile columns still derive from IDX_Broker_Profile.';

-- Move the catalog identity from staging to the canonical table. Its v2
-- physical comments are the reviewed per-column definitions.
DELETE FROM public."Column_Catalog"
WHERE table_schema='public' AND table_name='Feature_02_Broker_Rolling'
  AND column_name='broker_type';
UPDATE public."Column_Catalog" dst
SET ordinal_position=src.ordinal_position, data_type=src.data_type,
    is_nullable=src.is_nullable, default_expression=src.default_expression,
    is_primary_key=src.is_primary_key, definition=src.definition,
    source_column_or_expression='Feature_Catalog active semantic version',
    source_code_paths=ARRAY['database/migrations/20260914_043_cutover_feature_02_investor_type.sql',
                            'scripts/backfill_feature_02_v2.py'],
    documentation_status='VERIFIED'
FROM public."Column_Catalog" src
WHERE dst.table_schema='public' AND dst.table_name='Feature_02_Broker_Rolling'
  AND src.table_schema='public' AND src.table_name='Feature_02_Broker_Rolling_v2'
  AND dst.column_name=src.column_name;
INSERT INTO public."Column_Catalog" (
    table_schema,table_name,column_name,ordinal_position,data_type,is_nullable,
    default_expression,is_primary_key,definition,source_column_or_expression,
    source_code_paths,documentation_status
)
SELECT 'public','Feature_02_Broker_Rolling',column_name,ordinal_position,data_type,
       is_nullable,default_expression,is_primary_key,definition,
       'Feature_Catalog active semantic version',
       ARRAY['database/migrations/20260914_043_cutover_feature_02_investor_type.sql',
             'scripts/backfill_feature_02_v2.py'],'VERIFIED'
FROM public."Column_Catalog"
WHERE table_schema='public' AND table_name='Feature_02_Broker_Rolling_v2'
  AND column_name='investor_type';
DELETE FROM public."Column_Catalog"
WHERE table_schema='public' AND table_name='Feature_02_Broker_Rolling_v2';
DELETE FROM public."Table_Catalog"
WHERE table_schema='public' AND table_name='Feature_02_Broker_Rolling_v2';
UPDATE public."Table_Catalog"
SET category='Feature',documentation_status='VERIFIED',
    definition='Validated daily and rolling broker flows by source ticker, broker, Investor Type, Market Board and transaction date. Investor Type is exact source investor identity; broker_classification remains current profile metadata.',
    grain='One row per source ticker, broker, Investor Type, Market Board and transaction date',
    primary_key_columns=ARRAY['ticker','market_board','broker','investor_type','date'],
    source_tables=ARRAY['IDX_Broker_Summary','IDX_Broker_Profile'],
    source_code_paths=ARRAY['database/migrations/20260914_034_create_feature_02_investor_type_shadow.sql',
                            'database/migrations/20260914_043_cutover_feature_02_investor_type.sql',
                            'scripts/backfill_feature_02_v2.py','scripts/validate_feature_02_v2_sample.py'],
    update_rule='Validated full v2 backfill. No automatic Feature 02 worker is deployed; rebuild affected tickers after Broker Summary changes.',
    readiness_mode='DATA_DATE',
    availability_rule='Only through the last validated IDX_Broker_Summary date; do not equate broker domicile with source investor type.',
    point_in_time_status='PARTIAL',
    historical_metadata_method='broker_classification is current-state metadata; investor_type is source point-in-time data.'
WHERE table_schema='public' AND table_name='Feature_02_Broker_Rolling';

INSERT INTO public."Feature_Catalog" (
    feature_table,feature_column,grain,feature_category,definition,calculation,
    source_tables,source_columns,lookback_window,minimum_history,unit,null_rule,
    refresh_trigger,dependency_rule,version,is_active,semantic_role,
    allowed_aggregations,ranking_interpretation,is_filterable,is_groupable,
    availability_rule,point_in_time_safe,historical_metadata_warning,
    analytical_interpretation,recommended_use,misuse_warning,
    semantic_review_status,validation_evidence
)
SELECT 'Feature_02_Broker_Rolling',
       CASE WHEN old.feature_column='broker_type' THEN 'investor_type' ELSE old.feature_column END,
       'Date × source ticker × broker × Investor Type × Market Board',
       CASE WHEN old.feature_column='broker_type' THEN 'Identity' ELSE old.feature_category END,
       col_description('public."Feature_02_Broker_Rolling"'::regclass,att.attnum),
       CASE
         WHEN old.feature_column='broker_type' THEN
           'Copy IDX_Broker_Summary."Investor Type" exactly (Domestic or Foreign); never infer it from IDX_Broker_Profile.broker_type.'
         WHEN old.feature_column='broker' THEN
           'Copy source "Broker"; retain separate rows for each source Investor Type and Market Board.'
         WHEN old.feature_column IN ('buy_value_1d','sell_value_1d','buy_lots_1d','sell_lots_1d') THEN
           replace(old.calculation,'across investor types','within one Investor Type')
           || ' Group by source Date, Symbol, Broker, Investor Type and Market Board.'
         ELSE old.calculation || ' All broker windows partition by Broker, Investor Type and Market Board on the ticker transaction-date calendar; missing broker activity contributes zero.'
       END,
       CASE WHEN old.feature_column='broker_type' THEN 'IDX_Broker_Summary'
            ELSE old.source_tables END,
       CASE WHEN old.feature_column='broker_type' THEN 'IDX_Broker_Summary."Investor Type"'
            ELSE old.source_columns END,
       old.lookback_window,old.minimum_history,
       CASE WHEN old.feature_column='broker_type' THEN 'Domestic/Foreign investor label' ELSE old.unit END,
       CASE WHEN old.feature_column='broker_type' THEN 'Never NULL for a stored row.' ELSE old.null_rule END,
       'Broker Summary load or correction; current Broker Profile change affects broker_classification only.',
       'Requires source ticker transaction-date calendar across any board. Stored rows require activity by broker, Investor Type and board. No automatic Feature 02 worker is deployed.',
       'v2',true,
       old.semantic_role,old.allowed_aggregations,old.ranking_interpretation,
       old.is_filterable,old.is_groupable,
       'Use only through the last validated Broker Summary date. Filter investor_type and market_board explicitly when comparing investor flows.',
       CASE WHEN old.feature_column='broker_type' THEN true ELSE old.point_in_time_safe END,
       CASE WHEN old.feature_column='broker_type' THEN
           'Source investor identity on the transaction date; unlike current broker profile domicile.'
            ELSE old.historical_metadata_warning END,
       CASE WHEN old.feature_column='broker_type' THEN
           'Domestic or Foreign describes the investor represented by the broker-summary row, not where the broker is domiciled.'
            ELSE col_description('public."Feature_02_Broker_Rolling"'::regclass,att.attnum) END,
       CASE WHEN old.feature_column='broker_type' THEN
           'Filter or group investor flows by Domestic versus Foreign within the same ticker, date and board.'
            ELSE old.recommended_use END,
       CASE WHEN old.feature_column='broker_type' THEN
           'Do not equate investor_type with IDX_Broker_Profile.broker_type; a foreign broker can serve domestic investors.'
            ELSE 'Rows are investor-type-specific. Aggregate both types by broker before counting or ranking brokers. ' || old.misuse_warning END,
       'CALCULATION_VERIFIED',
       ARRAY['FEATURE_02_BROKER_ROLLING_V2.md',
             'scripts/validate_feature_02_v2_sample.py',
             'DATABASE_CHANGELOG.md',
             'database/migrations/20260914_043_cutover_feature_02_investor_type.sql']
FROM public."Feature_Catalog" old
JOIN pg_attribute att
  ON att.attrelid='public."Feature_02_Broker_Rolling"'::regclass
 AND att.attname=CASE WHEN old.feature_column='broker_type' THEN 'investor_type' ELSE old.feature_column END
WHERE old.feature_table='Feature_02_Broker_Rolling' AND old.version='v1'
  AND att.attnum>0 AND NOT att.attisdropped;

UPDATE public."Feature_Relationship_Catalog" SET is_active=false
WHERE is_active AND (left_feature_table='Feature_02_Broker_Rolling'
                  OR right_feature_table='Feature_02_Broker_Rolling');
INSERT INTO public."Feature_Relationship_Catalog" (
    left_feature_table,right_feature_table,left_join_columns,right_join_columns,
    relationship_type,safe_output_grain,requires_preaggregation,definition,
    version,is_active
)
SELECT left_feature_table,right_feature_table,left_join_columns,right_join_columns,
       relationship_type,
       CASE WHEN right_feature_table='Feature_02_Broker_Rolling' THEN
            'ticker × date after explicit Feature 02 aggregation, or ticker × date × board × broker × investor_type without aggregation'
            ELSE 'ticker × date × board after explicit Feature 02 broker and investor-type aggregation' END,
       true,
       definition || ' Feature 02 v2 adds source Investor Type. Sum investor types by broker before broker counts/ranks and aggregate to the output grain before joining.',
       'v2',true
FROM public."Feature_Relationship_Catalog"
WHERE version='v1' AND (left_feature_table='Feature_02_Broker_Rolling'
                    OR right_feature_table='Feature_02_Broker_Rolling');

DELETE FROM public."Database_Table_Status"
WHERE "Table Name"='Feature_02_Broker_Rolling_v2';

DO $validate$
BEGIN
    IF to_regclass('public."Feature_02_Broker_Rolling_v2"') IS NOT NULL
       OR to_regclass('public."Feature_02_Broker_Rolling"') IS NULL
       OR (SELECT count(*) FROM public."Feature_Catalog"
           WHERE feature_table='Feature_02_Broker_Rolling' AND version='v2' AND is_active) <> 38
       OR (SELECT count(*) FROM public."Column_Catalog"
           WHERE table_schema='public' AND table_name='Feature_02_Broker_Rolling') <> 38 THEN
        RAISE EXCEPTION 'Feature 02 cutover coverage check failed';
    END IF;
END
$validate$;
COMMIT;
