# Rencana: menghidupkan kembali G2 (event study) dan G3 (uji hipotesis bebas), lalu golden test 5 soal

Status: rencana, belum dijalankan (2026-10-02). Keputusan user 2026-10-02:
- G2 dan G3 dihidupkan kembali;
- keduanya bisa berdiri sendiri atau saling melengkapi;
- yang disesuaikan adalah arsitektur dan kode G2/G3 agar cocok dengan infrastruktur sekarang (DataNeed, sesi
  sandbox, riset multi-angle G4, mode 4);
- sesudahnya golden test 5 soal.

Terkait:
- `FACTOR_EVENT_RESEARCH_PLAN.md`: return abnormal, jalur event, S20, minimal 4 hipotesis;
- `MODE4_CONVERSATION_PLAN.md`: disetujui;
- `ERRORS_AND_SOLUTIONS.md`: S20, S21, S22, S23, P22, G18.

## 1. Kondisi sekarang (diverifikasi di kode)

| | G2 event study | G3 uji hipotesis bebas |
|---|---|---|
| Kode | sandbox `app/spec.py` (metode `EVENT_STUDY`), `runtime/validator.py` (`_event_study_reference`, `_segment_stats`, `CALCULATION_MISMATCH`) | orc `app/research_plan.py` (rencana v1: 1–4 eksperimen, satu hipotesis per eksperimen); sandbox `app/research_governance.py`, `app/research_findings.py`, `runtime/research_stats.py`, helper `saniti.event_summary` |
| Kenapa mati | Hidup di jalur Analysis Spec, yang hanya aktif bila DataNeed mati | Orc memilih prompt dan skema rencana v1 **atau** v2 (multi-angle) dalam satu saklar (`orchestrator.py` ~775). Sandbox sudah bisa keduanya saat riset selesai (`dataneed_service.py` ~773 grup v2, ~785 temuan v1) |
| Kekuatan | Satu-satunya pemeriksa yang menghitung ulang hasil AI secara independen dan membandingkannya | Hipotesis bebas dari penalaran AI, tidak dibatasi perpustakaan metode; statistik dihitung ulang backend dengan pengelompokan per tanggal, MDE, kategori sampel, vonis; anggaran eksperimen dan tindak lanjut |
| Kelemahan yang ikut diperbaiki | CI menganggap baris independen; return mentah; satu horizon | Baris event/pembanding buatan AI tidak dicek |

## 2. Prinsip

1. **G2 dan G3 berdiri sendiri.** Masing-masing bisa dipakai tanpa yang lain dan tanpa G4.
2. **Saling melengkapi lewat antarmuka yang sama:**
   - hasil setiap alat menjadi output atau temuan yang tercatat di catatan percakapan
     (`MODE4_CONVERSATION_PLAN.md` E1) dan bisa dirujuk (`out.oN`, `finding.<id>`);
   - event dari G2 bisa langsung menjadi masukan hipotesis G3;
   - semua uji masuk satu buku percobaan.
3. **Tanpa hardcode:**
   - event, outcome dan benchmark dideklarasikan sebagai peran, memakai bahasa rumus yang sudah ada
     (`runtime/expression.py`, `runtime/research_inputs.py`);
   - ambang (minimal event, overlap) adalah kebijakan dengan default yang tercatat;
   - tidak ada nama tabel, kolom, ticker atau indeks di kode metode.
4. **Pakai ulang infrastruktur aktif:** bundle DataNeed, sesi sandbox, harness penyelesaian, value reference, gerbang
   jawaban. Tidak menghidupkan jalur Analysis Spec.

## 3. G2: event study di infrastruktur sekarang

**Bentuk:** helper sesi `saniti.event_study(...)`.
- Tersedia di **setiap sesi analisis dan riset**, jadi AI bisa memakainya kapan saja di `run_python`, tanpa rencana
  riset.
- Masukan (peran):
  - `request`: permintaan data;
  - `event`: rumus predikat per entitas dan tanggal, bahasa rumus yang sama dengan riset;
  - `outcome`: `{"forward_return": <kolom harga>}`, horizon atau jendela;
  - `overlap_policy` (default `NON_OVERLAPPING`);
  - `min_events` (default kebijakan 30);
  - opsional `holdout_start`.
- Keluaran: tabel ringkasan per segmen (ALL, IN_SAMPLE, OUT_OF_SAMPLE) dengan kolom dari `spec.py`
  (`EVENT_STUDY_COLUMNS`), dirilis sebagai output, ditambah tabel event (tanggal dan entitas) supaya bisa dipakai G3.

**Pemeriksa independen (inti G2, diangkat dari `runtime/validator.py`):**
- saat `complete_analysis` atau penyelesaian grup riset, harness (di luar proses AI) membaca ulang file bundle,
  membangun ulang event dan outcome dari deklarasi, lalu menghitung ulang ringkasannya;
- hasilnya dibandingkan dengan output yang dirilis: `PASS` atau `CALCULATION_MISMATCH` (pola
  `_event_study_reference`);
