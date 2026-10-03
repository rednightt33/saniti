# Rencana round 2026-10-03: anti-menyesatkan, anti-"kejedot", efisien

**Status:** disetujui user (2026-10-03), termasuk keputusan 1–5 di §8. Pengerjaan dimulai dari Fase A.

- **Bukti dan diagnosis:** `GOLDEN_TEST_HIGH_ALERT_2026-10-02.md`, `ERRORS_AND_SOLUTIONS.md` (M68, M69, S28, G19, P26).
- **Rencana sebelumnya:** `HIGH_ALERT_IMPLEMENTATION_PLAN.md` (Langkah 1–7) dan `FUTURE_PLAN.md`.
- **Dokumen ini:** menggabungkan semua item round ini menjadi satu urutan kerja.

---

## 0. Tujuan dan cara mengukurnya

| Tujuan | Artinya | Diukur dengan (golden test sebelum vs sesudah) |
|---|---|---|
| **Tidak menyesatkan** | Setiap angka di jawaban bisa ditelusuri ke data, aturan user dipakai mesin, dan data kosong tidak tampil sebagai "bukti tidak cukup" | Klaim TERCEK / TIDAK COCOK (bukti), temuan dengan `success_rule` dari user, 0 riset jalan di atas data kosong |
| **AI tidak "kejedot"** | AI tidak tersesat oleh catatan bolong, error yang ambigu, jalur panjang untuk pertanyaan sederhana, atau ruang kerja penuh | **Indeks kejedot** per jawaban: panggilan alat yang ditolak + perbaikan gerbang + pesanan data diulang (dari `repair_ledger`, log gerbang, audit) |
| **Efisien** | Lebih sedikit iterasi, token dan waktu; ruang kerja tidak tertahan | Iterasi, token, biaya dan detik per jawaban; jumlah `SESSION_CAPACITY_EXCEEDED` |

**Aturan kerja (tetap):**
- Cabang `claude/g2-g3-reactivation`, deploy ke **dev** saja; `main` tidak disentuh.
- AI_MODEL, AI_MODEL_2 dan switch tidak diubah.
- Golden test hanya atas perintah user.
- Setiap migrasi:
  - forward-only, dibuat generator bila berisi teks;
  - diparse di tes (R27);
  - dijalankan lewat job sementara DRYRUN → APPLY → baca balik;
  - job dihapus setelahnya.
- Deploy dinyatakan berhasil hanya setelah status `SUCCESS` dan log startup dibaca.
- Setiap perubahan dicatat di `ERRORS_AND_SOLUTIONS.md`, `RAILWAY_CHANGELOG.md`, `DATABASE_CHANGELOG.md`, README
  service dan **`AI_TOOLS.md`**.
- Fitur baru di balik flag `AI_ENABLE_*` (bawaan mati). Flag dinyalakan di dev setelah tes lulus, dan dicatat di
  `RAILWAY_CHANGELOG.md`.

---

## 1. Isi round

