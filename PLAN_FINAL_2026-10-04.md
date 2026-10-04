# Rencana final putaran 2026-10-04

Status: **FINAL, disetujui user 2026-10-04, belum dieksekusi.** Dokumen ini menggantikan `PLAN_ROUND_2026-10-04.md` dan
`PLAN_EVIDENCE_GATE_2026-10-04.md` (keduanya disimpan sebagai riwayat diskusi). Dasar bukti:
`GT_ANALYSIS_2026-10-04.md`, `GOLDEN_TEST_ROUND_2026-10-03.md` bagian 3, dan `ERRORS_AND_SOLUTIONS.md` (G22, G23, P27,
M71, M72, M73).

## Prinsip yang dipakai semua solusi

Setiap solusi diuji dengan tiga pertanyaan; yang gagal tidak masuk rencana.
1. **Kelas, bukan kasus:** solusi menangani mekanismenya, tanpa menyebut tabel, ticker, skenario dialog atau model
   tertentu.
2. **Turunkan, jangan daftar:** pengetahuan yang dibutuhkan (alat yang dipegang, asal angka, nilai data, satuan) dibaca
   dari sistem saat berjalan, bukan ditulis tangan.
3. **Lapisan yang tepat:** sistem yang menegakkan; instruksi ke AI hanya penjelas.

## Keputusan user (2026-10-04)

| No | Keputusan |
|---|---|
| K1 | Model aktif `xiaomi/mimo-v2.6-flash`, reasoning high; diukur dulu lewat golden test kecil sebelum dipakai luas |
| K2 | AI diberi tahu bahwa gerbang bukti hanya menolak sekali, dan jalan keluarnya |
| K3 | Tidak ada gagal total: saat batas langkah habis, jawaban terakhir tetap sampai ke user dengan catatan dan kode permintaan. Rem otomatis (pemutus loop) **tidak** dikerjakan |
| K4 | Satuan uji dicek dengan **hitung ulang**, bukan aturan skala |
| K5 | Nilai kosong dibuang dari kedua kelompok |
| K6 | Prinsip "Pilihan AI": sistem melacak asal setiap masukan dan menampilkan pilihan AI; tidak memblok, tidak mewajibkan bertanya. Bila ambigu, cukup dinyatakan |
| K7 | Kirim ulang catatan pikiran AI di dalam satu jawaban (S4c) |
| K8 | Pencari fakta web ringan, maks. 30 detik (S4b), masuk putaran ini |
| K9 | Perbaikan G22 nomor 1–3 (satu timeout per pesanan, antrean query berat, simpan percakapan coba sekali lagi) |
| K10 | Golden test setelah semua fase, mencakup perbaikan putaran ini **dan** daftar "menunggu golden test" |
| K12 | Router: salah baca saat ada usulan riset menunggu (S7), benchmark dulu sebelum diperbaiki |
| K11 | ~~S6~~ **ditarik.** Mode 4 menjalankan riset untuk setiap pertanyaan analisis baru **sesuai desain** (arahan user 2026-10-02, `MODE4_CONVERSATION_PLAN.md` tujuan 1). Pertanyaan lanjutan sudah tidak memicu riset (router). Kelambatan kasus tabel g9.1 ditangani G23 |

**Masih menunggu keputusan user (tidak dikerjakan di putaran ini):**
- keputusan 6 (kolom BUMN resmi);
- S7 (pengaturan provider);
- G22-6 (database terpisah);
- rotasi kunci audit (R21).

## Urutan

| Fase | Isi | Layanan |
|---|---|---|
| 1 | Ganti model + uji tingkat reasoning + golden test kecil | orc (setelan) |
| 2 | G23: alat di meja AI, gerbang bukti, jalan keluar; S7 router saat usulan menunggu | orc |
| 3 | Kebenaran jawaban: S3 satuan, S5 nilai kosong, S4 "Pilihan AI", S4c catatan pikiran | sandbox, orc |
| 4 | S4b pencari fakta web ringan | web-governor, orc |
| 5 | G22 database | Governor, orc |
| 6 | Golden test akhir + hitung ulang independen | runner, job baca-saja |

Setiap fase:
- dites lokal;
- dideploy ke **dev saja** dari cabang `claude/g2-g3-reactivation` lewat CLI upload;
- variabel diubah dengan `--skip-deploys`, lalu redeploy cabang dan dicek bahwa deployment bukan dari `main` (pelajaran
  R31);
