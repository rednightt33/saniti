# Prompt untuk chat baru: restart Postgres otomatis (EXEC-PG-RESTART-CRON)

Salin salah satu blok di bawah ke chat baru di repository `rednightt33/saniti`. Untuk eksekusi, lampirkan juga file
token Railway yang baru (khusus layanan ini). Token tidak disimpan di Git, jadi chat baru tidak bisa menemukannya sendiri.

## A. Jalankan eksekusinya

```
Baca AGENTS.md dan semua file wajibnya (Required reading), lalu baca EXEC.md bagian EXEC-PG-RESTART-CRON dan
EXEC-PG-MEMORY, ERRORS_AND_SOLUTIONS.md M229, M319 dan M340, RAILWAY_CHANGELOG.md bagian 2026-11-03,
scripts/restart_postgres.py, scripts/set_postgres_memory.py, apps/terminal-publisher/publisher.py (run_times, cron_for,
should_run) dan apps/stockbit-updater/deploy.sh.

Go untuk EXEC-PG-RESTART-CRON langkah 1–9, termasuk migrasi grant kecil untuk pgweb, tombol Telegram (restart
sekarang dan auto ON/OFF) di telegram-trigger, dan pesan Telegram (manual, dimulai, sukses, gagal, ditolak) di
telegram-monitor. Jam restart:
PG_RESTART_TIMES_WIB=09:45,20:45 (bisa saya ubah nanti). Token Railway baru terlampir: pakai hanya sebagai variabel
RAILWAY_RESTART_TOKEN di layanan postgres-memory-cron (set lewat stdin), jangan dicetak, jangan di-commit, dan hapus
file sementaranya.

Aturan:
- Setiap keputusan dari inspeksi kode, log dan data live saat itu, bukan dari ingatan. Sebutkan file:line, log atau ID
  run sebagai bukti.
- Sebelum restart Postgres atau deploy apa pun, cek tidak ada run user aktif (M340), tidak ada cron dalam 45 menit dan
  di luar jendela B6.
- Run terjadwal pertama harus mode check (tanpa restart). Pindah ke apply hanya sesudah log check benar.
- Jangan klaim deployment berhasil sebelum deployment itu SUCCESS. Jangan klaim perubahan database berhasil sebelum
  dibaca balik dari live.
- Kalau ada temuan di luar rencana atau rencana harus berubah, berhenti dan tanya saya dulu.
- Catat semuanya sesuai Mandatory workflow di AGENTS.md (migrasi, DATABASE_SCHEMA/CHANGELOG, RAILWAY_CHANGELOG,
  railway.ts lewat config pull, AGENTS.md, EXEC.md), lalu push ke main dan pastikan sama dengan origin/main.
- Laporkan ke saya dalam bahasa Indonesia yang mudah dipahami non-developer.
```

## B. Ubah jam restart

```
Baca AGENTS.md bagian "Postgres memory after large updates" dan EXEC.md bagian EXEC-PG-RESTART-CRON. Ubah jam restart
Postgres otomatis menjadi <JAM WIB, mis. 09:30,21:00> dengan scripts/set_postgres_restart_times.py: jalankan dulu tanpa
--apply dan tunjukkan hasilnya ke saya (bentrok dengan cron lain atau B6?), baru --apply setelah saya setuju. Catat di
RAILWAY_CHANGELOG.md dan EXEC.md dengan kata-kata saya.
```

## B2. Restart manual atau matikan restart otomatis

Tanpa chat: buka bot Telegram, ketik `/start`, lalu tekan "🔄 Restart Postgres" atau tombol "Auto restart: ON/OFF".
Lewat chat:

```
Baca AGENTS.md bagian "Postgres memory after large updates" dan EXEC.md bagian EXEC-PG-RESTART-CRON. Saya mau
<restart Postgres sekarang | matikan restart otomatis | nyalakan lagi restart otomatis>. Cek dulu run user aktif,
cron terdekat dan jendela B6, tunjukkan hasilnya, lalu jalankan setelah saya setuju. Catat di RAILWAY_CHANGELOG.md.
```

## C. Tanya jawab (tanpa mengubah apa pun)

```
Baca AGENTS.md, EXEC.md bagian EXEC-PG-RESTART-CRON dan EXEC-PG-MEMORY, dan ERRORS_AND_SOLUTIONS.md M319. Jangan
mengubah file, data, variabel atau layanan apa pun. Jawab berdasarkan kode, log Railway dan data live saat ini (sebut
buktinya), dalam bahasa non-developer:
<PERTANYAAN SAYA, mis. "Apakah restart otomatis semalam jalan? Berapa memori Postgres sebelum dan sesudahnya, dan
berapa biaya memori 7 hari terakhir dibanding minggu sebelumnya?">
```

## D. Cari saham dengan pola candle (tanpa mengubah apa pun)

```
Baca AGENTS.md dan DATABASE_SCHEMA.md bagian Feature_04_Technical_Indicator. Cari saham dengan pola candle <NAMA POLA>
pada tanggal bursa terakhir. Pakai kolom cdl_* yang sudah dihitung (TA-Lib: +100 bullish, -100 bearish). Kalau pola itu
tidak ada sebagai kolom, tanya saya dulu definisinya sebelum menghitung dari OHLC. Query hanya-baca lewat pgweb
(verification/terminal_api/pgq.py), filter satu tanggal. Sebutkan tanggal datanya dan apakah sama dengan hari bursa
terakhir. Urutkan menurut nilai transaksi, dan beri catatan bahwa TA-Lib tidak memeriksa tren sebelumnya.
```
