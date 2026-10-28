# html_model: data model, metric catalogue, indicator engine, evaluation and presets of `screener_EDGE_layout.html`

**Scope.** I audited prototype lines 559-1138 (I skipped line 557, the vendored chart library). I checked them against:
- the repository at HEAD `3db84ae` (origin/main, 2026-10-27);
- the live market PostgreSQL, through pgweb (read-only);
- a numeric parity run of the prototype's own indicator engine against `apps/edge-bff/terminal/src/calc/indicators.ts`, on real OHLCV.

Nothing under `/home/user/saniti` was changed.

**Labels.** FACT means seen now in code, data or a measurement. INFERENCE means reasoned from facts. PROPOSED is my recommendation. UNKNOWN means not established.

**Line numbers.** The lead's line map is off by up to 3 lines. This report cites the actual lines: `CAT` 793, bandar helpers 781-786, `XPARAM` 864, `XI` 897, `XK` 972, `XMETA.forEach` 1018, `evalCond` 1055, `PRESETS` 1083, `freshUniverse` 1141, `compute` 1178, `rowVal`/sort 1506-1510, `toBacktest` 1655.

**Evidence files.** All are in `/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/audit/html_model/`:
- `parity_default.tsv`, `parity_custom.tsv`: parity results;
- `catalog.json`, `legacy_catalog.txt`, `registry_catalog.txt`, `presets_resolved.txt`: the prototype catalogue, obtained by executing lines 562-1115 in a Node vm;
- `registry_summary.txt`: the backtest registry: parameters, ranges, outputs, `not_accepted`;
- `columns.txt`: live columns of 14 tables;
- `feature_catalog_flow.txt`: Feature_Catalog formulas;
- `listings_check.txt`: prototype listings compared with the database;
- `scripts/`: `parity.mjs`, `debug.mjs`, `debug_all.mjs`, `legrsi.mjs`, `catalog.mjs`, `bench.mjs`, `listings.py`, `xl.py`;
- `data/*.txt`: OHLCV of BBCA, GOTO, MTDL, DADA and ADRO, read from the database.

---
## 0. Key findings

1. **The prototype runs on its own sample data.** FACT:
   - 94 real IDX tickers (not 95), with prices, volumes, flows, index flags and financials all generated (header comment lines 560-568).
   - 400 synthetic weekday sessions ending 2026-10-23, with no holidays (569-571).
   - 14 brokers (667).
2. **115 screenable metrics** in `CAT`. FACT, counted by execution: 17 legacy Technical, 13 Flow, 32 Fundamental, and 53 registry indicators (`x_*`). The 53 are grouped as Trend 12, Momentum 14, Volatility 8, Volume 5 and PriceVolume 14.
3. **The 53-indicator engine `XI` (897-968) is the prototype's own JavaScript.** FACT: it is not `indicators.ts`. On real data (5 tickers, full history from 2018, default parameters, last 250 bars):
   - **43 match `indicators.ts F`** to within 1e-9 of each series' scale.
   - **10 differ:**
     - `kvo`: a different formula;
     - `hist_vol`: sample instead of population SD, a constant ×1.026;
     - `rvol`: the prototype's default leaves the current bar out; the registry includes it (user decision 2026-10-25);
     - `obv`: starts at 0, not at the first bar's volume;
     - `psar`: a different start and reversal convention;
     - `kama`, `stoch_rsi`, `cci`, `cmo`, `ultimate_osc`: conventions on flat-price windows.
   - `hma` also differs at custom lengths (√n rounded vs floored).
   - `rsi` also differs in long flat stretches (DADA, 45 bars in 2023-07: prototype 48.14, TA-Lib 0).
4. **The legacy Technical and Flow groups re-implement 11 indicators in separate code:** rsi, stoch, macd, adx, bb, atr, supertrend, mfi, cmf, obv, volspike. FACT: on the 5 tickers the legacy versions equal `F` after warm-up. The exceptions are the OBV offset and the RSI flat stretch.
5. **Evaluation is per condition.** FACT:
   - Value and state tests read the last bar.
   - Events and level crosses pass "within n sessions".
   - Match modes are ALL / ANY / AT LEAST k; a near miss is exactly one condition short.
   - This differs from the Backtest, which uses one window for the whole entry and counts any condition true inside it (`conditions.ts` 259-292).
6. **26 presets.** INFERENCE from the database facts:
   - 15 (Bandarmology 6, Technical 9) need only price and broker data, which the database has; they need calculation code.
   - 11 (Fundamental 8, Combined 3) need financial-statement data, which the database does not have.
7. **Real-data gaps.** FACT: the database has no market cap (EXEC-MCAP is planned but waits for "go", EXEC.md 8152), index membership, listing board, special notation, free float, foreign ownership or financial statements. Dividends exist in `idx_event_annotation`.
8. **New data defect.** FACT: `Universe_Equity_Description` has `Sector` and `Industry` swapped for 844 of 844 rows when compared with `IDX_Stock_Universe`. The D01 fix (ERRORS_AND_SOLUTIONS.md line 167) covered only `IDX_Stock_Universe`. This defect has no ERRORS entry. The screener must read sector and industry from `IDX_Stock_Universe`.
9. **The sample foreign flow is look-ahead by construction.** FACT: line 700 builds it from the next 3 sessions' returns (`fwd(i)`). Flow presets therefore look predictive in the demo.
10. **Recommended architecture.** PROPOSED:
    - Compute every technical value with `indicators.ts F`, the single formula module already shared by the Terminal and the Backtest.
    - Compute flow from Feature 02/03/05/06 and `flow.ts`.
    - Keep `XI` only as a UI reference and do not port it.

---
## 1. Synthetic data model (559-742)

### 1.1 Global objects

