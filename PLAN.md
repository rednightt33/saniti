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
| 1b | Menu alamat lengkap (celah item 10.1): setiap angka tabel punya alamat, pola alamat ditulis, nilai terformat | 2026-10-05 15:49 dan 17:55 ("Menu alamat siap salin … alamat lengkap di samping angkanya"); ditegaskan 2026-10-06 ("padahal sudah saya suruh") | Sebagian: menu live sejak golden test 06b, tetapi tabel hanya satu baris contoh dan baris pola yang direncanakan tidak dibuat; **EXEC 2026-10-06** ("Ok masukan", bagian dari EXEC-1) | **EXEC** (EXEC-1 langkah 1b) | 1 |
| 1c | EXEC-R: penolakan tanpa tulis ulang (R1–R5: edit field bersarang, `keep`, angka ketik jadi alamat, galat format yang benar + edit kedua, validasi per butir + jatah per penyebab + tanggal terbuka) | 2026-10-06 ("Masukan exec untuk masalah AI rejection tapi harus ulang dari awal") | **EXEC** (menunggu konfirmasi mulai) | Sesudah EXEC-1 |
| 1d | EXEC-C: konteks dibawa ke run berikutnya setelah LIMITED / giliran baru (memo run + P4) | 2026-10-06 ("masukan exec") | **EXEC** (menunggu konfirmasi mulai) | Sesudah EXEC-R |
| 1e | EXEC-A: penyelarasan jalur (satu pembaca maksud, gerbang hanya meminta alat yang ada, 10.6 dan edit sama di semua jalur) | 2026-10-06 ("masukan exec") | **EXEC** (menunggu konfirmasi mulai) | Bersama EXEC-3 |
| 1f | EXEC-E: hapus `get_evidence` dan gerbang EVIDENCE, perbarui dokumen terkait | 2026-10-06 ("hapus get evidence, update related docs terkait itu, masukan exec"); membatalkan keputusan 2026-10-03 "Prioritas 2, WAJIB" | **EXEC** (menunggu konfirmasi mulai) | Sebelum EXEC-R |
| 1g | EXEC-P2: P2a (berhenti mendorong `check_references`) + P2e (jawaban ringkas) | 2026-10-06 ("p2a p2e … masukan exec") | **EXEC** (menunggu konfirmasi mulai) | Bersama EXEC-R |
| 1h | EXEC-P1: mode 4 berhenti setelah analisis + rencana | 2026-10-06 ("p1 … masukan exec") | **EXEC** (menunggu konfirmasi mulai) | Sesudah EXEC-3 |
| 1i | EXEC-P5: gabung langkah mekanis | 2026-10-06 ("p5 masukan exec") | **EXEC** (menunggu konfirmasi mulai) | Sesudah EXEC-R |
| 1j | EXEC-T: perangkat alat per proses (matriks HARUS/BOLEH/TIDAK BOLEH final, alat terlarang dikunci kode dan tidak bisa ditemukan) | 2026-10-06 ("finalize dan masukan ke EXEC"; catatan user: alat TIDAK BOLEH dikunci kode, tidak boleh ditemukan lewat pencarian) | **EXEC** (menunggu konfirmasi mulai) | Bersama EXEC-A |
| 2 | P3: gerbang yang salah tolak | 2026-10-06 "OK masukan plan jangan execute dulu" | Belum (P3a ikut EXEC butir 1, P3b ikut EXEC butir 3) | 3 |
| 3 | Item 11: penyortir "free will", jalur TANYA BALIK, cadangan berupa pertanyaan | 2026-10-05 (16:47, 17:40, 17:51, 17:55), ditegaskan 2026-10-06; **EXEC 2026-10-06** | **EXEC** (lihat bagian EXEC) | 2 |
| 4 | P2: jawaban ditulis sekali | 2026-10-06 | P2b–d di EXEC-R, P2a dan P2e di EXEC-P2 | — |
| 5 | P1: mode 4 berhenti setelah analisis + rencana | 2026-10-06 | EXEC-P1 | — |
| 6 | P5: gabung langkah mekanis | 2026-10-06 | EXEC-P5 | — |
| 7 | P4: hasil jelajah dibawa antar-putaran | 2026-10-06 | Masuk EXEC-C (butir 1d) | — |
| 8 | Round 2026-10-03 Fase E: E1 hit rate (M69 tahap 2), E2 ambil sekali beri label (G19 lapis 2) | 2026-10-03 (round disetujui) | Belum; E2 menunggu keputusan 6 | 8 |
| 9 | C06 1a-permanen dan D06 peringatan Telegram | 2026-10-02 | Belum (sisanya sudah live) | 9 |
| 10 | G2-B, S20, minimal 4 hipotesis, analisis faktor | 2026-10-02 (`G2_G3_REACTIVATION_PLAN.md` langkah 8, FINAL) | Belum; 4 keputusan rinci masih terbuka | 10 |
| 11 | P9 kamus nilai dan alat "cari nilai" | Keputusan desain user 2026-10-01 | Belum; perlu cek ulang cakupan | 11 |
| 12 | Prosedur tabel baru (FX, indeks, makro) | 2026-10-01 "record now, run later" | Menunggu pemicu: tabel baru | Saat ada tabel baru |

