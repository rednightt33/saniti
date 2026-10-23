#!/usr/bin/env python3
"""Validate and optionally insert one universe ticker's closed Daily TradingView history.

Defaults to preflight. ACTION=apply additionally requires the preflight fingerprint.
Existing price rows are never overwritten; standard database enqueue triggers remain on.
"""
from __future__ import annotations
import hashlib
import base64
import gzip
import json
import os
from pathlib import Path
import sys
from datetime import date, datetime, timedelta, timezone
import time

import psycopg
from psycopg import sql

if os.environ.get('PRICE_MODULE_GZIP'):
    module_dir=Path('/tmp/idx-history-helper');module_dir.mkdir(exist_ok=True)
    (module_dir/'price_update.py').write_text(gzip.decompress(base64.b64decode(os.environ['PRICE_MODULE_GZIP'])).decode())
    sys.path.insert(0,str(module_dir))
else:
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'apps/idx-price-cron'))
import price_update as price

def emit(event,**fields):
    print(json.dumps({'event':event,**fields},default=str),flush=True)

def fetch_index_ohlc(ws,session,symbol,bars,query_date):
    """Read provider OHLC points without inventing an absent volume observation."""
    alias='history_index_symbol';series='history_index_series'
    definition='='+json.dumps({'symbol':symbol.tradingview_symbol,'adjustment':'none','session':'regular'},separators=(',',':'))
    ws.send(price.frame('resolve_symbol',[session,alias,definition]))
    ws.send(price.frame('create_series',[session,series,series,alias,'1D',bars]))
    rows={};deadline=time.monotonic()+90;completed=False
    while time.monotonic()<deadline and not completed:
        ws.settimeout(max(0.2,min(5,deadline-time.monotonic())))
        try:raw=ws.recv()
        except (price.WebSocketTimeoutException,price.socket.timeout):continue
        objects,heartbeats=price.parse_frames(raw)
        for beat in heartbeats:ws.send(beat)
        for obj in objects:
            method=obj.get('m');params=obj.get('p',[])
            if method=='timescale_update' and len(params)>1:
                for point in params[1].get(series,{}).get('s',[]):
                    v=point.get('v',[])
                    if len(v)<5 or not isinstance(v[0],(int,float)):continue
                    timestamp=int(v[0]);source_time=datetime.fromtimestamp(timestamp,timezone.utc)
                    rows[timestamp]={'company_name':symbol.company_name,'ticker':symbol.ticker,'tradingview_symbol':symbol.tradingview_symbol,'date':source_time.astimezone(price.JAKARTA).date(),'open':v[1],'high':v[2],'low':v[3],'close':v[4],'volume':v[5] if len(v)>5 else None,'source':'TradingView','query_date':query_date,'timeframe':price.PRICE_TIMEFRAME,'source_bar_time':source_time}
            elif method=='series_completed' and series in params:completed=True
            elif method in ('critical_error','series_error','symbol_error'):raise RuntimeError('Provider error: '+json.dumps(params))
    if not completed:raise TimeoutError('Index OHLC history timeout')
    return [rows[k] for k in sorted(rows)]

def validate_ohlc(row):
    for k in ('open','high','low','close'):row[k]=price.as_decimal(row[k],k)
    if not row['low']<=row['open']<=row['high'] or not row['low']<=row['close']<=row['high']:raise ValueError('Invalid OHLC')
    if row['volume'] is not None:row['volume']=price.as_decimal(row['volume'],'volume')
    return row

