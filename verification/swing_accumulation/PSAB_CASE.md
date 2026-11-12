# Kasus PSAB: sektor Basic Materials (dicatat 2026-11-12)

**Status:** catatan pengamatan, saham kedua setelah BEEF. PSAB dipilih oleh aturan (acak benih 11 di antara 21 saham liquid Basic Materials dengan pola swing),
**bukan** karena paling cocok, jadi ia lebih mewakili saham biasa daripada BEEF. Bukan bukti umum: satu saham, 24 bulan (1 Nov 2024 sampai 12 Nov 2026).
Keputusan user 2026-11-12: Tafsir 1 untuk VWAP, kohort Top-3, sektor "Undefined" dilewati, batas liquid disetujui, sisanya "Ok" atas rekomendasi.

## 1. Data dan metode

| Hal | Isi |
|---|---|
| Harga | 482 candle harian final, 2024-11-01 sampai 2026-11-12 |
| Broker | 30.278 baris sampai 2026-11-09 (Regular 30.099, Nego 154, Tunai 25) |
| Likuiditas | ADV20 Rp33,2 miliar, ADV60 Rp43,3 miliar (close × volume, sampai 2026-11-10) |
| Ambang swing | **25%** = 5 × median rentang harian saham ini (5,2%), dibulatkan ke 5%. Aturan itu juga memberi 35% untuk BEEF (5 × 6,5% = 33%, dibulatkan 35%), sama dengan yang dipakai di `BEEF_CASE.md`. |
| Swing | ZigZag dari high dan low mentah; pembalikan dikonfirmasi hanya pada candle sesudah candle ekstrem; pivot hanya diketahui dengan hindsight (jeda 1 sampai 46 candle) |
| Perhitungan | Regular, lot, tipe investor digabung per broker; Nego dan Tunai dicatat terpisah (kecil di PSAB) |
| VWAP (Tafsir 1) | Kohort = 3 pembeli bersih terbesar (net lot) dari puncak pra-rally (tidak ikut) sampai swing low; VWAP beli = Σ nilai beli ÷ (100 × Σ lot beli) |

## 2. Pivot (17 terkonfirmasi, 1 sementara)

| # | Pivot | Harga | Dikonfirmasi | Jeda | # | Pivot | Harga | Dikonfirmasi | Jeda |
|---|---|---:|---|---:|---|---|---:|---|---:|
| 1 | H 21 Nov 2024 | 344 | 19 Des 2024 | 19 | 10 | L 18 Nov 2025 | 520 | 14 Jan 2026 | 37 |
| 2 | L 30 Jan 2025 | 206 | 4 Feb 2025 | 3 | 11 | H 21 Jan 2026 | 680 | 29 Jan 2026 | 6 |
| 3 | H 20 Feb 2025 | 318 | 13 Mar 2025 | 15 | 12 | L 3 Feb 2026 | 446 | 12 Feb 2026 | 7 |
| 4 | L 13 Mar 2025 | 232 | 17 Mar 2025 | 2 | 13 | H 3 Mar 2026 | 590 | 19 Mei 2026 | 46 |
| 5 | H 19 Mar 2025 | 336 | 24 Mar 2025 | 3 | 14 | L 22 Mei 2026 | 360 | 25 Mei 2026 | 1 |
| 6 | L 9 Apr 2025 | 220 | 11 Apr 2025 | 2 | 15 | H 3 Jun 2026 | 560 | 22 Jun 2026 | 12 |
| 7 | H 4 Jun 2025 | 590 | 19 Jun 2025 | 9 | 16 | L 1 Jul 2026 | 374 | 6 Agu 2026 | 26 |
| 8 | L 1 Agu 2025 | 396 | 28 Agu 2025 | 18 | 17 | H 27 Agu 2026 | 665 | 13 Okt 2026 | 33 |
| 9 | H 17 Okt 2025 | 755 | 22 Okt 2025 | 3 | 18 | L 2 Nov 2026 | 378 | sementara | |

## 3. Tafsir 1: VWAP kohort top-3 dari puncak pra-rally sampai swing low

