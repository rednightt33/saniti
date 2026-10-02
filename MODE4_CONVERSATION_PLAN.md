# Rencana: mode 4 sebagai percakapan yang luwes (M56)

Status: **dikerjakan di branch `claude/g2-g3-reactivation` (2026-10-02), belum di-deploy; saklar `AI_ENABLE_CONVERSATION_ROUTER`**. Disetujui user 2026-10-02 ("Setuju untuk mode 4"), difinalkan bersama `G2_G3_REACTIVATION_PLAN.md` (langkah 5
di urutan kerjanya); belum dijalankan. Terkait `ERRORS_AND_SOLUTIONS.md` M56.

> Diperluas oleh `G2_G3_REACTIVATION_PLAN.md` bagian 4d (2026-10-02): jenis giliran CLARIFY, INSIGHT (analisis pendorong) dan
> CONTINUE dengan arah bebas G1–G4, state lintas giliran (temuan, manual, buku percobaan), berlaku untuk semua mode.

## 1. Arahan user (2026-10-02)

- Apa pun isi jawabannya, pertanyaan lanjutan **tidak boleh membuat riset diulang dari awal**, kecuali user memang
  memintanya.
- Mode 4 harus luwes, seperti percakapan biasa antara user dan AI.
- Tujuan 1 tetap berlaku: pertanyaan analisis baru dijawab lalu dibawa satu langkah lebih jauh (uji hipotesis,
  event study).

## 2. Alur sekarang (diinspeksi di `app/mode4.py`)

```
Giliran 1 (tanpa rencana tertunda):   A analisis → B rencana 2–6 angle → C uji langsung → D satu saran (menunggu user)
Giliran berikutnya (ada saran D):     pengklasifikasi: APPROVE / REVISE / CANCEL / UNRELATED
   APPROVE   → jalankan saran (C) + saran baru (D)
   REVISE    → saran direvisi, menunggu konfirmasi
   CANCEL    → selesai
   UNRELATED → saran dibatalkan, lalu giliran 1 lagi dari awal (A + B + C + D)
Tanpa saran tertunda:                 setiap pesan = giliran 1 dari awal
```

Masalah yang terverifikasi:

| # | Masalah | Bukti |
|---|---|---|
| 1 | Pertanyaan apa pun ("kenapa XL paling tinggi?", "jelaskan angka ini") masuk UNRELATED, sehingga A+B+C+D diulang (m01 728 s) | Instruksi pengklasifikasi: "UNRELATED: anything else: silence, a question, …" (`research_plan.py` ~514); cabang UNRELATED memanggil `first_round` (`mode4.py` ~229) |
| 2 | Penyempitan cakupan ("kalau hanya bank BUMN?") dibaca sebagai REVISE saran, lalu berakhir dengan klarifikasi | `ma-batch-20261001a`, m01 giliran 2 |
| 3 | Temuan riset (status, estimasi, CI, p) tidak disimpan di catatan percakapan, jadi tidak bisa dikutip di giliran berikutnya | `data_record` hanya mencatat data yang dipakai angle (`add_research`), bukan hasilnya; rujukan `finding.<angle>` hanya berlaku di run tempat riset selesai |
| 4 | Angka dari jawaban AI sebelumnya bukan sumber angka di giliran berikutnya; hanya pesan user yang dihitung | `orchestrator.py` ~1598: hanya `turn.role == "user"` |
| 5 | Saran yang tertunda hilang begitu user bertanya hal lain | Cabang UNRELATED membatalkannya |

Hal yang sudah mendukung percakapan:
- alias output `out.oN` berlaku sepanjang percakapan (P1);
- catatan data (tabel, kolom, nilai, relasi, coverage, output) dibawa ke setiap giliran (M47, P5);
- sesi dan bundle hangat bisa dipakai ulang (conversation reuse).

## 3. Alur yang diusulkan

