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
| 1 | FL07 Share · Market Volume | Pensiunkan atau sembunyikan dari menu | "Maaf, maksud saya FL07 yang di sembunyikan. Bukan FL17." (2026-11-04) | To-do; keputusan user 2026-11-05: menu tidak ditampilkan lagi (sembunyikan), kode tidak digeser, komponen yang dipakai fitur lain tetap berfungsi. Kartu di bagian 5b |
| 2 | FL32 Transactions · Spike | Diedit **di tempat** (kode FL32 dipertahankan) menjadi "Activity Spike": parameter **Ukuran** (Transaksi, Nilai Rp, Lot) dan **Sisi** (Beli, Jual, atau Keduanya sebagai dua garis terpisah) | "P2 Ok tambahkan"; "P1 Pisahkan ... dipisahkan mana yang beli mana yang jual, per parameter"; "1. ya boleh" (pilihan Keduanya); "2. pertahankan di tempat" (2026-11-04) | To-do, belum dijadwalkan. Bagian 5c |
| 3 | Indikator baru: Spike Balance | Ditambahkan: lonjakan sisi beli dibagi lonjakan sisi jual untuk investor atau kelompok terpilih; **skala linear dengan garis netral 1** | "Spike balance OK tambahkan"; "3. skala garis netral 1" (2026-11-04) | To-do, belum dijadwalkan. Bagian 5c |
| 4 | FL33 Transaction Size · Change % | Ditambah pemilihan kelompok broker: parameter Top N, broker terpilih, dan sejenisnya, **sama seperti FL01** | "Tambahkan to donya ya buat FL33 tambahkan paramter Top N, broker dll sama seperti FL01" (2026-11-04) | To-do; keputusan user 2026-11-05: Top-N dipilih per hari (iv), bawaan tetap semua broker, parameter Side ditambahkan. Bagian 5d |
| 5 | FL13, FL14, FL38 (keluarga Concentration HHI) | Ditambah pilihan kelompok: **broker terpilih** dan **Top-N cohort dengan N yang bisa dipilih**, **sama seperti FL01** | "untuk HHI tambahkan opsi pilih by broker dan top N cohort yang N nya bisa dipilih seperti FL01 - masukan ke docs" (2026-11-04, dengan tangkapan layar menu: FL13, FL14, FL38) | To-do, belum dijadwalkan. Bagian 5e |
| 6 | FL15 (gross), FL16 (net), FL13 (HHI gross), FL38 (HHI net) | FL15 dan FL16 tetap **dua indikator** (satu gross, satu net), keduanya diberi parameter **Satuan: Lot atau Rupiah**; FL13 dan FL38 diberi parameter Satuan yang sama | "Goalnya 2 indikator itu tetap jadikan 2. 1 measure gross 1 measure nett, tapi 2 2nya harus bisa cater whether its rupiah dan lot (filterable)"; "Ok masukan ke to do 6 ya"; "Yes, tambahkan juga untuk FL13 dan FL38" (2026-11-04) | To-do, belum dijadwalkan. Bagian 5f |
| 7 | FL11 Net Flow / Turnover Ratio | **Hapus pilihan Denominator**: satu penyebut tetap, yaitu gross beli semua investor dengan filter papan saja (opsi A) | "Okay pakai A" (2026-11-04) | To-do, belum dijadwalkan. Bagian 5g.1 |
| 8 | Indikator baru (kode ditetapkan saat dikerjakan) | Sama persis dengan FL11, tetapi penyebutnya **rata-rata nilai transaksi (gross beli) N sesi terakhir**, N bawaan 20 dan bisa diatur | "Kemudian masukan juga untuk ditambahkan indikator yang sama persis tapi turnovernya adalah avg last 20D or can be adjustable. coba confirm" (2026-11-04) | To-do; bacaan AI dikonfirmasi user dengan "Ok" (2026-11-04). Bagian 5g.2 |
| 9 | FL35 Net Buy Persistence · Top Buyer | **Disembunyikan** dari menu indikator (hide) | "Hide saja FL35, masukan ke review" (2026-11-04) | To-do, belum dijadwalkan. Bagian 5h |
| 10 | FL21 Net Flow Percentile · vs Turnover | Ditambah parameter **Ukuran**: gross beli, gross jual, atau net beli (net), yang dipersentilkan terhadap turnover | "Not untuk FL21 yang bisa dimasukkan ke flow indicator review adalah biar ditambahkan filter untuk gross buy. Atau gross sell, dan juga net buy." (2026-11-05) | To-do, belum dijadwalkan. Bagian 5i |
| 11 | FL25 Bandar Balance · Rupiah | Visual tambahan yang menunjukkan **apa yang mendorong tiap kenaikan dan penurunan** FL25 | "Tampilan dua garis buat apa? FL25 sebenarnya yang perlu kita, kalau mau ditambahkan visual, adalah setiap kenaikan dan penurunan ini didorong oleh apa. Mungkin itu bisa dimasukkan ke to-do list." (2026-11-05) | **Dibatalkan 2026-11-05:** user memutuskan FL25 dibiarkan apa adanya, tanpa perubahan. Bagian 5j |
| 12 | FL29 Bandar Balance · Accumulation Days | Ditambah ukuran **seberapa besar** akumulasi, dalam persen atau persentil (sebanding antar saham), di panel yang sama atau sebagai indikator baru yang berpasangan | "mungkin di panel yang sama harus ditambahkan ... akumulasi terjadi 70% of the time. Tapi mesti dikasih tahu juga seberapa besar akumulasinya. Bukan in rupiah, tapi harus in percentage atau percentile. Sehingga angka tersebut bisa comparable across stock. Atau mungkin ya dibuatkan indikator baru lah. Yang bisa di-pair dengan FL29." (2026-11-05) | To-do; keputusan user 2026-11-05: ukuran C dalam persen, garis kedua di panel yang sama, FL24 dibiarkan, hari tanpa data tetap dihitung bukan akumulasi. Bagian 5k |
| 13 | Indikator baru (kode ditetapkan saat dikerjakan), berpasangan dengan FL17 | Harga rata-rata pembelian bergulir dengan **Top-N dipilih per hari** (cara B); indikator **terpisah**, FL17 tidak diubah | "Jadi aja kita tambahkan untuk opsi top N per hari yang nomor B. Ini dijadikan indikator terpisah saja nanti. You can review dan to do" (2026-11-05) | To-do, belum dijadwalkan. Bagian 5l |
| 14 | Dua indikator baru (kode ditetapkan saat dikerjakan): versi jual dari FL17 dan dari FL18 | **Dua indikator tambahan terpisah** yang menghitung nilai jual dibagi lot jual (harga rata-rata penjualan, gross jual): satu bergulir seperti FL17, satu beranchor seperti FL18 | "Boleh nggak ditambahkan satu indikator yang represent sell atau gross sell? Mirip FL18 juga. Berlaku juga untuk FL17."; "FL17 kan dia menghitung basically beli dibagi lot beli kan. FL18 juga. Yang saya butuhkan adalah dua indikator tambahan jual dan lot jual." (2026-11-05) | To-do, belum dijadwalkan. Bagian 5m |
| 15 | Indikator baru: Buy VWAP · Anchored · Distance % (sejajar FL20); versi rolling sudah ada sebagai FL39 | Jarak harga penutupan terhadap harga rata-rata pembelian beranchor (FL18) dalam persen; jarak terhadap harga rata-rata pembelian bergulir (FL17) sudah ada di FL39 | "Tolong tambahkan saja by vweb anchor dan by vweb rolling tapi versi percentage distance. seperti FL20. Konfirmasi kalau kamu paham." (2026-11-05; "vweb" dibaca VWAP) | To-do; bacaan AI dikonfirmasi user: hanya versi anchor yang baru, jarak rolling cukup FL39 (2026-11-05). Bagian 5n |
| 16 | FL17 dan FL39 | FL17 tetap menghitung harga, FL39 menghitung jarak (%) terhadap FL17, dan jarak itu dihitung dengan **parameter FL17** (bawaan FL39 disamakan: 20 sesi, semua papan, Foreign dan Domestic) | "17 dan 39. Jadikan FL17 menghitung secara price, tapi FL39 menghitung secara distance. Nah, distance ini harus dihitung menggunakan parameter yang ada di FL17." (2026-11-05) | To-do; keputusan user 2026-11-05: bawaan FL39 disamakan dengan bawaan FL17 sistem; FL39 tidak mengikuti pengaturan FL17 yang diubah pengguna. Bagian 5o |
| 17 | FL34 Institutional vs Retail Net | Ditambah ukuran **perubahan** (daily to daily, dan rentang lain): bacaan AI, perubahan nilai FL34 dibanding sesi sebelumnya dan beberapa jarak waktu lain; maksud pastinya menunggu user | "Alright, untuk FL34, to-do list-nya adalah kita perlu tambahkan change. Jadi change daily to daily, dan lain sebagainya. Paham?" (2026-11-05) | To-do; keputusan user 2026-11-05: panel gabungan, tanpa toggle (kedua tampilan langsung ditampilkan), opsi di settings untuk mematikan garis atau batang, poin persentase, tanpa penyebab perubahan. Bagian 5p |
| 18 | FL27 Silent Accumulation | FL27 tetap as is; ditambah **dua pemicu berbasis broker (net dan gross)** yang menyala sebagai penanda bila rasio nilai 3 pembeli teratas terhadap nilai 3 penjual teratas mencapai 1,5 kali; **opsional, bisa di-toggle on dan off** | "Tambahkan ke FL27 metrik tetap as is, tapi tambahkan metric, it triggers kalau ada akumulasi. Akumulasi: Which is rasio top X broker net ataupun gross di atas 1/X rasio top N sell atau gross sell. Konfirmasi." (2026-11-05) | To-do; definisi dijawab user (butir 1 sampai 5 dan 10); beberapa butir kecil menunggu user. Bagian 5q |

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
| FL21 | Net Flow Percentile · vs Turnover | Net Flow | Panel | 0-100 | value | To-do: ditambah parameter Ukuran (gross beli, gross jual, net) | Ditambah (2026-11-05, to-do) | Bagian 5i. Sekarang hanya net (FL11) terhadap turnover |
| FL22 | Broker Buy Breadth | Other | Panel | % | value | Belum ditinjau |  |  |
| FL23 | Broker Inventory | Other | Panel | lot|IDR | lines, total | Belum ditinjau |  |  |
| FL24 | Bandar Balance · % | Bandar Balance | Panel | % | value | Belum ditinjau |  |  |
| FL25 | Bandar Balance · Rupiah | Bandar Balance | Panel | IDR | value | Dibiarkan apa adanya (keputusan user 2026-11-05) | Tidak ada perubahan | Bagian 5j. Satu garis jumlah NB + NS; matriks penyebab naik dan turun ada di 5j.3b sebagai bahan bacaan |
| FL26 | Net Flow Streak | Net Flow | Panel | days | value | Belum ditinjau |  |  |
| FL27 | Silent Accumulation | Other | Penanda di bawah candle | flag | value | Belum ditinjau |  |  |
| FL28 | Average Daily Value | Other | Panel | IDR | value | Belum ditinjau |  |  |
| FL29 | Bandar Balance · Accumulation Days | Bandar Balance | Panel | % | value | To-do: ditambah ukuran besarnya akumulasi | Ditambah (2026-11-05, to-do) | Bagian 5k. Hanya menghitung jumlah hari, bukan besarnya |
| FL30 | Crossing Share | Other | Panel | % | value | Belum ditinjau |  |  |
| FL31 | Insider Net Change | Other | Panel | IDR | value | Belum ditinjau |  |  |
| FL32 | Transactions · Spike | Transactions | Panel | x | value | To-do: diedit di tempat menjadi Activity Spike | P1 dan P2 disetujui; di tempat; "Keduanya" disediakan (2026-11-04) | Kartu di bagian 5c; hanya sisi beli dan jumlah transaksi saat ini |
| FL33 | Transaction Size · Change % | Transaction Size | Panel | % | value | Belum ditinjau |  |  |
| FL34 | Institutional vs Retail Net | Other | Panel | % | value | Belum ditinjau |  |  |
| FL35 | Net Buy Persistence · Top Buyer | Net Flow | Panel | % | value | To-do: sembunyikan (hide) | Hide (2026-11-04, to-do) | Kartu di bagian 5h. Hanya satu broker (Top Buyer), menghitung hari bukan besarnya net |
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

1. ~~Sembunyikan, pensiunkan penuh, atau gabung ke FL03?~~ **Dijawab user 2026-11-05:** "Maksudnya adalah menu tersebut tidak usah visible lagi. Penomoran tidak digeser. Namun fitur-fitur atau AFL lain yang menggunakan komponen dari kode FL07 harus tetap functional as is." Jadi **sembunyikan dari menu** (opsi A di 5b.4); kode FL07 tidak dipakai ulang dan penomoran tidak digeser; FL09 dan pembantu penjelasan yang memakai komponen FL07 tidak boleh berubah perilakunya.
2. Apakah tampilan "porsi terhadap seluruh volume saham" masih dibutuhkan (pilihan penyebut di FL03)? **Tidak dijawab eksplisit**; karena user memilih sembunyikan saja tanpa menggabung ke FL03, kemampuan itu tidak dipertahankan di menu (bacaan AI).
3. ~~Kode FL07 tidak dipakai ulang dan tanpa penomoran ulang.~~ **Dijawab user 2026-11-05:** "Penomoran tidak digeser."

