# Rumus Radar (dev)

<!-- explained-for: feature_07_below_percentile=159754d9ef7ace0cf3550ee42252debd, feature_07_robust_z=d1fe81a0de4be41621702bcea79466d3, feature_07_rule_version=cd41aa9aefc7dc9807be3466a74d27a6, refresh_feature_07=1073ab6d3793846a7ca8727a597d570e, refresh_feature_07_day=a032a5372e79594e9d6b38f812bd57bf -->

Dokumen ini menjelaskan **setiap rumus halaman Radar yang berjalan di dev**, dengan bahasa sederhana dan contoh angka
asli. Pakai dokumen ini sebagai rujukan saat ingin mengubah ambang, atau saat bertanya kenapa sebuah saham masuk atau
tidak masuk ke suatu filter.

- **Sumber kebenaran:** kode SQL di database dev (fungsi `refresh_feature_07` dan `refresh_feature_07_day`) dan tabel
  aturan `Feature_07_Radar_Rule`. Halaman Radar tidak menghitung apa pun; ia hanya menampilkan hasil tabel itu.
- **Angka ambang yang berlaku** ada di bagian paling bawah ("Angka yang berlaku di dev"). Bagian itu ditulis otomatis
  dari database dev, jadi selalu sama dengan yang berjalan.
- **Contoh** memakai data asli dev tanggal **9 Nov 2026**, gerbang Luas (Broad), tingkat Standar. Angka rupiah ditulis
  dalam miliar (Rp M).

## Cara dokumen ini dijaga tetap benar

1. Setiap hari (01:17 WIB) workflow GitHub `database-schema-docs.yml` membaca dev, menulis ulang bagian "Angka yang
   berlaku di dev", lalu mengecek dokumen. Kalau kode rumus di dev berubah tetapi penjelasan di atas belum diperbarui,
   workflow itu **gagal (merah)** dan menyebut fungsi mana yang berubah.
2. Setiap push ke GitHub, tes `scripts/tests/test_radar_formulas_doc.py` membandingkan sidik jari kode di dokumen
   dengan migrasi yang sudah dipasang di dev (`database/migrations/APPLIED.sha256`). Beda = merah.
3. Aturan kerja (AGENTS.md): setiap perubahan rumus atau ambang Radar wajib memperbarui dokumen ini di commit yang sama
   (`python3 scripts/radar_formulas_doc.py --write`, lalu perbarui penjelasan dan baris `explained-for` di atas).

"Sidik jari" = md5 dari isi fungsi SQL. Kalau satu huruf kode berubah, sidik jarinya berubah, sehingga perubahan tidak
bisa lolos tanpa ketahuan.

---

## 1. Gambaran besar

Setiap kali data broker baru masuk (ronde broker di stockbit-updater), Radar dihitung dalam tiga langkah:

```
Langkah 1, per saham:   ukuran harian tiap saham (aliran asing 5 sesi, peringkat terhadap riwayatnya sendiri, dst.)
                        → tabel Feature_07_Radar_Measure
Langkah 2, per tanggal: siapa yang ikut dihitung (universe G2, gerbang Luas/Likuid), lalu peringkat antar saham (S2, S3)
                        → Feature_07_Radar_Gate dan kolom penampang di Feature_07_Radar_Measure
Langkah 3, aturan:      tiap filter S1–S8 dicek syarat A, B, C, D untuk tiap tingkat (Longgar/Standar/Ketat)
                        → Feature_07_Radar_Result: hit, near (kurang satu), left (keluar)
```

Publisher lalu menulis hasilnya ke file, dan halaman Radar menampilkannya. Riwayat yang disimpan adalah 250 tanggal
hasil terakhir; pemilih tanggal di halaman menampilkan 20 tanggal terakhir. Hasil Radar tertinggal sejauh data broker
(contoh: harga sampai 13 Nov, data broker sampai 9 Nov, maka Radar sampai 9 Nov).

## 2. Istilah dasar

