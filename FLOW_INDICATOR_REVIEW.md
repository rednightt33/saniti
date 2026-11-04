# Tinjauan indikator Flow di BFF terminal

**Status:** dokumen kerja, dibuat 2026-11-04. Satu indikator sudah ditinjau (FL03); sisanya belum. Tidak ada keputusan
yang diambil dan tidak ada kode yang diubah.

**Tujuan (user 2026-11-04):** "Goalnya adalah apakah indikator ini perlu di eliminate, perlu di edit metric, visualnya
perlu diganti atau tidak." Bagian ini dibuat atas permintaan user: "create another section di REPO, which interkait
dengan indikator FLOW yang di display di BFF."

Dokumen ini adalah register tinjauan: untuk tiap indikator Flow ia mencatat apa indikator itu, buktinya pada data nyata,
dan pilihan keputusan. Keputusan akhir ada di user.

## Daftar to-do (catatan user)

Daftar ini mencatat apa yang ingin user lakukan kelak pada indikator Flow. Ini bukan jadwal dan bukan persetujuan eksekusi; tiap
item baru dijalankan atas perintah user.

| # | Indikator | To-do | Kata user | Status |
|---|---|---|---|---|
| 1 | FL07 Share · Market Volume | Pensiunkan atau sembunyikan dari menu | "Maaf, maksud saya FL07 yang di sembunyikan. Bukan FL17." (2026-11-04) | To-do, belum dijadwalkan. Kartu di bagian 5b |
| 2 | FL32 Transactions · Spike | Diedit **di tempat** (kode FL32 dipertahankan) menjadi "Activity Spike": parameter **Ukuran** (Transaksi, Nilai Rp, Lot) dan **Sisi** (Beli, Jual, atau Keduanya sebagai dua garis terpisah) | "P2 Ok tambahkan"; "P1 Pisahkan ... dipisahkan mana yang beli mana yang jual, per parameter"; "1. ya boleh" (pilihan Keduanya); "2. pertahankan di tempat" (2026-11-04) | To-do, belum dijadwalkan. Bagian 5c |
| 3 | Indikator baru: Spike Balance | Ditambahkan: lonjakan sisi beli dibagi lonjakan sisi jual untuk investor atau kelompok terpilih; **skala linear dengan garis netral 1** | "Spike balance OK tambahkan"; "3. skala garis netral 1" (2026-11-04) | To-do, belum dijadwalkan. Bagian 5c |

**Diusulkan, belum diputuskan user:** Participation Shift (FL36 dibanding riwayat sendiri), bagian 5c.4.

**Koreksi 2026-11-04:** sebelumnya item ini sempat tercatat salah untuk FL17 (commit `e8f4f21` dan `af2db50`, termasuk butir
`FLOW-RM-FL17` di `PLAN.md`). Penyebabnya salah ketik pada permintaan (tertulis FL17, yang dimaksud FL07); FL17 tidak ditinjau dan tetap "Belum ditinjau". Catatan FL17 dan butir
`PLAN.md` itu sudah dicabut di commit koreksi.

## 1. Di mana indikator Flow berada

| Apa | Lokasi |
|---|---|
| Daftar 39 indikator (FL01 sampai FL39): nama, keluarga, tempat, satuan, parameter dan bawaan | `apps/edge-bff/terminal/src/data/flowRegistry.json` |
| Rumus dan konvensi yang disepakati | `verification/terminal_api/flow_indicators/FORMULAS.md` |
| Hitungan (satu modul untuk Terminal, kelak Screener dan Backtest) | `apps/edge-bff/terminal/src/calc/flow.ts` |
| Penjelasan angka per indikator (kartu "i") | `apps/edge-bff/terminal/src/calc/explainFlowA.ts`, `src/data/indNotes.json` |
| Menu pemilih indikator (tabel NAME, GROUP, PLACE, UNIT) | `apps/edge-bff/terminal/src/app/indMenu.ts` |
| Pencocokan kode dengan spesifikasi | `verification/terminal_api/flow_indicators/CODE_INSPECTION_20261101.md`, `oracle/cases.json` |
| Uji | `apps/edge-bff/terminal/tests/calc/flow.test.ts` |

Registri berisi 39 indikator: 34 di panel sendiri, 3 di sumbu harga (overlay), 2 penanda di bawah candle. Keluarga: Share,
Transaction Size, Transactions, Concentration, Bandar Balance, Buy VWAP & Implied Cost, Net Flow, Other.

## 2. Kerangka tinjauan

Setiap indikator dinilai dengan enam pertanyaan:

| Kode | Pertanyaan |
|---|---|
| C1 | Apakah pertanyaan yang dijawabnya jelas bagi pembaca? |
| C2 | Apakah metriknya valid? Cari sirkularitas (cohort dipilih dari hal yang kemudian diukur), penyebut yang menyesatkan, papan yang dicampur |
| C3 | Apakah tumpang tindih dengan indikator lain? |
| C4 | Apakah bisa dibaca dari hari ke hari (identitas cohort stabil, ada pembanding)? |
| C5 | Apakah visualnya cocok (jenis garis, tempat, satuan, skala, tooltip)? |
| C6 | Apakah datanya cukup dan dapat diandalkan? |

