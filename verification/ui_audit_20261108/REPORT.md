# Audit UI/UX frontend — Terminal dan Screener (2026-11-08)

Mode: **audit saja** (tidak ada perbaikan dalam audit ini). **Status 2026-11-08: ke-27 temuan diperbaiki di branch dan dicek ulang di browser, lihat bagian F.** Build yang diaudit: branch `claude/practical-thompson-2intee`
commit `0132bdab` (Terminal di stand-in BBRI, Screener di build fixture). Lima auditor independen (lebar 1440, 1100 dan
390 px, terang dan gelap), lalu temuan berat direproduksi ulang oleh agen utama (`scratchpad/visual_review/verify.mjs`).
Bukti (tangkapan layar dan skrip) per auditor: `scratchpad/visual_review/a1` … `a5` (tidak di Git).

## A. Ringkasan

- **Temuan unik:** 27, sesudah duplikat digabung (dari 43 temuan mentah). P0: 0 · P1: 3 · P2: 11 · P3: 13.
- **Asal:**
  - 14 dari perubahan hari ini;
  - 12 sudah ada sebelumnya;
  - 1 sesuai keputusan user (bukan cacat).
- **Cakupan:**
  - Terminal: toolbar, legend, pane, Indicators, Settings, Loaders, FL52, panel kanan, pop-out, Layout, gambar, Events.
  - Screener: halaman, builder, Add a condition, Customize, drawer, tabel, preset.
  - Sekitar 550 interaksi.
- **Tidak tercakup:**
  - dialog Save/Open Layout dan Save/Export Screener;
  - isi column picker;
  - gestur sentuh;
  - pop-out F×D;
  - Terminal di mode gelap (Terminal memang tidak punya mode gelap, tercatat di EXEC).
- **Konsol:** tidak ada error halaman. Hanya 404 `reference/fixed_income` yang memang ada di stand-in.
- **Prioritas teratas:**
  - U1: kotak Loaders tertutup garis pemisah pane.
  - U2: klik grup di Add a condition tidak menggulir ke atas.
  - U3: jendela Add a condition bisa diperkecil sampai tabelnya tergulir ke samping.
  - U4: kotak Loaders menutup tombol baris legend.

## B. Daftar temuan

Kolom "Asal": **baru** = dari perubahan hari ini, **lama** = sudah ada di `main` sebelumnya.
Keyakinan: **C** = CONFIRMED (dicek ulang oleh agen utama bila ditandai ✓), **DM** = DESIGN MISMATCH, **NV** = NEEDS VERIFICATION.

