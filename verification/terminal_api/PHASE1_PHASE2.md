# Financial terminal — Phase 1 (HTML) dan Phase 2 (database, read-only)

Tanggal: 2026-10-24. Scope: EXEC-TERMINAL-API (lihat `EXEC.md`). Hanya inspeksi; tidak ada DDL, DML, migrasi atau
perubahan service.

Referensi UI: `03-terminal-right-panel.html` (lampiran user, 626.633 byte, 3.008 baris). Baris 888–905 adalah
library (`lightweight-charts-drawing 0.6.2`, bundel Lightweight Charts); logika aplikasi ada di baris 906–3006.

## 0. Status bukti

| Bagian | Status | Bukti |
|---|---|---|
| Phase 1 — HTML | **SELESAI** | Seluruh logika aplikasi dibaca; formula dikutip dengan nomor baris HTML. |
| Phase 2 — database live | **SELESAI (read-only)** | Setelah user membuka akses jaringan (2026-10-24), semua query lewat service `pgweb` (`pgweb-dev-a888.up.railway.app`, `/api/query`). Dicek dulu: `current_user = pgweb`, `default_transaction_read_only = on`, `statement_timeout = 30s`, 0 hak INSERT/UPDATE/DELETE/TRUNCATE. PostgreSQL 18.6. Tidak ada DDL, DML atau perubahan service. |
| Phase 2 — backend existing | **SELESAI** | Kode repo + deployment live (`railway deployment list`): `edge-bff` SUCCESS `d564aba8` (2026-10-24 16:09 UTC), `/ready` = ready; `market-sql-governor` deployment terbaru SKIPPED (watch path), tidak berubah. |

Percobaan pertama (sebelum akses dibuka) gagal karena proxy menolak host Railway: ERRORS R40.

## 1. Phase 1 — inspeksi HTML

### 1.1 Temuan utama

1. **Semua data harga di HTML sintetis.** `makeRng(7139)` membuat 1.280 hari kerja mulai 2021-01-04 (Senin–Jumat,
   tanpa libur bursa), harga awal 1.450, drift dan "shock" buatan (HTML 912–952). Volume juga buatan.
2. **Seri pembanding sintetis.** `catalog` (IHSG, BBCA, BBRI, BMRI, TLKM, ASII, UNVR, GOTO, ANTM, EXCL) dibuat dari
   return seri utama × `beta` + noise (HTML 954–976). IHSG di panel Statistics adalah seri buatan ini.
3. **Timeframe bukan data.** Tombol 5M/15M/1H/4H/D/W/M hanya mengubah jumlah bar yang terlihat dari data harian
   yang sama (`map = {'5M':170, …, M:1280}`, HTML 1210–1212). Tidak ada data intraday, mingguan atau bulanan.
4. **Broker activity (panel kanan): 1 hari nyata + 29 hari buatan.** `BK_BASE` (HTML 2704) = 88 baris BBCA tanggal
   2023-12-18: 60 broker, board Regular dan Nego (tanpa Tunai/Cash), Domestic dan Foreign; kolom
   `[broker, investor, board, buy value, sell value, buy lot, sell lot]`; total buy = total sell =
   Rp 1.067.042.438.606. Hari 1–29 dibuat dengan hash (`bkRows`, HTML 2776–2786).
5. **Flow Timeline (panel bawah): sintetis** dari `BROKSUM_PROFILE` (data hari yang sama, 5 kolom, HTML 1635), plus
   board Cash buatan untuk 6 broker terbesar (HTML 1646–1650). Ada hook `MarketLab.setBroksumRows(rows)` untuk data
   nyata dengan bentuk `{date, broker, investor, board, net}` (HTML 1890–1906).
6. **Label ticker tidak konsisten.** Panel kanan menulis `BBCA` (HTML 2981), Relative Performance menulis `MAPI`
   secara hardcode (HTML 1497–1501). Keduanya label prototipe, bukan data.

### 1.2 LEFT — Statistics

