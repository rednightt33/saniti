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

## Pembanding (benchmark) untuk H1 dan H2: masalah percakapan multi-giliran (2026-10-02)

| Sumber | Temuannya | Dibanding usulan kita |
|---|---|---|
| Laban dkk., "LLMs Get Lost in Multi-Turn Conversation" (ICLR 2026) | Semua model teratas rata-rata 39% lebih buruk di percakapan multi-giliran. Penyebab utamanya ketidakandalan (+112%), bukan kemampuan. Model membuat asumsi di awal dan tidak pulih. | Sama dengan M63: AI menebak "papan Reguler" lalu yakin. Usulan 1 (jawaban lengkap di riwayat) membantu, tetapi menurut temuan ini memberi lebih banyak teks saja tidak cukup andal. |
| Dialogue state tracking / structured state | Keadaan percakapan disimpan sebagai isian terstruktur. Kalau keadaan disimpulkan ulang dari transkrip setiap giliran, hasilnya bergeser saat riwayat dipotong atau dikoreksi. | Usulan 2 dan 4 memakai prinsip ini. Kekurangan usulan awal: definisi tabel berupa teks bebas tulisan AI. Diperbaiki menjadi isian terstruktur (filter, periode, cakupan, ambang). |
| Anthropic, "Effective context engineering" | Catatan terstruktur di luar konteks, dipanggil lagi saat perlu. Saat meringkas, utamakan tidak ada yang hilang, baru dirampingkan. | Catatan data kita sudah ada, tetapi tidak menyimpan definisi hasil dan dipotong 8.000 karakter. Definisi harus termasuk bagian yang tidak pernah dipotong. |
| Agen dengan state bertipe dan persetujuan manusia (LangGraph) | Nilai yang disetujui disimpan sebagai field bertipe. Eksekusi membaca field itu, bukan teks rencana. | Sama dengan usulan H2. Dipertegas: backend sendiri yang memasang ambang ke mesin hitung, sehingga AI tidak bisa lupa atau mengubahnya. |

### Usulan yang disesuaikan setelah pembanding

- **H1-a. Riwayat lengkap:** riwayat menyimpan isi, asumsi, batasan dan metodologi. Tetap dikerjakan karena murah,
  tetapi bukan perlindungan utama.
- **H1-b. Definisi terstruktur, diturunkan bila bisa:**
  - Filter yang dipasang di permintaan data (cakupan) sudah tercatat otomatis oleh backend. AI diarahkan dan didorong
    memasang filter di permintaan data, bukan di kode.
  - Filter yang tetap dipasang di kode wajib dinyatakan sebagai isian terstruktur saat tabel dirilis:
    - filter: kolom, operator, nilai;
    - periode;
    - cakupan entitas;
    - ambang.
- **H1-c.** Pertanyaan lanjutan mulai dari tabel yang dijelaskan (tidak berubah).
- **H1-d. Cek konsistensi mekanis:** definisi terstruktur tabel asal dan tabel penjelasan dibandingkan oleh backend.
  Kalimat "konsisten dengan sebelumnya" hanya boleh bila hasilnya sama.
- **H1-e. Bila definisi lama tidak diketahui:** AI wajib membuka tabel asal atau bertanya, tidak boleh menebak
  (menjawab temuan Laban soal asumsi dini).
- **H2. Rencana yang disetujui = kontrak bertipe:**
  - ambang sukses dan efek minimal dibaca mesin hitung langsung dari rencana yang disetujui;
  - argumen berbeda yang dikirim AI ditolak;
  - laporan menampilkan aturan yang dipakai mesin.

Yang tidak dicakup pembanding dan tetap kita tambahkan: bukti agregat per klaim (prioritas 2). Pembanding hanya
membahas menjaga informasi, bukan memeriksa angka.

Sumber:
- [Laban dkk., LLMs Get Lost In Multi-Turn Conversation](https://www.alphaxiv.org/abs/2505.06120)
- [A State-Update Prompting Strategy for Multi-turn Dialogue](https://arxiv.org/pdf/2509.17766)
- [Dialogue state tracking](https://www.usefini.com/glossary/what-is-dialogue-state-tracking-dst)
- [Anthropic: Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [LangGraph Graph API (state and reducers)](https://docs.langchain.com/oss/python/langgraph/graph-api)
