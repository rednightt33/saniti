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

**Selesai dan ter-deploy (go 2026-10-12, "ok"; label diperbarui 2026-10-13 dari bukti yang sudah tercatat):** EXEC-JOINKEY (G25), EXEC-RELEASE (sisa M139), EXEC-FRICTION (P0, M142) dan
EXEC-STYLE, dengan rencana implementasi bersama EXEC-IMPL-1012 (3 fase). Sesudah A/B, EXEC-STYLE kembali ke gaya Run A
tanpa kewajiban asumsi/batasan (keputusan user 2026-10-12).

**Selesai dan ter-deploy (go 2026-10-12, "2 dan 3 OK untuk jalankan masukan EXEC"):** EXEC-EXPORT dan EXEC-TYPING (perbaikan EDGE).
**Selesai dan ter-deploy (go 2026-10-12, jawaban user atas tiga pertanyaan hapus):** EXEC-SORT, EXEC-UI-1012 (B1, C)
dan EXEC-DELETE; juga EXEC-DETAILS (+ M144) dan EXEC-DURATION.

**Dihapus dari EXEC 2026-10-13 (user: "remove from EXEC"; selesai dan ter-deploy, teks lengkap di git `b9ccb2e`):**
EXEC-TABLE (saklar `AI_ENABLE_TABLE_DIRECTIVES` hidup sejak EXEC-DAYS), EXEC-M143 (a)+(c) dan solusi 1 (orc
`06da1d23`), EXEC-REASONING `medium` (orc `82cdb137`), EXEC-IMPL-1013 (rencana eksekusinya). Riwayat deploy di
RAILWAY_CHANGELOG.md, masalahnya di ERRORS_AND_SOLUTIONS.md.
**Menunggu keputusan:** M145, M146, EXEC-DETAILS butir 1 (tampilan mobile saat scroll).

**Berjalan (2026-10-08):** EXEC-X (M124 + M125 A/B, tampilan jawaban EDGE). Dibangun di cabang
`claude/code-session-2k3oeg` (HTML user sebagai sumber utama, API dipisah dari tampilan, teks backend bahasa biasa);
uji lulus (orc 1.563, EDGE 46). Ter-deploy dari `main` `72478cd` dan `1f14c5a` (lihat EXEC-X; label diperbarui 2026-10-13 dari bukti yang sudah tercatat).

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

## Butir terbuka per layanan (review 2026-10-15, user: "review all exec dulu ya. Pisahkan saja yg terkait orc, yg terkait bff dan yg terkait bff + orc agar tidak tumpang tindih")

| Kelompok | Butir | Status | Berkas utama |
|---|---|---|---|
| orc/backend saja | EXEC-BE1-1 label hasil toleran | **ter-deploy 2026-10-15** (sandbox `b1f26312`; M158); cek live menunggu saldo | sandbox `runtime/saniti_session.py` |
| orc/backend saja | EXEC-BE1-2 catatan katalog `total_buy/sell_value` | **diterapkan 2026-10-15** (`20261015_011`; temuan M157) | migrasi katalog |
| orc/backend saja | PLAN 14 lampiran data ke sesi terbuka | **ter-deploy dengan saklar mati 2026-10-15** (sandbox `88739487`, orc `7ce61160`, `round_u`); A/B atas perintah user (berbayar) | sandbox `sessions.py`, orc `tools/session.py`, `data_need.py` |
| orc/backend saja | M145 panggilan model `RemoteProtocolError` tidak diulang | usulan, menunggu keputusan | orc `openrouter_client.py` |
| orc/backend saja | Panjang adaptif (EXEC-FASTLANE) | ditunda | orc prompt |
| orc/backend saja | M154 b cek profil, M155 normalisasi bentuk | usulan, belum disetujui | katalog, validator |
| BFF/EDGE saja | EXEC-UI-1015 U1 Asumsi/Batasan menutup sendiri (M156) | **ter-deploy 2026-10-15** (edge-bff `0eb6c761`) | `static/index.html` `patchNode` |
| BFF/EDGE saja | U2 celah di atas kolom tanya | **ter-deploy 2026-10-15** (18 px) | `static/index.html` CSS |
| BFF/EDGE saja | U3 lebar kolom ~768 px selalu | **ter-deploy 2026-10-15** | `static/index.html` CSS |
| BFF/EDGE saja | U5 pemilih model ponsel (level + Jalur ke kanan kartu, panel di atas kolom tanya) | **ter-deploy 2026-10-15** | `static/index.html` |
| BFF/EDGE saja | EXEC-DETAILS butir 1 (ponsel saat gulir) | menunggu penjelasan user | — |
| BFF + orc | U4 tabel sampai 50 baris, dilipat | **ter-deploy 2026-10-15** (EDGE `0eb6c761`, orc `abeadb31`, prompt v008); run live tabel >10 menunggu saldo | orc `table_directives.py`, prompt (snapshot); EDGE lipatan |
| BFF + orc | EXEC-UI-1015B progres run seperti Claude | usulan, menunggu go | orc progres, BFF snapshot, `edge-client.js` |

Tumpang tindih: U1, U2, U3, U4 (bagian EDGE) dan U5 mengubah `static/index.html` → satu putaran EDGE; U4 (orc) dan PLAN 14 sama-sama di `orchestrator.py`/alat → urut, bukan paralel; UI-1015B menyentuh `edge-client.js` status run → sesudah putaran EDGE.

### EXEC-IMPL-1015: rencana implementasi butir yang disetujui (2026-10-15; go 2026-10-15; selesai kecuali cek berbayar)

**Hasil (2026-10-15).** Fase 1 EDGE `e3ccf5d` (edge-bff `0eb6c761`); Fase 2 `c997c4d` + `bb2430d` (sandbox `b1f26312`,
orc `abeadb31`); Fase 3 migrasi `20261015_011`; Fase 4 `4d9a3cd` (sandbox `88739487`, orc `7ce61160`, saklar
`AI_ENABLE_SESSION_ATTACH` mati, Tool_Catalog `round_u`). Semua deploy SUCCESS; suite EDGE 96, sandbox 851, orc 1.791
lulus. **Belum:** cek live berbayar U4/BE1-1 dan A/B PLAN 14 (saldo kunci OpenRouter $0,37 dari $41; menunggu user).

Go: user 2026-10-15 "Ok jalankan" atas checklist rinci di bawah. A/B berbayar Fase 4.19 tetap menunggu perintah
terpisah.

User 2026-10-15: "Sekarang inspect architecture, align dengan approved exec. Buat implementation plan. Describe before after kira2 end result arsitekturnya akan seperti apa."

#### Context

User meminta: "inspect architecture, align dengan approved exec. Buat implementation plan. Describe before after kira2
end result arsitekturnya". Butir yang **disetujui** (EXEC.md "Butir terbuka per layanan", PLAN 14):

- BE1-1 label hasil toleran (sandbox) · BE1-2 catatan katalog `total_buy/sell_value` (katalog DB)
- PLAN 14 lampiran data ke sesi terbuka, batas 2 (sandbox + orc)
- U1 Asumsi/Batasan menutup sendiri (M156) · U2 celah di atas kolom tanya · U3 kolom ~768 px selalu (EDGE)
- U4 tabel sampai 50 baris, 10 terlihat, sisanya dilipat (orc + EDGE)
- U5 pemilih model ponsel: kartu tetap, level berpikir **dan Jalur** pindah ke ruang kanan kartu ("kotak A"), panel di
  area kosong percakapan di atas kolom tanya (user 2026-10-15: "ya dipindah")

**Tidak termasuk** (belum disetujui): UI-1015B progres ala Claude, M145, M154b, M155, panjang adaptif. Jalur yang live
adalah jalur Cepat: semua perubahan orc berlaku di jalur Cepat dan Standar kecuali disebut lain.

#### Arsitektur sebelum → sesudah (ringkas)

```
SEBELUM                                          SESUDAH
EDGE  index.html                                 EDGE
  patchNode hapus atribut "open" tiap render       patchNode pertahankan "open" <details> tak terkontrol
  kolom 1120 px; jarak 22+32+12 px                 kolom 768 px (jawaban + kolom tanya); satu jarak ~18 px
  tabel tampil semua baris (maks 25)               tabel >10 baris: 10 tampil + "Tampilkan N baris lagi"
  pemilih model ponsel: lembar layar penuh,        pemilih di area percakapan di atas kolom tanya; level +
  level & jalur di bawah daftar                    jalur di kanan kartu model terpilih
orc
  table_directives MAX_ROWS 25, prompt "≤25"       MAX_ROWS 50, prompt "≤50, rincian lengkap tampil penuh,
                                                   jangan potong data di kode kecuali user minta top N"
  data tambahan → need baru → paket baru →         need baru dengan attach_to_session → paket → DILAMPIRKAN
  SESI BARU (variabel hilang)                      ke sesi yang sama (variabel tetap); gagal → sesi baru
sandbox
  label salah format → eksekusi gagal              thresholds list→dict, satuan tak dikenal dibuang + peringatan
  1 sesi = 1 paket, permintaan dipasang saat buka  1 sesi = paket awal + ≤2 lampiran; view DuckDB ditambah
                                                   lewat op worker "attach"; cakupan per need, lampiran tak
                                                   dipakai = "tidak dipakai" (bukan gagal)
katalog DB
  deskripsi buy/sell tanpa catatan identitas       deskripsi + misuse_warning: total beli = total jual
```

Jaminan yang tidak berubah: data hanya lewat Governor; setiap angka bersumber; data yang dikutip dibaca penuh; hasil
eksekusi gagal tidak dirilis (M139); jalur riset yang disetujui tidak bisa melampirkan data di luar rencana (EXEC-D).

#### Fase 1 — EDGE saja (U1, U2, U3, U5, bagian EDGE U4) · satu deploy edge-bff

File: `apps/edge-bff/static/index.html` (perilaku + CSS), kata baru di `static/edge-labels.js`.
1. **U1** `patchNode` (~baris 10140): saat menghapus atribut yang tidak ada di node baru, lewati `open` pada `<details>`
   bila `node._props` tidak punya `open` (lipatan terkontrol seperti `edge-flow-accordion` tetap mengikuti state).
2. **U2** gap: `.research-exchange` margin-bottom 22 px, `.research-scroll` padding-bottom 32 px (~8970), composer
   margin-top 12 px → percakapan terakhir tanpa margin bawah, satu jarak ~18 px. Ponsel (`padding-bottom:8px`, ~9989)
   tidak berubah.
3. **U3** `--conversation-max-width: 1120px` (~9693) → 768px untuk jawaban, kolom tanya dan `jump-latest`; tabel lebar
   tetap bergulir horizontal + tombol perbesar (dialog lebar EDGE V4). Cek `user-message max-width:90%` tetap rapi.
4. **U4-EDGE** di `renderMarkdown` (~11165): tabel dengan >10 baris badan → 10 baris tampil, sisanya dalam baris yang
   disembunyikan + tombol "Tampilkan N baris lagi"/"Sembunyikan" (state per tabel, bertahan saat render ulang karena
   memakai `updateValue`); dialog perbesar selalu menampilkan semua baris; urut kolom (EXEC-SORT) bekerja pada semua
   baris. Berlaku juga untuk tabel lama (≤25).
5. **U5** komponen pemilih model (~10880): `edge-model-option` tetap; tombol level (`current.reasoning_levels`) dan
   jalur (`data.lane_selection`) dipindah ke kolom kanan kartu yang `aria-pressed=true` (kartu lain: ruang kanan kosong /
   level bawaan tampil redup); menu ponsel (CSS ~10002) dari lembar `position:fixed` layar penuh menjadi panel di atas
   kolom tanya selebar kolom percakapan, `max-height` = ruang di atas kolom tanya. Desktop: posisi popover sama, isi
   kartu ikut tata letak baru.
6. Tes: `tests/test_visual.py`, `test_frontend_contract.py`, `test_browser.py` + tes baru: klik lipatan → gulir → tetap
   terbuka; jarak kartu terakhir–kolom tanya; lebar kolom ≤768; tabel 30 baris → 10 tampil, tombol membuka 30; pemilih
   model ponsel: level/jalur di kartu terpilih, panel tidak menutupi header.
7. Deploy edge-bff, cek live: skrip QA Playwright yang sudah ada (`scratchpad/qa/qa.py`, `interact.py`, `notes2.py`,
   `gap.py`) desktop 1440/1920 + ponsel 390, terang/gelap; tangkapan layar dikirim ke user.

#### Fase 2 — sandbox BE1-1 lalu orc U4 · deploy sandbox, lalu orc

1. **BE1-1** `apps/market-python-sandbox/runtime/saniti_session.py`: `_units` (~2121) satuan di luar
   `VALUE_UNITS` → dibuang + `_WARNINGS.append({"code":"UNIT_DROPPED",...})`, bukan `InvalidOutput`; kolom tak ada tetap
   ditolak. `_definition` (~2158): `thresholds` list → dict (item `{name,value}` jadi pasangan; item lain `threshold_1..n`)
   + peringatan `THRESHOLDS_CONVERTED`. Pesan penolakan yang tersisa menyebut cukup label yang dikirim ulang. Tes
   `tests/test_output_definition.py` (+ kasus baru). Method guide/HELPERS tidak berubah kecuali kalimat contoh.
2. **U4-orc** `apps/market-ai-orc/app/table_directives.py` `MAX_ROWS` 25 → 50 (`TABLE_CAPPED_LINE` ikut); prompt
   rule 13 `orchestrator.py` (~864–871): "tampilkan jumlah yang diminta user, 10 bila tidak; tabel rincian lengkap (semua
   kelompok) tampil penuh sampai 50; jangan memotong hasil di kode (nlargest/head) kecuali user meminta top N — rilis
   hasil lengkap, tampilan yang memilih; >50 tawarkan Excel". Snapshot prompt (`scripts/snapshot_system_prompt.py record`),
   tes `test_table_directives.py`, `test_prompt_history.py`, anggaran prompt bila naik.
3. Deploy sandbox (tunggu SUCCESS) → orc (SUCCESS, startup tanpa `*_inactive`). Cek live satu pertanyaan jalur Cepat
   dengan tabel >10 baris (berbayar kecil, cek saldo kunci dulu).

#### Fase 3 — BE1-2 katalog (migrasi)

Migrasi baru `database/migrations/2026101x_00N_feature03_buy_sell_identity.sql`: `UPDATE` `AI_column_catalog`
(`description`, `description_id`, status DRAFT) dan `Feature_Catalog` aktif (`misuse_warning`, `validation_evidence` +
bukti pgweb) untuk `total_buy_value`, `total_sell_value` (pola UPDATE di tempat seperti `20261012_003`).
`Column_Catalog` tidak diubah langsung: disinkron dari Feature_Catalog oleh `sync_database_catalog.py`; status tidak
dinaikkan. Jalankan lewat job `mmig-job` (DRYRUN → APPLY →
hapus job), baca balik lewat pgweb, `sha256sum >> APPLIED.sha256`, `audit_feature_catalog_semantics.py`,
`DATABASE_SCHEMA.md` (bagian terkait saja), `DATABASE_CHANGELOG.md`.

#### Fase 4 — PLAN 14 lampiran data · deploy sandbox, lalu orc (saklar mati), A/B atas perintah

**Sandbox** (`app/sessions.py`, `app/dataneed_service.py`, `app/main.py`, `runtime/session_worker.py`,
`runtime/saniti_session.py`, `app/config.py`, `app/dataneed_store.py`):
- Faktorkan pembuatan `requests` dari `_launch` (~840–870) jadi fungsi bersama.
- `POST /v1/sessions/{id}/attach` {request_id, input_bundle_id}: sesi ACTIVE milik request yang sama, bukan sesi riset,
  paket READY dengan `reference_date` sama, `data_request_id` tidak bertabrakan, jumlah lampiran <
  `PY_SANDBOX_MAX_ATTACHMENTS` (2), baris/byte gabungan ≤ `bundle_max_rows/bytes`; link file ke `input/`, cek checksum.
- Worker op baru `attach` → `saniti._attach(requests)`: `REQUESTS.update`, `CREATE VIEW` di `_CONNECTION`; harness-only
  (pola op `inspect`).
- Store: kolom `attached` (JSON: need_id, bundle_id, waktu) di `sessions` (migrasi skema SQLite pola baris 147).
- Completion (~900): cakupan dihitung per need (awal + lampiran) dengan `processing_coverage`; need lampiran yang tidak
  dibaca sama sekali → status `UNUSED` (tidak menggagalkan, tidak masuk catatan data); lineage output mencatat
  `attached_need_ids`.
- `/v1/runtime` melaporkan `session_attach: 1`.
**Orc** (`app/tools/data_need.py`, `app/tools/session.py`, `app/orchestrator.py` `_merge_mechanical` ~4395,
`app/tool_desks.py`, `app/config.py`):
- `submit_data_need_spec` argumen opsional `attach_to_session_id` (diperiksa: sesi milik run ini).
- Langkah mekanis: prepare READY + niat lampir → alat baru `attach_data_bundle` (bukan `open_analysis_session`); gagal
  → jatuh ke `open_analysis_session` dengan alasan.
- Saklar `AI_ENABLE_SESSION_ATTACH` (default mati) + kapabilitas sandbox; desk FASTLANE dan analisis, tidak di desk riset.
- Kalimat di deskripsi `run_python`/sesi; hint sandbox saat SCRIPT_ERROR menyebut kolom yang tidak ada.
- Data record orc mencakup need lampiran yang dipakai.
- Dokumen: ronde `Tool_Catalog` (generator `scripts/generate_tool_catalog_migration.py`), `AI_TOOLS.md`
  (`generate_ai_tools_doc.py`), `.railway/railway.ts` untuk variabel baru.
- A/B jalur Cepat pola j2 (saklar mati vs hidup): waktu, putaran, sesi per run — **hanya atas perintah user** (berbayar).

#### Urutan dan tumpang tindih

Fase 1 (EDGE) → Fase 2 (sandbox, orc) → Fase 3 (DB) → Fase 4 (sandbox, orc). U4 orc dan PLAN 14 sama-sama di
`orchestrator.py`: berurutan (Fase 2 sebelum Fase 4). Setiap fase: tes lokal, commit, push `main` dan
`claude/code-session-2k3oeg`, deploy sampai SUCCESS, catat di ERRORS (M156, M154 a), EXEC (hapus butir selesai),
RAILWAY/DATABASE_CHANGELOG.

#### Verifikasi

- Tes: EDGE (`EDGE_TEST_CHROMIUM`, `EDGE_TEST_POSTGRES_URL`), orc (`ORC_TEST_POSTGRES_URL`, Postgres lokal 55432), sandbox
  (`/var/tmp/venv-sbx`).
- Live EDGE: skrip Playwright QA (klik→gulir lipatan, ukur jarak, lebar kolom, tabel 10/50, pemilih model ponsel),
  tangkapan layar desktop+ponsel, terang+gelap.
- Live orc/sandbox: satu pertanyaan jalur Cepat dengan tabel >10 baris; log `ai_table_directive` rows≤50; label tanpa
  eksekusi gagal (`UNIT_DROPPED`/`THRESHOLDS_CONVERTED` di peringatan).
- Katalog: pgweb baca balik dua kolom; audit Feature Catalog lulus.
- PLAN 14: tes sandbox (lampiran, tabrakan nama, batas gabungan, sesi lain ditolak, UNUSED tidak gagal, cakupan penuh
  tetap dicek), tes orc (langkah mekanis attach, fallback ke sesi baru); A/B atas perintah.

#### Checklist rinci (2026-10-15; user: "Alright, pls create implementation plan agar tidak ada yg terskip")

Rencana disetujui di mode rencana 2026-10-15. Eksekusi tetap menunggu "go" (AGENTS: persetujuan rencana bukan perintah
menjalankan). Checklist ini menggantikan rincian fase di atas bila berbeda.

Aturan umum setiap fase (dicentang di akhir fase):
- [ ] `git pull origin main` sebelum mulai; tidak menimpa perubahan sesi lain.
- [ ] Tes lokal hijau; `git diff --check`; tinjau diff.
- [ ] Commit (atribusi), push `claude/code-session-2k3oeg` dan `main`; `main` = `origin/main`.
- [ ] Deploy layanan terkait sampai **SUCCESS** (bukan klaim sebelum itu); startup orc tanpa `*_inactive`.
- [ ] Cek live sesuai fase; bukti (id deploy, id run, tangkapan layar) dicatat.
- [ ] ERRORS (status di tempat), EXEC (butir selesai dihapus/ditandai, catatan hasil), RAILWAY_CHANGELOG /
      DATABASE_CHANGELOG.
- [ ] Laporan singkat ke user dalam bahasa Indonesia.

##### Fase 0 — Persiapan (tanpa perubahan)

- [ ] 0.1 Sinkron `main`; catat commit awal.
- [ ] 0.2 Catat deployment aktif (rollback): edge-bff, market-ai-orc, market-python-sandbox
      (`railway deployment list --service X --environment dev --json`).
- [ ] 0.3 Siapkan lingkungan tes: Postgres lokal 55432 (`/var/tmp/orc-pg`), venv orc/EDGE di scratchpad,
      `/var/tmp/venv-sbx`, Chromium `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`.
- [ ] 0.4 Baseline QA EDGE live (sebelum perubahan): skrip `scratchpad/qa/notes2.py` (lipatan tertutup saat gulir),
      `gap.py` (66 px, lebar 1120), tangkapan layar pemilih model ponsel.
- [ ] 0.5 Cek saldo kunci OpenRouter sebelum cek live berbayar (Fase 2 dan 4).

##### Fase 1 — EDGE saja: U1, U2, U3, U5, U4 (tampilan) · deploy edge-bff

File: `apps/edge-bff/static/index.html`, kata baru di `static/edge-labels.js` (bukan di index.html).

- [ ] 1.1 **U1** `patchNode` (~baris 10140, loop hapus atribut): lewati `open` pada `<details>` bila
      `node._props` tidak punya kunci `open`. Lipatan terkontrol (`edge-flow-accordion`, `open:expanded`) tetap ikut state.
      Tes baru (browser): klik "Batasan" → gulir 50 px → tetap terbuka; accordion terkontrol tetap mengikuti state.
- [ ] 1.2 **U2** satu jarak antara kartu terakhir dan kolom tanya (~18 px): `.research-exchange:last-child`
      margin-bottom 0 dan padding bawah `.research-scroll` (~8970) disesuaikan; margin atas composer tetap. Ponsel
      (`padding-bottom:8px`, ~9989) tidak berubah. Tes: jarak terukur 14–22 px di desktop.
- [ ] 1.3 **U3** `--conversation-max-width` 1120px → 768px (~9693): berlaku untuk percakapan, kolom tanya,
      `jump-latest` (rumus ~9696). Tabel lebar: gulir horizontal + tombol perbesar tetap. Tes: lebar kartu ≤ 768 di 1920
      px dengan panel buka dan tutup.
- [ ] 1.4 **U4-EDGE** di `renderMarkdown` (~11165): tabel >10 baris badan → 10 tampil, sisa disembunyikan, tombol
      "Tampilkan N baris lagi" / "Sembunyikan" (label di `edge-labels.js`). State per tabel lewat `updateValue` supaya
      bertahan saat render ulang (pelajaran M156). Urut kolom (EXEC-SORT) mengurutkan semua baris; dialog perbesar
      menampilkan semua baris. Tes: tabel 30 baris → 10 tampil → klik → 30; sort tetap benar.
- [ ] 1.5 **U5** pemilih model (komponen ~10880, CSS ~9505 dan ~10002):
  - [ ] kartu `edge-model-option` tetap (logo, nama, harga input/output, id);
  - [ ] tombol level (`current.reasoning_levels`) dan Jalur (`data.lane_selection`) pindah ke kolom kanan kartu yang
        terpilih ("kotak A"); kartu lain tanpa tombol; klik kartu lain = pilih model + level bawaan
        (`edgeDefaultLevel`); baris level/jalur di bawah daftar dihapus;
  - [ ] ponsel: panel tidak lagi lembar layar penuh, tetapi di area percakapan di atas kolom tanya, selebar kolom,
        `max-height` = ruang di atas kolom tanya, gulir di dalam panel;
  - [ ] desktop: popover tetap di atas tombol, isi kartu memakai tata letak baru;
  - [ ] aksesibilitas tetap: `role=radiogroup`, `aria-checked`, `aria-pressed`.
  Tes: level/jalur hanya di kartu terpilih; pilihan tersimpan (`edge-model-choice`); panel ponsel tidak menutupi header.
- [ ] 1.6 Tes EDGE penuh: `test_visual`, `test_frontend_contract`, `test_browser`, `test_edge`, `test_v4_frontend`,
      `test_v5_frontend`, `test_answer_view` (`EDGE_TEST_CHROMIUM`, `EDGE_TEST_POSTGRES_URL`) + tes baru 1.1–1.5.
- [ ] 1.7 Deploy edge-bff SUCCESS; QA live desktop 1440/1920 + ponsel 390, terang/gelap: lipatan, jarak, lebar,
      tabel lipat (pakai percakapan dengan tabel >10 baris; bila tidak ada, fixture lokal), pemilih model; tidak ada
      overflow horizontal (`qa.py`). Tangkapan layar dikirim ke user.
- [ ] 1.8 Dokumen: ERRORS M156 → DEPLOYED; EXEC-UI-1015 U1/U2/U3/U5 dan bagian EDGE U4 ditandai selesai;
      RAILWAY_CHANGELOG.

##### Fase 2 — sandbox BE1-1 lalu orc U4 · deploy sandbox → orc

- [ ] 2.1 **BE1-1** `apps/market-python-sandbox/runtime/saniti_session.py`:
  - [ ] `_units` (~2121): satuan di luar `VALUE_UNITS` dibuang + `_WARNINGS.append({"code":"UNIT_DROPPED", ...})`;
        `units` bukan dict dan kolom yang tidak ada tetap `InvalidOutput`;
  - [ ] `_definition` (~2158): `thresholds` list → dict (item `{name|label, value}` jadi pasangan; item lain
        `threshold_1..n`) + peringatan `THRESHOLDS_CONVERTED`; tipe lain tetap ditolak;
  - [ ] pesan `InvalidOutput` yang tersisa menyebut cukup label yang dikirim ulang (variabel sesi masih ada).
  Tes: `tests/test_output_definition.py`, `test_units.py` + kasus baru (list→dict, DECIMAL dibuang + peringatan, kolom
  tak ada tetap gagal); suite sandbox penuh.
- [ ] 2.2 Peringatan baru terlihat AI: pastikan `warnings` hasil `run_python` diteruskan orc (tidak dibuang envelope).
- [ ] 2.3 **U4-orc** `apps/market-ai-orc/app/table_directives.py`: `MAX_ROWS` 25 → 50; teks `TABLE_CAPPED_LINE`/
      `TABLE_ROWS_LINE` (user_texts) disesuaikan bila menyebut 25.
- [ ] 2.4 **U4-prompt** `app/orchestrator.py` aturan 13 (~864–871): jumlah yang diminta user, 10 bila tidak; tabel
      rincian lengkap (semua kelompok) tampil penuh sampai 50; jangan memotong hasil di kode (nlargest/head) kecuali user
      meminta top N — rilis hasil lengkap, tampilan yang memilih; >50 tawarkan Excel. Periksa juga catatan jalur Cepat
      yang menyebut jumlah baris (`grep "twenty-five\|25"` di orchestrator dan `fastlane_defaults.py`).
- [ ] 2.5 Snapshot prompt: `scripts/snapshot_system_prompt.py record <nama> --decision "<kata user, tanggal>"
      --change "<ringkas>"`; `test_prompt_history.py`; anggaran ukuran prompt (`test_orchestrator` BUDGET) bila naik.
- [ ] 2.6 Tes orc penuh (`ORC_TEST_POSTGRES_URL`), termasuk `test_table_directives.py` (50, footer cap),
      `test_fastlane.py`.
- [ ] 2.7 Deploy sandbox SUCCESS → orc SUCCESS (startup bersih). Cek live berbayar kecil (saldo dicek): satu pertanyaan
      jalur Cepat yang menghasilkan tabel >10 baris; log `ai_table_directive` rows ≤ 50; EDGE melipat setelah 10.
- [ ] 2.8 Dokumen: EXEC-BE1-1 dan U4 ditandai selesai; ERRORS (catatan M139/M155 kelas terkait bila relevan);
      RAILWAY_CHANGELOG; prompts/SYSTEM_PROMPT_HISTORY.md (dari snapshot).

##### Fase 3 — BE1-2 katalog (migrasi DB)

- [ ] 3.1 Migrasi baru `database/migrations/<tgl>_<n>_feature03_buy_sell_identity.sql` (tidak mengubah migrasi lama):
  - [ ] `AI_column_catalog.description` + `description_id` (status DRAFT) untuk `total_buy_value`, `total_sell_value`:
        dijumlah atas semua broker per saham, tanggal, papan → keduanya sama (setiap transaksi punya pembeli dan
        penjual); selisihnya nol; untuk akumulasi pakai `positive_net_value_total` atau net per tipe investor;
  - [ ] `Feature_Catalog` v2 aktif: tambahan di `misuse_warning`, `validation_evidence` + bukti (pola UPDATE di tempat
        `20261012_003`);
  - [ ] `Column_Catalog`: tidak diubah langsung (disinkron dari Feature_Catalog oleh `sync_database_catalog.py`);
        status tidak dinaikkan.
- [ ] 3.2 Uji lokal di Postgres 55432 (migrasi dapat dijalankan, idempoten bila mungkin).
- [ ] 3.3 Terapkan lewat job sementara `mmig-job` (DRYRUN → APPLY → hapus layanan); `sha256sum >>
      database/migrations/APPLIED.sha256`.
- [ ] 3.4 Baca balik lewat pgweb (deskripsi, description_id, misuse_warning); `scripts/audit_feature_catalog_semantics.py`.
- [ ] 3.5 Dokumen: `DATABASE_SCHEMA.md` (bagian terkait saja), `DATABASE_CHANGELOG.md`, ERRORS M154 bagian a →
      DEPLOYED, Part A (pelajaran: kolom yang tidak bisa membawa informasi untuk pertanyaan umum harus menyatakannya),
      EXEC-BE1-2 selesai.

##### Fase 4 — PLAN 14 lampiran data ke sesi terbuka · sandbox → orc (saklar mati)

Sandbox (`apps/market-python-sandbox`):
- [ ] 4.1 Faktorkan pembuatan `requests` dari `SessionManager._launch` (`app/sessions.py` ~840–870) menjadi fungsi
      bersama (link file, cek checksum, dict permintaan).
- [ ] 4.2 Konfigurasi `PY_SANDBOX_MAX_ATTACHMENTS` (bawaan 2) di `app/config.py`; `.railway/railway.ts` bila diset.
- [ ] 4.3 Store `app/dataneed_store.py`: `SCHEMA_VERSION` 5 → 6, `UPGRADES[6]` kolom `sessions.attached TEXT` (JSON:
      need_id, bundle_id, attached_at).
- [ ] 4.4 Worker op `attach` (`runtime/session_worker.py`, pola op `inspect`) → `saniti._attach(requests)` di
      `runtime/saniti_session.py`: `REQUESTS.update`, `CREATE VIEW` di `_CONNECTION`; harness-only.
- [ ] 4.5 `SessionManager.attach_bundle(session_id, request_id, input_bundle_id)` + route `POST
      /v1/sessions/{id}/attach` (`app/main.py`): sesi ACTIVE milik request yang sama; bukan sesi riset; paket READY milik
      percakapan yang sama; `reference_date` sama; `data_request_id` tidak bertabrakan; lampiran < batas; baris/byte
      gabungan ≤ `bundle_max_rows/bytes`; penolakan dengan alasan + sisa kapasitas + `next_action OPEN_ANALYSIS_SESSION`.
- [ ] 4.6 Completion (`app/dataneed_service.py` ~900): cakupan per need (awal + lampiran) dengan
      `processing_coverage`; need lampiran tak dibaca sama sekali → `UNUSED` (tidak gagal, tidak masuk catatan data);
      dibaca sebagian → aturan sekarang; lineage output mencatat `attached_need_ids`.
- [ ] 4.7 `/v1/runtime` kapabilitas `session_attach: {enabled, version: 1, max_attachments}`.
- [ ] 4.8 Hint SCRIPT_ERROR: bila galat menyebut kolom yang tidak ada di permintaan mana pun, tambahkan saran
      "lampirkan data yang memuat kolom itu".
- [ ] 4.9 Tes sandbox baru: lampiran berhasil (variabel tetap, `load` permintaan baru), nama bertabrakan, batas jumlah,
      batas gabungan, sesi request lain ditolak, sesi riset ditolak, `UNUSED` tidak gagal, cakupan penuh tetap dicek,
      migrasi store 5→6; suite sandbox penuh.

orc (`apps/market-ai-orc`):
- [ ] 4.10 Saklar `AI_ENABLE_SESSION_ATTACH` (bawaan false) di `app/config.py`; aktif hanya bila sandbox melaporkan
      `session_attach` (pola `session_release` di `app/main.py` ~272).
- [ ] 4.11 `submit_data_need_spec`: argumen opsional `attach_to_session_id` (diperiksa: sesi milik run ini, ada di
      `state.sessions`); tidak dikirim ke validator sandbox.
- [ ] 4.12 Alat `attach_data_bundle` (`app/tools/session.py`, pola `open_analysis_session`) + desk FASTLANE dan analisis
      (`app/tool_desks.py`), tidak di desk riset.
- [ ] 4.13 Langkah mekanis `_merge_mechanical` (`app/orchestrator.py` ~4395): prepare READY + niat lampir →
      `attach_data_bundle`; gagal → `open_analysis_session` dengan alasan.
- [ ] 4.14 Deskripsi alat: satu kalimat di `run_python`/sesi dan argumen baru (kapan dipakai, batas 2).
- [ ] 4.15 Data record dan audit: need lampiran yang dipakai masuk catatan data; `log_event("session_attached")`.
- [ ] 4.16 Dokumen alat: ronde Tool_Catalog baru setelah `round_t` (`scripts/generate_tool_catalog_migration.py`,
      migrasi + terapkan + baca balik), `AI_TOOLS.md` (`scripts/generate_ai_tools_doc.py`, `PLAIN` untuk nama baru),
      `test_ai_tools_doc.py`.
- [ ] 4.17 Tes orc: argumen, langkah mekanis attach, fallback, saklar mati = perilaku lama, desk riset tanpa alat;
      suite penuh.
- [ ] 4.18 Deploy sandbox SUCCESS → orc SUCCESS dengan saklar **mati**; startup bersih.
- [ ] 4.19 A/B jalur Cepat pola j2 (saklar mati vs hidup): waktu, putaran, sesi per run — **hanya atas perintah user**
      (berbayar); menyalakan saklar = perubahan variabel Railway → `railway config pull --force` + `config plan`,
      RAILWAY_CHANGELOG.
- [ ] 4.20 Dokumen: PLAN 14 dipindah ke selesai (setelah A/B dan keputusan user), ERRORS (entri baru bila ada temuan),
      RAILWAY_CHANGELOG.

##### Fase 5 — Penutupan

- [ ] 5.1 Bandingkan EXEC/PLAN dengan perilaku yang ter-deploy; laporkan butir yang belum dibangun.
- [ ] 5.2 Bersihkan EXEC sesuai AGENTS (butir selesai dicatat di ERRORS/changelog dan dihapus dari daftar terbuka).
- [ ] 5.3 Laporan akhir ke user: apa yang berubah, bukti live, sisa butir (UI-1015B, M145, M154b, M155, panjang adaptif).

