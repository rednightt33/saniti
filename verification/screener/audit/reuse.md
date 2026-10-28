# Reuse audit: Backtest and Terminal stack for the EDGE Screener

Read-only audit. Repository `/home/user/saniti` at `3db84ae` (origin/main). `git status` is clean after the audit. No Railway call and no HTTP call to EDGE services were made. The database was read through pgweb with SELECT and EXPLAIN only.

Raw outputs and scripts are under `/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/audit/reuse/`:
- `pack_size.txt`: price-pack and cross-section sizes.
- `warmup_table_scaled.txt`: warm-up of the 53 indicators at their defaults.
- `warmup_long.txt`: warm-up for long custom lengths.
- `timing.txt`: CPU cost.
- `semantics.txt`: VALUE, STATE and EVENT computed from the shared core on live bars.
- `bars_sample.json`: 40 tickers of live bars.
- `scripts/*.mts|py`: the scripts behind these files.

I ran the repository's TS modules directly with `node --experimental-strip-types` (node 22.22). They import and run unchanged.

Labels: **FACT** means seen in code, data or a recorded measurement. **INFERENCE** is a conclusion from facts. **PROPOSED** is a recommendation. **UNKNOWN** could not be checked.

---
## 0. Summary

1. **FACT.** One formula source is already shared by the Terminal chart, the Backtest page and the backtest worker: `apps/edge-bff/terminal/src/calc/indicators.ts` `F`, with 53 keys.
   - Parameters go through `backtest/src/core/registry.ts` `resolveParams`.
   - 0/1 condition series come from `core/conditions.ts` `Calc` and `conditionSeries`.
   - All of these are pure modules with no DOM and no Node API (registry.ts:1-4, conditions.ts:1-10).
2. **PROPOSED: lowest shared layer.**
   - Keep the pure core as is: `datafile.ts`, `flow.ts`, `indicators.ts` `F`, `registry.ts`, `conditions.ts`.
   - Add one new pure module, `core/screen.ts`. It evaluates a condition at an evaluation bar and returns `{value, pass, event_date, sessions_ago, na}`, plus the match count and near miss.
   - The browser preview, a full-market screen service, the daily precompute and later the Backtest all call that module.
   - New operators (`between`, comparing a series with its own lagged value, an indicator of an indicator) belong in `conditions.ts` `compare` or an adjacent module, so the Backtest can adopt them later without a second formula.
3. **FACT.** The existing loading path cannot screen the whole market.
   - Worker `load.ts` `loadMarket` is built per ticker: one `/bundle` answer per ticker, then the files.
   - Every portfolio and preview is capped at 12 stocks (`engine.ts:151` `MAX_PORTFOLIO_TICKERS = 12`; `config.ts:77` may only lower it; `validate.ts:107-113` `pickedStocks`).
   - `/v1/signals` answers only `entry_signals` and `last_signal` per ticker (`contract.ts:308-313`). There are no per-condition values.
4. **Measured (INFERENCE from a 30-ticker sample): the bytes are small.**
   - All daily price history of all 845 tickers is about 16.5 MB gzip (12.4 B/row × 1,330,722 rows).
   - The per-object and per-request overhead is the real cost: 845 objects, 845 `/bundle` grants and audit rows, and 120 s presigned URLs.
5. **Measured CPU cost (sandbox, single thread):**

   | Work | 845 tickers | Per ticker |
   |---|---|---|
   | 5 typical conditions | ≈ 1 s | 1.15 ms |
   | All 53 indicators at their defaults | ≈ 15 s | 17.4 ms |
   | Decoding the price packs | ≈ 4.4 s | 5.19 ms |

6. **Measured: the screener must evaluate on the full published history**, as the Terminal and the Backtest do. With only the last K bars:
   - Cumulative indicators (OBV, PVT, A/D, NVI, PVI) never match.
   - Long custom lengths still differ after 1,000 bars (EMA 200: 1.5e-4; MACD 50/200/50 signal: 2.2e-3).
7. **FACT: Send to Backtest has no landing place.**
   - The Backtest page has no import entry point. A grep for `location.hash`, `#import` or `import=` in `apps/edge-bff/backtest/src` finds nothing.
   - The prototype's `backtest.html#import=<base64>` payload and its legacy-card mapping (`toBacktest`) do not match anything the page reads.

---
## 1. Reuse matrix

### 1.1 Pure core, shared by browser and Node

