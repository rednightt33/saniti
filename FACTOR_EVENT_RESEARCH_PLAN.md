# Rencana: event study, disiplin uji hipotesis dan analisis faktor untuk AI

Status: rencana, belum dijalankan (2026-10-02). Menunggu keputusan user di bagian 10.
Terkait: `ERRORS_AND_SOLUTIONS.md` S20 (fungsi lintas saham) dan S22 (event study dan uji hipotesis tidak aktif).

## 1. Permintaan user (2026-10-02)

- Event study lama (item 2) boleh dihidupkan kembali dengan **return abnormal**.
- Disiplin uji hipotesis riset v1 (item 3) ikut ditambahkan.
- Analisis faktor (factor return): benchmark dulu, lihat infrastruktur kita, lalu putuskan cara integrasinya.
- **Tujuan:** AI bisa memakai alat ini kapan pun ia menilai alat itu membantu.
- **Syarat:** tidak ada metode yang di-hardcode. Data masih awal; data lintas aset dan fundamental akan menyusul
  setelah mesin berjalan efisien dan benar.

## 2. Benchmark: cara quant house menganalisis data harga

| Praktik | Rujukan | Inti metode |
|---|---|---|
| Event study | MacKinlay (1997); Kothari & Warner (2007) | Return abnormal = return aktual − return normal. Return normal dari model pasar (alpha + beta × return pasar, diestimasi di jendela estimasi sebelum event), market-adjusted, atau rata-rata konstan. Jendela estimasi / event / sesudah event. CAR (return abnormal kumulatif) diuji statistik. |
| Evaluasi faktor | Alphalens (Quantopian) | Per tanggal: saham dibagi kuantil menurut faktor. Return per kuantil, spread atas−bawah, IC (korelasi peringkat faktor vs return berikutnya), IC IR (rata-rata IC ÷ simpangannya), t-stat, beberapa horizon (peluruhan), turnover / autokorelasi peringkat, rincian per sektor, opsi demean (netral sektor). |
| Return faktor | Fama-French (sort dan portofolio long-short); Fama-MacBeth (regresi lintas saham per periode, rata-rata koefisien, galat Newey-West) | Faktor diubah menjadi deret return portofolio (long atas, short bawah) atau premi per unit eksposur. Deret ini bisa diuji dan dibandingkan antar faktor. |
| Disiplin uji | Harvey, Liu & Zhu (2016); Bailey & López de Prado (Deflated Sharpe, purged CV) | Semakin banyak yang dicoba, ambang harus naik (t ≈ 3, bukan 2). Semua percobaan dihitung, termasuk yang gagal dan pengulangan. Data uji dipisah dari data penemuan. |
| Agen AI untuk faktor | Microsoft Qlib + RD-Agent | Agen membuat dan menguji faktor; evaluasinya standar (IC, ICIR, rank IC, return tahunan) dan dihitung oleh mesin, bukan oleh agen. |
| Alat untuk agen | Anthropic, *Writing effective tools for agents* | Alat menangani pekerjaan yang sering berulang dalam satu panggilan dan mengembalikan konteks yang bermakna. |

## 3. Infrastruktur kita sekarang (dicek di kode)

