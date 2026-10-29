# Matrix B: coverage of I28..I53 (26 indicators)

Read-only audit. No file in `/home/user/saniti` was changed (`git status` is clean). No Railway call, no EDGE HTTP call. The only database access was SELECT and EXPLAIN through pgweb. TA-Lib 0.6.8 on C 0.6.4 (the Feature 04 pin, `features/feature04/requirements.txt`) was installed in a scratch venv, so the TA-Lib claims below were tested, not reasoned.

## Evidence files

All are under `/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/audit/matrix_b/`:

- **E1** `compare_summary_26tickers.txt`: TS `F[key]` against TA-Lib 0.6.8 and Feature 04. It covers 26 tickers on their full history from the first price row: BBCA, GOTO, BNBR, AYAM, BLTA, TLKM, plus 20 deterministic random tickers listed in `random_tickers.txt`.
- **E2** `compare_report_6.txt` and `compare_report_random20.txt`: the same results per ticker.
- **E3** `startdep2_report.txt` (scale-normalised, 1e-9 × series max) and `startdep_report.txt` (relative): start dependence when history starts on 2021-01-04, 2024-01-02 or 2025-01-02 (BBCA, TLKM, BNBR).
- **E4** `f01cmp_report.txt`: comparison with `Feature_01_Stock_Daily`.
- **E5** `bench_report.txt`: CPU cost.
- **E6** `edge_checks_report.txt`: code-behaviour checks.
- **E7** `residue_report.txt`: floating-point residue on flat windows.
- **E8** `xlsx_params_I28_I53.txt`, `xlsx_I28_I53.txt`, `xlsx_panes.txt`: the uploaded spec workbook.
- **E9** `registry_I28_I53.txt`: the registry rows.

Scripts: `fetch.py`, `run_ts.mjs` (node 22, imports `apps/edge-bff/terminal/src/calc/indicators.ts` directly), `compare.py`, `startdep*.py`, `f01cmp.py`, `bench.mjs`, `edge_checks.mjs`.

## 1. Storage: what already exists for these 26 rows

| Class | Rows | Evidence |
|---|---|---|
| Stored in Feature 04 as a column (default only) | I30 ATR → `atr_14` | identical: max rel 0, same first bar and nulls, 26 tickers / 39,092 bars (E1) |
| Derivable exactly from Feature 04 columns (default only, SQL expression, no schema change) | I28 %B = (close − bb_lower_20)/(bb_upper_20 − bb_lower_20); I29 BBW = 100·(bb_upper_20 − bb_lower_20)/bb_middle_20; I31 NATR = 100·atr_14/close | max rel 0 / 3.1e-16 / 2.8e-16, null patterns equal (E1) |
| Derivable from Feature 04, approximate | I32 StdDev = (bb_upper_20 − bb_middle_20)/2 | ≤ 1e-14 rel, but 1.3e-9 on 80 BNBR flat-window bars (cancellation) |
| Equal to a Feature 01 column (default only) | I35 volume SMA 20 = `volume_avg_20d`; I37 RVOL 20 = `volume_ratio_20d` | max rel 0 to 1.5e-11, same nulls, 4 tickers (E4) |
| Similar name, different formula (do not reuse) | I33 HV against `Feature_01.volatility_20d_ann_pct`: sample stdev of simple returns (migration `20260912_001`, lines 200–234), whereas I33 uses the population stdev of log returns | median rel diff 0.25–3%, max 14% (E4) |
| Not stored anywhere | I34, I36, I38–I53 (19 rows) | none |

Feature 04 has no volume-based column at all. All 844 stocks have a Feature 04 row on their latest price date (DB query).

## 2. Formula compatibility (from code, confirmed on live data)

- **TA-Lib.** Every row with a TA-Lib function equals TA-Lib 0.6.8 exactly (rel 0 on 26 tickers, E1): BBANDS-derived I28/I29, ATR, NATR, STDDEV, SMA(V), EMA(V), PPO(V, matype=1) with an EMA signal, OBV, AD, ADOSC, MFI. The composite rows equal their TA-Lib compositions within 4e-11 rel (I33, I37, I42, I48). The few differences are running-sum residue where the true value is about 0 (I34, I45).
- **The one convention gap: I39 Volume ROC.** It is null where V[t−n] = 0; TA-Lib returns 0 there.
- **ATR warm-up difference is gone.** The "atr_14 differs in warm-up" in `verification/terminal_api/INDICATOR_ALIGNMENT.md` §2 described the old HTML engine. The TS now uses `kAtr` (`indicators.ts:138`), and ATR/NATR are identical to Feature 04 from bar 14.
- **The prototype's own engine (lines 866–968) must not be reused.** It differs from the TS on 9 of these 26 rows:
  - ATR: H − L on bar 0 (line 890)
  - HV: sample stdev (line 944)
  - RVOL: excludes the current bar by default (line 948), against the user's 2026-10-25 decision
  - OBV and A/D: start at 0 (lines 951, 958)
  - Chaikin: SMA-seeded EMA (line 960)
  - MFI: different zero-denominator rule (line 771)
  - EOM: 0 instead of null on V = 0 (line 963)
  - KVO: a different formula (line 966)

