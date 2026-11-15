"""EXEC-RADAR, ERRORS M434 (user decision 2026-11-14: "2 perbaiki sekarang"): compute every Radar result date again, in
date order, after migration 20261114_005 moved G2's 16-date window to Feature 06. The per-ticker measures do not change
(refresh_feature_07 is not called); refresh_feature_07_day rewrites each date's gate row, cross-section columns and
result rows. Every date is redone because a run of days carries from one date to the next.

Run with scripts/onboarding/run_job.sh (orc-test-runner, Railway dev) or locally with DATABASE_URL set:

params.json:
  DRYRUN: {"mode": "DRYRUN", "sample_dates": 20}   the oldest sample_dates dates in one transaction, then ROLLBACK
  APPLY:  {"mode": "APPLY", "large_write": true}    every date (one commit each), then the checks

Checks (APPLY): every date has a G2 universe; the gate rows from the 16th date on equal the ones before (from there the
old window was already whole); the result rows of a date differ only while the change carries (the last differing date
is reported); the round check of backfill_job.py (rows and sums against Feature 06, no row without its cross-section).

Guards (as backfill_job.py): refuses while a stockbit-updater round is RUNNING, holds the advisory lock
feature_07_radar_backfill while it writes (the round step and the publisher leave the Radar alone meanwhile). Prints OUT
lines (JSON), VERDICT and JOB_DONE. No secret is printed. One connection, work_mem 64 MB, no parallel workers.
"""
import datetime
import json
import os
import time

import psycopg

p = json.load(open('params.json'))
mode = p.get('mode', 'DRYRUN')
assert mode in ('DRYRUN', 'APPLY'), mode
UNIVERSE = 'SELECT "Ticker" FROM public."IDX_Stock_Universe"'
LOCK = 'feature_07_radar_backfill'
LIVE_ROUND = ("SELECT count(*) FROM public.\"Monitoring_Stockbit_Update\" WHERE status = 'RUNNING' "
              "AND updated_at > now() - interval '10 minutes'")
GATE = 'SELECT trade_date, universe_n, broad_n, liquid_n, broad_cut, liquid_cut FROM public."Feature_07_Radar_Gate"'
RESULT_MD5 = """SELECT trade_date, md5(string_agg(concat_ws('|', filter_id, level, gate, ticker, status, met, cond_n, run_day,
                       left_reason, strong, sort_value, flag), ',' ORDER BY filter_id, level, gate, ticker))
                FROM public."Feature_07_Radar_Result" GROUP BY trade_date"""


def out(q, **kw):
    print('OUT ' + json.dumps({'q': q, **kw}, default=str), flush=True)


def refuse(reason):
    out('refused', reason=reason)
    print('VERDICT REFUSED', flush=True)
    raise SystemExit(1)


