#!/usr/bin/env python3
"""The final Flow indicator workbook for the user (request 2026-10-31: "Excel finalnya").

FLOW_INDICATORS_SPEC.xlsx is the agreed contract (user decisions 2026-10-30) and stays unchanged: the Terminal's registry
is generated from it (`scripts/build_flow_registry.py --check`). This script copies its sheets as they are and adds:
- Rumus_Kode: the exact formula of every indicator and the shared conventions, read from FORMULAS.md (what
  `apps/edge-bff/terminal/src/calc/flow.ts` computes);
- Perubahan: what changed after the spreadsheet was agreed (reviews and decisions of 2026-10-30 and 2026-10-31);
- Versi: the sources, their sha256 and the registry check;
- Semua_Indikator (2026-10-31, user: "versi finalnya yang ada FL01 sampai latest termasuk indikator di screener"): one
  row per indicator the code offers: the Terminal's Flow indicators (flowRegistry.json), the 53 technical indicators of
  the Terminal, the Backtest and the Screener (indRegistry.json, backtest-registry.json, INDICATOR_SPEC.md), and the
  Screener's other metrics (screener-metrics.json), with the Screener's live availability (catalog_dump_dev.py output).

  python3 verification/terminal_api/flow_indicators/build_final_workbook.py <out.xlsx> [<screener catalog.json>]
"""
import hashlib
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SPEC = HERE / 'FLOW_INDICATORS_SPEC.xlsx'
FORMULAS = HERE / 'FORMULAS.md'
REGISTRY = ROOT / 'apps/edge-bff/terminal/src/data/flowRegistry.json'
FLOW_TS = ROOT / 'apps/edge-bff/terminal/src/calc/flow.ts'
IND_REG = ROOT / 'apps/edge-bff/terminal/src/data/indRegistry.json'
BT_REG = ROOT / 'apps/edge-bff/backtest/src/core/backtest-registry.json'
SC_REG = ROOT / 'apps/edge-bff/screener/src/core/screener-registry.json'
SC_METRICS = ROOT / 'apps/edge-bff/screener/src/core/screener-metrics.json'
IND_SPEC = ROOT / 'verification/terminal_api/INDICATOR_SPEC.md'
STATUS = {'AVAILABLE': 'Tersedia', 'REQUIRES_DATA': 'Belum: datanya belum ada',
          'REQUIRES_DECISION': 'Belum: menunggu keputusan / tahap berikut', None: 'Tersedia'}
KIND = {'transform': 'Screener · transform', 'xsection': 'Screener · peringkat', 'pattern': 'Screener · pola',
        'universe': 'Screener · atribut', 'flow': 'Screener · flow'}

