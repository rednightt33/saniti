"""EXEC-INDEX-INCREMENTAL (2), option 1 (user 2026-11-09 "Opsi 1 dl untuk tes setela putaran ini selesai"): the full
and the bounded refresh plan of apps/stockbit-updater/refresh.py on the live database, read only, once. Prints both
plans, the bounded plan's candidates and why the full plan would be required, and EQUAL or DIFFERENT. Also the
bounded plan over every date of the last 60 days (a wider candidate set): it must equal the full plan restricted to
those dates. Nothing is written (read-only session)."""
import json
import os
import sys
import time

import psycopg

sys.path.insert(0, 'updater')
import refresh  # noqa: E402


def out(q, **kw):
    print('OUT ' + json.dumps({'q': q, **kw}, default=str), flush=True)


for i in range(30):  # the private network name can need a few seconds after start
    try:
        psycopg.connect(os.environ['DATABASE_URL'], connect_timeout=10).close()
        break
    except psycopg.OperationalError:
        time.sleep(5)

with psycopg.connect(os.environ['DATABASE_URL'], options='-c default_transaction_read_only=on') as c:
    c.execute("SET statement_timeout = '30min'")
    c.execute('SET max_parallel_workers_per_gather = 0')
    t0 = time.monotonic()
    candidates, why = refresh.bounded_candidates(c)
    out('state', candidates=candidates, why_full=why, seconds=round(time.monotonic() - t0, 1))
    t0 = time.monotonic()
    full = refresh.plan(c.execute(refresh.PER_DATE_FULL).fetchall())
    out('full_plan', changed=full[0], index=full[1], seconds=round(time.monotonic() - t0, 1))
    verdict = []
    if candidates is not None:
        t0 = time.monotonic()
        bounded = refresh.plan(c.execute(refresh.PER_DATE_BOUNDED, {'dates': candidates}).fetchall() if candidates else [])
        out('bounded_plan', changed=bounded[0], index=bounded[1], seconds=round(time.monotonic() - t0, 1))
        verdict.append(bounded == full)
    wide = [r[0] for r in c.execute('SELECT DISTINCT "Date" FROM public."IDX_Broker_Summary" '
                                    "WHERE \"Date\" >= current_date - 60 ORDER BY 1").fetchall()]
    t0 = time.monotonic()
    wide_plan = refresh.plan(c.execute(refresh.PER_DATE_BOUNDED, {'dates': wide}).fetchall())
    wide_full = ([d for d in full[0] if d in wide], [d for d in full[1] if d in wide])
    out('wide_bounded_plan', dates=len(wide), first=wide[0] if wide else None, changed=wide_plan[0], index=wide_plan[1],
        full_restricted=wide_full, seconds=round(time.monotonic() - t0, 1))
    verdict.append(wide_plan == wide_full)
    out('verdict', verdict='EQUAL' if verdict and all(verdict) else 'DIFFERENT', checks=verdict)
print('JOB_DONE PLAN_COMPARE', flush=True)
