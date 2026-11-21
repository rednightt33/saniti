"""EXEC-MU-ACCOUNTS 3e, the example mode (ERRORS M527, the example-mode checker's Watchlist finding): a read-only probe
of the Watchlist example's list against the LQ45 membership history. The checker found that the stored list of "LQ45 on
30 October 2026" is the list first recorded on 10 November (members_on's fallback), and an outside source (Stockbit
Research, 2026-10-27) that the exchange announced on 26 October a review effective 2 November: ELSA and SMGR in, CUAN and
SCMA out. This probe reads, for the tickers named in params.json only:
- whether each is in the stored example's list (edge_bff.example_files, tab watchlist, its lists file);
- its LQ45 history rows (valid and point-in-time dates, bases, the run that recorded them);
and, for the whole list, the count of members per pit_valid_from and per pit_valid_to, and the stock-list rounds
(Stock_List_Load_Log: dates, status, counts). Prints dates, counts and the named tickers' membership only, no market
data. One READ ONLY transaction, a 30 s statement timeout; every table read is small (the history of one list, one
tab's example rows).

params.json: {"code": "LQ45", "tickers": ["ELSA", "SMGR", "CUAN", "SCMA"]}
Run: scripts/onboarding/run_job.sh verification/edge_multiuser/example_mode/lq45_probe_job.py <params.json> <log>
"""
import gzip
import json
import os

import psycopg

p = json.load(open('params.json'))


def out(**kw):
    print('OUT ' + json.dumps(kw, default=str), flush=True)


def main():
    code, named = p['code'], p['tickers']
    with psycopg.connect(os.environ['DATABASE_URL']) as conn:
        conn.execute('SET statement_timeout = 30000')
        conn.execute('BEGIN READ ONLY')
        rows = conn.execute('SELECT name, as_of::text, rows, sha256, body FROM edge_bff.example_files '
                            'WHERE tab = %s ORDER BY name', ('watchlist',)).fetchall()
        for name, as_of, n, sha, body in rows:
            doc = json.loads(gzip.decompress(bytes(body)))
            held = None
            if isinstance(doc, dict) and isinstance(doc.get('lists'), list):
                held = [{'list_name': l.get('name'), 'tickers': len(l.get('tickers') or []),
                         'named': {t: any(x.get('ticker') == t for x in l.get('tickers') or []) for t in named}}
                        for l in doc['lists']]
            elif isinstance(doc, dict) and isinstance(doc.get('ticker'), list):
                held = {'tickers': len(doc['ticker']), 'named': {t: t in doc['ticker'] for t in named}}
            out(step='stored', name=name, as_of=as_of, rows=n, sha256=sha[:12], held=held)
        lk = conn.execute('SELECT list_key, first_seen_at::text, last_seen_at::text, member_count FROM public."Stock_List" '
                          'WHERE list_kind = %s AND code = %s', ('INDEX', code)).fetchall()
        out(step='list', rows=[list(r) for r in lk])
        if not lk:
            print('VERDICT NO_LIST', flush=True)
            return
        key = lk[0][0]
        for t in named:
            h = conn.execute('SELECT valid_from::text, valid_to::text, valid_basis, available_basis, recorded_from::text, '
                             'recorded_to::text, superseded_reason, pit_valid_from::text, pit_valid_to::text, run_id '
                             'FROM public."Stock_List_Member_History" WHERE list_key = %s AND "Ticker" = %s '
                             'ORDER BY recorded_from', (key, t)).fetchall()
            out(step='history', ticker=t, rows=[list(r) for r in h])
        f = conn.execute('SELECT pit_valid_from::text, count(*) FROM public."Stock_List_Member_History" WHERE list_key = %s '
                         'GROUP BY 1 ORDER BY 1', (key,)).fetchall()
        t = conn.execute('SELECT coalesce(pit_valid_to::text, \'open\'), count(*) FROM public."Stock_List_Member_History" '
                         'WHERE list_key = %s GROUP BY 1 ORDER BY 1', (key,)).fetchall()
        b = conn.execute('SELECT valid_basis, available_basis, count(*) FROM public."Stock_List_Member_History" '
                         'WHERE list_key = %s GROUP BY 1, 2 ORDER BY 1, 2', (key,)).fetchall()
        out(step='list_history', by_pit_valid_from=[list(r) for r in f], by_pit_valid_to=[list(r) for r in t],
            by_basis=[list(r) for r in b])
        runs = conn.execute('SELECT run_id, started_at::text, status, lists_applied, members, added, removed, '
                            '(changes ? %s) AS touched FROM public."Stock_List_Load_Log" ORDER BY run_id', (key,)).fetchall()
        out(step='rounds', rows=[list(r) for r in runs])
        # the Stockbit rounds since the lists' first capture (UPDATE_TABLE.md step 4b runs in every APPLY round): mode,
        # status, times and the stock_lists step's summary keys or its error class, never a value of the data
        since = p.get('rounds_since', '2026-11-08')
        sb = conn.execute('SELECT left(execution_id::text, 8), mode, status, started_at::text, finished_at::text, '
                          'stock_lists FROM public."Monitoring_Stockbit_Update" WHERE started_at >= %s::date '
                          'ORDER BY started_at', (since,)).fetchall()
        def step(v):
            if not isinstance(v, dict):
                return v if v is None else type(v).__name__
            return {k: (v[k] if isinstance(v[k], (int, bool)) or v[k] is None or k in ('status', 'reason', 'code')
                        else type(v[k]).__name__) for k in list(v)[:12]}
        out(step='stockbit_rounds', since=since, rows=[[*r[:5], step(r[5])] for r in sb])
        conn.execute('ROLLBACK')
    print('VERDICT DONE', flush=True)


main()
print('JOB_DONE', flush=True)