Pilihan keputusan:

| Pilihan | Artinya |
|---|---|
| **Pertahankan** | Tidak diubah |
| **Edit metrik** | Rumus, bawaan parameter, atau cara memilih cohort diubah |
| **Ganti visual** | Rumus tetap; jenis plot, tempat, satuan, atau keterangan diubah |
| **Gabung** | Dilebur ke indikator lain (alias atau satu pilihan parameter) |
| **Hapus** | Dikeluarkan dari menu |

Aturan bukti: setiap temuan memuat angka yang diukur pada data, bukan kesan. Indikator dihitung ulang mengikuti
`FORMULAS.md` dari data broker; perbandingan dengan keluaran BFF yang hidup dicatat terpisah bila dilakukan.

## 3. Daftar indikator dan status tinjauan

Kolom "Keputusan user" dikosongkan untuk diisi.

| Id | Nama | Keluarga | Tempat | Satuan | Output | Status | Keputusan user | Catatan awal |
|---|---|---|---|---|---|---|---|---|
| FL01 | Transaction Size · Lot | Transaction Size | Panel | lot/tx | buy, sell | Belum ditinjau |  |  |
| FL02 | Transaction Size · Value | Transaction Size | Panel | IDR/tx | buy, sell | Belum ditinjau |  |  |
| FL03 | Share · Volume | Share | Panel | % | buy, sell | Sedang ditinjau |  | SEDANG DITINJAU (kartu di bagian 5) |
| FL04 | Share · Transactions | Share | Panel | % | buy, sell | Belum ditinjau |  | Saudara FL03 (porsi transaksi); kemungkinan menanggung temuan F1 dan F3 yang sama, belum diukur |
| FL05 | Transaction Size · vs Market | Transaction Size | Panel | x | buy, sell | Belum ditinjau |  |  |
| FL06 | Transaction Size · Buy/Sell Ratio | Transaction Size | Panel | x | ratio | Belum ditinjau |  |  |
| FL07 | Share · Market Volume | Share | Panel | % | value | To-do: pensiunkan atau sembunyikan | Pensiunkan atau hide (2026-11-04, to-do) | Kartu di bagian 5b. Identik dengan garis Buy FL03 pada bawaan; fungsi hitungnya dipakai FL09 |
| FL08 | Transaction Size · Percentile | Transaction Size | Panel | 0-100 | value | Belum ditinjau |  |  |
| FL09 | Block Money Candidate | Other | Penanda di bawah candle | flag | value | Belum ditinjau |  |  |
| FL10 | Transactions · Buy/Sell Imbalance | Transactions | Panel | -1..1 | value | Belum ditinjau |  |  |
| FL11 | Net Flow / Turnover Ratio | Net Flow | Panel | % | value | Belum ditinjau |  |  |
| FL12 | Net Buy Persistence · Cohort | Net Flow | Panel | % | value | Belum ditinjau |  |  |
| FL13 | Concentration HHI · Gross | Concentration | Panel | 0-1 | buy, sell | Belum ditinjau |  |  |
| FL14 | Concentration HHI · Buy − Sell | Concentration | Panel | diff | asym | Belum ditinjau |  |  |
| FL15 | Concentration Top-N · Gross Buy | Concentration | Panel | % | value | Belum ditinjau |  |  |
| FL16 | Concentration Top-N · Net Buy | Concentration | Panel | % | value | Belum ditinjau |  |  |
| FL17 | Buy VWAP · Rolling | Buy VWAP & Implied Cost | Overlay harga | price | value | Belum ditinjau |  |  |
| FL18 | Buy VWAP · Anchored | Buy VWAP & Implied Cost | Overlay harga | price | value | Belum ditinjau |  |  |
| FL19 | Implied Cost · Anchored | Buy VWAP & Implied Cost | Overlay harga | price | value | Belum ditinjau |  |  |
| FL20 | Implied Cost · Distance % | Buy VWAP & Implied Cost | Panel | % | value | Belum ditinjau |  |  |
| FL21 | Net Flow Percentile · vs Turnover | Net Flow | Panel | 0-100 | value | Belum ditinjau |  |  |
| FL22 | Broker Buy Breadth | Other | Panel | % | value | Belum ditinjau |  |  |
| FL23 | Broker Inventory | Other | Panel | lot|IDR | lines, total | Belum ditinjau |  |  |
| FL24 | Bandar Balance · % | Bandar Balance | Panel | % | value | Belum ditinjau |  |  |
| FL25 | Bandar Balance · Rupiah | Bandar Balance | Panel | IDR | value | Belum ditinjau |  |  |
| FL26 | Net Flow Streak | Net Flow | Panel | days | value | Belum ditinjau |  |  |
| FL27 | Silent Accumulation | Other | Penanda di bawah candle | flag | value | Belum ditinjau |  |  |
| FL28 | Average Daily Value | Other | Panel | IDR | value | Belum ditinjau |  |  |
| FL29 | Bandar Balance · Accumulation Days | Bandar Balance | Panel | % | value | Belum ditinjau |  |  |
| FL30 | Crossing Share | Other | Panel | % | value | Belum ditinjau |  |  |
| FL31 | Insider Net Change | Other | Panel | IDR | value | Belum ditinjau |  |  |
| FL32 | Transactions · Spike | Transactions | Panel | x | value | To-do: diedit di tempat menjadi Activity Spike | P1 dan P2 disetujui; di tempat; "Keduanya" disediakan (2026-11-04) | Kartu di bagian 5c; hanya sisi beli dan jumlah transaksi saat ini |
| FL33 | Transaction Size · Change % | Transaction Size | Panel | % | value | Belum ditinjau |  |  |
| FL34 | Institutional vs Retail Net | Other | Panel | % | value | Belum ditinjau |  |  |
| FL35 | Net Buy Persistence · Top Buyer | Net Flow | Panel | % | value | Belum ditinjau |  |  |
| FL36 | Share · Market Value (Buy + Sell) | Share | Panel | % | value | Belum ditinjau |  | Bawaan Top-N asing, bukan partisipasi asing seluruh broker: BBRI 3 Nov 0,26% lawan 41,49% (pilihan cakupan Semua broker) |
| FL37 | Net Flow Percentile · Rupiah | Net Flow | Panel | 0-100 | value | Belum ditinjau |  |  |
| FL38 | Concentration HHI · Net Buy | Concentration | Panel | 0-1 | value | Belum ditinjau |  |  |
| FL39 | Buy VWAP · Rolling · Distance % | Buy VWAP & Implied Cost | Panel | % | value | Belum ditinjau |  |  |

