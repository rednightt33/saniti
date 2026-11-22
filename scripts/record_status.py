"""AGENTS.md "Findings and fixes", rule 9 (the user, 2026-11-22: "Ada tes otomatis yang membandingkan status catatan error
dengan apa yang benar-benar terpasang di beta dan live"): the status an ERRORS_AND_SOLUTIONS.md entry's heading claims
against the commits each website runs (verification/records/deployed_commits.json, written at each deploy).

The status part is the heading's last parenthesised group; its clauses are split at ';'. A clause claims one of: not
deployed / on the branch, on the beta, on the live site. Each claim is judged in both directions:

- A clause that names a commit (`<hex>`) is judged by the commits it names: "on the branch" is stale when the beta runs
  one of them (understated); "on the beta" is stale when the beta runs none of them (overclaimed) or the live site runs
  all of them (understated); "on the live site" is stale when the live site does not run one of them (overclaimed).
- A claim whose clause names no commit is judged by the commits the whole entry cites: "on the branch" is stale when
  the beta runs one of them; "on the beta" when the beta runs none of them or the live site runs all of them; "on the
  live site" when the live site runs none of them. A "not deployed" or "on the branch" heading that cites no commit at
  all cannot be judged; the ones of 2026-11-22 are frozen in the test's LEGACY (a new one fails: cite the fix's
  commit).

deployed_commits.json is tied to the deploy records: each site's commit there is named, and no newer commit is, by the
bullets of the newest RAILWAY_CHANGELOG.md entry that name the site's service (`edge-bff`, `edge-bff-live`) and a git
commit, so a deploy recorded without the file, or the file changed without a deploy entry, fails.

Read-only; it needs the full git history (git merge-base --is-ancestor). `python3 scripts/record_status.py` prints the
stale entries; exit 1 when there are any."""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ERRORS = ROOT / 'ERRORS_AND_SOLUTIONS.md'
DEPLOYED = ROOT / 'verification' / 'records' / 'deployed_commits.json'
CHANGELOG = ROOT / 'RAILWAY_CHANGELOG.md'
# The service of each website, as RAILWAY_CHANGELOG.md names it: the beta is `edge-bff` (not `edge-bff-live`).
SITE_SERVICE = {'beta': re.compile(r'\bedge-bff\b(?!-)'), 'live': re.compile(r'\bedge-bff-live\b')}
NOT_DEPLOYED = re.compile(r'not deployed|fixed on (?:the )?branch|on (?:the )?branch\b|built on the branch', re.I)
ON_BETA = re.compile(r'on the beta', re.I)
ON_LIVE = re.compile(r'on the live site|live since|promoted', re.I)
COMMIT = re.compile(r'`([0-9a-f]{8,40})`')


def entries(text=None):
    """[(id, heading, body)] of the entries (### M<n> headings)."""
    text = ERRORS.read_text(encoding='utf-8') if text is None else text
    parts = re.split(r'(?m)^(### M\d+[^\n]*)\n', text)
    out = []
    for i in range(1, len(parts) - 1, 2):
        m = re.match(r'### (M\d+)', parts[i])
        out.append((m.group(1), parts[i], parts[i + 1]))
    return out


def status_part(heading):
    """The heading's last parenthesised group (nested parentheses kept), or the whole heading without one."""
    h = heading.rstrip()
    if not h.endswith(')'):
        return h
    depth = 0
    for i in range(len(h) - 1, -1, -1):
        depth += {')': 1, '(': -1}.get(h[i], 0)
        if depth == 0:
            return h[i:]
    return h


def ancestor(commit, of):
    r = subprocess.run(['git', '-C', str(ROOT), 'merge-base', '--is-ancestor', commit, of], capture_output=True)
    return r.returncode == 0


def known(commit):
    return subprocess.run(['git', '-C', str(ROOT), 'cat-file', '-e', f'{commit}^{{commit}}'], capture_output=True).returncode == 0


def claims(text):
    """The claims of one clause: a subset of {'branch', 'beta', 'live'}."""
    out = set()
    if NOT_DEPLOYED.search(text):
        out.add('branch')
    if ON_BETA.search(text):
        out.add('beta')
    if ON_LIVE.search(text):
        out.add('live')
    return out


