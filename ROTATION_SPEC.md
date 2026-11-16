# Rotation Map EDGE: spesifikasi halaman rotasi dan panel Analisis Sektor

**Status:** masuk to-do list (`PLAN.md` ROTATION-MAP, user 2026-11-14). Spesifikasi usulan. Bagian yang sudah diputuskan user ditandai dengan tanggal dan kata-katanya; sisanya
usulan. Belum dibangun. Disusun 2026-11-13.
**Sumber angka contoh:** database dev, dibaca dengan role `pgweb` (read-only), as-of **9 Nov 2026**, papan Regular,
gerbang "Luas" (426 saham dengan sektor, di luar "Undefined"). Satu tanggal; kestabilan belum diuji.
**Bukan rekomendasi investasi.** Peta menggambarkan keadaan, bukan ramalan.

---

## 0. Keputusan user

| Tanggal | Keputusan | Kata user |
|---|---|---|
| 2026-11-13 | Rotation Map adalah halaman sendiri, terpisah dari halaman library screener dan bukan bagian dari Market Overview | "Benar, tapi bukan untuk market overview. Ini akan menjadi page sendiri di luar screener yang tadi kita buat." |
| 2026-11-13 | Rekomendasi peta disetujui: lensa Harga, Breadth, Arus asing; kelompok sektor (industri sebagai pilihan); ekor 20 hari / 5 hari / sekarang; drill-down ke saham; matriks konfirmasi | "Saya setuju dengan rekomendasi sektor." |
| 2026-11-13 | Pembanding bawaan: rata-rata pasar sama bobot; IHSG sebagai pilihan | "Oke, untuk opsi kamu pembanding bawaan bisa digunakan." |
| 2026-11-13 | Ada panel Analisis Sektor saat sektor diklik: saham yang outperform dan underperform, line chart mulai dari 0, heatmap | "ketika kita klik sektor, maka akan ada banyak informasi ... line chart dengan indeks 0 ... heat map yang goalnya adalah supaya kita bisa melihat alpha atau sektor atau saham" |
| 2026-11-13 | Nilai sektor dan pasar memakai **median** anggotanya | "ok median" |
| 2026-11-13 | "Alpha" = **selisih return** (excess return) | "A - mau tahu excess return" |
| 2026-11-14 | Sumbu lensa Arus asing memakai **nol mutlak** (0 = asing beli dan jual seimbang), tidak dipusatkan ke pasar | "1. Mutlak 0" |
| 2026-11-14 | Pembanding excess return di panel Analisis Sektor: **dua pilihan yang bisa di-toggle** (median sektor, median pasar) | "2. 2 options bisa di toggle" |
| 2026-11-14 | Periode bawaan line chart P2: **60D** | "3. Ok" |
| 2026-11-14 | Leaderboard dan Rotation Map masuk to-do list; spesifikasi detail ini menjadi acuan saat halaman dibuat | "Ini semua dimasukkan ke to-do list ya" |
| 2026-11-13 | Heatmap mengikuti rekomendasi: saham × periode sebagai tampilan utama, heatmap harian 20 sesi sebagai tab opsional. Bacaan AI atas "ok rekomendasi kamu" | "ok rekomendasi kamu" |

---

## 1. Aturan bersama

