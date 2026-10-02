# HIGH ALERT: kesalahan diam-diam (keputusan user 2026-10-02)

Status: rencana. Prioritas 1 = membereskan masalah di bawah. Prioritas 2 = bukti agregat (WAJIB), dikerjakan sesudah
prioritas 1. Golden test tidak dijalankan sampai user menyuruh.

## Kenapa HIGH ALERT

Masalah ini berbahaya karena tidak terlihat oleh pengguna:
- jawabannya terdengar yakin dan konsisten;
- angkanya sendiri lolos semua pemeriksaan;
- tetapi isinya berbeda dari yang ditanyakan atau disetujui user.

Pengguna awam tidak punya cara untuk menyadarinya. Setiap kasus baru dari kelas ini dicatat di `ERRORS_AND_SOLUTIONS.md`
dengan tanda **HIGH ALERT** di kolom status, dan masuk golden test berikutnya.

## Kelas yang termasuk

| Kelas | Kasus | Mekanisme (terbukti) |
|---|---|---|
| H1. Informasi hilang antar giliran | M63 | Giliran berikutnya hanya menerima isi jawaban; asumsi, batasan dan metodologi dibuang. Tabel hasil tidak membawa definisinya. AI menebak definisi lama dan menulis "konsisten dengan jawaban sebelumnya". |
| H2. Aturan user tidak mengikat backend | M28, M26, M29 | Ambang sukses, efek minimal dan jumlah cakupan disimpan sebagai kalimat; mesin hitung memakai angkanya sendiri (ambang bawaan 0), dan teks rencana tidak dicek terhadap hasil cek kelayakan. |
| H3. Definisi istilah berubah antar-run | M66, M13 | Istilah tanpa definisi baku ("hari crash", "bank BUMN", "paling likuid") ditentukan AI setiap kali. |
| H4. Angka hasil kode AI tidak diperiksa | S23 | Hanya event study dan statistik riset yang dihitung ulang backend. Lihat prioritas 2. |

## Prioritas 1: membereskan masalahnya

| Kelas | Perbaikan | Status |
|---|---|---|
| H1 | (1) Riwayat menyimpan jawaban lengkap (isi, asumsi, batasan, metodologi). (2) Setiap tabel hasil membawa definisinya (filter, ambang, periode, cakupan). (3) Pertanyaan lanjutan "kenapa/jelaskan" mulai dari tabel yang dijelaskan. (4) Klaim "konsisten dengan sebelumnya" hanya boleh bila definisinya sama; bila beda, jawaban wajib menyebut perbedaannya. | Disetujui user, belum dikerjakan |
| H2 | Ambang sukses berupa angka dan dipakai mesin hitung; laporan menyebut aturan yang dipakai. Angka cakupan di rencana diisi backend dari hasil cek kelayakan. M26 (vonis memperhitungkan efek minimal): keputusan user. | Usulan; M26 menunggu keputusan |
| H3 | Kamus istilah yang disetujui user (`UNDERADDRESSED_PLAN_CAT23.md` kelompok 1). | Usulan; perlu daftar istilah dari user |

Rincian masing-masing ada di `UNDERADDRESSED_PLAN_CAT23.md`.

## Prioritas 2 (WAJIB): bukti agregat untuk setiap jawaban

**Keputusan user (2026-10-02):** setiap data mentah harus bisa dicek silang, dalam bentuk agregat. Keluaran setiap
jawaban yang berisi klaim data ada dua:
1. jawaban AI;
2. agregasi data yang mendukung klaim-klaim di jawaban itu.

### Proses

1. **AI menyatakan klaimnya.** Setiap klaim angka di jawaban ditandai dengan resep agregatnya: tabel, filter, kelompok,
   ukuran, dan periode. Resep ini memakai bentuk ringkasan gudang yang sudah ada (G18: kelompok + SUM/MIN/MAX/COUNT),
   bukan kode bebas.
2. **Backend menghitung sendiri dari data mentah.**
   - Hitungan dilakukan di gudang (SQL Governor) dengan aturan ringkasan yang sama.
   - Ini jalur yang terpisah dari kode AI, jadi berfungsi sebagai pemeriksa independen.
