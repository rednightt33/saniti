"""EXEC-RADAR R3: first fill of the Radar tables (Feature 07) after migration 20261114_001.

Run with scripts/onboarding/run_job.sh (orc-test-runner, Railway dev) or locally with DATABASE_URL set:

params.json:
  {"mode": "DRYRUN" | "APPLY", "result_sessions": 250, "large_write": true,
   "sample_tickers": 20, "sample_dates": 3, "check_dates": ["2026-11-03", "2026-11-09"]}

  result_sessions  the result history D4 asks for (user 2026-11-14 "D4 ok": 250 sessions, date picker of 20); the
                   measures start at the market date that many Regular sessions back, and refresh_feature_07 reads the
                   400 sessions before it
  DRYRUN           sample_tickers tickers and the last sample_dates dates inside one transaction, timed, then ROLLBACK:
                   nothing is kept; the timings estimate the APPLY
  APPLY            every universe ticker (one commit each), then every date in order (one commit each; a run of days
                   reads the date before), then the checks
  large_write      run_job.sh restarts Postgres afterwards (AGENTS.md "Postgres memory after large updates")

Prints OUT lines (JSON), VERDICT and JOB_DONE. No secret is printed. Heavy reads: work_mem 64 MB, no parallel workers,
one connection (AGENTS.md).
"""
import json
import os
import time

import psycopg

p = json.load(open('params.json'))
mode = p.get('mode', 'DRYRUN')
assert mode in ('DRYRUN', 'APPLY'), mode
N = int(p.get('result_sessions', 250))
UNIVERSE = 'SELECT "Ticker" FROM public."IDX_Stock_Universe"'


def out(q, **kw):
    print('OUT ' + json.dumps({'q': q, **kw}, default=str), flush=True)


def session(c):
    c.execute("SET work_mem = '64MB'")
    c.execute('SET max_parallel_workers_per_gather = 0')
    c.execute("SET statement_timeout = '30min'")


