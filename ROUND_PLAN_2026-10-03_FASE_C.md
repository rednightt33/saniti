# Rencana Fase C — ruang kerja dilepas, hasil disimpan tahan lama (round 2026-10-03)

## Konteks

Fase A dan B sudah live di dev. Fase C menutup dua masalah yang ditemukan golden test `ma-golden-20261002c`.

- **S28 — ruang kerja tertahan.** Penyebabnya terverifikasi dari kode:
  - sandbox `sessions.py:783-802`: sesi yang sudah selesai (`WARM_IDLE`) menjalankan kode lagi, sehingga `_new_epoch` mengubahnya kembali menjadi `ACTIVE`;
  - orc `_close_sessions` (`orchestrator.py:2126`) melewati sesi yang pernah COMPLETED, jadi sesi itu tidak pernah ditutup;
  - sesi `ACTIVE` tidak pernah digusur. Slot (2) baru bebas setelah 15 menit menganggur, sementara percakapan lain mendapat `SESSION_CAPACITY_EXCEEDED`.
- **R-STORE — hasil hilang setelah 24 jam.**
  - Tabel hasil hanya ada di disk sandbox (24 jam). Barisnya dihapus oleh sweep, lalu `load_output` gagal dengan "not a carried table".
  - Tidak ada jalur dari Postgres kembali ke sandbox.
  - Tidak ada `data_as_of` di orc, sehingga hitung ulang bisa memakai data yang lebih baru tanpa disebut.

Hasil yang diinginkan:
- ruang kerja dilepas di akhir setiap jawaban;
- tabel hasil, kode dan batas tanggal data disimpan selama percakapan hidup;
- percakapan yang aktif lagi memakai tabel dan batas tanggal yang sama, sehingga angkanya sama.

## Keputusan user yang dipakai

| No | Keputusan |
|---|---|
| 2 | File ekspor disimpan di tabel Postgres terpisah (tabelnya dibuat di fase ini, dipakai di Fase D) |
| 3 | Tabel ≤ 50.000 baris / 20 MB disimpan di Postgres; yang lebih besar ke **bucket baru khusus** (jawaban 2026-10-03) |
| 4 | Resume memakai batas tanggal data lama, lalu menawarkan hitung ulang dengan data terbaru |
| 5 | Antrean ruang kerja 60 detik |
| baru | Saat ruang kerja baru dibuka, **semua tabel percakapan** yang sudah kedaluwarsa di sandbox dimuat ulang (maks. 40, sama dengan batas carried sandbox) |

**Koreksi fakta dari survei kode.** Tabel percakapan ada di database Postgres utama (`AI_conversation`, `AI_conversation_turn`, migrasi `20260927_002`) dengan login terpisah `market_ai_conversation`. Database-nya bukan terpisah. Nama tabel baru mengikuti pola itu: `AI_conversation_output`, `AI_conversation_execution`, `AI_conversation_export`.

---

## C1. S28 — ruang kerja dilepas di akhir setiap jawaban (dikerjakan dan di-deploy lebih dulu)

**Penyebab:** sumber daya milik satu jawaban hanya dilepas oleh timeout.
**Kelas masalah:** semua sumber daya yang dipegang sebuah request (sesi analisis, sesi grup riset; nanti antrean dan lock pada banyak user).
**Lapisan perbaikan:** kontrak antar-service sandbox↔orc. Permanen.

### Sandbox (`apps/market-python-sandbox`)

1. **Kontrak baru `POST /v1/requests/{request_id}/release`** (`app/main.py`, `DataNeedService.release`).
   - Berlaku untuk setiap sesi terbuka yang `request_id`-nya request ini (`store.sessions_for`, `dataneed_store.py:304`, saat ini belum dipakai):
     - sesi yang pernah lulus `complete`, workernya hidup, dan reuse menyala → `WARM_IDLE` (bisa dipakai ulang atau digusur);
     - selain itu (termasuk `BUSY` yatim) → `CLOSED` dengan alasan `RELEASED`.
   - Idempoten. Mengembalikan `[{session_id, status}]`. `RELEASED` adalah alasan normal (tidak masuk `ABNORMAL_REASONS`).