| Istilah | Arti |
|---|---|
| **Sesi** | Hari ketika saham itu diperdagangkan di papan mana pun (Regular, Nego, Tunai), seperti di Feature 06. Hari suspensi dilewati. Sesi tanpa transaksi Regular dihitung **0** untuk papan Regular. |
| **Papan Regular** | Semua angka Radar memakai transaksi papan Regular saja. |
| **Beli asing, jual asing, beli domestik** | Nilai rupiah per hari dari Feature 06 (`foreign_buy_1d`, `foreign_sell_1d`, `domestic_buy_1d`). |
| **Net asing harian** | beli asing − jual asing. |
| **Total beli harian** | beli asing + beli domestik (semua nilai beli di papan Regular). |
| **Jendela 5 sesi** | Hari ini dan 4 sesi sebelumnya milik saham itu. Belum genap 5 sesi = kosong (NULL). |
| **T−5** | Nilai yang sama, 5 sesi sebelumnya. Jendela hari ini dan jendela T−5 berurutan dan tidak tumpang tindih. |
| **Riwayat setahun sendiri** | 252 sesi sebelumnya milik saham itu (tidak termasuk hari ini). |
| **Kosong (NULL)** | Ukuran tidak bisa dihitung (riwayat kurang, pembagi nol). Syarat yang membaca ukuran kosong dianggap **tidak terpenuhi**; syarat lain tetap dinilai. |

### Dua cara membuat "persentil"

1. **Persentil riwayat sendiri** (dipakai S1, S6, S8): berapa persen dari 252 nilai sebelumnya yang **lebih kecil**
   dari nilai hari ini.
   - Rumus: `100 × (jumlah nilai sebelumnya yang < hari ini) ÷ 252`.
   - Butuh 252 nilai lengkap; kurang dari itu = kosong.
   - Contoh: nilai hari ini lebih besar dari 240 dari 252 nilai sebelumnya → 100 × 240 ÷ 252 = **95,2**.
   - Kode: `feature_07_below_percentile`.
2. **Peringkat antar saham** (dipakai S2, S3): berapa persen saham **lain** pada tanggal yang sama yang nilainya lebih
   kecil.
   - Rumus: `100 × (jumlah saham lain yang lebih kecil) ÷ (jumlah saham − 1)`.
   - Hanya di antara saham yang lolos gerbang. Saham dengan nilai tertinggi = 100, terendah = 0.
   - Kalau hanya ada satu saham = kosong.

## 3. Ukuran per saham (langkah 1, `refresh_feature_07`)

Dihitung untuk setiap saham universe dan setiap sesi Regular. Untuk menghitung, fungsi ini membaca 400 sesi sebelum
tanggal mulai.

### 3.1 Aliran asing 5 sesi (S1, S2, S6, S6Δ)

| Kolom | Rumus | Contoh 9 Nov |
|---|---|---|
| `foreign_net_5d` | jumlah net asing harian 5 sesi | MPMX: Rp 12,29 M |
| `total_buy_5d` | jumlah total beli harian 5 sesi | MPMX: Rp 47,21 M |
| `foreign_ratio_5d` (rasio asing) | `100 × foreign_net_5d ÷ total_buy_5d` (kosong kalau total beli 0) | MPMX: 100 × 12,29 ÷ 47,21 = **26,03%** |
| `buy_days_5d` | berapa dari 5 sesi yang net asingnya positif | MPMX: 5 |
| `foreign_net_5d_pct252` | persentil riwayat sendiri dari `foreign_net_5d` | MPMX: 100 (tertinggi setahun) |
| `foreign_net_5d_z252` | z-score biasa: `(hari ini − rata-rata 252 sebelumnya) ÷ simpangan baku 252 sebelumnya` | MPMX: 4,44 |
| `foreign_ratio_5d_prev` | rasio asing T−5 | PGJO: −28,47% |
| `foreign_ratio_5d_change` | rasio hari ini − rasio T−5 (poin) | PGJO: 42,14 − (−28,47) = **+70,61** |
| `foreign_ratio_5d_pct252` | persentil riwayat sendiri dari rasio asing | SILO: 99,6 |
| `foreign_ratio_5d_pct252_prev`, `_change` | persentil yang sama pada T−5, dan selisihnya | PGJO: 100 − 13,9 = **+86,1** |
| `foreign_net_5d_max_day`, `_max_date` | hari dengan net asing terbesar di jendela 5 sesi, dan tanggalnya | dipakai untuk tanda "One-day block" |