| Kode | Masalah (non-dev) | Solusi | Lapisan | Fase |
|---|---|---|---|---|
| **M68** | Catatan untuk AI kehilangan nilai saringan ("Industri = ___") | Orc membaca `values`; tes kontrak dengan nota asli sandbox | Kontrak orc ↔ sandbox | A |
| **ENV** | Bentuk hasil dan error tiap alat berbeda, error tanpa petunjuk langkah berikutnya | Envelope standar + `next_action` di setiap error | Batas alat orc | A |
| **TOOLS-DOC** | Daftar alat AI tidak ada di repo | `AI_TOOLS.md` dibuat dari kode + tes drift + aturan di `AGENTS.md` | Dokumentasi/proses | A |
| **G19** (lapis 1, 3) | Riset banding kelompok mendapat data kosong; data kosong lolos | Kunci penggabungan lengkap; gerbang data kosong; audit simpan argumen utuh | Perencana riset orc, sandbox, audit | B |
| **P26** | Satuan angka di rencana bercampur | Angka rencana membawa satuan; dikonversi atau ditolak | Validasi rencana | B |
| **M69** (tahap 1) | Aturan sukses user tidak dipakai di mode 4; horizon bergeser | Mode 4 boleh rencana hipotesis bila ada aturan sukses; horizon user dikunci | Orc (mode 4, gerbang rencana) | B |
| **S28** | Ruang kerja tertahan 15 menit, "penuh" | Lepas di akhir jawaban; 1 ruang aktif per jawaban; antrean | Kontrak orc ↔ sandbox | C |
| **R-STORE** | Tabel hasil hilang setelah 24 jam; angka bisa bergeser saat dihitung ulang | Tabel hasil + kode di penyimpanan tahan lama; batas tanggal data; tiga celah resume | Orc (DB percakapan), sandbox, bucket | C |
| **inspect_dataset** | AI tidak melihat statistik kolom sebelum menghitung | Statistik ringkas per kolom di profil bundle | Sandbox profiler | D |
| **get_artifact** | Script dan artefak lama tidak bisa dibuka AI | Akses artefak (tabel, JSON, script, chart) dari R-STORE | Orc + R-STORE | D |
| **get_lineage** | AI tidak bisa menjawab "angka ini dari mana" | Alat penelusuran jawaban → tabel → kode → bundle → query → tabel sumber | Orc + sandbox | D |
| **export_result** | User tidak bisa mengunduh hasil | Ekspor CSV/XLSX/Parquet ke bucket, tautan unduh berumur pendek | Sandbox + bucket + API orc | D |
| **get_evidence** | Klaim tanpa data pendukung (contoh: 132 hari crash RB) | Tabel bukti per klaim untuk user + cek angka (Prioritas 2, WAJIB) | Orc + Governor + sandbox | D |
| **query_metric** | Pertanyaan sederhana lewat jalur panjang 4–6 langkah | Metrik resmi dihitung langsung di Governor, satu panggilan | Katalog metrik + Governor (G18 fase 2) + orc | D |
| **M69** (tahap 2) | Riset multi-sudut tidak punya ukuran "hit rate" | Hit rate dihitung dan diperiksa ulang mesin | Sandbox metode riset + validator | E |
| **G19** (lapis 2) | 20 kelompok = puluhan pesanan, syarat bisa bertentangan | "Ambil sekali, beri label" + kolom ciri kelompok resmi | Perencana riset + katalog | E |
| **1b, 1c** (dari Langkah 1) | Rentang "sampai data terbaru"; status SEGAR/BASI | `end: "LATEST"`; status kesegaran di katalog (melengkapi describe_data) | Sandbox DataNeed, orc katalog | B |

**Tidak masuk round ini:**
- `FUTURE_PLAN.md` §2 (banyak mesin sandbox untuk 100 pengguna);
- 1a-permanen dan Telegram 1c (service pemuat dan telegram bersumber `main`; perlu keputusan deploy);
- H3 kamus istilah (kecuali definisi metrik untuk query_metric);
- M26.

---

## 2. Peta arsitektur sekarang dan tempat setiap perubahan

```
User ─► market-ai-backend ─► market-ai-orc (orkestrator, alat model, gerbang, DB percakapan Postgres)
                                  │
                                  ├─► market-sql-governor ─► Postgres data pasar (katalog, query aman)
                                  │        └─ dataset Parquet hasil ekstraksi di bucket market-sql-datasets (7 hari)
                                  ├─► market-python-sandbox (bundle di disk /data 24 jam, sesi Python 2 slot,
                                  │        tabel hasil 24 jam, validator independen)
                                  └─► market-audit-store (jejak lengkap, bucket market-ai-audit-artifacts)
```

| Perubahan | orc | sandbox | Governor | DB katalog | DB percakapan | bucket |
|---|---|---|---|---|---|---|
| M68 | ✔ | (tes kontrak memakai kodenya) | | | | |
| ENV | ✔ | | | | | |
| TOOLS-DOC | ✔ (generator, tes) | (dibaca generator) | | | | |
| G19 | ✔ perencana | ✔ gerbang kosong | (sudah menghitung baris) | | | |
| P26 | ✔ rencana | ✔ konversi | | | | |
| M69 | ✔ | ✔ (tahap 2) | | ✔ library riset (tahap 2) | | |
| S28 | ✔ pelepasan | ✔ status sesi, antrean | | | | |
| R-STORE | ✔ | ✔ impor tabel | | | ✔ tabel baru | ✔ tabel besar |
| inspect_dataset | | ✔ profiler | | | | |
| get_artifact / get_lineage | ✔ alat | ✔ endpoint lineage | | | ✔ (R-STORE) | |
| export_result | ✔ alat + API unduh | ✔ penulis file | | | ✔ `conversation_exports` | |
| get_evidence | ✔ alat + gerbang akhir | ✔ (tabel dasar) | ✔ (resep ringkasan) | | ✔ | |
| query_metric | ✔ alat | | ✔ ringkasan antar-waktu | ✔ `AI_metric_catalog` | | |

---

## 3. Fase dan urutan

Urutan ini disusun supaya fondasi yang murah dan paling mengurangi kejedot datang lebih dulu, dan alat baru dibangun
di atas penyimpanan yang sudah tahan lama.

