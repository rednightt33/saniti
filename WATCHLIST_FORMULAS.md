# Rumus Watchlist

Dokumen ini menjelaskan setiap angka di halaman **Watchlist** (EDGE) dalam bahasa sederhana, dengan contoh nyata dari dev
(harga 13 Nov 2026, data broker 9 Nov 2026). Keputusan user 2026-11-16: halaman dibuat **seringan mungkin, tanpa hitungan
baru** ("selight as possible yang mana tidak perlu ada calculation lagi"). Karena itu hampir setiap angka adalah nilai
yang **sudah tersimpan** di database, dibaca apa adanya. Satu-satunya hitungan adalah jarak harga ke EMA (satu pembagian
di baris yang sama).

<!-- explained-for: watchlist.py=0fd9f284452665831e3feda5b1cbb59f, app/watchlist.py=943ecc862a6c5a628be9b099f75a90de -->

## 1. Dari mana angkanya datang

Setiap hari publisher menulis dua file. `watchlist-stocks` berisi angka untuk **semua saham biasa** (862 saham di
daftar universe, `IDX_Stock_Universe` dengan `Security Type` = stock). `watchlist-radar` berisi hanya badge Radar (bagian
5), karena Radar adalah halaman dengan hak akses sendiri: server EDGE mengirim file ini hanya ke akun yang boleh membuka
Radar (`radar.view`; EXEC-MU-ACCOUNTS fase 3d). Akun tanpa Radar tetap melihat semua angka, hanya tanpa badge dan filter
Radar. Kedua file sama untuk semua pengguna yang boleh membacanya. Isi list
masing-masing pengguna disimpan terpisah di server (`edge_bff.watchlist_lists` dan `watchlist_items`). Halaman lalu
mencocokkan saham di list dengan baris di file.

Satu lari publisher membaca: satu tanggal Feature 01 dan Feature 04, satu tanggal broker Feature 06, 30 tanggal harga,
aksi korporasi 30 hari ke depan, dan satu tanggal Radar. Di dev semuanya selesai dalam 3,1 detik saat cache dingin
(di bawah 0,1 detik saat hangat), 17–29 ribu halaman memori, sebagian besar dari cache
(`verification/watchlist/EXPLAIN_20261116.txt`). Ini **bukan** update besar, jadi tidak perlu restart Postgres.
File dibangun ulang hanya bila isinya berubah (stempelnya adalah isi file itu sendiri).

## 2. Dua tanggal

- **Tanggal harga** ("Prices to …"): tanggal pasar terbaru yang **lengkap**: setiap saham yang punya penutupan final
  hari itu juga punya baris Feature 01, dan setiap baris Feature 01 punya baris Feature 04 (jumlahnya dihitung dari
  data hari itu sendiri; di dev ketiganya sama setiap hari, mis. 836 pada 13 Nov). Kalau worker Feature masih menulis
  hari terbaru, file memakai hari lengkap sebelumnya, tidak pernah campuran dua hari. Diperiksa satu tanggal per kali,
  sampai 10 tanggal ke belakang; tanpa tanggal lengkap, file sebelumnya tetap dipakai.
- **Tanggal broker** ("Broker data to …"): tanggal terbaru data asing (Feature 06, papan Regular). Biasanya beberapa
  hari di belakang tanggal harga, karena ronde broker dijalankan terpisah. Contoh: harga 13 Nov, broker 9 Nov. Setiap
  angka asing di halaman diberi tanggal ini.