| # | Aturan | Isi |
|---|---|---|
| B1 | Tanggal | Satu tanggal as-of untuk seluruh halaman: tanggal terakhir yang dimiliki semua sumber yang dipakai lensa aktif. Tanggal tampil di kepala halaman |
| B2 | Universe dan gerbang | Sama dengan library: universe G2, gerbang likuiditas "Luas" (bawaan) atau "Likuid". Keanggotaan ditetapkan pada tanggal as-of dan dipakai untuk semua titik ekor, supaya ekor tidak melompat karena anggota berganti |
| B3 | Kelompok | Pilihan tambahan **Indeks** dan **Grup konglomerasi** dari `Stock_List` (median anggota; usulan 2026-11-14, menunggu konfirmasi). **Sektor** (bawaan, `Feature_01_Stock_Daily.sector`, 11 sektor; "Undefined" tidak ditampilkan) atau **Industri** (`Feature_01_Stock_Daily.industry`; 59 industri, 46 dengan ≥ 5 saham di seluruh universe) |
| B4 | Anggota minimum | Sektor ≥ 10 saham, industri ≥ 5 saham sesudah gerbang. Kelompok di bawah batas tidak digambar dan disebut di catatan peta |
| B5 | Agregasi | **Median** nilai anggota (keputusan 2026-11-13). Rata-rata tidak dipakai, karena satu saham bisa menguasainya (bagian 4.4) |
| B6 | Pembanding | Bawaan **pasar sama bobot**: median nilai semua saham yang lolos gerbang. Pilihan **IHSG** (hanya lensa Harga). Pembanding yang dipakai selalu disebut di judul peta, misalnya "vs median 426 saham" |
| B7 | Ekor | Titik pada **T−20**, **T−5** dan **T** (sesi bursa), disambung panah ke arah T. Pilihan: ekor harian 10 sesi |
| B8 | Papan | Regular |
| B9 | Format | EDGE Design Spec v1.2; poin bertanda ("+3,7 pt") untuk selisih |

---

## 2. Lensa

Setiap lensa memberi **X (level)** dan **Y (momentum)**. Titik (0, 0) adalah pembanding.

| Kuadran | Syarat | Arti |
|---|---|---|
| **Leading** | X ≥ 0, Y ≥ 0 | lebih kuat dari pembanding dan makin kuat |
| **Weakening** | X ≥ 0, Y < 0 | masih lebih kuat, tetapi melemah |
| **Lagging** | X < 0, Y < 0 | lebih lemah dan makin lemah |
| **Improving** | X < 0, Y ≥ 0 | masih lebih lemah, tetapi membaik |

Nama kuadran mengikuti kebiasaan Relative Rotation Graph. Nama "RRG", "JdK RS-Ratio" dan "JdK RS-Momentum" adalah merek terdaftar RRG Research dan tidak dipakai; rumus di bawah adalah rumus sendiri.

### 2.1 Lensa Harga
- **X(t)** = median `return_20d_pct` anggota kelompok − median `return_20d_pct` pembanding (pasar sama bobot), dalam poin. Dengan pembanding IHSG: dikurangi `return_20d_pct` IHSG (`Feature_01_Stock_Daily_INDEX`).
- **Y(t)** = X(t) − X(t−5).
- **Sumber:** `Feature_01_Stock_Daily`. Status: Siap.

### 2.2 Lensa Breadth
- **Breadth kelompok** = % anggota dengan close > EMA. Bawaan EMA 50 (`ema_50`), pilihan EMA 20 dan EMA 200.
- **X(t)** = breadth kelompok − breadth pasar (semua saham yang lolos gerbang), dalam poin.
- **Y(t)** = X(t) − X(t−5).
- **Alasan dipusatkan:** pada 9 Nov hanya 13,8% saham pasar di atas EMA 50. Dengan titik tengah 50%, semua sektor menumpuk di sisi kiri.
- **Sumber:** `Feature_04_Technical_Indicator` (EMA 20 belum ada sebagai kolom: Hitung). Status: Siap untuk EMA 50/200.

