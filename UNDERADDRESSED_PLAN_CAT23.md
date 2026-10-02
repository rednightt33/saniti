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
- **Akar (terbukti 2026-10-02, jejak audit `…-3-m4i` + log pikiran AI):**
  - Giliran 3 meminta ulang data yang persis sama dengan giliran 1, jadi datanya tidak berbeda.
  - AI tahu tabel hasil giliran 1 bisa dimuat (`load_output`), tetapi memilih menghitung ulang dari data mentah.
  - Filter papan Reguler adalah tebakan AI: "analisis sebelumnya mungkin dibatasi ke Regular". Padahal jawaban
    giliran 1 menyebut semua papan digabung.
  - Jawaban giliran 3 lalu menulis "agar konsisten dengan jawaban sebelumnya", klaim yang tidak dicek.
  - Mekanismenya: definisi hasil (filter yang dipasang di kode) tidak tersimpan bersama tabel hasil, sehingga
    tindak lanjut menebaknya.
- **Kelas:** setiap tindak lanjut yang menjelaskan hasil sebelumnya (INSIGHT, CLARIFY, "jelaskan angka ini").
- **Praktik umum:** drill-down di BI mewarisi filter angka yang diklik, jadi cakupannya otomatis sama.
- **Usulan:**
  - Setiap tabel hasil menyimpan definisinya: filter, ambang, dan cakupan yang dipakai kode, dinyatakan saat tabel
    dirilis dan ditampilkan bersama tabelnya.
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

**Status: disetujui user 2026-10-02, belum dikerjakan.**

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

## 5. Angka benar, kalimatnya salah (S27, M24, P08) — HIGH ALERT (H5)

**Bukti dari log pikiran AI (golden a, pertanyaan 3, deployment `ece48dd0`):**
- **S27:** AI memegang angka yang benar: event_count 2.258, overlapping_dropped 1.387, censored 13. Total yang
  memenuhi syarat (3.658) tidak pernah dihitung atau disediakan, lalu kalimatnya melabeli 2.258 sebagai
  "memenuhi syarat".
- **Kasus kedua di kelas yang sama (baru):**
  - Pikiran AI: "hari-hari lainnya = NON_EVENT (tanpa hari event)", lalu ia memilih ALL_ELIGIBLE (termasuk hari
    event) sebagai pembanding.
  - Kolom tabel jawaban tetap berlabel "Hari-hari lainnya (baseline)". Asumsinya menyebut ALL_ELIGIBLE, tetapi label
    yang dibaca user salah.
- **M24, P08:** terjadi 28 September, sebelum perekaman pikiran dinyalakan, jadi log pikirannya tidak ada. Di run g6
  (2026-10-02) kalimat INCONCLUSIVE sudah benar ("bukan berarti tidak ada efek"), tetapi belum dijaga sistem.

**Akar (terbukti):** label, jumlah turunan, dan kata vonis ditulis AI dengan bebas. Angka-angkanya nyata, jadi
pemeriksa angka meloloskannya. Tidak ada yang memeriksa apakah label cocok dengan definisi yang dipakai.

**Kelas:** setiap jumlah, label kelompok, dan kalimat vonis yang diturunkan dari parameter backend tetapi ditulis
ulang AI. Berlaku untuk event study, riset, `period_return` (pengecualian), dan data makro nanti.

**Pembanding:**
| Sumber | Praktiknya | Dibanding usulan awal |
|---|---|---|
| CONSORT (uji klinis) | Diagram alur wajib: setiap tahap (dinilai → dikeluarkan beserta alasannya → dianalisis) diberi jumlah, sehingga tidak ada angka yang "melompat". | Usulan awal hanya menambah `qualifying_count`. Ini diperluas: tabel alur lengkap yang dibuat sistem untuk setiap helper yang menyaring data. |
| GRADE / Cochrane | Kalimat hasil dibakukan per besar efek × tingkat kepastian ("mungkin menghasilkan sedikit atau tanpa perbedaan"). | Usulan awal berupa daftar frasa terlarang. Diganti: kalimat vonis baku dibuat sistem, dan daftar terlarang hanya jadi cadangan. |
| Data-to-text (semantic accuracy, NLI) | Teks dicek terhadap data dengan model NLI untuk menemukan penghilangan dan karangan. | Tidak dipakai sebagai jalur utama karena probabilistik dan menambah biaya; label dan jumlah dibuat sistem secara pasti. |

