# Library screener: filter yang memunculkan aset kandidat

**Status:** rancangan, belum diputuskan parameternya, belum dibangun sebagai fitur. Dicatat 2026-11-04. Dipublikasikan ke `main` 2026-11-10 atas permintaan user ("Goal: ini akan jadi screener library untuk dipost di FE. Langsung push saja ke main"); integrasi ke FE belum dikerjakan. Hitungan detail S1 sampai S3 ada di bagian 9.

**Tujuan (user 2026-11-04):** "Goalnya adalah bukan database testing. Ini membuat library of screener, agar potential
asset can appear when we applied these filters." Dan: "Tambahkan dulu ke repo."

Library ini adalah daftar screener (kombinasi filter) yang disusun dari blok di
[`METHODOLOGY_DICTIONARY.md`](METHODOLOGY_DICTIONARY.md). Hasil sebuah screener adalah **kandidat untuk ditelaah**, bukan
sinyal beli atau jual. Daya prediksi tidak diuji di sini; peringatan baca ada di tiap kartu.

## 1. Bagaimana sebuah screener disusun

Setiap kartu screener berisi:

| Bagian | Isi |
|---|---|
| Pertanyaan | Aset seperti apa yang ingin dimunculkan |
| Blok | Filter dari kamus (id `M-...`) |
| Tingkat parameter | **Longgar**, **Standar**, **Ketat**: ambang persentil atau z-score tiap blok |
| Gerbang | Aturan yang berlaku sebelum filter (data segar, universe, likuiditas, jumlah broker) |
| Peringkat | Cara mengurutkan kandidat |
| Kolom hasil | Nilai dan persentil tiap blok, tanggal data |
| Peringatan baca | Apa yang tidak dikatakan hasilnya |

Prinsip dari kamus yang berlaku: semua ambang relatif (terhadap riwayat saham itu sendiri atau terhadap saham lain pada
tanggal yang sama), satu board per perhitungan (Regular), "sesi" adalah sesi saham itu sendiri (5 sesi terakhir tiap saham),
dan angka KSEI berharga perkiraan.

## 2. Gerbang global

| Gerbang | Aturan | Status |
|---|---|---|
| G1 Kesegaran | Semua sumber di tanggal yang sama (as-of); bila ada yang tertinggal, screener menyebutnya | Usulan |
| G2 Universe | Saham yang ada di `Feature_06` dan punya ≥ 5 sesi Regular di 16 tanggal bursa terakhir | Usulan |
| G3 Likuiditas (materialitas) | Total beli bruto 5 sesi tiap saham, dibuang menurut persentil. **"Luas":** buang 50% terbawah. **"Likuid":** buang 80% terbawah | **Ukuran diputuskan 2026-11-10 (bagian 6 nomor 10); tingkat bawaan belum diputuskan** |
| G4 Jumlah broker | Untuk blok konsentrasi: minimal 10 broker net beli | Pilihan AI, belum diputuskan |
| G5 Materialitas asing | Rasio net asing minimum agar blok asing tidak meloloskan net yang sangat kecil | **Terbuka** (lihat bagian 6) |

Batas Rp pada 3 Nov 2026 (total beli bruto 5 sesi): buang 20% = Rp0,3 miliar, 50% = Rp2,3 miliar, 70% = Rp8,7 miliar,
80% = Rp25,6 miliar. Batasnya relatif sehingga berubah tiap hari.

## 3. Kartu screener

### S1 — Akumulasi asing heavy
- **Pertanyaan:** saham mana yang net beli asing 5 sesinya luar biasa besar terhadap riwayat saham itu sendiri?
- **Blok:** `M-FF-HEAVY` (net asing 5 sesi > 0; persentil 252 sesi; net beli di ≥ 3 dari 5 sesi).
- **Parameter:** Longgar: persentil ≥ 90. Standar: persentil ≥ 95. Ketat: persentil ≥ 95 dan z-score ≥ 2.
- **Pembanding persentil:** riwayat saham itu sendiri, 252 sesi sebelum hari ini (jenis A). Hitungan: bagian 9.3.
- **Peringkat:** z-score 252 sesi, menurun.
- **Kolom:** beli bruto 5 sesi, net asing 5 sesi, persentil dan z-score, jumlah hari net beli, rasio net asing.
- **Peringatan:** persentil terhadap riwayat sendiri tidak memandang ukuran. Tanpa G3 dan G5, saham mikro dengan net
  asing Rp0,3 miliar ikut lolos (contoh NATO).

### S2 — Arus asing menguat
- **Pertanyaan:** saham mana yang arus beli asingnya naik tajam dibanding 5 sesi sebelumnya?
- **Blok:** `M-FF-INC` (net asing > 0; Δ rasio net asing terhadap 5 sesi sebelumnya > 0; peringkat Δ antar saham net beli).
- **Parameter:** Longgar: Δ persentil ≥ 75. Standar: ≥ 90. Ketat: ≥ 95.
- **Pembanding persentil:** antar saham pada tanggal yang sama (jenis B), hanya saham yang net beli asing 5 sesi **dan** lolos gerbang likuiditas (diputuskan user 2026-11-10, bagian 6 nomor 9; terverifikasi pada hitung ulang). Hitungan: bagian 9.4.
- **Peringkat:** Δ menurun.
- **Kolom:** net asing, rasio sekarang, rasio 5 sesi lalu, Δ, persentil Δ.
- **Peringatan:** Δ besar sering berarti pemulihan dari net jual besar (MYOR, PGAS, UNVR), bukan pembelian besar.