| ID | Agen | Lokasi | Kategori | Sev | Asal | Diharapkan | Terjadi (bukti) | Perbaikan yang diusulkan | Yakin |
|---|---|---|---|---|---|---|---|---|---|
| U1 | A3 | Terminal, kotak Loaders | Interaction | P1 | baru | Klik kode broker menambah ke Broker Inventory; tepi kotak bisa ditarik | Garis pemisah pane chart (div z-index 50, tinggi 9 px) ada di atas kotak (z-index 6): `elementFromPoint` di tombol YU = DIV pemisah, klik tidak berbuat apa-apa; tepi kiri/kanan di garis itu memulai resize pane | Kotak di atas lapisan internal chart (z-index > 50) atau `isolation:isolate` pada chart | C ✓ |
| U2 | A3 | Screener, Add a condition, daftar grup kiri | Interaction | P1 | baru | Klik grup menggulir ke grup itu (naik atau turun) | Sesudah Fundamental (8271), klik Trend tetap 8271: `scrollToGroup` mengukur judul kelompok yang menempel (sticky) | Ukur baris pertama grup (`.qrow[data-rg]`), bukan judulnya | C ✓ |
| U3 | A4 | Screener, Add a condition diperkecil | Responsive | P1 | baru | Jendela tidak bisa lebih kecil dari isinya, atau tata letak menyesuaikan | Minimum 640 px, isi baris 886 px dalam 424 px: daftar tergulir ke samping, judul kolom INDICATOR/TIMEFRAME bertumpuk, Add terdorong keluar | Lebar minimum diturunkan dari kolom tabel (± 900 px), atau kolom dilipat di bawah lebar itu | C ✓ |
| U4 | A1, A3, A5 | Terminal, kotak Loaders posisi awal | Layout / UX | P2 | baru | Tombol baris legend (mata, gear, simpan, hapus) bisa diklik | Kotak di x 646–1022, y 90–414 menutupi tombol baris FL51, FL52, FL49 (gear FL51 → `.ldb-seg`); tidak ada tombol tutup/sembunyi di kotak; di 390 px kotak menutup hampir seluruh chart | Posisi awal di bawah baris legend; tombol sembunyikan (×) di kepala kotak; di ponsel lebih kecil/menempel di bawah | C ✓ |
| U5 | A5 | Screener, Add a condition dan Customize | Interaction | P2 | lama (kemungkinan) | Satu klik pada Add / Done / Reset bekerja | Ketik di isian lalu klik Add: baris digambar ulang saat `change`, tombol diganti, klik hilang ("0 conditions on the screen") | Perbarui baris tanpa mengganti tombol, atau tunda gambar ulang sampai sesudah klik | C ✓ |
| U6 | A5 | Terminal, kotak Loaders diperlebar | Interaction | P2 | baru | Lebar mengikuti tarikan | CSS `max-width:min(420px,…)` memotong; ukuran tersimpan 523 tetapi tampil 420; tepi kanan bergeser saat tepi kiri ditarik | Hapus batas 420 untuk kotak yang diubah ukurannya, atau batasi `w` di JS dengan angka yang sama | C ✓ |
| U7 | A1, A4 | Screener, baris SMA/EMA/WMA/HMA | Layout | P2 | lama | Label "Source" terbaca | Tampil "S…" (lebar 21 px, isi 37 px) di 1440 dan 1100 | `flex:none` pada label, atau batasi lebar select | C |
| U8 | A1, A2, A4 | Screener, Add a condition di 1100 px | Responsive | P2 | lama + baru | Nama dan pilihan timeframe terbaca | Nama terpotong ("Simple Moving Av…"; kode baru ikut makan tempat); tombol "Daily" 27 px dalam 24 px | Atur ulang lebar kolom di ≤1100 (timeframe ≥ 200 px, nama lebih lebar) | C |
| U9 | A2 | Screener, tombol Customize saat terbuka | Design | P2 | baru | Tanda terpilih Terminal: tanpa garis, bayangan lembut | Garis putus-putus biru saat terbuka; fokus keyboard garis abu | `.qcus[aria-expanded=true]` dan `:focus-visible`: garis transparan + `--sel-shadow` | DM |
| U10 | A1, A4 | Screener, tab Screen builder di 1100–1280 px | Layout | P2 | lama | Tiga tab terlihat | "Saved" terpotong, angkanya hilang (291 px dalam 258–268 px) | Kecilkan jarak tab atau sembunyikan angka di lebar ini | C |
| U11 | A2 | Terminal, Settings dan panel kanan | Design | P2 | lama | Satu gaya dropdown | Campuran `select` bawaan (panah tebal) dan menu `fl-btn` (panah tipis) di dialog dan panel yang sama | Satu gaya (panah sama) | C |
| U12 | A2 | Screener, Add a condition vs Indicators Terminal | Design | P2 | baru | Ukuran kontrol seperti Terminal | Add 28 × 50 px (Terminal 34 × 80); item grup 40 px (36); select 28 px (32); token warna sedikit beda (--text-2, --sel, --hover) | Samakan ukuran `.qact`, `.qri`, isian dan token dengan `.im-*` | DM |
| U13 | A4 | Terminal ≤1100 px | Responsive | P2 | lama | Panel Broker activity bisa dibuka | `.side.right{display:none}` (terminal.css:535) tanpa tombol pembuka | Bila memang disengaja: tombol untuk membuka panel sebagai laci; bila tidak: turunkan batasnya | NV |
| U14 | A4 | Terminal 390 px | Responsive | P2 | lama + baru | Toolbar dan chart terpakai di ponsel | Toolbar tergulir ke samping tanpa tanda (772/390 px); kotak Loaders 374 × 343 menutup chart | Tanda gulir di toolbar; kotak Loaders versi ponsel | C |
| U15 | A4 | Screener, Customize di ukuran minimum | Responsive | P3 | baru | Reset / Done terlihat | Di 300 × 160 tombol di bawah lipatan tanpa tanda | Baris tombol menempel di bawah, atau minimum setinggi isi | C |
| U16 | A3 | Screener, Add a condition diperbesar | Responsive | P3 | baru | Jendela tetap di layar | Lebar 1424 dari x 20 → tepi kanan 1444, bawah 904 (pegangan sudut terpotong) | Batasi ke `innerWidth − 2·margin` | C |
| U17 | A3 | Screener, latar gelap saat Customize terbuka | Interaction | P3 | baru | Klik di luar menutup kotak saja | Klik di latar gelap menutup kotak dan jendela Add sekaligus | Saat Customize terbuka, klik latar menutup kotak saja | NV |
| U18 | A5 | Terminal, kotak Loaders dan Settings | Interaction | P3 | baru + lama | Fokus keyboard tetap di kontrol | Pilihan Top 5 dengan keyboard: fokus pindah ke BODY (isi kotak digambar ulang); Ok di Settings: fokus ke BODY (Cancel kembali ke gear) | Kembalikan fokus ke kontrol yang sama / ke gear | C |
| U19 | A3 | Terminal, legend FL51 mode Sellers | UX | P3 | baru | Catatan legend sesuai isi kotak | "No value: fewer than 3 net buyers or sellers here" padahal kotak menampilkan 3 penjual (tidak ada garis di mode Sellers) | Catatan khusus: "Cost lines are for loaders; Sellers shows none" | NV |
| U20 | A3 | Terminal, kotak Loaders | UX | P3 | baru | Status broker jelas | Broker yang sudah di Broker Inventory tidak ditandai, judul tetap "Add NI"; legend FL52 menampilkan 5 dari 7 broker | Tanda "in inventory"; legend FL52 memuat semua atau "+2" | C |
| U21 | A1 | Terminal, tabel kotak Loaders | Layout | P3 | baru | Garis pemisah kelompok selebar kotak | Tabel 300 px dalam kotak 375 px: garis di atas "TOP 3 NET SELLERS" berhenti 73 px sebelum tepi | Tabel `width:100%` (sesuai acuan pada lebar awal) | NV |
| U22 | A2 | Screener, kotak Customize | Design | P3 | baru | Sesuai catatan EXEC "Esc / × = dibuang" | Kotak Screener yang lama tidak punya ×; teks "default …" tidak sejajar satu kolom | Tambah × di judul (seperti Esc), atau ubah catatan EXEC | DM |
| U23 | A3 | Screener, More filters | Interaction | P3 | lama | Esc mengembalikan fokus ke pembuka; chip sektor terbaca pembaca layar | Fokus ke BODY; chip tanpa `aria-pressed` | Kembalikan fokus; tambah `aria-pressed` | C |
| U24 | A3 | Screener, hapus kondisi di builder | UX | P3 | lama | Ada umpan balik / Undo seperti di Add window | Tanpa toast, tanpa Undo; toast lama "… added" tetap tampil | Toast "removed" dengan Undo | NV |
| U25 | A3 | Terminal, isian angka Settings | UX | P3 | lama | Nilai di luar batas diberi tahu | 0 dan −5 jadi 1, 5000 jadi 250 tanpa pesan | Pesan singkat di bawah isian | C |
| U26 | A2, A1 | Detail kecil | Design / Layout | P3 | lama + baru | — | Tombol Layout 32 px/8 px (lainnya 30/6); kode broker Loaders bukan monospace (`--mono` = `--sans`); kartu builder punya blok kosong 14 px; petunjuk "/" tertutup tombol "+"; Flow Timeline di 390 px membungkus | Rapikan satu per satu bila diinginkan | C |
| U27 | A4 | Screener 390 px | Responsive | P3 | lama | Ada tanda bisa digulir | Strip grup Add window, tab preset dan chip cepat terpotong tanpa tanda gulir | Bayangan/tanda gulir di tepi | C |

