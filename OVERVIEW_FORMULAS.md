# Rumus Market Overview (dev)

<!-- explained-for: overview.py=ec4d588d48d5767519cbcf16e808d746, model.ts=f807be497cd316b11d7fad04f98c41f8, overview_stock_size=f451fc552b78a6174bc47b4e2a217293 -->

Dokumen ini menjelaskan **setiap angka di halaman Market Overview** (tab "Overview" di EDGE) dengan bahasa sederhana
dan contoh angka asli dev. Pakai dokumen ini saat ingin mengubah rumus, atau saat bertanya dari mana sebuah angka
datang.

- **Sumber kebenaran:**
  - `apps/terminal-publisher/overview.py`: menghitung semua angka dari Postgres dan menyimpannya sebagai file
    `overview/*.json.gz` di storage.
  - Fungsi database `public.overview_stock_size(date)`: ukuran kotak peta pasar.
  - `apps/edge-bff/overview/src/model.ts`: halaman tidak menghitung angka baru. Ia hanya memilih saham sesuai universe,
    periode dan metrik pilihan pengguna, lalu menjumlah, merata-rata dengan bobot, atau mengurutkannya.
- **Angka yang berlaku** (jendela, periode, skala warna, sidik jari kode) ada di bagian paling bawah. Bagian itu ditulis
  otomatis dari kode, jadi selalu sama dengan kode di repo.
- **Contoh** memakai data asli dev: harga **Jumat 13 Nov 2026**, data broker **Senin 9 Nov 2026** (data broker terakhir
  yang sudah dimuat). Rupiah ditulis dalam miliar (Rp M) atau triliun (Rp T). Di halaman (bahasa Inggris) miliar ditulis
  "B" dan triliun "T".

## Cara dokumen ini dijaga tetap benar

1. **Setiap push ke GitHub:** tes `scripts/tests/test_overview_formulas_doc.py` menjalankan
   `scripts/overview_formulas_doc.py --repo`. Tes merah bila:
   - konstanta atau sidik jari di bagian bawah tidak sama dengan kode; atau
   - penjelasan di atas ditulis untuk versi kode yang lain (baris `explained-for` di atas).
2. **Setiap hari (01:17 WIB):** workflow `database-schema-docs.yml` menjalankan `--check`. Selain pengecekan di atas, ia
   membandingkan fungsi `overview_stock_size` di database dev dengan isi migrasinya. Beda = merah.
3. **Aturan kerja (AGENTS.md):** setiap perubahan rumus Overview memperbarui dokumen ini di commit yang sama:
   - jalankan `python3 scripts/overview_formulas_doc.py --write`;
   - perbarui penjelasan;
   - samakan baris `explained-for` dengan sidik jari baru.

"Sidik jari" = md5 dari isi kode. Satu huruf berubah, sidik jarinya berubah. Sidik jari `overview.py` juga dipakai
publisher sebagai `CODE`: kalau berubah, publisher menulis ulang semua file Overview.

**Batas:** publisher di-deploy lewat Railway CLI, bukan otomatis dari GitHub. Cek harian tidak bisa melihat kode yang
sedang berjalan di publisher. Gantinya: publisher menulis `CODE` sebagai elemen terakhir `overview_stamp` di
`state.json`. Setelah deploy publisher, cocokkan nilai itu dengan sidik jari `overview.py` di bawah.

---

## Gambaran: dari mana angka datang

```
Postgres (harga, Feature 01/04/06, daftar saham)
  ─► publisher (overview.py) ─► 3 file: overview-meta, overview-series, overview-day-<tanggal>
  ─► halaman (model.ts memilih dan mengurutkan)
```

| Panel | File | Tabel sumber |
|---|---|---|
| KPI IHSG, LQ45 | day `index` | `Price_Stock_Indonesia_IDX` (harian final) |
| KPI Breadth | day `breadth` | `Feature_01_Stock_Daily.return_1d_pct` |
| KPI Turnover, Foreign net; panel Foreign Flow (total pasar) | day `market` | `Feature_06_Foreign_Domestic_INDEX` (IHSG, papan Regular) |
| KPI Volatility | day `volatility` | penutupan IHSG di tabel harga |
| Peta pasar, Top Movers | day `stocks` | Feature 01 (return), `overview_stock_size` (ukuran), Feature 06 (net asing per saham) |
| Grafik IHSG | day `intraday` (1D, 5D), series `index` (1M, 1Y) | `price_stock_idx_intraday`, tabel harga |
| Sector Performance | series `sector` | penutupan 11 indeks sektor IDX (`Feature_Index_Entity` jenis SECTOR) |
| % Above EMA | series `above_ema50`, `above_ema200` | `Feature_04_Technical_Indicator` |
| Foreign Flow (daftar saham) | day `stocks.fnet_*` | `Feature_06_Foreign_Domestic` (papan Regular) |

