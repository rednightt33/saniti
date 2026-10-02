# Rencana penuh + rencana implementasi: HIGH ALERT & masalah kategori 2/3 (2026-10-02)

## Konteks

Golden test dan audit hari ini menemukan kesalahan "diam-diam": jawaban terdengar yakin dan angkanya lolos pemeriksaan,
tetapi isinya berbeda dari yang ditanya atau disetujui user. Kasus yang terbukti dari log dan pikiran AI:
- **M63:** penjelasan memakai papan Reguler karena AI menebak; batasan jawaban sebelumnya ("papan digabung") dibuang
  dari riwayat.
- **M28 (terulang di g6):** ambang sukses ≥ 3% hanya berupa kalimat; mesin memakai > 0. Jawaban akhirnya benar hanya
  karena AI kebetulan menyadarinya.
- **S27:** label "memenuhi syarat" tertukar; label pembanding "hari-hari lainnya" padahal pembandingnya termasuk hari
  event.
- **S13 / M25:** hasil riset dicap ganda atau hilang dari catatan.
- **C06 (terulang hari ini):** analisis malam memakai data sampai kemarin karena ringkasan cakupan baru diperbarui pagi.
- **D06:** data broker berhenti 31 Agustus.
- **D02:** sektor bernilai "0".

Semua keputusan user hari ini tercatat di `HIGH_ALERT_PLAN.md` dan `UNDERADDRESSED_PLAN_CAT23.md`. Rencana ini
menyatukannya menjadi urutan kerja.

**Aturan kerja:**
- Cabang `claude/g2-g3-reactivation`, deploy ke dev saja. Tidak push `main`.
- **Golden test tidak dijalankan sampai user menyuruh.**
- Satu langkah = tes lokal → commit → deploy satu service sampai SUCCESS → baca log startup.
- Catatan di `ERRORS_AND_SOLUTIONS.md`, `RAILWAY_CHANGELOG.md`, `DATABASE_CHANGELOG.md`, dan README service.
- Tidak mengubah AI_MODEL / AI_MODEL_2 / switch.

## Ringkasan untuk user (bahasa non-dev)

| No | Apa yang dibereskan | Hasil yang terlihat |
|---|---|---|
| 1 | Data & kesegaran (C06, D06, D02) | Analisis malam memakai data hari itu; status SEGAR/TERLAMBAT/BASI per sumber dan peringatan Telegram; sektor "0" menjadi "Undefined" |
| 2 | Hasil riset hilang/ganda (S13, M25) | Rekaman ganda ditolak saat itu juga dengan pesan jelas; semua hasil eksperimen tercatat |
| 3 | Tabel alur (S27) | Jumlah per tahap (memenuhi syarat → dibuang per alasan → dipakai) dibuat sistem; AI tinggal mengutip |
| 4 | Informasi antar giliran (M63, H1) | Riwayat lengkap; setiap tabel hasil membawa definisinya (filter, periode, ambang) dan asal-usulnya; penjelasan wajib membuka tabel asal; klaim "konsisten" dicek mesin |
| 5 | Aturan user mengikat mesin (M28, M29, H2) | Ambang sukses berupa angka resmi dipakai mesin; bisa diubah user ("ubah jadi 5%") dan hasil lama tetap tampil; jumlah di rencana harus bersumber |
| 6 | Prioritas 2 (WAJIB, sesudah 1–5) | Setiap jawaban disertai tabel bukti ringkasan data per klaim |

**Keputusan yang masih terbuka (tidak menahan langkah 1–5):**
- daftar istilah untuk kamus (H3);
- M26 (vonis memperhitungkan efek minimal);
- label "ambang diubah setelah melihat hasil";
- otomatisasi refresh broker (D06);
- A1.4 vs "Undefined": dicatat sebagai pengecualian untuk saat ini.

---

## Langkah 1 — Data & kesegaran (C06, D06, D02)

### 1a. C06: cakupan diperbarui setelah data masuk

- **TEMPORARY:** ganti `cronSchedule` ai-data-coverage menjadi dua kali sehari.
  - Jadwal pagi tetap; satu run lagi setelah muat sore (pemuat selesai ±10:08 UTC), misalnya `"20 0,10 * * *"`.
  - Lewat `.railway/railway.ts` (layanan `ai-data-coverage`), lalu `railway config pull --force` dan
    `railway config plan`.
  - Tidak mencakup run recovery 23:00 UTC; itu ditutup oleh 1a-permanen.
