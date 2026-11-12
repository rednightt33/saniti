# Perbandingan 12 saham: pola yang mendahului rally (dicatat 2026-11-12)

**Tujuan (user 2026-11-12):** "we need to find a pattern that precedes a rally." **Status:** eksplorasi pada 12 saham (satu per sektor, ditambah BEEF sebagai kasus acuan), 24 bulan
(1 Nov 2024 sampai 12 Nov 2026), satu periode pasar yang jatuh pada 2026. Ini bahan hipotesis yang harus divalidasi pada saham dan periode lain, **bukan** hasil teruji.

## 1. Saham dan pengaturan

| Saham | Sektor | ADV20 (Rp miliar) | Ambang swing | Kaki turun pra-rally |
|---|---|---:|---:|---:|
| PSAB | Basic Materials | 33,2 | 25% | 8 |
| MAPA | Consumer Cyclicals | 15,9 | 20% | 7 |
| JPFA | Consumer Non-Cyclicals | 33,9 | 20% | 5 |
| ITMG | Energy | 55,6 | 15% | 4 |
| BFIN | Financials | 11,1 | 15% | 7 |
| MEDS | Healthcare | 2,1 | 25% | 11 |
| SMIL | Industrials | 28,2 | 25% | 9 |
| KETR | Infrastructures | 20,7 | 35% | 6 |
| PWON | Properties & Real Estate | 20,0 | 15% | 6 |
| IRSX | Technology | 10,9 | 25% | 15 |
| SMDR | Transportation & Logistic | 11,9 | 15% | 7 |
| BEEF (acuan) | Consumer Non-Cyclicals | **0,92 (di bawah lantai Rp1 miliar)** | 30% | 10 |

Total **95** kaki turun yang diikuti rally. Sebelas saham dipilih oleh aturan (acak benih 11, `select_stocks.py`); BEEF dipilih karena paling cocok dengan pola. Ambang swing = 5 × median rentang harian saham itu, dibulatkan ke 5%
(15% sampai 50%). Dengan aturan 24 bulan BEEF mendapat 30%, bukan 35% seperti di `BEEF_CASE.md` (17 bulan).

## 2. Kaki turun pra-rally (semua 95 digabung)

Median per kaki: turun −34,5% (P25 −42,9%, P75 −28,1%), lama 20 candle (P25 9,5, P75 37), porsi lot 3 pembeli terbesar 9,6%, asimetri −1,1 poin, hari akumulasi (FL29) 38,5%, porsi top-1 dari net beli 27%,
underwater pada close swing low terhadap VWAP kohort top-3 **−13,5%** (P25 −18,8%, P75 −8,3%; pada low −18,4%), rally sesudahnya +41,7% dalam 15 candle.

| Ciri | Jumlah kaki | Porsi |
|---|---:|---:|
| Tanda tangan "akumulasi terpusat" (porsi lot top-3 ≥ 10%, asimetri ≥ +5, hari akumulasi ≥ 50%) | 5 dari 95 (BEEF, IRSX, ITMG, JPFA, PWON) | 5% |
| Porsi lot top-3 ≥ 10% | 46 | 48% |
| Asimetri ≥ +5 poin | 9 | 9% |
| Hari akumulasi ≥ 50% | 25 | 26% |
| HHI net beli ≥ 0,3 | 13 | 14% |
| Underwater ≤ −10% pada swing low | | 65% |
| Underwater ≤ −20% pada swing low | | 23% |

Korelasi peringkat (interval 90% dengan bootstrap per saham) antara ciri kaki turun dan rally sesudahnya: porsi lot, asimetri, HHI, top-1: semuanya mendekati 0 (|ρ| ≤ 0,07, interval memuat 0).
Hubungan yang tidak memuat 0: lama penurunan dengan besar rally +0,33 [+0,22; +0,45] dan dengan kecepatan rally −0,36 [−0,47; −0,18]; besar penurunan dengan kecepatan −0,36 [−0,44; −0,19];
underwater dengan besar rally −0,27 [−0,42; −0,15]; hari akumulasi dengan besar rally −0,23 [−0,43; −0,04].
Catatan: semua kaki ini diikuti rally menurut definisi ZigZag, jadi bagian ini **tidak** punya contoh negatif.

## 3. Dekat dasar vs lebih awal di kaki yang sama (48 kaki ≥ 20 candle)

10 candle terakhir sampai swing low (A) dibanding 10 candle sebelumnya (B), selisih median A−B (interval 90% bootstrap per saham): porsi lot top-3 +0,20 poin [−0,21; +4,52]; asimetri −0,01 [−1,59; +1,39];
hari akumulasi 0,0 poin [−10; 0]; HHI −0,00; porsi top-1 −0,72 [−2,58; +4,89]; volume +10,7% [−8,8; +28,0]. Tidak ada perubahan jejak broker yang konsisten menjelang dasar.

## 4. Uji per hari tanpa hindsight (`realtime_lift.py`)

