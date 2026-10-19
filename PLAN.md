# Rencana induk: sudah disetujui user, belum dieksekusi

Dokumen ini memuat pekerjaan yang sudah disetujui user tetapi belum punya rencana eksekusi (keputusan user 2026-10-06:
"tidak ada format plan PLAN_YYYY-MM-DD, semua plan harus jadi 1 kecuali future plan"). Eksekusi yang sudah disetujui
ada di `EXEC.md`, satu bagian per eksekusi (keputusan user 2026-10-06: "EXEC itu harusnya jadi 1 file").

Aturan:
- **Isi dokumen ini:** pekerjaan yang sudah disetujui user tetapi belum punya rencana eksekusi. Begitu rencana
  eksekusinya disetujui, butirnya pindah ke `EXEC.md`.
- **Usulan dan keputusan yang masih terbuka** ada di `FUTURE_PLAN.md`.
- **Setiap butir tetap dijalankan hanya atas perintah user.** Persetujuan masuk rencana bukan perintah eksekusi.
- **Persetujuan dicatat di sini pada tugas yang sama**, beserta tanggal dan kata-kata user, termasuk persetujuan
  "secara umum" (pelajaran R34 di `ERRORS_AND_SOLUTIONS.md`). Detail yang masih terbuka ditulis sebagai pertanyaan di
  butirnya.
- **Butir yang selesai** dipindah keluar: statusnya ke `ERRORS_AND_SOLUTIONS.md` / changelog, lalu baris di sini
  dihapus.
- **Dokumen rencana bertanggal yang lama** (`PLAN_2026-10-05.md`, `PLAN_*_2026-10-04.md`, `ROUND_PLAN_2026-10-03*.md`,
  dan `*_PLAN.md` lain) adalah riwayat diskusi. Butir yang belum selesai dari dokumen itu sudah dipindah ke sini atau
  ke `FUTURE_PLAN.md` (audit 2026-10-06, bagian akhir).

Kode masalah (M, P, S, G, W, R, C, D) merujuk ke `ERRORS_AND_SOLUTIONS.md`.

## Ringkasan

| No | Butir | Disetujui | Status | Urutan usulan |
|---|---|---|---|---|
| 8 | Round 2026-10-03 Fase E: E1 hit rate (M69 tahap 2), E2 ambil sekali beri label (G19 lapis 2) | 2026-10-03 (round disetujui) | Belum; E2 menunggu keputusan 6 | 8 |
| 9 | C06 1a-permanen dan D06 peringatan Telegram | 2026-10-02 | Belum (sisanya sudah live) | 9 |
| 10 | G2-B, S20, minimal 4 hipotesis, analisis faktor | 2026-10-02 (`G2_G3_REACTIVATION_PLAN.md` langkah 8, FINAL) | Belum; 4 keputusan rinci masih terbuka | 10 |
| 12 | Prosedur tabel baru (FX, indeks, makro) | 2026-10-01 "record now, run later" | Menunggu pemicu: tabel baru | Saat ada tabel baru |
| 13 | Feature04 otomatis setelah update harga, retry ticker/indikator gagal lewat Telegram | 2026-10-11 (implementation plan disetujui) | Selesai; dipindahkan ke `EXEC.md` EXEC-F04 | Selesai 2026-10-11 |
| 15 | Finality equity, pemeriksaan koreksi lima sesi, dan Feature04 incremental dengan checkpoint state | 2026-10-12 ("Ok jalankan.") | Selesai; migration, 868-instrument shadow, 6.076 checkpoint, live five-session run dan zero-change repeat lulus | Selesai 2026-10-12 |

Eksekusi yang sudah disetujui (dulu butir 1–7 dan 1b–1k) ada di `EXEC.md`.

---

## 8. Round 2026-10-03 Fase E

**Asal:** `ROUND_PLAN_2026-10-03.md` §1, §4 Fase E, §9 (round disetujui 2026-10-03). Fase A–D sudah live; Fase E
belum dikerjakan.

- **E1. M69 tahap 2: hit rate di riset multi-sudut.**
  - research_plan/v2 memuat `success_rule {operator, value, unit}` di hipotesis akar.
  - `conditional_distribution` dan `threshold_sensitivity` menghitung porsi kejadian yang memenuhi aturan dan
    selisihnya terhadap pembanding (interval, p-value). Validator `research_validation.py` menghitung ulang.
  - REVISE menyimpan temuan lama `<id>@n`.
  - Library riset dan Tool_Catalog versi baru.

  Status M69: tahap 1 live; tahap 2 belum.
- **E2. G19 lapis 2: ambil sekali, beri label.**
  - Perencana menggabung pesanan per kelompok menjadi satu pesanan dengan kolom label kelompok.
  - Ciri kelompok yang belum menjadi kolom (contoh BUMN) didaftarkan lewat forward migration + Column_Catalog.
  - **Menunggu keputusan 6** (`FUTURE_PLAN.md` §3): nama, sumber data dan isi kolom ciri kelompok dikonfirmasi user
    sebelum dimuat (Part A).

## 9. C06 1a-permanen dan D06 peringatan Telegram

**Asal:** `UNDERADDRESSED_PLAN_CAT23.md` §7 butir 1 dan 3 (disetujui 2026-10-02); rincian di
`HIGH_ALERT_IMPLEMENTATION_PLAN.md` Langkah 1a dan 1c. Bagian 1a-TEMPORARY, 1b (rentang "LATEST") dan status
kesegaran sudah live.

- **1a-permanen:**
  - `coverage_job.py --datasets` dibuat;
  - `apps/idx-price-cron/price_update.py` menyegarkan cakupan `Price_Stock_Indonesia_IDX` setelah muat sukses;
  - feature-01-worker menyegarkan `Feature_01_Stock_Daily` saat antrean kosong (jeda ≥ 5 menit);
  - kegagalan hanya dicatat (`coverage_refresh_failed`), memakai kunci advisory `ai_data_coverage_job`;
  - job pagi tetap menjadi cadangan.
- **Telegram:**
  - `coverage_job.py` mengirim satu notifikasi per hari per sumber BASI ke `telegram-monitor`;
  - `telegram_monitor.py` menerima `source_table` `AI_data_coverage` dengan dedupe yang ada;
  - variabel berupa referensi Railway (hanya nama dicatat).
- **Catatan:** layanan pemuat dan telegram bersumber `main`, jadi deploy-nya dikonfirmasi user saat eksekusi.

## 10. G2-B, S20, minimal 4 hipotesis, analisis faktor

