# Rencana: event study dengan return abnormal, minimal 4 hipotesis teruji, lalu analisis faktor

Status: rencana, belum dijalankan. Disusun 2026-10-02, direvisi 2026-10-02 sesuai arahan user.
Terkait: `ERRORS_AND_SOLUTIONS.md` S20 (fungsi lintas saham), S22 (event study dan uji hipotesis tidak aktif),
P22 (unit dobel). Alur percakapan mode 4 ada di `MODE4_CONVERSATION_PLAN.md`.

## 1. Tujuan (user, 2026-10-02)

- Setiap pertanyaan analisis dijawab, lalu dibawa **satu langkah lebih jauh**: event study dan uji hipotesis.
- AI bisa memakai **event study** dan **uji hipotesis minimal 4 buah** dengan praktik terbaik, berdasarkan data yang
  ada di database.
- **Tidak ada yang di-hardcode.** Data masih awal; data lintas aset dan fundamental menyusul setelah mesin efisien
  dan benar.
- Jalur atau pintu (eksplorasi vs konfirmasi) dibahas **setelah** infrastruktur sanggup melayani ini.

Dua kekurangan yang disiapkan di rencana ini:
1. event study dengan **return abnormal** (dibanding pasar atau benchmark);
2. **jalur return di sekitar event** (hari −k … +h, AAR, CAR).

## 2. Kondisi sekarang (dicek di kode dan run `ma-reason-20261001b`)

- Mode 4 sudah menjawab, lalu menyusun dan langsung menguji 2–6 hipotesis. Di m01 ada 4 angle (crash_rebound,
  fall_depth, breadth_ranking, flow_leads), lengkap dengan CI 95%, p-value, koreksi Benjamini-Hochberg, holdout,
  MDE dan hitung ulang oleh backend.
- `conditional_distribution` sudah merupakan event study dasar: return ke depan setelah hari event dibanding hari
  lain, dengan tanggal yang dijarangkan sesuai horizon (`_thinned`), sehingga event tidak dihitung dobel.
- Hasil (outcome) dideklarasikan sebagai `{"forward_return": <kolom>}`, boleh dari permintaan data lain
  (`{"forward_return": c, "request": r}`, `runtime/research_inputs.py`). Return abnormal menempel di sini.
- Satu horizon per angle; tidak ada jalur hari relatif event.
- Formulir rumus riset hanya punya fungsi per entitas; rata-rata pasar memaksa jalur FRAME (S20).
- **Database belum punya tabel indeks pasar dan kapitalisasi pasar.** Benchmark sekarang harus diturunkan dari
  universe yang diminta (rata-rata lintas saham, sama bobot), dan harus bisa diganti deret indeks begitu tabelnya
  masuk, tanpa mengubah kode.
- Batas jumlah angle mode 4: minimal `max(2, AI_RESEARCH_MIN_ANGLES)` (default 2), maksimal
  `AI_RESEARCH_MAX_ANGLES` (6); batas sandbox `PY_SANDBOX_RESEARCH_MIN_ANGLES=1` di dev.

## 2b. Mesin lama yang sudah ada dan bedanya dengan rencana ini (dicek di kode 2026-10-02)