**Bukan cacat (sesuai keputusan user):**
- **FL52 dan panel kanan:** daftar brokernya bisa berbeda (A5-5). Broker yang keluar dari panel tetap ada di FL52 (user: "OK" atas usul itu).
- **Terminal tanpa mode gelap:** sudah tercatat di EXEC.
- **Teks bahasa Indonesia:** penjelasan indikator berbahasa Indonesia di UI berbahasa Inggris. Ini keputusan konten, di luar audit.

## C. Perbandingan visual (acuan yang disetujui)

| Acuan | Hasil | Selisih |
|---|---|---|
| `verification/screener/add_condition_look/add_condition_terminal_style.html` | Kotak cari, daftar grup dengan bagian, judul kelompok menempel, kode + penjelasan, tanda terpilih isian: sesuai | Ukuran kontrol lebih kecil (U12), tombol Customize terbuka (U9), × di Customize (U22) |
| `verification/terminal_api/flow_dots/loaders_final.html` | Permukaan, tombol, segmen, warna, tabel: sesuai | Kode broker bukan monospace, berat huruf judul 600 (acuan 700), tinggi baris 26 px (25 px) |
| Jendela Indicators dan dialog Settings Terminal | Pilihan grup bergaris kiri, radius dan bayangan jendela: sama | Lihat U12 |

