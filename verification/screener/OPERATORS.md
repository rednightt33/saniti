# Screener universal operators: specification (EXEC-SCREENER-FLOW-CANDLES, P0; draft for the user's approval, K4)

Status: DRAFT, 2026-11-07. Nothing in this file is built yet. Once the user approves it, it is the reference the
implementation (P2, P3, P5) and the five QA agents (P7) check against. A change to a rule here needs the user's approval.

Sources this file follows (checked in the code on 2026-11-07):
- User decisions: EXEC.md `EXEC-SCREENER-FLOW-CANDLES` (operators 1-15; two layers "indicator setup + operator"; C =
  cross-sectional population is the user's filtered universe; K1 = broker data 60 sessions; K3 = the old RS rank keeps its
  fixed population; K5 = no further operators; K7 = "=" and "!=" only for whole-number outputs).
- Conventions reused, not re-invented:
  - percentile (mid-rank) and z-score (sample SD, n-1) of `verification/terminal_api/flow_indicators/FORMULAS.md`
    "Shared conventions";
  - crosses: `apps/edge-bff/backtest/src/core/conditions.ts:52-61` (`compare`): above = previous `x <= y` and now
    `x > y`; below = previous `x >= y` and now `x < y`; a missing value on either bar is no cross;
  - SMA and EMA: `apps/edge-bff/terminal/src/calc/indicators.ts:46-67` (SMA needs N consecutive values and restarts
    after a missing one; EMA is seeded with the SMA of the first N values, alpha 2/(N+1));
  - cross-sectional percent rank: `apps/edge-bff/screener/src/core/xsection.ts:29-44` (`percentRank`), with the
    population of decision C;
  - evaluation date: each stock is evaluated at its own last bar on or before the evaluation date E
    (`screener/src/core/evaluate.ts:77-83`); a flow series at the broker as-of date, labelled (P10 a).

## 1. Terms

- **Series** `x`: one value per session of one stock: an indicator output, a price, a flow indicator output (FL01-FL48,
  with its Terminal setup parameters), or the result of another operator. `x_t` is its value at the evaluation session
  `t`; `x_(t-k)` the value k sessions earlier, counting the stock's own sessions (its price bars), never calendar days.
- **Missing**: a session without a value (no data, not enough history, a zero denominator). A missing value is never
  read as 0. A condition whose value is missing at `t` is **n/a**, not "fail" (the existing NA rule,
  `evaluate.ts:71-75`).
- **Window of N before t**: the N sessions `t-N .. t-1` (today excluded). Used where today is compared with its own past
  (operators 2, 3, 6), so today never dilutes its own baseline.
- **Window of N ending at t**: the N sessions `t-N+1 .. t` (today included). Used where today belongs to the period
  (operators 5, 9, 12, 14).
- **Ready**: a window operator gives a value only when its window has the values its rule needs; otherwise missing
  ("insufficient history").
- **Output type** (decides which operators apply; section 4): K continuous normalised (%, x, 0-1, -1..1), P already a
  percentile or z-score, Rp Rupiah, L lots per transaction, H price level, D consecutive-day count, F 0/1 signal,
  B broker count (FL23).

## 2. Operators

Each operator has: its parameters, its exact rule, when it is missing, its unit, and its limits. "Chain" says what it can
take and give.

### 1. Absolute Value
- Parameters: comparison `>`, `<`, `>=`, `<=`, `=`, `!=`; threshold `X`.
- Rule: `x_t (op) X`.
- `=` and `!=` only on whole-number outputs (types F, D, B; and counts); K7. On any other output they are refused.
- Missing: `x_t` missing -> n/a.
- Strict `>` `<`; inclusive `>=` `<=`.

### 2. Historical Average
- Parameters: average `SMA` or `EMA`; `N`; form `difference`, `ratio` or `percent`; then a comparison (operator 1 or 15).
- Average `A_t` = SMA or EMA of `x` over the window of N before t (the series shifted by one session, then SMA/EMA as
  in indicators.ts).
- Forms: difference `x_t - A_t` (unit of x; "points" for a % output); ratio `x_t / A_t`; percent
  `100 x (x_t / A_t - 1)`.
- Missing: `A_t` not ready, or `x_t` missing; ratio and percent also when `A_t <= 0` (a ratio to a zero or negative
  average has no meaning).

### 3. Historical Percentile (own history)
- Parameters: `N` (baseline); then a comparison (`>=`/`<=`/range on 0-100).
- Rule (mid-rank): `P_t = 100 x (count(v < x_t) + 0.5 x count(v = x_t)) / count(v)`, `v` = the non-missing values of
  `x` in the window of N before t.
- Missing: `x_t` missing; fewer than N sessions since the first non-missing value of `x`; no non-missing `v`.
- Unit: percentile 0-100.

