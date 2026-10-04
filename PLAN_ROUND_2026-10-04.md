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

- **Masalah:** AI menebak anggota kelompok dari ingatannya.
- **Solusi (orc + katalog, permanen):**
  - Kelompok yang disebut user (BUMN, grup usaha, indeks, nanti region makro) harus berasal dari kolom atau tabel
    referensi yang ada.
  - Bila tidak ada, AI wajib bilang "data kelompok ini tidak ada" dan meminta daftar dari user.
  - Daftar dari user dicatat di definisi hasil sebagai "dari user".
  - Penegakan: kode yang menulis daftar ticker sebagai teks (`['BBCA', …]`) untuk membentuk kelompok, tanpa sumber, ditolak
    sebelum dijalankan. Polanya sama dengan penolakan angka tertulis di kode (P25).
- **Data (keputusan 6, user):** tambah atribut kepemilikan negara, bersumber resmi (BP BUMN / laporan emiten), dengan
  tanggal berlaku. Fakta saat ini: BBRI, BMRI, BBNI, BBTN adalah BUMN; BRIS anak usaha BUMN; BBCA swasta.
- **Hasil benchmark:**
  - Daftar AI salah 2 dari 6.
  - AbstentionBench: model reasoning 24% lebih jarang mau bilang "tidak tahu". Karena itu penegakannya harus di sistem,
    bukan di instruksi.
- **Tes:**
  - BUMN tanpa kolom: AI bertanya, tidak menebak;
  - daftar dari user dipakai dan dicatat;
  - kelompok yang ada kolomnya (Industry = Banks) tetap jalan;
  - daftar ticker yang memang disebut user di pertanyaan tidak ditolak.

## 4. G22: database kewalahan

**Apakah benar?**
- **Putaran 2 (5 worker):** ya. 45 perintah database dibatalkan dalam 7 menit. Penyimpanan percakapan gagal: rencana g4
  hilang dan riwayat g5 tidak terbaca. Ini terverifikasi.
- **Putaran 3 (3 worker):** 29 pembatalan, semuanya hitungan baris Governor yang memang dibatasi 7 detik. 0 kegagalan
  simpan percakapan, dan sync checkpoint kembali normal (< 0,4 detik setelah menit-menit awal).

Kesimpulan: kewalahan nyata pada 5 worker, tidak merusak pada 3 worker. Hitungan baris yang selalu habis waktu tetap kerja
sia-sia (21 kali untuk satu pesanan data di putaran 2). Dugaan "disk penuh sesak" belum diverifikasi dengan metrik disk.

**Usulan (perlu keputusan user):**
1. Governor membatasi jumlah query berat yang jalan bersamaan; sisanya mengantre.
2. Governor tidak menghitung baris bila rencana query sudah jelas akan melewati batas waktu, dan tidak menghitung ulang
   per bagian dari pesanan yang sudah dipecah.
3. Simpan percakapan mencoba sekali lagi sebelum menyerah.
4. Opsional: database terpisah untuk percakapan/audit.

Sebelum G22 diperbaiki, golden test memakai paling banyak 3 worker.

## 5. Verifikasi bersama (setelah fase 2–3)

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

## Catatan yang diperbarui saat eksekusi

`ERRORS_AND_SOLUTIONS.md` (G22, G23, P27, M71, M72), `OUTSTANDING_ISSUES.md`, `AGENTS.md` (keputusan model),
`RAILWAY_CHANGELOG.md`, `AI_TOOLS.md` (bila alat atau helper berubah), buku metode (generator, versi baru),
README sandbox/orc.
