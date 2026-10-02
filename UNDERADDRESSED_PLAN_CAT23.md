# Usulan solusi: kategori 2 (jawaban salah) dan 3 (buntu) yang UNDERADDRESSED (2026-10-02)

Status: usulan, belum dikerjakan. Kode masalah merujuk ke `ERRORS_AND_SOLUTIONS.md`. Masalah dikelompokkan per kelas
(satu mekanisme yang sama), supaya satu perbaikan menutup semua kasus di kelas itu.

Pembanding (praktik umum) dicari 2026-10-02; sumbernya di bagian akhir.

## 1. Istilah yang tidak didefinisikan user (M66, M13)

- **Masalah:** "hari crash", "bank BUMN" dan "saham paling likuid" ditentukan AI sendiri setiap kali.
  - Run a: crash = median return harian ≤ −1% (2022–2026, 57 hari). Run b: rata-rata ≤ −1% (2018–2026, 132 hari).
  - Akibatnya broker teratas berbeda (TF vs RB), dan "bank BUMN" 5 di satu run, 4 di run lain.
  - Angka setiap run benar menurut definisinya sendiri.
- **Akar (terbukti):** tidak ada definisi baku di katalog; `VALUE_DICTIONARY_PLAN.md` belum dibuat.
- **Kelas:** semua istilah pasar tanpa definisi tunggal (crash, BUMN, likuid, big caps; nanti makro: "rupiah melemah tajam").
- **Praktik umum:** semantic layer (dbt, Cube, LookML). Definisi ditulis sekali dan dipakai semua query. Benchmark 2026:
  akurasi naik 17–23 poin persen. Konsistensi didapat karena definisinya tetap.
- **Usulan:**
  - Kamus istilah di katalog: istilah, sinonim, aturan yang bisa dijalankan backend, versi, dan status disetujui user.
  - Backend mencocokkan istilah di pertanyaan dan memasang definisinya ke permintaan data.
  - Jawaban menyebut "definisi baku: …". User boleh menimpanya.
  - Istilah yang belum ada di kamus: AI menyebut definisinya (seperti sekarang) dan backend mencatatnya sebagai kandidat.
  - Dibanding praktik umum: prinsipnya sama, cakupannya lebih kecil (istilah saja, bukan semua metrik).
- **Lapisan:** katalog → validasi backend → prompt terakhir.
- **Tidak tercakup:** istilah yang muncul pertama kali.
- **Risiko dan mitigasi:**
  - Definisi baku tidak sesuai maksud user → disetujui user, selalu ditampilkan, bisa ditimpa.
  - Salah cocok istilah → hanya istilah dan sinonim terdaftar, dan pencocokannya ditampilkan.
  - Biaya sedang: tabel, migrasi, pencocokan, tes, dan daftar awal ±10 istilah dari user.
- **Verifikasi:**
  - g5.1 dijalankan dua kali → definisi sama;
  - kasus lain: g1 "paling likuid", "saham BUMN non-bank";
  - kasus yang tidak berlaku: user memberi definisi sendiri.
- **Permanen.** Perlu keputusan user.

## 2. Penjelasan menghitung ulang dengan cakupan lain (M63)

- **Masalah:** "kenapa broker teratas paling tinggi?" dijelaskan dengan data papan Reguler saja, padahal ranking di
  giliran 1 menjumlah semua papan.
- **Akar:**
  - Terbukti: cakupannya berbeda (baris cakupan kedua jawaban).
  - Dugaan: tahap INSIGHT membuat permintaan data baru, tidak memuat tabel hasil giliran 1.
  - Cek yang memastikan: jejak audit giliran 3.
- **Kelas:** setiap tindak lanjut yang menjelaskan hasil sebelumnya (INSIGHT, CLARIFY, "jelaskan angka ini").
- **Praktik umum:** drill-down di BI mewarisi filter angka yang diklik, jadi cakupannya otomatis sama.
- **Usulan:**
  - INSIGHT mulai dari tabel hasil yang dijelaskan (`load_output` sudah ada).
  - Backend membandingkan cakupan data penjelasan (tabel, filter, rentang) dengan cakupan tabel yang dijelaskan.
  - Kalau berbeda, jawaban wajib menyebut "definisi berbeda: …" dan labelnya diturunkan.
- **Lapisan:** catatan data dan cek backend, lalu prompt.
- **Tidak tercakup:** hasil yang tidak dirilis.
- **Risiko dan mitigasi:** penjelasan yang sah kadang butuh data lain → tidak dilarang, hanya wajib disebut.
- **Verifikasi:**
  - g5.3;
  - kasus lain: g5.9, lanjutan setelah g1;
  - kasus yang tidak berlaku: pertanyaan baru yang bukan penjelasan.
