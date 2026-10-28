# EDGE Screener audit: flow and bandarmology data (read-only)

Audit time: 2026-10-27, 19:33 to 19:50 UTC. Repo `/home/user/saniti` at `3db84ae`; no file in the repo was changed. Database reads went through pgweb (role `pgweb`, read-only, statement_timeout 30 s, PostgreSQL 18.6). Raw outputs are in `/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/audit/flow/`.

Labels: **FACT** (seen now in code, data or a recorded measurement), **INFERENCE**, **PROPOSED**, **UNKNOWN**.

---

## 0. Summary for the approval gate

1. **FACT:** All flow tables are current. `IDX_Broker_Summary`, F02, F03, F05 and F06 all end on 2026-10-27, the same day as the latest final Daily price. The M243 lag is 0 sessions right now.
   **FACT:** The lag comes back whenever no new Stockbit token is supplied. A round runs only when the token is replaced (UPDATE_TABLE.md part 0, K2 A). The current token expires 2026-10-28 10:53 UTC (`Monitoring_Stockbit_Update`, row `51a399f1`).
2. **FACT:** No flow table stores the prototype's **broker-ranking metrics**: Bandar status / top-N broker net over D sessions, price vs bandar average, D-session broker breadth. F03 ranks brokers on **one day** only. F02 has D-session sums per (broker × investor type × board), but only on the dates that broker traded. A cross-section of F02 on the latest date therefore leaves out the brokers that did not trade that day.
   **FACT, ANTM:** the F02 foreign 20-day net summed over latest-date rows is −408.06 B, against a true −477.11 B. **DMAS:** 39.09 B against 82.41 B.
3. **FACT:** F06 stores foreign net (1/5/10/20/40/60 sessions), foreign net as % of traded value (1/5/20), buy and sell days, z-scores and percentiles, strength and frequency. These are stored per board, on the ticker's own sessions. Reading the latest cross-section takes 23 ms cold (865 rows).
4. **FACT, benchmarks for the whole universe at 2026-10-27:**

   | Query | Cold | Warm | Rows read / buffers |
   |---|---|---|---|
   | F06 latest cross-section | 23 ms | — | — |
   | F06 61-session window (streak, all-board 20D, freq spike) | 1.5 s | 0.58 s | 22k buffers |
   | F05 top-3 accumulation + VWAP, 10 sessions | 4.3 s | 0.55 s | 243k rows |
   | F05 top-3 accumulation + VWAP, 20 sessions | 0.85 s | 0.55 s | 483k rows |
   | F05 top-3 accumulation + VWAP, 60 sessions | 12.3 s | 1.9 s | 1.5M rows; 89k buffers; 30 MB temp spill per worker |
   | Full broker grid for one date (D 5/10/20 × top 3/5 + VWAP + breadth + top buyer/seller) | 4.7 s | 1.47 s | result 890 rows, 137 KB |
   | F03 20-session sums | 0.35 s | 14 ms | — |

   **FACT:** `shared_buffers` is 128 MB on a 42 GB database.
5. **INFERENCE (recommendation):**
   - **Fixed-window F06 metrics:** no snapshot is needed; read F06 directly.
   - **Broker-ranking, streak and frequency-spike metrics:** a **daily flow snapshot** is recommended, grain (as_of_date, ticker), Regular board, fixed parameter grid.
   - Why: the dynamic version is acceptable warm, 4 to 12 s cold, and it multiplies with "within N days" operators and with every parameter edit, on a cache-starved database shared with the AI.
   - A snapshot needs a schema change (not approved), or a publisher-written file (no schema change). Both need the user's "go".
6. **PROPOSED decisions for the user:**
   - (a) Board: Regular by default. 168 of 844 stocks differ between Regular and all boards on the 20-day foreign net; 20 change sign (CARE: −1.5 B Regular vs +376.2 B all boards).
   - (b) The Bandar formula and thresholds. The Terminal's Bandar detector is still hidden because no definition has been approved (`verification/terminal_api/DESIGN.md:40,147`).
   - (c) Fixed parameter grid, or custom D.
   - (d) The as-of date shown when broker data lags price.

---

## 1. Live state of the flow tables (FACT, pgweb 2026-10-27 19:33 UTC)

