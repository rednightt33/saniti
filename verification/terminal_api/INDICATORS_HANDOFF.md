# Handoff: indikator Terminal EDGE (cara kerja, edit, tambah, audit)

Disusun 2026-11-05 dari kode di `main` `e23899f6`. Rujukan `T/` = `apps/edge-bff/terminal/`. Setiap klaim punya
rujukan file:baris; kalau kode berubah, cek ulang rujukannya.

---

## 1. Gambaran besar

Terminal punya dua keluarga indikator:

| Keluarga | Jumlah | Daftar (registry) | Rumus | Dibuat dari |
|---|---|---|---|---|
| Teknikal | 53 (I01–I53) | `T/src/data/indRegistry.json` | `T/src/calc/indicators.ts` (`F[key]`) | **diedit tangan** (tidak ada generator) |
| Flow (broker) | 39 (FL01–FL39) + 2 buatan tangan (`netflow`, `netbuyline`) | `T/src/data/flowRegistry.json` | `T/src/calc/flow.ts` (`FLOW[id]`) | **digenerate** dari `verification/terminal_api/flow_indicators/FLOW_INDICATORS_SPEC.xlsx` |

Alurnya:

```
bucket (file harga/broker per ticker)
  └─ T/src/data/live.ts          minta URL file lewat edge-bff, jalankan 1 Web Worker
       └─ T/src/data/worker.ts   unduh, cek sha256, parse; TIDAK menghitung indikator
            └─ T/src/main.ts     susun konteks (OHLC, volume, registry, baris broker)
                 ├─ T/src/app/indicators.ts     F[key](bars, params)  → seri per output
                 ├─ T/src/app/flowIndicators.ts computeFlow(id, ...)  → seri per output
                 └─ lightweight-charts          garis / histogram / titik / panel
```

- Semua hitungan indikator berjalan di **main thread**, bukan di worker. Worker hanya mengunduh dan mem-parse
  (`T/src/data/worker.ts:1-5, 7, 148-185`).
- Hitungan teknikal: `F[r.key](BARS, p)` (`T/src/app/indicators.ts:75`).
- Hitungan Flow: `computeFlow(r.id, context(), q)` (`T/src/app/flowIndicators.ts:172-183`).
- Di chart intraday, indikator yang hanya untuk data harian (misalnya I34 ADR) dihitung di sesi harian lalu
  dipetakan ke candle. Flow juga selalu dihitung per hari (`T/src/app/indicators.ts:32-39, 75`;
  `T/src/app/flowIndicators.ts:64-68, 106-112`).

**Yang paling penting diingat:** rumus dan registry teknikal **dipakai bersama** oleh tiga produk:

| Pemakai | Membaca | Cara deploy |
|---|---|---|
| Terminal | `T/src/calc/*`, kedua registry | edge-bff, otomatis dari GitHub |
| Backtest (halaman + `backtest-worker`) | `indicators.ts`, `indRegistry.json` | halaman: edge-bff; **worker: unggah CLI saja** |
| Screener (halaman + `screener-worker`) | `indicators.ts`, `indRegistry.json`, seluruh `T/src/calc/*.ts` | otomatis dari GitHub |

Mengubah satu byte di `indicators.ts` atau `indRegistry.json` (termasuk teks tooltip bahasa Indonesia) mengubah versi
registry Backtest dan Screener. Kedua worker menolak start sampai registry turunannya dibangun ulang (bagian 6).

---

## 2. Anatomi entri registry teknikal (`indRegistry.json`)

Array 53 objek. Setiap objek punya 17 field yang sama.

### Field tingkat indikator

