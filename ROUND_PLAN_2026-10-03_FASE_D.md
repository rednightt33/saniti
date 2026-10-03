# Rencana Fase D (alat untuk AI dan user) + rencana golden test sesudahnya (round 2026-10-03)

## Konteks

Fase A, B dan C sudah live di dev (orc `b458843d`, sandbox `8270c163`), tetapi **belum diuji dengan lalu lintas model**. Fase D menambah alat agar AI tidak "kejedot" dan user bisa memeriksa angka:
- statistik kolom sebelum menghitung;
- membuka hasil, kode dan file lama;
- menelusuri asal angka;
- mengunduh hasil;
- jalan pintas untuk pertanyaan sederhana;
- bukti per klaim (Prioritas 2, WAJIB).

Golden test (GT) dijalankan **sekali setelah Fase D selesai, dan hanya atas perintah user**. Rencananya ada di Bagian 2.

### Keputusan user (2026-10-03, jawaban terbaru)

| No | Keputusan |
|---|---|
| D-a | Net beli asing (query_metric) dari `Feature_03_Stock_Broker_Daily.foreign_net_value` |
| D-b | Nilai transaksi **ditunda** sampai ada kolom nilai transaksi resmi |
| D-c | Net beli per broker dari `IDX_Broker_Summary."Net Value"` per `"Broker"` |
| D-d | Golden test **sekali, setelah Fase D** |
| lama | Metrik awal (keputusan 1), ekspor di tabel Postgres terpisah (2), batas 20 MB (3) |

### Fakta survei yang mengubah rencana awal (§Fase D `ROUND_PLAN_2026-10-03.md`)

1. **Orc tidak punya pyarrow/pandas.** Semua pembacaan Parquet (halaman tabel lama, ekspor, hitung ulang bukti) dikerjakan sandbox lewat endpoint **tanpa sesi** yang menerima file. Satu pembaca, satu batas ukuran, satu cek checksum.
2. **Governor G18 fase 1 tidak bisa menjumlah antarwaktu.** Kolom waktu wajib ada di `group_by`, fungsi LAST/FIRST tidak ada, dan hasilnya hanya berupa dataset Parquet, tidak pernah baris.
   - query_metric dan bukti tingkat 1 butuh endpoint baru `POST /v1/summary` (G18 fase 2). Satu mekanisme dipakai keduanya.
3. **Bundle manifest tidak menyimpan `query_id`/`query_hash` Governor** (`bundles.py:170-173`; dibuang setelah cek cakupan). Lineage butuh perubahan kontrak: hanya bundle baru yang tercatat.
4. **`ResultStore` belum bisa membaca** satu output, satu eksekusi, atau ekspor. Tabel `AI_conversation_export` sudah ada (migrasi 006) tetapi belum dipakai.
5. **Generator Tool_Catalog hanya menaikkan versi alat lama.** Alat baru butuh template "alat baru" (preseden `20260926_001_register_dataneed_tools.sql`).
6. **Baseline `ma-golden-20261002c` tidak mengukur indeks kejedot maupun TERCEK.** `repair_ledger` hanya ada di log orc `ai_run_completed`, tidak di respons API.
7. **`inspect_session` hanya memeriksa variabel.** Profil kolom sesi (DuckDB, `carried.py:71-134`) sudah ada, tetapi hanya di memori dan tidak muncul di `prepare_data_bundle`.

---

# Bagian 1 — Fase D

Urutan disusun supaya fondasi bersama dibuat sekali dan dipakai semua alat:

```
D0 fondasi ─► D1 inspect ─► D2 artefak ─► D3 lineage ─► D4 ekspor ─► D5 G18-2 + query_metric ─► D6 bukti
```

Deploy dilakukan per sub-fase supaya masalah ketahuan lebih awal. Urutan deploy: Governor → sandbox → orc. Semuanya di dev, dari cabang `claude/g2-g3-reactivation`. Semua alat:
- ada di balik flag (bawaan mati, dinyalakan di dev setelah tes);
- memakai envelope;
- kode error baru masuk `ERROR_ACTIONS` (tes AST menangkap yang terlewat);
- deskripsinya pendek, detail di buku metode;
- masuk Tool_Catalog lewat generator, ke `AI_TOOLS.md` (`PLAIN` + `SWITCHES`), dan ke set alat baca-saja (`DISCOVERY_TOOLS`, daftar giliran rencana, `router.READ_ONLY_TOOLS`) bila relevan.

## D0. Fondasi bersama

**Kelas masalah:** setiap alat yang membaca hasil lama butuh isi tabel, padahal orc tidak bisa membaca Parquet dan salinan sandbox hilang setelah 24 jam. Ini berlaku untuk tabel G1–G4, tabel bukti, ekspor, dan nanti data makro/lintas aset.
**Lapisan:** kontrak service. Permanen.

