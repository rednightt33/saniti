# Leaderboard EDGE: spesifikasi 12 tabel (6 teknikal, 6 flow) dan sudut lain

**Status:** masuk to-do list (`PLAN.md` LEADERBOARD, user 2026-11-14: "Ini semua dimasukkan ke to-do list ya"). Belum dibangun.
Disusun 2026-11-13; ambang dan level adalah usulan sampai halamannya dibahas. Rotasi ada di [`ROTATION_SPEC.md`](ROTATION_SPEC.md).
**Sumber angka contoh:** database dev, dibaca dengan role `pgweb` (read-only), as-of **9 Nov 2026** (tanggal terakhir yang
dimiliki semua tabel broker; `Feature_01` sudah sampai 12 Nov). Papan Regular. Gerbang "Luas" pada tanggal itu: total beli
5 sesi ≥ Rp1,85 miliar, 428 dari 855 saham. Semua ambang adalah usulan awal; jumlah saham per level dihitung pada satu
tanggal, jadi kestabilannya belum diuji.
**Bukan rekomendasi investasi.** Setiap tabel menampilkan kandidat untuk ditelaah, bukan sinyal beli atau jual.

---

## 0. Aturan bersama (berlaku untuk ke-12 tabel)

| # | Aturan | Isi | Alasan |
|---|---|---|---|
| A1 | Tanggal data | Satu tanggal "as-of" untuk semua tabel: tanggal terakhir yang dimiliki semua sumber. Tanggal itu tampil di kepala halaman. Bila satu sumber tertinggal, halaman menyebutnya | Gerbang G1 library. Pada 9–12 Nov teknikal lebih baru (12 Nov) daripada broker (9 Nov) |
| A2 | Universe | Saham di `Feature_06` dengan baris pada tanggal itu dan ≥ 5 sesi Regular di 16 tanggal bursa terakhir | Gerbang G2 library |
| A3 | Gerbang likuiditas | Bawaan "Luas" (buang 50% saham dengan total beli 5 sesi terkecil), pilihan "Likuid" (buang 80%) | Keputusan library 2026-11-12. Tanpa gerbang, saham mikro menguasai setiap daftar |
| A4 | Papan | Regular | Nego dan Tunai adalah transaksi blok; dibaca di sudut tersendiri (bagian 3) |
| A5 | Sesi | Sesi saham itu sendiri (5D = 5 sesi terakhir saham itu) | Sama dengan library |
| A6 | Isi tabel | Dua sisi bila ada (contoh: gainers dan losers), masing-masing 20 baris; seri diurutkan menurut ticker | |
| A7 | Kolom tetap di setiap tabel | Ticker, nama, sektor, close, perubahan 1D %, nilai beli 5 sesi | Pembaca selalu bisa menilai ukuran saham |
| A8 | Level | Label berwarna di kolom "Level", diturunkan dari angka yang tampil (dibulatkan dulu, baru diberi label; ERRORS M389) | |
| A9 | Kepala tabel | Rumus dalam satu kalimat, penyebutnya, jendela, dan "bukan sinyal beli/jual" | ERRORS M390: label membawa semua parameter yang mengubah angka |
| A10 | Klik baris | Membuka Terminal untuk ticker itu dengan indikator padanannya (kolom "Padanan" di setiap tabel) | Leaderboard sebagai pintu masuk ke analisis |
| A11 | Kosong | Tabel tanpa baris menyebut sebabnya ("tidak ada saham di atas pita Bollinger hari ini"), bukan tabel kosong tanpa kata | ERRORS M390 |
| A12 | Format | EDGE Design Spec v1.2 (`specFormat.ts`): Rp ringkas, persen 1 desimal, poin bertanda | |

Status data di setiap tabel:
- **Siap**: semua kolom sudah ada, cukup dibaca.
- **Hitung**: dihitung dari tabel yang ada, tanpa sumber baru.
- **Data baru**: butuh sumber yang belum ada.

---

## 1. Teknikal

