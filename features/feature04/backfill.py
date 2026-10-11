"""Explicit scoped/all-source backfill, serial and resumable, with atomic ticker commits.

This separate command leaves the bounded refresh CLI's range/ticker limits intact.
Default dry-run. --tickers OR --all-source-tickers, --run-id and --manifest required.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from uuid import UUID
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from engine import COLUMNS, TABLE, VERSION, calculate

SOURCE_QUERY='''SELECT ticker,date,open,high,low,close,volume,timeframe,
 tradingview_symbol,source,query_date,ingestion_time
 FROM public."Price_Stock_Indonesia_IDX" WHERE ticker=%s ORDER BY date'''
TARGET_QUERY='''SELECT * FROM public."Feature04_Technical_Indicator"
 WHERE ticker=%s ORDER BY trade_date,timeframe'''
PAYLOAD=tuple(c for c in COLUMNS if c!='calculated_at')

def digest(rows, *, output=False):
    data=[{c:r[c] for c in PAYLOAD} for r in rows] if output else rows
    return hashlib.sha256(json.dumps(data,sort_keys=True,default=str,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def verify_values(stored, expected):
    if len(stored)!=len(expected):
        raise ValueError('Ticker source/target row-count mismatch')
    for got,want in zip(stored,expected):
        if any(got[c]!=want[c] for c in PAYLOAD):
            raise ValueError('Stored ticker payload differs from calculation')
    return digest(stored,output=True)

def bulk_upsert(connection, rows):
    if not rows or len(rows)>5000:
        raise ValueError('One nonempty ticker with at most 5000 observations per transaction')
    if len({r['ticker'] for r in rows})!=1:
        raise ValueError('Serial backfill requires exactly one ticker per transaction')
    connection.execute(sql.SQL('CREATE TEMP TABLE feature04_stage (LIKE public.{}) ON COMMIT DROP').format(sql.Identifier(TABLE)))
    columns=sql.SQL(',').join(map(sql.Identifier,COLUMNS))
    with connection.cursor().copy(sql.SQL('COPY feature04_stage ({}) FROM STDIN').format(columns)) as copy:
        for row in rows:
            copy.write_row([row[c] for c in COLUMNS])
    nonkey=COLUMNS[3:]
    payload=tuple(c for c in nonkey if c!='calculated_at')
    statement=sql.SQL('''INSERT INTO public.{} AS target ({})
     SELECT {} FROM feature04_stage ORDER BY trade_date
     ON CONFLICT(ticker,trade_date,timeframe) DO UPDATE SET {}
     WHERE ROW({}) IS DISTINCT FROM ROW({})''').format(
        sql.Identifier(TABLE),columns,columns,
        sql.SQL(',').join(sql.SQL('{}=EXCLUDED.{}').format(sql.Identifier(c),sql.Identifier(c)) for c in nonkey),
        sql.SQL(',').join(sql.SQL('target.{}').format(sql.Identifier(c)) for c in payload),
        sql.SQL(',').join(sql.SQL('EXCLUDED.{}').format(sql.Identifier(c)) for c in payload))
    return connection.execute(statement).rowcount

def process_ticker(connection, ticker, run_id, *, write=False):
    started=datetime.now(timezone.utc)
    with connection.transaction():
        connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        if write:
            locked=connection.execute("SELECT pg_try_advisory_xact_lock(hashtextextended('Feature04_Technical_Indicator',0)) AS locked").fetchone()['locked']
            if not locked:
                raise RuntimeError('Another Feature04 writer holds the advisory lock')
        else:
            connection.execute('SET TRANSACTION READ ONLY')
        history=connection.execute(SOURCE_QUERY,(ticker,)).fetchall()
        if not history or len(history)>5000:
            raise ValueError('Ticker history must contain 1–5000 observations')
        expected=calculate(history)
        source_sha=digest(history)
        output_sha=digest(expected,output=True)
        previous=connection.execute('''SELECT * FROM public.feature04_backfill_log
         WHERE run_id=%s AND ticker=%s''',(run_id,ticker)).fetchone()
        existing=connection.execute(TARGET_QUERY,(ticker,)).fetchall()
        if previous and previous['status']=='COMPLETED' and previous['calculation_version']==VERSION and previous['source_sha256']==source_sha:
            # Resume trusts neither a stale log nor a target that was changed elsewhere.
            actual_sha=verify_values(existing,expected)
            if actual_sha!=previous['output_sha256']:
                raise ValueError('Completed log output hash does not match target')
            return {'ticker':ticker,'status':'SKIPPED_VERIFIED','rows':len(expected),'changed_rows':0}
        changed=0
        if write:
            changed=bulk_upsert(connection,expected)
            stored=connection.execute(TARGET_QUERY,(ticker,)).fetchall()
            if verify_values(stored,expected)!=output_sha:
                raise RuntimeError('Stored output hash differs from computed payload')
            # The writer cannot affect source rows; verify the snapshot fingerprint again.
            if digest(connection.execute(SOURCE_QUERY,(ticker,)).fetchall())!=source_sha:
                raise RuntimeError('Source snapshot changed during ticker transaction')
            connection.execute('''INSERT INTO public.feature04_backfill_log
             (run_id,ticker,source_start,source_end,source_rows,source_sha256,output_sha256,
              calculation_version,status,changed_rows,started_at,finished_at,detail)
             VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'COMPLETED',%s,%s,%s,%s)
             ON CONFLICT(run_id,ticker) DO UPDATE SET source_start=EXCLUDED.source_start,
             source_end=EXCLUDED.source_end,source_rows=EXCLUDED.source_rows,
             source_sha256=EXCLUDED.source_sha256,output_sha256=EXCLUDED.output_sha256,
             calculation_version=EXCLUDED.calculation_version,status=EXCLUDED.status,
             changed_rows=EXCLUDED.changed_rows,started_at=EXCLUDED.started_at,
             finished_at=EXCLUDED.finished_at,detail=EXCLUDED.detail''',
             (run_id,ticker,history[0]['date'],history[-1]['date'],len(history),source_sha,output_sha,
              VERSION,changed,started,datetime.now(timezone.utc),
              'All stored payload columns verified; chronological full-history replay; no source write.'))
        return {'ticker':ticker,'status':'COMPLETED' if write else 'DRY_RUN',
                'rows':len(expected),'changed_rows':changed,
                'source_start':str(history[0]['date']),'source_end':str(history[-1]['date'])}

def write_manifest(path, manifest):
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(manifest,indent=2)+'\n')
    temporary.replace(path)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    scope=parser.add_mutually_exclusive_group(required=True)
    scope.add_argument('--all-source-tickers',action='store_true')
    scope.add_argument('--tickers',nargs='+',help='Explicit source ticker codes, without .JK')
    parser.add_argument('--run-id',type=UUID,required=True)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--write',action='store_true')
    args=parser.parse_args()
    if args.tickers and (len(args.tickers)>10 or len(set(args.tickers))!=len(args.tickers)
                         or any(not t or t!=t.strip().upper() or t.endswith('.JK') for t in args.tickers)):
        parser.error('--tickers requires 1–10 distinct canonical source codes without .JK')
    beginning=monotonic()
    manifest={'run_id':str(args.run_id),'calculation_version':VERSION,
              'mode':'WRITE' if args.write else 'DRY_RUN','status':'RUNNING',
              'completed_tickers':0,'skipped_verified_tickers':0,'failed_tickers':0,
              'processed_rows':0,'changed_rows':0,'last_ticker':None,
              'started_at':datetime.now(timezone.utc).isoformat(),
              'tradingview_parity':'NOT VERIFIED','training_point_in_time_eligibility':'NOT VERIFIED'}
    try:
        with psycopg.connect(os.environ['DATABASE_URL'],autocommit=True,row_factory=dict_row,
                             options='-c statement_timeout=60000 -c lock_timeout=5000') as connection:
            # Freeze the actual source universe for this invocation; do not use current IDX membership.
            statement='''SELECT ticker,count(*) AS rows,min(date) AS first_date,max(date) AS last_date
             FROM public."Price_Stock_Indonesia_IDX"'''
            if args.tickers:
                statement+=' WHERE ticker=ANY(%s)'
            universe=connection.execute(statement+' GROUP BY ticker ORDER BY ticker',
                                        (args.tickers,) if args.tickers else ()).fetchall()
            if args.tickers and set(args.tickers)!={r['ticker'] for r in universe}:
                raise ValueError('At least one requested ticker has no source history')
            manifest.update(total_tickers=len(universe),expected_rows=sum(r['rows'] for r in universe))
            write_manifest(args.manifest,manifest)
            for item in universe:
                ticker=item['ticker']
                try:
                    result=process_ticker(connection,ticker,args.run_id,write=args.write)
                except Exception as error:
                    # Stop on the first failed ticker; earlier commits remain resumable.
                    if args.write:
                        with connection.transaction():
                            now=datetime.now(timezone.utc)
                            connection.execute('''INSERT INTO public.feature04_backfill_log
                             (run_id,ticker,calculation_version,status,started_at,finished_at,detail)
                             VALUES(%s,%s,%s,'FAILED',%s,%s,%s)
                             ON CONFLICT(run_id,ticker) DO UPDATE SET status='FAILED',finished_at=EXCLUDED.finished_at,detail=EXCLUDED.detail''',
                             (args.run_id,ticker,VERSION,now,now,type(error).__name__+'; transaction rolled back; inspect executor evidence.'))
                    manifest.update(status='FAILED',failed_tickers=1,last_ticker=ticker,error_type=type(error).__name__)
                    write_manifest(args.manifest,manifest)
                    raise
                manifest['completed_tickers']+=result['status'] in ('COMPLETED','DRY_RUN')
                manifest['skipped_verified_tickers']+=result['status']=='SKIPPED_VERIFIED'
                manifest['processed_rows']+=result['rows']
                manifest['changed_rows']+=result['changed_rows']
                manifest.update(last_ticker=ticker,elapsed_seconds=round(monotonic()-beginning,3))
                write_manifest(args.manifest,manifest)
                print(json.dumps(result),flush=True)
            manifest.update(status='COMPLETED',finished_at=datetime.now(timezone.utc).isoformat(),elapsed_seconds=round(monotonic()-beginning,3))
            write_manifest(args.manifest,manifest)
    except Exception as error:
        manifest.update(status='FAILED',error_type=type(error).__name__,finished_at=datetime.now(timezone.utc).isoformat())
        write_manifest(args.manifest,manifest)
        print(json.dumps({'status':'FAILED','error_type':type(error).__name__}),flush=True)
        raise SystemExit(1)
    print(json.dumps(manifest),flush=True)

if __name__=='__main__':
    main()
