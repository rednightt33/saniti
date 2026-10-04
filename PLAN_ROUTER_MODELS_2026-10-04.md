# Rencana: daftar model di repo + router pesan pertama (2026-10-04)

Status: **RENCANA, belum dieksekusi.** Keputusan user yang sudah ada:
- router pesan pertama memakai DeepSeek V4.1 Flash, reasoning low;
- daftar model dimasukkan ke repo dan dijaga terbaru lewat AGENTS.md.

## 0. Kondisi infrastruktur (dicek ulang 2026-10-04 malam, baca saja)

**Railway:** proyek lucid-patience, satu environment `dev`, 15 layanan.

**Deployment yang sedang jalan:**

| Layanan | Deployment aktif | Asal | Catatan |
|---|---|---|---|
| `market-ai-orc` | `6b47c80f` SUCCESS | `main` `5dbe0de` (O2–O4, P28-D) | **M78 belum live**: commit `a3141c0` hanya di branch |
| `market-sql-governor` | `baed5b02` SUCCESS | `main` `a6d7ded` | Sesuai `main` |
| `market-python-sandbox` | `8f460c32` SUCCESS | **unggahan CLI 13:49** (sebelum merge) | Build dari `main` di-SKIP Railway. Isi diasumsikan sama dengan `main`, tetapi tidak bisa dibuktikan dari meta deployment |
| `market-web-governor` | `1ccfc59b` SUCCESS | **unggahan CLI 12:15** (sebelum merge) | Sama seperti sandbox |
| `orc-test-runner` | `f13b6bc6` SUCCESS | unggahan CLI | Suite `ma-qa-20261004a` selesai |

**Git:**
- `origin/main` = `81bfbea`;
- branch `claude/g2-g3-reactivation` = `cae9886`, **11 commit di depan `main`**: M78 (kode orc), fixture dan suite runner,
  dokumen benchmark dan rencana.

**Model yang dipakai (nilai variabel dev, bukan rahasia):**

| Layanan | Panggilan | Model | Setelan |
|---|---|---|---|
| orc | Semua panggilan (loop utama, router percakapan, klasifikasi balasan rencana) | `AI_MODEL` = `deepseek/deepseek-v4.1-flash` (`AI_MODEL_SWITCH=1`); cadangan `AI_MODEL_2` = `xiaomi/mimo-v2.6-flash` | Lihat rincian di bawah |
| web-governor `/v1/fact`, `/v1/ask`, riset kriteria | Slot bawaan `WEB_DEFAULT_SLOT=1` | `deepseek/deepseek-v4.1-flash` (`WEB_OPENROUTER_MODEL`) | `WEB_OPENROUTER_MAX_OUTPUT_TOKENS=8000`, engine `exa`, `WEB_MAX_RESULTS_PER_SEARCH=30`, timeout 90 s, 3 retry |
| web-governor klasifikasi event | `WEB_CLASSIFIER_SLOT=2`, cek silang `WEB_CLASSIFIER_CHECK_SLOT=1` | **`xiaomi/mimo-v2.5`** (slot 2), dicek DeepSeek (slot 1) | Reasoning klasifikasi mati (bawaan kode) |
| web-governor slot 3 | Tidak dipakai endpoint mana pun secara bawaan | `z-ai/glm-5.3-flashx` | — |

Rincian setelan orc:
- `AI_REASONING_EFFORT=high` (router dan klasifikasi memakai `low` di kode);
- `AI_MAX_OUTPUT_TOKENS=24000`, `AI_MAX_CONTEXT_TOKENS=500000`, `AI_MAX_HISTORY_TOKENS=150000`;
- `AI_REPLAY_REASONING=true`, `AI_CAPTURE_REASONING=true`;
- `AI_PROVIDER_MAX_CACHE_PRICE_RATIO=0.25`, `AI_PROVIDER_SORT` tidak diset;
- `AI_MODE_SWITCH=4`, `AI_MAX_ANALYSIS_SECONDS=1800`, `AI_REQUEST_TIMEOUT_SECONDS=600`.

**Layanan lain** (sandbox, governor, audit-store, telegram-monitor/trigger, ai-data-coverage, feature-01-worker, cron
harga): tidak punya variabel model atau kunci.

**Kode `apps/market-ai-backend`** (memanggil OpenAI/OpenRouter) **tidak punya layanan Railway**.

