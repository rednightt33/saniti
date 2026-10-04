# Rencana perbaikan G23: gerbang bukti, daftar alat AI, dan jalan keluar saat buntu (2026-10-04)

> **Digantikan oleh `PLAN_FINAL_2026-10-04.md` (2026-10-04).** Dokumen ini disimpan sebagai riwayat diskusi.

Status: **RENCANA, belum dieksekusi.** Menunggu persetujuan user. Dasar: `GT_ANALYSIS_2026-10-04.md` §1a dan
`ERRORS_AND_SOLUTIONS.md` G23.

## Keputusan user (2026-10-04)

1. AI **harus diberi tahu** bahwa gerbang bukti hanya menolak sekali, dan bahwa jawaban yang dikirim ulang akan lolos
   dengan catatan "angka belum dicek".
2. Lapis 4 hanya untuk "tidak ada gagal total": saat jatah langkah habis, user tetap menerima jawaban terakhir yang sudah
   jadi, dengan catatan dan kode permintaan. **Rem otomatis (pemutus loop) tidak dikerjakan.**

## Akar masalah (terverifikasi)

| Bagian sistem kita | Yang terjadi | Bukti |
|---|---|---|
| Daftar alat AI per langkah | Router memberi set alat baca-saja untuk pesan klarifikasi dan baca ulang (`conversation_router.READ_ONLY_TOOLS`). Riset (`m4c`) punya set alat sendiri. Keduanya tanpa `get_evidence` | log `tools_offered` g9.2 |
| Gerbang bukti | `orchestrator._evidence_gate` memeriksa `self.registry.names()`, yaitu alat seluruh sistem, bukan alat langkah ini | kode |
| Alat `get_system_capabilities` | Melaporkan `available_tools = registry.names()` dengan deskripsi "tools available to this agent". AI membaca bahwa `get_evidence` tersedia, padahal tidak ada di daftar alatnya | `tools/system.py`; reasoning g9.2 iterasi 40 dan 59 |
| Perintah gerbang | "Call get_evidence … Then answer". Tidak menyebut bahwa penolakan hanya sekali, dan tidak menyebut jalan keluar bila alatnya tidak ada | `EVIDENCE_INSTRUCTION` |
| Batas langkah | Saat 60 langkah habis, jawaban yang sudah benar (iterasi 2) dibuang; hasilnya `FAILED MAX_ITERATIONS` | kode (`RunFailure("MAX_ITERATIONS")`), g9.2 |

**Kelas masalah:** satu bagian sistem membaca daftar alat seluruh kantor, sementara AI hanya memegang sebagian. Ini
berlaku untuk setiap gerbang yang perbaikannya butuh alat, setiap pesan yang menyebut alat, setiap jenis langkah yang
punya set alat sendiri (klarifikasi, rencana, riset, baca ulang), dan nanti alat untuk data makro/lintas aset.

## Cara AI tahu alat apa yang ia pegang

AI hanya tahu dari **daftar alat yang dikirim bersama setiap panggilan model**: nama, deskripsi dan isian tiap alat. Ia
tidak bisa memanggil alat di luar daftar itu. Saat ini ada dua sumber yang saling bertentangan:

- daftar alat di panggilan (benar: tanpa `get_evidence`);
- jawaban `get_system_capabilities` dan perintah gerbang (salah: menyebut `get_evidence` ada).

Perbaikannya: **satu sumber kebenaran**, yaitu set alat langkah itu. Semua yang menyebut alat membaca dari set yang sama.

## Langkah

### A. Satu sumber kebenaran: set alat langkah ini (orc)

1. Orchestrator menyimpan set alat yang benar-benar ditawarkan ke langkah ini (`RunState.offered_tools`), diisi di tempat
   yang sama dengan daftar alat yang dikirim ke model, termasuk penyaringan router dan mode 4.
2. Tiga pembaca memakai set itu:
   - **Gerbang:** setiap gerbang yang perbaikannya butuh alat mendeklarasikan alatnya (peta gerbang → alat, misalnya
     `EVIDENCE → get_evidence`). Bila alat tidak ada di set langkah, gerbang tidak meminta perbaikan dan langsung memakai
     catatan bawaannya.
   - **`get_system_capabilities`:** `available_tools` diisi set langkah ini. Daftar seluruh sistem dipindah ke kunci
     terpisah `other_tools_not_in_this_step`, dengan penjelasan "tidak bisa dipanggil di langkah ini".
   - **Teks perintah gerbang:** dibentuk dari set langkah (lihat C).

### B. Pengecekan diminta hanya untuk angka yang perlu dicek (orc)

Tidak ada daftar per jenis langkah. Aturannya diturunkan dari **asal angka**, yang sudah diketahui pelacak asal angka
(provenance):

- Angka yang **dihitung ulang backend** (temuan riset, ringkasan Governor, `query_metric`) tidak perlu dicek lagi.
  Labelnya "dihitung ulang backend".
- Angka yang **berasal dari kode AI** perlu dicek sekali bila alat pemeriksanya ada di meja langkah itu (A). Bila alatnya
  tidak ada, angka itu diberi label "belum dicek ulang".

`get_evidence` hanya membaca dan menghitung ulang; ia menulis baris bukti milik percakapan itu sendiri, bukan data pasar.
Karena itu ia boleh berada di set alat baca-saja, sehingga langkah baca ulang (misalnya g9.2) bisa mengecek. Ini satu
perubahan set alat, bukan aturan per skenario.

### C. AI diberi tahu aturannya (orc, keputusan user 1)

