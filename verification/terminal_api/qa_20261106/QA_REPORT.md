# QC/QA frontend Terminal — draft `c20703ff` (2026-11-06)

Diminta user 2026-11-06 ("Lakukan QC dan QA frontend terminal pada draft saat ini menggunakan 5 subagent ... Tahap ini
hanya pemeriksaan dan pelaporan"). Lima subagen Sonnet (effort high): 1 UI, 2 angka vs backend, 3 label, 4 fungsi,
5 kelancaran/aksesibilitas/regresi. Tidak ada kode yang diubah dan tidak ada yang dipublikasikan. Draft ada di branch
`claude/practical-thompson-2intee` dan tidak ada di `main`.

Bukti (skrip, tangkapan layar, hitung ulang) disimpan di scratch sesi:
`/tmp/claude-0/-home-user-saniti/5abac1e8-94e8-5166-9d5b-02bb4e4273bc/scratchpad/qa1` … `qa5`.

## 1. Status: FAIL

- **Angka:** tidak ada angka yang salah. Snapshot sama dengan PostgreSQL: BBRI 19.622 baris broker dan 436 baris harga,
  jumlahnya identik. Ada 44 baris matriks dari agen 2 ditambah hitung ulang agen 3, semuanya cocok.
- **Kegagalan yang terbukti:**
  - tata letak ponsel/tablet rusak (High);
  - label sumbu Y peta kehilangan tanda +/− (High);
  - pilihan yang dikosongkan hilang saat reload (Medium).
- **Batas cakupan:**
  - Situs dev live tidak diuji (tanpa login). Semua pengujian memakai stand-in lokal dengan data asli yang diekspor
    2026-11-06 ~07:00 UTC, data sampai 2026-11-03.
  - Broker BBRI hanya sejak 2026-01-02, jadi baseline 250 tidak bisa diuji.
  - Tidak diuji: obligasi, intraday, perangkat sentuh asli, Safari/Firefox, pembaca layar.
  - Warna titik domisili broker tidak terlihat karena stand-in memberi semua broker tipe Domestic.

## 2. Temuan (digabung, tanpa duplikat)

### High
**H1 — Ponsel/tablet: tombol filter Flow di baris panel meluber keluar panel.** Ditemukan agen 1, 4 dan 5.
- Lokasi: `terminal.css` `.ind-row.in-pane:has(.ind-flt)` (~1220) dan `@media(max-width:760px)` (~1267).
- Langkah: emulasi iPhone 13 (390 px), tambahkan FL12 (dan FL23).
- Hasil: kontrol menumpuk satu kolom. Tinggi baris 262 px di panel ±140–230 px. Rank by, Board dan Investor menutupi
  judul Flow Timeline dan angka "Latest day net". Di 768 px/iPad, nilai "100.0%" muncul di panel berikutnya dan label
  sumbu Broker Inventory terpotong.
- Bukti: qa1/t12_phone_fl12.png, qa1/t9_main_iPhone 13.png, qa1/t9_main_768.png, qa5/shots/p2_rows.png.
- Dampak: Terminal di ponsel tidak terpakai begitu ada indikator Flow di panel.
- Saran: di bawah ~1024 px, kontrol dilipat ke satu tombol "Filters" (popover), atau dibuat satu baris yang bisa
  di-scroll; panel tidak boleh lebih pendek dari barisnya.

**H2 — Ponsel: baris Flow di chart harga melebar keluar layar.** Ditemukan agen 5.
- Lokasi: `.ind-flt.on-hover`.
- Hasil: setelah diketuk, baris FL17 selebar 615 px pada layar 390 px; Board dan Investor di luar layar.
- Bukti: qa5/shots/p3_fl17_tapped.png.
- Saran: sama dengan H1.

**H3 — Peta Foreign × Domestic: label sumbu Y terpotong, tanda +/− hilang.** Ditemukan agen 1, 2 dan 3.
- Lokasi: `fdMap.ts` `mapSvg`, margin kiri `L=30` dengan label di `L-4`.
- Hasil: "+17.5%" dan "−17.5%" sama-sama tampil "7.5%"; "+35%" kehilangan tanda (bbox x mulai −12 px).
- Bukti: qa2/s17_map.png, qa3/shots/03_map_hi.png, qa1/t4_fdmap.png.
- Dampak: salah baca sumbu domestic. Angka di tabel tetap benar.
- Saran: margin kiri ±44, atau hapus label setengah-rentang.

### Medium
**M1 — Pilihan yang dikosongkan (Clear) hilang saat reload, dan semua parameter ikut kembali ke bawaan.**
Ditemukan agen 4 dan 5.
- Lokasi: `indicators.ts` `add()` menjalankan `def.validate` lalu `defaults()`; `flowIndicators.ts` `validate` menolak
  kondisi yang justru diizinkan `emptyChoice`.
- Langkah:
  - FL23 → Brokers → Clear → reload: broker kembali XL, YU, ZP.
  - FL12 → Days 12 → scope Selected (kosong) → reload: kembali Top-N/3/5.
- Hasil tambahan: dialog ⚙ menolak Ok untuk FL23 yang kosong ("Choose 1 to 5 brokers.").
- Bukti: qa4/t6.mjs, t10.mjs, t24.mjs; qa5/s9.mjs, s10.mjs.
- Saran: daftar kosong yang tersimpan jangan di-reset (`emptyChoice` sudah menanganinya); dialog konsisten dengan baris.

**M2 — Cakupan "All brokers" dengan kedua jenis investor memberi 0% struktural tanpa keterangan.** Ditemukan agen 2 dan 3.
- Hasil: FL11 menampilkan "0.0% / 0.00 pt", FL12 garis datar 0.0%, FL21 kosong. Ini terjadi karena setiap beli ada
  penjualnya.
- Pembanding: FL46 punya gerbang untuk kasus ini; indikator lain tidak. Kontrol baris membuatnya hanya satu klik.
- Bukti: qa2/s24.png, qa3/run6.mjs.
- Saran: catatan di baris ("Net of all brokers over both investor types is always 0"), atau minta filter investor.

**M3 — Arti "Foreign/Domestic" dan nama kuadran bisa salah dibaca.** Ditemukan agen 3.
- Lajur dan peta memakai **jenis investor transaksi**, hanya di dalam broker Top N. Tabel di panel yang sama mewarnai
  titik broker menurut **domisili broker**.
- Contoh: X peta 1D = −232B lewat Top-N, sedangkan net asing seluruh saham −310B.
- Nama kuadran tetap muncul untuk nilai sangat kecil (−0.04%/+0.1%).
- Saran: label "Foreign investors / Domestic investors (via Top N)", catatan bahwa warna titik = domisili broker,
  kuadran "… in Top N", dan ambang minimum sebelum memberi nama kuadran.

**M4 — Peta: titik 20D tidak bisa di-hover, tooltip hanya untuk mouse, titik ganda.** Ditemukan agen 1, 3 dan 5.
- Lingkaran hit r=12 milik titik 5D menutupi titik 20D (jarak 10,4 unit).
- Tooltip tidak muncul lewat keyboard atau ketukan.
- Custom = preset, atau periode dekat sesi pertama, menghasilkan baris dan titik kembar (mis. tiga baris "2D" sama).
- Bukti: qa5/s6.mjs, s7.mjs, shots/map_dots.png; qa1/t16_map_260.png.
- Saran: gambar lingkaran hit lebih dulu atau pilih titik terdekat; titik bisa difokus (tabindex, aria-label) dan
  tooltip muncul saat fokus/ketuk; buang titik kembar.

**M5 — Kontrol di baris chart harga tidak bisa dicapai keyboard.** Ditemukan agen 4 dan 5.
- `.ind-flt.on-hover{display:none}`.
- Tombol mata/gear/x di legend juga sudah tidak bisa dicapai sejak sebelum draft ini.
- Saran: baris bisa difokus sehingga `:focus-within` memunculkan kontrol.

**M6 — File broker gagal: baris menulis "Loading broker data" selamanya, header "Rp 0".** Ditemukan agen 4.
- Langkah: 500 pada `/bucket/broker/...`.
- Bukti: qa4/t18_s3.png.
- Sebagian kemungkinan sudah ada sebelum draft ini.
- Saran: tampilkan pesan galat di baris dan "–", bukan 0.

**M7 — Top brokers papan Nego/Cash menulis "Tidak ada data" padahal ada transaksi (net 0).** Ditemukan agen 2 dan 4.
- Petunjuk di header tetap "· Neutral"; teks berbahasa Indonesia di panel berbahasa Inggris.
- Saran: "No broker has a net buy or sell on this board".

**M8 — Nilai legend kosong tanpa alasan.** Ditemukan agen 1, 2 dan 4.
- Contoh: riwayat terlalu pendek (FL21 baseline 250, FL24 mingguan, Buy VWAP 20M bulanan).
- Saran: `note()` menyebut "Needs N candles of history".

**M9 — Cari "RSI" tidak menemukan Relative Strength Index.** Ditemukan agen 4.
- Pencarian tidak memakai nama pendek (SMA, EMA, ATR, OBV, VWAP…).
- Sudah ada sebelum draft ini, tetapi placeholder kini memberi contoh "RSI".
- Saran: masukkan `short` ke pencarian.

### Low
**Kotak N dan undo**
- Mengosongkan kotak N lalu Enter memberi Top 1, bukan kembali ke nilai sebelumnya.
- Setiap langkah spinner menjadi satu langkah undo.
- Klik broker di panel kanan tidak bisa di-undo.

**Fokus, keyboard dan aksesibilitas**
- Sesudah memilih scope/Rank, fokus tetap di select sehingga Ctrl+Z dan Alt+B diabaikan.
- Jendela Indicators bukan modal penuh (Tab keluar dari jendela).
- Esc pada popover Brokers memindahkan fokus ke body.
- Urutan Tab mata/gear/x vs kontrol tidak urut.
- Kontras abu-abu legend 3,23:1, di bawah AA 4,5:1. Ini permintaan "soft grey"; #767676 (4,54:1) akan lulus.

**Tata letak**
- Rail tidak pernah menandai kelompok terakhir yang pendek (Other) saat di-scroll.
- Legend melompat saat baris chart harga di-hover (CLS 0,001–0,043).
- Tooltip peta `nowrap` selebar ±800 px.
- Panel kanan 260 px sempit.
- Label sumbu bertabrakan dengan badge (perilaku library).

**Format angka**
- "−0.0%" muncul; tanda "-" dan "−" bercampur.
- Format T satu desimal (+3,043B tampil "+3T").
- Satuan tidak tertulis: FL23 tanpa "lot", Value tanpa "Rp".
- Bulan "Sept" (en-GB).
- Denominator FL24 Foreign tidak disebut.
- N > 20 dipotong diam-diam.
- Komentar dan aria-label peta masih menyebut diagonal.

**Penyimpanan**
- `boards:"abc"` di localStorage yang diedit tangan memunculkan galat; `top:999` diterima.

**Sudah ada sebelum draft ini**
- Return mode dihitung dari candle pertama yang dimuat.
- Flow Timeline "Rp 0" sebelum tanggal broker pertama.
- Toolbar ponsel terpotong; panel kanan tidak terjangkau di ponsel.

## 3. Matriks validasi angka (ringkas; lengkap di laporan agen 2 dan 3)

| Komponen | Label | Field backend | Nilai sumber | Transformasi/unit | Nilai UI | Status |
|---|---|---|---|---|---|---|
| Top brokers | Verdict Top 3 5D | Feature_05 buy_value, sell_value | −6.3283% | (net Top3 beli − net Top3 jual) ÷ total beli | −6.33% Dist | Cocok |
| Top brokers | Verdict Top 3 1D / 20D | sama | −2.4534% / −3.7322% | sama | −2.45% / −3.73% | Cocok |
| Top brokers | Verdict Top 5 5D / Top 10 20D | sama | −4.8854% / −2.6997% | sama | −4.89% / −2.70% | Cocok |
| Top brokers | Domestic / Foreign / Total 5D | + investor_type | +354.73B / −599.46B / −244.73B | Rp ringkas | +354.7B / -599.5B / -244.7B | Cocok |
| Top brokers | Board Regular 5D | market_board | −6.3689% | penyebut papan itu | −6.37% | Cocok |
| Top brokers | Board Nego 5D | market_board | 37 baris, net tiap broker 0 | — | "Tidak ada data" | Menyesatkan (M7) |
| Broker summary | OD 1D lot/value/avg | buy/sell lots, value | 409,017 / 111.59B / 2,728 | value ÷ (lot×100) | 409K / 111.6B / 2,728 | Cocok |
| Peta | X/Y/verdict 1D, 5D, 20D Top 3 | per investor_type | −26.63/+24.17/−2.45; −15.50/+9.17/−6.33; −15.96/+12.22/−3.73 | % total beli | −26.6/+24.2/−2.5; −15.5/+9.2/−6.3; −16.0/+12.2/−3.7 | Cocok |
| Peta | Top 10 1D; 4 periode custom | sama | −35.85/+31.80/−4.05 | % | −35.9/+31.8/−4.0 | Cocok |
| Peta | Label sumbu Y ±17.5% | — | +17.5% | teks | "7.5%" | Salah (H3) |
| Broker inventory panel | NI/CC/OD lot sejak 26 Jan | bl − sl | 5,998,606 / 4,917,894 / 4,041,651 | lot | +6M / +4.9M / +4M | Cocok |
| FL23 | Broker bawaan opsi C | Σ(bv−sv) | XL, YU, ZP | 2 net buyer + 1 net seller | XL YU ZP | Cocok |
| FL23 | Garis akhir | bl − sl kumulatif | 9.49M / 6.50M / −19.70M | lot | 9.5M / 6.5M / −19.7M | Cocok (tanpa satuan, Low) |
| FL23 | Zoom mulai 15 Apr | bl − sl | XL 539,077 | kumulatif dari candle pertama terlihat | 539.1K | Cocok |
| FL12 | Top-N 5, Rank gross buyers, 5D | bv, sv | 80.0 / 40.0 / 20.0 | % hari net beli | sama | Cocok |
| FL01 | Selected OD, CC, Buy, 03 Nov | bl, bf | 73.4738 | lot per transaksi | 73.5 | Cocok |
| FL24 | N=5; Foreign N=3 | bv, sv | 5.3669; −35.4023 | % | 5.4%; −35.4% | Cocok |
| FL22 | Foreign 03 Nov | bv, sv | 62.963 | % broker aktif | 63.0% | Cocok |
| FL11 | Rank net sell, Regular | bv, sv | −27.798; −13.02 | %, pt | −27.8%, −13.02 pt | Cocok |
| FL10 | Foreign | bf, sf | −0.3344 | (bf−sf)/(bf+sf) | −0.33 | Cocok |
| FL21 | Foreign, baseline 20 | bv, sv | 90/95/35/50/45 | persentil | sama | Cocok (baseline 250 belum terverifikasi) |
| FL17 | Top 5 gross, Foreign, 20D | bv, bl | 2,824.13 | Rp/lembar | 2,824.1 | Cocok |
| Mingguan | FL12/FL24/FL11 | jumlah mingguan | 60.0 / −0.936 / 19.068 | candle W | 60.0% / −0.9% / 19.1% | Cocok |
| FL11/FL12 | Scope All brokers | bv, sv | 0 secara konstruksi | % | 0.0% | Menyesatkan (M2) |
| Flow Timeline | Latest/period/avg (Foreign) | bv − sv | −310.06B; −16.32T; ÷200 | Rp | −310.1B; −16.3T; −81.6B | Cocok |
| Sumbu harga | BBRI last | close | 2,660 | 0 desimal | 2,660 | Cocok |
| Sumbu harga | IHSG last | close | 4,904.287 | 2 desimal (keputusan user) | 4,904.29 | Cocok (dibulatkan) |
| Panel IHSG | Rasio / lajur / peta 5D | Feature_05_INDEX | −1.652% / 1,294B, −2,335B, −1,041B | Rp | −1.65% / +1.3T, -2.3T, -1T | Cocok |
| Legend | 4–5 Nov (sesudah data broker) | — | tanpa baris | teks | "No broker data yet (through Tue 03 Nov)" | Benar |
| FL34 | Klasifikasi Institutional/Retail | IDX_Broker_Profile | — | — | — | Belum terverifikasi (stand-in) |
| Statistics kiri | — | — | — | — | — | Belum terverifikasi (tidak berubah) |

## 4. Tes yang dijalankan

- **Terminal:**
  - `tsc --noEmit`: OK.
  - `vitest`: 21 file, 862/862 lulus.
- **Screener:** `npm run tripwire` OK.
- **Backtest:** `npm test` 88/88 lulus.
- **backtest-worker:** `npm test` gagal 3. Penyebabnya Node lokal menolak `import ... flowRegistry.json`
  (ERR_IMPORT_ATTRIBUTE_MISSING). Kegagalan yang sama terjadi pada arsip commit dasar `80b77b50`, jadi bukan karena
  draft ini.
- **screener-worker:** `npm test` gagal 1 (`onboarding_pointers`: nomor baris di SCREENER_ONBOARDING.md sudah bergeser).
  File itu tidak disentuh draft ini; belum dijalankan ulang di commit dasar.
- **Playwright pada halaman hasil build dengan stand-in:**
  - ±30 skenario fungsi, termasuk latensi 3,5 s dan respons 500;
  - 39 indikator Flow diputar kontrolnya;
  - 10 lebar layar plus emulasi iPhone/iPad;
  - pengukuran CLS dan long task;
  - mode `?fixture=reference`.

## 5. Rekomendasi kesiapan rilis

**Belum siap rilis.** Tidak ada angka yang salah, tetapi sebelum merge ke `main` perlu:
- **Wajib diperbaiki:** H1, H2, H3, M1, M2, M3.
- **Sebaiknya ikut:** M4, M5, M7, M8, M9 dan butir Low yang murah (−0.0%, satuan, N kosong, kelompok terakhir di rail).
- **Pemeriksaan ulang:** QA terarah pada butir-butir itu, ditambah ponsel/tablet.

Tidak ada yang dipublikasikan.

## 6. Perbaikan sesudah laporan (2026-11-06, go user)

Dicek ulang di Chromium dengan snapshot yang sama: `verification/terminal_api/terminal_look/look_check2.mjs` dan
`look_check3.mjs`, desktop 1440 px dan emulasi iPhone 13.

| Temuan | Perbaikan | Hasil cek ulang |
|---|---|---|
| H1, H2 | Di layar ≤ 1024 px kontrol dilipat ke tombol **Filters**. Panelnya terbuka di dalam layar dan memuat Hide, Settings dan Remove. Baris legend dibatasi lebar kolomnya. | Tinggi baris FL12/FL23/FL17 32 px, tepi kanan ≤ 314 px pada layar 390 px; panel 8–382 px; tanpa luapan halaman |
| H3 | Margin kiri peta 46 | Tidak ada label sumbu yang mulai di x < 0 |
| M1 | Daftar kosong bukan lagi "tidak valid" (validate), jadi tetap tersimpan; dialog menerimanya | Sesudah reload FL23 tetap `[]` dan menulis "Choose at least one broker"; FL12 tetap scope All |
| M2 | Dideteksi dari hasil hitungan (semua 0/kosong) saat scope All + kedua investor | Baris menulis "All brokers over both investor types always net to 0: choose Foreign or Domestic, or a Top-N cohort" |
| M3 | Tag kuadran "· Top N"; sumbu "Foreign/Domestic investors via Top N"; keterangan lajur "Investor type of the trades · Top N brokers"; legenda titik = tipe broker | Teks tampil |
| M4 | Titik besar digambar lebih dulu, area hit = titik + 3; titik bisa difokus; tooltip saat fokus/ketuk; satu titik per periode berbeda | Hover 5D, 20D, 1D masing-masing memberi tooltipnya; fokus memberi tooltip |
| M5 | Baris di chart harga bisa difokus (Tab memunculkan kontrol) | Kontrol tampil saat fokus |
| M6 | File broker gagal: "Broker data could not be loaded: reload the page" | Belum diuji ulang dengan respons 500 |
| M7 | Papan tanpa net: "No broker has a net buy or sell on this board in this period"; hint tanpa vonis | Tampil di Nego |
| M8 | Nilai kosong karena riwayat pendek: "Needs N candles of broker history (k so far)" | Belum diuji ulang di halaman |
| M9 | Pencarian memakai nama pendek, yang tepat lebih dulu | "RSI" → Relative Strength Index |
| Low | Kotak N kosong kembali ke nilai sebelumnya, nilai diterapkan saat Enter/blur (satu undo); select melepas fokus; "−0.0%" dibuang; "Sep"; tooltip maks. 360 px; kelompok terakhir ditandai di ujung daftar | Tes unit dan cek halaman |

Belum diubah: kontras abu-abu legend (permintaan user "soft grey"); satuan di judul FL23; urutan Tab mata/gear/x; Esc
pada popover; titik tunggal FL23 di indeks; perilaku lama di luar draft (Return mode, Rp 0 sebelum data broker, panel
kanan di ponsel).

## 7. QA putaran 2 — draft `55cba679` (2026-11-06)

Lima subagen Sonnet (high), hanya pemeriksaan. Bukti ada di scratch `qa1r2` … `qa5r2`.

**Status: FAIL.** Tidak ada angka hitungan yang berubah atau salah: matriks putaran 1 diulang (120/126 nilai sama, 6 sisanya
pembulatan ringkas yang sudah ada). Masih ada dua pesan yang salah (R2-M1, R2-M2), jadi belum lulus.

### Status temuan putaran 1
- **CLOSED:**
  - H1 dan H2 (ponsel/tablet), H3 (label sumbu peta).
  - M1 (pilihan kosong dan reload; dialog menerimanya), M4 (titik peta, tooltip lewat fokus/ketukan), M7 (Nego/Cash),
    M9 (pencarian; semua 51 nama pendek ketemu lebih dulu).
  - Kotak N, fokus sesudah select, kelompok terakhir di rail, "−0.0%", lebar tooltip.
- **PARTIAL:**
  - M2: catatan muncul di FL11/FL12/FL26, tetapi FL21/FL37 masih menggambar garis datar 50.0 bila baseline lebih pendek
    dari riwayat.
  - M3: label benar, tetapi persamaan dan tabel peta belum menyebut Top N, dan legenda titik memakai kata "Local".
  - M5: baris di chart harga sudah bisa difokus, tetapi tombol mata/gear/x di desktop masih hanya bisa dicapai lewat
    Shift+Tab.
  - M6: baris Flow sudah benar, tetapi Flow Timeline masih "Rp 0", catatannya terpotong, dan panel kanan "Loading" terus.
  - M8: catatan "Needs N" ada tetapi angkanya kurang 1.
  - "Sep": hanya dua tempat yang diperbaiki.

### Temuan baru dan sisa (digabung)
**Medium**
- **R2-M1 — Catatan "always net to 0" salah tempat.** Ditemukan agen 2 dan 4.
  - Lokasi: `carriesNothing` juga menyala bila semua nilai kosong.
  - Akibat: muncul di indikator gross, rasio dan konsentrasi (FL13, FL14, FL21 gross, FL33, FL36, FL38) yang kosong hanya
    karena riwayatnya pendek, termasuk di timeframe bulanan.
  - Garis datar 50.0 pada FL21/FL37 lolos dari deteksi.
- **R2-M2 — "Needs N candles" kurang 1.** Ditemukan agen 2 dan 3.
  - Contoh: FL21 b20 tertulis 20, sebenarnya 21; FL24 W10 tertulis 9, sebenarnya 10.
  - Akibatnya satu candle kosong tanpa alasan.
  - FL47 mode Value menulis "Needs 256" padahal cukup 5.
- **R2-M3 — File broker gagal: sisa halaman belum ikut.** Ditemukan agen 3 dan 4.
  - Flow Timeline "Rp 0" dan garis 0; catatan terpotong "Reload the p…".
  - Panel kanan "Loading" terus; header "BBRI · loading".
- **R2-M4 — Ponsel: catatan dan nilai legend terpotong.** Ditemukan agen 1 dan 5.
  - Contoh: "All br…", "Cho…", "Nee…", "2…".
  - Tidak ada `title` dan panel Filters tidak mengulang catatannya.
- **R2-M5 — Daftar broker dari panel Filters keluar dari bawah layar pendek.** Ditemukan agen 1.
  - Contoh: 1024×500 dan 667×300.
- **R2-M6 — Panel Filters dan keyboard/posisi.** Ditemukan agen 4 dan 5.
  - Tab melewati tombol terakhir membuat panel tetap terbuka di atas tombol baris berikutnya.
  - Esc tidak menutup panel bila fokus di body.
  - Posisi panel tidak mengikuti resize.
  - Panel menutupi tombol Filters baris di bawahnya.

**Low**
- "Sept" masih ada di chart (tooltip/legend), Flow, kalender, Statistics, aset, pop-out dan header panel kanan.
- Tanda minus bercampur: hyphen "-" di lajur/tabel, "−" di vonis/peta.
- Komentar kode peta masih menyebut diagonal.
- Persamaan/tabel peta "X · Foreign" tanpa "Top N"; legenda titik "Local" seharusnya "Domestic" (sesuai
  `IDX_Broker_Profile`: Domestic 80, Foreign 32).
- `aria-label` baris chart harga menggantikan teks baris (nilai tidak terbaca).
- Esc pada titik peta tidak menyembunyikan tooltip.
- Esc di popover Brokers memindahkan fokus ke body.
- Nama kuadran tanpa ambang minimum.
- Legend melompat ±2 px saat hover di desktop.
- Satuan (lot/Rp) tidak tertulis; format "T" satu desimal.

**Tidak berubah / sudah ada sebelumnya**
- Biaya geser chart dengan 6 indikator Flow pada CPU 4x setara versi sebelumnya (p50 ±55 ms di keduanya).
- Kontras abu-abu legend (keputusan user).
- Return mode; "Rp 0" sebelum data broker pertama.

### Tes
- **Terminal:** vitest 864/864 lulus; `tsc` OK.
- **Screener/Backtest:** tripwire OK; Backtest 88/88 lulus.
- **Playwright:** ±30 skenario per agen (desktop 1000–1920, iPhone 13, iPad, CPU 4x), tanpa galat konsol.
- **Tidak diuji:** situs live, perangkat sentuh asli, pembaca layar, obligasi, intraday, kasus baseline 250 pada riwayat
  > 250 sesi.

## 8. Perbaikan sesudah putaran 2 dan pekerjaan 1A/2A (2026-11-06, go user)

**Kata user:** "1A 2A. Jalankan setelah laporan QA agent beres saja, biar sekalian bereskan bug." lalu "Ok".

**Temuan putaran 2 yang diperbaiki** (commit `f2660c95`)
- R2-M1: catatan "always net to 0" hanya bila hasilnya konstan (bukan bila kosong karena riwayat pendek).
- R2-M2: "Needs N" dihitung dari nilai pertama indikator itu sendiri.
- R2-M3: file broker gagal tampil "—" dan pesan di Flow Timeline, tooltip dan panel kanan.
- R2-M4: di layar sempit nilai/catatan pindah ke baris sendiri dan dibungkus; `title` berisi teks penuh.
- R2-M5: daftar broker membuka ke atas bila ruang di bawah lebih sempit, atau dipotong dan bisa digulir.
- R2-M6: Esc menutup panel Filters di mana pun fokusnya; Tab keluar menutupnya; panel ikut saat resize/scroll.
- Low: "Sep" di semua tempat; satu tanda minus "−"; komentar diagonal; "Top N" di persamaan peta; "Domestic" di legenda
  titik; baris chart harga tanpa `aria-label`; Esc pada titik peta.
- **Belum dikerjakan (Low):** Esc di daftar Brokers memindah fokus ke body; nama kuadran tanpa ambang minimum; legend
  bergeser ±2 px saat hover; satuan lot/Rp tidak tertulis.

**1A — Top brokers** (draft)
- Tangga 5 tingkat Big Dist · Dist · Neutral · Acc · Big Acc; tingkat sekarang diwarnai, posisi rasio ditandai garis,
  ambang −10%/−6%/+6%/+10% di bawahnya (dari `BANDAR_LEVELS`, skala linear ±15%).
- Pilihan Board pindah ke baris periode; jarak antar blok rapi.

**2A — bawaan papan Regular** (draft)
- Panel kanan (live): Broker summary, Top brokers, Broker inventory, peta Foreign × Domestic mulai di Regular.
  Peta kini punya pilihan Board sendiri; x, y dan vonis memakai papan yang sama, tooltip menyebut papannya.
- Jendela pop-out mulai di Regular; state jendela yang sudah tersimpan tetap dipakai.
- Indikator Flow yang ditambahkan user: 45 parameter papan bawaan Regular lewat spesifikasi → registry (`--check` OK).
- Tetap All: Flow Timeline (panel bawah bawaan), mode fixture, Bandar detector (hanya tampil di fixture).

**Tes**
- Terminal vitest 864/864, `tsc` OK; Backtest 88/88; tripwire OK.
- Oracle vs Terminal: 127 kasus × 7 ticker, 457.498 nilai, 0 selisih (bawaan registry baru).
- Playwright (`terminal_look/look_check4.mjs`, `look_check3.mjs`): keempat pilihan papan = Regular di desktop dan
  iPhone 13; tangga BBRI 5D −6,37% → Dist; peta tooltip "Regular board"; FL12 baru `boards: ["Regular"]`; tanpa geser
  horizontal, tanpa galat konsol.

## 9. QA putaran 3 — draft `28614e02` (2026-11-06)

**Kata user:** "QA putaran 3." Lalu, sebelum QA mulai, dua fitur baru ditambahkan (EXEC-TERMINAL-LAYOUTS: "di akun edge. Tidak usah
mengganti saham."). Lima agen (Sonnet, high) hanya memeriksa; tanpa ubah kode, build, publish atau migrasi Railway.
Bukti tiap agen: scratchpad `qa1r3` … `qa5r3`.

| Agen | Area | Status |
|---|---|---|
| 1 | Menu layout di halaman | FAIL (1 High, 6 Medium) |
| 2 | API dan migrasi layout | PASS dengan temuan (3 Medium) |
| 3 | Angka sesudah 1A/2A (vs PostgreSQL) | PASS (3 Low) |
| 4 | Collapse panel bawah; setelan yang diingat | FAIL (collapse); PASS (setelan) |
| 5 | Uji ulang putaran 2; regresi | FAIL minor |

**Angka:** tidak ada yang salah. Top brokers 18 kombinasi, Broker summary 48, peta 243 nilai, FL11/12/23/24/33 Regular dan
All, Flow Timeline sesudah reload: semua cocok dengan PostgreSQL (BBRI sampai 2026-11-03).

### Temuan digabung
**High**
- **Q3-H1 — Collapse di layar ≤ 1024 px dan di ponsel:** panel Flow yang dilipat 30 px, padahal barisnya 44–193 px; baris saling
  tumpuk. Di 1440 baris dua-baris juga meluber dan chevron bisa mengenai tombol Remove baris berikutnya (agen 4 H1, M1).
  Akar yang sama: baris panel Flow di ponsel satu kata per baris dan saling tumpuk walau tidak dilipat (agen 5 M2).
- **Q3-H2 — Dialog Open layout keluar layar** di ponsel/1024 bila nama layout panjang (≥ 30 huruf); tombol Close/hapus tidak
  terjangkau (agen 1 H1).

**Medium**
- Q3-M1 — Panel terlipat masih menampilkan label sumbu "0.0"/"0.0%" (agen 4 M2).
- Q3-M2 — Menu layout: panah bawah berputar di Save/Autosave saja; dialog tanpa focus trap, Esc hanya bila fokus di dalam;
  fokus tidak kembali ke tombol Layout (agen 1 M1, M2).
- Q3-M3 — Perubahan dalam detik-detik awal sesudah membuka layout tidak tersimpan dan tidak ditandai (agen 1 M3).
- Q3-M4 — Membuka layout / Create new tanpa layout aktif membuang chart yang belum disimpan tanpa konfirmasi (agen 1 M4).
- Q3-M5 — Konflik autosave mengembalikan nama layout yang diganti di perangkat lain (agen 1 M5, agen 2 L2).
- Q3-M6 — Pesan gagal tidak jelas ("retry after the stated seconds", "answered 500", "No such layout.") dan toast terpotong
  di ponsel (agen 1 M6, agen 2 M2).
- Q3-M7 — Runbook migrasi belum punya parameter/pemeriksaan untuk `20261106_001` (agen 2 M1); tes hak akses tabel belum ada
  (agen 2 M3).
- Q3-M8 — R2-M3 sebagian: file broker gagal, Flow Timeline masih "Rp 0" dan garis nol sampai di-zoom (agen 5 M1).
- Q3-M9 — Peta: persamaan terpotong di panel kanan ≤ ~308 px (agen 5 M3); titik 0,0/0,0 di Nego disebut "Both
  accumulating" dan "−0.0%" muncul lagi (agen 5 M4 = Low lama "nama kuadran tanpa ambang").

**Low (ringkas)**
- Toolbar terlalu lebar di 1440 bila kedua panel terbuka, atau di 1024 dengan nama layout panjang (agen 5 L4, agen 1 L4).
- Daftar broker Flow Timeline yang diingat ditimpa pada saham tanpa broker itu; di saham tanpa data broker, Board/Investor
  tidak lagi tersimpan (agen 4 L3).
- Tanda minus "-" sisa di pop-out, Statistics, Flow Timeline, legend chart (agen 3 F2, agen 5 L3).
- Hint Broker summary/Top brokers tidak menyebut papan (agen 3 F3).
- ±6,00% / ±10,00% tampil, verdict tingkat bawah (agen 3 F1).
- Panel Filters tidak ikut baris sesudah resize (agen 5 L1).
- Tombol baris indikator tidak terjangkau Tab (agen 5 L2, M5 putaran 1).
- "Big Dist" terpotong 1 px di 260 px (agen 5 L5).
- Label chevron tanpa nama indikator; tinggi lipat 28–44 px (agen 4 L1, L2).
- 503/NUL/surrogate dijawab 503, bukan 422; README/dokumen inventaris tabel (agen 2 L1, L3, L4).
- Menu "No saved layouts yet" saat masih memuat; Save tanpa perubahan tetap menulis; toast menutupi menu (agen 1 L1, L5, L6).

**Tertutup dari putaran 2:** R2-M1, R2-M2, R2-M5, "Sep", Low peta, aria-label baris, Esc titik peta; Alt+B sesudah panel
diurutkan ulang menggulir ke atas.

### Tes
Terminal vitest 870/870; Backtest 88/88; tripwire OK; edge-bff `test_layouts.py` 18/18 (agen 2: suite penuh 305/306, satu
tes chat EDGE ponsel gagal juga di kode sebelumnya). Agen 2 menjalankan halaman build terhadap edge-bff asli dengan
login `edge_bff_login` di Postgres lokal: semua alur dan pesan sampai ke pengguna.

### Rekomendasi
Belum siap rilis. Perbaiki High dan Medium dulu (layout dan collapse), lalu QA ulang singkat pada area yang diubah.

## 10. Perbaikan sesudah putaran 3 (2026-11-06, go user)

**Kata user:** "1 dan 2, jalankan" — semua temuan High, Medium dan Low diperbaiki, lalu QA singkat area yang diubah.
Bukti: `verification/terminal_api/terminal_look/look_check6.mjs` (satu cek per temuan; API tiruan dengan kegagalan disuntik)
plus `look_check3/4/5.mjs` (regresi). ERRORS M355.

| Temuan | Perbaikan | Bukti (look_check6) |
|---|---|---|
| Q3-H1 collapse bertumpuk | tinggi panel terlipat = tinggi barisnya + margin, diamati ulang; baris pane satu baris di ≤ 1024 px, teks penuh di panel Filters | 3 panel terlipat: ponsel 32/32/32 px, 1440 24/24/50 px, 0 tumpuk |
| Q3-H2 dialog keluar layar | kolom `minmax(0,1fr)`, dialog `min-width:0` | nama 120 huruf di 390 px: dialog 16–374, Close 290–356 |
| Q3-M1 label sumbu panel terlipat | warna teks sumbu transparan saat terlipat | tangkapan `fold_d1440.png` |
| Q3-M2 panah/Esc/fokus | daftar panah dari input switch; Esc dan Tab-trap di tingkat dokumen; fokus kembali ke tombol Layout | panah: save→autosave→copy→rename→new→recent→open→save; trap true; fokus `layoutBtn` |
| Q3-M3 perubahan awal hilang | base = isi layout yang dibuka; beda sesudah settle = perubahan | "Target •", dirty true |
| Q3-M4 chart tanpa layout dibuang | konfirmasi "This chart is not saved as a layout. Discard it?" | indikator tetap 3 setelah Cancel |
| Q3-M5 nama tertimpa | ulang 409 memakai nama tersimpan | server tetap "Renamed elsewhere" |
| Q3-M6 pesan | kalimat dengan tindakan; 503 tanpa "stated seconds"; toast membungkus, gagal bertahan sampai ditutup | teks 503 dan 500 terbaca |
| Q3-M7 runbook migrasi | params + pemeriksaan + gladi lokal (DRYRUN 38/38, APPLY 23/23); tes hak akses tabel | `verification/terminal_api/layouts_migration/` |
| Q3-M8 file broker gagal | `failed()` → `redrawFlow` | ringkasan "—" langsung |
| Q3-M9 peta | persamaan membungkus; bagian 0,0% = datar ("No net flow"); tidak ada "−0.0%" | panel 260 px tanpa geser; Nego "No net flow · Top 3" |
| Low: toolbar | ≤ 900 px toolbar: Indicators/Events ikon saja (nama tetap untuk pembaca layar), tanpa hint tombol | 1440 dua panel: tanpa luber, Search 99 px, Full screen terlihat |
| Low: daftar broker diingat | ditulis hanya saat user memilih; kode yang tidak ada di ticker tetap disimpan; diterapkan sampai seluruh riwayat masuk | ZZ1, ZZ2 tetap |
| Low: tanda minus | satu "−" di Flow Timeline, Statistics, pop-out, tooltip, aria | ringkasan "−Rp" |
| Low: papan di hint; ±6,00% | hint menyebut papan; verdict dari rasio yang tampil | "Net · 03 Nov · Regular"; "… · Dist · Regular" |
| Low: Esc daftar Brokers; Tab ke tombol baris | fokus kembali ke tombolnya; setiap baris legend bisa di-Tab | fokus "board button"; Tab → `volEye` |
| Low: panel Filters sesudah resize | ditempatkan ulang sesudah baris diletakkan | — |
| Low: legend bergeser hover; "Big Dist" 1 px; judul panel; satuan lot; pencarian "rsi"; Undo di akhir | tinggi baris tetap 24 px; label rapat; judul satu baris; "Lot"/"lot per trade" dari satuan registry; cocok dari awal kata; Undo kembali ke posisi | Undo: FL12, FL23, FL21 |
| Low backend | NUL/surrogate/JSON dalam → 422; pesan 503 polos; README/docstring; PUBLIC dicek di provisioning; inventaris data | `test_layouts.py` 26 tes |

**Tidak diubah (bukan bagian draft):** label sumbu waktu "2"/"4" (pilihan tick lightweight-charts, sama di build lama).

**Tes:** Terminal vitest 870/870; Backtest 88/88; tripwire OK; edge-bff 162/162 (layouts, screener, edge, backtest,
terminal); oracle 457.498 nilai 0 selisih.

## 11. QA putaran 4 (singkat) dan perbaikannya (2026-11-06)

Dua agen (Sonnet, high) atas draft `c0f6fa2e`. Agen 1 (layout): FAIL minor, backend dan runbook PASS (gladi sendiri
DRYRUN 38/38, APPLY 23/23, ulang ditolak). Agen 2 (collapse, panel, Flow, minus): PASS dengan 2 Medium. Temuan putaran 3
tertutup kecuali yang tercatat di bawah; tidak ada angka salah (dicek lagi ke PostgreSQL).

| Temuan putaran 4 | Perbaikan | Bukti (`look_check7.mjs`) |
|---|---|---|
| Q4-M1 layout baru langsung "unsaved" | saat settle, setelan yang tidak disentuh user diambil seperti yang ditulis halaman | dirty false, 0 PUT |
| Q4-M2 perubahan saat settle tak tersimpan | setelan yang ditulis dalam 1,5 s sesudah klik/tombol = milik user (touched), dihitung sebagai perubahan | Ctrl+S → 1 PUT, style line |
| Q4-M3 autosave gagal lalu pindah layout | sebelum pindah: simpan bila Autosave; yang masih belum tersimpan selalu ditanya | "Discard the unsaved changes to “Alpha”?" |
| Q4-M4 dua tab | tab yang layout-nya diganti tab lain berhenti menyimpan dan memberi tahu | Alpha tak berubah, 0 PUT |
| Q4-L1 simpan saat keluar | token dibaca saat layout aktif | 1 PUT keepalive |
| Q4-L2 toolbar 1280/1024 dua panel | tingkat ringkas kedua (≤ 780 px bar) | luber 0 di 1024–1440, nama pendek/panjang |
| Q4-L3 "No saved layouts yet" saat memuat | "Loading…" sejak awal | "Loading…" |
| Q4-L4 Indicators tanpa tooltip | `title` | — |
| 409 tanpa tindakan | kalimat "Open it again (Open layout), then try again." | — |
| Agen 2 M1 chart harga mengecil saat sebagian dilipat | tinggi yang dilepas panel terlipat diberikan ke chart harga; panel terlipat tidak pernah lebih tinggi dari panel terbuka | 235 → 235 (tidak mengecil); 5 panel 0 tumpuk |
| Agen 2 M2 baris pane tetap terbungkus di 1280 dengan dua panel | bentuk sempit mengikuti lebar area chart (< 1000 px), bukan lebar layar | 1280 dua panel: 24/24/24 px |
| Agen 2 M3 judul panel terpotong | hint yang dipotong lebih dulu | 4 judul utuh |
| Agen 2 L1 baris membesar saat hover | panel terlipat mengikuti tinggi baris saat diam, bukan saat hover | 50 → 50 |
| Agen 2 L2 nama penuh di ponsel | panel Filters mengulang judul lengkap dan nilainya | "Net Buy Persistence · Cohort (…, 5D) · 100.0%" |
| Agen 2 L3 label peta bertumpuk, "+0", penanda tangga | label digeser bila bertumpuk; nol tanpa tanda; penanda jadi dua takik | label 121,5/132,5/143,5; "+0" 0 |
| Agen 2 L4 sumbu karangan saat gagal | skala Flow Timeline disembunyikan bila file gagal | `flow_failed.png` |

**Catatan tidak diubah:** pencarian "ma" tidak lagi menemukan "Moving Average" (sengaja: cocok dari awal kata; "sma"
menemukannya); tombol Layout di ponsel ada di ujung toolbar yang digeser (desain toolbar yang ada).

**Tes:** Terminal 870/870; Backtest 88/88; tripwire OK; edge-bff 162/162; oracle 0 selisih; `look_check3–7` tanpa galat.
