#!/usr/bin/env python3
"""Keeps SECTOR_FORMULAS.md equal to the Sector Analysis formulas (EXEC-SECTOR-ANALYSIS S0; the Overview's rule, AGENTS.md
"Mandatory workflow", applied to the Sector Analysis).

The Sector Analysis figures live in the publisher module apps/terminal-publisher/sector.py (every figure of the files)
and in two PostgreSQL functions of migration 20261126_001: public.refresh_feature_08_day(date) (the group aggregates of
Feature_08_Group_Daily) and public.feature_08_weight(date) (the one weight basis, replaceable by market cap). The page
(apps/edge-bff/sector, part S4) computes what depends on the user's choice from those files; its model joins the
fingerprints below when it lands. So:

SECTOR_FORMULAS.md has two parts:
  * the explanation, written by hand, in plain Indonesian with examples; its line
    `<!-- explained-for: sector.py=..., refresh_feature_08_day=..., feature_08_weight=... -->` names the version it
    explains;
  * the section between `<!-- sector-live:start -->` and `<!-- sector-live:end -->`, written by this script from the
    repository: the constants of sector.py and the fingerprints (md5 of sector.py, md5 of each function body in its
    newest migration, the text between the dollar quotes, as pg_proc.prosrc keeps it).

  python3 scripts/sector_formulas_doc.py --write   rewrite the generated section from the repository (no database)
  python3 scripts/sector_formulas_doc.py --repo    exit 1 when the document differs from the repository
  python3 scripts/sector_formulas_doc.py --check   --repo, and both functions as dev holds them equal the document's
                                                   (read-only: DATABASE_URL, else pgweb)

sector.py's fingerprint is also the publisher's CODE (it rebuilds every Sector Analysis day file when it changes, and
writes it as the last element of state.json `sector_stamp`). Where they run: scripts/tests/test_sector_formulas_doc.py on
every push (--repo); --check belongs in .github/workflows/database-schema-docs.yml once migration 20261126_001 is
applied on dev (before that dev has no such function and the check would be red). After a formula change: change the
code, run --write, update the explanation and its explained-for line, commit them together.
"""
import argparse
import ast
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import radar_formulas_doc as radar  # noqa: E402  (the read-only query helper and the function-body pattern)

DOC = ROOT / 'SECTOR_FORMULAS.md'
PUBLISHER = ROOT / 'apps/terminal-publisher/sector.py'
OVERVIEW = ROOT / 'apps/terminal-publisher/overview.py'
MIGRATIONS = ROOT / 'database/migrations'
FUNCTIONS = ('refresh_feature_08_day', 'feature_08_weight')
START, END = '<!-- sector-live:start -->', '<!-- sector-live:end -->'
CONSTANTS = (('DAY_DATES', 'tanggal yang bisa dipilih (file sector-day), sama dengan Overview'),
             ('SERIES_SESSIONS', 'sesi pasar di sector-series dan sector-stocks, sama dengan Overview'),
             ('RECHECK_SESSIONS', 'tanggal pasar terbaru yang isi inputnya dicek setiap lari'),
             ('STATUS_CAP', 'batas hitungan lama status terhadap EMA (ditampilkan "300+")'),
             ('HISTORY_TICKERS', 'saham per kueri hitung mundur Feature 04'),
             ('READ_THREADS', 'file publikasi sebelumnya yang dibaca bersamaan'),
             ('PERIODS', 'sesi per periode (keputusan E, sama dengan Overview)'),
             ('RETURNS', 'return saham di file sector-day (nama, sesi pasar)'),
             ('BENCHMARK', 'indeks pembanding kedua (Beta & Correlation)'),
             ('OTHER', 'nama sektor untuk "Undefined"'),
             ('BASIS_LABELS', 'label basis bobot yang ditulis di sector-meta'),
             ('SHORT', 'nama pendek sektor (sama dengan halaman Overview)'),
             ('BACKFILL_LOCK', 'kunci advisory pengisian riwayat Feature 08'))


def md5(path):
    return hashlib.md5(path.read_bytes()).hexdigest()


def module_constants(path):
    tree = ast.parse(path.read_text())
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            out[node.targets[0].id] = node.value
    return out


def publisher_constants():
    """The module-level constants of sector.py, read without importing it; a name it takes from overview.py
    (`overview.DAY_DATES`) is read from overview.py."""
    own, ov = module_constants(PUBLISHER), module_constants(OVERVIEW)
    found = {}
    for name, _ in CONSTANTS:
        node = own.get(name)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == 'overview':
            node = ov.get(node.attr)
        if node is None:
            raise SystemExit(f'sector.py no longer defines {name}: update CONSTANTS in this script')
        found[name] = ast.literal_eval(node)
    return found