### S3 — Pembelian terkonsentrasi dan bersih
- **Pertanyaan:** saham mana yang net belinya dikuasai sedikit broker dan sebagian besar pembeliannya searah?
- **Blok:** `M-CR3X-NET` (persentil dalam kelompok jumlah pembeli net yang mirip) dan `M-NET-INTENSITY` (persentil antar
  saham). Gerbang G4.
- **Parameter:** Longgar: CR3 − 3/k ≥ P70 dan intensitas ≥ P60. Standar: P80 dan P75. Ketat: P90 dan P90.
- **Pembanding persentil:** CR3 − 3/k diperingkat di dalam kelompok saham dengan k mirip (lima kelompok, dibentuk di antara saham yang lolos gerbang); intensitas diperingkat antar saham yang lolos gerbang. Hitungan: bagian 9.5.
- **Peringkat:** rata-rata kedua persentil, menurun.
- **Kolom:** k, CR3 − 3/k, persentil kelompok, intensitas, persentil intensitas, net asing 5 sesi.
- **Peringatan:** ini semua investor, bukan hanya asing. Beberapa kandidat justru dijual asing (ITMG net asing
  −Rp87,8 miliar). Pada uji awal 2026-11-04 (30 saham, di `M-NET-INTENSITY`), konsentrasi pembeli berhubungan negatif
  dengan return ke depan, belum konklusif. Baca sebagai pemindai "siapa yang membeli", bukan petunjuk arah.

### S4 — Insider opportunistic (direncanakan, belum dibangun)
Insider IDX yang membeli dengan pola opportunistic (bukan pola bulan yang sama berulang), tanpa baris berlabel repo dan
transfer, tanpa kembar IDX–KSEI, dan dengan ukuran relatif terhadap saham beredar. Bergantung pada keputusan aturan dedup
(ERRORS M241) dan label repo. Dasar riset: Cohen, Malloy, Pomorski (2012).

### S5 — Konfluensi
Aset yang muncul di S1 dan (S2 atau S3). Daftar pendek dengan jumlah bukti tertinggi, tetapi juga paling sedikit anggotanya.

## 4. Contoh keluaran, as-of 3 Nov 2026 (semua sumber di tanggal itu)

Contoh parameter dan jumlah, bukan rekomendasi. Jendela = 5 sesi Regular terakhir tiap saham.

**Jumlah aset per tingkat parameter** (gerbang G3 buang 20% terbawah):

| Tingkat | S1 | S2 | S3 | S1&S2 | S1&S3 | S2&S3 | ketiganya |
|---|---:|---:|---:|---:|---:|---:|---:|
| Longgar | 38 | 75 | 90 | 15 | 9 | 13 | 5 |
| Standar | 21 | 30 | 35 | 7 | 3 | 4 | 2 |
| Ketat | 9 | 15 | 15 | 4 | 1 | 2 | 0 |

**Pengaruh gerbang likuiditas** (tingkat Standar):

| Dibuang terbawah | Batas total beli | Saham tersisa | S1 | S2 | S3 | S1 & (S2 atau S3) |
|---|---:|---:|---:|---:|---:|---:|
| 20% | Rp0,3 miliar | 687 | 21 | 30 | 35 | 8 |
| 50% | Rp2,3 miliar | 430 | 16 | 19 | 31 | 4 |
| 70% | Rp8,7 miliar | 258 | 11 | 12 | 15 | 3 |
| 80% | Rp25,6 miliar | 172 | 6 | 8 | 11 | 3 |

**Kandidat pada gerbang "Likuid"** (buang 80% terbawah, Standar; miliar Rp):

S1:

| Ticker | Perusahaan | Beli 5 sesi | Net asing | Persentil 252 | z | Hari net beli | Rasio |
|---|---|---:|---:|---:|---:|---:|---:|
| BOGA | Apollo Global Interactive | 62,9 | 61,8 | 100,0 | 7,85 | 4 | 98,2% |
| BINA | Bank Ina Perdana | 39,1 | 1,3 | 99,2 | 5,85 | 3 | 3,2% |
| DKFT | Central Omega Resources | 32,3 | 14,8 | 95,2 | 1,48 | 3 | 45,9% |
| FORU | Fortune Indonesia | 87,8 | 3,0 | 97,6 | 1,31 | 3 | 3,4% |
| SQMI | Wilton Makmur Indonesia | 88,7 | 5,6 | 96,0 | 0,93 | 3 | 6,4% |
| NATO | Olympus Strategic Indonesia | 81,5 | 0,3 | 98,0 | 0,05 | 4 | 0,4% |

S2:

| Ticker | Perusahaan | Net asing | Rasio sekarang | Rasio 5 sesi lalu | Δ (poin) | Persentil Δ |
|---|---|---:|---:|---:|---:|---:|
| BOGA | Apollo Global Interactive | 61,8 | 98,2 | 1,8 | 96,4 | 100,0 |
| DKFT | Central Omega Resources | 14,8 | 45,9 | −29,9 | 75,8 | 98,6 |
| MSIN | MNC Digital Entertainment | 4,1 | 77,2 | 3,3 | 73,9 | 97,1 |
| RANS | Rans Entertainment | 11,7 | 43,8 | −10,0 | 53,8 | 95,7 |
| MYOR | Mayora Indah | 8,3 | 22,6 | −23,6 | 46,2 | 94,3 |
| PGAS | Perusahaan Gas Negara | 4,0 | 0,8 | −33,3 | 34,1 | 92,9 |
| UNVR | Unilever Indonesia | 14,8 | 7,2 | −20,8 | 28,1 | 91,4 |
| KOTA | DMS Propertindo | 15,0 | 20,5 | −5,5 | 26,0 | 90,0 |

