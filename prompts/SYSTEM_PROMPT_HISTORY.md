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

## Changes

### v001 deployed-before-reader-rules (2026-10-08)

Versi dasar riwayat. Berisi semua perubahan yang sudah disetujui sampai EXEC-W gelombang A (2026-10-08): audit prompt pass 2, M117, M121 h, M122. Belum ada bagian WRITING FOR THE READER.

### v002 reader-rules (2026-10-08)

M125 C. Bagian baru WRITING FOR THE READER: pembacanya investor perorangan; kesimpulan dulu, lalu angka dengan pembandingnya, artinya, dan batasannya; kalimat pendek dan kata sehari-hari; nama tabel, kolom, output, ID dan kode hanya di pemanggilan tool dan field terstruktur; satu contoh jawaban berbahasa Indonesia. Sembilan kalimat yang bertentangan ditulis ulang: aturan 12, bendera kualitas, data di METHODOLOGY, istilah putusan dan status, kategori sampel, sudut tidak valid, penutup INTERPRETING, instruksi perbaikan temuan, dan LIMITATION jalur lama. Deskripsi skema temuan dan metodologi diselaraskan. Ukuran +8,6% terhadap fixture pass-2, batas baru 1,09.
