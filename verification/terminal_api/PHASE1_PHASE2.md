# Financial terminal — Phase 1 (HTML) dan Phase 2 (database, read-only)

Tanggal: 2026-10-24. Scope: EXEC-TERMINAL-API (lihat `EXEC.md`). Hanya inspeksi; tidak ada DDL, DML, migrasi atau
perubahan service.

Referensi UI: `03-terminal-right-panel.html` (lampiran user, 626.633 byte, 3.008 baris). Baris 888–905 adalah
library (`lightweight-charts-drawing 0.6.2`, bundel Lightweight Charts); logika aplikasi ada di baris 906–3006.

## 0. Status bukti

| Bagian | Status | Alasan |
|---|---|---|
| Phase 1 — HTML | **SELESAI** | Seluruh logika aplikasi dibaca; formula di bawah dikutip dengan nomor baris HTML. |
| Phase 2 — database live | **BLOCKED / UNKNOWN — NOT VERIFIED** | Kebijakan jaringan sesi ini menolak `backboard.railway.com` (Railway API/CLI) dan `*.up.railway.app` (pgweb, EDGE): proxy menjawab 403 pada CONNECT (`/__agentproxy/status`, 2026-10-24 20:22 UTC). Token Railway yang dilampirkan tidak bisa dipakai. Tidak ada `DATABASE_URL` di sesi. ERRORS R40. |
| Phase 2 — dari repo | **SELESAI (dokumen + kode migrasi)** | Bagian 2 di bawah berasal dari `DATABASE_SCHEMA.md` (refresh live 2026-10-12, sebagian 2026-10-22/23), `DATABASE_CHANGELOG.md` dan file migrasi. Ini **bukan** bukti live; setiap angka harus dibaca ulang dari database. |
| Phase 2 — backend existing | **SELESAI (kode di repo)** | `apps/edge-bff`, `apps/market-sql-governor`. Deployment live belum dicek (butuh Railway API). |

Pemeriksaan yang masih diperlukan ada di bagian 5.

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

## 2. Phase 2 — kondisi database menurut dokumen repo (BELUM DIVERIFIKASI LIVE)

| Objek | Grain / kunci | Kolom relevan | Cakupan menurut dokumen | Indeks | Relevansi |
|---|---|---|---|---|---|
| `Price_Stock_Indonesia_IDX` | PK `(ticker, date)` | open, high, low, close, volume (NULL hanya untuk index), timeframe, is_final | Saham 2018-01-02 – 2026-10-09 (`DATABASE_SCHEMA.md`, refresh 2026-10-12); 1.326.939 baris non-IHSG (`DATABASE_CHANGELOG.md` 2026-10-23) | PK; `final_idx (ticker, date DESC) WHERE is_final AND timeframe='Daily'`; `date_idx` | Main chart, Statistics. Harga **tidak disesuaikan dividen** (ERRORS D10); penyesuaian split belum jelas — perlu cek. |
| IHSG di tabel yang sama | ticker `IHSG` (provider `IDX:COMPOSITE`) | OHLC, volume NULL | 2.125 baris, 2018-01-02 – 2026-10-23 (`DATABASE_CHANGELOG.md` 2026-10-23) | sama | Benchmark Relative Performance. |
| `Feature_01_Stock_Daily` | PK `(ticker, date)` | return_1d_pct, volatility_20d_ann_pct (return sederhana), volume_avg_20d, volume_ratio_20d, drawdown_20d/60d | sampai 2026-10-09 | PK, `date_idx` | Opsional: volume ratio sama dengan HTML; volatilitas beda basis (log vs sederhana); drawdown beda definisi. |
| `IDX_Broker_Summary` | PK `(Date, Symbol, Broker, Investor Type, Market Board)` | Buy/Sell/Net Value, Buy/Sell/Net Lots, Avg Buy/Sell, buy_freq/sell_freq | sampai 2026-08-31; data 2016–2017 kurang 9 tanggal (Feature 05/06 doc) | **hanya PK (diawali Date)** | Sumber mentah broker. Akses per ticker lintas banyak tanggal tidak punya indeks berawalan Symbol — perlu `EXPLAIN` live. |
| `Feature_05_Foreign_Domestic_Broker_Detail` | PK `(ticker, trade_date, broker, investor_type, market_board)` | buy/sell/net value, buy/sell/net lots, freq, `source_balance_gap` | 1 baris per baris `IDX_Broker_Summary`, sampai 2026-08-31; refresh **manual** | PK (diawali ticker), `trade_date_idx` | Kandidat terkuat untuk Broker summary, Accumulators, Inventory, Bandar, Flow Timeline (grain dan kunci cocok dengan HTML). |
| `Feature_05_…_Stock` (view) | sama | sama, hanya saham IDX | sejak EXEC-M204 (2026-10-23) | — | View existing yang sudah dibuka ke SQL Governor. |
| `Feature_06_Foreign_Domestic` | `(ticker, market_board, trade_date)` | foreign/domestic buy/sell/net 1d, cumulative, rolling | sampai 2026-08-31; manual | — (cek live) | Hanya berguna untuk Flow Timeline **tanpa filter broker**; kumulatifnya dihitung sejak sesi pertama ticker (beda dengan kumulatif dari range). |
| `IDX_Broker_Summary_Freq`, `IDX_Net_Foreign_Summary` (+ partisi 2016–2027) | lihat schema | freq; net foreign per ticker | belum ada deskripsi di katalog | lihat schema | Bukan kebutuhan HTML saat ini (HTML tidak menampilkan frekuensi). |
| `IDX_Broker_Profile` | PK `broker_code` | broker_name, broker_type (Domestic/Foreign), broker_classification | — | PK | Nama broker dan kategori F/L untuk tag; tidak ada kategori BUMN. |
| `IDX_Stock_Universe` | PK `Ticker` | Company Name, Security Type, Sector | termasuk IHSG sejak 2026-10-23 | PK | Daftar ticker / pencarian. |

