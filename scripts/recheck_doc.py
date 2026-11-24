"""AGENTS.md "Findings and fixes", rule 8, and EXEC-RECHECK-LIST (the user 2026-11-24: "kayaknya perlu ada dibuatkan MD
untuk menampung item ini (item yang sudah di solve, tapi belum di recheck apakah perbaikannya tidak ada collateral damage
dll) ... Recheck MD perlu dimention juga di AGENTS MD dan harus di update"; "UD39 ok - masukan EXEC"; "Untuk 2-5 bisa
go"): RECHECK.md, the list of every fix no agent other than its author tested out, across executions, written from its one
source, verification/records/recheck_ledger.json (one row per finding, keyed by run plus finding id).

    python3 scripts/recheck_doc.py --write    rewrite RECHECK.md from the ledger
    python3 scripts/recheck_doc.py --check    exit 1 when RECHECK.md is not what the ledger gives
    python3 scripts/recheck_doc.py --sites    after a deploy: where each fix runs (runs_on) from
                                              verification/records/deployed_commits.json, then RECHECK.md

RECHECK.md depends on the ledger only (no git), so its check runs on a shallow clone
(.github/workflows/generated-files.yml, scripts/tests/test_recheck_doc.py). The ledger's guard, which reads git, is
scripts/tests/test_recheck_ledger.py (.github/workflows/records-status.yml, full history)."""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / 'verification' / 'records' / 'recheck_ledger.json'
DOC = ROOT / 'RECHECK.md'
DEPLOYED = ROOT / 'verification' / 'records' / 'deployed_commits.json'
ERRORS = ROOT / 'ERRORS_AND_SOLUTIONS.md'
EXEC = ROOT / 'EXEC.md'

WHAT = ('The re-check ledger (AGENTS.md "Findings and fixes", rule 8; EXEC-RECHECK-LIST, the user 2026-11-24): one row '
        'per finding whose fix an agent other than its author must test out, across executions, with its re-checks. '
        'The one source of RECHECK.md (python3 scripts/recheck_doc.py --write). A fix no other agent tested out enters '
        'here in the same commit as the fix, status waiting; an approved re-check takes its items from here, gives its '
        'agents the original finding, and its results update the row (recheck, status) in the same task. The 422 rows '
        'of the step-8 ledger of EXEC-MU-ACCOUNTS moved in on 2026-11-24 (from step8_ledger; '
        'verification/records/step8_ledger.json keeps that build\'s notes, groups and critic); the rows from scan came '
        'from the ERRORS_AND_SOLUTIONS.md and EXEC.md entries that said their fix was tested by its author only.')