2. **Satu sesi aktif per jawaban** (`SessionManager.open`):
   - sebelum cek slot, sesi `ACTIVE` lain milik request yang sama dan sudah complete → `WARM_IDLE`;
   - sesi yang belum complete tidak disentuh, kecuali slot habis: ditutup dengan `REPLACED_IN_REQUEST` (kasus g7: 3 sesi dalam satu jawaban).
3. **Antrean** `PY_SANDBOX_OPEN_WAIT_SECONDS` (bawaan 0 = perilaku sekarang; dev 60, maksimum 120).
   - Bila slot penuh setelah penggusuran, `open` menunggu dengan `threading.Condition`. Tiket FIFO dibangunkan oleh close, release dan sweep, dan setiap putaran mencoba menggusur lagi.
   - Habis waktu → 429 `SESSION_CAPACITY_EXCEEDED` dengan `waited_seconds` dan `retry_after_seconds`.
   - Log `session_open_waited`.
4. **Kapabilitas** `session_release: {version: 1}` dan `open_wait_seconds` di `GET /v1/runtime`.
5. Batas idle 900 detik tetap ada sebagai jaring pengaman. Tes `sweep(now=...)` ditambahkan (belum pernah dites).

### Orc (`apps/market-ai-orc`)

1. Di `AgentOrchestrator.run`, blok `finally` sebelum kunci percakapan direset (`orchestrator.py:1901-1912`):
   - bila sandbox melapor `session_release` v1, panggil `SandboxClient.release(request_id)`;
   - bila tidak, `_close_sessions` / `_close_research_sessions` lama tetap jalan (fail closed);
   - ini mencakup sub-run mode 4 (setiap sub-run punya `request_id` sendiri, `-m4a`…`-m4d`), grup riset, dan run yang gagal di tengah.
2. Timeout HTTP `open_session` dan `_open` milik executor riset (`research_run_executor.py:187`) = `open_wait_seconds` + `PY_SANDBOX_REQUEST_TIMEOUT_SECONDS`.
3. Pesan `SESSION_CAPACITY_EXCEEDED` (`tools/session.py:317`) menyebut bahwa sistem sudah menunggu N detik; `next_action` tetap `REPORT_LIMITATION`; envelope `retryable: false`.

**Tes:**
- skenario g7: complete → execute lagi → release → `WARM_IDLE` → slot bisa digusur;
- dua percakapan paralel dengan 2 slot;
- slot dibebaskan thread lain selama menunggu → open berhasil;
- habis waktu → 429 setelah tunggu (tunggu kecil di tes);
- orc gagal di tengah → release tetap terkirim;
- mode 4: setiap sub-run memanggil release;
- capability tidak ada → fallback lama.

**Tidak tercakup:** dua analisis yang benar-benar paralel tetap butuh dua slot (bagian "100 user" di `FUTURE_PLAN.md` §2).

---

## C2. R-STORE — tabel hasil tahan lama, ruang kerja sementara

**Penyebab:** hasil, kode dan batas tanggal hanya ada di penyimpanan sementara sandbox.
**Kelas masalah:** setiap hasil yang dirujuk lintas giliran (tabel G1–G4, temuan riset, nanti ekspor dan bukti data mentah, data lintas aset dan makro).
**Lapisan perbaikan:** data model (Postgres) dan kontrak service. Permanen. Flag orc `AI_ENABLE_RESULT_STORE` (bawaan mati; butuh `AI_ENABLE_CONVERSATION_STORE` dan kapabilitas sandbox).

### C2a. Migrasi `20261003_006_conversation_results.sql` (Postgres utama, mengikuti pola `20260927_002`)