```
A (fondasi: M68, ENV, TOOLS-DOC) ─► B (benar secara data: G19-1/3, P26, M69-1, 1b, 1c)
      ─► C (ruang kerja & penyimpanan: S28, R-STORE) ─► D (alat: inspect, artifact, lineage, export, evidence, metric)
      ─► E (riset lanjutan: M69-2, G19-2) ─► F (golden test + perbandingan)
```

Setiap fase:
1. tes lokal (orc dan sandbox; Governor bila berubah);
2. commit;
3. migrasi (bila ada) lewat job sementara;
4. deploy Governor → sandbox → orc sampai `SUCCESS`, lalu baca log startup;
5. catat perubahan.

---

## 4. Rincian per item

### Fase A — fondasi

#### A1. M68: catatan saringan lengkap (HIGH ALERT)

- **Perubahan:**
  - `apps/market-ai-orc/app/data_record.py` `scope_text` membaca `values` (bentuk baku sandbox). `value` tetap diterima
    untuk catatan lama.
  - Daftar panjang diringkas: "BBCA, BMRI, … (48 nilai)".
- **Tes kontrak** (`apps/market-ai-orc/tests/test_scope_contract.py`):
  - scope dibuat oleh fungsi asli sandbox `app/data_need.py` `canonical_scope` (dimuat seperti generator migrasi
    memuat kode sandbox);
  - kasus: EQ, IN, AND/OR/NOT, nilai angka;
  - semua nilai harus muncul di catatan.
- **Pelajaran** di `ERRORS_AND_SOLUTIONS.md` Part D: kode yang menampilkan keluaran service lain dites dengan keluaran
  asli service itu.
- **Efisiensi:** di g7, AI tidak lagi mengulang pesanan 3× dan membuka 3 sesi (26 iterasi → perkiraan ≤ 12).

#### A2. ENV: envelope standar untuk semua alat

Bentuk yang dilihat model, untuk setiap alat:

```json
{
  "status": "OK | PARTIAL | REJECTED | ERROR",
  "tool": "prepare_data_bundle",
  "data": { "...": "isi khusus alat, tidak berubah" },
  "warnings": [{"code": "FREQUENCY_GAPS", "message": "..."}],
  "errors": [{"code": "SESSION_CAPACITY_EXCEEDED", "message": "...", "retryable": true,
              "next_action": "WAIT_AND_RETRY | FIX_ARGUMENTS | CALL:<tool> | ANSWER_LIMITATION | ASK_USER",
              "details": {}}],
  "meta": {"call_id": "...", "duration_ms": 143, "result_bytes": 5120, "truncated": false,
           "execution_id": "exe_... (bila ada)"}
}
```

- **Di mana:**
  - Hanya di batas registry (`apps/market-ai-orc/app/tools/registry.py`, saat hasil diserialisasi untuk model).
  - `ToolOutcome.output` internal **tidak berubah**, supaya logika orkestrator yang membaca hasil alat tidak rusak.
  - `error_outcome` mengisi `errors[]`.
- **`next_action` wajib untuk setiap kode error:**
  - satu tabel `ERROR_ACTIONS` (kode → next_action, retryable);
  - tes yang memindai semua kode error di `app/` dan sandbox, dan gagal bila ada kode tanpa aksi (derive, don't
    enumerate);
  - kode baru otomatis tertangkap.
- **Error yang sudah punya `next_action`** (sandbox `SessionError`, DataNeed) diteruskan apa adanya.
- **Efisiensi:**
  - Envelope menambah ±40 token per hasil.
  - Hasil yang terpotong ditandai `meta.truncated`, sehingga AI tahu harus membaca halaman berikutnya, bukan menebak.

#### A3. TOOLS-DOC: `AI_TOOLS.md` dari kode + aturan

Sesuai rencana yang sudah disetujui:
- **Generator** `scripts/generate_ai_tools_doc.py`, sumbernya:
  - registry dengan semua flag; flag pengaktif tiap alat diturunkan dengan mematikan satu flag per kali;
  - helper sesi (`HELPERS`, `RESEARCH_HELPERS`);
  - buku metode;
  - ringkasan non-dev per alat di kamus `PLAIN`;
  - `--flags` snapshot dev, hanya nilai `AI_ENABLE_*` true/false.
- **Tes drift** `apps/market-ai-orc/tests/test_ai_tools_doc.py`.
- **Aturan baru di `AGENTS.md`** (Mandatory workflow, butir 5) dan `README.md`: setiap perubahan alat, helper, buku
  metode atau flag pengaktif wajib diikuti regenerasi `AI_TOOLS.md` di task yang sama.
- Setiap alat baru di fase D otomatis masuk dokumen ini.

### Fase B — benar secara data

#### B1. G19 lapis 1 dan 3 (HIGH ALERT)