| Generasi | Di mana | Status | Cara kerja | Yang kurang |
|---|---|---|---|---|
| G1 worker statistik | `apps/market-analytics-worker/worker.py` | Service dihapus 2026-09-26 | Menjalankan SQL DuckDB tulisan AI yang diberi label `EVENT_STUDY_SQL` / `SIGNIFICANCE_TEST_SQL`; tidak ada metode bawaan | Rumus dan statistik sepenuhnya dari AI, tanpa pemeriksaan |
| G2 event study Analysis Spec | sandbox `app/spec.py` (metode `EVENT_STUDY`), `runtime/validator.py` (`_event_study_reference`, `_segment_stats`) | Jalur cadangan (aktif hanya bila DataNeed mati) | Event dari predikat sinyal; outcome FORWARD_RETURN; NON_OVERLAPPING; minimal 30 event; sensor ujung data; pembanding semua observasi eligible; mean, median, hit rate, delta; CI Welch; segmen in-sample / out-of-sample; validator menghitung ulang rumusnya | Return mentah (tanpa benchmark); satu horizon; CI menganggap baris independen (event di hari yang sama tidak dikelompokkan); koreksi hanya NONE/BONFERRONI |
| G3 riset v1 | orc `app/research_plan.py` (rencana 1–4 eksperimen, satu hipotesis per eksperimen); sandbox `app/research_governance.py`, `app/research_findings.py`, `runtime/research_stats.py`, helper `saniti.event_summary` | Tidak aktif (multi-angle menyala) | Hipotesis dideklarasikan dulu (kondisi, outcome, pembanding, arah, horizon, efek minimum, kebijakan koreksi) dan disetujui user; anggaran 4 hipotesis, 6 eksperimen, 5 tindak lanjut per hipotesis. AI membangun event dan pembanding dengan Python bebas lalu memanggil `event_summary`; backend menghitung ulang statistik dari agregat per tanggal: selisih rata-rata dan selisih proporsi sukses, pengelompokan per tanggal, penjarangan horizon, MDE, kategori sampel, vonis | Cara event dan return dibangun tidak diperiksa (hanya statistiknya); return abnormal hanya kalau AI menghitung sendiri, tanpa pemeriksaan; satu horizon; tidak ada jalur hari sekitar event |
| G4 riset multi-angle | `runtime/research_engines.py`, `app/research_methods.py`, `AI_research_library` | **Aktif** | 8 metode; peran dideklarasikan dan rumus dihitung ulang backend (DECLARATIVE) atau tabel buatan AI (FRAME); pengelompokan per tanggal; holdout; koreksi per kandidat (BONFERRONI/HOLM/BH); kategori sampel dan MDE | Tidak ada fungsi lintas saham, return abnormal, maupun jalur hari sekitar event; koreksi hanya per rencana (tanpa anggaran lintas giliran seperti G3) |

**Yang dibawa dari mesin lama ke rencana ini:**
- dari G2: definisi event, NON_OVERLAPPING, minimal event, sensor ujung data (langkah 3);
- dari G3: hipotesis dideklarasikan dulu dengan arah dan efek minimum (sudah ada di G4), batas 4 hipotesis (dijadikan
  **minimal** 4 di langkah 4), anggaran eksperimen dan tindak lanjut lintas giliran (buku percobaan, langkah 5),
  pengelompokan per tanggal dan kategori sampel (sudah ada di G4).

**Yang baru di rencana ini (tidak ada di generasi mana pun):**
- return abnormal dengan benchmark dan model return normal yang dideklarasikan dan diperiksa backend;
- jalur AAR/CAAR dengan beberapa jendela CAR yang ikut koreksi uji berganda;
- fungsi lintas saham di rumus yang diperiksa (rata-rata pasar dan sektor tanpa jalur FRAME);
- pengujian rumus event dan return oleh backend. G3 hanya memeriksa statistik; G2 memeriksa rumus tapi tanpa
  pengelompokan per tanggal.

## 3. Benchmark praktik

| Praktik | Rujukan | Yang dipakai di sini |
|---|---|---|
| Event study | MacKinlay (1997); Kothari & Warner (2007) | Return normal dari model (market-adjusted, market model, constant mean); jendela estimasi, celah, jendela event; AR, AAR, CAR, CAAR; uji CAR |
| Event yang mengelompok di tanggal sama | Kothari & Warner | Galat dari sebaran antar tanggal event, bukan antar baris |
| Uji berganda | Harvey, Liu & Zhu (2016); Benjamini-Hochberg | Setiap horizon atau ambang adalah kandidat; ambang dikoreksi |
| Data uji terpisah | Bailey & López de Prado | Holdout yang sudah ada tetap berlaku |
| Operator lintas saham | Qlib, Zipline Pipeline, WorldQuant BRAIN | `cs_*` dan `group_*` (S20 F1) |

## 4. Prinsip tanpa hardcode

1. Metode bekerja atas **peran** (`event`, `outcome`, `benchmark`, `group`, `weight`), tidak pernah atas nama tabel,
   kolom, ticker, indeks atau jenis aset.