1. **`AI_conversation_output`:**
   - kolom: `output_id` PK (`^out_[0-9a-f]{24}$`), `conversation_id` FK → `AI_conversation` ON DELETE CASCADE, `request_id`, `session_id`, `execution_id`, `name`, `output_type`, `format` (PARQUET|JSON|TEXT|CSV|PNG), `label`, `definition` jsonb, `units` jsonb, `lineage` jsonb (need_id, bundle_id, code_sha256), **`data_as_of` date**, `row_count`, `columns` jsonb, `byte_count`, `checksum_sha256`, `storage` (POSTGRES|BUCKET), `content` bytea, `object_key`, `created_at`;
   - CHECK: tepat satu dari `content`/`object_key` sesuai `storage`, dan `content` ≤ 20 MB.
2. **`AI_conversation_execution`:** `execution_id` PK, `conversation_id` FK cascade, `request_id`, `session_id`, `code` (≤ 65.536 karakter; lebih panjang → potong + `code_truncated`), `code_sha256` (kode utuh), `modules`, `access` jsonb, `status`, `created_at`.
3. **`AI_conversation_export`:** kolom sesuai keputusan 2 (export_id, conversation_id, request_id, source_ref, format CSV/XLSX/PARQUET, file_name, mime_type, size_bytes ≤ 20 MB, sha256, content bytea, includes jsonb, created_at). Dipakai Fase D.
4. **Lainnya:** indeks `(conversation_id, created_at)`; grant SELECT/INSERT/DELETE untuk `market_ai_conversation_store`; baris `Table_Catalog` dan `Column_Catalog`; blok verify.
5. **Script dan dokumen:**
   - `scripts/provision_market_ai_conversation_login.py`: `TABLES` menjadi 5 tabel, dan tes privilege di `tests/test_conversations.py` ikut diperbarui;
   - `DATABASE_SCHEMA.md` lewat `scripts/sync_database_catalog.py`, lalu `sync_database_schema.py`;
   - `DATABASE_CHANGELOG.md`; `APPLIED.sha256` setelah diterapkan.
6. **Diterapkan** lewat job sementara: DRYRUN → APPLY → baca balik (termasuk login hanya menjangkau 5 tabel) → hapus job.

### C2b. Bucket baru `market-ai-conversation-outputs` (Railway, dev)

- Region `sjc`, privat, dibuat di project `lucid-patience` dev, lalu `railway config pull --force` + `railway config plan`.
- Variabel orc berupa referensi ke bucket (tidak ada nilai yang dicatat): `RESULT_BUCKET_NAME`, `RESULT_BUCKET_ENDPOINT`, `RESULT_BUCKET_REGION`, `RESULT_BUCKET_ACCESS_KEY_ID`, `RESULT_BUCKET_SECRET_ACCESS_KEY`.
- Klien S3 mengikuti `apps/market-audit-store/app/storage.py` (boto3 `1.43.100`, versi yang sama).
- Kunci objek: `outputs/{conversation_id}/{output_id}.{ext}`.
- Penghapusan: `ConversationStore.cleanup` menghapus objek milik percakapan yang dihapus sebelum barisnya dihapus. Upkeep mengecek objek yatim (> 31 hari tanpa baris).
- Dicatat di `RAILWAY_CHANGELOG.md`, `PROJECT_CONTEXT.md` (ID bucket) dan `.railway/railway.ts`.

### C2c. Simpan

**Sandbox:**
- Kontrak baru `GET /v1/sessions/{id}/outputs/{output_id}/file?request_id=`: file mentah streaming dengan header sha256, format dan byte. Aturan akses sama dengan `read_output` (request yang sama, atau kunci percakapan yang sama dan output sudah dirilis).
- `complete()`: `released_outputs[].lineage` mendapat:
  - `data_as_of` = tanggal akhir aktual terbesar dari rentang bundle (`requested_ranges[].actual_end`), diturunkan oleh sandbox;
  - `reference_date`.
