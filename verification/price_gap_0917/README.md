# PRICE-GAP-0917 — bukti read-only

Rencana: `PLAN.md`, bagian PRICE-GAP-0917.

## Perbandingan skala TradingView vs harga tersimpan (2026-10-30, `scale_scan.py`)

Hanya membaca: TradingView lewat klien milik `apps/idx-price-cron/price_update.py` (`adjustment: splits`, sama dengan
run harian), SQL lewat pgweb (role read-only). Tidak ada yang ditulis.

- 843 saham universe (bukan indeks) yang punya harga tersimpan 2026-09-01..2026-10-30.
- **815 sama skala:** close tersimpan 09-16 dan 09-21 sama persis dengan TradingView, begitu juga setiap hari tersimpan
  lain di jendela itu.
- **22 tanpa tetangga tersimpan** pada 09-16 atau 09-21 (saham yang hari itu tidak punya candle). Setiap hari tersimpan
  yang sama tanggalnya tetap sama persis dengan TradingView, jadi skalanya sama.
- **6 beda skala:** AHAP, BUVA, ENRG, FORU, PBSA, VKTR. Untuk masing-masing:
  - rasio close tersimpan ÷ TradingView sama di setiap hari sampai tepat sehari sebelum ex-date aksi korporasinya;
  - candle 09-17/18 TradingView yang dikali rasio itu jatuh di rupiah bulat (dan di fraksi harga BEI).

  | Saham | Aksi (ex-date) | Rasio | 09-17 O/H/L/C setelah dikali rasio | 09-18 O/H/L/C setelah dikali rasio |
  |---|---|---|---|---|
  | AHAP | rights 7:5 (10-09) | 1,219401 | 112 / 120 / 111 / 115 | 117 / 117 / 103 / 104 |
  | BUVA | rights 4:1 (10-14) | 1,130269 | 700 / 715 / 660 / 685 | 690 / 700 / 660 / 665 |
  | ENRG | rights 2:1 (10-05) | 1,354234 | 1.350 / 1.380 / 1.260 / 1.310 | 1.310 / 1.325 / 1.250 / 1.305 |
  | FORU | rights 100:46.235 (09-22) | 19,504203 | 4.000 / 4.060 / 3.540 / 3.540 | 3.340 / 3.350 / 3.010 / 3.010 |
  | PBSA | split 1:2 (10-14) | 2 | 750 / 755 / 730 / 740 | 745 / 745 / 710 / 725 |
  | VKTR | rights 35:12 (10-07) | 1,331920 | 730 / 775 / 725 / 770 | 770 / 800 / 740 / 785 |

- BAJA (rights 09-28) dan BRNA (rights 10-09) **sama skala**: TradingView tidak menyesuaikan keduanya. Daftar aksi
  korporasi saja tidak cukup untuk menebak saham mana yang beda skala; perbandingan dengan data tersimpan yang menentukan.
- Candle TradingView yang tersedia untuk saham sama skala: 825 pada 09-17 dan 823 pada 09-18.
- Temuan sampingan: PBSA 2026-10-08, TradingView sekarang memberi close seperempat dari nilai tersimpan (rasio 4,
  hari lain 2). Dicatat sebagai M313; tidak disentuh rencana ini.

## Ganti 1 Sep–terbaru dengan TradingView sekarang? (2026-10-30, `ohlcv_scan.py`)

- 837 saham selain enam di atas, 2026-08-03..10-30: 50.333 hari-saham dibandingkan pada open, high, low, close dan
  volume. Hanya 1 nilai berbeda: volume GOTO 2026-10-12, tersimpan 28.057.826.200 dan TradingView 28.057.826.000.
  TradingView tidak punya hari lain yang tidak ada di database, kecuali 09-17/18.
- Enam saham, seluruh riwayat tersimpan: rasio tersimpan ÷ TradingView tetap dari baris pertama sampai sehari sebelum
  ex-date. Rinciannya:
  - AHAP 1,219401 (2018-01-03..2026-10-08);
  - BUVA 1,130269 (2018-01-02..2026-10-13);
  - ENRG 1,354234 (2018-01-02..2026-10-02);
  - FORU 19,504203 (2018-01-02..2026-09-21);
  - PBSA 2 (2018-01-24..2026-10-13, kecuali 10-08 = M313);
  - VKTR 1,33192 (2023-06-19..2026-10-06).

  Sesudah ex-date, rasionya 1. Jadi mengganti hanya mulai 1 Sep memindahkan patahan skala ke 1 Sep.

## Rumus sama dengan baris tersimpan? (2026-10-30)

- `f01_repro.py`: SELECT di dalam `refresh_feature_01_stock_daily` live untuk 60 saham. Hasilnya 89.369 baris, 27
  kolom, 0 beda.
- `f04_repro.py`: `features/feature04/engine.py` dengan TA-Lib 0.6.8 dan numpy 2.3.5 untuk 30 saham, 48.212 baris,
  2.458.812 nilai.
  - Indikator, swing dan `close`: 0 beda di atas 1e-10.
  - 52 flag candle lama berbeda (M314), semuanya ≤ 2026-06-10.

## Seluruh riwayat semua saham vs TradingView (2026-10-31, `full_scan.py`)

- 844 saham, 1.331.073 baris tersimpan. Setiap baris ada di TradingView.
- 829 saham: close sama di setiap hari sejak 2018. Riwayat bulk load sebelum 2026-09-12 sudah disesuaikan, misalnya
  AGRO 2020-12-02 close 591,928975.
- 6 saham (AHAP, BUVA, ENRG, FORU, PBSA, VKTR): rasio tetap dari baris pertama sampai sehari sebelum ex-date.
- 9 saham: selisih ≤ 0,0004 % hanya pada 2020-12-02. Ada 24 hari-saham dengan close atau volume berbeda pada tanggal
  itu, ditambah volume GOTO 2026-10-12 (200 lembar).
- Hari di TradingView yang tidak ada di database: hanya 2026-09-17 (830 saham) dan 2026-09-18 (829 saham).
