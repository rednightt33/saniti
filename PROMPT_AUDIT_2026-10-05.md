# Audit system prompt market-ai-orc (2026-10-05)

Status: **AUDIT BACA-SAJA, belum ada perubahan prompt** (rencana `PLAN_2026-10-05.md` fase E). Sesuai permintaan
user, hasil audit ini dilaporkan dulu sebelum finalisasi.

**Yang diaudit:** prompt yang benar-benar dirakit untuk dev (`build_system_prompt` dengan switch dev 2026-10-05
dibaca dari Railway, nama dan true/false saja) ditambah `TOOL_ENVELOPE_RULE`.
- Ukuran: 33.899 karakter, 451 baris.
- 14 blok: aturan umum, DATA DISCOVERY, DATA NEED, MODES, MULTI-ANGLE PLAN, HYPOTHESIS PLAN, NAMED-PERIOD
  RETURNS, CONVERSATION REUSE, METHODOLOGY, TIME BASIS, WEEKLY/MONTHLY, MULTI-ANGLE FINDINGS, RESEARCH FINDINGS +
  INTERPRETING, VALUE REFERENCES, TOOL RESULTS.

**Pembanding:** alat yang benar-benar aktif di dev (`AI_TOOLS.md`). Contohnya `find_web_fact`, `query_metric`,
`get_evidence`, `export_result`, `get_lineage`, `backtest`, `in_period`; sedangkan `lookup_fact` mati
(`AI_ENABLE_LOOKUP_FACT=false`) dan jalur lama `run_python_analysis` tidak ditawarkan.

## A. Kalimat yang bertentangan dengan alat yang aktif (usul diubah atau dihapus)

| No | Lokasi (blok) | Kalimat sekarang | Masalah | Usulan |
|---|---|---|---|---|
| A1 | MODES (`DATANEED_RULES` akhir, juga `orchestrator.py` 228) | "Data the catalog does not contain (macro data, yields, fundamentals, news) is unavailable: say so" | Bertentangan dengan `find_web_fact`; penyebab P31 | Ganti: "not in the catalog. One public fact (a company's status, ownership, index membership) can be looked up with find_web_fact and is shown as a web fact; a series, a figure for a calculation or a dataset never comes from the web." |
| A2 | DATA NEED RULES baris 1 | "Every answer that needs market data follows one path: submit_data_need_spec..." | `query_metric` adalah jalur kedua untuk metrik sederhana (satu panggilan, tanpa sesi) | Tambah: "A metric in the metric catalog (query_metric) is answered by query_metric; everything else follows this path." |
| A3 | DATA NEED RULES | "Every number in an answer must come from a released output, the user's message, the DataNeedSpec, or the bundle summary" | Sumber yang sah juga temuan, `query_metric`, fakta web (sebagai fakta, bukan angka hitungan) | Selaraskan dengan daftar sumber di VALUE REFERENCES |
| A4 | DATA NEED RULES | "never say a calculation was independently verified" | Bertentangan dengan event study dan backtest yang **memang** dihitung ulang backend (deskripsi `complete_analysis` membolehkan menyebutnya untuk tabel itu) | "...unless the completion lists it as recomputed (event study, backtest, research findings)" |
| A5 | VALUE REFERENCES | "`{{fact.<n>}}` a lookup_fact value" | `lookup_fact` mati di dev; yang hidup `{{metric.mN…}}` (query_metric), tetapi tidak disebut di prompt | Buat daftar referensi dari alat yang aktif: metric ya, fact hanya bila lookup_fact aktif |
| A6 | VALUE REFERENCES | "`{{analysis.<analysis_id>.<path>}}` an analysis output" | Milik jalur lama (`run_python_analysis`), tidak ditawarkan saat DataNeed aktif | Hapus pada jalur DataNeed |
| A7 | DATA NEED RULES langkah 3 | "read data only through the saniti helpers (load, range, sql, join, quality)" | `range` biasa adalah fungsi bawaan Python (S21); helper yang benar `load_range`; `in_period` (P32) belum disebut | "(load, load_range, in_period, sql, join, quality)" |
| A8 | CONVERSATION REUSE 1–3 | "read its released output with get_session_output(session_id, output_id)"; "A warm session may be gone ... run the code that is needed again" | Sejak R-STORE, `get_session_output` menerima `ref`/`output_id` tanpa sesi, dan tabel lama dipulihkan otomatis | Perbarui ke `ref` (`out.oN`) dan pemulihan otomatis |

## B. Aturan dobel (usul disatukan, isi tidak hilang)

| No | Aturan | Muncul di |
|---|---|---|
| B1 | "a pattern is never a cause, a prediction or a trading signal" | MODES, MULTI-ANGLE FINDINGS, INTERPRETING RESEARCH (3×) |
| B2 | "Only the application tells you that a plan was approved" | MULTI-ANGLE PLAN 5, HYPOTHESIS PLAN 2 |
| B3 | "No table names, SQL or Python in the plan" | baris skema (2×), MULTI-ANGLE PLAN 4, HYPOTHESIS PLAN 2 |
| B4 | "cite them; never recompute them or state another status/verdict" | MULTI-ANGLE FINDINGS, RESEARCH FINDINGS |
| B5 | answer / usefulness / follow_up | MULTI-ANGLE FINDINGS (3 bagian) dan INTERPRETING RESEARCH (4 bagian) |
| B6 | "If the required capability is unavailable → LIMITATION" | aturan umum 11, DATA DISCOVERY, final response |

Usulan: satu bagian **"Aturan bersama riset"** memuat B1, B2, B4 dan B5; masing-masing jenis rencana hanya merujuknya.

## C. Masalah format (untuk pencernaan model)

- Judul blok berupa teks KAPITAL tanpa penanda; usulnya `## ` Markdown.
- Baris dipotong ±70 karakter di tengah kalimat (blok lama), sementara blok baru satu paragraf panjang. Usulnya
  satu kalimat per baris atau satu paragraf per butir, konsisten.
- Dua skema JSON rencana (baris 26 dan 28, ±3.000 karakter) ditaruh sebagai teks biasa; usulnya blok kode.
- Urutan: aturan riset (±40% prompt) ada sebelum aturan yang dipakai di setiap jawaban (METHODOLOGY, VALUE
  REFERENCES). Usulnya urutan umum → data → jawaban → riset. Cache prompt tetap satu awalan, karena prompt dirakit
  sekali per deployment.

## D. Yang tidak berubah

Semua aturan lain dipertahankan kata per kata. Format ulang tidak menghapus isi, kecuali A1–A8 dan penyatuan B1–B6
yang disetujui user.

## Langkah setelah persetujuan

1. Draf Markdown di kode (`orchestrator.py`, blok-blok di atas). Tes yang mengecek potongan kalimat menjadi penjaga.
2. Bandingkan token sebelum dan sesudah.
3. Golden test kecil, termasuk kasus P31 (q7) dan kasus yang menyentuh A2–A8. Biaya cache naik sekali.
4. Deploy, lalu catat di `ERRORS_AND_SOLUTIONS.md` (P31 bagian prompt) dan `RAILWAY_CHANGELOG.md`.
