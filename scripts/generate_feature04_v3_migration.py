#!/usr/bin/env python3
"""Append Pine SMI/swing columns without changing the applied v1/v2 migrations."""
import hashlib
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'features/feature04'))
from engine import COLUMNS, TABLE
from swing import SWING_COLUMNS
from specs import specifications, SWING_NULL_RULES
from generate_feature04_v2_migration import FIELDS, lit, arr

MIGRATION=ROOT/'database/migrations/20261011_003_add_feature04_smi_swing.sql'
EVIDENCE=['features/feature04/tests/test_swing.py','verification/feature04/SMI_BBCA.md',
          'FEATURE04_COLUMN_DEFINITIONS.md','features/feature04/reference/HH.pine']
SOURCES=['features/feature04/engine.py','features/feature04/swing.py',
         'features/feature04/backfill.py','FEATURE04_COLUMN_DEFINITIONS.md',*EVIDENCE[:2]]
FLAGS=('tracking_high','tracking_low','break_swing_high')
INDICES=('temp_high_bar','temp_low_bar')


def render():
    specs=specifications()
    lines=['BEGIN;',"SET LOCAL lock_timeout='5s';","SET LOCAL statement_timeout='60s';",
           "SELECT pg_advisory_xact_lock(hashtextextended('Feature04_Technical_Indicator',0));",
           '''DO $guard$ BEGIN
 IF (SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='Feature04_Technical_Indicator')<>46
 OR (SELECT count(*) FROM public."Feature_Catalog" WHERE feature_table='Feature04_Technical_Indicator' AND is_active AND version='v2')<>46
 OR EXISTS(SELECT 1 FROM public."Feature_Catalog" WHERE feature_table='Feature04_Technical_Indicator' AND version='v3') THEN
 RAISE EXCEPTION 'Expected inspected v2 schema/catalog; stop for inspection'; END IF;
END $guard$;''']
    adds=[]
    for col in SWING_COLUMNS:
        dtype='integer' if col in FLAGS+INDICES else 'double precision'
        adds.append(f'ADD COLUMN {col} {dtype}')
        check=f'{col} IN (0,1)' if col in FLAGS else f'{col}>=0' if col in INDICES else f"{col}>'-Infinity'::double precision AND {col}<'Infinity'::double precision"
        adds.append(f'ADD CONSTRAINT feature04_{col}_valid CHECK({col} IS NULL OR ({check}))')
    lines.append(f'ALTER TABLE public."{TABLE}"\n '+',\n '.join(adds)+';')
    lines.append(f'COMMENT ON TABLE public."{TABLE}" IS '+lit('55-column daily technical Feature04: unchanged TA-Lib v1/v2 formulas plus Pine SMI14/5/5 ±40 and post-bar swing state. v3 BBCA only initially; other tickers retain v2 and NULL new columns. Closed-bar trigger INTEGER 1/0; no historical backdating, scheduler or TradingView-export parity claim.')+';')
    lines.append(f'''UPDATE public."Table_Catalog" SET definition={lit('55-column causal daily indicators, native candlestick codes, strict inside bar and Pine SMI/swing state. Initial SMI extension calculated for BBCA only; other rows retain v2. TradingView chart parity NOT VERIFIED.')},
 source_code_paths={arr(SOURCES)},update_rule={lit('Manual scoped chronological replay; SMI v3 initially BBCA only. Existing serial/bounded writers calculate v3 only when explicitly invoked within authorized scope; no scheduler.')},updated_at=clock_timestamp()
 WHERE table_schema='public' AND table_name={lit(TABLE)};''')
    copies=[]
    for field in FIELDS:
        copies.append("'v3'" if field=='version' else 'true' if field=='is_active' else
                      'validation_evidence || '+arr(['FEATURE04_COLUMN_DEFINITIONS.md']) if field=='validation_evidence' else field)
    lines.append(f'UPDATE public."Feature_Catalog" SET is_active=false WHERE feature_table={lit(TABLE)} AND version=\'v2\';')
    lines.append('INSERT INTO public."Feature_Catalog"('+','.join(FIELDS)+') SELECT '+','.join(copies)+f' FROM public."Feature_Catalog" WHERE feature_table={lit(TABLE)} AND version=\'v2\';')
    for col in SWING_COLUMNS:
        category,definition,formula,history,unit,use,warning=specs[col]
        null_rule=SWING_NULL_RULES[col]
        lines.append(f'COMMENT ON COLUMN public."{TABLE}".{col} IS '+lit(definition+' '+formula+' '+null_rule)+';')
        lines.append(f'''INSERT INTO public."Column_Catalog"(table_schema,table_name,column_name,ordinal_position,data_type,is_nullable,default_expression,is_primary_key,definition,source_column_or_expression,unit,null_rule,source_code_paths,documentation_status)
 SELECT 'public',{lit(TABLE)},{lit(col)},a.attnum,format_type(a.atttypid,a.atttypmod),true,NULL,false,{lit(definition)},{lit(formula)},{lit(unit)},{lit(null_rule)},{arr(SOURCES)},'VERIFIED'
 FROM pg_attribute a WHERE a.attrelid='public."{TABLE}"'::regclass AND a.attname={lit(col)};''')
        role='DIMENSION' if col in INDICES or col in ('tracking_high','tracking_low') else 'MEASURE'
        aggregations=['COUNT','SUM','AVG'] if col=='break_swing_high' else ['COUNT','COUNT_DISTINCT'] if role=='DIMENSION' else ['MIN','MAX','AVG','MEDIAN']
        vals=[lit(TABLE),lit(col),lit('ticker x trade_date x timeframe'),lit(category),lit(definition),lit(formula),
              lit('Price_Stock_Indonesia_IDX'),lit('ticker,date,timeframe,high,low,close; OHLCV validation'),
              lit(history),lit(history),lit(unit),lit(null_rule),lit('Manual explicitly authorized ticker replay; no scheduler'),
              lit('Chronological full source history per ticker/timeframe; post-bar Pine block order, no future bars; invalid OHLCV resets state'),
              "'v3'",'true',lit(role),arr(aggregations),lit('NOT_APPLICABLE' if role=='DIMENSION' else 'CONTEXTUAL'),
              'true','true' if role=='DIMENSION' else 'false',
              lit('Available after current Daily close, with confirmation-date state only. Initial scope BBCA; uncomputed other tickers NULL. Prediction timestamp/horizon and training point-in-time eligibility NOT VERIFIED.'),
              'false',lit('Source revision/adjustment vintages and historical availability incomplete; chart-export numerical parity NOT VERIFIED. Bar indices are relative to available ticker source history.'),
              lit(definition+' '+warning),lit(use),lit(warning),"'CALCULATION_VERIFIED'",arr(EVIDENCE)]
        lines.append('INSERT INTO public."Feature_Catalog"('+','.join(FIELDS)+') VALUES('+','.join(vals)+');')
    lines.append(f'''DO $verify$ BEGIN
 IF (SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name={lit(TABLE)})<>55
 OR (SELECT count(*) FROM public."Feature_Catalog" WHERE feature_table={lit(TABLE)} AND is_active AND version='v3')<>55 THEN
 RAISE EXCEPTION 'Feature04 v3 schema/catalog mismatch'; END IF;
END $verify$;''')
    lines.append('COMMIT;')
    return '\n'.join(lines)+'\n'


if __name__=='__main__':
    content=render()
    applied={name:digest for digest,name in (line.split('  ',1) for line in
             (ROOT/'database/migrations/APPLIED.sha256').read_text().splitlines() if line and not line.startswith('#'))}
    if MIGRATION.name in applied and hashlib.sha256(content.encode()).hexdigest()!=applied[MIGRATION.name]:
        raise RuntimeError('Applied migration is immutable; add a forward migration')
    if MIGRATION.name in applied and MIGRATION.exists() and MIGRATION.read_text()!=content:
        raise RuntimeError('Applied SQL file differs from its generator/manifest; stop for inspection')
    if not MIGRATION.exists() or MIGRATION.read_text()!=content:
        MIGRATION.write_text(content)
    print(MIGRATION.name)
