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
| v008 | 2026-10-15 | [table-rows-fifty](history/v008-2026-10-15-table-rows-fifty/system_prompt.md) | 38,697 | `527c0a76a4aa` | `48bceaa503bc` | user 2026-10-15: "malah saya mau sampai 50 kalau bisa. Di tampilan di frontend, tapi bisa di collapse/ expand. Agar datanya rinci dan jelas, lengkap"; "Ok masukan EXEC U4"; go "Ok jalankan" |
| v009 | 2026-10-15 | [text-values-stored](history/v009-2026-10-15-text-values-stored/system_prompt.md) | 39,130 | `d2930510576d` | `48bceaa503bc` | user 2026-10-15: "setiap WHERE = '' maka harus wajib menggunakan value dari get dimension value, or else rejected. Rule ini AI harus tahu before hand"; "O1 masukan exec"; go "Ok jalankan" (EXEC-IMPL-1016 Fase 1) |
| v010 | 2026-10-15 | [turn-brief-facts](history/v010-2026-10-15-turn-brief-facts/system_prompt.md) | 39,130 | `d2930510576d` | `667c512aab9c` | user 2026-10-15: O2 "saya setuju hanya untuk router diberi tahu fungsi dan kemampuan setiap jalur"; O3 "OK masukan exec", signal "Dari isi jawaban"; O5 "Sisanya OK untuk O5"; go "Next lanjutkan tanpa minta saya naikan limit" (EXEC-IMPL-1016 Fase 2) |
| v011 | 2026-10-15 | [names-to-search-values](history/v011-2026-10-15-names-to-search-values/system_prompt.md) | 39,099 | `322029a86b77` | `667c512aab9c` | EXEC-IMPL-1016 Fase 3 (O1 dictionary), user 2026-10-15: "Next lanjutkan tanpa minta saya naikan limit"; matching "Alias + persis + potongan" |
| v012 | 2026-10-16 | [metric-path-when-offered](history/v012-2026-10-16-metric-path-when-offered/system_prompt.md) | 39,119 | `e25cd0b3d4df` | `4098ec4dd2c0` | EXEC-1018B E3/E8, user 2026-10-16: "Ini masuk E3 (merapikan aturan) --> OK", go "Jalankan." |
| v013 | 2026-10-16 | [exec-1018b-next-step](history/v013-2026-10-16-exec-1018b-next-step/system_prompt.md) | 39,190 | `f9c74fe4abd9` | `4098ec4dd2c0` | User 2026-10-16: "1. OK 2. Skip E10 3. OK 4. Otomatis 5. OK ... Jalankan." (EXEC-1018B Fase 4, E9 b/c) |
| v014 | 2026-10-16 | [exec-1018b-fast-prefix](history/v014-2026-10-16-exec-1018b-fast-prefix/system_prompt.md) | 41,594 | `235a54f89172` | `ef9b0ecbca7d` | User 2026-10-16: "1. OK 2. Skip E10 3. OK 4. Otomatis 5. OK ... Jalankan." (EXEC-1018B Fase 5, E2 and A3) |
| v015 | 2026-10-19 | [exec-fastlane-len-goal-answers](history/v015-2026-10-19-exec-fastlane-len-goal-answers/system_prompt.md) | 41,594 | `235a54f89172` | `ef9b0ecbca7d` | User 2026-10-19: 'Selain yang tidak saya sebutkan harus dirubah dengan goal based instead of hardcode'; 'Teks final CITING AND CHECKS ... OK'; 'Ok, execute' (AI_FASTLANE_GOAL_ANSWERS on dev) |
| v016 | 2026-10-20 | [exec-1020-citing-groups](history/v016-2026-10-20-exec-1020-citing-groups/system_prompt.md) | 41,594 | `235a54f89172` | `ef9b0ecbca7d` | Ok sesuai, masukan exec (2026-10-20); Ya oke, jalankan semua end to end |
| v017 | 2026-10-20 | [onboard-fixed-income-feature04](history/v017-2026-10-20-onboard-fixed-income-feature04/system_prompt.md) | 41,727 | `e47165812f9f` | `ef9b0ecbca7d` | Ok view saja ya untuk no 1. Jalankan. (EXEC-ONBOARD-1, 2026-10-20: expose Price_Fixed_Income and Feature 04; AI refers to stored indicator columns instead of computing them) |
| v018 | 2026-10-21 | [rules-1021-in-period-emit-json-units](history/v018-2026-10-21-rules-1021-in-period-emit-json-units/system_prompt.md) | 41,837 | `5a5788480a39` | `ef9b0ecbca7d` | user 2026-10-21: "Masukan exec dan eksekusi. #7 — satuan pada emit_json, #6 — in_period (masker baris)" |

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

