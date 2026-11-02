#!/usr/bin/env python3
"""The Flow indicators as the Terminal has them, one workbook (user 2026-11-02: "FLOW_INDICATORS_FINAL.xlsx yang ini saja,
tapi hanya indikator flow. Versi final sesuai dengan yang ada di terminal").

FLOW_INDICATORS_FINAL.xlsx also holds the technical indicators, the Screener metrics and the 2026-10-30 spec sheets. This
workbook keeps only FL01-FL39, and every field comes from what the Terminal runs and shows today:
- names, groups, place, unit, outputs, parameters and defaults: apps/edge-bff/terminal/src/data/flowRegistry.json (the
  registry the Terminal draws from; `scripts/build_flow_registry.py --check` must pass);
- formulas and shared rules: FORMULAS.md, which states what calc/flow.ts computes (Inspeksi_Kode: code read line by line);
- display, usefulness and the data each formula reads: build_final_workbook.py's Terminal-only fields (no Screener text);
- the cautions and a worked example per output: the Terminal's own "How it works" cards (collect_cards.py, the same run as
  flow_indicators_audit_BBCA.html/.xlsx), whose values equal the chart;
- decisions and changes: the agreed decisions of 2026-10-30 and every change after them that touches a Flow indicator.

  python3 build_terminal_workbook.py <cards.json> <out.xlsx>
"""
import ast
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_final_workbook as F  # noqa: E402  (the shared readers of FORMULAS.md, the registry and the spec)

ROOT = F.ROOT
CARDS_COMMIT = '1b657d59'

LATER_CHANGES = [
    ('2026-11-01', 'FL01-FL39', 'Kartu "How it works" (Kalkulator, Grafik, Langkah) untuk setiap indikator; nilainya sama '
     'dengan chart di setiap candle (tes).', 'EXEC-IND-CARDS, user go 2026-11-01.', 'Tidak ada; penjelasan saja.'),
    ('2026-11-01', 'FL01-FL39', 'Judul dan angka mengikuti EDGE Design Spec v1.2: parameter dalam kurung ("Bandar Balance · % '
     '(Top 3, 10D)"), angka en-US, minus "−", rupiah B/T.', 'EXEC-SPEC-IND, user 2026-11-01.', 'Tampilan saja.'),
    ('2026-11-01', 'FL01-FL39', 'Di ticker tanpa data broker (obligasi) indikator Flow tidak digambar; tetap tersimpan dan '
     'muncul lagi di saham berikutnya. Menu tidak menawarkannya di ticker itu.', 'ERRORS M332, user 2026-11-01 (screenshot '
     'US10Y).', 'Tidak ada pada saham.'),
    ('2026-11-01', 'FL24', 'Vonis Bandar (Top 3/5/10, batas 6% dan 10%) pindah dari panel Bandar detector ke panel Top brokers '
     '(opsi "Tarik tambang"); rumus sama (bandarBalance), angkanya sama dengan panel lama.', 'EXEC-BANDAR-MERGE, user: "Pakai '
     'opsi 10 ya Tarik tambang".', 'Tidak ada; panel Bandar detector disembunyikan.'),
    ('2026-11-01', 'FL23', 'Broker yang diklik di panel kanan ikut masuk ke Broker Inventory (aturan panel: maksimal 5, yang '
     'paling lama keluar); setiap garis menulis kode brokernya di samping nilainya di sumbu kanan.', 'EXEC-INV-SYNC, user: '
     '"klik KZ ... otomatis broker inventory juga display", "KZ - 234.1K".', 'Daftar broker berubah saat user mengklik.'),
]


def style(ws, widths):
    for i, w in enumerate(widths, 1):
        c = ws.cell(1, i)
        c.font = Font(bold=True, color='FFFFFF')
        c.fill = PatternFill('solid', fgColor='171717')
        ws.column_dimensions[get_column_letter(i)].width = w
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical='top')
    ws.freeze_panes = 'A2'


def sheet(wb, title, head, rows, widths):
    ws = wb.create_sheet(title)
    ws.append(head)
    for r in rows:
        ws.append(r)
    style(ws, widths)
    if len(rows) > 1:
        ws.auto_filter.ref = ws.dimensions
    return ws


def lit(v):
    """A field collect_cards.py wrote as Python text (lists, dicts) back to a value."""
    try:
        return ast.literal_eval(v) if isinstance(v, str) and v[:1] in '[{(' else v
    except (ValueError, SyntaxError):
        return v