S3 (delapan dari 11):

| Ticker | Perusahaan | k | CR3 − 3/k | Persentil kelompok | Intensitas | Persentil intensitas | Net asing |
|---|---|---:|---:|---:|---:|---:|---:|
| ITMG | Indo Tambangraya Megah | 24 | 0,835 | 100 | 0,539 | 94 | −87,8 |
| BTPS | Bank BTPN Syariah | 12 | 0,743 | 92 | 0,659 | 99 | −7,9 |
| CBDK | Bangun Kosambi Sukses | 16 | 0,766 | 97 | 0,509 | 91 | −0,7 |
| SMRA | Summarecon Agung | 13 | 0,738 | 89 | 0,625 | 98 | −5,4 |
| CNMA | Nusantara Sejahtera Raya | 34 | 0,729 | 94 | 0,511 | 92 | −1,6 |
| ADMF | Adira Dinamika Multi Finance | 22 | 0,743 | 82 | 0,897 | 100 | −16,8 |
| BINA | Bank Ina Perdana | 13 | 0,733 | 83 | 0,549 | 94 | +1,3 |
| MARK | Mark Dynamics Indonesia | 12 | 0,733 | 86 | 0,481 | 88 | +7,2 |

**S5 (konfluensi) pada gerbang itu:** BOGA, DKFT, BINA.

## 5. Pelajaran desain dari contoh ini

1. **Gerbang materialitas wajib.** Pada gerbang 20%, daftar teratas penuh saham mikro dengan net asing Rp0–3 miliar (MAPB,
   BRNA, SBMA). Persentil terhadap riwayat sendiri menyaring "luar biasa untuk saham kecil itu", bukan kandidat berarti.
2. **S1 masih meloloskan net sangat kecil** walau likuid (NATO: net Rp0,3 miliar dari beli Rp81,5 miliar, 0,4%).
3. **S3 bukan akumulasi asing.** Sebagian kandidat dijual asing; yang terjadi adalah sedikit broker menyerap pembelian.
4. **S2 menangkap pemulihan dari jual.** Δ besar karena titik awalnya sangat negatif.
5. **Konfluensi sangat sedikit.** Tiga aset pada gerbang "Likuid".

## 6. Keputusan yang terbuka

1. Tingkat gerbang likuiditas bawaan: "Luas" (buang 50%), "Likuid" (buang 80%), atau keduanya sebagai pilihan.
2. G5: rasio net asing minimum untuk S1 (usulan contoh: ≥ 5%) atau nilai minimum.
3. G4: angka 10 broker sudah tepat atau perlu diubah.
4. Nama S3 yang lebih tepat ("pembelian terkonsentrasi") dan apakah S3 hanya asing atau semua investor.
5. Ambang tiap tingkat (Longgar, Standar, Ketat) yang dipakai sebagai bawaan.
6. Aturan S4: dedup IDX–KSEI, label repo, definisi opportunistic (ERRORS M241, FUTURE_PLAN).
7. Penyimpanan: tetap dokumen ini, atau dimasukkan ke tabel kamus di database kelak.
8. Apakah S1 sampai S5 menjadi preset di Screener yang sudah ada (bagian 7) atau library terpisah.
9. ~~Persentil S2 dan S3 dihitung sesudah gerbang atau di seluruh universe.~~ **Diputuskan user 2026-11-10** ("Go dengan usulan untuk nomor 9 sampai 11. Masukan screener docs."): persentil S2 dan S3 dihitung **sesudah** gerbang likuiditas, pembandingnya hanya saham yang lolos gerbang. Bacaan AI atas "usulan": usulan yang ada di dokumen ini adalah cara itu (cocok dengan angka bagian 4 pada hitung ulang 2026-11-10, bagian 9.6); sebelum jawaban user belum ada usulan tertulis yang eksplisit. Akibat: pada gerbang ketat pembandingnya kecil (S2: 70 saham, satu saham = ±1,4 poin).
10. ~~Ukuran likuiditas G3.~~ **Diputuskan user 2026-11-10** (jawaban yang sama): G3 memakai **total beli bruto 5 sesi** (ukuran yang dipakai semua angka library ini). Entri "Likuiditas cukup" di `METHODOLOGY_DICTIONARY.md` (median nilai transaksi 60 sesi, buang 20%) belum disamakan dan tidak berlaku untuk library ini.
11. **Tampilan di FE: tetap terbuka.** Tidak ada usulan konkret sebelum jawaban user; bergantung pada butir 8 (preset di Screener yang ada atau library terpisah).

## 7. Hubungan dengan Screener yang sudah ada di repo

Repo sudah punya aplikasi Screener (`apps/edge-bff/screener`) dengan katalog 75 metrik
(`src/core/screener-metrics.json`) dan UI preset (`src/presets-ui.ts`). Dua puluh metrik Flow di katalog itu (kode `fl`
FL01 sampai FL20) berstatus **belum tersedia**: `unavailable_reason` "Flow metrics arrive with Phase 2". Library ini bisa
menjadi isi preset untuk fase itu.

Padanan konsep (terverifikasi dari rumus di katalog; keduanya belum dicocokkan angkanya):

