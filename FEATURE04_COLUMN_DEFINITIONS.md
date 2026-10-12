# Definisi setiap kolom Feature04 Technical Indicator

Tabel PostgreSQL: `public."Feature_04_Technical_Indicator"`. Ada **57 kolom**:
4 identitas, 1 harga penutupan sumber, 15 indikator numerik, 25 pola candlestick TA-Lib,
1 inside bar, 9 kolom SMI/swing, dan 2 metadata perhitungan.

Satu baris mewakili **satu asset type × ticker × tanggal perdagangan × timeframe Daily**.
Semua perhitungan memakai riwayat ticker itu sendiri, diurutkan dari tanggal paling
lama ke terbaru. Periode berarti jumlah candle yang tersedia, bukan hari kalender.
Tidak ada penggabungan riwayat antar ticker atau asset type, atau pengisian hari tanpa candle.

`asset_type` tidak berasal dari daftar ticker hardcode. Ticker yang ada di
`IDX_Stock_Universe` diklasifikasikan `equity`; ticker yang ada di
`Universe_Fixed_income` diklasifikasikan `bonds`. Ticker yang tidak ada atau ada pada
kedua universe ditolak agar tidak salah klasifikasi. Equity memakai
`Price_Stock_Indonesia_IDX`; bonds memakai `Price_Fixed_Income` khusus
`metric_type='price'` dan timeframe sumber `1D`, yang dinormalisasi menjadi `Daily`.

Ekstensi SMI/swing v3 pertama diuji untuk **BBCA**, lalu user menyetujui kelanjutan
untuk seluruh ticker pada 2026-10-11. Backfill v3 kini mencakup **844 ticker dan
1.318.633 candle Daily**, dari tanggal sumber terendah masing-masing ticker sampai
terbaru (cakupan keseluruhan 2018-01-02 sampai 2026-10-09). Seluruh baris memakai
versi v3; hasil BBCA dan indikator lama dipertahankan. Katalog aktif v3 menjelaskan
skema, dan `calculation_version` menjelaskan implementasi yang menghitung baris tersebut.
Bukti: [`SMI_ALL_TICKERS.md`](verification/feature04/SMI_ALL_TICKERS.md).
Ada 16.344 trigger historis. SMI tersedia pada 1.317.585 candle; 1.048 nilai awal
masih `NULL` karena rentang harga awal nol. Seluruh candle memiliki flag trigger 1/0,
dan SMI pada candle terakhir tersedia untuk setiap ticker.

Ekstensi lintas aset menambahkan **24 ticker bonds dan 60.409 candle Daily** dari
2016-01-01 sampai 2026-10-09, sehingga target berisi **1.379.042 baris**. Seluruh key
sumber price/1D bonds dan equity memiliki pasangan target tanpa key ekstra. Rumus,
warmup, SMI, dan arti flag tetap sama; lihat
[`BONDS.md`](verification/feature04/BONDS.md).

Migrasi terbaru mengganti nama fisik tabel ke `Feature_04_Technical_Indicator` dan
menambahkan `close` berdasarkan pasangan ticker dan `trade_date` yang sama persis pada
sumber sesuai `asset_type`. Bukti rename dan kecocokan nilai ada di
[`RENAME_CLOSE.md`](verification/feature04/RENAME_CLOSE.md).

## Cara membaca nilai

- `NULL` berarti nilai belum tersedia atau tidak berlaku menurut aturan kolom.
  Pada pola TA-Lib, warmup yang belum cukup juga `NULL`.
- `0` pada flag berarti candle **sudah dihitung** dan kondisi tidak terpenuhi.
  `break_swing_high` memakai **integer 1/0**, bukan boolean atau kode 100.
- Harga dan indikator dengan satuan harga mengikuti unit harga sumber masing-masing asset.
- `close` wajib tersedia dan merupakan salinan langsung harga penutupan sumber pada `trade_date`,
  bukan hasil kalkulasi indikator.
