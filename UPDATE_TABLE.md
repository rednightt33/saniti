# Update table

Panduan memperbarui tabel yang diisi dari Stockbit. Setiap kelompok tabel punya bagiannya sendiri:

| Bagian | Tabel | Cara |
|---|---|---|
| **A. Tabel broker** (nomor 1–7 di bawah) | `IDX_Broker_Summary` → Feature 05, 02, 03, 06, `_INDEX` | Loader lokal + job refresh di `orc-test-runner` |
| **B. Corporate action, insider dan anotasi** (B1–B7) | `stockbit_corporate_action`, `stockbit_insider_transaction`, `idx_event_annotation` | Satu job di `orc-test-runner` dengan token dari user |

# Bagian A — tabel broker

Panduan ini menjelaskan cara memperbarui semua tabel yang berasal dari data broker Stockbit, setelah
`IDX_Broker_Summary` diisi tanggal baru atau tanggal lama dikoreksi. Isinya diturunkan dari kode dan dari
pelaksanaan 2026-10-25 (EXEC-REFRESH-1025, EXEC-INCR-1025; hasilnya ada di `DATABASE_CHANGELOG.md`). Skrip yang
benar-benar dijalankan hari itu disimpan di `verification/broker_update_20261025/`.

Aturan AGENTS tetap berlaku: cek infra live sebelum mengubah apa pun, satu job saja di `orc-test-runner` pada satu
waktu (M210), klaim berhasil hanya setelah dibaca ulang, dan setiap putaran update dicatat di
`DATABASE_CHANGELOG.md` dan `RAILWAY_CHANGELOG.md`.

## 1. Tabel yang terlibat

**Sumber**

| Tabel | Isi | Diisi oleh |
|---|---|---|
| `IDX_Broker_Summary` | Satu baris per tanggal × saham × broker × tipe investor (Domestic/Foreign) × papan (Regular/Nego/Tunai): nilai, lot, harga rata-rata, `buy_freq`/`sell_freq` | Loader Stockbit lokal di PC user, memakai token JWT Stockbit (lihat bagian 2) |
| `stockbit_broker_summary_load_log` | Status per tanggal (`COMPLETED`, `NEEDS_REVIEW`, …) | Loader di Git; loader yang dipakai untuk 2026-09-01…10-23 **tidak** menulis log ini |

**Dihitung dari sumber.** Urutan baris di tabel ini adalah urutan refresh.

| # | Tabel | Rutin | Membaca |
|---|---|---|---|
| 1 | `Feature_05_Foreign_Domestic_Broker_Detail` | `refresh_feature_05(p_from, p_to, p_tickers)` | `IDX_Broker_Summary` |
| 2 | `Feature_02_Broker_Rolling` | `refresh_feature_02(ticker, p_from)` (migrasi `20261025_008`) | Feature 05 |
| 3 | `Feature_03_Stock_Broker_Daily` | `refresh_feature_03_stock_broker_daily(date, tickers)` | Feature 02 |
| 4 | `Feature_06_Foreign_Domestic` | `refresh_feature_06(ticker, p_from)` | Feature 05 |
| 5 | `Feature_01…06_*_INDEX` (IHSG) | `scripts/backfill_index_features.py` `prepare` + `apply_chunks` | `IDX_Broker_Summary` dan harga indeks |

Feature 01 dan 04 saham dihitung dari harga, bukan dari broker. Keduanya diurus `feature-01-worker` dan
`feature-04-worker` (Railway), jadi tidak termasuk panduan ini.

**Ikut berubah sendiri**

| Objek | Kenapa tidak perlu langkah sendiri |
|---|---|
| View `Feature_05_Foreign_Domestic_Broker_Detail_Stock` dan `Feature_06_Foreign_Domestic_Stock` | View biasa (bukan materialized), jadi langsung membaca tabelnya |
| `AI_data_coverage` (rentang tanggal yang dilihat AI) | Service `ai-data-coverage`, cron `30 0,10 * * *` UTC (`.railway/railway.ts`) |
| Kamus nilai Governor (kode saham dan broker untuk `search_values`) | Dibangun dari tabel dengan cache di `apps/market-sql-governor/app/value_dictionary.py` |