- `calculation_validation` untuk output ini berubah dari `NOT_PERFORMED` menjadi `PASS` / `FAIL`. Ini perbaikan nyata
  untuk S23, khusus event study;
- gerbang jawaban memberi label sesuai hasil pemeriksaan.

**Perbaikan statistik saat diangkat:**
- CI dan p-value memakai **pengelompokan per tanggal** dan penjarangan horizon dari mesin aktif
  (`research_engines._welch` / effective count), bukan baris independen;
- koreksi uji berganda memakai kebijakan yang sudah ada (NONE/BONFERRONI/HOLM/BH).

**Tahap G2-B (sesudah G2-A stabil; detail di `FACTOR_EVENT_RESEARCH_PLAN.md` langkah 2–3):**
- jalur hari sekitar event (AAR, CAAR, CAR beberapa jendela);
- return abnormal dengan benchmark yang dideklarasikan:
  - deret dari permintaan lain sekarang;
  - rata-rata lintas saham setelah S20 (S20 memindahkan hitungan itu dari AI ke backend; sebelum S20, benchmark yang
    dihitung AI tidak diperiksa).

## 4. G3: uji hipotesis bebas di infrastruktur sekarang

**Bentuk:** rencana riset v2 diperluas dengan daftar **`experiments`** (G3) di samping **`angles`** (G4), dalam satu
rencana, satu persetujuan dan satu token. Mode 4 dan alur persetujuan tidak perlu jalur baru. Satu rencana boleh
berisi:
- hanya `experiments` (G3 sendiri);
- hanya `angles` (G4 sendiri);
- keduanya (saling melengkapi).

**Isi eksperimen G3** (dari rencana v1, tidak memakai perpustakaan metode):
- hipotesis, tujuan, kondisi, outcome, pembanding (teks bebas);
- arah yang diharapkan, horizon, satuan outcome, efek minimum, definisi sukses, kebijakan koreksi, holdout opsional.

**Eksekusi:** di sesi grup riset yang sama.
- AI membangun event dan pembanding dengan Python bebas, atau dari tabel event G2.
- AI memanggil `saniti.event_summary(...)`.
- Saat grup selesai, harness menghitung ulang statistik dari agregat per tanggal yang dirilis (`research_findings` v1
  + `research_stats`), dengan nilai dari rencana yang disetujui.
- Temuan G3 masuk respons dengan namespace rujukan sendiri (`finding.<hypothesis_id>`), berlabel **STATISTICS_VERIFIED**
  (rumus buatan AI tidak dicek, ditulis jelas).

**Anggaran dan disiplin (dari G3 lama):**
- maksimal hipotesis dan eksperimen per run (kebijakan `PY_SANDBOX_RESEARCH_MAX_*`);
- tindak lanjut (`followup_of`) dihitung ke hipotesis induknya;
- jumlah uji untuk koreksi = angle G4 + eksperimen G3 di rencana itu (nanti ditambah buku percobaan percakapan).

**Yang diubah:**
- **orc:**
  - skema rencana v2 + `experiments`;
  - cek kelayakan untuk data eksperimen;
  - prompt rencana dibangkitkan dari skema;
  - `research_plan_v2` totals menghitung keduanya;
  - render temuan G3.
- **sandbox:**
  - governance v2 menerima eksperimen;
  - `validate_group` memanggil evaluator temuan v1 untuk eksperimen di grup itu;
  - satu envelope temuan untuk angle dan eksperimen.
- **Migrasi:** `Tool_Catalog` untuk skema alat rencana yang berubah, bila skemanya berubah.

## 5. Bagaimana G2, G3, G4 saling melengkapi (contoh)

Pertanyaan: "Apa yang terjadi pada saham bank setelah net jual asing besar?"
- **G2 (analisis, tanpa rencana):** `saniti.event_study` menghitung return 5 hari setelah event, lalu pemeriksa
  independen PASS.
- **G3 (di rencana):** hipotesis bebas "efeknya hanya di bank BUMN", memakai tabel event G2, lalu `event_summary`.
- **G4 (di rencana):** 4 angle dari perpustakaan, misalnya `quantile_ranking` net asing dan `lead_lag`.

Jawaban merujuk ketiganya. Setiap angka membawa label pemeriksaannya.

## 6. Perbaikan kecil yang masuk batch ini

Keduanya memengaruhi kualitas jawaban di golden test.
- **S21:** helper `range` menimpa `range` bawaan Python.
  - Helper tetap tersedia sebagai `saniti.range`.
  - Nama bebas `range` kembali ke bawaan Python.
  - Test: `range(3)` di sesi.
- **P22:** unit dobel ("pp pp").
  - Setelah rujukan diisi, salinan unit yang sama tepat di belakangnya dibuang dan dicatat di log.
  - Berlaku untuk semua format yang menambah unit (`pct`, `pctv`, `pp`, `x`, `rp`).

## 7. Golden test 5 soal (sesudah langkah 1–4)

**Tujuan:** angka akurasi nyata, bukan perkiraan (S23).

