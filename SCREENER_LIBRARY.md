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


### S6 — Akumulasi asing, rasio 5 sesi (rancangan, struktur versi terkunci 2026-11-10; jendela 5 sesi sejak 2026-11-10)
Empat versi (V1 absolut, V1Δ perubahan absolut terhadap T−5, V2 persentil riwayat, V2Δ perubahan persentil), bebas dicentang; tanpa peringkat antar saham (V3). Rincian dan hitungan: bagian 11. S7 dan S8 menyusul dengan struktur yang sama.

### S7 — Institusi masuk, ritel keluar (rancangan, disetujui user 2026-11-10)
Indikator FL34 (selisih net broker institusi dan ritel, jendela 5 sesi) dengan keadaan perubahan terhadap T−5 (membaik, pembalikan, menguat dan cerminnya), besar Δ sebagai syarat, dan penjaga net institusi > 0 serta ukuran kaki institusi ≥ 5% dari total beli. V2 dan V2Δ menunggu keputusan data. Rincian dan kriteria masuk: bagian 12 (12.6).
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

1. Tingkat gerbang likuiditas bawaan: "Luas" (buang 50%), "Likuid" (buang 80%), atau keduanya sebagai pilihan. **Rekomendasi AI: bagian 10 nomor 1.**
2. G5: rasio net asing minimum untuk S1 (usulan contoh: ≥ 5%) atau nilai minimum. **Rekomendasi AI: bagian 10 nomor 2.**
3. G4: angka 10 broker sudah tepat atau perlu diubah.
4. Nama S3 yang lebih tepat ("pembelian terkonsentrasi") dan apakah S3 hanya asing atau semua investor. **Rekomendasi AI: bagian 10 nomor 4.**
5. Ambang tiap tingkat (Longgar, Standar, Ketat) yang dipakai sebagai bawaan.
6. Aturan S4: dedup IDX–KSEI, label repo, definisi opportunistic (ERRORS M241, FUTURE_PLAN).
7. Penyimpanan: tetap dokumen ini, atau dimasukkan ke tabel kamus di database kelak.
8. Apakah S1 sampai S5 menjadi preset di Screener yang sudah ada (bagian 7) atau library terpisah. **Koreksi 2026-11-10:** jawaban awal AI ("library terpisah, karena metrik Flow Screener belum tersedia") memakai katalog Screener lama dan tidak berlaku; keadaan di `main` ada di bagian 7. Butir ini tetap terbuka.
9. ~~Persentil S2 dan S3 dihitung sesudah gerbang atau di seluruh universe.~~ **Diputuskan user 2026-11-10** ("Go dengan usulan untuk nomor 9 sampai 11. Masukan screener docs."): persentil S2 dan S3 dihitung **sesudah** gerbang likuiditas, pembandingnya hanya saham yang lolos gerbang. Bacaan AI atas "usulan": usulan yang ada di dokumen ini adalah cara itu (cocok dengan angka bagian 4 pada hitung ulang 2026-11-10, bagian 9.6); sebelum jawaban user belum ada usulan tertulis yang eksplisit. Akibat: pada gerbang ketat pembandingnya kecil (S2: 70 saham, satu saham = ±1,4 poin).
10. ~~Ukuran likuiditas G3.~~ **Diputuskan user 2026-11-10** (jawaban yang sama): G3 memakai **total beli bruto 5 sesi** (ukuran yang dipakai semua angka library ini). Entri "Likuiditas cukup" di `METHODOLOGY_DICTIONARY.md` (median nilai transaksi 60 sesi, buang 20%) belum disamakan dan tidak berlaku untuk library ini.
11. **Tampilan di FE: tetap terbuka.** Tidak ada usulan konkret sebelum jawaban user; bergantung pada butir 8 (preset di Screener yang ada atau library terpisah).

## 7. Hubungan dengan Screener yang sudah ada di repo (diperbarui 2026-11-10 dari `origin/main` commit `f0519350`)

**Koreksi:** versi bagian ini yang dipublikasikan sebelumnya memakai katalog Screener lama (75 metrik; dua puluh metrik Flow "belum tersedia, Fase 2") dan tidak berlaku lagi di `main`. Penyebabnya: salinan lokal `origin/main` di sandbox basi saat itu (ketinggalan 412 commit); angka di bagian ini dibaca ulang dari `main` yang baru di-fetch.

**Keadaan di `main`:**

