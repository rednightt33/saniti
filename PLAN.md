# Rencana induk: sudah disetujui user, belum dieksekusi

Dokumen ini memuat pekerjaan yang sudah disetujui user tetapi belum punya rencana eksekusi (keputusan user 2026-10-06:
"tidak ada format plan PLAN_YYYY-MM-DD, semua plan harus jadi 1 kecuali future plan"). Eksekusi yang sudah disetujui
ada di `EXEC.md`, satu bagian per eksekusi (keputusan user 2026-10-06: "EXEC itu harusnya jadi 1 file").

Aturan:
- **Isi dokumen ini:** pekerjaan yang sudah disetujui user tetapi belum punya rencana eksekusi. Begitu rencana
  eksekusinya disetujui, butirnya pindah ke `EXEC.md`.
- **Usulan dan keputusan yang masih terbuka** ada di `FUTURE_PLAN.md`.
- **Setiap butir tetap dijalankan hanya atas perintah user.** Persetujuan masuk rencana bukan perintah eksekusi.
- **Persetujuan dicatat di sini pada tugas yang sama**, beserta tanggal dan kata-kata user, termasuk persetujuan
  "secara umum" (pelajaran R34 di `ERRORS_AND_SOLUTIONS.md`). Detail yang masih terbuka ditulis sebagai pertanyaan di
  butirnya.
- **Butir yang selesai** dipindah keluar: statusnya ke `ERRORS_AND_SOLUTIONS.md` / changelog, lalu baris di sini
  dihapus.
- **Dokumen rencana bertanggal yang lama** (`PLAN_2026-10-05.md`, `PLAN_*_2026-10-04.md`, `ROUND_PLAN_2026-10-03*.md`,
  dan `*_PLAN.md` lain) adalah riwayat diskusi. Butir yang belum selesai dari dokumen itu sudah dipindah ke sini atau
  ke `FUTURE_PLAN.md` (audit 2026-10-06, bagian akhir).

Kode masalah (M, P, S, G, W, R, C, D) merujuk ke `ERRORS_AND_SOLUTIONS.md`.

## Ringkasan

| No | Butir | Disetujui | Status | Urutan usulan |
|---|---|---|---|---|
| 8 | Round 2026-10-03 Fase E: E1 hit rate (M69 tahap 2), E2 ambil sekali beri label (G19 lapis 2) | 2026-10-03 (round disetujui) | Belum; E2 menunggu keputusan 6 | 8 |
| 9 | C06 1a-permanen dan D06 peringatan Telegram | 2026-10-02 | Belum (sisanya sudah live) | 9 |
| 10 | G2-B, S20, minimal 4 hipotesis, analisis faktor | 2026-10-02 (`G2_G3_REACTIVATION_PLAN.md` langkah 8, FINAL) | Belum; 4 keputusan rinci masih terbuka | 10 |
| 11 | P9 kamus nilai dan alat "cari nilai" | Keputusan desain user 2026-10-01 | Belum; perlu cek ulang cakupan | 11 |
| 12 | Prosedur tabel baru (FX, indeks, makro) | 2026-10-01 "record now, run later" | Menunggu pemicu: tabel baru | Saat ada tabel baru |

Eksekusi yang sudah disetujui (dulu butir 1–7 dan 1b–1k) ada di `EXEC.md`.

---

## 8. Round 2026-10-03 Fase E

**Asal:** `ROUND_PLAN_2026-10-03.md` §1, §4 Fase E, §9 (round disetujui 2026-10-03). Fase A–D sudah live; Fase E
belum dikerjakan.

- **E1. M69 tahap 2: hit rate di riset multi-sudut.**
  - research_plan/v2 memuat `success_rule {operator, value, unit}` di hipotesis akar.
  - `conditional_distribution` dan `threshold_sensitivity` menghitung porsi kejadian yang memenuhi aturan dan
    selisihnya terhadap pembanding (interval, p-value). Validator `research_validation.py` menghitung ulang.
  - REVISE menyimpan temuan lama `<id>@n`.
  - Library riset dan Tool_Catalog versi baru.

  Status M69: tahap 1 live; tahap 2 belum.
- **E2. G19 lapis 2: ambil sekali, beri label.**
  - Perencana menggabung pesanan per kelompok menjadi satu pesanan dengan kolom label kelompok.
  - Ciri kelompok yang belum menjadi kolom (contoh BUMN) didaftarkan lewat forward migration + Column_Catalog.
  - **Menunggu keputusan 6** (`FUTURE_PLAN.md` §3): nama, sumber data dan isi kolom ciri kelompok dikonfirmasi user
    sebelum dimuat (Part A).

