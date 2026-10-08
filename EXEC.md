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
- 2026-10-07, sesudah batch B dan pemeriksaan read-only aturan yang menolak atau memaksa langkah AI: M102 dan M103
  "siap2 uji ya —> masuk EXEC"; prinsip penilaian (teks verbatim di EXEC-D); lalu "okay, untuk both points. masukan exec
  untuk point no 2. jalanakn exec untuk point no 2, kemudian ujibulang yg ada di exec existing. lakukan inspeksi
  arsitektur sebelum buat implementation plan". Pilihan: cakupan "Rekomendasi + P-g (Recommended)", pencatatan prinsip
  "EXEC.md + AGENTS.md (Recommended)". Rencana implementasi disetujui (2026-10-07) → EXEC-D.
- Gelombang: 1 = EXEC-1 + EXEC-S; 2 = EXEC-E + EXEC-R + EXEC-P2; 3 = EXEC-3 + EXEC-A + EXEC-T; 4 = EXEC-C +
  EXEC-P5 + EXEC-P1, lalu golden test akhir.
- 2026-10-07, sesudah review `HANDOFF_M109_M110.md` dan pemeriksaan log M110 (read-only):
  - M109: "M109 OK untuk perbaikan plan. Masukan ke EXEC." → EXEC-M109.
  - M110: "Ini bukan hanya kalau dia research ya, kalau analisis juga.. Idealnya kalau untuk menjawab pertanyaan user
    bisa menggunakan 1 data, dan data tinggal di tweak parameter sesuai request variasi user, maka tidak perlu lagi
    request data. Dan kalau bisa dilakukan disandbox yang sama. Masukan ini ke EXEC. Masukan plan B ke EXEC juga." dan
    "Berlaku untuk semuanya yang applicable." → EXEC-V.
  - Pilihan user: variasi di pesan berikutnya "Ya, ikut (Recommended)"; M109 "Ya, masukkan juga (Recommended)"; golden
    test "Tulis suite saja (Recommended)".
  - Sesudahnya: "review EXEC yang sudah saya setujui dan inspect current architecture, ensuring implementation plan tidak
    mengganggu hal yang lain. Siapkan 2 golden test untuk ini (1 research, 1 analysis)". Rencana implementasi EXEC-V dan
    EXEC-M109 diajukan setelah review itu; belum ada perubahan kode.

## Ringkasan

**Berjalan (2026-10-07):** EXEC-V (M110 + opsi B) dan EXEC-M109, rencana implementasi 4 tahap disetujui. Tahap 1
(V-a opsi B + EXEC-M109) dan tahap 2 (data sama walau nama beda; sandbox `0598a616`, orc `f43f627d`) ter-deploy;
tahap 3 (banyak eksperimen satu kebutuhan data) ter-deploy; golden test
`apps/orc-test-runner/suites/qa_variant_20261007.json` (tahap 4) hanya atas perintah user.

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
  - Sesudah batch A, sisa kredit USD 0,225 < USD 0,30, jadi uji berhenti dan dilaporkan. User menaikkan kredit dan
    memutuskan "No, q7 nanti saja. Lanjut batch B" (2026-10-07).
  - Batch B `ma-qa-20261007b` (orc `3d217256`, ±USD 0,15):
    - "BBRI" ditanya balik dalam 5,3 dtk;
    - bakrie 140 dtk dengan 2 panggilan web;
    - p2 12 panggilan (06b 20), tanpa langkah mekanis dipanggil AI dan tanpa penolakan tambahan.
    EXEC-P5 lulus dan dihapus dari dokumen ini; rinciannya tetap di `GT_QA_2026-10-06.md` §9 dan M101.
  - Sesudah EXEC-D, uji ulang `ma-qa-20261007c` (2026-10-07, orc `63e29b62`, `GT_QA_2026-10-06.md` §10):
    - **EXEC-C lulus dan dihapus dari dokumen ini:** jelajah katalog di run lanjutan 0 (07a 4, 06b 4), nol
      penolakan untuk angka giliran sebelumnya, 10/10 run punya memori;
    - **EXEC-P1 lulus dan dihapus:** q7 giliran 1 6,6 menit dengan rencana menunggu, persetujuan menjalankan rencana
      tanpa usulan lanjutan yang tidak diminta;
    - target bersama "waktu sesudah penolakan ≤ 5%" tetap belum tercapai (7,5%; 07a+b 10,0%), menunggu keputusan
      user (Verifikasi bersama).
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
| 1d | EXEC-C: AI membawa semuanya ke run ID berikutnya dalam satu percakapan, tanpa terkecuali (13 butir, termasuk P4) | 2026-10-06 ("masukan exec"; "Seharusnya AI membawa semuanya tanpa terkecuali. Masukan EXEC") | Selesai 2026-10-07: lulus di uji ulang `ma-qa-20261007c` (jelajah katalog lanjutan 4 → 0, memori 10/10; M94, M95, M106) | — |
| 1e | EXEC-A: penyelarasan jalur (satu pembaca maksud, gerbang hanya meminta alat yang ada, 10.6 dan edit sama di semua jalur) | 2026-10-06 ("masukan exec") | Selesai 2026-10-06 (gelombang 3; P40) | — |
| 1h | EXEC-P1: mode 4 berhenti setelah analisis + rencana | 2026-10-06 ("p1 … masukan exec") | Selesai 2026-10-07: lulus di `ma-qa-20261007c` (q7 6,6 menit; persetujuan menjalankan rencana tanpa usulan; M92, M104) | — |
| 1i | EXEC-P5: gabung langkah mekanis | 2026-10-06 ("p5 masukan exec") | Selesai 2026-10-07: lulus di batch B (p2 20 → 12 panggilan, tanpa penolakan tambahan; M101) | — |
| 1j | EXEC-T: perangkat alat per proses (matriks HARUS/BOLEH/TIDAK BOLEH final, alat terlarang dikunci kode dan tidak bisa ditemukan) | 2026-10-06 ("finalize dan masukan ke EXEC"; catatan user: alat TIDAK BOLEH dikunci kode, tidak boleh ditemukan lewat pencarian) | Selesai 2026-10-06 kecuali butir 3 (keputusan terbuka, `FUTURE_PLAN.md` 3b; P41) | — |
| 2 | P3: gerbang yang salah tolak | 2026-10-06 "OK masukan plan jangan execute dulu" | Selesai 2026-10-06 (P3a EXEC-1, P3b dan P3c gelombang 3, P3d EXEC-R) | — |
| 3 | Item 11: penyortir "free will", jalur TANYA BALIK, cadangan berupa pertanyaan | 2026-10-05 (16:47, 17:40, 17:51, 17:55), ditegaskan 2026-10-06; **EXEC 2026-10-06** | Selesai 2026-10-06 (EXEC-3, gelombang 3; M97) | — |
| 4 | P2: jawaban ditulis sekali | 2026-10-06 | Selesai 2026-10-06 (EXEC-R dan EXEC-P2, gelombang 2) | — |
| 5 | P1: mode 4 berhenti setelah analisis + rencana | 2026-10-06 | EXEC-P1 | — |
| 6 | P5: gabung langkah mekanis | 2026-10-06 | Selesai 2026-10-07 (EXEC-P5) | — |
| 7 | P4: hasil jelajah dibawa antar-putaran | 2026-10-06 | Masuk EXEC-C (butir 1d) | — |
| 8 | EXEC-D: AI dinamis tetapi dibatasi (prinsip penilaian; M104, M105, P-a/b/c/e/f/g/h, uji ulang M102/M103) | 2026-10-07 ("masukan exec untuk point no 2. jalanakn exec untuk point no 2"; cakupan "Rekomendasi + P-g (Recommended)") | Live di dev 2026-10-07 (orc `63e29b62`); uji ulang `ma-qa-20261007c` lulus kecuali M102 sebagian (M110); cacat baru M109, M110 menunggu keputusan | — |