Catatan persentil rasio: riwayatnya hanya memakai sesi yang **punya** rasio. Sesi yang jendela 5 sesinya tanpa beli
Regular sama sekali dilewati, supaya satu minggu tanpa transaksi Regular tidak membuat peringkat kosong selama setahun.

### 3.2 Kelas broker (S7), dari Feature 03

Feature 03 membagi broker menjadi kelas institusi dan ritel menurut klien yang biasa dilayani broker itu.

| Kolom | Rumus | Contoh 9 Nov (UCID) |
|---|---|---|
| `inst_net_5d` | jumlah net beli broker institusi 5 sesi | Rp 1,035 M |
| `retail_net_5d` | jumlah net beli broker ritel 5 sesi | Rp −0,979 M |
| `fl34_5d` (FL34) | `100 × (inst_net_5d − retail_net_5d) ÷ total beli 5 sesi menurut Feature 03` | 100 × (1,035 + 0,979) ÷ 2,0 = **100,76** |
| `fl34_5d_prev` | FL34 pada T−5 | 56,13 |
| `inst_share_5d` | `100 × inst_net_5d ÷ total beli 5 sesi Feature 03` | **51,78** |
| `inst_buy_days_5d` | berapa dari 5 sesi yang net institusinya positif | — |

FL34 bisa lebih dari 100 karena ia menjumlahkan dua sisi: institusi membeli dan ritel menjual. Kalau satu sesi Regular
di jendela tidak punya baris Feature 03, semua ukuran kelas broker hari itu dibuat **kosong**. Tujuannya supaya jendela
yang bolong tidak terlihat lengkap.

### 3.3 Lonjakan satu hari (S8)

| Kolom | Rumus | Contoh 9 Nov (MPPA) |
|---|---|---|
| `foreign_net_1d`, `total_buy_1d` | net asing dan total beli hari ini | Rp 0,109 M; Rp 1,624 M |
| `adv20_prev` (ADV20) | rata-rata total beli harian **20 sesi sebelum** hari ini | Rp 0,635 M |
| `foreign_ratio_1d` (U1) | `100 × net asing hari ini ÷ total beli hari ini` | 6,70% |
| `net_vs_adv20` (U3) | `100 × net asing hari ini ÷ ADV20` | **17,14%** |
| `rz_foreign_ratio_1d`, `rz_net_vs_adv20` | z robust U1 dan U3 terhadap 252 sesi sebelumnya | 7,38 dan **50,04** |
| `net_1d_pct252` | persentil riwayat sendiri dari net asing harian | 88,1 |

**Z robust** (`feature_07_robust_z`) menilai seberapa jauh hari ini dari kebiasaan saham itu, tanpa terpengaruh beberapa
hari ekstrem:

- Rumus: `(hari ini − median) ÷ (1,4826 × MAD)`.
- MAD = median dari jarak tiap nilai ke median.
- Butuh minimal 200 nilai dalam 252 sesi sebelumnya. Kurang dari itu, atau MAD = 0, hasilnya kosong.

## 4. Siapa yang ikut dihitung, dan peringkat antar saham (langkah 2, `refresh_feature_07_day`)

### 4.1 Universe G2

Saham ikut dihitung pada suatu tanggal kalau tiga syarat ini terpenuhi semua:

- saham ada di `IDX_Stock_Universe` (waran dan right tidak ikut);
- punya minimal **5 sesi Regular dalam 16 tanggal pasar terakhir**. Tanggal dan sesi ini dibaca dari Feature 06. Tanggal
  pasar = hari dengan transaksi Regular saham mana pun;