Biaya model: butir 1 (ulang uji ±USD 0,07) dan setiap golden test sesudah butir 2–7. Sisa kredit OpenRouter terakhir
±USD 0,7, jadi kredit dicek sebelum uji apa pun.

Status **EXEC** = rencana eksekusi sudah disetujui isinya, tetapi **baru dijalankan setelah user memberi konfirmasi
mulai** (keputusan user 2026-10-06: "EXEC dijalankan setelah konfirmasi saya"). Tidak ada push (cabang maupun `main`)
sebelum konfirmasi itu. Setelah dimulai, berhenti dan lapor bila menemui kondisi berhenti, atau bila perlu tindakan di
luar langkah ini.

## EXEC (disetujui 2026-10-06: "1 dan 3 … EXEC")

Urutan: EXEC-1, lalu EXEC-3. EXEC-3 dibangun di atas `main` yang sudah memuat EXEC-1.

### EXEC-1: sisa item 10 dan 12 (butir 1)

| Langkah | Isi | Biaya | Lulus bila |
|---|---|---|---|
| 0 | Pra-cek: kredit OpenRouter (dibaca di proses, kunci tidak dicetak); Railway dev (tidak ada golden test atau job berjalan); cabang = `origin`; `main` bisa fast-forward | 0 | Kredit ≥ USD 0,30; tidak ada run berjalan |
| 1 | Tes lokal: suite orc dan web-governor; `git diff --check` | 0 | Hijau |
| 1b | Butir 1b (menu alamat lengkap): kode `value_refs.py` dan `orchestrator.py` + tes `test_address_menu.py`; ukur tambahan token menu pada hasil tabel nyata dari golden test 06b (lokal, tanpa model); commit sebelum push langkah 2 | 0 | Tes hijau; setiap baris tabel kecil punya alamat; tabel besar punya pola; format `nama: nilai → {{alamat}}`; tambahan token dilaporkan |
| 2 | Push `main` (fast-forward ke cabang kerja: `7eda0b7`, `d675404`, dokumen). Orc dan web-governor auto-deploy | 0 | Kedua deployment SUCCESS; log start bersih (`ai_provider_policy` OK, tanpa `web_research_inactive`); `railway config plan` up to date |
| 3 | Uji asap route web: 1 kasus (`bi_rate`) lewat `web-governor-test-runner` fase `orc_web` | ±USD 0,02 | `currency` berupa kode ISO, `unit_code`, tanggal ISO, tanpa `DATE_NOT_ISO` |
| 4 | Ulang uji `threshold_from_result` (3 giliran), suite `qa_20261006c`, prefix `ma-qa-20261006c` | ±USD 0,07 | Giliran 2 = rencana dengan efek minimal dari hasil sebelumnya (tidak LIMITED); giliran 3 menjalankan riset; tanpa penolakan REFERENCE; tidak ada alamat yang disusun sendiri di log pikiran (butir 1b) |
| 5 | Laporan `GT_QA_2026-10-06.md` (non-dev): kriteria lulus rencana item 10/12, analisis waktu, ulang uji langkah 4; prosedur 5 langkah per temuan, termasuk praktik terbaik online dan perbandingannya | 0 | Setiap temuan punya akar masalah dari log, usulan, risiko, pembanding online dan solusi final |
| 6 | Catatan: status P35, P36, P37, M83, W24, W26; 11 entri temuan baru (lihat butir 1 langkah 5); `RAILWAY_CHANGELOG.md`, `DATABASE_CHANGELOG.md`, `OUTSTANDING_ISSUES.md`; butir 1 dihapus dari `PLAN.md`. Commit, push `main` dan cabang, cek sama dengan `origin` | 0 | Push sukses |

