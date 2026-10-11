#!/usr/bin/env python3
"""Forward-only Feature04 extension and per-ticker backfill audit metadata."""
import sys
import hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'features/feature04'))
from engine import TABLE,COLUMNS,EXTENSIONS
from specs import specifications
from sql_text import sql_literal

MIGRATION=ROOT/'database/migrations/20261011_002_extend_feature04_and_backfill_log.sql'
FIELDS=['feature_table','feature_column','grain','feature_category','definition','calculation',
 'source_tables','source_columns','lookback_window','minimum_history','unit','null_rule',
 'refresh_trigger','dependency_rule','version','is_active','semantic_role','allowed_aggregations',
 'ranking_interpretation','is_filterable','is_groupable','availability_rule','point_in_time_safe',
 'historical_metadata_warning','analytical_interpretation','recommended_use','misuse_warning',
 'semantic_review_status','validation_evidence']
EVIDENCE=['features/feature04/tests/test_engine.py','verification/feature04/FULL_BACKFILL.md','FEATURE04_TECHNICAL_INDICATOR.md']
SOURCES=['features/feature04/engine.py','features/feature04/pipeline.py','features/feature04/backfill.py',*EVIDENCE[1:]]
def lit(s):return "'"+sql_literal(str(s))+"'"
def arr(a):return 'ARRAY['+','.join(lit(s) for s in a)+']::text[]'

