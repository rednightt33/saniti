# Masalah yang belum selesai: status (2026-10-02, diperbarui 2026-10-05 sore)

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

- P27: hasil uji dari kode AI berbentuk pecahan tetapi berlabel persen; putusan dibandingkan dengan ambang 100× terlalu besar. --> DIPERBAIKI (sandbox `567c7a48`: satuan dicek dengan hitung ulang), menunggu golden test akhir (g5.6)
- M71: kelompok tanpa kolom di data (BUMN) ditebak AI; BBCA dimasukkan ke BUMN. --> KEPUTUSAN USER (keputusan 6) + sebagian: daftar ketikan AI kini tampil sebagai "Pilihan AI" dan catatan pikiran dikirim ulang dalam satu jawaban (orc `06d6be4a`); fakta web ringan di Fase 4 (g5.5–6)
- M72: baris tanpa nilai indikator (RSI awal) dimasukkan ke kelompok pembanding. --> DIPERBAIKI (sandbox `567c7a48`), menunggu golden test akhir (g6_revise.1)
- **[HIGH ALERT]** M66: pertanyaan sama, definisi "hari crash" / "bank BUMN" berbeda. --> UNDERADDRESSED + KEPUTUSAN USER (kamus istilah); terulang di GT 2026-10-02c (g1 vs g1_repeat: definisi "paling likuid" berbeda)
- **[HIGH ALERT]** M63: penjelasan menghitung ulang dengan cakupan berbeda dari tabelnya. --> TERBUKTI (GT `ma-golden-20261002c`): g7 tetap di papan Nego, g5.3 menjelaskan dari tabel asal; celah baru M68 (nilai filter hilang dari catatan) UNDERADDRESSED
- **[HIGH ALERT]** M28: definisi sukses dari user diganti aturan bawaan. --> TERBUKTI untuk rencana hipotesis (GT `ma-golden-20261002c`); jalur riset multi-sudut (mode 4) belum mengikat ambang: M69 UNDERADDRESSED
- **[HIGH ALERT]** M26: SUPPORTED walau efek di bawah batas yang disebut user. --> DIPUTUSKAN user 2026-10-05: pilihan B (SUPPORTED hanya bila efek mencapai batas user; di bawahnya PARTIALLY_SUPPORTED); DIBANGUN 2026-10-05 (orc `c1f7119`: vonis diterima, alasan berbahasa Indonesia, "didukung" penuh ditolak, gerbang `PLAN_MIN_EFFECT`; sandbox: aturan vonis di kedua jalur, hanya untuk estimasi berskala satuan hasil); diuji item `m26_min_effect` golden test `ma-qa-20261005b`
- **[HIGH ALERT]** M29: rencana menyebut 6 bank, eksekusi 48. --> TERBUKTI (GT `ma-golden-20261002c`): gerbang menolak angka rencana tanpa sumber
- M25: temuan eksperimen pertama hilang dari metadata. --> TERBUKTI (GT `ma-golden-20261002c`)
- S13: sudut riset INVALID karena rekaman ganda. --> TIDAK MUNCUL LAGI (GT `ma-golden-20261002c`) (0 dari 25 sudut; jalur penolakan host belum terpicu)
- S27: kalimat salah menyebut jumlah "memenuhi syarat". --> TERBUKTI (GT `ma-golden-20261002c`)
- M24: INCONCLUSIVE terdengar seperti "ditolak". --> UNDERADDRESSED (g4, g6)
- G11/D12, G08: saham keliru dikeluarkan; nilai terakhir saham tak likuid hilang. --> UNDERADDRESSED (g1, g2)
- D14: RSI/EMA berbeda dari nilai sejarah penuh. --> KEPUTUSAN USER (g6)
- C06: tanggal akhir data salah disebut. --> MITIGATED di dev 2026-10-03 (rentang "LATEST" + catatan katalog bisa tertinggal; cron dua kali sehari TEMPORARY tetap live); penyegaran setelah muat (1a-permanen) menunggu `main`; belum diverifikasi live
- D02: sektor bernilai "0". --> SELESAI di dev ("Undefined", migrasi 20261003_001, dibaca balik) (luar GT)
- **[HIGH ALERT]** S23: angka hasil kode AI tidak diperiksa ulang backend. --> UNDERADDRESSED (g1–g4 dibandingkan hitungan independen)
- **[HIGH ALERT]** M13: "saham terbaik" memakai definisi pilihan AI. --> UNDERADDRESSED, sebagian (AI wajib menyebut definisinya) (g1)