| Component | What it does | Verdict | Why | file:symbol |
|---|---|---|---|---|
| Indicator formulas | The 53 registry indicators (I01–I53); `{output: (number\|null)[]}` aligned with the bars; a non-finite input breaks the series (outputs null, restart) | **As is** | The only verified formula source: parity with Feature 04 and TA-Lib (`verification/terminal_api/INDICATOR_SPEC.md`, tests `apps/edge-bff/terminal/tests/calc`). The prototype's own `XI` formulas must not be ported (§7). | `terminal/src/calc/indicators.ts` `F`, `DEFAULTS`, `def`, `sma`, `ema`, `rma`, `isN` |
| Display registry | Per indicator: zone (12 overlay, 39 panel, 2 volume), units, guides, colours | **As is** for preview rendering | Says which outputs sit on the price pane | `terminal/src/data/indRegistry.json` |
| Parameter contract | Registry document; checks a condition's parameters (unknown key, type, min/max, enum); fills defaults; never clamps | **As is** (see the I37 caveat in §7) | The 67 integer parameters have `min: 1` and **no max** (count from `backtest-registry.json`), so custom lengths are unbounded | `core/registry.ts` `REGISTRY`, `BY_ID`, `indicator`, `resolveParams`, `calculate`; `core/backtest-registry.json` |
| Per-ticker memo | Memo of indicator outputs per key+params, and of flow series | **As is** | A screen evaluates many conditions on one ticker | `core/conditions.ts` `Calc` |
| Comparison rules | gt, lt, crosses_above, crosses_below; bar 0 never true; NaN false; a cross needs both sides on the previous bar | **As is** for STATE and EVENT. **With change** for `between`, "rising vs N ago", an indicator of an indicator | `OPS` holds only 4 operators (conditions.ts:25). lhs and rhs come from **one indicator instance with one parameter set** (conditions.ts:92-96), so EMA20 vs EMA50 or close vs another indicator cannot be expressed. | `core/conditions.ts` `compare`, `indicatorCondition`, `conditionSeries` |
| Price-action conditions | dip, breakout (close > highest high of the previous N bars), volspike (V ÷ SMA(V,N) of the previous bar), macross (SMA only: golden_cross, fast_above_slow), macd (bullish_divergence, crosses_above_signal, histogram_positive) | **As is** for these | No death cross, no "close below prior N-day low", no EMA-based MA cross | `core/conditions.ts` `PRICE_ACTION`, `priceActionCondition`, `bullishDivergence` |
| Flow conditions | fnet gt/lt, broker gt, top5 gt over N bars, in IDR, on one ticker's broker files | **As is** for a one-ticker preview and ≤ 12 tickers. **Not** for a full-market screen. | Needs each ticker's broker files: 46.2M rows in `Feature_05` (pg_class.reltuples), above `BACKTEST_MAX_BROKER_ROWS` (20M) | `core/conditions.ts` `flowCondition`, `flowConditionShape`; `core/flow.ts` `flowData`, `brokerNet`, `rollingSum`, `top5Accumulation` |
| Entry combination | Backtest "within window" rule: one window for all conditions, states included | **Not for matching**. Reuse only `entryNeed`. | Screener events have their own N each; states must be true **on** the evaluation bar | `core/conditions.ts` `combineEntry`, `combineExit`, `entryNeed`, `WINDOW_BARS` (1–20) |
| Series helpers | Switch-on bars; count of true bars | **As is** for chart markers | | `core/conditions.ts` `switchOns`, `trueBars` |
| Request-level signals | Condition list checks; combined entry per ticker; switch-ons in a period; preview row | **With change**. The request shape and window semantics differ. `runSignals` is the template for "load → Calc per ticker → leave out → warning". | `previewRow` returns only `entry_signals` and `last_signal` (signals.ts:242-245) | `core/signals.ts` `activeConditions`, `requestConditions`, `tickerSignals`, `periodSignals`, `previewRow` |
| Leave-out rules | A condition without any value on the ticker's bars (`INDICATOR_OUTPUT_EMPTY`, `FLOW_OUTPUT_EMPTY`, `FLOW_UNAVAILABLE`) leaves the ticker out instead of failing | **As is**, for "n/a" rows | | `core/signals.ts` `EXCLUDED_CODES`, `unlessLeftOut`, `leftOut` |
| Ranking and liquidity | Ranking scores; liquidity = SMA20(close × volume) | **As is** for sort keys and the ADV filter | The prototype's `adv` is the same definition: `val = c×v` (proto l.697), `SMA(val, 20)/1e9` | `core/signals.ts` `rankScores`, `liquidity`, `LIQUIDITY_BARS` |
| Date utilities | | **As is** | | `core/signals.ts` `isIsoDate`, `byTicker`, `barMap`, `resultCalendar`, `track` |
| Published-file decoding | gunzip with a bomb cap; sha256 and size check against the manifest; price, broker and corporate-action decoding with integrity errors; as-of alignment (IHSG compare); data version | **As is** | Same reading rules as the Terminal (a row without 4 prices is dropped) | `core/datafile.ts` `decodeColumnar`, `inflateVerified`, `priceSeries`, `brokerRows`, `brokerGaps`, `corporateActions`, `asOf`, `dataVersion` |
| Backtest engine | Event clock and trades | **Not needed**, except `portfolioTickers` to check a Send-to-Backtest set | | `core/engine.ts` `prepare`, `run`, `validateRun`, `portfolioTickers`, `MAX_PORTFOLIO_TICKERS`, `LEVEL_LINES` |
| Card → wire mapping | Page card (legacy or registry) → wire condition; display scales (Rp B → IDR, % → fraction) | **As is** for Send to Backtest | | `core/catalog.ts` `legacyToCondition`, `regToCondition`, `LEGACY`, `DISPLAY` |
| Wire types | Request, preview, catalog, limits and error types | **As is** | | `core/contract.ts` `BacktestRequest`, `SignalsPreviewRequest`, `Catalog`, `Limits`, `ApiError` |

### 1.2 Backtest worker (`apps/backtest-worker/src`)

