"""3e, the example mode (ERRORS M527, the example-mode checker): an example page keeps nothing of the visitor's browser.
shared/example-storage.ts holds the frame's localStorage and sessionStorage in memory, and it must run before any other
module of the page: the Screener's layout modules and the Backtest's panel read their keys when they load. This test
derives every page whose sources call viewOnly (the view-only layer of shared/example-view.ts) and checks that its entry
imports the storage module before any other module (3f keeps '@edge-lab' the first import of a page with a lab build:
the lab module reads no storage), that the storage module imports only the side-effect-free view layer, and that the
view layer imports nothing. A new view-only page is found by its viewOnly call, never by a list here."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]                          # apps/edge-bff
STORAGE = '../../shared/example-storage.ts'
IMPORT = re.compile(r"""^\s*import\s+(?:[^'";]*?\s+from\s+)?['"]([^'"]+)['"]""", re.M)
LAB = '@edge-lab'                                                   # 3f: the lab module, first where a page has a lab build


def view_only_pages():
    """Every page folder whose sources call viewOnly( (the call, not the import or a comment)."""
    out = []
    for main in sorted(ROOT.glob('*/src/main.ts')):
        src = main.parent
        calls = [f for f in src.rglob('*.ts') if re.search(r'(?<![\w.])viewOnly\(\s*\{', f.read_text())]
        if calls:
            out.append((main.parent.parent.name, main, calls))
    return out


def test_every_view_only_page_holds_its_storage_in_memory_before_any_other_module_runs():
    pages = view_only_pages()
    assert {p for p, *_ in pages} >= {'radar', 'watchlist', 'backtest', 'screener'}, pages   # the derivation's self-test
    for page, main, calls in pages:
        assert calls == [main], f'{page}: viewOnly is called outside its entry ({calls}); call it from src/main.ts'
        imports = IMPORT.findall(main.read_text())
        first = [i for i in imports if i != LAB]
        assert imports[:1] == [LAB] or imports[:1] == [STORAGE], (page, imports[:3])
        assert first[:1] == [STORAGE], f'{page}: {STORAGE} must be the first import (after {LAB}), not {first[:1]}'


def test_the_storage_module_runs_nothing_before_itself():
    """It imports only the view layer, which imports nothing: no other module of the page can run before it."""
    storage = (ROOT / 'shared' / 'example-storage.ts').read_text()
    assert IMPORT.findall(storage) == ['./example-view.ts']
    assert IMPORT.findall((ROOT / 'shared' / 'example-view.ts').read_text()) == []
    assert re.search(r'^if \(exampleMode\(\)\) isolateStorage\(\);$', storage, re.M)


def test_the_check_sees_an_entry_that_imports_a_page_module_first(tmp_path):
    """The self-test: an entry whose first import is a page module is refused by the rule above."""
    text = "import './app.ts';\nimport '../../shared/example-storage.ts';\nviewOnly({ source: 'x', name: 'X' });\n"
    imports = IMPORT.findall(text)
    assert [i for i in imports if i != LAB][:1] != [STORAGE]