Biaya model: setiap uji dan golden test. Sisa batas kunci OpenRouter setelah gelombang 3: USD 0,857 (2026-10-06;
benchmark router ±0,07 dan uji `ma-qa-20261006f` ±0,197), jadi kredit dicek sebelum uji apa pun. Sesudah batch A gelombang 4 (2026-10-07): USD 0,225.
Status **EXEC** = rencana eksekusi sudah disetujui isinya, tetapi **baru dijalankan setelah user memberi konfirmasi
mulai** (keputusan user 2026-10-06: "EXEC dijalankan setelah konfirmasi saya"). Konfirmasi mulai diberikan 2026-10-06 ("mulai"). Setelah dimulai, berhenti dan lapor bila menemui kondisi berhenti, atau bila perlu tindakan di
luar langkah ini.

Urutan sisa:
- batch B: selesai 2026-10-07 (keputusan user "No, q7 nanti saja. Lanjut batch B"); EXEC-P5 lulus;
- EXEC-D (2026-10-07): kode live, uji ulang `ma-qa-20261007c` selesai; EXEC-C dan EXEC-P1 lulus dan dihapus;
- keputusan user yang menunggu: M109 (pertanyaan router diganti pertanyaan baku), M110 (model membuka semua sesi
  sebelum menjalankan kode), dan target bersama waktu sesudah penolakan ≤ 5% (7,5%);
- bila keduanya diputuskan, EXEC-D dihapus dari dokumen ini.

---

### EXEC-D: AI dinamis tetapi dibatasi (prinsip penilaian; M104, M105, uji ulang M102/M103)

**Keputusan user 2026-10-07 (kata-kata user):**
- M102 dan M103: "siap2 uji ya —> masuk EXEC".
- "okay, untuk both points. masukan exec untuk point no 2. jalanakn exec untuk point no 2, kemudian ujibulang yg ada di
  exec existing. lakukan inspeksi arsitektur sebelum buat implementation plan".
- Cakupan: "Rekomendasi + P-g (Recommended)" (P-a, P-b, P-c, P-e, P-f, P-h, ditambah P-g; P-d ke `FUTURE_PLAN.md`).
- Pencatatan prinsip: "EXEC.md + AGENTS.md (Recommended)".
- Rencana implementasi disetujui 2026-10-07 (sesudah inspeksi arsitektur read-only).

**Prinsip penilaian (verbatim dari user):**

> PRINSIP PENILAIAN (keputusan user 2026-10-06, EXEC.md "kenapa gak serahkan ke model saja?"): AI harus dinamis tetapi
> dibatasi. Penilaian (maksud user, jalur, kapan bertanya balik, isi pertanyaan, nilai desain) diserahkan ke model.
> Kode hanya untuk JAMINAN: alat terkunci per langkah; data hanya sesudah persetujuan; setiap angka bersumber; kunci
> ambang/horizon; peta pilihan → jalur; pertanyaan baku saat model gagal; maksimal dua pertanyaan berturut-turut.
> Prinsip tambahan user 2026-10-07: model SELALU boleh bertanya balik bila maksud user ambigu, di jalur mana pun.
> Larangan bertanya balik dianggap cacat kecuali ada alasan jaminan yang jelas. Kriteria untuk setiap aturan di kode:
> 1. Apakah aturan ini melindungi data, biaya, atau kebenaran angka? Bila ya, JAMINAN: tetap di kode. 2. Apakah aturan
> ini menebak maksud user atau memaksa satu jenis jawaban? Bila ya, PENILAIAN: pindah ke model. 3. Bila model salah
> menilai, adakah jalan keluar "tanya balik"? Bila tidak ada, tambahkan. 4. Apakah ada tes yang mengunci aturan ini,
> dan apakah tes itu harus diubah?

**Bukti (golden test `ma-qa-20261007a`, log + kode):** q7 giliran 2 dibaca CANCEL oleh penyortir balasan rencana;
model ingin bertanya balik, tetapi giliran CANCEL hanya boleh ANSWER/LIMITATION tanpa alat, dan angka "10" dipaksa
jadi LIMITATION (M104). Akarnya M105: balasan untuk rencana yang dibuat langkah B mode 4 (`-m4b`) jatuh ke mode 1,
karena `is_mode4_plan` hanya mengenali `-m4d`.

**Butir (semua di orc; tanpa saklar baru, tanpa migration, tanpa variabel Railway):**
- **P-b (M105):** balasan untuk rencana yang diterbitkan langkah mode 4 mana pun (B, C, D, lanjutan; akhiran `-m4b`,
  `-m4c`, `-m4d`, `-m4n`) tetap di mode 4. Rencana v2 dibaca router giliran mode 4 (bisa bertanya balik). Rencana v1
  (rencana hipotesis) tetap dibaca penyortir balasan rencana, dan kini membawa data record.
- **P-a:** giliran CANCEL boleh mengembalikan CLARIFICATION (satu pertanyaan) bila pesan user tidak jelas membatalkan
  atau meminta hal lain; alat tetap kosong. Rencana tetap menunggu (token dan kedaluwarsa sama). Pertanyaan itu diakhiri
  kalimat tetap "Rencana riset masih menunggu: balas setuju, ubah, atau batal.", yang dihitung kode: sesudah dua
  pertanyaan berturut-turut, CLARIFICATION tidak ditawarkan lagi (jaminan "maksimal dua pertanyaan berturut-turut").
- **P-c:** penyortir balasan rencana: CANCEL hanya untuk penolakan yang jelas; balasan yang tidak jelas, pertanyaan, atau
  permintaan hal lain menjadi UNRELATED (ditanya balik). "Jangan pernah APPROVE bila ragu" tetap. Benchmark baru
  `scripts/benchmark_plan_reply.py` sebelum deploy; router giliran `--ask-back` diulang sebagai regresi.
- **P-e:** catatan gate menyebut jalan tanya balik, hanya bila CLARIFICATION boleh di giliran itu.
- **P-f:** giliran tanpa alat tetap mendapat satu kesempatan menyunting untuk gate yang perbaikannya berupa sunting teks
  (PROVENANCE, TYPED_FIGURES, DEFINITION, METHODOLOGY, METHODOLOGY_PROVENANCE, REFERENCE); anggaran yang habis tetap
  mengunci.
- **P-g:** beda kata pada `hypothesis`/`objective` (teks deskriptif) diselaraskan ke teks yang disetujui, tidak lagi
  RESEARCH_PLAN_MISMATCH; `condition`, `outcome`, `baseline`, ambang, horizon dan batas "lebih ketat saja" tetap persis.
- **P-h (M106):** data record menyimpan `subject` dan `relationships` setiap data need, dan catatan untuk AI
  menampilkannya, supaya run berikutnya tidak membaca ulang katalog untuk fakta yang sama.