- **Lapis 1, kunci penggabungan lengkap:** `apps/market-ai-orc/app/tools/research_planner.py` `_key` memasukkan setiap
  sambungan INNER yang menyentuh pesanan (kiri **dan** kanan), beserta kunci pesanan di seberangnya (rekursif, dengan
  penjaga siklus).
  - Tes:
    - BUMN/non-BUMN → pesanan terpisah;
    - 4 dan 20 kelompok → tidak ada pesanan dengan syarat yang saling meniadakan;
    - reproduksi `g19_repro.py` dijadikan tes permanen.
- **Lapis 3, gerbang data kosong:**
  - `check_research_feasibility` dan `check_data_feasibility`: bila Governor menghitung `result_rows: 0`
    (`row_basis COUNTED`) untuk pesanan yang dipakai sudut atau eksperimen, statusnya `REVISION_REQUIRED` dengan
    error `EMPTY_REQUEST` yang menyebut pesanan, tabel dan saringannya. `next_action`: susun ulang saringan, atau
    laporkan "tidak ada transaksi" sebagai temuan bila memang wajar.
  - Sandbox `start_research_run` / `complete`: bundle READY dengan `EMPTY_DATASET` pada pesanan wajib → sudut
    `NOT_RUN` alasan `EMPTY_INPUT`, bukan INSUFFICIENT_EVIDENCE. Jawaban wajib menyebutnya (gerbang temuan).
  - Audit menyimpan argumen alat secara utuh (batas 2.018 karakter dihapus untuk argumen; tetap ada batas ukuran
    total).
- **Efisiensi:** user tidak lagi menyetujui rencana yang pasti kosong. g5 giliran 5–8 menghemat ±10 menit dan dua riset
  sia-sia.

#### B2. P26: satuan angka di rencana

- Ambang di rencana v1 dan v2 (`success_rule`, `min_effect`, ambang metode) menjadi `{value, unit: PERCENT | DECIMAL |
  BASIS_POINT}`.
- Validasi di orc (`research_plan.py`, `research_plan_v2.py`) dan sandbox (`research_governance.py`).
- Konversi ke satuan hasil sebelum `event_summary` / `research_stats` / hitung daya uji. Kalau tidak bisa diselaraskan,
  rencana ditolak dengan pesan berisi angkanya.
- Rencana lama tanpa satuan dianggap memakai satuan hasilnya, dengan peringatan tercatat.
- Tes: 0,03 DECIMAL = 3 PERCENT = 300 BASIS_POINT; kasus g6 menghasilkan rekomendasi sampel ±1.487, bukan 14,8 juta.

#### B3. M69 tahap 1: aturan sukses dan horizon user (HIGH ALERT)

- `apps/market-ai-orc/app/orchestrator.py` `_plan_form_runs` dan gerbang `PLAN_VERSION`: mode 4 boleh mengajukan
  rencana hipotesis (v1) bila rencana memuat `success_rule` yang angkanya ada di pesan user (gerbang
  `PLAN_SUCCESS_RULE` yang sudah ada).
  - Keputusan dibuat backend dari isi rencana.
  - `app/mode4.py` menghitung langkah dan sudut untuk rencana v1.
- **Horizon dikunci:** angka horizon di pesan user wajib sama di semua sudut dan usulan lanjutan. Perubahan harus
  diusulkan eksplisit dan disetujui. Dicek di gerbang rencana dengan pola M29 (angka rencana harus bersumber).

#### B4. 1b dan 1c (dibawa dari Langkah 1)

- **1b:** `end: "LATEST"` di DataNeed. Sandbox bind ke tanggal referensi; `actual_end` masuk definisi hasil.
- **1c:** status kesegaran SEGAR / TERLAMBAT / BASI di bagian COVERAGE `get_catalog_details`, diturunkan dari
  `AI_table_catalog.freshness_sla`. Ini memenuhi kebutuhan "describe_data" untuk freshness tanpa alat baru.
- Telegram dan 1a-permanen tidak termasuk (service bersumber `main`).

### Fase C — ruang kerja dan penyimpanan

#### C1. S28: pelepasan ruang kerja

- **Kontrak baru sandbox** `POST /v1/requests/{request_id}/release`, dipanggil orc di akhir setiap jawaban (juga saat
  gagal, di blok `finally`):
  - sesi dengan completion → `WARM_IDLE` (bisa dipakai ulang percakapan yang sama, atau digusur);
  - sesi tanpa completion → `CLOSED`.
- **Satu sesi aktif per jawaban:** `open` pada request yang sudah punya sesi aktif menjadikan sesi lama `WARM_IDLE`.
- **Eksekusi setelah completion:** sesi tetap `WARM_IDLE` setelah eksekusi selesai, tidak kembali `ACTIVE` permanen.
- **Antrean:** bila slot penuh, `open` menunggu sampai `PY_SANDBOX_OPEN_WAIT_SECONDS` (usulan 60 detik) sebelum
  `SESSION_CAPACITY_EXCEEDED`, dengan `next_action: WAIT_AND_RETRY` dan `retry_after`.
