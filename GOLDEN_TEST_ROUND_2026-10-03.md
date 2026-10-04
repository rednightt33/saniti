# Golden test ronde 2026-10-03 (sementara)

Rencana: `ROUND_PLAN_2026-10-03_FASE_D.md` Bagian 2. Dijalankan atas perintah user.

## Putaran 1: `ma-golden-20261003d` (suite kecil, 3 worker, 2026-10-03 22:31 UTC)

Runner `5e690200`; orc `f2b1cfbc`, sandbox `5a7e839a`, Governor `0fa3f146`. Mode bawaan dev: mode 4.

| Item:giliran | Status / detik / USD | Iterasi | Kejedot (ditolak / perbaikan gerbang / pesanan ulang / penuh) | Bukti | Catatan |
|---|---|---|---|---|---|
| g1:1 | COMPLETED / 108 / 0,050 | 14 | 1 / 1 / 0 / 0 | 7 TERCEK, 1 TIDAK_BISA_DICEK | Baseline 02c: 244 detik, USD 0,041 |
| g8_metric:1 | COMPLETED / 239 / 0,041 | 14 | 0 / 2 / 0 / 0 | 4 TIDAK_BISA_DICEK (G20) | Metrik resmi dipakai; papan tidak dicampur; data sampai 31-08-2026 disebut |
| g7:1 | COMPLETED / 248 / 0,057 | 23 | 4 / 3 / 0 / 0 | 1 TERCEK, 6 TIDAK_BISA_DICEK (G20), 1 TIDAK COCOK (G21) | Baseline 02c g7:1: rencana, 436 detik |
| g7:2–3 | FAILED / 0 | 0 | — | — | `PROVIDER_REJECTED`: batas kunci OpenRouter (R30) |
| g6:1 | COMPLETED / 175 / 0,080 | 28 | 2 / 2 / 0 / 0 | 6 TERCEK | Aturan user dipakai: naik ≥ 3%, 10 hari, ambang 1 poin persen; langkah rencana riset gagal (R30) |
| g6:2 | FAILED / 0 | 0 | — | — | R30 |

**Terbukti:**
- 0 `SESSION_CAPACITY_EXCEEDED` dengan 3 jawaban paralel (S28).
- 0 pesanan data ulang.
- Tidak ada angka tanpa sumber (provenance kosong).
- Bukti tingkat 2 (tabel dasar) TERCEK di semua item.
- Kesegaran data disebut.

**Masalah baru:**
- **G20:** bukti tingkat 1 membaca angka Governor sebagai kosong.
- **G21:** jumlah hari tidak bisa dinyatakan dalam resep.

Keduanya sudah diperbaiki (orc `4b764004`, migrasi 20261004_001).

**R30:** batas total kunci OpenRouter habis. Sisa golden test menunggu batas dinaikkan.

## Putaran 2: `ma-golden-20261003e` (2026-10-04 05:22 UTC, 12 item, 5 worker)

Runner `b2c2a5be`. Sebelum mulai, sisa batas kunci OpenRouter USD 2,97. Masa simpan sandbox diset 1 jam untuk g9/g11.
Mulai 05:27 UTC setiap panggilan model ditolak OpenRouter dengan HTTP 402: **saldo kredit akun habis** (total kredit
USD 25, terpakai USD 25,007; R30). Runner dihentikan pukul 05:31 dan masa simpan dikembalikan ke 24 jam.

Hasil: 17 giliran tercatat, total biaya USD 0,31. Uji kedaluwarsa (g9 giliran 2–3, g11 setuju ulang) **tidak sempat
berjalan**.

| Giliran | Status | Detik | Biaya USD | Iterasi | Friction (tolak/perbaikan/ulang) | Bukti |
|---|---|---|---|---|---|---|
| g2:1 | COMPLETED | 110 | 0,040 | 17 | 2/1/0 | 8 TERCEK, 1 TIDAK BISA DICEK (Governor 503, G22), 0 TIDAK COCOK |
| g3:1 | COMPLETED | 261 | 0,009 | 20 | 0/1/0 | 10 TERCEK, 0 TIDAK COCOK |
| g9:1 | COMPLETED | 240 | 0,102 | 32 | 1/2/0 | 4 TERCEK; tabel return September 4 bank |
| g4:1 | AWAITING_CONFIRMATION | 54 | 0,021 | 7 | 2/0/0 | rencana diajukan |
| g4:2 | HTTP 404 `RESEARCH_PLAN_NOT_FOUND` | 2 | – | – | – | rencana giliran 1 tidak tersimpan (G22) |
| g5:1 | HTTP 503 `CONVERSATION_STORE_UNAVAILABLE` | 10 | – | – | – | baca riwayat percakapan timeout (G22) |
| g11:1 | LIMITED | 322 | 0,051 | 17 | 0/1/0 | 30 angka tanpa sumber; langkah riset kena 402 |
| g7_lineage_export:2 | LIMITED | 70 | 0,009 | 4 | 0/1/0 | tidak ada tabel karena giliran 1 kena 402 |
| g6, g7, g8, g7_lineage, g6_rsi (8 giliran) | FAILED `PROVIDER_REJECTED` | – | – | – | – | HTTP 402 (R30) |
| g7_followup:2–3 | NEEDS_CLARIFICATION | – | – | 1 | 0/0/0 | lanjutan dari giliran 1 yang gagal |