| Table | reltuples | Total size | Grain (PK) | Latest date | Earliest | Useful indexes | Heap correlation |
|---|---|---|---|---|---|---|---|
| `IDX_Broker_Summary` | 45.07 M | 10 GB | ("Date","Symbol","Broker","Investor Type","Market Board") | 2026-10-27 | 2016-01-04 | pkey only (date-leading) | — |
| `Feature_05_Foreign_Domestic_Broker_Detail` | 46.24 M | 9.8 GB | (ticker, trade_date, broker, investor_type, market_board) | 2026-10-27 | 2016-01-04 | pkey; `trade_date_idx` | trade_date 0.99 |
| `Feature_02_Broker_Rolling` | 46.29 M | 15 GB | (ticker, market_board, broker, investor_type, date) | 2026-10-27 | 2016-01-04 | pkey; `(date, market_board, ticker)` | — |
| `Feature_03_Stock_Broker_Daily` | 2.32 M | 1.09 GB | (ticker, market_board, date) | 2026-10-27 | 2016-01-04 | pkey; `(date, market_board, ticker)` | date 0.90 |
| `Feature_06_Foreign_Domestic` | 2.31 M | 1.37 GB | (ticker, market_board, trade_date) | 2026-10-27 | 2016-01-04 | pkey; `(trade_date, market_board)` | ticker 0.97, date 0.05 |
| `IDX_Broker_Profile` | 112 | 80 kB | broker_code | — | — | pkey | — |
| `_INDEX` tables (IHSG) | F02/F05 585k, F03/F06 7.3k | small | as their parents | 2026-10-27 (Monitoring row 38cdc7dc "newest") | — | — | — |
| `Feature_05/06_*_Stock` | views | — | parent filtered to `IDX_Stock_Universe` "Security Type" = 'stock' (DATABASE_SCHEMA.md 4264-4340) | — | — | — | — |

Further facts, from queries saved in the scratch directory:

- **Rows on the latest date (2026-10-27):**
  - F05: 24,860 rows (Regular 24,503); recent dates hold 23.3k to 26.7k rows each (`f05_rows_per_date.txt`).
  - F06 and F03: Regular 865, Nego 130, Tunai 9.
  - Price (Daily, final): 829 tickers = 828 universe stocks + IHSG.
  - Universe: 844 stocks. 828 have both price and an F06 Regular row today; 16 did not trade.
  - The 37 F06 Regular tickers outside the universe are ETFs and similar (X*), plus AKKU, CRAB, GTBO, TRUE and UNSP.
- **History depth**, F06 Regular, universe stocks: all 844 have at least 60 sessions; 833 have at least 252; 830 have at least 312. Median 1,930 sessions, p10 715.
- **Frequency:**
  - Universe stocks: frequency is non-null on every 2026 Regular row. The nulls are warrants and rights only (long symbols, January–August 2026).
  - Total buy frequency equals total sell frequency on 865 of 865 latest Regular rows. So `foreign_buy_freq_1d + domestic_buy_freq_1d` is the **number of trades** (BBCA 81,369; BBRI 60,879).
- **Volume:** price volume equals the Regular-board share volume from F05 exactly, on 5 of 5 samples (ANTM, BBCA, BBRI, DMAS, GOTO, 2026-10-27). BBCA all boards: 457.2 M shares against price volume 366.8 M.
  - **INFERENCE:** price-based technical metrics (volume spike, OBV, MFI, CMF) are Regular-board metrics.
- **Average price:** `IDX_Broker_Summary."Avg Buy"` = Buy Value / (Buy Lots × 100) on 387 of 387 sample rows (max difference 8e-13). F05 does not carry Avg Buy, but value / lots reproduces it exactly.
- **Source gaps (M157):** `source_balance_gap` rows since 2025 are 4, all structured warrants. M157 does not matter for current stock screens.
- **Broker profile:** 112 brokers, classified Institutional-heavy (25), Mixed (23), Niche (45) and Retail-heavy (19).
  - The classification is current-state, not point-in-time (Feature_Catalog misuse warning for F02 `broker_classification`).
  - Some foreign brokers are Retail-heavy (YP, ZP, YU, DR, KK ...).
  - No broker in F05 since 2026-10-01 is missing from the profile.
- **Feature_Catalog:** active rows are F02 v2 (38), F03 v2 (24), F05 v1 (15) and F06 v1 (87), all `CALCULATION_VERIFIED`. Full dump: `feature_catalog_flow.txt`.
  - F06 misuse warning: "Do not compare across boards or sum across boards."
  - F03: "Do not combine Regular, Nego and Tunai implicitly."

### 1.1 ERRORS M243: broker lag measured now

- **FACT:** latest final Daily price is 2026-10-27; latest `IDX_Broker_Summary` / F05 / F02 / F03 / F06 is 2026-10-27, so the **lag is 0 sessions**.
  - The lag was closed by `stockbit-updater` round `38cdc7dc` (APPLY, 2026-10-27 11:08 to 12:58 UTC): 48,661 broker rows for 2026-10-26 and 2026-10-27; feature refresh 2,214 s; INDEX 2,077 s.