| Component | What it does | Verdict | Why | file:symbol |
|---|---|---|---|---|
| terminal-api client | `/bundle` (`packs: true`), `/manifest`, `/reference`, presigned download, sha check, retries, file-origin allow-list, memory LRU and shared disk LRU | **With change**: reusable as is in a Node screen service for per-ticker loads | No method for a cross-sectional file; `/manifest` carries no `packs` (terminal-api main.py:297-304) | `terminal.ts` `TerminalClient.bundle` (426), `usable` (460), `cached` (467), `file`, `loadTicker` (522), `manifest` (572), `reference` (594), `MemoryCache` (193), `DiskCache` (241) |
| Market loader | Step 1: one `/bundle` per ticker, always, whatever the cache holds (load.ts:116). Then the limits, then the downloads. Re-asks an answer that is too old. Broker data-through check. | **With change** | Built for ≤ 12 tickers. 845 tickers would mean 845–1,690 `/bundle` grants and audit rows per screen. | `load.ts` `loadMarket` (104), `PlannedClient`, `brokerDataThrough` (188) |
| Request checks | Strict field check; condition checks on empty bars; condition id rule | **Pattern reusable**; the 12-ticker cap is not | | `validate.ts` `checkSignalsRequest`, `pickedStocks`, `checkConditions`, `CONDITION_ID` |
| Run entry points | Job and preview runs; published-data checks | **Not as is**. `runSignals` is the closest template. | | `run.ts` `runJob` (112), `runSignals` (196), `checkPublished` (103) |
| Compute threads | Exactly 2 long-lived threads (jobs, previews), one task each (server.ts:106) | **With change**: a screen would need its own thread or service | A screen on the preview thread would queue behind, and block, backtest previews | `compute.ts` `ComputeThread`, `packResult` |
| HTTP server | Key header, preview queue (one at a time), deadline, caller watch, 409 BUSY | **Pattern reusable** | Adding routes means touching the worker the Backtest depends on | `server.ts` `createApp`, `preview`, `callerWatch`, `deadline` |
| Configuration | Limits from the environment (§3.2) | Reuse the pattern | | `config.ts` `loadConfig` |
| Catalog | tickers, name, type, sector, industry; groupings; IHSG first and last bar; flow data-through | **As is** for the universe list and the sector/industry filters | The reference file holds only ticker, name, type, sector, industry (publisher.py:418-431) | `catalog.ts` `buildCatalog`, `groupingsOf` |

### 1.3 edge-bff, terminal-api, publisher, pages

| Component | What it does | Verdict | Why | file:symbol |
|---|---|---|---|---|
| edge-bff backtest relay | Worker client (key, 504 TIMEOUT mapping); relay on the event loop with timeout = `BACKTEST_TIMEOUT_SECONDS` + 30; cancel when the caller leaves; one preview in flight per owner with `client_order`; JSON guard (NaN, Inf, 1e400, lone surrogate); error redaction; gzip pass-through | **As is (patterns)** for a screener relay | | `app/backtest.py` `WorkerClient` (287), `Backtests.ask` (949), `unless_gone` (971), `latest_preview` (1002), `loads` (94), `error_of`, `json_part` |
| edge-bff gateway | Terminal proxy (allow-list GET `manifest\|reference\|history\|logo`, POST `files\|bundle`, httpx timeout 30 s); session cookie (DB lookup per request); CSRF on writes; same-origin POST; 128 KiB body cap | **As is** for preview data | Each `/bundle` through it costs one edge session DB lookup and one terminal-api quota transaction | `app/main.py` `TERMINAL_ROUTES` (34), `forward_terminal` (364), `session` (245), `write` (252), `protections` (221-238) |
| terminal-api | `/bundle` (one audit row per call, `file_count` = files), `/files`, `/manifest` (no quota, no audit, no packs), `/reference` (1 file each), `/history` (dates before the published first year only), quotas, manifest cache until `state.json` `finished_at` changes | **As is** for one ticker. **With change** for the full market. | Per-ticker grants; the presign TTL defaults to 120 s | `apps/terminal-api/app/main.py` `bundle` (357), `grant` (308), `manifest` (298), `reference` (270); `quota.py` `check`; `bucket.py` `_fresh`, `manifest` |
| Publisher | Yearly files, price pack (all years), broker archive (all but the last 2 years), reference files | **With change** if a cross-sectional file is chosen | Price is published from the first stored year: 2018-01-02 (publisher.py:321-323, 471-479; `min(date)` = 2018-01-02 live) | `apps/terminal-publisher/publisher.py` `publish`, `publish_packs`, `publish_refs`, `window`, `resolve_price_first_year` |
| Terminal page data | Bundle → presigned downloads in a Web Worker; IndexedDB cache by sha256 (50 MB LRU); price rows; broker aggregation | **As is (pattern)** | `liveData` is shaped for the Terminal page | `terminal/src/data/live.ts` `bundle`, `liveData`; `worker.ts` `download`, `priceRows`, `brokerData`, `CACHE_LIMIT` |
| Terminal chart and panes | Chart, overlays, indicator panes | **With change** (bound to the Terminal's `Ctx` and DOM ids) | Library useful, not a drop-in widget | `terminal/src/app/chart.ts` `initChart`, `app/indicators.ts` `initIndicators`, `app/context.ts` |
| Backtest page preview stack | Browser: `/bundle` → `inflateVerified` → `priceSeries` → `Compute.conditionSeries` per card; candle chart with switch-on markers | **Closest reusable preview stack**; extract it | Already the "chart + markers from the shared core" pattern | `backtest/src/api/live.ts` `liveApi` (`bars`, `priceOf`, `flowOf`), `api/compute.ts` `Compute`, `api/cache.ts` `fileCache`, `src/signals.ts` `initPriceChart`, `refreshSignals` |
| Broker aggregation | Terminal Broker-activity aggregation | Not needed for screener v1 | | `terminal/src/data/brokerAgg.ts` |

---
## 2. Semantics the screener needs, and what exists

### 2.1 How to derive VALUE, STATE and EVENT without duplicating formulas

Proved on live data in `scripts/semantics.mts` → `semantics.txt`.

- **Evaluation bar `at`.** PROPOSED: the ticker's own last bar with a date on or before the evaluation date (IHSG's last bar). Flag tickers whose last bar is older.
  - FACT: 829 of 845 tickers have a bar on 2026-10-27, so 16 would be stale (query on `Price_Stock_Indonesia_IDX`).
  - The Backtest also uses each ticker's own bars, with no filling (CONTRACT §2).