| Hal | Keadaan | Bukti |
|---|---|---|
| Indikator Flow di terminal | 52 (FL01 sampai FL52) | `apps/edge-bff/terminal/src/data/flowRegistry.json` |
| Metrik Flow di Screener | 48 indikator terminal sebagai metrik; FL49 sampai FL52 dan garis rata-rata FL14 tidak ikut (`terminal_only`); FL31 butuh data insider | commit `cc991d2a` (2026-11-07, P5a), `bbda1f2e`; header `core/flowmetrics.ts` |
| Cara dihitung | `computeFlow` terminal yang sama, per saham, pada jendela broker 60 sesi (K1) | header `core/flowmetrics.ts` |
| Kode FL | Screener memakai kode FL yang sama dengan terminal; dua puluh entri lama diganti. **Bentrokan kode FL yang tertulis di versi lama sudah tidak ada.** | commit `cc991d2a`; `core/screener-metrics.json` (grup Flow tinggal `silent` dan `adv20_idr`) |
| "Intensitas" | FL47 Net Buy Intensity memakai rumus `M-NET-INTENSITY` (100 × Σ max(net, 0) ÷ Σ beli bruto), jadi tidak ada lagi dua arti istilah | `terminal/src/calc/flow.ts` (FL47) |
| Preset Bandarmology yang sudah ada | Big Accumulation (FL24), Foreign Accumulation Streak (FL26), Silent Accumulation, Frequency Spike (FL32), Near Bandar Average Price (FL39 + FL24), Broker Follow (FL23); gabungan: Quality + Foreign Inflow, Value + Accumulation | `core/presets.json` |
| Universe bawaan preset | harga ≥ 50, ADV20 ≥ Rp1 miliar, diperdagangkan pada tanggal evaluasi, tanpa PRICE_BREAK | `core/presets.json` |
| Peringkat antar saham | Hanya `return_rank`; peringkat Flow antar saham (berkas xsection Flow) berstatus Phase 2, diusulkan | header `core/xsection.ts`; `SCREENER_ONBOARDING.md` |

**Padanan S1 sampai S3 dengan indikator Flow di BFF** (bacaan dari registry dan kode; angkanya belum dicocokkan):

| Bagian library | Indikator BFF terdekat | Batas |
|---|---|---|
| S1 net asing 5 sesi luar biasa terhadap riwayat | FL37 (investor Foreign, scope all, window 5) | Baseline persentil dibatasi jendela broker 60 sesi dikurangi jendela indikator (K1), jadi tidak bisa 252 sesi |
| S1 net beli di ≥ 3 dari 5 sesi | FL12 (Foreign, scope all, window 5) | Persentase hari net beli; 3 dari 5 = 60% |
| S2 Δ rasio dan persentil antar saham | FL11 (Foreign, window 5) dan perubahannya | Persentil antar saham untuk Flow belum ada; apakah perubahan FL11 dapat dipakai sebagai kondisi belum diperiksa |
| S3 CR3 − 3/k | FL16 (Top 3, window 5, `even` aktif) | Persentil dalam kelompok k belum ada |
| S3 intensitas | FL47 (window 5) | `stat` persentil membandingkan dengan riwayat sendiri, bukan antar saham |

Akibatnya (bacaan AI): S1 sampai S3 persis seperti bagian 9 belum dapat dibuat sebagai preset Screener, karena butuh peringkat Flow antar saham dan baseline lebih dari 60 sesi. Versi dengan ambang mutlak dapat dibuat dari indikator di atas. Belum diputuskan apakah S1 sampai S5 ditulis sebagai preset (dengan versi pendekatan) atau tetap library terpisah yang dihitung dari data mentah (bagian 6 nomor 8).

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

## 10. Rekomendasi AI (bukan keputusan user; permintaan 2026-11-10)

User meminta nomor 1, 2, dan 4 dari tabel usulan dimasukkan ke dokumen sebagai rekomendasi, lengkap dengan alasannya. Nomor merujuk bagian 6.

| # | Butir | Rekomendasi | Alasan |
|---|---|---|---|
| 1 | Tingkat gerbang likuiditas bawaan (G3) | Sediakan dua tingkat; bawaan **"Luas" (buang 50%)**, "Likuid" (buang 80%) sebagai pilihan | (a) Jumlah lolos S1 / S2 / S3 pada "Luas" 16 / 19 / 30, pada "Likuid" hanya 6 / 7 / 11 dan konfluensi S5 hanya 3 saham (bagian 4). (b) Pada gerbang 20% daftar teratas dipenuhi saham mikro dengan net asing Rp0 sampai 3 miliar (bagian 5 nomor 1). (c) Preset Screener yang sudah ada memakai lantai ADV20 ≥ Rp1 miliar (bagian 7); perkiraan dari total beli broker 20 sesi ÷ 20, lantai itu meloloskan 385 dari 858 saham, mendekati "Luas" (430 saham, batas Rp2,3 miliar per 5 sesi), jadi bawaan "Luas" konsisten dengan preset yang ada. Perkiraan ini bukan metrik `adv20_idr` resmi. |
| 2 | G5, net asing minimum untuk S1 dan S2 | Rasio net asing 5 sesi **≥ 5%** (net asing ÷ total beli 5 sesi), berlaku untuk S1 dan S2 | Persentil terhadap riwayat sendiri tidak memandang ukuran (NATO: simpangan baku riwayat Rp10 miliar, net sekarang Rp0,3 miliar, 0,4% dari pembelian). Hitungan 2026-11-10: pada "Luas" S1 turun dari 16 ke 6 dan S2 dari 19 ke 17; pada "Likuid" S1 dari 6 ke 3 (BINA 3,2%, NATO 0,4%, FORU 3,4% gugur) dan S2 dari 7 ke 6 (PGAS 0,8% gugur). Yang bertahan material: S1 BOGA 98,2%, DKFT 45,9%, SQMI 6,4%; S2 MSIN 77,2%, RANS 43,8%, MYOR 22,6%, UNVR 7,2%. Angka 5% adalah usulan awal dokumen ini; belum diuji sensitivitasnya di sekitar 3% sampai 10%. |
| 4 | Nama dan cakupan S3 | Cakupan **semua investor**; nama **"Pembelian bersih terkonsentrasi"** (bukan "akumulasi asing") | S3 dihitung dari net per broker semua investor (bagian 9.5), dan 8 dari 11 kandidat pada "Likuid" justru net jual asing (ITMG −Rp87,8 miliar, ADRO −Rp134,7 miliar, UNTR −Rp108,9 miliar). Nama yang menyebut asing akan menyesatkan. Contoh ekstrem BTPS: satu broker (CC) memegang 97,2% net beli, jadi "terkonsentrasi" menggambarkan hasilnya dengan benar. Membatasi ke asing akan mengubah pertanyaan menjadi net asing per broker, yang bukan yang diukur. |

