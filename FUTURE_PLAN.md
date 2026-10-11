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

## Feature04 otomatis setelah update harga (desain 2026-10-11, menunggu konfirmasi)

Permintaan user: "cek bagaimana data price diupdate dan bagaimana trigger monitoing ke telegram terjadi ...
design job ketika harga update then indikator juga auto calculate fir eligible ticker ... design dulu baru confirm".
Bagian ini **usulan**, bukan persetujuan implementasi. Pemeriksaan menggunakan SELECT melalui role `pgweb`
dengan `transaction_read_only=on`, pembacaan kode, dan Railway describe; tidak menjalankan price job atau mengirim Telegram.
Bukti: `verification/feature04/automation_design_inspection.json` dan `automation_design_railway.json` dalam direktori yang sama.

### Kondisi yang diverifikasi

- Railway `lucid-patience` / `dev`, database utama `Postgres`; service price, Feature01 dan Telegram memakai `rednightt33/saniti@main`.
- DAILY `idx-price-cron`: `python price_update.py --mode daily`, cron `0 10 * * *` UTC = 17:00 WIB.
  Scope seluruh `IDX_Stock_Universe`, saat diperiksa 844 ticker `IDX` / `stock`. Hanya candle bertanggal target diterima.
- RECOVERY `idx-price-recovery-cron`: `python price_update.py --mode recovery`, cron `0 23 * * *` UTC = 06:00 WIB
  hari berikutnya. Mengambil hanya ticker yang masih missing untuk hari kerja sebelumnya; weekend menargetkan Jumat.
- `bulk_upsert_prices()` menulis harga `(ticker,date)` dan `ingestion_time=statement_timestamp()`;
  pengulangan dengan OHLCV sama tetap memperbarui timestamp. Harga dan `Monitoring_Price_ALL` commit bersama.
  Shared advisory lock mencegah dua price run menulis bersamaan. Weekend DAILY dicatat SKIPPED.
- Sesudah commit, `commit_monitoring_and_notify()` POST `{source_table: Monitoring_Price_ALL, execution_id}`
  ke private `/notify`, autentikasi `X-Notify-Secret`; default empat percobaan, timeout 20 detik.
  `telegram-monitor` membaca monitoring, mengirim pesan, lalu mencatat `Telegram_Notification_Log`.
  Dedup key `(source_table,source_execution_id,notification_type)`; SENT dilewati, SENDING segar dianggap in-progress.
  Service tidur saat idle, tidak mempunyai cron/polling DB. Kegagalan Telegram tidak membatalkan harga.
- `/run_price` dan `/run_recovery` masuk melalui `telegram-trigger`: webhook secret + owner Chat ID,
  dedup Telegram update ID + cooldown, lalu Railway Run Now. Acknowledgement awal berbeda dari hasil akhir monitor.
- Pada 9 Oktober DAILY memperbarui 827/844 ticker, missing 17; pesan hasil SENT.
  RECOVERY terbaru 11 Oktober WIB menargetkan 9 Oktober, mendapat 0 dari 17, NEEDS_REVIEW; pesan juga SENT.
- Trigger harga yang aktif hanya enqueue Feature01 dan pencatatan status tabel. Feature01 mempunyai 14.907 queue item DONE,
  841 ticker status SUCCESS. Queue/status tersebut memiliki CHECK khusus `Feature_01_Stock_Daily`.
  Feature04 belum mempunyai trigger/worker otomatis; harga dan Feature04 saat pemeriksaan sama-sama 1.318.633 baris,
  844 ticker, tanggal maksimum 2026-10-09. Kelengkapan sekarang berasal dari backfill manual.
- Rujukan kode: `apps/idx-price-cron/price_update.py`, `apps/telegram-monitor/telegram_monitor.py`,
  `apps/telegram-trigger/telegram_trigger.py`, `apps/feature-01-worker/worker.py`, dan migration `20260913_004`, `20260913_006`.

### Rekomendasi alur dan eligibility

```text
TradingView -> price UPSERT + Feature04 enqueue + membership batch + monitoring (satu commit)
                    |                              |
                    |                              +-> pesan hasil harga yang sudah ada
                    v
             feature-04-worker -> replay per ticker -> Feature04 + audit (commit atomik)
                    |
                    +-> batch selesai -> notification outbox -> telegram-monitor -> pesan hasil indikator
```

Default usulan eligibility: semua ticker sumber yang mempunyai candle `Daily` valid dan baru masuk/berubah,
termasuk ticker baru; tidak mensyaratkan 200 bar, volume positif, ADX tertentu, atau breakout.
History pendek tetap dihitung; NULL warmup EMA200/ADX/SMI tetap mengikuti definisi masing-masing kolom.
Ticker tanpa candle target tidak dibuatkan candle/indikator palsu dan dihitung sebagai missing price, terpisah dari failed calculation.
Pertanyaan filter universe/daftar pilihan diajukan; default ini masih menunggu konfirmasi user.
Re-ingestion identik ketika output masih current tidak memicu kalkulasi; input relevant adalah tanggal, ticker,
timeframe dan OHLCV. Pergantian company_name/query_date/ingestion_time saja bukan perubahan rumus.
Jika output belum current atau versi kalkulasi berbeda, re-ingestion identik tetap dapat menjadwalkan perbaikan.