### 2.3 Lensa Arus asing (nol mutlak, keputusan 2026-11-14)
- **Rasio kelompok (jendela W)** = Σ net asing anggota ÷ Σ total beli anggota (beli asing + beli domestik) selama W sesi, dalam %.
- **X(t)** = rasio 20D kelompok. 0 berarti asing beli dan jual seimbang; positif = asing beli bersih.
- **Y(t)** = rasio 5D − rasio 20D kelompok. Positif berarti minggu ini asing lebih banyak membeli (atau lebih sedikit menjual) daripada rata-rata bulannya.
- Rasio pasar (semua saham yang lolos gerbang) tampil sebagai titik abu-abu "Pasar" di peta, sebagai pembanding visual.
- **Agregasi:** rasio dari jumlah Rupiah, bukan median rasio per saham. Satu Rupiah dihitung satu kali, dan saham tanpa transaksi asing tidak membuat median nol.
- **Sumber:** `Feature_06_Foreign_Domestic`. Status: Siap.
- Kuadran tetap memakai nama yang sama; untuk lensa ini artinya mutlak: Leading = asing beli bersih dan makin deras.

### 2.4 Contoh 9 Nov 2026 (median, dipusatkan ke pasar)

Pasar pada 9 Nov: median return 20D −20,6%, breadth EMA 50 13,8%, rasio asing 20D −6,1% dan 5D −0,7% (titik "Pasar" di lensa Arus asing: (−6,1; +5,4)).

Format: (X, Y) pada T−20 → T−5 → T.

| Sektor | Harga (dipusatkan) | Breadth EMA 50 (dipusatkan) | Arus asing (mutlak, 0 = seimbang) |
|---|---|---|---|
| Basic Materials | (1,7; 0,6) → (−0,7; −2,0) → (3,7; 4,4) **Leading** | (7,0; −3,4) → (3,4; −1,3) → (0,4; −2,9) **Weakening** | (−1,6; −0,4) → (−1,8; −0,6) → (−2,8; −3,9) **Lagging** |
| Consumer Cyclicals | (−3,1; −3,2) → (−5,7; −1,4) → (−5,1; 0,6) **Improving** | (−7,2; −7,3) → (2,9; 2,6) → (0,4; −2,5) **Weakening** | (−0,7; 0,6) → (0,0; −0,9) → (0,7; 2,5) **Leading** |
| Consumer Non-Cyclicals | (2,4; −0,1) → (4,8; 2,0) → (5,2; 0,3) **Leading** | (8,5; 1,3) → (2,1; 2,1) → (5,3; 3,2) **Leading** | (0,4; 3,1) → (−0,2; −2,6) → (−1,6; −2,3) **Lagging** |
| Energy | (−0,8; −0,3) → (1,0; −0,6) → (−0,7; −1,7) **Lagging** | (−0,5; −2,9) → (3,1; −3,1) → (3,7; 0,6) **Leading** | (−3,0; 0,7) → (−3,0; 1,2) → (−3,3; −0,0) **Lagging** (Y di batas 0) |
| Financials | (−1,4; −1,5) → (2,9; 6,3) → (7,5; 4,6) **Leading** | (−12,1; 0,2) → (2,4; 6,3) → (3,7; 1,2) **Leading** | (−14,9; 3,5) → (−15,4; 9,4) → (−13,0; 16,0) **Improving** |
| Healthcare | (9,2; 7,9) → (3,6; 0,2) → (0,6; −3,0) **Weakening** | (17,4; 18,5) → (−0,5; 2,7) → (−1,3; −0,9) **Lagging** | (−3,5; 5,4) → (−2,2; −3,8) → (−4,8; −6,9) **Lagging** |
| Industrials | (−1,1; −4,8) → (−6,8; −6,1) → (−5,9; 0,9) **Improving** | (−1,9; −5,5) → (−1,4; 5,1) → (−6,2; −4,7) **Lagging** | (−2,4; 0,3) → (1,0; 2,5) → (4,7; 13,7) **Leading** |
| Infrastructures | (−4,6; −2,2) → (−7,1; −2,2) → (−2,2; 4,9) **Improving** | (−9,3; 5,2) → (−3,0; −4,4) → (−7,2; −4,2) **Lagging** | (−10,5; 2,0) → (−10,3; −6,6) → (−9,1; 7,9) **Improving** |
| Properties & Real Estate | (−2,0; −0,3) → (−1,1; −0,1) → (0,7; 1,9) **Leading** | (−5,4; 2,1) → (−6,9; −0,2) → (−4,8; 2,2) **Improving** | (−3,5; 2,1) → (3,3; −7,2) → (3,4; −6,2) **Weakening** |
| Technology | (−2,5; −2,0) → (−0,9; −4,9) → (−5,4; −4,5) **Lagging** | (2,2; 1,7) → (−13,0; −12,8) → (−5,2; 7,8) **Improving** | (−16,3; 3,6) → (−1,7; 7,0) → (1,9; −11,1) **Weakening** |
| Transportation & Logistic | (3,0; 2,1) → (−0,3; 6,0) → (−3,8; −3,5) **Lagging** | (11,1; 18,5) → (−6,7; −3,6) → (−7,6; −0,9) **Lagging** | (−0,4; −0,6) → (−1,8; −4,3) → (−2,8; −5,2) **Lagging** |