## 4. Cara membaca baris di menu indikator (tangkapan layar user 2026-11-04)

Tangkapan layar berasal dari menu "Indicators" (`indMenu.ts`). Contoh baris FL03:

| Elemen | Arti |
|---|---|
| Bintang (☆) | Tombol favorit. Menyimpan indikator ke daftar "Favorites" (disimpan di browser pengguna) |
| **Share · Volume** | Nama indikator |
| **FL03** (kecil) | Kode indikator |
| **1 on chart** (lencana) | Jumlah salinan indikator ini yang sedang tampil di grafik. Muncul hanya bila minimal satu |
| **Flow · Share** (GROUP) | "Flow" = jenis indikator (bukan Technical); "Share" = keluarga di registri |
| **Panel** (PLACE) | Digambar di panel sendiri di bawah grafik harga. Pilihan lain "Overlay" (di sumbu harga atau penanda di bawah candle) |
| **%** (UNIT) | Satuan nilai yang digambar |
| Tombol **i** | Membuka kartu penjelasan indikator, dengan cara kerja dan contoh |
| Tooltip saat hover | "Porsi lot beli (atau jual) yang berasal dari broker atau kelompok broker yang dipilih, dibanding semua broker." |

## 5. Kartu tinjauan: FL03 Share · Volume

### 5.1 Apa indikator ini

FL03 mengukur **porsi volume (lot)** yang berasal dari sekelompok broker dibanding seluruh broker pada saham itu, di
filter papan dan investor yang sama. Ada dua garis: porsi lot **beli** dan porsi lot **jual** kelompok itu.

Rumus (`FORMULAS.md`, `flow.ts:365`): Buy = `100 × BL(C) / BL(A)`; Sell = `100 × SL(C) / SL(A)`.
- `C` = kelompok broker (cohort) pada candle itu; `A` = semua broker dengan filter yang sama.
- `BL`, `SL` = jumlah lot beli, jual (1 lot = 100 saham) pada jendela `W` yang berakhir di candle itu.
- Kosong (null), bukan 0, bila penyebutnya 0 atau candle tidak punya data broker.

Parameter dan bawaan (`flowRegistry.json`):

| Parameter | Bawaan |
|---|---|
| Kelompok (`scope`) | Top-N cohort (alternatif: broker yang dipilih) |
| N (`top`) | 3 |
| Peringkat Top-N menurut (`rank`) | Net beli (Rp); alternatif beli bruto, net jual |
| Peringkat | Dihitung ulang tiap hari |
| Papan (`boards`) | Regular, Nego, Cash (semua) |
| Investor | Foreign dan Domestic (semua) |
| Sisi (`side`) | Buy (alternatif Sell, Both) |
| Jendela (`window`) | 1 (harian); 1 sampai 250 |

Aturan Top-N: di tiap candle, broker diurutkan menurut skor di jendela itu (net beli = Σ(beli − jual) dalam nilai);
hanya broker berskor > 0 yang layak; N tertinggi diambil (seri: kode broker A–Z).

### 5.2 Contoh nyata: BBRI, pengaturan bawaan **[T]**

Dihitung ulang dari `Feature_02_Broker_Rolling` (semua papan, semua investor, jendela 1).

3 Nov 2026: total lot beli semua broker 3.195.143 (sama dengan total lot jual).