##### Matriks pelacakan

| Butir | Langkah | Tes | Bukti live | Dokumen |
|---|---|---|---|---|
| U1 (M156) | 1.1 | browser klik→gulir | QA live lipatan | ERRORS M156, EXEC |
| U2 | 1.2 | jarak 14–22 px | tangkapan layar | EXEC |
| U3 | 1.3 | lebar ≤768 | tangkapan layar | EXEC |
| U4 | 1.4, 2.3–2.5 | tabel 30 baris; `test_table_directives` | run tabel >10 | EXEC, snapshot prompt |
| U5 | 1.5 | pemilih model desktop+ponsel | tangkapan layar ponsel | EXEC |
| BE1-1 | 2.1–2.2 | `test_output_definition`, `test_units` | peringatan di run | EXEC |
| BE1-2 (M154a) | 3.1–3.5 | migrasi lokal, audit Feature | baca balik pgweb | DATABASE_*, ERRORS, Part A |
| PLAN 14 | 4.1–4.20 | sandbox + orc | A/B atas perintah | Tool_Catalog, AI_TOOLS, PLAN |

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

### EXEC-W: rencana eksekusi putaran 2026-10-08 (butir EXEC-V yang disetujui; dikerjakan, W-A1–W-A6 ter-deploy)

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

### EXEC-Y: rencana implementasi putaran 2026-10-09 (review semua butir EXEC yang disetujui; dikerjakan, Fase 1–3 ter-deploy)

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
- Deploy `977b525`: sandbox `92eabc87` dan orc `d6177468` **SUCCESS**. Cek live: pada run berikutnya yang mengalami kode gagal atau angka ganda.

### EXEC-UI-1015: Asumsi/Batasan menutup sendiri, celah di atas kolom tanya, lebar kolom percakapan (dicatat 2026-10-15; bagian EDGE ter-deploy 2026-10-15)

**Hasil (go 2026-10-15 "Ok jalankan"; `main` `e3ccf5d`, edge-bff dev `0eb6c761` SUCCESS).** U1 (M156 DEPLOYED): `patchNode`
mempertahankan `open` yang dibuka pembaca; live: catatan MSCI tetap terbuka setelah digulir 0/50/600/200 px. U2: satu
jarak 18 px (dulu 66) di 1920 dan 1440 px, terang dan gelap; ponsel tidak berubah. U3: kolom jawaban dan kolom tanya 768
px dengan panel Details terbuka atau tertutup; tidak ada gulir horizontal. U4 bagian EDGE: tabel dengan lebih dari 10
baris menampilkan 10 baris pertama (urutan saat itu), baris total tetap tampil, sisanya di balik tombol "Tampilkan N baris
lagi"/"Sembunyikan baris" (label di `edge-labels.js`); urut kolom mengurutkan semua baris; dialog perbesar dan cetak
menampilkan semua baris. U5: level berpikir dan Jalur ada di ruang kanan kartu model terpilih (kartu lain tanpa tombol;
catatan Jalur menjadi tooltip); di ponsel panel berada di atas kolom tanya, sejajar dan selebar kolom tanya (posisi dan
lebar dibaca dari kolom tanya), tidak menutupi header (live 390 px: panel y 70–733, header 58, kolom tanya 739). Tes
baru `apps/edge-bff/tests/test_ui_1015.py`; tes V5 lembar bawah ponsel diganti tes U5. Suite EDGE 96 passed. Sisa U4:
batas backend 50 dan aturan prompt (Fase 2).

**Hasil U4 bagian orc (2026-10-15, `c997c4d`, orc `abeadb31` SUCCESS):** `table_directives.MAX_ROWS` 25 → 50; aturan 13
dan blok TABLES: jumlah yang diminta user, sepuluh untuk peringkat tanpa angka, semua baris sampai lima puluh untuk
rincian per kelompok, lebih dari 50 ditawari Excel, baris dipotong di kode hanya bila user meminta top N. Snapshot
prompt v008 (`prompts/history/v008-2026-10-15-table-rows-fifty`). Tes `test_table_directives` (50, 40 tampil utuh),
`test_prompt_pass2` (kalimat yang disetujui), suite orc 1.782 lulus. Cek live berbayar **dilewati**: saldo kunci
OpenRouter $0,37 dari batas $41 (satu run bisa menghabiskannya); dicek setelah saldo diisi.

**Keputusan user 2026-10-15 (lanjutan):** atas U1 dan U2: "Aight OK - masukan EXEC jangan execute dulu"; atas U3 (berlaku selalu atau hanya saat kedua panel ditutup): "seperti chat GPT" → kolom jawaban dan kolom tanya paling lebar sekitar 768 px CSS **selalu**, panel terbuka atau tidak. Status U1–U3: disetujui, belum dieksekusi.
- **U4 tabel sampai 50 baris, bisa dilipat (disetujui 2026-10-15, user: "Ok masukan EXEC U4"; belum dieksekusi; 10 baris terlihat, sampai 50, sisanya dilipat; dampak token dicek: instruksi tabel satu baris, baris diisi backend sesudah model, riwayat giliran berikutnya dibatasi 16.000 karakter, saran lanjutan membaca 6.000 karakter jawaban).** User: "malah saya mau sampai 50 kalau bisa. Di tampilan di frontend, tapi bisa di collapse/ expand. Agar datanya rinci dan jelas, lengkap. Gimana menurutmu?" Sekarang: `table_directives.MAX_ROWS = 25` (pengaman EXEC-ROWS, user 2026-10-13) dan aturan prompt "jumlah yang diminta user, 10 bila tidak disebut"; di run `edge_19f817ae…` tabel sektor 12 baris tampil 10, dan AI sendiri memotong saham naik ke 10 di kode (`nlargest(10)`). Usulan: (a) pengaman backend 25 → 50; (b) EDGE menampilkan 10 baris pertama, sisanya dilipat dengan tombol "Tampilkan N baris lagi" (dialog lebar tetap ada); (c) prompt: tabel rincian lengkap (semua kelompok) ditampilkan penuh sampai 50; AI tidak memotong data di kode kecuali user meminta "top N" (hasil lengkap dirilis, tampilan yang memilih); lebih dari 50 ditawarkan sebagai Excel. Baris dibaca backend dari tabel hasil, jadi tidak menambah token model. Butuh snapshot prompt.
**Permintaan user 2026-10-15** (dua tangkapan layar): "Catat juga bug terlampir di front end.. Which ketika saya klik asumsi dan batasan maka itu automatically tertutup. Kemudian under normal conditions ada gap putih seperti terlampir. PLease fix it dan confirm visually dan interactionally. Masukan ke EXEC jangan eksekusi dulu." dan "terkait dengan padding kiri dan kanan, saat ini kalau panel kiri dan kanan di collapse, maka jaraknya sangat lebar. Boleh gak buat seperti chat GPT jaraknya? Konfirmasi apakah yang saya maksud kamu paham."
- **U1 Asumsi/Batasan menutup sendiri (ERRORS M156).** Direproduksi di EDGE dev (Chromium 1920 px, percakapan MSCI): klik "Batasan" membuka, menggulir 50 px ke atas menutupnya lagi; elemen yang sama (bukan dibuat ulang). Akar masalah (terverifikasi di kode): setiap gulir mengubah state (`setAutoFollow`, bagian aktif) sehingga tampilan digambar ulang; `patchNode` (`static/index.html`) menghapus setiap atribut node lama yang tidak ada di node baru, termasuk `open` yang dipasang browser saat diklik. Kelas: setiap `<details>` yang tidak dikendalikan (`edge-notes`, `edge-more`, `edge-technical`) dan setiap atribut lain yang dipegang browser. Rencana: `patchNode` mempertahankan `open` pada `<details>` bila node baru tidak mengaturnya sendiri (perbaikan di lapisan perender, mencakup semua lipatan). Cek: tes browser klik → gulir → tetap terbuka, lipatan yang dikendalikan (`edge-flow-accordion`) tetap mengikuti state; cek visual dan interaksi desktop dan ponsel di live.
- **U2 celah di atas kolom tanya.** Diukur di live (1920 px, terang): jarak kartu jawaban terakhir ke kolom tanya 66 px = margin bawah percakapan 22 px + padding bawah area gulir 32 px + margin atas kolom tanya 12 px (tiga jarak menumpuk). Rencana: satu jarak saja (sekitar 16–20 px) tanpa mengubah desain lain; ponsel (sudah 8 px) tidak berubah. Cek: ukur ulang dan tangkapan layar terang/gelap, desktop dan ponsel.
- **U3 lebar kolom percakapan seperti ChatGPT (menunggu konfirmasi user).** Sekarang kolom jawaban dan kolom tanya paling lebar 1120 px CSS (`--conversation-max-width`), jadi dengan panel kiri dan kanan ditutup baris teks sangat panjang. ChatGPT memakai sekitar 768 px CSS (di tangkapan layar user 1152 px layar = 768 px pada skala 150%). Usulan: kolom paling lebar sekitar 768 px, di tengah, untuk jawaban dan kolom tanya; tabel lebar tetap bisa dibuka di dialog lebar (EDGE V4). Pertanyaan ke user: berlaku selalu (seperti ChatGPT) atau hanya saat kedua panel ditutup.

- **U5 pemilih model di ponsel (disetujui 2026-10-15; Jalur ikut dipindah, user: "ya dipindah"; belum dieksekusi).** User 2026-10-15 (dua tangkapan layar ponsel): "retain existing design untuk model selection; pindahkan reasoning selection ke kotak A; untuk size dan lokasi bs disesuaikan dengan nomor (1)". Dibaca sebagai: kartu model (logo, nama, harga input/output, id) tetap; pilihan level berpikir (Rendah/Tinggi/Maks) pindah dari baris terpisah di bawah daftar ke ruang kosong di kanan setiap kartu model ("kotak A"), hanya aktif pada kartu model yang dipilih; panel pemilih menempati area kosong percakapan di atas kolom tanya (area "1"), bukan menutupi seluruh layar.

### EXEC-IMPL-1016: rencana implementasi EXEC-OPEN-1015, UI-1015E, EDGE-CTX dan UI-1015B (Fase 0–4 selesai dan ter-deploy 2026-10-15/16; Fase 5 penutupan)