## 3. Warm-up and recursion classes (default parameters)

| Class | Rows (first valid bar index) | Start dependence (E3) |
|---|---|---|
| Point-wise | I39 (10), I53 (0), I43 Session (0) | none |
| Window | I28, I29, I32 (19); I33 (20); I34 (13); I35, I37, I42, I45 (19); I47 (14); I49 (14) | none in exact arithmetic. Running-sum kernels leave floating-point residue on flat windows at non-integer prices (BNBR: I28 null pattern differs on 412 bars; I29/I32 differ for 822 bars at 1e-9 × scale) |
| Recursive, short memory | I46 (9) ~68–95 bars; I48 (13) ~59–125; I36 (19) ~146–189; I30/I31 (14) ~181–253; I38 (25/33) ~230–330 | settles to 1e-9 × scale after that many bars |
| Recursive, long memory | I52 (55/67) ~433–600 bars | not settled with 429 bars. 58 of 844 stocks have fewer than 600 bars |
| Cumulative, never settles | I40, I41, I44, I50, I51 (0) | the level is offset or scaled by the start forever (last-bar rel diff 0.3%–85%). Only changes, ratios and the level against its own MA are comparable |
| Calendar-anchored | I43 Week/Month/Quarter/Year | depends only on bars inside the period |

**Consequence (INFERENCE).** A screener that computes from a truncated window will not match Terminal, Backtest or Feature 04 for the recursive and cumulative rows. It must compute from the first price row (2018 or listing), as the publisher and Feature 04 do.

## 4. TA-Lib gaps

No TA-Lib function exists for I41 PVT, I43 VWAP, I49 EOM, I50 NVI, I51 PVI, I52 KVO or I53 Market FI.

Composites built from TA-Lib functions exist for I33, I34, I37, I42, I45 and I48. These have no TA-Lib equivalent:
- I32 sample stdev
- the RMA basis of I28/I29

## 5. Cost of a full-market dynamic calculation (E5)

- **Measured (FACT).** After JIT warm-up, all 26 TS functions on BBCA's 2,125 bars take 5.2 ms. The slowest is VWAP at 0.53 ms.
- **Estimated (INFERENCE).** Extrapolated to the 1,330,722 final daily rows, the full market takes about 3.3 s of single-thread CPU for all 26 indicators, and about 0.05–0.4 s for one custom indicator.
- **What this means.** CPU is not the constraint. Loading full history and keeping parity are.

## 6. Recommendations (PROPOSED; implementation is not approved)

- **Use what exists now, with no schema or Feature 04 change:**
  - read `atr_14` for I30
  - derive I28, I29 and I31 in SQL from Feature 04 columns
  - reuse `Feature_01` `volume_avg_20d` for I35 and `volume_ratio_20d` for I37
- **Screener snapshot (a new artifact that needs approval).** One nightly job runs the same TS module on the published full-history price files. It stores the latest value and the previous bar (for crosses), plus an event window, for these defaults: I33, I36, I38, I45, I46, I47, I48. It also stores start-independent derived states for I40 and I44 (and I41/I50/I51 if wanted).
  - Using the same TS module gives parity with Terminal and Backtest by construction.
  - The Backtest worker stays untouched, because `indicators.ts` is not modified.
- **Dynamic-only** (low screening value, weak default evidence, or trivial): I32, I34, I39, I42, I43 Session, I49, I53, and I52 until its formula is confirmed.
- **Custom parameters for any row:** compute dynamically from full history.
- **Condition kinds.** The screener needs a few derived transforms the TS module and Backtest conditions do not have: MA of an output, k-bar change, N-bar high/low, % distance from an overlay. Register them in the screener layer, not in `F`.
  - Restrict "price vs line" to overlays (I42, I43) and to volume overlays (I35, I36 against V).
  - Today the Backtest registry accepts "price vs output" for every indicator, for example close against RVOL. That condition is accepted but meaningless.

## 7. Other facts that matter for the screener

- **`def()` floors `annualization_periods`.** The `LENGTH_KEYS` pattern matches `_periods` (`indicators.ts:239`), so 252.9 behaves as 252 (E6), although the registry types it `number`.
- **Invalid bars are handled differently.**
  - Feature 04 `_valid` breaks the series on inconsistent or negative OHLC and on a missing equity volume.
  - TS `def()` breaks only on non-finite needed inputs.
  - The Backtest loader drops a row without four finite prices instead of breaking (`datafile.ts:137–160`).
  - Live data today has 0 inconsistent OHLC rows and 0 null OHLC rows, and volume is null only for IHSG. So no difference shows now (FACT). Future rows could diverge (INFERENCE).
- **Data shape.**
  - 9.3% of final daily rows have H = L.
  - 40 rows have zero volume.
  - Volume is in shares (BBCA: 366,846,200 on 2026-10-27).
- **Flat windows.** In the last year, 502 Feature 04 ticker-days on 16 tickers have zero-width Bollinger bands, so %B is null. Another 154 have a noise width below 1e-6 × close.
