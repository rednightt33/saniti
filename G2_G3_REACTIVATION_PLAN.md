# Rencana: menghidupkan kembali G2 (event study) dan G3 (uji hipotesis bebas), lalu golden test 5 soal

Status: **FINAL, disetujui user 2026-10-02** ("Great, finalize plan"); belum dijalankan. Tidak ada keputusan terbuka.
Urutan kerja di bagian 8. Dikerjakan di branch `claude/g2-g3-reactivation` (keputusan user 2026-10-02).
Keputusan user 2026-10-02:
- G2 dan G3 dihidupkan kembali;
- keduanya bisa berdiri sendiri atau saling melengkapi;
- yang disesuaikan adalah arsitektur dan kode G2/G3 agar cocok dengan infrastruktur sekarang (DataNeed, sesi
  sandbox, riset multi-angle G4, mode 4);
- sesudahnya golden test 5 soal + satu skenario percakapan;
- G3 jalur rencana terpisah (v1) di samping G4 (v2);
- AI mengetahui alat lewat menu, manual dan contoh yang dibawa sepanjang percakapan (4b);
- percakapan multi-giliran: CLARIFY / INSIGHT (analisis pendorong) / CONTINUE bebas G1–G4, riset hanya bila diminta (4d).

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

## 4. G3: uji hipotesis bebas di infrastruktur sekarang (keputusan user: jalur terpisah)

**Bentuk:** rencana riset **v1** (eksperimen, satu hipotesis per eksperimen) hidup **berdampingan** dengan rencana v2
(G4), sebagai jalur terpisah. Tidak digabung ke `experiments` di v2.

**Yang diubah:**
- **orc:**
  - prompt tidak lagi memilih v1 *atau* v2 lewat satu saklar (`orchestrator.py` ~775); aturan kedua jenis rencana
    tersedia, dan AI memilih jenis rencana sesuai hipotesisnya;
  - alat rencana menerima kedua skema (v1 dan v2) dengan penanda jenis;
  - kelanjutan rencana (persetujuan, revisi) menangani keduanya. `mode4.py` sudah meneruskan kelanjutan non-v2 ke
    orchestrator (~186), yang perlu dicek dan dites;
  - rujukan `finding.<hypothesis_id>` untuk temuan v1.
- **sandbox:** penyelesaian sudah menangani v1 (`dataneed_service.py` ~785) di samping grup v2 (~773). Yang dicek dan
  dites: keduanya aktif bersamaan (`PY_SANDBOX_MULTI_ANGLE_RESEARCH_ENABLED` dan `PY_SANDBOX_RESEARCH_FINDINGS_ENABLED`
  menyala di dev) tanpa saling menolak.
- **Mode 4:** langkah B saat ini selalu membuat rencana v2. Kapan langkah B atau D memakai v1 (G3) mengikuti router
  mode 4 (`MODE4_CONVERSATION_PLAN.md`). Untuk tahap ini, G3 tersedia di mode RESEARCH dan bisa dipilih AI di langkah
  B. Detailnya ditetapkan saat implementasi dan dicatat.

**Isi eksperimen G3** (rencana v1 yang ada, tidak memakai perpustakaan metode):
- hipotesis, tujuan, kondisi, outcome, pembanding (teks bebas);
- arah yang diharapkan, horizon, satuan outcome, efek minimum, definisi sukses, kebijakan koreksi, holdout opsional;
- anggaran Research Governor: maksimal 4 hipotesis, 6 eksperimen, 5 tindak lanjut per hipotesis (kebijakan
  `PY_SANDBOX_RESEARCH_MAX_*`).

**Eksekusi:**
- AI membangun event dan pembanding dengan Python bebas, atau dari tabel event G2.
- AI memanggil `saniti.event_summary(...)`.
- Harness menghitung ulang statistik dari agregat per tanggal (`research_findings` v1 + `research_stats`).
- Label hasil: **STATISTICS_VERIFIED** (rumus buatan AI tidak dicek, ditulis jelas).

## 4b. Bagaimana AI tahu alat apa saja yang ada dan cara memakainya (FINAL 2026-10-02)

### 4b-1. Kondisi sekarang (dicek di kode)

