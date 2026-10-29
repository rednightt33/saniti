# EDGE Screener audit: prototype UI behaviour (html_ui)

**Scope.** I read the prototype markup (lines 530-550) and the app script (lines 559-1717; line 557, the vendored library, was skipped), plus CSS only where it explains a control. The data, catalog and preset section (lines 563-1115) was run once inside an isolated Node `vm` context with no DOM and no network, to list the catalog exactly. The script is `scratchpad/audit/html_ui/scripts/extract_catalog.js` and its output is `catalog.json`.

I compared the prototype with the EDGE front end at repository HEAD `3db84aec`: `apps/edge-bff/app/main.py`, `static/index.html`, `static/edge-labels.js`, `backtest/` and `terminal/`. I also ran read-only pgweb queries for the universe columns.

Nothing was written inside `/home/user/saniti`; `git status` is clean. Scratch files are in `/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/audit/html_ui/`:
- `catalog.json`: the full catalog, the presets and the coverage of the Send-to-Backtest mapping.
- `prototype_line_map.tsv`: each identifier and its line number.
- `universe_industries.txt`: the live IDX-IC sectors and industries.
- `scripts/extract_catalog.js`

Labels: FACT means seen in code, data or a measurement now, with a citation. INFERENCE means reasoned from facts. PROPOSED means a recommendation. UNKNOWN means not determinable read-only.

---

## 1. Headline findings

1. **The prototype is one standalone vanilla-JS page with no network calls.** All data is synthetic and built in the browser: 94 tickers, 400 sessions to 2026-10-23, a synthetic IHSG, fundamentals and broker nets (FACT: lines 569-735, `catalog.json` N=400, tickers=94).
   - Every screen is evaluated in the browser over every ticker on every refresh (FACT: `refresh()` 1698-1699 calls `compute()` 1178).
   - At boot it also evaluates all 26 presets to show their match counts (FACT: `libCounts` 1187, called at boot 1713).
2. **The prototype's own top bar is `hidden`.** This hides the global ticker search, the ⌘K shortcut target, the theme toggle and the Analytics / Watchlist / Screener nav (FACT: `<header class="top" hidden>` 531 with CSS `[hidden]{display:none!important}` 106). The page was drawn to sit under a host top bar (INFERENCE). EDGE's shell bar has a "Search markets — coming soon" button and its own ⌘K (FACT: `static/index.html` Shell, about lines 10637-10660).
3. **The "screen performance history (Portfolio123-style)" is not implemented.** The code under that comment (1575-1588) only draws the **selected stock vs IHSG**, both rebased to 100, over 1M/3M/6M/1Y (21/63/126/250 sessions) in an inline SVG (FACT).
   - There is no rebalancing, no holding rule, no historical universe and no screen-level aggregation (FACT: no such code; `grep` finds no "rebal", and "Portfolio" appears only in that comment and the Send dialog).
4. **The catalog has 115 entries.** These are the 53 registry indicators (`x_*`, I01-I53), 17 older "Technical" entries, 13 "Flow" entries and 32 "Fundamental" entries (FACT: `catalog.json`).
   - **All 26 presets use only the older keys, never an `x_*` key** (FACT: `presetCondKeys`).
   - Ten indicators exist twice: RSI, Stochastic, MACD, ADX, Bollinger, ATR, Supertrend, MFI, CMF and OBV (FACT: key lists).
5. **Universe filters need data the market DB does not hold.** These are index membership (LQ45/IDX30/IDX80/ISSI), listing board, special notation / FCA, free float and market cap (FACT: no such column in any schema; `market_board` is the trading board {Regular, Nego, Tunai}, read from `pg_stats`).
   - Sector and industry exist in `IDX_Stock_Universe` (844 stocks plus 1 index) and in the backtest catalog groupings (FACT).
6. **Watchlist, saved screens, "My metrics" and theme live only in browser `localStorage`.** The keys are `edge-watchlist`, `edge-screens`, `edge-metrics` and `edge-scr-theme` (FACT: 1136, 1150, 1515, 1644-1653, 1711). EDGE has no Watchlist page and no server table for these (FACT: the shell nav is Monitor, Terminal, Backtest; the `edge_bff` schema per the lead).
7. **"Send to Backtest" targets a file that does not exist in EDGE**, `backtest.html#import=<base64 JSON>` (FACT: 1680-1686). The EDGE Backtest page reads no import (FACT: no `location.*` or `hash` use in `backtest/src`).
   - The payload uses the Backtest page's own old card format (type and op codes match `core/catalog.ts` LEGACY), not `BacktestRequest`.
   - It maps only 13 older keys and **none of the 53 `x_*` indicators** (FACT: 31 mappable (key, op) pairs in `catalog.json`).
   - It can carry far more tickers than the Backtest limit of 12 (FACT: `engine.ts:151 MAX_PORTFOLIO_TICKERS = 12`).
8. **The prototype's inline scripts cannot run under the CSP that EDGE gives its iframe apps.** The Terminal/Backtest CSP has `script-src 'self'`, no `'unsafe-inline'` (FACT: `main.py:39-48`). The prototype also embeds a 197 KB inline copy of Lightweight Charts 5.2.1, the same version Terminal and Backtest import from npm (FACT: both `package.json` pin `lightweight-charts: 5.2.1`).
9. **Several prototype behaviours disagree with each other or do needless work** (FACT, details in section 3.15):
   - Near-miss rules differ between the table and the detail panel.
   - "Clear all" leaves two default chips.
   - Two "clear liquidity" paths give different results.
   - The per-condition pass count is computed but never shown.
   - Pagination resets on every edit.
   - The rows of the table cannot be reached with the keyboard.

---

## 2. Page structure and state model (FACT)

**Markup (530-550).** The page holds:
- `header.top[hidden]`
- `main.page` with: `#pageHead`, `#pageActs`, card `#cardU` (universe), card `#cardC` (screen builder), `#bulk`, card `#cardR` (results: `#resMeta`, `#tq` search, `#resTools`, `#resPane`)
- `aside#preview` (detail panel `#dtb` plus actions `#dCopy` / `#dSend`)
- Floating hosts `#pop`, `#drawerHost`, `#menu`, `#overlay` (dialogs) and `#toast`

