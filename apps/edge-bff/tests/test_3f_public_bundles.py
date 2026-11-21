"""3f (EXEC option A item 4; CONTRACT.md 8a "Lab code"): no file served without the admin check carries a lab item.

- Every file of the public builds (each page's build, its Web Worker files included) and of the shell (static/) is
  scanned for the lab items of the release file: each lab item's id, and a lab indicator's formula key. The lab builds
  (static/terminal-app-lab, the Backtest's dist-lab) are served to the admin on the beta only (tests/test_3f_lab_pages.py)
  and are not scanned.
- The proof builds: the Terminal and the Backtest page are built as in production with one fixture lab indicator added
  to their registries (terminal/tests/lab/fixture-entry.json, never in the release file) and, in the lab build, its
  formula as the lab module (terminal/tests/lab/fixture-lab.ts). The public build carries none of the fixture's markers;
  the lab build carries every one, which is also the scan's self-test (it must find what is there).
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from app import releases

EDGE = Path(__file__).resolve().parents[1]
STATIC = EDGE / 'static'
# the public builds: what each page route serves without the admin check (app/main.py page_app), as built in the
# repository (the image copies the same folders, Dockerfile)
PUBLIC_BUILDS = (STATIC / 'terminal-app', EDGE / 'backtest' / 'dist', EDGE / 'screener' / 'dist', EDGE / 'radar' / 'dist',
                 EDGE / 'overview' / 'dist', EDGE / 'watchlist' / 'dist')
LAB_BUILDS = (STATIC / 'terminal-app-lab', EDGE / 'backtest' / 'dist-lab', STATIC / 'backtest-app-lab')
TEXT = {'.js', '.mjs', '.html', '.css', '.json', '.svg', '.txt'}
REGISTRY_KEYS = {'terminal/src/data/indRegistry.json': lambda d: d, 'backtest/src/core/backtest-registry.json': lambda d: d['indicators']}
FIXTURE = EDGE / 'terminal' / 'tests' / 'lab'
PROOF_MARKERS = ('I_LAB_PROOF', 'lab_proof_7f3a', 'Lab proof indicator 7f3a', 'LAB-PROOF-FORMULA-7f3a')


def lab_markers():
    """What would name a lab item in a file: the id of every lab item of the release file, and for a lab indicator the
    formula key its registry entries give it (the formula map is keyed by it)."""
    marks = set()
    for kind in releases.KINDS:
        for e in releases.entries(kind):
            if e['stage'] == releases.LAB:
                marks.add(e['id'])
                if kind == 'indicator':
                    for rel, entries in REGISTRY_KEYS.items():
                        marks |= {r['key'] for r in entries(json.loads((EDGE / rel).read_text())) if r.get('id') == e['id']}
    return marks


def files_of(*roots):
    """The text files under the roots (a root that is not built yet is skipped), the lab builds left out."""
    out = []
    for root in roots:
        if root.is_dir():
            out += [p for p in root.rglob('*') if p.is_file() and p.suffix in TEXT
                    and not any(p.is_relative_to(lab) for lab in LAB_BUILDS)]
    return out


def shell_files():
    """The shell's own files: static/ without the built pages under it."""
    return [p for p in STATIC.iterdir() if p.is_file() and p.suffix in TEXT]


def leaks(files, markers):
    """[(file, marker)] for each marker found in a file as a whole token (not as a part of a longer name)."""
    found = []
    for f in files:
        text = f.read_text(encoding='utf-8', errors='replace')
        for m in markers:
            if re.search(rf'(?<![\w$]){re.escape(m)}(?![\w$])', text):
                found.append((f.relative_to(EDGE).as_posix() if f.is_relative_to(EDGE) else str(f), m))
    return found


def test_no_public_file_carries_a_lab_item_of_the_release_file():
    built = [root for root in PUBLIC_BUILDS if root.is_dir()]
    if STATIC / 'terminal-app' not in built:
        pytest.skip('the Terminal page is not built (cd apps/edge-bff/terminal && npm run build)')
    files = files_of(*built) + shell_files()
    assert any(f.name.startswith('worker-') for f in files), 'the Web Worker files are scanned too'
    assert leaks(files, lab_markers()) == []


def test_the_scan_finds_a_marker_planted_in_a_public_file(tmp_path):
    """The scan's self-test on a file of its own: a whole token is found, a part of a longer name is not."""
    planted = tmp_path / 'index-abc.js'
    planted.write_text('var a={"FL99":1},b=x.FL990;')
    assert leaks([planted], {'FL99'}) == [(str(planted), 'FL99')]
    assert leaks([planted], {'FL9'}) == []


def build(app, config, out, lab):
    env = {**os.environ, 'EDGE_LAB_PROOF_OUT': str(out)}
    cmd = ['npx', 'vite', 'build', '--config', str(config), '--logLevel', 'warn'] + (['--mode', 'lab'] if lab else [])
    r = subprocess.run(cmd, cwd=EDGE / app, env=env, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    return out


@pytest.mark.skipif(shutil.which('npx') is None, reason='node is not installed')
def test_the_proof_builds_keep_a_lab_item_out_of_the_public_files_and_give_it_to_the_lab_build(tmp_path):
    for app in ('terminal', 'backtest'):
        if not (EDGE / app / 'node_modules').is_dir():
            pytest.skip(f'{app}/node_modules is missing (npm ci)')
    fixture = json.loads((FIXTURE / 'fixture-entry.json').read_text())
    assert releases.stage_of('indicator', fixture['id']) == releases.LAB        # never in the release file: lab
    assert set(PROOF_MARKERS) <= {fixture['id'], fixture['key'], fixture['name'], 'LAB-PROOF-FORMULA-7f3a'}
    configs = {'terminal': FIXTURE / 'proof.config.mjs', 'backtest': FIXTURE / 'backtest-proof.config.mjs'}
    for app, config in configs.items():
        public = build(app, config, tmp_path / f'{app}-public', lab=False)
        lab = build(app, config, tmp_path / f'{app}-lab', lab=True)
        assert leaks(files_of(public), PROOF_MARKERS) == [], app
        assert sorted({m for _, m in leaks(files_of(lab), PROOF_MARKERS)}) == sorted(PROOF_MARKERS), app