| Broker (Top-3 net beli) | Lot beli | % dari semua beli | Lot jual | % dari semua jual | Net (Rp miliar) |
|---|---:|---:|---:|---:|---:|
| OD | 458.508 | 14,4% | 49.491 | 1,5% | +111,6 |
| CC | 511.052 | 16,0% | 240.087 | 7,5% | +73,2 |
| YP | 196.874 | 6,2% | 77.921 | 2,4% | +32,3 |
| **FL03** | | **Buy 36,5%** | | **Sell 11,5%** | |

Sepuluh sesi terakhir (cohort berganti hampir tiap hari):

| Tanggal | Cohort | Buy% | Sell% |
|---|---|---:|---:|
| 21 Okt | OD, BK, NI | 32,5 | 10,3 |
| 22 Okt | NI, BB, AK | 47,2 | 10,0 |
| 23 Okt | CC, IF, KZ | 57,5 | 10,0 |
| 26 Okt | NI, YU, YP | 55,9 | 10,7 |
| 27 Okt | OD, AK, CC | 43,2 | 22,3 |
| 28 Okt | DX, LG, ZP | 26,6 | 7,0 |
| 29 Okt | XL, OD, CC | 31,6 | 14,4 |
| 30 Okt | AK, LG, MG | 29,2 | 11,3 |
| 2 Nov | ZP, BK, XL | 43,5 | 16,3 |
| 3 Nov | OD, CC, YP | 36,5 | 11,5 |

Sebaran 252 sesi terakhir (jendela 1): Buy% min 15,7, P10 23,6, median 33,9, P90 51,8, maks 72,6. Sell% min 1,0, P10 5,2,
median 11,2, P90 21,4, maks 45,8. Jendela 5 sesi: Buy% P10 18,0, median 26,8, P90 40,7.

### 5.3 Temuan

| Kode | Temuan | Bukti | Kriteria |
|---|---|---|---|
| F1 | **Sirkularitas:** cohort dipilih dari net beli pada jendela yang sama dengan yang diukur, jadi garis Buy selalu di atas garis Sell | Buy% > Sell% pada **252 dari 252** sesi. Dengan peringkat "net jual", Sell% > Buy% pada 252 dari 252 sesi (Sell median 41,2%, Buy 13,6%). Selisih Buy − Sell tidak bisa menunjukkan cohort yang justru menjual | C2 |
| F2 | **Level tinggi karena seleksi:** tiga broker teratas menurut net beli otomatis besar | Tiga broker acak (yang membeli hari itu) rata-rata memegang 4,7% lot beli; FL03 Buy median 33,9% | C2, C4 |
| F3 | **Identitas cohort berganti:** garis menghubungkan kelompok yang berbeda tiap hari | Rata-rata hanya 0,94 dari 3 broker sama dengan hari sebelumnya; 31% hari tidak ada yang sama | C4 |
| F4 | **Tumpang tindih dengan FL07:** pada pengaturan bawaan keduanya identik | FL07 memakai penyebut "papan, semua investor"; FL03 memakai filter yang sama dan investor bawaan = semua. FL07 sama dengan garis Buy FL03; FL03 hanya menambah garis Sell. Dengan `denom = filter`, FL07 = FL03 | C3 |
| F5 | **Papan Nego dan Cash:** dimasukkan secara bawaan | |Buy% semua papan − hanya Regular|: rata-rata 1,81 poin, maks 14,7 poin, > 5 poin pada 26 dari 252 hari; cohort sama pada 99% hari | C2 |
| F6 | **Visual:** dua garis % di satu panel tanpa identitas cohort dan tanpa pembanding (garis acuan) | Kartu "i" dan tooltip tidak menyebut siapa cohort hari itu. Korelasi Buy% dan Sell% 0,63 (keduanya bergerak bersama volume) | C5 |
| F7 | **Kode FL03 ganda di dua sistem** | Di screener (`screener-metrics.json`, `verification/screener/AUDIT.md`) "FL03" adalah *Foreign participation* (% nilai transaksi); di terminal "FL03" adalah Share · Volume. Lihat bagian 6 | C1 |

### 5.4 Pilihan keputusan untuk FL03

| Pilihan | Isi | Dampak |
|---|---|---|
| Pertahankan | Tidak diubah | F1 sampai F3 tetap; garis Buy > Sell selalu |
| **Edit metrik (a)** | Cohort dipilih dari jendela **sebelumnya** (t−W sampai t−1), lalu porsinya diukur pada jendela sekarang | Menghilangkan sirkularitas; Sell bisa melebihi Buy; mengukur kelanjutan peran broker yang sudah net beli |
| Edit metrik (b) | Cohort tetap sepanjang periode (seperti FL18 sampai FL20) | Identitas stabil (F3 hilang); tetapi cohort melihat data setelah t, tidak boleh dibaca sebagai diketahui pada t (catatan di `FORMULAS.md`) |
| Edit metrik (c) | Bawaan papan menjadi Regular saja | Menghilangkan efek F5 pada hari blok Nego |
| **Ganti visual** | Tampilkan selisih Buy − Sell sebagai histogram, tambahkan garis acuan tiga broker acak, dan tampilkan nama cohort saat hover | Mengurangi salah baca F1 dan F6 |
| Gabung | FL07 dilebur ke FL03 (alias atau satu pilihan penyebut) | Menghilangkan F4 |
| Hapus FL03 | Dikeluarkan dari menu | Hanya bila FL07 dan FL04 dinilai cukup |

