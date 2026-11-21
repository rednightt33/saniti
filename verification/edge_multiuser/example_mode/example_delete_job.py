"""EXEC-MU-ACCOUNTS 3e, the example mode (ERRORS M527): delete one tab's stored example rows from edge_bff.example_files,
only when the rows there are exactly the ones named. The user's answer of 2026-11-21 on the Watchlist ("Untuk table
watchlist nggak apa-apa pakai data latest saja", "Benar opsi B"): its example is the latest publication, cut by edge-bff
(apps/edge-bff/app/examples.py WatchlistLatest), so the rows of 30 October (job b77b0506, the wrong LQ45 list) are read
by nothing and are deleted.

Looks before it deletes: lists the tab's rows (name, date, rows, bytes, the first 16 hex of the sha256, never a body) and
refuses unless their names are exactly params.json "expect"; then deletes them in the same transaction and reads the
tab back (0 rows), or rolls back. A 30 s statement timeout; the table holds a few rows per tab.

params.json: {"tab": "watchlist", "expect": ["watchlist-lists", "watchlist-stocks"], "write": false}
  write false: lists and checks only.
Run: scripts/onboarding/run_job.sh verification/edge_multiuser/example_mode/example_delete_job.py <params.json> <log>
"""
import json
import os

import psycopg

p = json.load(open('params.json'))
tab, expect, write = p['tab'], sorted(p['expect']), bool(p.get('write'))


def out(**kw):
    print('OUT ' + json.dumps(kw), flush=True)


with psycopg.connect(os.environ['DATABASE_URL']) as conn:
    conn.execute('SET statement_timeout = 30000')
    rows = conn.execute('SELECT name, as_of::text, rows, bytes, left(sha256, 16) FROM edge_bff.example_files '
                        'WHERE tab = %s ORDER BY name FOR UPDATE', (tab,)).fetchall()
    for name, as_of, n, size, sha in rows:
        out(step='row', tab=tab, name=name, as_of=as_of, rows=n, bytes=size, sha256=sha)
    names = [r[0] for r in rows]
    if names != expect:
        conn.rollback()
        print(f'VERDICT REFUSED the rows of {tab} are {names}, not {expect}', flush=True)
    elif not write:
        conn.rollback()
        print(f'VERDICT DRY_RUN_OK {len(names)} rows would be deleted', flush=True)
    else:
        done = conn.execute('DELETE FROM edge_bff.example_files WHERE tab = %s AND name = ANY(%s)', (tab, names)).rowcount
        left = conn.execute('SELECT count(*) FROM edge_bff.example_files WHERE tab = %s', (tab,)).fetchone()[0]
        if done != len(names) or left:
            conn.rollback()
            print(f'VERDICT ROLLED_BACK deleted {done}, {left} left', flush=True)
        else:
            conn.commit()
            back = conn.execute('SELECT count(*) FROM edge_bff.example_files WHERE tab = %s', (tab,)).fetchone()[0]
            others = conn.execute('SELECT tab, count(*) FROM edge_bff.example_files GROUP BY tab ORDER BY tab').fetchall()
            out(step='after', tab=tab, rows=back, other_tabs={t: c for t, c in others})
            print(f'VERDICT {"DELETED" if back == 0 else "READBACK_FAILED"} {done} rows', flush=True)
print('JOB_DONE', flush=True)