| Komponen | Status | Isi yang relevan |
|---|---|---|
| Riset multi-angle (`runtime/research_engines.py`, `app/research_methods.py`) | **Aktif** | 8 metode. `quantile_ranking` sudah berisi inti Alphalens: kuantil per tanggal, spread atas−bawah, monotonisitas, rata-rata IC. Uji Welch, p-value, koreksi uji berganda (NONE/BONFERRONI/HOLM/BH), holdout, minimum sampel, MDE. Backend menghitung ulang setiap angle. |
| Perpustakaan metode (`AI_research_library`, alat `get_research_library`) | Aktif | Deskripsi metode untuk AI, **dibangkitkan dari kode** (hash-bound). Menambah baris tidak membuat metode; mesinnya tetap kode. |
| Formulir rumus riset (`runtime/expression.py`) | Aktif | Hanya fungsi per entitas (`lag`, `rolling_*`). Belum ada fungsi lintas entitas (S20). |
| Event study Analysis Spec (`app/spec.py`) | Tidak aktif (jalur cadangan) | Aturan yang berguna: event dari predikat sinyal, NON_OVERLAPPING, minimal 30 event, event terpotong di ujung data disensor, pembanding ALL_ELIGIBLE. **Tanpa** return abnormal dan tanpa uji signifikansi. |
| Riset v1 (`app/research_governance.py`) | Tidak aktif (multi-angle menyala) | Anggaran eksperimen, hipotesis dan tindak lanjut per run; `followup_of` dihitung ke hipotesis induknya. |
| Jumlah uji untuk koreksi (orc `research_plan_v2.py` ~563) | Aktif | Dihitung **per rencana** (jumlah kandidat angle di rencana itu). Tidak ditemukan penghitungan uji dari rencana atau giliran sebelumnya di percakapan yang sama (dugaan: tidak ada; dicek lagi saat implementasi). |
| Sesi analisis (`runtime/saniti_session.py`) | Aktif | AI menulis Python bebas dengan helper (`load`, `sql`, `period_return`, `resample`, `join`, ...). Belum ada helper event study atau faktor. |
| Worker statistik lama (`market-analytics-worker`) | Dihapus 2026-09-26 | Baris `Tool_Catalog` (`run_event_study`, `run_signal_validation`, ...) tersisa tanpa pembaca. |

## 4. Selisih dengan benchmark

| Kemampuan | Ada? | Catatan |
|---|---|---|
| Return abnormal (vs pasar / sektor / benchmark) | Tidak | Butuh deret return normal per tanggal: fungsi lintas entitas (S20 F1) atau deret benchmark yang dideklarasikan. |
| Jendela estimasi / event, CAR, uji CAR | Tidak | |
| Kuantil, spread, monotonisitas, rata-rata IC | Ya | `quantile_ranking` |
| IC IR, t-stat IC (Newey-West), beberapa horizon (peluruhan) | Sebagian | Satu horizon per angle; IC hanya rata-rata. |
| Turnover / autokorelasi peringkat faktor | Tidak | |
| Netral sektor / demean per kelompok | Tidak | Butuh `group_*` (S20 F1). |
| Deret return faktor (long-short per tanggal) | Dihitung di dalam, tidak dikeluarkan | Spread per tanggal sudah ada di mesin. |
| Regresi lintas saham (Fama-MacBeth, banyak faktor sekaligus) | Tidak | |
| Penghitungan semua percobaan dalam percakapan | Tidak | Koreksi hanya per rencana. |
| Akses tanpa rencana riset (eksplorasi di sesi analisis) | Tidak | Metode hanya bisa dipakai lewat rencana riset yang disetujui user. |

## 5. Prinsip: tidak ada yang di-hardcode

Metode adalah **kode statistik yang umum**; semua yang spesifik data diturunkan saat run dari katalog dan kontrak data.

1. **Peran, bukan kolom.** Setiap metode bekerja atas peran: `signal`, `outcome`, `event`, `benchmark`, `group`,
   `weight`. Tidak ada nama tabel, kolom, ticker, indeks atau jenis aset di kode metode. Saham, FX, komoditas
   atau obligasi diperlakukan sama: entitas + tanggal + nilai.
2. **Return normal dideklarasikan, bukan dipasang.** Benchmark adalah peran yang diisi dari kontrak data: deret
   indeks (kalau tabelnya ada nanti), `cs_mean` / `group_mean` dari universe yang diminta (S20 F1), atau deret lain
   yang dipilih AI. Tidak ada default "IHSG" atau "rata-rata sama bobot" yang diam-diam dipakai. Model return normal
   (`MARKET_ADJUSTED`, `MARKET_MODEL`, `CONSTANT_MEAN`, `RAW`) adalah parameter yang tercatat di hasil.
3. **Kelompok dari katalog.** Netral sektor dan rincian per kelompok hanya dengan kolom `is_groupable`. Kolom baru
   (sektor GICS, negara, kelas aset) otomatis bisa dipakai begitu terdaftar di katalog.
