#!/usr/bin/env python3
"""What the beta holds that the live site does not, derived at run time (the user, 2026-11-20, EXEC option A:
development happens on the beta and reaches the live site only on request; LIVE_PROMOTION.md). Read-only.

It compares the beta's branch with the live site's (default origin/main and origin/live, fetched first) and their
release files (apps/edge-bff/catalog/releases.json), so a session without the earlier conversation sees:
- the commits the live site does not have;
- the areas they change (apps, migrations, scripts, documents);
- new migrations: the database is shared, so each must keep the live site's older code working (expand only);
- the release file's changes: tabs and catalog items whose stage differs or that are new (an unlisted tab or item is
  'lab', on the beta only);
- what is at the lab stage on the beta's side (it stays off on the live site when `live` moves);
- what is at the preview stage on the beta's side (it reaches the live site for the admin only when `live` moves:
  EXEC-MU-ACCOUNTS "A preview release stage");
- with --sites, the commits both sites run (GET /version): `live` may move only to a commit the beta runs.

Usage (repository root):
    python3 scripts/live_diff.py                 # origin/main against origin/live, after a fetch
    python3 scripts/live_diff.py --sites --json  # also the running commits; machine-readable
    python3 scripts/live_diff.py --beta <ref> --live <ref> --no-fetch
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request

RELEASES = 'apps/edge-bff/catalog/releases.json'
MIGRATIONS = 'database/migrations/'
SITES = {'beta': 'https://edge-bff-dev.up.railway.app/version', 'live': 'https://app.edgefinance.id/version'}


def git(*args: str) -> str:
    return subprocess.run(['git', *args], capture_output=True, text=True, check=True).stdout


def area(path: str) -> str:
    """The area a changed file belongs to: an app (apps/<name>), the migrations, scripts, verification, the CI, or the
    documents at the root; anything else by its first folder."""
    parts = path.split('/')
    if parts[0] == 'apps' and len(parts) > 1:
        return f'apps/{parts[1]}'
    if path.startswith(MIGRATIONS):
        return 'database/migrations'
    if len(parts) == 1:
        return 'documents (root)' if path.endswith('.md') else 'root files'
    return parts[0]


def group_areas(paths):
    out = {}
    for p in paths:
        out.setdefault(area(p), []).append(p)
    return dict(sorted(out.items()))


def stages(doc):
    """(items, tabs) of a release file: {(kind, id): stage} and {tab: stage}."""
    if not doc:
        return {}, {}
    return ({(i['kind'], i['id']): i['stage'] for i in doc.get('items', [])},
            {t['id']: t['stage'] for t in doc.get('tabs', [])})


def release_changes(live_doc, beta_doc):
    """What moving `live` would change in the release file: entries new on the beta's side (with their stage), stages
    that differ, entries gone; everything at the lab stage on the beta's side (it stays off on the live site); and, for
    items, everything at the preview stage there (on the live site for the admin only once `live` moves)."""
    out = {}
    for name, (old, new) in (('items', (stages(live_doc)[0], stages(beta_doc)[0])),
                             ('tabs', (stages(live_doc)[1], stages(beta_doc)[1]))):
        key = (lambda k: f'{k[0]}:{k[1]}') if name == 'items' else str
        out[name] = {
            'new': sorted(f'{key(k)}={v}' for k, v in new.items() if k not in old),
            'changed': sorted(f'{key(k)}: {old[k]} -> {v}' for k, v in new.items() if k in old and old[k] != v),
            'gone': sorted(key(k) for k in old if k not in new),
            'lab_on_beta': sorted(key(k) for k, v in new.items() if v == 'lab'),
        }
        if name == 'items':
            out[name]['preview_admin_only'] = sorted(key(k) for k, v in new.items() if v == 'preview')
    return out


def release_doc(ref: str):
    try:
        return json.loads(git('show', f'{ref}:{RELEASES}'))
    except subprocess.CalledProcessError:
        return None


def running_commits():
    out = {}
    for site, url in SITES.items():
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'saniti-live-diff'}),
                                        timeout=20) as r:
                out[site] = json.load(r).get('commit')
        except Exception as e:                       # noqa: BLE001
            out[site] = f'unreadable ({type(e).__name__})'
    return out


def report(beta: str, live: str, sites: bool):
    commits = [line for line in git('log', '--format=%h %s', f'{live}..{beta}').splitlines() if line]
    changed = [p for p in git('diff', '--name-only', live, beta).splitlines() if p]
    added = [line.split('\t', 1)[1] for line in git('diff', '--name-status', '--diff-filter=A', live, beta).splitlines()
             if line.startswith('A\t')]
    out = {'beta_ref': beta, 'live_ref': live, 'beta_commit': git('rev-parse', beta).strip(),
           'live_commit': git('rev-parse', live).strip(), 'commits': commits, 'areas': group_areas(changed),
           'new_migrations': sorted(p for p in added if p.startswith(MIGRATIONS) and p.endswith('.sql')),
           'releases': release_changes(release_doc(live), release_doc(beta))}
    if sites:
        out['running'] = running_commits()
        out['beta_runs_beta_ref'] = out['running'].get('beta') == out['beta_commit']
    return out


def text(r) -> str:
    lines = [f"beta {r['beta_ref']} {r['beta_commit'][:12]}  vs  live {r['live_ref']} {r['live_commit'][:12]}",
             f"{len(r['commits'])} commit(s) the live site does not have:"]
    lines += [f'  {c}' for c in r['commits'][:60]] + (['  ...'] if len(r['commits']) > 60 else [])
    lines.append('areas changed:')
    lines += [f'  {a}: {len(ps)} file(s)' for a, ps in r['areas'].items()]
    lines.append('new migrations (the shared database: each must keep the live site\'s older code working):')
    lines += [f'  {m}' for m in r['new_migrations']] or ['  none']
    for name in ('tabs', 'items'):
        rc = r['releases'][name]
        lines.append(f'release file, {name}: new {rc["new"] or "none"}; changed {rc["changed"] or "none"}; '
                     f'gone {rc["gone"] or "none"}; lab on the beta (stays off on the live site) {rc["lab_on_beta"] or "none"}'
                     + (f'; preview (on the live site for the admin only, paid and free accounts do not see it) '
                        f'{rc["preview_admin_only"] or "none"}' if 'preview_admin_only' in rc else ''))
    if 'running' in r:
        lines.append(f"running: beta {r['running'].get('beta')}, live {r['running'].get('live')}; the beta runs the "
                     f"beta ref: {r['beta_runs_beta_ref']} (live may move only to a commit the beta runs)")
    return '\n'.join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--beta', default='origin/main')
    p.add_argument('--live', default='origin/live')
    p.add_argument('--no-fetch', action='store_true')
    p.add_argument('--sites', action='store_true', help='also read the commits both sites run (GET /version)')
    p.add_argument('--json', action='store_true')
    args = p.parse_args(argv)
    if not args.no_fetch:
        subprocess.run(['git', 'fetch', '-q', 'origin', 'main', 'live'], check=False)
    try:
        r = report(args.beta, args.live, args.sites)
    except subprocess.CalledProcessError as e:
        print(f'git could not compare {args.live}..{args.beta}: {e.stderr.strip()[:300]}', file=sys.stderr)
        return 2
    print(json.dumps(r, indent=1) if args.json else text(r))
    return 0


if __name__ == '__main__':
    sys.exit(main())