`SESSION_CAPACITY_EXCEEDED` dan pesanan data ulang: 0 pada giliran yang selesai. g1_repeat masih berjalan saat runner
dihentikan (orc menyelesaikannya pukul 05:32), sehingga hasilnya tidak tercatat runner.

**Temuan baru: G22 (database bersama kewalahan).** Antara 05:23 dan 05:30, Postgres membatalkan 45 statement karena
timeout. Penyebab terverifikasi:
- Simpan percakapan (batas 5 detik) gagal, sehingga rencana g4 hilang dan riwayat g5 tidak terbaca.
- Pada saat yang sama, 30 hitung-baris Governor habis waktu. 21 di antaranya adalah hitungan berulang untuk satu pesanan
  data g1 (`IDX_Broker_Summary` dirangkum per tanggal/saham/tipe investor, dipecah per bagian, 6 menit).
- Checkpoint Postgres butuh 23–48 detik untuk sync.

Dugaan (belum diverifikasi): disk Postgres jenuh oleh scan gudang yang berjalan bersamaan. Cara cek dan usulan perbaikan
ada di `ERRORS_AND_SOLUTIONS.md` G22. Belum ada yang diubah.

**Putusan sementara per update** (dari giliran yang selesai):

| Update | Putusan |
|---|---|
| D6 bukti | Bekerja: 22 TERCEK, 0 TIDAK COCOK. Satu TIDAK BISA DICEK menyebut alasannya (Governor 503), tidak disembunyikan (G20/G21 terbukti) |
| D0 friction | Terisi di setiap giliran |
| S28 | 0 penolakan kapasitas |
| D5 query_metric, D3 lineage, D4 ekspor | Belum terbukti: giliran yang memakainya kena 402 |
| R-STORE resume, rencana kedaluwarsa | Belum terbukti: giliran yang memakainya kena 402 |

**Sisa yang menunggu:**
1. Kredit OpenRouter ditambah (R30).
2. Keputusan perbaikan G22, supaya putaran berikutnya tidak gagal karena database.

Tanpa keputusan G22, uji ulang sebaiknya memakai 2–3 worker.

## Putaran 3: `ma-golden-20261004a` (2026-10-04 05:47–07:24 UTC, 31 pesan, 3 worker)

Runner `5901537c`. Kredit OpenRouter sudah ditambah oleh user. Masa simpan sandbox diset 1 jam selama test (sandbox
`b36561f8`), lalu dikembalikan ke 24 jam (`bdb0bcce`). Tidak ada penolakan dari provider. g2 dan g3 tidak diulang karena sudah
selesai di putaran 2.

### Biaya

Total **USD 2,19** untuk 31 pesan (rata-rata USD 0,07 per pesan, 148 menit waktu model). Biaya ini dipakai oleh 57
langkah model.

| Percakapan | Pesan | USD | Menit |
|---|---|---|---|
| g5 percakapan panjang | 9 | 0,870 | 55,8 |
| g6 ubah ambang | 4 | 0,284 | 15,8 |
| g6 RSI | 2 | 0,208 | 11,0 |
| g7 asal-usul + ekspor | 3 | 0,196 | 8,3 |
| g7 definisi | 3 | 0,190 | 10,5 |
| g9 tabel lama | 3 | 0,155 | 18,3 |
| g11 rencana kedaluwarsa | 3 | 0,126 | 14,6 |
| g8 metrik | 1 | 0,101 | 4,3 |
| g1 net asing | 1 | 0,042 | 3,1 |
| g4 hipotesis | 2 | 0,015 | 5,8 |

| Langkah | Jumlah | USD |
|---|---|---|
| Langsung (tanpa pemecahan mode 4) | 14 | 0,660 |
| Riset | 13 | 0,490 |
| Rencana riset | 8 | 0,349 |
| Lanjutan rencana | 4 | 0,248 |
| Analisis | 8 | 0,241 |
| Usulan | 10 | 0,193 |