**State `S` (1154)** holds:
- `name`, `source` (`p:<preset>` / `s:<saved>` / null), `dirty`, `universe`, `conds[]`
- `open` (cards in Custom mode), `logic` (`all|any|n`), `atLeast`, `nearMiss`, `sort {key, dir}`
- `sel` (selected tickers), `pick` (previewed ticker), `dtab` (`stock|method`), `theme`
- `pcat`, `pexp`, `pvView` (`chart|perf`), `perf` ('6M'), `q`, `page`, `perPage` (25)
- `preview`, `bOpen` (builder open), `pop`, `drawer`

**A condition (`mkCond` 1142)** is `{id, key, on, p:{param:value}, op, v, v2, n}`. When it was added from a My metric it also carries `{m, mName, mp}`.

**Universe default (`freshUniverse` 1141):** `{indexes:[], boards:[], sectors:[], sectorsEx:[], industries:[], capMin:'', capMax:'', advMin:1, priceMin:50, ffMin:0, exclNotation:true, fund:[]}`. By default the universe therefore requires ADV ≥ Rp 1 B (20-session mean of close × volume, `advOf` via `fixedCond('adv')`), close ≥ Rp 50 and no special notation.

---

## 3. Inventory of UI behaviour

### 3.1 Top bar (hidden in the prototype)

| Control | Behaviour (code) |
|---|---|
| Brand "EDGE" and nav: Analytics (disabled), Watchlist (disabled), Screener (on) | Static; the disabled buttons carry the title "Not part of this screener prototype" (532-533) |
| Global ticker search `#gq` | On input it shows up to 8 tickers whose symbol starts with the query or whose name contains it. Each has a tag: "Match" if in `R.matches`, else "Stock". Enter or click picks the first hit (`pickStock`, scrolls to the preview); Esc clears; a click elsewhere closes it (1632-1637). |
| ⌘K / Ctrl+K | Focuses `#gq` (1638). The header is hidden, so this has no visible effect (FACT/INFERENCE). |
| Theme toggle | Switches light/dark, stores `edge-scr-theme`, redraws the preview (1710-1712). CSS accepts `:root.dark` or `[data-theme=dark]` (84, 101). |
| Avatar "AR" | Static |

### 3.2 Page head (`renderHeader` 1225)

- **Header text:** "Market intelligence / Market Screener"; an inline screen-name input `#titleIn` (Enter blurs; change marks the screen dirty); a source pill ("Preset · <cat>", "My screen" or "Custom screen", plus " · edited"); and a data line "IDX equities (94 sample listings) · close <last date>".
- **Buttons:**
  - **Reset** returns to a fresh universe with no conditions and toasts.
  - **Save screen** reads "Save changes" when a saved screen is dirty.
  - **Export** opens a menu (`openMenu` 1240) with:
    - Export results (CSV)
    - Send to Backtest
    - Duplicate as new screen (in memory only: `S.source=null`, the name gets " (copy)")
    - Method & sources (`S.dtab='method'`)

### 3.3 Universe card (`renderUniverse` 1281)

**Quick filters** (`QF` 1258) are pills that each open a popover (`renderPop` 1296; focus goes to the first input; the Clear and Done buttons; a live "In universe X of N"):

| Pill | Popover content (`usec` 1265) | Shown as "on" when |
|---|---|---|
| Index | Chips LQ45 / IDX30 / IDX80 / ISSI with counts; none selected means all; multi-select is OR (`some`) | `indexes.length>0` |
| Sector | Sector chips cycle include → exclude → clear; the **Industry** checklist sits in the same popover | sectors or sectorsEx set |
| Market Cap | Min/Max inputs (IDR T) and buckets Mega ≥200, Big 50-200, Mid 10-50, Small 1-10, Micro <1 (`CAPB` 1257) | capMin or capMax set |
| Liquidity | Avg value ≥ Rp B, Price ≥ Rp, Free float ≥ % | any differs from the default |
| Board | Main / Development chips | `boards.length>0` |

**More filters drawer** (`renderDrawer` 1307, `role=dialog`) has sections Index, Board, Liquidity & price, Sector, Market cap, Industry, **Metric filters** and Special notation, plus a footer with Reset universe, the count and Done. A click on the backdrop closes it.
- **Metric filters** are universe-level conditions with operators `>`, `<` and between. The metric list is 8 Technical, 10 Flow and 32 Fundamental entries, and **excludes the 53 registry indicators** because only groups Technical/Flow/Fundamental are offered and entries with custom ops are left out (FACT: 1274; `catalog.json metricFilterOpts`).
- "Add metric filter" defaults to **ROE > 10**, a fundamental (FACT: `onClick` `addfund`).
- Special notation is a checkbox "Exclude special-notation / FCA stocks"; its note says the filter is wired for the live feed (1275).

**Active filters chip bar** (`scopeChips` 1243): Index, Board, Sector or Excluding, Industry, Market cap, Avg value ≥, Price ≥, Free float ≥, one "Filter" chip per metric filter, and the fixed chip "Excludes special notation", which has no remove button. "Clear all" appears when removable chips exist. "In universe X of 94" is shown.

**Universe evaluation** (`inUniverse` 1160), applied in this order: index (OR), board, sector include, sector exclude, industry, cap min/max, last close ≥ priceMin, ADV20 ≥ advMin, free float, notation, then each metric filter through `evalCond`.

### 3.4 Presets (`presetsHtml` 1206)

- **Category tabs** (`role=tab`): All, Bandar(mology), Technical, Fundamental, Combined, and "My screens" with a count.
- **Chips** show the name and a badge with today's match count (title "Stocks that match today"). The tooltip is the preset's `why`.
- **Overflow:** chips sit on one clamped row with an expand button; the active chip moves to the front (`fitPresets` 1217).
- **Clicking a preset** loads its universe, conditions, logic and sort (`openSource` 1197). Clicking the active preset again clears the conditions but keeps the universe. When a preset is active, a "why" line is shown.
- **26 presets** (FACT, `catalog.json`):
  - Bandarmology (6): bigacc, fstreak, silent, freq, bavg, follow
  - Technical (9): minervini (universe advMin 5), brk52, oversold, golden, macddiv, rebound, squeeze, stflip, ichi
  - Fundamental (8): graham, piotroski, magic (capMin 5, exclude Financials), quality, dividend, garp, deep, bank (industry Banks)
  - Combined (3): canslim, qflow, vacc
  - Seven set a default sort on the first or second condition column.
