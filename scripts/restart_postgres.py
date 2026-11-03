#!/usr/bin/env python3
"""Planned Postgres restart after a large backfill (user decision 2026-11-01, ERRORS M319: "Restart terencana Postgres
sesudah setiap backfill besar. Memori langsung bersih, dengan jeda sekitar satu menit.").

A large write leaves Linux page cache that Railway bills as Postgres memory until it is reclaimed (up to the 4 GB limit,
for hours). A restart frees it at once, at the cost of about one minute without the database. This script restarts
only when it is worth it and safe:
  1. memory: the newest 5-minute Postgres memory (Railway metrics) is above --min-gb (default 0.8; the usual idle level is
     0.1-0.6 GB, so more means a job's page cache, under the 4 GB limit of EXEC-PG-MEMORY). Below it there is nothing to free, so no restart;
  2. no cron is due: every service's cron schedule is read from Railway (not listed here) and no run may start within
     --margin minutes (default 45) of now; the user's B6 windows (00:00-01:45 and 12:00-13:20 UTC) are refused too;
  3. no client is working: no `active` statement in pg_stat_activity other than this check (through pgweb, read-only);
  4. restart the newest SUCCESS Postgres deployment (GraphQL deploymentRestart), wait until Postgres answers with a new
     start time, then check edge-bff /ready.
--check (default) runs 1-3 and prints the verdict without restarting; --apply restarts when 1-3 pass; --force skips
1 and 3 (never 2). Credentials: RAILWAY_TOKEN (project token) in the environment; nothing secret is printed.

  python3 scripts/restart_postgres.py [--apply] [--force] [--min-gb 1.5] [--margin 45]
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'verification/terminal_api'))
import pgq  # noqa: E402  (read-only queries through pgweb)

PID, ENV = '8aef1702-030b-49cb-9df7-5ac2e0a42691', '4d3e5af2-302b-4a2e-84e2-7d7476d6ff49'   # PROJECT_CONTEXT.md
B6 = [((0, 0), (1, 45)), ((12, 0), (13, 20))]       # user rule B6: no maintenance in these UTC windows


def gql(query, variables):
    req = urllib.request.Request('https://backboard.railway.com/graphql/v2',
                                 json.dumps({'query': query, 'variables': variables}).encode(),
                                 {'Content-Type': 'application/json', 'Project-Access-Token': os.environ['RAILWAY_TOKEN'],
                                  'User-Agent': 'saniti-restart-postgres/1'})
    body = json.loads(urllib.request.urlopen(req, timeout=60).read())
    if body.get('errors'):
        raise SystemExit('Railway refused: ' + '; '.join(str(e.get('message'))[:200] for e in body['errors']))
    return body['data']


def cron_matches(expr, t):
    """True when the 5-field cron expression fires at minute t (UTC; lists, ranges, steps and *)."""
    fields = expr.split()
    if len(fields) != 5:
        return False
    vals = [t.minute, t.hour, t.day, t.month, t.isoweekday() % 7]

    def ok(field, v):
        for part in field.split(','):
            step = 1
            if '/' in part:
                part, s = part.split('/')
                step = int(s)
            if part == '*':
                lo, hi = 0, 59
            elif '-' in part:
                lo, hi = map(int, part.split('-'))
            else:
                lo = hi = int(part)
            if lo <= v <= hi and (v - lo) % step == 0:
                return True
        return False
    return all(ok(f, v) for f, v in zip(fields, vals))


def checks(args):
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    services = gql('query($id:String!){project(id:$id){services{edges{node{id name}}}}}', {'id': PID})
    services = {e['node']['name']: e['node']['id'] for e in services['project']['services']['edges']}
    out = {'now': now.isoformat(), 'refusals': []}
    # 1. memory
    m = gql('query($p:String!,$e:String!,$s:String!,$d:DateTime!){metrics(projectId:$p,environmentId:$e,serviceId:$s,'
            'startDate:$d,measurements:[MEMORY_USAGE_GB],sampleRateSeconds:300){values{ts value}}}',
            {'p': PID, 'e': ENV, 's': services['Postgres'], 'd': (now - timedelta(minutes=30)).isoformat()})
    # EXEC-PG-MEMORY (2026-11-03): the newest 5-minute value; an hourly average still showed 2.6 GB right after the limit
    # fell to 1 GB
    vals = [v for x in m['metrics'] for v in x['values']]
    mem = max(vals, key=lambda v: v['ts'])['value'] if vals else None
    out['postgres_memory_gb'] = mem
    if not args.force and (mem is None or mem < args.min_gb):
        out['refusals'].append(f'memory {mem} GB is below {args.min_gb} GB: nothing to free')
    # 2. crons and B6
    for (h1, m1), (h2, m2) in B6:
        if (h1, m1) <= (now.hour, now.minute) <= (h2, m2):
            out['refusals'].append(f'inside the B6 window {h1:02d}:{m1:02d}-{h2:02d}:{m2:02d} UTC')
    due = []
    for name, sid in services.items():
        si = gql('query($s:String!,$e:String!){serviceInstance(serviceId:$s,environmentId:$e){cronSchedule}}',
                 {'s': sid, 'e': ENV})['serviceInstance']
        cron = (si or {}).get('cronSchedule')
        if not cron:
            continue
        for k in range(-args.margin, args.margin + 1):
            t = now + timedelta(minutes=k)
            if cron_matches(cron, t):
                due.append(f'{name} ({cron}) at {t:%H:%M} UTC')
                break
    if due:
        out['refusals'].append('a cron runs within the margin: ' + '; '.join(due))
    # 3. client work
    r = pgq.q("SELECT count(*) FROM pg_stat_activity WHERE state = 'active' AND pid <> pg_backend_pid() "
              "AND backend_type = 'client backend'")
    active = r['rows'][0][0] if 'rows' in r else None
    out['active_statements'] = active
    if not args.force and active:
        out['refusals'].append(f'{active} statements are running')
    return out, services


def restart(services):
    deps = gql('query($s:String!,$e:String!){deployments(first:5,input:{serviceId:$s,environmentId:$e}){edges{node{id status}}}}',
               {'s': services['Postgres'], 'e': ENV})
    dep = next(e['node']['id'] for e in deps['deployments']['edges'] if e['node']['status'] == 'SUCCESS')
    before = pgq.q('SELECT pg_postmaster_start_time()::text')['rows'][0][0]
    gql('mutation($id:String!){deploymentRestart(id:$id)}', {'id': dep})
    started = time.monotonic()
    while time.monotonic() - started < 600:
        time.sleep(10)
        r = pgq.q('SELECT pg_postmaster_start_time()::text')
        if 'rows' in r and r['rows'][0][0] != before:
            break
    else:
        raise SystemExit('Postgres did not come back within 10 minutes; check the Railway dashboard')
    after = r['rows'][0][0]
    domain = json.loads(os.popen('railway variables --service edge-bff --environment dev --json').read())['RAILWAY_PUBLIC_DOMAIN']
    try:
        ready = urllib.request.urlopen(f'https://{domain}/ready', timeout=30).status
    except urllib.error.HTTPError as e:
        ready = e.code
    return {'deployment': dep, 'start_before': before, 'start_after': after,
            'seconds': round(time.monotonic() - started), 'edge_bff_ready': ready}


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--apply', action='store_true')
    p.add_argument('--force', action='store_true', help='skip the memory and client checks (never the cron check)')
    # EXEC-PG-MEMORY (user 2026-11-03): idle is 0.1-0.6 GB, so 0.8 GB means a large job's page cache is left; the limit
    # went back to 4 GB the same day and the threshold stays (it still separates idle from cache)
    p.add_argument('--min-gb', type=float, default=0.8)
    p.add_argument('--margin', type=int, default=45)
    args = p.parse_args()
    out, services = checks(args)
    hard = [x for x in out['refusals'] if x.startswith(('a cron', 'inside the B6'))]
    soft = [x for x in out['refusals'] if x not in hard]
    out['verdict'] = 'REFUSED' if hard or (soft and not args.force) else ('READY' if not args.apply else 'RESTARTING')
    print(json.dumps(out, default=str))
    if args.apply and out['verdict'] == 'RESTARTING':
        print(json.dumps(restart(services), default=str))
    return 0 if out['verdict'] != 'REFUSED' else 3


if __name__ == '__main__':
    raise SystemExit(main())