- **Permanen.**

## 3. Aturan yang disetujui user tidak mengikat backend (M28, M26, M29)

- **Masalah dan akar (terbukti):**
  - **M28:**
    - User menyetujui "berhasil = return ≥ 10%". Backend memakai aturan bawaan (> 0) dan melaporkan 44% sebagai
      "≥ 10%". Yang benar 172 dari 1.499 (11%).
    - Definisi sukses hanya teks; mesin statistik memakai ambangnya sendiri (default 0).
  - **M26:**
    - User menyebut efek minimal 1 poin persen. Hasil +0,52 (CI 0,20–0,84) tetap diberi SUPPORTED.
    - Ini sesuai desain: vonis hanya menguji arah.
  - **M29:**
    - Rencana menyebut ±6 bank, eksekusi memakai 48.
    - Angka rencana diketik AI sebelum data dibaca dan tidak dicek.
- **Kelas:** aturan dan angka yang ditetapkan sebelum analisis (ambang sukses, efek minimal, jumlah saham, periode)
  harus menjadi isian terstruktur yang dibaca mesin, bukan teks.
- **Praktik umum:**
  - Pre-registration A/B test: aturan keputusan ditulis sebelum analisis sebagai angka ("p < 0,05 DAN lift ≥ 3%"),
    dengan tiga hasil: ya / tidak / belum jelas.
  - Statistik (Lakens): bila ada efek minimal yang penting (SESOI), hasil disebut bermakna hanya bila CI seluruhnya
    melewati ambang itu (minimum-effect test).
- **Usulan:**
  - **M28:**
    - Rencana riset memuat `success_threshold` berupa angka dan arah, lalu diteruskan ke mesin statistik.
    - Temuan menampilkan "aturan yang dipakai".
    - Gerbang menolak kalimat yang menyebut ambang berbeda dari aturan yang dipakai.
  - **M26 (keputusan user):** bila user menyebut efek minimal, ada tambahan label:
    - BERMAKNA (CI seluruhnya ≥ ambang);
    - DI BAWAH AMBANG (arah jelas, ambang belum tercapai);
    - BELUM JELAS.

    Tanpa ambang dari user, label tetap seperti sekarang.
  - **M29:** angka cakupan di rencana (jumlah saham, rentang, baris) diisi backend dari hasil cek kelayakan. Gerbang
    rencana menolak angka cakupan yang tidak cocok.
- **Lapisan:** kontrak rencana riset, mesin statistik, gerbang.
- **Tidak tercakup:** analisis bebas tanpa rencana (G1); itu ditangani kelompok 1 dan 8.
- **Risiko dan mitigasi:**
  - Ambang yang diucapkan samar ("naik signifikan") → hanya angka eksplisit yang jadi isian; selain itu AI minta
    klarifikasi.
  - Label baru → hanya berlaku bila user menyebut ambang.
- **Verifikasi:**
  - g6 (≥ 3%);
  - kasus lain: b04 (≥ 10%), g4 dengan ambang;
  - kasus yang tidak berlaku: pertanyaan tanpa ambang.
- **Permanen.**

## 4. Hasil hilang atau dianggap tercatat ganda (M25, S13)

- **Masalah dan akar:**
  - **M25 (terbukti):** dua eksperimen, tetapi metadata hanya menampilkan yang terakhir. Status akhir hanya menyimpan
    completion terakhir.
  - **S13:** sudut riset ditandai INVALID "rekaman ganda". Di golden a keempat sudutnya INVALID.
    - Terbukti: penjaga anti-ganda disimpan di memori proses kode AI.
    - Dugaan: kode AI sendiri yang menghapus penanda itu.
    - Cek: kode run di jejak audit (terhambat R26).
- **Kelas:** status yang harus tahan lama disimpan di tempat sementara.
- **Praktik umum:** idempotensi lewat kunci unik di database. Penanda "sudah dikerjakan" di memori tidak berguna setelah
  proses diulang.
- **Usulan:**
  - Rekaman sudut ditentukan host (di luar kode AI) dari output yang tersimpan, dengan kunci unik (run, sudut).
  - Rekaman kedua ditolak saat itu juga dengan pesan jelas, bukan INVALID di akhir.
  - Penggantian rekaman yang disengaja harus eksplisit, dan versi lamanya dicatat.
  - Metadata mendaftar temuan dari semua completion.