| Field | Contoh | Mengatur apa | Dibaca di |
|---|---|---|---|
| `id` | `I13` | ID di menu, favorit, kartu, Backtest, Screener | `indMenu.ts:28,169`; `indCard.ts:36,151`; Backtest `core/registry.ts:24,36-41` |
| `cat` | `Momentum` | grup di menu, kategori Backtest | `indMenu.ts:27-28`; `build-registry.mjs:46` |
| `name` | `Relative Strength Index` | judul; **harus unik** di teknikal + Flow (menu menambah indikator lewat nama) | `indicators.ts:72,215`; `indMenu.ts:132` |
| `key` | `rsi` | nama fungsi `F[key]` dan `DEFAULTS[key]`; **disimpan di pengaturan user** | `indicators.ts:72,75,230` |
| `short` | `RSI` | judul legend, mis. "RSI (14, close)" | `indicators.ts:91` |
| `req` | `C`, `HLC`, `HLCV` | data yang wajib ada; tanpa data itu indikator tidak tampil | `data/inputs.ts:42-48`; `indicators.ts:222-223,747-751` |
| `zone` | `overlay` / `panel` / `volume` | menumpang di candle, panel sendiri, atau skala volume | `indicators.ts:73,251-253`; Backtest `reg.ts:42` |
| `unit` | `price`, `pct`, `index` | format angka di legend, sumbu, kartu | `indicators.ts:43-48`; `specFormat.ts:108-117` |
| `colorRule` | `solid:auto` | **tidak dibaca kode mana pun** | — |
| `outs` | lihat bawah | output yang digambar | — |
| `params` | lihat bawah | input yang bisa diatur user | — |
| `guides` | `[30, 70]` | garis bantu putus-putus | `indicators.ts:112,270-274,322-327` |
| `fill` | `"upper ↔ lower"` | arsiran di antara dua output | `indicators.ts:70,275,328-332` |
| `tip` | teks Indonesia | tooltip menu | `indMenu.ts:29,138` |
| `info` | teks Indonesia | paragraf di dialog setting dan kartu | `indicators.ts:495`; `indCard.ts:216` |
| `display` | teks Indonesia | "Ditampilkan sebagai" di kartu dan Backtest | `picker.ts:16`; Backtest `reg.ts:20` |
| `position` | teks Inggris | **tidak dibaca kode mana pun** | — |

### Field per output (`outs[]`)

| Field | Mengatur apa | Rujukan |
|---|---|---|
| `k` | nama output; **harus sama dengan output `F[key]`**; dipakai di pengaturan user dan kondisi Backtest | `indicators.ts:110,230`; backtest-worker `tests/registry.test.ts:17-21` |
| `label` | label di legend dan tab Style | `indicators.ts:424,607` |
| `r` | cara menggambar: `line`, `histogram`, `segmented_line`, `dots`, `state` (tidak digambar, hanya pewarnaan) | `indicators.ts:261-268,98,290` |
| `role` | warna bawaan: `signal_line`/`center_line` dapat warna kedua, `boundary_line` warna dasar | `indicators.ts:103-108` |
| `vis`, `w` | tampil awal dan tebal garis | `indicators.ts:99` |
| `rule` | `histogram:*` naik/turun, `rising`, `optional_state` 4 warna | `indicators.ts:101,279,303-305` |
| `cond` | hanya `bands_mode` yang dibaca (sembunyikan output saat `bands_mode` = None); sisanya catatan | `indicators.ts:99,290-291` |

### Field per parameter (`params[]`)

| Field | Mengatur apa | Rujukan |
|---|---|---|
| `k` | nama parameter yang dikirim ke `F`; **harus ada di `DEFAULTS[key]`** | `build-registry.mjs:36-44` |
| `type` | `integer`, `number`, `enum`, `boolean`, `fixed` (fixed = tampil "Uses X (fixed)", tidak bisa diubah) | `indicators.ts:64-68,91` |
| `def` | nilai bawaan; **harus sama dengan `DEFAULTS[key][k]` di `indicators.ts`** | `indicators.ts:65-68,231`; `build-registry.mjs:38-39` |
| `ev` | status bukti nilai bawaan (`VERIFIED_DEFAULT`, `PROPOSED_DEFAULT`, ...); hanya ditampilkan di Backtest | Backtest `reg.ts:21,27` |
| `min`, `max`, `step` | batas input; tanpa batas: integer 1–5000 | `indicators.ts:65-66`; Backtest menolak nilai di luar batas (`core/registry.ts:61-62`) |
| `opts` | pilihan enum; `timeframe` dengan satu opsi `1D` = indikator khusus harian | `indicators.ts:38,68` |
| `hint` | tooltip label di dialog | `indicators.ts:506` |

Aturan hitung bersama (fungsi `def()`, `T/src/calc/indicators.ts:244-273`):
- parameter yang tidak dikirim memakai `DEFAULTS[key]`;
- parameter yang namanya cocok `LENGTH_KEYS` (`length`, `smoothing`, `smooth_k`, `smooth_d`, `periods`) dibulatkan ke
  bawah; panjang < 1 menghasilkan semua null (`indicators.ts:239`);
- bar yang input-nya tidak valid memutus seri; hitungan mulai lagi setelahnya (`indicators.ts:17-20,252-269`).

---

## 3. Anatomi registry Flow (`flowRegistry.json`)

- **Jangan diedit tangan.** File ini mencatat sha256 spreadsheet sumbernya. Digenerate oleh
  `python3 scripts/build_flow_registry.py` (butuh `openpyxl`; `--check` untuk memeriksa).
