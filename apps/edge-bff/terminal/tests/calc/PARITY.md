# Indicator parity (T1): `src/calc/indicators.ts`

Run 2026-10-25 against `verification/terminal_api/INDICATOR_SPEC.md`. Rule: same first valid bar, same null bars, and
relative difference `|a-b| / max(|a|,|b|) <= 1e-9` on every bar of the full history (from the first price row).

- **Tickers.** BBCA, GOTO, IHSG and 20 tickers drawn with `random.Random(20261025).sample(...)` from the 842 tickers
  that have final daily prices and Feature 04 rows (BBCA and GOTO excluded): KOCI ISEA UNVR DEWI CLAY SHIP STAR PBID
  LION AYAM YPAS KEJU INOV BPFI TRST SMDR BNBR ASBI IBOS LFLO. The table reports the 23-ticker run (full-precision
  expected values, 1,619 tests, all passed). The committed fixtures (`fixtures/`, 4.9 MB) hold BBCA, GOTO, IHSG and the
  first five random tickers (KOCI ISEA UNVR DEWI CLAY), with TA-Lib and reference values rounded to 11 significant
  digits. That rounding moves a comparison by at most 5e-12. On those fixtures the largest measured difference is 5.0e-11.
  IHSG has no volume, so the volume rows cover 22 tickers. Alternative parameters run on GOTO only.
- **Oracles.**
  - Feature 04: the stored `Feature_04_Technical_Indicator(_INDEX)` values, calculation version
    `feature04-v3-smi14-5-5-th40-talib0.6.8-c0.6.4`, read on 2026-10-25.
  - TA-Lib: TA-Lib 0.6.8 Python on C 0.6.4, through `tools/gen_talib.py`.
  - Reference: the `TA` engine of `03-terminal-right-panel.html`, through `tools/gen_html.mjs`. The script applies the
    spec's conventions as three patches: no true range on the first bar (I30); RSI is 0 when gain plus loss is within
    1e-14 (I13); fast %K is 0 on a zero range (I14).
- **Comparison.** Feature 04 and TA-Lib rows are compared strictly. The kernels repeat TA-Lib's order of operations,
  so nearly every value is the same double; the only differences are 1–2 ulps on three outputs. The reference engine
  sums in a different order, so for it a difference within 1e-12 of the series' largest value also counts as equal.
  In practice that is rounding residue such as 3e-14 against -2e-15 where both should be 0.
- **Rerun.** From `apps/edge-bff/terminal`: `npx vitest run tests/calc`. To rerun on other tickers: run
  `tools/fetch_live.py`, then `tools/gen_talib.py`, then `tools/gen_html.mjs` into a directory, and run
  `CALC_FIXTURES=<dir> npx vitest run tests/calc`. Add `CALC_REPORT=<file>` to get the per-output numbers.

