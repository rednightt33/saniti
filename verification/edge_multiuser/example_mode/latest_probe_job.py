"""EXEC-MU-ACCOUNTS 3e, the example mode (ERRORS M527): a read-only probe for the user's decision of 2026-11-21 on the
Watchlist's example ("Untuk table watchlist nggak apa-apa pakai data latest saja, karena yang dibutuhkan hanya harga
saham"). It reads what an example on the latest data would hold, from the publication's own statements:
- the Watchlist's newest complete price date and its broker date (watchlist.build, as the daily publication runs it);
- the list's members now (public."Stock_List_Member", the table the Market Overview's lists read) and its recorded
  history (Stock_List_Member_History: the rows covering the price date, the first recorded day);
- for the members, how many have a value of each default indicator and of the price columns.
Prints dates and counts only, never a value of the data. One READ ONLY transaction, a 60 s statement timeout; the reads
are the Watchlist publication's (0.1-3 s on dev, its module docstring) and the history of one list.

params.json: {"code": "LQ45"}
Run (the publisher's modules go along as extras):
  scripts/onboarding/run_job.sh verification/edge_multiuser/example_mode/latest_probe_job.py <params.json> <log> \
    apps/terminal-publisher/watchlist.py apps/terminal-publisher/radar.py
"""
import json
import os

import psycopg

import watchlist

p = json.load(open('params.json'))


def out(**kw):
    print('OUT ' + json.dumps(kw, default=str), flush=True)


with psycopg.connect(os.environ['DATABASE_URL']) as conn:
    conn.execute('SET statement_timeout = 60000')
    conn.execute('BEGIN READ ONLY')
    run = lambda sql, params: conn.execute(sql, params).fetchall()
    docs = watchlist.build(run)
    s = docs['watchlist-stocks']
    out(step='dates', prices_through=s['prices_through'], broker_through=s['broker_through'],
        trend_from=s['dates'][0] if s['dates'] else None, trend_sessions=len(s['dates']), stocks=len(s['ticker']),
        default=s['default'])
    code = p['code']
    now = [r[0] for r in run('SELECT m."Ticker" FROM public."Stock_List_Member" AS m JOIN public."Stock_List" AS l '
                             'USING (list_key) WHERE l.list_kind = %s AND l.code = %s ORDER BY 1', ('INDEX', code))]
    hist = run('SELECT h."Ticker", h.pit_valid_from::text, h.pit_valid_to::text FROM public."Stock_List_Member_History" '
               'AS h JOIN public."Stock_List" AS l USING (list_key) WHERE l.list_kind = %s AND l.code = %s', ('INDEX', code))
    d = s['prices_through']
    covering = sorted(t for t, a, b in hist if a <= d and (b is None or b > d))
    out(step='members', code=code, members_now=len(now), history_rows=len(hist),
        first_recorded=min((a for _, a, _ in hist), default=None), closed_rows=sum(1 for *_, b in hist if b is not None),
        covering_price_date=len(covering), same_as_now=covering == now)
    at = {t: i for i, t in enumerate(s['ticker'])}
    inside = [t for t in now if t in at]
    filled = lambda arr: sum(1 for t in inside if arr[at[t]] is not None)
    out(step='values', members_in_file=len(inside), outside_file=len(now) - len(inside),
        last=filled(s['last']), r1d=filled(s['r1d']), r1m=filled(s['r1m']),
        trend_full=sum(1 for t in inside if all(v is not None for v in s['trend'][at[t]])),
        **{f'default_{k}': filled(s['values'][k]) for k in s['default']},
        events_next_days=sum(1 for t in inside if s['events'].get(t)))
    conn.execute('ROLLBACK')
print('VERDICT PROBED', flush=True)
print('JOB_DONE', flush=True)
