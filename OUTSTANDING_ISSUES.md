# Masalah yang belum selesai: status (2026-10-02)

Sumber: `ERRORS_AND_SOLUTIONS.md` (kode adalah rujukan ke sana). Satu masalah dimasukkan ke satu kategori saja, yaitu
dampak terberatnya.

Status:
- **MENUNGGU GOLDEN TEST**: perbaikan sudah jalan di dev, tinggal dibuktikan.
- **UNDERADDRESSED**: belum ada perbaikan, atau baru sebagian.
- **KEPUTUSAN USER**: menunggu keputusan.
- **(luar GT)**: tidak bisa dibuktikan lewat golden test; dicek lewat database, log, atau uji terpisah.

Dalam kurung: pertanyaan golden test yang memperlihatkannya (g1–g5 = suite `ma-golden-20261002a`, g5.3 = giliran ke-3,
g6 = usulan pertanyaan tambahan).

## 1. Bolak-balik, tetapi jawaban akhirnya benar

- S21: nama `range` tertimpa helper. --> MENUNGGU GOLDEN TEST (semua)
- S10: kode analisis error lalu diperbaiki sendiri. --> UNDERADDRESSED, sebagian (S19 menunggu golden test) (semua)
- M11: membaca katalog halaman per halaman. --> UNDERADDRESSED, sudah dibatasi (semua)
- G17: AI tidak bisa melihat nilai pasti kategori di tabel bertanggal. --> UNDERADDRESSED (g1)

## 2. Ada jawaban, tetapi salah (fatal)

- **[HIGH ALERT]** M66: pertanyaan sama, definisi "hari crash" / "bank BUMN" berbeda. --> UNDERADDRESSED + KEPUTUSAN USER (kamus istilah); terulang di GT 2026-10-02c (g1 vs g1_repeat: definisi "paling likuid" berbeda)
- **[HIGH ALERT]** M63: penjelasan menghitung ulang dengan cakupan berbeda dari tabelnya. --> TERBUKTI (GT `ma-golden-20261002c`): g7 tetap di papan Nego, g5.3 menjelaskan dari tabel asal; celah baru M68 (nilai filter hilang dari catatan) UNDERADDRESSED
- **[HIGH ALERT]** M28: definisi sukses dari user diganti aturan bawaan. --> TERBUKTI untuk rencana hipotesis (GT `ma-golden-20261002c`); jalur riset multi-sudut (mode 4) belum mengikat ambang: M69 UNDERADDRESSED
- **[HIGH ALERT]** M26: SUPPORTED walau efek di bawah batas yang disebut user. --> KEPUTUSAN USER (g6)
- **[HIGH ALERT]** M29: rencana menyebut 6 bank, eksekusi 48. --> TERBUKTI (GT `ma-golden-20261002c`): gerbang menolak angka rencana tanpa sumber
- M25: temuan eksperimen pertama hilang dari metadata. --> TERBUKTI (GT `ma-golden-20261002c`)
- S13: sudut riset INVALID karena rekaman ganda. --> TIDAK MUNCUL LAGI (GT `ma-golden-20261002c`) (0 dari 25 sudut; jalur penolakan host belum terpicu)
- S27: kalimat salah menyebut jumlah "memenuhi syarat". --> TERBUKTI (GT `ma-golden-20261002c`)
- M24: INCONCLUSIVE terdengar seperti "ditolak". --> UNDERADDRESSED (g4, g6)
- G11/D12, G08: saham keliru dikeluarkan; nilai terakhir saham tak likuid hilang. --> UNDERADDRESSED (g1, g2)
- D14: RSI/EMA berbeda dari nilai sejarah penuh. --> KEPUTUSAN USER (g6)
- C06: tanggal akhir data salah disebut. --> UNDERADDRESSED, sebagian (cron dua kali sehari TEMPORARY sudah live, belum bisa dinilai di GT 2026-10-02c karena jadwal 10:30 UTC pertama baru besok; penyegaran setelah muat dan rentang "LATEST" belum)
- D02: sektor bernilai "0". --> SELESAI di dev ("Undefined", migrasi 20261003_001, dibaca balik) (luar GT)
- **[HIGH ALERT]** S23: angka hasil kode AI tidak diperiksa ulang backend. --> UNDERADDRESSED (g1–g4 dibandingkan hitungan independen)
- **[HIGH ALERT]** M13: "saham terbaik" memakai definisi pilihan AI. --> UNDERADDRESSED, sebagian (AI wajib menyebut definisinya) (g1)