**Persetujuan user 2026-10-15:** rencana diminta ("Ok, pls create implementation plan. Inspect current architecture to
ensure plan take that into account."), saldo diisi ("Done di isi"), lalu "Ok jalankan" untuk Fase 0 + Fase 1. Fase 2–5
masing-masing menunggu "go" sendiri.

**Keputusan user atas pertanyaan rencana (2026-10-15):**
- O3: tanda "menjelaskan hasil lama" diturunkan dari isi jawaban ("Dari isi jawaban"), tanpa kolom router baru.
- O2: router hanya diberi kartu kemampuan per jalur, tanpa kelas atau kolom baru.
- UI-1015E: kepala jawaban bergaya lama, teks "EDGE · Completed" ("Completed (huruf depan kapital)").
- O1: pencocokan alias + persis + potongan teks, tanpa `pg_trgm` ("Alias + persis + potongan").
- Cacat sampingan: hanya "Cek cakupan entitas G13 mati" ikut dibereskan; tumpukan peringatan sandbox tidak.
- Ditunda: O4 (M166 tetap OPEN) dan O5 butir 5.

**Fase:**
- 0: catat go, deploy aktif untuk rollback, saldo.
- 1: M167 (satuan saat rilis, pesan gerbang sesuai cek); UI-1015E; O1 aturan nilai teks di prompt dan deskripsi alat.
- 2: O2 kartu kemampuan router; O3 gerbang dari isi jawaban dan satu catatan per giliran; O5 butir 1 fakta berversi;
  O5 butir 2–4 default tafsir.
- 3: O1 kamus nilai dan alias entitas (menggantikan PLAN 11), alat `search_values`, cek kode entitas, G13, kolom kembar.
- 4: EDGE-CTX B lalu A; UI-1015B.
- 5: penutupan.

**Fase 0 (2026-10-15):**
- Deploy aktif untuk rollback: orc `fcda847e` (`5158381`), edge-bff `1aca46e9` (`2e201d7`), sandbox `88739487`
  (`4d9a3cd`). Governor tidak disentuh di Fase 1–2.
- Koreksi (Fase 1): orc `fcda847e` membawa M168 (sejak `ed07e66c`, 09:28 UTC, setiap panggilan model gagal). Titik
  rollback orc yang benar untuk panggilan model adalah commit `1fbec6d` (deploy `ac4ea638`).
- Saldo dibaca live: akun USD 85 total, terpakai 43,73; kunci orc batas USD 42, terpakai 41,09 (sisa USD 0,91).
- Batas kunci perlu dinaikkan user sebelum Fase 2 (benchmark router dua kali dan cek live).

**Keputusan user 2026-10-15 sesudah Fase 1:** "Skip M169"; "Next lanjutkan tanpa minta saya naikan limit. Hanya beritahu
ketika ada cost rejection. Ini membuat progress lama karna kamu harus berhenti terus ditengah jalan". Artinya: go untuk
Fase 2–5 berturut-turut. Pekerjaan berbayar (benchmark router, cek live) dijalankan tanpa minta izin batas kunci, dan
user diberi tahu hanya bila provider menolak karena biaya. Berhenti hanya untuk keputusan yang benar-benar milik user
(mis. celah Part A di Fase 3).

**Fase 1 (dibangun 2026-10-15):**
- 1.1 M167:
  - Sandbox `_unit_hints` juga menilai kolom float/desimal dari nilainya: semua nilai hingga ±1,5 dan tidak semuanya
    bilangan bulat, aturan yang sama dengan `units_advice`. `emit_json` menilai angka tingkat atas dengan aturan itu.
  - Satu peringatan `UNIT_UNDECLARED` per tabel, dengan contoh nilai. Isinya hanya perbaikan yang lolos cek: rilis
    ulang dengan `units=`, atau `|dec`/`|x` untuk rasio biasa. Teks perbaikan tidak pernah terpotong oleh batas 500
    karakter.
  - Pesan gerbang UNITS di orc hanya menawarkan format persen sesudah `units=`. Tes `test_fastlane.py` merender setiap
    format yang ditawarkan pada kolom tanpa satuan.
- 1.2 UI-1015E:
  - Kepala jawaban memakai gaya lama (redup, .75rem, 500, `letter-spacing:.1em`, tanpa huruf besar paksa) dengan teks
    "EDGE · Completed" (`edgeUi().answerKicker`).
  - Baris metadata menampilkan label model ("DeepSeek V4.1 Flash"), dengan id di tooltip. "Fast lane" dihapus.
- 1.3 O1 awal:
  - Aturan DATA NEED: setiap nilai teks di scope adalah nilai tersimpan. Kategori diambil dari `column_values` atau
    `get_dimension_values`. Kode entitas yang user tulis diketik apa adanya, tanpa `get_dimension_values`. Nama dicari
    dulu di tabel referensi (`lookup_reference` bila ditawarkan), dan AI bertanya bila cocok ke beberapa kode.
  - Prompt v009. Tool_Catalog `round_v`: `get_dimension_values` v2 dan `submit_data_need_spec` v14.
- Tes lokal: orc 1.807 lulus; EDGE 103 lulus; sandbox 860 lulus.
- M168 (ditemukan saat Fase 1): sejak orc `ed07e66c` (M163, 09:28 UTC) setiap panggilan model gagal, karena jawaban
  gzip didekode dua kali. Diperbaiki di commit yang sama (ERRORS M168).
- Deploy `2ea90c8` → SUCCESS: orc `5163a5e0`, sandbox `3c3db0c9`, edge-bff `1875326a`. Tool_Catalog `round_v`
  diterapkan.
- Cek live `edge_91cfccda…` ("rata-rata rentang harga harian … BBRI dan BMRI selama 1 bulan terakhir"):
  - COMPLETED dalam 50 dtk: 6 iterasi, 9 alat, USD 0,006.
  - Tidak ada `get_dimension_values` untuk kode saham, dan tidak ada gerbang UNITS (model menyatakan `FRACTION` sejak
    awal). Angka tampil 2,28% / 1,74%.
  - EDGE desktop dan ponsel: "EDGE · Completed" bergaya redup, "DeepSeek V4.1 Flash" dengan id di tooltip, tanpa
    "Fast lane", tanpa geser samping.
  - Temuan baru M169 (OPEN): kata bilangan ("seperempat persen") tidak dicek sumbernya.

**Fase 2 (dibangun 2026-10-15):**
- 2.1 O2:
  - Router giliran lanjutan membaca kartu kemampuan per kelas (`ROUTE_CAPABILITIES`). Nama metode riset dan batas sudut
    diturunkan dari `research_library` dan `lanes.EXPLORE_MAX_ANGLES`.
  - Kalimat "rekap/daftar → INSIGHT" diselaraskan: bukan CLARIFY; INSIGHT bila merinci data yang sudah dipakai, CONTINUE
    bila butuh data atau kriteria baru.
  - Router pesan pertama membaca apa yang dijalankan tiap rute (`FIRST_ROUTES`) dan perilaku jalur cepat
    (`FAST_LANE_ROUTES`).
  - Fixture ditambah 12 kasus batas (giliran lanjutan) dan 4 kasus heldout. Benchmark sebelum/sesudah: giliran lanjutan
    73/78 → 78/78 (kasus batas 22/24 → 24/24); pesan pertama 126/128 → 127/128 dua kali; kriteria keras FAIL → PASS
    dua kali. Satu versi kalimat jalur cepat sempat membuat "kenapa … turun" ke RESEARCH (124/128) dan diganti.
  - Biaya benchmark sekitar USD 0,35.
- 2.2 O3:
  - Gerbang hasil lama kini dipicu dari isi jawaban, di semua kelas: jawaban yang merilis hasil baru dan mengutip hasil
    giliran lalu yang belum dibuka ditolak sekali (`INSIGHT_SOURCE_NOT_OPENED`, di jawaban akhir).
  - Catatan per giliran dikirim sebagai satu brief; giliran baca (CLARIFY, CONVERSATIONAL, FACT) tidak menerima catatan
    kerja data.
  - Catatan mode insight bersyarat: uji untuk "kenapa" dan pola; cari, daftar atau peringkat dijawab dengan tabel.
- 2.3 O5 butir 1:
  - `data_record.facts`: jenis ENTITY_SET, EVENT_DATE (dengan makna tanggal), PERIOD, DEFINITION; asal USER, DATABASE,
    WEB, AI. Urutan berlaku: user terbaru > user sebelumnya > database > web > AI. Fakta yang diganti disimpan.
  - Router membaca nama baru EVENT_DATE dan DEFINITION; fakta dari pesan user masuk ke data record sebelum langkah
    analisis.
  - Jawaban akhir punya kolom opsional `facts`. Asal dibaca dari sumber yang dikutip, bukan dari kata model.
  - Data record yang hanya berisi fakta juga ditampilkan ke model.
- 2.4 O5 butir 2–4:
  - `FASTLANE_DEFAULTS` mendapat tiga tafsir (net, tipe investor asing, penutupan implementasi), dengan tabel AGENTS.md.
  - Catatan keputusan berisi kalimat "kirim data need begitu cakupan jelas".
  - Butir 3 tercakup oleh brief tunggal (2.2).
- Prompt snapshot v010 (skema jawaban, catatan keputusan); `AI_ROUTER.md` dibuat ulang. Tes orc 1.821 lulus.
- Deploy `264c16f` → orc `07f748de` SUCCESS (startup tanpa `*_inactive`). Cek live tiga giliran
  `conv_4151c554…` (jalur cepat, DeepSeek V4.1 Flash high):
  - 1. broker asing BBRI sekitar 24 Nov 2025: ANALYSIS, 181 dtk. Tiga fakta dari pesan user tercatat. Tafsir default
    (net, tipe investor asing) tertulis di asumsi.
  - 2. "Cari saja juga untuk tanggal efektif 26 Agustus 2025…": **CONTINUE** (dulu INSIGHT), 139 dtk (run asli
    `2f7523a7` 336 dtk). Fakta EVENT_DATE ditambahkan. Gerbang hasil lama menyala sekali karena jawaban membandingkan
    dengan hasil November; model memastikan definisinya sama.
  - 3. "kenapa broker itu…": INSIGHT, 297 dtk, rincian harian tanpa uji statistik (pilihan model).
  - Satu bacaan router kurang tepat: "beli" dicatat sebagai DEFINITION (tidak berbahaya).

**Fase 3 (dibangun 2026-10-15):**
- Penyimpangan dari rencana, dengan alasan: rencana memakai tabel `AI_value_dictionary` yang diisi job
  `ai-data-coverage`. Yang dibangun: kamus diturunkan saat berjalan di SQL Governor (`app/value_dictionary.py`, cache
  300 dtk) dari data yang sudah ada. Alasannya: tidak ada salinan yang harus dijaga tetap segar; tabel referensi baru
  cukup diberi tanda `entity_name`, tanpa kode (aturan user "derive, do not enumerate"). Yang disimpan hanya alias
  kurasi (`AI_entity_alias`, kosong saat dibuat).
- 3.1–3.2 migrasi `20261015_014` (diterapkan di dev): `AI_column_catalog.entity_name` untuk empat kolom nama (Universe,
  Universe_History, Broker_Profile, Broker_Profile_History) dan tabel `AI_entity_alias`. Cek Part A: tabel metadata,
  bukan data pasar; tidak ada celah.
- 3.3–3.4 sumber nilai per kolom: daftar CHECK; nilai tabel statis (kode entitas, batas 20.000); kolom entitas tabel
  bertanggal = entitas di `AI_data_coverage` ∪ kode tabel referensinya (lengkap); kolom kode yang hanya terhubung ke
  profil (broker) = kode profil, **tidak lengkap**: kode yang tidak ada hanya diberi peringatan
  `VALUE_NOT_IN_REFERENCE`, tidak ditolak.
  - Alias turunan: singkatan nama tiga kata atau lebih ("Bank Rakyat Indonesia" → BRI), nama tanpa PT/Tbk/(Persero)/
    Class, nama lama dari tabel history; alias yang menunjuk lebih dari satu kode menjadi kandidat, tidak ditebak.
  - Governor `POST /v1/catalog/search-values` dan alat orc `search_values` (Tool_Catalog `round_w`, migrasi
    `20261015_015`, `AI_TOOLS.md`, prompt v011). `value_domains` kontrak membawa daftar nilai dan alias pendek.
  - Sandbox: nilai yang tidak tersimpan di daftar lengkap ditolak dengan kandidat (alias, potongan nama, ejaan dekat)
    dan petunjuk `search_values`.
  - Kemampuan `value_lookup` di `get_system_capabilities` tidak ditambahkan sebagai nama: kemampuan diturunkan dari
    efek alat (P31), dan `search_values` (READS) otomatis muncul.
  - Data record menyimpan kata user yang sudah ditemukan ("BRI" = BBRI) untuk giliran berikutnya.
- 3.5 G13 (M170): pemeriksa entitas memakai `search_values` (hanya kode persis); sebelumnya mati karena bertanya ke
  `get_dimension_values` yang menolak kolom entitas.
- 3.6 `saniti.join` membuang kolom kunci kanan yang namanya berbeda (nilainya sama), dicatat di
  `join_report()["dropped_right_keys"]`; ringkasan sesi menyebut pasangan kunci tiap relasi (`key_pairs`).
- Tes: Governor 291, sandbox 864 (+ tes join/sesi diulang 113), orc 1.826.
- Deploy `ba5b52b`: Governor `f70bf612`, sandbox `c5b30598`, orc `cb8d5d2a` SUCCESS (startup orc tanpa `*_inactive`).
  Migrasi 014 dan 015 diterapkan (mmig-job DRYRUN `a32618c9`, APPLY `943e8009`) dan dibaca ulang.
- Uji kamus di data live lewat pgweb (gratis): "BCA" → BBCA, "bank mandiri" → BMRI, "Mandiri Sekuritas" → CC,
  "Telkom"/"Astra" → kandidat, "BRI" → ambigu BBRI/AGRO (PT Bank Raya Indonesia juga berinisial BRI). Aturan umum
  ditambahkan: alias kurasi mengalahkan alias turunan (`7a9314e`, Governor `624c6a5b`). Usulan untuk user: satu baris
  `AI_entity_alias` "BRI" → BBRI (MANUAL) bila user setuju; tanpa itu model melihat dua kandidat.
- Cek live 3.7:
  - `edge_b4d0b88a…` "harga BRI dan Mandiri minggu lalu": `search_values` dipanggil sekali; jawaban memakai BBRI dan
    BMRI dan menyebut kodenya (96 dtk). Pilihan dari kandidat ambigu tidak ditulis di asumsi (catatan, bukan cacat).
  - `edge_38585d20…` "BBRX dan TLKN": jalur `query_metric` (Governor summary) tidak memeriksa nilai, BBRX memberi 0 baris.
    Model bertanya balik untuk BBRX dan menulis asumsi TLKN → TLKM. Diperbaiki di Governor: jalur summary memeriksa
    nilai teks scope dan restriction dengan kamus (`check_scope`).
  - Sesudah `2334b44` (Governor `33e8d485` SUCCESS), `edge_ba384d53…` "harga penutupan BBRX": summary ditolak
    `VALUE_NOT_FOUND`, model memanggil `search_values` lalu bertanya balik dengan contoh BBRI (32 dtk).
- Fase 3 selesai. Sisa usulan untuk user: baris alias kurasi "BRI" → BBRI; jalur lama `/v1/query` dan `/v1/lookup`
  (mati di dev) belum memakai cek kamus.

**Fase 4 (dibangun 2026-10-15):**
- 4.1 EDGE-CTX B: Sources diawali "Tabel hasil (N)": tabel yang dirilis jawaban ini (`data_record.outputs` dengan
  `request_id` jawaban ini), dengan nama, alamat (`out.N`), baris, kolom, "Data per" dan tombol "Ask AI to export
  data". Tombol mengirim pesan "Ekspor data tabel out.N (nama) ke Excel" lewat jalur pesan yang sama dengan pertanyaan
  lanjutan. Daftar bukti lama tetap ada, dilipat, berjudul "Rujukan angka (N)". Tabel jawaban lain tidak ikut.
- 4.3 UI-1015B: orc mencatat langkah run di memori (`app/progress.py`, pola `stop.py`): "Memahami pertanyaan" (router),
  "Menyusun langkah berikutnya" (panggilan model), dan tiap alat dengan labelnya sendiri atau menurut efeknya
  (`user_texts.PROGRESS_EFFECTS`). Langkah yang ditolak ditandai. Endpoint `GET /v1/agent/requests/{id}/progress`
  hanya untuk pemilik run; run yang selesai masih bisa dibaca 10 menit.
  - Penyimpangan dari rencana, dengan alasan: rencana menyimpan progres di kolom baru tabel job BFF (migrasi `edge_bff`)
    lewat worker. Yang dibangun: BFF meneruskan progres orc lewat `GET /api/v1/runs/{id}/progress` (memeriksa pemilik
    job), dan EDGE membacanya tiap 2,5 detik selama run berjalan. Progres hanya berguna selama run berjalan, jadi tidak
    perlu disimpan: tidak ada migrasi, tidak ada tulisan ke database tiap 2 detik. Bila orc restart, hanya progresnya
    yang hilang.
  - EDGE: di bawah "AI request running" tampil waktu berjalan, langkah sekarang, dan "Langkah selesai (N)" yang dilipat;
    hilang saat jawaban tiba (durasi total sudah tampil di jawaban).
- 4.2 EDGE-CTX A:
  - orc mengirim `answer_tables` di jawaban: untuk tiap tabel yang dibangun dari instruksi tabel, judul kolom yang
    tampil, kolom hasil di baliknya, dan posisi baris yang tampil di tabel rilis (`rows[_row=N]`), plus `output_id`.
  - EDGE mencocokkan tabel yang dirender lewat judul dan jumlah baris, bukan lewat penanda tersembunyi di teks jawaban
    (penyimpangan dari rencana: penanda bisa terbaca oleh gerbang angka dan ikut tersimpan di riwayat). Tabel yang
    diketik model sendiri tidak punya peta, jadi tidak bisa dilampirkan.
  - Pada tabel yang bisa dilampirkan: klik baris untuk memilih, tombol "Attach to question" (atau "Attach N rows").
    Pilihan tampil sebagai chip di dalam kotak tanya, bisa dihapus, dan ikut pesan berikutnya sebagai
    `attached_selection {ref, output_id, title, columns, rows, shown_values}`. Satu lampiran per pertanyaan.
  - Pilihan per kolom atau per sel belum dibuat; yang dilampirkan adalah baris (semua kolom yang tampil).
  - BFF dan orc memeriksa batas yang sama (12 kolom, 50 baris, sel 80 karakter, ref `out.*`).
  - orc menambahkan satu catatan ke brief giliran: tabel dan baris yang dilampirkan, angka dibaca ulang dari tabelnya
    (bukan dari teks yang tampil), data mentah lewat `get_lineage`, muat, saring, rilis, dan `export_result`.
- Tes: EDGE 105 (dua tes browser baru), orc 1.831 (`test_progress.py`), `AI_MODELS.md` dibuat ulang (nama call site
  router menjadi `_router_call_once`).
- Deploy:
  - `56066b1` (4.1, 4.3): orc `4e9e7fd4`, edge-bff `761b8db3` SUCCESS.
  - `d2c9ed8` (judul tabel di Sources dari nama output): edge-bff `c36d4622` SUCCESS.
  - `801013b` (4.2): orc `74ab0f54`, edge-bff `8c6ace94` SUCCESS.
- Cek live:
  - 4.3 `edge_5aa6abf8…`: progres terbaca lewat BFF tiap 4 detik selama 139 dtk (20 langkah: "Memahami pertanyaan",
    "Menyusun langkah berikutnya", "Permintaan data", …); sebelum orc mulai `NOT_RUNNING`.
  - 4.1: Sources di desktop dan ponsel menampilkan "Tabel hasil (1)" dengan isi, baris, kolom, data per dan tombol
    ekspor; "Rujukan angka (8)" terlipat; tanpa luapan horizontal. Temuan yang diperbaiki: `label` output berisi status
    validasi ("DATA_COVERAGE_VERIFIED"), bukan nama, dan output JSON ikut terdaftar.
  - 4.2 `edge_b7fe6dfd…` lalu `edge_a2dc2f0b…`: jawaban pertama membawa `answer_tables` (out.o1, 5 baris, 5 kolom);
    baris pertama (BK) dilampirkan ke "kenapa broker di baris yang saya lampirkan ini paling besar?". Jawaban kedua
    menyebut BK dan menjelaskan dari data (beli Rp 297,86 miliar, jual Rp 47,12 miliar, net Rp 250,74 miliar).
- `test_visual.py::test_typing_while_an_answer_arrives_keeps_focus` gagal sekali dalam suite penuh dan sekali di basis
  tanpa perubahan; lulus 3× sendirian. Ini masalah timing yang sudah ada, bukan akibat perubahan ini.

**Fase 5 — penutupan (2026-10-16):**
- Perbandingan EXEC dengan perilaku ter-deploy: semua butir EXEC-IMPL-1016 Fase 1–4 ter-deploy dan dicek live. Yang
  dibangun lebih sempit atau berbeda dari rencana tercatat di fase masing-masing (kamus diturunkan saat berjalan, bukan
  tabel + job; progres lewat proxy BFF, bukan kolom job; tabel dicocokkan lewat judul, bukan penanda; lampiran per
  baris, belum per kolom/sel; kemampuan `value_lookup` diturunkan dari efek alat).
- Sebelum dan sesudah (run sejenis `edge_2f7523a7…` dan kasus yang memicu O1):

| Kasus | Sebelum | Sesudah |
|---|---|---|
| "Cari saja … tanggal efektif …" | INSIGHT, 336 dtk, gerbang hasil lama salah sasaran | CONTINUE, 139 dtk, fakta EVENT_DATE tercatat |
| Kode saham di scope | 9 panggilan `get_dimension_values` ditolak | aturan di prompt dan deskripsi alat; `search_values` |
| "BRI", "Mandiri" | ditebak model | `search_values`: BRI ambigu (BBRI/AGRO), Mandiri → kandidat; jawaban menyebut kode |
| Kode salah "BBRX" | 0 baris, diam-diam | `VALUE_NOT_FOUND` dengan kandidat, model bertanya balik (32 dtk) |
| Rasio tanpa satuan | gerbang UNITS di akhir, kode dijalankan ulang | peringatan saat rilis, saran yang lolos cek |
| G13 cakupan entitas | mati (cek selalu false) | aktif lewat `search_values` |
| Gabung `Symbol`/`ticker` | dua kolom entitas | satu kolom, salinan kanan dicatat |
| Saat run berjalan | "AI request running" | waktu, langkah sekarang, langkah selesai |
| Bukti di Sources | daftar rujukan angka | tabel hasil + "Ask AI to export data" |
| Bertanya soal baris tabel | ketik ulang | lampirkan baris (chip), model membaca tabelnya |

- Sisa dan usulan (menunggu keputusan user, tidak dikerjakan):
  - O4 (M166, kalender MSCI) dan O5 butir 5 (anggaran penalaran, A/B): ditunda user.
  - Satu baris alias kurasi "BRI" → BBRI (`AI_entity_alias`, MANUAL) agar "BRI" tidak ambigu dengan AGRO.
  - Jalur lama `/v1/query` dan `/v1/lookup` (mati di dev) belum memakai cek kamus.
  - Lampiran per kolom atau per sel; pilihan dari kandidat ambigu belum wajib ditulis di asumsi.
  - `test_visual.py::test_typing_while_an_answer_arrives_keeps_focus` kadang gagal karena timing (juga di basis).
- Bagian EXEC yang selesai (EXEC-OPEN-1015, UI-1015E, M164, EDGE-CTX, UI-1015B, M163) diberi status selesai di
  judulnya. Penghapusan dari EXEC.md (aturan AGENTS) menunggu user menyatakan eksekusi ini selesai ("conclude").

### EXEC-REVIEW-1015: tinjauan semua EXEC terbuka dan arsitekturnya (2026-10-15; user: "please review all exec, inspect arsitektur ... contrast what ideal conditions would look like")

**Keputusan user 2026-10-15:** "O5 nanti dulu A/B test tidak perlu dahulu. Sisanya OK untuk O5 masukan exec jangan execute
dulu. O4 skip dulu."

**Yang masih terbuka (menunggu go):** EXEC-OPEN-1015 O1 (= EXEC-M164), M167, O2, O3, O5 (butir 1–4); EXEC-UI-1015E;
EXEC-EDGE-CTX (B lalu A); EXEC-UI-1015B (progres run). Ditunda: O4 (M166 OPEN), O5 butir 5. EXEC-M163 butir 2–4 digabung:
butir 2 → O2/O3, butir 3 → O5 butir 1, butir 4 → O1. PLAN 11 (kamus nilai kolom kategori tabel bertanggal, keputusan
`pg_trgm`) digabung dengan O1 menjadi satu kamus entitas dan nilai.

**Temuan arsitektur:**
1. O3 butuh sinyal "giliran ini menjelaskan hasil lama", tetapi O2 dibatasi user ke kartu kemampuan (tanpa kolom router
   baru). Usulan: sinyal diturunkan dari bukti jawaban — draf yang mengutip angka hasil giliran sebelumnya wajib sudah
   membuka hasil itu; tanpa kolom router.
2. O2 dan O5 butir 1 sama-sama mengubah router (instruksi; nama perubahan fakta di `design_value_changes`). AGENTS: ubah
   router → `AI_ROUTER.md` dan benchmark router sebelum deploy (berbayar kecil, ±USD 0,07; saldo kunci ±USD 0,42). Satu
   benchmark untuk keduanya; set kasus ditambah kasus batas (mis. "Cari saja … di tanggal efektif tersebut").
3. Perubahan prompt (O1 aturan nilai teks, O3 catatan gabungan, O5 default tafsir dan bertindak lebih awal) → satu snapshot
   prompt.
4. O1 menyentuh empat layanan: Governor (`get_dimension_values` untuk kolom entitas tabel statis, cek daftar nilai,
   `value_domains`), sandbox (`resolve_text_values` cek kode entitas), orc (alat `resolve_entities`, prompt), database
   (tabel alias baru: migrasi, Table/Column_Catalog, cek Part A, Tool_Catalog, AI_TOOLS).
5. M167 kecil dan berdiri sendiri: runtime sandbox (`emit_table` peringatan) + teks `UNITS_INSTRUCTION` orc.
6. EDGE-CTX menambah kontrak baru orc ↔ BFF ↔ EDGE (`tables` di jawaban, `attached_selection` di permintaan).
7. Kebersihan dokumen: EXEC.md 3.937 baris, banyak bagian selesai belum dipindah (AGENTS: catat di ERRORS/changelog lalu
   hapus); judul EXEC-W dan EXEC-Y masih "menunggu go" padahal sudah dikerjakan.

**Urutan eksekusi yang diusulkan (setiap fase: tes, deploy SUCCESS, cek live bila saldo cukup):**
- Fase 1 (kecil, tanpa ubah router): M167; UI-1015E; O1 aturan nilai teks di prompt dan deskripsi alat.
- Fase 2 (router, satu benchmark): O2 kartu kemampuan; O5 butir 1 fakta berversi; O3 gerbang dari bukti + catatan gabungan;
  O5 butir 2–4.
- Fase 3 (data, perlu Part A dan migrasi): O1 kamus entitas dan nilai (alias, `resolve_entities`, cek kode entitas,
  kolom kategori tabel bertanggal), menggantikan PLAN 11.
- Fase 4 (kontrak EDGE): EDGE-CTX B lalu A; UI-1015B.
- Kebersihan EXEC.md (dokumen saja) kapan saja.

### EXEC-OPEN-1015: empat item run `edge_2f7523a7…` yang wajib dibereskan (dicatat 2026-10-15; O1, O2, O3, O5 butir 1–4 selesai lewat EXEC-IMPL-1016; O4 dan O5 butir 5 ditunda)

**Permintaan user 2026-10-15:** "Jangan sampai item2 tersebut lepas/terlewat, ingatkan terus sampai kita conclude
eksekusi dan go, saya mau kita bereskan." Setiap balasan kepada user menyebut status keempat item ini sampai semuanya
tuntas (dieksekusi dan diverifikasi, atau diputuskan tidak dikerjakan).

| # | Item | Status |
|---|---|---|
| O1 | `get_dimension_values`, aturan nilai teks tersimpan, nama → kode (alias, `resolve_entities`) | selesai (EXEC-IMPL-1016 Fase 1.3 dan 3): kamus nilai, `search_values`, cek nilai di sandbox dan Governor summary; terverifikasi live |
| O2 | Pertanyaan "Cari saja …" masuk kelas INSIGHT | selesai (Fase 2.1): kartu kemampuan router; live "Cari saja …" kini CONTINUE |
| O3 | Penolakan `INSIGHT_SOURCE_NOT_OPENED` | selesai (Fase 2.2): gerbang dari isi jawaban, satu brief per giliran |
| O5 | Waktu berpikir habis untuk ragu (tanggal, arti pertanyaan), bukan untuk hitung | butir 1–4 selesai (Fase 2.3–2.4: fakta percakapan, tafsir default, bertindak lebih awal); butir 5 (anggaran penalaran, A/B) ditunda |
| O4 | Kalender MSCI disusun ulang dari ingatan | ditunda user 2026-10-15 ("O4 skip dulu"); M166 tetap OPEN |

**Keputusan user 2026-10-15 (putaran 3):** "O1: get_dimension_value harus ada, karena ini penting"; "O2: saya setuju hanya
untuk router diberi tahu fungsi dan kemampuan setiap jalur"; "O3: OK masukan exec jangan execute dulu"; O4 ditanya: "berarti
masalahnya adalah bagaimana tanggal tersebut didapatkan at the first place?".
- O1: alat tetap. Tiga gesekan `edge_b90899…`/`edge_417e…`: (a) 9 panggilan ditolak: aturan prompt untuk kategori dibaca
  berlaku untuk kode saham; (b) gerbang UNITS: aturan satuan sudah tertulis di deskripsi `run_python` dan prompt, tetapi
  kolom rentang harga (rasio) tidak dianggap rasio oleh model, dan pemeriksaan baru terjadi di gerbang jawaban akhir
  (setelah draf ditulis) — usulan: peringatan saat `emit_table` untuk kolom desimal tanpa satuan (diturunkan dari nilai,
  seperti `units_advice`), bukan di akhir; (c) kolom kembar: tabel broker menamai kode saham `Symbol`, tabel harga `ticker`;
  `merge(left_on='Symbol', right_on='ticker')` lalu rename `Symbol`→`ticker` membuat dua kolom `ticker` — usulan: data
  yang disiapkan memberi kolom entitas satu nama baku di semua tabel (dari kolom entitas katalog) atau helper gabung dari
  relasi katalog. Usulan O1 (a)–(c) menunggu go.
- O2 (disetujui untuk dirumuskan): hanya kartu kemampuan per jalur di prompt router (CLARIFY, ANSWER/INSIGHT di jalur cepat,
  CONTINUE, NEW_TOPIC: apa yang dikerjakan, alat, keluaran, contoh). Kelas baru dan kolom tambahan tidak termasuk. Mode
  INSIGHT jalur cepat (`EXPLORE_INSIGHT_NOTE`): sampai 5 sudut, tiap sudut satu metode pustaka riset lewat
  `saniti.explore_test` (stability, koreksi Benjamini-Hochberg): conditional_distribution, threshold_sensitivity,
  streak_persistence, regime_comparison, cohort_comparison, quantile_ranking, lead_lag, correlation_dependency. Run
  `edge_2f7523a7…` dapat catatan itu, tetapi model menilai "Cari saja" sebagai pencarian (penalaran: "That's a
  lookup/description, not really a statistical pattern") dan tidak menjalankan uji — jawabannya deskriptif.
- O3 (disetujui untuk dirumuskan, tidak dieksekusi): gerbang "buka hasil lama" terikat pada giliran yang menjelaskan hasil
  lama, catatan gabungan per giliran yang menyatakan aturan itu di awal.
**Putaran 4 (user 2026-10-15):** "setiap WHERE = '' maka harus wajib menggunakan value dari get dimension value, or else
rejected. Rule ini AI harus tahu before hand. Saat ini sudah? Kode saham harusnya kategori juga ... lets align dulu tipe
data yang bisa dipakai di get dimension value"; "peringatan langsung saat tabel dirilis (emit_table) untuk kolom desimal
tanpa satuan ... --> approved"; "AI harus mengulang? ... cek deh kodenya"; "can I confirm bahwa mode 5 itu di test ...
then kok bisa lama sekali?".
- Penegakan yang sudah ada (P14, 2026-10-01, sandbox `resolve_text_values`): nilai saringan teks dicocokkan ke ejaan
  tersimpan tanpa peduli huruf besar/kecil; nilai yang tidak ada ditolak `VALUE_NOT_FOUND` dengan daftar nilai tersimpan,
  sebelum data dibaca. Hanya untuk kolom yang daftar nilainya lengkap: CHECK constraint, atau kolom kategori tabel statis
  (≤ 1.024 nilai). Celah: kode saham (kolom entitas) hanya dijadikan huruf besar, tidak dicek ada; kolom teks tabel
  bertanggal tanpa CHECK tidak dicek. AI belum diberi tahu di awal bahwa nilai di luar daftar ditolak.
- Tipe yang dilayani `get_dimension_values` sekarang: kolom teks (text/varchar/char), `group_by_allowed`, di tabel statis
  (tanpa kolom waktu), bukan kolom entitas, ≤ 2.000 nilai berbeda (≤ 200 dikembalikan, saring dengan `match`). Kode saham
  di `IDX_Stock_Universe` adalah teks tetapi kolom entitas, jadi ditolak.
- Usulan penyelarasan (menunggu go): kolom entitas tabel referensi statis (kode saham, kode broker) ikut dilayani dengan
  `match` atau daftar nilai yang dicek (kembali: ada / tidak ada); validator mengecek kode entitas di scope terhadap tabel
  referensinya (diturunkan dari relasi katalog) dan menolak yang tidak ada; aturan "nilai teks harus dari daftar tersimpan,
  atau ditolak" ditulis di prompt dan deskripsi alat; kolom teks tabel bertanggal mendapat daftar nilai dari CHECK atau
  katalog, selain itu ditandai.
- Disetujui: peringatan saat `emit_table` untuk kolom desimal tanpa satuan (ERRORS M167). Temuan: gerbang UNITS menolak
  angka yang sudah ditulis `|pct:1` (kolom dirilis tanpa `units=`), padahal pesannya menawarkan `|pct` sebagai
  perbaikan; AI lalu menjalankan ulang kode dan menulis ulang jawaban (57 dtk). Pesan disesuaikan dengan cek (go).
- Mode INSIGHT di `edge_2f7523a7…`: `explore_mode="insight"` aktif, tetapi tidak ada satu pun `explore_test` dijalankan
  (0 di log dan di kode iterasi 2); jawabannya tabel deskriptif. Waktu berpikir panggilan pertama (17 bagian penalaran,
  ±66 ribu karakter, kira-kira menurut topik): cakupan dan tanggal efektif ±40%, arti pertanyaan (bruto/net, tipe
  investor) ±35%, menyusun spesifikasi data dan kode di kepala ±20%, memutuskan perlu uji atau tidak ±6%.
**Putaran 5 (user 2026-10-15):** "semua Where ='X', X ini harus dari table ... didapat dari get dimension value ... user
bilang BRI, tapi kode tickernya BBRI ... How we handle this? Apakah sudah ada?"; M167 "OK masukan exec ya, jangan execute
dulu"; "bagaimana kita bisa buat supaya waktu habis untuk hitung/analisa data instead of meragukan yang lain ya? Coba seek
best practice."
- O1 (nama → kode): yang ada sekarang: (1) P14 membetulkan huruf besar/kecil dan menolak nilai kategori yang tidak
  tersimpan; (2) `lookup_reference` bisa mencari baris tabel referensi dengan potongan teks (`match`) di satu kolom, mis.
  "Rakyat" di `Company Name` → BBRI. Yang belum ada: alias dan singkatan. `IDX_Stock_Universe` hanya punya `Ticker`,
  `Company Name` ("PT Bank Rakyat Indonesia (Persero) Tbk Class B"), ISIN, Sector, Industry; "BRI" tidak cocok dengan
  potongan teks mana pun, jadi model menerjemahkannya dari pengetahuannya sendiri tanpa cek. Usulan (praktik umum entity
  linking: kamus alias + pencocokan + konfirmasi bila ragu): tabel alias entitas (kode, alias, jenis alias: singkatan,
  nama pendek, merek, kode lama; sumber), diisi otomatis dari nama perusahaan (singkatan kata: Bank Rakyat Indonesia →
  BRI; nama tanpa "PT", "Tbk", "(Persero)") ditambah koreksi manual; alat `resolve_entities(["BRI", "Mandiri"])` →
  kandidat dengan alasan cocok (kode persis, alias persis, mirip); validator menolak kode yang tidak ada dan menyertakan
  kandidat; bila lebih dari satu kandidat, AI boleh bertanya balik. Berlaku juga untuk broker ("Mandiri Sekuritas" → CC) dan
  nanti seri makro. Menunggu keputusan; tabel baru perlu cek Part A.
- M167: masuk EXEC, tidak dieksekusi (peringatan satuan saat `emit_table` + pesan gerbang sesuai cek).

**Putaran 6 (user 2026-10-15):** "Ok. O1 masukan exec jangan jalankan dulu" dan, atas O5 butir 1 ("AI diberi tahu fakta itu
berlaku kecuali Anda mengubahnya"): "Tapi kadang ada LIFO, yang berlaku adalah message yang dikirimkan user belakangan. How
we handle this?"
- O1 (tabel alias entitas, `resolve_entities`, validator kode entitas, aturan nilai teks tersimpan di awal, penyelarasan
  tipe `get_dimension_values`) masuk EXEC, tidak dijalankan.
- Yang sudah ada untuk "pesan terbaru berlaku": nilai desain uji (horizon, ambang, efek minimum; M82 dan variants)
  dibaca router dari pesan terbaru sebagai perubahan terstruktur REPLACE / ADD / REMOVE, dan pesan terbaru yang menang
  (`user_words.py`, dengan catatan bila pola teks dan bacaan router berbeda); M64: hasil terbaru menjadi rujukan bawaan.
  Belum ada untuk fakta percakapan (daftar entitas, tanggal peristiwa, definisi).
- Usulan untuk O5 butir 1: fakta disimpan berversi dengan asalnya (pesan user, data database, web, tafsiran AI) dan giliran
  yang menetapkannya; router membaca setiap pesan baru untuk perubahan fakta dengan bentuk yang sama (REPLACE / ADD /
  REMOVE; nama: ENTITY_SET, EVENT_DATE, DEFINITION); urutan berlaku: pernyataan user terbaru > pernyataan user lebih awal >
  data database terverifikasi > hasil web > tafsiran AI; fakta yang digantikan tidak dihapus (bisa "kembali ke yang
  tadi"); bila pernyataan user terbaru bertentangan dengan data terverifikasi (mis. user menyebut 25 Nov, rilis resmi
  menyebut penutupan 24 Nov), pernyataan user dipakai tetapi perbedaannya disebut di jawaban, atau AI bertanya balik bila
  maknanya ragu; pesan yang tidak mengubah fakta tidak menyentuhnya.
- O5 (baru) waktu habis untuk menganalisis, bukan meragukan: lihat bagian EXEC-OPEN-1015 O5 di bawah tabel.
- O4: ya. Tanggal didapat lewat 6 panggilan `research_web` di `edge_ca6cf5a4…` (16 sumber: idx.co.id 5, bisnis.com 3,
  katadata 2, CNBC, Kontan, IDX Channel, OJK, Bank Dunia, msci.com 1); model menyalinnya ke teks jawaban, tanpa tabel
  dan tanpa membedakan pengumuman, penutupan implementasi dan hari efektif; media menulis "efektif" dengan arti berbeda.

**Pertanyaan lanjutan user 2026-10-15 dan jawabannya** (user: "O1: Maksudnya get dimension value itu untuk apa? ... O2
silahkan benchmark dengan best practice terlebih dahulu ... O3 ... kenapa AI tidak tahu bahwa ia harus melakukan ini
beforehand? Coba cek log. O4: ... kenapa harus dari ingatan, padahal kan jawaban itu baru di reply"):
- O1: setara SQL `SELECT DISTINCT kolom FROM tabel WHERE kolom ILIKE '%kata%' ORDER BY 1 LIMIT 200`, lewat Governor; nilai
  yang didapat dipakai di scope data need (`PREDICATE kolom = 'Banks'`), yang Governor kompilasi menjadi `WHERE`. Ya, untuk
  saringan.
- O2: perbandingan praktik umum router (kelas didefinisikan oleh kemampuan penanganannya, satu dimensi per keputusan,
  contoh positif dan negatif per kelas, kasus batas di benchmark berlabel, matriks kebingungan) dengan router sekarang
  (kelas berdasarkan niat user, mencampur "hubungan dengan hasil lama" dan "jenis kerja", tidak tahu apa yang dilakukan mode
  INSIGHT di jalur cepat, benchmark 24 kasus tanpa kasus "daftar baru atas konteks"). Usulan di balasan; benchmark
  berbayar kecil menunggu perintah.
- O3: log: catatan INSIGHT dikirim (`conversation_turn_routed` turn_kind INSIGHT untuk `-m4i`), tetapi penalaran panggilan
  pertama tidak pernah menyebutnya; yang ditimbang hanya catatan cakupan router dan catatan explore jalur cepat. Tiga
  catatan berbeda arah untuk satu giliran; catatan INSIGHT tidak menyebut bahwa penyelesaian akan ditolak. Gerbang perlu
  terikat pada "menjelaskan hasil lama" (bukan nama kelas).
- O4: tanggal ada di riwayat (penalaran mengutip "the answer said ... 27 Agu 2025"; `history_turns_dropped=0`); model
  memakainya tetapi meragukannya dengan pengetahuannya sendiri karena teks riwayat tidak konsisten dan tidak membedakan
  pengumuman, penutupan implementasi dan hari efektif. Keraguan itu sebagian benar: MSCI November 2025 diimplementasikan
  pada penutupan 24 Nov 2025 (rilis resmi), Agustus 2025 pada penutupan 26 Agu 2025 (berita); jawaban memakai hari
  sesudahnya (ERRORS M166).

**O5 (usulan 2026-10-15, praktik umum agen analisis):** di `edge_2f7523a7…` ±75% penalaran panggilan pertama untuk ragu
(tanggal, cakupan, arti pertanyaan), ±20% menulis spesifikasi dan kode sebelum data ada. Praktik yang dipakai sistem agen
data: (1) fakta percakapan terstruktur sebagai sumber kebenaran (entitas, tanggal peristiwa dengan maknanya, definisi yang
sudah dipilih), bukan teks jawaban lama — di sini: data record membawa "fakta yang sudah ditetapkan" dan model diberi tahu
fakta itu berlaku kecuali user mengubahnya; (2) default tafsir yang tertulis, bukan ditimbang ulang tiap kali — memperluas
`FASTLANE_DEFAULTS` dengan default arti (pembelian tertinggi = net, bruto ditampilkan; "investor asing" = tipe investor;
tanggal peristiwa = penutupan implementasi), dinyatakan sebagai asumsi, user bisa mengubah, AI tetap boleh bertanya balik;
(3) satu catatan per giliran tanpa arah yang bertabrakan (O3); (4) bertindak lebih awal: kirim data need begitu cakupan
jelas, tulis kode setelah profil data datang; (5) anggaran penalaran: panggilan pertama jalur cepat diukur pada tingkat
medium vs high (perubahan model setting, perlu persetujuan dan A/B kecil berbayar). Ukur: token penalaran dan waktu per
fase per run (log sudah ada), sebelum dan sesudah.

**O1.** Kegunaan alat: ejaan nilai kategori yang tersimpan (mis. "Banks", "Regular") untuk saringan; saringan dengan ejaan
salah tidak gagal, hanya mengembalikan nol baris tanpa peringatan, jadi alat ini mencegah jawaban kosong diam-diam.
Governor hanya melayaninya untuk kolom teks kategori di tabel statis; kolom entitas (kode saham) dan tabel bertanggal
ditolak. Deskripsi argumen alat sudah menyebut "static table" dan "not its entity column" (koreksi: catatan M164 awal
menyebut deskripsi tidak menyebutnya; yang tidak menyebut hanya kalimat utama). Penyebab pemakaian salah (penalaran
`edge_b90899…`): aturan prompt "take exact values from get_dimension_values and never type a member list yourself", plus
keinginan wajar memastikan 9 kode saham ada; alat untuk itu tidak ada, maka ia memakai alat yang salah 9 kali. Usulan:
(a) aturan prompt hanya untuk kategori; nilai yang user tulis (kode saham, tanggal) diketik di scope apa adanya;
(b) hasil penyiapan data menyebut entitas yang diminta tetapi tidak punya baris (berlaku untuk semua daftar entitas:
saham, broker, nanti seri makro), sehingga cek keberadaan terjadi setelah ekstraksi tanpa panggilan tambahan; (c)
kalimat utama deskripsi alat menyebut batasnya.

**O2.** Kelas router untuk giliran lanjutan: CLARIFY (tanpa hitungan baru), INSIGHT (mengapa/apa yang menonjol, rincian
hasil yang sudah ditampilkan; aturannya: "rekap atau daftar menurut sesuatu yang belum ada di hasil → INSIGHT"),
CONTINUE (analisis atau uji lanjutan), NEW_TOPIC (tidak bergantung pada hasil sebelumnya). "Cari saja di tanggal efektif
tersebut broker asing teratas" bergantung pada hasil sebelumnya dan meminta daftar baru, jadi aturan memilih INSIGHT
(log: `turn_kind="INSIGHT"`, `referent="NEWEST_RESULT"`). Masalahnya nama INSIGHT dipakai dua arti: di router "hitungan
baru atas konteks sebelumnya", di jalur cepat "boleh menguji sampai 5 sudut dengan explore_test" (`explore_mode="insight"`),
dan memicu gerbang O3. Golongan: setiap permintaan daftar/angka baru atas konteks percakapan. Usulan A: kelas baru
(mis. LOOKUP: daftar atau angka baru yang memakai konteks sebelumnya, bukan penjelasan hasil) → jalur cepat mode ANSWER,
tanpa gerbang O3; AI_ROUTER.md dan benchmark router ikut. Usulan B: INSIGHT tetap, tetapi mode explore dan gerbang O3
hanya untuk penjelasan ("mengapa", "apa yang menonjol") yang dibaca router sebagai `explains_result`. Rekomendasi: A.

**O3.** Gerbang `INSIGHT_SOURCE_NOT_OPENED` (H1, M63, golden test 2026-10-02): giliran INSIGHT yang tidak pernah membuka
tabel hasil sebelumnya ditolak saat menyelesaikan analisis, karena dulu penjelasan yang membangun ulang hasil dengan
definisi tebakan menghasilkan angka yang bertentangan. Di run ini pertanyaannya bukan penjelasan, jadi AI membuka dua tabel
lama hanya untuk lolos gerbang: 1 putaran tambahan (16 dtk) dan tabel hasil ganda (out.o19, out.o20). Golongan: gerbang
yang menegakkan aturan satu kelas pada pesan yang salah kelas. Usulan: gerbang hanya untuk giliran penjelasan (ikut O2);
aturan penjaminnya tetap (penjelasan hasil lama wajib membuka hasil itu).

**O4.** Tanggal efektif MSCI di percakapan ini berasal dari riset web giliran `edge_ca6cf5a4…` ("saham yang secara
historis ada di MSCI 2-3 tahun terakhir"): giliran itu tidak merilis tabel hasil (outputs kosong), tanggalnya hanya ada di
teks jawaban, dan sumbernya tidak seragam (AVIA: "efektif 26 Nov 2024" dan "penutupan 25 Nov 2024"; Small Cap Mei 2024:
"efektif 1 Juni 2024", hari Sabtu). Giliran berikutnya tidak punya data terstruktur, jadi model membaca ulang teks dan
menebak aturan kalender MSCI dari ingatan (hari kerja terakhir bulan, penutupan sehari sebelum efektif). Praktik umum
studi peristiwa indeks: kalender peristiwa adalah data rujukan bertabel (penyedia indeks, tinjauan, tanggal pengumuman,
tanggal implementasi = penutupan perdagangan, saham masuk/keluar, URL siaran resmi, tanggal diambil), diselaraskan ke
kalender bursa (hari 0 = hari perdagangan terakhir pada atau sebelum penutupan implementasi), dan semua jendela dihitung
dalam hari perdagangan dari tabel itu, bukan dari ingatan. Usulan: (a) segera: hasil riset web yang memuat tanggal atau
daftar entitas dirilis sebagai tabel hasil terstruktur dengan sumber per baris, dan giliran berikutnya memuatnya
(`load_output`); (b) nanti: tabel katalog peristiwa indeks (MSCI, FTSE, LQ45, IDX80) dari siaran resmi lewat pipeline,
sejalan dengan kalender makro (BI, FOMC, rilis data) — perlu cek Part A dan keputusan user sebelum dimuat.

### EXEC-UI-1015E: kepala jawaban dan baris metadata (dicatat 2026-10-15; "masukan EXEC jangan execute dulu"; selesai lewat EXEC-IMPL-1016 Fase 1.2, ter-deploy)

**Permintaan user 2026-10-15** (tangkapan layar kepala jawaban): "A. kembalikan seperti awal tapi tanpa tulisan AI ya;
B. ini nama mode saja langsung; C. tidak perlu ada fast lane, karena ini default".
- A: gaya kepala jawaban kembali seperti sebelum EXEC-UI-1015D (huruf kecil-besar paksa, jarak huruf, warna redup), teks
  "EDGE · COMPLETED" (status tetap berbahasa Inggris sesuai D3; dikonfirmasi saat go).
- B: baris metadata menampilkan nama model (label dari daftar model EDGE, mis. "DeepSeek V4.1 Flash") alih-alih id
  `deepseek/deepseek-v4.1-flash`; id tetap di tooltip; model di luar daftar tetap memakai id-nya.
- C: "Fast lane" dihapus dari baris metadata (jalur cepat adalah bawaan sejak D1).
- Cek: tes EDGE untuk kepala dan baris metadata; QA live desktop dan ponsel.

### EXEC-M164: aturan alat terlihat sebelum dilanggar (dicatat 2026-10-15; "Solusi M164 OK ... jangan execute dulu"; selesai lewat EXEC-IMPL-1016 Fase 1.3 dan 3, ter-deploy)

**Akar masalah (terbukti dari penalaran `edge_b90899…` iterasi 1 dan kode):** aturan DATA NEED di prompt orc "take exact
values from get_dimension_values and never type a member list yourself" ditulis untuk saringan lewat tabel lain (mis.
"bank saja"), tetapi model menerapkannya ke kode saham yang user sebut sendiri; ia memanggil `get_dimension_values` 9 kali
pada kolom ticker, dan Governor menolak setiap panggilan (`DIMENSION_IS_ENTITY`: kolom entitas tidak dilayani, daftar
entitas masuk ke scope). Deskripsi `get_dimension_values` tidak menyebut bahwa kolom entitas dan tabel bertanggal ditolak.
Bukan katalog alat yang usang: Tool_Catalog (`round_u`) dan alat yang ditawarkan sudah benar; yang kurang adalah aturan
yang tidak dinyatakan sebelum dipanggil. **Golongan:** setiap batas yang ditegakkan Governor atau sandbox tetapi tidak
tertulis di deskripsi alat atau prompt (kolom entitas, tabel bertanggal, satuan sebelum rilis).
- Usulan: (1) deskripsi `get_dimension_values` menyebut kolom yang dilayani, diturunkan dari peran kolom di katalog
  (entitas dan waktu tidak; kategori ya), dan `get_catalog_details` menandai peran itu per kolom; (2) kalimat prompt
  DATA NEED dibatasi: nilai yang user tulis (kode saham, tanggal) diketik apa adanya di scope; `get_dimension_values`
  hanya untuk ejaan kategori; (3) aturan satuan sebelum rilis ditulis di deskripsi `emit_table`/`run_python`. Snapshot
  prompt dan `AI_TOOLS.md` ikut diperbarui; tes: satu permintaan dengan kode saham dari user tidak memanggil
  `get_dimension_values`.

### EXEC-EDGE-CTX: lampirkan pilihan tabel sebagai konteks (A) dan bukti data di Sources (B) (dicatat 2026-10-15; "OK, masukan exec ya. Jangan execute dulu"; selesai lewat EXEC-IMPL-1016 Fase 4.1 dan 4.2, ter-deploy)

Dipindah dari `FUTURE_PLAN.md`. Fakta: setiap angka tabel jawaban berasal dari tabel hasil sandbox (`{{table out.oN}}`),
tetapi EDGE hanya menerima teks tabelnya; data mentah di balik angka bisa dikeluarkan dengan alat yang ada (muat ulang
data jawaban, saring, rilis, `export_result`).
- **A (lampirkan pilihan):** orc menyertakan peta tabel di jawaban (`tables`: urutan, `output_id`, kolom tampil → kolom
  hasil, kunci baris). EDGE: memilih sel/kolom/baris memunculkan "Attach to question"; pilihan tampil sebagai chip di atas
  kolom tanya dan dikirim sebagai `attached_selection {output_id, columns, row_keys, shown_values}`; orc memberi model
  catatan sumbernya; "keluarkan raw data" → `get_lineage`, muat data sumber, saring, rilis, ekspor.
- **B (Sources):** "Bukti (N)" diganti daftar tabel hasil jawaban (nama, baris, kolom, data per), masing-masing dengan
  "Ask AI to export data". Panel Pinned responses: keputusan saat go.
- Urutan usulan: B lalu A. Cek: tes kontrak orc ↔ EDGE, tes EDGE, satu run live berbayar atas perintah.

### EXEC-UI-1015D: jalur cepat selalu, label pemilih model berbahasa Inggris, kepala jawaban "Edge · Completed", tabel ringkas (dicatat 2026-10-15; go 2026-10-15)

**Go 2026-10-15** (user: "D1 OK D2 OK D3 OK D4 OK"; D1 sesuai usulan: hanya di EDGE, jalur standar tetap di orc).
**Hasil (ter-deploy):** `2e201d7` → edge-bff `1aca46e9` SUCCESS. Pesan EDGE selalu `lane=fast`, baris Jalur hilang
(pilihan "standard" lama diabaikan); pemilih model berbahasa Inggris (AI model, Price per 1M tokens, Prices updated,
Reasoning, Low/High/Max); kepala jawaban "Edge · Completed" tebal; tabel selebar isinya, kolom kode/tanggal/angka satu
baris (diturunkan dari isi sel ≤ 16 karakter atau kolom angka/tanggal), teks membungkus per kata (12–28 karakter),
sel 8×12 px (ponsel 6×10), kolom pertama menempel di ponsel. Penyebab kata terpotong terkonfirmasi: `overflow-wrap`
diwarisi dari blok jawaban; sel kini `normal`. QA live 390 dan 1440 px: tanpa baris Jalur, tanpa kata terpotong, tanpa
luapan horizontal. Tes `test_ui_1015c.py` (tabel ringkas), `test_browser.py` (jalur cepat selalu).

**Permintaan user 2026-10-15** (tangkapan layar ponsel): "bisa buat semua jalur cepat fastlane latest V by default,
sehingga kita tidak perlu ada opsi jalur"; "harga per juta. harga diperbaharui dll bisa di conver jd bahasa inggris?
termasuk kata tingkat berpikir, rendah tinggi maks"; "1. edge AI jadi Edge 2. selesai ganti Completed tanpa tulisan
berjarak buat nice and bold"; "screenshot 1-3 lihat jarak antara kolom tidak compact. seek best practice ya".
- **D1 Jalur cepat selalu.** Semua saklar V terbaru jalur cepat sudah menyala di dev (`AI_FASTLANE_V5_PRESENTATION`,
  `_DECISION_RULES`, `_GATE_ADVICE`, `_SECTION_CAPS`, `_CONVENTION_NUMBERS`, `_EXPLORE_TESTS`, `_ABANDONED_SESSIONS`;
  `AI_FASTLANE_DRAFT_CHECK=false` tetap). Usulan: EDGE selalu mengirim `lane=fast` (bila orc melaporkan
  `lane_selection`) dan baris "Jalur" hilang dari pemilih model; pilihan "standard" yang tersimpan diabaikan. Jalur standar
  tetap ada di orc sebagai cadangan lewat API (A/B, golden test). Pertanyaan: cukup di EDGE, atau orc juga memakai jalur
  cepat untuk permintaan tanpa jalur?
- **D2 Bahasa Inggris di pemilih model** (`edge-labels.js`): "AI model", "Price per 1M tokens", "Prices updated 15:46
  WIB", "Reasoning", Low/Medium/High/Max/Off/On, "Choose model and reasoning"; label tingkat di baris metadata jawaban
  ikut ("· High").
- **D3 Kepala jawaban:** "EDGE AI · SELESAI" (huruf besar, berjarak) menjadi "Edge · Completed", tebal, tanpa jarak huruf
  dan tanpa huruf kapital paksa; status lain ikut berbahasa Inggris (Limited, Awaiting approval, Needs your answer,
  Paused, Failed).
- **D4 Tabel ringkas (praktik umum tabel data):** penyebab terukur di CSS: `.data-table {width:100%}` merentangkan
  kolom selebar kartu dan kolom pertama dipaksa minimal 140 px, sementara kolom teks dipaksa membungkus per huruf
  ("Internati / onal") oleh `overflow-wrap:anywhere` pada blok jawaban (dikonfirmasi lewat gaya terhitung saat
  dibangun). Usulan: lebar tabel mengikuti isi (`width:max-content; min-width:100%` hanya bila lebih sempit), tanpa lebar
  minimum kolom pertama; kode, tanggal dan angka tidak membungkus; teks membungkus per kata dengan lebar 12–28 karakter;
  padding 8×12 px (ponsel 6×10 px); kolom pertama menempel saat digulir ke samping di ponsel; gulir samping di dalam
  bingkai tetap. Berlaku untuk semua tabel jawaban, tidak per tabel.
- Cek: tes EDGE (tidak ada baris Jalur, `lane=fast` terkirim, label Inggris, kepala jawaban, lebar kolom: tabel 3 kolom
  pendek tidak melebar, tidak ada kata terpotong di tengah), QA live desktop dan ponsel dengan tangkapan layar.

### EXEC-M163: batas waktu panggilan model yang benar-benar berlaku, catatan INSIGHT, tindak lanjut memakai tabel jawaban sebelumnya (dicatat 2026-10-15; butir 1 go 2026-10-15; selesai lewat EXEC-IMPL-1016 butir 1 dan Fase 2, ter-deploy)

**Go butir 1 2026-10-15** (user: "Klien model: jawaban dibaca sebagai aliran dan ditutup tepat pada batas waktu total
... --> ini OK"). **Hasil:** `2e201d7` → market-ai-orc `ed07e66c` SUCCESS: setiap panggilan model dibaca sebagai aliran
dan ditutup pada batas totalnya (batas panggilan, atau `AI_REQUEST_TIMEOUT_SECONDS`), log `ai_provider_call_deadline`;
tes server yang mengirim byte tiap 30 dtk terpotong di 90–120 dtk. Butir 2–4 belum disetujui.

Dasar: ERRORS M163 dan M164 (run `edge_2f7523a7…` 336 dtk; 210 dtk di panggilan pertama; batas 90 dtk jalur cepat tidak
pernah terpicu). Usulan: (1) klien model membaca jawaban sebagai aliran dan menutupnya pada batas waktu total, dengan log
`ai_lane_call_timeout` saat terpicu dan tes terhadap server lambat yang terus mengirim byte; (2) catatan INSIGHT jalur
cepat: `explore_test` dipakai bila user meminta pola, permintaan "cari/daftar" dijawab dengan tabelnya; (3) tindak lanjut
yang merujuk entitas atau tanggal jawaban sebelumnya diarahkan ke tabel yang sudah dirilis (muat, jangan susun ulang);
(4) deskripsi alat menyebut kolom mana yang dilayani `get_dimension_values` (dari peran kolom di katalog) dan aturan satuan
sebelum rilis (M164). Perubahan teks prompt → snapshot prompt; perubahan alat → AI_TOOLS.md.

### EXEC-UI-1015C: tombol ke percakapan di Response History, tombol kanan atas ke rel kiri, baris status dihapus (dicatat 2026-10-15; go 2026-10-15)

**Go 2026-10-15** (user: "Ok, confirmed. Go."): atas pemahaman ponsel (menu dan "+" ke header; rel kiri hilang, percakapan
selebar layar; ikon pengaturan keluar dari header ponsel dan tetap bisa dibuka dari menu akun; baris Research session
ponsel tetap), favicon logo "E" EDGE (SVG, PNG 32 px, apple-touch 180 px), dan usulan desain M160 (golongan galat
penyedia di klien model, pemutus di orc, router tanpa tanya balik saat penyedia menolak, teks jelas di EDGE, pemantauan
saldo kunci).

**Keputusan user 2026-10-15:** "Yes, perubahan UI sudah confirmed, tapi ini hanya untuk desktop ya." atas pemahaman
berikut (desktop saja, ponsel tidak berubah oleh butir ini):
1. Response History (panel Details): setiap kartu run mendapat tombol "Lihat di percakapan" (di bawah baris status
   simpan); klik menutup panel bila perlu dan menggulir ke jawaban itu; run milik percakapan lain membuka percakapan itu
   dulu.
2. A → B: tombol Details, Pin (bookmark) dan Share dari kanan atas pindah ke rel kiri, di bawah tombol menu dan "+",
   sebagai ikon.
3. C dihapus: baris "Research session · Run N · status" di atas percakapan dihilangkan; status tetap ada di setiap
   jawaban.

**Hasil (2026-10-15, ter-deploy):**
- `1bc7b50` → edge-bff dev `22e386f5` SUCCESS. Desktop: baris Research session hilang di atas 720 px; tombol Details
  (berganti "Hide Details" saat terbuka), Bookmark dan Share (nonaktif) di rel kiri, bersusun di rel sempit (≤1050 px)
  atau tertutup; setiap kartu Response History punya "Lihat di percakapan". Ponsel (≤720 px): menu dan "+" di header
  antara logo dan tombol cari, rel hilang (percakapan 390/390 px), baris Research session tetap, ikon pengaturan keluar
  dari header dan muncul sebagai "Pengaturan" di menu akun; laci riwayat tetap terbuka dari menu. Favicon "E"
  (`/favicon.svg`, `/favicon-32.png`, `/apple-touch-icon.png`, publik, cache 1 hari).
- QA live (Chromium, 1440 px dan 390 px terang/gelap): semua butir di atas lulus, tanpa luapan horizontal; favicon 200.
  Temuan: "Lihat di percakapan" tidak menggulir dari dasar percakapan panjang (ERRORS M161, juga mengenai lompatan pin
  dan tautan bagian). Diperbaiki di susulan (`scrollResearchTo`), tes baru; deploy dan QA ulang dicatat di
  RAILWAY_CHANGELOG.
- Susulan M161 `09e9ddc` → edge-bff `729ee9f3` SUCCESS: kedua lompatan live mendarat 24 px dari atas.
- M160 `1fbec6d` → market-ai-orc `ac4ea638` dan edge-bff `67039127` SUCCESS, startup tanpa `*_inactive`, tidak ada run
  yang terputus. Penolakan akun dikenali dari HTTP 401/402 atau catatan kunci sendiri (`GET /key`, sisa ≤ 0); pemutus 120
  dtk lalu satu panggilan uji; router tidak bertanya balik saat penyedia mati, giliran berakhir `SERVICE_UNAVAILABLE`
  dengan satu baris jelas dan tombol Retry di EDGE; saldo kunci dicatat saat start dan tiap 15 menit. Live: saat start
  tercatat `ai_provider_credit_low` (batas $41,5, sisa $0,42). Jalur penolakan hanya diuji lewat tes (tidak sengaja
  memicu gangguan di live). Variabel baru tidak diset (bawaan 900 dtk dan $2).
- Tes: `tests/test_ui_1015c.py` (6) dan penyesuaian `test_visual.py` (baris sesi hanya di ponsel, pengaturan ponsel lewat
  menu akun); suite EDGE 101 lulus. Tes mengetik kadang gagal sudah ada sebelum perubahan ini (ERRORS M162).

### EXEC-UI-1015B: progres run seperti Claude (dinilai 2026-10-15; usulan, menunggu "go"; selesai lewat EXEC-IMPL-1016 Fase 4.3, ter-deploy)

**Permintaan user 2026-10-15** (tangkapan layar aplikasi Claude dan EDGE): "saat ini ketika AI thinking, maka tulisannya ai request is running. Bisa kamu buat seperti claude? Coba assess dulu kondisi backend ya".
- **Kondisi sekarang (diperiksa di kode):** `POST /v1/agent/run` di orc berjalan sekali jalan sampai selesai; `GET /v1/agent/requests/{id}` menjawab 404 selama run berjalan; BFF hanya tahu state (QUEUED/RUNNING/FINISHED) dan mengumumkan `tool_progress: false`; EDGE menulis satu langkah "AI request running" (`edge-client.js`). Langkah rinci (alat, iterasi, gerbang, `hurdles`) hanya ada di log orc dan baru terlihat di panel Flow sesudah selesai.
- **Usulan:** (1) orc mencatat langkah run saat terjadi dari titik yang sudah ada (panggilan alat, langkah mekanis, gerbang, jawaban): label kata biasa dari `user_texts.py` ("Membaca katalog", "Menyiapkan data (29.908 baris)", "Menjalankan analisis ke-2", "Memeriksa angka jawaban", "Menulis jawaban"), waktu mulai/selesai, status; disimpan di memori per run dan dibaca lewat `GET /v1/agent/requests/{id}/progress` (satu replika orc; run yang terputus deploy sudah ditangani terpisah); (2) BFF membaca progres selama RUNNING, menaikkan `state_version`, `tool_progress: true`; (3) EDGE: penghitung waktu ("2m 1s"), langkah yang sedang berjalan, daftar langkah selesai yang bisa dilipat ("5 langkah"), seperti Claude; sesudah selesai dilipat jadi satu baris. Tanpa panggilan model tambahan dan tanpa menampilkan penalaran mentah AI. Cek: tes orc/BFF/EDGE, cek visual dan interaksi desktop dan ponsel di live dengan satu pertanyaan.
- Tangkapan layar ketiga ("Nothing to stop yet" pada Run 7 pukul 00:44 WIB) adalah run `edge_87c7…` yang terputus deploy ulang A/B V4 (dicatat di EXEC-FASTLANE V5; perbaikan A dan C sudah dideploy dengan V5).

### EXEC-BE1: efisiensi backend dari A/B V4/V5 (disetujui 2026-10-15; go 2026-10-15 "Ok jalankan")

**Hasil BE1-1 (2026-10-15, ter-deploy):** `c997c4d` dan susulan `bb2430d`, sandbox `b1f26312` SUCCESS. Satuan di luar
FRACTION/PERCENT/P_VALUE dibuang dengan peringatan `UNIT_DROPPED` (huruf kecil seperti "percent" dibaca); `thresholds`
berbentuk list atau satu nilai disimpan sebagai dict dengan `THRESHOLDS_CONVERTED`; yang tetap ditolak: kolom yang tidak
ada, operator tak dikenal, kunci definisi tak dikenal (sesuai butir c; versi pertama sempat memindahkannya ke catatan,
diperbaiki di `bb2430d`). Setiap penolakan label menyebut "kirim ulang panggilan emit saja, variabel sesi masih ada"
(`LABEL_REPAIR`). Peringatan sampai ke AI lewat `warnings` hasil `run_python` (diteruskan apa adanya). Suite sandbox 843
lulus. Cek live: belum (berbayar, saldo).

**Hasil BE1-2 (2026-10-15, ter-deploy):** migrasi `20261015_011` diterapkan (DRYRUN `6ff1fb47`, APPLY `24184757`,
`mmig-job` dihapus), dibaca balik lewat pgweb, audit Feature Catalog lulus (148/148). **Koreksi premis:** cek seluruh
riwayat (2.268.015 baris) menemukan total beli ≠ total jual di 47.768 baris: sejak 2021 sama (4 pengecualian), tetapi
2016–2020 sekitar 7% baris papan Regular berbeda karena data sumber Broker Summary (ERRORS M157 baru; sampel lama 1 dari
89.933 hanya data sejak Juni 2026). Teks katalog menyebut keduanya: selisihnya nol atau celah data sumber, bukan
permintaan; akumulasi dibaca dari `positive_net_value_total`, `foreign_net_value`, `domestic_net_value`. Bukti
`verification/feature03/BUY_SELL_IDENTITY.md`; pelajaran Part A A3.15a. `Column_Catalog` tidak diubah langsung
(mengikuti Feature_Catalog lewat sinkronisasi).

**Keputusan user 2026-10-15:** "Ok, with solution 1, masukan exec jangan eksekusi dulu." dan "Ok, kita update saja kolom katalog untuk 2 kolom itu ya. --> masukan exec jangan update dulu." Dasar: log A/B V4/V5 (ERRORS M154, M155).
- **BE1-1 (solusi 1, sandbox): label hasil lebih toleran.** Ditanyakan user: "thresholds berbentuk list diubah otomatis jadi dict, dan satuan yang tidak dikenal dibuang dengan peringatan ... masuk juga pada solusi 1 ya?" — ya, itu isi solusi 1. Rencana: (a) `definition['thresholds']` berbentuk list diubah ke dict tanpa kehilangan isi (pasangan nama-nilai tetap, item lain diberi nama urut), dengan peringatan; (b) satuan di luar FRACTION/PERCENT/P_VALUE dibuang dengan peringatan, tidak ditebak (bukti: `DECIMAL` untuk kuantil 0,9 bukan persen); (c) yang tetap ditolak: kolom yang tidak ada, saringan dengan operator tak dikenal, kunci definisi tak dikenal. Pesan penolakan menyebut bentuk benar dan bahwa cukup label yang dikirim ulang (variabel sesi masih ada). Bagian "cek lebih awal" dari usulan nomor 3 dibatalkan (label baru ada di akhir skrip). Tes: list jadi dict, satuan tak dikenal jadi peringatan, kolom tak ada tetap gagal. Perkiraan hemat: satu putaran kode (10–25 dtk) per kejadian (2 dari 6 run A/B V5).
- **BE1-2 (M154 bagian a, katalog): deskripsi `total_buy_value` dan `total_sell_value` `Feature_03_Stock_Broker_Daily`.** Rencana: migrasi baru yang memperbarui `AI_column_catalog.description` (dan `description_id`), `Column_Catalog` dan `Feature_Catalog` (`misuse_warning`) kedua kolom: dijumlah atas semua broker per saham, tanggal dan papan, keduanya sama (setiap transaksi punya pembeli dan penjual), jadi selisihnya nol; untuk akumulasi pakai `positive_net_value_total` atau net per tipe investor. Bukti di catatan: pgweb 2026-10-15, 1 dari 89.933 baris berbeda. Status semantik tidak dinaikkan ke VERIFIED tanpa ulasan. Cek profil otomatis (M154 bagian b) tidak termasuk.

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

### EXEC-F04: otomatisasi Feature04 dan retry failure melalui Telegram

**Otorisasi 2026-10-11:** user: "Ok, jalankan." dan kemudian "Ok, kita akan jalankan. Baca semua MD, perubahan ini perlu dicatat dimana saja".

**Scope yang disetujui:** implementasi `feature-04-worker` baru; enqueue setelah perubahan harga; isolasi failure per ticker;
status/retry per indikator dengan dependency closure; menu Telegram untuk retry ticker/indikator yang benar-benar gagal;
pesan price harus terkirim sebelum hasil Feature04; dan pencatatan lengkap pada schema/catalog/changelog/Railway/docs/evidence.
NULL yang sah tidak dianggap failure. Retry Feature04 tidak menjalankan TradingView atau price cron.

**Urutan eksekusi:**

1. Audit seluruh Markdown, live schema, runtime service, dan migration yang relevan.
2. Tambahkan forward migration untuk queue, status kolom, attempt/run/member/retry/outbox, enqueue routines, trigger, catalog, dan grants.
3. Refactor engine agar dependency bundle dapat dihitung/divalidasi tanpa mengubah output v3 yang sudah tervalidasi.
4. Buat worker serial per ticker dengan lease, retry, generation race protection, partial bundle commit, dan monitoring/outbox.
5. Hubungkan price execution ID dan sealing batch; perluas Telegram trigger/monitor untuk status/retry dan urutan delivery.
6. Uji lokal, rehearsal migration, canary BBCA, apply live, deploy service secara terisolasi, lalu verifikasi exact deployment/data state.
7. Perbarui seluruh dokumentasi/evidence, hapus butir 13 dari `PLAN.md` setelah selesai, commit, push `main`, dan verify origin.

**Rollback:** hentikan worker/dispatcher dan retry enqueue; pertahankan durable queue/audit serta price cron. Jangan drop data
atau menghapus status failure. Kembalikan deployment aplikasi bila perlu, perbaiki, lalu replay pending work.

**Status:** COMPLETED 2026-10-11. Migration `20261011_005` committed after rollback rehearsal;
live readback found 7 control tables, 4 functions, one price trigger, 42,200 successful
baseline column states, and zero initial queue rows. Commit `4082626` was pushed to `main`;
worker, both price services, Telegram monitor, and Telegram trigger all deployed `SUCCESS`.
BBCA canary replayed 2,113 rows / 50 outputs with zero failure and zero payload change;
outbox and Telegram delivery reached `SENT`. Evidence: `verification/feature04/AUTOMATION.md`.

**Klarifikasi lanjutan:** user: "Termasuk NULL yang seharusnya sudah tersedia". Pemeriksaan
NULL diperluas dari candle terakhir ke semua bar hasil kalkulasi, termasuk lookback candlestick
dan availability state SMI/swing. NULL sah setelah reset OHLCV atau sebelum state tersedia
tetap dikecualikan. Kegagalan satu anggota menahan penulisan dependency bundle terkait.
Uji corruption pada bar historis dan pembacaan BBCA/RANS/PRDL dicatat pada bukti yang sama.
Suite terkait: 67 lulus. Perbaikan worker commit `557ef11` ter-deploy `SUCCESS` pada
`51838910-b0f0-4256-8f79-8c998ee28b9a`; formula version dan skema database tidak berubah.

### EXEC-F04-BONDS: perluasan Feature04 ke harga fixed income

**Otorisasi 2026-10-11:** user meminta OHLC dan metrik yang sama dari
`Price_Fixed_Income` untuk dimasukkan ke Feature04, menetapkan `asset_type`, melarang
hardcode ticker, dan menyetujui eksekusi dengan "Ok" setelah desain dikonfirmasi.

**Scope:** `asset_type=equity` hanya untuk membership `IDX_Stock_Universe`, dan
`asset_type=bonds` hanya untuk membership `Universe_Fixed_income`; bond source dibatasi
`metric_type='price'` dan `Timeframe='1D'`. Perluasan mencakup skema, worker, retry
ticker/kolom, katalog, backfill seluruh ticker eligible, serta Telegram tracking. Cron
fixed-income daily dan recovery tetap terpisah dari cron IDX; keduanya dihubungkan melalui
monitoring row dan durable outbox agar pesan harga fixed income terkirim sebelum pesan
Feature04.

**Urutan eksekusi:** rolled-back rehearsal; forward migration; rollback-only trigger
checks; deploy worker/monitor/trigger; enqueue backfill dari query universe; tunggu setiap
ticker terminal; validasi cakupan dan formula; perbarui schema/evidence/changelog; commit
dan push `main`. Ticker absent/ambigu dari universe harus fail closed. Tidak ada source
fetch, perubahan schedule, atau daftar ticker di kode.

**Status:** COMPLETED 2026-10-11. Migration `20261011_006` dan dokumentasi
`20261011_007` lulus rehearsal/rollback lalu diterapkan. Commit `b7b4471` membuat worker,
Telegram monitor, dan Telegram trigger mencapai deployment `SUCCESS`. Bootstrap
`f04-bonds-bootstrap-20261011` menyelesaikan 24/24 ticker, 60.409 bar, nol failure/partial,
dan notifikasi final `SENT`. Validasi menemukan nol key source hilang/ekstra pada equity
maupun bonds, nol salah klasifikasi, serta 56/56 definisi Feature04 aktif. Bukti:
`verification/feature04/BONDS.md` dan `cross_asset_validation.json`.

### EXEC-F04-RENAME-CLOSE: nama tabel governed dan close per trade_date

**Otorisasi 2026-10-11:** user meminta `feature04_technical_indicator` diganti menjadi
`Feature_04_Technical_Indicator`, seluruh script terkait diselaraskan, kolom `close`
ditambahkan berdasarkan `trade_date`, lalu meminta semua dokumentasi terkait diperbarui.
Nama operasional queue/monitor/function `Feature04_*` tetap karena nama itu adalah kontrol
workflow, bukan nama tabel hasil yang diminta untuk diganti.

**Scope:** forward migration tanpa mengubah migrasi yang sudah diterapkan; rename tabel dan
constraint/index terkait; backfill `close` dari sumber equity atau bonds yang ditentukan oleh
`asset_type`; pembaruan engine, worker, bounded pipeline/backfill, selectable retry columns,
status kolom, catalog, safe relationship, schema export, dokumentasi dan evidence. Formula
indikator dan calculation version v3 tetap. Script generator migrasi lama dan evidence lama
tetap menyebut nama lama sebagai audit history, bukan runtime aktif.

**Urutan eksekusi:** uji engine; inspeksi queue dan catalog live; rehearsal penuh dengan
ROLLBACK; apply migration dan readback nilai close terhadap kedua sumber; semantic audit;
deploy worker; canary satu equity dan satu bonds; refresh schema; catat evidence/changelog;
hapus runner sementara; commit dan push `main`; verifikasi deployment exact `SUCCESS` dan
branch sama dengan `origin/main`.

**Status:** COMPLETED 2026-10-11. Sebanyak 38 uji Feature04 dan 2 pemeriksaan migrasi
beku lulus. Migrasi 008/009 direhearsal dengan rollback lalu diterapkan; readback menemukan
1.379.042 baris, 57 kolom, 868 status `close` sukses, nol NULL/mismatch dan semantic audit
148/148. Commit `90e7244` mendeploy worker `3bf6c748-c429-41d2-97b1-c3cef69400aa`
`SUCCESS`. Canary equity `BBCA` dan bonds `ID01MY` sama-sama `SUCCESS` untuk 51/51 output,
nol failure, nol perubahan idempoten dan nol mismatch close. Runner sementara dihapus,
sandbox `DESTROYED`, config ditarik ulang, dan plan Railway menyatakan up to date. Bukti:
`verification/feature04/RENAME_CLOSE.md` dan `rename_close_validation.json`.

### EXEC-F04-FIXED-INCOME-FINALITY: market-specific closing jobs

**Otorisasi 2026-10-12:** user menyetujui desain pemisahan closing Indonesia/US
(`"Ok, setuju dengan design"`), meminta konfirmasi source Railway versus Git, lalu setelah
konfirmasi memberi go eksekusi: `"Ok, pls proceed."`

**Scope:** pindahkan source fixed-income updater ke Git; ticker/simbol/unit dibaca dari
`Universe_Fixed_income`; jam tutup dan timezone dibaca dari tabel konfigurasi; pisahkan
daily/recovery Indonesia dan US; simpan bukti final candle; recovery membaca ulang seluruh
latest completed session; hanya perubahan final `price`/`1D` yang memicu Feature04;
pertahankan urutan Telegram price lalu Feature04; lakukan re-query lima sesi terakhir,
canary kedua market, dokumentasi, migrasi, katalog, dan rekonsiliasi Railway.

**Status:** COMPLETED 2026-10-12. Migrasi `20261012_001` dan forward-only
`20261012_002` lulus rehearsal/rollback lalu diterapkan. Empat cron Git aktif untuk ID dan
US daily/recovery pada commit `7cc8d72`; semua exact deployment `SUCCESS`. Canary ID
22/22 dan US 26/26 lulus. Re-query 2026-10-05..09 menghasilkan 10/10 run `SUCCESS`, 240
seri final, nol missing; 24 ticker harga menyelesaikan Feature04, close cocok 120/120, dan
semua notifikasi price/Feature04 `SENT`. Recovery identik memverifikasi 26 seri dengan
`changed_series=0` dan Feature04 `SKIPPED`. Semantic audit 148/148 lulus, schema/IaC
disinkronkan, service/sandbox sementara dihapus, dan Railway plan up to date. Bukti:
`verification/feature04/FIXED_INCOME_FINALITY.md`.

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

### EXEC-F04-INCREMENTAL-FINALITY: exact checkpoint suffix dan recovery lima sesi

**Otorisasi 2026-10-12:** setelah menyetujui implementation plan, user memberi perintah eksekusi: `"Ok jalankan."`

**Scope:** finality evidence equity; recovery berbasis konfigurasi untuk lima completed market sessions pada IDX, ID bonds, dan US bonds; state checkpoint versioned per ticker; normal worker menghitung hanya suffix dari earliest changed session sampai latest; tidak ada fallback full-history otomatis; explicit bootstrap membangun state dan shadow-compare seluruh indikator; retry ticker/kolom mempertahankan dirty range; migrasi, katalog, dokumentasi, Railway IaC, tests, live readback, commit, dan push `main`.

**Urutan eksekusi:** implementasi dan local parity; rolled-back migration rehearsal; pause worker; apply migration; bootstrap/shadow checkpoints; deploy price producers dan worker; controlled canary correction/identity; verify exact deployments dan live data; refresh evidence/schema/changelog; commit dan push `main`.

**Status:** COMPLETED 2026-10-12. Migration rehearsal/apply passed; 868/868 full shadows
matched; 6,076 checkpoints were bootstrapped; the live worker processed exactly five rows
for 868/868 instruments with zero failures; an identical rerun changed zero rows. Final
worker deployment is `c6abb05e-4341-4b6f-a060-2ef8962238d9`; evidence is under
`verification/feature04/INCREMENTAL_FINALITY.md`.

### EXEC-F04-TELEGRAM-MONITOR: one daily result and failure-only bounded retry

**Otorisasi 2026-10-12:** user narrowed the issue to the Feature04 monitor and requested:
`"kalau feature 4 sudah selesai di calculate, berapa yang sukses, berapa yang gagal"`,
with a failed ticker/indicator recalculation option over the latest five days. After the
design and existing final-candle behavior were confirmed, user authorized execution with
`"Okay gas."`

**Scope:** Feature04-only Telegram changes. Scheduled DAILY and RECOVERY for the same
market/trade date update one compact final message containing eligible, success, failed, and
blocked counts. Failure details are capped at ten and link to `/feature04`. Ticker/column
retry remains failure-only, derives the latest five final sessions from market policy, uses
the preceding checkpoint, and edits its acknowledgement on completion. The price Telegram
flow, price cron schedules, formulas, and Railway topology stay unchanged.

**Status:** COMPLETED 2026-10-12. Migrations `20261012_004` and `20261012_005` passed
rollback rehearsal, apply, and live readback; 68 relevant tests passed. Commit `35fee3f`
deployed exact `SUCCESS` versions of worker (`cc083003-…`), monitor (`bbdef14e-…`), and
trigger (`621f630c-…`). The temporary runner was deleted with no volume, and no permanent
service or schedule was added. Evidence: `verification/feature04/TELEGRAM_MONITOR.md`.

### EXEC-JOINKEY: kunci gabungan hanya entitas, kolom tanggal tidak ikut (G25)

**Keputusan user 2026-10-12:** "kuncingabungan hanya entitas, kolom tanggal tidak ikut —> yes pls fix sesuai
rekomendasimu masukan exec". Status: **selesai** (Fase 1 `597b77f` SUCCESS, lulus Run A; label diperbarui 2026-10-13 dari bukti yang sudah tercatat). Bukti: run `edge_87c8c408…-m4n` (2026-10-09 10:24, orc
`540227e6`), ERRORS G25.
- **Masalah:** bagian RELATIONSHIPS katalog menampilkan relasi #23 dengan `left_columns`/`right_columns`
  `[ticker, date]` dan `join_rule` "left_columns[i] joins right_columns[i]", sedangkan `submit_data_need_spec` (v2,
  `AI_ENABLE_COMPOSITE_KEYS=true`) meminta pasangan kunci entitas **tanpa** kolom waktu (deskripsi field). Model menyalin
  katalog; validator sandbox menolak `RELATIONSHIP_KEY_MISMATCH` dengan `rejected_value` saja, tanpa nilai yang benar.
- **Perbaikan 1 (sandbox, `app/data_need.py`):** isu `RELATIONSHIP_KEY_MISMATCH` pada pasangan kunci membawa
  `expected_value` (contoh `"ticker = ticker"`) dan satu kalimat sebab (kolom waktu diterapkan oleh `join_semantics`,
  bukan kunci). `Issues.add` menerima `expected` opsional; kode isu dan aturan validasi tidak berubah.
- **Perbaikan 2 (orc, `app/tools/catalog.py`):** tiap entri RELATIONSHIPS mendapat `request_key_columns`
  (`left`/`right`: pasangan kunci tanpa pasangan waktu, dihitung dengan aturan yang sama dengan validator) dan
  `join_rule` menyebut bahwa data need memakai `request_key_columns`, sedangkan waktu dipasangkan lewat
  `left_time_column`/`right_time_column`. Kolom katalog asli tetap ditampilkan.
- **Perbaikan 3 (sandbox, keputusan user 2026-10-12: "1. Ok masukan exec"):** bila pasangan kunci yang diminta
  sama dengan pasangan katalog **ditambah persis** pasangan kolom waktu katalog, dan `join_semantics` EXACT_DATE atau
  AS_OF, validator menerima dan mencatat peringatan `RELATIONSHIP_TIME_KEY_DROPPED`; semantik lain tetap ditolak
  dengan `expected_value`. Aman: kontrak yang disetujui memakai pasangan dari katalog (`b.pairs` di
  `approved_contract`), jadi hash kontrak tidak berubah dan Governor (`extract.py`, cek yang sama) menerima kontrak.
- **Aturan lama yang diubah:** README sandbox, docstring `tools/data_need.py` dan deskripsi alat
  `submit_data_need_spec` menulis "never suggests a replacement" (fase 1 DataNeed, 2026-09-25). Diubah menjadi:
  validator tidak pernah memilihkan data lain (tabel, cakupan, periode), tetapi menyebut bentuk yang sudah pasti dari
  katalog. Deskripsi alat berubah, jadi versi baru di Tool_Catalog lewat
  `scripts/generate_tool_catalog_migration.py` (ronde R) dan `AI_TOOLS.md` diregenerasi.
- **Tes:** sandbox: relasi dengan kolom waktu di kunci ditolak dengan `expected_value` yang benar (semantik selain
  EXACT_DATE/AS_OF), diterima dengan peringatan untuk EXACT_DATE/AS_OF dan kontraknya identik dengan permintaan
  tanpa kolom waktu, relasi yang benar tetap lolos; orc: `request_key_columns` sama dengan hasil fungsi validator untuk semua relasi fixture (satu fungsi
  bersama atau tes kontrak, aturan M68); suite orc dan sandbox lengkap.
- **Dokumen:** `AI_TOOLS.md` bila deskripsi alat berubah; README orc (Catalog discovery) dan sandbox; ERRORS G25.
- **Deploy dan cek live:** sandbox dan orc (setelah konfirmasi push); satu run dev yang menggabungkan harga dengan
  broker: data need lolos pada revisi pertama tanpa `RELATIONSHIP_KEY_MISMATCH`.

### EXEC-RELEASE: hasil baru sah setelah analisis ditutup (M139 sisa)

**Keputusan user 2026-10-12:** "hasil baru sah setelah analisis ditutup —> yes pls fix seusai rekomendasi mu masukan
exec". Status: **selesai** (Fase 1 `597b77f` SUCCESS, lulus Run A; label diperbarui 2026-10-13 dari bukti yang sudah tercatat).
- **Sudah ada (EXEC-Z, deploy `977b525`, 2026-10-09):** `run_python` yang gagal menaruh tabelnya di
  `discarded_outputs` dengan catatan bahwa `complete_analysis` tidak akan merilisnya.
- **Sisa yang diperbaiki:** panduan metode (`app/method_guides.py`, identik di orc dan sandbox, v7) masih menulis
  "label NOT_RELEASED until complete_analysis releases it" tanpa membedakan eksekusi gagal. Kalimat ini sama dengan
  anggapan model di run `edge_87c8c408…` ("not released until completion"). Ubah menjadi: tabel dari eksekusi yang
  berhasil berlabel NOT_RELEASED sampai `complete_analysis`; tabel dari eksekusi yang gagal dibuang dan tidak pernah
  dirilis, harus di-emit ulang di eksekusi yang berhasil.
- **Versi panduan:** `GUIDES_VERSION` 8, kedua salinan file identik, migrasi `AI_method_guide` v8 (pola
  `20261009_005_ai_method_guides_v7.sql`), sandbox dan orc di-deploy bersama karena hash panduan harus sama.
- **Deskripsi alat `run_python` (`tools/session.py`):** kalimat "label NOT_RELEASED until released" dan hasil
  SCRIPT_ERROR ditambah: tabel dari eksekusi yang gagal dibuang dan tidak pernah dirilis, emit ulang di eksekusi yang
  berhasil. Versi baru Tool_Catalog di ronde R yang sama dengan EXEC-JOINKEY.
- **Tes:** tes identik dua salinan dan hash; tes sandbox M139 yang ada tetap lulus; tes drift Tool_Catalog;
  `AI_TOOLS.md` diregenerasi.
- **Cek live (sekaligus cek live M139 yang tertunda):** satu run dev dengan eksekusi kode yang gagal setelah emit tabel:
  model membuat ulang tabel di eksekusi berikutnya sebelum `complete_analysis`, tanpa putaran tambahan.

### EXEC-FRICTION: hambatan proses tampil di EDGE dari data backend (P0, M142)

**Keputusan user 2026-10-12:** "P0 oke, masukan exec". Status: **selesai** (Fase 2 `cbe1860` SUCCESS, lulus Run A; label diperbarui 2026-10-13 dari bukti yang sudah tercatat). Bukti: run `edge_01fccf…-m4q` (M142):
laporan diri AI menambah dua hambatan yang tidak terjadi dan melewatkan empat penolakan gerbang yang terjadi.
- **Tujuan:** pengguna melihat hambatan sebuah jawaban dari catatan backend, bukan dari cerita AI.
- **Orc:** `execution` mendapat `hurdles` (dihilangkan bila kosong): daftar hambatan run ini, satu butir per penolakan
  alat atau gerbang yang sudah dicatat run memory (langkah, jenis, kode, kalimat bahasa Indonesia dari
  `app/user_texts.py`, diperbaiki atau tidak). Mode 4 menggabungkan butir semua langkah. `friction` tetap.
- **Temuan infra (2026-10-12) yang ikut diperbaiki:** buku penolakan run memory (`_remember_tool_refusal`) tidak
  mencatat status `REVISION_REQUIRED` (penolakan data need, termasuk `RELATIONSHIP_KEY_MISMATCH` 9 Okt: memo backend
  run `edge_87c8c408…` mencatat 3 penolakan, TYPED_FIGURES dan SCRIPT_ERROR ×2), sedangkan `friction`
  (`tools/envelope.py`) menghitung `REVISION_REQUIRED` tetapi tidak `SCRIPT_ERROR`. Satu pengelompok status untuk
  keduanya; `hurdles`, memo dan `friction` membaca catatan yang sama.
- **EDGE:** bagian "Hambatan proses" di panel Detail (bentuk di `static/edge-view.js`, kata di `static/edge-labels.js`,
  tampilan di `static/index.html`); kosong berarti tidak tampil.
- **Tes:** orc: run dengan penolakan alat dan gerbang menghasilkan `hurdles` yang sama dengan memo run; EDGE:
  `test_orc_contract.py` dengan keluaran orc asli (aturan M68), `test_answer_view.py`, `test_visual.py`.
- **Dokumen:** README orc (API contract) dan EDGE; `tests/fixtures/orc_responses.json` diperbarui dari orc asli.
- **Deploy dan cek live:** orc lalu EDGE; satu percakapan dev dengan penolakan nyata tampil di Detail, sama dengan log.

### EXEC-STYLE: jawaban natural, struktur mengikuti jenis pertanyaan

**Keputusan user 2026-10-12:** "Ok, yang adopsi dan sebagian --> masukan EXEC." dan "A/B test hanya sebagian saja 4
pertanyaan maksimal --> masukan exec". Konsekuensi diterima: "snapshot system prompt baru, batas ukuran prompt +2% harus
dicek, dan cache prompt di-reset sekali. --> tidak apa." Tabel tetap seperti sekarang ("hanya terkait table tidak apa
leave as is"). Status: **selesai**, gaya Run A (`main` `f30e710`, orc `dbc11d42` SUCCESS; label diperbarui 2026-10-13 dari bukti yang sudah tercatat). Bukti: run `edge_01fccf…` (reasoning "Also add assumptions/limitations"; tabel
6 baris untuk pertanyaan obrolan), 11 dari 13 run percakapan `conv_9d6092c4…` mencatat `ai_answer_long`; benchmark
eksternal (Anthropic prompting best practices, OpenAI GPT-5.1/5.2 prompting guides dan Model Spec, Tam dkk. EMNLP 2024).
- **S1 struktur per jenis (adopsi):** di `WRITING FOR THE READER` (`orchestrator.py`) urutan kesimpulan → angka →
  arti → catatan hanya untuk jawaban yang melaporkan hasil analisis. Catatan langkah router (`conversation_router.py`
  `NOTES`: CONVERSATIONAL, CLARIFY; catatan FACT router pesan pertama) mendapat satu kalimat gaya: jawab seperti
  percakapan, prosa singkat, tanpa judul dan huruf tebal. Catatan langkah ada di luar awalan prompt yang di-cache.
  Bagian tebal mode 4 penuh (**Jawaban/Hasil riset/Usulan**, `mode4.py`) tetap.
- **S2 contoh beragam (adopsi):** `READER_EXAMPLE` (satu contoh dengan pembuka tebal) diganti tiga contoh pendek:
  obrolan, fakta, hasil analisis yang belum meyakinkan; tanpa huruf tebal; tanpa digit baru (tes pass 2); instruksi
  ditulis positif ("tulis paragraf yang mengalir").
- **S3 asumsi/batasan bila material (sebagian):** aturan 14 dan kontrak jawaban: daftar asumsi dan batasan kosong
  kecuali mengubah seberapa jauh jawaban bisa dipercaya. Skema tidak berubah; yang diwajibkan kode tetap (LIMITATION
  minimal satu batasan, batas konteks, baris jalur analisis, asumsi fakta web, anotasi klaim P17, metodologi).
  EDGE: Asumsi dan Batasan tampil terlipat di bawah jawaban dengan jumlahnya (`index.html`, kata di
  `edge-labels.js`).
- **S4 panjang bertingkat (adopsi):** aturan 13 dalam kata-kata (tes pass 2 melarang digit baru): obrolan beberapa
  kalimat, fakta satu paragraf, hasil analisis sekitar dua setengah ribu karakter; aturan tabel sepuluh baris tetap.
  `ai_answer_long` mencatat target per jenis langkah (`current_answer_target`).
- **S5 prosa di bagian pembaca (sebagian):** hanya `WRITING FOR THE READER` ditulis sebagai prosa; aturan alat dan
  gerbang tetap berupa daftar.
- **Tidak diadopsi:** parameter `verbosity` (tidak ada endpoint DeepSeek di OpenRouter yang mendukungnya; dengan
  `require_parameters: true` semua penyedia gugur, dicek dari API endpoint OpenRouter 2026-10-12); melepas skema JSON
  ketat (gerbang membaca field jawaban); "tawarkan detail" di teks (sudah lewat `follow_ups`).
- **Dokumen dan tes:** `scripts/snapshot_system_prompt.py record` (keputusan dan perubahan di atas),
  `tests/test_prompt_history.py`, `tests/test_prompt_pass2.py` (`SIZE_BUDGET` diukur dulu; dinaikkan bila perlu, sudah
  disetujui), `AI_ROUTER.md` diregenerasi (catatan langkah berubah, kriteria rute tidak, jadi benchmark router tidak
  wajib), README orc (Answer length).
- **A/B (maksimal 4 pertanyaan):** pertanyaan yang sama sebelum (A) dan sesudah (B) deploy gaya, lewat
  `orc-test-runner`. Ukuran: panjang terhadap tingkatnya, jawaban dengan asumsi/batasan tidak kosong, pembuka tebal,
  penolakan gerbang (tidak boleh naik), penilaian natural oleh user.

**Keputusan user sesudah A/B (2026-10-12):** "well saya lebih suka Run A tapi tanpa kewajiban AI untuk kasih asumsi,
batasan. Also table is a good thing." lalu "We'll go with option A deh, tapi tanpa kewajiban AI harus kash asumsi,
batasan saat reply ke useer. Tabel juga boleh lebih dari 1 tabel as long as diperlukan." Atas usulan: baris yang ditulis
sistem "OK terlipat, masukan exec"; kalimat tabel "tidak usah, pakai metode existing di A + dalam 1 jawaban boleh lebih
dari 1 tabel as long as membantu user. (tidak wajib harus lebih dari 1)". Yang dijalankan:
- Kembali ke Run A: bagian WRITING FOR THE READER, contoh jawaban dan satu target panjang (sekitar 2.500 karakter)
  seperti sebelum A/B; catatan gaya router dan target per jenis langkah dihapus (S1, S2, S4 dibatalkan).
- Tetap dari S3: aturan 14 dan kontrak jawaban: asumsi atau batasan hanya bila mengubah cara membaca jawaban atau
  seberapa jauh jawaban bisa dipercaya; tidak ada kewajiban mengisinya.
- Baris yang ditulis sistem (pilihan AI, pencarian web, baris jalur analisis) tetap ada, tampil terlipat di EDGE dengan
  jumlahnya.
- Aturan 13: setiap tabel maksimal sepuluh baris; satu jawaban boleh memuat lebih dari satu tabel bila membantu
  pembaca (tidak wajib).
- Snapshot prompt `v005 exec-style-run-a` (prompt +0,5% dari Run A). Run C tidak dijalankan (belum diminta).

### EXEC-EXPORT: ekspor Excel belum jalan (diperbaiki)

**Permintaan user 2026-10-12:** "Saat ini feature export excel masih belum works. Investigate --> masukan exec".
Status: **diperbaiki dan ter-deploy** (`main` `e0cf486`, edge-bff `f069c6a7` SUCCESS; label diperbarui 2026-10-13 dari bukti yang sudah tercatat). Temuan investigasi awal:
- orc menyalakan ekspor saat start (`result_store_active`, tanpa `export_inactive`); alat `export_result` ditawarkan.
- Log orc 9–12 Oktober: hanya satu run yang memanggil `export_result` (`edge_4a0c52b6…`, 9 Oktober, COMPLETED, cek live
  EXEC-Y). Tidak ada permintaan Excel lain yang gagal di orc pada periode itu.
- EDGE tidak mencatat log akses HTTP, jadi klik unduh (`/api/v1/exports/{id}` → orc `/v1/exports/{id}/download`) tidak
  bisa ditelusuri dari log; kegagalan unduh tidak terlihat.
- Butuh dari user: contoh yang gagal (ID `edge_…` atau waktu dan pertanyaannya) dan gejalanya (tombol unduh tidak muncul,
  klik gagal, atau file rusak). Alternatif: satu uji live lewat `orc-test-runner` (minta Excel lalu unduh lewat orc),
  perkiraan biaya di bawah USD 0,05, dengan izin user.
- **Akar masalah (2026-10-12, user: "lihat edge_ddb3367765be54339bd3408fec055423"):** file Excel dibuat dengan benar
  dan bisa diunduh dari orc (probe read-only: HTTP 200, sha256 cocok, XLSX valid). Tombol "Download" di EDGE mengubah
  `/api/v1/exports/exp_…` menjadi rute halaman `#/api/v1/exports/exp_…`, jadi klik tidak pernah meminta file
  (direproduksi di Chromium). Usulan perbaikan: tautan `/api/` tidak diubah; tes browser mengklik Download dan
  menerima file. Menunggu konfirmasi (`ERRORS_AND_SOLUTIONS.md`, EDGE download and typing).
- **Go 2026-10-12:** "2 dan 3 OK untuk jalankan masukan EXEC". Dibangun: tautan yang diawali `/api/` tidak lagi diubah
  menjadi rute halaman, di dua tempat (`applyProps` dan penyesuaian tautan sesudah `refresh`). Tes browser
  `test_download_link_requests_the_exported_file` mengklik Download dan menerima file (gagal pada kode lama).

### EXEC-TYPING: mengetik di kotak pesan EDGE tersendat

**Laporan user 2026-10-12:** "ada bug di front end dimana saya tidak bisa typing, atau hanya bisa typing 1 huruf per 1
huruf." Status: **diperbaiki dan ter-deploy** (`main` `e0cf486`, edge-bff `f069c6a7` SUCCESS; label diperbarui 2026-10-13 dari bukti yang sudah tercatat).
Temuan investigasi awal: Setiap huruf membuat EDGE
menggambar ulang seluruh halaman (semua jawaban dan tabel): sekitar 17 ms per huruf di halaman kosong, 76–211 ms
dengan 15 jawaban dan 45 tabel (diukur di Chromium). Fokus tidak hilang di semua skenario yang dicoba. Usulan: mengetik
hanya memperbarui kotak pesan, dan jawaban yang sudah tampil tidak digambar ulang.
- **Go 2026-10-12:** "2 dan 3 OK untuk jalankan masukan EXEC". Saat membangun, penyebab utama ditemukan dan
  direproduksi: penggambaran ulang yang terjadi **saat jawaban sedang diproses atau baru tiba** memindahkan kotak pesan
  di halaman, dan elemen yang dipindah kehilangan fokus, jadi huruf berikutnya hilang (kode lama: dari "halo dunia apa
  kabar lagi" hanya "a" atau "h" yang masuk). Dibangun: (1) sesudah setiap penggambaran ulang, elemen yang tadinya fokus
  mendapat fokus kembali beserta posisi kursornya; (2) mengetik hanya menyimpan teks, halaman digambar ulang hanya saat
  kotak berubah kosong/berisi (tombol Submit), dan Enter mengirim teks terakhir. Tes browser:
  `test_typing_while_an_answer_arrives_keeps_focus`, `test_typing_does_not_redraw_the_page` (keduanya gagal pada kode
  lama). Tes EDGE: 65 lulus.

### EXEC-SORT: tabel di jawaban bisa diurutkan dengan klik judul kolom

**Permintaan user 2026-10-12:** "Untuk tabel, bisa saya minta fitur sortable kalau klik header? Konfirmasi."
Status: **selesai** (`main` `00f808f`, edge-bff `9db6483d` SUCCESS; label diperbarui 2026-10-13 dari bukti yang sudah tercatat). Riwayat: review prototipe (user: "boleh kasih saya standalone HTML dulu untuk direview?"; prototipe HTML
mandiri dikirim 2026-10-12, di luar repo). Usulan:
- Hanya di EDGE (browser): tabel Markdown di jawaban (`renderMarkdown` → `data-table`). Backend, angka dan jawaban AI
  tidak berubah.
- Klik judul kolom: naik → turun → urutan asli; tanda panah di judul; `aria-sort`; bisa dengan keyboard.
- Angka dibaca format Indonesia: "1.975,4", "−466,3", "2,87%", "Rp 79,42 miliar", "349 juta" (kata skala), tanggal;
  sel kosong selalu di bawah; teks diurutkan menurut abjad bahasa Indonesia.
- Baris total (sel pertama "Total"/"Jumlah") tetap di bawah.
- Tes: kontrak frontend dan uji visual EDGE; deploy edge-bff saja.

**Keputusan user 2026-10-12 (sesudah prototipe):** "untuk design sekarang (yang live) sudah OK, jangan dirubah lagi, hanya
tambahkan opsi untuk sort seperti terlampir. Tampilan pakai existing (hanya sortable feature dan display icon seperti
pada screenshot) .. masukan EXEC". Spesifikasi yang dibaca dari screenshot (menunggu konfirmasi pemahaman):
- Tampilan tabel tetap seperti yang live (warna, huruf, judul kolom); prototipe hanya acuan perilaku, bukan tampilan.
- Judul kolom yang disorot mouse: latar judul sedikit lebih gelap dan ikon ⇅ di kanan nama kolom.
- Klik pertama: urut turun, ikon ↓; klik kedua: urut naik, ikon ↑; ikon arah tetap tampil di kolom yang aktif, kolom
  lain tanpa ikon. Klik ketiga: kembali ke urutan asli (dikonfirmasi user: "A. correct").
- Tanpa menu ⋮ di atas tabel (ada di screenshot, tidak diminta).
- Cara membaca angka, sel kosong di bawah, baris Total tetap di bawah dan keyboard seperti di prototipe.

### EXEC-UI-1012: panel kiri, bagian yang bisa dilipat, judul ringkas (dokumen user)

**Permintaan user 2026-10-12** (dokumen "By default dibuka saja saat ini kebanyakan masih ditutup.docx", masing-masing
"masukan EXEC, clarify if needed"). Status: **selesai** untuk B1 dan C (`main` `00f808f` SUCCESS), B2 tetap ("leave
as is"); label diperbarui 2026-10-13 dari bukti yang sudah tercatat.
1. "By default panel kiri boleh bisa dibuka saja instead of ditutup" (screenshot: daftar percakapan di panel kiri; hanya
   percakapan yang dipilih menampilkan dua baris, judul dan cuplikan, yang lain satu baris).
2. "Asumsi, batasan, metodologi bisa dibuat bisa ditutup saja? Sama seperti detail backend ... Font size, font colour
   keep as is, Cuma tambahkan segitiga ke kiri ... to allow collapse and expanse section." (screenshot: "▼ Detail
   backend" terbuka dan "▶ Detail backend" tertutup). Judul dokumen: bagian seperti ini terbuka saat pertama tampil.
3. "title panel kiri boleh dibedakan, tidak perlu 1:1 exactly seperti pertanyaa user. AI router bisa rephrase. Dan ini
   nanti akan ke affect ke 2 bagian yang saya tandai" (screenshot: judul di panel kiri dan judul besar di atas jawaban;
   contoh "kasih saya data BBCA harga…" menjadi "BBCA Share Price" atau "BBCA Price").

**Jawaban user atas klarifikasi (2026-10-12):** "B1. (i)" (setiap percakapan di panel kiri menampilkan dua baris: judul
dan cuplikan pertanyaan, bukan hanya yang dipilih); "B2. leave as is, konsisi sekarang sudah benar" (Asumsi/Batasan
terlipat dengan jumlahnya tetap seperti sekarang; tidak ada perubahan); "C. sesuai bahasa penanya dan only first
question" (judul ringkas dalam bahasa penanya, hanya untuk pertanyaan pertama percakapan). Usulan implementasi:
- B1: daftar percakapan EDGE (`list_conversations`) ikut membawa pertanyaan terakhir tiap percakapan dari tabel job
  EDGE (tanpa perubahan skema); baris kedua yang sudah ada tampil untuk setiap item.
- C: router pesan pertama orc menambah satu field `title` (dua sampai lima kata, bahasa penanya); EDGE memakainya
  sebagai judul percakapan dan judul besar jawaban pertama; tanpa judul router (router gagal atau jalur dipilih
  pemanggil) tetap 80 karakter pertama pertanyaan. Bubble "YOU" tetap kata-kata user; percakapan lama tidak berubah.
  `AI_ROUTER.md` diregenerasi; kriteria rute tidak berubah.

### EXEC-DELETE: hapus percakapan dari panel kiri

**Permintaan user 2026-10-12:** "saya juga minta opsi untuk delete conversation ya, tombol tong sampah disebelah
bookmarked left panel on every chat". Status: **selesai** (`main` `00f808f`, orc `d608732c`, edge-bff `9db6483d` SUCCESS; label diperbarui 2026-10-13 dari bukti yang sudah tercatat). Kondisi sebelum perubahan: orc hanya menghapus
percakapan otomatis 30 hari sesudah aktivitas terakhir (`AI_CONVERSATION_RETENTION_DAYS`, default); belum ada hapus
manual. Usulan:
- UI: ikon tong sampah di sebelah bookmark pada setiap percakapan; dialog konfirmasi sebelum menghapus; tidak tersedia
  selagi percakapan masih berjalan.
- orc: endpoint baru hapus satu percakapan milik owner (giliran, tabel hasil, file ekspor ikut terhapus lewat cascade;
  objek bucket dihapus dulu, sama seperti pembersihan retensi). EDGE: endpoint yang memanggil orc lalu menghapus baris
  `edge_bff.conversation_ui` dan job percakapan itu.
- Catatan audit (`AI_research_run_audit`, market-audit-store) tetap (jejak audit), kecuali user memutuskan lain.

**Keputusan user 2026-10-12:** "1 pakai B hanya smebunyikan di front end tapi backend bisa akses if needed", "2 Ok"
(dialog konfirmasi), "3 Ok" (catatan audit tetap). Dibangun: tombol tong sampah di sebelah bookmark (nonaktif selagi
percakapan berjalan), dialog "Delete conversation?", `DELETE /api/v1/conversations/{id}` mengisi
`edge_bff.conversation_ui.hidden_at` (migrasi `20261012_008`, diterapkan di dev dan dibaca balik) dan menolak percakapan
yang masih berjalan (409); orc tidak diubah dan tetap menyimpan percakapan sesuai retensinya (30 hari sesudah aktivitas
terakhir). Bersama itu dibangun EXEC-SORT (`MdTable`), B1 (`last_message`) dan C (`title` router pesan pertama, dipakai
EDGE hanya untuk pertanyaan pertama; judul yang diubah user tidak ditimpa). Tes: orc 1.634, EDGE 70 lulus.
- Deploy `main` `00f808f` (2026-10-12): orc `d608732c` dan edge-bff `9db6483d` SUCCESS. Cek live judul: "tolong jelaskan
  singkat apa itu indikator RSI untuk saham" → judul "Penjelasan Indikator RSI" (rute FACT). Temuan baru M144 (gerbang
  ROUTING memaksa LIMITATION pada jawaban definisi RSI; sudah ada sebelumnya, menunggu keputusan user).

### EXEC-DETAILS: panel Details di EDGE (geser batas, lipat bagian) dan M144

**Permintaan user 2026-10-12:** "M144 Ok masukan exec"; "2. also boleh untuk pinned response dan response history yang
saya kuningij kalau di press then bisadrag atas bawah bawah"; "3. minta juga opsi untuk collapse dan expand pinned
response dan response history"; "1-3 tolong setelah perubahan ini applied, cek vidually dan interactionally to ensure
well carried". Dibangun:
- Garis antara Pinned responses dan Response History bisa ditekan dan digeser ke atas/bawah (sentuh, mouse, atau
  tombol panah); tingginya disimpan di browser ini. Judul kedua bagian bisa dilipat/dibuka (chevron, `aria-expanded`);
  bila keduanya terlipat, kedua judul tetap berdampingan di atas.
- M144: gerbang ROUTING tidak meminta analisis pada langkah FACT, CLARIFY dan CONVERSATIONAL; teks hambatan "(routing)"
  menjadi kata biasa.
- Cek visual dan interaksi (Chromium, desktop 1440 dan ponsel 390 dengan layar sentuh): geser dengan mouse dan jari,
  bertahan sesudah muat ulang, lipat/buka, tanpa geser horizontal. Tes: EDGE 72, orc 1.635 lulus.
- Butir 1 (tampilan ponsel saat scroll ke bawah): belum bisa direproduksi berbeda di emulator; menunggu penjelasan
  user tentang bagian yang salah.
- Deploy `main` `2a74fc4`: orc `dc757f0b` dan edge-bff `23a9d7f4` SUCCESS. Galeri bentuk output jawaban (permintaan
  user: "separate html on how those looks like currently") dikirim sebagai file terpisah, dirender dari EDGE yang live.

### EXEC-DURATION: lama proses tiap run di EDGE

**Permintaan user 2026-10-12:** "tolong tambahkan berapa lama each run_id progress, tampilkan di edge sebelah tokens/
reported cost dan dibagian response history". Dibangun: lama proses dari `execution.duration_ms` orc (cadangan: waktu
mulai-selesai yang tersimpan) tampil sebagai "⏱ 6m 36s" di baris metadata jawaban (sesudah tokens) dan di baris Response
History ("… · completed · 6m 36s"); run yang masih berjalan tidak diberi durasi. Tes `test_each_answer_shows_how_long_it_took`;
EDGE 73 lulus. Status: **ter-deploy** (`main` `cc0dd74`, edge-bff `04aacf39` SUCCESS; label diperbarui 2026-10-13 dari bukti yang sudah tercatat).

**Investigasi 2026-10-12 ("ini kenapa research failed", "pertanyaan tersebut took almost 8 minutes, kepentok dimana"):**
- Gagal: `edge_e0ee24d0…` berakhir INTERNAL_ERROR karena `RemoteProtocolError` dari panggilan model yang tidak diulang
  (M145, usulan perbaikan menunggu keputusan user).
- Lama: run terpanjang `edge_517a29…` 6m 36s di orc: panggilan model pertama 161 s (menalar 14 ribu token untuk
  merencanakan permintaan data), data dan Python beberapa detik sampai sekitar 30 s, menulis jawaban sekitar 3 menit
  (tiga cek rujukan 11 s, 54 s, 59 s, satu draf ditolak gerbang PROVENANCE lalu dua panggilan perbaikan 35 s).
  `edge_3511fb…` 5m 48s: pola sama (perencanaan 97 s, penulisan dan cek rujukan sekitar 3 menit).

### EXEC-M146-M147: panggilan alat tertulis sebagai teks; jumlah tanggal di profil data (ter-deploy)

**Keputusan user 2026-10-13:** "fix M146c rencanakan terlebih dahulu", lalu "selidiki 147, cek kode", lalu "Ok go".
- **M146.** deepseek-v4.1-flash sesekali menulis panggilan alat dalam markup DSML sebagai teks; provider meneruskannya
  tanpa panggilan alat (laporan publik: sglang #40236, openclaw #159665, DeepSeek-V3 #1244, command-code #909). Terjadi
  2 dari sekitar 200 panggilan hari ini, sekali ON dan sekali OFF.
  - Orc dulu menganggapnya jawaban rusak, sehingga run berakhir LIMITATION tanpa data.
  - Sekarang giliran itu diminta ulang dengan alat yang sama (paling banyak 2 kali, log `ai_tool_markup_retried`,
    hambatan "panggilan alat tertulis sebagai teks"). Markup tidak pernah dieksekusi.
  - Tes `test_tool_markup.py`.
- **M147.** Profil dataset di sandbox menghitung nilai unik dengan perkiraan HyperLogLog. Direproduksi dengan DuckDB 1.5.5:
  19 tanggal terbaca 21, 32 terbaca 35, 180 terbaca 228.
  - Kolom tanggal sekarang dihitung pasti; kolom lain tetap perkiraan.
  - Tes `test_profile_distinct.py`.
  - Suite sandbox: kegagalan sama persis sebelum dan sesudah perubahan (196 tes isolasi yang butuh slot user, tidak
    bisa jalan di container ini).
- Tes: orc 1.662 lulus. Tidak ada perubahan prompt, database atau variabel.
- Deploy `main` `e6745a4`: orc `23a4aeea` dan sandbox `d56ead43` SUCCESS, `/ready` 200.
- Cek live `ma-m147-20261013a` (pertanyaan ab5, USD 0,038, 249 s, COMPLETED):
  - Sesudah sesi dibuka, AI langsung menulis "Flow data: 19 trading dates … Price: 29 dates including buffer",
    tanpa pemeriksaan ulang 21 vs 19. **M147 FIXED.**
  - M146 tidak muncul di run ini (tidak bisa dipicu dengan sengaja); menunggu log `ai_tool_markup_retried` di pemakaian
    berikutnya.
  - Catatan: satu TYPED_FIGURES "19" lagi (jumlah hari bursa diketik), pola yang sama dengan cek live M143.

### EXEC-FASTLANE: jalur riset baru "eksplorasi di sandbox" untuk A/B (rencana, belum dieksekusi)

**Keputusan user 2026-10-13:** "Jangan sampai merubah cara research bekerja. Retain existing condition, kita buat jalur
baru saja untuk nanti A/B test. Saya suka idenya. Lets catat dulu." Latar: run 7, 9, 10, 12, 13 conversation
`conv_99ccd2429f766946eb2cdc42ac98af6b` makan 3–9 menit per giliran; waktu terbesar di pikiran AI (memilih jalur riset,
menebak ukuran data dan batas 64 bagian, mengisi formulir rencana, dua giliran rencana lalu eksekusi), bukan di gerbang
(sekitar 10%).
- **Jalur sekarang tetap utuh:** analisis DataNeed, rencana hipotesis, riset multi-sudut, persetujuan rencana, semua
  gerbang dan alat tidak diubah. Jalur baru hanya aktif lewat saklar baru (mati secara default) atau pilihan per pesan
  untuk A/B.
- **Jalur baru, tingkat 1 eksplorasi (satu giliran):** AI membuka sandbox langsung; data diambil dengan satu fungsi
  `fetch(...)` di kode (di belakangnya tetap DataNeed dan Governor; ukuran, cakupan tanggal dan batas dilaporkan sebelum
  data ditarik); alat bantu riset yang ada (`research_*`, `event_study`, `backtest`, `event_summary`) dipanggil dari
  kode; hipotesis dirumuskan AI sendiri. Setiap uji dicatat otomatis (buku catatan uji) dan dikoreksi Benjamini–Hochberg
  atas semua uji; jawaban berlabel eksploratif, tanpa klaim "terbukti"; backend tetap menghitung ulang angka.
- **Jalur baru, tingkat 2 konfirmasi (hanya bila user minta):** hipotesis terbaik menjadi rencana pre-registrasi yang
  diisi sistem, satu klik setuju, diuji di periode holdout dengan ambang lebih ketat, vonis lewat `complete_research_run`.
- **Persetujuan:** hanya untuk tingkat 2 atau bila ekstraksi melewati anggaran Governor.
- **A/B:** 5 pertanyaan conversation di atas, jalur sekarang vs jalur baru; diukur waktu, biaya, mutu dan kebenaran
  angka. **Target (user 2026-10-13): "fokus utama adalah bisa menjawab dulu under maks 3 mins"**, yaitu setiap
  pertanyaan selesai paling lama 3 menit (menggantikan target median < 2 menit, p90 < 4 menit).
- **Ditunda (user: "No deh, untuk sekarang"):** ukuran "insightful", hipotesis dipilih sistem dari beberapa kandidat,
  sudut lanjutan dihitung sebelum diklik, dan nilai insight di A/B.
- **Tahapan (masing-masing butuh go user):** 0 baseline; 1 batas data terlihat dan level berpikir adaptif di jalur baru
  (R2, R4, G1); 2 `fetch()` (R1, R3, R5, R6, G2, G4); 3 buku catatan uji dan label eksploratif; 4 tingkat konfirmasi.
  G3 dan G5 (R7) bisa dikerjakan kapan saja di jalur baru.
- **Rujukan:** CodeAct (arXiv 2402.01030), Data Interpreter (arXiv 2402.18679), Anthropic "Code execution with MCP",
  POPPER (arXiv 2502.09858), Harvey–Liu–Zhu (NBER w21329), adaptive reasoning (arXiv 2608.26442).
- **Prinsip jalur (user 2026-10-13):** "ingat, ini jalur berbeda dari current/ existing ya. Jadi harus selalu ada
  fallback jika nanti kedepan makin worse design yang kita buat."
  - semua butir R dan G di bawah hanya berlaku di jalur baru; jalur sekarang tidak berubah;
  - fallback: jalur baru dimatikan dengan satu saklar dan semua pesan kembali ke jalur sekarang; per pesan bisa dipilih
    jalur sekarang; setiap run mencatat jalur yang dipakai (log dan `execution`) untuk A/B;
  - butir yang mirip entri lain dicatat sebagai konteks (rujukan silang), bukan pekerjaan ganda.
- **Rekomendasi R1–R8** (user: "masukan exec"):
  - **R1 jalur cepat sebagai default di jalur baru:** pertanyaan saring, deskripsi dan perbandingan historis langsung
    diambil datanya lalu dihitung dengan kode dalam satu giliran (gaya CodeAct); rencana dan persetujuan hanya untuk uji
    formal yang diminta user atau ekstraksi yang sangat besar (tingkat 2 di atas).
  - **R2 batas terlihat sejak awal:** cakupan tiap tabel dan perkiraan ukuran ekstraksi (batas 64 bagian) diberikan
    sejak awal atau lewat satu alat estimasi murah.
  - **R3 formulir dikurangi:** AI menulis query dan analisis di kode sandbox; Governor tetap menjaga batas data
    (sama dengan `fetch()` di tingkat 1).
  - **R4 level berpikir adaptif:** default panggilan loop Rendah/Sedang, Tinggi hanya untuk merancang; panggilan lebih
    dari 90 s diulang dengan level Rendah. Konteks: pengaman runaway M150 (EXEC-LOGOS) sudah ada di semua jalur.
  - **R5 aturan prompt dirapikan:** aturan yang bertentangan (lingkup router vs metode) dibuang; hanya alat yang relevan
    per langkah ditawarkan (prompt jalur baru sendiri; prompt jalur sekarang tidak diubah).
  - **R6 pra-cek draf hanya bila perlu:** misalnya bila jawaban punya banyak angka, agar jawaban tidak ditulis dua kali.
  - **R7 perbaikan run `9cd51749`:** routing ke CONTINUE dan kode broker disimpan (sama dengan G5).
  - **R8 ukur sebelum dan sesudah:** 5 pertanyaan conversation di atas; target paling lama 3 menit per pertanyaan
    (butir A/B di atas).
- **Usulan gerbang G1–G5** (inspeksi kode jalur riset 2026-10-13; user: "masukan exec"):
  - **G1 batas terlihat saat ditolak:** penolakan `check_data_feasibility` / `check_research_feasibility` dan Governor
    ("The extraction needs 105 parts; the limit is 64", `market-sql-governor/app/extract.py:844`, `next_action`
    `NARROW_THE_PLAN_OR_REPORT_LIMITATION`) menyertakan perkiraan periode, universe atau agregasi yang muat. Bukti: run
    `e5faf07f` mencoba 4 kali (105, 67, 128, 122 bagian) sekitar 79 s. Konteks: R2.
  - **G2 governance diisi sistem:** `research_plan.match_governance` mewajibkan sekitar 12 field governance sama persis
    dengan eksperimen yang disetujui (RESEARCH_PLAN_MISMATCH); di jalur baru AI cukup menyebut `hypothesis_id`, sistem
    mengisi sisanya dari rencana. Bukti: run `a45f86c8` ditolak lalu menulis ulang spec, sekitar 48 s.
  - **G3 salah tolak DEFINITION:** `definition_check.problems` menolak kalimat "konsisten dengan hasil sebelumnya" bila
    run tidak membuka hasil lama lewat `load_output`, juga saat run tidak membuat tabel baru dan hanya membaca tabel
    lama (`get_session_output`, ekspor). Bukti: run `80e733ba` (ekspor Excel), sekitar 25 s. Usulan: lewati bila run
    tidak membuat tabel baru, atau hitung `get_session_output` sebagai membuka hasil lama.
  - **G4 angka rencana tanpa ronde perbaikan:** PLAN_SUCCESS_RULE, PLAN_MIN_EFFECT, PLAN_HORIZON, PLAN_TEXT_PROVENANCE
    dan PLAN_PROVENANCE cukup masuk daftar "nilai yang perlu dikonfirmasi" yang sudah ditulis backend
    (`plan_meta.values_to_confirm`), tanpa menyuruh AI memperbaiki rencana.
  - **G5 CLARIFY yang butuh hitungan baru:** catatan router CLARIFY ("No new data is extracted and nothing is computed in
    this turn", `conversation_router.py:327`) membuat run `9cd51749` hanya menawarkan rekap broker; permintaan yang
    butuh hitungan baru diarahkan ke CONTINUE, dan tabel hasil riset ikut menyimpan identitas kunci (kode broker).
  - Gerbang lain jalur riset dinilai perlu dengan pesan dan langkah perbaikan yang jelas: EMPTY_REQUEST,
    PLAN_CARRIED_INPUTS, PLAN_FINDINGS, PLAN_VERSION, RESEARCH_PLAN_REAPPROVAL_REQUIRED, PLAN_NOT_EXECUTED,
    RESEARCH_RUN_INCOMPLETE, ANALYSIS, ROUTING, PROVENANCE, FINDINGS/FINDINGS_2.
- **Keputusan user atas review (2026-10-13):**
  - **K1 "Ok boleh":** tingkat 1 jalur baru boleh mengambil data tanpa persetujuan (penyimpangan sadar dari jaminan
    EXEC-D, khusus jalur baru); vonis "terbukti" tetap hanya lewat tingkat 2 dengan persetujuan.
  - **K2 "perbaiki dulu di jalur sekarang, baru nanti pecah jalur agar perbaikan terbawa":** G3 (DEFINITION) dan G5
    (CLARIFY yang butuh hitungan baru, kode broker disimpan) dikerjakan lebih dulu di jalur sekarang, sebelum jalur baru
    dipisah.
    **Dikerjakan 2026-10-13 (Fase A):** G3 = M151, G5 = M152 (lihat ERRORS).
- **Catatan desain dari inspeksi kode (2026-10-13, user: "Yes"):**
  - **D1 alat riset = pemeriksa, bukan kemampuan hitung.** Sandbox bisa menghitung semuanya; alat riset ada supaya
    statistik dihitung ulang sistem di luar proses AI dengan nilai yang disetujui (`research_validation.py`,
    `research_findings.py`, `event_study_validation.py`), sampel efektif dan efek minimum dihitung sistem, jumlah uji
    dicatat (`research_policy.py`), dan vonis memakai label baku. `research_*` saat ini hanya tersedia di sesi riset
    yang disetujui (terikat `angle_id`, `sessions.py:871`). Jalur baru butuh versi eksploratif `research_*` tanpa
    `angle_id` yang disetujui; tetap dihitung ulang sistem, berlabel eksploratif.
  - **D2 tabel turunan dalam satu sesi:** sesi sandbox persisten (variabel tetap ada antar `run_python`,
    `sessions.py:797`); `save_table`/`load_table` menyimpan dan membuka tabel kerja, jadi tabel 3 = gabungan tabel 1
    dan 2 bisa dibuat (pandas `merge`). Batas: tabel kerja `NOT_RELEASED` sampai `emit_table`, kuota
    `working_table_bytes`, anggaran frame dan jumlah output per sesi. `sql()` hanya membaca view data DataNeed; SQL atas
    tabel kerja belum diuji.
  - **D3 isi hipotesis bebas, bentuk uji terbatas:** rumus kondisi dan outcome bebas ditulis AI
    (`research_governance.py`: tidak ada daftar rumus). Vonis terverifikasi hanya untuk bentuk uji yang ada: kondisi →
    hasil (`event_summary`, `research_conditional`), sensitivitas ambang, persistensi, perbandingan kelompok/rezim,
    peringkat kuantil, lead-lag/korelasi, event study dan backtest. Di luar itu `research_custom` berstatus
    `EXECUTION_ONLY` dan vonis paling tinggi `INSUFFICIENT_EVIDENCE` (`saniti_session.py:1633`). Di jalur baru: tingkat
    1 boleh bentuk apa pun (label "eksploratif, dihitung AI"); tingkat 2 hanya bentuk yang bisa diverifikasi; bentuk baru
    ditambah bila pola pertanyaannya sering muncul.
- **B0 baseline jalur sekarang (2026-10-13, user "Go"; runner `157a081f` dan `db92253f`, orc `2e935d87`, DeepSeek V4.1
  Flash Tinggi):**

  | Giliran | Jalur router | Waktu | Panggilan model | Formulir data | Pra-cek draf | Hasil |
  |---|---|---|---|---|---|---|
  | b1 pergerakan BBRI seminggu | ANALYSIS | 114 s | 9 (78 s) | 1× / 10 s | 21 s | jawaban |
  | b2 distribusi BBRI kemarin | ANALYSIS | 241 s | 11 (209 s, terlama 75 s) | 1× / 15 s | 58 s | jawaban |
  | b3 akumulasi asing + performa lanjutan | EXPLORE | 569 s | 19 (534 s) | 2× / 72 s | 77 s | jawaban satu giliran (event study), tanpa rencana |
  | b4 akumulasi broker X/Y → return > 10% | ANALYSIS | 381 s | 16 (314 s) | 2× / 47 s | 39 s | jawaban satu giliran, tanpa rencana |
  | b5.1 lima broker net beli BBRI | ANALYSIS | 164 s | 13 (138 s) | 1× / 33 s | 32 s | jawaban |
  | b5.2 rekap per minggu | INSIGHT | 272 s | 11 (261 s) | 1× / 9 s | 45 s | jawaban |
  | b5.3 ekspor Excel | CLARIFY | 42 s | 2 (39 s) | 0 | 0 | 2 file XLSX |

  - Lolos target ≤ 3 menit: 3 dari 7 giliran (b1, b5.1, b5.3); 4 lewat (b2, b3, b4, b5.2).
  - Pembagian waktu model (±1.570 s):
    - menulis dan mengulang `run_python` ±33%;
    - menjelajah katalog dan panduan sebelum formulir ±22%;
    - pra-cek draf `check_references` ±17%;
    - formulir data `submit_data_need_spec` ±12%;
    - menulis jawaban ±12%.
  - Gerbang jawaban: tidak ada yang menolak. Tidak ada runaway.
  - b3 dan b4 kini dijawab dalam satu giliran, jadi pesan "Setuju, jalankan rencananya" dijawab dengan pertanyaan balik
    (tidak ada rencana menunggu).
  - **Keputusan `fetch()`:** formulir data hanya ±12% waktu, jadi `fetch()` tetap ditunda. Sasaran terbesar B1/B2:
    - jumlah iterasi `run_python`;
    - penjelajahan katalog (batas dan cakupan terlihat sejak awal, R2);
    - pra-cek draf (R6).
  - Biaya B0: USD 0,35. Run pertama (`157a081f`) berhenti di b3 karena limit kunci OpenRouter habis (USD 38 dari 38);
    user menaikkan limit ke USD 39, lalu b3–b5 diulang (`db92253f`).
- **B1 + B2 dibangun (user 2026-10-13: "B1 + B2 berturut2"):**
  - **Orc:**
    - saklar `AI_ENABLE_FASTLANE` (default mati), field `lane` per pesan (`app/lanes.py`, contextvar `current_lane`);
    - `execution.lane`; `/v1/models` `lane_selection`; `lane: "fast"` ditolak `LANE_NOT_AVAILABLE` saat saklar mati;
    - giliran jalur cepat: desk `FASTLANE` (alat analisis + `check_data_feasibility`, tanpa alat rencana/riset) dan
      `FASTLANE_NOTE` (satu giliran, satu data need lengkap, satu skrip per `run_python`, pra-cek draf hanya bila
      > ±8 angka, hasil eksploratif);
    - rute RESEARCH dijalankan sebagai analisis (mode ANALYSIS); EXPLORE langsung satu langkah analisis;
    - panggilan sesudah yang pertama memakai level `low` (model berlevel); satu panggilan per run dipotong 90 s lalu
      diulang dengan level rendah;
    - penolakan ukuran data membawa `fits` (bagian yang muat).
  - **EDGE:** pilihan "Jalur: Standar / Cepat" di menu model (hanya bila `lane_selection`), dikirim sebagai `lane`,
    disimpan di browser, "Jalur Cepat" tampil di kepala jawaban.
  - **Runner:** `lane` per item.
  - **Fallback terbukti di tes:** tanpa `lane` atau `lane: "standard"`, payload identik dengan saklar mati.
  - **Tes:** orc 1.475 lulus; EDGE 84 lulus (satu kali gagal di tes mengetik yang memang kadang gagal di main).
- **A/B pertama B2 (2026-10-13, user "Ok done": saklar dinyalakan, limit kunci dinaikkan ke USD 40; runner `0288fb7e`,
  orc `03e68187`, DeepSeek V4.1 Flash Tinggi, `lane: "fast"`):**

  | Giliran | B0 jalur sekarang | Jalur cepat | Panggilan model (B0 → cepat) | `run_python` | Pra-cek draf |
  |---|---|---|---|---|---|
  | b1 pergerakan BBRI seminggu | 114 s | **94 s** | 9 → 6 | 1 → 2 | 21 s → 0 |
  | b2 distribusi BBRI kemarin | 241 s | 194 s | 11 → 9 | 2 → 3 | 58 s → 62 s |
  | b3 akumulasi asing | 569 s | 360 s | 19 → 13 | 9 → 4 | 77 s → 53 s |
  | b4 akumulasi broker X/Y | 381 s | 246 s | 16 → 14 | 6 → 2 | 39 s → 29 s |
  | b5.1 lima broker BBRI | 164 s | **118 s** | 13 → 9 | 4 → 3 | 32 s → 11 s |
  | b5.2 rekap per minggu | 272 s | 309 s | 11 → 8 | 4 → 2 | 45 s → **210 s** |
  | b5.3 ekspor Excel | 42 s | **26 s** | 2 → 3 | 0 | 0 → 8 s |

  - Total waktu 1.783 s → 1.348 s (−24%). Lolos ≤ 3 menit: 3/7 → 3/7 (b2 194 s nyaris).
  - Bolak-balik `run_python` turun tajam (b3 9 → 4, b4 6 → 2).
  - Sisa pemborosan terbesar:
    - pra-cek draf berulang (b5.2: 4 panggilan, 210 s);
    - formulir data dikirim ulang (b3: 4 formulir, 124 s).
  - Tidak ada panggilan yang dipotong 90 s; gerbang menolak sekali (ROUTING di b5.1).
  - Biaya A/B USD 0,31.
  - Saklar `AI_ENABLE_FASTLANE=true` di orc dev (deployment `03e68187` SUCCESS, dibaca ulang dari variabel);
    `.railway/railway.ts` mencatat variabel itu. `railway config pull` juga menarik perubahan perintah start job
    Feature04 yang tidak terkait (drift cron yang user tunda: "nanti saja"), jadi tidak ikut di-commit.
- **A/B B2b pra-cek draf di jalur cepat (2026-10-14, user: "Coba A/B 3 pertanyaan serupa dengan yg lama tadi. Pakai
  fastlane, bedanya pra draft enable dan disable. Jalankan. Please assess juga dari sisi akurasi"):**
  - Saklar baru `AI_FASTLANE_DRAFT_CHECK` (default `true` = perilaku lama). `false` menarik `check_references` dari
    setiap langkah jalur cepat dan menghapus butir pra-cek dari catatan jalur. Jalur Standar selalu tetap memakainya.
    `main` `bd9b52f`, orc `86cdc41b` SUCCESS.
  - ON: runner `59099d59`, orc `86cdc41b`. OFF: variabel `false`, orc `dbbb98e1`, runner `f17d3012`. Sesudahnya variabel
    dihapus dan orc `d2aab9ea` SUCCESS (kembali ke default ON). Pertanyaan b2, b4 (giliran 1 saja), b5 (3 giliran);
    DeepSeek V4.1 Flash Tinggi; biaya ≈ USD 0,21.

  | Giliran | ON (pra-cek) | OFF | Pra-cek di ON | Penolakan gerbang ON / OFF |
  |---|---|---|---|---|
  | b2 distribusi BBRI kemarin | 191 s | 212 s | 2×, 64 s | PROVENANCE / – |
  | b4 akumulasi broker X/Y | 473 s | 354 s | 1×, 62 s | – / REFERENCE (format tak dikenal, perbaikan 2 s) |
  | b5.1 lima broker BBRI | 159 s | 159 s | 1×, 20 s | ROUTING / ROUTING |
  | b5.2 rekap per minggu | 313 s | 232 s | 4×, 90 s | – / PROVENANCE |
  | b5.3 ekspor Excel | 23 s | 36 s | 0 | PROVENANCE / PROVENANCE |

  - Total 1.158 s → 992 s (−14%); waktu model 1.016 s → 876 s. Pra-cek di ON: 8 panggilan, 236 s, tidak mencegah
    penolakan (b2 tetap kena PROVENANCE sesudah 2 pra-cek). Di OFF penolakan gerbang naik 3 → 4, masing-masing
    diperbaiki dalam satu ronde singkat. Lolos ≤ 3 menit: 2/5 → 2/5.
  - Variasi lama berpikir model mendominasi. OFF b2 tanpa pra-cek tetap 212 s karena dua panggilan 65 s dan 73 s
    (4.600–6.000 token berpikir walau level rendah); ON b4 473 s karena penjelajahan katalog dan cek ukuran 129 s.
  - **Akurasi** (silang-cek antar-run independen: ON, OFF, dan A/B 2026-10-13; query langsung ke database ditolak
    pengaman sesi):
    - Angka inti sama persis di semua run: candle BBRI 13 Okt, lima broker net beli Agustus, hitungan pekan 5 besar.
    - Jendela "distribusi" b2 berbeda per run (63 hari, 29 hari, ±127 sesi), yaitu pilihan AI yang dicatat di asumsi.
      Kedua jendela sama-sama kurang 2 hari bursa dari kalender (diduga celah data harga Sep–Okt, belum diverifikasi).
    - Salah tafsir di OFF:
      - b2: posisi tutup 71% disebut "bagian bawah" rentang;
      - b4: judul memakai statistik hari-kondisi yang tumpang tindih ("justru sebaliknya"), padahal baris kejadian dan
        uji non-overlapping (p 0,91) tidak menunjukkan arah;
      - b5.2: asumsi/batasan tertulis dua kali di badan jawaban.
    - ON tidak punya salah tafsir serupa. Pra-cek tidak memeriksa tafsir, jadi selisih ini kemungkinan variasi model
      (sampel 5 giliran).
    - Satuan: koreksi satuan otomatis tetap jalan di kedua sisi. Kolom turunan buatan AI (mis. ambang X) tercatat
      `ai_reference_unit_unknown` di kedua sisi, artinya satuan kolom itu tidak dikenal sistem.
  - **Keputusan user 2026-10-14:** "Ok, matikan ya untuk fastlane." `AI_FASTLANE_DRAFT_CHECK=false` di orc dev
    (deployment `12a494eb` SUCCESS). Fokus berikutnya: lama berpikir AI dan langkah pencarian tabel.
- **B3 revisi (2026-10-14, user: "Ok, jalankan"; dikerjakan, belum di-deploy):**
  - **Keputusan user:** fase ini hanya ANALYSIS dan EXPLORE. "Uji statistik untuk pencarian insight tidak perlu
    dibuktikan secara statistik melalui research governor, but should be reliable and trustworthy enough sehingga
    hasilnya tidak misleading." Angka tidak perlu divalidasi kebenarannya oleh backend, tetapi harus cukup akurat.
    `fetch()` tidak dibuat; B4 (validasi di holdout) keluar dari fase ini.
  - **Dua mode di jalur cepat:**
    - Mode Jawab (default): uji hanya pertanyaan pengguna, tanpa hipotesis baru.
    - Mode Insight: route EXPLORE dari router pesan pertama atau kelas INSIGHT dari router percakapan; paling banyak 5
      sudut dari library riset, `stability=True`.
  - **Keputusan kecil:** a) helper diarahkan lewat catatan, tidak dipaksa; b) tanpa gerbang tolak-perbaiki baru,
    cukup catatan + kalimat bukti dari sistem; c) pemicu Insight memakai route EXPLORE yang ada (prompt router tidak
    diubah); d) kalimat bukti di `limitations`; e) BH dengan alfa 5%; f) cek stabilitas dua paruh periode di Insight.
  - **Sandbox** (`PY_SANDBOX_EXPLORE_TESTS_ENABLED`, default mati):
    - `saniti.explore_test` (extra helper sesi analisis, tidak pernah di sesi riset) menjalankan
      `research_engines.evaluate` atas frame AI: sampel efektif per tanggal, interval, p dua sisi; harga sebagai
      outcome ditolak; merilis `explore_<nama>` dan mencatat `explore_test_call_<nama>`.
    - `event_study` di sesi itu ikut tercatat; hitung ulang backend tidak berubah.
    - `final_status.explore_tests` (`app/explore_tests.py`): koreksi BH atas uji eksekusi yang berhasil, `held`,
      `unstable`, `small_samples`; `/v1/runtime` `explore_tests`.
  - **Orc** (`AI_FASTLANE_EXPLORE_TESTS`, default mati; aktif hanya bila sandbox melaporkan `explore_tests`):
    `lanes.current_explore_mode`, catatan per mode (`EXPLORE_ANSWER_NOTE`, `EXPLORE_INSIGHT_NOTE` dengan 8 metode dari
    `research_library.py`), kalimat "Bukti statistik" ditulis sistem (`user_texts.explore_evidence_line`), dan kalimat
    jalur analisis "tanpa uji signifikansi" tidak ditempel bila uji sudah dilaporkan (kontradiksi yang ditemukan
    saat tes).
  - **Tes:** sandbox 6 tes baru lulus; suite sandbox 821 lulus, 2 gagal yang juga gagal di `main` tanpa perubahan ini
    (`test_a_weekly_analysis_records_its_derivation`, `test_a_crash_is_labelled_after_the_process_exits`, kegagalan
    lingkungan). Orc 1.484 lulus, 258 dilewati. `AI_TOOLS.md` diregenerasi.
  - **Berikutnya (butuh izin user):** deploy sandbox lalu orc dev, nyalakan kedua variabel, A/B ON vs OFF (Mode Jawab
    b3/b4, Mode Insight 2 pertanyaan baru).