- Kapabilitas `output_files: 1`.

**Orc** (`app/result_store.py` baru, metode baru di `ConversationStore`):
- Setelah `complete_analysis` atau complete grup riset lulus (`_track_references`, `orchestrator.py:3377`), setiap output yang dirilis diambil filenya dan disimpan:
  - ≤ 20 MB dan ≤ 50.000 baris → `content` di Postgres;
  - lebih besar → bucket.
  - Penulisan memakai `SET LOCAL statement_timeout '60s'` (bawaan login 5 detik).
  - Batas per percakapan di Postgres 200 MB; kelebihannya ke bucket.
- Setiap `run_python` / `run_research_code` → baris `AI_conversation_execution` (kode, sha, modul, status).
- Gagal simpan tidak menggagalkan jawaban: log `result_store_failed`, dan catatan output mendapat `stored: false`.
- Log ukuran `result_stored` (byte, baris, storage) sebagai bahan ukur.
- Entri output di buku catatan mendapat `data_as_of` dan `stored`.

### C2d. Muat ulang ke ruang kerja baru

**Sandbox:**
- Kontrak baru `POST /v1/sessions/{id}/carried`: metadata JSON + file PARQUET.
  - Checksum diverifikasi.
  - Ditulis sebagai output dirilis dengan `output_id` asli, `origin: RESTORED`, `data_as_of`, definition, units dan label.
  - Muncul di `carried()` lewat `stage_carried` biasa. Sesi riset tetap hanya boleh memuat tabel yang disebut rencana.
- Kapabilitas `carried_restore: 1`.

**Orc:**
- Saat `open_session`, attach, atau open grup riset:
  1. ambil daftar yang masih dipegang sandbox (`GET /v1/conversations/{key}/resources`);
  2. unggah **semua** tabel PARQUET tersimpan milik percakapan yang tidak ada di sandbox (maks. 40, terbaru dulu); untuk sesi riset, hanya `carried_outputs` rencana.
- Batas pengaman per open 500 MB; sisanya dicatat di log dan diberi tahu AI ("tersimpan, belum dimuat").
- Log `carried_restored` (jumlah, byte, ms).
- Data mentah (bundle) lewat 24 jam dibuat ulang lewat DataNeed dengan batas tanggal yang sama (C2e-3).

### C2e. Tiga celah resume

1. **Rencana kedaluwarsa.**
   - Bila user menyetujui rencana yang tiketnya sudah lewat 1 jam (balasan plan atau router APPROVE), backend tidak menolak. Ia menjalankan giliran rencana: "ajukan ulang rencana tersimpan tanpa perubahan". Kelayakan dicek ulang, lalu tiket baru diterbitkan.
   - Jawaban berbunyi "Rencana ini dibuat <tanggal>; setujui ulang?".
   - Tempat: `conversation_plans.continuation_for`, `mode4.routed`/`follow_up`, dan jalur non-mode-4.
2. **Ringkasan setiap jawaban di buku catatan.**
   - `data_record.answers[]` (maks. 30): request_id, turn_index, pertanyaan ≤ 200 karakter, response_type, ringkasan ≤ 300 karakter, ref output, id temuan, `data_as_of`.
   - Aturan prompt: isi giliran yang tidak terlihat di riwayat hanya diketahui dari daftar ini; AI tidak boleh menebak.
