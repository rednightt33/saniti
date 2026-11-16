#!/usr/bin/env python3
"""Planned Postgres restart: by hand after a large update (user decision 2026-11-01, ERRORS M319: "Restart terencana
Postgres sesudah setiap backfill besar. Memori langsung bersih, dengan jeda sekitar satu menit.") and on a schedule
from the postgres-memory-cron service (EXEC-PG-RESTART-CRON, user go 2026-11-03: "Go langkah 1–9, tafsiran toggle
benar, setuju").

Why: a large read or write leaves Linux page cache that Railway bills as Postgres memory until it is reclaimed (up to
the 4 GB limit, for hours). A restart frees it at once, at the cost of about 12 seconds without the database.

Guards (checks()):
  hard (never skipped, a run stops): a cron of another service runs within --margin minutes (default 45; this
       service's own cron is left out, RAILWAY_SERVICE_NAME), or the time is inside the user's B6 windows
       (00:00-01:45 and 12:00-13:20 UTC);
  soft (a cron run waits for them, PG_RESTART_WAIT_MINUTES, default 60): a client statement is running, or a user run
       is active (ERRORS M340: edge_bff.jobs QUEUED/RUNNING/RECOVERING or "AI_conversation_turn" RUNNING, each updated
       or created within 2 hours), or those could not be read;
  memory: the newest 5-minute Postgres memory is at least --min-gb (default 0.8; idle is 0.1-0.6 GB). A scheduled run
       below it does nothing; a manual run (button or dashboard) ignores it.

Hand use (an agent, after a large update; AGENTS.md "Postgres memory after large updates"):
  python3 scripts/restart_postgres.py [--apply] [--force] [--min-gb 0.8] [--margin 45]
--check (default) prints the verdict without restarting; --apply restarts when every guard passes; --force skips the
memory and the soft guards (never the hard ones). It sends no Telegram message (the notify address is private).

Cron use (postgres-memory-cron, `--cron`; every setting from the service's variables):
  PG_RESTART_TIMES_WIB   restart times, e.g. "09:45,20:45"; the service's cronSchedule is cron_for(times)
                         (scripts/set_postgres_restart_times.py keeps the two together)
  PG_RESTART_MODE        "check" (default: decide and report, never restart) or "apply"
  PG_RESTART_AUTO        "false" turns the scheduled restart off whatever Telegram says
  PG_RESTART_WAIT_MINUTES, PG_RESTART_MIN_GB
  A run is one of:
    manual-telegram  the Telegram button (/restart_postgres) wrote RESTART_POSTGRES in "Telegram_Command_Log" within
                     15 minutes;
    scheduled        within 20 minutes after a listed time; only when the automatic restart is on (the newest
                     PG_AUTO_ON/PG_AUTO_OFF in "Telegram_Command_Log", default on) and memory is above --min-gb;
    tick             another tick of the cron's minute x hour product: exits without work (publisher's should_run);
    manual-railway   any other start (Railway dashboard Run Now).
  Telegram (telegram-monitor source Postgres_Restart): manual (a manual request arrived), started, success, failed,
  refused (a manual run always; a scheduled run when a guard stops it), check (mode check, every run but ticks).
  A scheduled run skipped for low memory or auto off sends nothing (log only).

Credentials (ERRORS M433), the first one Railway accepts: RAILWAY_RESTART_TOKEN (postgres-memory-cron) or RAILWAY_TOKEN
(project tokens), then RAILWAY_API_TOKEN (an account or agent-session token, sent as Bearer). When none works the
script prints one line "POSTGRES_RESTART NOT_RUN: ..." and exits 4. DATABASE_URL when set (read-only session),
otherwise pgweb. Nothing secret is printed; the output names the variable that worked.
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
PID, ENV = '8aef1702-030b-49cb-9df7-5ac2e0a42691', '4d3e5af2-302b-4a2e-84e2-7d7476d6ff49'   # PROJECT_CONTEXT.md
B6 = [((0, 0), (1, 45)), ((12, 0), (13, 20))]       # user rule B6: no maintenance in these UTC windows
WIB = timezone(timedelta(hours=7))
SOURCE = 'Postgres_Restart'                         # telegram-monitor source (parse_postgres_restart)
SCHEDULE_SLACK_MINUTES = 20                         # a tick this long after a listed time is that time's run
MANUAL_TELEGRAM_MINUTES = 15                        # a RESTART_POSTGRES command this recent makes the run manual
WAIT_STEP_SECONDS = 300
HARD = ('cron_due', 'b6_window')
SOFT = ('active_statements', 'user_runs', 'runs_unreadable')


# ERRORS M433: the Railway credential is whichever the place running this has, tried in this order. A project token
# (postgres-memory-cron's own, or an agent's) goes in the Project-Access-Token header; an account or session token
# (an agent session behind its network proxy) goes in Authorization: Bearer. A credential Railway refuses is skipped
# and the next one is tried; the one that worked is kept for the run. Only the variable names are ever printed.
CREDENTIALS = (('RAILWAY_RESTART_TOKEN', 'Project-Access-Token'), ('RAILWAY_TOKEN', 'Project-Access-Token'),
               ('RAILWAY_API_TOKEN', 'Authorization'))
AUTH_REFUSED = ('not authorized', 'unauthorized', 'invalid token', 'authentication')
_auth = {'name': None, 'tried': []}


class RailwayAuthError(SystemExit):
    """No credential of CREDENTIALS reached Railway; main() prints POSTGRES_RESTART NOT_RUN instead of a traceback."""


def cli_env():
    """The environment for the `railway` CLI: as here, except a RAILWAY_TOKEN Railway refuses is left out so the CLI
    uses the session's own credential (M433; the CLI cannot combine a project token with an agent proxy's)."""
    import shutil
    env = dict(os.environ, _=shutil.which('railway') or 'railway')   # the CLI reads its own path from $_
    if os.environ.get('RAILWAY_TOKEN'):
        if _auth['name'] is None:
            gql('query($id:String!){project(id:$id){name}}', {'id': PID})
        if _auth['name'] != 'RAILWAY_TOKEN':
            env.pop('RAILWAY_TOKEN')
    return env


def candidates():
    """(variable name, header) for every credential set here, in CREDENTIALS order; the one that worked first."""
    found = [(n, h) for n, h in CREDENTIALS if os.environ.get(n)]
    if _auth['name']:
        found.sort(key=lambda c: c[0] != _auth['name'])
    return found


def _post(query, variables, name, header):
    value = os.environ[name]
    headers = {'Content-Type': 'application/json', 'User-Agent': 'saniti-restart-postgres/3',
               header: f'Bearer {value}' if header == 'Authorization' else value}
    req = urllib.request.Request('https://backboard.railway.com/graphql/v2',
                                 json.dumps({'query': query, 'variables': variables}).encode(), headers)
    try:
        return json.loads(urllib.request.urlopen(req, timeout=60).read())
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return None                              # refused: try the next credential
        raise


def gql(query, variables):
    tried = []
    for name, header in candidates():
        body = _post(query, variables, name, header)
        errors = (body or {}).get('errors') or []
        if body is None or (errors and body.get('data') is None
                            and all(any(w in str(e.get('message', '')).lower() for w in AUTH_REFUSED) for e in errors)):
            tried.append(name)
            continue
        _auth['name'] = name
        if errors:
            raise SystemExit('Railway refused: ' + '; '.join(str(e.get('message'))[:200] for e in errors))
        return body['data']
    _auth['tried'] = tried
    names = ', '.join(n for n, _ in CREDENTIALS)
    raise RailwayAuthError(f'Railway refused every credential set here ({", ".join(tried) or "none set"}; '
                           f'one of {names} is needed)')


def query(sql):
    """Rows of a read-only statement: DATABASE_URL in a read-only session when set (postgres-memory-cron), else pgweb
    (role pgweb, read-only). Returns {'rows': [...]} or {'error': ...}."""
    url = os.environ.get('DATABASE_URL')
    if url:
        import psycopg
        try:
            with psycopg.connect(url, autocommit=True, connect_timeout=30,
                                 options='-c default_transaction_read_only=on -c statement_timeout=30000') as c:
                return {'rows': [list(r) for r in c.execute(sql).fetchall()]}
        except Exception as e:                       # noqa: BLE001  (reported, never raised: a guard reads it)
            return {'error': type(e).__name__}
    sys.path.insert(0, str(ROOT / 'verification/terminal_api'))
    import pgq
    return pgq.q(sql)


def run_times(value):
    """'09:45,20:45' -> [(9, 45), (20, 45)] (WIB); a malformed entry is a SystemExit."""
    out = []
    for part in (value or '').split(','):
        if part.strip():
            h, m = part.strip().split(':')
            h, m = int(h), int(m)
            if not (0 <= h < 24 and 0 <= m < 60):
                raise SystemExit(f'bad time {part!r}')
            out.append((h, m))
    return out


def cron_parts(times):
    """The UTC minutes and hours of the listed WIB times."""
    utc = [((h - 7) % 24, m) for h, m in times]
    return sorted({m for _, m in utc}), sorted({h for h, _ in utc})


def cron_for(times):
    """The one Railway cronSchedule (UTC) that fires at every listed WIB time: the product of their UTC minutes and
    hours (as terminal-publisher's cron_for); the other ticks of the product are 'tick' runs that do nothing."""
    minutes, hours = cron_parts(times)
    return f"{','.join(map(str, minutes))} {','.join(map(str, hours))} * * *"


def _near(times, now, slack):
    mins = now.astimezone(WIB).hour * 60 + now.astimezone(WIB).minute
    return any(0 <= (mins - (h * 60 + m)) % 1440 <= slack for h, m in times)


def run_kind(times, now, telegram_manual):
    """manual-telegram, scheduled, tick or manual-railway (see the module text)."""
    if telegram_manual:
        return 'manual-telegram'
    if times and _near(times, now, SCHEDULE_SLACK_MINUTES):
        return 'scheduled'
    minutes, hours = cron_parts(times)
    ticks = [((uh + 7) % 24, um) for uh in hours for um in minutes]
    if times and _near(ticks, now, SCHEDULE_SLACK_MINUTES):
        return 'tick'
    return 'manual-railway'


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


def services_by_name():
    s = gql('query($id:String!){project(id:$id){services{edges{node{id name}}}}}', {'id': PID})
    return {e['node']['name']: e['node']['id'] for e in s['project']['services']['edges']}


def cron_schedules(services):
    out = {}
    for name, sid in services.items():
        si = gql('query($s:String!,$e:String!){serviceInstance(serviceId:$s,environmentId:$e){cronSchedule}}',
                 {'s': sid, 'e': ENV})['serviceInstance']
        if (si or {}).get('cronSchedule'):
            out[name] = si['cronSchedule']
    return out


def crons_due(crons, now, margin, skip=None):
    """'<service> (<cron>) at HH:MM UTC' for every cron of another service firing within margin minutes of now."""
    due = []
    for name, cron in crons.items():
        if name == skip:
            continue
        for k in range(-margin, margin + 1):
            t = now + timedelta(minutes=k)
            if cron_matches(cron, t):
                due.append(f'{name} ({cron}) at {t:%H:%M} UTC')
                break
    return due


def in_b6(now):
    return next((f'{h1:02d}:{m1:02d}-{h2:02d}:{m2:02d}' for (h1, m1), (h2, m2) in B6
                 if (h1, m1) <= (now.hour, now.minute) <= (h2, m2)), None)


def memory_gb(services, since_minutes=30):
    now = datetime.now(timezone.utc)
    m = gql('query($p:String!,$e:String!,$s:String!,$d:DateTime!){metrics(projectId:$p,environmentId:$e,serviceId:$s,'
            'startDate:$d,measurements:[MEMORY_USAGE_GB],sampleRateSeconds:300){values{ts value}}}',
            {'p': PID, 'e': ENV, 's': services['Postgres'], 'd': (now - timedelta(minutes=since_minutes)).isoformat()})
    # EXEC-PG-MEMORY (2026-11-03): the newest 5-minute value; an hourly average lags behind a restart
    vals = [v for x in m['metrics'] for v in x['values']]
    return max(vals, key=lambda v: v['ts']) if vals else None


def user_runs():
    """(active EDGE jobs, running orc turns) of the last 2 hours (ERRORS M340), or None when unreadable."""
    r = query("SELECT (SELECT count(*) FROM edge_bff.jobs WHERE state IN ('QUEUED','RUNNING','RECOVERING') "
              "AND updated_at > now() - interval '2 hours'), "
              "(SELECT count(*) FROM public.\"AI_conversation_turn\" WHERE status = 'RUNNING' "
              "AND created_at > now() - interval '2 hours')")
    return tuple(r['rows'][0]) if 'rows' in r else None


def checks(args):
    """Every guard at this minute: (out, services); out['reasons'] holds the codes, out['refusals'] the words."""
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    services = services_by_name()
    out = {'now': now.isoformat(), 'refusals': [], 'reasons': []}

    def refuse(code, text):
        out['reasons'].append(code)
        out['refusals'].append(text)
    # memory (decided by the caller: a manual run ignores it)
    mem = memory_gb(services)
    out['postgres_memory_gb'] = mem['value'] if mem else None
    min_gb = getattr(args, 'min_gb', 0.8)
    if out['postgres_memory_gb'] is None or out['postgres_memory_gb'] < min_gb:
        refuse('memory_low', f"memory {out['postgres_memory_gb']} GB is below {min_gb} GB: nothing to free")
    # hard: B6 and the other services' crons
    window = in_b6(now)
    if window:
        refuse('b6_window', f'inside the B6 window {window} UTC')
    due = crons_due(cron_schedules(services), now, getattr(args, 'margin', 45), getattr(args, 'self_service', None))
    if due:
        refuse('cron_due', 'a cron runs within the margin: ' + '; '.join(due))
    # soft: client statements and user runs
    r = query("SELECT count(*) FROM pg_stat_activity WHERE state = 'active' AND pid <> pg_backend_pid() "
              "AND backend_type = 'client backend'")
    out['active_statements'] = r['rows'][0][0] if 'rows' in r else None
    if out['active_statements'] is None or out['active_statements']:
        refuse('active_statements', f"{out['active_statements']} statements are running")
    runs = user_runs()
    out['user_runs'] = {'edge_jobs': runs[0], 'orc_turns': runs[1]} if runs else None
    if runs is None:
        refuse('runs_unreadable', 'the active user runs could not be read (edge_bff.jobs, AI_conversation_turn)')
    elif any(runs):
        refuse('user_runs', f'a user run is active ({runs[0]} EDGE jobs, {runs[1]} orc turns; ERRORS M340)')
    return out, services


def edge_domain():
    """edge-bff's public domain in dev, read through the same Railway credential as every other call (M433: the CLI
    may not hold one)."""
    s = gql('query($id:String!){project(id:$id){services{edges{node{id name}}}}}', {'id': PID})
    sid = next(e['node']['id'] for e in s['project']['services']['edges'] if e['node']['name'] == 'edge-bff')
    d = gql('query($s:String!,$e:String!){domains(projectId:"' + PID + '",serviceId:$s,environmentId:$e)'
            '{serviceDomains{domain}}}', {'s': sid, 'e': ENV})
    return d['domains']['serviceDomains'][0]['domain']


def edge_ready():
    url = os.environ.get('EDGE_BFF_URL')
    if not url:
        domain = os.environ.get('RAILWAY_SERVICE_EDGE_BFF_URL') or edge_domain()
        url = f'https://{domain}/ready'
    for _ in range(6):
        try:
            return urllib.request.urlopen(url, timeout=30).status
        except urllib.error.HTTPError as e:
            code = e.code
        except Exception:                            # noqa: BLE001
            code = None
        time.sleep(10)
    return code


def postgres_start():
    r = query('SELECT pg_postmaster_start_time()::text')
    return r['rows'][0][0] if 'rows' in r else None


def restart(services):
    deps = gql('query($s:String!,$e:String!){deployments(first:5,input:{serviceId:$s,environmentId:$e}){edges{node{id status}}}}',
               {'s': services['Postgres'], 'e': ENV})
    dep = next(e['node']['id'] for e in deps['deployments']['edges'] if e['node']['status'] == 'SUCCESS')
    before = postgres_start()
    gql('mutation($id:String!){deploymentRestart(id:$id)}', {'id': dep})
    started = time.monotonic()
    after = None
    while time.monotonic() - started < 600:
        time.sleep(10)
        after = postgres_start()
        if after and after != before:
            break
    else:
        raise SystemExit('Postgres did not come back within 10 minutes; check the Railway dashboard')
    return {'deployment': dep, 'start_before': before, 'start_after': after,
            'seconds': round(time.monotonic() - started), 'edge_bff_ready': edge_ready()}


def notify(kind, run_id, event, details):
    """POST one fixed-shape message to telegram-monitor (source Postgres_Restart); never raises."""
    url, secret = os.environ.get('TELEGRAM_NOTIFY_URL'), os.environ.get('TELEGRAM_NOTIFY_SECRET')
    if not url or not secret:
        return 'not_configured'
    payload = {'source_table': SOURCE, 'execution_id': f'pg-restart-{kind}-{run_id}-{event}',
               'details': dict(details, kind=kind, event=event)}
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, json.dumps(payload).encode(), method='POST',
                                         headers={'Content-Type': 'application/json', 'X-Notify-Secret': secret})
            return json.loads(urllib.request.urlopen(req, timeout=20).read() or b'{}').get('status')
        except Exception as e:                       # noqa: BLE001
            last = type(e).__name__
            time.sleep(2 * (attempt + 1))
    print('PG_RESTART ' + json.dumps({'notify_failed': event, 'error': last}), flush=True)
    return 'failed'


