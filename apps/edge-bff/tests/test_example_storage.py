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
# every module request of an entry, in source order: an import (side effect or bindings) and an export ... from (the
# example-mode re-check: a re-export is evaluated in that order too), at the start of a line or after a ';', read with
# the comments taken out (the test-out of 2026-11-22: "/* x */ import './app.ts';" before the storage import passed)
IMPORT = re.compile(r"""(?:^|;)\s*(?:import|export)\s+(?:[^'";]*?\s+from\s+)?['"]([^'"]+)['"]""", re.M)
LAB = '@edge-lab'                                                   # 3f: the lab module, first where a page has a lab build


def without_comments(text):
    """text with its // and /* */ comments blanked (newlines kept), string and template literals left as they are."""
    out, i, n = [], 0, len(text)
    while i < n:
        c, two = text[i], text[i:i + 2]
        if c in '\'"`':
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if text[j] == '\\' else 1
            out.append(text[i:j + 1])
            i = j + 1
        elif two == '//':
            j = text.find('\n', i)
            j = n if j < 0 else j
            out.append(' ' * (j - i))
            i = j
        elif two == '/*':
            j = text.find('*/', i + 2)
            j = n if j < 0 else j + 2
            out.append(re.sub(r'[^\n]', ' ', text[i:j]))
            i = j
        else:
            out.append(c)
            i += 1
    return ''.join(out)


def module_requests(text):
    """Every module request of a source, in source order (IMPORT over the text without its comments)."""
    return IMPORT.findall(without_comments(text))


def storage_order_refusal(text):
    """Why an entry's module requests do not run the storage module first (after the lab module), or None."""
    requests = module_requests(text)
    if not (requests[:1] == [LAB] or requests[:1] == [STORAGE]):
        return f'its first module request is {requests[:1]}'
    first = [i for i in requests if i != LAB]
    if first[:1] != [STORAGE]:
        return f'{STORAGE} must be the first module request (after {LAB}), not {first[:1]}'
    return None


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
        refusal = storage_order_refusal(main.read_text())
        assert refusal is None, f'{page}: {refusal}'


def test_the_storage_module_runs_nothing_before_itself():
    """It imports only the view layer, which imports nothing: no other module of the page can run before it."""
    storage = (ROOT / 'shared' / 'example-storage.ts').read_text()
    assert module_requests(storage) == ['./example-view.ts']
    assert module_requests((ROOT / 'shared' / 'example-view.ts').read_text()) == []
    assert re.search(r'^if \(exampleMode\(\)\) isolateStorage\(\);$', storage, re.M)


def test_the_check_sees_an_entry_that_runs_a_page_module_first():
    """The self-test, through the same rule the pages pass: an entry whose first module request is a page module, an
    import or a re-export, is refused; the storage module first, or right after the lab module, passes."""
    storage = "import '../../shared/example-storage.ts';\n"
    for first in ("import './app.ts';\n", "import { start } from './app.ts';\n", "export { start as boot0 } from './app.ts';\n",
                  "export * from './api.ts';\n", "import '@edge-lab';\nexport * from './api.ts';\n"):
        assert storage_order_refusal(first + storage + "viewOnly({ source: 'x', name: 'X' });\n"), first
    # a module request hidden after a comment or another statement on the same line (the test-out of 2026-11-22), and a
    # commented-out one that does not run
    for first in ("/* x */ import './app.ts';\n", "// note\n/* a\n b */ import { s } from './app.ts';\n",
                  "const a = 1; import './app.ts';\n", "/** doc */export * from './api.ts';\n"):
        assert storage_order_refusal(first + storage + "viewOnly({ source: 'x', name: 'X' });\n"), first
    assert storage_order_refusal("// import './app.ts';\n/* import './app.ts'; */\n" + storage) is None
    assert storage_order_refusal("/* '//' */ " + storage + "const u = 'http://x/*y';\nimport './app.ts';\n") is None
    assert storage_order_refusal(storage + "import './app.ts';\n") is None
    assert storage_order_refusal("import '@edge-lab';\n" + storage + "export * from './app.ts';\n") is None
