#!/usr/bin/env python3
"""EXEC-TERMINAL-FLOW-IND: the Terminal's Flow indicator registry, generated from the agreed spreadsheet.

Reads verification/terminal_api/flow_indicators/FLOW_INDICATORS_SPEC.xlsx (sheets Ringkasan, Parameter_Terminal,
Indicator_SPECS_reviewed, Indikator_baru_dari_Screener; user decisions of 2026-10-30) and writes
apps/edge-bff/terminal/src/data/flowRegistry.json: per indicator its id, name, family (the menu subgroup), place, unit,
outputs, plain-language tip, and per parameter its key, the label the Terminal shows, the control, the options, the
default and the range, all taken from the spreadsheet. Nothing about an indicator is typed here except the mapping of
the spreadsheet's Indonesian labels to the Terminal's keys and English labels (the Terminal is in English).

  python3 scripts/build_flow_registry.py           # writes the registry
  python3 scripts/build_flow_registry.py --check   # fails when the committed registry differs from the spreadsheet
"""
import hashlib
import json
import re
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / 'verification/terminal_api/flow_indicators/FLOW_INDICATORS_SPEC.xlsx'
OUT = ROOT / 'apps/edge-bff/terminal/src/data/flowRegistry.json'

# the menu subgroups (user 2026-10-30: "3. OK"), in menu order; an indicator's family is the part of its name before
# " · ", the rest go to "Other"
FAMILIES = ['Share', 'Transaction Size', 'Transactions', 'Concentration', 'Bandar Balance', 'Buy VWAP & Implied Cost',
            'Net Flow', 'Other']
FAMILY_OF = {'Share': 'Share', 'Transaction Size': 'Transaction Size', 'Transactions': 'Transactions',
             'Concentration HHI': 'Concentration', 'Concentration Top-N': 'Concentration', 'Bandar Balance': 'Bandar Balance',
             'Buy VWAP': 'Buy VWAP & Implied Cost', 'Implied Cost': 'Buy VWAP & Implied Cost',
             'Net Flow Percentile': 'Net Flow', 'Net Buy Persistence': 'Net Flow'}
NET_FLOW_NAMES = {'Net Flow / Turnover Ratio', 'Net Flow Streak'}

# outputs of each place / side
PLACE = {'Panel sendiri': 'pane', 'Di atas candle': 'price', 'Tanda di bawah candle': 'marker'}

# Indonesian option text -> (value, English label)
OPTIONS = {
    'Semua broker': ('all', 'All brokers'), 'Broker terpilih': ('selected', 'Selected brokers'),
    'Top-N cohort': ('topn', 'Top-N cohort'),
    'Net beli (Rp)': ('net_buy', 'Net buy (Rp)'), 'Beli kotor (Rp)': ('gross_buy', 'Gross buy (Rp)'),
    'Net jual (Rp)': ('net_sell', 'Net sell (Rp)'),
    'Buy': ('buy', 'Buy'), 'Sell': ('sell', 'Sell'), 'Both': ('both', 'Both'),
    'Histogram': ('hist', 'Histogram'), 'Garis': ('line', 'Line'),
    'Volume papan terpilih (semua investor)': ('board', 'Board volume, all investors'),
    'Volume papan + jenis investor terpilih': ('filter', 'Board and investor volume'),
    'Turnover papan terpilih (semua investor)': ('board', 'Board turnover, all investors'),
    'Turnover papan + jenis investor terpilih': ('filter', 'Board and investor turnover'),
    'Lot': ('lot', 'Lot'), 'Value': ('value', 'Value'), 'Kumulatif': ('cum', 'Cumulative'), 'Harian': ('daily', 'Daily'),
    'Ya': (True, 'Yes'), 'Tidak': (False, 'No'),
}
BOARDS, INVESTORS = ['Regular', 'Nego', 'Cash'], ['Foreign', 'Domestic']

