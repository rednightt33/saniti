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

**Berjalan (2026-10-08):** EXEC-X (M124 + M125 A/B, tampilan jawaban EDGE). Dibangun di cabang
`claude/code-session-2k3oeg` (HTML user sebagai sumber utama, API dipisah dari tampilan, teks backend bahasa biasa);
uji lulus (orc 1.563, EDGE 46). Belum di `main`, belum deploy: menunggu OK user atas pratinjau.

**Menunggu "go" (2026-10-09):** EXEC-Y, rencana implementasi semua butir yang disetujui dan belum dibangun (4 fase).

**Menunggu "go" (2026-10-08):** EXEC-W, rencana eksekusi butir EXEC-V yang disetujui (dua
gelombang).

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
  - Disetujui user 2026-10-08: "Saran saya, GT ini dijalankan setelah V-f dan perbaikan M117 dibangun ... -->
    approved, masukan EXEC. We'll work on M117 now." Urutan: perbaikan M117 → V-f → GT V-g (perintah run tetap dari
    user).
- **M117 diperlakukan sebagai cacat struktural** (inspeksi kode + audit 2026-09-30..10-08, `ERRORS_AND_SOLUTIONS.md`
  M117): opsi perbaikan menunggu keputusan user.
- **M119 (disetujui 2026-10-08, belum dijalankan):** "M119 solusi A dan B - ensure AI aware of this. Penolakan alasan
  harus jelas. Cek sekarang informasi lewat mana AI dapat mengetahui fitur backend. Should include this as well."
  - A: `event_study` (dan `backtest`) mengembalikan data tabel yang dibuatnya.
  - B: kode bisa membaca tabel buatan sesinya sendiri menurut nama (label "belum dirilis"; mengutip tetap butuh rilis).
  - AI tahu lewat semua jalur fitur backend: deskripsi `run_python`/`open_analysis_session`, daftar helper dan batas di
    hasil pembukaan sesi, panduan metode `event_study` (tabel `AI_method_guide`, migrasi), `get_system_capabilities`,
    `help()` di sesi, dan pesan galat. Penolakan menyebut alasannya dan langkah berikutnya; akhiran "sesi riset" hanya
    di sesi riset.
  - **B sebagai penyimpanan tabel kerja sesi, disetujui user 2026-10-08:** "1.000 tabel turunan, konfirmasi: ...
    Usulan saya: opsi B dibangun sebagai penyimpanan tabel kerja sesi, yaitu simpan dan baca menurut nama, dibatasi
    kuota disk, tidak dirilis, dan tidak dihitung dalam batas 40. Dengan begitu 1.000 tabel turunan bisa dipakai di
    analisis. Untuk dikutip di jawaban, tabel tetap harus dirilis seperti biasa. --> OK masukan EXEC."
    - Saat ini: variabel di sesi tidak dibatasi jumlahnya (memori sesi 4 GB, satu frame maks ±40% ≈ 1,6 GB) tetapi
      hilang saat sesi ditutup dan tidak bisa dipanggil menurut nama dari luar kode; tabel yang disimpan sebagai
      keluaran maks 40 per sesi (`PY_SANDBOX_SESSION_MAX_OUTPUTS`, kode maks 500).
    - Dibangun: simpan/baca tabel kerja menurut nama di sesi, dibatasi kuota disk (bukan jumlah), tidak dirilis, tidak
      dihitung dalam 40 keluaran; mengutip angka tetap butuh tabel yang dirilis. Kuota, masa simpan dan nama variabel
      ditetapkan di rencana eksekusi. Status: disetujui, belum ada perintah jalan.
