# Swing dan akumulasi broker: satu saham sekaligus

Tujuan (user 2026-11-12): melihat apakah ada akumulasi oleh satu atau beberapa pihak saat saham pullback dari rally panjang, satu saham
sekaligus, dari data mentah harian. Ini folder kerja riset (bukan kode produk, tidak ada di `main`).

## Keputusan user (2026-11-12)

| Hal | Keputusan |
|---|---|
| VWAP | **Tafsir 1**: dari puncak pra-rally (anchor, tidak ikut) sampai swing low pada akhir pullback yang mendahului rally; underwater = harga ÷ VWAP − 1 |
| Kohort VWAP | **Top 3** pembeli bersih terbesar (net lot) pada jendela itu |
| Sektor | `IDX_Stock_Universe.Sector`; "Undefined" dilewati |
| Cukup liquid | Lantai Screener (close ≥ 50, ADV20 ≥ Rp1 miliar) dan ADV60 di atas median sektor (di antara yang lolos lantai); ADV = close × volume |
| Pemilihan | Acak benih tetap 11 di antara saham liquid yang punya sedikitnya satu pola swing HIGH → LOW → HIGH (BEEF dikecualikan sebagai kasus acuan) |
| Periode | 24 bulan (mulai 2024-11-01) |
| Ambang swing | 5 × median rentang harian saham itu, dibulatkan ke 5%, dibatasi 15% sampai 50% (BEEF: 30% pada basis 24 bulan studi lintas saham; `BEEF_CASE.md` memakai 35% pada 17 bulan) |

## Satu saham per sektor (seleksi dengan data sampai 2026-11-10; `select_stocks.py`)

| Sektor | Saham | Status |
|---|---|---|
| Basic Materials | PSAB | selesai: `PSAB_CASE.md` |
| Consumer Cyclicals | MAPA | selesai (`reports/MAPA_report.txt`) |
| Consumer Non-Cyclicals | JPFA (BEEF = kasus acuan terpisah: `BEEF_CASE.md`) | selesai (`reports/JPFA_report.txt`) |
| Energy | ITMG | selesai (`reports/ITMG_report.txt`) |
| Financials | BFIN | selesai (`reports/BFIN_report.txt`) |
| Healthcare | MEDS | selesai (`reports/MEDS_report.txt`) |
| Industrials | SMIL | selesai (`reports/SMIL_report.txt`) |
| Infrastructures | KETR | selesai (`reports/KETR_report.txt`) |
| Properties & Real Estate | PWON | selesai (`reports/PWON_report.txt`) |
| Technology | IRSX | selesai (`reports/IRSX_report.txt`) |
| Transportation & Logistic | SMDR | selesai (`reports/SMDR_report.txt`) |

## Hasil lintas saham

Lihat `COMPARISON.md` (12 saham, 95 kaki turun pra-rally, uji per hari tanpa hindsight). Tujuan user 2026-11-12: menemukan pola yang mendahului rally.

## Alur per saham

1. `SWING_DATA_DIR=<folder> python3 pull_stock.py TICKER 2024-11-01` (hanya baca, satu saham).
2. `SWING_DATA_DIR=<folder> python3 analyze_stock.py TICKER` (pivot, broker per kaki, HHI, VWAP Tafsir 1, grafik).
3. Catat di `<TICKER>_CASE.md` dan bandingkan dengan `BEEF_CASE.md` dan saham sebelumnya.

## Templat catatan per saham (supaya sebanding)

| Bidang | Isi |
|---|---|
| Saham, sektor, ADV (20 dan 60 sesi, Rupiah) | |
| Periode, ambang swing, jumlah pivot | |
| Per kaki turun yang mendahului rally: tanggal, gerak, candle | |
| 3 pembeli dan 3 penjual bersih terbesar: kode, klasifikasi, net lot, porsi dari total lot | |
| Asimetri, persistensi pembeli terbesar, hari akumulasi (FL29), jumlah broker net beli, HHI net beli, porsi top-1 dan top-3 | |
| Tipe investor pembeli terbesar; papan Nego dan Tunai (blok, harga crossing terhadap harga pasar) | |
| VWAP beli kohort top-3 dan underwater (%) pada swing low | |
| Rally sesudahnya; apakah pembeli terbesar terus mengumpulkan | |
| Catatan dan peringatan | |

## Berkas

`pull_stock.py`, `select_stocks.py`, `analyze_stock.py`, `aggregate_swings.py`, `realtime_lift.py`, `stock_swings.py` (versi awal untuk BEEF), `COMPARISON.md`, `reports/` (laporan per saham), `BEEF_CASE.md`, `BEEF_swings.png`, `PSAB_CASE.md`, `PSAB_swings.png`.