- **Permanen:**
  - `coverage_job.py` mendapat argumen `--datasets` untuk menyegarkan dataset tertentu saja. Fungsi per dataset
    yang sudah ada dipakai ulang (sumber mentah, Feature_01 dari `Feature_Status`).
  - `apps/idx-price-cron/price_update.py`, setelah `run_completed` sukses, memanggil penyegaran untuk
    `Price_Stock_Indonesia_IDX` dan `Feature_01_Stock_Daily`.
  - Feature_01 baru dihitung worker beberapa menit kemudian, jadi penyegaran Feature_01 dijalankan oleh
    feature-01-worker saat antriannya kosong, dengan jeda ≥ 5 menit antar penyegaran.
  - Gagal menyegarkan hanya dicatat (`coverage_refresh_failed`), tidak menggagalkan muat data. Job pagi tetap jadi
    cadangan.
  - Kunci advisory yang sama (`ai_data_coverage_job`) dipakai agar tidak bentrok.

### 1b. C06: rentang "sampai data terbaru"

- **DataNeed:** `end` boleh berisi `"LATEST"`. Di `apps/market-python-sandbox/app/data_need.py` (validasi rentang
  ~1106) nilai itu diganti tanggal referensi (hari ini) saat bind, dan bentuk aslinya dicatat (`end_requested`).
- **Governor tidak berubah.** Profil bundle (`runtime/profiler.py` `_ranges`) sudah menghitung `actual_end`.
  - Untuk rentang LATEST, `PARTIAL_RANGE_COVERAGE` karena "belum ada data sampai hari ini" tidak dihitung sebagai
    kekurangan.
  - Saat implementasi, dicek dulu bahwa ekstraksi Governor tidak menolak akhir rentang di luar cakupan katalog
    (`policy.py` hanya untuk jalur SQL).
- **Jawaban:** tanggal akhir aktual dari `bundles.model_view` (`ranges[].actual_end`) masuk ke definisi hasil
  (langkah 4) dan ke `final_status`.
- **Prompt/deskripsi alat:**
  - "pakai LATEST bila user tidak menyebut tanggal akhir";
  - catatan katalog COVERAGE (`apps/market-ai-orc/app/tools/catalog.py` `_availability`) menambahkan "rangkuman ini
    bisa tertinggal; gunakan LATEST".
- **Tool_Catalog:** deskripsi field `end` berubah → forward migration (lihat "Migrasi").

### 1c. D06: status kesegaran per sumber + Telegram

- **Status diturunkan saat dibaca.** Di catalog COVERAGE (orc `catalog.py`), status dihitung dari
  `AI_table_catalog.freshness_sla` dan tanggal akhir (actual, atau expected untuk turunan) terhadap hari ini:
  SEGAR ≤ SLA, TERLAMBAT ≤ 2×SLA, BASI > 2×SLA.
  - Tanpa SLA → `UNKNOWN`.
  - Untuk Feature_02/03, `pipeline_status = MANUAL_REFRESH_REQUIRED` ikut ditampilkan.
- **Jawaban:** status sumber dimasukkan ke `final_status.warnings` (sandbox `complete`) bila BASI, sehingga jawaban
  menyebutnya.
- **Telegram:**
  - `coverage_job.py` mengirim satu notifikasi per hari per sumber BASI ke `telegram-monitor`.
  - `telegram_monitor.py` menerima `source_table` baru `AI_data_coverage` (saat ini hanya `Monitoring_Price_ALL`,
    baris 25/338), memakai dedupe `Telegram_Notification_Log` yang ada, dan kunci `<dataset>:<tanggal>`.
  - Variabel `TELEGRAM_NOTIFY_URL` / secret untuk ai-data-coverage berupa referensi Railway; hanya nama yang dicatat.

### 1d. D02: "0" → "Undefined"

1. **Preflight (job sementara, read-only):** hitung baris `Sector = '0'` di `IDX_Stock_Universe`,
   `Universe_Equity_Description`, `Feature_01_Stock_Daily.sector` dan `IDX_Stock_Universe_History`. Catat ticker-nya.
