# Rencana putaran 2026-10-04: ganti model, perbaiki 3 jawaban salah, G22, dan G23

Status: **RENCANA, belum dieksekusi.** Perbaikan G23 (gerbang bukti dan jalan keluar saat buntu) ada di
`PLAN_EVIDENCE_GATE_2026-10-04.md`. Dasar analisis: `GT_ANALYSIS_2026-10-04.md`.

## Urutan

| Fase | Isi | Kenapa urutan ini |
|---|---|---|
| 1 | Ganti model ke `xiaomi/mimo-v2.6-flash` reasoning high (keputusan user) + uji coba kecil | Diminta lebih dulu ("dulu"). Dampak model diukur sendiri, sebelum kode lain berubah |
| 2 | G23 (`PLAN_EVIDENCE_GATE_2026-10-04.md`) | Penyebab terbesar waktu dan biaya terbuang |
| 3 | S3, S5, S4: tiga jawaban salah | Melindungi kebenaran angka |
| 4 | G22: database kewalahan | Perlu keputusan user (lihat §4) |
| 5 | Golden test kecil + hitung ulang independen | Membuktikan semuanya |

## 1. Ganti model (keputusan user 2026-10-04)

**Keputusan:** model aktif `xiaomi/mimo-v2.6-flash`, reasoning **high**. AGENTS.md mencatat model 1 = DeepSeek,
model 2 = `xiaomi/mimo-v2.6-pro`; perubahan ini disetujui user dan AGENTS.md diperbarui.

**Fakta yang sudah dicek (OpenRouter, 2026-10-04):**

| Model | Input / 1 juta token | Output / 1 juta | Cache / 1 juta | Alat (tools) |
|---|---|---|---|---|
| `xiaomi/mimo-v2.6-flash` | USD 0,14 | USD 0,28 | USD 0,003 | ya, 8 provider |
| `deepseek/deepseek-v4.1-flash` (sekarang) | USD 0,003 | USD 2,40 | USD 0,003 | ya |

Dua catatan:
- **Reasoning "high" belum tentu diterima.** Kode kita untuk model 2 hanya mengirim "reasoning nyala"
  (`Settings.reasoning`), karena per 2026-09-30 MiMo tidak punya tingkat reasoning di OpenRouter. Metadata OpenRouter hari
  ini juga tidak menyebut tingkatnya.
- **Biaya sangat tergantung cache.** Dengan token test kemarin (37,3 juta input dari cache, 3,3 juta input baru, 1,3 juta
  output), MiMo flash akan memakan USD 0,94 bila cache tetap ±90%, USD 3,50 bila cache 50%, dan USD 6,05 bila tanpa
  cache. DeepSeek kemarin USD 2,18.

**Langkah:**
1. **Uji coba reasoning (tanpa golden test, ± USD 0,05).** Prompt yang sama dikirim tiga kali ke MiMo flash:
   `effort: high`, `effort: low`, `enabled: true`. Jumlah token reasoning dibandingkan.
   - Bila high dan low berbeda nyata: tingkat diterima. `Settings.reasoning` mengirim `effort` untuk model ini. Bentuknya
     dicatat sebagai setelan per model (`AI_MODEL_2_REASONING_FORM = effort | enabled`), tidak ditebak dari nama model.
   - Bila tidak berbeda: lapor ke user bahwa "high" tidak tersedia, hanya nyala/mati. Tetap pakai `enabled`.
2. **Setelan Railway (dev):**
   - `AI_MODEL_2=xiaomi/mimo-v2.6-flash` dan `AI_MODEL_SWITCH=2`, dengan `--skip-deploys`.
   - Lalu redeploy orc dari cabang (CLI upload, pelajaran R31), dan cek bahwa deployment tidak berasal dari `main`.
   - `AI_MODEL` (DeepSeek) tidak diubah, sehingga bisa kembali dengan `AI_MODEL_SWITCH=1`.
   - Setelah itu `config pull` / `plan`.
3. **Golden test kecil di kode sekarang:** g1, g4, g8, g9 (3 pesan), g5 pesan 1–4. Dibandingkan dengan
   `ma-golden-20261004a`:
   - angka jawaban dicek ulang lewat job baca-saja (pola `verify-job`);
   - detik, biaya, rasio cache, jumlah panggilan;
   - penolakan argumen alat;
   - kepatuhan format jawaban (Indonesia, referensi nilai).

**Risiko dan mitigasi:**