- jendela 5 sesinya lengkap (`total_buy_5d` tidak kosong).

Contoh 9 Nov: **855 saham**. CSMI dan XSPI bertransaksi hari itu, tetapi hanya punya 2 sesi Regular dalam 16 tanggal,
jadi tidak ikut.

### 4.2 Gerbang G3: Luas (Broad) dan Likuid (Liquid)

Gerbang menyaring saham menurut **total beli 5 sesi** (`total_buy_5d`) di antara saham G2:

| Gerbang | Lolos kalau | 9 Nov |
|---|---|---|
| **Luas** | total beli 5 sesi ≥ median (P50) → separuh teratas | batas Rp 1,85 M; 428 saham |
| **Likuid** | total beli 5 sesi ≥ P80 → 20% teratas | batas Rp 17,61 M; 171 saham |

Batas dihitung ulang setiap tanggal (persentil linear, seperti numpy). Halaman menampilkan batasnya, misalnya
"≥ Rp 1.85B / 5 days".

### 4.3 Peringkat S2

- Siapa yang diperingkat: saham yang lolos gerbang, punya `foreign_net_5d` > 0, dan punya `foreign_ratio_5d_change`.
- Rumus: peringkat antar saham dari `foreign_ratio_5d_change`.
- Contoh: PGJO naik +70,61 poin, tertinggi di gerbang Luas, jadi peringkatnya **100**.

### 4.4 Konsentrasi pembeli S3, dari Feature 05

Untuk tiap saham, dihitung dari baris broker Feature 05. Rentangnya 5 sesi milik saham itu sendiri, papan Regular, semua
jenis investor dijumlahkan. Contoh di tabel memakai BBHI:

| Ukuran | Rumus | BBHI |
|---|---|---|
| `s3_net_buyers` (k) | jumlah broker dengan net beli positif | 14 |
| `s3_cr3` | net beli 3 broker terbesar ÷ total net beli semua broker yang positif | 0,996 |
| `s3_cr3_excess` | CR3 − 3 ÷ k (konsentrasi di atas "kalau rata") | 0,996 − 3/14 = **0,782** |
| `s3_intensity` | total net beli positif ÷ total beli semua broker | 0,928 |

Setelah itu, untuk tiap gerbang:

1. Hanya saham dengan **k ≥ 10** yang diperingkat (syarat G4, sama dengan syarat S3 A).
2. Saham dibagi ke **5 kelompok menurut k**, dengan batas kuintil k (P20, P40, P60, P80). Satu nilai k tidak pernah
   terbelah ke dua kelompok.
3. `s3_group_rank` = peringkat CR3 excess **di dalam kelompoknya**.
4. `s3_intensity_rank` = peringkat intensitas di antara semua saham yang diperingkat.

BBHI: kelompok 0, peringkat kelompok 98,9, peringkat intensitas 99,8.

## 5. Aturan tiap filter (langkah 3)

Setiap filter punya syarat A, B, C, (D). Angka ambangnya ada di tabel paling bawah. Kartu di halaman diurutkan menurut
"nilai urut" filter itu, dari besar ke kecil.