| Konsep di library ini | Metrik screener yang serupa | Catatan |
|---|---|---|
| `M-FF-HEAVY` (persentil 252 sesi net asing) | `fsurprise` (FL05): persentil net asing 20 sesi terhadap 252 nilai sebelumnya | Jendela berbeda (5 sesi vs 20 sesi) |
| Net dan rasio asing | `fnet`, `fpct` (FL01, FL02) | Rasio net asing terhadap nilai transaksi |
| HHI pembeli net (kandidat kamus) | `net_buy_hhi` (FL10) | Rumus sama dengan "HHI hanya net buyer" |
| Top-N net beli terhadap net jual | `topacc`, `bandar` (FL07, FL09) | Mirip `M-TOPN-RATIO` |
| Persistensi pembeli terbesar | `dominant_persistence` (FL14) | Belum ada di kamus |
| Insider | `insider_net` (FL20) | Padanan S4 |

**Dua bentrokan nama yang harus diwaspadai:**
1. Kode: FL01 sampai FL20 di screener berarti hal lain daripada FL01 sampai FL20 di terminal
   (`FLOW_INDICATOR_REVIEW.md`, bagian 6; berkas itu ada di branch kerja `claude/intelligent-mccarthy-70imcn` dan belum di `main`).
2. Istilah: `buy_intensity` (FL08) di screener adalah `100 × B_N / nilai transaksi` (nilai net beli top-N sebagai % nilai
   transaksi), sedangkan "intensitas net beli" di kamus (`M-NET-INTENSITY`) adalah net beli broker bernet positif dibagi
   beli bruto. Keduanya berbeda.

Belum diputuskan: apakah S1 sampai S5 ditulis sebagai preset di Screener yang sudah ada (memakai metriknya) atau tetap
sebagai library terpisah yang dihitung dari data mentah.

## 8. Batas

- Satu tanggal (3 Nov 2026), satu jendela 5 sesi. Kestabilan daftar dari hari ke hari belum diukur.
- Nama perusahaan diambil dari `Price_Stock_Indonesia_IDX.company_name`.
- Persentil riwayat asing (`persentil 252`, `z`) berasal dari `Feature_06`; ukuran broker dihitung dari
  `IDX_Broker_Summary` di sandbox dan sama dengan `Feature_06` pada net asing (784 dari 784 saham, uji 2026-11-03).
- Bukan rekomendasi investasi.

## 9. Hitungan detail S1 sampai S3 (hitung ulang 2026-11-10, as-of 3 Nov 2026)

Semua angka dihitung dari data hidup, bukan disalin: S1 dan S2 dari `Feature_06_Foreign_Domestic`, S3 dari `IDX_Broker_Summary`,
papan Regular, **5 sesi terakhir tiap saham** (28 Okt sampai 3 Nov 2026), universe 859 saham di `Feature_06` yang punya
data 3 Nov. Satuan Rupiah miliar. Hasil adalah kandidat untuk ditelaah, bukan rekomendasi.

### 9.1 Dua jenis persentil

| Jenis | Pembanding | Rumus | Dipakai di |
|---|---|---|---|
| A. Riwayat sendiri | 252 nilai sebelum hari ini milik saham yang sama | 100 × (jumlah nilai riwayat yang **lebih kecil** dari nilai sekarang) ÷ 252 | S1 |
| B. Antar saham | Saham lain pada tanggal yang sama (kumpulan pembanding disebut di tiap kartu) | 100 × (jumlah saham pembanding lain yang **lebih kecil**) ÷ (jumlah pembanding − 1) | S2, S3 (intensitas dan kelompok k) |

Persentil 98,6 berarti nilai itu lebih besar daripada 98,6% pembandingnya. Persentil **bukan** nilai itu sendiri: Δ 75,8 poin
hanya sekian poin, sedangkan persentil menunjukkan peringkatnya.

### 9.2 Gerbang G3 (likuiditas): saham terkecil dibuang dulu

Langkah, untuk satu tanggal: (1) tiap saham: jumlahkan beli asing + beli domestik pada 5 sesi Regular terakhir saham itu;
(2) kumpulkan angka dari semua saham pada tanggal itu; (3) tentukan batas pada persentil yang dipilih; (4) buang saham di
bawah batas, lalu jalankan S1 sampai S3 pada sisanya. Tidak ada saham yang "disaring" lebih dulu: semua dihitung, diurutkan, lalu
bagian terbawah dibuang. Batas Rupiah berubah tiap hari.

| Dibuang terbawah | Persentil | Batas total beli 5 sesi (Rp miliar) | Saham tersisa |
|---|---:|---:|---:|
| 20% | P20 | 0,30 | 687 |
| 50% | P50 | 2,30 | 430 |
| 70% | P70 | 8,68 | 258 |
| 80% | P80 | 25,64 | 172 |

Sama dengan bagian 2 (batas Rp0,3 / 2,3 / 8,7 / 25,6 miliar; sisa 687 / 430 / 258 / 172). **Universe menentukan batas:** pada
populasi lain batasnya berbeda; dari seluruh 1.221 simbol di `IDX_Broker_Summary` batas "buang 80%" hanya Rp9,61 miliar,
sedangkan pada universe `Feature_06` Rp25,64 miliar (G2).

### 9.3 S1 Akumulasi asing heavy

**Syarat (Standar):** ketiganya terpenuhi.

| # | Syarat | Rumus |
|---|---|---|
| 1 | Net asing 5 sesi > 0 | Σ (beli asing − jual asing) 5 sesi |
| 2 | Persentil riwayat 252 sesi ≥ 95 | persentil jenis A dari `foreign_net_5d` |
| 3 | Net beli di ≥ 3 dari 5 sesi | hari dengan net asing harian > 0 |

