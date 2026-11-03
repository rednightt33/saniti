# Kamus metodologi discovery: akumulasi dan indikator pre-rally

**Status:** usulan discovery, belum disetujui untuk dibangun, belum diuji daya prediksinya. Dicatat 2026-11-03.

**Keputusan user 2026-11-03 (kata-kata asli):** "ini adalah metodologi discovery, dimana kalau ada yang tanya
accumulation atau indicator pre-rally, then we'll have this disctionary combinations. save ya untuk nanti kita masukan
ke database."

Artinya: setiap entri di bawah adalah satu blok yang dapat dipakai sendiri atau digabung (kombinasi) saat ada pertanyaan
tentang akumulasi atau indikator pre-rally. Dokumen ini adalah sumber untuk tabel kamus di database nanti. Skema tabel
itu belum dirancang; jangan membuat migrasi dari dokumen ini tanpa go dari user (`AGENTS.md`, Plans).

## Prinsip yang berlaku untuk semua entri

1. **Semua ukuran relatif, bukan titik waktu.** Setiap ambang harus menyebut pembandingnya. Ada dua jenis:
   - **A. Riwayat saham itu sendiri** (persentil atau z-score terhadap 252 sesi sebelumnya).
   - **B. Saham lain pada tanggal yang sama** (peringkat lintas saham).
   Persentil dan z-score di `Feature_06` adalah jenis A saja; katalog menyatakan "bukan peringkat lintas saham".
2. **Satu board per perhitungan.** Regular, Nego, dan Tunai tidak dijumlah atau dibandingkan (peringatan
   `Feature_Catalog`). Bawaan: Regular.
3. **"Sesi" adalah sesi saham itu sendiri** (tanggal saham itu punya baris), bukan mundur sekian hari kalender.
4. **Bawaan parameter** mengikuti `apps/market-ai-orc/app/fastlane_defaults.py` bila user tidak menyebut: "besar" =
   persentil 90 riwayat sendiri, "1 minggu" = 5 hari bursa, "1 bulan" = 21, "asing" = investor type Foreign.
5. **Pilihan yang diambil dari kata user menang** atas bawaan; AI boleh bertanya balik.
6. **Ini adalah aliran transaksi, bukan perubahan kepemilikan.** Dan memilih puncak dari ratusan saham pasti menangkap
   sebagian kebetulan: persentil 90 meloloskan sekitar 10% saham hanya karena peluang.
7. **Daya prediksi belum diuji.** Kata "indikator pre-rally" baru boleh dipakai setelah ada uji peristiwa (forward
   return bersyarat) yang disetujui user. Sampai itu, entri hanya menjelaskan *keadaan* data.

Kolom penanda status pada tiap entri: **[T]** terverifikasi di data atau katalog pada 2026-11-03, **[D]** dugaan atau
usulan yang belum diverifikasi.

---

## M-FF-INC — Peningkatan foreign flow (5 sesi)

**Pertanyaan yang dijawab:** saham mana yang aliran net beli asingnya naik dalam 5 sesi terakhir dibanding 5 sesi
sebelumnya?

**Pembanding:** 5 sesi tepat sebelumnya pada saham yang sama (perubahan antar periode, bukan level).

| Langkah | Definisi |
|---|---|
| Ukuran | `foreign_net_turnover_ratio_5d` = 100 × jumlah(F, 5 sesi) ÷ jumlah(T, 5 sesi), F = beli asing − jual asing, T = beli asing + beli domestik. Satuan persen, rentang −100 sampai +100. **[T]** rumus dari katalog, dicocokkan ke data BBCA. |
| Peningkatan | Δ = rasio(sekarang) − rasio(5 sesi lalu), dalam poin persentase. **[D]** |
| Syarat | Δ > 0 **dan** `foreign_net_5d` > 0 (naik dari −10% ke −2% bukan akumulasi). |
| Urutan hasil | Peringkat Δ lintas saham pada tanggal yang sama (jenis B). |
| Papan | Regular. |