## 3. Tidak keluar jawaban (buntu)

- P05/P08: jawaban benar dipaksa LIMITATION karena angka parameter. --> UNDERADDRESSED (g3, g6)
- G10: FEASIBLE tetapi 7 dari 8 penarikan ditolak. --> MENUNGGU GOLDEN TEST (lewat G13) (g5.7–8)
- D06: data broker berhenti 31 Agustus. --> UNDERADDRESSED (luar GT, refresh manual)
- M42: "siapa broker…" dijawab rencana riset. --> UNDERADDRESSED, sebagian (g5.1)

## 4. Ada jawaban, tetapi sangat lama

- M67: soal 5 sekitar 28 menit. --> MENUNGGU GOLDEN TEST untuk bagian penarikan data (G18 fase 1); provider lambat dan rencana yang berpikir lama UNDERADDRESSED (g5)
- M23: penyaringan broker 27 menit. --> UNDERADDRESSED, sebagian (g5.1)
- M37: jawaban terpotong karena jatah token habis. --> KEPUTUSAN USER (jatah per fase) (semua)
- M09: penemuan katalog boros. --> UNDERADDRESSED (semua)
- W22: biaya web naik 5×. --> UNDERADDRESSED, sebagian (luar GT, kecuali g7 web)

## 5. Masalah alur di backend

- G18 fase 1 + petunjuk ringkasan. --> MENUNGGU GOLDEN TEST (g1, g2, g5.1)
- G18 fase 2: ringkasan antar-waktu. --> UNDERADDRESSED (belum dibuat)
- S20: riset belum bisa memakai rata-rata lintas saham. --> UNDERADDRESSED + KEPUTUSAN USER (g5.7)
- S22: event study belum sepenuhnya bisa dipakai AI sebagai jalur. --> MENUNGGU GOLDEN TEST (g3, g4, g5.4)
- M56: pertanyaan lanjutan menjalankan ulang semua tahap. --> MENUNGGU GOLDEN TEST untuk router; temuan riset di catatan percakapan UNDERADDRESSED (g5.2, g5.3, g5.9)
- M61: event study tersimpan tanpa angka ringkasannya. --> UNDERADDRESSED (g5.4 → g5.9)
- R26: jejak audit langkah riset tidak tersimpan. --> UNDERADDRESSED (g5)
- S24: return ke depan bisa "mengintip" rentang berikutnya. --> MENUNGGU GOLDEN TEST untuk event study; jalur lain UNDERADDRESSED (g3, g5.4)
- S18: batas ukuran keluaran. --> UNDERADDRESSED, sebagian (batas baris sudah dihapus; batas byte belum)
- D09: aturan resample. --> UNDERADDRESSED, sebagian (g5.7–8)
- D05/D18/D07: katalog belum lengkap. --> UNDERADDRESSED (luar GT, audit katalog)
- C08: deskripsi alat tertinggal dari kode. --> UNDERADDRESSED, sebagian (`run_python` v2 dan `submit_data_need_spec` v6 kini dibuat dari kode dengan tes drift; alat lain belum) (luar GT)
- M57, M58, M59, S25: label hasil, IN_SAMPLE, hasil antar tahap. --> MENUNGGU GOLDEN TEST (g4, g5.4–9)
- M60: semua hasil terlihat oleh AI dan API. --> bagian A MENUNGGU GOLDEN TEST; B dan C KEPUTUSAN USER (g5)

## 6. Lainnya

