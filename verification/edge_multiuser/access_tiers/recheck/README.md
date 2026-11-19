# Re-check of the EDGE multi-user Phases 0-3b (ultracode, xhigh)

User request 2026-11-18: "Cek juga fase sebelumnya, bisa? Jangan sampai fase 3C di bangun dari broken block fase2
sebelumnya." Phase 3c (branch of the session, built on main bf273f52) waits until the findings that affect it are fixed.
EXEC.md, EXEC-MU-ACCOUNTS, "Phase 3c and the 3b follow-up", holds the status and the user's words.

This folder keeps the re-check's work in Git so that a usage-limit stop, a restart of the session's machine or a new
session loses nothing (user 2026-11-19: "please pause and stop apabila limit reached 5 hours dan save work supaya
kejadian sebelumnya tidak hilang").

## Contents

| Path | What it is |
|---|---|
| `r1_findings.json` | Round 1: 46 findings of seven finders (one lens each), ids R1-1 to R1-46 |
| `r1_checked.json` | Round 1: what each finder checked and found sound |
| `r1_verdicts.json` | Round 1 cross-check: three refuters per finding (reproduce, code path, specification and decisions); all 46 survive; side notes of the refuters |
| `r1_seen.json` | The short list handed to round 2 (titles, classes, notes), so round 2 reports only new defects |
| `r1_tests/*.patch` | The round 1 failing tests (nine commits on main bf273f52). They fail on purpose until the fix round; kept as patches so CI does not run them |
| `workflows/*.js` | The workflow scripts of each round, to run again in a new session |

Later rounds add `r2_*` files the same way.

## How to continue

- Restore the failing tests on a branch of main: `git checkout -b recheck-tests bf273f52 && git am
  verification/edge_multiuser/access_tiers/recheck/r1_tests/*.patch` (local only; the fix round makes them pass and then
  moves them into the app test folders).
- A workflow stopped by the usage limit is resumed in the same session with its run id (`resumeFromRunId`): finished
  agents come from the cache and only the stopped ones run again. In a new session, run the script from `workflows/`
  with the saved findings as its input instead.
- Workflow scripts from 2026-11-19 on stop starting new agents after the first agent that fails (a limit stop shows as a
  failed agent), so a stop leaves the finished work intact and nothing is half-run.
