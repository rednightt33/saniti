"""EXEC.md option A rollback step 3 (the live checker after the switch-on, F5): when a site is taken down, end its open
Backtest jobs, so the shared backtest-worker slot and its owners (one running job per owner on either site) are not held
by a loop that no longer runs: QUEUED ends CANCELLED, RUNNING ends FAILED WORKER_LOST (app/backtest.py reap's own end,
which only the site's own loop runs). params.json: {"site": "live", "apply": false}; without apply it counts and
changes nothing (DRYRUN: the same statements in one transaction, rolled back). Prints counts only.
    scripts/onboarding/run_job.sh scripts/onboarding/end_site_backtests_job.py params.json log.txt
"""
import json
import os

import psycopg
from psycopg.types.json import Jsonb

p = json.load(open("params.json"))
site, apply = p["site"], p.get("apply") is True
if site not in ("live", "beta"):
    raise SystemExit("site is live or beta")
with psycopg.connect(os.environ["DATABASE_URL"]) as c:
    before = dict(c.execute("""SELECT state, count(*) FROM edge_bff.backtest_jobs WHERE site = %s
        AND state IN ('QUEUED', 'RUNNING') GROUP BY state""", (site,)).fetchall())
    cancelled = c.execute("""UPDATE edge_bff.backtest_jobs SET state = 'CANCELLED', finished_at = now(), updated_at = now()
        WHERE site = %s AND state = 'QUEUED'""", (site,)).rowcount
    failed = c.execute("""UPDATE edge_bff.backtest_jobs SET state = 'FAILED', error = %s, lease_token = NULL,
        lease_expires_at = NULL, finished_at = now(), updated_at = now() WHERE site = %s AND state = 'RUNNING'""",
                       (Jsonb({"code": "WORKER_LOST"}), site)).rowcount
    if not apply:
        c.rollback()
print("OUT", json.dumps({"site": site, "mode": "APPLY" if apply else "DRYRUN", "before": before,
                         "cancelled": cancelled, "failed": failed}))
print("JOB_DONE")