### 5.5 Usulan sementara AI (menunggu keputusan user)

Jangan dihapus. Metrik dan visual perlu diubah: **Edit metrik (a)** untuk menghilangkan sirkularitas, **Edit metrik (c)** untuk
papan Regular, **Ganti visual** (selisih Buy − Sell, garis acuan acak, nama cohort), dan **Gabung** FL07 ke FL03. Alasan:
pertanyaan yang dijawabnya (seberapa dominan broker teratas dalam volume) masuk akal untuk pembaca, tetapi bentuk
sekarang memberi angka yang sebagian besar ditentukan oleh cara memilih cohort.

### 5.6 Keputusan yang dibutuhkan

1. Pilihan untuk FL03: pertahankan, edit metrik (a), (b), atau (c), ganti visual, gabung dengan FL07, atau hapus.
2. Apakah FL07 dilebur ke FL03 atau tetap.
3. Bawaan papan: semua papan atau Regular saja.
4. Apakah FL04 (porsi transaksi) ikut ditinjau dengan cara yang sama.
5. Penomoran: satu sistem kode FL untuk terminal dan screener (bagian 6).

### 5.7 Batas verifikasi

- Dihitung ulang dari `Feature_02_Broker_Rolling` mengikuti `FORMULAS.md`, **belum dibandingkan** dengan angka yang tampil
  di BFF yang hidup. Pencocokan kode terhadap spesifikasi sudah ada di `CODE_INSPECTION_20261101.md` ("Cocok").
- Satu saham (BBRI), satu tahun (2025-08-01 sampai 2026-11-03), bawaan parameter. Temuan lain (F1) bersifat struktural
  dan berlaku pada saham mana pun yang memakai Top-N menurut net beli; F2, F3, F5 angkanya khusus BBRI.
- Belum diukur: seberapa sering pengguna memakai bawaan Top-3 dan seberapa sering mengganti `scope` ke broker pilihan.

## 5b. Kartu: FL07 Share · Market Volume (to-do: pensiunkan atau sembunyikan)

**Catatan user 2026-11-04 (kata-katanya):** "Pensiunkan saja, atau hide." lalu "Maaf, maksud saya FL07 yang di sembunyikan. Bukan
FL17. Ini hanya semacam to do list saja, jadi tolong diupdate di flow indicator review." Jadi ini item to-do, bukan
jadwal eksekusi: belum ada tanggal dan belum ada perintah "go". Alasan belum disebut user dan tidak ditulis di sini.

### 5b.1 Apa indikator ini

FL07 menghitung porsi **lot beli bruto** kelompok broker terhadap volume beli saham.
- Rumus (`FORMULAS.md`): `100 × BL(C) / BL(A)`. Pembilang sama dengan FL03. Penyebut `A` bawaan: lot beli semua broker dengan
  **filter papan saja** (semua investor); pilihan `denom = filter` memakai filter papan dan investor.
- Kelompok bawaan: Top-3 net beli, dihitung ulang tiap hari. Bawaan: semua papan, semua investor, jendela 1. Satu garis (beli).
- Kode: `apps/edge-bff/terminal/src/calc/flow.ts:382`, fungsi `marketShare` di baris 279.

### 5b.2 Hubungan dengan FL03 (terukur pada BBRI)

- Pada bawaan (investor = semua), FL07 identik dengan garis Buy FL03 (sama persis pada 5 sesi: 26,56; 31,61; 29,17; 43,47; 36,51%).
- Berbeda bila filter investor dipersempit. BBRI 3 Nov, investor = asing saja: FL03 = **47,85%** (lot beli kelompok dibagi lot beli
  asing semua broker) dan FL07 bawaan = **8,70%** (dibagi lot beli semua investor).

### 5b.3 Fakta untuk pelaksanaan (terverifikasi dengan pembacaan kode dan pencarian di repo, 2026-11-04)

- **FL09 (Block Money Candidate) memakai `marketShare`** dengan penyebut papan (`flow.ts:386`). Entri FL07 boleh disembunyikan atau
  dikeluarkan, tetapi fungsi hitungnya harus tetap ada. Penjelasan angka FL07 juga berbagi pembantu penyebut dengan FL11
  (`explainFlowA.ts:320`), dan rumus FL09 di dokumen menyebut FL07.
- **Keputusan lama di spesifikasi:** lembar "Keputusan" (`build_spec_workbook.py:257`): "FL07: Tetap terpisah dari FL03. —
  2. Tetap pisah dulu". To-do ini meninjau ulang keputusan itu.
- **Kemampuan yang hilang** bila FL07 tidak ditawarkan: tampilan "porsi kelompok terhadap *seluruh volume saham*" dengan filter
  investor dipersempit (contoh asing 8,70% di atas). FL03 tidak punya pilihan penyebut. Bisa dipertahankan bila FL03 diberi
  pilihan penyebut seperti FL07 (jalur gabung).