### 5b.6b Kriteria penerimaan untuk pelaksanaan (dari jawaban user 2026-11-05)

1. FL07 tidak muncul di menu indikator.
2. Kode FL07 dan penomoran FL lain tidak berubah.
3. Fungsi hitung FL07 (`marketShare`, `flow.ts:279`) tetap ada; hasil FL09 (yang memakainya, `flow.ts:386`) dan pembantu penjelasan angka yang berbagi penyebut dengan FL11 (`explainFlowA.ts:320`) tidak berubah.
4. Indikator FL07 yang sudah dipasang pengguna: perilakunya (tetap tergambar) belum diuji di browser; perlu diperiksa saat pelaksanaan.
5. Mekanisme sembunyikan yang sama dipakai untuk to-do 9 (FL35).

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

## 5d. To-do: FL33 mendapat pemilihan kelompok broker (Top-N, broker terpilih)

**Catatan user 2026-11-04 (kata-katanya):** "Tambahkan to donya ya buat FL33 tambahkan paramter Top N, broker dll sama seperti FL01."
Ini daftar to-do, bukan jadwal eksekusi: belum ada tanggal dan belum ada perintah "go". Kode tidak diubah.

### 5d.1 Kondisi sekarang **[T]** (kode dan registry dibaca 2026-11-04)

- Rumus (`FORMULAS.md:99`, `flow.ts:508-515`): `100 × ((BV/BF pada 5 candle terakhir) / (BV/BF pada 20 candle sebelumnya) − 1)`,
  nilai Rupiah per transaksi **beli**, tertimbang (total ÷ total).
- Parameter di `flowRegistry.json`: `boards`, `investors`, `recent` (5), `baseline` (20), `levels` (0). **Tidak ada** `scope`, `brokers`,
  `top`, `rank`, atau `ranking`. `grid0` (`flow.ts:231`) hanya membentuk grid dari papan dan investor, lalu `aw(...)` menjumlahkan
  **semua broker** di grid itu. Dengan investor bawaan, FL33 menggambarkan pasar saham itu secara keseluruhan.
- Contoh BBRI 3 Nov 2026: semua investor −11,2% (Rp16,54 juta/tx berbanding Rp18,62 juta/tx); investor Foreign −25,8%
  (Rp29,74 juta/tx berbanding Rp40,07 juta/tx). Sebaran 252 sesi (semua investor): P10 −23%, median −1%, P90 +21%.

### 5d.2 To-do: parameter yang ditambahkan (mengikuti FL01)

| Parameter | Bawaan di FL01 | Catatan untuk FL33 |
|---|---|---|
| Broker scope (`scope`) | Top-N cohort; alternatif Selected brokers | Baru di FL33 |
| Brokers (`brokers`) | kosong | Baru; dipakai bila scope = Selected brokers |
| Top N (`top`) | 3 (1 sampai 20) | Baru |
| Rank Top-N by (`rank`) | Net beli (Rp); alternatif beli bruto, net jual | Baru |
| Top-N ranking (`ranking`) | Dihitung ulang tiap hari | Baru (tetap, tidak bisa diubah) |
| `boards`, `investors`, `recent`, `baseline`, `levels` | | Tetap seperti sekarang |

### 5d.3 Keputusan user 2026-11-05 (jawaban atas tiga pertanyaan)

User menjawab: "(iv) Top-N per hari, bawaan tetap semua broker, Side ya".
1. **Kelompok: cara (iv), Top-N per hari.** Pada tiap sesi dalam periode terbaru (5) dan periode baseline (20), kelompok adalah Top-N hari itu (menurut `rank`, bawaan net beli); gross beli dan transaksi beli kelompok hari itu dijumlahkan sepanjang periode; FL33 membandingkan kedua total (`Σ BV / Σ BF` terbaru terhadap baseline).
2. **Bawaan `scope` tetap semua broker.** Ditambahkan opsi `All brokers` (FL01 hanya punya Top-N dan Selected brokers), sehingga FL33 yang sudah tersimpan pengguna tidak berubah arti.
3. **Parameter Side ditambahkan seperti FL01** (Beli, Jual, Keduanya sebagai dua garis terpisah). Sisi jual memakai `SV / SF`.

Contoh BBRI 3 Nov 2026 (semua investor, semua papan, N = 3, rank net beli, recent 5, baseline 20):

| Sesi terbaru | Top-3 hari itu | Gross beli (Rp miliar) | Transaksi beli | **Rp juta per transaksi beli** | Gross jual (Rp miliar) | Transaksi jual | **Rp juta per transaksi jual** |
|---|---|---:|---:|---:|---:|---:|---:|
| 28 Okt | DX, LG, ZP | 247,0 | 5.560 | **44,42** | 64,6 | 2.362 | **27,35** |
| 29 Okt | XL, OD, CC | 202,2 | 19.186 | **10,54** | 92,5 | 8.647 | **10,70** |
| 30 Okt | AK, LG, MG | 270,0 | 6.813 | **39,63** | 105,1 | 5.305 | **19,81** |
| 2 Nov | ZP, BK, XL | 218,8 | 13.422 | **16,30** | 81,9 | 7.196 | **11,38** |
| 3 Nov | OD, CC, YP | 317,7 | 16.733 | **18,98** | 100,6 | 7.973 | **12,62** |
| **Total (dibagi total, bukan rata-rata harian)** | | **1.255,6** | **61.714** | **20,35** | **444,8** | **31.483** | **14,13** |

Baseline (30 Sep sampai 27 Okt, 20 sesi, Top-3 tiap hari), sisi beli: gross beli (Rp miliar), transaksi beli, Rp juta per transaksi beli per sesi:
30 Sep KZ,BK,AG 179,9 / 2.698 / 66,68; 1 Okt YU,XL,YP 146,4 / 16.678 / 8,78; 2 Okt CC,BK,XL 178,9 / 17.605 / 10,16; 5 Okt BK,XL,BQ 91,8 / 9.714 / 9,45; 6 Okt BK,YU,LG 137,6 / 4.702 / 29,27;
7 Okt RX,ZP,AK 167,9 / 4.618 / 36,36; 8 Okt CC,YP,XL 169,3 / 17.549 / 9,65; 9 Okt LG,AZ,BK 107,7 / 2.045 / 52,69; 12 Okt ZP,KZ,DR 160,4 / 5.976 / 26,84; 13 Okt YP,SQ,CC 93,9 / 5.381 / 17,45;
14 Okt BK,YU,LG 170,8 / 4.161 / 41,05; 15 Okt AK,ZP,CC 234,4 / 7.774 / 30,15; 16 Okt XL,YP,SQ 910,3 / 100.254 / 9,08; 19 Okt CC,BK,XL 907,5 / 63.869 / 14,21; 20 Okt XL,OD,PD 445,4 / 45.763 / 9,73;
21 Okt OD,BK,NI 454,6 / 14.438 / 31,49; 22 Okt NI,BB,AK 717,0 / 21.619 / 33,16; 23 Okt CC,IF,KZ 606,5 / 18.765 / 32,32; 26 Okt NI,YU,YP 408,4 / 12.781 / 31,95; 27 Okt OD,AK,CC 556,8 / 17.210 / 32,35.
Total baseline: Rp6.845,6 miliar / 393.600 transaksi = Rp17,39 juta per transaksi (sisi jual: Rp2.323,6 miliar / 145.334 transaksi). Rata-rata sederhana dari angka harian akan memberi 26,64 (baseline) dan 25,97 (terbaru), **bukan** yang dipakai; FL33 memakai total dibagi total.
Sisi beli: 20,35 / 17,39 jt per transaksi, FL33 = **+17,0%**. Sisi jual: 14,13 / 15,99, FL33 = **−11,6%**. Bawaan semua broker (tanpa kelompok): −11,2% (sisi beli).

**Dikonfirmasi lagi 2026-11-05** sesudah user melihat contoh dengan Rupiah per transaksi tiap sesi: "Oke, kita pakai yang IV. Masukkan ke review."

**Pertanyaan yang tersisa (bacaan AI di sebelahnya):**
1. Pada Side = Jual, kelompok Top-N tetap dipilih menurut `rank` (bawaan net beli, seperti FL01), bukan menurut net jual; user belum menyebut.
2. Hari dengan pembeli bersih kurang dari N: kelompok memakai yang ada (usulan).
3. Peringkat per hari memakai net hari itu; bila `rank` = net jual, kelompok adalah penjual bersih terbesar hari itu.

### 5d.4 Berkas yang menyebut FL33 (hasil pencarian di repo; ini daftar awal, bukan hitungan dampak)

`apps/edge-bff/terminal/src/calc/flow.ts`, `apps/edge-bff/terminal/src/calc/explainFlowB.ts`, `apps/edge-bff/terminal/src/data/flowRegistry.json`
(dibangkitkan dari `verification/terminal_api/flow_indicators/build_spec_workbook.py` lewat `scripts/build_flow_registry.py`),
`apps/edge-bff/terminal/src/data/indNotes.json`, `apps/edge-bff/terminal/tests/calc/explain_flowB.test.ts`,
`verification/terminal_api/flow_indicators/FORMULAS.md`, `CODE_INSPECTION_20261101.md`, `oracle/cases.json`, dan berkas audit kartu
indikator di `verification/terminal_api/indicator_cards/`.

### 5d.5 Batas

Angka dari satu saham (BBRI), satu tanggal untuk nilai terakhir, dan 252 sesi untuk sebaran. Belum dicocokkan dengan angka di BFF
yang hidup. Tidak ada klaim bahwa perubahan ukuran tiket memprediksi harga. Tidak ada kode yang diubah.

## 5e. To-do: indikator HHI (FL13, FL14, FL38) mendapat pemilihan kelompok broker

**Catatan user 2026-11-04 (kata-katanya):** "untuk HHI tambahkan opsi pilih by broker dan top N cohort yang N nya bisa dipilih seperti FL01 - masukan ke docs."
Permintaan disertai tangkapan layar menu yang menampilkan tiga indikator HHI: FL13 Concentration HHI · Gross, FL14 Concentration HHI · Buy − Sell,
dan FL38 Concentration HHI · Net Buy. Tiga indikator itu yang dicatat di sini; **bila user bermaksud lain, koreksi bagian ini**.
Ini daftar to-do, bukan jadwal eksekusi: belum ada tanggal dan belum ada perintah "go". Kode tidak diubah.

### 5e.1 Kondisi sekarang **[T]** (registry dan kode dibaca 2026-11-04)

| Indikator | Parameter sekarang | Cara hitung (`flow.ts`, `FORMULAS.md`) |
|---|---|---|
| FL13 | `boards`, `investors`, `side` (Buy bawaan), `window` (1) | `Σ_b (BL(b)/BL(A))²` atas lot bruto **semua broker**; sisi jual memakai `SL` |
| FL14 | `boards`, `investors`, `window` (1), `levels` (0), `plot` (histogram) | FL13 Buy − FL13 Sell |
| FL38 | `boards`, `investors`, `window` (20, status PROPOSED) | `Σ (n_b / Σ n positif)²` atas net beli positif (Rp) **semua broker** |

Ketiganya tidak punya `scope`, `brokers`, `top`, `rank`, atau `ranking`. Pembentukan data hanya dari papan dan investor (`grid0`, `flow.ts:231`).

### 5e.2 To-do: parameter yang ditambahkan (mengikuti FL01)

| Parameter | Bawaan di FL01 |
|---|---|
| Broker scope (`scope`) | Top-N cohort; alternatif Selected brokers |
| Brokers (`brokers`) | kosong; dipakai bila scope = Selected brokers |
| Top N (`top`) | 3 (1 sampai 20) |
| Rank Top-N by (`rank`) | Net beli (Rp); alternatif beli bruto, net jual |
| Top-N ranking (`ranking`) | Dihitung ulang tiap hari |

### 5e.3 Pertanyaan terbuka (saat to-do ini diambil)

1. ~~Apa arti HHI pada sebuah kelompok.~~ **Dijawab user 2026-11-05:** "concentration HHI top N cohort adalah sum HHI dari top N atas broker2 di hari itu. Dalam contoh kamu, seharusnya yang di show adalah value 0,04997." Jadi bacaan (b) ditampilkan sebagai **nilai mentah**, bukan persen terhadap HHI total: `nilai = Σ_{b ∈ kelompok} (ukuran broker b ÷ total ukuran semua broker)²`.
   Contoh FL13, BBRI 3 Nov 2026 (semua investor, semua papan, window 1, sisi Beli), Top-3 menurut net beli (OD +111,6, CC +73,2, YP +32,3 Rp miliar): lot beli OD 458.508, CC 511.052, YP 196.874 dari total 3.195.143; porsi 14,35%, 15,99%, 6,16%; porsi² 0,02059 + 0,02558 + 0,00380 = **0,04997**. HHI seluruh broker (FL13 sekarang) 0,07616 (73 broker aktif). Dengan N = 1, 2, 3, 5: 0,02059; 0,04618; 0,04997; 0,06354 (naik bila N naik, tidak sebanding antar N). FL38 (5 sesi 28 Okt sampai 3 Nov, porsi terhadap total net beli positif Rp710,9 miliar): Top-3 OD, LG, DX = **0,0619** dari HHI total 0,0939.
   Menampilkan FL13 total sebagai garis pembanding di panel yang sama: belum diminta user.
