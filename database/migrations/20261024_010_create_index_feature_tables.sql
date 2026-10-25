-- Dedicated INDEX analytical tables. No daily schedules, workers, source writes or bulk load.
-- Applied by scripts/initialize_index_feature_sample.py inside its atomic sample/cleanup transaction.
CREATE SCHEMA IF NOT EXISTS migration_archive;
CREATE TABLE IF NOT EXISTS migration_archive.index_feature_rows (
 snapshot_id uuid NOT NULL,source_table text NOT NULL,row_hash text NOT NULL,row_data jsonb NOT NULL,
 backed_up_at timestamptz NOT NULL DEFAULT statement_timestamp(),PRIMARY KEY(snapshot_id,source_table,row_hash)
);
CREATE OR REPLACE FUNCTION public.validate_index_feature_identity()
RETURNS trigger LANGUAGE plpgsql AS $fn$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public."IDX_Stock_Universe" u WHERE u."Ticker"=NEW.ticker AND u."Security Type"='index')
 OR EXISTS(SELECT 1 FROM public."Universe_Fixed_income" b WHERE b.ticker=NEW.ticker) THEN
  RAISE EXCEPTION 'INDEX feature target requires unambiguous universe index identity: %',NEW.ticker;
 END IF;
 RETURN NEW;
END $fn$;
DO $ddl$
DECLARE base text;target text;c record;
BEGIN
 FOREACH base IN ARRAY ARRAY['Feature_01_Stock_Daily','Feature_02_Broker_Rolling','Feature_03_Stock_Broker_Daily',
 'Feature_04_Technical_Indicator','Feature_05_Foreign_Domestic_Broker_Detail','Feature_06_Foreign_Domestic'] LOOP
  target=base||'_INDEX';
  EXECUTE format('CREATE TABLE IF NOT EXISTS public.%I (LIKE public.%I INCLUDING ALL)',target,base);
  IF base='Feature_04_Technical_Indicator' THEN
   FOR c IN SELECT conname FROM pg_constraint WHERE conrelid=format('public.%I',target)::regclass
   AND contype='c' AND pg_get_constraintdef(oid) LIKE '%asset_type%' LOOP
    EXECUTE format('ALTER TABLE public.%I DROP CONSTRAINT %I',target,c.conname);
   END LOOP;
   EXECUTE format('ALTER TABLE public.%I ADD CONSTRAINT index_asset_type_only CHECK(asset_type=''index'')',target);
  END IF;
  IF base IN ('Feature_05_Foreign_Domestic_Broker_Detail','Feature_06_Foreign_Domestic') THEN
   EXECUTE format('ALTER TABLE public.%I ADD COLUMN IF NOT EXISTS frequency_source_rows bigint NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS buy_freq_known_rows bigint NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS sell_freq_known_rows bigint NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS buy_freq_missing_rows bigint NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS sell_freq_missing_rows bigint NOT NULL DEFAULT 0',target);
   IF NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid=format('public.%I',target)::regclass AND conname='index_frequency_coverage_check') THEN
    EXECUTE format('ALTER TABLE public.%I ADD CONSTRAINT index_frequency_coverage_check CHECK(
     frequency_source_rows>=0 AND buy_freq_known_rows>=0 AND sell_freq_known_rows>=0 AND buy_freq_missing_rows>=0 AND sell_freq_missing_rows>=0
     AND buy_freq_known_rows+buy_freq_missing_rows=frequency_source_rows
     AND sell_freq_known_rows+sell_freq_missing_rows=frequency_source_rows)',target);
   END IF;
  END IF;
  EXECUTE format('DROP TRIGGER IF EXISTS index_feature_identity_guard ON public.%I',target);
  EXECUTE format('CREATE TRIGGER index_feature_identity_guard BEFORE INSERT OR UPDATE OF ticker ON public.%I FOR EACH ROW EXECUTE FUNCTION public.validate_index_feature_identity()',target);
  IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='pgweb') THEN EXECUTE format('GRANT SELECT ON public.%I TO pgweb',target); END IF;
  EXECUTE format('COMMENT ON TABLE public.%I IS %L',target,
   'Dedicated universe-index analytical output. Single-date audited sample; automatic updates and bulk are not enabled. Broker flows use all declared raw symbols, not official historical index constituents.');
 END LOOP;
