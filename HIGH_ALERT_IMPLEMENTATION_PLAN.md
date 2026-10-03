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

## Progres (dihentikan karena mode rencana diaktifkan lagi oleh user)

- **Sudah:**
  - rencana disimpan di repo (`HIGH_ALERT_IMPLEMENTATION_PLAN.md`, commit `c5a04cf`);
  - 1a-TEMPORARY sudah live: cron ai-data-coverage diubah menjadi `30 0,10 * * *` lewat pinned plan
    (`railway config apply --plan`, 1 perubahan, aman). Deploy `c3144f5b` SUCCESS. `railway config pull --force` dan
    `railway config plan` menunjukkan tidak ada drift;
  - preflight D02 lewat job read-only sementara `d02-check-job` (deployment `e8afdd3f`), sudah dihapus.
- **Belum di-commit:** `.railway/railway.ts` (baris cron). Entri `RAILWAY_CHANGELOG.md` untuk cron dan job sementara
  belum ditulis. Keduanya jadi pekerjaan pertama setelah rencana disetujui lagi.
- **Hasil preflight D02:** nilai `0` ada di **Sector dan Industry** untuk 3 ticker yang sama (XCID, XCIS, XSPI):

  | Tabel | Baris berisi `0` |
  |---|---|
  | `IDX_Stock_Universe` | 3 |
  | `Universe_Equity_Description` | 3 |
  | `IDX_Stock_Universe_History` | 3 (riwayat, tidak diubah) |
  | `Feature_01_Stock_Daily` (`sector`, `industry`) | 3.365 |

- **Keputusan user (jawaban AskUserQuestion):** "Sector + Industry, semua". Langkah 1d diperluas, lihat bawah.

### Status per 2026-10-02 malam (dev, cabang `claude/g2-g3-reactivation`)

| Langkah | Status | Bukti |
|---|---|---|
| 1a-TEMPORARY (cron dua kali sehari) | LIVE | `c3144f5b` SUCCESS; `RAILWAY_CHANGELOG.md` |
| 1d (D02 → "Undefined") | LIVE | migrasi `20261003_001` diterapkan dan dibaca balik; `DATABASE_CHANGELOG.md` |
| 2 (S13, M25) | LIVE | sandbox `c7ff6e1c`, orc `90ac9f64` |
| 3 (S27 tabel alur) | LIVE | sandbox `c7ff6e1c` |
| 4 (M63, H1) | LIVE | sandbox `b1983cf7`, orc `b3aaae90` |
| 5 (M28, M29, H2) | LIVE | sandbox `b1983cf7`, orc `b3aaae90`; migrasi `20261003_002` (buku metode v2) dan `20261003_003` (Tool_Catalog) diterapkan |
| 1a-permanen, 1b, 1c | BELUM | layanan pemuat/coverage/telegram bersumber `main`: tanya user sebelum deploy |
| 6 (Prioritas 2, WAJIB) | BELUM | rencana teknis ditulis setelah 1a/1b/1c |
| Golden test | TIDAK DIJALANKAN | menunggu perintah user |

Kejadian: uji coba pertama migrasi `20261003_003` gagal (R27, tanda kutip tidak di-escape; tidak ada data berubah).
Diperbaiki di semua generator, dan sekarang setiap migrasi diparse PostgreSQL di tes sebelum dikirim.

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

1. **Preflight:** SELESAI (lihat "Progres").
2. **Forward migration** `database/migrations/20261003_001_classification_placeholder_undefined.sql`:
   - Pola `20260907_001`: BEGIN; guard `DO $check$` memastikan jumlah baris tepat sama dengan preflight (3 / 3 / 3.365,
     ticker XCID/XCIS/XSPI); UPDATE `'0'` → `'Undefined'` untuk `Sector` dan `Industry` di `IDX_Stock_Universe` dan
     `Universe_Equity_Description`, serta `sector` dan `industry` di `Feature_01_Stock_Daily`; COMMIT.
   - `IDX_Stock_Universe_History` tidak diubah: trigger `reference_history_capture` menambah versi baru, dan versi lama
     `0` tetap sebagai riwayat.
   - **Sebelum menulis migrasi, dicek read-only:**
     - trigger atau aturan di `Feature_01_Stock_Daily` yang bisa menolak UPDATE langsung (migrasi `20260912_001`
       memakai advisory lock refresh);
     - apakah UPDATE universe memicu antrean hitung ulang Feature 01 (trigger antrean di `Feature_Calculation_Queue`).

     Bila hitung ulang otomatis sudah menangani Feature_01, UPDATE langsung di Feature_01 tidak dilakukan; hitung ulang
     dibiarkan berjalan lalu hasilnya diverifikasi.
   - Dijalankan lewat job sementara: DRYRUN dulu (rollback), lalu APPLY, dibaca balik, dan job dihapus. Pola sama
     dengan `wa-explain-job`.
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

