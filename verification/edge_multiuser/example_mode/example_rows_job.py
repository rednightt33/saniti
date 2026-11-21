"""EXEC-MU-ACCOUNTS 3e, the example mode (ERRORS M527): a read-only list of the stored examples on dev, to compare a capture
made again with the rows it replaces (a file the change did not mean to touch must keep its sha256). Prints each row's
tab, name, date, rows, bytes and the first 16 hex of its sha256, never a body. One READ ONLY transaction, a 30 s
statement timeout; the table holds a few rows per tab.

params.json: {"tabs": ["radar", "backtest"]}   (an empty list: every tab)
Run: scripts/onboarding/run_job.sh verification/edge_multiuser/example_mode/example_rows_job.py <params.json> <log>
"""
import json
import os

import psycopg

p = json.load(open('params.json'))
with psycopg.connect(os.environ['DATABASE_URL']) as conn:
    conn.execute('SET statement_timeout = 30000')
    conn.execute('BEGIN READ ONLY')
    tabs = list(p.get('tabs') or [])
    rows = conn.execute('SELECT tab, name, as_of::text, rows, bytes, left(sha256, 16), made_at::text FROM edge_bff.example_files '
                        'WHERE cardinality(%s::text[]) = 0 OR tab = ANY(%s) ORDER BY tab, name', (tabs, tabs)).fetchall()
    for tab, name, as_of, n, size, sha, made in rows:
        print('OUT ' + json.dumps({'step': 'row', 'tab': tab, 'name': name, 'as_of': as_of, 'rows': n, 'bytes': size,
                                   'sha256': sha, 'made_at': made}), flush=True)
    conn.execute('ROLLBACK')
print(f'VERDICT ROWS {len(rows)}', flush=True)
print('JOB_DONE', flush=True)