| Filter | Syarat | Nilai urut | Contoh hit 9 Nov (Standar, Luas) |
|---|---|---|---|
| **S1** Heavy foreign accumulation | A: net asing 5 sesi > 0. B: rasio asing ≥ 5%. C: persentil net 5 sesi ≥ P90/P95/P95; tingkat Ketat juga butuh z ≥ 2. D: net beli di ≥ 3 dari 5 hari | z-score | MPMX: 12,29 M > 0; 26,03% ≥ 5; persentil 100 ≥ 95; 5 hari ≥ 3 → **hit** |
| **S2** Strengthening foreign flow | A: net asing 5 sesi > 0. B: rasio naik dibanding T−5 (> 0). C: peringkat S2 ≥ 75/90/95 | perubahan rasio | PGJO: +70,61 > 0; peringkat 100 ≥ 90 → **hit** |
| **S3** Concentrated net buying | A: k ≥ 10. B: peringkat kelompok ≥ 70/80/90. C: peringkat intensitas ≥ 60/75/90 | rata-rata kedua peringkat | BBHI: k 14; 98,9 ≥ 80; 99,8 ≥ 75 → **hit** |
| **S6** Foreign accumulation (5D) | A: net asing 5 sesi > 0. B: rasio asing ≥ 3/5/10%. C: persentil rasio ≥ 90/95/98 | rasio asing | SILO: 50,29% ≥ 5; persentil 99,6 ≥ 95 → **hit** |
| **S6Δ** strengthening (Ratio / Rank / Both) | Syarat S6 A–C, ditambah D. Ratio: rasio naik ≥ 12/20/35 poin vs T−5. Rank: persentil rasio naik ≥ 40/65/90 poin. Both: keduanya | kenaikan rasio (Rank: kenaikan persentil) | PGJO: S6 lolos; rasio +70,61 ≥ 20 (Ratio); persentil +86,1 ≥ 65 (Rank) → **hit** keduanya |
| **S7** Institutions in, retail out | A: FL34 naik ≥ 10/20/40 poin vs T−5. B: FL34 sekarang ≥ 0. C: net institusi > 0. D: porsi institusi ≥ 2/5/10% | FL34 sekarang | UCID: 100,76 − 56,13 = +44,6 ≥ 20; ≥ 0; 1,035 M > 0; 51,78% ≥ 5 → **hit** |
| **S8** One-day foreign buying spike | A: z robust U1 **atau** U3 ≥ 3. B: U3 ≥ 10%. C: persentil net harian ≥ 95 | z robust terbesar | MPPA: z 50,04 ≥ 3; 17,14% ≥ 10; persentil 88,1 < 95 → **hit, tingkat Watch**. GDST: 97,6 ≥ 95 → **Strong** |

S8 tidak memakai tingkat Longgar/Standar/Ketat:

- Syarat A dan B wajib terpenuhi.
- Syarat C hanya menentukan tingkatnya: **Strong** kalau C terpenuhi, **Watch** kalau tidak.

Contoh "near" (kurang satu syarat): DKFT di S1 Standar.

- A, B dan D terpenuhi: net 14,91 M; rasio 33,69%; 5 hari net beli.
- C tidak: persentil 94,0, di bawah 95.

## 6. Status hasil dan tanda di kartu

| Status | Arti |
|---|---|
| **hit** | Semua syarat terpenuhi (S8: A dan B). |
| **near** | Tepat satu syarat kurang, dan saham itu **bukan** hit pada tanggal hasil sebelumnya. S8: A atau B kurang, C terpenuhi. |
| **left** | Hit pada tanggal hasil sebelumnya, tetapi tidak lagi hari ini. Alasan yang ditampilkan adalah syarat pertama yang gagal (A, B, C atau D), atau `gate` kalau saham keluar dari gerbang, atau `no_data` kalau saham tidak punya data hari ini. Saham yang keluar tapi hanya kurang satu syarat tetap dicatat sebagai **left**, bukan near. |

Tanda di kartu:

| Tanda | Arti |
|---|---|
| **New** | Hari pertama hit (`run_day` = 1). |
| **Day N** | Hit N tanggal hasil berturut-turut di filter, tingkat dan gerbang yang sama. |
| **+N** | Saham yang sama juga hit di N kolom filter lain pada pilihan yang sama. |
| **Watch** | S8 hit tanpa syarat C (lihat atas). |
| **Outlier** | Ada catatan kehati-hatian (`flag`). Isinya salah satu atau keduanya (lihat di bawah tabel). |
| **+1 vs yday** | Jumlah hit hari ini dibanding tanggal hasil sebelumnya. |
| **% di kanan atas** | Perubahan harga penutupan pada tanggal hasil dibanding sesi harga sebelumnya. Grafik kecil di kanan bawah = 20 harga penutupan terakhir. |