### T1 — Top gainers / Top losers
- **Pertanyaan:** saham apa yang paling naik dan paling turun?
- **Ukuran:** `Feature_01_Stock_Daily.return_1d_pct`; pilihan jendela 1D / 5D (`return_5d_pct`) / 20D (`return_20d_pct`).
- **Urutan:** menurun (gainers), menaik (losers).
- **Kolom khusus:** volume ÷ rata-rata 20 hari (`volume_ratio_20d`).
- **Level:** label **"Volume tipis"** bila `volume_ratio_20d` < 0,5. Kenaikan dengan volume setengah dari biasanya mudah dibaca salah.
- **Data 9 Nov (Luas, 1D):** P95 +8,1%, P5 −5,7%. Teratas SOTS +25,0%, PTSP +24,9%, BAJA +21,7%. Terbawah LAPD −8,3%, BOBA −7,0%.
- **Padanan:** Terminal harga; Screener `chg_1d_pct`.
- **Status:** Siap.
- **Catatan:** label ARA/ARB butuh aturan batas auto-reject bursa per rentang harga, yang belum ada di database. Tidak dimasukkan.

### T2 — Lonjakan volume
- **Pertanyaan:** saham apa yang diperdagangkan jauh di atas kebiasaannya?
- **Ukuran:** `volume_zscore_20d` (volume hari ini dibanding rata-rata dan simpangan baku 20 hari).
- **Urutan:** menurun. Dua sisi menurut arah harga hari itu: **volume naik + harga naik**, dan **volume naik + harga turun**.
- **Kolom khusus:** `volume_ratio_20d`, return 1D.
- **Level:** z ≥ 2 **"Tinggi"**, z ≥ 3 **"Ekstrem"**.
- **Data 9 Nov:** 14 saham z ≥ 2, 7 saham z ≥ 3. Teratas INAI 4,17, JTPE 4,00, FLMC 3,92.
- **Padanan:** Terminal Volume; Screener `volspike`, preset "Frequency Spike".
- **Status:** Siap.

### T3 — Posisi terhadap pita Bollinger, dengan tren (contoh user)
- **Pertanyaan:** saham apa yang menembus pita atas sementara trennya naik, dan cerminnya?
- **Ukuran utama:** **%B** = (close − `bb_lower_20`) ÷ (`bb_upper_20` − `bb_lower_20`). Nilai 1 berarti di pita atas, 0 di pita bawah.
- **Syarat tren (pilihan):** close > EMA (20 / **50** / 200: `ema_50`, `ema_200`; EMA 20 belum ada sebagai kolom, harus dihitung).
- **Urutan:** %B menurun (sisi atas, syarat close > EMA) dan menaik (sisi bawah, syarat close < EMA).
- **Kolom khusus:** jarak dari pita dalam ATR = (close − `bb_upper_20`) ÷ `atr_14`, supaya saham mahal dan murah sebanding.
- **Level:** %B > 1 **"Tembus atas"**, 0,8–1 **"Dekat atas"**, < 0 **"Tembus bawah"**, 0–0,2 **"Dekat bawah"**.
- **Data 9 Nov:** hanya 2 saham tembus atas dengan close > EMA 50 (FLMC, SOTS) dan 3 tembus bawah. **Itulah alasan ukurannya %B, bukan syarat "di luar pita":** tabel versi "di luar pita" hampir kosong di pasar yang lemah, sedangkan %B selalu punya urutan.
- **Padanan:** Terminal Bollinger Bands dan EMA; Screener `squeeze`/`breakout`.
- **Status:** Siap (EMA 20: Hitung).

### T4 — Dekat harga tertinggi / tembus swing high
- **Pertanyaan:** saham apa yang berada di dekat atau baru mencetak harga tertingginya?
- **Ukuran:** jarak close dari tertinggi 52 minggu = (close ÷ tertinggi 252 sesi − 1) × 100, sama dengan rumus Screener `hi52`. Sementara bisa memakai 60 sesi (`Feature_01.drawdown_60d_pct`).
- **Urutan:** menurun (yang paling dekat puncak di atas). Sisi kedua: dekat terendah 52 minggu (`lo52`).
- **Kolom khusus:** penanda `Feature_04.break_swing_high` (baru menembus swing high terakhir), return 20D.
- **Level:** 0 sampai −1% **"Di puncak"**, −1 sampai −5% **"Dekat puncak"**.
- **Data 9 Nov (60 sesi):** 4 saham di puncak, 15 dalam 3% dari puncak, 3 baru menembus swing high. Median saham Luas 35,7% di bawah puncak 60 hari.
- **Padanan:** Screener `hi52`, `new_high`, preset "52W Breakout + Volume".
- **Status:** 60 sesi Siap; 52 minggu Hitung (dari `Price_Stock_Indonesia_IDX`).