Pesan termahal adalah g5 pesan 1 (USD 0,26; 27 menit; 76 iterasi). Untuk pertanyaan angka sederhana, mode 4 tetap
menambahkan langkah riset dan usulan. Contohnya g8 (net asing 5/20 hari): sudah dijawab tepat, tetapi tetap ada riset
3 sudut dan usulan, sehingga biayanya USD 0,10, padahal g1 hanya USD 0,04. Mode bawaan 4 adalah keputusan user.

### Verifikasi manual

Angka-angka dihitung ulang langsung dari tabel mentah lewat job sementara `verify-job` (`2d811a7c`). Job ini hanya
membaca (koneksi read-only), tidak memakai kode AI, sandbox, maupun Governor, dan sudah dihapus setelah selesai.

| Jawaban | Yang dihitung ulang | Hasil |
|---|---|---|
| g1 net asing pasar reguler, 10 bank paling likuid 2025 | peringkat close×volume; net asing dari `IDX_Broker_Summary` (dicek silang dengan `Feature_03`) | **Cocok semua**: urutan 10 saham, nilai transaksi, net per saham, 236/233 hari, total −Rp 55,64 T |
| g2 close tertinggi/terendah 48 bank 2025 (putaran 2) | max/min close dan tanggalnya, selisih % | **Cocok 48 dari 48** (harga, tanggal, %) |
| g3 event study turun ≥5% (putaran 2) | event tanpa tumpang tindih, dari harga mentah | **Cocok**: 90.027 baris, 3.659 / 1.387 / 14 / 2.258 event, rata-rata 0,19%, median −0,37%, hit 44,6%, pembanding 86.094 / 0,29% |
| g4 hipotesis BBCA | net asing positif → return 1 hari | **Cocok** (selisih 1 hari): 1.027 vs 1.026 event, −0,019% vs −0,021%, pembanding 0,033% vs 0,032%, p 0,40 vs 0,39 |
| g7 net asing pasar Nego, 5 bank teratas | turnover dan Nego asing dari `IDX_Broker_Summary` | **Cocok semua**: turnover (631,37 T …), beli/jual/net per saham, hari Nego 236/236/236/229/128, total Rp 1,57 T |
| g8 net asing BBCA 5/20 hari | per papan, dari `IDX_Broker_Summary` dan `Feature_03` | **Cocok sampai rupiah**: Regular +473.338.522.500 / +1.143.965.065.000; Nego −7.481.298.150 / +147.921.004.632; Tunai 0 (2 hari) |
| g9 return September dan 1–2 Okt | close 31 Agu, 30 Sep, 2 Okt | **Cocok** (8 angka) |
| g11 turun ≥3% → 5 hari (deskriptif) | dari harga mentah | **Cocok secara angka**: rata-rata 0,28/0,32%, hit 45,1/39,6%, P10/P90. Jumlah baris berbeda tipis (7.560 vs 7.550; 73.534 vs 73.398). Jawaban pesan 3 menyebut 81.194 baris, sedangkan pesan 1 menyebut 81.094 |
| g6 RSI(14) < 30 → naik ≥3% dalam 10 hari | RSI Wilder dari harga mentah | **Cocok**: 33,3% vs 23,3%, rata-rata 1,21% vs 0,52%. Run g6_rsi tepat (88.875 baris). Run g6_revise memasukkan 672 baris tanpa nilai RSI ke kelompok pembanding (**M72**, dampak 0,1 pp) |

**Salah atau menyesatkan:**
- **g5 pesan 6 (P27):** jawabannya "0,00% vs 0,00%" dan putusan NOT_SUPPORTED. Nilai aslinya −0,41% vs −0,32%.
  Nilai dalam bentuk pecahan diberi label persen, sehingga putusan dibandingkan dengan ambang yang 100 kali terlalu besar.
  **Putusan itu tidak valid.**
- **g5 pesan 5–6 (M71):** BBCA dimasukkan ke kelompok "bank BUMN". Database tidak punya atribut BUMN (keputusan 6),
  jadi AI menebak tanpa menyatakannya.
- **g9 pesan 2 (G23):** pertanyaan lanjutan sederhana gagal karena mencapai batas 60 iterasi.

Yang belum diverifikasi independen:
- angka arus broker g5 (definisi "hari jatuh" ada di pesan 1, yang dump-nya tidak tersimpan);
- angka riset multi-sudut. Backend sudah menghitung ulang angka riset dari deklarasinya, tetapi P27 menunjukkan bahwa
  jalur frame bisa salah satuan.
