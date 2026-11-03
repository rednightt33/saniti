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
8. **Hitung sendiri dari data mentah; tabel Feature hanya jalan pintas dan pembanding.** Keputusan user 2026-11-03:
   "ini tidak perlu rely on feature only ya.. Ini bisa buat our own calculation dan jalankan di your own sandbox. Data
   raw sudah ada IDX_Broker_Summary". Sumber utama setiap entri adalah `IDX_Broker_Summary` (45,07 juta baris, 10 GB;
   Regular ±23 ribu baris per tanggal untuk ±858 saham), ditarik per tanggal lewat pgweb hanya-baca (batas 30 detik per
   query) dan dihitung di sandbox. Hasil uji 2026-11-03: **[T]**
   - 5 tanggal Regular, semua saham = 116.183 baris, 29 MB, 3,9 detik total;
   - net asing 5 sesi hitungan sendiri cocok dengan `Feature_06.foreign_net_5d` pada 784 dari 784 saham yang
     bertransaksi di kelima tanggal (selisih maksimum 0,00 Rp);
   - contoh BBCA (top 3 beli/jual) sama dengan hitungan tangan sebelumnya.
   Yang tidak terbatas lagi oleh Feature: top N penjual, sisi gross, nilai N, cakupan investor type, dan pemilihan
   universe saham. Riwayat panjang (252 sesi × ±858 saham ≈ 6 juta baris Regular, ±1,4 GB terbaca) belum diukur
   langsung: sebut perkiraan dan minta izin sebelum menjalankannya (cache memori Postgres ikut ditagih; `AGENTS.md`,
   Postgres memory). Perhitungan yang rumit dilakukan di sandbox dari hasil query yang sudah difilter, jangan menarik
   jutaan baris sekaligus.
9. **Setiap entri dijelaskan dengan contoh untuk pembaca.** Permintaan user 2026-11-03: "Tolong setiap metode dijelaskan
   dengan contoh. Walk through the readers agar mereka paham dan mengerti indikator tersebut bicara soal apa."
   Setiap entri dimulai dengan bagian "Penjelasan dan contoh (untuk pembaca)" (intinya, langkah, contoh kecil yang bisa
   dihitung dengan kalkulator, contoh nyata BBCA, cara membaca, dan apa yang tidak dijawab), baru diikuti "Rincian
   teknis". Angka contoh nyata dihitung dari data pada 2026-11-03 dan ditandai **[T]**; angka contoh kecil adalah
   karangan untuk menjelaskan rumus.

Kolom penanda status pada tiap entri: **[T]** terverifikasi di data atau katalog pada 2026-11-03, **[D]** dugaan atau
usulan yang belum diverifikasi.

---

## Istilah yang dipakai di dokumen ini

| Istilah | Arti |
|---|---|
| Broker | Perusahaan sekuritas yang mengeksekusi transaksi (kode dua huruf, misalnya BK, ZP). **Kode broker bukan identitas investor:** satu broker melayani banyak klien, domestik maupun asing |
| Beli bruto / jual bruto | Total nilai yang dibeli / dijual, tanpa saling dikurangkan |
| Net | Beli dikurangi jual. Positif = net beli, negatif = net jual |
| Pembeli net / penjual net | Broker yang net-nya positif / negatif pada jendela yang dihitung |
| k | Jumlah broker di sisi yang dihitung. `k_net` = jumlah pembeli net; `k_gross` = jumlah broker yang punya beli bruto |
| Sesi dan jendela | Sesi = hari bursa saham itu. Jendela = rentang sesi yang dihitung (bawaan 5 sesi, kira-kira satu minggu) |
| Board | Regular (pasar utama), Nego (negosiasi), Tunai. Tidak pernah dijumlah |
| Investor Type | Domestic atau Foreign: jenis investor pada transaksi, bukan jenis broker |
| Persentil | Posisi dalam urutan. Persentil 90 berarti lebih tinggi dari 90% pembandingnya |
| z-score | Berapa simpangan baku sebuah nilai berada di atas rata-rata pembandingnya. z = 2 berarti sekitar 2 simpangan baku di atas |
| Pembanding jenis A / B | A = riwayat saham itu sendiri. B = saham lain pada tanggal yang sama |
| Miliar, triliun | Dalam percakapan "M" berarti miliar dan "T" triliun. Di dokumen ini ditulis lengkap, dalam Rupiah |

---

## M-FF-INC — Peningkatan foreign flow (5 sesi)

### Penjelasan dan contoh (untuk pembaca)

**Intinya:** apakah dalam 5 sesi terakhir investor asing membeli *lebih banyak* daripada 5 sesi sebelumnya, dengan
memperhitungkan seberapa ramai saham itu? Ukurannya bukan berapa Rupiah, tetapi berapa **persen dari transaksi saham
itu** yang berupa net beli asing.