- Setiap panggilan model adalah satu request OpenRouter `POST /responses` (orc `_payload`) berisi `instructions`
  (system prompt), `tools` (7–14 alat per tahap, dengan deskripsi dan skema) dan `input` (percakapan run dan semua hasil
  alat). `store: false`: OpenRouter dan DeepSeek tidak menyimpan apa pun. Pengetahuan AI tentang alat hanya yang ada di
  request itu.
- `get_system_capabilities` hanya mengembalikan tanda ya/tidak per kemampuan dan daftar nama alat.
- Helper sandbox, G2 dan G3 adalah fungsi di dalam sandbox, bukan alat API. AI hanya melihat namanya saat sesi dibuka
  (`HELPERS`, `extra_helpers`). Aturan `event_summary` ada di prompt riset v1, yang sekarang mati.
- Manual hanya ada untuk G4 (`get_research_library`), saat menyusun rencana riset.

### 4b-2. Benchmark

| Praktik | Sumber | Inti |
|---|---|---|
| Deskripsi berorientasi kapan dipakai | OpenAI function calling guide; Anthropic *Writing effective tools* | Situasi pemakaian, batas, bentuk hasil; tanpa tumpang tindih antar alat |
| Sedikit alat per langkah | OpenAI (< ~20); Anthropic Tool Search | Hanya alat relevan per tahap (kita sudah 7–14) |
| Progressive disclosure | Anthropic Agent Skills | Lapis 1 menu selalu dimuat; lapis 2 manual (SKILL.md) dibuka saat relevan; lapis 3 contoh saat eksekusi. Di belakang layar manual dibaca lewat panggilan alat dan masuk konteks sebagai hasil alat |
| Daftar dari sistem | Model Context Protocol (`tools/list`) | Dibangkitkan dari server, bukan ditulis ulang |

### 4b-3. Desain final

**Lapis 1: menu (selalu ada).**
- `get_system_capabilities` ditambah bagian `analysis_methods`.
- Isinya: G1 kode bebas, G2 event study, G3 hipotesis bebas, G4 multi-angle, dan setiap helper sandbox. Per entri:
  nama, satu kalimat **kapan dipakai** dan **kapan tidak**, tingkat pemeriksaan (tabel di
  `FACTOR_EVENT_RESEARCH_PLAN.md` 2c), dan versi manualnya.
- Dibangkitkan dari registri kode, lewat `GET /v1/runtime` sandbox untuk helper dan metode.
- Sistem menjalankannya otomatis di awal setiap run (`VALUE_DICTIONARY_PLAN.md` 5.4c), dan hasilnya masuk `input`.

**Lapis 2: buku manual per metode (dibuka saat perlu).**
- Alat `get_method_guide(nama)` menggantikan dan memperluas `get_research_library` (alias lama tetap berlaku untuk G4).
- Isi kartu manual:
  1. untuk apa, kapan dipakai dan kapan tidak;
  2. masukan (peran dan parameter);
  3. batasan (minimal event, aturan overlap, kolom yang boleh dijumlah menurut katalog, anggaran hipotesis);
  4. tingkat pemeriksaan: apa yang dicek sistem dan apa yang tidak (S23);
  5. hasil dan cara mengutipnya (`out.oN`, `finding.<id>`);
  6. kesalahan umum dari log nyata (S15, S21, P22, …).
- **Penyimpanan:**
  - parameter, default dan batasan dibangkitkan dari kode;
  - panduan teks disimpan berversi di database dengan hash, pola `AI_research_library`;
  - test gagal bila manual dan kode tidak sinkron.

**Lapis 3: contoh (ikut di manual).**
- Satu atau dua contoh lengkap per metode.
- Setiap contoh **dijalankan di test**, jadi dijamin masih bekerja.

**Manual yang sudah dibuka dibawa sepanjang percakapan.**
- Catatan percakapan (`data_record`) mendapat bagian baru `manuals`: nama metode, versi, hash, dan isi kartu.
- **Antar sub-langkah mode 4** (A → B → C → D) dan **antar giliran percakapan**, manual yang pernah dibuka
  disuntikkan otomatis di awal run berikutnya, di sebelah menu. AI tidak perlu membukanya lagi.