2. **Benchmark dideklarasikan oleh AI** dan tercatat di hasil. Bentuk yang diterima:
   - deret dari permintaan data lain (`{"forward_return": c, "request": r}`), misalnya tabel indeks atau kurs nanti;
   - turunan lintas entitas dari permintaan yang sama: `cs_mean`, `cs_median`, atau `group_mean` dengan kolom
     `is_groupable` (S20 F1).

   Tidak ada benchmark default yang dipasang diam-diam. Tanpa benchmark, modelnya `RAW` atau `CONSTANT_MEAN`, dan
   labelnya tertulis di hasil.
3. **Bobot** sama secara default. Bobot lain hanya lewat peran `weight` yang dideklarasikan (misalnya kapitalisasi
   pasar setelah data fundamental masuk).
4. **Jendela dalam jumlah observasi** entitas itu (kalender perdagangan dari datanya sendiri), bukan hari kalender
   atau kalender bursa tertentu.
5. **Ambang sebagai kebijakan** dengan default yang dicatat di setiap hasil: minimal event, minimal entitas per
   tanggal untuk benchmark lintas entitas, panjang minimal jendela estimasi. Pola konfigurasi `PY_SANDBOX_RESEARCH_*`.
6. Deskripsi metode untuk AI dibangkitkan dari kode (`AI_research_library`, sudah begitu). Prompt tidak menyebut
   tabel atau kolom.

## 5. Langkah 1 — Fungsi lintas entitas (S20 F1, prasyarat)

Lapisan: mesin rumus sandbox (`runtime/expression.py`, `runtime/research_inputs.py`).
- `cs_mean`, `cs_median`, `cs_min`, `cs_max`, `cs_count`, `cs_rank`, `cs_zscore`, `cs_share(kondisi)`; `cs_sum` hanya
  untuk kolom ber-aturan SUM di katalog; `group_mean` dan `group_rank` hanya dengan kolom `is_groupable`.
- Dihitung per tanggal atas entitas permintaan itu; hanya nilai di tanggal yang sama (tidak ada nilai masa depan).
- Ditolak untuk permintaan tanpa kolom entitas atau dengan satu entitas.
- Jumlah entitas per tanggal dicatat; tanggal di bawah minimal kebijakan ditandai.
- Detail risiko dan test: S20 di `ERRORS_AND_SOLUTIONS.md`.

## 6. Langkah 2 — Return abnormal

Lapisan: builder input riset (`runtime/research_inputs.py`) dan mesin (`runtime/research_engines.py`). Tidak ada jalur
baru: outcome yang sudah ada diperluas.

- **Deklarasi outcome baru:**
  `{"abnormal_return": "<kolom harga>", "benchmark": <deklarasi benchmark>, "normal_model": "<model>"}`.
  - `benchmark`: bentuk di bagian 4 butir 2.
  - `normal_model`:
    - `MARKET_ADJUSTED`: AR = R_saham − R_benchmark;
    - `MARKET_MODEL`: AR = R_saham − (α + β·R_benchmark), dengan α dan β diestimasi per entitas di jendela
      estimasi sebelum setiap event;
    - `CONSTANT_MEAN`: AR = R_saham − rata-rata R_saham di jendela estimasi;
    - `RAW`: tanpa pengurangan (perilaku sekarang, label jelas).
  - Parameter (dari rencana yang disetujui): `estimation_window` (observasi, default kebijakan), `gap` (observasi
    antara akhir estimasi dan event, default kebijakan), batas minimal observasi estimasi.
- **Penjaga:**
  - α dan β hanya memakai observasi **sebelum** jendela event (tidak bocor);
  - event dengan estimasi terlalu pendek dikeluarkan dan dihitung di hasil;
  - benchmark lintas entitas memakai entitas yang sama dengan universe permintaan, dan jumlahnya per tanggal dicatat.
- **Dipakai oleh semua metode** yang punya peran outcome (`conditional_distribution`, `threshold_sensitivity`,
  `quantile_ranking`, `streak_persistence`, `regime_comparison`, `cohort_comparison`). Contoh: kuantil broker
  net-beli diuji terhadap return di atas sektor.