CHANGES = [
    ('2026-10-30', 'Semua (pemanggil Screener/Backtest)', 'Parameter yang tidak dikirim memakai default di registry, '
     'bukan nilai cadangan di dalam rumus.', 'Reviewer A, A4: FL26 tanpa `scope` terbaca "all" di satu tempat dan '
     '"topn" di tempat lain.', 'Terminal tidak berubah (selalu mengirim semua parameter).'),
    ('2026-10-30', 'FL09', 'Ambang "> 0" tidak menerima 0; dialog menulis "Above 0".', 'Reviewer A, A5.',
     'Nilai 0 ditolak di dialog.'),
    ('2026-10-30', 'FL18-FL20', 'Dicatat: Top-N beku diurutkan atas seluruh periode di chart, jadi melihat candle sesudah t.',
     'Reviewer A, A8.', 'Rumus sama; Backtest dan Screener tidak boleh membacanya sebagai informasi yang diketahui di t.'),
    ('2026-10-30', 'FL19, FL20', 'Aturan inventori di 0 atau di bawahnya mengikuti opsi A.', 'Keputusan user: "1 pakai A".',
     'Aturan live tetap; tidak ada perubahan kode.'),
    ('2026-10-30', 'FL26', 'Dicatat: candle tanpa data = kosong; candle dengan data tetapi tanpa net = 0.', 'Reviewer A, A7.',
     'Rumus sama.'),
    ('2026-10-30', 'Semua', 'Sesi broker pada tanggal yang tidak punya harga tidak masuk candle mana pun.',
     'Reviewer A, A1 (celah 17-18 Sep, M238).', 'Celah 17-18 Sep 2026 diisi 2026-10-31 (EXEC-PRICE-GAP-0917); '
     'Flow kini menghitung broker kedua hari itu. Aturannya tetap untuk celah lain.'),
    ('2026-10-30', 'FL08, FL21, FL37', 'Garis referensi tanpa default tetap punya isian di dialog.', 'Reviewer B, B1.',
     'Tampilan saja.'),
    ('2026-10-30', 'Semua (W/M)', 'Di chart mingguan/bulanan label "(1 = daily)" dan "Daily" mengikuti candle '
     '("Rolling weeks (1 = weekly)").', 'Reviewer B, B2-B3.', 'Label saja; rumus per candle sudah begitu.'),
    ('2026-10-30', 'FL09', 'Label ambang partisipasi: "Buy participation (%) at least".', 'Reviewer B, B4.', 'Label saja.'),
    ('2026-10-30', 'FL14', 'Empat desimal seperti FL13.', 'Reviewer B, B5.', 'Tampilan saja.'),
    ('2026-10-30', 'FL01-FL23, FL34', 'Tooltip dalam bahasa Indonesia sederhana; FL34 memberi tahu bila klasifikasi '
     'belum dimuat; dialog Flow dirapikan.', 'Audit front end (V3, V4, V7, V8, V9).', 'Tampilan saja.'),
    ('2026-11-01', 'FL01-FL39', 'Kedua sheet FL memakai Terminal sebagai satu-satunya acuan: rumus dari kode, default dan '
     'tampilan dari registry Terminal, contoh dari oracle (= Terminal); kolom dan teks Screener dikosongkan. FL36/FL37 tetap '
     'Top-N seperti di Terminal.', 'User: "samakan dengan bagaimana formula dihitung di terminal. Jangan sangkut-pautkan '
     'dengan screener dulu."', 'Dokumentasi saja; Terminal tidak berubah.'),
    ('2026-11-01', 'FL01-FL39', 'Sheet Inspeksi_Kode: setiap FL dibaca di calc/flow.ts dan dibandingkan dengan FORMULAS.md, '
     'registry dan sheet Indikator_baru. Rumus cocok semua; default FL25 (Top N), FL36 dan FL37 (cakupan) berbeda antara '
     'sheet Indikator_baru dan kode.', 'User: "untuk setiap indikator boleh dilakukan inspeksi kode terlebih dahulu".',
     'Belum ada perubahan angka; FL36/FL37 menunggu keputusan.'),
    ('2026-11-01', 'FL01-FL39', 'Indicator_SPECS_reviewed dan Indikator_baru_dari_Screener dilengkapi sampai FL39; '
     'baris tambahan berlatar kuning, isinya dari registry, FORMULAS.md, metrik Screener dan contoh nyata oracle (BBCA).',
     'User: "Lengkapi list indicators FL only di sheet ini mengikuti format sheet tsb".', 'Dokumentasi saja.'),
    ('2026-10-31', 'Semua dialog indikator', 'Kontrol yang dipilih memakai garis abu-abu tipis dan cincin samar, bukan '
     'garis hitam 2 px.', 'User: "selected state bisa dirubah bordernya tidak setebal sekarang. Dibuat soft saja".',
     'Tampilan saja.'),
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def formulas():
    """(conventions, rows) from FORMULAS.md: the bullet text of sections 1-2 and the table of section 3."""
    text = FORMULAS.read_text()
    conv = []
    part = text.split('## 3. Formulas')[0]
    for block in re.split(r'\n(?=## )', part):
        head = block.splitlines()[0].lstrip('# ').strip()
        for item in re.split(r'\n(?=- )', block):
            if item.startswith('- '):
                conv.append((head, ' '.join(line.strip() for line in item[2:].splitlines())))
    rows = [[c.strip() for c in line.strip().strip('|').split(' | ')]
            for line in text.split('## 3. Formulas')[1].splitlines() if re.match(r'^\| FL\d\d ', line)]
    return conv, rows


def params_text(params, label='label', default='default', key='key'):
    out = []
    for q in params or []:
        if q.get('kind') in ('button', 'fixed'):
            continue
        d = q.get(default, q.get('def'))
        if isinstance(d, list):
            d = ', '.join(map(str, d)) or 'semua'
        out.append(f"{q.get(label) or q.get(key) or q.get('k')} ({d})")
    return '; '.join(out)


def fl_equivalents():
    """Screener metric id -> Terminal FL id, from the agreed spreadsheet (Indikator_baru_dari_Screener and
    Screener_ke_Chart 'Sudah ada / sama dengan')."""
    wb = openpyxl.load_workbook(SPEC, read_only=True)
    eq = {}
    for r in list(wb['Indikator_baru_dari_Screener'].iter_rows(values_only=True))[1:]:
        if r[0] and r[2]:
            eq[str(r[2])] = str(r[0])
    for r in list(wb['Screener_ke_Chart'].iter_rows(values_only=True))[1:]:
        m = re.search(r'FL\d\d', str(r[5] or ''))
        if r[0] and m and str(r[0]) not in eq:
            eq[str(r[0])] = m.group(0)
    return eq


def all_indicators(catalog):
    """Rows of the Semua_Indikator sheet (see the module docstring)."""
    reg = json.loads(REGISTRY.read_text())['indicators']
    conv, frows = formulas()
    formula = {r[0]: r[3].replace('`', '') for r in frows}
    eq = fl_equivalents()
    live = {m['id']: m for m in (catalog or {}).get('metrics', []) + (catalog or {}).get('fundamentals', [])}
    live_ind = {i['id'] for i in (catalog or {}).get('indicators', [])}
    metrics = json.loads(SC_METRICS.read_text())['metrics']
    by_fl = {}
    for sid, fl in eq.items():
        by_fl.setdefault(fl, []).append(sid)
    # cautions and worked examples of the Flow indicators, from the agreed spreadsheet
    wb = openpyxl.load_workbook(SPEC, read_only=True)
    spec_rows = list(wb['Indicator_SPECS_reviewed'].iter_rows(values_only=True))
    head = spec_rows[0]
    example, useful = {}, {}
    for r in spec_rows[1:]:      # one row per spec item; an FL id may gather two (its Buy and its Sell side)
        for store, col in ((example, 'Example Illustration'), (useful, 'Why It Is Useful / Why Formula Works')):
            v = r[head.index(col)]
            if r[0] and v and v not in store.setdefault(r[0], []):
                store[r[0]].append(v)
    example = {k: ' / '.join(v) for k, v in example.items()}
    useful = {k: ' '.join(v) for k, v in useful.items()}
    caution = {str(r[0]): r[6] for r in list(wb['Indikator_baru_dari_Screener'].iter_rows(values_only=True))[1:] if r[0]}
    rows = []
    for i in reg:
        sids = by_fl.get(i['id'], [])
        status = '; '.join(f"{sid}: {STATUS.get(live.get(sid, {}).get('availability'), 'tidak ada di katalog')}" for sid in sids)
        rows.append([i['id'], i['name'], 'Flow (Terminal)', i['family'], 'Ya', 'Belum', status or 'Tidak ada',
                     ', '.join(sids), formula.get(i['id'], ''), ' '.join(x for x in (i.get('tip'), useful.get(i['id'])) if x),
                     caution.get(i['id']) or '', example.get(i['id']) or '',
                     params_text(i.get('params')), f"{', '.join(i.get('outputs') or [])} [{i.get('unit') or ''}]",
                     'apps/edge-bff/terminal/src/data/flowRegistry.json; FORMULAS.md'])
    spec = {}
    for line in IND_SPEC.read_text().splitlines():
        c = [x.strip() for x in line.strip().strip('|').split('|')]
        if len(c) >= 7 and re.match(r'^I\d\d$', c[0]):
            spec[c[0]] = c
    bt = {x['id']: x for x in json.loads(BT_REG.read_text())['indicators']}
    sc = {x['id']: x for x in json.loads(SC_REG.read_text())['indicators']}
    for t in json.loads(IND_REG.read_text()):
        sp = spec.get(t['id'], [''] * 12)
        outs = ', '.join(o.get('label') or o.get('k') for o in t.get('outs') or [])
        rows.append([t['id'], t['name'], 'Teknikal (Terminal, Backtest, Screener)', t['cat'], 'Ya',
                     'Ya' if bt.get(t['id'], {}).get('available_for_backtest') else 'Tidak',
                     'Tersedia' if (not catalog or t['id'] in live_ind) else 'Tidak ada', '',
                     sp[5].replace('`', ''), (t.get('tip') or '') + (' ' + t['info'] if t.get('info') else ''),
                     sp[11] if len(sp) > 11 else '', t.get('display') or '',
                     params_text(t.get('params'), label='label', default='def', key='k'),
                     f"{outs} [{t.get('unit') or ''}]", 'indRegistry.json; INDICATOR_SPEC.md; screener-registry.json: '
                     + (sc.get(t['id'], {}).get('description') or '')])
    for m in metrics:
        st = live.get(m['id'], {})
        kind = 'Screener · fundamental' if m['group'] == 'Fundamental' else KIND.get(m['kind'], 'Screener')
        fl = eq.get(m['id'], '')
        rows.append([m['id'], m['label'], kind, m['group'], f'Ya ({fl})' if fl else 'Tidak', 'Tidak',
                     STATUS.get(st.get('availability'), 'tidak ada di katalog') if catalog else '',
                     fl, m.get('formula') or '', m.get('interpretation') or '', m.get('misuse') or '', '',
                     params_text(m.get('params')), m.get('unit') or '',
                     'screener-metrics.json' + (f"; status: {st.get('reason')}" if st.get('reason') else '')])
    return rows


ORACLE = HERE / 'oracle/out/BBCA.json'
ADDED = PatternFill('solid', fgColor='FFF4D6')


def idn(v):
    """A number the Indonesian way (thousands '.', decimals ',', two decimals unless whole)."""
    if v is None:
        return 'kosong'
    t = f'{v:,.0f}' if float(v).is_integer() else f'{v:,.2f}'
    return t.replace(',', '#').replace('.', ',').replace('#', '.')


def oracle_examples():
    """FL id -> 'BBCA <date> (parameter default): out = value; ...' from the independent oracle's default case."""
    if not ORACLE.exists():
        return {}
    out = {}
    for c in json.loads(ORACLE.read_text())['cases']:
        if c.get('case') != 'default':
            continue
        parts, day = [], None
        for name, series in c['outputs'].items():
            last = next(((d, v) for d, v in reversed(series) if v is not None), None)
            if last:
                day = day or last[0]
                parts.append(f'{name} = {idn(last[1])}')
        if parts:
            out[c['id']] = f'CONTOH NYATA: BBCA {day} (parameter default, oracle independen = Terminal): ' + '; '.join(parts)
    return out


PLACE = {'pane': 'Panel sendiri di bawah chart', 'price': 'Garis di atas chart harga (sumbu harga)',
         'marker': 'Tanda di bawah candle saat nilainya 1'}
SIDE_OUT = {('buy', 'sell'): 'Buy, Sell atau keduanya (pilihan Side)'}


def terminal_display(i):
    """How the Terminal draws the indicator, read from its registry entry (apps/edge-bff/terminal/src/app/flowIndicators.ts
    turns place, plot and levels into the chart series)."""
    pr = {q['key']: q for q in i['params']}
    kind = 'tanda' if i['place'] == 'marker' else ('histogram' if pr.get('plot', {}).get('default') == 'hist' else 'garis')
    alt = ' (bisa diganti garis/histogram)' if 'plot' in pr else ''
    outs = SIDE_OUT.get(tuple(i['outputs']), ', '.join(i['outputs']))
    lv = str(pr.get('levels', {}).get('default') or '').strip()
    guides = f"; garis acuan {lv}" if lv else ('; garis acuan bisa diisi' if 'levels' in pr else '')
    return f"{PLACE[i['place']]}; {kind}{alt}; output: {outs}; satuan {i['unit']}{guides}"


def complete_fl_sheets(wb):
    """User 2026-11-01: "Lengkapi list indicators FL only di sheet ini mengikuti format sheet tsb", then "samakan dengan
    bagaimana formula dihitung di terminal. Jangan sangkut-pautkan dengan screener dulu. Fokus ke bagaimana formula
    tersebut dihitung. Dan di display di terminal." Both FL sheets hold FL01-FL39 in their own columns; every formula,
    default, display and example comes from the Terminal (calc/flow.ts as FORMULAS.md states it, flowRegistry.json, the
    oracle that equals the Terminal); no Screener field is used. Rows not in the 2026-10-30 sheet are shaded."""
    reg = json.loads(REGISTRY.read_text())['indicators']
    by_id = {i['id']: i for i in reg}
    _, frows = formulas()
    formula = {r[0]: r[3].replace('`', '') for r in frows}
    examples = oracle_examples()
    insp = {r[0]: r for r in json.loads((HERE / 'code_inspection_20261101.json').read_text())}
    no_sc = lambda t: ' '.join(x for x in re.split(r'(?<=[.!?])\s+', str(t or '')) if 'creener' not in x).strip()

    def sources(fid, seen=()):
        """The data an FL formula reads: its own terms plus those of every FL it refers to (FL09 = FL05 + FL07 + ...)."""
        f, out = formula.get(fid, ''), []
        if any(k in f for k in ('BV', 'SV', 'BL', 'SL', 'BF', 'SF', 'bv', 'sv', 'bl', 'sl')):
            out.append('broker')
        if str(by_id.get(fid, {}).get('needs_frequency')) == 'True':
            out.append('frekuensi')
        if 'close' in f or 'volume' in f.lower():
            out.append('harga')
        if 'insider' in f.lower():
            out.append('events (insider)')
        for ref in re.findall(r'FL\d\d', f):
            if ref != fid and ref not in seen:
                out += sources(ref, seen + (fid,))
        return list(dict.fromkeys(out)) or ['broker']

    # ---- Indicator_SPECS_reviewed: every row's Terminal fields replaced, missing ids added ----
    ws = wb['Indicator_SPECS_reviewed']
    rows = list(ws.iter_rows(values_only=True))
    head, old_ids = rows[0], {r[0] for r in rows[1:] if r[0]}
    col = {h: n for n, h in enumerate(head)}
    spec_use, spec_def = {}, {}
    for r in rows[1:]:
        for store, c in ((spec_use, 'Why It Is Useful / Why Formula Works'), (spec_def, 'Definition')):
            v = r[col[c]]
            if r[0] and v and v not in store.setdefault(r[0], []):
                store[r[0]].append(v)

    def terminal_fields(i, base):
        v = dict(base)
        v.update({
            '# (Terminal)': i['id'], 'Terminal indicator (final)': i['name'], 'Category': i['family'],
            'Chart Display (Reviewed)': PLACE[i['place']], 'Chart Parameters (Reviewed)': params_text(i.get('params')),
            'Screener Parameters (PROPOSED)': '-',
            'Recommended Chart Type': terminal_display(i).split('; ')[1].capitalize(),
            'Formula / Calculation': formula.get(i['id'], ''), 'Display Guidance': terminal_display(i),
            'Status / Evidence': 'Kode Terminal: ' + insp[i['id']][2] + '. ' + insp[i['id']][3],
        })
        for k, x in list(v.items()):         # no Screener reference in a Terminal row (user 2026-11-01)
            if k in head and x and 'creener' in str(x):
                v[k] = no_sc(x) or '-'
        ex = examples.get(i['id'])
        if ex:
            v['Example Illustration'] = (f"{base['Example Illustration']} / " if base.get('Example Illustration') else '') + ex
        return v

    out_rows = []
    for r in rows[1:]:
        base = dict(zip(head, r))
        if base.get('# (Terminal)') in by_id:
            out_rows.append((False, terminal_fields(by_id[base['# (Terminal)']], base)))
    for i in reg:
        if i['id'] not in old_ids:
            base = {h: '' for h in head}
            base.update({'Spec #': '-', 'Indicator': i['name'], 'Definition': i.get('tip') or '',
                         'Why It Is Useful / Why Formula Works': '', 'Original Placement': '-', 'Default Display': '-',
                         'Review / Correction': 'Ditambahkan 2026-11-01 dari kode Terminal; tidak ada di sheet ini pada spec 30 Okt'})
            out_rows.append((True, terminal_fields(i, base)))
    ws.delete_rows(2, ws.max_row)
    for added, v in out_rows:
        ws.append([v.get(h, '') for h in head])
        for cell in ws[ws.max_row]:
            cell.alignment = Alignment(wrap_text=True, vertical='top')
            if added:
                cell.fill = ADDED

    # ---- Indikator_baru_dari_Screener: the same sheet, every FL, Terminal fields only ----
    ws = wb['Indikator_baru_dari_Screener']
    rows = list(ws.iter_rows(values_only=True))
    head, old = rows[0], {r[0]: dict(zip(rows[0], r)) for r in rows[1:] if r[0]}
    ws.delete_rows(2, ws.max_row)
    for i in reg:
        o = old.get(i['id'], {})
        caution = no_sc(o.get('Hati-hati')) if o else ''
        if i['id'] == 'FL24':      # the old text named panel levels 3/6/12; the Terminal panel and indicator use 6 and 10
            caution = 'Label Bandar di panel dan garis acuan indikator memakai 6 dan 10 (Acc/Dist, Big Acc/Big Dist).'
        note = insp[i['id']][3]
        v = {'Usulan id': i['id'], 'Nama (usulan, sama di Terminal dan Screener)': i['name'], 'Screener id': '-',
             'Rumus': formula.get(i['id'], ''), 'Maksud': i.get('tip') or '',
             'Kegunaan': no_sc(o.get('Kegunaan')) if o else ' '.join(spec_use.get(i['id'], [])),
             'Hati-hati': ' '.join(x for x in (caution, '' if note.startswith('Cocok.') and len(note) < 8 else note) if x) or '-',
             'Parameter (default)': params_text(i.get('params')) + ' | Tampilan: ' + terminal_display(i),
             'Data': ' + '.join(sources(i['id'])), 'Data sudah di storage?': 'Ya'}
        ws.append([v.get(h, '') for h in head])
        for cell in ws[ws.max_row]:
            cell.alignment = Alignment(wrap_text=True, vertical='top')
            if i['id'] not in old:
                cell.fill = ADDED
    return len(reg)


def style_head(ws, widths):
    for cell in ws[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='171717')
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical='top')
    ws.freeze_panes = 'A2'