Batas: satu tanggal (3 Nov 2026) dan satu jendela 5 sesi; kestabilan hari ke hari belum diukur; rekomendasi ini menunggu keputusan user.

## 11. S6 Akumulasi asing: struktur versi (terkunci 2026-11-10, belum dibangun)

**Keputusan user 2026-11-10:** "V1 absolute / V1 delta: delta absolute terhadap T-5 / V2 riwayat percentile absolute value / V2 delta: riwayat percentile absolute value vs. riwayat percentile absolute value T-5" dan "Ok lock ya rekomendasi kamu." Sebelumnya: "Leave S1 S2 S3 dulu as is karena sudah OK", subset bebas dicentang (iii). **Koreksi user 2026-11-10: "tidak ada V3. yang ada adalah V1 dan V1-delta, V2 dan V2-delta"**; versi peringkat antar saham (V3-abs, V3-pct) yang sempat tercatat dihapus. S1 sampai S3 tidak berubah. S7 dan S8 belum disusun.
Ambang masih usulan yang belum diuji sensitivitasnya; semua angka dihitung dari `Feature_06_Foreign_Domestic`, as-of 3 Nov 2026, papan Regular.

### 11.1 Ukuran dan versi

**Jendela: 5 sesi** (keputusan user 2026-11-10: "jadikan saja dulu 5 hari"; sebelumnya 20 sesi). **Ukuran:** rasio net asing 5 sesi = Σ(beli asing − jual asing) ÷ Σ(beli asing + beli domestik), 5 sesi terakhir saham itu (`foreign_net_turnover_ratio_5d`; setara FL11 asing, jendela 5). Positif berarti net beli. Dengan jendela 5 dan T−5, V1Δ membandingkan dua blok 5 sesi berurutan yang tidak tumpang tindih, sama dengan Δ S2 (bagian 11.5).

**Peringatan:** ambang, jumlah lolos, dan contoh di bagian 11.1 sampai 11.3 dihitung untuk rasio **20 sesi** dan belum dihitung ulang untuk jendela 5 sesi. Rasio 5 sesi lebih bergejolak (contoh DKFT: −29,87% lalu +45,89% pada dua blok 5 sesi), jadi ambang kemungkinan perlu disesuaikan; itu belum diuji.

| Versi | Yang diuji | Longgar | **Standar** | Ketat |
|---|---|---:|---:|---:|
| V1 Absolut | rasio ≥ | 3% | **5%** | 10% |
| V1Δ Perubahan absolut | rasio hari ini − rasio T−5 ≥ (poin) | 3 | **5** | 13 |
| V2 Persentil riwayat | persentil rasio hari ini terhadap 252 nilai rasio saham itu sendiri ≥ | 90 | **95** | 98 |
| V2Δ Perubahan persentil | persentil hari ini − persentil T−5 ≥ (poin); persentil T−5 dihitung dengan riwayat 252 nilai sebelum T−5 | 5 | **13** | 25 |

Persentil riwayat = 100 × (jumlah dari 252 nilai sebelumnya yang lebih kecil dari nilai hari ini) ÷ 252.

**Aturan yang terkunci:**