- **VALUE.** `calc.out(BY_ID[id].key, resolveParams(BY_ID[id], params))[output][at]`; null means n/a.
  - Example (FACT, live): BBCA 2026-10-27 RSI14 = 28.9596.
- **STATE.** `conditionSeries(calc, cond, field, at)[at] === 1`.
  - Examples: "close above SMA200" = `{kind:'indicator', indicator:'I01', params:{length:200}, lhs:{type:'price'}, op:'gt', rhs:{type:'output', output:'sma'}}`.
  - Supertrend "in uptrend" = I09 `direction` gt value 0. `direction` is 1 or −1 (indicators.ts:329-343).
- **EVENT within N sessions.** Let s be the cross series (`crosses_above` / `crosses_below`). Find the largest j in [at−N+1, at] with s[j]=1. Then `event_date = dates[j]` and `sessions_ago = at − j`. Chart markers come from `switchOns`.
  - Example (FACT, live): BBCA "MACD crosses above signal" last on 2026-10-15, 8 sessions ago. PMUI Supertrend flipped up on 2026-07-31, 58 sessions ago (I09 `direction` crosses_above 0).
- **Match and near miss.**
  - `met` = conditions passed; `need = entryNeed(logic, at_least, count)` (conditions.ts:263). This equals the prototype's `needOf` (proto l.1176).
  - Near = `met === need − 1` (proto l.1179). The prototype has no numeric distance.
- **n/a.** A series with no value up to `at` (a new listing shorter than the length; a volume indicator on IHSG) raises `INDICATOR_OUTPUT_EMPTY`. Treat it as n/a and not passed, as the prototype does (`na:true`, proto l.1063). Use the `EXCLUDED_CODES` pattern (FACT, MDLA with 367 bars and PMUI with 314 bars handled).

### 2.2 Missing in the core

| Prototype construct | Core today | Gap |
|---|---|---|
| `between` (inclusive `v >= min && v <= max`, proto l.1064) | No operator (conditions.ts:25) | New operator; two strict conditions change the count under any/at_least and the boundary |
| "Line rising vs 5 sessions ago", "cum rising over 20", "histogram rising 3 sessions" | None | Compare a series with its own lagged value |
| Cum line above or crossing its EMA(20/255) (OBV, PVT, A/D, NVI, PVI) | None | Indicator of an indicator |
| VALUE as % distance of close from a line or the basis; % position inside a band | Only raw outputs; %B exists for Bollinger only (I28, a fraction, not %) | Derived transforms on top of `calc.out` (no new formula) |
| Fast MA vs slow MA with EMA type; death cross; close below prior N-day low | `macross` SMA only, golden/fast_above_slow; breakout up only | New price-action operators, or cross-instance comparison |
| Donchian "close above upper (prior session)" (lag 1, proto l.977) | I10 upper = MAX(H,n) **including** the current bar (indicators.ts:345-347), so `price gt upper` is never true | Map to `price_action breakout`, or add a lag |
| RS vs IHSG, RS-rank percentile across all listings (`cross:true`, proto l.827), 52-week high/low distance | `asOf` for alignment; I17 ROC for return | Cross-sectional ranks need the whole universe in one evaluation |
| Per-condition "within N" for events | One `window_bars` 1–20 for the whole entry | Screener evaluator (2.1) |
| Near-miss distance | — | Count-based in the prototype; a numeric distance would be new (VALUE − threshold) |

### 2.3 Warm-up: latest value on the last K bars vs the full history

Measured on 40 live tickers with registry defaults. The error is scaled by each output's median |value| over the last 250 bars (`warmup_table_scaled.txt`).

| Group (FACT, measured) | K=60 | K=120 | K=250 | K=500 | K=750 |
|---|---|---|---|---|---|
| Window-only indicators (SMA, WMA, HMA, Aroon, Donchian, Stochastic, W%R, ROC, MOM, CCI, CMO, UO, AO, BOP, BB, %B, BBW, StdDev, HV, ADR, VolSMA, RVOL, VROC, VWMA, VWAP Session, CMF, MFI, EOM, MarketFI) | ≤ 7e-11 | same | same | same | same |
| EMA20, Keltner, Supertrend line | 8e-4, 1.3e-3, 5.4e-2 | ~3e-6 | ~7e-12 | 0 | 0 |
| RSI14, ATR14, NATR | 1.1e-2, 2.1e-2 | 3e-4 | 2–3e-8 | ~5e-16 | 0 |
| MACD, PPO, PVO (12/26/9) | 0.16–0.69 | 3e-3–2.2e-2 | 1.4e-7–4.6e-6 | ≤ 4.5e-15 | 0 |
| ADX14, TSI, TRIX, Stoch RSI, KAMA | up to 0.53 | up to 4.8e-2 | ≤ 8.4e-6 | ≤ 1.2e-13 | 0 |
| PSAR (direction differs at K=60) | 2.0 (dir) | 2.1e-3 (sar) | 0 | 0 | 0 |
| KVO (signal null at K=60) | 6.6 | 0.57 | 1.7e-2 | 1.9e-6 | 1.0e-8 |
| **OBV, PVT, A/D, NVI, PVI (cumulative)** | 1.5–1,500 | 1.1–1,100 | 1.4–740 | 2.1–330 | 1.4–130 |

