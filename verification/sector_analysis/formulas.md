# Sector Analysis prototype: data inputs and formulas

Scope: the static prototype `sector/logic.js` (1,621 lines; identical to the script embedded in `app_overview.txt`
lines 1991-3610) and its embedded data `window.SX` (`app_overview.txt` line 1990). Every formula below is quoted from
the code with its line number in `logic.js`. Field meanings come from the publisher that writes these files,
`apps/terminal-publisher/overview.py`, and `OVERVIEW_FORMULAS.md` in the repository.

Data snapshot used for the examples: prices to **Tue 17 Nov 2026** (`day.date`), broker data to **Mon 9 Nov 2026**
(`meta.broker_through`), 300 series dates from 2025-08-22.

---

## 0. Conventions and the SX data dictionary

### 0.1 Conventions used in the code

| Symbol | Code | Meaning |
|---|---|---|
| `E` | `dates.indexOf(DY.date)` (L22) | index of the page date in `series.dates`; here 299 (the last of 300) |
| "session" | | one entry of `series.dates` = one IHSG market date (publisher: final daily IHSG rows) |
| `C_s(i)` | `S.sector[s][i]` | close of sector index `s` at session `i` |
| `C_M(i)` | `IH = S.index[MT.market]` (L22) | IHSG close |
| `ret(a,i,n)` | L23 | `(a[i] / a[i-n] − 1) × 100`, null if either close is null |
| `rr(s,n,i=E)` | L24 | `ret(C_s,i,n) − ret(C_M,i,n)`: excess return vs IHSG in percentage points (pp) |
| `rankAt(n,i)` | L25 | rank 1..11 of the sectors by `rr(s,n,i)`, descending (null sorts last) |
| `sma(a,i,n)` | L26 | simple mean of `a[i−n+1..i]` |
| `members(s)` | L38-42 | the rows of `day.stocks` whose `meta.stocks.sector[i] = s` **and `size > 0`** (all 833 rows have size > 0 here), each with `r5 = r5d`, `v5 = r5d − ret(C_M,E,5)`, `r1m`, `ema = above_ema50`, `f5 = fnet_5d`, `size` |
| `NAMES` | `Object.keys(S.sector)` (L22) | the 11 IDX-IC sectors; "Other" (no index) is never a row |
| YTD base | `ovxYtd()` L964 (same loop in L268, L306) | last session of the previous calendar year: index 89 = 2025-12-30, so YTD = 210 sessions |
| Custom range | `ovxResolve(d0,d1)` L1003-1011 | `i0` = first session ≥ From, `i1` = last session ≤ To, at least 5 sessions; return base = `i0` itself |
| Colour scale | e.g. L572, L883, L1088 | alpha `k = min(1, |v| / cap) × 0.72 + 0.06`, green `rgba(8,153,129,k)` for v ≥ 0, red `rgba(242,54,69,k)` below; white text when k > 0.5. For shares the scale is centred on 50 % (`|v − 50| / 50`) |

Every card is anchored at `E`. Nothing in the page is dated earlier than the last session (section 1.3).

### 0.2 What each SX field is (from `overview.py`)

`window.SX` is the three Overview publisher files (`overview-series`, `overview-meta`, `overview-day-2026-11-17`) plus
one extra map `ind` that the publisher does **not** write.

| SX field | Meaning | Source (publisher) | Used by the page |
|---|---|---|---|
| `series.dates[300]` | the 300 newest market dates (`SERIES_SESSIONS`), oldest first | `DATES_SQL`, IHSG final daily rows of `Price_Stock_Indonesia_IDX` | yes (every card) |
| `series.index.IHSG`, `.LQ45` | daily final **closes in index points** (2 decimals) | `CLOSES_SQL` / `series_doc` L289-293 | IHSG everywhere; LQ45 only in `pmT` (benchmark toggle) |
| `series.sector[11]` | daily final **closes in index points** of the 11 IDX-IC sector indexes (IDXBASIC, IDXCYCLIC, IDXNONCYC, IDXENERGY, IDXFINANCE, IDXHEALTH, IDXINDUST, IDXINFRA, IDXPROPERT, IDXTECHNO, IDXTRANS: `Feature_Index_Entity` `entity_kind='SECTOR'`) | `CLOSES_SQL`, `series_doc` L294 | yes (nearly every card) |
|  | They are **index levels published by IDX** (IDX's free-float capitalisation-weighted sector indexes). They are not returns and EDGE computes no weighting of its own: every sector return in the page is a ratio of two levels. No nulls in this snapshot. | | |
| `series.above_ema50`, `.above_ema200` | % (2 decimals) of common stocks whose Feature 04 daily `close > ema_50` (`ema_200`), divided by the stocks that have an `ema_50` (`ema_200`) that date. **Whole market only**, no per-sector split | `BREADTH_SQL` L92-95, `series_doc` L295-296 | `brH`/`brT`/`brB` (IHSG line), and as an ingredient of the synthetic sector breadth |
| `series.breadth_n` | `[stocks with ema_50, stocks with ema_200]` per date (the denominators) | `series_doc` L297 | no |
| `series.flow{dates[294], foreign_buy, foreign_sell, turnover}` | per **broker date**: IHSG Regular-board foreign buy, foreign sell, turnover = foreign buy + domestic buy (`Feature_06_Foreign_Domestic_INDEX`) | `MARKET_FLOW_SQL`, `series_doc` L298-301 | no |
| `meta.market`, `meta.benchmark` | `IHSG`, `LQ45` | | `market` yes |
| `meta.stocks{ticker,name,sector}[862]` | every common stock of `IDX_Stock_Universe` (`Security Type='stock'`), ticker order; sector "Undefined" written "Other" (21 stocks) | `STOCKS_SQL`, `meta_doc` L276-277 | yes |
| `meta.sectors[12]` | 11 sectors with their index ticker, plus `Other` (index null) | `meta_doc` L278 | no |
| `meta.dates[20]` | the 20 newest market dates with Feature 01 rows (the date picker) | `meta_doc` L281 | no (see 1.3) |
| `meta.size_basis` | `adv20_value` | `overview_stock_size` | no (`day.stocks.size` is used) |
| `meta.prices_through`, `meta.broker_through` | newest price date; newest broker date (Feature 06 _INDEX, IHSG, Regular) | `files` L483-484 | `broker_through` only (pill, legacy footer) |
| `meta.periods.flow` | `['1D','5D','1M','3M']` | | no |
| (`meta.lists`) | stock lists and members: in the publisher's meta, **absent from SX** | `meta_doc` L279 | n/a |
| `day.date`, `day.prior_date`, `day.size_basis` | the page date, its previous session, the size basis | `day_doc` L341 | `date` only |
| `day.index.{IHSG,LQ45}` | open, high, low, close, prior close of that date | `day_doc` L337 | no |
| `day.volatility` | IHSG 20-session annualised sample volatility (`value`, %) and `rank_1y` (% of the previous 252 values strictly below) | `volatility`, `below_rank` | no |
| `day.breadth` | advancers / decliners / unchanged by Feature 01 `return_1d_pct` (> 0, < 0, = 0), all stocks | `day_doc` L344-346 | no (the page recounts per sector from `stocks.r1d`) |
| `day.market` | turnover, its 20-broker-date average and ratio, foreign net 1D/10D, foreign flow periods 1D/5D/1M/3M (buy, sell, net, from) at the broker date | `market_figures` | no |
| `day.stocks.i[833]` | position in `meta.stocks` of each stock that has a Feature 01 row that date (833 of 862) | `day_doc` L348 | yes |
| `day.stocks.close` | Feature 01 close | `DAY_SQL` | **no** (but `fwdBRN` fakes a close, G8) |
| `day.stocks.r1d`, `r5d`, `r1m` | Feature 01 `return_1d_pct`, `return_5d_pct`, `return_20d_pct` (%). Each counts *valid trading observations of that stock*, so **`r1m` is a 20-observation return**, not 21 | `DAY_SQL` L82-85 | yes |
| `day.stocks.size` | `overview_stock_size(date)`, basis `adv20_value`: Σ(close × volume) over the last 20 market sessions ÷ 20, in IDR (a day without trades counts 0). It is a **liquidity** measure, not market cap (`OVERVIEW_FORMULAS.md` §7) | `SIZE_SQL` | yes: membership filter (`size > 0`), weights, treemap areas, dot sizes, liquidity floor |
| `day.stocks.above_ema50`, `above_ema200` | 1 if Feature 04 `close > ema_50` (`ema_200`) that date, 0 if not, null without a Feature 04 value (8 nulls for EMA200) | `DAY_SQL` | yes; null is treated as "below" everywhere |
| `day.stocks.fnet_1d/5d/1m/3m` | Feature 06 `foreign_net_1d/5d/20d/60d`, Regular board, **at the broker date** (9 Nov, not 17 Nov); null without a row (4 stocks) | `STOCK_FLOW_SQL` | `fnet_5d` only, in the hidden legacy stock table |
| `day.intraday.{1h,5m}` | IHSG 1-hour bars of the 5 sessions to the date, 5-minute bars of the session (empty here) | `INTRADAY_SQL` | no |
| `ind{841}` | ticker → **IDX-IC Industry** label (section 10). Not a publisher field: it matches `IDX_Stock_Universe."Industry"` (also `Feature_01_Stock_Daily.industry`) | not published | `rsD`, `mkCard`, detail windows |

Production also has a file the prototype does not embed: **`overview-stocks`** (`stocks_doc` L405-410): every common
stock's **daily close on all 300 series dates** and its Regular-board **daily foreign net on every broker date**
(±1 MB). It closes several gaps below (G1, G9, partly G2).

### 0.3 Which cards are actually drawn

`RENDER` (L1212) decides what runs on each tab.

| Tab | Drawn | In the markup but not drawn |
|---|---|---|
| Overview | KPI row `#kpis`; `rcCard`, `mmCard`, `hxCard`, `mkCard` (`ovxAll` L1208) | `snCard` is rendered but hidden (`display:none`); the legacy Sector Performance `#spb` and Sector stocks `#stc` (with the CSV button) are rendered into a `hidden` block |
| Relative Strength | `rsA`, `rsB`, `rsD`, `rsL`, `rsW`, `rsC` | none |
| Rotation | `rotA`, `rotD` (function `rotCmp`), `rotB`, `rotC` | none |
| Pair Matrix | `pmM`, `pmR`, `pmT`, `pmS` | `pmA`, `pmB` (parent `display:none`, never called by `RENDER.pm`) |
| Breadth | `brH`, `brT`, `brA`, `brN`, `brD` | `brM` (`display:none`), `brC`, `brB` (hidden block); none is ever called |

Every drawn card except `rotD` has an expand button (`FW_P`, L1299-1311). It opens a floating window (at most 3)
with its own copy of the filters and, for every card except `brD`, a **detail table** (`fwd*`, L1358-1531). The
detail tables are documented under their card.

---

## 1. Page chrome

### 1.1 KPI row (`#kpis`, `kpis()` L65-75)

Visible on the Overview tab only (`showTab` L1214).

- **Inputs:** `series.index.IHSG`, `series.sector[*]`. Lookback 30 sessions (sparkline); RRG needs 25 sessions of
  warm-up (section 4.1).
- **Formulas:**
  1. *IHSG · 5D*: value `C_M(E)`. Change in points `ihd = C_M(E) − C_M(E−5)`, and in % `ret(C_M,E,5)`. Sparkline:
     the 30 closes `C_M(E−29..E)`, green when `ihd ≥ 0`.
     Example: 5,304.76, +179.03 (+3.49 %).
  2. *Beating IHSG · 5D*: number of sectors with `rr(s,5) > 0`, written "x / 11". Example: 4 / 11.
  3. *Strongest sector · 5D*: the sector with the largest `rr(s,5)`. Example: Transportation & Logistic +1.78 pp.
  4. *Improving · RRG*: number of sectors whose RRG quadrant at E is Improving (`rrg()` L27-34, section 4.1).
     Example: 6 / 11. "Biggest rank gain" = largest `drank = rankAt(5,E−5)[s] − rankAt(5,E)[s]` (L43-45).
     Example: Transportation ▲8.
- **GAP:** none in data. "11" is hard-coded (L72-74). The ▲ is printed even when the best gain is 0 or negative.
- **Per-sector only.** Cost: trivial (11 × 30).

### 1.2 Pills (`#pills`, `head()` L54-58)

- **Inputs:** `day.date`, `meta.broker_through`.
- "Prices to `<weekday day month>`" (green) and "Broker data to `<broker date>`" (always amber: the code does not
  compare the two dates). `#dlab` on the date button = "`<date>` · Close".
- **GAP:** none. Only the hidden legacy stock table shows broker data, so the broker pill describes nothing visible.

### 1.3 Date button (`#datebtn`, L1233-1242)

- **Inputs:** `day.date` only. The menu lists one item, the latest close, with "Earlier dates are not available in
  this prototype; they need the data service".
- **GAP (G10):** choosing a date needs
  - the date list (`meta.dates`, 20 dates, already in SX and unused);
  - the day file of each date (`overview-day-<date>`, one per date);
  - moving `E` to that date's index in `series.dates`.
  Every formula is written relative to `E`, so no formula changes. At the oldest picker date (index 280) only
  280 sessions of history exist. Two cards are then short: the Pair Ratio 1Y (needs 300, section 5.2) and the
  52-week rotation timeline (needs 280, section 4.1).

### 1.4 Open in Screener (`#scrbtn`, L1243-1245)

- Marked `aria-disabled`. A click shows a toast: "not available in this prototype". No data is read.
- **GAP (G11):** no destination. A real one is a Screener route with a sector filter (the pinned sector `ST.pin`).

### 1.5 CSV export (`#csv`)

- The only "Export CSV" button is in the **hidden** legacy "Sector stocks" card (markup, `#stc`). `logic.js` has no
  handler for it, nor for its "All N stocks" button `#allst`. Nothing exports.
- **GAP (G12):** not implemented. The natural payload is a floating window's detail table (`fwDetail` builds
  `D.cols` / `D.rows`, L1535-1554). It needs no new data.