- deployment dibaca sampai `SUCCESS`;
- dicatat.

---

## Fase 1 — Ganti model (K1)

**Fakta (OpenRouter, 2026-10-04):**

| Model | Input / 1 jt token | Output / 1 jt | Cache / 1 jt |
|---|---|---|---|
| `xiaomi/mimo-v2.6-flash` | USD 0,14 | 0,28 | 0,003 |
| `deepseek/deepseek-v4.1-flash` (sekarang) | 0,003 | 2,40 | 0,003 |

Keduanya mendukung alat dan reasoning.

Dua catatan:
- **Biaya ditentukan cache.** Dengan token test kemarin, biaya MiMo flash: USD 0,94 bila cache ±90%, USD 3,50 bila 50%,
  USD 6,05 tanpa cache. DeepSeek kemarin: USD 2,18.
- **Tingkat reasoning belum pasti diterima.** Kode kita mengirim "reasoning nyala" saja untuk model 2
  (`Settings.reasoning`).

**Langkah:**
1. **Uji tingkat reasoning** (± USD 0,05): prompt sama dengan `effort: high`, `effort: low`, `enabled: true`; bandingkan
   token reasoning.
   - Bila diterima, bentuk pengiriman disimpan sebagai setelan per model (`AI_MODEL_2_REASONING_FORM = effort | enabled`)
     dan `high` dikirim.
   - Bila tidak, user diberi tahu.
2. **Setelan dev:** `AI_MODEL_2=xiaomi/mimo-v2.6-flash`, `AI_MODEL_SWITCH=2`. `AI_MODEL` (DeepSeek) tetap, sebagai jalan
   kembali (`AI_MODEL_SWITCH=1`). AGENTS.md diperbarui (keputusan model).
3. **Golden test kecil** (3 worker), kode sekarang: g1, g4, g8, g9 (3 pesan), g5 pesan 1–4. Dibandingkan dengan
   `ma-golden-20261004a`:
   - angka (job baca-saja);
   - detik, biaya, rasio cache;
   - penolakan argumen alat;
   - format jawaban.

**Berhenti dan lapor** bila biaya > USD 0,15 per pesan, atau angka yang dulu terverifikasi benar menjadi salah.

| Risiko | Mitigasi |
|---|---|
| Kualitas pemakaian alat / JSON turun | Golden test kecil dulu; kembali ke model 1 dengan satu setelan |
| Cache rendah, biaya naik sampai ±3× | Rasio cache diukur; batas biaya per pesan di atas |
| Uptime provider bervariasi | Error provider dicatat; routing tidak diubah tanpa izin (S7) |

---

## Fase 2 — G23: alat di meja AI, gerbang bukti, jalan keluar

**Akar masalah (terverifikasi di log dan kode):** tiga bagian sistem membaca daftar alat **seluruh kantor**, sementara
AI hanya memegang sebagian:
- gerbang bukti (`self.registry.names()`);
- alat `get_system_capabilities` (`available_tools = registry.names()`);
- teks perintah gerbang.

Dampak di putaran `ma-golden-20261004a`:
- gerbang meminta `get_evidence` di 17 langkah yang tidak punya alat itu;
- terbuang 245 panggilan model (29%), 1.663 detik (19%), USD 0,39 (18%);
- g9.2 gagal di 60 iterasi, padahal jawaban benar sudah ada di iterasi 2.

**A. Satu sumber kebenaran: alat di meja langkah ini.**
- Orchestrator menyimpan set alat yang benar-benar ditawarkan (`RunState.offered_tools`), di tempat yang sama dengan
  daftar alat yang dikirim ke model.
- Pembaca set itu:
  - **gerbang:** setiap gerbang mendeklarasikan alat perbaikannya; bila alat tidak ada di meja, gerbang tidak meminta
    perbaikan dan langsung memakai catatannya;
  - **`get_system_capabilities`:** `available_tools` = meja langkah ini; alat lain di `other_tools_not_in_this_step`;
  - **teks perintah.**

**B. Bukti diminta hanya untuk angka yang perlu, diturunkan dari asal angka.**
- Angka yang dihitung ulang backend (temuan riset, ringkasan Governor, `query_metric`) tidak dicek lagi; labelnya
  "dihitung ulang backend".
- Angka dari kode AI dicek sekali bila alatnya ada; bila tidak, diberi label "belum dicek ulang".
- `get_evidence` (hanya membaca dan menghitung ulang; menulis bukti milik percakapan itu) masuk set alat baca-saja.