### Queue, worker dan jaminan konsistensi

1. Buat trigger enqueue Feature04 yang ringan pada perubahan harga relevan. Berbeda dari Feature01,
   enqueue tidak bergantung pada `ingestion_time` non-NULL: koreksi history dengan timestamp lama/NULL tetap tertangkap.
   Perubahan valid menjadi invalid juga harus enqueue: engine menulis NULL dan mereset state sesuai kontraknya,
   kemudian monitoring NEEDS_REVIEW; tidak boleh diam-diam mempertahankan indikator lama.
   Jika identitas ticker/date/timeframe berubah, tandai kelompok lama dan baru serta hapus target key yang ditinggalkan
   dalam penyelesaian worker. DELETE candle juga menjadwalkan kelompok lama; TRUNCATE di luar flow ini perlu rekonsiliasi eksplisit.
2. Gunakan queue khusus Feature04, satu row `(ticker,timeframe)`, menggabungkan beberapa perubahan dalam ticker.
   Simpan `dirty_from_date` paling awal, `requested_generation`, `completed_generation`, `calculation_version`,
   state PENDING/PROCESSING/DONE/FAILED, claim token/lease, retry dan error. Generation naik monotonik pada perubahan input;
   jangan memakai `max(date)` atau timestamp ingestion sebagai satu-satunya freshness marker.
   Queue baru tidak memakai FK ke satu candle agar koreksi/DELETE bisa diproses.
3. Worker Railway baru `feature-04-worker`, satu replica, proses ticker serial, polling idle 5 detik; tanpa cron dan TradingView.
   Claim pendek dengan `FOR UPDATE SKIP LOCKED`, lease 10 menit; lima percobaan per generation dengan exponential backoff
   mulai 30 detik, cap 30 menit. Retry ticker gagal tidak menghalangi ticker lain. Lease kedaluwarsa dapat direclaim.
4. Baca snapshot konsisten seluruh history ticker, tanggal paling lama sampai terbaru, dengan pinned engine v3
   `features/feature04/engine.py` dan `swing.py`. Jangan membatasi ke 200 atau 120 bar: EMA, ADX dan SMI/swing rekursif;
   koreksi lama bisa memengaruhi seluruh tanggal berikutnya. Full replay juga menjaga indeks `temp_*_bar`.
   Stage pertama mempertahankan batas aman 5.000 observasi/ticker; yang melebihi batas FAILED dengan alasan, bukan dipotong.
   Jika DELETE mengosongkan seluruh history, worker membersihkan target ticker dan mencatat SOURCE_EMPTY; tidak memanggil replay kosong.
5. Hitung dari snapshot tanpa menahan queue row lock selama CPU work. Snapshot harus membaca generation yang sesuai claim.
   Di transaksi final yang pendek, ambil existing Feature04 advisory lock dan queue row lock, periksa claim token,
   generation dan versi lagi. Jika sudah berubah, buang hasil lama sebagai SUPERSEDED dan proses ulang generation terbaru.
   Price update yang belum commit tetap akan membuka pekerjaan baru setelahnya. Tidak ada stale completion yang menutup perubahan baru.
6. Upsert suffix dari `dirty_from_date` sampai tanggal terbaru, reconcile key yang hilang/berubah, validasi seluruh payload
   yang ditulis, lalu commit output + completion generation + attempt SUCCESS bersama. Payload identik mempertahankan
   `calculated_at`. NULL yang sah bukan failed calculation. Source hash memakai input rumus, bukan ingestion metadata.
   Snapshot lama atau exception tidak boleh menulis sebagian output maupun menandai DONE.
7. Freshness dinilai dari `completed_generation=requested_generation` dan versi engine yang sesuai, bukan tanggal maksimum saja.
   Formula tetap v3, 55 kolom yang ada, termasuk `break_swing_high` INTEGER 1/0 pada bar valid.

### Batch monitoring dan Telegram

Untuk setiap price execution, price writer memasang transaction-local execution ID sebelum UPSERT dan membuat run
Feature04 OPEN di transaksi yang sama. Trigger mencatat membership ticker beserta required generation; setelah UPSERT,
writer menyegel run READY, atau SKIPPED bila tidak ada candle yang berhasil ditulis. Worker hanya membaca run committed/sealed.
Koreksi SQL tanpa execution ID tetap otomatis masuk queue; audit mencatat origin ADHOC, kegagalan terminal mempunyai alert
dedup per ticker/generation. Tidak membuat batch Telegram per satu candle history.

Worker memperbarui hasil member dari generation yang benar-benar selesai. Generation lebih baru yang selesai dapat
memenuhi member lama, dengan label bahwa hasil memakai source terbaru. Jangan mengklaim rekonstruksi snapshot historis
execution lama. Run final ketika semua member mencapai hasil terminal: SUCCESS, PARTIAL, NEEDS_REVIEW, FAILED atau SKIPPED;
pisahkan status kalkulasi dari status PARTIAL/NEEDS_REVIEW price run. Bedakan validasi output berhasil dari freshness current.
Batch yang macet melewati 30 menit mendapat satu alert keterlambatan; hasil akhir nanti tetap dikirim.