- Field per indikator: `id`, `name`, `family` (dari awalan nama, `build_flow_registry.py:27-33`), `place` (`pane`,
  `price`, `marker`), `unit`, `needs_frequency` (butuh jumlah transaksi), `outputs`, `tip`, `params`.
- Field parameter: `key`, `label` (Inggris, dipetakan dari label Indonesia di `LABELS`), `status` (DECIDED/PROPOSED),
  `kind` (`select`, `multi`, `brokers`, `int`, `num`, `levels`, `bool`, `date`, `button`, `fixed`), `default`,
  `options`, `min`, `max`.
- Nilai bawaan Flow juga menjadi `DEFAULTS` di `calc/flow.ts` (`flow.ts:569-575`). Panel Bandar membaca nilai bawaan FL24
  (`app/broker.ts:8-12`).
- Teks tooltip: FL01–FL23 dari `PLAIN` di `build_flow_registry.py:163-187`; FL24–FL39 dari spreadsheet.
- `netflow` dan `netbuyline` ditulis tangan di `T/src/app/indicators.ts:153-211`, tidak ada di registry.
- Rumus dan definisi tertulis Flow: `verification/terminal_api/flow_indicators/FORMULAS.md` bagian 3. Ada pemeriksa
  independen: `verification/terminal_api/flow_indicators/oracle/oracle.py`.

---

## 4. Mengedit indikator teknikal yang sudah ada

### 4a. Mengubah rumus atau perilaku

1. Ubah `F[key]` di `T/src/calc/indicators.ts`. Jaga kesetaraan dengan sumbernya (bagian 7.1).
2. Kalau nilai bawaan parameter berubah, ubah **tiga tempat sekaligus**:
   - `DEFAULTS[key]` di `T/src/calc/indicators.ts:215-237`;
   - `params[].def` di `indRegistry.json`;
   - salinan tangan `REGISTRY` di `T/tests/calc/edge.test.ts:8-62`.
3. Kartu penjelasan menghitung ulang `F` sendiri:
   - I01–I26: `T/src/calc/explainTechA.ts`;
   - I27–I53: `T/src/calc/explainTechB.ts`.

   Keduanya punya salinan logika `def()` (`LENGTH_KEYS`, peta kebutuhan input). Kalau `def()` diubah, salinannya juga
   diubah. Tes mewajibkan nilai di kartu sama dengan nilai di chart (`T/tests/calc/explain.test.ts:65-84`).
4. Kalau teks rumusnya berubah: ubah baris indikator itu di `scripts/terminal_indicator_spec.py` (`I`, baris 31-185),
   lalu jalankan:
   - `python3 scripts/terminal_indicator_spec.py`: menulis ulang `INDICATOR_SPEC.md` **dan migrasi** (lihat jebakan
     7.3);
   - `python3 scripts/build_indicator_notes.py`: menulis ulang `T/src/data/indNotes.json`.
5. Bangun ulang registry turunan, **di commit yang sama** (ERRORS M329):
   - `cd apps/backtest-worker && npm run registry`
   - `cd apps/edge-bff/screener && npm run registry` (butuh python3)
6. Kalau nilai pembanding berubah, perbarui fixture dan baris di `T/tests/calc/PARITY.md` (langkah ulang di
   `PARITY.md:21-24`).

### 4b. Mengubah tampilan saja (tip, info, label, guides, fill, warna, tebal garis)

- Cukup ubah `indRegistry.json`; rumus tidak berubah.
- **Tetap wajib** menjalankan `npm run registry` di `apps/backtest-worker` dan `apps/edge-bff/screener`. Versi registry
  dihitung dari byte file, jadi tanpa ini kedua worker gagal start.
- Warna bawaan tidak diambil dari registry. Warnanya diturunkan di kode (`PALETTE`, `UP`, `DOWN`, `regStyle`,
  `T/src/app/indicators.ts:25-27,95-113`).

### 4c. Mengubah batas parameter (`min`, `max`, `step`, `opts`)

- Ubah `indRegistry.json`, lalu bangun ulang kedua registry.
- Backtest langsung menerima atau menolak nilai sesuai batas baru (`core/registry.ts:56-67`).
- Screen tersimpan yang nilainya di luar batas baru akan tampil "needs review" (`SCREENER_ONBOARDING.md:787-790`).

---

## 5. Menambah indikator teknikal baru (mis. I54)

Contoh lengkap yang sudah ditulis di repo: `SCREENER_ONBOARDING.md:1338-1414` (bagian 2.11), dengan tabel ceknya di
`:1180-1194`.

