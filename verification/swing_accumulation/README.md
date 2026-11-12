# Swing dan akumulasi broker: satu saham sekaligus

Tujuan (user 2026-11-12): melihat apakah ada akumulasi oleh satu atau beberapa pihak saat saham pullback dari rally panjang, satu saham
sekaligus, dari data mentah harian. Ini folder kerja riset (bukan kode produk, tidak ada di `main`).

## Rencana yang dikonfirmasi user (belum dijalankan)

1. Ambil satu saham liquid per sektor (`IDX_Stock_Universe.Sector`).
2. Tarik data mentah (harga harian dan baris broker, semua papan).
3. Deteksi swing high dan swing low pada grafik harian.
4. Per kaki: broker summary, inventori broker, konsentrasi, HHI, akumulasi broker teratas (hari akumulasi), dan harga rata-rata beli (VWAP).
5. VWAP dari periode pre-rally sampai swing low, untuk melihat berapa persen harga saham pada swing low sudah underwater.
6. Bandingkan dengan BEEF (`BEEF_CASE.md`).

Pertanyaan yang masih terbuka dicatat di akhir `BEEF_CASE.md` bagian 5 dan di jawaban sesi 2026-11-12 (tafsir "pre-rally", aturan pemilihan saham, ADV, sektor "Undefined").

## Templat catatan per saham (supaya sebanding dengan BEEF)

| Bidang | Isi |
|---|---|
| Saham, sektor, ADV (20 dan 60 sesi, Rupiah) | |
| Periode, ambang swing, jumlah pivot | |
| Kaki pullback yang mendahului rally: tanggal, gerak, candle | |
| 3 pembeli dan 3 penjual bersih terbesar di kaki itu: kode, klasifikasi, net lot, porsi dari total lot | |
| Asimetri, persistensi pembeli terbesar, hari akumulasi, k, HHI net beli, porsi top-1 dan top-3 | |
| Tipe investor pembeli terbesar; papan Nego (blok, harga crossing terhadap harga pasar) | |
| VWAP beli (pasar, kohort, pembeli terbesar) dan harga pokok implisit pada swing low; underwater (%) | |
| Rally sesudahnya (gerak, candle); apakah pembeli terbesar terus mengumpulkan | |
| Catatan dan peringatan | |

## Berkas

`pull_stock.py`, `stock_swings.py`, `BEEF_CASE.md`, `BEEF_swings.png`.