1. **Sandbox — operasi tabel tersimpan tanpa sesi** (`app/stored_tables.py` baru, rute di `app/main.py`).
   - Rute `POST /v1/stored-tables/{op}` dengan `op` = `page` | `export` | `recount`.
   - Body berisi file mentah. Metadata dikirim di header base64url (pola `X-Saniti-Output-Meta` dari `/carried`).
   - Checksum diverifikasi, batas ukuran memakai `restore_max_bytes` yang sudah ada, dan pembacaan berjalan di threadpool.
   - Kapabilitas runtime baru: `stored_tables: {version: 1, ops: [...]}`.
2. **Orc — penyedia byte output** (`app/result_store.py`, fungsi `output_bytes`).
   - Ambil dari sandbox (`GET .../outputs/{oid}/file`) selama salinannya masih ada; selain itu dari R-STORE (Postgres `content` atau bucket).
   - Dipakai D2, D4 dan D6.
3. **ResultStore — metode baca baru:** `output(conversation_id, output_id)`, `execution(conversation_id, execution_id)`, `export(conversation_id, export_id)` (metadata tanpa isi), `export_chunks(...)`.
   - Semua dibatasi `conversation_id`, sehingga percakapan lain tidak pernah terbaca.
4. **Generator Tool_Catalog — template "alat baru".**
   - `scripts/generate_tool_catalog_migration.py` mendapat round `round_d` dengan dua bagian:
     - versi baru untuk alat lama, dengan pola `INSERT … SELECT` yang sudah ada;
     - baris baru (status inactive) untuk alat baru, dengan preflight "belum ada".
   - Tes drift dipindah ke round terbaru. Cek `data_as_of_policy` yang di-hardcode untuk NEWEST (`test_data_need_tool.py:335-352`) diubah supaya membaca round tempat alat itu terakhir berubah.
5. **Ukuran kejedot (bahan GT)** — orc `ExecutionMetadata.friction` berisi `{rejected_tool_calls, gate_repairs, repeated_data_orders, capacity_waits}`.
   - Diturunkan dari `repair_ledger` dan hasil alat yang sudah ada, bukan dihitung manual.
   - Muncul di respons API dan log `ai_run_completed`. Bukan fitur model, jadi tidak perlu flag.

**Tes:**
- sandbox: page, export dan recount dengan checksum salah, file terlalu besar, format bukan PARQUET;
- orc: `output_bytes` fallback sandbox → Postgres → bucket; baca lintas percakapan ditolak; friction dihitung dari ledger contoh;
- generator: hasil round_d diparse (R27) dan round lama tetap beku.

## D1. inspect_dataset — statistik kolom sebelum menghitung

- **Penyebab:** `prepare_data_bundle` hanya menampilkan nama kolom; AI menghitung tanpa tahu null, rentang atau celah.
- **Kelas masalah:** setiap dataset dari DataNeed, termasuk nanti makro dan lintas aset.
- **Lapisan:** profiler sandbox. Permanen.

**Perubahan:**
- **Profiler** `runtime/profiler.py` (proses validator terkurung) menambah `quality.columns[]` per kolom:
  - `nulls`;
  - angka: `min` / `median` / `max`;
  - DIMENSION/IDENTIFIER: `distinct` (dibatasi);
  - per entitas: `entities_with_gaps`, yaitu jumlah entitas yang kehilangan tanggal di dalam rentangnya sendiri.
  - Celah diukur terhadap **kalender tanggal dataset itu sendiri**, bukan kalender IDX, sehingga data bulanan atau makro tidak dianggap bolong.
  - Statistik disimpan di manifest (permanen di SQLite).
- **`model_view`** (`bundles.py:388-414`) menampilkan maksimum 30 kolom × 5 angka, plus `columns_not_shown`.
- **`inspect_session`** mendapat argumen nullable `dataset` (logical_name).
  - Sandbox mengembalikan statistik lengkap kolom dataset itu dan daftar entitas bercelah (maksimum 50), tanpa baris data.
  - Sumbernya manifest, jadi tetap bisa dibaca setelah file bundle kedaluwarsa.
- **Tool_Catalog:** versi baru `prepare_data_bundle` dan `inspect_session`.

**Tidak tercakup:** contoh baris tetap lewat `inspect_session` dengan `names`. Kolom teks bebas tidak dihitung distinct-nya.

**Tes:**
- dataset harian dengan celah → `entities_with_gaps` benar;
- dataset bulanan → 0 celah;
- 40 kolom → 30 tampil + `columns_not_shown: 10`;
- tes kontrak orc memakai `model_view` asli sandbox (pola M68).

## D2. get_artifact — membuka tabel, JSON, kode, chart dan file lama

- **Penyebab:** `get_session_output` wajib `session_id` dan hanya membaca sandbox (24 jam). Kode eksekusi lama tidak bisa dibuka.
- **Kelas masalah:** setiap referensi lintas giliran (output, kode, ekspor, bukti).
- **Lapisan:** alat orc + R-STORE. Permanen.