### T5 — RSI ekstrem
- **Pertanyaan:** saham apa yang paling jenuh beli atau jenuh jual?
- **Ukuran:** `Feature_04.rsi_14`.
- **Urutan:** menurun (jenuh beli), menaik (jenuh jual).
- **Kolom khusus:** penanda **"Di atas EMA 200"** (close > `ema_200`): jenuh jual di dalam tren naik dibaca lain dari jenuh jual di tren turun.
- **Level:** ≤ 30 **"Jenuh jual"**, ≤ 20 **"Sangat jenuh jual"**, ≥ 70 **"Jenuh beli"**, ≥ 80 **"Sangat jenuh beli"**.
- **Data 9 Nov:** 88 saham RSI ≤ 30, hanya 1 saham ≥ 70, 0 saham jenuh jual di atas EMA 200. Median RSI 37,4. **Tabel ini timpang di pasar yang lemah:** sisi jenuh beli bisa hampir kosong, dan pesan kosongnya harus menjelaskan itu (A11).
- **Padanan:** Terminal RSI; preset Screener "Oversold in Uptrend".
- **Status:** Siap.

### T6 — Tren terkuat dan persilangan EMA
- **Pertanyaan:** saham apa yang trennya paling kuat, atau baru berbalik?
- **Ukuran:** `adx_14`, hanya saham dengan `ema_50` > `ema_200` (tren naik). Sisi kedua: ADX tertinggi dengan `ema_50` < `ema_200` (tren turun).
- **Kolom khusus:** penanda **"Golden cross"** / **"Death cross"** bila EMA 50 memotong EMA 200 dalam 10 sesi terakhir.
- **Level ADX:** < 20 **"Lemah"**, 20–25 **"Mulai"**, 25–40 **"Kuat"**, ≥ 40 **"Sangat kuat"** (konvensi umum ADX).
- **Data 9 Nov:** 126 saham dalam tren naik; 60 dengan ADX ≥ 25 dan 11 dengan ADX ≥ 40. Teratas JRPT 69,1, NICK 52,3, ARII 51,6. Persilangan 6→9 Nov: 0 golden cross, 4 death cross (ICON, ELSA, MUTU, UCID). Karena itu penandanya memakai jendela 10 sesi, bukan hanya hari ini.
- **Alternatif slot:** **Squeeze**, yaitu lebar Bollinger tersempit terhadap riwayat saham itu sendiri (persentil 120 sesi). Ini cocok dengan minat pra-reli (usulan pra-reli opsi 6). Status: Hitung.
- **Padanan:** Terminal ADX dan EMA; preset "Golden Cross", "Supertrend Flip".
- **Status:** Siap (penanda 10 sesi: Hitung).

---

## 2. Flow

### F1 — Top net foreign buy / sell
- **Pertanyaan:** ke saham mana uang asing masuk dan keluar?
- **Ukuran:** `Feature_06.foreign_net_1d` (Rp); pilihan 5D (`foreign_net_5d`) / 20D (`foreign_net_20d`).
- **Urutan:** menurun (beli), menaik (jual).
- **Kolom khusus:** rasio net asing = net asing ÷ total beli (`foreign_net_turnover_ratio_1d/5d/20d`), dalam %.
- **Level (dari rasio):** ≥ 5% **"Material"**, ≥ 20% **"Dominan"**, dengan cerminnya untuk sisi jual. Alasannya: Rupiah mentah selalu dikuasai saham terbesar, dan rasio menunjukkan seberapa besar artinya bagi saham itu sendiri. Batas 5% sama dengan syarat S1 library.
- **Data 9 Nov (1D):** beli BBCA +Rp523,1 miliar, ASII +Rp200,1 miliar; jual BMRI −Rp134,5 miliar, BBNI −Rp99,5 miliar, BBRI −Rp94,7 miliar. Rasio 1D: P90 +22,8%, P10 −24,8%.
- **Padanan:** Terminal FL11 (Foreign, Net Flow / Turnover); panel Foreign × Domestic.
- **Status:** Siap.

