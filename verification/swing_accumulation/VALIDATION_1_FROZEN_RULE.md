# Validasi 1: aturan beku (ditulis 2026-11-12 sebelum data baru ditarik)

**Tujuan:** menguji pada 22 saham baru apakah temuan eksploratori dari 12 saham bertahan. Dokumen ini dan `frozen_validation.py` di-commit **sebelum** data 22 saham ditarik; keduanya tidak diubah sesudah hasil dilihat. Bila ada yang perlu diubah, perubahan dicatat sebagai perubahan beserta alasannya dan hasilnya dilaporkan dengan label "aturan diubah sesudah melihat data".

**Persetujuan user 2026-11-12:** "ok", atas usulan AI: (1) uji A (V3) ditambah uji B (per hari), (2) daftar 22 saham di bawah, (3) aturan beku ini (H1 dan H2 diuji terpisah, minimal 15 kaki), (4) jalankan Validasi 1 dulu, Validasi 2 (12 saham, 2022 sampai 2024) sesudah hasil 1 dilihat.

## 1. Data

| Hal | Isi |
|---|---|
| Saham (22) | SMGR, TINS, MAPI, MGLV, JARR, MYOR, INDY, PKPK, BMRI, BNGA, MMIX, RSCH, UNTR, SINI, MTEL, PGEO, SMRA, TRIN, EMTK, UVCR, HATM, MITI |
| Pemilihan | `select_stocks.py 2026-11-10 2 <12 saham lama>`: dua per sektor, acak benih 11 di antara kandidat (lantai Screener, ADV60 di atas median sektor, ada pola H→L→H), tanpa 12 saham sebelumnya |
| Periode | 2024-11-01 sampai data terakhir (candle harian final; broker sampai 2026-11-09) |
| Papan | Regular, lot, semua tipe investor digabung per broker |
| Bukan independen | Periode sama dengan 12 saham pertama (pasar jatuh 2026): ini saham lain, bukan rezim lain |

## 2. Swing V3 (persis yang disetujui user 2026-11-12)

ZigZag harga pada high/low mentah dengan ambang θ = 5 × median rentang harian saham itu, dibulatkan ke 5%, dibatasi 15% sampai 50% (rumus yang sama dengan 12 saham pertama), pembalikan dikonfirmasi hanya pada candle sesudah candle ekstrem; titik dipertahankan hanya bila stochastic 14,3,3 slow (definisi terminal: raw %K 14, K = SMA3, D = SMA3) berada ≤ 30 (swing low) atau ≥ 70 (swing high) pada sedikitnya satu candle dalam ±5 candle dari titik itu; dua titik sejenis berurutan digabung ke yang lebih ekstrem. Kode: `swing_lib.py` (`stochastic`, `zigzag`, `combine`), tidak diubah.

## 3. Uji A: kaki turun V3 (hindsight)

- **Kaki:** swing high H(k) → swing low L(k+1) yang diikuti swing high H(k+2). Jendela = candle sesudah puncak sampai candle swing low. Kaki dengan rally sementara (H(k+2) belum terkonfirmasi) **dikeluarkan**.
- **Ciri:** HHI net beli = Σ (porsi net beli broker)² di antara broker net beli; porsi top-3 = net lot 3 pembeli bersih terbesar ÷ total lot beli bruto jendela itu (`v3_legs.py`).
- **Hasil:** retrace = ln(③ ÷ ②) ÷ ln(① ÷ ②), ① puncak lama, ② dasar, ③ puncak baru.
- **H1:** kaki dengan HHI ≥ 0,3 mempunyai retrace median lebih besar daripada kaki lain.
- **H2:** kaki dengan porsi top-3 ≥ 20% mempunyai retrace median lebih besar daripada kaki lain.
- H1 dan H2 diuji **terpisah, tanpa "atau"**. Hanya dua hipotesis utama ini yang boleh disebut "lulus".
- **LULUS** bila: kaki terflag ≥ 15 dari ≥ 6 saham; interval 90% (bootstrap per saham, 2.000 ulangan, benih 2026) untuk selisih median retrace (terflag − lainnya) berbatas bawah > 0; selisih positif di ≥ 60% saham yang bisa dibandingkan (punya kaki terflag dan tidak terflag), dengan sedikitnya 4 saham seperti itu.
- **TIDAK DISIMPULKAN** bila syarat jumlah di atas tidak terpenuhi.
- **TIDAK MENDUKUNG** bila syarat jumlah terpenuhi tetapi syarat LULUS tidak.
- Pendamping tanpa verdict: korelasi peringkat HHI, porsi top-3, dan FL29 dengan retrace (dengan interval bootstrap per saham).

