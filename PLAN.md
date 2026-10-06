# Rencana induk: sudah disetujui user, belum dieksekusi

Dokumen ini satu-satunya rencana kerja aktif (keputusan user 2026-10-06: "tidak ada format plan PLAN_YYYY-MM-DD,
semua plan harus jadi 1 kecuali future plan").

Aturan:
- **Isi dokumen ini:** hanya pekerjaan yang sudah disetujui user tetapi belum selesai dieksekusi.
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
| 1 | Sisa item 10 dan 12: deploy dua perbaikan, ulang uji item ambang, laporan golden test `ma-qa-20261006b` | "gas" 2026-10-05; format web "Ok tambahkan" 2026-10-06; **EXEC 2026-10-06** | **EXEC** (lihat bagian EXEC) | 1 |
| 2 | P3: gerbang yang salah tolak | 2026-10-06 "OK masukan plan jangan execute dulu" | Belum (P3a ikut EXEC butir 1, P3b ikut EXEC butir 3) | 3 |
| 3 | Item 11: penyortir "free will", jalur TANYA BALIK, cadangan berupa pertanyaan | 2026-10-05 (16:47, 17:40, 17:51, 17:55), ditegaskan 2026-10-06; **EXEC 2026-10-06** | **EXEC** (lihat bagian EXEC) | 2 |
| 4 | P2: jawaban ditulis sekali | 2026-10-06 | Belum | 4 |
| 5 | P1: mode 4 berhenti setelah analisis + rencana | 2026-10-06 | Belum | 5 |
| 6 | P5: gabung langkah mekanis | 2026-10-06 | Belum | 6 |
| 7 | P4: hasil jelajah dibawa antar-putaran | 2026-10-06 | Belum | 7 |
| 8 | Round 2026-10-03 Fase E: E1 hit rate (M69 tahap 2), E2 ambil sekali beri label (G19 lapis 2) | 2026-10-03 (round disetujui) | Belum; E2 menunggu keputusan 6 | 8 |
| 9 | C06 1a-permanen dan D06 peringatan Telegram | 2026-10-02 | Belum (sisanya sudah live) | 9 |
| 10 | G2-B, S20, minimal 4 hipotesis, analisis faktor | 2026-10-02 (`G2_G3_REACTIVATION_PLAN.md` langkah 8, FINAL) | Belum; 4 keputusan rinci masih terbuka | 10 |
| 11 | P9 kamus nilai dan alat "cari nilai" | Keputusan desain user 2026-10-01 | Belum; perlu cek ulang cakupan | 11 |
| 12 | Prosedur tabel baru (FX, indeks, makro) | 2026-10-01 "record now, run later" | Menunggu pemicu: tabel baru | Saat ada tabel baru |

Biaya model: butir 1 (ulang uji ±USD 0,07) dan setiap golden test sesudah butir 2–7. Sisa kredit OpenRouter terakhir
±USD 0,7, jadi kredit dicek sebelum uji apa pun.

Status **EXEC** = user sudah menyetujui eksekusi; dijalankan hari ini atau saat kuota siap, tanpa meminta izin lagi
untuk langkah di dalamnya. Berhenti dan lapor bila menemui kondisi berhenti, atau bila perlu tindakan di luar langkah ini.

## EXEC (disetujui 2026-10-06: "1 dan 3 … EXEC")

Urutan: EXEC-1, lalu EXEC-3. EXEC-3 dibangun di atas `main` yang sudah memuat EXEC-1.

### EXEC-1: sisa item 10 dan 12 (butir 1)

| Langkah | Isi | Biaya | Lulus bila |
|---|---|---|---|
| 0 | Pra-cek: kredit OpenRouter (dibaca di proses, kunci tidak dicetak); Railway dev (tidak ada golden test atau job berjalan); cabang = `origin`; `main` bisa fast-forward | 0 | Kredit ≥ USD 0,30; tidak ada run berjalan |
| 1 | Tes lokal: suite orc dan web-governor; `git diff --check` | 0 | Hijau |
| 2 | Push `main` (fast-forward ke cabang kerja: `7eda0b7`, `d675404`, dokumen). Orc dan web-governor auto-deploy | 0 | Kedua deployment SUCCESS; log start bersih (`ai_provider_policy` OK, tanpa `web_research_inactive`); `railway config plan` up to date |
| 3 | Uji asap route web: 1 kasus (`bi_rate`) lewat `web-governor-test-runner` fase `orc_web` | ±USD 0,02 | `currency` berupa kode ISO, `unit_code`, tanggal ISO, tanpa `DATE_NOT_ISO` |
| 4 | Ulang uji `threshold_from_result` (3 giliran), suite `qa_20261006c`, prefix `ma-qa-20261006c` | ±USD 0,07 | Giliran 2 = rencana dengan efek minimal dari hasil sebelumnya (tidak LIMITED); giliran 3 menjalankan riset |
| 5 | Laporan `GT_QA_2026-10-06.md` (non-dev): kriteria lulus rencana item 10/12, analisis waktu, ulang uji langkah 4; prosedur 5 langkah per temuan, termasuk praktik terbaik online dan perbandingannya | 0 | Setiap temuan punya akar masalah dari log, usulan, risiko, pembanding online dan solusi final |
| 6 | Catatan: status P35, P36, P37, M83, W24, W26; 11 entri temuan baru (lihat butir 1 langkah 5); `RAILWAY_CHANGELOG.md`, `DATABASE_CHANGELOG.md`, `OUTSTANDING_ISSUES.md`; butir 1 dihapus dari `PLAN.md`. Commit, push `main` dan cabang, cek sama dengan `origin` | 0 | Push sukses |

**Kondisi berhenti:**
- **Deploy tidak SUCCESS:** redeploy deployment sebelumnya (orc `96726ca5`, web-governor `7ca3067e`), lalu lapor.
- **Kredit kurang:** berhenti sebelum langkah 3.
- **Ulang uji gagal:** dicatat dan dilaporkan. Perbaikan kode di luar langkah ini menunggu izin.

### EXEC-3: item 11 penyortir "free will" + TANYA BALIK (butir 3, termasuk P3b)

| Langkah | Isi | Biaya | Lulus bila |
|---|---|---|---|
| 0 | Patokan: `scripts/benchmark_first_router.py` dan `benchmark_turn_router.py` dengan kode sekarang | ±USD 0,03 | Angka patokan tercatat |
| 1 | Set berlabel, ditulis **sebelum** kode dijalankan. Pesan pertama: ≥ 8 harus-tanya ("BBRI", "BBCA", "analisis BBRI", "strategi ini bagus nggak?" tanpa strategi, …) dan ≥ 8 tidak-boleh-tanya (bakrie, q7, h_add, threshold, p2, …), dibagi pengembangan dan uji tersembunyi. Pesan lanjutan: ≥ 4 harus-tanya | 0 | — |
| 2 | Kode orc di balik saklar baru `AI_ENABLE_ASK_BACK` (default mati). Rincian di bawah tabel | 0 | — |
| 3 | Tes unit + suite orc; `AI_ROUTER.md` dan `AI_MODELS.md` diregenerasi (skema keluaran berubah) | 0 | Hijau; tes drift lulus |
| 4 | Benchmark ulang dengan saklar menyala (lokal, model asli) | ±USD 0,03 | 0 pertanyaan data dirutekan ke CHAT/FACT; harus-tanya ≥ 90% ditanya; tidak-boleh-tanya 0 ditanya; akurasi rute lain tidak di bawah patokan |
| 5 | Push `main` → orc deploy SUCCESS; `AI_ENABLE_ASK_BACK=true` di dev (satu perubahan variabel); `railway config pull --force` + `config plan`; `RAILWAY_CHANGELOG.md` | 0 | SUCCESS; log start bersih |
| 6 | Uji live kecil: "BBRI" dan pilihan ① ringkasan cepat; satu kasus cadangan gagal disimulasikan di tes, tidak live | ±USD 0,05 | "BBRI" mendapat pertanyaan ≤ 15 dtk; pilihan ① menghasilkan ringkasan dengan cakupan sesuai maksud |
| 7 | Catatan: entri ERRORS untuk perubahan penyortir, R34 tetap; README orc; butir 3 dan P3b dihapus dari `PLAN.md`. Commit, push `main` dan cabang | 0 | Push sukses |

**Rincian kode langkah 2** (`apps/market-ai-orc/app/conversation_router.py`, `orchestrator.py`, `mode4.py`,
`schemas.py`, `main.py`):
- **Penyortir pesan pertama:**
  - jalur ASK_BACK dengan kriteria (a)–(c);
  - daftar kemampuan dibuat dari tabel jalur di kode;
  - aturan "ambigu + data → ANALYSIS" dicabut;
  - keluaran `understood_intent`, `assumptions`, `question`, `options`;
  - ASK_BACK menjawab langsung CLARIFICATION tanpa run analisis;
  - `understood_intent` dikirim ke langkah analisis sebagai catatan aplikasi.
- **Penyortir pesan lanjutan:** kelas ASK_BACK.
- **Cadangan gagal teknis** (pesan pertama dan lanjutan): coba ulang sekali, lalu pertanyaan baku tanpa model.
- **Pilihan:** setiap pilihan memetakan ke jalur.
  - ① ringkasan cepat = ANALYSIS dengan maksud "ringkasan singkat" dan cakupan terbatas;
  - ② analisis data = ANALYSIS;
  - ③ uji/riset = RESEARCH.

  Balasan teks bebas tetap lewat penyortir.
- **P3b:** pembaca balasan rencana non-mode-4 mengembalikan `design_value_changes` dan `referent`, lalu mengisi
  `current_design_changes` / `current_turn_referent`.

**Kondisi berhenti dan jalan balik:**
- Benchmark langkah 4 tidak lulus: berhenti, lapor, tidak deploy.
- Masalah setelah live: `AI_ENABLE_ASK_BACK=false` (satu perubahan variabel, kode tetap).

---

## 1. Sisa item 10 dan 12

**Asal:** rencana implementasi item 10 dan 12 (disetujui "gas" 2026-10-05), langkah 5–6, dan penyeragaman format web
("Ok tambahkan" 2026-10-06). Prosedur masalah 5 langkah (user 2026-10-05).

**Yang belum:**
1. **Push dan deploy:**
   - Push `main` dengan `7eda0b7` (10.6: alamat di jawaban rencana dirender sebelum gerbang rencana) dan `d675404`
     (mata uang ISO, kode satuan, tanggal ISO di route web orc).
   - Push itu me-redeploy orc dan web-governor di dev; keduanya ditunggu sampai SUCCESS.
2. **Ulang uji item `threshold_from_result`** (±USD 0,07). Target: giliran 2 tidak LIMITED, dan "setuju, jalankan"
   menjalankan riset.
3. **Laporan `GT_QA_2026-10-06.md` (bahasa non-dev).** Hasil dicocokkan dengan kriteria lulus rencana:
   - penolakan REFERENCE/PROVENANCE/EVIDENCE dibanding 14 di `ma-qa-20261005b`;
   - h_add mengutip median dan tingkat keyakinan lewat alamat;
   - bakrie ≤ 3 panggilan web;
   - deret q7 berlabel "fakta web";
   - item ambang lolos;
   - kenaikan token masukan;
   - analisis waktu (golden test 06b: 4.096 dtk waktu model, 177 panggilan).
4. **Prosedur 5 langkah untuk setiap temuan golden test 06b:**
   1. log pikiran AI;
   2. usulan;
   3. risiko dan mitigasi;
   4. praktik terbaik online;
   5. perbandingan dan solusi final.

   Langkah 3–4 belum dijalankan untuk temuan mana pun.
5. **Catatan wajib:**
   - status P35, P36, P37, M83, W24 dan W26 diperbarui dengan bukti live;
   - entri baru untuk temuan 2026-10-06:
     - EVIDENCE langsung LIMITATION di langkah riset (`tool_not_in_step`);
     - kirim ulang jawaban utuh demi catatan;
     - edit tidak bisa mengubah field rencana bersarang;
     - pesan galat JSON yang menyesatkan;
     - 4 penolakan `query_metric` menutup alat;
     - `get_evidence` semua-atau-tidak;
     - aturan LAST di Governor dengan filter satu nilai;
     - PLAN_HORIZON di luar mode 4 (Temuan B);
     - catatan menu alamat menyebut alat yang tidak ada;
     - rantai mode 4 selama 34 menit;
     - angka web tidak dicek di dalam kutipan;
   - `RAILWAY_CHANGELOG.md` dan `DATABASE_CHANGELOG.md`.

---

## 2. P3: gerbang yang salah tolak

**Asal:** analisis waktu golden test 06b. Disetujui masuk rencana 2026-10-06.

- **a. Deploy 10.6 dan format web:** butir 1 langkah 1.
- **b. PLAN_HORIZON di jalur non-mode-4:**
  - Pembaca balasan rencana (`_classify_reply` di `apps/market-ai-orc/app/orchestrator.py`, `CLASSIFIER_SCHEMA`)
    mengembalikan juga `design_value_changes` (skema M82 di `conversation_router.py`) dan mengisi
    `current_design_changes`.
  - Ia juga mengisi `current_turn_referent`, supaya `CITED_THRESHOLD_HINT` muncul di jalur ini.
  - Tetap satu panggilan, tanpa tambahan waktu.
  - Bukti: h_add giliran 2 LIMITED, karena "tambahkan horizon 10 hari, tetap uji 3 hari" dibaca sebagai mengganti.
- **c. Gerbang hanya meminta alat yang ada di langkah itu:**
  - `_approve_v2` (langkah riset disetujui, 13 alat) ditambah `get_evidence` dan `check_references`.
  - `plan_tools` (langkah rencana, 9 alat) ditambah `check_references`.
  - Catatan menu alamat hanya menyebut `check_references` bila alat itu tersedia.
  - Bukti: q7-m4c dipaksa LIMITATION setelah 580 dtk.
- **d. JSON jawaban akhir:**
  - Karakter kontrol mentah sudah diterima sejak M40.
  - Bila parser longgar juga gagal, model diberi galat parser longgar (penyebab sebenarnya), bukan galat "control
    character" dari parser ketat.
  - Draf q7-m4c dicek dulu di audit store.
- **Tes:**
  - `tests/test_plan_*`, `tests/test_address_menu.py`, tes jawaban akhir;
  - suite orc hijau;
  - AI_TOOLS.md diregenerasi bila deskripsi alat berubah.

## 3. Item 11: penyortir "free will", jalur TANYA BALIK, cadangan berupa pertanyaan

**Persetujuan user:**
- 2026-10-05 16:47: "harusnya ada [jalur tanya balik] kan?" dan "gagal → should fall back to question?"
- 17:40: "BBRI" tanya balik maupun ringkasan + pilihan "both alright"; cadangan "coba ulang, lalu pertanyaan baku"
  "ok".
- 17:51: instruksi penyortir untuk memahami maksud user, bukan profil per user.
- 17:55: "Saya setuju in general".
- 2026-10-06: "kalau ambigu maka pilih clarify".

Ini menggantikan keputusan 2026-10-04 "bila ambigu cukup dinyatakan, tidak perlu jalur baru" untuk penyortir.

**Bukti (golden test 06b, orc `96726ca5`):**
- "BBRI" dirutekan ANALYSIS dengan alasan "ambiguous but market-data related, so prefer ANALYSIS".
- Asisten menulis "extremely ambiguous" tetapi lanjut, karena aturan umum no. 9–10.
- 4 penolakan `query_metric` menutup alat itu.
- Cakupan melebar: 48 bank, nama broker.
- Hasilnya 28 panggilan, 569 dtk.

**Perubahan:**
- **Penyortir pesan pertama** (`apps/market-ai-orc/app/conversation_router.py`: `FIRST_ROUTES`,
  `FIRST_INSTRUCTIONS`, `FIRST_SCHEMA`, `FirstRoute`, `first_route_path`, `FIRST_FALLBACK`):
  - Daftar kemampuan tiap jalur dibuat dari kode: apa yang bisa, perkiraan waktu dan biaya, kapan cocok, contoh.
  - Instruksi utama: pahami dulu apa yang sebenarnya user mau.
  - Jalur baru **ASK_BACK**, dipakai bila:
    - (a) tidak ada permintaan yang bisa dikenali (ticker saja, nama saja, satu kata);
    - (b) ada dua tafsiran atau lebih yang menghasilkan pekerjaan sangat berbeda;
    - (c) pesan akan masuk jalur mahal (RESEARCH/EXPLORE) padahal informasi kuncinya tidak ada dan tidak bisa
      diasumsikan.

    Hasilnya satu pertanyaan dengan 3–4 pilihan cepat, tanpa run analisis.
  - Aturan "ambigu + data → ANALYSIS" dicabut. Ambigu dan tebakan salah mahal → ASK_BACK. Ambigu tapi murah → pilih
    jalur dengan asumsi yang dinyatakan.
  - Keluaran ditambah `understood_intent`, `assumptions`, `question` dan `options`. `understood_intent` diteruskan
    ke langkah analisis supaya cakupan tidak melebar.
- **Penyortir pesan lanjutan** (`ROUTER_INSTRUCTIONS`, `TURN_KINDS`): kelas ASK_BACK dengan aturan yang sama.
- **Cadangan gagal teknis**, menggantikan `FIRST_FALLBACK = "ANALYSIS"` dan `FALLBACK = "INSIGHT"`:
  - coba ulang sekali;
  - bila masih gagal, pertanyaan baku tanpa model. Pesan pertama: "① ringkasan cepat ② analisis data ③ uji/riset".
    Pesan lanjutan: "① jelaskan hasil tadi ② analisis lanjutan ③ setujui usulan" (③ hanya bila ada usulan menunggu).
- **Respons API:** CLARIFICATION dengan `options` yang masing-masing memetakan ke jalur. Pilihan yang dikirim sebagai
  jalur langsung menentukan jalan; teks bebas tetap lewat penyortir. Berkas: `schemas.py`, `main.py`, `mode4.py`.
- **Satu pembaca maksud untuk semua jalur:** sama dengan P3b.

**Tes dan dokumen:**
- `tests/test_first_message_router.py`, `tests/test_conversation_router.py`, `tests/test_ai_router_doc.py`.
- Set berlabel (`tests/fixtures/first_message_router_cases.json`, `turn_router_cases.json`) ditambah kasus:
  - perlu tanya: "BBRI", "analisis BBRI", "strategi ini bagus nggak?" tanpa strategi;
  - tidak perlu tanya: bakrie, q7, h_add, threshold, p2 (bertanya berlebihan juga dihitung salah).
- Benchmark router live dijalankan ulang sebelum deploy.
- `AI_ROUTER.md` diregenerasi; `AI_MODELS.md` bila keluaran atau token penyortir berubah.

**Target:**
- "BBRI" mendapat pertanyaan ≤ 15 dtk.
- Pertanyaan jelas tidak pernah ditanya balik.
- Gagal teknis menghasilkan pertanyaan baku.

## 4. P2: jawaban ditulis sekali

**Bukti:**
- 41% waktu model golden test 06b habis untuk menulis dan menulis ulang jawaban akhir.
- Penolakan rencana selalu memaksa tulis ulang penuh (±400 dtk dan 3 giliran terbuang).

**Perubahan:**
- **a.** `ADDRESS_MENU_NOTE` tidak lagi mendorong `check_references` sebelum menulis.
  - Gerbang REFERENCE sudah mendaftar semua alamat salah sekaligus beserta pengganti terdekat (10.3).
  - Alatnya tetap ada sebagai opsi.
- **b. Edit untuk field bersarang:** `edit_repair.apply` menerima `"set": {"research_plan.angles[0].min_effect":
  null}`.
- **c. `GATE_ONCE_NOTE`:** model cukup membalas `{"keep": true}`; backend mengirim draf tersimpan beserta catatannya.
  Contoh biaya sekarang: h_add t2 mengirim ulang 8.660 token selama 109 dtk.
- **d. Edit gagal:**
  - satu kesempatan edit lagi dengan penyebab persisnya;
  - `"all": true` pada teks biasa diperlakukan sebagai `count` = jumlah kemunculan.
- **e. Jawaban lebih ringkas:** target panjang di aturan jawaban akhir, diukur di golden test. Draf terpanjang
  sekarang 10–17 ribu karakter.

**Berkas dan tes:**
- `orchestrator.py` (`ADDRESS_MENU_NOTE`, `GATE_ONCE_NOTE`, `_offer_edit`, `_apply_edit`);
- `edit_repair.py`;
- tes edit repair, `tests/test_prompt_pass2.py` (ADDED/REMOVED).

## 5. P1: mode 4 berhenti setelah analisis + rencana

**Bukti:** q7 giliran 1 makan 34 menit (analisis 759 dtk, rencana 350 dtk, riset otomatis 580 dtk, rencana lanjutan
250 dtk), atau 48% waktu model golden test 06b.

Perubahan ini mengganti perilaku keputusan 2026-09-30 / 2026-10-02 (riset pertama langsung jalan), dan sudah
disetujui masuk rencana.

**Perubahan:**
- `apps/market-ai-orc/app/mode4.py` `first_round`: setelah A (m4a) dan B (m4b), selesai dengan rencana B sebagai
  usulan menunggu (AWAITING_CONFIRMATION). C dan D tidak jalan otomatis.
- APPROVE menjalankan rencana (C). D hanya bila user meminta (`requested_count` SUGGESTION atau giliran CONTINUE).
- Teks yang ikut diperbarui:
  - `FIRST_ROUTES["EXPLORE"]` dan `FIRST_ROUTE_RULES` di `conversation_router.py`;
  - docstring `mode4.py`;
  - `AI_ROUTER.md` diregenerasi dan benchmark router diulang.
- **Tes:** `tests/test_mode4*.py`.
- **Perkiraan:** q7 giliran 1 dari ±34 menjadi ±12–18 menit.

## 6. P5: gabung langkah mekanis

- Setelah `submit_data_need_spec` diterima, backend langsung menjalankan `prepare_data_bundle` dan
  `open_analysis_session`, lalu mengembalikan hasil gabungan. Alat lama tetap ada untuk mengulang.
- `run_python` mendapat argumen `complete` (boolean): setelah kode sukses, backend menjalankan `complete_analysis`.
- **Berkas:**
  - `apps/market-ai-orc/app/tools/data_need.py`, `data_planner.py`, `session.py`;
  - `orchestrator._handle_call`;
  - `AI_TOOLS.md`;
  - migration Tool_Catalog round berikutnya;
  - tes.
- **Perkiraan:** 3–5 panggilan model lebih sedikit per analisis. Ongkos tetap ±3,6 dtk per panggilan, dan golden
  test 06b punya 52 panggilan kecil rata-rata 6 dtk.

## 7. P4: hasil jelajah dibawa antar-putaran

- Ringkasan katalog yang sudah dibaca (tabel, kolom, relasi, cakupan) dan panduan metode yang sudah dibuka disimpan
  di data record percakapan (`data_record.py`).
- Ringkasan itu diberikan ke putaran berikutnya (sub-run mode 4 dan giliran berikutnya) sebagai catatan aplikasi
  setelah prefix statis, supaya cache prompt tidak pecah.
- **Berkas:** `mode4.py` (`sub`), `orchestrator.py`, `data_record.py`, `tools/catalog.py`, `tools/method_guides.py`.
- **Bukti:** q7-m4b membaca ulang katalog dan 5 panduan (±170 dtk). Fakta yang sama ("Feature_01 punya sektor")
  ditemukan ulang di tiga item.

**Verifikasi butir 2–7:**
- suite orc, sandbox dan Governor hijau;
- golden test ulang 6 item 06b, dengan target:
  - q7 giliran 1 ≤ 15 menit;
  - waktu tindak lanjut penolakan ≤ 5% waktu model (sekarang 18%);
  - nol `tool_not_in_step`;
  - h_add t2 dan threshold t2/t3 lolos;
  - median panggilan per putaran turun ≥ 30%;
  - "BBRI" ditanya balik.

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

---

## Sudah dieksekusi, tinggal bukti live

Bukan rencana lagi; daftar dan statusnya ada di `OUTSTANDING_ISSUES.md` ("Sudah diperbaiki, hanya menunggu golden
test") dan `ERRORS_AND_SOLUTIONS.md`. Contoh: G19 lapis 1 dan 3, M69 tahap 1, M70, S28, S29 (R-STORE), C06 1b, S22.

## Audit dokumen rencana (2026-10-06)

| Dokumen | Hasil audit |
|---|---|
| `PLAN_2026-10-05.md` | Item 1–10 dan 12 dieksekusi (golden test 06b); sisa item 10/12 → butir 1; item 11 → butir 3 |
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