def term_value(v, unit):
    """a card term's value as the card writes it (EDGE Design Spec v1.2: en-US, minus U+2212, rupiah B/T)"""
    if not isinstance(v, (int, float)):
        return str(v)
    sign, a = ('−' if v < 0 else ''), abs(v)
    if unit == 'idr':
        return f'{sign}Rp {a / 1e12:,.1f}T' if a >= 1e12 else f'{sign}Rp {a / 1e9:,.1f}B' if a >= 1e9 else f'{sign}Rp {a:,.0f}'
    if unit == 'pct':
        return f'{sign}{a:,.2f}%'
    if unit in ('lot', 'count') or float(v).is_integer():
        return f'{sign}{a:,.0f}' + (' lot' if unit == 'lot' else '')
    return f'{sign}{a:,.2f}'


def terminal_fields():
    """FL id -> the Terminal-only fields build_final_workbook writes into its two FL sheets (display, usefulness,
    cautions of the spec, data read), taken from a fresh build of those sheets."""
    wb = openpyxl.load_workbook(F.SPEC)
    F.complete_fl_sheets(wb)
    rows = list(wb['Indikator_baru_dari_Screener'].iter_rows(values_only=True))
    head = rows[0]
    out = {r[0]: dict(zip(head, r)) for r in rows[1:] if r[0]}
    rows = list(wb['Indicator_SPECS_reviewed'].iter_rows(values_only=True))
    head = rows[0]
    for r in rows[1:]:
        v = dict(zip(head, r))
        fid = v.get('# (Terminal)')
        if fid in out:
            out[fid].setdefault('_def', [])
            if v.get('Definition') and v['Definition'] not in out[fid]['_def']:
                out[fid]['_def'].append(v['Definition'])
            out[fid]['_display'] = v.get('Display Guidance')
    return out