- Batas idle 15 menit tetap ada sebagai jaring pengaman.
- **Tes:** skenario g7 (3 sesi dalam satu jawaban), dua percakapan paralel, orc gagal di tengah jalan.

#### C2. R-STORE: tabel hasil tahan lama, ruang kerja sementara

- **DB percakapan** (Postgres orc), migrasi baru:
  - `conversation_outputs`: output_id, conversation_id, request_id, name, type, definition, lineage, **data_as_of**,
    row_count, columns, format, `content` bytea (Parquet/JSON ≤ 20 MB) **atau** `object_key` di bucket, created_at,
    expires_at = umur percakapan.
  - `conversation_executions`: execution_id, request_id, code (≤ 64 KB), code_sha256, modules, access (pesanan/rentang
    yang dibaca), created_at.
- **Alur simpan:** setelah `complete_analysis` / `complete_research_run` merilis output, orc mengambil isinya dari
  sandbox dan menyimpannya.
  - Tabel di atas batas ukuran (usulan 50.000 baris / 20 MB) disimpan di bucket (prefix `outputs/`); hanya alamatnya
    di Postgres.
- **Alur pakai ulang:**
  - `load_output` / carried tables di sesi baru: bila salinan sandbox sudah kedaluwarsa, orc mengunggah dari R-STORE
    lewat kontrak baru `POST /v1/sessions/{id}/carried`.
  - Data mentah dibuat ulang dari dataset Governor (bucket, 7 hari) atau resep, dengan **batas tanggal data yang
    sama**.
- **Tiga celah resume:**
  - Rencana kedaluwarsa (1 jam) diajukan ulang dari catatan: "rencana ini dibuat kemarin, setujui ulang?".
  - Buku catatan memuat ringkasan setiap jawaban (angka utama + definisi) sehingga giliran lama tetap bisa dirujuk.
    AI dilarang menebak isi giliran yang tidak terlihat.
  - Hitung ulang memakai `data_as_of` yang sama. Data terbaru hanya bila user minta, dan perbedaannya wajib disebut.
- **Migrasi:** forward migration di DB percakapan (bukan DB katalog), grant untuk login `market_ai_conversation`,
  dicatat di `DATABASE_CHANGELOG.md`.

### Fase D — alat untuk AI dan user

Semua alat:
- memakai envelope A2;
- dibuat dari kode;
- didaftarkan di Tool_Catalog lewat generator + tes drift (versi baru, inactive seperti alat orc lain);
- muncul di `AI_TOOLS.md`;
- di balik flag.

Deskripsi alat dibuat pendek; detail dipindah ke buku metode supaya token per panggilan tidak membengkak.

#### D1. inspect_dataset: statistik kolom di profil (memperkuat yang ada)

- Sandbox `runtime/profiler.py` menambah per kolom:
  - jumlah null;
  - min / median / max (angka);
  - jumlah nilai berbeda (dimensi, dibatasi);
  - cakupan tanggal per entitas: jumlah entitas dengan celah.
- Tampil ringkas di hasil `prepare_data_bundle` dan `open_analysis_session` (maks. 30 kolom × 5 angka), lengkap lewat
  `inspect_session` mode `dataset`.
- Tidak ada alat baru dan tidak ada baris data yang dikirim. Contoh 5 baris tetap lewat `inspect_session`.

#### D2. get_artifact (memperkuat `get_session_output`)

- **Request:** `{"ref": "out.o3" | "artifact_id": "...", "include_content": false, "offset": 0, "limit": 200}`.
- **Jenis:**
  - TABLE / JSON: isi berhalaman;
  - SCRIPT: kode eksekusi dari `conversation_executions`, maks. 20 KB bila `include_content`;
  - CHART: metadata + tabel sumbernya;
  - EXPORT: metadata file.
- **Bawaan `delivery: "reference"`:** metadata, ukuran, sha256, lineage singkat. Isi hanya bila diminta, dengan batas
  ukuran.
- Membaca R-STORE, sehingga bekerja juga setelah 24 jam.

#### D3. get_lineage