| Object (line) | What it is | How it is generated | Real counterpart |
|---|---|---|---|
| `N` (569) | 400 sessions per ticker | constant | Per-ticker bar count from `Price_Stock_Indonesia_IDX` (FACT: BBCA 2,125 bars 2018-01-02..2026-10-27; GOTO 1,084 from 2022-04-11) |
| `DAYS` (571) | session dates | 400 weekdays back from 2026-10-23, no IDX holidays | Distinct `date` values in the price table, aligned by date. FACT: 829-835 tickers have a candle on each of the last six sessions (D11 missing candles exist) |
| `LISTINGS` (573-666) | 94 rows `tk\|name\|sector\|industry\|px\|cap\|flags\|board` | hard-coded; `idx` = {LQ45: 'L', IDX30: '3', IDX80: '8' or 'L', ISSI: 'S'}; `notation:''` (666) | See 1.2 |
| `BROKERS` (667) | 14 `[code, name, foreignFlag]` | hard-coded | `IDX_Broker_Profile` (FACT: 112 brokers, `broker_type` Domestic/Foreign). YP (Mirae) is `Foreign` in the database but flag 0 in the prototype |
| `MARKET`, `SECTOR_F` (677) | Gaussian factor series | seeded RNG (`hashStr`/`rng`, 670-675) | none needed |
| `IHSG` (710) | index level | cap-weighted chain of the 94 sample tickers, static weights | `Price_Stock_Indonesia_IDX` ticker `IHSG` (FACT: 2,127 rows 2018-01-02..2026-10-27, `volume` NULL) |
| `T[tk].F` (713-734) | 32 fundamentals | random, "consistent with price" | none in the database (see 2.3) |

### 1.2 Per-ticker fields

`makeTicker` (682-708) returns `{...L, c,o,h,l,v,val,freq,foreign,net,tp,ret,regime,shares,bandarIdx}`. Need classes: **A** = supported, integration only; **C** = requires calculation, inputs in the database; **D** = requires new data; **P** = requires a product decision.

| Field | Prototype generation | Real source (FACT unless marked) | Need |
|---|---|---|---|
| `tk`, `name` | LISTINGS | `IDX_Stock_Universe."Ticker"`, `"Company Name"`: 845 rows (844 `stock/common` plus `IHSG`). **WIKA is in neither the universe nor the price table** | A |
| `sector` | LISTINGS (IDX-IC names) | `IDX_Stock_Universe."Sector"`: 12 values; `Undefined` for IHSG, XCID, XCIS, XSPI. 92 of the 93 sample tickers in the database match; SIDO differs (prototype Consumer Non-Cyclicals, database Healthcare) | A |
| `industry` | LISTINGS | `IDX_Stock_Universe."Industry"`: 59 values. **25 prototype labels do not exist in the database** (e.g. Telecommunication → Telecommunication Services / Wireless Telecommunication Services; Food & Beverage → Processed Foods / Beverages / Agricultural Food Products; Heavy Constructions → Building Construction). `Banks` (preset `bank`) exists | A; the filter list must come from the database |
| `px` | anchor for the synthetic closes | last final `close`. FACT: 62 of 93 sample prices differ by more than 25% from the database close of 2026-10-27 (BBCA 9,850 vs 4,900) | A |
| `cap` (IDR T) | hard-coded | **none.** RAILWAY_CHANGELOG.md 2247: "No market-capitalisation column exists". EXEC-MCAP (EXEC.md 8152-) plans TradingView `market_cap_calc` and `shares_outstanding` into `Price_Stock_Indonesia_IDX`: 820/844 covered, history only from the first ingest; part B (quarterly shares history) also waits for "go" | D (planned) |
| `idx` LQ45 / IDX30 / IDX80 / ISSI | flags (46 L, 26 '3', 71 IDX80, 78 S) | **none** | D |
| `board` Main / Development | LISTINGS (92 Main, 2 Development) | **none** | D |
| `notation` | always `''`; the universe default excludes notation (1141) | **none** (special notation, watch-list board) | D |
| `o,h,l,c` | factor model, scaled so the last close = `px`, IDX tick sizes (`tick` 674) | `Price_Stock_Indonesia_IDX` open/high/low/close where `is_final` | A |
| `v` | shares rounded to 100 (695) | `volume`. FACT: this is **Regular-board shares**. BBCA 2026-10-23: 495,623,900 = Feature_05 Regular `buy_lots` 4,956,239 × 100; MTDL also matches | A |
| `val` = `c × v` | 696 | Traded value. `Feature_03_Stock_Broker_Daily.total_buy_value` per board (BBCA 2026-10-23: Regular 2.5246T, Nego 0.7198T), or close × volume (2.4905T) | C + P (board, definition) |
| `freq` (trades) | val ÷ ticket size, with random spikes (697) | Feature_06 `foreign_buy_freq_1d + domestic_buy_freq_1d` per board, or Σ Feature_05 `buy_freq` (BBCA Regular 68,755). FACT: complete for universe stocks in 2026-08 (15,867/15,867). Regular-board rows of all symbols were 65-83% non-null in 2025-04..2026-08 and 100% from 2026-09; the nulls are non-universe symbols. INFERENCE: the buy-side frequency sum equals the trade count | C |
| `foreign` | `val × (.07·tanh(fwd/vol) + .04·tanh(ret/vol) + .05·regime + noise)`; **`fwd` = the next 3 returns** (699-700) | `Feature_06_Foreign_Domestic.foreign_net_1d` per board (Regular / Nego / Tunai) | A + P (board) |
| `net[14]` | 2-3 "bandar" brokers follow the hidden regime, foreign and domestic brokers share the foreign flow, noise; demeaned so the nets sum to 0 per day (702-704) | Feature_05 `net_value` per broker × investor type × board × day, summed over investor types and boards; Feature_02 rolling 5/20/60 per broker × investor × board | C |
| `tp` | (c+h+l)/3 | from price | C (trivial) |
| `ret`, `regime`, `shares`, `bandarIdx` | internal; regime is the synthetic "truth" | not needed | — |

---
## 2. Metric catalogue (793-865, 1018-1050)

**Operators.** FACT (785-792):
- `NUMOPS` = gt, lt, between. `LVLOPS` = gt, lt, between, xa (crosses above a level), xb (crosses below).
- Custom operators are `state` (a test on the last bar) or `event` (within n sessions).
- `I.last` metrics have no series, so they offer only gt, lt and between.

Abbreviations in the tables below: F = `indicators.ts F`; F01-F06 = Feature_01-Feature_06.

### 2.1 Legacy Technical (17)