- **Hasil mencatat** model, benchmark, jendela estimasi, event yang dikeluarkan, dan β rata-rata.

## 7. Langkah 3 — Jalur return di sekitar event (event window, AAR, CAR)

Lapisan: mesin riset, metode baru `event_study` di keluarga `CONDITIONAL_OUTCOME`. Tidak perlu mengubah `CHECK`
`AI_research_library`; baris perpustakaan dibangkitkan dari kode.

- **Peran:** `event` (rumus per entitas dan tanggal, termasuk fungsi lintas entitas dari langkah 1) dan `outcome`
  (return harian atau abnormal dari langkah 2).
- **Parameter:** `event_window` [−k, +h] dalam observasi; `primary_car` (jendela CAR utama yang diuji, mis. [0, +5]);
  `secondary_cars` (opsional, ikut koreksi uji berganda); `overlap_policy` (`NON_OVERLAPPING` default: event
  berikutnya untuk entitas yang sama hanya setelah jendela event sebelumnya selesai, dari `spec.py`); `min_events`
  (kebijakan, default 30 dari `spec.py`).
- **Keluaran:**
  - AAR per hari relatif (−k … +h) dengan CI;
  - CAAR (jalur kumulatif);
  - CAR utama dan sekunder dengan uji;
  - jumlah event, entitas, tanggal event unik;
  - event yang disensor (jendela melewati ujung data) dan event yang dikeluarkan (estimasi pendek).
- **Uji:**
  - CAR dengan galat dari sebaran rata-rata per **tanggal event** (pola `_welch` / effective count yang sudah ada),
    sehingga 20 saham yang kena event di hari crash yang sama dihitung sebagai satu tanggal;
  - koreksi uji berganda atas CAR utama dan sekunder;
  - holdout seperti metode lain;
  - status keputusan memakai `decide()` yang sama.
- **Pemeriksaan arah waktu:** AAR sebelum hari 0 dilaporkan. Return abnormal yang sudah besar sebelum event adalah
  tanda kebocoran atau antisipasi, dan ditulis sebagai catatan, bukan disembunyikan.
- **Dari `spec.py` dipindahkan:** definisi event dari predikat, NON_OVERLAPPING, minimal event, sensor ujung data.

## 8. Langkah 4 — Minimal 4 hipotesis teruji

- Mode 4 langkah B membuat **minimal 4** angle. Caranya dengan konfigurasi, bukan kode: `AI_RESEARCH_MIN_ANGLES=4`
  (orc) dan `PY_SANDBOX_RESEARCH_MIN_ANGLES` ≤ 4 (sandbox). Batas maksimal tetap `AI_RESEARCH_MAX_ANGLES` (6).
  Perubahan variabel ini butuh persetujuan user saat dijalankan.
- **Keragaman tanpa hardcode:** angle diambil dari keluarga metode di `AI_research_library` (sekarang 5 keluarga, plus
  `event_study`). Pilihan `AI_RESEARCH_MIN_FAMILIES` (sudah ada, default 0) bisa dinaikkan supaya 4 angle tidak semuanya
  satu metode. Keputusan user.
- **Kalau data tidak cukup untuk 4 angle** (cek kelayakan menolak), rencana tidak diisi angle pengisi. Langkah B
  melaporkan jumlah yang layak dan alasannya. Kebijakan ini perlu dikonfirmasi (bagian 12).
- **Akibat yang diketahui:**
  - koreksi uji berganda per rencana jadi lebih ketat (lebih banyak kandidat);
  - waktu langkah C bertambah (m01: 4 angle, 156 s).

## 9. Langkah 5 dan seterusnya (setelah langkah 1–4 terbukti)

- **Analisis faktor:** perluasan `quantile_ranking` (IC IR, t-stat Newey-West, beberapa horizon, turnover, netral
  kelompok, deret return faktor) dan `cross_sectional_regression` (Fama-MacBeth) saat data fundamental masuk.
- **Buku percobaan per percakapan** (disiplin riset v1): semua angle yang pernah diuji di percakapan ikut dihitung
  dalam koreksi uji berganda.