FIELDS = {
    'key': 'unique: the run that found it plus the finding id (errors/<M id> when no checker found it)',
    'execution': 'the EXEC.md execution the row belongs to (the step-8 rows: EXEC-MU-ACCOUNTS, step 8)',
    'area': 'the group RECHECK.md lists it under, in plain Indonesian',
    'run': 'the workflow run(s) whose journal holds the finding as its checker wrote it; empty when no checker found it',
    'finding_id': 'the id the checker gave it',
    'title': 'a short name of the finding',
    'finding': ('the original finding as its checker wrote it (run, agent, id, severity, verdict: text), or the '
                "ERRORS entry's symptom when no checker found it; empty for a row moved from the step-8 ledger, whose "
                'title and recheck_action stand for it (the checkers\' own words are in their run journals)'),
    'errors': 'the ERRORS_AND_SOLUTIONS.md entries (M ids) the row names',
    'fix_commits': 'the git commits of the fix (each must exist in git)',
    'fix_note': 'the fix as written (for a step-8 row: its fix_commit text, Railway job ids included)',
    'runs_on': ('where the fix runs: live, beta or branch (every fix commit an ancestor of that site\'s commit in '
                'deployed_commits.json; scripts/recheck_doc.py --sites), not_code (records only), none (no fix commit)'),
    'author_test': 'how the fix\'s author tested it (empty for a step-8 row: see evidence)',
    'status': 'one of STATUSES (scripts/recheck_doc.py)',
    'open_row': 'for an open row: its owner row in PLAN.md or EXEC.md (rule 1), empty when it has none',
    'recheck': ('the re-check rounds that tested it: {run, round, verdict (fixed, partly, not_fixed, cannot_tell), '
                'date, evidence}; a step-8 row\'s earlier test-outs are in tested_out_by as written'),
    'recheck_action': 'what a re-check reproduces and looks for (a step-8 row: its step8_action)',
    'tested_out_by': 'the test-out by another agent, as the step-8 ledger wrote it; none when there was none',
    'evidence': 'where the facts of the row come from',
    'from': 'step8_ledger (moved 2026-11-24), scan (the scan of 2026-11-24) or fix (entered with its fix)',
    'step8_fate': 'a step-8 row only: its fate as that ledger wrote it',
    'step8_key': 'a step-8 row only, when its key changed to be unique: the old key',
}
REQUIRED = [k for k in FIELDS if not k.startswith('step8_')]
# status: (meaning in plain Indonesian for RECHECK.md)
STATUSES = {
    'waiting': 'sudah diperbaiki, menunggu uji ulang oleh agen selain pembuatnya',
    'fixed': 'diuji ulang agen lain: beres',
    'partly': 'diuji ulang agen lain: sebagian beres, sisanya belum diperbaiki',
    'not_fixed': 'diuji ulang agen lain: belum beres',
    'cannot_tell': 'diuji ulang agen lain: tidak bisa dipastikan',
    'open': 'belum diperbaiki',
    'accepted': 'diterima user apa adanya',
    'obsolete': 'tidak berlaku lagi',
}
VERDICTS = ('fixed', 'partly', 'not_fixed', 'cannot_tell')
FROM = ('step8_ledger', 'scan', 'fix')
SITE_ORDER = ('branch', 'beta', 'live')            # a fix only moves to the right
RUNS_ON = SITE_ORDER + ('not_code', 'none')
SITE_WORD = {'live': 'live', 'beta': 'beta', 'branch': 'branch', 'not_code': 'bukan kode', 'none': 'tanpa commit'}

# The words an ERRORS_AND_SOLUTIONS.md entry or an EXEC.md line uses for a fix no other agent has tested out yet
# (AGENTS.md rule 8: "the report says the fix was tested by its author only"). Each entry saying so has a ledger row
# (scripts/tests/test_recheck_ledger.py).
AUTHOR_ONLY = re.compile(r'tested(?: out)? by (?:its|their) authors? only|not (?:yet )?tested out by (?:another|any other) '
                         r'agent|test-out joins step 8|fixed, not tested out', re.I)
MID = re.compile(r'\bM(\d{3,4})\b')


def load(path=None):
    return json.loads((path or LEDGER).read_text(encoding='utf-8'))


def dumps(ledger):
    """The ledger's one written form (the step-8 ledger's: indent 1, UTF-8 as is), so a rewrite changes only what
    changed."""
    return json.dumps(ledger, indent=1, ensure_ascii=False) + '\n'


# --- git (the guard and --sites only; RECHECK.md never reads git) -------------------------------------------------

def git(*args):
    return subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True, text=True)


def shallow():
    return git('rev-parse', '--is-shallow-repository').stdout.strip() == 'true'


def known(commit):
    return git('cat-file', '-e', f'{commit}^{{commit}}').returncode == 0


def ancestor(commit, of):
    return git('merge-base', '--is-ancestor', commit, of).returncode == 0


def site_of(commits, deployed):
    """live when the live site runs every commit, beta when the beta does, else branch."""
    for site in ('live', 'beta'):
        if all(ancestor(c, deployed[site]) for c in commits):
            return site
    return 'branch'