- **Belum ada mekanisme "sembunyikan":** tiap indikator di registri hanya punya `family`, `id`, `name`, `needs_frequency`,
  `outputs`, `params`, `place`, `tip`, `unit`. Registri dihasilkan (`scripts/build_flow_registry.py` dari
  `FLOW_INDICATORS_SPEC.xlsx`, yang dibuat `build_spec_workbook.py`).
- **Indikator pengguna disimpan di browser** (`ml.ind.v1`, `indicators.ts:218`). Entri yang kodenya tidak ada di registri
  **dibuang diam-diam** saat dimuat (`indicators.ts:746`, `add()` mengembalikan kosong bila definisi tidak ditemukan).

### 5b.4 Pilihan jalur

| | Sembunyikan (hide) | Pensiunkan (retire) | Gabung ke FL03 |
|---|---|---|---|
| Isi | Definisi tetap ada; menu tidak menawarkannya | Dikeluarkan dari registri, uji, oracle, dokumen | FL03 diberi pilihan penyebut; FL07 dilebur |
| FL07 yang sudah dipasang pengguna | Tetap tergambar | Hilang diam-diam saat dimuat | Perlu pemetaan ke FL03 |
| FL09 dan `marketShare` | Tidak tersentuh | Fungsi dipertahankan | Fungsi dipertahankan |
| Perlu dibuat baru | Mekanisme sembunyikan (generator, registri, penyaring menu, uji) | Tidak ada | Pilihan penyebut di FL03 |
| Kemampuan penyebut papan-saja | Hilang dari menu | Hilang | **Tetap ada** |

**Usulan sementara AI (menunggu pilihan user):** sembunyikan dulu (tidak membuang grafik pengguna), dan beri FL03 pilihan penyebut
hanya bila tampilan "seluruh volume saham" memang masih dibutuhkan.

### 5b.5 Daftar yang menyentuh FL07 (untuk jalur pensiun penuh)

| Lokasi | Isi | Tindakan |
|---|---|---|
| `build_spec_workbook.py` (baris 46, 128, 257, 401) dan `FLOW_INDICATORS_SPEC.xlsx` | Baris spesifikasi FL07; keputusan "tetap pisah"; catatan FL36 yang membandingkan dengan FL07 | Hapus baris FL07, perbarui keputusan dan catatan FL36, bangkitkan ulang |
| `scripts/build_flow_registry.py` (baris 165), `flowRegistry.json` (baris 834) | Tip dan entri FL07 | Hapus di generator, bangkitkan ulang registri |
| `indNotes.json` (baris 515; baris 526 menyebut FL07 di rumus FL09) | Catatan indikator | Hapus entri FL07; teks rumus FL09 dijaga |
| `flow.ts` (baris 382 dan fungsi `marketShare` baris 279) | Entri dan fungsi hitung | Hapus entri; **pertahankan `marketShare`** (dipakai FL09) |
| `explainFlowA.ts` (baris 320, 362 sampai 363, 411) | Penjelasan angka FL07; pembantu penyebut dibagi dengan FL11; teks FL09 | Hapus penjelasan FL07; pertahankan pembantu |
| `flow.test.ts` (baris 55 sampai 59), `explain_flowA.test.ts` (baris 45) | Uji FL07 | Pindahkan ke FL09 atau FL03, atau hapus |
| `oracle/cases.json` (baris 410, 431, 454), `oracle/oracle.py` (baris 414) | Tiga kasus oracle FL07; hitungan FL07 di oracle dipakai untuk FL09 | Hapus kasus; **pertahankan hitungan** untuk FL09 |
| `FORMULAS.md` (baris 73; baris 75 FL09 menyebut FL07) | Rumus | Hapus baris FL07; jaga rumus FL09 |
| `CODE_INSPECTION_20261101.md` dan `.json`; `build_final_workbook.py` (baris 257, komentar); `indicator_cards/flow_audit/*` | Pencocokan kode, kartu audit, hasil pembangkitan | Bangkitkan ulang atau tandai riwayat |

Untuk jalur sembunyikan daftar sentuhnya jauh lebih kecil: generator dan registri (penanda), penyaring menu di `indMenu.ts`, dan
uji menu.

### 5b.6 Pertanyaan terbuka (saat to-do ini diambil)

1. Sembunyikan, pensiunkan penuh, atau gabung ke FL03?
2. Bila disembunyikan atau dipensiunkan, apakah tampilan "porsi terhadap seluruh volume saham" masih dibutuhkan (pilihan penyebut di FL03)?
3. Kode FL07 tidak dipakai ulang dan tanpa penomoran ulang (usulan, lihat bagian 6).

### 5b.7 Batas

Daftar di atas hasil pencarian teks `FL07` di repo (tanpa `node_modules`); referensi yang tidak menyebut kodenya secara harfiah tidak
terdeteksi. Perilaku penyimpanan indikator dibaca dari `indicators.ts`, belum diuji di browser. Tidak ada kode yang diubah.

## 5c. To-do: Activity Spike (edit FL32) dan Spike Balance (baru)