**Perlu dicek, jarang berubah**

| Tabel | Kapan |
|---|---|
| `IDX_Broker_Profile` / `IDX_Broker_Profile_History` | Bila ada kode broker baru di `IDX_Broker_Summary` yang belum ada di profil. Loader membaca daftar broker Stockbit tetapi tidak menulis profil. |
| `Database_Table_Status` | Status dokumentasi. Diperbarui dengan `scripts/sync_database_schema.py`, yang sekarang perlu go (26 baris basi untuk tabel yang sudah dihapus). |

## 2. Memuat `IDX_Broker_Summary` dari Stockbit

**Loader di Git:** `apps/stockbit-broker-backfill/stockbit_marketwide_broker_activity.py`. Cara kerjanya:
- berjalan di PC lokal, bukan di Railway;
- token JWT dibaca dari `STOCKBIT_TOKEN`, `--token-stdin` atau prompt, dan tidak pernah ditulis ke Git;
- per tanggal: menghapus tanggal itu, menulis ulang semua baris (`COPY`), lalu menandai `COMPLETED` di log, semuanya
  dalam satu transaksi;
- lima kali berturut-turut 401/403 menghentikan job dengan `STOPPED_INVALID_TOKEN`. Ambil token baru lalu jalankan
  ulang; tanggal yang sudah `COMPLETED` dilewati.

**Celah yang sudah diverifikasi (2026-10-25)**
- Loader di Git **tidak menulis `buy_freq`/`sell_freq`**: `CANONICAL_KEYS` tidak memuat kolom itu, dan tidak ada
  branch yang memuatnya.
- Tanggal 2026-09-01…10-23 punya frekuensi di 100 % baris tanpa baris log, jadi dimuat oleh loader lain yang belum
  ada di Git.
- Akibatnya, kalau loader Git dipakai untuk tanggal yang sudah ada, tanggal itu dihapus lalu ditulis ulang **tanpa
  frekuensi**. Kolom frekuensi di F05/F06 untuk tanggal itu jadi kosong. Staging `IDX_Broker_Summary_Freq` sudah
  dihapus (`20261025_007`), jadi tidak ada cadangan.
- Sampai loader yang menulis frekuensi masuk Git, **pakai loader yang sama dengan yang memuat 2026-09-01…10-23**.

## 3. Sebelum refresh: pastikan sumber selesai dan utuh

Semua cek ini read-only dan dijalankan sebagai job (`scripts/onboarding/run_job.sh`).

1. **Tidak ada penulis aktif.** `pg_stat_activity` tidak boleh punya sesi yang menulis `IDX_Broker_Summary`. Loader
   di Git menghapus lalu menulis satu tanggal dalam satu transaksi. Cara kerja loader frekuensi belum bisa dicek dari
   Git. Jadi jangan refresh sebelum user memastikan pemuatan selesai.
2. **Tanggal yang berubah diturunkan dari data, bukan ditebak.** Bandingkan per tanggal `IDX_Broker_Summary` dengan
   Feature 05: jumlah baris dan baris yang nilainya berbeda. Ini query `DIFF` di
   `verification/broker_update_20261025/r1_feature_05_06_job.py`. Tanggal pertama yang berbeda menjadi `p_from`.
   Koreksi tanggal lama juga tertangkap dengan cara ini.
3. **Keutuhan per tanggal baru:** jumlah baris, jumlah broker, dan bagian baris dengan `buy_freq` kosong. Bandingkan
   dengan tanggal-tanggal sebelumnya. Penurunan tajam berarti tanggal itu belum lengkap; tanyakan ke user sebelum
   lanjut.

## 4. Langkah refresh

Semua langkah dijalankan sebagai job di `orc-test-runner`:
- bungkus dengan `flock` pada satu file kunci;
- `run_job.sh` menunggu 90 × 20 detik (30 menit). Job yang lebih lama memerlukan salinan dengan tunggu lebih
  panjang supaya kunci tidak lepas saat job masih berjalan;
- akhir job wajib mencetak `VAR_REMOVED`.