# spreadsheet parameter label -> (key, English label); per indicator where the same label means another key
LABELS = {
    'Cakupan broker': ('scope', 'Broker scope'), 'Broker': ('brokers', 'Brokers'), 'Top N': ('top', 'Top N'),
    'Urutkan Top-N berdasarkan': ('rank', 'Rank Top-N by'), 'Ranking Top-N': ('ranking', 'Top-N ranking'),
    'Papan (Market board)': ('boards', 'Market board'), 'Jenis investor (Investor type)': ('investors', 'Investor type'),
    'Sisi (Side)': ('side', 'Side'), 'Hari rolling (1 = harian)': ('window', 'Rolling days (1 = daily)'),
    'Hari rolling': ('window', 'Rolling days'), 'Hari (N)': ('window', 'Days'), 'Hari': ('window', 'Days'),
    'Batas hari': ('window', 'Limit (days)'), 'Sessions': ('window', 'Sessions'), 'Jendela net': ('window', 'Net window'),
    'Recent sessions': ('recent', 'Recent sessions'), 'Baseline sessions': ('baseline', 'Baseline sessions'),
    'Jendela histori (baseline)': ('baseline', 'Baseline sessions'), 'Garis acuan': ('levels', 'Reference lines'),
    'Bentuk': ('plot', 'Plot'), 'Penyebut': ('denom', 'Denominator'), 'Dasar': ('basis', 'Basis'),
    'Ambang percentile ukuran transaksi >=': ('pct_min', 'Size percentile at least'),
    'Ambang Size Ratio (Buy) >=': ('ratio_min', 'Size ratio (buy) at least'),
    'Ambang Buy Participation >=': ('part_min', 'Market volume share (%) at least'),
    'Ambang Net Flow / Turnover >': ('flow_min', 'Net flow / turnover (%) above'),
    'Pakai Frequency Imbalance': ('use_imb', 'Use buy/sell imbalance'),
    'Ambang Frequency Imbalance >=': ('imb_min', 'Buy/sell imbalance at least'),
    'Tanggal awal (anchor)': ('anchor', 'Anchor date'), 'Posisi awal inventori': ('opening', 'Opening inventory'),
    'Aturan validitas': ('validity', 'Validity rule'), 'Satuan': ('unit', 'Unit'), 'Tampilan': ('view', 'View'),
    'Show cohort total': ('total', 'Show cohort total'), 'Mulai hitung': ('start', 'Counts from'),
    'Volume x': ('volx', 'Volume x'), 'Max move %': ('move', 'Max move %'),
    'Ambang Bandar Balance harian (%)': ('threshold', 'Daily balance above (%)'),
    'Broker institusi': ('inst', 'Institutional brokers'), 'Broker ritel': ('retail', 'Retail brokers'),
    'Kembalikan ke klasifikasi bawaan': ('reset', 'Back to the default classification'),
}
FIXED_TEXT = {'Dihitung ulang tiap hari': 'Recomputed every day',
              'Beku: diurutkan sekali dari tanggal awal sampai hari ini': 'Frozen: ranked once from the anchor to the last day',
              'Lot': 'Lot', '0': '0 (assumed)', 'Harga rata-rata kosong bila inventori model <= 0': 'No cost while the modelled inventory is 0 or less',
              'Candle pertama yang terlihat': 'The first visible candle'}
UNIT = {'lot per transaksi': 'lot/tx', 'Rp per transaksi': 'IDR/tx', '%': '%', 'x': 'x', '0-100': '0-100',
        'tanda': 'flag', '-1 s/d +1': '-1..1', '0-1': '0-1', 'selisih': 'diff', 'harga': 'price', 'lot atau Rp': 'lot|IDR',
        'Rp': 'IDR', 'hari': 'days'}


def number(text):
    v = float(text)
    return int(v) if v.is_integer() and '.' not in text else v


def span(text):
    """'1 - 20', '20 - 1000 sesi', '-100 - 100', '> 0' -> (min, max)."""
    t = text.replace('sesi', '').replace('broker', '').strip()
    if t.startswith('>'):
        return number(t[1:].strip()), None
    m = re.fullmatch(r'(-?[\d.]+)\s*-\s*(-?[\d.]+)', t)
    return (number(m.group(1)), number(m.group(2))) if m else (None, None)