**Langkahnya**
1. Hitung rasio net asing: (beli asing − jual asing) ÷ total nilai transaksi, selama 5 sesi. Contoh: asing net beli
   Rp50 miliar dari transaksi Rp1.000 miliar = **5%**.
2. Hitung rasio yang sama untuk 5 sesi tepat sebelumnya (tidak tumpang tindih).
3. Peningkatan Δ = rasio sekarang − rasio sebelumnya, dalam poin persentase.
4. Syarat lolos: Δ > 0 **dan** net asing 5 sesi sekarang > 0.
5. Urutkan saham dari Δ terbesar.

**Contoh kecil (angka karangan)**

| Saham | Rasio 5 sesi lalu | Rasio sekarang | Δ | Lolos? |
|---|---:|---:|---:|---|
| X | −2% | +6% | +8 poin | Ya: asing net beli dan lebih banyak dari sebelumnya |
| Y | −10% | −2% | +8 poin | Tidak: Δ sama, tetapi asing masih net jual |
| Z | +12% | +13% | +1 poin | Lolos, tetapi naiknya kecil, peringkatnya rendah |

**Contoh nyata: BBCA** **[T]**

| Jendela | Net asing | Rasio |
|---|---:|---:|
| 5 sesi yang berakhir 26 Okt 2026 | −Rp2.145,5 miliar | −15,70% |
| 5 sesi yang berakhir 2 Nov 2026 (27 Okt – 2 Nov) | +Rp489,4 miliar | +5,57% |
| **Δ** | | **+21,27 poin** |

- BBCA lolos: asing net beli dan jauh lebih baik daripada sebelumnya. Di antara 379 saham net beli asing, Δ BBCA ada di
  **persentil 90,2**.
- **Δ besar di sini terutama karena periode sebelumnya sangat negatif.** BBCA "pulih dari jual besar", bukan "beli
  besar": net belinya sekarang hanya 5,6% dari transaksi.
- Net beli itu pun berasal dari satu hari: 28 Okt +Rp1.174,7 miliar, sedangkan empat hari lain net jual (−59,7;
  −503,5; −6,0; −116,1 miliar).
- **Syarat Δ > 0 saja tidak memilah:** 297 dari 379 saham net beli punya Δ > 0 (median Δ 3,9 poin; P90 20,5). Karena itu
  hasilnya harus diurutkan, bukan hanya disaring.

**Cara membaca:** makin besar Δ, makin kuat perubahan arus asing dibanding minggu sebelumnya. Baca bersama level
(rasio sekarang): Δ +21 dari rasio −15,7% berbeda dari Δ +21 dari rasio +10%.

**Yang tidak dijawab:** apakah net beli itu *besar* untuk saham ini (lihat `M-FF-HEAVY`); apakah harga akan naik
(belum diuji); dan Δ bergantung pada pembandingnya (periode sebelumnya yang sangat buruk membuat Δ tampak besar).

### Rincian teknis


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

### Penjelasan dan contoh (untuk pembaca)

**Intinya:** apakah net beli asing 5 sesi terakhir **luar biasa besar untuk saham ini sendiri**? Nilai Rupiah mentah
menyesatkan: Rp500 miliar itu biasa untuk BBCA tetapi luar biasa untuk saham kecil. Jadi nilai sekarang dibandingkan
dengan **252 nilai net-5-sesi sebelumnya milik saham yang sama** (kira-kira setahun). Hari ini tidak ikut dihitung.

**Dua ukuran "seberapa luar biasa"**
- **Persentil:** persentil 91 berarti net beli sekarang lebih besar dari 91% nilai riwayatnya.
- **z-score:** berapa simpangan baku di atas rata-rata riwayatnya; z ≥ 2 umumnya dianggap tidak biasa.

**Contoh kecil (angka karangan)** Saham A: net asing 5 sesi sekarang **+Rp360 miliar**. Dari 252 nilai riwayatnya,
rata-ratanya Rp50 miliar, simpangan bakunya Rp120 miliar, dan 230 nilai lebih kecil dari 360.
- Persentil = 230 ÷ 252 = **91,3**.
- z-score = (360 − 50) ÷ 120 = **2,58**.

Syarat tambahan agar bukan lonjakan satu hari: net beli di minimal 3 dari 5 sesi.
- Saham A: net beli di 4 dari 5 sesi, **lolos**.
- Saham B: angkanya sama (+Rp360 miliar), tetapi semuanya dari satu hari (transaksi blok), net beli di 1 dari 5 sesi,
  **ditolak**.

**Contoh nyata: BBCA, 5 sesi berakhir 2 Nov 2026** **[T]**

| Ukuran | BBCA | Ambang | Lolos? |
|---|---:|---:|---|
| Net asing 5 sesi | +Rp489,4 miliar | > 0 | Ya |
| Persentil 252 sesi | 84,1 | ≥ 90 | **Tidak** |
| z-score 252 sesi | 0,71 | ≥ 2 | **Tidak** |
| Sesi net beli dari 5 | 1 | ≥ 3 | **Tidak** |