**Cara baca contoh:**
- **Financials** Leading di Harga dan Breadth, Improving di Arus asing: tiga lensa searah membaik. Asing masih jual bersih (X −6,8), tetapi minggu ini jauh lebih ringan (Y +10,5).
- **Consumer Non-Cyclicals** Leading di Harga dan Breadth, tetapi asing melemah: harga belum didukung asing.
- **Industrials:** asing Leading (ASII +Rp200 miliar pada 9 Nov), tetapi harga dan breadth masih lemah.
- **Arus asing mutlak:** Industrials satu-satunya sektor yang asing beli bersih dan makin deras (4,7%; +13,7). Financials masih dijual bersih (−13,0%) tetapi melambat tajam (+16,0). Basic Materials dijual bersih dan makin deras (−2,8%; −3,9).

---

## 3. Peta (tampilan)

| Unsur | Isi |
|---|---|
| Sumbu | X dan Y dalam poin; garis 0 tebal di kedua sumbu; skala simetris di sekitar 0 menurut nilai terbesar di data (ditambah ruang 10%) |
| Kuadran | Latar tipis per kuadran, labelnya di sudut: hijau Leading, kuning Weakening, merah Lagging, biru Improving |
| Titik | Satu per kelompok; titik T tebal dengan label nama, titik T−5 dan T−20 lebih kecil dan pudar |
| Ekor | Garis dari T−20 ke T−5 ke T dengan panah di ujung T |
| Ukuran titik | Nilai transaksi 20D kelompok (total beli) |
| Warna titik | Kuadran titik T |
| Hover | Nama, jumlah anggota, X dan Y di ketiga titik, kuadran, median return 20D mutlak, breadth mutlak, rasio asing mutlak |
| Kontrol | Lensa (Harga / Breadth / Arus asing); Kelompok (Sektor / Industri); Pembanding (Pasar / IHSG, lensa Harga saja); EMA (20 / 50 / 200, lensa Breadth saja); Ekor (20-5-0 / harian 10); Gerbang (Luas / Likuid) |
| Klik titik | Membuka panel Analisis Sektor (bagian 5) |
| Judul | Lensa, pembanding, gerbang dan tanggal, misalnya "Harga · vs median 426 saham · Luas · 9 Nov 2026" |
| Kosong | Kelompok di bawah anggota minimum disebut di catatan: "Healthcare tidak digambar: 8 saham, minimum 10" |

---

## 4. Matriks konfirmasi (di bawah peta)

### 4.1 Isi
Satu baris per sektor, tiga kolom badge kuadran (Harga, Breadth, Arus asing) pada T, ditambah kolom "berubah dari T−5" (panah bila kuadran berubah).

### 4.2 Penanda
- **"Searah membaik"**: ≥ 2 lensa di Leading atau Improving dan Y ≥ 0. Pada 9 Nov: Financials (tiga lensa), Properties & Real Estate (Harga Leading, Breadth Improving).
- **"Searah memburuk"**: ≥ 2 lensa di Lagging atau Weakening dan Y < 0. Pada 9 Nov: Healthcare, Technology, Transportation.
- **"Bertentangan"**: harga Leading tetapi asing Weakening, atau sebaliknya. Contohnya Consumer Non-Cyclicals.