2. **Broker terpilih**: apakah penyebut HHI tetap seluruh broker (jadi porsi broker terpilih terhadap pasar), atau hanya broker terpilih.
3. **Peringkat Top-N** memakai nilai yang sama atau berbeda dengan ukuran HHI-nya (misalnya FL13 menghitung lot bruto, sedangkan peringkat bawaan FL01 net beli Rp).
   Jika berbeda, ada sirkularitas seperti F1 pada FL03.
4. ~~FL14 mewarisi parameter FL13 atau punya sendiri.~~ **Dijawab user 2026-11-05: "Ok FL14 warisi parameter."** **Kelompok sisi jual FL14 dijawab user 2026-11-05:** "Ya kalau top end cohort, ya HHI top end dikurang HHI top sum. Tiga broker paling atas dikurang tiga broker sisi lainnya." Bacaan AI: cara **(B)**: FL14 = jumlah porsi² Top-N pembeli bersih (sisi beli) dikurangi jumlah porsi² Top-N penjual bersih (sisi jual, peringkat net jual). Contoh BBRI 3 Nov 2026, window 1, N = 3, total lot beli = total lot jual = 3.195.143: sisi beli OD 458.508 (porsi 0,143502; porsi² 0,020593), CC 511.052 (0,159947; 0,025583), YP 196.874 (0,061617; 0,003797), jumlah **0,049972**; sisi jual YU 550.075 (0,172160; 0,029639), BK 256.526 (0,080286; 0,006446), AK 278.607 (0,087197; 0,007603), jumlah **0,043688**; **FL14 = 0,049972 − 0,043688 = +0,006284**. Penafsiran "sisi lainnya" sebagai Top-N net jual adalah bacaan AI; koreksi bila yang dimaksud peringkat lain (misalnya lot jual bruto).
5. **Ditawarkan, belum dijawab user:** FL38 juga diberi parameter sisi (net beli, net jual, keduanya). Penyebabnya: HHI net beli tinggi tidak
   memberi tahu apakah HHI net jual juga tinggi. Bukti pada BBRI (252 sesi, semua investor): 3 Nov HHI net beli 0,1328 berbanding net jual 0,2217
   (jendela 20 sesi); keduanya di atas median bersamaan di 45 dari 252 sesi, dan di atas P90 bersamaan 0 sesi. Bukan to-do sampai user memutuskan.

**FL13 final (user 2026-11-05):** sesudah contoh final (BBRI 3 Nov 2026, Top-3 OD, CC, YP: porsi² beli 0,02059 + 0,02558 + 0,00380 = **0,04997**, jual 0,00648; HHI semua broker 0,07616 beli dan 0,07088 jual) user menjawab "Okay 1-1 ya. ini FL 13 selesai." Spesifikasi FL13: nilai kelompok = jumlah porsi² anggota kelompok, penyebut porsi seluruh broker hari itu; Top-N menurut `rank` (bawaan net beli seperti FL01); bila `window` > 1, Top-N dari net sepanjang jendela dikunci untuk jendela itu (cara FL17); bawaan `scope` tetap semua broker; broker terpilih memakai penyebut seluruh broker. FL14 dan FL38 dibahas satu per satu sesudahnya.

**FL38 final (user 2026-11-05):** sesudah penelusuran lengkap (BBRI, window 20, 7 Okt sampai 3 Nov 2026, Top-3 NI, CC, OD) user menjawab "Okay. Masukan ke review." Metode: nilai kelompok = jumlah porsi² anggota kelompok, porsi = net anggota ÷ total net beli positif seluruh pembeli bersih (net = gross beli − gross jual per broker). Asal angka contoh: net NI 1.345,132 − 364,998 = +980,134; CC 2.868,148 − 2.016,576 = +851,572; OD 1.127,490 − 420,300 = +707,190 (Rp miliar); total net beli positif (jumlah net 71 pembeli bersih dari 89 broker aktif) = Rp4.337,444 miliar; porsi 0,225970, 0,196330, 0,163043; porsi² 0,051063, 0,038546, 0,026583; **nilai kelompok 0,116192** (tanpa pembulatan 0,116191); pembanding FL38 semua pembeli bersih 0,132784 (jumlah porsi² 71 pembeli bersih). Broker terpilih CC dan XL: 0,038546 + 0,009459 = 0,048005. Window 1 (3 Nov 2026), Top-3 OD, CC, YP: total net beli positif Rp358,674 miliar (56 pembeli bersih), porsi² 0,096798 + 0,041605 + 0,008093 = 0,146496; pembanding 0,162522.
Butir kecil FL38 yang dianggap disetujui dengan jawaban "Okay" (bacaan AI atas usulan AI; **koreksi bila berbeda**): aturan FL13 berlaku (penyebut total net beli positif); pilihan `rank` hanya net beli dan gross beli (peringkat net jual menghasilkan 0); broker terpilih dengan net ≤ 0 bernilai 0; parameter sisi tidak ditambahkan dulu; `window` bawaan tetap 20; untuk `window` > 1 Top-N dari net sepanjang jendela dikunci; bawaan `scope` tetap semua broker; Satuan Lot atau Rupiah memakai tanda net lot sendiri.

### 5e.4 Batas

Satu saham (BBRI), satu tanggal untuk contoh, dan 252 sesi untuk sebaran. Tidak ada klaim bahwa konsentrasi memprediksi harga. Belum dicocokkan dengan angka di BFF yang hidup. Tidak ada kode yang diubah.

## 5f. To-do: FL15 dan FL16 tetap dua indikator, keduanya dengan pilihan satuan (Lot atau Rupiah); FL13 dan FL38 ikut

**Catatan user 2026-11-04 (kata-katanya):** "Goalnya 2 indikator itu tetap jadikan 2. 1 measure gross 1 measure nett, tapi 2 2nya haeus bisa cater whether its rupiah dan lot (filterable)"; lalu "Ok masukan ke to do 6 ya."
Ini daftar to-do, bukan jadwal eksekusi: belum ada tanggal dan belum ada perintah "go". Kode tidak diubah.

**Lingkup, dijawab user 2026-11-04:** "Yes, tambahkan juga untuk FL13 dan FL38." Maksudnya (dikonfirmasi user): parameter Satuan yang sama dengan FL15 dan FL16 ditambahkan ke FL13 dan FL38, bukan membuat FL13 dan FL38 memakai satuan yang sama satu sama lain. Sekarang FL13 hanya lot (bruto) dan FL38 hanya Rupiah (net); sesudahnya FL13 bisa dipilih dalam Rupiah dan FL38 dalam lot.

Bacaan AI atas kata-kata itu (belum dikonfirmasi user, "low" dibaca "lot"): dua indikator tetap; parameter baru **Satuan** (Lot, Rupiah) di keduanya;
filter papan dan investor yang sudah ada tetap.

### 5f.1 Kondisi sekarang **[T]** (kode dan registry dibaca 2026-11-04)

| | FL15 Concentration Top-N · Gross Buy | FL16 Concentration Top-N · Net Buy |
|---|---|---|
| Urutan broker | Lot beli bruto (`topBrokers(..., 'gross_buy_lots')`) | Net beli `BV(b) − SV(b)` (Rp), hanya yang positif |
| Pembilang | Jumlah N lot beli terbesar | Jumlah N net beli positif terbesar |
| Penyebut | `BL(A)`, semua lot beli | Jumlah semua net beli positif |
| Satuan | **Lot saja** | **Rupiah saja** |
| Parameter | `boards`, `investors`, `window` (1), `top` (3) | sama |

### 5f.1b FL13 dan FL38 **[T]**

| | FL13 HHI · Gross | FL38 HHI · Net Buy |
|---|---|---|
| Dasar | Lot beli (atau jual) bruto semua broker: `Σ (BL(b)/BL(A))²` | Net beli positif `BV(b) − SV(b)`: `Σ (n_b/Σ n positif)²` |
| Satuan | **Lot saja** | **Rupiah saja** |
| Parameter | `boards`, `investors`, `side` (Buy), `window` (1) | `boards`, `investors`, `window` (20, PROPOSED) |

### 5f.2 To-do

- Tambah parameter `Satuan`: Lot atau Rupiah, di FL15 dan FL16.
- FL15 dengan Rupiah: urut dan jumlahkan `BV` (nilai beli bruto); penyebut total nilai beli semua broker.
- FL16 dengan Lot: `n_b = BL(b) − SL(b)` yang positif; penyebut jumlah net lot positif.
- **Bawaan dipertahankan** (FL15 lot, FL16 Rupiah), agar indikator tersimpan pengguna (parameter yang hilang diisi bawaan registry) tidak berubah arti.
- FL13 dengan Rupiah: porsi `BV(b)/BV(A)` (atau `SV`) bruto; FL38 dengan Lot: `n_b = BL(b) − SL(b)` yang positif. Bawaan dipertahankan (FL13 lot, FL38 Rupiah).
- Perbedaan yang tetap: FL15 memakai ukuran bruto dan penyebut total beli; FL16 memakai ukuran net dan penyebut jumlah net positif. Dengan satuan yang sama,
  perbedaannya hanya bruto dan net.

### 5f.3 Bukti pada data (BBRI, 252 sesi, semua investor, semua papan, dihitung 2026-11-04)

FL13 dan FL38 (HHI): FL13 beli, lot vs Rp, selisih mutlak rata-rata / maksimum 0,0001 / 0,0013 (jendela 1) dan 0,0003 / 0,0036 (jendela 20); FL38, Rp vs lot, 0,0003 / 0,0041 (jendela 1) dan 0,0027 / 0,0246 (jendela 20). Pada 3 Nov: FL38 jendela 20 = 0,1328 (Rp) dan 0,1253 (lot). FL15 dan FL16:

| | Jendela 1 hari | Jendela 20 sesi |
|---|---|---|
| FL15, lot vs Rp: selisih mutlak rata-rata / maksimum (poin) | 0,03 / 0,65 | 0,10 / 0,92 |
| FL16, Rp vs lot: selisih mutlak rata-rata / maksimum (poin) | 0,07 / 0,83 | 0,57 / 3,97 |
| Top-3 sama persis | 99% hari | 98% hari |

Pada 3 Nov: FL15 40,8% (lot) dan 40,7% (Rp); FL16 60,5% (Rp) dan 60,7% (lot). Pilihan satuan hampir tidak mengubah hasil pada saham ini; nilainya
terutama pada konsistensi dan perbandingan yang adil gross lawan net. Pada saham tipis atau berharga sangat bervariasi, selisih bisa lebih besar (belum diukur).

### 5f.4 Pertanyaan terbuka (saat to-do ini diambil)

1. ~~Lingkup: apakah FL13 dan FL38 ikut.~~ **Dijawab user 2026-11-04: ya, ikut.** Tersisa: bagaimana Satuan berinteraksi dengan pilihan kelompok broker yang dicatat di bagian 5e (to-do 5).
2. Apakah FL01/FL02 juga digabung dengan parameter Satuan (usulan AI, belum diputuskan).
3. Tanda net lot dan net Rupiah bisa berbeda untuk broker tertentu; apakah net lot memakai tandanya sendiri (usulan AI) atau mengikuti net Rupiah.

### 5f.5 Batas

Satu saham (BBRI). Tidak ada klaim bahwa satuan mana pun lebih prediktif. Belum dicocokkan dengan angka di BFF yang hidup. Tidak ada kode yang diubah.

## 5g. To-do: penyebut FL11 disederhanakan (opsi A) dan indikator baru dengan penyebut rata-rata turnover

Ini daftar to-do, bukan jadwal eksekusi: belum ada tanggal dan belum ada perintah "go". Kode tidak diubah.

### 5g.1 To-do 7: FL11 hanya satu penyebut (opsi A)

**Keputusan user 2026-11-04:** "Okay pakai A", sesudah AI menyajikan tiga opsi untuk pilihan Denominator FL11: A hapus pilihan, B pertahankan dengan peringatan, C ganti opsi kedua dengan metrik baru.

- **Sekarang [T]:** `denom` = `board` (bawaan, "Board turnover, all investors") atau `filter` ("Board and investor turnover"). Pembilang selalu **net** `BV(C) − SV(C)`. Penyebut
  `board` = **gross** beli semua broker, hanya filter papan (semua investor); `filter` = gross beli semua broker dengan filter papan dan investor (`flow.ts:280`, `:229`; `FORMULAS.md:62`).
