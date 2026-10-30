"""Final Flow indicator workbook (decisions 2026-10-30). Usage: python3 -I build_flow_final.py <user.xlsx> <out.xlsx>"""
import sys
import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

src, out = sys.argv[1], sys.argv[2]
D, P, O = 'DECIDED', 'PROPOSED', 'OPEN'

# ---- parameter groups ----
SCOPE = [
    ('Cakupan broker', 'Pilihan', 'Broker terpilih / Top-N cohort', 'Top-N cohort', D, 'B5 setuju (Top 3). Broker terpilih dan Top-N dijumlah menjadi satu kelompok.'),
    ('Broker', 'Pilih banyak (cari kode)', 'Semua kode broker', 'Kosong', D, 'Dipakai bila Cakupan = Broker terpilih.'),
    ('Top N', 'Angka bulat', '1 - 20', '3', D, 'Default Top 3 untuk semua (user 2026-10-30).'),
    ('Urutkan Top-N berdasarkan', 'Pilihan', 'Net beli (Rp) / Beli kotor (Rp) / Net jual (Rp)', 'Net beli (Rp)', D, 'B3 setuju.'),
    ('Ranking Top-N', 'Tetap', 'Dihitung ulang tiap hari', 'Ulang tiap hari', D,
     'B4: "Hitung ulang tiap hari, jadi apabila yang dipilih top N maka bisa berbeda2 untuk broker".'),
]
SCOPE_ALL = [(SCOPE[0][0], SCOPE[0][1], 'Semua broker / Broker terpilih / Top-N cohort', 'Top-N cohort', D,
              'Semua broker = agregat jenis investor yang dipilih.')] + SCOPE[1:]
ANCH_SCOPE = SCOPE[:4] + [('Ranking Top-N', 'Tetap', 'Beku: diurutkan sekali dari tanggal awal sampai hari ini', 'Beku', D,
                           'User 2026-10-30: "yes pakai kelompok broker tetap untuk ketiganya."')]
FILTER = [('Papan (Market board)', 'Pilih banyak', 'Regular, Nego, Cash (Tunai)', 'Semua', D, ''),
          ('Jenis investor (Investor type)', 'Pilih banyak', 'Foreign, Domestic', 'Semua', D, '')]
DAYS = [('Hari rolling (1 = harian)', 'Angka bulat', '1 - 250', '1', D, 'Rolling = jumlah N hari dibagi jumlah N hari ("Ok rolling").')]
BASE = [('Jendela histori (baseline)', 'Angka bulat', '20 - 1000 sesi', '250', D, 'D12 ya. Hanya data sebelum hari itu.')]
ANCHOR = [('Tanggal awal (anchor)', 'Tanggal / pilih di chart', 'Tanggal sesi broker yang ada', 'Candle pertama yang terlihat', D,
           'User: "no need" (default tidak diubah).')]
OPENINV = [('Posisi awal inventori', 'Tetap', '0', '0', D, 'D11 ya. Ditulis di label sebagai asumsi.'),
           ('Aturan validitas', 'Tetap', 'Harga rata-rata kosong bila inventori model <= 0', '-', D, 'D11 ya.')]
SIDE3 = [('Sisi (Side)', 'Pilihan', 'Buy / Sell / Both', 'Buy', D, 'C6 B: satu indikator; Both = dua garis di satu panel.')]
REF = lambda v, st=P: [('Garis acuan', 'Angka (boleh dikosongkan)', 'Bebas', v, st, '')]
PLOT = [('Bentuk', 'Pilihan', 'Histogram / Garis', 'Histogram', P, '')]