| key (line) | Params (default) | Unit | Ops [kind] (default) | Formula as implemented | Lookback; bar used | Real source | Need |
|---|---|---|---|---|---|---|---|
| `price_ma` (795-800) | len 50, kind SMA/EMA | % | above[s] below[s] xa[e] xb[e] rising[s] gt lt between (above) | MA = legacy `SMA` (running sum) or legacy `EMA` (seeded with the first close, emitted from bar len−1; 754). Value = (c/MA−1)×100. xa/xb = close crosses MA (prev ≤/≥, now >/<). rising = MA[t] > MA[t−21] | len (+21); today's close | F.sma / F.ema. Feature_04 has `sma_20`, `sma_50`, `ema_12/26/50/200` | A (SMA). P (EMA seed: first value vs F's SMA seed; INFERENCE: converges after warm-up) |
| `ma_cross` (801-803) | fast 50, slow 200, kind | — | golden[e] death[e] above[s] (golden, n 20) | crossUp/crossDn(fast MA, slow MA); above = fast > slow | slow | F.sma. Backtest `PRICE_ACTION.macross` golden_cross / fast_above_slow, SMA only (conditions.ts 124, 176-178): same cross rule | A |
| `rsi` (804) | len 14 | 0-100 | LVLOPS (lt 30) | legacy RSI (759): seed = mean of the first len gains/losses, then Wilder; 100−100/(1+g/(l‖1e-9)) | len; today | Feature_04.`rsi_14`; F.rsi. FACT: equal except in long flat stretches (DADA 45 bars) | A + P (flat convention) |
| `stoch` (805-806) | len 14, smooth 3, dlen 3 | 0-100 | lt gt between xa xb kxd[e] kxd_os[e] (lt 20) | raw = 100(c−LL(l))/((HH(h)−LL)‖1), 50 before the window; K = SMA(raw, smooth); D = SMA(K, dlen); value K. kxd = K crosses above D. kxd_os = kxd **and K < 25, while the label says "below 20"** | len+smooth+dlen | F.stochastic k,d (equal on the 5 tickers) | A (fix the label) |
| `macd` (807-810) | 12/26/9 | — | xsig[e] zero[e] bdiv[e] hup[s] gt lt (xsig, n 5) | legacy EMAs. Value = histogram. xsig = MACD crosses above signal. zero = MACD crosses above 0. bdiv = `bullDiv` (774): swing low ≤ 3 bars on each side, lower low than the previous swing within 40 bars while the MACD is higher, flagged 3 bars after the low. hup = histogram up 3 sessions | slow+sig; bdiv lag 3 | F.macd; Feature_04 macd/signal/histogram. Backtest `bullishDivergence` (conditions.ts 142) is the same algorithm | A |
| `adx` (811-812) | len 14 | 0-100 | gt lt between xa plus[s] dixa[e] (gt 25) | legacy DMI (762-766), Wilder sums; value ADX. plus = +DI > −DI; dixa = +DI crosses above −DI. No xb | 2×len | Feature_04.`adx_14` (ADX only); F.adx (adx, plus_di, minus_di) | A |
| `bb` (813-815) | len 20, k 2, sq 120 | fraction | lt gt between below[s] brk[e] squeeze[e] (lt 0, n 10) | BB (768): SMA ± k·population SD. Value = %B (0..1). below = c < lower. brk = close crosses above upper. squeeze = bandwidth ≤ its minimum over sq bars including today | len; sq | Feature_04 `bb_*_20` (k 2); F.bollinger / bollinger_width; squeeze needs a rolling minimum | A (bands), C (squeeze) |
| `atr` (816) | len 14 | % | NUMOPS (gt 3) | legacy ATR (767), seeded with the running mean of TR including bar 0 (h−l), then Wilder; value ATR/c×100 | len + warm-up | F.natr (equal after warm-up, measured); Feature_04.`atr_14` / close | A |
| `supertrend` (817-818) | len 10, mult 3 | — | flip[e] bull[s] (flip, n 5) | legacy SUPERTREND (769): standard final-band rules, direction tested against the current final band | len | F.supertrend.direction. FACT: 0 differing bars after bar 30 on all 5 tickers | A |
| `ichimoku` (819-820) | 9 / 26 / 52 | — | above[s] tk[e] (above) | ICHI (770): tenkan and kijun midpoints; cloud top at t = max(spanA, spanB) computed at t−26. above = c > top; tk = tenkan crosses above kijun | s+b | not in the 53, not in Feature 04 | C (new indicator) |
| `breakout` (821-822) | days 20 | — | up[e] dn[e] (up, n 3) | up: c > max(h of the `days` bars before today) (`HH` lag 1). dn: c < min(l) before today | days | Backtest `PRICE_ACTION.breakout` (conditions.ts 170-172): same rule, up only | A (up), C (dn) |
| `hi52` (823) | — | % | NUMOPS (gt −10) | (c / max(h over 250 bars including today) − 1)×100 | 250 | price highs. Feature_01.`high_60d` is close-based over 60 bars: **not equal** | C |
| `lo52` (824) | — | % | NUMOPS (gt 30) | (c / min(l over 250) − 1)×100 | 250 | price | C |
| `ret` (825) | days 20 | % | NUMOPS (gt 5) | (c/c[t−days]−1)×100 | days | Feature_01 `return_{1,5,20,60}d_pct` (same formula) | A for 1/5/20/60, C otherwise |
| `rs` (826) | days 63 | pts | NUMOPS (gt 0) | (c/c[t−d] − IHSG[t]/IHSG[t−d])×100 | d | price + ticker `IHSG`, aligned by date | C |
| `rs_rank` (827) | days 252 | 0-100 | NUMOPS (gt 70); `last` only | count of **all listings** (not the filtered universe) with a lower d-return ÷ (count−1) × 100. A NaN return still counts in the denominator | 252; cross-section | price of every ticker | C + P |
| `volspike` (828) | len 20 | × | gt lt between xa (gt 2, n 3) | v[t] / SMA(v,len)[t−1]: the average of the **previous** len sessions | len | Backtest `PRICE_ACTION.volspike` is identical (conditions.ts 173-175). Not equal to registry `rvol` or Feature_01.`volume_ratio_20d`, which include today | A + P |

### 2.2 Flow and bandarmology (13)

