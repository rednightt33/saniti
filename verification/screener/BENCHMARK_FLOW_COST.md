# Flow cost model: measurement and check (QA unit B, QA4)

Local measurement on 2026-11-07 in the build sandbox, not the Railway service: Intel Xeon @ 2.10 GHz x 4 vCPU (shared
with other builds; load average 0.7 to 1.2 during the runs), Node 22.22.0, `SCREENER_THREADS` 2,
`SCREENER_THREAD_HEAP_MB` 512. Phase 17 measures the service. The numbers are the evidence of the priors in
`apps/edge-bff/screener/src/core/screener-overlay.json` `cost_model.flow` and of the check in section 4.

## 1. The defect

QA4 (900 stocks x 60 broker sessions, the worker end to end): the 4500 ms budget (`SCREENER_MAX_CPU_MS`) did not
protect flow screens. Predicted against measured busy ms before this change: FL10 1 against 889, FL36 1 against 695,
FL38 1 against 631, FL18 anchored at 20 under a percentile 5 against 1962, anchored at 35 6 against 3021, five anchored
at 40 18 against 16 to 19 s (each admitted, each past the 20 s deadline's margin).

Root cause (`apps/screener-worker/src/run.ts`, before):
- a flow kernel was one unit of `bars: sessions` (60) at the indicators' prior of 5.96 ns per bar and length, while
  computeFlow's work grows with the stock's broker rows and brokers (about 1 ms per stock);
- an anchored one was `ceil(sessions computed x (N + 1) / 60)` window calls of that unit;
- the thread recorded an observation only for a series of exactly one cost unit, so a flow indicator under an operator
  (a percentile, every anchored test of QA4) never taught the model, and the window context's build was paid by
  whichever series first touched a stock's view.

## 2. The model (run.ts costUnits, plan.ts costTracker)

- A flow kernel's unit count on a stock is what computeFlow does there: its broker rows in the window (its grid reads
  each once) plus its brokers x (sessions + 1) grid cells (a measure's prefix sums; a Top-N ranking visits every
  broker on every session). An anchored kernel (`anchor_sessions` N) counts, per session it computes, the slice's rows
  (rows x (N + 1) / sessions) and a grid of brokers x (N + 2); the sessions it computes are the screen's reach plus one
  (a value test 1, a percentile over 20 21, the whole series every session from the N-th). The counts per stock come
  from the broker store (`snapshot.ts` brokerRowCount, brokerCounts); the estimate averages them over the survivors.
- The key is the indicator and its choices (its select and switch parameters: `flow:FL23{holders=top,...}`), so a
  Top-K inventory and a selected brokers' one are learned apart (the presets teach the second).
