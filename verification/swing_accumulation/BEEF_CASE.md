# Kasus BEEF: akumulasi saat pullback (dicatat 2026-11-12)

**Status:** catatan pengamatan untuk dibandingkan dengan saham lain. **Bukan bukti umum.** BEEF dipilih karena paling cocok dengan pola
dari analisis sebelumnya (bias seleksi), satu saham, satu periode (2 Jun 2025 sampai 12 Nov 2026), dan 2026 adalah pasar yang jatuh
(IHSG −41,5% sampai 11 Nov). Dibuat atas permintaan user 2026-11-12: "Untuk finding beef bisa dicatat dulu untuk kita compare kemudian dengan saham-saham lain."

## 1. Data dan metode

| Hal | Isi |
|---|---|
| Harga | `Price_Stock_Indonesia_IDX`, harian final, 345 candle, 2025-06-02 sampai 2026-11-12 |
| Broker | `IDX_Broker_Summary`, 14.114 baris sampai 2026-11-09 (Regular 14.021, Nego 93), tipe investor Domestic dan Foreign |
| Akses | `verification/terminal_api/pgq.py` (pgweb, role `pgweb`, hanya baca), `pull_stock.py` |
| Swing | ZigZag buatan sendiri (`stock_swings.py`), bukan indikator bawaan sistem (tidak ada ZigZag di `origin/main`). Ambang pembalikan **35%** dari high atau low mentah. Pembalikan hanya dikonfirmasi pada candle **sesudah** candle ekstrem. Ambang 20% dan 25% terlalu bising untuk BEEF, 40% terlalu kasar. |
| Perhitungan per kaki | Semua dalam **lot**, papan Regular, semua tipe investor digabung per broker. Papan Nego dicatat terpisah. |
| Pembanding seleksi | Tiga penjual bersih terbesar yang dipilih dengan cara yang sama (pembeli terbesar dipilih setelah melihat jendela, jadi porsi dan persistensinya sebagian otomatis) |

**Hindsight:** pivot hanya diketahui setelah harga berbalik 35%. Jeda konfirmasi 1 sampai 43 candle (median sekitar 8). Pivot terakhir (22 Okt 2026) masih sementara.

## 2. Pivot

| # | Pivot | Harga | Dikonfirmasi pada | Jeda (candle) | Gerak dari pivot sebelumnya |
|---|---|---:|---|---:|---:|
| 1 | LOW 10 Jun 2025 | 244 | 11 Agu 2025 | 43 | |
| 2 | HIGH 3 Okt 2025 | 770 | 16 Okt 2025 | 4 | +216% |
| 3 | LOW 20 Okt 2025 | 400 | 22 Okt 2025 | 2 | −48% |
| 4 | HIGH 14 Nov 2025 | 920 | 17 Nov 2025 | 1 | +130% |
| 5 | LOW 3 Feb 2026 | 248 | 18 Feb 2026 | 9 | −73% |
| 6 | HIGH 24 Feb 2026 | 388 | 9 Mar 2026 | 9 | +56% |
| 7 | LOW 13 Mar 2026 | 222 | 23 Apr 2026 | 23 | −43% |
| 8 | HIGH 23 Apr 2026 | 302 | 5 Mei 2026 | 7 | +36% |
| 9 | LOW 8 Jun 2026 | 118 | 12 Jun 2026 | 4 | −61% |
| 10 | HIGH 20 Agu 2026 | 498 | 20 Okt 2026 | 42 | +322% |
| 11 | LOW 22 Okt 2026 | 304 | sementara | | −39% |

## 3. Broker per kaki (Regular, lot)

Asimetri = porsi lot 3 pembeli bersih terbesar dikurangi porsi lot 3 penjual bersih terbesar (poin). Persistensi = % hari pembeli terbesar net beli.
HHI dihitung atas net beli positif semua broker (HHI jika merata = 1/k).

| Kaki | Gerak | Candle | Total lot (juta) | 3 pembeli terbesar (porsi lot) | 3 penjual terbesar (porsi lot) | Asimetri | Persistensi pembeli terbesar | k pembeli net | HHI net beli | Top-1 dari net beli |
|---|---:|---:|---:|---|---|---:|---:|---:|---:|---:|
| NAIK 10 Jun → 3 Okt 2025 | +216% | 79 | 20,75 | IF, AK, ZP (2,5%) | SQ, YU, LG (2,7%) | −0,2 | 43% | 27 | 0,12 | 25% |
| TURUN 3 Okt → 20 Okt 2025 | −48% | 6 | 0,44 | BB, CP, IF (23,9%) | YP, CD, MG (29,1%) | −5,3 | 17% | 27 | 0,14 | 25% |
| NAIK 20 Okt → 14 Nov 2025 | +130% | 19 | 6,98 | LG, XL, NI (7,5%) | CP, CC, AK (5,3%) | +2,2 | 47% | 32 | 0,14 | 23% |
| TURUN 14 Nov 2025 → 3 Feb 2026 | −73% | 52 | 16,73 | XL, OD, BQ (7,3%) | CP, SQ, IF (10,5%) | −3,2 | 60% | 49 | 0,14 | 24% |
| NAIK 3 Feb → 24 Feb 2026 | +56% | 13 | 1,76 | YU, XL, XC (13,2%) | AK, CC, AO (11,2%) | +2,0 | 100% | 35 | 0,22 | 37% |
| TURUN 24 Feb → 13 Mar 2026 | −43% | 13 | 0,78 | SQ, YU, AK (13,2%) | XL, XC, YP (12,0%) | +1,3 | 85% | 24 | 0,22 | 40% |
| NAIK 13 Mar → 23 Apr 2026 | +36% | 23 | 2,01 | SQ, XL, AZ (15,8%) | ZP, YU, CC (26,1%) | −10,2 | 87% | 34 | 0,13 | 27% |
| **TURUN 23 Apr → 8 Jun 2026** | **−61%** | 26 | 6,04 | **SQ, CC, XL (29,7%)** | LG, YU, AO (22,9%) | **+6,8** | **96%** | 47 | **0,43** | **64%** |
| **NAIK 8 Jun → 20 Agu 2026** | **+322%** | 50 | 15,18 | **SQ, AK, CP (19,6%)** | AO, BQ, XL (9,5%) | **+10,1** | **100%** | 16 | **0,69** | **83%** |
| **TURUN 20 Agu → 22 Okt 2026** (sementara) | −39% | 44 | 2,05 | **SQ, CP, BQ (23,7%)** | CC, AK, ZP (12,9%) | **+10,8** | **84%** | 19 | **0,54** | **71%** |