## Langkah 7 — Perbaikan dari golden test `ma-golden-20261002c` (round ini; BELUM dijalankan, user masih menyeleksi solusi)

Bukti dan diagnosis: `GOLDEN_TEST_HIGH_ALERT_2026-10-02.md` dan `ERRORS_AND_SOLUTIONS.md`. **Rencana round lengkap (urutan, alat baru, migrasi, flag, golden test): `ROUND_PLAN_2026-10-03.md`.** Isi round ini:

| Kode | Status di plan | Rincian |
|---|---|---|
| M68 | Disetujui masuk plan | `FUTURE_PLAN.md` §1 (orc membaca `values`; tes kontrak dengan `canonical_scope` asli sandbox) |
| S28 + R-STORE | Disetujui masuk plan round ini | `FUTURE_PLAN.md` §1 (lepas ruang kerja di akhir jawaban, tabel hasil di Postgres) |
| **M69** | Disetujui, kedua tahap (2026-10-03) | 7a di bawah |
| **P26** | Disetujui (2026-10-03) | 7b di bawah |
| **G19** | Disetujui, tiga lapis (2026-10-03) | 7c di bawah |

### 7a. M69 — aturan sukses user mengikat semua jalur riset (HIGH ALERT H2)

**Akar masalah (terverifikasi):**
- Mode 4 hanya mengajukan rencana multi-sudut. `orchestrator._plan_form_runs`: "a plan it presents is multi-angle"; rencana
  hipotesis v1 ditolak dengan gerbang `PLAN_VERSION`.
- Metode multi-sudut (`research_library.py`: conditional_distribution, threshold_sensitivity, …) hanya mengukur rata-rata
  dan arah; tidak ada aturan sukses.
- Pikiran AI di g6_revise: *"The library can't test the +3% threshold directly… hypothesis plan (v1) has success_rule…
  exactly designed for this user's criterion"*.
- Ikut terlihat: horizon dari user (10 hari) bergeser diam-diam ke 5 hari pada usulan lanjutan.

**Kelas masalah:** parameter yang dinyatakan user (ambang sukses, horizon, efek minimal) diikat ke satu jalur saja.
Jalur lain (multi-sudut, mode 4, usulan lanjutan) bisa mengabaikannya.

**Tahap 1 — pilihan jalur oleh sistem (cepat, permanen):**
- Bila pesan user memuat aturan sukses yang eksplisit, mode 4 boleh mengajukan rencana hipotesis (v1, `success_rule`)
  di tempat rencana multi-sudut.
  - Syaratnya diturunkan dari isi rencana: rencana v1 dengan `success_rule` yang angkanya ada di pesan user, dicek oleh
    gerbang `PLAN_SUCCESS_RULE` yang sudah ada. Keputusan tidak diserahkan ke AI.
- Yang diubah:
  - `_plan_form_runs` / gerbang `PLAN_VERSION` di `apps/market-ai-orc/app/orchestrator.py`;
  - langkah dan hitungan sudut mode 4 (`app/mode4.py`, yang sudah meneruskan rencana v1 ke jalurnya);
  - `PLAN_VERSION_INSTRUCTION`.

**Tahap 2 — ukuran "hit rate" di riset multi-sudut (lengkap, permanen):**
- Rencana multi-sudut (research_plan/v2) mendapat `success_rule {operator, value, unit}` di tingkat hipotesis akar.
- Metode conditional_distribution dan threshold_sensitivity menghitung, di samping rata-rata, porsi kejadian yang
  memenuhi aturan (hit rate) dan selisihnya terhadap pembanding, beserta interval dan p-value.
  - Lokasi: sandbox `app/research_methods.py`, helper `research_*` di `runtime/saniti_session.py`.
- Validator independen (`app/research_validation.py`) menghitung ulang hit rate; selisih → INVALID.
- `research_findings` membawa `success_rule` per sudut; gerbang orc memastikan angkanya sama dengan pesan user, dan
  perubahan ("ubah jadi 5%") lewat REVISE menyimpan temuan lama (`<id>@n`), seperti v1.
- **Horizon:** angka horizon yang disebut user wajib dipakai semua sudut, termasuk usulan lanjutan. Perubahan horizon
  harus diusulkan eksplisit ("horizon 5 hari, bukan 10, karena …") dan disetujui user; dicek gerbang rencana dari pesan
  user (pola M29).
