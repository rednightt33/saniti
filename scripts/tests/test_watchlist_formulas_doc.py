"""WATCHLIST_FORMULAS.md describes the Watchlist code (EXEC-WATCHLIST L1): its generated section equals the constants,
indicator catalog, limits and fingerprints of apps/terminal-publisher/watchlist.py and apps/edge-bff/app/watchlist.py
(scripts/watchlist_formulas_doc.py --repo), and the explanation was written for those fingerprints."""
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.generated_file

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import watchlist_formulas_doc as doc  # noqa: E402


def test_the_document_names_the_watchlist_code():
    run = subprocess.run([sys.executable, str(ROOT / 'scripts/watchlist_formulas_doc.py'), '--repo'], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr


def test_every_indicator_of_the_catalog_is_in_the_document():
    text = doc.DOC.read_text()
    for key, *_ in doc.constants()['CATALOG']:
        assert f'| `{key}` |' in text, key


def test_a_changed_module_is_reported_with_the_way_out(monkeypatch):
    text = doc.DOC.read_text()
    assert doc.problems(text) == []
    moved = dict(doc.fingerprints(), **{'app/watchlist.py': 'b' * 32})
    monkeypatch.setattr(doc, 'fingerprints', lambda: moved)
    assert any('explanation was written for another version of app/watchlist.py' in p for p in doc.problems(text))
    monkeypatch.undo()
    stale = text.replace('| `EVENT_DAYS` | 30 |', '| `EVENT_DAYS` | 14 |')
    assert any('--write' in p for p in doc.problems(stale))
