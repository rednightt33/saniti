# Benchmark visual: siapa memilih grafik dan data (2026-10-04)

Status: **BENCHMARK, belum ada perubahan kode.** Visual memakai ECharts (keputusan user); yang dinilai adalah siapa
yang memilih jenis grafik dan data, dan apakah datanya tersedia.

## 1. Apa yang dikirim jawaban selain teks (inventaris)

Sumber: 16 jawaban COMPLETED (golden test `ma-golden-final-20261004a` + suite `ma-qa-20261004a`).

| Bagian respons | Isi | Bisa jadi grafik? |
|---|---|---|
| `response.answer` | Teks + tabel markdown (15 dari 16 jawaban punya tabel markdown) | Tidak langsung; angka sudah dirender jadi teks |
| `data_record.outputs[]` | 27 TABLE + 5 JSON yang dirilis: `ref`, nama, **nama kolom**, `row_count`, definisi, lineage, `data_as_of` | **Ya**, tetapi respons hanya berisi metadata; barisnya disimpan backend (sandbox 24 jam, lalu R-STORE) dan dibaca lewat `stored-tables/page` |
| `evidence[]` | Klaim + status; baris bukti (≤ 200) hanya untuk cek BASE_TABLE | Terbatas |
| `research_findings` | Statistik per sudut riset | Ya (ringkasan) |
| Chart PNG (`CHART`, matplotlib) | Didukung sandbox lama, **0 kali dipakai** | Tidak cocok untuk ECharts |

**Celah yang ditemukan:**
1. **Tipe dan satuan kolom tidak tercatat.** Metadata output hanya punya nama kolom, tanpa dtype (tanggal, angka,
   teks) atau satuan (%, rupiah, lembar). Karena itu tidak bisa dicek otomatis apakah grafik mencampur satuan pada
   satu sumbu (contoh dari benchmark: `zscore` dan `volume` di satu sumbu).
2. **Data tingkat baris tidak selalu dirilis.** q5 (EMA cross) menyebut 657 kejadian sejak 2020, tetapi yang dirilis
   hanya 1 baris statistik. Distribusi return per kejadian tidak bisa digambar. g3 dan g5.4 merilis tabel per kejadian
   (2.258 dan 2.954 baris), sehingga histogram bisa digambar.
3. 5 dari 16 jawaban (pertanyaan lanjutan dan lineage) tidak merilis tabel baru. Grafiknya, bila ada, memakai tabel
   giliran sebelumnya.

## 2. Benchmark model: dari (pertanyaan, jawaban, metadata tabel) ke spesifikasi grafik

**Setup:**
- Model hanya melihat nama tabel, kolom dan jumlah baris, tanpa nilai.
- Model mengusulkan maksimal 2 grafik dalam JSON (`table_ref`, `chart_type`, `x`, `y`, `series`), atau tidak sama
  sekali.
- 16 kasus × 4 model, reasoning mati.
- Skrip: scratchpad `viz_bench.py`.

**Valid struktur** artinya JSON benar dan semua tabel serta kolom ada. **Tepat makna** dinilai manual: grafik
menjawab pertanyaan, sumbu masuk akal, dan tidak ada satuan campur.

| Model | JSON valid | Grafik diusulkan | Valid struktur | Tepat makna (manual) | Biaya 16 kasus | Median detik |
|---|---|---|---|---|---|---|
| `deepseek/deepseek-v4.1-flash` (model utama sekarang) | 16/16 | 24 | 24 | **± 22** (2 lemah) | USD 0,0033 | 2,0 |
| `qwen/qwen3.7-flash` | 16/16 | 25 | 25 | ± 19 | USD 0,0008 | 3,1 |
| `mistralai/ministral-8b-2512` | 16/16 | 32 | 28 | ± 14 | USD 0,0011 | 3,1 |
| `ibm-granite/granite-4.2-8b` | 16/16 | 20 | 19 | ± 12 | USD 0,0014 | 5,0 |

**Contoh nyata:**
- **q4 candle.** DeepSeek memilih `candlestick` dari `out.o2` (OHLC per ticker) dan bar jumlah pola, keduanya tepat.
  Qwen memilih scatter harga close, yang lemah. Ministral menaruh teks `pattern` di sumbu Y, yang salah.
- **q1 Z-score.** Semua model memilih bar Z-score per ticker dan line volume 20 hari, tepat. Ministral dan Granite
  mencampur `zscore` dan `volume` di satu sumbu (satuan campur).