Dua jenis catatan Outlier:

- **One-day block:** satu hari menyumbang ≥ 80% dari net asing 5 sesi yang positif. Hanya untuk S1, S2, S6 dan S6Δ. Isi
  catatannya contoh: "Rp 3.2B of the foreign net came on 5 Nov" (teks asli dari SQL, bahasa Inggris).
- **Corporate action:** ada aksi korporasi apa pun (`idx_event_annotation`, keluarga `CORPORATE_ACTION`) dalam 5 sesi
  saham itu. Termasuk RUPS dan mulai diperdagangkannya waran (keputusan user "2 A", 14 Nov 2026).

## 7. Kalau ingin mengubah (tweak)

| Ingin mengubah | Caranya | Yang ikut berubah |
|---|---|---|
| Angka ambang (misalnya S6Δ 12/20/35) | migrasi baru yang memperbarui baris `Feature_07_Radar_Rule`, lalu hitung ulang tanggal hasil (`verification/radar/redo_days_job.py`) | hasil semua tanggal; tabel di bawah otomatis ikut |
| Rumus ukuran (misalnya jendela 5 → 10 sesi) | migrasi baru `refresh_feature_07`, isi ulang ukuran (`verification/radar/backfill_job.py`) | sidik jari berubah, jadi penjelasan di atas wajib diperbarui |
| Gerbang, peringkat, status | migrasi baru `refresh_feature_07_day`, lalu hitung ulang tanggal | sidik jari berubah, jadi penjelasan di atas wajib diperbarui |

Setiap perubahan butuh persetujuan user dan dicatat di `EXEC.md`, `DATABASE_CHANGELOG.md`, `ERRORS_AND_SOLUTIONS.md`
(kalau perbaikan), dan dokumen ini. Rujukan teknis lain:

- `FEATURE_07_RADAR.md`: kamus kolom, dibuat dari katalog;
- `verification/radar/RADAR_PAGE_SPEC.md`: spesifikasi halaman;
- `SCREENER_LIBRARY.md`: asal-usul filter dan contoh lama;
- `verification/radar/validate_radar.py`: hitung ulang independen dalam Python.

## 8. Angka yang berlaku di dev

<!-- radar-live:start -->

Versi aturan di dev: **`radar-v1`**. Ditulis oleh `scripts/radar_formulas_doc.py --write` dari tabel `Feature_07_Radar_Rule` dan `Feature_07_Radar_Filter` di dev; jangan diedit dengan tangan.