- **Sesudahnya:** satu penyebut, `BV(A)` gross beli semua investor dengan filter papan saja. Pilihan Denominator hilang dari dialog FL11.
- **Dasar keputusan (hasil ukur BBRI, 2026-11-04):** dengan investor Foreign dan Domestic kedua opsi identik; dengan investor Foreign saja opsi `filter` memberi nilai di luar ±100% pada 43 dari 252
  sesi (minimum −778%; 3 Nov −196,0% berbanding −35,5% pada opsi `board`); FL09 dan FL36 sudah memakai penyebut papan-saja yang tetap; tabel fitur menghitung `foreign_net_turnover_ratio` terhadap nilai transaksi total (`DATABASE_SCHEMA.md:3053`).
- **Berkas yang memuat kata `denom` (daftar awal, sebagian mungkin tidak terkait):** `apps/edge-bff/terminal/src/calc/flow.ts`, `explainFlowA.ts`, `src/data/flowRegistry.json`, `src/data/indNotes.json`,
  `tests/calc/flow.test.ts`, `tests/calc/explain_flowA.test.ts`, `verification/terminal_api/flow_indicators/FORMULAS.md`, `oracle/oracle.py`, `oracle/cases.json`, `scripts/terminal_indicator_spec.py`, `scripts/build_flow_registry.py`.
- **Pertanyaan terbuka:**
  1. **FL07** punya pilihan `denom` yang sama (pada opsi `filter`, FL07 sama dengan FL03). Apakah FL07 ikut disederhanakan, atau diputuskan bersama to-do 1 (menyembunyikan atau memensiunkan FL07).
  2. **Grafik tersimpan** yang memakai `denom = filter`: perilakunya sesudah opsi dihapus belum diperiksa (indikator tersimpan ada di browser; parameter yang hilang diisi bawaan registry).
  3. FL21 (persentil FL11, "same denominator") mengikuti perubahan ini.

### 5g.2 To-do 8: indikator baru "net flow terhadap rata-rata turnover"

**Kata user 2026-11-04:** "Kemudian masukan juga untuk ditambahkan indikator yang sama persis tapi turnovernya adalah avg last 20D or can be adjustable. coba confirm."

**Dikonfirmasi user 2026-11-04:** setelah AI menyajikan bacaan di bawah dan tujuh pertanyaan konfirmasi (usulan AI untuk tiap butir tertera), user menjawab "Ok". Jawabannya satu kata dan tidak menyebut butir per butir; **bila ada butir yang dimaksud berbeda, koreksi**. Usulan AI yang berlaku: baseline N sesi sebelum t, `W × rata-rata harian` bila `W > 1`, N 1 sampai 250, nama "Net Flow / Average Turnover" dengan kode ditetapkan saat dikerjakan, null bila sesi sebelumnya kurang dari N.

**Bacaan AI:**
- Pembilang sama dengan FL11: **net** `BV(C) − SV(C)` kelompok `C` pada jendela `W` (bawaan 1).
- Penyebut: **rata-rata harian gross beli semua broker (semua investor, papan saja)** selama N sesi terakhir, dikalikan `W` bila `W > 1`. N bawaan 20 dan bisa diatur (parameter `baseline`, seperti FL32 dan FL33).
- Parameter lain sama dengan FL11 (`scope`, `brokers`, `top`, `rank`, `ranking`, `boards`, `investors`, `window`, `plot`), tanpa `denom`.
- Maksudnya: net flow diukur terhadap turnover "normal", bukan turnover hari itu, sehingga hari dengan lonjakan volume tidak mengencerkan nilainya.

**Bukti pada data (BBRI, cohort Top-3 net beli, jendela 1, semua papan, semua investor, 252 sesi, dihitung 2026-11-04):**
- 3 Nov: net kelompok Rp217,0 miliar; FL11 (penyebut hari itu Rp872,5 miliar) = 24,9%; penyebut rata-rata 20 sesi **sebelumnya** (Rp1.054,9 miliar) = 20,6%; rata-rata 20 sesi **termasuk** hari ini (Rp1.076,6 miliar) = 20,2%.
- Sebaran 252 sesi: FL11 min 7,5, median 22,7, P90 38,0, maks 56,4; versi rata-rata 20 sesi min 3,7, median 20,6, P90 39,3, **maks 109,6** (16 Okt 2026, saat nilai transaksi hari itu 6,50 kali rata-ratanya).
- Korelasi kedua versi hanya 0,42. Pada 28 hari dengan nilai transaksi > 1,5 kali rata-rata 20 sesi, rata-rata FL11 23,1% berbanding 51,6% pada versi rata-rata. Variasi penyebut (CV): hari itu 0,55 berbanding rata-rata 20 sesi 0,23.
- Versi rata-rata bisa melewati 100% pada hari lonjakan (net kelompok lebih besar dari turnover hari rata-rata).

**Pertanyaan konfirmasi (dijawab "Ok" atas usulan AI):**
1. Baseline N sesi **sebelum** t (tanpa hari ini, seperti baseline FL32 dan FL33) atau **termasuk** hari ini? Usulan AI: sebelum. Selisihnya pada 3 Nov 20,6% berbanding 20,2%.
2. Bila `W > 1`: pembilang dijumlahkan sepanjang W sesi, penyebut = `W × rata-rata harian N sesi` (asumsi AI).
3. Penyebut gross beli semua investor, papan saja (konsisten dengan keputusan A).
4. Nama dan kode: kode FL40 atau berikutnya, ditetapkan saat dikerjakan. Usulan nama: "Net Flow / Average Turnover".
5. Kosong (null) bila sesi sebelumnya kurang dari N.
6. Rentang N yang boleh diatur (usulan 1 sampai 250, seperti `window`).
7. Sirkularitas kohort bawaan (FL11 positif 252 dari 252 sesi karena kohort dipilih dari net beli) tetap berlaku di indikator baru.

### 5g.3 Batas

Satu saham (BBRI), satu tanggal untuk contoh. Tidak ada klaim bahwa penyebut mana pun lebih prediktif. Belum dicocokkan dengan angka di BFF yang hidup. Tidak ada kode yang diubah.

## 5h. To-do: FL35 disembunyikan (hide)

**Catatan user 2026-11-04 (kata-katanya):** "Hide saja FL35, masukan ke review." Alasan tidak disebut user. "Review" dibaca sebagai dokumen ini.
Ini daftar to-do, bukan jadwal eksekusi: belum ada tanggal dan belum ada perintah "go". Kode tidak diubah.

### 5h.1 Apa indikatornya **[T]** (kode `flow.ts:527-534`, `FORMULAS.md:101`, registry)

Broker dengan **net** `BV − SV` kumulatif terbesar dan positif dalam jendela `D` (bawaan 20) dibekukan untuk jendela itu;
`FL35 = 100 × (sesi dengan net harian > 0) / D`. Parameter hanya `boards`, `investors`, dan `window`; tidak ada scope, Top-N, atau peringkat.

### 5h.2 Bukti dari penjelasan AI 2026-11-04 (BBRI, semua investor, semua papan, jendela 20; bukan alasan user)

- Contoh 3 Nov 2026: top buyer NI, net +Rp980,1 miliar, sesi net beli 13 dari 20, **FL35 = 65%**; dua hari (+Rp499 dan +Rp301 miliar) menyumbang 82% dari net total. Yang dihitung hari, bukan besarnya.
- Sebaran 252 sesi: minimum 45%, P10 55%, median 75%, maksimum 100%; ≥ 50% pada 115 dari 120 sesi, jadi ambang 50% tidak membedakan.
- Efek seleksi: rata-rata persistensi pembeli bersih lain (aktif ≥ 5 hari) median 53%; top buyer lebih persisten pada 236 dari 252 sesi.
- Hubungan dengan arus asing (net asing 20 sesi × FL35 ≥ 75%): net beli 3 tinggi / 32 rendah, net jual 62 / 23; korelasi −0,66 (arah dan sebab belum diuji; pemisahan jenis investor top buyer tidak dihitung).
- Belum diuji hubungannya dengan return ke depan.

### 5h.3 Fakta untuk pelaksanaan (pencarian di repo, 2026-11-04)

- FL35 **tidak dipakai indikator lain**: fungsi hitungnya (`flow.ts:527`) dan penjelasan angkanya (`explainFlowB.ts:585`) tidak dirujuk oleh FL09, FL11, atau yang lain. Berkas yang menyebut FL35:
  `build_spec_workbook.py`, `FORMULAS.md`, `CODE_INSPECTION_20261101.md` dan `.json`, `oracle/cases.json`, `flowRegistry.json`, `indNotes.json`, `explainFlowB.ts`, `explain_flowB.test.ts`, kartu audit di `verification/terminal_api/indicator_cards/`, serta `ERRORS_AND_SOLUTIONS.md` dan `FUTURE_PLAN.md` (sebutan di sana tidak diperiksa).
- **Belum ada mekanisme "sembunyikan"** (lihat 5b.3): registri hanya punya `family`, `id`, `name`, `needs_frequency`, `outputs`, `params`, `place`, `tip`, `unit`. Mekanisme itu dibutuhkan juga oleh to-do 1 (FL07), jadi satu mekanisme bisa melayani keduanya.
- **Indikator tersimpan pengguna** (`ml.ind.v1`, `indicators.ts:218`): pada jalur hide definisi tetap ada, sehingga grafik yang sudah memasang FL35 tetap tergambar (asumsi dari 5b.4, perilaku persisnya belum diperiksa). Pada jalur pensiun, entri yang kodenya hilang dibuang diam-diam (`indicators.ts:746`).

### 5h.4 Pertanyaan terbuka (saat to-do ini diambil)

1. **Arti "hide":** disembunyikan dari menu saja, definisi dan hitungan tetap ada (diasumsikan, sama dengan FL07 jalur "sembunyikan"). Bila yang dimaksud dikeluarkan sepenuhnya, daftar sentuhnya jauh lebih besar (lihat 5b.5).
2. **Pengganti.** Gagasan yang sempat muncul dalam penjelasan (belum diputuskan, belum to-do): FL35 dengan Top-N atau broker terpilih seperti FL01, atau ukuran yang memperhitungkan besarnya net. Dengan hide, gagasan itu tidak dikerjakan kecuali user meminta.
3. **Urutan.** Mekanisme sembunyikan sama dengan to-do 1; apakah dikerjakan bersama.

### 5h.5 Batas

Satu saham (BBRI), satu tanggal untuk contoh. Angka dihitung dari data broker mentah, belum dicocokkan dengan BFF yang hidup. Tidak ada kode yang diubah.

## 5i. To-do: FL21 diberi pilihan ukuran (gross beli, gross jual, net)

**Catatan user 2026-11-05 (kata-katanya):** "Not untuk FL21 yang bisa dimasukkan ke flow indicator review adalah biar ditambahkan filter untuk gross buy. Atau gross sell, dan juga net buy."
Ini daftar to-do, bukan jadwal eksekusi: belum ada tanggal dan belum ada perintah "go". Kode tidak diubah.

### 5i.1 Kondisi sekarang **[T]** (`flow.ts:421`, registry, `FORMULAS.md:87`)

FL21 = persentil (baseline 250, peringkat tengah, hanya nilai sebelumnya) dari FL11 = `100 × (BV(C) − SV(C)) / TBV`. Pembilang selalu **net** kelompok; penyebut `TBV`
= **gross** beli semua broker (papan saja). Parameter: `scope` (Top-N bawaan), `brokers`, `top`, `rank`, `ranking`, `boards`, `investors`, `window` (1), `baseline` (250), `levels`.
Tidak ada parameter ukuran.

### 5i.2 To-do

Bacaan AI atas kata-kata user (belum dikonfirmasi): parameter baru **Ukuran** dengan tiga pilihan, penyebut dan persentil tetap:

| Ukuran | Pembilang | Catatan |
|---|---|---|
| Net (bawaan; yang user sebut "net buy") | `BV(C) − SV(C)`, **net** | Sama dengan FL21 sekarang; positif = net beli, negatif = net jual |
| Gross beli | `BV(C)`, **gross** beli kelompok | Porsi beli kelompok terhadap turnover |
| Gross jual | `SV(C)`, **gross** jual kelompok | Porsi jual kelompok terhadap turnover |

Penyebut tetap `TBV` (gross beli semua broker, papan saja; keputusan opsi A di to-do 7). Persentil (baseline 250) dan parameter lain tidak berubah.

### 5i.3 Bukti pada data (BBRI, 3 Nov 2026, dihitung 2026-11-05)

Kohort Top-3 asing menurut net beli (CC, AK, BK), jendela 5 sesi, semua papan, baseline 250. Gross beli kohort Rp782,9 miliar, gross jual Rp743,6 miliar, net Rp39,2 miliar, turnover 5 sesi Rp3.867,2 miliar.

| Ukuran | Nilai (% turnover) | Median 250 nilai sebelumnya | Persentil |
|---|---:|---:|---:|
| Net | 1,01 | 7,83 | **3,2** |
| Gross beli | 20,24 | 17,74 | **56,4** |
| Gross jual | 19,23 | 9,68 | **89,2** |

Pada hari yang sama net tampak lemah, gross beli biasa saja, dan gross jual tinggi: tiga ukuran memberi gambaran berbeda. Korelasi persentil 252 sesi: net-gross beli 0,84; net-gross jual 0,41; gross beli-gross jual 0,82.

### 5i.4 Pertanyaan terbuka (saat to-do ini diambil)