| Puncak → swing low | Turun | Candle | Kohort top-3 (net lot, % dari total lot) | VWAP kohort | **Underwater** pada close (pada low) | VWAP seluruh pasar | Rally sesudahnya |
|---|---:|---:|---|---:|---:|---:|---:|
| 21 Nov 2024 → 30 Jan 2025 | −40% | 42 | ZP, YJ, XL (498.817 = 0,5%) | 274,3 | **−21,3%** (−24,9%) | 274,7 (−21,4%) | +54% / 15 candle |
| 20 Feb → 13 Mar 2025 | −27% | 15 | NI, AZ, CC (633.887 = 2,0%) | 268,9 | **−12,2%** (−13,7%) | 268,2 (−12,0%) | +45% / 4 |
| 19 Mar → 9 Apr 2025 | −35% | 8 | AK, NI, TP (566.623 = 2,7%) | 282,2 | **−15,0%** (−22,0%) | 272,4 (−11,9%) | +168% / 34 |
| 4 Jun → 1 Agu 2025 | −33% | 39 | NI, YP, XL (1.998.064 = 4,2%) | 477,8 | **−16,3%** (−17,1%) | 467,4 (−14,4%) | +91% / 53 |
| 17 Okt → 18 Nov 2025 | −31% | 22 | XL, NI, SQ (859.524 = 3,7%) | 595,4 | **−11,0%** (−12,7%) | 593,0 (−10,6%) | +31% / 41 |
| 21 Jan → 3 Feb 2026 | −34% | 9 | EP, BK, DR (389.872 = 2,7%) | 553,0 | **−7,8%** (−19,4%) | 582,4 (−12,4%) | +32% / 18 |
| 3 Mar → 22 Mei 2026 | −39% | 49 | CC, GR, LG (714.084 = 1,7%) | 510,9 | **−16,6%** (−29,5%) | 511,6 (−16,7%) | +56% / 5 |
| 3 Jun → 1 Jul 2026 | −33% | 19 | XL, NI, XC (1.064.410 = 4,1%) | 488,2 | **−20,9%** (−23,4%) | 472,8 (−18,4%) | +78% / 39 |

Underwater pada close swing low: median **−15,7%** (rentang −7,8% sampai −21,3%); pada low: median −20,7%. VWAP kohort hampir sama dengan VWAP seluruh pasar (selisih underwater maksimum sekitar 5 poin, 4,6 pada kaki 21 Jan → 3 Feb 2026).
Peringatan: setiap swing low terkonfirmasi **pasti** diikuti kenaikan ≥ ambang (itu definisi ZigZag), jadi tabel ini tidak bisa membedakan "swing low yang diikuti rally" dari yang tidak. Ini deskripsi, bukan prediktor.

## 4. Broker per kaki turun (Regular)

| Kaki turun | Total lot (juta) | 3 pembeli terbesar (porsi) | 3 penjual terbesar (porsi) | Asimetri | Hari akumulasi (FL29) | HHI net beli (merata) | Top-1 dari net beli |
|---|---:|---:|---:|---:|---:|---:|---:|
| 21 Nov 2024 → 30 Jan 2025 | 91,4 | 0,5% | 0,9% | −0,4 | 19% | 0,06 (0,02) | 13% |
| 20 Feb → 13 Mar 2025 | 31,2 | 2,0% | 1,5% | +0,5 | 40% | 0,10 (0,03) | 21% |
| 19 Mar → 9 Apr 2025 | 20,8 | 2,7% | 3,5% | −0,8 | 25% | 0,09 (0,02) | 21% |
| 4 Jun → 1 Agu 2025 | 47,4 | 4,2% | 6,6% | −2,4 | 31% | 0,10 (0,02) | 19% |
| 17 Okt → 18 Nov 2025 | 23,4 | 3,7% | 9,2% | −5,5 | 18% | 0,06 (0,02) | 12% |
| 21 Jan → 3 Feb 2026 | 14,5 | 2,7% | 3,9% | −1,2 | 33% | 0,07 (0,03) | 15% |
| 3 Mar → 22 Mei 2026 | 41,1 | 1,7% | 1,2% | +0,6 | 31% | 0,17 (0,03) | 39% |
| 3 Jun → 1 Jul 2026 | 25,8 | 4,1% | 4,3% | −0,2 | 32% | 0,15 (0,02) | 32% |