- Input OHLC yang tidak valid menghasilkan `NULL` untuk semua fitur pada baris itu
  dan mereset riwayat perhitungan berikutnya. Equity juga mewajibkan volume nonnegatif;
  bond boleh memiliki volume `NULL` karena formula Feature04 tidak memakai volume.
- Kolom bond hanya dihitung dari `Price_Fixed_Income` `price`/`1D` dengan
  `is_final=true`; timestamp bar sumber dan waktu penutupan market disimpan pada tabel
  harga. Kolom dihitung pada candle Daily yang sudah selesai. Nilai historis dapat berubah
  bila harga sumber dikoreksi dan riwayat dihitung ulang.

## Identitas dan metadata — 6 kolom

| Kolom | Tipe | Definisi dan penggunaan |
|---|---|---|
| `ticker` | text, wajib | Kode instrumen pada sumber/universe, misalnya `BBCA` atau ticker fixed income. Bagian primary key. |
| `trade_date` | date, wajib | Tanggal candle perdagangan menurut tanggal sumber IDX. Bagian primary key. Untuk `break_swing_high=1`, inilah tanggal trigger. Bukan tanggal peak lama atau waktu eksekusi backfill. |
| `timeframe` | text, wajib | Interval sumber, saat ini tepat `Daily`. Bagian primary key; bukan data intraday. |
| `asset_type` | text, wajib | Klasifikasi `equity` atau `bonds` dari membership universe saat kalkulasi. Bagian primary key dan batas partisi riwayat; tidak boleh ditentukan dari daftar ticker di kode. |
| `calculation_version` | text, wajib | Versi rumus, seed, dan library yang menghasilkan baris. Versi historis v2: `feature04-v2-talib0.6.8-c0.6.4`; seluruh hasil saat ini memakai v3 SMI: `feature04-v3-smi14-5-5-th40-talib0.6.8-c0.6.4`. Bukan fitur numerik untuk model. |
| `calculated_at` | timestamptz, wajib | Waktu UTC perhitungan terakhir yang mengubah payload baris. Rerun dengan hasil identik mempertahankan timestamp. Bukan bukti kapan data tersedia secara historis. |

## Harga sumber langsung — 1 kolom

| Kolom | Tipe / satuan | Definisi | Ketersediaan |
|---|---|---|---|
| `close` | double precision, wajib / unit harga sumber | Harga penutupan dari `Price_Stock_Indonesia_IDX.close` untuk equity, atau `Price_Fixed_Income.close` dengan `metric_type='price'` dan `Timeframe='1D'` untuk bonds. Dicocokkan tepat menurut `asset_type`, ticker, dan `trade_date`. | Setiap baris target; nilai sumber yang hilang/tidak valid menggagalkan kalkulasi ticker. |

## Indikator numerik — 15 kolom

Semua EMA pada bagian ini memakai **seed SMA dari N close pertama**, lalu
`EMA[t] = EMA[t-1] + 2/(N+1) × (close[t] − EMA[t-1])`.
Seed ini berbeda dari EMA internal SMI pada bagian berikutnya.

Nomor candle pertama tersedia dihitung mulai 1 pada awal riwayat valid atau setelah reset.