2. **Forward migration** `database/migrations/20261003_001_sector_placeholder_undefined.sql`:
   - pola `20260907_001`: BEGIN, guard `DO $check$` jumlah baris, UPDATE `'0'` → `'Undefined'` di universe dan
     description, COMMIT;
   - trigger `reference_history_capture` mencatat perubahan;
   - Feature_01 hanya disentuh bila preflight menemukan nilai di sana; tabel Feature dikunci, jadi pakai jalur ubah
     yang diizinkan atau dicatat sebagai kandidat terpisah.
3. **Metadata:**
   - Column_Catalog `Sector`: arti "Undefined" (keputusan user 2026-10-02);
   - `DATABASE_CHANGELOG.md`;
   - `ERRORS_AND_SOLUTIONS.md` D02 → FIXED;
   - Part A A1.4: catatan pengecualian "Undefined" untuk Sector.
4. **Pencegah:** cek kualitas reusable `scripts/check_placeholder_categories.py` (angka murni di kolom kategori), untuk
   dijalankan sebelum memuat universe. Tidak ada pemuat otomatis di repo, jadi skrip ini masuk prosedur muat manual.

---

## Langkah 2 — Hasil riset hilang/ganda (S13, M25)

### S13: penolakan oleh host

- **Di mana:** `apps/market-python-sandbox/app/sessions.py` `SessionManager.execute`, setelah `_collect` (~843).
- **Cek:** output baru bernama `research_call_<id>` / `research_input_<id>` dibandingkan dengan output dari eksekusi OK
  sebelumnya di epoch yang sama (`store.outputs_for`).
- **Bila sudah ada:**
  - output baru dibuang (file dihapus, masuk `rejected_outputs`);
  - eksekusi dikembalikan dengan pesan `ANGLE_ALREADY_RECORDED` yang menyebut sudut dan output pertama;
  - jalur pengganti eksplisit: `saniti.research_replace(angle_id, …)` mencatat versi lama di lineage dan menggantinya.
- Penanda di memori worker (`_RESEARCH_DONE`) tetap ada sebagai lapis pertama. Keputusan akhir ada di host, yang
  membaca output tersimpan.
- `validate_group` (`research_validation.py` 197–203) tetap jadi penjaga terakhir.

### M25: semua completion tercatat

- `apps/market-ai-orc/app/orchestrator.py` ~3064 menimpa `state.final_status`.
- Ditambahkan `state.final_statuses` (daftar); `analysis_final_status` tetap yang terakhir, demi kompatibilitas.
- Field baru `analysis_final_statuses` (semua) masuk respons API dan audit (`schemas.py:566`, `audit_outbox.py:131`).

---

## Langkah 3 — Tabel alur (S27, H5)

- **Fungsi:** `runtime/event_study.py` mendapat `flow(frame, params)` dari `_masks` (134–161). Isinya per segmen:
  - `condition_true` (memenuhi syarat);
  - `censored`;
  - `overlapping_dropped`;
  - `used`;
  - plus `excluded_before_masks` dari info `build_input` (`censored_outcome_rows`).
- **Rilis:** helper `event_study` (`runtime/saniti_session.py` ~513) merilis `<label>_flow`, dan `call` diberi
  `flow_output`.
- **Validator:** `app/event_study_validation.py` membangun ulang dan membandingkannya seperti `baseline_output`
  (70–73), lalu menambah id-nya ke `verified_output_ids`.
- **Panduan:** `event_study` di `apps/market-ai-orc/app/method_guides.py` menyebut "kutip jumlah dari `_flow`"; bila
  isinya berubah, migrasi buku metode dibuat lewat `generate_ai_method_guide_migration.py`.
- **Tidak dalam langkah ini:** `period_return` (pengecualian hanya warning) dan helper riset; dicatat sebagai lanjutan.

---

## Langkah 4 — Informasi antar giliran (M63, H1)

### a. Riwayat lengkap

- `apps/market-ai-orc/app/conversations.py` `assistant_text` (90–98) menambahkan bagian berlabel "Asumsi:",
  "Batasan:" dan "Metodologi:" (ringkas, dalam batas `MAX_ASSISTANT_TEXT`).
- `trim_history` (`compaction.py:34`) tidak berubah. Definisi hasil (4b) dibawa lewat catatan data, bukan riwayat.

### b. Definisi terstruktur per tabel hasil (DERIVED / DECLARED)