Longgar: persentil ≥ 90. Ketat: persentil ≥ 95 dan z-score ≥ 2 (z = (nilai − rata-rata riwayat) ÷ simpangan baku riwayat).

**DKFT** PT Central Omega Resources Tbk: net asing harian 5 sesi (Rp miliar)

| Tanggal | Net asing (beli asing − jual asing) | Net beli? |
|---|---:|---|
| 2026-10-28 | −1,173 | tidak |
| 2026-10-29 | −1,159 | tidak |
| 2026-10-30 | +7,669 | ya |
| 2026-11-02 | +4,973 | ya |
| 2026-11-03 | +4,525 | ya |
| **Jumlah (net asing 5 sesi)** | **+14,834** | **3 dari 5** |

| Langkah | Hitungan | Hasil |
|---|---|---:|
| Riwayat | 252 nilai `foreign_net_5d` sebelum 3 Nov | rata-rata −0,089; simpangan baku 10,098 |
| Persentil | nilai riwayat yang lebih kecil dari +14,834: 240 dari 252, 240 ÷ 252 × 100 | **95,2** |
| z-score | (+14,834 − (−0,089)) ÷ 10,098 | **1,48** (tersimpan 1,48) |
| Total beli 5 sesi | beli asing + beli domestik | 32,33 |
| Rasio net asing | +14,834 ÷ 32,33 | 45,9% |

**NATO** PT Olympus Strategic Indonesia Tbk: net asing harian 5 sesi (Rp miliar)

| Tanggal | Net asing (beli asing − jual asing) | Net beli? |
|---|---:|---|
| 2026-10-28 | −0,011 | tidak |
| 2026-10-29 | +0,006 | ya |
| 2026-10-30 | +0,198 | ya |
| 2026-11-02 | +0,036 | ya |
| 2026-11-03 | +0,081 | ya |
| **Jumlah (net asing 5 sesi)** | **+0,309** | **4 dari 5** |

| Langkah | Hitungan | Hasil |
|---|---|---:|
| Riwayat | 252 nilai `foreign_net_5d` sebelum 3 Nov | rata-rata −0,139; simpangan baku 10,081 |
| Persentil | nilai riwayat yang lebih kecil dari +0,309: 247 dari 252, 247 ÷ 252 × 100 | **98,0** |
| z-score | (+0,309 − (−0,139)) ÷ 10,081 | **0,04** (tersimpan 0,05) |
| Total beli 5 sesi | beli asing + beli domestik | 81,54 |
| Rasio net asing | +0,309 ÷ 81,54 | 0,4% |

**BBCA** PT Bank Central Asia Tbk: net asing harian 5 sesi (Rp miliar)

| Tanggal | Net asing (beli asing − jual asing) | Net beli? |
|---|---:|---|
| 2026-10-28 | +1.174,698 | ya |
| 2026-10-29 | −503,491 | tidak |
| 2026-10-30 | −5,955 | tidak |
| 2026-11-02 | −116,143 | tidak |
| 2026-11-03 | −23,847 | tidak |
| **Jumlah (net asing 5 sesi)** | **+525,262** | **1 dari 5** |

| Langkah | Hitungan | Hasil |
|---|---|---:|
| Riwayat | 252 nilai `foreign_net_5d` sebelum 3 Nov | rata-rata −670,145; simpangan baku 1.639,234 |
| Persentil | nilai riwayat yang lebih kecil dari +525,262: 213 dari 252, 213 ÷ 252 × 100 | **84,5** |
| z-score | (+525,262 − (−670,145)) ÷ 1.639,234 | **0,73** (tersimpan 0,73) |
| Total beli 5 sesi | beli asing + beli domestik | 8.288,17 |
| Rasio net asing | +525,262 ÷ 8.288,17 | 6,3% |

**Keputusan untuk tiga contoh (Standar):**

| Saham | Net asing > 0 | Persentil ≥ 95 | Net beli ≥ 3 dari 5 | z ≥ 2 (Ketat) | Hasil Standar |
|---|---|---|---|---|---|
| DKFT | ya (+14,834) | ya (95,2) | ya (3) | tidak (1,48) | **lolos** |
| NATO | ya (+0,309) | ya (98,0) | ya (4) | tidak (0,05) | **lolos**, tetapi net hanya 0,4% dari pembelian |
| BBCA | ya (+525,262) | **tidak (84,5)** | **tidak (1)** | tidak (0,73) | **tidak lolos** |

Persentil tinggi terhadap riwayat sendiri tidak memandang ukuran: NATO lolos karena riwayat net asingnya sendiri sangat kecil
(simpangan baku Rp10 miliar), padahal net sekarang hanya Rp0,3 miliar. Itu sebabnya G5 (net minimum) masih terbuka.

**Jumlah lolos S1 menurut gerbang (Standar):**

| Dibuang terbawah | Saham tersisa | Net asing 5 sesi > 0 | + persentil ≥ 95 | + net beli ≥ 3 dari 5 sesi (lolos S1) |
|---|---:|---:|---:|---:|
| 20% | 687 | 298 | 27 | **21** |
| 50% | 430 | 188 | 20 | **16** |
| 70% | 258 | 112 | 13 | **11** |
| 80% | 172 | 70 | 6 | **6** |

Cocok dengan bagian 4 (21 / 16 / 11 / 6). **Daftar pada gerbang "Likuid" (buang 80%):**

