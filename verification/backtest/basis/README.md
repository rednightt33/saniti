# Broker basis around corporate actions (EXEC-BACKTEST-REVAMP P9, measured 2026-11-16)

Why: the published prices before 2026-09-12 carry each later action's adjustment, the broker lots do not always
(ERRORS M450, M458 item 2). Option A (user 2026-11-16: "A dulu") publishes, per action, the factor that puts broker
prices on the price basis. This folder holds the read-only measurement the plan rests on.

- `fetch.py`: per action (type, years), the Regular-board broker VWAP and the published high, low and close on each
  session within 21 days of the ex date (pgweb read-only role, credentials from the environment, SELECT only).
- `analyse.py`: the observed basis jump (median VWAP/close before the ex date over the median after it) against the
  factor of the action's terms (`idx_event_annotation` ratio_old, ratio_new, amount_per_share).
- `results_2026-11-16.txt`: the output on dev, actions with an ex date 2016-03-01 to 2026-11-06.

Result (dev, 2026-11-16):

| Action | Measured | Broker on the price basis already | Broker raw, prices adjusted (jump = terms factor) | Other | Too few broker days |
|---|---|---|---|---|---|
| Stock split | 144 | 86 | 0 | 1 | 57 |
| Bonus share | 60 | 37 (+5 with a factor under 2 %) | 6 with a factor of 3.6-5 %, inside the tolerance either way | 2 | 10 |
| Reverse split | 9 | 1 | 0 | 3 | 5 |
| Rights issue, exercise below the market (factor > 1.02) | 107 | 3 | 98 (median difference 0.6 %, 90th percentile 3.3 %) | 6 | |
| Rights issue, exercise above the market (factor < 0.98) | 54 | 38 | 13 | 3 | |
| Rights issue, factor within 2 % of 1 | 45 | (no change expected) | | | |
| Rights issue, too few broker days | 87 | | | | 87 |

Reading: splits and bonus shares are on one basis in both sources (Stockbit adjusts them); rights issues are the
mismatch, and their terms give the factor the prices carry. The "other" rows are data problems to resolve one by one
(for example ATIC 2018-06-25: terms 1000:298666 at Rp 1, a factor of 244 against an observed 1.01).

## The factor the Backtest applies (2026-11-16, P9)

The terms factor of a rights issue above uses the broker VWAP of the last session before the ex date for the traded
price. The publisher (`publisher.py terms_factor`) uses the exact form instead: the published close of that session is
TERP on the scale of the prices after every later action, so f = ((old + new) A - new X) / (old A), with A that close
times the later actions' price factors (the actions are measured newest first). On COCO (exported 2023-2026):

| Factor used | Sessions with the scaled VWAP outside the day's range (1 %) |
|---|---|
| none | 799 of 885 |
| terms with the VWAP (2.692, 1.788) | 165 |
| observed jump (2.686, 1.728) | 44 |
| exact form (2.7097, 1.7429) | 0 |

## The decision rule since Stage C2 (user 2026-11-16 "A", ERRORS M459 item 1)

An action is decided once its 21 days after the ex date have passed, from its own window only: the status compares the
observed jump with the terms in the VWAP form (the traded price of the last session before the ex date), never with the
later actions' factors, so a later action never moves an earlier decision; the exact form above stays the scale of the
lots. `compare_rule.py` runs both versions of `broker_basis` on the fetched windows (each action alone):
`compare_rule_2026-11-16.txt`, 21 of 506 decisions differ, all rights issues but none of the splits and bonus shares.
Among them COCO 2025-10-09 (the exact form taken alone reads a close adjusted by its 2026 rights issue: 1.75 against an
observed 2.686; the VWAP form 2.69: `terms`), and four whose VWAP form misses the observed jump by more than the
tolerance (SQMI 2019, GOLD 2019, PANI 2022, FORU 2026): now `unresolved`, so the Backtest leaves their Flow values
across the action empty rather than scaling them.

`basis_from_export.py` writes the publisher's basis block for an exported ticker (`verification/backtest/lookahead`),
which `real_data.ts` reads. `guard_sample.py` measures the per-day guard of `apps/backtest-worker/src/basis.ts` on 40
stocks for 2025 without any factor (`guard_sample_2026-11-16.txt`): 7,466 sessions, 228 outside the range, all VKTR
(rights issue 2026-10-07; its prices were pulled again on 2026-10-31, its broker lots are raw, so its factor puts them
back); 0 of the 7,238 sessions of the other 39 stocks.