END $ddl$;
-- Catalog clone preserves per-column formula/seed/lookback semantics, with explicit index overrides.
DO $catalog$
DECLARE base text;target text;fcols text[];ccols text[];
BEGIN
 FOREACH base IN ARRAY ARRAY['Feature_01_Stock_Daily','Feature_02_Broker_Rolling','Feature_03_Stock_Broker_Daily',
 'Feature_04_Technical_Indicator','Feature_05_Foreign_Domestic_Broker_Detail','Feature_06_Foreign_Domestic'] LOOP
  target=base||'_INDEX';
  INSERT INTO public."Table_Catalog"
  SELECT (jsonb_populate_record(NULL::public."Table_Catalog",to_jsonb(c)||jsonb_build_object(
   'table_name',target,'definition','Dedicated index output. '||c.definition||' Transaction aggregates include all declared source symbols, including warrants/rights; not an official historical constituent basket.',
   'source_code_paths',ARRAY['scripts/initialize_index_feature_sample.py','database/migrations/20261024_010_create_index_feature_tables.sql'],
   'update_rule','Explicit one-date validation only. Daily update logic and bulk await user approval.',
   'related_functions',ARRAY['validate_index_feature_identity()'],
   'documentation_status','PARTIAL','created_at',now(),'updated_at',now()))).*
  FROM public."Table_Catalog" c WHERE c.table_schema='public' AND c.table_name=base
  AND NOT EXISTS(SELECT 1 FROM public."Table_Catalog" z WHERE z.table_schema='public' AND z.table_name=target);
  INSERT INTO public."Column_Catalog"
  SELECT (jsonb_populate_record(NULL::public."Column_Catalog",to_jsonb(c)||jsonb_build_object(
   'table_name',target,'source_code_paths',ARRAY['scripts/initialize_index_feature_sample.py'],
   'created_at',now(),'updated_at',now()))).*
  FROM public."Column_Catalog" c WHERE c.table_schema='public' AND c.table_name=base
  AND NOT EXISTS(SELECT 1 FROM public."Column_Catalog" z WHERE z.table_schema='public' AND z.table_name=target AND z.column_name=c.column_name);
  INSERT INTO public."Feature_Catalog"
  SELECT (jsonb_populate_record(NULL::public."Feature_Catalog",to_jsonb(c)||jsonb_build_object(
   'feature_table',target,'version','v1','is_active',false,
   'definition','Index scope. '||c.definition,
   'refresh_trigger','Manual audited single-date initialization; daily updates not enabled.',
   'availability_rule','Only the explicitly validated INDEX output date. Historical context is read, not bulk-written.',
   'validation_evidence',ARRAY['verification/ihsg_feature_aggregation/index_tables/README.md','scripts/initialize_index_feature_sample.py'],
   'created_at',now(),'updated_at',now()))).*
  FROM public."Feature_Catalog" c WHERE c.feature_table=base AND c.is_active
  AND NOT EXISTS(SELECT 1 FROM public."Feature_Catalog" z WHERE z.feature_table=target AND z.feature_column=c.feature_column AND z.version='v1');
 END LOOP;
END $catalog$;
UPDATE public."Feature_Catalog" SET definition='Universe index code; eligibility from IDX_Stock_Universe Security Type=index.',calculation='Universe index ticker'
WHERE feature_table LIKE '%\_INDEX' ESCAPE '\' AND feature_column='ticker' AND version='v1';
UPDATE public."Feature_Catalog" SET calculation='index',definition='Index asset class, resolved from approved universe metadata.'
WHERE feature_table='Feature_04_Technical_Indicator_INDEX' AND feature_column='asset_type' AND version='v1';
UPDATE public."Feature_Catalog" SET calculation='NULL by user policy for index aggregate',null_rule='Always NULL by explicit user decision; not an error or retry target.'
WHERE feature_table='Feature_03_Stock_Broker_Daily_INDEX' AND feature_column='broker_concentration_hhi' AND version='v1';
UPDATE public."Feature_Catalog" SET calculation='SUM of available raw frequency across declared source symbols on identical date/broker/investor/board scope',
 null_rule='NULL only when all inputs are unknown; mixed known and unknown retains SUM of known values with separate coverage counts. Known zero remains zero.'