- **Request:** `{"ref": "out.o3"}`, atau `{"output_id": ...}`, atau `{"execution_id": ...}`.
- **Response `data`** (contoh):
  ```json
  {"output": {"ref": "out.o3", "name": "crash_broker_rank", "definition": {...}, "data_as_of": "2026-10-02"},
   "execution": {"execution_id": "exe_...", "code_sha256": "...", "modules": ["pandas"],
                 "read": [{"request": "broker_flow", "ranges": ["full"]}]},
   "bundle": {"bundle_id": "bundle_...", "need_id": "need_...",
              "requests": [{"logical_name": "broker_flow", "source_table": "IDX_Broker_Summary",
                            "scope": "Industry EQ Banks (via IDX_Stock_Universe)", "rows": 13319,
                            "actual_range": ["2018-01-02", "2026-08-31"]}]},
   "governor": [{"query_id": "qry_...", "query_hash": "...", "rows": 13319}],
   "source_tables": ["IDX_Broker_Summary", "IDX_Stock_Universe", "Feature_01_Stock_Daily"]}
  ```
- **Sumber:** data record (lineage per output), endpoint baru sandbox `GET /v1/outputs/{output_id}/lineage` (bundle
  manifest berisi query Governor; eksekusi berisi modul dan akses), dan R-STORE.
- Tidak ada data baris. Dipakai AI untuk menjawab "angka ini dari mana", dan untuk gerbang klaim "konsisten" (M63).

#### D4. export_result (file di Postgres, keputusan user 2026-10-03)

- **Request:** `{"source": {"ref": "out.o3"} | {"evidence_id": "..."}, "format": "CSV | XLSX | PARQUET",
  "options": {"include_definition": true, "include_lineage": true}}`.
- **Sandbox** menulis file dari output (CSV dan Parquet tanpa dependensi baru; XLSX dengan `openpyxl` baru, ditambah
  lembar "definisi" dan "lineage").
- **Penyimpanan:** tabel terpisah `conversation_exports` di DB percakapan.
  - Kolom: export_id, conversation_id, request_id, source_ref, format, file_name, mime_type, size_bytes, sha256, content
    bytea, includes, created_at, expires_at (umur percakapan, 30 hari).
  - Grant hanya untuk login `market_ai_conversation`.
  - Tidak ada bucket ekspor dan tidak ada URL publik.
- **Batas 20 MB per file.** Lebih besar → `EXPORT_TOO_LARGE`, dengan `next_action`: kurangi kolom atau baris, atau pilih
  Parquet.
- **Unduhan:** API orc `GET /v1/exports/{export_id}/download` (auth sama dengan API, streaming dari Postgres). Respons
  API mendapat `artifacts[]`.
- **Response ke model:** hanya `export_id`, nama, ukuran dan format. File tidak pernah masuk konteks model.
- **Penghapusan:** dihapus bersama percakapan.

#### D5. get_evidence: tabel bukti per klaim (Prioritas 2, WAJIB)

Dua tingkat, sesuai `HIGH_ALERT_PLAN.md` Prioritas 2:
- **Tingkat 1, hitung ulang independen:** klaim yang bisa dinyatakan sebagai ringkasan gudang (tabel, saringan,
  kelompok, SUM/MIN/MAX/COUNT, periode) dihitung ulang Governor (G18) di jalur yang terpisah dari kode AI → **TERCEK**
  atau **TIDAK COCOK**.
- **Tingkat 2, baris dasar:** klaim hasil rumus (contoh: "RB beli bersih 116 dari 132 hari crash") dibuktikan dengan
  tabel baris dasar yang dirilis analisis (contoh: 132 baris hari crash × RB).
  - Backend menghitung ulang angka klaim dari tabel itu (jumlah baris, jumlah net > 0) secara deterministik.
  - Labelnya **TERCEK dari tabel dasar**; asal-usul tabel lewat lineage.
- **Diturunkan otomatis:** setiap referensi nilai (`out.oN…`) di jawaban akhir menunjuk ke output. Gerbang akhir
  menyusun bukti untuk klaim utama (maks. 10 per jawaban) tanpa AI harus memanggil alat.
  - Alat `get_evidence` dipakai AI untuk memeriksa sebelum menjawab.
  - Buku metode mewajibkan analisis merilis tabel baris dasar untuk klaim utama. Helper (event_study, riset) sudah
    merilisnya otomatis.
- **Ke user:** respons API `evidence[]` berisi klaim, status cek, resep, tabel (≤ 200 baris), dan tautan ekspor bila
  lebih.
- **Ke model:** hanya ringkasan dan hasil cek.
- **Batas:**
  - 10 resep per jawaban;
  - 200 baris per tabel tampil;
  - 30 detik per query, 120 detik total;
  - batas biaya EXPLAIN Governor.
- **TIDAK COCOK:** satu kali dikembalikan ke AI dengan selisihnya. Setelah itu ditampilkan apa adanya, tidak
  disembunyikan.

#### D6. query_metric: jalan pintas untuk pertanyaan sederhana