- **Jalur dan pintu** (eksplorasi tanpa rencana vs konfirmasi): dibahas setelah ini, sesuai arahan user.

## 9b. Varian: G2 dan G3 dibangun ulang tanpa S20 (diminta user 2026-10-02, untuk ditimbang)

Langkah 1 (S20) dilewati. G2 (event study, langkah 2–3) dan G3 (disiplin hipotesis, langkah 4–5) dibangun di mesin
aktif (G4) dengan fungsi per entitas yang sudah ada.

**Yang tetap jalan penuh, diperiksa backend:**
- event yang didefinisikan **per saham** (return saham itu ≤ −5%, net jual asing terbesar saham itu dalam 60 hari,
  streak beli broker di saham itu);
- jalur AAR/CAAR dan CAR per jendela, NON_OVERLAPPING, minimal event, sensor ujung data, pengelompokan per tanggal;
- model return normal `RAW` dan `CONSTANT_MEAN`;
- `MARKET_ADJUSTED` dan `MARKET_MODEL` **hanya** dengan deret benchmark dari permintaan data lain. Database belum punya
  tabel indeks, jadi untuk saat ini praktis tidak bisa dipakai;
- seluruh G3: hipotesis dideklarasikan dulu, minimal 4, anggaran dan buku percobaan lintas giliran, kategori sampel.
  G3 tidak bergantung pada S20.

**Yang tidak bisa (atau turun ke jalur FRAME yang hanya diperiksa statistiknya):**
- return abnormal terhadap pasar atau sektor, karena benchmark "rata-rata pasar" adalah hitungan lintas saham;
- event tingkat pasar (hari crash dari rata-rata pasar, breadth harian);
- perbandingan relatif sektor dan netral sektor.

**Risiko varian ini:**

| Risiko | Dampak (non-dev) | Contoh | Mitigasi bila varian dipilih |
|---|---|---|---|
| R1. Event study tanpa pembanding pasar | Pola yang terlihat sebenarnya gerakan seluruh pasar. Ini kesalahan utama yang ingin dihindari metode MacKinlay | "Saham bank naik 5 hari setelah crash" padahal semua saham naik (pantulan pasar) | Model RAW/CONSTANT_MEAN diberi label tegas di hasil ("tidak dibandingkan pasar"); gerbang jawaban melarang kata "abnormal" / "di atas pasar" tanpa benchmark |
| R2. Pertanyaan tingkat pasar tetap lewat FRAME | Rumus event dan benchmark dibuat AI dengan Python bebas, backend hanya memeriksa statistiknya; salah rumus tidak ketahuan | m01: 2 dari 4 angle (crash_rebound, fall_depth) memang FRAME | Tingkat pemeriksaan FRAME ditulis di jawaban; jumlah angle FRAME diukur tiap suite |
| R3. Godaan jalan pintas yang di-hardcode | Untuk menutup R1, muncul "rata-rata pasar bawaan" di dalam event study. Itu S20 versi sempit, dan nanti ada dua implementasi berbeda | Benchmark bawaan sama bobot yang diam-diam dipakai | Tidak membuat benchmark bawaan. Kalau dibutuhkan, dibuat sebagai fungsi internal yang nanti dibuka oleh S20 (satu jalur kode) |
| R4. Minimal 4 hipotesis dengan alat terbatas | AI punya lebih sedikit metode yang diperiksa penuh untuk pertanyaan pasar, sehingga 4 angle cenderung jatuh ke FRAME atau angle yang lemah | Pertanyaan crash: hampir semua angle butuh rata-rata pasar | Tidak ada angle pengisi; jumlah layak dilaporkan; keputusan 3 di bagian 12 |
| R5. Kerja ulang | Saat S20 masuk, deklarasi benchmark, test dan deskripsi metode diperluas lagi | Migrasi `AI_research_library` dua kali | Skema benchmark sejak awal sudah menyediakan tempat untuk bentuk lintas entitas (ditolak dengan pesan jelas sampai S20 ada) |
| R6. Ekspektasi user | Fitur "event study" ada, tapi jawaban crash tetap memakai return mentah | User membaca CAR sebagai return abnormal | Label model di setiap angka (R1) |