- **My screens** come from `localStorage['edge-screens']`. Chip tooltip: "n conditions · saved <data date>". Each chip has Duplicate (adds `′` until the name is unique) and Delete; neither asks for confirmation.
- **Bandar thresholds** are reset to acc 6 / big 10 after the catalog is built (1082).

### 3.5 Screen builder (`renderConds` 1341)

- **Header:**
  - A collapse toggle with a summary: "n active conditions · m of U pass", or a hint.
  - **Match** control (only with ≥2 conditions): All / Any / At least, plus a number input (min 1, max = active count) and "of n active".
  - Clear (`clearconds`).
- **Adder (type-ahead)** `#adderQ` (`drawSuggest` 1365):
  - Searches the label, short name, description and key of all 115 entries plus a synonym table (golden/death/cross→ma_cross, asing/foreign→fnet, squeeze→bb, dividen→divYield, frekuensi→freq, magic, graham, piotroski, …).
  - "My metrics" matches are listed first. Results are grouped by `GORD` (Trend, Momentum, Volatility, Volume, PriceVolume, Technical, Flow, Fundamental) and each shows its default parameters.
  - A footer link reads "Browse all 115 indicators".
  - Keys: ↑/↓ move, Enter adds, Esc closes; "/" focuses the adder from anywhere outside a field (1407).
- **Empty state** has a quick-add rail: Browse all, RSI (x_rsi), Stochastic (x_stochastic), MACD (x_macd), Supertrend (x_supertrend), Bollinger (x_bollinger), Relative Volume (x_rvol), Bandar status (bandar), ROE (roe).
- **Indicator browser dialog** (`openBrowser` 1417, `drawBrowser` 1433) has three panes:
  - Groups with counts: All, My metrics (hidden when none), Trend, Momentum, Volatility, Volume, Price & volume, Technical, Flow & bandarmology, Fundamental.
  - A list (`role=listbox`, items `role=option`).
  - Details: group tag, registry id (I01..I53), name, description, "Default parameters" (or "Saved parameters"), "Conditions you can test" (the op labels), "Starts as" (the default `condText`), and "Add to screen".
  - Keys: ↑/↓ and Enter.
- **Condition card** (`condRow` 1318) is a horizontal strip, with a final "Add indicator" tile. Each card has:
  - A color dot, the name (tooltip = description) and an enable switch.
  - A remove button.
  - A summary (`condText` 1069).
  - **Default / Custom** segmented control, or "No parameters".
  - In Custom: a parameter grid. Number inputs use step and min, and each field shows "default X"; a changed field is highlighted. Select inputs offer options such as source or MA type.
  - "★ name" badge and "Save as My metric".
  - An **operator select** and value input(s) with unit (two for between).
  - **"within N sessions"** for events and level crosses.
- **Default/Custom rule:** a card is "Default" when every parameter string-equals the catalog default (`isDefP`/`isCustom` 1148-1149). Pressing Default resets the parameters (`resetParams` 1384). A parameter edit is ignored when it is empty or ≤ 0, and is rounded when step = 1 (`applyField` 1489).
- **My metrics** (`openSaveMetric` 1385): a name of at most 40 characters; saving under an existing name (case-insensitive) replaces it. Stored record: `{id:'m'+Date.now(36), name, key, p, op, v, v2, n, date:<data date>}` in `localStorage['edge-metrics']`. Linked cards are renamed or unlinked. Editing a parameter away from the saved set unlinks the card (`syncMetric`). Delete keeps the cards' settings.

### 3.6 Operators and evaluation semantics (`evalCond` 1055)

| Kind | Operators (labels) | Rule |
|---|---|---|
| Value | `gt` "greater than", `lt` "less than", `between` | Read on the **last bar** only. `>` and `<` are strict; between is inclusive and order-agnostic. A null or NaN value gives fail, "n/a", sort null. |
| Level cross | `xa` "crosses above", `xb` "crosses below" | `s[i-1] ≤ a < s[i]` (or the mirror) at any bar inside the last N sessions (`n`, min 1). Event bars from the last 130 sessions are kept for chart markers. |
| State (custom) | e.g. "Close above SMA", "In uptrend", "+DI above −DI", "Big Accumulation", "Above its 20-session average", "SMA rising (vs 5 sessions ago)" | Read on the last bar only; shows Yes/No |
| Event (custom) | e.g. "Golden cross", "Flipped to uptrend", "MACD crosses above signal", "Bullish divergence", "Squeeze", "OBV N-session high" | Passes if the event happened in the last N sessions; shows "today", "Nd ago" or "—"; sort key = 1000 − age |

Counts over (entry, op) pairs: 109 gt, 109 lt, 101 between, 43 xa, 38 xb, 68 custom-state and 65 custom-event; 96 distinct custom labels (FACT: `catalog.json`).
- **Overlays:** 12 registry entries can draw on the chart (x_sma, x_ema, x_wma, x_hma, x_kama, x_supertrend, x_donchian, x_keltner, x_psar, x_bollinger, x_vwma, x_vwap), plus the older `price_ma` line.
- **Last-value-only entries:** the 32 fundamentals and `rs_rank` have no series, so crosses and "within N" are impossible for them.
- **`rs_rank` is cross-sectional across all listings, not across the filtered universe** (FACT: 827).
- **Match logic** (`needOf` 1177): all = n, any = 1, at least = min(N, n). A **near miss** is a stock with `met = k−1`, shown only when there are >1 active conditions and k>1 (1180).

### 3.7 Results card (`renderResults` 1518)

- **Meta line:**
  - With conditions: "N matches" plus "meet all/any/at least k of n conditions · U in universe".
  - Without conditions: "U instruments · pick a preset".
  - Plus "filtered by q" when searching, "Near misses n", a near-miss switch, and "Show preview" when the preview is closed.
