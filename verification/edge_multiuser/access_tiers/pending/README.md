# Checker tests waiting for a user decision

These tests were written by an independent checker. They fail on the current code because the behaviour they expect is
a user decision that is not taken yet. They sit here, outside every suite, so CI stays green. They are not skipped: the
decision lands with the test, changed to match it, in the suite it came from.

| File | From | Decision | Goes back to |
|---|---|---|---|
| `test_cp0_runner_key.py` | C-P0, re-check round 1 of Phases 0-3b (2026-11-18, finding R1-2) | **Kept here by the user's decision of 2026-11-19** ("leave as is, ini setau saya untuk ai bisa lihat log untuk proses enhancement di belakang"; EXEC.md EXEC-MU-ACCOUNTS "Decisions after the fix round" item 4; CONTRACT.md sections 7 and 18): orc-test-runner keeps `MARKET_AI_ORC_API_KEY` so the AI agents' jobs there may read conversations for improvement work, so this test, which asserts the key is gone, stays outside every suite; it returns only if the user later decides to delete the variable. Before that decision it was a Railway change waiting for the user's go. orc-test-runner still holds `MARKET_AI_ORC_API_KEY` (`.railway/railway.ts`, the live project as code), the Orc key that may name any owner (M475). The code side is done: `apps/orc-test-runner/run.py` reads only `MARKET_AI_ORC_TEST_KEY`, and `apps/market-ai-orc/tests/test_main_key_readers.py` holds that no file the runner runs (its own folder, `scripts/`, `verification/`) reads the main key, so deleting it cannot break the runner. The test turns green only when the main agent deletes the variable on orc-test-runner (the user's go), runs `railway config pull --force` and `railway config plan`; it cannot pass by a code change, and in `apps/market-ai-orc/tests/` it would hold every edge-bff deploy (backend-tests.yml is in its check suite) | `apps/market-ai-orc/tests/` (its `ROOT` is `parents[3]` from that folder), unchanged, in the commit that records the deletion |

The one before it, `test_r2_trace_beta_live.py` (C2-TRACE, re-check round 2 of Phases 0-3b, 2026-11-19, ERRORS R2-38),
went back with the two-site design (EXEC.md EXEC-MU-ACCOUNTS "Production environment":
EDGE_SITE beta|live, the queues' `site` column, the seed's mark; fix round, track site) to
`apps/edge-bff/tests/test_r2_trace_beta_live.py`, changed to the decision: the checker wrote it for a beta with the
switch on and a live site with it off, the pairing the decision reversed (config.validate refuses both outside a
developer machine); it holds the same rule for the decided pairing.

Before it, `c1-phase3b.test.ts` (C1, Phase 3b, `4188e3cf`, ERRORS M482), went back with
O3b-1 (CONTRACT.md 8b "3b follow-up", decided 2026-11-18) to `apps/backtest-worker/tests/c1-phase3b.test.ts`, changed to
the decision: the technical built-ins (`rank_by` adx/rsi/vol, the `macd` card, the ATR stop, target and chandelier) are
accepted without their indicator; `rank_by` `fnet` and the `broker` and `top5` cards are refused without their flow item.