**Penilaian:** G3 aman dibangun tanpa S20. Untuk G2, varian ini memberi event study yang benar untuk event per saham,
tapi tidak untuk pertanyaan pasar dan sektor. Padahal pertanyaan pasar adalah sebagian besar pertanyaan seperti m01,
dan R1 adalah jenis kesalahan yang paling sering terjadi di event study.

## 10. Risiko dan mitigasi

| Risiko | Penjelasan non-dev | Mitigasi |
|---|---|---|
| Benchmark buatan dari universe | "Pasar" = rata-rata saham yang diminta; universe kecil membuat benchmark bias | Jumlah entitas per tanggal dicatat; minimal entitas dari kebijakan; benchmark selalu tertulis di hasil; tabel indeks nanti cukup dideklarasikan |
| Bocor waktu di market model | α/β diestimasi memakai data di sekitar event | Jendela estimasi berakhir sebelum `gap`; test khusus |
| Event mengelompok | Hari crash membuat banyak event sekaligus | Galat per tanggal event; jumlah tanggal unik dilaporkan |
| Terlalu banyak uji | CAR berbagai jendela dan 4+ angle membuat "kebetulan signifikan" | Semua jendela CAR dan angle masuk koreksi; holdout; buku percobaan (langkah 5) |
| Angle pengisi | Memaksa 4 angle saat data tidak cukup | Tidak ada angle pengisi; jumlah layak dan alasannya dilaporkan |
| Waktu | Langkah C lebih lama | Diukur pada m01; tuas kecepatan di rencana kecepatan tetap berlaku |
| Hardcode tersisip | Default diam-diam | Test dengan data sintetis non-saham dan nama kolom lain; review untuk literal tabel/kolom/ticker |
| Unit dobel di jawaban (P22) | "−0,10 pp pp" | Perbaikan P22 di lapisan render, sebelum uji live |

## 11. Verifikasi

- **Test terhadap perhitungan independen** (data sintetis dengan efek tertanam):
  - AR, AAR, CAR, CAAR dibandingkan dengan perhitungan pandas/statsmodels yang ditulis terpisah;
  - β market model sama dengan OLS statsmodels di jendela estimasi;
  - tidak ada observasi jendela event di estimasi;
  - NON_OVERLAPPING dan sensor ujung data;
  - galat per tanggal event.
- **Test tanpa hardcode:** event study atas deret sintetis bergaya FX dengan benchmark dari permintaan lain.
- **Uji live (saklar pikiran menyala):**
  - m01 (crash: return abnormal saham bank vs rata-rata universe);
  - "Bagaimana return abnormal saham bank 10 hari setelah net jual asing terbesar?" (event study dengan jendela
    [−2, +10]);
  - satu pertanyaan non-bank (sektor lain) untuk memastikan tidak ada asumsi bank;
  - minimal 4 angle per rencana; dicatat waktu langkah C dan jumlah angle yang layak.
- **Kasus yang tidak cocok:** data makro satu deret, karena benchmark lintas entitas tidak bermakna. Event study tetap
  bisa dengan `CONSTANT_MEAN` atau benchmark dari permintaan lain.

## 12. Keputusan yang diminta dari user

1. Setuju urutan langkah 1 → 2 → 3 → 4 (lalu P22 sebelum uji live)?
2. Minimal 4 angle: set `AI_RESEARCH_MIN_ANGLES=4` di dev saat langkah 4?
3. Kalau data hanya layak untuk < 4 angle: laporkan jumlah yang layak (usulan), atau tetap paksa 4?
4. Naikkan `AI_RESEARCH_MIN_FAMILIES` supaya 4 angle memakai metode yang beragam?

## Rujukan

- MacKinlay (1997), *Event Studies in Economics and Finance*; Kothari & Warner, *Econometrics of Event Studies*.
- Harvey, Liu & Zhu (2016), *…and the Cross-Section of Expected Returns*.
- Bailey & López de Prado, *Statistical Overfitting and Backtest Performance*.
- Qlib, Zipline Pipeline, WorldQuant BRAIN (operator lintas saham); Alphalens; Fama-MacBeth (tidy-finance.org).