**Keputusan user 2026-10-02:** yang dipakai hanya butir 1 (tabel alur buatan sistem). Butir 2–4 tidak dipilih
dan disimpan sebagai catatan. Akibatnya masih terbuka:
- label pembanding yang bertentangan dengan pilihan sebenarnya (kasus "Hari-hari lainnya"), kecuali lewat definisi
  terstruktur H1;
- kalimat vonis INCONCLUSIVE yang terlalu keras (M24);
- jawaban benar yang ditolak karena kata "lebih rendah" (P08).

**Usulan yang disesuaikan:**
1. **[DIPILIH] Tabel alur buatan sistem** untuk setiap helper yang menyaring data:
   - kandidat → dibuang (per alasan: tumpang tindih, disensor, tanpa harga sebelumnya) → dipakai;
   - setiap baris membawa label tetap;
   - divalidasi ulang seperti tabel event study lainnya;
   - jawaban mengutip angka lewat rujukan dengan label sistem.
2. **[TIDAK DIPILIH] Label kelompok dari parameter.** Nama pembanding diambil dari parameter yang dipakai, misalnya ALL_ELIGIBLE →
   "semua hari yang memenuhi syarat (termasuk hari event)", NON_EVENT → "hari tanpa event". Label kolom yang
   bertentangan dengan parameter ditolak gerbang.
3. **[TIDAK DIPILIH] Kalimat vonis baku per status:**
   - sistem menyediakan kalimat per status, misalnya INCONCLUSIVE → "data belum cukup untuk menyimpulkan; ini bukan
     bukti tidak ada efek";
   - jawaban wajib memuatnya lewat rujukan;
   - penjelasan bebas tetap boleh;
   - daftar frasa terlarang tetap ada sebagai cadangan.