1. **"net buy" dibaca net bertanda** (sama dengan sekarang). Bila yang dimaksud hanya sisi positif atau cara lain, koreksi.
2. **Nama.** "Net Flow Percentile · vs Turnover" tidak lagi akurat bila ukuran bisa gross; nama baru ditentukan saat dikerjakan.
3. **Penyebut untuk gross jual:** gross beli semua broker (untuk semua investor sama dengan total jual semua broker; 3 Nov Rp872,5 miliar kedua sisi).
4. **Peringkat kohort** (`rank`) tetap terpisah dari ukuran. Kohort bawaan dipilih dari net beli; pada ukuran gross jual kohort itu bisa memiliki gross jual tinggi karena dipilih dari net beli jendela yang sama.
5. **Gross beli + gross jual** (partisipasi seperti FL36) sebagai pilihan keempat atau indikator tersendiri (usulan Participation Shift di 5c.4, belum diputuskan).
6. Hubungan dengan to-do 6 (Satuan: lot atau Rupiah; FL21 sekarang hanya Rupiah) dan to-do 8 (penyebut rata-rata turnover).

### 5i.5 Batas

Satu saham (BBRI), satu tanggal untuk contoh, baseline 250 nilai yang saling tumpang tindih. Tidak ada klaim bahwa ukuran mana pun prediktif. Dihitung dari data broker mentah, belum dicocokkan dengan BFF yang hidup. Tidak ada kode yang diubah.

## 5j. To-do: FL25 menampilkan apa yang mendorong tiap kenaikan dan penurunan

**Catatan user 2026-11-05 (kata-katanya):** "Tampilan dua garis buat apa? FL25 sebenarnya yang perlu kita, kalau mau ditambahkan visual, adalah setiap kenaikan dan penurunan ini didorong oleh apa. Mungkin itu bisa dimasukkan ke to-do list."
Ini daftar to-do, bukan jadwal eksekusi: belum ada tanggal dan belum ada perintah "go". Kode tidak diubah. Usul AI sebelumnya, tampilan dua garis (NB dan NS terpisah), **tidak diambil** karena user mempertanyakan gunanya; yang diminta adalah penyebab perubahan.

**Keputusan user 2026-11-05 (membatalkan to-do ini):** "Yes, sudah untuk indikator ini we leave it as is saja, tidak ada perubahan. Move on to next indicator." Jadi **tidak ada perubahan pada FL25** dan to-do 11 tidak dikerjakan. Isi bagian ini dipertahankan sebagai catatan riwayat dan bahan bacaan.

### 5j.1 Kondisi sekarang **[T]** (`flow.ts:300-305`, `:447-450`, registry)

FL25 = `NB + NS` (Rupiah): `NB` jumlah **net** (`BV − SV`, gross beli dikurangi gross jual) dari N pembeli bersih terbesar, `NS` dari N penjual bersih terbesar (negatif), net dijumlahkan sepanjang `window` (10). Outputnya satu garis (`net`).
Parameter: `top` (3), `boards`, `investors`, `window` (10), `plot`. Perubahan garis tidak menunjukkan penyebabnya.

### 5j.2 Bacaan AI atas "didorong oleh apa" (belum dikonfirmasi user)

Perubahan harian FL25 dapat dipecah **persis** (jumlah komponen sama dengan perubahan, selisih 0,000000 pada 252 sesi) menjadi tiga komponen, dengan `S_t` enam broker (N pembeli dan N penjual) pada hari `t`, `d_(t,b)` net harian broker `b`, `cum_(t,b)` net kumulatif jendela:

`ΔFL25_t = Σ_(b∈S_t) d_(t,b)` **(hari yang masuk jendela)**
`− Σ_(b∈S_t) d_(t−W,b)` **(hari yang keluar jendela)**
`+ [Σ_(b∈S_t) cum_(t−1,b) − Σ_(b∈S_(t−1)) cum_(t−1,b)]` **(pergantian anggota enam broker)**

Pemecahan lain yang bisa dipertimbangkan: menurut sisi (perubahan NB dan NS) dan menurut broker (nama broker yang menyumbang).

### 5j.3 Bukti pada data (BBRI, jendela 10, N = 3, semua papan, dihitung 2026-11-05)

Rp miliar, semua investor:

| Tanggal | FL25 | Perubahan | Hari masuk | Hari keluar | Pergantian anggota |
|---|---:|---:|---:|---:|---:|
| 29 Okt | −849,8 | −133,6 | −31,6 | −102,0 | 0,0 |
| 30 Okt | −255,0 | +594,8 | −275,0 | +190,5 | +679,3 |
| 2 Nov | +622,3 | +877,3 | +78,2 | +574,8 | +224,4 |
| 3 Nov | +696,1 | +73,8 | +34,7 | −81,2 | +120,3 |

- Pada 252 sesi, porsi |kontribusi| rata-rata: hari masuk 39%, hari keluar 38%, pergantian anggota 23% (investor Foreign: 43%, 40%, 16%). Anggota enam broker berganti (minimal satu broker baru) pada 180 dari 252 sesi.
- Pada 10% perubahan terbesar (26 sesi), komponen terbesar: hari keluar 11, hari masuk 11, pergantian anggota 4 (Foreign: hari keluar 18, hari masuk 6, pergantian anggota 2).
- Dari penjelasan sebelumnya (jendela 10, N = 3): FL25 turun pada 121 dari 252 sesi; penyebabnya hanya NS memburuk 57, keduanya memburuk 34, hanya NB menyusut 30. Pada 30 Okt dan 2 Nov FL25 naik Rp1.472 miliar dalam dua hari saat NB justru menyusut, sebab hari berpenjualan besar keluar dari jendela.

### 5j.3b Matriks penyebab naik dan turun (bahan bacaan; BBRI, 252 sesi 16 Okt 2025 sampai 3 Nov 2026, jendela 10, N = 3, semua investor, dihitung 2026-11-05)

Perubahan harian FL25 = hari masuk + hari keluar + pergantian anggota (selisih 0,000000). Naik (131 sesi): komponen terbesar hari keluar 61, hari masuk 46, pergantian anggota 24; rata-rata komponen +43,8, +106,6, +7,5 (Rp miliar). Turun (121 sesi): hari masuk 59, hari keluar 37, pergantian anggota 25; rata-rata −116,3, −40,1, +0,8.
Level FL25: P10 −1.171,1; median −306,0; P90 +473,1. Dari puncak (level kemarin ≥ P90, 25 sesi): turun pada 15 (60%), komponen terbesar hari masuk 9, hari keluar 5, pergantian 1. Dari dasar (≤ P10, 26 sesi): naik pada 13 (50%), komponen terbesar hari keluar 8, hari masuk 3, pergantian 2. Contoh: 28 Jan 2026 FL25 797,9 → 226,6 (−571,2 = masuk −708,4 + keluar −215,7 + pergantian +352,9); 2 Jul 2026 −1.342,4 → −821,3 (+521,1 = masuk +130,7 + keluar +419,0 + pergantian −28,6).

### 5j.4 Pertanyaan terbuka (saat to-do ini diambil)

1. **Apa arti "didorong oleh apa"** bagi user: pemecahan menurut waktu (hari masuk, hari keluar, pergantian anggota), menurut sisi (NB atau NS), menurut broker, atau gabungan. Bacaan di 5j.2 hanya usulan AI.
2. **Bentuk visual:** batang bertumpuk di bawah garis, keterangan saat kursor diarahkan, atau panel terpisah. Belum dibahas.
3. **Nama broker** per komponen perlu ditampilkan atau tidak.
4. **Cakupan:** hanya FL25 (kata user) atau juga FL24 (versi persen) dan indikator sejenis.
5. **Rolling days** tetap menentukan jendela; pemecahan "hari keluar" bergantung padanya.

### 5j.5 Batas

Satu saham (BBRI), satu tanggal untuk contoh. Pemecahan dihitung dari data broker mentah, belum dicocokkan dengan BFF yang hidup. Tidak ada klaim bahwa komponen mana pun prediktif. Tidak ada kode yang diubah.

## 5k. To-do: FL29 diberi ukuran besarnya akumulasi (persen atau persentil)

**Catatan user 2026-11-05 (kata-katanya):** "Alright, mungkin to-do list untuk FL FL29 ini adalah mungkin di panel yang sama harus ditambahkan yes, betul, akumulasi terjadi 70% of the time. Tapi mesti dikasih tahu juga seberapa besar akumulasinya. Bukan in rupiah, tapi harus in percentage atau percentile. Sehingga angka tersebut bisa comparable across stock. Atau mungkin ya dibuatkan indikator baru lah. Yang bisa di-pair dengan FL29."
Ini daftar to-do, bukan jadwal eksekusi: belum ada tanggal dan belum ada perintah "go". Kode tidak diubah.

### 5k.1 Kondisi sekarang **[T]** (`flow.ts:485-489`, `FORMULAS.md:95`, registry)

Per sesi dihitung saldo harian = `100 × (net 3 pembeli bersih terbesar sesi itu + net 3 penjual bersih terbesar sesi itu) / gross beli semua broker sesi itu` (net = `BV − SV`). Sesi dengan saldo di atas `threshold` (0%) dihitung sebagai hari akumulasi.
`FL29 = 100 × (jumlah hari akumulasi dalam days sesi terakhir) / days` (days 20). Yang dihitung jumlah hari; besarnya saldo tidak ikut. Parameter: `top`, `boards`, `investors`, `window` (Days), `threshold`.

### 5k.2 Bacaan AI atas permintaan (belum dikonfirmasi user)

Ditambahkan satu ukuran **besarnya** akumulasi, dalam persen turnover atau persentil (bukan Rupiah), yang berpasangan dengan FL29 di panel yang sama (garis kedua) atau sebagai indikator baru. Calon ukuran:

| Kode | Ukuran | Satuan |
|---|---|---|
| A | Rata-rata saldo harian dalam `days` sesi | % turnover |
| B | Rata-rata saldo harian hanya pada hari akumulasi | % turnover |
| C | Saldo tertimbang turnover: jumlah `(NB + NS)` / jumlah gross beli semua broker, dalam `days` sesi | % turnover |
| D | Persentil A atau C terhadap riwayat saham itu sendiri (baseline, misalnya 250 nilai sebelumnya) | 0-100 |

**Keputusan user 2026-11-05:** sesudah AI membedakan A dan C (A memberi bobot sama tiap hari, C memberi bobot menurut turnover; pada BBRI 3 Nov A +1,34% berbanding C −4,11%) dan menyebut pilihan lain (indikator yang ada dengan jendela 20), user menjawab "C".
Ukuran yang dipilih (definisi, mengikuti kelompok harian FL29): `C = 100 × Σ_k (NB_k + NS_k) / Σ_k TBV_k` untuk `k` dalam `days` sesi terakhir, dengan `NB_k` net (`BV − SV`) tiga pembeli bersih terbesar sesi `k`, `NS_k` net tiga penjual bersih terbesar sesi `k` (negatif), dan `TBV_k` gross beli semua broker sesi `k`. Tidak memakai `threshold`. Parameter lain mengikuti FL29 (`top`, `boards`, `investors`, `days`).

**Dijawab user 2026-11-05 (persen, bukan Rupiah):** setelah AI menanyakan apakah yang ditambahkan C dalam persen, garis kumulatif Rupiah, atau keduanya, user menjawab "Saya setuju harus in percent, which is point 1" (butir 1 = hanya C dalam persen). Penyebut C adalah **turnover kumulatif** (jumlah turnover harian selama jendela), bukan rata-rata: BBRI 3 Nov 2026, 20 sesi, jumlah turnover harian (gross beli semua broker per sesi, Rp miliar) = 11.688,7 (10 sesi pertama) + 9.844,4 (10 sesi berikutnya) = **21.533,0** (selisih pembulatan 0,1); pembilang `Σ(NB + NS)` = −884,1; **C = 100 × (−884,1) ÷ 21.533,0 = −4,11%**. Pembilang dan penyebut harus sama-sama jumlah (atau sama-sama rata-rata: −44,2 ÷ 1.076,65 = −4,11%); mencampur jumlah pembilang dengan rata-rata penyebut akan salah (dikali 20). Persentil (D) tidak diminta, sehingga tidak ditambahkan (bacaan AI atas jawaban "point 1"); garis kumulatif Rupiah tidak ditambahkan.

**Disetujui user 2026-11-05 ("Ok, setuju dengan usulan"):** (1) garis kedua di panel FL29 yang sama, bukan indikator baru; (2) FL24 dengan window 20 dibiarkan berdampingan; (3) hari tanpa data broker tetap dihitung bukan akumulasi dengan pembagi tetap `days`. To-do 12 tidak lagi memiliki pertanyaan terbuka kecuali bahwa kesebandingan antar saham belum diuji (hanya BBRI).

### 5k.3 Bukti pada data (BBRI, semua investor, semua papan, N = 3, days 20, threshold 0%, dihitung 2026-11-05)