def migration_functions():
    """{function: (migration file, fingerprint)} of the newest migration (by name) that defines each function."""
    best = {}
    for path in sorted(MIGRATIONS.glob('*.sql')):
        text = path.read_text(errors='replace')
        if 'feature_08' not in text:
            continue
        for fn, _, body in radar.BODY.findall(text):
            if fn in FUNCTIONS:
                best[fn] = (path.name, hashlib.md5(body.encode()).hexdigest())
    return best


def fingerprints():
    fns = migration_functions()
    return {'sector.py': md5(PUBLISHER), **{f: (fns.get(f) or (None, None))[1] for f in FUNCTIONS}}


def fmt(v):
    if isinstance(v, dict):
        return ', '.join(f'{k} = {x}' for k, x in v.items())
    if isinstance(v, tuple):
        return ', '.join(f'{a} = {b}' if isinstance(a, str) else str(a) for a, b in v) \
            if all(isinstance(x, tuple) for x in v) else ', '.join(map(str, v))
    return str(v)


def section():
    c, fps, fns = publisher_constants(), fingerprints(), migration_functions()
    lines = [START, '', 'Ditulis oleh `scripts/sector_formulas_doc.py --write` dari kode di repo; jangan diedit dengan tangan.', '',
             '| Konstanta publisher (`sector.py`) | Nilai | Arti |', '|---|---|---|']
    lines += [f'| `{n}` | {fmt(c[n])} | {meaning} |' for n, meaning in CONSTANTS]
    lines += ['', '| Kode | Sumber | Sidik jari (md5) |', '|---|---|---|',
              f'| `sector.py` | `apps/terminal-publisher/sector.py` (= `CODE` publisher) | `{fps["sector.py"]}` |']
    lines += [f'| `{f}` | isi fungsi di `database/migrations/{(fns.get(f) or ("TIDAK ADA",))[0]}` | `{fps[f] or "TIDAK ADA"}` |'
              for f in FUNCTIONS]
    return '\n'.join(lines + ['', END])


def written(text):
    m = re.search(re.escape(START) + '.*?' + re.escape(END), text, re.S)
    return m.group(0) if m else None


def explained_for(text):
    m = re.search(r'<!-- explained-for: (.*?) -->', text)
    return dict(x.strip().split('=', 1) for x in m.group(1).split(',')) if m else {}


def problems(text):
    """Every way the document differs from the repository (empty when it is current)."""
    out = []
    block, fps = written(text), fingerprints()
    if block is None:
        out.append(f'SECTOR_FORMULAS.md has no generated section ({START} ... {END}): run --write')
    elif block != section():
        out.append('the generated section differs from the code (a constant or a fingerprint changed): run '
                   'scripts/sector_formulas_doc.py --write')
    stale = [k for k in fps if explained_for(text).get(k) != fps[k]]
    if stale:
        out.append('the explanation was written for another version of ' + ', '.join(stale) + ': read the new code, update '
                   'the explanation and set its explained-for line to the fingerprints of the generated section')
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--write', action='store_true')
    g.add_argument('--repo', action='store_true')
    g.add_argument('--check', action='store_true')
    a = p.parse_args()
    text = DOC.read_text()
    if a.write:
        old, new = written(text), section()
        DOC.write_text(text.replace(old, new) if old else text.rstrip('\n') + '\n\n' + new + '\n')
        print('SECTOR_FORMULAS written:', ', '.join(f'{k}={v}' for k, v in fingerprints().items()))
        return 0
    bad = problems(text)
    if a.check:
        rows = radar.query("SELECT p.proname, md5(p.prosrc) FROM pg_proc AS p JOIN pg_namespace AS n ON n.oid = p.pronamespace "
                           "WHERE n.nspname = 'public' AND p.proname IN ('" + "', '".join(FUNCTIONS) + "')")
        live, fps = dict(rows), fingerprints()
        for f in FUNCTIONS:
            if live.get(f) != fps[f]:
                bad.append(f'{f} on dev is {live.get(f) or "absent"}, the newest migration defines {fps[f]}: apply the '
                           'migration on dev (with the user\'s go) or revert it')
    for b in bad:
        print('SECTOR_FORMULAS_DRIFT ' + b)
    print('SECTOR_FORMULAS ' + ('OK' if not bad else 'DIFFERS'))
    return 1 if bad else 0


if __name__ == '__main__':
    raise SystemExit(main())
