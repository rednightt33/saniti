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
    nonkey = COLUMNS[3:]
    payload = tuple(c for c in nonkey if c != 'calculated_at')
    statement = sql.SQL('''INSERT INTO public.{} AS target ({}) VALUES ({})
      ON CONFLICT (ticker, trade_date, timeframe) DO UPDATE SET {}
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
    history = connection.execute('''SELECT ticker,date,open,high,low,close,volume,timeframe,
             tradingview_symbol,source,query_date,ingestion_time
             FROM public."Price_Stock_Indonesia_IDX"
             WHERE ticker=ANY(%s) AND date<=%s ORDER BY ticker,date''', (tickers, end)).fetchall()
    if set(tickers) != {r['ticker'] for r in history}:
        raise ValueError('At least one requested ticker has no source history')
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
