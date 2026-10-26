#!/usr/bin/env python3
"""Feature 3/5/6: one index, one date, shared aggregate formulas for subsequent bulk.
Default rollback. No source/schema/Feature2/Feature4 mutation. Board partitions retained.
"""
from __future__ import annotations
import argparse,json,os,sys,math,hashlib
from datetime import date
from pathlib import Path
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
sys.path.insert(0,str(Path(__file__).resolve().parent))
TABLES={3:'Feature_03_Stock_Broker_Daily',5:'Feature_05_Foreign_Domestic_Broker_Detail',6:'Feature_06_Foreign_Domestic'}
def emit(event,**kw):print(json.dumps(dict(event=event,**kw),default=str),flush=True)
def equal(a,b):
 if a is None or b is None:return a is None and b is None
 if isinstance(a,str) or isinstance(b,str):return a==b
 return math.isclose(float(a),float(b),rel_tol=1e-9,abs_tol=1e-9)
def clone_writer(db,signature,name,stages):
 definition=db.execute('SELECT pg_get_functiondef(%s::regprocedure) AS d',(signature,)).fetchone()['d']
 emit('formula_snapshot',routine=signature,sha256=hashlib.sha256(definition.encode()).hexdigest())
 original=signature.split('(')[0].split('.')[-1]
 definition=definition.replace('FUNCTION public.'+original+'(', 'FUNCTION pg_temp.'+name+'(')
 if 'FUNCTION pg_temp.'+name+'(' not in definition:raise RuntimeError('Unexpected function identity')
 for table,stage in stages.items():
  token='public."'+table+'"'
  if token not in definition:raise RuntimeError('Unexpected SQL source contract '+table)
  definition=definition.replace(token,'pg_temp.'+stage)
 db.execute(definition,prepare=False)