Setiap giliran setelah giliran pertama dibaca oleh **router percakapan**: pengklasifikasi yang sudah ada diperluas,
dan backend menjalankan aturan tegas berdasarkan kelasnya.

| Kelas | Contoh | Yang dijalankan | Riset (B/C)? | Saran tertunda |
|---|---|---|---|---|
| **FOLLOW_UP**: penjelasan, rincian, klarifikasi, penyempitan atau perluasan cakupan atas topik yang sama | "Kenapa XL paling tinggi?", "Jelaskan hasil crash_rebound", "Kalau hanya BUMN?", "Rinci per tahun" | **Satu langkah analisis** atas hasil percakapan (output, temuan, catatan data); data ditarik lagi hanya bila hasil yang ada tidak memuat yang dibutuhkan (bundle hangat dipakai ulang) | **Tidak** | Tetap disimpan |
| **RESEARCH_REQUEST**: user meminta uji atau riset | "Uji juga untuk BUMN", "Buktikan", "Riset lagi", "Jalankan sarannya" | Persetujuan saran → C + D baru. Hipotesis baru dari user → B (angle dari user) + C + D | Ya, karena diminta | Diganti hasil baru |
| **REVISE_SUGGESTION** | "Sarannya pakai 5 tahun saja" | B revisi, menunggu konfirmasi | Tidak | Direvisi |
| **CANCEL** | "Tidak usah" | Konfirmasi singkat | Tidak | Dibatalkan |
| **NEW_TOPIC**: pertanyaan analisis yang tidak bergantung pada hasil sebelumnya | "Sekarang bagaimana saham telko?" | Giliran pertama: A + B + C + D (tujuan 1) | Ya (lihat keputusan 2) | Diganti |
| **CONVERSATIONAL**: terima kasih, pertanyaan metodologi atau definisi | "Metode apa yang dipakai?", "Apa itu CAR?" | Jawaban langsung dari konteks, tanpa alat data | Tidak | Tetap |

**Aturan backend** (bukan sekadar instruksi prompt):
1. B dan C hanya jalan untuk **RESEARCH_REQUEST** dan **NEW_TOPIC**. Kelas lain tidak pernah memicu riset, apa pun
   isi jawabannya.
2. Kalau ragu antara FOLLOW_UP dan NEW_TOPIC atau RESEARCH_REQUEST, pilih **FOLLOW_UP**, dan jawabannya menawarkan
   "mau saya uji / riset?". Salah ke arah yang murah (satu langkah analisis), bukan ke arah yang mahal (12 menit).
3. Saran yang tertunda tidak hilang karena pertanyaan lanjutan. User bisa menyetujuinya kapan saja di percakapan itu.
4. Jawaban FOLLOW_UP satu bagian, tanpa bagian "Hasil riset" atau "Saran" kosong. Status percakapan tetap
   `AWAITING_CONFIRMATION` bila ada saran tertunda.

## 4. Prasyarat agar FOLLOW_UP bisa menjawab dari hasil yang ada

**E1. Temuan riset disimpan di percakapan.**
- Lapisan: `app/data_record.py` dan state percakapan.
- Bagian baru `findings`: per angle `angle_id`, metode, status, estimasi utama, CI, p (terkoreksi), sampel efektif,
  hasil holdout, rentang data, `request_id`.
- `finding.<angle>` bisa dirujuk di giliran mana pun, dan gerbang angka menerimanya sebagai sumber, sama seperti
  `out.oN`.
- Kelasnya: semua hasil bertingkat (output analisis, temuan riset, nanti event study) bisa dikutip ulang tanpa
  dihitung ulang.

**E2. Router di setiap giliran.**
- Pengklasifikasi dijalankan juga saat tidak ada saran tertunda.
- Masukannya ringkasan percakapan: pertanyaan terakhir, tabel yang dipakai, angle yang sudah diuji, saran tertunda.
- Skema keluarannya diperluas dengan kelas di bagian 3.
- Sumber kebenaran tetap aturan backend di bagian 3.

