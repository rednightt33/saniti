# Analisis golden test `ma-golden-20261004a`: kenapa lama, jawaban mana yang salah, dan di mana model keliru (2026-10-04)

Ini lanjutan bagian 3 `GOLDEN_TEST_ROUND_2026-10-03.md`, atas permintaan user: periksa log percakapan, temukan letak
kesalahan model, bandingkan dengan sumber luar, lalu usulkan solusi dengan risiko dan mitigasinya, dan uji ulang.

## Sumber bukti

| Sumber | Isi |
|---|---|
| Log `market-ai-orc` | 4.262 baris JSON, 05:46–07:26 UTC, diambil per jendela 3 menit (`railway logs --since/--until --json`, maks. 5.000 baris per jendela). Berisi 838 panggilan model, 57 ringkasan biaya, gerbang, penolakan argumen, dan reasoning model (`AI_CAPTURE_REASONING`) |
| Kode yang dijalankan | `AI_conversation_execution`, 58 eksekusi dari g5.6, g6, g9; dibaca lewat job baca-saja `verify-job2` (sudah dihapus) |
| Dump respons runner | 30 dari 31 pesan |
| Hitung ulang independen | `verify-job` (kemarin) dan `verify-job3`: RMS return 6.150 saham-tahun, untuk menguji usulan aturan satuan |

## 1. Kenapa lama (total 8.628 detik waktu run, 838 panggilan model)

**88% waktu adalah model yang berpikir** (7.616 detik). Alat dan sistem hanya 1.012 detik.

| Waktu model per jenis langkah | Panggilan | Detik | USD | Detik/panggilan |
|---|---|---|---|---|
| riset (mode 4) | 252 | 2.209 | 0,490 | 8,8 |
| analisis | 159 | 1.180 | 0,241 | 7,4 |
| rencana riset | 52 | 1.036 | 0,349 | 19,9 |
| langsung | 145 | 1.010 | 0,337 | 7,0 |
| usulan riset berikutnya | 40 | 687 | 0,193 | 17,2 |
| lanjutan (setuju/revisi) | 47 | 567 | 0,248 | 12,1 |
| baca ulang / klarifikasi | 107 | 564 | 0,211 | 5,3 |
| hitung ulang | 36 | 364 | 0,112 | 10,1 |

Ada tiga penyebab, diurutkan menurut dampaknya.

### 1a. Gerbang bukti meminta alat yang tidak diberikan (G23 / G9). Terverifikasi.

- **Gejala:** g9 pesan 2 memanggil `get_lineage` 57 kali sampai mencapai batas 60 iterasi. g9 pesan 1 memanggilnya 45 kali.
- **Bukti di log:** pada iterasi 2, `ai_final_gate EVIDENCE REJECTED_FOR_REPAIR` dengan perintah "Call get_evidence...".
  - Alat yang ditawarkan ke run itu tidak memuat `get_evidence`. Router mengklasifikasi pesan sebagai `CLARIFY`, sehingga
    hanya alat baca-saja yang ditawarkan.
  - Reasoning model iterasi 3: "There's no get_evidence tool... the instruction says to call get_evidence".
  - Iterasi 20: "I keep looping. I must stop."
  - Iterasi 59: "I'm stuck in a loop."
- **Bukti di kode:** `orchestrator._evidence_gate` memeriksa `"get_evidence" in self.registry.names()`, yaitu semua alat
  yang terdaftar, bukan alat yang ditawarkan ke run ini. Run klarifikasi, run riset (`m4c`) dan run baca-ulang (`m4q`)
  tidak menawarkan `get_evidence`, tetapi gerbang tetap memintanya.
- **Skala:** gerbang muncul di 17 run tanpa `get_evidence`. Setelah gerbang, terpakai **245 panggilan model (29% dari
  semua panggilan), 1.663 detik (19%), USD 0,39 (18%)**, termasuk 198 panggilan `get_lineage` yang sia-sia. Pada 12 run
  yang punya alatnya, gerbang hanya menambah 35 panggilan dan 279 detik.