- **Mengapa rasio dan bukan Rupiah:** menyamakan ukuran saham. Rp500 miliar net beli itu besar untuk saham kecil dan biasa
  untuk BBCA.
- **Rasio 5 hari bukan rata-rata rasio harian;** ia membobot hari yang ramai lebih besar. Contoh BBCA 27 Okt – 2 Nov
  2026: harian −3,3%, +39,2%, −31,9%, −0,4%, −11,8%; 5 sesi +5,57% (489,4 ÷ 8.783,4 miliar). **[T]**
- **Alternatif pembanding:** laju 20 sesi sendiri (`foreign_net_20d` ÷ 4), atau `foreign_flow_vs_prev_20d` (20 sesi
  lawan 20 sesi sebelumnya, sudah ada di tabel).
- **Keterbatasan:** rasio menyamakan ukuran saham tetapi bukan kebiasaan saham itu. Persentil `base252d` yang ada
  dihitung atas Rupiah, bukan atas rasio. Persentil rasio terhadap riwayat sendiri harus dihitung terpisah (±216 ribu
  baris dari `Feature_06`, murah). **[D]**
- **Sumber:** `Feature_06_Foreign_Domestic` (`foreign_net_5d`, `foreign_net_turnover_ratio_5d`; indeks
  `(trade_date, market_board)`). **[T]**
- **Belum diuji:** apakah Δ > 0 mendahului kenaikan harga.

## M-FF-HEAVY — Akumulasi heavy (net beli asing besar terhadap riwayat sendiri)

**Pertanyaan yang dijawab:** saham mana yang net beli asing 5 sesinya luar biasa besar dibanding kebiasaan saham itu?

**Pembanding:** riwayat saham itu sendiri, 252 sesi sebelumnya (jenis A). Hari ini tidak ikut dihitung. **[T]**

| Syarat | Kolom / rumus | Catatan |
|---|---|---|
| Net beli asing 5 sesi > 0 | `foreign_net_5d > 0` | Net jual besar bukan akumulasi. |
| Besar terhadap riwayat sendiri | `foreign_net_percentile_5d_base252d ≥ 90` (bawaan EDGE), atau `foreign_net_zscore_5d_base252d ≥ 2` | Ambang adalah **keputusan terbuka**. |
| Bukan satu lonjakan | `foreign_buy_days_5d ≥ 3` | **[D]** tambahan AI, bukan bawaan EDGE; menyaring satu transaksi blok. |
| Likuiditas cukup | Buang 20% saham paling tidak likuid pada tanggal itu, berdasarkan median nilai transaksi 60 sesi | **[D]** relatif, bukan batas Rupiah; kolom nilai transaksi di tabel harga belum diverifikasi. |
| Basis alternatif | `base60d` (60 sesi) sebagai uji sensitivitas | |

**Pratinjau ketatnya ambang** (2026-11-02, Regular, 858 saham di `Feature_06`; hitungan, bukan daftar hasil) **[T]**:

| Ambang | Saham lolos |
|---|---:|
| Net beli 5 hari > 0 | 379 |
| + persentil 252 hari ≥ 90 | 75 |
| z-score 252 hari ≥ 2 dan net beli | 18 |
| Punya riwayat cukup untuk basis 252 hari | 842 |

Persentil 90 mengharapkan sekitar 84 saham dari 842 hanya karena peluang, dan yang lolos 75. Jadi P90 menyaring "decile
teratas", bukan "luar biasa". P95 atau z ≥ 2 lebih tepat bila yang dimaksud benar-benar tidak biasa.

- **Peringatan katalog:** jendela yang tumpang tindih membuat nilai hari berurutan tidak independen; jangan dibaca
  sebagai bukti statistik. Baris `source_balance_gap = true` dari 2016 sampai Agustus 2020 berasal dari sumber yang
  kurang beberapa broker (ERRORS M157); net asing dan domestiknya tidak berjumlah nol.