| Risiko | Mitigasi |
|---|---|
| Kualitas pemakaian alat dan format JSON berbeda | Golden test kecil sebelum dipakai luas; kembali dengan `AI_MODEL_SWITCH=1` |
| Cache rendah, sehingga biaya naik sampai ±3× | Rasio cache diukur di golden test kecil; berhenti bila biaya per pesan > USD 0,15 |
| Reasoning "high" tidak tersedia | Langkah 1 memastikan sebelum golden test |
| Uptime provider bervariasi (82–99,9% per 30 menit) | Error provider dicatat; routing provider tidak diubah tanpa izin |

## 2. G23

Lihat `PLAN_EVIDENCE_GATE_2026-10-04.md`:
- A: satu sumber kebenaran untuk alat di meja AI;
- B: cek bukti hanya di tempat yang perlu;
- C: AI diberi tahu aturannya;
- D: tidak ada gagal total.

## 3. Tiga jawaban salah

### S3: satuan hasil uji (P27, BUMN "0,00%")

- **Masalah:** angka yang dibuat kode AI diterima dengan label satuan apa pun.
- **Solusi (sandbox, permanen):**
  1. Untuk hasil yang berasal dari harga (return ke depan), backend mengambil contoh ≤ 500 baris, menghitung ulang
     return-nya dari harga yang ia pegang, lalu membandingkan. Bila angka AI 100× lebih kecil atau lebih besar, uji
     ditolak dengan pesan jelas ("hasilmu pecahan, rencana minta persen").
  2. Helper `forward_return(prices, horizon)` dibuat di sandbox. Ia menghitung return dalam satuan rencana, sehingga AI
     tidak perlu mengalikan sendiri. Buku metode menyarankan helper ini.
  3. Hasil yang bukan dari harga (nanti data makro) diberi status "satuan dideklarasikan, tidak dicek".
- **Hasil benchmark:**
  - Aturan sederhana "angka persen yang terlalu kecil pasti pecahan" **ditolak**. Pada 6.150 saham-tahun, tidak ada
    ambang aman: 1,3% data persen akan salah tangkap, dan return 20 hari bisa > 1.
  - Hitung ulang dari harga tidak punya masalah itu, karena yang dibandingkan adalah rasio, tepat 100.
- **Tes:**
  - kasus g5.6 (pecahan di bawah PERSEN) ditolak;
  - persen yang benar tetap lolos;
  - saham tidur (return 0) tidak salah tangkap;
  - horizon 1, 5 dan 20 hari.

### S5: hari tanpa nilai indikator (M72, RSI)

- **Masalah:** kode AI bebas memasukkan hari tanpa nilai ke kelompok mana saja.
- **Solusi (sandbox, permanen):** `event_summary` dan helper riset membuang baris yang kondisi atau hasilnya kosong dari
  **kedua** kelompok, lalu melaporkan jumlahnya (`rows_condition_undefined`). Aturan ini ditulis di buku metode.
- **Hasil benchmark:**
  - Hitung ulang independen memberi 84.166 baris pembanding (sama dengan run g6_rsi).
  - Run g6_revise memakai 84.819; dengan S5 jumlahnya menjadi 84.166, sehingga dua run memberi angka yang sama.
  - Sesuai TA-Lib: 14 hari pertama RSI memang kosong.
- **Tes:**
  - kondisi kosong di awal (pemanasan indikator);
  - kondisi kosong di tengah (celah data);
  - hasil kosong di akhir periode.

### S4: semua pilihan AI terlihat (M71 BBCA sebagai BUMN; juga M13, P25, P05/P08)

**Kelas masalah:** hasil analisis bergantung pada masukan yang **tidak berasal dari data atau dari user**, yaitu pilihan
AI (daftar anggota kelompok, definisi istilah, ambang, persentil), dan pilihan itu **tidak terlihat** oleh user.

- Kasus BBCA: daftar tampil di Asumsi rencana, tetapi di antara banyak asumsi lain, tanpa label sumber ("pengetahuan AI"), dan disetujui tanpa dibaca.