- **Kelas masalah:** setiap gerbang yang perbaikannya membutuhkan alat yang tidak ditawarkan ke jenis run tersebut. Ini
  berlaku untuk gerbang bukti, dan nanti setiap gerbang baru di run klarifikasi, rencana, riset, dan data makro/lintas aset.
- **Model:** model gagal "berhenti dan menjawab". Ia terus mencoba mematuhi perintah yang mustahil. Ini sejalan dengan
  literatur: loop terjadi ketika umpan balik validator mengarahkan model kembali ke aksi tanpa batas yang kuat.

### 1b. Mode 4 menambahkan riset, rencana dan usulan ke pertanyaan angka sederhana. Terverifikasi (M73).

Pada 4 pertanyaan angka (g7 ×2, g8, g9 pesan 1):
- jawabannya sendiri: 71 panggilan, 248 detik, USD 0,146;
- riset, rencana dan usulan otomatis: **151 panggilan, 1.570 detik (6×), USD 0,364**.

Contoh g8: jawabannya lewat `query_metric` hanya 28 detik dan USD 0,013, tepat sampai ke rupiah; riset otomatisnya
menambah 219 detik. Mode bawaan 4 adalah keputusan user (2026-09-30).

### 1c. Variasi kecepatan antar-provider dan output rencana yang panjang. Terverifikasi, dampak sedang.

- Median kecepatan 210 token/detik, tetapi ada panggilan yang hanya 63 token/detik. Model dilayani 9 provider berbeda
  (Together 425 panggilan, InferenceNet 202, Parasail 159, dst.).
- Panggilan rencana menulis rata-rata 4.500 token output dan 3.100 token reasoning (19,9 detik per panggilan).
  Panggilan terlama 131 detik (rencana g5.1).
- Pengaturan provider dan model adalah keputusan user (AGENTS.md: jangan set `AI_PROVIDER_SORT` tanpa persetujuan).

## 2. Jawaban yang salah dan letak kesalahan model

### P27: g5 pesan 6, "efek hanya di bank BUMN". Jawaban "0,00% vs 0,00%", putusan NOT_SUPPORTED tidak sah.

- **Letak kesalahan model:**
  - Reasoning iterasi 5: "Safer: pass percent values since unit is PERCENT... I'll go with percent (×100)."
  - Kode yang dijalankan (`exe_d079…`, `exe_b557…`): `p['fwd5'] = close.shift(-5) / close - 1` (pecahan), lalu dikirim
    apa adanya ke `event_summary(...)`. Perkalian 100 tidak pernah ditulis.
  - Tabel per bank di eksekusi yang sama *dikali 100* dengan label PERCENT, sehingga tabel itu benar. Jadi model
    konsisten untuk tabel, tetapi tidak untuk input statistik.
  - Ini adalah **ketidaksesuaian antara reasoning dan aksi** (unfaithful reasoning): model *berniat* ×100, tetapi kodenya
    tidak.
- **Letak kesalahan sistem:**
  - `event_summary` menerima angka berapa pun di bawah satuan rencana (PERCENT).
  - Penjaga P26 (`research_findings.unit_problem`) hanya memeriksa arah sebaliknya: DECIMAL dengan RMS > 1.
  - Ambang efek 0,50 (persen) lalu dibandingkan dengan selisih −0,0009 (pecahan). Putusan selalu NOT_SUPPORTED.
  - Format `pctv:2` mencetak −0,0041 menjadi "0,00%".
- **Kelas masalah:** setiap hasil atau ambang yang nilainya berasal dari kode model, sementara satuannya hanya dari
  deklarasi: frame hipotesis dan riset, dan nanti data makro dalam basis poin atau poin indeks.

### M71: g5 pesan 5–6, BBCA dimasukkan ke "bank BUMN".

- **Letak kesalahan model:**
  - Reasoning iterasi 3: "Need to figure out BUMN tickers... BBCA, BBRI, BMRI, BBNI, BBTN, BRIS... I know these from
    real-world... Better to read the universe in the session and identify BUMN by company name containing 'Persero'."
    Rencana pemeriksaan itu tidak dijalankan.
  - Kode: `bumn = ['BBCA','BBRI','BMRI','BBNI','BBTN','BRIS']`, ditulis langsung dari pengetahuan model.