# ---- final Terminal indicators: id, name, spec rows, place, unit, freq, note, params ----
FL = [
    ('FL01', 'Average Lot per Transaction', [1, 2], 'Panel sendiri', 'lot per transaksi', True,
     'Dari #1/#2. Nama memakai "Lot" karena satuan tetap lot (F15).', SCOPE + FILTER + SIDE3 + DAYS),
    ('FL02', 'Average Value per Transaction', [3, 4], 'Panel sendiri', 'Rp per transaksi', True, 'Dari #3/#4.', SCOPE + FILTER + SIDE3 + DAYS),
    ('FL03', 'Volume Share', [5, 7], 'Panel sendiri', '%', False, 'Dari #5/#7. Penyebut tetap: semua broker pada papan + jenis investor yang sama.',
     SCOPE + FILTER + SIDE3 + DAYS),
    ('FL04', 'Frequency Share', [6, 8], 'Panel sendiri', '%', True, 'Dari #6/#8. Penyebut seperti FL03.', SCOPE + FILTER + SIDE3 + DAYS),
    ('FL05', 'Size Ratio', [9, 10], 'Panel sendiri', 'x', True, 'Dari #9/#10.', SCOPE + FILTER + SIDE3 + DAYS + REF('1.0')),
    ('FL06', 'Buy/Sell Average Transaction Size Ratio', [11], 'Panel sendiri', 'x', True, 'Nama baru (#11).',
     SCOPE + FILTER + DAYS + REF('1.0')),
    ('FL07', 'Buy Participation Rate', [12], 'Panel sendiri', '%', False, '',
     SCOPE + FILTER + DAYS + [('Penyebut', 'Pilihan', 'Volume papan terpilih (semua investor) / Volume papan + jenis investor terpilih',
                               'Volume papan terpilih (semua investor)', D, 'D8 OK.')]),
    ('FL08', 'Average Transaction Size Percentile', [13], 'Panel sendiri (0-100)', '0-100', True, 'Nama baru (#13).',
     SCOPE + FILTER + [('Sisi (Side)', 'Pilihan', 'Buy / Sell', 'Buy', D, '"bisa parameter opsi beli dan jual"'),
                       ('Dasar', 'Tetap', 'Lot', 'Lot', D, 'F15: tetap LOT.')] + DAYS + BASE + REF('')),
    ('FL09', 'Block Money Candidate', [14], 'Tanda di bawah candle', 'tanda', True, 'Nama baru (#14). Ambang awal belum diuji (E13 OK).',
     SCOPE + FILTER + DAYS + BASE + [
         ('Ambang percentile ukuran transaksi >=', 'Angka', '0 - 100', '90', D, 'E13 OK, label "belum diuji".'),
         ('Ambang Size Ratio (Buy) >=', 'Angka', '> 0', '2.0', D, ''),
         ('Ambang Buy Participation >=', 'Angka (%)', '0 - 100', '5', D, ''),
         ('Ambang Net Flow / Turnover >', 'Angka (%)', '-100 - 100', '0', D, ''),
         ('Pakai Frequency Imbalance', 'Centang', 'Ya / Tidak', 'Tidak', D, ''),
         ('Ambang Frequency Imbalance >=', 'Angka', '-1 - 1', '0', D, 'Dipakai bila dicentang.')]),
    ('FL10', 'Cohort Frequency Imbalance', [15], 'Panel sendiri (-1 s/d +1)', '-1 s/d +1', True, '',
     SCOPE + FILTER + DAYS + REF('0') + PLOT),
    ('FL11', 'Net Flow / Turnover Ratio', [16], 'Panel sendiri', '%', False,
     'Turnover = total nilai beli seluruh broker pada papan terpilih (D7 OK).',
     SCOPE_ALL + FILTER + DAYS + [('Penyebut', 'Pilihan', 'Turnover papan terpilih (semua investor) / Turnover papan + jenis investor terpilih',
                                   'Turnover papan terpilih (semua investor)', D, 'D7 OK.')] + PLOT),
    ('FL12', 'Buy Persistence N-Day', [17], 'Panel sendiri (0-100%)', '%', False, 'Hari tanpa transaksi = bukan hari beli (D9 ya).',
     SCOPE_ALL + FILTER + [('Hari (N)', 'Angka bulat', '2 - 250', '5', P, '')]),
    ('FL13', 'Buyer/Seller HHI', [18, 19], 'Panel sendiri', '0-1', False, 'Dari #18/#19. Tanpa pilihan broker: sebaran seluruh broker.',
     FILTER + SIDE3 + DAYS),
    ('FL14', 'HHI Asymmetry', [20], 'Panel sendiri', 'selisih', False, '', FILTER + DAYS + REF('0') + PLOT),
    ('FL15', 'Top-N Buy Concentration', [21], 'Panel sendiri (0-100%)', '%', False, 'Dasar lot beli; Top-N diurutkan dari beli kotor tiap hari.',
     FILTER + DAYS + [('Top N', 'Angka bulat', '1 - 20', '3', D, 'Default Top 3 untuk semua.')]),
    ('FL16', 'Top-N Net Buy Concentration', [22], 'Panel sendiri (0-100%)', '%', False, 'Dasar net beli positif (Rp), Top-N tiap hari.',
     FILTER + DAYS + [('Top N', 'Angka bulat', '1 - 20', '3', D, 'Default Top 3 untuk semua.')]),
    ('FL17', 'Rolling Buy VWAP N-Day', [23], 'Di atas candle', 'harga', False, '',
     SCOPE + FILTER + [('Hari rolling', 'Angka bulat', '2 - 250', '20', P, '')]),
    ('FL18', 'Anchored Accumulation VWAP', [24], 'Di atas candle', 'harga', False, '', ANCH_SCOPE + FILTER + ANCHOR),
    ('FL19', 'Implied Inventory Average Cost', [26], 'Di atas candle', 'harga', False, 'Label wajib "Implied".', ANCH_SCOPE + FILTER + ANCHOR + OPENINV),
    ('FL20', 'Price Distance to Implied Cost', [27], 'Panel sendiri', '%', False, '', ANCH_SCOPE + FILTER + ANCHOR + OPENINV + REF('0')),
    ('FL21', 'Net Flow Abnormality Percentile', [28], 'Panel sendiri (0-100)', '0-100', False, '', SCOPE_ALL + FILTER + DAYS + BASE + REF('')),
    ('FL22', 'Broker Buy Breadth', [29], 'Panel sendiri (0-100%)', '%', False,
     'Broker aktif = punya transaksi beli atau jual pada hari itu (D10).', FILTER + DAYS),
    ('FL23', 'Broker Inventory', [25, 30], 'Panel sendiri', 'lot atau Rp', False,
     'Panel Broker inventory sebagai indikator Flow (E14 A), dengan garis total kelompok (#25: B).',
     [('Broker', 'Pilih banyak (cari kode)', '1 - 5 broker', '3 net buyer terbesar 20 sesi terakhir', D, 'Sama dengan panel.'),
      ('Satuan', 'Pilihan', 'Lot / Value', 'Lot', D, 'Sama dengan panel.'),
      ('Tampilan', 'Pilihan', 'Kumulatif / Harian', 'Kumulatif', D, 'Sama dengan panel.'),
      ('Show cohort total', 'Centang', 'Ya / Tidak', 'Tidak', D, '#25 "B alright": satu garis total broker terpilih.')] + FILTER +
     [('Mulai hitung', 'Tetap', 'Candle pertama yang terlihat', '-', D, 'Sama dengan panel.')]),
    # ---- from the Screener (2026-10-30, for review) ----
    ('FL24', 'Bandar Balance (Top-N)', [], 'Panel sendiri', '%', False, 'Screener bandar. Angkanya sama dengan vonis panel Bandar Terminal; ambang label berbeda.',
     [('Top N', 'Angka bulat', '1 - 20', '3', D, 'User 2026-10-30: B (default Top 3).')] + FILTER + [('Hari rolling', 'Angka bulat', '1 - 250', '10', D, '')] +
     [('Garis acuan', 'Angka (boleh dikosongkan)', 'Bebas', '6, 10, -6, -10', D, 'B: Acc >= 6, Big Acc >= 10, Dist <= -6, Big Dist <= -10. Berlaku juga untuk panel Bandar.')]),
    ('FL25', 'Top-N Net Accumulation', [], 'Panel sendiri', 'Rp', False, 'Screener topacc.',
     [('Top N', 'Angka bulat', '1 - 20', '3', D, 'Default Top 3 untuk semua.')] + FILTER + [('Hari rolling', 'Angka bulat', '1 - 250', '10', P, '')] + PLOT),
    ('FL26', 'Net Flow Streak', [], 'Panel sendiri', 'hari', False, 'Screener fstreak, dibuat umum untuk kelompok mana pun.',
     [('Cakupan broker', 'Pilihan', 'Semua broker / Broker terpilih / Top-N cohort', 'Semua broker', P, ''), SCOPE[1], SCOPE[2], SCOPE[3], SCOPE[4],
      ('Papan (Market board)', 'Pilih banyak', 'Regular, Nego, Cash (Tunai)', 'Semua', P, ''),
      ('Jenis investor (Investor type)', 'Pilih banyak', 'Foreign, Domestic', 'Foreign', P, 'Default asing seperti Screener.'),
      ('Batas hari', 'Angka bulat', '1 - 250', '60', P, '')] + PLOT),
    ('FL27', 'Silent Accumulation', [], 'Tanda di bawah candle', 'tanda', False, 'Screener silent. Dari harga dan volume.',
     [('Recent sessions', 'Angka bulat', '1 - 60', '5', P, ''), ('Baseline sessions', 'Angka bulat', '1 - 1000', '20', P, ''),
      ('Volume x', 'Angka', '0 - 100', '1.5', P, ''), ('Max move %', 'Angka', '0 - 100', '3', P, '')]),
    ('FL28', 'Average Daily Value', [], 'Panel sendiri', 'Rp', False, 'Screener adv20_idr. Dari harga dan volume.',
     [('Sessions', 'Angka bulat', '1 - 250', '20', P, 'Screener memakai 20 tetap.')]),
    ('FL29', 'Accumulation-Day Ratio', [], 'Panel sendiri (0-100%)', '%', False, 'Screener acc_days.',
     [('Top N', 'Angka bulat', '1 - 20', '3', P, '')] + FILTER + [('Hari', 'Angka bulat', '2 - 250', '20', P, ''),
      ('Ambang Bandar Balance harian (%)', 'Angka', '-100 - 100', '0', P, 'Screener belum punya default.')]),
    ('FL30', 'Crossing Share', [], 'Panel sendiri (0-100%)', '%', False, 'Screener crossing_share (Nego + Tunai).',
     [('Jenis investor (Investor type)', 'Pilih banyak', 'Foreign, Domestic', 'Semua', P, ''), ('Hari rolling', 'Angka bulat', '1 - 250', '20', P, '')]),
    ('FL31', 'Insider Net Change', [], 'Panel sendiri', 'Rp', False, 'Screener insider_net. Data event yang sudah ada.',
     [('Hari rolling', 'Angka bulat', '1 - 250', '20', P, '')] + PLOT),
    ('FL32', 'Trade-Count Spike', [], 'Panel sendiri', 'x', True, 'Screener freq.',
     FILTER + [('Baseline sessions', 'Angka bulat', '1 - 250', '20', P, '')] + REF('2.5')),
    ('FL33', 'Average Trade Size Change', [], 'Panel sendiri', '%', True, 'Screener trade_size_change.',
     FILTER + [('Recent sessions', 'Angka bulat', '1 - 60', '5', P, ''), ('Baseline sessions', 'Angka bulat', '1 - 250', '20', P, '')] + REF('0')),
    ('FL34', 'Institutional vs Retail Net', [], 'Panel sendiri', '%', False,
     'Screener inst_retail. Butuh klasifikasi broker di storage. Edit manual klasifikasi oleh user: nanti saat Screener dibangun (user 2026-10-30).',
     [('Papan (Market board)', 'Pilih banyak', 'Regular, Nego, Cash (Tunai)', 'Semua', P, ''), ('Hari rolling', 'Angka bulat', '1 - 250', '20', P, ''),
      ('Jenis investor (Investor type)', 'Pilih banyak', 'Foreign, Domestic', 'Semua', P, ''),
      ('Broker institusi', 'Pilih banyak (cari kode)', 'Semua kode broker', 'Broker Institutional-heavy (IDX_Broker_Profile)', P,
       'User bisa menambah atau membuang broker (permintaan user 2026-10-30).'),
      ('Broker ritel', 'Pilih banyak (cari kode)', 'Semua kode broker', 'Broker Retail-heavy (IDX_Broker_Profile)', P,
       'Satu broker tidak boleh ada di dua kelompok. Mixed dan Niche tidak dihitung kecuali dipilih user.'),
      ('Kembalikan ke klasifikasi bawaan', 'Tombol', '-', '-', P, '')] + PLOT),
    ('FL35', 'Dominant-Buyer Persistence', [], 'Panel sendiri (0-100%)', '%', False, 'Screener dominant_persistence. Pembeli terbesar dibeku per jendela.',
     FILTER + [('Hari', 'Angka bulat', '2 - 250', '20', P, '')]),
    ('FL36', 'Participation Rate (Buy + Sell)', [], 'Panel sendiri (0-100%)', '%', False, 'Screener fpart, dibuat umum. Beda dengan FL07: beli dan jual.',
     SCOPE_ALL + [('Papan (Market board)', 'Pilih banyak', 'Regular, Nego, Cash (Tunai)', 'Semua', P, ''),
                  ('Jenis investor (Investor type)', 'Pilih banyak', 'Foreign, Domestic', 'Foreign', P, 'Default asing seperti Screener.'),
                  ('Hari rolling', 'Angka bulat', '1 - 250', '20', P, '')]),
    ('FL37', 'Net Flow Surprise Percentile', [], 'Panel sendiri (0-100)', '0-100', False, 'Screener fsurprise, dibuat umum. Beda dengan FL21: dasar net Rupiah.',
     SCOPE_ALL + [('Papan (Market board)', 'Pilih banyak', 'Regular, Nego, Cash (Tunai)', 'Semua', P, ''),
                  ('Jenis investor (Investor type)', 'Pilih banyak', 'Foreign, Domestic', 'Foreign', P, ''),
                  ('Jendela net', 'Angka bulat', '1 - 250', '20', P, ''), ('Jendela histori (baseline)', 'Angka bulat', '20 - 1000', '250', D, 'Disamakan 250 (user 2026-10-30).')] + REF('')),
    ('FL38', 'Net Buyer HHI', [], 'Panel sendiri', '0-1', False, 'Screener net_buy_hhi. Beda dengan FL13: hanya broker net beli, dasar net.',
     FILTER + [('Hari rolling', 'Angka bulat', '1 - 250', '20', P, '')]),
    ('FL39', 'Price Distance to Rolling Buy VWAP', [], 'Panel sendiri', '%', False, 'Screener bavg. Beda dengan FL17: jarak harga dalam %, bukan garis harga.',
     SCOPE + [('Papan (Market board)', 'Pilih banyak', 'Regular, Nego, Cash (Tunai)', 'Regular', P, 'Screener: Regular.'),
              ('Jenis investor (Investor type)', 'Pilih banyak', 'Foreign, Domestic', 'Semua', P, ''),
              ('Hari rolling', 'Angka bulat', '2 - 250', '10', P, '')] + REF('0')),
]
BY_SPEC = {n: f for f in FL for n in f[2]}
NEW_NAME = {11: 'Buy/Sell Average Transaction Size Ratio', 13: 'Average Transaction Size Percentile', 14: 'Block Money Candidate'}
FIX = {10: ('#7', '#9'), 11: ('#7 dan #8', '#1 dan #2'), 19: ('#20', '#18'), 26: ('(#34)', '(#27)')}
PAIR = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 18, 19}