"Saham" di semua panel = baris `IDX_Stock_Universe` dengan `Security Type = 'stock'` (saham biasa). Reksa dana,
ETF dan kode indeks tidak dihitung.

## 1. Dua tanggal: harga dan broker

- **Tanggal harga** = tanggal yang dipilih di pemilih tanggal ("Fri 13 Nov · Close"). Semua angka harga, return, EMA
  dan volatilitas memakai tanggal ini.
- **Tanggal broker** = tanggal terbaru data broker (Feature 06 _INDEX, IHSG, Regular) yang **tidak lebih baru** dari
  tanggal harga. Turnover dan semua angka asing memakai tanggal ini.
- Contoh: tanggal harga 13 Nov, data broker baru sampai 9 Nov. Maka:
  - penanda di kepala halaman berbunyi "Prices to Fri 13 Nov" dan "Broker data to Mon 9 Nov" (kuning karena tertinggal);
  - kartu Turnover dan Foreign net memakai label kecil "9 Nov".
- Pemilih tanggal menampilkan **20 tanggal pasar terakhir** yang punya data Feature 01. Satu file per tanggal.

## 2. KPI IHSG dan LQ45

- **Angka besar** = penutupan hari itu.
- **Perubahan** = penutupan − penutupan sesi sebelumnya; persen = perubahan ÷ penutupan sebelumnya × 100.
- Contoh IHSG 13 Nov: 5.344,41 − 5.250,90 = **+93,51**; 93,51 ÷ 5.250,90 = **+1,78%**. Rentang hari 5.215,15–5.361,94.
- Contoh LQ45: 550,37 vs 543,06 → **+7,31 (+1,35%)**.
- **Garis kecil** (sparkline) = 30 penutupan terakhir. Hijau bila penutupan terakhir ≥ penutupan pertama dari 30 itu,
  merah bila lebih rendah. Garis ini menggambarkan arah 30 sesi, bukan hari ini. Contoh: IHSG naik 1,78% hari ini,
  tetapi garisnya merah karena IHSG turun dalam 30 sesi.

## 3. Breadth (saham naik dan turun)

- Hitung saham dengan `return_1d_pct` Feature 01 pada tanggal itu: **naik** = di atas 0, **turun** = di bawah 0,
  **tetap** = tepat 0. Saham tanpa nilai return tidak dihitung.
- **A/D** = jumlah naik ÷ jumlah turun.
- Contoh 13 Nov (836 saham punya return): **564 naik, 143 turun, 129 tetap**; A/D = 564 ÷ 143 = **3,94×**.

## 4. Turnover (nilai transaksi)

- **Turnover** = beli asing + beli domestik, papan Regular, IHSG, pada tanggal broker. Setiap transaksi punya satu
  pembeli, jadi jumlah semua beli = nilai transaksi.
- **Rata-rata 20D** = rata-rata turnover dari **20 tanggal broker sebelumnya** (tanggal itu sendiri tidak ikut).
- **Rasio** = turnover ÷ rata-rata 20D.
- Contoh 9 Nov:
  - turnover = 3.258,17 + 4.894,98 = **Rp 8.153,2 M (Rp 8,15T)**;
  - rata-rata 12 Okt–6 Nov = Rp 13.459,5 M;
  - rasio = 8.153,2 ÷ 13.459,5 = **0,61×**. Pasar jauh lebih sepi dari biasanya.
- Garis kecil = turnover 30 tanggal broker terakhir.

## 5. Foreign net (KPI)

- **1D** = beli asing − jual asing (IHSG, Regular) pada tanggal broker.
- **10D** = jumlah net asing 10 tanggal broker terakhir, termasuk tanggal itu.
- Contoh 9 Nov:
  - 1D = 3.258,17 − 3.141,56 = **+Rp 116,6 M**;
  - 10D (27 Okt–9 Nov) = **−Rp 2.813,3 M (−Rp 2,81T)**.

## 6. Volatility (20D)

