# Benchmark: data apa yang ditampilkan ke user, dalam bentuk apa (2026-10-04)

Status: **BENCHMARK, belum ada perubahan kode.** Lanjutan dari `VISUAL_BENCHMARK_2026-10-04.md`. Benchmark itu
menilai jenis grafik; benchmark ini menilai pemilihan tabel mana yang ditampilkan dan bentuknya.

## Masalahnya

Satu jawaban merilis 1–7 tabel. Sebagian adalah hasil utama, sebagian tabel antara:
- baseline, hitungan alur, data masukan riset;
- **salinan dengan nama sama**: g1 merilis `top10_bank_foreign_net_2025` tiga kali, g7.3 merilis
  `bbca_share_monthly_by_year` dua kali.

Menampilkan semuanya membanjiri user; memilih yang salah menyembunyikan hasil.

**Sinyal yang sudah dimiliki backend:**
- tabel yang **dirujuk** teks jawaban (`{{out.oN…}}`, dicatat sebagai bukti DIRUJUK);
- nama dan jumlah baris tabel;
- urutan rilis.

**Temuan saat menyiapkan benchmark:** daftar rujukan di respons API (`evidence[]` DIRUJUK) **dipotong di 20 rujukan**
(`_evidence`, `state.referenced[:20]`). Akibatnya tabel yang dirujuk belakangan tidak muncul. Contoh: statistik
sejak 2020 di q5.

## Setup

- **Data:** 16 jawaban COMPLETED (golden test + `ma-qa-20261004a`).
- **Label ditulis sebelum dijalankan** (scratchpad `display_labels.json`). Per jawaban:
  - tabel **wajib** tampil;
  - tabel **opsional**;
  - tabel yang wajib berbentuk **kartu KPI** (ringkasan 1 baris).
  - Tabel antara (`*_baseline`, `*_flow`, `research_input_*`) tidak ditampilkan secara bawaan.
- **Aturan backend murni (tanpa model):**
  - tampilkan tabel yang dirujuk jawaban, salinan bernama sama diambil yang terakhir;
  - bentuk dari jumlah baris: 1 baris → KPI, ≤ 50 → tabel + grafik, > 50 → unduhan saja.
- **Model:** DeepSeek V4.1 Flash, reasoning low, satu panggilan. Model menerima pertanyaan, jawaban, metadata tabel
  dan daftar rujukan, lalu memilih tabel dan bentuk: `kpi`, `table`, `chart`, `table_and_chart`, `download_only`.
- **Skrip:** scratchpad `display_bench.py`.

## Hasil

| Cara | Tabel wajib tampil | Tabel antara ikut tampil | Salinan ganda | Bentuk KPI tepat | Biaya | Waktu |
|---|---|---|---|---|---|---|
| Aturan backend (rujukan + jumlah baris) | 15/20 | 2 (`drop5_flow`, `sq_bigbuy_5d_flow`) | 0 | 15/16 | 0 | 0 |
| **Model** (DeepSeek V4.1 Flash, low) | **19/20** | **0** | **0** | **16/16** | USD 0,011 untuk 16 (± USD 0,0007 per jawaban) | median ± 7 detik |

**Kenapa aturan backend kurang:**
1. Rujukan dipotong 20, sehingga statistik q5 hilang.
2. Tabel yang dipakai untuk grafik sering tidak dirujuk teks. Contoh: jendela OHLC candle q4, dan tren bulanan g7.2 dan
   g7.3.
3. Tabel antara yang dirujuk untuk satu angka (jumlah event yang dipakai) ikut tampil.

**Kesalahan model:**
- q4: tidak menampilkan `candle_window` (data candlestick). Benchmark visual menunjukkan model memilih candlestick bila
  diminta merancang grafik.
- **1 dari 16 gagal dua kali** (respons kosong, pola M78) pada g4. Jawaban g4 berupa temuan riset tanpa tabel hasil
  (M80), sehingga tidak ada yang wajib tampil.
- Bentuk "table" sering dipilih untuk tabel yang lebih jelas sebagai grafik (g2, 48 baris). Pemilihan jenis grafik
  sudah diukur terpisah di benchmark visual.

## Kesimpulan dan usulan (belum dieksekusi)

**Satu panggilan model:** DeepSeek V4.1 Flash, low, setelah jawaban final lolos gerbang. Panggilan ini menghasilkan
**rencana tampilan lengkap**:
- blok yang ditampilkan, berurutan;
- bentuk tiap blok (KPI, tabel, grafik, unduhan);
- untuk grafik: jenis dan kolomnya. Ini menggabungkan benchmark visual: satu panggilan, bukan dua.

**Backend menyiapkan sinyal yang lebih baik dan menjaga hasilnya** (permanen):
1. **Daftar rujukan lengkap** untuk perencana tampilan (tidak dipotong 20). Respons API tetap boleh meringkas.
2. **Salinan bernama sama digabung** sebelum ditunjukkan ke model; diambil yang terakhir.
3. **Tipe dan satuan kolom** dicatat saat rilis (dari benchmark visual).
4. **Validasi:** tabel ada, kolom ada, bentuk sesuai jumlah baris. Tabel > 5.000 baris tidak dijadikan tabel tampil
   (unduhan atau grafik teragregasi).
5. **Gagal atau kosong:** jatuh ke aturan backend (rujukan + jumlah baris), sehingga user tetap melihat tabel yang
   dirujuk. Tidak pernah tanpa apa-apa.