**C. AI diberi tahu aturannya (K2).**
- Perintah gerbang menyebut bahwa ia hanya meminta sekali, dan bahwa jawaban yang dikirim ulang tanpa perubahan akan lolos
  dengan catatan.
- Berlaku untuk semua gerbang yang memakai `_gate_once`.

**D. Tidak ada gagal total (K3).**
- Saat batas langkah atau waktu habis, draf terakhir dijalankan sekali lagi melewati semua gerbang dalam mode tanpa
  perbaikan (`FORCED_LIMITATION`), lalu dikirim sebagai `LIMITED` dengan catatan "pemeriksaan tidak selesai, kode
  permintaan: …".
- Tanpa draf: "Tidak bisa dihitung: <yang kurang>. Kode permintaan: …".
- `error.code` tetap dicatat.

| Risiko | Mitigasi |
|---|---|
| Lebih banyak jawaban tanpa cek angka | Label selalu tampil; angka riset sudah dihitung ulang backend |
| `get_evidence` di langkah baca ulang menambah beban Governor | Batas yang ada: 10 klaim, 30 detik per query, 120 detik total |
| Draf terakhir berisi angka salah | Draf tetap melewati semua gerbang |

**Tes:**
- kontrak: setiap jenis gerbang × setiap set alat (router dan mode 4) tidak pernah meminta alat yang tidak ada;
- `get_system_capabilities` per langkah;
- putar ulang g9.2: jawaban dalam ≤ 3 iterasi, tanpa `MAX_ITERATIONS`;
- langkah analisis tetap ditolak sekali (kasus yang tidak berubah);
- batas langkah habis: dengan draf, draf dengan angka tanpa sumber, dan tanpa draf.

**Ukuran:** panggilan setelah gerbang di langkah tanpa alat = 0 (baseline 245); gagal total = 0 (baseline 1).

### S7. Router salah baca saat ada usulan riset menunggu (K12)

- **Masalah (terverifikasi di log):** 9 pesan lanjutan dinilai router; 8 benar. Yang salah adalah g7.3 "Bandingkan dengan
  tahun 2024 memakai definisi yang sama".
  - Saat itu ada usulan riset menunggu (dari g7.1), sehingga pesan dibaca sebagai **REVISE** usulan.
  - User mendapat rencana riset revisi, bukan angka 2024.
  - Pola yang sama pernah terjadi ("kalau hanya bank BUMN?").
- **Akar:** `apply_rules` (aturan 5) mensyaratkan `referent = PENDING_SUGGESTION` untuk APPROVE/REVISE **hanya bila** ada
  hasil baru setelah usulan. Di g7, pesan 2 hanya klarifikasi (tanpa hasil baru), jadi syarat itu tidak aktif.
- **Kelas masalah:** setiap pesan yang menyebut perubahan (tahun, kelompok, ambang) saat ada usulan menunggu.
- **Langkah:**
  1. **Benchmark dulu:**
     - Kumpulkan semua pesan yang dikirim saat ada usulan menunggu, dari semua suite dan log golden test.
     - Beri label: revisi usulan / pertanyaan tentang hasil / permintaan baru.
     - Ukur router sekarang (2 model × 3 ulangan).
  2. **Perbaikan yang diuji (orc, permanen, satu aturan umum):** APPROVE/REVISE berlaku hanya bila `referent =
     PENDING_SUGGESTION`, **selalu**, bukan hanya saat ada hasil baru. Bila ragu, pesan diperlakukan sebagai pertanyaan
     atau permintaan (jalan termurah), dan usulan tetap menunggu (aturan 4 yang sudah ada).
  3. Perbaikan diterapkan hanya bila benchmark menunjukkan perbaikan tanpa menurunkan pengenalan revisi yang
     benar-benar dimaksud ("ubah ambang suksesnya jadi 5%", "sarannya pakai 5 tahun saja").
- **Risiko:** revisi yang sah tidak dikenali. **Mitigasi:** benchmark mengukur dua arah; usulan tidak hilang, jadi user
  bisa mengulang dengan menyebut usulannya.
- **Tes:**
  - g7.3 → pertanyaan, bukan revisi;
  - g6_revise.3 "Ubah ambang suksesnya jadi naik minimal 5%" → tetap revisi;
  - "kalau hanya bank BUMN?" saat usulan menunggu → pertanyaan.

### Catatan: S6 ditarik (2026-10-04)