### 1.6 Lock / pin (shared state)

- `pin(nm)` / `lockT(nm)` (L153, L175-178) set `ST.pin`. The cards that show a single sector read it:
  - `pinSec()` (L50) = the pinned sector, or **"Infrastructures" hard-coded** when nothing is pinned (`rsL`, `rotC`,
    `mkCard` in a window, several detail tables);
  - the Breadth tab has its own selection `TT.bhS` ("IHSG" = all stocks); picking a sector there also pins it
    (`brSet` L749).
- The lock pill was removed (`lockUI` returns at once, L1221).

---

## 2. Overview tab

### 2.1 `snCard`: Sector Snapshot (`ovxSnap()` L1095-1103), hidden

- Rendered on every redraw but `display:none` in the markup.
- **Inputs:** `series.index.IHSG`, `series.sector[*]`. Lookback 64 sessions.
- **Formula:** one tile each for IHSG and the 11 sectors:
  - big number = `ovxRet(a,1)` = 1-session return;
  - "1M" = `ovxRet(a,21)`;
  - sparkline = `a[E−63..E]` (64 closes), green if the last close ≥ the first.
  - Click = pin.
- **GAP:** none. **Per-sector.** Cost trivial.

### 2.2 `rcCard`: Cumulative Return (`ovxList`, `ovxLine`, `ovxLegend`, `ovxDefaultSel`; L959-1058, wiring L1105-1137)

- **Inputs:** `series.sector[*]`, `series.index.IHSG`, `series.dates`.
- **Lookback:** period `OVX.w` is 1M = 21, **3M = 63 (default)**, YTD = 210, or Custom (any range inside the 300
  sessions, at least 5 sessions). The longest is 299 sessions (Custom).
- **Formula:**
  - base `b = ovxBase(w)` = `E − n`, or the YTD base, or Custom `i0`; end `e = ovxEnd(w)` = `E`, or Custom `i1`
    (L965-966).
  - Path `P_s(i) = (C_s(i) / C_s(b) − 1) × 100` for `i = b..e` (`ovxPath` L968); IHSG the same (dashed).
  - Right-hand list: `ovxRet(C_s, w) = P_s(e)`, sorted descending; bar width = `|v| / max|v| × 50 %` (L1032-1033).
  - Lines drawn: the hovered or pinned sector alone, otherwise the selected set. The default set is the 2 best and
    2 worst sectors by period return (`ovxDefaultSel` L973); the legend toggles membership.
  - `OVX.w`, the Custom range, the scatter axes, the heatmap sort and the legend are kept in `localStorage`
    (`edge.sa.overview.v1`, L985-1001; browser only).
  - **Custom base = `i0`** (the close of the first session in the range). The Overview page (`OVERVIEW_FORMULAS.md`
    §12b) bases a Custom return on the session *before* the first one, and caps the range at 365 days. Here there is
    no cap (I3).
- **Detail window `fwdRC`** (L1358-1365): one row per sector and IHSG over `[b, e]`:

  | Column | Definition |
  |---|---|
  | Return | `(C(e) / C(b) − 1) × 100` |
  | vs IHSG | Return − IHSG Return (pp) |
  | Max DD | `min_i (C(i) / max(C(b..i)) − 1) × 100` (`fwMdd` L1353) |
  | Best day, Worst day | max and min of the daily % returns over `(b, e]` |
  | Up days | share of the sessions in `(b, e]` that closed higher |
- **GAP:** none (the sector levels are real).
- **Per-sector only.** Cost: 12 series × ≤ 300 points.

### 2.3 `mmCard`: Momentum, Horizon vs Horizon (`ovxScatter()` L1059-1083)

- **Inputs:** `series.sector[*]` (IHSG only in the detail table). Lookback = the longer axis: 1W = 5, 1M = 21, 3M = 63,
  YTD = 210.
- **Formula:**
  - `x = ovxRet(C_s, OVX_HZ[mx])` and `y = ovxRet(C_s, OVX_HZ[my])`, with `mx, my ∈ {1W, 1M, 3M, YTD}`; default
    **x = 3M, y = 1M** (L959).
  - Axis ranges include 0, padded 12 %.
  - Dot colour: green if x ≥ 0 and y ≥ 0, red if both < 0, amber otherwise.
  - Quadrant labels: "Up on both", "Turning up" (x < 0, y ≥ 0), "Down on both", "Turning down".
- **Detail `fwdMM`** (L1366-1373): x, y, `d = y − x` (pp), the reading, the rank of x and of y among the 11 sectors;
  IHSG row.
- **GAP:** none. **Per-sector.** Cost trivial.

### 2.4 `hxCard`: Sector × Horizon (`ovxHeat()` L1084-1094)

- **Inputs:** `series.sector[*]`, `series.index.IHSG`. **Lookback 250 sessions** (1Y).
- **Formula:**
  - Columns `OVX_HZ` (L961): 1D = 1, 1W = 5, 1M = 21, 3M = 63, 6M = 126, YTD, 1Y = **250** sessions.
  - Cell = `ovxRet(C_s, h)`.
  - Colour per column: `cap_h = max_s |v|`, alpha scale as in 0.1.
  - Rows sorted by column `OVX.hk` (default index 2 = **1M**), toggled by clicking a header; IHSG row last, uncoloured.
  - Example (Financials): 1D +0.45, 1W +3.65, 1M +9.37, 3M −6.48, 6M −7.29, YTD −18.82, 1Y −13.30 %; IHSG
    −0.30, +3.49, +6.17, −17.04, −21.10, −38.65, −35.02 %.