4. **Bobot sebagai peran.** Sama bobot secara default; bobot kapitalisasi pasar hanya kalau ada peran `weight` yang
   dideklarasikan (dari data fundamental nanti). Tidak ada kolom kapitalisasi pasar yang dipasang di kode.
5. **Waktu dari data.** Horizon, frekuensi dan jendela dalam jumlah observasi entitas itu (kalender perdagangan dari
   datanya sendiri, bukan kalender bursa tertentu). Resample memakai aturan katalog yang sudah ada.
6. **Ambang sebagai kebijakan.** Minimal event, minimal entitas per tanggal, ambang signifikansi dan anggaran
   percobaan disimpan sebagai konfigurasi kebijakan dengan default yang dicatat di setiap hasil, bukan angka yang
   tersebar di kode. Kebijakan riset sudah punya pola ini (`PY_SANDBOX_RESEARCH_*`).
7. **Point-in-time.** Sinyal dari data fundamental nanti dibaca as-of (semantik `AS_OF` / `POINT_IN_TIME` yang sudah
   ada), supaya faktor tidak memakai data yang belum dipublikasikan pada tanggal itu.
8. **Deskripsi metode dibangkitkan dari kode** (`AI_research_library`, sudah begitu). Metode baru = kode mesin + test +
   migrasi yang dibangkitkan, tanpa perubahan prompt.

## 6. Keputusan integrasi: satu mesin, dua pintu

**Satu implementasi statistik** (`runtime/research_engines.py`), dipakai lewat dua pintu supaya AI bisa memakainya
kapan pun berguna, dengan aturan bukti yang sesuai pintunya:

| | Pintu A: sesi analisis (eksplorasi) | Pintu B: riset (konfirmasi) |
|---|---|---|
| Kapan AI memakainya | Kapan saja di `run_python`, tanpa rencana riset | Lewat angle di rencana riset yang disetujui user |
| Bentuk | Helper sesi: `saniti.event_study(...)`, `saniti.factor_report(...)` | Metode di perpustakaan riset: `event_study`, perluasan `quantile_ranking` (atau metode `factor_return`), `cross_sectional_regression` |
| Hasil | Statistik lengkap, berlabel **EXPLORATORY / IN_SAMPLE**: tidak boleh disebut "terbukti" | Temuan per angle (SUPPORTED, …) dengan holdout, koreksi uji berganda, penghitungan ulang backend |
| Penjaga | Gerbang jawaban yang sudah ada; label eksplorasi ikut di provenance | Penjaga riset yang sudah ada + buku percobaan (bagian 7.3) |
| Penemuan oleh AI | Daftar helper dan docstring di hasil `open_analysis_session`, dibangkitkan dari registri yang sama | `get_research_library` (sudah ada) |

Alasannya: tujuan user adalah akses kapan pun berguna, sedangkan riset multi-angle mewajibkan rencana yang
disetujui. Pintu A memberi akses langsung untuk menggambarkan pola; pintu B tetap satu-satunya jalan untuk klaim
"terbukti". Satu mesin berarti angka eksplorasi dan konfirmasi dihitung dengan rumus yang sama.

## 7. Rancangan per kemampuan

### 7.1 Event study dengan return abnormal (menghidupkan item 2)

- **Masukan (peran):** `event` (kondisi per entitas dan tanggal, rumus dengan fungsi per entitas dan lintas entitas),
  `price` atau `return`, `benchmark` (opsional; wajib untuk model selain RAW / CONSTANT_MEAN).
- **Parameter:** `normal_model` (`MARKET_ADJUSTED`, `MARKET_MODEL`, `CONSTANT_MEAN`, `RAW`), `estimation_window`
  dan `gap` (observasi sebelum event), `event_window` (mis. [−k, +h]), `overlap_policy` (NON_OVERLAPPING default,
  dari `spec.py`), `min_events` (kebijakan, default 30 dari `spec.py`).
- **Keluaran:** AAR per hari relatif event, CAAR, sebaran CAR, jumlah event dan entitas, event terpotong (disensor),
  tanggal yang mengelompok (banyak event di tanggal yang sama).