- **Metadata:**
  - library riset versi baru: migrasi generator `scripts/generate_ai_research_library_migration.py` (pola target beku);
  - Tool_Catalog `check_research_feasibility` dan `submit_data_need_spec` versi baru (generator + tes drift);
  - buku metode `multi_angle`;
  - `AI_TOOLS.md` (aturan baru).

**Benchmark:**
- pre-registration (kriteria sukses dicatat sebelum uji dan wajib dipakai semua analisis);
- hit rate sebagai ukuran standar backtest di samping rata-rata return.

**Risiko dan mitigasi:**
- *Mode 4 punya dua bentuk rencana.* Aturan pemilihan satu tempat di backend, dites dengan beberapa pertanyaan.
- *Uji statistik hit rate salah.* Dihitung ulang validator independen, dengan tes yang membandingkan hitungan manual.
- *Horizon dikunci mengurangi kebebasan AI.* Usulan horizon lain tetap boleh, asal eksplisit dan disetujui.

**Cakupan:**
- Tertutup: (a) "naik ≥ 5% dalam 20 hari" di mode 4; (b) "turun > 2% setelah sinyal jual"; (c) usulan lanjutan yang
  mengganti horizon.
- Tidak tertutup: aturan non-angka ("lebih baik dari IHSG"), yang ditangani lewat baseline.

**Verifikasi:**
- tes orc dan sandbox;
- golden test g6_revise yang ditulis ulang untuk alur mode 4: aturan ≥ 3% dan ≥ 5% dihitung dan diperiksa mesin,
  temuan lama tersimpan, horizon tetap 10 hari kecuali disetujui.

### 7b. P26 — angka di rencana membawa satuannya

**Akar masalah (terverifikasi):**
- Pikiran AI g6: *"success_rule 0.03? Hmm… if outcome_unit is PERCENT, the value should be 3. Ambiguity."*
- Rencana tercatat `outcome_unit DECIMAL`, `min_effect 0.01`, `success_rule 3.0`.
- Backend membandingkan 0,01 dengan MDE dalam persen (2,82), sehingga menyarankan 14.868.205 sampel.

**Kelas masalah:** angka tanpa satuan yang berpindah antar-bagian sistem. Ini berlaku untuk ambang sukses, efek minimal,
return, dan nanti suku bunga atau inflasi (persen vs basis poin) di data makro.

**Perbaikan (permanen, validasi rencana di backend):**
- Setiap ambang di rencana (v1 dan v2) menyimpan satuannya: `{value, unit: PERCENT | DECIMAL | BASIS_POINT}`.
- Backend mengonversi ke satuan hasil sebelum menghitung (`event_summary`, `research_stats`, perhitungan daya uji), atau
  menolak rencana yang satuannya tidak bisa diselaraskan, dengan pesan yang menyebut angkanya.
- Rencana lama tanpa satuan dianggap memakai satuan hasilnya, dengan peringatan tercatat.

**Benchmark:** angka bersatuan ala Pint dan UCUM; kegagalan klasik Mars Climate Orbiter (1999).

**Perbandingan:** versi ringan Pint (hanya angka di rencana). Alternatif "selalu persen" gagal untuk basis poin.

**Risiko dan mitigasi:**
- *Rencana lama menjadi tidak sah.* Bawaan = satuan hasil, plus peringatan.

**Cakupan:**
- Tertutup: (a) ambang ≥ 3% ditulis dalam desimal; (b) efek minimal dalam basis poin untuk suku bunga.
- Tidak tertutup: satuan uang (Rp vs USD), yang menjadi urusan katalog kolom.

**Verifikasi:** tes konversi (0,03 DECIMAL = 3 PERCENT = 300 BASIS_POINT); rencana g6 dengan satuan bercampur
menghasilkan rekomendasi sampel yang wajar (±1.487, seperti run sebelumnya).

### 7c. G19 — riset perbandingan kelompok mendapat data kosong (HIGH ALERT)

**Akar masalah (terverifikasi 2026-10-03):**
- Perencana riset multi-sudut menggabungkan pesanan data yang "sama" dari beberapa sudut
  (`apps/market-ai-orc/app/tools/research_planner.py` `_key`/`_merge`/`_group_spec`).
- Kunci "sama" hanya memasukkan sambungan INNER di mana pesanan berada di sisi kiri. Pesanan transaksi broker dan harga
  berada di sisi kanan sambungan ke daftar saham (relasi 17 dan 2).
- Akibatnya, pesanan sudut BUMN dan non-BUMN digabung menjadi satu dan membawa kedua syarat sekaligus. Governor
  menggabungkan syarat dengan AND (`compile_extraction`), jadi hasilnya 0 baris.