- **Sumber:** `Feature_06_Foreign_Domestic`. **[T]**
- **Belum diuji:** apakah akumulasi heavy mendahului kenaikan harga.

## M-TOPN-RATIO — Rasio top N pembeli dibagi top N penjual

**Pertanyaan yang dijawab:** apakah beli dikuasai segelintir broker sementara jual tersebar (timpang), atau sebaliknya?
Ini mengukur **konsentrasi**, bukan arah total: untuk semua investor, jumlah net semua broker pasti nol (84 broker BBCA
5 sesi: 0,000). **[T]**

**Definisi:** B = jumlah net N pembeli net terbesar; S = jumlah |net| N penjual net terbesar. N adalah parameter
(bawaan usulan: 3).

| Ukuran | Rumus | Catatan |
|---|---|---|
| Rasio | B ÷ S | Meledak bila S kecil. |
| Imbalance (pendamping, usulan AI) | (B − S) ÷ (B + S) | Terbatas −1 sampai +1. **[D]** |

- **Agregasi:** untuk jendela 5 sesi, jumlahkan net **per broker lebih dulu** selama 5 sesi, baru pilih N terbesar.
  Menjumlah top N harian salah, karena brokernya bisa berbeda tiap hari. **[T]** (dihitung begitu pada contoh).
- **Pembanding:** (a) persentil imbalance atau rasio terhadap 252 sesi sebelumnya saham itu, karena saham berfloat tipis
  bisa selalu timpang; (b) peringkat lintas saham pada tanggal yang sama. **[D]**
- **Cakupan (keputusan terbuka):** semua investor (konsentrasi murni) atau hanya asing (`investor_type = 'Foreign'`,
  mencampur konsentrasi dan arah). Kode broker bukan identitas investor.
- **Contoh BBCA 27 Okt – 2 Nov 2026, Regular, dari `IDX_Broker_Summary`** **[T]**:

  | Cakupan | Top 3 beli (Rp miliar) | Top 3 jual (Rp miliar) | B/S | Imbalance |
  |---|---:|---:|---:|---:|
  | Semua investor | 1.149,0 (BK, ZP, YU) | 1.008,8 (CC, KZ, AK) | 1,14 | 0,07 |
  | Hanya asing | 1.228,2 (BK, ZP, YU) | 727,7 (CC, KZ, RX) | 1,69 | 0,26 |

  Jumlah net asing 489,4 miliar sama dengan `foreign_net_5d` di `Feature_06`.
- **Sumber:** `Feature_02_Broker_Rolling.net_value_5d` (net per broker, investor type, dan board selama 5 sesi). **[T]**
  `Feature_03_Stock_Broker_Daily` hanya punya `top3_buyer_net_value` dan `top3_buyer_share` untuk **1 hari**, serta
  penjual hanya top 1 (`top_seller_net_value`); **tidak ada top 3 penjual**, jadi sisi jual harus dihitung. **[T]**
- **Biaya:** `Feature_02` ±15 GB. Satu saham satu tahun memakai indeks primary key (EXPLAIN 2026-11-03). Lintas ±858
  saham × 252 tanggal belum diukur dan berarti puluhan juta baris: jalankan `EXPLAIN`, sebut perkiraan ukuran, dan minta
  izin sebelum memulai (cache memori Postgres ikut ditagih; `AGENTS.md`, Postgres memory). **[D]**
- **Belum diuji:** apakah rasio timpang mendahului kenaikan harga.

---

## Kombinasi (kerangka, belum diputuskan)

| Pertanyaan user | Kombinasi usulan | Status |
|---|---|---|
| "Saham yang foreign flow-nya naik 5 hari" | M-FF-INC | Usulan |
| "Saham dengan akumulasi heavy" | M-FF-HEAVY, atau M-FF-HEAVY **dan** M-TOPN-RATIO | Terbuka: satu daftar atau dua |
| "Indikator pre-rally" | Menunggu uji peristiwa | Belum ada |

## Kandidat entri dari riset 2026-11-03 (belum diminta masuk kamus)

