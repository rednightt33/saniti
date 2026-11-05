"""EXEC-UNIVERSE-BROKER S3 (user go 2026-11-05: "Ok jalankan"): rebuild the IHSG INDEX tables after the upload of the
codes that are not four letters, with stockbit-updater's own step (apps/stockbit-updater/refresh.py refresh_index:
scripts/backfill_index_features.py prepare + apply_chunks, its universe cross-check of S2), on orc-test-runner.
Prints the newest date of each INDEX table and the IHSG Feature 05 INDEX totals of 2026-09-01..11-03 against the source."""
import json
import os
import sys
import time
import uuid
from datetime import date

sys.path.insert(0, 'scripts')
import psycopg
from psycopg.rows import dict_row
import backfill_index_features as b

t0 = time.monotonic()
with psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row, autocommit=True,
                     application_name='index-rebuild-s3') as db:
    db.execute("SET statement_timeout='20min'")
    db.execute("SET lock_timeout='10s'")
    db.execute("SET work_mem='64MB'")
    db.execute('SET max_parallel_workers_per_gather=0')
    if not db.execute('SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS ok', ('index-bulk:IHSG',)).fetchone()['ok']:
        raise SystemExit('Another INDEX writer is active')
    with db.transaction():
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        b.prepare(db, 'IHSG', date(2026, 8, 31), False)
    b.apply_chunks(db, 'IHSG', uuid.uuid4())
    newest = {f: str(db.execute(f'SELECT max({"date" if f in (1, 2, 3) else "trade_date"}) AS d '
                                f'FROM public."{t}_INDEX"').fetchone()['d']) for f, t in b.BASE.items()}
    for t in b.BASE.values():
        db.execute(f'ANALYZE public."{t}_INDEX"')
    check = db.execute('''WITH s AS (SELECT "Date" d, sum("Buy Value") bv, sum("Sell Value") sv, sum(buy_freq) bf
            FROM public."IDX_Broker_Summary" WHERE "Date" BETWEEN '2026-09-01' AND '2026-11-03' GROUP BY 1),
        i AS (SELECT trade_date d, sum(buy_value) bv, sum(sell_value) sv, sum(buy_freq) bf
            FROM public."Feature_05_Foreign_Domestic_Broker_Detail_INDEX" WHERE ticker='IHSG'
              AND trade_date BETWEEN '2026-09-01' AND '2026-11-03' GROUP BY 1)
        SELECT count(*) AS dates, count(*) FILTER (WHERE (s.bv, s.sv, s.bf) IS NOT DISTINCT FROM (i.bv, i.sv, i.bf)) AS equal
        FROM s LEFT JOIN i USING (d)''').fetchone()
print('OUT ' + json.dumps({'event': 'index_done', 'newest': newest, 'sep_nov_dates': check['dates'],
                           'sep_nov_equal_to_source': check['equal'], 'seconds': round(time.monotonic() - t0, 1)}),
      flush=True)
print('JOB_DONE', flush=True)
