# Rencana ke depan: usulan dan keputusan yang masih terbuka

Sejak 2026-10-06 (keputusan user), pekerjaan yang **sudah disetujui** tetapi belum dieksekusi ada di `PLAN.md`, dan
eksekusi yang sudah disetujui ada di `EXEC.md`.
Dokumen ini berisi sisanya:
- usulan yang belum disetujui;
- rencana masa depan;
- keputusan user yang masih terbuka.

Butir yang disetujui user dipindah ke `PLAN.md` atau `EXEC.md` pada tugas yang sama. Kode masalah merujuk ke
`ERRORS_AND_SOLUTIONS.md`.

## 0. PRIORITAS TINGGI

### M157 — total beli ≠ total jual di Broker Summary 2016–2020 (HIGH PRIORITY, user 2026-10-15: "describe di future plan dan remark as high priority ... agar agent lain bisa bantu investigate")

**Ringkasan untuk agen yang menyelidiki.** Di `Feature_03_Stock_Broker_Daily`, `total_buy_value` (jumlah `buy_value_1d`
semua broker per saham, tanggal, papan) seharusnya sama dengan `total_sell_value`: setiap transaksi punya broker pembeli
dan broker penjual dengan nilai yang sama. Ternyata tidak sama di 47.768 dari 2.268.015 baris. Hampir semuanya di
2016–2020. Feature_03 sudah direkonsiliasi persis ke sumber mentah, jadi celahnya ada di data sumber
`IDX_Broker_Summary` (Stockbit, lewat `apps/stockbit-broker-backfill`), bukan di rumus Feature.

**Fakta yang sudah terverifikasi** (pgweb read-only 2026-10-15, `lucid-patience/dev`; bukti
`verification/feature03/BUY_SELL_IDENTITY.md`):

| Papan | 2016 | 2017 | 2018 | 2019 | 2020 | 2021–2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|
| Regular, baris tidak sama | 14.270 / 97.000 | 7.849 / 118.461 | 9.084 / 136.753 | 10.647 / 145.085 | 5.446 / 154.717 | 0 | 2 / 261.053 | 2 / 203.536 |
| Regular, rata-rata selisih relatif | 3,8% | 5,1% | 4,0% | 3,4% | 5,4% | – | 2,5% | 80% |
| Nego, baris tidak sama | 76 | 53 | 9 | 139 | 116 | 0 | 0 | 0 |
| Tunai, baris tidak sama | 41 | 10 | 15 | 7 | 2 | 0 | 0 | 0 |

- Selisih terbesar Rp 291.005.760.675 dalam satu baris.
- `foreign_net_value + domestic_net_value = total_buy_value − total_sell_value` berlaku di setiap baris (DATABASE_CHANGELOG,
  rebuild Feature 03 v2), jadi selisih itu juga muncul sebagai net asing + domestik yang tidak nol di level saham.
- Rekonsiliasi Feature_02/03 ke `IDX_Broker_Summary`: nol baris hilang, nol baris lebih, nol selisih nilai
  (DATABASE_CHANGELOG, backfill Feature 02 dan rebuild Feature 03). Artinya angka sumber diteruskan apa adanya.
- Sampel lama "1 dari 89.933 baris" hanya mencakup data sejak 2026-06-01. Sampel itu tidak boleh dipakai sebagai bukti
  untuk seluruh riwayat.

**Belum terverifikasi: dugaan penyebab dan cara mengeceknya.** Semua cek bersifat read-only.
1. **Broker hilang di halaman sumber lama.** Mungkin Stockbit mengembalikan daftar broker terbatas, atau broker yang
   sudah tutup tidak tercatat. Cek: per (Symbol, Date, Market Board) yang tidak sama, bandingkan jumlah broker baris
   tersebut dengan baris yang sama di hari sekitarnya, lalu lihat apakah selisihnya cocok dengan satu broker yang hilang.
   Cek juga apakah broker di `IDX_Broker_Profile_History` yang aktif saat itu tidak muncul.
2. **Batas jumlah baris per halaman atau paginasi di backfill.** Cek kode `apps/stockbit-broker-backfill`: apakah
   respons dibatasi top-N atau diputus per halaman. Hitung juga apakah baris yang tidak sama cenderung yang jumlah
   brokernya mendekati angka bulat (misalnya 50 atau 100).
3. **Pembagian Investor Type.** Apakah Domestic/Foreign untuk satu broker kadang hanya satu sisi. Cek: di baris yang
   tidak sama, jumlahkan `Buy Value` dan `Sell Value` per `Investor Type`.
4. **Pembanding luar.** Bandingkan nilai transaksi saham itu di hari itu (`Price_Stock_Indonesia_IDX` volume × harga,
   atau nilai IDX bila ada) dengan `total_buy_value` dan `total_sell_value`. Sisi yang lebih dekat ke nilai bursa
   menunjukkan sisi mana yang kurang.
5. **Muatan ulang parsial.** Cek `ingestion_time` dan log muatan untuk tanggal yang tidak sama: apakah dimuat dalam batch
   yang sama, terputus, atau diulang.
6. **Empat baris 2025–2026.** Pemeriksaan per baris (Symbol, Date, Board), karena pola ini berbeda dari 2016–2020.

Kueri awal per tahun dan papan ada di bukti `verification/feature03/BUY_SELL_IDENTITY.md`. Jalankan per partisi
(tahun atau rentang ticker) sesuai Part A A3.23, jangan sebagai satu kueri besar.

**Dampak.**
- Jawaban yang menjumlah net broker atau net asing/domestik di level saham, sektor atau pasar untuk 2016–2020 bisa
  membaca celah sumber sebagai akumulasi. Contohnya pertanyaan "akumulasi broker", "net asing tahunan" atau backtest
  aliran dana.
- Fitur turunan yang memakai jumlah net (Feature_02 rolling di level saham, Feature_03 net totals) membawa celah yang
  sama.

**Yang sudah dilakukan.** Katalog sudah menyatakannya (migrasi `20261015_011`, ERRORS M154 a dan M157): selisihnya nol
atau celah sumber, bukan permintaan; akumulasi dibaca dari net per broker atau per tipe investor.

**Yang belum.**
- Akar penyebab di sumber (cek 1–6).
- Catatan cakupan per tahun di `AI_data_coverage` atau penanda per baris (misalnya `source_balance_gap`) supaya AI dan
  ekspor bisa memilah baris yang tidak seimbang.
- Keputusan user: muat ulang 2016–2020 dari sumber (bila sumber sekarang lengkap), tandai saja, atau keluarkan dari
  analisis aliran.

Setiap perubahan data atau skema mengikuti AGENTS.md (migrasi baru, baca balik, changelog) dan butuh persetujuan user.

### EDGE-CTX — dipindah ke EXEC.md (EXEC-EDGE-CTX), 2026-10-15

## 1. Antrean perbaikan dekat

**Riwayat, sudah dieksekusi.** M68, S28 dan R-STORE dikerjakan di round 2026-10-03 (`ROUND_PLAN_2026-10-03.md` Fase A dan C, live di dev). Teks di bawah disimpan sebagai riwayat desain.

### M68 — catatan untuk AI kehilangan nilai saringan (HIGH ALERT, disetujui masuk rencana 2026-10-03)

- **Masalah:**
  - Gudang (sandbox) menyimpan saringan pesanan data dalam bentuk baku berlabel `values` (daftar).
  - Orc (`app/data_record.py` `scope_text`) mencari label `value`, sehingga buku catatan untuk AI tertulis
    "Industry EQ" tanpa "Banks".
  - Di g7 giliran 2, AI bingung, mengulang pesanan 3 kali, sempat mendapat angka yang salah, lalu pulih.
- **Kenapa lolos:** tes langkah 4 memakai contoh nota karangan, bukan nota asli buatan gudang.
- **Perbaikan (permanen, kontrak antar-service):**
  1. `scope_text` membaca `values`. `value` tetap diterima untuk catatan lama. Daftar panjang diringkas.
  2. Tes kontrak memakai fungsi asli sandbox `canonical_scope` untuk semua jenis saringan (EQ, IN, AND/OR/NOT,
     angka).
  3. Pelajaran di `ERRORS_AND_SOLUTIONS.md`: kode yang menampilkan atau menyalin keluaran service lain dites dengan
     keluaran asli service itu.
- **Risiko dan mitigasi:**
  - *Catatan lebih panjang.* Diringkas; batas catatan 8.000 karakter tetap berlaku.
  - *Bentuk saringan baru.* Tes membuat semua jenis node langsung dari sandbox.
- **Verifikasi:**
  - tes orc dan sandbox;
  - deploy dev;
  - g7 giliran 1–2: catatan memuat "Market Board EQ Nego", dan giliran 2 tidak mengulang pesanan.

### S28 — ruang kerja analisis tidak dikembalikan

**Kapan ruang kerja dianggap "selesai":**
- Ruang kerja dianggap selesai di akhir **setiap jawaban** (setiap giliran), bukan di akhir percakapan.
- Percakapan bisa berhenti kapan saja tanpa tanda, sehingga sistem tidak pernah tahu kapan percakapan benar-benar
  berakhir. Satu jawaban selalu punya akhir yang jelas.

**Yang tetap disimpan setelah ruang kerja dilepas** (nilai dari konfigurasi sandbox sekarang):

| Barang | Disimpan di | Bertahan | Kalau user kembali |
|---|---|---|---|
| Data yang sudah diambil (bundle) | Disk sandbox | 24 jam (`PY_SANDBOX_BUNDLE_RETENTION_HOURS`) | Dibaca ulang dari disk tanpa query ke database; ruang baru siap dalam hitungan detik |
| Tabel hasil yang sudah dirilis | Sandbox | 24 jam (`PY_SANDBOX_RESULT_RETENTION_HOURS`) | Dibuka dengan `load_output` |
| Buku catatan percakapan (definisi, temuan, rencana) | Database percakapan | Sepanjang percakapan | Langsung dibaca AI |
| Variabel sementara di memori Python | Ruang kerja | Hilang saat dilepas | Dihitung ulang dari tabel atau bundle bila perlu |