**Koreksi 2026-10-04 (log reasoning g5.5–g5.6):** daftar BUMN *tampil* di bagian Asumsi rencana g5.5 ("Bank BUMN = …: BBCA, BBRI, BMRI, BBNI, BBTN, dan BSI/BRIS"), bukan tersembunyi; persetujuan diberikan runner otomatis. Jejak reasoning: it1–it2 benar ("BBCA is private (Djarum); BUMN banks: BMRI, BBRI, BBNI, BBTN"), katalog dicek dan tidak ada kolom BUMN; it3 memakai aturan dari data (nama perusahaan mengandung "(Persero)", yang menambah BRIS); it5 daftar akhir menambah BBCA, bertentangan dengan reasoning-nya sendiri (kemungkinan terbawa "empat bank besar BBCA, BBRI, BMRI, BBNI" dari jawaban g5.4). g5.6 memakai asumsi rencana yang sudah disetujui. **Tidak ada pencarian web:** tidak ada alat web yang ditawarkan maupun dipanggil di seluruh run.
- Kasus sebaliknya, P25/P05/P08: pilihan AI (persentil ke-90) terlihat, tetapi justru *ditolak*, sehingga jawaban benar
  dipaksa LIMITATION.

**Satu prinsip, tanpa daftar skenario:**
- Sistem, bukan AI, menentukan asal setiap masukan yang ditulis di kode.
- Masukan yang bukan dari data dan bukan dari user **ditampilkan otomatis** sebagai "Pilihan AI".
- Tidak ada penolakan dan tidak ada kewajiban bertanya.

**Mekanisme (sandbox + orc, permanen):**
1. Saat kode berhasil jalan, sandbox membaca nilai tertulis (teks dan angka) yang dipakai untuk menyaring, mengelompokkan
   atau sebagai ambang. Ini perluasan dari pembacaan angka tertulis yang sudah ada untuk P25.
2. Asal setiap nilai **diturunkan**, tidak didaftar:
   - teks yang ada sebagai nilai di dataset yang dimuat kode (ticker, broker, sektor, negara, apa pun kolomnya) adalah
     nilai data;
   - nilai yang muncul di pesan user, atau di hasil alat sebelumnya di percakapan ini, berasal dari user/data;
   - sisanya adalah **pilihan AI**.
3. Orc menambahkan bagian **"Pilihan AI"** ke jawaban (dan ke rencana bila pilihan itu sudah ada saat rencana dibuat),
   ditulis oleh backend, bukan oleh model. Contoh: "Kelompok dipilih AI: BBCA, BBNI, BBRI, BBTN, BMRI, BRIS; persentil
   95." Bagian ini ikut tercatat di definisi hasil, lineage dan ekspor.
4. Gerbang angka tidak lagi menolak angka yang berasal dari kode AI sendiri. Angka itu dipindah ke "Pilihan AI". Ini
   menutup P25/P05/P08 dengan mekanisme yang sama.

**Kenapa ini fleksibel:**
- Tidak ada aturan per jenis daftar, per jenis dialog, atau per tabel.
- "Cari broker yang akumulasi", "kamu yang tentukan berdasarkan X", BUMN, data makro nanti: semuanya masuk ke jalur yang
  sama.
  - Bila AI memilih dari data lewat kode, tidak ada nilai tertulis, sehingga hasilnya data.
  - Bila AI menulis daftar dari ingatannya, daftar itu tampil sebagai pilihan AI.
- AI tetap bebas bertanya bila ia mau, tetapi tidak diwajibkan.

**Bila ambigu, nyatakan (keputusan user 2026-10-04):**
- Tidak perlu jalur baru. Kelompok atau filter yang dipakai tampil di "Pilihan AI" (di atas), sehingga user sadar.
- AI tetap boleh memakai jawaban `CLARIFICATION` yang sudah ada bila ia mau bertanya, tetapi tidak diwajibkan.

**S4b — membumikan fakta lewat web (opsional, keputusan user):** dengan cara yang sama seperti analisis ini mengetahui
bahwa BBCA bukan BUMN (pencarian web, beberapa sumber dicocokkan).
- **Sudah ada:**
  - `market-web-governor` dengan kutipan sumber, syarat 2 sumber independen (`NEED_2_INDEPENDENT_SOURCES`) dan toko
    hasil terpisah (`Postgres-E8GM`).
  - Tetapi AI analis belum memegang alat web: `get_system_capabilities` melaporkan `web_search` false.
- **Usulan:**
  - Sambungkan Web Governor sebagai alat AI untuk fakta yang **tidak ada di data**, misalnya keanggotaan kelompok
    (BUMN, grup usaha, indeks).
  - Hasilnya masuk ke "Pilihan AI" dengan sumber `WEB`: kutipan, tanggal terbit, dan ≥ 2 sumber yang setuju.
  - Satu pencarian per istilah dipakai ulang di percakapan.
  - Daftar yang terverifikasi bisa diusulkan menjadi data referensi resmi (keputusan 6), dengan sumber dan tanggal.