| Kolom | Tipe / satuan | Definisi | Pertama tersedia |
|---|---|---|---|
| `sma_20` | double precision / IDR | Rata-rata aritmetika 20 close terakhir; baseline harga pendek. | Candle 20 |
| `sma_50` | double precision / IDR | Rata-rata aritmetika 50 close terakhir; baseline harga lebih panjang. | Candle 50 |
| `ema_12` | double precision / IDR | EMA close periode 12, alpha `2/13`; komponen cepat MACD. | Candle 12 |
| `ema_26` | double precision / IDR | EMA close periode 26, alpha `2/27`; komponen lambat MACD. | Candle 26 |
| `rsi_14` | double precision / poin 0–100 | RSI dari gain/loss 14 perubahan close, dilanjutkan smoothing Wilder `1/14`. Mengukur momentum relatif. TA-Lib menghasilkan 0 bila gain dan loss sama-sama nol. | Candle 15 |
| `macd` | double precision / IDR | `ema_12 − ema_26` dari dua EMA yang tersimpan. Positif berarti baseline cepat di atas baseline lambat. Bukan hasil fungsi MACD TA-Lib yang memakai seed internal berbeda. | Candle 26 |
| `macd_signal` | double precision / IDR | EMA periode 9 atas MACD yang sudah valid. Seed adalah rata-rata sembilan MACD pertama; alpha `0,2`. | Candle 34 |
| `macd_histogram` | double precision / IDR | `macd − macd_signal`; selisih momentum terhadap baseline momentum yang dihaluskan. | Candle 34 |
| `atr_14` | double precision / IDR | Rata-rata Wilder 14 true range. `TR=max(high−low, abs(high−close sebelumnya), abs(low−close sebelumnya))`. Memerlukan close sebelumnya; mengukur rentang volatilitas, bukan arah harga. | Candle 15 |
| `bb_upper_20` | double precision / IDR | `SMA20 + 2 × standar deviasi populasi 20 close`, pembagi varians 20. Batas dispersi atas Bollinger. | Candle 20 |
| `bb_middle_20` | double precision / IDR | SMA20, sama persis dengan `sma_20`; garis tengah Bollinger. | Candle 20 |
| `bb_lower_20` | double precision / IDR | `SMA20 − 2 × standar deviasi populasi 20 close`. Batas dispersi bawah Bollinger. | Candle 20 |
| `adx_14` | double precision / poin 0–100 | ADX Wilder periode 14 dari directional movement, true range, dan DX. Mengukur **kekuatan tren**, bukan bullish/bearish. Contoh nilai 40 adalah hasil ADX, sedangkan periode tetap 14. | Candle 28 |
| `ema_50` | double precision / IDR | EMA close periode 50, alpha `2/51`; baseline harga menengah. | Candle 50 |
| `ema_200` | double precision / IDR | EMA close periode 200, alpha `2/201`; baseline harga panjang. Tetap `NULL` bila belum ada 200 candle valid. | Candle 200 |

Nilai harga mentah antar ticker tidak langsung setara untuk pemeringkatan. RSI/ADX
bukan probabilitas; crossing EMA/MACD atau sentuhan Bollinger tidak memberikan win rate.

## Pola candlestick TA-Lib — 25 kolom

Semua kolom berikut bertipe **integer nullable**, memakai OHLC historis dan pengaturan
candle default TA-Lib 0.6.8 / C 0.6.4. `0` berarti pola tidak terdeteksi setelah warmup;
`NULL` berarti belum cukup riwayat atau input tidak valid. Kode signed native dipertahankan:
umumnya `+100`/`−100`, tetapi beberapa fungsi dapat menghasilkan magnitudo lain seperti
80 atau 200. Magnitudo bukan tingkat keyakinan atau probabilitas.

Deskripsi berikut menjelaskan bentuk pola; batas body/shadow, kesetaraan, gap, dan panjang
relatif tetap mengikuti fungsi TA-Lib yang disebut. Pola dapat muncul bersamaan. Nama
pola tidak membuktikan pembalikan harga berikutnya, dan pola netral tidak boleh dianggap
bullish hanya karena kode library positif.