- **FACT:** earlier the same day (M243, 08:19 UTC) broker data ended 2026-10-23 while price was 2026-10-26, a 1-session lag.
- **FACT:** the round runs only when `STOCKBIT_TOKEN` is replaced (UPDATE_TABLE.md part 0, "Putaran berjalan saat token diganti, bukan terjadwal (K2 A)").
- **INFERENCE:** each new session's broker data needs a new token before the screener's flow metrics move. The lag recurs by design, so the screener needs a separate broker as-of date.
- **FACT, partial state during a refresh:** `apps/stockbit-updater/refresh.py:68-75,117-140` commits F02 and F06 **per ticker** (`run_in` opens one connection and commits per call). While a refresh runs (about 37 min of features on 2026-10-27), the latest date exists for some tickers and not others.
  - **INFERENCE:** a screener must not read the cross-section while a round is RUNNING. Use `Monitoring_Stockbit_Update` status / finished_at, or the publisher's `state.json` `broker_through`.

---

## 2. Definitions that decide formula equivalence (FACT from code)

- **F05** (`database/migrations/20261022_002…:63-95`, renamed and identical in `20261022_005`): one row per `IDX_Broker_Summary` row. No window. Net = buy − sell. Carries buy_freq and sell_freq. `source_balance_gap` is sum(buy) ≠ sum(sell) per (date, ticker, board).
- **F06** (`20261022_003…:145-382`; the `20261022_005` copy is identical after renames, diff of 233 lines = 0):
  - Grain (ticker, board, date). A row exists only where the board traded that day (`WHERE x.active`).
  - Windows count **ticker sessions**: the dates the ticker has any F05 row on any board. Every board is zero-filled inside the window.
  - `foreign_net_turnover_ratio_Nd = 100·ΣF/Σ(fb+db)` (buy-side traded value of that board).
  - z-score and percentile use the previous 252 or 60 values, today excluded.
  - `foreign_strength = 100·ΣR/Σ|R|` with R = F/T.
  - Frequency imbalance and ticket sizes come from buy_freq and sell_freq.
  - **Consequence:** an all-board N-day value cannot be read by summing the latest-date rows of F06. A board that did not trade today has no row, even if it had flow inside the window. All-board values must be summed from `foreign_net_1d`.
- **F02** (`20261025_008…:52-193`):
  - Grain (ticker, board, broker, investor_type, date). Rows are written only where that combination traded that day (`FROM history JOIN daily`).
  - The 5/20/60-day sums are on the ticker-session calendar, zero-filled.
  - **Consequence:** F02 on the latest date is **sparse**. Measured 2026-10-09 to 10-27 window (20 sessions from 2026-09-30):
    - ANTM: 79 of 143 broker combinations have a latest-date row; |net20| of the missing ones is 88.6 B.
    - BBCA: 112 of 169 (658.7 B missing).
    - DMAS: 52 of 94 (61.5 B missing).
- **F03** (`20260914_047…:30-129`):
  - Daily only, per (ticker, board). Brokers are first summed over both investor types.
  - Stored daily: top buyer and seller, top-3 buyer net and share, HHI, net-buy and net-sell broker counts and ratio, foreign and domestic net (investor type), and institutional / retail / mixed / niche net (current `broker_classification`). The four classes sum to the total net: ANTM 2026-10-26 −76.54 + 40.34 + 32.72 + 3.48 = 0.
- **"Foreign":** everywhere it means **investor type** (source investor identity), not broker domicile (publisher `broker_doc`, `apps/terminal-publisher/publisher.py:165-172`; F06 column definitions).
  - The prototype's `BROKERS` list carries a domicile flag (HTML 572ff `['AK','UBS Sekuritas',1]`), but its foreign series is generated separately (HTML 700), so there is nothing to match.
- **Backtest and Terminal flow** (`apps/edge-bff/backtest/src/core/flow.ts:1-121`):
  - Calendar: the ticker's price bars.
  - `fnet`: foreign investor-type net over **all boards**.
  - `broker X`: both investor types, all boards.
  - `top5Accumulation`: on each bar, sort the n-bar net of every broker; take the positives among the first 5 plus the negatives among the last 5. The series starts at bar `from + n` (`flow.ts:108-119`).
  - The same ranking rule as the prototype's `bandarRatio` (HTML 782-783: `x.slice(0, top).filter(v>0)` + `x.slice(-top).filter(v<0)`), with top = 5 and no denominator.