- M75: jawaban lambat 4–36 menit karena hampir semua panggilan jatuh ke penyedia lambat (Morph). --> KEPUTUSAN USER 2026-10-04: rute penyedia **as is** (O1 tidak dikerjakan); dikurangi lewat router (M79). **Terulang 2026-10-05** (Sail Research, 22 token/detik; p1 904 detik). KEPUTUSAN USER 2026-10-05: preferensi kecepatan minimal 50 token/detik (`AI_PROVIDER_MIN_THROUGHPUT=50`, dev), menunggu pengukuran di golden test
- M76: pertanyaan lanjutan kehilangan riwayat setelah jawaban panjang. --> DIPERBAIKI (O2, `AI_MAX_HISTORY_TOKENS` 150.000, live); belum diuji live dengan pesan lanjutan khusus
- M77: ekspor tidak tersedia di langkah baca. --> DIPERBAIKI (O3, sifat alat; live); TERBUKTI live 2026-10-05 (s1.4 dan s3.4: ekspor di langkah baca, 13 dan 55 detik)
- P28: penolakan angka karena angka dari layar print / alarm palsu; putaran bukti tanpa temuan. --> D dan bukti DIPERBAIKI (P28-D, O4; live, terlihat di q4); A/B (angka dari print, hitung di kepala) gerbang tetap
- P29: "data terbaru berakhir 31 Agustus" padahal harga sampai 2 Okt (g9.3). --> UNDERADDRESSED (dugaan, cek log reasoning dulu)
- P30: AI menolak membuat trade setup. --> DITUNDA user

## 2b. Baru 2026-10-04 (suite `ma-qa-20261004a`, router)

- M78: penyedia berhenti di tengah jawaban → giliran kosong → AI dipaksa menjawab tanpa alat → LIMITED (q2, q3). --> DIPERBAIKI dan TERBUKTI live 2026-10-05 (percobaan ulang terpicu di r_store_expiry, giliran selesai)
- M79: pertanyaan fakta/sapaan menjalani mode 4 penuh (g13 23 menit). --> DIPERBAIKI dan TERBUKTI live: router pesan pertama (g13 44 detik, sapaan 23 detik), penahan riset tanpa angka data
- M80: hasil riset multi-sudut tidak bisa diekspor (bukan tabel); ekspor dirouting CONTINUE. --> DIPERBAIKI dan TERBUKTI live 2026-10-05: tabel `research_findings_table` diekspor ke Excel (s3.4); benchmark router lanjutan 30/30
- Tes kedaluwarsa R-STORE (S29). --> TERBUKTI live 2026-10-05: masa simpan sandbox 1 jam, tabel dipulihkan setelah kedaluwarsa dengan angka sama, lalu diekspor; masa simpan kembali 24 jam

## 2c. Baru 2026-10-05 (stress test router `ma-qa-20261005a`, 5 percakapan + suite b)

- M81: topik baru di tengah percakapan menjalankan mode 4 penuh. --> DIPERBAIKI dan TERBUKTI live (pertanyaan data setelah sapaan: satu langkah analisis, 42–52 detik)
- M82: horizon yang diubah user ("jadi 10 hari") dikembalikan gerbang ke 5 hari. --> DIPERBAIKI (router membaca perubahan horizon terstruktur, benchmark 14/14), live; uji golden test berikutnya
- P31: AI menyebut "tidak ada kapasitas pencarian web" padahal alat fakta web ada. --> daftar kemampuan DIPERBAIKI (live); kalimat prompt DIPERBAIKI 2026-10-05 (audit A1: kalimat ditulis dari alat yang aktif); uji live menunggu golden test yang ditunda
- P34: pertanyaan fakta yang datanya ada di database (sektor BBCA) dijawab dari web; daftar saham sektor energi LIMITED. --> DIPERBAIKI 2026-10-05 (pilihan A): alat `lookup_reference` di semua langkah baca termasuk FACT, alat web ditolak untuk atribut yang ada di tabel referensi sampai tabelnya dibaca, angka web tidak boleh masuk perhitungan; live di dev, uji smoke Governor lulus; perilaku AI menunggu golden test yang ditunda
- P32: jumlah bar uji (1.693) ikut menghitung bar pemanasan (70). --> DIPERBAIKI lapis 1–4 (hitungan berlabel, in_period, backtest, buku metode v5), live; uji golden test berikutnya
- P33: uji Pine rusak no. 5 dan 9b. --> no. 5 DIPERBAIKI (z-score aktivitas tanpa hari ini, dari katalog), live; no. 9b koreksi kunci jawaban tes
- M14 (bagian s4.1): pesan "BBRI" saja dijawab klarifikasi berbahasa Inggris. --> DIPERBAIKI 2026-10-05 lewat prompt putaran 2 K2 (orc `c1f7119`, live); uji `lang_ticker_only` di golden test `ma-qa-20261005b`. Bagian utama M14 (catatan backend berbahasa Inggris) ada di bagian 4

## 3. Tidak keluar jawaban (buntu)