1. **DERIVED, scope permintaan data.**
   - Sandbox `dataneed_service.py` 194–207 menambah `requests[].scope` (bentuk kanonik yang sudah ada, `data_need.py`
     587–600) dan `ranges` ke tampilan approved.
   - Orc `data_record.add_need` (106) menyimpannya.
   - `note()` menampilkannya dalam bentuk terbaca (`Industry EQ Banks`), bukan hanya `scope_sha256`.
2. **DECLARED, filter di kode.**
   - `emit_table` / `emit_json` (`runtime/saniti_session.py` 1496/1544) mendapat
     `definition={"filters": [<PREDICATE scope>], "period": {...}, "entities": ..., "thresholds": {...},
     "notes": str}`.
   - Divalidasi dengan tata bahasa scope DataNeed yang sama (validator dipakai ulang; operator `EQ … IS_NOT_NULL`).
   - **Wajib** untuk TABLE/JSON yang dirilis. `{}` berarti "tidak ada filter tambahan selain permintaan data".
   - Helper bawaan (`event_study`, `event_summary`, `research_*`) mengisinya otomatis dari parameternya.
   - Ditegakkan di sandbox `complete()` (dataneed_service.py 943–948): output tanpa definisi → `INCOMPLETE`, dengan
     `next_action RUN_PYTHON` dan pesan berisi daftar output plus contoh.
   - Output yang dirilis ulang dengan nama sama menggantikan versi lama untuk keperluan cek ini (yang terakhir per
     nama).
3. **Jalur meta** (temuan eksplorasi):
   - `_record(**extra)`;
   - allowlist `meta` di `sessions.py:1032` dan tampilan accepted 1037–1040;
   - `released` di `dataneed_service.py:947`;
   - `resources()` 709–716;
   - manifest `carried.py:185–192`;
   - atribut `load_output` (`saniti_session.py:378`).

   Kolom `outputs.meta` sudah JSON, jadi tidak perlu migrasi.
4. **Orc** `orchestrator.py` ~3262 `add_output` menyimpan `definition` dan `need_id` (dari `state`); `note()`
   menampilkan definisi setiap output.
   - Definisi tidak pernah dipotong selama output masih tercatat.
   - Output lama yang terpotong ditulis "N lainnya tidak ditampilkan".
5. **Tidak ada ruang tersisa:** jika `definition` dikirim melebihi batas ukuran, ditolak di runtime dengan pesan.

### c. Lineage

- Setiap output yang dirilis membawa:
  - `execution_id` (sudah ada di store);
  - `code_sha256` eksekusinya (`dataneed_store.py` 88–103);
  - `need_id` / `bundle_id`.
- Ditampilkan di `released_outputs`, carried manifest dan catatan data.
- Teks kode tetap hanya di audit (`_archive_execution`).

### d. Filter diarahkan ke permintaan data

- Paragraf DATANEED_RULES (`orchestrator.py`) dan buku metode `free_code`: "pasang filter baris (papan, industri,
  ticker) di scope permintaan data; filter di kode wajib dinyatakan di `definition`".
- Ini panduan saja; penegakannya ada di 4b.

### e. INSIGHT wajib membuka tabel asal

- Pra-cek di `orchestrator._execute` dekat 2601: untuk `complete_analysis` bila `state.plan_meta["turn_kind"] ==
  "INSIGHT"`.
- **Lolos** bila run ini memuat output giliran sebelumnya. Sumber buktinya:
  - `load_output(` di kode `run_python` run ini;
  - atau `get_session_output` atas output dari request lain;
  - konfirmasi akhir dari `final_status.carried_inputs` (`dataneed_service.py` 890–899).
- **Bila tidak:** `error_outcome("INSIGHT_SOURCE_NOT_OPENED", …)` lewat `_repair_budget` dengan contoh `load_output`.
- **Larangan menebak:** catatan router INSIGHT (`conversation_router.py:117`) menyebut "definisi hasil sebelumnya ada di
  catatan data; jangan menebak; bila tidak ada, buka tabelnya atau tanya user".

### f. Cek klaim "konsisten"

- Gerbang baru di `_dataneed_gate` setelah `_findings_problems` (~3580), memakai `_gate_once`.
- Dipicu bila teks jawaban memuat klaim konsistensi atau definisi yang sama. Polanya didefinisikan sekali di modul
  baru `app/definition_check.py`, bersama perbandingan definisi.
- Definisi (DERIVED + DECLARED) output yang dirilis run ini dibandingkan dengan definisi output yang dimuat
  (`carried_inputs`).