Long custom lengths (`warmup_long.txt`):

| Indicator | K=500 | K=1000 | K=1500 |
|---|---|---|---|
| EMA 200 | 1.6e-2 | 1.5e-4 | 1.7e-6 |
| MACD 50/200/50, signal | 0.17 | 2.2e-3 | 2.4e-5 |
| ATR 100 | 1.3e-2 | 1.5e-4 | 1.5e-6 |
| ADX 50 | 1.4e-3 | 6.5e-7 | — |

**Comparison with `verification/terminal_api/INDICATOR_ALIGNMENT.md` §2.**
- That table gives the bars from the series start until the difference drops under 0.1%, for BBCA and GOTO: EMA200 ≈ 310–430, MACD signal ≈ 150, ADX ≈ 100–120, RSI ≈ 60–95, ATR ≈ 50–80.
- My worst case over 40 tickers is consistent in order but has a longer tail: ADX14 at K=120 still 4.8%; EMA200 needs ≈ 750 bars for < 0.1%.
- Note: the doc's §3.5 ("the display bucket holds price from 2021") is outdated. The code publishes price from the first stored year (publisher.py:321-323; live `min(date)` = 2018-01-02), so the browser, the worker and Feature 04 start on the same bar.

**INFERENCE / PROPOSED.**
- A recent-window file (K ≈ 500) is exact to ≤ 2e-12 only for default parameters and non-cumulative indicators.
- Exactness with the Terminal chart and the Backtest for custom parameters (unbounded lengths) and for OBV, PVT, A/D, NVI and PVI requires the full published history.
- That history is cheap: about 16.5 MB gzip for the whole market. Evaluate on full history.

---
## 3. Data loading for a full-market screen

### 3.1 What one ticker costs today

| Path | Requests | Files and bytes (gzip) | Quota and audit |
|---|---|---|---|
| Price only, `/bundle {datasets:['price'], packs:true}` | 1 `/bundle` + 1 presigned GET | 1 price pack. Measured 30 tickers: 3.4–42 KB, IHSG 42 KB, BBCA 26 KB, about 12.4 B/row (`pack_size.txt`) | 1 audit row (`dataset='bundle'`, `file_count`), 1 file, 1 ticker (main.py:308-328, 375) |
| Price + events | 1 + 2 | + events file (only for tickers with events) | 1 row, `file_count` 2 |
| Price + broker (+ events) | 1 + 4–5 | Price pack + broker archive + 2 yearly broker files (+ events). The 12 largest stocks: 28.4 MB and 2,494,454 rows together (CONTRACT §3). BBRI archive 2.2 MB gzip / 14.5 MB inflated (worker README). | 1 row, `file_count` 4–5 |
| From the browser (Terminal or Backtest page) | Each goes through edge-bff | Same files | Plus 1 edge session DB lookup per call (main.py:245-249) |
| Worker job or preview | + 2 reference grants per call (CONTRACT §8) | Same files | `/manifest` (catalog, `FLOW_DATA_THROUGH`) has no quota and no audit row |

- FACT: `url_ttl_seconds` defaults to 120 (migration `20261025_100` l.79).
- FACT: the worker uses an answer only while `age + BACKTEST_HTTP_TIMEOUT_MS (60000) < 120 s`, otherwise it asks again (terminal.ts:460-462). Re-asks are skipped only when every file is cached (load.ts:146).

### 3.2 Every limit that blocks 800+ tickers