Semua metrik dihitung dari `closes`/`volume` seri utama dan **visible range** chart (`visRange()`, HTML 1408–1414:
indeks bar pertama dan terakhir yang terlihat, minimal 4 bar).

| Komponen | Formula di HTML (baris) | Input | Catatan |
|---|---|---|---|
| Return Distribution | `dayRet[i] = close[i]/close[i-1] − 1` (1314); histogram 10 bin, dipotong di persentil 2%–98% (1336–1363); Mean, Median, % sesi positif (`ret > 0`), jumlah observasi (1458–1466) | close harian | Return hari pertama visible memakai close sebelum range (masuk akal). |
| Seasonality — bulanan | return bulan = close terakhir bulan ÷ close terakhir bulan sebelumnya − 1; hanya bulan yang **berakhir** di dalam range; rata-rata per nama bulan (1420–1430) | close harian | Bulan berjalan yang belum selesai ikut dihitung sebagai bulan penuh — perlu keputusan. |
| Seasonality — hari | rata-rata `dayRet` per Senin–Jumat (1431–1435) | close + tanggal | Di data nyata, hari libur tidak ada barisnya; return sesudah libur memuat >1 hari kalender. |
| Drawdown | `peak` berjalan mulai bar pertama visible; `dd = close/peak − 1` (1473–1479) | close | Bergantung visible range; bukan `drawdown_20d/60d` Feature 01. |
| Realized Volatility | log return; std sampel 20 sesi (÷19); × √252 × 100 (1315–1320) | close | **Beda dengan Feature 01**: `volatility_20d_ann_pct` memakai return **sederhana** (`migration 20260912_001`, baris 176–234). |
| Relative Performance | close dan IHSG di-rebase ke bar pertama visible; selisih dalam pp (1491–1501) | close ticker + close IHSG | IHSG di HTML sintetis; di DB ada IHSG nyata (bagian 2). |
| Volume Distribution | `volume[i] / avg(volume[i−19..i])` (termasuk hari ini) (1321–1322); Current, Median, persentil (`≤ current`), observasi (1504–1511) | volume | Sama dengan `volume_ratio_20d` Feature 01 (window 20 termasuk hari ini). IHSG tidak punya volume (NULL). |

Kesimpulan Phase 1 kiri: semua metrik bisa dihitung dari **satu seri OHLCV harian per ticker + seri IHSG**; tidak ada
yang butuh tabel baru (keputusan desain tetap menunggu Phase 2 live).

### 1.3 RIGHT — Broker activity

Satu sumber bersama: baris harian `broker × investor type × board × tanggal` dengan buy/sell value dan buy/sell lot.
Semua panel memakai date picker yang sama (`makeRange`, HTML 2830–2869): preset N hari + custom from/to + (untuk
Broker summary) tombol prev/next.

| Komponen | Filter | Grain agregasi | Formula di HTML (baris) | Status logika |
|---|---|---|---|---|
| Broker summary | investor All/Foreign/Domestic; board All/Regular/Nego/Cash; Net/Gross; range 1/5/20D/custom (default 1D) | jumlah per broker atas range | Net = Σbuy − Σsell; Gross = Σbuy (pembeli) dan Σsell (penjual); top 5 (atau 10) pembeli dan penjual; kolom Lot, Value, **Avg = value / (lot × 100)** (2873–2897) | Agregasi: terverifikasi secara definisi. **Gauge "Broker action"** `g = clamp((Σtop5 net buy − Σtop5 net sell) / Σbuy × 4, −1, 1)`, ambang 0,2/0,6 (2876–2881): **UNVERIFIED** (heuristik prototipe). |
| Top accumulators | Buy/Sell; range 1/5/20D/custom (default **5D**) | jumlah per broker atas range, **selalu All investor + All board** (mengabaikan filter Broker summary) | ranking `net value` (buy: net > 0 menurun; sell: net < 0 naik); 8 baris; tooltip net lot (2900–2913) | Aturan ranking jelas; perlu konfirmasi bahwa All/All memang diinginkan. |
| Broker inventory | 1–5 broker; Lot/Value; range 10/20/30D/custom (default 20D; default broker = 3 akumulator terbesar) | per broker per hari, **All investor + All board** | `cum` mulai 0 pada hari pertama range, ditambah net lot atau net value harian; hari tanpa baris = 0 (2916–2955) | Ini **kumulatif net transaksi dalam range**, bukan kepemilikan saham. Tidak ada posisi awal di data. Label "inventory" menyesatkan bila diartikan holding. |
| Bandar detector | Top 3/5/10; range 1/5/20D/custom (default 1D) | per broker, All/All | `r = (Σ topN net buy − Σ topN net sell) / Σ buy`; verdict Neutral < 3%, Small < 6%, Normal < 12%, Big (2817–2821, 2962–2987); "Foreign share of buyers" memakai daftar broker hardcode `BK_FOREIGN` (2704–2705) | **UNVERIFIED** — formula dan ambang belum punya definisi bisnis yang disetujui. "Foreign" di sini = **domisili broker** (hardcode), beda dengan filter Investor Type di panel lain. Di DB padanannya `IDX_Broker_Profile.broker_type`. `BK_BUMN` juga hardcode. |

