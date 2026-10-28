# Matrix A: indicators I01-I27 (Trend, Momentum, Bollinger)

Read-only audit, 2026-10-27, repository at `3db84ae`. Every compatibility claim below was checked against the code and re-run on live data today:

- **Feature 04 and the terminal code.** Price history and Feature 04 rows for BBCA, BEKS (the stock with the most H = L bars), RANS (74 bars), TLKM, ANTM and BUMI were read through pgweb. The terminal code `indicators.ts` was run under node 22.
- **TA-Lib.** TA-Lib 0.6.8 (C 0.6.4, the same version Feature 04 pins) was installed in a scratch venv.

All scripts and raw outputs are in `/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/audit/matrix_a/`:

| File | What it holds |
|---|---|
| `f04_vs_ts.txt` | Feature 04 compared with the terminal code |
| `talib_vs_ts.txt` | TA-Lib compared with the terminal code |
| `warmup_cut1000.txt` | how long each indicator depends on where history starts |
| `bench.txt`, `bench_len.txt` | compute cost |
| `donchian_check.txt` | Donchian breakout through the backtest's `compare()` |
| `beks_check.txt` | flat-stretch artefacts on BEKS |
| `ppo_f04.txt` | PPO derived from Feature 04; Bollinger WMA basis |
| `registry_I01_I27.txt` | registry entries I01-I27 |
| `xlsx/I01_I27.txt` | workbook parameters and default evidence |

## Summary table

Legend:
- **Class:** W = finite window (does not depend on where history starts); R = recursive (depends on the start); S = state machine; B = one bar.
- **Evidence** (xlsx Default Evidence): V = VERIFIED_DEFAULT, P = PROPOSED_DEFAULT, RP = REFERENCE_PROFILE_NOT_UI_DEFAULT, RF = REFERENCE_FORMULA_NOT_UI_DEFAULT.
- **Converge:** bars after the history is cut at bar 1000 until the value is within 1e-6 of the full-history run (5 tickers).