3. **Batas tanggal sama.**
   - Orc menurunkan `data_as_of` percakapan dari buku catatan dan mengirim `as_of_date` di body DataNeed, di luar spec (hash spec tidak berubah). Sandbox mengikat `LATEST` ke min(tanggal referensi, `as_of_date`).
   - Data terbaru hanya bila AI mengisi argumen baru `data_as_of_policy: NEWEST` (diambil orc sebelum dikirim, seperti `research_governance`).
   - Backend menambahkan baris otomatis ke jawaban bila `data_as_of` jawaban berbeda dari jawaban sebelumnya ("Data sampai X; jawaban sebelumnya memakai data sampai Y"). Saat batas lama dipakai, jawaban menawarkan hitung ulang dengan data terbaru (keputusan 4).
   - Tool_Catalog: versi baru `submit_data_need_spec` dan `check_data_feasibility` dari generator (pola `scripts/generate_round_b_tool_migration.py`, tes drift registrasi terbaru) dan `AI_TOOLS.md` digenerate ulang.

---

## Urutan kerja dan deploy (dev saja, `main` tidak disentuh)

1. **C1:**
   - tes sandbox dan orc → commit;
   - deploy sandbox → orc sampai `SUCCESS` dan baca log startup;
   - `PY_SANDBOX_OPEN_WAIT_SECONDS=60` di sandbox dev;
   - catat; push.
2. **C2a migrasi:** generator/tes parse → job DRYRUN/APPLY → baca balik → `APPLIED.sha256`.
3. **C2b bucket dan variabel orc:** lalu `config pull`/`plan`.
4. **C2c–C2e:**
   - tes → commit;
   - migrasi Tool_Catalog lewat job;
   - deploy sandbox → orc;
   - `AI_ENABLE_RESULT_STORE=true` di dev;
   - catat; push.
5. **Catatan yang diperbarui:** `ERRORS_AND_SOLUTIONS.md` (S28 dan entri baru bila ditemukan), `RAILWAY_CHANGELOG.md`, `DATABASE_CHANGELOG.md`, `DATABASE_SCHEMA.md`, README sandbox dan orc, `AI_TOOLS.md`, progres di `ROUND_PLAN_2026-10-03.md`, `OUTSTANDING_ISSUES.md`.
6. Golden test hanya atas perintah user. Usulannya: percakapan panjang dengan jeda > 24 jam (disimulasikan dengan memajukan kedaluwarsa), membuka tabel lama, dan angkanya harus sama.

## Risiko dan mitigasi

| Risiko | Mitigasi |
|---|---|
| Antrean membuat jawaban lebih lama | Bawaan 0; dev 60 detik; pesan menyebut lama tunggu |
| Release menutup sesi yang masih dibutuhkan giliran berikutnya | Sesi yang sudah complete menjadi `WARM_IDLE`, bukan ditutup; data tetap di disk; tabel ada di Postgres |
| Postgres membesar | 20 MB per tabel, 200 MB per percakapan, sisanya ke bucket; dihapus bersama percakapan (30 hari) |
| Timeout login 5 detik saat menulis bytea besar | `SET LOCAL statement_timeout` per transaksi tulis |
| Muat semua tabel memperlambat open | Maks. 40 tabel dan 500 MB; log waktu; dievaluasi dari log `carried_restored` |
| Objek bucket yatim | Dihapus sebelum baris percakapan; cek yatim di upkeep |
| Sandbox lama tanpa kapabilitas | Orc fail closed ke perilaku lama |
| AI memakai NEWEST tanpa diminta | Perbedaan tanggal selalu disebut otomatis oleh backend |

## Verifikasi

- Tes lokal:
  - orc (scratch Postgres `ORC_TEST_POSTGRES_URL`): store, privilege 5 tabel, migrasi parse/frozen, release di finally, restore, resume, Tool_Catalog drift;
  - sandbox (`/opt/venv-sbx`, root): release, antrean, sweep, file endpoint, carried restore;
  - kasus selain yang diamati: grup riset, sub-run mode 4, percakapan kedua.
- Live dev:
  - deployment `SUCCESS` dan log startup memuat kapabilitas baru;
  - migrasi dibaca balik;
  - login hanya menjangkau 5 tabel;
  - bucket ada dan privat.
- Golden test hanya atas perintah user.