- **Volatilitas** = rumus Feature 01, dihitung dari penutupan IHSG:
  1. ambil 20 return harian terakhir (penutupan ÷ penutupan sebelumnya − 1);
  2. hitung simpangan baku sampel (dibagi 19);
  3. kalikan √252 (disetahunkan) dan × 100.
- **Persentil "vs own 1Y"** = persen dari **252 nilai volatilitas sebelumnya** yang **lebih kecil** dari nilai hari ini
  (cara yang sama dengan Radar). Hanya diisi bila ke-252 nilai itu ada.
- Contoh 13 Nov:
  - volatilitas = **35,98%**;
  - 204 dari 252 nilai sebelumnya lebih kecil → 204 ÷ 252 = 80,95 → **P81**;
  - dalam setahun itu volatilitas berkisar 8,73%–54,53%.

## 7. Peta pasar (Market map)

### Ukuran kotak

- Sumber satu-satunya: fungsi `overview_stock_size(tanggal)`. File menyimpan nama dasarnya (`size_basis`) dan halaman
  menuliskannya ("size: 20-day average value traded").
- Sekarang (`adv20_value`):
  - ukuran = jumlah (penutupan × volume) selama **20 sesi pasar terakhir**, dibagi 20;
  - sesi pasar = tanggal IHSG di tabel harga; hari tanpa transaksi dihitung 0, jadi saham yang lama disuspensi
    kotaknya kecil;
  - saham tanpa transaksi sama sekali dalam 20 sesi tidak punya ukuran dan tidak digambar.
- Contoh 13 Nov (sesi 19 Okt–13 Nov): BBCA **Rp 1.685,2 M per hari**, BMRI Rp 824,8 M per hari.
- **Nanti, saat data saham beredar ada** (keputusan user 2026-11-15): satu migrasi baru mengganti fungsi menjadi
  penutupan × saham beredar dengan `size_basis = 'market_cap'`. Halaman otomatis menulis "size: market cap" tanpa
  perubahan kode halaman.

### Warna "Performance"

- Nilai = return saham pada periode pilihan: 1D = `return_1d_pct`, 5D = `return_5d_pct`, 1M = `return_20d_pct`
  (Feature 01).
- Nilai dibagi **pembagi periode** (1D: 1, 5D: 2, 1M: 4), lalu masuk ke langkah warna:

| Hasil bagi | Warna |
|---|---|
| ≥ 3 | hijau paling tua |
| 1,5 sampai < 3 | hijau |
| di atas 0 sampai < 1,5 | hijau muda |
| tepat 0 | abu-abu (netral) |
| di bawah 0 sampai −1,5 | merah muda |
| di atas −3 sampai −1,5 | merah |
| ≤ −3 | merah paling tua |

- **Abu-abu hanya untuk return 0** (keputusan user 2026-11-15, pilihan 3: "Hanya return persis 0% yang abu-abu").
  - Return yang naik sekecil apa pun hijau muda; yang turun sekecil apa pun merah muda.
  - "0" dihitung dari angka yang tertulis di kotak (2 desimal), jadi kotak abu-abu selalu bertulisan 0,00%.
  - Desain semula memakai pita netral −0,5 sampai +0,5; pita itu tidak dipakai lagi (Foreign buy juga mengikuti aturan
    ini, di bawah).
- Artinya untuk 1M batasnya 0, ±6%, ±12% (return sebulan wajar lebih besar dari return sehari).
- Contoh 13 Nov, 1D:
  - BBCA +0,46% → **hijau muda** (dulu abu-abu);
  - BMRI 0,00% → **abu-abu**;
  - WIFI +19,59% → ≥ 3 → **hijau paling tua**.

### Warna "Foreign buy"

- Nilai = net asing saham (papan Regular, Feature 06) pada tanggal broker: 1D = `foreign_net_1d`, 5D = `foreign_net_5d`,
  1M = `foreign_net_20d`.
- Pembagi = **Rp 120 M × √(jumlah sesi)**: 1D Rp 120 M, 5D Rp 268 M, 1M Rp 537 M. Langkahnya sama dengan tabel
  Performance di atas (keputusan user 2026-11-15: "Foreign buy samakan juga"):
  - abu-abu hanya bila kotak bertulisan **0**, yaitu net di bawah Rp 1 juta (jumlah sekecil itu ditulis "0");
  - net beli lain → paling tidak hijau muda; net jual lain → paling tidak merah muda;
  - untuk 1D: hijau/merah mulai ±Rp 180 M, paling tua mulai ±Rp 360 M.
