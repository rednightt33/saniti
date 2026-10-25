# Technical indicators — alignment of the terminal HTML, Feature 04 and the AI catalog

Inspection only (2026-10-25); nothing was changed. Inputs: `03-terminal-right-panel.html` (user upload, 3,990 lines),
`Technical_Indicators_53_Frontend_Display_Spec.xlsx` (user upload), `features/feature04/engine.py`,
`Feature_04_Technical_Indicator(_INDEX)` and `AI_calculation_catalog` read live through pgweb (read-only).

## 1. The three sources

| Source | What it holds | Calculation basis |
|---|---|---|
| HTML (`indRegistry` line 770, engine `TA` lines 1733–2005) | 53 indicators I01–I53, user-adjustable parameters, computed in the browser | own JavaScript; EMA/RMA seeded with the SMA of the first n values; population stdev; TradingView-style ATR (first bar TR = high − low) and ADX (RMA seeds) |
| Excel spec | the same 53: parameters (126), formula outlines, outputs (76), display rules; marked `SPEC_ONLY_NOT_EXECUTABLE`; "TypeScript is runtime calculation source of truth" | formula outlines; seeds/zero-denominator policies left to the implementer |
| Feature 04 (`features/feature04/engine.py`, version `feature04-v3-smi14-5-5-th40-talib0.6.8-c0.6.4`) | 15 fixed-parameter values (SMA 20/50, EMA 12/26/50/200, RSI 14, MACD 12/26/9, ATR 14, BB 20/2, ADX 14) + 24 TA-Lib candlestick codes, inside bar, SMI 14/5/5 and swing state; full history from the first price row (2018) | TA-Lib 0.6.8; MACD from stored EMAs; engine header: TradingView "ATR first-bar treatment NOT claimed equivalent" |
| `AI_calculation_catalog` | one ACTIVE row per Feature 04 column (57 stock + 57 index) describing exactly the TA-Lib formulas and seeds above | mirrors Feature 04; no rows for the other 38 HTML indicators |

## 2. Parity test on live data (HTML engine run on the stored OHLC, compared with Feature 04)

Tickers BBCA (2,123 bars), GOTO (1,082), IHSG (2,125), full history from the first price row.

| Feature 04 column | First valid bar equal | Max relative difference | Verdict |
|---|---|---|---|
| sma_20, sma_50, bb_middle_20 | yes | 0 | identical |
| ema_12, ema_26, ema_50, ema_200 | yes | ≤ 7e-15 | identical (floating point) |
| rsi_14 | yes | ≤ 5e-13 | identical |
| macd, macd_signal, macd_histogram | yes | ≤ 1.4e-10 | identical |
| bb_upper_20, bb_lower_20 | yes | ≤ 1.1e-12 | identical (both population stdev) |
| **atr_14** | **no** (HTML bar 13, F04 bar 14) | up to 8.5% | differs during warm-up: HTML puts bar 0's high − low in the seed (TradingView), TA-Lib skips bar 0; difference decays, last > 1e-9 about one year after the first bar |
| **adx_14** | yes (bar 27) | up to 3.6% | differs during warm-up: RMA (Pine) vs Wilder-sum (TA-Lib) seeding; same decay |

Starting point matters for every recursive indicator (EMA, RSI, MACD, ATR, ADX). The HTML engine run on data that
starts later than Feature 04 differs by more than 0.1% for: EMA 200 ≈ 310–430 bars, MACD signal ≈ 150, EMA 50 ≈
80–130, ADX ≈ 100–120, RSI ≈ 60–95, ATR ≈ 50–80 bars (BBCA and GOTO loaded from 2025-01-01; BBCA from 2021-01-01).
GOTO loaded from 2021 matches because 2021 precedes its listing, i.e. the browser saw the full history.

Scripts: `verification/terminal_api/parity/compare.js`, `warmup.js`; they read `ta_engine.js`, lines 1733–2005 of the uploaded HTML plus `module.exports = TA;` (not committed: user source).

## 3. Other differences found

1. RSI with zero gains and zero losses in the window (a flat price): TA-Lib/Feature 04 returns 0; the HTML returns
   `null`. Not hit on BBCA/GOTO/IHSG; likely on illiquid or suspended stocks.
2. RVOL: Excel/HTML default excludes the current bar (`include_current_bar=False`); `Feature_01.volume_ratio_20d` and
   the Statistics panel ("volume ÷ 20D average") include it.
3. Indicators in Feature 04 that the 53 do not have: SMI 14/5/5 with swing state, 24 candlestick patterns, inside bar.
4. 38 of the 53 have no database counterpart; the AI cannot compute or cite them today.
5. The display bucket holds price from 2021; Feature 04 starts in 2018, so recursive indicators in the browser start
   later than in the database.

## 4. Options to align (for the user's decision)

A. **One convention: TA-Lib (Feature 04 as reference).** Change the HTML/TypeScript ATR and ADX (and RSI flat case)
   to TA-Lib's convention; no database change. Small and safe; the browser then equals the database and the AI,
   and differs from TradingView's own chart only in the first ~year of a ticker's history.
B. **One convention: TradingView/Pine.** Change Feature 04 ATR/ADX (new calculation version, recompute all history,
   update `AI_calculation_catalog`). Larger; matches TradingView charts.

Independent of A/B:
- Publish the full price history (from 2018-01-02, the first price row) instead of 5 years: price files are ~2 KB per ticker-year (≈ +6 MB), so
  every recursive indicator in the browser starts from the same first bar as Feature 04.
- One TypeScript calculation module for the 53, with a parity test suite whose expected values come from Feature 04
  for the 15 shared outputs (and from TA-Lib run offline for the other 38).
- Decide whether the AI should also know the other 38 (catalog entries only, or computed columns).

## 5. HTML engine vs TA-Lib 0.6.8 for indicators outside Feature 04 (BBCA, full history, Excel defaults)

Why it matters: the AI sandbox follows "TA-Lib first, then AI_formula_reference" for registered methods
(`apps/market-python-sandbox/app/spec.py`, CONVENTIONS), and model-written code may call TA-Lib directly.

| Result | Indicators |
|---|---|
| identical (≤ 1e-10) | WMA, KAMA, Aroon up/down, Williams %R, ROC, Momentum, TRIX, Ultimate Oscillator, PPO (EMA), BOP, StdDev (population), A/D line, MFI, Donchian upper, Stochastic %D |
| identical after warm-up (ATR seed only) | NATR, +DI, Chaikin oscillator |
| tiny | Stochastic %K: first value 2 bars earlier in the HTML (TA-Lib waits for %D), max rel 6e-5; CCI max rel 1.8e-3 |
| convention differs | Parabolic SAR (initial trend/extreme point; up to 19%), Stochastic RSI (TA-Lib STOCHRSI's fast %K is not smoothed; the HTML smooths K like TradingView), CMO (TA-Lib smooths gains/losses like RSI; the HTML uses plain sums as in Chande), OBV (TA-Lib starts at the first bar's volume, the HTML at 0: a constant offset) |

The `AI_formula_reference` entries for the 38 should therefore state the HTML convention and, where it differs,
the TA-Lib function it must not be replaced with (as CONVENTION_NOTES does for CALC_028/CALC_044).
Script: `parity/dump_html.js` + the TA-Lib comparison in this session's scratchpad.