- **Terminal broker summary:** `avgPrice = value / (lots × 100)` (`apps/edge-bff/terminal/src/data/brokerAgg.ts:25`). This is the gross VWAP and equals Stockbit "Avg Buy".

---

## 3. Mapping of the prototype's Flow & bandarmology metrics (HTML 778-787, 829-847)

Prototype shape: one ticker series, N = 400 sessions, no board or investor dimension. Evaluation (HTML 1052-1067):

- **States** read only the last bar.
- **Value tests** (gt / lt / between) read the last bar.
- **Crossing tests** (`xa` / `xb`) test `s[i-1] <= a && s[i] > a` within the last n sessions.
- **Event markers** for the preview chart are collected over the last 130 sessions, for the selected ticker only (HTML 1602, 1614).

Dead code (FACT): `topBrokers` (785) and `bandarStatus` (784) are defined but never called.

Bandar thresholds: `BANDAR = {acc:4, big:10}` (781), reset to acc 6 / big 10 (1082). The user can edit them (1621, 1628), and they are saved with a screen (1643).

| # | Prototype metric (line) | Prototype formula (from code) | Real source | Status | Formula / grain match |
|---|---|---|---|---|---|
| 1 | `bandar` Bandar status (830-832), params days 10, top 3; ops acc, bigacc, dist, bigdist, gt, lt | 100·(Σ positive of top-N D-day broker nets + Σ negative of bottom-N) / D-day traded value | F05 net_value and buy_value, summed per (ticker, broker) over D sessions | **Not stored; dynamic or snapshot.** F03 `top3_buyer_*` is one day, buyers only, denominator = positive net, so it is **not equivalent** | Equivalent if computed from F05 per broker (investor types summed) with denominator Σbuy_value on the same board. Board: decision (Regular proposed). Measured in Q3. Thresholds and formula need user approval (DESIGN.md:40) |
| 2 | `topacc` Top-N broker net (833), top 5, days 10, Rp B | (b+s)/1e9 of the same ranking | F05 | Not stored; dynamic or snapshot | With top = 5 it is the Backtest `top5` formula (flow.ts:108-119). Differences: Backtest uses all boards, price-bar calendar, and starts at from+n |
| 3 | `broker` Broker net buy (834), code (YP), days 5; ops gt, lt, between, xa | RSUM(net[broker], D)/1e9 | F05 filtered on broker, summed over D sessions (both investor types) | Not usable from F02 at the latest date (sparse). **Dynamic is cheap:** 30 ms warm for one broker × all tickers × 5 sessions (Q5) | Equivalent to Backtest `broker` (all boards). Broker list: 112 codes from `IDX_Broker_Profile` (publisher `ref/brokers.json.gz`) instead of the 14 sample brokers. `xa` needs D+n sessions of daily nets |
| 4 | `bavg` Price vs bandar average (835), days 10 | top-3 D-day net buyers; avg = Σ positive daily net / Σ(positive daily net / typical price); (close/avg − 1)·100 | F05 buy_value and buy_lots of the top-3 D-day net buyers; close from price | Not stored; dynamic or snapshot | **Not equivalent by formula.** The prototype approximates with typical price because its sample has no broker prices. Real data has the gross VWAP Σbuy_value/(Σbuy_lots·100), equal to Stockbit Avg Buy (FACT). PROPOSED: use the gross VWAP. Decision: gross VWAP vs net-buy days only |
| 5 | `fnet` Foreign net flow (836), days 5; ops gt, lt, between, xa, xb | RSUM(foreign, D)/1e9 | F06 `foreign_net_{1,5,10,20,40,60}d` | **Stored** for D ∈ {1,5,10,20,40,60}, per board | Equivalent per board on ticker sessions. Other D: Σ `foreign_net_1d`, or the difference of `foreign_cumulative_net`. All boards: Σ `foreign_net_1d` over boards (not the latest-date rows) |
| 6 | `fstreak` Foreign net-buy streak (837) | consecutive sessions with foreign > 0, ending today | F06 `foreign_net_1d` | **Not stored** (only `foreign_buy_days_Nd` counts); dynamic (Q2b) or snapshot | Exact once the calendar is fixed. Q2b uses market sessions, so a missed session breaks the streak. Max streak on 2026-10-27: 21; 27 tickers have ≥ 5 |
| 7 | `fpct` Foreign net % of value (838), days 20 | 100·RSUM(foreign, D)/RSUM(val, D) | F06 `foreign_net_turnover_ratio_{1,5,20}d` | **Stored** for D ∈ {1,5,20} | Equivalent by code (100·ΣF/Σ(fb+db)). Recomputed value = stored on 833 of 865 rows; the 32 differences all have fewer than 20 market sessions |
| 8 | `freq` Frequency spike (839), len 20; ops gt, lt, xa | freq[i] / SMA(freq, len)[i−1] | F06 `foreign_buy_freq_1d + domestic_buy_freq_1d` (trade count, FACT) | Not stored; dynamic (Q2b) or snapshot | Equivalent once trade count = buy-side frequency. The price table has no frequency. Null for warrants |
| 9 | `silent` Silent accumulation (840) | SMA(v,5)/SMA(v,len)[i−days] ≥ volx and \|price move\| ≤ move | Price close and volume (Regular board) | Price-based, not broker data | Technical area. The preset combines it with `bandar` > 0 |
| 10 | `mfi`, `cmf`, `obv` (841-843) | prototype MFI, CMF and OBV | 53-indicator registry keys `mfi`, `cmf`, `obv` exist in `backtest-registry.json` | Technical area | Equivalence to the registry formulas belongs to the technical audit, not checked here |
| 11 | `adv` Average daily value (844), len 20 | SMA(val, N)/1e9, val = close × volume | Exact Regular traded value: F06 fb+db or F03 `total_buy_value`. Approximation: close × volume | Dynamic (F03 20D sum: 14 ms warm) or snapshot | The universe filter `advMin` (default 1 B, HTML 1141, 1170) evaluates it **for every ticker on every screen**. close × volume differs from the exact value by about 1-2% (ANTM 375.0 vs 370.2 B) and does not depend on the broker lag |

