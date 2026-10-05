# Audit system prompt market-ai-orc (2026-10-05)

Status: **DISETUJUI dan DIJALANKAN 2026-10-05** (A1–A8, B1–B6, format Markdown). Golden test ditunda atas permintaan
user, jadi perilaku live belum diukur. Hasilnya ada di bagian "Hasil" di akhir dokumen.

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

## Hasil (2026-10-05)

**Ukuran prompt dev** (dirakit dengan switch dev dan alat dev):

| | Sebelum | Sesudah |
|---|---|---|
| Karakter | 33.899 | 34.509 |
| Token (perkiraan `estimate_tokens`) | ±11.557 | ±11.654 (+0,8%) |
| Baris | 452 | 132 |

Prompt bertambah sedikit karena kalimat baru tentang alat yang aktif (web, `lookup_reference`, `query_metric`, sumber
angka, hitung ulang backend). Penyatuan B1–B6 menghapus kalimat dobel.

**Yang berubah** (`app/orchestrator.py`):

| No | Perubahan |
|---|---|
| A1 | Kalimat "data di luar katalog" ditulis dari alat aktif. Bila ada `find_web_fact`: satu fakta publik boleh dari web, dan fakta web tidak pernah menjadi input perhitungan. Bila ada `lookup_reference`: atribut tabel referensi dibaca dari database, bukan web |
| A2 | Bila ada `query_metric`: metrik resmi dijawab `query_metric`, lainnya lewat jalur DataNeed |
| A3 | Daftar sumber angka mengikuti alat aktif (`query_metric`, baris `lookup_reference`, fakta web sebagai fakta web) |
| A4 | "Jangan bilang terverifikasi" kecuali `complete_analysis` menyebutnya dihitung ulang backend (event study, backtest, temuan riset) |
| A5, A6 | Referensi nilai mengikuti alat aktif: `{{metric…}}` bila ada `query_metric`; `{{fact…}}` hanya bila `lookup_fact` aktif; `{{analysis…}}` dihapus dari jalur DataNeed |
| A7 | Helper: `load, load_range, in_period, sql, join, quality` |
| A8 | `get_session_output` lewat `ref` (`out.oN`); tabel lama dipulihkan otomatis |
| B1 | "Pola bukan sebab/prediksi/sinyal" cukup di MODES |
| B2, B3 | Rencana hipotesis merujuk langkah 4–5 rencana multi-sudut |
| B4 | Temuan eksperimen dikutip seperti temuan sudut |
| B5 | Bagian interpretasi sudut merujuk INTERPRETING RESEARCH |
| B6 | Aturan LIMITATION disatukan di aturan umum no. 11 |
| C | Judul blok `## `, satu baris per paragraf atau butir, urutan umum → data → jawaban → riset |

Skema rencana **tidak** dibungkus code fence, karena aturan balasan melarang code fence; skema hanya ditaruh di baris
sendiri.

**Prinsip yang dipakai:** kalimat yang menyebut alat hanya ditulis bila alatnya ditawarkan. Nama alat diambil dari
registry (`build_system_prompt(tools=...)`), kelas masalah yang sama dengan P31.

**Tes:** `tests/test_prompt_audit.py` (7 tes). Tes lama yang membandingkan blok mentah dengan prompt sekarang memakai
`markdown_prompt(...)`. Orc: 1.113 lulus.

## Putaran 2: merapikan bentuk (DIJALANKAN 2026-10-05, lihat "Hasil putaran 2")