- **Lapisan:** sandbox host dan metadata eksekusi.
- **Risiko dan mitigasi:** AI ingin memperbaiki rekamannya → jalur "ganti rekaman" yang eksplisit. Biaya kecil–sedang.
- **Verifikasi:**
  - tes: worker diulang → tidak ada INVALID palsu;
  - g5.1, g5.8; g4 dengan dua eksperimen → keduanya tampil.
- **Permanen.**

## 5. Angka benar, kalimatnya salah (S27, M24, P08)

- **Masalah dan akar (terbukti):**
  - **S27:**
    - Kalimat: "dari 2.258 event yang memenuhi syarat … sisanya 2.258 dipakai". Seharusnya 3.658 memenuhi syarat.
    - Total itu tidak disediakan backend, jadi AI menjumlah sendiri dan salah memberi label.
  - **M24:**
    - INCONCLUSIVE ditulis "tidak didukung data", dan MDE disebut "efek terbesar".
    - Cek kata hanya mencakup sebagian frasa.
  - **P08:**
    - "Lebih rendah sekitar 0,6 poin" ditolak karena sumbernya −0,6086.
    - Kata arah yang dikenali hanya "turun, melemah, minus, …"; kata pembanding tidak dikenali.
- **Kelas:** backend menyerahkan ke AI tugas menyusun angka turunan (total, arah) atau memilih kata vonis.
- **Praktik umum:**
  - Laporan otomatis menghitung semua angka turunan di sistem.
  - Hasil tidak signifikan disebut "belum cukup bukti" atau "tidak jelas secara statistik", bukan "tidak ada efek"
    ("absence of evidence is not evidence of absence").
- **Usulan:**
  - **S27:**
    - Ringkasan event study menambah `qualifying_count`, dan validator menghitungnya ulang.
    - Aturannya untuk semua helper: setiap jumlah yang biasa disebut di jawaban disediakan jadi.
  - **M24:**
    - Backend menyediakan kalimat vonis baku per status, misalnya INCONCLUSIVE → "data belum cukup untuk menyimpulkan".
    - Gerbang menolak "tidak didukung / ditolak / tidak ada efek" untuk INCONCLUSIVE.
    - Istilah MDE diberi nama tetap.
    - Angka sebuah hipotesis hanya boleh dari hipotesis itu sendiri.
  - **P08:**
    - Rujukan nilai `abs(...)` sudah ada, jadi itu jalur utamanya.
    - Gerbang juga mengenali kata pembanding (lebih rendah/tinggi, di bawah/atas, lebih kecil/besar, lower/higher,
      below/above), dengan syarat arahnya cocok dengan tanda angka sumber.
- **Lapisan:** helper sandbox, gerbang jawaban.
- **Risiko dan mitigasi:**
  - Kata pembanding salah pasang → hanya dalam 40 karakter sebelum angka, dan tanda yang bertentangan tetap ditolak.
  - Kalimat baku terasa kaku → hanya kalimat vonis yang baku.
- **Verifikasi:**
  - g3 (jumlah event); g4/g6 bila ada hasil INCONCLUSIVE;
  - tes kalimat r03 dan r02;
  - kasus lain: g5.4;
  - kasus yang tidak berlaku: angka dari pertanyaan user.
- **Permanen.**

## 6. Data sebelum periode dan pemanasan indikator (G11/D12/G08, D14, P05)

- **Masalah dan akar (terbukti):**
  - **G11/D12/G08:**
    - Saham jarang transaksi (BSWD) dikeluarkan dengan alasan "tidak ada harga sebelumnya", padahal harga 15 dan 27
      hari sebelumnya ada. Return sebenarnya +34,42% / +37,41%, di atas ambang anomali, jadi saham itu hilang dari
      jawaban.
    - Data "sebelum periode" dihitung dalam hari bursa pasar, bukan per saham.
  - **D14:**
    - RSI/EMA berbeda dari nilai sejarah penuh (EMA50 +3,3%, RSI hingga 3,2 poin).
    - AI memilih panjang pemanasan sendiri (20–255 baris).
  - **P05:**
    - Jawaban RSI yang benar dipaksa LIMITATION karena menyebut angka uji konvergensinya sendiri.
    - Kelasnya sama dengan P25 (pesan tolak sudah diperbaiki, menunggu golden test). Bila D14 dikerjakan backend, AI
      tidak perlu menguji konvergensi sendiri.