**Kondisi berhenti:**
- **Deploy tidak SUCCESS:** redeploy deployment sebelumnya (orc `96726ca5`, web-governor `7ca3067e`), lalu lapor.
- **Kredit kurang:** berhenti sebelum langkah 3.
- **Ulang uji gagal:** dicatat dan dilaporkan. Perbaikan kode di luar langkah ini menunggu izin.
- **Tambahan token menu (butir 1b) > 10%** pada tabel nyata: batas baris diturunkan sampai ≤ 10%, lalu dilaporkan.

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

### EXEC-R: penolakan tanpa tulis ulang dari awal (butir 1c)

**Asal:** analisis penolakan golden test 06b (2026-10-06). ±730 dtk (18% waktu model) habis untuk langkah sesudah
penolakan; di 05b ±1.018 dtk (14%). Disetujui user 2026-10-06 untuk lima masalah di bawah.

Bagian yang sudah ada di EXEC lain tidak diulang:
- deploy 10.6 (P3a) ada di EXEC-1;
- bacaan "tambah/ganti" (P3b) ada di EXEC-3.

| No | Masalah (bukti) | Perubahan | Berkas |
|---|---|---|---|
| R1 | Gerbang rencana (PLAN_*) selalu memaksa tulis ulang penuh: ±400 dtk dan 3 giliran terbuang. Edit hanya bisa mengganti teks atau field paling atas | Edit menerima `"set": {"research_plan.angles[0].min_effect": null}` untuk field bersarang (jalur bertitik + `[i]`, hanya field yang ada di skema), lalu jawaban dicek ulang penuh. Pesan gerbang PLAN_* menyebut jalur field yang harus diubah. `EDIT_REPAIR_INSTRUCTION` diperbarui | `edit_repair.py` (`apply`, instruksi), `orchestrator.py` (pesan PLAN_*) |
| R2 | "Kirim ulang tanpa perubahan" agar catatan backend ikut: h_add t2 mengirim ulang 8.660 token (109 dtk) | Bila edit ditawarkan, `GATE_ONCE_NOTE` meminta balasan `{"keep": true}`; backend memakai draf tersimpan dan menjalankan jalan keluar gerbang. Bila edit tidak ditawarkan, perilaku lama tetap | `orchestrator.py` (`GATE_ONCE_NOTE`, `_offer_edit`, `_apply_edit`), `edit_repair.py` (`is_edit`) |
| R3 | Angka diketik tanpa alamat. EVIDENCE meminta alamat atau `get_evidence` (gerbang ini dihapus di EXEC-E; R3 berlaku untuk aturan pengganti "angka dari kode wajib beralamat") | Angka ketik yang cocok dengan **tepat satu** nilai rilis (pembulatan dan satuan sama) diperlakukan sebagai alamat: masuk bukti sebagai DIRUJUK, gerbang EVIDENCE tidak memintanya lagi, dicatat `ai_reference_auto`. Dua kecocokan atau lebih: tetap diminta. Angka tanpa sumber sama sekali (PROVENANCE, misalnya "82,18%") tidak tertolong; pesan gerbangnya menyarankan merilis nilai itu lalu mengutip alamatnya | `orchestrator.py` (`_evidence_gate`, `typed_figures`, pesan PROVENANCE), `value_refs.py` (cari kecocokan unik) |
| R4 | Galat format dan edit gagal (79 dtk); jawaban riset q7 jatuh menjadi LIMITATION | (a) Bila parser longgar juga gagal, model diberi galat parser longgar beserta posisi dan potongan teksnya. Galat "control character" dari parser ketat menyesatkan (P3d). (b) Edit yang gagal mendapat satu kesempatan edit lagi dengan penyebab persisnya, bukan langsung tulis ulang penuh. (c) `"all": true` pada teks biasa diperlakukan sebagai `count` = jumlah kemunculan (P2d) | `orchestrator.py` (`_parse_final_output`, `_apply_edit`), `edit_repair.py` |
| R5 | Validasi semua-atau-tidak dan jatah perbaikan yang langsung habis (`query_metric` ×4, `get_evidence` `claims.2`) | (a) ~~`get_evidence` per klaim (E2)~~: gugur karena alat dihapus (EXEC-E). (b) Jatah perbaikan dihitung per penyebab **per giliran model**: 4 penolakan sama dalam satu giliran dihitung 1. (c) `query_metric` menerima `start_date` tanpa `end_date` (sampai data terakhir / `as_of`) | `tools/evidence.py`, `orchestrator.py` (`_repair_budget`), `tools/metric.py` (`Period`) |