1. **Rumus.** `F.<key> = def('<key>', [outputs], kebutuhan, hitung)` dan `DEFAULTS.<key>` di `T/src/calc/indicators.ts`.
   Beri komentar sumbernya (`FEATURE_04`, `TA_LIB`, atau `HTML`). Beri nama parameter panjang yang cocok `LENGTH_KEYS`.
2. **Registry.** Entri baru dengan 17 field di `indRegistry.json`. Setiap kunci `DEFAULTS` harus jadi parameter registry;
   kalau tidak, generator Backtest berhenti (`build-registry.mjs:43-44`). Terminal dan halaman Backtest otomatis
   menampilkannya (menu, dialog, chart, legend).
3. **Kartu penjelasan.** Tambahkan di `T/src/calc/explainTechB.ts` dan daftarkan di `TECH_EXPLAIN_B` (`:236`). Tes
   mewajibkan setiap ID punya penjelasan (`explain.test.ts:87-91`).
4. **Spesifikasi rumus.** Baris baru di `scripts/terminal_indicator_spec.py`, lalu jalankan generator spec dan notes.
   Tes kartu mewajibkan rumus untuk setiap ID (`T/tests/data/ind_card.test.ts:29-32`).
   **Masalah terbuka:** generator itu menulis ulang migrasi yang sudah diterapkan (jebakan 7.3). Sebelum indikator baru
   pertama, generatornya harus dipecah dulu: migrasi lama dibekukan, baris baru masuk migrasi baru (ID berikutnya
   sekitar `CALC_247`; `SCREENER_ONBOARDING.md:1361-1367`).
5. **Tes yang diubah tangan:**
   - `T/tests/calc/edge.test.ts`: salinan `REGISTRY` dan hitungan 53 (`:88-90`);
   - `apps/backtest-worker/tests/registry.test.ts`: hitungan 53 (`:15`) dan uji `indicator('I54')` yang sekarang
     diharapkan `UNKNOWN_INDICATOR` (`:51`);
   - fixture pembanding di `T/tests/calc` (`tools/gen_talib.py`, `gen_html.mjs`, `fetch_live.py`) dan baris
     `PARITY.md`.
6. **Backtest.** `cd apps/backtest-worker && npm run registry`, commit `backtest-registry.json`.
7. **Screener.** Tambahkan ke `apps/edge-bff/screener/src/core/screener-overlay.json` (wajib satu entri per ID,
   `tests/core/registry.test.ts:69-72`), lalu `cd apps/edge-bff/screener && npm run registry`.
8. **Catatan.** `BACKTEST_END_TO_END.md` bagian 14, `CONTRACT.md` bila aturan berubah, `RAILWAY_CHANGELOG.md`,
   `DATABASE_CHANGELOG.md`, `EXEC.md`.
9. **Deploy** (bagian 6).

---

## 6. Deploy sesudah perubahan indikator

| Layanan | Cara | Yang memicu | Catatan |
|---|---|---|---|
| edge-bff (halaman Terminal, Backtest, Screener) | otomatis dari GitHub `main` | `/apps/edge-bff/**` | Dockerfile membangun ketiga halaman (`apps/edge-bff/Dockerfile:3-46`) |
| screener-worker | otomatis dari GitHub | termasuk `/apps/edge-bff/terminal/src/calc/**` dan `indRegistry.json` (`.railway/railway.ts:211-217`) | registry turunan yang basi membuat `/ready` gagal (M329) |
| backtest-worker | **unggah CLI saja** (`railway up`), tidak ikut GitHub (`.railway/railway.ts:202-210`) | — | harus diunggah ulang dari commit hasil merge (`SCREENER_ONBOARDING.md:1395-1405`); kalau lupa, halaman Backtest menawarkan hal yang ditolak worker lama |

- Jendela rilis: di luar 00:00–01:45 dan 12:00–13:20 UTC (`SCREENER_ONBOARDING.md:1395`).
- Klaim deploy berhasil hanya setelah setiap layanan yang terpicu mencapai `SUCCESS` (ERRORS M329).

---

## 7. Hal yang harus diperhatikan

### 7.1 Kesetaraan rumus (parity)

- Aturan uji: bar valid pertama sama, null sama, selisih relatif ≤ 1e-9. Feature 04 dan TA-Lib dibandingkan ketat;
  mesin referensi HTML boleh selisih sisa 1e-12 (`T/tests/calc/PARITY.md:3-4`; `parity.test.ts:1-7,80-82`).