### 4. Change
- Parameters: `N`; form `absolute` (points for a % output), `percent`; then a comparison.
- Rule: absolute `x_t - x_(t-N)`; percent `100 x (x_t / x_(t-N) - 1)`.
- Missing: either value missing; percent also when `x_(t-N) <= 0`.
- Unit: absolute keeps the unit of x (points for %); percent is %.

### 5. Ever / Lookback
- Parameters: an inner condition `C` (any of 1, 2-4 with a comparison, 6, 7, 8, 11-15) and `N`.
- Rule: true when `C` is true on at least one session of the window of N ending at t.
- A session where `C` is n/a counts as not true; the result is n/a only when `C` is n/a on all N sessions.
- Limit: `N <= within_max` (130 today) and, on a flow series, the broker data limit (section 3).

### 6. Z-Score
- Parameters: `N`; then a comparison (in standard deviations).
- Rule: `z_t = (x_t - M) / SD`, `M` the mean and `SD` the sample standard deviation (n-1) of the non-missing values in
  the window of N before t.
- Missing: as operator 3, and when fewer than 2 values or `SD = 0`.
- Unit: standard deviations.

### 7. Relative Comparison
- Parameters: a second series `B` on the same stock (another indicator or output, the same indicator with other
  parameters, the close, another flow indicator), form `difference` or `ratio`; then a comparison.
- Rule: difference `x_t - B_t`; ratio `x_t / B_t`.
- Allowed only when `x` and `B` have the same unit (price with price, % with %, lots with lots, Rupiah with Rupiah);
  otherwise refused with the two units named.
- Missing: either value missing; ratio also when `B_t <= 0`.

### 8. Crossover / Crossunder
- Parameters: direction `above` / `below`; target: a constant `X` or a second series `B` (same unit rule as 7); `N`
  (the cross happened within the last N sessions; 1 = today).
- Rule (the core's `compare`): above at session s: `x_(s-1) <= y_(s-1)` and `x_s > y_s`; below: `x_(s-1) >= y_(s-1)`
  and `x_s < y_s`; `y` = X or B. True when a cross happened on a session of the window of N ending at t.
- A missing value on s or s-1 is no cross on s.
- Limit: `N <= within_max`; flow: section 3.

### 9. Persistence / Frequency
- Parameters: inner condition `C`, `K`, `N` with `1 <= K <= N`.
- Rule: true when `C` is true on at least K sessions of the window of N ending at t. n/a sessions count as not true;
  n/a only when all N are n/a.
- Limit: as operator 5.

### 10. Consecutive / Streak
- Parameters: inner condition `C`, `K >= 1`.
- Rule: true when `C` is true on each of the last K sessions (t-K+1 .. t). An n/a session breaks the run.
- Limit: `K <= within_max`; flow: section 3.
- On FL26 (Net Flow Streak, already a run count) this operator is not offered (section 4).

### 11. Ranking / Cross-Sectional
- Parameters: the series value to rank (`x_t`, or the result of operators 2, 3, 4, 6, 7, 12, 13, 14); then a
  comparison on 0-100.
- Rule: `xsection.ts percentRank`: `100 x #(population values strictly below x_t) / (P - 1)` for a member, ties
  share a rank; every rank in [0, 100].
- **Population (decision C)**: the stocks of the user's filtered universe (after the universe filters, before the
  conditions) whose value at their evaluation session is not missing. P < 2 -> missing.
- The old RS rank (`return_rank`) keeps its fixed population (K3); it is a separate metric.
- A stock outside the population (shown through a chip) is compared with all P members (denominator P), as today.

### 12. Trend / Slope
- Parameters: `N >= 2`; then a comparison (`> 0` rising, `< 0` falling, or against X).
- Rule: ordinary least-squares slope of `x` over the window of N ending at t against the session index 0 .. N-1.
- Missing: any missing value in the window.
- Unit: unit of x per session.

### 13. Acceleration
- Parameters: `N >= 2`; then a comparison (`> 0` accelerating, `< 0` slowing).
- Rule: `slope_N(t) - slope_N(t-N)` (operator 12 on the last N sessions minus the N sessions before them).
- Missing: either slope missing.
- Unit: unit of x per session.

### 14. Distance to Extreme
- Parameters: extreme `highest` or `lowest` over the window of N ending at t (today included, as `rolling_max` /
  `rolling_min`, `transforms.ts:74-94`); form `absolute` (points for %) or `percent`; then a comparison.
- Rule: to the highest `H`: absolute `x_t - H` (0 or below), percent `100 x (x_t / H - 1)`; to the lowest `L`:
  absolute `x_t - L` (0 or above), percent `100 x (x_t / L - 1)`.
- Missing: `x_t` missing, no value in the window; percent also when the extreme `<= 0`. A missing value inside the
  window restarts it (as `rolling_max`).

### 15. Range / Between
- Parameters: `inside` or `outside`, `X <= Y`.
- Rule: inside `X <= x_t <= Y` (both ends included); outside `x_t < X` or `x_t > Y`.
- `X > Y` is refused.

## 3. Limits