### 4.3 Urutan
Menurut jumlah lensa searah, lalu nama sektor.

### 4.4 Kenapa median (bukti)
Pada 9 Nov, BSWD naik +489% dalam 20 hari. Dengan rata-rata, Financials tercatat +15,2 poin di atas pasar dan hanya 6 dari 40 saham mengalahkan "rata-rata sektor". Dengan median, Financials +7,5 poin.

---

## 5. Panel Analisis Sektor (saat sektor diklik)

**Excess return** (keputusan 2026-11-13) = return saham − return pembanding pada periode yang sama, dalam poin.
- Pembanding: **toggle median sektor / median pasar** (keputusan 2026-11-14). Bawaan median sektor (usulan); pilihan terakhir pengguna diingat.

| # | Komponen | Isi dan rumus |
|---|---|---|
| P1 | Kepala sektor | Badge kuadran tiga lensa, jumlah anggota, median return 20D, breadth EMA 50, rasio asing 20D (Rp dan %) |
| P2 | **Line chart mulai dari 0** | Return kumulatif sejak awal periode: indeks(t) = 100 × (harga(t) ÷ harga(awal) − 1); semua garis mulai dari 0%. Garis: median sektor (setiap hari median return kumulatif anggota) dan pembanding (median pasar atau IHSG). Pilihan: garis 3 saham dengan excess return terbaik dan 3 terburuk. Pilihan kedua: satu garis excess sektor (sektor − pembanding), juga mulai dari 0. Periode: 20D / **60D (bawaan, keputusan 2026-11-14)** / 120D / YTD |
| P3 | **Heatmap saham × periode** (tampilan utama) | Baris = anggota; kolom = 1D / 5D / 20D / 60D / YTD; sel = excess return vs median sektor (pilihan vs median pasar). Warna divergen: hijau positif, merah negatif, intensitas dipotong di ±P95 sektor supaya satu pencilan tidak memucatkan semua sel. Urutan menurut kolom yang dipilih (bawaan 20D) |
| P4 | Heatmap harian (tab opsional) | Baris = anggota; kolom = 20 sesi terakhir; sel = excess return harian vs median sektor hari itu. Menunjukkan apakah outperform konsisten atau dari satu hari |
| P5 | Peta rotasi anggota | Rotation Map yang sama, titiknya saham anggota vs median sektornya (lensa Harga) |
| P6 | Tabel outperform / underperform | 10 teratas dan 10 terbawah menurut excess 20D. Kolom: excess 5D, 20D, 60D; rasio net asing 20D; Top Brokers % 5D (leaderboard F3); di atas EMA 50 (ya/tidak); RSI 14; nilai transaksi 20D |
| P7 | Sebaran | P90 − P10 return 20D anggota, dibanding sebaran sektor lain. Lebar berarti pilihan saham lebih menentukan daripada pilihan sektor |
| P8 | Penanda pencilan | Saham dengan return di luar median ± 3 × IQR sektor diberi label "Pencilan", dengan nilai transaksi dan catatan "periksa aksi korporasi" |

**Contoh Financials, 9 Nov (excess return vs median sektor):**
- Median sektor −13,1% (20D) dan −0,2% (5D). Median pasar −20,6%.
- Batas pencilan 20D: di atas +35,4% atau di bawah −61,5% (IQR 16,2 poin). **BSWD (+489%) adalah pencilan.**

