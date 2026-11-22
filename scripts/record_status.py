"""AGENTS.md "Findings and fixes", rule 9 (the user, 2026-11-22: "Ada tes otomatis yang membandingkan status catatan error
dengan apa yang benar-benar terpasang di beta dan live"): the status an ERRORS_AND_SOLUTIONS.md entry's heading claims
against the commits each website runs (verification/records/deployed_commits.json, written at each deploy).

- An entry whose heading says the fix is not deployed or only on a branch, and whose body cites a commit the beta (or
  the live site) already runs, is stale: its heading must say where it runs now.
- An entry whose heading says "on the beta" and cites a commit the live site runs is stale too.
- An entry with such a heading that cites no commit cannot be judged; the ones of today are frozen in LEGACY (a new one
  fails: cite the fix's commit in the entry).

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


def ancestor(commit, of):
    r = subprocess.run(['git', '-C', str(ROOT), 'merge-base', '--is-ancestor', commit, of], capture_output=True)
    return r.returncode == 0


def known(commit):
    return subprocess.run(['git', '-C', str(ROOT), 'cat-file', '-e', f'{commit}^{{commit}}'], capture_output=True).returncode == 0


def status(text=None, deployed=None):
    """{'stale': [(id, why)], 'unjudged': [ids]}."""
    deployed = deployed or json.loads(DEPLOYED.read_text(encoding='utf-8'))
    beta, live = deployed['beta'], deployed['live']
    stale, unjudged = [], []
    for mid, heading, body in entries(text):
        status_part = heading[heading.rfind('('):] if '(' in heading else heading
        says_branch, says_beta = bool(NOT_DEPLOYED.search(status_part)), bool(ON_BETA.search(status_part))
        if not (says_branch or says_beta) or ON_LIVE.search(status_part):
            continue
        cited = [c for c in COMMIT.findall(heading + body) if known(c)]
        if not cited:
            if says_branch:
                unjudged.append(mid)
            continue
        if says_branch and any(ancestor(c, beta) for c in cited):
            where = 'the live site' if any(ancestor(c, live) for c in cited) else 'the beta'
            stale.append((mid, f'its heading says not deployed, but {where} runs a commit it cites'))
        elif says_beta and not says_branch and all(ancestor(c, live) for c in cited):
            stale.append((mid, 'its heading says on the beta, but the live site runs every commit it cites'))
    return {'stale': stale, 'unjudged': unjudged}


if __name__ == '__main__':
    r = status()
    for mid, why in r['stale']:
        print(f'STALE {mid}: {why}')
    print(f"{len(r['stale'])} stale, {len(r['unjudged'])} unjudged (no commit cited)")
    sys.exit(1 if r['stale'] else 0)