**Perubahan:**
- **Nama alat tetap `get_session_output`** (versi baru) supaya prompt, `read_more` dan router tidak pecah. Kemampuannya menjadi "get_artifact".
- **Argumen** (semua nullable, tepat satu sumber):
  - `ref` (`out.oN`, dari buku catatan), atau `output_id`, atau `execution_id`, atau `export_id`;
  - `session_id` menjadi opsional;
  - `include_content`, `offset`, `limit`.
- **Isi per jenis:**

  | Jenis | Isi |
  |---|---|
  | TABLE / CSV | Baris berhalaman: dari sandbox bila salinannya masih ada, selain itu `stored-tables/page` dari R-STORE |
  | JSON / TEXT | Potongan teks |
  | SCRIPT (`execution_id`) | Kode dari `AI_conversation_execution`, maks. 20 KB bila `include_content`; selalu ada sha, modul, status dan ringkasan akses |
  | CHART | Metadata + daftar tabel yang dirilis oleh eksekusi yang sama (diturunkan dari `execution_id`) |
  | EXPORT | Metadata file, tanpa isi |

- **Bawaan `include_content: false`:** respons hanya berisi metadata, ukuran, sha256 dan lineage singkat.
- Penyelesaian `ref` memakai `data_record.outputs[]`. Bila value references mati, alat tetap menerima `output_id`/`execution_id`.
- **Flag:** `AI_ENABLE_RESULT_STORE` (sudah ada; R-STORE adalah prasyaratnya).

**Tidak tercakup:** isi chart (PNG) tidak pernah dikirim ke model.

**Tes:**
- output masih di sandbox → dibaca dari sandbox;
- output kedaluwarsa → dibaca dari R-STORE dengan angka yang sama;
- SCRIPT dipotong pada 20 KB;
- ref percakapan lain → `NOT_FOUND`;
- ref tidak dikenal → `next_action`.

## D3. get_lineage — "angka ini dari mana"

- **Penyebab:** rantai jawaban → tabel → kode → bundle → query → tabel sumber tersebar dan sebagian tidak tercatat (query Governor).
- **Kelas masalah:** setiap angka yang dikutip, termasuk gerbang "konsisten" (M63) dan bukti D6.
- **Lapisan:** kontrak sandbox (manifest) + alat orc. Permanen untuk bundle baru.

**Sandbox:**
- `bundles.py` `_manifest` menyimpan per dataset `governor: {query_id, query_hash, rows, executed_scope}` dari grant. Ini hanya untuk bundle baru; bundle lama ditandai `governor: NOT_RECORDED`.
- Endpoint ringkas baru `GET /v1/bundles/{id}/lineage`:
  - isi: per dataset `logical_name`, `source_table`, scope, `restricted_by`, `relationships`, rows, rentang aktual dan governor;
  - tanpa baris data;
  - akses hanya untuk request atau kunci percakapan pemilik bundle (`/v1/bundles/{id}` saat ini tanpa cek, jadi endpoint baru diberi cek).

**Orc** — alat baru `get_lineage` dengan argumen `ref` | `output_id` | `execution_id`. Sumbernya:
- data record dan baris R-STORE (lineage, `data_as_of`, definisi);
- eksekusi (`access`: rentang/kolom yang dibaca, `load_output`);
- lineage bundle dari sandbox.

Tabel bawaan `load_output` ditelusuri rekursif sampai kedalaman 3, dengan penjaga siklus. `source_tables` diturunkan dari `source_table` dan relasi, bukan ditulis tangan.

**Flag:** `AI_ENABLE_LINEAGE_TOOL`.

**Tes:**
- output dari bundle baru → `query_id` muncul;
- bundle lama → `NOT_RECORDED`;
- rantai `load_output` dua tingkat;
- bundle percakapan lain → 404.

## D4. export_result — file unduhan

- **Penyebab:** user tidak bisa mengunduh hasil.
- **Kelas masalah:** setiap tabel output, dan nanti tabel bukti.
- **Lapisan:** sandbox (penulis file) + DB percakapan + API orc. Permanen.

**Sandbox:**
- `stored-tables/export` menulis CSV dan Parquet (pyarrow) atau XLSX (**`openpyxl` baru** di `requirements.txt`, versi dipin).
- XLSX mendapat lembar `definisi` dan `lineage` dari metadata yang dikirim orc.
- Batas 20 MB → `EXPORT_TOO_LARGE`, dengan `next_action`: kurangi kolom atau baris, atau pilih PARQUET. Batas baris Excel juga dicek.

**Orc:**
- Alat `export_result` dengan argumen `source.ref` (nanti juga `evidence_id`), `format`, `include_definition`, `include_lineage`.
- Alurnya: ambil byte lewat D0, minta sandbox menulis file, simpan di `AI_conversation_export`.
- **Model hanya melihat** `export_id`, nama, ukuran dan format.