| Ticker | Perusahaan | Beli 5 sesi | Net asing | Persentil 252 | z | Hari net beli | Rasio |
|---|---|---:|---:|---:|---:|---:|---:|
| BOGA | PT Apollo Global Interactive Tbk | 62,9 | 61,8 | 100,0 | 7,85 | 4 | 98,2% |
| BINA | PT Bank Ina Perdana Tbk | 39,1 | 1,3 | 99,2 | 5,85 | 3 | 3,2% |
| NATO | PT Olympus Strategic Indonesia Tbk | 81,5 | 0,3 | 98,0 | 0,05 | 4 | 0,4% |
| FORU | PT Fortune Indonesia, Tbk | 87,8 | 3,0 | 97,6 | 1,31 | 3 | 3,4% |
| SQMI | PT Wilton Makmur Indonesia Tbk | 88,7 | 5,6 | 96,0 | 0,93 | 3 | 6,4% |
| DKFT | PT Central Omega Resources Tbk | 32,3 | 14,8 | 95,2 | 1,48 | 3 | 45,9% |

### 9.4 S2 Arus asing menguat

**Syarat (Standar):** (1) net asing 5 sesi > 0; (2) Δ > 0, dengan Δ = rasio 5 sesi sekarang − rasio 5 sesi tepat sebelumnya
(tidak tumpang tindih), rasio = 100 × Σ(beli asing − jual asing) ÷ Σ(beli asing + beli domestik); (3) Δ berada di persentil
≥ 90 (jenis B) di antara saham yang net beli asing dan lolos gerbang. Longgar: ≥ 75. Ketat: ≥ 95.

| Saham | Jendela | Net asing | Total beli | Rasio |
|---|---|---:|---:|---:|
| DKFT | sekarang 2026-10-28 s.d. 2026-11-03 | +14,834 | 32,328 | 45,89% |
| DKFT | sebelumnya 2026-10-21 s.d. 2026-10-27 | −1,869 | 6,258 | −29,87% |
| **DKFT** | **Δ = 45,89 − (−29,87)** | | | **75,75 poin** |
| KOTA | sekarang 2026-10-28 s.d. 2026-11-03 | +15,030 | 73,309 | 20,50% |
| KOTA | sebelumnya 2026-10-21 s.d. 2026-10-27 | −6,415 | 116,127 | −5,52% |
| **KOTA** | **Δ = 20,50 − (−5,52)** | | | **26,03 poin** |
| PGAS | sekarang 2026-10-28 s.d. 2026-11-03 | +3,969 | 496,445 | 0,80% |
| PGAS | sebelumnya 2026-10-21 s.d. 2026-10-27 | −165,340 | 497,134 | −33,26% |
| **PGAS** | **Δ = 0,80 − (−33,26)** | | | **34,06 poin** |

Hasil sesuai tabel di atas dengan `foreign_net_turnover_ratio_5d` tersimpan (DKFT 45,89 dan −29,87; KOTA 20,50 dan −5,52; PGAS 0,80 dan −33,26).

**Penelusuran persentil Δ pada gerbang 80% (pembanding 70 saham, jadi 69 saham lain per saham):**

| Saham | Δ (poin) | Saham lain dengan Δ lebih kecil | Persentil | Lolos ≥ 90? |
|---|---:|---:|---:|---|
| DKFT | 75,8 | 68 dari 69 | 68 ÷ 69 × 100 = 98,6 | ya |
| PGAS | 34,1 | 64 dari 69 | 92,8 | ya |
| KOTA | 26,0 | 62 dari 69 | 62 ÷ 69 × 100 = 89,9 | **tidak** (kurang 0,1) |

**Jumlah lolos S2 menurut gerbang (Standar):**

| Dibuang terbawah | Saham tersisa | Pembanding (net asing > 0) | Δ > 0 | Batas Δ persentil 90 (poin) | Lolos S2 (persentil Δ ≥ 90) |
|---|---:|---:|---:|---:|---:|
| 20% | 687 | 298 | 242 | 24,8 | **30** |
| 50% | 430 | 188 | 157 | 25,2 | **19** |
| 70% | 258 | 112 | 94 | 26,0 | **12** |
| 80% | 172 | 70 | 59 | 28,1 | **7** |

**Daftar sepuluh teratas pada gerbang "Likuid" (buang 80%):**

| Ticker | Perusahaan | Net asing | Rasio sekarang | Rasio 5 sesi lalu | Δ (poin) | Persentil Δ | Lolos? |
|---|---|---:|---:|---:|---:|---:|---|
| BOGA | PT Apollo Global Interactive Tbk | 61,8 | 98,2 | 1,8 | 96,4 | 100,0 | ya |
| DKFT | PT Central Omega Resources Tbk | 14,8 | 45,9 | −29,9 | 75,8 | 98,6 | ya |
| MSIN | PT MNC Digital Entertainment Tbk | 4,1 | 77,2 | 3,3 | 73,9 | 97,1 | ya |
| RANS | PT Rans Entertainmen Indonesia Tbk | 11,7 | 43,8 | −10,0 | 53,8 | 95,7 | ya |
| MYOR | PT Mayora Indah Tbk | 8,3 | 22,6 | −23,6 | 46,2 | 94,2 | ya |
| PGAS | PT Perusahaan Gas Negara (Persero) Tbk Class B | 4,0 | 0,8 | −33,3 | 34,1 | 92,8 | ya |
| UNVR | PT Unilever Indonesia Tbk | 14,8 | 7,2 | −20,8 | 28,1 | 91,3 | ya |
| KOTA | PT DMS Propertindo Tbk | 15,0 | 20,5 | −5,5 | 26,0 | 89,9 | tidak |
| CDIA | PT Chandra Daya Investasi Tbk. | 10,8 | 13,1 | −12,1 | 25,2 | 88,4 | tidak |
| GOTO | PT GoTo Gojek Tokopedia Tbk | 99,6 | 12,0 | −12,2 | 24,2 | 87,0 | tidak |

