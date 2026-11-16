# Studi perilaku indikator di titik ①②③: hasil (2026-11-16)

Rencana beku: `POINT_BEHAVIOUR_PLAN.md` (commit 6246ba66, sebelum data ditarik). Tujuan user: **daftar kandidat untuk ditelusuri**, bukan bukti.

## Data dan mesin
15 saham, 30 episode (`episodes_step1.csv`), harga 2023-01-02 sampai 2026-11-13, broker 2023-01-02 sampai 2026-11-09: **1,01 juta baris** (semua papan, kedua tipe investor, frekuensi terisi 100%), 8 sampai 14 detik per saham.
Postgres: memori 0,48 GB sebelum, 1,41 GB sesudah; tidak ada restart (hanya dengan izin user).
Mesin hitung: kode terminal `origin/main` di Node, bawaan registri; stochastic K dari mesin sama dengan V3 (selisih maksimum 8,5e-14). 131 deret per saham; sesudah pengecualian rencana (FL31 dan indikator inventori per broker FL23, yang namanya berbeda antar saham) **127 deret** (76 teknikal, 51 Flow), tanpa galat.

## 1. Hasil sesuai aturan beku
- **A dan B tidak dapat dinilai:** jendela pembanding yang lolos (swing low kecil, panjang sama, turun ≥ θ/3) median **8** per episode (rencana meminta ≥ 15), sehingga hanya 4 sampai 6 dari 30 episode bernilai per deret (syarat 20). Nol kandidat pada A dan B adalah **kekurangan data pembanding**, bukan bukti tidak ada pola.
- **C dinilai (27 episode bernilai):** 5 deret lolos, kalibrasi nol rata-rata 0,9, persentil ke-95 3. Deret: MACD signal, PPO signal, ROC, FL24, FL02 (sisi beli). Empat dari lima berpersentil **di bawah** 50 (22 sampai 28): indikator **tertinggal** lebih lama dari biasanya di ②, bukan mendahului. Hanya ROC (73) mendahului lebih sering dan ROC berkorelasi 0,83 dengan stochastic.

## 2. Analisis tambahan (aturan diubah sesudah melihat data)
Pembanding A/B diganti: jendela di saham yang sama dengan panjang ±15% dan gerak log harga 60% sampai 140% dari episode, di luar semua episode ±5 candle (maksimum 150, acak). Median episode bernilai 27 (B2: 20). C tidak berubah.

| Ukuran | Lolos kriteria | Rata-rata nol | P95 nol |
|---|---:|---:|---:|
| A1 | 43 | 1,3 | 5 |
| A2 | 55 | 1,7 | 6 |
| B1 | 20 | 1,5 | 5 |
| B2 | 9 | 2,8 | 9 |
| C | 5 | 0,9 | 3 |

69 deret lolos pada ≥ 1 ukuran (60 teknikal, 9 Flow); Tingkat 1 (≥ 2 ukuran pada segmen yang sama) 20, Tingkat 2 49.

### Peringatan utama: sebagian besar kandidat adalah cerminan konstruksi
- **31 dari 69** berkorelasi peringkat |ρ| ≥ 0,5 dengan stochastic K, padahal V3 menentukan titik memakai stochastic zona 30/70. Osilator yang searah dengan stochastic akan tampak ekstrem di ① ② ③ dengan sendirinya (**sirkular**). Dari Tingkat 1, 16 dari 20 termasuk kelompok ini.
- **20 dari 69** adalah deret level harga (korelasi dengan close ≥ 0,9): MA, VWAP, band, SAR, Supertrend, Donchian.
- Hanya **18 dari 69** yang tidak terikat keduanya.
- Ukuran A1 dan A2 sebagian besar mencerminkan gerak harga yang lebih dalam atau lebih kuat pada episode; ini tidak menguji "mendahului".

### Hipotesis "divergensi bullish di ①→②"
Tidak didukung. Pola divergensi relatif terhadap penurunan sebesar yang sama berarti Δ1 tinggi dan ρ1 rendah. Deret yang menonjol justru **lebih serempak dengan harga** pada penurunan pra-rally (RSI, stochastic, CMF, ADL, OBV, KVO: Δ1 persentil rendah, ρ1 persentil tinggi). Satu-satunya deret Flow dengan ρ1 rendah (persentil 15) adalah FL24, tetapi tidak lolos kriteria kelompok (searah di 67% kelompok, syarat 75%).

## 3. Kandidat yang tidak sirkular (untuk ditelusuri, bukan bukti)
Flow, persentil median per ukuran (A1, A2, B1, B2, C); ★ = lolos kriteria:
- **FL24 Top Brokers · %** (bawaan jendela 10): A1 45, A2 **73★**, B1 15, B2 51, C **25★**. Korelasi dengan stochastic 0,50.
- **FL41 Net Flow / Average Turnover**: A1 28★, A2 61, B1 52, B2 73, C 67.
- **FL36 Share · Market Value**: A2 73, B2 **78★**.
- **FL28 Average Daily Value**: A2 29★, B2 24.
- **FL02 Transaction Size · Value (beli)**: C **28★**.
Teknikal tidak terikat osilator atau harga: CMF (B1 82★), ADL (B1 87★), OBV (A1 16★), KVO signal (A1 14★, B1 73★), ADX, volatilitas (stddev, NATR, ADR, lebar Bollinger: A2 dan B2 rendah).
Deret VWAP FL17, FL42, FL43 dan FL39 adalah level atau jarak harga (korelasi 0,95 dengan close atau 0,87 dengan stochastic) dan tidak dihitung sebagai temuan Flow.

## 4. Batas
30 episode jatuh ke 9 kelompok pasar (12 episode di Mei sampai Juli 2026); jendela pembanding saling tumpang tindih; V3 butuh hindsight dan memakai stochastic; analisis tambahan dirancang sesudah melihat hasil beku; ratusan deret dan lima ukuran; lima indikator berjangkar (FL18, FL19, FL20, FL44, FL45) tidak dalam pemindaian; parameter bawaan terminal.

## 5. Berkas
`point_behaviour_results/`: `results_frozen.csv`, `results_matched_annotated.csv` (kolom `dep`: osilator-stochastic, harga-level, lain; `corrK`, `corrP`), `report_frozen.txt`, `report_matched.txt`. Skrip: `pull_episode_stocks.py`, `prepare_inputs.py`, `point_series.ts`, `point_analysis.py` (`PLACEBO=matched` untuk analisis tambahan).
