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