Waktu di bawah diukur untuk 39 tanggal baru × 912 ticker.

**Langkah 1. Feature 05** (`refresh_feature_05(p_from, p_to)`, `p_to` eksklusif; 74 detik)
- Cek: jumlah baris = sumber, baris berbeda = 0. Gagal → rollback.
- Lalu `ANALYZE`.

**Langkah 2. Feature 02** per ticker yang punya baris F05 baru (`refresh_feature_02(ticker, p_from)`; ±3 detik per
ticker, 47 menit)
- Fungsi membaca 311 sesi sebelum `p_from`: jendela 60 sesi ditambah 252 sesi untuk z-score dan persentil. Fungsi
  hanya menghapus dan menulis baris ≥ `p_from`.
- Ticker baru yang riwayatnya kurang dari 311 sesi dihitung dari awal riwayatnya.
- Cek: jumlah baris F02 = jumlah baris F05 untuk rentang itu.

**Langkah 3. Feature 03** per tanggal baru (`refresh_feature_03_stock_broker_daily(date, NULL)`; kurang dari 2 menit
untuk 39 tanggal)
- Cek: jumlah baris F03 = jumlah grup `(date, ticker, market_board)` di F02.

**Langkah 4. Feature 06** per ticker (`refresh_feature_06(ticker, p_from)`; 312 sesi dasar; 8 menit)
- Cek: rekonsiliasi terhadap Σ F05 per `(trade_date, ticker, market_board)`, selisih = 0.

**Langkah 5. INDEX (IHSG).** Driver `verification/broker_update_20261025/i2_index_job.py` dengan `params.json`
`{ticker, sample_date, run_id}`. Bahan job: `scripts/`, `features/feature04/`, dan `requirements.txt` (psycopg,
numpy, TA-Lib, pandas, versi persis seperti di job 2026-10-25).
- `prepare` menghitung ulang seluruh riwayat di tabel sesi dan menjalankan validasi independen F02/F03/F06 serta
  sampel 2026-08-31.
- `apply_chunks` menulis per tahun hanya baris yang berubah (`IS DISTINCT FROM`), menjalankan ulang (harus 0), lalu
  membandingkan isi tabel dengan payload.
- `archive_and_migrate` **tidak** dijalankan, karena itu bootstrap sekali jalan.
- Cek: tahun lama menulis 0 baris (riwayat tidak berubah). Hanya tanggal baru atau yang dikoreksi yang ditulis.

**Langkah 6. `ANALYZE`** setiap tabel yang ditulis.

## 5. Bukti bahwa rumus baris baru sama dengan riwayat

Setiap putaran membuktikan dua hal pada sampel ticker. Pilih ticker besar, ticker tipis, warrant, dan ticker yang
punya papan Nego. Pembuktian dijalankan dalam transaksi yang di-rollback, jadi tidak ada yang tertulis.

**1. Inkremental = hitung penuh**
- F02: tulis ulang dari tanggal yang lebih awal (misalnya tiga bulan sebelum `p_from`), lalu bandingkan semua kolom
  kecuali `calculated_at` dengan `EXCEPT` dua arah. Hasilnya harus 0 selisih. Contoh:
  `i1_feature_02_03_job.py` (bagian akhir) dan `i1_feature_02_validate_job.py`.
- F06: `r1_feature_06_incremental_check.py`.

**2. Riwayat tidak berubah**
- Baris sebelum `p_from` tidak ikut ditulis. Untuk INDEX, jumlah tulis per tahun lama = 0.

## 6. Sesudah refresh

1. Baca ulang tanggal terbaru setiap tabel (F02, F03, F05, F06, dan keempat tabel INDEX broker) dan ukuran database.
2. Pastikan `AI_data_coverage` sudah memuat tanggal terbaru setelah cron berikutnya.
3. Cek kode broker baru terhadap `IDX_Broker_Profile` (bagian 1).
4. Catat di `DATABASE_CHANGELOG.md`:
   - rentang tanggal sumber;
   - jumlah baris per tabel dan hasil setiap cek;
   - ID job.