- Mode 4 menjalankan analisis → rencana riset → riset → usulan untuk setiap pertanyaan analisis baru. Ini **desain yang
  disetujui user** (tujuan 1 di `MODE4_CONVERSATION_PLAN.md`), bukan cacat.
- Pertanyaan lanjutan (klarifikasi, wawasan, penjelasan) sudah ditangani router tanpa riset.
- Waktu kasus tabel g9.1 (877 detik):
  - jawaban 24 detik;
  - rencana 113 detik;
  - riset 619 detik, di mana ± 553 detik adalah loop G23 setelah gerbang bukti;
  - usulan 23 detik.
  - Tanpa loop, riset ± 66 detik, sehingga waktu model total ± 4 menit. Ini diperbaiki di Fase 2.
- Benchmark router (61 pesan) tetap tercatat di `GT_ANALYSIS_2026-10-04.md` sebagai bahan bila mode bawaan suatu saat
  diubah.

---

## Fase 3 — Kebenaran jawaban

### S3. Satuan hasil uji dicek dengan hitung ulang (P27, K4)

- **Akar:** kode AI g5.6 mengirim return pecahan (`close.shift(-5)/close - 1`) ke `event_summary` di bawah rencana
  PERSEN. Niat "×100" ada di reasoning, tidak di kode. Sandbox menerima satuan apa pun; penjaga P26 hanya memeriksa arah
  sebaliknya.
- **Solusi (sandbox):**
  1. Untuk hasil berbasis harga, backend menghitung ulang contoh ≤ 500 baris dari harga yang ia pegang dan membandingkan
     rasio. Rasio ±100 ditolak dengan pesan jelas.
  2. Helper `forward_return(prices, horizon)` menghitung dalam satuan rencana.
  3. Hasil bukan harga diberi status "satuan dideklarasikan, tidak dicek".
- **Bukti:**
  - aturan skala sederhana ditolak: pada 6.150 saham-tahun tidak ada ambang aman (1,3% data persen salah tangkap, return
    20 hari > 1);
  - hitung ulang membandingkan rasio tepat 100.
- **Tes:**
  - g5.6 ditolak;
  - persen benar lolos;
  - saham tidur tidak salah tangkap;
  - horizon 1, 5 dan 20 hari.

### S5. Nilai kosong dibuang dari kedua kelompok (M72, K5)

- **Akar:** kode AI g6_revise menulis `baseline = … | rsi14.isna()`; run lain menulis `notnull()`. Helper tidak
  menegakkan aturan.
- **Solusi (sandbox):** `event_summary` dan helper riset membuang baris dengan kondisi atau hasil kosong dari kedua
  kelompok dan melaporkan `rows_condition_undefined`.
- **Bukti:** hitung ulang independen memberi 84.166 baris pembanding; g6_revise memakai 84.819 (+672 = 48 × 14 hari
  pemanasan RSI).
- **Tes:**
  - kosong di awal (pemanasan);
  - kosong di tengah (celah);
  - hasil kosong di akhir periode.

### S4. Semua pilihan AI terlihat (M71; juga M13, P25, P05/P08; K6)

**Prinsip:**
- Sistem sendiri yang melacak asal setiap masukan yang dipakai AI. Apa pun yang bukan dari data atau dari user otomatis
  ditampilkan sebagai **"Pilihan AI"**.
- Tidak memblok apa pun, tidak mewajibkan AI bertanya, tidak butuh daftar skenario.
- Bila ambigu, cukup dinyatakan; jawaban `CLARIFICATION` yang sudah ada tetap boleh dipakai AI, tidak diwajibkan.

**Cara kerja (sandbox + orc):**
1. Setelah kode AI berhasil jalan, sistem membaca nilai yang **diketik** AI untuk menyaring, mengelompokkan atau sebagai
   ambang. Ini perluasan pembacaan angka tertulis yang sudah ada (P25). Nilai yang dihitung dari data tidak termasuk.
2. Asal tiap nilai ditentukan otomatis:
   - ada di pesan user (termasuk nama perusahaan ↔ ticker lewat tabel referensi, persen ↔ pecahan) → **dari user**;
   - ada sebagai nilai di data yang dimuat kode, atau di hasil alat sebelumnya di percakapan ini → **dari data**;
   - selain itu → **Pilihan AI**.
3. Orc menulis bagian "Pilihan AI" di jawaban (dan di rencana bila pilihannya sudah ada saat itu). Bagian ini ditulis
   oleh sistem, bukan oleh AI, dan ikut di definisi hasil, lineage dan ekspor.
