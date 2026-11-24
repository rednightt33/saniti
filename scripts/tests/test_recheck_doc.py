"""EXEC-RECHECK-LIST (the user 2026-11-24, UD39; AGENTS.md "Findings and fixes", rule 8): RECHECK.md is written by
scripts/recheck_doc.py from verification/records/recheck_ledger.json and equals what the script writes now. It reads no
git, so it runs on the shallow clone of .github/workflows/generated-files.yml. The ledger's own guard (statuses, fix
commits in git, where each fix runs, the ERRORS entries tested by their author only) is test_recheck_ledger.py."""
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.generated_file

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import recheck_doc  # noqa: E402


def test_recheck_md_is_what_the_ledger_gives():
    run = subprocess.run([sys.executable, 'scripts/recheck_doc.py', '--check'], cwd=ROOT, capture_output=True,
                         text=True, timeout=120)
    assert run.returncode == 0, f'{run.stdout}{run.stderr} (run python3 scripts/recheck_doc.py --write)'


def test_every_waiting_row_is_listed_once_and_no_other():
    text = recheck_doc.DOC.read_text(encoding='utf-8')
    rows = recheck_doc.load()['rows']
    listed = {r['key']: text.count(f'| `{recheck_doc.cell(r["key"])}` |') for r in rows}
    assert [r['key'] for r in rows if r['status'] == 'waiting' and listed[r['key']] != 1] == []
    assert [r['key'] for r in rows if r['status'] != 'waiting' and listed[r['key']]] == []


def test_a_changed_status_changes_the_document():
    ledger = recheck_doc.load()
    before = recheck_doc.render(ledger)
    row = next(r for r in ledger['rows'] if r['status'] == 'waiting')
    row['status'] = 'fixed'
    after = recheck_doc.render(ledger)
    assert after != before and f'| `{recheck_doc.cell(row["key"])}` |' not in after