- **Wajib sama persis dengan Feature 04** (kolom yang dipakai AI dan Screener): I01 SMA, I02 EMA, I06 MACD, I07 ADX,
  I13 RSI, I27 Bollinger, I30 ATR (`parity.test.ts:17-30`). Mengubah salah satunya berarti Terminal tidak lagi sama
  dengan Feature 04 di database.
- 24 indikator mengikuti TA-Lib 0.6.8; 22 mengikuti mesin referensi HTML. Sumber per indikator ada di kolom `source`
  `scripts/terminal_indicator_spec.py`.
- Flow: pembanding `oracle_compare.ts`, toleransi |a−b| ≤ 1e-9·max(1,|a|,|b|).

### 7.2 Nama yang tidak boleh diganti diam-diam

- **Pengaturan user di browser** (`localStorage`):
  - `ml.ind.v1` menyimpan daftar indikator user `[{def, params, style, on, base}]` (`indicators.ts:218,230`).
    - `def` = `key` teknikal (mis. `rsi`) atau ID Flow (mis. `FL24`).
    - `def` yang tidak dikenal **dibuang** saat dimuat; hanya `ma` dan `ema` yang punya migrasi
      (`indicators.ts:739-748`).
    - Parameter yang diganti namanya kembali ke nilai bawaan (`:231`). `style.out` memakai nama output `k`.
  - `ml.ind.favs`, `ml.ind.kind`, `ml.ind.box`, `ml.ind.navw`: favorit dan tata letak menu (`indMenu.ts`).
  - Pengaturan indikator tidak disimpan di server (EXEC-TERMINAL-PREFS belum dijalankan).
- **Backtest:** permintaan dan hasil tersimpan memakai ID, nama parameter dan nama output. ID tidak dikenal menjadi
  `UNKNOWN_INDICATOR` (`core/registry.ts:36-71`).
- **Screener:** item tersimpan membawa versi registry dan divalidasi ulang saat dimuat. Aturannya: "rilis hanya menambah
  ID" (`SCREENER_ONBOARDING.md:1414`).
- Jadi: **jangan mengganti `id`, `key`, nama output `k`, atau nama parameter `k`.** Ubah label, bukan kuncinya.

### 7.3 File generate vs file tangan

| File | Status | Cara memperbarui |
|---|---|---|
| `T/src/data/indRegistry.json` | tangan | edit langsung |
| `DEFAULTS` di `T/src/calc/indicators.ts` | salinan tangan dari `def` registry | edit bersama registry |
| `REGISTRY` di `T/tests/calc/edge.test.ts` | salinan tangan kedua | edit bersama registry |
| `verification/terminal_api/INDICATOR_SPEC.md` | generate ("jangan edit tangan") | `python3 scripts/terminal_indicator_spec.py` |
| `database/migrations/20261025_102_terminal_indicator_formulas.sql` | generate oleh skrip yang sama, **sudah diterapkan** | lihat peringatan di bawah |
| `T/src/data/indNotes.json` | generate | `python3 scripts/build_indicator_notes.py` |
| `T/src/data/flowRegistry.json` | generate | `python3 scripts/build_flow_registry.py` |
| `FLOW_INDICATORS_SPEC.xlsx` | sumber kontrak Flow | edit spreadsheet |
| `apps/edge-bff/backtest/src/core/backtest-registry.json` | generate | `npm run registry` di `apps/backtest-worker` |
| `apps/edge-bff/screener/src/core/screener-registry.json` | generate | `npm run registry` di `apps/edge-bff/screener` |
| `screener-overlay.json` | tangan | edit langsung |

**Peringatan migrasi:** `terminal_indicator_spec.py` menulis ulang migrasi `20261025_102` dari semua baris
non-Feature-04 (`scripts/terminal_indicator_spec.py:281-327`). Migrasi itu sudah diterapkan (CALC_201..246,
`DATABASE_CHANGELOG.md`), dan AGENTS.md melarang mengedit migrasi yang sudah diterapkan. Menjalankan generator setelah
mengubah teks rumus indikator non-Feature-04 akan mengubah file itu. Kembalikan perubahan pada file migrasi lama, lalu
buat migrasi baru untuk baris `AI_formula_reference` yang berubah. Lebih baik lagi, pecah generatornya dulu (bagian 5
langkah 4).

### 7.4 Jebakan versi dan hash

- **Backtest `registry_version`:** sha256 dari `indRegistry.json` dan `indicators.ts` (16 karakter pertama,
  `apps/backtest-worker/scripts/build-registry.mjs:25`). Worker membandingkannya saat start; kalau beda, ia mencatat
  `registry_mismatch` dan berhenti (`backtest-worker/src/server.ts:402`).