- **g3 event study.** Hanya Qwen yang mengusulkan histogram return per event (`out.o2`, 2.258 baris). DeepSeek hanya
  membuat bar mean/median.
- **q5 EMA.** Qwen mengusulkan histogram dari tabel 1 baris (salah). Penyebabnya: tabel per kejadian tidak dirilis
  (celah 2).
- **g7_lineage.2 (pertanyaan asal-usul angka).** DeepSeek, Qwen dan Granite tepat tidak mengusulkan grafik. Ministral
  mengarang tabel `out.o1`.
- **Kesalahan yang berulang di model kecil:** mengarang kolom atau tabel, nilai teks di sumbu angka, dan dua satuan di
  satu sumbu.

**Riset eksternal (pembanding):**
- [VisEval](https://www.researchgate.net/publication/383919090_VisEval_A_Benchmark_for_Data_Visualization_in_the_Era_of_Large_Language_Models)
  dan [Text2Vis](https://arxiv.org/pdf/2507.19969) mencatat kegagalan yang sama: makna salah, kode tidak jalan,
  grafik sulit dibaca.
- [Evaluasi LLM untuk visualisasi](https://arxiv.org/html/2507.22890v1): pembuatan spesifikasi deklaratif
  (Vega-Lite) jauh lebih sering gagal daripada kode Python, misalnya GPT-4o 70% vs 95%.
- [LIDA (Microsoft)](https://github.com/microsoft/lida) memisahkan ringkasan data (dtype dan statistik dari pandas)
  dari pemilihan grafik oleh LLM.
- [Databricks Genie](https://answers.databricks.com/ai-analytics-platforms-best-data-visualization-recommendations)
  memprofil tipe kolom, kardinalitas dan relasi dari metadata katalog dulu, baru mencocokkan jenis grafik.
- **Kesimpulan:** model hanya memilih, sedangkan tipe data dan nilai diurus backend.

## 3. Usulan (belum dieksekusi)

**Satu model:** DeepSeek V4.1 Flash, model utama yang sama, dipanggil **sekali setelah jawaban final lolos gerbang**.
- Panggilan ini terpisah, tanpa alat, reasoning mati: ± 2 detik dan ± USD 0,0002 per jawaban.
- Tidak digabung ke jawaban final, karena setiap putaran gerbang akan menulis ulang spesifikasi grafik.
- Hasil benchmark menunjukkan model ini paling tepat, jadi tidak perlu model kedua.

**Pembagian kerja:**

| Siapa | Tugas | Lapisan |
|---|---|---|
| Sandbox (saat rilis) | Mencatat dtype, satuan (dari katalog kolom sumber atau definisi output) dan peran kolom (waktu/entitas/ukuran/kategori) di metadata output | Kontrak output, diturunkan dari data, bukan daftar nama |
| Model (sekali) | Memilih tabel, jenis grafik, kolom x/y/seri dan judul dari metadata itu, atau tidak ada grafik | orc |
| Backend | Memvalidasi: tabel dan kolom ada, tipe cocok dengan jenis grafik (line butuh sumbu waktu/urut, candlestick butuh OHLC, satu satuan per sumbu), batas titik (bin/agregasi di backend bila terlalu banyak). Lalu mengisi `series` ECharts dari baris yang tersimpan (`stored-tables/page`). **Model tidak pernah menulis angka** | orc + sandbox |
| Front-end | Merender opsi ECharts apa adanya | front-end |

**Celah data (permanen, bukan prompt saja):**
- Analisis yang melaporkan statistik dari kejadian juga merilis tabel per kejadian, seperti yang sudah dilakukan
  helper `event_study`. Pengecekan rilis bisa memastikannya. Ini perlu didesain bersama gerbang kelengkapan rilis.

**Mencakup:**
- semua tabel output, termasuk data makro dan lintas aset nanti, karena tipe kolom diturunkan saat rilis;
- pertanyaan lanjutan yang memakai tabel giliran lama.

**Tidak mencakup:**
- grafik yang butuh hitung baru, misalnya indikator yang tidak ada di tabel; itu harus dirilis analisis dulu;
- anotasi pola di atas candlestick (markPoint) perlu join dua tabel, yaitu jenis "overlay" yang belum diuji.

**Benchmark lanjutan sebelum dibangun:**
- ulangi 16 kasus dengan metadata dtype dan satuan;
- tambah kasus jawaban yang memakai tabel giliran lama;
- ukur apakah kesalahan satuan campur dan kolom karangan turun menjadi 0 setelah validasi backend.