**Catatan user 2026-11-04 (kata-katanya):** "P2 Ok tambahkan", "P1 Pisahkan", "Spike balance OK tambahkan", lalu "Jadi ini adalah
indikator2 yang nanti akan ditambahkan/ di edit. Saat ini tolong dimasukan ke flow indicator review." Ini daftar to-do, bukan
jadwal eksekusi: belum ada tanggal dan belum ada perintah "go".

### 5c.1 Kondisi sekarang: FL32 Transactions · Spike

- Rumus (`FORMULAS.md`): `BF_t(A) / mean(BF_k(A), k = t − baseline .. t − 1)`. `BF` adalah **jumlah transaksi beli** (`buy_freq`),
  `A` adalah semua broker dengan filter papan dan investor. Satuan "x", bawaan baseline 20 sesi, garis acuan 2,5.
- Hanya sisi beli, hanya jumlah transaksi (gross, tidak dikurangi transaksi jual), tanpa parameter sisi atau ukuran.
- Kode: `apps/edge-bff/terminal/src/calc/flow.ts:501`.
- **Untuk semua investor, jumlah transaksi beli selalu sama dengan transaksi jual** (BBRI 3 Nov: 67.211 lawan 67.211; korelasi
  lonjakan beli–jual 1,00). Satu sisi baru menjadi masalah bila filter investor atau kelompok dipakai.

### 5c.2 To-do 2: Activity Spike (FL32 diedit)

| Parameter | Isi |
|---|---|
| **Ukuran** (baru) | **Transaksi** (jumlah, seperti FL32 sekarang), **Nilai (Rp)**, atau **Lot** |
| **Sisi** (baru) | **Beli**, **Jual**, atau **Keduanya**: dipisahkan per parameter, tidak dijumlah. "Keduanya" menggambar dua garis terpisah (diputuskan user 2026-11-04) |
| Baseline | Sesi sebelum hari ini (bawaan 20; user memakai 5; 1 sampai 250) |
| Papan, Investor, Garis acuan | Tetap seperti FL32 |

Rumus: `X_t(A) / mean(X_k(A), k = t − baseline .. t − 1)` dengan `X` = `BF` atau `SF` (Transaksi), `BV` atau `SV` (Nilai), `BL` atau `SL`
(Lot), menurut Ukuran dan Sisi. Kosong bila baseline tidak penuh; aturan data frekuensi (`bf`/`sf`) hanya berlaku untuk Ukuran
Transaksi.

**Mengapa dua parameter:**
- *Ukuran:* lonjakan jumlah dan lonjakan nilai berbeda. BBRI 3 Nov, semua investor: jumlah 1,48× tetapi nilai 1,02× (banyak
  transaksi kecil). Korelasi lonjakan jumlah dan nilai 0,81 pada 252 sesi; 2 dari 10 hari jumlah ≥ 2× nilainya < 1,5×.
- *Sisi:* sisi jual dan beli bisa bercerita berlawanan.

**Bukti BBRI per 3 Nov 2026, baseline 5 sesi** (data `Feature_05`, semua papan):

| Investor | Transaksi beli | Transaksi jual | Nilai beli | Nilai jual |
|---|---:|---:|---:|---:|
| Asing | **0,39×** | **1,85×** | 0,47× | 1,16× |
| Domestik | 1,80× | 1,22× | 1,38× | 0,90× |
| Semua | 1,48× | 1,48× | 1,02× | 1,02× |

FL32 sekarang untuk asing hanya menampilkan 0,39× ("sepi"), padahal transaksi jual asing melonjak 1,85×. Selama 252 sesi, lonjakan beli
dan jual asing hampir tidak berkorelasi (−0,01), dan ada 4 hari ketika hanya sisi jual melonjak (jual ≥ 2,5× dan beli < 1,5×). Pada
domestik korelasinya 0,79.

**Fakta pelaksanaan (dibaca dari kode, belum diuji di browser):**
- Pola parameter sisi sudah ada (`sided()` di `flow.ts:241`, dipakai FL01 sampai FL05): sisi beli, sisi jual, atau "both" yang
  menggambar dua garis terpisah, tidak dijumlah.
- Indikator tersimpan di browser mengisi parameter yang hilang dengan bawaan registri (`indicators.ts:231`). Bila bawaan baru
  dibuat `Ukuran = Transaksi` dan `Sisi = Beli`, FL32 yang sudah dipasang tetap berperilaku sama.
- Registri dihasilkan dari spesifikasi (`build_spec_workbook.py`, lalu `build_flow_registry.py`), jadi perubahan parameter harus lewat
  generator dan dibangkitkan ulang.

**Keputusan user 2026-11-04 (kata-katanya):** "1. ya boleh" (pilihan "Keduanya" disediakan) dan "2. pertahankan di tempat" (FL32 diedit di
tempat: kode FL32 dipertahankan, nama diganti "Activity Spike", sehingga grafik tersimpan tidak terputus dan penomoran tidak berubah).

**Pertanyaan yang masih terbuka:**
1. Keluaran FL32 sekarang satu garis `value`; pola sisi memakai keluaran `buy` dan `sell`. Perlu diputuskan penanganan gaya garis
   tersimpan (warna dan ketebalan) saat keluaran berubah.