Riset atas "bagaimana HHI" dan "share top 3 net/gross buyer naik atau turun". Dicatat agar tidak hilang; user yang
memutuskan masuk kamus atau tidak.

**M-HHI — `Feature_03_Stock_Broker_Daily.broker_concentration_hhi`.** Jumlah kuadrat bobot |net| per broker (kedua
Investor Type dijumlah per broker lebih dulu); `CALCULATION_VERIFIED`. **[T]**
- **Buta arah:** bobot memakai nilai absolut, pembeli dan penjual dicampur. HHI tinggi tidak membedakan akumulasi dari
  distribusi.
- **Sebagian besar redundan dengan `top3_buyer_share`:** korelasi level lintas saham 0,80 (872 saham Regular dengan ≥ 35
  sesi, data harian 15 Jul – 2 Nov 2026). **[T]**
- **Lantai mekanis:** HHI minimum = 1/N broker aktif. HHI ternormalisasi `(H − 1/N) ÷ (1 − 1/N)` searah dengan HHI mentah
  pada 92% saham (perubahan vs 5 sesi sebelumnya), jadi normalisasi jarang mengubah kesimpulan. **[T]**

**M-TOP3-SHARE-TREND — share top 3 net buyer naik atau turun.** Net: `top3_buyer_share` = top 3 net ÷ jumlah semua net
positif, 1 hari, `Feature_03`. **Gross** (top 3 berdasarkan nilai beli ÷ total nilai beli) **tidak ada di
`Feature_03`**; harus dihitung dari `Feature_02.buy_value_1d`. **[T]**
- **Lantai mekanis:** pada 22,8% baris saham-hari ada ≤ 3 broker net beli, sehingga share = 100% tanpa arti. Median 10
  broker net beli dan 20 broker aktif. Pembanding netral: 3 ÷ jumlah broker net beli (share merata). Arah perubahan
  share mentah dan share-di-atas-merata sama hanya pada 71% saham. **[T]**
- **Bukan pemilah:** vs 5 sesi sebelumnya, share top 3 net naik pada 480 saham dan turun pada 375 (median +0,0096);
  vs 30 sesi sebelumnya naik 535, turun 326. Menandai "naik" saja meloloskan 55–62% saham. Perlu ambang relatif
  terhadap variasi saham itu sendiri atau peringkat lintas saham. **[T]**
- **Variasi mingguan besar:** BBCA, net_top3 rolling 5 sesi di sejarah 252 sesi berkisar 0,30 – 1,00 (median 0,60); loncatan
  mingguan ±0,15 – 0,32 biasa. Perubahan harus dibaca terhadap variasi sendiri. **[T]**
- **Gross dan net bisa berlawanan:** ANTM 2 Nov 2026: share top 3 gross 0,519 = maksimum 252 sesi (persentil 99,6) sementara
  share top 3 net datar (−0,019 vs 5 sesi lalu). Gross mengukur konsentrasi aktivitas, bukan akumulasi. Korelasi perubahan
  5 sesi gross vs net: BBCA 0,72; BBRI 0,70; ANTM 0,45. **[T]** (3 saham saja).
- **Cara yang konsisten dengan M-TOPN-RATIO:** hitung per broker 5 sesi dulu, baru ambil top N. Pada ringkasan lintas saham
  `Feature_03` memakai rata-rata share harian, bukan share dari net kumulatif 5 sesi; keduanya tidak sama.
- **Cakupan data:** `Feature_03` berisi 1.593 ticker Regular dalam jendela itu karena menyertakan instrumen di luar
  universe saham (katalog), sedangkan `Feature_06` memuat 858. Pilih universe saham sebelum screening. **[T]** (katalog) /
  **[D]** (sebab selisih).
- **Riwayat panjang:** total beli ≠ total jual di sumber 2016–2020 (ERRORS M157; `FUTURE_PLAN.md`, bagian 0). Analisis
  tren panjang harus mulai 2021 atau menandai baris itu.