H = Font(bold=True, color='FFFFFF'); HF = PatternFill('solid', fgColor='171717')
FILL = {D: PatternFill('solid', fgColor='E6F4EA'), P: PatternFill('solid', fgColor='FFF4D6'), O: PatternFill('solid', fgColor='FDE2E1')}
CH = PatternFill('solid', fgColor='E8F1FF')
wrap = Alignment(wrap_text=True, vertical='top')

def head(ws, cols, widths):
    ws.append(cols)
    for c in ws[1]: c.font = H; c.fill = HF; c.alignment = wrap
    for i, w in enumerate(widths, 1): ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = 'C2'

wb = openpyxl.Workbook()

# ---- 1. Indicator_SPECS_reviewed (the user's sheet, final) ----
u = openpyxl.load_workbook(src)['Indicator_SPECS_reviewed']
rows = list(u.iter_rows(values_only=True))
ws = wb.active; ws.title = 'Indicator_SPECS_reviewed'
cols = list(rows[0]); cols[0] = '# (Terminal)'
cols = cols[:1] + ['Spec #', 'Terminal indicator (final)'] + cols[1:]
head(ws, cols, [11, 7, 30, 30] + [30] * 15)
for k, r in enumerate(rows[1:], 1):
    r = list(r); n = k                                   # rows are in spec order 1..30
    f = BY_SPEC[n]; ch = set()
    r[0] = f[0]
    if n in NEW_NAME: r[1] = NEW_NAME[n]; ch.add(1)
    r[3] = '; '.join(f'{p[0]}: {p[3]}' + (f' ({p[2]})' if p[1] != 'Tetap' else ' (tetap)') for p in f[7]); ch.add(3)
    if n in FIX and FIX[n][0] in str(r[4]): r[4] = str(r[4]).replace(FIX[n][0], FIX[n][1])
    r[4] = 'NANTI: Terminal dulu, Screener rencana terpisah (A1, 2026-10-30). Usulan awal: ' + str(r[4]); ch.add(4)
    if isinstance(r[9], str) and 'Shares' in r[9]: r[9] += ' [ditampilkan dalam lot; F15: tetap LOT]'; ch.add(9)
    for j in (4, 13):
        if n in FIX and FIX[n][0] in str(r[j]): r[j] = str(r[j]).replace(FIX[n][0], FIX[n][1]); ch.add(j)
    if n in PAIR: r[13] = f'{r[13]} -> Final: satu indikator {f[0]} {f[1]} dengan Side Buy/Sell/Both (C6 B).'; ch.add(13)
    if n in (25, 30): r[13] = f'Final: {f[0]} Broker Inventory' + (' dengan "Show cohort total" (#25 B).' if n == 25 else ' (E14 A).'); ch.add(13)
    r[15] = 'Diabaikan (user 2026-10-30)'; ch.add(15)
    ws.append([r[0], n, f[1]] + r[1:])
    for j in ch: ws.cell(row=k + 1, column=j + 3).fill = CH
    for c in ws[k + 1]: c.alignment = wrap