def refresh_sites(ledger, deployed, is_shallow=None):
    """Sets runs_on of every row with fix commits (not not_code) from the sites' commits. On a shallow clone the
    ancestry of an old commit cannot be read, so a site lower than the one written is left as written (a fix only moves
    forward; the full-history guard in CI reads it). Returns [(key, old, new)]."""
    is_shallow = shallow() if is_shallow is None else is_shallow
    changes = []
    for row in ledger['rows']:
        if row['runs_on'] == 'not_code':
            continue
        new = site_of(row['fix_commits'], deployed) if row['fix_commits'] else 'none'
        old = row['runs_on']
        if (is_shallow and old in SITE_ORDER and new in SITE_ORDER
                and SITE_ORDER.index(new) < SITE_ORDER.index(old)):
            continue
        if new != old:
            row['runs_on'] = new
            changes.append((row['key'], old, new))
    return changes


# --- the scan the guard holds -------------------------------------------------------------------------------------

def entries(text):
    """[(M id, its text)] of the ERRORS_AND_SOLUTIONS.md entries (### M<n> headings)."""
    parts = re.split(r'(?m)^(### M\d+[^\n]*)\n', text)
    return [(re.match(r'### (M\d+)', parts[i]).group(1), parts[i] + '\n' + parts[i + 1])
            for i in range(1, len(parts) - 1, 2)]


def entry_ids(text):
    """Every entry id of ERRORS_AND_SOLUTIONS.md: the ### M<n> headings and the rows of its older tables (| M<n> |)."""
    return set(re.findall(r'(?m)^### (M\d+)\b', text)) | set(re.findall(r'(?m)^\| (M\d+) \|', text))


def author_only(errors_text, exec_text):
    """{M id: where it says so}: every ERRORS entry whose text says its fix was tested by its author only (or not yet
    tested out by another agent), and every M id an EXEC.md line saying so names."""
    out = {}
    for mid, text in entries(errors_text):
        m = AUTHOR_ONLY.search(text)
        if m:
            out.setdefault(mid, f'ERRORS_AND_SOLUTIONS.md {mid}: "{m.group(0)}"')
    for n, line in enumerate(exec_text.splitlines(), 1):
        m = AUTHOR_ONLY.search(line)
        if m:
            for mid in MID.findall(line):
                out.setdefault('M' + mid, f'EXEC.md:{n}: "{m.group(0)}"')
    return out


# --- RECHECK.md ---------------------------------------------------------------------------------------------------

def cell(text):
    return ' '.join(str(text).split()).replace('|', '\\|')


def owner_row(row):
    return bool(row['open_row'].strip()) and row.get('step8_fate') != 'open_without_row'