4. Gerbang angka tidak lagi menolak angka dari kode AI sendiri; angka itu dipindah ke "Pilihan AI". Ini menutup
   P25/P05/P08.

**Contoh skenario tanpa aturan khusus.** "Cari broker yang akumulasi" → "kamu yang tentukan berdasarkan X":
- AI memilih dengan menghitung dari data, sehingga tercatat "dari data" beserta cara hitungnya;
- AI mengetik daftar dari ingatan, sehingga tampil "Pilihan AI: AK, BK, …";
- AI bertanya dulu: boleh.

BUMN, broker, sektor, dan nanti negara atau seri makro memakai mekanisme yang sama.

**Bukti (prototipe pada 59 eksekusi kode nyata):**

| Kode | Ditandai | Tepat? |
|---|---|---|
| g5.6 | BBCA, BBNI, BBRI, BBTN, BMRI, BRIS; persentil 95 | Ya |
| g6 | 2,5 dan 97,5 (batas interval 95%) | Ya, pilihan metode AI |
| g6 ambang 30, 3%, 10 hari | Tidak ditandai | Ya, dari kata-kata user |
| 55 kode lain | Tidak ada | Ya |

Prototipe memakai 48 ticker bank sebagai nilai data; versi sebenarnya memakai nilai dari dataset yang dimuat.

**Catatan koreksi (log reasoning):** daftar BUMN di g5.5 tampil di bagian Asumsi rencana, tetapi tanpa label sumber,
dan disetujui oleh runner otomatis. Label "Pilihan AI" dari sistem membuatnya menonjol, tetapi tetap bergantung pada
user membacanya. Pencegahan sebenarnya datang dari S4c dan S4b.

**Batasan:**
- Mekanisme ini membuat tebakan terlihat, bukan benar.
- Daftar yang disusun di kode setelah rencana disetujui tampil di jawaban, tidak di rencana.
- Data BUMN resmi bergantung pada keputusan 6.

| Risiko | Mitigasi |
|---|---|
| "Pilihan AI" penuh hal remeh | Hanya nilai untuk menyaring, mengelompokkan atau ambang; 0/1 diabaikan; prototipe: 4 dari 59 |
| Nilai dari user tidak dikenali | Pencocokan nama ↔ ticker dan persen ↔ pecahan; salah kenal hanya menambah satu baris, tidak menolak |
| User tidak membaca | Bagian ini di atas asumsi; ikut di bukti dan ekspor |

**Tes:**
- g5.6 menampilkan daftar dan persentil;
- g6 tidak menampilkan ambang dari user;
- P25 "persentil ke-90" tidak lagi menyebabkan LIMITATION;
- daftar kode broker tertulis di kode ditampilkan;
- pilihan dari data lewat kode tidak ditandai.

### S4c. Catatan pikiran AI dikirim ulang di dalam satu jawaban (K7)

- **Akar (terverifikasi di kode):** `orchestrator._handle_call`: "provider reasoning items are never replayed".
  - Di g5.5, kesimpulan "BBCA is private (Djarum); BUMN = BMRI, BBRI, BBNI, BBTN" (iterasi 1–2) dibuang.
  - Pada iterasi 5 daftar disusun ulang tanpa kesimpulan itu, dan memuat BBCA. Kemungkinan terbawa dari "empat bank besar:
    BBCA, BBRI, BMRI, BBNI" di jawaban g5.4; ini dugaan kuat.
  - Pola yang sama menjelaskan niat "×100" yang hilang di P27.
- **Kelas masalah:** setiap kesimpulan antara yang hanya ada di reasoning bisa hilang di langkah berikutnya dalam run yang
  sama.
- **Praktik penyedia:** OpenRouter menyarankan mengirim ulang blok reasoning (`reasoning_details`) saat memakai alat.
- **Solusi (orc):**
  - kirim ulang item reasoning dari panggilan sebelumnya di run yang sama, persis seperti diterima;
  - antar pesan percakapan tidak dikirim;
  - bila model atau provider menolak, kembali ke mode sekarang dan dicatat;
  - setelan `AI_REPLAY_REASONING`.

| Risiko | Mitigasi |
|---|---|
| Token input naik (± 1,5–5 rb per langkah) | Diukur bersama rasio cache; bisa dimatikan |
| Format ditolak provider | Fallback otomatis, dicatat |