- **A/B B3 (2026-10-14, user: "Boleh", izin variabel diberikan): OFF runner `d8f977b1` (orc `6a5ecc4f`), lalu
  `PY_SANDBOX_EXPLORE_TESTS_ENABLED=true` (sandbox `b92b29c6` SUCCESS) dan `AI_FASTLANE_EXPLORE_TESTS=true` (orc
  `bcc854cc` SUCCESS, tanpa `explore_tests_inactive`), ON runner `f0c1a7f1`. DeepSeek V4.1 Flash Tinggi, jalur cepat.**

  | Item | OFF | ON | Mode ON | Uji tercatat (lolos) |
  |---|---|---|---|---|
  | j1 akumulasi asing 1 bulan + performa lampau | 251 s | **177 s** | Jawab (route RESEARCH) | 1 (0, sampel kecil) |
  | j2 akumulasi broker X/Y → >10% | 354 s (run B2b OFF) | 438 s | Jawab (route RESEARCH) | 1 (0, sampel kecil) |
  | i1 "carikan insight" aliran asing BBRI | 115 s | 214 s | **Jawab** (route ANALYSIS) | 1 (0) |
  | i2 "pola apa yang menarik" broker bank | 208 s | 244 s | **Jawab** (route ANALYSIS) | 0 |
  | m1.1 distribusi return BBRI | – | 152 s | Jawab | 0 |
  | m1.2 net beli asing besar → return 5 hari | – | 324 s | Jawab (CONTINUE) | 1 (0) |
  | m1.3 "carikan insight lain" | – | 4 s | tanya-balik 4 pilihan | – |
  | m1.4 "rekap per minggu" (balasan tanya-balik) | – | 78 s | **Insight** (kelas INSIGHT) | 0 |
  | m1.5 pindah ke TLKM | – | 146 s | Jawab (NEW_TOPIC → ANALYSIS) | 0 |

  - **Keandalan (tujuan utama):** semua p-value di jawaban ON datang bersama selisih, rentang dan sampel efektif
    (j2: −0,85 pp, −4,61…2,92, p 0,66, 44 tanggal; m1.2: −0,32 pp, −1,19…0,56, p 0,47); tidak ada klaim arah atau
    "terbukti"; kata "sebab" hanya dalam penyangkalan. Kalimat "Bukti statistik" muncul di 4 jawaban yang menguji,
    kalimat "tanpa uji signifikansi" tidak muncul bersamanya. OFF j1 masih memakai "justru sebaliknya" (untuk peringkat
    deskriptif, bukan uji).
  - **Mode Insight hampir tidak terpicu:** router pesan pertama memberi ANALYSIS untuk i1 dan i2, jadi keduanya
    berjalan sebagai Mode Jawab. Insight hanya terpicu di m1.4 (balasan tanya-balik "insight lain"), dan pertanyaan
    itu rekap sehingga tanpa uji. Mode Insight dengan beberapa sudut belum teruji di run nyata.
  - **Waktu:** giliran tunggal 574 s → 635 s (+11%); j1 −30%, j2/i1/i2 lebih lama (ada uji, j2 19 panggilan dan satu
    perbaikan TYPED_FIGURES, router pesan pertama j2 46 s dengan 2 percobaan). ≤ 3 menit: 4 dari 8 run ON.
  - **Gerbang:** ON 3 penolakan (TYPED_FIGURES ×2, METHODOLOGY_PROVENANCE ×1), masing-masing satu perbaikan.
  - **Biaya:** OFF USD 0,09, ON USD 0,38. Sisa kunci ≈ USD 0,5.
  - **Saklar tetap menyala di dev** sampai keputusan user (fallback: hapus kedua variabel).