4. **[TIDAK DIPILIH] Arah dari tanda angka (P08).** Format rujukan baru menulis kata arah dari tanda angkanya ("lebih rendah 0,61
   poin" untuk −0,61), sehingga AI tidak perlu mengetik arah. Ini diturunkan, bukan daftar kata. Angka yang diketik
   AI tetap dicek seperti sekarang.

**Lapisan:** helper sandbox dan validator (tabel alur), rujukan nilai di orc (label, vonis, arah), gerbang jawaban
(cadangan).

**Tidak tercakup:** label yang dikarang AI untuk tabel buatan kodenya sendiri. Itu ditangani definisi terstruktur H1
dan bukti agregat (prioritas 2).

**Risiko dan mitigasi:**
- Jawaban terasa kaku → hanya kalimat vonis dan label kelompok yang baku.
- Rujukan bertambah → format pendek (`out.o1` / `finding.<id>`).

**Verifikasi:**
- g3 (tabel alur, label pembanding), g4/g6 (kalimat INCONCLUSIVE), tes r03 (arah);
- kasus lain: riset multi-sudut, `period_return` dengan pengecualian;
- kasus yang tidak berlaku: angka dari pertanyaan user.

**Permanen.**

Sumber:
- [CONSORT flow diagram](https://casrai.org/dictionary/term/consort-flow-diagram)
- [GRADE guidelines 26: informative statements](https://www.sciencedirect.com/science/article/pii/S0895435619304160)
- [Evaluating semantic accuracy of data-to-text with NLI](https://aclanthology.org/2020.inlg-1.19.pdf)

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

**Dicek ulang 2026-10-02 (log service dan log pikiran AI):**
- **C06, terbukti dan terulang hari ini:**
  - harga 2 Oktober dimuat pukul 10:06 UTC dan Feature 01 selesai 10:08 UTC;
  - ringkasan cakupan terakhir diperbarui 00:32 UTC, sehingga katalog masih menulis "sampai 2026-10-01";
  - g6 (16:39 UTC) menulis di pikirannya "coverage 2018-01-02 to 2026-10-01 … use … to 2026-10-01", sama seperti golden a
    (10:11–10:15 UTC);
  - akibatnya hari bursa terbaru hilang diam-diam dari setiap analisis antara muat sore dan pembaruan pagi berikutnya.
- **D06, masih:** cakupan broker berakhir 2026-08-31; jawaban menyebutkannya dengan jujur.
- **D02, masih:** daftar lengkap Sector yang dibaca golden a g1 memuat nilai `0`.

**Keputusan user 2026-10-02:** butir 1, 2 dan 3 disetujui (belum dikerjakan). D02: nilai `0` diganti teks
`Undefined`, bukan NULL. Ini bertentangan dengan Part A A1.4 ("Unknown = NULL plus reason, never a fake category");
perlu diputuskan apakah Part A diubah atau D02 dicatat sebagai pengecualian. Otomatisasi refresh broker (D06) masih
keputusan user.

**Usulan (diperbarui):**
1. **[DISETUJUI] C06, cakupan diperbarui saat data masuk:**
   - Pemuat harga dan Feature 01 memperbarui cakupan dataset-nya sendiri setelah berhasil.
   - Kegagalan pembaruan dicatat terpisah dan tidak menggagalkan muat data. Job pagi tetap jalan sebagai cadangan.
   - TEMPORARY sampai itu jadi: jadwal job cakupan ditambah satu kali setelah muat sore.
2. **[DISETUJUI] C06, rentang "sampai data terbaru":**
   - Permintaan data boleh berakhir di "terbaru"; Governor mengisinya dengan tanggal terakhir yang benar-benar ada saat
     penarikan, jadi tidak bergantung pada ringkasan.
   - Jawaban menyebut tanggal akhir dari data yang diterima, ditulis sistem.
3. **[DISETUJUI] D06, status kesegaran per sumber:**
   - SEGAR / TERLAMBAT / BASI dihitung dari jadwal muat yang diharapkan di katalog, ditampilkan di katalog dan
     jawaban.
   - Peringatan Telegram bila sebuah sumber BASI (`telegram-monitor` sudah ada).
   - Otomatisasi refresh broker = keputusan user (token Stockbit masih manual).
4. **[DISETUJUI, diubah user] D02, nilai pengganti:**
   - Migrasi `0` → `Undefined` (keputusan user); riwayat universe mencatat perubahannya.
   - Cek kualitas di pemuat: nilai yang bukan kategori (angka murni di kolom kategori) ditolak atau ditandai.
   - Tiga ticker-nya dicek lewat SQL sebelum migrasi.

**Risiko dan mitigasi:**
| Risiko | Mitigasi |
|---|---|
| Pemuat menjadi lebih rumit | Pembaruan cakupan dipisah dan gagalnya hanya dicatat; job pagi tetap jadi cadangan |
| "Terbaru" membuat hasil berubah antar-run di hari yang sama | Tanggal akhir aktual dicatat di definisi hasil (H1) dan disebut di jawaban |
| Peringatan BASI terlalu sering untuk sumber manual | Ambang sesuai jadwal sumber; satu peringatan per hari |
| Migrasi D02 mengubah data historis | Nilai asal tersimpan di riwayat universe; jumlah baris dicek dulu |

**Verifikasi (tanpa biaya model):**
- setelah muat sore, katalog menunjukkan tanggal hari itu dalam hitungan menit;
- analisis malam hari memakai tanggal terbaru;
- query D02 = 0 baris;
- kasus lain: tabel Feature 02/03 setelah broker diisi, data makro nanti;
- kasus yang tidak berlaku: sumber yang memang manual (statusnya tampil BASI, datanya tetap tidak segar).

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