**Kunci jawaban:**
- dihitung **independen**: SQL read-only dan pandas lewat job sementara di Railway (pola `dataneed-poc-job`);
- dicatat di tabel `Golden_Analysis_Test` dan `Golden_Analysis_Test_Run` / `_Result` yang sudah ada, lengkap dengan
  toleransi.

| # | Soal (bahasa user) | Yang diuji | Kunci dihitung dari |
|---|---|---|---|
| 1 | Total net beli investor asing di pasar reguler per saham untuk 10 saham bank paling likuid selama 2025 | Analisis SUM + peringkat | SQL `IDX_Broker_Summary` / `Feature_03` |
| 2 | Harga penutupan tertinggi dan terendah tiap saham bank 2025 dan persen selisihnya | Analisis MIN/MAX | SQL harga |
| 3 | Return 5 hari saham bank setelah hari turun ≥ 5% (event per saham, tidak tumpang tindih), dibanding hari lain | **G2** + pemeriksa independen | pandas independen |
| 4 | Apakah hari dengan net beli asing positif di BBCA diikuti return 1 hari lebih tinggi daripada hari lainnya? | **G3** (hipotesis bebas, `event_summary`) | pandas independen (selisih rata-rata dan CI dengan pengelompokan per tanggal) |
| 5 | Siapa broker yang konsisten membeli saham bank saat market crash? (mode 4) | Alur lengkap: analisis + G4 4 angle (+ G2/G3 bila dipakai AI) | Bagian analisis dari pandas independen; riset dinilai dari kelengkapan dan konsistensi temuan, bukan angka tunggal |

**Dicatat per soal:**
- angka benar/salah terhadap kunci (toleransi per kolom);
- metode yang dipilih AI;
- label pemeriksaan;
- detik;
- jumlah panggilan model;
- penolakan gerbang.

Saklar pikiran (`AI_CAPTURE_REASONING`) menyala, supaya kesalahan bisa ditelusuri ke penalarannya.

**Hasil** dicatat di `DATABASE_CHANGELOG.md` (data golden), `RAILWAY_CHANGELOG.md` (run) dan
`ERRORS_AND_SOLUTIONS.md` (S23 diperbarui dengan angka akurasi).

## 8. Urutan kerja

1. S21 + P22 (kecil; sandbox dan orc).
2. **G2-A:** helper `event_study` + pemeriksa independen + CI per tanggal (sandbox), lalu render dan label (orc).
3. **G3:** `experiments` di rencana v2 (orc), lalu governance dan evaluasi di grup (sandbox).
4. Uji live singkat G2 dan G3 masing-masing sendiri, lalu bersama (saklar pikiran menyala).
5. **Golden test 5 soal.**
6. Sesudahnya, sesuai hasil golden test: G2-B (jalur event, return abnormal), S20, router mode 4, minimal 4 hipotesis.

Setiap langkah:
- `pytest` per service dengan PG scratch;
- `git diff --check`, commit, push `main`;
- deploy satu service per kali sampai `SUCCESS` dan baca log startup;
- dokumen diperbarui: README service, `ERRORS_AND_SOLUTIONS.md` (S22 jadi FIXED bertahap), `RAILWAY_CHANGELOG.md`,
  `Tool_Catalog` / `AI_research_library` lewat migrasi bila skemanya berubah.

## 9. Risiko dan mitigasi

| Risiko | Penjelasan non-dev | Mitigasi |
|---|---|---|
| Kode lama tidak cocok dengan data sekarang | Validator G2 dibuat untuk Analysis Spec (nama dataset, manifest lama) | Yang diangkat hanya logika hitung ulang; masukannya dari bundle DataNeed seperti `research_validation.py`; test dengan data sintetis dan data dev |
| G2 dan G3 bertabrakan di satu rencana | Dua jenis uji di satu sesi | Satu envelope temuan, ID terpisah (`angle_id` vs `hypothesis_id`), test rencana campuran |
| Rencana jadi lebih rumit untuk AI | Skema v2 ditambah `experiments` | `experiments` opsional; prompt dibangkitkan dari skema; diukur lewat golden test |
| G3 tetap tidak mengecek rumus AI | Event buatan AI bisa salah | Label STATISTICS_VERIFIED tertulis di jawaban; AI dianjurkan memakai tabel event G2 (yang dicek) sebagai dasar G3 |
| Uji makin banyak, peluang kebetulan naik | G2 + G3 + G4 dalam satu rencana | Koreksi menghitung semua uji di rencana; holdout |
| Golden test terlalu kecil | 5 soal bukan ukuran statistik akurasi | Disebut sebagai baseline awal; soal ditambah setelah fitur berikutnya |
| Waktu run | Pemeriksa independen menambah waktu penyelesaian | Diukur; pemeriksa hanya berjalan untuk output event study |

## 10. Keputusan yang diminta dari user

1. G3 masuk sebagai `experiments` di rencana v2 (satu rencana untuk G3 dan G4, usulan), atau tetap jalur rencana
   v1 terpisah?
2. G2 tersedia di sesi analisis tanpa rencana riset (usulan), atau hanya di riset?
3. Lima soal golden test di bagian 7 cukup, atau ada soal yang ingin diganti?
