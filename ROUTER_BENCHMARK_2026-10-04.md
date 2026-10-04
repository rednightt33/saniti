# Benchmark: router untuk pesan pertama (2026-10-04)

Status: **BENCHMARK, belum ada perubahan kode.** Perubahan ini mengganti perilaku bawaan mode 4 (keputusan user
2026-09-30), sehingga butuh keputusan user.

## Masalah sekarang (terverifikasi dari kode dan log)

- Pesan pertama tidak dinilai siapa pun. `AI_MODE_SWITCH=4` membuat setiap pesan pertama tanpa `analysis_path`
  menjalani A analisis → B rencana riset → C riset → D usulan (`app/mode4.py` `first_round`).
- Satu-satunya syarat B jalan adalah A tidak gagal (`_ok(analysis, "ANSWER", "LIMITATION")`).
- Router percakapan (`app/conversation_router.py`) hanya membaca pesan lanjutan.
- **Bukti:** g13 ("BBCA dan BRIS BUMN?"). A menjawab benar dari web dalam 32 detik, lalu B–D berjalan 23 menit,
  USD ± 0,04.
- Sapaan seperti "bagaimana kabarmu" bisa mengalami hal yang sama bila A memilih tipe ANSWER (dari kode, belum
  dicoba live).
- **Kelas:** setiap pesan pertama yang bukan pertanyaan data (sapaan, definisi, fakta perusahaan, pertanyaan tentang
  data yang tersedia).

## Praktik eksternal

| Sumber | Praktik |
|---|---|
| [Anthropic, Building effective agents](https://www.anthropic.com/engineering/building-effective-agents) | Pola "routing": satu panggilan LLM mengklasifikasi input lalu mengarahkannya ke alur khusus; cocok bila kategorinya jelas dan klasifikasi bisa akurat. Pertanyaan mudah diarahkan ke jalur murah |
| [OpenAI Agents SDK, handoffs](https://openai.github.io/openai-agents-python/handoffs/) dan [panduan membangun agen](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf) | Pesan pertama masuk ke "triage agent" yang mengenali niat lalu menyerahkan ke spesialis; pisahkan alur hanya bila instruksi, alat atau kebijakannya berbeda |
| [RouteLLM](https://arxiv.org/html/2406.18665v4), [vLLM Semantic Router](https://arxiv.org/pdf/2510.08731) | Routing pertanyaan sederhana vs kompleks menghemat biaya 40–85% dengan kualitas terjaga; router semantik juga memangkas token dan latensi ± 50% |

**Kesimpulan:** router di depan (triage) adalah praktik standar. Menjalankan pipeline penuh untuk setiap pesan
pertama bukan praktik standar.

## Benchmark internal

**Setup:**
- Prototipe router pesan pertama: satu panggilan tanpa alat, JSON, 5 rute:
  - CHAT (sapaan);
  - FACT (definisi, fakta, isi katalog);
  - ANALYSIS (hitung deskriptif satu langkah);
  - RESEARCH (uji hipotesis dengan rencana);
  - EXPLORE (pertanyaan terbuka: analisis lalu sudut riset, seperti mode 4 sekarang).
- Aturan bila ragu: pilih ANALYSIS, karena pertanyaan data yang dijawab tanpa data adalah kesalahan termahal.
- Setiap pesan dinilai 2×.
- Skrip: scratchpad `route_bench.py`, `route_cases_dev.json`, `route_cases_heldout.json`.

**Set pengembangan:** 30 pesan dari golden test dan suite ini ditambah sapaan. Label dan instruksi ditulis sambil
melihat set ini.

| Model | Benar | Data → tanpa data | Tanpa data → data | Tidak stabil | Biaya 60 panggilan | Median detik |
|---|---|---|---|---|---|---|
| DeepSeek V4.1 Flash, reasoning low | 58/60 | 0 | 0 | 0/30 | USD 0,0056 | 1,9 |
| DeepSeek V4.1 Flash, reasoning mati | 57/60 | 0 | 0 | 3/30 | USD 0,0025 | 1,5 |
| Qwen 3.7 Flash, reasoning mati | 58/60 | 0 | 0 | 0/30 | USD 0,0011 | 1,6 |

**Set uji tersembunyi:**
- 16 pesan baru dengan gaya berbeda: bahasa Inggris, singkatan dan typo, sapaan yang disertai pertanyaan
  ("halo, tolong hitung return BBCA 2024", "pagi bro, gimana pasar hari ini?").
- Label ditulis sebelum dijalankan.

| Model | Benar | Data → tanpa data | Tanpa data → data | Tidak stabil |
|---|---|---|---|---|
| DeepSeek V4.1 Flash, reasoning low | 31/32 | 0 | 0 | 1/16 |
| DeepSeek V4.1 Flash, reasoning mati | **32/32** | 0 | 0 | 0/16 |
| Qwen 3.7 Flash, reasoning mati | 29/32 | **1** ("pagi bro, gimana pasar hari ini?" → CHAT) | 0 | 1/16 |

**Kesalahan yang tersisa:**
- Batas EXPLORE vs RESEARCH/ANALYSIS, misalnya "sektor apa yang diuntungkan kalau BI turunkan suku bunga". Kesalahan
  ini murah: semua rute itu tetap menarik data.
- Tidak ada pertanyaan data yang diarahkan ke jalur tanpa data oleh DeepSeek.

**Batas benchmark ini:**
- Setnya kecil (46 pesan) dan labelnya dari satu penilai.
- Sebelum dipasang, set uji perlu diperluas dari pertanyaan user nyata, termasuk pesan lanjutan yang sudah ditangani
  router sekarang, agar router baru tidak merusaknya.

## Usulan (butuh keputusan user)

1. **Router di depan untuk pesan pertama:** DeepSeek V4.1 Flash, model yang sama dengan router sekarang, satu panggilan
   ± 1–2 detik, USD < 0,0001 per pesan. Dipakai hanya bila pemanggil tidak menetapkan `analysis_path`.
   - **CHAT dan FACT:** satu langkah tanpa tarik data (fakta web dan katalog tetap boleh).
   - **ANALYSIS:** satu langkah analisis, tanpa B–D.
   - **RESEARCH:** rencana untuk persetujuan user.
   - **EXPLORE:** mode 4 penuh seperti sekarang.
2. **Penahan dari backend (permanen, bukan hanya prompt):**
   - Langkah B–D mode 4 hanya jalan bila jawaban A memakai angka dari data, menurut catatan sumber angka (provenance)
     yang sudah ada. Ini juga menahan kesalahan router.
   - Router tidak dipakai bila pemanggil memilih mode.
3. **Verifikasi:**
   - set uji diperluas;
   - live: "bagaimana kabarmu", g13 dan q1 masing-masing sekali; ukur detik dan biaya dibanding sekarang
     (g13: 23 menit → target < 1 menit).

**Tidak mencakup:** pesan lanjutan. Pesan lanjutan tetap memakai router percakapan yang ada; kelas keduanya perlu
diselaraskan saat dibangun.