**API:**
- Respons mendapat `artifacts[]` berisi `export_id`, `file_name`, `format`, `size_bytes`, `sha256` dan `download_path`.
- Unduhan lewat `GET /v1/exports/{export_id}/download`:
  - Bearer yang sama, dan `X-Saniti-Owner` harus pemilik percakapan;
  - isi dibaca per 1 MB lewat `substring` (StreamingResponse);
  - `Content-Disposition` memakai nama yang sudah disaring.
- Dihapus bersama percakapan (cascade yang sudah ada).

**Flag:** `AI_ENABLE_EXPORT`.

**Tes:**
- CSV, XLSX dan Parquet: isi sama dengan sumber, dan lembar definisi/lineage ada;
- file > 20 MB ditolak;
- owner lain → 404;
- ekspor dari output yang sudah kedaluwarsa di sandbox tetap berhasil;
- isi file tidak pernah ada di argumen atau hasil alat (audit).

## D5. G18 fase 2 + query_metric — jalan pintas pertanyaan sederhana

- **Penyebab:** "net asing BBCA 5D dan 20D" butuh 4–6 langkah dan satu sesi Python, karena Governor tidak bisa merangkum antarwaktu.
- **Kelas masalah:** setiap ringkasan per entitas dalam jendela waktu, untuk semua tabel yang aturan agregasinya terisi di katalog (termasuk nanti makro dan lintas aset).
- **Lapisan:** Governor (validasi dan SQL), katalog metrik (definisi), alat orc. Permanen.

**Governor `POST /v1/summary`** (kunci orc). Dipakai juga oleh bukti tingkat 1.
- **Request:**
  - `source_table`;
  - `scope` (pohon PREDICATE yang sama dengan extract) dan `restrictions`;
  - `group_by` (bukan kolom waktu);
  - `measures[{column, time_function, as}]`;
  - `period` berupa `{from, to}` atau `{trading_days: N, as_of}`;
  - `lineage {request_id, purpose: METRIC|EVIDENCE, recipe_sha256}`.
- **Aturan, diturunkan dari katalog (tidak ditulis ulang):**
  - `time_function` harus sama dengan `resample_aggregation` kolom, atau MIN/MAX untuk kolom MEASURE angka;
  - COUNT selalu boleh;
  - setiap kunci grain yang dilepas (entitas, papan, broker, tipe investor) wajib punya `cross_entity_aggregation` yang cocok. Kalau tidak, `AGGREGATION_NOT_ADDITIVE` (contoh: volume lintas saham ditolak).
- **Jendela N hari** dihitung dari kalender tanggal **tabel itu sendiri** sampai `as_of`.
  - Cakupan per entitas (hari ada / hari jendela) ikut dikembalikan.
- **Batas:** maksimum 200 baris, ditambah `query_id` dan `query_hash`. EXPLAIN cost, statement timeout 20 detik dan batas scan sama dengan extract.
- **Kinerja:** sebelum ada indeks, `EXPLAIN (ANALYZE, BUFFERS)` terbatas dijalankan lewat job sementara untuk tiga pola (`Feature_03` 1 saham × 20 hari; `IDX_Broker_Summary` 1 saham × broker × 20 hari; harga 20 hari). Hasilnya dicatat; tidak ada indeks spekulatif.

**Katalog metrik `AI_metric_catalog`** (migrasi DB katalog):
- **Kolom:** `metric_id`, `label`, `description`, `source_table`, `measure_column`, `time_function`, `default_scope` jsonb, `allowed_dimensions`, `formula`, `interpretation`, `recommended_use`, `misuse_warning`, `review_status` (**INFERRED**; tidak ditandai VERIFIED sebelum user mengonfirmasi), `is_active`.
- Satuan dan aditivitas **tidak disalin**; dibaca dari `AI_column_catalog` saat dipakai.
- **Pelengkap migrasi:** Table_Catalog, Column_Catalog, dan grant ke `market_ai_catalog_reader`. Governor tidak membaca katalog ini, karena ia memvalidasi resep dari katalog kolom sendiri.
- **Metrik awal (keputusan D-a…D-c):**

  | metric_id | Sumber | Fungsi waktu | Catatan |
  |---|---|---|---|
  | `net_foreign_value` | `Feature_03.foreign_net_value` | SUM | per saham/papan; antar-saham SUM |
  | `broker_net_value` | `IDX_Broker_Summary."Net Value"` per `"Broker"` | SUM | dimensi Investor Type dan Market Board |
  | `volume` | `Price_Stock_Indonesia_IDX.volume` | SUM | per saham saja (lintas saham NULL di katalog) |
  | `last_close` | `Price.close` | LAST | |
  | `period_high` / `period_low` | `Price.high` / `Price.low` | MAX / MIN | |
  | ~~nilai transaksi~~ | ditunda (D-b) | | |