- **Cek ulang A/B B3 dan dua perbaikan berikutnya (2026-10-14, user: "Ok untuk 1 dan 2 masukan exec"; belum
  dikerjakan, masing-masing butuh go):**
  - **Cek ulang:** semua p-value di jawaban ON sama dengan uji tercatat (i1 0,567, j2 0,655, m1.2 0,475 via
    `event_study`); angka inti j1 OFF/ON konsisten (bulan kalender 19 hari vs 21 hari bergulir, definisi ditulis di
    jawaban); alasan router untuk i1/i2 sama di OFF dan ON ("perhitungan deskriptif, bukan pengujian hipotesis").
  - **Perbaikan 1, celah satuan (bug lama, bukan dari B3):** jawaban i1 ON menulis "turun −6,07", "setara −0,107
    dari nilai transaksi" dan "menyumbang 0,444" (seharusnya −6,07%, −10,7%, 44,4%). Tabel AI `konteks_periode`
    dirilis tanpa `units` dan isinya campuran (`return_periode_pct` sudah persen, `net_asing_pct_transaksi` pecahan
    walau bernama pct); rujukan ditulis tanpa format, dan `ai_reference_unit_unknown` hanya aktif untuk format persen,
    jadi tidak ada peringatan. Usulan (a, disarankan): `emit_table` di sandbox mewajibkan `units` untuk kolom yang
    namanya menunjukkan persen, porsi, rasio atau return (`*_pct`, `pct_*`, `porsi*`, `share*`, `ratio*`,
    `return*`) dan menolak eksekusi dengan pesan jelas; berlaku di semua jalur. Usulan (b, opsional): orc mencatat
    rujukan tanpa format ke kolom seperti itu sebagai `unit_unknown` dan meminta satu perbaikan.
  - **Perbaikan 2, pemicu Mode Insight:** router pesan pertama memberi ANALYSIS untuk "carikan insight…" dan "pola
    apa yang menarik…", jadi Mode Insight hanya terpicu sekali (m1.4, balasan tanya-balik). Usulan: field `insight`
    (boolean) di skema router pesan pertama, menyala bila pengguna meminta insight, pola atau "apa yang menarik";
    route tidak berubah, field hanya dipakai jalur cepat untuk Mode Insight. Uji: `scripts/benchmark_turn_router.py`
    (akurasi route tidak boleh turun), deploy dev, ulang i1, i2 dan satu pertanyaan insight lain (≈ USD 0,15).