| Key | Source | Compared against | Tickers | Max relative difference | First valid bar | Result | Notes |
|---|---|---|---|---|---|---|---|
| `sma` (I01) | FEATURE_04 | Feature 04 sma_20, sma_50; TA-Lib SMA(MEDPRICE, 7) | 23 | 0 | equal | PASS | |
| `ema` (I02) | FEATURE_04 | Feature 04 ema_12, ema_26, ema_50, ema_200; TA-Lib EMA(AVGPRICE, 9) | 23 | 0 | equal | PASS | |
| `wma` (I03) | TA_LIB | WMA 20; WMA(TYPPRICE, 9) | 23 | 0 | equal | PASS | |
| `hma` (I04) | HTML | reference (9 close; 16 hl2) | 23 | 0 | equal | PASS | |
| `kama` (I05) | TA_LIB | KAMA 10; KAMA 5 | 23 | 0 | equal | PASS | Follows TA-Lib: ER = 1 when the n-bar path sum is within 1e-14 (the reference used 0), so it differs from the reference on flat windows |
| `macd` (I06) | FEATURE_04 | Feature 04 macd, macd_signal, macd_histogram; TA-Lib EMA 5 − EMA 35, signal EMA 5 (the Feature 04 method) | 23 | 0 | equal | PASS | |
| `adx` (I07) | FEATURE_04 | Feature 04 adx_14; TA-Lib PLUS_DI, MINUS_DI 14; ADX/PLUS_DI/MINUS_DI 7 | 23 | 1.1e-15 (adx vs Feature 04); 0 vs TA-Lib | equal | PASS | 1 ulp against the values Feature 04 computed on Railway. If TR is 0, DX is skipped, as in TA-Lib. `di_length` ≠ `adx_smoothing` generalises TA-Lib's single period. With `di_length` = 1, TA-Lib's DI drops the ×100; this module does not |
| `aroon` (I08) | TA_LIB | AROON 14; AROON 25 | 23 | 0 | equal | PASS | |
| `supertrend` (I09) | HTML | reference with the I30 patch (no TR on bar 0); 10/3 and 7/2.5 | 23 | 0 | equal | PASS | Direction is equal on every bar |
| `donchian` (I10) | TA_LIB | MAX(H, 20), MIN(L, 20), basis (u+l)/2 | 23 | 0 | equal | PASS | |
| `keltner` (I11) | HTML | reference with the I30 patch: ATR style (all tickers); TR style with SMA basis on hlc3; HL_RANGE style | 23 | 0 | equal | PASS | The TR style has no TR on bar 0 (TA_TRANGE). This is visible only with `length` = 1 |
| `psar` (I12) | TA_LIB | SAREXT(start = increment = 0.02, max 0.2), asserted equal to SAR; SAREXT 0.01/0.03/0.25 | 23 | 0 | equal | PASS | `sar` = abs(SAREXT), `direction` = sign |
| `rsi` (I13) | FEATURE_04 | Feature 04 rsi_14; TA-Lib RSI(O, 7) | 23 | 2.3e-16 | equal | PASS | RSI is 0 when gain plus loss is within TA-Lib 0.6's epsilon (1e-14). This happens after long flat stretches (for example BNBR) |
| `stoch_rsi` (I14) | HTML | TA-Lib STOCHRSI fast %K (fastd 1), then SMA 3, SMA 3, on all bars; reference with the I13 and I14 patches (14/14/3/3 and 7/10/1/5 on ohlc4) | 23 | 0 | equal | PASS | 3,094 of 73,438 K/D bars read a flat RSI window (range < 1e-9). Rounding noise in RSI decides %K there, in TA-Lib and in the reference alike. These bars equal TA-Lib but are counted, not compared, against the reference; there 1,054 K bars differ |
| `stochastic` (I15) | TA_LIB | STOCH 14/3/3 (SMA); STOCH 5/1/3 | 23 | 0 | equal | PASS | K starts on the same bar as D, as in TA-Lib (2 bars later than the reference). 0 on a zero range |
| `williams_r` (I16) | TA_LIB | WILLR 14 | 23 | 3.8e-16 | equal | PASS | 0 on a zero range, as in TA-Lib (the reference gave null) |
| `roc` (I17) | TA_LIB | ROC 9 | 23 | 0 | equal | PASS | 0 when the base is 0, as in TA-Lib. Prices are never 0 |
| `momentum` (I18) | TA_LIB | MOM 10 | 23 | 0 | equal | PASS | |
| `cci` (I19) | TA_LIB | CCI 20; CCI 14 | 23 | 0 | equal | PASS | Repeats TA-Lib's circular-buffer summation order. 0 when the mean deviation is 0, as in TA-Lib (the reference gave null) |
| `cmo` (I20) | HTML | reference (14 close; 9 hlc3) | 23 | 0 | equal | PASS | Chande plain sums; not talib.CMO |
| `tsi` (I21) | HTML | reference (25/13/7 close; 13/7/5 hl2) | 23 | 0 | equal | PASS | |
| `trix` (I22) | TA_LIB | TRIX 15; TRIX(MEDPRICE, 9) | 23 | 0 | equal | PASS | |
| `ultimate_osc` (I23) | TA_LIB | ULTOSC 7/14/28; ULTOSC 5/10/20 | 23 | 0 | equal | PASS | The weights are general. TA-Lib sorts the three periods ascending; this module keeps the named lengths |
| `awesome_osc` (I24) | HTML | reference (5/34; 3/20) | 23 | 0 | equal | PASS | |
| `ppo` (I25) | TA_LIB | PPO 12/26 matype 1, signal = talib.EMA(PPO, 9); PPO 5/20/4 | 23 | 0 | equal | PASS | TA-Lib swaps fast and slow when fast > slow; this module does not |
| `bop` (I26) | TA_LIB | BOP | 23 | 0 | equal | PASS | |
| `bollinger` (I27) | FEATURE_04 | Feature 04 bb_upper_20, bb_middle_20, bb_lower_20; BBANDS 10/1.5; BBANDS 20/2 matype 1 | 23 | 0 | equal | PASS | |
| `bollinger_pctb` (I28) | HTML | TA-Lib BBANDS, then (C − lower)/(upper − lower) (the spec takes the bands from I27); BBANDS 10/1 with EMA basis | 23 | 0 | equal | PASS | Against the unpatched reference: 106 bars differ and 923 bars are null only in the reference. These bars are on BNBR, BPFI, IHSG, KEJU and STAR. On flat windows with non-integer prices (for example BNBR 425.5315), TA-Lib's E[x²] − E[x]² leaves stdev noise of about 1e-5 instead of 0 (see the report) |
| `bollinger_width` (I29) | HTML | TA-Lib BBANDS, then 100 × (upper − lower)/middle; BBANDS(MEDPRICE) 15/2.5 with WMA basis | 23 | 0 | equal | PASS | Against the reference: 1,003 BNBR bars show a width of about 5e-6 where the reference shows 0 (same cause) |
| `atr` (I30) | FEATURE_04 | Feature 04 atr_14; TA-Lib ATR 5; SMA(TRANGE, 10) | 23 | 0 | equal | PASS | No TR on the first bar |
| `natr` (I31) | TA_LIB | NATR 14 | 23 | 0 | equal | PASS | |
| `stddev` (I32) | TA_LIB | STDDEV 20 nbdev 1; STDDEV(MEDPRICE, 5) | 23 | 0 | equal | PASS | `stdev_method` = sample uses the two-pass n − 1 form (no TA-Lib function; covered by the edge tests only) |
| `hist_vol` (I33) | HTML | reference (20 log 252; 10 simple 365) | 23 | 0 | equal | PASS | Population stdev |
| `adr` (I34) | HTML | reference | 23 | 0 | equal | PASS | |
| `volume_sma` (I35) | TA_LIB | SMA(V, 20) | 22 | 0 | equal | PASS | |
| `volume_ema` (I36) | TA_LIB | EMA(V, 20) | 22 | 0 | equal | PASS | |
| `rvol` (I37) | HTML | reference with `include_current_bar` = true and `rolling_sma` | 22 | 0 | equal | PASS | Always includes bar t (user 2026-10-25). The registry's `include_current_bar` and `reference_method` are not read |
| `pvo` (I38) | TA_LIB | PPO(V) 12/26 matype 1, signal = talib.EMA(PVO, 9) | 22 | 0 | equal | PASS | 0 when the slow EMA is 0, as in TA-Lib |
| `volume_roc` (I39) | TA_LIB | ROC(V, 10), with null where V[t−10] = 0 | 22 | 0 | equal | PASS | Null follows the spec; TA-Lib returns 0 there |
| `obv` (I40) | TA_LIB | OBV | 22 | 0 | equal | PASS | Starts at the first bar's volume |
| `pvt` (I41) | HTML | reference | 22 | 0 | equal | PASS | |
| `vwma` (I42) | HTML | reference (20 close; 10 hl2) | 22 | 0 | equal | PASS | |
| `vwap` (I43) | HTML | reference: Session and Month StdDev 1; Week Percentage 2 on close; Quarter StdDev 2 on ohlc4; Year without bands | 22 | 0 | equal | PASS | `_breaks` are equal |
| `adl` (I44) | TA_LIB | AD | 22 | 0 | equal | PASS | |
| `cmf` (I45) | HTML | reference | 22 | 0 | equal | PASS | |
| `chaikin_osc` (I46) | TA_LIB | ADOSC 3/10; ADOSC 5/20 | 22 | 0 | equal | PASS | |
| `mfi` (I47) | TA_LIB | MFI 14; MFI 5 | 22 | 0 | equal | PASS | 0 when the n-bar money flow is below 1, as in TA-Lib |
| `force_index` (I48) | HTML | reference | 22 | 0 | equal | PASS | |
| `eom` (I49) | HTML | reference (14 / 1e6; 5 / 1) | 22 | 0 | equal | PASS | |
| `nvi` (I50) | HTML | reference (1000; 100) | 22 | 0 | equal | PASS | |
| `pvi` (I51) | HTML | reference | 22 | 0 | equal | PASS | |
| `kvo` (I52) | HTML | reference (34/55/13; 10/20/5) | 22 | 0 | equal | PASS | |
| `market_fi` (I53) | HTML | reference | 22 | 0 | equal | PASS | |

