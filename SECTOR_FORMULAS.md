# Rumus Sector Analysis (dev)

<!-- explained-for: sector.py=bb59669314930aa147da892b70c60077, refresh_feature_08_day=04c532e911d08570d5a4e49a4ce26510, feature_08_weight=25282caa1c9ce32ee23d0346ffd38a2e -->

Dokumen ini menjelaskan **setiap angka halaman Sector Analysis** (tab "Sector Analysis" di EDGE) dengan bahasa
sederhana dan contoh angka asli dev. Pakai dokumen ini saat ingin mengubah rumus, atau saat bertanya dari mana sebuah
angka datang. Keputusan user yang membentuk rumusnya ada di `EXEC.md` EXEC-SECTOR-ANALYSIS (UD66 A-J, UD67 "1A 2A 3
go", 26 Nov 2026); kontrak antarbagian di `verification/sector_analysis/CONTRACT.md`.

- **Sumber kebenaran:**
  - Fungsi database `public.refresh_feature_08_day(date)` (migrasi `20261126_001`): angka per kelompok per tanggal di
    tabel `Feature_08_Group_Daily` (anggota, breadth EMA, naik/tetap/turun, return tertimbang, indeks industri).
  - Fungsi database `public.feature_08_weight(date)`: **satu-satunya** sumber bobot (keputusan D1). Hari ini sama dengan
    ukuran kotak Overview: rata-rata nilai transaksi 20 sesi (`adv20_value`). Nanti bisa diganti market cap tanpa
    mengubah halaman.
  - `apps/terminal-publisher/sector.py`: membaca Postgres dan menulis file `sector/*.json.gz` di storage.
  - Halaman (`apps/edge-bff/sector`, bagian S4): menghitung yang bergantung pada pilihan pengguna (periode, urutan,
    peta rotasi, pasangan, korelasi, beta) dari file-file itu. Halaman tidak pernah membaca database.
- **Angka yang berlaku** (jendela, periode, sidik jari kode) ada di bagian paling bawah, ditulis otomatis dari kode.
- **Contoh** memakai data asli dev: tanggal halaman **Rabu 25 Nov 2026**, sesi sebelumnya Selasa 24 Nov 2026, 300 sesi
  seri sejak 1 Sep 2025. Rupiah ditulis dalam miliar (Rp M) atau triliun (Rp T). Angka grup (bagian 2-5) dihitung oleh
  SELECT dari fungsi refresh itu sendiri, dijalankan read-only di dev sebelum migrasi diterapkan
  (`verification/sector_analysis/db/crosscheck_dev_20261126.txt`, 0 beda dengan hitungan ulang independen).

## Cara dokumen ini dijaga tetap benar

1. **Setiap push ke GitHub:** tes `scripts/tests/test_sector_formulas_doc.py` menjalankan
   `scripts/sector_formulas_doc.py --repo`. Tes merah bila konstanta atau sidik jari di bagian bawah tidak sama dengan
   kode, atau penjelasan di atas ditulis untuk versi kode yang lain (baris `explained-for`).
2. **Setelah migrasi diterapkan di dev:** `--check` juga membandingkan kedua fungsi di database dev dengan isi migrasinya
   (masuk ke workflow harian `database-schema-docs.yml` setelah migrasi diterapkan; sebelum itu fungsinya belum ada di
   dev).
3. **Aturan kerja (AGENTS.md):** setiap perubahan rumus Sector Analysis memperbarui dokumen ini di commit yang sama:
   jalankan `python3 scripts/sector_formulas_doc.py --write`, perbarui penjelasan, samakan baris `explained-for`.

"Sidik jari" = md5 dari isi kode. Sidik jari `sector.py` juga dipakai publisher sebagai `CODE`: kalau berubah, publisher
menulis ulang semua file harian Sector Analysis, dan menulisnya sebagai elemen terakhir `sector_stamp` di `state.json`.

---

## Gambaran: dari mana angka datang

```
Postgres (harga harian final, Feature 04, daftar saham)
  ─► refresh_feature_08_day (dipanggil feature-04-worker setelah Feature 04 tanggal itu selesai)
  ─► Feature_08_Group_Daily (per tanggal: pasar, 11 sektor, 58 industri)
  ─► publisher (sector.py) ─► sector-meta, sector-series, sector-day-<tanggal>, sector-stocks-<indeks>
  ─► halaman (menghitung periode, peringkat, rotasi, pasangan, beta dari file)
```

| File | Isinya | Kapan diunduh |
|---|---|---|
| `sector-meta` | pasar (IHSG), pembanding (IHSG, LQ45), basis bobot dan labelnya, periode, 11 sektor (nama, nama pendek, kode indeks), industri dengan sektornya, semua saham biasa (nama, sektor, industri), 20 tanggal pilihan | saat halaman dibuka |
| `sector-series` | 300 sesi: penutupan IHSG, LQ45 dan 11 indeks sektor; breadth per kelompok (IHSG dan tiap sektor); level dan jumlah anggota tiap industri | saat halaman dibuka |
| `sector-day-<tanggal>` | satu tanggal: semua saham yang punya penutupan final hari itu (penutupan, volume, return, bobot, posisi terhadap EMA, lama status) | tanggal yang dipilih |
| `sector-stocks-<indeks>` | satu sektor: penutupan harian setiap sahamnya selama 300 sesi (nama file memakai kode indeks huruf kecil, misalnya `sector-stocks-idxfinance`) | hanya saat garis saham atau beta saham sektor itu dibuka |

---

## 1. Tanggal dan periode

- **Sesi** = satu tanggal pasar: tanggal dengan penutupan harian final IHSG (entitas `MARKET` di `Feature_Index_Entity`).
- **20 tanggal pilihan** (keputusan I) sama persis dengan Overview: 20 tanggal pasar terbaru yang punya baris Feature 01.
- **Periode** (keputusan E, sama dengan Overview): 1D = 1 sesi, 3D = 3, 1W = 5, 2W = 10, 1M = 20, 3M = 60, 6M = 120,
  1Y = 252. "4W/8W/12W" = 20/40/60 sesi; langkah mingguan = 5 sesi.
- **YTD**: dari penutupan sesi terakhir tahun sebelumnya. Contoh: untuk 25 Nov 2026 dasarnya **30 Des 2025**.
- **Custom**: sama dengan Overview (`OVERVIEW_FORMULAS.md` bagian 12b): dasar return = sesi sebelum sesi pertama rentang,
  rentang paling panjang 365 hari.
- **Return sebuah indeks atau saham selama n sesi** = (penutupan hari ini / penutupan n sesi sebelumnya − 1) × 100.
  Contoh IHSG 25 Nov 2026: 5.197,61 / 5.241,59 − 1 = **−0,84%** (1D); 1W −0,96%; 1M −1,60%; 3M −21,20%; YTD −39,89%;
  1Y −37,66%.
- Pembanding semua kartu adalah IHSG; Beta & Correlation boleh memakai LQ45 (keputusan A1).

## 2. Kelompok dan anggotanya (`Feature_08_Group_Daily`)

Satu baris per tanggal pasar per kelompok:

| Kelompok | Nama di tabel | Anggota |
|---|---|---|
| `MARKET` | kode pasar (`IHSG`) | semua saham biasa (`Security Type` = stock), sektor "Undefined" ikut |
| `SECTOR` | nama sektor IDX (misalnya `Financials`) | saham dengan `IDX_Stock_Universe."Sector"` itu (11 sektor dari `Feature_Index_Entity`) |
| `INDUSTRY` | nama industri IDX-IC (misalnya `Banks`) | saham dengan `"Industry"` itu, kecuali "Undefined"; sektornya = sektor kebanyakan sahamnya |

- **members** = anggota yang punya penutupan harian final pada tanggal itu. Contoh 25 Nov 2026: pasar **837**,
  Financials **98**, Banks **46**.
- **Keanggotaan memakai klasifikasi hari ini** (sama dengan Overview dan Feature 01): saham yang pindah sektor dihitung di
  sektor barunya untuk semua tanggal lama. Riwayat berbasis keanggotaan sekarang punya bias survivorship.
- Kelompok tetap punya baris walau tidak ada anggota yang bertransaksi (members 0).

## 3. Bobot (satu basis, bisa diganti)

- `feature_08_weight(tanggal)` = rata-rata nilai transaksi 20 sesi pasar terakhir: Σ(penutupan × volume) ÷ 20 (hari
  tanpa transaksi dihitung 0). **Ini ukuran likuiditas, bukan market cap.** Label di file: "20-day average traded
  value" (`weight_basis` = `adv20_value`).
- Semua bobot halaman memakai basis ini: indeks industri, luas kotak peta, "top-N terbesar", ukuran titik.
- **weight_sum** = jumlah bobot anggota pada tanggal itu. Contoh 25 Nov 2026: pasar Rp 9,39 T per hari, Financials
  Rp 2,80 T, Banks Rp 2,74 T (97,7% dari Financials). BBCA sendiri Rp 1,10 T per hari.
- Ganti ke market cap nanti = versi baru fungsi ini (nama basis baru), lalu hitung ulang semua tanggal (job backfill).
  Halaman membaca labelnya dari file, jadi halaman tidak berubah.

## 4. Breadth: saham di atas EMA50 dan EMA200

- **n_ema50** = anggota yang punya baris Feature 04 (Daily) dengan `ema_50` terisi; **above_ema50** = dari mereka, yang
  `close > ema_50` (close milik Feature 04). Sama untuk EMA200. Close yang sama persis dengan EMA dihitung **tidak** di
  atas.
- **% di atas EMA50** = above_ema50 / n_ema50 × 100. Contoh 25 Nov 2026: pasar 133 / 837 = **15,9%**; EMA200 132 / 829
  = 15,9%; Financials 22 / 98 = 22,4% (EMA200 14 / 98 = 14,3%); Banks 12 / 46 = 26,1%.
- Baris pasar **sama persis** dengan breadth Overview (`BREADTH_SQL`): dev 25 Nov 2026 Overview 837 / 133 / 829 / 132.
- Tidak ada EMA20 (keputusan C1: Feature 04 tidak punya EMA20). Saham baru yang belum punya EMA tidak masuk penyebut.

## 5. Naik, tetap, turun (A/U/D)

- Setiap anggota dibandingkan dengan **penutupan finalnya sendiri sebelumnya** (setelah suspensi, itu bisa beberapa
  hari pasar yang lalu). Saham baru tanpa penutupan sebelumnya tidak masuk ketiganya.
- Contoh 25 Nov 2026: pasar **197 naik, 187 tetap, 453 turun**; Financials 24 / 31 / 43; Banks 12 / 10 / 24.
- Halaman menghitung A/U/D untuk 1W dan 1M sendiri dari return di file harian (bagian 7).

## 6. Return tertimbang harian dan indeks industri

- **ret_1d_w** = 100 × Σ w(kemarin) × (penutupan hari ini / penutupan sebelumnya − 1) ÷ Σ w(kemarin), atas anggota yang
  punya kedua penutupan dan bobot pada sesi pasar sebelumnya. Bobot **kemarin** dipakai supaya transaksi hari itu sendiri
  tidak ikut menimbang return hari itu.
- Contoh 25 Nov 2026: pasar **−1,593%**, Financials −0,162%, Banks −0,129%. Ini **berbeda dari indeks resmi IDX**
  (IDXFINANCE −0,31% hari itu) karena IDX menimbang dengan kapitalisasi free float, kita dengan nilai transaksi.
- **index_level** (indeks buatan EDGE untuk industri; industri tidak punya indeks resmi): 100 pada tanggal pertama
  kelompok, lalu level(t) = level terakhir × (1 + ret_1d_w / 100). Contoh hitungan: bila level Banks kemarin 100,
  hari ini 100 × (1 − 0,00129) = 99,871. Hari tanpa return (tidak ada anggota dengan dua penutupan dan bobot) levelnya
  kosong dan level terakhir dipakai lagi besoknya.
- Riwayat dimulai **25 Jan 2021** (tanggal pertama indeks sektor IDX) lewat job backfill; sebelum backfill selesai
  publisher tidak menerbitkan file (tidak pernah setengah terisi).
- Return sebuah industri untuk periode = level(akhir) / level(awal) − 1. Industri dengan 1 anggota (misalnya Consumer
  Electronics) returnnya = return satu saham itu.

## 7. File harian: angka per saham (`sector-day-<tanggal>`)

Setiap saham biasa dengan penutupan final pada tanggal itu, urut sesuai `meta.stocks` (kolom `i`). Contoh **BBCA, 25 Nov
2026**:

| Kolom | Rumus | BBCA |
|---|---|---|
| `close`, `volume` | penutupan dan volume harian final | 5.825; 164.649.600 lembar |
| `r1d`, `r5d`, `r1m`, `r3m` | (penutupan / penutupan 1, 5, 20, 60 sesi pasar sebelumnya − 1) × 100; kosong bila salah satu tidak ada | +0,43% (vs 5.800); +1,30% (vs 5.750); +10,43% (vs 5.275); −12,73% (vs 6.675) |
| `weight` | `feature_08_weight` tanggal itu | Rp 1,10 T per hari |
| `above_ema50`, `above_ema200` | 1 bila close Feature 04 > EMA, 0 bila tidak, kosong tanpa EMA | 1 (5.825 > 5.634,95); 0 (5.825 < 6.343,67) |
| `d_ema50`, `d_ema200` | (close / EMA − 1) × 100 | +3,37%; −8,18% |
| `days50`, `days200` | berapa sesi (baris Feature 04 saham itu sendiri) berturut-turut sampai hari ini statusnya sama, paling banyak 300 ("300+") | 3; 251 |
| `since50`, `since200` | sesi pertama status itu; kosong bila sudah 300+ | 23 Nov 2026; 10 Nov 2025 |

- Catatan: return di file ini dihitung dari penutupan per **sesi pasar** (seperti grafik Overview), bukan
  `return_20d_pct` Feature 01 (yang menghitung observasi saham itu sendiri). Saham yang disuspensi di sesi dasar
  returnnya kosong.
- Lama status dihitung sekali dari riwayat Feature 04, lalu setiap hari cukup +1 dari file kemarin (atau mulai lagi dari
  1 bila statusnya berubah).

## 8. Kartu halaman (dihitung halaman dari file)

Nama netral (keputusan A, UD67 2A): "Rotation map", sumbu "Relative strength" dan "Momentum". Kartu tersembunyi di
prototipe dihapus (keputusan H). Rumus kartu mengikuti audit prototipe final (`verification/sector_analysis/final/
formulas.md`), dengan periode keputusan E. "pp" = poin persentase (selisih dua persen).

### 8.1 Tab Overview
- **Baris KPI:** IHSG 5D (5.197,61; −50,27 poin; −0,96%); "Beating IHSG 5D" = jumlah sektor dengan return 5D − IHSG 5D
  > 0: **4 / 11** (Financials +0,95 pp, Transportation & Logistic +0,90, Healthcare +0,70, Industrials +0,51);
  "Strongest sector 5D" = **Financials +0,95 pp**; "Improving" = jumlah sektor di kuadran Improving peta rotasi.
- **Cumulative Return:** garis (penutupan / penutupan dasar − 1) × 100 sejak dasar periode (1M, 3M bawaan, YTD,
  Custom); daftar kanan = return periode, urut dari terbesar. Contoh 1M Financials +2,53%, IHSG −1,60%.
- **Momentum (horizon vs horizon):** titik sektor dengan x = return satu horizon, y = horizon lain (bawaan x = 3M,
  y = 1M). Financials: x −10,87%, y +2,53% ("Turning up": x < 0, y ≥ 0).
- **Sector × Horizon:** tabel return 1D, 1W, 1M, 3M, 6M, YTD, 1Y. Financials: −0,31 / −0,00 / +2,53 / −10,87 / +4,56 /
  −19,07 / −14,58%.
- **Market map:** kotak per industri, luas = Σ bobot (bagian 3), isinya 10 saham terbesar per bobot, warna = return 5D
  saham − IHSG 5D (pp). Label industri = rata-rata tertimbang bobot dari selisih itu.

### 8.2 Tab Relative Strength
- **Relative Return:** return sektor n sesi (3, 5 bawaan, 10) − return IHSG n sesi. 5D: Financials **+0,95 pp**
  (tertinggi), Technology −2,27 pp (terendah).
- **Rank change:** peringkat 1-11 menurut selisih itu, pada tanggal pembanding (5, 10, 20 sesi lalu, atau Custom) dan
  hari ini; garis hijau bila naik ≥ 3 peringkat, merah bila turun ≥ 3.
- **Weekly excess heatmap:** sel = selisih 5 sesi per blok 5 sesi yang tidak tumpang tindih, mundur dari tanggal halaman
  (4 atau 8 minggu); urut bawaan menurut selisih 20 sesi.
- **Sector drill-down:** per sektor return 3D, 1W, 1M, 3M, YTD; vs IHSG 1M dan 3M; **RS rating** 1-99 = urutan selisih
  1M di antara 11 sektor (1 + 98 × (N − 1 − k) / (N − 1), k = posisi dari atas): Financials **99** (+4,13 pp), Basic
  Materials 1 (−13,81 pp); Δ 4W = rating hari ini − rating 20 sesi lalu; % di atas EMA50 (bagian 4); kuadran rotasi;
  **Momentum** g = selisih 5D − selisih 1M × 5/20: Financials 0,95 − 4,13 × 5/20 = **−0,08** → "Steady" (Gaining bila
  > +0,5, Fading bila < −0,5). Baris industri memakai level industri (bagian 6) untuk 3M, YTD, Δ 4W dan kuadran.
- **Sector stocks:** garis kumulatif 10 saham terbesar per bobot dari `sector-stocks-<indeks>` (penutupan asli, bukan
  garis buatan).

### 8.3 Tab Rotation
- **Rotation map** (rumus milik kita sendiri, bukan JdK): r = penutupan sektor / penutupan IHSG; **Relative strength**
  = 100 × r / rata-rata 20 sesi r; **Momentum** = 100 × Relative strength hari ini / Relative strength 5 sesi lalu.
  Kuadran: keduanya ≥ 100 Leading; strength ≥ 100 dan momentum < 100 Weakening; strength < 100 dan momentum ≥ 100
  Improving; selain itu Lagging. Contoh Financials: r = 0,24135, rata-rata 20 sesi 0,23809, Relative strength
  **101,37**, 5 sesi lalu 101,61, Momentum **99,76** → **Weakening**. Ekor = titik mingguan (4, 8, 12 minggu).
- **Direction & speed:** perubahan (Δ strength, Δ momentum) selama 1, 2 atau 4 minggu; arah = sudut atan2, kecepatan =
  panjang vektornya.
- **Rotation detail:** kuadran sekarang dan 5/10/20 sesi lalu; kecepatan = jarak yang ditempuh dalam 5 sesi; perubahan
  kuadran terakhir pada seri harian.
- **Stock momentum quadrant:** titik saham sektor terpilih, x = r1m saham − return 20 sesi pembanding, y = r5d saham −
  return 5 sesi pembanding; ukuran titik = bobot.

### 8.4 Tab Pair Matrix
- **Pair matrix:** sel = return sektor baris − sektor kolom selama periode (spread), atau korelasi Pearson return harian
  (20, 60, 120 sesi). Contoh Financials − Energy 1M: 2,53 − (−7,59) = **+10,12 pp**; korelasi 60 sesi **0,78**.
- **Pair ratio:** rasio Q = penutupan A / penutupan B, rata-rata MA (20, 50) dan pita ± 2 simpangan baku (populasi), z =
  (Q − rata-rata) / simpangan. Financials / Energy dengan MA50: Q 0,5372, rata-rata 0,4672, simpangan 0,0438, **z
  +1,60** (di dalam pita).
- **Beta & Correlation** ke IHSG atau LQ45, W sesi (20, 60, 120 bawaan, 252): β = kovarians / varians return harian,
  korelasi Pearson, alpha = return sektor − β × return pembanding. Financials 120 sesi vs IHSG: **β 0,75**, korelasi
  **0,93**, return +4,56% vs IHSG −7,10%, alpha +4,56 − 0,75 × (−7,10) = **+9,86 pp**. Beta saham dihitung sama dari
  `sector-stocks-<indeks>`.
- **Stretched pairs:** 55 pasangan diurutkan menurut |spread| H sesi (3, 5, 20).

### 8.5 Tab Breadth
- **Breadth vs Price:** garis % di atas EMA50 (atau EMA200) per tanggal dari `sector-series.breadth` (pasar atau satu
  sektor; nilai asli Feature 04 per sektor, bukan garis buatan), dengan IHSG di sumbu kanan; Δ = selisih dengan 5 sesi
  lalu.
- **Breadth heatmap table:** per sektor % saham naik 1D/1W/1M (dari `r1d`, `r5d`, `r1m` hari itu), % di atas EMA50 dan
  EMA200, Δ EMA50 1W dari riwayat breadth sektor.
- **Breadth by sector:** % di atas EMA50, % dengan r5d > IHSG 5D, atau % dengan r5d > 0, per sektor.
- **Advancers · Unchanged · Decliners:** jumlah saham naik/tetap/turun per sektor untuk 1D, 1W, 1M dari return harian;
  rincian memakai `close` dan `volume` asli.
- **Stock detail:** per saham status di atas/bawah EMA, jaraknya (`d_ema50`, `d_ema200`), lama status dan sejak kapan
  (bagian 7).

## 9. Kapan file diperbarui

- `feature-04-worker` menyelesaikan run Feature 04 harian (sekitar 17:05 WIB), lalu menghitung ulang Feature 08 untuk 5
  sesi terakhir (jendela koreksi Feature 04) sampai tanggal terbaru, satu tanggal per perintah, berurutan.
- Publisher berjalan dengan pemicu yang sama dengan Overview (sinyal loader dan lari pengaman 07:30 WIB). File harian
  dibangun ulang hanya bila inputnya berubah: tanggal baru, atau baris harga/Feature 04 di 3 tanggal terbaru berubah.
  Seri dan file per sektor ditulis ulang bila isinya berubah.
- Mode manual `sector` (Run Now dengan `TERMINAL_PUBLISH_MODE=sector`) membangun semua dari database lagi: bacaan besar,
  jadi Postgres di-restart sesudahnya (AGENTS.md).

## Angka yang berlaku

<!-- sector-live:start -->

Ditulis oleh `scripts/sector_formulas_doc.py --write` dari kode di repo; jangan diedit dengan tangan.

| Konstanta publisher (`sector.py`) | Nilai | Arti |
|---|---|---|
| `DAY_DATES` | 20 | tanggal yang bisa dipilih (file sector-day), sama dengan Overview |
| `SERIES_SESSIONS` | 300 | sesi pasar di sector-series dan sector-stocks, sama dengan Overview |
| `RECHECK_SESSIONS` | 3 | tanggal pasar terbaru yang isi inputnya dicek setiap lari |
| `STATUS_CAP` | 300 | batas hitungan lama status terhadap EMA (ditampilkan "300+") |
| `HISTORY_TICKERS` | 50 | saham per kueri hitung mundur Feature 04 |
| `READ_THREADS` | 4 | file publikasi sebelumnya yang dibaca bersamaan |
| `PERIODS` | 1D = 1, 3D = 3, 1W = 5, 2W = 10, 1M = 20, 3M = 60, 6M = 120, 1Y = 252 | sesi per periode (keputusan E, sama dengan Overview) |
| `RETURNS` | r1d = 1, r5d = 5, r1m = 20, r3m = 60 | return saham di file sector-day (nama, sesi pasar) |
| `BENCHMARK` | LQ45 | indeks pembanding kedua (Beta & Correlation) |
| `OTHER` | Other | nama sektor untuk "Undefined" |
| `BASIS_LABELS` | adv20_value = 20-day average traded value, market_cap = market capitalisation | label basis bobot yang ditulis di sector-meta |
| `SHORT` | Basic Materials = Basic Mat., Consumer Cyclicals = Cons. Cyc, Consumer Non-Cyclicals = Non-Cyc, Infrastructures = Infra, Properties & Real Estate = Property, Transportation & Logistic = Transport, Healthcare = Health, Technology = Tech | nama pendek sektor (sama dengan halaman Overview) |
| `BACKFILL_LOCK` | feature_08_group_backfill | kunci advisory pengisian riwayat Feature 08 |

| Kode | Sumber | Sidik jari (md5) |
|---|---|---|
| `sector.py` | `apps/terminal-publisher/sector.py` (= `CODE` publisher) | `bb59669314930aa147da892b70c60077` |
| `refresh_feature_08_day` | isi fungsi di `database/migrations/20261126_001_feature_08_group_daily.sql` | `04c532e911d08570d5a4e49a4ce26510` |
| `feature_08_weight` | isi fungsi di `database/migrations/20261126_001_feature_08_group_daily.sql` | `25282caa1c9ce32ee23d0346ffd38a2e` |

<!-- sector-live:end -->
