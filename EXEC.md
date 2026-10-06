# EXEC: eksekusi yang sudah disetujui

Setiap eksekusi yang isinya disetujui user ada di sini, satu bagian per eksekusi, dengan rinciannya langsung di
bawahnya (keputusan user 2026-10-06: "EXEC itu harusnya jadi 1 file dengan setiap execution yang berbeda …
gabungkan ya", pilihan "File baru EXEC.md"). Pekerjaan yang disetujui tetapi belum punya rencana eksekusi ada di
`PLAN.md`; usulan dan keputusan terbuka di `FUTURE_PLAN.md`. Kode masalah merujuk ke `ERRORS_AND_SOLUTIONS.md`.

## Keputusan 2026-10-06 untuk menjalankan

- "kita jalankan setiap EXEC + GT yang memang diperlukan", lalu "mulai" (konfirmasi mulai).
- Kredit: "Jalan dengan USD 1,59" (sisa batas kunci OpenRouter); berhenti dan lapor bila sisa < USD 0,30 sebelum
  sebuah uji.
- Antar gelombang: "Lanjut otomatis bila lulus"; berhenti dan lapor hanya pada kondisi berhenti.
- EXEC-C: Q1 "pakai MEMO", Q2 "BACKEND + AI".
- Varian nilai desain dan koreksi uji berganda (lintas varian dan lintas giliran) dilebur ke EXEC-3 dan EXEC-A
  (pilihan "2+5 Varian + koreksi", "Lebur ke EXEC-3 dan EXEC-A"). Usulan multi-tugas lain ke `FUTURE_PLAN.md`.
- 2026-10-06, sesudah gelombang 2 (target waktu sesudah penolakan ≤ 5% tidak tercapai, 20,5%): pilihan user "Lanjut
  gelombang 3 (Recommended)"; target 5% diukur ulang setelah M90 diperbaiki.
- Gelombang: 1 = EXEC-1 + EXEC-S; 2 = EXEC-E + EXEC-R + EXEC-P2; 3 = EXEC-3 + EXEC-A + EXEC-T; 4 = EXEC-C +
  EXEC-P5 + EXEC-P1, lalu golden test akhir.

## Ringkasan

**Selesai 2026-10-06:**
- EXEC-1 (sisa item 10 dan 12, menu alamat lengkap 1b) dan EXEC-S (satu `session_id` per percakapan), terverifikasi
  live; status di `ERRORS_AND_SOLUTIONS.md` (P35–P38, M96, R35, W26).
- Gelombang 2: EXEC-E (`get_evidence` dihapus), EXEC-R (R1–R5) dan EXEC-P2 (P2a, P2e), live di dev (orc `8740079c`);
  ulang uji `ma-qa-20261006e`: semua giliran selesai, tanpa gerbang EVIDENCE, tanpa angka tanpa sumber yang lolos.
  Target waktu sesudah penolakan ≤ 5% **tidak tercapai** (20,5%; 06b 26,8%). Sebab terbesar: M90 (EXEC-3/EXEC-A) dan
  jalur 10.6. Status di `ERRORS_AND_SOLUTIONS.md` (M84–M89, M91, P39, S23, G20, G21).
- Perbedaan dari kata-kata rencana gelombang 2 (R35):
  - P2e: target ±2.500 karakter ditulis ke model dalam kata-kata, bukan angka (prompt adalah sumber angka; tes pass 2
    melarang digit baru). Target 1.500 per bagian mode 4 hanya diukur lewat log, tidak dikirim ke model.
  - R1: `set` boleh mengisi field terakhir yang tidak ada di draf (field opsional). Cek skema penuh sesudahnya yang
    memutuskan.
  - R4b: kesempatan edit kedua diberikan sekali per draf dan tidak dihitung sebagai penolakan.
  - Commit: satu commit kode gelombang 2 (`6c6ce58`), bukan satu per EXEC.
  - EXEC-E langkah 5 menyebut uji ulang 2 item; dijalankan 3 item (lang, threshold, h_add) bersama EXEC-R.
- Laporan `GT_QA_2026-10-06.md` §6–7, deploy di `RAILWAY_CHANGELOG.md`.

| No | Butir | Disetujui | Status | Urutan usulan |
|---|---|---|---|---|
| 1d | EXEC-C: AI membawa semuanya ke run ID berikutnya dalam satu percakapan, tanpa terkecuali (13 butir, termasuk P4) | 2026-10-06 ("masukan exec"; "Seharusnya AI membawa semuanya tanpa terkecuali. Masukan EXEC") | **EXEC**, berjalan ("mulai" 2026-10-06); Q1 memo, Q2 backend + AI (diputuskan 2026-10-06) | Sesudah EXEC-R |
| 1e | EXEC-A: penyelarasan jalur (satu pembaca maksud, gerbang hanya meminta alat yang ada, 10.6 dan edit sama di semua jalur) | 2026-10-06 ("masukan exec") | **EXEC**, berjalan ("mulai" 2026-10-06) | Bersama EXEC-3 |
| 1h | EXEC-P1: mode 4 berhenti setelah analisis + rencana | 2026-10-06 ("p1 … masukan exec") | **EXEC**, berjalan ("mulai" 2026-10-06) | Sesudah EXEC-3 |
| 1i | EXEC-P5: gabung langkah mekanis | 2026-10-06 ("p5 masukan exec") | **EXEC**, berjalan ("mulai" 2026-10-06) | Sesudah EXEC-R |
| 1j | EXEC-T: perangkat alat per proses (matriks HARUS/BOLEH/TIDAK BOLEH final, alat terlarang dikunci kode dan tidak bisa ditemukan) | 2026-10-06 ("finalize dan masukan ke EXEC"; catatan user: alat TIDAK BOLEH dikunci kode, tidak boleh ditemukan lewat pencarian) | **EXEC**, berjalan ("mulai" 2026-10-06) | Bersama EXEC-A |
| 2 | P3: gerbang yang salah tolak | 2026-10-06 "OK masukan plan jangan execute dulu" | Belum (P3a ikut EXEC butir 1, P3b ikut EXEC butir 3) | 3 |
| 3 | Item 11: penyortir "free will", jalur TANYA BALIK, cadangan berupa pertanyaan | 2026-10-05 (16:47, 17:40, 17:51, 17:55), ditegaskan 2026-10-06; **EXEC 2026-10-06** | **EXEC** (lihat bagian EXEC) | 2 |
| 4 | P2: jawaban ditulis sekali | 2026-10-06 | Selesai 2026-10-06 (EXEC-R dan EXEC-P2, gelombang 2) | — |
| 5 | P1: mode 4 berhenti setelah analisis + rencana | 2026-10-06 | EXEC-P1 | — |
| 6 | P5: gabung langkah mekanis | 2026-10-06 | EXEC-P5 | — |
| 7 | P4: hasil jelajah dibawa antar-putaran | 2026-10-06 | Masuk EXEC-C (butir 1d) | — |

Biaya model: butir 1 (ulang uji ±USD 0,07) dan setiap golden test sesudah butir 2–7. Sisa batas kunci OpenRouter setelah gelombang 2:
±USD 1,16 (2026-10-06; 1,373 sebelum ulang uji `ma-qa-20261006e`, yang memakai ±0,215), jadi kredit dicek sebelum uji
apa pun.
Status **EXEC** = rencana eksekusi sudah disetujui isinya, tetapi **baru dijalankan setelah user memberi konfirmasi
mulai** (keputusan user 2026-10-06: "EXEC dijalankan setelah konfirmasi saya"). Konfirmasi mulai diberikan 2026-10-06 ("mulai"). Setelah dimulai, berhenti dan lapor bila menemui kondisi berhenti, atau bila perlu tindakan di
luar langkah ini.

Urutan: EXEC-1, lalu EXEC-3. EXEC-3 dibangun di atas `main` yang sudah memuat EXEC-1.

---

### EXEC-3: item 11 penyortir "free will" + TANYA BALIK (butir 3, termasuk P3b)

| Langkah | Isi | Biaya | Lulus bila |
|---|---|---|---|
| 0 | Patokan: `scripts/benchmark_first_router.py` dan `benchmark_turn_router.py` dengan kode sekarang | ±USD 0,03 | Angka patokan tercatat |
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

#### Rincian dari butir 3 (dipindah dari `PLAN.md` 2026-10-06)

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

---

### EXEC-A: penyelarasan jalur (butir 1e)

**Masalah:** aturan yang sama berbeda antar-jalur. Contohnya:
- bacaan "tambah/ganti" hanya di mode 4 (h_add t2 LIMITED);
- gerbang EVIDENCE meminta `get_evidence` di langkah riset yang tidak punya alat itu (q7-m4c LIMITATION setelah
  580 dtk);
- catatan menu alamat menyebut `check_references` di langkah tanpa alat itu;
- 10.6 dan edit tidak berlaku sama di semua jalur.

**Perubahan:**
1. **Satu pembaca maksud untuk semua jalur.** Penyortir pesan pertama, penyortir mode 4 dan pembaca balasan rencana
   menghasilkan keluaran yang sama: `design_value_changes` (tambah/ganti/hapus), `referent` (merujuk hasil
   sebelumnya), dan `understood_intent`. Gerbang membaca keluaran itu di jalur mana pun. Mencakup P3b dan dibangun
   bersama EXEC-3.
2. **Gerbang hanya meminta jalan keluar yang alatnya ada** (mencakup P3c, kini disetujui). Isi perangkat alat per
   proses mengikuti matriks final di EXEC-T:
   - setiap gerbang yang punya `needs` hanya muncul sebagai permintaan bila alatnya ada di meja langkah itu; bila
     tidak ada, alat itu ditambahkan ke meja langkah tersebut;
   - langkah riset disetujui ditambah `check_references` (`get_evidence` dihapus di EXEC-E);
   - langkah rencana ditambah `check_references` dan `get_session_output`, karena rencana harus bisa mengutip hasil
     sebelumnya.
   - **Tes permanen:** gagal bila `needs` sebuah gerbang tidak ada di meja proses tempat gerbang itu bisa muncul, atau
     bila kalimat prompt atau catatan hasil alat menyebut alat yang tidak ada di meja (prinsip P31).
3. **10.6 dan edit berlaku sama di semua jalur.** Alamat dirender di jawaban rencana di semua jalur rencana (PROPOSE,
   REVISE, REPLAN, m4b, m4d). Edit, termasuk field bersarang (R1) dan `keep` (R2), ditawarkan di semua langkah yang
   punya alat. Tes per jalur.

- **Berkas:** `conversation_router.py`, `orchestrator.py` (`_classify_reply`, `_desk`, `_gate_once`, `_approve_v2`,
  `plan_tools`, `ADDRESS_MENU_NOTE`), `mode4.py`, tes baru `tests/test_tool_desks.py`.
- **Lulus bila:**
  - tes meja alat hijau;
  - ulang uji h_add t2 dan q7 tanpa `tool_not_in_step` dan tanpa LIMITED karena "tambah horizon".
- **Catatan:** analisis lengkap "alat per proses" (HARUS / BOLEH / TIDAK BOLEH) yang diminta user belum dijalankan.
  Hasilnya bisa mengubah daftar alat di langkah 2.

#### Rincian dari butir 2 (dipindah dari `PLAN.md` 2026-10-06)

P3a ada di EXEC-1, P3b di EXEC-3, P3c di EXEC-A, P3d di EXEC-R (R4).

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

---

### EXEC-T: perangkat alat per proses (butir 1j)

**Aturan user (2026-10-06):** alat yang TIDAK BOLEH ada di sebuah proses dikunci oleh kode, dan tidak boleh bisa
ditemukan lewat pencarian. Contohnya alat ambil data sebelum rencana disetujui.

**Hasil cek ulang di kode (2026-10-06):**

| Lapisan kunci | Keadaan sekarang |
|---|---|
| 1. Tidak ditawarkan | Perangkat A, B, D, baca-saja, dan fakta disaring kode (`_desk`, `_turn_tools`). Perangkat C (CONTINUE, AUTO tanpa rencana, riset v1 disetujui) tidak disaring sama sekali (`tool_filter=None`): semua 27 alat ditawarkan |
| 2. Ditolak saat dipanggil | `_execute` menolak alat di luar perangkat (`TOOL_NOT_AVAILABLE_IN_THIS_TURN`), tetapi hanya untuk perangkat yang disaring. Perangkat C tidak punya kunci ini. Pesan tolaknya juga selalu menyebut "rencana menunggu keputusan user", walau prosesnya bukan rencana |
| 3. Penjaga khusus | `ResearchGuard`: data mode RESEARCH ditolak sebelum rencana disetujui (terbukti di log: `RESEARCH_PLAN_REQUIRED` 2× di CONTINUE). Alat riset v2 menolak bila tidak ada rencana disetujui (`refused()` di `research_run_executor.py`). Dua alat web saling eksklusif (`config.py`). Alat lama mati bersama DataNeed |
| 4. Tidak bisa ditemukan | **Belum.** Nama alat di luar perangkat terlihat di tiga tempat: (a) `get_system_capabilities` mengembalikan `other_tools_not_in_this_step`; (b) system prompt dibuat sekali per deployment dari semua alat terdaftar, jadi menyebut alat yang tidak ada di langkah itu; (c) buku panduan metode menyebut alat (misalnya `get_evidence`) di langkah mana pun |

**Matriks final** (H = harus ada, B = boleh, X = tidak boleh karena melanggar kontrak; ⚠ = beda dari sekarang):

| Alat | CHAT | FACT | CLARIFY / CONVERSATIONAL | Analisis (pesan pertama, m4a, INSIGHT) | Rencana (PROPOSE, REVISE, REPLAN, m4b, m4d) | CONTINUE | Riset v1 disetujui | Riset v2 disetujui |
|---|---|---|---|---|---|---|---|---|
| `get_system_capabilities` | B | B | B | B | B | B | B | B |
| Jelajah katalog (discover, details, rows, dimension) | B | H | B | H | H | H | B | B |
| `lookup_reference` | B | H | B | H | B | H | B | B |
| `get_method_guide` | B | B | B | H | H | H | H | H |
| `preview_table_rows` | X | X | X | B | X | B | B | X |
| `query_metric` | X | X | X | H | X | B | B | X |
| Alur data (submit, bundle, sesi, `run_python`, complete) | X | X | X | H | X | B (mode RESEARCH dikunci `ResearchGuard`) | H | X |
| `inspect_session` | B | B | B | H | B | H | H | H |
| `get_session_output` | B | B | H | H | **H ⚠** | H | H | H |
| `export_result` | B | B | H | B | B | B | B | B |
| `get_lineage` | B | B | H | B | B | B | B | B |
| `check_references` | B | B | H | B | **H ⚠** | B | B | **H ⚠** |
| Cek kelayakan rencana | X | X | X | X | H | H | B | B |
| `get_research_library` | B | B | B | B | H | H | B | H |
| Alat riset v2 (start, run, complete) | X | X | X | X | X | **X ⚠** | **X ⚠** | H |
| `research_web` | B | H | B | B | B | B | B | B |
| Alat baca memori percakapan (baru, EXEC-C) | **H ⚠** | **H ⚠** | **H ⚠** | **H ⚠** | **H ⚠** | **H ⚠** | **H ⚠** | **H ⚠** |
| `find_web_fact` (selama `research_web` aktif) | X | X | X | X | X | X | X | X |
| `get_evidence` (EXEC-E) | **X ⚠** | **X ⚠** | **X ⚠** | **X ⚠** | X | **X ⚠** | **X ⚠** | X |
| Alat jalur lama (sebelum DataNeed) | X | X | X | X | X | X | X | X |

Alasan X:
- **Rencana:** ambil atau hitung data sebelum disetujui.
- **Giliran baca saja dan FACT:** menghitung ulang dengan cakupan lain (M63) dan mengambil data gudang.
- **Analisis:** pemanggil menetapkan tanpa rencana.
- **Riset v2:** AI tidak boleh menyusun ulang pesanan data atau menjalankan kode bebas di luar executor.
- **Alat riset v2 tanpa rencana v2 yang disetujui.**
- **Dua alat web sekaligus.**
- **`get_evidence`:** dihapus atas keputusan user.

Tambahan dari EXEC-C (2026-10-06): karena semua sumber run sebelumnya didaftarkan ulang di awal run, mengutip output giliran lalu tidak lagi bergantung pada `get_session_output`. Catatan data record dan memo hanya menyebut alat yang ada di perangkat langkah itu.

B tidak berarti wajib ditawarkan. Perangkat tiap proses = semua H ditambah B yang dipilih di tabel `DESKS`, dengan
biaya token dicatat.

**Perubahan:**
1. **Satu sumber kebenaran:** tabel `DESKS` di kode. Isinya per proses: daftar H, daftar B yang ditawarkan, dan daftar
   X. `_desk`, `_turn_tools`, `plan_tools`, `_approve_v2`, `_apply_turn_kind` dan saringan `forced_path` membaca tabel
   itu. Perangkat C tidak lagi `None`:
   - CONTINUE memakai perangkat sesuai maksud dari penyortir (analisis, rencana, atau baca), dibangun bersama EXEC-3;
   - riset v1 mendapat perangkatnya sendiri.
2. **Kunci kode berlapis untuk setiap X:**
   - (a) tidak ditawarkan;
   - (b) ditolak saat dipanggil di semua proses, termasuk yang dulu tanpa saringan, dengan pesan yang benar ("tidak
     tersedia di langkah ini", tanpa daftar alat terlarang);
   - (c) penjaga khusus tetap ada sebagai lapis kedua (`ResearchGuard`, executor riset, saklar eksklusif web).
3. **Tidak bisa ditemukan:**
   - `get_system_capabilities` hanya menyebut alat di perangkat langkah itu. `other_tools_not_in_this_step` dihapus;
     yang tersisa hanya label kemampuan yang tidak tersedia.
   - Kalimat system prompt yang menyebut alat tertentu dipindah ke deskripsi alat itu atau ke catatan per langkah,
     sehingga prefix statis tidak menyebut alat yang tidak ada (P31 per langkah). Kenaikan token diukur; `test_prompt_pass2.py` diperbarui.
   - `get_method_guide` mengembalikan teks panduan dengan nama alat di luar perangkat disaring.
   - Bila nanti memakai pencarian alat (`defer_loading` / tool search): indeks dibangun hanya dari perangkat langkah
     itu, sehingga alat X tidak pernah terindeks. Aturan ini dicatat di AGENTS.md.
4. **Tes permanen** (`tests/test_tool_desks.py`):
   - setiap gerbang dengan `needs` hanya bisa muncul di proses yang perangkatnya memuat alat itu;
   - tidak ada alat X di perangkat yang ditawarkan;
   - memanggil alat X ditolak di setiap proses;
   - jawaban `get_system_capabilities`, system prompt, catatan hasil alat dan buku panduan tidak menyebut alat di luar
     perangkat;
   - `AI_TOOLS.md` memuat matriks yang dibuat dari `DESKS` (generator), dan tes drift gagal bila berbeda.

- **Berkas:**
  - `orchestrator.py`, `conversation_router.py`, `mode4.py`;
  - `tools/system.py`, `tools/registry.py`, `tools/method_guides.py`;
  - `scripts/generate_ai_tools_doc.py`;
  - AGENTS.md (aturan perangkat dan pencarian alat).
- **Lulus bila:**
  - tes hijau;
  - ulang uji q7 dan h_add tanpa `tool_not_in_step`;
  - tidak ada panggilan alat X di log;
  - log pikiran tidak menyebut alat di luar perangkat.

---

### EXEC-C: AI membawa semuanya ke run berikutnya, tanpa terkecuali (butir 1d, mencakup P4)

**Keputusan user (2026-10-06):**
- "masukan exec" (memo run setelah LIMITED / giliran baru);
- "Okay ini salah... Seharusnya AI membawa semuanya tanpa terkecuali. Masukan EXEC" (tentang pikiran AI, alasan
  penolakan, keputusan desain di luar rencana dan fakta web yang tidak terbawa);
- lalu "what else?", dijawab dengan 9 celah tambahan di bawah.

Keputusan ini menggantikan kalimat lama di butir ini, "pikiran mentah tidak dibawa".

**Lingkup:** setiap run ID baru dalam satu conversation ID menerima semua yang dihasilkan run sebelumnya. Ini berlaku
untuk giliran user berikutnya, sub-run mode 4 (m4a → m4b → m4c → m4d), dan run lanjutan setelah LIMITED.

**Yang dibawa** (13 butir; nomor 1–4 dari daftar awal, 5–13 dari cek ulang kode dan log 2026-10-06):

| # | Hal | Keadaan sekarang (bukti) | Perubahan |
|---|---|---|---|
| 2 | Alasan penolakan | Hanya baris batasan umum bila berakhir LIMITED | Setiap penolakan disimpan: gerbang atau alat, kode, pesan lengkap, bagian draf yang ditolak, dan perbaikan yang dicoba. Galat alat ikut, misalnya `query_metric` butuh tanggal awal+akhir, atau LAST butuh `group_by` |
| 3 | Keputusan desain di luar rencana | Hilang bila tidak masuk rencana | Horizon, ambang, efek minimal, cakupan, definisi dan pilihan AI disimpan beserta asalnya: kata user, hasil sebelumnya (alamat), atau pilihan AI |
| 4 | Fakta web | `web.<id>` tidak masuk data record; hanya kalimat asumsi | Amplop `citable` disimpan dan didaftarkan ulang sebagai sumber `web.<id>` di awal run berikutnya, beserta kutipan dan URL |
| 5 | Catatan data record | Dipotong di 8.000 karakter. Di 05b terjadi pada 11 dari 23 run. Dari q7 giliran 1 ke 2, 13 dari 14 output, 5 sudut riset dan semua temuan tidak terlihat. Di 06b mentok 8.000 di q7 m4c, m4d dan giliran 2 | Tidak ada potongan diam-diam. Output, temuan, jawaban sebelumnya dan keputusan selalu masuk. Bagian referensi panjang (relasi, nilai kategori) diringkas dengan penunjuk ke isi lengkap |
| 6 | Riwayat per pesan | Dipotong 16.000 karakter. Asumsi/Batasan/Metodologi ada di akhir, jadi terbuang lebih dulu. q7 giliran 1 menyimpan 20.450 karakter; 4.450 karakter bagian itu hilang (perbaikan M63 batal untuk mode 4) | Asumsi/Batasan/Metodologi tidak pernah terpotong. Bila perlu memotong, yang dipotong badan jawaban, dengan penunjuk ke teks penuh |
| 7 | Jawaban gabungan mode 4 | Metodologi hanya dari satu bagian; teks rencana m4b tidak ikut; Asumsi dan Batasan dibatasi 20 butir (`_merge`) | Metodologi semua bagian, teks rencana m4b, dan semua asumsi/batasan ikut |
| 8 | Di dalam rantai mode 4 | m4b dan m4d hanya menerima 5.000 karakter pertama analisis, m4d 6.000 karakter pertama riset; asumsi/batasan/metodologi analisis tidak diteruskan | Langkah berikutnya menerima semuanya lewat mekanisme yang sama dengan giliran baru (butir ini), bukan potongan teks |
| 9 | Kode Python run sebelumnya | Tersimpan di `AI_conversation_execution` (sampai 65.536 karakter), tetapi AI hanya melihat hash lewat `get_lineage` | Teks kode bisa dibaca AI dan masuk daftar isi memo |
| 10 | Isi katalog | Hanya nama kolom yang dibawa, tanpa arti, satuan dan peringatan, padahal catatannya berkata "jangan baca katalog lagi" | Arti, satuan dan peringatan kolom yang sudah dibaca ikut dibawa; kalimat catatan diselaraskan |
| 11 | Sumber angka run sebelumnya | Hanya `finding.*` yang otomatis terdaftar. `out.oN` baru bisa dikutip setelah `get_session_output`. `fact`, `metric`, `reference`, `web` dan `analysis` giliran lalu tidak bisa dikutip | Semua sumber run sebelumnya didaftarkan ulang di awal run dengan alamat yang sama, langsung bisa dikutip. Angka tetap dikutip lewat alamat; angka yang diketik ulang dari teks jawaban lama tetap tidak dianggap sumber (aturan gerbang tidak berubah) |
| 12 | Giliran gagal atau terputus | Tidak masuk riwayat sama sekali (riwayat hanya mengambil giliran dengan `assistant_text`) | Masuk riwayat: pesan user, kode galat, dan apa yang sempat dikerjakan |
| 13 | Bacaan penyortir per giliran | Jenis giliran, rujukan, perubahan nilai desain dan maksud (EXEC-3) tidak disimpan | Disimpan di state percakapan dan diberikan ke giliran berikutnya |

**Cara membawa:**
- **Penyimpanan:** satu catatan per run (memori run) di penyimpanan percakapan, berisi butir 1–13 dalam bentuk
  terstruktur, beserta isi lengkapnya (pikiran utuh, pesan penolakan, kode, draf). Masa simpannya sama dengan
  percakapan (30 hari). Tabel atau kolom baru mengikuti workflow AGENTS.md: migration, `DATABASE_SCHEMA.md`, changelog.
- **Masuk prompt:** memo terstruktur per run, ditempatkan setelah prefix statis. Susunannya terlama dulu dan hanya
  bertambah di belakang (append-only), supaya cache prompt antar run bisa terpakai (lihat EXEC-S).
- **Isi lengkap:** bisa dibaca AI kapan saja lewat satu alat baca memori percakapan (READS, tanpa model). Alat itu
  **H di semua perangkat** EXEC-T.
- Hanya penunjuk ke isi lengkap yang boleh menggantikan isi. Tidak ada potongan tanpa penunjuk (aturan P5 diperluas).

**Pertanyaan terbuka:**
- **Q1 (bentuk pikiran AI di prompt):**
  - (a) pikiran utuh dimasukkan ke prompt run berikutnya; atau
  - (b) yang masuk prompt adalah memo, sedangkan pikiran utuh tersimpan dan bisa dibaca lewat alat baca memori.

  Rekomendasi asisten: (b). Alasannya:
  - pikiran lama ikut membawa percobaan yang ditolak dan tebakan yang salah;
  - penyedia model sendiri tidak membawa pikiran antar giliran;
  - biaya bukan penghalang: cache dalam satu run 89%, jadi membawa 98 ribu token ke run 20 panggilan ±USD 0,022.

  **Diputuskan user 2026-10-06: "pakai MEMO" (b).**
- **Q2 (siapa menulis ringkasan pikiran, bila Q1 = b):**
  - fakta (butir 2–13) disusun backend dari kejadian yang tercatat, tanpa panggilan model;
  - ringkasan pikiran ditulis model sebagai satu field catatan di jawaban akhirnya (±200–500 token, tanpa panggilan
    tambahan).

  **Diputuskan user 2026-10-06: "BACKEND + AI".** Bila run berhenti tanpa jawaban akhir, bagian backend tetap
  tertulis.

**Berkas:**
- `data_record.py`, `conversations.py` (`assistant_text`, riwayat), `conversation_plans.py` (state), `mode4.py`
  (`sub`, `first_round`, `suggest`, `_combined_response`, `_merge`), `orchestrator.py` (`_build_input`,
  `_seed_data_record`, `_seed_findings` jadi semua sumber, akhir run), `tools/lineage.py`, `tools/catalog.py`,
  `tools/method_guides.py`;
- alat baca memori baru (+ `AI_TOOLS.md`, Tool_Catalog);
- migration penyimpanan memori.

**Tes:**
- percakapan uji 3 giliran + rantai mode 4: setiap butir 1–13 dari run sebelumnya terlihat atau bisa dibaca di run
  berikutnya;
- tidak ada potongan tanpa penunjuk (catatan data record, riwayat, jawaban gabungan mode 4);
- alamat `out`, `fact`, `metric`, `reference`, `web`, `analysis`, `finding` dari giliran lalu langsung lolos gerbang
  REFERENCE tanpa `get_session_output`;
- giliran gagal muncul di riwayat giliran berikutnya;
- alat baca memori ada di setiap perangkat (`tests/test_tool_desks.py`);
- susunan memo append-only: awalan prompt run N+1 sama persis dengan run N sampai akhir memo run N.

**Lulus bila** di ulang uji threshold (3 giliran) dan q7 (2 giliran):
- panggilan jelajah katalog di run lanjutan turun ≥ 50%;
- token berpikir langkah pertama run lanjutan turun;
- nol penolakan PROVENANCE/REFERENCE untuk angka yang berasal dari giliran sebelumnya;
- giliran 2 q7 menerima Asumsi/Batasan/Metodologi giliran 1 utuh.

#### Rincian dari butir 7 (dipindah dari `PLAN.md` 2026-10-06)

P4 sebagian sudah ada (koreksi 2026-10-06 di EXEC-C).

- Ringkasan katalog yang sudah dibaca (tabel, kolom, relasi, cakupan) dan panduan metode yang sudah dibuka disimpan
  di data record percakapan (`data_record.py`).
- Ringkasan itu diberikan ke putaran berikutnya (sub-run mode 4 dan giliran berikutnya) sebagai catatan aplikasi
  setelah prefix statis, supaya cache prompt tidak pecah.
- **Berkas:** `mode4.py` (`sub`), `orchestrator.py`, `data_record.py`, `tools/catalog.py`, `tools/method_guides.py`.
- **Bukti:** q7-m4b membaca ulang katalog dan 5 panduan (±170 dtk). Fakta yang sama ("Feature_01 punya sektor")
  ditemukan ulang di tiga item.

---

### EXEC-P5: gabung langkah mekanis (butir 1i)

- Rincian di bagian 6 di bawah.
- **Langkah:**
  1. kode `tools/data_need.py`, `data_planner.py`, `session.py`, `orchestrator._handle_call`;
  2. argumen `complete` di `run_python`;
  3. tes;
  4. `AI_TOOLS.md`;
  5. migration Tool_Catalog;
  6. deploy orc;
  7. ulang uji p2 dan threshold t1 (±USD 0,05).
- **Lulus bila:** panggilan model per analisis turun ≥ 3 tanpa kenaikan penolakan.

#### Rincian dari butir 6 (dipindah dari `PLAN.md` 2026-10-06)

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

---

### EXEC-P1: mode 4 berhenti setelah analisis + rencana (butir 1h)

- Rincian di bagian 5 di bawah.
- **Langkah:**
  1. kode `mode4.py` (`first_round`, `follow_up`);
  2. teks EXPLORE di `conversation_router.py`;
  3. `AI_ROUTER.md` diregenerasi dan benchmark router diulang;
  4. tes `test_mode4*`;
  5. deploy orc;
  6. ulang uji q7 giliran 1–2 (±USD 0,15).
- **Lulus bila:**
  - q7 giliran 1 ≤ 15 menit dan berakhir dengan analisis + rencana yang menunggu;
  - "setuju" menjalankan riset;
  - tidak ada rencana lanjutan tanpa diminta.
- **Jalan balik:** revert commit (tanpa saklar), atau saklar `AI_MODE4_AUTO_RESEARCH` (default mati = perilaku baru).
  Usul memakai saklar.

#### Rincian dari butir 5 (dipindah dari `PLAN.md` 2026-10-06)

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

---

## Verifikasi bersama

**Verifikasi butir 2–7:**
- suite orc, sandbox dan Governor hijau;
- golden test ulang 6 item 06b, dengan target:
  - q7 giliran 1 ≤ 15 menit;
  - waktu tindak lanjut penolakan ≤ 5% waktu model (sekarang 18%);
  - nol `tool_not_in_step`;
  - h_add t2 dan threshold t2/t3 lolos;
  - median panggilan per putaran turun ≥ 30%;
  - "BBRI" ditanya balik.
