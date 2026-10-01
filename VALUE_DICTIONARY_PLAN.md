# Rencana: kamus nilai dan alat "cari nilai" (P9)

Status: **rencana, belum dijalankan** (permintaan user 2026-10-01: dipisah dari batch perbaikan Langkah 8). Rencana ini
berdiri sendiri karena menyentuh database (tabel baru, migrasi, katalog), SQL Governor, market-ai-orc dan satu job
terjadwal.

## 1. Masalah

AI tahu **apa** yang mau difilter (dari pertanyaan user), tetapi tidak tahu **cara menuliskannya persis** sebagai nilai
yang tersimpan di database, dan tidak bisa memastikan nilainya ada.

Bukti dari audit `ma-steps-20261001a`, m01:

- **2-m4a.** AI berpikir 523 s, lalu meminta nilai `Market Board` dari `IDX_Broker_Summary`. Ditolak
  `DIMENSION_VALUES_STATIC_ONLY`: "IDX_Broker_Summary is dated; dimension values come from static reference tables".
  Di iterasi 2 AI sudah membaca deskripsi kolom "IDX market board: Regular, Nego, or Tunai", tetapi itu teks bebas,
  bukan daftar resmi.
- **2-m4b.** AI berpikir 583 s, lalu meminta nilai `Ticker` BMRI/BBRI/BBNI/BBTN dari `IDX_Stock_Universe`. Ditolak
  `DIMENSION_IS_ENTITY`: "Ticker identifies entities; list them in an ENTITY_LIST scope instead".
- **Setiap tahap.** AI mencari ulang `Industry` "Bank", yang di tabel referensi memang berhasil.

## 2. Akar masalah (terverifikasi di kode)

Alat yang ada untuk "mengintip" database punya dua titik buta:

| Alat | Yang diberikan | Kenapa tidak cukup |
|---|---|---|
| `get_catalog_details` | Deskripsi kolom (teks bebas) | Bukan daftar nilai resmi |
| `preview_table_rows` | Maksimal 20 baris, urutan tetap | Tidak pernah lengkap; 20 baris teratas tabel harian hampir pasti hanya "Regular", 20 kartu saham pertama hanya AALI, ABBA, … |
| `get_dimension_values` | Nilai unik kolom kategori | Hanya tabel statis (`governor.py` `DIMENSION_VALUES_STATIC_ONLY`) dan bukan kolom entitas (`DIMENSION_IS_ENTITY`); mencari nilai unik di tabel puluhan juta baris saat ditanya terlalu berat |

Database sendiri sudah memegang daftar resmi untuk sebagian kolom (CHECK constraint, misalnya
`IDX_Broker_Summary_market_board_check`, `..._investor_type_check`, dan constraint yang sama di Feature 02), tetapi
daftar itu tidak pernah ditunjukkan ke AI.

## 3. Kelas masalah

Penerjemahan kata pengguna ke nilai persis yang tersimpan (*value linking / entity matching*). Berlaku untuk:

- setiap kolom teks yang dipakai untuk memfilter, di semua tabel: kategori di tabel harian, kategori di tabel
  referensi, dan kode entitas (saham, broker);
- data lintas aset dan makro nanti: kode negara, mata uang, seri indikator, tenor.

## 4. Pembanding di luar

| Sistem | Cara | Kapan |
|---|---|---|
| Snowflake Cortex Analyst | `sample_values` di model semantik untuk kolom berkardinalitas rendah (sekitar 1–10); layanan Cortex Search untuk kolom berkardinalitas tinggi atau sering berubah | Otomatis sebelum SQL ditulis; jumlah nilai yang diberikan ke model dibatasi |
| Databricks Genie | Entity matching (dulu value dictionary): nilai asli kolom string disimpan dan dicocokkan ke istilah pengguna ("Florida" → "FL"). Maksimal 1.024 nilai unik per kolom, 127 karakter per nilai, 120 kolom; bisa di-refresh | Otomatis |
| LangChain SQL agent | Alat `search_proper_nouns`: semua nama unik diindeks; model wajib mencari dulu sebelum memfilter nama | Dipanggil model |
| CHESS (Stanford) | Ekstraksi kata kunci, lalu pengambilan nilai dari jutaan baris (LSH) disaring dengan kemiripan ejaan dan makna | Otomatis, sebelum SQL |

