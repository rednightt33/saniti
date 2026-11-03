#!/usr/bin/env python3
"""Set the Postgres container memory limit (EXEC-PG-MEMORY, user 2026-11-03: "Kembalikan ke 4GB ya sekarang tapi keep
existing path in case kita mau adjust memory Postgres in the future supaya lebih gampang").

    python3 scripts/set_postgres_memory.py --gb 4            # check only: guards, the railway.ts edit and the plan
    python3 scripts/set_postgres_memory.py --gb 4 --apply    # the same, then railway config apply and the read-back

Steps:
  1. guards: the hard guards of scripts/restart_postgres.py (no cron within 45 minutes, outside the B6 windows) and no
     running client statement; a limit change restarts Postgres, so the same rules apply. Check also that no user run is
     active (AGENTS.md "Postgres memory after large updates", ERRORS M340) before --apply;
  2. edit `.railway/railway.ts` (`Postgres.deploy.limitOverride.containers.memoryBytes`, decimal bytes: 4 GB is
     4000000000);
  3. `railway config plan` must show exactly that one change, else nothing is applied;
  4. with --apply: `railway config apply --yes`, then wait for the new Postgres deployment to reach SUCCESS, read the
     limit back (serviceInstanceLimits), Postgres's new start time and edge-bff /ready.
Record the change in RAILWAY_CHANGELOG.md and the user's words in EXEC.md. Needs RAILWAY_TOKEN; prints no secret.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'verification/terminal_api'))
import restart_postgres as rp  # noqa: E402  (guards, Railway GraphQL)
import pgq  # noqa: E402

RAILWAY_TS = ROOT / '.railway/railway.ts'
LINE = re.compile(r'(Postgres\.deploy = \{ limitOverride: \{ containers: \{ memoryBytes: )(\d+)( \} \} \};)')


# the Railway SDK reads the CLI version through $_ (the shell's last command): point it at the railway binary
CLI_ENV = dict(os.environ, _=shutil.which('railway') or 'railway')


def plan() -> str:
    return subprocess.run(['railway', 'config', 'plan'], cwd=ROOT, capture_output=True, text=True, env=CLI_ENV).stdout


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--gb', type=float, required=True, help='new limit in GB (decimal: 1 GB = 1,000,000,000 bytes)')
    p.add_argument('--apply', action='store_true')
    args = p.parse_args()
    target = int(round(args.gb * 1_000_000_000))
    if not 500_000_000 <= target <= 32_000_000_000:
        raise SystemExit('refused: the limit must be between 0.5 and 32 GB')

    guard_args = argparse.Namespace(force=False, min_gb=0.0, margin=45)
    out, services = rp.checks(guard_args)
    hard = [x for x in out['refusals'] if not x.startswith('memory ')]
    print(json.dumps({'guards': hard or 'clear', 'active_statements': out.get('active_statements'),
                      'postgres_memory_gb': out.get('postgres_memory_gb')}))

    text = RAILWAY_TS.read_text()
    found = LINE.search(text)
    if not found:
        raise SystemExit('refused: the Postgres memoryBytes line was not found in .railway/railway.ts')
    current = int(found.group(2))
    if current != target:
        RAILWAY_TS.write_text(LINE.sub(lambda m: f'{m.group(1)}{target}{m.group(3)}', text, count=1))
    shown = plan()
    # the plan compares the file with the live project: either nothing to do, or exactly this one change to `target`
    up_to_date = 'up to date' in shown
    one_change = '0 to add, 1 to change, 0 to destroy' in shown and 'memoryBytes' in shown \
        and f'→ {target})' in shown
    print(json.dumps({'railway_ts': f'{current} -> {target}', 'live_already': up_to_date, 'plan_ok': up_to_date or one_change}))
    if not (up_to_date or one_change):
        print(shown[-1500:])
        raise SystemExit('refused: the plan is not exactly the memory change')
    if not args.apply or up_to_date:
        return 0
    if hard:
        raise SystemExit('refused: ' + '; '.join(hard))

    before = pgq.q('SELECT pg_postmaster_start_time()::text')['rows'][0][0]
    applied = subprocess.run(['railway', 'config', 'apply', '--yes'], cwd=ROOT, capture_output=True, text=True,
                             env=CLI_ENV)
    print(applied.stdout[-400:])
    if applied.returncode != 0:
        raise SystemExit('railway config apply failed')
    started = time.monotonic()
    status = None
    while time.monotonic() - started < 600:
        time.sleep(15)
        deps = rp.gql('query($s:String!,$e:String!){deployments(first:1,input:{serviceId:$s,environmentId:$e})'
                      '{edges{node{id status}}}}', {'s': services['Postgres'], 'e': rp.ENV})
        node = deps['deployments']['edges'][0]['node']
        status = node['status']
        if status in ('SUCCESS', 'FAILED', 'CRASHED'):
            break
    limits = rp.gql('query($s:String!,$e:String!){serviceInstanceLimits(serviceId:$s,environmentId:$e)}',
                    {'s': services['Postgres'], 'e': rp.ENV})['serviceInstanceLimits']
    after = pgq.q('SELECT pg_postmaster_start_time()::text')['rows'][0][0]
    domain = json.loads(subprocess.run(['railway', 'variables', '--service', 'edge-bff', '--environment', 'dev', '--json'],
                                       capture_output=True, text=True).stdout)['RAILWAY_PUBLIC_DOMAIN']
    try:
        ready = urllib.request.urlopen(f'https://{domain}/ready', timeout=30).status
    except urllib.error.HTTPError as e:
        ready = e.code
    print(json.dumps({'deployment': node['id'], 'status': status, 'memory_bytes_live': limits['containers']['memoryBytes'],
                      'start_before': before, 'start_after': after, 'edge_bff_ready': ready}))
    return 0 if status == 'SUCCESS' and limits['containers']['memoryBytes'] == target else 1


if __name__ == '__main__':
    raise SystemExit(main())