**Alat orc `query_metric`:**
- **Argumen:** `metric`, `entities` atau `filters`, `dimensions`, `periods` (misalnya `[5, 20]` hari bursa atau rentang tanggal).
- **`as_of`:** diambil dari pin tanggal data percakapan (R-STORE) atau `data_as_of_policy`.
- **Alur:** satu panggilan `/v1/summary` per periode; hasil ≤ 200 baris langsung ke model, dengan `coverage`, `as_of`, `metric_definition_id` dan `query_id`.
- **Hasil dicatat di buku catatan** sebagai output dengan definisi dan lineage, sehingga bisa dikutip (`out.oN`) dan lolos gerbang provenance tanpa sandbox.
- **Di luar katalog** → `METRIC_NOT_IN_CATALOG`, `next_action CALL:submit_data_need_spec`.
- **Daftar metrik** di deskripsi alat dibaca dari katalog saat startup (derive), bukan ditulis di kode.

**Flag:** `AI_ENABLE_QUERY_METRIC`.

**Tes:**
- Governor (Postgres scratch): hasil `/v1/summary` sama dengan SQL `GROUP BY` biasa untuk SUM 5D/20D, LAST close dan MAX high;
- volume lintas saham ditolak;
- jendela memakai kalender tabel (tabel dengan hari libur berbeda);
- batas biaya ditolak dengan pesan jelas;
- orc: metrik tidak dikenal → `next_action`, hasil bisa dikutip dan lolos provenance.

## D6. get_evidence — bukti per klaim (Prioritas 2, WAJIB)

- **Penyebab:** klaim seperti "RB beli bersih 116 dari 132 hari crash" tidak punya bukti yang bisa dicek user, dan tidak dihitung ulang di jalur terpisah dari kode AI.
- **Kelas masalah:** setiap klaim angka di jawaban, di semua tabel yang aturan agregasinya terisi.
- **Lapisan:** kontrak jawaban akhir + gerbang orc, Governor (tingkat 1), sandbox (tingkat 2), DB percakapan. Prompt hanya panduan. Permanen.

**Resep klaim** (alat `get_evidence`):

```
claims[{text, value, unit, ref?, recipe}]
recipe = WAREHOUSE {source_table, scope, group_by, measures, period}
       | BASE_TABLE {ref, where, measure, column}
```

- **Tingkat 1 (WAREHOUSE):** dihitung ulang Governor `/v1/summary` (D5).
- **Tingkat 2 (BASE_TABLE):** dihitung ulang deterministik oleh sandbox `stored-tables/recount` dari tabel dasar yang dirilis (contoh: 132 baris hari crash × RB → hitung `net > 0`).
- **Perbandingan:** toleransi pembulatan sama dengan provenance (`provenance.py`). Hasilnya **TERCEK**, **TIDAK COCOK** (dengan selisih), **TIDAK DICEK (batas)**, atau **TIDAK BISA DICEK** (resep tidak valid).
- **Batas:**
  - 10 resep per jawaban;
  - 200 baris per tabel;
  - 30 detik per query, 120 detik total.
  - Sisa resep dilabeli "bukti tidak dihitung (batas)", tidak pernah diam-diam.

**Penyimpanan:**
- Tabel baru `AI_conversation_evidence` (migrasi DB percakapan 008).
- Kolom: `evidence_id`, `conversation_id` (FK cascade), `request_id`, claim, value, recipe, status, nilai backend, `rows` jsonb ≤ 200, lineage, `created_at`.
- Grant ke `market_ai_conversation_store`; `TABLES` di provisioning menjadi 6 tabel, dan tes privilege diperbarui.
- `export_result` menerima `source.evidence_id`. Baris JSON dikirim ke `stored-tables/export` sebagai Parquet yang dibuat sandbox.

**Gerbang akhir** (`_dataneed_gate`, lewat `_gate_once`; satu perbaikan per jenis):
1. Jawaban dengan referensi nilai angka tetapi tanpa satu pun bukti → satu kali diminta memanggil `get_evidence` untuk klaim utama. Setelah itu jawaban jalan dengan label "bukti tidak dihitung".
2. Klaim TIDAK COCOK → satu kali dikembalikan ke AI dengan selisihnya. Setelah itu tampil dengan anotasi "TIDAK COCOK: backend menghitung X" (pola P17), tidak disembunyikan.
3. Setiap `out.oN` di jawaban otomatis mendapat entri bukti "DIRUJUK" (baris yang dirujuk + lineage), tanpa AI memanggil alat.

**Keluaran:**
- **Ke user:** respons API `evidence[]` berisi klaim, status, resep, tabel ≤ 200 baris, dan `export_id` bila lebih panjang.
- **Ke model:** hanya status dan selisih.
- **Buku metode:** versi 4. Analisis wajib merilis tabel dasar untuk klaim utama (helper `event_study` dan riset sudah otomatis); resep klaim dijelaskan di buku metode, bukan di deskripsi alat.