- 3 Nov 2026: FL29 = 55% (11 dari 20 sesi). A = +1,34% (persentil 76 terhadap 250 nilai sebelumnya). B: rata-rata +13,1% pada 11 hari akumulasi; rata-rata −13,0% pada sembilan hari lain. C = −4,11% (persentil 55).
- **FL29 yang sama, besar akumulasi berbeda:** FL29 = 55% terjadi pada 30 dari 252 sesi, dengan A dari −1,0% (23 Jan 2026) sampai +6,5% (2 Mar 2026); FL29 = 40% pada 36 sesi dengan A dari −7,5% sampai +0,6%.
- Korelasi FL29 dengan A 0,94 dan dengan C 0,89 (252 sesi), jadi pada BBRI ukuran besarnya sebagian besar searah dengan jumlah hari; tambahan informasinya terutama pada selisih pada FL29 yang sama.
- Tanda A dan C berbeda pada 21 dari 252 sesi (korelasi 0,96). Saldo enam broker teratas yang dipilih dari seluruh jendela 20 sesi (FL24 dengan `window` 20): −3,73% pada 3 Nov, korelasi dengan C 0,88, selisih mutlak rata-rata dengan C 2,6 poin.
- Dengan filter investor Foreign saldo harian tidak terbatas (nilai harian sampai −190%), sehingga A dan C dalam persen menjadi tidak stabil; persentil (D) lebih cocok.

### 5k.4 Pertanyaan terbuka (saat to-do ini diambil)

1. **Panel yang sama (garis kedua) atau indikator baru yang berpasangan.** Keduanya disebut user; belum dipilih.
2. ~~Ukuran mana.~~ **Dipilih user 2026-11-05: C** (saldo tertimbang turnover).
3. **Persentil D di atas C atau persen saja.** User memilih C (persen turnover); apakah persentilnya ikut ditambahkan agar sebanding antar saham belum dijawab. Persentil memerlukan baseline; C sudah relatif terhadap turnover tetapi hanya dihitung pada satu saham di sini.
4. **Sebanding antar saham:** saldo dalam persen turnover mungkin sebanding antar saham, tetapi belum diuji; hanya BBRI yang dihitung.
5. **Kedekatan dengan indikator yang ada:** saldo jendela 20 sesi (FL24 dengan `window` 20) mirip dengan C, tetapi memilih enam broker dari net seluruh jendela, bukan per hari. User memilih C, bukan pemakaian ulang indikator yang ada; apakah keduanya dipertahankan berdampingan belum dibahas.
6. Perlakuan hari tanpa data broker (sekarang dihitung bukan akumulasi dan pembagi tetap `days`).

### 5k.5 Batas

Satu saham (BBRI), satu tanggal untuk contoh. Dihitung dari data broker mentah, belum dicocokkan dengan BFF yang hidup. Tidak ada klaim bahwa ukuran mana pun prediktif. Tidak ada kode yang diubah.

## 5l. To-do: indikator baru "Buy VWAP · Rolling · Top-N per hari" (cara B), terpisah dari FL17

**Catatan user 2026-11-05 (kata-katanya):** "Jadi aja kita tambahkan untuk opsi top N per hari yang nomor B. Ini dijadikan indikator terpisah saja nanti. You can review dan to do."
"Nomor B" merujuk pada penjelasan AI atas tiga cara membangun harga rata-rata pembelian bergulir (A: kohort dikunci dari jendela, B: Top-N per hari, C: peringkat dari jendela sebelumnya). FL17 (cara A) tidak diubah, dan cara C belum diminta.
Ini daftar to-do, bukan jadwal eksekusi: belum ada tanggal dan belum ada perintah "go". Kode tidak diubah.

### 5l.1 Kondisi sekarang **[T]** (`flow.ts:310-313`, `cohort:208`)

FL17 menentukan Top-N **sekali per hari grafik** dari net beli (`BV − SV`) sepanjang jendela (bawaan 20 sesi), mengunci broker itu untuk jendela tersebut, lalu menjumlahkan **seluruh** gross beli dan lot beli mereka pada semua sesi di jendela:
`Σ BV(C) / (100 × Σ BL(C))`. Dalam satu jendela, brokernya sama untuk semua sesi; antar hari grafik kohort bisa berganti.

### 5l.2 To-do: definisi cara B (bacaan AI atas kata-kata user, belum dikonfirmasi)

Untuk hari `t` dan jendela `W`: pada **tiap sesi `k`** dalam jendela, ambil Top-N pembeli bersih **sesi itu sendiri** (net `BV − SV` hari itu), jumlahkan gross beli (Rp) dan gross beli (lot) mereka **pada sesi itu**; lalu:
`nilai_t = Σ_k BV(Top-N_k, k) / (100 × Σ_k BL(Top-N_k, k))`, `k` dari `t − W + 1` sampai `t`.
Brokernya boleh berbeda tiap sesi dan tidak dikunci. Ukuran di pembilang dan penyebut tetap **gross** beli; peringkat memakai **net** beli harian.

### 5l.3 Bukti pada data (BBRI, 252 sesi, Top-3, jendela 20, semua investor, semua papan, dihitung 2026-11-05)

| | 3 Nov 2026 | Perubahan harian rata-rata | Perubahan harian maksimum |
|---|---:|---:|---:|
| A (FL17 sekarang) | Rp2.795 | Rp13,0 | Rp186 |
| B (Top-N per hari) | Rp2.802 | Rp11,9 | Rp130 |
| C (peringkat dari jendela sebelumnya; tidak diminta) | Rp2.774 | Rp13,6 | Rp107 |

Korelasi A dengan B 0,999; selisih mutlak rata-rata Rp14 (maksimum Rp103). Kohort A berganti pada 79 dari 252 sesi. Pada saham likuid dengan banyak broker kedua cara hampir sama; pada saham tipis perbedaannya belum diukur.

### 5l.4 Pertanyaan terbuka (saat to-do ini diambil)

1. **Nama dan kode** indikator baru, ditetapkan saat dikerjakan. Usulan nama: "Buy VWAP · Rolling · Daily Top-N".
2. **Parameter:** `top` (3), `boards`, `investors`, `window` (usulan 20), peringkat harian menurut net beli. Apakah pilihan peringkat (`rank`) seperti FL17 ikut disediakan.
3. **Sesi dengan pembeli bersih kurang dari N:** perilaku (memakai yang ada, atau kosong).
4. **Arti** cara B: "harga beli para pembeli bersih terbesar tiap hari", bukan harga beli sebuah kelompok yang tetap; perlu dijelaskan di tooltip.
5. **FL17 tetap cara A**; apakah opsi C (peringkat dari jendela sebelumnya) ikut ditambahkan belum diputuskan.

### 5l.5 Batas

Satu saham (BBRI). Dihitung dari data broker mentah (semua papan), belum dicocokkan dengan BFF yang hidup. Tidak ada klaim bahwa cara B lebih prediktif. Tidak ada kode yang diubah.

## 5m. To-do: harga rata-rata penjualan (gross jual) untuk FL17 dan FL18

**Catatan user 2026-11-05 (kata-katanya):** "Oke, saya rasa untuk F5 18 sudah benar, tapi ini kan hanya metriknya hanyalah gross beli ya, which is kita menghitung berapa rata-rata harga average beli broker-broker yang akumulasi atau melakukan net buy pada kurun waktu tertentu. Boleh nggak ditambahkan satu indikator yang represent sell atau gross sell? Mirip FL18 juga. Berlaku juga untuk FL17."
("F5 18" dibaca FL18.) Ini daftar to-do, bukan jadwal eksekusi: belum ada tanggal dan belum ada perintah "go". Kode tidak diubah.

### 5m.1 Kondisi sekarang **[T]** (`flow.ts:310-313`, `:327-331`, `:182-186`, registry)

FL17 dan FL18 menghitung `Σ BV(C) / (100 × Σ BL(C))`: harga rata-rata **gross beli** kelompok, sisi jual tidak masuk. Parameter `rank` sudah menawarkan **net beli, gross beli, dan net jual** (`SCORE`, `flow.ts:182-186`), jadi kelompok Top-N net **jual** sudah bisa dipilih; yang belum ada adalah sisi jual pada ukuran harganya (`Σ SV(C) / (100 × Σ SL(C))`).

### 5m.2 To-do (bacaan AI atas kata-kata user, belum dikonfirmasi)

**Dikonfirmasi user 2026-11-05:** FL17 dan FL18 menghitung nilai beli dibagi lot beli, dan yang dibutuhkan adalah **dua indikator tambahan** yang menghitung nilai jual dibagi lot jual: "Yang saya butuhkan adalah dua indikator tambahan jual dan lot jual."
Dua indikator baru, terpisah, masing-masing `Σ SV(C) / (100 × Σ SL(C))` (gross jual, Rp per lembar):
- **Versi jual dari FL17:** jendela bergulir, kohort dikunci per jendela (cara A), parameter sama dengan FL17 (`scope`, `brokers`, `top`, `rank`, `boards`, `investors`, `window`).
- **Versi jual dari FL18:** anchor, kohort beku, parameter sama dengan FL18 (termasuk `anchor`).
**Dijawab user 2026-11-05:** "Persis seperti FL 17 dan 18." Artinya parameter dan nilai bawaan sama dengan FL17 dan FL18, termasuk `rank` bawaan **net beli** (bacaan AI atas jawaban satu kalimat itu); hanya ukurannya yang diganti menjadi nilai jual dibagi lot jual. Karena `rank` menawarkan net beli, gross beli, dan net jual, kelompok penjual bersih dapat dipilih dengan mengubah `rank`.

### 5m.3 Bukti pada data (BBRI, semua investor, semua papan, Top-3, dihitung 2026-11-05; penutupan 3 Nov Rp2.660)

| Periode | Kelompok | Net (Rp miliar) | Harga rata-rata **beli** | Harga rata-rata **jual** |
|---|---|---:|---:|---:|
| Anchor 10 Agu (60 sesi) | Pembeli bersih NI, OD, CC | +1.988,1 | Rp2.947 | Rp3.042 |
| Anchor 10 Agu (60 sesi) | Penjual bersih ZP, AK, BB | −2.501,4 | Rp3.086 | Rp2.980 |
| Jendela 20 sesi | Pembeli bersih NI, CC, OD | +2.538,9 | Rp2.795 | Rp2.809 |
| Jendela 20 sesi | Penjual bersih ZP, AK, KZ | −3.342,5 | Rp2.845 | Rp2.744 |

### 5m.4 Pertanyaan terbuka (saat to-do ini diambil)

1. ~~Kelompok dan bawaan `rank` untuk sisi jual.~~ **Dijawab user 2026-11-05: "Persis seperti FL 17 dan 18"**, jadi bawaan `rank` net beli; kelompok penjual bersih dipilih dengan `rank` net jual.
2. ~~Bentuk: parameter sisi atau indikator terpisah.~~ **Dijawab user 2026-11-05: dua indikator tambahan terpisah** (jual dan lot jual).
3. **Nama dan kode** ditetapkan saat dikerjakan.
4. **Kaitan dengan to-do 13** (Top-N per hari): apakah sisi jual berlaku juga di sana.
5. Perlakuan bila kelompok tidak punya penjualan (penyebut nol): kosong.

### 5m.5 Batas

Satu saham (BBRI), satu tanggal. Dihitung dari data broker mentah (semua papan), belum dicocokkan dengan BFF yang hidup. Tidak ada klaim bahwa harga rata-rata jual memprediksi apa pun. Tidak ada kode yang diubah.

## 5n. To-do: jarak harga terhadap Buy VWAP dalam persen (anchor), sejajar FL20 dan FL39

**Catatan user 2026-11-05 (kata-katanya):** "Tolong tambahkan saja by vweb anchor dan by vweb rolling tapi versi percentage distance. seperti FL20. Konfirmasi kalau kamu paham." ("vweb" dibaca VWAP.)
Ini daftar to-do, bukan jadwal eksekusi: belum ada tanggal dan belum ada perintah "go". Kode tidak diubah.

### 5n.1 Kondisi sekarang **[T]** (`flow.ts:553`, `:420`, registry, `FORMULAS.md:105`)

- **FL18** (Buy VWAP · Anchored) dan **FL17** (Buy VWAP · Rolling) menghasilkan harga (garis di grafik harga); keduanya tidak punya versi jarak dalam persen.
- **FL20** (Implied Cost · Distance %) = `100 × (close / FL19 − 1)`; ini versi jarak untuk harga pokok perkiraan (FL19).
- **FL39** (Buy VWAP · Rolling · Distance %) **sudah ada**: `100 × (close / FL17 − 1)` dengan kelompok, filter, dan jendela FL39 sendiri. Nilai bawaan FL39: `window` 10, `boards` Regular, `investors` keduanya (status PROPOSED); bawaan FL17: `window` 20, semua papan.
- Jarak terhadap FL18 (anchor) **belum ada**.

### 5n.2 Bacaan AI atas permintaan (menunggu konfirmasi user)

1. **Baru:** "Buy VWAP · Anchored · Distance %" = `100 × (close / FL18 − 1)`, dengan kelompok beku, anchor, dan parameter yang sama dengan FL18, garis acuan 0, ditampilkan di panel seperti FL20.
2. **Rolling:** jarak terhadap FL17 sudah ada sebagai FL39.