| Filter | Syarat | Bunyi syarat di halaman (Standar) | Longgar | Standar | Ketat | Status |
|---|---|---|---:|---:|---:|---|
| S1 (Heavy foreign accumulation) | A | Foreign net 5D above 0 | 0 | 0 | 0 | decided |
| S1 (Heavy foreign accumulation) | B | Foreign net ≥ 5% of buying | 5 | 5 | 5 | decided |
| S1 (Heavy foreign accumulation) | C | Above P95 of its own year | 90 | 95 | 95 / 2 | decided |
| S1 (Heavy foreign accumulation) | D | Net buying on 3 or more of 5 days | 3 | 3 | 3 | decided |
| S2 (Strengthening foreign flow) | A | Foreign net 5D above 0 | 0 | 0 | 0 | decided |
| S2 (Strengthening foreign flow) | B | Foreign ratio up vs prior 5 sessions | 0 | 0 | 0 | decided |
| S2 (Strengthening foreign flow) | C | Change in the top 10% of stocks | 75 | 90 | 95 | decided |
| S3 (Concentrated net buying) | A | At least 10 net buyers | 10 | 10 | 10 | decided |
| S3 (Concentrated net buying) | B | Concentration ≥ P80 in its group | 70 | 80 | 90 | decided |
| S3 (Concentrated net buying) | C | Intensity ≥ P75 | 60 | 75 | 90 | decided |
| S6 (Foreign accumulation (5D)) | A | Foreign net 5D above 0 | 0 | 0 | 0 | decided |
| S6 (Foreign accumulation (5D)) | B | Foreign ratio ≥ 5% | 3 | 5 | 10 | decided |
| S6 (Foreign accumulation (5D)) | C | Ratio ≥ P95 of its own year | 90 | 95 | 98 | decided |
| S6D_RATIO (Foreign accumulation, strengthening) | A | Foreign net 5D above 0 | 0 | 0 | 0 | decided |
| S6D_RATIO (Foreign accumulation, strengthening) | B | Foreign ratio ≥ 5% | 3 | 5 | 10 | decided |
| S6D_RATIO (Foreign accumulation, strengthening) | C | Ratio ≥ P95 of its own year | 90 | 95 | 98 | decided |
| S6D_RATIO (Foreign accumulation, strengthening) | D | Ratio up ≥ 20 pt vs 5 sessions ago | 12 | 20 | 35 | decided |
| S6D_RANK (Foreign accumulation, strengthening) | A | Foreign net 5D above 0 | 0 | 0 | 0 | decided |
| S6D_RANK (Foreign accumulation, strengthening) | B | Foreign ratio ≥ 5% | 3 | 5 | 10 | decided |
| S6D_RANK (Foreign accumulation, strengthening) | C | Ratio ≥ P95 of its own year | 90 | 95 | 98 | decided |
| S6D_RANK (Foreign accumulation, strengthening) | D | Rank up ≥ 65 pt vs 5 sessions ago | 40 | 65 | 90 | decided |
| S6D_BOTH (Foreign accumulation, strengthening) | A | Foreign net 5D above 0 | 0 | 0 | 0 | decided |
| S6D_BOTH (Foreign accumulation, strengthening) | B | Foreign ratio ≥ 5% | 3 | 5 | 10 | decided |
| S6D_BOTH (Foreign accumulation, strengthening) | C | Ratio ≥ P95 of its own year | 90 | 95 | 98 | decided |
| S6D_BOTH (Foreign accumulation, strengthening) | D | Ratio up ≥ 20 pt and rank up ≥ 65 pt | 12 / 40 | 20 / 65 | 35 / 90 | decided |
| S7 (Institutions in, retail out) | A | FL34 up ≥ 20 pt vs 5 sessions ago | 10 | 20 | 40 | decided |
| S7 (Institutions in, retail out) | B | FL34 now at 0 or above | 0 | 0 | 0 | decided |
| S7 (Institutions in, retail out) | C | Institutional net above 0 | 0 | 0 | 0 | decided |
| S7 (Institutions in, retail out) | D | Institutional side ≥ 5% of buying | 2 | 5 | 10 | decided |
| S8 (One-day foreign buying spike) | A | Robust z ≥ 3 on the foreign ratio or on net vs ADV20 | — | 3 | — | decided |
| S8 (One-day foreign buying spike) | B | Net ≥ 10% of the 20-day average value | — | 10 | — | decided |
| S8 (One-day foreign buying spike) | C | Net ≥ P95 of its own days | — | 95 | — | decided |

Angka kedua (`a / b`) adalah `threshold2`: S1 Ketat = persentil / z minimum; S6Δ Both = kenaikan rasio / kenaikan peringkat. S8 hanya punya satu tingkat (Strong dan Watch dibedakan oleh syarat C).

| Fungsi di dev | Sidik jari (md5 isi fungsi) |
|---|---|
| `feature_07_below_percentile` | `159754d9ef7ace0cf3550ee42252debd` |
| `feature_07_robust_z` | `d1fe81a0de4be41621702bcea79466d3` |
| `feature_07_rule_version` | `cd41aa9aefc7dc9807be3466a74d27a6` |
| `refresh_feature_07` | `1073ab6d3793846a7ca8727a597d570e` |
| `refresh_feature_07_day` | `a032a5372e79594e9d6b38f812bd57bf` |

<!-- radar-live:end -->