- **Detail `fwdHX`** (L1374-1382): excess = sector − IHSG per horizon (pp); the rank per horizon; "Avg rank" = mean
  of the 7 ranks.
- **GAP:** none. 1Y = 250 here, but 252 on the Overview page (`model.ts` `YEAR = 252`) (I2).
- **Per-sector.** Cost: 12 × 7.

### 2.5 `mkCard`: Market map (`ovxMap()` L1165-1207, squarify `ovxSq` L1169-1179)

- **Inputs:**
  - `meta.stocks.{ticker,name,sector}`, `day.stocks.{i,size,r5d}`, `ind`;
  - `series.index.IHSG` (5D);
  - `series.sector[n]` (header row).
  - Stock data: the page date only. Header lookback 210 (YTD).
- **Which sector `n`:** initially the sector with the best 5-session index return (L1117); afterwards the pinned
  sector (`ovxPin` L1104); a window keeps its own copy, or `pinSec()` when it has none (L1303).
- **Formula:**
  1. Stocks: `members(n)` with `r5d` not null. Each gets `ind = SX.ind[ticker] || 'Unclassified'` and
     `v5 = r5d − ret(C_M,E,5)` (pp).
  2. Groups by `ind`. Group weight `w = Σ size`. Group label `v5_g = Σ(size·v5) / w` (adv20-value-weighted excess).
     Groups are sorted by `w` and laid out by a squarified treemap on `w`.
  3. Inside a group: the **10 largest stocks by `size`**. Their areas are `size`, re-normalised to fill the whole
     group box, so the stocks beyond 10 are dropped and their area goes to the 10.
  4. Colour = `v5`, `cap = max |v5|` over the sector's stocks, alpha scale 0.1. The tile text is `v5` in pp.
  5. Header strip `#mkS`:
     - sector index return at 1D, 1W (5), 1M (21), 3M (63), YTD, coloured with `cap = max over the 11 sectors` per
       horizon;
     - second row = sector − IHSG (pp).
  6. Footer: "N stocks in K subsectors · largest 10 per subsector".
- **Detail `fwdMK`** (L1383-1391), per `ind`, over all members (`fwStocks`, including null `r5d`):

  | Column | Definition |
  |---|---|
  | n | number of members |
  | value share | `Σ size / Σ size of the sector × 100` |
  | 5D | `Σ size·(r5d ?? 0) / Σ size`: **a null counts as 0** |
  | vs IHSG | 5D − IHSG 5D |
  | Up 5D | % of members with `r5d > 0` |
  | Leader | the member with the best `r5d`, and its `r5d` |
- **GAP / caveats:**
  - "Subsector" is the IDX-IC **Industry** (`ind`). The publisher does not write it (G3a).
  - The colour period is fixed at 5D: the day file has stock returns at 1D, 5D and 20 sessions only.
  - Weights and areas are 20-day **trading value**, not market cap (G3b).
  - Properties & Real Estate has one industry (77 stocks), so its map is a single group.
- **Per-stock, page date only** (no stock history). Cost: ≤ 136 stocks (Consumer Cyclicals).

### 2.6 Legacy hidden cards (rendered, inside `<div class="sx-grid" hidden>`)

- **Sector Performance `#spb`** (`sectors()` L120-133):
  - cumulative path from `s = E − ST.sp`, with `ST.sp ∈ {20, 60 (default), 250}`;
  - highlighted lines = the 2 best and 2 worst;
  - Bug: the YTD button gives `+'YTD' = NaN`, so the card falls back to 60 sessions; Custom is ignored (I5).
- **Sector stocks `#stc`** (`stocks()` L136-148):
  - the top or bottom 5 members of the active sector by `v5`;
  - columns: 5D vs IHSG, 1M (`r1m`), > EMA50 flag, Foreign 5D (`fnet_5d` at the broker date), Value/day (`size`);
  - the CSV and "All stocks" buttons do nothing (1.5).
- Kept, the comment says (L956-958), "for the sector detail pop-up that comes later".

---

## 3. Relative Strength tab

### 3.1 `rsA`: Relative Return (`rsA()` L183-193)

- **Inputs:** `series.sector[*]`, `series.index.IHSG`. Lookback 10 (detail window 21).
- **Formula:**
  - Window `n = TT.rsN ∈ {3, 5 (default), 10}`; the same `n` drives `rsB` and `rsC`.
  - Mode "vs IHSG" (default) bar = `rr(s,n)` (pp). Mode "Absolute" bar = `ret(C_s,E,n)`, with a marker at IHSG's
    `ret(C_M,E,n)`.
  - Sorted descending; bar scale = `max|v| × 1.1`.
  - Click = lock the sector.
- **Detail `fwdRSA`** (L1392-1399): `rr` (or `ret`) at 1, 3, 5, 10, 21 sessions; "Rank nD".
- **GAP:** none. **Per-sector.** Cost trivial.

### 3.2 `rsB`: Rank change (slope chart, `rsB()` L195-226)

- **Inputs:** as `rsA`. Lookback = `k + n`: with the presets at most 21 + 10 = 31; Custom any date with index ≥ n.
- **Formula:**
  - Compare date `P0 = E − k`, `k ∈ {5 (default), 10, 21 (1M)}`, or Custom: the last session ≤ the chosen date,
    before `E`, with index ≥ n (L202-204).
  - Left rank `a = rankAt(n,P0)`, right rank `b = rankAt(n,E)` (rank by n-session excess return).
  - Line colour: green if `a − b ≥ 3`, red if ≤ −3, else grey. The tooltip also shows `rr(s,n,P0)` → `rr(s,n,E)`.
- **Detail `fwdRSB`** (L1400-1406): the rank at `E−20, E−15, E−10, E−5, P0, E` (dates ≥ n); "Places gained" =
  `rank(P0) − rank(E)`; `rr(s,n)`.
- **GAP:** none. **Per-sector.** Cost: 11 × ≤ 6 rankings.

### 3.3 `rsW`: Weekly Excess Return heatmap (`rsW()` L245-260)

- **Inputs:** as `rsA`.
- **Lookback:** `5·NW + 5`: 8W = 45 sessions, Custom up to 26 weeks = 135 sessions. Row order needs 20.
- **Formula:**
  - Weeks are **non-overlapping 5-session blocks** ending at `e1` (= E, or the Custom end):
    `K_k = e1 − 5·(NW−1−k)`, `k = 0..NW−1`, with `NW ∈ {4, 8 (default)}`. Custom gives
    `NW = min(26, max(1, ⌊(i1 − i0) / 5⌋))`.
  - Cell = `rr(s, 5, K_k)` = sector 5-session return − IHSG 5-session return over `(K_k − 5, K_k]`.
  - Rows sorted by `rr(s,20)` (20 sessions, not 21). Colour cap = max |cell| over the grid.
- **Detail `fwdRSW`** (L1407-1414):
  - average week; weeks ahead (cell > 0) / NW; best and worst week;
  - streak = the latest run of weeks with the same sign ("n up" / "n down").
- **GAP:** none. **Per-sector.** Cost: 11 × 26.

### 3.4 `rsD`: Sector Drill-down (`rsD()` L261-301)

- **Inputs:**
  - `series.sector[*]`, `series.index.IHSG`;
  - `day.stocks.{r5d, r1m, size, above_ema50}` through `members()`;
  - `ind`, and the RRG quadrant (`rrg()`).
- **Lookback:** YTD 210, 3M 63; "Δ 4W" needs 41 (`rr(s,21,E−20)`); RRG 25+.
- **Formula, sector rows** (L272-277, L290):

  | Column | Definition |
  |---|---|
  | 3D, 1W, 1M, 3M | `ret(C_s,E,n)` for n = 3, 5, 21, 63 |
  | YTD | `C_s(E) / C_s(YTD base) − 1` |
  | vs IHSG 1M | `eM = r_s(21) − r_M(21)` |
  | vs IHSG 3M | `e3 = r_s(63) − r_M(63)` |
  | RS | **RS rating 1-99** = `round(1 + 98·(N−1−k)/(N−1))`, where k is the 0-based position of `eM` in descending order among the N = 11 sectors (`rate()` L269) |
  | Δ 4W | `rt − rt4`. `rt4` is the same rating computed on `eM4 = rr(s,21,E−20)`, the 1M excess as of 20 sessions ago |
  | > EMA50 | % of members (size > 0) with `above_ema50 = 1` today (null counts as below) |
  | RRG | quadrant of `rrg(s)` at E (section 4.1) |
  | Momentum | `g = e1 − eM·5/21`, with `e1 = r_s(5) − r_M(5)`: **Gaining** if g > +0.5 pp, **Fading** if g < −0.5 pp, else **Steady** (L270) |

  Every column sorts. Click = lock the sector. The sort key for RRG uses Leading 4, Improving 3, Weakening 2,
  Lagging 1.
- **Formula, subsector (industry) rows** (L273-275, L278, L280):
  - members grouped by `ind`;
  - 1W `r1 = Σ size·r5d / Σ size` and 1M `rM = Σ size·r1m / Σ size` (adv20-value-weighted; nulls dropped);
  - `e1`, `eM` against IHSG 5 and **21** sessions (the stock `r1m` is 20 observations, I1);
  - "> EMA50" share;
  - RS rating among **all industries of all sectors** (`ALLU`) by `eM`.
