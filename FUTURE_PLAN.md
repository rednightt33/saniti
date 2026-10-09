# Rencana ke depan: usulan dan keputusan yang masih terbuka

Sejak 2026-10-06 (keputusan user), pekerjaan yang **sudah disetujui** tetapi belum dieksekusi ada di `PLAN.md`, dan
eksekusi yang sudah disetujui ada di `EXEC.md`.
Dokumen ini berisi sisanya:
- usulan yang belum disetujui;
- rencana masa depan;
- keputusan user yang masih terbuka.

Butir yang disetujui user dipindah ke `PLAN.md` atau `EXEC.md` pada tugas yang sama. Kode masalah merujuk ke
`ERRORS_AND_SOLUTIONS.md`.

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
