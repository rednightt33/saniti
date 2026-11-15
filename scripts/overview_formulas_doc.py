#!/usr/bin/env python3
"""Keeps OVERVIEW_FORMULAS.md equal to the Market Overview formulas (EXEC-OVERVIEW O1; the Radar's rule of 2026-11-15
"formula2 yang live saat ini di DEV harus selalu terupdate MDnya" applied to the Overview).

The Overview's formulas live in three places: the publisher module apps/terminal-publisher/overview.py (every figure
of the files), the page module apps/edge-bff/overview/src/model.ts (what the page arranges: universe, colour scales,
periods) and the PostgreSQL function public.overview_stock_size(date) (the tile size, replaceable by market cap).
Unlike the Radar, no threshold lives in a table: every number is in code. So:

OVERVIEW_FORMULAS.md has two parts:
  * the explanation, written by hand, in plain Indonesian with examples; its line
    `<!-- explained-for: overview.py=..., model.ts=..., overview_stock_size=... -->` names the version it explains;
  * the section between `<!-- overview-live:start -->` and `<!-- overview-live:end -->`, written by this script from
    the repository: the constants of both modules and the fingerprints (md5 of overview.py and model.ts, md5 of the
    function body in its newest migration, the text between the dollar quotes, as pg_proc.prosrc keeps it).

  python3 scripts/overview_formulas_doc.py --write   rewrite the generated section from the repository (no database)
  python3 scripts/overview_formulas_doc.py --repo    exit 1 when the document differs from the repository
  python3 scripts/overview_formulas_doc.py --check   --repo, and the function as dev holds it equals the document's
                                                     (read-only: DATABASE_URL, else pgweb)

overview.py's fingerprint is also the publisher's CODE (it rebuilds every Overview file when it changes, and writes it as
the last element of state.json `overview_stamp`). Where they run: scripts/tests/test_overview_formulas_doc.py on every
push (--repo) and .github/workflows/database-schema-docs.yml every day (--check). After a formula change: change the
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

DOC = ROOT / 'OVERVIEW_FORMULAS.md'
PUBLISHER = ROOT / 'apps/terminal-publisher/overview.py'
PAGE = ROOT / 'apps/edge-bff/overview/src/model.ts'
MIGRATIONS = ROOT / 'database/migrations'
FUNCTION = 'overview_stock_size'
START, END = '<!-- overview-live:start -->', '<!-- overview-live:end -->'
CONSTANTS = (('DAY_DATES', 'tanggal yang bisa dipilih (file harian)'),
             ('SERIES_SESSIONS', 'sesi pasar di overview-series'),
             ('VOL_WINDOW', 'jendela volatilitas (hari bursa)'),
             ('VOL_BASE', 'pembanding persentil volatilitas (nilai sebelumnya)'),
             ('TURNOVER_BASE', 'rata-rata turnover (tanggal broker sebelumnya)'),
             ('FOREIGN_SUM', 'net asing KPI "10D" (tanggal broker)'),
             ('FLOW_PERIODS', 'periode Foreign Flow (nama, tanggal broker)'),
             ('INTRADAY_5D', 'sesi grafik IHSG 5D (bar 1 jam)'),
             ('RECHECK_SESSIONS', 'tanggal pasar terbaru yang isi inputnya dicek setiap lari'),
             ('BREADTH_CHUNK', 'tanggal per kueri hitungan Feature 04'),
             ('BENCHMARK', 'indeks pembanding (KPI kedua)'),
             ('OTHER', 'nama sektor untuk "Undefined"'))
PAGE_VALUES = (('PERF_SCALE', r"PERF_SCALE: Record<TilePeriod, number> = (\{[^}]*\})", 'pembagi return sebelum langkah warna'),
               ('foreignScale', r'foreignScale = \(p: TilePeriod\) => ([^;]+);', 'pembagi net asing sebelum langkah warna (Rp)'),
               ('YEAR', r'export const YEAR = (\d+);', 'sesi "1Y" (grafik dan Kinerja Sektor)'),
               ('SESSIONS', r"export const SESSIONS: Record<string, number> = (\{[^}]*\})", 'sesi per periode'))


def md5(path):
    return hashlib.md5(path.read_bytes()).hexdigest()


def publisher_constants():
    """The module-level constants of overview.py, read without importing it (it needs psycopg-free imports only, but the
    script must not depend on the publisher's environment)."""
    tree = ast.parse(PUBLISHER.read_text())
    found = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in dict(CONSTANTS):
                found[name] = ast.literal_eval(node.value)
    missing = [n for n, _ in CONSTANTS if n not in found]
    if missing:
        raise SystemExit(f'overview.py no longer defines {", ".join(missing)}: update CONSTANTS in this script')
    return found


def page_values():
    text = PAGE.read_text()
    out = {}
    for name, pattern, _ in PAGE_VALUES:
        m = re.search(pattern, text)
        if not m:
            raise SystemExit(f'model.ts no longer matches the pattern of {name}: update PAGE_VALUES in this script')
        out[name] = ' '.join(m.group(1).split())
    return out


def migration_function():
    """(migration file, fingerprint) of the newest migration (by name) that defines the size function."""
    best = None
    for path in sorted(MIGRATIONS.glob('*.sql')):
        text = path.read_text(errors='replace')
        if FUNCTION not in text:
            continue
        for fn, _, body in radar.BODY.findall(text):
            if fn == FUNCTION:
                best = (path.name, hashlib.md5(body.encode()).hexdigest())
    return best or (None, None)


def fingerprints():
    return {'overview.py': md5(PUBLISHER), 'model.ts': md5(PAGE), FUNCTION: migration_function()[1]}


def fmt(v):
    if isinstance(v, tuple):
        return ', '.join(f'{a} = {b}' if isinstance(b, int) else str(a) for a, b in v) if all(isinstance(x, tuple) for x in v) \
            else ', '.join(map(str, v))
    return str(v)


def section():
    c, p, fps, (mig, _) = publisher_constants(), page_values(), fingerprints(), migration_function()
    lines = [START, '', 'Ditulis oleh `scripts/overview_formulas_doc.py --write` dari kode di repo; jangan diedit dengan tangan.', '',
             '| Konstanta publisher (`overview.py`) | Nilai | Arti |', '|---|---|---|']
    lines += [f'| `{n}` | {fmt(c[n])} | {meaning} |' for n, meaning in CONSTANTS]
    lines += ['', '| Nilai halaman (`model.ts`) | Nilai | Arti |', '|---|---|---|']
    lines += [f'| `{n}` | `{p[n]}` | {meaning} |' for n, _, meaning in PAGE_VALUES]
    lines += ['', '| Kode | Sumber | Sidik jari (md5) |', '|---|---|---|',
              f'| `overview.py` | `apps/terminal-publisher/overview.py` (= `CODE` publisher) | `{fps["overview.py"]}` |',
              f'| `model.ts` | `apps/edge-bff/overview/src/model.ts` | `{fps["model.ts"]}` |',
              f'| `{FUNCTION}` | isi fungsi di `database/migrations/{mig}` | `{fps[FUNCTION] or "TIDAK ADA"}` |', '', END]
    return '\n'.join(lines)


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
        out.append(f'OVERVIEW_FORMULAS.md has no generated section ({START} ... {END}): run --write')
    elif block != section():
        out.append('the generated section differs from the code (a constant or a fingerprint changed): run '
                   'scripts/overview_formulas_doc.py --write')
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
        print('OVERVIEW_FORMULAS written:', ', '.join(f'{k}={v}' for k, v in fingerprints().items()))
        return 0
    bad = problems(text)
    if a.check:
        rows = radar.query("SELECT md5(prosrc) FROM pg_proc WHERE oid = to_regprocedure('public.overview_stock_size(date)')")
        live = rows[0][0] if rows else None
        if live != fingerprints()[FUNCTION]:
            bad.append(f'{FUNCTION} on dev is {live or "absent"}, the newest migration defines '
                       f'{fingerprints()[FUNCTION]}: apply the migration on dev (with the user\'s go) or revert it')
    for b in bad:
        print('OVERVIEW_FORMULAS_DRIFT ' + b)
    print('OVERVIEW_FORMULAS ' + ('OK' if not bad else 'DIFFERS'))
    return 1 if bad else 0


if __name__ == '__main__':
    raise SystemExit(main())
