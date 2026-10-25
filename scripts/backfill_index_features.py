#!/usr/bin/env python3
"""Approved INDEX-only historical bootstrap. Default rollback; no daily routing or source writes.

Reads monthly raw slices once, computes aggregate history once, validates accepted samples before
public writes, and applies idempotent year chunks. Temporary stages survive chunk commits.
"""
from __future__ import annotations
import argparse
import hashlib
import itertools
import json
import math
import os
import statistics
import sys
import time
import uuid
from datetime import date
from pathlib import Path

import pandas as pd
import psycopg
from psycopg import sql
from psycopg.rows import dict_row

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'features/feature04')]
from backfill_feature_02_v2 import INSERT_TICKER
from check_feature_06_sample import compute as reference6
from engine import calculate, COLUMNS as F4_COLUMNS
from upsert_index_broker_feature_sample import clone_writer

BASE={1:'Feature_01_Stock_Daily',2:'Feature_02_Broker_Rolling',3:'Feature_03_Stock_Broker_Daily',
4:'Feature_04_Technical_Indicator',5:'Feature_05_Foreign_Domestic_Broker_Detail',6:'Feature_06_Foreign_Domestic'}
COVER=('frequency_source_rows','buy_freq_known_rows','sell_freq_known_rows','buy_freq_missing_rows','sell_freq_missing_rows')
MIGRATION='database/migrations/20261025_001_index_feature05_remove_frequency_coverage.sql'

def emit(event,**kw):
    print(json.dumps(dict(event=event,**kw),default=str),flush=True)

def equal(a,b,tolerance=1e-7):
    if a is None or b is None:return a is None and b is None
    if isinstance(a,(str,date,bool)) or isinstance(b,(str,date,bool)):return a==b
    if not isinstance(a,float) and not isinstance(b,float):return a==b
    return math.isclose(float(a),float(b),rel_tol=tolerance,abs_tol=1e-7)

def cols(db,table,schema='public'):
    return [r['column_name'] for r in db.execute('SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position',(schema,table))]