- **Search** `#tq` filters the current rows by symbol or company name (substring). Esc and an × button clear it.
- **Columns:**
  - Select checkbox, then a Watch button.
  - Sortable: **Symbol**, **Last**, **1D**, **Mkt cap**, **Avg value** (tooltip "Average daily traded value, 20 sessions").
  - Not sortable: Company, Sector (a colored tag).
  - **Met** (dots plus m/n) when there are conditions.
  - **One column per active condition.** The header shows the color dot, the short name and a parameter pill (highlighted when custom); the tooltip is `condText` plus "default/custom parameters: …" or "reported figure". The cell shows the value text; failing cells are greyed (`fail`).
  - Near rows get class `near` and a "near" pill.
- **Sort** (`sortedRows` 1507): default `match desc`. Clicking toggles the direction; a new key starts desc, except Symbol, which starts asc.
  - Matches always rank above near rows, and nulls sort last.
  - Ties go to market cap, descending.
  - The `match` sort value is `met + 100·match`.
- **Pagination:** 10/25/50/100 per page (default 25), "Showing a–b of n", "p / P", previous and next.
- **Selection:**
  - Row checkboxes, plus "select all", which selects only the visible page.
  - The selection survives paging and is cleared by `loadState`.
  - The bulk bar (`#bulk`) shows "N selected" with Add to Watchlist (add only), Send to Backtest, Export CSV (selected) and Clear selection.
- **Row click** picks the stock for the preview (`pickStock` 1574).
- **Empty states:**
  - No search hit: Clear search.
  - No match: "Show near misses (n)" and "Match at least n−1".
  - Empty universe: Reset universe.

### 3.8 Detail panel (`renderDetails` 1590)

- **Head:** a two-letter logo colored by a hash of the ticker, the ticker, a sector tag, the company name and a close button.
- **Quote:** last close, "±x% today" and a status pill: Outside universe, In universe, Match m/n, Near m/n or m/n. Then "industry · board · index memberships".
- **Chart / Performance** segmented control (`role=tab`).
- **Chart** (`drawChart` 1608, the vendored Lightweight Charts):
  - `createChart` with autoSize and `handleScroll:false`, `handleScale:false` (static), no grid, colors from CSS tokens.
  - A `CandlestickSeries` of the **last 130 sessions** (about 6 months).
  - A `LineSeries` per overlay output of each active condition (dashed for the 2nd and 3rd lines of a band), plus the MA line for older `price_ma`.
  - `createSeriesMarkers`: `arrowUp` below the bar on each event bar of each active condition, in the condition's color.
  - No volume series, no indicator panes and no IHSG on this chart.
  - Legend: the conditions that have events, else the text "Arrows mark event conditions … over 6 months".
- **Performance** (`perfCard` 1581): see 3.9.
- **"Why it passed / did not pass":** each active condition with its color dot, `condText`, value text and ✓ or ✕.
- **Fundamentals facts:** Market cap, P/E (n/m when loss-making), P/B, ROE, Div. yield, EPS growth, D/E ("bank" for banks), Piotroski.
- **Actions:**
  - **Copy** puts "TK Name · price" plus one "✓/✕ condText → value" line per condition on the clipboard (1629).
  - **Send to Backtest** sends the single picked ticker (1630).
