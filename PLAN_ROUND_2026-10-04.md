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

### S4: kelompok yang tidak ada datanya (M71, BBCA sebagai BUMN)

- **Masalah yang sebenarnya:** daftar anggota kelompok **tersembunyi**.
  - Rencana g5 yang disetujui user hanya menulis "bank BUMN = bank milik negara", tanpa daftar saham. User tidak bisa
    melihat BBCA ada di dalamnya.
  - Daftarnya baru muncul di kode, yang tidak dibaca user.
- **Prinsip:** AI **tidak perlu bertanya** untuk bisa bekerja. AI boleh memakai pengetahuannya sendiri, asalkan daftar itu
  **terlihat dan diberi label sumbernya** di tempat user memutuskan. Bertanya hanya salah satu pilihan, bukan kewajiban.
  Revisi ini menggantikan usulan sebelumnya ("wajib tanya user"), karena aturan itu akan menghambat uji hipotesis dan
  mengulang pola P05/P08 (gerbang terlalu ketat).
- **Solusi (orc + sandbox, permanen): kelompok wajib dideklarasikan, bukan wajib ditanyakan.**
  1. Setiap kelompok yang dipakai untuk menyaring atau mengelompokkan dideklarasikan sekali:
     `groups: [{name, members, source}]`. `source` salah satu dari:
     - `DATA` (kolom atau tabel referensi);
     - `USER` (disebut user, termasuk nama perusahaan yang dicocokkan ke ticker);
     - `AI_KNOWLEDGE` (pengetahuan AI, belum diverifikasi data).
     - `DATA_RULE` (dipilih dari data dengan aturan yang ditulis, misalnya "10 broker dengan net beli 20 hari terbesar"
       atau "broker berprofil Institutional-heavy"). Anggota yang terpilih dihitung kode dari data, dan aturannya ikut
       tampil.
  2. **Uji hipotesis dan riset:** daftar dan sumbernya tampil di rencana yang memang disetujui user. **Tidak ada langkah
     tambahan.** Contoh: "BUMN (pengetahuan AI, belum diverifikasi): BBCA, BBRI, BMRI, BBNI, BBTN, BRIS". User bisa
     mengoreksi saat menyetujui.
  3. **Analisis biasa (tanpa tahap persetujuan):** AI langsung jalan. Jawaban menampilkan daftar dan label sumber di
     bagian asumsi. AI boleh memilih bertanya (`CLARIFICATION`) bila kelompoknya penting dan ia tidak yakin, tetapi itu
     tidak diwajibkan.
  3b. **Pilih dari data dulu, baru tanya.** Bila kelompok bisa dipilih dari data dengan kriteria yang tersirat di
     pertanyaan ("broker yang akumulasi", "saham paling likuid"), AI memilihnya sendiri (`DATA_RULE`) dan menampilkan
     aturan beserta hasilnya, bukan bertanya "broker mana?". Istilah seperti "akumulasi" didefinisikan dan ditampilkan
     (M66/M13).
  3c. **User mendelegasikan** ("kamu yang tentukan berdasarkan X"):
     - X berupa ukuran dari data (net beli, frekuensi beli, nilai transaksi) menjadi `DATA_RULE` dengan aturan X;
     - X berupa atribut yang ada di katalog (asing/domestik, profil institusi/ritel di `IDX_Broker_Profile`) menjadi
       `DATA`;
     - X yang tidak ada di data (misalnya "broker milik grup konglomerat") menjadi `AI_KNOWLEDGE`, dengan label di
       jawaban.
     Pada semua kasus, jawaban menyebut "dipilih AI atas permintaan Anda: aturan …, hasil …", sehingga user bisa
     merevisi.
  3d. **Kelompok disimpan di percakapan** (nama, anggota, sumber, aturan), sehingga pertanyaan lanjutan ("bagaimana
     return-nya setelah broker itu beli?") memakai kelompok yang sama, tidak memilih ulang dengan definisi lain (M66).
  4. Penegakan oleh sistem: daftar nilai dari kolom dimensi atau identitas yang ditulis di kode, **tanpa deklarasi**,
     ditolak dengan pesan "deklarasikan kelompok ini beserta sumbernya". Kolom yang diperiksa diturunkan dari katalog.
     Ini berlaku untuk semua jenis daftar: ticker, broker, sektor, tipe investor, papan, dan nanti negara, indeks, seri
     makro. Nilai yang dihitung kode dari data, misalnya "hari crash", tidak terkena aturan.
  5. **Angka dan parameter desain** (ambang 3%, horizon 10 hari, persentil 95) **tidak terkena aturan ini.** Itu pilihan
     desain yang sudah dideklarasikan di rencana; satuannya dijaga P26 dan S3.
  6. Label `AI_KNOWLEDGE` ikut tercatat di definisi hasil, sehingga bisa ditelusuri lewat `get_lineage` dan ekspor.
- **Data (keputusan 6, user):** atribut kepemilikan negara bersumber resmi. Begitu ada, kelompok BUMN otomatis bersumber
  `DATA`. Fakta saat ini: BBRI, BMRI, BBNI dan BBTN adalah BUMN; BRIS anak usaha BUMN; BBCA swasta.
- **Uji ulang pada kasus g5:**
  - Dengan aturan ini, rencana g5.5 akan menampilkan keenam saham dengan label `AI_KNOWLEDGE` **sebelum** user menyetujui.
  - Kesalahan BBCA dan BRIS bisa terlihat di tahap persetujuan, dengan 0 langkah tambahan.
  - AbstentionBench: model reasoning jarang mau bilang "tidak tahu". Karena itu penegakannya **membuat tebakan terlihat**,
    bukan berharap AI menolak.
- **Risiko dan mitigasi:**

| Risiko | Mitigasi |
|---|---|
| User tidak membaca daftar di rencana, dan kesalahan tetap lolos | Label `AI_KNOWLEDGE` juga tampil di jawaban akhir dan di bukti; keputusan 6 menghapus tebakan untuk BUMN |
| Penolakan keliru, misalnya nama perusahaan dari user | Nama yang cocok di tabel referensi dihitung `USER`; setiap penolakan dicatat dan ditinjau di golden test |
| Rencana jadi lebih panjang | Daftar > 20 anggota diringkas ("48 saham Industry = Banks"); daftar lengkap ada di definisi hasil |

- **Tes:**
  - g5.5: rencana menampilkan daftar BUMN + label, dan uji tetap jalan tanpa bertanya;
  - daftar dari user dipakai dengan label `USER`;
  - kelompok berkolom (Industry = Banks) berlabel `DATA`;
  - daftar ticker di kode tanpa deklarasi ditolak;
  - ambang dan horizon angka tidak pernah ditolak oleh aturan ini;
  - kasus broker (daftar kode broker) diperlakukan sama.
  - dialog "cari broker yang akumulasi" → AI langsung memilih dengan aturan dari data (tanpa bertanya), menampilkan
    aturan dan daftar;
  - dialog "kamu yang tentukan berdasarkan profil institusi" → `DATA` dari `IDX_Broker_Profile`;
  - "berdasarkan net beli" → `DATA_RULE`;
  - "berdasarkan grup konglomerat" → `AI_KNOWLEDGE` dengan label;
  - pertanyaan lanjutan memakai kelompok yang tersimpan.

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
