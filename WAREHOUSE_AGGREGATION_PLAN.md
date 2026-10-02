# Rencana: ringkasan di gudang data (Langkah 10 / G18 / M67)

Status (2026-10-02): **fase 1 (antar-entitas) dikerjakan dan di-deploy di dev**, belum di `main`; verifikasi live
(golden test ulang) belum. **Fase 2 (antar-waktu) belum dikerjakan.** Keputusan user 2026-10-02: antar-entitas dulu;
job dev sementara dan migrasi Tool_Catalog disetujui.

### Ringkasan fase 1 (lihat `ERRORS_AND_SOLUTIONS.md` G18, `DATABASE_CHANGELOG.md` 2026-10-02)

- Field `aggregate` per request DataNeed, mode ANALYSIS saja. Kolom tanggal wajib tetap di `group_by`, jadi
  pemeriksa cakupan bekerja seperti biasa.
- Aturan diturunkan dari katalog oleh sandbox **dan** diperiksa ulang oleh Governor dari kontrak katalognya sendiri:
  - SUM hanya bila `cross_entity_aggregation` = SUM;
  - MIN/MAX untuk kolom MEASURE numerik;
  - COUNT untuk jumlah baris;
  - COUNT_DISTINCT untuk kolom IDENTIFIER/DIMENSION/TIME;
  - kunci join tetap di-group.
- Hasil ringkasan tidak pernah dipecah per entitas yang dibuang (total per bagian akan terpotong). Pemecahan hanya per
  tanggal.
- Pengukuran di dev (job hanya-baca `wa-explain-job`, sudah dihapus):

  | Bentuk | Mentah | Ringkasan |
  |---|---|---|
  | Bank 2 bulan | 63.292 baris (628 ms) | 3.483 grup (73 ms) |
  | Semua saham 1 bulan | 500.001+ baris (35 detik) | 2.141 grup (1,8 detik) |
  | Bank 2022–2026 | 1,84 juta baris | 95.397 grup |

  Bentuk SQL berurutan biasa membuat planner mengurutkan semua baris sumber (lebih dari 60 detik). Karena itu
  Governor menghitung ringkasan dalam CTE MATERIALIZED, lalu mengurutkan grupnya (3,0 detik).
- Migrasi `20261002_002` (Tool_Catalog `submit_data_need_spec` v5, `check_data_feasibility` v4, dibuat dari kode,
  dijaga test drift) sudah diterapkan di dev.
- Fase 2 (belum): ringkasan antar-waktu (total per periode) dengan statistik cakupan dari Governor; AVG tetap
  SUM ÷ COUNT di sesi.

Status awal: usulan (2026-10-02).

## 1. Masalah (terverifikasi)

- Soal 5 golden test (`ma-golden-20261002b`, M67) menarik **4.388.779 baris** broker dalam 30 potongan (±192 detik).
  Jawabannya hanya butuh sekitar satu baris per broker. Hal yang sama terjadi di m01 (3,09 juta baris, G18).
- Jalur DataNeed hanya bisa meminta baris mentah:
  - kontrak `REQUEST_FIELDS` (sandbox `app/data_need.py`) tidak punya field ringkasan;
  - Governor `/v1/extract` hanya menyusun `SELECT … WHERE … ORDER BY … LIMIT`.
- Gudang dulu bisa meringkas: `request_data` punya `group_by` dan SUM/AVG/MEDIAN/MIN/MAX/COUNT/COUNT_DISTINCT
  (`apps/market-sql-governor/README.md`, gate 5–6). Jalur itu dimatikan pada 2026-09-25 (rilis dua jalur).

## 2. Kenapa dulu bermasalah (terverifikasi di migrasi)

Izin ringkasan dulu memakai `AI_column_catalog.allowed_aggregations`. Kolom ini **tidak tahu arah penjumlahan**:
SUM diizinkan tanpa membedakan menjumlah antar-broker/antar-saham pada tanggal yang sama atau antar-tanggal.

- **Tabel non-Feature** (`20260922_001`): setiap kolom angka yang bukan kunci otomatis mendapat
  `SUM, AVG, MIN, MAX`. Jadi menjumlah harga `close` atau `"Avg Buy"` diizinkan, padahal hasilnya tidak bermakna.
- **Feature 03** (`20260913_021`): semua kolom di luar daftar pengecualian mendapat SUM/AVG/MEDIAN. Termasuk
  `positive_net_value_total` dan `top3_buyer_net_value`, yang menurut migrasi `20260927_005` **tidak aditif**
  ("jumlah bagian positif bukan bagian positif dari jumlah"), serta hitungan broker per papan (broker yang sama
  terhitung lagi di papan lain).
- **Total bergulir** (`net_value_5d/20d/60d`) boleh di-SUM. Menjumlahkannya antar-tanggal menghitung hari yang sama
  berkali-kali.

Itulah kelas kesalahan "mengelompokkan kolom yang tidak bisa dikelompokkan / menjumlah yang tidak bisa dijumlah".

## 3. Yang sudah benar di struktur kita