Pola yang sama di semua sistem:

1. kamus nilai disiapkan di depan, bukan dipindai saat ditanya;
2. nilai sedikit langsung ditampilkan, nilai banyak lewat pencarian;
3. pencocokan toleran (huruf besar/kecil, salah ketik);
4. hasilnya selalu nilai persis yang tersimpan.

Sumber:

- [Snowflake: literal search for Cortex Analyst](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst/cortex-analyst-search-integration)
- [Snowflake: semantic model specification](https://docs.snowflake.com/user-guide/snowflake-cortex/cortex-analyst/semantic-model-spec)
- [Databricks: Genie sample values and entity matching](https://docs.databricks.com/gcp/en/genie/sample-values)
- [LangChain: high-cardinality categoricals](https://python.langchain.com/docs/how_to/query_high_cardinality/)
- [CHESS paper](https://scalingintelligence.stanford.edu/pubs/CHESSpaper.pdf)

## 5. Rancangan

### 5.1 Tabel baru `AI_value_dictionary` (lapisan: database dan katalog)

Satu baris per nilai per kolom. Kolomnya:

- `table_name`, `column_name`, `value` (persis seperti tersimpan), `value_folded` (huruf kecil, spasi dirapikan, untuk
  pencocokan);
- `source`: `CHECK_CONSTRAINT`, `REFERENCE_TABLE` atau `DISTINCT_SCAN`;
- `column_kind`: `CATEGORY` atau `ENTITY`;
- `distinct_count` (kolom), `complete` (apakah daftar kolom ini lengkap);
- `first_seen`, `last_seen` bila diturunkan dari data;
- `refreshed_at`, `refresh_run_id`.

Primary key `(table_name, column_name, value)`. Index untuk pencarian dibuat hanya setelah pengukuran (§7): `value_folded`,
dan trigram (`pg_trgm`) bila ekstensinya tersedia di Railway.

**Kolom mana yang masuk** diturunkan dari katalog, tanpa daftar manual:

- semua kolom teks `ai_allowed`, tidak `is_sensitive`, dan `group_by_allowed` atau kolom entitas tabel statis di
  `AI_column_catalog`;
- kolom dengan lebih dari ambang nilai unik (awal 1.024, mengikuti Genie; diturunkan dari setting, bukan konstanta di
  kode) ditandai `complete = false` dan tidak dipindai penuh.

**Urutan sumber nilai** (yang pertama tersedia dipakai):

1. CHECK constraint kolom itu (`pg_constraint`, `= ANY (ARRAY[...])`). Pasti lengkap dan murah.
2. Tabel referensi, bila kolom itu punya relasi terdaftar ke tabel statis (`AI_catalog_relationships`). Contoh:
   `IDX_Broker_Summary."Broker"` → `IDX_Broker_Profile.broker_code`. Ditandai bahwa relasi ini logis, tanpa foreign key.
3. `DISTINCT` terbatas pada tabelnya sendiri: hanya tabel statis, atau tabel bertanggal lewat index yang ada, setelah
   `EXPLAIN (ANALYZE, BUFFERS)` membuktikan biayanya wajar.

### 5.2 Pengisian dan pembaruan (lapisan: job terjadwal)

- Diisi oleh job terjadwal setelah data harian masuk, satu transaksi per kolom dan idempoten (upsert pada primary key,
  nilai yang hilang ditandai, bukan dihapus diam-diam).
- **Keputusan user 2026-10-01: memperluas job `ai-data-coverage` yang sudah ada.** Pola, deploy dan cron-nya sama.
  Job itu satu-satunya penulis tabel ini. Langkah kamus dijalankan setelah langkah coverage, dan kegagalan langkah kamus
  tidak membatalkan hasil coverage. Keduanya dicatat terpisah di log job.
- Hasil setiap pembaruan dicatat di log (jumlah kolom, nilai baru, nilai hilang, durasi).

### 5.3 Pilihan sedikit langsung tampil (lapisan: katalog di orc; keputusan user 2026-10-01: dua jalur, katalog dan alat)

`get_catalog_details` bagian COLUMNS menampilkan `allowed_values` untuk kolom dengan `complete = true` dan nilai sedikit.
Ambangnya diturunkan dari setting, awal 20; Cortex menyarankan sekitar 10. Contoh:
`Market Board: allowed_values ["Nego","Regular","Tunai"] (source CHECK_CONSTRAINT)`. AI tidak perlu memanggil alat untuk
kolom seperti ini.

### 5.4 Alat baru `search_values` (lapisan: market-ai-orc + SQL Governor)

Masukan:

- `table`, `column`;
- `query`: satu atau beberapa istilah, wajib untuk kolom besar;
- `limit` kecil.

Jawaban selalu berbentuk sama:

- per istilah: `exact` (nilai persis bila cocok tanpa membedakan huruf), `candidates` (nilai mirip dengan skor),
  `found` (true/false);
- untuk kolom: `complete`, `distinct_count`, `source`, `refreshed_at`, dan catatan (mis. "daftar profil broker, belum
  tentu semua kode yang pernah bertransaksi").

Aturannya:

- hanya nilai, tidak pernah jumlah atau ukuran;
- kolom kecil boleh tanpa `query`, menghasilkan daftar lengkap;
- kolom besar wajib `query`, sehingga daftar penuh tidak pernah dikirim;
- pencocokan: sama persis tanpa membedakan huruf, lalu awalan atau kandungan, lalu kemiripan ejaan (trigram atau edit
  distance). Pencarian berdasarkan makna (embedding) **tidak** termasuk;
- dibaca Governor dari `AI_value_dictionary` dengan role baca saja; AI tidak pernah membaca tabel itu langsung;
- `get_dimension_values` tetap ada untuk kompatibilitas. Deskripsinya menunjuk ke `search_values`, dan penolakan
  tabel bertanggal / kolom entitas menyebut `search_values`.

### 5.4b AI tahu alat apa saja yang dimilikinya (permintaan user 2026-10-01)

AI mengetahui alatnya dari tiga tempat, dan ketiganya diperbarui bersamaan dengan alat baru:

1. **Daftar alat yang dikirim di setiap panggilan model.** Ini registry market-ai-orc (`app/tools/__init__.py`): nama,
   deskripsi dan skema argumen `search_values`. Inilah yang benar-benar dibaca model. Deskripsinya menyebut kapan
   memakai `search_values` dan kapan cukup membaca `allowed_values` di katalog.
2. **`get_system_capabilities`** (`app/tools/system.py` `CAPABILITY_TOOLS`): kemampuan baru `value_lookup` →
   `search_values`, sehingga jawaban "alat apa yang tersedia" menyebutnya.
3. **`Tool_Catalog` di database:** baris `search_values` v1 lewat migrasi maju (purpose, input/output schema, batas),
   dan catatan pada `get_dimension_values` yang menunjuk ke alat baru.
   - Terverifikasi (`DATABASE_CATALOG.md`): tidak ada service yang membaca `Tool_Catalog` saat berjalan. Tabel itu
     catatan resmi untuk manusia dan audit, bukan sumber yang dibaca model.
   - Supaya ketiganya tidak berbeda isi, ditambahkan test yang membandingkan skema argumen di registry dengan
     `input_schema` di `Tool_Catalog`, seperti pola test `check_research_feasibility` yang gagal kalau keduanya berbeda.

Aturan "katalog penemuan" di prompt sistem juga menyebut urutannya: baca `allowed_values` di detail katalog dulu; untuk
nilai yang banyak pakai `search_values`. Ini hanya panduan; penjaganya tetap P14.

### 5.4c `get_system_capabilities` wajib dipanggil (permintaan user 2026-10-01)

- **Kondisi sekarang (terverifikasi):**
  - prompt sistem justru berkata "get_system_capabilities is not a routine first step: the tool list already shows what
    is available" (`orchestrator.py` ~349);
  - aturan itu dibuat untuk menghemat panggilan (uji 2026-09-26: penemuan katalog memakan 20% waktu model dan 28%
    biaya);
  - `AI_CATALOG_SUMMARY_IN_PROMPT` tidak aktif di dev.
- **Perubahan:** aturan prompt nomor 4 diganti menjadi "get_system_capabilities wajib dipanggil di awal setiap run".
- **Penegakan oleh backend:** diputuskan user 2026-10-01, pilihan **(a)**, sistem menjalankannya di awal setiap run.
  - **(a) Disarankan:** orc menjalankan `get_system_capabilities` sendiri di awal setiap run, sebelum panggilan model
    pertama. Hasilnya dimasukkan sebagai hasil alat dan dicatat di audit seperti panggilan biasa. Pasti terjadi, tanpa
    satu putaran model tambahan.
  - **(b)** Model wajib memanggilnya sendiri. Kalau model memanggil alat lain lebih dulu, orc menolak panggilan itu
    dengan pesan "panggil get_system_capabilities dulu". Biayanya satu putaran model per run; mode 4 menjalankan 4 run
    per giliran.
- Isi jawaban `get_system_capabilities` ditambah kemampuan `value_lookup` → `search_values` (§5.4b).

### 5.5 Penjaga di belakang: P14 memakai kamus yang sama (lapisan: SQL Governor)

P14 (huruf besar/kecil; Langkah 8 rencana utama) memetakan setiap nilai filter teks ke nilai resmi sebelum query, dengan
kamus ini sebagai sumber pertama:

- cocok tanpa membedakan huruf, satu-ke-satu → dipakai nilai resminya;
- tidak ada di kamus, tetapi kolom `complete = false` → dicek ke data asli dengan biaya terbatas sebelum menolak;
- tidak ada sama sekali → ditolak sebelum penarikan, dengan kandidat dari `search_values`;
- kode broker di luar daftar profil → peringatan saja, tidak ditolak.

Dengan begini, aturan "cari dulu sebelum memfilter" ditegakkan backend, bukan hanya instruksi ke model seperti di
LangChain.

### 5.6 Buku catatan percakapan (P5)

Hasil `search_values` dan `allowed_values` yang dibaca dicatat di data record, supaya tahap berikutnya tidak mencari
lagi.

## 6. Pekerjaan dan catatan wajib (AGENTS.md langkah 5, Part A)

1. Migrasi maju: tabel, constraint, grant (SELECT ke role Governor dan reader katalog; tulis hanya ke role job), dan
   ekstensi `pg_trgm` bila disetujui dan tersedia.
2. `Table_Catalog` (1 baris) dan `Column_Catalog` (semua kolom), dicatat di `DATABASE_CATALOG.md`.
3. `Tool_Catalog`: `search_values` v1 (inactive, `runtime_service = 'market-ai-orc'`, seperti tool orc lain), dan
   catatan pada `get_dimension_values`.
4. `DATABASE_SCHEMA.md`, `DATABASE_CHANGELOG.md` (migrasi dan hasil pengisian pertama), `RAILWAY_CHANGELOG.md` (job dan
   deploy), `.railway/railway.ts` bila ada service atau cron baru.
5. Cek Part A `ERRORS_AND_SOLUTIONS.md` untuk tabel baru ini (grain, primary key, deskripsi yang bisa dicari, nama kolom
   `snake_case`).
6. Entri baru di `ERRORS_AND_SOLUTIONS.md` untuk P9 dengan status yang diperbarui di tempat.

## 7. Performa (diukur sebelum index besar atau pemindaian)

- Query pengisian per sumber, dengan `EXPLAIN (ANALYZE, BUFFERS)` terbatas di dev:
  - CHECK: murah;
  - tabel referensi: kecil;
  - `DISTINCT` pada tabel bertanggal: hanya lewat index yang ada (mis. `Feature_02_Broker_Rolling_date_board_ticker_idx`).
    Kalau pengukuran menunjukkan pemindaian penuh, kolom itu tidak dipindai dan ditandai `complete = false`.
- Query pencarian `search_values` dengan dan tanpa index trigram. Index ditambah hanya bila terbukti perlu.
- Bukti dicatat di `DATABASE_CHANGELOG.md`.

## 8. Uji

**Test unit dan integrasi:**

- CHECK constraint menghasilkan daftar lengkap (Market Board, Investor Type);
- relasi ke tabel referensi (broker);
- kolom di atas ambang ditandai tidak lengkap;
- `search_values`:
  - "reguler" → kandidat "Regular";
  - "bbri" → "BBRI";
  - "XXXX" → not found;
  - kolom besar tanpa `query` → ditolak;
- `allowed_values` tampil di `get_catalog_details` untuk kolom kecil;
- P14 memakai kamus (cocok, tidak ada, kolom tidak lengkap, broker di luar profil);
- pembaruan idempoten (dijalankan dua kali menghasilkan hal yang sama; nilai hilang ditandai).

**Kasus lain selain m01:**

- e02 (net beli asing BBCA: filter `Investor Type` "Foreign"/"asing");
- a05 (semua saham, tanpa filter teks);
- nanti tabel makro atau lintas aset (kode negara, mata uang).

**Kasus yang tidak berlaku:** filter angka dan tanggal, karena tidak ada nilai teks.

**Uji live:**

- suite dengan pertanyaan yang memakai "pasar reguler", "investor asing", "bank BUMN", dan satu salah ketik;
- yang diukur: jumlah panggilan `get_dimension_values` / `search_values`, penolakan, waktu berpikir sebelum filter;
- dibandingkan dengan `ma-steps-20261001a`.

## 9. Keputusan yang dibutuhkan dari user

1. ~~Pembaruan kamus: memperluas job `ai-data-coverage` atau job baru.~~ Diputuskan: memperluas `ai-data-coverage`.
2. ~~Ekstensi `pg_trgm`~~ Diputuskan (user 2026-10-01): `pg_trgm` bila database Railway mengizinkannya (dicek lebih
   dulu, diaktifkan lewat migrasi maju). Kalau tidak diizinkan, pencocokan ejaan dihitung di Governor atas daftar
   kolom yang terbatas.
3. ~~Ambang~~ Diputuskan (user 2026-10-01): "nilai sedikit" 20 dan batas kamus 1.024 nilai per kolom, sebagai
   pengaturan awal (bukan konstanta di kode).
4. ~~Urutan terhadap rencana utama~~ Diputuskan (user 2026-10-01): **P14 dulu**, di Langkah 8 rencana utama.
   - P14 awalnya memetakan nilai ke sumber yang sudah ada: aturan database (CHECK), tabel referensi, dan pengecekan
     terbatas ke data asli.
   - Rencana kamus ini dikerjakan setelahnya. Kamus kemudian menjadi sumber pertama P14 (§5.5) tanpa mengubah kontrak
     P14.

## 10. Risiko dan mitigasi

| Risiko | Mitigasi |
|---|---|
| Kamus basi (nilai baru belum masuk) | Pembaruan terjadwal; `refreshed_at` di setiap jawaban; P14 mengecek data asli sebelum menolak nilai di kolom yang tidak lengkap |
| Pencocokan salah ketik memilih nilai keliru | Kandidat dikembalikan dengan skor; pemetaan otomatis (P14) hanya untuk kecocokan pasti tanpa membedakan huruf |
| Daftar profil broker tidak memuat semua kode transaksi (relasi logis, tanpa foreign key) | Sumber dicatat per nilai; kode di luar profil hanya peringatan |
| Pemindaian `DISTINCT` membebani database | Hanya lewat index dan setelah `EXPLAIN`; di luar itu kolom ditandai tidak lengkap |
| Satu alat lagi menambah pilihan bagi model | `get_dimension_values` menunjuk ke alat baru; nilai sedikit tampil di katalog sehingga alat hanya dipakai untuk nilai banyak |
| Kolom sensitif ikut terindeks | Hanya kolom `ai_allowed` dan tidak `is_sensitive` |

## 11. Yang tercakup dan yang tidak

- **Tercakup:** semua kolom teks yang boleh difilter AI, di semua tabel sekarang dan berikutnya, tanpa perubahan kode
  per tabel.
- **Tidak tercakup:**
  - pencarian berdasarkan makna ("bank pelat merah" → BMRI, BBRI), yang butuh embedding atau layanan tambahan;
  - sinonim lintas bahasa yang ejaannya jauh berbeda (mis. "asing" → "Foreign");
  - kolom angka dan tanggal.

  Untuk "asing" → "Foreign", pilihannya kolom `aliases` yang diisi dari deskripsi katalog atau kurasi. Ini keputusan
  terpisah dan tidak termasuk rencana ini.

Status: permanen.
