# Masalah yang belum selesai: status dan cakupan golden test (2026-10-02)

Sumber: `ERRORS_AND_SOLUTIONS.md` (kode di kolom pertama adalah rujukan ke sana). Satu masalah dimasukkan ke satu
kategori saja, yaitu dampak terberatnya.

## Arti status

| Status | Arti | Yang dibutuhkan |
|---|---|---|
| **TUNGGU-GT** | Perbaikan sudah ada di kode dan sudah jalan di dev. Belum dibuktikan dengan pertanyaan sungguhan. | Golden test |
| **SEBAGIAN** | Sudah dikurangi atau sebagian diperbaiki, tetapi akarnya belum tuntas | Golden test untuk mengukur sisanya, lalu perbaikan lanjutan |
| **BELUM** | Belum ada perbaikan (paling jauh baru usulan) | Golden test hanya mencatat apakah masih terjadi |
| **KEPUTUSAN** | Menunggu keputusan user | Keputusan, baru dikerjakan |
| **LUAR-GT** | Tidak bisa dibuktikan oleh golden test (data, infrastruktur, web) | Cek langsung ke database/log (tanpa biaya model) atau uji terpisah |

Kolom "Dicek di" menyebut pertanyaan golden test yang memperlihatkan masalahnya: g1–g5 adalah suite yang sama dengan
`ma-golden-20261002a`/`b`. g5.3 berarti giliran ke-3 di g5. g6 adalah usulan pertanyaan tambahan (lihat bawah).

## 1. Bolak-balik, tetapi jawaban akhirnya benar

| Kode | Masalah | Status | Dicek di |
|---|---|---|---|
| S21 | Nama `range` tertimpa helper | TUNGGU-GT | semua (jumlah error kode) |
| S10 | Kode analisis error lalu diperbaiki sendiri | SEBAGIAN (S19 menyeragamkan keluaran resample) | semua (jumlah `SCRIPT_ERROR`) |
| M11 | Membaca katalog halaman per halaman | SEBAGIAN | semua (jumlah panggilan katalog) |
| G17 | AI tidak bisa melihat nilai pasti kategori di tabel bertanggal (Market Board) | BELUM | g1 ("pasar reguler") |

## 2. Ada jawaban, tetapi salah (fatal)

| Kode | Masalah | Status | Dicek di |
|---|---|---|---|
| M13 | "Saham terbaik/terlikuid" memakai definisi pilihan AI | SEBAGIAN (AI wajib menyebut definisinya) | g1 |
| M66 | Pertanyaan sama, definisi berbeda ("hari crash", "bank BUMN") | BELUM, usulan kamus istilah (KEPUTUSAN) | g5.1, dibandingkan dengan run a dan b |
| M63 | Penjelasan menghitung ulang dengan cakupan berbeda | BELUM | g5.3 |
| M29 | Rencana menyebut 6 bank, eksekusi 48 | BELUM | g5.5 |
| M25 | Temuan eksperimen pertama hilang dari metadata | BELUM | g4, g5.7–8 |
| S13 | Sudut riset INVALID karena rekaman ganda | BELUM | g5.1 (langkah riset), g5.8 |
| S27 | Kalimat salah menyebut jumlah "memenuhi syarat" | BELUM | g3, g4 |
| M24 | INCONCLUSIVE terdengar seperti "ditolak" | BELUM | g4, g5 (bila hasilnya INCONCLUSIVE) |
| M28 | Definisi sukses user (mis. ≥ 10%) diganti aturan bawaan | BELUM | g6 |
| M26 | SUPPORTED walau efek di bawah batas yang disebut user | KEPUTUSAN | g6 |
| D14 | RSI/EMA berbeda dari nilai sejarah penuh | KEPUTUSAN | g6 |
| G11 / D12, G08 | Saham keliru dikeluarkan (`NO_PRIOR_CLOSE`); nilai terakhir saham tak likuid hilang | BELUM | g1, g2 (log pengecualian universe) |
| C06 | Jawaban menyebut tanggal akhir data yang salah | BELUM | g1, g2 (dibandingkan tanggal akhir di database) |
| S23 | Angka hasil kode AI tidak diperiksa ulang backend | BELUM | g1–g4: runner membandingkan dengan hitungan independen |
| D02 | Sector bernilai teks `0` | LUAR-GT (perbaikan data, cek lewat SQL) | — |

## 3. Tidak keluar jawaban (buntu)

| Kode | Masalah | Status | Dicek di |
|---|---|---|---|
| G10 | Kelayakan FEASIBLE, ekstraksi ditolak | SEBAGIAN (G13 TUNGGU-GT) | g5.7–8 |
| M42 | "Siapa broker…" dijawab rencana riset | SEBAGIAN | g5.1 |
| P05, P08 | Jawaban benar dipaksa LIMITATION karena angka parameter | BELUM | g3 ("5 hari", "5%"), g6 |
| D06 | Data broker berhenti 2026-08-31 | LUAR-GT (cek tanggal terakhir lewat SQL; refresh manual) | — |

## 4. Ada jawaban, tetapi sangat lama

| Kode | Masalah | Status | Dicek di |
|---|---|---|---|
| M67 | Soal 5 ±28 menit (penarikan 4,39 juta baris, provider lambat, rencana lama) | SEBAGIAN (G18 fase 1 + petunjuk TUNGGU-GT) | g5: total detik vs 1.660 s run b |
| M23 | Penyaringan broker 40 iterasi | SEBAGIAN | g5.1 |
| M09 | Penemuan katalog boros | BELUM | semua (jumlah panggilan katalog) |
| M37 | Jawaban terpotong karena jatah token | KEPUTUSAN (jatah per fase) | semua (`ai_final_truncated`) |
| W22 | Biaya web naik 5× | SEBAGIAN, LUAR-GT | — |