Net beli BBCA positif dan naik (lolos `M-FF-INC`), tetapi **tidak heavy**: hanya lebih besar dari 84% riwayatnya sendiri
dan berasal dari satu hari saja. Ini contoh bahwa kedua entri menjawab pertanyaan yang berbeda.

**Gambaran seluruh pasar (2 Nov 2026, Regular):** dari 858 saham, 379 net beli; 75 punya persentil ≥ 90 (sekitar 84
saham akan lolos hanya karena peluang), 18 punya z ≥ 2. Dari 75 saham itu, 65 juga punya Δ > 0 (`M-FF-INC`).

**Cara membaca:** persentil tinggi berarti besar dibanding kebiasaan sendiri, bukan dibanding saham lain. Persentil 90
meloloskan "10% teratas", bukan "luar biasa"; untuk yang benar-benar tidak biasa pakai persentil 95 atau z ≥ 2.

**Yang tidak dijawab:** apakah net beli itu akan berlanjut atau diikuti kenaikan harga (belum diuji); jendela yang
tumpang tindih membuat nilai hari-hari berurutan tidak independen.

### Rincian teknis


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

### Penjelasan dan contoh (untuk pembaca)

**Intinya:** dalam 5 sesi, apakah segelintir broker membeli **jauh lebih banyak** daripada segelintir broker terbesar
yang menjual? Ini mengukur ketimpangan pihak-pihak terbesar di dua sisi, bukan total aliran.

**Langkahnya**
1. Per broker, jumlahkan net (beli − jual) selama 5 sesi.
2. B = jumlah net N pembeli net terbesar. S = jumlah (nilai positif dari) net N penjual net terbesar. N = 3 sebagai
   contoh.
3. Rasio = B ÷ S. Pendampingnya, imbalance = (B − S) ÷ (B + S), selalu antara −1 dan +1.

**Contoh kecil (angka karangan, miliar Rp)**

| | B (3 pembeli: 40, 30, 20) | S | Rasio B/S | Imbalance |
|---|---:|---|---:|---:|
| Penjual terbesar tersebar | 90 | 60 (25, 20, 15) | 1,50 | 0,20 |
| Penjual terbesar sangat kecil | 90 | 5 (3, 1, 1) | 18,0 | 0,89 |

Rasio meloncat dari 1,5 ke 18 hanya karena penyebutnya kecil. Imbalance tetap di bawah 1 dan lebih mudah dibaca.

**Contoh nyata: BBCA, 5 sesi (27 Okt – 2 Nov 2026), Regular** **[T]**

| Cakupan | Top 3 beli | Top 3 jual | Rasio | Imbalance |
|---|---:|---:|---:|---:|
| Semua investor | Rp1.149,0 miliar | Rp1.008,8 miliar | 1,14 | 0,07 |
| Hanya asing | Rp1.228,2 miliar | Rp727,7 miliar | 1,69 | 0,26 |

- Semua investor: hampir seimbang. Pembeli dan penjual terbesar sama-sama besar.
- Hanya asing: pembeli terbesar sekitar 1,7 kali penjual terbesar, jadi lebih timpang.
- Net asing totalnya Rp489,4 miliar, sama dengan `foreign_net_5d` di `Feature_06`, sehingga hitungannya konsisten.

**Cara membaca:** rasio > 1 (imbalance > 0) berarti pembeli terbesar lebih besar dari penjual terbesar. Untuk semua
investor, total net beli sama dengan total net jual, sehingga ukuran ini mengukur **konsentrasi**, bukan arah total.

**Yang tidak dijawab:** pada cakupan hanya-asing, 75% saham punya kurang dari 3 broker di salah satu sisi sehingga
top 3 tidak terdefinisi (lihat gerbang di Rincian teknis). Daya prediksi belum diuji.

### Rincian teknis


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
- **Sumber:** `IDX_Broker_Summary` (`"Date"`, `"Symbol"`, `"Broker"`, `"Investor Type"`, `"Market Board"`, `"Buy Value"`,
  `"Sell Value"`), dihitung sendiri di sandbox (prinsip 8): jumlahkan net per broker (dan per investor type bila cakupan
  asing) selama jendela, lalu ambil N terbesar tiap sisi. **[T]** `Feature_02.net_value_5d` adalah jalan pintas yang
  sama hasilnya; `Feature_03` hanya punya `top3_buyer_net_value` dan `top3_buyer_share` untuk 1 hari dan penjual hanya
  top 1, tanpa top 3 penjual. **[T]**