### v008 table-rows-fifty (2026-10-15)

EXEC-UI-1015 U4: a table shows the rows the user asked for, ten for an unnumbered ranking, every row up to fifty for a breakdown that lists each group; more than fifty offers Excel; rows are cut in code only for an asked top N (rule 13 and TABLES)

### v009 text-values-stored (2026-10-15)

DATA NEED: every text value in a scope is a stored value (categories from column_values or get_dimension_values; entity codes the user wrote typed as written, never checked with get_dimension_values; a name looked up in its reference table first, ask when it matches several codes); replaces 'take exact values from get_dimension_values and never type a member list yourself' (O1 early, M164)

### v010 turn-brief-facts (2026-10-15)

final-response schema: optional facts field (entities, event dates with their meaning, periods, definitions, with sources); fast-lane decisions note: default readings of open words (net buy, foreign investor type, implementation close) and send the data need early; the turn's notes go as one brief (no prompt text change in the system prompt itself)

### v011 names-to-search-values (2026-10-15)

DATA NEED and the legacy analysis rule: names, initials or part of a name (BRI, Mandiri) are matched with search_values on the request's own table and column; replaces the lookup_reference name lookup (O1 dictionary, M164).

### v012 metric-path-when-offered (2026-10-16)

DATA SOURCES: the metric path holds when query_metric is offered in the turn (a read-only turn gets neither the tool nor the METRICS menu, E8).

### v013 exec-1018b-next-step (2026-10-16)

Final response gains needs_computation (a read-only turn hands a calculation to CONTINUE) and offered_action (a short yes runs the offer); the contract names offered_action; the read-only class note asks for needs_computation instead of an offer in prose.

### v014 exec-1018b-fast-prefix (2026-10-16)

E2: the fast lane gets its own static prefix without the research plan, plan form and findings sections (insight rule kept as INSIGHTS; data needs in mode ANALYSIS). A3: the snapshot renders the real dev profile (run memory, merged steps, table directives, the dev registry's tools from AI_TOOLS.md's Railway snapshot) and the schema with memo_note and next_step; the fast prefix is kept as fast_prompt.md. Fast lane prefix: [25,415 chars](history/v014-2026-10-16-exec-1018b-fast-prefix/fast_prompt.md), sha256 `d8e071fb16a8`.

### v015 exec-fastlane-len-goal-answers (2026-10-19)

Fast prefix only: rule 13 length cap, WRITING, TABLES and VALUE REFERENCES length wording replaced by goal-based rules (table limit kept); new CITING AND CHECKS section. Standard prompt and schema unchanged. Fast lane prefix: [27,539 chars](history/v015-2026-10-19-exec-fastlane-len-goal-answers/fast_prompt.md), sha256 `67dbef029144`.

### v016 exec-1020-citing-groups (2026-10-20)

Fast prefix (AI_FASTLANE_GOAL_ANSWERS): CITING AND CHECKS in five groups (answer shape, tool arguments, data lifetime and recovery, evidence, reproduction) with ids copied exactly, expiry recovery, kept working tables, same-as claims naming what differs, statistics in the model's own code by default; rule 13 table rows up to fifty (M185). Standard prefix unchanged. Fast lane prefix: [28,991 chars](history/v016-2026-10-20-exec-1020-citing-groups/fast_prompt.md), sha256 `e7cb230d4ff3`.

### v017 onboard-fixed-income-feature04 (2026-10-20)

Outside-data rules no longer give yields as an example of data outside the catalog; every outside-data rule adds: an indicator or candle pattern a Feature column already stores (a formula's stored_in) is read from that column, not computed again. Fast lane prefix: [29,124 chars](history/v017-2026-10-20-onboard-fixed-income-feature04/fast_prompt.md), sha256 `e81903b9d9a6`.

### v018 rules-1021-in-period-emit-json-units (2026-10-21)

data-need step 3: in_period is a row mask (frame[in_period(frame, request)]), not listed as a data reader; value-reference units name emit_table or emit_json; CITING AND CHECKS A3: emit_json fields declare units, with a right and a wrong example (EXEC-RULES-1021) Fast lane prefix: [29,480 chars](history/v018-2026-10-21-rules-1021-in-period-emit-json-units/fast_prompt.md), sha256 `97f8f9ee1abc`.
