# Rencana optimasi backend (2026-10-04)

Status: **RENCANA, belum dieksekusi.** Dasar: `GT_FINAL_2026-10-04.md` (log otak AI golden test `ma-golden-final-20261004a`).
Setiap usulan di-benchmark dulu; yang tidak terbukti tidak dipasang.

## Evaluasi jujur putaran sebelumnya

| Bagian rencana | Hasil di golden test |
|---|---|
| Fase 1: ganti ke MiMo flash + uji tingkat reasoning | Dibatalkan, kembali ke DeepSeek. Uji reasoning menghabiskan waktu tanpa kesimpulan |
| Fase 1: aturan penyedia (diskon cache) | **Ikut memperlambat:** menyingkirkan InferenceNet, dan 415/416 panggilan jatuh ke Morph yang lambat (K1) |
| Fase 2: G23 (AI tidak buntu) | Bekerja: 0 loop, 0 gagal total |
| Fase 2: router (S7) | Bekerja di g7.3 |
| Fase 3–5 | Sebagian besar belum teruji (pesan g5.6–9, g9.2–3, g11, g13, suite B tidak dijalankan) |
| Gerbang bukti (D6) | 94 klaim dicek, **0 tidak cocok**, biaya ± 824 detik; lihat O4 |

## O2 — Riwayat percakapan (K2): pesan terakhir tidak pernah dibuang

**Akar masalah (terverifikasi):**
- `trim_history` membuang giliran utuh dari yang terbaru ke belakang dengan batas `AI_MAX_HISTORY_TOKENS` = 4.000
  (bawaan). Batas ini hanya 0,8% dari batas konteks dev (500.000).
- Jawaban terakhir yang lebih dari 4.000 token membuat **semua** riwayat hilang. Ini terjadi pada g5.2:
  `history_turns_dropped = 2`, dengan reasoning "I don't have the earlier answer text".
- 4 dari 23 jawaban melewati batas ini.

**Kelas masalah:** setiap pertanyaan lanjutan setelah jawaban panjang (tabel, mode 4), di semua jenis data.

**Benchmark eksternal:**

| Sumber | Praktik |
|---|---|
| OpenAI Responses `truncation: auto` | Membuang dari **tengah** percakapan, bukan yang terbaru |
| OpenAI compaction | Semua pesan user disimpan **verbatim**; jawaban, alat dan reasoning lama dipadatkan. Contoh ambang di dokumentasi 200 rb token; praktik umum: padatkan saat lewat ± 70% konteks |
| Anthropic | Reasoning giliran lama dibuang otomatis; reasoning tetap dikirim selama satu putaran alat |
| DeepSeek (dokumentasi API) | Reasoning ronde sebelumnya **tidak** digabungkan ke konteks ronde berikutnya; di dalam satu ronde dengan alat, reasoning wajib dikirim balik |
| OpenRouter | Reasoning dikirim balik untuk kesinambungan pemakaian alat; mode `current_turn` vs `all_turns` |

**Kesimpulan benchmark untuk "multi percakapan dengan catatan pikiran AI di dalamnya":**
- Catatan pikiran hanya berlaku di dalam satu jawaban. Ini sudah dikerjakan: `AI_REPLAY_REASONING`, dan DeepSeek
  menerimanya.
- Antar pesan, catatan pikiran **tidak** dibawa. Yang dibawa adalah kesimpulannya di jawaban: asumsi, batasan,
  metodologi, dan "Pilihan AI", seperti yang sudah disimpan `assistant_text`.
- Pesan user selalu dibawa utuh.
- Jawaban AI terbaru selalu dibawa. Jawaban lama dipadatkan, tidak dibuang.

**Perbaikan (orc, permanen):**
1. **Anggaran riwayat** diturunkan dari batas konteks: persentase `AI_MAX_CONTEXT_TOKENS`, misalnya 10%, bukan angka
   tetap 4.000.
2. **Urutan pengisian:**
   - semua pesan user, verbatim;
   - jawaban terbaru, utuh bila muat;
   - jawaban lama dipadatkan: kalimat pembuka + asumsi + batasan + "Pilihan AI" + daftar tabel hasil yang dirujuk;
   - baru yang paling lama dibuang, dari tengah, dengan catatan "N pesan lama diringkas".
3. Isi tabel lengkap tetap dibaca lewat `get_session_output`; referensi `out.oN` tetap valid.