5. Catat di `RAILWAY_CHANGELOG.md`: job yang dijalankan, dan `DATABASE_URL` di `orc-test-runner` sudah dihapus.

## 7. Yang belum ada (usulan, perlu go user)

- **Loader frekuensi di Git.** Loader yang menulis `buy_freq`/`sell_freq` dan baris log masuk ke
  `apps/stockbit-broker-backfill/`. Tanpa ini, panduan bagian 2 bergantung pada program di luar repo.
- **Satu job update di repo.** Langkah 3–6 digabung menjadi satu skrip berparameter (`p_from` diturunkan dari
  data), bukan salinan per putaran.
- **Pembaruan harian otomatis**, setelah loader dan job di atas ada.

# Bagian B — corporate action, insider dan anotasi

Keputusan user 2026-10-25 (`EXEC.md` EXEC-EVENT-ANNOTATION): data ditarik **penuh** setiap kali user minta update (tidak
harian), job jalan di Railway (`orc-test-runner`, tanpa service baru), dan user memberi token Stockbit untuk tiap putaran.
Kode: `apps/stockbit-event-annotation/` (README di folder itu).

## B1. Tabel

| Tabel | Isi | Satu baris = |
|---|---|---|
| `stockbit_corporate_action` | Dividen, stock split, reverse split, saham bonus, rights issue, waran (waran terstruktur di ticker induknya), tender offer, RUPS, public expose. Tanggal-tanggal penting + baris asli Stockbit (`source_payload`) | Satu kejadian Stockbit (`<jenis>:<id Stockbit>`) |
| `stockbit_insider_transaction` | Transaksi insider IDX dan perubahan pemegang ≥5 % KSEI: pemegang, peran, broker, saham sebelum/sesudah/perubahan, Current %, Change %, harga, nilai, `data_origin` | Satu transaksi berbeda (kunci hash; salinan persis digabung, `source_copies`) |
| `idx_event_annotation` | Satu sumber anotasi grafik EDGE: corporate action (jenis + tanggal) dan insider (detail lengkap) | Satu kejadian; dibangun ulang oleh `refresh_idx_event_annotation()` |

Kalender ekonomi dan IPO tidak ditarik (keputusan user). Dua tabel sumber tidak pernah menghapus baris: baris yang tidak
lagi dikirim Stockbit diberi `source_removed_at` dan keluar dari `idx_event_annotation`.

## B2. Sebelum menjalankan

1. **Token.** Minta user memberi token Stockbit (JWT) yang masih berlaku. Token habis sekitar 1 hari setelah dibuat (lihat
   `exp` di bagian tengah JWT). Simpan hanya di file sementara di scratchpad, jangan di repo atau log.
2. **`orc-test-runner` sepi** (aturan M210: satu deploy baru menggantikan yang sedang jalan). Cek deploy terakhir dan
   variabelnya; jangan mulai bila ada deploy dalam beberapa menit terakhir atau `DATABASE_URL` masih terpasang dari job
   orang lain:
   ```bash
   railway deployment list -s 09358b92-09d4-4da2-b547-bf8f621e226c -e 4d3e5af2-302b-4a2e-84e2-7d7476d6ff49 -p 8aef1702-030b-49cb-9df7-5ac2e0a42691 --json
   railway variable list -s 09358b92-09d4-4da2-b547-bf8f621e226c -e 4d3e5af2-302b-4a2e-84e2-7d7476d6ff49 -p 8aef1702-030b-49cb-9df7-5ac2e0a42691 --json  # hanya nama
   ```
3. **Railway CLI 5.x** di `PATH` (perintah `railway variable ...`; CLI 4.x memakai `variables` dan gagal).

## B3. Menjalankan

Dari root repo:

```bash
echo '{"mode": "DRYRUN"}' > /tmp/params.json       # opsional: tarik + rekonsiliasi, lalu rollback
echo '{"mode": "APPLY"}'  > /tmp/params.json       # menulis
apps/stockbit-event-annotation/run_on_railway.sh load /tmp/params.json /tmp/load.log < token.txt
```