### F2 — Imbalance asing (contoh user)
- **Pertanyaan:** di saham mana pembelian asing jauh melebihi penjualannya, atau sebaliknya?
- **Ukuran:** `foreign_buy_1d` ÷ `foreign_sell_1d` (×); pilihan 5D (jumlah 5 sesi).
- **Penjaga wajib:** beli + jual asing ≥ **Rp1 miliar** pada jendela itu, dan jual asing > 0. Tanpa lantai ini, saham dengan beli asing Rp10 juta dan jual Rp1 juta mendapat 10×.
- **Urutan:** menurun (beli dominan), menaik (jual dominan).
- **Kolom khusus:** beli asing, jual asing, net asing (Rp).
- **Level:** ≥ 2× **"Beli dominan"**, ≥ 4× **"Sangat dominan"**; ≤ 0,5× **"Jual dominan"**, ≤ 0,25× **"Sangat dominan (jual)"**.
- **Data 9 Nov (1D):** dengan lantai Rp1 miliar tersisa 194 saham; 29 saham ≥ 2× dan 31 saham ≤ 0,5×. Teratas CMNT 45,0×, BJTM 42,8×; terbawah MSTI dan JRPT (hampir tanpa beli asing). Rasio ekstrem seperti 45× tampil sebagai "> 10×", supaya urutan tidak dikuasai satu pencilan.
- **Padanan:** Terminal FL46 Flow Ratio (pembilang beli kotor asing, penyebut jual kotor asing). FL46 dikunci keputusan user, jadi hanya dipakai sebagai tautan, tidak diubah.
- **Status:** Siap (5D: Hitung).

### F3 — Top 3 buyer net vs Top 3 seller net (contoh user)
- **Pertanyaan:** apakah broker besar di sisi beli lebih kuat daripada broker besar di sisi jual?
- **Ukuran (sama dengan FL24 Top Brokers %):** 100 × (Σ net 3 pembeli bersih terbesar − Σ |net| 3 penjual bersih terbesar) ÷ total beli saham itu, semua investor. Jendela bawaan **5D**, pilihan 1D/10D.
- **Kolom khusus:** imbalance (B − S) ÷ (B + S) dari −1 sampai 1 (FL48); kode 3 pembeli dan 3 penjual teratas dengan net masing-masing.
- **Level (sama dengan garis acuan FL24 di Terminal):** ≥ +10 **"Big Acc"**, ≥ +6 **"Acc"**, −6 sampai +6 **"Neutral"**, ≤ −6 **"Dist"**, ≤ −10 **"Big Dist"**.
- **Data 9 Nov:**

  | Jendela | Big Acc | Acc | Neutral | Dist | Big Dist |
  |---|---:|---:|---:|---:|---:|
  | 1D | 55 | 32 | 234 | 43 | 64 |
  | 5D | 36 | 37 | 300 | 21 | 34 |

  Pada 1D, 45% saham punya label selain Neutral, terlalu ramai untuk sebuah leaderboard. Karena itu bawaannya 5D (70% Neutral). Teratas 5D: EMMI +44,8, WINS +42,0, SMRA +38,6; terbawah ISSP −40,0, CARS −30,2.
- **Padanan:** Terminal FL24, FL48; Broker activity "Top brokers"; preset "Big Accumulation".
- **Status:** Hitung. `Feature_03` hanya menyimpan sisi beli (`top3_buyer_net_value`), jadi sisi jual dihitung dari `Feature_05`. Pada pengujian, satu kueri agregat untuk semua saham selesai sekitar 0,6 detik per jendela.

### F4 — Anomali asing (contoh user)
- **Pertanyaan:** arus asing saham mana yang paling tidak biasa menurut riwayat saham itu sendiri?
- **Ukuran:** `foreign_net_zscore_5d_base252d` (net asing 5 sesi dibanding 252 nilai sebelumnya milik saham itu); pilihan persentil (`foreign_net_percentile_5d_base252d`).
- **Penjaga wajib:** |rasio net asing 5 sesi| ≥ 5% (sama dengan S1). Tanpa itu, saham seperti NATO (net Rp0,3 miliar, 0,4% dari pembelian) bisa memuncaki daftar karena riwayatnya kecil.
- **Urutan:** menurun (anomali beli), menaik (anomali jual).
- **Level:** |z| ≥ 2 **"Tidak biasa"**, |z| ≥ 3 **"Ekstrem"**.
- **Data 9 Nov:** 198 saham lolos penjaga; 7 saham z ≥ 2, 2 saham z ≥ 3 (MPMX 4,44, PCAR 3,96); 6 saham z ≤ −2 (BAJA −5,96).
- **Padanan:** library S1 (versi screener dengan syarat tambahan) dan S8 (versi 1 hari); Terminal FL37 dengan stat z.
- **Status:** Siap.