| Limit | Value | Where | Effect for 845 tickers |
|---|---|---|---|
| `MAX_PORTFOLIO_TICKERS` / `BACKTEST_MAX_PORTFOLIO_TICKERS` | 12, may only be lowered | engine.ts:151, config.ts:77, validate.ts:107-113, 206, 229 | `/v1/signals` and jobs refuse it: `INVALID_PORTFOLIO` |
| `MAX_POSITIONS` | 12 | engine.ts:150 | Backtest only |
| `BACKTEST_MAX_BROKER_ROWS` | 20,000,000 (dev, README) | load.ts `within` | A full-market flow load (46.2M rows in F05) is refused |
| `BACKTEST_MAX_DOWNLOAD_BYTES` | 1.5e9 (dev) | load.ts `within` | Price only (~16.5 MB) fits; with broker (≥ 300 MB) fits in bytes, but memory is the issue: the 12-stock worst case peaked at 1.31 GB (README) |
| `BACKTEST_TIMEOUT_SECONDS` | 900 | server.ts, backtest.py `ask` | — |
| `BACKTEST_MAX_CONDITIONS` | 32 enabled per list | validate.ts `withinConditions` | — |
| Preview concurrency | 1 preview at a time per worker (queue); 1 job (409 BUSY); 2 threads; 1 replica (RAILWAY_CHANGELOG 2026-10-27) | server.ts:106, 192-230 | Screens would serialise behind previews |
| edge-bff preview rule | 1 preview in flight per owner, latest wins (409 `PREVIEW_REPLACED`) | backtest.py:1002 | — |
| terminal-api default quotas | `files_per_hour` 60, `tickers_per_hour` 30, `tickers_per_day` 150, `megabytes_per_day` 300 | migration 20261025_100 l.79-84 | A full screen is impossible under the defaults |
| Gateway account override | 1,000,000,000 on all five quotas, **TEMPORARY** | DATABASE_CHANGELOG 2026-10-26 | Live value UNKNOWN: pgweb has no permission on schema `terminal` |
| Shared quota account | Worker `TERMINAL_PROXY_KEY` = `${{terminal-api.TERMINAL_PROXY_KEY}}` (RAILWAY_CHANGELOG ~4697) | | Worker and browser draw on one gateway account |
| Presign TTL vs worker margin | 120 s vs 60 s margin | | Usable window about 60 s, then a new grant |
| `access_log` growth | One audit row per `/bundle`; quota usage sums the subscriber's last day for every request (store.py `usage`; index `(subscriber_id, at DESC)`); kept 90 days | | INFERENCE: 845–1,690 rows per screen; the per-request quota query grows with daily volume |
| edge-bff POST body | 131,072 bytes | main.py:229 | 845 tickers ≈ 6 KB, fine |
| Browser IndexedDB cache | 50,000,000 B, shared by Terminal and Backtest | worker.ts:28, cache.ts:13 | All price packs (~16.5 MB) fit |
| Per-object bucket latency | ~0.8 s per object over HTTP/1.1 (ERRORS M240); 5 objects in 0.94–1.16 s with 6 connections | ERRORS_AND_SOLUTIONS EXEC-TERMINAL-SPEED | INFERENCE: browser cold load of 845 objects ≈ minutes |

### 3.3 Cache layers that exist (FACT)

- **Browser:** IndexedDB `terminal-files`, 50 MB LRU, keyed by sha256. Shared by the Terminal and the Backtest page.
- **Worker memory:** per thread, `BACKTEST_CACHE_BYTES` (1.5e9 in dev), LRU by sha256.
- **Worker disk:** `/tmp/backtest-cache`, 1 GiB, shared by all threads (`DiskCache`). Measured: a 12-stock preview downloaded 48 files (28.27 MB); the job after it read them from disk; 4.7 s vs 7.05–7.23 s cold.
- **terminal-api manifests:** in memory until `state.json` `finished_at` changes, checked every 60 s; at most 4,000 entries (bucket.py).
- **edge-bff catalog:** 60 s.
- **Per run:** `Calc` memo and engine `prepare()` context. **No cache of computed indicator values across requests.**

### 3.4 Options for loading the whole universe

| Option | Requests per screen | Bytes | Latency (sandbox numbers) | Changes needed | Notes |
|---|---|---|---|---|---|
| A. Worker-style per ticker (`loadMarket` with the cap lifted) | 845 `/bundle` (+ re-asks), 845 GETs cold | ~16.5 MB price | INFERENCE: tens of seconds cold. Warm disk: 845 `/bundle` + decode ~4.4 s + compute ~1 s. | New route or limit, new thread | 845–1,690 audit rows per screen; TTL churn; shares the worker the Backtest needs |
| B. Browser per ticker (Backtest page pattern) | 845 `/bundle` via edge-bff + 845 GETs | ~16.5 MB (fits IndexedDB) | INFERENCE: minutes cold (per-object latency), seconds warm | Page code only | 845 edge session lookups and quota transactions per screen; the user's device does the work |
| C. **Published cross-sectional file** (all tickers, full history; or recent K) | 1 grant + 1 GET | Full history ≈ 12–16.5 MB. K=260 ≈ 2.0 MB, K=400 ≈ 3.1 MB, K=520 ≈ 4.0 MB (measured, extrapolated from 30 tickers) | Decode ≈ 4–5 s Node, compute ~1 s per 5 conditions | Publisher writes the file at each publish; terminal-api serves it (new `REF_FILES` key or route); deploys | Full history keeps exact parity with Terminal and Backtest. Recent K breaks custom lengths and cumulative indicators (§2.3). Must be written before the manifest and state, as the publisher does now. |
| D. Long-lived in-memory cache in a service | 0 per screen; refresh on publish (manifests have no quota; no exact publish marker, load.ts:388-406) | ~100–200 MB RAM INFERENCE | ~1 s compute per screen | New service or thread | Pairs best with C (one file to refresh) |
| E. Read Postgres directly | 1 query | Full-price seq scan 2.0 s server-side (EXPLAIN ANALYZE: 1,330,722 rows, 49k buffers); recent window `date ≥ 2024-08-01` 2.1 s bitmap (429,832 rows) | + transfer | **Role or grant change** | `edge_bff_runtime`/`edge_bff_login` have **no SELECT** on Price, F04 or F05 (`has_table_privilege`, live). The worker has no DB credentials by design (terminal.ts:1-3). Only the terminal roles (`terminal_market_reader`) can read Price and F05. Not approved. |
| F. Daily precompute of all 53 indicators at defaults (latest value, state and event dates) | Once per publish | 53 × 845 ≈ 15 s CPU (measured 17.4 ms per ticker) | Instant reads | Output file or table (schema change if a table) | Custom parameters still need on-demand compute |