- R21: rotasi kunci audit. --> KEPUTUSAN USER (luar GT)
- R07/R16: akses agen ke database terbatas. --> UNDERADDRESSED, sebagian (luar GT; diatasi job sementara)
- R22: runner uji tidak mencatat timeout-nya sendiri. --> UNDERADDRESSED
- R27: migrasi gagal karena tanda kutip tidak di-escape (tertangkap saat uji coba, tidak ada data berubah). --> SELESAI, dikonfirmasi user (semua migrasi kini diparse PostgreSQL di tes) (luar GT)
- **[HIGH ALERT]** M68: catatan data menulis filter tanpa nilainya ("Industry EQ"). --> UNDERADDRESSED (ditemukan GT 2026-10-02c; rencana perbaikan di FUTURE_PLAN.md, belum dijalankan)
- **[HIGH ALERT]** M69: ambang sukses user tidak mengikat riset multi-sudut (mode 4). --> UNDERADDRESSED (ditemukan GT 2026-10-02c)
- S28: slot sesi sandbox tertahan sampai 15 menit, analysis/riset gagal "penuh". --> UNDERADDRESSED (ditemukan GT 2026-10-02c; rencana di FUTURE_PLAN.md, belum dijalankan)
- G19: dataset riset kosong tetap lolos cakupan, riset jalan di atas data kosong. --> FIXED IN CODE (penyebab terverifikasi: kunci penggabungan pesanan; lapis 1 kunci lengkap + lapis 3 gerbang kosong EMPTY_REQUEST/EMPTY_INPUT + argumen audit utuh; belum deploy/verifikasi live; lapis 2 menunggu keputusan 6)
- P26: satuan efek minimal (desimal) dibandingkan dengan hasil (persen). --> UNDERADDRESSED (ditemukan GT 2026-10-02c)
- M14: catatan berbahasa Inggris di jawaban berbahasa Indonesia. --> UNDERADDRESSED (semua)
- D08/D13: peringatan data historis; tanggal terbaru. --> UNDERADDRESSED, sebagian (g1)
- W06–W11: masalah pencarian web. --> UNDERADDRESSED (luar GT, kecuali g7 web)

## Sudah diperbaiki, hanya menunggu golden test

- P22, P23: satuan ganda / satuan dari data. --> MENUNGGU GOLDEN TEST (g1, g2)
- P24, M65: format p; CI dipasangkan dengan p yang benar. --> MENUNGGU GOLDEN TEST (g3, g4, g5.4–8)
- P25, P20, P21: pesan penolakan yang jelas. --> MENUNGGU GOLDEN TEST (semua)
- M62: satu aturan rencana. --> MENUNGGU GOLDEN TEST (g5.5, g5.7)
- M64: pertanyaan lanjutan merujuk hasil terbaru. --> MENUNGGU GOLDEN TEST (g5.2)
- G13: rencana layak tidak gagal karena ukuran data. --> MENUNGGU GOLDEN TEST (g5.7–8)
- G16: "regular" vs "Regular". --> MENUNGGU GOLDEN TEST (g1)
- M46, M48: perbaikan jawaban akhir. --> MENUNGGU GOLDEN TEST (semua)
- M47, M49, M53, M54, M55: catatan data dan rencana riset. --> MENUNGGU GOLDEN TEST (g5)
- S19: satu bentuk keluaran helper. --> MENUNGGU GOLDEN TEST (g5.7–8)
- M45: perbaikan berupa tambalan. --> MENUNGGU GOLDEN TEST, tetapi saklarnya mati: tidak teruji kecuali dinyalakan
- W17–W20: linimasa dan tanggal di jawaban web. --> MENUNGGU GOLDEN TEST, hanya teruji bila ada g7 web

## Usulan golden test berikutnya (satu putaran)

1. g1–g5 tanpa perubahan kata-kata, supaya bisa dibandingkan dengan run a dan b.
   g1 dijalankan dua kali di percakapan terpisah (`g1_foreign_net_banks_repeat`, sudah ada di `apps/orc-test-runner/suite.json`): definisi "paling likuid" dan 10 tickernya harus sama (M66/M13).
2. g6 (RESEARCH): "Apakah saham bank yang RSI 14-nya di bawah 30 naik minimal 3% dalam 10 hari berikutnya? Anggap
   berhasil kalau naik ≥ 3%." Mencakup M28, M26, P05/P08, D14, M24, S27.
3. g7 web (opsional, biaya provider web): W17–W20, W06–W08, W22.
4. Tanpa biaya model, sebelum golden test: D06, C06, D02, D05/D18/D07, C08 lewat SQL/log.
5. Dibaca dari log setiap run:
   - jumlah error kode;
   - jumlah panggilan katalog;
   - jawaban terpotong;
   - jumlah percobaan jawaban akhir;
   - detik per giliran;
   - pemakaian `aggregate`;
   - jejak audit riset;
   - sudut INVALID;
   - definisi istilah dibandingkan run a/b.
