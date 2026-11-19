"""EXEC-MU-ACCOUNTS fix round (records track, re-check R1-44): static/edge-session.js is the build of the shared session
module, compared by the generator itself.

tests/test_storage_registry.py compares only the source sha256 named in the copy's first line, so a hand edit of the
copy's body (a merge conflict, a quick fix) kept every suite green while the shell served code that differs from the
tested source (sign-out clearing, the CSRF retry). `node shared/build-shell.mjs --check` rebuilds the copy in memory
and compares every byte (and, since the fix round's plans track, catalog/storage_sync.json with it). AGENTS.md
"Generated files": a file written by a script has a test marked generated_file that compares it with what the script
writes now; .github/workflows/generated-files.yml runs these tests on every push and pull request, and
scripts/tests/test_generated_files.py finds this generator by its `--check` flag.

The generator needs the esbuild of the Terminal page (`npm ci` in apps/edge-bff/terminal). Without it the test skips
on a developer machine; in CI (EDGE_TEST_REQUIRE_NODE=1) it fails instead, so a missing install never passes unseen.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.generated_file

EDGE = Path(__file__).resolve().parents[1]


def test_the_shell_copy_of_the_session_module_is_its_build():
    missing = [what for what, ok in (('node', shutil.which('node')),
                                     ('the Terminal page\'s esbuild (npm ci in apps/edge-bff/terminal)',
                                      (EDGE / 'terminal/node_modules/esbuild/package.json').is_file())) if not ok]
    if missing:
        if os.environ.get('EDGE_TEST_REQUIRE_NODE') == '1':
            pytest.fail(f'shared/build-shell.mjs --check cannot run here: {", ".join(missing)} missing')
        pytest.skip(f'shared/build-shell.mjs --check needs {", ".join(missing)}')
    run = subprocess.run(['node', 'shared/build-shell.mjs', '--check'], cwd=EDGE, capture_output=True, text=True,
                         timeout=120)
    assert run.returncode == 0, (f'{run.stdout}{run.stderr}static/edge-session.js is not the build of '
                                 'shared/edge-session.ts: run `node shared/build-shell.mjs` from apps/edge-bff and '
                                 'commit its output (never edit the copy by hand)')


def test_a_hand_edit_of_the_copy_is_caught(tmp_path):
    """The comparison is of the whole file, not its first line: the edit the re-check made (removeItem -> getItem in
    the body, first line kept) fails the check."""
    if not shutil.which('node') or not (EDGE / 'terminal/node_modules/esbuild/package.json').is_file():
        if os.environ.get('EDGE_TEST_REQUIRE_NODE') == '1':
            pytest.fail('node or the Terminal page\'s esbuild is missing')
        pytest.skip('needs node and the Terminal page\'s esbuild')
    copy = tmp_path / 'edge'
    for part in ('shared', 'static', 'catalog'):
        shutil.copytree(EDGE / part, copy / part)
    (copy / 'terminal').mkdir()
    shutil.copy(EDGE / 'terminal/package.json', copy / 'terminal/package.json')
    os.symlink(EDGE / 'terminal/node_modules', copy / 'terminal/node_modules')
    shell = copy / 'static/edge-session.js'
    text = shell.read_text()
    assert 'removeItem(' in text
    shell.write_text(text.replace('removeItem(', 'getItem(', 1))
    run = subprocess.run(['node', 'shared/build-shell.mjs', '--check'], cwd=copy, capture_output=True, text=True,
                         timeout=120)
    assert run.returncode == 1, run.stdout + run.stderr
