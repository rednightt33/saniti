#!/usr/bin/env python3
"""Generate the scoped Feature04 DDL and catalog registration from reviewed definitions."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'features/feature04'))
from engine import V1_COLUMNS as COLUMNS, IDENTITY, INDICATORS as ALL_INDICATORS, PATTERNS, TABLE
from specs import specifications
from sql_text import sql_literal
def lit(value):return "'"+sql_literal(value)+"'"
INDICATORS = tuple(c for c in ALL_INDICATORS if c in COLUMNS)

MIGRATION=ROOT/'database/migrations/20261011_001_create_feature04_technical_indicator.sql'
SOURCES=['features/feature04/engine.py','features/feature04/pipeline.py','FEATURE04_TECHNICAL_INDICATOR.md','verification/feature04/calculation_validation.json']
def arr(values):return 'ARRAY['+','.join(lit(v) for v in values)+']::text[]'

def render():
    specs={k:v for k,v in specifications().items() if k in COLUMNS}
    # Naming exception required by the user's exact target name. Preserve all
    # existing physical-column and VERIFIED-table guards in the catalog trigger.
    validator_before=(ROOT/'verification/feature04/catalog_validator_before.sql').read_text()
    old="IF NEW.feature_table !~ '^Feature_[0-9]{2}_[A-Za-z0-9_]+$' THEN"
    new="IF NEW.feature_table !~ '^Feature_[0-9]{2}_[A-Za-z0-9_]+$' AND NEW.feature_table <> 'Feature04_Technical_Indicator' THEN"
    assert validator_before.count(old)==1
    validator_after=validator_before.replace(old,new)
    lines=['BEGIN;',"SET LOCAL lock_timeout='5s';", "SET LOCAL statement_timeout='60s';",'''DO $guard$
BEGIN
 IF to_regclass('public."Feature04_Technical_Indicator"') IS NOT NULL THEN
  RAISE EXCEPTION 'Feature04_Technical_Indicator exists; stop for inspection, no conflicting changes';
 END IF;
 IF to_regclass('public."Price_Stock_Indonesia_IDX"') IS NULL THEN
  RAISE EXCEPTION 'Verified source table is absent';
 END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='public."Price_Stock_Indonesia_IDX"'::regclass AND contype='p' AND pg_get_constraintdef(oid)='PRIMARY KEY (ticker, date)') THEN
  RAISE EXCEPTION 'Verified source grain changed';
 END IF;
 IF EXISTS(SELECT 1 FROM public."Price_Stock_Indonesia_IDX" WHERE timeframe<>'Daily' OR source<>'TradingView' OR tradingview_symbol<>'IDX:'||ticker) THEN
  RAISE EXCEPTION 'Source dimensions/mapping differ from inspection';
 END IF;
 IF EXISTS(SELECT 1 FROM (VALUES ('ticker','varchar'),('date','date'),('timeframe','varchar'),('open','numeric'),('high','numeric'),('low','numeric'),('close','numeric'),('volume','numeric')) AS expected(name,udt)
  LEFT JOIN information_schema.columns c ON c.table_schema='public' AND c.table_name='Price_Stock_Indonesia_IDX' AND c.column_name=expected.name
  WHERE c.column_name IS NULL OR c.udt_name<>expected.udt OR c.is_nullable<>'NO') THEN
  RAISE EXCEPTION 'Verified source column contract changed';
 END IF;
END $guard$;''',f'CREATE TABLE public."{TABLE}" (']
    for col in COLUMNS:
        dtype='text' if col in ('ticker','timeframe','calculation_version') else 'date' if col=='trade_date' else 'timestamptz' if col=='calculated_at' else 'integer' if col in PATTERNS else 'double precision'
        required=' NOT NULL' if col in IDENTITY or col in ('calculation_version','calculated_at') else ''
        lines.append(f' "{col}" {dtype}{required},')
    lines += [f' CONSTRAINT "{TABLE}_pkey" PRIMARY KEY(ticker,trade_date,timeframe),',
              " CHECK(ticker=upper(btrim(ticker)) AND ticker<>''),"," CHECK(timeframe='Daily'),"," CHECK(btrim(calculation_version)<>''),"]
    for col in INDICATORS:
        lines.append(f''' CHECK("{col}" IS NULL OR ("{col}">'-Infinity'::double precision AND "{col}"<'Infinity'::double precision)),''')
    lines += [" CHECK(rsi_14 IS NULL OR rsi_14 BETWEEN 0 AND 100),"," CHECK(atr_14 IS NULL OR atr_14>=0)",');',
        f'COMMENT ON TABLE public."{TABLE}" IS '+lit('Daily IDX wide technical features; 42 columns; full-history causal TA-Lib initialization. TradingView numerical parity and point-in-time training eligibility NOT VERIFIED. No automatic writer deployed.')+';']
    for col in COLUMNS:lines.append(f'COMMENT ON COLUMN public."{TABLE}"."{col}" IS '+lit(specs[col][1]+' '+specs[col][2])+';')
    lines.append(f'''INSERT INTO public."Table_Catalog"(table_schema,table_name,category,definition,grain,primary_key_columns,source_system,source_tables,source_code_paths,update_rule,related_functions,documentation_status,readiness_mode,readiness_date_column,observation_date_column,data_available_at_column,availability_rule,point_in_time_status,historical_metadata_method)
VALUES('public',{lit(TABLE)},'Feature',{lit('Causal daily technical indicators and independent native TA-Lib candlestick codes; formulas calculation-verified, TradingView parity NOT VERIFIED.')},'One IDX ticker x observed trading date x Daily timeframe',{arr(IDENTITY)},'Python / TA-Lib, existing TradingView OHLCV',ARRAY['Price_Stock_Indonesia_IDX']::text[],{arr(SOURCES)},'Manual bounded refresh only; source corrections require full-history recalculation and output from earliest changed bar onward. No full backfill or scheduler authorized.',ARRAY[]::text[],'VERIFIED','DATA_DATE','trade_date','trade_date',NULL,'Close-t information only; prediction timestamp/target horizon undefined; calculated_at is not historical availability. Source ingestion_time is incomplete.','PARTIAL','No current-universe join; inherits source survivor selection, unknown historical adjustment vintages and source revisions.') ;''')
    lines.append("DO $validator_guard$ BEGIN IF md5(pg_get_functiondef('public.validate_feature_catalog_target()'::regprocedure)) <> md5("+lit(validator_before)+") THEN RAISE EXCEPTION 'Catalog validator changed since inspection'; END IF; END $validator_guard$;")
    lines.append(validator_after.rstrip()+';')
    lines.append("UPDATE public.\"Table_Catalog\" SET related_functions=array_append(related_functions,'public.validate_feature_catalog_target()'),updated_at=clock_timestamp() WHERE table_schema='public' AND table_name IN ('Feature_Catalog','Feature04_Technical_Indicator') AND NOT ('public.validate_feature_catalog_target()'=ANY(related_functions));")
    lines.append("INSERT INTO public.\"Feature_Relationship_Catalog\"(left_feature_table,right_feature_table,left_join_columns,right_join_columns,relationship_type,safe_output_grain,requires_preaggregation,definition,version,is_active) VALUES ('Feature04_Technical_Indicator','Feature_01_Stock_Daily',ARRAY['ticker','trade_date'],ARRAY['ticker','date'],'ONE_TO_ONE','ticker x trade_date x Daily timeframe',false,'Exact observed-date left join on ticker and trade_date=date; Feature04 timeframe must be Daily. Retain unmatched rows; no availability or historical sector/industry validity is implied.','v1',true);")
    feature_fields=['feature_table','feature_column','grain','feature_category','definition','calculation','source_tables','source_columns','lookback_window','minimum_history','unit','null_rule','refresh_trigger','dependency_rule','version','is_active','semantic_role','allowed_aggregations','ranking_interpretation','is_filterable','is_groupable','availability_rule','point_in_time_safe','historical_metadata_warning','analytical_interpretation','recommended_use','misuse_warning','semantic_review_status','validation_evidence']
    for ordinal,col in enumerate(COLUMNS,1):
        category,definition,formula,history,unit,use,warning=specs[col]
        nullable=col not in IDENTITY and col not in ('calculation_version','calculated_at')
        nullrule='NULL before independent lookback or invalid/missing OHLCV; state restarts after an invalid bar. Available non-detection remains INTEGER 0.' if col in PATTERNS else 'NULL before independent initialization or after invalid/missing OHLCV; no zero imputation.' if nullable else 'Required; never synthesized from missing source identity.'
        lines.append(f'''INSERT INTO public."Column_Catalog"(table_schema,table_name,column_name,ordinal_position,data_type,is_nullable,default_expression,is_primary_key,definition,source_column_or_expression,unit,null_rule,source_code_paths,documentation_status)
 SELECT 'public',{lit(TABLE)},{lit(col)},{ordinal},format_type(a.atttypid,a.atttypmod),{str(nullable).lower()},NULL,{str(col in IDENTITY).lower()},{lit(definition)},{lit(formula)},{lit(unit)},{lit(nullrule)},{arr(SOURCES)},'VERIFIED' FROM pg_attribute a WHERE a.attrelid='public."{TABLE}"'::regclass AND a.attname={lit(col)};''')
        role='IDENTITY' if col in ('ticker','trade_date') else 'DIMENSION' if col in ('timeframe','calculation_version','calculated_at') else 'MEASURE'
        vals=[lit(TABLE),lit(col),lit('ticker x trade_date x timeframe'),lit(category),lit(definition),lit(formula),lit('Price_Stock_Indonesia_IDX'),lit('ticker,date,timeframe,open,high,low,close,volume; ingestion_time only in external source manifest'),lit(history),lit(history),lit(unit),lit(nullrule),lit('Manual explicit refresh; no scheduler'),lit('Full available chronological source history through output end; no future bars; each ticker partition isolated'),"'v1'",'true',lit(role),arr(['MIN','MAX','AVG','MEDIAN'] if role=='MEASURE' and col not in PATTERNS else ['COUNT','COUNT_DISTINCT']),"'CONTEXTUAL'" if role=='MEASURE' else "'NOT_APPLICABLE'",'true','true' if role!='MEASURE' else 'false',lit('Close-t feature; actual prediction timestamp and horizon are undefined. Training point-in-time eligibility NOT VERIFIED.'),'false',lit('Incomplete source ingestion_time, no immutable source revision history, historical adjustment basis incomplete; TradingView parity NOT VERIFIED.'),lit(definition+' '+warning),lit(use),lit(warning),"'CALCULATION_VERIFIED'",arr(['verification/feature04/calculation_validation.json','features/feature04/tests/test_engine.py','FEATURE04_TECHNICAL_INDICATOR.md'])]
        lines.append('INSERT INTO public."Feature_Catalog"('+','.join(feature_fields)+') VALUES('+','.join(vals)+');')
    lines.append('COMMIT;')
    return '\n'.join(lines)+'\n'

if __name__=='__main__':
    rendered=render()
    if MIGRATION.exists():
        if MIGRATION.read_text()!=rendered:
            raise RuntimeError('Applied v1 migration is immutable; create a forward migration')
    else:
        MIGRATION.write_text(rendered)
    print(MIGRATION.name)