- **Versi:** bila manual di kode berubah (hash beda), versi baru yang disuntikkan, dan catatan diperbarui.
- **Ukuran:** kartu ditulis ringkas (target per kartu ditetapkan saat implementasi dan diukur). Bila jumlah kartu
  melewati batas catatan, yang paling lama tidak dipakai diringkas menjadi menu + "buka lagi dengan
  `get_method_guide`", dengan penanda yang terlihat (pola P5, tidak dipotong diam-diam).
- Disimpan bersama catatan data di `AI_conversation.state`, ikut di respons API dan audit (pola M47).

**Lapis tambahan: umpan balik saat salah.**
- Penolakan G2 dan G3 menyebut alasan dan langkah berikutnya (pola `allowed_actions`).

**Pengukuran.**
- Golden test mencatat metode yang dipilih AI per soal dibanding metode yang semestinya.
- Juga dicatat: berapa kali manual dibuka, dan token tambahan per run.

## 4c. Istilah G1–G4 (disepakati 2026-10-02)

| Istilah | Arti |
|---|---|
| **G1** | **AI bebas memakai sandbox**: menulis kode Python/SQL sendiri (`run_python`) di mode ANALYSIS maupun RESEARCH. Yang dicek hanya asal angka dan cakupan data, bukan rumusnya (S23). Worker statistik lama (`market-analytics-worker`, dihapus) adalah bentuk lama dari pola yang sama. |
| **G2** | Event study (helper + pemeriksa independen) |
| **G3** | Uji hipotesis bebas (rencana v1 + `event_summary`) |
| **G4** | Riset multi-angle (rencana v2 + perpustakaan metode) |

## 4d. Desain percakapan multi-giliran (keputusan user 2026-10-02)

**Tujuan:**
- setelah G1–G4 berjalan, user bisa bertanya arti angka, insight dan penjelasan, seperti percakapan biasa;
- bila user meminta, analisis berlanjut, dan arahnya bebas ke G1, G2, G3 atau G4;
- tidak ada pengulangan riset dari awal kecuali diminta.

Desain ini memperluas `MODE4_CONVERSATION_PLAN.md` (sudah disetujui) dan berlaku untuk semua mode (mode 4, ANALYSIS,
RESEARCH).

### 4d-1. Yang dibawa dari giliran ke giliran (state percakapan)

Disimpan di `AI_conversation.state` (catatan data, M47) dan disuntikkan otomatis di awal setiap run dan sub-langkah:

| Bagian | Isi | Untuk apa |
|---|---|---|
| Data | tabel, kolom, nilai kategori, relasi, coverage (sudah ada) | Tidak membaca katalog ulang |
| Output G1/G2 | `out.oN` dengan nama, kolom, jumlah baris (sudah ada) | Mengutip dan memakai ulang tabel hasil |
| Temuan G2/G3/G4 | status, estimasi, CI, p, sampel, label pemeriksaan, rentang data (baru, E1) | Menjelaskan dan mengutip temuan di giliran berikutnya |
| Manual | kartu metode yang pernah dibuka (baru, 4b-3) | Tidak membuka manual ulang |
| Rencana tertunda | saran v1 (G3) / v2 (G4) yang belum disetujui | User bisa menyetujui kapan saja |
| Buku percobaan | semua uji yang pernah dijalankan (G2, G3, G4) | Koreksi uji berganda lintas giliran |
| Sesi dan bundle hangat | sudah ada (conversation reuse) | Lanjutan tanpa menarik data ulang |

### 4d-2. Jenis giliran dan apa yang dijalankan

Router di setiap giliran: pengklasifikasi diperluas dari `MODE4_CONVERSATION_PLAN.md`, ditambah aturan backend.