Di kedelapan kaki, porsi lot 3 pembeli terbesar hanya 0,5% sampai 4,2%, asimetri −5,5 sampai +0,6, hari akumulasi 18% sampai 40% (di bawah 50%), dan HHI net beli 0,06 sampai 0,17.
**Tidak ada akumulasi satu pihak yang terpusat saat penurunan pra-rally**, berbeda dengan BEEF.

## 5. Pola broker yang terlihat

| Broker | Perilaku |
|---|---|
| AK (UBS Sekuritas Indonesia, Foreign, Institutional-heavy) | Penjual bersih terbesar di 5 dari 9 kaki turun (−389 ribu, −1,70 juta, −1,24 juta, −397 ribu, −1,47 juta lot) dan pembeli bersih terbesar di 3 dari 8 kaki naik (+1,95 juta, +1,37 juta, +1,14 juta lot); di kaki naik +78% ia nomor dua (+1,40 juta lot) setelah BK |
| CC (Mandiri Sekuritas) | Membeli di kaki naik +168% (+1,36 juta lot), menjual di kaki turun sesudahnya (−918 ribu) |
| BK (J.P. Morgan Sekuritas Indonesia) | Pembeli terbesar di kaki naik +78% (+1,61 juta lot, bersama AK; top-3 = 78% dari net beli, HHI 0,27) |
| XL (Stockbit), YP (Mirae), NI (BNI), ZP (Maybank) | Pembeli bersih saat turun, tetapi kecil (sampai sekitar 0,7 juta lot dari 14 sampai 91 juta lot) |

Pola utama: institusi asing (AK, BK) dan CC **membeli ke dalam kenaikan dan menjual ke dalam penurunan**; broker ritel dan campuran menyerap sisi sebaliknya dengan porsi kecil.
Itu kebalikan dari hipotesis "satu pihak mengumpulkan saat turun". Pada PSAB akumulasi terpusat hanya muncul di kaki naik (HHI 0,53 pada +45% dalam 4 candle, 0,27 pada +78%).

## 6. Perbandingan dengan BEEF (kaki turun yang mendahului rally)

| Ukuran | BEEF (23 Apr → 8 Jun 2026) | PSAB (8 kaki) |
|---|---:|---|
| Porsi lot 3 pembeli terbesar | 29,7% | 0,5% sampai 4,2% |
| Asimetri pembeli−penjual (poin) | +6,8 | −5,5 sampai +0,6 |
| HHI net beli | 0,43 | 0,06 sampai 0,17 |
| Hari akumulasi (FL29) | 27% | 18% sampai 40% |
| Top-1 dari net beli | 64% | 12% sampai 39% |
| Underwater kohort pada swing low (close) | −22,5% (SQ sendiri −19,0%) | median −15,7% (−7,8% sampai −21,3%) |
| VWAP kohort vs VWAP pasar | 170,3 vs 171,7 | hampir sama |

Underwater pada swing low serupa (puluhan persen di bawah biaya kohort), tetapi **konsentrasi pembelian tidak**: BEEF terpusat pada SQ, PSAB tidak.

## 7. Cara membaca

- Dua saham tidak cukup untuk kesimpulan umum. BEEF dipilih karena cocok; PSAB dipilih acak.
- Pivot dan kaki dipilih dengan hindsight; setiap swing low terkonfirmasi diikuti rally menurut definisi.
- "Pihak" adalah broker, bukan pemilik sebenarnya.
- PSAB punya volume sangat besar (14 sampai 91 juta lot per kaki), jadi porsi kecil tetap bisa berarti ratusan ribu lot.

## 8. Berkas

`analyze_stock.py` (swing, broker per kaki, HHI, VWAP Tafsir 1, grafik), `PSAB_swings.png`, `select_stocks.py` (pemilihan satu saham per sektor).
Jalankan: `SWING_DATA_DIR=<folder> python3 pull_stock.py PSAB 2024-11-01`, lalu `SWING_DATA_DIR=<folder> python3 analyze_stock.py PSAB`.