| # | Aturan |
|---|---|
| 1 | Versi dipilih bebas sebagai subset (keputusan user: iii). |
| 2 | V1Δ dan V2Δ tidak boleh dicentang tanpa V1 atau V2. Alasan: Δ sendirian meloloskan terlalu banyak saham (V1Δ 36% dan V2Δ 38% dari 168 saham pada ambang awal), termasuk yang rasionya rendah atau negatif (GOTO 1,8% dari −14,5; BBYB −10,1%). |
| 3 | Arah Δ dapat dipilih naik atau turun; "turun" (Δ ≤ −ambang) dipakai untuk mencari momentum yang melambat. Bacaan AI atas "naik atau menurun". |
| 4 | Jarak tetap T−5 (5 sesi sebelum hari ini). |
| 5 | Tidak ada versi peringkat antar saham (V3). V2 dan V2Δ hanya terhadap riwayat saham itu sendiri; satu-satunya pembanding antar saham adalah gerbang likuiditas. |
| 6 | Persistensi "net beli di ≥ 3 dari 5 sesi" (seperti S1) kembali sebagai **syarat opsional**, di luar keempat versi (keputusan user 2026-11-10: "Ok" atas usulan AI). Streak berturut-turut tidak dipakai. |
| 7 | Bawaan subset (bacaan AI): V1 + V2; versi Δ mati. |
| 8 | **Syarat tetap (bukan versi):** net asing 5 sesi > 0, seperti S1 dan S2, supaya V2 atau V2Δ sendirian tidak meloloskan saham yang asingnya menjual (contoh rasio 20 sesi: HEAL persentil riwayat 94,8 dengan rasio −2,1%, lolos pada tingkat Longgar). Keputusan user 2026-11-10: "Ok". |
| 9 | **Gerbang global ditulis eksplisit:** G2 universe dan G3 likuiditas (total beli bruto 5 sesi); tingkat bawaan "Luas" sesuai rekomendasi bagian 10 nomor 1 (disetujui untuk S6 oleh "Ok" 2026-11-10; belum menjadi keputusan global). |
| 10 | Aturan 6, 8, dan 9 juga berlaku untuk S7 dan S8 saat disusun, dengan padanan sisi masing-masing. |

**Dasar ambang Δ:** sebaran Δ pada saham yang lolos V1 (rasio ≥ 5%), gerbang "Luas" (n = 56): V1Δ P50 2,9, P75 5,5, P90 13,7 poin; V2Δ P50 4,6, P75 12,6, P90 27,6 poin. Longgar ≈ P50, Standar ≈ P75, Ketat ≈ P90, dibulatkan. Pada gerbang "Likuid" (n = 32): V1Δ 2,6 / 5,0 / 13,5; V2Δ 1,0 / 12,6 / 20,8.

### 11.2 Jumlah lolos (Standar)

| Subset | Likuid 80% (168 punya riwayat) | Luas 50% (412) | 20% (666) |
|---|---:|---:|---:|
| V1 | 32 | 56 | 83 |
| V2 | 12 | 32 | 52 |
| V1 + V2 | 11 | 24 | 35 |
| V1 + V1Δ | 8 | 16 | 23 |
| V2 + V2Δ | 5 | 10 | 13 |
| V1 + V2 + V1Δ | 4 | 8 | 12 |
| V1 + V2 + V2Δ | 5 | 8 | 8 |
| V1 + V2 + V1Δ + V2Δ | 4 | 6 | 6 |

V1Δ sendiri 17 / 35 / 46 dan V2Δ sendiri 35 / 81 / 108 (hanya untuk dokumentasi; aturan 2 melarangnya sendirian). Tingkat lain pada "Likuid": Longgar V1 44, V2 25, V1 + V2 22, keempat versi 9; Ketat V1 18, V2 9, V1 + V2 6, keempat versi 2.

### 11.3 Contoh: 11 saham yang lolos V1 + V2 pada gerbang "Likuid", Standar

| Saham | V1 rasio | V1Δ (poin) | V2 | V2Δ (poin) | V1Δ ≥ 5 | V2Δ ≥ 13 |
|---|---:|---:|---:|---:|:-:|:-:|
| BOGA | 97,6 | +98,3 | 98,4 | +27,0 | ✓ | ✓ |
| PWON | 31,8 | −2,4 | 95,2 | −4,8 | ✗ | ✗ |
| MAPA | 25,0 | +4,7 | 100,0 | +0,4 | ✗ | ✗ |
| CTRA | 23,4 | +1,3 | 98,4 | −1,6 | ✗ | ✗ |
| DKFT | 21,9 | +22,5 | 100,0 | +43,3 | ✓ | ✓ |
| WIIM | 20,3 | +14,4 | 98,0 | +21,0 | ✓ | ✓ |
| ARKO | 13,3 | +6,1 | 96,0 | +13,5 | ✓ | ✓ |
| SSMS | 13,3 | +3,2 | 100,0 | 0,0 | ✗ | ✗ |
| EMTK | 8,5 | +3,3 | 98,4 | +9,1 | ✗ | ✗ |
| RAJA | 5,5 | +3,2 | 99,2 | +8,3 | ✗ | ✗ |
| KOTA | 5,2 | +4,3 | 99,6 | +18,3 | ✗ | ✓ |

PWON dan CTRA lolos level tetapi gagal kedua Δ: kasus "melambat". Penelusuran dua saham:

| Saham | V1 rasio | rasio T−5 | V1Δ | V2: nilai riwayat lebih kecil | V2 T−5 | V2Δ |
|---|---:|---:|---:|---|---:|---:|
| BOGA | 97,6 | −0,7 | +98,3 | 248 dari 252 = 98,4 | 71,4 | +27,0 |
| DKFT | 21,9 | −0,5 | +22,5 | 252 dari 252 = 100,0 | 56,7 | +43,3 |