- **Kelas:** "nilai terakhir sebelum tanggal X" dan "riwayat cukup untuk indikator", per entitas. Berlaku juga untuk data
  makro (rilis terakhir sebelum tanggal).
- **Praktik umum:**
  - As-of join (DuckDB, kdb+, QuestDB) mengambil nilai terakhir ≤ tanggal per entitas.
  - TA-Lib "unstable period": jumlah bar pemanasan diturunkan dari periode indikator. Untuk EMA ≈ K·(n+1)/2. RSI(14)
    butuh ±196 bar untuk presisi 1e-6.
- **Dibanding usulan lama saya (pemanasan tetap 250 bar):** untuk toleransi 0,1%, rumusnya memberi RSI14 ≈ 97,
  EMA50 ≈ 177, EMA200 ≈ 695 bar. Jadi 250 kebanyakan untuk RSI dan kurang untuk EMA200. Usulan diganti: diturunkan dari
  definisi indikator.
- **Usulan:**
  - **Nilai dasar per entitas:** Governor menyediakan nilai terakhir sebelum awal periode per entitas (as-of), lengkap
    dengan tanggal dan umurnya.
    - Ada batas umur (misalnya 365 hari); di atas batas tetap tampil sebagai pengecualian.
    - Jawaban menyebut umur harga dasarnya.
  - **Pemanasan indikator:**
    - Katalog Feature mencatat jenis dan periode indikator.
    - Backend menghitung minimal bar dari toleransi yang disepakati dan menaikkan buffer otomatis; AI tidak memilih
      sendiri.
- **Lapisan:** Governor, katalog, planner.
- **Risiko dan mitigasi:**
  - Query per saham lebih berat → EXPLAIN dulu (index Ticker+Date), hanya untuk saham dalam cakupan.
  - Pemanasan menambah baris → kecil dibanding batas bundle; diukur.
  - Harga dasar terlalu lama → umurnya ditampilkan, dan ditolak di atas batas.
- **Verifikasi:**
  - BSWD d01: harus +34,42% / +37,41%;
  - RSI14/EMA50 dibandingkan sejarah penuh: selisih di bawah toleransi;
  - kasus lain: saham suspensi, data makro bulanan;
  - kasus yang tidak berlaku: SMA (tidak rekursif, cukup n bar).
- **Permanen.** Toleransi perlu keputusan user (usul 0,1%).

## 7. Kesegaran dan isi data (C06, D06, D02)

- **Masalah dan akar (terbukti):**
  - **C06:**
    - Jawaban menyebut data harga berakhir 25 September, padahal 28 September sudah ada.
    - Harga dimuat 17:00 WIB, sedangkan ringkasan cakupan diperbarui job terpisah pukul 07:30 WIB. Akibatnya ringkasan
      tertinggal ±14,5 jam setiap hari (lebih lama di akhir pekan), dan AI lebih percaya ringkasan daripada data yang
      diterimanya.
  - **D06:**
    - Data broker berhenti 31 Agustus karena refresh manual.
    - Jawabannya jujur (LIMITATION), tetapi pertanyaan September tidak terjawab.
  - **D02:**
    - Tiga saham punya sektor bernilai teks "0", yang muncul sebagai sektor sendiri.
    - Nilai pengganti itu dari sumber.
- **Kelas:** kesegaran per sumber dan nilai "tidak diketahui". Berlaku untuk semua sumber baru (FX, makro dengan jadwal
  rilis berbeda).
- **Praktik umum:**
  - dbt source freshness: tanggal terakhir diambil dari waktu muat.
  - Status lulus / peringatan / gagal per sumber, dengan ambang sesuai jadwal sumber, dicek otomatis.
  - "Tidak diketahui" = NULL + alasan (sudah aturan A1.4 kita).
- **Usulan:**
  - **C06:**
    - Cakupan diperbarui oleh pemuat itu sendiri setelah berhasil memuat; job harian tetap ada sebagai cadangan.
    - Jawaban menyebut tanggal akhir dari data yang benar-benar diterima, ditulis backend.
  - **D06:**
    - Status kesegaran per sumber (SEGAR / TERLAMBAT / BASI), dihitung dari jadwal muat yang tercatat di katalog.
    - Otomatisasi refresh broker = keputusan user.
  - **D02:**
    - Migrasi "0" → NULL + alasan; nilai asal disimpan di log.
    - Tes kualitas yang menolak nilai pengganti di kolom kategori.