WHERE feature_table='Feature_05_Foreign_Domestic_Broker_Detail_INDEX' AND feature_column IN ('buy_freq','sell_freq') AND version='v1';
UPDATE public."Column_Catalog" c SET definition=f.definition,source_column_or_expression=f.calculation,null_rule=f.null_rule
FROM public."Feature_Catalog" f WHERE c.table_schema='public' AND c.table_name=f.feature_table AND c.column_name=f.feature_column
AND f.version='v1' AND f.feature_column IN ('ticker','asset_type','broker_concentration_hhi','buy_freq','sell_freq');
-- Price-derived index levels are in index points; cash broker flows remain IDR.
UPDATE public."Feature_Catalog" SET unit='index points' WHERE feature_table IN ('Feature_01_Stock_Daily_INDEX','Feature_04_Technical_Indicator_INDEX')
AND unit IN ('IDR','source price unit');
UPDATE public."Column_Catalog" c SET unit=f.unit FROM public."Feature_Catalog" f WHERE c.table_schema='public' AND c.table_name=f.feature_table
AND c.column_name=f.feature_column AND f.version='v1';
DO $coverage$
DECLARE target text;col text;meaning text;formula text;
BEGIN
 FOREACH target IN ARRAY ARRAY['Feature_05_Foreign_Domestic_Broker_Detail_INDEX','Feature_06_Foreign_Domestic_INDEX'] LOOP
  FOREACH col IN ARRAY ARRAY['frequency_source_rows','buy_freq_known_rows','sell_freq_known_rows','buy_freq_missing_rows','sell_freq_missing_rows'] LOOP
   meaning=CASE col WHEN 'frequency_source_rows' THEN 'Count of contributing raw broker source rows.'
    WHEN 'buy_freq_known_rows' THEN 'Contributing source rows with known buy frequency; not the number of buy trades.'
    WHEN 'sell_freq_known_rows' THEN 'Contributing source rows with known sell frequency; not the number of sell trades.'
    WHEN 'buy_freq_missing_rows' THEN 'Contributing source rows whose buy frequency is unknown.'
    ELSE 'Contributing source rows whose sell frequency is unknown.' END;
   formula=CASE col WHEN 'frequency_source_rows' THEN 'COUNT(*) of contributing raw source rows'
    WHEN 'buy_freq_known_rows' THEN 'COUNT(buy_freq) of contributing raw source rows'
    WHEN 'sell_freq_known_rows' THEN 'COUNT(sell_freq) of contributing raw source rows'
    WHEN 'buy_freq_missing_rows' THEN 'COUNT(*) - COUNT(buy_freq) of contributing raw source rows'
    ELSE 'COUNT(*) - COUNT(sell_freq) of contributing raw source rows' END;
   INSERT INTO public."Column_Catalog"(table_schema,table_name,column_name,ordinal_position,data_type,is_nullable,is_primary_key,
    definition,source_column_or_expression,unit,null_rule,source_code_paths,documentation_status)
   SELECT 'public',target,col,c.ordinal_position,c.data_type,false,false,meaning,formula,'source rows','Never NULL; zero is a known coverage count.',
    ARRAY['scripts/initialize_index_feature_sample.py'],'PARTIAL' FROM information_schema.columns c
   WHERE c.table_schema='public' AND c.table_name=target AND c.column_name=col
   AND NOT EXISTS(SELECT 1 FROM public."Column_Catalog" z WHERE z.table_schema='public' AND z.table_name=target AND z.column_name=col);
   INSERT INTO public."Feature_Catalog"
   SELECT (jsonb_populate_record(NULL::public."Feature_Catalog",to_jsonb(c)||jsonb_build_object(
    'feature_column',col,'feature_category','Data Quality','definition',meaning,'calculation',formula,'unit','source rows',
    'null_rule','Never NULL; zero is a known coverage count.','minimum_history','1 source row','lookback_window','1 session',
    'analytical_interpretation',meaning,'recommended_use','Check completeness before treating known-frequency SUM as a complete market total.',
    'misuse_warning','Coverage rows are not trade counts or index constituents; no zero-imputation for missing frequencies.',
    'allowed_aggregations',ARRAY['SUM','MIN','MAX','COUNT'],
    'created_at',now(),'updated_at',now()))).*
   FROM public."Feature_Catalog" c WHERE c.feature_table=target AND c.feature_column='buy_freq' AND c.version='v1'
   AND NOT EXISTS(SELECT 1 FROM public."Feature_Catalog" z WHERE z.feature_table=target AND z.feature_column=col AND z.version='v1');
   -- Feature06 has no column named buy_freq; use a daily-frequency template there.
   IF target='Feature_06_Foreign_Domestic_INDEX' THEN
    INSERT INTO public."Feature_Catalog"
    SELECT (jsonb_populate_record(NULL::public."Feature_Catalog",to_jsonb(c)||jsonb_build_object(
     'feature_column',col,'feature_category','Data Quality','definition',meaning,'calculation',formula,'unit','source rows',
     'null_rule','Never NULL; zero is a known coverage count.','minimum_history','1 source row','lookback_window','1 session',
     'analytical_interpretation',meaning,'recommended_use','Check daily source coverage; partial-frequency ratios remain unavailable.',
     'misuse_warning','Source-row coverage is not a number of trades.','allowed_aggregations',ARRAY['SUM','MIN','MAX','COUNT'],
     'created_at',now(),'updated_at',now()))).*
    FROM public."Feature_Catalog" c WHERE c.feature_table=target AND c.feature_column='foreign_buy_freq_1d' AND c.version='v1'
    AND NOT EXISTS(SELECT 1 FROM public."Feature_Catalog" z WHERE z.feature_table=target AND z.feature_column=col AND z.version='v1');
   END IF;
  END LOOP;
 END LOOP;