Cara membaca: Δ besar sering berarti pemulihan dari net jual (rasio sebelumnya negatif), bukan pembelian besar. PGAS lolos
dengan rasio sekarang hanya 0,8%. Syarat 2 (Δ > 0) tidak memilah: pada gerbang 80%, 59 dari 70 saham net beli punya Δ > 0.

### 9.5 S3 Pembelian terkonsentrasi dan bersih

**Langkah per saham (5 sesi, Regular, semua investor):**

| # | Langkah | Rumus |
|---|---|---|
| 1 | Net per broker | Σ beli − Σ jual per broker (jenis investor dijumlah) |
| 2 | k | jumlah broker dengan net > 0 (gerbang G4: k ≥ 10) |
| 3 | CR3 | jumlah net 3 pembeli net terbesar ÷ jumlah net semua pembeli net |
| 4 | Konsentrasi | **CR3 − 3 ÷ k** (0 bila merata) |
| 5 | Intensitas | jumlah net semua pembeli net ÷ jumlah **beli bruto semua broker** |
| 6 | Persentil kelompok | peringkat CR3 − 3/k di dalam kelompok k |
| 7 | Persentil intensitas | peringkat intensitas antar saham yang lolos gerbang |

**Syarat (Standar):** persentil kelompok ≥ 80 **dan** persentil intensitas ≥ 75. Longgar: 70 dan 60. Ketat: 90 dan 90.
Kelompok: saham yang lolos gerbang dibagi lima menurut k (kuantil k; saham dengan k sama tidak dipisah), lalu tiap saham
diperingkat di dalam kelompoknya.

**BTPS** PT Bank BTPN Syariah Tbk: pembeli net 5 sesi 28 Okt s.d. 3 Nov (Rp miliar, papan Regular, semua investor)

| Peringkat | Broker | Beli | Jual | Net (beli − jual) |
|---:|---|---:|---:|---:|
| 1 | CC | 34,220 | 5,719 | +28,501 |
| 2 | BS | 0,460 | 0,000 | +0,460 |
| 3 | BB | 0,162 | 0,000 | +0,162 |
| 4 | PP | 0,087 | 0,000 | +0,087 |
| 5 | ZP | 0,761 | 0,731 | +0,030 |
| 6 | AT | 0,072 | 0,044 | +0,028 |
| 7 | HP | 0,044 | 0,017 | +0,028 |
| 8 | GR | 0,280 | 0,259 | +0,021 |
| 9 | BQ | 0,017 | 0,007 | +0,010 |
| 10 | PC | 0,004 | 0,001 | +0,003 |
| 11 | YJ | 0,001 | 0,001 | +0,000 |
| 12 | QA | 0,000 | 0,000 | +0,000 |
| **Jumlah 12 pembeli net** | | 36,109 | 6,778 | **29,331** |

| Langkah | Hitungan | Hasil |
|---|---|---:|
| k (pembeli net) | broker dengan net > 0 | 12 |
| Jumlah net positif | seperti tabel di atas (jumlah net 32 penjual net: −29,331; total semua broker −0,000) | 29,331 |
| CR3 | 29,123 ÷ 29,331 | 0,9929 |
| Bagian merata | 3 ÷ 12 | 0,2500 |
| **CR3 − 3/k** | 0,9929 − 0,2500 | **0,743** |
| Total beli bruto semua broker | Σ beli seluruh broker | 44,483 |
| **Intensitas** | 29,331 ÷ 44,483 | **0,659** |
| Kelompok k | k = 12: kelompok 1 | |
| Persentil dalam kelompok | peringkat CR3 − 3/k di kelompok | **91,4** |
| Persentil intensitas | peringkat di 171 saham likuid | **98,8** |

**BBCA** PT Bank Central Asia Tbk: pembeli net 5 sesi 28 Okt s.d. 3 Nov (Rp miliar, papan Regular, semua investor)

| Peringkat | Broker | Beli | Jual | Net (beli − jual) |
|---:|---|---:|---:|---:|
| 1 | ZP | 1.409,016 | 548,319 | +860,697 |
| 2 | BK | 931,218 | 739,327 | +191,891 |
| 3 | AG | 137,056 | 43,087 | +93,969 |
| 4 s.d. 43 | 40 pembeli net lain | 3.264,564 | 2.811,816 | +452,748 |
| **Jumlah 43 pembeli net** | | 5.741,854 | 4.142,549 | **1.599,305** |

| Langkah | Hitungan | Hasil |
|---|---|---:|
| k (pembeli net) | broker dengan net > 0 | 43 |
| Jumlah net positif | seperti tabel di atas (jumlah net 42 penjual net: −1.599,305; total semua broker −0,000) | 1.599,305 |
| CR3 | 1.146,557 ÷ 1.599,305 | 0,7169 |
| Bagian merata | 3 ÷ 43 | 0,0698 |
| **CR3 − 3/k** | 0,7169 − 0,0698 | **0,647** |
| Total beli bruto semua broker | Σ beli seluruh broker | 8.288,170 |
| **Intensitas** | 1.599,305 ÷ 8.288,170 | **0,193** |
| Kelompok k | k = 43: kelompok 5 | |
| Persentil dalam kelompok | peringkat CR3 − 3/k di kelompok | **96,7** |
| Persentil intensitas | peringkat di 171 saham likuid | **24,7** |

