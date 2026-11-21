"""EXEC-MU-ACCOUNTS 3e, the example mode as the user set it on 2026-11-21 (EXEC.md option A; ERRORS M527): builds the
example files of the tabs params.json names for its as_of (apps/terminal-publisher/examples.py: the files of each page's
opening view, cut at that date, every one checked for a later date) and writes them to edge_bff.example_files (migration
20261121_001), each tab's rows replaced whole in one transaction, then reads them back.

params.json: {"as_of": "2026-10-30", "tabs": ["radar"], "write": false}
  write false: builds and checks only; prints what it would write and writes nothing.

The reads are the publication's own statements (radar.build, its as-of variants), in a READ ONLY transaction; the write
is a second transaction. Prints OUT lines with names, row counts, byte sizes and the first 16 hex of each sha256, never a
value of the data (real market data stays out of Git and the logs), then VERDICT and JOB_DONE.

Run from the repository root (the publisher's modules go along as extras; publisher.py imports the other three):
  scripts/onboarding/run_job.sh verification/edge_multiuser/example_mode/capture_job.py <params.json> <log> \
    apps/terminal-publisher/publisher.py apps/terminal-publisher/radar.py apps/terminal-publisher/watchlist.py \
    apps/terminal-publisher/overview.py apps/terminal-publisher/examples.py
"""
import datetime
import json
import os
import sys

import psycopg

import examples
import publisher

p = json.load(open('params.json'))


def out(**kw):
    print('OUT ' + json.dumps(kw, default=str), flush=True)


def main():
    as_of = datetime.date.fromisoformat(p['as_of']).isoformat()
    tabs, write = list(p['tabs']), p.get('write') is True
    if not tabs or len(set(tabs)) != len(tabs):
        raise SystemExit('params.json: tabs must name each tab once')
    with psycopg.connect(os.environ['DATABASE_URL'], autocommit=False) as conn:
        with conn.transaction():
            conn.execute('SET TRANSACTION READ ONLY')
            conn.execute("SET LOCAL statement_timeout = '5min'")
            universe = conn.execute(publisher.UNIVERSE_SQL).fetchall()
            names = {t: n for t, n, *_ in universe}
            lists = [(r[0], r[1], r[2], r[3], list(r[6] or [])) for r in conn.execute(publisher.STOCK_LISTS_SQL).fetchall()]
            out(step='read', universe=len(names), lists=len(lists))
            rows = []
            for tab in tabs:
                built = examples.build(conn, tab, as_of, names, lists,
                                       stream=lambda sql, params: list(publisher.stream_rows(conn, sql, params)))
                for _, name, day, n, size, sha, _ in built:
                    out(step='built', tab=tab, name=name, as_of=day, rows=n, bytes=size, sha256=sha[:16])
                for note in examples.NOTES:                   # what a builder took as given (no data value)
                    out(step='note', tab=tab, note=note)
                examples.NOTES.clear()
                rows += built
        if not write:
            out(step='dry_run', files=len(rows))
            print('VERDICT DRY_RUN_OK', flush=True)
            return
        with conn.transaction():
            conn.execute("SET LOCAL statement_timeout = '1min'")
            gone = conn.execute('DELETE FROM edge_bff.example_files WHERE tab = ANY(%s)', (tabs,)).rowcount
            with conn.cursor() as c:
                c.executemany('INSERT INTO edge_bff.example_files(tab, name, as_of, rows, bytes, sha256, body) '
                              'VALUES (%s, %s, %s, %s, %s, %s, %s)', rows)
            out(step='written', replaced=gone, files=len(rows))
        back = conn.execute('SELECT tab, name, as_of::text, rows, bytes, sha256, encode(sha256(body), \'hex\') = sha256 '
                            'FROM edge_bff.example_files WHERE tab = ANY(%s) ORDER BY tab, name', (tabs,)).fetchall()
        want = sorted((t, n, a, r, b, s, True) for t, n, a, r, b, s, _ in rows)
        same = sorted(tuple(x) for x in back) == want
        out(step='readback', files=len(back), same=same)
        print('READBACK ' + ('OK' if same else 'DIFFERENT'), flush=True)
        print('VERDICT ' + ('WRITTEN' if same else 'READBACK_FAILED'), flush=True)
        if not same:
            sys.exit(1)


if __name__ == '__main__':
    try:
        main()
    except examples.ExampleError as e:
        print('VERDICT REFUSED ' + json.dumps(str(e)), flush=True)
        sys.exit(1)
    except Exception as e:  # noqa: BLE001 - the class only: a driver error may carry connection details
        print('ERR ' + type(e).__name__, flush=True)
        sys.exit(1)
    print('JOB_DONE', flush=True)
