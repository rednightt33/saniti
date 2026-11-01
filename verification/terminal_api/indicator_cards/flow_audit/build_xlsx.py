#!/usr/bin/env python3
"""Flow indicator audit workbook (user 2026-11-01: "Excelnya mana?"): the same 39 "How it works" cards as the audit HTML,
as tables, in the style of FLOW_INDICATORS_FINAL.xlsx (black header row, wrapped text, frozen header). The numbers come
from collect_cards.py, which reads them from the Terminal's own card and explainers (equal to the chart).

  python3 build_xlsx.py <cards.json> <out.xlsx> <commit>
"""
import json
import sys
from datetime import datetime, timezone

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


def style_head(ws, widths):
    for i, w in enumerate(widths, 1):
        cell = ws.cell(1, i)
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='171717')
        ws.column_dimensions[get_column_letter(i)].width = w
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical='top')
    ws.freeze_panes = 'A2'


def sheet(wb, title, head, rows, widths):
    ws = wb.create_sheet(title)
    ws.append(head)
    for r in rows:
        ws.append(r)
    style_head(ws, widths)
    return ws


def main(src, out, commit):
    d = json.loads(open(src).read())['cards']
    rows = d['rows']
    wb = openpyxl.Workbook()
    info = wb.active
    info.title = 'Info'
    made = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    for r in [['Hal', 'Isi'],
              ['Isi', f'{len(set(r["id"] for r in rows))} indikator Flow Terminal ({len(rows)} output), kartu "How it works" '
                      'sebagai tabel; sama dengan flow_indicators_audit_' + d['ticker'] + '.html'],
              ['Saham', d['ticker']], ['Grafik', 'harian (D), parameter default Terminal'],
              ['Tanggal nilai', f'candle terakhir yang bernilai; data broker terakhir {d["broker"]}, harga sampai {d["last"]}'],
              ['Asal angka', 'kartu dan explainer Terminal (apps/edge-bff/terminal/src/app/indCard.ts, src/calc/explain*.ts); '
                             'nilai explainer = nilai chart di setiap candle (tests/calc/explain.test.ts)'],
              ['Format angka', 'kolom "Nilai (kartu)" seperti tampil di Terminal (EDGE Design Spec v1.2); kolom "Nilai" angka mentah'],
              ['Kode', f'commit {commit}'], ['Dibuat', f'{made}, data dev'],
              ['Sheet', 'Ringkasan (satu baris per output) · Istilah (angka penyusun rumus terakhir) · Langkah · Tabel_Langkah '
                        '(tabel broker per langkah) · Parameter · Hati_hati · Grafik_Data (80 candle yang digambar kartu)']]:
        info.append(r)
    style_head(info, [18, 120])

    sheet(wb, 'Ringkasan',
          ['ID', 'Nama', 'Kelompok', 'Output', 'Satuan', 'Tanggal', 'Jendela dari', 'Jendela sampai', 'Candle', 'Nilai',
           'Nilai (kartu)', 'Rumus terakhir', 'Rumus dengan angka (kartu)', 'Rumus (spesifikasi)'],
          [[r['id'], r['name'], r['family'], r['output'], r['unit'], r['date'], (r['span'] or {}).get('from'),
            (r['span'] or {}).get('to'), (r['span'] or {}).get('candles'), r['value'], r['big'], r['expr'], r['filled'], r['formula']]
           for r in rows], [7, 30, 18, 12, 9, 11, 11, 11, 7, 16, 14, 30, 60, 70])
    sheet(wb, 'Istilah', ['ID', 'Output', 'Istilah', 'Arti', 'Nilai', 'Satuan'],
          [[r['id'], r['output'], k, label, v, u] for r in rows for k, label, v, u in r['terms']], [7, 12, 10, 45, 22, 8])
    sheet(wb, 'Langkah', ['ID', 'Output', 'No', 'Langkah', 'Penjelasan dengan angka'],
          [[r['id'], r['output'], n, st['title'], st['text']] for r in rows for n, st in enumerate(r['steps'], 1)], [7, 12, 5, 34, 100])
    width = max([len(st['table']['head']) for r in rows for st in r['steps'] if st.get('table')] + [1])
    trows = []
    for r in rows:
        for n, st in enumerate(r['steps'], 1):
            t = st.get('table')
            if not t:
                continue
            trows.append([r['id'], r['output'], n, 'kolom'] + t['head'])
            trows += [[r['id'], r['output'], n, ''] + row for row in t['rows']]
            if t.get('note'):
                trows.append([r['id'], r['output'], n, 'catatan', t['note']])
    ws = sheet(wb, 'Tabel_Langkah', ['ID', 'Output', 'Langkah', 'Baris'] + [f'Kolom {i}' for i in range(1, width + 1)],
               trows, [7, 12, 8, 8] + [16] * width)
    for row in ws.iter_rows(min_row=2):
        if row[3].value == 'kolom':
            for cell in row:
                cell.font = Font(bold=True)
    sheet(wb, 'Parameter', ['ID', 'Output', 'Parameter', 'Dipakai', 'Default', 'Pilihan / rentang'],
          [[r['id'], r['output']] + p for r in rows for p in r['params']], [7, 12, 26, 24, 24, 26])
    sheet(wb, 'Hati_hati', ['ID', 'Output', 'Hati-hati'], [[r['id'], r['output'], c] for r in rows for c in r['cautions']], [7, 12, 110])
    sheet(wb, 'Grafik_Data', ['ID', 'Output', 'Tanggal', 'Nilai indikator', 'Close ' + d['ticker']],
          [[r['id'], r['output']] + list(p) for r in rows for p in r['chart']], [7, 12, 11, 18, 12])
    wb.save(out)
    print(f'{out}: {len(rows)} rows, sheets {wb.sheetnames}')


if __name__ == '__main__':
    main(*sys.argv[1:4])