- **Risiko:**
  - Sumber web bisa usang atau bertentangan. Contoh: ringkasan pencarian untuk analisis ini sempat menyebut BRIS dalam
    daftar "bank BUMN", padahal sumber yang sama menjelaskan BRIS anak usaha BUMN.
  - Biaya web pernah naik 5× (W22).
  - Pencarian bisa lama (W13/W14, ± 3 menit).
  - Tanggal terbit sering kosong (W07).
- **Mitigasi:**
  - Wajib ≥ 2 sumber yang setuju dan sumber resmi diutamakan (BP BUMN, laporan emiten).
  - Ketidaksepakatan ditampilkan, bukan dipilih diam-diam.
  - Hanya dipakai untuk fakta yang tidak ada di data.
  - Hasil disimpan ulang dan batas biaya per percakapan diterapkan.
- **Bergantung pada:** penyelesaian W06–W11 dan W22 yang masih terbuka.

**Uji pada data nyata** (prototipe pada 59 eksekusi kode putaran `ma-golden-20261004a`):

| Eksekusi | Ditandai sebagai pilihan AI | Benar? |
|---|---|---|
| g5.6 (2 eksekusi) | BBCA, BBNI, BBRI, BBTN, BMRI, BRIS; persentil 95 | Ya, tepat kesalahan M71 dan ambang pilihan AI |
| g6 (2 eksekusi) | 2,5 dan 97,5 (batas interval 95%) | Ya, pilihan metode AI |
| g6 ambang 30, 3%, 10 hari | **Tidak** ditandai | Benar, berasal dari kata-kata user |
| 55 eksekusi lain | Tidak ada | Tidak ada tanda yang salah |

Prototipe memakai 48 ticker bank sebagai "nilai data". Versi sebenarnya memakai nilai dari dataset yang benar-benar dimuat
kode.

**Yang tidak dicakup (jujur):**
- Mekanisme ini membuat tebakan **terlihat**, tidak membuatnya benar. Kesalahan BBCA tampil di jawaban, dan user bisa
  meminta ulang.
- Bila daftar baru dibuat di kode setelah rencana disetujui, ia tampil di jawaban, bukan di rencana.
- Data resmi BUMN tetap keputusan 6. Fakta saat ini: BBRI, BMRI, BBNI dan BBTN adalah BUMN; BRIS anak usaha BUMN; BBCA
  swasta.

**Risiko dan mitigasi:**

| Risiko | Mitigasi |
|---|---|
| Daftar "Pilihan AI" penuh hal remeh | Hanya nilai yang dipakai untuk menyaring, mengelompokkan atau sebagai ambang; angka 0 dan 1 diabaikan; uji di atas: 4 dari 59 eksekusi |
| Nilai dari user tidak dikenali (nama perusahaan vs ticker, "3%" vs 0,03) | Pencocokan memakai tabel referensi (nama ↔ ticker) dan bentuk angka setara (persen ↔ pecahan); salah kenal hanya menambah satu baris di "Pilihan AI", tidak menolak apa pun |
| User tidak membaca bagian itu | Bagian "Pilihan AI" selalu di bagian atas asumsi, dan ikut di bukti dan ekspor |

**Tes:**
- g5.6 menampilkan daftar dan persentil;
- g6 tidak menampilkan ambang dari user;
- angka pilihan AI (P25 "persentil ke-90") tidak lagi menyebabkan LIMITATION;
- kasus lain selain yang diamati: daftar kode broker tertulis di kode, dan pilihan dari data lewat kode (tidak
  ditandai).

## 4. G22: database kewalahan

**Apakah benar?**
- **Putaran 2 (5 worker):** ya. 45 perintah database dibatalkan dalam 7 menit. Penyimpanan percakapan gagal: rencana g4
  hilang dan riwayat g5 tidak terbaca. Ini terverifikasi.
- **Putaran 3 (3 worker):** 29 pembatalan, semuanya hitungan baris Governor yang memang dibatasi 7 detik. 0 kegagalan
  simpan percakapan, dan sync checkpoint kembali normal (< 0,4 detik setelah menit-menit awal).