Status: **DIJALANKAN 2026-10-05** (orc `c1f7119`, deploy `a7363094` SUCCESS); rencana awal di bawah.
Status sebelumnya: **RENCANA FINAL, belum dijalankan.** Diminta user 2026-10-05 ("coba kita ganti promptnya dulu ya. masukan
ke dalam plan jangan eksekusi"); K1–K4 **disetujui user 2026-10-05** ("K1-K4 OK"). Belum ada kode yang diubah.
Dijalankan bersama M26 pilihan B (`PLAN_2026-10-05.md` item 8), yang juga mengubah dua kalimat prompt (M26-P di
bawah); keduanya diukur oleh satu golden test (`PLAN_2026-10-05.md` item 9). Item F1–F4 hanya memindah dan memecah
kalimat yang sudah ada.

### Dasar

- **Bahan:** prompt yang benar-benar dirakit untuk dev (`build_system_prompt` dengan switch dev + `TOOL_ENVELOPE_RULE`):
  34.509 karakter, ±11.654 token, 132 baris, 18 bagian (sama persis dengan angka "Sesudah" di atas).
- **Acuan luar:**
  - [OpenAI GPT-4.1 Prompting Guide](https://developers.openai.com/cookbook/examples/gpt4-1_prompting_guide): judul
    Markdown untuk bagian dan subbagian, daftar bernomor atau berbutir; periksa instruksi yang bertentangan; bila
    bertentangan, instruksi yang lebih dekat ke akhir cenderung diikuti.
  - [Anthropic, Effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents):
    bagian terpisah dengan judul jelas; informasi minimal tetapi cukup; hindari logika rapuh.
- **Kesimpulan putaran 1:** isi sudah benar (alat aktif saja, tanpa nama alat usang, aturan dobel sudah disatukan).
  Yang belum rapi adalah **bentuk**.

### Temuan (nomor baris = prompt dev yang dirakit)

| No | Temuan | Baris |
|---|---|---|
| T1 | 13 paragraf prosa lebih dari 600 karakter dalam satu baris, masing-masing 8–15 aturan: Final response 1.874; DATA DISCOVERY 1.754; DATA NEED butir 1 1.712 dan paragraf angka 1.241; MODES 1.046; NAMED-PERIOD RETURNS 898; VALUE REFERENCES 1.410; MULTI-ANGLE PLAN butir 2, 3, 6 (709, 704, 1.095); HYPOTHESIS PLAN butir 2 617; MULTI-ANGLE FINDINGS 1.908; RESEARCH FINDINGS 1.454. Penyebab: format putaran 1 menyambung baris menjadi satu paragraf per butir tanpa memecah aturannya | 27, 44, 48, 53, 56, 59, 96, 101, 102, 105, 112, 117, 120 |
| T2 | Aturan sumber data luar (fakta web, `lookup_reference`) ada di bawah MODES | 56 |
| T3 | Aturan menjalankan riset (jangan ubah modul sandbox, `session_recovery`) ada di awal MULTI-ANGLE FINDINGS, bukan di langkah 6 rencana multi-sudut | 117 |
| T4 | RESEARCH FINDINGS sebagian besar berisi isi rencana hipotesis dan cara menjalankannya (`event_summary`), bukan cara membaca temuan | 120 |
| T5 | Dua bagian alat terpisah jauh: "Tool use" (atas) dan TOOL RESULTS (paling akhir, ditempel `TOOL_ENVELOPE_RULE`) | 20, 131 |
| T6 | Dua skema JSON rencana riset (±3.700 karakter) ada di Final response, jauh dari aturan riset; urutan "umum → data → jawaban → riset" jadi tidak berlaku untuk bagian ini | 29–41 |
| T7 | Kata "angle" dipakai untuk dua hal: sudut rencana multi-sudut (`angle_id`) dan dua ukuran temuan hipotesis (`angle_a` = besar efek, `angle_b` = frekuensi sukses). "When the two angles point different ways" bisa dibaca sebagai dua sudut riset | 92, 120, 125 |
| T8 | Bekas rakitan: dua "for example" dalam satu butir; butir terakhir daftar referensi berakhir ";" | 92, 94 |
| T9 | Gaya judul campur ("General rules", "Tool use", "Final response" vs huruf kapital) dan nama yang tidak sejajar ("RESEARCH PLAN CONFIRMATION: HYPOTHESIS PLAN", "RESEARCH FINDINGS") | — |
| T10 | Aturan memilih bentuk rencana ditulis dua kali dengan kata berbeda (pembuka MULTI-ANGLE PLAN dan pembuka HYPOTHESIS PLAN) | 99, 110 |
| T11 | Aturan 15 ("bahasa pesan terakhir user") tanpa bawaan bila pesan tidak berbahasa. Kasus M14 s4.1: "BBRI" saja dijawab klarifikasi berbahasa Inggris | 18 |

### Perubahan yang diusulkan

**Bentuk saja (kata tidak berubah):**

- **F1. Pecah paragraf panjang (T1).** Setiap aturan menjadi satu butir "-" di bawah judulnya. Butir memakai "-", bukan
  nomor, supaya tidak ada angka baru di prompt (prompt adalah sumber angka bagi gerbang provenance). Daftar bernomor
  yang sudah ada tetap.
- **F2. Pindahkan blok ke tempatnya:**
  1. Kalimat metrik resmi (`query_metric`, awal DATA NEED) dan kalimat data luar (MODES: fakta web dan
     `lookup_reference`) → bagian baru **DATA SOURCES** tepat sebelum DATA NEED. Urutannya database dulu, web terakhir:
     metrik resmi → tabel referensi → DataNeed → fakta web. Kalimat `lookup_reference` dipindah sebelum kalimat web;
     katanya tetap.
  2. "A data need in mode RESEARCH is accepted only for an approved hypothesis plan…" (akhir MULTI-ANGLE PLAN) →
     MODES.
  3. Dua kalimat pembuka MULTI-ANGLE FINDINGS (modul sandbox, `session_recovery`) → langkah 6 MULTI-ANGLE PLAN (T3).
  4. RESEARCH FINDINGS dibagi (T4):
     - kalimat isi rencana dan satuan → langkah 2 HYPOTHESIS PLAN;
     - kalimat sampel minimum dan `event_summary` → langkah 4 HYPOTHESIS PLAN;
     - sisanya (apa yang dikembalikan `complete_analysis`) tetap sebagai HYPOTHESIS FINDINGS.
  5. TOOL RESULTS → tepat setelah TOOL USE, tetap hanya bila `AI_ENABLE_TOOL_ENVELOPE` aktif (T5).
- **F3. Judul seragam (T9).** Semua kapital, tanpa akhiran "RULES":
  - GENERAL RULES, TOOL USE, FINAL RESPONSE;
  - DATA DISCOVERY, DATA NEED;
  - MULTI-ANGLE PLAN, HYPOTHESIS PLAN, HYPOTHESIS FINDINGS.

  Rujukan antar-bagian di dalam teks hanya "VALUE REFERENCES" dan "INTERPRETING RESEARCH"; keduanya tidak berganti
  nama.
- **F4. Bekas rakitan (T8).** Butir terakhir daftar referensi ditutup titik. Contoh temuan dipecah menjadi dua butir:
  satu untuk temuan sudut, satu untuk temuan hipotesis.

**Mengubah atau menambah kata (K1–K4 disetujui user 2026-10-05):**

- **K1 (T7).** Satu kalimat baru di HYPOTHESIS FINDINGS: "`angle_a` (the effect against the baseline) and `angle_b`
  (the success rate against the base rate) are the two measures of a hypothesis finding, not angles of a multi-angle
  plan." Lalu "When the two angles point different ways" menjadi "When angle_a and angle_b point different ways".
  Nama field tidak diubah, karena itu keluaran backend.
- **K2 (T11).** Aturan 15 ditambah: "When the latest message has no language of its own (for example only a ticker),
  use the language of the conversation, and Indonesian when there is none." Ini hanya menutup kasus s4.1. Akar utama
  M14, yaitu kalimat batasan yang ditulis backend dalam bahasa Inggris, tidak tercakup (lihat "Tidak tercakup").
- **K3 (T6).** Dua skema rencana riset beserta aturan field-nya pindah ke bagian baru RESEARCH PLAN FORMS setelah
  HYPOTHESIS PLAN. Final response cukup menyebut "research_plan: one of the two forms under RESEARCH PLAN FORMS".
  Alasannya, skema hanya dipakai untuk RESEARCH_PLAN_CONFIRMATION, dan model membacanya tepat setelah aturan rencana.
  Kode: `final_contract_block` mengeluarkan skema sebagai blok terpisah.
- **K4 (T10).** Aturan memilih bentuk rencana disatukan di bagian pendek RESEARCH PLANS sebelum kedua rencana. Isinya
  gabungan kedua versi tanpa menghilangkan syarat apa pun: "with no angles the user did not ask for", "even when a
  library method could also test them", "Never mix the two in one plan".
- **M26-P (ikut keputusan M26 pilihan B).** Dua kalimat menyebut vonis baru PARTIALLY_SUPPORTED untuk rencana
  hipotesis:
  - daftar vonis di HYPOTHESIS FINDINGS menjadi "(SUPPORTED, PARTIALLY_SUPPORTED, NOT_SUPPORTED, INCONCLUSIVE,
    NOT_EVALUATED)", ditambah: "PARTIALLY_SUPPORTED means the effect is in the expected direction but smaller than
    the minimum effect the user named";
  - INTERPRETING RESEARCH butir answer: "supported, partially supported, not supported, or inconclusive".
  Untuk riset multi-sudut status itu sudah ada; hanya alasannya yang baru (`BELOW_USER_MINIMUM_EFFECT`).

### Urutan bagian sesudahnya

1. Pembuka
2. GENERAL RULES
3. TOOL USE
4. TOOL RESULTS (bila aktif)
5. FINAL RESPONSE
6. DATA DISCOVERY
7. DATA SOURCES (baru, F2.1)
8. DATA NEED
9. MODES
10. TIME BASIS
11. NAMED-PERIOD RETURNS
12. WEEKLY AND MONTHLY
13. CONVERSATION REUSE
14. VALUE REFERENCES
15. METHODOLOGY
16. RESEARCH PLANS (K4)
17. MULTI-ANGLE PLAN
18. HYPOTHESIS PLAN
19. RESEARCH PLAN FORMS (K3)
20. MULTI-ANGLE FINDINGS
21. HYPOTHESIS FINDINGS
22. INTERPRETING RESEARCH

### Pagar pengaman (isi tidak boleh berubah diam-diam)

- **Tes inventaris kalimat (baru):** kalimat prompt sebelum dan sesudah dibandingkan (dinormalisasi, urutan diabaikan).
  Selisihnya harus persis daftar K1–K4 dan M26-P yang disetujui; kalimat lain tidak boleh hilang, bertambah atau
  berubah.
- **Tidak ada angka baru** di luar yang disetujui. Tes yang sudah ada diperluas ke semua teks baru.
- **Ukuran:** token naik paling banyak 2%. Paragraf prosa paling panjang 600 karakter, kecuali skema JSON.
- **Kesesuaian dengan alat aktif tetap:** tes `tests/test_prompt_audit.py` tetap lulus. Tes yang mencari potongan
  kalimat atau urutan judul disesuaikan dengan judul baru.
- **Tes penuh orc.** `AI_TOOLS.md`, `AI_MODELS.md` dan `AI_ROUTER.md` tidak terpengaruh; tes drift-nya ikut
  dijalankan.

### Deploy dan verifikasi

- **Deploy:** hanya market-ai-orc (push `main`, deploy otomatis). Klaim SUCCESS hanya untuk deployment commit itu.
  Biaya cache naik sekali karena awalan prompt berubah.
- **Golden test:** satu golden test setelah putaran 2 dan M26 live, rinciannya di `PLAN_2026-10-05.md` item 9
  (hanya setelah user meminta).

### Dokumen yang diperbarui saat dijalankan

- Dokumen ini, bagian "Hasil putaran 2".
- `PLAN_2026-10-05.md` (item 7).
- `ERRORS_AND_SOLUTIONS.md` M14 (bagian s4.1, K2).
- `RAILWAY_CHANGELOG.md` (deploy).
- `OUTSTANDING_ISSUES.md`.

### Tidak tercakup

- Prompt lain: router pesan pertama dan lanjutan, pengklasifikasi balasan rencana, dan web-governor.
- Kalimat batasan yang ditulis backend dalam bahasa Inggris, akar utama M14. Perbaikannya di kode backend, bukan di
  prompt; diusulkan terpisah.
- Nama field `angle_a` / `angle_b`.

### Hasil putaran 2 (2026-10-05)

- **Live:** commit `c1f7119`, market-ai-orc `a7363094` SUCCESS. Diperintah user 2026-10-05 ("Langsung jalankan plan").
- **Isi:** F1–F4, K1–K4 dan M26-P sesuai rencana. Urutan 22 bagian persis seperti "Urutan bagian sesudahnya".
- **Tes inventaris kalimat** (`tests/test_prompt_pass2.py`, acuan `tests/fixtures/prompt_dev_before_pass2.md` = prompt
  dev `d9c4ebc`): selisih kalimat persis K1, K2, K3, K4, M26-P dan F4. Kalimat lain hanya pindah.
- **Angka:** tidak ada digit baru (daftar digit sebelum dan sesudah sama).
- **Ukuran:** 34.509 → 34.937 karakter (+1,2%). Token (tokenizer o200k) 7.409 → 7.530 = **+1,63%** (batas 2%).
- **Satu penyesuaian dari rencana (F1):** paragraf panjang dipecah **satu baris per aturan tanpa tanda "-"**. Dengan
  tanda "-" per aturan, token naik 3,12% (tanda saja +1,96%), melewati batas 2%. Aturan turunan di bawah butir bernomor
  diberi indentasi. Baris prosa terpanjang sekarang 517 karakter (batas 600).
- **Tambahan kecil yang diperlukan:** catatan persetujuan rencana (`APPROVED_NOTE`) kini menyebut bagian yang benar
  ("HYPOTHESIS PLAN" saat dua bentuk rencana aktif), karena judul lama tidak ada lagi.
- **Tes orc:** 1.126 lulus. Tes lama yang mencari potongan teks satu baris atau judul lama disesuaikan; isinya tidak
  berubah.
- **Pengukuran perilaku:** golden test `PLAN_2026-10-05.md` item 9 (jumlah jawaban akhir yang ditolak karena bukan
  JSON, bahasa `lang_ticker_only`, `g6_success_rule`).