Pada kaki 2025 dan awal 2026 tidak ada pola akumulasi satu pihak: pembeli terbesar bergantian, asimetri negatif atau kecil, HHI 0,12 sampai 0,22.

## 4. SQ (BCA Sekuritas; Domestic, Mixed)

| Periode | Net SQ (lot, Regular) | Catatan |
|---|---:|---|
| Jun–Okt 2025 (naik +216%) | −338 ribu | Penjual bersih terbesar |
| Nov 2025–Feb 2026 (turun −73%) | −310 ribu | Distribusi terbesar saat itu: CP (KB Valbury, Foreign, Retail-heavy) −1,17 juta |
| **23 Apr → 8 Jun 2026 (turun −61%)** | **+1.440.285** (beli 1.509.748, jual 69.463) | Net beli di 96% dari 26 hari; hari terbesar 13 Mei +451.410 lot (41% dari seluruh lot hari itu) = 31% dari net kaki ini; tanpa tiga hari terbesar tetap +580.852 lot |
| 8 Jun → 20 Agu 2026 (naik +322%) | +2.643.404 | Net beli di 100% hari |
| 20 Agu → 22 Okt 2026 (turun −39%) | +377.918 | Net beli di 84% hari |

Posisi bersih kumulatif Regular SQ sejak 2 Jun 2025 sekitar +4,3 juta lot (garis biru, panel bawah `BEEF_swings.png`); garis itu mulai dari 0, bukan kepemilikan sebenarnya.

**Papan Nego, 22 Mei 2026:** SQ membeli **1.497.075 lot**, CP menjual **1.949.200 lot** (CC membeli sekitar 483 ribu lot pada seluruh periode). Harga crossing SQ **250**, padahal Regular hari itu close 151 (low 137, high 161): 65% di atas harga pasar. Itu bukan pembelian di harga pasar dan perlu dibaca sebagai pengalihan posisi. Papan Nego **tidak** ikut perhitungan FL bawaan (Regular saja).

## 5. VWAP beli berjangkar (anchored) dan "underwater" pada swing low (peragaan, tiga tafsir)

VWAP beli = Σ nilai beli ÷ (100 × Σ lot beli) pada Regular, dari tanggal anchor (tidak ikut) sampai tanggal swing low. Harga pokok implisit memakai akuntansi rata-rata biaya (logika FL19). Underwater = harga ÷ VWAP − 1.

| Tafsir | Anchor → swing low | VWAP pasar | VWAP kohort top-3 | VWAP SQ | Harga pokok implisit SQ | Underwater pada close swing low (vs VWAP SQ) | pada low |
|---|---|---:|---:|---:|---:|---:|---:|
| **1.** Pullback yang mendahului rally | 23 Apr (high 302) → 8 Jun (close 132, low 118) | 171,7 | 170,3 | 163,0 | 162,9 | **−19,0%** (pasar −23,1%) | −27,6% |
| 2. Dari swing low pra-rally melewati rally | 8 Jun → 22 Okt (close 316, low 304) | 284,4 | 282,8 | 282,9 | 283,0 | **+11,7%** | +7,5% |
| 3. Dari awal pra-rally terus | 23 Apr → 22 Okt | 255,1 | 251,6 | 245,8 | 244,3 | **+28,6%** | +23,7% |

Tafsir 1 dengan Nego (22 Mei @ 250) menaikkan VWAP SQ menjadi 206,3 dan underwater close menjadi −36,0%. Hasil itu sangat bergantung pada harga crossing yang di luar pasar.
Tafsir mana yang dimaksud user **belum dikonfirmasi** pada saat dicatat; tafsir 1 yang paling sesuai dengan kalimat "VWAP dari periode pre-rally sampai swing low".

## 6. Cara membaca

- Satu saham yang dipilih karena cocok; bukan estimasi seberapa umum polanya.
- "Pihak" adalah **broker**, bukan pemilik sebenarnya. BCA Sekuritas melayani banyak nasabah.
- Pivot dan kaki dipilih dengan hindsight; deteksi dini belum diuji.
- Statistik kaki hanya Regular; Nego (crossing 22 Mei) tidak ikut dan sangat besar.
- Tidak ada klaim bahwa pola ini memprediksi apa pun. Setelah dasar 118 harga naik +322%, tetapi itu satu kejadian.

## 7. Berkas

`stock_swings.py` (swing dan statistik per kaki, grafik), `pull_stock.py` (penarikan data hanya baca untuk satu saham), `BEEF_swings.png` (grafik).
Jalankan: `SWING_DATA_DIR=<folder> python3 pull_stock.py BEEF 2025-06-01` lalu `SWING_DATA_DIR=<folder> python3 stock_swings.py BEEF 0.35`.
Statistik HHI dan konsentrasi per kaki (bagian 3) dihitung terpisah dan belum ada di `stock_swings.py`.