# ---- 2. Parameter_Terminal (final) ----
ws = wb.create_sheet('Parameter_Terminal')
head(ws, ['# (Terminal)', 'Indikator', 'Dari spec #', 'Parameter (label di Terminal)', 'Jenis isian', 'Pilihan / rentang', 'Default',
          'Status', 'Catatan'], [11, 34, 10, 32, 22, 42, 26, 11, 60])
APPROVED = {f'FL{n}' for n in range(24, 36)}
for f in FL:
    for p in f[7]:
        if f[0] in APPROVED and p[4] == P: p = (*p[:4], D, (p[5] + ' ' if p[5] else '') + 'Disetujui 2026-10-30.')
        ws.append([f[0], f[1], ', '.join(map(str, f[2])), *p])
        for c in ws[ws.max_row]: c.alignment = wrap; c.fill = FILL[p[4]]
ws.auto_filter.ref = ws.dimensions

# ---- 3. Ringkasan ----
ws = wb.create_sheet('Ringkasan')
head(ws, ['# (Terminal)', 'Indikator', 'Dari spec #', 'Grup', 'Tempat', 'Satuan', 'Butuh frekuensi', 'Parameter', 'Catatan'],
     [11, 36, 10, 8, 26, 16, 12, 70, 60])
for f in FL:
    ws.append([f[0], f[1], ', '.join(map(str, f[2])), 'Flow', f[3], f[4], 'Ya' if f[5] else 'Tidak', '; '.join(p[0] for p in f[7]), f[6]])
    for c in ws[ws.max_row]: c.alignment = wrap
ws.append([]); ws.append(['', 'Semua indikator juga punya pengaturan tampilan Terminal: tampil/sembunyi, warna, tebal garis.'])
ws.append(['', 'Butuh frekuensi = Ya: menunggu frekuensi ditambahkan ke file broker di storage (A2, urutan B: storage dulu).'])

