# Validasi 1: hasil (2026-11-12), sesuai `VALIDATION_1_FROZEN_RULE.md` (commit d803de7c, sebelum data ditarik)

**Data:** 22 saham baru (daftar di aturan beku), 1 Nov 2024 sampai 12 Nov 2026, ditarik 2026-11-12 dalam sekitar 1,5 menit, 0,47 juta baris, hanya baca lewat pgweb. Memori Postgres 1,97 GB sebelum, 1,70 GB sesudah; tidak ada restart (di bawah ambang "pembaruan besar" dan memori turun).
**Aturan tidak diubah** sesudah data dilihat. Keluaran lengkap skrip: `frozen_validation.py` (disimpan di luar repo, ringkasan di bawah).

## Verdict (7 uji yang didaftarkan)

| Uji | Hasil | Verdict |
|---|---|---|
| A-H1 (HHI ≥ 0,3): 7 kaki dari 6 saham | retrace median 1,69 vs 0,93; selisih +0,76 [−0,19; +1,60]; searah 3/6 saham | **TIDAK DISIMPULKAN** (kaki terflag < 15) |
| A-H2 (top-3 ≥ 20%): 15 kaki dari 6 saham | retrace median 0,90 vs 0,96; selisih −0,06 [−0,42; +0,53]; searah 2/6 saham | **TIDAK MENDUKUNG** |
| B FL29 sejak puncak | AUC 0,504 [0,448; 0,564] (harapan < 0,5); 10 dari 22 saham sesuai | **TIDAK MENDUKUNG** |
| B kedalaman pullback | AUC 0,582 [0,542; 0,626] (harapan > 0,5); 15 dari 22 saham sesuai | **LULUS** |
| B aturan eksploratori (kedalaman + top-3 + FL29) | 230 hari dari 20 saham; laju rally 14% vs 23%; selisih −9,0 poin [−16,1; −0,7] (arah terbalik) | **TIDAK MENDUKUNG** |
| B flag H1 pada hari | 573 hari dari 17 saham; 24% vs 23%; +1,7 [−5,2; +10,0] | **TIDAK MENDUKUNG** |
| B flag H2 pada hari | 763 hari dari 12 saham; 31% vs 21%; +9,4 [−7,7; +24,6] | **TIDAK MENDUKUNG** |

Sampel: uji A 88 kaki (rally sementara dikeluarkan); uji B 4.837 hari pullback, 1.108 (23%) diikuti rally.

## Deskriptif (bukan verdict): AUC uji B, 12 saham lama vs 22 baru

| Ciri | Lama | Baru [P5; P95] |
|---|---:|---|
| Kedalaman | 0,575 | 0,582 [0,542; 0,626] |
| Umur pullback | 0,550 | 0,556 [0,516; 0,597] |
| Underwater terhadap VWAP kohort | 0,450 | 0,418 [0,370; 0,468] |
| Porsi top-3 pembeli | 0,578 | 0,511 [0,465; 0,567] |
| Porsi top-3 penjual | 0,589 | 0,520 [0,463; 0,574] |
| HHI | 0,514 | 0,505 [0,463; 0,548] |
| FL29 sejak puncak | 0,402 | 0,504 [0,451; 0,567] |

Hanya kedalaman (dan ciri yang berkaitan dengannya: umur pullback dan underwater) bertahan arah dan besarnya. Ciri broker yang tampak di 12 saham (FL29, porsi top-3) menghilang. Empat belas ciri diuji, jadi sebagian besar kebetulan; "umur" dan "underwater" tidak didaftarkan sebelumnya.
Ketahanan (deskriptif): tanpa SINI (54 pivot, 249 hari) atau tanpa SINI dan MGLV hasil FL29 0,520 dan 0,518, kedalaman 0,580 dan 0,581. Gabungan 34 saham: FL29 0,465, kedalaman 0,579.

## Cara membaca

- Temuan broker dari 12 saham (FL29 rendah, porsi top-3 tinggi, konsentrasi) **tidak bertahan** pada 22 saham baru di periode yang sama. Satu-satunya yang bertahan adalah kedalaman penurunan, ciri harga, bukan jejak broker.
- Uji A kekurangan kaki terflag (H1: 7), jadi H1 tidak dapat dinilai; H2 punya cukup kaki dan tidak mendukung.
- Periode pasar sama dengan 12 saham pertama; hasil ini menguji saham lain, bukan rezim lain. Validasi 2 (12 saham, 2022 sampai 2024) belum dijalankan.
- Bukan sinyal beli dan bukan rekomendasi investasi.