- **Fake fields in the subsector rows** (seeded Park-Miller PRNG, seed 7, L267, L280):
  - `u.r3 = sector r3 + (rnd − .5)·14`;
  - `u.ry = sector YTD + (rnd − .5)·20`;
  - `u.e3 = u.r3 − IHSG 3M`;
  - `u.rt4 = clamp(1, 99, rt + round((rnd − .5)·40))`;
  - `u.quad` random: if eM ≥ 0, Leading with probability 70 %, else Weakening; otherwise Lagging 60 %, else Improving.
- **Subsector rows are never shown:** `open` is a new empty `Set` on every render (L281, L296), so only the 11
  sector rows appear. The fake values are computed and discarded.
- **Detail `fwdRSD`** (L1415-1420), stocks of `pinSec()`: industry, `r1d`, `r5d`, `r5d − IHSG 5D`, `r1m`, the EMA50
  flag, `size`.
- **GAP (G2):** industry 3M, YTD, vs IHSG 3M, Δ 4W and RRG quadrant are random. They need an industry-level price
  series:
  - a chain-linked index from member closes over ≥ 210 sessions (YTD), ≥ 63 + 20 (rating 4W ago) and ≥ 25 (RRG), or
  - at least the per-stock closes at `E−20`, `E−21`, `E−41`, `E−63` and the YTD base.

  `overview-stocks` (300 closes per stock) is enough to compute these. A weighting must be chosen (G3b).