## D. Urutan perbaikan yang disarankan

1. **P1 (perubahan hari ini):**
   - U1: kotak Loaders di atas lapisan internal chart.
   - U2: gulir ke grup naik dan turun.
   - U3: lebar minimum jendela Add a condition diturunkan dari kolomnya.
2. **P2 hari ini:**
   - U4: posisi awal kotak Loaders, dan tombol × untuk menyembunyikannya.
   - U6: batas lebar 420 px.
   - U9: tanda terpilih tombol Customize.
   - U12: ukuran kontrol.
   - U8: tata letak 1100 px.
3. **P2 lama:**
   - U5: klik pertama hilang. Ini yang paling terasa pengguna.
   - U7: label "Source".
   - U10: tab builder.
   - U11: dua gaya dropdown.
   - U13: keputusan untuk panel kanan di ≤1100 px.
   - U14: tampilan ponsel.
4. **P3:** sesudah poin di atas, sebagian besar perubahan kecil di CSS atau penanganan fokus.

## E. Gerbang mutu

- [x] Halaman yang bisa diakses diperiksa, atau dicatat sebagai tidak tercakup (A).
- [x] Kontrol interaktif diuji (sekitar 550 interaksi).
- [x] Komponen berulang dibandingkan (A2).
- [x] Perataan diukur dari DOM dan piksel (A1, A4).
- [x] Tema: Screener terang dan gelap. Terminal tidak punya tema gelap (tercatat).
- [x] Lebar 1440, 1100 dan 390 diuji.
- [x] Overflow dan pemotongan diperiksa (tidak ada gulir samping di tingkat halaman).
- [x] Error konsol diperiksa.
- [x] Temuan berat (U1–U6) direproduksi ulang oleh agen utama.
- [x] Duplikat digabung (43 → 27).
- [x] Setiap temuan punya bukti. Yang belum pasti ditandai NV.

## F. Perbaikan (user 2026-11-08: "perbaiki semua temuan / sembunyikan kotak / tidak, tambahkan laci")

Semua dicek ulang di browser (`scratchpad/visual_review/fixT.mjs`, `fixS.mjs`, `u12.mjs`, `dbgok.mjs`, `dbg24.mjs`). Tes:
Terminal 887, Screener 1.327, screener-worker 105, backtest-worker 205 lulus. Pemeriksaan tampilan juga lulus: look check
3, 5-13 dan `shots.mjs` Screener.