# ---- 4. Keputusan ----
ws = wb.create_sheet('Keputusan')
head(ws, ['Status', 'Butir', 'Isi', 'Kata user (2026-10-30)'], [11, 22, 80, 60])
K = [
    (D, 'Grup', 'Semua masuk grup Flow, dibangun seperti Net Buy Flow.', 'benar ini masuk ke indikator "Flow"'),
    (D, 'A1 lingkup', 'Terminal dulu; Backtest dan Screener rencana terpisah.', 'Terminal dulu'),
    (D, 'A2 storage', 'Frekuensi ditambahkan ke file broker yang sudah ada (pembaca membaca per nama kolom, kolom baru diabaikan).',
     'Jadikan 1 saja, di storage saat ini sudah ada broker, tinggal di tambahkan kan?'),
    (D, 'Urutan', 'Storage dulu, lalu semua indikator.', 'B dulu'),
    (D, 'B3 Top-N', 'Diurutkan berdasarkan net beli (Rp), pilihan lain tetap ada.', 'Yes agree'),
    (D, 'B4 ranking', 'Top-N dihitung ulang tiap hari.', 'Hitung hulang tiap hari, jadi apabila yang dipilih top N maka bisa sberbeda2 untuk broker'),
    (D, 'B5 default', 'Default Cakupan = Top-5.', 'Yes agree'),
    (D, 'C6 pasangan', 'Pasangan beli/jual menjadi satu indikator dengan Side Buy/Sell/Both (FL01-FL05, FL13).', 'Go with B'),
    (D, 'D7-D12', 'Turnover satu sisi; penyebut partisipasi papan terpilih; hari tanpa transaksi bukan hari beli; broker aktif = '
     'punya transaksi beli atau jual; inventori awal 0 dan harga kosong bila <= 0; baseline 250 sesi.',
     'OK / OK / Ya / Ok make sense (punya transaksi beli atau jual pada hari itu) / Ya / ya'),
    (D, 'E13 #14', 'Ambang awal dipakai dengan label belum diuji; tampil sebagai tanda.', 'OK'),
    (D, 'E14 inventori', 'Broker Inventory baru meniru panel; Net Buy Flow (Line) tetap.', 'OK'),
    (D, '#25', 'Pilihan "Show cohort total" di Broker Inventory.', 'B alright'),
    (D, 'F15 satuan', 'Tetap lot.', 'tetap LOT'),
    (D, 'Nama', 'Nama baru untuk #11, #13, #14.', 'Nama indikator pakai nama baru diatas.'),
    (D, 'Default Display', 'Diabaikan.', 'abaikan kata default ini.'),
    (D, 'Koreksi rujukan', '#10->#9, #11->#1/#2, #19->#18, #26->#27.', 'benar'),
    (D, 'Anchor default', 'Default tanggal awal tidak diubah (candle pertama yang terlihat).', 'no need'),
    (D, 'Ranking FL18-FL20', 'Kelompok broker tetap (beku) untuk FL18, FL19, FL20.', 'yes pakai kelompok broker tetap untuk ketiganya. (2026-10-30)'),
    (D, 'Nama FL01', '"Average Lot per Transaction".', 'yes (2026-10-30)'),
    (D, 'Preset di chart', 'Tidak ada indikator "Screener preset signal".', 'ini tidak usah. (2026-10-30)'),
    (D, 'Breadth', 'Satu definisi: D10 (broker net nol dihitung aktif) untuk Terminal dan Screener.', 'Kita pakai D10 (2026-10-30)'),
    (D, 'Klasifikasi broker', 'Klasifikasi institusi/ritel ikut ke storage sekarang; edit manual oleh user nanti saat Screener.',
     'Ok, tapi nanti harus dibuat opsi juga buat user mereka mau manually edit mana broker institusi/ mana broker retail. Tapi ini nanti saja saat pembangunan screener.'),
    (D, 'File lintas saham Screener', 'Nanti, bersama keputusan indikator Screener, setelah fase Terminal selesai.',
     'nanti saja. Kita mesti decide separately mana2 indikator yang boleh dimasukan ke screener dan default serta parameter yang di tweak apa saja.'),
    (D, 'Nama', 'Satu rumus = satu nama di Terminal dan Screener.', 'Samakan'),
    (D, 'Varian', 'Empat varian Screener dibuat indikator baru dengan nama sendiri (FL36-FL39).',
     'lebih baik dibuat baru, dengan nama indikator dipisahkan agar lebih jelas that they\'re different.'),
    (D, 'Bandar batas', 'Batas Screener: Acc >= 6%, Big Acc >= 10% (Dist dan Big Dist cerminannya), default Top 3; berlaku untuk FL24, panel Bandar dan Screener.',
     'Kita pakai B dulu ya which B: pakai batas Screener (6/10%), default Top 3.'),
    (D, 'FL24-FL35', 'Disetujui kecuali FL25, FL33, FL34.', 'Semua indikator F24-35 OK kecuali: FL25, FL34, FL33'),
    (D, 'FL25', 'Tetap ada.', 'FL 25 tetap ada.'),
    (D, 'FL33', 'Cukup; ukuran per hari lewat FL02 (Rolling days 1) dan FL33 (Recent sessions 1).', 'FL 33 OK'),
    (D, 'FL34', 'Kelompok institusi dan ritel bisa dipilih user, default dari IDX_Broker_Profile.', 'FL 34 OK'),
    (D, 'FL36-FL39', 'Disetujui.', 'FL36 OK, FL 37 OK, FL 38 OK, FL 39 OK'),
    (D, 'Default dan candle', 'Default kuning disetujui; di chart mingguan/bulanan "hari" = candle.', '2-3 OK'),
    (D, 'Rilis', '39 indikator sekaligus setelah storage.', '4 sekaligus.'),
    (D, 'Bandar', '"Bandar" = N broker dengan net beli (Rp) terbesar dalam jendela indikator, dihitung ulang tiap hari; default N = 3 untuk semua.',
     'Usul saya: satu default untuk semua, yaitu Top 3 ... OK'),
    (D, 'Nama', 'Pola "Keluarga · pembeda" (sheet Ringkasan, kolom nama).', 'Indikator yang hanya beda dasar atau filter, tapi namanya jauh berbeda OK'),
    (D, 'Panel Bandar', 'Panel Bandar Terminal ikut batas 6/10% dan Top 3 (label Neutral, Acc, Big Acc, Dist, Big Dist).', '3. OK'),
    (D, 'Histori percentile', 'FL21 dan FL37 memakai 250 sesi.', '1. OK'),
    (D, 'FL07', 'Tetap terpisah dari FL03.', '2. Tetap pisah dulu'),
    (D, 'Menu', 'Grup Flow dibagi subgrup per keluarga nama.', '3. OK'),
]
for r in K:
    ws.append(list(r))
    for c in ws[ws.max_row]: c.alignment = wrap
    ws.cell(row=ws.max_row, column=1).fill = FILL[r[0]]

# ---- 5. Screener flow metrics and presets onto the chart ----
ws = wb.create_sheet('Screener_ke_Chart')
head(ws, ['Screener id', 'Nama di Screener', 'Jenis', 'Status di Screener', 'Bisa di chart?', 'Sudah ada / sama dengan',
          'Bentuk di chart', 'Parameter di chart (default)', 'Data', 'Catatan'], [14, 32, 10, 18, 12, 30, 26, 46, 22, 50])