- **Fakta (sumber luar):**
  - Bank BUMN yang tercatat di BEI adalah BBRI, BMRI, BBNI dan BBTN.
  - BRIS adalah *anak usaha* BUMN (dikendalikan Bank Mandiri), bukan BUMN.
  - BBCA adalah bank swasta, dikendalikan keluarga Hartono (Djarum) lewat PT Dwimuria Investama Andalan (±55%).
  - Daftar model salah pada 2 dari 6 saham (33%).
- **Letak kesalahan sistem:** gudang data tidak punya atribut BUMN (keputusan 6 masih terbuka), dan tidak ada aturan yang
  menolak pengelompokan tanpa sumber data.
- **Kelas masalah:** setiap pengelompokan yang disebut user tetapi tidak punya kolom di data, misalnya BUMN, grup
  konglomerasi, keanggotaan indeks, kelompok negara/region untuk makro.

**Koreksi 2026-10-04 (log reasoning g5.5–g5.6):** daftar BUMN *tampil* di bagian Asumsi rencana g5.5 ("Bank BUMN = …: BBCA, BBRI, BMRI, BBNI, BBTN, dan BSI/BRIS"), bukan tersembunyi; persetujuan diberikan runner otomatis. Jejak reasoning: it1–it2 benar ("BBCA is private (Djarum); BUMN banks: BMRI, BBRI, BBNI, BBTN"), katalog dicek dan tidak ada kolom BUMN; it3 memakai aturan dari data (nama perusahaan mengandung "(Persero)", yang menambah BRIS); it5 daftar akhir menambah BBCA, bertentangan dengan reasoning-nya sendiri (kemungkinan terbawa "empat bank besar BBCA, BBRI, BMRI, BBNI" dari jawaban g5.4). g5.6 memakai asumsi rencana yang sudah disetujui. **Tidak ada pencarian web:** tidak ada alat web yang ditawarkan maupun dipanggil di seluruh run.

### M72: g6_revise pesan 1, baris tanpa nilai RSI masuk ke kelompok pembanding.

- **Letak kesalahan model:** kode `exe_94b6…`:
  `baseline = elig[(elig['rsi14'] >= 30) | elig['rsi14'].isna()]`, yaitu model *sengaja* memasukkan NaN.
  - Run lain untuk pertanyaan yang sama (g6_rsi, `exe_2789…`) menulis `df['rsi14'].notnull()` dengan benar.
  - Jadi pilihan desain model tidak stabil antar run.
- **Dampak:** 672 baris ekstra (48 saham × 14 hari pemanasan RSI). Selisihnya 0,1 pp, tidak mengubah kesimpulan.
- **Kelas masalah:** kondisi yang tidak bisa dievaluasi (masa pemanasan indikator, celah data) masuk ke salah satu
  kelompok. Ini berlaku untuk setiap indikator bergulir.

### G23 / G9 pesan 2, MAX_ITERATIONS

Akar masalahnya sama dengan 1a. Pertanyaan "saham mana yang tertinggi?" sudah dijawab benar oleh model pada iterasi 2
(BBRI −3,3846%). Jawaban itu ditahan oleh gerbang bukti, lalu model terjebak loop.

## 3. Pembanding eksternal