Sejak 2026-09-27/28 katalog punya dua aturan yang **tahu arah**:

| Kolom katalog | Arti | Contoh |
|---|---|---|
| `cross_entity_aggregation` | Boleh dijumlah **antar-entitas pada tanggal yang sama** (broker → saham, papan → saham) | `net_value_1d` SUM, `net_value_5d` SUM; rasio, HHI, hitungan broker: NULL |
| `resample_aggregation` | Boleh diringkas **antar-waktu** | `net_value_1d` SUM; `close` LAST; `high` MAX; `net_value_5d`: NULL (tidak boleh) |
| `group_by_allowed` / `semantic_type` | Kolom yang boleh menjadi kunci pengelompokan | `ticker`, `broker`, `market_board`, `date`, `Industry` |

Ini persis konsep **aditif / semi-aditif / non-aditif** di benchmark (bagian 5): `net_value_1d` aditif ke semua
arah; `net_value_5d` semi-aditif (antar-entitas ya, antar-waktu tidak); rasio dan HHI non-aditif.

## 4. Usulan solusi

**Prinsip:** izin ringkasan diturunkan dari **arah yang diringkas**, bukan dari daftar fungsi per kolom.

1. **Kontrak DataNeed** (sandbox): field opsional `aggregate` per request.
   - Bentuk: `{"group_by": [kolom], "measures": [{"column", "function", "as"}]}`.
   - Fungsi: `SUM, MIN, MAX, COUNT, COUNT_DISTINCT`. `AVG` hanya sebagai `SUM ÷ COUNT` dari kolom ber-aturan SUM.
     Tidak ada AVG atau MEDIAN bebas (keputusan user 2026-10-01).
2. **Penentuan arah dari kunci pengelompokan** (backend, bukan AI):
   - kunci yang **dibuang** dibandingkan dengan grain tabel (`AI_table_catalog`: kolom waktu dan entitas;
     kolom kunci lain di primary key) menentukan arahnya:
     - waktu dibuang (kolom waktu tidak ada di `group_by`) → arah **waktu**;
     - entitas atau kunci lain dibuang (misalnya ticker, investor_type, market_board) → arah **antar-entitas**;
   - setiap measure harus punya aturan untuk **setiap** arah yang terjadi:
     SUM butuh `resample_aggregation = SUM` untuk arah waktu dan `cross_entity_aggregation = SUM` untuk arah
     entitas; MIN/MAX butuh MIN/MAX atau SUM di arah itu;
   - `COUNT(*)` selalu boleh, dan hasilnya diberi label "jumlah baris pada grain tabel" (bukan "jumlah hari");
     `COUNT_DISTINCT` hanya untuk kolom TIME/IDENTIFIER/DIMENSION;
   - aturan kosong di salah satu arah → ditolak `AGGREGATION_NOT_ADDITIVE`, dengan arah dan kolomnya disebut, dan
     usulan: tarik baris mentah atau ganti kolom (misalnya `net_value_1d` sebagai ganti `net_value_5d`);
   - `group_by` hanya untuk kolom `group_by_allowed`.
3. **Governor**: `/v1/extract` menyusun `SELECT keys, agg(...) … GROUP BY keys`.
   - Gate yang sama dipakai: EXPLAIN, batas biaya, dan `count_cap` G15.
   - Estimasi baris hasil = jumlah grup, bukan baris sumber.
   - `executed_scope` mencatat pengelompokan dan fungsi, supaya validasi sandbox tetap bisa membandingkan.
4. **Cakupan data**: pemeriksa cakupan sekarang menghitung tanggal dan entitas dari baris mentah. Untuk hasil
   ringkasan, Governor mengembalikan statistik cakupan dari query sumber yang sama (tanggal pertama/terakhir, jumlah
   tanggal dan entitas yang terbaca), sehingga label DATA_COVERAGE_VERIFIED tetap jujur.
5. **Hapus kontradiksi katalog** (migrasi baru):
   - `allowed_aggregations` tidak lagi dipakai untuk SUM di jalur baru;
   - audit sekali jalan menghasilkan daftar lengkap kolom yang SUM-nya diizinkan `allowed_aggregations` tetapi
     ditolak dua aturan arah; hasilnya dicatat di `DATABASE_CHANGELOG.md`;
   - Part A (`ERRORS_AND_SOLUTIONS.md`) mewajibkan tabel baru (FX, indeks, makro) mengisi kedua aturan arah, atau
     sengaja mengosongkannya.
6. **Panduan AI** (menu dan manual 4b): kartu "ringkas di gudang dulu" dengan contoh soal 5. Ini hanya panduan;
   penjaganya adalah langkah 2–3.

## 5. Benchmark

