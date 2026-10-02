# Golden test sesudah HIGH ALERT langkah 1–5: before vs after (2026-10-02)

## Yang diuji

- **Run after:** `ma-golden-20261002c` (prefix request id), runner `orc-test-runner` deployment `7959d2cf`, suite
  commit `ea17bb1`, 19:30–20:01 UTC, 2 worker.
  - Diuji: sandbox `b1983cf7`, orc `b3aaae90`, cabang `claude/g2-g3-reactivation` `c625aa3`/`00cc597`.
  - Database: migrasi `20261003_001` sampai `20261003_003`.
  - Model `deepseek/deepseek-v4.1-flash` (switch 1), mode default 4.
- **Run before:**
  - `ma-golden-20261002a` (g1–g5; g5 giliran 6–9 gagal karena batas kunci OpenRouter, R25);
  - `ma-golden-20261002b` (g5, 9 giliran);
  - `ma-g6-20261002a` (g6).
- **Audit:**
  - market-audit-store menyimpan jejak lengkap per request id. Readback otomatis dibuat untuk item non-percakapan
    (8 giliran); readback tambahan `ma-audit-20261002c` (`b45aef68`, tanpa model) untuk lima sub-request mode 4.
  - Data baris tidak disalin ke GitHub; log dan dump mentah ada di scratchpad sesi.