**Desain:** pada hari t hanya dengan data sampai t. Keadaan pullback: harga ≤ puncak 60 candle × (1 − θ/2) dan ≥ 5 candle sejak puncak (θ = ambang swing saham itu).
**Label:** high tertinggi 20 candle berikutnya ≥ close(t) × (1 + θ). **Ciri** (Regular, lot): kedalaman, umur, underwater terhadap VWAP kohort top-3 sejak puncak, jejak broker sejak puncak dan 10 candle terakhir,
rasio volume, pantulan sejauh ini. Setiap ciri diubah menjadi persentil di dalam saham itu; interval 90% dengan bootstrap per **saham**.
**Sampel:** 2.820 hari pullback, 735 (26%) diikuti rally; laju dasar per saham 1% (ITMG) sampai 51% (MEDS).

| Ciri (hanya data sampai t) | AUC | P5–P95 | Saham dengan AUC > 0,5 | Laju rally sepertiga bawah → atas | Atas − bawah (poin; interval) |
|---|---:|---|---:|---|---|
| Kedalaman pullback | **0,57** | 0,53–0,62 | 9/12 | 22,1% → 32,4% | +10,3 (+2,2; +17,5) |
| Porsi lot top-3 pembeli bersih | **0,58** | 0,52–0,64 | 9/12 | 21,9% → 34,7% | +12,8 (+3,6; +23,7) |
| Porsi lot top-3 penjual bersih | **0,59** | 0,51–0,67 | 10/12 | 19,7% → 34,4% | +14,7 (+3,2; +27,2) |
| **Hari akumulasi (FL29) sejak puncak** | **0,40** | 0,34–0,45 | **2/12** | 33,1% → 16,8% | **−16,3 (−26,5; −7,4)** |
| Hari akumulasi, 10 candle terakhir | 0,42 | 0,37–0,48 | 2/12 | 33,2% → 17,6% | −15,7 (−25,1; −7,7) |
| Underwater terhadap VWAP kohort | 0,45 | 0,40–0,51 | 4/12 | 31,7% → 24,5% | −7,3 (−15,1; +1,8) |
| Asimetri pembeli−penjual | 0,49 | 0,42–0,55 | 4/12 | 28,4% → 27,3% | −1,1 (−11,8; +8,2) |
| HHI net beli, kohort 10 candle terakhir, rasio volume, pantulan, return 5 hari | 0,46 sampai 0,53 | memuat 0,50 | | | |

**Bacaan:** hari pullback yang kemudian diikuti rally cenderung (a) lebih dalam, (b) punya **kedua** sisi besar (porsi lot 3 pembeli dan 3 penjual bersih sama-sama tinggi), dan (c) **lebih sedikit hari ketika pembeli terbesar
mengalahkan penjual terbesar** (FL29 rendah). Asimetri (pembeli dikurangi penjual) sendiri tidak membedakan. Jadi polanya lebih mirip **penyerapan jual besar oleh pembeli besar** (peralihan posisi) dengan tekanan jual yang dominan
di sebagian besar hari, bukan akumulasi satu arah yang konsisten.

**Aturan sederhana (dipilih SESUDAH melihat tabel, jadi hipotesis):** kedalaman di atas median saham, porsi lot top-3 pembeli di sepertiga atas, hari akumulasi di sepertiga bawah.
131 hari (5%); laju rally **50% vs 25%** pada hari lain (dasar 26%); selisih +25 poin, interval 90% [+9,0; +38,2]. Per saham (9 saham dengan ≥ 10 hari aturan dan ≥ 10 hari rally):
lebih tinggi pada 7 dari 9 (BEEF 59% vs 30%, KETR 73% vs 30%, MEDS 95% vs 47%, PWON 53% vs 13%, SMDR 80% vs 21%, JPFA 17% vs 9%, PSAB 31% vs 26%); lebih rendah pada MAPA (10% vs 20%) dan SMIL (8% vs 31%).

**Ketahanan:** tanpa BEEF: AUC FL29 0,41 [0,35; 0,47], kedalaman 0,59, aturan 48% vs 25%. Tanpa MEDS dan IRSX (laju dasar tinggi): FL29 0,39 [0,31; 0,46], aturan 41% vs 21%. Tanpa ITMG: tidak berubah.
Porsi lot pembeli dan penjual lebih lemah: batas bawah interval 0,49 sampai 0,50 pada sebagian variasi.

## 5. Peringatan

- 12 saham, satu periode (termasuk pasar jatuh 2026); hari-hari dalam satu episode saling tumpang tindih, jadi sampel efektif jauh di bawah 2.820 hari.
- Empat belas ciri diuji; beberapa akan tampak bermakna karena kebetulan. Yang bertahan di semua variasi: FL29 (arah terbalik) dan kedalaman.
- Ambang θ dihitung dari seluruh 24 bulan (sedikit melihat ke depan untuk skala), dan aturan sederhana dipilih setelah melihat hasil (dalam-sampel, optimistis).
- Hanya papan Regular; "pihak" adalah broker, bukan pemilik; BEEF di bawah lantai likuiditas.
- Ini hubungan statistik, bukan sinyal beli: belum ada biaya, titik masuk, atau uji pada data baru.

## 6. Berkas

`aggregate_swings.py` (bagian 2 dan 3), `realtime_lift.py` (bagian 4), laporan per saham di `reports/`, skrip penarikan dan analisis di folder ini.
Jalankan setelah `pull_stock.py` dan `analyze_stock.py` untuk tiap saham: `SWING_DATA_DIR=<folder> python3 aggregate_swings.py <saham...>` dan `python3 realtime_lift.py <saham...>`.