### F5 — Pembelian bersih terkonsentrasi
- **Pertanyaan:** di saham mana pembelian bersih dikuasai segelintir broker?
- **Ukuran:** CR3 − 3/k (porsi 3 pembeli bersih teratas dikurangi porsi bila semua pembeli sama besar), diperingkat **di dalam 5 kelompok menurut jumlah pembeli k** (cara S3, keputusan user 2026-11-12). Penjaga k ≥ 10.
- **Kolom khusus:** k, CR3, broker teratas dan porsinya, intensitas (FL47: net pembeli ÷ total beli), net asing 5D.
- **Level (persentil dalam kelompok):** ≥ 80 **"Terkonsentrasi"**, ≥ 90 **"Sangat terkonsentrasi"**.
- **Data 9 Nov (1D, dari `Feature_03`):** 375 saham dengan k ≥ 10; batas kelompok k 13 / 15 / 18 / 23; 78 saham persentil ≥ 80. CR3 − 3/k tertinggi GOTO 0,82, PGEO 0,78.
- **Peringatan di kepala tabel:** "siapa yang membeli, bukan arah harga". Uji awal (30 saham) menemukan hubungan negatif dengan return ke depan, dan riset user tidak menemukan bahwa konsentrasi membedakan fase sebelum reli.
- **Padanan:** library S3; Terminal FL16 (minus even share), FL47.
- **Status:** 1D Siap (`Feature_03.top3_buyer_share`, `net_buy_broker_count`); 5D Hitung (`Feature_05`, seperti S3).

### F6 — Institusi vs Ritel (keputusan user 2026-11-13: "F6 boleh institusi vs ritel")
- **Pertanyaan:** di saham mana broker berklien institusi membeli bersih sementara broker berklien ritel menjual bersih, dan sebaliknya?
- **Ukuran (sama dengan Terminal FL34):** 100 × (net broker Institutional-heavy − net broker Retail-heavy) ÷ total beli semua broker, papan Regular, semua investor. Jendela bawaan **20D** (bawaan FL34 di Terminal), pilihan 5D.
- **Sumber:** `Feature_03_Stock_Broker_Daily` (`institutional_net_value`, `retail_net_value`, `total_buy_value`) per hari, dijumlah atas jendela.
- **Urutan:** menurun (institusi masuk, ritel keluar), menaik (ritel masuk, institusi keluar).
- **Kolom khusus:** net institusi (Rp), net ritel (Rp), broker institusi teratas dan porsinya.
- **Penjaga (dari S7 library):** net institusi > 0 untuk sisi atas (net ritel > 0 untuk sisi bawah), dan kaki institusi ≥ 5% dari total beli. Tanpa itu, saham dengan nilai sangat kecil di kedua kaki bisa muncul.
- **Level:** ≥ +10 **"Condong institusi"**, ≥ +20 **"Institusi kuat"**; ≤ −10 **"Condong ritel"**, ≤ −20 **"Ritel kuat"**.
- **Data 9 Nov:**

  | Jendela | P10 | P50 | P90 | ≥ +10 | ≥ +20 | ≤ −10 | ≤ −20 |
  |---|---:|---:|---:|---:|---:|---:|---:|
  | 5D | −23,8 | −0,5 | +21,6 | 103 | 50 | 111 | 56 |
  | 20D | −13,2 | +0,3 | +15,8 | 67 | 33 | 57 | 24 |

  Teratas 5D: WINE +109,6, UCID +100,8, SMRA +89,0; terbawah ALII −171,3, RELF −81,7.
  Nilainya bisa melewati ±100%: selisih dua kaki net bisa mencapai dua kali total beli (institusi +X, ritel −X). Karena itu bawaannya 20D, yang lebih tenang.
- **Peringatan di kepala tabel:**
  - label broker adalah kecenderungan kliennya, bukan jenis investor transaksi;
  - broker Mixed dan Niche (68 dari 112 broker) tidak masuk pembilang;
  - klasifikasi yang dipakai adalah klasifikasi terkini untuk semua tanggal;
  - satu broker bisa menguasai kaki institusi (contoh S7: CBDK, satu broker memegang 99,7% net institusi).
- **Padanan:** Terminal FL34; library S7.
- **Status:** Hitung (`Feature_03`, jumlah per jendela).
- **Yang digantikan:** runtun beli asing (FL26) tidak lagi menjadi tabel; tetap tersedia di Terminal dan preset "Foreign Accumulation Streak".

---

## 3. Sudut lain di luar teknikal dan flow

Diurutkan menurut kesiapan data. Angka contoh as-of 9 Nov, gerbang Luas.