| Jenis giliran | Contoh | Yang dijalankan | G yang boleh dipakai |
|---|---|---|---|
| **CLARIFY**: arti angka, definisi, cara membaca | "68,9% itu artinya apa?", "Lift itu apa?", "Datanya dari mana?" | Jawaban dari state, manual dan katalog (definisi kolom, satuan, grain), tanpa hitungan baru | Tanpa alat data |
| **INSIGHT**: kenapa, apa pendorongnya, apa yang menonjol | "Kenapa XL tertinggi?", "Insight-nya apa?", "Apa yang mendorong kenaikan ini?" | **Analisis pendorong** atas data dan output yang sudah ada (4d-3b): kontributor teratas/terbawah, perubahan antar periode, pendorong per dimensi, nilai tak biasa, konsentrasi. Hasilnya deskriptif (asosiasi, bukan sebab); boleh ditutup dengan tawaran uji (G2/G3/G4) | G1 (AI menghitung di sandbox), tanpa riset kecuali diminta |
| **CONTINUE**: user minta analisis lanjutan | "Coba lihat dampaknya setelah crash", "Uji ide saya", "Cari sudut lain" | AI memilih G dari menu sesuai permintaan; data dan output sebelumnya dipakai ulang | **Bebas G1–G4**: G1 dan G2 langsung di sesi; G3 dan G4 lewat rencana (persetujuan user mengikuti `AI_REQUIRE_RESEARCH_PLAN_CONFIRMATION`) |
| **APPROVE / REVISE / CANCEL** | "Jalankan", "Pakai 5 tahun", "Tidak usah" | Seperti sekarang, untuk rencana v1 maupun v2 | G3 / G4 |
| **NEW_TOPIC** | "Sekarang saham telko?" | Giliran pertama (mode 4: A + riset) | Sesuai mode |
| **CONVERSATIONAL** | "Apa itu CAR?", "Metode apa yang dipakai?" | Jawaban langsung dari manual/state | Tanpa alat data |

**Aturan backend:**
1. Riset (G3/G4) hanya jalan bila diminta (CONTINUE yang meminta uji, APPROVE) atau NEW_TOPIC di mode 4. CLARIFY,
   INSIGHT dan CONVERSATIONAL tidak pernah memicu riset.
2. Kalau ragu antara CLARIFY / INSIGHT dan CONTINUE yang meminta riset, pilih yang tanpa riset dan tawarkan uji lanjutan
   (salah ke arah yang murah).
3. Saran tertunda tidak hilang karena pertanyaan lanjutan.
4. Arah lanjutan bebas: tidak ada urutan wajib G1 → G2 → G3 → G4. AI memilih dari menu; user boleh menyebut metode
   ("pakai event study").

### 4d-3. Menjawab arti angka dan insight dengan benar

- **Angka** selalu dirujuk dari state (`out.oN`, `finding.<id>`). Angka turunan (selisih, rasio) lewat fungsi rujukan
  (`diff`, `ratio`) atau dihitung di sesi. Angka dari teks jawaban sebelumnya tidak dipercaya (keputusan lama tetap).
- **Arti angka:** definisi diambil dari manual metode dan katalog (arti kolom, satuan, grain), bukan dikarang.
- **Insight:** interpretasi diberi label sebagai interpretasi. Klaim sebab atau prediksi tetap mengikuti aturan bukti
  (hanya dari temuan riset dengan status yang sesuai). Tingkat pemeriksaan angka ditulis (S23).
- **Penyebab di luar database** (berita, aksi korporasi) tidak tersedia; jawaban menyatakannya.

### 4d-3b. Benchmark dan rancangan INSIGHT (revisi 2026-10-02)

Di produk analitik, "insight" dan "kenapa" bukan menjelaskan ulang angka, melainkan **analisis pendorong yang dihitung**:

| Produk | Cara kerja "kenapa / insight" |
|---|---|
| Tableau Explain Data | Membangun dan menguji model statistik untuk menjelaskan kenapa satu titik tinggi/rendah, termasuk dimensi yang tidak ditampilkan |
| Tableau Pulse | Jenis insight baku: perubahan antar periode, kontributor teratas/terbawah, pendorong teratas, nilai tak terduga, outlier, perubahan tren, konsentrasi |
| Power BI | Key influencers (regresi logistik dan pohon keputusan) dan decomposition tree (memecah metrik per dimensi); "explain the increase/decrease" |
| ThoughtSpot SpotIQ | Deteksi anomali, analisis perubahan (akar penyebab fluktuasi KPI), tren, analisis pendorong antar dua titik |