### 11.4 Keterbatasan

- V2 jenuh di 100 (3 saham persis 100,0): MAPA dan SSMS naik +4,7 dan +3,2 poin di V1Δ tetapi V2Δ hampir nol. Itu alasan kedua Δ dipertahankan.
- (Berlaku untuk jendela 20 sesi; pada jendela 5 sesi blok berurutan dan tidak tumpang tindih.) Rasio hari ini dan rasio T−5 berbagi 15 dari 20 sesi: V1Δ adalah selisih 5 sesi yang masuk dan 5 sesi yang keluar. BOGA: 5 sesi masuk (28 Okt sampai 3 Nov) net asing +Rp61,77 miliar dari total beli Rp62,89 miliar = 98,2%; 5 sesi keluar (30 Sep sampai 6 Okt) −9,6% dari Rp0,04 miliar.
- V2 memakai persentil rasio (bukan Rupiah); riwayat kurang dari 252 sesi (4 saham pada "Likuid") tidak diikutkan di V2 dan V2Δ.
- Tumpang tindih dengan S1: pada "Likuid" hanya BOGA dan DKFT yang ada di S1 dan lolos ketiga versi S6; 9 dari 11 saham tidak ada di S1 (horizon 20 sesi dan rasio, bukan 5 sesi dan Rupiah).
- Di BFF `main`, persentil riwayat 252 sesi dan peringkat Flow antar saham belum dapat dibuat persis (baseline dibatasi jendela broker 60 sesi; peringkat antar saham Flow masih Phase 2); bagian 7.
- Satu tanggal; ambang Δ dibulatkan dari sebaran sampel kecil (n = 32 sampai 56); sensitivitas belum diuji.

### 11.5 Kepekaan V1Δ dibanding S2 (hitungan 2026-11-10)

V1Δ memakai rasio 20 sesi yang digeser 5 sesi (berbagi 15 sesi), sedangkan Δ S2 membandingkan dua blok 5 sesi berurutan. Akibatnya V1Δ jauh kurang peka: ia hanya melihat selisih 5 sesi yang masuk dan 5 sesi yang keluar, dan di dalam jendela 20 sesi selisih itu diencerkan oleh 15 sesi yang sama. Penelusuran DKFT (Rp miliar, papan Regular):

| Blok | Sesi | Net asing | Total beli | Rasio |
|---|---|---:|---:|---:|
| Keluar | 30 Sep s.d. 6 Okt | −0,635 | 11,831 | −5,37% |
| Bersama (15 sesi) | 7 Okt s.d. 27 Okt | +0,368 | 36,946 | 1,00% |
| Masuk | 28 Okt s.d. 3 Nov | +14,834 | 32,328 | 45,89% |
| Blok sebelumnya (S2) | 21 Okt s.d. 27 Okt | −1,869 | 6,258 | −29,87% |

r20 hari ini = (0,368 + 14,834) ÷ (36,946 + 32,328) = 21,95%; r20 pada T−5 = (0,368 − 0,635) ÷ (36,946 + 11,831) = −0,55%; **V1Δ = +22,49 poin**. Δ S2 = 45,89 − (−29,87) = **+75,75 poin**.

| Saham | Δ S2 (blok 5 sesi) | V1Δ (rasio 20 sesi, T−5) | Selisih |
|---|---:|---:|---:|
| DKFT | +75,75 | +22,49 | 3,4 kali |
| MYOR | +46,25 | +8,24 | 5,6 kali |
| UNVR | +28,08 | +3,44 | 8,2 kali |

Selisihnya tidak konstan (3,4 sampai 8,2 kali), karena bergantung pada isi 15 sesi yang sama. **Diputuskan user 2026-11-10: jendela 5 sesi dulu** ("jadikan saja dulu 5 hari"). Apakah jendela dapat dipilih (5 atau 20 sesi) belum diputuskan. Dengan jendela 5 sesi dan T−5, V1Δ identik dengan Δ S2 sebelum diperingkat.

### 11.6 Arti sebuah saham lolos tiap versi (jendela 5 sesi; penjelasan, belum dihitung ulang)

**Apa yang dihitung:** untuk tiap saham, rasio net asing 5 sesi = (beli asing − jual asing) ÷ (beli asing + beli domestik) selama 5 sesi terakhir saham itu, papan Regular, jenis investor Foreign melawan Domestic. Positif berarti asing menyerap pembelian saham itu secara bersih.