- **Uji:** t lintas event untuk CAR, dengan galat dari sebaran per tanggal event (pola `_welch` / effective count yang
  sudah ada) supaya event yang mengelompok di satu tanggal tidak dihitung sebagai bukti independen. Uji BMP/Patell
  menyusul bila dibutuhkan.
- **Dari `spec.py` dipindahkan:** definisi event, NON_OVERLAPPING, minimal event, sensor ujung data. Jalur lama tetap
  sebagai cadangan sampai keputusan pembersihan (S22).

### 7.2 Analisis faktor dan return faktor

Diperluas dari `quantile_ranking`, tidak dibangun ulang:

- IC per tanggal (rank dan Pearson), **IC IR**, t-stat IC dengan **Newey-West**, persentase tanggal IC positif;
- **beberapa horizon** dalam satu angle (peluruhan), dihitung sebagai kandidat sehingga masuk koreksi uji berganda;
- **turnover** dan autokorelasi peringkat;
- opsi **netral kelompok** (demean atau peringkat per kelompok, `group` dari katalog);
- **deret return faktor** (long kuantil atas − short kuantil bawah per tanggal, sama bobot atau dengan peran `weight`)
  dikeluarkan sebagai tabel hasil, sehingga bisa dipakai angle atau analisis lain;
- ringkasan deret itu: rata-rata, t-stat, Sharpe dan Sharpe terdeflasi (Bailey & López de Prado) dengan jumlah
  percobaan dari buku percobaan (7.3).

Metode baru tahap kedua: **`cross_sectional_regression`** (Fama-MacBeth): beberapa sinyal sekaligus, koefisien per
tanggal, rata-rata dan galat Newey-West. Ini yang dibutuhkan saat data fundamental masuk (banyak faktor sekaligus).

### 7.3 Disiplin uji hipotesis (menambahkan item 3)

- **Buku percobaan per percakapan** (state percakapan di market-ai-orc, di sebelah catatan data): setiap angle yang
  pernah diuji (metode, peran, parameter, data) dicatat. Rencana berikutnya di percakapan yang sama menghitung
  semua percobaan sebelumnya dalam `m` untuk koreksi uji berganda. Pengulangan angle yang sama di data yang sama
  dihitung sebagai percobaan baru. Ini setara `followup_of` dan anggaran eksperimen riset v1, dibawa ke multi-angle.
- **Anggaran percobaan** per percakapan dari konfigurasi kebijakan (pola `PY_SANDBOX_RESEARCH_MAX_*`).
- **Pelaporan ambang:** hasil menyebut jumlah percobaan dan ambang terkoreksinya, supaya user melihat kenapa temuan
  dengan t = 2,4 bisa tidak lolos setelah 30 percobaan.
- Sumber riset v1 yang dipakai ulang: struktur anggaran dan validasi `followup_of` (`app/research_governance.py`).

## 8. Urutan dan ketergantungan

1. S21 (helper `range` menimpa bawaan Python): perbaikan kecil, lebih dulu.
2. S20 F1: fungsi lintas entitas (`cs_*`, `group_*`). Syarat untuk benchmark dan netral kelompok.
3. 7.1 event study (pintu B dan pintu A).
4. 7.2 perluasan faktor (pintu B dan pintu A).
5. 7.3 buku percobaan.
6. `cross_sectional_regression`, saat data fundamental mulai dimuat.
7. Keputusan pembersihan jalur lama (S22): `spec.py` EVENT_STUDY, riset v1, baris `Tool_Catalog` worker lama.

Setiap langkah: migrasi `AI_research_library` yang dibangkitkan, `Tool_Catalog` bila skema alat berubah, README
sandbox dan orc, `ERRORS_AND_SOLUTIONS.md`, test, deploy satu service per kali sampai `SUCCESS`, uji live.

## 9. Risiko dan mitigasi

