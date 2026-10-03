# Rencana ke depan (belum dijalankan)

Isi dokumen ini sudah disetujui untuk dimasukkan ke rencana, tetapi **belum boleh dijalankan sampai user menyuruh**.
Kode masalah merujuk ke `ERRORS_AND_SOLUTIONS.md`; hasil uji ada di `GOLDEN_TEST_HIGH_ALERT_2026-10-02.md`.

## 1. Antrean perbaikan dekat

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