- **Method & sources view** (`renderMethod` 1617):
  - Preset or screen context.
  - **Editable bandar thresholds**, Accumulation ≥ % and Big accumulation ≥ %. They are global: they recompute every bandar condition and the preset counts, and they are saved with screens.
  - A "How conditions work" text, the preset sources (Stockbit & Ajaib, Minervini, Greenblatt, Graham, Piotroski, O'Neil) and a sample-data note.
- **Empty panel:** "Pick a stock — click a result row or look up any ticker at the top". The search it refers to is hidden.
- **Responsive:** at ≤900 px the preview becomes a fixed right drawer of at most 380 px (CSS 526). `sizePreview` (1540) stretches it to the bottom of the window.

### 3.9 "Screen performance history" (requested precise reading)

**What the code does (FACT, 1575-1588):**
- For the **selected ticker only**: n ∈ {21, 63, 126, 250} sessions for 1M/3M/6M/1Y; default 6M; `from = N−1−n`.
- `a[i] = close[from+i] / close[from] × 100` and `b[i] = IHSG[from+i] / IHSG[from] × 100`, for i = 0..n.
- It draws the two lines in an inline SVG (`plines`: stock solid, IHSG grey dashed) and prints each total return and the difference in points ("Outperformed/Underperformed IHSG by x pts … Sample data.").

**What it does not have:**

| Portfolio123 element | In the prototype |
|---|---|
| Rebalancing frequency | none |
| Holding rule / number of holdings | none |
| Historical universe or point-in-time membership | none |
| Screen evaluated on past dates | none |
| Costs / slippage | none |
| Aggregation across the passing stocks | none |
| Benchmark | IHSG |

**Look-ahead and hindsight:**
- The per-stock series uses only past closes (FACT).
- But the stock is chosen by today's screen, so reading the chart as "how this screen performed" is hindsight and survivorship bias (INFERENCE).
- In the prototype, IHSG is synthetic: a cap-weighted mean of the 94 sample tickers using **today's** market caps as fixed weights (FACT: 710).
- Live, the published IHSG would be used. The Terminal already loads it (FACT: `terminal/src/data/live.ts:179-182`).
- Whether published closes are split- or dividend-adjusted is UNKNOWN to this area; it changes a rebased chart.

**A true screen backtest would need** (PROPOSED, needs a product decision):
- Point-in-time universe and membership; `IDX_Stock_Universe_History` has `valid_from` and `pit_valid_from` columns (FACT, information_schema).
- Conditions evaluated as of each rebalance date with data available then.
- A rebalance frequency, holding count and holding rule, costs, delisting handling and an IHSG benchmark.

That is a separate engine. The existing Backtest worker is limited to 12 picked stocks (FACT).

### 3.10 Dialogs, export and copy

- **Save screen** (`openSave` 1644):
  - The name field shows "A screen with this name exists — saving replaces it." when relevant.
  - It stores `{name, date: <data date, not wall clock>, state: snapshot()}` in `localStorage['edge-screens']`, keyed by **name**.
  - The `snapshot` (1643) holds universe, conditions (params, op, v, v2, n, on, metric link), logic, atLeast, sort, nearMiss and the bandar thresholds.
  - Saving sets source `s:<name>` and the tab to My screens.
- **CSV export** (`exportCsv` 1565): a client-side Blob named `<name-slug>-<last date>.csv`.
  - Columns: Symbol, Name, Sector, Industry, Last, 1D %, Market cap (IDR T), Avg value 20D (Rp B), Status (in universe / match / near miss), Met (m/n), then one column per active condition (header = `condText`, value = the cell text).
  - Rows: all visible rows (search and near-miss applied, every page). The "selected" export uses the universe order, not the sorted order (FACT).
- **Send to Backtest** (`openSend` 1674, `toBacktest` 1655):
  - Tickers come from the argument (the single pick), else the selection, else all matches. The mode is Single (with a ticker select) or Portfolio (disabled below 2).
  - A table marks each condition "Entry rule", "Screen only — it chose the tickers" (fundamentals) or "Screen only — not in the Backtest catalog".
  - Payload: `{v:1, source:'EDGE Screener', screen, date, mode, tickers:[{tk, px:last close, vol: sample stdev of last 120 daily returns}], conds:[{type, len/fast/slow/sig/k/smooth/broker, op, val}], logic, atLeast}`.
  - Actions: **Download JSON** (`backtest-import-<date>.json`), **Copy link** (absolute URL of `backtest.html#import=` with the base64 payload) and **Open in Backtest** (`<a target=_blank>`).
  - Mapping losses (FACT): `bandar` acc/bigacc/gt all become `top5 > 0` (the threshold and top-3 are lost); `topacc` ignores its `top` parameter; only SMA versions of `price_ma`/`ma_cross` map; `stoch` %D is dropped. No period, exit, costs or sizing is sent.
- **Copy actions:** the detail summary and the Backtest link only.
- **Toast:** `#toast` disappears after 2.2 s.

### 3.11 Browser storage

| Key | Content | Code |
|---|---|---|
| `edge-screens` | `[{name, date, state}]` | 1206, 1453-1455, 1644-1653 |
| `edge-metrics` | `[{id, name, key, p, op, v, v2, n, date}]` | 1150, 1385-1404 |
| `edge-watchlist` | `[ticker]`; read once at load, not synced across tabs | 1515-1516 |
| `edge-scr-theme` | 'light' / 'dark' | 1154, 1711 |

`store` (1136) wraps every access in try/catch.

### 3.12 Tooltips (FACT: 28 `title=` uses)

They appear on: preset chips (why); the count badge; disabled nav; condition names (description); the Default/Custom segment; the enable switch; remove, duplicate and delete buttons; result column headers (rule and parameters); Avg value; watch buttons (state); cap buckets (range); Browse; Close; previous and next; the builder sum. There is no custom tooltip component.

### 3.13 State transitions

**`refresh(level)` (1698)** always recomputes `R = compute()`, sets `page = 1`, then re-renders:

| Level | Re-render |
|---|---|
| `all` / `universe` | universe and builder cards |
| `universe-light` | quick filters, chips, counts, cards in place |
| `conds` | the builder |
| `conds-light` | cards in place, plus the universe count |

After that it always re-renders the header and results, and the details when the preview is open.

**Edits:** number inputs fire after a 350 ms debounce; `change` fires immediately; an identical value is ignored (1489-1503). `MEMO` caches every series by ticker, key and parameters and is never evicted (except bandar keys) (FACT: 776-777, 1203).

**Boot (1709-1717):** theme icon → `libCounts()` (all 26 presets plus saved screens) → `S.preview=false` → `loadState(empty)` → `refresh('all')`. Loading a preset with the preview open picks the first match (`repick` 1201).

### 3.14 Keyboard and accessibility (FACT)

**Shortcuts:**
- `/` focuses the adder.
- ⌘/Ctrl+K focuses the global search (hidden).
- Esc closes, in order: menu → dialog → popover → drawer → preview.
- In the adder and the browser: ↑/↓ and Enter.
- In the title input, Enter commits.
- In the results search, Esc clears.

**Present:**
- `role=dialog` (5), `role=tab`/`tablist`, a listbox/option in the browser.
- `aria-expanded`, `aria-pressed`, `aria-selected`, and aria-labels on icon buttons.
- `:focus-visible` outline.
- The popover returns focus to its pill; the drawer focuses its Close button.

**Missing:**
- `aria-modal`, a focus trap, and focus return after a dialog or drawer closes.
- `aria-live` on the toast.
- `aria-sort` on sortable headers.
- `tabindex` on result rows: a row click is the only way to open a preview from the table, so keyboard users cannot reach it.
- Arrow-key handling on the `role=tab` segments.
- Any text alternative for the canvas chart; the "Why it passed" list is a partial one.

### 3.15 Defects and dead code in the prototype (FACT)

- **Near-miss rules differ.** The table requires >1 condition and k>1 (1180). The detail panel's pill uses `met === k−1` with no guard (1599), so one failed condition, or a stock under "Any", shows "Near 0/n".
- **"Clear all" leaves two chips.** It calls `freshUniverse()`, which brings the ADV ≥ 1 and Price ≥ 50 chips back.
- **Two liquidity clears disagree.** The chip × sets advMin, priceMin and ffMin to 0, while the popover's Liquidity "Clear" restores the defaults 1/50/0 (`QCLEAR` 1295).
- **Per-condition pass count is computed but not rendered.** `condRow` evaluates every condition over the universe on each render (1318). `updateCondsLight` looks for `[data-pass]`, which no markup creates.
- **Unreachable code.** `paramUI` (1353) and its `data-pb/psum/hb/preset`, `data-pedit` and `act 'tqclear'` are never reached.
- **Parameters must be > 0** (1497). A registry parameter that may legitimately be 0 or negative could not be entered; whether such a parameter exists is for the indicator auditors.
- **Any edit returns the table to page 1** (`refresh`, 1699).

---

## 4. UI → backend requirement mapping

Classification codes:
- **S**: already supported (an existing endpoint or published data already delivers it to an EDGE page)
- **I**: requires integration (the data exists; it needs wiring or an endpoint)
- **C**: requires calculation (derived values must be computed server- or client-side)
- **N**: requires new data (not in the market DB)
- **D**: requires a product decision

| # | Control | What it does (code) | Data / API needed | Class |
|---|---|---|---|---|
| 1 | Index quick filter + drawer | LQ45/IDX30/IDX80/ISSI with counts, OR (1266, 1161) | Index membership per ticker (point-in-time for history); no column exists (FACT) | N, D (which indexes) |
| 2 | Sector include/exclude | 3-state chips (1269, 1471) | `IDX_Stock_Universe.Sector`; backtest `catalog.groupings` / `tickers[].groups` (contract.ts:320-336). Names match the prototype's 11 sectors (FACT) | S |
| 3 | Industry checklist | multi-select (1272) | `Industry` (59 IDX-IC values; several prototype names differ, e.g. "Telecommunication" vs "Telecommunication Services", see `universe_industries.txt`) | S (take the list from data) |
| 4 | Market cap min/max + buckets | `t.cap` (1167-1168, 1257) | Shares outstanding × close; no share-count or cap column (FACT) | N, D (bucket bounds) |
| 5 | ADV ≥ Rp B | 20-session mean of close × volume (`advOf`) | `Price_Stock_Indonesia_IDX` close, volume (FACT columns); or per-ticker price files | C |
| 6 | Price ≥ | last close | Last close per ticker | C (trivial) / I |
| 7 | Free float ≥ | `t.F.freeFloat` | No column (FACT) | N |
| 8 | Board Main/Development | `t.board` | No listing-board column; `market_board` = Regular/Nego/Tunai (FACT) | N, D |
| 9 | Exclude special notation (default on) | `t.notation` | No notation/FCA column (FACT) | N, D (default when there is no data) |
| 10 | Metric filters (universe) | 8 tech, 10 flow, 32 fundamental; default ROE>10 (1274, 1487) | Technical and flow series; fundamentals | C (tech/flow), N (fund.), D (allow registry indicators? change default) |
| 11 | Active chips, Clear all, "In universe X of N" | (1243, 1286) | Universe count after filters | C |
| 12 | Preset tabs, chips, match counts | 26 presets, all evaluated at boot (1187) | A server scan per preset; cost per page load | C, D (show counts? cache per data date) |
| 13 | Bandarmology presets (6) | bandar, fstreak, fnet, silent, freq, bavg, broker | Broker nets per broker per day, foreign net, trade frequency (see flow audit; trade frequency is not in the price table, FACT) | C, D (EDGE's own flow definitions; user: "come up with your own") |
| 14 | Technical presets (9) | Older keys only (FACT) | OHLCV; IHSG for RS; whole-market for `rs_rank` | C, D (rebuild on the 53-indicator registry?) |
| 15 | Fundamental presets (8) + Combined using fundamentals (canslim, qflow, vacc) | P/E, P/B, ROE, D/E, EPS growth, dividends, Piotroski, Altman, Magic rank, bank NIM/NPL/CAR/CASA/LDR | No fundamental tables (lead FACT) | N, D (hide until data exists) |
| 16 | My screens (save, load, duplicate, delete) | `localStorage edge-screens` | A server table for durability across devices (edge_bff has none) | D (browser vs server; a schema change needs approval) |
| 17 | Match All/Any/At least | `needOf` (1177) | The evaluation engine returns per-condition pass flags | C |
| 18 | Type-ahead adder + synonyms | 115 entries (1365) | The 53-indicator registry is in repo (`backtest-registry.json`, `terminal/src/data/indRegistry.json`); flow/fundamental catalog to be defined | S (53 tech), D (flow / fundamental list, removing the 10 duplicates) |
| 19 | Indicator browser | groups, list, details (1433) | Same as 18, plus descriptions | S / D |
| 20 | Condition card Default/Custom params | params grid, default hints (1318) | Any parameter value → indicators computed from OHLCV with custom params (cannot rely on precomputed default columns only) | C |
| 21 | Operators gt/lt/between/xa/xb; states/events "within N" | (1055) | Full series, at least N + warm-up bars per ticker | C |
| 22 | Save as My metric | `localStorage edge-metrics` | Same as 16 | D |
| 23 | Results meta, near misses, near toggle | (1518) | Per-ticker met count and pass flags | C |
| 24 | Results search | ticker or company substring | Company names: backtest `catalog.tickers[].name` / `reference/tickers` | S |
| 25 | Columns Symbol, Company, Sector | | Catalog | S |
| 26 | Columns Last, 1D | last two closes | Price | C / I |
| 27 | Column Mkt cap | | Shares outstanding | N |
| 28 | Column Avg value 20D | | Price × volume | C |
| 29 | Per-condition columns | value text, event age, Yes/No | Last value and last event index per condition | C |
| 30 | Sort, pagination, selection, bulk bar | client-side (1507) | All rows of one scan (at most ~844 stocks) in one answer | client only (INFERENCE: small enough) |
| 31 | Watchlist toggle / bulk add | `localStorage edge-watchlist` (1515) | EDGE has no Watchlist page or table (FACT) | D (+ N/schema if server-side) |
| 32 | CSV export (results / selected) | client Blob (1565) | Rows already loaded | client only |
| 33 | Detail head + logo | 2-letter badge | Optional real logo: `/api/terminal/v1/logo/{ticker}` (main.py:35) | I (optional) |
| 34 | Quote + status pill | last close, 1D, status | Price + scan result | I / C |
| 35 | "industry · board · indexes" line | | Industry S; board and indexes N | S / N |
| 36 | Preview chart: candles (130 sessions) + overlays + event markers | (1608) | One ticker's OHLCV: `POST /api/terminal/v1/bundle` (already used by Terminal and Backtest); overlays through the shared core; event bars of each condition | I + C |
| 37 | Performance: stock vs IHSG rebased 1M/3M/6M/1Y | (1581) | IHSG published (`terminal/src/data/live.ts:179-182`); the same maths as Terminal "Relative performance" (`stats.ts:263-281`) | I |
| 38 | "Why it passed" list | per-condition text | Scan answer for the ticker, or recompute on its bundle | I / C |
| 39 | Fundamentals facts (8 fields) | | No fundamental data | N |
| 40 | Copy summary | clipboard | none | client only |
| 41 | Method & sources: editable bandar thresholds | global `BANDAR` (1617) | Flow definition and thresholds | D, C |
| 42 | Screen name, source pill, "close <date>" | (1225) | `data_through` (backtest `catalog.data_through`) | S |
| 43 | Send to Backtest (dialog, JSON, link) | `backtest.html#import=` (1674) | The EDGE Backtest page has no import; its limit is 12 tickers; the request format differs (FACT) | D (defer, or add a page-only import), I |
| 44 | Global ticker search, ⌘K | hidden (1632) | Ticker list (S); placement conflicts with the EDGE shell's search | D |
| 45 | Theme toggle | `edge-scr-theme` | EDGE shell theme `localStorage edge-auth-monitor-theme`, `html.dark` (index.html App) | I / D |
| 46 | Nav (Analytics/Watchlist/Screener) | hidden | EDGE shell nav (`nav` array, `go()`, `App` path switch) | I |
| 47 | "Screen performance history" (as titled) | not implemented (3.9) | Point-in-time universe, historical evaluation, rebalance engine | D, C, N |

---

## 5. Existing EDGE front end (FACT)

### 5.1 Shell (`static/index.html`, 12,467 lines)

- The shell uses an in-house React-like runtime.
- **Routes:** `/`, `/monitor`, `/terminal`, `/backtest` and `/login` all serve `index.html` (`main.py:281-289`).
- **Nav:** `[["Monitor","monitor"], [Terminal,"terminal"], [Backtest,"backtest"]]` (index.html ~10614). `App` maps the path to `TerminalPage`/`BacktestPage`, and `go()` holds an allow-list (12432-12460).
- **Page components:** `TerminalPage` and `BacktestPage` render `Shell` with an `<iframe class="terminal-frame" src="/terminal-app/">` or `"/backtest-app/"` (10793-10807).
- **Labels:** `edge-labels.js:130-132` holds `terminal: {nav, frameTitle}` and `backtest: {nav, frameTitle}`.
- **Theme:** stored in `localStorage edge-auth-monitor-theme` (default dark) and applied as `html.dark`. No code in `backtest/src` or `terminal/src` reads it (grep empty).

### 5.2 Backtest page (`apps/edge-bff/backtest`)

- **Build:** Vite 7.1.9 + TS 5.9.3. `base:'/backtest-app/'`, one IIFE classic script at the end of `<body>` (the `classicScriptAtEnd` plugin), `cssCodeSplit:false`, test builds `--mode smoke` and `--mode fixture`.
- **Dockerfile:** a Node stage copies `terminal/src` next to it, because the shared core imports `terminal/src/calc/indicators.ts`. The output goes to `static/backtest-app` (Dockerfile:12-20).
- **Serving and CSP:** `/backtest-app/` and `/backtest-app/assets/{name}` with immutable caching. `BACKTEST_CSP = TERMINAL_CSP` is `script-src 'self'`, `worker-src 'self'`, `connect-src 'self' https://*.t3.storageapi.dev`, style `'unsafe-inline'` plus Google Fonts, `frame-ancestors 'self'` (`main.py:39-48, 242, 347-359`). Every other page gets EDGE's CSP: `script-src 'self' 'unsafe-inline'`, `connect-src 'self'` only (main.py:242).
- **Data:**
  - `BacktestApi` interface (`src/api/types.ts`) with the live implementation `src/api/live.ts`: CSRF from `/api/v1/auth/session`, then a per-ticker `POST /api/terminal/v1/bundle {ticker, datasets, packs:true}`.
  - The page downloads the presigned files with retries, verifies sha256 (`core/datafile.ts inflateVerified`) and decodes them in the browser.
  - The IndexedDB cache `terminal-files` (50 MB LRU) is shared with the Terminal (`src/api/cache.ts`).
  - Backtest jobs go through `/api/v1/backtests…` (`app/backtest.py:1049-1173`): catalog, signals preview (worker-computed, at most 12 tickers), submit, status, result, events and cancel.
- **Charts:** `signals.ts initPriceChart` uses lightweight-charts 5.2.1 `CandlestickSeries` + `createSeriesMarkers`, the same API pattern as the prototype's `drawChart`. It is bound to the page's module state (`S`, `DATA`, `$('priceChart')`).
- **Condition model:** older cards (`core/catalog.ts` LEGACY: adx, dmi, stoch, rsi, macd, ma, macross, volspike, breakout, bb, dip, fnet, broker, top5) and registry cards (`RegCard {ind:'I13', p, lhs, op gt|lt|ca|cb, rhs}`), sent as `Condition` (`core/contract.ts:22-52`). The page's own logic codes are `all|any|n` (`state.ts`); the wire uses `at_least`.
- **Picker:** `picked.ts searchMatches` matches tickers by prefix, then names by substring. These are the same semantics as the prototype's global search, in a pure, reusable module.

### 5.3 Terminal page (`apps/edge-bff/terminal`)

- **Build:** Vite + TS, `base:'/terminal-app/'`, IIFE, lightweight-charts 5.2.1 plus lightweight-charts-drawing 0.6.2 (patched ink).
- **Loader:** `src/data/live.ts` with a Web Worker (`src/data/worker.ts`, cache). IHSG loads lazily for Statistics → Relative performance.
- **Chart:** `src/app/chart.ts initChart(ctx)` builds the full terminal chart (candles, line, volume, compare series, display modes) from a `Ctx` that requires the terminal's markup (toolbar ids). It is not a standalone component.
- **Relative performance:** `stats.ts:263-281` computes stock vs IHSG rebased and draws it with a local `lineChart` helper defined inside `initStats` (stats.ts:153, not exported).
- **Remembered symbol:** the Terminal's symbol is `localStorage 'ml.symbol'` (main.ts:117, search.ts:47).

---

## 6. How the screener page should be delivered (INFERENCE / PROPOSED)

1. **PROPOSED: a third iframe app, built like the Backtest page.**
   - Create `apps/edge-bff/screener/` (Vite + TS, `base:'/screener-app/'`, one IIFE classic script, `cssCodeSplit:false`).
   - Port the markup from 530-550 without inline script, the CSS from 1-529 as `src/styles/screener.css`, and the script as modules: state, universe, presets, builder, browser, results, preview, dialogs, storage.
   - Data goes behind a `ScreenerApi` interface (like `BacktestApi`), with a `live` implementation and a `fixture` implementation (the prototype's synthetic data, for a 1:1 visual check; kept out of the production bundle as Backtest does, `tests/bundle.test.mjs`).
   - **Why:**
     - It keeps the prototype's CSS from mixing with EDGE's large stylesheet; the Terminal uses the iframe for this reason (FRONTEND_ARCHITECTURE.md §2).
     - It satisfies the strict CSP.
     - It reuses the shared core with no copy.
   - Inlining the page into `static/index.html` (EDGE CSP allows inline scripts) is the weaker option. It mixes CSS and runtime, and its `connect-src 'self'` would block presigned bucket downloads (FACT: main.py:242).
2. **PROPOSED: wiring in edge-bff, a code change that needs approval and a deploy.**
   - Add `/screener` to the index routes, plus `/screener-app/` and `/screener-app/assets/{name}` with `SCREENER_CSP = TERMINAL_CSP`.
   - Add a Dockerfile stage like the backtest stage.
   - In the shell: a nav entry `[EdgeLabels.screener.nav,"screener"]`, `ScreenerPage` with an iframe, and the `go()` and `App` path lists. Add `edge-labels.js` `screener:{nav:"Screener", frameTitle:"Stock screener"}`.
   - Words inside the app stay in the app, as Backtest's `api/texts.ts` does.
3. **PROPOSED: computation.**
   - A whole-market scan in the browser would need one `/bundle` call and file set per ticker for about 844 stocks. That goes through terminal-api quotas and the 50 MB browser cache (FACT: per-ticker `files()` in `backtest/src/api/live.ts`; cache limit in `cache.ts`).
   - The worker's preview is limited to 12 tickers (FACT).
   - The scan should therefore be a **new server endpoint** that returns, per ticker, last values, pass flags and the last event bar per condition, plus Last, 1D and ADV. The browser then sorts, pages, searches and exports locally (about 844 rows fit one answer, INFERENCE).
   - The single-ticker preview chart can keep the existing per-ticker bundle path.
   - Backend design belongs to the other areas. The worker must not be changed for this unless approved, because the user requires the existing worker not to break.
4. **PROPOSED: chart reuse instead of the vendored library.**
   - Import `lightweight-charts@5.2.1` from npm, the version already pinned in both apps, and drop the 197 KB inline copy.
   - Reuse modules, not page widgets:
     - `backtest/src/api/live.ts` patterns: `csrf`, `call`, `fetchFile` retries
     - `core/datafile.ts`: `inflateVerified`, `priceSeries`
     - `src/api/cache.ts`: the shared IndexedDB
     - `core/registry.ts` with `terminal/src/calc/indicators.ts`: overlay outputs for the 12 overlay indicators
     - `core/conditions.ts conditionSeries`: markers for gt/lt/cross registry conditions
     - `picked.ts searchMatches`: ticker search
   - Port the IHSG relative-performance maths and the `lineChart` helper from `terminal/src/app/stats.ts` (extracting it into a shared module touches the Terminal and needs approval). Otherwise keep the prototype's small SVG `plines`, fed with published IHSG.
   - Neither `terminal/src/app/chart.ts` nor `backtest/src/signals.ts` is reusable as a component, because both are bound to page state (INFERENCE from code). Copy the pattern instead.
   - Event types the shared core does not express (between, rising, states/events "within N", divergence, squeeze, flips) need new condition code (INFERENCE).
5. **PROPOSED: shell integration details.**
   - Keep the prototype header hidden.
   - Global search and ⌘K: either drop them or move them into the page. EDGE's shell search is "coming soon".
   - At boot, read the theme from `localStorage edge-auth-monitor-theme`; the prototype CSS already supports `html.dark`.
   - "Open in Terminal" could set `localStorage 'ml.symbol'` and navigate the parent to `/terminal` (same origin).
6. **Storage.** `localStorage` works unchanged inside a same-origin iframe (INFERENCE). Making screens, metrics and watchlist durable or cross-device needs new `edge_bff` tables: a schema change, which needs approval.

---

## 7. Product decisions this area surfaces

These are for the approval-gate list:

1. **Universe filters with no data** (index, board, notation, free float, market cap): hide them, disable them, or source new data first. Also decide the default "Exclude special notation = on" when no notation data exists.
2. **Fundamental group:**
   - 32 metrics, 8 Fundamental presets, 3 Combined presets that use fundamentals, the 8 fundamentals facts in the panel, "Add metric filter" defaulting to ROE, and ROE in the quick rail.
   - Decide: remove them until fundamental data exists, or show them disabled.
3. **Duplicates:** keep the older Technical entries (17) beside the 53 registry indicators, or rebuild the technical presets on the registry. Ten names are duplicated.
4. **Flow catalog:** EDGE's own definitions and thresholds (bandar ratio, top-N, broker follow, foreign streak, frequency spike, silent accumulation). Decide whether the bandar thresholds stay user-editable and global.
5. **Storage:** browser-only or server-side for saved screens, My metrics and watchlist. Decide also whether a Watchlist page is in scope.
6. **Send to Backtest:**
   - Defer it.
   - Or add a page-only import to the Backtest page (worker untouched), with at most 12 tickers, mapping registry indicators to `RegCard` and keeping "screen only" for the rest.
   - Or only hand over tickers.
7. **"Screen performance history":** keep it as stock-vs-IHSG and say so, or build a real point-in-time screen backtest (a separate engine).
8. **Preset match counts at load:** cost per page load. Cache them per data date, or drop them.
9. **Accessibility fixes** to include in the port: dialog modality and focus return, `aria-live` toast, `aria-sort`, keyboard-reachable rows.
10. **Fix the prototype inconsistencies (3.15) or keep them for 1:1:** the near-miss rules, "Clear all" and the liquidity clears.