**Contoh: user pergi coffee break 1 jam, lalu kembali.** Model tidak mengulang dari awal.
- AI membaca buku catatan.
- Sistem membuka ruang kerja baru di atas data yang sudah ada di disk.
- AI memuat tabel hasil sebelumnya.

Yang hilang hanya hitungan sementara yang tidak dirilis. Kalau user kembali **lebih dari 24 jam** kemudian, data
diambil ulang dari database, tetapi rencana dan definisinya tetap sama karena ada di buku catatan.

**Langkah dekat (permanen):**
1. Di akhir setiap jawaban, orc meminta sandbox melepas semua ruang kerja milik jawaban itu:
   - ruang yang punya hasil → "siap dipakai ulang" (bisa diambil percakapan yang sama, atau digusur bila slot
     dibutuhkan);
   - ruang lain → ditutup.

   Batas menganggur 15 menit tetap ada sebagai jaring pengaman.
2. Satu ruang aktif per jawaban. Membuka ruang kedua otomatis menjadikan ruang pertama "siap dipakai ulang". Kasus g7:
   3 ruang dibuka dalam satu jawaban.
3. Antrean menggantikan penolakan "penuh": permintaan menunggu slot dengan batas waktu, lalu AI dan user diberi tahu
   bila tetap penuh.

**Risiko dan mitigasi:**
- *Giliran berikutnya butuh ruang yang sudah dilepas.* Ruang dijadikan "siap dipakai ulang", bukan dihapus, dan data
  tetap di disk.
- *Orc mati sebelum melepas ruang.* Batas 15 menit tetap ada.
- *Antrean membuat jawaban lebih lama.* Ada batas tunggu, posisi antrean diumumkan, dan ada pesan jelas bila habis
  waktu.

### R-STORE — tabel hasil tahan lama, ruang kerja sementara (masuk round 2026-10-03; DEPLOYED dev 2026-10-03, belum diverifikasi live: `OUTSTANDING_ISSUES.md` S29 / R-STORE)