**Uji ulang (`ma-qa-20261007c`, ±USD 0,7; kredit dicek ≥ USD 0,30 sebelum benchmark dan uji):**
- q7 (3 giliran: pertanyaan q7, "lanjutkan saran riset berikutnya", "setuju, jalankan rencananya"): EXEC-P1, EXEC-C,
  M104, M105, P-a/b/c;
- variant_bbca (2 giliran, sama dengan 07a): M102, P-g;
- threshold_from_result (3 giliran, sama dengan 07a): EXEC-C, P-h, EXEC-P5;
- cancel_plan (baru, 2 giliran: rencana uji BBRI 5 hari, lalu "tidak usah, batalkan rencana uji 5 hari itu"): M103,
  P-a.

**Lulus bila:**
- q7 giliran 2/3 berjalan di mode 4 (router giliran), giliran 2 tidak dipaksa LIMITATION, dan hasilnya salah satu dari:
  ditanya balik dengan rencana tetap menunggu, CONTINUE dengan rencana baru, atau APPROVE;
- q7 giliran 1 ≤ 15 menit dengan rencana menunggu; "setuju, jalankan rencananya" menjalankan rencana tanpa usulan
  lanjutan yang tidak diminta;
- EXEC-C: Asumsi/Batasan/Metodologi utuh di giliran berikutnya, nol penolakan PROVENANCE/REFERENCE untuk angka giliran
  sebelumnya, setiap run punya memori; bacaan katalog di run lanjutan (langkah B/C mode 4, giliran 2 dan
  seterusnya) lebih sedikit dari 07a (4 panggilan);
- M102: nol sesi yang saling menutup; M103: jawaban batal selesai tanpa PROVENANCE yang memaksa;
- P-g: nol RESEARCH_PLAN_MISMATCH karena hypothesis/objective;
- nol `tool_not_in_step`; waktu sesudah penolakan dilaporkan terhadap target ≤ 5%.

**Jalan balik:** redeploy orc `3d217256` atau revert commit EXEC-D.

**Hasil (2026-10-07):**
- **Deploy:** orc `63e29b62` SUCCESS (kode `c07f9b0`).
- **Benchmark pembaca balasan rencana:** 36/36. Instruksi lama membaca "lanjutkan saran riset berikutnya" sebagai BATAL
  2/2, instruksi baru UNRELATED 2/2.
- **Router giliran:** 49/50, 0 baca ke riset, 0 ditanya balik.
- **Uji ulang `ma-qa-20261007c` (±USD 0,50):** rinciannya di `GT_QA_2026-10-06.md` §10.
  - Lulus: M105, M104 (dibaca SETUJU di mode 4), M103, M106, P-g (0 MISMATCH) dan nol alat di luar meja.
  - M102 sebagian: buka otomatis sudah benar, tetapi model sendiri membuka 3 sesi berturut-turut, sehingga 4 sesi
    tertutup (M110, baru).
  - Tidak terpicu live (dibuktikan tes unit): P-a (giliran BATAL bertanya) dan P-f.
  - Cacat baru: M109 (pertanyaan router diganti pertanyaan baku saat pilihannya satu jalur).
- **Perbedaan dari kata-kata rencana (R35):**
  - q7 giliran 3 tidak menjalankan rencana karena giliran 2 sudah menjalankannya: router membaca kalimat 06b sebagai
    persetujuan, yang termasuk hasil sah di syarat lulus.
  - Sebelum menulis syarat EXEC-D, data 07a dicek ulang. Bacaan katalog threshold giliran 2/3 sudah 0 di 07a, jadi
    syaratnya diganti menjadi total bacaan katalog di run lanjutan (07a 4).
  - Uji pembanding instruksi lama di benchmark (±USD 0,008) ditambahkan untuk bukti sebelum/sesudah.

### EXEC-V: satu data untuk semua variasi, di ruang kerja yang sama (M110 + opsi B)

**Keputusan user 2026-10-07 (kata-kata user):**
- "Ini bukan hanya kalau dia research ya, kalau analisis juga.. Idealnya kalau untuk menjawab pertanyaan user bisa
  menggunakan 1 data, dan data tinggal di tweak parameter sesuai request variasi user, maka tidak perlu lagi request
  data. Dan kalau bisa dilakukan disandbox yang sama. Masukan ini ke EXEC. Masukan plan B ke EXEC juga."
- "Berlaku untuk semuanya yang applicable."
- Variasi di pesan berikutnya ikut aturan yang sama: "Ya, ikut (Recommended)".
- Sesudah review EXEC dan inspeksi arsitektur (2026-10-07): riset di pesan lanjutan "Data dipakai ulang, ruang kerja
  baru (Recommended)"; urutan "Setuju, susun rencana implementasi (Recommended)"; rencana implementasi 4 tahap disetujui
  (persetujuan rencana = mulai tahap 1–3 di dev; golden test tahap 4 hanya atas perintah user).

**Temuan inspeksi (read-only, `main` `08d6c94`):**
1. **Penggunaan ulang paket data gagal karena nama.**
   - Alur penggunaan ulang sudah ada (`data_planner.prepare` → sandbox `reuse_bundle`).
   - Identitas data (`data_contract_sha256`, `contract_covers` di `apps/market-python-sandbox/app/data_need.py`)
     memasukkan `data_request_id`, dan id wajib diawali `request_group_id`.
   - Data identik dari grup berbeda selalu dianggap berbeda. Di BBCA ada 4 ekstraksi.
2. **Riset multi-sudut sudah menggabungkan data yang sama** ke satu spec dan satu ruang kerja
   (`research_planner._merge`). Itu pola acuan.
3. **Temuan riset v1 sudah per hipotesis** (`research_events_<hypothesis_id>`; orc mengulang temuan per penyelesaian),
   tetapi satu ruang kerja hanya membawa satu set nilai rencana (`_FINDINGS_V1`, `research_governance._constraints`).
4. **Kebutuhan data riset selalu mendapat ruang kerja baru.** Jaminan isolasi ini tetap (keputusan user).
5. **Opsi B melengkapi M102 dan EXEC-P5.** `_one_open_session` menutup sesi yang belum dipakai tanpa memberi tahu AI.