## 9. C06 1a-permanen dan D06 peringatan Telegram

**Asal:** `UNDERADDRESSED_PLAN_CAT23.md` §7 butir 1 dan 3 (disetujui 2026-10-02); rincian di
`HIGH_ALERT_IMPLEMENTATION_PLAN.md` Langkah 1a dan 1c. Bagian 1a-TEMPORARY, 1b (rentang "LATEST") dan status
kesegaran sudah live.

- **1a-permanen:**
  - `coverage_job.py --datasets` dibuat;
  - `apps/idx-price-cron/price_update.py` menyegarkan cakupan `Price_Stock_Indonesia_IDX` setelah muat sukses;
  - feature-01-worker menyegarkan `Feature_01_Stock_Daily` saat antrean kosong (jeda ≥ 5 menit);
  - kegagalan hanya dicatat (`coverage_refresh_failed`), memakai kunci advisory `ai_data_coverage_job`;
  - job pagi tetap menjadi cadangan.
- **Telegram:**
  - `coverage_job.py` mengirim satu notifikasi per hari per sumber BASI ke `telegram-monitor`;
  - `telegram_monitor.py` menerima `source_table` `AI_data_coverage` dengan dedupe yang ada;
  - variabel berupa referensi Railway (hanya nama dicatat).
- **Catatan:** layanan pemuat dan telegram bersumber `main`, jadi deploy-nya dikonfirmasi user saat eksekusi.

## 10. G2-B, S20, minimal 4 hipotesis, analisis faktor