**Flag:** `AI_ENABLE_EVIDENCE`.

**Tidak tercakup:**
- Klaim statistik (p-value, model) hanya mendapat bukti masukan, dengan label "tidak dicek langsung".
- Rata-rata lintas saham menunggu S20.

**Tes:**
- Resep tingkat 1 cocok → TERCEK.
- Resep dengan angka salah → TIDAK COCOK, satu perbaikan, lalu anotasi.
- Kasus tingkat 2 "116 dari 132" dari tabel `_events`.
- Lebih dari 10 resep → label batas.
- Kasus lain selain yang diamati:
  - klaim min/maks harga dari `Price`;
  - klaim jumlah broker dari `Feature_03`.

## Migrasi, katalog dan catatan Fase D

| Migrasi | DB | Isi |
|---|---|---|
| `…_008_conversation_evidence.sql` | percakapan | `AI_conversation_evidence` + grant + Table/Column_Catalog |
| `…_009_ai_metric_catalog.sql` | katalog | `AI_metric_catalog` + 5 metrik (INFERRED) + Table/Column_Catalog + grant |
| `…_010_ai_method_guides_v4.sql` | katalog | buku metode v4 (generator, `VERSION_TARGETS` + 4) |
| `…_011_round_d_tool_catalog.sql` | katalog | versi baru `prepare_data_bundle`, `inspect_session`, `get_session_output`; alat baru `get_lineage`, `export_result`, `query_metric`, `get_evidence` (inactive) |

Semua migrasi:
- dibuat generator bila berisi teks;
- diparse di tes;
- dijalankan lewat job sementara DRYRUN → APPLY → baca balik → job dihapus;
- dicatat di `APPLIED.sha256`.

Setiap sub-fase memperbarui catatan berikut:
- `DATABASE_SCHEMA.md` (sync), `DATABASE_CHANGELOG.md`, `RAILWAY_CHANGELOG.md`;
- `ERRORS_AND_SOLUTIONS.md` (entri baru dan pelajaran Part D);
- `AI_TOOLS.md` (regenerasi dengan `--flags`), README service;
- progres di `ROUND_PLAN_2026-10-03.md`, `OUTSTANDING_ISSUES.md`.

Setelah perubahan variabel Railway: `railway config pull --force` + `railway config plan`.

## Deploy per sub-fase (dev saja)

| Sub-fase | Deploy | Flag dinyalakan di dev |
|---|---|---|
| D0 + D1 | sandbox → orc | — |
| D2 | orc | (R-STORE sudah aktif) |
| D3 | sandbox → orc | `AI_ENABLE_LINEAGE_TOOL` |
| D4 | migrasi Tool_Catalog parsial bila perlu, sandbox (openpyxl) → orc | `AI_ENABLE_EXPORT` |
| D5 | migrasi 009 → Governor (`railway up` dari cabang, seperti `deae118b`) → orc | `AI_ENABLE_QUERY_METRIC` |
| D6 | migrasi 008 + 010 + 011 → sandbox → orc | `AI_ENABLE_EVIDENCE` |

- Governor live di dev adalah unggahan CLI dari cabang ini. `main` tidak disentuh; push `main` yang menyentuh folder Governor akan menimpa (sudah tercatat).
- Rollback dilakukan per service ke deployment sebelumnya, dan setiap fitur bisa dimatikan lewat flag.

## Risiko dan mitigasi

| Risiko | Mitigasi |
|---|---|
| Token definisi alat naik (4 alat baru) | Deskripsi pendek; alat hanya terdaftar bila flag dan prasyarat aktif; detail di buku metode v4 |
| Kalender jendela N hari mahal di `IDX_Broker_Summary` | EXPLAIN terbatas dulu; kalender diambil dari baris yang sudah tersaring scope; batas biaya Governor |
| Parquet dari kode AI dibaca di proses service sandbox | Batas ukuran, checksum, threadpool; preseden yang sama dengan `carried.profile` (DuckDB) |
| Bukti memperlambat jawaban | 10 resep / 120 detik; tingkat 2 tanpa query gudang |
| Gerbang bukti menolak jawaban wajar | Hanya satu perbaikan, lalu label; tidak pernah memblokir jawaban |
| Definisi metrik keliru | Status INFERRED, tes nilai terhadap SQL independen, dan konfirmasi user sebelum VERIFIED |
| `ExecutionMetadata` `extra=forbid` | Field baru opsional, dibuang bila null (pola `mode4`/`annotations`) |

## Verifikasi Fase D

- **Tes lokal:**
  - orc (`ORC_TEST_POSTGRES_URL` scratch) — target ≥ 1.140 tes lulus ditambah tes baru;
  - sandbox (`/opt/venv-sbx`, root) ≥ 729;
  - Governor dari venv bersih yang dibangun dari `requirements.txt` (R19), dengan Postgres scratch.
