"""EXEC-MU-ACCOUNTS 3e, the example mode as the user set it on 2026-11-21 (EXEC.md option A; ERRORS M527): builds the
example files of the tabs params.json names for its as_of (apps/terminal-publisher/examples.py: the files of each page's
opening view, cut at that date, every one checked for a later date) and writes them to edge_bff.example_files (migration
20261121_001), each tab's rows replaced whole in one transaction, then reads them back.

params.json: {"as_of": "2026-10-30", "tabs": ["radar"], "write": false}
  write false: builds and checks only; prints what it would write and writes nothing.
  with the tab "backtest", also "backtest": {"worker_url": ..., "releases": "releases.json", "built_on": the part of the
  worker's catalog the request is built on (backtest_catalog_job.py prints it), "request": the page's own request on
  it (backtest_request.ts)}; capture_backtest.json holds the example's. The worker's key goes as a Railway reference for
  the run only (RUN_JOB_EXTRA_VARS='BACKTEST_WORKER_KEY=${{backtest-worker.BACKTEST_WORKER_KEY}}') and
  apps/edge-bff/catalog/releases.json goes along as an extra (the items a run may read: the released ones).

The reads are the publication's own statements (radar.build, its as-of variants), in a READ ONLY transaction; the write
is a second transaction. Prints OUT lines with names, row counts, byte sizes and the first 16 hex of each sha256, never a
value of the data (real market data stays out of Git and the logs), then VERDICT and JOB_DONE.

Run from the repository root (the publisher's modules go along as extras; publisher.py imports the other three):
  scripts/onboarding/run_job.sh verification/edge_multiuser/example_mode/capture_job.py <params.json> <log> \
    apps/terminal-publisher/publisher.py apps/terminal-publisher/radar.py apps/terminal-publisher/watchlist.py \
    apps/terminal-publisher/overview.py apps/terminal-publisher/examples.py
"""
import datetime
import gzip
import json
import os
import secrets
import sys
import time
import urllib.request

import psycopg

import examples
import publisher

p = json.load(open('params.json'))


def out(**kw):
    print('OUT ' + json.dumps(kw, default=str), flush=True)


# ---- the Backtest: one run of the page's own request on the real worker (examples.py backtest_files) -------------------
# The worker keeps one job at a time and drops the previous one's result when a new one starts, so the run starts only
# while no backtest of either site is queued or running (and the worker answers 409 BUSY to one that is).
BUSY_SQL = "SELECT count(*) FROM edge_bff.backtest_jobs WHERE state IN ('QUEUED', 'RUNNING')"
# the items a run may read: every item released to the live site (apps/edge-bff/catalog/releases.json), per kind the
# worker knows; no right (the point-in-time versions are refused)
ALLOW_KINDS = ('indicator', 'flow_indicator', 'candle_pattern', 'screener_metric')


def backtest_worker(url, key):
    def call(method, path, body=None):
        req = urllib.request.Request(url.rstrip('/') + path, method=method,
                                     data=None if body is None else json.dumps(body).encode(),
                                     headers={'x-backtest-worker-key': key, 'accept': 'application/json',
                                              **({} if body is None else {'content-type': 'application/json'})})
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read()
            return json.loads(gzip.decompress(raw) if r.headers.get('content-encoding') == 'gzip' else raw)
    return call


def backtest_extra(conn, spec, as_of):
    """The Backtest builder's request, the catalog part it was built on, run and catalog (params.json backtest:
    {request, built_on, worker_url, releases}). The run is made here, before the build's READ ONLY transaction (it may
    take minutes; no transaction waits on it), and only when the worker's catalog cut to the period holds the part
    (the builder checks it again)."""
    call = backtest_worker(spec['worker_url'], os.environ['BACKTEST_WORKER_KEY'])
    releases = json.load(open(spec.get('releases', 'releases.json')))
    allow = {k: sorted(i['id'] for i in releases['items'] if i['kind'] == k and i['stage'] == 'released') for k in ALLOW_KINDS}

    def run(request):
        if conn.execute(BUSY_SQL).fetchone()[0]:
            raise examples.ExampleError('a backtest of a user is queued or running: try the capture again later')
        job = 'bt_' + secrets.token_hex(16)
        call('POST', '/v1/jobs', {'job_id': job, 'request': request, 'context': {
            'job_id': job, 'prior_trials': [], 'rights': [], 'allow': allow, 'limits': {}}})
        for _ in range(600):
            st = call('GET', f'/v1/jobs/{job}')
            if st.get('state') in ('FINISHED', 'FAILED', 'CANCELLED'):
                break
            time.sleep(2)
        out(step='backtest_run', job=job, state=st.get('state'), duration_ms=st.get('duration_ms'),
            error=(st.get('error') or {}).get('code'))
        if st.get('state') != 'FINISHED':
            raise examples.ExampleError(f"the example's backtest ended {st.get('state')}: {(st.get('error') or {}).get('message')}")
        return call('GET', f'/v1/jobs/{job}/result')
    catalog = call('GET', '/v1/catalog')
    first = (spec['request'].get('period') or {}).get('from')
    where = examples.outside(spec['built_on'], examples.backtest_catalog(catalog, first, as_of))
    if where:
        raise examples.ExampleError(f'the request was built on a catalog the worker\'s does not hold at {where}: build '
                                    'it again on the worker\'s catalog (backtest_catalog_job.py, backtest_request.ts)')
    result = run(spec['request'])
    conn.commit()                                       # the busy check's transaction ends before the build's starts

    def ran(request):
        if request != spec['request']:
            raise examples.ExampleError('the builder asked for another request than the one run')
        return result
    return {'request': spec['request'], 'run': ran, 'catalog': catalog, 'built_on': spec['built_on']}


def main():
    as_of = datetime.date.fromisoformat(p['as_of']).isoformat()
    tabs, write = list(p['tabs']), p.get('write') is True
    if not tabs or len(set(tabs)) != len(tabs):
        raise SystemExit('params.json: tabs must name each tab once')
    with psycopg.connect(os.environ['DATABASE_URL'], autocommit=False) as conn:
        extras = {'backtest': backtest_extra(conn, p['backtest'], as_of)} if 'backtest' in tabs else {}
        with conn.transaction():
            conn.execute('SET TRANSACTION READ ONLY')
            conn.execute("SET LOCAL statement_timeout = '5min'")
            universe = conn.execute(publisher.UNIVERSE_SQL).fetchall()
            names = {t: n for t, n, *_ in universe}
            lists = [(r[0], r[1], r[2], r[3], list(r[6] or [])) for r in conn.execute(publisher.STOCK_LISTS_SQL).fetchall()]
            out(step='read', universe=len(names), lists=len(lists))
            rows = []
            for tab in tabs:
                extra = extras.get(tab, {})
                built = examples.build(conn, tab, as_of, names, lists,
                                       stream=lambda sql, params: list(publisher.stream_rows(conn, sql, params)), **extra)
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
