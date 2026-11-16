#!/usr/bin/env python3
"""Keeps RADAR_FORMULAS.md equal to the Radar formulas that run on dev (user 2026-11-15: "formula2 yang live saat ini di
DEV harus selalu terupdate MDnya, at least untuk bagian radar dulu").

RADAR_FORMULAS.md has two parts:
  * the explanation, written by hand, in plain Indonesian with examples; its line
    `<!-- explained-for: name=fingerprint, ... -->` names the version of each Radar function it explains;
  * the section between `<!-- radar-live:start -->` and `<!-- radar-live:end -->`, written by this script: the rule
    version, every threshold of every filter and level, and the fingerprint (md5 of the body) of each Radar function.

A fingerprint is the md5 of the function body, the text between the dollar quotes. PostgreSQL keeps that text as it was
written (pg_proc.prosrc), so the same fingerprint can be computed three ways: from the live database, from the newest
applied migration that defines the function (database/migrations/APPLIED.sha256 names what is applied on dev), and as
written in the document. When the three agree, the document explains the code that runs.

  python3 scripts/radar_formulas_doc.py --write    read dev, rewrite the generated section (DATABASE_URL, else pgweb)
  python3 scripts/radar_formulas_doc.py --check    read dev, exit 1 when the document differs from it
  python3 scripts/radar_formulas_doc.py --repo     no database: exit 1 when the document differs from the applied migrations

--check and --write read only (SELECT). Where they run: .github/workflows/database-schema-docs.yml every day (--write,
commit, then --check), and scripts/tests/test_radar_formulas_doc.py on every push (--repo). After a change of a Radar
function or of a rule row: apply it on dev, run --write, update the explanation and its explained-for line, commit.
"""
import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / 'RADAR_FORMULAS.md'
MIGRATIONS = ROOT / 'database/migrations'
START, END = '<!-- radar-live:start -->', '<!-- radar-live:end -->'
FUNCTIONS = ('feature_07_below_percentile', 'feature_07_robust_z', 'feature_07_rule_version', 'refresh_feature_07',
             'refresh_feature_07_day')
LEVELS = ('loose', 'standard', 'strict')
LEVEL_ID = {'loose': 'Longgar', 'standard': 'Standar', 'strict': 'Ketat'}

RULES_SQL = ('SELECT r.filter_id, r.cond_key, r.level, r.label, r.threshold, r.threshold2, r.status, f.name, f.position '
             'FROM public."Feature_07_Radar_Rule" AS r JOIN public."Feature_07_Radar_Filter" AS f '
             'ON f.rule_version = r.rule_version AND f.filter_id = r.filter_id '
             'WHERE r.rule_version = public.feature_07_rule_version() ORDER BY f.position, r.cond_key, r.level')
FUNCTIONS_SQL = ("SELECT p.proname, md5(p.prosrc) FROM pg_proc AS p JOIN pg_namespace AS n ON n.oid = p.pronamespace "
                 "WHERE n.nspname = 'public' AND p.proname IN ('" + "', '".join(FUNCTIONS) + "') ORDER BY 1")


def query(sql):
    """Rows of a read-only statement: DATABASE_URL in a read-only session when set (the daily workflow), else pgweb."""
    url = os.environ.get('DATABASE_URL')
    if url:
        import psycopg
        with psycopg.connect(url, autocommit=True, connect_timeout=30,
                             options='-c default_transaction_read_only=on -c statement_timeout=30000') as c:
            return [list(r) for r in c.execute(sql).fetchall()]
    sys.path.insert(0, str(ROOT / 'verification/terminal_api'))
    import pgq
    r = pgq.q(sql)
    if 'error' in r:
        raise SystemExit(f'pgweb refused the read: {str(r["error"])[:300]}')
    return r['rows']


def live():
    """(rule version, rule rows, {function: fingerprint}) as dev holds them now."""
    version = query('SELECT public.feature_07_rule_version()')[0][0]
    return version, query(RULES_SQL), dict(query(FUNCTIONS_SQL))


BODY = re.compile(r'CREATE (?:OR REPLACE )?FUNCTION public\.(\w+)\s*\(.*?\bAS\s+(\$\w*\$)(.*?)\2', re.S)


def applied():
    """{function: fingerprint} of the newest migration in APPLIED.sha256 (file order) that defines each Radar function."""
    names = [line.split('  ', 1)[1] for line in (MIGRATIONS / 'APPLIED.sha256').read_text().splitlines()
             if line and not line.startswith('#') and '  ' in line]
    out = {}
    for name in names:
        path = MIGRATIONS / name
        if not path.exists() or 'feature_07' not in path.read_text(errors='replace'):
            continue
        for fn, _, body in BODY.findall(path.read_text()):
            if fn in FUNCTIONS:
                out[fn] = hashlib.md5(body.encode()).hexdigest()
    return out


def num(v):
    if v is None:
        return '—'
    v = float(v)
    return str(int(v)) if v == int(v) else f'{v:g}'


