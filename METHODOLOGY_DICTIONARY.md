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
- **Pasangan yang disarankan AI (belum diputuskan):** intensitas net beli = Σ net beli ÷ Σ nilai beli bruto (median
  0,30; korelasi dengan konsentrasi 0,16–0,26). BBCA: 18,5% (persentil 20,5), artinya konsentrasi tinggi tetapi porsi net
  kecil.

**Keterbatasan:** satu jendela; kestabilan peringkat dan daya prediksi belum diuji; hanya melihat 3 broker teratas, jadi
tidak membedakan satu broker dominan dari tiga yang setara (pakai share top 1).

## M-CR3X-GROSS — Konsentrasi beli bruto: CR3_gross − 3/k_gross

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

## M-HHI3-NETBUY dan M-HHI3-NETSELL — Porsi 3 teratas dari HHI sisi pembeli net / penjual net

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
| "Pembelian terkonsentrasi di sedikit broker" (screener) | M-CR3X-NET (peringkat dalam kelompok jumlah broker); M-CR3X-GROSS sebagai konteks aktivitas; pasangan intensitas net beli | Usulan; M-HHI3-* tidak disarankan sebagai penyaring tunggal |
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