### 1.4 BOTTOM — Flow Timeline

| Aspek | Perilaku HTML (baris) |
|---|---|
| Sumber | `COMBOS`: satu entri per `broker × investor × board` dengan array net value harian sepanjang seluruh seri harga (1630–1669). |
| Filter | Broker multi-select (default semua), Board multi (default semua), Investor multi (**default Foreign**) (1673–1677, 1870–1884). |
| Net harian | Σ net value kombinasi yang lolos filter per tanggal (1727–1733). Unit: Rupiah. |
| Kumulatif | running sum **mulai dari sesi pertama seluruh seri**, bukan dari visible range (1734–1735). |
| Ringkasan | Latest day net; Period net total = kumulatif akhir; **Avg daily net = total / N semua sesi** (termasuk hari tanpa transaksi) (1722–1726). |
| Tanggal tanpa transaksi | 0. Baris broker di tanggal yang tidak ada di seri harga **dibuang diam-diam** (`setBroksumRows`, 1895). |
| Sinkronisasi | Time scale disinkronkan dengan chart harga lewat indeks bar (logical range) (1769–1770). Artinya tanggal broker harus memakai daftar sesi yang sama dengan harga. |
| Catatan "net to zero" | Bila semua broker, board dan investor dipilih, total harian = 0 "by definition" (1740–1742). Di data nyata ini tidak selalu benar: ERRORS M157 (2016–2020 ada ketidakseimbangan buy/sell di sumber). |
| Indikator terkait | "Net Buy Flow" (rolling N hari) dan "Net Buy Flow (Line)" per broker di main chart (2376–2430) memakai `COMBOS` yang sama. Di luar scope (indicator engine), tapi sumber datanya sama. |

### 1.5 MAIN CHART — Price

Kebutuhan: OHLCV harian per ticker (`time` = `YYYY-MM-DD`), volume histogram (warna dari close ≥ open), mode Price
atau Return (rebase ke bar pertama), seri pembanding (ticker lain, IHSG) dalam mode return. Timeframe: hanya
harian yang nyata di HTML. Kebijakan penyesuaian harga (split/dividen) tidak disebut di HTML.

### 1.6 Klasifikasi per elemen UI