- `N` and `K` are whole numbers of at least 1 (2 for 12 and 13).
- Price and indicator series: `N` up to 260 for operators 2, 3, 4, 6, 12, 13, 14 (the range of the existing `lag` /
  `change` arguments); operators 5, 8, 9, 10 up to `within_max` (130), the evaluation tail (`metrics.ts:176-179`).
- Flow series (K1): the broker data holds 60 sessions. The sessions an operator reads plus the flow indicator's own
  window must fit: `N + window_of_the_indicator <= 60` (13: `2N + window <= 60`). The limit is derived from the file's
  depth and the indicator's window, not listed by hand; a request beyond it is refused with both numbers named.
  The built-in baselines of FL08, FL09, FL21, FL37 and FL47 (percentile; 250 in the Terminal) are capped the same way.
- Chain depth: at most 4 operators or transforms in one reference (`transforms.ts:146`).
- Cost: each operator adds cost units to the screen budget (`SCREENER_MAX_CPU_MS` 4500 ms); percentile and z-score over
  N cost about N per session.

## 4. Which operators apply to which output type

| Type | Example | Applies | Not offered, and why |
|---|---|---|---|
| K continuous normalised | FL24, FL38, RSI | 1-15 | — |
| P already percentile / z | FL08, FL21, FL37 | 1, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15 | 2, 3, 6: the value is already against its own history |
| Rp Rupiah | FL02, FL25, FL28, FL31 | 1-15 | — (a Rupiah threshold or rank favours large stocks; said in the help text) |
| L lots per transaction | FL01 | 2, 3, 4, 5, 6, 7 (lots with lots), 8 (against an average or series), 9, 10, 12, 13, 14 | 1, 11, 15: lots depend on the price per share |
| H price level | FL17, FL18, FL42, FL43, FL44 | 2, 3, 4, 5, 6, 7 (e.g. close vs VWAP), 8, 9, 10, 12, 13, 14 | 1, 11, 15: a price level is not comparable across stocks |
| D consecutive-day count | FL26 | 1, 3, 5, 7, 8, 9, 11, 15 | 2, 4, 6, 12, 13, 14: a run grows by one a day; 10: it is already a run |
| F 0/1 signal | FL09, FL27, patterns, candles | 1 (`= 1`), 5, 9, 10 | 2, 3, 4, 6, 7, 8, 11, 12, 13, 14, 15: no magnitude |
| B broker count (FL23) | FL23 | per broker series (a cumulative, b daily, c normalised): 2-14 as their own type; then "at least X brokers" (1) | decided per series type |

FL31 (insider net) is 0 on days without insider trades: 3 and 6 are not offered on it.

## 5. Refusals (AGENTS.md "Gates and evidence": rule, how to pass, right and wrong example, message)

| Refusal | Rule the user sees before | How to pass | Right / wrong | Message names |
|---|---|---|---|---|
| Operator not offered for the output type | the operator list shows only section 4's operators | pick a listed operator | right: FL24 percentile; wrong: FL01 absolute | the indicator, its output type, the operators it takes |
| N or K out of range | the field shows its range | a value inside it | right: N 20; wrong: N 0, N 300 | the field, the range |
| K > N | "K of N" shows both | K <= N | right: 3 of 5; wrong: 6 of 5 | K and N |
| `=` / `!=` on a non-whole output | only whole-number outputs offer them | use `>=`, `<=` or a range | right: FL26 = 3; wrong: RSI = 30 | the output and its unit |
| Units differ (7, 8) | the second series list shows only same-unit series | pick a same-unit series | right: close vs FL17; wrong: FL24 % vs close | both units |
| Flow window beyond the broker data | the N field shows its maximum for that indicator | a smaller N or window | right: FL24 window 10, N 40; wrong: N 55 | N, the window, the 60-session data |
| `X > Y` in a range | "from" <= "to" | swap them | right: 2-8; wrong: 8-2 | both values |
| Chain deeper than 4 | the builder stops at 4 | simplify | — | the depth |

## 6. What the screen shows

- The cell shows the value the comparison reads, in the operator's unit: percentile and rank `0-100`, z-score `σ`,
  change `%` or points, slope per session; a condition (5, 8, 9, 10) shows Yes / No, and 8 the sessions since the cross.
- "Why it passed" names the series, its setup, the operator and its parameters, e.g. "Bandar Balance % (Top 3, 10
  sessions): percentile 250 >= 90 -> 94".
- A flow value carries its broker as-of date when it is older than the price date (P10 a).

## 7. Tests the QA agents run against this file

- Each operator: an independent brute-force computation on real fixture series compared value by value (operators
  2-4, 6, 12-14), and condition truth tables at the boundaries (1, 5, 8-10, 15: equal to the threshold, just above and
  below, missing values, not-ready windows).
- Cross-sectional (11): the population follows the universe filters (a filter change moves the ranks; the old RS rank
  does not move).
- Limits and refusals of section 5, each with its message.
- Chains: an operator over another operator's result equals the brute-force composition.