**PROPOSED.**
1. Use **C + D** for the full market: a publisher-written full-history price file, held in memory by a screen compute service running `core/screen.ts`.
2. Use the existing per-ticker `/bundle` path (B) for the one-ticker preview.
3. Do not put full-market screens on the backtest worker's preview or job threads.
4. Flow screening needs a precomputed per-ticker daily flow series. Feature_06 (2.3M rows) or a published flow file are candidates. Whether its foreign net equals `flow.ts` `fnet` is UNKNOWN (needs verification).
5. All of this needs the user's approval (publisher, terminal-api, deploy).

---
## 4. Chart preview

- **FACT: one ticker's chart data from the browser.** `POST /api/terminal/v1/bundle {ticker, datasets, packs:true}` through edge-bff (session + CSRF), then presigned GETs.
  - Price only: 1 file, ~20 KB.
  - IHSG for a "vs IHSG" line: 1 file, 42 KB.
  - Broker: archive + 2 yearly files.
  - Also `GET /api/terminal/v1/reference/{tickers|brokers|logos}` and `/logo/{ticker}`.
- **Stack to reuse.** The Backtest page already does exactly the preview path:
  - `liveApi().bars(ticker)` downloads, verifies and decodes; `Compute.conditionSeries(ticker, card)` gives the 0/1 series; `indicatorOutputs` gives the overlay lines (api/live.ts, api/compute.ts).
  - `signals.ts` `initPriceChart` / `refreshSignals` draw candles with switch-on arrows via lightweight-charts `createSeriesMarkers`.
  - FACT: the prototype's preview (proto l.1625-1631) is candles over 130 bars + overlay lines + `arrowUp` markers. The same idea.
- **Chart library.** Terminal and Backtest pin `lightweight-charts` 5.2.1 (package.json), the same version the prototype vendors (proto l.553).
- **Terminal chart code.** INFERENCE: reusable as a library, not as a component. `initChart(ctx)` and `initIndicators(ctx)` are bound to the Terminal's `Ctx` and DOM ids (app/context.ts).
- **Volume difference.** FACT: the Terminal maps a null volume to 0 (`live.ts:175` `value:r.v ?? 0`), while the core keeps null (`datafile.ts:159`). Volume indicators on an index differ between the two; for stocks the volume is normally present. Use the core path for the preview so values equal the screen and the Backtest.
- **Stock vs IHSG rebased** (proto `perfCard`): `datafile.ts` `asOf` or the Terminal's `alignTo` give the IHSG closes on the ticker's dates.

---
## 5. BFF conventions a screener API should follow (FACT)

- **Paths and auth.** Paths sit under `/api/v1/...`. Reads use the session cookie (`Depends(session)`, a DB lookup per request).
- **Writes.** POST needs `Origin == settings.origin` (else 403 `ORIGIN_REJECTED`), a CSRF header `x-csrf-token` (`Depends(write)`, else 403), and a body ≤ 131,072 bytes (else 413 `REQUEST_TOO_LARGE`) (main.py:221-254).
- **Error shape.** `{"error": {"code", "field?", "message?", "details?"}}` (CONTRACT §11; `main.py` `error()`; `backtest.py` `BacktestError`).
  - Pydantic validation is 422 `INVALID_INPUT`; an unexpected error is 503 `SERVICE_UNAVAILABLE` with no detail.
  - Data errors are 424 (`DATA_MISSING`, `DATA_INTEGRITY`, `DATA_UNAVAILABLE`). Limits are 422 `LIMIT_EXCEEDED` with `details{limit, allowed, needed}`. Timeouts are 504 `TIMEOUT`. A missing upstream is 503 `*_UNAVAILABLE` or `*_DISABLED`.
  - Exception: the terminal proxy passes terminal-api's own shape `{error: code, message}` through unchanged (main.py:383-386), which is inconsistent.
- **Relay pattern** (`backtest.py`):
  - Await on the event loop (not the thread pool).
  - Read timeout = upstream deadline + 30 s; connect timeout 30 s.
  - `unless_gone` cancels the upstream call when the browser leaves (answer 204).
  - "Latest wins" per owner with a page `client_order {page, seq}`.
  - `loads()` refuses NaN, Infinity, over-range numbers and lone surrogates before relaying.
  - Small catalog-like answers are cached 60 s.
- **Private service API.** Shared-secret header (`x-backtest-worker-key`, ≥ 32 characters); `/health` without the key; JSON logs with no secrets; redaction (`failure_of`, `public_data`).

---
## 6. Send to Backtest: lossless vs lossy

**The Backtest request** (CONTRACT §3, contract.ts):
- `entry {logic: all|any|at_least, at_least ≥ 1, window_bars 1–20, conditions[]}`.
- Conditions:
  - `indicator {indicator I01–I53, params (accepted keys only), lhs price|output, op gt|lt|crosses_above|crosses_below, rhs output|value}`.
  - `price_action` (dip, breakout, volspike, macross, macd).
  - `flow` (fnet gt|lt, broker gt, top5 gt; IDR).
- Ids `^[0-9a-z]{1,6}$`, unique; ≤ 32 enabled.
- `portfolio.tickers` 1–12 distinct stocks; `single.ticker` a stock.

The page keeps logic `'n'` for `at_least` and cards as `RegCard` or `LegacyCard` (state.ts:17-31, request.ts:21-23).