- **Screener:** `screener-registry.json` menyimpan sha256 `backtest-registry.json`, `indRegistry.json`, `indicators.ts`,
  `screener-overlay.json` dan generatornya. screener-worker menolak start kalau ada yang beda
  (`screener-worker/src/version.ts:55-70`).
- **`screener_engine`:** hash dari **semua** `T/src/calc/*.ts`. Mengubah `flow.ts` atau `explain*.ts` ikut mengubahnya,
  walau tidak perlu membangun ulang registry (`version.ts:28-34`).
- **Pemeriksa ubahan:** `npm run tripwire` di `apps/edge-bff/screener` melindungi `indicators.ts`, `indRegistry.json`,
  `backtest/src/core` dan `features/feature04` terhadap `origin/main` (`scripts/screener/check_backtest_untouched.mjs:43-50`).
  Dijalankan manual; tidak ada CI yang menjalankannya.

### 7.5 Letak teks bahasa Indonesia

| Teks | Lokasi |
|---|---|
| `tip`, `info`, `display` indikator teknikal | `indRegistry.json` |
| `tip` Flow FL01–FL23 | `PLAIN` di `scripts/build_flow_registry.py:163-187` (lalu generate) |
| `tip` Flow FL24–FL39 | `FLOW_INDICATORS_SPEC.xlsx` (lalu generate) |
| catatan indeks dan "butuh jumlah transaksi" | `T/src/app/flowIndicators.ts:26-32,143` |
| tab dan kalimat kartu indikator | `T/src/app/indCard.ts:24,55-78,159-209` |
| langkah penjelasan ("Baca hasilnya" dst.) | `T/src/calc/explain*.ts` |
| tooltip volume | `T/src/app/picker.ts:52`; `indMenu.ts:31-32` |

Label parameter, hint dan `position` berbahasa Inggris.

---

## 8. Temuan audit yang sudah terlihat dari kode

Tidak satu pun diperbaiki di sini; semuanya kandidat untuk audit indikator.

1. **I12 Parabolic SAR:** registry `req` = `HLC`, padahal rumus hanya butuh `HL`
   (`T/src/calc/indicators.ts:357`; spec juga HL). Akibatnya ticker tanpa close tidak bisa memakai PSAR padahal bisa.
2. **I37 RVOL:** parameter `include_current_bar` bawaan `false` di registry, tetapi rumus selalu memasukkan bar saat
   ini (`indicators.ts:483`; spec: "RVOL includes the current bar"). Dialog menawarkan pilihan yang tidak berpengaruh.
3. **Parameter yang tampil tapi tidak dibaca rumus:** I26 `source` (fixed); I34 `timeframe` (hanya penanda khusus
   harian); I37 `reference_method` dan `include_current_bar`; I40, I41, I44 `calculation_parameters` (fixed). Backtest
   menandainya `not_accepted`.
4. **Field registry yang tidak dibaca siapa pun:** `colorRule` (tingkat indikator) dan `position`.
5. **Tiga salinan nilai bawaan** (registry, `DEFAULTS`, `edge.test.ts`) tanpa pemeriksa otomatis registry ↔
   `DEFAULTS` di Terminal. Hanya generator Backtest yang mencatat perbedaannya (`workbook_default`); saat ini tidak ada
   yang berbeda.
6. **Tidak ada tes** yang membandingkan `terminal_indicator_spec.py` (input, nilai bawaan) dengan `indRegistry.json`.
   Selisih seperti nomor 1 tidak tertangkap.
7. **Komentar basi:** `explainTechA.ts:2`, `explainTechB.ts:2`, `explainFlowA.ts:2` menyebut `explainTechIndex.ts` /
   `explainFlowIndex.ts`; file sebenarnya `calc/explainIndex.ts`.
8. **Generator spec menulis migrasi yang sudah diterapkan** (7.3).
9. Feature 04: rantai inkremental worker dan hitungan referensi bisa berbeda di masa harga datar tanpa transaksi
   (ERRORS M349, AKKU RSI). Ini di sisi database Feature 04, tetapi menyangkut indikator yang wajib sama dengan Terminal
   (I13 RSI).

---

## 9. Perintah

