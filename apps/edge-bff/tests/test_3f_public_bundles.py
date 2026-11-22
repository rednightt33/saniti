"""3f (EXEC option A item 4; CONTRACT.md 8 "Lab code"): no file served without the admin check carries a lab item.

- Every file of the public builds (each page's build, its Web Worker files included) and of the shell (static/) is
  scanned for the lab items of the release file: each lab item's id, and a lab indicator's formula key. The lab builds
  (static/terminal-app-lab, the Backtest's dist-lab) are served to the admin on the beta only (tests/test_3f_lab_pages.py)
  and are not scanned.
- The proof builds (round 2 of the checker, 2026-11-21: the fixtures had entered through the filter they tested, so a
  bundle built without it lost them and passed): on a copy of apps/edge-bff, terminal/tests/lab/plant.mjs writes fixture
  items into every registry the filter knows, on disk, one released, one lab and one the release file does not list, each
  with a marker of its own, imports every registry from every page and Web Worker entry, and gives the lab module a
  formula marker. Every page is then built there with its own configuration, unchanged. Each bundle file of a public
  build carries every released marker (the plant reached it) and no other; each one of a lab build carries every marker;
  the lab formula is in the lab builds only; and each build names only its own files, under its own base.
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
# (the admin page's build, admin/dist -> static/admin-app, is not public either: main.py serves it to the beta's admin
# only, page_app admin_only, tests/test_admin_page.py; so it is outside this scan, as the lab builds are)
TEXT = {'.js', '.mjs', '.html', '.css', '.json', '.svg', '.txt'}
REGISTRY_KEYS = {'terminal/src/data/indRegistry.json': lambda d: d, 'backtest/src/core/backtest-registry.json': lambda d: d['indicators']}
PLANT = EDGE / 'terminal' / 'tests' / 'lab' / 'plant.mjs'
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


def pages():
    """The pages: each folder of apps/edge-bff holding a vite.config.ts and an index.html (shared/import-walk.mjs pages)."""
    return sorted(d.name for d in EDGE.iterdir() if (d / 'vite.config.ts').is_file() and (d / 'index.html').is_file())


def copy_of_edge(dest):
    """A copy of the pages' sources, shared/ and catalog/ (every file git tracks or would track) under dest/apps/edge-bff,
    each page's node_modules linked to the repository's."""
    repo = EDGE.parents[1]
    names = subprocess.run(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard', '--',
                            *[f'apps/edge-bff/{d}' for d in (*pages(), 'shared', 'catalog')]],
                           cwd=repo, capture_output=True, check=True).stdout.decode().split('\0')
    for rel in filter(None, names):
        if (repo / rel).is_file():
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(repo / rel, dest / rel)
    for page in pages():
        (dest / 'apps' / 'edge-bff' / page / 'node_modules').symlink_to(EDGE / page / 'node_modules')
    return dest / 'apps' / 'edge-bff'


def outputs(edge, page):
    """{'public': folder, 'lab': folder}: where the page's builds went (the Terminal's into static/, the others' into
    the page's dist folders)."""
    found = {}
    for kind, names in (('public', (f'static/{page}-app', f'{page}/dist')), ('lab', (f'static/{page}-app-lab', f'{page}/dist-lab'))):
        built = [edge / n for n in names if (edge / n / 'index.html').is_file()]
        assert len(built) <= 1, built
        if built:
            found[kind] = built[0]
    return found


def own_paths(build, base):
    """[(file, path)] for each page path (/<page>-app/...) a build's index.html or script names that is not one of its
    own files: under its own base + assets/ and present there."""
    wrong = []
    for f in [build / 'index.html', *sorted((build / 'assets').glob('*.js'))]:
        for ref in re.findall(r"""["'`(](/[a-z]+-app/[^"'`)\s]*)""", f.read_text(encoding='utf-8', errors='replace')):
            if not (ref.startswith(f'{base}assets/') and (build / 'assets' / ref[len(f'{base}assets/'):]).is_file()):
                wrong.append((f.name, ref))
    return wrong


def test_the_proof_builds_keep_each_planted_item_where_it_belongs(tmp_path):
    if shutil.which('npx') is None:
        missing('node is not installed')
    for page in pages():
        if not (EDGE / page / 'node_modules').is_dir():
            missing(f'{page}/node_modules is missing (npm ci)')
    edge = copy_of_edge(tmp_path)
    r = subprocess.run(['node', str(PLANT), str(edge)], capture_output=True, text=True, timeout=120)    # the repository's script, on the copy
    assert r.returncode == 0, r.stderr[-3000:]
    plant = json.loads(r.stdout)
    released = sorted(m['R'] for m in plant['markers'].values())
    others = sorted(m[s] for m in plant['markers'].values() for s in ('L', 'U'))
    assert len(plant['markers']) == len({part for part in plant['markers']}) >= 10 and plant['entries'], plant
    labs = []
    for page in pages():
        lab_build = '--mode lab' in json.loads((edge / page / 'package.json').read_text())['scripts']['build']
        for lab in (False, True) if lab_build else (False,):
            cmd = ['npx', 'vite', 'build', '--logLevel', 'warn'] + (['--mode', 'lab'] if lab else [])
            b = subprocess.run(cmd, cwd=edge / page, capture_output=True, text=True, timeout=600)
            assert b.returncode == 0, f'{page} lab={lab}: ' + b.stdout[-2000:] + b.stderr[-2000:]
        built = outputs(edge, page)
        assert set(built) == ({'public', 'lab'} if lab_build else {'public'}), (page, built)
        for kind, folder in built.items():
            base = f'/{page}-app/lab/' if kind == 'lab' else f'/{page}-app/'
            assert own_paths(folder, base) == [], (page, kind)            # 3f round 2, CRIT-2: a lab page reads its own files
            for f in sorted((folder / 'assets').glob('*.js')):            # each bundle: the page's and each Web Worker's
                text = f.read_text(encoding='utf-8', errors='replace')
                where = f'{page} {kind} {f.name}'
                assert [m for m in released if m not in text] == [], f'{where}: the plant did not reach this bundle'
                if kind == 'public':
                    assert [m for _, m in leaks([f], others + [plant['formula']])] == [], f'{where} carries a lab item'
                else:
                    assert [m for m in others if m not in text] == [], f'{where}: a lab item is missing from the lab build'
            if kind == 'public':
                assert leaks(files_of(folder), others + [plant['formula']]) == [], page
            else:
                labs.append(page)
                mains = [f for f in (folder / 'assets').glob('index-*.js')]
                assert len(mains) == 1 and plant['formula'] in mains[0].read_text(), f'{page}: the lab formula is not in the lab build'
    assert labs == ['backtest', 'terminal'], labs