**E3. Konteks langkah FOLLOW_UP.**
- Langkah analisis menerima catatan data, daftar output dan temuan (E1), dan instruksi: jawab dari hasil
  percakapan dulu; minta data baru hanya bila tidak tersedia.
- Pemakaian ulang bundle "sama atau lebih sempit" (Langkah 9 butir 4 di rencana kecepatan) membuat penyempitan
  seperti "hanya BUMN" tidak menarik ulang dari gudang.

**E4. Angka penjelasan tetap terjaga.**
- Angka dari jawaban sebelumnya tidak dipercaya sebagai teks (keputusan lama tetap). Penjelasan merujuk `out.oN`
  atau `finding.<angle>`, atau angka turunan yang dihitung lewat analisis.
- Penyebab dari luar database (berita, aksi korporasi) tidak tersedia di orc. Jawaban menyatakannya, tidak menebak.

## 5. Risiko dan mitigasi

| Risiko | Mitigasi |
|---|---|
| Router salah kelas: pertanyaan baru dianggap lanjutan, sehingga riset tidak jalan | Jawaban FOLLOW_UP selalu menawarkan riset; user cukup bilang "uji"; tingkat salah kelas diukur di suite multi-giliran |
| Router salah kelas: lanjutan dianggap topik baru, sehingga riset 12 menit jalan | Aturan "ragu → FOLLOW_UP"; NEW_TOPIC hanya bila tidak merujuk hasil sebelumnya; diukur |
| Temuan lama dikutip padahal data sudah bergeser | Setiap temuan menyimpan rentang data dan waktu; jawaban menyebut "per data s.d. tanggal X"; user bisa minta riset ulang |
| State percakapan membesar | Batas jumlah temuan dengan penanda "N lainnya tidak ditampilkan" (pola P5); versi lengkap di store |
| Satu panggilan pengklasifikasi tambahan per giliran | Panggilan kecil (reasoning low), sudah ada untuk saran tertunda; diukur |

## 6. Verifikasi

Suite multi-giliran baru dengan saklar pikiran menyala. Dicatat per giliran: kelas, langkah yang jalan, detik, dan
rujukan angka.

1. "Siapa broker yang konsisten membeli saham bank ketika market crash?" → giliran pertama (A+B+C+D).
2. "Kenapa XL paling tinggi?" → FOLLOW_UP, tanpa B/C, < 2 menit, angka dari `out.oN`.
3. "Jelaskan hasil crash_rebound" → FOLLOW_UP, angka dari `finding.crash_rebound` (E1).
4. "Kalau hanya bank BUMN?" → FOLLOW_UP dengan penyempitan, bundle dipakai ulang, tanpa B/C.
5. "Uji juga untuk BUMN saja" → RESEARCH_REQUEST, B+C.
6. "Ok jalankan saran yang tadi" → RESEARCH_REQUEST (saran tertunda masih ada).
7. "Sekarang bagaimana saham telko?" → NEW_TOPIC.

Kasus di luar m01: e02 (asing → harga BBCA) dengan lanjutan "kenapa korelasinya negatif?".

Kasus yang tidak berlaku: percakapan mode ANALYSIS atau RESEARCH tetap (bukan mode 4). Alurnya tidak berubah.

## 7. Keputusan yang diminta dari user

1. ~~Kelas dan aturan~~: disetujui, diperluas di `G2_G3_REACTIVATION_PLAN.md` 4d-2 (CLARIFY dan INSIGHT menggantikan
   FOLLOW_UP; CONTINUE dengan arah bebas G1–G4).
2. ~~NEW_TOPIC~~: giliran pertama (A + riset) di mode 4.
3. ~~E1~~: dikerjakan bersama router (langkah 5 urutan kerja `G2_G3_REACTIVATION_PLAN.md`).