- **Gerbang wajib (temuan 2026-11-03, 5 sesi 27 Okt – 2 Nov, Regular):** top N hanya terdefinisi bila ada ≥ N broker
  net beli **dan** ≥ N broker net jual. **[T]**
  - Semua investor: 845 dari 872 saham memenuhi; imbalance ≥ 0,5 hanya 0,4% saham (P90 0,213). Median imbalance 0,016.
  - Hanya asing: 75% dari 797 saham punya < N=3 broker di salah satu sisi; imbalance jenuh di ±1 pada 31% saham
    (112 tanpa penjual net, 124 tanpa pembeli net). Dengan gerbang tersisa 199 saham; imbalance ≥ 0,5 masih 23,6%
    karena aktivitas asing terkonsentrasi di sedikit broker. Jadi cakupan hanya-asing butuh gerbang dan pembanding
    riwayat sendiri; angka mentahnya banyak mencerminkan struktur broker asing, bukan sinyal.
- **Biaya:** satu jendela 5 sesi lintas saham ±116 ribu baris, ±4 detik (terukur). Riwayat 252 sesi untuk persentil
  ±6 juta baris: lihat prinsip 8, perlu izin. **[D]**
- **Belum diuji:** apakah rasio timpang mendahului kenaikan harga.

---

## M-CR3X-NET — Konsentrasi pembeli net (atau penjual net): CR3 − 3/k_net

### Penjelasan dan contoh (untuk pembaca)

**Intinya:** dari seluruh net beli, berapa yang dipegang 3 pembeli terbesar, **dibandingkan dengan yang akan mereka
pegang jika semua pembeli berbagi rata**? Angka tinggi berarti pembelian bersih terpusat di sedikit broker.

**Mengapa dikurangi 3/k?** Makin banyak pembeli, makin kecil bagian 3 teratas secara otomatis. Membandingkan CR3 mentah
antar saham tidak adil.

| | Pembeli net (k) | Bagian merata 3/k | CR3 (nyata) | CR3 − 3/k |
|---|---:|---:|---:|---:|
| Saham X | 10 | 30,0% | 40% | **0,10** (hanya sedikit di atas merata) |
| Saham Y | 40 | 7,5% | 40% | **0,325** (jauh di atas merata) |

CR3 sama-sama 40%, tetapi pada Y tiga pembeli itu jauh lebih menonjol di antara 40 pembeli.

**Contoh nyata: BBCA, 5 sesi (27 Okt – 2 Nov 2026), Regular, semua investor** **[T]**
- 40 pembeli net membeli net total Rp1.623,1 miliar. Tiga terbesar: BK 498,2 + ZP 412,4 + YU 238,4 = **Rp1.149,0
  miliar**.
- CR3 = 1.149,0 ÷ 1.623,1 = 70,8%. Bagian merata = 3 ÷ 40 = 7,5%. Hasil = **0,633** (63,3 poin; 9,4 kali bagian
  merata).
- Pembeli ke-4 sampai ke-6 (AZ, AG, DX) hanya Rp58–92 miliar, jauh di bawah tiga teratas.
- Di antara 716 saham, BBCA persentil 70,5; di antara saham dengan jumlah pembeli mirip (28–62 pembeli net), persentil
  87,3.

**Cara membaca:** skala 0 (rata) sampai 1 − 3/k (maksimum; k = 40 → 0,925; k = 10 → 0,70). Makin tinggi, makin
terkonsentrasi. BBCA 0,633 adalah sekitar 68% dari maksimum untuk k = 40.

**Yang tidak dijawab:** **arah.** Sisi jual BBCA juga terkonsentrasi (0,553). Tidak membedakan satu broker dominan dari
tiga yang setara (pakai share top 1). Dan konsentrasi tinggi dengan intensitas net rendah, seperti BBCA (lihat
`M-NET-INTENSITY`), belum tentu akumulasi besar.

### Rincian teknis


**Ditambahkan atas permintaan user 2026-11-03:** "masukan Cr3 - 3/k_net dan CR3- 3/k_gross ke dalam MD".

**Pertanyaan yang dijawab:** seberapa terpusat net beli (atau net jual) di sedikit broker, setelah memperhitungkan
jumlah brokernya?

| Langkah | Definisi |
|---|---|
| Net per broker | (beli − jual) per broker selama jendela (bawaan 5 sesi); kedua Investor Type dijumlah dulu |
| Sisi | Pembeli net (net > 0) atau penjual net (\|net\| untuk net < 0); parameter `sisi` |
| k_net | Jumlah broker di sisi itu |
| CR3 | Jumlah 3 terbesar ÷ jumlah seluruh sisi itu |
| **Ukuran** | **CR3 − 3 ÷ k_net** |

- **Skala:** 0 (semua sama rata) sampai 1 − 3/k_net; tidak pernah negatif. Batas atas bergantung k (k = 40: 0,925;
  k = 10: 0,70). Makin tinggi, makin terkonsentrasi.
- **Bukan arah:** untuk semua investor total net beli selalu sama dengan total net jual. Nilai tinggi hanya berarti
  terpusat; sisi jual BBCA juga terkonsentrasi.
