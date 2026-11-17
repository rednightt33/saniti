# Checker tests waiting for a user decision

These tests were written by an independent checker. They fail on the current code because the behaviour they expect is
a user decision that is not taken yet. They sit here, outside every suite, so CI stays green. They are not skipped: the
decision lands with the test, changed to match it, in the suite it came from.

| File | From | Decision | Goes back to |
|---|---|---|---|
| `c1-phase3b.test.ts` | C1, Phase 3b (`4188e3cf`, ERRORS M482) | O3b-1 (CONTRACT.md 8b): gate the Backtest's built-in options that compute an item (`rank_by`, the `macd` card, the ATR stop/target and chandelier), or record them as part of the Backtest | `apps/backtest-worker/tests/` (its imports are relative to that folder) |