6. **Temuan riset** menjadi tabel standar (M80 a, sudah disetujui), sehingga jawaban riset seperti g4 punya sesuatu
   untuk ditampilkan.

**Front-end:** merender blok apa adanya (ECharts untuk grafik); angka selalu diisi backend dari tabel tersimpan.

**Mencakup:** semua jawaban yang merilis tabel, termasuk pertanyaan lanjutan dan data makro nanti.

**Tidak mencakup:** tampilan yang butuh data yang belum dirilis (misalnya distribusi per kejadian bila analisis hanya
merilis ringkasan); itu celah rilis yang dicatat di benchmark visual.

**Benchmark lanjutan sebelum dibangun:**
- ulangi dengan rujukan lengkap, salinan digabung, dan tipe kolom;
- tambah jawaban riset setelah M80 a;
- ukur kegagalan dengan percobaan ulang (M78);
- target: tabel wajib 20/20, tabel antara 0.

## Benchmark dengan praktik eksternal

| Sumber | Siapa memilih **data apa** yang ditampilkan | Siapa memilih **bentuk/grafik** | Nilai angka |
|---|---|---|---|
| [Tableau Pulse](https://help.tableau.com/current/online/en-us/pulse_insights_platform_insight_types.htm) | Metrik yang didefinisikan + **jenis insight tetap** (perubahan antar periode, outlier, kontributor, korelasi); hanya **insight teratas** per metrik yang ditonjolkan | Template per jenis insight | Mesin metrik |
| [ThoughtSpot / Spotter](https://docs.thoughtspot.com/cloud/26.10.0.cl/charts) | Hasil query yang menjawab pertanyaan (satu hasil = satu visual) | **Otomatis dari data hasil** (tipe kolom); user bisa ganti ke 25 jenis grafik | Mesin query |
| [Databricks Genie](https://answers.databricks.com/ai-analytics-platforms-best-data-visualization-recommendations) | Hasil SQL pertanyaan | Profil data (tipe kolom, kardinalitas, deret waktu) → aturan pencocokan grafik; metadata katalog | Mesin query |
| [Tableau Show Me / Draco](https://idl.cs.washington.edu/files/2023-Draco2-VIS.pdf) | — | **Aturan dan constraint** dari tipe data: aturan keras (tidak boleh dilanggar) + preferensi berbobot hasil eksperimen persepsi | — |
| [Generative UI, Vercel AI SDK / json-render](https://ai-sdk.dev/v4/docs/ai-sdk-ui/generative-user-interfaces) | Model memilih **dari katalog komponen tetap** (kartu KPI, grafik, tabel) | Spesifikasi JSON dibatasi skema; **setiap field divalidasi, jangan pernah meneruskan argumen model mentah ke komponen** | Data dari tool, bukan model |
| [LIDA](https://github.com/microsoft/lida) | LLM membuat tujuan eksplorasi dari ringkasan data | LLM membuat kode grafik, lalu dievaluasi dan diperbaiki | Kode dieksekusi atas data |

**Pola bersama:**
1. **Nilai angka tidak pernah dari model.** Usulan kita sudah sesuai.
2. **Bentuk/jenis grafik diputuskan aturan dari tipe data.** Contoh: Show Me, Draco, ThoughtSpot, Genie. Model paling
   jauh mengusulkan, dan usulannya divalidasi aturan keras.
3. **Pilihan dari katalog komponen tetap**, divalidasi skema.
4. **Satu pesan utama ditonjolkan** (insight teratas / kartu KPI), detail di bawahnya.
5. **User bisa mengganti bentuk** (ThoughtSpot): backend menawarkan semua bentuk yang sah, bukan hanya satu.

**Selisih usulan awal kita dengan praktik:**

| Aspek | Usulan awal | Praktik | Perbaikan usulan |
|---|---|---|---|
| Jenis grafik | Dipilih model | Dipilih aturan dari tipe data | **Aturan backend (gaya Draco: aturan keras + preferensi) menentukan jenis dan encoding**; model hanya mengusulkan, dan usulan dipakai bila lolos aturan |
| Tipe kolom | Belum ada | Prasyarat semua sistem | Wajib dicatat saat rilis (sudah di usulan) |
| Data apa yang tampil | Model + rujukan jawaban | Hasil yang menjawab pertanyaan + insight teratas | Sama: rujukan jawaban (lengkap) + model memilih urutan dan yang ditonjolkan |
| Ganti bentuk oleh user | Tidak ada | Ada | Backend mengirim daftar bentuk yang sah per blok; front-end menampilkan pilihan |
| Katalog komponen | kpi/table/chart/download | Katalog tetap + skema | Sama, ditambah validasi skema ketat |

**Usulan yang direvisi:**
- **Model** (satu panggilan, DeepSeek V4.1 Flash low) memutuskan **apa** yang ditampilkan dan **urutannya**: blok
  utama, kartu KPI, detail.
- **Aturan backend** memutuskan **bagaimana**: jenis grafik dan encoding dari tipe/satuan/kardinalitas kolom, plus
  daftar alternatif yang sah.
- **Backend** mengisi angka.

Pembagian ini sesuai praktik semua sistem di atas, dan menutup kelemahan model di benchmark visual (teks di sumbu
angka, satuan campur).

**Benchmark lanjutan:** setelah tipe kolom tercatat, bandingkan jenis grafik dari aturan dan dari model pada 16 kasus
yang sama.