**Tambahan dari saya** (daftar perbedaan dari usulan Anda, sesuai R35):
- **P3c (kini disetujui lewat EXEC-A):** gerbang hanya meminta alat yang ada di langkah itu. `check_references` ditambahkan ke
  langkah riset yang disetujui (`_approve_v2`); `get_evidence` tidak lagi, karena dihapus (EXEC-E). Tanpa P3c, jawaban riset q7 tetap bisa langsung jatuh menjadi
  LIMITATION (`tool_not_in_step`) walau R4 sudah ada.
- **Tidak termasuk:**
  - E1 (aturan LAST di Governor dengan filter satu nilai);
  - E3 (deskripsi `get_evidence`);
  - P2a (dorongan `check_references`);
  - P2e (jawaban ringkas).

  Semuanya tetap di P2 dan `FUTURE_PLAN.md`.

**Langkah eksekusi (setelah konfirmasi mulai):**

| Langkah | Isi | Biaya | Lulus bila |
|---|---|---|---|
| 0 | Patokan: hitung ulang dari log 06b dan 05b waktu dan token sesudah penolakan per jenis (skrip analisis yang sudah ada) | 0 | Angka patokan tercatat |
| 1 | Kode R1–R5 (+ P3c bila di-OK), satu commit per R | 0 | — |
| 2 | Tes: R1 jalur bersarang dan jalur tidak dikenal ditolak; R2 `keep` menghasilkan jalan keluar gerbang tanpa tulis ulang; R3 satu kecocokan diterima, dua kecocokan tetap diminta; R4 pesan parser longgar dan edit kedua; R5 klaim campuran sah+cacat, 4 penolakan paralel = 1, `query_metric` tanggal terbuka. Suite orc lengkap, `test_prompt_pass2.py`, `AI_TOOLS.md` diregenerasi (argumen `query_metric` berubah), migration Tool_Catalog round berikutnya bila skema alat berubah | 0 | Hijau; tes drift lulus |
| 3 | Push dan deploy orc (hanya setelah konfirmasi push dari user), SUCCESS | 0 | SUCCESS; log start bersih |
| 4 | Ulang uji 2 item yang memicu penolakan rencana dan format: h_add (3 giliran) dan threshold (3 giliran) | ±USD 0,15 | Tidak ada tulis ulang penuh setelah penolakan PLAN_*; `keep` dipakai bila model memilih tetap; waktu sesudah penolakan ≤ 5% waktu model |
| 5 | Catatan: entri ERRORS (status), `RAILWAY_CHANGELOG.md`, `AI_TOOLS.md`; butir 1c dihapus dari `PLAN.md` | 0 | — |

**Kondisi berhenti:**
- Tes merah yang tidak bisa diperbaiki di dalam cakupan R1–R5.
- Uji ulang menunjukkan gerbang menjadi longgar (angka tanpa sumber lolos). Bila ini terjadi, R3 dimatikan dan
  dilaporkan.

### EXEC-C: konteks dibawa ke run berikutnya (butir 1d, mencakup P4)

**Masalah:** setelah sebuah run berakhir (LIMITED atau selesai), giliran berikutnya adalah run baru. Yang terbawa hanya
teks percakapan dan output yang dirilis. Pikiran, bacaan katalog, panduan yang dibuka, dan alasan penolakan hilang,
sehingga model menjelajah ulang. Contoh: threshold t3 langkah 1 berpikir 5.253 token selama 64 dtk; q7-m4b membaca
ulang katalog dan 5 panduan (±170 dtk).

**Perubahan:**
- **Memo run** disimpan di data record percakapan (`data_record.py`) di akhir setiap run dan sub-run mode 4. Isinya
  terstruktur:
  - tabel, kolom dan relasi yang sudah dibaca, beserta cakupannya;
  - panduan metode yang sudah dibuka;
  - spesifikasi data yang diajukan dan statusnya;
  - keputusan desain yang dipakai (horizon, ambang, efek minimal, cakupan);
  - asumsi jawaban;
  - bila berakhir LIMITED/LIMITATION: gerbang yang menolak, alasannya, dan bagian draf yang ditolak.
- Run berikutnya menerima memo itu sebagai catatan aplikasi setelah prefix statis, supaya cache prompt tetap. Model
  dipandu memakai memo dulu sebelum menjelajah katalog lagi.
