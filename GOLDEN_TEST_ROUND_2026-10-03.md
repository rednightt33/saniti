# Golden test ronde 2026-10-03 (sementara)

Rencana: `ROUND_PLAN_2026-10-03_FASE_D.md` Bagian 2. Dijalankan atas perintah user.

## Putaran 1: `ma-golden-20261003d` (suite kecil, 3 worker, 2026-10-03 22:31 UTC)

Runner `5e690200`; orc `f2b1cfbc`, sandbox `5a7e839a`, Governor `0fa3f146`. Mode bawaan dev: mode 4.

| Item:giliran | Status / detik / USD | Iterasi | Kejedot (ditolak / perbaikan gerbang / pesanan ulang / penuh) | Bukti | Catatan |
|---|---|---|---|---|---|
| g1:1 | COMPLETED / 108 / 0,050 | 14 | 1 / 1 / 0 / 0 | 7 TERCEK, 1 TIDAK_BISA_DICEK | Baseline 02c: 244 detik, USD 0,041 |
| g8_metric:1 | COMPLETED / 239 / 0,041 | 14 | 0 / 2 / 0 / 0 | 4 TIDAK_BISA_DICEK (G20) | Metrik resmi dipakai; papan tidak dicampur; data sampai 31-08-2026 disebut |
| g7:1 | COMPLETED / 248 / 0,057 | 23 | 4 / 3 / 0 / 0 | 1 TERCEK, 6 TIDAK_BISA_DICEK (G20), 1 TIDAK COCOK (G21) | Baseline 02c g7:1: rencana, 436 detik |
| g7:2–3 | FAILED / 0 | 0 | — | — | `PROVIDER_REJECTED`: batas kunci OpenRouter (R30) |
| g6:1 | COMPLETED / 175 / 0,080 | 28 | 2 / 2 / 0 / 0 | 6 TERCEK | Aturan user dipakai: naik ≥ 3%, 10 hari, ambang 1 poin persen; langkah rencana riset gagal (R30) |
| g6:2 | FAILED / 0 | 0 | — | — | R30 |

**Terbukti:**
- 0 `SESSION_CAPACITY_EXCEEDED` dengan 3 jawaban paralel (S28).
- 0 pesanan data ulang.
- Tidak ada angka tanpa sumber (provenance kosong).
- Bukti tingkat 2 (tabel dasar) TERCEK di semua item.
- Kesegaran data disebut.

**Masalah baru:**
- **G20:** bukti tingkat 1 membaca angka Governor sebagai kosong.
- **G21:** jumlah hari tidak bisa dinyatakan dalam resep.

Keduanya sudah diperbaiki (orc `4b764004`, migrasi 20261004_001).

**R30:** batas total kunci OpenRouter habis. Sisa golden test menunggu batas dinaikkan.

## Putaran 2: `ma-golden-20261003e` (sisa suite penuh, 27 giliran)

**Belum dijalankan (R30).** Isinya:
- g9_resume dan g11_plan_expiry, dengan masa simpan sandbox 1 jam dan jeda 66 menit;
- g1_repeat, g2, g3, g4, g5 (9 giliran), g6_revise dan g7 asli.

Suite ini sudah di-commit di `apps/orc-test-runner/suite.json`.