| Versi | Pertanyaan yang dijawab | Arti bila saham lolos | Yang tidak dikatakan |
|---|---|---|---|
| V1 | Seberapa besar asing menyerap pembelian saham ini secara bersih dalam 5 sesi terakhir? | Net beli asing ≥ ambang persen dari seluruh nilai beli saham itu. Dapat dibandingkan antar saham (relatif terhadap transaksi), dan menjaga ukuran minimum. | Tidak berarti tidak biasa bagi saham itu, dan bukan jumlah Rupiah yang besar. |
| V1Δ | Apakah net beli asing minggu ini lebih besar daripada minggu lalu? | Rasio 5 sesi terakhir lebih tinggi ≥ ambang poin dibanding 5 sesi tepat sebelumnya (blok berurutan; sama dengan Δ S2). | Bisa berarti pemulihan dari net jual (minggu lalu negatif) dan tidak menjamin level tinggi; karena itu wajib disertai V1 atau V2. |
| V2 | Apakah rasio minggu ini tinggi menurut kebiasaan saham itu sendiri? | Rasio lebih besar daripada ≥ persentil ambang dari 252 nilai rasio 5 sesi sebelumnya milik saham itu. | Tidak berarti besar dibanding saham lain. Nilai riwayat berurutan berbagi 4 dari 5 sesi, jadi 252 nilai itu tidak independen (bacaan AI). Jenuh di 100. |
| V2Δ | Apakah rasio itu menjadi lebih tidak biasa dibanding minggu lalu? | Persentil minggu ini naik ≥ ambang poin dibanding persentil minggu lalu, masing-masing terhadap riwayatnya saat itu. | Persentil jenuh di atas (100 menjadi 100 = nol), dan tidak sama dengan arus Rupiah yang menguat. |

**Arti kombinasi:** V1 + V2 = besar dan tidak biasa bagi saham itu; V1 + V1Δ = besar dan menguat; V2 + V2Δ = tidak biasa dan makin tidak biasa; keempatnya = besar, tidak biasa, dan menguat. Dengan arah Δ "turun", lolos level tetapi nilainya lebih rendah daripada 5 sesi lalu berarti momentum melambat.

**Hubungan dengan S1 dan S2:** V2 mirip S1 (persentil terhadap riwayat sendiri) tetapi atas rasio, bukan Rupiah, dan tanpa syarat 3 dari 5 hari net beli. V1Δ sama dengan Δ S2 tetapi dipakai dengan ambang, bukan diperingkat antar saham.

**Yang bukan artinya:** bukan sinyal beli; hanya jenis investor Foreign di seluruh broker (bukan broker tertentu); tidak membedakan satu transaksi blok dari pembelian yang tersebar (kecuali syarat persistensi opsional dicentang).

## 12. S7 Institusi masuk, ritel keluar (rancangan disetujui 2026-11-10, belum dibangun)

**Keputusan user 2026-11-10:** "Ok default 5 sesi tidak apa sebenarnya. Yang mau di detect adalah apabila value ini negatif tapi jadi less negative compare to X session, negative to positive, atau positive to even stronger positive. Kemudian magnitude perubahannya juga." Atas usulan AI (penjaga per keadaan, ambang, cerminnya): "bisa disetujui. Dan oke lah kita masuk ... ke usulan tersebut dan itu bisa dipakai."
Angka dihitung dari `IDX_Broker_Summary` (papan Regular, kedua jenis investor), as-of 3 Nov 2026, universe 859 saham `Feature_06`. Ambang adalah usulan awal; sensitivitas belum diuji.

### 12.1 Ukuran

**FL34** (kode `main`, `flow.ts`): `100 × (net broker institusi − net broker ritel) ÷ total beli bruto semua broker`, dijumlahkan selama jendela W sesi yang berakhir hari itu (W = "Rolling days", bawaan 20; **di S7 dipakai 5**). Keluaran `change` = nilai hari ini − nilai pada 1, 5, atau 20 sesi lalu (di S7: 5, sehingga dua blok 5 sesi berurutan dan tidak tumpang tindih).
Daftar broker: `Institutional-heavy` dan `Retail-heavy` dari `IDX_Broker_Profile` (yang dibaca BFF; 112 broker: 25 institusi-heavy, 19 ritel-heavy, 23 Mixed, 45 Niche). Label identik dengan `Feature_02_Broker_Rolling` untuk 89 broker yang sama, dan hasil S7 identik pada kedua daftar (3 Nov, jendela 5 sesi). Klasifikasi terkini dipakai untuk semua tanggal. Broker yang ada di kedua daftar membuat nilai kosong.

**Penguraian (identitas):** FL34 = % institusi − % ritel, dengan % = net kelompok ÷ total beli semua broker. Perubahan Δ = dI + dR, dI = perubahan % institusi, dR = −(perubahan % ritel); identitas diuji pada semua saham (selisih terbesar 1,4·10⁻¹⁴). Net institusi + net ritel + net "lainnya" (Mixed dan Niche) = 0, sehingga net "lainnya" dapat diturunkan.

### 12.2 Keadaan perubahan dan besar Δ

| Kode | FL34 sebelumnya → sekarang | Nama | Jumlah ("Likuid" 172 / "Luas" 430) |
|---|---|---|---:|
| A | negatif → kurang negatif | Dominasi ritel mereda | 28 / 64 |
| B | negatif → positif | Pembalikan | 23 / 87 |
| C | positif → lebih positif | Menguat | 33 / 73 |
| x | negatif → lebih negatif | Memburuk | 26 / 67 |
| y | positif → kurang positif | Melemah | 21 / 44 |
| z | positif → negatif | Berbalik turun | 41 / 95 |

