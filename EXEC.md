# EXEC: eksekusi yang sudah disetujui

Setiap eksekusi yang isinya disetujui user ada di sini, satu bagian per eksekusi, dengan rinciannya langsung di
bawahnya (keputusan user 2026-10-06: "EXEC itu harusnya jadi 1 file dengan setiap execution yang berbeda …
gabungkan ya", pilihan "File baru EXEC.md"). Pekerjaan yang disetujui tetapi belum punya rencana eksekusi ada di
`PLAN.md`; usulan dan keputusan terbuka di `FUTURE_PLAN.md`. Kode masalah merujuk ke `ERRORS_AND_SOLUTIONS.md`.

## Keputusan 2026-10-06 untuk menjalankan

- "kita jalankan setiap EXEC + GT yang memang diperlukan", lalu "mulai" (konfirmasi mulai).
- Kredit: "Jalan dengan USD 1,59" (sisa batas kunci OpenRouter); berhenti dan lapor bila sisa < USD 0,30 sebelum
  sebuah uji.
- Antar gelombang: "Lanjut otomatis bila lulus"; berhenti dan lapor hanya pada kondisi berhenti.
- EXEC-C: Q1 "pakai MEMO", Q2 "BACKEND + AI".
- Varian nilai desain dan koreksi uji berganda (lintas varian dan lintas giliran) dilebur ke EXEC-3 dan EXEC-A
  (pilihan "2+5 Varian + koreksi", "Lebur ke EXEC-3 dan EXEC-A"). Usulan multi-tugas lain ke `FUTURE_PLAN.md`.
- 2026-10-06, sesudah gelombang 2 (target waktu sesudah penolakan ≤ 5% tidak tercapai, 20,5%): pilihan user "Lanjut
  gelombang 3 (Recommended)"; target 5% diukur ulang setelah M90 diperbaiki.
- 2026-10-06, benchmark router gelombang 3 tidak lulus (M98: jawaban router terpotong di batas 2.000 token, "ok" ditanya
  balik, waktu tengah 2,1 → 4,4 dtk): pilihan user "Naikkan batas token" (batas keluaran router 4.000 token dengan
  `AI_ENABLE_ASK_BACK`; router lebih lambat diterima), lalu benchmark ulang sebelum deploy.
- 2026-10-06, sesudah benchmark ulang (0 panggilan gagal; sisa selisih hanya "ok" dan "Cari pola apa saja …" yang
  ditanya balik): pertanyaan user "apakah memang semua harus di hardcode seperti ini? kenapa gak serahkan ke model
  saja?". Keputusan (rencana disetujui):
  - penilaian (maksud, jalur, kapan bertanya balik, isi pertanyaan, nilai desain) diserahkan ke model;
  - kode hanya untuk jaminan (alat terkunci, data sesudah persetujuan, angka bersumber, kunci ambang/horizon, peta
    pilihan → jalur, pertanyaan baku saat model gagal, maksimal dua pertanyaan berturut-turut);
  - tambalan "ok" di instruksi ditarik;
  - pesan dengan dua jawaban wajar menerima keduanya di set benchmark;
  - syarat lulus benchmark hanya kesalahan mahal (data ke CHAT/FACT, harus-tanya tidak ditanya, pertanyaan jelas
    ditanya, panggilan gagal).
- Gelombang: 1 = EXEC-1 + EXEC-S; 2 = EXEC-E + EXEC-R + EXEC-P2; 3 = EXEC-3 + EXEC-A + EXEC-T; 4 = EXEC-C +
  EXEC-P5 + EXEC-P1, lalu golden test akhir.

## Ringkasan

**Selesai 2026-10-06:**
- EXEC-1 (sisa item 10 dan 12, menu alamat lengkap 1b) dan EXEC-S (satu `session_id` per percakapan), terverifikasi
  live; status di `ERRORS_AND_SOLUTIONS.md` (P35–P38, M96, R35, W26).
- Gelombang 2: EXEC-E (`get_evidence` dihapus), EXEC-R (R1–R5) dan EXEC-P2 (P2a, P2e), live di dev (orc `8740079c`);
  ulang uji `ma-qa-20261006e`: semua giliran selesai, tanpa gerbang EVIDENCE, tanpa angka tanpa sumber yang lolos.
  Target waktu sesudah penolakan ≤ 5% **tidak tercapai** (20,5%; 06b 26,8%). Sebab terbesar: M90 (EXEC-3/EXEC-A) dan
  jalur 10.6. Status di `ERRORS_AND_SOLUTIONS.md` (M84–M89, M91, P39, S23, G20, G21).
- Perbedaan dari kata-kata rencana gelombang 2 (R35):
  - P2e: target ±2.500 karakter ditulis ke model dalam kata-kata, bukan angka (prompt adalah sumber angka; tes pass 2
    melarang digit baru). Target 1.500 per bagian mode 4 hanya diukur lewat log, tidak dikirim ke model.
  - R1: `set` boleh mengisi field terakhir yang tidak ada di draf (field opsional). Cek skema penuh sesudahnya yang
    memutuskan.
  - R4b: kesempatan edit kedua diberikan sekali per draf dan tidak dihitung sebagai penolakan.
  - Commit: satu commit kode gelombang 2 (`6c6ce58`), bukan satu per EXEC.
  - EXEC-E langkah 5 menyebut uji ulang 2 item; dijalankan 3 item (lang, threshold, h_add) bersama EXEC-R.
- Gelombang 3: EXEC-3 (TANYA BALIK, pilihan cepat, pertanyaan baku, maksud user), EXEC-A (satu pembaca maksud di
  semua jalur termasuk P3b, varian dan koreksi uji berganda) dan EXEC-T (meja alat per proses). Live di dev: orc
  `f5bb4e23`, `AI_ENABLE_ASK_BACK=true`.
  - Uji `ma-qa-20261006f`:
    - "BBRI" ditanya balik dalam 3,1 dtk;
    - h_add menambah horizon 10 hari tanpa LIMITED (M90 selesai);
    - 4 varian BBCA dijalankan dengan koreksi Holm;
    - waktu sesudah penolakan 0,8% (target ≤ 5% tercapai);
    - 0 alat di luar meja dipanggil.
  - Status di `ERRORS_AND_SOLUTIONS.md` (M90, M97–M100, P40–P42).
- Perbedaan dari kata-kata rencana gelombang 3 (R35):
  - EXEC-T butir 3 (kalimat system prompt yang menyebut alat dipindah ke deskripsi alat atau catatan per langkah)
    **tidak dikerjakan**. Model tidak pernah memanggil alat di luar meja (06b, 06e, 06f), sedangkan prompt per meja
    memecah cache antar langkah. Kini keputusan terbuka di `FUTURE_PLAN.md` 3b.
  - Varian dan koreksi ikut saklar `AI_ENABLE_ASK_BACK`, supaya satu saklar cukup untuk mundur.
  - Keluarga koreksi = semua uji di percakapan (konservatif); hanya tampilan, putusan tiap uji tidak berubah.
  - Syarat benchmark router diubah atas keputusan user (hanya kesalahan mahal); batas token router 4.000 (M98).
  - Dua cacat dari uji live (M99 ID event study, M100 kalimat "tanpa koreksi") diperbaiki di kode tanpa uji ulang
    berbayar; dibuktikan tes unit dan diperiksa di golden test akhir.
- Laporan `GT_QA_2026-10-06.md` §6–8, deploy di `RAILWAY_CHANGELOG.md`.
- Gelombang 4 (2026-10-07): EXEC-C, EXEC-P5, EXEC-P1 live di dev.
  - Migration `20261006_003` (tabel memori) dan `20261006_004` (Tool_Catalog round K) diterapkan dan dibaca ulang.
  - orc `2eb9f9f1`, lalu `AI_ENABLE_RUN_MEMORY=true` dan `AI_ENABLE_MERGED_STEPS=true` (`48e41023`).
  - Golden test akhir batch A `ma-qa-20261007a` (4 item, 10 giliran, ±USD 0,63). Hasil di `GT_QA_2026-10-06.md` §9:
    - q7 giliran 1 11,6 menit (06b 34 menit), berakhir dengan rencana menunggu;
    - h_add dan threshold lolos semua giliran, jauh lebih cepat dari 06b;
    - 4 varian terjawab dengan koreksi;
    - 11 run, 11 baris memori;
    - waktu sesudah penolakan 10,3% (target ≤ 5% tidak tercapai).
  - Cacat dari uji: M101 dan M102 (EXEC-P5 tidak terlihat oleh AI lewat amplop; sesi saling menutup) dan M103
    (angka rencana yang dibatalkan). Ketiganya diperbaiki di kode dan di-deploy (`3d217256`), belum diukur live.
    M104 (kalimat uji 06b dibaca BATAL di alur baru) tetap terbuka.
  - **Berhenti:** sisa kredit USD 0,225 < USD 0,30 sebelum batch B. Batch B dan uji ulang q7 menunggu kredit
    (perkiraan ±USD 0,40 seluruhnya).
- Perbedaan dari kata-kata rencana gelombang 4 (R35):
  - EXEC-C dan EXEC-P5 di balik saklar baru (`AI_ENABLE_RUN_MEMORY`, `AI_ENABLE_MERGED_STEPS`), supaya ada jalan balik
    tanpa redeploy.
  - EXEC-P1: benchmark router tidak diulang; instruksi dan skema penyortir terbukti byte-identik, yang berubah hanya
    teks dokumentasi EXPLORE.
  - Uji ulang per-EXEC dilebur ke golden test akhir (seperti rencana gelombang 4).
  - Butir 7: respons rencana tidak boleh membawa metodologi (skema), jadi riwayat giliran berikutnya mengambil
    metodologi tiap langkah dari blok mode 4 yang tersimpan.
  - Pikiran AI disimpan di tabel percakapan (30 hari, ikut terhapus bersama percakapan), bukan di audit store.
  - Golden test dibagi dua batch supaya aturan kredit tetap berlaku; kalimat item disalin persis dari 06b/06f.
  - Tiga perbaikan kecil sesudah uji (M101–M103) di-deploy tanpa uji ulang berbayar, karena kredit habis; dibuktikan
    dengan tes unit yang gagal tanpa perbaikan.

| No | Butir | Disetujui | Status | Urutan usulan |
|---|---|---|---|---|
| 1d | EXEC-C: AI membawa semuanya ke run ID berikutnya dalam satu percakapan, tanpa terkecuali (13 butir, termasuk P4) | 2026-10-06 ("masukan exec"; "Seharusnya AI membawa semuanya tanpa terkecuali. Masukan EXEC") | Live di dev 2026-10-07; batch A sebagian lulus (§9), sisa uji menunggu kredit | — |
| 1e | EXEC-A: penyelarasan jalur (satu pembaca maksud, gerbang hanya meminta alat yang ada, 10.6 dan edit sama di semua jalur) | 2026-10-06 ("masukan exec") | Selesai 2026-10-06 (gelombang 3; P40) | — |
| 1h | EXEC-P1: mode 4 berhenti setelah analisis + rencana | 2026-10-06 ("p1 … masukan exec") | Live di dev 2026-10-07; giliran 1 lulus, persetujuan belum teruji live (M104) | — |
| 1i | EXEC-P5: gabung langkah mekanis | 2026-10-06 ("p5 masukan exec") | Live di dev 2026-10-07; tidak lulus di batch A (M101, M102), diperbaiki `3d217256`, ukur ulang di batch B | — |
| 1j | EXEC-T: perangkat alat per proses (matriks HARUS/BOLEH/TIDAK BOLEH final, alat terlarang dikunci kode dan tidak bisa ditemukan) | 2026-10-06 ("finalize dan masukan ke EXEC"; catatan user: alat TIDAK BOLEH dikunci kode, tidak boleh ditemukan lewat pencarian) | Selesai 2026-10-06 kecuali butir 3 (keputusan terbuka, `FUTURE_PLAN.md` 3b; P41) | — |
| 2 | P3: gerbang yang salah tolak | 2026-10-06 "OK masukan plan jangan execute dulu" | Selesai 2026-10-06 (P3a EXEC-1, P3b dan P3c gelombang 3, P3d EXEC-R) | — |
| 3 | Item 11: penyortir "free will", jalur TANYA BALIK, cadangan berupa pertanyaan | 2026-10-05 (16:47, 17:40, 17:51, 17:55), ditegaskan 2026-10-06; **EXEC 2026-10-06** | Selesai 2026-10-06 (EXEC-3, gelombang 3; M97) | — |
| 4 | P2: jawaban ditulis sekali | 2026-10-06 | Selesai 2026-10-06 (EXEC-R dan EXEC-P2, gelombang 2) | — |
| 5 | P1: mode 4 berhenti setelah analisis + rencana | 2026-10-06 | EXEC-P1 | — |
| 6 | P5: gabung langkah mekanis | 2026-10-06 | EXEC-P5 | — |
| 7 | P4: hasil jelajah dibawa antar-putaran | 2026-10-06 | Masuk EXEC-C (butir 1d) | — |

Biaya model: setiap uji dan golden test. Sisa batas kunci OpenRouter setelah gelombang 3: USD 0,857 (2026-10-06;
benchmark router ±0,07 dan uji `ma-qa-20261006f` ±0,197), jadi kredit dicek sebelum uji apa pun. Sesudah batch A gelombang 4 (2026-10-07): USD 0,225.
Status **EXEC** = rencana eksekusi sudah disetujui isinya, tetapi **baru dijalankan setelah user memberi konfirmasi
mulai** (keputusan user 2026-10-06: "EXEC dijalankan setelah konfirmasi saya"). Konfirmasi mulai diberikan 2026-10-06 ("mulai"). Setelah dimulai, berhenti dan lapor bila menemui kondisi berhenti, atau bila perlu tindakan di
luar langkah ini.

Urutan sisa (menunggu kredit dan konfirmasi user):
- batch B (bakrie_bank, p2_pine_standard, "BBRI");
- ulang q7 dua giliran dengan "setuju, jalankan rencananya";
- bila lulus, EXEC-C, EXEC-P5 dan EXEC-P1 dihapus dari dokumen ini.

---

### EXEC-C: AI membawa semuanya ke run berikutnya, tanpa terkecuali (butir 1d, mencakup P4)

**Keputusan user (2026-10-06):**
- "masukan exec" (memo run setelah LIMITED / giliran baru);
- "Okay ini salah... Seharusnya AI membawa semuanya tanpa terkecuali. Masukan EXEC" (tentang pikiran AI, alasan
  penolakan, keputusan desain di luar rencana dan fakta web yang tidak terbawa);
- lalu "what else?", dijawab dengan 9 celah tambahan di bawah.

Keputusan ini menggantikan kalimat lama di butir ini, "pikiran mentah tidak dibawa".

**Lingkup:** setiap run ID baru dalam satu conversation ID menerima semua yang dihasilkan run sebelumnya. Ini berlaku
untuk giliran user berikutnya, sub-run mode 4 (m4a → m4b → m4c → m4d), dan run lanjutan setelah LIMITED.

**Yang dibawa** (13 butir; nomor 1–4 dari daftar awal, 5–13 dari cek ulang kode dan log 2026-10-06):

| # | Hal | Keadaan sekarang (bukti) | Perubahan |
|---|---|---|---|
| 2 | Alasan penolakan | Hanya baris batasan umum bila berakhir LIMITED | Setiap penolakan disimpan: gerbang atau alat, kode, pesan lengkap, bagian draf yang ditolak, dan perbaikan yang dicoba. Galat alat ikut, misalnya `query_metric` butuh tanggal awal+akhir, atau LAST butuh `group_by` |
| 3 | Keputusan desain di luar rencana | Hilang bila tidak masuk rencana | Horizon, ambang, efek minimal, cakupan, definisi dan pilihan AI disimpan beserta asalnya: kata user, hasil sebelumnya (alamat), atau pilihan AI |
| 4 | Fakta web | `web.<id>` tidak masuk data record; hanya kalimat asumsi | Amplop `citable` disimpan dan didaftarkan ulang sebagai sumber `web.<id>` di awal run berikutnya, beserta kutipan dan URL |
| 5 | Catatan data record | Dipotong di 8.000 karakter. Di 05b terjadi pada 11 dari 23 run. Dari q7 giliran 1 ke 2, 13 dari 14 output, 5 sudut riset dan semua temuan tidak terlihat. Di 06b mentok 8.000 di q7 m4c, m4d dan giliran 2 | Tidak ada potongan diam-diam. Output, temuan, jawaban sebelumnya dan keputusan selalu masuk. Bagian referensi panjang (relasi, nilai kategori) diringkas dengan penunjuk ke isi lengkap |
| 6 | Riwayat per pesan | Dipotong 16.000 karakter. Asumsi/Batasan/Metodologi ada di akhir, jadi terbuang lebih dulu. q7 giliran 1 menyimpan 20.450 karakter; 4.450 karakter bagian itu hilang (perbaikan M63 batal untuk mode 4) | Asumsi/Batasan/Metodologi tidak pernah terpotong. Bila perlu memotong, yang dipotong badan jawaban, dengan penunjuk ke teks penuh |
| 7 | Jawaban gabungan mode 4 | Metodologi hanya dari satu bagian; teks rencana m4b tidak ikut; Asumsi dan Batasan dibatasi 20 butir (`_merge`) | Metodologi semua bagian, teks rencana m4b, dan semua asumsi/batasan ikut |
| 8 | Di dalam rantai mode 4 | m4b dan m4d hanya menerima 5.000 karakter pertama analisis, m4d 6.000 karakter pertama riset; asumsi/batasan/metodologi analisis tidak diteruskan | Langkah berikutnya menerima semuanya lewat mekanisme yang sama dengan giliran baru (butir ini), bukan potongan teks |
| 9 | Kode Python run sebelumnya | Tersimpan di `AI_conversation_execution` (sampai 65.536 karakter), tetapi AI hanya melihat hash lewat `get_lineage` | Teks kode bisa dibaca AI dan masuk daftar isi memo |
| 10 | Isi katalog | Hanya nama kolom yang dibawa, tanpa arti, satuan dan peringatan, padahal catatannya berkata "jangan baca katalog lagi" | Arti, satuan dan peringatan kolom yang sudah dibaca ikut dibawa; kalimat catatan diselaraskan |
| 11 | Sumber angka run sebelumnya | Hanya `finding.*` yang otomatis terdaftar. `out.oN` baru bisa dikutip setelah `get_session_output`. `fact`, `metric`, `reference`, `web` dan `analysis` giliran lalu tidak bisa dikutip | Semua sumber run sebelumnya didaftarkan ulang di awal run dengan alamat yang sama, langsung bisa dikutip. Angka tetap dikutip lewat alamat; angka yang diketik ulang dari teks jawaban lama tetap tidak dianggap sumber (aturan gerbang tidak berubah) |
| 12 | Giliran gagal atau terputus | Tidak masuk riwayat sama sekali (riwayat hanya mengambil giliran dengan `assistant_text`) | Masuk riwayat: pesan user, kode galat, dan apa yang sempat dikerjakan |
| 13 | Bacaan penyortir per giliran | Jenis giliran, rujukan, perubahan nilai desain dan maksud (EXEC-3) tidak disimpan | Disimpan di state percakapan dan diberikan ke giliran berikutnya |

**Cara membawa:**
- **Penyimpanan:** satu catatan per run (memori run) di penyimpanan percakapan, berisi butir 1–13 dalam bentuk
  terstruktur, beserta isi lengkapnya (pikiran utuh, pesan penolakan, kode, draf). Masa simpannya sama dengan
  percakapan (30 hari). Tabel atau kolom baru mengikuti workflow AGENTS.md: migration, `DATABASE_SCHEMA.md`, changelog.
- **Masuk prompt:** memo terstruktur per run, ditempatkan setelah prefix statis. Susunannya terlama dulu dan hanya
  bertambah di belakang (append-only), supaya cache prompt antar run bisa terpakai (lihat EXEC-S).
- **Isi lengkap:** bisa dibaca AI kapan saja lewat satu alat baca memori percakapan (READS, tanpa model). Alat itu
  **H di semua perangkat** EXEC-T.
- Hanya penunjuk ke isi lengkap yang boleh menggantikan isi. Tidak ada potongan tanpa penunjuk (aturan P5 diperluas).

**Pertanyaan terbuka:**
- **Q1 (bentuk pikiran AI di prompt):**
  - (a) pikiran utuh dimasukkan ke prompt run berikutnya; atau
  - (b) yang masuk prompt adalah memo, sedangkan pikiran utuh tersimpan dan bisa dibaca lewat alat baca memori.

  Rekomendasi asisten: (b). Alasannya:
  - pikiran lama ikut membawa percobaan yang ditolak dan tebakan yang salah;
  - penyedia model sendiri tidak membawa pikiran antar giliran;
  - biaya bukan penghalang: cache dalam satu run 89%, jadi membawa 98 ribu token ke run 20 panggilan ±USD 0,022.

  **Diputuskan user 2026-10-06: "pakai MEMO" (b).**
- **Q2 (siapa menulis ringkasan pikiran, bila Q1 = b):**
  - fakta (butir 2–13) disusun backend dari kejadian yang tercatat, tanpa panggilan model;
  - ringkasan pikiran ditulis model sebagai satu field catatan di jawaban akhirnya (±200–500 token, tanpa panggilan
    tambahan).

  **Diputuskan user 2026-10-06: "BACKEND + AI".** Bila run berhenti tanpa jawaban akhir, bagian backend tetap
  tertulis.

**Berkas:**
- `data_record.py`, `conversations.py` (`assistant_text`, riwayat), `conversation_plans.py` (state), `mode4.py`
  (`sub`, `first_round`, `suggest`, `_combined_response`, `_merge`), `orchestrator.py` (`_build_input`,
  `_seed_data_record`, `_seed_findings` jadi semua sumber, akhir run), `tools/lineage.py`, `tools/catalog.py`,
  `tools/method_guides.py`;
- alat baca memori baru (+ `AI_TOOLS.md`, Tool_Catalog);
- migration penyimpanan memori.

**Tes:**
- percakapan uji 3 giliran + rantai mode 4: setiap butir 1–13 dari run sebelumnya terlihat atau bisa dibaca di run
  berikutnya;
- tidak ada potongan tanpa penunjuk (catatan data record, riwayat, jawaban gabungan mode 4);
- alamat `out`, `fact`, `metric`, `reference`, `web`, `analysis`, `finding` dari giliran lalu langsung lolos gerbang
  REFERENCE tanpa `get_session_output`;
- giliran gagal muncul di riwayat giliran berikutnya;
- alat baca memori ada di setiap perangkat (`tests/test_tool_desks.py`);
- susunan memo append-only: awalan prompt run N+1 sama persis dengan run N sampai akhir memo run N.

**Lulus bila** di ulang uji threshold (3 giliran) dan q7 (2 giliran):
- panggilan jelajah katalog di run lanjutan turun ≥ 50%;
- token berpikir langkah pertama run lanjutan turun;
- nol penolakan PROVENANCE/REFERENCE untuk angka yang berasal dari giliran sebelumnya;
- giliran 2 q7 menerima Asumsi/Batasan/Metodologi giliran 1 utuh.

#### Rincian dari butir 7 (dipindah dari `PLAN.md` 2026-10-06)

P4 sebagian sudah ada (koreksi 2026-10-06 di EXEC-C).

- Ringkasan katalog yang sudah dibaca (tabel, kolom, relasi, cakupan) dan panduan metode yang sudah dibuka disimpan
  di data record percakapan (`data_record.py`).
- Ringkasan itu diberikan ke putaran berikutnya (sub-run mode 4 dan giliran berikutnya) sebagai catatan aplikasi
  setelah prefix statis, supaya cache prompt tidak pecah.
- **Berkas:** `mode4.py` (`sub`), `orchestrator.py`, `data_record.py`, `tools/catalog.py`, `tools/method_guides.py`.
- **Bukti:** q7-m4b membaca ulang katalog dan 5 panduan (±170 dtk). Fakta yang sama ("Feature_01 punya sektor")
  ditemukan ulang di tiga item.

---

### EXEC-P5: gabung langkah mekanis (butir 1i)

- Rincian di bagian 6 di bawah.
- **Langkah:**
  1. kode `tools/data_need.py`, `data_planner.py`, `session.py`, `orchestrator._handle_call`;
  2. argumen `complete` di `run_python`;
  3. tes;
  4. `AI_TOOLS.md`;
  5. migration Tool_Catalog;
  6. deploy orc;
  7. ulang uji p2 dan threshold t1 (±USD 0,05).
- **Lulus bila:** panggilan model per analisis turun ≥ 3 tanpa kenaikan penolakan.

#### Rincian dari butir 6 (dipindah dari `PLAN.md` 2026-10-06)

- Setelah `submit_data_need_spec` diterima, backend langsung menjalankan `prepare_data_bundle` dan
  `open_analysis_session`, lalu mengembalikan hasil gabungan. Alat lama tetap ada untuk mengulang.
- `run_python` mendapat argumen `complete` (boolean): setelah kode sukses, backend menjalankan `complete_analysis`.
- **Berkas:**
  - `apps/market-ai-orc/app/tools/data_need.py`, `data_planner.py`, `session.py`;
  - `orchestrator._handle_call`;
  - `AI_TOOLS.md`;
  - migration Tool_Catalog round berikutnya;
  - tes.
- **Perkiraan:** 3–5 panggilan model lebih sedikit per analisis. Ongkos tetap ±3,6 dtk per panggilan, dan golden
  test 06b punya 52 panggilan kecil rata-rata 6 dtk.

---

### EXEC-P1: mode 4 berhenti setelah analisis + rencana (butir 1h)

- Rincian di bagian 5 di bawah.
- **Langkah:**
  1. kode `mode4.py` (`first_round`, `follow_up`);
  2. teks EXPLORE di `conversation_router.py`;
  3. `AI_ROUTER.md` diregenerasi dan benchmark router diulang;
  4. tes `test_mode4*`;
  5. deploy orc;
  6. ulang uji q7 giliran 1–2 (±USD 0,15).
- **Lulus bila:**
  - q7 giliran 1 ≤ 15 menit dan berakhir dengan analisis + rencana yang menunggu;
  - "setuju" menjalankan riset;
  - tidak ada rencana lanjutan tanpa diminta.
- **Jalan balik:** revert commit (tanpa saklar), atau saklar `AI_MODE4_AUTO_RESEARCH` (default mati = perilaku baru).
  Usul memakai saklar.

#### Rincian dari butir 5 (dipindah dari `PLAN.md` 2026-10-06)

**Bukti:** q7 giliran 1 makan 34 menit (analisis 759 dtk, rencana 350 dtk, riset otomatis 580 dtk, rencana lanjutan
250 dtk), atau 48% waktu model golden test 06b.

Perubahan ini mengganti perilaku keputusan 2026-09-30 / 2026-10-02 (riset pertama langsung jalan), dan sudah
disetujui masuk rencana.

**Perubahan:**
- `apps/market-ai-orc/app/mode4.py` `first_round`: setelah A (m4a) dan B (m4b), selesai dengan rencana B sebagai
  usulan menunggu (AWAITING_CONFIRMATION). C dan D tidak jalan otomatis.
- APPROVE menjalankan rencana (C). D hanya bila user meminta (`requested_count` SUGGESTION atau giliran CONTINUE).
- Teks yang ikut diperbarui:
  - `FIRST_ROUTES["EXPLORE"]` dan `FIRST_ROUTE_RULES` di `conversation_router.py`;
  - docstring `mode4.py`;
  - `AI_ROUTER.md` diregenerasi dan benchmark router diulang.
- **Tes:** `tests/test_mode4*.py`.
- **Perkiraan:** q7 giliran 1 dari ±34 menjadi ±12–18 menit.

---

## Verifikasi bersama

**Verifikasi butir 2–7:**
- suite orc, sandbox dan Governor hijau;
- golden test ulang 6 item 06b, dengan target:
  - q7 giliran 1 ≤ 15 menit;
  - waktu tindak lanjut penolakan ≤ 5% waktu model (sekarang 18%);
  - nol `tool_not_in_step`;
  - h_add t2 dan threshold t2/t3 lolos;
  - median panggilan per putaran turun ≥ 30%;
  - "BBRI" ditanya balik.