| # | Sudut | Pertanyaan | Data | Contoh 9 Nov | Status |
|---|---|---|---|---|---|
| X1 | **Divergensi harga vs broker** (lintas sudut) | Harga turun tetapi broker besar menyerap (atau harga naik tetapi broker besar melepas)? | return 5D (`Feature_01`) + Top Brokers 5D (F3) | 26 saham "serapan" (return 5D ≤ −3% dan Top Brokers ≥ +6), contohnya WINE, MBSS, PBSA; 5 saham "distribusi saat naik" (SMAR, ICBP) | Hitung. Ini "Hari serapan" di usulan pra-reli |
| X2 | **Sektor dan rotasi** | Sektor mana yang naik dan ke mana asing bergerak? | `Feature_01.sector` + `Feature_06` | Net asing 5D: Industrials +Rp441,5 miliar, Financials +Rp415,6 miliar; Basic Materials −Rp576,6 miliar, Energy −Rp259,9 miliar | Hitung |
| X3 | **Lebar pasar (breadth)**: satu strip konteks di atas semua tabel, bukan tabel | Seberapa sehat pasar secara umum? | `Feature_04` | Hanya 82 dari 428 saham (19%) di atas EMA 200; 88 saham RSI ≤ 30 | Siap. Membantu membaca mengapa T5 timpang |
| X4 | **Kekuatan relatif vs IHSG** | Saham mana lebih kuat dari pasar? | harga saham + IHSG (Screener `rs`) | – | Hitung |
| X5 | **Kalender aksi korporasi** | Dividen, rights issue, tender offer, stock split apa yang mendekat? | `stockbit_corporate_action`, `idx_event_annotation` (cum_date, ex_date, ratio) | – | Siap (perlu dicek kelengkapannya) |
| X6 | **Transaksi orang dalam terbesar** | Siapa orang dalam yang membeli atau menjual besar 30 hari terakhir? | `stockbit_insider_transaction` (holder_role, value_idr, shares_change) | – | Sebagian: aturan dedup IDX–KSEI (ERRORS M241) belum diputuskan, sama dengan masalah S4 |
| X7 | **Leaderboard broker** (sudut pandang broker, bukan saham) | Broker mana yang paling banyak net beli di seluruh pasar, dan di saham apa? | `Feature_05` + `IDX_Broker_Profile` | – | Hitung |
| X8 | **Transaksi blok (Nego/Tunai)** | Saham mana yang porsi transaksi di luar pasar regulernya besar? | `Feature_05` papan Nego/Tunai (FL30) | – | Hitung. Berguna sebagai peringatan bagi F1–F6 |
| X9 | **Volatilitas** | Saham mana yang volatilitasnya melonjak atau menyempit? | `Feature_01.volatility_*_change_pct`, ATR | – | Siap |
| X10 | **Obligasi (fixed income)** | Yield mana yang bergerak paling besar? | `Price_Fixed_Income` | – | Aset lain; halaman tersendiri |

**Belum ada sumber datanya** (dicek di katalog Screener `screener-metrics.json`, keterangan "No source exists" atau "waits for approval"):
fundamental dan valuasi (P/E, P/B, ROE, dividen), kapitalisasi pasar, free float, kepemilikan asing (KSEI), notasi khusus / FCA, dan batas ARA/ARB.

**Koreksi 2026-11-14:** keanggotaan indeks (33 indeks, misalnya LQ45, IDX30, KOMPAS100) dan grup konglomerasi (33 grup) **sudah ada** di `Stock_List` sejak 2026-11-09 (EXEC-SCREENER-STOCK-LISTS), keanggotaan terkini. Leaderboard bisa memakainya sebagai saringan universe, seperti Screener.

---

## 4. Keputusan dan pertanyaan terbuka

**Sudah diputuskan:**
- 2026-11-13: F6 = Institusi vs Ritel ("F6 boleh institusi vs ritel").
- 2026-11-13: rotasi (bagian 3 X2) menjadi halaman sendiri, lihat `ROTATION_SPEC.md`.
- 2026-11-14: leaderboard dan Rotation Map masuk to-do list; spesifikasi ini menjadi acuan saat halamannya dibuat ("Ini semua dimasukkan ke to-do list ya").

**Masih terbuka:**
1. **Halaman:** leaderboard satu halaman dengan library screener, atau halaman umum sendiri (misalnya "Market Overview")?
2. **Tanggal:** semua tabel memakai satu tanggal (yang paling lama tersedia, sekarang 9 Nov), atau tiap tabel memakai tanggal terbarunya sendiri dengan label?
3. **Saringan dasar:** gerbang "Luas" seperti library?
4. **Slot alternatif T6:** tren/persilangan atau squeeze?
5. **Sudut lain:** mana dari X1, X3–X10 yang masuk halaman pertama?