def render():
 specs=specifications()
 lines=['BEGIN;',"SET LOCAL lock_timeout='5s';","SET LOCAL statement_timeout='60s';",'''DO $guard$
BEGIN
 IF (SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='Feature04_Technical_Indicator') <> 42 THEN
  RAISE EXCEPTION 'Expected the inspected 42-column v1 table; stop for inspection';
 END IF;
 IF EXISTS(SELECT 1 FROM public."Feature_Catalog" WHERE feature_table='Feature04_Technical_Indicator' AND version='v2') THEN
  RAISE EXCEPTION 'Feature04 v2 is already registered';
 END IF;
 IF (SELECT count(*) FROM public."Feature_Catalog" WHERE feature_table='Feature04_Technical_Indicator' AND version='v1' AND is_active) <> 42 THEN
  RAISE EXCEPTION 'Expected all 42 active v1 definitions';
 END IF;
 IF to_regclass('public.feature04_backfill_log') IS NOT NULL THEN
  RAISE EXCEPTION 'Backfill log exists; stop for inspection';
 END IF;
END $guard$;''',f'''ALTER TABLE public."{TABLE}"
 ADD COLUMN adx_14 double precision,
 ADD COLUMN ema_50 double precision,
 ADD COLUMN ema_200 double precision,
 ADD COLUMN inside_bar integer,
 ADD CONSTRAINT feature04_adx_14_valid CHECK(adx_14 IS NULL OR (adx_14 BETWEEN 0 AND 100)),
 ADD CONSTRAINT feature04_ema_50_finite CHECK(ema_50 IS NULL OR (ema_50>'-Infinity'::double precision AND ema_50<'Infinity'::double precision)),
 ADD CONSTRAINT feature04_ema_200_finite CHECK(ema_200 IS NULL OR (ema_200>'-Infinity'::double precision AND ema_200<'Infinity'::double precision)),
 ADD CONSTRAINT feature04_inside_bar_binary CHECK(inside_bar IS NULL OR inside_bar IN (0,1));''',
 '''CREATE TABLE public.feature04_backfill_log (
 run_id uuid NOT NULL,
 ticker text NOT NULL CHECK(ticker=upper(btrim(ticker)) AND ticker<>''),
 source_start date,
 source_end date,
 source_rows integer CHECK(source_rows>=0),
 source_sha256 text CHECK(source_sha256 ~ '^[0-9a-f]{64}$'),
 output_sha256 text CHECK(output_sha256 ~ '^[0-9a-f]{64}$'),
 calculation_version text NOT NULL,
 status text NOT NULL CHECK(status IN ('COMPLETED','FAILED')),
 changed_rows integer CHECK(changed_rows>=0),
 started_at timestamptz NOT NULL,
 finished_at timestamptz NOT NULL,
 detail text,
 PRIMARY KEY(run_id,ticker),
 CHECK(source_start IS NULL OR source_end>=source_start),
 CHECK(finished_at>=started_at),
 CHECK(status<>'COMPLETED' OR (source_start IS NOT NULL AND source_end IS NOT NULL
  AND source_rows>0 AND source_sha256 IS NOT NULL AND output_sha256 IS NOT NULL AND changed_rows IS NOT NULL))
);''',
 "COMMENT ON TABLE public.feature04_backfill_log IS 'Atomic per-run/ticker Feature04 historical load metadata and resume fingerprints; no copied price or feature rows. Source hash is an extraction fingerprint, not point-in-time availability.';",
 f'COMMENT ON TABLE public."{TABLE}" IS '+lit('Daily IDX wide technical features; 46 columns; v2 adds ADX14, close EMA50/200 and strict current-candle inside bar. Full-history causal initialization. TradingView parity and point-in-time training eligibility NOT VERIFIED. Manual per-ticker backfill, no automatic scheduler.')+';',
 f'''UPDATE public."Table_Catalog" SET definition={lit('Causal daily technical indicators, independent native TA-Lib codes, and strict current-candle inside bar; 46 columns, v2 calculation-verified. TradingView parity NOT VERIFIED.')},
 source_code_paths={arr(SOURCES)},update_rule={lit('Manual bounded refresh or explicitly authorized serial full-history per-ticker backfill; source corrections require chronological replay through output end. No scheduler.')},updated_at=clock_timestamp()
 WHERE table_schema='public' AND table_name={lit(TABLE)};''']
 for col in EXTENSIONS:
  cat,definition,formula,history,unit,use,warning=specs[col]
  nullrule='NULL on the first usable candle or after invalid/missing OHLCV; 0 means available non-detection; strict equal-boundary cases are 0.' if col=='inside_bar' else 'NULL before independent initialization or after invalid/missing OHLCV; no zero imputation.'
  lines += [f'COMMENT ON COLUMN public."{TABLE}".{col} IS '+lit(definition+' '+formula)+';',
   f'''INSERT INTO public."Column_Catalog"(table_schema,table_name,column_name,ordinal_position,data_type,is_nullable,default_expression,is_primary_key,definition,source_column_or_expression,unit,null_rule,source_code_paths,documentation_status)
   SELECT 'public',{lit(TABLE)},{lit(col)},a.attnum,format_type(a.atttypid,a.atttypmod),true,NULL,false,{lit(definition)},{lit(formula)},{lit(unit)},{lit(nullrule)},{arr(SOURCES)},'VERIFIED'
   FROM pg_attribute a WHERE a.attrelid='public."{TABLE}"'::regclass AND a.attname={lit(col)};''']
 # Copy the 42 unchanged formula definitions to v2 while preserving v1 history.
 copies=[]
 for f in FIELDS:
  copies.append("'v2'" if f=='version' else 'true' if f=='is_active' else arr(EVIDENCE) if f=='validation_evidence' else lit('Manual explicit refresh or authorized per-ticker backfill; no scheduler') if f=='refresh_trigger' else f)
 # A partial unique index permits only one active definition per physical column.
 # Disable v1 inside the same transaction before inserting active v2 definitions.
 lines.append(f'UPDATE public."Feature_Catalog" SET is_active=false WHERE feature_table={lit(TABLE)} AND version=\'v1\';')
 lines.append('INSERT INTO public."Feature_Catalog"('+','.join(FIELDS)+') SELECT '+','.join(copies)+f' FROM public."Feature_Catalog" WHERE feature_table={lit(TABLE)} AND version=\'v1\';')
 for col in EXTENSIONS:
  cat,definition,formula,history,unit,use,warning=specs[col]
  nullrule='NULL without a usable predecessor; available strict non-detection is INTEGER 0.' if col=='inside_bar' else 'NULL before independent initialization or after invalid/missing OHLCV; no zero imputation.'
  vals=[lit(TABLE),lit(col),lit('ticker x trade_date x timeframe'),lit(cat),lit(definition),lit(formula),lit('Price_Stock_Indonesia_IDX'),lit('ticker,date,timeframe,high,low,close; OHLCV input quality validation'),lit(history),lit(history),lit(unit),lit(nullrule),lit('Manual explicit refresh or authorized per-ticker backfill; no scheduler'),lit('Full available chronological history per ticker; no future bars, state resets on invalid OHLCV'),"'v2'",'true',"'MEASURE'",arr(['COUNT','AVG'] if col=='inside_bar' else ['MIN','MAX','AVG','MEDIAN']),"'CONTEXTUAL'",'true','false',lit('Current closed Daily bar and earlier observations only; prediction timestamp/horizon undefined. Training point-in-time eligibility NOT VERIFIED.'),'false',lit('Source revision/adjustment vintages and historical availability incomplete; TradingView numerical parity NOT VERIFIED.'),lit(definition+' '+warning),lit(use),lit(warning),"'CALCULATION_VERIFIED'",arr(EVIDENCE)]
  lines.append('INSERT INTO public."Feature_Catalog"('+','.join(FIELDS)+') VALUES('+','.join(vals)+');')
 logdefs={
  'run_id':('Caller-supplied UUID identifying an authorized resumable load run.','CLI --run-id','identifier'),
  'ticker':('Actual source ticker processed in this atomic transaction.','Price_Stock_Indonesia_IDX.ticker','symbol'),
  'source_start':('Earliest observation in this ticker source snapshot.','min(source.date)','date'),
  'source_end':('Latest observation in this ticker source snapshot.','max(source.date)','date'),
  'source_rows':('Number of source observations processed for this ticker.','len(source history)','observations'),
  'source_sha256':('SHA256 of canonical source serialization, including known source metadata.','SHA256 sorted-key canonical JSON; extraction fingerprint','hash'),
  'output_sha256':('SHA256 of all stored feature payloads, excluding calculated_at.','SHA256 canonical output; calculated_at excluded for idempotency','hash'),
  'calculation_version':('Version of the engine that produced the stored payload.','engine.VERSION','version'),
  'status':('COMPLETED means verified target and log committed atomically; FAILED means no partial ticker write was committed.','transaction result','state'),
  'changed_rows':('Inserted or materially changed rows in this ticker UPSERT.','PostgreSQL INSERT/UPDATE rowcount; identical rerun zero','rows'),
  'started_at':('UTC time this ticker attempt began.','timezone-aware execution clock','timestamp'),
  'finished_at':('UTC time verification finished, before atomic commit.','timezone-aware execution clock','timestamp'),
  'detail':('Bounded execution or failure explanation without credentials.','executor metadata','text')}
 lines.append(f'''INSERT INTO public."Table_Catalog"(table_schema,table_name,category,definition,grain,primary_key_columns,source_system,source_tables,source_code_paths,update_rule,related_functions,documentation_status)
 VALUES('public','feature04_backfill_log','Monitoring','Atomic Feature04 per-run/ticker historical calculation audit and resumable extraction/output fingerprints.','One authorized run UUID x source ticker',ARRAY['run_id','ticker'],'Feature04 Python backfill',ARRAY['Price_Stock_Indonesia_IDX','Feature04_Technical_Indicator'],{arr(SOURCES)},'Manual serial runner; completed output and audit committed together; failed ticker rolls back.',ARRAY[]::text[],'VERIFIED');''')
 for col,(definition,formula,unit) in logdefs.items():
  lines.append('COMMENT ON COLUMN public.feature04_backfill_log.'+col+' IS '+lit(definition)+';')
  lines.append(f'''INSERT INTO public."Column_Catalog"(table_schema,table_name,column_name,ordinal_position,data_type,is_nullable,default_expression,is_primary_key,definition,source_column_or_expression,unit,null_rule,source_code_paths,documentation_status)
 SELECT 'public','feature04_backfill_log',{lit(col)},a.attnum,format_type(a.atttypid,a.atttypmod),NOT a.attnotnull,NULL,{str(col in ('run_id','ticker')).lower()},{lit(definition)},{lit(formula)},{lit(unit)},'Source/output fields can be NULL only on failed attempts; never fabricate source availability.',{arr(SOURCES)},'VERIFIED'
 FROM pg_attribute a WHERE a.attrelid='public.feature04_backfill_log'::regclass AND a.attname={lit(col)};''')
 lines += [f'''DO $verify$ BEGIN
 IF (SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name={lit(TABLE)})<>46 OR
 (SELECT count(*) FROM public."Feature_Catalog" WHERE feature_table={lit(TABLE)} AND is_active AND version='v2')<>46 THEN
 RAISE EXCEPTION 'Feature04 v2 schema/catalog mismatch'; END IF;
END $verify$;''','COMMIT;']
 return '\n'.join(lines)+'\n'

if __name__=='__main__':
 text=render()
 applied={name:digest for digest,name in (line.split('  ',1) for line in
  (ROOT/'database/migrations/APPLIED.sha256').read_text().splitlines() if line and not line.startswith('#'))}
 if MIGRATION.name in applied and hashlib.sha256(text.encode()).hexdigest()!=applied[MIGRATION.name]:
  raise RuntimeError('Applied migration is immutable; use a new forward migration')
 if MIGRATION.exists() and MIGRATION.name in applied and MIGRATION.read_text()!=text:
  raise RuntimeError('Applied file differs from its generator/manifest; stop for inspection')
 if not MIGRATION.exists() or MIGRATION.read_text()!=text:
  MIGRATION.write_text(text)
 print(MIGRATION.name)