- Contoh 9 Nov, 1D:
  - BBCA +Rp 523,1 M ÷ 120 = 4,36 → **hijau paling tua**;
  - BMRI −Rp 134,5 M ÷ 120 = −1,12 → **merah muda**;
  - net +Rp 30 M → **hijau muda** (dulu abu-abu); saham tanpa transaksi asing (net 0) → **abu-abu**.

### Judul sektor dan universe

- Kotak dikelompokkan per sektor `IDX_Stock_Universe`. Sektor "Undefined" ditulis **"Other"** (keputusan 5).
- **Angka di judul sektor:**
  - Performance: rata-rata return saham sektor itu, **dibobot ukuran kotak**;
  - Foreign buy: **jumlah** net asingnya;
  - saham tanpa nilai tidak ikut.
- **Universe** = semua saham, atau satu daftar indeks/grup Stockbit (`Stock_List` dan anggotanya, sama dengan Screener).
  Bawaan: **LQ45**. Universe juga menentukan Top Movers.
- Klik kotak: popover dengan return dan net asing periode itu. Bila data broker tertinggal, ada catatan tanggal
  brokernya. Tombol "Open in Terminal" membuka saham itu di Terminal.

## 8. Grafik IHSG

| Periode | Titik | Pembanding (garis putus-putus / persen) |
|---|---|---|
| 1D | bar 5 menit sesi itu (`price_stock_idx_intraday`) | penutupan sesi sebelumnya |
| 5D | bar 1 jam dari 5 sesi yang berakhir di tanggal itu | titik pertama |
| 1M | 21 penutupan harian (20 sesi ke belakang + titik awal) | titik pertama |
| 1Y | 253 penutupan harian (252 sesi ke belakang + titik awal) | titik pertama |

- Baris Open/High/Low/Close:
  - **1D:** angka resmi hari itu dari tabel harga;
  - **periode lain:** "Start/High/Low/End" dari penutupan pada periode itu. High = penutupan tertinggi, bukan harga
    tertinggi intraday.
- Contoh 13 Nov, 1D: Open 5.265,67, High 5.361,94, Low 5.215,15, Close 5.344,41; +93,51 (+1,78%) dari penutupan
  sebelumnya.
- Tiga kotak di bawah grafik mengulang Breadth, Turnover dan Foreign net 1D (dengan tanggal broker bila tertinggal).

## 9. Sector Performance

- Garis = **return kumulatif** indeks sektor IDX dari titik awal periode:
  `penutupan hari ke-n ÷ penutupan titik awal − 1`.
- Titik awal:

| Periode | Titik awal |
|---|---|
| 20D | 20 sesi sebelum tanggal terpilih |
| 60D | 60 sesi sebelum tanggal terpilih |
| YTD | sesi terakhir tahun sebelumnya (30 Des 2025) |
| 1Y | 252 sesi sebelum tanggal terpilih |

- Garis putus-putus hitam = IHSG dengan rumus yang sama.
- Batang di kanan = nilai akhir tiap sektor, diurutkan dari yang terbaik.
- Garis berwarna = 2 sektor terbaik dan 2 terburuk; sektor lain abu-abu. Arahkan kursor ke nama sektor untuk menyorot
  garisnya.
- Contoh 60D (20 Agu → 13 Nov):
  - IDXFINANCE 1.365,65 → 1.246,64 = **−8,7%**;
  - IHSG 6.501,59 → 5.344,41 = **−17,8%**.
- Contoh YTD:
  - IDXFINANCE 1.550,07 → 1.246,64 = **−19,6%**;
  - IHSG 8.646,94 → 5.344,41 = **−38,2%**.
- Kalau satu penutupan hilang, garis diputus di titik itu (tidak diisi dengan angka karangan).

## 10. % Above EMA

- **% di atas EMA50** = jumlah saham dengan penutupan **lebih besar dari** `ema_50` ÷ jumlah saham yang punya `ema_50`,
  × 100. Sumbernya Feature 04, harian, saham biasa. EMA200 sama dengan `ema_200`.
- **Perubahan "vs 5 sessions"** = nilai hari ini − nilai 5 sesi sebelumnya, dalam poin persen (pp).
- Pita hijau muda (70–100%) dan merah muda (0–30%) hanya penanda area tinggi dan rendah dari desain, bukan sinyal.
- Contoh 13 Nov:
  - EMA50: 162 dari 836 saham di atas → **19,38%** (halaman: 19%);
  - 6 Nov: 86 dari 832 = 10,34% → **+9,0 pp**;
  - EMA200: 152 dari 828 = **18,36%**.