**Tes / benchmark:** ulangi g5.4 → g5.5 tiga kali dengan dan tanpa replay. Ukur apakah daftar akhir sesuai kesimpulan
awal di reasoning, dan biaya per pesan.

---

## Fase 4 — S4b pencari fakta web ringan, `find_web_fact` (K8)

**Kenapa tidak memakai jalur yang ada:**
- `/v1/ask` adalah riset berita: model perencana, 8 jendela waktu × Google News, hingga 8 putaran tinjauan, baca artikel,
  jawaban dengan reasoning, implikasi, pertanyaan lanjutan; batas 180 detik.
- `/v1/search`: satu kriteria, selalu minta 2 domain (W06), provider bisa 2–4 pencarian (W08), kutipan tanpa tanggal
  (W07).

**Endpoint baru `POST /v1/fact` (market-web-governor), memakai ulang komponen yang ada:**
1. **Cache:** tabel `web_fact` di Postgres-E8GM, kunci (subjek, atribut), TTL misalnya 30 hari; cache hit < 1 detik.
2. **Dua pencarian paralel tanpa model perencana:** query dari kode; satu umum, satu dibatasi domain resmi (kebijakan
   sumber yang ada); masing-masing ≤ 5 hasil, satu pencarian.
3. **Satu panggilan model kecil, tanpa reasoning, JSON ketat:** membaca cuplikan saja; nilai per sumber dan kutipan
   verbatim.
4. **Kode yang memutuskan status:**
   - kutipan harus ada di cuplikan (logika `VERIFIED_QUOTE`);
   - `CONFIRMED`: ≥ 2 domain independen setuju, atau 1 resmi;
   - `CONFLICTING`: kedua versi ditampilkan;
   - `NOT_FOUND`.
5. **Batas keras 30 detik;** lewat dari itu, hasil yang ada dikembalikan sebagai `PARTIAL`/`NOT_FOUND`.
6. **Disimpan** dengan kutipan, URL, tanggal bila ada, sumber.

**Sisi orc:**
- Alat `find_web_fact(subject, attribute)` untuk fakta yang **tidak ada di data**: keanggotaan kelompok, pemegang saham
  pengendali, status perusahaan.
- Hasilnya masuk ke "Pilihan AI / Sumber" dengan label `WEB`, kutipan dan status.
- Nama `lookup_fact` sudah dipakai untuk fakta gudang data.

**Perkiraan:** 10–20 detik, < USD 0,01 per fakta; cache < 1 detik.

**Benchmark sebelum dinyalakan:** set fakta dengan jawaban diketahui:
- status BUMN 10 bank, termasuk BBCA (swasta) dan BRIS (anak usaha);
- pemegang saham pengendali 5 emiten;
- anggota indeks 5 saham.

Diukur: akurasi, `CONFLICTING` yang benar, waktu p95 ≤ 30 detik, biaya.

| Risiko | Mitigasi |
|---|---|
| Hanya cuplikan dibaca | `NOT_FOUND`, bukan tebakan; opsional satu `/v1/fetch` ke sumber resmi bila waktu tersisa |
| Sumber usang, tanggal kosong | Sumber resmi diutamakan; tanggal ditampilkan; TTL |
| Pencarian berlebih dari provider (W08) | Batas biaya per fakta dan per percakapan |
| Sumber bertentangan | `CONFLICTING` dengan kedua kutipan |
| Fakta berubah | `as_of` dan TTL |

**Tes:**
- `/v1/fact` dengan provider palsu: CONFIRMED, CONFLICTING, NOT_FOUND, PARTIAL di 30 detik, kutipan tidak verbatim
  dibuang, cache hit;
- orc: hasil masuk ke "Pilihan AI / Sumber";
- alat hanya ada bila setelan dinyalakan.

---

## Fase 5 — G22 database (K9)

**Akar (terverifikasi):**
- 5 worker: 45 pembatalan dalam 7 menit; simpan percakapan (batas 5 detik) gagal, sehingga rencana g4 hilang dan riwayat
  g5 tidak terbaca.
- Hitungan baris Governor yang selalu habis waktu: putaran 3 hanya 24 dari 612 (4%), tetapi memakan 57% waktu database
  untuk hitungan. Putaran 2: 21 timeout untuk satu pesanan data g1 yang dipecah.
- 3 worker: 0 kegagalan simpan.
- Dugaan disk jenuh belum diukur dengan metrik disk.

**Solusi:**