## 5. Masalah alur di backend

| Kode | Masalah | Status | Dicek di |
|---|---|---|---|
| G18 fase 1 | Ringkasan antar-saham di gudang + petunjuk ke AI | TUNGGU-GT | g1, g2, g5.1 (apakah AI memakai `aggregate`) |
| G18 fase 2 | Ringkasan antar-waktu (per bulan/periode) | BELUM | — |
| S22 | Event study dan riset v1 sebagai jalur | TUNGGU-GT | g3, g4, g5.4 |
| M56 | Pertanyaan lanjutan menjalankan ulang semua tahap | SEBAGIAN (router TUNGGU-GT) | g5.2, g5.3, g5.9 |
| S24 | Return ke depan mengintip rentang berikutnya | SEBAGIAN (event study TUNGGU-GT; jalur lain BELUM) | g3, g5.4 |
| M57, M58, M59, S25 | Label hasil, IN_SAMPLE, hasil antar tahap | TUNGGU-GT | g4, g5.4–9 |
| M60 | Semua hasil terlihat oleh AI dan API | A: TUNGGU-GT; B, C: KEPUTUSAN | g5 |
| M61 | Event study tersimpan tanpa angka ringkasannya | BELUM | g5.4 → g5.9 |
| R26 | Jejak audit langkah riset kadang tidak tersimpan | BELUM | g5 (cek audit setiap langkah riset) |
| D09 | Aturan resample | SEBAGIAN | g5.7–8 |
| S20 | Rata-rata lintas saham di bahasa rumus riset | KEPUTUSAN (usulan belum disetujui) | g5.7 |
| S18 | Batas ukuran byte keluaran | SEBAGIAN | hanya bila keluaran besar |
| D05 / D18 / D07 | Katalog belum lengkap | LUAR-GT (audit katalog lewat SQL) | — |
| C08 | Deskripsi `run_python` di Tool_Catalog tertinggal | LUAR-GT (tes drift) | — |

## 6. Lainnya

| Kode | Masalah | Status | Dicek di |
|---|---|---|---|
| M14 | Catatan berbahasa Inggris di jawaban Indonesia | BELUM | semua |
| D08 / D13 | Klasifikasi masa kini pada data historis; tanggal terbaru | SEBAGIAN | g1 |
| R22 | Runner tidak mencatat timeout-nya sendiri | BELUM | runner |
| R21 | Rotasi `AUDIT_STORE_SANDBOX_KEY` | KEPUTUSAN, LUAR-GT | — |
| R07 / R16 | Akses agen ke database Railway | SEBAGIAN, LUAR-GT | — |
| W06, W07, W08, W11 | Web Governor | BELUM/SEBAGIAN, LUAR-GT kecuali ada pertanyaan web | g7 (opsional) |

## Sudah diperbaiki, menunggu golden test (TUNGGU-GT)

| Kode | Yang diperbaiki | Dicek di |
|---|---|---|
| P22, P23 | Satuan ganda / satuan dari data | g1, g2 |
| P24, M65 | Format p; CI dipasangkan dengan p yang benar | g3, g4, g5.4–8 |
| P25, P20, P21 | Pesan penolakan menyebut sumber dan bentuk yang benar | semua (bila ada penolakan) |
| M62 | Satu aturan rencana | g5.5, g5.7 |
| M64 | Pertanyaan lanjutan merujuk hasil terbaru | g5.2 |
| G13 | Rencana layak tidak gagal karena ukuran bundle | g5.7–8 |
| G16 | "regular" vs "Regular" ditolak/dipetakan sebelum penarikan | g1 |
| M46, M48 | Kunci tambahan; perbaikan jawaban akhir | semua (jumlah percobaan final) |
| M47, M53, M54, M55, M49 | Catatan data, hasil riset besar, field rencana, spec terbungkus, ganti nama sudut | g5 |
| S19, S21 | Satu bentuk keluaran helper; `range` | g5.7–8, semua |
| G18 fase 1 + petunjuk, S22, M57–M59, S25, M60-A | lihat di atas | g1–g5 |
| M45 | Perbaikan berupa tambalan | Saklar mati: tidak teruji kecuali dinyalakan |
| W17–W20 | Linimasa dan tanggal di jawaban web | Hanya g7 (opsional) |

## Usulan golden test berikutnya (satu putaran)

1. **g1–g5 tanpa perubahan kata-kata**, supaya bisa dibandingkan dengan run a dan b (waktu, definisi M66, angka).
2. **Tambah g6 (satu pertanyaan RESEARCH)** yang menangkap tujuh masalah sekaligus: M28, M26, P05/P08, D14, M24, S27.
   Contoh: "Apakah saham bank yang RSI 14-nya di bawah 30 naik minimal 3% dalam 10 hari berikutnya? Anggap berhasil
   kalau naik ≥ 3%."
3. **g7 web (opsional, biaya provider web terpisah):** untuk W17–W20, W06–W08 dan W22.
4. **Tanpa biaya model** (sebelum golden test, cek langsung lewat SQL/log): D06, C06 (tanggal akhir data), D02,
   D05/D18/D07, C08.
5. **Yang dibaca dari log setiap run:**
   - jumlah `SCRIPT_ERROR` (S10, S19, S21);
   - jumlah panggilan katalog (M09, M11);
   - `ai_final_truncated` (M37);
   - jumlah percobaan jawaban akhir (M46, M48);
   - detik per giliran (M67, M23);
   - pemakaian `aggregate` (G18);
   - jejak audit setiap langkah riset (R26);
   - sudut INVALID (S13);
   - definisi istilah dibandingkan run a/b (M66).