| Masalah | Yang dikatakan sumber luar | Posisi kita |
|---|---|---|
| Loop agen (1a) | "When Agents Do Not Stop" (arXiv 2607.01641): 69% kegagalan loop berasal dari umpan balik retry/validator dan iterasi alat yang tidak dibatasi kuat; akibat utamanya biaya API habis. Praktik yang dianjurkan: deteksi tanpa-kemajuan dari tuple (alat, argumen, hasil) yang sama, pemutus keras (agent-loop-guard), dan umpan balik validator yang jelas | Kita punya batas keras 60 iterasi, tetapi tidak ada deteksi tanpa-kemajuan, dan umpan balik gerbang *tidak bisa dipenuhi* |
| Satuan (P27) | Kesalahan satuan dan skala (persen vs basis poin, juta vs miliar, rasio vs absolut) adalah kelas kesalahan utama LLM di analisis keuangan (Fin-RATE). Praktik: satuan dibawa bersama nilai (Pint), dan asersi runtime pada kode buatan LLM (Flowco) | Satuan hanya dideklarasikan; nilai dari kode model tidak dicek |
| Pengelompokan tanpa data (M71) | AbstentionBench: model reasoning (DeepSeek R1, s1) rata-rata 24% *lebih jarang* menolak menjawab daripada versi non-reasoning; menolak harus ditegakkan sistem. Text-to-SQL: "content hallucination" adalah filter pada nilai yang tidak ada di database | Model kita adalah model reasoning; ia menebak tanpa menyatakannya |
| NaN indikator (M72) | TA-Lib: RSI(14) butuh 15 harga sebelum nilai pertama, dan sebelum itu NaN; Wilder butuh K·n bar agar stabil. pandas: perbandingan dengan NaN selalu False, sehingga negasi kondisi memasukkan NaN | Helper riset tidak menegakkan aturan "kondisi NaN dikeluarkan dari kedua kelompok" |
| Reasoning ≠ aksi (P27) | CoT tidak selalu setia pada aksi; tingkat ketidaksetiaan di model produksi sampai ±13% (Arcuschin dkk., "CoT in the wild is not always faithful") | Kita tidak boleh bergantung pada niat di reasoning; backend harus menghitung atau memeriksa |
| Biaya rute (1b) | RouteLLM: merutekan pertanyaan sederhana ke jalur murah menghemat 35–85% biaya dengan 95% kualitas | Mode 4 menjalankan jalur riset penuh untuk semua pertanyaan |
| Latensi provider (1c) | OpenRouter: `provider.sort = "throughput"` atau `:nitro`; reasoning bisa dimatikan atau dikurangi per permintaan | Default provider routing (keputusan user) |

## 4. Solusi, risiko dan mitigasi

| # | Solusi (lapisan) | Mengatasi | Risiko | Mitigasi | Permanen? |
|---|---|---|---|---|---|
| S1 | **Gerbang hanya meminta alat yang ditawarkan ke run itu** (orc, `_evidence_gate` dan `_gate_once`). Gerbang membaca daftar alat run, bukan registry. Bila alatnya tidak ada, langsung pakai label "bukti tidak dihitung". Tes kontrak: setiap jenis gerbang × setiap set alat router | G23/G9, 1a | Jawaban di run klarifikasi/riset keluar tanpa bukti per klaim | Label "bukti tidak dihitung" tetap tampil. Alternatif: tawarkan `get_evidence` di run baca-ulang (`m4q`) karena murah | Permanen |
| S2 | **Pemutus tanpa-kemajuan** (orc): hash (alat, argumen, hasil); bila sama 3× berturut-turut, panggilan diblok dengan alasan terstruktur, lalu model wajib menjawab | Semua loop, termasuk yang belum ditemukan | Memotong ulangan yang sah | Hanya blok bila *hasilnya* juga identik (bukan hanya nama alat) | Permanen, jaring pengaman |
| S3 | **Hasil yang bisa diturunkan dihitung backend; nilai dari kode dicocokkan sampel** (sandbox/research): untuk hasil berbasis harga (forward return), backend menghitung ulang sampel baris dari harga yang ia pegang dan membandingkan rasio. Rasio ±100 berarti salah satuan dan ditolak dengan pesan jelas. Untuk hasil bukan harga: helper `forward_return(..., unit=approved)` wajib, dan kolom membawa satuannya | P27 | Biaya hitung ulang; hasil non-harga tidak bisa dicek | Sampel ≤ 500 baris; hasil non-harga diberi status "satuan dideklarasikan, tidak dicek" | Permanen |
| S4 | **Pengelompokan tanpa sumber data ditolak** (orc planner + katalog): kelompok yang disebut user (BUMN, grup, indeks) harus berasal dari kolom/tabel referensi yang ada. Bila tidak ada, jawab bahwa data itu tidak ada dan minta user memberi daftar, atau tunggu keputusan 6 | M71 | Pertanyaan wajar tertolak | User bisa memberi daftar sendiri; daftar itu dicatat di definisi output sebagai "dari user" | Permanen (+ keputusan 6 untuk data) |
| S5 | **Kondisi NaN dikeluarkan dari kedua kelompok** (sandbox helper `event_summary` / riset): baris dengan kondisi atau hasil NaN dibuang dan jumlahnya dilaporkan; helper menyediakan kolom kondisi tiga nilai (benar / salah / tidak terdefinisi) | M72 | Jumlah baris berubah dibanding jawaban lama | Laporkan `rows_condition_undefined` di temuan | Permanen |
| S6 | **Rute sederhana tanpa riset otomatis** (orc mode 4, *keputusan user*): pertanyaan angka/deskriptif hanya dijawab analisis, dan riset ditawarkan sebagai usulan satu kalimat, bukan dijalankan | 1b | User kehilangan riset yang tidak diminta | Riset tetap tersedia lewat "jalankan riset" atau `analysis_path` | Keputusan user |
| S7 | **Kecepatan provider** (*keputusan user*): `provider.sort=throughput` / ambang throughput minimum, atau reasoning effort lebih rendah untuk langkah usulan | 1c | Biaya per token bisa naik; kualitas usulan turun | Uji A/B kecil dulu | Keputusan user |