def prepare(db,ticker,day):
 """Same daily aggregation, rolling, cumulative and missingness contract for sample and future bulk."""
 db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
 db.execute("SET LOCAL statement_timeout='20min'")
 db.execute("SET LOCAL lock_timeout='15s'")
 db.execute("SELECT pg_advisory_xact_lock(hashtextextended('index-broker-feature-sample',0))")
 u=db.execute('SELECT "Security Type" AS kind FROM public."IDX_Stock_Universe" WHERE "Ticker"=%s',(ticker,)).fetchone()
 if not u or u['kind']!='index':raise ValueError('Target must be an explicit universe index')
 for f,t in TABLES.items():db.execute(sql.SQL('CREATE TEMP TABLE {} (LIKE public.{} INCLUDING DEFAULTS) ON COMMIT DROP').format(sql.Identifier('s'+str(f)),sql.Identifier(t)))
 # Exact daily aggregation directly from raw source. Per-source-symbol gap flags cannot cancel.
 db.execute('''CREATE TEMP TABLE current_detail ON COMMIT DROP AS
 WITH b AS (SELECT *,SUM("Buy Value") OVER(PARTITION BY "Symbol","Market Board") <>
 SUM("Sell Value") OVER(PARTITION BY "Symbol","Market Board") AS gap
 FROM public."IDX_Broker_Summary" WHERE "Date"=%s)
 SELECT %s::date AS trade_date,%s::text AS ticker,"Broker"::text AS broker,"Market Board"::text AS market_board,
 "Investor Type"::text AS investor_type,SUM("Buy Value") AS buy_value,SUM("Sell Value") AS sell_value,
 SUM("Buy Value"-"Sell Value") AS net_value,SUM("Buy Lots") AS buy_lots,SUM("Sell Lots") AS sell_lots,
 SUM("Buy Lots"-"Sell Lots") AS net_lots,
 CASE WHEN count(buy_freq)=count(*) THEN SUM(buy_freq)::bigint END AS buy_freq,
 CASE WHEN count(sell_freq)=count(*) THEN SUM(sell_freq)::bigint END AS sell_freq,
 bool_or(gap) AS source_balance_gap,statement_timestamp() AS calculated_at
 FROM b GROUP BY "Broker","Market Board","Investor Type"''',(day,day,ticker))
 if not db.execute('SELECT 1 FROM current_detail LIMIT 1').fetchone():raise ValueError('No source on output date')
 # Daily-only F02-shaped temporary input. F03 does not depend on any F02 rolling output.
 db.execute('CREATE TEMP TABLE f2_daily (LIKE public."Feature_02_Broker_Rolling" INCLUDING DEFAULTS) ON COMMIT DROP')
 db.execute('''INSERT INTO f2_daily(date,ticker,broker,investor_type,market_board,broker_classification,
 buy_value_1d,sell_value_1d,net_value_1d,buy_lots_1d,sell_lots_1d,net_lots_1d)
 SELECT d.trade_date,d.ticker,d.broker,d.investor_type,d.market_board,p.broker_classification,
 d.buy_value,d.sell_value,d.net_value,d.buy_lots,d.sell_lots,d.net_lots FROM current_detail d
 LEFT JOIN public."IDX_Broker_Profile" p ON p.broker_code=d.broker''')
 clone_writer(db,'public.refresh_feature_03_stock_broker_daily(date,text[])','compute3',{'Feature_02_Broker_Rolling':'f2_daily',TABLES[3]:'s3'})
 db.execute('SELECT pg_temp.compute3(%s,ARRAY[%s])',(day,ticker))
 db.execute('UPDATE s3 SET broker_concentration_hhi=NULL')
 emit('stage_complete',stage='daily_and_feature3')
 # Earlier canonical broker details are exact additive source context, aggregated to only
 # date/board/investor (no need to materialize broker rolling histories for Feature06).
 db.execute('''INSERT INTO s5
 SELECT trade_date,%s::text,'__CONTEXT__'::text,market_board,investor_type,
 SUM(buy_value),SUM(sell_value),SUM(net_value),SUM(buy_lots),SUM(sell_lots),SUM(net_lots),
 CASE WHEN count(buy_freq)=count(*) THEN SUM(buy_freq)::bigint END,
 CASE WHEN count(sell_freq)=count(*) THEN SUM(sell_freq)::bigint END,
 bool_or(source_balance_gap),statement_timestamp()
 FROM public."Feature_05_Foreign_Domestic_Broker_Detail" f
 WHERE trade_date<%s AND NOT EXISTS(SELECT 1 FROM public."IDX_Stock_Universe" u WHERE u."Ticker"=f.ticker AND u."Security Type"='index')
 GROUP BY trade_date,market_board,investor_type''',(ticker,day))
 db.execute('INSERT INTO s5 SELECT * FROM current_detail')
 db.execute('CREATE INDEX ON s5(ticker,trade_date)');db.execute('ANALYZE s5')
 emit('stage_complete',stage='historical_context',rows=db.execute('SELECT count(*) AS n FROM s5').fetchone()['n'])
 clone_writer(db,'public.refresh_feature_06(text,date)','compute6',{TABLES[5]:'s5',TABLES[6]:'s6'})
 db.execute('SELECT pg_temp.compute6(%s,NULL)',(ticker,))
 freqcols=[r['column_name'] for r in db.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s AND (column_name LIKE '%%freq%%' OR column_name LIKE '%%ticket%%')",(TABLES[6],))]
 calendar=[r['trade_date'] for r in db.execute('SELECT DISTINCT trade_date FROM s5 ORDER BY trade_date')]
 bad={}
 for r in db.execute('SELECT DISTINCT trade_date,market_board FROM s5 WHERE buy_freq IS NULL OR sell_freq IS NULL'):
  bad.setdefault(r['market_board'],set()).add(r['trade_date'])
 # SQL SUM skips missing values, so completeness must also hold across the full input window.
 for board in db.execute('SELECT market_board FROM s6 WHERE trade_date=%s',(day,)):
  for c in freqcols:
   n=25 if 'vs_prev20d' in c else (20 if '_20d' in c else 1)
   if set(calendar[-n:]) & bad.get(board['market_board'],set()):
    db.execute(sql.SQL('UPDATE s6 SET {}=NULL WHERE trade_date=%s AND market_board=%s').format(sql.Identifier(c)),(day,board['market_board']))
 # Independent Feature06 reference: aggregate only additive daily inputs, then recompute.
 import pandas as pd
 from check_feature_06_sample import compute
 agg=db.execute('''SELECT trade_date,market_board,investor_type,SUM(buy_value) AS buy_value,SUM(sell_value) AS sell_value,
 SUM(buy_lots) AS buy_lots,SUM(sell_lots) AS sell_lots,SUM(buy_freq) AS buy_freq,SUM(sell_freq) AS sell_freq,
 bool_or(source_balance_gap) AS source_balance_gap FROM s5 GROUP BY trade_date,market_board,investor_type''').fetchall()
 reference=compute(pd.DataFrame(agg));reference=reference[reference.trade_date==day]
 comparisons=0
 for actual in db.execute('SELECT * FROM s6 WHERE trade_date=%s',(day,)):
  row=reference[reference.market_board==actual['market_board']].iloc[0]
  for c in reference.columns:
   if c in ('trade_date','market_board'):continue
   value=row[c]
   if c in freqcols:
    n=25 if 'vs_prev20d' in c else (20 if '_20d' in c else 1)
    if set(calendar[-n:]) & bad.get(actual['market_board'],set()):value=None
   if value is not None and pd.isna(value):value=None
   if not equal(actual[c],value):raise RuntimeError('Independent Feature06 mismatch '+actual['market_board']+'/'+c)
   comparisons+=1
 # Reference Feature03 from daily broker entries, including active zero-net brokers and source investor identity.
 checks3=0
 for a in db.execute('SELECT * FROM s3 WHERE date=%s',(day,)):
  entries=db.execute('SELECT * FROM f2_daily WHERE date=%s AND market_board=%s',(day,a['market_board'])).fetchall();brokers={}
  for r in entries:
   b=brokers.setdefault(r['broker'],dict(net=0,buy=0,sell=0,active=False,classification=r['broker_classification']))
   b['net']+=r['net_value_1d'];b['buy']+=r['buy_value_1d'];b['sell']+=r['sell_value_1d']
   b['active'] |= any(r[c]!=0 for c in ['buy_value_1d','sell_value_1d','buy_lots_1d','sell_lots_1d'])
  buyers=sorted([(k,b['net']) for k,b in brokers.items() if b['net']>0],key=lambda x:(-x[1],x[0]))
  sellers=sorted([(k,b['net']) for k,b in brokers.items() if b['net']<0],key=lambda x:(x[1],x[0]))
  active=sum(b['active'] for b in brokers.values());positive=sum(v for k,v in buyers);top3=sum(v for k,v in buyers[:3])
  exp=dict(total_buy_value=sum(b['buy'] for b in brokers.values()),total_sell_value=sum(b['sell'] for b in brokers.values()),
   active_broker_count=active,net_buy_broker_count=len(buyers),net_sell_broker_count=len(sellers),net_buy_broker_ratio=len(buyers)/active if active else None,
   foreign_net_value=sum(r['net_value_1d'] for r in entries if r['investor_type']=='Foreign'),domestic_net_value=sum(r['net_value_1d'] for r in entries if r['investor_type']=='Domestic'),
   top_buyer=buyers[0][0] if buyers else None,top_buyer_net_value=buyers[0][1] if buyers else None,top_seller=sellers[0][0] if sellers else None,top_seller_net_value=sellers[0][1] if sellers else None,
   top3_buyer_net_value=top3,positive_net_value_total=positive,top3_buyer_share=top3/positive if positive else None,broker_concentration_hhi=None)
  for col,kind in [('institutional','Institutional-heavy'),('retail','Retail-heavy'),('mixed','Mixed'),('niche','Niche')]:exp[col+'_net_value']=sum(b['net'] for b in brokers.values() if b['classification']==kind)
  for c,v in exp.items():
   if not equal(a[c],v):raise RuntimeError('Independent Feature03 mismatch '+c)
   checks3+=1
 emit('validated',feature3_comparisons=checks3,feature6_comparisons=comparisons,source='raw daily + canonical historical broker detail',hhi='NULL by policy')
 return freqcols

def upsert_one_date(db,ticker,day):
 counts={}
 for f,t in TABLES.items():
  dc='date' if f==3 else 'trade_date';stage='current_detail' if f==5 else 's'+str(f)
  cols=[r['column_name'] for r in db.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position",(t,))]
  keys=['ticker',dc,'market_board']+(['broker','investor_type'] if f==5 else [])
  names=sql.SQL(',').join(map(sql.Identifier,cols));keysql=sql.SQL(',').join(map(sql.Identifier,keys))
  sets=sql.SQL(',').join(sql.SQL('{}=EXCLUDED.{}').format(sql.Identifier(c),sql.Identifier(c)) for c in cols if c not in keys)
  db.execute(sql.SQL('INSERT INTO public.{} ({}) SELECT {} FROM {} WHERE ticker=%s AND {}=%s ON CONFLICT ({}) DO UPDATE SET {}').format(sql.Identifier(t),names,names,sql.Identifier(stage),sql.Identifier(dc),keysql,sets),(ticker,day))
  counts[f]=db.execute(sql.SQL('SELECT count(*) AS n FROM public.{} WHERE ticker=%s AND {}=%s').format(sql.Identifier(t),sql.Identifier(dc)),(ticker,day)).fetchone()['n']
  mismatch=db.execute(sql.SQL('SELECT count(*) AS n FROM ((SELECT {} FROM public.{} WHERE ticker=%s AND {}=%s EXCEPT SELECT {} FROM {} WHERE ticker=%s AND {}=%s) UNION ALL (SELECT {} FROM {} WHERE ticker=%s AND {}=%s EXCEPT SELECT {} FROM public.{} WHERE ticker=%s AND {}=%s)) x').format(names,sql.Identifier(t),sql.Identifier(dc),names,sql.Identifier(stage),sql.Identifier(dc),names,sql.Identifier(stage),sql.Identifier(dc),names,sql.Identifier(t),sql.Identifier(dc)),(ticker,day,ticker,day,ticker,day,ticker,day)).fetchone()['n']
  if mismatch:raise RuntimeError('Stored payload differs '+t)
 emit('upsert_verified',ticker=ticker,date=day,rows=counts,mismatches=0,output_dates=1)

def main():
 p=argparse.ArgumentParser();p.add_argument('--ticker',required=True);p.add_argument('--date',required=True,type=date.fromisoformat);p.add_argument('--apply',action='store_true');a=p.parse_args()
 with psycopg.connect(os.environ['DATABASE_URL'],row_factory=dict_row,application_name='index-feature356-one-date') as db:
  prepare(db,a.ticker,a.date)
  if a.apply:upsert_one_date(db,a.ticker,a.date)
  else:db.rollback()
 emit('complete',committed=a.apply,ticker=a.ticker,date=a.date,features=[3,5,6],output_dates=1)
if __name__=='__main__':main()
