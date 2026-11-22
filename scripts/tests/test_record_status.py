"""AGENTS.md "Findings and fixes", rule 9 (the user, 2026-11-22): the statuses the ERRORS_AND_SOLUTIONS.md headings claim
follow what each website runs (scripts/record_status.py against verification/records/deployed_commits.json). Needs the
full git history (.github/workflows/records-status.yml checks out with fetch-depth 0); skipped on a shallow clone."""
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

# The entries of 2026-11-22 whose "not deployed" or "on the branch" heading cites no commit, so no rule can judge them
# (rule 9 was written that day). Frozen: a new one fails (cite the fix's commit); one that leaves this list by citing its
# commit or changing its status leaves it here too.
LEGACY = {'M387', 'M388', 'M389', 'M390', 'M400', 'M401', 'M417', 'M409', 'M410', 'M408', 'M406', 'M407', 'M425',
          'M532', 'M526', 'M524', 'M522', 'M521', 'M518', 'M516', 'M503', 'M501', 'M499', 'M498', 'M497', 'M496',
          'M495', 'M494', 'M493', 'M492', 'M491', 'M489', 'M488', 'M486', 'M485', 'M484', 'M483'}


def test_no_heading_claims_a_status_the_sites_contradict():
    r = record_status.status()
    assert r['stale'] == [], (f'ERRORS entries whose heading status the deployed commits contradict: {r["stale"]}. '
                              'Update each heading to where its fix runs (rule 9), and keep '
                              'verification/records/deployed_commits.json the commits the sites run')
    new = sorted(set(r['unjudged']) - LEGACY)
    assert new == [], (f'{new}: a heading says not deployed or on the branch but the entry cites no commit; cite the '
                       "fix's commit (`<hex>`) so the status can be checked against the sites")


def test_the_check_catches_a_stale_heading_and_leaves_a_true_one():
    deployed = json.loads(record_status.DEPLOYED.read_text(encoding='utf-8'))
    old = deployed['live']                                   # a commit both sites run
    text = (f'### M9001 — planted (2026-11-22; fixed on the branch)\n\n- fix `{old}`\n\n'
            f'### M9002 — planted (2026-11-22; on the live site)\n\n- fix `{old}`\n\n'
            '### M9003 — planted (2026-11-22; fixed on the branch)\n\n- no commit\n')
    r = record_status.status(text, deployed)
    assert [m for m, _ in r['stale']] == ['M9001'] and r['unjudged'] == ['M9003']


def test_the_deployed_commits_are_known_and_the_live_one_is_the_betas_ancestor():
    d = json.loads(record_status.DEPLOYED.read_text(encoding='utf-8'))
    assert record_status.known(d['beta']) and record_status.known(d['live'])
    assert record_status.ancestor(d['live'], d['beta'])     # the live site runs only what the beta ran first