- **Katalog metrik `AI_metric_catalog`** (DB katalog, migrasi + Table/Column_Catalog + grant ke
  `market_ai_catalog_reader`):
  - kolom: metric_id, label, deskripsi, tabel sumber, kolom ukuran, saringan bawaan (contoh: `Investor Type = Foreign`),
    agregasi antar-entitas dan antar-waktu, satuan, dimensi yang boleh, status review;
  - aturan agregasi **diturunkan** dari `AI_column_catalog` (`cross_entity_aggregation`, `resample_aggregation`), tidak
    ditulis ulang;
  - **daftar metrik awal disetujui user.**
- **Governor (G18 fase 2 minimal):** ringkasan antar-waktu dalam jendela N hari bursa per entitas.
  - Hanya ukuran yang boleh: SUM untuk aditif, LAST/FIRST untuk harga, MIN/MAX.
  - Jendela dihitung dari kalender tanggal tabel itu sendiri sampai `as_of`.
  - Statistik cakupan (hari ada / hari jendela) ikut kembali.
- **Request / response:** seperti contoh user (metric, dimensions, filters, periods), ditambah `as_of`, `coverage`,
  `metric_definition_id`, `query_id`.
  - Hasil (≤ 200 baris) langsung ke model.
  - Hasil dicatat di data record sebagai output dengan definisi dan lineage, sehingga **bisa dikutip tanpa sandbox** dan
    lolos gerbang provenance.
- **Efisiensi:** "net asing BBCA 5D dan 20D" dari 4–6 langkah dan 1 sesi Python menjadi 1 panggilan Governor.

### Fase E — riset lanjutan

#### E1. M69 tahap 2: hit rate di riset multi-sudut

- research_plan/v2: `success_rule {operator, value, unit}` di hipotesis akar.
- `conditional_distribution` dan `threshold_sensitivity` menghitung porsi kejadian yang memenuhi aturan dan selisihnya
  terhadap pembanding (interval, p-value).
  - Lokasi: sandbox `app/research_methods.py` dan helper `research_*`.
  - Validator independen `app/research_validation.py` menghitung ulang.
- Temuan membawa `success_rule`. REVISE ("ubah jadi 5%") menyimpan temuan lama `<id>@n`.
- Library riset versi baru (generator migrasi, target beku) dan Tool_Catalog versi baru.

#### E2. G19 lapis 2: ambil sekali, beri label

- Perencana menulis ulang pesanan per kelompok (sumber dan sambungan sama) menjadi satu pesanan untuk gabungannya,
  dengan kolom label kelompok dari tabel daftar saham. Metode riset membagi menurut label.
- Ciri kelompok yang belum menjadi kolom (contoh: BUMN, saat ini tersirat dari nama perusahaan) didaftarkan sebagai
  kolom resmi lewat forward migration + Column_Catalog. **Nama, sumber data dan isinya dikonfirmasi user sebelum
  dimuat** (Part A standar data). Ini sekaligus menutup definisi "bank BUMN" yang berubah-ubah (M66).

### Fase F — verifikasi akhir

Golden test atas perintah user, dibandingkan dengan `ma-golden-20261002c`:

| Item | Membuktikan |
|---|---|
| g1, g1_repeat | M68 (catatan bernilai), ENV, 1c kesegaran |
| g3 | S27 tetap, get_evidence tingkat 2 (tabel alur) |
| g5 (9 giliran) | G19 (data BUMN terisi, sudut BUMN dan non-BUMN berhasil), S28 (tidak ada `SESSION_CAPACITY_EXCEEDED`), get_evidence (132 hari crash RB) |
| g6 + g6_revise (ditulis ulang untuk alur mode 4) | M69 tahap 1–2, P26, horizon terkunci |
| g7 | M68: giliran 2 tidak mengulang pesanan |
| **baru** g8_metric | query_metric: "net beli asing BBCA 5D dan 20D" dalam 1 panggilan |
| **baru** g9_resume | R-STORE: tabel output sandbox dikedaluwarsakan di dev, lalu giliran lanjutan memuat tabel dari Postgres dan angkanya sama |
| **baru** g10_export | export_result XLSX dengan lembar definisi dan lineage |
| **baru** paralel (3 worker) | S28 di bawah beban kecil |

Untuk setiap item dicatat: status, waktu, biaya, iterasi, **indeks kejedot**, dan klaim TERCEK / TIDAK COCOK.

---

## 5. Migrasi dan registrasi