| ID | Perbaikan | Bukti sesudah |
|---|---|---|
| U1 | Kotak di atas lapisan chart (z-index 60 > 50) | 6 dari 6 kode broker bisa diklik (`elementFromPoint`) |
| U2 | Gulir diukur pada baris pertama grup | Fundamental 8270 → Trend 0 → Volume 1970 (baris 85 px di bawah judul) |
| U3 | Container query: baris rapat di < 1000 px daftar, bertumpuk di < 820 px; minimum = daftar kiri + 446 | Jendela 656 px tanpa gulir samping |
| U4 | Posisi awal di bawah baris legend, tinggi dibatasi di pane harga; × menyembunyikan kotak (Settings "Show box"); ponsel: di kaki chart | Tombol baris FL51, FL52, FL49: 111/111/111 bisa diklik; × lalu Ctrl+Z: tersembunyi → tampil |
| U5 | Tombol aksi tidak mengambil fokus saat ditekan (nilai sudah tersimpan dari ketikan) | Ketik 25 lalu klik Add sekali: "1 condition on the screen"; Done sekali menutup |
| U6 | Batas 420 px dihapus | Lebar ditarik menjadi 602 px |
| U7 | Label parameter tidak menyusut | "Length", "Source" utuh |
| U8 | Kolom di 1100 px diatur ulang, nama dua baris | Tidak ada gulir samping, tidak ada nama terpotong, "Daily" muat |
| U9 | Tombol Customize terbuka: tanpa garis, bayangan lembut | Garis transparan + bayangan |
| U10 | Jarak tab dirapatkan di ≤1280 px | 258/258 px (sebelumnya 291/258) |
| U11 | Select bawaan memakai panah tipis yang sama dengan menu | `appearance:none` + panah sama |
| U12 | Ukuran kontrol dan warna seperti Indicators Terminal | Add 32 px, grup 36 px, select 32 px, `--text-2` #666 |
| U13 | Laci Broker activity di ≤1100 px (tombol toolbar; », Esc, klik di luar menutup) | 1100 px: tombol tampil, laci 360 px di kanan, Esc menutup |
| U14 | Toolbar ponsel memudar di tepi; kotak Loaders versi ponsel | Kotak 374 × 235 di kaki chart (sebelumnya menutup chart) |
| U15 | Reset / Done menempel di bawah kotak | Kotak 160 px: Done tetap terlihat |
| U16 | Ukuran jendela dibatasi layar | Kanan 1420 ≤ 1440, bawah 880 ≤ 900 |
| U17 | Klik latar saat Customize terbuka menutup kotaknya saja | Jendela tetap terbuka, kotak tertutup |
| U18 | Fokus dijaga saat isi kotak digambar ulang; fokus kembali ke gear (baris ditampilkan sesaat) | Top 5 dengan keyboard: fokus tetap di "5"; Ok dan Cancel: fokus di gear |
| U19 | Catatan legend mode Sellers | "Cost lines are drawn for loaders; Sellers lists none" |
| U20 | Broker yang sudah di Broker Inventory ditandai ✓ dengan judul yang sesuai | NI ✓ |
| U21 | Tabel selebar kotak | Sisa 3 px (sebelumnya 73 px) |
| U22 | × di kotak Customize; catatan "default" satu kolom | × menutup; catatan di satu x |
| U23 | Fokus kembali ke tombol More filters; chip sektor `aria-pressed` + label status | Fokus `[data-act="drawer"]` |
| U24 | Hapus kondisi: notifikasi dengan Undo | "Simple Moving Average removed · Undo"; Undo mengembalikan di posisi semula |
| U25 | Catatan di bawah isian yang disesuaikan | "Set to 1: the allowed range is 1–20" |
| U26 | Layout 30 px/6 px; kode broker monospace; kartu tanpa baris kosong; "/" tidak tertutup; legend Flow Timeline satu baris di ponsel | Tercek di tangkapan layar |
| U27 | Tepi memudar di baris yang tergulir ke samping (390 px) | `mask-image` aktif di 390, tidak di 1440 |