- **Parameter:** N = 3 (usulan), jendela 5 sesi, sisi beli atau jual, cakupan semua investor atau hanya asing.
- **Gerbang:** minimal 10 broker di sisi itu (**pilihan AI, bukan dari data; keputusan terbuka**). Pada jendela uji
  lolos 716 dari 872 simbol (sisi jual: 715).
- **Pembanding:** peringkat persentil antar saham pada tanggal yang sama; **usulan, belum diputuskan:** peringkat di dalam
  kelompok saham dengan jumlah broker yang mirip (lima kelompok sama besar; pada jendela uji 10–13, 14–17, 18–21,
  22–27, 28–62 pembeli net); riwayat sendiri 252 sesi (menunggu izin menarik data).
- **Sumber:** `IDX_Broker_Summary`, dihitung di sandbox (prinsip 8).

**Bukti (uji 2026-11-03; 716 saham, 5 sesi 27 Okt – 2 Nov, Regular, semua investor)** **[T]**
- Sebaran P10 / P50 / P90 = 0,40 / 0,56 / 0,72; bin terpadat 16,5% (10 bin sama lebar antara P1 dan P99).
- Korelasi peringkat dengan k_net: **−0,24** (CR3 mentah: −0,60). Dengan jumlah broker yang membeli (bruto): −0,03;
  dengan semua broker aktif: −0,02. Peringkat di dalam kelompok k: **−0,01**.
- Varian yang lebih buruk: baseline dengan k_gross atau k_active (−0,42 dan −0,46 terhadap k_net); versi
  dinormalisasi (CR3 − 3/k) ÷ (1 − 3/k) (−0,51). Sisa korelasi −0,24 belum diketahui penyebabnya (dugaan: baseline
  merata kurang cocok untuk pembeli nyata yang miring, atau struktur nyata).
- Sisi jual: P10 / P50 / P90 = 0,37 / 0,52 / 0,68, korelasi k −0,30. Korelasi peringkat sisi beli vs sisi jual
  **−0,05**: hampir independen.
- Keluarga konsentrasi pada dasarnya satu faktor: CR3, share top 1, dan CR3 − 3/k saling berkorelasi 0,83–0,93.
- **Contoh BBCA** (5 sesi): k = 40, CR3 = 1.149,0 ÷ 1.623,1 = 0,708 (BK 498,2; ZP 412,4; YU 238,4 miliar), baseline
  3/40 = 0,075, hasil **0,633** (63,3 poin; 9,4 kali bagian merata). Persentil 70,5 di 716 saham; 87,3 di kelompok k
  28–62 (126 saham; median kelompok 0,515, P90 0,647). Riwayat sendiri (hitungan 2026-11-03, `Feature_02`, 252 sesi):
  median 0,531, rentang 0,257–0,838, persentil 65,5. Sisi jual: k = 44, hasil 0,553.
- **Pasangan:** lihat `M-NET-INTENSITY` (entri sendiri, ditambahkan atas permintaan user 2026-11-03). BBCA:
  intensitas 18,5% (persentil 20,5), jadi konsentrasi tinggi tetapi porsi net kecil.

**Keterbatasan:** satu jendela; kestabilan peringkat dan daya prediksi belum diuji; hanya melihat 3 broker teratas, jadi
tidak membedakan satu broker dominan dari tiga yang setara (pakai share top 1).

## M-CR3X-GROSS — Konsentrasi beli bruto: CR3_gross − 3/k_gross

### Penjelasan dan contoh (untuk pembaca)

**Intinya:** bukan "siapa yang menumpuk posisi", tetapi **"siapa yang paling aktif membeli"**. Ukurannya memakai total
nilai beli setiap broker tanpa dikurangi penjualannya, lalu mengambil bagian tiga terbesar, dikurangi bagian merata
(3/k_gross).

**Mengapa dua ukuran (net dan gross)?** Broker yang membeli Rp300 miliar dan menjual Rp280 miliar tetap sangat aktif
(masuk tiga besar gross) tetapi nyaris tidak menumpuk apa pun (net hanya +Rp20 miliar).

**Contoh kecil (angka karangan, total beli saham = Rp1.000 miliar)**

| Broker | Beli | Jual | Net |
|---|---:|---:|---:|
| M1 | 300 | 280 | +20 |
| M2 | 250 | 260 | −10 |
| M3 | 200 | 190 | +10 |

Tiga broker ini memegang 75% dari seluruh pembelian (gross), tetapi net mereka hanya +Rp20 miliar. Gross tinggi, net
hampir nol: aktif, bukan menumpuk.

**Contoh nyata: BBCA, 5 sesi, Regular, semua investor** **[T]**
- Tiga pembeli bruto terbesar: BK Rp1.171,6; ZP Rp1.130,5; AK Rp890,8 miliar = **Rp3.192,8 miliar** dari total beli
  Rp8.783,4 miliar = **36,4%**. Ada 83 broker yang membeli, bagian merata 3/83 = 3,6%. Hasil = **0,327**.