| Migrasi | DB | Isi |
|---|---|---|
| R-STORE + export | Percakapan | `conversation_outputs`, `conversation_executions`, `conversation_exports`, grant |
| query_metric | Katalog | `AI_metric_catalog` + Table/Column_Catalog + grant + metrik awal yang disetujui |
| Tool_Catalog | Katalog | Versi baru: `submit_data_need_spec` (LATEST, satuan), `check_research_feasibility` (satuan, success_rule v2), `get_session_output` → get_artifact; alat baru `get_lineage`, `export_result`, `get_evidence`, `query_metric` (inactive) |
| Library riset | Katalog | Versi baru untuk hit rate (E1) |
| Buku metode | Katalog | Versi baru: pola ambil-sekali-beri-label, wajib tabel dasar untuk klaim, satuan |
| Kolom ciri kelompok | Katalog/data | Setelah keputusan user (E2) |

Semua migrasi dibuat generator bila berisi teks, diparse di tes (R27), dijalankan lewat job sementara DRYRUN → APPLY,
dan dibaca balik.

## 6. Flag baru (bawaan mati; dinyalakan di dev setelah tes)

| Flag | Fitur |
|---|---|
| `AI_ENABLE_TOOL_ENVELOPE` | ENV |
| `AI_ENABLE_RESULT_STORE` | R-STORE, get_artifact (script), resume |
| `AI_ENABLE_LINEAGE_TOOL` | get_lineage |
| `AI_ENABLE_EXPORT` | export_result |
| `AI_ENABLE_EVIDENCE` | get_evidence + `evidence[]` |
| `AI_ENABLE_QUERY_METRIC` | query_metric |
| `PY_SANDBOX_OPEN_WAIT_SECONDS` | Antrean slot (S28) |

## 7. Risiko utama dan mitigasi

| Risiko | Mitigasi |
|---|---|
| Alat bertambah → token definisi per panggilan naik (±2–3 ribu) | Deskripsi pendek, detail di buku metode; alat hanya terdaftar bila flag dan prasyarat aktif; input ter-cache murah |
| Envelope merusak logika orkestrator | Envelope hanya di serialisasi ke model; `ToolOutcome.output` internal tidak berubah; seluruh tes orc |
| R-STORE menambah beban DB percakapan | Batas ukuran per tabel; tabel besar ke bucket; hapus bersama percakapan |
| Evidence memperlambat jawaban | Batas 10 resep / 120 detik; tingkat 2 tanpa query baru |
| query_metric dipakai untuk pertanyaan yang butuh analisis | Hanya metrik di katalog; di luar itu `next_action: CALL:submit_data_need_spec` |
| Gerbang data kosong menolak kasus wajar | Hanya pesanan wajib; pesan mengarahkan ke temuan "tidak ada transaksi" |
| DB percakapan membesar karena file ekspor | Batas 20 MB per file, retensi 30 hari, ukuran total dicatat di log |
| Perubahan besar sekaligus | Fase berurutan, flag per fitur, rollback ke deployment sebelumnya per service |

## 8. Keputusan user (2026-10-03)

| No | Keputusan | Status |
|---|---|---|
| 1 | Metrik awal query_metric: net beli asing (per saham/papan), net beli per broker, nilai transaksi, volume, harga penutupan terakhir, harga tertinggi/terendah dalam periode | **Diputuskan: OK** |
| 2 | Tempat file export | **Diputuskan: tabel Postgres terpisah** (`conversation_exports`, D4) |
| 3 | Batas tabel hasil di Postgres 50.000 baris / 20 MB; lebih besar ke bucket | **Diputuskan: OK.** Bucketnya (prefix di bucket yang ada atau bucket baru) ditentukan saat Fase C dan dicatat di `RAILWAY_CHANGELOG.md` |
| 4 | Resume: batas tanggal data lama + tawaran hitung ulang dengan data terbaru | **Diputuskan: OK** |
| 5 | Antrean ruang kerja 60 detik | **Diputuskan: OK** (`PY_SANDBOX_OPEN_WAIT_SECONDS=60`) |
| 6 | Sumber dan nama kolom ciri kelompok (contoh `is_state_owned` untuk BUMN) | **Terbuka**: ditanyakan sebelum E2 |

## 9. Perkiraan urutan kerja

| Fase | Isi | Deploy |
|---|---|---|
| A | M68, ENV, TOOLS-DOC | orc |
| B | G19-1/3, P26, M69-1, 1b, 1c | orc, sandbox (+ Tool_Catalog) |
| C | S28, R-STORE | sandbox, orc (+ migrasi DB percakapan) |
| D | inspect, artifact, lineage, export, evidence, metric | Governor (fase 2), sandbox, orc (+ migrasi katalog, bucket) |
| E | M69-2, G19-2 | sandbox, orc (+ library riset, kolom kelompok) |
| F | Golden test + perbandingan | runner |

Setiap fase bisa berhenti di tengah tanpa merusak fase sebelumnya, karena fitur ada di balik flag dan deploy
dilakukan per service.