with psycopg.connect(os.environ['DATABASE_URL'], autocommit=True, application_name='radar-backfill') as c:
    session(c)
    if c.execute("SELECT to_regclass('public.\"Feature_07_Radar_Measure\"')").fetchone()[0] is None:
        out('refused', reason='migration 20261114_001 is not applied')
        print('VERDICT REFUSED', flush=True)
        raise SystemExit(1)
    dates = [r[0] for r in c.execute("""SELECT DISTINCT trade_date FROM public."Feature_06_Foreign_Domestic"
                                        WHERE market_board = 'Regular' ORDER BY 1 DESC LIMIT %s""", (N,))]
    start, newest = min(dates), max(dates)
    tickers = [r[0] for r in c.execute(f"""SELECT DISTINCT ticker FROM public."Feature_06_Foreign_Domestic"
                                           WHERE market_board = 'Regular' AND trade_date >= %s AND ticker IN ({UNIVERSE})
                                           ORDER BY 1""", (start,))]
    existing = c.execute('SELECT count(*) FROM public."Feature_07_Radar_Measure"').fetchone()[0]
    out('plan', mode=mode, start=start, newest=newest, result_sessions=len(dates), tickers=len(tickers),
        existing_measure_rows=existing)

    if mode == 'DRYRUN':
        k = int(p.get('sample_tickers', 20))
        pick = tickers[:: max(1, len(tickers) // k)][:k]
        c.execute('BEGIN')
        t0 = time.monotonic()
        rows = sum(c.execute('SELECT public.refresh_feature_07(%s, %s)', (t, start)).fetchone()[0] for t in pick)
        per_ticker = (time.monotonic() - t0) / max(1, len(pick))
        out('sample_tickers', tickers=len(pick), rows=rows, seconds_per_ticker=round(per_ticker, 2))
        # the sample dates need every ticker of the date: the rest are computed from 16 dates before them (G2 counts
        # the sessions of the last 16 dates)
        k_days = int(p.get('sample_dates', 3))
        days = sorted(dates)[-k_days:]
        tail_from = sorted(dates)[-(k_days + 16)]
        t1 = time.monotonic()
        for t in tickers:
            if t not in pick:
                c.execute('SELECT public.refresh_feature_07(%s, %s)', (t, tail_from))
        tail_s = time.monotonic() - t1
        t2 = time.monotonic()
        for d in days:
            n = c.execute('SELECT public.refresh_feature_07_day(%s)', (d,)).fetchone()[0]
            g = c.execute('SELECT universe_n, broad_n, liquid_n, broad_cut, liquid_cut FROM public."Feature_07_Radar_Gate" WHERE trade_date = %s', (d,)).fetchone()
            out('sample_day', date=d, result_rows=n, universe=g[0], broad=g[1], liquid=g[2], broad_cut=g[3], liquid_cut=g[4])
        per_day = (time.monotonic() - t2) / len(days)
        c.execute('ROLLBACK')
        out('estimate', tickers_minutes=round(per_ticker * len(tickers) / 60, 1),
            days_minutes=round(per_day * len(dates) / 60, 1), tail_tickers_seconds=round(tail_s, 1))
        print('VERDICT DRYRUN_OK (rolled back)', flush=True)
        print('JOB_DONE', flush=True)
        raise SystemExit(0)

    t0 = time.monotonic()
    rows = 0
    for i, t in enumerate(tickers, 1):
        rows += c.execute('SELECT public.refresh_feature_07(%s, %s)', (t, start)).fetchone()[0]
        if i % 100 == 0 or i == len(tickers):
            out('tickers', done=i, of=len(tickers), rows=rows, seconds=round(time.monotonic() - t0, 1))
    c.execute('ANALYZE public."Feature_07_Radar_Measure"')
    t1 = time.monotonic()
    for i, d in enumerate(sorted(dates), 1):
        c.execute('SELECT public.refresh_feature_07_day(%s)', (d,))
        if i % 25 == 0 or i == len(dates):
            out('days', done=i, of=len(dates), seconds=round(time.monotonic() - t1, 1))
    c.execute('ANALYZE public."Feature_07_Radar_Result"')
    c.execute('ANALYZE public."Feature_07_Radar_Gate"')
    regular, measured = c.execute(f"""SELECT
        (SELECT count(*) FROM public."Feature_06_Foreign_Domestic" WHERE market_board = 'Regular' AND trade_date >= %(a)s AND ticker IN ({UNIVERSE})),
        (SELECT count(*) FROM public."Feature_07_Radar_Measure" WHERE trade_date >= %(a)s AND ticker IN ({UNIVERSE}))""",
                                  {'a': start}).fetchone()
    gates = c.execute('SELECT count(*) FROM public."Feature_07_Radar_Gate" WHERE trade_date >= %s', (start,)).fetchone()[0]
    out('reconcile', regular_rows=regular, measure_rows=measured, gate_rows=gates, dates=len(dates))
    for d in p.get('check_dates', []):
        g = c.execute('SELECT universe_n, broad_n, liquid_n, broad_cut, liquid_cut FROM public."Feature_07_Radar_Gate" WHERE trade_date = %s', (d,)).fetchone()
        hits = c.execute("""SELECT filter_id, level, gate, count(*) FROM public."Feature_07_Radar_Result"
                            WHERE trade_date = %s AND status = 'hit' AND level = 'standard' GROUP BY 1, 2, 3 ORDER BY 1, 3""",
                         (d,)).fetchall()
        out('check_date', date=d, gate=g, standard_hits=[list(h) for h in hits])
    ok = regular == measured and gates == len(dates)
    out('done', seconds=round(time.monotonic() - t0, 1), measure_rows=measured)
    print('VERDICT ' + ('APPLY_OK' if ok else 'APPLY_MISMATCH'), flush=True)
    print('JOB_DONE', flush=True)
    raise SystemExit(0 if ok else 1)