def judge(claim, commits, beta, live, named):
    """Why the claim is stale for these commits, or None. `named`: the commits are the clause's own (all must hold),
    not the entry's (one is enough)."""
    on_beta = [ancestor(c, beta) for c in commits]
    on_live = [ancestor(c, live) for c in commits]
    if claim == 'branch' and any(on_beta):
        where = 'the live site' if any(on_live) else 'the beta'
        return f'it says not deployed, but {where} runs a commit it cites'
    if claim == 'beta':
        if all(on_live):
            return 'it says on the beta, but the live site runs every commit it cites'
        if (not all(on_beta)) if named else (not any(on_beta)):
            return 'it says on the beta, but the beta does not run ' + ('a commit it names' if named else 'any commit it cites')
    if claim == 'live' and ((not all(on_live)) if named else (not any(on_live))):
        return 'it says on the live site, but the live site does not run ' + ('a commit it names' if named else 'any commit it cites')
    return None


def status(text=None, deployed=None):
    """{'stale': [(id, why)], 'unjudged': [ids]}."""
    deployed = deployed or json.loads(DEPLOYED.read_text(encoding='utf-8'))
    beta, live = deployed['beta'], deployed['live']
    stale, unjudged = [], []
    for mid, heading, body in entries(text):
        part = status_part(heading)
        mixed = len(claims(part)) > 1
        cited = [c for c in COMMIT.findall(heading + body) if known(c)]
        whys = []
        for clause in part.strip('()').split(';'):
            said = claims(clause)
            if not said:
                continue
            own = [c for c in COMMIT.findall(clause) if known(c)]
            # "on the beta and the live site" in one clause is judged as its strongest claim.
            for claim in (['live'] if 'live' in said else sorted(said)):
                if own:
                    why = judge(claim, own, beta, live, named=True)
                elif cited and not mixed:
                    why = judge(claim, cited, beta, live, named=False)
                else:
                    # No commit to judge this claim by: the entry cites none, or the heading has more than one status
                    # and this clause does not name the commit of its own part.
                    if claim == 'branch' and mid not in unjudged:
                        unjudged.append(mid)
                    why = None
                if why:
                    whys.append(why)
        if whys:
            stale.append((mid, '; '.join(dict.fromkeys(whys))))
    return {'stale': stale, 'unjudged': unjudged}


def bullets(part):
    """The top-level bullets of a changelog entry, each with its continuation lines."""
    out = []
    for line in part.split('\n')[1:]:
        if line.startswith('- '):
            out.append(line)
        elif out and line.startswith(' '):
            out[-1] += '\n' + line
    return out


def newest_deploy_entry(site, text=None):
    """(title, [commits]) of the newest RAILWAY_CHANGELOG.md entry (## heading) with a bullet that names the site's
    service and a git commit: the git commits of those bullets. (None, []) when there is none."""
    text = CHANGELOG.read_text(encoding='utf-8') if text is None else text
    for part in re.split(r'(?m)^(?=## )', text):
        if not part.startswith('## '):
            continue
        named = [b for b in bullets(part) if SITE_SERVICE[site].search(b)]
        commits = [c for c in dict.fromkeys(c for b in named for c in COMMIT.findall(b)) if known(c)]
        if commits:
            return part.split('\n', 1)[0][3:], commits
    return None, []


def deployed_unrecorded(deployed=None, text=None):
    """[(site, why)]: a site whose commit in deployed_commits.json the newest deploy record of its service does not
    name, or that record names a newer commit (a descendant) than the file's."""
    deployed = deployed or json.loads(DEPLOYED.read_text(encoding='utf-8'))
    out = []
    for site in ('beta', 'live'):
        title, commits = newest_deploy_entry(site, text)
        mine = deployed[site]
        same = lambda c: mine.startswith(c) or c.startswith(mine)
        newer = [c for c in commits if not same(c) and ancestor(mine, c)]
        if not any(same(c) for c in commits) or newer:
            out.append((site, f'deployed_commits.json says {mine[:8]}, but the newest RAILWAY_CHANGELOG.md record of its '
                              f'service ({title!r}) names {", ".join(c[:8] for c in commits) or "no commit"}'
                              + (f', {", ".join(c[:8] for c in newer)} newer' if newer else '')))
    return out


if __name__ == '__main__':
    r = status()
    for mid, why in r['stale']:
        print(f'STALE {mid}: {why}')
    print(f"{len(r['stale'])} stale, {len(r['unjudged'])} unjudged (no commit cited)")
    bad = deployed_unrecorded()
    for site, why in bad:
        print(f'UNRECORDED {site}: {why}')
    sys.exit(1 if r['stale'] or bad else 0)