TEMPORARY yang **tidak** diusulkan: menambah kalimat di prompt ("kalikan 100", "BBCA bukan BUMN"). Itu hanya menambal
contoh yang terlihat dan tidak melindungi kasus lain.

## 5. Uji ulang (benchmark kedua) atas usulan

| Solusi | Cara diuji ulang | Hasil |
|---|---|---|
| S1 | Kontrafaktual dari log 838 panggilan: buang semua panggilan setelah gerbang di run tanpa `get_evidence` | **−245 panggilan, −1.663 detik (−19% waktu), −USD 0,39 (−18%)**; g9 pesan 2 selesai di iterasi 2 dengan jawaban benar |
| S2 | Kontrafaktual: blok bila set alat sama diulang >3× | Proksi berbasis nama memotong 201 panggilan (1.186 detik, USD 0,27), tetapi juga memotong `run_research_code` yang sah. Karena itu S2 harus memakai hash argumen dan hasil (sesuai literatur), bukan nama saja |
| S3 (versi naif ditolak) | Aturan skala "PERCENT dengan RMS kecil = pecahan" diuji pada RMS return 6.150 saham-tahun dari gudang data | **Tidak ada ambang aman.** 1,3% saham-tahun persen (saham tidur, RMS ≈ 0) salah dianggap pecahan di setiap ambang ≥ 0,1. Pada horizon 20 hari, pecahan mencapai 5,3 (530%), sehingga ambang 1,0 salah 0,9%. Maka pemeriksaan skala ditolak sebagai penjaga utama, dan S3 memakai *hitung ulang sampel dari harga* (rasio tepat 100, tidak ada salah tangkap untuk hasil berbasis harga) |
| S4 | Dibandingkan dengan daftar BUMN resmi | Daftar model salah 2/6. S4 akan menolak atau meminta daftar, bukan menebak. AbstentionBench menunjukkan aturan prompt tidak cukup untuk model reasoning, sehingga penegakan di backend dibenarkan |
| S5 | Hitung ulang independen (`verify-job`) | Dengan kondisi NaN dibuang: 84.166 baris pembanding (sama dengan run g6_rsi). Run g6_revise memakai 84.819 (+672). Dengan S5 kedua run akan memberi angka yang sama |
| S6 | Kontrafaktual pada 4 pertanyaan angka | **−1.570 detik dan −USD 0,36** (−71% biaya untuk pertanyaan itu). Sejalan dengan RouteLLM (35–85%) |