def param(row):
    _, _, _, label, control, choices, default, status, note = row
    key, en = LABELS[label]
    p = {'key': key, 'label': en, 'status': status}
    default = '' if default is None else str(default)
    if control == 'Pilihan':
        opts = [OPTIONS[o.strip()] for o in choices.split(' / ')]
        p.update(kind='select', options=[[v, t] for v, t in opts], default=OPTIONS[default][0])
    elif control.startswith('Pilih banyak'):
        if key == 'boards':
            p.update(kind='multi', options=BOARDS, default=BOARDS if default == 'Semua' else [default])
        elif key == 'investors':
            p.update(kind='multi', options=INVESTORS, default=INVESTORS if default == 'Semua' else [default])
        elif key == 'brokers':
            lo, hi = span(choices)
            p.update(kind='brokers', default='top3_net_buy_20' if default.startswith('3 net buyer') else [],
                     **({'min': lo, 'max': hi} if hi else {}))
        else:                                                # inst, retail: a classification's brokers by default
            p.update(kind='brokers', default='class:' + re.search(r'(Institutional-heavy|Retail-heavy)', default).group(1))
    elif control == 'Angka bulat':
        lo, hi = span(choices)
        p.update(kind='int', default=number(default), min=lo, max=hi)
    elif control.startswith('Angka (boleh'):
        p.update(kind='levels', default='' if default in ('', 'None') else default)
    elif control.startswith('Angka'):
        lo, hi = span(choices)
        p.update(kind='num', default=number(default), **({'min': lo} if lo is not None else {}), **({'max': hi} if hi is not None else {}),
                 # '> 0' excludes its bound (Reviewer A, A5: FL09's size-ratio threshold accepted 0)
                 **({'min_exclusive': True} if str(choices).strip().startswith('>') else {}))
    elif control == 'Centang':
        p.update(kind='bool', default=OPTIONS[default][0])
    elif control.startswith('Tanggal'):
        p.update(kind='date', default='view')
    elif control == 'Tombol':
        p.update(kind='button')
    elif control == 'Tetap':
        p.update(kind='fixed', text=FIXED_TEXT.get(choices, FIXED_TEXT.get(default, choices)),
                 default={'Ulang tiap hari': 'daily', 'Beku': 'frozen'}.get(default, default))
    else:
        raise SystemExit(f'unknown control {control!r} for {label!r}')
    return p


def outputs(fid, params):
    side = next((p for p in params if p['key'] == 'side'), None)
    if side and any(o[0] == 'both' for o in side['options']):
        return ['buy', 'sell']
    return {'FL06': ['ratio'], 'FL14': ['asym'], 'FL23': ['lines', 'total']}.get(fid, ['value'])