- Persentil gross BBCA hanya **6,7** di antara 716 saham (versi net: 70,5): beli bruto BBCA tersebar dibanding saham
  lain, sementara beli bersihnya terkonsentrasi.
- Dari Rp3.192,8 miliar yang dibeli tiga broker itu, net hanya Rp765,4 miliar (24,0%). **AK ada di tiga besar gross,
  tetapi net jual Rp145,2 miliar.**

**Cara membaca:** nilai tinggi = pembelian didominasi sedikit broker besar. Bandingkan dengan versi net: net tinggi dan
gross rendah = beli bersih terpusat di tengah banyak peserta; keduanya tinggi = pusat pembelian dan aktivitas ada di
broker yang sama.

**Yang tidak dijawab:** gross lebih terpengaruh ukuran saham (korelasi −0,30) dan jumlah broker (−0,40) daripada net,
jadi harus diperingkat di dalam kelompok yang sebanding.

### Rincian teknis


**Ditambahkan atas permintaan user 2026-11-03** (kalimat yang sama dengan M-CR3X-NET).

**Pertanyaan yang dijawab:** seberapa terpusat **aktivitas** beli di sedikit broker (bukan posisi bersih)?

| Langkah | Definisi |
|---|---|
| Beli bruto per broker | Jumlah `Buy Value` per broker selama jendela, Investor Type dijumlah |
| k_gross | Jumlah broker dengan beli bruto > 0 |
| CR3_gross | Beli bruto 3 broker terbesar ÷ total beli bruto |
| **Ukuran** | **CR3_gross − 3 ÷ k_gross** |

- **Beda dengan net:** broker yang beli dan jual sama besar tetap masuk tiga besar. Gross mencerminkan siapa yang paling
  aktif, bukan siapa yang menumpuk posisi.
- **Gerbang:** sama dengan M-CR3X-NET (minimal 10 pembeli net) agar universe saham sama.
- **Pembanding:** wajib peringkat di dalam kelompok jumlah broker dan ukuran/likuiditas (lihat bukti).

**Bukti (uji 2026-11-03; sama dengan M-CR3X-NET)** **[T]**
- Sebaran P10 / P50 / P90 = 0,35 / 0,49 / 0,63; bin terpadat 17,0%.
- Korelasi peringkat dengan k_gross **−0,40** dan dengan ukuran (log nilai beli bruto) **−0,30**; versi net: −0,24 dan
  0,09. Jadi gross lebih terpengaruh jumlah broker dan likuiditas.
- Korelasi dengan versi net: **0,45** (bukan duplikat); dengan share broker terbesar (top 1 gross): 0,87.
- **Contoh BBCA** (5 sesi): 3 pembeli bruto terbesar BK 1.171,6; ZP 1.130,5; AK 890,8 = Rp3.192,8 miliar dari
  Rp8.783,4 miliar = 36,4%; k_gross = 83; baseline 3,6%; hasil **0,327**. Persentil **6,7** di 716 saham dan 14,4 di
  kelompok k_gross 48–83 (139 saham). Versi net BBCA persentil 70,5.
- Dari Rp3.192,8 miliar yang dibeli tiga broker itu, net hanya Rp765,4 miliar (24,0%); AK net jual Rp145,2 miliar.
- Ide belum diuji: net ÷ bruto dari 3 pembeli teratas sebagai ukuran keyakinan.

## M-NET-INTENSITY — Intensitas net beli

**Ditambahkan atas permintaan user 2026-11-03** (user menandai istilah ini dan meminta penjelasannya).

### Penjelasan dan contoh (untuk pembaca)

**Intinya:** dari setiap Rp100 yang dibeli di saham ini, **berapa yang benar-benar "bersih"**, yaitu tidak dibatalkan oleh
penjualan broker yang sama? Intensitas rendah berarti banyak pembelian dan penjualan bolak-balik di broker yang sama;
tinggi berarti pembelian cenderung searah.

**Langkahnya**
1. Per broker, jumlahkan net selama 5 sesi (beli − jual, kedua Investor Type dijumlah).
2. Jumlahkan net semua broker yang net-nya **positif** (total net beli).
3. Bagi dengan total nilai beli bruto semua broker.

Hasilnya sama dengan **1 − (volume yang dibeli sekaligus dijual oleh broker yang sama ÷ total beli)**.

**Contoh kecil (angka karangan, miliar Rp)** Dua saham dengan total beli sama, Rp190 miliar:

| Saham | Broker (beli / jual) | Total net beli | Intensitas |
|---|---|---:|---:|
| P (bolak-balik) | A 100/90, B 50/60, C 40/0, D 0/40 | 10 (A) + 40 (C) = **50** | 50 ÷ 190 = **26,3%** |
| Q (searah) | E 100/0, F 90/0, G 0/100, H 0/90 | 100 + 90 = **190** | 190 ÷ 190 = **100%** |

