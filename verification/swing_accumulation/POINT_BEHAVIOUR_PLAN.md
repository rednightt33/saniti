# Studi perilaku indikator antara titik ①, ② dan ③: rencana analisis (ditulis 2026-11-16 sebelum data broker ditarik dan sebelum hasil dihitung)

**Tujuan (user 2026-11-16):** "cari potential candidate to explore further." Hasilnya **daftar kandidat**, bukan bukti. Tidak ada klaim signifikansi; setiap kandidat dilaporkan bersama jumlah kandidat yang diharapkan muncul karena kebetulan (kalibrasi nol).
**Persetujuan user:** pola yang dicari (divergensi di ①→② dan mendahului di ②, ②→③ sebagai konfirmasi), pembanding jendela turun di saham yang sama, daftar indikator (53 teknikal + Flow), dan penarikan broker 2023 sampai sekarang untuk 15 saham: "Ok" 2026-11-16.

## 1. Episode dan data

| Hal | Isi |
|---|---|
| Episode | 30 episode dari `episodes_step1.csv` (15 saham paling liquid, masing-masing 2; V3; syarat SMA50 pada pivot). Tidak diubah |
| Segmen | S1 = ① → ② (penurunan), S2 = ② → ③ (rally), dalam candle harian. Titik adalah tanggal pivot V3 |
| Kelompok pasar | Titik ② berurutan yang berjarak ≤ 21 hari kalender masuk satu kelompok (9 kelompok pada 30 episode). Hasil dilaporkan per episode **dan** per kelompok |
| Harga | `Price_Stock_Indonesia_IDX` harian final, 2023-01-02 sampai terakhir (warm-up untuk indikator berjendela panjang) |
| Broker | `IDX_Broker_Summary`, semua papan dan kedua tipe investor, termasuk frekuensi transaksi, 2023-01-02 sampai terakhir; klasifikasi broker dari `IDX_Broker_Profile` |
| Mesin hitung | Kode terminal `origin/main` (`calc/indicators.ts`, `calc/flow.ts`), diekspor ke folder sementara dan dijalankan di Node; parameter = bawaan registri terminal |

## 2. Indikator

- **Teknikal:** 53 indikator di `F` (`indicators.ts`), setiap keluaran (garis) menjadi satu deret.
- **Flow:** FL01 sampai FL50 dengan parameter bawaan registri, setiap keluaran menjadi satu deret.
- **Dikeluarkan:** FL31 (butuh data insider), FL51 dan FL52 (tampilan, bukan deret), dan lima indikator berjangkar FL18, FL19, FL20, FL44, FL45 (butuh tanggal jangkar; jarak ke anchored VWAP sudah dilaporkan terpisah). Indikator yang menghasilkan galat atau deret kosong dicatat dan dikeluarkan, bukan diperbaiki.
- Deret dipakai hanya bila ≥ 90% candle pada jendela yang dinilai bernilai.

## 3. Tiga ukuran (opsi A, B, C pilihan user)

Untuk setiap deret x dan setiap episode:

| Ukuran | Statistik per episode | Pembanding (placebo) |
|---|---|---|
| **A1** | Δ1 = x(②) − x(①) | Jendela sepanjang S1 di saham yang sama yang **berakhir di swing low kecil** (low terendah dalam ±5 candle, bukan V3 dan berjarak > 10 candle dari pivot V3 mana pun) dan harganya turun ≥ θ/3 selama jendela itu |
| **A2** | Δ2 = x(③) − x(②) | Jendela sepanjang S2 yang **dimulai di swing low kecil** dan harganya naik ≥ θ/3 |
| **B1, B2** | Spearman antara x dan close sepanjang S1 (B1) atau S2 (B2); hanya bila segmen ≥ 10 candle | Jendela pembanding yang sama dengan A1 atau A2 |
| **C** | Lag k\* ∈ [−10, +10] yang memaksimalkan \|korelasi peringkat\| antara perubahan harian x pada hari t dan perubahan harian close pada hari t+k, pada jendela ②−20 sampai ②+20; **k\* > 0 berarti indikator mendahului harga** | Jendela ±20 yang berpusat di swing low kecil yang sama |

θ = ambang swing saham itu (kolom `th` di `episodes_step1.csv`). Pembanding diminta ≥ 15 jendela per saham, kalau kurang episode itu NA untuk ukuran tersebut. Jendela pembanding yang tumpang tindih dengan [①, ③] episode itu dibuang.

**Persentil:** pct = 100 × (jumlah nilai pembanding < nilai episode + 0,5 × jumlah yang sama) ÷ jumlah pembanding. 50 berarti nilai episode biasa untuk saham itu; di atas 50 berarti lebih tinggi dari biasanya.

## 4. Kriteria kandidat (tetap)

Untuk setiap deret dan ukuran, dengan ≥ 20 episode bernilai:

1. median persentil ≤ 30 atau ≥ 70;
2. rata-rata persentil per kelompok pasar berada di sisi 50 yang sama dengan median pada ≥ 75% kelompok;
3. paruh awal (titik ② di 2024–2025) dan paruh akhir (2026) sama-sama bermedian di sisi yang sama dan berjarak ≥ 10 dari 50.

Deret yang lolos pada ≥ 2 ukuran berbeda di segmen yang sama (A1 dan B1, atau A1 dan C, atau B1 dan C) berstatus **Tingkat 1**, sisanya **Tingkat 2**.

## 5. Kalibrasi nol (wajib dilaporkan)

300 kali: untuk setiap episode ganti nilai episode dengan satu jendela pembanding acak dari sahamnya (persentil dihitung terhadap jendela pembanding lainnya), jalankan seluruh kriteria di atas, dan catat berapa deret yang lolos per ukuran. Laporkan rata-rata dan persentil ke-95 jumlah lolos pada data nol, dan **selisih jumlah kandidat nyata terhadap rata-rata nol**. Tidak ada koreksi FDR yang diklaim; kalibrasi inilah yang menggantikannya.

## 6. Batas

- 30 episode jatuh ke 9 kelompok pasar (12 episode di satu kelompok, Mei sampai Juli 2026); sampel efektif kecil.
- V3 butuh hindsight; kandidat tidak otomatis menjadi sinyal waktu nyata. Mesin hitung terminal tidak diubah.
- Ratusan deret dan lima ukuran: sebagian lolos karena kebetulan; lihat kalibrasi nol.
- Tidak ada uji lanjutan pada data baru dalam studi ini; kandidat yang terpilih perlu aturan beku baru pada kaki V3 lain atau saham lain.
- Bukan sinyal beli dan bukan rekomendasi investasi.