| Screener element | Mapping | Lossless? |
|---|---|---|
| 53-indicator VALUE gt/lt a number | `RegCard {ind, p, lhs:{t:'out',o}, op:'gt'\|'lt', rhs:{t:'val',v}}` | **Yes**: registry defaults equal the workbook (verified by lead); same `F` |
| VALUE crosses a level "within N" | op `ca`/`cb` + `window_bars = N` | Yes only if every event shares one N ≤ 20 and there are no STATE conditions (else lossy, below) |
| Close above/below a line (SMA, EMA, ..., VWAP basis), close vs band upper/lower | lhs price, rhs output | Yes (STATE). Donchian prior-session upper → `price_action breakout` (up only) |
| Pair cross / above (MACD, PPO, PVO, TSI, KVO, Stoch, Stoch RSI, Aroon; ADX +DI vs −DI) | lhs output a, rhs output b | Yes |
| Supertrend or PSAR up / flip | `direction` gt 0 / ca 0 / cb 0 | Yes |
| Volume above Vol SMA/EMA | lhs price (= volume for `price_input 'volume'`) | Yes |
| `between` | Two conditions gt and lt | **Lossy**: strict vs inclusive; counts twice under any/at_least |
| Rising vs N ago; cum vs its EMA; % distance or % band position values | — | **Lossy** (no operator) |
| MA cross with EMA type; death cross; breakdown below prior low; Ichimoku; squeeze; 52W distance; RS vs IHSG; RS rank | Only SMA golden / fast_above_slow and breakout up exist | **Lossy** |
| STATE + EVENT mixed with N > 1 | `window_bars` W applies to all: a state becomes "true on one of the last W bars" (conditions.ts:269-285) | **Lossy** unless W = 1 and every event's N = 1 |
| "Match today" | The Backtest trades switch-ons (false → true) of the combined state | INFERENCE: conceptually consistent, but a 10-day match is one entry |
| Flow: fnet, single broker net, top-N net | fnet / broker / top5 (top 5 fixed, IDR) | fnet and broker: yes (Rp B × 1e9). top-N with N ≠ 5: **lossy**. Bandar ratio, foreign % of value, streaks, frequency, bandar average price, silent accumulation: **lossy** |
| Fundamentals | No data in the DB (lead) | **Screen only** |
| Universe filters (index membership, board, cap, price, free float, notation) | Only ADV ↔ `portfolio.min_avg_value_20d_idr` (same SMA20(c×v) definition); applied per signal day, not at the evaluation date | **Lossy** |
| More than 12 matches | Must pick ≤ 12 (e.g. by sort key) | **Lossy**; plus the `SURVIVORSHIP` warning (engine.ts:536) |
| Period, exits, costs | Not in the screen | Defaults of the Backtest page (state.ts:34-43) |
| RVOL `include_current_bar` | `regToCondition` drops it only when it equals the workbook default `false` | **Mislabelled**, see §7 |

**PROPOSED.**
- The hand-off carries page-shaped cards: `RegCard` for the 53, `LegacyCard` for price_action and flow. It also carries `logic` ('n' for at_least), `atLeast`, `window`, `mode`, and `tickers` (≤ 12) or `ticker`.
- It lists the screener conditions that were dropped, with their reasons, as the prototype's dialog already shows ("Screen only").
- The Backtest page needs a new import step that validates through `toWire` / `regToCondition` and `portfolioTickers` before applying. Today it has none (FACT).

---
## 7. Other findings and risks

1. **FACT: the prototype's formulas differ from `F` in several places.** Examples:
   - RSI returns 100 when losses are 0 (`xRSI`, proto l.890); `F` gives 0 when gains and losses are both 0 (INDICATOR_SPEC I13).
   - TR on bar 0 is `h−l` (`xTR`), while `F`/TA-Lib skip it.
   - KVO is a simplified signed-volume EMA (proto l.957), not Klinger's trend/cm accumulation (INDICATOR_SPEC I52).
   - RVOL excludes the current bar by default (`base[i−1]`, proto l.948).
   - The screener must call `F`, never port `XI`.
2. **FACT: registry I37 `not_accepted` contradicts the calculation module.**
   - `backtest-registry.json` I37 has `not_accepted` `include_current_bar: False`, built from the workbook default (`build-registry.mjs:37`).
   - `regToCondition` drops such a parameter when it equals that value, on the assumption that it is "the value the module implements" (catalog.ts:128-139).
   - But `F.rvol` divides by `sma(V,n)[i]`, which includes the current bar (indicators.ts:484; INDICATOR_SPEC I37 "includes the current bar").
   - So a card showing `include_current_bar=false` is computed with the current bar included.
   - The prototype sends the string `'false'` (XPARAM), which `regToCondition` refuses (`PARAM_NOT_ACCEPTED`).
   - INFERENCE: label and calculation disagree. Settle with the user before exposing the parameter.
3. **FACT: one indicator instance per condition** (conditions.ts:92-96). Cross-indicator comparisons need a new condition kind.
4. **FACT: Donchian `close > upper` can never be true** with `F` (upper includes the current high).
5. **INFERENCE: running screens on the backtest worker risks the Backtest.** It is 1 replica with one preview thread and one job thread, and its memory budget was sized for 12 stocks (1.31 GB peak). A separate thread or service and separate limits keep "the existing Backtest worker must not break".
6. **FACT: test suites that must stay green if core modules change.**
   - `apps/backtest-worker/tests/*.test.ts` (conditions, datafile, engine, flow, load, registry, run, server, terminal, validate, …).
   - `apps/edge-bff/backtest/tests` (live, page, preview, cache, …).
   - `apps/edge-bff/terminal/tests/calc` (parity).
   - The worker re-checks the registry hash at start (server.ts:342-343, version.ts): any change to `indicators.ts` changes `registry_version` and needs the registry regenerated.
