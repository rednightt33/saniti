# Library screener: filter yang memunculkan aset kandidat

**Status:** rancangan, belum diputuskan parameternya, belum dibangun sebagai fitur. Dicatat 2026-11-04.

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
| G3 Likuiditas (materialitas) | Total beli bruto 5 sesi tiap saham, dibuang menurut persentil. **"Luas":** buang 50% terbawah. **"Likuid":** buang 80% terbawah | **Usulan; tingkat bawaan belum diputuskan** |
| G4 Jumlah broker | Untuk blok konsentrasi: minimal 10 broker net beli | Pilihan AI, belum diputuskan |
| G5 Materialitas asing | Rasio net asing minimum agar blok asing tidak meloloskan net yang sangat kecil | **Terbuka** (lihat bagian 6) |

Batas Rp pada 3 Nov 2026 (total beli bruto 5 sesi): buang 20% = Rp0,3 miliar, 50% = Rp2,3 miliar, 70% = Rp8,7 miliar,
80% = Rp25,6 miliar. Batasnya relatif sehingga berubah tiap hari.

## 3. Kartu screener

### S1 — Akumulasi asing heavy
- **Pertanyaan:** saham mana yang net beli asing 5 sesinya luar biasa besar terhadap riwayat saham itu sendiri?
- **Blok:** `M-FF-HEAVY` (net asing 5 sesi > 0; persentil 252 sesi; net beli di ≥ 3 dari 5 sesi).
- **Parameter:** Longgar: persentil ≥ 90. Standar: persentil ≥ 95. Ketat: persentil ≥ 95 dan z-score ≥ 2.
- **Peringkat:** z-score 252 sesi, menurun.
- **Kolom:** beli bruto 5 sesi, net asing 5 sesi, persentil dan z-score, jumlah hari net beli, rasio net asing.
- **Peringatan:** persentil terhadap riwayat sendiri tidak memandang ukuran. Tanpa G3 dan G5, saham mikro dengan net
  asing Rp0,3 miliar ikut lolos (contoh NATO).

### S2 — Arus asing menguat
- **Pertanyaan:** saham mana yang arus beli asingnya naik tajam dibanding 5 sesi sebelumnya?
- **Blok:** `M-FF-INC` (net asing > 0; Δ rasio net asing terhadap 5 sesi sebelumnya > 0; peringkat Δ antar saham net beli).
- **Parameter:** Longgar: Δ persentil ≥ 75. Standar: ≥ 90. Ketat: ≥ 95.
- **Peringkat:** Δ menurun.
- **Kolom:** net asing, rasio sekarang, rasio 5 sesi lalu, Δ, persentil Δ.
- **Peringatan:** Δ besar sering berarti pemulihan dari net jual besar (MYOR, PGAS, UNVR), bukan pembelian besar.

### S3 — Pembelian terkonsentrasi dan bersih
- **Pertanyaan:** saham mana yang net belinya dikuasai sedikit broker dan sebagian besar pembeliannya searah?
- **Blok:** `M-CR3X-NET` (persentil dalam kelompok jumlah pembeli net yang mirip) dan `M-NET-INTENSITY` (persentil antar
  saham). Gerbang G4.
- **Parameter:** Longgar: CR3 − 3/k ≥ P70 dan intensitas ≥ P60. Standar: P80 dan P75. Ketat: P90 dan P90.
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
   ([`FLOW_INDICATOR_REVIEW.md`](FLOW_INDICATOR_REVIEW.md), bagian 6).
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