- **Keputusan desain Mode Jawab vs Mode Insight (2026-10-14, user: "Kita lock untuk mode insight dengan perbaikan
  B3"; "That is correct"; belum dikerjakan di kode):**
  - **Definisi:** uji statistik = pertanyaan pengguna dibuktikan dengan statistik (Mode Jawab); insight = eksplorasi
    oleh AI (Mode Insight).
  - **Mode Insight dikunci dengan B3:** klaim pola hanya dari `explore_test` (library riset), uji tercatat, koreksi
    BH, cek stabilitas; rincian deskriptif bebas. Ditambah Perbaikan 2 (pemicu `insight` di router).
  - **Mode Jawab: model + kode, tanpa mesin validasi.** Model menganalisa dengan kode bebas di sandbox (scipy,
    statsmodels, pandas); helper (`forward_return`, `period_return`, `event_study`, `explore_test`) opsional bila
    cocok; checklist metode singkat di catatan (kejadian tumpang tindih, cluster per tanggal, rentang + N, parameter
    dipilih sekali dan ditulis di asumsi); aturan tafsir tetap; tanpa buku catatan wajib, koreksi BH atau Research
    Governor. Aturan B3 sekarang ("setiap uji lewat explore_test, jangan scipy") dicabut untuk Mode Jawab karena
    pertanyaan pengguna beragam dan bisa dipaksa masuk ke metode yang tidak cocok. Perbaikan 1 (satuan wajib) tetap.
    Tahap berikutnya: resep istilah bisnis yang sering muncul.
  - **Bukti eksternal:** kode jauh lebih andal dari penalaran teks (QRData, arXiv 2402.17644); kesalahan utama LLM
    adalah pemilihan uji dan tafsir, bukan aritmetika (StatQA arXiv 2406.07815, StatABench arXiv 2606.22977); agen
    menghasilkan kesalahan diam yang tampak masuk akal (arXiv 2607.21482, LongDS-Bench arXiv 2605.30434); resep atau
    query terverifikasi menaikkan akurasi produksi (Snowflake Cortex Analyst, vendor: 51% → 90%+).
- **Mode Jawab v2 (2026-10-14, user: "OK"; 5B + butir 2 + butir 3 dipersempit; tanpa saklar untuk 5B):**
  - **5B satuan (semua jalur):** sandbox `emit_table` memberi `return_pct` PERCENT dan `return_decimal` FRACTION bila
    tidak dideklarasikan, dan memperingatkan (`UNIT_UNDECLARED`) kolom numerik bernama seperti share, rate, persen,
    rasio bagian atau return tanpa satuan (kata hitungan di awal/akhir nama dikecualikan; `porsi_5_hari_masuk_terbesar`
    tetap terdeteksi). Orc: rujukan tanpa format ke kolom seperti itu di tabel AI (`out.*`) dicatat
    `unit_unknown` dan memicu gerbang `UNITS` sekali (annotate, edit saja). Temuan backend (`finding.*`) tidak ikut.
    Panduan metode dan prompt sistem tidak diubah (tanpa migrasi DB).
  - **Butir 2:** `EXPLORE_ANSWER_NOTE` baru (kode bebas, helper bila cocok, checklist metode, units=); aturan wajib
    `explore_test` hanya di Mode Insight; kalimat `FASTLANE_ANSWER_LINE` menggantikan "tanpa uji signifikansi" di Mode
    Jawab jalur cepat tanpa uji tercatat.
  - **Butir 3 (dipersempit):** `get_system_capabilities` di `never` desk FASTLANE + satu kalimat di `FASTLANE_NOTE`;
    `preview_table_rows` dan `check_data_feasibility` tetap. Prompt sistem tidak diedit (dipakai semua jalur, prefix
    cache).
  - **Tes:** orc 1.486 lulus, 258 dilewati; sandbox 835 lulus, 2 gagal lama yang sama. `AI_TOOLS.md` diregenerasi.
  - **Baseline sebelum deploy** (runner `1702d854`, orc `bcc854cc`): o1 volatilitas BBRI Q3 vs Q2 145 s, o2
    normalitas return TLKM 63 s.
- **Keputusan lanjutan Mode Jawab v2 (2026-10-14; belum dikerjakan):**
  - **F1 disetujui** (user: "F1 --> usulan approved"): sesi tanpa completion tidak memblokir bila ada sesi lain di run
    itu yang COMPLETED dan jawaban tidak merujuk output sesi yang ditinggalkan (atau orc menutup sesi lama otomatis
    saat formulir data dikirim ulang).
  - **F2 terbatas** (user: "Okelah untuk F2 masukan exec"): mekanisme saran yang ada tetap (R3 auto-referensi, menu
    alamat, kandidat TYPED_FIGURES M140, EXEC-DERIVED, petunjuk literal kode P25). Diterima otomatis tanpa putaran,
    dengan label: B1 tingkat kepercayaan standar (90/95/99%) bersebelahan dengan "kepercayaan"/"confidence"/"selang"
    (label konvensi); B2 parameter yang tertulis sebagai literal di kode yang berhasil jalan, bila ditulis di asumsi/
    metodologi atau bersebelahan dengan kata parameter (jendela, ambang, persentil, horizon, hari bursa) (label
    parameter dari kode). Tetap ditolak: C hitungan turunan (selisih/rasio/perubahan, kecocokan bisa kebetulan) dan D
    angka dari stdout atau output tidak dirilis. Bukti eksternal: verifikasi eksternal lebih andal dari verifikasi diri
    (CRITIC, arXiv 2305.11738); perbaikan mempertahankan teks asli (RARR, arXiv 2210.08726); grounding struktural saat
    menulis (Anthropic Citations API). Risiko "semua disarankan": angka tanpa sumber sampai ke user, label DIRUJUK
    kehilangan arti, kecocokan kebetulan diberi label resmi.
  - **Bagian asumsi, batasan, metodologi dibatasi** (user: "Ok untuk limitasi asumsi dan metodologi dibatasi, masukan
    exec"; concern: waktu, tetapi jawaban jangan terlalu "summary"). Ukuran 18 jawaban: jawaban utama 45%, asumsi
    14%, batasan 21% (termasuk kalimat sistem), metodologi 21% dari teks; panggilan menulis jawaban 24% dari token
    output run, ketiga bagian sekitar 5–6%, dan setiap penolakan gerbang menulis ulang semuanya. Arah: jawaban utama
    tidak dipangkas (detail tetap: angka kunci, tabel inti, penjelasan pendorong); asumsi dan batasan masing-masing
    paling banyak 3 poin pendek tanpa mengulang isi jawaban; metodologi ringkas (langkah, data, uji, parameter) di
    jalur cepat. Rincian angka batas ditetapkan di rencana implementasi.
- **A/B Mode Jawab v2 (2026-10-14): `main` `e323015`, sandbox `f4b459e6` dan orc `3a133fa1` SUCCESS (auto-deploy,
  tanpa variabel baru, `explore_tests` tetap aktif); runner baseline `1702d854` (orc `bcc854cc`) dan v2 `3af9103f`.**

  | Item | Sebelum | v2 | Catatan v2 |
  |---|---|---|---|
  | j1 akumulasi asing + performa lampau | 166 s (ON B3) | 425 s | 22 panggilan; 3 perbaikan gerbang (PROVENANCE "3,7", TYPED_FIGURES "21", REFERENCE sintaks tabel salah); 3 uji tercatat |
  | j2 akumulasi broker → >10% | 391 s (ON B3) | 252 s | **LIMITATION**: formulir data dikirim ulang, sesi pertama ditinggalkan, gerbang ANALYSIS memblokir walau sesi kedua COMPLETED |
  | t1 net beli asing besar → return 5 hari | 310 s (m1.2, giliran ke-2) | **111 s** | 1 uji tercatat; PROVENANCE "95%" |
  | o1 volatilitas BBRI Q3 vs Q2 (di luar library) | 140 s | **58 s** | uji F, Levene, Welch; rasio 0,40× (CI 0,24–0,68); PROVENANCE "36%" |
  | o2 normalitas return TLKM (di luar library) | 50 s | 119 s | Shapiro, D'Agostino, Jarque-Bera, Anderson-Darling, KS (lebih lengkap dari baseline: hanya JB) |

  - **Butir 2 bekerja:** pertanyaan di luar library dijawab dengan uji yang tepat, bukan dipaksa ke `explore_test`
    (baseline o1 memakai `explore_test` + 4 bacaan panduan). Bacaan panduan metode turun (j2, o1, o2: 0).
  - **Butir 3 bekerja:** `get_system_capabilities` tidak dipanggil di semua run v2.
  - **Butir 5B:** tidak ada angka persen/porsi tampil mentah; desimal telanjang yang tersisa sah (rasio "kali", pp,
    p-value, statistik uji, skewness). Gerbang `UNITS` tidak terpicu di run ini.
  - **≤ 3 menit:** 3 dari 5 (t1, o1, o2). Biaya v2 USD 0,13, baseline USD 0,05.
  - **Temuan baru (belum diperbaiki, butuh go):**
    - **F1 sesi ditinggalkan (perilaku lama, `_dataneed_findings`):** sesi yang sudah menjalankan kode tapi tidak
      diselesaikan memblokir jawaban walau sesi pengganti COMPLETED, kecuali model menutupnya dengan
      `close_session_id`; j2 yang valid dipaksa LIMITATION. Usulan: sesi tanpa completion tidak memblokir bila ada
      sesi lain di run itu yang COMPLETED dan jawaban tidak merujuk output sesi yang ditinggalkan (atau orc menutup sesi
      lama otomatis saat formulir data dikirim ulang).
    - **F2 tingkat kepercayaan "95%" ditolak PROVENANCE:** checklist meminta rentang, model menulis "selang kepercayaan
      95%"; angka 95 bukan dari tabel. Usulan: tingkat kepercayaan standar (90/95/99%) yang ditulis berdampingan dengan
      "kepercayaan"/"confidence" dianggap konstanta yang sah.
- **Panjang adaptif (2026-10-14, user: "Ok, masukan exec"; belum dikerjakan, menunggu go atas rencana di bawah):**
  - **Yang mengatur panjang selain level penalaran:** instruksi yang menyesuaikan panjang dengan kompleksitas
    (prompt sistem Claude: jawaban ringkas untuk pertanyaan sangat sederhana, menyeluruh untuk pertanyaan kompleks dan
    terbuka), contoh di prompt, struktur wajib, dan parameter `verbosity` OpenAI (terpisah dari `reasoning.effort`;
    tidak didukung endpoint DeepSeek di OpenRouter, lihat EXEC-STYLE). Praktik: BLUF (kesimpulan dulu) dan
    progressive disclosure (detail lanjutan ditawarkan, tidak dipaksakan).
  - **A, router menilai kedalaman:** field `depth` di router pesan pertama: `ringkas` (pertanyaan satu angka atau
    satu fakta), `standar` (default), `dalam` (pengguna meminta analisa lengkap atau pertanyaan berlapis). Target:
    ringkas, jawaban sekitar enam ratus karakter, metodologi satu kalimat, asumsi dan batasan paling banyak satu;
    standar, sekitar dua setengah ribu karakter, asumsi dan batasan masing-masing paling banyak tiga poin pendek,
    metodologi ringkas; dalam, jawaban lebih panjang dengan metodologi empat bagian lengkap.
  - **B, aturan kalibrasi di catatan jalur cepat:** panjang mengikuti kompleksitas; jawaban utama tidak dipangkas
    (angka kunci, tabel inti, penjelasan pendorong); asumsi dan batasan tidak mengulang isi jawaban.
  - **C, override pengguna:** kata "singkat", "ringkas", "detail", "lengkap" di pesan menang atas penilaian router;
    nanti tombol di frontend (terpisah, belum dikerjakan).
  - **D, metodologi sebanding kedalaman:** menggantikan kewajiban empat bagian di jalur cepat saja.
- **Review benturan dengan EXEC dan arsitektur (2026-10-14, read-only):**
  - **Butuh persetujuan user, EXEC-STYLE S4:** panjang bertingkat per jenis langkah pernah dicoba dan dibatalkan
    (user memilih Run A, satu target sekitar dua setengah ribu karakter). Panjang adaptif berbeda (kedalaman per
    pertanyaan, dinilai router, hanya jalur cepat, di balik saklar), tetapi menyentuh keputusan yang sama. Jalur
    Standar tetap Run A.
  - **Tidak berbenturan, EXEC-STYLE S3:** asumsi dan batasan sudah tidak wajib; batas tiga poin hanya membatasi poin
    yang ditulis AI. Baris yang ditulis sistem (jalur analisis, bukti uji, angka tanpa sumber) tidak dihitung.
  - **Tidak berbenturan, prompt sistem:** `METHODOLOGY_RULES` (empat bagian) dan aturan 13 ada di prompt sistem bersama
    (semua jalur, prefix cache, tes pass 2 melarang digit baru). Perubahan ditulis di catatan jalur cepat (pesan
    user, di luar prefix cache) dalam kata-kata, seperti `EXPLORE_ANSWER_NOTE`. Gerbang METHODOLOGY hanya memeriksa
    ada atau tidaknya catatan dan sumber angkanya, bukan empat bagian, jadi metodologi ringkas tetap lolos.
  - **Perlu diputuskan bersama, Perbaikan 2 (field `insight` router):** `depth` dan `insight` sama-sama mengubah
    skema dan instruksi router pesan pertama (dipakai semua jalur; `AI_ROUTER.md` diregenerasi, benchmark router
    wajib). Usulan: digabung dalam satu perubahan router dan satu benchmark (hemat biaya); field baru hanya dibaca
    jalur cepat.
  - **F1:** sudah ada `closed_by_model` (model menutup sesi lewat `close_session_id`); F1 menambah kasus sesi yang
    ditinggalkan tanpa ditutup. Hanya `_dataneed_findings`, tanpa prompt. Jalur riset tidak tersentuh.
  - **F2:** temuan: catatan metodologi **sudah** menerima literal kode (`_methodology_gate` menambah
    `state.code_numbers` ke indeks), jadi B2 hanya perlu untuk teks jawaban (gerbang PROVENANCE hanya memeriksa
    `final.answer`). Mekanisme saran yang ada (R3, menu alamat, M140, EXEC-DERIVED, P25) tidak diubah. Label B1/B2
    tidak mengubah label bukti jawaban.
  - **Temuan sampingan (bukan bagian rencana):** di gerbang PROVENANCE jalur lama (non-DataNeed),
    `_derived_hint` ditambahkan dua kali ke instruksi penolakan (petunjuk turunan ditulis ganda). Tidak memengaruhi
    jalur cepat; diperbaiki hanya bila disetujui.
- **Keputusan atas rencana (2026-10-14, user: "Yg lain sudah OK.. konfirmasi dan buat execution plan"; rencana
  disetujui, dikerjakan):**
  - **Ditunda:** panjang adaptif A–D ("Ini nanti saja deh"; "no need for now") dan Perbaikan 2 (`insight` router),
    karena disetujui digabung ke perubahan router yang sama.
  - **Prioritas:** "Pastikan asumsi, limitasi, dan metodologi tidak mengambil porsi mayor dalam setiap balasan
    terlebih dahulu" (A/B v2: ketiganya 56% teks, jawaban utama 45%).
  - **Cakupan:** F1 dan F2 hanya jalur cepat; label F2 sebagai baris sistem terlipat di Asumsi; temuan sampingan
    (petunjuk turunan ganda di gerbang PROVENANCE jalur lama) diperbaiki ("ya perbaiki").
  - **Rencana eksekusi:** (1) F1 di balik `AI_FASTLANE_ABANDONED_SESSIONS`: sesi tanpa completion tidak memblokir bila
    ada sesi lain COMPLETED (sesi tanpa completion tidak merilis output, jadi tidak bisa dikutip); (2) F2 di balik
    `AI_FASTLANE_CONVENTION_NUMBERS`: B1 dan B2 diterima tanpa putaran dengan label, sisanya tetap ditolak; (3) batas
    bagian di balik `AI_FASTLANE_SECTION_CAPS`: kalimat di catatan jalur cepat (asumsi dan batasan masing-masing paling
    banyak tiga poin pendek tanpa mengulang jawaban, metodologi satu paragraf pendek; jawaban utama tetap lengkap),
    tanpa pemotongan kode dan tanpa gerbang baru; log `ai_answer_sections` mengukur porsi (kriteria A/B: porsi tiga
    bagian di bawah porsi jawaban utama, rata-rata sekitar 35% atau kurang); (4) petunjuk ganda dihapus. Prompt sistem
    dan jalur Standar tidak berubah. A/B 4–5 pertanyaan jalur cepat dengan baseline run v2 (≈ USD 0,15).
- **F1, F2, batas bagian dikerjakan (2026-10-14):** `main` `798dad1`; orc dev `0981b6c7` SUCCESS, saklar
  `AI_FASTLANE_ABANDONED_SESSIONS`, `AI_FASTLANE_CONVENTION_NUMBERS`, `AI_FASTLANE_SECTION_CAPS` menyala (redeploy
  `a7d55636` SUCCESS, dibaca ulang). Tes orc 1.498 lulus, 259 dilewati. Catatan bangun: (a) parser angka sudah
  menutupi "selang keyakinan 95%" dan "interval kepercayaan 95%" (P28 D); B1 menambah urutan lain ("95% selang
  kepercayaan", "batas kepercayaan 95%", "selang 95%"); jendela konteks 20 karakter sebelum dan 12 sesudah angka;
  (b) setiap tempat angka ditulis harus berdampingan dengan kata jenisnya; (c) log `ai_answer_sections` hanya di jalur
  cepat (jalur Standar tetap identik). Penolakan "36%" o1 kemungkinan hitungan turunan (kelas C, belum diverifikasi; teks drafnya tidak tercatat), tetap ditolak.
  **A/B belum dijalankan:** sisa kunci USD 0,09, di bawah perkiraan USD 0,13–0,15; menunggu keputusan user.
- **A/B F1, F2, batas bagian (2026-10-14, user: "Jalankan untuk A/B masukan exec"):** saklar menyala, orc
  `a7d55636`; runner `f20c6a39`, suite `gates_20261014_s1` (prefix `ma-gates-20261014-s1`), pertanyaan identik dengan
  v2, jalur cepat, DeepSeek Tinggi; baseline = run v2 (`ma-jawab2-20261014-v2`). Tahap 2 (j2, F1) **tidak dijalankan**:
  tahap 1 menghabiskan USD 0,083 (o1 saja 0,047, v2 0,007) dan sisa kunci tinggal USD 0,007.

  | Item | Waktu v2 → baru | Penolakan gerbang v2 → baru | Jawaban utama (karakter) | Porsi asumsi+batasan+metodologi tulisan AI | Porsi semua bagian (termasuk baris sistem) |
  |---|---|---|---|---|---|
  | t1 net beli asing → return 5 hari | 111 s → 220 s | PROVENANCE "95%" → tidak ada | 1.723 → 1.919 | 0,51 → 0,42 | 0,62 → 0,54 |
  | o1 volatilitas BBRI Q3 vs Q2 | 58 s → 113 s | PROVENANCE "36%" → UNITS (gagal diperbaiki, dianotasi) | 1.758 → 2.059 | 0,48 → 0,43 | 0,55 → 0,52 |
  | o2 normalitas return TLKM | 119 s → 66 s | tidak ada → tidak ada | 2.380 → 1.874 | 0,35 → 0,39 | 0,45 → 0,49 |

  - **Batas bagian, efek sebagian:** rata-rata porsi bagian tulisan AI 0,45 → 0,41; asumsi AI paling banyak 3 (patuh);
    batasan AI masih 4–5 poin (batas 3 tidak dipatuhi); metodologi 720–970 karakter (belum "satu paragraf pendek");
    jawaban utama rata-rata tidak memendek (1.954 → 1.951). Kriteria rata-rata ≤ 35% **tidak tercapai**. Baris yang
    ditulis sistem sendiri 370–510 karakter (sekitar 10–13% balasan).
  - **F2 belum teruji live:** tidak ada penolakan PROVENANCE di ketiga run (v2: dua), tetapi `ai_provenance_accepted`
    tidak pernah muncul: model menulis "interval kepercayaan 95%", yang sudah ditutup parser lama (P28 D). Perbaikan
    ini tidak bisa diatribusikan ke F2; F2 hanya terbukti lewat tes.
  - **F1 belum teruji live** (tahap 2 dilewati karena saldo); terbukti lewat tes.
  - **o1 UNITS:** model menulis rujukan berformat poin persen ke kolom selisih bootstrap tanpa `units`; gerbang menolak
    sekali (benar: satuan tidak diketahui), perbaikan model tidak menyatakan satuan, sel tabel tampil "–" dan
    dianotasi. Bukan regresi dari perubahan ini; prosa jawaban tetap menulis "−1,00% poin persentase" dengan
    intervalnya.
  - **Waktu:** 2 dari 3 ≤ 3 menit (o1, o2); t1 lebih lama karena satu kode gagal dan diperbaiki. Satu run per
    pertanyaan, jadi variasi waktu antar-run besar.
  - **Saklar tetap menyala** (tidak ada regresi gerbang atau satuan). Langkah berikutnya butuh go: batasan dan
    metodologi belum cukup pendek hanya dengan catatan; opsi yang bisa diusulkan sesudah saldo diisi: target panjang
    metodologi dalam kata-kata, atau menggabungkan baris sistem yang tumpang tindih.
- **Saran di penolakan (2026-10-14, user: "OK" atas tiga usulan sesudah audit gerbang):** audit: TYPED_FIGURES (R3
  otomatis + kandidat M140), REFERENCE (alamat dengan field sama), METHODOLOGY_PROVENANCE (literal kode otomatis + saran
  turunan) sudah memberi saran; PROVENANCE DataNeed dan UNITS belum. Dikerjakan (tanpa saklar; hanya isi pesan
  penolakan, gerbang yang menolak tetap sama):
  1. **Bug EXEC-DERIVED:** saran hitungan turunan (`_derived_hint`) tertempel dua kali di gerbang jalur lama dan tidak
     pernah ada di gerbang PROVENANCE DataNeed (yang aktif di dev, jalur Cepat dan Standar). Sekarang ada di gerbang
     DataNeed; tes `test_the_dataneed_provenance_refusal_names_the_derived_reference` gagal pada kode lama.
  2. **Penolakan UNITS menyarankan:** dugaan dari nilai rujukan (desimal: |pct untuk porsi, |x atau |dec untuk rasio,
     selisih porsi dalam poin persen butuh `units='FRACTION'` lalu |pp; nilai besar: |pctv atau |x) dan, untuk sel
     baris tabel, cara memisah kolom bersatuan campuran (kasus o1 `ma-gates-20261014-s1`). Tetap tebakan, AI memutuskan.
  3. **Pesan galat `emit_table` di sandbox memberi contoh:** `units` bukan dict dan `units[...]` tidak sah (kolom yang
     bukan porsi/persen/p-value tidak dideklarasikan; kolom campuran dipecah per satuan), `definition['thresholds']`
     bukan dict (contoh dan tipe yang diterima).
  - **Deploy:** `main` `bacc2e9`; orc `b065fe2d` dan sandbox `a088cbd0` SUCCESS. Tes orc 1.500 lulus; sandbox per file
    lulus kecuali 2 kegagalan lama. Belum terbukti live (saldo kunci).
- **Analisis langkah "menulis permintaan data" t1 v2 vs v3 (2026-10-14, dari log penalaran, tidak dikutip):** data dan
  catatan sama; v2 memutuskan metode lebih awal dan menimbang helper `event_study` sesudah data siap, v3 menimbang
  helper vs kode sendiri, tumpang tindih, holdout dan buffer sebelum mengirim permintaan data, menulis spesifikasi dua
  kali (di penalaran lalu di pemanggilan alat), lalu tetap membuka panduan `event_study`. Penyebab: catatan Mode Jawab
  membiarkan pilihan helper terbuka tanpa menyebut kapan diputuskan. Usulan **disetujui** (user 2026-10-14: "OK
  masukan exec"; belum dikerjakan): satu kalimat di `EXPLORE_ANSWER_NOTE` — tentukan metode setelah data siap;
  permintaan data cukup memuat kolom, periode dan buffer yang dibutuhkan pertanyaan — ditambah ringkasan cara
  `saniti.event_study` memakai dua permintaan (kondisi di satu permintaan, harga hasil di permintaan lain lewat
  `'request'`), supaya AI tidak menebak. Tugas lanjutan dari user: cari titik lain tempat AI diberi pilihan terbuka
  ("menawarkan") dengan sifat serupa.
- **V4: aturan memutuskan di jalur Cepat + 4 perbaikan EDGE (2026-10-14, user: "save ini as V4 in addition to
  approved EXEC"; rencana disetujui; dikerjakan):** audit log 41 run jalur Cepat (859 potongan penalaran) menemukan
  instruksi yang hanya "menawarkan" pilihan tanpa aturan memutuskan. Keputusan per butir:
  - **A disetujui (versi 2, user: "pakai helper apabila cocok, fall back ke default AI"):** metode diputuskan sesudah
    data siap; helper dipakai bila bentuk pertanyaan cocok (kejadian → return ke depan: `event_study`; metode
    library: `explore_test`; return periode bernama: `period_return`), selain itu kode AI sendiri; ringkasan
    `event_study` dengan dua permintaan.
  - **B1 disetujui:** desain kejadian → hasil: permintaan harga tidak dibatasi INNER join (LEFT dengan harga di kiri,
    atau tanpa relasi dan digabung di sesi), agar jendela hasil tidak terpotong.
  - **B2 disetujui:** periode default = cakupan tabel paling pendek (dibatasi tahun riwayat default) sampai LATEST;
    rentang nyata dibaca dari ringkasan bundle.
  - **C disetujui (user: "kasih nama tablenya dan harus di update di agents MD karna user perlu tweak"):** parameter
    yang tidak disebut user memakai tabel `FASTLANE_DEFAULTS` di `apps/market-ai-orc/app/fastlane_defaults.py`
    (pilihan user: file kode, bukan tabel DB atau variabel Railway); cara mengubahnya di AGENTS.md.
  - **D disetujui:** satu aturan rujukan (kolom ber-`units=` → `{{ref}}` tanpa format; tabel lewat `{{table …}}`;
    jawaban sesudah `complete_analysis`).
  - **E disetujui (parameter, sama seperti C):** `check_data_feasibility` sekali bila entitas × tahun melewati batas
    di `FASTLANE_DEFAULTS`; ulang hanya bila spesifikasi berubah.
  - **F disetujui:** panduan metode dibuka hanya untuk helper yang akan dipakai.
  - **G dilewati** (user: "NO, skip this").
  - **H disetujui:** kurang kolom/periode → permintaan data baru + `close_session_id`; galat kode → perbaiki di sesi.
  - Saklar `AI_FASTLANE_DECISION_RULES` (default mati), hanya jalur Cepat; prompt sistem bersama tidak diedit. Dua
    kontradiksi instruksi (catatan jalur "tanpa uji formal" vs Mode Jawab; konvensi `period_return` vs rentang
    bebas) dicatat, belum disetujui.
  - **EDGE:** (1) tombol perbesar tabel jawaban → dialog lebar penuh seperti contoh screenshot; (2) di HP tombol
    Kembali/Enter menambah baris baru, bukan mengirim; (3) hapus teks "Kirim balasan langsung" di kartu pilihan;
    (4) hilangkan celah antara status "AI request running" di percakapan dan kotak pesan.
  - **Dikerjakan (2026-10-14):** orc `main` `e96244a` (`FASTLANE_DECISIONS_NOTE`, `EXPLORE_ANSWER_HELPERS_V4`,
    `app/fastlane_defaults.py`; nilai awal dari pilihan AI paling sering di log: persentil 90 sebanyak 133 kali, jendela
    21 hari bursa 48 kali, riwayat 5 tahun 61 kali; horizon 5 hari bursa; batas cek ukuran 100 entitas-tahun); EDGE
    `7a48df3`. Temuan saat membangun: aturan D yang benar adalah `|pct` (satuan kolom menentukan skala), bukan "tanpa
    format" (format otomatis menampilkan pecahan 0,123); dialog tabel di dalam jawaban tertutup bar atas dan kotak
    pesan di HP, jadi dirender dari akar aplikasi; celah HP terukur 60 px (22 + 32 + 6) menjadi sekitar 14 px.
    Tes: orc 1.503 lulus; EDGE 87 lulus (4 tes baru). Deploy: orc `c64f8401` SUCCESS, edge-bff `15b7178a` SUCCESS;
    `AI_FASTLANE_DECISION_RULES=true` (redeploy orc `34cd841f` SUCCESS, dibaca ulang). EDGE live menyajikan kode
    baru (dicek lewat file statis). Uji live backend menunggu saldo kunci (sisa USD 0,007).
- **V4.1: dua kontradiksi instruksi (2026-10-14, user: "5 hari kerja, senin-jumat"; lalu "5 hari bursa terakhir" dan
  "semua hari bursa"; dikerjakan di bawah saklar V4 `AI_FASTLANE_DECISION_RULES`):** log 41 run: 64 paragraf/16 run
  menimbang kalimat "tanpa uji formal", 71 paragraf/20 run menimbang konvensi periode bernama.
  - **Kontradiksi 1:** kalimat "hasil eksploratif tanpa uji formal… tawarkan uji formal" dibedakan per mode: Mode
    Jawab: uji yang dihitung AI tidak diperiksa ulang sistem; laporkan efek, selang, uji, sampel efektif; tawarkan
    studi terverifikasi hanya bila pengguna bertanya apakah terbukti. Mode Insight: klaim pola hanya dari uji
    `explore_test` yang dicatat dan dikoreksi sistem. Tanpa saklar uji: kalimat lama.
  - **Kontradiksi 2:** periode kalender bernama (YTD, bulan/kuartal/tahun bernama) tetap `period_return`; rentang
    relatif bergulir dalam hari bursa dari tanggal data terakhir: 1 minggu = 5, 1 bulan = 21 (3 bulan = 63), 1 tahun =
    252; dasar = penutupan N hari bursa sebelum tanggal terakhir; tanggal awal-akhir ditulis di asumsi. Nilai di
    `FASTLANE_DEFAULTS` (`span_*_trading_days`, AGENTS.md). Prompt sistem (`PERIOD_RETURN_RULES`) dan jalur Standar
    tidak berubah.
  - **Deploy:** `main` `e0ac8d6`, orc `90e26804` SUCCESS; aktif lewat saklar V4 yang sudah menyala. Tes orc 1.504
    lulus. Uji live menunggu saldo kunci.
- **A/B V4 + V4.1 (2026-10-14, user: "lakukan a/b tes 3 pertanyaan targetted to test speed and depth"):** tiga
  pertanyaan sama, jalur Cepat, DeepSeek Tinggi; ON = `AI_FASTLANE_DECISION_RULES=true` (orc `90e26804`), OFF = false
  (orc `def768d5`), saklar lain sama; saklar dikembalikan ON (orc `186a63c3`). Runner ON `808f6dae`, OFF `6288cc44`
  (`ma-v4-20261014-on/off`). Biaya total ≈ USD 0,25 (sisa kunci USD 0,74).

  | Pertanyaan | Waktu ON / OFF | Token output ON / OFF | Pertimbangan ulang ON / OFF | Server (token/s) ON / OFF |
  |---|---|---|---|---|
  | t1 net beli asing "besar" → return 5 hari | 195 s / 231 s | 11.274 / 15.942 | 22 / 35 | 74 / 79 |
  | j2 akumulasi broker → >10% dalam 20 hari | 167 s / 570 s | 24.185 / 35.532 | 118 / 206 | 191 / 73 |
  | s1 return 3 bank 1 minggu dan 3 bulan + pendorong | 401 s / 294 s | 27.220 / 29.659 | 105 / 82 | 74 / 114 |
  | **Total** | 763 s / 1.095 s | 62.679 / 81.133 (−23%) | 245 / 323 (−24%) | |

  - **Kecepatan:** token output dan pertimbangan ulang turun sekitar seperempat; waktu mengikuti server yang dipilih
    OpenRouter (s1 ON kena server 74 token/s, OFF 114). Dengan kecepatan server yang sama, ketiga pertanyaan ON lebih
    sedikit waktu model.
  - **E bekerja:** j2 ON 1 cek ukuran dan 1 permintaan data; OFF 4 cek ukuran, 2 permintaan data dan 2 sesi.
  - **V4.1 bekerja:** s1 ON dasar 1 minggu = 7 Okt (5 hari bursa), 3 bulan = 13 Juli (63 hari bursa), tanggal ditulis
    di tabel dan asumsi; OFF memakai rentang kalender dan menulis return 3 bulan BBCA 0,00% (dicurigai salah dasar;
    ON −1,61% dari Rp 6.225 ke Rp 6.125).
  - **C sebagian:** t1 dan j2 ON memakai persentil 90 dan jendela 21 hari; s1 ON memilih ambang "besar" sendiri
    (Rp 0,5 triliun) alih-alih persentil 90.
  - **F2 bekerja live:** "95%" diterima otomatis di t1 dan j2 (`ai_provenance_accepted`).
  - **Kedalaman:** t1 ON lebih ringkas (1.486 vs 2.933 karakter; OFF menambah 10 hari terbesar dan rincian per tahun);
    j2 ON lebih panjang (2.272 vs 1.958); s1 setara. Porsi bagian ON 0,47–0,62.
  - **Temuan baru:** (a) gerbang METHODOLOGY_PROVENANCE masih menolak "95%" (F2 hanya untuk teks jawaban); (b) gerbang
    TYPED_FIGURES menolak "21" (parameter jendela default yang juga muncul di tabel hasil) dan "34" (jumlah hari);
    (c) baris "Pilihan AI" memuat string kode ('forward', 'explore') — bug lama; (d) tabel per tahun OFF menulis tahun
    "2.020" (format ribuan pada kolom tahun) — bug lama tampilan angka.
- **V5 (2026-10-14, user; belum dikerjakan, rencana implementasi menyusul):**
  - **Gerbang mode saran (jalur Cepat):** user: "gerbang angka yang diketik dan lain sebagainya perlu kita buat
    seminimal mungkin. Sehingga sifatnya hanya suggestion terhadap AI". Kondisi sekarang: semua gerbang angka menolak
    satu putaran (TYPED_FIGURES 7, PROVENANCE 3, METHODOLOGY_PROVENANCE 3, UNITS 1, REFERENCE 1 di 18 run terakhir;
    3–21 detik per putaran). Arah: sistem memperbaiki sendiri bila aman (angka diketik, satuan dari nama kolom), lolos
    dengan label (metodologi, rujukan salah), saran dimasukkan sebelum AI menulis. **PROVENANCE pilihan (a)** (user:
    "untuk preference saya pilih A"): satu putaran hanya untuk angka yang tidak cocok dengan apa pun; angka turunan dan
    parameter otomatis diterima dengan label.
  - **Format tanggal (semua jalur, tampilan):** user: "tahun 4 digit, bulan disebutkan bulannya", pilihan "7 Oktober
    2026": `2026-10-07` → "7 Oktober 2026", `2024-09` → "September 2024"; kolom tahun tanpa pemisah ribuan (bug
    "2.020").
  - **Satuan pp → %** (user: "untuk masalah PP diganti persentase saja", dicek visual sesudahnya): format rujukan `|pp`
    (`value_refs.py`) ditampilkan dengan "%" alih-alih " pp". Risiko yang sudah disampaikan: selisih poin persen bisa
    dibaca sebagai perubahan relatif.
  - **EDGE HP: klik respons yang di-pin** di panel Details/filter → panel tertutup dan percakapan langsung bergulir ke
    respons itu. **Kirim pertanyaan saat sedang scroll di atas** → percakapan otomatis bergulir ke bawah ke pertanyaan
    baru (sekarang harus scroll sendiri).
  - **Menu model di HP** memenuhi layar dan terpotong rel kiri (screenshot): jadikan lembar bawah lebar penuh di lapisan
    teratas, tinggi maksimal dengan scroll.
  - **Kuota Run 7:** tidak ada panggilan model agen tercatat sebelum terputus (paling banyak satu panggilan router).
  - **Run terputus macet "Recovering delivery" (Run 7 `edge_87c7…`, terputus oleh deploy ulang A/B V4 pukul 17:29
    UTC):** lease orc 62 menit dan pemeriksaan per jam membuat giliran tetap RUNNING sampai sekitar satu jam. Disetujui
    (user: "saya terima untuk yang A dan C"): (A) orc menandai giliran milik proses yang mati segera saat start;
    (C) tombol stop di EDGE menandai run terputus bila orc menjawab tidak ada yang berjalan, kotak pesan dibuka lagi.
    Penghentian manual Run 7 disetujui ("Boleh diinterrupted") tetapi tidak bisa dari sesi ini: koneksi TCP ke
    database diblokir kebijakan jaringan sesi dan `railway ssh` butuh kunci SSH di akun; Run 7 lepas sendiri saat
    lease habis (≈ 18:32 UTC) lewat batas EDGE (≈ 18:36 UTC) atau pemeriksaan orc berikutnya.
  - **Tugas berikutnya (user):** cari akar masalah penolakan gerbang: dari 10 run terakhir, urutkan gerbang yang paling
    sering menolak, lalu cek di log apakah AI tidak tahu gerbangnya, salah mengira, atau tidak tahu cara lolos
    (instruksi kurang jelas).
- **Akar masalah penolakan gerbang (2026-10-14, user: "kenapa AI itu at the first place bisa salah?"; 10 run terakhir:
  V4 ON 3, V4 OFF 3, `ma-gates-20261014-s1` 3, live `edge_e6cce…` 1; log penalaran dibaca, tidak dikutip):**

  | # | Penolakan | Jumlah (run) | Apakah AI tahu aturannya? | Akar masalah |
  |---|---|---|---|---|
  | 1 | `get_dimension_values` di tabel bertanggal | 4 (3) | Tahu ("hanya tabel statis") tetapi mencoba "karena murah" | Tidak ada jalan lain untuk memastikan nilai `market_board` = 'Regular'; celah informasi |
  | 2 | Kode gagal (`SCRIPT_ERROR`, `units` None, format `definition`) | 3 (3) | Tahu fungsinya, salah bentuk argumen | Contoh format tidak ada (sudah diperbaiki di pesan galat 2026-10-14) |
  | 3 | Cek ukuran data `NOT_FEASIBLE` / kunci relasi | 3 (1, OFF) | Tahu | Tanpa aturan V4 E; tidak muncul di ON |
  | 4 | Angka diketik (TYPED_FIGURES): "21", "34", "Rp500 miliar" | 2 + 2 ulang (2) | Tahu aturan rujukan, tetapi menganggap parameter (jendela 21 hari dari tabel default V4), hitungan hari (34) dan ambang pilihannya sendiri bukan "angka data" | Definisi gerbang (angka apa pun yang sama dengan nilai rilis) berbeda dari anggapan AI; pesan tidak menyebut letak kalimatnya, sehingga perbaikan "21" gagal dua kali (AI tidak menemukannya) |
  | 5 | `submit_data_need_spec` `INVALID_SCOPE` | 2 (2) | Tahu, salah bentuk | Skema scope AND membingungkan (`children` diisi, `child` harus null); diperbaiki sekali |
  | 6 | Angka di metodologi "95%" | 1 | Tahu | F2 hanya mencakup teks jawaban; AI menghapus "95%" sehingga metodologi kurang informatif |
  | 7 | UNITS kolom satuan campuran | 1 | Tahu | Aturan satuan per kolom tidak bisa dipenuhi untuk tabel uji campuran |
  | 8 | `get_method_guide('explore_test')` UNKNOWN_METHOD, sumber insight belum dibuka | 2 (2) | Ragu | Catatan menyebut helper tetapi rincian perannya tidak ada di panduan |

  Kesimpulan: hampir tidak ada kasus "AI tidak tahu ada gerbang". Polanya: (a) definisi gerbang berbeda dari anggapan AI
  (parameter, hitungan, ambang sendiri dianggap bukan data), (b) pesan penolakan tidak menyebut letak dan cara lolos,
  (c) celah informasi yang memaksa AI mencoba (nilai dimensi, peran helper), (d) bentuk argumen alat yang membingungkan
  tanpa contoh. Masukan untuk V5: gerbang angka diketik dan metodologi menjadi saran/otomatis, angka parameter dan
  hitungan hari diterima sebagai parameter, pesan menyebut kalimat, contoh skema scope AND, nilai dimensi umum
  (`market_board`) ditulis di katalog/catatan.
- **V5 tambahan (2026-10-14, user: "Saya setuju untuk semuanya dengan catatan jawaban limitation tetap ditampilkan
  sebagai batasan… keep as is untuk jalur standar"):**
  - **Batasan disembunyikan, hanya jalur Cepat:** sumbernya: baris sistem (keterangan cakupan, sumber angka, bukti uji;
    17 baris di 6 jawaban A/B) dan tulisan AI (30 baris, rata-rata 5 walau dibatasi 3). Jawaban jalur Cepat
    menampilkan Metodologi dan Asumsi saja; "Bukti statistik" dan peringatan angka tanpa sumber pindah ke Asumsi;
    keterangan cakupan/sumber angka dihapus (sudah di label bukti); catatan jalur Cepat: AI tidak menulis
    limitations, keterbatasan material ditulis di jawaban atau asumsi. **Jawaban LIMITATION tetap menampilkan
    Batasan.** Jalur Standar tidak berubah.
  - **Solusi akar masalah #4 disetujui:** angka parameter, hitungan hari dan ambang pilihan AI diterima sebagai parameter
    (bukan angka diketik); pesan gerbang menyebut kalimat tempat angka ditulis.
  - **Solusi akar masalah #5 disetujui:** contoh skema filter AND (children diisi, child null) di catatan/deskripsi alat.
  - **#1 `get_dimension_values` di tabel bertanggal: opsi 1 disetujui** (user: "please proceed for option one"):
    akar masalah: database sudah punya daftar nilai (CHECK constraint `Feature_03_Stock_Broker_Daily_board_check`:
    Regular, Nego, Tunai), kontrak katalog Governor membacanya (`value_domains`) dan sandbox memakainya untuk validasi
    filter, tetapi `get_catalog_details` orc tidak menampilkannya ke AI. Perbaikan (jalur Cepat, tanpa migrasi):
    bagian COLUMNS menampilkan daftar nilai kolom yang punya CHECK list, dan catatan jalur Cepat menyebut bahwa nilai
    sah ada di detail katalog (tidak memanggil `get_dimension_values` untuk tabel bertanggal). Praktik terbaik:
    kolom bernilai sedikit dan tetap = daftar lengkap di katalog (Snowflake `sample_values` + `is_enum`); opsi 3
    (pencarian nilai di tabel bertanggal) disimpan untuk kolom teks bernilai banyak tanpa tabel referensi, sesudah
    bukti beban kueri (EXPLAIN).
- **V5 dikerjakan (2026-10-14, user: "please review current exec… proceed end to end"):** perilaku AI/jawaban hanya
  jalur Cepat dan di balik saklar (default mati, bisa dimatikan lagi); bug UI/infra berlaku umum.
  - **orc, saklar `AI_FASTLANE_GATE_ADVICE`:** TYPED_FIGURES, UNITS dan REFERENCE tidak meminta putaran perbaikan
    (`_gate_once`, alasan log `advice_mode`; perbaikan dan label sistem tetap jalan); angka metodologi lolos (log
    `ai_gate_advised`); PROVENANCE pilihan (a): literal kode yang berhasil → "parameter dari kode", angka dengan satu
    bacaan turunan → "hitungan dari hasil" (label di Asumsi); angka yang tidak cocok apa pun tetap satu putaran dan
    pesannya mengutip kata di sekitarnya ("Written in: …", akar masalah #4).
  - **orc, saklar `AI_FASTLANE_V5_PRESENTATION`:** jawaban ANSWER jalur Cepat tanpa Batasan: baris cakupan, sumber angka
    dan jalur analisis dihapus, baris lain (bukti uji, angka tanpa sumber, catatan AI) pindah ke Asumsi (log
    `ai_limitations_folded`); LIMITATION tetap punya Batasan. `|pp` tampil "%". Catatan presentasi: limitations
    kosong, selisih persen ditulis dengan %; batas "tiga limitations" di catatan bagian dihapus saat saklar hidup.
  - **orc, ikut saklar V4 `AI_FASTLANE_DECISION_RULES`:** aturan (9) nilai kategori dari `column_values` di detail
    katalog, tanpa `get_dimension_values` di tabel bertanggal; aturan (10) contoh scope AND (lolos validasi skema
    `ScopeNode`, termasuk `children`/`child` null di predikat). `get_catalog_details` COLUMNS (v1 dan v2) memuat
    `column_values` dari CHECK list satu kolom (`pg_constraint`), hanya di jalur Cepat.
  - **orc, run terputus (A), saklar `AI_CONVERSATION_RESTART_SWEEP_SECONDS` (0 = mati):** sekian detik sesudah start,
    giliran RUNNING yang dibuat sebelum proses ini start ditandai INTERRUPTED (`PROCESS_RESTARTED`) dan lease dilepas
    (log `conversation_restart_sweep`). Jeda dipakai supaya kontainer lama selesai berhenti saat deploy.
  - **EDGE:** jawaban jalur Cepat (`execution.lane = fast`): `2026-10-07` → "7 Oktober 2026", `2024-09` → "September
    2024", kolom Tahun "2.020" → "2020" (jawaban, asumsi, metodologi; kode, tautan dan jam tidak disentuh; bulan
    tertulis tetap terurut sebagai tanggal). Jalur Standar tidak berubah (catatan awal V5 menyebut "semua jalur";
    rencana yang disetujui membatasi ke jalur Cepat, bisa diperluas satu baris). Menu model di HP: lembar bawah lebar
    penuh, tinggi maks 72dvh dengan scroll, z-index di atas rel. Klik "View full response" di pin (HP): panel Details
    tutup lalu gulir ke respons. Kirim pertanyaan saat membaca di atas: langsung bergulir ke pertanyaan baru. Stop (C):
    run yang sudah dikirim tetapi orc menjawab tidak berjalan dan belum menyimpan jawaban → INTERRUPTED
    (`STOPPED_NOT_RUNNING`), kotak pesan terbuka lagi; bila orc sudah COMPLETED, tetap 409 (jawaban sedang dikirim).
  - **Tes:** orc 1.777+ lulus (3 galat `pyarrow` lingkungan lokal, sudah ada sebelumnya); tes baru di
    `test_fastlane.py` (14), `test_conversations.py` (2), `test_catalog_postgres.py` (2); EDGE `test_edge.py` (1) dan
    `test_v5_frontend.py` (4, tes gulir terbukti gagal tanpa perbaikan).
  - **Deploy dan A/B V5 (2026-10-14):** `main` `4e99848` (orc `049fb844`, edge-bff `71d4161d`, SUCCESS); saklar
    dinyalakan, redeploy orc `bf853494` SUCCESS; sweep live 19:20 UTC (0 giliran). A/B 3 pertanyaan sama dengan A/B V4
    (n=1 per pertanyaan; OFF = saklar V5 mati, V4 tetap hidup), 6/6 ANSWER:

    | Ukuran | V5 OFF | V5 ON |
    |---|---|---|
    | Penolakan gerbang yang meminta perbaikan | 4 (UNITS, PROVENANCE ×2, TYPED_FIGURES) | 0 (2 TYPED_FIGURES jadi label) |
    | Baris Batasan (t1/j2/s1) | 6/6/6 | 0/0/0 (pindah ke Asumsi 3/6/3, dibuang 2/1/1) |
    | "pp" di jawaban | 6/2/2 | 0/0/0 |
    | `get_dimension_values` | 0 | 0 |
    | Waktu total | 568 s | 644 s |
    | Biaya | USD 0,103 | USD 0,099 |

    Waktu ON lebih lama (+13%) bukan karena gerbang (tanpa putaran perbaikan): penyedia model berbeda (OFF sebagian
    besar Baidu, ON InferenceNet/AtlasCloud); keduanya lebih cepat dari V4 ON (763 s). Temuan: 2 dari 3 jawaban ON
    memuat label "Angka berikut diketik … tidak dibaca ulang" di Asumsi, karena angka diketik tidak lagi diperbaiki AI
    (keputusan lanjutan menunggu user). Format tanggal/menu/pin/gulir diverifikasi dengan tes browser (runner tidak
    merender EDGE); pengecekan visual oleh user.
  - **Kenapa V5 ON lebih lama (2026-10-15, user: "identify kenapa bisa lebih lama, contrast log"):** dari log orc per
    panggilan model (waktu panggilan, token keluaran, penyedia):

    | Bagian | V5 OFF | V5 ON |
    |---|---|---|
    | Waktu total (wall) | 569 s | 645 s |
    | Waktu model | 442 s | 517 s |
    | Di luar model (alat, sandbox, Governor) | 127 s | 128 s |
    | Token keluaran | 68,7 rb | 70,8 rb |
    | Penyedia (kecepatan) | t1 DigitalOcean 178 tok/s; j2, s1 Baidu 152 tok/s | t1 DigitalOcean 196; j2 InferenceNet 116; s1 AtlasCloud 138 tok/s |
    | Putaran ulang jawaban | 4 (gerbang: 39 s) | 1 (s1: JSON jawaban terpotong di tengah metodologi, `ai_final_reask`, 20 s) |

    Selisih 76 s seluruhnya di waktu model; waktu alat sama. Token ON di kecepatan penyedia OFF: j2 ≈ 159 s (nyata
    216 s, +57 s), s1 ≈ 205 s (nyata 226 s, +21 s), jadi penyedia yang lebih lambat menjelaskan ≈ 78 s; V5 menghemat
    ≈ 39 s putaran gerbang, tetapi s1 ON kehilangan 20 s karena jawaban JSON terpotong (masalah format, bukan V5).
    Per jenis pekerjaan (OFF → ON): katalog/rencana 121 → 132 s, data need 38 → 60 s (t1 ditolak sekali karena nama
    permintaan data `INVALID_REQUEST_ID`; s1 29,7 s berpikir sebelum data need), kode 175 → 216 s (panggilan terbesar:
    j2 60 s dan s1 61 s menulis kode analisis dengan 6,6 rb–7,6 rb token penalaran), jawaban 79 → 89 s. Kesimpulan:
    V5 tidak menambah kerja; penyedia OpenRouter yang dipilih per panggilan menentukan sebagian besar selisih (n=1).
  - **Opsi 2 (2026-10-15, user: "2 alright"):** dalam mode saran, angka diketik yang sama dengan literal kode → label
    "parameter dari kode"; angka yang sama dengan beberapa nilai hasil → dirujuk otomatis ke nilai yang barisnya
    disebut di kalimat yang sama (mis. "RB … 116" dan baris broker=RB, broker=YP); sisanya tetap berlabel angka
    diketik. Rujukan otomatis untuk satu nilai yang cocok (R3) sudah ada sebelumnya; label di A/B ON tersisa untuk
    "196, 90" dan "Rp1,5 triliun, 63, 9" (beberapa nilai cocok atau parameter). Tes:
    `test_v5_option_2_typed_figures_resolve_by_the_row_named_or_count_as_code_parameters`.
- **Review EXEC 2026-10-13, hubungan dengan entri lain:**
  - EXEC-D (jaminan "data hanya sesudah persetujuan"): tingkat 1 jalur baru mengambil data tanpa persetujuan untuk
    pertanyaan bergaya hipotesis, seperti jalur analisis sekarang. Ini penyimpangan sadar dari jaminan EXEC-D di jalur
    baru saja; vonis "terbukti" tetap hanya lewat tingkat 2 dengan persetujuan (K1: disetujui).
  - EXEC-MODELS (default EDGE DeepSeek Tinggi) dan EXEC-LOGOS (level Rendah/Tinggi/Maks, pengaman M150): R4 hanya
    mengatur level di dalam jalur baru; default EDGE tidak berubah.
  - EXEC-PROSE dan EXEC-DAYS (pra-cek draf): R6 hanya di jalur baru.
  - EXEC-W (`stop_policy`: jeda dan tanya): jalur baru memakai aturan jeda yang sama.
  - EXEC-UI-1013B: tampilan, berlaku untuk kedua jalur.
  - G3 dan G5 adalah bug yang juga ada di jalur sekarang (K2: diperbaiki di jalur sekarang lebih dulu).

### EXEC-UI-1013B: pilihan bernomor bisa diklik, logo model dan Excel di jawaban, pemantau run di iPhone (dikerjakan, Fase A)

**Keputusan user 2026-10-13:** gambar 1 "yes yg kamu bilang benar + Untuk angka ini boleh dikasih button atau clickable
feature agar mudah Setiap yang sifatnya pilihan angka.. So bisa pilih angka, atau jawaban user sendiri"; gambar 2 "Boleh
tambah logo AI nya disebelah kiri tulisan yang saya kotakin, dan logo excel juga disebelah kiri"; bug "AI is thinking"
sampai di-refresh: "Ok, masukan exec ya bersama gambar 1 dan gambar 2 diatas. Jangan execute dl".
- **A. Pilihan bernomor (gambar 1, run `edge_a912d6a1…`):** pertanyaan balik router (`text_choices=4`, `options=[]`)
  tampil dua kali dan opsinya hanya teks "① … Balas dengan nomor pilihan". Rencana: setiap pilihan bernomor (dari router
  atau dari jawaban AI) menjadi tombol di panel "Response choices" (EXEC-CHOICES), ditambah "Tulis jawaban lain";
  pertanyaannya tampil sekali; menekan tombol mengirim teks pilihan itu.
- **B. Logo (gambar 2):** logo model di kiri label `deepseek/deepseek-v4.1-flash · Tinggi` pada kepala jawaban (komponen
  logo EXEC-LOGOS dipakai ulang); logo Excel di kiri setiap tombol "Download …xlsx" (file lokal, CSP `img-src 'self'`).
- **C. Pemantau run di iPhone:** log HTTP EDGE menunjukkan koneksi `/events` dari iPhone putus beberapa detik setelah
  kirim dan tidak tersambung lagi sampai refresh (run `80e733ba`, `e5faf07f`, `a45f86c8`, `e886f12d`); iOS 18 tidak
  memicu `error` pada EventSource setelah aplikasi kembali dari background (Apple Developer Forums 765183). Komentar
  `: heartbeat` tidak terlihat oleh JavaScript. Rencana: server mengirim event `ping`; klien menyambung ulang atau polling
  bila tidak ada pesan dalam sekitar 2x interval; saat halaman terlihat lagi (`visibilitychange`/`pageshow`) klien
  menarik status run sekali.
- **Tes yang direncanakan:** tes browser untuk tombol pilihan bernomor dan "Tulis jawaban lain", logo di kepala jawaban
  dan tombol unduh (desktop dan HP), koneksi pemantau yang diam lalu pulih tanpa refresh.
- **Dikerjakan 2026-10-13 (rencana implementasi Fase A, disetujui):** Orc mengirim `mode4.question` dan `mode4.choices`
  pada pertanyaan balik; EDGE menampilkan pertanyaan sekali dan setiap pilihan sebagai tombol yang mengirim katanya,
  plus "Tulis jawaban lain"; logo model di kiri label model pada kepala jawaban; tanda Excel di kiri tombol unduh
  `.xlsx`; stream run mengirim `ping`, stream diam 15 s diganti, halaman yang terlihat lagi membaca status (M153).
  Tes: orc 1.467 lulus; EDGE 83 lulus (satu kali gagal di tes mengetik yang memang kadang gagal di main).
- **Deploy dan cek live (RAILWAY_CHANGELOG EXEC-PHASE-A):** orc `2e935d87` dan EDGE `cadcd89c` SUCCESS; rekap per minggu
  dirouting INSIGHT dan dihitung; ekspor tanpa penolakan DEFINITION. Menunggu cek user di iPhone (jawaban muncul tanpa
  refresh) dan tampilan pilihan bernomor pada pertanyaan balik berikutnya.

### EXEC-LOGOS: logo model di EDGE, level Rendah/Tinggi/Maks, MiMo Pro dikeluarkan, pengaman berpikir tanpa ujung (deployed; cek live bersih)

**Keputusan user 2026-10-13:** "kasih logo untuk setiap model ya di HP"; "Request edge_7bc93daf9e463c521e8886c00c219cd5
boleh cek kenapa lama, cek log"; logo "Logo merek asli"; level "Rendah / Tinggi / Maks"; MiMo "cek dulu
dokumentasinya"; setelah temuan log: "Keluarin saja Mimo pro ya, the rest sudah OK".
- **Temuan (M150):** panggilan pertama MiMo Pro 405 s, 23.999 token berpikir tanpa output (berputar pada "kemarin" 12
  atau 13 Okt dan pada lebar periode, lalu menulis seluruh kode di dalam pikiran sampai batas 24.000 habis). Jawaban
  keluar lewat pengulangan giliran kosong; panggilan 2 mulai dari nol dan memakai data 5 hari yang sudah ada.
- **Orc:** `app/model_choices.py` tanpa MiMo Pro (4 model); DeepSeek dan GLM `low/high/max` (`supported_efforts`
  OpenRouter); MiMo Flash Nyala batas output 12.000 per panggilan; Qwen Nyala `reasoning.max_tokens` 8000;
  `schemas.py` menerima `max`. `orchestrator.py`: panggilan loop yang kosong tepat di batas output diulang sekali dengan
  berpikir Mati (atau `low`) untuk satu panggilan itu, log `ai_reasoning_runaway`.
- **EDGE:** logo LobeHub (MIT, `static/model-logos/`, route `/model-logos/<nama>.svg`); di HP tombol hanya logo; logo
  satu warna (Z.ai, MiMo) mengikuti warna teks; label `max: "Maks"`; BFF menerima level `max`.
- **Tes:** orc 1.465 lulus; EDGE 80 lulus (termasuk tes HP baru).
- **Deploy dan cek live (RAILWAY_CHANGELOG EXEC-LOGOS):** orc `7c11b4ad` dan EDGE `865c2c8f` SUCCESS. MiMo Pro ditolak
  400 `MODEL_NOT_ALLOWED`. Pertanyaan M150 dengan MiMo Flash Nyala selesai 198 s (sebelumnya 826 s), panggilan terlama
  51 s, tanpa runaway; distribusi 70 sesi; biaya ±USD 0,03.

### EXEC-CHOICES dan EXEC-ROWS: panel "Response choices" di EDGE; jumlah baris tabel sesuai permintaan, maks. 25 (deployed)

**Keputusan user 2026-10-13:** lampiran `Selection_option_for_user.html` ("Jalankan terlampir dan cek terlampir. Lihat
nama file untuk intruksi. konfirmasi pemahaman kamu sebelum execute"), revisi "tidak perlu 1:1 selection di
aplikasikan. Aplikasikan yang memang applicable untuk sistem kita. Seperti menawarkan berita, meminta persetujuan opsi,
dll"; saran lanjutan "Ikut gaya baru"; "Ya, eksekusi". Untuk tabel: "Yes boleh. Tp mesti ada safe guard kalau
seandainya output user = 1000 rows?", batas "25 baris", tambahan "Buang tabel kosong (hanya judul)" dan "Opsi 'Tulis
jawaban lain' di klarifikasi".
- **EXEC-CHOICES (EDGE):** satu komponen untuk semua titik pilihan sistem:
  - klarifikasi router (rute dikirim langsung; Eksplorasi diberi keterangan "Termasuk riset berita"; ditambah "Tulis
    jawaban lain" yang membuka kotak pesan);
  - persetujuan rencana riset (Setujui = tombol utama, Revisi = isi kotak pesan dulu, Batalkan);
  - jeda (pilihan `needs_input` = isi dulu; pilihan kirim-langsung pertama = tombol utama);
  - saran lanjutan (pertanyaan lanjutan, ide insight, riset lanjutan).

  Pemisah berlabel "Langkah Anda berikutnya". Tombol menampilkan ikon (panah atau pensil), keterangan kecil ("Kirim
  balasan langsung" / "Isi kotak pesan dulu") dan ekor ("→" / "Tulis"); yang dipilih ditandai "Dipilih · balasan
  terkirim". Tidak diambil dari desain: "Keep paused", pilihan rentang waktu contoh, tombol tema/demo. Tidak ada
  perubahan backend. Di HP pemilih model diringkas jadi huruf modelnya supaya tombol kirim tetap satu baris.
- **EXEC-ROWS (orc):**
  - aturan TABLES: `top` = jumlah baris yang diminta pengguna (sepuluh bila tidak disebut), paling banyak dua puluh
    lima; bila diminta lebih, tampilkan 25 dan tawarkan tabel lengkap sebagai file Excel;
  - pengaman di kode (`table_directives.MAX_ROWS = 25`): instruksi apa pun tidak menampilkan lebih dari 25 baris, dan
    catatan di bawah tabel menjadi "Menampilkan 25 dari N baris; tabel di chat dibatasi 25 baris, tabel lengkap bisa
    diminta sebagai file Excel.";
  - tabel Markdown yang hanya berisi judul dibuang dari jawaban (log `ai_empty_table_removed`; screenshot user: tabel
    harga BBRI dengan judul ganda dari MiMo flash).
- **Tes:** orc 1.453 lulus; EDGE 79/79 lulus dua kali (tes baru: panel rencana, klarifikasi dengan "Tulis jawaban
  lain", jeda).
- **Deploy (RAILWAY_CHANGELOG):** `main` `e7377dd`, orc `ce10d331` dan EDGE `e87fc0be` SUCCESS (11:59Z); diganti
  EXEC-LOGOS pukul 12:52Z. Harga per jam terbukti live di orc `7c11b4ad`: dibaca 12:52:53Z (startup) dan 13:52:53Z
  (satu jam kemudian, tanpa permintaan), keduanya OK untuk 4 model.

### EXEC-MODELS: pilihan model dan level berpikir per pesan di EDGE (deployed)

**Keputusan user 2026-10-13:** "Kita akan menambahkan model2 ini bisa di toggle model dan intellegence level di EDGE
(Default router tetap low) ->kita akan tetap pakai ON for now. model: \"xiaomi/mimo-v2.6-pro\" model:
\"z-ai/glm-5.3-flash\" model: \"qwen/qwen3.8-flash\" Web govt tetap as is dan tidak terpengaruh oleh model2 selection.
(Default) informasi in dan out of each model updated on hourly basis." Jawaban: router tetap DeepSeek low; per pesan;
tampilkan level yang didukung saja; info = harga input dan output per 1 juta token. Go: "Ok, go defaultnya adalah
deepseek V4.1 flash HIGH ya. Cek dulu infra dan buat plan serta testing plan."; default HIGH "Hanya pilihan awal di
EDGE"; MiMo pro dan flash "Both ya". Rencana disetujui (plan EXEC-MODELS).

| Model | Level | in $/1M | out $/1M (OpenRouter 2026-10-13) |
|---|---|---|---|
| deepseek/deepseek-v4.1-flash (awal EDGE: high) | low / medium / high | 0,044 | 0,63 |
| z-ai/glm-5.3-flash | low / medium / high | 0,026 | 0,90 |
| xiaomi/mimo-v2.6-pro | off / on | 0,435 | 0,87 |
| xiaomi/mimo-v2.6-flash | off / on | 0,14 | 0,28 |
| qwen/qwen3.8-flash | off / on | 0,15 | 0,47 |

- **Orc (push 1):**
  - `app/model_choices.py` (daftar, level, bentuk reasoning);
  - `model` dan `reasoning_level` di `/v1/agent/run` (400 bila tidak ditawarkan);
  - pilihan berlaku untuk semua panggilan loop agen termasuk langkah mode 4; router, saran lanjutan, pengklasifikasi
    balasan rencana dan cek fakta web tetap `AI_MODEL` low;
  - daftar provider per model;
  - harga dibaca dari OpenRouter `/models` tiap jam (`app/model_prices.py`), `GET /v1/models`;
  - `execution.model`/`reasoning_level`;
  - log `ai_model_chosen`.
  - Tanpa pilihan: sama persis dengan sebelumnya (`AI_REASONING_EFFORT=medium` di dev).
- **Runner:** item suite boleh membawa `model` dan `reasoning_level`.
- **EDGE (push 2):**
  - `POST /api/v1/runs` menerima `model` dan `reasoning_level` lalu meneruskannya ke orc;
  - `GET /api/v1/models` meneruskan daftar dari orc (cache 10 menit, daftar terakhir dipertahankan bila orc gagal);
  - pemilih di sebelah kotak tulis: 5 model dengan harga input/output per 1 juta token dan level per model, mulai
    DeepSeek V4.1 Flash high, diingat di browser (`edge-model-choice`);
  - header jawaban menampilkan model dan level;
  - daftar dibaca sekali saat login (sebelum halaman kerja tampil), supaya kedatangannya tidak menggambar ulang
    halaman saat pengguna mengetik.
- **Harga:** dibaca saat start lalu **tiap jam di latar belakang** (thread `model-prices`), tanpa menunggu ada yang
  membuka daftar.
- **Tes:**
  - orc 1.444 lulus (`tests/test_exec_models.py`, 21 tes); `AI_MODELS.md` digenerate ulang.
  - EDGE 78/78 lulus dua kali berturut-turut.
  - Catatan: tes visual `test_typing_while_an_answer_arrives_keeps_focus` goyah juga di `main` tanpa perubahan ini
    (1 dari 6 percobaan gagal di kedua kode).
- **Deploy:** orc `956e2d46` (`d42cd76`) SUCCESS, harga 5 model terbaca saat start, daftar provider per model terbaca;
  EDGE `51ac4310` (`bf4d002`) SUCCESS, halaman menyajikan pemilih, `/api/v1/models` tanpa login = 401.
- **Cek live** `ma-models-20261013a` (pertanyaan ab6, biaya sekitar USD 0,23): semua COMPLETED dengan jawaban, dan
  semua panggilan loop memakai model pilihan:

  | Pilihan | Waktu | Biaya | Penolakan gerbang |
  |---|---|---|---|
  | tanpa pilihan (DeepSeek medium) | 105 s | 0,018 | 0 |
  | DeepSeek high | 187 s | 0,019 | 0 |
  | MiMo flash on | 144 s | 0,020 | 0 |
  | MiMo pro on | 259 s | 0,110 | 0 |
  | GLM medium | 455 s | 0,027 | 1 REFERENCE (alamat salah bentuk) + 1 minta ulang JSON |
  | Qwen on | 288 s | 0,033 | 0 |

  Satu run per model: tanda awal, bukan perbandingan mutu.
- **Tes mutu** (user: "Boleh tes mutu tiap model. 2 questions each reasoning high"; ab5 peringkat 15 saham, ab6 broker
  BBRI; level tertinggi: high untuk DeepSeek/GLM, on untuk MiMo/Qwen; `ma-quality-20261013a`, MiMo pro diulang
  `-b` sesudah perbaikan M149; biaya sekitar USD 0,41):

  | Model | ab5 (detik / USD) | ab6 (detik / USD) | Lengkap | Catatan mutu |
  |---|---|---|---|---|
  | DeepSeek high | 189 / 0,017 | 226 / 0,025 | 15 dan 10 baris | Tercepat dan termurah; ab5 membulatkan Rp 1,51 triliun menjadi "Rp 2 triliun" |
  | GLM high | 333 / 0,030 | 197 / 0,012 | **10 dari 15** | Tabel paling kaya (nama emiten, tipe broker); porsi ZP 9,8% karena penyebut lain (jumlah net positif harian Rp 4,58 triliun), beda dari 4 model lain (24,9%) |
  | MiMo pro on | 477 / 0,053 | 316 / 0,034 | 15 dan 10 baris | Run pertama gagal (M149, bug orc, sudah diperbaiki); ab5 memakai semua papan (DSSA teratas) |
  | MiMo flash on | 539 / 0,030 | 159 / 0,021 | **10 dari 15** | ab5 semua papan (DSSA teratas); ab6 ada tabel kosong ganda di atas tabel |
  | Qwen on | 393 / 0,042 | 440 / 0,035 | **10 dari 15** | Paling lambat; isi konsisten |

  - Tidak ada penolakan gerbang di 12 run; satu kali minta ulang JSON (GLM ab6).
  - Angka ab6 seragam (ZP Rp 448,46 miliar, 12 hari net buy).
  - Pertanyaan ab5 ditafsirkan dua cara: papan Regular saja (DeepSeek, GLM, Qwen: BBRI teratas Rp 1,51 triliun) atau
    semua papan termasuk nego (MiMo pro/flash: DSSA Rp 4,22 triliun). Keduanya dinyatakan di asumsi.
  - Temuan sistem: tiga model menampilkan 10 dari 15 baris yang diminta, karena instruksi tabel tanpa `top` berarti
    sepuluh baris (usulan perbaikan belum disetujui).

### EXEC-DERIVED: gerbang menyarankan alamat hitungan untuk angka tanpa sumber (deployed, menunggu bukti live)

**Keputusan user 2026-10-13:** usulan (b) "Gerbang memberi saran hitungan, bukan aturan baru per kata ... masukan exec
dan jalankan diatas."
- Bila angka yang ditolak PROVENANCE atau METHODOLOGY_PROVENANCE (dan di pra-cek draf `check_references`) sama dengan
  hasil `abs(a)` atau `diff(a, b)` dari nilai yang bisa dirujuk di run ini (dibulatkan seperti tampilannya, atau dibaca
  sebagai persen dari pecahan), pesan penolakan menyebut alamatnya: "Of these, 654 equals {{diff(…)}}: if that is what
  the number means, write that reference with a format; otherwise remove it." `chg` dan `ratio` hanya untuk angka yang
  ditulis dengan %.
- **Orc tidak pernah mengganti angka sendiri**; AI yang memutuskan. Log `ai_derived_suggested`.
- **Pengaman kebetulan:** operand harus angka yang tertulis di teks yang sama (kasus "654" ditulis di samping 1.498 dan
  844); angka dengan lebih dari 3 kemungkinan tidak disarankan. Uji data acak tanpa hubungan: saran kebetulan 19%
  sebelum syarat operand tertulis, 6% sesudahnya; risiko sisa ditangani kalimat "if that is what the number means".
- Tidak mengubah gerbang mana pun (yang ditolak tetap sama), prompt, atau deskripsi alat; hanya isi pesan penolakan dan
  hasil pra-cek (`derived_references`).
- **Tes:** orc 1.423 lulus (`tests/test_exec_derived.py` baru).
- **Deploy:** `main` `a066215`: market-ai-orc `9c024c2e` SUCCESS. Bukti live menunggu penolakan berikutnya
  (log `ai_derived_suggested`).
- **A/B 4** (user: "Sudah jalan semua? jika sudah pls A/B on dan off. 2 pertanyaan each"; EXEC-PROSE dan EXEC-DERIVED
  aktif di kedua sisi; ON `ma-ab-table-20261013i`, OFF `ma-ab-table-20261013j`; biaya sekitar USD 0,17):

  | | ab5 peringkat | ab6 broker |
  |---|---|---|
  | OFF | 160 s, COMPLETED, 0 penolakan | 89 s, COMPLETED, 0 penolakan |
  | ON | 104 s, COMPLETED, 0 penolakan | 69 s, COMPLETED, 0 penolakan |

  - Fase orc (rencana / data / analisis / menulis, detik): OFF ab5 24/53/25/43, ON ab5 17/34/15/21; OFF ab6 31/13/13/17,
    ON ab6 6/11/19/13.
  - Teks di luar tabel: ab5 OFF 1.195 karakter / 13 angka, ON 1.052 / 17; ab6 OFF 1.411 / 16, ON 920 / 16.
  - Keempat run memakai pra-cek draf tanpa "..." dan bersih; `ai_derived_suggested` belum terpicu karena tidak ada
    penolakan. Catatan: draf OFF yang dicek lebih pendek dari jawaban akhirnya (408 dan 778 karakter; metodologi 134
    dan 25), jadi draf sebagian tanpa "..." belum terdeteksi.
  - Saklar tabel dikembalikan ke ON (orc `c93a69b8` SUCCESS). Sampel 2 per sisi: tanda, bukan bukti statistik.

### EXEC-PROSE: tafsiran periode tanpa angka, pra-cek draf lengkap dan metodologi, teks di sekitar tabel singkat (deployed; cek cepat bersih)

**Keputusan user 2026-10-13:** "both usulan 1 dan 2 ok" dan "2a + yg tadi kamu mention — Tambah satu kalimat di bagian
TABLES prompt: angka sudah ada di tabel, jadi penjelasan cukup singkat dan setiap angka di kalimat harus dari alamat."
Latar: analisis A/B 1–3 (ERRORS M148). Gerbang tidak berubah; tidak ada aturan gerbang baru per kata (user: "tidak
mungkin seluruh gerbang bisa di sesuaikan dengan apa yang ai akan tulis").
- **Usulan 1, router.** `conversation_router.PERIOD_WORDS_RULE` di router pesan pertama dan router pesan berikutnya:
  periode disebut dengan kata, bukan jumlah hari atau angka lain yang tidak ada di pesan. Catatan router ke langkah
  jawaban (`INTENT_NOTE`) menambah: angka di catatan yang tidak ditulis user adalah tafsiran router, bukan sumber, jangan
  diulang di jawaban. `AI_ROUTER.md` digenerate ulang.
- **Usulan 2, pra-cek draf.** `check_references` v3: argumen `methodology` (wajib, boleh null) diperiksa seperti gerbang
  METHODOLOGY_PROVENANCE (angka kode yang berhasil ikut sumber); draf yang memuat "..." atau "…" dilaporkan `SHORTENED`
  dengan catatan bahwa kalimat yang dihilangkan tidak dicek; deskripsi meminta draf utuh. Tool_Catalog round T
  (`20261013_010_round_t_tool_catalog.sql`, dari generator).
- **2a, bagian TABLES prompt** (hanya saat `AI_ENABLE_TABLE_DIRECTIVES=true`): tabel sudah memuat angkanya, jadi teks
  di sekitarnya singkat; tafsirkan dengan kata dan sebut hanya angka kunci lewat alamat; angka baru (selisih, total,
  jumlah, rasio) dari analisis atau diff/ratio/abs/chg alamat, tidak dihitung di teks; contoh nominal dengan kata.
- **Tes:** orc 1.416 lulus (`tests/test_exec_prose.py` baru, `test_day_counts_and_draft_check.py` disesuaikan).
- **Go 2026-10-13:** "Ok" (migrasi, push/deploy, catatan, dan cek cepat 2 pertanyaan dengan tabel ON). Migrasi round T
  diterapkan dan dibaca balik (`DATABASE_CHANGELOG.md`).
- **Deploy:** `main` `aecfc1e`: market-ai-orc `67a68295` SUCCESS, startup bersih; saklar tabel tetap ON.
- **Cek cepat** `ma-prose-20261013h` (ab5 dan ab6, tabel ON, USD 0,049): keduanya COMPLETED (ab5 229 s, ab6 110 s),
  **0 penolakan gerbang** (putaran 3 ON: "654" dan "30").
  - Router menulis "bulan terakhir yang tersedia di data, bukan 30 hari kalender"; AI tidak menyalin angka.
  - Kedua run memanggil `check_references` dengan draf utuh dan metodologi (1.129/514 dan 1.717/842 karakter),
    tidak disingkat, hasil bersih; panggilan cek 10 s dan 29 s.
  - Teks di luar tabel: ab5 1.397 karakter, 16 angka (putaran 3 ON 1.544/21, OFF 1.221/22); ab6 1.189, 16 angka
    (ON 1.283/16, OFF 1.228/16).
  - Sampel 2 run: tanda awal, bukan bukti statistik.

### EXEC-DAYS dan solusi 2: alamat jumlah hari bursa, pra-cek draf, saklar tabel hidup (deployed; A/B 3 selesai)

**Keputusan user 2026-10-13:** "Ok, coba perbaiki ya, also enable solusi 2, enable ON kemudian A/B on vs off 2 questions"; untuk A/B: "Hanya tabel ON vs OFF" (solusi 2 dan alamat hari bursa aktif di
kedua sisi; sesudah A/B saklar tabel dibiarkan hidup).
- **EXEC-DAYS.**
  - Masalah: "19 hari bursa" diketik, ditolak TYPED_FIGURES, lalu dirujuk lewat hari transaksi satu saham (DSSA) karena
    jumlah hari periode tidak punya alamat sendiri.
  - Profiler bundle sandbox (`runtime/profiler.py`) menghitung tanggal pasti di dalam setiap rentang yang diminta
    (`ranges[].dates`, buffer tidak ikut).
  - Orc mendaftarkannya sebagai `{{data.<data_request_id>.<range_id>.dates}}` (ikut di menu alamat; nama sumber "data
    yang disiapkan").
  - Snapshot prompt `v007`.
- **Solusi 2 (dulu ditunda, sekarang dinyalakan user).**
  - `check_references` v2 menerima `draft`. Orc menjalankan pemeriksaan TYPED_FIGURES dan PROVENANCE atas draf tanpa
    efek (tanpa jatah penolakan, tanpa DIRUJUK), lalu mengembalikan angka diketik beserta alamat kandidat dan angka tanpa
    sumber.
  - Deskripsi alat menganjurkan draf dikirim di cek yang memang sudah dilakukan sebelum menjawab.
  - Tool_Catalog `check_references` v2 (migrasi `20261013_009_round_s_tool_catalog.sql` dari generator).
- **Tes:** orc 1.667 lulus (`test_day_counts_and_draft_check.py`, `test_profile_distinct.py`); suite sandbox gagal
  sama persis dengan baseline (196 tes isolasi).
- **Deploy:** `main` `199e16d`: orc `12ffea95` dan sandbox `e62b7d3a` SUCCESS; migrasi round S diterapkan lewat
  `mmig-job` (dibaca balik: `check_references` v2 memuat `draft`). Saklar tabel `AI_ENABLE_TABLE_DIRECTIVES=true` →
  orc `9d620a75` SUCCESS, **dibiarkan hidup** sesuai keputusan user.
- **A/B 3** (2 pertanyaan; OFF `ma-ab-table-20261013f`, ON `ma-ab-table-20261013g`; biaya sekitar USD 0,20):

  | | ab5 peringkat | ab6 broker |
  |---|---|---|
  | OFF | 116 s, COMPLETED | 179 s, COMPLETED |
  | ON | 279 s, COMPLETED | 323 s, COMPLETED |

  - Fase orc (rencana / data / analisis / menulis, detik): OFF ab5 38/12/18/23, ON ab5 56/34/86/80, OFF ab6
    14/69/31/40, ON ab6 56/38/81/123. Selisih ON ada di rencana, analisis (ab5 ON: 7 `run_python` karena print
    terpotong dan error dict ambang) dan ronde perbaikan, bukan di penulisan tabel: 0 instruksi tabel ditolak.
  - Solusi 2 dipakai di 3 dari 4 run, semuanya bersih, tetapi: ON ab5 tetap kena METHODOLOGY_PROVENANCE "654" (pra-cek
    tidak memeriksa metodologi/asumsi); ON ab6 mengirim draf yang disingkat ("...") sehingga pra-cek tidak efektif, lalu
    kena PROVENANCE "30" ("30 hari kalender terakhir"); panggilan cek itu sendiri 33 s.
  - Alamat `data.*` belum dipakai: ON ab6 merujuk hari bursa lewat output analisisnya sendiri.
  - Sampel sangat kecil (2 pertanyaan per sisi); bukan dasar keputusan akhir.
- **Usulan lanjutan (belum disetujui):** pra-cek ikut memeriksa metodologi dan asumsi; tolak draf yang disingkat
  (meminta draf lengkap).

### EXEC-IMPL-1012: rencana implementasi EXEC-JOINKEY, EXEC-RELEASE, EXEC-FRICTION, EXEC-STYLE (selesai; Fase 3c berhenti di M143)

**Permintaan user 2026-10-12:** "cek infra kita, dan EXEC yang sudah saya approve, buat implementation plan berdasarkan
ini before full proceed." **Go 2026-10-12:** "ok" atas tiga pertanyaan: push dokumen ke `main`, jalankan rencana ini
dengan lanjut otomatis antar fase bila lulus (berhenti hanya pada kondisi berhenti di bawah), dan empat pertanyaan A/B
di bawah. Hasil pemeriksaan infra (read-only) yang membentuk rencana:
- ORC, sandbox, Governor dan EDGE men-deploy dari GitHub `main` dengan watch path per folder: **push kode ke `main`
  adalah deploy**. Dokumen di root repo tidak memicu deploy.
- Panduan metode hanya disajikan bila tabel `AI_method_guide`, sandbox dan file orc memuat hash yang sama: migrasi v8
  diterapkan sebelum push; sandbox dan orc ter-deploy dari satu push; selama keduanya belum SUCCESS, menu panduan
  sementara tidak tersedia (bukan error jawaban).
- Kontrak yang disetujui memakai pasangan kunci dari katalog, jadi Perbaikan 3 tidak mengubah hash atau Governor.
- Deskripsi `submit_data_need_spec` dan `run_python` berubah: satu ronde Tool_Catalog (R) dengan generator dan tes drift.
- Catatan penolakan run memory dan `friction` tidak konsisten (lihat EXEC-FRICTION).

| Fase | Isi | Layanan yang ter-deploy | Lulus bila |
|---|---|---|---|
| 0 | Branch kode dari `main` terbaru; venv orc, sandbox, EDGE; jalankan suite tes yang ada (patokan hijau); ukur rasio ukuran prompt terhadap `SIZE_BUDGET`; catat deployment aktif orc, sandbox, EDGE sebagai titik rollback; cek sisa kredit OpenRouter | — | Patokan tercatat |
| 1 | EXEC-JOINKEY (perbaikan 1–3) + EXEC-RELEASE: kode sandbox dan orc, panduan v8 di dua salinan, migrasi `AI_method_guide` v8 dan Tool_Catalog ronde R, `AI_TOOLS.md`, README, ERRORS G25/M139. Tes lengkap orc dan sandbox. Terapkan dua migrasi di dev (cara yang sama dengan migrasi sebelumnya), baca balik, lalu push | sandbox, orc | Tes hijau; migrasi terbaca balik; kedua deployment SUCCESS; `/ready` bersih |
| 2 | EXEC-FRICTION: satu pengelompok status penolakan, `execution.hurdles`, kalimat di `user_texts.py`, EDGE (view, labels, html), fixture dari orc asli, README, ERRORS M142. Tes orc dan EDGE (kontrak, tampilan, visual) | orc, EDGE | Tes hijau; kedua deployment SUCCESS; halaman EDGE terbuka tanpa error |
| 3a | **Run A** (4 pertanyaan, prompt lama, kode fase 1–2): sekaligus cek live EXEC-JOINKEY, EXEC-FRICTION dan, bila terjadi kode gagal, EXEC-RELEASE | — | Semua giliran selesai; data harga + broker lolos revisi pertama; hambatan tampil sama dengan log |
| 3b | EXEC-STYLE S1–S5: prompt, catatan router, aturan 13, contoh, `ai_answer_long` per jenis, EDGE terlipat; snapshot prompt, `AI_ROUTER.md`, tes prompt. Push | orc, EDGE | Tes hijau; kedua deployment SUCCESS |
| 3c | **Run B** (4 pertanyaan yang sama) dan laporan A/B ke user | — | Penolakan gerbang tidak naik; ukuran A/B dilaporkan; keputusan user |

**Empat pertanyaan A/B** (mode lewat `analysis_path` agar biaya terkendali):
1. obrolan: "Apa saja yang bisa kamu bantu soal data saham di sini?" (CHAT);
2. fakta: "Apa arti net buy asing dan kenapa investor memperhatikannya?" (FACT);
3. analisis: "Bandingkan return BBCA dan BBRI selama sebulan terakhir data yang tersedia." (ANALYSIS);
4. analisis gabungan harga + broker: "Bagaimana harga BBRI bergerak di hari-hari net buy asingnya besar, sebulan
   terakhir data?" (ANALYSIS; menguji kunci gabungan harga ↔ broker, relasi #23).

**Biaya dan batas:** 8 run; perkiraan ≤ USD 0,40. Kredit dicek sebelum fase 3a; berhenti dan lapor bila sisa < USD 0,30
sebelum sebuah run (aturan yang sama dengan 2026-10-06).

**Berhenti dan lapor bila:** tes merah yang bukan dari perubahan ini; deployment tidak SUCCESS; migrasi tidak terbaca
balik; penolakan gerbang naik di run B; biaya melewati batas; langkah di luar rencana ini diperlukan.

**Rollback:** redeploy deployment yang dicatat di fase 0 (orc, sandbox, EDGE); prompt kembali lewat
`prompts/SYSTEM_PROMPT_HISTORY.md`; migrasi bersifat menambah (baris panduan v7 dan versi alat lama tetap ada).

**Progres 2026-10-12:**
- Fase 1 (`597b77f`) dan Fase 2 (`cbe1860`): deployment SUCCESS (detail `RAILWAY_CHANGELOG.md`).
- Fase 3a, **Run A** (`ma-ab-style-20261012a`, prompt lama, orc `79f13a5e`): 4/4 selesai, biaya sekitar USD 0,110.
  Pertanyaan 1 dan 2 lewat `AUTO` (router pesan pertama memilih CHAT dan FACT; `analysis_path` hanya menerima AUTO,
  ANALYSIS, RESEARCH, MODE4), 3 dan 4 lewat ANALYSIS. Cek live: EXEC-JOINKEY lulus (permintaan data harga + net beli
  asing lolos pada pengajuan pertama), EXEC-RELEASE lulus (satu run_python gagal, diulang, tabel yang dirilis dari run
  yang berhasil), EXEC-FRICTION lulus (hambatan sama dengan log). Temuan: penolakan dengan status polos REJECTED tertulis
  "ditolak (rejected)"; diperbaiki di Fase 3b (status polos tanpa alasan).

  | Run A | Karakter | Huruf tebal | Pembuka tebal | Baris tabel | Asumsi | Batasan |
  |---|---|---|---|---|---|---|
  | 1 obrolan (CHAT) | 2.301 | 15 | tidak | 0 | 2 | 3 |
  | 2 fakta (FACT) | 2.663 | 5 | ya | 6 | 3 | 1 |
  | 3 analisis | 1.231 | 1 | ya | 8 | 3 | 7 |
  | 4 harga + net beli asing | 1.995 | 1 | ya | 5 | 6 | 10 |

  Penolakan gerbang Run A: 2 (perbaikan angka tanpa rujukan di 3 dan 4), keduanya teratasi.
- Fase 3b: prompt +1,93% terhadap prompt saat ini (`SIZE_BUDGET` 1,10 → 1,12 terhadap fixture pass 2; batas konteks
  tes `test_orchestrator.py` 20.600 → 20.800 token seperti perubahan prompt sebelumnya), snapshot `v004 exec-style`,
  `AI_ROUTER.md` diregenerasi. Tes: orc 1.632 lulus, EDGE 62 lulus.
- Fase 3b ter-deploy dari `main` `6adc09b` (orc `1ac6bcc5`, edge-bff `7c2ad4f9`, keduanya SUCCESS).
- Fase 3c, **Run B** (`ma-ab-style-20261012b`, prompt EXEC-STYLE): biaya sekitar USD 0,066 (A + B sekitar USD 0,176).

  | Run B | Status | Karakter | Huruf tebal | Pembuka tebal | Baris tabel | Asumsi | Batasan |
  |---|---|---|---|---|---|---|---|
  | 1 obrolan (CHAT) | COMPLETED | 2.493 | 0 | tidak | 0 | 0 | 1 |
  | 2 fakta (FACT) | COMPLETED | 1.737 | 0 | tidak | 0 | 2 | 0 |
  | 3 analisis | COMPLETED | 1.110 | 0 | tidak | 4 | 3 | 4 |
  | 4 harga + net beli asing | **LIMITED** | 2.487 | 0 | tidak | 7 | 5 | 6 |

  Huruf tebal 22 → 0, pembuka tebal 3 → 0, asumsi + batasan 35 → 21. Panjang obrolan belum turun (2.301 → 2.493,
  target sekitar 800); fakta turun (2.663 → 1.737). Penolakan gerbang: A 2 (keduanya teratasi), B 2 di pertanyaan 4
  (satu perbaikan, lalu LIMITATION paksa). **Berhenti dan lapor** (kondisi berhenti: hasil gerbang memburuk di Run B).
  Penyebabnya bug gerbang yang sudah ada (M143: kata skala "juta"/"miliar" sesudah rujukan ke kolom yang sudah
  berskala), bukan perubahan gaya; usulan perbaikan menunggu keputusan user. Laporan lengkap A/B (8 jawaban) di luar
  repo (jawaban AI tidak disimpan di repo publik).
