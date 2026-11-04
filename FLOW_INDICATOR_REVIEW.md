# Tinjauan indikator Flow di BFF terminal

**Status:** dokumen kerja, dibuat 2026-11-04. Satu indikator sudah ditinjau (FL03); sisanya belum. Tidak ada keputusan
yang diambil dan tidak ada kode yang diubah.

**Tujuan (user 2026-11-04):** "Goalnya adalah apakah indikator ini perlu di eliminate, perlu di edit metric, visualnya
perlu diganti atau tidak." Bagian ini dibuat atas permintaan user: "create another section di REPO, which interkait
dengan indikator FLOW yang di display di BFF."

Dokumen ini adalah register tinjauan: untuk tiap indikator Flow ia mencatat apa indikator itu, buktinya pada data nyata,
dan pilihan keputusan. Keputusan akhir ada di user.

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
| FL07 | Share · Market Volume | Share | Panel | % | value | Belum ditinjau |  | Sama dengan garis Buy FL03 pada pengaturan bawaan (bagian 5, temuan F4) |
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
| FL32 | Transactions · Spike | Transactions | Panel | x | value | Belum ditinjau |  |  |
| FL33 | Transaction Size · Change % | Transaction Size | Panel | % | value | Belum ditinjau |  |  |
| FL34 | Institutional vs Retail Net | Other | Panel | % | value | Belum ditinjau |  |  |
| FL35 | Net Buy Persistence · Top Buyer | Net Flow | Panel | % | value | Belum ditinjau |  |  |
| FL36 | Share · Market Value (Buy + Sell) | Share | Panel | % | value | Belum ditinjau |  |  |
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