END $coverage$;
UPDATE public."Feature_Catalog" SET null_rule='Sum available source frequency; NULL if all relevant inputs are unknown; zero only for known no activity. Coverage columns describe completeness.'
WHERE feature_table='Feature_06_Foreign_Domestic_INDEX' AND feature_column IN ('foreign_buy_freq_1d','foreign_sell_freq_1d','domestic_buy_freq_1d','domestic_sell_freq_1d') AND version='v1';
UPDATE public."Feature_Catalog" SET null_rule=null_rule||' INDEX sample: unavailable when contributing frequency input/window is incomplete; never divide full-scope value by partial-scope frequency.'
WHERE feature_table='Feature_06_Foreign_Domestic_INDEX' AND version='v1'
AND (feature_column LIKE '%freq%' OR feature_column LIKE '%ticket%')
AND feature_column NOT IN ('foreign_buy_freq_1d','foreign_sell_freq_1d','domestic_buy_freq_1d','domestic_sell_freq_1d','frequency_source_rows','buy_freq_known_rows','sell_freq_known_rows','buy_freq_missing_rows','sell_freq_missing_rows');
INSERT INTO public."Feature_Relationship_Catalog"
SELECT (jsonb_populate_record(NULL::public."Feature_Relationship_Catalog",to_jsonb(c)||jsonb_build_object(
 'left_feature_table',c.left_feature_table||'_INDEX','right_feature_table',c.right_feature_table||'_INDEX','version','v1',
 'definition','Index-only version: '||replace(c.definition,'asset_type=equity','asset_type=index'),
 'created_at',now(),'updated_at',now()))).*
FROM public."Feature_Relationship_Catalog" c WHERE c.is_active
AND c.left_feature_table IN ('Feature_01_Stock_Daily','Feature_02_Broker_Rolling','Feature_03_Stock_Broker_Daily','Feature_04_Technical_Indicator','Feature_05_Foreign_Domestic_Broker_Detail','Feature_06_Foreign_Domestic')
AND c.right_feature_table IN ('Feature_01_Stock_Daily','Feature_02_Broker_Rolling','Feature_03_Stock_Broker_Daily','Feature_04_Technical_Indicator','Feature_05_Foreign_Domestic_Broker_Detail','Feature_06_Foreign_Domestic')
AND NOT EXISTS(SELECT 1 FROM public."Feature_Relationship_Catalog" z WHERE z.left_feature_table=c.left_feature_table||'_INDEX' AND z.right_feature_table=c.right_feature_table||'_INDEX' AND z.version='v1')
ON CONFLICT DO NOTHING;