- **Tes drift:** `AI_TOOLS.md`, Tool_Catalog round terbaru, buku metode orc = sandbox.
- **Live dev:**
  - setiap deployment `SUCCESS`, dan log startup memuat kapabilitas baru (`stored_tables`, lineage) dan alat aktif;
  - migrasi dibaca balik;
  - login percakapan menjangkau 6 tabel;
  - `/v1/summary` dicoba sekali lewat job sementara dengan pembanding SQL langsung (tanpa model).
- **Tidak ada golden test** sampai user memerintahkan (Bagian 2).

---

# Bagian 2 — Rencana golden test setelah Fase D (dijalankan HANYA atas perintah user)

**Tujuan:** mendeteksi masalah dari semua update round ini (A–D), dan membandingkannya dengan `ma-golden-20261002c` (USD 1,26; 25 giliran; 31 menit).

## GT-0. Persiapan (tanpa lalu lintas model)

1. **Baseline indeks kejedot.**
   - Baca log orc deployment `b3aaae90` (event `ai_run_completed`, request `ma-golden-20261002c-*`).
   - Hitung `repair_ledger`, penolakan alat, dan pesanan data ulang dengan rumus yang sama dengan `friction` (D0).
   - Bila log sudah lewat retensi Railway, baseline dicatat "tidak tersedia", dan pembanding hanya iterasi/biaya/detik.
2. **Cek status:**
   - semua deployment `SUCCESS`;
   - `/v1/runtime` sandbox (`session_release` 1, `result_store` 1, `stored_tables` 1, `method_guides` 4);
   - snapshot flag dev (nama dan true/false saja);
   - baca balik DB: Tool_Catalog aktif, buku metode v4, 6 tabel percakapan, `AI_metric_catalog`.
3. **Runner `apps/orc-test-runner`:**
   - item mendapat `checks` opsional yang dievaluasi otomatis dari respons, termasuk `friction`, `evidence[]`, `artifacts[]` dan `data_record`;
   - runner mengunduh `artifacts[]` dan memverifikasi sha256;
   - baris `OTR` memuat `friction` dan jumlah TERCEK / TIDAK COCOK.
4. **Kunci baca audit sementara** `AUDIT_STORE_READER_KEY`:
   - dibuat untuk GT dan dihapus setelahnya;
   - hanya namanya yang dicatat;
   - rotasi `AUDIT_STORE_SANDBOX_KEY` tetap keputusan user.

## GT-1. Suite (prefix `ma-golden-round-<tanggal>`, 3 worker)

| Item | Update yang diuji | Cek otomatis / sumber |
|---|---|---|
| g1, g1_repeat | M68, ENV, 1b, 1c, D1, D6 | Catatan scope memuat nilai saringan, tidak ada "= ___" (data_record). Hasil alat ber-envelope dengan `next_action` pada error (audit). `data_as_of` = hari bursa terakhir (1b). Status kesegaran tampil di COVERAGE (audit). `model_view` memuat statistik kolom. Ada bukti TERCEK. |
| g2, g4 | regresi | Status dan biaya tidak lebih buruk dari baseline |
| g3 | S27, D6 tingkat 2 | Tabel alur → klaim TERCEK dari tabel dasar |
| g5 (9 giliran) | G19, S28, R-STORE, D3, D6 | Pesanan BUMN dan non-BUMN terpisah, tidak ada dataset kosong; bila kosong → `EMPTY_REQUEST`/`EMPTY_INPUT`, bukan INSUFFICIENT_EVIDENCE (audit argumen utuh). 0 `SESSION_CAPACITY_EXCEEDED` dan log `request_sessions_released` per request. Klaim "132 hari crash RB" punya bukti tingkat 2. `answers[]` bertambah per giliran. Baris `AI_conversation_output`/`_execution` ada. Giliran tambahan "angka ini dari mana?" → `get_lineage` dengan tabel sumber dan `query_id` |
| g6 + g6_revise | M69, M70, P26 | Mode 4 mengajukan rencana v1 dengan `success_rule` dari kata user. Horizon 10 hari di semua sudut dan usulan. Satuan konsisten, sampel rekomendasi ≈ 1.487 (bukan 14,8 juta). Tidak ada angka konteks aplikasi yang dianggap kata user. REVISE menyimpan temuan lama `<id>@n` |
| g7 | M68, S28 | Giliran 2 tidak mengulang pesanan data. Satu sesi per jawaban. Iterasi ≤ 12 (baseline 26) |
| g8_metric (baru) | D5 | "Net beli asing BBCA 5D dan 20D" → 1 panggilan `query_metric`, sumber `Feature_03`. Angka sama dengan SQL independen (job baca-saja). `coverage` dan `as_of` tampil |
| g9_resume (baru) | R-STORE, C2e | Giliran 1 menghasilkan tabel. Masa simpan sandbox dipendekkan (di bawah), lalu giliran 2 merujuk tabel lama → log `carried_restored`, angka sama, baris pengungkapan tanggal data. Giliran 3 "pakai data terbaru" → NEWEST + baris perbedaan tanggal |
| g10_export (baru) | D4, D2 | Ekspor XLSX dengan lembar definisi dan lineage. Runner mengunduh, sha256 cocok, owner lain 404. "Tunjukkan kode yang dipakai" → `get_session_output` SCRIPT |
| g11_plan_expiry (baru) | C2e-1 | Rencana dibuat, ditunggu > 1 jam (jendela yang sama dengan g9), lalu "setuju" → jawaban "Rencana ini dibuat <tanggal>; setujui ulang?", lalu setuju lagi → jalan |
| paralel | S28 | 3 worker serentak: 0 `SESSION_CAPACITY_EXCEEDED`, antrean terlihat di log `session_open_waited` bila terjadi |

