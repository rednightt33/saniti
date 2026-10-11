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
| 11 | P9 kamus nilai dan alat "cari nilai" | Keputusan desain user 2026-10-01 | Belum; perlu cek ulang cakupan | 11 |
| 12 | Prosedur tabel baru (FX, indeks, makro) | 2026-10-01 "record now, run later" | Menunggu pemicu: tabel baru | Saat ada tabel baru |
| 13 | Feature04 otomatis setelah update harga; Telegram price lebih dulu, hasil indikator sesudah selesai | 2026-10-11 (desain secara umum) | Menunggu perintah eksekusi; filter eligibility bila ada | Setelah go user |

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
- **Keputusan yang masih terbuka** (`FACTOR_EVENT_RESEARCH_PLAN.md` §12, dijawab sebelum mulai): urutan langkah,
  `AI_RESEARCH_MIN_ANGLES=4`, perlakuan bila data < 4 angle, `AI_RESEARCH_MIN_FAMILIES`.
- **Status:** S20 OPEN, S22 PARTLY FIXED.

## 11. P9 kamus nilai dan alat "cari nilai"

**Asal:** `VALUE_DICTIONARY_PLAN.md`. Rencana dipisah atas permintaan user 2026-10-01, dengan keputusan desain user
2026-10-01:
- memperluas job `ai-data-coverage`;
- dua jalur (katalog dan alat);
- `get_system_capabilities` dijalankan sistem di awal run, pilihan (a).

**Yang sudah menutup sebagian:**
- `get_dimension_values` (tabel statis);
- `lookup_reference` (tabel referensi, cari nama);
- `get_system_capabilities` (P31).

**Yang belum:** kamus nilai untuk kolom kategori di tabel bertanggal (G17 UNDERADDRESSED).

**Sebelum eksekusi:** cocokkan ulang isi rencana dengan alat yang sudah ada. `pg_trgm` adalah keputusan terpisah
(`FUTURE_PLAN.md` §3).

## 12. Prosedur tabel baru (FX, indeks, makro)

**Asal:** `NEW_TABLE_ONBOARDING_PLAN.md` (keputusan user 2026-10-01: "record now, run later").

Dijalankan saat tabel baru pertama dimuat, bersama Part A `ERRORS_AND_SOLUTIONS.md`. Tabel makro di database adalah
keputusan terpisah (`FUTURE_PLAN.md` §3).

**Rencana user 2026-10-09 (bukan perintah jalan):** "saya plan sehabis ini karena kuota weekly sudah habis tuk ingest habis2an data macro, fundamental, fx, cross market, commodities etc. kemudian feature.. ini adalah proses onboarding only. saya minta kamu cek, table onboarding plan MD apakah bisa solely cukup dijadikan dokumen onboarding table ini, yang mana pada akhirnya data2 ini juga bisa visible ke sisi AI?" Rencana diperiksa dan diperbarui hari yang sama (rantai visibilitas AI, butir 14–21, pertanyaan per kelas aset, tabel Feature, keadaan kode sekarang, daftar yang harus jadi sebelum tabel pertama dibuka ke AI). Usulan kode di dalamnya (ERRORS M136, M137) menunggu keputusan user.

---

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

## 13. Feature04 otomatis setelah update harga


Permintaan user: "cek bagaimana data price diupdate dan bagaimana trigger monitoing ke telegram terjadi ...
design job ketika harga update then indikator juga auto calculate fir eligible ticker ... design dulu baru confirm".
**Persetujuan desain secara umum, 2026-10-11:** user:

> Ok, monitoring update ke telegram setelah:
> 1. update ke telegram price selesai
> 2. feature 4 fully calculated?

Urutan notifikasi dicatat di bawah. Ini persetujuan rencana; belum ada perintah implementasi/deployment. Pemeriksaan menggunakan SELECT melalui role `pgweb`
dengan `transaction_read_only=on`, pembacaan kode, dan Railway describe; tidak menjalankan price job atau mengirim Telegram.
Bukti: `verification/feature04/automation_design_inspection.json` dan `automation_design_railway.json` dalam direktori yang sama.

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
   Snapshot lama atau exception tidak boleh menulis sebagian output maupun menandai DONE.
7. Freshness dinilai dari `completed_generation=requested_generation` dan versi engine yang sesuai, bukan tanggal maksimum saja.
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

Usulan lima tabel baru (semua nama belum dibuat):

| Objek | Grain / fungsi |
|---|---|
| `Feature04_Calculation_Queue` | Satu row per ticker/timeframe; work coalescing dan status freshness. |
| `Feature04_Calculation_Log` | Satu completed attempt; SUCCESS/FAILED/SUPERSEDED, generation, source/output hash, durasi dan changed rows. |
| `Monitoring_Feature04` | Satu run per source execution; price scope, updated/missing, calculation scope, counts, status dan waktu. |
| `Monitoring_Feature04_Ticker` | Satu ticker/timeframe per run; required generation, outcome dan error. |
| `Feature04_Notification_Outbox` | Satu event per run/type, atau ADHOC ticker/generation/error; payload reference, lease, next retry dan delivery state. |

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
