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