Skrip memasang `STOCKBIT_TOKEN` (lewat stdin, tidak pernah di command line) dan `DATABASE_URL`, mengunggah job,
menunggu `JOB_DONE`, lalu menghapus keduanya dan mencetak `TOKEN_REMOVED` dan `VAR_REMOVED`. Lama jalan sekitar
15 menit: corporate action ±360 request, daftar insider seluruh pasar ±2.100 halaman (untuk daftar ticker), lalu insider
per ticker ±1.000 ticker. Batas tunggu `run_job.sh` 30 menit.

## B4. Jaminan per putaran

Semua dicek di dalam satu transaksi; bila satu gagal, tidak ada yang ditulis (`ERR ...`, exit bukan 0).

| Jaminan | Cara |
|---|---|
| Tidak ada gap | Tarik penuh setiap kali: semua jenis × tahun 1995 s.d. tahun depan, dan insider setiap ticker (daftar ticker = `IDX_Stock_Universe` ∪ ticker tersimpan ∪ seluruh daftar insider pasar ∪ ticker corporate action). Laporan terlambat bertanggal lama tetap masuk. |
| Tidak dobel | Kunci tetap: `<jenis>:<id>` untuk corporate action; insider = hash (ticker, id pemegang, tanggal, aksi, saham sebelum/sesudah/perubahan, harga, asal) + nomor varian. Salinan persis dari Stockbit menjadi satu baris (`source_copies`). |
| Tidak hilang diam-diam | Baris yang tidak dikirim lagi diberi `source_removed_at` (tidak dihapus). Bila hasil tarik < 99,5 % baris aktif sebuah tabel (`min_ratio`), job berhenti `pull_too_small`. |
| Nilai wajib terisi | Constraint tabel (ticker, tanggal anotasi, jenis, kolom insider wajib); baris corporate action tanpa id atau tanggal anotasi menghentikan job; jumlah baris anotasi = baris aktif kedua sumber. |
| Request gagal | Satu request yang tetap gagal setelah 4 percobaan menghentikan job. Tahun corporate action yang menjawab HTTP 5xx diterima sebagai kosong hanya bila tabel memang tidak punya baris untuk jenis dan tahun itu (Stockbit menjawab 500 untuk tahun tanpa data, mis. dividen sebelum 2009). |
| Token kedaluwarsa | HTTP 401/403 menghentikan job dengan `STOPPED_INVALID_TOKEN`; minta token baru dan jalankan ulang. |
| Dua job bersamaan | Advisory lock `stockbit_event_annotation`; job kedua berhenti `lock`. |

## B5. Membaca hasil

`OUT` di log: `pull_corporate_action`, `insider_ticker_list`, `pull_insider`, `reconcile_corporate_action` dan
`reconcile_insider` (`pulled`, `new`, `changed`, `reappeared`, `unchanged`, `removed`), `refresh_annotation`, ringkasan
per jenis/asal/flag, lalu `committed`. Putaran ulang tanpa perubahan di sumber menghasilkan `new` = `changed` =
`removed` = 0.

## B6. Excel gabungan

```bash
apps/stockbit-event-annotation/run_on_railway.sh export /tmp/export.log      # read-only, tanpa token
python apps/stockbit-event-annotation/build_excel.py --log /tmp/export.log --output idx_event_annotation.xlsx
```

`build_excel.py` menolak log yang tidak lengkap (chunk hilang atau sha256 berbeda), jadi Excel sama persis dengan isi
tabel. Sheet: tabel, definisi kolom (dari `Column_Catalog`), ringkasan per jenis dan flag.

## B7. Sesudah menjalankan

1. Catat di `DATABASE_CHANGELOG.md`: run id, mode, angka `reconcile_*`, rentang tanggal, ID deploy.
2. Catat di `RAILWAY_CHANGELOG.md`: deploy di `orc-test-runner`, `TOKEN_REMOVED` dan `VAR_REMOVED`.
3. Data baru atau aneh dari Stockbit (jenis aksi baru, tipe corporate action baru tanpa tanggal anotasi) → catat di
   `ERRORS_AND_SOLUTIONS.md` dan perbarui `CORP_TYPES` di `stockbit_events.py` beserta tesnya.