**Mencakup:** semua pertanyaan lanjutan. **Tidak mencakup:** percakapan yang sangat panjang, puluhan pesan dengan tabel
besar; untuk itu perlu ringkasan buatan model (compaction), yang belum diusulkan.

**Benchmark sebelum pasang:** ulang g5.1 → g5.2, g7.1 → g7.2 dan g6.1 → g6.2 dengan anggaran lama vs baru.
- Ukur: balik bertanya atau tidak, dan apakah merujuk angka yang benar.
- Ukur juga token input dan biaya per pesan.

**Risiko:** token input naik. **Mitigasi:** batas persentase; cache prefix tetap berlaku.

## O3 — Set alat baca diturunkan dari sifat alat (K3) — *masuk rencana, belum dieksekusi*

**Akar masalah (terverifikasi):**
- "Ekspor ke Excel" dirouting sebagai CLARIFY.
- `conversation_router.READ_ONLY_TOOLS` adalah daftar tulis-tangan tanpa `export_result`.
- Akibatnya g7_lineage.3 berakhir LIMITED.

**Kelas masalah:** setiap aksi atas hasil yang sudah ada (ekspor, bukti, lineage, nanti grafik) di langkah baca.

**Perbaikan (orc, permanen):**
- Setiap `ToolSpec` membawa sifat efek: tidak mengubah apa pun / hanya artefak milik percakapan sendiri / menarik data /
  menghitung.
- Set baca-saja diturunkan dari dua sifat pertama, tidak didaftar per nama.
- Tes kontrak: setiap alat wajib punya sifat.

**Tidak mencakup:** permintaan yang butuh hitung baru, karena itu memang bukan langkah baca.

**Benchmark:** ulang g7_lineage.3 dan satu pertanyaan "tunjukkan lineage" di langkah baca.

## O4 — Bukti otomatis untuk angka yang dirujuk (K4)

**Akar masalah (terverifikasi dari log):**
- Gerbang bukti meminta AI menulis "angka persis seperti yang kamu tulis" plus resep hitung ulang.
- Padahal AI menulis angka lewat rujukan `{{out.oN…}}` yang sudah diketahui sistem sampai tabel, baris dan kolomnya.
  Golden test: 392 angka DIRUJUK.
- AI menjadi perantara. Di g4 ia bingung harus menulis rujukan atau angka, dan dua kali resep `base_table`-nya
  ditolak.
- Hasilnya 94/94 TERCEK, 0 tidak cocok, dengan biaya 10 putaran ± 824 detik.

**Kelas masalah:** setiap gerbang yang meminta AI menyatakan ulang sesuatu yang sudah diketahui backend.

**Perbaikan (orc + sandbox, permanen):**
- Untuk angka yang dirujuk ke tabel hasil, backend menghitung ulang sendiri dari tabel dasar yang dirilis (tingkat 2),
  dan untuk metrik gudang lewat Governor (tingkat 1), tanpa meminta AI.
- Gerbang hanya meminta AI untuk angka yang **diketik** (bukan rujukan) dan berasal dari kode AI.

**Tidak mencakup:** angka yang diketik AI tanpa rujukan; untuk itu gerbang tetap meminta sekali.

**Benchmark:** jawaban g1, g3, g5.3, g6.1. Ukur berapa klaim yang bisa dicek otomatis, berapa panggilan model yang
hilang, dan apakah status bukti sama.

## O1 — Rute penyedia berdasarkan kecepatan terukur (K1) — *butuh keputusan user*

**Akar masalah (terverifikasi):**
- Rute OpenRouter condong ke harga; Morph termurah dan lambat (± 57 tok/s).
- Aturan cache Fase 1 menyingkirkan InferenceNet.
- Sticky routing mengunci satu jawaban ke satu penyedia.

**Pilihan untuk user:**
- (a) Matikan aturan cache (`AI_PROVIDER_MAX_CACHE_PRICE_RATIO`) dan kembali ke rute bawaan seperti putaran
  sebelumnya.
- (b) Kecualikan penyedia yang lambat berdasarkan kecepatan terukur dari log kita sendiri.
- (c) `AI_PROVIDER_SORT=throughput`.

**Benchmark dulu (± USD 0,05):** 10 panggilan yang sama di Morph vs Together vs DeepSeek resmi. Ukur detik dan biaya.

## Urutan usulan

1. O1 benchmark + keputusan. Ini dampak terbesar: kira-kira setengah waktu tunggu.
2. O2.
3. O4.
4. O3, menunggu persetujuan eksekusi.

Masing-masing di-benchmark dulu, lalu dilaporkan sebelum dipasang.