**Dikonfirmasi user 2026-11-05:** "Oh yes, FL39 udah ada ya. Benar, berarti yang sisa yang tinggal anchor aja. FL18 benar nggak?" Jawaban AI: ya, indikator baru berbasis FL18. Jadi yang dikerjakan hanya indikator **anchored**; FL39 dengan bawaannya dianggap cukup untuk sisi rolling.

### 5n.3 Contoh nilai (BBRI, 3 Nov 2026; penutupan Rp2.660; semua investor; Top-3 menurut net beli)

| Garis | Nilai | Jarak penutupan |
|---|---:|---:|
| FL18, anchor 10 Agu 2026 (60 sesi) | Rp2.947,3 | **−9,7%** |
| FL17, jendela 20 sesi, semua papan (bawaan FL17) | Rp2.795 | **−4,8%** |
| FL17, jendela 10 sesi (bawaan FL39; papan Regular dan semua papan memberi hasil sama) | Rp2.841 | **−6,4%** |

### 5n.4 Pertanyaan terbuka (saat to-do ini diambil)

1. ~~Apakah FL39 sudah memenuhi permintaan "by VWAP rolling".~~ **Dijawab user 2026-11-05: ya, yang tersisa hanya anchored.**
2. Nama dan kode indikator baru (anchored), ditetapkan saat dikerjakan.
3. Apakah versi jarak juga dibutuhkan untuk dua indikator harga rata-rata penjualan (to-do 14).
4. Status FL19 dan FL20 tidak berubah oleh to-do ini; penilaian kegunaan FL19 tetap terbuka (user belum memilih opsi).

### 5n.5 Batas

Satu saham (BBRI), satu tanggal. Dihitung dari data broker mentah (semua papan) dan harga penutupan tabel harga, belum dicocokkan dengan BFF yang hidup. Tidak ada klaim bahwa jarak ke VWAP memprediksi apa pun. Tidak ada kode yang diubah.

## 5o. To-do: FL39 dihitung dengan parameter FL17

**Catatan user 2026-11-05 (kata-katanya):** pertanyaan "FL17 sama FL39, apakah secara parameter di set sama atau beda? Jika beda, kita samakan saja. FL39 disamakan dengan FL37." Setelah AI menunjukkan perbedaannya dan menanyakan apakah yang dimaksud FL17 atau FL37, user menjawab: "17 dan 39. Jadikan FL17 menghitung secara price, tapi FL39 menghitung secara distance. Nah, distance ini harus dihitung menggunakan parameter yang ada di FL17."
Ini daftar to-do, bukan jadwal eksekusi: belum ada tanggal dan belum ada perintah "go". Kode tidak diubah.

### 5o.1 Kondisi sekarang **[T]** (registry, `flow.ts:417`, `:553`)

| Parameter | FL17 | FL39 |
|---|---|---|
| scope, top, rank, ranking | Top-N, 3, net beli, harian | sama |
| `boards` | semua papan (DECIDED) | Regular saja (PROPOSED) |
| `investors` | Foreign dan Domestic (DECIDED) | Foreign dan Domestic (PROPOSED) |
| `window` | 20 (PROPOSED) | 10 (PROPOSED) |
| `levels` | tidak ada | 0 (PROPOSED) |

FL39 = `100 × (close / FL17 − 1)`, dihitung dengan `rollingVwap(c, p, 10)` (`flow.ts:553`); FL17 dengan `rollingVwap(c, p, 20)` (`flow.ts:417`). Perbedaannya hanya `window` dan `boards` bawaan.

### 5o.2 To-do

- FL17 tetap menghasilkan **harga** (garis di grafik harga); FL39 tetap menghasilkan **jarak** penutupan terhadap harga itu dalam persen.
- Jarak FL39 dihitung dengan **parameter FL17**: bawaan FL39 menjadi `window` 20, `boards` semua papan, `investors` Foreign dan Domestic.
- Dampak pada BBRI 3 Nov 2026 (penutupan Rp2.660, semua investor, Top-3): sekarang FL39 memberi VWAP Rp2.841 dan jarak −6,4%; dengan parameter FL17 menjadi VWAP Rp2.795 dan jarak −4,8%. Perbedaan papan tidak mengubah nilai pada BBRI untuk jendela itu.

### 5o.3 Pertanyaan terbuka (saat to-do ini diambil)

1. ~~Bentuk "menggunakan parameter FL17".~~ **Dijawab user 2026-11-05:** "FL39 hanya pada menggunakan default aja ... Ketika FL39 di-hit, maka ya dia menggunakan FL17 default system. Ya kalau nanti seandainya user mau adjust FL17 manually, ya FL39 dia juga harus adjust manually. Confirm." Jadi **bawaan FL39 disamakan dengan bawaan FL17** (dua indikator, dua perangkat parameter); FL39 **tidak** mengikuti pengaturan FL17 yang diubah pengguna. Bawaan FL17 yang berlaku (registry): scope Top-N cohort, top 3, rank net beli, ranking harian, papan Regular, Nego, Cash, investor Foreign dan Domestic, window 20. Usulan AI sebelumnya agar FL39 membaca pengaturan FL17 (dan agar pola itu diperluas ke FL19/FL20) **ditolak user**; tidak ada mekanisme baru.
2. Keselarasan dengan to-do 15 (jarak terhadap FL18, yang memakai parameter FL18) dan to-do 14 (versi jual).
3. `levels` (garis acuan 0) dipertahankan di FL39.

### 5o.4 Batas

Satu saham (BBRI), satu tanggal. Dihitung dari data broker mentah (semua papan) dan harga penutupan tabel harga, belum dicocokkan dengan BFF yang hidup. Tidak ada kode yang diubah.

## 5p. To-do: FL34 diberi ukuran perubahan (daily to daily dan lainnya)

**Catatan user 2026-11-05 (kata-katanya):** "Alright, untuk FL34, to-do list-nya adalah kita perlu tambahkan change. Jadi change daily to daily, dan lain sebagainya. Paham?"
Ini daftar to-do, bukan jadwal eksekusi: belum ada tanggal dan belum ada perintah "go". Kode tidak diubah.

### 5p.1 Kondisi sekarang **[T]** (`flow.ts:516-526`, `FORMULAS.md:100`)

`FL34 = 100 × (net institusi − net ritel) / turnover`, dijumlahkan sepanjang `window` (20 sesi); satu garis, tanpa ukuran perubahan. Net adalah gross beli dikurangi gross jual; turnover adalah gross beli semua broker.

### 5p.2 Bacaan AI atas permintaan (belum dikonfirmasi user)

Ukuran **perubahan nilai FL34**: nilai hari ini dikurangi nilai sesi sebelumnya (daily to daily), dalam poin persen, dan ukuran sejenis untuk jarak waktu lain (usulan: 5 sesi dan 20 sesi). "Dan lain sebagainya" belum dirinci user.

### 5p.3 Bukti pada data (BBRI, semua investor, semua papan, `window` 20, dihitung 2026-11-05; klasifikasi broker dari tabel fitur 3 Nov)

| Tanggal | FL34 | Perubahan harian (poin) | Perubahan 5 sesi (poin) |
|---|---:|---:|---:|
| 29 Okt | −10,43% | +0,75 | +2,39 |
| 30 Okt | −8,44% | +1,99 | +4,41 |
| 2 Nov | −8,67% | −0,23 | +4,03 |
| 3 Nov | −9,28% | −0,61 | +2,16 |

Sebaran 252 sesi, |perubahan| median: harian 1,37 poin (P10 −3,38, P90 +2,90, rentang −20,0 sampai +8,4), 5 sesi 5,11 poin, 20 sesi 14,29 poin. Tiga perubahan harian terbesar: 22 Okt 2025 (−20,0), 16 Okt 2026 (−18,5), 29 Mei 2026 (−9,7). Karena FL34 adalah jumlah bergulir 20 sesi, perubahan harian sama dengan (hari yang masuk − hari yang keluar) pada pembilang, ditambah efek perubahan turnover.

### 5p.4 Pertanyaan terbuka (saat to-do ini diambil)

1. ~~Apa yang diubah.~~ **Dijawab user 2026-11-05:** "Apa yang dirubah? Tidak ada yang dirubah. FL34 tetap as is, tapi ditambahkan toggle atau misalkan line change-nya seperti apa." Jadi FL34 tidak berubah; yang ditambahkan adalah garis perubahan (atau tombol pilihan/toggle) atas nilai FL34. Bentuknya, garis tetap atau toggle, belum dipilih user.
2. ~~"Dan lain sebagainya": jarak waktu.~~ **Disetujui user 2026-11-05 ("Oke, setuju")** atas usulan AI: harian ditambah 5 sesi dan 20 sesi; cara memilih jarak di tampilan belum dirinci (bacaan AI: parameter jarak perubahan, bawaan harian).
3. ~~Satuan.~~ **Disetujui:** poin persentase (selisih nilai FL34, bukan persen perubahan).
4. ~~Bentuk: garis kedua di panel yang sama atau indikator terpisah.~~ **Dijawab user 2026-11-05: "Panel gabungan aja"** (ukuran perubahan ditampilkan di panel yang sama dengan FL34; bacaan AI: sebagai garis kedua).
5. ~~Kaitan dengan to-do 11.~~ **Disetujui:** penyebab perubahan (hari masuk dan hari keluar jendela) tidak ditampilkan; to-do 11 sendiri dibatalkan.

**Keputusan user 2026-11-05 tentang bentuk (kata-katanya, dua pesan):** pertama "Tidak usah ada toggle, langsung aja kita display SLI chart, tapi ya di opsinya nanti di settings bisa ada pilihan either mau line chart yang mau di-disable atau tidak, atau bar chartnya mau disable atau tidak." Lalu user mengoreksi tulisannya: "Tidak usah ada toggle, langsung aja kita display **as line chart**, tapi ya di opsinya nanti di settings bisa ada pilihan either mau line chart yang mau di-disable atau tidak, atau bar chartnya mau disable atau tidak." Dan: "Ok untuk jarak perubahan."
**Bacaan AI (koreksi bila berbeda):** tidak ada toggle; panel FL34 langsung menampilkan **dua elemen sekaligus**: FL34 yang ada sekarang sebagai **batang (bar chart, histogram bawaan)** dan ukuran perubahan sebagai **garis (line chart)**; di pengaturan masing-masing elemen dapat dimatikan (garis dimatikan atau batang dimatikan). Bacaan ini mengganti bacaan sebelumnya (garis = FL34, batang = perubahan), karena FL34 sudah ditetapkan tetap as is.
**Jarak perubahan disetujui** ("Ok untuk jarak perubahan"): harian, 5 sesi, dan 20 sesi; bacaan AI: satu jarak terpilih ditampilkan sekali, bawaan harian.
**Pertanyaan yang tersisa:** (1) benar bacaan di atas (batang = FL34, garis = perubahan)? (2) Skala: FL34 pada 252 sesi berkisar −41,6% sampai +18,4% (BBRI), sedangkan perubahan harian berkisar sekitar −3,4 sampai +2,9 poin (P10 sampai P90), sehingga garis perubahan akan tampak hampir datar bila memakai sumbu yang sama; apakah garis memakai sumbu kedua. (3) Hubungan dengan opsi tampilan FL34 yang ada (`plot`: histogram atau garis) bila pengguna memilih garis untuk FL34.

### 5p.5 Batas

Satu saham (BBRI). Klasifikasi broker dibaca dari kolom klasifikasi tabel fitur pada 3 Nov dan dipakai untuk semua tanggal (kesamaannya dengan daftar di terminal belum diperiksa). Dihitung dari data broker mentah (semua papan), belum dicocokkan dengan BFF yang hidup. Tidak ada kode yang diubah.

## 5q. To-do: FL27 tetap, ditambah pemicu akumulasi berbasis broker

**Catatan user 2026-11-05 (kata-katanya):** "Tambahkan ke FL27 metrik tetap as is, tapi tambahkan metric, it triggers kalau ada akumulasi. Akumulasi: Which is rasio top X broker net ataupun gross di atas 1/X rasio top N sell atau gross sell. Konfirmasi."
Ini daftar to-do, bukan jadwal eksekusi: belum ada tanggal dan belum ada perintah "go". Kode tidak diubah. **Definisi pemicu belum dikonfirmasi; yang pasti hanya butir 1 dan 2 di bawah.**

### 5q.1 Kondisi sekarang **[T]** (`flow.ts:466-475`, `CODE_INSPECTION_20261101.md:37`)

FL27 memakai harga dan volume harian saja (tanpa data broker): penanda 1 bila rata-rata volume `recent` (5) sesi dibagi rata-rata volume `baseline` (20) sesi sebelumnya ≥ `volx` (1,5) **dan** |perubahan penutupan 5 sesi| ≤ `move` (3%). Pada BBRI (252 sesi) penanda 1 muncul pada 10 sesi.

### 5q.2 Jawaban user 2026-11-05 atas lima pertanyaan (kata-katanya)