- **Pikiran mentah tidak dibawa** (panjang, milik penyedia). Yang dibawa adalah kesimpulannya dalam bentuk terstruktur.
- **Berkas:** `data_record.py`, `orchestrator.py` (akhir run, awal run), `mode4.py` (`sub`), `tools/catalog.py`,
  `tools/method_guides.py`.
- **Tes:**
  - memo tersimpan dan dibaca;
  - batas panjang memo (usul ≤ 4.000 karakter);
  - memo tidak memuat angka yang bisa dikutip, karena angka tetap lewat alamat.
- **Lulus bila** di ulang uji threshold dan q7: panggilan jelajah katalog di run lanjutan turun ≥ 50%, dan token
  berpikir langkah pertama run lanjutan turun.

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

### EXEC-E: hapus `get_evidence` (butir 1f)

**Alasan** (data 3 golden test):
- round 2026-10-03: 23 TERCEK, 1 TIDAK COCOK yang ternyata alarm palsu (G21);
- 05b: gerbang EVIDENCE menolak 5 kali (±192 dtk);
- 06b: 5 panggilan, 2 penolakan, dan q7-m4c dipaksa LIMITATION (`tool_not_in_step`).

Alat ini belum pernah menangkap angka yang benar-benar salah. Keputusan user 2026-10-06 membatalkan "Prioritas 2,
WAJIB" (2026-10-03).

**Yang dihapus / diubah:**
1. **Saklar dulu:** `AI_ENABLE_EVIDENCE=false` di dev, satu perubahan variabel yang bisa dikembalikan. Ini langsung
   menghapus alat dan gerbangnya dari run.
2. **Kode orc:**
   - `tools/evidence.py`;
   - registrasi di `tools/__init__.py` dan `main.py`;
   - `config.py` (`ai_enable_evidence` dan cek `AI_ENABLE_RESULT_STORE`);
   - gerbang `EVIDENCE` dan `EVIDENCE_MISMATCH` beserta kalimatnya (`EVIDENCE_INSTRUCTION`, `EVIDENCE_*_LINE`);
   - kalimat prompt dan catatan yang menyebut `get_evidence` (`orchestrator.py`, `conversation_router.py`,
     `method_guides.py`, `tools/envelope.py`);
   - tes terkait (`test_evidence.py`, `test_tool_effects.py`, `test_g23_desk.py`).
3. **Pengganti gerbang EVIDENCE:** angka dari kode AI sendiri yang diketik tanpa alamat ditolak sekali dengan pesan
   "tulis lewat alamat dari daftar `addresses`, atau hapus angkanya". Edit kecil tersedia. Angka yang cocok dengan
   tepat satu nilai rilis diterima otomatis (EXEC-R R3).
4. **Tetap dipertahankan:**
   - daftar angka beralamat untuk user (`evidence[]` dengan status DIRUJUK): dibuat backend tanpa alat ini;
   - Governor `/v1/summary` (dipakai `query_metric`);
   - operasi sandbox `recount` (tidak dipakai lagi; dicatat, dihapus terpisah bila disetujui);
   - tabel `AI_conversation_evidence` (riwayat, tidak di-drop).
5. **Database:**
   - migration baru Tool_Catalog: `get_evidence` dinonaktifkan (migration lama tidak diedit);
   - buku metode versi baru lewat generator tanpa kalimat `get_evidence`;
   - Table_Catalog `AI_conversation_evidence`: catatan "tidak diisi lagi sejak <tanggal>".
6. **Dokumen:**
   - `AI_TOOLS.md` (regenerasi, `--flags` dari `railway variables --kv`);
   - `scripts/generate_ai_tools_doc.py` (`PLAIN`, `SWITCHES`);
   - `scripts/generate_tool_catalog_migration.py`, `scripts/generate_ai_method_guide_migration.py`;
   - README orc dan sandbox;
   - ERRORS: S23 status menjadi "tidak ada cek independen untuk angka hitungan AI" (risiko diterima user), D6 dan
     G20/G21 dicatat ditutup karena alat dihapus, entri baru untuk keputusan ini;
   - `OUTSTANDING_ISSUES.md`;
   - `FUTURE_PLAN.md`: E1/E3 dihapus, ditambah usulan B "backend mengecek ulang metrik baku secara otomatis";
   - `RAILWAY_CHANGELOG.md`, `DATABASE_CHANGELOG.md` dan `DATABASE_SCHEMA.md`;
   - `.railway/railway.ts` (config pull/plan).

**Risiko yang diterima:**
- Angka hitungan kode AI tidak pernah dihitung ulang secara independen. Alamat hanya menjamin angka sama dengan tabel
  AI, bukan bahwa tabelnya benar (S23).
