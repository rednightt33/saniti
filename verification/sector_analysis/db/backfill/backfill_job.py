"""EXEC-SECTOR-ANALYSIS S1: the first fill of Feature_08_Group_Daily after migration 20261126_001 (not run yet).

Run with scripts/onboarding/run_job.sh (orc-test-runner, Railway dev), the validator staged beside it:

  scripts/onboarding/run_job.sh verification/sector_analysis/db/backfill/backfill_job.py \\
      verification/sector_analysis/db/backfill/params_dryrun.json <log> verification/sector_analysis/db/validate_feature_08.py

params.json:
  DRYRUN: {"mode": "DRYRUN", "from": "2021-01-25", "sample_dates": 5}
  APPLY:  {"mode": "APPLY", "from": "2021-01-25", "large_write": true, "check_dates": [...]}

  from          the first market date (the sector indexes' first date, CONTRACT.md section 2); every market date of the
                MARKET entity from it to the newest final one is computed, one date per statement, in date order (the
                index level is chain-linked)
  DRYRUN        the first sample_dates dates inside one transaction, timed and checked by the independent validator,
                then ROLLBACK: nothing is kept; the timings estimate the APPLY
  APPLY         every date (one commit each), then once more any date that became final meanwhile, ANALYZE, and the
                checks: one row per date and group, MARKET breadth equal to the Overview's BREADTH_SQL on a spread of
                dates, the validator on check_dates (and the first, a middle and the last date), no negative level
  large_write   APPLY only: run_job.sh restarts Postgres afterwards (AGENTS.md "Postgres memory after large updates":
                about 1,400 dates of prices and Feature 04 are read)

Guards: the job holds the advisory lock feature_08_group_backfill while it writes, so feature-04-worker waits
(Feature08Refresher) and the publisher does not publish half-filled tables (apps/terminal-publisher/sector.py busy);
it refuses while another holder has the lock, and when the migration is not applied.

Prints OUT lines (JSON), VERDICT and JOB_DONE. No secret is printed. Heavy reads: work_mem 64 MB, no parallel workers,
one connection (AGENTS.md).
"""
import json
import os
import time

import psycopg

import validate_feature_08

p = json.load(open('params.json'))
mode = p.get('mode', 'DRYRUN')
assert mode in ('DRYRUN', 'APPLY'), mode
FIRST = p.get('from', '2021-01-25')
LOCK = 'feature_08_group_backfill'               # apps/terminal-publisher/sector.py BACKFILL_LOCK, worker.py
F08 = 'public."Feature_08_Group_Daily"'
DATES = ("SELECT p.date FROM public.\"Price_Stock_Indonesia_IDX\" p WHERE p.ticker = (SELECT ticker FROM "
         "public.\"Feature_Index_Entity\" WHERE entity_kind = 'MARKET') AND p.timeframe = 'Daily' AND p.is_final "
         'AND p.date >= %s ORDER BY 1')
# the Overview's market breadth (apps/terminal-publisher/overview.py BREADTH_SQL), one date
BREADTH = ('SELECT count(t.ema_50), count(*) FILTER (WHERE t.close > t.ema_50), count(t.ema_200), '
           'count(*) FILTER (WHERE t.close > t.ema_200) FROM public."Feature_04_Technical_Indicator" AS t '
           "WHERE t.trade_date = %s AND t.timeframe = 'Daily' AND t.asset_type = 'equity' "
           'AND t.ticker IN (SELECT "Ticker" FROM public."IDX_Stock_Universe" WHERE "Security Type" = \'stock\')')


def out(q, **kw):
    print('OUT ' + json.dumps({'q': q, **kw}, default=str), flush=True)


def refuse(reason):
    out('refused', reason=reason)
    print('VERDICT REFUSED', flush=True)
    print('JOB_DONE', flush=True)
    raise SystemExit(1)


def session(c):
    c.execute("SET work_mem = '64MB'")
    c.execute('SET max_parallel_workers_per_gather = 0')
    c.execute("SET statement_timeout = '5min'")