def main(cards_path, out):
    check = subprocess.run([sys.executable, str(ROOT / 'scripts/build_flow_registry.py'), '--check'], capture_output=True, text=True)
    if check.returncode:
        raise SystemExit('the registry differs from the agreed spreadsheet: ' + (check.stdout + check.stderr)[-400:])
    reg = json.loads(F.REGISTRY.read_text())
    ind = reg['indicators']
    conv, frows = F.formulas()
    formula = {r[0]: (r[2], r[3].replace('`', '')) for r in frows}
    if sorted(formula) != sorted(i['id'] for i in ind) or len(ind) != 39:
        raise SystemExit('FORMULAS.md and the registry do not hold the same FL01-FL39')
    tf = terminal_fields()
    cards = json.loads(Path(cards_path).read_text())['cards']
    crow = cards['rows']
    insp = json.loads((HERE / 'code_inspection_20261101.json').read_text())

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    info = [
        ('Isi', '39 indikator Flow (FL01-FL39) persis seperti di Terminal EDGE: nama, grup, tampilan, parameter dan '
                'default dari registry Terminal; rumus seperti dihitung kode Terminal; peringatan dan contoh dari kartu '
                '"How it works" Terminal. Indikator teknikal dan metrik Screener tidak dimasukkan.'),
        ('Dibuat', date.today().isoformat()),
        ('Registry Terminal', f'{F.REGISTRY.relative_to(ROOT)} sha256 {F.sha(F.REGISTRY)}'),
        ('Kode hitung', f'{F.FLOW_TS.relative_to(ROOT)} sha256 {F.sha(F.FLOW_TS)}'),
        ('Rumus', f'{F.FORMULAS.relative_to(ROOT)} sha256 {F.sha(F.FORMULAS)}'),
        ('Cek registry = spreadsheet yang disepakati', (check.stdout or 'ok').strip()),
        ('Kartu dan contoh', f"Kartu Terminal (kode {CARDS_COMMIT}), {cards['ticker']} harian, parameter default, data broker "
                             f"sampai {cards['broker']}; nilai kartu = nilai chart (tes)."),
        ('Sheet', 'Ringkasan · Rumus · Parameter · Hati_hati · Contoh_BBCA · Inspeksi_Kode · Keputusan · Perubahan'),
        ('Cara membaca', 'Satu baris per indikator di Ringkasan dan Rumus; satu baris per parameter di Parameter; satu '
                         'baris per peringatan di Hati_hati; satu baris per output di Contoh_BBCA. Kolom ID sama di '
                         'semua sheet (filter aktif).'),
    ]
    sheet(wb, 'Info', ['Hal', 'Nilai'], info, [30, 120])

    rows = []
    for i in ind:
        t = tf.get(i['id'], {})
        rows.append([i['id'], i['name'], i['family'], F.terminal_display(i), i['unit'], ', '.join(i['outputs']),
                     'Ya' if i.get('needs_frequency') else 'Tidak', t.get('Data') or '', i.get('tip') or '',
                     t.get('Kegunaan') or '', F.params_text(i.get('params'))])
    sheet(wb, 'Ringkasan', ['ID', 'Nama di Terminal', 'Kelompok', 'Tampilan di chart', 'Satuan', 'Output',
                            'Butuh frekuensi', 'Data yang dibaca', 'Arti (tooltip Terminal)', 'Kegunaan', 'Parameter (default)'],
          rows, [7, 34, 18, 46, 10, 16, 10, 20, 52, 52, 60])

    ws = sheet(wb, 'Rumus', ['ID', 'Nama di Terminal', 'Output', 'Rumus (seperti dihitung di Terminal)'],
               [[i['id'], i['name'], formula[i['id']][0], formula[i['id']][1]] for i in ind], [7, 34, 14, 120])
    ws.append([])
    ws.append(['Bagian', 'Aturan bersama semua indikator Flow'])
    for c in ws[ws.max_row]:
        c.font = Font(bold=True)
    for head, item in conv:
        ws.append([head, item.replace('`', '').replace('**', '')])
        ws.merge_cells(start_row=ws.max_row, start_column=2, end_row=ws.max_row, end_column=4)
        ws.cell(ws.max_row, 2).alignment = Alignment(wrap_text=True, vertical='top')

    rows = []
    for i in ind:
        for q in i['params']:
            if q.get('kind') in ('button', 'fixed') and q.get('key') != 'start':
                continue
            opts = q.get('options')
            opts = ', '.join(o[1] if isinstance(o, list) else str(o) for o in opts) if opts else (
                f"{q['min']} - {q['max']}" if 'min' in q and 'max' in q else q.get('text') or '')
            d = q.get('default')
            d = ', '.join(map(str, d)) if isinstance(d, list) else ('' if d is None else str(d))
            rows.append([i['id'], i['name'], q.get('label') or q['key'], q['key'], q.get('kind') or '', opts, d,
                         q.get('status') or ''])
    sheet(wb, 'Parameter', ['ID', 'Indikator', 'Parameter (label di Terminal)', 'Kunci', 'Jenis isian', 'Pilihan / rentang',
                            'Default', 'Status'], rows, [7, 30, 30, 16, 12, 44, 30, 11])

    rows, seen = [], set()
    for r in crow:
        if r['id'] in seen:
            continue
        seen.add(r['id'])
        for k, c in enumerate(lit(r['cautions']) or [], 1):
            rows.append([r['id'], r['name'], k, c, 'Kartu Terminal'])
        spec = (tf.get(r['id'], {}).get('Hati-hati') or '').replace(' Cocok. ', ' ').strip()   # 'Cocok.' = the inspection's verdict, not a caution
        if spec and spec != '-':
            rows.append([r['id'], r['name'], len(lit(r['cautions']) or []) + 1, spec, 'Spec yang disepakati + inspeksi kode'])
    sheet(wb, 'Hati_hati', ['ID', 'Indikator', 'No', 'Peringatan', 'Sumber'], rows, [7, 30, 5, 110, 26])

    rows = []
    for r in crow:
        sp = lit(r['span'])
        rows.append([r['id'], r['name'], r['output'], r['date'], r['big'], r['expr'], r['filled'],
                     f"{sp['from']} – {sp['to']} ({sp['candles']} candle)" if isinstance(sp, dict) else '',
                     '; '.join(f'{t[0]} ({t[1]}) = {term_value(t[2], t[3])}' for t in (lit(r['terms']) or [])),
                     ' | '.join(f"{s['title']}: {s['text']}" for s in (lit(r['steps']) or []))])
    sheet(wb, 'Contoh_BBCA', ['ID', 'Indikator', 'Output', 'Tanggal', 'Nilai (seperti di chart)', 'Rumus terakhir',
                              'Dengan angka', 'Candle yang dibaca', 'Istilah', 'Langkah (dari kartu)'],
          rows, [7, 30, 12, 11, 14, 30, 46, 30, 60, 110])

    sheet(wb, 'Inspeksi_Kode', ['ID', 'Nama', 'Kode (file:baris)', 'Temuan', 'Perlu diperbaiki / diputuskan'],
          [r for r in insp if str(r[0]).startswith('FL')], [7, 30, 46, 90, 46])

    spec_wb = openpyxl.load_workbook(F.SPEC, read_only=True)
    dec = list(spec_wb['Keputusan'].iter_rows(values_only=True))
    rows = [list(r) for r in dec[1:] if any(r)]
    for r in rows:
        if r[1] == 'Panel Bandar':
            r[2] = f'{r[2]} Sejak 2026-11-01 vonis ini ada di panel Top brokers (EXEC-BANDAR-MERGE).'
    sheet(wb, 'Keputusan', list(dec[0]), rows, [11, 24, 70, 70])

    sheet(wb, 'Perubahan', ['Tanggal', 'Indikator', 'Perubahan', 'Asal', 'Pengaruh ke angka'],
          [list(c) for c in F.CHANGES] + [list(c) for c in LATER_CHANGES], [12, 20, 70, 44, 44])
    wb.save(out)
    print(f'{out}: {len(ind)} indicators, {sum(len(i["params"]) for i in ind)} parameters, {len(crow)} card outputs, '
          f'{len(F.CHANGES) + len(LATER_CHANGES)} changes')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