S = [
    ('silent', 'Silent accumulation', 'pattern', 'Ada', 'Ya', 'Baru', 'Tanda di bawah candle',
     'Recent sessions (5), Baseline sessions (20), Volume x (1.5), Max move % (3)', 'harga + volume (sudah ada)', ''),
    ('adv20_idr', 'Average daily value (20 sessions)', 'universe', 'Ada', 'Ya', 'Baru', 'Panel sendiri, garis',
     'Sessions (20)', 'harga + volume (sudah ada)', 'Screener memakai 20 tetap; di chart bisa diubah.'),
    ('fnet', 'Foreign net value', 'flow', 'No data (Phase 2)', 'Sudah', 'Net Buy Flow, investor Foreign', '-',
     'Rolling days (20), Market board', 'broker', 'Tidak perlu indikator baru.'),
    ('fpct', 'Foreign net intensity', 'flow', 'No data (Phase 2)', 'Ya', 'FL11 Net Flow / Turnover, Cakupan = Semua broker, investor Foreign', '-',
     'Hari rolling (20), Papan, Jenis investor', 'broker', 'Tidak perlu indikator baru.'),
    ('fpart', 'Foreign participation', 'flow', 'Belum (Phase 2 lanjutan)', 'Ya', 'FL36 Participation Rate (Buy + Sell)',
     'Panel sendiri, garis %', 'Jenis investor (Foreign), Hari rolling (20)', 'broker', ''),
    ('fstreak', 'Foreign net streak', 'flow', 'No data (Phase 2)', 'Ya', 'Baru', 'Panel sendiri, histogram (+ hari beli beruntun, - hari jual)',
     'Jenis investor (Foreign), Papan, Batas (60)', 'broker', 'Bisa dibuat umum: streak untuk kelompok broker mana pun.'),
    ('fsurprise', 'Foreign flow surprise', 'flow', 'Belum (Phase 2 lanjutan)', 'Ya', 'FL37 Net Flow Surprise Percentile',
     '-', 'Jendela net (20), Histori (250)', 'broker', ''),
    ('broker', 'Broker net (chosen broker)', 'flow', 'No data (Phase 2)', 'Sudah', 'Net Buy Flow, pilih broker', '-',
     'Brokers, Rolling days (5)', 'broker', 'Tidak perlu indikator baru.'),
    ('topacc', 'Top-N broker net accumulation', 'flow', 'No data (Phase 2)', 'Ya', 'Baru', 'Panel sendiri, histogram Rp',
     'Top N (5), Hari rolling (10), Papan', 'broker', 'Net Top-N pembeli + net Top-N penjual.'),
    ('buy_intensity', 'Buy intensity (top-N net buyers)', 'flow', 'No data (Phase 2)', 'Ya', 'FL11 dengan Cakupan = Top-N', '-',
     'Top N (3), Hari rolling (10)', 'broker', 'Tidak perlu indikator baru.'),
    ('bandar', 'Bandar balance (top-N)', 'flow', 'No data (Phase 2)', 'Ya', 'FL24 Bandar Balance (Top-N)',
     'Panel sendiri, garis % dengan garis acuan +-6 dan +-10', 'Top N (3), Hari rolling (10), Papan; garis acuan Acc 6, Big Acc 10', 'broker',
     'Dipakai preset Big Accumulation, Silent Accumulation, Near Bandar Average Price.'),
    ('net_buy_hhi', 'Net-buy concentration (HHI)', 'flow', 'No data (Phase 2)', 'Ya', 'FL38 Net Buyer HHI',
     '-', 'Hari rolling (20)', 'broker', ''),
    ('conc_gap', 'Buy-vs-sell concentration gap', 'flow', 'Belum (Phase 2 lanjutan)', 'Ya', 'Sama dengan FL14 HHI Asymmetry', '-', '-', 'broker',
     'Tidak perlu indikator baru.'),
    ('breadth', 'Broker breadth', 'flow', 'No data (Phase 2)', 'Ya', 'FL22 Broker Buy Breadth (definisi D10)', '-', '-', 'broker',
     'User 2026-10-30: pakai D10 untuk keduanya.'),
    ('bavg', 'Top-buyer cost distance', 'flow', 'Belum (Phase 2 lanjutan)', 'Ya', 'FL39 Price Distance to Rolling Buy VWAP', '-',
     'Top 3, Hari rolling (10), Papan Regular', 'broker', 'Dipakai preset Near Bandar Average Price.'),
    ('dominant_persistence', 'Dominant-buyer persistence', 'flow', 'Belum (Phase 2 lanjutan)', 'Ya', 'Mirip FL12, tetapi pembeli terbesar dibeku per jendela',
     'Panel sendiri, garis %', 'Hari (20), Papan', 'broker', 'Bertentangan dengan B4 (ulang tiap hari) bila dijadikan pilihan FL12.'),
    ('acc_days', 'Accumulation-day ratio', 'flow', 'Belum (Phase 2 lanjutan)', 'Ya', 'Turunan bandar balance', 'Panel sendiri, garis %',
     'Hari (20), Top N (3), Ambang x', 'broker', ''),
    ('freq', 'Trade-count spike', 'flow', 'No data (Phase 2)', 'Ya, setelah frekuensi ada di storage', 'Baru', 'Panel sendiri, garis x dengan garis acuan 2.5',
     'Baseline sessions (20), Papan', 'broker + frekuensi', 'Dipakai preset Frequency Spike.'),
    ('trade_size_change', 'Average trade size change', 'flow', 'Belum (Phase 2 lanjutan)', 'Ya, setelah frekuensi ada', 'Turunan FL02',
     'Panel sendiri, garis %', 'Recent (5), Baseline (20), Papan', 'broker + frekuensi', ''),
    ('crossing_share', 'Crossing share (Nego + Tunai)', 'flow', 'No data (Phase 2)', 'Ya', 'Baru', 'Panel sendiri, garis %',
     'Hari rolling (20)', 'broker', ''),
    ('inst_retail', 'Institutional vs retail broker net', 'flow', 'Belum (Phase 2 lanjutan)', 'Ya, setelah klasifikasi ada di storage', 'FL34 Institutional vs Retail Net',
     'Panel sendiri, garis %', 'Hari rolling (20), Papan', 'broker + klasifikasi broker',
     'Klasifikasi ada di database (IDX_Broker_Profile.broker_classification) tetapi belum dikirim ke storage (ref/brokers hanya kode, nama, tipe).'),
    ('insider_net', 'Insider and major-holder net change', 'flow', 'Belum (Phase 2 lanjutan)', 'Ya', 'Baru (rail event sudah menampilkan transaksi insider)',
     'Panel sendiri, histogram Rp', 'Hari rolling (20)', 'event insider (sudah ada)', ''),
]
for r in S:
    ws.append(list(r))
    for c in ws[ws.max_row]: c.alignment = wrap
ws.auto_filter.ref = ws.dimensions