| ID | key | default (evidence) | Feature 04 column | Feature 04 vs TS | TA-Lib | TA-Lib = TS | Class | first valid | converge (1e-6) | proposal |
|---|---|---|---|---|---|---|---|---|---|---|
| I01 | sma | 20 close (P) | sma_20 (+sma_50) | identical | SMA | yes | W | 19 | 0 | read Feature 04 |
| I02 | ema | 20 close (P) | only 12/26/50/200 | identical for stored lengths | EMA | yes | R | 19 | 97-120 | snapshot EMA20 |
| I03 | wma | 20 (P) | none | - | WMA | yes | W | 19 | 0 | snapshot (cheap) |
| I04 | hma | 9 (RP) | none | - | none (WMA build 8e-12) | n/a | W | 10 | 0 | dynamic-only or snapshot |
| I05 | kama | 10/2/30 (P) | none | - | KAMA (2/30 fixed) | yes at 2/30 | R | 10 | 10-119 | snapshot |
| I06 | macd | 12/26/9 (V) | macd, macd_signal, macd_histogram | identical | talib.MACD differs; EMA-EMA build equal | MACD no / build yes | R | 25/33 | 153-187 | read Feature 04 |
| I07 | adx | 14/14 (RP) | adx_14 only | identical (8.4e-16) | ADX, PLUS_DI, MINUS_DI | yes (d = a) | R | DI 14 / ADX 27 | 129-211 (BEKS 668) | ADX from Feature 04, DI in snapshot |
| I08 | aroon | 14 (P) | none | - | AROON | yes | W | 14 | 0 | snapshot |
| I09 | supertrend | 10/3 (P) | none | - | none | n/a | S+R | 10 | line 75-100, dir 10-38 | snapshot |
| I10 | donchian | 20 (V) | none | - | MAX/MIN | yes | W | 19 | 0 | snapshot; breakout vs prior bar |
| I11 | keltner | 20 close (V); 2/EMA/ATR/10 (P) | none | - | none (EMA+ATR build 8e-16) | n/a | R | 19 | 64-121 | snapshot |
| I12 | psar | .02/.02/.2 (V) | none | - | SAR/SAREXT | yes | S | 1 | 7-26 | snapshot |
| I13 | rsi | 14 close (V) | rsi_14 | identical | RSI | yes | R | 14 | 149-184 (BEKS 451) | read Feature 04 |
| I14 | stoch_rsi | 14/14/3/3 (RP) | none | - | STOCHRSI fastd = K, then SMA | yes via fastd; fastk differs | R | 29/31 | 171-195 (BEKS 453) | snapshot |
| I15 | stochastic | 14/3/3 (V) | none | - | STOCH | yes | W | 17 | 0 | snapshot |
| I16 | williams_r | 14 close (V) | none | - | WILLR | yes (close) | W | 13 | 0 | snapshot |
| I17 | roc | 9 close (V) | none (Feature_01 return_5/20/60d) | - | ROC | yes | W | 9 | 0 | snapshot or dynamic |
| I18 | momentum | 10 (RP) | none | - | MOM | yes | W | 10 | 0 | dynamic-only acceptable |
| I19 | cci | 20 (RP), 0.015 (P) | none | - | CCI | yes (0.015) | W | 19 | 0 | snapshot; cap length |
| I20 | cmo | 14 (P) | none | - | talib.CMO differs | no | W | 14 | 0 | snapshot |
| I21 | tsi | 25 (RF), 13/7 (P) | none | - | none | n/a | R | 37/43 | 147-209 (BEKS 510+) | snapshot |
| I22 | trix | 15 (P) | none | - | TRIX | yes | R | 43 | 108-143 | snapshot |
| I23 | ultimate_osc | 7/14/28 (RP), 4/2/1 (P) | none | - | ULTOSC | yes (ascending periods, 4/2/1) | W* | 28 | 28 (BEKS 510, residue) | snapshot on full history |
| I24 | awesome_osc | 5/34 (P) | none | - | none (MEDPRICE+SMA build) | n/a | W | 33 | 0 | snapshot or dynamic |
| I25 | ppo | 12/26/9 (P) | none (ppo line = 100*macd/ema_26) | line derivable (2.8e-16) | PPO matype=1 + EMA signal | yes | R | 25/33 | 149-191 | snapshot |
| I26 | bop | none (N/A) | none | - | BOP | yes | B | 0 | 0 | dynamic-only |
| I27 | bollinger | 20 close 2 (V); SMA basis (P) | bb_upper_20, bb_middle_20, bb_lower_20 | identical | BBANDS | yes (SMA/EMA/WMA basis) | W (SMA basis) | 19 | 0 | read Feature 04 |

## Patterns

1. **Feature 04 holds the default of only 5 of the 27 (FACT).** They are I01 sma_20, I06 (all three outputs), I07 (adx_14 only, not +DI/-DI), I13 rsi_14 and I27 (all three bands).
   - I02 is stored only at lengths 12/26/50/200, not the registry default 20.
   - The I25 PPO line can be derived from macd/ema_26.
   - The other 21 have no database counterpart.
   - Feature 04 stores only `source=close`. SMA 150/200, which the prototype presets need, are not stored.
2. **Every stored column is identical to the terminal code (FACT, live).**
   - Check: 6 tickers on 2026-10-27 compared with Feature 04 version `feature04-v3-smi14-5-5-th40-talib0.6.8-c0.6.4`.
   - Result: same first valid bar, no null mismatches, maximum relative difference 8.4e-16; atr_14 is equal as well.
   - INDICATOR_ALIGNMENT.md section 2 says atr_14 and adx_14 "differ in warm-up". That compared the old HTML engine. The current module (kAtr, kDmi with TA-Lib seeding; PARITY.md 2026-10-25) supersedes it, so the brief's known fact about ATR/ADX warm-up applies to the HTML reference, not to the terminal code.
