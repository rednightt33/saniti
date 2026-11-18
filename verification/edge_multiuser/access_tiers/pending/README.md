# Checker tests waiting for a user decision

These tests were written by an independent checker. They fail on the current code because the behaviour they expect is
a user decision that is not taken yet. They sit here, outside every suite, so CI stays green. They are not skipped: the
decision lands with the test, changed to match it, in the suite it came from.

| File | From | Decision | Goes back to |
|---|---|---|---|
| `c1-phase3b.test.ts` | C1, Phase 3b (`4188e3cf`, ERRORS M482) | O3b-1 (CONTRACT.md 8b), decided 2026-11-18: the technical built-ins (`rank_by` adx/rsi/vol, the `macd` card, the ATR stop/target and chandelier) stay open, so their tests change to "accepted"; `rank_by` `fnet` stays refused, and tests for the `broker` and `top5` cards are added | `apps/backtest-worker/tests/` (its imports are relative to that folder) |
