"""AGENTS.md "Findings and fixes", rule 9 (the user, 2026-11-22): the statuses the ERRORS_AND_SOLUTIONS.md headings claim
follow what each website runs (scripts/record_status.py against verification/records/deployed_commits.json), in both
directions (a heading that says less than the sites run, or more), and deployed_commits.json follows the deploy records
(RAILWAY_CHANGELOG.md). Needs the full git history (.github/workflows/records-status.yml checks out with fetch-depth 0);
skipped on a shallow clone."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import record_status  # noqa: E402

SHALLOW = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', '--is-shallow-repository'],
                         capture_output=True, text=True).stdout.strip() == 'true'
pytestmark = pytest.mark.skipif(SHALLOW, reason='a shallow clone: the ancestry of the cited commits cannot be read')

# Entries whose "not deployed" or "on the branch" status cites no commit, so no rule can judge them. The 37 of
# 2026-11-22 were corrected the same day (each heading names its fix's commit and where it runs; M417 and M425 settled
# from the code), so the set is empty: a new one fails (cite the fix's commit).
LEGACY = set()

# Two commits of this repository's history with a known relation: OLD is an ancestor of NEW, NEW is not of OLD.
OLD, NEW = '7819dc99', '4b35b5ed'


def test_no_heading_claims_a_status_the_sites_contradict():
    r = record_status.status()
    assert r['stale'] == [], (f'ERRORS entries whose heading status the deployed commits contradict: {r["stale"]}. '
                              'Update each heading to where its fix runs (rule 9), and keep '
                              'verification/records/deployed_commits.json the commits the sites run')
    new = sorted(set(r['unjudged']) - LEGACY)
    assert new == [], (f'{new}: a heading says not deployed or on the branch but the entry cites no commit; cite the '
                       "fix's commit (`<hex>`) in the clause that says so, so the status can be checked against the sites")


def test_the_check_catches_a_stale_heading_and_leaves_a_true_one():
    deployed = json.loads(record_status.DEPLOYED.read_text(encoding='utf-8'))
    old = deployed['live']                                   # a commit both sites run
    text = (f'### M9001 — planted (2026-11-22; fixed on the branch)\n\n- fix `{old}`\n\n'
            f'### M9002 — planted (2026-11-22; on the live site)\n\n- fix `{old}`\n\n'
            '### M9003 — planted (2026-11-22; fixed on the branch)\n\n- no commit\n')
    r = record_status.status(text, deployed)
    assert [m for m, _ in r['stale']] == ['M9001'] and r['unjudged'] == ['M9003']


def test_the_check_catches_an_overclaim_on_either_site():
    """The tester's probe (2026-11-22): 'on the live site' and 'on the beta' citing a commit neither site runs passed."""
    deployed = {'beta': OLD, 'live': OLD}                    # both sites run OLD; NEW is not run anywhere
    text = (f'### M9101 — planted (2026-11-22; FIXED, on the live site)\n\n- fix `{NEW}`\n\n'
            f'### M9102 — planted (2026-11-22; FIXED, on the beta)\n\n- fix `{NEW}`\n\n'
            f'### M9103 — planted (2026-11-22; FIXED in `{NEW}`, on the live site)\n\n- body\n\n'
            f'### M9104 — planted (2026-11-22; FIXED in `{NEW}`, on the beta)\n\n- body\n\n'
            f'### M9105 — planted (2026-11-22; FIXED in `{OLD}`, on the live site)\n\n- body\n\n'
            f'### M9106 — planted (2026-11-22; FIXED, on the live site)\n\n- fix `{OLD}`, a later note `{NEW}`\n')
    r = record_status.status(text, deployed)
    assert [m for m, _ in r['stale']] == ['M9101', 'M9102', 'M9103', 'M9104'], r


def test_a_mixed_heading_is_judged_clause_by_clause():
    """A heading with a live part and a branch part: each clause by the commit it names."""
    text = (f'### M9201 — planted (2026-11-22; fixed in `{OLD}`, on the live site; a part fixed in `{NEW}` on the branch, '
            'not deployed)\n\n- body\n\n'
            f'### M9202 — planted (2026-11-22; fixed in `{OLD}`, on the live site; a part on the branch)\n\n- `{NEW}`\n')
    # NEW not run anywhere yet: both true, but M9202's branch part names no commit of its own, so it cannot be judged
    r = record_status.status(text, {'beta': OLD, 'live': OLD})
    assert r['stale'] == [] and r['unjudged'] == ['M9202'], r
    # the beta now runs NEW: M9201's branch part says less than the beta runs
    r = record_status.status(text, {'beta': NEW, 'live': OLD})
    assert [m for m, _ in r['stale']] == ['M9201'] and 'the beta runs' in r['stale'][0][1], r
    # and an 'on the beta' clause naming a commit the live site now runs says less than the live site runs
    r = record_status.status(f'### M9203 — planted (2026-11-22; FIXED in `{OLD}`, on the beta)\n\n- body\n',
                             {'beta': NEW, 'live': NEW})
    assert [m for m, _ in r['stale']] == ['M9203'], r


def test_the_status_part_is_the_last_group_with_its_nested_parentheses():
    h = '### M1 — a title (with a note) (2026-11-22; fixed on fix-int2 (`613c3925`), on the live site)'
    assert record_status.status_part(h) == '(2026-11-22; fixed on fix-int2 (`613c3925`), on the live site)'


def test_the_deployed_commits_are_known_and_the_live_one_is_the_betas_ancestor():
    d = json.loads(record_status.DEPLOYED.read_text(encoding='utf-8'))
    assert record_status.known(d['beta']) and record_status.known(d['live'])
    assert record_status.ancestor(d['live'], d['beta'])     # the live site runs only what the beta ran first


def test_the_deployed_commits_are_the_ones_the_newest_deploy_entries_name():
    bad = record_status.deployed_unrecorded()
    assert bad == [], (f'{bad}: at each deploy, write the commit the site runs (its latest SUCCESS deployment) in '
                       'verification/records/deployed_commits.json and a RAILWAY_CHANGELOG.md entry naming the service '
                       'and that commit, in the same commit')


def test_the_deploy_record_check_catches_a_file_the_changelog_does_not_name():
    log = (f'# Railway changelog\n\n## 2026-11-23 — something on the beta\n\n- **Commit `{NEW}`:** `edge-bff` SUCCESS\n'
           f'- **Live:** unchanged (`edge-bff-live` stays on `{OLD}`)\n\n## 2026-11-20 — older\n\n- `edge-bff` `{OLD}`\n')
    assert record_status.deployed_unrecorded({'beta': NEW, 'live': OLD}, log) == []
    bad = record_status.deployed_unrecorded({'beta': OLD, 'live': OLD}, log)      # the file not updated at the deploy
    assert [s for s, _ in bad] == ['beta'], bad
    bad = record_status.deployed_unrecorded({'beta': NEW, 'live': NEW}, log)      # the live site moved without a record
    assert [s for s, _ in bad] == ['live'], bad
