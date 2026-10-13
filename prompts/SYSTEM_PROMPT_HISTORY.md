# System prompt history

Every version of what the orc model reads at the start of each call: the system prompt and the final-response schema,
rendered with the dev profile (`scripts/snapshot_system_prompt.py`). The newest entry is what the code renders now
(`apps/market-ai-orc/tests/test_prompt_history.py`). Recorded with `scripts/snapshot_system_prompt.py record`
whenever the rendered prompt or schema changes (AGENTS.md, Mandatory workflow).

## How to fall back

1. Find the version to return to below; its commit is the commit that added its snapshot folder
   (`git log --diff-filter=A -- prompts/history/<folder>`).
2. Fastest, without code: in Railway, redeploy the orc deployment built from that commit or a later one with the same
   prompt sha256 (RAILWAY_CHANGELOG.md lists deployments by commit). Verify the deployment reaches SUCCESS.
3. In code: `git revert` the commits after that version that changed `apps/market-ai-orc/app/orchestrator.py` prompt
   texts or `app/schemas.py` descriptions, run the orc tests, record a new snapshot (it must have the old sha256), push
   `main`, and verify the deployment.
4. A snapshot is text to compare and restore, not a file the service reads: a prompt goes with the tools and checks of
   its code, so an old prompt is restored together with its code, never alone.

## Versions

| Version | Date | Name | Prompt chars | Prompt sha256 | Schema sha256 | User decision |
|---|---|---|---|---|---|---|
| v001 | 2026-10-08 | [deployed-before-reader-rules](history/v001-2026-10-08-deployed-before-reader-rules/system_prompt.md) | 35,194 | `5ae68c51948c` | `b4e5b2cd9d33` | Titik awal riwayat: prompt yang ter-deploy di dev sebelum M125 C (orc 9efe1118, kode main df18695) |
| v002 | 2026-10-08 | [reader-rules](history/v002-2026-10-08-reader-rules/system_prompt.md) | 37,462 | `367d6103d2e3` | `48bceaa503bc` | 2026-10-08: "Naikan batas"; "Lanjut tulis prompt. Pakai best practice prompt. Pastikan tidak ada prompt yg contradict di system prompt." |
| v003 | 2026-10-09 | [row-presence-and-day-counts](history/v003-2026-10-09-row-presence-and-day-counts/system_prompt.md) | 37,793 | `19b8a23befb7` | `48bceaa503bc` | 2026-10-09: "E1 ok 2-4 masukan exec"; go "gas" (EXEC-Y Fase 3) |
| v004 | 2026-10-12 | [exec-style](history/v004-2026-10-12-exec-style/system_prompt.md) | 38,522 | `58d6ec180d2f` | `48bceaa503bc` | Ok, yang adopsi dan sebagian --> masukan EXEC. (2026-10-12); go: ok |
| v005 | 2026-10-12 | [exec-style-run-a](history/v005-2026-10-12-exec-style-run-a/system_prompt.md) | 37,979 | `1aeee73d55c7` | `48bceaa503bc` | well saya lebih suka Run A tapi tanpa kewajiban AI untuk kasih asumsi, batasan. ... dalam 1 jawaban boleh lebih dari 1 tabel as long as membantu user (tidak wajib harus lebih dari 1) (2026-10-12) |
| v006 | 2026-10-13 | [exec-m143](history/v006-2026-10-13-exec-m143/system_prompt.md) | 38,420 | `0395b6925985` | `48bceaa503bc` | "Ok perbaiki M143 dulu" (cara "(a) + (c) (Recommended)"); "saya setuju solusi 1 dan 2"; "Go" (2026-10-13; solusi 2 ditunda: "Tunda solusi 2 (Recommended)") |
| v007 | 2026-10-13 | [exec-days](history/v007-2026-10-13-exec-days/system_prompt.md) | 38,633 | `c248a495a4f0` | `48bceaa503bc` | "Ok, coba perbaiki ya, also enable solusi 2, enable ON" (2026-10-13) |