**Simulasi kedaluwarsa (g9, g11):**
- `PY_SANDBOX_RESULT_RETENTION_HOURS=1` dan `PY_SANDBOX_BUNDLE_RETENTION_HOURS=1` di sandbox dev selama GT. Ini nilai minimum konfigurasi, tanpa kode khusus tes.
- Urutannya: giliran 1, tunggu ± 70 menit (sweep), lalu giliran berikutnya. Setelah itu kembali ke 24.
- Dicatat di `RAILWAY_CHANGELOG.md`, lalu `config pull`/`plan`.
- Efek samping: percakapan dev lain dalam jendela itu ikut kedaluwarsa 1 jam.

**Per giliran dicatat:**
- status, detik, biaya, iterasi, `tool_calls`;
- `friction` (indeks kejedot);
- TERCEK / TIDAK COCOK;
- jumlah `SESSION_CAPACITY_EXCEEDED`.

**Baca balik DB** (job sementara, SELECT saja):
- jumlah baris `AI_conversation_output`/`_execution`/`_export`/`_evidence` per percakapan GT;
- POSTGRES vs BUCKET;
- objek bucket tanpa baris = 0.

## GT-2. Laporan

- **`GOLDEN_TEST_ROUND_2026-10-03.md`:** tabel sebelum vs sesudah per item (kejedot, iterasi, biaya, detik, TERCEK), dan putusan per update A–D.
- **Masalah baru:** dicatat di `ERRORS_AND_SOLUTIONS.md` dengan akar masalah terverifikasi sebelum ada usulan perbaikan.
- **Bersih-bersih:** kunci baca audit sementara dihapus, masa simpan sandbox dikembalikan ke 24, job dihapus.
- **Perkiraan:** ± 40 giliran, ± 2,5 jam (termasuk tunggu 70 menit), biaya model ± USD 2–3.

**Kriteria lulus:**

| Ukuran | Syarat |
|---|---|
| `SESSION_CAPACITY_EXCEEDED` | 0 |
| Riset di atas dataset kosong | 0 |
| Satuan rencana | Konsisten |
| Horizon | Terkunci |
| Angka resume | Sama |
| Ekspor | sha256 cocok |
| query_metric | Sama dengan SQL independen |
| Klaim TIDAK COCOK | Tampil apa adanya |
| Indeks kejedot dan iterasi | Turun dibanding baseline (bila baseline tersedia) |

---

## Progres (2026-10-03)

| Bagian | Status |
|---|---|
| D0 fondasi | LIVE dev: operasi tabel tersimpan (sandbox), baca ResultStore, `output_bytes`, `execution.friction` |
| D1 statistik kolom | LIVE dev (sandbox `920d7cc4`) |
| D2 buka hasil/kode lama | LIVE dev (orc `9ce37963`); nama alat tetap `get_session_output`. **Beda dari rencana:** isi tabel tetap dikirim berhalaman seperti sebelumnya (bawaan `include_content` hanya untuk kode), supaya alur yang sudah ada tidak berubah |
| D3 get_lineage | LIVE dev, `AI_ENABLE_LINEAGE_TOOL=true` |
| D4 export_result | LIVE dev, `AI_ENABLE_EXPORT=true` |
| D5 G18-2 + query_metric | LIVE dev: Governor `0fa3f146`, migrasi `20261003_008` (diterapkan dan dibaca balik), `AI_ENABLE_QUERY_METRIC=true`; EXPLAIN terukur, tidak ada indeks baru; uji asap `/v1/summary` = SQL langsung |
| D6 get_evidence | Belum mulai. Nomor migrasi bergeser: 008 dipakai katalog metrik, jadi bukti = 009, buku metode v4 = 010, Tool_Catalog round D = 011 |

Tes: orc 1.167, sandbox 745, Governor 254 lulus. Belum ada lalu lintas model (golden test atas perintah user).