Perintah gerbang bukti menjadi dua versi, dipilih otomatis dari set langkah:

- **Alat ada:** "Angka di jawabanmu belum dicek. Panggil get_evidence untuk klaim utama (maks. 10). Permintaan ini hanya
  sekali: bila pengecekan tidak bisa dibuat, kirim ulang jawabanmu tanpa perubahan; jawaban itu dikirim dengan catatan
  'angka belum dicek'."
- **Alat tidak ada:** gerbang tidak menolak; catatan "angka belum dicek ulang secara terpisah" langsung ditambahkan.

Aturan yang sama (penolakan hanya sekali, dan jalan keluarnya) juga ditambahkan ke perintah semua gerbang lain yang
memakai `_gate_once`, supaya AI tidak mengira ia harus terus mencoba. Teks ini hanya menjelaskan; penegakannya tetap A
dan D.

### D. Tidak ada gagal total (orc, keputusan user 2; lapis 4 saja)

Saat jatah langkah habis (`MAX_ITERATIONS`) atau batas waktu langkah tercapai:

1. Bila sudah ada **draf jawaban terakhir**, draf itu dijalankan sekali lagi melewati semua gerbang dalam mode "tanpa
   perbaikan". Tiap gerbang memakai hasil `FORCED_LIMITATION` yang sudah ada, sehingga angka tanpa sumber tetap ditandai
   atau ditolak, tidak diloloskan diam-diam.
2. Hasilnya dikirim sebagai `LIMITED` dengan catatan: "Pemeriksaan tidak selesai (batas langkah tercapai). Kode
   permintaan: <request_id>."
3. Bila belum ada draf sama sekali, user menerima pesan "Tidak bisa dihitung: <apa yang kurang>. Kode permintaan:
   <request_id>", bukan error kosong. `error.code` tetap `MAX_ITERATIONS`, supaya statistik kegagalan tidak hilang.

**Tidak dikerjakan:** rem otomatis atau pemutus loop (keputusan user).

## Risiko dan mitigasi

| Risiko | Mitigasi |
|---|---|
| Lebih banyak jawaban keluar tanpa cek angka (riset, langkah tanpa alat) | Catatan "belum dicek" atau "dihitung ulang backend" selalu tampil. Angka riset memang sudah dihitung ulang backend |
| `get_evidence` di langkah baca ulang menambah beban Governor (G22) | Maks. 10 klaim, 30 detik per query, 120 detik total (batas yang sudah ada); tier 2 dari tabel yang sudah dirilis tidak menyentuh gudang data |
| Draf terakhir saat batas habis berisi angka yang salah | Draf melewati semua gerbang dalam mode `FORCED_LIMITATION`; angka tanpa sumber diberi label atau ditolak seperti biasa |
| `get_system_capabilities` berubah bentuk | Kunci lama `available_tools` tetap ada (isinya set langkah); kunci baru hanya tambahan |
| Perubahan set alat menggeser biaya token definisi alat | Hanya satu alat ditambahkan ke set baca-saja; deskripsinya sudah pendek |

## Tes (sebelum deploy)

- **Kontrak:** untuk setiap jenis gerbang × setiap set alat router dan mode 4 (ANALYSIS, CLARIFY, CONVERSATIONAL,
  rencana, riset, baca ulang), gerbang tidak pernah meminta alat yang tidak ada di set langkah itu.
- **`get_system_capabilities`** pada langkah CLARIFY melaporkan set langkah, bukan seluruh sistem.
- **Putar ulang G9** dengan ScriptedClient. Pesan CLARIFY: jawaban, lalu gerbang. Hasil: `get_evidence` dipanggil, atau
  jawaban keluar dengan catatan, dalam ≤ 3 iterasi; tidak ada `MAX_ITERATIONS`.
- **Kasus lain:**
  - langkah riset tidak lagi ditolak gerbang bukti;
  - langkah analisis tetap ditolak sekali (kasus di mana perbaikan ini *tidak* mengubah apa-apa);
  - pesan percakapan biasa tanpa angka tidak terpengaruh.
- **Batas langkah:**
  - draf ada → `LIMITED` berisi jawaban, catatan dan kode permintaan;
  - draf berisi angka tanpa sumber → angka itu tetap diberi label atau ditolak;
  - tanpa draf → pesan "tidak bisa dihitung" dengan kode permintaan.
- Tes lama orc (± 1.181) tetap lulus.

## Verifikasi live (dev, setelah persetujuan deploy)

Golden test kecil, 2–3 worker:
- g9 tiga pesan;
- g5 pesan 2 dan 9 (baca ulang);
- g7_lineage_export pesan 2 (asal angka);
- satu pertanyaan riset (g11);
- satu pertanyaan analisis (g1).

| Ukuran | Target | Baseline `ma-golden-20261004a` |
|---|---|---|
| Panggilan model setelah gerbang bukti di langkah tanpa `get_evidence` | 0 | 245 |
| `MAX_ITERATIONS` tanpa jawaban | 0 | 1 (g9.2) |
| Angka jawaban | Sama dengan hitung ulang independen (job baca-saja, seperti `verify-job`) | — |

Biaya dan detik per pesan juga dibandingkan dengan baseline.

## Catatan yang diperbarui saat eksekusi

- `ERRORS_AND_SOLUTIONS.md` G23: status dan solusi.
- `AI_TOOLS.md`: diregenerasi, karena set alat baca-saja berubah dan `get_system_capabilities` mengubah isi.
- README orc.
- `RAILWAY_CHANGELOG.md` saat deploy.
- `OUTSTANDING_ISSUES.md`.
