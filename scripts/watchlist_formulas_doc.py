#!/usr/bin/env python3
"""Keeps WATCHLIST_FORMULAS.md equal to the Watchlist code (EXEC-WATCHLIST L1; the Radar's and Overview's rule
"formula2 yang live saat ini di DEV harus selalu terupdate MDnya" applied to the Watchlist).

The Watchlist's figures live in the publisher module apps/terminal-publisher/watchlist.py (every value of the daily
file: which stored column, at which date) and its limits in apps/edge-bff/app/watchlist.py. No formula lives in the
database (every value is a stored column read as it is), so there is nothing to compare on dev.

WATCHLIST_FORMULAS.md has two parts:
  * the explanation, written by hand, in plain Indonesian with examples; its line
    `<!-- explained-for: watchlist.py=..., app/watchlist.py=... -->` names the version it explains;
  * the section between `<!-- watchlist-live:start -->` and `<!-- watchlist-live:end -->`, written by this script from
    the repository: the constants, the indicator catalog with its source column, the limits and the fingerprints.

  python3 scripts/watchlist_formulas_doc.py --write   rewrite the generated section from the repository
  python3 scripts/watchlist_formulas_doc.py --repo    exit 1 when the document differs from the repository

Where it runs: scripts/tests/test_watchlist_formulas_doc.py on every push (generated-files workflow). After a change of
either module: run --write, update the explanation and its explained-for line, commit them together.
"""
import argparse
import ast
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / 'WATCHLIST_FORMULAS.md'
PUBLISHER = ROOT / 'apps/terminal-publisher/watchlist.py'
API = ROOT / 'apps/edge-bff/app/watchlist.py'
START, END = '<!-- watchlist-live:start -->', '<!-- watchlist-live:end -->'
CONSTANTS = (('SCHEMA', 'versi format file'),
             ('TREND_SESSIONS', 'jumlah penutupan di garis Trend (sesi bursa)'),
             ('EVENT_DAYS', 'aksi korporasi sesudah tanggal harga (hari kalender)'),
             ('RADAR_LEVEL', 'level Radar untuk badge dan filter (bawaan halaman Radar)'),
             ('RADAR_GATE', 'gerbang Radar untuk badge dan filter (bawaan halaman Radar)'),
             ('DEFAULT_INDICATORS', 'indikator bawaan list baru (empat pertama tampil di kartu)'))
LIMITS = (('LISTS', 'list per akun'), ('PER_LIST', 'saham per list (juga batas bintang Screener)'),
          ('INDICATORS', 'indikator per list'), ('NAME_CHARS', 'huruf nama list'))


def md5(path):
    return hashlib.md5(path.read_bytes()).hexdigest()


def assigned(path, wanted):
    tree = ast.parse(path.read_text())
    found = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in wanted:
                found[name] = ast.literal_eval(node.value)
    missing = [n for n in wanted if n not in found]
    if missing:
        raise SystemExit(f'{path.relative_to(ROOT)} no longer defines {", ".join(missing)}: update this script')
    return found


def constants():
    return assigned(PUBLISHER, {n for n, _ in CONSTANTS} | {'CATALOG'})


def limits():
    return assigned(API, {n for n, _ in LIMITS})


def fingerprints():
    return {'watchlist.py': md5(PUBLISHER), 'app/watchlist.py': md5(API)}


def fmt(v):
    return ', '.join(map(str, v)) if isinstance(v, (tuple, list)) else str(v)


def section():
    c, lim, fps = constants(), limits(), fingerprints()
    lines = [START, '', 'Ditulis oleh `scripts/watchlist_formulas_doc.py --write` dari kode di repo; jangan diedit dengan tangan.', '',
             '| Konstanta (`apps/terminal-publisher/watchlist.py`) | Nilai | Arti |', '|---|---|---|']
    lines += [f'| `{n}` | {fmt(c[n])} | {meaning} |' for n, meaning in CONSTANTS]
    lines += ['', '| Kunci | Nama di halaman | Kelompok | Satuan | Tanggal | Warna tanda | Kolom sumber |', '|---|---|---|---|---|---|---|']
    lines += [f'| `{k}` | {name} | {fam} | {unit} | {"broker" if d == "broker" else "harga"} | {"ya" if sg else "tidak"} | {src} |'
              for k, name, _, _, fam, unit, d, sg, src in c['CATALOG']]
    lines += ['', '| Batas (`apps/edge-bff/app/watchlist.py`) | Nilai | Arti |', '|---|---|---|']
    lines += [f'| `{n}` | {lim[n]} | {meaning} |' for n, meaning in LIMITS]
    lines += ['', '| Kode | Sidik jari (md5) |', '|---|---|']
    lines += [f'| `{k}` | `{v}` |' for k, v in fps.items()]
    lines += ['', END]
    return '\n'.join(lines)


def written(text):
    m = re.search(re.escape(START) + '.*?' + re.escape(END), text, re.S)
    return m.group(0) if m else None


def explained_for(text):
    m = re.search(r'<!-- explained-for: (.*?) -->', text)
    return dict(x.strip().split('=', 1) for x in m.group(1).split(',')) if m else {}


def problems(text):
    out = []
    block, fps = written(text), fingerprints()
    if block is None:
        out.append(f'WATCHLIST_FORMULAS.md has no generated section ({START} ... {END}): run --write')
    elif block != section():
        out.append('the generated section differs from the code (a constant, an indicator, a limit or a fingerprint '
                   'changed): run scripts/watchlist_formulas_doc.py --write')
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
    a = p.parse_args()
    text = DOC.read_text()
    if a.write:
        old, new = written(text), section()
        DOC.write_text(text.replace(old, new) if old else text.rstrip('\n') + '\n\n' + new + '\n')
        print('WATCHLIST_FORMULAS written:', ', '.join(f'{k}={v}' for k, v in fingerprints().items()))
        return 0
    bad = problems(text)
    for b in bad:
        print('WATCHLIST_FORMULAS_DRIFT ' + b)
    print('WATCHLIST_FORMULAS ' + ('OK' if not bad else 'DIFFERS'))
    return 1 if bad else 0


if __name__ == '__main__':
    raise SystemExit(main())