| Elemen | Langsung dari DB | Turunan dari raw | UI-only | Sintetis di HTML | Formula UNVERIFIED | Belum tersedia |
|---|---|---|---|---|---|---|
| OHLCV harian | ✓ | | | ✓ | | |
| Timeframe 5M/15M/1H/4H | | | | | | ✓ (tidak ada data intraday) |
| Timeframe W/M | | ✓ (agregasi dari harian) | | | | |
| Return/Seasonality/Drawdown/Vol/Volume dist. | | ✓ | histogram, binning | ✓ | | |
| Relative vs IHSG | IHSG ✓ | ✓ | | ✓ | | |
| Broker summary (net/gross/lot/avg) | ✓ | ✓ (Σ per range) | sort, top N | ✓ (29 hari) | | |
| Gauge "Broker action" | | | | | ✓ | |
| Top accumulators | | ✓ | | ✓ | | |
| Broker inventory (kumulatif net) | | ✓ | | ✓ | | Holding nyata: ✓ tidak tersedia |
| Bandar detector | | ✓ (input) | | ✓ | ✓ | |
| Flow timeline | | ✓ | | ✓ | | |
| Kategori broker F/B/L (warna tag) | `broker_type` ✓ | | | hardcode | BUMN: ✓ tidak ada di DB (perlu cek) | |

## 2. Phase 2 — kondisi database (LIVE, 2026-10-24)

### 2.1 Inventaris

Schema: `public` (102 tabel, 2 tabel partisi, 3 view; semua bisa dibaca role `pgweb`), `ai_audit` (9), `edge_bff` (3),
`migration_archive` (1) — tiga yang terakhir tidak bisa dibaca role ini (tidak relevan untuk terminal). Tidak ada
materialized view.

Objek live yang **belum tercatat** di `DATABASE_SCHEMA.md` (dokumen tertinggal, ERRORS R33):
`Feature_01_Stock_Daily_INDEX`, `Feature_02_Broker_Rolling_INDEX`, `Feature_03_Stock_Broker_Daily_INDEX`,
`Feature_04_Technical_Indicator_INDEX`, `Feature_05_Foreign_Domestic_Broker_Detail_INDEX`,
`Feature_06_Foreign_Domestic_INDEX` (keluaran khusus index; komentar tabel: "Automatic daily updates are not enabled";
`Feature_05_…_INDEX` hanya berisi ticker `IHSG`), `Feature_Vocabulary` (kamus frontend Bahasa Indonesia),
`idx_stockbit_value_corrections` (10 koreksi 2016-11-02 – 2017-02-07, tanpa komentar), dan indeks
`Feature_06_Foreign_Domestic_date_board_idx (trade_date, market_board)`.

### 2.2 Objek yang relevan untuk terminal

| Objek | Grain / kunci | Ukuran | Cakupan live | Indeks | Relevansi |
|---|---|---|---|---|---|
| `Price_Stock_Indonesia_IDX` | PK `(ticker, date)` | ~1,33 jt baris, 533 MB | 1.329.064 baris, 845 ticker (844 `stock` + 1 `index`), **2018-01-02 – 2026-10-23**; semua `timeframe = 'Daily'`, semua `is_final = true`, 0 baris akhir pekan; `source = TradingView`, `market_code = IDX` | PK; `final_idx (ticker, date DESC) WHERE is_final AND timeframe='Daily'`; `date_idx` | Main chart + Statistics. Hanya harian. |
| IHSG (tabel yang sama) | ticker `IHSG` | 2.125 baris | 2018-01-02 – 2026-10-23, volume NULL semua | sama | Benchmark. Punya **2 tanggal tanpa saham**: 2026-09-17 dan 2026-09-18 (sudah diketahui, ERRORS IHSG 2026-10-23). |
| `Feature_01_Stock_Daily` | PK `(ticker, date)` | ~1,33 jt | — | PK, `date_idx` | Opsional (volume ratio sama dengan HTML; volatilitas beda basis). |
| `IDX_Broker_Summary` | PK `(Date, Symbol, Broker, Investor Type, Market Board)` | ~45,1 jt baris, 10 GB | **2.560 tanggal**, 2016-01-04 – 2026-08-31 | **hanya PK (diawali Date)** | Sumber mentah. |
| `Feature_05_Foreign_Domestic_Broker_Detail` | PK `(ticker, trade_date, broker, investor_type, market_board)` | ~45,2 jt, 9,6 GB | 2.560 tanggal, 2016-01-04 – 2026-08-31 (sama dengan mentah) | PK (diawali ticker), `trade_date_idx` | **Sumber utama panel kanan dan bawah.** |
| `Feature_05_…_Stock` (view) | sama | — | filter `IDX_Stock_Universe."Security Type" = 'stock'` | — | Versi saham saja. |
| `Feature_06_Foreign_Domestic` | PK `(ticker, market_board, trade_date)` | 2,27 jt, 1,3 GB | 2016 – 2026-08-31 | PK, `date_board_idx` | Jalur cepat Flow Timeline **tanpa filter broker**. |
| `IDX_Broker_Profile` | PK `broker_code` | 112 broker | 32 Foreign, 80 Domestic; 4 klasifikasi | PK | Nama broker, kategori Foreign/Domestic. Tidak ada kategori BUMN. |
| `IDX_Stock_Universe` | PK `Ticker` | 844 + IHSG | — | PK | Daftar ticker. |