Pada P, Rp140 miliar (73,7%) dibeli oleh broker yang juga menjual, jadi saling menghapus. Pada Q, tidak ada yang
saling menghapus.

**Contoh nyata: BBCA, 5 sesi (27 Okt – 2 Nov 2026), Regular, semua investor** **[T]**
- Total net beli 40 pembeli net: **Rp1.623,1 miliar**. Total nilai beli bruto semua broker: **Rp8.783,4 miliar**.
- Intensitas = 1.623,1 ÷ 8.783,4 = **18,5%**. Artinya 81,5% dari nilai beli BBCA dibatalkan oleh penjualan broker yang
  sama.
- Di antara 716 saham, BBCA persentil **20,5** (rendah). Pembanding: ARKO 45,9% (persentil 79,3), BMRI 30,9% (persentil
  51,8).
- Sebaran 716 saham: median 30,3%, P10 12,7%, P90 56,7%.

**Cara membaca:** makin tinggi, makin sedikit pembelian yang "dibatalkan" oleh penjualan broker yang sama. BBCA memiliki
konsentrasi pembeli yang tinggi (`M-CR3X-NET` 0,633) tetapi intensitas rendah: sedikit broker memegang net beli, namun
net beli itu kecil dibanding total aktivitas.

**Yang tidak dijawab:**
- **Arah.** Untuk semua investor, total net beli sama dengan total net jual, jadi intensitas hanya mengukur seberapa
  "bersih" aliran, bukan apakah harga akan naik.
- **Level broker, bukan investor.** Dua klien dari broker yang sama, satu asing membeli dan satu domestik menjual,
  saling menghapus pada ukuran ini.
- Satu jendela; kestabilan dan daya prediksi belum diuji.

### Rincian teknis

- **Rumus:** intensitas = Σ net beli (broker net positif) ÷ Σ beli bruto semua broker; jendela 5 sesi; Regular; semua
  investor. **Gerbang:** sama dengan `M-CR3X-NET` (minimal 10 pembeli net).
- **Sumber:** `IDX_Broker_Summary` (`"Buy Value"`, `"Sell Value"`), dihitung di sandbox (prinsip 8). **[T]**
- **Bukti (716 saham, 5 sesi 27 Okt – 2 Nov 2026):** P10 / P50 / P90 = 0,127 / 0,303 / 0,567; bin terpadat 18,7%;
  korelasi peringkat dengan jumlah pembeli net −0,31 dan dengan ukuran saham −0,07; dengan konsentrasi: CR3 0,26,
  share top 1 0,19, CR3 − 3/k 0,16. Jadi intensitas hampir independen dari konsentrasi dan memberi informasi lain.
  **[T]**
- **Pembanding:** peringkat persentil antar saham pada tanggal yang sama; sebaiknya di dalam kelompok jumlah broker
  yang mirip (lihat `M-CR3X-NET`). Riwayat sendiri belum dihitung.
- **Gunakan bersama:** `M-CR3X-NET` (konsentrasi) dan `M-FF-HEAVY` (arah asing). Konsentrasi saja tidak cukup, karena
  broker yang saling menghapus tetap bisa tampak terkonsentrasi.

---

## M-HHI3-NETBUY dan M-HHI3-NETSELL — Porsi 3 teratas dari HHI sisi pembeli net / penjual net

### Penjelasan dan contoh (untuk pembaca)

**Intinya:** HHI adalah satu angka yang menggambarkan seberapa terpusat sebuah sisi: bobot tiap broker dikuadratkan lalu
dijumlah, sehingga broker besar sangat berpengaruh. Ukuran ini menjawab: **dari angka HHI sisi pembeli (atau penjual),
berapa persen berasal dari tiga broker terbesar?**

**Langkahnya**
1. Bobot tiap pembeli net = net-nya ÷ jumlah net semua pembeli net.
2. HHI sisi = jumlah semua bobot yang dikuadratkan.
3. Ukuran = jumlah kuadrat bobot 3 terbesar ÷ HHI sisi.

**Contoh kecil (angka karangan, 10 pembeli, tiga teratas memegang 60% dari net beli)**

| Susunan | Bobot tiga teratas | HHI sisi | Ukuran | Share broker terbesar |
|---|---|---:|---:|---:|
| Tiga setara | 20%, 20%, 20% | 0,143 | **0,840** | 20% |
| Satu paus | 40%, 10%, 10% | 0,203 | **0,887** | 40% |

Susunannya sangat berbeda (broker terbesar 20% lawan 40%), tetapi ukurannya hanya 0,840 lawan 0,887. Ukuran ini
cepat mendekati 1 dan kurang peka. Share broker terbesar membedakannya jelas (20% lawan 40%).