| Produk | Cara menyatakan aturan ringkasan | Padanan di katalog kita |
|---|---|---|
| Kimball, dimensional modeling | Fakta **aditif**, **semi-aditif** (mis. saldo: antar-akun ya, antar-waktu tidak), **non-aditif** (rasio) | `net_value_1d` aditif; `net_value_5d` semi-aditif; rasio/HHI non-aditif |
| dbt Semantic Layer (MetricFlow) | Measure punya `agg` dan `non_additive_dimension` (dimensi waktu yang tidak boleh dijumlah; diambil nilai awal/akhir) | `cross_entity_aggregation` + `resample_aggregation` (LAST/FIRST) |
| Microsoft Analysis Services / Power BI | `AggregateFunction` per measure: Sum, LastNonEmpty, FirstChild (semi-aditif terhadap waktu) | `resample_aggregation` LAST/FIRST/SUM |
| Cube, Looker (LookML) | Rasio didefinisikan sebagai measure turunan "SUM ÷ SUM", tidak pernah AVG dari rasio | AVG hanya SUM ÷ COUNT; rasio tidak diringkas |
| Snowflake Cortex Analyst, Databricks Genie | Model semantik: dimensi, measure dengan agregasi default, "verified queries"; SQL dibuat dari model, bukan bebas | `AI_column_catalog` sebagai model semantik; Governor menyusun SQL dari kontrak |

Kesamaan semua benchmark: **aturan ringkasan melekat pada definisi measure dan arah dimensinya**, bukan pada
daftar fungsi yang berlaku ke segala arah. Itu yang membedakan dua kolom aturan kita (benar) dari
`allowed_aggregations` (sumber kesalahan lama).

## 6. Contoh dengan soal 5

"Broker mana yang paling sering net beli saham bank di hari crash":

1. Hari crash: `Feature_01_Stock_Daily`, MEDIAN atau rata-rata return per tanggal. Ini butuh aturan antar-entitas
   untuk return. Return tidak aditif, jadi diringkas di sesi (±2.000 baris per hari, kecil) atau lewat helper.
2. Aliran broker: `Feature_02_Broker_Rolling` dengan `group_by = [date, broker]`, `SUM(net_value_1d)`.
   Ticker, investor_type dan market_board dibuang, jadi arahnya antar-entitas, dan `net_value_1d` punya SUM →
   diizinkan. Filter: saham bank, tanggal crash. Hasil ±57–132 tanggal × ±100 broker = **±6–13 ribu baris**, bukan
   4,39 juta.
3. Konsistensi per broker dihitung di sesi dari tabel kecil itu.

Kalau AI meminta `SUM(net_value_5d)` dengan tanggal dibuang → ditolak dengan alasan "net_value_5d tidak aditif
antar-waktu; pakai net_value_1d".

## 7. Risiko dan mitigasi

| Risiko | Mitigasi |
|---|---|
| Aturan katalog salah → ringkasan salah tapi lolos | Aturan hanya dari dua kolom arah yang sudah diaudit (26 + 27 baris); kolom tanpa aturan ditolak (fail closed); golden test membandingkan dengan kunci independen |
| Query GROUP BY berat di database | EXPLAIN dan batas biaya yang sama; ukur dulu dengan `EXPLAIN (ANALYZE, BUFFERS)` bentuk soal 5 (AGENTS.md); tidak menambah index tanpa bukti |
| Pemeriksa cakupan kehilangan dasar | Statistik cakupan dari query sumber (langkah 4) |
| AI tidak memakai fitur ini | Panduan dan kartu metode; diukur dari jumlah baris yang ditarik per soal |
| Grain tabel tidak jelas untuk tabel baru | Part A mewajibkan grain dan dua aturan arah sebelum tabel dimuat |

## 8. Cakupan

- **Tercakup:** semua tabel yang punya grain dan aturan arah, termasuk FX, indeks dan makro nanti, bila Part A
  dipenuhi.
- **Tidak tercakup:** statistik yang tidak bisa diringkas tanpa baris (median per grup, persentil, korelasi). Ini
  tetap di sesi (DuckDB). Ringkasan lintas tabel (join) tetap mengikuti aturan `requires_preaggregation`.

## 9. Verifikasi

- Test sandbox dan Governor:
  - `SUM(net_value_1d)` per broker diizinkan;
  - `SUM(net_value_5d)` antar-tanggal ditolak;
  - `SUM(close)` ditolak;
  - `SUM(positive_net_value_total)` antar-papan ditolak;
  - `COUNT_DISTINCT(date)` diizinkan;
  - AVG = SUM ÷ COUNT;
  - kasus lain selain soal 5: total net asing per saham per bulan (soal 1), volume per sektor;
  - kasus yang tidak cocok: median return per saham (tetap di sesi).
- Ukur di golden test ulang: baris yang ditarik dan detik `prepare_data_bundle` soal 5 (sekarang 4,39 juta / 192 detik).

## 10. Langkah kerja (setelah disetujui)

1. Audit katalog (query hanya-baca) dan `EXPLAIN (ANALYZE, BUFFERS)` bentuk soal 5 di dev.
2. Kontrak DataNeed `aggregate` + aturan arah (sandbox) + test.
3. Governor compile GROUP BY + statistik cakupan + test.
4. Migrasi katalog (Tool_Catalog, catatan `allowed_aggregations`), Part A.
5. Panduan AI, lalu golden test ulang.
