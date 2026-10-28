# Ringkasan: arsitektur multi-user untuk Terminal, Backtest dan Screener (2026-10-28)

Read-only: tidak ada perubahan di repository, Railway, atau database. AI Orc tidak disentuh. Detail: `RUNTIME.md` (folder sama).
Bantuan dari Anda: buka Terminal dengan `?perf=1` sekali dari Indonesia, supaya waktu dari sisi user nyata terukur.

**Bentuk dasar.** Satu "pool" per service untuk semua user; setiap user dipisah lewat `owner_key` (sekarang satu owner,
nanti banyak). Bukan satu copy service per user: ketiga tab memakai data pasar yang sama, jadi copy per user hanya mengulang
download dan hitungan, membuat user menunggu 15-25 detik tiap kembali, dan 10-70× lebih mahal saat user aktif bersamaan.

**Kondisi sekarang.** Screener sedang dibangun dengan pola ini (antrean adil per user, batas CPU per user P33, cache hasil
bersama). Backtest belum siap: satu job dan satu preview sekaligus untuk seluruh EDGE, urut kedatangan; run tunggal yang
hitungannya 0,5 detik butuh 5,5-5,9 detik, kebanyakan menunggu polling. Terminal murah dan cepat per user, tetapi semua user
dan dua worker masih satu akun terminal-api, dengan kuota dimatikan sementara.

**Temuan baru.** Worker Backtest dan semua user berbagi satu akun terminal-api. Kalau Backtest diperbesar sebelum worker
punya akun sendiri (T1) atau sebelum perencanaan tanpa grant (B7), gerbang data macet di sekitar 60 user bersamaan dan ikut
memperlambat Terminal. Jadi T1 dulu.

**Biaya per bulan** (perkiraan; tiga tab plus bagiannya di edge-bff; di luar AI dan biaya dasar Postgres): sekitar
USD 22 / 28 / 56 untuk 10 / 50 / 200 user bersamaan (±33 / 167 / 667 user harian). Biaya tetap ±USD 19-21; tambahan per user
harian USD 0,04-0,09. Pos terbesar: dua replika Screener di memori (USD 12-24). Desain Backtest sekarang: ±USD 13 / 21 / 49,
dan tidak sanggup melayani 50 atau 200 user.

**Target waktu** (sandbox AS; dari Indonesia belum pernah diukur), dijaga di 10, 50 dan 200 user (thread dulu, baru
replika): ganti ke ticker yang sudah ada di browser 1,8-2,5 → ≤ 0,9 detik; backtest tunggal 5,5-5,9 → ≤ 2 detik; portofolio
12 saham dengan flow 10,8 → ≤ 3 detik; screen setelah diedit p95 ≤ 2 detik; preview p95 ≤ 1 detik.

**Akurasi.** Satu celah ada sekarang: halaman Terminal tetap menggambar file yang checksum-nya tidak cocok (T7). Screener
membaca daftar ticker dari kunci tetap (T5). Publisher di branch ini jangan di-deploy sebelum commit content-key masuk (R1).
Hasil yang sama dikunci dengan tes, juga saat dihitung paralel, dari cache, atau di replika lain.

**Urutan:** (0) ukur dulu; (1) bersama Screener: T1, T3, T5, T7, healthcheck, cek R1; (2) Backtest: B1+B2, lalu K thread,
klaim adil, deploy aman, lalu sisanya; (3) Terminal: satu grant per buka, tampil dari cache dulu; (4) sebelum user eksternal
pertama: akun per user, kuota, replika kedua.

**Keputusan (RT1-RT15 di `RUNTIME.md` §12), yang terpenting:**
- RT1 prinsip bersama (setuju); RT2 "go" Fase 0 + 1 bersama Screener; RT3 target waktu di atas;
- RT5 batas per user dibangun sekarang dengan nilai longgar, nilainya ditetapkan sebelum user eksternal;
- RT10 dua replika terminal-api saat user eksternal pertama;
- RT14 service tetap menyala (tidak di-sleep): hemat paling banyak USD 8, tetapi user pertama menunggu 15-25 detik.