**Asal:** `G2_G3_REACTIVATION_PLAN.md` §8 langkah 8 (FINAL, disetujui 2026-10-02: "sesudahnya, sesuai hasil golden
test"); rincian di `FACTOR_EVENT_RESEARCH_PLAN.md` langkah 1–5.

- **S20:** fungsi lintas entitas di backend (prasyarat).
- **Return abnormal** dengan benchmark yang dideklarasikan.
- **Jalur di sekitar event:** AAR, CAAR, CAR beberapa jendela.
- **Minimal 4 hipotesis teruji.**
- **Analisis faktor** setelah langkah 1–4 terbukti.
- **Lingkup (user 2026-10-16):** "Yes, untuk minimal 4 hipotesis jalur standar": hanya jalur riset standar; jalur cepat
  (EXEC-IMPL-1017 insight v2) tidak mewajibkan hipotesis atau uji.
- **Keputusan yang masih terbuka** (`FACTOR_EVENT_RESEARCH_PLAN.md` §12, dijawab sebelum mulai): urutan langkah,
  `AI_RESEARCH_MIN_ANGLES=4`, perlakuan bila data < 4 angle, `AI_RESEARCH_MIN_FAMILIES`.
- **Status:** S20 OPEN, S22 PARTLY FIXED.

## 12. Prosedur tabel baru (FX, indeks, makro)

**Asal:** `NEW_TABLE_ONBOARDING_PLAN.md` (keputusan user 2026-10-01: "record now, run later").

Dijalankan saat tabel baru pertama dimuat, bersama Part A `ERRORS_AND_SOLUTIONS.md`. Tabel makro di database adalah
keputusan terpisah (`FUTURE_PLAN.md` §3).

**Rencana user 2026-10-09 (bukan perintah jalan):** "saya plan sehabis ini karena kuota weekly sudah habis tuk ingest habis2an data macro, fundamental, fx, cross market, commodities etc. kemudian feature.. ini adalah proses onboarding only. saya minta kamu cek, table onboarding plan MD apakah bisa solely cukup dijadikan dokumen onboarding table ini, yang mana pada akhirnya data2 ini juga bisa visible ke sisi AI?" Rencana diperiksa dan diperbarui hari yang sama (rantai visibilitas AI, butir 14–21, pertanyaan per kelas aset, tabel Feature, keadaan kode sekarang, daftar yang harus jadi sebelum tabel pertama dibuka ke AI). Usulan kode di dalamnya (ERRORS M136, M137) menunggu keputusan user.

---

## 14. Data tambahan ke sesi analisis yang sedang terbuka (ATTACH; desain disetujui untuk dirumuskan, belum "go")

**Dinyalakan di dev 2026-10-15** (user: "buka dan jalankan ya. Siapkan fallback apabila intended resultnya jelek"):
`AI_ENABLE_SESSION_ATTACH=true` di `market-ai-orc` dev (deploy `bb3738ea` SUCCESS, startup tanpa `session_attach_inactive`).
Temuan saat menyala: deteksi research findings v1 membaca nama kelas argumen, yang diganti pembungkus lampiran, sehingga
`hypothesis_plan_inactive` (ERRORS M165); diperbaiki di `5158381` (deteksi dari field), orc `fcda847e` SUCCESS tanpa `*_inactive`. Jalan balik: (1) otomatis per
pesan: lampiran yang ditolak sandbox membuka sesi baru dengan alasannya (perilaku lama); (2) seluruhnya: hapus
`AI_ENABLE_SESSION_ATTACH` di orc dev (`railway variables --service market-ai-orc --environment dev --remove
AI_ENABLE_SESSION_ATTACH` atau set `false`), orc redeploy dan alat `attach_data_bundle` tidak ditawarkan lagi. Tanda
"hasil jelek" yang dipantau di log orc: `mechanical_steps_merged` dengan `attach_data_bundle` ditolak berulang, penyelesaian
dengan lampiran INCOMPLETE, atau run dengan lampiran yang lebih lama dari run serupa tanpa lampiran. A/B berbayar belum
(saldo OpenRouter $0,42).

**Keputusan user 2026-10-15:** atas usulan di `FUTURE_PLAN.md`: "Ok untuk solusi. Also you should know bahwa yang live
sekarang adalah fastlane. Boleh dirumuskan designnya?" dan "Cara kerjanya: data tambahan tetap diminta lewat jalur biasa
(Governor, batas ukuran). Bedanya, paketnya dilampirkan ke sesi yang sedang terbuka. Variabel tetap ada, dan analisis
langsung dilanjutkan. --> ini sudah OK". Pertanyaan user tentang cek "kedua data dipakai" dan batas gabungan dijawab di
percakapan; desain di bawah sudah memuat jawabannya.

**Masalah (diperiksa di kode 2026-10-15):** satu sesi sandbox terikat pada satu paket data sejak dibuka
(`sessions.py` `_launch`: file paket di-link ke `input/`, daftar permintaan dikirim sekali ke proses sesi). Data
tambahan = data need baru, paket baru dan sesi baru (`open_analysis_session`); variabel dan tabel kerja sesi lama tidak
terbawa. A/B V5 j2: sesi kedua, muat ulang data dan tulis ulang kode, puluhan detik per kejadian. Kelas: setiap analisis
yang baru tahu kebutuhan datanya di tengah jalan (pengayaan, kolom yang terlewat, pembanding).

**Desain (jalur Cepat dulu; jalur Standar ANALYSIS memakai alat yang sama; jalur riset yang disetujui tidak berubah):**
1. AI di sesi S (data need N1) memutuskan butuh data tambahan (penilaian AI, kapan saja di tengah analisis).
2. AI mengirim data need N2 berisi hanya permintaan tambahan, dengan `attach_to_session: S`. N2 lewat jalur biasa:
   validator, Governor, batas ukuran, pakai ulang potongan dengan SQL sama (M134).
3. Paket N2 dilampirkan ke S (langkah mekanis, menggantikan pembukaan sesi): sandbox memeriksa S milik jawaban yang sama
   dan masih aktif, N2 punya tanggal referensi yang sama dengan N1, nama permintaan tidak bertabrakan, dan ukuran
   gabungan masih di bawah batas sesi; file N2 di-link ke `input/` S, proses sesi diberi tahu permintaan baru
   (operasi baru seperti `inspect`), `load('<permintaan baru>')` langsung bisa dipakai.
4. Variabel, tabel kerja (`save_table`) dan tabel yang sudah dibuat tetap ada; AI melanjutkan dengan `run_python`.
5. `complete_analysis`: cakupan diperiksa per data need seperti sekarang (data yang dipakai jawaban dibaca penuh). Data
   need lampiran yang tidak dibaca sama sekali **tidak menggagalkan** analisis: dicatat "tidak dipakai" dan tidak masuk
   catatan data jawaban (AI boleh memutuskan data itu ternyata tidak perlu).
6. Gagal melampirkan (sesi mati, batas ukuran, jalur riset) → jalan lama: buka sesi baru, dengan alasan dan sisa
   kapasitas di pesan.

**Jaminan yang tetap di kode:** data hanya lewat Governor; setiap angka bersumber; data yang dikutip dibaca penuh;
batas ukuran per sesi dihitung gabungan (melindungi memori dan disk mesin yang dipakai bersama, paling banyak 4 sesi);
batas jumlah lampiran per sesi (mencegah putaran tanpa ujung); jalur riset: data di luar rencana yang disetujui butuh
persetujuan user (EXEC-D).

**Kontrak dan dokumen:** kemampuan baru dilaporkan sandbox di `/v1/runtime` (orc memakainya hanya bila ada); argumen
`attach_to_session` di `submit_data_need_spec` → ronde `Tool_Catalog` dan `AI_TOOLS.md`; satu saklar orc untuk A/B dan
jalan balik (prinsip "harus selalu ada fallback" EXEC-FASTLANE).

**Tes dan ukuran:** lampiran berhasil (variabel tetap, `load` permintaan baru), nama bertabrakan, batas gabungan,
sesi milik jawaban lain ditolak, lampiran tidak dipakai tidak menggagalkan, data yang dipakai tetap diperiksa penuh;
A/B jalur Cepat dengan pertanyaan yang butuh data tambahan di tengah (pola j2): waktu, putaran, sesi per run.

**Keputusan user 2026-10-15:** atas penjelasan batas lampiran (2 per sesi; lampiran ke-3 ditolak dengan jalan ke data yang ada atau sesi baru) dan cara AI tahu (deskripsi alat `submit_data_need_spec` dan alat sesi, saran di pesan galat; kalimat system prompt hanya bila A/B menunjukkan AI belum memakainya): "Aight OK - masukan EXEC jangan execute dulu". Batas: 2 lampiran per sesi.

**Status 2026-10-15 (go "Ok jalankan", EXEC-IMPL-1015 Fase 4): dibangun, saklar mati.** Sandbox: route attach,
op worker `attach`, store v6 `sessions.attached`, penyelesaian per need (USED/INCOMPLETE/UNUSED), kapabilitas
`session_attach`, saran `missing_data_hint`. Orc: alat `attach_data_bundle`, argumen `attach_to_session_id`, langkah
mekanis dengan jalan balik ke sesi baru, saklar `AI_ENABLE_SESSION_ATTACH` (mati). Tool_Catalog ronde `round_u`,
AI_TOOLS.md. ERRORS M159. Sisa: A/B jalur Cepat pola j2 (berbayar, saldo OpenRouter saat ini $0,37) atas perintah user;
setelah A/B dan keputusan user butir ini dipindah ke selesai.

**Pertanyaan terbuka:** apakah A/B dulu dengan saklar mati di jalur Standar.

## Sudah dieksekusi, tinggal bukti live

Bukan rencana lagi; daftar dan statusnya ada di `OUTSTANDING_ISSUES.md` ("Sudah diperbaiki, hanya menunggu golden
test") dan `ERRORS_AND_SOLUTIONS.md`. Contoh: G19 lapis 1 dan 3, M69 tahap 1, M70, S28, S29 (R-STORE), C06 1b, S22.

## Audit dokumen rencana (2026-10-06)

| Dokumen | Hasil audit |
|---|---|
| `PLAN_2026-10-05.md` | Item 1–10 dan 12 dieksekusi (golden test 06b); sisa item 10/12 → EXEC-1; item 11 → EXEC-3 (`EXEC.md`) |
| `PLAN_FINAL_2026-10-04.md` | Fase 1–6 dieksekusi (golden test akhir dihentikan user di 23/32). Daftar "buntu" (P05/P08, G10, D06, M42) bukan butir yang disetujui |
| `PLAN_ROUND_2026-10-04.md`, `PLAN_EVIDENCE_GATE_2026-10-04.md` | Digantikan `PLAN_FINAL_2026-10-04.md` |
| `PLAN_BE_OPTIMIZATION_2026-10-04.md` | O2, O3, O4, P28-D live (label "belum dieksekusi" di judul O3 sudah basi); O1 tidak dikerjakan (keputusan user "as is") |
| `PLAN_ROUTER_MODELS_2026-10-04.md` | Dieksekusi (router, `AI_MODELS.md`, M80 a/b, uji R-STORE); P30 ditunda user → `FUTURE_PLAN.md` |
| `ROADMAP_FRONTEND_2026-10-04.md` | Usulan → `FUTURE_PLAN.md` |
| `ROUND_PLAN_2026-10-03.md` (+ Fase C, D) | Fase A–D live; Fase E → butir 8 |
| `G2_G3_REACTIVATION_PLAN.md`, `MODE4_CONVERSATION_PLAN.md` | Dieksekusi (judul masih "belum dijalankan", basi); langkah 8 → butir 10 |
| `FACTOR_EVENT_RESEARCH_PLAN.md` | Rincian butir 10 |
| `HIGH_ALERT_PLAN.md`, `HIGH_ALERT_IMPLEMENTATION_PLAN.md` | H1, H2, H5, Prioritas 2 dieksekusi; 1a-permanen dan Telegram → butir 9; H3 kamus istilah menunggu daftar istilah user → `FUTURE_PLAN.md` |
| `UNDERADDRESSED_PLAN_CAT23.md` | Kelompok 2–5, 7 (sebagian) dieksekusi; §7 sisa → butir 9; kelompok 1, 6, 8 → `FUTURE_PLAN.md` |
| `VALUE_DICTIONARY_PLAN.md` | → butir 11 |
| `NEW_TABLE_ONBOARDING_PLAN.md` | → butir 12 |
| `WAREHOUSE_AGGREGATION_PLAN.md` | Fase 1 dan 2 dieksekusi (fase 2 = D5 `query_metric`) |
| `EXTRACTION_AND_AUDIT_PLAN.md` | Bagian yang disetujui dieksekusi; "Proposed, not approved yet" → `FUTURE_PLAN.md` |
| `ANSWER_INTEGRITY_FIX_PLAN.md`, `MULTI_ANGLE_FIX_PLAN.md` | Dieksekusi; topik desain multi-angle yang belum disetujui → `FUTURE_PLAN.md` |
| `WEB_GOVERNOR_PLAN.md` | P1–P8 diimplementasikan; golden set dan antrean tinjauan manusia P4 → `FUTURE_PLAN.md` |
| `AI_ANALYST_IMPLEMENTATION_PLAN.md` (2026-09-13), `FEATURE_01_AUTOMATION_PLAN.md` | Dasar arsitektur lama / sudah aktif; tidak ada butir disetujui yang tertunda |
| `FUTURE_PLAN.md` | Tetap terpisah; §1 sudah dieksekusi di round 2026-10-03 |

## 13. Feature04 otomatis setelah update harga — selesai

Implementasi, deployment, canary, dan bukti final telah dipindahkan ke `EXEC.md` EXEC-F04
serta `verification/feature04/AUTOMATION.md`. Isi berikut dipertahankan sebagai riwayat
keputusan desain yang menghasilkan eksekusi tersebut.


Permintaan user: "cek bagaimana data price diupdate dan bagaimana trigger monitoing ke telegram terjadi ...
design job ketika harga update then indikator juga auto calculate fir eligible ticker ... design dulu baru confirm".
**Persetujuan desain secara umum, 2026-10-11:** user:

> Ok, monitoring update ke telegram setelah:
> 1. update ke telegram price selesai
> 2. feature 4 fully calculated?

Urutan notifikasi dicatat di bawah. Ini persetujuan rencana; belum ada perintah implementasi/deployment. Pemeriksaan menggunakan SELECT melalui role `pgweb`
dengan `transaction_read_only=on`, pembacaan kode, dan Railway describe; tidak menjalankan price job atau mengirim Telegram.
Bukti: `verification/feature04/automation_design_inspection.json` dan `automation_design_railway.json` dalam direktori yang sama.

**Tambahan scope, 2026-10-11:** user: "buat opsi di telegram, untuk re calculate hanya untuk yang gagal, baik ticker level /
column indicstor level. then inspect database, buat implementation plan. ada yg ambigu?".
Implementation plan di bawah mencakup otomatisasi dan menu retry. Permintaan ini diperlakukan sebagai penyusunan rencana;
kode runtime, migration, service dan pengiriman Telegram belum diubah.

**Keputusan dua ambiguitas, 2026-10-11:** user: "both ya" untuk (1) definisi gagal sebagai error kalkulasi/validasi,
termasuk NULL yang terbukti salah, dengan NULL sah dikecualikan; dan (2) retry kolom wajib mencakup dependency terkait,
dengan cakupan ditampilkan sebelum dijalankan. Kedua keputusan ditetapkan; belum merupakan perintah go implementasi/deployment.

**Klarifikasi failure per ticker, 2026-10-11:** user: "jika scriptnya failure saja untuk that ticker. possible?".
Failure boundary worker berada pada satu ticker: exception script saat memproses BBCA dicatat sebagai failure BBCA,
worker melanjutkan ticker lain, dan menu retry hanya mengambil ticker yang gagal. Exception script yang belum mempunyai
diagnosis per indikator memakai retry full-ticker; tidak menebak kolom gagal dari NULL atau menandai semua ticker gagal.
Contoh: BBCA FAILED, BBRI SUCCESS, BMRI SUCCESS -> ulang script untuk BBCA saja, dengan full available BBCA history;
BBRI/BMRI tidak masuk request tersebut. CLI backfill lama yang berhenti pada failure pertama tidak menjadi entrypoint worker.

**Persetujuan implementation plan, 2026-10-11:** user: "Ok agree, baagimana service telegram monitor dan telegram trigger dipakai".
Persetujuan ini menetapkan desain dan pembagian service di bawah; belum merupakan perintah untuk membuat migration,
service Railway, deployment, menjalankan price job, atau mengirim pesan Telegram live.

### Kondisi yang diverifikasi

- Railway `lucid-patience` / `dev`, database utama `Postgres`; service price, Feature01 dan Telegram memakai `rednightt33/saniti@main`.
- DAILY `idx-price-cron`: `python price_update.py --mode daily`, cron `0 10 * * *` UTC = 17:00 WIB.
  Scope seluruh `IDX_Stock_Universe`, saat diperiksa 844 ticker `IDX` / `stock`. Hanya candle bertanggal target diterima.
- RECOVERY `idx-price-recovery-cron`: `python price_update.py --mode recovery`, cron `0 23 * * *` UTC = 06:00 WIB
  hari berikutnya. Mengambil hanya ticker yang masih missing untuk hari kerja sebelumnya; weekend menargetkan Jumat.
- `bulk_upsert_prices()` menulis harga `(ticker,date)` dan `ingestion_time=statement_timestamp()`;
  pengulangan dengan OHLCV sama tetap memperbarui timestamp. Harga dan `Monitoring_Price_ALL` commit bersama.
  Shared advisory lock mencegah dua price run menulis bersamaan. Weekend DAILY dicatat SKIPPED.
- Sesudah commit, `commit_monitoring_and_notify()` POST `{source_table: Monitoring_Price_ALL, execution_id}`
  ke private `/notify`, autentikasi `X-Notify-Secret`; default empat percobaan, timeout 20 detik.
  `telegram-monitor` membaca monitoring, mengirim pesan, lalu mencatat `Telegram_Notification_Log`.
  Dedup key `(source_table,source_execution_id,notification_type)`; SENT dilewati, SENDING segar dianggap in-progress.
  Service tidur saat idle, tidak mempunyai cron/polling DB. Kegagalan Telegram tidak membatalkan harga.
- `/run_price` dan `/run_recovery` masuk melalui `telegram-trigger`: webhook secret + owner Chat ID,
  dedup Telegram update ID + cooldown, lalu Railway Run Now. Acknowledgement awal berbeda dari hasil akhir monitor.
- Pada 9 Oktober DAILY memperbarui 827/844 ticker, missing 17; pesan hasil SENT.
  RECOVERY terbaru 11 Oktober WIB menargetkan 9 Oktober, mendapat 0 dari 17, NEEDS_REVIEW; pesan juga SENT.
- Trigger harga yang aktif hanya enqueue Feature01 dan pencatatan status tabel. Feature01 mempunyai 14.907 queue item DONE,
  841 ticker status SUCCESS. Queue/status tersebut memiliki CHECK khusus `Feature_01_Stock_Daily`.
  Feature04 belum mempunyai trigger/worker otomatis; harga dan Feature04 saat pemeriksaan sama-sama 1.318.633 baris,
  844 ticker, tanggal maksimum 2026-10-09. Kelengkapan sekarang berasal dari backfill manual.
- Rujukan kode: `apps/idx-price-cron/price_update.py`, `apps/telegram-monitor/telegram_monitor.py`,
  `apps/telegram-trigger/telegram_trigger.py`, `apps/feature-01-worker/worker.py`, dan migration `20260913_004`, `20260913_006`.

### Rekomendasi alur dan eligibility

```text
TradingView -> price UPSERT + Feature04 enqueue + membership batch + monitoring (satu commit)
                    |                              |
                    |                              +-> pesan hasil harga yang sudah ada
                    v
             feature-04-worker -> replay per ticker -> Feature04 + audit (commit atomik)
                    |
                    +-> batch selesai -> notification outbox -> telegram-monitor -> pesan hasil indikator
```

Default usulan eligibility: semua ticker sumber yang mempunyai candle `Daily` valid dan baru masuk/berubah,
termasuk ticker baru; tidak mensyaratkan 200 bar, volume positif, ADX tertentu, atau breakout.
History pendek tetap dihitung; NULL warmup EMA200/ADX/SMI tetap mengikuti definisi masing-masing kolom.
Ticker tanpa candle target tidak dibuatkan candle/indikator palsu dan dihitung sebagai missing price, terpisah dari failed calculation.
Eligibility tersebut tetap default desain; user belum memberikan jawaban khusus mengenai filter universe/daftar pilihan.
Re-ingestion identik ketika output masih current tidak memicu kalkulasi; input relevant adalah tanggal, ticker,
timeframe dan OHLCV. Pergantian company_name/query_date/ingestion_time saja bukan perubahan rumus.
Jika output belum current atau versi kalkulasi berbeda, re-ingestion identik tetap dapat menjadwalkan perbaikan.

### Queue, worker dan jaminan konsistensi

1. Buat trigger enqueue Feature04 yang ringan pada perubahan harga relevan. Berbeda dari Feature01,
   enqueue tidak bergantung pada `ingestion_time` non-NULL: koreksi history dengan timestamp lama/NULL tetap tertangkap.
   Perubahan valid menjadi invalid juga harus enqueue: engine menulis NULL dan mereset state sesuai kontraknya,
   kemudian monitoring NEEDS_REVIEW; tidak boleh diam-diam mempertahankan indikator lama.
   Jika identitas ticker/date/timeframe berubah, tandai kelompok lama dan baru serta hapus target key yang ditinggalkan
   dalam penyelesaian worker. DELETE candle juga menjadwalkan kelompok lama; TRUNCATE di luar flow ini perlu rekonsiliasi eksplisit.
2. Gunakan queue khusus Feature04, satu row `(ticker,timeframe)`, menggabungkan beberapa perubahan dalam ticker.
   Simpan `dirty_from_date` paling awal, `requested_generation`, `completed_generation`, `calculation_version`,
   state PENDING/PROCESSING/DONE/FAILED, claim token/lease, retry dan error. Generation naik monotonik pada perubahan input;
   jangan memakai `max(date)` atau timestamp ingestion sebagai satu-satunya freshness marker.
   Queue baru tidak memakai FK ke satu candle agar koreksi/DELETE bisa diproses.
3. Worker Railway baru `feature-04-worker`, satu replica, proses ticker serial, polling idle 5 detik; tanpa cron dan TradingView.
   Claim pendek dengan `FOR UPDATE SKIP LOCKED`, lease 10 menit; lima percobaan per generation dengan exponential backoff
   mulai 30 detik, cap 30 menit. Retry ticker gagal tidak menghalangi ticker lain. Lease kedaluwarsa dapat direclaim.
4. Baca snapshot konsisten seluruh history ticker, tanggal paling lama sampai terbaru, dengan pinned engine v3
   `features/feature04/engine.py` dan `swing.py`. Jangan membatasi ke 200 atau 120 bar: EMA, ADX dan SMI/swing rekursif;
   koreksi lama bisa memengaruhi seluruh tanggal berikutnya. Full replay juga menjaga indeks `temp_*_bar`.
   Stage pertama mempertahankan batas aman 5.000 observasi/ticker; yang melebihi batas FAILED dengan alasan, bukan dipotong.
   Jika DELETE mengosongkan seluruh history, worker membersihkan target ticker dan mencatat SOURCE_EMPTY; tidak memanggil replay kosong.
5. Hitung dari snapshot tanpa menahan queue row lock selama CPU work. Snapshot harus membaca generation yang sesuai claim.
   Di transaksi final yang pendek, ambil existing Feature04 advisory lock dan queue row lock, periksa claim token,
   generation dan versi lagi. Jika sudah berubah, buang hasil lama sebagai SUPERSEDED dan proses ulang generation terbaru.
   Price update yang belum commit tetap akan membuka pekerjaan baru setelahnya. Tidak ada stale completion yang menutup perubahan baru.
6. Upsert suffix dari `dirty_from_date` sampai tanggal terbaru, reconcile key yang hilang/berubah, validasi seluruh payload
   yang ditulis, lalu commit output + completion generation + attempt SUCCESS bersama. Payload identik mempertahankan
   `calculated_at`. NULL yang sah bukan failed calculation. Source hash memakai input rumus, bukan ingestion metadata.
   Snapshot lama atau error fatal membatalkan transaksi. Sesuai tambahan retry indikator, error per kelompok formula dapat
   diisolasi: hanya kelompok yang selesai dan tervalidasi boleh commit, bersama status/audit per kolom; kelompok gagal tidak
   menulis output. Ticker dengan kelompok gagal tetap PARTIAL/FAILED, tidak DONE. Detail freshness parsial ada di implementation plan.
7. Freshness dinilai dari generation dan versi engine yang sesuai untuk **seluruh 50 kolom fitur**, bukan tanggal maksimum saja.
   `completed_generation=requested_generation` pada ticker hanya valid setelah semua kolom mencapai SUCCESS, termasuk NULL sah.
   Formula tetap v3, 55 kolom yang ada, termasuk `break_swing_high` INTEGER 1/0 pada bar valid.

### Batch monitoring dan Telegram

Untuk setiap price execution, price writer memasang transaction-local execution ID sebelum UPSERT dan membuat run
Feature04 OPEN di transaksi yang sama. Trigger mencatat membership ticker beserta required generation; setelah UPSERT,
writer menyegel run READY, atau SKIPPED bila tidak ada candle yang berhasil ditulis. Worker hanya membaca run committed/sealed.
Koreksi SQL tanpa execution ID tetap otomatis masuk queue; audit mencatat origin ADHOC, kegagalan terminal mempunyai alert
dedup per ticker/generation. Tidak membuat batch Telegram per satu candle history.

Worker memperbarui hasil member dari generation yang benar-benar selesai. Generation lebih baru yang selesai dapat
memenuhi member lama, dengan label bahwa hasil memakai source terbaru. Jangan mengklaim rekonstruksi snapshot historis
execution lama. Run final ketika semua member mencapai hasil terminal: SUCCESS, PARTIAL, NEEDS_REVIEW, FAILED atau SKIPPED;
pisahkan status kalkulasi dari status PARTIAL/NEEDS_REVIEW price run. Bedakan validasi output berhasil dari freshness current.
Batch yang macet melewati 30 menit mendapat satu alert keterlambatan; hasil akhir nanti tetap dikirim.

Usulan tujuh tabel baru setelah tambahan retry kolom (semua nama belum dibuat):

| Objek | Grain / fungsi |
|---|---|
| `Feature04_Calculation_Queue` | Satu row per ticker/timeframe; work coalescing dan status freshness. |
| `Feature04_Calculation_Log` | Satu completed attempt; SUCCESS/PARTIAL/FAILED/SUPERSEDED, generation, scope kolom, outcomes per kelompok, source/output hash, durasi dan changed rows. |
| `Monitoring_Feature04` | Satu run per source execution; price scope, updated/missing, calculation scope, counts, status dan waktu. |
| `Monitoring_Feature04_Ticker` | Satu ticker/timeframe per run; required generation, requested columns, outcome dan error. |
| `Feature04_Notification_Outbox` | Satu event per run/type, atau ADHOC ticker/generation/error; payload reference, lease, next retry dan delivery state. |
| `Feature04_Column_Status` | Satu ticker/timeframe/feature column; source generation, calculation version, readiness/error dan legitimate NULL evidence. |
| `Feature04_Retry_Request` | Satu owner request/preview token; selected failure scope, parent run, dedup identity, lifecycle dan child retry run. |

Commit run terminal + outbox event atomik; dispatcher dalam worker mengirim hanya referensi run/event ke notifier.
Perlu memperluas allowlist/formatter `telegram-monitor` karena sekarang hanya menerima `Monitoring_Price_ALL`.
Pesan harga tetap segera dikirim; pesan indikator menyusul satu ringkasan per batch yang berisi tanggal, berhasil/eligible,
failed/missing-price, durasi dan ticker bermasalah. Contoh hipotetis: "Feature04 DAILY — 827/827 calculated; price missing 17".

**Urutan delivery sesuai pertanyaan user:** pesan hasil price lebih dahulu, pesan hasil Feature04 sesudahnya.
Pesan Feature04 SUCCESS hanya boleh dilepas ketika kedua kondisi benar: (1) notification price untuk execution yang sama
tercatat SENT dengan Telegram message ID (bukan sekadar HTTP accepted/in_progress atau SENT tanpa pesan karena suppression),
(2) seluruh member eligible telah dihitung, divalidasi dan outputnya committed untuk generation/version yang dipersyaratkan.
Kalkulasi boleh berjalan segera setelah price commit, paralel dengan pengiriman Telegram price; hanya delivery ringkasan
Feature04 yang menunggu kedua kondisi. Jika Feature04 selesai lebih dahulu, outbox menunggu price delivery.
Bila price notify gagal, dispatcher melakukan retry delivery price dengan execution ID dan dedup yang sama; pekerjaan
kalkulasi tetap berjalan. Pending delivery bertahan di outbox dan dapat direplay, tanpa mengulang price fetch.
Jika ada ticker gagal atau antrean tertahan, laporan PARTIAL/FAILED/NEEDS_REVIEW atau keterlambatan tetap diperbolehkan
setelah price delivery, tetapi tidak boleh mengatakan fully calculated/SUCCESS. Fully calculated mencakup ticker
eligible yang mempunyai candle; missing price tidak menjadi denominator kalkulasi dan tetap ditampilkan terpisah.
Batch SKIPPED tanpa input baru tidak menambah pesan indikator. Ini monitoring kalkulasi; alert trading breakout merupakan scope terpisah.
Outbox bertahan jika worker/notifier mati dan dapat retry setelah restart; POST 202/in_progress bukan bukti delivery SENT.
Dispatcher memastikan status SENT melalui log delivery sebelum menutup outbox, menggunakan acknowledgement/status read internal.
Untuk FAILED Telegram retry dibatasi dengan backoff, lalu disimpan untuk replay operator, tanpa mengulang TradingView/kalkulasi.
Dedup menahan pengiriman normal berulang; timeout setelah Telegram menerima tetapi sebelum log commit masih bisa menghasilkan
duplikasi. Tidak menjanjikan exactly-once delivery ke API Telegram.

### Biaya, rollout, acceptance dan rollback (menunggu perintah eksekusi)

- Full v3 backfill 844 ticker sebelumnya memerlukan sekitar 344 detik. Ini baseline serial dengan banyak write/verification,
  bukan SLA daily; daily tetap replay history tetapi biasanya menulis satu candle baru per ticker. Ukur compute/DB/latency
  untuk BBCA dahulu. Tambahan biaya satu worker selalu aktif dan polling; jumlah perubahan ticker menentukan work, bukan 844 scan jobs tiap poll.
- Runtime baru membungkus pure engine, tidak langsung menjalankan CLI backfill/manual dengan run ID lama. Docker build perlu
  memasukkan shared `features/feature04` dan pinned dependencies; root build repo dengan Dockerfile khusus worker,
  watch paths worker + shared engine, supaya perubahan engine benar-benar deploy. Price/Telegram watch paths tetap scoped.
- Forward migration + semua catalog/schema docs, least-privilege worker role (SELECT harga, write Feature04/control saja),
  atomic enqueue routines dengan privilege terukur, index queue/member/outbox berdasarkan query plans yang diukur.
- Pasang trigger + durably capture perubahan sebelum worker aktivasi. Bootstrap queue untuk seluruh source ticker dan
  hitung/validasi sebagai baseline; jangan mengasumsikan current dari equal max date/count atau mengisi ingestion timestamp lama.
  Simpan activation generation/version; perubahan selama bootstrap tidak boleh hilang. Canary BBCA dahulu, lalu seluruh eligible ticker.
- Acceptance: insert candle baru; correction lama mengubah downstream sesuai full engine; identical re-ingestion no-op;
  history pendek dengan NULL sah; zero-volume valid; invalid input reset; ticker baru; perubahan ketika worker sedang menghitung;
  source rollback tanpa queue; lease/restart/retry; writer manual lock; identity/DELETE; partial price run; notifier outage
  dan duplicate/in-progress requests. Canary tidak membutuhkan TradingView query atau Telegram send tanpa otorisasi tahap eksekusi.
- Rekonsiliasi startup dan berkala (usulan 1x/hari dalam worker) memeriksa source input fingerprints, missing target keys,
  versi, stuck generations dan notification outbox; enqueue hanya drift. Biaya full fingerprint scan harus diukur, bukan
  mengandalkan freshness per max date yang tidak menangkap koreksi lama.
- Rollback operasional: pause worker/dispatcher, pertahankan price cron dan queue capture agar pending work tidak hilang;
  kembalikan deployment notifier/price integration bila perlu. Tidak drop output/control/history; perbaiki lalu replay antrean.

Desain secara umum dicatat disetujui; urutan price Telegram SENT kemudian hasil Feature04 ditetapkan.
Detail terbuka: filter eligibility bila berbeda dari default. Implementasi/deployment menunggu perintah eksekusi user.

### Implementation plan: otomatisasi + retry gagal di Telegram (disetujui 2026-10-11)

#### Hasil inspeksi tambahan, read-only

Bukti baru: `verification/feature04/retry_design_inspection.json` dan `retry_design_railway.json`.

- Feature04: 55 kolom fisik = 3 identity + 50 feature outputs + 2 metadata. Seluruh 1.318.633 baris / 844 ticker memakai v3;
  v3 backfill log mempunyai 844 COMPLETED, tidak mempunyai FAILED. Ini keberhasilan backfill yang tercatat, bukan bukti bahwa
  setiap kolom sudah mempunyai status operasional individual; status tersebut belum ada.
- Ketujuh objek kontrol Feature04 usulan belum ada. Engine `calculate()` monolitik: error satu call dapat menghentikan ticker.
  Log lama bergrain run/ticker, bukan column; tidak bisa menyimpulkan kegagalan kolom dari NULL.
- Latest bar per ticker: tidak ada missing Feature row. EMA200 NULL pada 11 ticker dengan 62–189 bar (<200).
  SMI latest tersedia untuk semua ticker; 1.048 historical NULL adalah leading zero-range yang sebelumnya divalidasi.
  Latest `temp_high` NULL 771 ticker, `temp_low` NULL 490, `last_swing_high` NULL 5; ketidaktersediaan state ini mengikuti
  formula, bukan daftar retry. Pola candlestick nol dan breakout nol juga hasil sah.
- `Telegram_Command_Log` baru menyimpan RUN_PRICE/RUN_RECOVERY; satu FAILED RUN_RECOVERY lama adalah kegagalan command
  Railway, **bukan** kegagalan Feature04. Bot menu sekarang hanya dua price controls. Retry Feature04 tidak boleh menjalankan keduanya.
- PK target `(ticker,trade_date,timeframe)` dan source `(ticker,date)` sudah mendukung akses ticker. Read BBCA 2.113 observasi
  memakai bitmap scan PK + in-memory sort, execution 2,198 ms pada pemeriksaan ini; tidak perlu index harga spekulatif.
  Index kontrol baru tetap perlu EXPLAIN setelah fixture/rehearsal, sebelum deploy.

#### Definisi gagal, scope dan perilaku menu

Definisi disetujui user (2026-10-11, "both ya"): retry hanya error kalkulasi/validasi yang terstruktur, termasuk NULL yang terbukti
unexpected berdasarkan aturan availability. NULL warmup, zero-range SMI, inactive tracking dan pre-confirmation swing
bukan failure. SOURCE_INVALID ditampilkan "Perlu perbaikan data harga"; tombol recalculation tidak akan memperbaiki source.
NULL yang sah tidak masuk daftar retry. Dependency closure untuk indikator yang saling terkait juga sudah disetujui.

Menu `/feature4`, label untuk pengguna:

```text
Feature 4
  [Lihat status]
  [Ulang ticker gagal]
  [Ulang indikator gagal]

Ulang ticker gagal
  Pilih batch bermasalah (default batch terbaru yang masih punya failure aktif)
  Pilih [Semua ticker gagal di batch ini] atau satu ticker
  Ringkasan pilihan -> [Jalankan] [Batal]

Ulang indikator gagal
  Pilih batch -> ticker -> hanya indikator yang statusnya gagal
  Pilih [Semua indikator gagal] atau satu indikator/kelompok terkait
  Ringkasan pilihan, termasuk indikator terkait yang harus ikut -> [Jalankan] [Batal]
```

- Daftar paginated; tampilkan hanya failure yang masih berlaku, bukan kegagalan lama yang sudah pulih. Batch/ticker boleh
  dipilih; tidak otomatis mencakup seluruh sejarah atau seluruh market. Retry ticker menghitung seluruh feature untuk
  ticker yang dipilih; ticker sukses lain tidak disentuh. Retry indikator memperbarui hanya scope kolom gagal + dependency closure.
- Preview dibuat read-only dengan token opaque server-side, TTL 15 menit, terikat owner Chat ID, batch, ticker,
  error attempt, source generation dan versi. Telegram callback membawa ID/action pendek (<64 bytes), bukan nama SQL.
  `Jalankan` transaksi atomik: dedup telegram_update_id/request token, cek failure/generation saat ini, lalu enqueue dan audit.
  Duplicate click mengembalikan request yang sama; request aktif dengan scope yang sama tidak membuka job ganda.
- Jika sudah pulih: "Sudah selesai, tidak perlu diulang". Jika source/failed scope berubah sejak preview: tunjukkan status
  terbaru dan minta pilih ulang; jangan diam-diam memperluas scope. Bila tidak ada failure: "Tidak ada kalkulasi gagal".
  PENDING/PROCESSING tidak dianggap failure; expired lease dipulihkan worker, bukan double claim dari tombol.
- Auto retry lima attempt/generation tetap berjalan. Manual retry yang valid membuka retry cycle baru dengan cap lima
  attempt, menjaga lifetime attempt monotonik dan audit lama. Cooldown/dedup berdasarkan scope, bukan global price-service
  cooldown yang akan memblokir perbaikan ticker berbeda. SOURCE_INVALID/BLOCKED_DEPENDENCY menyatakan akar masalahnya.
- Telegram-trigger hanya enqueue melalui routine EXECUTE dengan izin terbatas; tidak menulis Feature values, menjalankan
  arbitrary SQL, atau memanggil TradingView/Railway Run Now untuk retry Feature04. Semua handler tetap memeriksa webhook
  secret dan owner Chat ID. Existing command log dapat memakai TRIGGERED sebagai "request accepted/enqueued" dengan
  request ID di kolom reference baru; `railway_reference` tetap khusus price command.

#### Dependency dan per-column freshness

| Pilihan gagal | Scope kalkulasi/penulisan yang konsisten |
|---|---|
| ADX14, RSI14, ATR14, SMA20/50, EMA50/200, inside bar | Formula mandiri; full-history replay untuk warmup/state, write kolom terpilih. |
| EMA12 atau EMA26 | EMA terpilih serta downstream MACD, MACD signal, MACD histogram. EMA upstream lain dibaca/dihitung sebagai dependency, ditulis hanya bila juga gagal/stale. |
| MACD/MACD signal/MACD histogram | Kelompok tiga MACD; EMA12/26 dihitung sebagai upstream, tidak overwrite yang current. |
| Salah satu Bollinger band | Ketiga band dalam satu kelompok; SMA20 dihitung/dites sebagai dependency dan identitas middle-band. |
| SMI atau salah satu state/break swing | Sembilan kolom SMI/swing dalam satu replay causal. Tidak memperbarui SMI saja sambil meninggalkan state lama. |
| Satu pola candlestick | Hanya pola tersebut dengan candle settings/lookback asli; pola lain tidak diubah. |

Hitung dependency upstream dari source; jangan memakai nilai target lama sebagai seed. Closure juga menyertakan dependents
yang menjadi stale bila upstream berubah; tampilkan closure sebelum enqueue. Shared formula calls menghasilkan coherent
multi-column bundle. Kolom identity/metadata tidak boleh dipilih sebagai indikator; allowlist 50 outputs dari engine.
Provider/symbol mapping juga divalidasi; perubahan yang memengaruhi source contract harus invalidate pekerjaan, walaupun OHLCV sama.

`Feature04_Column_Status` mempunyai PK `(ticker,timeframe,feature_column)` (sekitar 42.200 row untuk 844 ticker),
bukan 66 juta row per candle/column. Simpan requested/completed generation, source-input fingerprint,
version, dirty_from/validated-through, status PENDING/PROCESSING/SUCCESS/FAILED/BLOCKED, error code/message,
last attempt/retry cycle dan latest availability + expected NULL counts/reasons. Attempt log menyimpan outcome/range
per kelompok/column sebagai structured JSON. SUCCESS berarti validated output current, termasuk expected NULL.
Actual unexpected NULL/mismatch/nonfinite post-availability = VALIDATION_FAILED; unavailable upstream = dependency failure
yang menunjuk root, bukan 50 error independen. Library/source/DB fatal failure dicatat di ticker attempt, kolom BLOCKED.
Validator memakai aturan per-segmen valid, native pattern codes dan toleransi float; tidak menganggap kode 80/200 atau
SMI floating overshoot kecil sebagai error. Definisi formula tetap v3.

Untuk generation sama dan versi sama, hasil kelompok sukses boleh commit walaupun kelompok lain gagal; kelompok gagal
tidak ditimpa, statusnya FAILED/stale. Retry indikator menulis hanya selected closure dari dirty date sampai latest.
Field target lama pada kelompok gagal bukan current: **status kolom wajib dipakai untuk readiness**; existing row-level
`calculation_version`/`calculated_at` tidak membuktikan semua kolom fresh. Ticker SUCCESS hanya jika seluruh 50 kolom SUCCESS
pada generation/version yang diperlukan; NULL sah tidak menghalangi sukses. Ini revisi kontrak atomisitas awal per-ticker:
set write terpilih + status/log commit atomik, masing-masing dependency bundle lengkap, bukan partially written bundle.
Formula-version upgrade tetap wajib full-ticker atomic recalculation; column retry tidak membuat mixed formula versions.
Generation berubah saat retry: hasil dibuang SUPERSEDED; queue otomatis full refresh menangani source terbaru,
request lama tidak boleh melaporkan seleksi kolom lama sebagai pemulihan source baru. Retry source unchanged tidak perlu
menambah source generation, tetapi memakai work/request revision terpisah agar gagal lama tidak menutup attempt baru.

Queue per ticker menambahkan requested column mask, work revision dan retry-cycle reference; claim memotret ketiganya.
Perubahan source selalu membuka scope ALL, sehingga prioritasnya mengalahkan retry parsial source lama. Scope dua request
boleh digabung hanya jika generation/version sama dan masing-masing membership tetap mencatat pilihan asli.
Trigger price cukup menaikkan ticker generation; tidak perlu memperbarui 50 status rows per candle dalam transaksi harga.
Readiness/failure views membandingkan completed column generation terhadap requested ticker generation; failure dari source
lama tidak ditampilkan sebagai failure aktif source baru. Worker membuat status PENDING untuk scope yang sedang diproses.
Reset retry budget manual berlaku untuk request/kelompok yang dipilih, tidak untuk indikator gagal lain yang tidak dipilih.

#### Monitoring retry dan urutan Telegram

Pembagian service yang disetujui:

| Service | Peran Feature04 | Tidak dikerjakan service ini |
|---|---|---|
| `telegram-trigger` | Menerima webhook/command owner, menampilkan menu status dan retry, memvalidasi callback/preview, dedup click, lalu memanggil routine DB terbatas untuk enqueue retry. Command price/recovery lama tetap memakai Railway Run Now. | Tidak menghitung indikator, tidak menulis Feature04, dan retry Feature04 tidak menjalankan price cron. |
| `feature-04-worker` (baru) | Membaca queue otomatis/retry, claim per ticker, replay history, menulis bundle kolom yang valid, memperbarui status/log/run/outbox, dan melanjutkan ticker berikutnya bila satu ticker gagal. | Tidak menerima Telegram webhook dan tidak mengambil data TradingView. |
| `telegram-monitor` | Menerima private notify untuk execution/run yang sudah committed, membaca monitoring/outbox, memformat dan mengirim hasil price/Feature04, serta mencatat delivery dedup. | Tidak menghitung ulang indikator dan tidak memutuskan scope retry. |

Kedua service Telegram tetap event-driven tanpa cron. `telegram-trigger` bangun karena webhook Telegram; `telegram-monitor`
bangun karena private notify dari price job/worker. Worker Feature04 satu-satunya service baru dan berjalan terus sebagai
consumer queue. Menu retry hanya membuat durable request; worker yang mengeksekusinya. Acknowledgement "diterima" berasal
dari trigger, sedangkan hasil final berasal dari monitor. Secret bot tetap di service Telegram; worker hanya memerlukan
database dan shared private-notify credential, tanpa token Telegram.

Retry menjadi child run bertipe `RETRY_TICKER` atau `RETRY_COLUMN`, menaut ke parent price/Feature04 run.
Parent summary historis tidak ditimpa; error attempt lama tetap ada, current status dan child recovery diperbarui.
Pesan awal: "Permintaan ulang diterima" dengan jumlah ticker/indikator dan scope terkait. Pesan akhir memakai child run ID
untuk dedup; laporkan selected scope yang pulih, yang masih gagal dan status keseluruhan ticker/batch.
Contoh: "ADX BBCA berhasil dihitung ulang; ticker masih PARTIAL karena SMI belum pulih" tidak boleh menjadi
"Feature04 fully calculated". Request selesai berbeda dari ticker semuanya current.
Auto batch dan child run tetap menunggu parent price Telegram SENT dengan message ID sebelum pesan hasil Feature04.
Acknowledgement command boleh langsung. ADHOC/rekonsiliasi tanpa price run memakai event origin sendiri, tidak menunggu
price execution yang tidak ada. Telegram failure tidak membuka ulang kalkulasi yang sudah sukses; outbox hanya retry delivery.

#### Fase implementasi dan kriteria selesai

| Fase | Perubahan konkret | Validasi / exit gate |
|---|---|---|
| 1. Kontrak & engine diagnostics | Registry dependency/50 columns + group result/error/availability di `features/feature04`; refactor memakai rumus/seed yang sama, strict `calculate()` tetap kompatibel. | Existing engine tests + exact equal outputs old/new pada fixtures dan source snapshot BBCA/GOTO serta ticker history pendek/flat; fault injection ADX dan SMI menunjukkan isolasi error/closure. |
| 2. Database control | Forward migration baru untuk tujuh tabel, routines enqueue/claim/retry/status, column/request revisions, price trigger dan permission roles; katalog seluruh tabel/kolom/routines. Forward alter `Telegram_Command_Log` tambah nullable `feature04_request_id`, tanpa mengubah histori price command. | Rollback DDL rehearsal, constraint/grant checks, source+enqueue atomic rollback, request dedup dan generation race; measured queue/failure/lease query plans. |
| 3. Worker | `apps/feature-04-worker`: serial ticker, full causal replay, selective bundle writes, per-column status, retry/backoff/leases, source and work revision checks, startup reconciliation dan notification outbox. | Commit/readback closure sesuai source; unrelated fields/tickers/timestamps unchanged; fatal DB exception rollback; duplicate/restart/superseded claims; 5.000-row guard. |
| 4. Price/monitor integration | Transaction-local execution ID, batch membership/sealing di `apps/idx-price-cron/price_update.py`; allowlist/format/status acknowledgement dan inline Feature04 menu di `apps/telegram-monitor`. | Partial/empty price batch, strict price-message SENT gate, restart between commit/POST, delivery 202/SENDING/FAILED, suppressed-message gate; mock Telegram, tanpa live send. |
| 5. Telegram control | `/feature4` + paginated failure views, token preview, run/cancel, atomic request enqueue/audit di `apps/telegram-trigger`; fungsi DB allowlisted, tidak lewat Railway Run Now. | Owner/webhook checks, forged/expired callback, stale selection, repeat Telegram update/click, no-failure no-op, per-scope cooldown; successful scopes excluded. |
| 6. Canary BBCA | Deploy satu worker dengan allowlist sementara BBCA dan per-column bootstrap dari source terbaru; test ticker retry dan ADX/SMI column retry via controlled fixtures/rollback rehearsal. | Readback semua 50 outputs, force group failure yang tidak merusak source, retry selected closure only; existing Feature01/price unaffected; live owner Telegram test hanya setelah tahap eksekusi diotorisasi. |
| 7. Semua eligible & docs | Lepas canary setelah pass; durable queue capture sebelum activation, baseline verify 844 ticker, reconcile drift. Catat service/watch paths/IaC dan version/readiness contract. | Semua queue/column statuses benar, 844 source coverage tepat tanpa menyamakan max date dengan freshness; error output tak dianggap current; operational monitoring+retry delivery diverifikasi, tepat deployment SUCCESS. |

File baru/utama yang direncanakan: worker Dockerfile/requirements/README/tests; shared Feature04 dependency/diagnostic
modules + tests; forward SQL migration (nomor ditentukan dari main saat implementasi, semua applied migrations immutable);
price/telegram handler dan tests; `.railway/railway.ts`; `FEATURE04_TECHNICAL_INDICATOR.md`, `FEATURE04_COLUMN_DEFINITIONS.md`,
`DATABASE_SCHEMA.md`, `DATABASE_CATALOG.md`, `DATABASE_CHANGELOG.md`, `RAILWAY_CHANGELOG.md`, `PROJECT_CONTEXT.md`, error ledger
dan verification evidence. AI allowlist/provider tidak masuk scope. Build harus membawa shared engine dan watch path-nya.

Acceptance khusus retry: (a) ticker A gagal, ticker B sukses tidak ikut recalculated; (b) ADX gagal hanya ADX ditulis,
(c) SMI gagal kesembilan state columns coherent, (d) EMA12 pulih dan MACD downstream ikut valid, (e) untouched columns
preserve value/calculated_at jika row payload tidak berubah, (f) valid NULL tidak menjadi infinite retry,
(g) unexpected NULL yang dibuktikan masuk failure, (h) same-generation manual retry membedakan cycle dari source version,
(i) new price ketika retry berlangsung tidak kehilangan refresh, (j) run selesai dengan selected indicators pulih tidak
mengklaim ticker seluruhnya sukses, (k) parent price notification mendahului Feature04 result, (l) DB/Telegram outage
tidak mengulang TradingView atau menghapus failure history.

Rollback: pause worker/retry enqueue endpoint, pertahankan durable price queue capture dan semua audit; restore deployment
handler bila perlu. Jangan menghapus status ketika output sebagian belum current. Replay pending setelah perbaikan;
monitor memberi status belum selesai sampai semua dependencies valid. Migrasi tidak dibatalkan dengan menghapus tabel/data.

Kedua ambiguitas material sudah diputuskan user (2026-10-11, "both ya"): error nyata termasuk unexpected NULL yang terbukti,
NULL sah dikecualikan, dan dependency closure wajib. Pilihan batch/ticker disediakan menu, default latest unresolved.
Implementation plan memakai keputusan tersebut dan disetujui user pada 2026-10-11; belum ada perintah go eksekusi/deployment.

## ORC-SANDBOX-READINESS — startup lengkap dan pertanyaan BFF menunggu dependency

**Persetujuan menyusun plan, 2026-10-19:** user: "Okay, inspect infra dan siapkan implementation plan.
Edit langsung dari git instead of hardcode langsung di railway. Cek dulu apakah bisa atau tidak."
User kemudian meminta pemeriksaan penyebab sandbox tidak tersedia lebih dahulu. Inspeksi tersebut selesai;
hasil di bawah masuk plan. **Belum ada perintah menjalankan perubahan aplikasi atau deploy.** M187 di error ledger.

**Tambahan permintaan plan, 2026-10-19 (kata user):** "Boleh buat plan untuk mitigasi ini? mungkin AI orc ketika aware dia butuh samdbox, makandia akan trigger something sehinga di frontend akan keluar tekos ‘Initiating sandbox session.’" User juga meminta penyebab sandbox Online tetapi belum bisa dipakai diperbaiki dalam scope yang sama. User menjelaskan kredit Railway sebelumnya habis dan ditambah sebelum redeploy; ini keterangan user, bukan hasil audit billing.

### Preflight Git dan infra

- Repo `rednightt33/saniti`, branch source `main`; baseline `7cb16c6560645f36c77f07a4236acbf749f6fce4`.
  Git fetch berhasil, permission akun terhubung admin, dan push dry-run main berhasil. Push nyata plan
  tetap harus dibaca kembali sebelum menyatakan dokumentasinya sudah terbit.
- Project lucid-patience `8aef1702-030b-49cb-9df7-5ac2e0a42691`, environment dev
  `4d3e5af2-302b-4a2e-84e2-7d7476d6ff49`.
- Orc `41dc17ee-3bac-41ef-90ec-8b9356815c71`: Git main, root `/apps/market-ai-orc`, Dockerfile,
  watch `/apps/market-ai-orc/**`, satu replica, `/ready`, healthcheck 120 detik, restart ALWAYS.
  Deployment `7eff177f-5b4d-424b-842d-df10a55a5817`, commit `01608fd968981ae41ed22ebd240f02e9edb8fe90`.
- BFF `c3656044-2817-44a7-9b55-54910bab416f`: Git main, root `/apps/edge-bff`, Dockerfile,
  watch `/apps/edge-bff/**`, satu worker Uvicorn, `/ready`, healthcheck 120 detik, restart ALWAYS.
  Deployment `1a6a3146-7b9c-40f0-a5a8-4587368e1c3f`. Antrean durable dan lease sudah tersedia.
- Sandbox `225b1be1-d7f5-4b2d-a4c7-052eb53af818`: Git main, root `/apps/market-python-sandbox`,
  satu replica, `/ready`, healthcheck 300 detik, restart ALWAYS, volume `/data`.
  Deployment `84fa7fa3-6bda-46af-8162-7d13d42fde7b`, commit `454272ee8c1f643ca97b9c93ca791723b483971c`.
  Manifest deployment mencatat `sleepApplication=false`; tidak ada sleep karena idle pada kejadian ini.
- Semua service tersebut mengikuti Git. Implementasi bisa lewat commit source main; tidak perlu Railway
  upload, perubahan dashboard, service baru, perubahan secret atau perubahan start command.
  `.railway/railway.ts` sudah mencatat kontrak deploy yang relevan. Docs-only commit di luar watch path
  tidak dimaksudkan menjalankan rollout aplikasi.

### Penyebab yang terverifikasi

18 Oktober 16:22 WIB: sandbox lama shutdown normal. Deployment baru dibuat 16:31 dengan metadata
`reason=redeploy`, source commit sama; sandbox baru ready 16:32. Record menyebut akun yang memicu,
tetapi belum membuktikan manusia atau otomatisasi yang menjalankan stop/redeploy. Tidak menyimpulkan
crash, OOM atau autosleep dari kejadian ini. Ada jeda service tidak tersedia sekitar sepuluh menit. Keterangan user mengenai kredit habis lalu top-up
konsisten dengan stop/redeploy tersebut; billing belum diverifikasi independen. Pemeriksaan ulang sesudahnya
menunjukkan Orc dan sandbox sama-sama Online, masing-masing satu replica, pada deployment yang sama.

Orc mulai lebih dahulu dan pada 16:31 mencatat `python_sandbox_not_ready`, menutup client, menetapkan
`sandbox=None`, lalu membangun registry tanpa tool kalkulasi. `/ready` tetap sukses. Registry, callback
sesi, mode efektif dan result store dibuat sekali. Request 19 Oktober 02:09
`edge_53fbcd8f586f0f674ead86d27a086eb9` dan 09:12 `edge_0abf7e606ba1a4a1ebc372b667c672d3`
berakhir LIMITED, tool_calls=0, sandbox NOT_USED; `run_python` tidak ditawarkan.

BFF punya celah berbeda: pada percakapan lama, submit memanggil `orc.messages` sebelum `store.submit`.
Jika Orc belum tersedia, pertanyaan belum masuk antrean. Worker sudah mempunyai RECOVERING dan
rekonsiliasi request ID; itu dipertahankan untuk mencegah kalkulasi ganda.

### Perubahan minimal yang diusulkan

1. **Orc startup:** saat sandbox diwajibkan konfigurasi, tunggu `/ready` dan runtime valid sebelum
   membuat registry. Satu deadline monotonic dengan backoff dan timeout per GET dibatasi sisa waktu.
   Usulan default total 90 detik di `config.py`, dengan headroom terhadap healthcheck 120 detik;
   ukur keseluruhan startup sebelum menetapkannya. Jangan memperpanjang timeout Railway langsung.
   Jangan lanjut menerima request dengan fallback `sandbox=None` ketika kemampuan kalkulasi diwajibkan.
   Jika deadline habis, startup gagal jelas dan deployment tidak sehat; Railway mengikuti kebijakan
   restart yang sudah ada. Ini tidak menjamin availability selama sandbox memang tidak tersedia.
2. **Metadata:** ambil satu snapshot runtime valid untuk seluruh negosiasi startup. Kegagalan/JSON
   kosong tidak disimpan sebagai kemampuan permanen. Optional feature/version yang tidak didukung
   tetap mengikuti guard yang ada; tidak menyalakan flag atau melewati validasi.
3. **Persiapan sesuai kebutuhan AI:** pertahankan client dan registry setelah startup valid. Ketika AI
   memilih tool yang membutuhkan sandbox, jalur backend memastikan dependency siap sebelum pekerjaan
   baru dikirim. AI tetap menentukan kebutuhan analisis; jangan menebak dari keyword pertanyaan.
   Pakai helper readiness bersama untuk seluruh jalur pembukaan sesi, termasuk research; DataNeed
   yang mengakses sandbox sebelum sesi juga memakai guard ini. GET readiness/runtime boleh dicoba
   ulang dengan backoff, deadline monotonic usulan maksimum 90 detik dan dibatasi sisa deadline run.
   Stop diperiksa selama menunggu; batasi timeout tiap GET. Request bersamaan berbagi pemeriksaan
   readiness yang sedang berjalan, tetapi identitas/progress dan sesi tetap terpisah per request.
   Validasi runtime pulih terhadap kontrak startup; ketidakcocokan bukan alasan menyalakan kemampuan
   baru diam-diam. Pertahankan registry, callback dan mode; tidak rebuild global di tengah run.
   Jangan replay POST kalkulasi atau pembukaan sesi ambigu otomatis. Sandbox restart dapat menghapus
   sesi yang sudah ada; tandai kehilangan sesi dengan jelas, jangan klaim melanjutkan Python lama.
   Deadline recovery berakhir sebagai dependency tidak tersedia, bukan sukses atau jawaban kalkulasi.
4. **BFF submit:** auth, format dan kepemilikan lokal tetap di awal. Simpan pesan secara durable sebelum
   pengecekan remote conversation. Pindahkan validasi remote ke worker ketika Orc siap; pisahkan
   conversation expired/owner mismatch dari dependency sementara tidak tersedia.
5. **BFF worker:** pakai queue, lease, heartbeat, stop dan RECOVERING yang ada. Selama job menunggu,
   cek readiness dengan timeout pendek/backoff bertahap; setelah siap tetap rekonsiliasi request ID
   sebelum POST. Readiness bukan bukti POST sebelumnya tidak pernah berjalan. Probe menunggu tidak
   memakai attempt_count pengiriman dan tidak membuat request ID baru. Pertahankan deadline delivery
   yang sudah dikonfigurasi (default timeout 3900 + lease 90 detik); jangan mengubahnya diam-diam.
6. **UI/progress:** sebelum Orc menerima run, BFF menampilkan "Waiting for services to be ready."
   melalui status delivery yang sudah ada. Jangan menyebut sesi sandbox sebelum kebutuhan analisis
   diketahui. Setelah AI memilih jalur sandbox dan backend benar-benar memeriksa kesiapan/membuka
   sesi, tampilkan tepat **"Initiating sandbox session."**. Setelah sesi berhasil dibuka, lanjutkan
   progress kalkulasi yang sudah ada; saat gagal, step gagal dan alasan dependency ditampilkan jelas.
   Gunakan `progress.step` Orc dan endpoint BFF `/runs/{request_id}/progress`, yang sudah dipoll UI;
   tidak perlu transport/service progress baru. Pastikan step menutupi readiness dan open session,
   seluruh jalur sesi, serta tidak muncul untuk chat yang tidak memanggil sandbox. Wording frontend
   di `edge-labels.js`, backend label di `user_texts.py`, response adapter di `edge-view.js` jika perlu.
   Bedakan dependency-wait dari RECOVERING pengiriman umum menggunakan reason terstruktur pada
   status yang ada; jangan mengganti semua error recovery dengan label sandbox. Saat deadline
   tercapai, tampilkan delivery terputus dengan pesan tetap tersimpan; tidak mengklaim pekerjaan remote
   pasti dibatalkan. Stop selama menunggu tetap berfungsi.

Alur target: pertanyaan tersimpan → tunggu Orc bila perlu → AI memilih kebutuhan analisis →
"Initiating sandbox session." → cek readiness terbatas → buka sesi pada bundle READY → kalkulasi →
hasil. Persiapan sesi ini memanggil API aplikasi sandbox, bukan Railway redeploy. Untuk kejadian saat
ini, rollout Orc yang sudah diperbaiki diperlukan agar registry lama yang tidak lengkap diganti.
Startup gate menyelesaikan dependency terlambat saat redeploy; guard on-demand menyelesaikan gangguan
setelah startup. Keduanya diperlukan: label frontend saja tidak memulihkan tool yang hilang.

### Scope dan biaya

Kode utama: Orc `app/main.py`, `app/tools/analysis.py`, pengaturan default bila diperlukan, serta test;
Orc session/DataNeed/research entry points dan progress/user_texts; BFF `app/main.py`, `app/client.py`,
`app/worker.py`, label/pemetaan status, adapter progress bila perlu dan test. Tidak perlu schema
baru, perubahan warehouse, cron harga/Feature04, model/provider, service sandbox atau service baru.
Tidak ada probe baru saat idle. Retry hanya pada startup atau saat ada job menunggu dependency.
Tidak ada LLM call sebelum runtime startup wajib siap. Saat dependency putus setelah startup, retry
kesiapan dilakukan backend dalam tool, tanpa meminta model mengulang planning tiap percobaan.
Tidak menambah Railway credential/permission ke AI. Jika kredit masih habis dan platform menghentikan
service, aplikasi tidak dapat menghidupkannya sendiri; kredit/layanan harus dipulihkan di Railway.
Alert saldo/anggaran Railway dapat diaktifkan pemilik akun; automation top-up di luar scope ini. Resident RAM sandbox sekitar 197 MB tidak diturunkan
oleh perbaikan ini; sleep/RAM merupakan keputusan terpisah. Mengubah startup agar chat ringan tetap
berjalan tanpa sandbox memerlukan lifecycle runtime dinamis yang lebih besar dan di luar usulan minimal.

### Acceptance dan rollout melalui Git

- Test sandbox down lalu ready: registry lengkap, callback/mode sesuai kontrak dan startup terukur
  masih dalam healthcheck; test down terus berhenti tepat deadline tanpa status ready palsu/LLM call.
- Test `/ready` sukses tetapi runtime gagal/invalid: tidak membentuk kemampuan dari snapshot kosong;
  snapshot sukses dipakai konsisten dan hanya diambil sekali selama inisialisasi.
- Test client yang telah siap mengalami gangguan lalu pulih tanpa penghapusan registry/replay POST.
- Test AI memilih sandbox setelah dependency sempat offline: label "Initiating sandbox session."
  tampil saat readiness/open berlangsung, satu sesi baru yang terkonfirmasi, kalkulasi benar dan hasil
  bersumber dari tool. Chat tanpa sandbox tidak menampilkan label itu. Uji jalur DataNeed/research,
  runtime tidak kompatibel, timeout, Stop, open POST ambigu, sesi lama hilang dan request bersamaan;
  tidak ada LLM retry loop, busy loop atau kebocoran owner. Dependency pulih setelah waktu startup
  habis harus dapat diinisialisasi oleh proses Orc sehat berikutnya; tidak menerima registry kosong.
- BFF percakapan baru/lama saat Orc belum ready: pesan tersimpan, owner/expiry diperiksa, UI menunggu,
  pulih lalu kirim satu kali dengan ID tetap. Test request sudah RUNNING/COMPLETED, POST ambigu,
  cold-start berbarengan, lease fencing, stop dan deadline agar tidak ada kehilangan/duplikasi.
- Ubah test lama yang menganggap startup tanpa tool sebagai hasil sukses; jalankan regression startup,
  registry/mode/capability, client, BFF delivery, ownership, idempotency dan status UI. Tidak perlu
  mengubah prompt/model untuk masalah ini. Jika generator AI_TOOLS/AI_MODELS terdampak pengaturan,
  jalankan generator dan contract test sesuai AGENTS.md; jangan mengubah tool catalog tanpa perubahan definisi.
- Setelah user go: re-fetch main, isolasi patch dari pekerjaan lain, implementasi dan test lokal; review
  diff lalu commit/push main. Verifikasi exact deployment SUCCESS masing-masing service dan log tool
  aktif; baru jalankan satu uji kalkulasi kecil yang disepakati untuk membuktikan sandbox dipanggil.
- Rollback per service ke commit yang diketahui, dengan sandbox disiapkan lebih dahulu. Queue dan
  hasil tersimpan dipertahankan; tidak menghapus state atau replay pekerjaan secara massal.
- Saat selesai, perbarui M187, README Orc/BFF, PROJECT_CONTEXT bila kontrak berubah,
  RAILWAY_CHANGELOG dan bukti verifikasi; keluarkan item dari plan hanya setelah live terverifikasi.

**Status:** infra/source dan jalur Git terinspeksi; implementasi/deployment belum dijalankan.