| # | Solusi | Bukti |
|---|---|---|
| G22-3 | Satu timeout per pesanan data cukup (Governor): bagian lain dari pesanan yang sama memakai perkiraan, karena pemecahan sudah membatasi tiap bagian | Memotong 20 dari 21 timeout g1 (± 140 detik) |
| G22-4 | Antrean query berat (Governor): maks. N bersamaan (setelan, awal 2), batas tunggu dan pesan "sedang antre" | 5 worker → 2 kegagalan; 3 worker → 0 |
| G22-5 | Simpan percakapan coba sekali lagi setelah jeda singkat (orc), dijaga nomor lease | Menutup momen sibuk seperti g4 |

Ditolak setelah diuji: "lewati hitungan bila perkiraan besar". Perkiraan tidak meramalkan timeout (ada yang 48 baris
tetap timeout; ambang 1 juta hanya menangkap 4/24).

| Risiko | Mitigasi |
|---|---|
| Bagian pesanan memakai perkiraan yang meleset 2–3× | Pemecahan membatasi ukuran; batas baris saat penarikan tetap |
| Antrean memperlambat saat ramai | Batas tunggu, pesan antre, N bisa diatur |
| Coba ulang menulis dua kali | Dijaga nomor lease; hanya bila percobaan pertama tidak tersimpan |

**Tes:**
- Governor: pesanan berpecahan dengan timeout pertama tidak menghitung bagian lain; antrean;
- orc: simpan gagal sekali lalu berhasil.

**Ukuran:** golden test 5 worker → 0 kegagalan simpan; ≤ 1 timeout per pesanan; pembatalan jauh di bawah 45.

---

## Fase 6 — Golden test akhir (K10)

Dijalankan setelah fase 1–5 terdeploy di dev. File suite sudah disiapkan:
- `apps/orc-test-runner/suites/final_20261004_A.json`
- `apps/orc-test-runner/suites/final_20261004_B.json`

Saat eksekusi, file disalin ke `suite.json` (runner membaca `suite.json`). Masa simpan sandbox 1 jam selama bagian A
(untuk g9); variabel diubah dengan `--skip-deploys`, lalu `railway redeploy`.

### Bagian A: 3 worker, 33 pesan (13 percakapan), perkiraan USD 2–3, ± 2 jam (termasuk jeda 66 menit g9)

| # | Item | Pesan | Membuktikan | Ukuran lulus |
|---|---|---|---|---|
| 1 | g1_foreign_net_banks | "Berapa total net beli investor asing di pasar reguler per saham untuk 10 saham bank paling likuid selama 2025?" | P22/P23, G16, M46/M48, model baru | Angka = hitung ulang independen (sudah diketahui: total −Rp 55,64 T) |
| 2 | g1_foreign_net_banks_repeat | sama, percakapan baru | M66/M13: definisi "paling likuid" dan 10 ticker sama | Daftar sama dengan #1 |
| 3 | g2_bank_minmax | "Berapa harga penutupan tertinggi dan terendah tiap saham bank selama 2025, dan berapa persen selisihnya?" | regresi | 48/48 cocok |
| 4 | g3_event_study | "Bagaimana return 5 hari saham bank setelah hari turun 5% atau lebih (event per saham, tidak tumpang tindih), dibanding hari-hari lainnya?" | P24/M65, S19, S22, S24 | 2.258 event, rata-rata 0,19%, median −0,37% |
| 5 | g4_hypothesis_bbca (2 pesan: tanya + setuju) | "Apakah hari dengan net beli asing positif di BBCA diikuti return 1 hari lebih tinggi daripada hari lainnya?" | P25/P20/P21, M62, S4 (pilihan AI) | ±1.026 event; selisih −0,05% |
| 6 | g5_conversation (9 pesan) | sama dengan suite sebelumnya | M64, G13, M47–M55, **S3** (pesan 6), **S4/S4b** (BUMN), **S4c**, **S7** (pesan 3, 7), G23 (pesan 2, 9) | Pesan 6: satuan benar atau ditolak; BUMN = BBRI, BMRI, BBNI, BBTN (web) atau tampil sebagai pilihan AI; 0 loop |
| 7 | g6_revise_threshold (4 pesan) | sama | **S5**, P26, **S7** (pesan 3 tetap revisi), S4 (ambang dari user tidak ditandai) | Pembanding 84.166 baris |
| 8 | g7_followup_definitions (3 pesan) | sama | M63/M66, **S7** (pesan 3 = angka 2024, bukan revisi) | Pesan 3 memberi net asing Nego 2024 per saham |
| 9 | g7_lineage_export (3 pesan) | sama | D3/D4 lineage + ekspor, G23 | Unduhan sha256 cocok, 0 loop |
| 10 | g8_metric | "Berapa net beli asing BBCA 5 hari dan 20 hari bursa terakhir?" | D5 `query_metric`, **B** (angka backend tanpa gerbang) | Sama sampai rupiah |
| 11 | g9_resume (3 pesan + jeda 66 menit) | sama | **G23** (pesan 2 menjawab), **D**, R-STORE resume | Pesan 2 BBRI −3,38%; 0 `MAX_ITERATIONS` |
| 12 | g11_plan_expiry (3 pesan + jeda 66 menit) | sama | rencana kedaluwarsa, riset tanpa gerbang bukti | Minta setujui ulang, lalu jalan |
| 13 | **g13_fact_bumn** (baru) | "Apakah BBCA dan BRIS termasuk bank BUMN? Sebutkan sumbernya." | **S4b** pencari fakta web | BBCA: bukan (swasta); BRIS: anak usaha BUMN; ≥ 2 sumber; `find_web_fact` ≤ 30 detik |

