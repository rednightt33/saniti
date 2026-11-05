# Verifikasi EXEC-TERMINAL-IND-EDIT (2026-11-05)

Tujuan (user 2026-11-05): "assign 5 sonnet 5.5 high untuk memastikan konsistensi, baik angka dan visual ... angka hasil
kalkulasi yang di display di depan, sudah benar dan tidak mislead." Merge ke `main` hanya sesudah verifikasi ini selesai.

Branch: `claude/practical-thompson-2intee`. Keputusan: `EXEC.md`, bagian EXEC-TERMINAL-IND-EDIT. Sumber review:
`FLOW_INDICATOR_REVIEW.md` (root), `SCREENER_LIBRARY.md`/`METHODOLOGY_DICTIONARY.md` (lampiran user, butir U1–U6 di EXEC).
Rumus: `verification/terminal_api/flow_indicators/FORMULAS.md`. Kode: `apps/edge-bff/terminal/src/calc/flow.ts`
(hitungan), `src/calc/explainFlowA.ts`/`explainFlowB.ts`/`explain.ts` (kartu "i"), `src/app/flowIndicators.ts`,
`src/app/indicators.ts`, `src/app/indMenu.ts` (tampilan), `src/data/flowRegistry.json` (dibangkitkan dari
`FLOW_INDICATORS_SPEC.xlsx` lewat `build_spec_workbook.py` dan `scripts/build_flow_registry.py`).

## A. Bisa diverifikasi di sesi ini (tanpa database)

| # | Butir | Cara | Hasil yang benar |
|---|---|---|---|
| A1 | Rumus setiap indikator yang berubah atau baru sama dengan keputusan user dan `FORMULAS.md` | Baca kode; hitung ulang dengan data kecil buatan sendiri (bukan tes yang ada) | Angka sama; arti sesuai kata user |
| A2 | Sisi memilih kelompok (K1/K2/R1): FL01–FL05, FL08, FL13, FL14, FL33 | Data kecil: Buy = Top-N pembeli, Sell = Top-N penjual; FL09 tidak berubah | Sesuai |
| A3 | Kartu "i" = angka chart untuk semua pilihan baru; teks kartu tidak menyesatkan (satuan, kata gross/net, beli/jual) | Jalankan kartu pada data buatan; baca teks | Angka sama; teks benar |
| A4 | Tampilan: menu (I37, I41, FL07, FL35, FL36 tidak ada), dialog parameter baru, kondisi tampil (Top N hanya saat Top-N), pesan gerbang FL46, judul legend, garis perubahan FL11/FL34 di sumbu kiri dalam poin, penanda FL27 mati bawaan, garis kedua FL29, FL32/FL33 Buy/Sell, IHSG tanpa Lot, judul tab EDGE | Build Terminal; buka di Chromium dengan data uji; tangkapan layar | Tidak ada yang salah tampil atau menyesatkan |
| A5 | Setting tersimpan lama (`ml.ind.v1`): FL11 `denom`, Rank `net_sell` di FL01–FL05/FL08, warna FL32 `value`, indikator tersembunyi tetap tergambar | Isi localStorage lalu muat Terminal | Tidak galat; perilaku sesuai migrasi |
| A6 | Backtest dan Screener tidak tersentuh | `npm run tripwire` (apps/edge-bff/screener), `pytest scripts/tests/test_registries_current.py` | Lulus |
| A7 | Spreadsheet → registry dapat dibangkitkan ulang | `python3 -I build_spec_workbook.py user_input_20261030.xlsx FLOW_INDICATORS_SPEC.xlsx` lalu `python3 scripts/build_flow_registry.py --check` | `flow registry current` |

## B. Butuh sesi baru dengan akses database (kredensial pgweb yang diperbarui user)

| # | Butir | Cara |
|---|---|---|
| B1 | Oracle independen = Terminal pada data hidup untuk semua kasus (126, termasuk 27 kasus baru) | `verification/terminal_api/flow_indicators/oracle/oracle.py` (pgq) lalu `npx vite-node ../../../verification/terminal_api/flow_indicators/oracle_compare.ts` dari `apps/edge-bff/terminal` |
| B2 | Angka contoh di `FLOW_INDICATOR_REVIEW.md` keluar dari kode | BBRI 3 Nov 2026: FL13 Top-3 = 0,04997; FL14 Top-3 = +0,006284; FL38 jendela 20 Top-3 = 0,116192; FL33 Top-3 per hari Beli +17,0%, Jual (penjual) sesuai aturan baru; FL29 C = −4,11%; FL21 asing Top-3 jendela 5: net 3,2 / gross beli 56,4 / gross jual 89,2 (persentil); FL40 asing transaksi baseline 5 = 0,21 |
| B3 | Data jumlah transaksi (`bf`/`sf`) ada di file broker yang dipakai | Cek file broker beberapa ticker dan IHSG |

## C. Belum diuji sama sekali di browser hidup

Perilaku chart user yang tersimpan sebelum rilis (C1), tampilan di ponsel (C2). Diperiksa sesudah deploy, sebelum diklaim selesai.

## Hasil putaran 1 (2026-11-05, lima agen Sonnet 5.5 effort high)

| Agen | Cakupan | Hasil |
|---|---|---|
| Angka A | FL01–FL05, FL08, FL11, FL13–FL16, FL21, FL22, FL34, FL37–FL39 | 0 angka salah: hitungan ulang independen 238.560 titik 0 selisih; regresi terhadap `main` 46.080 titik 0 selisih (indikator yang tidak diubah sama; yang diubah sama pada bawaannya) |
| Angka B | FL27, FL29, FL32, FL33, FL40–FL48 | 0 angka salah; contoh review FL33 Top-3 per hari +17,0% keluar (total ÷ total) |
| Kartu | teks dan angka kartu "i" | angka kartu = chart ±71.000 perbandingan; beberapa kalimat menyesatkan (diperbaiki) |
| Tampilan | menu, dialog, chart, IHSG di Chromium dengan data uji | menu, dialog, sumbu kiri poin, pesan K4 dan gerbang FL46 benar; format tidak berganti sesudah pilihan diubah (diperbaiki) |
| Regresi | setting tersimpan, generator, oracle, Backtest/Screener, diff | spreadsheet → registry 0 selisih; tripwire dan tes Backtest lulus; FL23 di IHSG menggambar Lot (regresi, diperbaiki, ERRORS M352); kasus oracle tanpa bawaan registry (diperbaiki) |

Perbaikan: commit `59981335`. Putaran 2: agen tampilan dan agen regresi memeriksa ulang temuan mereka sendiri.