**Mode contoh (EXEC-MU-ACCOUNTS 3e, keputusan user 2026-11-21; ERRORS M527).** Pengunjung yang belum login dan paket
gratis melihat Watchlist sebagai contoh dengan **data terbaru**, sama seperti Overview (user: "Untuk table watchlist
nggak apa-apa pakai data latest saja", lalu "Benar opsi B"). Tidak ada file contoh yang disimpan: setiap kali file
harian Watchlist terbit, edge-bff memotongnya sendiri (`apps/edge-bff/app/examples.py`, `watchlist_view`):
- **Daftarnya:** satu list "LQ45" berisi anggota LQ45 **hari ini**, sebagaimana diterbitkan Overview (`overview-meta`,
  dari tabel `Stock_List_Member`). Kalau daftar LQ45 diperbarui di database (putaran update Stockbit), contoh ikut
  berubah sendiri. Per 21 November 2026 isinya 45 saham, tercatat sejak 10 November.
- **Kolomnya:** sama dengan halaman asli saat dibuka, yaitu harga, 1D, 1M, garis 30 sesi, dan empat indikator bawaan
  (RSI, Volume, From 60D high, Foreign 5D). Nilai indikator lain kosong, karena menambah indikator adalah klik.
- **Tanggalnya:** tanggal harga ikut file harian (per 21 November: Jumat 20 November). Foreign 5D memakai tanggal data
  broker sendiri (per 21 November: Senin 9 November), jadi halaman menampilkan dua label tanggal, sama seperti untuk
  pengguna berbayar.
- **Yang tidak ikut:** aksi korporasi mendatang (pilihan bawaan pembuatnya, bukan keputusan user, dan masih menunggu
  jawaban user; paket gratis Terminal juga tidak memuat data event) dan badge Radar (butuh hak Radar).
- **Kalau datanya tidak cocok:** kalau daftar LQ45 tidak ada di Overview, muncul dua kali, kosong, atau berisi saham yang
  tidak ada di file Watchlist, contoh menolak tampil (`EXAMPLE_UNAVAILABLE`) dan tidak pernah menampilkan daftar lain.
  Ini pelajaran dari rencana lama: daftar LQ45 per 30 Oktober tidak bisa diketahui dari riwayat keanggotaan, karena
  riwayat itu baru mulai 10 November, padahal evaluasi BEI berlaku 2 November (ELSA dan SMGR masuk, CUAN dan SCMA
  keluar). Fungsi `build` dengan `as_of` masih ada di publisher dan teruji, tetapi kini tidak dipakai contoh mana pun.

## 3. Harga, 1D, 1M dan Trend

- **Last** = harga penutupan pada tanggal harga (Feature 01 `close`). BBCA: 5.500.
- **1D** = `return_1d_pct` Feature 01. BBCA: +0,46%.
- **1M** = `return_20d_pct` Feature 01, yaitu 20 sesi bursa (kira-kira satu bulan). BBCA: +6,28%.
- **Trend** = garis 30 penutupan terakhir (tabel harga, penutupan final). Hijau bila penutupan terakhir ≥ penutupan
  pertama, merah bila lebih rendah. BBCA: dari 6.175 (5 Okt) ke 5.500 (13 Nov), jadi merah, meskipun 1M-nya positif
  (1M hanya 20 sesi, Trend 30 sesi).

## 4. Indikator (14 pilihan)

Daftar indikator datang dari file itu sendiri (bagian `catalog`), bukan ditulis tetap di halaman. Indikator baru cukup
ditambahkan di publisher, dan halaman ikut menampilkannya. Tabel lengkapnya ada di bagian bawah dokumen. Contoh BBCA:

| Indikator | Arti sederhana | BBCA |
|---|---|---|
| RSI (14) | kekuatan naik-turun 14 sesi, skala 0–100; ≥ 70 sering disebut jenuh beli | 53,6 |
| MACD histogram | selisih garis MACD dengan sinyalnya (satuan harga) | 95,3 |
| ADX (14) | kekuatan tren, tanpa arah | 20,1 |
| Price vs EMA 50 | (harga ÷ EMA 50 − 1) × 100, dari baris Feature 04 yang sama | −2,1% |
| Price vs EMA 200 | sama, terhadap EMA 200 | −14,1% |
| Return 5D / 3M | `return_5d_pct` / `return_60d_pct` Feature 01 | +5,8% / −14,1% |
| Volume vs 20D average | volume hari ini ÷ rata-rata 20 sesi | 0,7× |
| Volatility 20D | volatilitas tahunan 20 sesi | 59,5% |
| From 60D high | posisi harga di bawah penutupan tertinggi 60 sesi | −18,8% |
| Foreign net 1D / 5D / 20D | beli asing dikurangi jual asing, papan Regular, pada tanggal broker | +Rp 523,1 B / +Rp 1,2 T / −Rp 3,3 T |
| Foreign net 5D rank | peringkat net asing 5 hari terhadap 252 nilai sebelumnya milik saham itu sendiri (sudah tersimpan di Feature 06) | P95 |

Bila sebuah saham tidak punya baris pada tanggal itu (misalnya baru tercatat), nilainya kosong ("—"), tidak pernah ditebak.

Bawaan list baru: RSI, Volume, From 60D high, Foreign 5D. Kartu menampilkan 4 indikator pertama; Tabel menampilkan semua
yang dipilih (maksimal 8).

## 5. Badge dan filter

- **Radar**: saringan Radar yang dipenuhi saham pada **tanggal Radar terbaru**, dibaca dengan pengaturan bawaan halaman
  Radar (level Standard, gerbang Broad), versi aturan yang sama dengan halaman Radar (`feature_07_rule_version()`), dan
  untuk S6Δ pada varian bawaannya (Ratio). Selama pengisian pertama Radar berjalan, file tidak diterbitkan ulang. Jadi badge menunjukkan apa yang
  terlihat saat halaman Radar dibuka. Contoh 9 Nov: BBCA lolos S6; DKFT lolos S6. Di dev ada 102 saham yang lolos minimal
  satu saringan. Filter "Radar" menampilkan hanya saham di list yang punya badge ini. Badge, nama saringan dan tanggal
  Radar datang dari file `watchlist-radar`; akun yang tidak boleh membuka Radar tidak menerima file itu, jadi tidak
  melihat badge maupun tombol filter Radar (contoh: paket tanpa `radar.view` membuka list berisi BBCA: angka BBCA tampil
  lengkap, badge "Radar S6" tidak). Publikasi lama (sebelum fase 3d) masih memuat badge di `watchlist-stocks`; halaman
  membacanya dari sana sampai publikasi berikutnya.
- **Aksi korporasi**: RUPS, public expose, dividen (tanggal ex), right issue, waran dan lainnya dengan tanggal **sesudah
  tanggal harga sampai 30 hari kemudian**, dibaca dari `idx_event_annotation` (keluarga `CORPORATE_ACTION`), sumber
  yang sama dengan penanda event di grafik Terminal, jadi kedua halaman selalu menunjukkan acara yang sama. Contoh: AMMN
  "RUPS 17 Nov", PGAS "Public expose 19 Nov". Data ini ikut ronde Stockbit; halaman menulis tanggal terakhir diambil. Filter "Corporate action" menampilkan
  hanya saham di list yang punya acara dalam jendela ini.

Kedua filter hanya mengubah tampilan list yang sedang dibuka, tidak mengubah isi list.

## 6. List dan batasnya

List disimpan di server per akun, jadi sama di perangkat mana pun, dan akun lain tidak bisa membaca atau mengubahnya. Akunnya selalu akun yang sedang masuk (sejak EXEC-MU-ACCOUNTS Fase 1 dibaca dari sesi itu, bukan dari pengaturan server); batas dan angkanya tidak berubah.
Sejak EXEC-MU-ACCOUNTS Fase 3a, halaman ini dan datanya perlu hak `watchlist.view` dari paket akun. Batas tiap akun
adalah angka paketnya (`watchlist.lists`, `watchlist.per_list`, `watchlist.indicators`), tetapi tidak pernah lebih dari
angka di tabel di bawah, yang tetap menjadi plafon server. Paket berbayar saat ini memakai angka yang sama (20, 50, 8),
dan halaman menampilkan angka milik akun itu sendiri. Contoh: akun dengan batas paket 10 list tidak bisa membuat list
ke-11; akun dengan batas 30 tetap berhenti di 20. Saklar multi-user masih mati, jadi akun pemilik memakai angka tabel.
Bintang di Screener memakai list pertama (keputusan 2A) dan ikut perlu `watchlist.view`. Bila akun belum punya list,
bintang hanya membuat list pertama selama batas list akun itu minimal 1. Batasnya (tabel di bawah) dijaga server. Setiap penolakan
menyebut batas mana yang tercapai dan cara memperbaikinya. Sejak fix round re-check R2-39, batas list, saham per list dan
indikator per list adalah batas paket: server menjawab 403 `LIMIT_REACHED` dengan nama hak paketnya (misalnya
`watchlist.per_list`), angka milik akun dan angka yang diminta, dan kalimatnya, misalnya "You have reached your plan's
limit for Tickers per watchlist (50). Remove one you no longer need, or upgrade the plan." Memilih nol indikator bukan
batas paket: itu isian yang tidak sah (422 `INVALID_INPUT`). Undo hapus list memakai isi list menurut server saat dihapus, dan
mengembalikannya ke posisi semula. Nilai yang tampil sebagai nol (mis. "0.0%", "Rp 0") tidak diberi warna.

<!-- watchlist-live:start -->

Ditulis oleh `scripts/watchlist_formulas_doc.py --write` dari kode di repo; jangan diedit dengan tangan.

| Konstanta (`apps/terminal-publisher/watchlist.py`) | Nilai | Arti |
|---|---|---|
| `SCHEMA` | 1 | versi format file |
| `TREND_SESSIONS` | 30 | jumlah penutupan di garis Trend (sesi bursa) |
| `EVENT_DAYS` | 30 | aksi korporasi sesudah tanggal harga (hari kalender) |
| `RADAR_LEVEL` | standard | level Radar untuk badge dan filter (bawaan halaman Radar) |
| `RADAR_GATE` | broad | gerbang Radar untuk badge dan filter (bawaan halaman Radar) |
| `DEFAULT_INDICATORS` | rsi, volr, dd60, fn5 | indikator bawaan list baru (empat pertama tampil di kartu) |

| Kunci | Nama di halaman | Kelompok | Satuan | Tanggal | Warna tanda | Kolom sumber |
|---|---|---|---|---|---|---|
| `rsi` | RSI (14) | Technical | index | harga | tidak | Feature 04 rsi_14 |
| `macdh` | MACD histogram | Technical | price | harga | ya | Feature 04 macd_histogram |
| `adx` | ADX (14) | Technical | index | harga | tidak | Feature 04 adx_14 |
| `ema50` | Price vs EMA 50 | Technical | pct | harga | ya | Feature 04 close / ema_50 - 1 |
| `ema200` | Price vs EMA 200 | Technical | pct | harga | ya | Feature 04 close / ema_200 - 1 |
| `r5d` | Return 5D | Price & volume | pct | harga | ya | Feature 01 return_5d_pct |
| `r3m` | Return 3M | Price & volume | pct | harga | ya | Feature 01 return_60d_pct |
| `volr` | Volume vs 20D average | Price & volume | ratio | harga | tidak | Feature 01 volume_ratio_20d |
| `vol20` | Volatility 20D | Price & volume | pct | harga | tidak | Feature 01 volatility_20d_ann_pct |
| `dd60` | From 60D high | Price & volume | pct | harga | tidak | Feature 01 drawdown_60d_pct |
| `fn1` | Foreign net 1D | Foreign flow | rp | broker | ya | Feature 06 foreign_net_1d |
| `fn5` | Foreign net 5D | Foreign flow | rp | broker | ya | Feature 06 foreign_net_5d |
| `fn20` | Foreign net 20D | Foreign flow | rp | broker | ya | Feature 06 foreign_net_20d |
| `fp5` | Foreign net 5D rank | Foreign flow | rank | broker | tidak | Feature 06 foreign_net_percentile_5d_base252d |

| Batas (`apps/edge-bff/app/watchlist.py`) | Nilai | Arti |
|---|---|---|
| `LISTS` | 20 | list per akun |
| `PER_LIST` | 50 | saham per list (juga batas bintang Screener) |
| `INDICATORS` | 8 | indikator per list |
| `NAME_CHARS` | 40 | huruf nama list |

| Kode | Sidik jari (md5) |
|---|---|
| `watchlist.py` | `0fd9f284452665831e3feda5b1cbb59f` |
| `app/watchlist.py` | `943ecc862a6c5a628be9b099f75a90de` |

<!-- watchlist-live:end -->