### Bagian B: 5 worker (G22)

g1, g2, g3, g5 pesan 1, g11 pesan 1, dijalankan bersamaan.

| Ukuran | Target |
|---|---|
| Kegagalan simpan percakapan | 0 |
| Timeout hitungan per pesanan data | ≤ 1 |
| Pembatalan database | Jauh di bawah 45 |

### Benchmark pencari fakta (S4b, sebelum alat dinyalakan untuk AI)

20 fakta dengan jawaban diketahui, langsung ke `/v1/fact`, tanpa model analis:
- status BUMN 10 bank: BBRI, BMRI, BBNI, BBTN (BUMN); BRIS (anak usaha); BBCA, BNGA, NISP, PNBN, BDMN (bukan);
- pemegang saham pengendali 5 emiten;
- 5 fakta keanggotaan indeks.

Ukuran: akurasi, status `CONFLICTING` yang benar, waktu p95 ≤ 30 detik, biaya per fakta.

### Benchmark router (S7, sebelum perbaikan)

Semua pesan yang dikirim saat ada usulan menunggu, dari suite dan log, dengan label. Diuji 2 model × 3 ulangan.

### Setiap putaran

- Angka dicek ulang lewat job baca-saja independen, lalu job dihapus.
- Biaya per pesan, per langkah dan per percakapan.
- Detik, rasio cache.
- Setiap kegagalan dicatat dengan akar masalah lebih dulu.

**Kriteria lulus keseluruhan:**

| Ukuran | Syarat |
|---|---|
| Panggilan terbuang setelah gerbang | 0 |
| Gagal total | 0 |
| g5.6 | Satuan benar (−0,41% vs −0,32%) atau ditolak |
| BUMN | Benar (web) atau tampil sebagai pilihan AI |
| g6 | 84.166 baris |
| g7.3 | Angka 2024, bukan revisi |
| Angka yang dulu benar | Tetap sama |
| Bagian B | 0 kegagalan simpan |

## Masalah "buntu" yang tidak selesai oleh putaran ini

Jalan keluar (D, S4) memastikan user selalu menerima jawaban, catatan atau pertanyaan. Akar berikut tetap perlu
perbaikannya sendiri:
- P05/P08: gerbang terlalu ketat. Sebagian tertutup oleh S4 butir 4; sisanya dicek di golden test.
- G10: penarikan data ditolak.
- D06: data broker berhenti 31 Agustus (muat ulang data).
- M42: salah jenis jawaban.

## Catatan yang diperbarui saat eksekusi

- `ERRORS_AND_SOLUTIONS.md`: G22, G23, P27, M71, M72, P25, dengan status dan solusi.
- `OUTSTANDING_ISSUES.md`.
- `AGENTS.md`: keputusan model K1.
- `RAILWAY_CHANGELOG.md`: setiap variabel, deploy, job; `config pull` / `plan`.
- `DATABASE_CHANGELOG.md` dan `DATABASE_SCHEMA.md`: tabel `web_fact` di Postgres-E8GM.
- Buku metode: versi baru lewat generator, helper `forward_return`, aturan nilai kosong, "Pilihan AI".
- `AI_TOOLS.md`: diregenerasi; `get_evidence` di set baca-saja, `find_web_fact`, perubahan `get_system_capabilities`.
- README orc, sandbox, Governor, web-governor.
- Laporan golden test.