**Rancangan untuk kita (keputusan user 2026-10-02: tanpa helper dulu):**
- INSIGHT memakai **G1**: AI menghitung analisis pendorong sendiri di sandbox (pandas/DuckDB) atas output dan bundle
  yang sudah ada.
- Jenis insight baku di atas (perubahan antar periode, kontributor, pendorong per dimensi, nilai tak biasa,
  konsentrasi) ditulis di **manual G1** (4b-3) sebagai panduan, bukan sebagai kode.
- Dimensi pemecah dipilih dari kolom `is_groupable` di katalog; penjumlahan mengikuti aturan katalog.
- **Label:** deskriptif ("berasosiasi dengan", bukan "menyebabkan"); tingkat pemeriksaan G1 (rumus tidak dicek, S23)
  ditulis. Penutup boleh berupa tawaran uji (G2 untuk dampak event, G3/G4 untuk hipotesis).
- Helper `saniti.insight(...)` yang dites backend menjadi kandidat sesudah golden test, bila hasilnya menunjukkan
  perlu.

### 4d-4. Rantai antar G (bebas arah)

- G1 → G2: tabel hasil analisis menjadi daftar event atau universe untuk event study.
- G2 → G3: tabel event G2 menjadi dasar hipotesis bebas (`event_summary`).
- G4 → G2/G3: angle yang menarik ditindaklanjuti dengan event study atau hipotesis bebas.
- G2/G3/G4 → G1: temuan dijelaskan atau dirinci dengan kode bebas.

Prasyaratnya: output dan temuan bisa dimuat ulang di sesi berikutnya (Langkah 9 di rencana kecepatan: hasil analisis
sebagai bahan riset) dan dirujuk lintas giliran (E1).

### 4d-5. Verifikasi: skenario percakapan

Satu skenario multi-giliran ditambahkan ke golden test (bagian 7):

1. Pertanyaan awal (mode 4): jawaban + G4.
2. "Angka 68,9% itu artinya apa?" → CLARIFY, tanpa alat data, angka dari `out.oN`.
3. "Kenapa XL paling tinggi? Insight-nya apa?" → INSIGHT: analisis pendorong (per tahun, per saham), tanpa riset.
4. "Coba event study: return saham bank 5 hari setelah XL beli besar." → CONTINUE → G2.
5. "Uji ide saya: efeknya hanya di bank BUMN." → CONTINUE → G3 (rencana v1, disetujui).
6. "Cari 4 sudut lain." → CONTINUE → G4.
7. "Jelaskan hasil uji tadi." → CLARIFY dengan `finding.<id>`.

**Dicatat per giliran:** jenis giliran, G yang jalan, detik, rujukan angka, dan apakah riset terulang tanpa diminta
(harus nol).

## 5. Bagaimana G2, G3, G4 saling melengkapi (contoh)

Pertanyaan: "Apa yang terjadi pada saham bank setelah net jual asing besar?"
- **G2 (analisis, tanpa rencana):** `saniti.event_study` menghitung return 5 hari setelah event, lalu pemeriksa
  independen PASS.
- **G3 (rencana v1):** hipotesis bebas "efeknya hanya di bank BUMN", memakai tabel event G2, lalu `event_summary`.
- **G4 (rencana v2):** 4 angle dari perpustakaan, misalnya `quantile_ranking` net asing dan `lead_lag`.

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

## 7. Golden test 5 soal + skenario percakapan (sesudah langkah 1–6 di bagian 8)

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

Ditambah skenario percakapan 7 giliran di 4d-5.

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

1. **S21 + P22** (kecil; sandbox dan orc). *Selesai di branch (`1be3bf5`), belum di-deploy.*
2. **G2-A:** helper `event_study` + pemeriksa independen + CI per tanggal (sandbox), lalu render dan label (orc).
   *Selesai di branch, belum di-deploy.* Tambahan dari implementasi:
   - setiap rentang dihitung di jendelanya sendiri, jadi return ke depan tidak pernah menyambung dua rentang (S24);
   - tabel event ikut diperiksa, bukan hanya ringkasan;
   - orc menjelaskan helper ke AI hanya dengan saklar `AI_ENABLE_EVENT_STUDY` (default mati), dinyalakan di dev pada
     langkah 6; label CALCULATION_VERIFIED mengikuti hasil sandbox apa pun saklarnya.