**Benchmark eksternal:**
- pesan galat menyebut langkah berikutnya ([Anthropic, Writing effective tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents));
- muat data sekali, jalankan semua variasi ([BacktestVariationRunner](https://kaxanuk-backtest-engine.readthedocs-hosted.com/en/latest/api_reference/backtest/orchestrators.html), [vectorbt](https://vectorbt.pro/getting-started)).

**Rencana implementasi (disetujui 2026-10-07):**

| Tahap | Isi | Layanan |
|---|---|---|
| 1 | V-a opsi B + EXEC-M109 | orc |
| 2 | V-c / V-d: identitas data tanpa nama permintaan; paket dipakai ulang lewat alias nama, di pesan yang sama dan pesan lanjutan (riset: data dipakai ulang, ruang kerja baru) | sandbox + orc |
| 3 | V-b: `research_experiments` (1–4 eksperimen satu kebutuhan data), temuan per eksperimen, dikunci kapabilitas sandbox `research_multi_experiment`, Tool_Catalog round baru | orc + sandbox + migrasi |
| 4 | golden test `qa_variant_20261007.json`, hanya atas perintah user | runner |

**Tahap 4 diperintahkan 2026-10-07:** "go ahead on stage 4." Sebelum uji:
- `expect` riset giliran 4 diperbarui ("data dipakai ulang, ruang kerja baru"); prefix `ma-qa-variant-20261007a`.
- Perbandingan dengan yang ter-deploy: EXEC-D, EXEC-V tahap 1–3 dan EXEC-M109 semuanya ter-deploy di dev. Butir
  `PLAN.md` 8–12 (disetujui, belum punya rencana eksekusi) belum dibangun dan bukan bagian uji ini.
- Kredit OpenRouter: sisa USD 1,529 (≥ 0,30).

**Hasil tahap 4 (golden test `ma-qa-variant-20261007a`, runner `150c16a5`, orc `9c6f5abf`, sandbox `6e396414`,
±USD 0,38, sisa USD 1,147):**
- **Lulus:** riset giliran 4 (varian 2,5x) memakai ulang data (`bundle_reused`) di ruang kerja baru, 2 eksperimen
  dalam 1 kebutuhan data dan 1 sesi, 2 temuan, 3 iterasi, 148 dtk. Giliran 1 dan 3 mengembalikan rencana (giliran 3
  rencana revisi). BBRI giliran 1: satu tabel berkolom varian, 10 iterasi. `analysis_sessions_superseded` = 0. M109
  tidak terpicu.
- **Gagal:** riset giliran 2 LIMITED, 925 dtk, 29 iterasi, 36 panggilan. 913 dtk adalah waktu model; eksekusi
  ruang kerja ±1,3 dtk. Keempat uji selesai di sandbox pada 17:14:11 (2 menit setelah mulai, `cmp_f4171f61`
  COMPLETED, 29 keluaran), lalu 20 putaran sisanya habis untuk pemulihan dari M111–M114. BBRI giliran 2 mengekstrak
  ulang data yang sama (M113).
- Rincian dan akar masalah: `ERRORS_AND_SOLUTIONS.md` M111–M114.

**Keputusan user 2026-10-08 (setelah golden test):** "kita revert saja ya, ruang kerja boleh dipakai oleh AI maks 4,
membuka 1 tidak menutup yang lain. data tetap as is, apabila sama maka tidak perlu ditarik ulang, tapi boleh dipakai
di ruang kerja lain." Lalu: "revert ke banyak ruang kerja, dan data yang sama maka tidak perlu ditarik lagi. data yg
sama bisa di proses di sandbox lain." Belum dijalankan; rencana eksekusi menunggu jawaban atas pertanyaan terbuka.

**Keputusan user 2026-10-08 (lanjutan):**
- M114 ("babak 2"): "Ok untuk usulan perbaikan babak 2. Masukan exec." Perbaikan: di pesan yang sama, eksekusi setelah
  penyelesaian yang lulus tetap di babaknya (hasil yang sudah selesai tidak hilang, tambahan ikut dirilis saat
  diselesaikan lagi); babak baru hanya untuk pesan berikutnya.
- Slot sandbox: "Ya naikan ke 4." (`PY_SANDBOX_MAX_SESSIONS` 2 → 4, maksimum kode). Diminta: cek aturan yang menutup
  ruang kerja otomatis.
- Masih terbuka: tahap 3 (pertanyaan diperjelas), opsi M113 (dengan benchmark).
- Persetujuan ini untuk rencana; eksekusi menunggu konfirmasi "go".

**Keputusan user 2026-10-08 (lanjutan 2):**
- Aturan yang menutup ruang kerja: "Harus diubah agar 'membuka satu tidak menutup yang lain'. Ok masukan exec terkait
  ini." Yang diubah:
  - A (orc `_one_open_session`, S08): membuka ruang kerja baru tidak lagi menutup ruang kerja run ini yang belum selesai.
  - B (orc, tahap 1 opsi B): penolakan pembukaan selama ada ruang kerja belum dipakai/belum diselesaikan dicabut.
  - C (orc `_merged_steps`, M102 + tahap 1): ruang kerja tetap dibuka otomatis setelah data siap selama di bawah batas;
    `COMPLETE_OPEN_SESSION_FIRST` dicabut.
  - D (sandbox `_take_slot`): ruang kerja run ini yang belum selesai tidak ditutup (`REPLACED_IN_REQUEST` dicabut);
    pembukaan di atas batas ditolak dengan pesan jelas.
  - Turunan yang diperlukan: AI diberi tahu batasnya (deskripsi `open_analysis_session` dan prompt: sampai 4 ruang kerja
    per jawaban, membuka satu tidak menutup yang lain, data yang sama dipakai ulang di ruang kerja lain), dan penolakan
    ke-5 menyebut ruang kerja yang terbuka beserta langkah berikutnya (pakai, selesaikan, atau tutup salah satu). Teks
    "one session of a request is open at a time" dihapus dari semua pesan.
  - Tetap: idle 15 menit, umur 1 jam, proses mati, restart, pelepasan di akhir jawaban, penggusuran ruang kerja WARM_IDLE
    percakapan lain bila slot penuh, kelompok riset multi-sudut satu per satu.
- Tahap 3: "Tahap 3 we'll go with opsi B." Dicabut: satu uji = satu kebutuhan data = satu ruang kerja (kapabilitas
  `research_multi_experiment` dimatikan, `research_experiments` tidak ditawarkan; Tool_Catalog round baru untuk
  `submit_data_need_spec` tanpa field itu). Data yang sama tetap tidak ditarik ulang (tahap 2) dan boleh dipakai di
  ruang kerja lain.
- M113: penjelasan cara backend mendeteksi data yang sama diminta; opsi belum dipilih.

**Keputusan user 2026-10-08 (lanjutan 3):**
- M113: opsi A ditolak ("rekomendasi kamu flawer dan hanya menunda masalah"). Dicek: BBRI giliran 2 menjalankan SQL
  yang identik (`query_hash` `4719e446…`, `part_key` sama) dengan giliran 1. Dipilih **opsi D, versi (i)**: "okay we ll
  to with (i) we need to ensure AI aware of this process as well dan penolakan apabila ada harus jelas. masukan exec".
  - Identitas data = SQL yang dijalankan Governor (bentuk kanonik, tanpa label dan tanpa LIMIT).
  - Versi data (i): SQL sama, rentang berakhir sebelum hari ini, paket masih berlaku (belum kedaluwarsa).
  - Cakupan: "Satu percakapan (Recommended)".
  - AI tahu prosesnya (prompt dan deskripsi alat), dan setiap potongan yang tidak dipakai ulang membawa alasan yang
    jelas di hasil `prepare_data_bundle`.
- Idle: "Aktivitas satu jawaban (Recommended)": aktivitas di salah satu ruang kerja jawaban menjaga semua ruang kerja
  jawaban itu tetap hidup.
- M111/M112: "keluarkan dari exec" (tetap OPEN di `ERRORS_AND_SOLUTIONS.md`).
- Rencana implementasi disetujui 2026-10-08 (persetujuan rencana = mulai tahap 1–4 di dev, berurutan; golden test
  tahap 5 hanya atas perintah user):

| Tahap | Isi | Layanan |
|---|---|---|
| 1 | Cabut tahap 3 (`research_experiments`, kapabilitas `research_multi_experiment`); migrasi `20261007_001` tetap sebagai riwayat | sandbox + orc |
| 2 | Banyak ruang kerja: batas per jawaban dari `/v1/runtime` (`PY_SANDBOX_MAX_SESSIONS_PER_REQUEST`), penolakan ke-5 `SESSION_LIMIT_PER_REQUEST`/`ANALYSIS_SESSION_LIMIT` berisi daftar ruang kerja dan langkah berikutnya, `REPLACED_IN_REQUEST`/superseded/`OPEN_SESSION_FIRST` dicabut, idle per jawaban; M114 (babak tetap di pesan yang sama); `PY_SANDBOX_MAX_SESSIONS=4` setelah cek memori | sandbox + orc + variabel |
| 3 | Opsi D: Governor `data_sha256` (SQL kanonik tanpa LIMIT) di estimasi dan ekstraksi; sandbox `POST /v1/parts/lookup` (alasan `RANGE_INCLUDES_TODAY`, `EXPIRED`, `NOT_EXTRACTED_IN_CONVERSATION`, `CATALOG_CHANGED`) dan bagian `reuse_of` (file dipakai ulang, cek lineage pada bidang data); mesin alias tahap 2 dicabut; planner orc memakai lookup, hasil menyebut potongan dipakai ulang/diekstrak beserta alasannya | Governor + sandbox + orc |
| 4 | Tool_Catalog round_m, `AI_TOOLS.md`, README, changelog; deploy Governor → sandbox → variabel → migrasi → orc | semua |
| 5 | Golden test, hanya atas perintah user | runner |

**Hasil revisi 2026-10-08 (tahap 0–4 selesai di dev; tahap 5 menunggu perintah user):**
- Deploy: Governor `ad4da9bb` (`main` `4cfbe06`), sandbox `ce18b33c` dan orc `6a0ebf8f` (`main` `92884b6`), semuanya
  `SUCCESS`; `PY_SANDBOX_MAX_SESSIONS=4` (batas container 24 GB / 24 vCPU, cukup untuk 4 × 4096 MB); migrasi
  `20261008_001` (round M) diterapkan dan dibaca balik. `/v1/runtime` live: `session_release` v2 (`max_sessions` 4,
  `max_sessions_per_request` 4), `part_reuse` v1, `research_multi_experiment` tidak ada lagi.
- Tes: Governor 269 lulus (dengan PostgreSQL lokal), sandbox 800 lulus, orc 1.301 lulus (tes PostgreSQL orc dilewati:
  butuh role khusus yang tidak ada di lingkungan lokal).
- Rincian teknis: `RAILWAY_CHANGELOG.md`, `DATABASE_CHANGELOG.md`, `ERRORS_AND_SOLUTIONS.md` M110, M113–M115.

**Perbedaan dari rencana (keputusan teknis saat membangun, dicatat untuk review user):**
1. Batas ruang kerja dijaga satu tempat saja, di sandbox (`SESSION_LIMIT_PER_REQUEST`). Orc tidak menghitung sendiri
   (tidak ada kode `ANALYSIS_SESSION_LIMIT`); orc hanya membaca angka batas dari `/v1/runtime` untuk deskripsi alat.
2. Jalan keluar baru untuk AI: `open_analysis_session` menerima `close_session_id`. Bila ditolak karena sudah 4, AI boleh
   memilih sendiri menutup salah satu ruang kerjanya yang sudah selesai atau tidak dipakai, lalu membuka yang baru.
   Backend tidak pernah menutup ruang kerja secara otomatis (prinsip EXEC-D: selalu ada jalan keluar).
3. Ruang kerja yang sudah diselesaikan tetap terbuka (ACTIVE) sampai jawaban selesai, baru menjadi WARM_IDLE. Ini perlu
   agar membuka ruang kerja lain tidak menggusurnya, dan agar perbaikan M114 berlaku.
4. Identitas data (`data_sha256`) tetap memuat nama kolom dan alias ukuran agregat, karena nama itu menjadi nama kolom
   di file. File dengan nama kolom lain tidak bisa dipakai apa adanya. Rencana awal menggantinya dengan posisi.
5. Prompt sistem tidak mendapat kalimat baru soal batas empat ruang kerja (batas ukuran prompt +2% sudah penuh). Angka
   "four" ada di deskripsi `open_analysis_session`. Kalimat CONVERSATION REUSE butir 2 ditulis ulang untuk aturan baru,
   dengan panjang yang sama.
6. Pemakaian ulang per potongan butuh hash dari estimasi, jadi planner selalu memakai preflight saat fitur ini aktif
   (di dev preflight memang sudah menyala).
7. Akibat aturan (i): data tanpa rentang tanggal (misalnya daftar saham per sektor) selalu diambil ulang
   (`NO_DATE_RANGE`), begitu juga rentang yang sampai hari ini (`RANGE_INCLUDES_TODAY`). Kasus BBRI giliran 2 hanya
   dipakai ulang bila rentangnya berakhir sebelum hari ini.
8. Bila sandbox menolak pemakaian ulang saat membangun paket (salinan lama kedaluwarsa di antara cek dan bangun),
   planner mengulang dengan ekstraksi biasa.
9. Ditemukan dan diperbaiki: tes janitor Governor gagal karena tanggal tetap di tes sudah terlewati (M115, cacat tes,
   bukan cacat kode).

**Uji end-to-end 2026-10-08 (perintah user: "run end to end to ensure this process works. flag any error. 2 GT"):**
- GT1 `ma-qa-variant-20261008a` (runner `16c929b9`, ±USD 0,15) dan GT2 `ma-qa-reuse-20261008a` (suite baru
  `apps/orc-test-runner/suites/qa_reuse_20261008.json`, runner `f2cf8210`, ±USD 0,05).
- Bekerja: riset GT1 giliran 4 membuka 2 ruang kerja sekaligus, keduanya COMPLETED, 6 event study dihitung ulang backend;
  tidak ada ruang kerja yang ditutup oleh pembukaan lain; setiap pengambilan data dicek dengan alasan jelas; GT2
  analisis giliran 2 memakai ulang data dan ruang kerja tanpa ekstraksi.
- Temuan: `ERRORS_AND_SOLUTIONS.md` M116–M120. M116 (hitungan BBCA = BMRI) dicek ke database: angkanya benar.

**Keputusan user 2026-10-08 (lanjutan 4), setelah uji end-to-end:**
- Sebelumnya (jawaban pertanyaan): "Tetap aturan (i) saja" untuk data sama di dalam satu jawaban. Diganti oleh user:
  "Data yang sama diambil dua kali dalam satu jawaban riset ... --> ambil jadi sekali saja --> masukan EXEC."
- **V-f (disetujui, belum dijalankan; menunggu "go"):** di dalam satu jawaban, data dengan SQL Governor yang sama diambil
  sekali saja, termasuk rentang yang sampai hari ini (waktu acuan sama untuk seluruh jawaban). Antar jawaban tetap
  aturan (i). Kasus GT1: riset giliran 4, dua uji (horizon 3 dan 10 hari) membaca data BBCA identik dan keduanya
  diekstrak, bersamaan, pada 03:34:09.
  - Lapisan: sandbox `lookup_parts` (pengecualian `RANGE_INCLUDES_TODAY` bila sumbernya dari request yang sama) dan
    planner orc (persiapan data dalam satu jawaban saling menunggu: potongan dengan `data_sha256` yang sedang diekstrak
    oleh kebutuhan lain di jawaban yang sama ditunggu lalu dipakai ulang, tidak diekstrak paralel).
  - Pertanyaan terbuka: tidak ada; detail teknis diputuskan saat rencana eksekusi.
- **V-g (disetujui, belum dijalankan):** "Satu jalur pemakaian ulang belum teruji langsung, yaitu data yang sama dengan
  label permintaan berbeda ... --> siapkan GT, masukan EXEC." Suite disiapkan:
  `apps/orc-test-runner/suites/qa_relabel_20261008.json` (rentang masa lalu; giliran berikutnya meminta data yang
  sama lewat pertanyaan lain sehingga model menulis kebutuhan data baru dengan label lain). Lulus bila log sandbox
  `parts_looked_up matched>0` dan `bundle_built parts_reused>0` dengan sumber kebutuhan berlabel lain. Dijalankan hanya
  atas perintah user; sebaiknya setelah V-f dan perbaikan M117 (riset dengan "naik" sekarang terhenti, M117).

**Hasil tahap 1 (2026-10-07, V-a opsi B):**
- **Kode** (`d25e108`, `apps/market-ai-orc/app/orchestrator.py`):
  - `_one_open_session` menolak pembukaan paket lain dengan `ANALYSIS_SESSION_ALREADY_OPEN` selama sesi run ini belum
    selesai dan belum punya eksekusi OK. Pesannya menyebut sesi dan paketnya (`open_session_id`, `open_bundle_id`); log
    `analysis_session_open_refused`.
  - Pembukaan ulang paket yang sama tetap boleh. Sesi yang tertutup karenanya disebut di hasil alat
    (`superseded_sessions`, `superseded_note`), tidak lagi diam-diam.
  - `_merged_steps`: paket yang siap saat ada sesi tertunda mendapat `next_action` `COMPLETE_OPEN_SESSION_FIRST` dengan
    id sesi itu.
- **Tes:** orc 1.296 lulus, 223 dilewati (baseline 1.293). Tes baru: paket lain ditolak tanpa sesi tertutup; paket sama
  boleh dan penutupannya disebut; prepare saat sesi tertunda menunjuk sesi itu.
- **Deploy:** orc `e6ab80c3` SUCCESS (kode `d25e108`); log startup sama seperti sebelumnya (`run_memory_active`,
  `mode4_active`, `ai_mode_selected` 4, model 1, `/ready` 200). Sandbox tidak berubah. Jalan balik: orc `63e29b62`.
- **Uji live:** ikut golden test tahap 4.

**Hasil tahap 2 (2026-10-07, V-c / V-d: data yang sama dikenali walau namanya beda):**
- **Kode sandbox** (`9805b63`):
  - `data_need.contract_alias(earlier, later)` memasangkan permintaan berdasarkan isinya (tabel, scope, restriksi,
    jendela tanpa `range_id`, frekuensi, buffer, urutan, versi katalog, kolom boleh lebih lebar) dan memeriksa relasi
    antar pasangan. Hasilnya peta id lama → id, nama logis dan id rentang baru; `{}` bila semua nama sama.
    `contract_covers` = selisih dari `contract_alias`.
  - Binding menyimpan alias (`bundle_bindings.aliases`, skema store SQLite versi 5).
    `data_need.aliased_manifest` mengganti nama di manifest (dataset, rentang, kualitas, cakupan, relasi) untuk
    kebutuhan data yang dilayani; file, baris, checksum dan id paket tetap. Hasil reuse, sesi (`session.json`: `load`,
    `load_range`, view SQL, event study, backtest), `inspect_dataset`, input audit dan cek cakupan penyelesaian memakai
    tampilan ini.
  - Ruang kerja hangat hanya dipasang ulang bila nama sama; dengan nama lain dibuka worker baru pada file yang sama
    (tanpa ekstraksi).
  - Beberapa kebutuhan data dalam satu pesan yang berbagi satu paket dilayani berurutan: yang pertama tanpa hasil
    COMPLETED (kebutuhan data milik paket lebih dulu).
- **Kode orc** (`6d28f26`): aturan CONVERSATION REUSE 2 menyebut data yang sama dikenali dari isinya, apa pun namanya;
  teks lama "submit the listed data_need_spec unchanged (any request_group_id …)" tidak pernah bisa dipakai ulang karena
  id wajib diawali id grup. Tes prompt (`test_prompt_pass2.py`) mencatat kalimat yang berubah; panjang prompt tetap di
  bawah batas +2%.
- **Tes:** sandbox 799 lulus (baru: `tests/test_same_data_other_labels.py`, 7 tes: pasangan berdasarkan isi, data lain
  tidak dipasangkan (jendela, scope, kolom kurang, relasi, point-in-time, jumlah permintaan), kebutuhan lebih sempit
  dilayani, manifest diganti nama tanpa mengubah file, pesan lanjutan dengan nama lain → paket sama di sesi baru dan
  COMPLETED, dua kebutuhan data satu pesan dilayani berurutan, riset dengan nama lain → event study dan verdict di paket
  yang dipakai ulang). Orc 1.297 lulus.
- **Deploy:** sandbox `0598a616` SUCCESS (log startup bersih), lalu orc `f43f627d` SUCCESS (log startup sama). Jalan
  balik: sandbox `d56eea1a`, orc `e6ab80c3`. Kode lama tetap bisa membaca store versi 5 (kolom baru nullable).
- **Perbedaan dari kata-kata rencana (R35):**
  - `data_contract_sha256` tidak diubah menjadi bebas-nama. Sidik yang tersimpan tetap (audit, paket lama, draf dan
    rencana riset yang ditandatangani tidak berubah); pencocokan bebas-nama dikerjakan `contract_alias` untuk setiap
    paket percakapan. Rencana memang mengizinkan "sidik lama tetap".
  - Ruang kerja hangat tidak dipasang ulang untuk nama berbeda (worker baru pada file yang sama), karena variabel dan
    view worker lama memakai nama lama.
  - Versi skema store tidak bisa dibaca langsung dari container (Railway SSH butuh kunci yang tidak ada di sesi ini);
    upgrade berjalan di konstruktor store dan startup selesai tanpa galat.
  - `AI_TOOLS.md` dan Tool_Catalog tidak berubah: tidak ada deskripsi alat yang berubah.

**Hasil tahap 3 (2026-10-07, V-b: banyak eksperimen dalam satu kebutuhan data dan satu ruang kerja):**
- **Kode sandbox** (`c131e48`):
  - `POST /v1/data-needs` menerima `research_experiments` (2–4 eksperimen satu rencana, `research_governance` kosong).
    Tiap eksperimen wajib punya nilai temuan v1, `hypothesis_id` tidak boleh ganda; tanpa temuan v1 ditolak
    `MULTI_EXPERIMENT_UNAVAILABLE`.
  - Research Governor (`review_experiments`): setiap eksperimen tetap dihitung satu eksperimen, dengan kunci (grup
    permintaan, hipotesis), untuk semua batas, revisi dan follow-up. Penolakan pertama menjadi keputusan dan menyebut
    hipotesisnya. Batasan yang disetujui menyimpan `experiments[]` per eksperimen dan anggaran komputasi per eksperimen.
  - Ruang kerja menerima nilai rencana tiap eksperimen; `event_summary(hypothesis_id=...)` memakai nilai hipotesis itu
    dan menolak hipotesis di luar daftar.
  - `complete_analysis` menilai tiap eksperimen dari `research_events_<hypothesis_id>` miliknya; COMPLETED hanya bila
    semua lengkap, pesan menyebut eksperimen yang belum. `final_status.research_findings` berisi satu temuan per
    eksperimen.
  - `/v1/runtime` melaporkan `research_multi_experiment: {enabled, version: 1, max_experiments: 4}`.
- **Kode orc** (`370d4a9`):
  - `submit_data_need_spec` mendapat `research_experiments` hanya bila sandbox melaporkan kapabilitas itu (tanpa itu
    field tidak ada: satu eksperimen per kebutuhan data, perilaku lama).
  - Setiap eksperimen dicocokkan dengan rencana yang disetujui (`match_governance`, P-g tetap); galat menyebut
    `research_experiments[i]`.
  - Pelacakan run dan audit riset mencatat satu baris per hipotesis.
  - Prompt: langkah 3 HYPOTHESIS PLAN ditambah kalimat "eksperimen dengan data yang sama berbagi satu kebutuhan data
    (`research_experiments`), `event_summary` tiap eksperimen di ruang kerja itu"; catatan varian menambah kalimat yang
    sama. Keduanya hanya muncul dengan kapabilitas.
- **Katalog:** migrasi `20261007_001_round_l_tool_catalog.sql` (`submit_data_need_spec` v10, tidak aktif) lewat job
  sementara `lmig-job`: DRYRUN `e6b58ee0` lulus dan di-rollback, APPLY `d69ef6b2`; dibaca balik 115 baris (dari 114),
  25 aktif tetap, jalankan kedua ditolak; job dihapus (17 layanan). `AI_TOOLS.md` dibuat ulang: tidak berubah (nama dan
  deskripsi alat sama).
- **Tes:** sandbox 804 lulus (baru `tests/test_research_experiments.py`: anggaran per eksperimen, revisi, sesi nyata
  dua eksperimen → INCOMPLETE menyebut yang kurang lalu COMPLETED dengan dua temuan, hipotesis di luar daftar ditolak,
  syarat 2–4 dan temuan v1). Orc 1.301 lulus (baru `tests/test_research_experiments.py`: daftar sampai ke sandbox,
  pencocokan per eksperimen, tanpa kapabilitas tidak ada field, prompt hanya dengan kapabilitas).
- **Deploy:** sandbox `6e396414` SUCCESS, lalu orc `9c6f5abf` SUCCESS (orc membaca kapabilitas saat startup; log tanpa `research_multi_experiment_inactive`). Jalan
  balik: sandbox `0598a616`, orc `f43f627d`; baris Tool_Catalog v10 tetap tidak aktif dan tidak dihapus.
- **Perbedaan dari kata-kata rencana (R35):**
  - Tool_Catalog hanya `submit_data_need_spec` v10: deskripsi `run_python` dan `complete_analysis` di orc tidak berubah,
    jadi tidak ada versi baru untuk keduanya.
  - Buku metode tidak diubah: kalimatnya ("each RESEARCH data need copies research_governance from its approved
    experiment"; "without event_summary for each hypothesis is not completed") tetap benar, dan perubahan akan memaksa
    migrasi hash buku metode di tiga tempat.
  - Push GitHub sempat gagal (HTTP 500 dari GitHub, 16:54–16:57 UTC); berhasil pada percobaan ulang tanpa perubahan.

**Bukti (golden test `ma-qa-20261007c` variant_bbca giliran 2, orc `63e29b62`, log dan penalaran AI):**
- Pertanyaan user punya 4 variasi (volume ≥ 2× dan ≥ 3×, horizon 3 dan 10 hari).
- 22 panggilan, 294 detik; ±45 detik untuk buka-tutup ruang kerja, ±1 menit untuk pengulangan data yang sama.
- Penalaran AI giliran 1: "The router says: one experiment or angle per variant or combination … So 4 experiments".
- Penalaran AI giliran 2: "The governance allows only one hypothesis per spec. So no [cannot combine]". Lalu, setelah 3
  pembukaan: "Session 1 got closed when I opened sessions 2-4? … sessions are exclusive".

**Akar masalah (terverifikasi dari log dan kode):**
1. **Satu eksperimen = satu kebutuhan data = satu ruang kerja.**
   - `VARIANT_NOTE` (`apps/market-ai-orc/app/orchestrator.py`) meminta satu eksperimen per varian.
   - Kontrak riset hanya membawa satu `hypothesis_id` per kebutuhan data:
     - `ResearchGovernance`, `app/tools/data_need.py`;
     - `match_governance`, `app/research_plan.py`;
     - sandbox `app/dataneed_service.py`: satu temuan per penyelesaian.
   - Akibatnya, data BBCA yang identik diajukan, diekstrak, dibuka dan diselesaikan 4 kali (4 paket data berbeda di
     log).
2. **Penutupan diam-diam dan petunjuk yang tidak lengkap.**
   - `_one_open_session` menutup ruang kerja lama yang belum dipakai tanpa memberi tahu AI.
   - Setelah paket data berikutnya disiapkan, petunjuknya hanya "buka ruang kerja", tanpa "selesaikan yang terbuka
     dulu".

**Kelas masalah:** setiap jawaban yang membutuhkan variasi nilai desain atas data yang sama:
- ambang, horizon, jendela, kuantil, periode, parameter event study atau backtest;
- di analisis, riset hipotesis, riset multi-sudut, event study dan backtest;
- di dalam satu pesan maupun pesan lanjutan;
- nanti juga data makro dan lintas-aset.

**Prinsip:** bila satu data bisa menjawab, data diminta sekali. Variasi dihitung dengan mengubah parameter di ruang
kerja yang sama.

**Jaminan yang tetap (prinsip penilaian EXEC-D):**
- data hanya setelah persetujuan, dan di riset hanya eksperimen yang disetujui;
- setiap variasi punya hasil, verdict dan hitung ulang backend sendiri;
- koreksi uji berganda tingkat percakapan (Holm/BH);
- satu ruang kerja per pertanyaan (S08) dan slot sandbox bersama;
- variasi riset di luar rencana tetap butuh rencana revisi dan persetujuan user.

**Butir** (desain teknis rinci di rencana implementasi setelah inspeksi):
- **V-a, opsi B:**
  - Selama ruang kerja run ini masih terbuka dan belum dipakai, pembukaan baru ditolak dengan
    `ANALYSIS_SESSION_ALREADY_OPEN`. Pesannya menyebut ruang kerja yang dipakai dan urutannya: jalankan → selesaikan →
    berikutnya.
  - Penutupan ruang kerja tidak lagi diam-diam; hasil alat memberi tahu AI.
  - Petunjuk setelah paket data berikutnya disiapkan menyebut "selesaikan ruang kerja X dulu".
  - Jalan keluar: penggantian tetap boleh untuk paket yang sama, atau bila ruang kerja itu memang tidak bisa dipakai.
- **V-b, riset hipotesis:** eksperimen satu rencana yang datanya sama berbagi satu kebutuhan data, satu paket dan satu
  ruang kerja. Penyelesaian merilis satu temuan per eksperimen. Yang berubah:
  - kontrak `research_governance`;
  - pencocokan rencana di orc (setiap eksperimen tetap dicocokkan);
  - temuan di sandbox;
  - teks prompt;
  - Tool_Catalog lewat migrasi, dan `AI_TOOLS.md`.
- **V-c, analisis:**
  - Variasi dijawab dalam satu ruang kerja dengan satu tabel berkolom varian (`VARIANT_NOTE`).
  - Backend mengenali kebutuhan data yang identik dengan paket data yang sudah ada di run atau percakapan ini, lalu
    memakai ulang paket dan ruang kerjanya, bukan mengekstrak ulang. Identitasnya diturunkan dari sidik kontrak data,
    bukan daftar nama.
- **V-d, lintas pesan:**
  - Variasi di pesan lanjutan memakai paket data dan ruang kerja percakapan yang masih hidup (CONVERSATION REUSE,
    R-STORE).
  - Di riset, setelah rencana revisi disetujui, perhitungannya berjalan di data yang sama.
- **V-e, cek cakupan ("semuanya yang applicable"):**
  - riset multi-sudut: kelompok paket sudah menggabungkan data bersama; dicek, bukan diasumsikan;
  - event study, backtest dan return per periode: dipastikan memakai pola yang sama.

**Uji (`apps/orc-test-runner/suites/qa_variant_20261007.json`, belum dijalankan):** satu item riset (BBCA) dan satu item
analisis (BBRI).

**Lulus bila:**
- data diambil sekali per data yang sama;
- `analysis_sessions_superseded` = 0;
- panggilan model lebih sedikit dari baseline variant_bbca giliran 2 (22 panggilan, 294 detik);
- semua variasi terjawab dengan verdict, koreksi dan hitung ulang yang sama benarnya;
- variasi di pesan lanjutan tanpa ekstraksi ulang.

**Tidak termasuk:** ruang kerja paralel untuk satu pertanyaan (S08 tetap; `AI_RESEARCH_MAX_PARALLEL_GROUPS` tetap 1).

**Jalan balik:** redeploy orc `63e29b62` dan deployment sandbox sebelumnya, atau revert commit EXEC-V.

### EXEC-M109: pertanyaan tanya-balik router tetap dipakai

**Keputusan user 2026-10-07:** "M109 OK untuk perbaikan plan. Masukan ke EXEC." Pilihan "Ya, masukkan juga
(Recommended)". Dibangun dan ter-deploy 2026-10-07; uji live menunggu golden test.

**Bukti (`ma-qa-20261007c` q7 giliran 3):**
- Router bertanya balik dengan benar: "Rencana riset mana yang harus dijalankan? …", dengan 4 pilihan sudut riset.
- User melihat pertanyaan baku "Maaf, maksud pesan ini belum terbaca dengan pasti …" dengan 2 pilihan baku.

**Akar masalah (terverifikasi dari kode `e551939`):**
- Keempat pilihan berjalur CONTINUE. `conversation_router.usable_options` menyimpan satu pilihan per jalur, jadi tinggal 1.
- `mode4.ask_back_response` lalu membuang pertanyaan router bila pilihan < 2, dan memakai `FALLBACK_QUESTION`.
- Pilihan cepat hanya membawa jalurnya (`chosen_option`), itu sebabnya jalur dijaga unik.

**Kelas masalah:** setiap tanya-balik yang pilihannya berjalur sama (pilih sudut, saham, periode, varian), di jalur pesan
pertama dan giliran lanjutan. Kode menimpa penilaian model, padahal pertanyaan baku hanya jaminan untuk "model gagal".

**Butir (orc; tanpa saklar baru, migrasi, variabel Railway, atau perubahan API):**
- **Langkah 0:** benchmark eksternal (pilihan cepat dengan payload vs label; pertanyaan klarifikasi LLM). Sumber dicatat
  di `ERRORS_AND_SOLUTIONS.md` M109. Bila temuan mengubah desain, lapor dulu.
- **M109-a:** pertanyaan router dipakai selama router tidak gagal dan pertanyaannya tidak kosong. Pertanyaan baku dan
  pilihan baku hanya untuk router gagal atau pertanyaan kosong.
- **M109-b:**
  - **≥ 2 pilihan berbeda jalur:** tombol seperti sekarang.
  - **Pilihan berjalur sama, atau pilihan sah < 2:** tanpa tombol. Label router ditulis sebagai baris bernomor di teks
    pertanyaan. User membalas dengan nomor atau kata-kata, dan router membacanya dari riwayat.
  - `ANSWER_HINT` tetap ada, jadi penghitung "maksimal dua pertanyaan berturut-turut" tetap jalan. `chosen_option` tetap
    berisi jalur.
- **Tes offline (tanpa biaya model):**
  - replay keluaran router q7 giliran 3;
  - router gagal → pertanyaan baku;
  - 2 pilihan beda jalur → tombol;
  - penghitung dua pertanyaan;
  - jalur pesan pertama dan giliran.
- **Dokumen:** teks `ASK_BACK_ACTION` / `ASK_BACK_TURN_RULE` bila perilaku berubah, lalu regenerate `AI_ROUTER.md`.
  `scripts/benchmark_turn_router.py --ask-back` sebelum deploy (kredit ≥ USD 0,30).

**Lulus bila:**
- tes orc dan tes drift hijau;
- benchmark router tanpa kesalahan mahal baru;
- replay q7 giliran 3 menampilkan pertanyaan router dan 4 label.

**Uji live:** ikut golden test berikutnya.

**Tidak termasuk** (`FUTURE_PLAN.md` §3a):
- tombol yang membawa label (perubahan API);
- jawaban "rencana sudah dijalankan, ini hasilnya".

**Jalan balik:** redeploy orc `63e29b62`, atau revert commit EXEC-M109.

**Hasil (2026-10-07):**
- **Kode** (`d25e108`):
  - `mode4.ask_back_response` memakai pertanyaan router kecuali router gagal atau pertanyaannya kosong.
  - `conversation_router.offered_choices` (pengganti `usable_options`): tombol hanya bila ≥ 2 pilihan sah dengan jalur
    berbeda (maksimal 4); selain itu label router ditulis sebagai baris bernomor, tanpa tombol. APPROVE hanya bila ada
    usulan menunggu. `ANSWER_HINT` tetap, jadi batas dua pertanyaan berturut-turut tidak berubah.
  - `AI_ROUTER.md` dibuat ulang dengan kalimat aturan ini; tes drift hijau.
- **Tes:** replay keluaran router q7 giliran 3 (4 pilihan CONTINUE) → pertanyaan router dan 4 baris bernomor tanpa
  tombol; pilihan tak sah dibuang; pilihan sejalur jadi teks; router gagal atau pertanyaan kosong → pertanyaan baku.
  Orc 1.296 lulus.
- **Deploy:** orc `e6ab80c3` SUCCESS (bersama tahap 1 EXEC-V).
- **Perbedaan dari kata-kata rencana (R35):**
  - Benchmark router `--ask-back` (±USD 0,07) tidak dijalankan. Alasannya: instruksi dan skema router yang dikirim ke
    model identik byte demi byte sebelum dan sesudah perubahan (SHA-256 keduanya
    `34161c9a924277c5f63f416b7390bd31b2feb91435f95a97e78effce2d07212e`), jadi keluaran router tidak berubah; yang berubah
    hanya cara backend menampilkan keluaran itu, dan itu dikunci tes offline.
  - Langkah 0 (benchmark eksternal) memakai sumber yang sudah dicatat di M109 (pilihan cepat memisahkan label dan
    payload).
- **Uji live:** ikut golden test berikutnya.

---

## Verifikasi bersama

**Verifikasi butir 2–7:**
- suite orc, sandbox dan Governor hijau;
- golden test ulang 6 item 06b, dengan target:
  - q7 giliran 1 ≤ 15 menit;
  - waktu tindak lanjut penolakan ≤ 5% waktu model (06b 26,8%; 07a+b 10,0%; 07c 7,5%: belum tercapai, menunggu
    keputusan user);
  - nol `tool_not_in_step`;
  - h_add t2 dan threshold t2/t3 lolos;
  - median panggilan per putaran turun ≥ 30%;
  - "BBRI" ditanya balik.
