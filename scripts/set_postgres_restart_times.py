#!/usr/bin/env python3
"""Set the times of the automatic Postgres restart (EXEC-PG-RESTART-CRON, user 2026-11-03: "Pagi dan sore, buat jamnya
bisa variable yang bisa di atur di cron ya").

    python3 scripts/set_postgres_restart_times.py --wib 09:45,20:45            # check only
    python3 scripts/set_postgres_restart_times.py --wib 09:45,20:45 --apply    # set, upload, read back

The times live in two places that must agree: the variable PG_RESTART_TIMES_WIB of postgres-memory-cron (which run is
a scheduled one) and the service's cronSchedule (when Railway starts it), cron_for(times) as in
scripts/restart_postgres.py. Steps:
  1. every time is checked against the live crons of the other services (no run within 45 minutes, the same margin as
     the restart's own guard) and the B6 windows (07:00-08:45 and 19:00-20:20 WIB); a clash refuses;
  2. `.railway/railway.ts` gets the new cronSchedule; `railway config plan` must show exactly that one change;
  3. with --apply: the variable (--skip-deploys), `railway config apply --yes`, then a new upload
     (apps/postgres-memory-cron/deploy.sh): a variable reaches a cron service only through a new deployment, and a
     redeploy keeps the old one (ERRORS M229). Then the cron and the variable are read back.
Ask the user first; record the change in RAILWAY_CHANGELOG.md and EXEC.md. Needs RAILWAY_TOKEN; prints no secret.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import restart_postgres as rp  # noqa: E402

SERVICE = 'postgres-memory-cron'
RAILWAY_TS = ROOT / '.railway/railway.ts'
BLOCK = re.compile(r'(const postgresMemoryCron = service\("postgres-memory-cron", \{.*?cronSchedule: ")([^"]*)(")',
                   re.S)
CLI_ENV = dict(os.environ, _=shutil.which('railway') or 'railway')
MARGIN = 45


def clashes(times, crons):
    """Every clash of a listed WIB time with B6 or another service's cron (checked on a sample day)."""
    out = []
    day = datetime(2026, 11, 4, tzinfo=timezone.utc)          # a Wednesday: weekday crons fire
    for h, m in times:
        t = day + timedelta(hours=(h - 7) % 24, minutes=m)
        window = rp.in_b6(t)
        if window:
            out.append(f'{h:02d}:{m:02d} WIB is inside the B6 window {window} UTC')
        for due in rp.crons_due(crons, t, MARGIN, skip=SERVICE):
            out.append(f'{h:02d}:{m:02d} WIB: {due}')
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--wib', required=True, help='restart times in WIB, e.g. 09:45,20:45')
    p.add_argument('--apply', action='store_true')
    args = p.parse_args()
    times = rp.run_times(args.wib)
    if not 1 <= len(times) <= 8:
        raise SystemExit('refused: give 1 to 8 times')
    value = ','.join(f'{h:02d}:{m:02d}' for h, m in sorted(times))
    cron = rp.cron_for(times)
    services = rp.services_by_name()
    crons = rp.cron_schedules(services)
    found = clashes(times, crons)
    extra = len(rp.cron_parts(times)[0]) * len(rp.cron_parts(times)[1]) - len(set(times))
    print(json.dumps({'times_wib': value, 'cron_utc': cron, 'current_cron': crons.get(SERVICE),
                      'extra_ticks_doing_nothing': extra, 'clashes': found or 'none'}))
    if found:
        raise SystemExit('refused: move the times away from the clashes above')
    text = RAILWAY_TS.read_text()
    m = BLOCK.search(text)
    if not m:
        raise SystemExit('refused: the postgres-memory-cron cronSchedule was not found in .railway/railway.ts')
    if m.group(2) != cron:
        RAILWAY_TS.write_text(text[:m.start(2)] + cron + text[m.end(2):])
    shown = subprocess.run(['railway', 'config', 'plan'], cwd=ROOT, capture_output=True, text=True, env=CLI_ENV).stdout
    up_to_date = 'up to date' in shown
    one_change = '0 to add, 1 to change, 0 to destroy' in shown and 'deploy.cronSchedule' in shown \
        and f'→ "{cron}")' in shown and 'postgres-memory-cron' in shown
    print(json.dumps({'plan_ok': up_to_date or one_change, 'cron_already_live': up_to_date}))
    if not (up_to_date or one_change):
        print(shown[-1500:])
        raise SystemExit('refused: the plan is not exactly the cronSchedule change')
    if not args.apply:
        return 0
    base = ['-p', rp.PID, '-e', rp.ENV, '-s', SERVICE]
    subprocess.run(['railway', 'variable', 'set', *base, '--skip-deploys', f'PG_RESTART_TIMES_WIB={value}'],
                   check=True, capture_output=True, text=True)
    if not up_to_date:
        subprocess.run(['railway', 'config', 'apply', '--yes'], cwd=ROOT, check=True, capture_output=True, text=True,
                       env=CLI_ENV)
    subprocess.run(['bash', 'apps/postgres-memory-cron/deploy.sh'], cwd=ROOT, check=True, capture_output=True,
                   text=True)
    status, started = None, time.monotonic()
    while time.monotonic() - started < 600:
        time.sleep(15)
        dep = rp.gql('query($s:String!,$e:String!){deployments(first:1,input:{serviceId:$s,environmentId:$e})'
                     '{edges{node{id status}}}}', {'s': services[SERVICE], 'e': rp.ENV})['deployments']['edges'][0]['node']
        status = dep['status']
        if status in ('SUCCESS', 'FAILED', 'CRASHED'):
            break
    live_cron = rp.cron_schedules({SERVICE: services[SERVICE]}).get(SERVICE)
    live_var = json.loads(subprocess.run(['railway', 'variable', 'list', *base, '--json'], capture_output=True,
                                         text=True).stdout).get('PG_RESTART_TIMES_WIB')
    print(json.dumps({'deployment': dep['id'], 'status': status, 'cron_live': live_cron, 'times_live': live_var}))
    return 0 if status == 'SUCCESS' and live_cron == cron and live_var == value else 1


if __name__ == '__main__':
    raise SystemExit(main())