3. **G3:** rencana v1 berdampingan dengan v2 (orc: prompt, skema, kelanjutan; sandbox: keduanya aktif bersamaan).
4. **Menu, manual dan contoh** (4b-3): `analysis_methods`, `get_method_guide`, kartu manual G1–G4 dan helper.
5. **Percakapan multi-giliran** (4d), dikerjakan bersama router `MODE4_CONVERSATION_PLAN.md`:
   - state lintas giliran: temuan (E1), manual, buku percobaan, rencana tertunda;
   - router CLARIFY / INSIGHT / CONTINUE / APPROVE / REVISE / CANCEL / NEW_TOPIC / CONVERSATIONAL;
   - INSIGHT lewat G1 dengan panduan di manual (4d-3b, tanpa helper);
   - rantai antar G (4d-4).
6. **Uji live singkat:** G2 dan G3 masing-masing sendiri, lalu bersama, lalu dua giliran lanjutan (saklar pikiran
   menyala).
7. **Golden test** 5 soal + skenario percakapan (bagian 7, 4d-5).
8. **Sesudahnya, sesuai hasil golden test:** G2-B (jalur event, return abnormal), S20, minimal 4 hipotesis
   (`FACTOR_EVENT_RESEARCH_PLAN.md`), analisis faktor.

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
| Dua jenis rencana membingungkan AI | AI memilih v1 atau v2 dengan salah | Aturan kapan memakai masing-masing di `analysis_methods`; pilihan AI dicatat dan diukur di golden test |
| Prompt lebih panjang | Aturan v1 dan v2 sama-sama dimuat | Aturan dipadatkan; ukuran prompt dan waktu diukur |
| G3 tetap tidak mengecek rumus AI | Event buatan AI bisa salah | Label STATISTICS_VERIFIED tertulis di jawaban; AI dianjurkan memakai tabel event G2 (yang dicek) sebagai dasar G3 |
| Uji makin banyak, peluang kebetulan naik | G2 + G3 + G4 dalam satu rencana | Koreksi menghitung semua uji di rencana; holdout |
| Golden test terlalu kecil | 5 soal bukan ukuran statistik akurasi | Disebut sebagai baseline awal; soal ditambah setelah fitur berikutnya |
| Router salah membaca giliran | Penjelasan dianggap permintaan riset, atau sebaliknya | Ragu → CLARIFY/INSIGHT plus tawaran; diukur di skenario 4d-5 (riset tak diminta harus nol) |
| State percakapan membesar | Temuan, manual dan output menumpuk | Batas per bagian dengan penanda terlihat (pola P5); versi lengkap di store |
| Waktu run | Pemeriksa independen menambah waktu penyelesaian | Diukur; pemeriksa hanya berjalan untuk output event study |
| Token bertambah karena manual dibawa | Setiap manual yang dibuka ikut di setiap panggilan berikutnya | Kartu ringkas; prompt caching (`session_id` per run); kartu lama diringkas dengan penanda; token per run diukur |
| Manual basi | Manual tidak sesuai perilaku kode | Bagian teknis dibangkitkan dari kode; hash dan test sinkron; contoh dijalankan di test |

## 10. Keputusan yang diminta dari user

1. ~~G3 sebagai `experiments` di v2 atau jalur terpisah~~: **terpisah** (keputusan user 2026-10-02).
2. ~~Ketersediaan G2~~: AI mengetahui alat lewat menu `get_system_capabilities`, manual `get_method_guide` dan contoh;
   manual yang dibuka dibawa sepanjang percakapan (bagian 4b-3, final).
3. ~~Soal golden test~~: 5 soal di bagian 7 + skenario percakapan 4d-5 (disetujui bersama finalisasi 2026-10-02).
4. ~~Topik baru di percakapan yang sama~~: di mode 4, NEW_TOPIC menjalankan giliran pertama (A + riset), sesuai tujuan
   "selalu satu langkah lebih maju" (4d-2).