2. Bawaan baseline untuk Activity Spike (FL32 sekarang 20 sesi; user memakai 5).

### 5c.3 To-do 3: Spike Balance (indikator baru)

- **Isi:** lonjakan sisi beli dibagi lonjakan sisi jual untuk investor atau kelompok terpilih:
  `(X_t^beli / mean(X^beli)) / (X_t^jual / mean(X^jual))` dengan ukuran dan baseline yang sama. Lebih dari 1: sisi beli relatif lebih
  menonjol; kurang dari 1: sisi jual.
- **Hanya bermakna dengan filter.** Untuk semua investor rasionya selalu 1 (jumlah transaksi, nilai, dan lot beli sama dengan jual).
  Dengan filter asing atau domestik, atau kelompok broker, rasionya informatif.
- **Contoh BBRI, asing, transaksi, baseline 5:** 3 Nov = 0,39 ÷ 1,85 = **0,21**. Sebaran 252 sesi: P10 0,34, median 1,01, P90 3,05;
  nilai 3 Nov di persentil 3. Lima sesi terakhir: 27 Okt 1,32; 28 Okt 2,09; 29 Okt 0,56; 30 Okt 0,91; 2 Nov 1,17; 3 Nov 0,21.
- **Keputusan user 2026-11-04:** "3. skala garis netral 1": skala **linear** dengan garis netral di **1**.
- **Pertanyaan yang masih terbuka:** garis acuan lain (usulan 0,5 dan 2), ukuran bawaan, dan apakah cakupan kelompok broker (Top-N) ikut
  ditawarkan atau hanya filter investor dan papan.

### 5c.4 Diusulkan, belum diputuskan: Participation Shift

FL36 (cakupan semua broker, investor asing) dibandingkan dengan riwayat sendiri (persentil 250 sesi): dua sisi sejak awal. BBRI
asing, nilai beli + jual 5 sesi: 41,7% per 3 Nov, di persentil 4 terhadap 252 sesi (median 52,9%, P10 45,2%, P90 61,3%). User belum
memutuskan butir ini.

### 5c.5 Batas

Semua angka dari satu saham (BBRI), satu tanggal untuk nilai terakhir, dan 252 sesi untuk sebaran. Baseline 5 sesi berisik: sesudah
satu lonjakan, baseline berikutnya ikut terangkat. Tidak ada klaim bahwa lonjakan sisi mana pun memprediksi harga. Tidak ada kode
yang diubah.

## 6. Bentrokan kode "FL" antara terminal dan screener

Dua sistem memakai awalan "FL" dengan arti berbeda:

| Sistem | FL03 | Sumber |
|---|---|---|
| Terminal BFF (spesifikasi 2026-10-30) | Share · Volume (porsi lot kelompok broker) | `flowRegistry.json`, `FORMULAS.md` |
| Screener (proposal Flow fase 2) | Foreign participation (% nilai transaksi) | `apps/edge-bff/screener/src/core/screener-metrics.json` (`"fl": "FL03"`), `verification/screener/AUDIT.md` |

Akibatnya "FL03" di percakapan, dokumen, atau log dapat berarti dua hal. **Terverifikasi 2026-11-04:** semua 20 metrik Flow
di katalog screener (75 metrik; 20 berkode `fl` FL01 sampai FL20) berarti hal lain daripada indikator terminal dengan kode
yang sama. Contoh:

| Kode | Metrik screener (`id`: arti) | Indikator terminal |
|---|---|---|
| FL01 | `fnet`: net asing 5 sesi | Transaction Size · Lot |
| FL02 | `fpct`: net asing sebagai % nilai transaksi | Transaction Size · Value |
| FL03 | `fpart`: partisipasi asing (% nilai transaksi) | Share · Volume |
| FL04 | `fstreak`: hari berturut-turut net asing positif | Share · Transactions |
| FL07 | `topacc`: net beli top-N ditambah net jual bawah-N | Share · Market Volume |
| FL10 | `net_buy_hhi`: HHI pembeli net | Transactions · Buy/Sell Imbalance |

Semua 20 metrik screener itu berstatus "belum tersedia" (`unavailable_reason`: "Flow metrics arrive with Phase 2").
`FORMULAS.md` menyatakan Screener dan Backtest kelak memakai modul `flow.ts` yang sama, jadi penomoran perlu disatukan
sebelum itu. Pilihan: satu sistem kode untuk keduanya (misalnya awalan lain untuk metrik screener), atau menyatakan
dengan jelas di tiap dokumen sistem mana yang dimaksud.

## 7. Template kartu berikutnya

```
### Kartu: FLxx Nama
- Apa indikatornya (rumus, parameter bawaan, data)
- Contoh nyata (satu saham, angka)
- Temuan (kode F1.., bukti terukur, kriteria C1-C6)
- Pilihan keputusan (pertahankan / edit metrik / ganti visual / gabung / hapus) beserta dampak
- Usulan sementara AI
- Keputusan yang dibutuhkan
- Batas verifikasi
```