# The tooltip in plain Indonesian, like the 53 price indicators' tips. FL24-FL39 take the meaning the Screener sheet
# gives; FL01-FL23 the spec's Definition column, which mixes languages ("Rata-rata purchase price frozen cohort sejak
# accumulation episode dimulai"), so their sentence is restated here with the same meaning (front-end audit V8,
# 2026-10-30). An id missing here falls back to the Definition column.
PLAIN = {
    'FL01': 'Rata-rata lot per transaksi beli (atau jual) dari broker atau kelompok broker yang dipilih.',
    'FL02': 'Rata-rata nilai Rupiah per transaksi beli (atau jual) dari broker atau kelompok broker yang dipilih.',
    'FL03': 'Porsi lot beli (atau jual) yang berasal dari broker atau kelompok broker yang dipilih, dibanding semua broker.',
    'FL04': 'Porsi jumlah transaksi beli (atau jual) yang berasal dari broker atau kelompok broker yang dipilih.',
    'FL05': 'Porsi lot dibagi porsi jumlah transaksi: di atas 1 berarti ukuran transaksinya lebih besar dari rata-rata pasar.',
    'FL06': 'Ukuran rata-rata transaksi beli dibanding ukuran rata-rata transaksi jual dari kelompok yang sama.',
    'FL07': 'Porsi pembelian broker atau kelompok broker terhadap seluruh volume saham.',
    'FL08': 'Posisi ukuran transaksi hari ini dibanding riwayat saham itu sendiri (0-100).',
    'FL09': 'Tanda saat pembelian berukuran besar, berporsi berarti dan berarus bersih positif terjadi bersamaan.',
    'FL10': 'Selisih jumlah transaksi beli dan jual dibagi totalnya (-1 sampai 1) untuk broker atau kelompok yang dipilih.',
    'FL11': 'Pembelian bersih broker atau kelompok broker dibanding seluruh nilai transaksi saham.',
    'FL12': 'Persentase hari dalam jendela ketika broker atau kelompok broker menjadi pembeli bersih.',
    'FL13': 'Seberapa terpusat pembelian (atau penjualan) pada sedikit broker (0-1).',
    'FL14': 'Keterpusatan sisi beli dikurangi keterpusatan sisi jual.',
    'FL15': 'Persentase pembelian yang dikuasai N broker pembeli terbesar.',
    'FL16': 'Persentase pembelian bersih positif yang berasal dari N pembeli bersih terbesar.',
    'FL17': 'Harga rata-rata pembelian kelompok broker selama N hari terakhir.',
    'FL18': 'Harga rata-rata pembelian kelompok broker tetap sejak tanggal awal.',
    'FL19': 'Perkiraan harga pokok rata-rata posisi yang masih dipegang kelompok broker sejak tanggal awal.',
    'FL20': 'Jarak harga penutupan dari perkiraan harga pokok rata-rata, dalam persen.',
    'FL21': 'Posisi arus bersih dibanding nilai transaksi hari ini terhadap riwayat saham itu sendiri (0-100).',
    'FL22': 'Persentase broker aktif yang menjadi pembeli bersih.',
    'FL23': 'Perkiraan posisi bersih (lot atau Rupiah) tiap broker yang dipilih sejak tanggal awal; bukan kepemilikan sebenarnya.',
}


def build():
    wb = openpyxl.load_workbook(SPEC, data_only=True)
    params = {}
    for row in wb['Parameter_Terminal'].iter_rows(min_row=2, values_only=True):
        if row[0]:
            params.setdefault(row[0], []).append(param(row))
    # a tip in the reader's language: the spec's definition (FL01-FL23), the Screener sheet's meaning (FL24-FL39)
    tips = {}
    for r in wb['Indicator_SPECS_reviewed'].iter_rows(min_row=2, values_only=True):
        tips.setdefault(r[0], r[10])
    for r in wb['Indikator_baru_dari_Screener'].iter_rows(min_row=2, values_only=True):
        if r[0]:
            tips[r[0]] = r[4]
    indicators = []
    for r in wb['Ringkasan'].iter_rows(min_row=2, values_only=True):
        if not (r[0] and str(r[0]).startswith('FL')):
            continue
        fid, name, _, _, place, unit, freq = r[:7]
        head = name.split(' · ')[0]
        family = FAMILY_OF.get(head) or ('Net Flow' if name in NET_FLOW_NAMES else 'Other')
        ps = params[fid]
        indicators.append({'id': fid, 'name': name, 'family': family, 'place': PLACE[place.split(' (')[0]],
                           'unit': UNIT[unit], 'needs_frequency': freq == 'Ya', 'outputs': outputs(fid, ps),
                           'tip': PLAIN.get(fid, tips[fid]), 'params': ps})
    return {'schema_version': 1, 'generated_by': 'scripts/build_flow_registry.py',
            'source': {'file': str(SPEC.relative_to(ROOT)), 'sha256': hashlib.sha256(SPEC.read_bytes()).hexdigest()},
            'families': FAMILIES, 'indicators': indicators}


def main(argv):
    text = json.dumps(build(), ensure_ascii=False, indent=1) + '\n'
    if '--check' in argv:
        if not OUT.exists() or OUT.read_text() != text:
            raise SystemExit(f'{OUT.relative_to(ROOT)} is stale: run python3 scripts/build_flow_registry.py')
        print('flow registry current')
        return
    OUT.write_text(text)
    print(f'wrote {OUT.relative_to(ROOT)}: {text.count(chr(34) + "id" + chr(34))} indicators')


if __name__ == '__main__':
    main(sys.argv[1:])
