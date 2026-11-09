"""EXEC-INDEX-INCREMENTAL before/after (user 2026-11-09: "jangan lupa dibandingkan before after ... run with proposed
process and detect where the gap"): for each from_date in params.json, stage the IHSG INDEX tables with the incremental
prepare() of scripts/backfill_index_features.py (session temp tables only) and compare them with the stored INDEX
tables, which the existing full rebuild wrote (stockbit-updater round 325f4864, 2026-11-09). Nothing is written: each
date runs in its own REPEATABLE READ transaction that is rolled back.

Compared per Feature: broker features (2, 3, 5, 6) every row with date >= from_date, prices (1, 4) every row; all
analytical columns (not calculated_at, not the frequency coverage counters). Exact first (EXCEPT both ways); when rows
differ, per column with keys joined: numbers equal within 1e-9 relative (math.isclose), everything else exact.
params.json: {"from_dates": ["2026-11-04", ...], "expect_full": ["2016-06-01"]}. Prints OUT/ERR lines and JOB_DONE.
"""
import json
import math
import os
import sys
import time
from datetime import date
from decimal import Decimal

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

sys.path[:0] = ['scripts', 'features/feature04']
import backfill_index_features as b  # noqa: E402

TICKER, SAMPLE = 'IHSG', date(2026, 8, 31)
p = json.load(open('params.json'))


def out(q, **kw):
    print('OUT ' + json.dumps({'q': q, **kw}, default=str), flush=True)


def keys_of(f, dc):
    return ['ticker', dc] + (['broker', 'investor_type', 'market_board'] if f in (2, 5) else ['market_board'] if f in (3, 6)
                             else ['timeframe', 'asset_type'] if f == 4 else [])


def close(a, c):
    if a is None or c is None:
        return a is None and c is None
    if isinstance(a, (int, float, Decimal)) and isinstance(c, (int, float, Decimal)) and not isinstance(a, bool):
        return math.isclose(float(a), float(c), rel_tol=1e-9, abs_tol=1e-9)
    return a == c


def compare(db, f, from_date):
    base = b.BASE[f]; target = base + '_INDEX'; stage = 'calc' + str(f); dc = 'date' if f in (1, 2, 3) else 'trade_date'
    names = [c for c in b.cols(db, target) if c != 'calculated_at' and c not in b.COVER]
    lo = from_date if f in b.BROKER else date.min
    proj = sql.SQL(',').join(map(sql.Identifier, names))
    where = sql.SQL('ticker=%s AND {}>=%s').format(sql.Identifier(dc))
    n_stage = db.execute(sql.SQL('SELECT count(*) AS n FROM {} WHERE ').format(sql.Identifier(stage)) + where, (TICKER, lo)).fetchone()['n']
    n_store = db.execute(sql.SQL('SELECT count(*) AS n FROM public.{} WHERE ').format(sql.Identifier(target)) + where, (TICKER, lo)).fetchone()['n']
    diff = sql.SQL('SELECT count(*) AS n FROM (SELECT {p} FROM {a} WHERE {w} EXCEPT SELECT {p} FROM {c} WHERE {w}) x')
    only_stage = db.execute(diff.format(p=proj, a=sql.Identifier(stage), c=sql.SQL('public.{}').format(sql.Identifier(target)), w=where),
                            (TICKER, lo, TICKER, lo)).fetchone()['n']
    only_store = db.execute(diff.format(p=proj, a=sql.SQL('public.{}').format(sql.Identifier(target)), c=sql.Identifier(stage), w=where),
                            (TICKER, lo, TICKER, lo)).fetchone()['n']
    columns, examples, unmatched = {}, [], 0
    if only_stage or only_store:
        keys = keys_of(f, dc)
        on = sql.SQL(' AND ').join(sql.SQL('s.{k}=t.{k}').format(k=sql.Identifier(k)) for k in keys)
        rows = db.execute(sql.SQL('SELECT to_jsonb(s) AS s, to_jsonb(t) AS t FROM {} s FULL JOIN public.{} t ON {} '
                                  'WHERE coalesce(s.ticker,t.ticker)=%s AND coalesce(s.{dc},t.{dc})>=%s').format(
            sql.Identifier(stage), sql.Identifier(target), on, dc=sql.Identifier(dc)), (TICKER, lo))
        for r in rows:
            s, t = r['s'], r['t']
            if s is None or t is None:
                unmatched += 1
                if len(examples) < 5:
                    examples.append({'only': 'stored' if s is None else 'staged', 'key': {k: (s or t).get(k) for k in keys}})
                continue
            for c in names:
                if not close(s.get(c), t.get(c)):
                    columns[c] = columns.get(c, 0) + 1
                    if len(examples) < 5:
                        examples.append({'key': {k: s.get(k) for k in keys}, 'column': c, 'staged': s.get(c), 'stored': t.get(c)})
    gap = unmatched + sum(columns.values())
    out('compare', from_date=from_date, feature=f, scope='>= from_date' if f in b.BROKER else 'all rows',
        staged_rows=n_stage, stored_rows=n_store, exact_only_staged=only_stage, exact_only_stored=only_store,
        unmatched_keys=unmatched, column_differences=columns, examples=examples, gap=gap)
    return gap


def wait_for_database(tries=30):
    # the private network name can need a few seconds after the container starts (log of 2026-11-09 11:30 UTC)
    for i in range(tries):
        try:
            with psycopg.connect(os.environ['DATABASE_URL'], connect_timeout=10) as c:
                c.execute('SELECT 1')
                return
        except psycopg.OperationalError:
            if i == tries - 1:
                raise
            time.sleep(5)


wait_for_database()
total = 0
for raw in p['from_dates']:
    d = date.fromisoformat(raw)
    started = time.monotonic()
    with psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row, autocommit=True,
                         application_name='index-incremental-compare') as db:
        db.execute("SET statement_timeout='20min'"); db.execute("SET work_mem='64MB'")
        db.execute('SET max_parallel_workers_per_gather=0')
        try:
            with db.transaction():
                db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
                info = b.prepare(db, TICKER, SAMPLE, False, from_date=d)
                staged_s = round(time.monotonic() - started, 1)
                full = info['from_date'] is None
                out('window', from_date=d, window_first=info['window_first'], full_rebuild=full,
                    expected_full=raw in p.get('expect_full', []), accepted_sample=info['sample'], stage_seconds=staged_s)
                gap = sum(compare(db, f, d if not full else date.min) for f in b.BASE)
                total += gap
                out('result', from_date=d, gap=gap, seconds=round(time.monotonic() - started, 1))
                raise psycopg.Rollback()
        except Exception as e:  # noqa: BLE001 - a failed date is reported and counted, the next date still runs
            total += 1
            print('ERR ' + json.dumps({'q': 'from_date', 'from_date': raw, 'error': f'{type(e).__name__}: {str(e)[:500]}'}), flush=True)
out('verdict', gap_total=total, verdict='NO_GAP' if total == 0 else 'GAP')
print('JOB_DONE INDEX_INCREMENTAL_COMPARE', flush=True)