ws = wb.create_sheet('Indikator_baru_dari_Screener')
head(ws, ['Usulan id', 'Nama (usulan, sama di Terminal dan Screener)', 'Screener id', 'Rumus', 'Maksud', 'Kegunaan', 'Hati-hati',
          'Parameter (default)', 'Data', 'Data sudah di storage?'], [10, 30, 16, 52, 44, 44, 44, 40, 24, 16])
NEW = [
    ('FL24', 'Bandar Balance (Top-N)', 'bandar',
     '100 x (net N pembeli terbesar + net N penjual terbesar) / nilai transaksi, dijumlah D sesi. Net penjual bernilai negatif.',
     'Apakah broker besar di sisi beli lebih kuat dari broker besar di sisi jual, dibanding seluruh nilai transaksi.',
     'Membaca akumulasi atau distribusi oleh "bandar". Screener: >= 10 Big Acc, >= 6 Acc, <= -6 Dist, <= -10 Big Dist.',
     'Angkanya sama dengan vonis panel Bandar Terminal (total beli = nilai transaksi), tetapi batas label berbeda: panel 3/6/12%, Screener 6/10%.',
     'Top N (3), Hari rolling (10), Papan; garis acuan 6, 10, -6, -10', 'broker', 'Ya'),
    ('FL25', 'Top-N Net Accumulation', 'topacc',
     'net N pembeli terbesar + net N penjual terbesar (Rp), dijumlah D sesi.',
     'Sama dengan Bandar Balance, tetapi dalam Rupiah, tidak dibagi nilai transaksi.',
     'Melihat besarnya uang bandar dalam Rupiah di satu saham.',
     'Tidak bisa dibandingkan antar saham (saham besar selalu terlihat besar). Untuk perbandingan pakai FL24.',
     'Top N (5), Hari rolling (10), Papan', 'broker', 'Ya'),
    ('FL26', 'Net Flow Streak', 'fstreak',
     'Hitung hari berturut-turut sampai hari ini dengan net > 0 (positif) atau net < 0 (negatif); dibatasi 60.',
     'Berapa hari berturut-turut kelompok (misalnya asing) membeli bersih atau menjual bersih.',
     'Membaca konsistensi arus. Preset Screener: streak asing > 4 hari.',
     'Satu hari net kecil di arah sebaliknya memutus streak.',
     'Cakupan (default: semua broker), Jenis investor (Foreign), Papan, Batas (60)', 'broker', 'Ya'),
    ('FL27', 'Silent Accumulation', 'silent',
     'Rata-rata volume 5 sesi / rata-rata volume 20 sesi sebelumnya >= 1,5 dan |perubahan harga 5 sesi| <= 3%.',
     'Volume naik tetapi harga hampir diam.',
     'Tanda kemungkinan akumulasi diam-diam sebelum harga bergerak.',
     'Bisa juga distribusi diam-diam; sebaiknya dibaca bersama Bandar Balance.',
     'Recent sessions (5), Baseline sessions (20), Volume x (1,5), Max move % (3)', 'harga + volume', 'Ya'),
    ('FL28', 'Average Daily Value', 'adv20_idr',
     'Rata-rata (harga penutupan x volume) selama N sesi.',
     'Rata-rata nilai Rupiah yang diperdagangkan per hari.',
     'Saringan likuiditas: arus broker di saham sepi lebih mudah menyesatkan.',
     'Bukan sinyal arah.', 'Sessions (20)', 'harga + volume', 'Ya'),
    ('FL29', 'Accumulation-Day Ratio', 'acc_days',
     'Bagian dari D sesi terakhir yang Bandar Balance hariannya (Top N) di atas ambang x.',
     'Seberapa sering akumulasi terjadi dalam satu periode.',
     'Membedakan akumulasi yang konsisten dari satu hari besar saja.',
     'Screener belum menetapkan default ambang x; usulan 0.',
     'Hari (20), Top N (3), Ambang x (0)', 'broker', 'Ya'),
    ('FL30', 'Crossing Share (Nego + Tunai)', 'crossing_share',
     '100 x nilai papan Nego dan Tunai / nilai semua papan, dijumlah D sesi.',
     'Berapa bagian transaksi yang terjadi di luar pasar reguler.',
     'Lonjakan bisa berarti transaksi blok, crossing, atau pengalihan antar pihak.',
     'Transaksi Nego tidak selalu berarti akumulasi; harganya bisa jauh dari pasar.',
     'Hari rolling (20)', 'broker', 'Ya'),
    ('FL31', 'Insider Net Change', 'insider_net',
     'Nilai BELI dikurangi JUAL oleh insider dan pemegang saham besar, tanggal transaksi dalam D sesi terakhir.',
     'Arah transaksi orang dalam.',
     'Konfirmasi dari pihak yang paling tahu kondisi perusahaan.',
     'Data datang dari laporan (bisa terlambat dilaporkan).',
     'Hari rolling (20)', 'event insider', 'Ya (rail event)'),
    ('FL32', 'Trade-Count Spike', 'freq',
     'Jumlah transaksi hari ini / rata-rata jumlah transaksi N sesi sebelumnya (frekuensi beli semua broker).',
     'Lonjakan aktivitas transaksi.',
     'Menangkap awal minat baru. Preset Screener: naik melewati 2,5x.',
     'Lonjakan bisa karena berita atau ritel; baca bersama ukuran transaksi (FL01).',
     'Baseline sessions (20), Papan; garis acuan 2,5', 'broker + frekuensi', 'Belum (frekuensi)'),
    ('FL33', 'Average Trade Size Change', 'trade_size_change',
     '100 x (nilai per transaksi 5 sesi terakhir / nilai per transaksi 20 sesi sebelumnya - 1).',
     'Apakah ukuran transaksi membesar atau mengecil.',
     'Membesar: kemungkinan pemain besar masuk; mengecil: lebih banyak ritel.',
     'Mirip FL02 dan FL08; bedanya membandingkan dua periode.',
     'Recent (5), Baseline (20), Papan', 'broker + frekuensi', 'Belum (frekuensi)'),
    ('FL34', 'Institutional vs Retail Net', 'inst_retail',
     '100 x (net broker Institutional-heavy - net broker Retail-heavy) / nilai transaksi, dijumlah D sesi.',
     'Siapa yang dominan: broker institusi atau broker ritel.',
     'Membaca apakah arus didorong institusi atau ritel.',
     'Klasifikasi broker adalah yang berlaku sekarang (IDX_Broker_Profile), dipakai untuk seluruh histori.',
     'Hari rolling (20), Papan', 'broker + klasifikasi broker', 'Belum (klasifikasi)'),
    ('FL35', 'Dominant-Buyer Persistence', 'dominant_persistence',
     'Pembeli net terbesar selama D sesi ditentukan sekali; lalu dihitung bagian hari dalam D sesi saat broker itu membeli bersih.',
     'Apakah pembeli terbesar membeli terus, atau hanya sekali besar.',
     'Membedakan akumulasi bertahap oleh satu pihak dari transaksi sekali jalan.',
     'Pembeli terbesar dibeku per jendela (beda dengan FL12 yang Top-N-nya ulang tiap hari).',
     'Hari (20), Papan', 'broker', 'Ya'),
    ('FL36', 'Participation Rate (Buy + Sell)', 'fpart',
     '100 x (nilai beli + nilai jual kelompok) / (2 x nilai transaksi), dijumlah D sesi.',
     'Seberapa besar kelompok (misalnya asing) ikut dalam semua transaksi, dari dua sisi.',
     'Mengukur keterlibatan, bukan arah. Partisipasi asing naik sering mendahului pergerakan besar.',
     'Beda dengan FL07 yang hanya sisi beli. Tinggi bisa berarti beli besar atau jual besar.',
     'Cakupan (Semua broker), Jenis investor (Foreign), Papan, Hari (20)', 'broker', 'Ya'),
    ('FL37', 'Net Flow Surprise Percentile', 'fsurprise',
     'Percentile net Rupiah D sesi terakhir dibanding 250 nilai sebelumnya (aturan mid-rank; Screener 252, disamakan 250).',
     'Apakah arus bersih saat ini luar biasa dibanding kebiasaan saham itu sendiri.',
     'Menemukan arus yang tidak biasa tanpa ambang Rupiah yang sama untuk semua saham.',
     'Beda dengan FL21 yang memakai net / turnover; saham yang makin likuid membuat net Rupiah ikut naik.',
     'Cakupan (Semua broker), Jenis investor (Foreign), Jendela net (20), Histori (250)', 'broker', 'Ya'),
    ('FL38', 'Net Buyer HHI', 'net_buy_hhi',
     'Jumlah kuadrat porsi tiap broker net beli terhadap total net beli positif, D sesi.',
     'Apakah pembelian bersih dikuasai sedikit broker.',
     'Lebih tajam membaca akumulasi terpusat daripada HHI beli kotor (FL13).',
     'Beda dengan FL13 yang memakai beli kotor seluruh broker. Bila hanya sedikit broker net beli, nilai cenderung tinggi.',
     'Papan, Jenis investor, Hari (20)', 'broker', 'Ya'),
    ('FL39', 'Price Distance to Rolling Buy VWAP', 'bavg',
     '100 x (harga penutupan / VWAP beli kelompok selama D sesi - 1). VWAP = nilai beli / (lot beli x 100).',
     'Seberapa jauh harga sekarang dari harga rata-rata beli bandar baru-baru ini.',
     'Dekat 0: harga di sekitar modal bandar (preset Screener: dalam +-3%).',
     'Beda dengan FL17 yang menggambar VWAP sebagai garis harga. Rata-rata beli, bukan modal sisa.',
     'Cakupan (Top 3 net beli), Papan (Regular), Hari (10)', 'broker', 'Ya'),
]
for r in NEW:
    ws.append(list(r))
    for c in ws[ws.max_row]: c.alignment = wrap
