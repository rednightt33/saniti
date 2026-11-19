# Checker tests waiting for a user decision

These tests were written by an independent checker. They fail on the current code because the behaviour they expect is
a user decision that is not taken yet. They sit here, outside every suite, so CI stays green. They are not skipped: the
decision lands with the test, changed to match it, in the suite it came from.

| File | From | Decision | Goes back to |
|---|---|---|---|

| `test_r2_trace_beta_live.py` | C2-TRACE, re-check round 2 of Phases 0-3b (2026-11-19) | The two-site design (EXEC.md EXEC-MU-ACCOUNTS: two edge-bff services on one database; open). The tests hold that a shared row made under one site's rules is read and changed only under those rules: a queued job is dispatched by the rules of the site that queued it, and a start of one site does not rewrite user #1's password identity set on the other. The design decides how (a site column on the queue tables and one loop per site, or one switch state for both, or a seed that never copies while another site has the switch on); the tests change to match it | `apps/edge-bff/tests/` (its imports are relative to that folder) |

No other test waits here now. The last one, `c1-phase3b.test.ts` (C1, Phase 3b, `4188e3cf`, ERRORS M482), went back with
O3b-1 (CONTRACT.md 8b "3b follow-up", decided 2026-11-18) to `apps/backtest-worker/tests/c1-phase3b.test.ts`, changed to
the decision: the technical built-ins (`rank_by` adx/rsi/vol, the `macd` card, the ATR stop, target and chandelier) are
accepted without their indicator; `rank_by` `fnet` and the `broker` and `top5` cards are refused without their flow item.