- Baris bukti hitung ulang per klaim untuk user hilang; daftar DIRUJUK tetap ada.

**Langkah:**
1. Saklar mati di dev.
2. Kode, tes dan dokumen.
3. Push dan deploy orc dan sandbox (setelah konfirmasi push).
4. Migration Tool_Catalog dan buku metode lewat job sementara (dry run, apply, baca ulang).
5. Ulang uji 2 item (lang, threshold): tidak ada panggilan atau gerbang EVIDENCE, dan tidak ada angka tanpa sumber
   yang lolos.

**Biaya:** ±USD 0,10.

### EXEC-P2: P2a + P2e (butir 1g)

- **P2a:** `ADDRESS_MENU_NOTE` dan aturan prompt tidak lagi mendorong `check_references` sebelum menulis. Alatnya
  tetap ada. Gerbang REFERENCE sudah mendaftar semua alamat salah dan penggantinya.
- **P2e:** target panjang jawaban akhir di aturan jawaban.
  - Usul: jawaban utama ≤ 2.500 karakter untuk ANALYSIS dan ≤ 1.500 karakter per bagian mode 4.
  - Tabel di jawaban paling banyak 10 baris; tabel lengkap tetap tersedia lewat output yang dirilis atau ekspor.
  - Kode hanya memperingatkan (log `ai_answer_long`), tidak menolak.
- **Tes:** `test_prompt_pass2.py` (ADDED/REMOVED, batas +2%).
- **Ukur di ulang uji:** panjang draf dan waktu tulis jawaban akhir dibanding 06b.
  - Patokan: draf terpanjang 10–17 ribu karakter.
  - Penulisan dan pengecekan jawaban = 41% waktu model.

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

## 1b. Menu alamat lengkap (celah item 10.1)

**Yang disetujui user** (2026-10-05): "Setiap hasil yang berisi angka langsung mencantumkan alamat lengkap di samping
angkanya, misalnya median: −2,40 → {{out.o2.content.groups.CONDITION.median}}. Asisten cukup menyalin, tidak menyusun
sendiri."

**Yang dibangun** (`apps/market-ai-orc/app/value_refs.py` `menu`; orchestrator `addresses`, live di dev sejak golden
test 06b):
- daftar terpisah `addresses` di hasil alat, berbentuk `alamat = nilai [satuan]` dengan nilai mentah;
- tabel hanya diberi **satu baris contoh** (`rows[ticker=BBRI]`);
- batas 40 alamat per objek dan 120 per hasil.

**Celah terhadap yang disetujui:**
1. **Tabel hanya satu baris contoh.** Untuk mengutip baris lain (BBCA), AI masih menyusun alamat sendiri.
   Penyempitan ini saya tulis di rencana implementasi ("tidak semua baris didaftar") tanpa saya tandai sebagai
   perbedaan dari kata-kata user.
2. **Baris pola yang dijanjikan rencana implementasi** ("ditambah polanya") tidak dibuat.
3. **Nilai tidak diformat**, dan `{{ }}` tidak ditulis seperti contoh user.

**Perubahan:**
- Setiap tabel yang dirilis dibuatkan:
  - satu baris pola, misalnya `out.o3.rows[ticker=<ticker>].<kolom>` beserta daftar kolom angka dan satuannya;
  - alamat untuk **setiap baris** sampai batas (usul 30 baris × kolom angka). Tabel yang lebih besar mendapat pola,
    daftar nilai kolom pengenal, dan catatan bahwa baris lain memakai pola yang sama.
- Setiap baris menu ditulis seperti contoh user: `nama: nilai terformat → {{alamat}}`, dengan satuan.
- Batas per hasil dinaikkan sesuai ukuran token yang diukur. Kenaikan token masukan dilaporkan; ditinjau ulang bila
  lebih dari 10%.

**Berkas dan tes:**
- `value_refs.py` (`menu`, `_menu_leaves`, `_row_example`), `orchestrator.py` (`ADDRESS_MENU_MAX`,
  `ADDRESS_MENU_NOTE`);
- tes `tests/test_address_menu.py`: semua baris tabel kecil, pola tabel besar, format seperti contoh;
- `tests/test_prompt_pass2.py` bila catatan berubah.

**Verifikasi:** golden test berikutnya. Kutipan baris selain baris contoh harus lolos tanpa REFERENCE; jumlah alamat
yang disusun sendiri dicek dari log pikiran.

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
