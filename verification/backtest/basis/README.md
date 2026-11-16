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