| Saham | 20D vs sektor | 5D vs sektor | 20D vs pasar |
|---|---:|---:|---:|
| BSWD (pencilan) | +502,1 | −9,7 | +509,6 |
| BTPS | +19,2 | +4,2 | +26,7 |
| SRTG | +14,5 | +8,6 | +22,0 |
| BTPN | +14,3 | +1,9 | +21,8 |
| BBNI | +13,1 | +2,9 | +20,6 |
| … | | | |
| ARTO | −18,9 | −1,7 | −11,4 |
| BCAP | −24,9 | +0,2 | −17,4 |
| ASMI | −25,2 | −8,5 | −17,7 |
| AHAP | −26,9 | −2,1 | −19,4 |
| COIN | −41,1 | +0,2 | −33,6 |

Sebaran 20D Financials (P90 − P10): 32,7 poin.

Klik baris di P3, P4 atau P6 membuka Terminal untuk saham itu.

---

## 6. Data dan status

| Kebutuhan | Sumber | Status |
|---|---|---|
| Return 1D/5D/20D/60D | `Feature_01_Stock_Daily` | Siap |
| Return YTD, 120D, garis kumulatif harian (P2) | `Price_Stock_Indonesia_IDX` (close harian) | Hitung |
| Sektor, industri | `Feature_01_Stock_Daily.sector`, `.industry` (klasifikasi terkini, dipakai untuk semua tanggal) | Siap |
| Breadth EMA 50/200 | `Feature_04_Technical_Indicator` | Siap |
| Breadth EMA 20 | dari close harian | Hitung |
| Arus asing | `Feature_06_Foreign_Domestic` | Siap |
| IHSG | `Feature_01_Stock_Daily_INDEX` (IHSG satu-satunya level indeks di database) | Siap |
| Anggota indeks (33: LQ45, IDX30, KOMPAS100, JII, …) dan grup konglomerasi (33: DANANTARA, SALIM, ASTRA, …) | `Stock_List`, `Stock_List_Member` (keanggotaan terkini; riwayat `Stock_List_Member_History` mulai 2026-11-09). Koreksi 2026-11-14: versi sebelumnya menyebut data ini tidak ada | Siap untuk kelompok "Indeks" dan "Grup" (median anggota). Catatan: keanggotaan terkini dipakai untuk semua titik ekor; satu saham bisa masuk banyak indeks |
| Level indeks sektoral dan LQ45 (harga indeksnya) | – | **Data baru** |
| Pengiriman ke halaman | Satu file ringkasan per tanggal (semua kelompok dan anggota untuk T, T−5, T−20 dan harian 20 sesi), ditulis publisher seperti file Terminal | Belum ada; dibangun bersama leaderboard |

---

## 7. Peringatan baca (tampil di halaman)

- Peta menggambarkan keadaan pada tanggal itu, bukan ramalan. Putaran searah jarum jam adalah pola pengamatan, bukan kepastian.
- Bukti akademik tentang arus asing di IDX bercampur. Ada studi yang menemukan arus asing memengaruhi harga, ada yang tidak menemukan pengaruh pada indeks.
- Klasifikasi sektor dan industri adalah klasifikasi terkini untuk semua tanggal.
- Median sektor tidak berbobot ukuran perusahaan; IHSG berbobot kapitalisasi. Keduanya menjawab pertanyaan berbeda.

---

## 8. Pertanyaan terbuka

1. ~~Sumbu arus asing~~: diputuskan 2026-11-14, nol mutlak.
2. **Anggota minimum:** sektor ≥ 10 dan industri ≥ 5 sudah tepat?
3. ~~Pembanding panel Analisis Sektor~~: diputuskan 2026-11-14, toggle median sektor / median pasar.
4. ~~Periode P2~~: diputuskan 2026-11-14, bawaan 60D.
5. **Kelompok Indeks dan Grup** (baru, karena `Stock_List` ternyata tersedia): masuk pilihan kelompok?

Sumber metode: StockCharts ChartSchool, *Relative Rotation Graphs*; StockCharts, *RRG Tails Have a Story to Tell*; StockCharts, *Using Breadth Data to Confirm Sector Rotation*; SAGE Open 2023 dan EUDL 2022 (arus asing IDX).