- **Biaya model run after:** USD 1,26 untuk 25 giliran (jumlah `cost` yang dilaporkan per giliran).
- **Satu item baru:** `g6_revise_threshold` (percakapan: pertanyaan g6 → "Setuju" → "Ubah ambang suksesnya jadi naik
  minimal 5%" → "Setuju").

## Ringkasan verdict

| Masalah | Verdict | Bukti |
|---|---|---|
| **S27** tabel alur event study | **TERBUKTI** | g3: `_flow` dirilis dan diverifikasi (`out_cb59…`, 88.326 nilai dicek, 0 beda). Jawaban mengutip 3.658 memenuhi syarat → 1.387 tumpang tindih → 13 terpotong → 2.258 dipakai; pembanding "bukan-event". Before: tanpa tabel alur, label tertukar |
| **H1** definisi per tabel | **TERBUKTI untuk jalur analisis; SEBAGIAN untuk riset** | Jalur analisis: 100% output membawa `definition` (g1 5/5, g1_repeat 2/2, g2 1/1, g3 4/4, g4 6/6, g6 4/4, g7 giliran 2 8/8); before 0. Jalur riset multi-sudut (mode 4): hanya sebagian (g5 giliran 1 3/11, g5 giliran 8 0/8, g6_revise giliran 1 2/10); output `research_*` tidak diwajibkan membawa definisi |
| **M63** informasi antar giliran | **TERBUKTI (g7, g5 giliran 3); ada celah baru M68** | g7 giliran 2 tetap di pasar Nego, 5 saham dan angka sama dengan giliran 1, membuka tabel asal (`get_session_output` ×3). g5 giliran 3 menjelaskan RB dari tabel yang dirilis sebelumnya (132 hari crash, 116 hari beli, 87,9%), tanpa menebak papan. Before (run a): penjelasan menghitung ulang dengan papan Reguler hasil tebakan. Celah: catatan data menampilkan "Industry EQ" / "Market Board EQ" tanpa nilainya (M68) |
| **M28** ambang sukses dari user | **TERBUKTI di jalur hipotesis (G3); BELUM di jalur multi-sudut (M69)** | g6 (RESEARCH): temuan membawa `success_rule {">=", 3}` yang dicek cocok dengan rencana; frekuensi naik ≥ 3% 33,29% vs 23,33%. Before: mesin memakai > 0 dan baru dibetulkan karena AI kebetulan sadar. g6_revise (mode 4, multi-sudut): sudut-sudut menguji selisih rata-rata, bukan aturan ≥ 3%/≥ 5%. AI mengungkapkannya dengan jujur, tetapi porsi ≥ 5% hanya dihitung kode AI (tidak diverifikasi backend) |
| **M29** angka di rencana harus bersumber | **TERBUKTI** | g6 giliran 1: gerbang `PLAN_PROVENANCE` menolak "59%" yang tidak bersumber, AI memperbaiki. Before: rencana menyebut 6 bank lalu eksekusi 48 |
| **S13** rekaman ganda | **TIDAK MUNCUL LAGI** | 0 INVALID `DUPLICATE_ANGLE_OUTPUT` dari 25 sudut riset (run a: 4, run b: 0). Penolakan host `ANGLE_ALREADY_RECORDED` tidak terpicu, jadi jalurnya belum teruji live |
| **M25** semua completion tercatat | **TERBUKTI** | g3: `analysis_final_statuses` memuat 3 completion; g7 giliran 2: 3. Before: field tidak ada, hanya completion terakhir |
| **C06** data hari ini dipakai | **BELUM BISA DINILAI** | Cron dua kali sehari baru aktif 17:26 UTC, setelah jadwal 10:30 UTC lewat. Katalog masih `last_checked_at 00:32 UTC`, data sampai 2026-10-01. Uji pertama yang sah: setelah 10:30 UTC 2026-10-03 |
| **M66/M13** definisi "paling likuid" sama saat diulang | **MASIH TERJADI (H3 belum dibuat, sesuai rencana)** | g1: rata-rata nilai transaksi harian, min 200 hari → BBKP masuk. g1_repeat: median, min 100 hari → BTPS masuk. Keduanya menyebut definisinya (H1 bekerja), tetapi definisinya berbeda |
| **M26** efek minimal dari user | **MASIH TERJADI (keputusan user)** | g6_revise giliran 4: backend memakai 0,50 pp (biaya transaksi), bukan 1 pp dari user |

## Per item dan giliran

Kolom: status / waktu (detik) / biaya USD. Output = output yang dirilis; "def" = output yang membawa definisi.

| Item:giliran | Before | After | Catatan after |
|---|---|---|---|
| g1:1 | COMPLETED / 52 / 0,034, 2 output, def 0 | COMPLETED / 244 / 0,041, 5 output, def 5 | Gerbang referensi menolak 1×; Regular, 10 ticker sama dengan before |
| g1_repeat:1 | (baru) | COMPLETED / 39 / 0,032, def 2/2 | Definisi likuid berbeda dari g1 (M66) |
| g2:1 | COMPLETED / 38 / 0,022 | COMPLETED / 109 / 0,022, def 1/1 | Tanggal min/maks per saham 2025 |
| g3:1 | COMPLETED / 48 / 0,023, tanpa `_flow` | COMPLETED / 49 / 0,029, `_flow` terverifikasi, 3 completion | S27 terbukti |
| g4:1–2 | plan → COMPLETED / 44 / 0,022 | plan → COMPLETED / 76 / 0,018, def 6/6 | Temuan `h1` NOT_SUPPORTED; balasan akhir sekali ditolak skema |
| g5:1 | plan / 670 (a), 512 (b) | plan / 751 / 0,238 | Crash = rata-rata ≤ −1%, 132 hari, RB teratas (sama dengan run b, beda dengan run a: M66) |
| g5:2 | COMPLETED / 13 | COMPLETED / 13 | Penjelasan angka |
| g5:3 | COMPLETED / 85 (a) | LIMITED / 150 | Penjelasan dari tabel asal; analisis baru tidak bisa karena slot sesi penuh (S28) |
| g5:4 | COMPLETED / 331 (a), LIMITED (b) | plan / 168 | Mode 4: event study diajukan sebagai revisi usulan, bukan dijalankan langsung |
| g5:5 | plan / 85 | plan / 90 | Ide BUMN |
| g5:6 | FAILED (a, R25), COMPLETED (b) | COMPLETED / 14, 3 sudut NOT_RUN | `research_group_failed SESSION_CAPACITY_EXCEEDED` (S28) |
| g5:7–8 | (b) plan → 4 sudut INSUFFICIENT_EVIDENCE | plan → 4 sudut INSUFFICIENT_EVIDENCE | Dua dataset kosong (`EMPTY_DATASET`), tetapi bundle READY dan cakupan PASS (G19) |
| g5:9 | COMPLETED / 31 (b) | COMPLETED / 31 | Menjelaskan hasil uji tadi, termasuk input kosong |
| g6:1–2 | plan → COMPLETED / 44 / 0,036 | plan → COMPLETED / 267 / 0,038 | M28 terbukti; M29 gerbang terpicu; output terpotong 24.000 token 1×; efek minimal 0,01 vs satuan persen (P26) |
| g6_revise:1–4 | (baru) | plan / 278 → plan / 95 → plan / 103 → COMPLETED / 73 | Lihat M69 |
| g7:1–3 | (baru) | plan / 436 → COMPLETED / 130 → plan / 51 | Nego dipertahankan di giliran 2 dan 3 |

## Error baru dari run ini

Semuanya dicatat di `ERRORS_AND_SOLUTIONS.md`, statusnya OPEN, dan belum diperbaiki (pekerjaan kode dikunci sampai
user memutuskan).

| ID | Ringkas | Akar masalah |
|---|---|---|
| **M68** | Catatan data menulis "Industry EQ" tanpa "Banks" | Terverifikasi. Bentuk kanonik scope dari sandbox memakai `values` (daftar), sedangkan `data_record.scope_text` di orc hanya membaca `value` |
| **S28** | `SESSION_CAPACITY_EXCEEDED` di g5 giliran 3 dan 6 | Terverifikasi. Hanya 2 slot. Sesi yang sudah selesai tetapi menjalankan kode lagi kembali ACTIVE, tidak bisa digusur, dan tidak dilepas di akhir run, sehingga menahan slot sampai 900 detik (`sess_343e…`, g7 giliran 2) |
| **M69** | Ambang sukses user tidak mengikat jalur multi-sudut (mode 4) | Terverifikasi. Rencana multi-sudut tidak punya `success_rule`; metode riset menguji selisih rata-rata |
| **P26** | Efek minimal 0,01 (desimal) dibandingkan dengan MDE 2,82 (persen); rekomendasi sampel 14.868.205 | Terverifikasi dari temuan. Satuan efek minimal di rencana tidak diselaraskan dengan satuan hasil `event_summary` |
| **G19** | Dataset riset kosong tetap READY / cakupan PASS; 4 sudut dijalankan di atas input kosong | Terverifikasi: kosong tetapi PASS. Penyebab kosongnya belum terverifikasi: argumen `check_research_feasibility` di jejak audit terpotong di 2.018 karakter |

## Catatan alur mode 4 (bukan error)

- Di mode 4, satu giliran berisi analisis, lalu rencana riset yang langsung dijalankan, lalu satu usulan lanjutan.
  Usulan lanjutan itulah yang menunggu persetujuan.
- Akibatnya "Setuju" di g6_revise menyetujui usulan lanjutan, dan pesan "bandingkan 2024" di g7 dibaca sebagai
  revisi usulan.
- Naskah g6_revise dan g7 perlu ditulis ulang untuk alur ini kalau ingin menguji perubahan ambang pada rencana utama.