Gabungan S1 + S6 pada run ini: kira-kira −3.200 detik waktu model (−42%) dan −USD 0,75 (−34%), tanpa mengubah satu pun
angka yang sudah terverifikasi benar.

## Sumber

- When Agents Do Not Stop: Uncovering Infinite Agentic Loops in LLM Agents — https://arxiv.org/pdf/2607.01641
- agent-loop-guard — https://github.com/shu0819-sjy/agent-loop-guard
- Stop AI agents looping on the same failed tool call — https://particula.tech/blog/stop-ai-agents-looping-same-tool-call-no-progress
- Fin-RATE: financial analytics benchmark for LLMs — https://arxiv.org/pdf/2602.07294
- Flowco: data analysis with LLMs (runtime assertions) — https://arxiv.org/pdf/2504.14038
- Unit-aware arithmetic with Pint — https://xarray.dev/blog/introducing-pint-xarray
- NUMCoT: numerals and units in CoT — https://arxiv.org/pdf/2406.02864
- AbstentionBench — https://openreview.net/pdf?id=OkHC30LLpO
- Hallucination detection for text-to-SQL — https://arxiv.org/html/2512.22250v1
- Chain-of-Thought reasoning in the wild is not always faithful — https://www.alphaxiv.org/abs/2503.08679
- TA-Lib auto warm-up / unstable period — https://github.com/TA-Lib/ta-lib/issues/492 ; RMA — https://ta-lib.org/functions/rma.html
- pandas missing data — https://pandas.pydata.org/docs/user_guide/missing_data.html
- Bank BUMN (Kompas) — https://money.kompas.com/read/2023/03/03/114209126/bank-bumn-apa-saja-ini-daftar-lengkapnya?page=all
- Bank Central Asia (Wikipedia) — https://en.wikipedia.org/wiki/Bank_Central_Asia ; kepemilikan Hartono (Kontan) — https://insight.kontan.co.id/news/bbca-bagi-bagi-dividen-duo-hartono-pemilik-djarum-kebagian-jatah-rp-585-triliun
- RouteLLM — https://www.lmsys.org/blog/2024-07-01-routellm/
- OpenRouter provider routing — https://openrouter.ai/docs/guides/routing/provider-selection

## Lampiran: benchmark router "meminta uji" (2026-10-04)

**Data:** 61 pesan unik dari semua suite golden test, label manual. Diuji pada 2 model × 2 versi × 3 ulangan (732
panggilan, USD 0,10).

| Model | Versi | Akurasi | Riset tanpa diminta | Uji terlewat |
|---|---|---|---|---|
| DeepSeek v4.1 flash | sekarang | 58,5% | 71/90 | 5/93 |
| DeepSeek v4.1 flash | `asks_test` | 93,4% | 12/89 | 0/93 |
| MiMo v2.6 flash | sekarang | 59,6% | 69/90 | 5/93 |
| MiMo v2.6 flash | `asks_test` | 94,0% | 11/90 | 0/92 |

**Catatan:** "riset tanpa diminta" pada versi sekarang adalah **perilaku yang disengaja** di mode 4 (tujuan 1: setiap
pertanyaan analisis baru dibawa ke riset). Usulan S6 ditarik. Data ini disimpan bila mode bawaan suatu saat diubah.

## Lampiran S7: router saat usulan riset menunggu (2026-10-04)

**Set uji:** 34 pesan, dikirim saat ada usulan riset menunggu dan belum ada hasil baru setelah usulan itu (kondisi g7.3).
- **18 pesan nyata** dari suite dan log golden test (g5, g6, g7, g9, g11, m01, m02).
- **16 varian** dengan kelas yang sama:
  - pertanyaan atau permintaan baru yang menyebut perubahan periode, kelompok atau ambang;
  - revisi, persetujuan dan pembatalan usulan yang sah.
- **Label:** SUGGESTION (setuju, revisi atau batal atas usulan) atau OTHER (pertanyaan atau permintaan).
- **Pengulangan:** 2 model × 3 ulangan, router dengan instruksi produksi. Biaya ± USD 0,07 untuk tiga putaran.