- **Per-sector, plus per-stock on the page date** (members' r5d/r1m/size/flags). Cost: 833 stocks, 11 + 58 rows.

### 3.5 `rsL`: Sector stocks, cumulative (`rsL()` L302-347)

- **Inputs:** `series.sector[pinSec()]`, `day.stocks.size` (to choose the 10). The stock paths are synthetic.
- **Lookback:** window `TT.rsLw ∈ {21, 63 (default), YTD, Custom}`, up to 299.
- **Formula:**
  - the sector index path `(C_s(i) / C_s(b0) − 1) × 100`, real, dashed;
  - the **top 10 members by `size`**; the 2 best and 2 worst final values are coloured;
  - hovering a line highlights it.
- **FAKE (G1)** (L307-311). For each ticker:
  - seed = FNV-1a hash of the ticker;
  - `β = 0.6 + 0.9·rnd`, `drift = (rnd − .5)·0.004`, `vol = 0.008 + 0.014·rnd`;
  - price `p_0 = 100`, `p_i = p_{i−1}·(1 + β·r_sector(i) + drift + vol·z)`, with `z = (rnd+rnd+rnd − 1.5)·2`.
- **Detail `fwdRSL`** (L1421-1426): real `r1d`, `r5d`, `r5d − sector 5D`, `r1m`, `size` of the 10.
- **Real data needed:** the daily closes of each stock over the window, ≤ 300 sessions. `overview-stocks` already
  carries them. Rebase: `(close_i / close_b0 − 1) × 100`.
- **Per-stock history** (10 stocks × ≤ 300). Cost trivial once the data is there; the cost is the ±1 MB
  `overview-stocks` download, or a server endpoint per sector.

### 3.6 `rsC`: Acceleration and streak (`rsC()` L348-357)

- **Inputs:** `series.sector[*]`, IHSG.
- **Lookback:** 10 for acceleration; `n + 5` for the rank change (≤ 15); the streak may scan back to the start of the
  series.
- **Formula:**
  - `r3 = rr(s,3)`, `r10 = rr(s,10)`;
  - acceleration `acc = rr(s,3)/3 − rr(s,10)/10` (pp per session);
  - streak `streakAt` (L179-180) = number of consecutive sessions ending at E with
    `C_s(i)/C_s(i−1) > C_M(i)/C_M(i−1)`; a pill turns green at ≥ 5;
  - Rank (nD) = `rankAt(n,E)`; rank change 5D = `rankAt(n,E−5) − rankAt(n,E)`;
  - sorted by acceleration.
- **GAP:** none. **Per-sector.** Cost trivial.

---

## 4. Rotation tab

### 4.1 `rotA`: Relative Rotation Graph (`rotA()` L369-412; series `rrgSeries`/`RRGS`/`QS` L169-174; IHSG strip `rotIH` L455-476; timeline `rotTL` L433-453)

- **Inputs:** `series.sector[*]`, `series.index.IHSG`, `series.dates`.
- **Lookback:**
  - RS-Ratio needs 20 sessions and RS-Momentum 5 more, so the first value is at index 24 (2025-09-26).
  - The IHSG strip and the Timeline show **52 weekly points** `E − 5·(51−j)`; the oldest is index 44 (2025-10-24).
  - In total ≈ 280 sessions. A 12W tail at the earliest selectable date adds 60.
- **Formula (precise; not JdK):**
  - RS line `r_s(i) = C_s(i) / C_M(i)`.
  - **RS-Ratio** `RSR_s(i) = 100 · r_s(i) / SMA20(r_s)(i)`, for i ≥ 19.
  - **RS-Momentum** `MOM_s(i) = 100 · RSR_s(i) / RSR_s(i−5)`.
  - Quadrant: RSR ≥ 100 and MOM ≥ 100 → **Leading**; RSR ≥ 100 and MOM < 100 → **Weakening**; RSR < 100 and
    MOM ≥ 100 → **Improving**; else **Lagging** (L173).
  - The card's "Draft formula" chip says the same.
  - This is a ratio-to-own-20-day-mean, with neither the smoothing nor the volatility normalisation of de Kempenaer's
    JdK RS-Ratio/RS-Momentum. Its scale differs by sector volatility; the axes are scaled to 1.15 × the largest
    deviation from 100.
- **RRG view:**
  - RRG date `K` = E by default. A click on the IHSG strip moves it to a weekly point ≥ `rotMinK()` (L456), the first
    week where every sector has MOM at `K − 5·TW`.
  - Tail = `TW + 1` points `K − 5·(TW−k)`, with `TW ∈ {4 (default), 8, 12}` weeks.
  - Dot = the point at K, coloured by quadrant. Tails are smoothed with Catmull-Rom (drawing only).
- **IHSG strip** (`rotIH`): IHSG close at the 52 weekly points. The grey band is the tail period; the label gives
  `C_M(K) / C_M(K − 5·TW) − 1`.
- **Timeline view** (`rotTL`):
  - 11 rows × 52 weekly columns, cell colour = `QS[s][week]`; weeks after K are faded;
  - "in phase" = the number of consecutive weekly samples ending at K in the current quadrant, "n+" when it runs to
    the first column;
  - rows sorted by quadrant (Leading, Weakening, Lagging, Improving), then by RSR descending.
- **Detail `fwdROTA`** (L1428-1435), at K:
  - RS-Ratio, RS-Mom, quadrant, weeks in;
  - Δ Ratio 1W = `RSR(K) − RSR(K−5)`, Δ Mom 1W likewise;
  - heading = the compass name of `atan2(ΔMom, ΔRatio)` in 45° slices (`fwHead2` L1427).
- **Detail `fwdROTB`** (L1436-1441): every change of quadrant between consecutive weekly samples over the 52 weeks;
  "Clockwise" when the move is one step along Lagging → Improving → Leading → Weakening.
- **GAP:** none in data (the formula is a draft by its own label). **Per-sector.** Cost: `RRGS` is built once,
  11 × 300 × 20 ≈ 66 k operations.

### 4.2 `rotD`: Rotation direction & speed (`rotCmp()` L414-429)

- **Inputs:** `RRGS`. Lookback = `5·NW` before K (≤ 20) on top of the RRG warm-up.
- **Formula:**
  - `LB = 5·NW` with `NW ∈ {1 (default), 2, 4}` weeks;
  - `dx = RSR(K) − RSR(K−LB)`, `dy = MOM(K) − MOM(K−LB)`;
  - direction `deg = (atan2(dy, dx)·180/π + 360) mod 360`; speed = `hypot(dx, dy)`;
  - arrow length = `10 + 22·speed / max speed`;
  - colour by angle: 0-90° green, 90-180° blue, 180-270° red, 270-360° amber (`CMPC` L415);
  - sort by angle (default) or by speed.
  - Click highlights in the RRG (Ctrl/Cmd adds).
- Not expandable (`FW_P` L1307); `fwdROTD` (L1449-1455) exists unused.
- **GAP:** none. **Per-sector.** Cost trivial.

### 4.3 `rotB`: Rotation detail (`rotRows()` L478-484, `rotB()` L485-508)

- **Inputs:** `RRGS`, `QS` (daily quadrants). Always at **E**: it does not follow the RRG date K.
- **Lookback:** the last change can be anywhere back to index 25; "Previous" ≤ 21 sessions.
- **Formula:**

  | Column | Definition |
  |---|---|
  | Current quadrant | `q(E)` |
  | Previous | `q(E − P)`, `P ∈ {5 (default), 10, 21}`; "=" when unchanged |
  | Speed | `hypot(RSR(E) − RSR(E−5), MOM(E) − MOM(E−5))` |
  | Last change | latest i with `q(i) ≠ q(i−1)` on the **daily** series, shown as "from `q(i−1)` · date(i)" |

  Hidden fields:
  - `dm = MOM(E) − MOM(E−3)`, the default tie-break, descending;
  - `ang` = the angle of the 5-session move;
  - `s` = days in the current quadrant.

  Multi-column sort, up to 3 levels.
- No detail of its own (`fwdROTB` lists the changes).
- **GAP:** none. **Per-sector.**

### 4.4 `rotC`: Stock momentum quadrant (`rotC()` L509-543)

- **Inputs:**
  - `day.stocks.{r1m, r5d, size}` of `members(pinSec())`;
  - benchmark IHSG or the sector index (`series.index.IHSG` / `series.sector[s]`).
- **Lookback:** stocks, page date only; benchmark 21 sessions.
- **Formula:**
  - `x = r1m − bench1M` and `y = r5d − bench5D`, with `bench1M = ret(bench,E,21)`, `bench5D = ret(bench,E,5)`;
    default bench = IHSG.
  - Quadrant by the signs of x and y (Leading x ≥ 0 & y ≥ 0, Weakening x ≥ 0 & y < 0, Improving x < 0 & y ≥ 0,
    Lagging); counts per quadrant.
  - Dot radius `2.5 + 7·√(size / max size)`; colour by the sign of y. Axes clipped to the 2nd-98th percentile, at
    least ±2.
  - Labels on the 8 largest.
- **Detail `fwdROTC`** (L1442-1448): per stock: industry, x, y, quadrant, `size`.
- **GAP:** none fake. But x mixes a **20-observation** stock return with a **21-session** benchmark return (I1).
  `r5d` counts the stock's own valid observations (a suspended stock spans more sessions).
- **Per-stock, page date only.** Cost: ≤ 136 dots.

---

## 5. Pair Matrix tab

The helpers (L547-553):
- `pqR(s,i) = C_s(i)/C_s(i−1) − 1`;
- `pqRet(a,i0,i1) = (a[i1]/a[i0] − 1)·100`;
- `pqCorr` = Pearson correlation;
- `pqSer(s,w,e)` = the w daily returns ending at e;
- `pqZ(a,b,w)` = z of the ratio `C_a/C_b` at E against its w-session mean and **population** sd.

There are 11 sectors, so 110 ordered cells and 55 unordered pairs.

### 5.1 `pmM`: Sector Pair Matrix (`pmM()` L561-588)

- **Inputs:** `series.sector[*]`.
- **Lookback:** Spread 3M = 63 (Custom up to 299, base ≥ 1); Correlation 120D = 121 closes; default pair 60.
- **Formula:**
  - Default pair on the first render: the ordered pair with the largest `|pqZ(x,y,60)|` (L563). Example: Consumer
    Cyclicals / Basic Materials, z = 3.02.
  - **Spread** (default): period `[i0, i1] = pqRange(P)` = `[max(1, E−P), E]`, with
    `P ∈ {5, 21 (default), 63, Custom}`. `rs_s = pqRet(C_s, i0, i1)`; cell(x,y) = `rs_x − rs_y` (pp).
    Colour cap = max |cell|.
  - **Correlation:** cell = Pearson ρ of the daily returns of x and y over the last `CW ∈ {20, 60 (default), 120}`
    sessions. Colour navy, alpha `max(0, ρ)·0.8` (a negative ρ gets no colour). The old "z" mode is mapped to
    Correlation (L564).
  - Rows and columns are ordered by `rs` descending. A column header re-sorts the rows by their value against that
    column.
  - Click a cell = open the pair in `pmR`, `pmS` and `pmT`.
- **Detail `fwdPMM`** (L1456-1463): the 55 pairs, leader first: spread, ahead return, behind return, Corr 60D.
- **GAP:** none. **Per-sector.** Cost: 110 cells × ≤ 120 returns ≈ 13 k.

### 5.2 `pmR`: Pair Ratio (`pmR()` L590-626)

- **Inputs:** `series.sector[A]`, `series.sector[B]`.
- **Lookback:** `P + MA` with `P ∈ {63, 126 (default), 250}` and `MA ∈ {20, 50 (default)}`. 1Y with MA50 needs all
  300 sessions; `i0 = max(MA, E − P)` makes "1Y" 249 sessions here.
- **Formula:**
  - ratio `Q(i) = C_A(i) / C_B(i)`;
  - `μ(i) = SMA_MA(Q)(i)`, `σ(i)` = population sd of Q over the same MA window;
  - plotted rebased to 100 at `i0`: `Q/Q(i0)·100`, `μ/Q(i0)·100`, and the bands `(μ ± 2σ)/Q(i0)·100`;
  - Spread = `pqRet(C_A,i0,E) − pqRet(C_B,i0,E)` (pp);
  - Band position: above the upper band / below the lower band / inside, with `%B = (v − dn)/(up − dn)·100`;
  - Custom: `[max(MA, i0), i1]`;
  - A/B pickers and a swap.
- **Detail `fwdPMR`** (L1464-1473): the last ≤ 60 sessions:
  - A 1D, B 1D, spread 1D;
  - cumulative spread since `i0`;
  - vs MA `(Q/μ − 1)·100`;
  - band z `(Q − μ)/σ`.
- **GAP:** none. **Per-sector.** Cost: ≤ 250 × 50.

### 5.3 `pmT`: Beta & Correlation to the benchmark (`pmT()` L628-651)

- **Inputs:** `series.sector[*]`, `series.index.IHSG` or `.LQ45` (`S.index[BM]`).
- **Lookback:** `W + 1` with `W ∈ {20, 60, 120 (default), 250, Custom}`. Δβ needs `2W + 1` (241 for 120D); for 250D
  Δβ is always null (it would need 501).
- **Formula:**
  - window `[j0, j1] = [E − W, E]`; daily simple returns over `(j0, j1]` (W of them);
  - **β = ρ · σ_s / σ_b** (population sd; equal to cov/var); **Corr = ρ** (Pearson);
  - Return `rt = pqRet(C_s, j0, j1)`;
  - vs BM = `rt − pqRet(C_b, j0, j1)`;
  - **Alpha** = `rt − β · pqRet(C_b, j0, j1)` (pp);
  - **Δβ** = `β(j0, j1) − β(j0 − W, j0)` when `j0 − W ≥ 1`;
  - a maximum drawdown is computed and not shown;
  - multi-sort, default β descending;
  - a row click makes that sector A of the pair.
- **Detail `fwdPMT` (FAKE, G9)** (L1474-1483): stocks of sector A.
  - **β_stock = β_sector·(0.55 + 0.9·rnd)**;
  - **corr_stock = clamp(0.05, 0.98, ρ_sector·(0.55 + 0.5·rnd))**, seeded by the stock's index;
  - 1M (`r1m`) and 1M − bench 21-session, and `size`, are real.
- **Real data needed for the detail:** each stock's daily closes over W (≤ 250), from `overview-stocks`, then the same
  β/ρ formula. 862 × 250 ≈ 216 k returns per window: possible in the browser, cleaner precomputed for the standard
  windows.
- **Card:** per-sector. **Detail:** per-stock history.

### 5.4 `pmS`: Stretched Pairs (`pmS()` L653-673)

- **Inputs:** `series.sector[*]`, IHSG. Lookback 21 (detail 63).
- **Formula:**
  - For each of the 55 pairs: `s_n = rr(x,n) − rr(y,n)`, which equals `ret(C_x,E,n) − ret(C_y,E,n)` (IHSG
    cancels), for n = 3, 5, 21.
  - Rank by `|s_H|` with `H ∈ {3, 5, 21 (default)}`.
  - Filters: both, A ahead (`s_H > 0`), A behind; top 7 or all.
  - The comment (L653) says "ranked by |z| of the ratio"; the code ranks by |spread|.
- **Detail `fwdPMS`** (L1484-1490): the spread at 1, 3, 5, 10, 21, 63 sessions; |1M|.
- **GAP:** none. **Per-sector.**

### 5.5 `pmA`, `pmB` (L674-715): not drawn

These are dead code (the parent has `display:none` and `RENDER.pm` does not call them):

- **Sector × Sector:**
  - cell text = the n-session (3/5/10) return difference;
  - colour = **zOf**: `z = d5(a,b,E) / s`, where `d5 = ret_a(5) − ret_b(5)` and `s` = the **sample** sd of `d5` over
    the last 250 sessions (numerator not mean-centred). Lookback 255.
- **Pair detail:**
  - differences 3/5/10D, z, Corr 60D (high at ≥ 0.7);
  - **reversal** = the ratio A/B crossed its SMA20 within the last 5 sessions;
  - a 60-session ratio chart with its SMA20.

---

## 6. Breadth tab

The tab has one selection, `brSel()` = `TT.bhS`: "IHSG" (all stocks) or a sector (L748-749).

### 6.1 `brH`: Breadth vs Price (`brH()` L788-860; series `brSeries` L733-745)

- **Inputs:**
  - IHSG: `series.above_ema50` / `above_ema200` (real) and `series.index.IHSG` (price, right axis).
  - Sector: `series.sector[s]` plus `day.stocks.above_ema50/200` of its members, through the synthetic `brSeries`.
- **Lookback:** period `{63, 126 (default), 250, Custom}`; wheel-zoom and drag across all 300 sessions (minimum span
  20). Headline Δ = 5 sessions.
- **Formula:**
  - main line `bs(i)` = % above `MS ∈ {EMA50 (default), EMA200}`;
  - headline `bs(E)` and `bs(E) − bs(E−5)` (pp);
  - zones: ≥ 70 % green, ≤ 30 % red;
  - up to 4 comparison lines (other sectors or IHSG); IHSG price dashed on the right axis;
  - tooltip: `% above`, the price, and the price change since the start of the visible range.
- **FAKE for any sector (G4)** (`brSeries` L738-744):
  - `em` = EMA_n of the **sector index** (n = 50 / 200 / 20);
  - `z(i) = 0.85·z(i−1) + (rnd − .5)·6`, an LCG seeded from the sector name;
  - `raw(i) = clamp(2, 98, 0.55·(50 + mult·(C_s(i)/em(i) − 1)) + 0.45·market%above(i) + z(i))`, with mult =
    520 / 260 / 900 for EMA50 / EMA200 / EMA20;
  - pinned to today's real share: `out(i) = clamp(1, 99, raw(i) + (target − raw(E))·max(0, 1 − (E−i)/20))`, where
    target = % of members (size > 0) above EMA50 / EMA200 today.

  The IHSG "EMA20" line is the mean of the 11 fake sector EMA20 lines (L736).
- **Detail `fwdBRH`** (L1491-1497), the last 60 sessions: close, 1D %, % above, Δ 1D, Δ 5D (zone and divergence are
  computed, not shown). For a sector this inherits the fake series.
- **Real data needed:** **per-sector % of members above EMA50 and EMA200 per date**, ≤ 300 sessions. That is
  Feature 04 grouped by sector, the same count the publisher already does for the whole market (`BREADTH_SQL`) with
  a `GROUP BY` sector added. It is a server-side precompute: Feature 04 is 2.5 GB and per-stock EMA200 cannot be
  rebuilt from 300 closes (warm-up).
- **Per-sector history** (11 × 300 × 2), built from per-stock Feature 04 rows (≈ 860 × 300).

### 6.2 `brT`: Breadth Heatmap Table (`brT()` L876-901; extra columns `BTX`/`brXv` L903-904)

- **Inputs:** `day.stocks.{r1d, r5d, r1m, above_ema50, above_ema200, size}`, `meta.stocks.sector`; `brSeries` for Δ.
- **Lookback:** stocks, page date only. Δ EMA50 1W = 5 sessions of breadth history; the window's extra columns need
  3, 5 and 21.
- **Formula:** per sector, plus "IHSG (all)" = every row with size > 0, **the 7 "Other" stocks included** (833):
  - N = members with size > 0;
  - Up 1D, 1W, 1M = % of N with `r1d`, `r5d`, `r1m` > 0 (null counts as not up);
  - > EMA50, > EMA200 = % of N with the flag = 1 (null counts as below);
  - Δ EMA50 1W = `brSeries(s,'ema50')[E] − [E−5]`: **fake for a sector**, real for IHSG
    (`series.above_ema50`). Example IHSG: 19.33 − 12.69 = +6.6 pp;
  - colour centred on 50 %; Δ cells capped at 25 pp;
  - toggle "%" or "count/N"; every header sorts;
  - `tag()` (Distribution? when e200 > 65 and e50 < 45, Recovery when e200 < 45 and e50 > 60, Overbought when
    e50 ≥ 80, Oversold when e50 ≤ 20) is computed and **not displayed**.
- **Window-only extra columns (FAKE, G5):** Δ % above EMA20, EMA50, EMA200 over 3D, 1W, 1M (`brXv`), all from
  `brSeries`. "EMA20 breadth is illustrative" (L902). Feature 04 has `sma_20`, `ema_50`, `ema_200` and **no `ema_20`**.
- **Detail `fwdBRT`** (L1498-1504): % above EMA50 and EMA200 now, Δ 1W, Δ 1M, from `brSeries` (fake for sectors).
- **Per-stock, page date only**, plus per-sector breadth history for the Δ columns (G4/G5). Cost: 833 × 5 flags.

### 6.3 `brA`: Breadth by sector (`brA()` L718-729)

- **Inputs:** `day.stocks.{r5d, above_ema50, size}`, IHSG 5D. Page date only.
- **Formula:**
  - per sector, members (size > 0) with `r5d` not null;
  - the measure is one of: **% above EMA50** (default), **% with r5d > IHSG 5D**, **% with r5d > 0**;
  - dot plot 0-100 %, sorted descending; a green dot at ≥ 50 %.
  - Click = select the sector for the tab.
- **Detail `fwdBRA`** (L1505-1512): the members with their EMA50 and EMA200 flags (real) and **"vs EMA50" distance
  (FAKE, from `brDum`, G7)**, and `r1m`.
- **GAP:** card none; detail distance fake. **Per-stock, page date.**

### 6.4 `brN`: Advancers · Unchanged · Decliners (`brN()` L862-874)

- **Inputs:** `day.stocks.{r1d, r5d, r1m, size}`. Page date only.
- **Formula:**
  - per sector and "IHSG (all)" (Other included): counts of members (size > 0) with `v > 0` (up), `v < 0` (down),
    and `|v| < 1e-9` **or null** (unchanged), where `v` = `r1d` / `r5d` / `r1m` for 1D / 1W / 1M;
  - stacked bar of the shares; sorted by the up share.
  - This differs from `day.breadth`: the publisher drops the nulls (and covers all stocks without the size filter).
- **Detail `fwdBRN` (FAKE, G8)** (L1513-1524): Close = `round(50 + rnd^2.2·9000)` and Volume = `size / fake close`
  are invented; the Change is real.
  - The real close is in SX (`day.stocks.close`, unused).
  - A daily volume is not in SX (Feature 01 `volume`); `size` is a 20-day average of value, not volume.
- **Per-stock, page date.**

### 6.5 `brD`: Stock detail (`brD()` L763-787; dummy `brDum` L753-762)

- **Inputs:** `day.stocks.{above_ema50, above_ema200, size}`, `meta.stocks.{ticker,name,sector}`.
- **Formula:**
  - rows = members of the selection (IHSG = all 833);
  - Status = Above / Below the EMA chosen in `brH` (real flag; null = below);
  - filter All / Above / Below; sort by any column; a search box in the window;
  - subtitle "x of N above".
- **FAKE (G6)** (`brDum`, seeded by the stock index, signs matched to the real flags):
  - Distance from EMA20, EMA50, EMA200 (%): `d50 = ±(0.2 + rnd^1.4·12)`, `d200 = ±(0.3 + rnd^1.3·24)`;
    `a20 = rnd < (a50 ? .78 : .25)`, `d20 = ±(0.1 + rnd^1.5·7)`;
  - **Days** in status (EMA50: `1 + ⌊rnd^1.6·75⌋`, EMA200: `1 + ⌊rnd^1.6·180⌋`) and **Since** = `E − days + 1`.
- **Real data needed:** per stock:
  - `close / ema_50 − 1`, `close / ema_200 − 1` (Feature 04 `close`, `ema_50`, `ema_200` at E);
  - the 20-period one: `sma_20` exists, EMA20 does not, so a decision is needed (G5);
  - days in status = the run length of `close > ema` back from E, which needs per-stock Feature 04 history (cap it,
    e.g. at 300).

  A server-side precompute (one row per stock).
- **Per-stock.** Cost: up to 833 DOM rows (the DOM is the cost, not the arithmetic).

### 6.6 `brM`, `brC`, `brB`: not drawn (L905-953)

- **`brM` % Above Moving Average:**
  - per sector, the shares "> EMA20", "> EMA50", "> EMA200", with a liquidity floor `size ≥ 0 / 1e9 / 1e10` IDR
    (336 and 116 stocks pass the last two);
  - **"> EMA20" is actually `r1m > 0`** (L909), a mislabelled proxy (G14).
- **`brC` Quality of the move:**
  - contribution `c_i = size_i / Σsize · r5d_i`;
  - top-3 share = `Σ_top3 |c| / Σ |c|` (amber ≥ 60 %);
  - "Divergence" is not recorded (needs sector breadth Δ5D, G4).
- **`brB` Breadth history:**
  - `series.above_ema50` over the last 250 sessions, all stocks;
  - **thrust** = within 10 sessions from < 30 % (the window's low) to > 60 %; overlapping episodes are merged;
  - "Sector history not recorded" (G4).

---

## 7. Card → inputs → lookback → GAP

| Card | SX inputs | Longest lookback (sessions before E) | GAP |
|---|---|---|---|
| KPI row | `series.index.IHSG`, `series.sector` | 30 (sparkline); RRG warm-up 25 | no (hard-coded "11") |
| Pills | `day.date`, `meta.broker_through` | 0 | no |
| Date button | `day.date` | 0 | **yes**: earlier dates need `meta.dates` + day files + moving E (G10) |
| Open in Screener | none | 0 | **yes**: no destination (G11) |
| CSV export | none (hidden legacy button) | 0 | **yes**: not implemented (G12) |
| snCard (hidden) | `series.sector`, IHSG | 63 | no |
| rcCard | `series.sector`, IHSG, `dates` | 63 default; YTD 210; Custom ≤ 299 | no (Custom base and cap differ from the Overview, I3) |
| mmCard | `series.sector`, IHSG | 210 (YTD axis) | no |
| hxCard | `series.sector`, IHSG | 250 (1Y) | no (1Y = 250 vs Overview 252, I2) |
| mkCard | `day.stocks.{i,size,r5d}`, `meta.stocks`, `ind`, IHSG, `series.sector` | stocks 0 (5D in file); header 210 | partly: `ind` not published (G3a); value-weighted (G3b); 5D only |
| Legacy `#spb`/`#stc` (hidden) | `series.sector`; `day.stocks` incl. `fnet_5d` | 250 | YTD bug (I5); CSV no-op |
| rsA | `series.sector`, IHSG | 10 (detail 21) | no |
| rsB | `series.sector`, IHSG | 31 (Custom ≤ 299) | no |
| rsW | `series.sector`, IHSG | 45 (8W); 135 (26W Custom) | no |
| rsD | `series.sector`, IHSG, `day.stocks.{r5d,r1m,size,above_ema50}`, `ind` | 210 (YTD); 41 (Δ4W); RRG 25 | **yes**: industry 3M/YTD/vs 3M/Δ4W/RRG random; industry rows never shown (G2) |
| rsL | `series.sector[s]`, `day.stocks.size` | 63 default; YTD 210; Custom ≤ 299 | **yes**: stock price paths synthetic (G1) |
| rsC | `series.sector`, IHSG | 15 (streak can scan all) | no |
| rotA | `series.sector`, IHSG, `dates` | ≈ 280 (52 weeks + 25 warm-up); 12W tail +60 | no (draft RRG formula, not JdK) |
| rotD | RRG series | K − 20 | no |
| rotB | RRG series | up to the whole series (last change) | no |
| rotC | `day.stocks.{r1m,r5d,size}`, IHSG or sector index | 21 | no fake; 20 vs 21 mismatch (I1) |
| pmM | `series.sector` | 121 (Corr 120D); 63 Spread; Custom ≤ 299 | no |
| pmR | `series.sector[A,B]` | 300 (1Y + MA50) | no |
| pmT | `series.sector`, `series.index.{IHSG,LQ45}` | 251; Δβ 2W + 1 (241 for 120D) | card no; **detail stock β/corr fake (G9)** |
| pmS | `series.sector`, IHSG | 21 (detail 63) | no |
| pmA/pmB (dead) | `series.sector` | 255 | n/a |
| brH | `series.above_ema50/200`, IHSG; sectors: `series.sector` + `day.stocks` flags | 300 (zoom); 250 (1Y) | **yes**: sector breadth history synthetic (G4) |
| brT | `day.stocks.{r1d,r5d,r1m,above_ema50/200,size}`; `brSeries` | 5 (Δ1W); window 21 | **yes**: sector Δ EMA50 fake; window Δ columns fake; EMA20 illustrative (G4, G5) |
| brA | `day.stocks.{r5d,above_ema50,size}`, IHSG | 5 | card no; **detail distance fake (G7)** |
| brN | `day.stocks.{r1d,r5d,r1m,size}` | 0 | card no; **detail close and volume fake (G8)** |
| brD | `day.stocks.{above_ema50/200,size}`, `meta.stocks` | 0 (status) | **yes**: EMA distances, days and since fake (G6) |
| brM/brC/brB (dead) | `day.stocks`; `series.above_ema50` | 250 (brB) | "> EMA20" = r1m > 0 (G14); divergence not recorded |

### GAP list

| Id | What is faked or missing | Where | Real data needed |
|---|---|---|---|
| G1 | stock cumulative price paths | `rsL` L307-311 | per-stock daily closes ≤ 300 sessions (in production `overview-stocks`) |
| G2 | industry 3M, YTD, vs IHSG 3M, RS rating 4W ago (Δ4W), RRG quadrant (random); industry rows never displayed | `rsD` L280-281 | industry price series: a chain-linked index from member closes (≥ 210 sessions), or member closes at E−20/21/41/63 and the YTD base; for the RRG ≥ 25 sessions of the industry ratio |
| G3a | industry label | `ind` | not in the publisher files: add `IDX_Stock_Universe."Industry"` to `overview-meta` |
| G3b | industry and treemap weights = 20-day trading value (`size`), a proxy for weight | `rsD`, `mkCard`, `fwdMK` | decide: equal-weight, value-weight or market cap (shares outstanding not loaded yet, `OVERVIEW_FORMULAS.md` §7) |
| G4 | per-sector % above EMA50/EMA200 history | `brSeries` L733-745 → `brH`, `brT` Δ, `fwdBRH`, `fwdBRT`; `brC`/`brB` | Feature 04 counts per sector per date (≤ 300), server-side |
| G5 | "EMA20" breadth and Δ columns (3D/1W/1M) | `brT` window `BTX`, `brSeries('ema20')` | Feature 04 has no `ema_20` (only `sma_20`): choose SMA20 or add an EMA20 |
| G6 | stock distance from EMA20/50/200; days in status; since | `brDum` L753-762 → `brD` | Feature 04 `close`, `ema_50`, `ema_200` (+ the 20-period one) at E; run length of `close > ema` per stock |
| G7 | "vs EMA50" distance in the brA detail | `fwdBRA` L1508 | as G6 |
| G8 | stock close and volume in the brN detail | `fwdBRN` L1518 | close is in SX (`day.stocks.close`, unused); volume from Feature 01 `volume` |
| G9 | stock β and correlation | `fwdPMT` L1478-1479 | per-stock daily closes over W ≤ 250 (`overview-stocks`), or precomputed per window |
| G10 | earlier dates | date button L1236 | `meta.dates` + day file per date; E re-anchored |
| G11 | Open in Screener | L1243-1245 | a Screener route with a sector filter |
| G12 | CSV export | `#csv` (hidden, no handler) | none (export the detail table rows) |
| G13 | divergence (BR-05) | `brC` (dead) | sector breadth Δ5D (G4) |
| G14 | "> EMA20" = share with `r1m > 0` | `brM` L909 (dead) | as G5 |

### Inconsistencies to settle before a precompute

| Id | Issue |
|---|---|
| I1 | "1M" is **21 sessions** for every index return in this page, but **20 observations** for stocks (`r1m` = Feature 01 `return_20d_pct`), and 20 broker dates for the Overview's flows. `rotC` x-axis and the `rsD` industry 1M mix them. `rsW` sorts by 20. |
| I2 | "1Y" is **250** sessions here (heatmap, `pmR`, `pmT`, `brH`) but **252** in the Overview (`model.ts` `YEAR`). |
| I3 | A Custom range return is based on the first session in the range (its own move is excluded). The Overview bases it on the session before and caps the range at 365 days. |
| I4 | Breadth denominators: the page's per-sector shares divide by members with size > 0 and count a null EMA flag as "below"; the market series divides by the stocks that have an EMA. "IHSG (all)" rows in `brT`/`brN` include the 7 "Other" stocks. `brN` counts a null return as "unchanged"; `day.breadth` drops it. |
| I5 | Legacy Sector Performance: the YTD button falls back to 60 sessions (hidden card). |
| I6 | The `pmS` comment says "ranked by z"; the code ranks by |spread|. |
| I7 | Stock foreign flows (`fnet_*`) are at the broker date (9 Nov), 6 sessions behind the prices. Only the hidden legacy table uses them. |

### SX fields the page never reads

`series.breadth_n`, `series.flow.*`, `meta.sectors`, `meta.dates`, `meta.size_basis`, `meta.prices_through`,
`meta.periods`, `day.prior_date`, `day.size_basis`, `day.index`, `day.volatility`, `day.breadth`, `day.market`,
`day.stocks.close`, `day.stocks.fnet_1d`, `fnet_1m`, `fnet_3m` (`fnet_5d` only in the hidden legacy card),
`day.intraday`. The page computes no sector-level foreign flow.

---

## 8. Derived measures a server-side precompute would produce

Notation: s = one of the 11 sectors (or IHSG / LQ45 where stated), t = a session index, `C` = the index close,
"members" = the common stocks of sector s with a row on t (the prototype also requires `size > 0`). All horizons are
in market sessions. "Needs" = the sessions before t that must exist.

### 8.1 Sector-index measures (from the index closes only)

| # | Measure | Exact definition | Horizons | Needed at | Needs |
|---|---|---|---|---|---|
| D1 | Sector return | `R_s(n,t) = (C_s(t)/C_s(t−n) − 1)·100`; YTD: base = last session of the previous year; Custom `[i0,i1]`: `C(i1)/C(i0) − 1` | n = 1, 3, 5, 10, 20, 21, 63, 126, 250; YTD | t = E (all n); also t = E−5k (n = 5, k < 26) and t = E−20 (n = 21) | 250 (or 210 YTD) |
| D2 | Excess return vs IHSG | `X_s(n,t) = R_s(n,t) − R_M(n,t)` (pp) | as D1 | as D1, plus t = P0 (n ≤ 10, P0 = E−5/10/21/Custom) | 250 |
| D3 | Sector rank | rank 1-11 of `X_s(n,t)`, descending | n = 3, 5, 10 | t = E, E−5, E−10, E−15, E−20, E−21, P0 | 31 |
| D4 | RS rating | `round(1 + 98·(N−1−k)/(N−1))`, k = position of `X_s(21,t)` descending, N = 11; Δ4W = rating(E) − rating(E−20) | 21 | E, E−20 | 41 |
| D5 | Momentum tag | `g = X_s(5,E) − X_s(21,E)·5/21`; Gaining > 0.5, Fading < −0.5 | 5, 21 | E | 21 |
| D6 | Acceleration | `X_s(3,E)/3 − X_s(10,E)/10` (pp/session) | 3, 10 | E | 10 |
| D7 | Outperformance streak | count of consecutive t ≤ E with `C_s(t)/C_s(t−1) > C_M(t)/C_M(t−1)` | daily | E | ≤ all |
| D8 | Cumulative path | `P_s(i;b) = (C_s(i)/C_s(b) − 1)·100`, i = b..e | b = E−21, E−63, YTD, Custom (legacy E−20/60/250) | E | ≤ 299 |
| D9 | Period statistics | over `[b,e]`: return, vs IHSG, max drawdown `min_i(C(i)/max C(b..i) − 1)`, best day, worst day, % up days | same periods | E | ≤ 299 |
| D10 | Weekly excess grid | `X_s(5, E − 5k)` | k = 0..25 | E | 135 |
| D11 | RS-Ratio, RS-Momentum | `r = C_s/C_M`; `RSR = 100·r/SMA20(r)`; `MOM = 100·RSR(t)/RSR(t−5)`; quadrant by RSR ≥ 100, MOM ≥ 100 | daily series; weekly samples `t = E − 5j` (j ≤ 51) | t ∈ [E−255−60, E] | ≈ 300 |
| D12 | RRG motion | `ΔRSR, ΔMOM` over LB ∈ {5, 10, 20}; direction `atan2(ΔMOM, ΔRSR)` in 0-360°; speed `hypot`; `dm = MOM(E) − MOM(E−3)`; quadrant at E−5/10/21; last daily quadrant change; weeks in quadrant (weekly runs, 52 weeks) | | K (default E) | ≈ 300 |
| D13 | Pair spread | `S_ab(n) = R_a(n) − R_b(n)` (= `X_a − X_b`) | n = 1, 3, 5, 10, 21, 63, Custom | E | 63 |
| D14 | Pair correlation | Pearson ρ of daily simple returns over the last W | W = 20, 60, 120 | E | 121 |
| D15 | Pair ratio band | `Q = C_a/C_b`; `μ = SMA_M(Q)`; `σ` = population sd over M; bands μ ± 2σ; z = (Q − μ)/σ; %B; rebased at `i0 = max(M, E−P)` | M = 20, 50; P = 63, 126, 250 | each i in [i0, E] | P + M ≤ 300 |
| D16 | Pair ratio z (default pair) | `(Q(E) − mean_60(Q))/sd_60(Q)` (population) | 60 | E | 60 |
| D17 | Beta, correlation, alpha | daily returns over `(E−W, E]`; β = ρ·σ_s/σ_b (population sd); alpha = `R_s − β·R_b`; Δβ = β(E) − β over `(E−2W, E−W]` | W = 20, 60, 120, 250; benchmark IHSG or LQ45 | E | W + 1; Δβ 2W + 1 |
| D18 | (dead) 5D-difference z, ratio reversal | `d5_E / sample sd(d5 over 250)`; ratio crossed SMA20 within 5 sessions | | E | 255 |

### 8.2 Measures from per-stock rows aggregated to a sector or industry

| # | Measure | Exact definition | Needed at | Needs |
|---|---|---|---|---|
| D19 | % above EMA50 / EMA200 per sector | `#(close > ema_50)/N` (decide N: stocks with ema vs members with size > 0) | **every session**, ≤ 300 (brH line, Δ1D/Δ5D/Δ21, thrust) | Feature 04 per stock per date (**server-side**) |
| D20 | % above the 20-period average per sector | as D19 on `sma_20` (or a new EMA20) | as D19 | as D19 |
| D21 | Up share and A/U/D per sector | counts of members with `r1d`, `r5d`, `r1m` > 0, < 0, = 0 (decide whether null is dropped or unchanged) | E | day file |
| D22 | % with `r5d` > IHSG 5D; % with `r5d` > 0 | members with r5d not null | E | day file |
| D23 | Industry (`ind`) aggregates now | n; value share `Σsize/Σsize_sector`; 1W/1M = Σ size·r / Σ size (or the chosen weights, G3b); excess vs IHSG 5/21; Up 5D share; leader | E | day file |
| D24 | Industry history measures | an industry index `I_g(t)` = chain-linked weighted member return; then 3M, YTD, vs IHSG 3M, RS rating among all industries at E and E−20, RS-Ratio/Momentum and quadrant | E, E−20 (+ series for the RRG) | per-stock closes ≤ 300 (`overview-stocks`) |
| D25 | Treemap group excess | `Σ size·(r5d − R_M(5)) / Σ size` per industry | E | day file |
| D26 | Top-3 contribution share (dead brC) | `c_i = size_i/Σsize·r5d_i`; `Σ top3 |c| / Σ |c|` | E | day file |

### 8.3 Per-stock measures

| # | Measure | Exact definition | Needs |
|---|---|---|---|
| D27 | Stock vs benchmark | `x = r1m − R_b(21)` (or 20, I1), `y = r5d − R_b(5)`, b = IHSG or sector index; quadrant | day file |
| D28 | Distance from EMAs | `(close/ema_50 − 1)·100`, `(close/ema_200 − 1)·100`, 20-period likewise | Feature 04 at E |
| D29 | Days in status | run length of `close > ema_n` back from E (cap e.g. 300); since = date(E − days + 1) | Feature 04 history per stock |
| D30 | Stock cumulative path | `(close_i/close_b − 1)·100`, top 10 by size per sector | per-stock closes ≤ 300 |
| D31 | Stock β, correlation | as D17 on the stock's daily returns | per-stock closes W + 1 ≤ 251 |
| D32 | Stock close, volume | Feature 01 `close` (in SX), `volume` (not in SX) | day file |

---

## 9. Cost summary

- **Arithmetic is small everywhere.** The heaviest loops are well under 1 M operations:
  - RRG: 11 × 300 × 20;
  - correlation grid: 110 × 120;
  - Pair Ratio bands: 250 × 50;
  - market-wide stock scans: 833 rows × a few filters, repeated per card.

  The browser can compute everything from the published files. The visible cost is the DOM (`brD`'s 833 rows) and
  the repeated `members()` scans, not the maths.
- **What must move server-side is the data, not the compute:**
  - per-sector breadth history (G4, D19-D20): Feature 04 is 2.5 GB, and EMA200 cannot be rebuilt from 300 closes;
  - per-stock EMA distances and days in status (G6, D28-D29), for the same reason;
  - industry index series (G2, D24): 862 stocks × 300 closes. Computable in the browser from `overview-stocks`
    (±1 MB), but a precomputed 58 × 300 series is smaller and keeps one weighting rule;
  - stock β and correlation (G9, D31): 862 × 250 returns per window. Feasible in the browser from `overview-stocks`;
    precompute it if several windows are offered.
- **Optional, for consistency with other EDGE surfaces:** precompute D11-D12 (RRG), D4 (RS rating) and D1-D2 at the
  fixed horizons, so the page, the Screener and the AI read one definition.

---

## 10. The subsector field `ind`

- **What it is:** a map `ticker → IDX-IC Industry` (the third IDX-IC level: Sector > Sub-sector > **Industry** >
  Sub-industry). Examples:
  - "Coal" is the industry under the sub-sector "Oil, Gas & Coal";
  - "Banks";
  - "Real Estate Management & Development".

  The counts match `IDX_Stock_Universe."Industry"` (`DATABASE_CHANGELOG.md`: Metals & Minerals 32, Coal 41, Oil, Gas &
  Coal Support 20), so the source is that column (also `Feature_01_Stock_Daily.industry`). The publisher does **not**
  write it (`overview.py` `STOCKS_SQL` reads Ticker, Company Name and Sector only). The page labels it "subsector".
- **Sample (10):** AADI Coal · AALI Agricultural Food Products · ABDA Insurance · ABMM Coal · ACES Specialty Retail ·
  ACRO Apparel & Luxury Goods · ACST Building Construction · ADES Beverages · ADHI Building Construction ·
  ADMF Consumer Financing.
- **Size:**
  - 841 tickers = every stock of `meta.stocks` except the 21 "Other" (Undefined) ones;
  - **58 distinct values**; every value belongs to exactly one sector;
  - the 7 "Other" stocks of the day file fall back to "Unclassified".
- **Industries per sector** (stocks on the page date in brackets):

  | Sector | Industries |
  |---|---|
  | Basic Materials (5) | Chemicals 27, Containers & Packaging 17, Metals & Minerals 32, Construction Materials 9, Forest & Paper 7 |
  | Consumer Cyclicals (12) | Tourism & Recreation 44, Specialty Retail 23, Apparel & Luxury Goods 15, Automotive Components 15, Household Goods 13, Media 11, Entertainment & Movie Production 5, Education & Support Services 3, Department Stores 3, Consumer Goods Distributors 2, Consumer Electronics 1, Sports Equipment & Hobbies Goods 1 |
  | Consumer Non-Cyclicals (6) | Agricultural Food Products 51, Processed Foods 31, Food & Staples Retailing 14, Personal Care Products 11, Beverages 9, Tobacco 4 |
  | Energy (4) | Coal 40, Oil, Gas & Coal Support 20, Oil & Gas 15, Alternative Energy Equipment 1 |
  | Financials (5) | Banks 47, Holding & Investment Companies 17, Insurance 16, Consumer Financing 13, Investment Services 6 |
  | Healthcare (3) | Healthcare Providers 16, Pharmaceuticals 13, Healthcare Equipment & Supplies 10 |
  | Industrials (7) | Machinery 14, Building Products & Fixtures 12, Commercial Services 11, Electrical Equipment 7, Professional Services 5, Multi-sector Holdings 4, Diversified Industrial Trading 3 |
  | Infrastructures (6) | Building Construction 20, Wireless Telecommunication Services 10, Electric Utilities 8, Telecommunication Services 8, Transportation Infrastructure Operators 7, Gas Utilities 1 |
  | Properties & Real Estate (1) | Real Estate Management & Development 77 |
  | Technology (6) | Internet Applications & Services 19, IT Services & Consulting 7, Computer Hardware 5, Software 5, Electronic Equipment, Instruments & Components 3, Networking Equipment 2 |
  | Transportation & Logistic (3) | Logistics & Deliveries 25, Passenger Ground Transportation 9, Airlines 2 |

- **How the page uses it** (`ind(t)` L271 and `ovxInd` L1166, both `SX.ind[t] || 'Unclassified'`):
  1. **Market map** (`mkCard`): the treemap groups. Area = Σ size; label = the size-weighted 5D excess; 10 largest
     stocks per group; the window table per industry (`fwdMK`).
  2. **Sector Drill-down** (`rsD`): the industry rows, with size-weighted 1W/1M, an RS rating among all 58, and the
     random 3M/YTD/Δ4W/RRG. These rows are never displayed (3.4).
  3. **Detail windows:** the "Subsector" column of the stock tables (`fwStocks` L1354 → `fwdRSD`, `fwdRSL`, `fwdROTC`,
     `fwdPMT`) and the per-industry breadth table `fwdBRD` (defined, not shown; its distances and days are `brDum`
     fakes).
- **Caveats:**
  - 1-stock industries (Consumer Electronics, Sports Equipment, Alternative Energy Equipment, Gas Utilities) make
    their "industry return" a single stock's.
  - Properties has one industry equal to the sector.
  - The classification is current, not point-in-time (`Feature_01_Stock_Daily.industry` says so). Industry history
    built from today's membership has survivorship and reclassification bias.