### 2.3 Kualitas data dan grain (live)

| Cek | Hasil |
|---|---|
| Duplikat per grain | Tidak mungkin: semua grain di atas adalah PK. |
| Kalender harga vs broker | Untuk 2018-01-02 – 2026-08-31, tanggal broker = tanggal harga BBCA **persis** (0 selisih dua arah). Data broker berhenti 2026-08-31; harga sampai 2026-10-23 → 37 sesi terakhir chart tanpa data broker. |
| Feature 05 vs mentah | Jumlah baris dan Σ net value sama persis pada 2016-03-01 (9.057 baris), 2023-12-18 (21.583) dan 2026-08-31 (27.059). 2019-06-03 kosong di keduanya (libur). Rekonsiliasi penuh semua tanggal belum dijalankan (butuh scan 45 jt baris; batas 30 detik pgweb). |
| HTML `BK_BASE` vs DB (BBCA 2023-12-18) | 88 dari 88 baris ada di mentah dan Feature 05; **semua buy/sell value sama persis**. 6 baris beda lot karena HTML membulatkan odd lot (mis. DB 38.141,18 lot vs HTML 38.141). |
| Lot pecahan | BBCA: 13.310 dari 219.762 baris Feature 05 punya lot pecahan (odd lot). API harus mengirim lot sebagai desimal. |
| Ketidakseimbangan buy ≠ sell (M157) | `source_balance_gap` di Feature 06: Regular 2016 14.270, 2017 7.849, 2018 9.084, 2019 10.647, 2020 5.446 baris; Nego/Tunai puluhan–ratusan baris 2016–2020; 2021–2024 nol; 2025 dan 2026 masing-masing 2 baris Regular. Catatan "net to zero" di HTML salah untuk baris ini. |
| Board | `Regular`, `Nego`, `Tunai` ada di semua tahun 2016–2026 (Tunai: 228–1.867 baris ticker-hari per tahun). |
| Kode broker | 91 broker aktif sejak 2026-01-01, semuanya ada di `IDX_Broker_Profile`. |
| Daftar broker asing HTML | 23 kode `BK_FOREIGN` semuanya Foreign di DB, tapi DB punya 9 broker Foreign lain yang tidak ada di HTML: BW, CP, DU, FG, GI, LH, LS, MS, RB. |
| Frekuensi | BBCA: `buy_freq` tidak pernah NULL. HTML tidak menampilkan frekuensi. |

### 2.4 Performa — `EXPLAIN (ANALYZE, BUFFERS)` (pgweb, 2026-10-24)

Waktu eksekusi di server (cold = jalan pertama, warm = diulang). Query: `verification/terminal_api/explain.py`
(jalankan `RAILWAY_TOKEN=… python3 explain.py [prefix…]` dari folder itu).