3. **Backend membandingkan.** Angka AI dibandingkan dengan hasil hitungan backend, dengan toleransi pembulatan dari
   tampilan angka (aturan yang sama dengan pemeriksaan provenance).
   - Cocok → klaim diberi label TERCEK.
   - Tidak cocok → jawaban dikembalikan ke AI dengan selisihnya (satu kali perbaikan). Kalau masih tidak cocok, klaim
     ditandai TIDAK COCOK di jawaban, tidak disembunyikan.
4. **Bukti ikut dikirim.** Respons API berisi `evidence`: tabel agregat per klaim beserta resepnya, sehingga user bisa
   melihat dan mengecek sendiri.
5. **Klaim yang tidak bisa diagregasi langsung** (p-value, model statistik, peringkat hasil rumus):
   - buktinya adalah agregat masukannya (jumlah kejadian, rata-rata per kelompok, rentang tanggal);
   - labelnya "tidak dicek langsung".

### Batas (diatur, bisa diubah lewat variabel)

| Batas | Nilai awal | Alasan |
|---|---|---|
| Jumlah resep bukti per jawaban | 10 | Cukup untuk klaim utama; mencegah biaya membengkak |
| Baris per tabel bukti | 200 | Bukti harus bisa dibaca manusia; ringkasan, bukan data mentah |
| Biaya query | Sama dengan batas EXPLAIN Governor | Tidak membuka jalan query mahal baru |
| Waktu per query bukti | 30 detik; total 120 detik per jawaban | Jawaban tidak tertahan lama |
| Bila batas terlewati | Klaim sisanya diberi label "bukti tidak dihitung (batas)" | Tidak pernah diam-diam |

### Lapisan

- Kontrak jawaban akhir di orc (resep per klaim).
- Governor (agregat, sudah ada sejak G18 fase 1).
- Gerbang perbandingan di orc.
- Respons API dan audit.
- Prompt hanya sebagai panduan; perlindungannya di backend.

### Tercakup dan tidak

- **Tercakup:** semua klaim berupa jumlah, total, minimum/maksimum, hitungan dan rasio dari dua agregat, di semua
  tabel, termasuk data makro dan lintas aset nanti, asal aturan agregasinya terisi di katalog (Part A).
- **Belum tercakup:**
  - total per bulan/periode menunggu G18 fase 2;
  - rata-rata lintas saham menunggu S20;
  - klaim statistik hanya mendapat bukti masukan.

### Risiko dan mitigasi

| Risiko | Mitigasi |
|---|---|
| Waktu jawaban bertambah | Query agregat terukur 3 detik untuk bentuk besar (DATABASE_CHANGELOG, G18); batas 120 detik |
| AI salah menulis resep sehingga bukti tidak cocok padahal jawabannya benar | Perbaikan satu kali dengan selisihnya; label TIDAK COCOK tetap terlihat, jadi tidak ada yang tersembunyi |
| Klaim yang tidak ditandai lolos tanpa bukti | Gerbang provenance yang ada menolak angka tanpa sumber; angka dari tabel hasil tanpa resep diberi label "tanpa bukti agregat" |
| Kolom tanpa aturan agregasi di katalog | Klaim di kolom itu mendapat label "tidak bisa dicek"; jadi dorongan untuk melengkapi katalog |

### Verifikasi

- Tes: klaim yang benar → TERCEK; angka yang sengaja diubah → TIDAK COCOK; batas 10 resep → label batas.
- Golden test: g1 (total net beli asing), g2 (min/maks harga), g5 giliran 1 (ranking broker).
- Kasus yang tidak cocok: jawaban tanpa angka (penjelasan konsep), karena bukti tidak diperlukan.

**Permanen.**

## Golden test untuk kelas ini (belum dijalankan)

`g7_followup_definitions` di `apps/orc-test-runner/suite.json`: satu percakapan yang sengaja memakai definisi bukan
bawaan (papan Nego, bukan Reguler), lalu pertanyaan lanjutan.
- Kalau AI menebak, kesalahannya langsung terlihat.
- Diperiksa:
  - giliran 2 dan 3 tetap memakai papan Nego;
  - jawaban menyebut definisinya;
  - tidak ada klaim "konsisten" yang keliru.

Ditambah g6 (ambang sukses ≥ 3%, H2) dan pengulangan g1 (H3).