RENAME = {
 'Net Flow Abnormality Percentile': 'Net Flow Percentile · vs Turnover', 'Net Flow Surprise Percentile': 'Net Flow Percentile · Rupiah',
 'Participation Rate (Buy + Sell)': 'Share · Market Value (Buy + Sell)', 'Buy Participation Rate': 'Share · Market Volume',
 'Volume Share': 'Share · Volume', 'Frequency Share': 'Share · Transactions',
 'Buyer/Seller HHI': 'Concentration HHI · Gross', 'Net Buyer HHI': 'Concentration HHI · Net Buy', 'HHI Asymmetry': 'Concentration HHI · Buy − Sell',
 'Top-N Buy Concentration': 'Concentration Top-N · Gross Buy', 'Top-N Net Buy Concentration': 'Concentration Top-N · Net Buy',
 'Bandar Balance (Top-N)': 'Bandar Balance · %', 'Top-N Net Accumulation': 'Bandar Balance · Rupiah', 'Accumulation-Day Ratio': 'Bandar Balance · Accumulation Days',
 'Buy Persistence N-Day': 'Net Buy Persistence · Cohort', 'Dominant-Buyer Persistence': 'Net Buy Persistence · Top Buyer',
 'Price Distance to Rolling Buy VWAP': 'Buy VWAP · Rolling · Distance %', 'Rolling Buy VWAP N-Day': 'Buy VWAP · Rolling',
 'Anchored Accumulation VWAP': 'Buy VWAP · Anchored', 'Price Distance to Implied Cost': 'Implied Cost · Distance %',
 'Implied Inventory Average Cost': 'Implied Cost · Anchored',
 'Average Lot per Transaction': 'Transaction Size · Lot', 'Average Value per Transaction': 'Transaction Size · Value',
 'Buy/Sell Average Transaction Size Ratio': 'Transaction Size · Buy/Sell Ratio', 'Average Transaction Size Percentile': 'Transaction Size · Percentile',
 'Average Trade Size Change': 'Transaction Size · Change %', 'Size Ratio': 'Transaction Size · vs Market',
 'Cohort Frequency Imbalance': 'Transactions · Buy/Sell Imbalance', 'Trade-Count Spike': 'Transactions · Spike',
}
ORDER = sorted(RENAME, key=len, reverse=True)
NAMECOL = {'Indicator_SPECS_reviewed': [3], 'Parameter_Terminal': [2], 'Ringkasan': [2], 'Indikator_baru_dari_Screener': [2]}
for ws in wb.worksheets:
    for col in NAMECOL.get(ws.title, []):
        for row in ws.iter_rows(min_row=2, min_col=col, max_col=col):
            c = row[0]
            if isinstance(c.value, str) and c.value in RENAME: c.value = RENAME[c.value]
    if ws.title == 'Screener_ke_Chart':
        for row in ws.iter_rows(min_row=2):
            for c in row:
                if isinstance(c.value, str):
                    for k in ORDER:
                        if f' {k}' in c.value: c.value = c.value.replace(f' {k}', f' {RENAME[k]}'); break
wb.save(out)
print(len(FL), 'indicators,', sum(len(f[7]) for f in FL), 'parameters,', len(S), 'screener rows')