Jawaban atas daftar pertanyaan AI (nomor sesuai daftar itu; butir 6 sampai 9 dibiarkan kosong oleh user):
1. "Nilai X pembeli / penjual teratas": rasio = jumlah **nilai** pembeli teratas dibagi jumlah **nilai** penjual teratas.
2. "Default 1.5 X": pemicu menyala bila rasio mencapai 1,5 kali (bawaan).
3. "X1.5 - N 3": pengali X = 1,5 dan N = 3 broker (bacaan AI: N = 3 di sisi beli dan sisi jual).
4. "Dua pemicu terpisah": satu untuk **net** dan satu untuk **gross**.
5. "Sebagai penanda": keluaran berupa penanda (seperti FL27), terpisah dari pemicu lama.
10. "Yang mesti dicatat adalah indikator + akumulasi ini optional, which is bisa di toggle on dan off."

### 5q.3 Definisi yang dicatat (bacaan AI atas jawaban itu; butir kecil yang belum dijawab ditandai)

- **FL27 tetap seperti sekarang** (volume naik dan harga diam, tanpa data broker).
- **Pemicu net:** `Σ net beli N pembeli bersih teratas ÷ Σ |net jual| N penjual bersih teratas ≥ X` (N = 3, X = 1,5). Net adalah gross beli dikurangi gross jual tiap broker.
- **Pemicu gross:** `Σ gross beli N pembeli gross teratas ÷ Σ gross jual N penjual gross teratas ≥ X` (N = 3, X = 1,5).
- Keluaran: dua penanda terpisah di bawah candle, **opsional dan bisa dinyalakan atau dimatikan (toggle)**; penanda FL27 lama tetap.
- Untuk semua investor, total net beli sama dengan total net jual (dan gross beli sama dengan gross jual), sehingga rasio nilai sama dengan rasio porsi terhadap total sisinya (angka BBRI di bawah memakai kenyataan ini).

**Belum dijawab user (pertanyaan terbuka):**
1. Cakupan waktu: per hari (yang dihitung di 5q.4) atau jendela bergulir.
2. Keadaan awal toggle: nyala atau mati secara bawaan.
3. "Mencapai" atau "di atas" 1,5 (bacaan AI: ≥, seperti ambang `volx` FL27).
4. Bacaan "X1.5 - N 3": X sebagai pengali dan N sebagai jumlah broker; bila sebaliknya, koreksi.
5. Apakah pemicu net dan gross masing-masing punya N dan X sendiri atau berbagi.

### 5q.4 Bukti pada data (BBRI, semua investor, semua papan, N = 3, X = 1,5, per hari, 252 sesi, dihitung 2026-11-05)

- 3 Nov 2026: net Rp217,0 miliar ÷ Rp238,4 miliar = **0,91**; gross Rp355,2 miliar ÷ Rp296,9 miliar = **1,20**. Keduanya di bawah 1,5, jadi tidak ada pemicu.
- Pemicu net (rasio ≥ 1,5): 48 sesi; pemicu gross: 18 sesi; keduanya bersamaan 16 sesi; salah satu 50 dari 252 sesi.
- Pemicu net terbaru: 22, 23, 26 Okt dan 2 Nov 2026. Pemicu gross terbaru: 15, 22, 23, 26 Okt 2026.
- Penanda FL27 lama menyala pada 10 sesi; bersamaan dengan pemicu net hanya 1 sesi dan dengan pemicu gross 0 sesi.

### 5q.5 Batas

Satu saham (BBRI). Dihitung dari data broker mentah (semua papan), belum dicocokkan dengan BFF yang hidup. Tidak ada klaim bahwa rasio itu memprediksi apa pun. Tidak ada kode yang diubah.

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
- Cara membaca setiap sel (lihat 7.1; wajib bila indikator punya tanda, ambang, atau dibaca bersama arus asing)
- Temuan (kode F1.., bukti terukur, kriteria C1-C6)
- Pilihan keputusan (pertahankan / edit metrik / ganti visual / gabung / hapus) beserta dampak
- Usulan sementara AI
- Keputusan yang dibutuhkan
- Batas verifikasi
```

### 7.1 Template penjelasan: "Cara membaca setiap sel"

Catatan user 2026-11-04, atas penjelasan FL10: "Cara membaca setiap sel ... Catat template ini kalau menjelaskan ya."
Berlaku untuk setiap penjelasan indikator Flow, baik di chat maupun di kartu. Urutannya:

1. **Ringkasan**: satu-dua kalimat, apa yang diukur dan apa yang **tidak** diukur (nilai, lot, atau jumlah transaksi).
   Rumus dengan sumber kodenya (`file:baris`) dan `FORMULAS.md`.
2. **Arti tiap tanda atau ambang**: positif, negatif, nol, batas atas dan bawah. Bila indikator dibaca bersama ukuran
   lain, nyatakan hubungan yang pasti secara matematis (identitas) dan pisahkan dari tafsiran.
3. **Matriks pada data nyata**: kondisi arus (misalnya asing net beli atau net jual) × tanda atau ambang indikator.
   Sebut saham, investor, papan, jendela, rentang tanggal, jumlah sesi, dan jumlah per sel.
4. **Tabel "Cara membaca setiap sel"** dengan kolom: kondisi | arti | contoh atau catatan. Satu baris per sel, termasuk
   sel yang tidak pernah terjadi (tulis bahwa tidak terjadi di sampel). Contoh memakai angka nyata dengan tanggalnya.
5. **Temuan**: apakah tanda itu informatif (tingkat dasar, median dan sebaran), apakah menduplikasi ukuran lain
   (korelasi), dan apakah ada sirkularitas karena cohort dipilih dari ukuran yang sama.
6. **Batas pembuktian**: jumlah saham dan sesi, tidak ada uji return ke depan, apa yang **belum** diperiksa beserta
   cara memeriksanya. Tafsiran diberi label hipotesis; yang terukur diberi label terukur.
7. **Istilah beli dan jual selalu disebut gross atau net.** Setiap kali penjelasan memakai "nilai beli", "beli" atau "jual", tulis apakah itu gross (`BV`, `SV`, `BL`, `SL`: satu sisi, belum dikurangi) atau net (`BV − SV`, `BL − SL`), untuk pembilang maupun penyebut. Catatan user 2026-11-04: "untuk penjelasan selanjutnya harus specify, buy value itu net atau gross."
8. **Kaitan dengan to-do** di bagian awal dokumen bila ada, lalu satu tawaran pencatatan.

Contoh pertama yang memakai template ini: FL10 pada BBRI (asing, 120 sesi, 8 Mei-3 Nov 2026). Semua broker asing: net beli
28 sel FL10 positif dan 16 negatif; net jual 0 positif dan 76 negatif. Median FL10 -0,33, korelasi dengan net asing 0,80.
Cohort Top-3 net beli harian: net beli 43 positif dan 1 negatif; net jual 59 positif dan 17 negatif, korelasi 0,38.
Hal yang belum diperiksa: ulangan hanya papan Regular.

### 7.2 Pedoman: cara menjelaskan cara kerja sebuah indikator (contoh FL29)

**Catatan user 2026-11-05 (kata-katanya):** "Tambahkan catatan di flow indicator review, which is adalah how we should explain how certain indicator works. Bisa menggunakan contoh terlampir yang saya remark. Jadi nanti cara menjelaskan indikator ini akan ada di suatu tempat, digunakan sebagai guideline untuk referensi."
Contoh yang ditandai user adalah jawaban "Contoh hitungan FL29: BBRI, 3 Nov 2026", yang diminta dengan "Coba kasih contoh hitungannya. Jangan sebut indikator lain." Bagian ini dipakai bila user meminta **contoh hitungan** atau penjelasan "cara kerja"; 7.1 dipakai untuk penjelasan penuh dengan matriks. Bila keduanya diminta, contoh hitungan mendahului matriks.

**Pola (bacaan AI atas contoh yang ditandai user; bila ada butir yang kurang tepat, koreksi di sini):**

1. **Pengaturan konkret dulu:** satu saham, satu tanggal, filter (investor, papan), parameter (N, jendela, ambang), dan definisi istilah (net = gross beli dikurangi gross jual; turnover = gross beli semua broker). Gross atau net selalu disebut (7.1 butir 7).
2. **Langkah 1: hitung satu hari secara rinci**, dengan nama broker dan angka, sampai hasil hari itu. Sertakan satu hari yang lolos dan satu yang tidak bila indikatornya memakai ambang.
3. **Langkah 2: ulangi untuk seluruh jendela dalam satu tabel** (tanggal, komponen, hasil harian, penanda).
4. **Langkah 3: gabungkan menjadi nilai indikator** dengan rumus yang berisi angka sebenarnya.
5. **Kalau parameter diubah:** tabel kecil yang menunjukkan nilai indikator pada beberapa pengaturan.
6. **Hal yang terlihat dari contoh:** dua sampai empat pengamatan konkret dari tabel itu (misalnya: yang dihitung jumlah hari, bukan besarnya).
7. **Variabel utama diuraikan asalnya** (catatan user 2026-11-05: "ketika kamu kasih contoh, make sure main variable yang digunakan itu harus di breakdown asalnya dari mana"): setiap angka yang masuk rumus (misalnya Rp per transaksi, porsi, net) ditampilkan dari komponen mentahnya (gross beli, transaksi, lot, broker mana), per sesi atau per broker, dan angka gabungannya dihitung dari komponen itu (total dibagi total, bukan rata-rata angka harian, bila memang begitu rumusnya).
8. **Aturan gaya:** Bahasa Indonesia sederhana; angka dari data nyata dengan tanggalnya; **tidak menyebut indikator lain** dalam contoh; menyebut bahwa angka dihitung dari data broker mentah, belum dicocokkan dengan BFF yang hidup; menyebut bahwa tidak ada perubahan di repo bila memang begitu.

**Contoh acuan (FL29, BBRI, 3 Nov 2026; semua investor, semua papan, N = 3, days 20, threshold 0%):**

Langkah 1. 3 Nov: tiga pembeli bersih terbesar OD +111,6, CC +73,2, YP +32,3 (Rp miliar), jumlah +217,0; tiga penjual bersih terbesar YU −125,5, BK −66,3, AK −46,7, jumlah −238,4; turnover Rp872,5 miliar; saldo = (217,0 − 238,4) / 872,5 × 100 = −2,5%, bukan hari akumulasi. 2 Nov: ZP +94,8, BK +35,8, XL +6,3 = +136,9; PD −28,0, MG −23,4, CC −22,9 = −74,3; turnover Rp502,8 miliar; saldo +12,4%, hari akumulasi.

Langkah 2 (Rp miliar; "Ya" bila saldo > 0%):

| Tanggal | Net pembeli | Net penjual | Turnover | Saldo | > 0% ? |
|---|---:|---:|---:|---:|---|
| 7 Okt | +107,3 | −55,2 | 363,3 | +14,3% | Ya |
| 8 Okt | +116,6 | −177,1 | 463,2 | −13,0% | tidak |
| 9 Okt | +95,2 | −140,9 | 485,5 | −9,4% | tidak |
| 12 Okt | +134,4 | −69,9 | 495,1 | +13,0% | Ya |
| 13 Okt | +45,2 | −119,8 | 430,4 | −17,3% | tidak |
| 14 Okt | +93,6 | −87,7 | 510,8 | +1,2% | Ya |
| 15 Okt | +109,1 | −48,2 | 350,4 | +17,4% | Ya |
| 16 Okt | +555,9 | −1.294,1 | 3.296,8 | −22,4% | tidak |
| 19 Okt | +580,4 | −1.384,1 | 3.413,3 | −23,5% | tidak |
| 20 Okt | +210,8 | −315,3 | 1.879,9 | −5,6% | tidak |
| 21 Okt | +311,1 | −216,9 | 1.396,5 | +6,7% | Ya |
| 22 Okt | +566,5 | −282,6 | 1.514,5 | +18,7% | Ya |
| 23 Okt | +500,7 | −286,1 | 1.053,7 | +20,4% | Ya |
| 26 Okt | +330,4 | −121,6 | 729,1 | +28,6% | Ya |
| 27 Okt | +269,4 | −208,3 | 1.283,4 | +4,8% | Ya |
| 28 Okt | +182,4 | −125,0 | 927,2 | +6,2% | Ya |
| 29 Okt | +109,7 | −138,8 | 639,3 | −4,5% | tidak |
| 30 Okt | +164,9 | −337,5 | 925,4 | −18,7% | tidak |
| 2 Nov | +136,9 | −74,3 | 502,8 | +12,4% | Ya |
| 3 Nov | +217,0 | −238,4 | 872,5 | −2,5% | tidak |

Langkah 3. Hari "Ya" 11 dari 20; FL29 = 100 × 11 / 20 = 55%. Bila ambang diubah: 3% memberi 50%, 6% memberi 45%, 10% memberi 35%.
Hal yang terlihat: yang dihitung jumlah hari, bukan besarnya saldo (+1,2% dihitung sama dengan +28,6%); dua hari berturnover besar (16 dan 19 Okt) sama-sama dihitung satu hari "tidak"; sesi tanpa data dihitung bukan hari akumulasi dengan pembagi tetap 20.
Catatan lanjutan: pada 3 Nov, jumlah net seluruh 20 sesi −Rp884,3 miliar terhadap turnover Rp21.533,1 miliar (−4,11%) walaupun FL29 55%, karena dua hari besar tadi lebih besar daripada seluruh sebelas hari "Ya" (lihat bagian 5k).