**Benchmark:**
- [OpenAI Code Interpreter](https://developers.openai.com/api/docs/guides/tools-code-interpreter): ruang kerja
  kedaluwarsa setelah 20 menit tidak dipakai, isinya dibuang, dan OpenAI menyarankan data disimpan di sistem sendiri.
- [Claude code execution](https://platform.claude.com/docs/en/agents-and-tools/tool-use/code-execution-tool): setelah
  sekitar 5 menit menganggur, ruang kerja di-checkpoint dan bisa dipulihkan sampai 30 hari.
- Platform data besar (Databricks, Snowflake, BigQuery, QuantConnect): data tinggal di gudang, mesin hitung sementara,
  dan yang disimpan lama adalah resep serta hasil kecil.

**Kondisi sekarang:**

| Barang | Disimpan di | Bertahan | Saat percakapan aktif lagi |
|---|---|---|---|
| Riwayat tanya-jawab | Postgres (orc) | 30 hari | Ke AI, hanya ±4.000 token terbaru (`AI_MAX_HISTORY_TOKENS`) |
| Buku catatan | Postgres (orc) | 30 hari | Ke AI, maks. 8.000 karakter (`MAX_NOTE_CHARS`) |
| Tabel hasil | Disk sandbox | 24 jam (`PY_SANDBOX_RESULT_RETENTION_HOURS`) | Lewat 24 jam hilang, harus dihitung ulang |
| Data mentah (bundle) | Disk sandbox satu mesin | 24 jam | Lewat 24 jam diambil ulang; angka bisa bergeser karena data bertambah |
| Memori sesi Python | Sandbox | 15 menit menganggur | Mulai kosong |

**Kondisi ideal:**

| Barang | Disimpan di | Bertahan | Saat percakapan aktif lagi |
|---|---|---|---|
| Riwayat | Postgres | Selama percakapan ada | Ke AI |
| Buku catatan + resep lengkap (pesanan data, kode, **batas tanggal data**) | Postgres | Selama percakapan ada | Ke AI |
| Tabel hasil | **Postgres** (tabel besar: file di bucket, alamatnya di Postgres) | Selama percakapan ada | Hanya tabel yang **dibuka AI** (`load_output`) dimuat ke sesi baru |
| Data mentah | Cache bersama | Jam | Dipakai ulang, atau dibuat ulang dari resep dengan batas tanggal yang sama |
| Memori sesi Python | Sandbox | Dilepas di akhir setiap jawaban | Mulai kosong |

**Alur saat percakapan aktif lagi:**
1. Orc mengambil riwayat dan buku catatan dari Postgres, lalu memberikannya ke AI. Keduanya tidak masuk ke sandbox.
2. Kalau jawabannya sudah ada di catatan, AI menjawab tanpa sandbox.
3. Kalau perlu hitung, sesi baru dibuka dalam keadaan kosong. Tabel lama yang dipanggil AI diambil dari Postgres; data
   mentah diambil dari cache atau resep.
4. Jawaban selesai: tabel baru disimpan ke Postgres, lalu sesi dilepas.

**Tiga celah yang ikut ditutup:**
- **Persetujuan basi.** Tiket rencana riset kedaluwarsa 1 jam (`AI_RESEARCH_PLAN_TTL_SECONDS`). Usulan: rencana yang
  kedaluwarsa diajukan ulang otomatis dari catatan, dengan pesan "rencana ini dibuat kemarin, setujui ulang?".
- **Ingatan percakapan panjang.** Giliran lama terbuang dari riwayat. Usulan: buku catatan wajib memuat ringkasan setiap
  jawaban (angka utama + definisi), sehingga giliran lama tetap bisa dirujuk; AI tidak boleh menebak isi giliran yang
  tidak terlihat.
- **Angka bergeser.** Hitung ulang memakai batas tanggal data yang sama. Kalau user minta data terbaru, AI wajib
  menyebut bahwa angkanya berbeda dari jawaban sebelumnya.

**Hubungan dengan S28:** penyimpanan tahan lama membuat pelepasan ruang kerja di akhir setiap jawaban aman (tidak ada
yang hilang). S28 tetap butuh tiga langkahnya sendiri (lepas di akhir jawaban, satu ruang aktif per jawaban, antrean).
Untuk 100 pengguna bersamaan tetap perlu bagian 2.

**Keputusan terbuka:**
- batas ukuran tabel hasil di Postgres (usulan: 50.000 baris; lebih dari itu disimpan sebagai file di bucket);
- bawaan saat user kembali: batas tanggal lama + tawaran hitung ulang dengan data terbaru.

**Risiko dan mitigasi:**
- *Biaya penyimpanan.* Batas ukuran per tabel, dan tabel dihapus bersama percakapan.
- *Migrasi skema baru di Postgres.* Forward migration + catalog, sesuai AGENTS.md.
- *Tabel lama di disk sandbox saat transisi.* Dibaca dari keduanya selama masa peralihan.

**Verifikasi:**
- tes lokal;
- golden test baru: percakapan panjang dengan jeda lebih dari 24 jam (simulasi dengan memajukan waktu kedaluwarsa)
  yang membuka tabel lama dan mendapat angka sama.

## 2. Masa depan: banyak pengguna bersamaan (contoh 100 orang)

**Kondisi sekarang:**
- 1 mesin sandbox (replika 1) dengan 2 ruang kerja (`PY_SANDBOX_MAX_SESSIONS`, maksimal 4).
- Data bundle disimpan di disk mesin itu.
- Paling banyak 2–4 analisis bisa berjalan serentak; permintaan berikutnya ditolak "penuh".

**Yang perlu dibangun sebelum dibuka ke banyak pengguna:**

| No | Kebutuhan | Penjelasan |
|---|---|---|
| 1 | Pelepasan ruang di akhir jawaban | Bagian S28 di atas |
| 2 | Antrean | Menunggu slot, bukan langsung ditolak |
| 3 | Beberapa mesin sandbox | Pengatur membagi jawaban ke mesin yang punya ruang kosong |
| 4 | Penyimpanan data bersama | Bundle disimpan di tempat yang bisa dibaca semua mesin, supaya giliran berikutnya bisa jalan di mesin mana saja |
| 5 | Jatah per percakapan | Satu percakapan tidak boleh memakai banyak ruang sekaligus |
| 6 | Pertanyaan sederhana tanpa ruang Python | Total, ranking, dan min/maks dijawab lewat ringkasan database (G18) |
| 7 | Uji beban | Simulasi 100 percakapan untuk mengukur jumlah ruang yang dibutuhkan |

- **Perkiraan kasar (belum diukur):** satu ruang dipakai 1–3 menit per pertanyaan. Untuk 100 orang aktif, perkiraannya
  10–20 ruang serentak, atau 3–5 mesin sandbox dengan antrean. Angka pastinya diukur lewat uji beban (no. 7).
- **Benchmark:** JupyterHub (satu kernel per user di kumpulan mesin yang bisa ditambah, plus pembersih kernel
  menganggur) dan pool koneksi database (dipinjam, lalu dikembalikan di akhir permintaan).
- **Keputusan user yang masih terbuka:** tambahan biaya server dan perubahan arsitektur untuk no. 3–4.

## 3. Usulan dan keputusan yang masih terbuka (dikumpulkan dari dokumen rencana lama, audit 2026-10-06)

### 3a. Usulan yang belum disetujui

| Usulan | Asal | Catatan |
|---|---|---|
| Pengecekan ulang otomatis oleh backend untuk metrik baku (pengganti `get_evidence`, yang dihapus 2026-10-06, `EXEC.md` EXEC-E) | Keputusan 2026-10-06 | Menutup sebagian S23 tanpa beban ke AI |
| Cek angka di dalam kutipan web (angka yang ditulis AI wajib ada di kutipan) | Analisis route web orc (2026-10-06) | Celah: kutipan asli, angka atau periode salah |
| Paket 1 sisanya: eksekusi alat paralel umum, kunci relasi otomatis, perubahan mode 4 lain. (Tanggal terbuka `query_metric` dan jatah perbaikan per penyebab disetujui 2026-10-06 → `EXEC.md` EXEC-R R5) | `PLAN_2026-10-05.md` (di luar cakupan item 10/12) | — |
| Tingkat berpikir model (`AI_REASONING_EFFORT=high` di dev) | Analisis waktu (2026-10-06) | Setelan model, perlu izin user; sesudah P1–P3 |
| S23 bertahap: hitungan umum ke helper teruji, cek rekonsiliasi, hitung ulang independen | `UNDERADDRESSED_PLAN_CAT23.md` §8 | Paling mahal |
| A1, A3, A4, D (perkiraan per bagian, pesan tolak lengkap, EXPLAIN broker, tabel jawaban lebih pendek) | `EXTRACTION_AND_AUDIT_PLAN.md` "Proposed, not approved yet" | — |
| Mode EXPLORATION yang dirancang ulang | `MULTI_ANGLE_FIX_PLAN.md` "To be designed" | Sebagian tertutup mode 4 |
| Golden set dan antrean tinjauan manusia untuk klasifikasi kepentingan peristiwa | `WEB_GOVERNOR_PLAN.md` P4 | — |
| Roadmap antarmuka pengguna (tugas asinkron, progres, notifikasi) | `ROADMAP_FRONTEND_2026-10-04.md` | Usulan |
| Banyak pengguna bersamaan | §2 di atas | Biaya server |
| Multi-tugas dalam satu pesan: penyortir memecah pesan menjadi daftar tugas (jalur, nilai, perlu persetujuan atau tidak); tugas murah dijawab bersama, tugas riset digabung jadi satu rencana; hasil sebagian per tugas bila satu gagal | Diskusi "free will" 2026-10-06 (butir 1+4) | Tidak dipilih user 2026-10-06; varian + koreksi uji berganda masuk EXEC-3/EXEC-A (`EXEC.md`) |
| Cek cakupan oleh kode: setiap tugas dan varian yang diminta dijawab atau dinyatakan tidak bisa | Diskusi 2026-10-06 (butir 3) | Tidak dipilih 2026-10-06 |
| Batas ukuran multi-tugas + tanya balik "mana yang didahulukan"; memo mencatat tugas selesai/belum | Diskusi 2026-10-06 (butir 7+8) | Tidak dipilih 2026-10-06 |
| P-d: giliran UNRELATED (balasan untuk rencana yang menunggu yang ternyata pertanyaan baru) boleh langsung menjawab pertanyaan itu sambil rencana tetap menunggu, bukan hanya bertanya setuju/ubah/batal | Pemeriksaan aturan read-only 2026-10-07; `EXEC.md` EXEC-D (tidak masuk cakupan, pilihan "Rekomendasi + P-g") | Di mode 4 rencana v2 sudah ditangani router giliran (CLARIFY/INSIGHT/NEW_TOPIC); yang tersisa jalur mode 1/3 dan rencana v1 |
| Batas "maksimal dua pertanyaan berturut-turut" untuk CLARIFICATION model di giliran biasa dan di giliran UNRELATED. EXEC-D membatasi pertanyaan router dan pertanyaan giliran CANCEL; CLARIFICATION model di giliran lain belum dibatasi (sudah begitu sejak dulu, tidak ada penanda di riwayat) | `EXEC.md` EXEC-D (2026-10-07) | Perlu penanda tetap di setiap pertanyaan model |
| Router giliran mode 4 juga membaca balasan untuk rencana v1 (rencana hipotesis): perlu ringkasan rencana v1 di konteks router | `EXEC.md` EXEC-D P-b (2026-10-07) | Sekarang rencana v1 dibaca penyortir balasan rencana (bisa bertanya balik lewat UNRELATED dan giliran CANCEL) |
| Pilihan cepat yang membawa labelnya sendiri (misalnya `chosen_option` + `chosen_label`), supaya pilihan berjalur sama tetap bisa diklik dengan maknanya | `EXEC.md` EXEC-M109 (2026-10-07, tidak termasuk) | Mengubah API antara aplikasi depan dan backend |
| "Setuju, jalankan" saat rencana sudah dijalankan: jawab "rencana sudah dijalankan, ini hasilnya" alih-alih bertanya balik | `EXEC.md` EXEC-M109 (2026-10-07, tidak termasuk) | Router perlu tahu rencana yang sudah selesai |
| M127a: mode 4 menampilkan bagian riset dan usulan hanya bila ada isinya; deskripsi EXPLORE router tidak lagi mencakup pertanyaan yang tidak dijawab data pasar (outlook makro, berita), yang pergi ke FACT | `ERRORS_AND_SOLUTIONS.md` M127 (2026-10-08) | User 2026-10-08: "M137a nanti saja" (M127a) |

### 3b. Keputusan user yang masih terbuka

| Keputusan | Asal | Menghambat |
|---|---|---|
| Keputusan 6: sumber dan nama kolom ciri kelompok (contoh BUMN) | `ROUND_PLAN_2026-10-03.md` §8 | `PLAN.md` butir 8 (E2) |
| Empat keputusan rinci G2-B (urutan, min 4 angle, data < 4 angle, min families) | `FACTOR_EVENT_RESEARCH_PLAN.md` §12 | `PLAN.md` butir 10 |
| H3 kamus istilah: daftar istilah dari user | `HIGH_ALERT_PLAN.md`, `UNDERADDRESSED_PLAN_CAT23.md` kelompok 1 (M66, M13) | — |
| Toleransi pemanasan indikator (usul 0,1%) | `UNDERADDRESSED_PLAN_CAT23.md` kelompok 6 (G11, D12, G08, D14, P05) | — |
| Label "ambang diubah setelah melihat hasil" | `HIGH_ALERT_IMPLEMENTATION_PLAN.md` Langkah 5 | — |
| D02 `Undefined` vs Part A A1.4 (NULL + alasan): ubah Part A atau catat pengecualian | `UNDERADDRESSED_PLAN_CAT23.md` §7 | — |
| Otomatisasi refresh broker (D06; token Stockbit manual) | `UNDERADDRESSED_PLAN_CAT23.md` §7 | — |
| Daftar entitas dari web dipakai menyaring perhitungan (sekarang hanya label) | `HANDOFF_2026-10-05.md` (M71) | — |
| Proyek data pemegang saham | `HANDOFF_2026-10-05.md` | Jawaban "saham grup Bakrie" dari database |
| Saran aturan keluar (exit) di buku metode backtest | `HANDOFF_2026-10-05.md` | — |
| `pg_trgm` untuk salah ketik (ditunda: "No need for now") | `HANDOFF_2026-10-05.md` | `PLAN.md` butir 11 sebagian |
| Tabel makro di database (Part A) | `PLAN_2026-10-05.md` item 12 keputusan 9 | — |
| P30 trade setup (ditunda user) | `PLAN_ROUTER_MODELS_2026-10-04.md` | — |
| O1 rute penyedia berdasarkan kecepatan (keputusan "as is dulu") | `PLAN_BE_OPTIMIZATION_2026-10-04.md` | — |
| Biaya server dan arsitektur banyak mesin sandbox | §2 di atas | — |
| Bagian user: secret `RAILWAY_TOKEN` di GitHub (R33), rotasi kunci (R21), kredit OpenRouter | `ERRORS_AND_SOLUTIONS.md` | Uji live |
| EXEC-T butir 3: kalimat system prompt yang menyebut alat dipindah ke deskripsi alat atau catatan per langkah, sehingga prompt tidak menyebut alat di luar meja. Kode kunci dan "tidak bisa ditemukan" sudah jalan (P41). Biaya: prompt per meja memecah cache antar langkah mode 4; manfaat terukur 0 (tidak ada panggilan alat di luar meja di 06b, 06e, 06f). Usul: ukur token dan cache dulu bila mau dikerjakan | `EXEC.md` EXEC-T (gelombang 3, 2026-10-06) | — |
| M121 (g) batas langkah dan waktu: jeda dengan pertanyaan "lanjutkan?" saat langkah/panggilan/waktu/konteks habis, AI diberi tahu sisa anggaran, dan nilai bawaan kode (8 / 12 / 600 detik) disamakan dengan dev (60 / 60 / 1.800) | `EXEC.md` EXEC-V M121; user 2026-10-08: "—> ini pending" | Lingkungan baru memakai bawaan kode; audit: 43% jawaban memakai ≥10 langkah |
| P42: ambang sukses 0 yang tersirat dari "naik"/"turun" diterima gerbang PLAN_SUCCESS_RULE (sekarang ditolak sekali, diperbaiki edit dalam 6 dtk) | `ERRORS_AND_SOLUTIONS.md` P42 | — |

## Jalur khusus pertanyaan kualitatif murni ke `/v1/ask` (usulan 2026-10-09, ditunda)

Pertanyaan yang tidak butuh data pasar (makro murni, berita) langsung ke riset berita `/v1/ask` tanpa langkah analisis
data, lebih cepat dan murah. Butuh perubahan kriteria router, `AI_ROUTER.md` dan benchmark router. User 2026-10-09:
"bisa untuk explore jalur khusus v1/ask di exclude dulu. jalurnya lain keep as is".

## Kelengkapan Excel: hari tanpa transaksi yang tersaring (usulan 2026-10-09, menunggu keputusan)

Bukti: uji live EXEC-Y Fase 3 (`edge_58b3a299…`): data diambil dengan saringan `Investor Type = Foreign`, jadi hari
papan Nego tanpa broker asing (2026-05-26) tidak pernah masuk; model tidak bisa menulis nol, dan baris kelengkapan dengan
saringan yang sama menulis "210 dari 210". Kelas: setiap data yang disaring pada atribut di luar kunci tabel lalu
disusun per kalender (broker, tipe investor, kategori makro nanti).
- P1 (backend, jaminan): baris kelengkapan juga menghitung hari aktif kelompok dengan saringan dilonggarkan (hanya
  saringan pada kolom entitas dan kolom kelompok dipertahankan, diturunkan dari katalog); satu kueri Governor tambahan.
- P2 (panduan model): bila ada tabel dengan butir yang sama dengan hasil yang diminta dan sudah memuat ukurannya
  (contoh Feature_03), pakai tabel itu.
- Bahasa teks backend untuk pembaca selalu Indonesia, sedangkan model menulis dalam bahasa pertanyaan (limitations
  bercampur di uji yang sama). Kelas: semua teks backend untuk pembaca.
User 2026-10-09: "lanjut fase 4 dan 5 dulu" (belum diputuskan).

Desain Feature04 setelah update harga dipindahkan ke `PLAN.md` butir 13 pada 2026-10-11 setelah user menyetujui
secara umum dan mengonfirmasi urutan Telegram price lalu hasil kalkulasi Feature04. Implementasi belum dimulai.

## Perplexity Search API sebagai backend pencarian `market-web-governor` (usulan 2026-10-12, belum dikerjakan)

User 2026-10-12: "masukan perplexity API ke future plan". Riset dari dokumen resmi Perplexity dan OpenRouter
(dibaca 2026-10-12); belum ada key, kode, atau uji live.

- **Sekarang:** semua pencarian web governor (`/v1/orc/web`, `/v1/fact`, Exa di `/v1/ask`, web need) memakai
  `openrouter:web_search` engine Exa lewat satu panggilan model yang hanya menjalankan query. `config.py` mengunci
  `WEB_PROVIDER=openrouter`, dan `orc_web.py`, `fact.py`, `ask.py` menulis `"engine": "exa"` langsung di kode.
- **Opsi A, engine `perplexity` di OpenRouter** (sudah ada di `ENGINES`): USD 0,005 per request (Exa 0,007), tetapi
  filter tanggal tetap tidak diteruskan OpenRouter dan panggilan model pembungkus tetap ada. Tidak menyelesaikan W07/W16.
- **Opsi B, `POST https://api.perplexity.ai/search` langsung (usulan utama):** tanpa model; USD 5 per 1.000 request
  (`search_type: fast` USD 1 per 1.000); `search_after_date_filter` / `search_before_date_filter`,
  `last_updated_*_filter`, `search_recency_filter`, `country`, `search_language_filter`, `search_domain_filter`
  (maksimal 20, allowlist atau denylist tidak bisa dicampur); tiap hasil membawa `title`, `url`, `snippet`, `date`,
  `last_updated`; panjang teks lewat `max_tokens_per_page`. Batas 50 query per detik, tidak tergantung tier.
  Menjawab W07 (tanggal terbit) dan W16 (jendela pra-event) bila filter terbukti bekerja pada hasil.
- **Opsi C, model Sonar / Agent API:** tidak diusulkan; model yang memilih query dan menulis jawaban bertentangan
  dengan prinsip governor (query dan bukti dipegang kode, kutipan verbatim).
- **Yang perlu disiapkan:** akun API Perplexity, kredit dan alert billing (pelajaran W11); secret
  `PERPLEXITY_API_KEY` hanya di `market-web-governor`; keputusan route pertama (usul `/v1/orc/web`, lalu `/v1/fact`,
  lalu pengganti Google News RSS di `/v1/ask`) dan Standard atau Fast; konfirmasi retensi data Search API ke Perplexity
  (dokumen menyatakan zero data retention untuk Sonar API).
- **Kode (usulan):** antarmuka `SearchBackend` yang mengembalikan `{url, title, text, date, last_updated}`, dengan
  `OpenRouterExaSearch` (yang ada) dan `PerplexitySearch`; `WEB_SEARCH_BACKEND` (default `openrouter_exa`); hapus
  `"engine": "exa"` yang terkunci di kode; biaya dihitung di kode karena respons tidak membawa biaya; tanggal
  MM/DD/YYYY; deadline, retry dan pemetaan 401/402/429 seperti adapter sekarang; blocklist tetap di kode.
- **Uji:** fixture unit test; A/B Exa vs Perplexity pada 20 kasus `tests/fixtures/orc_web_cases.json`
  (web-governor-test-runner fase `orc_web`): recall, kutipan yang lolos cek verbatim, cakupan tanggal, latensi, biaya;
  uji efek filter tanggal dari hasil, bukan dari request yang diterima (pelajaran W16), misalnya kasus pra-event ULTJ;
  cek apakah filter domain `.go.id` bekerja.
- **Rollout:** dev saja, flag default mati; rollback dengan mengganti `WEB_SEARCH_BACKEND`.

## Mode insight: dimatikan? (penilaian 2026-10-16; diputuskan 2026-10-16: INSIGHT tetap dengan hipotesis dari AI, lihat EXEC-IMPL-1017 Fase 1)

Pertanyaan user 2026-10-16: "boleh tau mode insight apakah berguna? bagaimana kalo di disable? jadi hanya mode hitung
biasa dan mode jawab. coba assess". Data dari 110 giliran tersimpan di dev:

| Jalur | Jumlah | Median waktu | Median biaya | Hasil uji eksploratif |
|---|---|---|---|---|
| CLARIFY | 20 | 67 dtk | USD 0,010 | – |
| ANALYSIS | 17 | 106 dtk | USD 0,023 | – |
| INSIGHT (giliran lanjutan) | 7 | 247 dtk | USD 0,021 | 0 dari 7 |
| EXPLORE (pesan pertama) | 3 | 242 dtk | USD 0,08 | 0 dari 3 |

- 3 dari 7 giliran INSIGHT adalah permintaan cari atau hitung (run `edge_2f7523a7…`, return bulanan GOTO, broker
  penjual). Ketiga EXPLORE adalah pertanyaan sentimen atau komentar analis (web).
- User 2026-10-14: "saya hanya butuh nama brokernya saja, bukan uji research".
- Penyebab: kelas router dibedakan oleh kemampuan di belakangnya (uji multi-sudut), bukan oleh maksud user, sehingga
  batasnya dengan ANALYSIS, CLARIFY dan FACT kabur.
- Usulan (router dan catatan orc, permanen, bisa dikembalikan lewat saklar):
  - INSIGHT dan EXPLORE dihapus dari pilihan router;
  - "kenapa" atas hasil lama masuk ANALYSIS di data percakapan, dengan aturan "mulai dari tabel lama, keterkaitan bukan
    sebab";
  - penjelasan tanpa hitungan baru masuk CLARIFY;
  - sentimen atau berita masuk FACT, atau router bertanya balik;
  - uji riset hanya bila diminta jelas.
- Biaya dan pemeriksaan: benchmark router sebelum dan sesudah (±USD 0,35), `AI_ROUTER.md`, snapshot prompt; 10
  pertanyaan nyata di atas diulang dan diukur.
- Langkah sementara: `AI_FASTLANE_EXPLORE_TESTS=false` hanya menghapus uji multi-sudut; salah rute tetap terjadi.
- Fakta kode jalur cepat (diperiksa 2026-10-16, atas pertanyaan user):
  - Jalur cepat punya dua mode (`app/lanes.py` ANSWER/INSIGHT). ANSWER (Mode Jawab): rute ANALYSIS dan RESEARCH pesan
    pertama, dan giliran lanjutan selain INSIGHT. Mode ini menghitung; bila user menanyakan apakah sesuatu berlaku,
    AI menguji satu pertanyaan itu dengan kodenya sendiri, tanpa hipotesis lain dan tanpa pemeriksaan sistem.
  - INSIGHT: rute EXPLORE pesan pertama dan kelas INSIGHT giliran lanjutan. AI membuat sudut (hipotesis) sendiri,
    paling banyak 5, masing-masing satu metode pustaka riset lewat `saniti.explore_test`. Sistem mencatat setiap uji,
    mengoreksinya bersama (Benjamini–Hochberg) dan menulis baris bukti.
  - Gerbang riset (Research Plan, persetujuan user, Research Governor) tidak pernah berjalan di jalur cepat: meja
    FASTLANE melarang `start_research_run`, `run_research_code`, `complete_research_run`. Gerbang itu hanya ada di jalur
    standar atau saat membalas rencana yang menunggu.
- Keputusan terbuka:
  1. "Mode jawab" = CLARIFY?
  2. Uji riset yang diminta jelas tetap ada?
  3. Ide insight di bawah jawaban ikut dihapus?

## Data tambahan ke sesi analisis yang sedang terbuka (usulan 2026-10-15)

Dipindah ke `PLAN.md` butir 14 (user 2026-10-15: "Ok untuk solusi ... Boleh dirumuskan designnya?").

## Audit system prompt dan router 2026-10-16 (diminta user 2026-10-16, belum dieksekusi)

Permintaan user: "sekarang saya mau kamu lakukan audit terhadap system prompt dan router. review apa yang sudah ada dan
apa yang belum ada. setelah itu cek dengan best practice yang saat ini ada." Bahan: prompt dev yang dirakit dengan saklar
dev sesungguhnya (orc `771be370`), teks kedua router, benchmark 2026-10-16, dan log penalaran tiga pertanyaan live
EXEC-1018. Pembanding: Anthropic "Effective context engineering for AI agents" dan "Writing effective tools for agents",
OpenAI GPT-4.1 Prompting Guide (dipakai juga di `PROMPT_AUDIT_2026-10-05.md`).

**Ukuran yang dibaca model per panggilan (jalur cepat, dev):**
- System prompt 41.503 karakter (±13,8 rb token), 23 bagian; 84 kata mutlak (never/always/must/only).
- Catatan giliran (turn brief) ±8,7 rb karakter, 6 bagian, setiap giliran.
- 22 alat ditawarkan di setiap panggilan; skema jawaban akhir ±19 rb karakter.
- Q1: 229 rb token input untuk 5 panggilan (±46 rb per panggilan).

### Yang sudah ada (sesuai praktik baik)

- Bagian Markdown berjudul; kalimat yang menyebut alat hanya ditulis bila alat itu ditawarkan (P31).
- Satu prefiks statis per deployment, sehingga cache prompt terpakai.
- Catatan giliran sudah disatukan menjadi satu brief (O3).
- Router: keluaran terstruktur dengan enum, kartu kemampuan diturunkan dari kode (O2), tanya balik dengan batas, fallback
  tetap, tanggal hari ini, set benchmark 84 + 128 kasus yang dijalankan sebelum deploy.
- Jaminan di kode, bukan di prompt: alat dikunci per langkah, angka bersumber, uji tercatat (M171), lampiran dicek persis.

### Yang belum ada

| No | Temuan | Bukti | Praktik baik |
|---|---|---|---|
| A1 | 37,7% system prompt (±15,6 rb karakter: RESEARCH PLANS, MULTI-ANGLE PLAN, HYPOTHESIS PLAN, RESEARCH PLAN FORMS, MULTI-ANGLE/HYPOTHESIS FINDINGS) berisi aturan rencana riset jalur standar, padahal jalur cepat (default) melarang alat riset | ukuran bagian prompt dev | konteks minimal dan relevan per tugas; satu prefiks statis per jalur tetap bisa di-cache |
| A2 | Instruksi tersebar di tiga lapis (system prompt, brief, deskripsi alat) dan bisa bertentangan | Q2: "the fast-lane notes say to send a data need. However, the DATA SOURCES rule says query_metric" | satu sumber per aturan; instruksi yang bertentangan dihapus |
| A3 | Riwayat prompt tidak mencatat yang benar-benar dibaca dev: profil snapshot 39.099 karakter vs dev 41.503 (tanpa run memory, merged steps, table directives, daftar alat asli); catatan giliran (v2, lampiran, jalur cepat) tidak pernah di-snapshot, jadi perubahan prompt EXEC-IMPL-1017 tidak punya versi | `scripts/snapshot_system_prompt.py` DEV | versi untuk setiap instruksi yang dibaca model |
| A4 | Kuantitas di kata-kata user tidak dikunci di kode (M173) | Q1 | jaminan di kode, bukan aturan prompt |
| A5 | Bacaan papan pasar tidak punya default: Q2 menggabung semua papan, Q3 hanya Regular | jawaban Q2/Q3 | default tafsir tertulis (seperti O5) |
| A6 | Batas alat hanya ada di skema JSON: `query_metric` maks 20 entitas ditolak sekali (Q3); arti agregasi bila dimensi dihilangkan tidak jelas ("presumably sums across boards", Q2 dan Q3) | log | deskripsi alat menyebut batas, default dan apa yang terjadi |
| A7 | Hasil yang ditulis ulang dalam satu request tetap bisa dikutip (M174) | Q3 | — (kontrak backend) |
| A8 | Katalog tanpa identitas pasar (M175) | Q3 | — (metadata) |
| R1 | Gerbang benchmark router satu kali jalan, padahal hasil berbeda pada kode yang sama (126/128 FAIL lalu 127/128 PASS) | benchmark 2026-10-16 | ulang k kali, putuskan dengan mayoritas, catat kasus tidak stabil |
| R2 | Tidak ada umpan balik dari produksi: kasus benchmark ditulis tangan; salah rute live tidak dikumpulkan | — | pantau salah rute, masukkan ke set evaluasi |
| R3 | Router giliran condong ke kelas giliran sebelumnya (CLARIFY berulang, EXEC-IMPL-1017 Fase 3) | live 2026-10-16 | rute dari pesan sekarang; riwayat hanya konteks |
| R4 | Kartu kemampuan router teks tetap; bila saklar v2 dimatikan, kartu tetap menyebut v2 | kode | turunkan dari saklar saat start |

### Usulan (menunggu keputusan user)

- **U1 (M173), kuantitas user dikunci.** Penyebab terverifikasi: model menghitung "3 bulan" sebagai 21 hari bursa;
  kode tidak membaca atau memeriksa. Kelas: setiap kuantitas bersatuan di pesan user pada giliran analisis, di semua
  tabel. Perbaikan (orc, backend): baca rentang relatif dari pesan (angka × kata satuan; hari bursa per satuan dari
  `FASTLANE_DEFAULTS`), tulis sebagai fakta di brief, dan cek tanggal awal dan akhir tabel rilis; beda ditolak sekali.
  Menutup juga "minggu", "tahun", "hari". Tidak menutup "top N" dan ambang (tahap kedua). Risiko: kalimat dengan dua
  rentang ("3 bulan terakhir dibanding 1 tahun") harus menghasilkan dua fakta, bukan satu. Uji: kasus 1 minggu, 6 bulan,
  2 tahun, dua rentang, rentang bernama (Agustus 2026, tidak kena). Permanen.
- **U2 (M174), keluaran yang digantikan berhenti jadi sumber.** Nama yang dirilis ulang dalam satu request menggantikan
  yang lama; rujukan ke yang lama ditolak sekali dengan alamat baru. Berlaku untuk penolakan penutupan, perbaikan kode,
  rilis ulang satuan. Tidak berlaku antar giliran (hasil giliran lalu tetap sah). Uji: rilis ulang lalu kutip yang
  lama. Permanen.
- **U3 (M175), identitas di katalog.** Cek baca-saja di database bahwa total beli = total jual di setiap baris; bila
  benar, Column_Catalog Feature_02, Feature_03, IDX_Broker_Summary menyebut identitas dan cara menghitung nilai
  transaksi; profil data melaporkan kolom yang sama persis. Lapisan: metadata. Permanen.
- **U4 (A1–A3), prompt per jalur.** Dua prefiks statis: jalur cepat tanpa bagian rencana riset, jalur standar seperti
  sekarang; aturan yang dobel di brief dan system prompt disatukan; snapshot memakai profil dev asli dan ikut mencatat
  brief per jenis giliran. Risiko: cache dua prefiks; perubahan perilaku jalur cepat, jadi butuh A/B kecil. Permanen.
- **U5 (A5), default bacaan papan.** Entri `flow_board_scope` di `FASTLANE_DEFAULTS` (unit "reading"), nilai dipilih
  user (semua papan atau Regular). Berlaku untuk net asing, net broker, aliran investor. Permanen.
- **U6 (A6), batas alat di deskripsi.** Deskripsi `query_metric` menyebut batas entitas dari `MAX_ENTITIES` dan bahwa
  dimensi yang dihilangkan dijumlahkan; diturunkan dari kode. Permanen.
- **U7 (R1–R4), router.** Benchmark diulang 3 kali dan diputuskan mayoritas; log keputusan router plus sinyal salah
  rute (giliran berikut minta hitung setelah CLARIFY, tanya ulang) dikumpulkan mingguan sebagai kasus baru; kartu
  kemampuan dari saklar. Permanen.

### Tambahan 2026-10-16 (pertanyaan user atas temuan uji)

- **Kenapa AI tidak tahu batas 20 entitas (terverifikasi di kode):** `tools/registry._provider_schema` hanya mengirim
  kata kunci `type, properties, required, additionalProperties, items, anyOf, enum, description` ke penyedia model.
  `maxItems`, `minItems`, `maxLength`, `minLength`, `minimum`, `maximum` dan `pattern` dibuang; Pydantic tetap
  menegakkannya. Di model alat ada 159 ruas berbatas, 143 di antaranya tanpa angka di deskripsinya, jadi model baru
  tahu batas setelah ditolak.
  - **U6 (diganti):** saat membuang batas, `_provider_schema` menulis batas itu ke deskripsi ruas secara otomatis
    ("at most 20 items", "1–260", pola tanggal). Berlaku untuk semua alat, termasuk yang ditambah nanti. Lapisan:
    registry alat. Tidak menutup batas yang hanya diperiksa di backend (Governor, sandbox): batas itu ditulis di
    deskripsi alatnya dari konstanta kode. Risiko: deskripsi alat sedikit lebih panjang (cache sekali). Uji: setiap ruas
    berbatas memuat batasnya di skema yang dikirim; `AI_TOOLS.md` dibuat ulang.
- **U8, arti `query_metric`:** deskripsi alat dan catatan METRICS tidak menyebut bahwa dimensi yang dihilangkan
  dijumlahkan (Governor memutuskan apakah boleh); Q2 dan Q3 menulis "presumably". Perbaikan: catatan METRICS menulis
  per metrik dimensi mana yang dijumlahkan bila dihilangkan, diturunkan dari katalog metrik dan aturan Governor.
- **U2 (penyebab terverifikasi):** saat penutupan lolos, `dataneed_service` merilis semua keluaran dari setiap run yang
  berhasil di sesi, termasuk keluaran sebelum penutupan yang ditolak; nama yang sama jadi dirilis dua kali. Perbaikan di
  sandbox: untuk nama yang sama dalam satu request hanya yang terbaru dirilis, yang lama ditandai digantikan; orc
  menolak sekali rujukan ke yang lama dengan alamat baru.
- **U9, kata kategori user vs nilai tersimpan:** "perbankan" tidak cocok dengan Sector ("Financials"); nilai benar ada
  di Industry ("Banks"); butuh 3 panggilan. Perbaikan: `get_dimension_values`/`search_values` yang tidak menemukan
  kecocokan di kolom yang diminta menyebut kolom kategori lain di tabel yang sama yang cocok (diturunkan dari kamus
  nilai). Terjemahan "perbankan" ke "bank" tetap penilaian model.
- **R2, benchmark ditulis tangan:** maksudnya kasus uji router di `tests/fixtures/turn_router_cases.json` (84 kasus)
  dan `first_message_router_cases.json` (128 kasus), ditulis pengembang; bukan di system prompt. Prompt router sendiri
  memuat ±30 contoh kalimat pendek. Usulan U7 tetap: kumpulkan pesan live yang salah rute sebagai kasus baru.

- **U1b (pengganti U1, 2026-10-16):** U1 membaca kalimat user dengan aturan tetap, sehingga rapuh terhadap salah ketik
  dan bentuk lain ("tiga bulan", "3bln", "kuartal terakhir"); user mempertanyakannya. Alternatif yang tidak membaca
  kalimat: AI menyatakan rentang yang ia pakai dalam ruas terstruktur (angka, satuan, kutipan kata user), membaca
  bahasa tetap tugas AI; kode menghitung jumlah hari bursa dari `FASTLANE_DEFAULTS` dan mencocokkan dengan tanggal
  tabel hasil. Menangkap salah hitung, tidak menangkap salah baca AI atas kata user (kutipannya tampil di jawaban).
  Belum diputuskan.
- **U5, tempat penegakan pilihan papan (2026-10-16):** tiga lapisan, dari yang paling kuat:
  (1) katalog metrik: `default_scope` metrik aliran (`net_foreign_value`, `broker_net_value`) diisi papan baku, jadi
  `query_metric` memakainya kecuali AI meminta papan lain secara eksplisit (database yang menerapkan);
  (2) jalur data mentah: entri bacaan `flow_board_scope` di `FASTLANE_DEFAULTS`, dibaca AI sebagai asumsi tertulis;
  (3) teks katalog yang sudah ada ("jangan gabung tanpa sengaja") tetap. Usulan: (1) + (2). Nilai baku menunggu user.

## Export dan pilihan yang ditawarkan (usulan 2026-10-16, M176, menunggu keputusan)

Dari percakapan `conv_bef8e72a…`: tiga permintaan "minta … dalam bentuk excel" untuk data yang belum dirilis masuk kelas
CLARIFY (baca saja), AI menulis tawaran "jalankan di langkah berikutnya", dan "Gas" / "Yg saya remark" / "Cek remark"
tidak pernah menjalankannya.
- (a) Router melihat tabel hasil percakapan (nama, satu baris = apa, kolom), diturunkan dari data record.
- (b) Jalan keluar: langkah baca saja yang menemukan permintaan butuh hitungan memindahkan giliran sekali ke kelas yang
  menghitung, dalam giliran yang sama, tercatat di log.
- (c) Tawaran langkah berikut di jawaban menjadi pilihan terstruktur, sehingga "gas", "ok", "jalan" menjalankannya.
- (d) Ekspor data mentah yang sudah diambil: `export_result` menerima kebutuhan data yang sudah terkirim (baris dari database, lineage dan saringan diketahui), tanpa hitungan, sehingga boleh di giliran baca saja; di #5 AI mencobanya dengan alamat kebutuhan data dan ditolak. Menutup "minta data harian" tanpa perpindahan kelas.
- Catatan METRICS seharusnya dikirim hanya di giliran yang menawarkan `query_metric` (meja ANALYSIS, FASTLANE): `_offer_metrics` membaca alat giliran, bukan daftar alat terdaftar.
- Juga: catatan METRICS dikirim di setiap run (`_offer_metrics`) termasuk giliran yang tidak menawarkan `query_metric`
  (CLARIFY); masuk tinjauan E3.

## Memaksimalkan `query_metric` dalam batas SQL Governor (saran 2026-10-16, menunggu keputusan)

Permintaan user 2026-10-16: "saya mau maximize this feature, tapi dengan constrain yang ada dari sql governor juga.
please advise metric baiknya seperti apa. berapa batas SQL governor?"

**Batas Governor untuk `/v1/summary` (jalur `query_metric`), dibaca dari kode dan konfigurasi dev:**
- hasil paling banyak 200 baris (`summary.MAX_ROWS`); periode paling panjang 260 hari bursa atau 3.660 hari kalender;
- nilai dalam satu daftar (IN) paling banyak 500 (`extract_max_in_values`);
- perkiraan baris yang dipindai paling banyak 2.000.000; biaya rencana paling banyak 600.000;
- batas waktu query 20 detik; fungsi SUM, MIN, MAX, FIRST, LAST, COUNT; dimensi hanya boleh dilepas bila katalog kolom
  mengizinkan penjumlahannya (`cross_entity_aggregation`).

**Saran:**
1. Satu baris per saham sebagai bentuk baku: papan baku (U5) membuat net asing 1 baris per saham, bukan 3; dengan 200
   baris, 100 saham (keputusan user) selalu muat.
2. Peringkat di database: tambahkan urut dan N teratas (`ORDER BY` ukuran, `LIMIT` N ≤ 200) ke summary, sehingga
   "5 saham net beli asing terbesar 2024" dari seluruh pasar selesai dalam satu panggilan tanpa mengirim semua saham.
   Pemindaian `Feature_03` seluruh pasar setahun ±900 saham × 260 hari × 3 papan ≈ 0,7 juta baris, di bawah 2 juta
   (diukur dengan EXPLAIN sebelum dibangun).
3. Kelompok saham dari tabel referensi: saringan "Industry = Banks" (atau indeks) lewat `restrictions` yang sudah ada
   di spesifikasi summary, jadi AI tidak mengetik daftar saham.
4. Batas saham diturunkan, bukan diketik: min(100, 200 ÷ baris per saham menurut dimensi yang diminta), ditulis di
   catatan METRICS.
5. `broker_net_value` paling berat (±200 baris sumber per saham per hari): banyak saham hanya untuk periode pendek atau
   satu broker; batas pastinya dari EXPLAIN.
6. Metrik baru cukup satu baris di `AI_metric_catalog` bila tabel dan kolomnya sudah ada; kandidat ditinjau user
   (nilai transaksi tetap ditunda, keputusan D-b).

## Rujukan jauh ke belakang dan lampiran (pertanyaan user 2026-10-16, usulan)

- Yang ada sekarang: data record (tabel, hasil, temuan, fakta) mencakup seluruh percakapan; langkah analisis menerima
  riwayat sampai 50 item (25 giliran) dan `read_conversation_memory` untuk run yang lebih lama; router menerima tiga
  pertanyaan user terakhir, nama tabel dan hasil, temuan, fakta, saran yang menunggu.
- Celah: rujukan router hanya PENDING_SUGGESTION, NEWEST_RESULT, UNCLEAR, NONE; rujukan ke hasil lama menjadi UNCLEAR
  lalu ditanya balik. Usulan: router boleh menyebut satu hasil dari daftar nama hasil yang sudah ia terima (rujukan
  EARLIER_RESULT + nama), dan langkah analisis membukanya dengan alat yang ada (load_output, memori run).
- Lampiran sudah sampai ke router (baris lampiran di pesan) dan ke langkah analisis (catatan lampiran, angka yang
  dilampirkan) dan tersimpan di riwayat; celah M178 (lampiran hilang setelah run gagal).

## Rumus Excel hidup untuk angka yang dihitung ulang (penilaian 2026-10-16, menunggu keputusan)

User 2026-10-16: "apakah heavey? if so how heavy? coba bandingkan best practice apakah ini memang diperlukan."

- **Kenapa berat:** AI menghitung dengan Python bebas (pandas); kode semacam itu tidak bisa diterjemahkan otomatis ke
  rumus Excel secara umum.
- **Opsi A (ringan, ±0,5 hari):** file memuat semua input mentah (termasuk input di luar periode, lihat
  M-harga-dasar di bawah), lembar "langkah" berisi input, rumus dalam teks, dan hasil. Tanpa risiko beda angka.
- **Opsi B (sedang, ±2–3 hari):** AI menyatakan rumus reproduksi dalam bahasa ekspresi terbatas (+ − × ÷, pangkat,
  ROUND, SUM/AVERAGE rentang) atas sel input bernama. Backend menghitung ekspresi yang sama dengan Python untuk cek
  sama persis, lalu menulis rumus Excel beserta nilai tersimpannya. Risiko: pembulatan Excel (setengah ke atas) beda
  dengan Python, simpangan baku sampel vs populasi, nilai tersimpan (openpyxl tidak menghitung rumus).
- **Opsi C (berat):** menerjemahkan semua kode: tidak layak.
- **Praktik baik:** standar pemodelan keuangan (FAST, ICAEW Financial Modelling Code) meminta rumus hidup untuk model
  yang dibangun di Excel. Ekspor data dari platform analitik dan penyedia data umumnya nilai saja ditambah dokumentasi.
  Untuk tujuan user ("bisa hitung sendiri, hasilnya sama persis"), yang wajib adalah input lengkap dan langkah yang
  jelas; rumus hidup menambah kenyamanan, bukan kebenaran.
- **Rekomendasi:** belum diperlukan. Kerjakan opsi A dan kelengkapan input lebih dulu; opsi B nanti bila user ingin
  rumus yang bisa diklik.

**Harga dasar di luar file (dijelaskan ke user 2026-10-16):** return 41,3% BMRI 2022 = (penutupan 30 Des 2022 ÷
penutupan 30 Des 2021) − 1. File Excel yang diekspor hanya memuat 246 baris tahun 2022 (3 Jan–30 Des 2022), jadi
harga dasar 30 Des 2021 (Rp 3.512,5) tidak ada di file; orang yang menghitung dari file saja akan memakai 3 Jan 2022 dan
mendapat angka lain. Kelas: setiap angka yang inputnya keluar dari jendela yang diekspor (return dengan harga dasar,
jendela bergulir yang butuh pemanasan, YoY, jendela estimasi event study). Usulan: ekspor di giliran reproduksi memuat
semua baris input tabel kerja (atau backend menolak ekspor yang tanggalnya tidak mencakup input reproduksi).

## Claude "di posisi AI" dan jejak run lengkap (usulan 2026-10-17, menunggu keputusan)

Permintaan user 2026-10-17: "boleh pikirkan cara agar kita bisa buat kamu yg di AI shoes instead of a/b testing terus?
so ketika saya tanya, coba kamu run pakai model kita end to end supaya lebih cepat trouble shoot".

- **Akar masalah (terverifikasi pada run `edge_7a07`, `edge_98750`):** log tidak menyimpan apa yang dilihat dan ditulis
  model per panggilan (masukan, keluaran mentah, argumen dan hasil alat, galat sandbox, endpoint penyedia); log Railway
  terpotong per deployment. Tanpa itu setiap dugaan harus diuji ulang dengan run baru (A/B).
- **Kelas:** setiap investigasi run (lambat, salah tafsir, gerbang, galat kode), di semua model dan jalur.
- **T1 Jejak run (dev saja, saklar `AI_CAPTURE_TRACE`):** setiap panggilan model disimpan per `request_id`: payload
  ringkas (hash prefiks statis + bagian giliran), keluaran mentah termasuk teks pendek, panggilan alat dan hasilnya,
  galat sandbox, waktu per langkah, endpoint penyedia. Disimpan di Postgres dengan masa simpan 14 hari. Skrip
  `scripts/trace_run.py <request_id>` mencetak garis waktu.
- **T2 Ulang dari langkah N:** panggilan ke-N diulang dengan payload yang sama (model kita, satu panggilan, biaya kecil),
  atau dengan perubahan prompt yang diuji, tanpa menjalankan seluruh run.
- **T3 Claude di posisi AI:** endpoint dev `POST /v1/dev/agent-step` menjalankan satu panggilan alat atas nama run
  (alat yang sama, gerbang yang sama, persetujuan data tetap berlaku). Claude memakai alat persis seperti model untuk
  menemukan instruksi atau pesan galat yang kurang jelas, tanpa variasi model.
- **T4 Uji ujung ke ujung atas permintaan:** pertanyaan user dikirim ke EDGE dev dengan model pilihannya
  (`live_submit.py`, sudah ada), lalu laporan T1 dibuat otomatis.
- **Batas:** tidak menggantikan A/B ketika yang diukur adalah variasi model antar-run. T3 memakai kredensial dev,
  tidak pernah prod.
- **Uji:** jejak `edge_7a07` serupa menunjukkan panggilan 622 s dan endpointnya; ulang langkah 2 dari `edge_98750`
  menunjukkan teks 10 token; satu panggilan T3 yang ditolak gerbang menghasilkan pesan yang sama dengan model.

## Run lambat (M181, usulan 2026-10-17, menunggu keputusan)

Audit dan implementation plan 2026-10-19 untuk target yang disetujui user (reasoning 48k, penyajian 48k,
tanpa penurunan level diam-diam) ada di `PLAN.md`, bagian "Anggaran reasoning dan penyajian"; bukti di
`verification/orc_token_budget/`. Belum dieksekusi. Rencana tersebut membatasi retry/deadline dan mewajibkan
verifikasi kemampuan provider; daftar berikut adalah usulan M181 sebelumnya, bukan tambahan yang otomatis
disetujui atau jaminan bahwa byte keepalive menunjukkan kemajuan reasoning.

- Batas waktu per panggilan berdasarkan kemajuan, untuk semua panggilan dan jalur: tanpa keluaran pertama dalam N detik,
  atau tanpa byte baru selama M detik, panggilan dipotong dan diulang sekali.
- Anggaran waktu per run yang terlihat di EDGE.
- Endpoint penyedia tercatat di setiap panggilan (memperbaiki `lookup: NOT_FOUND`).
- Mengulang di endpoint lain dari model yang sama termasuk perubahan penyedia, jadi perlu persetujuan user.
- Uji: penyedia tiruan yang diam 30 detik dipotong di N; penyedia yang lambat tapi terus mengalir tidak dipotong.

## Onboarding Feature 05/06 ke AI dan indeks Governor (usulan 2026-10-22, menunggu keputusan)

Permintaan user 2026-10-22: "cek feature 1, 2, 3, 4 dan onboarding table terkait dengan bagaimana membuat feature 5 dan 6
visible ke AI … Setiap query yang dilakukan harus menggunakan indeks apabila melewati SQL Governor … cek apakah saat ini
query di SQL Governor juga melewati indeks". Semua butir di bawah dibaca dari kode `main` (`33cf07b`) dan database live
(pgweb, read-only) 2026-10-22.

**Keadaan F05/F06:** Table_Catalog, Column_Catalog (15 dan 87 kolom), Feature_Catalog (CALCULATION_VERIFIED) dan CHECK
papan/tipe investor sudah ada. Lapisan AI belum ada: tidak ada baris `AI_table_catalog`, `AI_column_catalog`,
`AI_calculation_catalog`, `AI_catalog_relationships`, `AI_data_coverage`, dan `market_ai_sql_reader` belum punya SELECT
(EXEC-F05-F06: "Tidak dibuka ke AI").

**Pola F01–F04 (NEW_TABLE_ONBOARDING_PLAN.md bagian 0, 1 dan 4, migrasi `20261020_001`):** GRANT ke
`market_ai_sql_reader`; `AI_table_catalog` BOUNDED_READ; `AI_column_catalog` dari Feature_Catalog (kolom internal
`ai_allowed = false`, mis. `source_balance_gap`); satu `AI_calculation_catalog` per kolom; relasi; coverage turunan
dari `IDX_Broker_Summary`; daftar tulis-tangan `APPROVED`, `RAW_SOURCES`/`FORBIDDEN_FEATURE_TABLES`, preview,
`WAREHOUSE_SCOPE` (sudah menyebut "broker and foreign flows").

**Indeks yang dipakai Governor (diukur, ms):**

| Tabel | Saham + 90 hari | Satu tanggal semua saham | Kalender 20 tanggal |
|---|---|---|---|
| F01 | 54 (PK) | 9 (indeks tanggal) | 25 |
| F02 | 455 (indeks tanggal) | 10.014 (indeks tanggal, baca heap dingin) | 46 |
| F03 | 94 (PK) | 12 (indeks tanggal) | 17 |
| F04 (live) | 27 (PK) | 2.506 (PK, skip scan) | **10.893** (tanpa indeks tanggal) |
| F05 | 368 (PK) | 7.408 (PK, skip scan) | **Seq Scan 45 juta baris** (tidak dijalankan) |
| F06 | 75 (PK) | 585 (indeks tanggal) | 20 |

**Usulan (urutan):**
1. **Direvisi 2026-10-22 (DATABASE_INDEX_ACCEPTANCE.md, uji F04/F05 di bawah gerbang Governor):** jalur ekstraksi F04
   dan F05 lolos dengan PK (tanpa Seq Scan); F02 dengan indeks `(date, market_board, ticker)` justru lebih lambat untuk
   cross-section, jadi tidak ada indeks tanggal umum. Yang perlu diperbaiki hanya query kalender (M204): indeks
   `(trade_date)` sempit yang diukur dulu dalam transaksi DRYRUN (buat, EXPLAIN ANALYZE, ROLLBACK), atau gerbang
   EXPLAIN untuk kalender di Governor.
2. Governor: kalender ringkasan hanya lewat indeks yang diawali kolom waktu, atau di-EXPLAIN dulu (M204), sehingga
   jaminan "lewat indeks" berlaku di semua jalur.
3. Migrasi onboarding F05/F06 dengan template `20261020_001`: GRANT, `AI_table_catalog`, `AI_column_catalog` dari
   Feature_Catalog, `AI_calculation_catalog`, relasi (F05 ↔ F06, Price, Universe, Broker Profile), preview bila
   dipilih; `APPROVED`, `coverage_job.RAW_SOURCES["IDX_Broker_Summary"]["reference_for"]` dan
   `FORBIDDEN_FEATURE_TABLES` ditambah; Tool_Catalog/router bila teksnya berubah.
4. Validasi L0–L3 (NEW_TABLE_ONBOARDING_PLAN.md bagian 5) dan penerimaan indeks (bagian 3, `scripts/onboarding/measure_indexes.py`), termasuk satu pertanyaan per tabel lewat model.

**Keputusan user yang dibutuhkan:** indeks F05 (±0,4 GB, disk 49 GB dari 75 GB); indeks F04; perbaikan Governor (2);
F05 dibuka seluruhnya atau hanya F06; preview; refresh harian F05/F06 masih manual (freshness akan BASI tanpa job).

## STOCKBIT-UPDATER — satu service Railway: token → IDX_Broker_Summary → F05/F02/F03/F06 → INDEX → tiga tabel event (usulan 2026-10-25, menunggu go)

**Permintaan user, 2026-10-25 (kata user):** "Bisa nggak buat satu service di mana ketika kita running the service, maka
data IDX Broker Summary di-ingest atau di-update dari latest updated data. Ada variable bearer token yang bisa saya update
karena tokennya akan update setiap hari. Dan ketika saya update, maka table IDX Broker Summary akan terupdate. Kemudian
feature 2, 3, 5, dan 6 juga otomatis terupdate. Termasuk 3 table yang baru saja ada terkait dengan [corporate] action dan
insider ... Script ini harus digunakan agar [Railway] bisa mengquery data. Bukan melalui lokal saya." Script yang
dilampirkan: `import_full_broker_summary.py` + `stockbit_ihsg_daily.py` (loader yang memuat 2026-09-01…10-23, M217),
`FULL_BROKER_IMPORT.md`, `audit_full_broker_import.py`. Ini menggantikan keputusan sebelumnya "untuk saat ini tidak perlu
bikin service baru" (branch `claude/keen-keller-cq1d96`, STOCKBIT-PULLER) begitu user memberi go.

**Keadaan yang diperiksa 2026-10-25** (job read-only `eb43c1ec`, `verification/broker_consistency_20261025/`):
- semua Feature 01–06 saham dan `_INDEX` sampai 2026-10-23, sama dengan tanggal terbaru harga dan `IDX_Broker_Summary`;
- 12 objek aktif di `AI_table_catalog` (BOUNDED_READ) dan bisa dibaca `market_ai_sql_reader`; F05/F06 lewat view
  `_Stock`, tabel dasarnya tertutup;
- rantai sumber (kode live): `IDX_Broker_Summary` → F05 → F02 → F03, F05 → F06; F02/F03 juga membaca `IDX_Broker_Profile`;
- per tanggal 2016-01-04…2026-10-23 (2.599 tanggal): sumber = F05 (baris, beli, jual, net, frekuensi, net asing), F05 = F02
  (baris, beli, jual, net), F02 = F03 (grup saham-papan, beli, net), F05 = F06 (net asing, total beli): 0 tanggal berbeda.

**Uji lokal script user** (Stockbit palsu, PostgreSQL lokal dengan skema live `IDX_Broker_Summary`,
`loader_local_test.py`): dua tanggal × 520 simbol masuk dan cocok dua arah; jalan ulang melewati tanggal yang sudah
selesai; nilai sumber yang dikoreksi memperbarui baris; baris warrant yang ada tidak disentuh; tanggal awal yang bukan
hari bursa ditolak (tidak dimundurkan). Yang harus diubah untuk Railway: daftar simbol dari SQLite di PC
(`--historical-state`) dan path Windows; simbol hanya 4 huruf (`^[A-Z]{4}$`, M218); state (raw, checkpoint) perlu disk
tetap; baris yang tidak lagi dikirim Stockbit membuat tanggal itu berhenti (tidak dihapus diam-diam).

**Usulan (lapisan: service Railway + fungsi refresh yang sudah ada, tanpa rumus baru):**
1. Service `stockbit-updater` (`apps/stockbit-updater/`), `restartPolicyType: NEVER`, satu putaran per deploy. Variabel
   rahasia `STOCKBIT_TOKEN` diisi user di dashboard Railway (tidak lewat chat atau Git); mengganti token lalu Deploy =
   satu putaran update. `DATABASE_URL` referensi Postgres privat. Volume kecil untuk raw response dan checkpoint.
2. Tanggal diturunkan dari data, bukan dari argumen: tanggal bursa di `Price_Stock_Indonesia_IDX` yang belum ada di
   `IDX_Broker_Summary` (termasuk gap lama), sampai tanggal harga terbaru. Tanggal yang harganya belum masuk ditunda.
3. Muat per tanggal dengan logika script user (enam filter per simbol, validasi, satu transaksi, cek dua arah 15 kolom,
   `stockbit_full_broker_import_status`), token kedaluwarsa dicek dari `exp` JWT sebelum mulai.
4. Refresh berantai untuk tanggal yang berubah (diturunkan dari selisih sumber vs F05, seperti `UPDATE_TABLE.md`
   bagian 4): F05 → F02 → F03 → F06 → INDEX (`backfill_index_features.py`), cek setiap langkah, `ANALYZE`, lalu tiga tabel
   event (loader `apps/stockbit-event-annotation/` dari branch keen-keller) dan `Database_Table_Status`.
5. Ringkasan satu baris per putaran (log, opsional Telegram).

**Yang perlu diputuskan user:** K1 warrant/rights sesudah 2026-08-31 (temukan simbol lewat endpoint aktivitas broker,
seperti loader lama, atau tetap 4 huruf); K2 hanya saat deploy (token baru) atau juga cron harian; K3 lama simpan raw
response; K4 tiga tabel event ikut dalam putaran yang sama (perlu merge branch keen-keller; migrasinya bernama
`20261025_011`, bentrok dengan `20261025_011_exclude_index_from_stock_features.sql` yang sudah diterapkan, jadi harus
diganti nomor sebelum diterapkan); K5 notifikasi Telegram.

**Risiko:** Stockbit belum terbukti bisa diakses dari IP Railway (perlu satu uji dengan token); token berlaku ±1 hari;
F02 ±3 detik per ticker (±45 menit per putaran berapa pun jumlah tanggalnya).

## STOCKBIT-PULLER — satu service Railway untuk semua tarikan Stockbit (usulan user, belum disetujui untuk dibuat)

**Usulan user, 2026-10-25 (kata user):** "Saya berpikir untuk dibuat satu service yang goalnya adalah menarik data dari Stockbit. Dengan variabel bearer token tersebut. Jadi setiap hari atau setiap saya mau update, saya tinggal update saja. Variabel bearer token dan kemudian saya tinggal minta [AI] untuk update. Data-data yang diperlukan. Masuk broker summary." Untuk saat ini tidak dibuat ("tidak perlu bikin service baru"); skrip corporate action dan insider (PLAN.md EVENT-ANNOTATION) disusun supaya bisa dipindah ke service itu. Terbuka: loader broker summary yang menulis `buy_freq`/`sell_freq` belum ada di Git (`UPDATE_TABLE.md` bagian 2); cara token disimpan (variabel tetap vs dipasang per putaran).

## Biaya Railway U1–U5 (usulan 2026-10-24 di chat, ERRORS M215; dicatat 2026-10-25, menunggu keputusan)

Diagnosis biaya ada di ERRORS M215 (bagian "Biaya"). Usulan yang diberikan di chat 2026-10-24, belum ada yang dijalankan
kecuali U2:

| # | Usulan | Lapisan | Status |
|---|---|---|---|
| U1 | Cek penyebab sandbox ±0,7 GB saat diam (daftar proses di kontainer), lalu perbaiki di sumbernya | kode sandbox | DICEK 2026-10-25 (go EXEC-GO-1025), perbaikan menunggu keputusan; lihat di bawah |
| U2 | Staging `IDX_Broker_Summary_Freq` (±10 GB) | data | SELESAI: dihapus `20261025_004`/`007` (user "Hapus saja") |
| U3 | Aturan Part A: sebelum tabel turunan baru dibuat, hitung biaya disknya; bila bisa diturunkan saat dibaca (view), jangan disimpan penuh | standar data | SELESAI 2026-10-25: ERRORS Part A butir 25 |
| U4 | Fitur sleep Railway untuk layanan yang jarang dipakai (sandbox, web-governor, audit-store, pgweb); janitor M215 (usulan A) harus dibereskan dulu supaya layanan bisa tidur | konfigurasi Railway | DICEK 2026-10-25, TIDAK dinyalakan; lihat di bawah |
| U5 | Ukur lonjakan memori Postgres per job; bila terbukti cache halaman, jadwalkan job berat berdekatan | operasional | DIUKUR 2026-10-25; penjadwalan tidak perlu; lihat di bawah |

Urutan yang disarankan: U1 → M215 usulan A → U4.

**Hasil 2026-10-25 (go EXEC-GO-1025 butir 4), dibaca dari metrik dan kode:**
- **U1.** `railway metrics --memory --raw` 7 hari: sesudah restart sandbox ±0,19-0,21 GB (2026-10-18; 2026-10-25 13:00),
  naik pada hari ada analisis (2026-10-25 18:00 0,21 → 19:00 0,75 GB) dan tidak turun saat diam (2026-10-22…24 tetap
  0,57-0,70 GB), walau session ditutup sesudah 15 menit diam (`PY_SANDBOX_SESSION_IDLE_SECONDS` 900,
  `app/sessions.py`:513). Proses utama meng-import `duckdb`/`pyarrow` saat dipakai pertama kali (`app/carried.py`:81,
  `app/dataneed_service.py`:1470, 1506) dan memorinya tinggal sampai restart. **Dugaan, belum terverifikasi:** sisa
  memori itu ada di proses utama, bukan di worker. Cek yang memastikan: RSS per proses di kontainer. `railway ssh`
  butuh kunci SSH yang didaftarkan ke akun Railway (tidak dilakukan tanpa izin user), atau satu baris log RSS per proses
  di janitor sandbox (perubahan kode kecil). Usulan sesudah terverifikasi: kerja Parquet/DuckDB proses utama dijalankan
  di subproses berumur pendek, supaya memorinya kembali ke OS. Penghematan ±0,5 GB ≈ USD 5/bulan.
  - 2026-10-26 (user: "ya, saya kasih kamu akses SSH"): SSH belum bisa dari sesi cloud ini. `railway ssh keys add` →
    "SSH key management is not supported with project tokens (`RAILWAY_TOKEN`)", dan `railway ssh` dengan token proyek
    → "Unauthorized". Klien OpenSSH dipasang dan kunci sesi dibuat, tetapi koneksi butuh token akun atau workspace
    Railway (`RAILWAY_API_TOKEN`) di secret environment, dibaca oleh sesi baru.
- **U3.** Selesai: Part A butir 25 (biaya disk dihitung di header migrasi; view bila bisa diturunkan saat dibaca).
- **U4.** Tidak dinyalakan. docs.railway.com/reference/app-sleeping: layanan tidur sesudah 5-10 menit tanpa lalu lintas
  keluar, dan permintaan pertama yang membangunkannya bisa mendapat 502. Temuan per layanan:
  - `market-audit-store` membaca Postgres tiap `outbox_poll_seconds` (`app/ingest.py`:60-66) dan pgweb memegang koneksi
    database, jadi keduanya tidak akan tidur;
  - sandbox dan web-governor bisa tidur, tetapi klien orc tidak mencoba ulang 502 atau gagal koneksi
    (`app/tools/analysis.py`:612-621, `app/tools/web_research.py`:78-83). Pertanyaan pertama sesudah layanan tidur bisa
    gagal.
  - Alur bila sandbox sedang tidur (dibaca dari kode 2026-10-26): EDGE → BFF → worker → orc tidak tidur, jadi run
    mulai seperti biasa. orc sudah menyimpan runtime sandbox sejak start (`app/runtime_recovery.py`:39-57), jadi fitur
    tidak mati. Panggilan alat pertama ke sandbox membangunkannya; bila Railway menjawab 502, `_rejected`
    (`app/tools/analysis.py`:640-648) mengembalikan "sandbox unavailable (HTTP 502)", dan bila koneksi putus
    `_call`:612-621 mengembalikan "unreachable". Keduanya sampai ke model sebagai galat alat
    (`app/tools/registry.py`:480-483); model yang memutuskan mencoba lagi atau menjawab dengan keterbatasan. Di EDGE,
    langkah itu tampil di daftar progres; jawaban bisa lebih lambat atau berisi keterbatasan. Session analisis tidak
    bertahan saat restart (`app/sessions.py`:16): sandbox tidur 5-10 menit sesudah diam, lebih cepat dari batas diam
    session 15 menit, jadi pertanyaan lanjutan sesudah jeda kehilangan session hangat. Proses aplikasi siap ±1 detik
    sesudah kontainer jalan (deploy `8f1d3d53`: `sandbox_started` 12:31:35,5, `Application startup complete` sesudahnya);
    waktu Railway menyalakan kontainer tidak tercatat.
  - Usulan (perlu go): orc memanggil `/ready` sandbox dengan retry terbatas sebelum langkah pertama yang memakainya
    (GET aman diulang), lalu sleep dinyalakan untuk sandbox saja. Penghematan maksimal RAM diam sandbox ±0,7 GB ≈ USD 7/bulan,
    dibayar dengan jeda bangun di pertanyaan pertama.
- **U5.** `railway metrics -s Postgres --memory --raw` 7 hari: sebelum batas 4 GB (2026-10-22) puncak 14,71 GB
  (2026-10-20) dan 13,56 GB (2026-10-21); sesudahnya puncak harian 0,85-1,86 GB, saat diam 0,24-0,28 GB. Puncak
  2026-10-25 sejalan dengan job (10:00 1,86 GB; 18:00 1,48 GB saat putaran stockbit-updater) dan turun kembali dalam
  satu jam. Batas memori sudah memotong biaya cache halaman; menjadwalkan job berdekatan tidak diperlukan sekarang.
