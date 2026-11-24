"""EXEC-RECHECK-LIST (the user 2026-11-24, UD39: "Recheck MD perlu dimention juga di AGENTS MD dan harus di update";
AGENTS.md "Findings and fixes", rule 8): the guard of verification/records/recheck_ledger.json, the one source of
RECHECK.md. Every row is complete with known values and a unique key; every fix commit it names is in git; where each
fix runs follows verification/records/deployed_commits.json; and every ERRORS_AND_SOLUTIONS.md entry (and EXEC.md line)
that says its fix was tested by its author only has a row, found by scanning (scripts/recheck_doc.py AUTHOR_ONLY), not
from a list. The git checks need the full history (.github/workflows/records-status.yml checks out with fetch-depth 0)."""
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import recheck_doc as rd  # noqa: E402

LEDGER = rd.load()
ROWS = LEDGER['rows']
SHALLOW = rd.shallow()
RUN = re.compile(r'^wf_[0-9a-f]{8}-[0-9a-f]{3}$')
DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
# The rows moved from the step-8 ledger name no fix commit where the fix was a check to re-run, not a change
# (wf_c72ae04c-a73/deploy-compat: the mixed tree of the live edge-bff and the HEAD workers). A row entered from now on
# names its fix's commit.
NO_COMMIT = {'wf_c72ae04c-a73/deploy-compat'}


def test_rows_are_complete_with_known_values_and_unique_keys():
    keys = [r['key'] for r in ROWS]
    assert sorted(k for k in set(keys) if keys.count(k) > 1) == [], 'two rows share a key: key = run + finding id'
    problems = []
    for r in ROWS:
        k = r['key']
        problems += [f'{k}: no field {f!r}' for f in rd.REQUIRED if f not in r]
        problems += [f'{k}: unknown field {f!r} (scripts/recheck_doc.py FIELDS)' for f in r if f not in rd.FIELDS]
        if set(rd.REQUIRED) - set(r):
            continue
        if r['status'] not in rd.STATUSES:
            problems.append(f'{k}: status {r["status"]!r} is not one of {list(rd.STATUSES)}')
        if r['runs_on'] not in rd.RUNS_ON:
            problems.append(f'{k}: runs_on {r["runs_on"]!r} is not one of {list(rd.RUNS_ON)}')
        if r['from'] not in rd.FROM:
            problems.append(f'{k}: from {r["from"]!r} is not one of {list(rd.FROM)}')
        if not r['fix_commits'] and r['runs_on'] not in ('none', 'not_code'):
            problems.append(f'{k}: runs_on {r["runs_on"]} with no fix commit (none)')
        if r['fix_commits'] and r['runs_on'] == 'none':
            problems.append(f'{k}: runs_on none but it names fix commits (python3 scripts/recheck_doc.py --sites)')
        if not r['title'].strip() or not r['area'].strip() or not r['execution'].startswith('EXEC-'):
            problems.append(f'{k}: a title, an area and its execution (EXEC-...) are needed')
        rounds = [x.get('round') for x in r['recheck']]
        for x in r['recheck']:
            if not (RUN.match(str(x.get('run', ''))) and isinstance(x.get('round'), int) and x['round'] >= 1
                    and x.get('verdict') in rd.VERDICTS and DATE.match(str(x.get('date', '')))
                    and str(x.get('evidence', '')).strip()):
                problems.append(f'{k}: a re-check round needs run (wf_...), round (1, 2), verdict {rd.VERDICTS}, date '
                                f'and evidence: {x}')
        if rounds != sorted(rounds) or len(set(rounds)) != len(rounds):
            problems.append(f'{k}: its re-check rounds are not 1, 2, ... in order: {rounds}')
        if r['from'] != 'step8_ledger':
            # a row entered from now on carries what rule 8 gives the re-check: the original finding, the fix, how
            # its author tested it
            if not r['finding'].strip():
                problems.append(f'{k}: the original finding as its checker wrote it (or the entry\'s symptom)')
            if r['status'] != 'open' and not r['fix_commits'] and r['runs_on'] != 'not_code':
                problems.append(f'{k}: status {r["status"]} needs the fix commit(s)')
            if r['status'] != 'open' and not r['author_test'].strip():
                problems.append(f'{k}: how its author tested the fix (author_test)')
            if r['status'] in rd.VERDICTS and (not r['recheck'] or r['recheck'][-1]['verdict'] != r['status']):
                problems.append(f'{k}: status {r["status"]} is the verdict of its last re-check round')
        elif r['status'] == 'waiting' and not r['fix_commits'] and r['runs_on'] != 'not_code' and k not in NO_COMMIT:
            problems.append(f'{k}: waiting with no fix commit')
    assert problems == [], '\n'.join(problems)