Usulan lima tabel baru (semua nama belum dibuat):

| Objek | Grain / fungsi |
|---|---|
| `Feature04_Calculation_Queue` | Satu row per ticker/timeframe; work coalescing dan status freshness. |
| `Feature04_Calculation_Log` | Satu completed attempt; SUCCESS/FAILED/SUPERSEDED, generation, source/output hash, durasi dan changed rows. |
| `Monitoring_Feature04` | Satu run per source execution; price scope, updated/missing, calculation scope, counts, status dan waktu. |
| `Monitoring_Feature04_Ticker` | Satu ticker/timeframe per run; required generation, outcome dan error. |
| `Feature04_Notification_Outbox` | Satu event per run/type, atau ADHOC ticker/generation/error; payload reference, lease, next retry dan delivery state. |

Commit run terminal + outbox event atomik; dispatcher dalam worker mengirim hanya referensi run/event ke notifier.
Perlu memperluas allowlist/formatter `telegram-monitor` karena sekarang hanya menerima `Monitoring_Price_ALL`.
Pesan harga tetap segera dikirim; pesan indikator menyusul satu ringkasan per batch yang berisi tanggal, berhasil/eligible,
failed/missing-price, durasi dan ticker bermasalah. Contoh hipotetis: "Feature04 DAILY — 827/827 calculated; price missing 17".
Batch SKIPPED tanpa input baru tidak menambah pesan indikator. Ini monitoring kalkulasi; alert trading breakout merupakan scope terpisah.
Outbox bertahan jika worker/notifier mati dan dapat retry setelah restart; POST 202/in_progress bukan bukti delivery SENT.
Dispatcher memastikan status SENT melalui log delivery sebelum menutup outbox, menggunakan acknowledgement/status read internal.
Untuk FAILED Telegram retry dibatasi dengan backoff, lalu disimpan untuk replay operator, tanpa mengulang TradingView/kalkulasi.
Dedup menahan pengiriman normal berulang; timeout setelah Telegram menerima tetapi sebelum log commit masih bisa menghasilkan
duplikasi. Tidak menjanjikan exactly-once delivery ke API Telegram.

### Biaya, rollout, acceptance dan rollback (baru setelah disetujui)

- Full v3 backfill 844 ticker sebelumnya memerlukan sekitar 344 detik. Ini baseline serial dengan banyak write/verification,
  bukan SLA daily; daily tetap replay history tetapi biasanya menulis satu candle baru per ticker. Ukur compute/DB/latency
  untuk BBCA dahulu. Tambahan biaya satu worker selalu aktif dan polling; jumlah perubahan ticker menentukan work, bukan 844 scan jobs tiap poll.
- Runtime baru membungkus pure engine, tidak langsung menjalankan CLI backfill/manual dengan run ID lama. Docker build perlu
  memasukkan shared `features/feature04` dan pinned dependencies; root build repo dengan Dockerfile khusus worker,
  watch paths worker + shared engine, supaya perubahan engine benar-benar deploy. Price/Telegram watch paths tetap scoped.
- Forward migration + semua catalog/schema docs, least-privilege worker role (SELECT harga, write Feature04/control saja),
  atomic enqueue routines dengan privilege terukur, index queue/member/outbox berdasarkan query plans yang diukur.
- Pasang trigger + durably capture perubahan sebelum worker aktivasi. Bootstrap queue untuk seluruh source ticker dan
  hitung/validasi sebagai baseline; jangan mengasumsikan current dari equal max date/count atau mengisi ingestion timestamp lama.
  Simpan activation generation/version; perubahan selama bootstrap tidak boleh hilang. Canary BBCA dahulu, lalu seluruh eligible ticker.
- Acceptance: insert candle baru; correction lama mengubah downstream sesuai full engine; identical re-ingestion no-op;
  history pendek dengan NULL sah; zero-volume valid; invalid input reset; ticker baru; perubahan ketika worker sedang menghitung;
  source rollback tanpa queue; lease/restart/retry; writer manual lock; identity/DELETE; partial price run; notifier outage
  dan duplicate/in-progress requests. Canary tidak membutuhkan TradingView query atau Telegram send tanpa otorisasi tahap eksekusi.
- Rekonsiliasi startup dan berkala (usulan 1x/hari dalam worker) memeriksa source input fingerprints, missing target keys,
  versi, stuck generations dan notification outbox; enqueue hanya drift. Biaya full fingerprint scan harus diukur, bukan
  mengandalkan freshness per max date yang tidak menangkap koreksi lama.
- Rollback operasional: pause worker/dispatcher, pertahankan price cron dan queue capture agar pending work tidak hilang;
  kembalikan deployment notifier/price integration bila perlu. Tidak drop output/control/history; perbaiki lalu replay antrean.

Keputusan yang diminta: eligibility semua ticker Daily valid (atau filter pilihan), satu worker serial khusus Feature04,
dan pesan indikator terpisah setelah setiap batch non-empty selesai. Implementasi menunggu konfirmasi user.