- Beda atau tidak diketahui → tolak sekali, dengan daftar perbedaannya dan permintaan "sebutkan perbedaan definisinya".

---

## Langkah 5 — Aturan user mengikat mesin (M28, M29, H2)

### a. Ambang sukses berupa angka

- `success_rule: {"operator": ">=" | ">" | "<=" | "<", "value": number} | null` ditambahkan ke:
  - plan v1 `ResearchExperimentFindings` (`apps/market-ai-orc/app/research_plan.py` 145–174);
  - `ResearchGovernanceFindings` (`app/tools/data_need.py` 237–245);
  - pembanding rencana vs submit (`research_plan.py` 505–516);
  - sandbox `research_governance.py` FINDINGS (32, 128–133).
- `success_definition` tetap sebagai teks penjelas.

### b. Mesin membaca angka dari rencana

- Sandbox `dataneed_service.open` (~554) menulis `constraints["findings"]` ke `session.json` (kunci `research_v1`), dan
  runtime `_configure` membacanya.
- `event_summary` (`saniti_session.py` 954): `success_above` default = nilai rencana.
  - Argumen berbeda → `SanitiError` "ambang disetujui = 3; ubah lewat revisi rencana".
  - `research_stats.aggregate` mendukung operator `>=`.
- Ambang yang dipakai dicatat di `research_summary_<id>`.
- `research_findings.evaluate` (44–84) membandingkannya dengan rencana; tidak cocok → INVALID.
- Temuan memuat `success_rule`; data record / jawaban menampilkan "aturan yang dipakai mesin" dari temuan, bukan teks
  AI.

### c. Perubahan oleh user ("ubah jadi 5%")

- Jalur REVISE yang ada (`orchestrator.py` 2163, `conversation_plans.advance`) membuat versi rencana baru dengan
  `success_rule` baru.
  - Angka eksplisit dari user langsung dipakai: catatan REVISE menyuruh AI mengambil angka dari pesan user, dan
    pembanding rencana memastikan angka itu memang ada di pesan user.
  - Permintaan samar → AI mengusulkan angka, user mengonfirmasi.
- Data tidak ditarik ulang: pemakaian ulang bundle per kontrak data yang sama sudah ada.
- Hasil lama tidak ditimpa: `data_record.add_finding` (227) saat ini mengganti id yang sama, jadi id temuan diberi
  akhiran versi rencana (`<hypothesis>@v2`). Jawaban menampilkan keduanya berdampingan.
- Label "ambang diubah setelah melihat hasil": **menunggu keputusan**, tidak dikerjakan.

### d. M29: angka di teks rencana harus bersumber

- Teks rencana (objective, universe, time_scope, assumptions) dicek dengan `provenance.check_answer`.
- Sumbernya: hasil cek kelayakan run ini (`check_data_feasibility` / `check_research_feasibility`) + pesan user.
- Dicek di gerbang rencana yang sudah ada (`_plan_v2_problems` / v1 setara). Angka tanpa sumber → tolak sekali.

### e. Tool_Catalog

- Skema `submit_data_need_spec` berubah → forward migration.
- Generator `scripts/generate_warehouse_summary_tool_migration.py` saat ini memanggil registry tanpa
  `research_findings=True`, sehingga field findings tidak pernah ada di katalog. Dibuat generator baru
  `scripts/generate_research_findings_tool_migration.py` dengan flag itu, plus tes drift seperti
  `tests/test_data_need_tool.py:308`.

---

## Langkah 6 — Prioritas 2 (WAJIB, dikerjakan setelah 1–5)

Bukti agregat per klaim, sesuai `HIGH_ALERT_PLAN.md`:
1. Jawaban akhir membawa `claims: [{ref atau teks angka, recipe: {source_table, scope (PREDICATE), group_by,
   measures (G18), period}}]`.
2. Orc menjalankan setiap recipe lewat Governor ringkasan G18. Batasnya:
   - 10 recipe per jawaban;
   - 200 baris per tabel bukti;
   - 30 detik per query, 120 detik total;
   - batas biaya EXPLAIN yang ada.
3. Hasil dibandingkan dengan toleransi pembulatan provenance:
   - cocok → TERCEK;
   - tidak cocok → satu kali perbaikan, lalu label TIDAK COCOK.