def main(out, catalog_path=None):
    check = subprocess.run([sys.executable, str(ROOT / 'scripts/build_flow_registry.py'), '--check'],
                           capture_output=True, text=True)
    if check.returncode:
        raise SystemExit('the registry differs from the spreadsheet: ' + (check.stdout + check.stderr)[-500:])
    conv, rows = formulas()
    if len(rows) != 39:
        raise SystemExit(f'FORMULAS.md has {len(rows)} indicator rows, expected FL01-FL39')
    wb = openpyxl.load_workbook(SPEC)
    n_fl = complete_fl_sheets(wb)
    insp = HERE / 'code_inspection_20261101.json'
    if insp.exists():                      # user 2026-11-01: inspect every Flow indicator in code before the audit
        ws = wb.create_sheet('Inspeksi_Kode', 0)
        ws.append(['Id', 'Nama', 'Kode (file:baris)', 'Temuan', 'Perlu diperbaiki / diputuskan'])
        for r in json.loads(insp.read_text()):
            ws.append(r)
        style_head(ws, [8, 32, 46, 90, 46])
    catalog = json.loads(Path(catalog_path).read_text()) if catalog_path else None
    rows_all = all_indicators(catalog)
    ws = wb.create_sheet('Semua_Indikator', 0)
    ws.append(['ID', 'Nama', 'Jenis', 'Kelompok', 'Di Terminal', 'Di Backtest',
               'Di Screener (live ' + ((catalog or {}).get('data') or {}).get('published_at', 'tanpa katalog live')[:10] + ')',
               'Setara (Terminal FL / Screener id)', 'Rumus', 'Arti / cara membaca', 'Hati-hati',
               'Contoh / tampilan', 'Parameter (default)', 'Output [satuan]', 'Sumber di kode'])
    for r in rows_all:
        ws.append(r)
    style_head(ws, [9, 34, 26, 18, 11, 11, 30, 18, 70, 60, 50, 50, 50, 22, 40])
    ws.auto_filter.ref = ws.dimensions

    ws = wb.create_sheet('Rumus_Kode', 0)
    ws.append(['Id', 'Nama', 'Output', 'Rumus (seperti dihitung di Terminal)'])
    for r in rows:
        ws.append([v.replace('`', '') for v in r])
    ws.append([])
    ws.append(['Bagian', 'Konvensi bersama', '', ''])
    ws.cell(ws.max_row, 1).font = Font(bold=True)
    ws.cell(ws.max_row, 2).font = Font(bold=True)
    for head, item in conv:
        ws.append([head, item.replace('`', '').replace('**', '')])
        ws.merge_cells(start_row=ws.max_row, start_column=2, end_row=ws.max_row, end_column=4)
    style_head(ws, [8, 34, 16, 110])

    ws = wb.create_sheet('Perubahan', 1)
    ws.append(['Tanggal', 'Indikator', 'Perubahan', 'Asal', 'Pengaruh ke angka'])
    for c in CHANGES:
        ws.append(list(c))
    style_head(ws, [12, 22, 60, 40, 50])

    ws = wb.create_sheet('Versi', 2)
    ws.append(['Hal', 'Nilai'])
    for k, v in [
        ('Dibuat', date.today().isoformat()),
        ('Kontrak (sheet asli, tidak diubah)', f'{SPEC.name} sha256 {sha(SPEC)}'),
        ('Rumus', f'{FORMULAS.relative_to(ROOT)} sha256 {sha(FORMULAS)}'),
        ('Kode hitung', f'{FLOW_TS.relative_to(ROOT)} sha256 {sha(FLOW_TS)}'),
        ('Registry Terminal', f'{REGISTRY.relative_to(ROOT)} sha256 {sha(REGISTRY)}'),
        ('Cek registry = spreadsheet', (check.stdout or 'ok').strip()),
        ('Isi', 'Semua_Indikator, Rumus_Kode, Perubahan dan Versi ditambahkan; sheet lain adalah spreadsheet yang '
                'disepakati 2026-10-30.'),
        ('Semua_Indikator', f'{len(rows_all)} baris: Flow Terminal, 53 teknikal, metrik Screener; status Screener dari '
                            'katalog live' if catalog else 'tanpa katalog live'),
        ('Indicator_SPECS_reviewed, Indikator_baru_dari_Screener', f'lengkap FL01-FL{n_fl:02d} (user 2026-11-01); baris '
                                                                    'berlatar kuning diisi dari kode dan oracle'),
        ('Indikator teknikal', f'{IND_REG.relative_to(ROOT)} sha256 {sha(IND_REG)}'),
        ('Metrik Screener', f'{SC_METRICS.relative_to(ROOT)} sha256 {sha(SC_METRICS)}'),
    ]:
        ws.append([k, v])
    style_head(ws, [34, 110])
    wb.save(out)
    print(f'{out}: {len(rows_all)} rows in Semua_Indikator, {len(rows)} Flow formulas, {len(conv)} conventions, '
          f'{len(CHANGES)} changes')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
