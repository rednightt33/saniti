"""SECTOR_FORMULAS.md describes the Sector Analysis code (EXEC-SECTOR-ANALYSIS S0; AGENTS.md "Mandatory workflow", the
Overview's rule applied to the Sector Analysis). Without a database: the constants and fingerprints written in the
document equal those of sector.py and of the newest migration defining refresh_feature_08_day and feature_08_weight
(scripts/sector_formulas_doc.py --repo), and the explanation was written for those fingerprints. The functions as dev
holds them are compared by --check once migration 20261126_001 is applied on dev."""
import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.generated_file

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import sector_formulas_doc as doc  # noqa: E402


def test_the_document_names_the_sector_analysis_code():
    run = subprocess.run([sys.executable, str(ROOT / 'scripts/sector_formulas_doc.py'), '--repo'], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr


def test_every_constant_and_both_functions_are_found():
    assert set(doc.publisher_constants()) == {n for n, _ in doc.CONSTANTS}
    assert doc.publisher_constants()['DAY_DATES'] == 20 and doc.publisher_constants()['PERIODS']['1Y'] == 252
    fns = doc.migration_functions()
    assert set(fns) == set(doc.FUNCTIONS) and all(len(fp) == 32 for _, fp in fns.values())
    assert doc.fingerprints()['sector.py'] == hashlib.md5(doc.PUBLISHER.read_bytes()).hexdigest()


def test_a_changed_formula_is_reported_with_the_way_out(monkeypatch):
    text = doc.DOC.read_text()
    assert doc.problems(text) == []
    moved = dict(doc.fingerprints(), **{'refresh_feature_08_day': 'b' * 32})
    monkeypatch.setattr(doc, 'fingerprints', lambda: moved)
    out = doc.problems(text)
    assert any('explanation was written for another version of refresh_feature_08_day' in p for p in out)
    stale = text.replace('| `STATUS_CAP` | 300 |', '| `STATUS_CAP` | 250 |')
    monkeypatch.undo()
    assert any('--write' in p for p in doc.problems(stale))
