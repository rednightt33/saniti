# Rencana: daftar model di repo + router pesan pertama (2026-10-04)

Status: **RENCANA, belum dieksekusi.** Keputusan user yang sudah ada:
- router pesan pertama memakai DeepSeek V4.1 Flash, reasoning low;
- daftar model dimasukkan ke repo dan dijaga terbaru lewat AGENTS.md.

## 0. Kondisi infrastruktur (dibaca 2026-10-04)

**Railway:** proyek lucid-patience, satu environment `dev`, 15 layanan. Yang memanggil model AI hanya dua:

| Layanan | Model | Sumber deploy | Kunci |
|---|---|---|---|
| `market-ai-orc` | `AI_MODEL` = `deepseek/deepseek-v4.1-flash` (`AI_MODEL_SWITCH=1`), cadangan `AI_MODEL_2` | GitHub `main`, watch `/apps/market-ai-orc/**` | `OPENROUTER_API_KEY` (batas kunci USD 30, sisa ± USD 3,62) |
| `market-web-governor` | Slot `WEB_SLOT_1..3_*` + `WEB_OPENROUTER_MODEL` (slot 1 = DeepSeek V4.1 Flash) | GitHub `main`, watch `/apps/market-web-governor/**` | Kunci OpenRouter milik layanan sendiri |

**Layanan lain tanpa kunci atau variabel model:** sandbox, governor, audit-store, telegram-monitor/trigger,
ai-data-coverage, feature-01-worker dan cron harga (dicek nama variabelnya saja).

**Kode lama `apps/market-ai-backend`:** masih memanggil model, tetapi **tidak punya layanan Railway**; dicatat sebagai
"tidak dideploy".

**Titik panggilan model** (dipindai dari kode, AST):
- **orc:** loop utama `_payload`, router percakapan `classify_turn`, klasifikasi balasan rencana `_classify_reply`.
- **web-governor:**
  - `/v1/fact`: `_search`, `_extract`;
  - `/v1/ask`: `_plan`, `_scan`, `_read_articles`, `_review`, jawaban, `_implications`, `_follow_ups`;
  - `provider.py`: `research_criterion`, `read_document`, `classify`.

**Cara deploy sekarang:**
- push ke `main` yang menyentuh folder layanan langsung men-deploy layanan itu;
- runner tes diunggah lewat CLI;
- perubahan variabel memakai `--skip-deploys` lalu redeploy.

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
| 1 | Langkah 2 | Tanpa deploy layanan | Dokumen + tes. Tes orc menyentuh `apps/market-ai-orc` → ikut deploy berikutnya |
| 2 | Langkah 3 + M78 | Satu deploy orc | — |
| 3 | Verifikasi live langkah 3 | — | ± USD 0,05 |
| 4 | Langkah 4 | — | ± USD 0,5–1,0 |

Total sisa kunci ± USD 3,62.