A, B, C adalah arah naik; x, y, z cerminnya (arah turun, bacaan AI). Keadaan saja tidak selektif (A + B + C = 49% saham pada "Likuid"), karena FL34 5 sesi bergejolak: sebaran seluruh saham P10 −23,4, P50 −0,5, P90 +26,6; Δ P10 −29,5, P50 0,0, P90 +30,0. **Besar Δ wajib menjadi syarat.**

| Tingkat | Δ ≥ (poin FL34) |
|---|---:|
| Longgar | 10 |
| **Standar** | **20** |
| Ketat | 40 |

Jumlah per keadaan menurut ambang ("Likuid" / "Luas"):

| Keadaan | Δ ≥ 10 | Δ ≥ 20 | Δ ≥ 40 | Sebaran Δ P50 / P75 / P90 ("Likuid") |
|---|---:|---:|---:|---|
| A | 13 / 23 | 9 / 13 | 4 / 5 | 7,5 / 24,1 / 45,4 |
| B | 17 / 63 | 12 / 34 | 4 / 9 | 22,0 / 32,7 / 42,0 |
| C | 14 / 32 | 6 / 14 | 0 / 2 | 7,4 / 14,5 / 22,7 |

### 12.3 Penjaga (disetujui)

| # | Aturan |
|---|---|
| 1 | Keadaan dan Δ ≥ ambang menggantikan penjaga level V1 (aturan S6 "Δ wajib disertai V1 atau V2" tidak berlaku, karena A dan B justru lolos saat level negatif). |
| 2 | **Net institusi 5 sesi > 0** wajib untuk B dan C ("masuk"), bawaan aktif; **tidak** berlaku untuk A. |
| 3 | Net ritel 5 sesi < 0: penjaga opsional. |
| 4 | Hasil selalu menampilkan net institusi, net ritel, net "lainnya" (turunan), % tiap kelompok, Δ, dI dan dR. |
| 5 | G2 universe dan G3 likuiditas eksplisit (bawaan "Luas"); persistensi opsional: net institusi positif di ≥ 3 dari 5 sesi (padanan aturan 6 S6). |
| 6a | **Gerbang ukuran kaki institusi** untuk B dan C: % institusi = net institusi ÷ total beli semua broker (5 sesi) ≥ **2 / 5 / 10** (Longgar / Standar / Ketat). Alasan: net institusi positif bisa sangat kecil (JARR +0,6%, KIJA +1,0%, ISAT +2,2% dari total beli) sementara FL34 berbalik karena ritel menjual. Disetujui user 2026-11-10 ("Okay"). |
| 6 | V2 dan V2Δ (persentil terhadap 252 nilai FL34 saham itu sendiri) **menunggu keputusan data**: butuh tabel turunan (net institusi, net ritel, total beli per saham per hari); hanya `Feature_06` yang menyimpan persentil riwayat. Pemindaian 272 sesi data broker ke semua saham ditunda (membaca jutaan baris). |

Pengaruh penjaga net institusi > 0 pada Δ ≥ 20 ("Likuid" / "Luas"):

| Keadaan | Lolos Δ ≥ 20 | Dengan net institusi > 0 | Net institusi > 0 dan net ritel < 0 | "Lainnya" net beli lebih besar dari net institusi |
|---|---:|---:|---:|---:|
| A | 9 / 13 | 1 / 1 | 0 / 0 | 8 / 12 |
| B | 12 / 34 | 10 / 25 | 10 / 25 | 8 / 26 |
| C | 6 / 14 | 6 / 13 | 6 / 13 | 2 / 6 |

### 12.4 Cara membaca FL34 (jawaban atas pertanyaan user 2026-11-10)

**Pertanyaan:** bila FL34 sangat negatif lalu mendadak positif atau kurang negatif, apakah itu berarti institusi masuk atau net buy? **Jawaban:** tidak otomatis. Ritel net beli **menurunkan** FL34 (dikurangkan di pembilang); kenaikan FL34 datang dari institusi yang lebih banyak membeli dan/atau ritel yang lebih banyak menjual (atau kurang membeli). Net institusi positif hanya terlihat dari level kaki institusi, bukan dari tanda FL34.

Saham yang FL34-nya sebelumnya ≤ −30 lalu naik ≥ 20 poin:

| | "Likuid" | "Luas" |
|---|---|---|
| Jumlah | 8 | 13 |
| **Tetap negatif ("membaik")** | 6 | 10 |
| ... net institusi sekarang > 0 | **0 dari 6** | **0 dari 10** |
| ... kontribusi institusi (dI) > kontribusi ritel (dR) | 4 | 6 |
| ... kontribusi institusi positif (institusi kurang menjual) | 5 | 9 |
| **Menjadi positif ("pembalikan")** | 2 | 3 |
| ... net institusi sekarang > 0 | 2 dari 2 | 2 dari 3 |
| ... dI > dR | 2 | 2 |

Contoh ("Likuid"; Rp miliar untuk net institusi):