**Sandbox:** masa simpan hasil dan bundle 24 jam.

**Kunci OpenRouter orc:** batas USD 30, sisa **± USD 3,61**. Web-governor memakai kunci sendiri; sisanya belum dicek.

**Dampak pada rencana:**
1. Push ke `main` akan men-deploy orc (M78 + kode baru). Folder sandbox dan web-governor tidak berubah, jadi build
   mereka akan di-SKIP lagi dan tetap berjalan dari unggahan CLI.
2. Supaya semua layanan terbukti berjalan dari `main`, sandbox dan web-governor perlu dideploy ulang dari `main`
   sekali. Langkah 0b.
3. **Pemakaian MiMo V2.5 di klasifikasi web-governor** belum tercatat di AGENTS.md. `AI_MODELS.md` akan mencatatnya.
   Mengganti modelnya tetap butuh keputusan user.

## 0b. Sinkronkan deployment dengan `main` (baru)

- **Langkah:** sandbox dan web-governor dideploy dari `main` (redeploy dari sumber GitHub `main`, bukan unggahan
  CLI). Ditunggu `SUCCESS`, cek `/v1/runtime` sandbox dan log startup web-governor.
- **Kapan:** sebelum tes R-STORE, supaya hasil tes berasal dari kode yang tercatat.
- **Risiko:** pertanyaan yang sedang berjalan terputus. Tidak ada saat ini; runner selesai.
- **Catatan:** `RAILWAY_CHANGELOG.md`, `config pull`/`plan`.

## 1. Deploy M78 (sudah dikodekan, menunggu)

- **Isi:** giliran tanpa teks dan tanpa panggilan alat diulang dengan alat yang sama. Commit `a3141c0` di branch;
  1061 tes lulus.
- **Langkah:**
  1. push `main`;
  2. tunggu deploy orc `SUCCESS` dan cek log startup;
  3. catat di `RAILWAY_CHANGELOG.md`.
- Digabung dengan langkah 3 bila langkah 3 selesai di hari yang sama, supaya cukup satu deploy orc.

## 2. `AI_MODELS.md`: daftar model, dibuat dari kode

**Kelas masalah:** setelan model tersebar di kode, variabel Railway dan dokumen keputusan. Model, token, reasoning dan
aturan penyedia untuk setiap panggilan tidak bisa dilihat di satu tempat, dan bisa berubah tanpa tercatat.

**Generator `scripts/generate_ai_models_doc.py`**, pola yang sama dengan `AI_TOOLS.md`:

1. **Titik panggilan.** AST memindai `apps/*/app/*.py` untuk setiap payload model (dict dengan kunci `model` dan
   `input`/`messages`/`instructions`), termasuk payload yang dibuat lewat fungsi pembantu lalu diubah (`payload["x"] = …`).
   Per titik dicatat:
   - layanan, file, fungsi;
   - model (ekspresi + nilai setelan);
   - reasoning;
   - `max_output_tokens`;
   - alat (mis. `openrouter:web_search`, engine, `max_results`);
   - keluaran terstruktur (`json_schema`);
   - `store`, aturan penyedia (`require_parameters`, `ignore` dari aturan cache, `sort`);
   - kunci sesi (sticky routing / prompt cache).
2. **Setelan.** Nama variabel dan nilai bawaan dibaca dari `config.py` tiap layanan, disaring ke yang berkaitan dengan
   model: MODEL, REASONING, TOKENS, PROVIDER, CONTEXT, ENGINE, SLOT, RESULTS, REPLAY, MODE_SWITCH, ROUTER.
   - **Penjaga keamanan:** nama berakhiran `_KEY`, `_SECRET`, `_PASSWORD`, `_URL`, `_TOKEN` tidak pernah dibaca.
3. **Snapshot dev.** Nilai variabel di atas diambil dari `railway variables --kv`, hanya untuk nama hasil saringan.
   - Nilai ditolak bila berbentuk kunci (`sk-`, string panjang acak).
   - Disimpan di antara penanda; diperbarui dengan `--dev-values`.
4. **Model yang dipakai sekarang** per titik panggilan, diturunkan dari snapshot: `AI_MODEL_SWITCH` dan slot web
   governor.
5. **Satu-satunya bagian tulis tangan:** `PURPOSE`, satu kalimat per titik panggilan. Titik baru tanpa kalimat
   membuat generator gagal.