| # | Query | Plan | Baris keluar | Cold | Warm |
|---|---|---|---|---|---|
| P1 | OHLCV BBCA 1 tahun | Index Scan `final_idx` | 238 | 3,5 ms | — |
| P2 | OHLCV BBCA semua (2018–) | Bitmap `final_idx` | 2.123 | 7,4 ms | — |
| P3 | Close BBCA + IHSG semua | Bitmap `final_idx` | 4.248 | 18 ms | — |
| R1 | Mentah: per broker BBCA 1 hari | Index Scan PK | 64 | 17 ms | — |
| R2 | Mentah: per broker BBCA 20 hari | Index Scan PK (filter Symbol di dalam rentang Date) | 85 | 223 ms (1.812 buffer) | — |
| R3 | Mentah: per broker BBCA 1 tahun | sama | 92 | **3.071 ms** (25.512 buffer) | 47 ms |
| F1 | Feature 05: per broker BBCA 1 hari | Index Scan PK | 64 | 13 ms | — |
| F2 | Feature 05: per broker BBCA 20 hari | Bitmap PK | 85 | 9 ms (52 buffer) | — |
| F3 | Feature 05: per broker BBCA 1 tahun | Bitmap PK | 92 | 359 ms (675 buffer) | 10 ms |
| F4 | Feature 05: flow harian BBCA semua tahun, Foreign | Bitmap PK, 58.040 baris dibaca | 2.560 | **3.783 ms** | 107 ms |
| F5 | Feature 05: flow harian BBCA 3 tahun, 3 broker | Bitmap PK | 710 | 12 ms | — |
| F6 | Feature 05: inventory 5 broker × 30 hari | Index Scan PK | 145 | 0,6 ms | — |
| F7 | Feature 05: flow harian GOTO semua, semua investor | Bitmap PK, 96.219 baris dibaca | 1.045 | 2.221 ms | 26 ms |
| S1 | Feature 06: flow harian BBCA semua, Foreign | Index Scan PK | 2.560 | 421 ms | 6 ms |

Kesimpulan terukur:
- Per ticker, Feature 05 jauh lebih murah daripada tabel mentah (1 tahun: 675 vs 25.512 buffer), karena PK-nya diawali
  ticker. Tabel mentah tidak dipakai untuk query per ticker.
- Satu-satunya query yang lambat saat cold adalah flow seluruh riwayat (F4, F7: 2–4 detik, dominan baca disk); warm
  di bawah 110 ms. Belum ada bukti yang membenarkan indeks baru atau tabel agregat; keputusan ini dibahas di
  Phase 4 dengan target latensi dari user.
- Harga (P1–P3) di bawah 20 ms.

## 3. Phase 2 — backend existing (dari kode repo)

| Service | Fungsi | Akses DB | Auth | Cocok untuk API terminal? |
|---|---|---|---|---|
| `edge-bff` (`apps/edge-bff`, FastAPI) | Frontend + BFF untuk EDGE (chat AI): auth, runs, SSE, conversations, exports (`app/main.py` 231–536) | `psycopg`, login khusus `edge_bff_login` hanya ke schema `edge_bff` (`app/config.py` 57); `statement_timeout 5s` (`app/store.py` 28) | satu owner, cookie session (`/api/v1/auth/*`) | Belum ada route data pasar. Bisa diperluas, tapi login DB-nya sengaja dibatasi ke `edge_bff`. |
| `market-sql-governor` (FastAPI) | Satu-satunya jalur SQL untuk AI: `/v1/query`, `/v1/extract` (Parquet), `/v1/summary`, `/v1/lookup`, katalog (`app/main.py` 98–293) | `market_sql_governor` → `market_ai_sql_reader` (SELECT objek yang disetujui) | API key | Dirancang untuk AI (spec, EXPLAIN gate, dataset Parquet), bukan untuk chart interaktif. |
| Lainnya (cron, worker, orc, sandbox) | — | — | — | Tidak relevan. |

Deployment live: `edge-bff` SUCCESS `d564aba8-7414-4da8-bd6a-12f1a05936bb` (2026-10-24 16:09 UTC), `/ready` menjawab
`ready`. Tidak ada endpoint existing untuk OHLCV, statistik atau broker activity yang bisa dipakai langsung oleh terminal.
Pilihan service untuk API baru adalah keputusan user di Phase 5/6 (belum diusulkan di sini).

## 4. Selisih HTML vs database yang harus diputuskan (tidak dipilih diam-diam)

