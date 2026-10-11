"""Bounded, explicit daily refresh. Default is dry-run; never a full backfill."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from datetime import date
from pathlib import Path
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from engine import COLUMNS, TABLE, VERSION, calculate, library_contract


def upsert(connection, rows: list[dict]) -> int:
    if not rows:
        return 0
    if len(rows) > 5000:
        raise ValueError('At most 5000 output rows per controlled execution')
    key_columns = {'ticker', 'trade_date', 'timeframe', 'asset_type'}
    nonkey = tuple(column for column in COLUMNS if column not in key_columns)
    payload = tuple(c for c in nonkey if c != 'calculated_at')
    statement = sql.SQL('''INSERT INTO public.{} AS target ({}) VALUES ({})
      ON CONFLICT (ticker, trade_date, timeframe, asset_type) DO UPDATE SET {}
      WHERE ROW({}) IS DISTINCT FROM ROW({})''').format(
        sql.Identifier(TABLE), sql.SQL(',').join(map(sql.Identifier, COLUMNS)),
        sql.SQL(',').join(sql.Placeholder() for _ in COLUMNS),
        sql.SQL(',').join(sql.SQL('{}=EXCLUDED.{}').format(sql.Identifier(c), sql.Identifier(c)) for c in nonkey),
        sql.SQL(',').join(sql.SQL('target.{}').format(sql.Identifier(c)) for c in payload),
        sql.SQL(',').join(sql.SQL('EXCLUDED.{}').format(sql.Identifier(c)) for c in payload))
    changed = 0
    for r in rows:
        changed += connection.execute(statement, [r[c] for c in COLUMNS]).rowcount
    return changed


def refresh(connection, tickers: list[str], start: date, end: date, *, write=False) -> dict:
    if not tickers or len(tickers) > 10 or len(set(tickers)) != len(tickers):
        raise ValueError('Specify 1–10 distinct tickers; all-universe processing is unavailable')
    if start > end or (end - start).days > 366:
        raise ValueError('Specify an output range no longer than 366 days')
    connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
    if write:
        # Only coordinates this engine; source ingestion is deliberately untouched.
        connection.execute("SELECT pg_advisory_xact_lock(hashtextextended('Feature04_Technical_Indicator',0))")
    else:
        connection.execute('SET TRANSACTION READ ONLY')
    history = connection.execute('''
             SELECT p.ticker,p.date,p.open,p.high,p.low,p.close,p.volume,p.timeframe,
                    p.tradingview_symbol,p.source,p.query_date,p.ingestion_time,
                    'equity'::text AS asset_type
             FROM public."Price_Stock_Indonesia_IDX" p
             WHERE p.ticker=ANY(%s) AND p.date<=%s
               AND EXISTS(SELECT 1 FROM public."IDX_Stock_Universe" u WHERE u."Ticker"=p.ticker)
             UNION ALL
             SELECT p.ticker,p.date,p.open,p.high,p.low,p.close,p.volume,'Daily'::text,
                    p.tradingview_symbol,p.source,p.query_date,p.ingestion_time,
                    'bonds'::text AS asset_type
             FROM public."Price_Fixed_Income" p
             WHERE p.ticker=ANY(%s) AND p.date<=%s AND p.metric_type='price' AND p."Timeframe"='1D'
               AND EXISTS(SELECT 1 FROM public."Universe_Fixed_income" u WHERE u.ticker=p.ticker)
             ORDER BY ticker,date,asset_type''', (tickers, end, tickers, end)).fetchall()
    if set(tickers) != {r['ticker'] for r in history}:
        raise ValueError('At least one requested ticker has no source history')
    classified = {}
    for row in history:
        classified.setdefault(row['ticker'], set()).add(row['asset_type'])
    if any(len(asset_types) != 1 for asset_types in classified.values()):
        raise ValueError('A ticker must resolve to exactly one approved asset universe')
    features = calculate(history)
    selected = [r for r in features if start <= r['trade_date'] <= end]
    if len(selected) > 5000:
        raise ValueError('At most 5000 output rows per controlled execution')
    digest = hashlib.sha256(json.dumps(history, sort_keys=True, default=str, separators=(',', ':')).encode()).hexdigest()
    return {'calculation_version': VERSION, 'library': library_contract(),
            'source_rows_read': len(history), 'source_sha256': digest,
            'tickers': tickers, 'start': str(start), 'end': str(end),
            'output_rows': len(selected), 'changed_rows': upsert(connection, selected) if write else 0,
            'mode': 'WRITE' if write else 'DRY_RUN',
            'tradingview_parity': 'NOT VERIFIED', 'training_point_in_time_eligibility': 'NOT VERIFIED'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tickers', nargs='+', required=True)
    parser.add_argument('--start', type=date.fromisoformat, required=True)
    parser.add_argument('--end', type=date.fromisoformat, required=True)
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--manifest', type=Path, required=True)
    args = parser.parse_args()
    with psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row,
                         options='-c statement_timeout=60000 -c lock_timeout=5000') as connection:
        manifest = refresh(connection, args.tickers, args.start, args.end, write=args.write)
    args.manifest.write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