def auto_on():
    """The automatic restart's switch: PG_RESTART_AUTO=false wins, else the newest Telegram PG_AUTO_ON/PG_AUTO_OFF."""
    if os.environ.get('PG_RESTART_AUTO', '').strip().lower() in ('false', '0', 'off', 'no'):
        return False
    r = query("SELECT command FROM public.\"Telegram_Command_Log\" WHERE command IN ('PG_AUTO_ON','PG_AUTO_OFF') "
              "AND status = 'TRIGGERED' ORDER BY id DESC LIMIT 1")
    return not ('rows' in r and r['rows'] and r['rows'][0][0] == 'PG_AUTO_OFF')


def telegram_manual():
    r = query("SELECT count(*) FROM public.\"Telegram_Command_Log\" WHERE command = 'RESTART_POSTGRES' "
              "AND status IN ('RECEIVED','TRIGGERED') "
              f"AND requested_at > now() - interval '{MANUAL_TELEGRAM_MINUTES} minutes'")
    return bool('rows' in r and r['rows'][0][0])


def log(**fields):
    print('PG_RESTART ' + json.dumps(fields, default=str), flush=True)


def cron_main():
    """One run of postgres-memory-cron (module text). Exit 1 only when a restart failed."""
    times = run_times(os.environ.get('PG_RESTART_TIMES_WIB', '09:45,20:45'))
    mode = os.environ.get('PG_RESTART_MODE', 'check').strip().lower()
    wait = int(os.environ.get('PG_RESTART_WAIT_MINUTES', '60'))
    args = argparse.Namespace(min_gb=float(os.environ.get('PG_RESTART_MIN_GB', '0.8')), margin=45,
                              self_service=os.environ.get('RAILWAY_SERVICE_NAME', 'postgres-memory-cron'))
    now = datetime.now(timezone.utc)
    run_id = now.strftime('%Y%m%dT%H%M')
    kind = run_kind(times, now, telegram_manual())
    auto = auto_on()
    base = {'mode': mode, 'auto': auto, 'times_wib': ','.join(f'{h:02d}:{m:02d}' for h, m in times)}
    if kind == 'tick':
        log(kind=kind, action='none', **base)
        return 0
    manual = kind.startswith('manual')
    out, services = checks(args)
    if manual:
        notify(kind, run_id, 'manual', dict(base, memory_gb=out['postgres_memory_gb']))
    elif not auto or 'memory_low' in out['reasons']:
        reason = 'auto_off' if not auto else 'memory_low'
        log(kind=kind, action='skipped', reason=reason, memory_gb=out['postgres_memory_gb'], **base)
        if mode == 'check':
            notify(kind, run_id, 'check', dict(base, memory_gb=out['postgres_memory_gb'], would_restart=False,
                                               reasons=[reason]))
        return 0
    waited = 0
    while True:
        blocking = [r for r in out['reasons'] if r in HARD or r in SOFT]
        if not blocking or any(r in HARD for r in blocking) or waited >= wait:
            break
        log(kind=kind, action='waiting', reasons=blocking, waited_minutes=waited)
        time.sleep(WAIT_STEP_SECONDS)
        waited += WAIT_STEP_SECONDS // 60
        out, services = checks(args)
    blocking = [r for r in out['reasons'] if r in HARD or r in SOFT]
    facts = dict(base, memory_gb=out['postgres_memory_gb'], waited_minutes=waited)
    if mode == 'check':
        log(kind=kind, action='check', would_restart=not blocking, reasons=blocking, **facts)
        notify(kind, run_id, 'check', dict(facts, would_restart=not blocking, reasons=blocking))
        return 0
    if blocking:
        log(kind=kind, action='refused', reasons=blocking, refusals=out['refusals'], **facts)
        notify(kind, run_id, 'refused', dict(facts, reasons=blocking))
        return 0
    notify(kind, run_id, 'started', facts)
    try:
        result = restart(services)
    except SystemExit as e:
        log(kind=kind, action='failed', error=str(e), **facts)
        notify(kind, run_id, 'failed', dict(facts, reasons=['postgres_not_back']))
        return 1
    after, done = None, time.time()
    deadline = time.monotonic() + 480                # the next 5-minute memory sample after the restart
    while time.monotonic() < deadline:
        time.sleep(60)
        sample = memory_gb(services, since_minutes=15)
        if sample and sample['ts'] >= done:
            after = sample['value']
            break
    ok = result['edge_bff_ready'] == 200
    log(kind=kind, action='restarted' if ok else 'failed', memory_after_gb=after, **result, **facts)
    notify(kind, run_id, 'success' if ok else 'failed',
           dict(facts, seconds=result['seconds'], edge_ready=result['edge_bff_ready'], memory_after_gb=after,
                **({} if ok else {'reasons': ['edge_not_ready']})))
    return 0 if ok else 1


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--apply', action='store_true')
    p.add_argument('--force', action='store_true', help='skip the memory and the soft guards (never cron or B6)')
    p.add_argument('--cron', action='store_true', help='one postgres-memory-cron run, settings from its variables')
    # EXEC-PG-MEMORY (user 2026-11-03): idle is 0.1-0.6 GB, so 0.8 GB means a large job's page cache is left; the limit
    # went back to 4 GB the same day and the threshold stays (it still separates idle from cache)
    p.add_argument('--min-gb', type=float, default=0.8)
    p.add_argument('--margin', type=int, default=45)
    args = p.parse_args()
    try:
        return run(args)
    except RailwayAuthError as e:
        # ERRORS M433: one line a job's reader sees (run_job.sh prints the last lines), never a traceback
        print(f'POSTGRES_RESTART NOT_RUN: {e} Postgres was not restarted; run python3 scripts/restart_postgres.py '
              '(then --apply) where a Railway credential is set.')
        return 4


def run(args):
    if args.cron:
        return cron_main()
    out, services = checks(args)
    hard = [x for x, code in zip(out['refusals'], out['reasons']) if code in HARD]
    soft = [x for x in out['refusals'] if x not in hard]
    out['verdict'] = 'REFUSED' if hard or (soft and not args.force) else ('READY' if not args.apply else 'RESTARTING')
    out['railway_credential'] = _auth['name']
    print(json.dumps(out, default=str))
    if args.apply and out['verdict'] == 'RESTARTING':
        print(json.dumps(restart(services), default=str))
    return 0 if out['verdict'] != 'REFUSED' else 3


if __name__ == '__main__':
    raise SystemExit(main())