| Saham | FL34 sebelumnya → sekarang | Δ | dI | dR | Net institusi sekarang |
|---|---|---:|---:|---:|---:|
| CNMA | −83,5 → −6,6 | +76,9 | +39,8 | +37,0 | −2,86 |
| UNVR | −38,8 → +16,7 | +55,5 | +35,2 | +20,3 | **+22,76** |
| MIKA | −81,8 → −31,6 | +50,2 | +36,3 | +13,9 | −14,93 |
| SCMA | −35,9 → +6,3 | +42,2 | +22,1 | +20,1 | +1,51 |
| TCPI | −38,9 → −9,0 | +29,9 | −0,3 | +30,2 | −8,77 |
| TLKM | −40,2 → −15,7 | +24,6 | +5,0 | +19,6 | **−595,55** |

TLKM: FL34 membaik 24,6 poin padahal institusi masih net jual Rp595,55 miliar; seluruh perbaikan datang dari kaki ritel. BTPS (pembalikan ke +35,3) positif karena ritel menjual Rp19,77 miliar, sementara institusi net jual Rp4,08 miliar dan net "lainnya" +Rp23,85 miliar (54% dari total beli).

### 12.5 Keterbatasan

Satu tanggal dan satu jendela 5 sesi; sampel "sangat negatif lalu naik" kecil (8 dan 13 saham); ambang belum diuji sensitivitasnya; FL34 tidak memperlihatkan konsentrasi di dalam kelompok (CBDK: satu broker institusi, KI, memegang 99,7% net institusi 5 sesi); label broker adalah kecenderungan klien, bukan jenis investor transaksi; Mixed dan Niche (68 dari 112 broker) tidak masuk pembilang.

### 12.6 Kriteria sebuah saham masuk S7 (Standar)

**Jendela dan perbandingan:** FL34 dihitung pada jendela bergulir 5 sesi (5 sesi terakhir saham itu, papan Regular, Foreign + Domestic). Perbandingannya hanya **hari ini dikurangi T−5**, yaitu FL34 dari 5 sesi yang berakhir hari ini dikurangi FL34 dari 5 sesi yang berakhir 5 sesi sebelumnya. Dua blok itu berurutan dan tidak tumpang tindih (blok sekarang = sesi ke-1 sampai ke-5 mundur, blok sebelumnya = sesi ke-6 sampai ke-10 mundur). FL34 `change` di BFF menyediakan jarak 1, 5, atau 20; S7 memakai 5 saja.

**"Institusi masuk"** (semua harus terpenuhi):

| # | Kriteria | Ambang Standar |
|---|---|---|
| 1 | Lolos G2 (ada di `Feature_06`, ≥ 5 sesi Regular di 16 tanggal bursa terakhir) dan G3 (total beli bruto 5 sesi di atas batas; bawaan "Luas") | buang 50% terbawah |
| 2 | FL34 sekarang dan FL34 pada T−5 sama-sama punya nilai | |
| 3 | Keadaan **B** (sebelumnya < 0, sekarang ≥ 0) atau **C** (sebelumnya ≥ 0, sekarang lebih besar) | |
| 4 | Δ = FL34 sekarang − FL34 T−5 | ≥ 20 poin |
| 5 | Net institusi 5 sesi | > 0 |
| 6 | % institusi = net institusi ÷ total beli semua broker (5 sesi) | ≥ 5% |

Opsional: net ritel 5 sesi < 0 ("ritel keluar"); persistensi: net institusi positif di ≥ 3 dari 5 sesi.

**"Dominasi ritel mereda"** (keadaan A): kriteria 1, 2, dan 4 ditambah keadaan A (sebelumnya < 0, sekarang < 0 tetapi lebih tinggi); **tanpa** kriteria 5 dan 6, karena pada keadaan A institusi umumnya masih net jual. **Arah turun** memakai cerminnya (x, y, z) dengan Δ ≤ −ambang; penjaganya belum ditetapkan.

**Jumlah lolos "institusi masuk" (Standar):** 11 pada gerbang "Likuid" (B 5 + C 6) dan 23 pada "Luas" (B 11 + C 12); tanpa kriteria 6: 16 dan 38.

Contoh ("Likuid", 3 Nov 2026; FL34 sebelumnya → sekarang, Δ, net institusi dalam Rp miliar, % institusi):

| Saham | Keadaan | FL34 | Δ | Net institusi | % institusi | Hasil |
|---|---|---|---:|---:|---:|---|
| CBDK | C | +57,0 → +79,8 | +22,8 | +13,19 | 42,2 | **masuk** |
| UNVR | B | −38,8 → +16,7 | +55,5 | +22,76 | 11,1 | **masuk** |
| KOTA | B | −6,2 → +19,0 | +25,2 | +9,79 | 13,4 | **masuk** |
| JARR | B | −10,2 → +21,5 | +31,7 | +0,31 | 0,6 | gagal kriteria 6 |
| ISAT | B | −15,0 → +18,4 | +33,4 | +16,19 | 2,2 | gagal kriteria 6 |
| BTPS | B | −9,7 → +35,3 | +45,0 | −4,08 | −9,2 | gagal kriteria 5 dan 6 |