**Contoh nyata: BBCA, 5 sesi, Regular, semua investor** **[T]**
- Sisi beli (40 pembeli net): bobot BK 0,307, ZP 0,254, YU 0,147. Jumlah kuadratnya 0,1804, dari HHI sisi beli 0,1896.
  Ukuran = 0,1804 ÷ 0,1896 = **0,951**.
- Sisi jual (44 penjual net): **0,919**.

**Cara membaca:** mendekati 1 berarti hampir seluruh konsentrasi sisi itu berasal dari tiga broker teratas. Karena
hampir separuh saham bernilai di atas 0,95, angka ini kurang berguna untuk memilah saham.

**Yang tidak dijawab:** arah (sisi beli dan sisi jual dihitung terpisah), dan daya prediksi (belum diuji).
Rekomendasi AI: jangan dipakai sebagai penyaring tunggal.

### Rincian teknis


**Ditambahkan atas permintaan user 2026-11-03:** "HHI top 3 net dan HHI top 3 sell". **Tafsir AI** (dari diskusi
"top 3 HHI net share out of total HHI"): bila salah, user mengoreksi.

| Langkah | Definisi |
|---|---|
| Bobot | w_i = net_i ÷ jumlah net sisi itu (hanya pembeli net untuk `NETBUY`, hanya penjual net untuk `NETSELL`) |
| HHI sisi | H = Σ w_i² atas semua broker di sisi itu |
| **Ukuran** | **Σ w_i² (3 terbesar) ÷ H** |

- **Bukan** HHI yang dihitung dari tiga broker saja, dan **bukan** `broker_concentration_hhi` di `Feature_03` (itu
  memakai \|net\| gabungan pembeli dan penjual).
- **Rentang:** sekitar 3/k (semua sama besar) sampai 1.
- **Gerbang:** minimal 10 broker di sisi itu.

**Bukti dan peringatan (uji 2026-11-03; 5 sesi, Regular, semua investor)** **[T]**

| | Sisi beli (716 saham) | Sisi jual (715 saham) |
|---|---|---|
| P10 / P50 / P90 | 0,77 / 0,94 / 1,00 | 0,74 / 0,92 / 0,99 |
| Bin terpadat (10 bin, P1–P99) | **42,2%** | **35,7%** |
| Saham > 0,95 | 46,9% | 39,0% |
| Saham > 0,90 | 65,6% | 57,1% |
| Korelasi peringkat dengan CR3 | 0,95 | 0,95 |
| Korelasi peringkat dengan share top 1 | 0,92 | 0,92 |
| Korelasi peringkat dengan k | −0,45 | −0,47 |

- **Jenuh mendekati 1** dan sangat berkorelasi dengan CR3 dan share top 1, jadi sebagai penyaring antar saham
  daya pilahnya rendah. **Rekomendasi AI: jangan dipakai sebagai penyaring tunggal;** dicatat di kamus atas keputusan
  user.
- **Satu-satunya nilai tambah:** membedakan satu broker dominan dari tiga yang setara pada CR3 yang sama. Dari 68 saham
  ber-CR3 0,60–0,65: ARKO (broker terbesar 23%) = 0,78; BMRI (broker terbesar 46%) = 0,95. Share top 1 menangkap hal
  yang sama dengan lebih sederhana.
- Sisi beli dan sisi jual hampir independen (korelasi −0,06).
- **Contoh BBCA** (5 sesi): sisi beli **0,951** (k = 40): bobot BK 0,307, ZP 0,254, YU 0,147, Σ w² = 0,1804 dari H =
  0,1896. Sisi jual **0,919** (k = 44).

---

## Kombinasi (kerangka, belum diputuskan)

| Pertanyaan user | Kombinasi usulan | Status |
|---|---|---|
| "Saham yang foreign flow-nya naik 5 hari" | M-FF-INC | Usulan |
| "Saham dengan akumulasi heavy" | M-FF-HEAVY, atau M-FF-HEAVY **dan** M-TOPN-RATIO | Terbuka: satu daftar atau dua |
| "Pembelian terkonsentrasi di sedikit broker" (screener) | M-CR3X-NET (peringkat dalam kelompok jumlah broker); M-CR3X-GROSS sebagai konteks aktivitas; pasangan M-NET-INTENSITY | Usulan; M-HHI3-* tidak disarankan sebagai penyaring tunggal |
| "Indikator pre-rally" | Menunggu uji peristiwa | Belum ada |

## Kandidat entri dari riset 2026-11-03 (belum diminta masuk kamus)

**Pembaruan 2026-11-03:** entri `M-CR3X-NET`, `M-CR3X-GROSS`, `M-HHI3-NETBUY` dan `M-HHI3-NETSELL` sudah masuk
kamus atas permintaan user. Kandidat di bawah (`M-HHI` fitur, `M-TOP3-SHARE-TREND`) masih menunggu keputusan
(dibuang, diganti, atau dipertahankan).

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