- Bukti:
  - reproduksi lokal dengan kode perencana;
  - log Governor (`mar6249eb4d_g1_A`/`_C`, `mard9a11af6_g1_A`/`_C` = 0; daftar saham 4/46/42 ada isinya);
  - pikiran AI giliran 7 ("it might fail again").
- Cek kelayakan sudah menghitung 0 baris, tetapi tetap menjawab FEASIBLE; bundle tetap READY / coverage PASS.

**Kelas masalah:**
- Kunci penggabungan yang melewatkan parameter yang mengubah isi data. Ini berlaku untuk setiap riset yang
  membandingkan kelompok lewat tabel yang disambung: BUMN vs non-BUMN, sektor, ukuran, papan/investor, dan negara di
  data makro.
- Risikonya naik seiring jumlah kelompok (4, 20 kriteria).

**Perbaikan (tiga lapis, semuanya permanen):**
1. **Kunci penggabungan lengkap.**
   - `_key` memasukkan setiap sambungan INNER yang menyentuh pesanan, di sisi kiri maupun kanan, beserta kunci
     pesanan di seberangnya (rekursif, dengan penjaga siklus).
   - Pesanan hanya digabung bila semua syarat yang mengubah barisnya identik.
   - Tes: dua sudut BUMN/non-BUMN menghasilkan pesanan terpisah; 20 kelompok tidak pernah menghasilkan syarat yang
     saling bertentangan.
2. **Pola "ambil sekali, beri label" untuk perbandingan kelompok.**
   - Kelompok yang berbeda di atas tabel yang sama dilayani oleh satu pesanan untuk gabungannya (misalnya semua
     bank).
   - Ciri kelompok dibawa sebagai kolom label dari daftar saham, lalu mesin riset membagi data menurut label
     (cohort/regime comparison sudah bekerja dengan label).
   - Hasilnya, jumlah pesanan tetap (±3) untuk 2 maupun 20 kelompok.
   - Perencana menulis ulang pesanan per kelompok menjadi pola ini bila sumber dan sambungannya sama. Buku panduan
     metode `multi_angle` dan pesan kelayakan mengarahkan AI ke pola ini.
   - Ciri kelompok yang belum menjadi kolom (contoh: BUMN, kini tersirat dari nama perusahaan) didaftarkan di katalog
     sebagai kolom resmi, misalnya `is_state_owned`, lewat forward migration + Column_Catalog. Keputusan nama dan
     sumber kolom dikonfirmasi ke user sebelum memuat data. Ini sekaligus menutup definisi "bank BUMN" yang
     berubah-ubah (M66).
3. **Pengaman data kosong.**
   - Cek kelayakan menolak rencana bila Governor menghitung 0 baris untuk pesanan yang wajib dipakai sudut, dengan
     pesan yang menyebut pesanannya.
   - Bundle yang tetap kosong menghentikan riset sebelum sudut dijalankan, dengan status `EMPTY_INPUT`, bukan
     INSUFFICIENT_EVIDENCE.
   - Data yang memang wajar kosong ("broker X tidak pernah beli saham Y") dilaporkan sebagai temuan, bukan ditolak
     diam-diam.
   - Audit menyimpan argumen alat secara utuh (sekarang terpotong 2.018 karakter), supaya penyebab kosong di masa depan
     bisa dibaca balik.

**Benchmark:**
- Kunci cache/deduplikasi harus mencakup semua parameter yang mengubah hasil (cache query BI, dedup pipeline data).
- `GROUP BY` / `groupby` dan panel berlabel di riset kuant untuk perbandingan kelompok.
- Gerbang "row count > 0" ala Great Expectations / dbt tests.

**Risiko dan mitigasi:**
- *Pesanan gabungan lebih besar.* Batas ukuran tetap berlaku; dipecah per tanggal, bukan per kelompok.
- *Ciri kelompok belum ada sebagai kolom.* Didaftarkan di katalog lewat migrasi, dikonfirmasi user.
- *Pengaman kosong menolak kasus yang wajar.* Hanya berlaku untuk pesanan wajib, dan pesannya mengarahkan ke temuan
  "tidak ada transaksi".

**Cakupan:**
- Tertutup: (a) BUMN vs non-BUMN; (b) 4 sektor sekaligus; (c) kode broker salah tulis (lapis 3).
- Tidak tertutup: data yang tidak kosong tetapi terlalu sedikit, yang ditangani aturan ukuran sampel yang ada.

**Verifikasi:**
- Tes perencana: 2, 4 dan 20 kelompok. Jumlah baris per kelompok sama dengan baris gabungan, dan tidak ada kelompok yang
  kosong tanpa alasan.
- Golden test g5 giliran 5–8: data RB dan harga terisi, sudut BUMN dan non-BUMN mendapat hasil.

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