def section(version, rules, fingerprints):
    """The generated section's text."""
    lines = [START, '', f'Versi aturan di dev: **`{version}`**. Ditulis oleh `scripts/radar_formulas_doc.py --write` dari tabel '
             '`Feature_07_Radar_Rule` dan `Feature_07_Radar_Filter` di dev; jangan diedit dengan tangan.', '',
             '| Filter | Syarat | Bunyi syarat di halaman (Standar) | Longgar | Standar | Ketat | Status |',
             '|---|---|---|---:|---:|---:|---|']
    by = {}
    for fid, cond, level, label, t, t2, status, name, pos in rules:
        by.setdefault((pos, fid, name, cond), {})[level] = (label, t, t2, status)
    for (pos, fid, name, cond), lv in sorted(by.items()):
        label = (lv.get('standard') or next(iter(lv.values())))[0]
        cells = []
        for level in LEVELS:
            if level not in lv:
                cells.append('—')
                continue
            _, t, t2, _ = lv[level]
            cells.append(num(t) + (f' / {num(t2)}' if t2 is not None else ''))
        status = sorted({x[3] for x in lv.values()})
        lines.append(f'| {fid} ({name}) | {cond} | {label} | {" | ".join(cells)} | {", ".join(status)} |')
    lines += ['', 'Angka kedua (`a / b`) adalah `threshold2`: S1 Ketat = persentil / z minimum; S6Δ Both = kenaikan rasio / '
              'kenaikan peringkat. S8 hanya punya satu tingkat (Strong dan Watch dibedakan oleh syarat C).', '',
              '| Fungsi di dev | Sidik jari (md5 isi fungsi) |', '|---|---|']
    for fn in FUNCTIONS:
        lines.append(f'| `{fn}` | `{fingerprints.get(fn, "TIDAK ADA")}` |')
    lines += ['', END]
    return '\n'.join(lines)


def explained_for(text):
    m = re.search(r'<!-- explained-for: (.*?) -->', text)
    return dict(x.strip().split('=', 1) for x in m.group(1).split(',')) if m else {}


def written(text):
    m = re.search(re.escape(START) + '.*?' + re.escape(END), text, re.S)
    return m.group(0) if m else None


def fingerprints_in(block):
    return dict(re.findall(r'\| `(\w+)` \| `([0-9a-f]{32}|TIDAK ADA)` \|', block or ''))


def problems(text, version, rules, fps):
    """Every way the document differs from what it must describe (empty when it is current)."""
    out = []
    block = written(text)
    if block is None:
        out.append(f'RADAR_FORMULAS.md has no generated section ({START} ... {END}): run --write')
    elif block != section(version, rules, fps):
        changed = [fn for fn in FUNCTIONS if fingerprints_in(block).get(fn) != fps.get(fn)]
        out.append('the generated section differs from dev (' + (f'functions changed: {", ".join(changed)}' if changed
                   else 'rule version, thresholds, labels or status') + '): run scripts/radar_formulas_doc.py --write')
    stale = [fn for fn in FUNCTIONS if explained_for(text).get(fn) != fps.get(fn)]
    if stale:
        out.append('the explanation was written for another version of ' + ', '.join(stale) + ': read the new code, '
                   'update the explanation and set its explained-for line to the fingerprints of the generated section')
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--write', action='store_true')
    g.add_argument('--check', action='store_true')
    g.add_argument('--repo', action='store_true')
    a = p.parse_args()
    text = DOC.read_text()
    if a.repo:
        want, have = applied(), fingerprints_in(written(text))
        bad = [f'{fn}: document {have.get(fn)}, newest applied migration {want.get(fn)}' for fn in FUNCTIONS
               if have.get(fn) != want.get(fn)]
        bad += [f'{fn}: explained for {explained_for(text).get(fn)}, generated {have.get(fn)}' for fn in FUNCTIONS
                if explained_for(text).get(fn) != have.get(fn)]
        for b in bad:
            print('RADAR_FORMULAS_DRIFT ' + b)
        print('RADAR_FORMULAS ' + ('OK' if not bad else 'DIFFERS: after applying a Radar migration on dev, run '
                                   'scripts/radar_formulas_doc.py --write and update the explanation'))
        return 1 if bad else 0
    version, rules, fps = live()
    if a.write:
        new = section(version, rules, fps)
        old = written(text)
        text = text.replace(old, new) if old else text.rstrip('\n') + '\n\n' + new + '\n'
        DOC.write_text(text)
        print(f'RADAR_FORMULAS written: {version}, {len(rules)} rule rows, {len(fps)} functions')
        return 0
    bad = problems(text, version, rules, fps)
    for b in bad:
        print('RADAR_FORMULAS_DRIFT ' + b)
    print('RADAR_FORMULAS ' + ('OK: the document describes what runs on dev' if not bad else 'DIFFERS'))
    return 1 if bad else 0


if __name__ == '__main__':
    raise SystemExit(main())