Kesimpulan: kewalahan nyata pada 5 worker, tidak merusak pada 3 worker. Hitungan baris yang selalu habis waktu tetap kerja
sia-sia (21 kali untuk satu pesanan data di putaran 2). Dugaan "disk penuh sesak" belum diverifikasi dengan metrik disk.

**Ukuran dari log Governor putaran 3 (612 hitungan baris):**
- 588 berhasil, median 26 ms. Hitungan ini berguna: perkiraan bawaan database meleset median 2×, p90 3×, dibanding
  hasil hitungan.
- 24 habis waktu (7 detik). Ini 4% dari hitungan, tetapi **57% waktu database untuk hitungan** (175 dari 305 detik),
  tanpa hasil.
- Di putaran 2, 30 hitungan habis waktu (230 detik), 21 di antaranya untuk bagian-bagian dari **satu pesanan data** g1.

**Pilihan solusi, diuji terhadap data di atas:**

| # | Solusi (lapisan) | Uji ulang | Putusan |
|---|---|---|---|
| G22-1 | Lewati hitungan bila perkiraan database besar | Perkiraan **tidak meramalkan** timeout: ada hitungan diperkirakan 48 baris yang habis waktu (hasil kecil, scan besar). Ambang 1 juta hanya menangkap 4/24 dan ikut melewatkan 5 hitungan yang sukses | **Ditolak** |
| G22-2 | Simpan "hitungan ini pernah habis waktu" per query yang sama | Putaran 3: 6 dari 24 berulang (44 detik). Putaran 2: 0 dari 30 | Kecil, opsional |
| G22-3 | **Satu timeout per pesanan data cukup** (Governor): setelah satu bagian dari pesanan yang dipecah habis waktu, bagian lain memakai perkiraan, karena pemecahan sudah membatasi ukuran tiap bagian | Putaran 2: memotong 20 dari 21 timeout g1 (±140 detik) | **Diusulkan** (permanen) |
| G22-4 | **Batasi query berat yang jalan bersamaan** (Governor; antrean, misalnya maks. 2 query berat bersamaan, sisanya menunggu) | Pembanding alami: 5 worker menghasilkan 45 pembatalan dan 2 kegagalan simpan; 3 worker menghasilkan 29 pembatalan dan 0 kegagalan. Mengurangi beban bersamaan menghilangkan kegagalan yang terlihat user | **Diusulkan** (permanen) |
| G22-5 | Simpan percakapan **mencoba sekali lagi** setelah jeda singkat (orc) | Tidak menghilangkan beban, tetapi menutup satu momen lambat; g4 dan g5 putaran 2 gagal pada satu percobaan | **Diusulkan** (permanen, mitigasi) |
| G22-6 | Database terpisah (replika baca) untuk gudang data, terpisah dari percakapan/audit | Praktik standar (OLTP vs analitik); menghilangkan kelas masalahnya | Keputusan user (biaya infrastruktur) |

**Pembanding luar:**
- PostgreSQL wiki "Count estimate": `count(*)` harus memindai semua baris (MVCC), sedangkan perkiraan dari statistik
  ribuan kali lebih cepat tetapi tidak tepat.
- Praktik umum memisahkan beban transaksi kecil dari query analitik (replika baca), karena keduanya berebut I/O, cache
  dan autovacuum.
- Hitungan kita tetap berguna untuk 96% kasus, jadi yang dibuang hanya hitungan yang terbukti sia-sia (G22-3), bukan
  semua hitungan.

**Risiko dan mitigasi:**

| Risiko | Mitigasi |
|---|---|
| G22-3: bagian pesanan memakai perkiraan yang meleset 2–3× | Pemecahan pesanan sudah membatasi tiap bagian; batas baris saat penarikan (FETCH) tetap berlaku |
| G22-4: antrean membuat jawaban lebih lambat saat ramai | Batas tunggu antrean dan pesan "sedang antre"; angka maks. bersamaan bisa diatur lewat setelan |
| G22-5: percobaan ulang menulis dua kali | Penyimpanan sudah dijaga nomor lease; percobaan ulang hanya bila percobaan pertama tidak tersimpan |
| G22-6: biaya dan kerumitan infrastruktur | Hanya bila G22-3/4/5 tidak cukup pada golden test 5 worker |

**Verifikasi:** golden test dengan 5 worker (sama dengan putaran 2). Target: 0 kegagalan simpan percakapan, timeout
hitungan per pesanan ≤ 1, pembatalan database turun dibanding 45.

