"""OVERVIEW_FORMULAS.md describes the Market Overview code (EXEC-OVERVIEW O1; the Radar's rule of 2026-11-15 "formula2
yang live saat ini di DEV harus selalu terupdate MDnya" applied to the Overview). Without a database: the constants and
fingerprints written in the document equal those of overview.py, model.ts and the newest migration defining
overview_stock_size (scripts/overview_formulas_doc.py --repo), and the explanation was written for those fingerprints.
The function as dev holds it is compared every day in .github/workflows/database-schema-docs.yml (--check)."""
import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.generated_file

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import overview_formulas_doc as doc  # noqa: E402


def test_the_document_names_the_overview_code():
    run = subprocess.run([sys.executable, str(ROOT / 'scripts/overview_formulas_doc.py'), '--repo'], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr


def test_every_constant_and_the_size_function_are_found():
    assert set(doc.publisher_constants()) == {n for n, _ in doc.CONSTANTS}
    assert set(doc.page_values()) == {n for n, _, _ in doc.PAGE_VALUES}
    name, fp = doc.migration_function()
    assert name and len(fp) == 32
    assert doc.fingerprints()['overview.py'] == hashlib.md5(doc.PUBLISHER.read_bytes()).hexdigest()


def test_a_changed_formula_is_reported_with_the_way_out(monkeypatch):
    text = doc.DOC.read_text()
    assert doc.problems(text) == []
    moved = dict(doc.fingerprints(), **{'model.ts': 'b' * 32})
    monkeypatch.setattr(doc, 'fingerprints', lambda: moved)
    out = doc.problems(text)
    assert any('explanation was written for another version of model.ts' in p for p in out)
    stale = text.replace('| `VOL_WINDOW` | 20 |', '| `VOL_WINDOW` | 30 |')
    monkeypatch.undo()
    assert any('--write' in p for p in doc.problems(stale))