- Contoh satu saham: BBCA 13 Nov penutupan 5.500, EMA50 5.619,57 → **tidak** di atas EMA50.
- Catatan: catatan rencana (EXEC) sempat menulis "862 saham, 166 di atas". Angka itu dihitung tanpa saringan saham
  biasa. Hitungan halaman memakai saham biasa saja.

## 11. Top Movers

- Dari saham universe yang punya return pada periode pilihan (1D/5D/1M, Feature 01):
  - **5 naik terbesar**: return di atas 0, diurutkan dari terbesar;
  - **5 turun terbesar**: return di bawah 0.
- Panjang batang = return ÷ return absolut terbesar di daftar itu.
- Baris bawah = jumlah saham, berapa naik, berapa turun.
- Contoh 13 Nov, LQ45, 1D: WIFI +19,59% teratas; 45 saham, 37 naik, 5 turun.

## 12. Foreign Flow

- **Total pasar** (IHSG, Regular), periode dihitung dalam **tanggal broker** yang berakhir di tanggal broker:

| Periode | Jumlah tanggal broker |
|---|---|
| 1D | 1 |
| 5D | 5 |
| 1M | 20 |
| 3M | 60 |

  - Beli asing = jumlah `foreign_buy_1d`; jual asing = jumlah `foreign_sell_1d`; net = beli − jual.
  - Batang hijau/merah = porsi beli dan jual dari (beli + jual).
- **Daftar saham:** 4 net beli terbesar dan 4 net jual terbesar dari **semua saham**, memakai `foreign_net_1d/5d/20d/60d`
  Feature 06 pada tanggal broker. Saham dengan net 0 tidak masuk.
- Contoh 9 Nov:
  - 1D: beli Rp 3.258,2 M, jual Rp 3.141,6 M, net **+Rp 116,6 M** (beli 50,9%);
  - 5D (3–9 Nov): net **−Rp 295,1 M**;
  - 3M (14 Agu–9 Nov): net **−Rp 30.477,5 M**;
  - BBCA net beli 1D terbesar (+Rp 523,1 M); BMRI net jual 1D terbesar (−Rp 134,5 M).

## 13. Kapan file diperbarui

- Publisher membuat file Overview pada mode `daily`, `backfill` dan mode manual `overview`, **hanya bila "stempel"
  berubah**. Stempel terdiri dari:
  - tanggal harga terakhir, tanggal broker terakhir, tanggal Feature 01 dan Feature 04;
  - jumlah baris Feature 01 pada 20 tanggal pemilih;
  - isi sektor saham dan anggota daftar saham;
  - isi fungsi ukuran kotak;
  - **sidik jari isi** setiap baris input yang bertanggal di **3 tanggal pasar terbaru** (`RECHECK_SESSIONS`): harga
    semua kode, bar IHSG 5 menit dan 1 jam, Feature 01, Feature 04, dan Feature 06 pada tanggal broker yang dipakai
    tanggal-tanggal itu;
  - seluruh deret arus asing pasar (Feature 06 _INDEX, IHSG, Regular);
  - sidik jari `overview.py`.
- **Kenapa 3 tanggal terbaru dicek isinya:** loader harian menulis tanggal terbaru dan bisa terlambat atau bertahap:
  - publisher jalan pada sinyal harga pukul 17:00 WIB, sedangkan bar intraday IHSG baru dimuat 17:30 WIB;
  - Feature 01 dan 04 diisi per saham oleh worker antrean;
  - pemulihan harga pagi menulis ulang tanggal kemarin;
  - ronde broker bisa menulis ulang tanggalnya.

  Dengan sidik jari isi, setiap baris yang datang terlambat atau berubah di jendela itu membuat file yang membacanya
  ditulis ulang. Biaya di dev ±0,6 detik per lari.
- **Feature 04 itu besar** (2,5 GB). Jumlah saham di atas EMA untuk tanggal di luar jendela **dibawa dari publikasi
  sebelumnya** (carry); untuk 3 tanggal terbaru selalu dihitung segar. Hitungan banyak tanggal (lari pertama, mode
  manual) dipecah per 20 tanggal (`BREADTH_CHUNK`) agar setiap kueri jauh di bawah batas waktu login publisher
  (120 detik).