def render(ledger):
    rows = ledger['rows']
    waiting = [r for r in rows if r['status'] == 'waiting']
    areas = {}
    for r in waiting:
        areas.setdefault(r['area'], []).append(r)
    out = [
        '# RECHECK: perbaikan yang menunggu uji ulang',
        '',
        '> Ditulis oleh `scripts/recheck_doc.py` dari `verification/records/recheck_ledger.json`. Jangan edit file ini:',
        '> ubah ledger, lalu jalankan `python3 scripts/recheck_doc.py --write` (dicek oleh',
        '> `scripts/tests/test_recheck_doc.py`).',
        '',
        'Daftar setiap perbaikan yang belum diuji oleh agen selain pembuatnya, untuk semua eksekusi (AGENTS.md "Findings',
        'and fixes", aturan 8; keputusan user 2026-11-24, EXEC-RECHECK-LIST). Ledger memuat satu baris per temuan, dengan',
        'kunci run + id temuan.',
        '',
        '- Uji ulang berjalan hanya dengan persetujuan eksplisit user, setiap kali, dengan model dan tingkat berpikir',
        '  (effort) yang dipilih user. Agen tidak pernah memulainya sendiri.',
        '- Uji ulang yang disetujui mengambil itemnya dari daftar di bawah. Setiap agen menerima temuan asli dari ledger',
        '  (`finding`; untuk baris dari ledger langkah 8: `title` dan `recheck_action`), bukan ringkasan perbaikan.',
        '- Agen mereproduksi kegagalan asli, mencari mekanisme yang sama di tempat lain, dan memeriksa collateral damage:',
        '  tes dari file yang disentuh commit perbaikan, serta halaman dan worker yang memakai file itu.',
        '- Hasilnya (fixed, partly, not fixed, cannot tell) ditulis ke ledger di tugas yang sama, lalu file ini ditulis',
        '  ulang.',
        '',
        f'## Menunggu uji ulang: {len(waiting)} item',
        '',
        '"Berjalan di" adalah tempat commit perbaikan berjalan (`verification/records/deployed_commits.json`): live, beta,',
        'branch (belum di-deploy), bukan kode (catatan saja), tanpa commit (tidak ada commit yang disebut).',
        '',
        '| Area | Eksekusi | Item | live | beta | branch | bukan kode | tanpa commit |',
        '|---|---|---|---|---|---|---|---|',
    ]
    for area, items in areas.items():
        execs = ', '.join(dict.fromkeys(r['execution'] for r in items))
        n = {s: sum(r['runs_on'] == s for r in items) for s in RUNS_ON}
        out.append(f'| {cell(area)} | {execs} | {len(items)} | {n["live"]} | {n["beta"]} | {n["branch"]} | '
                   f'{n["not_code"]} | {n["none"]} |')
    twice = [r['key'] for r in waiting if len(r['recheck']) >= 2]
    if twice:
        out += ['', f'{len(twice)} item sudah dua ronde diuji ulang. Aturan 8 membolehkan paling banyak dua ronde, lalu '
                'sisanya masuk', 'register keputusan; uji berikutnya hanya dengan keputusan user:', '']
        out += [f'- `{k}`' for k in twice]
    for area, items in areas.items():
        out += ['', f'### {area} ({len(items)})', '',
                '| Kunci | Temuan | Commit perbaikan | Berjalan di | ERRORS | Ronde uji ulang sebelumnya |',
                '|---|---|---|---|---|---|']
        for r in items:
            commits = ', '.join(f'`{c}`' for c in r['fix_commits']) or '-'
            out.append(f'| `{cell(r["key"])}` | {cell(r["title"])} | {commits} | {SITE_WORD[r["runs_on"]]} | '
                       f'{", ".join(r["errors"]) or "-"} | {len(r["recheck"])} |')
    counts = {s: sum(r['status'] == s for r in rows) for s in STATUSES}
    opened = [r for r in rows if r['status'] == 'open']
    without = sum(not owner_row(r) for r in opened)
    out += ['', '## Hitungan per status', '', '| Status | Arti | Jumlah |', '|---|---|---|']
    out += [f'| `{s}` | {STATUSES[s]} | {counts[s]} |' for s in STATUSES]
    out += [f'| **Total** | | **{len(rows)}** |', '',
            f'Dari {len(opened)} baris `open`, {len(opened) - without} punya baris pemilik di PLAN.md atau EXEC.md dan '
            f'{without} belum', '(aturan 1: setiap bagian yang terbuka butuh pemilik dan pemicu).', '']
    return '\n'.join(out)


def main(argv):
    if argv == ['--write']:
        DOC.write_text(render(load()), encoding='utf-8')
        return 0
    if argv == ['--check']:
        if DOC.read_text(encoding='utf-8') != render(load()):
            print('RECHECK.md is not what verification/records/recheck_ledger.json gives: run '
                  'python3 scripts/recheck_doc.py --write')
            return 1
        return 0
    if argv == ['--sites']:
        ledger = load()
        deployed = json.loads(DEPLOYED.read_text(encoding='utf-8'))
        changes = refresh_sites(ledger, deployed)
        for key, old, new in changes:
            print(f'{key}: {old} -> {new}')
        if shallow():
            print('a shallow clone: a site lower than the one written is left as written (CI reads the full history)')
        LEDGER.write_text(dumps(ledger), encoding='utf-8')
        DOC.write_text(render(ledger), encoding='utf-8')
        print(f'{len(changes)} rows changed; RECHECK.md rewritten')
        return 0
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
