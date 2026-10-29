# Ringkasan: EDGE untuk user eksternal di semua tab (rencana, belum dijalankan)

Rencana lengkap: verification/edge_multiuser/AUDIT.md
Belum ada yang diubah di kode, Railway, atau database. Dicek ulang 28 Oktober sekitar 19:10 UTC.

**Keadaan sekarang.** EDGE masih dibuat untuk satu orang: satu login, satu pemilik data (`edge-private`). Datanya sudah
dipisah per pemilik, tetapi semua halaman masih memakai pemilik yang tetap.

**Yang bermasalah begitu ada user kedua**
1. Chat AI (Monitor) memproses satu pesan untuk semua orang. Satu pesan rata-rata 2-3 menit, jadi user lain antre.
2. Backtest menjalankan satu job untuk semua orang, menurut urutan datang. User yang mengantrekan 3 job membuat yang lain menunggu.
3. Terminal memakai satu akun untuk semua orang, dan kuotanya sedang dimatikan sementara. Fitur aset yang baru menambah
   jumlah unduhan per grafik (sampai 3 ticker), jadi kuota per user perlu dihitung per ticker, bukan per file.
4. Mode "Claude (manual)" bisa memperlihatkan pertanyaan user lain. Ini harus ditutup paling dulu.
5. Lima kali salah sandi oleh siapa pun bisa mengunci login semua orang.
6. Biaya AI tidak dibatasi per user. Satu user bisa menghabiskan saldo OpenRouter untuk semua.
7. Izin data (harga dari TradingView, broker summary Stockbit, corporate action, insider, logo) belum tercatat. Ini penghalang utama.

**Rencana 6 tahap** (setiap tahap baru jalan setelah "go" Anda)
- Tahap 1, pengamanan: tutup jalur "manual", batas salah sandi per akun, bersihkan data browser saat logout. Tidak ada perubahan yang terlihat.
- Tahap 2, akun user: undangan oleh admin, pemilik diambil dari login. Akun Anda sekarang menjadi admin dan riwayatnya tetap.
- Tahap 3, akun Terminal per user dan akun khusus untuk worker. Kuota per orang berlaku lagi.
- Tahap 4, keadilan dan anggaran: beberapa pesan AI bisa diproses bersamaan, giliran Backtest bergantian antar user,
  ada anggaran harian per user (AI, Backtest, Screener), dan proses latar dipisah ke service sendiri.
- Tahap 5, privasi dan izin data: sumber yang belum diizinkan tidak tampil untuk user eksternal; ada kebijakan simpan dan
  hapus data, halaman privasi dan syarat penggunaan.
- Tahap 6, siap luncur: environment, backup database, domain sendiri, uji beban, lalu undangan user pertama.

**Biaya (perkiraan)**
- Sekarang sekitar USD 33 per bulan. Hampir semua biaya per user adalah biaya AI: sekitar USD 6 per user per bulan; selain AI hanya USD 0,1.
- Perkiraan total: 10 user sekitar USD 115/bulan, 50 user sekitar USD 415, 200 user sekitar USD 1.445.
  Tanpa chat AI untuk user eksternal: sekitar USD 50, 80, dan 140.
- Batas USD 0,50 per user per hari (sekitar 16 pesan) membuat biaya AI paling tinggi USD 10,5 per user per bulan.

**Keputusan yang paling mendesak** (daftar lengkap MU1-MU26 ada di rencana)
- MU1: setujui rencana ini dan beri "go" untuk Tahap 1 saja.
- MU2: tanyakan izin data ke TradingView, Stockbit, dan IDX/KSEI. Rekomendasi: belum ada user eksternal sebelum ada jawaban tertulis.
- MU6: apakah chat AI dibuka untuk user eksternal? Rekomendasi: buka dengan batas harian, kalau izin datanya sudah jelas.
- MU5: perkiraan jumlah user harian dan yang memakai bersamaan, agar kapasitas dan biaya bisa dihitung.
- MU20: untuk uji tertutup (sekitar 10 orang) cukup di dev dengan aturan deploy ketat. Sebelum peluncuran terbuka atau berbayar, pakai environment produksi (sekitar +USD 30-35/bulan).