| Tempat | Perintah |
|---|---|
| `apps/edge-bff/terminal` | `npm run typecheck`; `npm test` (semua tes); `npx vitest run tests/calc` (parity); `npm run build` |
| `apps/edge-bff/terminal` (Flow oracle) | `npx vite-node ../../../verification/terminal_api/flow_indicators/oracle_compare.ts` |
| `apps/backtest-worker` | `npm run registry`; `npm run registry:check`; `npm test` |
| `apps/edge-bff/backtest` | `npm run typecheck`; `npm test` |
| `apps/edge-bff/screener` | `npm run registry`; `npm run registry:check`; `npm test`; `npm run tripwire` |
| `apps/screener-worker` | `npm test` |
| root repo | `python3 scripts/terminal_indicator_spec.py [--check]`; `python3 scripts/build_indicator_notes.py [--check]`; `python3 scripts/build_flow_registry.py [--check]` |
| root repo (Python tests) | `python3 -m pytest scripts/tests/test_indicator_notes.py scripts/tests/test_registries_current.py` |

Tes Terminal yang mengunci apa:
- `tests/calc/parity.test.ts`: rumus vs Feature 04, TA-Lib, referensi HTML.
- `tests/calc/edge.test.ts`: kunci `F` = 53, output, nilai bawaan, kasus tepi (harga datar, volume nol, H=L, data
  bolong).
- `tests/calc/explain.test.ts`: nilai kartu = nilai chart; setiap ID punya penjelasan.
- `tests/calc/flow.test.ts`: tepat FL01–FL39 dengan fungsi dan output.
- `tests/data/ind_card.test.ts`: setiap ID punya rumus di notes.
- `tests/data/inputs.test.ts`, `ind_menu.test.ts`: kebutuhan input dan isi menu.

---

## 10. Dokumen terkait

- `BACKTEST_END_TO_END.md` (aliran Backtest; bagian 14 rilis registry)
- `apps/edge-bff/backtest/CONTRACT.md:14-15` (rumus Backtest adalah modul Terminal, tidak disalin)
- `SCREENER_ONBOARDING.md` bagian 2.4 dan 2.11 (contoh menambah indikator)
- `verification/terminal_api/INDICATOR_SPEC.md`, `INDICATOR_ALIGNMENT.md`, `FRONTEND_ARCHITECTURE.md` bagian 18,
  `FRONTEND_HANDOFF.md`
- `verification/terminal_api/flow_indicators/FORMULAS.md` (rumus Flow)
- ERRORS M329 (rilis registry yang lupa dibangun ulang), M349 (Feature 04 di masa harga datar)

---

## 11. Perubahan EXEC-TERMINAL-IND-EDIT (2026-11-05)

Bagian ini menambah, bukan mengganti, isi di atas. Rincian keputusan: `EXEC.md`, EXEC-TERMINAL-IND-EDIT.

- **Menu menyembunyikan indikator lewat satu daftar** `MENU_HIDDEN` (`T/src/app/indMenu.ts`): I37, I41, FL07, FL35, FL36.
  `indRegistry.json` dan `indicators.ts` tidak disentuh, jadi Backtest dan Screener tidak berubah. Chart tersimpan yang
  memakainya tetap tergambar (restore membaca definisi, bukan menu).
- **Flow sekarang FL01–FL48.** FL40–FL48 baru (lihat `FORMULAS.md`). Tes menurunkan daftar id dari registry, bukan angka 39.
- **Aturan Sisi** (`sideParams`, `T/src/calc/flow.ts`): pada indikator ber-Sisi, Rank = Net atau Gross; Buy = Top-N pembeli,
  Sell = Top-N penjual. FL09 memakai rank-nya sendiri (`transactionSize`).
- **Registry Flow dibangkitkan** dari `build_spec_workbook.py` (lapisan "decisions 2026-11-05": `set_params`, `set_field`,
  baris FL40+) → `FLOW_INDICATORS_SPEC.xlsx` → `scripts/build_flow_registry.py`. `--check` sekarang dijalankan
  `scripts/tests/test_registries_current.py`. Indikator baru wajib punya tip di `PLAIN` (generator gagal jelas bila tidak).
- **Tampilan per garis**: output boleh punya skala kiri (`scale:'left'`) dan format sendiri (`fmt`), dipakai garis
  perubahan FL11/FL34 (poin) dan format yang bergantung pilihan (z-score, jumlah broker, rasio).
- **Pilihan menurut data**: di indeks (IHSG) pilihan Lot tidak ditawarkan dan simpanan Lot dibaca Rupiah
  (`offeredOptions`, `withoutLot`, `T/src/app/flowIndicators.ts`); pilihan "Transaksi" tanpa jumlah transaksi memberi garis
  kosong dengan pesan legend, bukan blokir dialog (validate mereset setting tersimpan, `indicators.ts`).