- Once per stock of a screen with a flow condition: the broker-data series (its rows' dates, `flow:broker_data`) and the
  window context (its rows into FlowRows, `flow:context`, built once per view and timed apart by the thread's meter,
  `ThreadSnapshot.contexts`, so it is the context's own cost and not the first flow series').
- Learning: every series computed cold is observed by its cost signature (the units' keys, classes and lengths), its
  time and per unit the bars or units it ran over; the main thread shares the time among the units in proportion to
  their predicted cost (`observeShared`) and keeps an exponential mean per key (alpha 0.2). A series that read a memo
  entry made by an earlier series (the thread's computeFlow memo, a view's Calc) is not observed (`series_reused`).
- Priors (before a key's first measurement): `cost_model.flow.ns_per_unit` per way an entry is computed (the
  registry's `compute`), `context_ns_per_row`, `presence_ns_per_row`; section 3.

## 3. Calibration (BENCH_MODE=calibrate)

Market `apps/screener-worker/tests/bench/market.ts` (QA4's): 900 stocks, 300 price bars, 60 broker days of 25,086 rows
(the publisher writes about 24,500 a day, `P4_BROKER_DAYS.md`); stocks T000-T099 traded by 50 to 100 of 100 brokers a
day (about 10,800 rows and 100 brokers each in the window), the 800 others by 2 to 5 a day (about 500 rows and 85
brokers). Every computed entry alone at its defaults (a value test; "= 1" on a 0/1 signal; a percentile on lots per
transaction and price levels, whose observations hold two kernels and are not in the table) on the whole market, on the
100 large and on the 800 small stocks, each memo-cold; ns per unit from the worker's own observations.

```
cd apps/screener-worker
BENCH_MODE=calibrate node --experimental-strip-types --no-warnings=ExperimentalWarning \
  --import ../backtest-worker/loader/register.mjs tests/bench/flow_cost.bench.ts
```

Results (kernel time without the window context):

| Kernel | compute | busy ms, whole market | ns/unit, whole market | 100 large | 800 small | prior / measured |
|---|---|---|---|---|---|---|
| FL02 | terminal | 687 | 80.0 | 69.3 | 88.6 | 0.84 |
| FL03 | terminal | 618 | 71.7 | 71.4 | 77.5 | 0.94 |
| FL04 | terminal | 712 | 85.4 | 75.3 | 86.4 | 0.79 |
| FL05 | terminal | 816 | 100.4 | 96.0 | 94.0 | 0.67 |
| FL06 | terminal | 947 | 120.4 | 140.0 | 117.3 | 0.56 |
| FL07 | terminal | 628 | 73.5 | 66.4 | 79.2 | 0.92 |
| FL08 | terminal | 836 | 101.1 | 90.1 | 102.1 | 0.67 |
| FL09 | terminal | 952 | 120.6 | 101.0 | 122.9 | 0.56 |
| FL10 | terminal | 776 | 95.4 | 90.2 | 98.5 | 0.71 |
| FL11 | terminal | 602 | 65.4 | 57.0 | 77.2 | 1.03 |
| FL12 | terminal | 630 | 73.7 | 60.2 | 85.1 | 0.91 |
| FL13 | terminal | 459 | 41.8 | 33.2 | 34.1 | 1.61 |
| FL14 | terminal | 545 | 62.1 | 49.7 | 65.0 | 1.08 |
| FL15 | terminal | 481 | 48.5 | 39.2 | 57.6 | 1.39 |
| FL16 | terminal | 590 | 70.6 | 72.8 | 64.9 | 0.95 |
| FL20 | anchored | 435 | 100.7 | 129.5 | 79.1 | 0.91 |
| FL21 | terminal | 834 | 91.2 | 66.8 | 87.5 | 0.74 |
| FL22 | terminal | 750 | 79.1 | 65.6 | 77.4 | 0.85 |
| FL23 | inventory | 1441 | 196.7 | 124.0 | 197.0 | 1.00 |
| FL24 | terminal | 903 | 111.5 | 75.4 | 107.2 | 0.60 |
| FL25 | terminal | 778 | 94.5 | 72.6 | 117.1 | 0.71 |
| FL26 | terminal | 357 | 27.4 | 36.8 | 34.9 | 2.46 |
| FL27 | terminal | 1155 | 160.1 | - | - | 0.42 |
| FL28 | terminal | 236 | 4.4 | - | - | 15.30 |
| FL29 | terminal | 799 | 99.0 | 104.2 | 108.8 | 0.68 |
| FL30 | terminal | 356 | 30.9 | - | - | 2.18 |
| FL32 | terminal | 359 | 30.2 | 29.7 | 27.4 | 2.23 |
| FL33 | terminal | 573 | 62.9 | 55.7 | 70.3 | 1.07 |
| FL34 | terminal | 595 | 63.4 | 55.9 | 62.5 | 1.06 |
| FL35 | terminal | 608 | 68.8 | 51.7 | 76.2 | 0.98 |
| FL36 | terminal | 678 | 78.9 | 67.1 | 95.6 | 0.85 |
| FL37 | terminal | 646 | 69.5 | 45.0 | 74.2 | 0.97 |
| FL38 | terminal | 696 | 82.1 | 66.8 | 95.4 | 0.82 |
| FL39 | terminal | 641 | 74.6 | 62.1 | 80.7 | 0.90 |
| FL40 | terminal | 423 | 40.3 | 36.1 | 40.5 | 1.67 |
| FL41 | terminal | 583 | 62.0 | 56.5 | 58.9 | 1.09 |
| FL45 | anchored | 382 | 84.0 | 122.7 | 74.9 | 1.10 |
| FL46 | terminal | 773 | 91.8 | - | - | 0.73 |
| FL47 | terminal | 595 | 65.7 | 51.4 | 61.3 | 1.02 |
| FL48 | terminal | 864 | 106.4 | 75.8 | 110.2 | 0.63 |
| fnet | foreign_net | 227 | 9.0 | 10.7 | 7.2 | 1.00 |

- The unit count holds across universes: per kernel, the 100 large stocks' ns per unit are 0.63 to 1.46 times the whole
  market's, the 800 small ones' 0.79 to 1.27 (with the rows alone the small stocks cost 8 times the large ones per
  row: the grid, not the rows, is most of a small stock's work).
- Priors, the geometric mean of the kernels of each way of computing: terminal 67.3 ns per unit (37 kernels, 4.4 FL28
  to 160.1 FL27), anchored 92.0 (FL20 100.7, FL45 84.0), inventory 196.7 (FL23), foreign_net 9.0 (fnet). Outside a
  factor of 2 of their prior: FL27 (2.4 times above it), FL26, FL30, FL32 (about half) and FL28 (one fifteenth); the
  model learns each after its first cold run.
- Window context: 102.2 ns per row pooled over 48 whole-market runs (57.5 on the large stocks, 218.5 on the small ones:
  it has a per-stock part of about 0.09 ms the rows do not show; it is a seventh of a flow condition's time).
- Broker-data series: 35 ns per row (`tests/bench/profile_flow.ts`, the whole market, in process; the worker measured
  6.5 on one run of 260,000 rows), a few hundredths of a flow condition's time.

## 4. Check (default mode): QA4's cases cold, then learned

Each case first with parameters no run used before (cold: the key's prior), then with others (learned: the model has
the first run). Predicted = the estimate in the run log (`predicted_ms`), measured = the thread's `busy_ms`, the whole
market (900 stocks) unless named.

| Case | before (QA4) | cold: predicted / measured ms | ratio | learned: predicted / measured ms | ratio |
|---|---|---|---|---|---|
| FL10 Regular+Nego, Foreign, window 5 (learned: Regular, Domestic, 3) | pred 1, busy 889 | 659 / 900 | 0.73 | 914 / 849 | 1.08 |
| FL36 every board, Domestic, window 20 (learned: Regular, Foreign, 10) | pred 1, busy 695 | 641 / 655 | 0.98 | 670 / 690 | 0.97 |
| FL38 window 20, every board (learned: 10, Regular) | pred 1, busy 631 | 634 / 667 | 0.95 | 684 / 701 | 0.98 |
| percentile 20 of FL18 anchored 20, Domestic (learned: anchored 10, Foreign, percentile 10) | pred 5, busy 1962 (percentile 10) | 4549 / 3094 | 1.47 | 962 / 1206 | 0.80 |
| percentile 20 of FL18 anchored 35, every board (learned: anchored 30, Foreign) | pred 6, busy 3021 (percentile 10) | 4939 / 4701 | 1.05 | 4407 / 4413 | 1.00 |
| FL23 Top-5 holders, lookback 20 (learned: Top-3, 10) | pred 255, busy 1659 | 1447 / 1276 | 1.13 | 1281 / 1214 | 1.06 |
| percentile 50 of FL24 window 5 (learned: 40 of window 6) | pred 1070, busy 833 | 1173 / 776 | 1.51 | 1080 / 803 | 1.34 |
| five anchored (FL18, FL19, FL20, FL44, FL45) at 40 under a percentile 10 (learned: Foreign) | pred 18, busy 16,000-19,000 | 20422 / 14336 | 1.42 | 14293 / 14898 | 0.96 |
| seven flow conditions (FL24, FL10, FL36, FL26, FL38, FL18 anchored, FL23 Top-5), windows 5 / 10 | ALL_COMBINED: pred 4321, busy 7295 | 9599 / 8353 (a fresh worker) | 1.15 | 8493 / 8064 | 1.05 |
| FL10 on the 100 large stocks only | - | - | - | 329 / 209 | 1.57 |
| FL10 on the 800 small stocks only | - | - | - | 522 / 631 | 0.83 |
| the same FL10 series again (in the thread's series cache) | - | - | - | 873 / 20 | 43.6 |

The production budget (`SCREENER_MAX_CPU_MS` 4500, `SCREENER_DEADLINE_MS` 20000, unchanged):

| Screen | predicted ms | answer |
|---|---|---|
| five anchored at 40 (cold) | 22057 | 422 LIMIT_EXCEEDED compute_budget (allowed 4500) |
| FL10 alone | 658 | 200, busy 970 ms |
| seven flow conditions, windows 8 | 10197 | 422 LIMIT_EXCEEDED compute_budget (allowed 4500) |
| five anchored at 40 (learned) | 22048 | 422 LIMIT_EXCEEDED compute_budget (allowed 4500) |

The refusal (worker `server.ts` budgetRefusal; the page words it from the catalog's limit entry, whose fix names the
same: "Use fewer custom or flow conditions, shorter lengths, windows or anchors, or a narrower universe."):

> This screen is predicted to need 10197 ms of compute, above the 4500 ms budget; the costliest is condition 6. To pass, use default parameters, fewer custom or flow conditions, shorter lengths, windows or anchors, or a narrower universe (right: one flow condition at its default window on the whole market; wrong: five anchored flow conditions at an anchor of 40 sessions on the whole market). {"limit":"compute_budget","allowed":4500,"needed":10197,"costliest":"c5"}

## 5. Limits

- Local, synthetic market; the priors are a start, each replica learns its own per key from its runs.
- A screen whose series are in a thread's series cache (an earlier run with the same series) costs a fraction of its
  estimate: the estimate does not know the cache, so it errs towards refusing (the memo-warm row of section 4).
- The window context's per-stock part makes a universe of small stocks' contexts about twice its estimate (a seventh
  of the flow condition, so about 10 % of the total).