- **File harian ditulis ulang** bila:
  - tanggal brokernya berubah;
  - Feature 04 tanggal itu muncul;
  - **daftar saham berubah** (saham baru atau hilang). File harian menyimpan *posisi* saham di daftar meta, jadi
    semua file harian dibangun ulang bersama meta yang baru;
  - baris arus asing pasar yang dibacanya berubah;
  - input di jendela 3 tanggal yang dibacanya berubah atau baru datang.

  Contoh: sesudah ronde broker, file 10–13 Nov ditulis ulang karena data broker 10 Nov dan seterusnya masuk. Tanggal
  yang keluar dari jendela tidak memicu apa pun.
- **Halaman:** kalau publikasi baru terbit saat halaman terbuka, permintaan file lama dijawab 409. Halaman membaca indeks
  lagi, dan bila meta atau series ikut berganti, memuat keduanya lagi sebelum file hari itu. File dari publikasi yang
  berbeda tidak pernah dicampur.
- Perubahan rumus (`overview.py`) atau fungsi ukuran kotak membuat publisher menghitung **semua** file lagi. Itu
  pembacaan besar (±1,2 GB Feature 04): ikuti aturan restart Postgres sesudahnya (AGENTS.md).
- **Perbaikan data tanggal lama** (di luar 3 tanggal terbaru) tidak terdeteksi stempel. Contoh: backfill atau hitung
  ulang Feature 01/04/06, koreksi harga, atau isi ulang bar intraday lama. Sesudahnya jalankan publisher mode manual
  `overview`: variabel `TERMINAL_PUBLISH_MODE=overview`, Run Now, lalu kembalikan ke `daily` (AGENTS.md, langkah
  sesudah update besar).

---

## Angka yang berlaku

<!-- overview-live:start -->

Ditulis oleh `scripts/overview_formulas_doc.py --write` dari kode di repo; jangan diedit dengan tangan.

| Konstanta publisher (`overview.py`) | Nilai | Arti |
|---|---|---|
| `DAY_DATES` | 20 | tanggal yang bisa dipilih (file harian) |
| `SERIES_SESSIONS` | 300 | sesi pasar di overview-series |
| `VOL_WINDOW` | 20 | jendela volatilitas (hari bursa) |
| `VOL_BASE` | 252 | pembanding persentil volatilitas (nilai sebelumnya) |
| `TURNOVER_BASE` | 20 | rata-rata turnover (tanggal broker sebelumnya) |
| `FOREIGN_SUM` | 10 | net asing KPI "10D" (tanggal broker) |
| `FLOW_PERIODS` | 1D = 1, 5D = 5, 1M = 20, 3M = 60 | periode Foreign Flow (nama, tanggal broker) |
| `INTRADAY_5D` | 5 | sesi grafik IHSG 5D (bar 1 jam) |
| `RECHECK_SESSIONS` | 3 | tanggal pasar terbaru yang isi inputnya dicek setiap lari |
| `BREADTH_CHUNK` | 20 | tanggal per kueri hitungan Feature 04 |
| `BENCHMARK` | LQ45 | indeks pembanding (KPI kedua) |
| `OTHER` | Other | nama sektor untuk "Undefined" |

| Nilai halaman (`model.ts`) | Nilai | Arti |
|---|---|---|
| `PERF_SCALE` | `{ '1D': 1, '5D': 2, '1M': 4 }` | pembagi return sebelum langkah warna |
| `foreignScale` | `120e9 * Math.sqrt(SESSIONS[p])` | pembagi net asing sebelum langkah warna (Rp) |
| `YEAR` | `252` | sesi "1Y" (grafik dan Kinerja Sektor) |
| `SESSIONS` | `{ '1D': 1, '5D': 5, '1M': 20, '3M': 60 }` | sesi per periode |

| Kode | Sumber | Sidik jari (md5) |
|---|---|---|
| `overview.py` | `apps/terminal-publisher/overview.py` (= `CODE` publisher) | `ec4d588d48d5767519cbcf16e808d746` |
| `model.ts` | `apps/edge-bff/overview/src/model.ts` | `f807be497cd316b11d7fad04f98c41f8` |
| `overview_stock_size` | isi fungsi di `database/migrations/20261115_020_overview_stock_size.sql` | `f451fc552b78a6174bc47b4e2a217293` |

<!-- overview-live:end -->