| Kolom | Fungsi | Definisi bentuk yang dikenali |
|---|---|---|
| `cdl_piercing` | CDLPIERCING | Dua candle: candle turun panjang, lalu candle naik yang membuka di bawah low sebelumnya dan menutup melewati tengah body turun tanpa sepenuhnya menutupinya. |
| `cdl_morning_star` | CDLMORNINGSTAR | Tiga candle: body turun panjang, body kecil yang gap ke bawah, lalu candle naik yang menembus body pertama. Penetration default 0,3. |
| `cdl_morning_doji_star` | CDLMORNINGDOJISTAR | Morning star dengan candle tengah berupa doji; penetration default 0,3. |
| `cdl_engulfing` | CDLENGULFING | Dua body berlawanan warna; body kedua melingkupi body pertama. Dapat mendeteksi bentuk bullish maupun bearish; kasus satu batas body sama dapat memakai kode native 80. |
| `cdl_3_white_soldiers` | CDL3WHITESOLDIERS | Tiga candle naik dengan close meningkat, open di dalam body sebelumnya, dan upper shadow pendek menurut setting library. |
| `cdl_hammer` | CDLHAMMER | Body pendek dekat bagian atas rentang, lower shadow panjang, upper shadow sangat pendek; posisi body juga diuji relatif terhadap candle sebelumnya. |
| `cdl_inverted_hammer` | CDLINVERTEDHAMMER | Body pendek, upper shadow panjang, lower shadow sangat pendek, dengan body gap ke bawah dari body sebelumnya. |
| `cdl_3_inside` | CDL3INSIDE | Tiga candle: candle pertama panjang, body kedua pendek di dalam body pertama, lalu candle ketiga berlawanan arah pertama dan menutup melewati open pertama. Berbeda dari `inside_bar` dua candle. |
| `cdl_3_outside` | CDL3OUTSIDE | Engulfing pada dua candle pertama, lalu candle ketiga melanjutkan arah candle engulfing dengan close lebih jauh. |
| `cdl_harami` | CDLHARAMI | Body kecil di dalam body candle panjang sebelumnya; varian tanda mengikuti konvensi library, termasuk magnitudo berbeda pada batas body yang sama. |
| `cdl_harami_cross` | CDLHARAMICROSS | Harami dengan candle kecil berupa doji di dalam body sebelumnya. |
| `cdl_dark_cloud_cover` | CDLDARKCLOUDCOVER | Candle naik panjang diikuti candle turun yang membuka di atas high sebelumnya dan menutup cukup dalam pada body naik, namun tetap di atas open sebelumnya. Penetration default 0,5. |
| `cdl_evening_star` | CDLEVENINGSTAR | Tiga candle: body naik panjang, body kecil yang gap ke atas, lalu candle turun yang menembus body pertama. Penetration default 0,3. |
| `cdl_evening_doji_star` | CDLEVENINGDOJISTAR | Evening star dengan doji pada candle tengah; penetration default 0,3. |
| `cdl_3_black_crows` | CDL3BLACKCROWS | Tiga candle turun dengan close menurun, open di dalam body sebelumnya dan lower shadow pendek, mengikuti candle naik sebelumnya menurut library. |
| `cdl_shooting_star` | CDLSHOOTINGSTAR | Body pendek dengan upper shadow panjang dan lower shadow sangat pendek; body gap ke atas dari body sebelumnya. |
| `cdl_hanging_man` | CDLHANGINGMAN | Body pendek di atas rentang dengan lower shadow panjang dan upper shadow sangat pendek; posisi body dekat bagian atas candle sebelumnya. |
| `cdl_doji` | CDLDOJI | Body sangat kecil dibanding ukuran candle historis menurut batas default library. Netral; bukan arah pembalikan dengan sendirinya. |
| `cdl_dragonfly_doji` | CDLDRAGONFLYDOJI | Doji dengan upper shadow sangat pendek dan lower shadow yang melampaui batas very-short library. |
| `cdl_gravestone_doji` | CDLGRAVESTONEDOJI | Doji dengan lower shadow sangat pendek dan upper shadow yang melampaui batas very-short library. |
| `cdl_marubozu` | CDLMARUBOZU | Body panjang dengan kedua shadow sangat pendek; warna body menentukan tanda kode. |
| `cdl_kicking` | CDLKICKING | Dua marubozu berlawanan warna dengan gap antar rentang candle; arah candle kedua menentukan varian bullish/bearish. |
| `cdl_rise_fall_3_methods` | CDLRISEFALL3METHODS | Lima candle: candle panjang, tiga candle kecil berlawanan arah dalam rentang pertama, kemudian candle searah pertama yang menutup melewati close pertama. |
| `cdl_mat_hold` | CDLMATHOLD | Lima candle lanjutan naik: candle naik panjang, candle kecil gap ke atas, dua candle kecil pullback terbatas, lalu candle naik yang melanjutkan gerakan. Penetration default 0,5. |
| `cdl_hikkake` | CDLHIKKAKE | Pola jebakan setelah inside bar dengan high/low bergerak ke satu sisi. Library dapat memberi kode awal ±100 dan kode konfirmasi ±200 pada penembusan dalam tiga candle berikutnya. |