def month_ranges(first,last):
    cur=date(first.year,first.month,1)
    while cur<=last:
        end=date(cur.year+cur.month//12,cur.month%12+1,1)
        yield max(first,cur),min(last.fromordinal(last.toordinal()+1),end)
        cur=end

def copy_rows(db,table,names,rows):
    with db.cursor().copy(sql.SQL('COPY {} ({}) FROM STDIN').format(sql.Identifier(table),sql.SQL(',').join(map(sql.Identifier,names)))) as cp:
        for r in rows:cp.write_row([r[c] for c in names])

def stage_raw(db,ticker,first,last):
    db.execute('CREATE TEMP TABLE bulk5 (LIKE public."Feature_05_Foreign_Domestic_Broker_Detail" INCLUDING ALL) ON COMMIT PRESERVE ROWS')
    db.execute('ALTER TABLE bulk5 '+','.join('ADD COLUMN '+c+' bigint NOT NULL DEFAULT 0' for c in COVER))
    manifest=[]
    for lo,hi in month_ranges(first,last):
        begun=time.monotonic()
        plan=db.execute('''EXPLAIN (FORMAT JSON) SELECT "Date","Broker","Investor Type","Market Board",SUM("Buy Value")
         FROM public."IDX_Broker_Summary" WHERE "Date">=%s AND "Date"<%s GROUP BY 1,2,3,4''',(lo,hi)).fetchone()
        if not manifest:emit('bounded_source_plan',month=lo,plan=plan)
        # Raw PK rows already have exact symbol/broker/investor/board grain. Window gap is
        # computed before symbol netting, so opposite source gaps cannot cancel invisibly.
        result=db.execute('''INSERT INTO bulk5
         WITH r AS (SELECT *,SUM("Buy Value") OVER w<>SUM("Sell Value") OVER w AS gap
          FROM public."IDX_Broker_Summary" WHERE "Date">=%s AND "Date"<%s
          WINDOW w AS (PARTITION BY "Date","Symbol","Market Board"))
         SELECT "Date",%s::text,"Broker"::text,"Market Board"::text,"Investor Type"::text,
          SUM("Buy Value"),SUM("Sell Value"),SUM("Buy Value"-"Sell Value"),
          SUM("Buy Lots"),SUM("Sell Lots"),SUM("Buy Lots"-"Sell Lots"),
          SUM(buy_freq)::bigint,SUM(sell_freq)::bigint,bool_or(gap),statement_timestamp(),
          COUNT(*),COUNT(buy_freq),COUNT(sell_freq),COUNT(*)-COUNT(buy_freq),COUNT(*)-COUNT(sell_freq)
         FROM r GROUP BY "Date","Broker","Market Board","Investor Type"''',(lo,hi,ticker))
        # Cross-check canonical monetary context without inheriting its stricter frequency rule.
        mismatch=db.execute('''WITH a AS (SELECT trade_date,broker,investor_type,market_board,
          SUM(buy_value) AS bv,SUM(sell_value) AS sv,SUM(buy_lots) AS bl,SUM(sell_lots) AS sl,bool_or(source_balance_gap) AS gap
          FROM public."Feature_05_Foreign_Domestic_Broker_Detail" f WHERE trade_date>=%s AND trade_date<%s
          AND NOT EXISTS(SELECT 1 FROM public."IDX_Stock_Universe" u WHERE u."Ticker"=f.ticker AND u."Security Type"='index') GROUP BY 1,2,3,4),
         b AS (SELECT trade_date,broker,investor_type,market_board,buy_value AS bv,sell_value AS sv,buy_lots AS bl,sell_lots AS sl,source_balance_gap AS gap FROM bulk5 WHERE trade_date>=%s AND trade_date<%s)
         SELECT count(*) AS n FROM ((SELECT * FROM a EXCEPT SELECT * FROM b) UNION ALL (SELECT * FROM b EXCEPT SELECT * FROM a))x''',(lo,hi,lo,hi)).fetchone()['n']
        if mismatch:raise RuntimeError(f'Raw/canonical monetary history mismatch {lo}: {mismatch}')
        info=db.execute('SELECT count(*) AS groups,SUM(frequency_source_rows) AS source_rows,SUM(buy_value) AS buy_value,SUM(sell_value) AS sell_value FROM bulk5 WHERE trade_date>=%s AND trade_date<%s',(lo,hi)).fetchone()
        manifest.append(dict(start=lo,end_exclusive=hi,**info))
        emit('raw_month_staged',start=lo,groups=result.rowcount,source_rows=info['source_rows'],seconds=round(time.monotonic()-begun,2))
    db.execute('ANALYZE bulk5')
    db.execute('CREATE TEMP TABLE index_market_calendar ON COMMIT PRESERVE ROWS AS SELECT DISTINCT trade_date AS date FROM bulk5')
    db.execute('CREATE UNIQUE INDEX ON index_market_calendar(date)')
    return manifest

def stage2(db,ticker):
    db.execute('''CREATE TEMP TABLE feature_02_v2_daily_base ON COMMIT PRESERVE ROWS AS
     SELECT trade_date AS date,ticker,broker,investor_type,market_board,buy_value,sell_value,buy_lots,sell_lots,net_value,net_lots FROM bulk5''')
    db.execute('CREATE UNIQUE INDEX ON feature_02_v2_daily_base(ticker,broker,investor_type,market_board,date)')
    db.execute('ANALYZE feature_02_v2_daily_base')
    statement=INSERT_TICKER.replace('INSERT INTO public."Feature_02_Broker_Rolling"','INSERT INTO calc2')
    statement=statement.replace('WHERE ticker = %s','WHERE ticker = %s AND broker=%s AND investor_type=%s AND market_board=%s')
    statement=statement.replace('FROM (SELECT DISTINCT date FROM daily) AS available','FROM index_market_calendar AS available')
    if 'INSERT INTO calc2' not in statement or 'FROM index_market_calendar AS available' not in statement:raise RuntimeError('F02 SQL contract changed')
    pairs=db.execute('SELECT DISTINCT broker,investor_type,market_board FROM feature_02_v2_daily_base ORDER BY 1,2,3').fetchall()
    for i,p in enumerate(pairs,1):
        db.execute(statement,(ticker,p['broker'],p['investor_type'],p['market_board']))
        if i%20==0 or i==len(pairs):emit('feature2_progress',pairs=i,total_pairs=len(pairs))
    db.execute('ANALYZE calc2')
    clone_writer(db,'public.refresh_feature_03_stock_broker_daily(date,text[])','bulk_compute3',{BASE[2]:'calc2',BASE[3]:'calc3'})
    db.execute('SELECT pg_temp.bulk_compute3(NULL,ARRAY[%s])',(ticker,))
    db.execute('UPDATE calc3 SET broker_concentration_hhi=NULL')

def stage6(db,ticker):
    legacy_cols=cols(db,BASE[5])
    names=sql.SQL(',').join(map(sql.Identifier,legacy_cols))
    db.execute(sql.SQL('INSERT INTO calc5 ({}) SELECT {} FROM bulk5').format(names,names))
    db.execute('CREATE TEMP TABLE strict5 (LIKE public."Feature_05_Foreign_Domestic_Broker_Detail" INCLUDING ALL) ON COMMIT PRESERVE ROWS')
    expressions=[sql.SQL('CASE WHEN {}=frequency_source_rows THEN {} END').format(sql.Identifier(side+'_freq_known_rows'),sql.Identifier(side+'_freq')) if c in ('buy_freq','sell_freq') and (side:=c.split('_')[0]) else sql.Identifier(c) for c in legacy_cols]
    db.execute(sql.SQL('INSERT INTO strict5 ({}) SELECT {} FROM bulk5').format(names,sql.SQL(',').join(expressions)))
    clone_writer(db,'public.refresh_feature_06(text,date)','bulk_compute6',{BASE[5]:'strict5',BASE[6]:'calc6'})
    db.execute('SELECT pg_temp.bulk_compute6(%s,NULL)',(ticker,))
    db.execute('''CREATE TEMP TABLE frequency_daily ON COMMIT PRESERVE ROWS AS SELECT trade_date,market_board,
     SUM(frequency_source_rows)::bigint AS frequency_source_rows,SUM(buy_freq_known_rows)::bigint AS buy_freq_known_rows,
     SUM(sell_freq_known_rows)::bigint AS sell_freq_known_rows,SUM(buy_freq_missing_rows)::bigint AS buy_freq_missing_rows,
     SUM(sell_freq_missing_rows)::bigint AS sell_freq_missing_rows,
     CASE WHEN COUNT(*) FILTER(WHERE investor_type='Foreign')=0 THEN 0 ELSE SUM(buy_freq) FILTER(WHERE investor_type='Foreign') END AS foreign_buy_freq_1d,
     CASE WHEN COUNT(*) FILTER(WHERE investor_type='Foreign')=0 THEN 0 ELSE SUM(sell_freq) FILTER(WHERE investor_type='Foreign') END AS foreign_sell_freq_1d,
     CASE WHEN COUNT(*) FILTER(WHERE investor_type='Domestic')=0 THEN 0 ELSE SUM(buy_freq) FILTER(WHERE investor_type='Domestic') END AS domestic_buy_freq_1d,
     CASE WHEN COUNT(*) FILTER(WHERE investor_type='Domestic')=0 THEN 0 ELSE SUM(sell_freq) FILTER(WHERE investor_type='Domestic') END AS domestic_sell_freq_1d
     FROM bulk5 GROUP BY trade_date,market_board''')
    db.execute('''CREATE TEMP TABLE frequency_masks ON COMMIT PRESERVE ROWS AS
     WITH dense AS (SELECT c.date AS trade_date,b.market_board,coalesce(f.buy_freq_missing_rows+f.sell_freq_missing_rows>0,false) AS bad
      FROM index_market_calendar c CROSS JOIN (SELECT DISTINCT market_board FROM bulk5)b
      LEFT JOIN frequency_daily f ON f.trade_date=c.date AND f.market_board=b.market_board)
     SELECT *,bool_or(bad) OVER(PARTITION BY market_board ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS bad20,
      bool_or(bad) OVER(PARTITION BY market_board ORDER BY trade_date ROWS BETWEEN 24 PRECEDING AND CURRENT ROW) AS bad25 FROM dense''')
    assignments=','.join(f'{c}=f.{c}' for c in COVER)+','+','.join(f'{c}=f.{c}' for c in ('foreign_buy_freq_1d','foreign_sell_freq_1d','domestic_buy_freq_1d','domestic_sell_freq_1d'))
    db.execute('UPDATE calc6 t SET '+assignments+' FROM frequency_daily f WHERE f.trade_date=t.trade_date AND f.market_board=t.market_board')
    primitive={'foreign_buy_freq_1d','foreign_sell_freq_1d','domestic_buy_freq_1d','domestic_sell_freq_1d'}
    frequency=[c for c in cols(db,BASE[6]) if ('freq' in c or 'ticket' in c) and c not in primitive]
    for c in frequency:
        mask='bad25' if 'vs_prev20d' in c else 'bad20' if '_20d' in c else 'bad'
        db.execute(sql.SQL('UPDATE calc6 t SET {}=NULL FROM frequency_masks m WHERE t.trade_date=m.trade_date AND t.market_board=m.market_board AND m.{}').format(sql.Identifier(c),sql.Identifier(mask)))
    return frequency

def stage_prices(db,ticker):
    db.execute('CREATE TEMP TABLE index_prices ON COMMIT PRESERVE ROWS AS SELECT * FROM public."Price_Stock_Indonesia_IDX" WHERE ticker=%s AND is_final AND timeframe=\'Daily\'',(ticker,))
    clone_writer(db,'public.refresh_feature_01_stock_daily(date,text[])','bulk_compute1',{BASE[1]:'calc1','Price_Stock_Indonesia_IDX':'index_prices'})
    db.execute('SELECT pg_temp.bulk_compute1(NULL,ARRAY[%s])',(ticker,))
    history=db.execute('''SELECT p.*, 'equity'::text AS asset_type,u."Security Type" AS security_type,
     u."TradingView Symbol" AS universe_tradingview_symbol FROM index_prices p JOIN public."IDX_Stock_Universe" u ON u."Ticker"=p.ticker ORDER BY p.date''').fetchall()
    result=calculate(history)
    for row in result:row['asset_type']='index'
    copy_rows(db,'calc4',F4_COLUMNS,result)
    return history

def validate2(db):
    calendar=[r['date'] for r in db.execute('SELECT date FROM index_market_calendar ORDER BY date')]
    sample_days={calendar[i] for i in (0,4,19,59,270,310,len(calendar)-1) if i<len(calendar)}
    sample_days.update(date(y,1,2) for y in range(calendar[0].year,calendar[-1].year+1))
    checks=0
    pairs=db.execute('SELECT DISTINCT broker,investor_type,market_board FROM feature_02_v2_daily_base ORDER BY 1,2,3').fetchall()
    for pair in pairs:
        params=(pair['broker'],pair['investor_type'],pair['market_board'])
        raw={r['date']:r for r in db.execute('SELECT * FROM feature_02_v2_daily_base WHERE broker=%s AND investor_type=%s AND market_board=%s',params)}
        for a in db.execute('SELECT * FROM calc2 WHERE broker=%s AND investor_type=%s AND market_board=%s AND date=ANY(%s)',(*params,list(sample_days))):
            days=[d for d in calendar if d<=a['date']];nv=[raw[d]['net_value'] if d in raw else 0 for d in days];nl=[raw[d]['net_lots'] if d in raw else 0 for d in days]
            act=[int(d in raw and any(raw[d][c]>0 for c in ('buy_value','sell_value','buy_lots','sell_lots'))) for d in days];e={}
            for n in (5,20,60):
                e[f'net_value_{n}d']=sum(nv[-n:]) if len(nv)>=n else None;e[f'net_lots_{n}d']=sum(nl[-n:]) if len(nl)>=n else None
            for n in (20,60):
                valid=len(nv)>=n;buy=sum(v>0 for v in nv[-n:]);sell=sum(v<0 for v in nv[-n:]);active=sum(act[-n:])
                for name,v in [('buy_days',buy),('sell_days',sell),('active_days',active),('stock_trading_days',n),('buy_day_ratio',buy/n),('buy_share_active_days',buy/active if active else None)]:e[f'{name}_{n}d']=v if valid else None
                h=[sum(nv[i-n+1:i+1]) for i in range(max(n-1,len(nv)-253),len(nv)-1)]
                if len(h)==252:
                    sd=statistics.stdev(map(float,h));cur=e[f'net_value_{n}d'];e[f'net_value_zscore_{n}d']=(float(cur)-statistics.mean(map(float,h)))/sd if sd else None
                    e[f'net_value_percentile_{n}d']=100*(sum(v<cur for v in h)+0.5*sum(v==cur for v in h))/252
                else:e[f'net_value_zscore_{n}d']=e[f'net_value_percentile_{n}d']=None
            pos=[v for v in nv[-20:] if v>0]
            e.update(positive_net_value_20d=sum(pos) if len(nv)>=20 else None,largest_buy_day_20d=max(pos) if pos and len(nv)>=20 else None,largest_buy_day_share_20d=float(max(pos))/float(sum(pos)) if pos and len(nv)>=20 else None)
            for c,v in e.items():
                if not equal(a[c],v):raise RuntimeError(f'F02 independent mismatch {params}/{a["date"]}/{c}: {a[c]} vs {v}')
                checks+=1
    emit('feature2_independent_validated',comparisons=checks,sampled_dates=len(sample_days))

def validate6(db,frequency):
    rows=db.execute('SELECT trade_date,market_board,investor_type,SUM(buy_value) AS buy_value,SUM(sell_value) AS sell_value,SUM(buy_lots) AS buy_lots,SUM(sell_lots) AS sell_lots,SUM(buy_freq) AS buy_freq,SUM(sell_freq) AS sell_freq,bool_or(source_balance_gap) AS source_balance_gap FROM strict5 GROUP BY 1,2,3').fetchall()
    expected=reference6(pd.DataFrame(rows));expected=expected.set_index(['trade_date','market_board'])
    masks={(r['trade_date'],r['market_board']):r for r in db.execute('SELECT * FROM frequency_masks')}
    daily={(r['trade_date'],r['market_board']):r for r in db.execute('SELECT * FROM frequency_daily')}
    checks=0
    for actual in db.execute('SELECT * FROM calc6 ORDER BY trade_date,market_board'):
        key=(actual['trade_date'],actual['market_board']);row=expected.loc[key];mask=masks[key]
        for c in expected.columns:
            value=row[c]
            if pd.isna(value):value=None
            if c in frequency and mask['bad25' if 'vs_prev20d' in c else 'bad20' if '_20d' in c else 'bad']:value=None
            if c in ('foreign_buy_freq_1d','foreign_sell_freq_1d','domestic_buy_freq_1d','domestic_sell_freq_1d'):value=daily[key][c]
            if not equal(actual[c],value,1e-6):raise RuntimeError(f'F06 independent mismatch {key}/{c}: {actual[c]} vs {value}')
            checks+=1
    emit('feature6_independent_validated',comparisons=checks,rows=len(expected))

def validate3(db):
    stored={(r['date'],r['market_board']):r for r in db.execute('SELECT * FROM calc3')};checks=0
    with db.cursor(name='independent_broker_rank_reference',row_factory=dict_row) as cur:
        cur.execute('''SELECT trade_date,market_board,b.broker,SUM(net_value) AS net,SUM(buy_value) AS buy,
         SUM(sell_value) AS sell,bool_or(buy_value<>0 OR sell_value<>0 OR buy_lots<>0 OR sell_lots<>0) AS active,
         coalesce(SUM(net_value) FILTER(WHERE investor_type='Foreign'),0) AS foreign_net,
         coalesce(SUM(net_value) FILTER(WHERE investor_type='Domestic'),0) AS domestic_net,p.broker_classification AS classification
         FROM bulk5 b LEFT JOIN public."IDX_Broker_Profile" p ON p.broker_code=b.broker
         GROUP BY trade_date,market_board,b.broker,p.broker_classification ORDER BY trade_date,market_board,b.broker''')
        groups=0
        for key,it in itertools.groupby(cur,lambda r:(r['trade_date'],r['market_board'])):
            entries=list(it);buyers=sorted([r for r in entries if r['net']>0],key=lambda r:(-r['net'],r['broker']));sellers=sorted([r for r in entries if r['net']<0],key=lambda r:(r['net'],r['broker']))
            active=sum(r['active'] for r in entries);positive=sum(r['net'] for r in buyers);top3=sum(r['net'] for r in buyers[:3])
            e=dict(total_buy_value=sum(r['buy'] for r in entries),total_sell_value=sum(r['sell'] for r in entries),active_broker_count=active,net_buy_broker_count=len(buyers),net_sell_broker_count=len(sellers),net_buy_broker_ratio=len(buyers)/active if active else None,
             foreign_net_value=sum(r['foreign_net'] for r in entries),domestic_net_value=sum(r['domestic_net'] for r in entries),top_buyer=buyers[0]['broker'] if buyers else None,top_buyer_net_value=buyers[0]['net'] if buyers else None,
             top_seller=sellers[0]['broker'] if sellers else None,top_seller_net_value=sellers[0]['net'] if sellers else None,top3_buyer_net_value=top3,positive_net_value_total=positive,top3_buyer_share=float(top3)/float(positive) if positive else None,broker_concentration_hhi=None)
            for c,kind in [('institutional','Institutional-heavy'),('retail','Retail-heavy'),('mixed','Mixed'),('niche','Niche')]:e[c+'_net_value']=sum(r['net'] for r in entries if r['classification']==kind)
            for c,v in e.items():
                if not equal(stored[key][c],v):raise RuntimeError(f'F03 independent mismatch {key}/{c}')
                checks+=1
            groups+=1
        if groups!=len(stored):raise RuntimeError('F03 source/output key coverage mismatch')
    emit('feature3_independent_validated',comparisons=checks,rows=groups)

def compare_sample(db,ticker,day,features=None):
    total=0
    for f,base in BASE.items():
        if features is not None and f not in features:continue
        dc='date' if f in (1,2,3) else 'trade_date';target=base+'_INDEX'
        names=[c for c in cols(db,target) if c not in COVER and c!='calculated_at']
        keys=['broker','investor_type','market_board'] if f in (2,5) else ['market_board'] if f in (3,6) else ['ticker']
        staged={tuple(r[c] for c in keys):r for r in db.execute(sql.SQL('SELECT * FROM {} WHERE {}=%s').format(sql.Identifier('calc'+str(f)),sql.Identifier(dc)),(day,))}
        stored=db.execute(sql.SQL('SELECT * FROM public.{} WHERE ticker=%s AND {}=%s').format(sql.Identifier(target),sql.Identifier(dc)),(ticker,day)).fetchall()
        if not stored or len(stored)!=len(staged):raise RuntimeError(f'Sample key mismatch F{f}')
        for a in stored:
            b=staged[tuple(a[c] for c in keys)]
            for c in names:
                if not equal(a[c],b[c],1e-6):raise RuntimeError(f'Accepted sample drift F{f}/{c}: {a[c]} vs {b[c]}')
                total+=1
    emit('accepted_sample_validated',date=day,comparisons=total)

def prepare(db,ticker,sample,smoke=False):
    u=db.execute('SELECT "Security Type" AS kind FROM public."IDX_Stock_Universe" WHERE "Ticker"=%s',(ticker,)).fetchone()
    if not u or u['kind']!='index':raise ValueError('Target is not a universe-classified index')
    if db.execute('SELECT 1 FROM public."Universe_Fixed_income" WHERE ticker=%s',(ticker,)).fetchone():raise ValueError('Ambiguous index/bond identity')
    bounds=db.execute('SELECT MIN("Date") AS first,MAX("Date") AS last FROM public."IDX_Broker_Summary"').fetchone()
    for f,base in BASE.items():
        db.execute(sql.SQL('CREATE TEMP TABLE {} (LIKE public.{} INCLUDING ALL) ON COMMIT PRESERVE ROWS').format(sql.Identifier('calc'+str(f)),sql.Identifier(base+'_INDEX' if f==4 else base)))
    for c in COVER:db.execute(sql.SQL('ALTER TABLE calc6 ADD COLUMN {} bigint NOT NULL DEFAULT 0').format(sql.Identifier(c)))
    manifest=stage_raw(db,ticker,sample if smoke else bounds['first'],sample if smoke else bounds['last'])
    if smoke:
        # Integration fixture only, session-local and always rolled back: exercises complete
        # 252+60-session warmups without another full historical raw scan.
        db.execute('CREATE TEMP TABLE fixture_seed ON COMMIT PRESERVE ROWS AS SELECT * FROM bulk5 WHERE broker IN (SELECT broker FROM bulk5 GROUP BY broker ORDER BY COUNT(*) DESC,broker LIMIT 6)')
        db.execute('TRUNCATE bulk5,index_market_calendar')
        db.execute('''INSERT INTO bulk5 SELECT %s::date-(329-g),ticker,broker,market_board,investor_type,
         buy_value*(1+g%%13),sell_value*(1+g%%13),net_value*(1+g%%13),buy_lots*(1+g%%13),sell_lots*(1+g%%13),net_lots*(1+g%%13),
         buy_freq,sell_freq,source_balance_gap,calculated_at,frequency_source_rows,buy_freq_known_rows,sell_freq_known_rows,buy_freq_missing_rows,sell_freq_missing_rows
         FROM fixture_seed CROSS JOIN generate_series(0,329)g''',(sample,))
        db.execute('INSERT INTO index_market_calendar SELECT DISTINCT trade_date FROM bulk5')
        db.execute('ANALYZE bulk5');emit('smoke_fixture_ready',sessions=330,public_writes=False)
    stage2(db,ticker);freq=stage6(db,ticker);history=stage_prices(db,ticker)
    validate2(db);validate3(db);validate6(db,freq);compare_sample(db,ticker,sample,{1,4} if smoke else None)
    emit('dry_run_validated',ticker=ticker,broker_range=bounds,price_rows=len(history),manifest=manifest)
    return manifest

def archive_and_migrate(db,ticker,snapshot):
    for base in BASE.values():
        target=base+'_INDEX'
        existing=db.execute('SELECT count(*) AS n FROM migration_archive.index_feature_rows WHERE snapshot_id=%s AND source_table=%s',(snapshot,target)).fetchone()['n']
        if existing:
            bad=db.execute('SELECT count(*) AS n FROM migration_archive.index_feature_rows WHERE snapshot_id=%s AND source_table=%s AND row_hash<>md5(row_data::text)',(snapshot,target)).fetchone()['n']
            if bad:raise RuntimeError('Existing pre-bulk archive hash mismatch')
            emit('original_snapshot_preserved',table=target,rows=existing)
            continue
        db.execute(sql.SQL('INSERT INTO migration_archive.index_feature_rows(snapshot_id,source_table,row_hash,row_data) SELECT %s,%s,md5(to_jsonb(t)::text),to_jsonb(t) FROM public.{} t WHERE ticker=%s ON CONFLICT DO NOTHING').format(sql.Identifier(target)),(snapshot,target,ticker))
        bad=db.execute(sql.SQL('SELECT count(*) AS n FROM public.{} t WHERE ticker=%s AND NOT EXISTS(SELECT 1 FROM migration_archive.index_feature_rows a WHERE a.snapshot_id=%s AND a.source_table=%s AND a.row_hash=md5(to_jsonb(t)::text) AND a.row_data=to_jsonb(t))').format(sql.Identifier(target)),(ticker,snapshot,target)).fetchone()['n']
        if bad:raise RuntimeError('INDEX sample archival verification failed')
    db.execute((ROOT/MIGRATION).read_text(),prepare=False)
    emit('schema_cleanup_verified',snapshot_id=snapshot,feature5_columns=len(cols(db,BASE[5]+'_INDEX')))

def apply_chunks(db,ticker,snapshot):
    summary={}
    for f,base in BASE.items():
        target=base+'_INDEX';stage='calc'+str(f);dc='date' if f in (1,2,3) else 'trade_date'
        names=cols(db,target);ident=sql.SQL(',').join(map(sql.Identifier,names));analytical=[c for c in names if c!='calculated_at']
        keys=['ticker',dc]+(['broker','investor_type','market_board'] if f in (2,5) else ['market_board'] if f in (3,6) else ['timeframe','asset_type'] if f==4 else [])
        assignments=sql.SQL(',').join(sql.SQL('{}=EXCLUDED.{}').format(sql.Identifier(c),sql.Identifier(c)) for c in names if c not in keys)
        before=sql.SQL(',').join(sql.SQL('t.{}').format(sql.Identifier(c)) for c in analytical)
        after=sql.SQL(',').join(sql.SQL('EXCLUDED.{}').format(sql.Identifier(c)) for c in analytical)
        command=sql.SQL('INSERT INTO public.{} AS t ({}) SELECT {} FROM {} WHERE ticker=%s AND {}>=%s AND {}<%s ON CONFLICT ({}) DO UPDATE SET {} WHERE ROW({}) IS DISTINCT FROM ROW({})').format(sql.Identifier(target),ident,ident,sql.Identifier(stage),sql.Identifier(dc),sql.Identifier(dc),sql.SQL(',').join(map(sql.Identifier,keys)),assignments,before,after)
        years=[r['y'] for r in db.execute(sql.SQL('SELECT DISTINCT EXTRACT(YEAR FROM {})::int AS y FROM {} ORDER BY y').format(sql.Identifier(dc),sql.Identifier(stage)))]
        for y in years:
            lo,hi=date(y,1,1),date(y+1,1,1)
            with db.transaction():
                written=db.execute(command,(ticker,lo,hi)).rowcount
                rerun=db.execute(command,(ticker,lo,hi)).rowcount
                if rerun:raise RuntimeError('Idempotent rerun modified rows')
                projection=sql.SQL(',').join(map(sql.Identifier,analytical))
                check=sql.SQL('SELECT count(*) AS n FROM ((SELECT {} FROM public.{} WHERE ticker=%s AND {}>=%s AND {}<%s EXCEPT SELECT {} FROM {} WHERE ticker=%s AND {}>=%s AND {}<%s) UNION ALL (SELECT {} FROM {} WHERE ticker=%s AND {}>=%s AND {}<%s EXCEPT SELECT {} FROM public.{} WHERE ticker=%s AND {}>=%s AND {}<%s))x').format(projection,sql.Identifier(target),sql.Identifier(dc),sql.Identifier(dc),projection,sql.Identifier(stage),sql.Identifier(dc),sql.Identifier(dc),projection,sql.Identifier(stage),sql.Identifier(dc),sql.Identifier(dc),projection,sql.Identifier(target),sql.Identifier(dc),sql.Identifier(dc))
                bad=db.execute(check,(ticker,lo,hi)*4).fetchone()['n']
                if bad:raise RuntimeError(f'Post-write payload mismatch F{f}/{y}')
                fingerprint=db.execute(sql.SQL("SELECT count(*) AS rows,md5(string_agg(md5((to_jsonb(s)-'calculated_at')::text),'' ORDER BY {})) AS hash FROM {} s WHERE ticker=%s AND {}>=%s AND {}<%s").format(sql.SQL(',').join(map(sql.Identifier,keys)),sql.Identifier(stage),sql.Identifier(dc),sql.Identifier(dc)),(ticker,lo,hi)).fetchone()
            emit('chunk_committed',feature=f,year=y,written=written,rerun_modified=rerun,mismatches=bad,**fingerprint)
        summary[f]=db.execute(sql.SQL('SELECT count(*) AS rows,MIN({}) AS first,MAX({}) AS last FROM public.{} WHERE ticker=%s').format(sql.Identifier(dc),sql.Identifier(dc),sql.Identifier(target)),(ticker,)).fetchone()
    with db.transaction():
        targets=[b+'_INDEX' for b in BASE.values()]
        db.execute('''UPDATE public."Table_Catalog" SET update_rule='Explicit validated INDEX historical bootstrap; automatic daily routing is not enabled.',
         source_code_paths=CASE WHEN 'scripts/backfill_index_features.py'=ANY(source_code_paths) THEN source_code_paths ELSE array_append(source_code_paths,'scripts/backfill_index_features.py') END,
         availability_rule='Validated loaded INDEX dates only; independent price and broker source endpoints. All-raw-symbol broker scope, not official historical constituents.'
         WHERE table_schema='public' AND table_name=ANY(%s)''',(targets,))
        db.execute('''UPDATE public."Feature_Catalog" SET refresh_trigger='Approved manual INDEX historical bootstrap; no automatic daily update.',
         availability_rule='Use only loaded INDEX output dates; price/broker histories have independent endpoints.',
         validation_evidence=CASE WHEN 'verification/ihsg_feature_aggregation/bulk/'=ANY(validation_evidence) THEN validation_evidence ELSE array_append(validation_evidence,'verification/ihsg_feature_aggregation/bulk/') END WHERE is_active AND feature_table=ANY(%s)''',(targets,))
    emit('bulk_complete',snapshot_id=snapshot,ticker=ticker,summary=summary,daily_updates_enabled=False)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--ticker',required=True);p.add_argument('--sample-date',type=date.fromisoformat,required=True);p.add_argument('--snapshot-id',type=uuid.UUID,required=True);p.add_argument('--apply',action='store_true');p.add_argument('--smoke',action='store_true');a=p.parse_args()
    if a.smoke and a.apply:p.error('--smoke is rollback-only and cannot be combined with --apply')
    with psycopg.connect(os.environ['DATABASE_URL'],row_factory=dict_row,autocommit=True,application_name='index-features-approved-bootstrap') as db:
        db.execute("SET statement_timeout='20min'");db.execute("SET lock_timeout='10s'");db.execute("SET work_mem='64MB'");db.execute('SET max_parallel_workers_per_gather=0')
        if not db.execute('SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS ok',('index-bulk:'+a.ticker,)).fetchone()['ok']:raise RuntimeError('Another INDEX writer is active')
        with db.transaction():
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            prepare(db,a.ticker,a.sample_date,a.smoke)
            if not a.apply:
                raise psycopg.Rollback()
        if not a.apply:
            emit('complete',committed=False);return
        with db.transaction():archive_and_migrate(db,a.ticker,a.snapshot_id)
        apply_chunks(db,a.ticker,a.snapshot_id)

if __name__=='__main__':main()