**Keputusan untuk dua contoh (Standar, gerbang 80%):**

| Saham | k | CR3 − 3/k | Ambang kelompok (persentil ≥ 80) | Intensitas | Ambang intensitas (persentil ≥ 75) | Hasil |
|---|---:|---:|---:|---:|---:|---|
| BTPS | 12 | 0,743 | 0,731 (kelompok 1) | 0,659 | 0,380 | **lolos** |
| BBCA | 43 | 0,647 | 0,586 (kelompok 5) | 0,193 | 0,380 | **tidak lolos** (konsentrasi tinggi, intensitas rendah) |

**Kelompok k dan ambangnya pada gerbang 80%:**

| Kelompok | Rentang k (pembeli net) | Jumlah saham | Ambang CR3 − 3/k untuk persentil ≥ 80 |
|---:|---|---:|---:|
| 1 | 10–21 | 36 | 0,731 |
| 2 | 22–26 | 33 | 0,743 |
| 3 | 27–31 | 37 | 0,662 |
| 4 | 32–38 | 34 | 0,623 |
| 5 | 39–63 | 31 | 0,586 |
| Semua | | 171 | ambang intensitas persentil ≥ 75: 0,380 |

**Jumlah lolos S3 menurut gerbang (Standar):**

| Dibuang terbawah | Saham tersisa | Lolos G4 (k ≥ 10) | CR3 − 3/k persentil kelompok ≥ 80 | + intensitas persentil ≥ 75 (lolos S3) |
|---|---:|---:|---:|---:|
| 20% | 687 | 633 | 130 | **35** |
| 50% | 430 | 416 | 85 | **30** |
| 70% | 258 | 255 | 54 | **15** |
| 80% | 172 | 171 | 37 | **11** |

**Kandidat pada gerbang "Likuid" (buang 80%), 11 saham:**

| Ticker | Perusahaan | k | CR3 − 3/k | Persentil kelompok | Intensitas | Persentil intensitas | Net asing 5 sesi |
|---|---|---:|---:|---:|---:|---:|---:|
| ITMG | PT Indo Tambangraya Megah Tbk | 24 | 0,835 | 100 | 0,539 | 94 | −87,8 |
| CBDK | PT Bangun Kosambi Sukses Tbk | 16 | 0,766 | 97 | 0,509 | 91 | −0,7 |
| CNMA | PT Nusantara Sejahtera Raya Tbk | 34 | 0,729 | 94 | 0,511 | 92 | −1,6 |
| ADRO | PT Alamtri Resources Indonesia Tbk | 43 | 0,625 | 93 | 0,397 | 80 | −134,7 |
| BTPS | PT Bank BTPN Syariah Tbk | 12 | 0,743 | 91 | 0,659 | 99 | −7,9 |
| SMRA | PT Summarecon Agung Tbk | 13 | 0,738 | 89 | 0,625 | 98 | −5,4 |
| UNTR | PT United Tractors Tbk | 42 | 0,599 | 87 | 0,389 | 78 | −108,9 |
| MARK | PT Mark Dynamics Indonesia Tbk | 12 | 0,733 | 86 | 0,481 | 88 | +7,2 |
| AMRT | PT Sumber Alfaria Trijaya | 47 | 0,596 | 83 | 0,488 | 89 | +4,1 |
| BINA | PT Bank Ina Perdana Tbk | 13 | 0,733 | 83 | 0,549 | 94 | +1,3 |
| ADMF | PT Adira Dinamika Multi Finance Tbk | 22 | 0,743 | 81 | 0,897 | 100 | −16,8 |

Cara membaca: S3 menangkap "sedikit broker menyerap pembelian", **bukan akumulasi asing**: 8 dari 11 kandidat net jual asing.
BTPS contoh ekstrem: satu broker (CC, +28,501) memegang 97,2% dari net beli (28,501 ÷ 29,331), jadi "3 pembeli terbesar"
sebenarnya satu broker. CR3 − 3/k tidak membedakan satu broker dominan dari tiga yang setara.

### 9.6 Selisih terhadap bagian 4 dan keterbatasan

| Butir | Bagian 4 | Hitung ulang 2026-11-10 | Penyebab yang diduga |
|---|---|---|---|
| S2 lolos, gerbang 80% | 8 (termasuk KOTA, persentil 90,0) | 7 (KOTA 89,9) | Pembanding 70 saham, bukan 71; satu saham menggeser KOTA 0,1 poin |
| S3 lolos, gerbang 50% | 31 | 30 | Satu saham pada batas persentil; cara memotong kelompok k |
| Persentil kelompok BTPS dan ADMF | 92 dan 82 | 91 dan 81 | Sama |
| z-score NATO | 0,05 | 0,04 (z tersimpan 0,05) | Pembulatan; tabel memakai nilai tersimpan |

Keterbatasan: satu tanggal dan satu jendela 5 sesi; kestabilan hari ke hari belum diukur; persentil kelompok dan persentil S2
sangat sensitif pada gerbang ketat karena pembandingnya hanya sekitar 70 sampai 170 saham (satu saham = ±1,4 poin pada S2);
cara pembentukan kelompok k (kuantil k) adalah bacaan dari angka bagian 4 yang tidak dituliskan di dokumen ini sebelumnya.
Nama perusahaan dari `Price_Stock_Indonesia_IDX.company_name`.
