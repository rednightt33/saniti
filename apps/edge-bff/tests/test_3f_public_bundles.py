"""3f (EXEC option A item 4; CONTRACT.md 8 "Lab code"): no file served without the admin check carries a lab item.

- Every file of the public builds (each page's build, its Web Worker files included) and of the shell (static/) is
  scanned for the lab items of the release file: each lab item's id, and a lab indicator's formula key. The lab builds
  (static/terminal-app-lab, the Backtest's dist-lab) are served to the admin on the beta only (tests/test_3f_lab_pages.py)
  and are not scanned.
- The proof builds: the Terminal and the Backtest page are built as in production with fixture lab items added to
  their registries (terminal/tests/lab/: a technical indicator in both indicator registries and the comparison lag, and,
  in the Terminal, a Flow indicator, which its Web Worker's bundle reads) and, in the lab build, the indicator's formula as
  the lab module. The release file lists the fixtures as lab, as a real lab item is listed. The public build carries
  none of the fixtures' markers, its Web Worker file included; the lab build carries every one, which is also the
  scan's self-test (it must find what is there).
- With EDGE_TEST_REQUIRE_NODE=1 (CI's edge-bff job builds every page first) a page that is not built, or node and the
  pages' packages missing, fails instead of skipping, so the scan can never pass by having nothing to read (checker B2).
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
INDICATOR_MARKERS = ('I_LAB_PROOF', 'lab_proof_7f3a', 'Lab proof indicator 7f3a', 'LAB-PROOF-FORMULA-7f3a')
FLOW_MARKERS = ('FL_LAB_PROOF', 'Lab proof flow 7f3a', 'LAB-PROOF-FLOW-7f3a')
PROOF_MARKERS = {'terminal': INDICATOR_MARKERS + FLOW_MARKERS, 'backtest': INDICATOR_MARKERS}
REQUIRE_NODE = os.environ.get('EDGE_TEST_REQUIRE_NODE') == '1'


def missing(reason):
    """A missing build or package: a failure where CI requires node (EDGE_TEST_REQUIRE_NODE=1), else a skip."""
    if REQUIRE_NODE:
        pytest.fail(reason + ' (EDGE_TEST_REQUIRE_NODE=1: CI builds every page before the tests)')
    pytest.skip(reason)


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
    absent = [root.relative_to(EDGE).as_posix() for root in PUBLIC_BUILDS if root not in built]
    if absent:
        missing(f'pages not built: {absent} (npm run build in each)')
    files = files_of(*built) + shell_files()
    assert any(f.name.startswith('worker-') for f in files), 'the Web Worker files are scanned too'
    assert leaks(files, lab_markers()) == []


def test_the_scan_finds_a_marker_planted_in_a_public_file(tmp_path):
    """The scan's self-test on a file of its own: a whole token is found, a part of a longer name is not."""
    planted = tmp_path / 'index-abc.js'
    planted.write_text('var a={"FL99":1},b=x.FL990;')
    assert leaks([planted], {'FL99'}) == [(str(planted), 'FL99')]
    assert leaks([planted], {'FL9'}) == []


def build(app, config, out, lab, releases=None):
    env = {**os.environ, 'EDGE_LAB_PROOF_OUT': str(out), **({'EDGE_LAB_PROOF_RELEASES': str(releases)} if releases else {})}
    cmd = ['npx', 'vite', 'build', '--config', str(config), '--logLevel', 'warn'] + (['--mode', 'lab'] if lab else [])
    r = subprocess.run(cmd, cwd=EDGE / app, env=env, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    return out


def test_the_proof_builds_keep_lab_items_out_of_the_public_files_and_give_them_to_the_lab_build(tmp_path):
    if shutil.which('npx') is None:
        missing('node is not installed')
    for app in ('terminal', 'backtest'):
        if not (EDGE / app / 'node_modules').is_dir():
            missing(f'{app}/node_modules is missing (npm ci)')
    indicator = json.loads((FIXTURE / 'fixture-entry.json').read_text())
    flow = json.loads((FIXTURE / 'fixture-flow-entry.json').read_text())
    assert releases.stage_of('indicator', indicator['id']) == releases.LAB        # never in the release file
    assert releases.stage_of('flow_indicator', flow['id']) == releases.LAB
    # the release file as a real lab item meets it: the repository's, with the fixtures listed at the lab stage
    data = json.loads(releases.PATH.read_text())
    data['items'] += [{'kind': 'indicator', 'id': indicator['id'], 'stage': 'lab'},
                      {'kind': 'flow_indicator', 'id': flow['id'], 'stage': 'lab'}]
    listed = tmp_path / 'releases.json'
    listed.write_text(json.dumps(data))
    configs = {'terminal': FIXTURE / 'proof.config.mjs', 'backtest': FIXTURE / 'backtest-proof.config.mjs'}
    for app, config in configs.items():
        public = build(app, config, tmp_path / f'{app}-public', lab=False, releases=listed)
        lab = build(app, config, tmp_path / f'{app}-lab', lab=True, releases=listed)
        assert leaks(files_of(public), PROOF_MARKERS[app]) == [], app
        assert sorted({m for _, m in leaks(files_of(lab), PROOF_MARKERS[app])}) == sorted(PROOF_MARKERS[app]), app
    # the Terminal's Web Worker reads the Flow registry (checker L1): its lab file has the fixture, its public one not
    workers = {kind: [f for f in files_of(tmp_path / f'terminal-{kind}') if f.name.startswith('worker-')] for kind in ('public', 'lab')}
    assert workers['public'] and workers['lab']
    assert leaks(workers['public'], FLOW_MARKERS) == []
    assert {m for _, m in leaks(workers['lab'], FLOW_MARKERS)} >= {'FL_LAB_PROOF', 'Lab proof flow 7f3a'}