## Changes

### v001 deployed-before-reader-rules (2026-10-08)

Versi dasar riwayat. Berisi semua perubahan yang sudah disetujui sampai EXEC-W gelombang A (2026-10-08): audit prompt pass 2, M117, M121 h, M122. Belum ada bagian WRITING FOR THE READER.

### v002 reader-rules (2026-10-08)

M125 C. Bagian baru WRITING FOR THE READER: pembacanya investor perorangan; kesimpulan dulu, lalu angka dengan pembandingnya, artinya, dan batasannya; kalimat pendek dan kata sehari-hari; nama tabel, kolom, output, ID dan kode hanya di pemanggilan tool dan field terstruktur; satu contoh jawaban berbahasa Indonesia. Sembilan kalimat yang bertentangan ditulis ulang: aturan 12, bendera kualitas, data di METHODOLOGY, istilah putusan dan status, kategori sampel, sudut tidak valid, penutup INTERPRETING, instruksi perbaikan temuan, dan LIMITATION jalur lama. Deskripsi skema temuan dan metodologi diselaraskan. Ukuran +8,6% terhadap fixture pass-2, batas baru 1,09.

### v003 row-presence-and-day-counts (2026-10-09)

EXEC-Y Fase 3 E1 bagian 2 dan 4. DATA DISCOVERY: arti row_presence dari katalog (ACTIVITY_ONLY: baris hanya ada bila ada aktivitas; deret harian dari tabel itu memakai setiap hari yang ada di sumber untuk kelompoknya dan menulis nol bila saringan tidak menyisakan baris; DENSE: baris yang tidak ada berarti data hilang). WRITING FOR THE READER: jumlah hari menyebut apa yang dihitung (hari bursa atau hari dengan aktivitas). Ukuran +9,5% terhadap fixture pass-2, batas baru 1,10.

### v004 exec-style (2026-10-12)

EXEC-STYLE S1-S4: the reader section as prose, the conclusion-figures-meaning-caveats order only for answers that report an analysis result; rule 13 length tiers in words (conversational reply a few sentences, definition or fact one paragraph, analysis result about two and a half thousand characters); rule 14 and the answer contract keep assumptions and limitations for what changes how the answer is read or trusted; three short examples (chat, definition, inconclusive test) without a bold opener

### v005 exec-style-run-a (2026-10-12)

After the A/B: back to the Run A reader section, example and single length target (v003 text); kept from v004: rule 14 and the answer contract (an assumption or a limitation only when it changes how the answer is read or trusted); rule 13 now says each table within ten rows and allows more than one table when that helps the reader

### v006 exec-m143 (2026-10-13)

VALUE REFERENCES: counts of the period or sample are figures from data, a number worked out from the user's figure is a calculation, an example amount is said in words, money and volume are released in base units (M143 (c), solution 1)

### v007 exec-days (2026-10-13)

VALUE REFERENCES: a new reference kind {{data.<data_request_id>.<range_id>.dates}} for the trading dates of a prepared data request's range (EXEC-DAYS); check_references v2 takes a draft (solution 2, tool description)

### Catatan EXEC-PROSE (2026-10-13, tanpa snapshot baru)

Snapshot memakai profil dev tanpa `AI_ENABLE_TABLE_DIRECTIVES`, jadi bagian TABLES (dan kalimat EXEC-PROSE di dalamnya:
teks di sekitar tabel singkat, angka baru dari analisis atau diff/ratio/abs/chg, contoh nominal dengan kata) tidak
tercatat di sini; teksnya ada di `TABLE_DIRECTIVE_RULES` (`app/orchestrator.py`) dan diuji `tests/test_exec_prose.py`.
Prompt router (aturan periode dengan kata) tercatat di `AI_ROUTER.md`; deskripsi `check_references` v3 di Tool_Catalog
round T.