**Asal:** `G2_G3_REACTIVATION_PLAN.md` §8 langkah 8 (FINAL, disetujui 2026-10-02: "sesudahnya, sesuai hasil golden
test"); rincian di `FACTOR_EVENT_RESEARCH_PLAN.md` langkah 1–5.

- **S20:** fungsi lintas entitas di backend (prasyarat).
- **Return abnormal** dengan benchmark yang dideklarasikan.
- **Jalur di sekitar event:** AAR, CAAR, CAR beberapa jendela.
- **Minimal 4 hipotesis teruji.**
- **Analisis faktor** setelah langkah 1–4 terbukti.
- **Keputusan yang masih terbuka** (`FACTOR_EVENT_RESEARCH_PLAN.md` §12, dijawab sebelum mulai): urutan langkah,
  `AI_RESEARCH_MIN_ANGLES=4`, perlakuan bila data < 4 angle, `AI_RESEARCH_MIN_FAMILIES`.
- **Status:** S20 OPEN, S22 PARTLY FIXED.

## 11. P9 kamus nilai dan alat "cari nilai"

**Asal:** `VALUE_DICTIONARY_PLAN.md`. Rencana dipisah atas permintaan user 2026-10-01, dengan keputusan desain user
2026-10-01:
- memperluas job `ai-data-coverage`;
- dua jalur (katalog dan alat);
- `get_system_capabilities` dijalankan sistem di awal run, pilihan (a).

**Yang sudah menutup sebagian:**
- `get_dimension_values` (tabel statis);
- `lookup_reference` (tabel referensi, cari nama);
- `get_system_capabilities` (P31).

**Yang belum:** kamus nilai untuk kolom kategori di tabel bertanggal (G17 UNDERADDRESSED).

**Sebelum eksekusi:** cocokkan ulang isi rencana dengan alat yang sudah ada. `pg_trgm` adalah keputusan terpisah
(`FUTURE_PLAN.md` §3).

## 12. Prosedur tabel baru (FX, indeks, makro)

**Asal:** `NEW_TABLE_ONBOARDING_PLAN.md` (keputusan user 2026-10-01: "record now, run later").

Dijalankan saat tabel baru pertama dimuat, bersama Part A `ERRORS_AND_SOLUTIONS.md`. Tabel makro di database adalah
keputusan terpisah (`FUTURE_PLAN.md` §3).

**Rencana user 2026-10-09 (bukan perintah jalan):** "saya plan sehabis ini karena kuota weekly sudah habis tuk ingest habis2an data macro, fundamental, fx, cross market, commodities etc. kemudian feature.. ini adalah proses onboarding only. saya minta kamu cek, table onboarding plan MD apakah bisa solely cukup dijadikan dokumen onboarding table ini, yang mana pada akhirnya data2 ini juga bisa visible ke sisi AI?" Rencana diperiksa dan diperbarui hari yang sama (rantai visibilitas AI, butir 14–21, pertanyaan per kelas aset, tabel Feature, keadaan kode sekarang, daftar yang harus jadi sebelum tabel pertama dibuka ke AI). Usulan kode di dalamnya (ERRORS M136, M137) menunggu keputusan user.

---

## Sudah dieksekusi, tinggal bukti live

Bukan rencana lagi; daftar dan statusnya ada di `OUTSTANDING_ISSUES.md` ("Sudah diperbaiki, hanya menunggu golden
test") dan `ERRORS_AND_SOLUTIONS.md`. Contoh: G19 lapis 1 dan 3, M69 tahap 1, M70, S28, S29 (R-STORE), C06 1b, S22.

## Audit dokumen rencana (2026-10-06)

| Dokumen | Hasil audit |
|---|---|
| `PLAN_2026-10-05.md` | Item 1–10 dan 12 dieksekusi (golden test 06b); sisa item 10/12 → EXEC-1; item 11 → EXEC-3 (`EXEC.md`) |
| `PLAN_FINAL_2026-10-04.md` | Fase 1–6 dieksekusi (golden test akhir dihentikan user di 23/32). Daftar "buntu" (P05/P08, G10, D06, M42) bukan butir yang disetujui |
| `PLAN_ROUND_2026-10-04.md`, `PLAN_EVIDENCE_GATE_2026-10-04.md` | Digantikan `PLAN_FINAL_2026-10-04.md` |
| `PLAN_BE_OPTIMIZATION_2026-10-04.md` | O2, O3, O4, P28-D live (label "belum dieksekusi" di judul O3 sudah basi); O1 tidak dikerjakan (keputusan user "as is") |
| `PLAN_ROUTER_MODELS_2026-10-04.md` | Dieksekusi (router, `AI_MODELS.md`, M80 a/b, uji R-STORE); P30 ditunda user → `FUTURE_PLAN.md` |
| `ROADMAP_FRONTEND_2026-10-04.md` | Usulan → `FUTURE_PLAN.md` |
| `ROUND_PLAN_2026-10-03.md` (+ Fase C, D) | Fase A–D live; Fase E → butir 8 |
| `G2_G3_REACTIVATION_PLAN.md`, `MODE4_CONVERSATION_PLAN.md` | Dieksekusi (judul masih "belum dijalankan", basi); langkah 8 → butir 10 |
| `FACTOR_EVENT_RESEARCH_PLAN.md` | Rincian butir 10 |
| `HIGH_ALERT_PLAN.md`, `HIGH_ALERT_IMPLEMENTATION_PLAN.md` | H1, H2, H5, Prioritas 2 dieksekusi; 1a-permanen dan Telegram → butir 9; H3 kamus istilah menunggu daftar istilah user → `FUTURE_PLAN.md` |
| `UNDERADDRESSED_PLAN_CAT23.md` | Kelompok 2–5, 7 (sebagian) dieksekusi; §7 sisa → butir 9; kelompok 1, 6, 8 → `FUTURE_PLAN.md` |
| `VALUE_DICTIONARY_PLAN.md` | → butir 11 |
| `NEW_TABLE_ONBOARDING_PLAN.md` | → butir 12 |
| `WAREHOUSE_AGGREGATION_PLAN.md` | Fase 1 dan 2 dieksekusi (fase 2 = D5 `query_metric`) |
| `EXTRACTION_AND_AUDIT_PLAN.md` | Bagian yang disetujui dieksekusi; "Proposed, not approved yet" → `FUTURE_PLAN.md` |
| `ANSWER_INTEGRITY_FIX_PLAN.md`, `MULTI_ANGLE_FIX_PLAN.md` | Dieksekusi; topik desain multi-angle yang belum disetujui → `FUTURE_PLAN.md` |
| `WEB_GOVERNOR_PLAN.md` | P1–P8 diimplementasikan; golden set dan antrean tinjauan manusia P4 → `FUTURE_PLAN.md` |
| `AI_ANALYST_IMPLEMENTATION_PLAN.md` (2026-09-13), `FEATURE_01_AUTOMATION_PLAN.md` | Dasar arsitektur lama / sudah aktif; tidak ada butir disetujui yang tertunda |
| `FUTURE_PLAN.md` | Tetap terpisah; §1 sudah dieksekusi di round 2026-10-03 |