Sebelum G22 diperbaiki, golden test memakai paling banyak 3 worker.

## 5. Golden test akhir (keputusan user: setelah plan selesai)

Satu putaran (2 bagian, 3 worker untuk bagian A, 5 worker untuk bagian B), dijalankan setelah fase 1–4 selesai dan
terdeploy di dev. Mencakup perbaikan putaran ini **dan** daftar "menunggu golden test" di `OUTSTANDING_ISSUES.md`.

| Pertanyaan | Membuktikan |
|---|---|
| g1 dan g1_repeat | P22/P23 (satuan ganda), G16 ("regular"), M66/M13 (definisi sama dua kali), M46/M48 |
| g3 event study | P24/M65 (format p dan CI), S19, S22, S24 |
| g4 hipotesis BBCA | P25/P20/P21 (pesan penolakan), M62 |
| g5 pesan 1–9 | M64 (merujuk hasil terbaru), G13 (rencana tidak gagal karena ukuran data), M47–M55, **S4 (BUMN: AI bertanya, tidak menebak)**, **S3 (satuan uji)** |
| g6_revise | **S5 (pembanding 84.166 baris)**, P26 |
| g8, g9 (3 pesan) | **G23 (0 loop; g9.2 menjawab)**, D (tidak ada gagal total), model baru |
| g11 | Riset tanpa gerbang bukti |
| Bagian B: g1, g3, g5.1, g11 dengan 5 worker | **G22** |

Setiap putaran: angka dicek ulang lewat job baca-saja, dan biaya per pesan dilaporkan.

## 5b. Verifikasi bersama (setelah fase 2–3)

Golden test kecil, 3 worker:
- g1, g4, g5 (1–6), g6_revise (1), g8, g9 (3 pesan), g11;
- angka dicek ulang lewat job baca-saja.

| Ukuran | Target |
|---|---|
| Panggilan terbuang setelah gerbang | 0 |
| Gagal total | 0 |
| g5.6 | Menolak satuan salah, atau angka benar −0,41% vs −0,32% |
| BUMN | Tidak ditebak |
| g6 | Pembanding 84.166 baris |
| Angka lain | Tetap sama dengan hitung ulang independen |

Biaya dan detik dibandingkan dengan `ma-golden-20261004a`.

## 6. Kategori "buntu": apa yang selesai oleh jalan keluar (G23-D dan S4)

Jalan keluar ("tidak ada gagal total" dan "boleh bilang tidak tahu / bertanya") mengubah **gejala**: user selalu
menerima jawaban, catatan, atau pertanyaan, bukan kosong. **Akar** tiap masalah tetap perlu perbaikannya sendiri.

| Masalah | Selesai oleh jalan keluar? | Yang tetap perlu |
|---|---|---|
| G23 loop gerbang bukti | **Ya** (A–D di `PLAN_EVIDENCE_GATE_2026-10-04.md`) | — |
| G22 database kewalahan | Tidak: rencana/riwayat yang gagal disimpan tetap hilang | G22-3/4/5 |
| M73 riset otomatis mode 4 | Tidak; ini masalah lama, bukan buntu | Keputusan user (S6) |
| R30 kredit habis | Tidak relevan | Selesai (kredit sudah ditambah) |
| R31 deploy dari `main` | Tidak relevan | Proses (`--skip-deploys` + CLI); tuntas saat cabang masuk `main` |
| P05/P08 jawaban benar dipaksa LIMITATION | Tidak: masalahnya kebalikan (gerbang terlalu ketat) | Perbaikan gerbang angka parameter (terpisah) |
| G10 penarikan data ditolak | Sebagian: user mendapat penjelasan, tetapi data tetap tidak ditarik | Pemecahan pesanan / G13 (menunggu golden test) |
| D06 data broker berhenti 31 Agustus | Tidak: data memang belum dimuat | Muat ulang data broker (di luar AI) |
| M42 "siapa broker" dijawab rencana riset | Tidak: salah jenis jawaban, bukan buntu | Router / S6 |

## Catatan yang diperbarui saat eksekusi

`ERRORS_AND_SOLUTIONS.md` (G22, G23, P27, M71, M72), `OUTSTANDING_ISSUES.md`, `AGENTS.md` (keputusan model),
`RAILWAY_CHANGELOG.md`, `AI_TOOLS.md` (bila alat atau helper berubah), buku metode (generator, versi baru),
README sandbox/orc.
