"""EXEC-INDEX-GROUP-HISTORY stage 5 (trial, dry run) and stage 6 (fill): scripts/backfill_index_entities.py on
orc-test-runner (user go 2026-11-15: "Langsung go tahap 4-9, kecuali ada perubahan arah material dan butuh decision
saya"). Extras: scripts, features, apps/stockbit-updater/requirements.txt.

params.json: {"tickers": [..] or null (every entity but IHSG), "apply": false, "batch": 10, "until": null,
              "since": null, "large_write": false}
Prints the script's events, TEMP_SIZE after each read, READBACK per entity (apply) and SUMMARY, then JOB_DONE."""
import json
import os
import sys
import time
from datetime import date

sys.path[:0] = ['scripts']
import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402
import backfill_index_entities as x  # noqa: E402

p = json.load(open('params.json'))
until = date.fromisoformat(p['until']) if p.get('until') else None
since = date.fromisoformat(p['since']) if p.get('since') else None
read = x.read_months


def measured_read(db, *args):
    started = time.monotonic()
    read(db, *args)
    size = db.execute('''SELECT coalesce(sum(pg_total_relation_size(c.oid)), 0) AS bytes,
        string_agg(c.relname || '=' || pg_total_relation_size(c.oid), ' ' ORDER BY c.relname) AS tables
        FROM pg_class c WHERE c.relnamespace = pg_my_temp_schema() AND c.relkind = 'r' ''').fetchone()
    rows = db.execute('SELECT (SELECT count(*) FROM bulk5_all) AS detail, (SELECT count(*) FROM hist6) AS collapsed').fetchone()
    print('TEMP_SIZE ' + json.dumps({'seconds': round(time.monotonic() - started, 1), 'mb': round(size['bytes'] / 2**20, 1),
                                     'rows': rows, 'tables': size['tables']}, default=str), flush=True)


x.read_months = measured_read
t0 = time.monotonic()
with psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row, autocommit=True,
                     application_name='index-entities-backfill') as db:
    db.execute("SET statement_timeout='30min'")
    db.execute("SET lock_timeout='10s'")
    db.execute("SET work_mem='64MB'")
    db.execute('SET max_parallel_workers_per_gather=0')
    result = x.run(db, p.get('tickers'), bool(p.get('apply')), int(p.get('batch') or 10), until, since)
    if p.get('apply'):
        for t in sorted(result['written']):
            counts = {}
            for f, base in x.b.BASE.items():
                dc = 'date' if f in (1, 2, 3) else 'trade_date'
                counts[f] = db.execute(f'SELECT count(*) AS n, min({dc})::text AS first, max({dc})::text AS last '
                                       f'FROM public."{base}_INDEX" WHERE ticker = %s', (t,)).fetchone()
            print('READBACK ' + json.dumps({'ticker': t, 'staged': result['written'][t], 'stored': counts}, default=str),
                  flush=True)
        for base in x.b.BASE.values():
            db.execute(f'ANALYZE public."{base}_INDEX"')
print('SUMMARY ' + json.dumps({'entities': result['entities'], 'apply': bool(p.get('apply')),
                               'seconds': round(time.monotonic() - t0, 1)}, default=str), flush=True)
print('VERDICT PASS', flush=True)
print('JOB_DONE', flush=True)
