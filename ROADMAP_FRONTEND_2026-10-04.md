# Roadmap: menghubungkan AI ke antarmuka pengguna (2026-10-04)

Status: **USULAN**, belum dikerjakan; menunggu keputusan user (bagian 5).

## 1. Gambaran: dua jalur

```
                 Jalur 2 (baru): untuk pengguna
  Browser/HP ──► Front-end ──► market-ai-gateway ──► market-ai-orc ──► Governor / sandbox / web-governor
                 (web app)    (layanan baru)         (tetap seperti sekarang)
                                    ▲
                 Jalur 1 (sekarang): untuk tim       │
  Runner GT, skrip, dashboard ──────────────────────┘  (langsung ke orc, dengan kunci internal)
```

- **Jalur 1 — `market-ai-orc` tetap seperti sekarang.**
  - Diakses langsung oleh runner golden test, skrip dan dashboard pemantauan, dengan kunci internal.
  - Fungsinya: memantau setiap pertanyaan, membaca log otak AI, mengukur biaya dan kecepatan, lalu mengoptimalkan.
  - Tidak ada perubahan perilaku. Orc tidak pernah terbuka ke internet.
- **Jalur 2 — layanan baru `market-ai-gateway`:** satu-satunya pintu untuk pengguna. Tugasnya:
  - mengenali tiap pengguna (login);
  - menerima pertanyaan dan meneruskannya ke orc atas nama pengguna itu;
  - menyimpan status jawaban yang sedang diproses;
  - membatasi pemakaian per pengguna;
  - mengirim hasil ke front-end.

## 2. Apa yang sudah ada di orc (dipakai ulang, tidak dibangun lagi)

| Kebutuhan | Sudah ada | Catatan |
|---|---|---|
| Percakapan per pengguna | `X-Saniti-Owner` + penyimpanan percakapan di server (`history_mode SERVER`) | Orc **mempercayai** header pemilik dari pemanggil, sehingga hanya gateway yang boleh memanggil orc |
| Riwayat pesan | `GET /v1/conversations/{id}/messages` | Daftar percakapan per pengguna **belum ada** |
| Setuju/revisi/batal rencana riset | `plan_reply` di `POST /v1/agent/run` | Front-end cukup menampilkan tombol |
| Unduhan file (Excel/CSV) | `GET /v1/exports/{id}/download` (dicek pemiliknya) | Gateway meneruskan unduhan |
| Bukti angka, "Pilihan AI", "Fakta web", anotasi | Ada di respons (`evidence[]`, asumsi, `annotations`) | Front-end tinggal menampilkannya |
| Biaya per jawaban | `execution.cost` | Dasar kuota per pengguna |
| Audit | audit outbox → `market-audit-store` | Untuk jalur 1 (pemantauan) |

## 3. Kesenjangan yang harus ditutup

1. **Jawaban lama: 4–36 menit pada golden test terakhir.** `POST /v1/agent/run` menunggu sampai selesai, sedangkan
   browser dan HP tidak bisa menunggu selama itu.
   - Gateway menerima pertanyaan dan langsung membalas "sedang diproses" beserta nomor tugas.
   - Pekerja di gateway memanggil orc.
   - Front-end menerima kabar progres, lalu jawabannya.
   - Percepatan dari O1 di `GT_FINAL_2026-10-04.md` tetap perlu.
2. **Login pengguna.** Orc tidak punya login pengguna. Gateway memverifikasi login, lalu menetapkan `X-Saniti-Owner`
   dari identitas pengguna, tidak pernah dari isian pengguna.
3. **Kuota dan biaya per pengguna:** batas pertanyaan per hari dan batas USD per hari, dihitung dari `execution.cost`.
4. **Progres langkah:** mode 4 sudah mencatat langkahnya (analisis → rencana → riset → usulan) di log. Untuk front-end
   perlu endpoint progres kecil di orc, atau gateway membaca status langkah.
5. **Daftar percakapan dan pembatalan:** dua endpoint kecil di orc, yaitu daftar percakapan milik pengguna dan
   membatalkan pertanyaan yang sedang berjalan.

## 4. Tahapan

| Tahap | Isi | Layanan | Hasil yang bisa dicoba |
|---|---|---|---|
| **0. Keputusan** | Siapa penggunanya, cara login, teknologi front-end, batas biaya (bagian 5) | — | Keputusan tertulis |
| **1. Gateway MVP** | Login (token), pengguna → owner, antrean tugas (Postgres), pekerja yang memanggil orc dengan kunci internal + `X-Saniti-Owner`, status tugas, kuota per pengguna, unduhan diteruskan | `market-ai-gateway` (baru, Railway dev) | Dua akun uji bertanya bersamaan dari `curl`; masing-masing hanya melihat percakapannya sendiri |
| **2. Tambahan kecil di orc** | Endpoint daftar percakapan, progres langkah, pembatalan | `market-ai-orc` | Gateway menampilkan "sedang menyiapkan data… menjalankan riset…" |
| **3. Front-end MVP** | Halaman chat; tabel markdown; tombol setuju/revisi/batal rencana; panel bukti, "Pilihan AI", "Fakta web"; unduhan; riwayat percakapan | web app (baru) | Pengguna uji memakai dari browser dan HP |
| **4. Pemantauan (jalur 1)** | Dashboard internal: pertanyaan per pengguna, waktu, biaya, kejedot (friction), penyedia, bukti TERCEK/TIDAK COCOK, dari log dan audit store | dashboard internal | Tim melihat setiap pertanyaan tanpa membuka log Railway |
| **5. Produksi** | Lingkungan production terpisah, domain, batas laju, cadangan database, uji beban (suite B golden test), kebijakan privasi | semua | Peluncuran terbatas |

**Keamanan, dipegang di semua tahap:**
- Kunci internal orc hanya ada di gateway, tidak pernah di browser.
- Orc tetap di jaringan privat Railway.
- Kepemilikan percakapan dan unduhan diputuskan oleh gateway dari login, bukan oleh isian pengguna.

## 5. Keputusan yang dibutuhkan dari user

1. **Pengguna:** internal (tim kecil) atau publik? Ini menentukan login dan kuota.
2. **Login:** email + kata sandi, Google, atau lewat Telegram?
3. **Front-end:** web app (misalnya Next.js), bot Telegram, atau keduanya? Bot Telegram lebih cepat dibuat karena
   pola layanan Telegram sudah ada di repo.
4. **Batas biaya:** per pengguna per hari, dan total per hari.
5. **Urutan:** gateway + bot Telegram dulu sebagai MVP tercepat, atau langsung web app?

## 6. Risiko

| Risiko | Mitigasi |
|---|---|
| Jawaban lama membuat pengguna menunggu | Tugas asinkron, progres langkah, notifikasi saat selesai; percepatan O1 |
| Biaya melonjak dengan banyak pengguna | Kuota per pengguna dan batas harian; biaya per jawaban sudah tercatat |
| Database bersama kewalahan (G22) | Antrean Governor (sudah aktif, N=2); uji beban sebelum produksi; database terpisah (G22-6, keputusan user) |
| Pengguna melihat data pengguna lain | Owner dari login di gateway; orc dan unduhan sudah memeriksa pemilik |
| Orc terbuka ke internet | Orc tetap privat; hanya gateway yang publik |