Board di DB bernama `Tunai`; HTML memakai `Cash`. Investor Type di DB adalah identitas investor dari sumber, bukan
domisili broker.

Hubungan tanggal: harga sampai 2026-10-09 (IHSG 2026-10-23), broker sampai 2026-08-31. Chart yang menggabungkan
keduanya akan punya ekor tanpa data broker; API harus mengembalikan tanggal terakhir masing-masing sumber.

## 3. Phase 2 — backend existing (dari kode repo)

| Service | Fungsi | Akses DB | Auth | Cocok untuk API terminal? |
|---|---|---|---|---|
| `edge-bff` (`apps/edge-bff`, FastAPI) | Frontend + BFF untuk EDGE (chat AI): auth, runs, SSE, conversations, exports (`app/main.py` 231–536) | `psycopg`, login khusus `edge_bff_login` hanya ke schema `edge_bff` (`app/config.py` 57); `statement_timeout 5s` (`app/store.py` 28) | satu owner, cookie session (`/api/v1/auth/*`) | Belum ada route data pasar. Bisa diperluas, tapi login DB-nya sengaja dibatasi ke `edge_bff`. |
| `market-sql-governor` (FastAPI) | Satu-satunya jalur SQL untuk AI: `/v1/query`, `/v1/extract` (Parquet), `/v1/summary`, `/v1/lookup`, katalog (`app/main.py` 98–293) | `market_sql_governor` → `market_ai_sql_reader` (SELECT objek yang disetujui) | API key | Dirancang untuk AI (spec, EXPLAIN gate, dataset Parquet), bukan untuk chart interaktif. |
| Lainnya (cron, worker, orc, sandbox) | — | — | — | Tidak relevan. |

Tidak ada endpoint existing untuk OHLCV, statistik atau broker activity yang bisa dipakai langsung oleh terminal.
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
| S11 | Kelengkapan tanggal | broker dan harga dianggap tanggal sama | broker berhenti 2026-08-31, harga 2026-10-09 |

## 5. Pemeriksaan live yang masih diperlukan (Phase 2 lanjutan)

Setelah akses Railway tersedia, jalankan read-only (role pembaca, `default_transaction_read_only=on`,
`statement_timeout`):

1. Inventaris live: schema, tabel, view, materialized view, PK/unique/FK, indeks, tipe kolom, `pg_class.reltuples`,
   fungsi terkait (`information_schema`, `pg_catalog`).
2. Cakupan dan grain: min/max tanggal, jumlah sesi per ticker, duplikat per grain, NULL, nilai `timeframe`,
   `is_final`, board dan investor type per tahun — untuk `Price_Stock_Indonesia_IDX`, `IDX_Broker_Summary`,
   `Feature_05_…`, `Feature_06_…`.
3. Rekonsiliasi: `Feature_05` vs `IDX_Broker_Summary` (jumlah baris dan Σ value per tanggal/ticker); data hari
   BBCA 2023-12-18 di DB vs `BK_BASE` HTML (88 baris, Σ buy = Σ sell = Rp 1.067.042.438.606).
4. Tanggal broker yang tidak punya baris harga dan sebaliknya (efek ke sinkronisasi chart).
5. Kebijakan split: cek lonjakan harga yang cocok dengan corporate action, dan parameter adjustment di
   `apps/idx-price-cron`.
6. `EXPLAIN (ANALYZE, BUFFERS)` untuk pola query representatif: OHLCV 1 ticker × 1/3/8 tahun; broker per ticker ×
   1/5/20/250 hari di `IDX_Broker_Summary` vs `Feature_05`; flow harian dengan filter broker multi.
7. Deployment live `edge-bff` dan `market-sql-governor` (versi, variabel nama saja).

Cara akses yang sudah dipakai proyek: Railway CLI (`backboard.railway.com`) untuk menjalankan job read-only di
runner privat (`scripts/onboarding/migration_job.py`), atau pgweb read-only. Keduanya butuh host Railway diizinkan
di Network access environment sesi ini.