| Risiko | Penjelasan non-dev | Mitigasi |
|---|---|---|
| Benchmark yang salah | Return abnormal hanya sebaik "return normal"-nya | Benchmark wajib dideklarasikan dan tercatat di hasil; model RAW diberi label jelas; jumlah entitas per tanggal untuk benchmark lintas entitas dicatat |
| Event mengelompok | Banyak saham kena event di hari crash yang sama, sehingga terlihat seperti banyak bukti padahal satu kejadian | Galat dari per tanggal event (effective count), jumlah tanggal unik dilaporkan |
| Data-mining | AI mencoba puluhan faktor lalu melaporkan yang kebetulan bagus | Buku percobaan per percakapan; koreksi memakai semua percobaan; Sharpe terdeflasi; holdout |
| Pintu A disalahartikan | Hasil eksplorasi dibaca sebagai bukti | Label EXPLORATORY / IN_SAMPLE dibawa ke provenance; klaim "terbukti" hanya dari pintu B |
| Survivorship dan universe | Universe saat ini dipakai untuk masa lalu | Peringatan HISTORICAL_REFERENCE_USES_CURRENT_STATE yang sudah ada; POINT_IN_TIME bila tersedia |
| Biaya hitung | Kuantil, IC dan Newey-West atas jutaan baris | Mesin per tanggal; diukur pada data broker 3 juta baris sebelum deploy |
| Hardcode tersisip | Default diam-diam (benchmark, bobot, kalender) | Test yang menjalankan metode atas data sintetis dua jenis aset (saham dan non-saham) dengan nama kolom berbeda; review kode mencari literal tabel/kolom/ticker |
| Mesin rumus bersama | Mengubah `expression.py` bisa mengganggu jalur lama | Fungsi baru hanya di konteks riset/sesi; seluruh test lama harus lulus |

## 10. Verifikasi

- **Test terhadap perhitungan independen:** data sintetis dengan efek yang ditanam (CAR yang diketahui, IC yang
  diketahui); hasil dibandingkan dengan perhitungan pandas/statsmodels yang ditulis terpisah.
- **Test tanpa hardcode:** metode yang sama dijalankan atas entitas non-saham (deret sintetis bergaya FX) dengan nama
  kolom lain dan memberi hasil yang benar.
- **Uji live** (saklar pikiran menyala):
  - event study: "Bagaimana return abnormal saham bank 10 hari setelah net jual asing terbesar?";
  - faktor: "Apakah net beli broker asing memprediksi return 5 hari saham bank?" (IC, IR, spread, turnover);
  - eksplorasi di mode ANALYSIS memakai pintu A tanpa rencana riset.
- **Kasus yang tidak cocok:** data makro satu deret, karena tidak ada lintas entitas untuk faktor. Event study satu
  entitas tetap jalan (time-series event) dengan model CONSTANT_MEAN atau benchmark yang dideklarasikan.

## 11. Keputusan yang diminta dari user

1. Setuju "satu mesin, dua pintu" (eksplorasi di sesi analisis tanpa rencana, konfirmasi lewat riset)?
2. Setuju urutan di bagian 8 (S21 → S20 F1 → event study → faktor → buku percobaan → regresi)?
3. Buku percobaan dihitung **per percakapan**, atau lebih luas (per user / global)?
4. Setelah event study baru aktif: jalur lama (`spec.py` EVENT_STUDY, riset v1, baris `Tool_Catalog` worker lama)
   dibersihkan atau tetap sebagai cadangan?

## Rujukan

- MacKinlay (1997), *Event Studies in Economics and Finance*; Kothari & Warner, *Econometrics of Event Studies*.
- Alphalens (github.com/quantopian/alphalens; alphalens.ml4trading.io).
- Fama-MacBeth: tidy-finance.org/chapters/fama-macbeth-regressions.html; Fama-French: tidy-finance.org (replicating
  Fama-French factors).
- Harvey, Liu & Zhu (2016), *…and the Cross-Section of Expected Returns* (NBER w20592).
- Bailey & López de Prado, *Statistical Overfitting and Backtest Performance*; purged cross-validation.
- Microsoft Qlib dan RD-Agent (github.com/microsoft/qlib, github.com/microsoft/rd-agent).
- Anthropic, *Writing effective tools for AI agents*.
