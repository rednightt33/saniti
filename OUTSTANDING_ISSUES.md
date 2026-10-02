# Masalah yang belum selesai, dikelompokkan (2026-10-02)

Sumber: `ERRORS_AND_SOLUTIONS.md` (kode di kolom pertama adalah rujukan ke sana). Hanya entri yang masih terbuka
(OPEN, MITIGATED, menunggu keputusan). Entri yang sudah diperbaiki di kode tetapi belum dibuktikan di uji live ada di
bagian terakhir, terpisah, karena statusnya berbeda: kodenya selesai, buktinya belum.

Satu masalah dimasukkan ke satu kelompok saja, yaitu kelompok dampak terberatnya.

## 1. Bolak-balik, tetapi jawaban akhirnya benar

AI tersandung, memperbaiki sendiri, lalu sampai di jawaban yang benar. Biayanya waktu dan token.

| Kode | Masalah |
|---|---|
| S10 | Kode analisis error (nama variabel, kolom keluaran helper resample) lalu diperbaiki di giliran berikut |
| S21 | Menyisipkan kolom `rank` gagal karena nama `range` tertimpa helper; perbaikan ada di cabang, belum di-deploy |
| G17 | AI tidak bisa melihat nilai pasti kolom kategori di tabel bertanggal (mis. Market Board), lalu mencari lama |
| M11 | Membaca katalog halaman per halaman sampai batas iterasi (sudah dibatasi) |

## 2. Ada jawaban, tetapi salah (fatal: angka, label, atau isi jawaban)

| Kode | Masalah | Jenis |
|---|---|---|
| M66 | Pertanyaan yang sama memberi definisi berbeda ("hari crash", "bank BUMN") sehingga broker teratas berbeda antar-run | jawaban berbeda-beda |
| M63 | Penjelasan (INSIGHT) menghitung ulang dengan cakupan berbeda dari tabel yang dijelaskan | angka tidak cocok dengan tabelnya |
| M28 | Definisi sukses yang disetujui user (return ≥ 10%) diganti aturan bawaan (> 0) oleh backend | angka salah |
| M26 | Status SUPPORTED walau efeknya di bawah batas yang disebut user (perlu keputusan user) | label salah |
| M29 | Rencana menyebut ±6 bank, eksekusi memakai 48 | isi rencana ≠ yang dijalankan |
| M25 | Dua eksperimen, hanya temuan kedua yang tampil di metadata | hasil hilang |
| S13 | Sudut riset ditandai INVALID (rekaman ganda) padahal penjaga seharusnya mencegah; penyebab belum terbukti | label salah |
| S27 | Kalimat menyebut 2.258 sebagai "memenuhi syarat" padahal itu jumlah yang dipakai (3.658 yang memenuhi syarat) | label salah, angka benar |
| M24 | Kata-kata hasil INCONCLUSIVE terdengar seperti "ditolak"; MDE disebut "efek terbesar" | label salah |
| G11 / D12 | Saham dikeluarkan sebagai `NO_PRIOR_CLOSE` walau harga sebelumnya ada (pemanasan dalam hari bursa, bukan per saham) | universe salah |
| G08 | Nilai terakhir saham tidak likuid sebelum periode bisa hilang dari bundle | angka salah (dugaan) |
| D14 | Indikator rekursif (RSI, EMA) berbeda dari nilai sejarah penuh (EMA50 +3,3%); perlu keputusan user | angka salah |
| C06 | Jawaban menyebut data berakhir lebih awal dari yang sebenarnya (ringkasan katalog lama) | fakta salah |
| D02 | Tiga saham punya Sector bernilai teks `0` dan muncul sebagai sektor | data salah |
| S23 | Angka yang dihitung kode AI sendiri tidak diperiksa ulang backend (hanya event study dan riset yang dihitung ulang) | risiko sistemik |
| M13 | "Saham terbaik" dijawab dengan definisi pilihan AI (sudah diminta disebutkan) | definisi |