def main():
    ticker=os.environ['TICKER'].strip().upper()
    start=date.fromisoformat(os.environ['START_DATE'])
    end=date.fromisoformat(os.environ['END_DATE'])
    if start>end:raise ValueError('Invalid date bounds')
    with psycopg.connect(os.environ['DATABASE_URL'],autocommit=True,application_name='idx-single-ticker-history') as db:
        with db.transaction():
            db.execute('SET TRANSACTION READ ONLY')
            identity=db.execute('SELECT "Company Name","Ticker","TradingView Symbol","Exchange","Security Type" FROM public."IDX_Stock_Universe" WHERE "Ticker"=%s',(ticker,)).fetchone()
            if not identity:raise ValueError('Ticker absent from IDX_Stock_Universe')
            symbol=price.Symbol(1,*identity)
            schedule=price.read_market_schedule(db)
            now=datetime.now(timezone.utc)
            if end>price.latest_completed_session(schedule,now):raise ValueError('End date is not final yet')
            baseline={r[0] for r in db.execute('SELECT date FROM public."Price_Stock_Indonesia_IDX" WHERE ticker=%s AND timeframe=%s AND date BETWEEN %s AND %s',('BBCA','Daily',start,end))}
            if not baseline or min(baseline)!=start or max(baseline)!=end:raise ValueError('BBCA baseline missing requested endpoints')
        ws=price.open_socket(90,True)
        try:
            session=price.start_chart_session(ws)
            fetched=(fetch_index_ohlc(ws,session,symbol,int(os.environ.get('REQUEST_BARS','5000')),now.astimezone(price.JAKARTA).date()) if symbol.asset_type=='index' else price.request_symbol(ws,session,symbol,int(os.environ.get('REQUEST_BARS','5000')),90,now.astimezone(price.JAKARTA).date()))
        finally:ws.close()
        selected=[validate_ohlc(r) for r in fetched if start<=r['date']<=end]
        selected.sort(key=lambda r:r['date'])
        dates={r['date'] for r in selected}
        if len(dates)!=len(selected):raise ValueError('Duplicate provider dates')
        missing=sorted(baseline-dates);extra=sorted(dates-baseline)
        fingerprint=hashlib.sha256(json.dumps([[str(r[k]) for k in ['date','open','high','low','close','volume','source_bar_time']] for r in selected],separators=(',',':')).encode()).hexdigest()
        emit('history_preflight',ticker=ticker,provider=symbol.tradingview_symbol,requested_from=start,requested_to=end,provider_bars=len(fetched),selected_rows=len(selected),first=min(dates) if dates else None,last=max(dates) if dates else None,bbca_dates=len(baseline),missing_vs_bbca=missing,extra_vs_bbca=extra,zero_volume_rows=sum(r['volume']==0 for r in selected),missing_volume_rows=sum(r['volume'] is None for r in selected),fingerprint=fingerprint,first_candle=selected[0] if selected else None,last_candle=selected[-1] if selected else None)
        if missing or extra:raise ValueError('Provider and BBCA date sets differ; no write performed')
        if os.environ.get('ACTION','preflight')!='apply':
            emit('preflight_only',database_changes=0);return
        if any(r['volume'] is None for r in selected):raise ValueError('Source volume absent; current table requires volume. Apply blocked pending an approved missing-volume policy')
        if os.environ.get('EXPECTED_FINGERPRINT')!=fingerprint:raise ValueError('Source fingerprint differs from approved preflight; no write performed')
        finalized=datetime.now(timezone.utc)
        for row in selected:
            close_at=price.market_close_at(schedule,row['date'])
            if finalized<close_at+timedelta(minutes=schedule.finality_delay_minutes):raise ValueError('Non-final source candle')
            row.update(market_code=schedule.market_code,market_close_at=close_at,is_final=True,finalized_at=finalized)
        with db.transaction():
            db.execute("SET LOCAL statement_timeout='120s'")
            db.execute("SET LOCAL lock_timeout='5s'")
            if not db.execute('SELECT pg_try_advisory_xact_lock(hashtext(%s))',(price.RUN_LOCK_KEY,)).fetchone()[0]:raise RuntimeError('Daily/recovery ingest currently holds price lock')
            db.execute('CREATE TEMP TABLE idx_history_stage (LIKE public."Price_Stock_Indonesia_IDX" INCLUDING DEFAULTS) ON COMMIT DROP')
            cols=sql.SQL(',').join(map(sql.Identifier,price.PRICE_COLUMNS))
            with db.cursor() as cur:
                with cur.copy(sql.SQL('COPY idx_history_stage ({}) FROM STDIN').format(cols)) as copy:
                    for row in selected:copy.write_row(tuple(row[c] for c in price.PRICE_COLUMNS))
                cur.execute(sql.SQL('INSERT INTO public."Price_Stock_Indonesia_IDX" ({},ingestion_time) SELECT {},statement_timestamp() FROM idx_history_stage ON CONFLICT(ticker,date) DO NOTHING').format(cols,cols))
                inserted=cur.rowcount
            mismatches=db.execute('''SELECT count(*) FROM idx_history_stage s LEFT JOIN public."Price_Stock_Indonesia_IDX" p USING(ticker,date) WHERE p.ticker IS NULL OR ROW(p.open,p.high,p.low,p.close,p.volume,p.tradingview_symbol,p.source,p.timeframe,p.source_bar_time,p.is_final,p.market_close_at) IS DISTINCT FROM ROW(s.open,s.high,s.low,s.close,s.volume,s.tradingview_symbol,s.source,s.timeframe,s.source_bar_time,s.is_final,s.market_close_at)''').fetchone()[0]
            if mismatches:raise RuntimeError(f'{mismatches} stored/source mismatches; transaction rolled back')
            stored=db.execute('SELECT count(*),min(date),max(date) FROM public."Price_Stock_Indonesia_IDX" WHERE ticker=%s AND date BETWEEN %s AND %s',(ticker,start,end)).fetchone()
            if stored[0]!=len(selected):raise RuntimeError('Unexpected stored row count; transaction rolled back')
        emit('history_committed',ticker=ticker,inserted_rows=inserted,preserved_existing_rows=len(selected)-inserted,stored_rows=stored[0],first=stored[1],last=stored[2],mismatches=mismatches,fingerprint=fingerprint)

if __name__=='__main__':main()