- **Setting tersimpan**: pilihan select yang tidak lagi ditawarkan kembali ke bawaan; gaya satu garis yang namanya berubah
  pindah ke garis pertama (`dropStale`, `indicators.ts`).
- **Kartu**: `withChange` (`T/src/calc/explain.ts`) untuk garis perubahan; semua kartu Flow juga diuji pada konteks indeks.

## 12. Sesudah 2026-11-06 (EXEC-TERMINAL-LOOK, EXEC-BROKER-INV-PANEL, EXEC-IND-DIALOG)

- Kartu indikator dihapus (user "2B"): `indCard.ts`, `calc/explain*.ts` dan tesnya tidak ada lagi; rujukan ke file itu di
  atas adalah sejarah. Tooltip hover (nama + `tip`) tetap.
- Jendela Indicators bergaya "Add a condition" Screener (`indMenu.ts`): baris abu-abu = setting bawaan dari registry
  (`defaultsText`), klik selalu menambah dengan notifikasi "added".
- Sumbu harga: desimal diturunkan dari harga instrumen (`data/priceFormat.ts`).
- FL23: bawaan `auto_c` (2 net buyer + 1 net seller di periode terlihat, dipilih sekali), tombol Brokers/Board/Investor di
  panelnya (`PANE_FILTERS`), label 0 (`zeroLabel` dari parameter tetap `start`).
- Panel kanan: lajur Domestic/Foreign/Total di Top brokers dan panel "Foreign × Domestic map" (`fdMap.ts`, `fdSplit`).

## 12. Perubahan EXEC-FLOW-NEW-3 dan EXEC-RP-LOOK-2 (2026-11-08)

Bagian ini menambah, bukan mengganti. Rincian keputusan: `EXEC.md`, EXEC-FLOW-NEW-3 dan EXEC-RP-LOOK-2.

- **Flow sekarang FL01–FL52.** FL49–FL52 tidak ada di spreadsheet: dibangkitkan oleh `extra_indicators()` di
  `scripts/build_flow_registry.py` (parameter bersama disalin dari FL22/FL23/FL24 agar label dan batas sama).
  Rumus di `FORMULAS.md`; tes `T/tests/calc/flow_new3.test.ts`. Screener tidak memakai `calc/flow.ts` (tidak berubah).
- **Garis opsional dari registry**: parameter bool dengan `line: true` (FL14 `avg`, FL50 `verdict`) menambah output
  bernama sama yang hanya digambar saat parameternya hidup (`o.hidden`, ikut `plotKeyOf`).
- **Jenis gambar baru**: `strip` dengan warna per kode (`o.quad`, FL49) dan `cells` (kolom kotak, Plot FL26) di
  `T/src/app/stripSeries.ts`. Pilihan Plot FL26 dari `PLOT_OPTIONS` (bawaan Histogram).
- **Garis di chart harga dengan sumbu kanan** (`o.scale === 'right'` di pane harga, FL52): tidak dikonversi ke mode Return,
  tidak memakai format harga. Garis yang namanya dari data memakai slot `b1..b5` + `_labels` (FL23, FL51, FL52).
- **Mengikuti tampilan**: `def.viewKey(params)` menyatakan candle mana yang diikuti (pertama dan/atau terakhir terlihat);
  `followView` menghitung ulang bila kuncinya berubah (menggantikan pengecualian id FL23).
- **Mengikuti panel Broker inventory**: `def.followsInventory` (FL52) dihitung ulang lewat `Ind.inventoryChanged`, yang
  dipanggil `broker.ts` setiap daftar broker berubah (`notify`).
- **Kotak mengambang**: `def.box(raw, params)` memberi HTML; mesin (`paintBox`, `placeBox`) menaruhnya di chart, menggeser
  dari kepala (`[data-drag]`), menyimpan posisi di `style.box`, dan menjalankan `data-broker` (tambah ke Broker Inventory)
  serta `data-act="view|pick"` (periode di tampilan / pilih di chart). Dicek di `look_check11.mjs`.
- **Khusus Terminal** (user 2026-11-08 "A"): `terminal_only` pada indikator (FL49–FL52) atau parameter garis (FL14 `avg`,
  yang juga tercatat di `terminal_only_outputs`) membuat Screener melewatinya (`build-screener-registry.mjs`
  `flowEntries`/`entryParams`). Indikator flow baru yang belum diputuskan untuk Screener diberi tanda ini; tanpa tanda dan
  tanpa baris di `flow-kinds.json`, pembuatan daftar Screener berhenti (disengaja).