### 3.1 Bandarmology presets (HTML 1084-1090) and combined flow presets

| Preset | Conditions | Data needed |
|---|---|---|
| Big Accumulation | bandar(10,3) ≥ 10 + close > MA20 | broker ranking (snapshot or F05) + price |
| Foreign Accumulation Streak | fstreak > 4 + fnet(20) > 0 | F06 (streak dynamic or snapshot; fnet20 stored) |
| Silent Accumulation | silent(5, 20, 1.3, 4) + bandar(10,3) > 0 | price + broker ranking |
| Frequency Spike | freq(20) crosses above 2.5 within 3 + ret(1) > 0 | F06 frequency for the last 24 sessions + price |
| Near Bandar Average | bavg(10) between −3 and 3 + bandar acc(10,3) | broker ranking + VWAP + close |
| Broker Follow | broker(YP, 5) > 1 B + close > MA50 | F05 one-broker query + price |
| Quality + Foreign Inflow (combined) | fnet(20) > 0 + fundamentals | F06 stored. Fundamentals **unavailable** (no fundamental tables, lead's FACT) |
| Value + Accumulation (combined) | bandar acc(10,3) + fundamentals | broker ranking. Fundamentals **unavailable** |

---

## 4. PROPOSED flow screener metric set

Built on the daily feature tables, so no request recomputes large broker aggregates. Defaults:

- Regular board, with an all-board toggle where noted.
- Investor type = source investor identity.
- Broker net = both investor types summed.
- Window = sessions. The proposed default is market sessions for dynamic and snapshot metrics; F06 stored windows are ticker sessions.

Cost codes:

| Code | Meaning | Measured cost |
|---|---|---|
| **S** | read stored F06 or F03 latest cross-section | 23 ms cold |
| **W** | short window over F06 or F03 | 14 ms – 1.5 s |
| **B** | F05 broker-ranking aggregate | 0.5 – 12 s |
| **Snap** | one row per (date, ticker) from the proposed snapshot | INFERENCE: ms |

| ID | Metric | Formula | Source table.columns | Grain | Unit | Lookback / params | Cost now → with snapshot |
|---|---|---|---|---|---|---|---|
| F1 | Foreign net N | Σ_N F | F06.foreign_net_{1,5,10,20,40,60}d; all boards: Σ F06.foreign_net_1d | ticker × board × date | IDR (shown Rp B) | N ∈ {1,5,10,20,40,60} | S (Regular) / W (all boards) |
| F2 | Foreign net % of traded value N | 100·Σ_N F / Σ_N(fb+db) | F06.foreign_net_turnover_ratio_{1,5,20}d; 10 and 60 from F06 1d columns | same | % | N ∈ {1,5,10,20,60} | S / W |
| F3 | Foreign net-buy day ratio N | foreign_buy_days_Nd / N | F06.foreign_buy_days_{5,10,20,40}d | same | 0-1 | N ∈ {5,10,20,40} | S |
| F4 | Foreign streak (signed) | +k consecutive F > 0 sessions, −k consecutive F < 0, ending as-of | F06.foreign_net_1d | ticker × date | sessions | capped at 60 | W (Q2b 0.58 s warm) → Snap; incremental from yesterday's value |
| F5 | Unusual foreign flow | z-score and own-history percentile of the N-day net | F06.foreign_net_zscore_{5,10,20,40,60}d_base252d, _percentile_* (and base60d) | ticker × board × date | σ / percentile | N + 252 history | S |
| F6 | Foreign flow acceleration | F_20 − F_prev20 | F06.foreign_flow_vs_prev_20d / _40d | same | IDR | 40 / 80 sessions | S |
| F7 | Foreign strength | 100·ΣR/Σ\|R\| | F06.foreign_strength_20d / _50d, _momentum_5d | same | −100..100 | 20 / 50 | S (EDGE formula, no thresholds defined) |
| F8 | Cross-sectional foreign rank | percentile of F2 across the screened universe | computed at query time from F2 | universe × date | 0-100 | — | trivial (about 850 values) |
| B1 | Top-N broker net D | Σ positive of top-N D-day broker nets + Σ negative of bottom-N | F05.net_value per (ticker, broker) over D | ticker × date | IDR | N ∈ {3,5}, D ∈ {5,10,20} | B (one date, whole grid: 1.47 s warm / 4.7 s cold) → Snap |
| B2 | Bandar ratio D (status Acc / Big Acc / Dist / Big Dist) | 100·B1 / Σ_D buy_value | F05 + F06 (fb+db) | ticker × date | % | thresholds editable (prototype 6 / 10) | B → Snap; **formula approval needed** |
| B3 | Close vs top-3 buyer VWAP D | 100·(close / VWAP − 1), VWAP = Σbuy_value/(Σbuy_lots·100) of the top-3 D-day net buyers | F05 buy_value, buy_lots; Price close | ticker × date | % | D ∈ {10,20} | B → Snap |
| B4 | Broker net D (chosen broker) | Σ_D net of broker X (both investor types) | F05 filtered on broker | ticker × date | IDR | any broker, D ≤ 20 | dynamic, 30 ms warm (Q5); no snapshot needed |
| B5 | D-day broker breadth | net buyers / (net buyers + net sellers) on D-day broker nets | F05 | ticker × date | 0-1 | D ∈ {5,20} | B → Snap (1-day version stored: F03.net_buy_broker_ratio) |
| B6 | Buying concentration D | top-3 D-day buyers' net / Σ positive D-day net | F05 (1 day: F03.top3_buyer_share) | ticker × date | 0-1 | D ∈ {1,20} | S (1 day) / B → Snap |
| B7 | Net-flow HHI (1 day) | Σ(\|net\|/Σ\|net\|)² | F03.broker_concentration_hhi | ticker × board × date | 0-1 | 1 | S |
| B8 | Top buyer / top seller D (display) | argmax / argmin of D-day net | F05; 1 day: F03.top_buyer / top_seller | ticker × date | code | D ∈ {1,20} | S / Snap |
| C1 | Institutional vs retail net D | Σ_D institutional_net_value, Σ_D retail_net_value, and each as % of Σ_D total_buy_value; divergence = inst% − retail% | F03 | ticker × board × date | IDR, % | D ∈ {5,20} | W (14 ms warm / 0.35 s cold). Caveat: current broker classification, not point-in-time |
| D1 | Trades and frequency spike | trades = fbf + dbf; spike = trades_t / mean(prior 20) | F06 frequency columns | ticker × date | count, × | 20 | W → Snap |
| D2 | Ticket-size change | (value/trades)_5 vs prior 20 | F06.*_value_per_freq_change_5d_vs_prev20d (by investor type), or derived | ticker × board × date | % | 25 | S / W |
| D3 | ADV N (exact) | mean_N(fb+db) | F06 or F03.total_buy_value | ticker × date | IDR | N ∈ {5,20,60} | W → Snap |
| D4 | Foreign participation | (foreign_buy_share + foreign_sell_share)/2 | F06.foreign_buy_share_1d, foreign_sell_share_1d | same | % | 1 (snapshot 20) | S |

PROPOSED new Bandarmology presets, built on these metrics:

- "Foreign accumulation, unusual": F2(20) > 3 % and F5 z20 ≥ 2.
- "Quiet bandar": B2(10) ≥ 6 and B6(20) ≥ 0.6 and \|ret 10\| ≤ 4 %.
- "Retail out, institutions in": C1 inst% > 0 > retail% over 20 sessions.
- "Accumulation near cost": B3(10) within ±3 % and B2(10) ≥ 6.
- "Breadth turn": B5(5) − B5(20) ≥ 0.15.

These are PROPOSED; thresholds are not validated.

---

## 5. Benchmarks (FACT, EXPLAIN ANALYZE BUFFERS, as-of 2026-10-27)

Session calendar used: d5 = 2026-10-21, d10 = 2026-10-14, d20 = 2026-09-30, d61 = 2026-07-31 (from the F03 date index, 61 rows, warm 42 ms).

| ID | Query | Plan | Cold | Warm | Buffers (read from disk) | Result | File |
|---|---|---|---|---|---|---|---|
| Q1 | F06 latest cross-section, Regular, 16 columns | Bitmap on `date_board_idx`, 176 heap blocks | 22.6 ms | — | 179 (179) | 865 rows; row 304 B | `bench_q1_f06_xsection.txt` |
| Q2 | F06 61 sessions: 20D all-board and Regular net, % value, streak, freq spike; calendar via CTE join | **Seq Scan of F06** (planner misestimate) | 18.6 s | — | 201k (161k) | — | `bench_q2_f06_window_run1.txt` |
| Q2b | Same, with a literal date range | skip-scan on F06 pkey (1,717 index searches) | 1.52 s | 0.58 s | 22.1k (10.1k) | 1,525 tickers incl. warrants and ETFs (844 universe), 124 KB | `bench_q2b_*` |
| Q3-10 | F05 top-3 net / bandar ratio / top-3 VWAP vs close, 10 sessions | Index Scan `trade_date_idx`, 243k rows | 4.27 s | 0.55 s | 14.4k (4.9k) | 886 tickers | `bench_q3_f05_10d_*` |
| Q3-20 | Same, 20 sessions | 483k rows; HashAgg spills 30 MB | 0.85 s | 0.55 s | 27k | 890 tickers, 106 KB | `bench_q3_f05_20d_*` |
| Q3-60 | Same, 60 sessions | parallel (3 workers), 1.50 M rows, 3 × 30 MB spill | 12.3 s | 1.92 s | 89k (28k, then 27k again) | — | `bench_q3_f05_60d_*` |
| Q4 | F03 20-session inst/retail/foreign net, value, breadth avg, latest top-3 share and HHI | Index Scan `date_board_ticker_idx`, 17k rows | 0.35 s | 14 ms | 589 (561) | 890 rows, 110 KB | `bench_q4_*` |
| Q5 | F05 one broker (YP) × all tickers × 5 sessions | `trade_date_idx`, 117k rows filtered away | — | 31 ms | 4.6k (hit) | — | `bench_q5_*` |
| Q6 | F02 latest date, Regular, per (ticker, broker) | Bitmap `date_board_ticker_idx`, 24.5k rows | 215 ms | 55 ms | 1.6k | **semantically incomplete (sparse)** | `bench_q6_*` |
| Q7 | Snapshot grid for one date from F05 (D 5/10/20 × top 3/5, VWAP 10, breadth, top-3 share 20, top buyer/seller 20) | `trade_date_idx`, about 483k rows | 4.73 s | 1.47 s | 23.5k (9k) | 890 rows, 137 KB | `bench_q7_*` |

Q2 and Q2b check the dynamic results against stored F06 (FACT):

- Recomputed 20D Regular net = stored `foreign_net_20d` on 847 of 865 rows; recomputed % value = stored on 833 of 865. Every difference is a ticker with fewer than 20 market sessions, because stored windows use ticker sessions.
- All-board ≠ Regular 20D for 168 universe stocks; > 10 % different for 59; sign flips for 20.

Environment (FACT, `pg_settings`): `shared_buffers` 128 MB, `work_mem` 4 MB, `effective_cache_size` 4 GB, `max_parallel_workers_per_gather` 2, database 42 GB.

**Is a daily screener flow snapshot needed? INFERENCE: yes, for the broker-ranking group only.**

- **Without it,** every screen that uses B1/B2/B3/B5/B6, F4 or D1 needs a 0.5 to 2 s warm aggregate (4 to 12 s cold) on the shared database.
  - It repeats on every parameter edit and multiplies by n for "crosses within n days". A cross-section ranking has to be recomputed for each of the n prior as-of dates.
  - Each run spills to disk at `work_mem` 4 MB and evicts the 128 MB buffer cache that the AI workload also uses.
- **With it,** the screen reads (W+1) × about 870 rows. Refresh cost per new date is about 1.5 to 5 s for the F05 grid plus about 1 s for the F06 part, about 0.3 % of the 2,214 s feature refresh of round 38cdc7dc. Size is about 140-400 KB per date, about 35-100 MB a year. A 252-day backfill is about 6 to 20 min one-off (INFERENCE from the per-date timings).
- **Fixed-window F06 metrics** (F1-3, F5-7, D4) need no snapshot.

Snapshot options (PROPOSED; all need the user's "go"):

- **(a) A new governed table**, e.g. `Feature_07_Flow_Screener`, grain (trade_date, ticker), Regular. Refreshed by `stockbit-updater` after F06 and F03 (`refresh.py`), read through one endpoint.
  - Requires a migration, Table/Column/Feature_Catalog rows, `measure_indexes.py` and the onboarding plan (AGENTS.md mandatory workflow).
- **(b) A publisher-written daily file** (e.g. `screener/flow/{as_of}.json.gz` with the last W+1 dates). No schema change; same path as the Terminal data. Published after the 19:00 WIB run when `broker_behind_sessions` = 0.
- **(c) On-demand compute with an in-process cache** keyed by the broker as-of date. No storage; the first request after a refresh pays 4.7 s cold or more.

---

## 6. Impact on the Backtest worker and Terminal

- **FACT:** the Backtest flow conditions read the published per-ticker broker files (`flow.ts`, `conditions.ts:190-245`; catalog `fnet`, `broker`, `top5` in `catalog.ts:53-55`), not F02, F03 or F06.
- **INFERENCE:** every proposal above is additive (a new table, file or endpoint) and leaves F05, `refresh_feature_*`, the publisher's broker files and the worker untouched. The existing Backtest does not break.
- **FACT:** there is no working screener in the repo today. `apps/edge-bff/static/index.html` holds 33 `screener-*` references, all CSS; there is no markup or logic.
  - **INFERENCE:** the "existing screener" the user mentions to retain most likely means the Backtest flow conditions `fnet`, `broker` and `top5`. They can be offered as is (B4 = `broker`; B1 with N = 5 = `top5`; F1 = `fnet`) if the board choice is all boards.
- **FACT:** whole-universe screening from published files is impractical. The 12 largest broker files hold 28.4 MB gzip (`apps/edge-bff/backtest/CONTRACT.md:184`); the largest, BBRI, is 2.2 MB gzip / 14.5 MB inflated (BACKTEST_END_TO_END.md:420).

---

## 7. Risks and unresolved product decisions

1. **Board** (FACT, material): Regular vs all boards changes 20D foreign net for 168 of 844 stocks; 20 flip sign.
   - The F06 catalog says do not sum across boards; the Backtest and Terminal use all boards.
   - PROPOSED: Regular by default (consistent with the price volume, FACT), all-boards toggle computed from 1d columns.
2. **Calendar:** stored F06 and F02 windows use ticker sessions; the dynamic and snapshot metrics proposed here use market sessions. They differ only for tickers with missing sessions (18 of 865 at 20D, FACT). Pick one and disclose it (M209 lesson).
3. **Bandar formula and thresholds:** the Terminal's Bandar detector and Broker action gauge are still waiting for an approved definition (DESIGN.md:37,40,147; FUTURE_PLAN.md:814). The prototype ratio (6 % / 10 %) is a heuristic; there is no validation evidence.
4. **bavg formula:** the gross VWAP of the top-3 buyers (proposed; equal to Stockbit Avg Buy) is not equivalent to the prototype's net-weighted typical price.
5. **Broker lag (M243):** the screener must show the broker as-of date separately from price.
   - Decision: a combined (flow + technical) screen evaluates flow at the broker date (labelled), or excludes the flow conditions, or waits.
   - The ADV universe filter should use price (close × volume) so it does not go stale. PROPOSED.
6. **Mid-refresh reads:** F02 and F06 commit per ticker (refresh.py), so gate on the round status, or build the snapshot only after `round_finished`.
7. **Custom parameters:** a snapshot only serves a fixed grid (D 5/10/20, N 3/5). Either restrict the UI to the grid, or allow custom D ≤ 20 on demand (Q3-20: 0.55 s warm / 0.85 s cold) with a cap and caching.
8. **Classification bias:** C1 uses the current broker classification (not point-in-time). Some foreign-domicile brokers are Retail-heavy (YP, ZP, YU, ...), so "foreign broker" ≠ "foreign investor" ≠ "institution".
9. **Planner trap** (FACT, Q2): joining F06 to a CTE calendar without a literal date range picked a sequential scan of 1.25 GB (18.6 s). Any implementation must pass explicit date bounds.
10. **UNKNOWN:** whether Stockbit's or IDX's public "foreign net" uses the Regular board or all boards (not checked here; no external call made).
