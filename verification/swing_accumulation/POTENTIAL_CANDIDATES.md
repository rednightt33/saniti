# Daftar kandidat (potential) penyaring pra-rally

**Dicatat 2026-11-12 atas permintaan user:** "catat 2 ukuran yang kamu buat ini menjadi potential 1. Dihitung dari point zigzag yang dicount menggunakan V3. We'll gather some more."
Ini daftar yang akan bertambah. **Status "potential" artinya kandidat untuk dikumpulkan dan diuji, bukan ukuran yang sudah terbukti.** Folder riset ini ada di cabang kerja, bukan di `main`.

## Potential 1: dua ukuran konsentrasi pembelian pada kaki turun V3

### Cara membangunnya

| Hal | Isi |
|---|---|
| Titik swing | **V3** (`swing_lib.py`): ZigZag harga dengan ambang θ = 5 × median rentang harian saham itu (dibulatkan 5%, 15% sampai 50%), dikonfirmasi hanya pada candle sesudah candle ekstrem, dipertahankan bila stochastic 14,3,3 slow (definisi terminal) berada ≤ 30 (low) atau ≥ 70 (high) dalam ±5 candle dari titik itu; titik sejenis berurutan digabung ke yang lebih ekstrem |
| Kaki | Swing high ① → swing low ② yang diikuti swing high ③ (kaki "pra-rally") |
| Jendela | Candle **sesudah ①** sampai candle **②** (① tidak ikut, ② ikut). Net lot tiap broker dijumlahkan **sekali untuk seluruh jendela** |
| Data | Papan Regular, lot, semua tipe investor digabung per broker |
| Kode | `v3_legs.py` (fungsi `feats`), contoh hitungan BEEF F→G di bawah |

### Dua ukuran

| # | Ukuran | Rumus | Ambang yang diuji (usulan, dipilih sesudah melihat 12 saham, belum final) |
|---|---|---|---|
| **P1-a** | **HHI net beli** | Σ (net_i ÷ jumlah net beli positif)² atas semua broker net beli di jendela | ≥ 0,3 |
| **P1-b** | **Porsi top-3 pembeli bersih terhadap total lot beli bruto** | (jumlah net lot 3 pembeli bersih terbesar) ÷ (total lot beli bruto semua broker di jendela) × 100 | ≥ 20% |

### Padanan di terminal (diperiksa pada kode `origin/main`, 2026-11-12)

| Ukuran | Padanan | Catatan |
|---|---|---|
| P1-a | **FL38** dengan `unit = lot`, `boards = Regular`, `window` = panjang kaki | Korelasi peringkat 0,99 dengan FL38 versi nilai Regular; 0,97 dengan bawaan terminal (nilai, jendela 20). Flag ≥ 0,3: 15 kaki (versi saya) vs 14 (FL38 Regular), irisan 14 |
| P1-b | **Bukan FL16.** Secara matematis = FL16 (top-3, `unit = lot`, `even` mati) × FL47 ÷ 100 | FL16 memakai penyebut net beli positif seluruh broker (median 53% pada 143 kaki, minimum 28%); ukuran ini median 9,4%. **FL16 ≥ 20% hampir selalu terpenuhi, jadi jangan disamakan.** FL47 di terminal berbasis nilai Rp |

### Contoh hitungan (BEEF kaki F→G, 25 Feb sampai 8 Jun 2026, 62 hari bursa)

Total lot beli bruto 8.830.348; 44 broker net beli dengan jumlah net beli positif 2.612.008 lot. Top-3 SQ + XL + CC = 1.653.352 + 185.501 + 143.602 = 1.982.455 lot. **P1-b = 22,45%** (gaya FL16: 75,9%). SQ saja p = 0,633, p² = 0,401. **P1-a = 0,413** (merata = 0,023).

### Bukti sampai sekarang (semuanya hindsight pada V3)

| Sumber | Hasil |
|---|---|
| 12 saham, 50 kaki (eksploratori, ambang dipilih sesudah melihat) | Kaki "terkonsentrasi" (HHI ≥ 0,3 atau top-3 ≥ 20%): 9 kaki; retrace median 1,21 vs 0,89; retrace ≥ 1 pada 7 dari 9 vs 17 dari 41. Hanya 2 kaki memenuhi keduanya; korelasi peringkat HHI dan top-3 antar kaki +0,38, jadi keduanya bukan hal yang sama |
| **Validasi 1** (22 saham baru, 88 kaki, aturan beku `VALIDATION_1_FROZEN_RULE.md`, hasil `VALIDATION_1_RESULT.md`) | **P1-a:** 7 kaki terflag dari 6 saham; retrace median 1,69 vs 0,93, selisih +0,76 [−0,19; +1,60]; **tidak disimpulkan** (kurang dari 15 kaki). **P1-b:** 15 kaki dari 6 saham; 0,90 vs 0,96, selisih −0,06 [−0,42; +0,53], searah di 2 dari 6 saham; **tidak mendukung** |
| Cakupan pada kaki (22 saham baru) | P1-a 8% kaki, P1-b 17%, salah satu 20%, keduanya 4 dari 88 |
| Pada hari pullback tanpa hindsight (jendela sejak puncak 60 candle, bukan ① ke ②) | P1-a: 12% hari, laju rally 24,4% vs dasar 22,9% (lift 1,07×), cakupan 13% hari rally; **tidak mendukung**. P1-b: 16% hari, 30,8% vs 22,9% (lift 1,34×), cakupan 21%, di atas dasar saham itu pada 4 dari 9 saham; **tidak mendukung** (interval memuat 0) |

### Batas dan yang belum diketahui

- **Belum terbukti.** Hasil di atas belum cukup untuk menyatakan ukuran ini mendahului rally, tetapi juga belum cukup untuk mengesampingkannya sebagai **penyaring kandidat** yang jarang menyala (tidak semua rally punya ciri ini; ukuran yang tepat adalah presisi dan cakupan, bukan AUC).
- Ambang 0,3 dan 20% dipilih sesudah melihat 12 saham, jadi optimistis di sana.
- V3 butuh hindsight (±5 candle dan jeda konfirmasi): kohort top-3 dipilih dengan mengetahui akhir kaki; bukan sinyal waktu nyata.
- Setiap kaki V3 pasti diikuti rally menurut definisi: uji pada kaki hanya menjelaskan **besar** rally, bukan **apakah** rally terjadi.
- Periode 22 saham baru sama dengan 12 saham pertama (pasar jatuh 2026); rezim lain belum diuji.
- Hanya papan Regular; Nego dan Tunai (misalnya kohort BEEF kaki R→S membeli 1,5 juta lot di Nego) tidak terhitung; tipe investor digabung.

### Langkah berikutnya yang diusulkan (belum disetujui)

1. Hitung ulang dengan definisi terminal (FL16 top-3 satuan lot dan FL38 lot Regular, dua flag terpisah) agar bisa direproduksi di layar.
2. Uji sebagai penyaring kandidat (presisi, cakupan, lift per saham) dengan aturan beku baru yang ditulis sebelum data dilihat.
3. Uji nilai tambah di atas kedalaman pullback, papan Nego, dan tipe investor.

## Potential 2, 3, ... (diisi kemudian)

Templat per kandidat: nama dan rumus; titik swing dan jendela; padanan di terminal (kode FL dan parameter); contoh hitungan nyata; bukti sampai sekarang (sumber, jumlah kaki atau hari, saham, interval); batas; langkah berikutnya.