4. Respons API mendapat `evidence[]`; audit ikut menyimpannya.

Rencana teknis rinci langkah 6 ditulis setelah langkah 1–5 selesai. Ada dependensi: G18 fase 2 untuk klaim per periode,
dan S20 untuk rata-rata lintas saham.

---

## Migrasi dan catatan

- **Tool_Catalog** (generator + tes drift):
  - `submit_data_need_spec` (`end: "LATEST"`, `success_rule`);
  - `run_python` (deskripsi `definition`; sekalian menutup drift C08);
  - `check_data_feasibility` bila deskripsi `end` ikut.
- **Data:** D02 (langkah 1d).
- **Tidak ada skema tabel baru:** meta output berupa JSON; freshness memakai `freshness_sla` yang sudah ada.
- **Dokumen:**
  - `ERRORS_AND_SOLUTIONS.md` (status C06, D02, D06, S13, M25, S27, M63, M28, M29 diperbarui di tempat; Part A catatan
    A1.4 dan aturan baru: setiap tabel hasil membawa definisi);
  - `HIGH_ALERT_PLAN.md`, `UNDERADDRESSED_PLAN_CAT23.md`, `OUTSTANDING_ISSUES.md` (status);
  - README tiga service;
  - `RAILWAY_CHANGELOG.md` (deploy, cron, variabel Telegram);
  - `DATABASE_CHANGELOG.md` (migrasi).

## Urutan, deploy, verifikasi

**Urutan:**
1. Langkah 1a-TEMPORARY + 1d (data, tanpa biaya model).
2. Langkah 2.
3. Langkah 3.
4. Langkah 4.
5. Langkah 5.
6. Langkah 1a-permanen, 1b, 1c.

Setiap langkah: deploy sandbox lalu orc (Governor tidak berubah).

Service pemuat, coverage dan telegram ber-source GitHub `main`. Perubahan kodenya (1a-permanen, 1c) hanya bisa live
lewat upload CLI dari cabang atau lewat merge ke `main`. Caranya dicek di PROJECT_CONTEXT saat implementasi dan
ditanyakan ke user sebelum deploy. Perubahan cron 1a-TEMPORARY hanya mengubah konfigurasi.

**Tes lokal per langkah:**
- **Sandbox** (`/opt/venv-sbx`, root):
  - duplikat sudut ditolak host dan `research_replace` berhasil;
  - tabel `_flow` dirilis dan dihitung ulang (mismatch → CALCULATION_MISMATCH);
  - `definition` wajib di complete, diturunkan dari helper, ikut ke carried/`load_output`;
  - `LATEST` dibind ke tanggal referensi, `actual_end` terlapor;
  - `success_rule` dibaca dari session.json, argumen beda ditolak, evaluate menolak ambang tidak cocok.
- **Orc** (`venv-orc` + `ORC_TEST_POSTGRES_URL`):
  - riwayat memuat Asumsi/Batasan/Metodologi;
  - note menampilkan scope terbaca dan definisi;
  - INSIGHT tanpa `load_output` → `INSIGHT_SOURCE_NOT_OPENED`;
  - klaim "konsisten" dengan definisi beda → ditolak; sama → lolos;
  - `final_statuses` menyimpan dua completion;
  - revisi 3% → 5% menyimpan dua temuan;
  - angka rencana tanpa sumber ditolak;
  - tes drift migrasi;
  - status freshness SEGAR/TERLAMBAT/BASI dari SLA.
- **Coverage / telegram:** `test_coverage_job.py` (`--datasets`), tes telegram-monitor sumber baru.

**Verifikasi live tanpa golden test (tanpa biaya model):**
- Setelah muat 17:00 WIB, katalog menunjukkan tanggal hari itu dalam hitungan menit (log ai-data-coverage).
- Query D02 = 0 baris (job sementara read-only, dihapus setelahnya).
- Pesan Telegram BASI untuk Feature_02 sekali sehari.

**Golden test (MENUNGGU perintah user):**
| Pertanyaan | Membuktikan |
|---|---|
| g1 + `g1_foreign_net_banks_repeat` | H3, definisi |
| g3 | tabel alur S27 |
| g5 giliran 3/9 | H1 |
| g6 + giliran "ubah jadi 5%" (runner perlu giliran ketiga) | H2 |
| `g7_followup_definitions` | H1, papan Nego |
| pertanyaan malam hari | C06 |