| # | Selisih | HTML | DB / definisi existing |
|---|---|---|---|
| S1 | Basis volatilitas 20 sesi | log return | Feature 01: return sederhana |
| S2 | Drawdown | peak dalam visible range | Feature 01: 20/60 sesi tetap |
| S3 | Bulan berjalan di Seasonality | dihitung sebagai bulan penuh | — |
| S4 | "Foreign" di Bandar detector | domisili broker (daftar hardcode) | `IDX_Broker_Profile.broker_type`; filter lain memakai Investor Type |
| S5 | Gauge Broker action dan verdict Bandar | heuristik, ambang hardcode | tidak ada definisi bisnis — UNVERIFIED |
| S6 | "Inventory" | kumulatif net dari awal range | tidak ada posisi awal; bukan holding |
| S7 | Kumulatif Flow Timeline | sejak sesi pertama seri yang dimuat | Feature 06: sejak sesi pertama ticker per board |
| S8 | Board | `Cash` | `Tunai` |
| S9 | Net-to-zero | dianggap selalu nol | tidak benar pada sebagian data 2016–2020 (M157) |
| S10 | Timeframe | 5M–M | hanya harian tersimpan |
| S11 | Kelengkapan tanggal | broker dan harga dianggap tanggal sama | sama persis sampai 2026-08-31; broker berhenti di situ, harga sampai 2026-10-23; IHSG punya 2026-09-17/18 tanpa saham |
| S12 | Lot | dibulatkan | odd lot pecahan (desimal) |
| S13 | Daftar broker asing | 23 kode hardcode | 32 broker Foreign di `IDX_Broker_Profile` |

## 5. Pemeriksaan yang masih terbuka

1. Rekonsiliasi penuh Feature 05 vs `IDX_Broker_Summary` untuk **semua** tanggal (baris dan Σ value per tanggal).
   Butuh job read-only di luar batas 30 detik pgweb (mis. runner privat), atau dijalankan per tahun.
2. Kebijakan stock split: harga disimpan sebagaimana dari TradingView (`IDX:…`); apakah TradingView mengirim harga
   saham yang disesuaikan split belum dicek di kode `apps/idx-price-cron` dan data (cari lonjakan close/close ≈ 1/n
   pada tanggal corporate action).
3. Target latensi API dari user (menentukan perlu tidaknya agregat atau cache untuk riwayat panjang).

## 6. Query yang dipakai

Helper read-only: `verification/terminal_api/pgq.py` (POST ke `/api/query` pgweb; kredensial dibaca dari variabel Railway ke memori, tidak
dicetak). Query performa (teks persis):

- P1 `select date,open,high,low,close,volume from "Price_Stock_Indonesia_IDX" where ticker='BBCA' and timeframe='Daily' and is_final and date between '2025-10-23' and '2026-10-23' order by date`
- R3 `select "Broker",sum("Buy Value"),sum("Sell Value") from "IDX_Broker_Summary" where "Symbol"='BBCA' and "Date" between '2025-09-01' and '2026-08-31' group by 1`
- F3 sama dengan R3 di `Feature_05_Foreign_Domestic_Broker_Detail` (`ticker`, `trade_date`)
- F4 `select trade_date,sum(net_value) from "Feature_05_Foreign_Domestic_Broker_Detail" where ticker='BBCA' and investor_type='Foreign' group by 1 order by 1`
- F5 sama dengan F4 untuk `trade_date >= '2023-09-01' and broker = any('{YP,AK,ZP}')` (semua investor)
- F6 `select trade_date,broker,sum(net_lots),sum(net_value) … where ticker='BBCA' and trade_date between '2026-07-20' and '2026-08-31' and broker = any('{YP,AK,ZP,CC,BK}') group by 1,2`
- F7 flow harian GOTO semua tanggal, semua investor; S1 `select trade_date,sum(foreign_net_1d) from "Feature_06_Foreign_Domestic" where ticker='BBCA' group by 1 order by 1`