- **M117, usulan "AI yang menafsirkan" (diminta user 2026-10-08: "Bisa gak AI saja yang infer apa maksud user -->
  masukan ke research? Apa resikonya"):** router (panggilan model terpisah yang hanya membaca pesan user) sudah membaca
  ambang/efek minimum/horizon (`design_value_changes`); pemeriksa rencana mengabaikannya. Usulan: (1) bacaan router
  menjadi sumber "kata user"; (2) nilai yang tidak tertelusur tidak lagi membuang rencana, tetapi ditandai "ditafsirkan,
  belum Anda sebut" di pertanyaan konfirmasi (persetujuan user wajib di dev); (3) jaminan EXEC-D "threshold dikunci ke
  kata user" diubah menjadi "tidak ada yang dijalankan dengan ambang yang tidak disebut atau tidak disetujui user".
  Menunggu keputusan user.
- **M117, benchmark praktik terbaik eksternal (2026-10-08).** User meminta: "M117 tolong benchmark dengan antrophic, GPT
  dan external source lainnya terlebih dahulu", lalu menjelaskan: "No, kita pakai deepseek. Yang saya maksud benchmark
  adalah kamu search best practice dari external source". Tidak ada panggilan model dan tidak ada perubahan model atau
  provider. Temuan (sumber di `ERRORS_AND_SOLUTIONS.md` M117):
  - OpenAI. Contoh pesan sistem function calling: "Don't make assumptions about what values to plug into functions. Ask
    for clarification if a user request is ambiguous." Strict JSON schema menjamin bentuk, bukan kebenaran nilai. Model
    Spec: bila maksud tidak jelas, beri tebakan aman, sebutkan asumsinya, dan tanya balik bila perlu. Panduan GPT-5: mode
    "eager" jalan terus dengan asumsi yang dicatat; mode hati-hati berhenti dan melaporkan pertanyaan terbuka sebelum
    lanjut. Pilihannya bergantung pada mahalnya salah.
  - Anthropic. Izinkan model berkata "tidak tahu"; dasarkan jawaban pada kutipan kata per kata dari sumber, cocokkan
    kutipan dengan teks asli lewat string matching, dan tarik klaim yang tidak punya kutipan. Building Effective Agents:
    pasang titik konfirmasi manusia sebelum langkah mahal atau tak bisa dibalik. Claude Code/Agent SDK: tanya user
    (pilihan ganda) hanya untuk keputusan yang memang milik user; selain itu pakai default yang masuk akal.
  - Sistem dialog klasik (Amazon Lex, Dialogflow CX). Setelah slot terisi, tanyakan konfirmasi. Bila user menolak, slot
    itu dikosongkan lalu ditanyakan ulang; maksud dan slot lain tidak dibuang. Batas pengulangan selalu berakhir di jalan
    keluar, tidak pernah buntu.
  - Riset. LLM lemah mengenali permintaan ambigu: CLAMBER (ACL 2024), AMBROSIA (NeurIPS 2024, kategori kata samar),
    PRACTIQ (NAACL 2025). Alur "deteksi, tanya, perbaiki" menaikkan akurasi: ClarifyGPT (FSE 2024), AmbiSQL hingga +50
    poin pada pertanyaan ambigu. Untuk ekstraksi: field wajib mendorong model mengarang; field boleh kosong + "jangan
    menebak" + bukti per nilai menguranginya.
  - **Desain M117 yang diturunkan dari temuan itu (usulan, belum dibangun; tetap DeepSeek):**
    1. Router menulis setiap nilai desain bersama kutipan kata user (`text`, sudah ada di skema) dan dasar
       `STATED`/`IMPLIED`. Backend hanya memeriksa kutipan itu benar ada di pesan user (string matching, diturunkan, tanpa
       daftar kata). Ini menggantikan pembaca ambang buatan tangan (tanda, kata bilangan, nol tersirat).
    2. Nilai yang tidak punya kutipan sah atau berdasar `IMPLIED` tidak membuang rencana. Nilai itu tampil di pertanyaan
       konfirmasi rencana sebagai "saya tafsirkan dari '...'" atau "usulan AI, belum Anda sebut". Persetujuan user adalah
       jaminannya (pola Lex/Anthropic). Karena model lemah mengenali ambiguitas (CLAMBER), jaminan tidak bergantung pada
       deteksi model: semua nilai tanpa kutipan sah selalu masuk konfirmasi.
    3. Kata samar ("signifikan", "naik banyak") dibiarkan kosong lalu ditanyakan (field boleh kosong + jangan menebak).
    4. Gate rencana tidak lagi berakhir di LIMITATION tanpa rencana. Penolakan kedua menyimpan rencana dan menanyakan
       nilai yang bermasalah (re-elicit, pola Lex). Pertanyaan tetap kalau model gagal; maksimal dua pertanyaan berturut
       (EXEC-D).
    5. Jalur analisis (tanpa langkah persetujuan): asumsi ditulis di jawaban (Model Spec) dan angka tetap lewat gate
       sumber yang ada.
    Jaminan EXEC-D "threshold dikunci ke kata user" menjadi: "tidak ada yang dijalankan dengan nilai desain yang tidak
    dikutip dari user atau tidak disetujui user".
  - **Disetujui user 2026-10-08:** "Oke untuk M117, masukan EXEC." Desain 1–5 di atas, termasuk perubahan jaminan
    EXEC-D. Ditambah: rencana yang tertahan gate disimpan sebagai PENDING sehingga "setuju" atau perubahan nilai dari
    user bisa langsung dipakai, dan pesan `GATE_ONCE_NOTE` yang keliru untuk rencana diperbaiki. Belum ada perintah
    jalan; urutan tetap M117 → V-f → GT V-g.
- **M121, inventaris jalan buntu (diminta user 2026-10-08: "saya tidak mau kalau seandainya kena limitation or whatever
  that label was maka AI deadlock jadi tidak dynamic, tidak bisa tanya user, tidak bisa query ulang, tidak bisa run
  another calculation di sandbox"):** 8 titik terverifikasi di kode dan audit (`ERRORS_AND_SOLUTIONS.md` M121). Usulan
  (belum dibangun, menunggu keputusan): setiap gate atau batas yang habis menjeda dan bertanya, bukan mengakhiri. Yang
  sudah terverifikasi tetap disampaikan; rencana, sesi dan draf disimpan; pilihan diturunkan dari penyebabnya (lanjut
  dengan anggaran baru, ubah nilai, terima jawaban sebagian). Perbaikan berlanjut selama ada kemajuan. Pesan alat dan
  prompt menawarkan "cara lain, tanya user, atau laporkan". Rencana yang disetujui tetap bisa dilanjutkan sampai risetnya
  selesai. Jaminan EXEC-D tetap: angka tanpa sumber tidak disampaikan, data hanya setelah persetujuan, belanja berhenti di
  batas sampai user bilang lanjut.
  - **Audit lanjutan 2026-10-08** (diminta user: "saya mau kamu audit mengenai 8 titik buntu ini dan kondisi arsitektur
    backend, mana yang perlu dirubah, mana yang kalau dibiarkan bisa menjadi masalah"; bukti di `ERRORS_AND_SOLUTIONS.md`
    M121):
    - Perlu diubah: (a) gate rencana membuang rencana (titik 2) → M117, disetujui; (b) satu perbaikan per jenis lalu
      LIMITATION untuk jawaban (titik 1: PROVENANCE, FINDINGS_2, METHODOLOGY_PROVENANCE, DEFINITION) → beri tanda dan
      tanya, seperti EXEC-E untuk EVIDENCE; (c) rencana yang disetujui dianggap terpakai apa pun hasilnya (titik 7);
      (d) `GATE_ONCE_NOTE` (titik 8) → bersama M117.
    - Bermasalah bila dibiarkan: (e) sandbox 4 slot total, satu jawaban boleh memegang 4 sampai jawabannya selesai,
      penunggu 60 detik lalu "jangan coba lagi, LIMITATION" (titik 5); jadi masalah begitu ada beberapa user; (f) pesan
      batas perbaikan alat melarang mencoba cara lain atau bertanya (titik 3); (g) batas langkah/waktu tanpa tawaran
      "lanjutkan" (titik 4), dengan default kode 8 langkah / 12 panggilan / 600 detik, padahal dev 60/60/1.800 dan
      lingkungan baru memakai default; (h) prompt mengarahkan ke LIMITATION (titik 6); (i) limit kunci OpenRouter: 31
      jawaban gagal sebelumnya, sisa USD 0,94; (j) arsitektur: setiap gate memutuskan sendiri cara berhenti (orc 6.251
      baris, 37 saklar fitur); usulan: satu aturan berhenti terpusat dan tes yang membaca semua jenis gate dari kode, lalu
      memastikan tidak ada yang berakhir buntu.
    - Sudah baik (dipertahankan): batas panggilan identik, pengklasifikasi balasan rencana yang bertanya bila ragu,
      mode 4 maksimal 2 pertanyaan lalu langkah cadangan, sandbox menunggu dan mengusir sesi hangat, memori percakapan
      membawa penolakan dan draf ke giliran berikut, angka yang tidak diketik dari sumber diberi tanda (bukan ditolak).
    - **M121 disetujui user 2026-10-08:** "M121 (jeda dan tanya, bukan berhenti, plus satu aturan berhenti terpusat):
      disetujui untuk dibuat rencana eksekusinya bersama M117? --> OK masukan EXEC." Lingkup: b, c, f, h, j di atas
      (g pending, lihat di bawah), dibangun bersama M117. Belum ada perintah jalan.
    - **Usulan rincian (user minta "propose a fix" 2026-10-08; menunggu persetujuan):**
      - (e) Sandbox penuh. Pesan "jangan coba lagi" ada karena sandbox sudah menunggu 60 detik dan percobaan ulang
        langsung oleh AI menemui slot yang sama (S05: dulu dicoba terus sampai anggaran jawaban habis). Akibatnya
        jawaban itu tidak selesai, dan user harus mengirim ulang. Usulan: (1) menunggu menjadi tugas backend, bukan AI:
        orc mengantre ulang selama sisa waktu jawaban, tanpa token model; (2) bagi rata: selama ada jawaban lain yang
        menunggu, satu jawaban tidak membuka sesi melebihi bagiannya (slot ÷ jawaban aktif dan menunggu, minimal 1),
        diturunkan saat itu juga; tidak ada sesi yang ditutup, sesuai keputusan "membuka satu tidak menutup yang lain";
        (3) bila waktu jawaban hampir habis: jeda M121, yaitu bagian yang selesai disampaikan, data yang sudah disiapkan
        disimpan, dan user ditanya "lanjutkan?"; (4) pesan "jangan coba lagi" dihapus.
        **Disetujui user 2026-10-08:** "Ok solusi sandbox nomor 1 menungguu jd tugas backend, jawaban jeda, dan feedback
        'jangan coba lagi' bisa diganti ke AI —> masukan exec": butir (1), (3) dan (4). Butir (2) bagi rata tidak
        disetujui (tidak dibangun). Belum ada perintah jalan.
      - (f) Batas perbaikan alat, akar masalah terverifikasi (M122): model mengirim nilai sebagai teks (`"null"`,
        `"[...]"`, `"20"`) sehingga `discover_catalog` menolak `CURSOR_INVALID` padahal model bermaksud kosong;
        `get_research_library` menolak daftar berbentuk teks; `get_lineage` menerima alias `out.o35` di kolom yang
        salah; `query_metric` menolak periode "dari 1 Jan sampai sekarang" (tanpa tanggal akhir); penghitung perbaikan
        tidak di-reset setelah panggilan berhasil. Usulan: (1) registri alat menerjemahkan nilai teks yang jelas sesuai
        tipe di skema (diturunkan dari skema, dicatat di log); (2) masukan yang jelas maksudnya diterima: id dikenali
        dari polanya, periode terbuka berakhir di tanggal data terakhir yang disebut di hasil; (3) pesan galat diturunkan
        dari skema: tipe yang diharapkan, contoh, dan "maksud Anda kolom X?"; (4) penghitung = penolakan berturut-turut
        tanpa sukses di antaranya; (5) saat batas tercapai: "pakai alat lain dengan fungsi sama (diturunkan dari
        registri), tanya user, atau lanjut tanpa bagian ini dan sebutkan", bukan "kembalikan LIMITATION"; (6) setiap
        kejadian dicatat sebagai cacat kontrak alat (friction).
        **Disetujui user 2026-10-08 sebagian:** "Untuk 2. Batas perbaikan alat (M122) --> OK... untuk solusi yang bisa
        dipakai nomor 1, nomor 3 dan 5": (1) terjemahan nilai teks dari skema, (3) pesan galat dari skema, (5) pilihan
        alternatif saat batas tercapai. Nomor 2, 4 dan 6 tidak dibangun. Belum ada perintah jalan.
      - (g) Batas langkah dan waktu. Dev disetel tangan ke 60 langkah / 60 panggilan / 1.800 detik setelah riset
        terpotong; kode bawaan tetap 8 / 12 / 600. Audit: 76% dari 537 jawaban memakai ≥5 langkah model dan 43% memakai
        ≥10, jadi dengan bawaan 8 sekitar separuh jawaban terpotong. Usulan: (1) nilai bawaan kode disamakan dengan nilai
        yang terbukti di dev, dicatat di satu tempat; (2) batas habis = jeda M121: bagian yang terverifikasi
        disampaikan, sesi/data/draf disimpan, dan user ditanya "Saya perlu kira-kira N langkah lagi untuk X.
        Lanjutkan?"; "lanjutkan" memberi anggaran baru (jaminan biaya: belanja di atas batas hanya dengan kata user);
        (3) AI diberi tahu sisa anggarannya mendekati batas, supaya bisa merapikan atau merencanakan jeda.
        **Pending (user 2026-10-08: "Usulan batas langkah dan waktu: jeda dengan pertanyaan 'lanjutkan?', dan nilai
        bawaan kode disamakan dengan dev —> ini pending").** Butir (g) keluar dari lingkup M121 putaran ini; dicatat di
        `FUTURE_PLAN.md`.

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

### EXEC-W: rencana eksekusi putaran 2026-10-08 (butir EXEC-V yang disetujui; menunggu "go")

**Permintaan user 2026-10-08:** "now untuk yg ada di exec tolong cek backend dan architecture dan propose plan untuk
approved exec this round." Rencana ini usulan; eksekusi mulai hanya setelah "go".

**Lingkup (semua sudah disetujui, rincian di EXEC-V):** M117 (desain 1–5, rencana tertahan disimpan PENDING,
`GATE_ONCE_NOTE`); M121 b, c, h, j; M122 butir 1, 3, 5; sandbox penuh butir 1, 3, 4; V-f; M119 A + B (tabel kerja
sesi) + AI tahu lewat semua jalur + penolakan jelas; GT V-g (hanya atas perintah).
**Tidak termasuk:** M121 g (batas langkah/waktu, pending, `FUTURE_PLAN.md`); M122 butir 2, 4, 6; sandbox bagi rata;
M118; M120.

**Temuan inspeksi (read-only, `main` `747e29e`; orc `6a0ebf8f`, sandbox `ce18b33c`, Governor `ad4da9bb`):**
- Pembawa jeda: `FinalResponse` melarang `clarification_question` pada LIMITATION (`app/schemas.py`); `_forced`
  (`orchestrator.py`) mengisinya null. Mode 4 menerima LIMITATION sebagai langkah sah (`mode4._ok`), dan runner hanya
  membaca status. Pembawa jeda paling aman: LIMITATION dengan pertanyaan dan pilihan yang ditulis backend.
- M117: `_plan_gate` memeriksa ambang dan efek minimum dengan `released_numbers` (angka berdigit di teks user) dan
  memakai nilai router hanya untuk REMOVE. Skema router: `text` hanya untuk PERIOD/SCOPE, tanpa dasar STATED/IMPLIED.
  `DesignValueChange`: nilai ≤ 0 diabaikan gate, sehingga "naik" (0) tidak pernah terbaca. Penerbitan rencana
  (`signer.issue`, `conversation_plans`) hanya terjadi bila jawaban tetap RESEARCH_PLAN_CONFIRMATION, jadi rencana
  yang tertahan tetap bisa disetujui asalkan gate tidak mengubahnya menjadi LIMITATION.
- M121 b: gate jawaban yang masih memaksa adalah PROVENANCE, DATANEED_PROVENANCE, ROUTING, ANALYSIS, FINDINGS/
  FINDINGS_2 dan METHODOLOGY_PROVENANCE. EVIDENCE sudah menjadi tanda sejak EXEC-E (`6c6ce58`); TYPED_FIGURES, klaim
  dan definisi sudah menandai. c: `conversation_plans` menandai EXECUTED apa pun hasilnya. h: 14 instruksi menyebut
  LIMITATION sebagai jalan keluar. j: tiap gate memanggil `_gate_once` dan `_forced` sendiri; jenis gate tidak punya
  daftar tunggal.
- M122: `registry.execute` hanya mengurai string argumen terluar; nilai di dalamnya (`"null"`, `"[...]"`) tidak
  diterjemahkan; pesan `REPAIR_BUDGET_EXHAUSTED` menyuruh LIMITATION.
- Sandbox penuh: `tools/session.py` mengubah `SESSION_CAPACITY_EXCEEDED` menjadi `CAPACITY_MESSAGE` ("Do not retry
  ... return LIMITATION"). Batas waktu alat `open_analysis_session` = batas permintaan + 30 detik, sedangkan sandbox
  sendiri bisa menunggu 60 detik plus pembukaan; risiko alat habis waktu saat sandbox masih bekerja. Kode lain yang
  bermakna "sibuk, coba nanti": `QUEUE_FULL` → `RETRY_LATER` (`tools/analysis.py`).
- V-f: dua uji GT1 diekstrak bersamaan di dalam satu `prepare` (potongan berjalan paralel, `AI_PLANNER_PARALLEL_PARTS=2`
  di dev). Sandbox memeriksa garis asal tiap potongan (`coverage.py` LINEAGE), jadi satu dataset tidak bisa dipakai
  dua potongan secara langsung. Jalur pakai ulang (`reuse_of`, `_link_reused`, cek kolom data) sudah ada untuk antar
  jawaban. `_match` menolak rentang sampai hari ini (`RANGE_INCLUDES_TODAY`) tanpa melihat apakah sumbernya jawaban
  yang sama.
- M119: `event_study` sudah mengembalikan frame `events` dan `baseline` tetapi tidak `flow` dan ringkasan;
  `load_output` hanya membaca tabel rilisan percakapan (`carried`), dan akhiran "sesi riset" dipasang setiap kali
  daftar itu kosong. Panduan metode tersimpan di tabel `AI_method_guide` (migrasi v6, generator
  `scripts/generate_ai_method_guide_migration.py`).

**Keputusan desain yang diusulkan (untuk direview):**
- D1, jeda = LIMITATION yang membawa pertanyaan dan pilihan dari backend, ditambah `execution.pause` (penyebab, pilihan,
  apa yang tersimpan). Status tetap LIMITED, jadi runner, mode 4 dan klien lama tetap jalan. Skema jawaban model tidak
  berubah (model tidak pernah menulis jeda). Status percakapan menyimpan jeda terakhir; giliran berikutnya membaca
  pilihan user ("lanjutkan", ubah nilai, terima sebagian) lewat router giliran, seperti rencana yang menunggu.
- D2, tanpa saklar fitur baru (masalah j: 37 saklar). Jalan balik dengan redeploy deployment sebelumnya. Pengecualian:
  satu setelan kuota disk tabel kerja di sandbox (M119 B).
- D3, dua gelombang deploy, masing-masing dengan GT kecil, supaya penyebab bila ada masalah jelas:
  A = orc saja (cara AI berhenti dan bertanya); B = sandbox + orc + migrasi (data dan ruang kerja).

**Gelombang A (orc; M117 + M121 + M122 + sandbox penuh):**
- A1, aturan berhenti terpusat (M121 j). Satu daftar penyebab (gate jawaban, gate rencana, batas perbaikan alat,
  sandbox sibuk). Setiap penyebab punya satu hasil: perbaiki (selama masih boleh), beri tanda, atau jeda (D1).
  `_forced` dan `_plan_not_feasible` lewat aturan ini dan tidak lagi mengakhiri diam-diam. Tes membaca semua jenis gate
  dari daftar itu dan dari pemanggilan di kode, lalu gagal bila ada jenis tanpa hasil atau berakhir buntu. `GATE_ONCE_NOTE`
  menyebut hasil sebenarnya per penyebab.
- A2, M117:
  - Skema tiga router (pesan pertama, giliran, balasan rencana): setiap nilai desain menulis kutipan kata user
    (`text`) dan dasar `STATED`/`IMPLIED`; nilai 0 dengan arah sah.
  - Backend memeriksa kutipan ada di pesan user (pencocokan teks yang dinormalkan, tanpa daftar kata). Nilai rencana
    yang cocok dengan nilai router berkutipan sah dianggap kata user (tanda dan skala persen tetap dicocokkan seperti
    sekarang).
  - Nilai yang tidak tertelusur, atau IMPLIED, tidak membuang rencana. Backend menambah blok "Nilai yang perlu Anda
    konfirmasi" ke jawaban rencana: nilai, kutipan atau "usulan AI, belum Anda sebut", dan asalnya. Rencana diterbitkan
    PENDING seperti biasa, sehingga persetujuan user mencakup nilai itu.
  - Kata samar: nilai kosong lalu ditanyakan.
  - Gate rencana lain (versi, temuan, input bawaan, kelayakan, sumber angka teks) setelah satu perbaikan: jeda D1
    dengan draf rencana tersimpan, bukan LIMITATION tanpa jejak.
  - Jaminan EXEC-D diubah teksnya: "tidak ada yang dijalankan dengan nilai desain yang tidak dikutip dari user atau
    tidak disetujui user".
- A3, M121 b, c, h:
  - b: gate jawaban yang memaksa diganti jeda D1. Bagian yang terverifikasi disampaikan; angka tanpa sumber tidak
    pernah disampaikan sebagai fakta (ditandai dan dikeluarkan, seperti EXEC-E); pilihan "hitung ulang bagian X /
    terima tanpa bagian itu".
  - c: rencana yang disetujui tetap bisa dilanjutkan sampai risetnya selesai (status baru: disetujui, belum selesai);
    "lanjutkan" memakai persetujuan yang sama selama rencana belum kedaluwarsa, dan sesudahnya rencana ditampilkan
    ulang untuk disetujui.
  - h: instruksi prompt yang menyebut LIMITATION diubah menjadi "cara lain, tanya user, atau laporkan", dengan aturan
    ukuran prompt +2% tetap dijaga.
- A4, M122 1, 3, 5: registri menerjemahkan nilai teks yang tipenya pasti menurut skema (null, angka, daftar, objek) dan
  mencatat `ai_tool_arguments_decoded`; pesan galat diturunkan dari skema (tipe yang diharapkan, contoh, kolom
  saudara yang cocok); saat batas tercapai pesannya menawarkan alat lain dengan efek yang sama (dari registri), tanya
  user, atau lanjut tanpa bagian itu.
- A5, sandbox penuh 1, 3, 4: orkestrator menunggu dan mencoba ulang kode "sibuk, coba nanti" (`SESSION_CAPACITY_EXCEEDED`
  tanpa sesi sendiri, `QUEUE_FULL`) selama sisa waktu jawaban, tanpa token model, dan mencatat antreannya. Batas waktu
  alat pembuka sesi diturunkan dari waktu tunggu sandbox. Bila waktu habis: jeda D1, dengan data yang sudah disiapkan
  tetap tersimpan. Pesan "Do not retry" diganti pesan yang menyebut apa yang terjadi dan pilihan AI.
- Dokumen: `AI_ROUTER.md` (generator), `AI_TOOLS.md`/`AI_MODELS.md` bila deskripsi alat atau setelan router berubah,
  EXEC-D, `ERRORS_AND_SOLUTIONS.md` (M117, M121, M122, P42), `RAILWAY_CHANGELOG.md`.
- Uji sebelum deploy: tes unit orc penuh. Benchmark router (`scripts/benchmark_first_router.py`,
  `benchmark_turn_router.py`, plus kasus M117: nol tersirat, tanda, kata bilangan, kata samar, tanpa ambang),
  DeepSeek saja, sekitar USD 0,05, kredit dicek ≥ USD 0,30.
- Deploy orc; log startup tanpa `*_inactive`; `/ready` 200.
- GT-A (atas perintah): riset "naik" → rencana dengan nilai ditafsirkan → "setuju" → riset jalan; "naik signifikan" →
  ditanyakan; ubah nilai setelah rencana; satu jawaban analisis yang memancing gate sumber angka → jeda dengan pilihan.

**Gelombang B (sandbox + orc + migrasi; V-f + M119):**
- B1, V-f:
  - Planner orc: di dalam satu `prepare`, potongan dengan `data_sha256` sama diekstrak sekali; potongan lainnya
    direncanakan `reuse_of` potongan saudara di rencana yang sama.
  - Sandbox: pembangun paket menerima pakai ulang dari potongan di paket yang sama (ditautkan setelah unduhan, cek
    checksum dan kolom data seperti pakai ulang antar jawaban).
  - `_match`: sumber dari request yang sama dengan tanggal acuan yang sama boleh dipakai walau rentangnya sampai hari
    ini atau tanpa rentang.
  - Laporan `data_reuse` menyebut "dipakai ulang di jawaban ini".
- B2, M119:
  - A: `event_study` dan `backtest` mengembalikan semua tabel yang dibuatnya sebagai frame (ringkasan, alur) beserta
    nama outputnya.
  - B: `save_table(name, frame)` / `load_table(name)` di sesi, dengan kuota disk per sesi (setelan baru, nilai
    ditetapkan setelah ukuran volume sandbox dibaca), tidak dirilis, tidak dihitung dalam 40 keluaran, label "belum
    dirilis". `load_output` juga membaca keluaran sesi sendiri menurut nama dengan label yang sama. Mengutip angka
    tetap butuh tabel yang dirilis.
  - Penolakan menyebut alasan dan langkah berikutnya; akhiran "sesi riset" hanya di sesi riset.
  - AI tahu lewat semua jalur: deskripsi `run_python`/`open_analysis_session`, daftar helper dan batas di hasil
    pembukaan sesi, `help()`, `get_system_capabilities`, panduan metode (migrasi `AI_method_guide` v7), `Tool_Catalog`
    round baru, `AI_TOOLS.md`.
- Migrasi: panduan metode v7 dan `Tool_Catalog` round baru (generator; `APPLIED.sha256`). Dibaca ulang dari database
  setelah dijalankan.
- Uji: tes sandbox dan orc penuh. Deploy sandbox → orc (orc di-redeploy setelah sandbox SUCCESS); log startup.
- GT V-g (`suites/qa_relabel_20261008.json`) + satu item M119 (riset dengan beberapa `event_study` lalu tabel ringkasan
  dari tabel kerja), atas perintah.

**Lulus bila:**
- Tidak ada jalan buntu baru (tes daftar penyebab), tidak ada LIMITATION tanpa pertanyaan dari gate atau sandbox sibuk.
- GT-A: riset "naik" berjalan setelah "setuju"; nilai IMPLIED tampil di konfirmasi; kata samar ditanyakan.
- GT B: `parts_looked_up matched>0` dan `bundle_built parts_reused>0` (V-g); satu SQL sekali per jawaban (log Governor);
  tidak ada `load_output` gagal untuk tabel sesi sendiri.
- Semua angka jawaban tetap bersumber; tidak ada data diambil sebelum persetujuan.

**Risiko dan mitigasi:**
- Perubahan cara berhenti menyentuh semua gate. Mitigasi: daftar penyebab tunggal dan tes yang membacanya; gelombang
  A tanpa perubahan sandbox.
- Router menulis kutipan yang tidak persis. Mitigasi: pencocokan dinormalkan; bila gagal, nilai masuk konfirmasi (tidak
  dibuang, tidak dijalankan diam-diam).
- Jeda terlalu sering mengganggu. Mitigasi: hanya setelah perbaikan habis, maksimal dua pertanyaan berturut (EXEC-D).
- Menunggu sandbox memperpanjang jawaban. Mitigasi: dibatasi sisa waktu jawaban; antrean dicatat.
- Tabel kerja memenuhi disk. Mitigasi: kuota per sesi dan dihapus saat sesi ditutup.
- Kredit: limit kunci tinggal USD 0,94; GT perlu limit dinaikkan user.

**Jalan balik:** orc `6a0ebf8f`, sandbox `ce18b33c` (Governor tidak berubah); revert commit per gelombang. Migrasi
tambah-saja (versi panduan baru dan round katalog baru), versi lama tetap.

**Disetujui user 2026-10-08:** "Ok" atas pertanyaan "D1, D2, D3 disetujui? Go untuk mulai Gelombang A?" Gelombang A
dimulai; Gelombang B dan setiap GT tetap menunggu perintah user.

**Hasil Gelombang A (2026-10-08, orc saja; commit `08549d0`, `8753eee`, `2e27136` di `claude/code-session-2k3oeg`):**
- A1 `app/stop_policy.py`: satu tabel hasil per jenis pemeriksaan (PAUSE, CONFIRM, ANNOTATE, ALTERNATIVES,
  PENDING_DECISION). `_forced` dan `_plan_not_feasible` lewat `_paused`: LIMITATION tetap membawa draf di balik catatan
  backend, lalu diakhiri pertanyaan dan pilihan penyebabnya; `execution.pause` dan `data_record.pause` menyimpannya, dan
  pesan berikutnya membaca catatan jeda sekali (`pause_answered`). Mode 4: langkah yang jeda menjedakan giliran. Catatan
  "hanya sekali" dan hasil di log diturunkan dari tabel (METHODOLOGY dan lain-lain tidak lagi tercatat
  FORCED_LIMITATION). Tes `tests/test_stop_policy.py` membaca semua jenis pemeriksaan dari kode dan gagal bila ada yang
  tanpa hasil atau berakhir tanpa pertanyaan.
- A2 M117: skema tiga router menulis `text` (kutipan kata user) dan `basis` STATED/IMPLIED; `user_words.quoted_in`
  mencocokkan kutipan tanpa daftar kata. Pemeriksa rencana: nilai berkutipan STATED = kata user; IMPLIED atau beda tanda
  = "saya tafsirkan dari ..."; tanpa kutipan = satu kali perbaikan lalu "usulan AI, belum Anda sebut"; horizon yang
  berbeda dan angka teks rencana tanpa sumber juga masuk daftar. Rencana tetap terbit PENDING dengan blok "Nilai yang
  perlu Anda konfirmasi sebelum riset dijalankan" yang ditulis backend. `CODE_GUARANTEES` diubah sesuai EXEC-D baru.
- A3 M121: `research_completed` di eksekusi rencana; rencana yang risetnya belum selesai tetap PENDING (percobaan
  dicatat) dan "lanjutkan" menjalankannya lagi. Prompt dan instruksi kelayakan/eksekusi menawarkan bertanya ke user
  (CLARIFICATION) sebelum LIMITATION (tes prompt +2% tetap lulus).
- A4 M122 1, 3, 5: registri menerjemahkan nilai berbentuk teks menurut skema (`ai_tool_arguments_decoded`,
  `text_values_decoded`); pesan galat menyebut tipe yang diharapkan dan kolom saudara yang cocok polanya; batas
  perbaikan menawarkan alat lain dengan efek sama, bertanya, atau lanjut tanpa hasil itu (`tool_repair_budget_reached`).
- A5 sandbox penuh: `open_with_wait` (dipakai `open_analysis_session` dan riset) mengantre ulang selama sisa waktu
  jawaban (cadangan 180 detik, maks 900 detik, dipacu sesuai tahanan sandbox), batas waktu alat diturunkan darinya;
  setelah itu pesan ke AI tanpa "Do not retry" (`next_action` PAUSE_ANSWER) dan LIMITATION-nya dijeda (SANDBOX_BUSY).
- Tes: orc 1.548 lulus termasuk tes database (Postgres lokal). Benchmark DeepSeek (kredit dicek, sisa limit kunci
  USD 0,94; biaya ±USD 0,11): router pesan pertama `--ask-back` PASS (development 60/60, heldout 32/32, ask-back 16/16);
  router giliran 48/50 (dua salah = kasus "BMRI kemarin" yang sama dengan sebelumnya, diterima di RAILWAY_CHANGELOG);
  set M117 16 kalimat: semua angka eksplisit terbaca dengan kutipan sah (termasuk "setengah persen", "lima persen",
  "-2" dari "turun lebih dari 2%"), nol tersirat 4/4 (sebelumnya 1/4), 0 kutipan palsu, 1 JSON rusak (dicoba ulang di
  produksi); empat kalimat tanpa ambang dibaca 0 IMPLIED dari "naik"/"kenaikan" (masuk konfirmasi, tidak dijalankan
  tanpa persetujuan); "naik signifikan" dibaca 0 dari "naik" tanpa menanyakan "signifikan" (dicatat untuk GT-A).

**Deploy dan GT-A (2026-10-08; perintah user: "Push semua ke main dan deploy. Lakukan GT"):**
- `main` = EDGE + Gelombang A (`52a4ae9`); sumber market-ai-orc dan edge-bff kembali ke `main` (`railway config apply`);
  orc `6bb2a68f` dan edge-bff `2dcf1155` SUCCESS (RAILWAY_CHANGELOG).
- GT-A `ma-qa-wavea-20261008a` (`apps/orc-test-runner/suites/qa_wave_a_20261008.json`, runner `7bb24f72`, 3 butir, 5
  giliran, biaya model USD 0,18; kredit dicek: sisa limit kunci USD 0,81 sebelum):
  - naik_confirm: rencana terbit (model mengosongkan success_rule, jadi tanpa blok konfirmasi); "setuju" menjalankan riset
    (EXECUTE_APPROVED, `research_completed` true, rencana EXECUTED); jawaban COMPLETED, satu perbaikan sumber angka.
  - vague_word ("naik signifikan"): rencana terbit dengan blok "Nilai yang perlu Anda konfirmasi" ("> 0 ... saya
    tafsirkan dari \"naik\""); tidak ada LIMITATION. Celah: "signifikan" tidak ditanyakan (desain M117 butir 3 baru
    separuh: nilai samar tidak dikarang, tetapi pertanyaannya belum ada; usulan: router melaporkan kata samar dan backend
    menambahkannya ke blok konfirmasi; menunggu keputusan).
  - revise_value: "ubah ambang suksesnya jadi minimal satu persen" menjadi success_rule ≥ 1% (kata bilangan, dikutip,
    tanpa baris konfirmasi); min_effect 1 yang dikarang model ditolak sekali lalu dikosongkan.
  - Tidak ada jeda (pause) atau LIMITATION; tidak ada penolakan argumen yang tersisa (satu `check_references` daftar
    kosong, M120).
  - Cacat yang ditemukan dan diperbaiki: baris konfirmasi menulis "0" tanpa tanda dan satuan; kini "> 0%" (`_shown_unit`).

**GT lewat front-end EDGE (2026-10-08; permintaan user: "lakukan pengecekan dan gt bisa pakai front end bff? agar kamu
bisa liat interaksi"):** Playwright + Chromium ke `https://edge-bff-dev.up.railway.app`, login dengan variabel edge-bff
(tidak pernah dicetak); CA proxy sesi dimasukkan ke penyimpanan NSS lokal (verifikasi TLS tetap aktif). 4 giliran,
biaya model ±USD 0,13 (sisa limit kunci USD 0,62 sebelum).
- Riset "naik" lalu klik **APPROVE** di UI: riset jalan, COMPLETED, `research_completed` true (INCONCLUSIVE,
  UNDERPOWERED). Model mengosongkan success_rule, jadi tanpa blok konfirmasi.
- "naik signifikan": rencana terbit; model menafsirkan "signifikan" sebagai keyakinan 95% dan menulisnya sebagai asumsi,
  **tidak bertanya** (M123).
- "ubah ambang suksesnya jadi minimal satu persen": success_rule ≥ 1% sebagai kata user; model juga mengisi efek minimum 1%
  yang tidak disebut user, dan backend menampilkannya di blok "Nilai yang perlu Anda konfirmasi ... Efek minimum ...: 1%,
  usulan AI, belum Anda sebut" (terlihat di UI).
- Jeda tidak terpicu di GT ini. Pilihan jeda saat ini hanya teks di akhir jawaban; UI belum membacanya dari
  `execution.pause.options` sebagai tombol (M124).
- Temuan front-end (M124): rencana riset dan "Research findings" tampil sebagai JSON mentah; markdown jawaban tidak
  dirender (`**...**` terlihat); tombol rencana APPROVE/REVISE/CANCEL dalam bahasa Inggris.

### EXEC-X: M124, tampilan jawaban di EDGE (go 2026-10-08; berjalan)

**Keputusan user 2026-10-08:**
- "m124 kamu beresin saja ya"
- "jadikan ini nice, inspect dulu code then generate plan"
- Bingkai aplikasi: "Tidak, tetap inggris." Hanya area jawaban, tombol pilihan dan status yang berbahasa Indonesia.
- "Go untuk EXEC-X? OK"

**Temuan inspeksi (read-only, `main` `ee1bee1`; edge-bff `2dcf1155`, orc `9efe1118`).**

`apps/edge-bff/static/index.html`, `ResearchDocument` dan `Sources`:
- Jawaban dicetak sebagai teks polos (`pre-wrap`), sehingga `**...**`, `##` dan tabel markdown terlihat mentah.
- `research_plan` dicetak dengan `JSON.stringify` di dalam `<pre>`. Butir `research_findings` juga dicetak sebagai JSON.
- Tombol rencana memakai teks tetap `["APPROVE","REVISE","CANCEL"]`. Pesan yang terkirim berbahasa Inggris
  ("Approve the research plan") dan muncul sebagai gelembung pesan user.
- `execution.pause` tidak dibaca. Pertanyaan jeda hanya berupa teks yang ditempel orc di akhir jawaban
  (`_paused`, `apps/market-ai-orc/app/orchestrator.py`).
- Status tampil teknis dan berbahasa Inggris: "Run 1 · Completed" untuk rencana yang menunggu persetujuan, dan
  "Saved response: AWAITING_CONFIRMATION".
- Tab Sources mencetak tiap bukti sebagai JSON.
- Tanda klaim P17 (`annotations`: teks miring dan catatannya) tidak tampil.
- Pilihan klarifikasi (`options`) sudah berupa tombol.

Uji `apps/edge-bff/tests/test_browser.py` memeriksa nama tombol APPROVE/REVISE/CANCEL.

**Akar masalah (terverifikasi dari kode dan tangkapan layar GT UI):** renderer tidak punya tampilan yang memahami jenis
data. Setiap bagian terstruktur jatuh ke teks atau JSON.

**Kelas masalah:** setiap bagian terstruktur yang dikirim orc tampil sebagai JSON atau tidak tampil sama sekali.
Contohnya:
- rencana v1, v1 dengan temuan, dan v2 (sudut);
- temuan per eksperimen dan per sudut dengan angka backend;
- jeda;
- bukti dan catatan data;
- data lintas-aset dan makro yang akan datang.

Selain itu, setiap pilihan dari backend di luar `options` hanya berupa teks.

**Perbaikan (permanen):**

1. **Front-end (`apps/edge-bff/static/index.html`, bagian renderer saja).**
   - **a. Markdown yang aman.** Dibangun dengan `element()` sebagai simpul DOM, tanpa `innerHTML`. Mendukung judul,
     paragraf, tebal/miring, kode sebaris, daftar, tabel (gaya `.data-table`), kutipan, garis, dan tautan lewat
     `Edge.safeUrl`. Sintaks lain tetap tampil sebagai teks. Teks miring yang sama dengan kutipan `annotations` diberi
     catatannya saat disentuh atau diarahkan kursor (P17).
   - **b. Tampilan umum untuk data terstruktur.**
     - Objek menjadi baris berlabel, daftar objek menjadi kartu, daftar teks menjadi butir, dan angka diformat id-ID.
     - Label diambil dari satu tabel label Indonesia. Field yang belum dikenal tetap tampil dengan nama yang dibuat
       mudah dibaca, tanpa perubahan kode.
     - JSON hanya ada di "Detail teknis" yang tertutup.
   - **c. Kartu rencana riset.**
     - Bagian atas: tujuan, cakupan, periode dan frekuensi.
     - Satu kartu per eksperimen (v1) atau sudut (v2): hipotesis, kondisi, yang diukur, pembanding, horizon, arah,
       ambang sukses dengan operator dan satuan (misalnya "> 0%"), efek minimum, dan tabel yang dibawa.
     - Asumsi dan batasan sebagai butir.
   - **d. Kartu temuan riset.**
     - Lencana putusan backend dengan warna dan label Indonesia: Didukung, Didukung sebagian, Tidak didukung, Belum
       konklusif, Tidak dievaluasi, Bukti belum cukup, Tidak valid, Tidak dijalankan. Nilai yang belum dikenal tampil
       apa adanya dengan warna netral.
     - Judul diambil dari eksperimen atau sudut di rencana bila tersedia.
     - Isi: Jawaban / Bukti / Kegunaan / Langkah berikutnya, serta angka backend (estimasi, CI, p, sampel).
   - **e. Satu komponen pilihan untuk semua pilihan backend.**
     - Mencakup pilihan klarifikasi (route), aksi rencana (Setujui / Revisi / Batalkan), dan pilihan jeda (dari
       `execution.pause.options`).
     - Klik pilihan jeda mengirim labelnya sebagai pesan. Orc sudah membaca pesan itu lewat catatan jeda.
     - Pilihan yang butuh kata user (`needs_input`) mengisi kolom ketik dan memfokuskannya.
     - Aturan aktif tetap seperti sekarang: hanya jawaban terakhir dan hanya saat tidak ada yang berjalan.
   - **f. Kartu jeda.** Berisi "Jawaban ini dijeda", alasan dan tombol pilihan. Pertanyaan jeda di akhir jawaban tidak
     ditampilkan dua kali, hanya bila sama persis dengan `pause.question`.
   - **g. Status dalam kata biasa:** Selesai, Menunggu persetujuan, Perlu jawaban Anda, Dijeda, Terbatas, Gagal. Pesan
     aksi rencana: "Setujui rencana riset", "Batalkan rencana riset".
   - **h. Tab Sources.**
     - Tiap bukti tampil sebagai baris yang mudah dibaca: status, klaim, sumber (ref, nama, tanggal data).
     - Catatan data diringkas: tabel yang dibaca dan output yang dirilis.
     - JSON di "Detail teknis".
   - **i. Gaya.** Memakai token dan kelas yang sudah ada (`.data-table`, `.pill`, `--positive`, `--card`, `--border`),
     tema terang/gelap, dan lebar 360–1600 px. Tanpa pustaka luar; CSP tidak berubah.
2. **Orc, kontrak kecil yang hanya menambah field.** Catatan jeda (`stop_policy.pause_record`) menyimpan `question`
   (teks persis yang ditempel di jawaban) dan `needs_input` per pilihan (REVISE_PLAN). Keduanya ditentukan oleh tabel
   kebijakan jeda itu sendiri. Klien lain tidak terpengaruh.

**Tidak termasuk:**
- M123;
- terjemahan bingkai aplikasi (Workspace, New conversation, Submit, Details): user memutuskan tetap bahasa Inggris;
- daftar nilai konfirmasi terstruktur, karena blok konfirmasi M117 tetap markdown tetapi kini terender;
- tampilan per langkah mode 4;
- berbagi publik.

**Langkah:**
1. **Orc.** Kontrak jeda dan uji (`tests/test_stop_policy.py`), lalu seluruh uji orc.
2. **EDGE.**
   - Renderer a–i.
   - Uji `test_browser.py` diubah untuk tombol Indonesia, kartu rencana, tanpa JSON mentah, tabel markdown, tombol jeda
     yang mengirim label, dan `needs_input` yang mengisi kolom ketik.
   - Fixture dari respons tersimpan GT: rencana v1, jawaban INCONCLUSIVE dengan tabel, klarifikasi, LIMITATION dengan
     jeda, rencana v2 dan temuan per sudut.
   - Uji keamanan: `<script>` dan tautan `javascript:` di markdown tetap tampil sebagai teks.
3. **Pratinjau.** Tangkapan layar lokal (desktop/ponsel, gelap/terang) dari fixture dikirim ke user **sebelum deploy**.
4. **Deploy setelah user setuju.**
   - Push `main`, lalu orc dan edge-bff ter-deploy lewat `watchPatterns`.
   - Status deployment dicek sampai SUCCESS, lalu dicatat di `RAILWAY_CHANGELOG.md`.
5. **Cek live tanpa biaya AI.** Buka percakapan GT yang tersimpan di dev (edge_d1bb…, edge_5141…, edge_3b0e…,
   edge_7c49…) di UI baru dan ambil tangkapan layar. Jeda live butuh run berbayar dan tidak bisa dipaksa, jadi hanya
   dijalankan atas perintah.
6. **Dokumentasi:** status M124 di `ERRORS_AND_SOLUTIONS.md`, ringkasan EXEC, README edge-bff (kontrak renderer), dan
   changelog.

**Risiko dan biaya:**
- `index.html` adalah file pasokan 10,6 ribu baris. Perubahan dibatasi pada fungsi renderer dan CSS tambahan di
  akhir.
- Sesi Codex mungkin mengubah file yang sama di `codex/edge-bff`, jadi perlu pull dulu.
- Markdown yang tidak didukung tampil sebagai teks (aman).
- Biaya: tanpa biaya AI, satu deploy orc dan satu deploy edge-bff.

**Uji generalisasi:**
- Kasus lain yang tercakup:
  - rencana v2 (sudut) dan temuan per sudut dengan angka backend, yang belum terlihat di GT;
  - field yang belum dikenal tampil berlabel;
  - nilai putusan yang belum dikenal tampil netral.
- Kasus yang tidak tercakup: isi teknis `data_record` dan lampiran unduhan. Keduanya tetap di Detail teknis atau
  sebagai tautan, karena itu data operasional dan bukan bacaan user.

**Lanjutan 2026-10-08 (keputusan user, kata-kata user):**
- Atas M125 (bahasa kaku, istilah teknis): "Ok, tolong perbaiki. Jalankan." Ini berlaku untuk usulan A (tampilan) dan B
  (teks backend). C (aturan pembaca untuk AI, butuh GT berbayar) belum dijalankan.
- "Saya akan lampirkan HTML yang sudah diperbaiki. Saya tidak mau ada formatting yang berubah." Lalu: "Pakai saja HTMl
  saya as the main source. Tinggal ubah API wiringnya kan."
- "untuk HTML karena akan banyak improvement, usahakan setiap API jangan ter-lock kesuatu object. Benchmark dan pakai
  best practice that allow us untuk edit FE jika ada improvement dimasa mendatang dengan mudah tanpa harus terlalu
  banyak coding."

**Benchmark (sumber eksternal):**
- Backend for Frontend (Sam Newman; AWS, Microsoft): backend membentuk data sesuai satu tampilan, sehingga logika di UI
  tipis.
- Server-driven UI (Airbnb Ghost Platform; Apollo SDUI): tampilan dibangun dari blok bertipe lewat registry komponen.
  Tipe yang belum dikenal ditangani oleh cadangan (fallback), bukan error.
- Adaptive Cards (Microsoft): elemen yang tidak dikenal punya `fallback` dan kartu punya `version`.

Yang diterapkan dari ketiganya: satu kontrak tampilan berversi, tampilan generik sebagai cadangan, dan pilihan sebagai
deskriptor aksi.

**Yang dibangun:**
1. **HTML user menjadi `static/index.html`.** Data dan server tiruan pratinjau dibuang, `/edge-client.js` dimuat lagi.
   CSS dan markup byte-identik dengan file user.
2. **Pemisahan lapisan.**
   - `static/edge-view.js` (`EdgeView.toView`, kontrak tampilan v1) adalah satu-satunya kode yang membaca bentuk respons
     orc.
   - `static/edge-labels.js` memuat semua kata.
   - Tampilan hanya membaca model tampilan.
   - Semua pilihan lewat satu `act()` dengan deskriptor `route`, `plan`, `message` atau `input`.
   - BFF menyajikan setiap script halaman menurut namanya.
   - DOM keenam percakapan pratinjau identik dengan halaman user sebelum langkah M125.
3. **Alat pratinjau dua arah** (`preview/edge_preview.py build|import`). File satu-halaman diedit lalu dikembalikan ke
   sumber. Round trip tanpa perubahan sudah diuji; file yang bukan buatan alat ini ditolak.
4. **M125 B (orc).**
   - `app/user_texts.py` memuat semua teks backend untuk user dalam bahasa Indonesia sehari-hari, tanpa ID dan kode.
   - Kode diubah ke kata lewat `words()`.
   - Angka yang dirujuk diberi nama lewat `value_label()`, yang diturunkan dari alamatnya.
   - Baris konfirmasi menyebut "eksperimen 1"; horizon ditulis "10 hari".
   - ID dan kode tetap ada di instruksi untuk model dan di log.
   - `tests/test_user_texts.py` gagal bila ada nama internal, kode, atau kalimat Inggris di teks user modul mana pun.
5. **M125 A (EDGE).**
   - Judul di tab Sources memakai nama dari backend, dan alamat kode tidak lagi tampil sebagai baris.
   - Kode yang belum punya kata ditampilkan terbaca, tidak mentah.
   - Format halaman user tidak diubah: struktur dan class tetap. Yang berubah hanya teks, satu baris batasan yang dobel,
     dan elemen judul Sources.
6. **Data contoh pratinjau.** Bagian yang ditulis backend dirender ulang dengan teks baru; teks AI tidak diubah.

**Belum tercakup:**
- Gaya bahasa kalimat AI (M125 C), menunggu persetujuan dan kredit.
- Teks dari layanan analisis yang diteruskan apa adanya (misalnya "numeric stored as float64", "not causation").
- Nama kolom pada label angka dari tabel hasil (misalnya "mean return"); idealnya diambil dari `Column_Catalog`.
- Kode baru dari mesin riset yang belum punya kata tampil sebagai kata Inggris yang terbaca.

**M125 C (aturan pembaca untuk AI): benchmark dan inspeksi (permintaan user 2026-10-08: "ok, benchmark denfan best
practice dulu then inspect current architecture").** Hanya laporan, belum ada perubahan prompt.
- **Benchmark:**
  - SEC Plain English Handbook: kalimat pendek, kata sehari-hari, kalimat aktif, daftar atau tabel untuk hal rumit.
  - POJK perlindungan konsumen (OJK): bahasa Indonesia yang mudah dimengerti konsumen.
  - Panduan prompt Anthropic dan OpenAI: sebut pembacanya, beri contoh, katakan apa yang harus dilakukan dan bukan hanya
    larangan.
  - Riset pengendalian keterbacaan: contoh (few-shot) membantu tetapi tidak konsisten di semua model.
  - Riset komunikasi statistik (Glenton 2010, Pocock 2009): selang kepercayaan paling sulit dipahami; makna dulu, angka
    kemudian.
- **Inspeksi (terverifikasi):**
  - Aturan 15 prompt hanya mengatur bahasa.
  - `FINDINGS_RETURNED` dan `INTERPRETING_RULES` mendaftar kode (INSUFFICIENT, ANECDOTAL, UNDERPOWERED, ADEQUATE, kode
    putusan) dan meminta "state the sample category".
  - `FINDINGS_INSTRUCTION` (perbaikan) meminta hal yang sama.
  - Gate temuan hanya memeriksa angka sampel, bukan kata kodenya. Jadi kode di jawaban berasal dari instruksi, bukan
    dari jaminan.
  - Deskripsi `methodology` meminta "data and period used".
  - Deskripsi temuan meminta "in the verdict's terms".
  - Ruang prompt tersisa 5 karakter dari batas +2% (`tests/test_prompt_pass2.py`, keputusan EXEC-P2).
- **Dugaan (belum terbukti):** aturan 12 ("Preserve exact identifiers ... table, field ... names") dibaca AI juga untuk
  teks jawaban.
- **Ukuran awal** (`scripts/answer_plainness.py`; kosakata diturunkan dari `DATABASE_SCHEMA.md` dan enum orc; 70
  jawaban GT gtA, gt_f, qa, golden_c):
  - 80% jawaban memuat istilah internal, rata-rata 4,7 per jawaban.
  - Kalimat median 19,5 kata.
  - Yang terbanyak: INSUFFICIENT_EVIDENCE ×22, UNDERPOWERED ×17, SUPPORTED ×13, `out.oN`, nama metode dalam snake_case,
    dan nama tabel (IDX_Stock_Universe ×6).
- **Keputusan user 2026-10-08:**
  - Ruang prompt: "Naikan batas". Batas ukuran prompt +2% (EXEC-P2) dinaikkan; besarnya diusulkan bersama draf.
  - "Lanjut tulis prompt. Pakai best practice prompt. Pastikan tidak ada prompt yg contradict di system prompt."
  - Draf ditulis dan diuji offline dulu. GT berbayar hanya atas perintah.
- **Dibangun 2026-10-08 (cabang sesi, belum deploy):**
  - Bagian prompt baru **WRITING FOR THE READER**, letaknya setelah FINAL RESPONSE dan berlaku di semua jalur dan mode 4.
    Isinya:
    - pembacanya investor perorangan;
    - kesimpulan dulu, lalu dua atau tiga angka dengan pembandingnya, lalu artinya, lalu batasannya;
    - kalimat pendek dan kata sehari-hari, istilah statistik dijelaskan sekali;
    - nama tabel, kolom, output, sudut, eksperimen dan metode, ref `out.oN`, ID dan kode tidak muncul di teks pembaca;
    - angka tetap berupa referensi nilai;
    - satu contoh jawaban berbahasa Indonesia. Contoh ini memakai referensi nilai, jadi hanya ditulis bila fitur itu aktif.
  - Kalimat yang bertentangan diperbaiki:
    - aturan 12, karena nama persis hanya untuk pemanggilan tool dan referensi;
    - "disclose" bendera kualitas, menjadi dengan kata biasa;
    - data di METHODOLOGY, tanpa nama tabel atau kolom;
    - "in the verdict's terms" dan "in its status's terms", menjadi kata yang sesuai putusan;
    - "the sample category", menjadi seberapa sampel bisa dipegang, dengan kata;
    - "Report an INVALID or NOT_RUN angle as such";
    - kalimat penutup INTERPRETING;
    - instruksi perbaikan temuan;
    - di jalur lama, "LIMITATION names ... from the tools' reason codes".
  - Deskripsi skema yang dibaca model juga diselaraskan (temuan, jawaban sudut, metodologi).
  - Ukuran prompt dev naik dari +2,0% menjadi +8,6% terhadap fixture pass-2; batas baru `SIZE_BUDGET` 1,09.
  - Tercatat di `tests/test_prompt_pass2.py`: 9 kalimat dihapus dan 21 ditambah, urutan bagian, dan uji baru
    `test_no_sentence_asks_for_codes_or_names_in_the_readers_text`. Uji ini terbukti menangkap dua kalimat konflik di
    prompt lama.
  - Anggaran konteks uji dinaikkan sekitar lima ratus token, sebesar ukuran bagian baru.
  - Uji orc: 1.563 lulus.
  - Langkah berikut: GT kecil berbayar sebelum dan sesudah, diukur dengan `scripts/answer_plainness.py`. Hanya atas
    perintah user, dan kredit perlu dicek dulu.

**Riwayat system prompt (keputusan user 2026-10-08: "jangan lupa buat dokumentasi / history system prompt agar selalu
bisa fallback. Masukan ke daftar wajib di update").** Dibangun di cabang sesi:
- `scripts/snapshot_system_prompt.py` merekam prompt sistem dev dan skema jawaban akhir (deskripsi field-nya juga
  instruksi) ke `prompts/history/vNNN-tanggal-nama/`, lengkap dengan keputusan user, isi perubahan, ukuran dan sha256.
- Indeks `prompts/SYSTEM_PROMPT_HISTORY.md` mendaftar semua versi dan langkah kembali ke versi lama (redeploy build
  lama di Railway, atau `git revert` lalu rekam snapshot baru). Prompt lama selalu dikembalikan bersama kodenya.
- v001: prompt yang ter-deploy sebelum aturan pembaca (dirender dari commit e4795e0, sama dengan `main`). v002: aturan
  pembaca M125 C.
- `apps/market-ai-orc/tests/test_prompt_history.py` gagal bila kode merender prompt atau skema yang belum direkam.
- Masuk daftar wajib `AGENTS.md` (Mandatory workflow, System prompt).
- Cacat yang ditemukan sebelum commit: versi pertama skrip memuat ulang modul `app` di dalam proses uji, sehingga lima
  uji lain yang berjalan sesudahnya gagal (uji itu memasang tiruan pada salinan modul yang lama). Sekarang perenderan
  selalu berjalan di proses Python tersendiri. Hasilnya: 1.567 uji orc lulus, termasuk dengan urutan uji riwayat lebih dulu.

**Langkah berikut (user "Ok" 2026-10-08 atas "deploy ke dev lalu jalankan GT kecil"):** gabung ke `main`, deploy orc
dan edge-bff sampai SUCCESS, cek live tanpa biaya AI, cek kredit, GT kecil sebelum dan sesudah diukur dengan
`scripts/answer_plainness.py`, lalu catat di changelog.

**Deploy dan GT kecil (2026-10-08).** `main` `72478cd`: orc `30d161b7` dan edge-bff `d5f225d3` SUCCESS. GT kecil
`ma-plain-20261008a` (pertanyaan sama dengan gtA, gt_f, qa, golden_c; USD 0,099): jawaban yang memuat nama internal 9/9
sebelum (5,4 per jawaban) → 0/5 sesudah; kalimat median 17,7 → 15,0 kata. Cacat yang ditemukan dengan membaca jawaban
dan pratinjau (`ERRORS_AND_SOLUTIONS.md` M125 sisa, M126):
- P1 (M126): referensi ke teks (fakta web, nama di tabel referensi) menyisipkan kutipan utuh, sebagian berbahasa
  Inggris, ke tengah kalimat; nama perusahaan tertulis dua kali.
- P2: panel Sources menamai bukti "Angka dari sumber web: nilai" dan "Angka dari reference: company name,
  rows[ticker=bris]"; situs, kutipan dan tautan fakta web tidak tampil.
- P3: baris sistem yang masih memuat kode: "(bukti DIRUJUK)"; baris kebutuhan web "… peng [OK; bca.co.id, …]" (kode
  status, teks terpotong).
- P4: "Catatan data percakapan" di Sources menampilkan field internal (Version, Next alias, Seq).
- P5: ukuran kejelasan hanya membaca teks jawaban, bukan asumsi, batasan, metodologi dan label bukti.

**Keputusan user 2026-10-08** atas permintaan "jalankan pertanyaan yg related to web govt juga ya, liat apakah efisien
dan gimana uinya 5 pertanyaan mix": kredit "Saya naikkan batas kunci"; urutan "Perbaiki dulu" (usulan perbaikan dulu,
uji web 5 pertanyaan sesudah disetujui dan di-deploy). Usulan P1–P5 menunggu persetujuan.
- **Go P1–P5 (user 2026-10-08: "Ok p1-p5 masukan exec", jawaban atas "Go untuk P1–P5").** Urutan kerja: P1–P5
  dibangun dan diuji offline, deploy orc dan edge-bff sampai SUCCESS, lalu uji 5 pertanyaan web campuran lewat EDGE.
- **Dibangun 2026-10-08 (cabang sesi):** P1 `7dfc475`, P2–P3 `a607cef`, EDGE P2/P4 `cc694da`, mobile `6b06928`, P5 dan
  nama sumber tabel `2f27781`. Uji: orc 1.575 lulus, EDGE 52 lulus. Prompt sistem tidak berubah (v002 tetap). Bukti
  desktop tidak berubah: gaya terhitung semua elemen sama dengan dan tanpa blok mobile di 721, 1024 dan 1440 px,
  menu tertutup dan terbuka (dikunci di `test_frontend_contract.py`).
- **Deploy dan uji web 5 pertanyaan (2026-10-08):** `main` `1f14c5a`, orc `4b6a272e`, edge-bff `be697e72` SUCCESS.
  Lewat EDGE, satu percakapan per pertanyaan:

  | Pertanyaan | Jalur | Waktu | Biaya | Hasil |
  |---|---|---|---|---|
  | BUMN dan pengendali BBRI, BMRI, BBCA | FACT | 1 mnt 47 dtk | USD 0,003 | Benar, 7 link per klaim, nama dari tabel referensi (database dulu) |
  | BI-Rate terbaru | FACT | 1 mnt 46 dtk | USD 0,007 | Isi benar (5,75, 23 Sep 2026), tetapi LIMITED karena M129 |
  | Kenapa saham bank turun Agustus 2026 | ASK_BACK | 12 dtk | USD 0,002 | Salah bertanya balik "sekarang Juni 2026" (M130) |
  | Outlook ekonomi 2027 | EXPLORE (mode 4) | 14 mnt 57 dtk | USD 0,090 | Proyeksi lembaga dengan 18 link; M129; lalu rencana riset pasar yang tidak diminta (M127a) |
  | Batu bara 2026 dan ADRO/PTBA | EXPLORE (mode 4) | 14 mnt 25 dtk | USD 0,054 | Tabel bulanan batu bara (World Bank, link per sel) dan return saham dari database; M129; rencana riset tidak diminta |

  M129 diperbaiki (cakupan P1). M130 menunggu keputusan user.

**Go 2026-10-09 (user: "1 3 dan 4 - jalankan sekarang").** 1 = M130 (router menerima tanggal hari ini dan tanggal data
terbaru; benchmark router ulang dengan kasus waktu sebelum deploy), 3 = M128b (judul dan arti kolom XLSX dari katalog),
4 = tombol stop (rencana di bawah). M127a tetap ditunda.

**Permintaan jalur EXPLORE (user 2026-10-09: "untuk jalur explore harus tambahkan pertanyaan agar user bis dxplore
lebih lanjut dan kalau bisa jawaban selaij menjawab tapi juga ngomong history, serta forward event terkait
pertanyaan. konsep mitip v1/ask").** Desain disusun sesudah inspeksi `/v1/ask` web governor dan mode 4; dibangun
sesudah go.
- **Usulan desain 2026-10-09 (menunggu go; belum dibangun).**
  - Akar masalah (terverifikasi dari kode): putaran pertama EXPLORE (mode 4) = A analisis database + B rencana riset
    yang menunggu persetujuan. Tidak ada langkah yang mencari riwayat, peristiwa ke depan, atau menulis pertanyaan
    lanjutan; orc tidak memanggil `/v1/ask` (hanya `/v1/orc/web` dan `/v1/fact`). Padahal `/v1/ask` sudah punya
    ketiganya: jendela riwayat sampai 7 tahun, pencarian peristiwa mendatang plus `timeline` (waktu disalin persis dari
    sumber), dan 3–5 `follow_ups`; tanggal tiap fakta diambil dari daftar sumber, bukan dari model.
  - Kelas masalah: setiap pertanyaan terbuka (makro, sektor, emiten, komoditas, kebijakan, juga data lintas aset dan
    makro yang direncanakan) dijawab tanpa konteks waktu dan hanya dengan satu jalan lanjut (rencana riset mahal; M127a).
  - Usulan (lapis kontrak antar-layanan, permanen): putaran pertama EXPLORE menjalankan `/v1/ask` (W) sejajar dengan A.
    Jawaban gabungan: Jawaban (A + W), Riwayat, Peristiwa ke depan, Pertanyaan lanjutan (pilihan yang bisa diklik; klik
    = pesan berikutnya, tidak ada yang jalan tanpa klik). Sumber W didaftarkan sebagai sumber web orc sehingga klaim
    ber-link (keputusan C) dan gerbang angka tetap berlaku. Tombol stop dicek sebelum W.
  - Biaya dan waktu (perkiraan, diukur saat uji): W dibatasi anggaran `/v1/ask` (maks. sekitar USD 0,06, 180 detik) dan
    berjalan sejajar dengan A; uji web sebelumnya EXPLORE 14–15 menit, USD 0,054–0,090.
  - Juga berlaku untuk: "prospek batu bara 2026" (riwayat harga, aturan DMO yang dijadwalkan), "kenapa GOTO turun"
    (riwayat peristiwa, RUPS mendatang), dan nanti data makro (angka dari database, jadwal RDG BI dari W). Tidak untuk:
    FACT (satu nilai; riwayat dan peristiwa ke depan menambah biaya tanpa nilai) dan ekstrak Excel.
  - Pertanyaan untuk user: (1) rencana riset B di putaran pertama EXPLORE tetap otomatis, atau dijadikan salah satu
    pertanyaan lanjutan ("Uji dengan data: …"), yang sekaligus menyelesaikan M127a? (2) Pertanyaan lanjutan hanya di
    EXPLORE, atau juga di ANALYSIS (satu panggilan model kecil)?
  - **Keputusan user 2026-10-09 atas pertanyaan (2): "analysis OK - masukan exec".** Pertanyaan lanjutan juga dibuat
    di jalur ANALYSIS. Disetujui untuk direncanakan; pembangunan menunggu go bersama desain EXPLORE.
  - Pertanyaan (1) dijelaskan ulang (user: "maksudnya gimana ya?"), belum diputuskan. Ukuran dari uji web 2026-10-08:
    langkah rencana riset otomatis memakan 7,5 menit dan USD 0,056 (outlook 2027, 62% biaya) dan 5,5 menit dan USD
    0,026 (batu bara, 48% biaya), padahal user tidak meminta riset.
  - **Keputusan user 2026-10-09 atas pertanyaan (1): "explore pakai B --> masukan exec jangan execute dulu".** Putaran
    pertama EXPLORE menjawab plus 3–5 pertanyaan lanjutan yang bisa diklik; rencana riset tidak dibuat otomatis, tetapi
    menjadi salah satu pilihan ("Uji dengan data: …") yang disusun hanya bila diklik (menyelesaikan M127a). Belum
    dieksekusi; menunggu go.
- Keputusan user 2026-10-08 atas contoh (a)/(b)/(c) tanda sumber: "pakai C". Klaim web selalu diberi link ke halaman
  sumbernya (teks link = nama situs, alamat dari daftar sumber yang dibaca sistem, bukan diketik AI); angka database
  tanpa tanda di kalimat, asalnya di panel Sources.

**Uji ekstrak data ke Excel (keputusan user 2026-10-08: "Kita test yg nomor 2 ya masukan exec", nomor 2 = ekstrak
data ke Excel; user 2026-10-08: "Fitur excel tadi masukan exec": hasil uji dan perbaikan yang dibutuhkan dicatat di
sini).** Satu pesan lewat EDGE seperti user: foreign flow BBRI 1 tahun terakhir dalam Excel. Diukur: jalur
yang dipilih router, waktu, biaya, file XLSX terunduh lewat tombol Download EDGE, isi file (baris, rentang tanggal,
lembar definisi dan asal data), beberapa angka dicocokkan langsung ke database, dan apakah batas data aliran asing
(sekitar 31 Agustus 2026, belum terverifikasi penuh) disebut. Batas kunci dinaikkan user (limit 38, sisa USD 5,37).
- **Hasil 2026-10-08** (`edge_398b4589…`): router ANALYSIS, 5 menit 6 detik, USD 0,023, 13 langkah AI. File XLSX 26 KB
  terunduh lewat EDGE: 457 baris harian per board, lembar `definisi` dan `lineage`. Batas data 31 Agustus 2026 disebut
  di jawaban. Semua angka cocok dengan hitung ulang mandiri read-only lewat pgweb (total, jumlah hari, rentang
  tanggal, hari ekstrem). Cacat: M128 (a) tombol Download menampilkan kode file, diperbaiki di P4; (b) kolom file
  memakai nama internal dan lembar definisi tanpa arti kolom, usulan menunggu keputusan.
- **Uji ulang sesudah M128b 2026-10-09** (`edge_c97a5348…`, 3 menit 32 detik, USD 0,025): judul kolom terbaca, lembar
  `kolom`, definisi dan asal data dalam kata biasa; angka cocok dengan database. Sisa (ERRORS M128 c–e).
- **Pertanyaan user 2026-10-09: "apakah ini masalah? coba benchmark data extraction and data explanation best
  practice ya".** Pembanding: panduan GSS "Releasing statistics in spreadsheets" dan "Symbols in tables" (nol hanya
  untuk nol sebenarnya, sel kosong harus dijelaskan, catatan di lembar Notes, satuan di judul kolom), Broman & Woo 2018
  (kamus data, tidak ada sel kosong tanpa arti), Frictionless Table Schema (judul, deskripsi dan nilai hilang per
  kolom). Usulan, menunggu keputusan: E1 baris kelengkapan di lembar definisi, dihitung backend dari tabel sumber
  (jumlah hari di sumber vs di file, tanggal yang tidak ada); E2 arti kolom berbahasa Indonesia di katalog
  (`Column_Catalog`, 836 kolom, 48 tabel; draf dibuat model, status DRAFT, ditinjau); E3 setiap kolom buatan analisis
  wajib punya arti (model menulisnya bersama judul kolom).
- **Keputusan dan pertanyaan user 2026-10-09.** E1: "juga perlu baris kelengkapan saja? atau perlu yang lain? dan
  kenapa yg hitung backend?" (dijawab: kelengkapan dihitung backend sebagai jaminan; hari yang sumbernya mencatat nol
  sebenarnya ditulis 0, bukan dihilangkan; aturan baris "satu baris = …" di lembar definisi; jumlah hari di jawaban
  menyebut apa yang dihitung; belum diputuskan). E2: "kenapa tidak e2 let ai terjemahkan agar sesuai dengan bahasa
  indonesia in default language --> masukan exec jangan execute". Disetujui untuk direncanakan: arti kolom
  diterjemahkan AI ke bahasa Indonesia sebagai bahasa bawaan; teks Inggris di katalog tetap sumber. Pertanyaan terbuka:
  terjemahan disimpan sekali per kolom dan dipakai ulang (usulan: konsisten, murah) atau dibuat ulang setiap ekspor.
  Belum dieksekusi. E3: user bertanya maksud "6 dari 10 kolom" (dijawab); belum diputuskan.
- **Keputusan user 2026-10-09: "E1 ok 2-4 masukan exec".** E1 disetujui untuk direncanakan dengan keempat bagiannya:
  (1) baris kelengkapan dihitung backend; (2) hari yang menurut sumber nol sebenarnya ditulis 0, bukan dihilangkan; (3)
  aturan baris ("satu baris = …") di lembar definisi; (4) jumlah hari di jawaban menyebut apa yang dihitung. Belum
  dieksekusi; menunggu go. User bertanya: "ini hanya berlaku sekali saja kan? … kalau kita update table atau tambah
  data lain, maka model automatically understand this rule?" Desainnya berlaku umum, bukan sekali: (1) dan (3)
  diturunkan backend saat ekspor dari asal data, kolom tanggal dan kolom kunci hasil, jadi tabel baru tercakup tanpa
  ubah kode; (2) membaca arti "tidak ada baris" dari katalog (Part A A3.15: tabel yang hanya menulis baris saat ada
  aktivitas wajib dinyatakan sparse), jadi tabel baru wajib menyatakannya saat didaftarkan; (4) aturan umum untuk model,
  dan baris kelengkapan dari backend menangkap bila model keliru. Syarat yang perlu dicek saat go: apakah katalog sudah
  punya tempat untuk sifat sparse dan arti ketiadaan baris per tabel (D05 masih OPEN); bila belum, migrasi katalog dan
  pengisian untuk tabel yang ada.

**Tampilan mobile EDGE (permintaan user 2026-10-08: "mobile design juga perlu rapihkan terutama bagian bawah dan jump
to latest / jump to latest pada mobile view hilangkan saja / kemudian untuk bagian stadard, server model etc mungkin
bisa dibuat clean khusus untuk mobil sama seperti tampilan claude srkarang dimobile. penting: hanya berlaku untuk
mobile, bukan desktop. jangan ubah desktop.")** Dibangun bersama P4 (perubahan EDGE):
- Hanya di dalam media query lebar layar mobile di `static/index.html`; aturan desktop tidak disentuh.
- Tombol "Jump to latest" tidak tampil di mobile.
- Kotak tanya di mobile ringkas seperti aplikasi Claude: kolom teks di atas, satu baris di bawahnya berisi tombol
  pilihan (Standard, Data Scope, lampiran) dalam satu tombol bulat kecil, lalu tombol kirim bulat di kanan; "Server
  model" disembunyikan.
- Bukti: tangkapan layar mobile sebelum dan sesudah; DOM dan tangkapan layar desktop (1440 dan 1024 px) identik
  sebelum dan sesudah.

**Tombol stop (permintaan user 2026-10-08: "kita jg perlu tambah stop button, which fungsinya kaya stop ai processing.
saat ini sudah ada? jika belum masukan exec"; disetujui 2026-10-08: "Tombol stop OK masukan exec", dibangun sesudah
P1–P5).** **Dibangun dan ter-deploy 2026-10-09** (go "1 3 dan 4 - jalankan sekarang"; detail di
`ERRORS_AND_SOLUTIONS.md` M131):
- EDGE: selama jawaban berjalan, tombol Submit menjadi Stop (desktop dan mobile); sesudah ditekan menjadi "Stopping…".
- BFF: `POST /api/v1/runs/{id}/stop` (sesi dan CSRF dicek). Run yang masih antre diakhiri di BFF dan tidak pernah
  sampai ke AI; run yang berjalan ditandai di orc. 409 bila belum atau sudah tidak ada yang bisa dihentikan.
  `capabilities.cancel` = true.
- Orc: `POST /v1/agent/run/{id}/stop` (pemilik dicek; run orang lain tidak pernah terungkap). Tanda dibaca di batas
  yang sama dengan tenggat run (awal tiap langkah, sebelum tiap langkah mode 4), jadi tidak ada panggilan model baru;
  panggilan yang sedang jalan selesai. Jawaban memakai jalur "waktu habis": draf terakhir lewat semua gerbang, atau
  baris "dihentikan oleh Anda".
- Jawaban pertanyaan terbuka: orc satu replika, tanda di memori cukup. Job sandbox yang sedang jalan dibiarkan selesai.
- Uji live 2026-10-09 (`edge_8b5bde97…`): Stop ditekan detik ke-27, run berakhir 10 detik kemudian, USD 0,0049.
- **Pertanyaan user 2026-10-09: "bagaimana behaviour tombol stop? jika user mau nanya lagi, harus resend message? coba
  benchmark dengan external."** Perilaku sekarang (terverifikasi dari kode): jawaban "dihentikan oleh Anda" tersimpan di
  percakapan; kolom pesan kosong (pertanyaan dikosongkan saat dikirim), draf yang diketik selama proses tetap ada; pesan
  baru melanjutkan percakapan yang sama; untuk menanyakan ulang pertanyaan yang sama user harus mengetik ulang (tombol
  Retry yang mengembalikan pertanyaan ke kolom pesan hanya muncul untuk run gagal atau dihentikan saat antre).
  Pembanding: Claude Code (dokumen resmi: Esc menghentikan, pekerjaan yang sudah jalan disimpan, pesan yang diketik
  selama bekerja diantrikan, Esc+Esc mengembalikan draf atau memutar balik); ChatGPT agent (pengumuman OpenAI: bisa
  disela kapan saja, lanjut tanpa kehilangan kemajuan, berhenti dengan hasil parsial); ChatGPT chat, Gemini dan
  Perplexity: perilaku stop tidak ada di dokumen resmi yang ditemukan. Usulan, menunggu keputusan: S1 tombol "Ubah &
  kirim ulang" di jawaban yang dihentikan (EDGE, memakai Retry yang ada); S2 jawaban yang dihentikan menyebut tabel
  yang sudah selesai dan pesan berikutnya bisa memakainya (perlu dicek dulu apakah reuse data EXEC-V sudah berlaku
  untuk run yang dihentikan); S3 (nanti) kirim pesan selama proses = hentikan lalu arahkan ulang.
- **Keputusan user 2026-10-09: "ok tombol stop with best practice. masukan exec, janfan execute dulu".** S1, S2 dan S3
  disetujui untuk direncanakan, mengikuti pola pembanding (pekerjaan yang sudah jalan disimpan; arahkan ulang tanpa
  mengetik ulang; pesan selama proses = hentikan lalu arahkan ulang). Belum dieksekusi; menunggu go. Langkah pertama
  saat go: uji live apakah tabel dari run yang dihentikan bisa dipakai giliran berikutnya (S2), lalu desain S3.
- **Review S1–S3 terhadap infrastruktur (permintaan user 2026-10-09: "pls review kembali dengan kondisi infra.. saya
  rasa mungkin tidak semua bisa diaplikasikan karna sistem kita tidak sama dengan claude dll. kalau bisa then its good.
  masukan ke exec").** Fakta yang dicek di kode dan live:
  - Satu replika per layanan (`.railway/railway.ts`); tanda stop di memori orc cukup.
  - Satu run aktif per pemilik di BFF (`RUN_IN_PROGRESS`); orc menjawab satu giliran per permintaan, tanpa saluran untuk
    pesan baru di tengah run.
  - Yang sedang berjalan tidak bisa dibatalkan di tengah: panggilan model (batas 180 detik), `run_python` di sandbox
    (sesi tidak punya rute batal; hanya jalur analisis lama yang punya), pencarian web. Jadi Stop bisa menunggu sampai
    sekitar 3 menit dalam kasus terburuk (uji live: 10 detik).
  - Router pesan pertama (3–11 detik) berjalan sebelum run terdaftar untuk stop, jadi Stop di detik-detik awal dijawab
    "belum bisa, coba lagi".
  - Run yang dihentikan sudah menyimpan catatan datanya ke percakapan (uji live `edge_8b5bde97…`: 7 tabel dibaca, 1
    kebutuhan data tercatat), dan giliran berikutnya membacanya (M47).
  Kesimpulan per usulan:
  - S1 "Ubah & kirim ulang": bisa, di EDGE saja. Cek saat go: run yang dihentikan saat menjalankan rencana riset yang
    disetujui (apakah rencananya masih bisa disetujui ulang).
  - S2 pekerjaan disimpan: sebagian besar sudah ada (catatan data tersimpan). Yang kurang: jawaban yang dihentikan
    tidak menyebut apa yang sudah selesai, dan pemakaian ulang tabel hasil belum diuji live (biaya sekitar USD 0,01).
  - S3 kirim pesan selama proses: versi Claude Code/ChatGPT agent (mengarahkan run yang sedang berjalan tanpa
    berhenti) TIDAK cocok: orc tidak punya saluran pesan di tengah run, dan jaminan (data hanya setelah persetujuan,
    ambang terkunci pada kata user) mengharuskan pesan baru dibaca router sebagai giliran baru. Versi yang bisa: kirim
    selama proses = hentikan run lalu BFF mengantrekan pesan itu dan menjalankannya otomatis sebagai giliran berikutnya
    begitu run berhenti (BFF mengizinkan satu pesan antre per pemilik).
  - Tambahan dari review: I1 daftarkan run untuk stop sejak permintaan diterima (sebelum router), sehingga jawaban
    "coba lagi" hampir hilang; I2 tampilan "Stopping…" menyebut bahwa langkah yang sedang berjalan ditunggu selesai;
    I3 (opsional) rute batal untuk job sesi sandbox, sehingga `run_python` yang lama bisa dihentikan di tengah.

### EXEC-Y: rencana implementasi putaran 2026-10-09 (review semua butir EXEC yang disetujui; menunggu "go")

**Permintaan user 2026-10-09:** "Ok, untuk semua yang ada di exec pls review lagi baik secara arsitektur dan eksekusi.
Kalau ada yg tidak cocok feel free to contrast alih2 merubah arsitektur secara massive. Buat implementation plan dulu
sekarang." Rencana ini usulan; tidak ada kode yang diubah sampai user memberi "go" (per fase).

**Lingkup (butir yang disetujui dan belum dibangun):**
- Tombol stop S1–S3 (EXEC-X, "ok tombol stop with best practice") dan I1–I2 dari review infrastruktur.
- EXPLORE opsi B dengan riwayat, peristiwa ke depan dan pertanyaan lanjutan (EXEC-X, "explore pakai B"); pertanyaan
  lanjutan juga di ANALYSIS ("analysis OK").
- Excel E1 bagian 1–4 ("E1 ok 2-4") dan E2 terjemahan AI ("let ai terjemahkan").
- Gelombang B EXEC-W: V-f (SQL yang sama diambil sekali per jawaban) dan M119 A + B; GT V-g hanya atas perintah.

**Tidak termasuk (menunggu keputusan):** E3 (arti kolom buatan analisis), M123 (kata samar ditanyakan), target EXEC-D
"waktu sesudah penolakan ≤ 5%", M121 g (batas langkah/waktu), M127b (exa.ai), salah baca "BMRI kemarin" di router giliran.
M127a selesai lewat EXPLORE opsi B.

**Hasil review (dicek di kode dan dev 2026-10-09):**

| Butir | Cocok dengan arsitektur? | Kontras / penyesuaian (bukan perubahan arsitektur besar) |
|---|---|---|
| S1 "Ubah & kirim ulang" | Ya. EDGE sudah punya Retry (pertanyaan kembali ke kolom pesan); rencana yang dihentikan saat dijalankan tetap PENDING (M121 c), jadi bisa disetujui ulang | Orc menambah satu field `execution.stopped` supaya EDGE tahu jawaban itu dihentikan |
| S2 pekerjaan disimpan | Sebagian besar sudah ada: run yang dihentikan menyimpan catatan datanya (live: 7 tabel dibaca) dan giliran berikut membacanya (M47) | Yang dibangun hanya baris "yang sudah selesai" (diturunkan dari catatan data) dan uji live pemakaian ulang tabel hasil |
| S3 kirim pesan selama proses | Versi "mengarahkan run tanpa berhenti" (Claude Code, ChatGPT agent) tidak cocok: orc tidak punya saluran pesan di tengah run, dan jaminan (data sesudah persetujuan, ambang dari kata user) mengharuskan pesan baru dibaca router sebagai giliran baru | Diganti: kirim selama proses = stop + pesan diantrekan di BFF (disimpan di `jobs.input`, tanpa migrasi) dan dijalankan otomatis begitu run berhenti. Worker tidak mengambil pesan antre selama run pemilik yang sama masih aktif |
| I1 stop sejak permintaan diterima | Ya: router pesan pertama (3–11 dtk) kini berjalan sebelum run terdaftar | Pendaftaran dipindah sebelum `routed()` di `main.py` |
| I2 teks "Stopping…" | Ya | Menyebut bahwa langkah yang sedang berjalan ditunggu selesai (maks. sekitar 3 menit) |
| I3 batal job sandbox di tengah | Kurang cocok: sesi `run_python` tidak punya rute batal; mematikan proses menghapus isi sesi | Tidak dibangun sekarang; usulan ke `FUTURE_PLAN.md` |
| EXPLORE W (`/v1/ask`) | Ya: `/v1/ask` sudah aktif di web governor dev (riwayat, `timeline` peristiwa mendatang dengan waktu disalin dari sumber, `follow_ups`), dibatasi USD 0,06 dan 180 dtk; orc sudah punya `WEB_GOVERNOR_URL` | Teks jawaban `/v1/ask` tidak ditempel ke jawaban yang diperiksa gerbang angka (sumbernya tidak terdaftar di orc, angkanya akan ditandai). Diganti: backend menulis bagian "Riwayat" dan "Peristiwa ke depan" dari data terstruktur `/v1/ask`, tiap butir bertanggal dan ber-link, diberi label "dari berita" |
| EXPLORE riwayat | `/v1/ask` mencari 24 bulan secara bawaan, 7 tahun bila pertanyaan menanyakan kapan/seberapa sering | Tidak dipaksa 7 tahun untuk semua pertanyaan (waktu dan biaya naik); penilaian tetap di `/v1/ask` |
| EXPLORE opsi B | Ya: langkah B mode 4 (rencana otomatis) dilewati; pilihan "Uji dengan data: …" memakai mekanisme pilihan cepat yang ada (`options` {label, route}, route RESEARCH), jadi tanpa jenis aksi baru di EDGE | — |
| Pertanyaan lanjutan (EXPLORE + ANALYSIS) | Ya | Satu panggilan model kecil di orc untuk kedua jalur (`follow_ups` dari `/v1/ask` hanya jadi bahan), supaya bentuk dan aturannya sama. Dikirim lewat `options` dengan tambahan `kind: FOLLOW_UP`; klik = pesan berikutnya dengan rute pilihannya |
| E1(1) baris kelengkapan | Ya: asal data (tabel sumber, periode, filter) sudah ada di metadata ekspor | Bila kolom tanggal/kunci hasil tidak bernama sama dengan kolom tabel sumber, baris menyebut "tidak dapat dicek otomatis", tidak menebak. Dibandingkan dengan setiap tabel sumber yang punya kolom kunci itu, jumlah terbesar dipakai |
| E1(2) nol sebenarnya ditulis 0 | Butuh arti "tidak ada baris" per tabel; `Table_Catalog` belum punya tempatnya (D05 OPEN) | Satu kolom baru `row_presence` (DENSE, ACTIVITY_ONLY, NOT_APPLICABLE) lewat migrasi, diisi untuk 48 tabel dengan status bukan VERIFIED bila disimpulkan; model membacanya dari katalog |
| E1(3) aturan baris | Ya | Diturunkan di sandbox saat ekspor: kumpulan kolom non-angka terkecil yang unik |
| E1(4) jumlah di jawaban | Ya | Satu kalimat di WRITING FOR THE READER (snapshot prompt); baris kelengkapan backend tetap jaminannya |
| E2 terjemahan AI | Ya | Terjemahan dibuat sekali per kolom oleh DeepSeek lewat skrip, disimpan di kolom baru `Column_Catalog` (migrasi hasil generator, status DRAFT, bisa ditinjau), lalu dipakai ulang. Kolom tanpa terjemahan tampil dalam bahasa Inggris dengan tanda. Bahasa bawaan Indonesia; percakapan berbahasa Inggris memakai teks Inggris |
| V-f, M119 A + B | Rencana EXEC-W masih berlaku (sandbox masih menolak `RANGE_INCLUDES_TODAY` tanpa melihat request yang sama; `AI_PLANNER_PARALLEL_PARTS=2` di dev) | Kode sandbox dan orc berubah sejak 2026-10-08, jadi inspeksi ulang singkat di awal fase |

**Fase dan urutan (satu deploy dan satu cek per fase, supaya penyebab masalah jelas):**

| Fase | Isi | Layanan | Migrasi | Cek berbayar |
|---|---|---|---|---|
| 1 | Stop S1, S2, S3, I1, I2 | orc, edge-bff | Tidak | Stop live + kirim selama proses + lanjutkan, ±USD 0,03 |
| 2 | EXPLORE opsi B + W + pertanyaan lanjutan (EXPLORE dan ANALYSIS) | orc, EDGE | Tidak | 5 pertanyaan (makro, sektor, emiten, analisis, FACT sebagai kontrol), ±USD 0,40 |
| 3 | Excel E1(1–4) + E2 | Governor/sandbox (hitung kelengkapan), orc, EDGE | `Table_Catalog.row_presence`, `Column_Catalog` teks Indonesia | Terjemahan ±USD 0,05; ekspor BBRI ulang + satu tabel lain, ±USD 0,05 |
| 4 | Gelombang B: V-f + M119 A + B | sandbox, orc | Panduan metode v7, Tool_Catalog round baru | GT V-g + butir M119, hanya atas perintah, ±USD 0,40 |

**Rincian per fase:**
- **Fase 1.** Orc: `stop.running` sebelum `routed()`; `execution.stopped`; baris "yang sudah selesai" dari catatan
  data (`user_texts`). BFF: `POST /api/v1/runs` saat ada run aktif dengan `after_stop: true` = stop run itu + simpan
  pesan antre (satu per pemilik); `claim()` melewati pesan antre selama run pemilik aktif; pesan antre mewarisi
  `conversation_id` run sebelumnya. EDGE: Send saat proses = "Stop & kirim"; tombol "Ubah & kirim ulang" pada jawaban
  yang dihentikan; teks I2 di `edge-labels.js`. Tes: orc, BFF (antre, urutan, pemilik lain), browser.
- **Fase 2.** Orc `mode4.first_round`: langkah B tidak dijalankan untuk EXPLORE; W berjalan sejajar dengan A (konteks
  stop ikut ke thread); bagian Riwayat/Peristiwa ke depan ditulis backend; satu fungsi pertanyaan lanjutan (model
  router DeepSeek, keluaran terstruktur, 3–5 pertanyaan dengan rute) untuk EXPLORE dan ANALYSIS; pilihan "Uji dengan
  data: …" rute RESEARCH. EDGE: `options` dengan `kind: FOLLOW_UP` tampil di bawah "Pertanyaan lanjutan"
  (`edge-view.js`, `edge-labels.js`). Dokumen: `AI_MODELS.md` (panggilan baru, `PURPOSE`), `AI_ROUTER.md` dan benchmark
  router bila teks rute EXPLORE berubah, snapshot prompt bila prompt berubah.
- **Fase 3.** Migrasi `row_presence` dan teks Indonesia (generator, DRYRUN lalu APPLY lewat job sementara, dibaca
  balik); skrip terjemahan (keluaran ditinjau di git sebelum diterapkan). Ekspor: baris kelengkapan dan aturan baris di
  lembar definisi; nilai 0 untuk hari aktif sumber tanpa aktivitas mengikuti `row_presence` (penilaian model, dibantu
  katalog); kalimat E1(4) di prompt (snapshot). Part A A3.15 diperbarui: tabel baru wajib mengisi `row_presence` dan
  teks Indonesia.
- **Fase 4.** Seperti EXEC-W Gelombang B (B1 V-f, B2 M119), didahului inspeksi ulang singkat.

**Jaminan yang tetap:** data hanya sesudah persetujuan; setiap angka bersumber (bagian dari berita diberi label dan
link); tidak ada pilihan yang menjalankan sesuatu tanpa klik user; satu run aktif per pemilik; model dan provider tidak
berubah (`AI_MODEL`, `AI_PROVIDER_SORT`, saklar mode tetap).

**Risiko:**
- Fase 2 menambah panggilan web di setiap EXPLORE; bisa tumpang tindih dengan pencarian web langkah A. Diukur di cek
  5 pertanyaan (waktu, biaya, isi ganda).
- Pesan antre (S3) menunggu langkah yang sedang berjalan, sampai sekitar 3 menit.
- Terjemahan katalog bisa keliru: status DRAFT, ditinjau, teks Inggris tetap sumber.
- Kredit: sisa batas kunci sekitar USD 4,47; perkiraan semua cek ±USD 1,0. Kredit dicek sebelum tiap cek berbayar.

**Jalan balik:** per fase, redeploy deployment sebelumnya (orc `eddb0530`, edge-bff `415baf87`, sandbox `8c06ff02`);
migrasi hanya menambah kolom atau versi baru.

**Pertanyaan untuk user sebelum go:** urutan fase 1 → 2 → 3 → 4 setuju? Terjemahan E2 disimpan sekali per kolom
(usulan) setuju?

**Keputusan user 2026-10-09:** "setuju untuk urutan fase 1 2 3 4". Belum ada "go" untuk fase mana pun; pertanyaan E2
(terjemahan disimpan sekali per kolom) belum dijawab.

**Go Fase 1 (user 2026-10-09: "go for phase 1").** Fase 2–4 tetap menunggu go masing-masing.

**Hasil Fase 1 (2026-10-09; `main` `58388b0`, orc `b05fbdfe`, edge-bff `4043ccd4` SUCCESS; detail M131):**
- S1: orc menandai jawaban yang dihentikan (`execution.stopped`); EDGE menampilkan "Stopped by you." dengan tombol
  "Edit & resend" yang mengembalikan pertanyaan ke kolom pesan.
- S2: jawaban yang dihentikan menyebut yang sudah selesai ("Sebelum dihentikan: 7 data sudah dibaca dan 0 tabel hasil
  sudah selesai. Catatan itu ikut ke pesan berikutnya di percakapan ini.").
- S3: mengetik saat proses berjalan memunculkan "Stop & send": run berhenti, pesan itu jalan berikutnya di percakapan
  yang sama. Enter saja tidak menghentikan apa pun. Pesan yang menunggu bisa dihentikan juga.
- I1, koreksi premis: router pesan pertama ternyata sudah berjalan di dalam run yang terdaftar untuk stop (`mode4.run`),
  jadi tidak ada yang dipindah di orc. Celah yang sebenarnya ada di BFF (job sudah diambil worker tetapi belum sampai ke
  orc): kini job ditandai berhenti dan worker tidak pernah mengirim job yang ditandai; untuk job yang baru dikirim,
  BFF mencoba stop ke orc sampai 3 kali.
- I2: teks proses "Stopping — waiting for the current step to finish".
- Perbedaan dari rencana (R35): pesan yang menunggu tidak bisa menjadi job kedua karena database BFF mewajibkan satu job
  aktif per pemilik (`edge_bff_one_active_owner`). Tanpa migrasi, pesan itu disimpan di job yang sedang dihentikan
  (`input.next`) dan dijadikan job sendiri dalam transaksi yang sama saat job itu berakhir; aturan satu job aktif tetap.
- Uji: orc 1.585 lulus, EDGE 58 lulus (termasuk tes browser Stop & send lalu Edit & resend).
- Uji live (USD 0,03; `conv_40a3700d…`): "Bandingkan volatilitas harian BBCA, BBRI dan BMRI selama 2025", lalu pada
  detik ke-40 "Lanjutkan, tapi cukup BBCA saja" lewat Stop & send. Run pertama berhenti 4 detik kemudian (`stopped`
  true, baris S2 benar, USD 0,006); pesan kedua mulai 0,3 detik sesudahnya di percakapan yang sama dan selesai
  (COMPLETED, 3 menit 25 detik, USD 0,024). Catatan data run pertama terbawa (7 tabel, 1 kebutuhan data, 1 paket data
  ditawarkan). Paket data tidak dipakai ulang karena pertanyaan kedua meminta data lain (hanya BBCA, SQL berbeda);
  aturan opsi D hanya memakai ulang SQL yang sama (M113), jadi ini sesuai desain, bukan cacat.

**Go Fase 2 (user 2026-10-09: "ok gas go").** Fase 3–4 tetap menunggu go masing-masing.

**Hasil Fase 2 (2026-10-09; `main` `52104e6`, orc `4494ba03`, edge-bff `473a2117` SUCCESS):**
- EXPLORE opsi B: putaran pertama tidak lagi menyusun rencana riset; `/v1/ask` berjalan sejajar dengan analisis dan
  backend menulis "Riwayat dan konteks berita" (setiap kalimat ber-link, baris berangka tanpa sumber dibuang) dan
  "Peristiwa ke depan" (waktu disalin dari sumber). Biaya `/v1/ask` ikut dihitung di jawaban.
- Pertanyaan lanjutan, ide insight dan satu "Uji dengan data" (hanya EXPLORE dengan angka dari data) lewat satu
  panggilan model router setelah jawaban ANALYSIS, EXPLORE, INSIGHT atau CONTINUE; tidak setelah FACT, CHAT, rencana,
  pertanyaan balik, jeda atau jawaban yang dihentikan. Ide insight hanya yang tabelnya sudah dibaca percakapan ini.
  Klik = pesan berikutnya (router giliran yang menilai). Field respons baru `follow_ups`.
- Perbedaan dari rencana (R35): saran dikirim di field baru `follow_ups`, bukan di `options`, karena `options` dipakai
  aturan tanya-balik (pilihan cepat dan batas dua pertanyaan); klik mengirim pesan, bukan rute, supaya router giliran
  yang memutuskan jalurnya (prinsip EXEC-D). Teks rute EXPLORE di router ("ten minutes or more") tidak diubah agar
  kriteria router tetap; perkiraan waktunya kini usang (dicatat di M127).
- Uji: orc 1.591 lulus (tes lama "rencana menunggu di putaran pertama" diganti tes opsi B), EDGE 60 lulus (termasuk
  tes browser klik ide insight).
- Uji live (USD 0,30, sisa batas kunci USD 3,90):

  | Pertanyaan | Jalur | Waktu | Biaya | Hasil |
  |---|---|---|---|---|
  | Outlook ekonomi 2027 | EXPLORE | 4 mnt 25 dtk (sebelumnya 14 mnt 57 dtk) | USD 0,085 (0,090) | 105 sumber berita ber-link, 8 peristiwa ke depan, 5 pertanyaan lanjutan, 3 ide insight |
  | Batu bara 2026, ADRO/PTBA | EXPLORE | 4 mnt 14 dtk (14 mnt 25 dtk) | USD 0,072 (0,054) | 255 sumber, 8 peristiwa, 5 + 3 saran, 1 uji dengan data |
  | Kenapa GOTO turun 3 bulan | EXPLORE | 8 mnt 5 dtk | USD 0,117 | 118 sumber, 0 peristiwa, 5 + 3 saran, 1 uji dengan data |
  | Return BBCA vs BBRI 2025 | ANALYSIS | 32 dtk | USD 0,009 | 5 pertanyaan lanjutan, 3 ide insight |
  | BI-Rate terbaru | FACT | 1 mnt 15 dtk | USD 0,003 | Tanpa saran (sesuai desain); cacat lama M132 terlihat |
  | Klik ide insight "return bulanan BBCA dan BBRI …" | CONTINUE | 1 mnt 15 dtk | USD 0,018 | Terjawab dari data yang sama (Maret paling berbeda) |

**Permintaan user 2026-10-09 sesudah Fase 2: "sumber untuk berita bisa dihilangkan, saat ini terlalu banyak hyperlink
dan nama source berita".** Belum dibangun; menunggu pilihan user (lihat jawaban di percakapan):
- Asal link di jawaban EXPLORE (terverifikasi dari kode dan jawaban live): (1) bagian "Riwayat dan konteks berita"
  dari `/v1/ask`, satu link per kalimat (outlook 2027: 105 sumber); (2) klaim web langkah analisis (alat
  `research_web`, aturan pilihan C 2026-10-08: link setelah setiap nilai web, sekali per kalimat).
- Usulan: link di teks dihapus dan semua sumber pindah ke panel Sources (judul, situs, tanggal, tautan); pemeriksaan
  "angka tanpa sumber dibuang" tetap berjalan di backend sebelum link dihapus, jadi jaminan "setiap angka bersumber"
  tetap, hanya tempat sumbernya yang pindah. Pilihan cakupan: hanya bagian berita, atau juga klaim web langkah
  analisis (berarti mengganti keputusan pilihan C).
- Pertanyaan user yang sama: "ada berapa jalur jawaban yg dipakai untuk pertanyaan qualitative?" (dijawab di
  percakapan: CHAT, FACT, ANALYSIS dengan web sebagai konteks, EXPLORE; ditambah tanya balik).

**Keputusan user 2026-10-09 (sesudah jawaban di atas), dengan "gas" sebagai go:**
- "bisa untuk explore jalur khusus v1/ask di exclude dulu. jalurnya lain keep as is masukan exec": dibaca sebagai usulan
  jalur khusus pertanyaan kualitatif murni langsung ke `/v1/ask` tidak dibangun sekarang (dicatat di
  `FUTURE_PLAN.md`); jalur lain, termasuk EXPLORE dengan `/v1/ask` yang sudah ter-deploy, tetap seperti sekarang.
- "Ok untuk B semua link web hilang pindah ke source masukan exec": semua link web hilang dari teks jawaban (bagian
  berita dan klaim web langkah analisis; menggantikan pilihan C 2026-10-08) dan sumbernya tampil di panel Sources.
  Jaminan tetap: angka tanpa sumber dibuang di backend sebelum link dihapus. M132 (angka web tercetak dua kali) ikut
  diperbaiki karena berada di kode tampilan yang sama.
- Mobile: "jawaban teks terlalu besar font size compared to the other, pls standardized" (tangkapan layar: kolom tanya
  dan tombol Standard di layar ponsel) → ukuran huruf mobile diseragamkan, hanya di mobile.
- "setelah semua fase selesai, uji interaksi dimobile dan web animasi dll. teks rusak, tidak align, broken silahkan
  dibenarkan tanpa merubah design site" → Fase 5 (QA tampilan mobile dan desktop) sesudah Fase 4.
- E2 tidak dijawab ulang; dipakai usulan: terjemahan disimpan sekali per kolom dan dipakai ulang.

**Go Fase 4 dan 5 (user 2026-10-09: "lanjut fase 4 dan 5 dulu").** Fase 4 = Gelombang B EXEC-W (B1 V-f, B2 M119 A+B),
didahului inspeksi ulang singkat; GT V-g dan item M119 tetap hanya atas perintah. Fase 5 = QA tampilan mobile dan
desktop. Usulan P1/P2 (hari aktif kelompok di baris kelengkapan; tabel dengan butir yang sama) dan bahasa teks backend
belum diputuskan ("dulu"): dicatat di `FUTURE_PLAN.md`.

**Hasil Fase 5 (2026-10-09, go "lanjut fase 4 dan 5 dulu"; ter-deploy dan dicek live):**
- QA tanpa panggilan model: percakapan nyata di EDGE dev dibuka di lebar 390, 820, 1024 dan 1440 px (gulir per layar,
  tema terang, menu Standard, laci riwayat, Details/Sources, kolom tanya panjang). Tidak ada halaman yang melebar ke
  samping di lebar mana pun.
- Diperbaiki (ERRORS M135, `dfdabf7`, hanya `static/index.html`, desain tidak berubah): satu perataan per kolom tabel
  (angka rata kanan bila semua isi kolom berupa angka); chip status "Dirujuk" di Sources tidak lagi patah jadi dua baris
  di ponsel; placeholder "Search markets" dan cari percakapan memakai "…" bila tidak muat; footer samping tanpa kata
  "Updated" yang tertinggal.
- Tes EDGE 61 lulus. edge-bff `a225ddfc` **SUCCESS**; QA diulang di live: semua temuan di atas hilang.
- Belum tercakup: judul berbahasa Inggris dari backend (misalnya "Industry & policy context") ikut keputusan bahasa teks
  backend yang masih ditunda.

**Hasil Fase 4 (2026-10-09, go "lanjut fase 4 dan 5 dulu"; ter-deploy, uji live menunggu perintah):**
- B1 V-f (ERRORS M134): data dengan SQL Governor yang sama diambil sekali per jawaban: sandbox memakai ulang potongan
  dari jawaban yang sama walau rentangnya sampai hari ini; dua permintaan dalam satu rencana berbagi satu file
  (`same_as`); dua persiapan data yang berjalan bersamaan saling menunggu lalu memakai ulang.
- B2 M119: sesi bisa membaca tabel buatannya sendiri menurut id atau nama (label "belum dirilis"); tabel kerja
  `save_table`/`load_table` dengan kuota disk (bawaan setengah disk sementara sesi), tidak dirilis dan tidak dikutip;
  `event_study`/`backtest` menyebut semua tabel yang dibuatnya; pesan penolakan menyebut langkah berikutnya.
- AI tahu lewat: tampilan sesi, `run_python` v6 (Tool_Catalog round Q), panduan metode v7, AI_TOOLS.md.
- Migrasi `20261009_005` (panduan v7) dan `_006` (round Q) diterapkan dan dibaca balik.
- Tes: orc 1.607 lulus; sandbox 809 lulus. Deploy: sandbox `e46c0ba5`, orc `540227e6` (di-redeploy sesudah sandbox
  SUCCESS), keduanya SUCCESS, tanpa peringatan kapabilitas.
- Uji live (GT V-g dan item M119, ±USD 0,40) hanya atas perintah user.

**Hasil Fase 3 (2026-10-09, go "gas"; ter-deploy dan dicek live):**
- Migrasi `20261009_002` (diterapkan, dibaca balik): `AI_table_catalog.row_presence` (5 tabel bertanggal
  ACTIVITY_ONLY, 4 tabel tanpa tanggal NOT_APPLICABLE, status INFERRED) dan `AI_column_catalog.description_id`
  (172 dari 173 arti kolom diterjemahkan sekali oleh DeepSeek, USD 0,034, status DRAFT). Tool_Catalog round O
  (research_web v2 tanpa link, export_result v3) dan round P (export_result v4 `source_columns`).
- E1(1)+(3): lembar `definisi` Excel menulis "Aturan baris" (diturunkan dari file) dan "Kelengkapan" per kelompok
  (satu ringkasan SQL Governor dengan saringan yang sama, atas periode file sendiri), atau "tidak dapat dicek
  otomatis" bila tidak bisa dihitung dengan cara yang sama.
- E1(2)+(4): prompt v003 (arti baris yang tidak ada dari `row_presence`; jumlah hari menyebut apa yang dihitung).
  Batas ukuran prompt naik dari 1,09 ke 1,10 (empat kalimat, +0,5%).
- E2: lembar `kolom` memakai arti berbahasa Indonesia; kolom tanpa terjemahan ditandai "teks Inggris".
- Uji live 1 (`edge_58b3a299…`, USD 0,037): aturan baris benar, tetapi kelengkapan "tidak dapat dicek" dan arti kolom
  kosong karena analisis mengganti nama kolom (`Date` → `trading_date`). Diperbaiki hari yang sama: model menyebut
  kolom sumber tiap kolom yang disalin (`source_columns`), backend memeriksa dan menghitung.
- Uji live 2 (USD 0,023): file harian "file memuat 211 tanggal; sumber punya data pada 211 hari" dari 211 hari bursa;
  dicek independen lewat pgweb (211 hari, net −Rp 20.152.871.413.000 sama dengan total file). File bulanan jujur "tidak
  dapat dicek otomatis". Saringan di lembar definisi kini satu baris kata biasa.
- Belum tercakup: model belum menulis nol untuk hari tanpa transaksi asing di papan Nego (uji 1: Nego 210 hari); baris
  kelengkapan dan catatan aktivitas sekarang menjelaskannya kepada pembaca. Arti kolom buatan analisis (E3) tidak
  disetujui. Ulasan manusia atas `row_presence` dan terjemahan (DRAFT) masih terbuka.

**Hasil B dan ukuran huruf mobile (2026-10-09, ter-deploy):**
- `main` `0bffe46` lalu `522cb50`: market-ai-orc `12f35049` dan edge-bff `9044798d` **SUCCESS**.
- B: teks jawaban tanpa link web dan tanpa nama situs; sumber web dan berita ada di panel Sources (berita sebagai bagian
  "Berita"). Angka tanpa sumber tetap dibuang di backend lebih dulu.
- M132: nilai web yang sudah tertulis di kalimat yang sama (angka dalam gaya desimal apa pun, atau tanggal dalam bentuk
  tulisan apa pun) tidak dicetak lagi. Cek live pertama menemukan "23 September 2026 2026-09-23"; tanggal ditambahkan
  di `522cb50`.
- Cek live (FACT BI-Rate, USD 0,012): 0 link di teks; halaman bi.go.id tampil di Sources.
- Mobile: kolom tanya dan placeholder 14px, sama dengan teks pesan (hanya di layar ≤ 720px); pengaman zoom hanya untuk
  iOS. Tes browser memeriksa ukuran yang sama. Desktop tidak berubah.

**Tambahan Fase 2 (user 2026-10-09: "Pertanyaan lanjutan … —>+ tambah idea research boleh?", lalu dikoreksi: "maksudnya
bukan idea research, tapi ide untuk pertanyaan insight lanjutan").** Dimasukkan ke desain Fase 2, menunggu go bersama
fasenya. Usulan "ide riset" sebelumnya dibatalkan; pilihan "Uji dengan data: …" (EXPLORE opsi B) tetap satu butir.
- Fungsi pertanyaan lanjutan yang sama menghasilkan juga 2–3 ide pertanyaan insight: pertanyaan yang menggali lebih
  dalam dari data yang ada (perbandingan, rincian per kelompok atau periode, tren, pemicu), misalnya "Bagaimana aliran
  asing BBRI dibanding BBCA di periode yang sama?" atau "Bulan apa jual asing BBRI paling besar, dan apa yang terjadi
  saat itu?".
- Ide diturunkan dari data yang tersedia: fungsi itu menerima tabel dan cakupan yang sudah dibaca (catatan data) dan
  ringkasan katalog, jadi hanya mengusulkan yang bisa dijawab, juga untuk tabel baru nanti tanpa ubah kode.
- Klik ide = pesan berikutnya dengan rute INSIGHT (satu langkah analisis, rute yang sudah ada di router giliran), bukan
  rencana riset; jadi cepat dan murah. Data tetap lewat jalur dan gerbang biasa.
- Biaya: tanpa panggilan tambahan (satu panggilan yang sama).
- EDGE: tampil di bawah judul "Ide insight" (`kind: INSIGHT_IDEA`, kata di `edge-labels.js`), terpisah dari
  "Pertanyaan lanjutan".
- Cek Fase 2: dari 5 pertanyaan uji, setiap ide insight yang diklik harus terjawab dari data yang ada; dihitung berapa
  yang ternyata tidak bisa dijawab.

### EXEC-Z: M139 dan M140 (hasil buangan dan pilihan angka ganda)

**Keputusan user 2026-10-09:** "Ok perbaikan untuk M139 langsung jalankan sekarang saja dan M140 langsung jalankan sekarang." Bukti: run `edge_87c8c408…` (ERRORS M139, M140).
- M139 (sandbox): jawaban `run_python` yang gagal tidak lagi mencantumkan tabel yang dibuatnya di `outputs`; tabel itu ada di `discarded_outputs` dengan satu kalimat bahwa `complete_analysis` tidak akan merilisnya dan harus dibuat ulang di eksekusi yang benar (tabelnya tetap bisa dibaca dengan `load_output(name)`). Aturan rilis tidak berubah.
- M140 (orc): permintaan perbaikan angka ketikan (`TYPED_FIGURES`) menyebut alamat nilai yang sama dengan setiap angka (paling banyak 6 per angka), supaya AI tinggal memilih. Angka yang cocok dengan lebih dari satu nilai tetap tidak dirujuk otomatis.
- Tes: sandbox 810 lulus (`test_dataneed_completion.py`: hasil buangan dan rilis sesudah dibuat ulang); orc 1.608 lulus (`test_g23_desk.py`: kandidat disebut, tanpa kandidat bila tidak ada yang sama).

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