3. **TA-Lib.**
   - **Equal at defaults (19):** SMA, EMA, WMA, KAMA, ADX/DI, AROON, MAX/MIN, SAR, RSI, STOCH, WILLR, ROC, MOM, CCI, TRIX, ULTOSC, PPO (matype=1 plus a separate EMA signal), BOP, BBANDS. Maximum relative difference is 3.6e-16 or less.
   - **TA-Lib function has a different convention (do not call it directly):** talib.MACD (seeds the fast EMA at the slow lookback; first bar 33 instead of 25; up to 78% off in warm-up); STOCHRSI fastk (unsmoothed; the terminal K is TA-Lib's fastd); talib.CMO (Wilder-smoothed; about 10 points off); talib.PPO with its default matype 0 (SMA).
   - **No TA-Lib function:** HMA, Supertrend, Keltner, TSI, AO. HMA, Keltner and AO can be built from TA-Lib pieces and match within 1e-11.
   - **Parameters that go beyond TA-Lib:** KAMA fast/slow, ADX with di_length != adx_smoothing, CCI constant, UO weights and period order, %R source, PPO/MACD when fast > slow (TA-Lib swaps), Bollinger RMA/VWMA basis.
4. **Recursion classes (FACT, measured).**
   - **Finite window** (start-independent from the first valid bar): I01, I03, I04, I08, I10, I15-I20, I24, I27 (SMA basis).
   - **Recursive** (need history from the first bar to equal Feature 04 and Backtest; 100-200 bars typical, up to 670-760 on illiquid BEKS): I02, I05, I06, I07, I11, I13, I14, I21, I22, I25.
   - **State machines:** I09 and I12.
   - I23 is finite in exact arithmetic but floating-point dependent on history on flat stretches.
   - The publisher already publishes price from the first stored year, so the terminal and Backtest start where Feature 04 does (publisher.py:319-322, 471-476).
5. **Cost (FACT, this 4-CPU machine).**
   - All 27 defaults over the full history take 6.9 ms per ticker, about 5.8 s for 845 tickers on one core. The cost of a full-market screen is loading about 1.33M bars, not computing.
   - The window-scan kernels are O(N*n): HMA, Aroon, Donchian, Stochastic, StochRSI, Williams %R, CCI. At n=1000, CCI takes 12.6 s for the whole market. The registry has no upper bound on lengths.
6. **Data (FACT).**
   - `Price_Stock_Indonesia_IDX`: 1,330,722 rows, all Daily and final.
   - None fails Feature 04's validity rule, so Feature 04's reset-on-invalid-row and TS's reset-on-non-finite segment identically today.
   - 123,853 bars (9.3%) have H = L and 40 have zero volume.
   - On illiquid flat stretches, history-dependent values appear in both TA-Lib and TS:
     - BEKS RSI is 46.03 on full history against 0 from bar 1000.
     - BEKS ADX is 87.7 against 100.
     - BEKS UO is -3.33 against 0.
   - Feature 04 is current: 828 stock rows on 2026-10-27, matching the 829 priced tickers minus one (INFERENCE: IHSG).
7. **Defect worth recording (FACT).** Donchian upper/lower include the current bar. So `close > upper` and `close crosses_above upper` can never be true, including in the existing Backtest's compare(): 0 hits on 5 tickers, against 72-124 with the prior bar. The screener needs the prior-bar form, which the prototype has (`lag:1`).
8. **The prototype's own engine** (prototype lines 866-968, synthetic data) differs from the terminal code in HMA rounding, PSAR start, ADX/ATR seeds, KAMA, CMO and the Stochastic K start. The screener should call `F[key]` and not port the prototype's `XI`.

## Proposal (PROPOSED, for the approval gate)

- **One nightly screener snapshot.** Compute it with the same TS module (`F`, under node as the backtest worker does) over the published full price history. For every ticker it holds each default output's latest value plus the last K bars, so "within N days" event conditions and chart marks work (the prototype scans 130 bars).
- **Feature 04's role.** For I01/I06/I07-adx/I13/I27, read Feature 04 directly or use it as the parity oracle; the values are identical. Feature 04 itself is not changed (not approved).
- **Custom parameters.** Compute them dynamically on the server on the full history. For finite-window indicators a short tail would do, but full history keeps one rule.
- **Limits and filters.** Add a length cap for the O(N*n) kernels and a liquidity or flat-bar filter for the illiquid-stock artefacts.