**Tes drift:** `apps/market-ai-orc/tests/test_ai_models_doc.py` (pola `test_ai_tools_doc.py`).

**Rincian eksekusi:**
1. Generator membaca kode tiga folder (`market-ai-orc`, `market-web-governor`, `market-ai-backend`) tanpa
   mengimpor layanan lain.
2. Pemetaan slot web-governor ke endpoint diturunkan dari kode (`settings.slot(None)`, `classifier_slot`,
   `classifier_check_slot`), bukan ditulis tangan.
3. Snapshot dev dibuat dari perintah baca `railway variables --kv`. Hanya nama yang lolos saringan; nilai rahasia
   ditolak.
4. Jalankan tes orc penuh + tes doc baru.
5. Push ke branch dulu. Push ke `main` digabung dengan langkah 3 (satu deploy orc), karena tes orc menyentuh folder
   orc.

**AGENTS.md:** aturan baru di "Mandatory workflow". Setiap kali titik panggilan model ditambah atau diubah, atau
variabel model/reasoning/token/penyedia diubah di Railway, regenerasi `AI_MODELS.md` di task yang sama (dengan
`--dev-values` untuk perubahan Railway). Ditambah satu baris di bagian "Model and provider" yang menunjuk ke file ini.

**Tidak mencakup:** model yang dipakai di luar repo (misalnya alat lokal user).

## 3. Router pesan pertama + penahan mode 4

**Dasar:** `ROUTER_BENCHMARK_2026-10-04.md`; benar 31/32 pada set uji, 0 pertanyaan data salah dikirim ke jalur tanpa
data.

**Desain (orc):**
- **Saklar baru `AI_ENABLE_FIRST_TURN_ROUTER`:** bawaan mati, nyala di dev.
- **Kapan router dipakai:** hanya bila
  - permintaan tanpa `analysis_path`;
  - mode bawaan = 4;
  - **tidak** ada rencana yang menunggu;
  - percakapan belum punya giliran.

  Pesan lanjutan tetap memakai router percakapan yang ada.
- **Panggilan:** satu panggilan tanpa alat, `self.settings.reasoning("low")`, model `AI_MODEL`, keluaran
  `json_schema` ketat {route, reason}. Pola yang sama dengan `classify_turn`, dan dicatat di log seperti router
  sekarang. Gagal → perilaku lama (mode 4 penuh).
- **Rute → yang dijalankan:**

  | Rute | Dijalankan |
  |---|---|
  | CHAT | Satu langkah tanpa alat data. Memakai jenis CONVERSATIONAL yang sudah ada (alat baca saja) |
  | FACT | Satu langkah, alat baca + `find_web_fact` + katalog, tanpa tarik data gudang |
  | ANALYSIS | Langkah A mode 4 saja (tanpa B–D) |
  | RESEARCH | Rencana untuk persetujuan user (jalur RESEARCH yang ada) |
  | EXPLORE | Mode 4 penuh seperti sekarang |
- **Penahan backend (permanen, terlepas dari router):** B–D mode 4 hanya jalan bila jawaban A punya angka dari sumber
  data.
  - Sinyalnya: label bukti / provenance jawaban A yang sudah dihitung backend.
  - **Diverifikasi dulu di kode** apakah `evidence_label` A terisi hanya bila ada angka data. Bila tidak, dipakai
    `data_kinds` provenance.
- **Instruksi router** di kode, bersama 46 contoh benchmark sebagai tes (set uji tetap).

**Tes:**
- satu tes per rute;
- router gagal → mode 4 penuh;
- `analysis_path` diisi → router tidak dipanggil;
- pesan lanjutan → router lama;
- penahan: A tanpa angka data → B–D tidak jalan; A dengan angka data → jalan;
- tes mode 4 lama tetap lulus dengan saklar mati.

**Dokumen:** `AI_MODELS.md` (titik panggilan baru), `AI_TOOLS.md` bila saklar ikut dicatat di sana, README orc,
`ERRORS_AND_SOLUTIONS.md` (M79), `RAILWAY_CHANGELOG.md`.

**Verifikasi live** (suite kecil, ± USD 0,05): "bagaimana kabarmu", g13 (BUMN), q1 (Z-score) dan q7 (ekspor) satu kali
lewat mode bawaan.