Lookback dan parameter aktual tiap fungsi disimpan di
[`calculation_validation.json`](verification/feature04/calculation_validation.json).
Deteksi ini tidak identik dengan pewarnaan/nama pola pada setiap script TradingView.

## Inside bar — 1 kolom

| Kolom | Tipe | Definisi |
|---|---|---|
| `inside_bar` | integer nullable | **1** bila `high[t] < high[t−1]` dan `low[t] > low[t−1]`; **0** bila sudah ada pembanding valid namun kondisi tidak terpenuhi. Perbandingan strict: high atau low yang sama menghasilkan 0. `NULL` pada candle pertama atau sesudah reset karena belum ada pembanding. Membandingkan harga numeric asli, bukan harga yang dibulatkan. Label untuk candle saat ini; tidak menentukan arah breakout. |

## SMI dan state swing — 9 kolom

Sumber logika: [`HH.pine`](features/feature04/reference/HH.pine) yang diberikan user.
Parameter tetap: **K=14, D=5, EMA=5, threshold ±40**. Parameter ini merupakan konfigurasi
versi, bukan sembilan kolom tambahan lain.

```text
HH  = highest(high, 14)
LL  = lowest(low, 14)
rel = close − (HH + LL) / 2
SMI = 200 × EMA5(EMA5(rel)) / EMA5(EMA5(HH − LL))
```

Pada awal riwayat, HH/LL memakai candle yang sudah tersedia hingga maksimum 14 candle.
EMA internal SMI memakai **input pertama sebagai seed**, alpha `1/3`, kemudian
`EMA[t] = alpha × input[t] + (1−alpha) × EMA[t−1]`.
Tidak ada SMA seed atau warmup 14 candle yang dipaksakan untuk SMI. Pembagi nol menghasilkan
`NULL`. SMI bukan stochastic %K dan script tidak memiliki SMI signal-line terpisah.

| Kolom | Tipe | Definisi / aturan |
|---|---|---|
| `smi` | double precision nullable | Nilai SMI dalam poin, umumnya −100 sampai +100, dari rumus di atas. `NULL` jika belum dihitung, input invalid, atau pembagi nol. |
| `tracking_high` | integer nullable | Status mencari peak setelah seluruh blok candle saat ini diproses. Mulai 1 ketika SMI crossover di atas +40; menjadi 0 ketika SMI crossunder di bawah +40. Awal valid 0; ticker belum dihitung `NULL`. SMI tepat +40 tidak langsung mengakhiri tracking. |
| `tracking_low` | integer nullable | Status mencari trough. Mulai 1 ketika SMI crossunder di bawah −40; menjadi 0 ketika SMI crossover di atas −40. Awal valid 0; ticker belum dihitung `NULL`. |
| `temp_high` | double precision nullable / IDR | Kandidat peak: mulai dari high candle +40 upcross, lalu naik hanya ketika high lebih tinggi selama SMI > +40 dan tracking aktif. `NULL` saat tracking tidak aktif atau setelah peak dikonfirmasi. High candle konfirmasi tidak masuk kandidat. |
| `temp_high_bar` | integer nullable | Indeks candle kandidat `temp_high`, mulai **0** pada tanggal sumber paling lama ticker tersebut. High yang sama mempertahankan indeks pertama. `NULL` bersama `temp_high`; ini bukan tanggal atau indeks universal TradingView. |
| `temp_low` | double precision nullable / IDR | Kandidat trough: mulai dari low candle −40 downcross, lalu turun hanya ketika low lebih rendah selama SMI < −40 dan tracking aktif. Dikosongkan menjadi `NULL` pada konfirmasi. Low candle konfirmasi tidak masuk kandidat. |
| `temp_low_bar` | integer nullable | Indeks candle kandidat `temp_low`, mulai 0 pada awal riwayat ticker. Low yang sama mempertahankan indeks pertama. `NULL` bersama `temp_low`. |
| `last_swing_high` | double precision nullable / IDR | Harga peak terakhir yang **sudah dikonfirmasi** saat SMI crossunder dari ≥ +40 ke < +40 ketika tracking aktif. Tersedia mulai tanggal konfirmasi dan dibawa ke candle berikutnya hingga diganti peak baru. `NULL` sebelum konfirmasi pertama. Tidak dikosongkan setelah breakout. |
| `break_swing_high` | integer nullable | **1** bila ada level terkonfirmasi pada candle kini dan sebelumnya, `close[t] > last_swing_high[t]`, serta `close[t−1] <= last_swing_high[t−1]`. **0** pada candle valid lainnya, termasuk sebelum konfirmasi pertama. `NULL` hanya untuk ticker belum dihitung atau input invalid. Tanggal trigger adalah `trade_date` pada baris bernilai 1. |