## Edge cases (`edge.test.ts`, synthetic bars)

- **Registry.** The module has exactly the 53 keys. Every registry output is returned with the length of the bars.
  `DEFAULTS` equal the registry defaults. Missing parameters take the defaults.
- **Flat prices.** No NaN or Infinity anywhere. Each zero-range rule holds: RSI 0, Stochastic and Stochastic RSI 0,
  %R 0, BOP 0, CCI 0, MFI 0, CMO null, %B null, bandwidth 0, ATR 0, stdev 0.
- **Zero volume.** RVOL, VROC, VWMA, VWAP, CMF, Market FI and EOM are null. MFI, PVO, OBV, A/D and Force Index are 0.
  NVI and PVI keep their initial value. A single zero-volume bar makes VROC null only on the bar that divides by it.
- **H = L bars.** BOP is 0, A/D is unchanged and Market FI is 0.
- **Short series.** A single bar or no bars gives arrays of matching length, without throwing. A length longer than
  the series gives nulls only.
- **Missing inputs.** A bar of null, NaN, undefined or Infinity values is null in every output, and every calculation
  restarts after it, as Feature 04 resets its histories. A missing input that an indicator does not read leaves it
  unchanged. A series without volume (an index) gives null volume indicators. Inputs are not modified.
- **Gap of dates.** The gap is not filled. Only VWAP anchors read the dates.
- **Parameters.** An invalid length gives nulls only. Numeric strings work, and fractional lengths are floored.