| Model | Varian | OTHER dibaca sebagai usulan | SUGGESTION dikenali |
|---|---|---|---|
| DeepSeek v4.1 flash | sekarang | 16/60 | 42/42 |
| DeepSeek v4.1 flash | aturan backend di rencana (referent wajib) | 16/60 | 42/42 |
| DeepSeek v4.1 flash | **instruksi: "tentang usulan" = menyebut usulan / menjawab pertanyaan konfirmasinya** | **4/60** | **42/42** |
| DeepSeek v4.1 flash | instruksi + "analisis dengan syarat sendiri bukan APPROVE" | 2/60 | 42/42 |
| MiMo v2.6 flash | sekarang | 14/60 | 37/42 |
| MiMo v2.6 flash | aturan backend di rencana | 14/60 | 37/42 |
| MiMo v2.6 flash | **instruksi (dipakai)** | **8/60** | **41/42** |
| MiMo v2.6 flash | instruksi + kalimat kedua | 7/60 | 38/42 |

**Temuan:**
- Aturan backend di rencana tidak mengubah apa pun. Setiap salah baca juga diberi `referent = PENDING_SUGGESTION`; referent adalah
  penilaian yang sama, bukan pemeriksaan terpisah.
- Yang diterapkan: definisi "pesan tentang usulan" di instruksi router. g7.3 benar di semua ulangan.
- **Sisa (MiMo):**
  - "Coba event study: …" dibaca sebagai setuju (3/3);
  - "pakai data 5 tahun terakhir untuk ranking tadi" dibaca sebagai revisi (3/3).
- **Dampak sisa:** usulan tetap menunggu (aturan 4), sehingga user bisa mengulang.

## Lampiran S4b: benchmark pencari fakta web ringan (2026-10-04, `fact-bench-20261004a`)

20 fakta dengan jawaban yang diketahui, 4 paralel, lewat `web-governor-test-runner` (`09496358`). Setelah 9 fakta,
kunci OpenRouter mencapai batas USD 25 (R30), sehingga semua panggilan berikutnya gagal seketika.

| Fakta | Status | Nilai | Benar? | Detik |
|---|---|---|---|---|
| BBRI status | CONFIRMED | BUMN | Ya | 13,7 |
| BMRI status | CONFIRMED | BUMN (milik negara) | Ya | 8,1 |
| BBNI status | PARTIAL (1 situs) | BUMN (milik negara) | Ya | 9,3 |
| BBTN status | CONFIRMED | BUMN (milik negara) | Ya | 10,0 |
| BBCA status | CONFIRMED | swasta | Ya | 12,4 |
| BRIS status | CONFIRMED | BUMN | Kurang tepat: anak usaha BUMN | 11,5 |
| BNGA status | CONFIRMED | swasta | Ya | 10,6 |
| BDMN status | CONFIRMED | swasta | Ya | 6,4 |
| PNBN status | NOT_FOUND (ekstraksi gagal: batas kunci) | — | Tidak diuji | 5,2 |
| 11 fakta lain (pengendali, LQ45, tahun IPO) | NOT_FOUND (pencarian gagal: batas kunci) | — | Tidak diuji | 0,1 |
| 3 ulangan (cache) | sama dengan pertama (bila tersimpan) | — | — | < 0,1 |

**Temuan:**
- 8 dari 8 fakta yang terjawab sejalan dengan jawaban yang diketahui; BRIS disederhanakan menjadi "BUMN".
- Biaya sekitar USD 0,015 per fakta, di atas perkiraan rencana (< 0,01).
- Waktu maksimal 13,7 detik, di bawah batas 30 detik.
- **Kelas temuan BRIS:** nilai yang benar sebagian (anak usaha vs induk) tidak bisa dibedakan dari cuplikan pendek.
  Bukan kesalahan kutipan; kutipan memang menyebut "BUMN".
- **Belum dinyalakan di orc** (`AI_ENABLE_WEB_FACT`): sisa benchmark menunggu batas kunci dinaikkan.