def test_the_ledger_is_in_its_written_form():
    """scripts/recheck_doc.py --sites rewrites the file; a hand edit in another form would show as a whole-file diff."""
    assert rd.LEDGER.read_text(encoding='utf-8') == rd.dumps(LEDGER), (
        'verification/records/recheck_ledger.json: write it as json.dumps(..., indent=1, ensure_ascii=False) plus a '
        'newline (scripts/recheck_doc.py dumps)')
    assert set(LEDGER) == {'what', 'fields', 'rows'} and LEDGER['fields'] == rd.FIELDS, (
        'the ledger\'s fields block is scripts/recheck_doc.py FIELDS (change both together)')


def test_every_fix_commit_is_in_git():
    missing = sorted({c for r in ROWS for c in r['fix_commits'] if not rd.known(c)})
    if missing and SHALLOW:
        pytest.skip(f'a shallow clone lacks {missing}; .github/workflows/records-status.yml reads the full history')
    assert missing == [], (f'fix commits not in git: {missing}. Name the commit of the fix (a Railway job or '
                           'deployment id goes in fix_note, not fix_commits)')


@pytest.mark.skipif(SHALLOW, reason='a shallow clone: the ancestry of the fix commits cannot be read')
def test_where_each_fix_runs_follows_the_deployed_commits():
    deployed = json.loads(rd.DEPLOYED.read_text(encoding='utf-8'))
    copy = json.loads(json.dumps(LEDGER))
    stale = rd.refresh_sites(copy, deployed, is_shallow=False)
    assert stale == [], (f'{stale}: where these fixes run changed with a deploy (key, written, now). Run python3 '
                         'scripts/recheck_doc.py --sites after writing verification/records/deployed_commits.json '
                         '(AGENTS.md "Findings and fixes", rules 8 and 9)')


def test_every_entry_that_says_its_author_only_tested_it_has_a_row():
    said = rd.author_only(rd.ERRORS.read_text(encoding='utf-8'), rd.EXEC.read_text(encoding='utf-8'))
    named = {m for r in ROWS for m in r['errors']}
    missing = {m: where for m, where in said.items() if m not in named}
    assert missing == {}, (f'{missing}: these say a fix was tested by its author only, and no row of '
                           'verification/records/recheck_ledger.json names the entry (errors). Add its row in the same '
                           'commit as the fix (key, finding, fix_commits, author_test, status waiting), then python3 '
                           'scripts/recheck_doc.py --write (AGENTS.md rule 8)')


def test_the_scan_finds_an_entry_without_a_row_and_each_wording():
    errors = ('### M9001 — planted (2026-11-24; fixed in `abc12345` on the branch)\n\n- **Status:** fixed, tested by its '
              'author only; not deployed.\n\n### M9002 — planted\n\n- **Not tested out by another agent yet:** the '
              're-check.\n\n### M9003 — planted\n\n- these fixes were tested out by their author only\n\n'
              '### M9004 — planted\n\n- **Status:** FIXED; its test-out joins step 8.\n\n### M9005 — planted\n\n'
              '- **Status:** FIXED, tested out by wf_00000000-000.\n')
    exec_text = '| The close of ERRORS M9006, tested out by its author only | ... |\n| ERRORS M9007, done | ... |\n'
    assert sorted(rd.author_only(errors, exec_text)) == ['M9001', 'M9002', 'M9003', 'M9004', 'M9006']


def test_the_errors_entries_a_row_names_exist():
    ids = rd.entry_ids(rd.ERRORS.read_text(encoding='utf-8'))
    unknown = sorted({m for r in ROWS for m in r['errors'] if m not in ids}, key=lambda m: int(m[1:]))
    assert unknown == [], f'rows name ERRORS entries that do not exist: {unknown}'


def test_the_step8_ledger_points_here():
    """EXEC-MU-ACCOUNTS step 8 reads its rows here (execution EXEC-MU-ACCOUNTS); step8_ledger.json keeps that build's
    notes, groups and critic, without rows, so there is one copy of each row."""
    step8 = json.loads((ROOT / 'verification' / 'records' / 'step8_ledger.json').read_text(encoding='utf-8'))
    assert 'rows' not in step8 and step8['rows_moved_to'] == 'verification/records/recheck_ledger.json'
    moved = [r for r in ROWS if r['from'] == 'step8_ledger']
    assert len(moved) == step8['rows_moved'] and all(r['execution'] == 'EXEC-MU-ACCOUNTS' for r in moved)