State di atas disimpan **setelah** seluruh blok script berjalan pada candle saat ini.
Ketika peak dikonfirmasi, `last_swing_high` diperbarui dan `temp_high`/`temp_high_bar`
langsung menjadi `NULL` pada baris yang sama. Swing low hanya ditampilkan sebagai label
dalam script; tidak ada `last_swing_low` yang disimpan.

Beberapa rincian script yang memengaruhi interpretasi:

- Label TradingView ditempatkan pada candle peak/trough yang lebih lama, tetapi baru
  diketahui pada candle konfirmasi. Database tidak menulis ulang baris peak lama
  dengan pengetahuan dari candle konfirmasi.
- Crossover membandingkan level **masing-masing tanggal**, bukan mengganti level
  kemarin dengan level baru hari ini. Bila swing high baru lebih rendah, perubahan
  level dapat ikut menyebabkan trigger. Pada konfirmasi pertama, level kemarin
  belum tersedia sehingga belum dapat menghasilkan crossover.
- Wick di atas level tanpa close yang memenuhi syarat tidak menghasilkan trigger.
  Close sama persis dengan level belum merupakan crossover ke atas.
- Trigger tidak mensyaratkan SMI > +40 pada tanggal breakout, dan level tidak ditandai
  sudah digunakan. Harga turun lalu menembus lagi dapat menghasilkan trigger ulang.
- Bila SMI menyentuh tepat +40 lalu crossover ke atas lagi, script menginisialisasi
  ulang kandidat high. Perilaku analog berlaku pada −40 untuk kandidat low.
- Indeks bar bergantung pada riwayat sumber yang tersedia. Penambahan tanggal lebih
  lama dapat menggeser indeks. Tidak ada rekonstruksi alert intrabar dari OHLC Daily.

## Verifikasi dan batas penggunaan

Rumus, isolasi ticker, urutan state, threshold, crossover level dinamis, tidak adanya
backdating, dan idempotensi diuji dalam kode dan dibaca kembali dari PostgreSQL.
Laporan seluruh ticker: [`SMI_ALL_TICKERS.md`](verification/feature04/SMI_ALL_TICKERS.md).
Laporan uji awal BBCA: [`SMI_BBCA.md`](verification/feature04/SMI_BBCA.md).
Kontrak engine: [`FEATURE04_TECHNICAL_INDICATOR.md`](FEATURE04_TECHNICAL_INDICATOR.md).

Kesamaan numerik dengan chart/export TradingView **belum diverifikasi** karena seed awal,
riwayat chart, dan vintage penyesuaian harga harus cocok. Perhitungan bersifat kausal pada
snapshot sumber yang ada; kelayakan point-in-time untuk training belum dibuktikan karena
riwayat ketersediaan/revisi sumber belum lengkap. Tidak ada klaim profitabilitas, alert
otomatis, atau scheduler dalam ekstensi ini.