## 3. Tidak keluar jawaban (buntu)

| Kode | Masalah |
|---|---|
| P05, P08 | Jawaban yang benar dipaksa jadi LIMITATION karena angka parameter (mis. "5, 10, 30", "0,6") dianggap tak bersumber |
| G10 | Cek kelayakan bilang FEASIBLE, tetapi 7 dari 8 ekstraksi ditolak biaya join, sehingga berakhir LIMITATION |
| D06 | Pertanyaan broker untuk September dijawab LIMITATION: data broker berhenti 2026-08-31 (refresh manual) |
| M42 | Pertanyaan "siapa broker…" dijawab rencana riset, bukan daftar broker |

## 4. Ada jawaban, tetapi sangat lama

| Kode | Masalah |
|---|---|
| M67 | Soal 5 (9 giliran) ±28 menit: provider lambat (77 token/detik), penarikan 4,39 juta baris (sudah ditangani G18 fase 1), rencana yang berpikir lama |
| M23 | Penyaringan broker: 40 iterasi, 27 menit |
| M37 | Jawaban terpotong karena jatah token habis untuk berpikir, lalu diulang (keputusan jatah per fase belum) |
| M09 | Penemuan katalog 73 panggilan (28% biaya) pada kasus lama |
| W22 | Biaya `/v1/ask` web naik 5× setelah membaca artikel |

## 5. Masalah alur di backend

| Kode | Masalah |
|---|---|
| G18 fase 2 | Ringkasan antar-waktu (total per bulan/periode) belum ada |
| S20 | Langkah riset tidak bisa memakai rata-rata lintas saham dalam bahasa rumusnya (cross-sectional), jadi menarik data penuh |
| S22 | Event study dan uji hipotesis ada di kode tetapi belum sepenuhnya bisa dipakai AI sebagai jalur |
| M56 | Pertanyaan lanjutan "jelaskan angka ini" di mode 4 menjalankan ulang seluruh pipeline (router sudah ada; verifikasi live) |
| M61 | Event study disimpan di catatan percakapan tanpa angka ringkasannya |
| S24 | Return ke depan di akhir satu rentang bisa membaca harga rentang berikutnya (di event study sudah dicegah; jalur lain belum) |
| S18 | Batas ukuran byte keluaran tabel masih ada |
| D09 | Resample dikerjakan kode AI; aturan resample menunggu rollout |
| D05 / D18 / D07 | Katalog belum lengkap: nilai rolling kosong di beberapa tanggal, `example_value` kosong, unit `null` di beberapa kolom |
| C08 | Deskripsi alat sesi (`run_python`) di Tool_Catalog tertinggal dari kode |
| R26 | Jejak audit langkah riset kadang tidak tersimpan |
| M57–M60, S25 | Perbaikan visibilitas hasil antar-langkah ada di cabang, sebagian belum diputuskan |

## 6. Lainnya

| Kode | Masalah |
|---|---|
| R21 | Rotasi `AUDIT_STORE_SANDBOX_KEY` (keputusan user) |
| R07, R16 | Akses agen ke database/SSH Railway terbatas (diatasi dengan job sementara) |
| R22 | Runner uji tidak mencatat timeout-nya sendiri |
| M14 | Catatan gerbang berbahasa Inggris di jawaban berbahasa Indonesia |
| D08, D13 | Peringatan klasifikasi masa kini pada data historis; tanggal terbaru berbeda antar-analisis (dimitigasi) |
| W06, W07, W08, W11 | Web Governor: domain tunggal tidak pernah lengkap, tanggal terbit kosong, jumlah pencarian tak terkendali, kredit provider |

## Sudah diperbaiki di kode, belum dibuktikan di uji live

Masuk golden test berikutnya: P22–P25, M62, M64, M65, G18 fase 1 (+ petunjuk ringkasan), G13, G16, M46–M49, M53–M55,
P20, P21, S19, W17–W20. M45 (perbaikan tambalan) ada di kode tetapi saklarnya mati.
