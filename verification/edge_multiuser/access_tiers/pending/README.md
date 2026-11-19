# Checker tests waiting for a user decision

These tests were written by an independent checker. They fail on the current code because the behaviour they expect is
a user decision that is not taken yet. They sit here, outside every suite, so CI stays green. They are not skipped: the
decision lands with the test, changed to match it, in the suite it came from.

| File | From | Decision | Goes back to |
|---|---|---|---|


No test waits here now. The last one, `test_r2_trace_beta_live.py` (C2-TRACE, re-check round 2 of Phases 0-3b,
2026-11-19, ERRORS R2-38), went back with the two-site design (EXEC.md EXEC-MU-ACCOUNTS "Production environment":
EDGE_SITE beta|live, the queues' `site` column, the seed's mark; fix round, track site) to
`apps/edge-bff/tests/test_r2_trace_beta_live.py`, changed to the decision: the checker wrote it for a beta with the
switch on and a live site with it off, the pairing the decision reversed (config.validate refuses both outside a
developer machine); it holds the same rule for the decided pairing.

The one before it, `c1-phase3b.test.ts` (C1, Phase 3b, `4188e3cf`, ERRORS M482), went back with
O3b-1 (CONTRACT.md 8b "3b follow-up", decided 2026-11-18) to `apps/backtest-worker/tests/c1-phase3b.test.ts`, changed to
the decision: the technical built-ins (`rank_by` adx/rsi/vol, the `macd` card, the ATR stop, target and chandelier) are
accepted without their indicator; `rank_by` `fnet` and the `broker` and `top5` cards are refused without their flow item.