with psycopg.connect(os.environ['DATABASE_URL'], autocommit=True, application_name='feature-08-backfill') as c:
    session(c)
    if c.execute("SELECT to_regprocedure('public.refresh_feature_08_day(date)')").fetchone()[0] is None:
        refuse('migration 20261126_001 is not applied')
    if not c.execute('SELECT pg_try_advisory_lock(hashtext(%s))', (LOCK,)).fetchone()[0]:
        refuse('another Feature 08 backfill holds the lock')
    dates = [r[0] for r in c.execute(DATES, (FIRST,))]
    groups = c.execute("""SELECT 1 + (SELECT count(*) FROM public."Feature_Index_Entity" WHERE entity_kind = 'SECTOR')
                          + (SELECT count(DISTINCT "Industry") FROM public."IDX_Stock_Universe"
                             WHERE "Security Type" = 'stock' AND "Industry" <> 'Undefined')""").fetchone()[0]
    existing = c.execute(f'SELECT count(*), min(date), max(date) FROM {F08}').fetchone()
    out('plan', mode=mode, first=dates[0] if dates else None, last=dates[-1] if dates else None, dates=len(dates),
        groups=groups, existing_rows=existing[0], existing_from=existing[1], existing_to=existing[2])
    if not dates:
        refuse(f'no market date from {FIRST}')

    if mode == 'DRYRUN':
        k = int(p.get('sample_dates', 5))
        c.execute('BEGIN')
        times, diffs = [], []
        if existing[0]:
            # the sample starts at FIRST: rows of later dates in the table would not change its chain, but a row before
            # FIRST would; the dry run only reads what the apply would write from FIRST on
            c.execute(f'DELETE FROM {F08} WHERE date >= %s', (dates[0],))
        for d in dates[:k]:
            t0 = time.monotonic()
            n = c.execute('SELECT public.refresh_feature_08_day(%s)', (d,)).fetchone()[0]
            times.append(time.monotonic() - t0)
            dd = validate_feature_08.validate(c, d)
            diffs += dd
            out('sample_date', date=d, rows=n, seconds=round(times[-1], 2), differences=len(dd), first=dd[:3])
        c.execute('ROLLBACK')
        per = sum(times) / len(times)
        out('estimate', dates=len(dates), seconds_per_date=round(per, 3), apply_minutes=round(per * len(dates) / 60, 1))
        print('VERDICT ' + ('DRYRUN_OK (rolled back)' if not diffs else f'DRYRUN_DIFF {len(diffs)} (rolled back)'), flush=True)
        print('JOB_DONE', flush=True)
        raise SystemExit(0 if not diffs else 1)

    t0, rows, done = time.monotonic(), 0, []
    pending = list(dates)
    while pending:
        for i, d in enumerate(pending, 1):
            rows += c.execute('SELECT public.refresh_feature_08_day(%s)', (d,)).fetchone()[0]
            done.append(d)
            if len(done) % 100 == 0 or i == len(pending):
                out('dates', done=len(done), of=len(dates), rows=rows, seconds=round(time.monotonic() - t0, 1))
        # a date that became final while the job ran (the worker waits for the lock): written too, in order
        pending = [r[0] for r in c.execute(DATES, (FIRST,)) if r[0] > done[-1]]
        dates += pending
    c.execute(f'ANALYZE {F08}')
    per_date = c.execute(f"""SELECT count(*) FILTER (WHERE n <> %s), count(*) FROM
                             (SELECT date, count(*) AS n FROM {F08} WHERE date >= %s GROUP BY date) x""",
                         (groups, dates[0])).fetchone()
    spread = sorted(set(dates[::max(1, len(dates) // 12)] + [dates[-1]]))
    breadth_bad = []
    for d in spread:
        m = c.execute(f"SELECT n_ema50, above_ema50, n_ema200, above_ema200 FROM {F08} WHERE date = %s AND group_kind = 'MARKET'",
                      (d,)).fetchone()
        b = c.execute(BREADTH, (d,)).fetchone()
        if tuple(m or ()) != tuple(b):
            breadth_bad.append((d, m, b))
    checks = sorted(set(p.get('check_dates', [])) | {str(dates[0]), str(dates[len(dates) // 2]), str(dates[-1])})
    diffs = []
    for d in checks:
        dd = validate_feature_08.validate(c, d)
        diffs += dd
        out('validate', date=d, differences=len(dd), first=dd[:3])
    neg, nulls = c.execute(f"""SELECT count(*) FILTER (WHERE index_level < 0), count(*) FILTER (WHERE index_level IS NULL)
                               FROM {F08} WHERE date >= %s""", (dates[0],)).fetchone()
    out('reconcile', dates_with_another_group_count=per_date[0], dates=per_date[1], breadth_dates=len(spread),
        breadth_differences=breadth_bad[:3], validated_dates=len(checks), differences=len(diffs),
        negative_levels=neg, null_levels=nulls)
    ok = per_date == (0, len(dates)) and not breadth_bad and not diffs and not neg
    out('done', seconds=round(time.monotonic() - t0, 1), rows=rows, dates=len(dates))
    print('VERDICT ' + ('APPLY_OK' if ok else 'APPLY_MISMATCH'), flush=True)
    print('JOB_DONE', flush=True)
    raise SystemExit(0 if ok else 1)