- G23: gerbang bukti meminta get_evidence di run yang tidak punya alat itu (gerbang dan alatnya DIHAPUS 2026-10-06, EXEC-E; uji `ma-qa-20261006e` tanpa gerbang EVIDENCE), sehingga model loop (g9.2 gagal di 60 iterasi; 29% panggilan model di run ini terbuang). --> DIPERBAIKI di kode dan live di dev (orc `26ee862e`), menunggu golden test akhir (g9.1–2, g5, g6, g7, g11)
- M74: router membaca pertanyaan lanjutan sebagai revisi usulan riset (g7.3 "bandingkan dengan 2024"). --> DIPERBAIKI sebagian (benchmark: salah baca 14/60 → 8/60 di MiMo; sisa "Coba event study" dibaca setuju), menunggu golden test akhir (g7, g5)
- M73: mode 4 menjalankan riset untuk setiap pertanyaan baru. --> SESUAI DESAIN (tujuan 1 mode 4); ditutup 2026-10-04
- G22: database bersama kewalahan saat 5 worker paralel; rencana dan riwayat percakapan gagal disimpan/dibaca, Governor 503. --> DIPERBAIKI di kode (Governor `a23aa316`: satu timeout per pesanan, antrean N=2; orc `fba3574e`: simpan coba ulang sekali), menunggu golden test akhir 5 worker; database terpisah (G22-6) menunggu keputusan user (GT `ma-golden-20261003e` g4.2, g5.1, g2)
- R30: kredit akun OpenRouter habis (HTTP 402) / batas kunci tercapai (403). --> batas kunci dinaikkan user ke USD 30; cek 2026-10-05: sisa kunci USD 2,99, sisa kredit akun USD 5,35 (cukup untuk satu golden test). Terulang setiap kali sisa menipis: KEPUTUSAN USER (tambah kredit/batas)
- R31: ubah variabel tanpa `--skip-deploys` men-deploy ulang dari `main`. --> SELESAI 2026-10-05: cabang sudah masuk `main`, semua service deploy dari `main` (luar GT)
- R33: GitHub Action harian "Track Railway and database state" gagal 29/29 karena secret `RAILWAY_TOKEN` kosong; `DATABASE_SCHEMA.md` tertinggal. --> KEPUTUSAN USER: isi secret repo `RAILWAY_TOKEN` (luar GT)
- P05/P08: jawaban benar dipaksa LIMITATION karena angka parameter. --> DIPERBAIKI (orc `06d6be4a`: ambang/persentil ketikan AI tampil sebagai "Pilihan AI", tidak ditolak), menunggu golden test akhir (g3, g6)
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
- **[HIGH ALERT]** M69: ambang sukses user tidak mengikat riset multi-sudut (mode 4). --> tahap 1 DEPLOYED dev 2026-10-03 (mode 4 boleh rencana hipotesis dengan success_rule; horizon user dikunci; gerbang membaca kata-kata user saja, M70); belum diverifikasi live; tahap 2 di Fase E
- S28: slot sesi sandbox tertahan sampai 15 menit, analysis/riset gagal "penuh". --> DEPLOYED dev 2026-10-03 (ruang kerja dilepas di akhir setiap jawaban, satu sesi aktif per jawaban, antrean 60 detik); belum diverifikasi live
- S29 / R-STORE: tabel hasil hilang setelah 24 jam, kode dan batas tanggal data tidak tersimpan. --> DEPLOYED dev 2026-10-03 (tabel, kode dan tanggal data disimpan selama percakapan hidup; dimuat ulang ke ruang kerja baru; batas tanggal lama dipakai kecuali user minta data terbaru, dan jawaban menyebut tanggalnya); belum diverifikasi live
- G19: dataset riset kosong tetap lolos cakupan, riset jalan di atas data kosong. --> DEPLOYED dev 2026-10-03 (penyebab terverifikasi: kunci penggabungan pesanan; lapis 1 kunci lengkap + lapis 3 gerbang kosong EMPTY_REQUEST/EMPTY_INPUT + argumen audit utuh); belum diverifikasi live; lapis 2 menunggu keputusan 6
- P26: satuan efek minimal (desimal) dibandingkan dengan hasil (persen). --> DEPLOYED dev 2026-10-03 (ambang membawa satuan, alat bantu memakai satuan rencana, harness memeriksa satuan); belum diverifikasi live
- Fase D (alat AI dan user): statistik kolom, buka hasil/kode lama, get_lineage, export_result, query_metric, get_evidence. --> DEPLOYED dev 2026-10-03 (D0–D6, termasuk get_evidence dan evidence[]); get_evidence DIHAPUS 2026-10-06 atas keputusan user (EXEC-E, P39), evidence[] tetap berisi daftar DIRUJUK; belum diverifikasi live. Enam metrik query_metric berstatus INFERRED sampai user meninjau definisinya; nilai transaksi ditunda (D-b)
- M14 (bagian utama): catatan backend berbahasa Inggris di jawaban berbahasa Indonesia. --> UNDERADDRESSED (semua); bagian s4.1 lihat bagian 2
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