- **Lapisan:** pemuat data, katalog cakupan, backend.
- **Risiko dan mitigasi:**
  - Gagal memperbarui cakupan tidak boleh menggagalkan muat data → dicatat terpisah.
  - Migrasi D02 → cek jumlah baris dulu.
- **Verifikasi (tanpa biaya model):**
  - setelah muat 17:00, cakupan = MAX(Date) dalam hitungan menit;
  - g1/g2 menyebut tanggal akhir yang benar;
  - D02: 0 baris;
  - kasus lain: tabel Feature, makro;
  - kasus yang tidak berlaku: sumber manual (statusnya tampil BASI, datanya tidak jadi segar).
- **Permanen.**

## 8. Angka hasil kode AI tidak diperiksa (S23)

- **Masalah dan akar (terbukti di kode):** angka dari kode AI sendiri tidak dihitung ulang backend, kecuali event study
  dan statistik riset.
- **Kelas:** setiap analisis bebas (G1).
- **Praktik umum:**
  - Semantic layer: hitungan umum lewat definisi tetap; akurasi naik 17–23 poin.
  - Benchmark agen analisis data: kesalahan terbanyak ada di hitungan multi-langkah.
  - Rekonsiliasi (jumlah bagian = total) seperti di audit.
- **Usulan (bertahap):**
  1. Hitungan umum dipindah ke helper teruji. Yang sudah: ringkasan gudang, event study, `period_return`. Berikutnya:
     fase 2, rata-rata lintas saham (S20), ranking.
  2. Cek rekonsiliasi murah pada setiap tabel hasil: baris vs cakupan, bagian = total, persen 0–100, satuan sesuai
     katalog. Dimulai sebagai label peringatan, bukan penolakan.
  3. Hitung ulang independen untuk hitungan yang dideklarasikan, mulai dari ringkasan gudang: angka AI dibandingkan
     query gudang.
  4. Golden test mengukur akurasi (kunci independen g1–g4 sudah ada).
- **Lapisan:** helper sandbox, validator, Governor.
- **Risiko dan mitigasi:**
  - Tambahan waktu → hanya untuk hitungan yang dideklarasikan.
  - Alarm salah → mulai sebagai peringatan.
- **Verifikasi:**
  - g1–g4 dengan kunci independen;
  - tes dengan kesalahan yang disuntik sengaja.
- **Permanen, bertahap.** Paling mahal.

## 9. M42: usul ditutup

Golden a dan b giliran 1 menjawab nama broker (TF, RB) lebih dulu, sebelum riset dijalankan (mode 4). Tetap dicek di
g5.1.

## Urutan yang disarankan

1. Kelompok 7: murah, tanpa biaya model.
2. Kelompok 5: kecil.
3. Kelompok 4: S13 merusak riset di setiap golden test.
4. Kelompok 3: M28 dan M29; M26 menunggu keputusan.
5. Kelompok 6: perlu EXPLAIN dan keputusan toleransi.
6. Kelompok 1: perlu daftar istilah.
7. Kelompok 2.
8. Kelompok 8: bertahap.

## Sumber pembanding

- [Semantic Layer vs. Text-to-SQL: 2026 Benchmark Update (dbt)](https://docs.getdbt.com/blog/semantic-layer-vs-text-to-sql-2026)
- [Semantic Layers for Reliable LLM-Powered Data Analytics (arXiv 2604.25149)](https://arxiv.org/pdf/2604.25149)
- [Lakens, Equivalence Testing and Interval Hypotheses](https://lakens.github.io/statistical_inferences/09-equivalencetest.html)
- [Pre-Registration (Experiment Protocol)](https://atticusli.com/behavioral-science-glossary/pre-registration/)
- [Rewriting results sections in the language of evidence](https://www.sciencedirect.com/science/article/pii/S0169534721002846)
- [Not enough evidence — Informed Health Choices](https://www.informedhealthchoices.org/key-concepts/concepts-about-evidence/not-enough-evidence/)
- [TA-Lib Unstable Period](https://ta-lib.org/api/unstable-period/), [TA-Lib issue #492 (auto warm-up)](https://github.com/TA-Lib/ta-lib/issues/492)
- [DuckDB ASOF JOIN (MotherDuck)](https://motherduck.com/glossary/asof-join/)
- [dbt source freshness](https://docs.getdbt.com/docs/build/sources)
- [Idempotency Is a Contract: Making Retries Safe from the Database Side](https://www.sqlserverscience.com/data-architecture/idempotency-keys-database/)
- [IDA-Bench: Evaluating LLMs on Interactive Guided Data Analysis](https://arxiv.org/pdf/2505.18223)