with psycopg.connect(os.environ['DATABASE_URL'], autocommit=True, application_name='radar-redo-days') as c:
    c.execute("SET work_mem = '64MB'")
    c.execute('SET max_parallel_workers_per_gather = 0')
    c.execute("SET statement_timeout = '30min'")
    src = c.execute("SELECT prosrc FROM pg_proc WHERE oid = to_regprocedure('public.refresh_feature_07_day(date)')").fetchone()
    if not src or 'Feature_06_Foreign_Domestic' not in src[0]:
        refuse('migration 20261114_005 is not applied (the day step still reads its window from the Radar rows)')
    if (c.execute("SELECT to_regclass('public.\"Monitoring_Stockbit_Update\"')").fetchone()[0] is not None
            and c.execute(LIVE_ROUND).fetchone()[0]):
        refuse('a stockbit-updater round is running; run the job after it ends')
    if not c.execute('SELECT pg_try_advisory_lock(hashtext(%s))', (LOCK,)).fetchone()[0]:
        refuse('a Radar backfill or redo holds the lock')
    before = {r[0]: r[1:] for r in c.execute(GATE)}
    dates = sorted(before)
    md5_before = dict(c.execute(RESULT_MD5).fetchall())
    out('plan', mode=mode, dates=len(dates), first=dates[0], last=dates[-1],
        empty_before=[d for d in dates if before[d][0] == 0])

    if mode == 'DRYRUN':
        k = int(p.get('sample_dates', 20))
        c.execute('BEGIN')
        t0 = time.monotonic()
        for d in dates[:k]:
            c.execute('SELECT public.refresh_feature_07_day(%s)', (d,))
        per = (time.monotonic() - t0) / k
        after = {r[0]: r[1:] for r in c.execute(GATE + ' WHERE trade_date = ANY(%s)', (dates[:k],))}
        out('sample', dates=[[d, before[d][0], after[d][0]] for d in dates[:k]])
        c.execute('ROLLBACK')
        out('estimate', minutes=round(per * len(dates) / 60, 1), seconds_per_date=round(per, 2))
        print('VERDICT DRYRUN_OK (rolled back)', flush=True)
        print('JOB_DONE', flush=True)
        raise SystemExit(0)

    t0 = time.monotonic()
    for i, d in enumerate(dates, 1):
        c.execute('SELECT public.refresh_feature_07_day(%s)', (d,))
        if i % 25 == 0 or i == len(dates):
            out('days', done=i, of=len(dates), seconds=round(time.monotonic() - t0, 1))
    c.execute('ANALYZE public."Feature_07_Radar_Result"')
    c.execute('ANALYZE public."Feature_07_Radar_Gate"')
    after = {r[0]: r[1:] for r in c.execute(GATE)}
    md5_after = dict(c.execute(RESULT_MD5).fetchall())
    empty = [d for d in dates if after[d][0] == 0]
    gate_changed_late = [d for d in dates[15:] if after[d] != before[d]]
    changed = [d for d in dates if md5_after.get(d) != md5_before.get(d)]
    out('gates', first_dates=[[d, before[d][0], after[d][0]] for d in dates[:16]], empty_after=empty,
        changed_from_16th=gate_changed_late)
    out('results', dates_changed=len(changed), first_changed=changed[:1], last_changed=changed[-1:])
    start = dates[0]
    regular, measured, net_equal, buy_equal, no_xs = c.execute(f"""
        WITH f AS (SELECT count(*) AS n, sum(foreign_buy_1d - foreign_sell_1d) AS net, sum(foreign_buy_1d + domestic_buy_1d) AS buy
                   FROM public."Feature_06_Foreign_Domestic" WHERE market_board = 'Regular' AND trade_date >= %(a)s AND ticker IN ({UNIVERSE})),
             m AS (SELECT count(*) AS n, sum(foreign_net_1d) AS net, sum(total_buy_1d) AS buy, count(*) FILTER (WHERE g2_eligible IS NULL) AS no_xs
                   FROM public."Feature_07_Radar_Measure" WHERE trade_date >= %(a)s AND ticker IN ({UNIVERSE}))
        SELECT f.n, m.n, f.net IS NOT DISTINCT FROM m.net, f.buy IS NOT DISTINCT FROM m.buy, m.no_xs FROM f, m""",
                                                                {'a': start}).fetchone()
    out('reconcile', regular_rows=regular, measure_rows=measured, gate_rows=len(after), net_equal=net_equal,
        buy_equal=buy_equal, rows_without_cross_section=no_xs)
    for d in p.get('check_dates', []):
        hits = c.execute("""SELECT filter_id, gate, count(*) FROM public."Feature_07_Radar_Result"
                            WHERE trade_date = %s AND status = 'hit' AND level = 'standard' GROUP BY 1, 2 ORDER BY 1, 2""",
                         (d,)).fetchall()
        out('check_date', date=d, gate=after.get(datetime.date.fromisoformat(d)), standard_hits=[list(h) for h in hits])
    ok = (not empty and not gate_changed_late and regular == measured and net_equal and buy_equal and not no_xs
          and len(after) == len(dates))
    out('done', seconds=round(time.monotonic() - t0, 1))
    print('VERDICT ' + ('APPLY_OK' if ok else 'APPLY_MISMATCH'), flush=True)
    print('JOB_DONE', flush=True)
    raise SystemExit(0 if ok else 1)