## 4. Uji B: per hari tanpa hindsight (`realtime_lift.py`, definisi tidak diubah)

- **Keadaan pullback pada hari t:** close ≤ puncak close 60 candle × (1 − θ/2) dan ≥ 5 candle sejak puncak. **Label:** high tertinggi 20 candle berikutnya ≥ close(t) × (1 + θ).
- **Ciri** (data sampai t; persentil di dalam saham): FL29 sejak puncak, kedalaman, porsi top-3 sejak puncak, HHI sejak puncak.
- **FL29:** AUC < 0,5 diharapkan; LULUS bila batas atas interval 90% < 0,5 dan ≥ 60% saham berAUC < 0,5.
- **Kedalaman:** AUC > 0,5 diharapkan; LULUS bila batas bawah interval 90% > 0,5 dan ≥ 60% saham berAUC > 0,5.
- **Aturan eksploratori dari 12 saham** (kedalaman ≥ median saham, porsi top-3 sejak puncak di sepertiga atas, FL29 sejak puncak di sepertiga bawah): selisih laju rally (aturan − lainnya) dengan interval 90% bootstrap per saham; syarat jumlah ≥ 50 hari terflag dari ≥ 6 saham; LULUS bila batas bawah > 0 dan searah di ≥ 60% saham yang punya ≥ 10 hari terflag dan ≥ 10 hari rally (minimal 4 saham).
- **Flag H1 dan H2 pada hari** (HHI sejak puncak ≥ 0,3; porsi top-3 sejak puncak ≥ 20%): kriteria sama dengan aturan di atas, syarat jumlah ≥ 100 hari terflag dari ≥ 6 saham.

## 5. Yang tidak dikerjakan dan peringatan

- **Daya uji rendah di uji A.** Pada 12 saham pertama hanya sekitar 10% kaki memenuhi tiap flag. Dengan sekitar 90 sampai 100 kaki, tiap flag kira-kira 10 kaki, jadi hasil "TIDAK DISIMPULKAN" sangat mungkin dan sah. Syarat 15 kaki **tidak** diturunkan agar hasil menjadi "lulus".
- Verdict hanya dari 22 saham baru. Menggabung dengan 12 saham lama hanya deskriptif, karena 12 saham itu dipakai membentuk hipotesis.
- Setiap kaki V3 pasti diikuti rally menurut definisi: uji A hanya menjelaskan **besar** rally, bukan **apakah** rally terjadi. Uji B yang punya contoh negatif.
- V3 membutuhkan hindsight (±5 candle dan jeda konfirmasi); bukan sinyal waktu nyata.
- Hari-hari dalam satu episode saling tumpang tindih di uji B; sampel efektif jauh di bawah jumlah hari.
- Ambang θ per saham dihitung dari seluruh 24 bulan (sedikit melihat ke depan untuk skala).
- Semua ciri lain (misalnya top-1, asimetri, underwater) hanya deskriptif; tidak ada klaim.
- Bukan sinyal beli dan bukan rekomendasi investasi.

## 6. Berkas

`frozen_validation.py` (verdict), `v3_legs.py`, `v3_pooled.py`, `realtime_lift.py`, `swing_lib.py`, `analyze_stock.py` (ambang θ), `select_stocks.py`, `pull_stock.py`.
