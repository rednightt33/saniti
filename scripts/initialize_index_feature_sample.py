#!/usr/bin/env python3
"""Atomic creation of six INDEX feature tables, one output date, archive then clean legacy index rows.
No daily scheduler/worker/configuration changes. Default dry run; cleanup requires explicit flag.
"""
from __future__ import annotations
import argparse,hashlib,json,math,os,sys,uuid,statistics
from datetime import date
from pathlib import Path
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'features/feature04')]
import upsert_index_broker_feature_sample as prior
from backfill_feature_02_v2 import INSERT_TICKER
from engine import calculate,FEATURE_COLUMNS,COLUMNS
BASE={1:'Feature_01_Stock_Daily',2:'Feature_02_Broker_Rolling',3:'Feature_03_Stock_Broker_Daily',4:'Feature_04_Technical_Indicator',5:'Feature_05_Foreign_Domestic_Broker_Detail',6:'Feature_06_Foreign_Domestic'}
COVER=('frequency_source_rows','buy_freq_known_rows','sell_freq_known_rows','buy_freq_missing_rows','sell_freq_missing_rows')
MIGRATION='database/migrations/20261024_010_create_index_feature_tables.sql'
def emit(event,**kw):prior.emit(event,**kw)
def columns(db,table):return [r['column_name'] for r in db.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position",(table,))]
def ref2(db,day):
 rows=db.execute('SELECT * FROM feature_02_v2_daily_base ORDER BY date').fetchall();calendar=sorted({r['date'] for r in rows});pairs={}
 for r in rows:pairs.setdefault((r['broker'],r['investor_type'],r['market_board']),{})[r['date']]=r
 checks=0
 for a in db.execute('SELECT * FROM index_f2 WHERE date=%s',(day,)):
  pair=pairs[(a['broker'],a['investor_type'],a['market_board'])];seq=[pair.get(d) for d in calendar]
  nv=[float(r['net_value']) if r else 0.0 for r in seq];nl=[float(r['net_lots']) if r else 0.0 for r in seq]
  active=[int(bool(r) and any(r[c]!=0 for c in ['buy_value','sell_value','buy_lots','sell_lots'])) for r in seq];e={}
  for n in (5,20,60):
   e[f'net_value_{n}d']=sum(nv[-n:]) if len(nv)>=n else None;e[f'net_lots_{n}d']=sum(nl[-n:]) if len(nl)>=n else None
  for n in (20,60):
   valid=len(nv)>=n;buy=sum(v>0 for v in nv[-n:]);sell=sum(v<0 for v in nv[-n:]);act=sum(active[-n:])
   for name,v in [('buy_days',buy),('sell_days',sell),('active_days',act),('stock_trading_days',n),('buy_day_ratio',buy/n),('buy_share_active_days',buy/act if act else None)]:e[f'{name}_{n}d']=v if valid else None
   h=[sum(nv[i-n+1:i+1]) for i in range(len(nv)-253,len(nv)-1)] if len(nv)>=n+252 else [];cur=e[f'net_value_{n}d'];sd=statistics.stdev(h) if h else 0
   e[f'net_value_zscore_{n}d']=(cur-statistics.mean(h))/sd if sd else None
   e[f'net_value_percentile_{n}d']=100*(sum(v<cur for v in h)+0.5*sum(v==cur for v in h))/252 if h else None
  pos=[v for v in nv[-20:] if v>0]
  e.update(positive_net_value_20d=sum(pos) if len(nv)>=20 else None,largest_buy_day_20d=max(pos) if pos and len(nv)>=20 else None,largest_buy_day_share_20d=max(pos)/sum(pos) if pos and len(nv)>=20 else None)
  for c,v in e.items():
   if not prior.equal(a[c],v):raise RuntimeError('Feature2 reference mismatch '+c)
   checks+=1
 return checks

def prepare_all(db,ticker,day):
 # Established F03/F06 reference validation, including full-history cumulative and strict derived-frequency coverage.
 prior.prepare(db,ticker,day)
 db.execute((ROOT/MIGRATION).read_text(),prepare=False)
 # No shared-table refresh. Clone F01 writer into a session-local target.
 db.execute('CREATE TEMP TABLE index_f1 (LIKE public."Feature_01_Stock_Daily" INCLUDING ALL) ON COMMIT DROP')
 prior.clone_writer(db,'public.refresh_feature_01_stock_daily(date,text[])','index_f1_compute',{BASE[1]:'index_f1'})
 db.execute('SELECT pg_temp.index_f1_compute(%s,ARRAY[%s])',(day,ticker))
 # Exact bounded-context F02 rolling reference: 312 preceding aggregate sessions plus output day.
 start=db.execute('SELECT MIN(d) AS d FROM (SELECT DISTINCT trade_date AS d FROM s5 WHERE trade_date<=%s ORDER BY d DESC LIMIT 313)x',(day,)).fetchone()['d']
 db.execute('''CREATE TEMP TABLE feature_02_v2_daily_base ON COMMIT DROP AS
 SELECT trade_date AS date,%s::text AS ticker,broker,investor_type,market_board,SUM(buy_value) AS buy_value,SUM(sell_value) AS sell_value,
 SUM(buy_lots) AS buy_lots,SUM(sell_lots) AS sell_lots,SUM(net_value) AS net_value,SUM(net_lots) AS net_lots
 FROM public."Feature_05_Foreign_Domestic_Broker_Detail" f WHERE trade_date BETWEEN %s AND %s
 AND NOT EXISTS(SELECT 1 FROM public."IDX_Stock_Universe" u WHERE u."Ticker"=f.ticker AND u."Security Type"='index')
 GROUP BY trade_date,broker,investor_type,market_board''',(ticker,start,day))
 db.execute('CREATE INDEX ON feature_02_v2_daily_base(date,broker,investor_type,market_board)');db.execute('ANALYZE feature_02_v2_daily_base')
 db.execute('CREATE TEMP TABLE index_f2 (LIKE public."Feature_02_Broker_Rolling" INCLUDING ALL) ON COMMIT DROP')
 statement=INSERT_TICKER.replace('INSERT INTO public."Feature_02_Broker_Rolling"','INSERT INTO index_f2')
 if statement==INSERT_TICKER:raise RuntimeError('F02 target contract changed')
 db.execute(statement,(ticker,));checks=ref2(db,day)
 # Current-date additive fields must equal independently aggregated raw broker source.
 bad=db.execute('''SELECT count(*) AS n FROM index_f2 f FULL JOIN current_detail d ON f.date=d.trade_date AND f.ticker=d.ticker
 AND f.broker=d.broker AND f.investor_type=d.investor_type AND f.market_board=d.market_board
 WHERE COALESCE(f.date,d.trade_date)=%s AND (f.ticker IS NULL OR d.ticker IS NULL OR
 ROW(f.buy_value_1d,f.sell_value_1d,f.net_value_1d,f.buy_lots_1d,f.sell_lots_1d,f.net_lots_1d)
 IS DISTINCT FROM ROW(d.buy_value,d.sell_value,d.net_value,d.buy_lots,d.sell_lots,d.net_lots))''',(day,)).fetchone()['n']
 if bad:raise RuntimeError('F02 daily source mismatch')
 emit('feature2_validated',rolling_comparisons=checks,source_start=start,output_date=day)
 # Refined F05: retain available sums with explicit per-side coverage.
 db.execute('''CREATE TEMP TABLE freq_coverage ON COMMIT DROP AS
 SELECT "Broker"::text AS broker,"Investor Type"::text AS investor_type,"Market Board"::text AS market_board,
 SUM(buy_freq)::bigint AS buy_freq,SUM(sell_freq)::bigint AS sell_freq,COUNT(*)::bigint AS frequency_source_rows,
 COUNT(buy_freq)::bigint AS buy_freq_known_rows,COUNT(sell_freq)::bigint AS sell_freq_known_rows,
 (COUNT(*)-COUNT(buy_freq))::bigint AS buy_freq_missing_rows,(COUNT(*)-COUNT(sell_freq))::bigint AS sell_freq_missing_rows
 FROM public."IDX_Broker_Summary" WHERE "Date"=%s GROUP BY 1,2,3''',(day,))
 db.execute('''UPDATE current_detail d SET buy_freq=c.buy_freq,sell_freq=c.sell_freq FROM freq_coverage c
 WHERE d.broker=c.broker AND d.investor_type=c.investor_type AND d.market_board=c.market_board''')
 for col,side,inv in [('foreign_buy_freq_1d','buy_freq','Foreign'),('foreign_sell_freq_1d','sell_freq','Foreign'),('domestic_buy_freq_1d','buy_freq','Domestic'),('domestic_sell_freq_1d','sell_freq','Domestic')]:
  db.execute(sql.SQL('''UPDATE s6 t SET {}=(SELECT CASE WHEN COUNT(*)=0 THEN 0 ELSE SUM({}) END FROM current_detail d
   WHERE d.market_board=t.market_board AND d.investor_type=%s) WHERE t.trade_date=%s''').format(sql.Identifier(col),sql.Identifier(side)),(inv,day))
 # F06 derived-frequency outputs keep the validated NULL rule when any required input window is incomplete.
 # F04 numerical calculations unchanged; source legacy class is only an adapter for the existing engine validator.
 history=db.execute('''SELECT p.*,u."Security Type" AS security_type,u."TradingView Symbol" AS universe_tradingview_symbol,
 public.feature04_asset_type(p.ticker) AS asset_type FROM public."Price_Stock_Indonesia_IDX" p JOIN public."IDX_Stock_Universe" u ON u."Ticker"=p.ticker
 WHERE p.ticker=%s AND p.date<=%s AND p.is_final ORDER BY p.date''',(ticker,day)).fetchall()
 expected=[r for r in calculate(history) if r['trade_date']==day]
 if len(expected)!=1:raise RuntimeError('F04 date unavailable')
 expected[0]['asset_type']='index'
 old=db.execute('SELECT * FROM public."Feature_04_Technical_Indicator" WHERE ticker=%s AND trade_date=%s',(ticker,day)).fetchone()
 if old and any(not prior.equal(old[c],expected[0][c]) for c in FEATURE_COLUMNS):raise RuntimeError('F04 numerical drift')
 db.execute('CREATE TEMP TABLE index_f4 (LIKE public."Feature_04_Technical_Indicator_INDEX" INCLUDING ALL) ON COMMIT DROP')
 names=sql.SQL(',').join(map(sql.Identifier,COLUMNS))
 db.execute(sql.SQL('INSERT INTO index_f4 ({}) VALUES ({})').format(names,sql.SQL(',').join(sql.Placeholder() for _ in COLUMNS)),[expected[0][c] for c in COLUMNS])
 # Compare all 29 F01 payload cells to the prior verified stored source before archival/deletion.
 before=db.execute('SELECT * FROM public."Feature_01_Stock_Daily" WHERE ticker=%s AND date=%s',(ticker,day)).fetchone()
 f1=db.execute('SELECT * FROM index_f1 WHERE ticker=%s AND date=%s',(ticker,day)).fetchone()
 if not f1:raise RuntimeError('F01 sample empty')
 if before:
  for c in f1:
   a,b=f1[c],before[c]
   if c in ('date','ticker','sector','industry'):ok=a==b
   else:ok=prior.equal(a,b)
   if not ok:raise RuntimeError('F01 payload differs '+c)
 emit('price_features_validated',feature1_columns=len(f1),feature4_columns=len(FEATURE_COLUMNS))

def write_and_archive(db,ticker,day,snapshot,cleanup):
 stages={1:('index_f1','date'),2:('index_f2','date'),3:('s3','date'),4:('index_f4','trade_date'),5:('current_detail','trade_date'),6:('s6','trade_date')}
 counts={}
 for f,base in BASE.items():
  target=base+'_INDEX';stage,dc=stages[f]
  cols=columns(db,base);names=sql.SQL(',').join(map(sql.Identifier,cols))
  exists=db.execute(sql.SQL('SELECT count(*) AS n FROM public.{} WHERE ticker=%s AND {}<>%s').format(sql.Identifier(target),sql.Identifier(dc)),(ticker,day)).fetchone()['n']
  if exists:raise RuntimeError('Target already has dates beyond this sample')
  db.execute(sql.SQL('DELETE FROM public.{} WHERE ticker=%s AND {}=%s').format(sql.Identifier(target),sql.Identifier(dc)),(ticker,day))
  db.execute(sql.SQL('INSERT INTO public.{} ({}) SELECT {} FROM {} WHERE ticker=%s AND {}=%s').format(sql.Identifier(target),names,names,sql.Identifier(stage),sql.Identifier(dc)),(ticker,day))
  if f in (5,6):
   group='broker,investor_type,market_board' if f==5 else 'market_board'
   joins=' AND '.join('t.'+c+'=c.'+c for c in group.split(','))
   db.execute(sql.SQL('UPDATE public.{} t SET {} FROM (SELECT '+group+','+','.join('SUM('+c+') AS '+c for c in COVER)+' FROM freq_coverage GROUP BY '+group+')c WHERE t.ticker=%s AND t.trade_date=%s AND '+joins).format(sql.Identifier(target),sql.SQL(',').join(sql.SQL('{}=c.{}').format(sql.Identifier(c),sql.Identifier(c)) for c in COVER)),(ticker,day))
  mismatch=db.execute(sql.SQL('SELECT count(*) AS n FROM ((SELECT {} FROM public.{} WHERE ticker=%s AND {}=%s EXCEPT SELECT {} FROM {} WHERE ticker=%s AND {}=%s) UNION ALL (SELECT {} FROM {} WHERE ticker=%s AND {}=%s EXCEPT SELECT {} FROM public.{} WHERE ticker=%s AND {}=%s))x').format(names,sql.Identifier(target),sql.Identifier(dc),names,sql.Identifier(stage),sql.Identifier(dc),names,sql.Identifier(stage),sql.Identifier(dc),names,sql.Identifier(target),sql.Identifier(dc)),(ticker,day,ticker,day,ticker,day,ticker,day)).fetchone()['n']
  if mismatch:raise RuntimeError('INDEX stored mismatch '+target)
  counts[f]=db.execute(sql.SQL('SELECT count(*) AS n FROM public.{} WHERE ticker=%s').format(sql.Identifier(target)),(ticker,)).fetchone()['n']
  emit('index_table_verified',table=target,date=day,rows=counts[f],mismatches=0)
 # Explicit reconciliation of refined sums and all new coverage fields before cleanup.
 differences=db.execute('''SELECT count(*) AS n FROM public."Feature_05_Foreign_Domestic_Broker_Detail_INDEX" t
 FULL JOIN freq_coverage c USING(broker,investor_type,market_board)
 WHERE (t.ticker=%s AND t.trade_date=%s OR t.ticker IS NULL) AND
 ROW(t.buy_freq,t.sell_freq,t.frequency_source_rows,t.buy_freq_known_rows,t.sell_freq_known_rows,t.buy_freq_missing_rows,t.sell_freq_missing_rows)
 IS DISTINCT FROM ROW(c.buy_freq,c.sell_freq,c.frequency_source_rows,c.buy_freq_known_rows,c.sell_freq_known_rows,c.buy_freq_missing_rows,c.sell_freq_missing_rows)''',(ticker,day)).fetchone()['n']
 if differences:raise RuntimeError('Refined F05 frequency/coverage mismatch')
 for r in db.execute('SELECT * FROM public."Feature_06_Foreign_Domestic_INDEX" WHERE ticker=%s AND trade_date=%s',(ticker,day)):
  for col,side,inv in [('foreign_buy_freq_1d','buy_freq','Foreign'),('foreign_sell_freq_1d','sell_freq','Foreign'),('domestic_buy_freq_1d','buy_freq','Domestic'),('domestic_sell_freq_1d','sell_freq','Domestic')]:
   value=db.execute(sql.SQL('SELECT CASE WHEN COUNT(*)=0 THEN 0 ELSE SUM({}) END AS v FROM freq_coverage WHERE investor_type=%s AND market_board=%s').format(sql.Identifier(side)),(inv,r['market_board'])).fetchone()['v']
   if r[col]!=value:raise RuntimeError('Refined F06 frequency mismatch '+col)
 emit('refined_frequency_verified',feature5_frequency_and_coverage_mismatches=0,feature6_daily_frequency_comparisons=12)
 # The archive is durable in the same transaction as cleanup. Every original row is preserved losslessly.
 deleted={}
 for f,base in BASE.items():
  count=db.execute(sql.SQL('SELECT count(*) AS n FROM public.{} WHERE ticker=%s').format(sql.Identifier(base)),(ticker,)).fetchone()['n']
  db.execute(sql.SQL('''INSERT INTO migration_archive.index_feature_rows(snapshot_id,source_table,row_hash,row_data)
   SELECT %s,%s,md5(to_jsonb(t)::text),to_jsonb(t) FROM public.{} t WHERE ticker=%s ON CONFLICT DO NOTHING''').format(sql.Identifier(base)),(snapshot,base,ticker))
  archived=db.execute('SELECT count(*) AS n FROM migration_archive.index_feature_rows WHERE snapshot_id=%s AND source_table=%s',(snapshot,base)).fetchone()['n']
  if archived!=count:raise RuntimeError('Archive count mismatch '+base)
  missing=db.execute(sql.SQL('SELECT count(*) AS n FROM public.{} t WHERE ticker=%s AND NOT EXISTS(SELECT 1 FROM migration_archive.index_feature_rows b WHERE b.snapshot_id=%s AND b.source_table=%s AND b.row_hash=md5(to_jsonb(t)::text) AND b.row_data=to_jsonb(t))').format(sql.Identifier(base)),(ticker,snapshot,base)).fetchone()['n']
  if missing:raise RuntimeError('Archive payload mismatch '+base)
  if cleanup:
   affected=db.execute(sql.SQL('DELETE FROM public.{} WHERE ticker=%s').format(sql.Identifier(base)),(ticker,)).rowcount
   if affected!=count:raise RuntimeError('Legacy deletion count changed')
  deleted[f]=count if cleanup else 0
 # Activate metadata only after source/payload/archive checks have succeeded. The single-date
 # availability rule remains explicit: this does not claim bulk history or daily updates are ready.
 targets=[t+'_INDEX' for t in BASE.values()]
 db.execute('UPDATE public."Table_Catalog" SET documentation_status=%s WHERE table_schema=%s AND table_name=ANY(%s)',('VERIFIED','public',targets))
 db.execute('UPDATE public."Feature_Catalog" SET is_active=true WHERE feature_table=ANY(%s) AND version=%s',(targets,'v1'))
 emit('archive_and_cleanup_verified',snapshot_id=snapshot,archived_total=sum(deleted.values()),deleted=deleted,cleanup=cleanup)
 return counts

def main():
 p=argparse.ArgumentParser();p.add_argument('--ticker',required=True);p.add_argument('--date',required=True,type=date.fromisoformat);p.add_argument('--apply',action='store_true');p.add_argument('--cleanup-legacy',action='store_true');p.add_argument('--snapshot-id',required=True,type=uuid.UUID);a=p.parse_args()
 if a.apply and not a.cleanup_legacy:raise ValueError('This approved migration requires explicit archival legacy cleanup flag')
 with psycopg.connect(os.environ['DATABASE_URL'],row_factory=dict_row,application_name='index-six-table-single-date') as db:
  prepare_all(db,a.ticker,a.date)
  result=write_and_archive(db,a.ticker,a.date,a.snapshot_id,a.cleanup_legacy)
  if not a.apply:db.rollback()
 emit('complete',committed=a.apply,ticker=a.ticker,date=a.date,counts=result,snapshot_id=a.snapshot_id,bulk=False,daily_updates_enabled=False)
if __name__=='__main__':main()