| key (line) | Params (default) | Unit | Ops (default) | Formula as implemented | Real source | Need |
|---|---|---|---|---|---|---|
| `bandar` (830-832; 782-784) | days 10, top 3 | % | acc[s] bigacc[s] dist[s] bigdist[s] gt lt (acc) | Each broker's D-session net sum, sorted descending. B = Σ of the positive values among the first `top`; S = Σ of the negative values among the last `top`. Ratio = (B+S) / Σ_D val × 100. Thresholds: bigacc ≥ 10, acc ≥ 6, dist ≤ −6, bigdist ≤ −10. `BANDAR={acc:4}` at 781 is overridden to 6 at 1082; editable in the Method panel (1622) and saved with screens | F05 per-broker daily net (Σ investor types and boards) → rolling D; denominator F03 `total_buy_value`. `flow.ts top5Accumulation` (108-121) computes the numerator for top 5 in IDR | C + P |
| `topacc` (833) | top 5, days 10 | Rp B | NUMOPS (gt 5) | (B+S)/1e9 | `flow.ts top5Accumulation` (top 5, IDR; its first value is at bar from+n, the prototype's at D−1) | A (top 5), C (other N) |
| `broker` (834) | code YP (14 codes), days 5 | Rp B | gt lt between xa (gt 1) | Σ_D of one broker's net / 1e9 | `flow.ts brokerNet + rollingSum` (82-104; Σ investor types and boards); F02 `net_value_5d/20d/60d` per broker×investor×board (sum the rows) | A |
| `bavg` (835; 786) | days 10 | % | NUMOPS (between −3..3) | At each bar: the top-3 brokers by D-net; average = Σx⁺ / Σ(x⁺/tp) over their net-buy days (a net-weighted harmonic mean of the typical price); value (c/average−1)×100 | F05 `buy_value`, `buy_lots` per broker per day; the true average buy price = buy_value/(buy_lots×100) | C + P |
| `fnet` (836) | days 5 | Rp B | gt lt between xa xb (gt 0) | Σ_D foreign / 1e9 | F06 `foreign_net_{5,10,20,40,60}d` per board; `flow.ts` fnet (all boards) | A for these D, C for others; P (board) |
| `fstreak` (837) | — | days | NUMOPS (gt 4) | consecutive sessions with foreign net > 0, ending today | F06 `foreign_net_1d`. `foreign_buy_days_Nd` are counts, not streaks | C |
| `fpct` (838) | days 20 | % | NUMOPS (gt 3) | Σ_D foreign / Σ_D val × 100 | F06 `foreign_net_turnover_ratio_{1,5,20}d` = 100·ΣF/Σ(FB+DB), per board | A for 1/5/20, C otherwise |
| `freq` (839) | len 20 | × | gt lt xa (gt 2.5, n 3) | trades[t] / SMA(trades,len)[t−1] | F06 frequency columns (see 1.2) | C |
| `silent` (840-841) | days 5, len 20, volx 1.5, move 3 | — | on[s] | SMA(v,days)[t] / SMA(v,len)[t−days] ≥ volx **and** \|c/c[t−days]−1\|×100 ≤ move; needs t > days+len | price | C |
| `mfi` (842) | len 14 | 0-100 | LVLOPS (lt 20) | legacy MFI (771) | F.mfi (equal) | A |
| `cmf` (843) | len 20 | −1..1 | gt lt between xa (gt 0.05) | legacy CMF (772) | F.cmf (equal) | A |
| `obv` (844-845) | len 20 | — | rising[s] high[e] (rising) | OBV starting at 0 (773). rising = OBV > SMA(OBV,len); high = OBV > max of the prior len bars | F.obv; the operators are offset-invariant | A |
| `adv` (846) | len 20 | Rp B | NUMOPS (gt 10) | SMA(c×v, len)/1e9. Also drives the universe `advMin` (default 1) and the "Avg value" column (1158-1159) | F03 `total_buy_value` (Σ boards or Regular), or close×volume | C + P |

### 2.3 Fundamentals (32)

`FUND` (849-853) holds 32 metrics, all `last`-only, with ops gt/lt/between. Defaults are adjusted at 857.

**Synthetic generation (713-733).** Loss-makers are GOTO, BUKA, WIKA, PTPP and about 4% at random. Values are random within ranges scaled by a quality draw, with these rules:
- pe = null for a loss-maker; BBCA is fixed at 22.4.
- pb = pe×roe/100.
- peg = pe/epsG3y when epsG3y > 0.
- grahamRatio = √(pe·pb/22.5).
- `magicRank` (855) = Greenblatt rank (EV/EBITDA rank + ROIC rank) over **all** non-Financials listings with EV/EBITDA and ROIC > 0, computed before any universe filter.
- Bank-only metrics: nim, npl, car, casa, ldr. Banks get null der, roic, evEbitda and intCov; Financials get null grossMargin, curr and altman.

| Metric(s) | Real requirement | Database status (FACT) | Need |
|---|---|---|---|
| `cap` | shares × close | none; EXEC-MCAP pending | D (planned) |
| `pe`, `pb`, `peg`, `evEbitda`, `grahamRatio`, `fcfYield` | EPS, book value, EBITDA, debt, cash, FCF + market cap | none | D (+C) |
| `roe`, `roa`, `roic`, `netMargin`, `grossMargin` | income statement + balance sheet | none | D |
| `revG`, `epsG`, `epsGq`, `epsG3y` | multi-period statements (quarterly and 3-year) | none | D |
| `der`, `curr`, `intCov` | balance sheet, interest expense | none | D |
| `piotroski`, `altman` | 2 years of statements + market cap | none | D |
| `magicRank` | EV/EBITDA + ROIC, cross-sectional | none | D + C + P (population for the rank) |
| `divYield` | trailing DPS / price | `idx_event_annotation` DIVIDEND: 5,301 rows, 628 tickers, 2009-2026, `amount_per_share`, `ex_date`, `currency` | C + P (window, split adjustment, currency) |
| `divYears` | years with a dividend | same table | C + P (consecutive vs total) |
| `payout` | DPS / EPS | no EPS | D |
| `freeFloat` | float shares / total shares | none. TradingView `float_shares_outstanding` was observed in the EXEC-MCAP check (EXEC.md 8167-8168) but is not in its planned columns | D |
| `foreignOwn` | KSEI ownership by investor type | none. `stockbit_insider_transaction` covers only insiders and ≥5% holders | D |
| `nim`, `npl`, `car`, `casa`, `ldr` | bank reports | none | D |

### 2.4 The 53 registry indicators (`x_*`)

**Parameters (`XPARAM`, line 864).** FACT:
- XPARAM is generated from the workbook's 02_PARAMETERS sheet with key, label, def and step or opts only. **It carries no min or max**, although the workbook and `backtest-registry.json` have them.
- Every default equals the registry (lead-verified).
- XPARAM still lists three parameters the registry marks `not_accepted`: `adr.timeframe`, `rvol.reference_method` and `rvol.include_current_bar`. The prototype ignores the option `same_time_of_day`.
- `bop.source` and the obv/pvt/adl calculation parameters are absent, which is consistent with the registry.
- Booleans are strings (`keltner.use_exponential_ma` "true", `rvol.include_current_bar` "false"), while the registry type is `boolean`. `registry.ts resolveParams` refuses a string and never rounds.

**Prototype edit rules (1496).** FACT:
- A number in a step-1 field is silently rounded.
- Any value ≤ 0 or empty is ignored. So the registry-legal 0 cannot be entered for factor, multiplier, the weights, band_1_multiplier, volume_scale, initial_value or constant.
- There is no maximum (the registry caps `std_dev` at 50).

**Shapes.** FACT, from `XK` 972-1016 and the shape builder 1018-1050:

| Shape | Indicators | Screen value (`ser`) | States | Events | Value ops | Default |
|---|---|---|---|---|---|---|
| line (6) | sma, ema, wma, hma, kama, vwma | (c/line−1)×100 % | above, below, rising (line > line 5 bars ago) | xa/xb = close crosses the line | gt lt between | above |
| band (4) | donchian (states and events use the prior-session band, `lag:1`; the value does not), keltner, bollinger, vwap (`dist`) | position in the band (c−lower)/(upper−lower)×100 (NaN if width ≤ 1e-9·c); vwap: (c/basis−1)×100 | abu (c > upper), bll (c < lower), abb (c > basis) | xau, xbl | gt lt between | abu (80..100); vwap abb |
| dir (2) | supertrend, psar | (c/line−1)×100 | up (dir = 1) | flipup, flipdn | gt lt between | up |
| osc (25) | rsi, williams_r, roc, momentum, cci, cmo, trix, ultimate_osc, awesome_osc, bop, bollinger_pctb, bollinger_width, atr, natr, stddev, hist_vol, adr, rvol, volume_roc, cmf, chaikin_osc, mfi, force_index, eom, market_fi | the output | — | xa/xb level crosses | LVLOPS | per `XK.def` (e.g. rsi lt 30, rvol gt 1.5, natr gt 3) |
| pair (8) | macd, aroon, stoch_rsi, stochastic, tsi, ppo, pvo, kvo | line `a` (MACD, Aroon Up, %K, TSI, PPO, PVO, KVO) | asig (a > b) | xsig (a crosses above b), xsigd | LVLOPS on a | xsig (the stochastics: lt 20) |
| adx (1) | adx | ADX | plus (+DI > −DI) | dixa | LVLOPS | gt 25 |
| vol (2) | volume_sma, volume_ema | average volume (shares) | vabove (v > average) | vxa | gt lt between | vabove |
| cum (5) | obv, pvt, adl (EMA 20); nvi, pvi (EMA 255) | cumulative level | cabove (line > **EMA**(line, avg); the label says "average"), crise (line > line 20 bars ago) | cxa | gt lt | cabove |

**Outputs that cannot be screened directly.** FACT: the MACD/PPO/PVO histograms, the band basis values, the ±DI values, and the SAR and Supertrend line values (reachable only through the derived tests).

**Cumulative levels.** INFERENCE: `gt`/`lt` on a cumulative level depends on where the history starts, so it is not comparable across tickers.

**Mapping to the Backtest.** INFERENCE, from `conditions.ts` OPS (25): gt/lt/crosses_above/crosses_below, with lhs price|output and rhs output|value on the same bar.
- Mappable: line above/below/xa/xb; band abu/bll/abb/xau/xbl (non-lagged); dir up ⇔ direction gt 0 and flips ⇔ direction crosses 0; osc/pair/adx level and pair tests; vol vabove/vxa (registry `price_input` volume).
- Not mappable without new Backtest operators: the derived % values, `between`, `rising`/`crise` (lagged comparisons), cum cabove/cxa (an EMA of an output), and the lagged Donchian states.
- FACT: the prototype's `toBacktest` (1655-1673) maps **none** of the `x_*` keys, only 13 legacy keys. It sends bandar acc, bigacc and gt as "top5 > 0", which loses their meaning.

---
## 3. Indicator engine (866-1051)

### 3.1 How `XI` is built (FACT)
- `XI` is new JavaScript in the page. It neither imports nor mirrors `indicators.ts`; the comment at 866-871 calls it the Screen builder catalogue from the spec workbook.
- Helpers:
  - `xSMA` keeps a running sum and restarts after a non-finite value.
  - `xEMA`/`xRMA` seed with the SMA of the first n finite values and skip later non-finite values.
  - `xSD` is population, or n−1 on request.
  - `xTR` puts h−l on bar 0.
  - `xATR` is xMA of TR by smoothing kind.
- Several `XI` entries reuse the legacy helpers: HH/LL for donchian, stochastic and williams; `CMF`; `MFI`.
- `memo` keys include the parameters as JSON (`xOut`, 1017), so each custom parameter set is computed separately.

### 3.2 Parity on real data (FACT)

Run with `scripts/parity.mjs` on BBCA, GOTO, MTDL, DADA and ADRO, full stored history, last 250 bars, difference ≤ 1e-9 × the max |value| of the F series.

| Result | Indicators | Evidence |
|---|---|---|
| Identical on all 5 tickers (43) | sma, ema, wma, hma, macd, adx, aroon, supertrend, donchian, keltner, rsi, stochastic, williams_r, roc, momentum, tsi, trix, awesome_osc, ppo, bop, bollinger, bollinger_pctb, bollinger_width, atr, natr, stddev, adr, volume_sma, volume_ema, pvo, volume_roc, pvt, vwma, vwap, adl, cmf, chaikin_osc, mfi, force_index, eom, nvi, pvi, market_fi | `parity_default.tsv`. VWAP Week/Month/Quarter/Year anchors also give 0 differing bars over the full BBCA history |
| Equal on liquid tickers, different on flat-price windows (GOTO, DADA) | `kama`: ER = 0 instead of TA-Lib's 1 on a zero path; recursive, up to 6.2e-3. `stoch_rsi`: RSI flat convention (DADA 2025-11-21: prototype ≈0, F 11.1). `cci`: running-sum floating error on flat windows (DADA 2025-11-25: prototype 66.67, F 0). `cmo`: 0 vs null. `ultimate_osc`: NaN vs a value when a TR sum is 0 | `debug.mjs` |
| Always different | `kvo`: the prototype uses sign(Δhlc3)×volume, F the Klinger dm/cm volume force; about 99% of scale, often a different sign. `hist_vol`: sample vs population SD, ×1.026 constant. `rvol`: the default leaves the bar out; with `include_current_bar:"true"` it equals F on all 2,125 MTDL bars. `obv`: starts at 0 vs V[0]. `psar`: first trend from c[1] ≥ c[0], reversal on `<` and the SAR is not clamped at a reversal; direction differs on 12-104 of 250 bars | lines 966, 944, 948, 951, 918; indicators.ts 547, 473, 484, 490, 357 |
| Different at custom lengths | `hma`: final WMA over round(√n) vs floor(√n), e.g. length 15: 1.2e-2 | `parity_custom.tsv` |
| Rare | `x_supertrend` direction is tested against the **previous** final band: 1-22 differing bars over a full history (DADA 22). `x_rsi`/legacy RSI in long flat stretches: DADA 45 bars in 2023-07 (48.14 vs 0). No ticker has 15 identical closes as of 2026-10-27 (0 of 837) | `debug_all.mjs`, `legrsi.mjs` |
| Legacy helpers vs F | RSI14, STOCH k/d, MACD m/sig/hist, DMI adx/+DI, ATR14, BB upper, SUPERTREND dir (0 bars after bar 30), MFI14 and CMF20 are equal over the last 250 bars; OBV has the offset | `parity_default.tsv` LEGACY rows |

### 3.3 History length
- FACT: the matches above use full history from 2018.
- FACT: `INDICATOR_ALIGNMENT.md` §2 measured that TR on bar 0 and RMA seeds make ATR (up to 8.5%) and ADX (3.6%) differ from TA-Lib during warm-up, with the difference decaying over about a year.
- PROPOSED: the screener computes on each ticker's full stored history (or a fixed long warm-up), not on a short window.

### 3.4 Compute cost (FACT, this machine, `bench.mjs`)
- All 53 F indicators at default parameters for 844 tickers × 2,125 bars: **11.5 s** on one thread (13.6 ms per ticker).
- RSI alone for 844 tickers: 79 ms.
- The prototype runs every preset at load to fill the chip counts (`libCounts`, 1187): 26 full screens.

### 3.5 Default vs custom (FACT, 1143-1153, 1352-1362)
- A condition is "Default" when every parameter equals `def` as a string, otherwise "Custom".
- Default mode resets all parameters (`resetParams`).
- "My metrics" (`localStorage` `edge-metrics`) store {key, p, op, v, v2, n}. A condition unlinks from its metric once its parameters change (`syncMetric`).

---
## 4. Evaluation (1052-1068, 1141-1188, 1506-1510)

### 4.1 Value test: gt / lt / between (1062-1067)
- v = `I.last(t,p)` or `series[N−1]`, i.e. today's bar.
- A non-finite v fails with `n/a` (`na:true`, sort null).
- gt and lt are strict. `between` is inclusive, and the bounds are reordered with min/max.
- `+''` is 0, so an empty v2 means 0.

### 4.2 Level cross: xa / xb on a series without a custom override (1065)
- The current value must be finite.
- Bars t ∈ [N−130, N−1] are scanned. xa: s[t−1] ≤ a and s[t] > a. xb: s[t−1] ≥ a and s[t] < a.
- The condition passes when a hit has t > N−1−n, i.e. in the last n bars including today; the window is capped at 130.
- The displayed text and the sort key are the current value, not the cross.

### 4.3 Custom state (1057-1058)
- Passes when `series[N−1]` is truthy (today only). Sort 1/0.

### 4.4 Custom event (1059-1061)
- n = max(1, n|0), with no maximum.
- Passes when the event is true on any of bars N−n..N−1.
- The text is "today" or "kd ago". Sort = 1000 − age; no event sorts at −1.
- Chart markers come from the last 130 bars.
- NaN comparisons are false.

### 4.5 Match (1177-1182)
- The universe filter runs first: index, board, sectors in/out, industries, cap min/max, `priceMin` (default 50: close ≥ 50), `advMin` (default Rp 1B on ADV20), `ffMin`, `exclNotation` (default true), and metric filters `U.fund` evaluated with `evalCond`.
- A = the enabled conditions. k = n for ALL; min(1, n) for ANY; min(+atLeast‖1, n) for AT LEAST. This is the same arithmetic as the Backtest's `entryNeed` (conditions.ts 263).
- `match` = met ≥ k. With no active conditions nothing matches and the table lists the whole universe.

### 4.6 Near miss
- `A.length > 1 && k > 1 && met === k−1`, and not a match. It is impossible in ANY mode.
- It is shown only when toggled. The empty state offers "Match at least n−1" (1549).
- Inconsistency (1599): the preview pill says "Near" whenever met = k−1 without that guard, so a single failing condition shows "Near 0/1".

### 4.7 Conditions met and sorting
- met = the number of passing active conditions (1180), shown as dots and "met/A".
- Matches always sort first. The key then is `match` (met + 100·match) by default, or sym, last, 1D, cap, adv, or `c{i}` (that condition's sort value).
- Nulls go last in both directions. Ties break on market cap, descending.
- A preset may set `sort` (e.g. `['c0','desc']`). Saved screens keep sort, nearMiss and the bandar thresholds (`snapshot`, 1643).

### 4.8 Bar convention and history
- Every test reads the last synthetic session; the Method text at 1623 says the same.
- Bars that exclude today: `breakout` (prior N high/low), `volspike` and `freq` (prior-N average), `x_rvol` default (prior average), Donchian states (prior-session band), `silent` (prior window).
- The "Performance" view is only stock vs IHSG rebased (`perfCard`, 1581-1589), not a screen backtest, despite its comment at 1575.

### 4.9 Difference from the Backtest (FACT)
- `combineEntry` (conditions.ts 269-292) uses one `window_bars` (1-20) for the whole entry. Every condition, states and value tests included, counts if it was true on any bar of that window.
- The prototype gives each event its own n, without a maximum, and tests states and values on today only.
- PROPOSED: the screener contract states its own semantics explicitly and does not reuse `combineEntry`.

---
## 5. Presets (1083-1115)

FACT: all 26 presets use logic `all` and `atLeast` 2, and the default sort unless shown. Each condition is listed as key(params) op value [kind]; `n` is the "within" window.

| id | Category | Conditions | Universe / sort | Real-data feasibility (INFERENCE) |
|---|---|---|---|---|
| bigacc | Bandarmology | bandar(10,3) bigacc [s]; price_ma(20,SMA) above [s] | sort c0 desc | C+P (F05/F03) + A |
| fstreak | Bandarmology | fstreak gt 4; fnet(20) gt 0 | c0 desc | C (F06) + A/P (board) |
| silent | Bandarmology | silent(5,20,1.3,4) on [s]; bandar(10,3) gt 0 | — | C + C+P |
| freq | Bandarmology | freq(20) **xa 2.5 within 3**; ret(1) gt 0 (today; "on the day" is ambiguous) | c0 desc | C (F06 freq) + A |
| bavg | Bandarmology | bavg(10) between −3..3; bandar(10,3) acc [s] | — | C+P |
| follow | Bandarmology | broker(YP,5) gt 1 (Rp B); price_ma(50) above | c0 desc | A (flow.ts) + A |
| minervini | Technical | price_ma 150 above; price_ma 200 above; ma_cross(150,200) above; price_ma 200 rising (vs 21 bars); ma_cross(50,150) above; price_ma 50 above; lo52 gt 30; hi52 gt −25; rs_rank(252) gt 70 (strict, "≥ 70" in the text) | advMin 5 | A + C (hi/lo52, rs_rank cross-section) |
| brk52 | Technical | breakout(250) up within 3 [e]; volspike(20) gt 1.5 (**today only, not on the breakout day**) | — | A |
| oversold | Technical | price_ma 200 above; rsi(14) lt 40 | c1 asc | A |
| golden | Technical | ma_cross(50,200) golden within 20 | — | A |
| macddiv | Technical | macd(12,26,9) bdiv within 10 | — | A |
| rebound | Technical | price_ma 50 above; price_ma(10) xa (close crosses MA10) within 3 [e]; price_ma 20 above; volspike gt 1.3 | — | A |
| squeeze | Technical | bb(20,2,120) squeeze within 15; bb brk within 5 (the "then" order in the text is not enforced) | — | A + C |
| stflip | Technical | supertrend(10,3) flip within 5; adx(14) gt 20 | — | A |
| ichi | Technical | ichimoku(9,26,52) above [s]; tk within 10 | — | C (new indicator) |
| graham | Fundamental | pe lt 15; grahamRatio lt 1; der lt 1; divYears gt 4; epsG3y gt 0 (the text's "P/B < 1.5" has no condition) | — | D |
| piotroski | Fundamental | piotroski gt 6; pb lt 3 | c0 desc | D |
| magic | Fundamental | magicRank lt 21 (ranked over all listings before the filters, so fewer than 20 can remain) | capMin 5, sectorsEx Financials; c0 asc | D |
| quality | Fundamental | roe gt 15; der lt 0.8; netMargin gt 10; epsG3y gt 8 | — | D |
| dividend | Fundamental | divYield gt 5; payout lt 85; divYears gt 4 | c0 desc | C (dividends) + D (payout) |
| garp | Fundamental | peg lt 1; epsG gt 15; roe gt 12 | — | D |
| deep | Fundamental | pb lt 1; pe between 0..10 | — | D |
| bank | Fundamental | roe gt 12; npl lt 3; car gt 18; casa gt 60 | industries [Banks] (exists in the database) | D |
| canslim | Combined | epsGq gt 20; epsG3y gt 10; hi52 gt −20; rs_rank(252) gt 70; roe gt 12 | — | D + C |
| qflow | Combined | roe gt 15; der lt 1; fnet(20) gt 0; price_ma 50 above | — | D + A |
| vacc | Combined | pb lt 1.5; pe lt 12; bandar(10,3) acc | — | D + C+P |

---
## 6. Metric → real source and backend need (consolidated)

| Domain | Metrics | Real source (FACT) | Status |
|---|---|---|---|
| Price only, code exists | 53 `x_*` (via F), legacy price_ma (SMA), ma_cross, rsi, stoch, macd (+bdiv), adx, bb bands, atr, supertrend, breakout up, volspike, mfi, cmf, obv | `Price_Stock_Indonesia_IDX` (is_final) + `indicators.ts F` / `conditions.ts PRICE_ACTION`. Feature_04 holds only sma_20/50, ema_12/26/50/200, rsi_14, macd, atr_14, bb_20, adx_14 | Integration. P: which convention where the prototype differs (§3.2) |
| Price only, new code | ichimoku, bb squeeze, breakout dn, hi52, lo52, ret (other N), silent, `rising`/`crise`/`cabove` derived tests, % distance values | price | Calculation (trivial to moderate) |
| Price + index | rs | price + ticker `IHSG` | Calculation |
| Cross-section | rs_rank, magicRank | every ticker's price / fundamentals | Calculation + P (population) |
| Broker and foreign flow | bandar, topacc, broker, bavg, fnet, fstreak, fpct, freq, adv | Feature_02/03/05/06, `IDX_Broker_Profile`, `flow.ts` | Calculation (rolling D, ranking) + P (board, definitions, thresholds, units: prototype Rp B, Backtest IDR) |
| Dividends | divYield, divYears | `idx_event_annotation` DIVIDEND | Calculation + P |
| Universe attributes | sector, industry | `IDX_Stock_Universe` (not `Universe_Equity_Description`: swapped) | Integration |
| Universe attributes | index membership, board, special notation, free float, market cap | none; market cap planned (EXEC-MCAP) | New data |
| Fundamentals | the other 28 FUND metrics | none | New data + P (source, licence, point-in-time) |

---
## 7. Defects and inconsistencies in the prototype (FACT unless marked)

1. `stoch` `kxd_os` tests K < 25 while its label says "below 20" (806).
2. `x_kvo` does not implement Klinger's volume force (966; compare indicators.ts 547).
3. `x_hist_vol` uses sample SD (944), while F uses population. Feature_01 `volatility_20d_ann_pct` uses sample SD of simple returns: three conventions in the codebase.
4. The `x_rvol` default leaves the current bar out (948), against the user decision of 2026-10-25 recorded in `INDICATOR_SPEC.md` I37. Legacy `volspike` also leaves it out, as the Backtest's `volspike` does.
5. `x_cci` produces garbage values on flat windows (running-sum floating error); `x_ultimate_osc` gives NaN and `x_cmo` gives 0 on zero ranges.
6. `x_psar` start and reversal conventions differ from TA-Lib SAREXT; `x_supertrend` tests against the previous band (rarely differs).
7. Donchian band: the value uses the unlagged band, while its states and events use the lagged one (1025-1027).
8. Cumulative-indicator "N-session average" is an EMA (1046).
9. `rs_rank` and `magicRank` ignore the user's universe; NaN returns still count in the `rs_rank` denominator.
10. Preset texts claim tests the code does not run: graham "P/B < 1.5"; squeeze "then"; brk52 volume "on" the breakout day; stflip and minervini ≥ coded as >.
11. The preview "Near 0/1" pill with one condition (1599).
12. XPARAM offers three parameters the registry refuses, sends booleans as strings, has no min/max, rounds silently and blocks legal zeros.
13. The synthetic foreign flow uses future returns (700).
14. `toBacktest` maps none of the 53 `x_*` keys.
15. Data side: `Universe_Equity_Description` Sector and Industry are swapped (844/844). WIKA is in none of the tables. 25 industry labels and one sector (SIDO) are stale.

---
## 8. PROPOSED flow screener (user: "feel free to benchmark and come up with your own")

Build the flow screener on the validated Feature columns that are already in the database (Feature_Catalog formulas in `feature_catalog_flow.txt`), plus the `flow.ts` helpers, rather than on the prototype's synthetic definitions.

1. **Foreign flow (F06, per board).** These are integration only:
   - `foreign_net_{5,10,20,40,60}d`, `foreign_net_turnover_ratio_{1,5,20}d`;
   - persistence: `foreign_buy_days_{5,10,20,40}d`;
   - abnormality: `foreign_net_zscore_*_base252d`, `foreign_net_percentile_*_base252d`;
   - `foreign_strength_20d/50d` and `foreign_strength_momentum_5d`;
   - acceleration: `foreign_flow_vs_prev_20d/40d`.

   A streak and arbitrary windows need calculation from `foreign_net_1d`.
2. **Broker concentration ("bandar", F03 daily):** `top3_buyer_net_value`, `top3_buyer_share`, `broker_concentration_hhi`, `net_buy_broker_ratio`, `institutional_net_value` vs `retail_net_value` (classified with the current `IDX_Broker_Profile`, which is not point-in-time). Keep the prototype's ratio as a transparent "EDGE accumulation ratio" with `flow.ts top5Accumulation` as the parity reference; window, top-N, denominator and thresholds are a user decision.
3. **One broker (F02):** `net_value_5d/20d/60d` (sum investor types and boards), `buy_day_ratio_20d`, `net_value_zscore_20d`, `largest_buy_day_share_20d`. For other windows use `flow.ts brokerNet/rollingSum`, as the Backtest does.
4. **Frequency and ticket size (F06):** trades = foreign + domestic `buy_freq`; `foreign_avg_buy_value_per_freq_1d` and `*_value_per_freq_change_5d_vs_prev20d` as a large-ticket proxy; `foreign_freq_imbalance_20d`; `foreign_value_freq_sign_mismatch_1d`.
5. **Average cost:** a true broker average buy price from F05 `buy_value/(buy_lots×100)` instead of the typical-price proxy.
6. **Price-volume:** use the registry indicators (cmf, mfi, obv, adl, chaikin_osc, force_index) through F.

---
## 9. Product decisions this area raises

1. **Formula convention for the 53.** PROPOSED: `indicators.ts F` everywhere, accepting the differences listed in §3.2. Alternatively, port the prototype's XI as the user's spec.
2. **Legacy catalogue.** Keep the 17 legacy Technical metrics, which duplicate 11 registry indicators, or map the presets onto the `x_*` keys (rsi → x_rsi and so on). Ichimoku, hi/lo52, rs, rs_rank, silent, breakout dn and squeeze are not in the registry.
3. **RVOL and volume spike:** current bar included (registry, Feature_01) or excluded (prototype default, Backtest `volspike`).
4. **Board scope of the flow metrics:** Regular or all boards. FUTURE_PLAN U5 is still open, and `flow.ts` sums all boards.
5. **Bandar:** formula, window, top-N, denominator and thresholds (acc 4 or 6, big 10). Are the thresholds user-editable and saved per screen?
6. **Fundamentals:** source, licence and point-in-time rules. Until data exists, hide the 8 Fundamental and 3 Combined presets or label them unavailable.
7. **Market cap / free float:** "go" on EXEC-MCAP (parts A and B), and whether free float is added. Then the source for index membership, board and special notation.
8. **As-of date:** the latest final date shared by all tickers, or each ticker's own last bar. Price rows: 829-835 tickers per day in the last week.
9. **Population** for the cross-sectional ranks.
10. **"Within n" limit and semantics:** per-condition n (prototype) or the Backtest's window. Is there a maximum, given that the Backtest window is 1-20?
11. **Parameter validation contract:** registry ranges and integer refusal vs the prototype's rounding and zero rejection; boolean type.
12. **Units:** the prototype uses Rp B and IDR T; the Backtest wire uses IDR.