| Pertanyaan | Hasil sekarang | Target |
|---|---|---|
| g13 | 23 menit | < 1 menit |
| Sapaan | Belum diukur | < 10 detik |
| q1 | ANALYSIS | Sama seperti sekarang, tanpa B–D |
| q7 | — | EXPLORE |

## 4. Putaran tes berikutnya (`qa_20261004b`)

Dijalankan setelah langkah 1 dan 3 (satu unggahan runner):
- q2 dan q3 diulang (M78);
- Pine Script salah;
- Pine Script benar;
- ekspor/perang dagang (q7).

## 5. Temuan dari suite `ma-qa-20261004a` yang masuk catatan (belum diperbaiki)

| Kode | Temuan | Akar masalah | Usulan |
|---|---|---|---|
| M79 | Pertanyaan fakta g13 menjalani mode 4 penuh (23 menit) | Pesan pertama tidak dinilai; B jalan bila A tidak gagal | Langkah 3 |
| P29 | g9.3: "data terbaru berakhir 31 Agustus" padahal data sampai 2 Okt | AI menyamakan rentang yang ia pesan dengan rentang data yang tersedia | Belum diusulkan; verifikasi lewat log reasoning dulu |
| M80 | g5.11 "ekspor hasil uji ke Excel": LIMITED setelah 12 menit | Statistik hasil riset multi-sudut hanya ada sebagai temuan backend, bukan tabel output; `export_result` hanya mengekspor tabel. Turn dirouting CONTINUE (bukan baca), jadi O3 tidak teruji di sini | Rilis temuan riset sebagai tabel output standar (juga berguna untuk visual). Butuh desain |
| P30 | q6.2: AI menolak membuat trade setup (entry/SL/target) | Instruksi produk: hasil "bukan sinyal perdagangan" | **Keputusan user:** apakah produk boleh memberi trade setup (dengan disclaimer dan dasar data)? |

## 5b. Disetujui user (2026-10-04, sore)

- **M80 (a), permanen, backend:** saat riset (multi-sudut atau hipotesis) selesai, backend merilis temuannya sebagai
  satu tabel output standar.
  - Satu baris per sudut/kandidat: sudut, status, estimasi, CI bawah, CI atas, p, p-adjusted, sampel efektif, flag,
    satuan.
  - Diturunkan dari temuan yang sudah dihitung backend: tanpa hitung ulang, tanpa AI.
  - Bisa diekspor, digambar dan dirujuk `out.oN`.
  - **Tes:** multi-sudut dan hipotesis (dua kasus berbeda), ekspor tabel itu, dan rujukan nilainya.
- **M80 (b), router:** permintaan ekspor, unduh atau "tampilkan tabel/kode" atas hasil yang sudah ada digolongkan
  sebagai aksi baca. Instruksi router sekarang dicek dan diukur dengan contoh kalimat dulu, dikerjakan bersama
  langkah 3.
- **Tes kedaluwarsa R-STORE disetujui:**
  - `PY_SANDBOX_RESULT_RETENTION_HOURS=1` dan `PY_SANDBOX_BUNDLE_RETENTION_HOURS=1` selama putaran tes;
  - setelah itu dikembalikan ke 24;
  - `config pull`/`plan` dan `RAILWAY_CHANGELOG.md`.
- **P30 (trade setup):** ditunda.

## 6. Keputusan yang dibutuhkan dari user

1. **P30 (trade setup):** ditunda oleh user.
2. **Pemilihan data dan bentuk tampilan ke user:** benchmark dulu (`DISPLAY_BENCHMARK_2026-10-04.md`).

## Urutan dan biaya

| Urutan | Langkah | Deploy | Catatan |
|---|---|---|---|
| 0 | Langkah 0b (sinkron `main`) | Sandbox + web-governor | Baca hasil, tanpa biaya model |
| 1 | Langkah 2 | Tanpa deploy layanan | Dokumen + tes. Tes orc menyentuh `apps/market-ai-orc` → ikut deploy berikutnya |
| 2 | Langkah 3 + M78 | Satu deploy orc | — |
| 3 | Verifikasi live langkah 3 | — | ± USD 0,05 |
| 4 | Langkah 4 | — | ± USD 0,5–1,0 |

Total sisa kunci orc ± USD 3,61 (dicek 2026-10-04 malam).
