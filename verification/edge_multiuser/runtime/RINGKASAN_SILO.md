# Ringkasan untuk user: satu service per user atau satu service bersama

## Duplikat service per user (Screener, Backtest, Terminal), 2026-10-28

**Pertanyaan:** kalau service yang tidak dipakai tidak kena biaya, apakah sebaiknya service diduplikat satu per user?
**Jawaban:** tidak. Satu service bersama untuk semua user, dengan pemisahan per user di dalamnya, lebih cepat, lebih
aman untuk akurasi, dan biayanya sama atau lebih murah.

- Benar: service yang "tidur" tidak ditagih CPU dan memori (dicek di catatan pemakaian Railway: service kita yang tidur
  hanya tercatat sekitar 4 % dari memorinya). Tetapi itu sifat fitur tidur, bukan duplikasi: service bersama juga bisa
  tidur. Saat ini belum ada service EDGE yang tidur.
- Salinan per user harus bangun dan memuat data setiap kali user mulai memakai. Screener butuh sekitar 20-27 detik
  sebelum hasil pertama; service bersama yang menyala menjawab dalam 0,003-0,26 detik. Backtest: job pertama sekitar
  5 detik, lawan 0,3 detik.
- Biaya per bulan (perkiraan, 10 / 50 / 200 user): salinan per user USD 3,5 / 12,7 / 48 dengan tunggu di setiap sesi;
  service bersama menyala terus USD 16 / 16 / 18 tanpa tunggu; service bersama yang tidur malam dan akhir pekan
  USD 7 / 7 / 9. Salinan per user hanya lebih murah di bawah sekitar 26-65 user, paling banyak hemat USD 12 sebulan.
- Batas Railway: paling banyak 100 service per project (terpakai 28) dan 25 service baru per hari, jadi salinan per user
  mentok sebelum 50 user. Koneksi database untuk Terminal per user sudah habis di 10 user.
- Akurasi: dengan puluhan salinan, data dan versi program bisa berbeda antar user tanpa ketahuan (misalnya satu salinan
  gagal memperbarui data dan terus menampilkan data kemarin). Service bersama hanya punya 2 salinan Screener yang dicek.
- Operasional: setiap rilis berarti deploy ulang puluhan sampai ratusan service; kunci rahasia, pengaturan dan
  pemantauan ikut berlipat.

**Rekomendasi:**
1. Screener, Backtest dan Terminal: satu service bersama, dengan antrean yang adil, batas pemakaian dan identitas per
   user. Terminal sudah per user karena hitungannya berjalan di browser masing-masing.
2. Saat peluncuran: service menyala terus. Menidurkannya di luar 08:10-22:10 WIB hari bursa hanya hemat sekitar USD 8,6
   sebulan, tetapi user pertama di malam hari atau akhir pekan menunggu 14-27 detik, dan programnya harus diubah dulu.
   Bisa dinyalakan nanti setelah diukur.
3. Salinan khusus hanya untuk pengecualian: user berbayar atau berat mendapat mesin Backtest sendiri (sekitar USD 4
   sebulan), atau ada kontrak yang mewajibkan mesin sendiri.

**Yang diukur berikutnya di dev:** waktu start Screener yang sebenarnya di Railway; waktu bangun service berukuran nyata
dan seberapa sering permintaan pertama gagal; uji beban banyak user. Yang membuat service baru perlu "go" dari Anda.
**Keputusan untuk Anda:** setuju satu service bersama, bukan per user? Setuju menyala terus saat peluncuran?
