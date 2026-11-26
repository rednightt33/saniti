# Sector Analysis — FINAL prototype (v2) — interaction inventory

Audit of `<scratchpad>/sector/v2/src.html` on 2026-11-26. file:// in Chromium (Playwright), route #/overview; the EDGE shell renders one iframe (srcdoc) holding the app. The app script in v2/app_overview.txt is identical to v2/logic.js (233,085 chars, +17.5 KB vs v1); markup differs from v1 only in the Market map subtitle; CSS +5.7 KB. Same embedded data window.SX as v1.

Viewports: 1440x900 @1x (all clicks); 390x844 @1x (one full-page screenshot per tab). Data as of: Prices to Tue 17 Nov 2026 (latest close); broker data to Mon 9 Nov 2026.

Screenshots are in this folder; the structured copy of this file is `inventory_v2.json`; the changes from the first version are in `changes_v1_v2.md`.

## 1. Load

- Console errors: none. Console warnings: none. Page errors: none. Failed requests: none. HTTP 4xx/5xx: none.
- Requests: /api/v1/auth/config -> 200, /api/v1/auth/session -> 200, /api/v1/models -> 200, /api/v1/preferences -> 200 (shell, served by the pack shim). The Sector Analysis iframe made no fetch (data embedded in window.SX).
- v2: no console message of any level, no page error, no failed request during load or during the full click-through. Same 4 shell requests (200), no request from the app frame.

## 2. Data the page uses (for the database mapping)

- **object**: window.SX (embedded; recorded EDGE overview publisher files overview-series, overview-meta, overview-day-2026-11-17, plus SX.ind)
- **series**: 300 sessions 2025-08-22 .. 2026-11-17: dates; index.IHSG, index.LQ45 (closes); sector{11 IDX-IC sector index closes}; above_ema50, above_ema200 (% of all stocks, daily); breadth_n; flow{dates to 2026-11-09, foreign_buy, foreign_sell, turnover}
- **meta**: market "IHSG", benchmark "LQ45", stocks{ticker,name,sector} for 862 stocks, prices_through 2026-11-17, broker_through 2026-11-09, size_basis "adv20_value"
- **day**: one day (2026-11-17) per-stock snapshot for 833 stocks: close, r1d, r5d, r1m (%), size (20-day average traded value, Rp), above_ema50, above_ema200 (0/1), fnet_1d/5d/1m/3m (foreign net, Rp); index snapshot, volatility, breadth A/U/D counts, market turnover
- **ind**: ticker -> IDX-IC industry (shown as "Subsector")
- **not_available**: no per-stock price history and no per-sector breadth history: charts that need them use illustrative (seeded) values, flagged per card below

**Periods as the page computes them**

- 1D: 1 session
- 3D: 3 sessions
- 1W / 5D: 5 sessions
- 10D: 10 sessions
- 2W: 10 sessions
- 1M: 21 sessions
- 3M: 63 sessions
- 6M: 126 sessions
- 1Y: 250 sessions (Pair Ratio 1Y = 250, Beta 250D = 250)
- YTD: from the last session of the previous year (30 Dec 2025 close) to 17 Nov 2026
- return: index close ratio over the window, %
- relative / excess return: sector return − IHSG return over the same window, pp
- week (Weekly Excess Return, RRG tails, Timeline): block of 5 sessions ending on the shown date (not a calendar week)

## 3. Header controls

Title **Sector Analysis** — subtitle "Which sectors started improving in the last few sessions, against IHSG and against each other."

- **Pill "Prices to Tue 17 Nov" (green)** (`#pills .pill.pos`, status pill): Not interactive (click does nothing). Native tooltip (title): "Daily closes and every price figure".
- **Pill "Broker data to Mon 9 Nov" (amber)** (`#pills .pill.warn`, status pill): Not interactive. Title: "Foreign flow (broker summary, Regular board)". Note: no visible card uses foreign-flow data (fnet_* is used only by the hidden legacy "Sector stocks" card).
- **Date button "Tue 17 Nov · Close"** (`#datebtn`, dropdown menu): Opens a menu (.ddpop, role=menu) with one checked item "Tue 17 Nov · Close" tagged "latest" and the note "Earlier dates are not available in this prototype; they need the data service." Clicking the item, Escape or a click outside closes it; nothing else changes (no other date can be picked).
- **Open in Screener** (`#scrbtn`, button (aria-disabled="true")): Shows a toast for 3.2 s: "Open in Screener is not available in this prototype — the Screener page is not part of this file." Title: "Not available in this prototype: the Screener page is not part of this file". Rendered greyed.
- **Tabs** (`.bar1 [role=tab]`, tab list): Overview / Relative Strength / Rotation / Pair Matrix / Breadth. Click (or Enter on a focused tab) switches the panel; the KPI row shows on Overview only; every floating window closes on switch (the window pin button is hidden in v2); the locked sector carries across tabs. Arrow keys do not move between tabs.
- **Meta text "11 IDX-IC sectors · benchmark IHSG"** (`.bar1 .meta`, static text): Not interactive.

**KPI row** (`#kpis`, Overview only) — Four static tiles, no hover or click behaviour, no tooltips.

| Tile | Sub-label | Value | Detail |
|---|---|---|---|
| IHSG (5D) | Benchmark · vs 5 sessions ago | 5,304.76 | +179.03 · +3.49% · sparkline of the last 30 IHSG closes (green if up over 5 sessions) |
| Beating IHSG (5D) | Sectors with relative return > 0 | 4 / 11 | progress bar 4 of 11 |
| Strongest sector (5D) | Relative return vs IHSG | Transport | +1.78 pp · rank 1 of 11 |
| Improving (RRG) | Below IHSG trend, momentum turning up | 6 / 11 | Biggest rank gain Transport ▲8 (rank by 5D relative return today vs 5 sessions earlier) |

Screenshots: hdr_datebtn_open.png, hdr_scrbtn_toast.png, tab-ov_full.png

## 4. Behaviours shared by all tabs

- **Sector lock (pin)**: Clicking a sector in most cards locks it page-wide (list row, scatter dot, heatmap row, bar row, slope line, table row, RRG dot, timeline row). Cards that show one sector (Market map, RS "· stocks", Rotation stock quadrant, Beta window, Breadth selection) follow it; other cards mark it. Clicking the locked sector again unlocks. v2 shows the lock inside the cards: bigger dot with a halo on Momentum and on the RRG head, the other rows dimmed (opacity .32) in Sector × Horizon, Weekly Excess Return, Pair Matrix and the Breadth heatmap, the row bolded (Rank change and the RRG already muted the other sectors in v1). There is still no page-level "locked" indicator (the lock pill stays removed). In Rotation, a click on an RRG dot or timeline row is a one-click selection: it replaces any sectors picked in Rotation detail with that sector (and locks it); clicking the only selected sector again clears the selection and the lock. Cards that need one sector default to Infrastructures (Infra) when nothing is locked; the Overview market map defaults to the best 5D sector (Transport).
- **Expand to floating window** (`.card-h h3 .fwx (title "Expand")`): Every visible card except "Rotation direction & speed" has an expand icon (title "Expand"). v2 changes: (1) the window is sized to its content on first open (tables at natural width/height, charts at the card's page size, at least 560×360, at most the viewport − 48 px; e.g. Cumulative Return 1375×629, Sector Drill-down 872×852 stacked, Stock detail 560×852) and cascades +28 px for each window opened in the session; (2) a dark backdrop (.fw-bd) covers the page — a click on it closes the top window, so with the mouse only one window can be open at a time (the 3-window limit and its toast "Up to 3 windows can be open. Close one to open another." still exist in code and were reached only by script); (3) the pin button is hidden (CSS .fw-pin{display:none!important}), so every window closes on a tab switch; (4) a footer "How to read · <explanation> Example · <sentence built from the first row>"; (5) detail rows are clickable in more windows (per card below); (6) detail tables use the shared multi-level sort, with "Sorted by … · Clear sort" appended to the detail subtitle. Still: live copy of the card with its own filters on the left, detail on the right, drag by the title bar, resize from the corner (min 760×420), Escape or × closes. Verified: backdrop click closes; a tab switch closes; the detail tables of all 20 windows fit their pane at 1440×900.
- **Tooltips**: Elements with data-tip show .ovx-tip on hover. v2 adds on the line charts (Cumulative Return, "· stocks", RRG IHSG strip, Pair Ratio, Breadth vs Price) a dark date tag on the x-axis under the hover line, with weekday and 2-digit year (e.g. "Mon 16 Nov '26", "Fri 24 Oct '25"). A cut-off card subtitle shows its full text as a native tooltip on hover.
- **Custom date range popover**: Opens a "Custom date range" popover: From / To date inputs (min 2025-08-22 = first session in the data, max 2026-11-17), prefilled with the current range; live note e.g. "19 Aug → 17 Nov · 64 trading days"; messages "Pick both dates.", "“From” must be on or before “To”.", "Data covers 22 Aug to 17 Nov.", "Pick a range of at least 5 trading days."; Apply is disabled while invalid; Apply or Enter applies (first session on/after From, last on/before To); Cancel, Escape or a click outside closes. Clicking Custom again toggles the popover. Same popover on: Cumulative Return, RS "· stocks", Weekly Excess Return (weeks capped at 26), Pair Matrix spread, Pair Ratio (start clamped to MA length), Beta (window = sessions in range), Breadth vs Price. Rank change uses a single-date "Compare with" popover instead.
- **Multi-column sort**: v2: one shared sort on every sortable table and heatmap (Sector × Horizon, Sector Drill-down, Weekly Excess Return [new], Rotation detail, Pair Matrix columns, Beta & Correlation, Stretched Pairs, Breadth Heatmap Table, Stock detail, every window detail table). Header title: "<column tip> · Click to sort · again to reverse · a third time to remove · click other columns to add sort levels (up to 3)". First click: numbers high → low (↓), text A → Z (↑); a first click on the default column reverses it; second click reverses; third removes; up to 3 levels (a 4th drops the oldest), superscript order numbers. With no level the default order is marked by a faint arrow (class df) on its column (none when the default measure has no column: Weekly Excess Return, Stretched Pairs). With ≥ 2 levels the card legend (or window detail subtitle) starts with "Sorted by X ↓, then Y ↑ · Clear sort"; "Clear sort" restores the default. Arrows now mean the same everywhere: ↑ = ascending (A → Z, low → high), ↓ = descending. The old "Reset" link in subtitles is gone.
- **Local persistence**: Overview only: period, custom range, scatter axes, heatmap sort and a user-chosen legend selection are stored in localStorage key "edge.sa.overview.v1" and restored after reload (verified: YTD / X=1W / sort 1D survived a reload). Other tabs reset on reload. v2 also saves the Sector × Horizon sort levels (key "hs"); the new IHSG legend toggle of Cumulative Return is NOT saved (IHSG reappears after reload).
- **Focus and form styling (v2)**: Focus rings are grey (var(--text-3)) instead of blue; inputs/selects show no focus ring or shadow; date-input segments get a grey highlight when focused.

## 5. Tab: Overview

Layout: KPI row; then Cumulative Return (wide) | Momentum; Sector × Horizon | Market map (wide)

Tab screenshots: tab-ov_full.png, tab-ov_full_pinned-Energy.png, mobile390_tab-ov.png

### 5.1 Cumulative Return (`#rcCard`)

- **Subtitle**: "Cumulative return since the start of the period"
- **Chart type**: multi-line chart (cumulative %, rebased to 0 at period start) + ranked diverging bar list
- **What it plots**:
  - series: 11 IDX-IC sector indices + IHSG (dashed black). Coloured lines = selected sectors (navy, green, red, amber, violet, teal in sector order); others thin grey.
  - y_axis: cumulative return % (e.g. −20%, 0%)
  - x_axis: trading dates of the period (5 labels)
  - end_labels: right end: "Sector ±x.x%" for each coloured line and IHSG
  - side_list: right: one row per sector "name — bar — ±x.x%" sorted by period return (bars centred at 0)
  - units: %
- **Defaults**: Period 3M (19 Aug – 17 Nov, 63 sessions); coloured lines = top 2 and bottom 2 by period return (Non-Cyc, Financials, Infra, Tech).
- **Controls**:
  - **Period** (`#rcW button[data-k]`, segmented, default 3M): Changes the period of the lines, the list and the footer range; resets the coloured selection to top 2 + bottom 2 of the new period.
    - `1M` (value 21): 21 sessions: "19 Oct – 17 Nov"; list e.g. Financials +9.4% … Tech −10.5%; IHSG +6.2%
    - `3M` (value 63): 63 sessions: "19 Aug – 17 Nov"; IHSG −17.0%
    - `YTD` (value YTD): from 30 Dec close: "30 Dec – 17 Nov"; IHSG −38.7%
    - `Custom` (value C): Custom range popover (#rcPop, #rcD0/#rcD1, Cancel #rcPc, Apply #rcPa). Tested 2026-06-01..2026-09-30 → "2 Jun – 30 Sep · 11 sectors", Custom button active, selection reset to top2/bottom2 (Energy, Financials, Infra, Tech).
  - **Legend toggles (11)** (`#rcLg .ovx-tog[data-n]`, toggle buttons): v2 restyle: text toggles with a small square swatch; off = grey text struck through. Toggles a sector between coloured and grey; the line is never removed, only greyed. All off leaves only IHSG labelled. The chosen set is saved locally.
    - `Basic Mat.`
    - `Cons. Cyc`
    - `Non-Cyc`
    - `Energy`
    - `Financials`
    - `Health`
    - `Industrials`
    - `Infra`
    - `Property`
    - `Tech`
    - `Transport`
  - **IHSG legend toggle "--- IHSG" (new in v2)** (`#rcLg .ovx-tog.ihx`, toggle button, default on): Hides/shows the dashed IHSG line and its end label (title "Click to hide IHSG" / "Click to show IHSG", aria-pressed). Not saved in localStorage.
  - **Sector list rows (11)** (`#rcBl .r[data-n]`, rows (role=button)): Hover: that sector's line turns black (others grey), row highlighted. Click: locks the sector page-wide (aria-pressed=true): stays highlighted here, highlighted dot in Momentum, highlighted row in Sector × Horizon, Market map switches to the sector. Click again: unlock (map keeps the last sector).
  - **Chart hover** (`#rcLine`, hover): Crosshair + dot on the nearest sector line within 14 px; that line is highlighted; tooltip "Financials · 16 Nov / Cumulative −6.90% / IHSG −16.78%". v2: dark date tag on the x-axis (e.g. "Mon 16 Nov '26").
- **Footer / legend**: "19 Aug – 17 Nov · 11 sectors" | "Click a name to show or hide its line · point at a sector in the list to highlight it"
- **Expand window** — detail table "Period statistics" (19 Aug – 17 Nov · 63 sessions):
  - Columns: Sector (11 + IHSG row) · Return · vs IHSG (pp) · Max DD · Best day · Worst day · Up days (% of sessions up)
  - Default sort: Return ↓
  - Row click: locks the sector (row marked, page Market map follows) — new in v2
  - Window controls: own period 1M/3M/YTD/Custom (independent of the page)
  - Note: "How to read · Return = change over the period; vs IHSG = sector return − IHSG return; Max DD = the deepest fall from a peak inside the period. Example · Financials fell −6.5% but is +10.55 pp vs IHSG, so it did better than IHSG; …"
- **Data notes**: Real data: sector index and IHSG closes (series).
- **Defects observed**:
  - Still: line tooltip hidden whenever the hovered line changes (4 of 4 moves in a dense area left it hidden; same document-mousemove cause).
  - Still: legend "off" only greys the line; v2 strikes the label through, which reads even more like "hidden".
  - Still: popover counts "64 trading days" for the 63-session 3M range.
  - New: the IHSG toggle state is not persisted while the rest of the legend is.
- **Screenshots**: tab-ov_full.png, tab-ov_card-rc_period-YTD.png, tab-ov_card-rc_legend-BasicMat-on.png, tab-ov_card-rc_ihsg-off.png, tab-ov_card-rc_line-hover.png, tab-ov_full_pinned-Energy.png, tab-ov_card-rc_expand-window.png, ov_window-backdrop-howtoread.png

### 5.2 Momentum: Horizon vs Horizon (`#mmCard`)

- **Subtitle**: "Return over two horizons"
- **Chart type**: scatter (one dot per sector, 4 named quadrants)
- **What it plots**:
  - x_axis: "Return <X> →" centred under the x-axis (v2): sector index return over horizon X (%)
  - y_axis: "Return <Y> →" written vertically along the left axis (v2): sector index return over horizon Y (%)
  - points: 11 sectors; colour green = both ≥ 0, red = both < 0, amber = mixed; labels auto-placed; v2: no dark ring for a hidden label, footer adds " Point at a dot for names not shown."
  - quadrants: UP ON BOTH (top right), TURNING UP (top left), DOWN ON BOTH (bottom left), TURNING DOWN (bottom right)
- **Defaults**: X = 3M, Y = 1M
- **Controls**:
  - **Horizontal axis select** (`#mmX`, select, default 3M): Changes X horizon and axis title; saved locally.
    - `1W` (value 1W): 5 sessions
    - `1M` (value 1M): 21 sessions
    - `3M` (value 3M): 63 sessions
    - `YTD` (value YTD): since 30 Dec
  - **Vertical axis select** (`#mmY`, select, default 1M): Changes Y horizon and axis title; saved locally.
    - `1W` (value 1W): 5 sessions
    - `1M` (value 1M): 21 sessions
    - `3M` (value 3M): 63 sessions
    - `YTD` (value YTD): since 30 Dec
  - **Dots (11)** (`#mmSc .ovx-dot[data-n]`, points (role=button)): Hover: tooltip "Energy / Return 3M −23.8% / Return 1M −1.9%". Click or Enter: lock the sector — v2 draws the locked dot bigger with a halo; again: unlock.
- **Footer / legend**: "Top right = up on both horizons. Top left = turning up." (+ " Point at a dot for names not shown." when labels are hidden)
- **Expand window** — detail table "3M vs 1M by sector" (Horizontal 3M · vertical 1M):
  - Columns: Sector (11 + IHSG) · 3M · 1M · 1M − 3M (pp) · Reading (Up on both / Turning up / Turning down / Down on both) · Rank 3M · Rank 1M
  - Default sort: 1M − 3M ↓
  - Row click: locks the sector (new in v2); note starts "Click a row to select the sector on the chart · …"
  - Window controls: own X / Y selects; titles and columns follow them
  - Note: "How to read · Each dot = a sector placed at its return over the horizontal horizon (across) and the vertical horizon (up). Top right = up on both; top left = turning up. Example · …"
- **Data notes**: Real data: sector index closes.
- **Defects observed**:
  - Still: the same horizon can be chosen on both axes (3M vs 3M → diagonal).
  - Still: with 1M vs 1M only 3 quadrant labels are drawn.
  - Still: at 3M vs 1M the x = 0 line runs through the "UP ON BOTH" / "TURNING DOWN" labels.
- **Screenshots**: tab-ov_card-mm_x-1W.png, tab-ov_card-mm_y-3M-same-as-x.png, tab-ov_card-mm_dot-pinned.png, tab-ov_card-mm_expand-window.png

### 5.3 Sector × Horizon (`#hxCard`)

- **Subtitle**: "Return per horizon · click a column header to sort"
- **Chart type**: heatmap table
- **What it plots**:
  - rows: 11 sectors + bottom row "IHSG" (uncoloured)
  - columns: 1D, 1W, 1M, 3M, 6M, YTD, 1Y
  - cell: sector index return over the horizon (%, 1 decimal); green/red, intensity scaled per column by the largest |value|
  - horizons: 1D = 1, 1W = 5, 1M = 21, 3M = 63, 6M = 126 sessions, YTD = since 30 Dec, 1Y = 250 sessions
- **Defaults**: sorted by 1M ↓
- **Controls**:
  - **Column headers** (`#hxM .hd[data-k] (keys sn, h0…h6)`, sort headers (shared multi-level sort)): v2 shared sort: first click high → low (↓), again ↑, third click removes; up to 3 levels; legend "Sorted by 1M ↑, then Sector ↑ · Clear sort"; default (no level) = 1M ↓ shown as a faint arrow. The blank first header sorts by sector name (A → Z ↑ first). Sort levels saved locally.
    - `(blank) = Sector name`
    - `1D`
    - `1W`
    - `1M`
    - `3M`
    - `6M`
    - `YTD`
    - `1Y`
  - **Row names and cells** (`#hxM .nm[data-n], #hxM div[data-n]`, rows / cells): Hover: row highlighted, cell tooltip "Energy / 3M −23.84%". Click (or Enter on a name): lock the sector; again unlock. v2: when a sector is locked the other rows are dimmed and its name is bold.
  - **IHSG row** (`#hxM .nm.ih`, static row): Not interactive. Values: −0.3% / +3.5% / +6.2% / −17.0% / −21.1% / −38.7% / −35.0%.
- **Footer / legend**: "Colour scaled per column · bottom row: IHSG"
- **Expand window** — detail table "Excess return vs IHSG" (Sector return − IHSG return per horizon (pp)):
  - Columns: Sector · 1D · 1W · 1M · 3M · 6M · YTD · 1Y (all pp) · Avg rank (mean rank over the 7 horizons)
  - Default sort: Avg rank ↑
  - Row click: locks the sector (new in v2)
  - Note: "How to read · Each cell = sector return − IHSG return over that horizon, in percentage points; green = ahead of IHSG. Avg rank 1 = strongest across horizons. Example · …"
- **Data notes**: Real data: sector index and IHSG closes.
- **Defects observed**: none.
- **Screenshots**: tab-ov_card-hx_multisort.png, tab-ov_card-hx_row-pin.png, tab-ov_card-hx_expand-window.png

### 5.4 <Sector> · market map (default "Transport · market map") (`#mkCard`)

- **Subtitle**: "Tile size = 20D avg trading value · colour = 5D return − IHSG · grouped by subsector"
- **Chart type**: treemap (sector → IDX-IC subsector → stocks)
- **What it plots**:
  - grouping: stocks of one sector grouped by IDX-IC industry (SX.ind, shown as "Subsector"); largest 10 stocks per subsector
  - area: 20-day average trading value (adv20_value, Rp)
  - colour: stock 5D return − IHSG 5D return (pp); green/red, intensity scaled by the largest |value| in the sector
  - labels: tile: ticker and ±pp; group: "Subsector ±x.x" (value-weighted 5D vs IHSG)
  - legend: colour scale − … +
- **Defaults**: sector with the best 5D return (Transport: "36 stocks in 3 subsectors · largest 10 per subsector")
- **Controls**:
  - **Sector shown** (`(no control in the card)`, follows lock): Switches to the sector locked anywhere on Overview; stays on the last locked sector after unlock.
  - **Stock tiles** (`#mkM .mk-t`, hover): Tooltip "BUMI PT Bumi Resources Tbk Class A / Coal / 5D +9.17% · vs IHSG +5.67 pp / Trading value Rp 355.1B". Click does nothing.
  - **Subsector labels** (`#mkM .mk-gl`, hover): Tooltip "Coal / 40 stocks · Rp 1.32T / 5D vs IHSG (value-weighted) +0.4 pp".
- **Footer / legend**: "<n> stocks in <k> subsectors · largest 10 per subsector" + colour scale
- **Subsectors by sector** (stocks / subsector count: names):
  - Basic Mat.: 92 stocks / 5: Metals & Minerals, Chemicals, Containers & Packaging, Construction Materials, Forest & Paper
  - Cons. Cyc: 136 / 12: Tourism & Recreation, Automotive Components, Media, Specialty Retail, Apparel & Luxury Goods, Entertainment & Movie Production, Household Goods, Education & Support Services, Department Stores, Consumer Goods Distributors, Sports Equipment & Hobbies Goods, Consumer Electronics
  - Non-Cyc: 120 / 6: Agricultural Food Products, Processed Foods, Food & Staples Retailing, Personal Care Products, Tobacco, Beverages
  - Energy: 76 / 4: Coal, Oil & Gas, Oil, Gas & Coal Support, Alternative Energy Equipment
  - Financials: 99 / 5: Banks, Holding & Investment Companies, Consumer Financing, Insurance, Investment Services
  - Health: 39 / 3: Healthcare Providers, Pharmaceuticals, Healthcare Equipment & Supplies
  - Industrials: 56 / 7: Multi-sector Holdings, Building Products & Fixtures, Machinery, Commercial Services, Professional Services, Diversified Industrial Trading, Electrical Equipment
  - Infra: 54 / 6: Telecommunication Services, Wireless Telecommunication Services, Electric Utilities, Building Construction, Transportation Infrastructure Operators, Gas Utilities
  - Property: 77 / 1: Real Estate Management & Development
  - Tech: 41 / 6: Internet Applications & Services, Software, IT Services & Consulting, Networking Equipment, Computer Hardware, Electronic Equipment, Instruments & Components
  - Transport: 36 / 3: Logistics & Deliveries, Passenger Ground Transportation, Airlines
- **Hidden part**: A horizon summary strip (#mkS: "Sector" 1D / 5D / 1M / 3M / YTD returns and a "vs IHSG" pp row) is rendered into the header but hidden by CSS (#mkS{display:none !important}).
- **Expand window** — detail table "<Sector> · subsectors" ("36 stocks · 5D, value-weighted"):
  - Columns: Subsector · Stocks · Value share (% of the sector's 20D avg traded value) · 5D (value-weighted) · vs IHSG (pp) · Up 5D (% of stocks) · Leader (best 5D stock) · Leader 5D
  - Default sort: Value share ↓
  - Row click: picks the subsector out on the window map (other subsectors dimmed to .32); click again to clear — new in v2
  - Sector select: 11 sectors; changes the window map and table only
  - Note: "How to read · Tile size = 20D average trading value; colour = 5D return − IHSG. Value share = the subsector’s part of the sector’s trading value. Example · Coal takes 61.0% of the sector’s trading value; it moved +3.9% in 5D (+0.36 pp vs IHSG), led by ARII at +30.1%."
- **Data notes**: Real data: one-day stock snapshot (r5d, size = adv20 traded value) + IDX-IC industry map.
- **Defects observed**:
  - Still: tiles not clickable on the page.
  - Still: keeps the last locked sector after unlock.
  - Still: Energy · Alternative Energy Equipment (1 stock) gets no tile.
  - Still: horizon summary strip (#mkS) hidden by CSS.
- **Screenshots**: tab-ov_full.png, tab-ov_card-mk_window-subsector-picked.png, ov_windows-max3-toast.png

## 6. Tab: Relative Strength

Layout: Sector Drill-down (top-left, wide) | Rank change (top-right); "<Sector> · stocks" + Weekly Excess Return (bottom-left) | Relative Return (bottom-right). The "Acceleration and streak" card is in the markup but hidden (#rsC{display:none}).

Tab screenshots: tab-rs_full.png, tab-rs_full_locked-Energy.png, mobile390_tab-rs.png

### 6.1 Sector Drill-down (`#rsD`)

- **Subtitle**: "Return, return vs IHSG and RS rating (1–99 rank of 1M vs IHSG) per sector and subsector"
- **Chart type**: table (11 sector rows, scrolls inside the card)
- **What it plots**:
  - columns:
    - Sector
    - 3D
    - 1W
    - 1M
    - 3M
    - YTD (sector index return, %)
    - vs IHSG 1M (pp; title "Excess return vs IHSG, 1M (pp)")
    - vs IHSG 3M (pp; title "Excess return vs IHSG, 3M (pp)")
    - RS (title "RS rating 1–99": percentile of the 1M excess return among the 11 sectors; values 99, 89, 79 … 1)
    - Δ 4W (title "RS rating now vs 4 weeks ago": RS now − RS computed 20 sessions earlier; "·" = unchanged)
    - > EMA50 (title "Share of member stocks above their 50-day EMA", %)
    - RRG (quadrant tag: Leading / Improving / Weakening / Lagging; title "Leading > Improving > Weakening > Lagging")
    - Momentum (Gaining / Steady / Fading tag; tag title "1W excess − average week of 1M excess: ±x.xx pp"; threshold ±0.5 pp)
- **Defaults**: sorted by RS ↓
- **Controls**:
  - **Column headers (13)** (`#rsD th[data-k] (Sector key now "sn")`, sort headers (shared multi-level sort)): v2 shared sort, up to 3 levels with "Sorted by … · Clear sort" in the legend; default RS ↓ (faint arrow); Sector sorts A → Z with ↑. RRG sorts Leading > Improving > Weakening > Lagging.
    - `Sector`
    - `3D`
    - `1W`
    - `1M`
    - `3M`
    - `YTD`
    - `vs IHSG 1M`
    - `vs IHSG 3M`
    - `RS`
    - `Δ 4W`
    - `> EMA50`
    - `RRG`
    - `Momentum`
  - **Sector rows** (`#rsD tr.g[data-n]`, rows (role=button)): Click: lock the sector (row marked; "· stocks", Rank change, Weekly heatmap, Relative Return mark it). Click again: unlock. No subsector rows open.
- **Footer / legend**: "vs IHSG in pp · RS = rating 1–99" | "17 Nov"
- **Expand window** — detail table "<Sector> · stocks (stacked under a copy of the table)" ("54 stocks"):
  - Columns: Ticker · Subsector · 1D · 5D · 5D vs IHSG (pp) · 1M · EMA50 (Above/Below) · Avg value (20D avg daily traded value)
  - Default sort: Avg value ↓
  - Row click: rows of the copied table switch the stock list
  - Sector select: 11 sectors
  - Search: "Search stock" (no match: "No stock matches “ZZZZ”.")
  - Layout: stacked (table on top, stocks below), 1146 px wide
  - Note: "How to read · Returns are the stock’s own. 5D vs IHSG = stock 5D return − IHSG 5D return. EMA50 = close above or below its 50-day average. Example · TLKM moved +6.9% in 5D, which is +3.37 pp vs IHSG; it closes below its EMA50."
- **Data notes**: Sector rows: real (sector closes, member stock flags). The code also builds subsector rows with random 3M/YTD/RS Δ/RRG (illustrative) but never shows them.
- **Defects observed**:
  - Still: subsector rows never appear — and the v2 subtitle now says "per sector and subsector".
- **Screenshots**: tab-rs_full.png, tab-rs_card-rsD_sort-RRG.png, tab-rs_card-rsD_expand-window.png, tab-rs_full_locked-Energy.png

### 6.2 Rank change (`#rsB`)

- **Subtitle**: "Rank by 5D relative return · 10 Nov → today"
- **Chart type**: slope chart (rank then → rank today)
- **What it plots**:
  - left: rank 1–11 on the compare date
  - right: rank today (17 Nov) with ▲n / ▼n / —
  - ranking: by N-session relative return (sector − IHSG), N = the Relative Return "Window" (3D/5D/10D)
  - colour: green = up 3+ places, red = down 3+, grey otherwise; locked sector black
- **Defaults**: compare 5D (10 Nov), N = 5
- **Controls**:
  - **Compare period** (`#rbk button[data-v]`, segmented, default 5D): Moves the compare date.
    - `5D` (value 5): 10 Nov → today
    - `10D` (value 10): 3 Nov → today
    - `1M` (value 21): 19 Oct → today
    - `Custom` (value C): Popover "Compare with" (one date input; min = data start + N sessions = 29 Aug 2025 for 5D; max 16 Nov). Messages: "Pick a date.", "Pick a date before today.", "Data starts 29 Aug 2025.", OK "Rank on Thu 1 Oct 2026 vs today · 33 sessions". Apply/Enter applies, Cancel/Escape/outside closes. Tested 2026-10-01 → "1 Oct → today".
  - **Window (in the Relative Return card)** (`#rsn`, segmented): Changes the ranking basis: subtitle "Rank by 10D relative return".
  - **Slope lines** (`#rsB .sl[data-n]`, lines): Hover: tooltip "Transportation & Logistic / Rank 6 on 1 Oct → 1 today · up 5 / 5D vs IHSG: +0.19 pp → +1.78 pp". Click: lock the sector; again unlock.
- **Footer / legend**: legend "up 3+ places", "down 3+" | "10 Nov → 17 Nov"
- **Expand window** — detail table "Rank history" (Rank by 5D relative return on each date):
  - Columns: Sector · 20 Oct · 27 Oct · 3 Nov · 10 Nov · 17 Nov (rank on weekly checkpoints + compare date; compare column highlighted) · Places gained · 5D vs IHSG (pp)
  - Default sort: Places gained ↓
  - Row click: locks the sector
  - Note: "How to read · Rank 1 = highest 5D return vs IHSG on that date. Places gained = last week’s rank − this week’s rank (positive = moved up). Example · Transport went from #9 on 10 Nov to #1 on 17 Nov, so up 8 places."
- **Data notes**: Real data: sector and IHSG closes.
- **Defects observed**: none.
- **Screenshots**: tab-rs_card-rsB_compare-1M.png, tab-rs_card-rsB_expand-window.png

### 6.3 Relative Return (`#rsA`)

- **Subtitle**: "Sector return − IHSG return over the last 5 sessions (pp)"
- **Chart type**: horizontal diverging bar chart (sorted high → low)
- **What it plots**:
  - vs IHSG mode: bar = sector N-session return − IHSG N-session return (pp); zero line = IHSG
  - Absolute mode: bar = sector N-session return (%); IHSG return drawn as a marker line; subtitle "Sector index return over the last 5 sessions · dashed line = IHSG"
  - value labels: ±x.xx pp (or %) at the right
- **Defaults**: Window 5D, vs IHSG
- **Controls**:
  - **Window** (`#rsn button[data-v]`, segmented (label "Window"), default 5D): Changes N here and the ranking basis of Rank change.
    - `3D` (value 3): "last 3 sessions", 12 Nov – 17 Nov, IHSG 3D +1.03%
    - `5D` (value 5): 10 Nov – 17 Nov, IHSG 5D +3.49%
    - `10D` (value 10): 3 Nov – 17 Nov, IHSG 10D +8.17%
  - **Mode** (`#rsb button[data-v]`, segmented, default vs IHSG): Switch excess vs absolute.
    - `vs IHSG` (value rel): excess return, pp
    - `Absolute` (value abs): sector return, %; e.g. Transport +5.27% … Basic Mat. −2.76%
  - **Bar rows** (`#rsA .dvb .r[data-n]`, rows (role=button)): Hover: tooltip "Energy · 5D / Sector +2.11% · IHSG +3.49% / Excess −1.38 pp / Rank 9 of 11". Click: lock; again unlock.
- **Footer / legend**: "IHSG 5D +3.49% is the zero line" | "10 Nov – 17 Nov"
- **Expand window** — detail table "Relative return by window ("Return by window" in Absolute)" (Sector − IHSG (pp) / Sector index return):
  - Columns: Sector · 1D · 3D · 5D · 10D · 1M · Rank <N>D
  - Default sort: <N>D ↓
  - Row click: locks the sector
  - Window controls: own Window and Mode
  - Note: "How to read · Each value = sector return − IHSG return over that window, in percentage points; positive = ahead of IHSG. Example · Transport 5D +1.78 pp = over the last 5 sessions it beat IHSG by that much, rank #1 on 5D."
- **Data notes**: Real data.
- **Defects observed**: none.
- **Screenshots**: tab-rs_card-rsA_expand-window.png

### 6.4 <Sector> · stocks (default "Infra · stocks") (`#rsL`)

- **Subtitle**: "Return since <start date> · top 10 traded (e.g. "Return since 19 Aug · top 10 traded"; 1M → "since 19 Oct", YTD → "since 30 Dec", custom → "since 1 Jul")"
- **Chart type**: multi-line chart (cumulative % from period start)
- **What it plots**:
  - series: top 10 stocks of the locked sector by 20D avg traded value + the sector index (dashed black)
  - colour: top 2 and bottom 2 stocks coloured, others grey
  - end_labels: e.g. "TOWR −15.4%", "Infra −34.3%"
  - y_axis: cumulative %
  - x_axis: dates (3 labels)
- **Defaults**: sector = locked sector, else Infrastructures; period 3M
- **Controls**:
  - **Period** (`#rslw button[data-v]`, segmented, default 3M): Changes the period; clears the highlighted stock.
    - `1M` (value 21): 19 Oct – 17 Nov
    - `3M` (value 63): 19 Aug – 17 Nov
    - `YTD` (value YTD): 30 Dec – 17 Nov
    - `Custom` (value C): From/To popover (see global). Tested 2026-07-01..2026-10-31 → "1 Jul – 30 Oct".
  - **Chart hover** (`#rsL .rlc`, hover): Nearest stock line thickens, others fade; tooltip "BREN · 29 Sep / Cumulative −21.46% / Infra index −9.99%". v2: date tag on the x-axis (e.g. "Tue 29 Sep '26").
  - **Sector** (`(lock from any card)`, follows lock): Title, lines and legend follow the locked sector (e.g. "Financials · stocks": BBCA +10.1%, COIN +5.3% …).
- **Footer / legend**: "- - Infra index · top 2 and bottom 2 coloured" | "19 Aug – 17 Nov"
- **Expand window** — detail table "<Sector> · top 10 by value" (The stocks drawn in the chart):
  - Columns: Ticker · Subsector · 1D · 5D · 5D vs sector (pp) · 1M · Avg value
  - Default sort: Avg value ↓
  - Row click: highlights that stock's line in the window chart
  - Sector select: 11 sectors
  - Search: Search stock
  - Note: "How to read · Lines = each stock’s cumulative return from the start date; the dashed line is the sector index. 5D vs sector = stock 5D − sector 5D. Example · …"
- **Data notes**: ILLUSTRATIVE: the stock price paths are dummy (seeded random walks around the sector index; code comment "Design phase: stock price paths are dummy"). Only the sector index line and the table figures are real; the data has no per-stock price history.
- **Defects observed**:
  - Still: stock lines are illustrative.
  - Still: shows Infra silently when nothing is locked.
- **Screenshots**: tab-rs_card-rsL_hover.png, tab-rs_card-rsL_window-row-highlight.png

### 6.5 Weekly Excess Return (`#rsW`)

- **Subtitle**: "Sector − IHSG return per 5-day week (pp)"
- **Chart type**: heatmap (sectors × weeks)
- **What it plots**:
  - rows: 11 sectors; default order = 20-session excess return ↓ (no column shows it, so no default arrow)
  - columns: consecutive 5-session blocks; header = month (when it changes) + day of the last session; header title "5 sessions ending 17 Nov 2026"
  - cell: sector 5-session return − IHSG 5-session return (pp); green/red intensity scaled by the largest |value|
- **Defaults**: 8W (columns Sep 29, Oct 6, 13, 20, 27, Nov 3, 10, 17)
- **Controls**:
  - **Weeks** (`#rsww button[data-v]`, segmented, default 8W): Number of 5-session columns.
    - `4W` (value 4): Oct 27, Nov 3, 10, 17; "20 Oct – 17 Nov"
    - `8W` (value 8): "22 Sep – 17 Nov"
    - `Custom` (value C): From/To popover; weeks = floor(sessions / 5), max 26 (wider ranges are cut silently). Tested 2026-01-02..2026-11-17 → "26 weeks · 7 May – 17 Nov", horizontal scroll, scrolled to the right end.
  - **Cells** (`#rsW .c[data-tip]`, hover): Tooltip "Financials · 27 Oct – 3 Nov / Sector −2.95% / IHSG −6.87% / Excess +3.92 pp".
  - **Sector name buttons** (`#rsW .nm[data-s]`, buttons): Click: lock the sector; again unlock. v2: a locked sector dims the other rows' cells.
  - **Headers (new in v2)** (`#rsW .hd[data-k] (sn = blank sector header, w<idx> = each week)`, sort headers (shared multi-level sort)): Sort rows by sector name or by any week column (title "5 sessions ending 17 Nov 2026 · Click to sort …"); up to 3 levels; legend "Sorted by week to 17 Nov ↑, then week to 29 Sep ↓ · Clear sort"; the blank sector header shows only an arrow when sorted.
- **Footer / legend**: "8 weeks · week ending on the date shown" | "22 Sep – 17 Nov"
- **Expand window** — detail table "Weekly summary" ("8 weeks · 22 Sep – 17 Nov"):
  - Columns: Sector · Avg week (pp) · Weeks ahead (n / N) · Best week · Worst week · Streak (n up / n down)
  - Default sort: Avg week ↓
  - Row click: locks the sector
  - Note: "How to read · Each week = sector return − IHSG return over 5 sessions. Weeks ahead = weeks with a positive gap; streak = latest run ahead (+) or behind (−). Example · Financials averaged +1.15 pp a week vs IHSG and was ahead in 6 / 8 weeks; best week +3.93 pp."
- **Data notes**: Real data.
- **Defects observed**:
  - Still: custom range capped at 26 weeks without a message (2 Jan → 7 May).
  - Still: 5-session "weeks" drift from calendar weeks.
- **Screenshots**: tab-rs_card-rsW_weeks-4W.png, tab-rs_card-rsW_custom-long.png, tab-rs_card-rsW_sorted-2-levels.png, tab-rs_card-rsW_expand-window.png

## 7. Tab: Rotation

Layout: left column: Relative Rotation Graph, Rotation direction & speed; right column: Rotation detail, stock momentum quadrant

Tab screenshots: tab-rot_full.png, tab-rot_full_locked-Energy.png, tab-rot_full_multi-select.png, tab-rot_full_rotpick.png, mobile390_tab-rot.png

### 7.1 Relative Rotation Graph (`#rotA`)

- **Subtitle**: "RS-Ratio × RS-Mom vs IHSG · 17 Nov · tail 4W"
- **Chart type**: RRG (rotation scatter with tails) + IHSG weekly line above; alternative view "Timeline" (quadrant heat-strip)
- **What it plots**:
  - ihsg_strip: IHSG close at 52 weekly points (every 5 sessions, 24 Oct 2025 – 17 Nov 2026); grey band = tail period; vertical line + dot = RRG date; label "17 Nov · 5,305 · +0.5% over tail"; y labels 9,075 / 6,990 / 4,904
  - rrg: X = RS-Ratio, Y = RS-Momentum (both centred on 100; ticks e.g. 93.2 … 106.8); quadrant fills Leading (top-right, green), Weakening (bottom-right, amber), Lagging (bottom-left, red), Improving (top-left, blue); per sector a head dot (quadrant colour) and a smoothed tail through the weekly readings. v2: "RS-Momentum →" written vertically along the y-axis, "RS-Ratio →" centred under the x-axis, wider margins; all 11 labels drawn at the default size (v1 hid 1); a hidden label no longer gets a dark ring; the locked head gets a halo (r 16) and a bigger dot (r 9)
  - formula_chip: "Draft formula" (title: "RS-Ratio = 100 × (sector/IHSG) ÷ its 20-session mean; RS-Momentum = 100 × RS-Ratio ÷ RS-Ratio 5 sessions ago")
  - timeline: rows = 11 sectors (grouped by current quadrant, then RS-Ratio), columns = the same 52 weekly readings, cell colour = quadrant; outlined column = RRG date; v2: the locked row is no longer outlined (the other rows are muted); right column "Nw" = weeks in the current quadrant ("in phase"); legend Leading / Weakening / Lagging / Improving
- **Defaults**: RRG view, tail 4W, IHSG strip on, RRG date = 17 Nov (latest)
- **Controls**:
  - **View** (`#rotv button[data-v]`, segmented, default RRG): Switch graph.
    - `RRG` (value rrg): rotation graph
    - `Timeline` (value tl): subtitle "RRG quadrant of each sector per week · 24 Oct – 17 Nov · outlined = 17 Nov"; Tail control hidden; strip label "… over period"
  - **Tail (RRG only)** (`#rott button[data-v]`, segmented (label "Tail"), default 4W): Number of weekly points in each tail; subtitle "tail 8W"; IHSG band widens ("−15.5% over tail" for 8W, "−18.4%" for 12W). If the RRG date is too early for the tail it moves forward.
    - `4W` (value 4): 5 points
    - `8W` (value 8): 9 points
    - `12W` (value 12): 13 points
  - **IHSG toggle** (`#rotA .ihq`, toggle button, default on): Hides/shows the IHSG strip (title "Hide the IHSG chart" / "Show the IHSG chart").
  - **IHSG strip** (`#rotA .ihc`, hover + click): Hover: crosshair + tooltip "IHSG · week of 10 Mar / Close 7,440.91 / 1 week −6.28% / Click to set the RRG date" (or "Too early for this tail"). Click: sets the RRG date to that week (subtitle "vs IHSG · 10 Mar · tail 4W"; Direction & speed follows); clamped to the first week with a full tail; a click at the right end returns to "17 Nov (latest)". In Timeline it moves the outlined column. v2: date tag on the axis while hovering (e.g. "Fri 24 Oct '25").
  - **Head dots** (`#rotA .pt[data-n]`, points): Hover: tooltip "Energy · Improving / RS-Ratio 96.41 · RS-Momentum 100.16 / Click to pin", tail emphasised. Click (v2 one-click selection): if sectors are picked in Rotation detail they are replaced by this one (and it is locked); clicking the only selected sector again clears the selection and the lock; otherwise lock/unlock as before.
  - **Tail points** (`#rotA g.tl circle[data-tip]`, hover): Tooltip "Energy · week ending 20 Oct / Lagging / RS-Ratio 96.17 · RS-Momentum 97.72".
  - **Timeline cells / names / "Nw"** (`#rotA .rrg rect[data-tip], text.tn, text.tw`, hover + click): Cell tooltip "Industrials · week ending 1 Sep / Leading / RS-Ratio 101.62 · RS-Momentum 105.18"; "Nw" tooltip "Industrials: 2 weeks in Leading as of 17 Nov"; name or row click locks/unlocks.
- **Footer / legend**: "Click a dot to pin the sector · hover for values" ("Click a dot to pin the sector · hover a dot for names not shown" when labels are hidden) + "Draft formula" chip
- **Expand window** — detail table "RRG readings · 17 Nov" (One row per sector at the RRG date):
  - Columns: Sector · RS-Ratio · RS-Mom · Quadrant · Weeks in · Δ Ratio 1W · Δ Mom 1W · Heading (Ratio up / Strengthening / Momentum up / Turning up / Ratio down / Weakening / Momentum down / Rolling over)
  - Default sort: RS-Ratio ↓
  - Row click: locks the sector
  - Window controls: own View / Tail; Timeline fills the whole window
  - Note: "How to read · RS-Ratio above 100 = stronger than IHSG; RS-Momentum above 100 = that strength is rising. Leading = both above 100, Lagging = both below. Example · Industrials: RS-Ratio 101.85 (stronger than IHSG) and RS-Mom 101.26 (gaining strength) → Leading."
- **Data notes**: Real data: sector/IHSG closes; RRG computed in the page (formula labelled "Draft").
- **Defects observed**:
  - Still: strip axis and subtitles have no year across 24 Oct 2025 – 17 Nov 2026 (the hover date tag now shows the year).
  - Still: first IHSG week tooltip "1 week 0.00%".
  - Still: #rotn handler without a control.
- **Screenshots**: tab-rot_full.png, tab-rot_card-rotA_tail-12W.png, tab-rot_card-rotA_ihsg-off.png, tab-rot_card-rotA_dot-hover.png, tab-rot_card-rotA_date-moved.png, tab-rot_card-rotA_view-Timeline.png, tab-rot_full_locked-Energy.png, tab-rot_full_rotpick.png, tab-rot_card-rotA_expand-window.png

### 7.2 Rotation direction & speed (`#rotD`)

- **Subtitle**: "Move on the RRG over the week to 17 Nov · length = speed · 0–90° = strengthening"
- **Chart type**: small multiples (11 compass tiles with an arrow)
- **What it plots**:
  - arrow: move on the RRG over the window to the RRG date: angle = atan2(Δ RS-Momentum, Δ RS-Ratio), length scaled to speed (hypot of the deltas)
  - label: sector + angle in degrees (e.g. "Infra 67°")
  - colour: 0–90° green, 90–180° blue, 180–270° red, 270–360° amber
- **Defaults**: Window 1W, Sort Angle
- **Controls**:
  - **Window** (`#cmpw button[data-v]`, segmented (label "Window"), default 1W): Look-back of the move.
    - `1W` (value 1): "over the week"
    - `2W` (value 2): "over 2 weeks"
    - `4W` (value 4): "over 4 weeks"
  - **Sort** (`#cmps button[data-v]`, segmented (label "Sort"), default Angle): Tile order.
    - `Angle` (value ang): ascending angle
    - `Speed` (value sp): fastest first
  - **Tiles** (`#rotD .cpi[data-n]`, tiles (role=button)): Hover: tooltip "Tech · Improving / Direction 77° · speed 11.66 over 1W / Δ RS-Ratio +2.72 · Δ RS-Momentum +11.34 / Click to highlight · Ctrl/Cmd-click to add". Click: highlight that sector only (v2: the selected tile gets a darker border, the other tiles are no longer dimmed; others muted in the RRG/timeline, row selected in Rotation detail, footer "1 highlighted in the RRG · Clear") and lock it. Ctrl/Cmd-click adds/removes. Clicking the only highlighted tile clears the highlight.
  - **RRG date** (`(set in the RRG IHSG strip)`, follows): The "to <date>" in the subtitle follows the RRG date.
- **Footer / legend**: (none)
- **Expand window**: none (no expand icon).
- **Data notes**: Real data (RRG computed in the page).
- **Defects observed**:
  - Still: only 7 of 11 tiles visible at 1440 px (row 1060 px in 684 px).
  - Still: subtitle truncated — v2 shows the full text as a tooltip on hover.
  - Still: clearing the highlight on a tile leaves the sector locked (stock quadrant stays on it).
  - Still: no expand button.
- **Screenshots**: tab-rot_card-rotD_multi.png

### 7.3 Rotation detail (`#rotB`)

- **Subtitle**: "Quadrant now vs 5D ago · speed = RRG distance moved in 5 sessions"
- **Chart type**: table
- **What it plots**:
  - columns:
    - Sector
    - Current quadrant (tag)
    - Previous (5D ago) (tag; "=" when unchanged; header title "Quadrant on 10 Nov 2026")
    - Speed (distance moved on the RRG in 5 sessions)
    - Last change ("from <quadrant> · <date>"; header title "Sorted by date of the last quadrant change")
- **Defaults**: Previous = 5D ago; no sort level (rows ordered by the change in RS-Momentum over 3 sessions, not shown)
- **Controls**:
  - **Previous** (`#rotp button[data-v]`, segmented (label "Previous"), default 5D ago): Changes the Previous column, its header AND the subtitle ("Quadrant now vs 10D ago · speed = RRG distance moved in 10 sessions"; 1M → "21 sessions") — but the Speed values do not change.
    - `5D ago` (value 5): header "Previous (5D ago)"
    - `10D ago` (value 10): header "Previous (10D ago)"
    - `1M ago` (value 21): header "Previous (1M ago)"
  - **Headers (multi-sort)** (`#rotB th[data-k]`, sort headers): v2 shared sort ("Sector" key now sn, Sector ↑ = A → Z); "Sorted by … · Clear sort" moved from the subtitle to the legend.
    - `Sector`
    - `Current quadrant`
    - `Previous (…)`
    - `Speed`
    - `Last change`
  - **Clear sort (replaces Reset)** (`#rotB .lgd .mss .rsr`, link button in legend): Clears all sort levels (shown when ≥ 2 levels).
  - **Rows** (`#rotB tbody tr[data-n]`, rows (title "Click to highlight in the RRG · Ctrl/Cmd-click to add")): Click: highlight in RRG + lock; Ctrl/Cmd-click: add/remove; footer "N highlighted in the RRG · Clear".
  - **Clear** (`#rotB .clr`, link button in footer): Clears the highlight (lock stays).
- **Footer / legend**: "Click a sector to highlight it in the RRG (Ctrl/Cmd-click to add) · Speed = distance moved in 5 sessions"
- **Expand window** — detail table "Quadrant changes" ("361 changes in 52 weeks"):
  - Columns: Week ending · Sector · From · To · Path (Clockwise / Skipped / reversed)
  - Default sort: Week ending ↓
  - Row click: locks the sector
  - Window controls: v2: the card copy's legend (with the "Clear" highlight link) is hidden inside the window
  - Note: "How to read · Each row = a week in which a sector moved to another RRG quadrant. Clockwise = the usual Lagging → Improving → Leading → Weakening order. Example · In the week ending 17 Nov, Basic Mat. moved from Improving to Lagging: not the usual order (it skipped or went back)."
- **Data notes**: Real data (RRG computed in the page).
- **Defects observed**:
  - NEW: with Previous = 10D/1M ago the subtitle says "speed = RRG distance moved in 10/21 sessions" but Speed stays the 5-session value (footer still says 5).
  - Still: Clear (highlight) leaves the sector locked.
- **Screenshots**: tab-rot_card-rotB_previous-1M.png, tab-rot_full_multi-select.png, tab-rot_card-rotB_expand-window.png

### 7.4 <Sector> · stock momentum quadrant (default "Infra · stock momentum quadrant") (`#rotC`)

- **Subtitle**: "Dot = stock · across = 1M − IHSG, up = 5D − IHSG (pp) · size = value (Sector index: "1M − Infra index …")"
- **Chart type**: bubble scatter with 4 quadrants
- **What it plots**:
  - x_axis: "1M vs IHSG →": stock 1M return − benchmark 1M return (pp)
  - y_axis: "5D vs IHSG →" written vertically along the y-axis (v2): stock 5D return − benchmark 5D return (pp)
  - size: 20-day average traded value
  - colour: green = 5D above benchmark, red = below
  - labels: 8 largest stocks labelled; v2: unlabelled dots get no ring (footer "· point at a dot for names not shown")
  - quadrants: LEADING, WEAKENING, LAGGING, IMPROVING
  - axis range: clamped to the 2nd–98th percentile (outliers drawn at the edge)
- **Defaults**: sector = locked sector, else Infra; Relative to IHSG
- **Controls**:
  - **Relative to** (`#rotbm button[data-v]`, segmented (label "Relative to"), default IHSG): Benchmark for both axes.
    - `IHSG` (value ih): legend "Leading 5 · Improving 20 · Weakening 3 · Lagging 26" (Infra)
    - `Sector index` (value sec): subtitle "1M × 5D vs Infra index · 54 stocks"; legend "Leading 17 · Improving 12 · Weakening 15 · Lagging 10"
  - **Bubbles** (`#rotC circle.dt`, hover + click): Tooltip "TLKM · Improving / … / Avg value 20D Rp 489.5B". v2: click selects the stock (white-ringed dot, halo, bold 12 px label); click it again to deselect.
  - **Sector** (`(lock from any card)`, follows lock): e.g. "Financials · stock momentum quadrant · 99 stocks".
- **Footer / legend**: "Leading n · Improving n · Weakening n · Lagging n" | "Size = trading value · green = 5D above IHSG" (+ "· N labels hidden (ring)")
- **Expand window** — detail table "<Sector> · stocks by quadrant" ("vs IHSG"):
  - Columns: Ticker · Subsector · 1M vs bench (pp) · 5D vs bench (pp) · Quadrant · Avg value
  - Default sort: 1M vs bench ↓
  - Row click: rings and labels the stock on the window chart (v2: the other dots are no longer muted)
  - Sector select: 11 sectors
  - Search: Search stock
  - Window controls: v2: the card legend (quadrant counts) is hidden inside the window
  - Note: "How to read · Across = 1M return − benchmark, up = 5D return − benchmark (pp). Leading = ahead on both; Improving = behind on 1M but ahead on 5D. Example · BSWD is +220.50 pp vs the benchmark over 1M but −31.17 pp over 5D → Weakening."
- **Data notes**: Real data: one-day stock snapshot (r1m, r5d, size) and sector/IHSG closes.
- **Defects observed**:
  - Still: outliers clamped to the axis edge without a marker (BSWD +220.5 pp).
- **Screenshots**: tab-rot_card-rotC_bench-Sector.png, tab-rot_card-rotC_stock-selected.png, tab-rot_card-rotC_expand-window.png, tab-rot_card-rotC_window-stock-marked.png

## 8. Tab: Pair Matrix

Layout: Sector Pair Matrix (top-left, wide) | Pair Ratio; Beta & Correlation (bottom-left, wide) | Stretched Pairs. Hidden in markup: "Sector × Sector" (#pmA) and pair detail (#pmB).

Tab screenshots: tab-pm_full.png, mobile390_tab-pm.png

### 8.1 Sector Pair Matrix (`#pmM`)

- **Subtitle**: "Return row − return column, 1M (pp) · green = row ahead · click a cell to open the pair"
- **Chart type**: matrix heatmap 11 × 11 (diagonal "—")
- **What it plots**:
  - Spread mode: cell = row sector return − column sector return over the period (pp, 1 decimal); green/red scaled by the largest |value|
  - Correlation mode: cell = correlation of daily returns over the window (2 decimals, shown with "+"); navy intensity; subtitle "Correlation of daily returns, 60D · darker = moves together"
  - order: rows and columns ordered by sector return over the period ↓; column headers abbreviated: Fin, NonCyc, Indus, Trans, Cyc, Health, Prop, Energy, Infra, Basic, Tech
  - selection: row name of pair A highlighted, row of B greyed/disabled; selected cell outlined; v2: cells of the rows other than A are dimmed (.32)
- **Defaults**: Spread, 1M (19 Oct – 17 Nov); correlation window 60D; pair at load = largest |z| of the 60-session ratio (Cons. Cyc / Basic Mat.)
- **Controls**:
  - **Mode** (`#pqm button[data-v]`, segmented, default Spread): Switches the cell measure and the second control.
    - `Spread` (value sp): period control shown
    - `Correlation` (value co): window control shown; legend "1.00 = identical daily moves · 0 = unrelated …"; range "26 Aug – 17 Nov" for 60D
  - **Period (Spread)** (`#pqp button[data-v]`, segmented, default 1M): Spread period; reorders rows/columns.
    - `5D` (value 5): 10 Nov – 17 Nov
    - `1M` (value 21): 19 Oct – 17 Nov
    - `3M` (value 63): 19 Aug – 17 Nov
    - `Custom` (value C): From/To popover; tested 2026-09-01..2026-10-31 → subtitle "… 1 Sep–30 Oct (pp)"; kept when switching back from Correlation
  - **Window (Correlation)** (`#pqw button[data-v]`, segmented, default 60D): Correlation window.
    - `20D` (value 20): 21 Oct – 17 Nov
    - `60D` (value 60): 26 Aug – 17 Nov
    - `120D` (value 120): 26 May – 17 Nov
  - **Column headers** (`#pmM .hd[data-c]`, buttons): v2 shared sort: sort rows by that column (title "Sort rows by <sector> · Click to sort …"), first click high → low ↓, again ↑, third off; several columns add levels (legend "Sorted by … · Clear sort"); the column's own sector goes last.
  - **Row names** (`#pmM .nm`, buttons): Click: make that sector A of the pair (B kept). The B row is disabled (title "Health is already B in Pair Ratio").
  - **Cells** (`#pmM .c[data-a]`, buttons): Hover: tooltip "Non-Cyc / Health / Spread 1M +5.08 pp / Corr 60D 0.80 / Click to open in Pair Ratio". Click: pair A = row, B = column → Pair Ratio, Beta A/B badges and Stretched Pairs selection update. Diagonal: no action.
- **Footer / legend**: "Value = row return − column return (pp), not a ratio · rows and columns ordered by sector return · click column names to sort rows (each adds a level)" | date range
- **Expand window** — detail table "All 55 pairs" ("1M · leader first"):
  - Columns: Pair (ahead / behind) · Spread (pp) · Ahead (return) · Behind (return) · Corr 60D
  - Default sort: Spread ↓
  - Row click: selects the pair in the window's matrix (the page pair is unchanged — the window has its own filters) — new in v2
  - Search: "Search sector or pair" (e.g. "Tech" → 10 rows)
  - Note: "How to read · Spread = return of the sector ahead − return of the sector behind over the matrix period (pp). Corr near 1 = the two move together. Example · Financials returned +9.4% and Technology −10.5%, …"
- **Data notes**: Real data: sector closes.
- **Defects observed**:
  - Correlations are printed with a "+" sign (e.g. "+0.82").
- **Screenshots**: tab-pm_full.png, tab-pm_card-pmM_mode-Correlation.png, tab-pm_card-pmM_colsort.png, tab-pm_card-pmM_expand-window.png

### 8.2 <A> / <B> (default "Cons. Cyc / Basic Mat.") (`#pmR`)

- **Subtitle**: "A ÷ B, start = 100 · line up = A ahead"
- **Chart type**: line chart with moving average and ±2σ band (Bollinger-style) + 2 KPI boxes
- **What it plots**:
  - line: ratio A/B rebased to 100 at the period start (navy)
  - ma: moving average of the ratio (MA20 or MA50, grey dashed)
  - band: MA ± 2 standard deviations over the same MA window (shaded)
  - markers: green dots above the band, red dots below; end dot
  - kpis: "Spread <period> (A − B)" = A return − B return over the period (pp); "Band position" = "Above upper band · stretched" / "Below lower band · stretched" / "Inside band · NN% of width"
- **Defaults**: Period 6M (13 May – 17 Nov), MA 50
- **Controls**:
  - **Period** (`#prp button[data-v]`, segmented, default 6M): Chart range and Spread KPI period.
    - `3M` (value 63): 19 Aug – 17 Nov; "Spread 3M (A − B)"
    - `6M` (value 126): 13 May – 17 Nov
    - `1Y` (value 250): legend "3 Nov – 17 Nov" (= 3 Nov 2025 – 17 Nov 2026)
    - `Custom` (value C): From/To popover; start moved to at least MA sessions after data start: 2025-09-01..2026-03-31 → "3 Nov – 31 Mar", KPI "Spread period (A − B)"
  - **Sector A** (`#prA`, select): Sets A; picking the current B swaps A and B (e.g. A = Health when B = Health → "Health / Financials").
    - `Basic Mat.`
    - `Cons. Cyc`
    - `Non-Cyc`
    - `Energy`
    - `Financials`
    - `Health`
    - `Industrials`
    - `Infra`
    - `Property`
    - `Tech`
    - `Transport`
  - **Swap** (`#pmR .sw (⇄, title "Swap A and B")`, button): Swaps A and B (e.g. "Transport / Tech").
  - **Sector B** (`#prB`, select): Sets B; picking the current A swaps them.
    - `Basic Mat.`
    - `Cons. Cyc`
    - `Non-Cyc`
    - `Energy`
    - `Financials`
    - `Health`
    - `Industrials`
    - `Infra`
    - `Property`
    - `Tech`
    - `Transport`
  - **MA** (`#prm button[data-v]`, segmented (label "MA"), default 50): MA length for the dashed line and band; changes Band position (e.g. MA20 → "Inside band · 89% of width").
    - `20` (value 20): MA20
    - `50` (value 50): MA50
  - **Chart hover** (`#pmR .pmc`, hover): Crosshair; tooltip "Transport / Tech · 4 Sep / Ratio 88.4 · MA50 86.8 / Band 81.6 – 91.9 / Transport −14.8% · Tech −3.7%". v2: date tag on the x-axis (e.g. "Tue 5 May '26").
- **Footer / legend**: legend "A / B (start = 100)", "MA50", "±2σ band" | date range
- **Expand window** — detail table "<A> / <B> · daily log" ("Last 60 sessions · MA50 band"):
  - Columns: Date · <A> (1D %) · <B> (1D %) · Spread (pp) · Cum. spread (pp, from period start) · vs MA50 (%) · Band (σ)
  - Default sort: Date ↓
  - Row click: marks that date on the window chart (vertical + horizontal guide, dot, dark date label, ratio value); click again to clear — new in v2
  - Window controls: own period, A/B selects, swap, MA
  - Note: "How to read · Spread = A daily return − B daily return. Ratio = A ÷ B rebased to 100. Band beyond ±2σ = the ratio is unusually stretched from its MA. Example · …"
- **Data notes**: Real data: sector closes.
- **Defects observed**:
  - Still: 1Y legend "3 Nov – 17 Nov" without years.
  - Still: custom start moved to 3 Nov without a message.
- **Screenshots**: tab-pm_card-pmR_period-1Y.png, tab-pm_card-pmR_MA20.png, tab-pm_card-pmR_hover-datetag.png, tab-pm_card-pmR_expand-window.png, tab-pm_card-pmR_window-date-marked.png

### 8.3 Beta & Correlation to IHSG (or "… to LQ45") (`#pmT`)

- **Subtitle**: "β = sector move per 1% IHSG move, from 120D daily returns · Corr = how closely they move (custom: "from custom daily returns"; LQ45: "per 1% LQ45 move")"
- **Chart type**: table with inline bar
- **What it plots**:
  - columns:
    - Sector (A / B badges)
    - Beta <N>D (daily returns vs benchmark; bar with a dashed line at beta 1.0; navy ≥ 1, grey < 1)
    - Δ Beta (beta now − beta over the previous window of the same length; red = more sensitive)
    - Corr (daily returns)
    - Return (sector over the window)
    - vs <bench> (pp)
    - Alpha (= return − beta × benchmark return, pp)
- **Defaults**: Window 120D (25 May – 17 Nov), vs IHSG, sort Beta ↓
- **Controls**:
  - **Window** (`#btw button[data-v]`, segmented (label "Window"), default 120D): Beta/corr window; header "Beta <N>D".
    - `20D` (value 20): 20 Oct – 17 Nov, IHSG +0.5%
    - `60D` (value 60): 24 Aug – 17 Nov, IHSG −18.4%
    - `120D` (value 120): 25 May – 17 Nov, IHSG −14.5%
    - `250D` (value 250): 31 Oct – 17 Nov (= 2025–2026), IHSG −35.0%
    - `Custom` (value C): From/To popover; 2026-03-01..2026-06-30 → "Beta 73D", "2 Mar – 30 Jun"
  - **vs** (`#btb button[data-v]`, segmented (label "vs"), default IHSG): Benchmark.
    - `IHSG` (value IHSG): title "Beta & Correlation to IHSG"
    - `LQ45` (value LQ45): title "… to LQ45", column "vs LQ45", "LQ45 −13.0% in the window"
  - **Headers (multi-sort)** (`#pmT th[data-k]`, sort headers): v2 shared sort; default Beta ↓ shown faint; Sector ↑ = A → Z.
    - `Sector`
    - `Beta`
    - `Δ Beta`
    - `Corr`
    - `Return`
    - `vs <bench>`
    - `Alpha`
  - **Clear sort (replaces Reset)** (`#pmT .lgd .mss .rsr`, link button in legend): Clears all sort levels (shown when ≥ 2 levels).
  - **Rows** (`#pmT tbody tr[data-n] (title "Click to make <sector> sector A of the pair")`, rows): Click: that sector becomes A (Pair Ratio and matrix follow) and is locked; clicking the current A toggles the lock.
- **Footer / legend**: "A / B = the pair in Pair Ratio · click a row to make it A · Dashed line = beta 1.0 · Δ Beta red = more sensitive than before · IHSG −14.5% in the window" | range
- **Expand window** — detail table "<A> · stocks" ("β 120D vs IHSG · sector β 1.30 · click a sector row to change"):
  - Columns: Ticker · Subsector · β · Corr · 1M · 1M vs IHSG (pp) · Avg value
  - Default sort: β ↓
  - Search: Search stock
  - Note: "How to read · β = how much the stock moves per 1% move in the benchmark. Corr near 1 = it moves closely with the benchmark. Example · … (window stock β/corr still illustrative)"
- **Data notes**: Sector rows: real (sector, IHSG and LQ45 closes). Window stock β and Corr: ILLUSTRATIVE (seeded around the sector β).
- **Defects observed**:
  - Still: 250D legend "31 Oct – 17 Nov" without years.
  - New: the v2 subtitle is cut off at 1440 px (full text on hover).
- **Screenshots**: tab-pm_card-pmT_bench-LQ45.png, tab-pm_card-pmT_expand-window.png

### 8.4 Stretched Pairs (`#pmS`)

- **Subtitle**: "Pairs ranked by return gap, first − second sector over 1M (pp) (follows Rank by: 3D / 1W / 1M)"
- **Chart type**: table (ranked list of sector pairs)
- **What it plots**:
  - rows: the 55 sector pairs, A/B in the fixed sector-list order (e.g. "Basic Mat. / Financials")
  - columns:
    - Pair (A / B)
    - Spread 3D
    - Spread 1W
    - Spread 1M (each = A return − B return over the horizon, pp; rank column tinted)
- **Defaults**: Rank by 1M, Both, Top 7
- **Controls**:
  - **Rank by** (`#sth button[data-v]`, segmented (label "Rank by"), default 1M): Sorts by |spread| at that horizon (resets the sort).
    - `3D` (value 3): top: Basic Mat. / Tech −4.7 pp
    - `1W` (value 5): top: Basic Mat. / Transport −8.0 pp
    - `1M` (value 21): top: Financials / Tech +19.9 pp
  - **Direction filter** (`#stf button[data-v]`, segmented, default Both): Filters by sign of the ranked spread.
    - `Both` (value all): "Top 7 of 55"
    - `A ahead` (value up): spread > 0: "Top 7 of 30"
    - `A behind` (value dn): spread < 0: "Top 7 of 25"
  - **Show** (`#stn button[data-v]`, segmented (label "Show"), default Top 7): Row count.
    - `Top 7` (value 7): 7 rows
    - `All` (value all): "55 pairs"
  - **Headers (multi-sort)** (`#pmS th[data-k]`, sort headers): v2 shared sort (default |spread| ↓ has no column, so no faint arrow); Pair ↑ = A → Z.
    - `Pair (A / B)`
    - `Spread 3D`
    - `Spread 1W`
    - `Spread 1M`
  - **Clear sort (replaces Reset)** (`#pmS .lgd .mss .rsr`, link button in legend): Clears all sort levels; clickable with 3 levels (verified).
  - **Rows** (`#pmS tbody tr (title "Click to open in Pair Ratio")`, rows): Click: opens the pair in Pair Ratio (A/B as listed); row selected.
- **Footer / legend**: "Top 7 of 55 · spread = A − B (pp)" | "17 Nov"
- **Expand window** — detail table "Spread across horizons" ("All 55 pairs · first − second (pp)"):
  - Columns: Pair · 1D · 3D · 1W · 2W · 1M · 3M · |1M|
  - Default sort: |1M| ↓
  - Row click: selects the pair in the window — new in v2
  - Note: "How to read · Each column = first sector return − second sector return over that horizon (pp). Same sign across = a steady gap; a sign flip = the gap is turning. Example · …"
- **Data notes**: Real data: sector closes.
- **Defects observed**:
  - Fixed: Clear sort is in the legend and works with 3 levels.
  - Still: "A ahead / A behind" depends on the fixed pair orientation.
  - New: the v2 subtitle is cut off at 1440 px (full text on hover).
- **Screenshots**: tab-pm_card-pmS_3-level-sort.png, tab-pm_card-pmS_expand-window.png

## 9. Tab: Breadth

Layout: Breadth vs Price | Breadth Heatmap Table; Breadth by sector | Advancers · Unchanged · Decliners | Stock detail. One selection (IHSG or one sector) drives all five cards. Hidden in markup: "% Above Moving Average", "Quality of the move", "Breadth history".

Tab screenshots: tab-br_full.png, tab-br_full_selected-Energy.png, mobile390_tab-br.png

### 9.1 Breadth vs Price (`#brH`)

- **Subtitle**: "% of all stocks closing above their EMA50 · IHSG price on the right"
- **Chart type**: dual-axis line chart (breadth % left, IHSG price right) with zones, zoom and pan
- **What it plots**:
  - main line: % of stocks above EMA50 (or EMA200) for the selection (black)
  - compare lines: up to 4 more sectors/IHSG (navy, red, amber, violet)
  - price: IHSG close, dashed grey, right axis ("IHSG price (right)")
  - zones: green ≥ 70%, red ≤ 30%
  - headline: "19% above EMA50 today · +6.6 pp vs 5 sessions"
  - y_left: 0–100%
  - x: dates (4 labels)
- **Defaults**: Show = IHSG (all stocks), % above EMA50, period 6M (13 May – 17 Nov · 127 sessions)
- **Controls**:
  - **Show** (`#brH .bms → popover .bxp`, button + checkbox list): Popover "Show up to 5 lines · N of 5": checkboxes IHSG (all stocks) + 11 sectors; main line tagged "Main"; other checked lines have a "make main" button; when 5 are checked the rest are disabled; unchecking the main promotes the first compare line (or IHSG). The main line is the Breadth tab selection (subtitle "% of Energy stocks above EMA50", Stock detail, heatmap, dots and A/U/D follow). Button label "IHSG (all stocks) +N". Escape or outside click closes.
    - `IHSG (all stocks)`
    - `Basic Mat.`
    - `Cons. Cyc`
    - `Non-Cyc`
    - `Energy`
    - `Financials`
    - `Health`
    - `Industrials`
    - `Infra`
    - `Property`
    - `Tech`
    - `Transport`
  - **% above** (`#bhm button[data-v]`, segmented (label "% above"), default EMA50): Breadth measure; also switches Stock detail Status to that EMA and its sort to "200 ↓".
    - `EMA50` (value ema50): 19% today
    - `EMA200` (value ema200): "18% above EMA200 today · +2.5 pp"; Stock detail "149 of 833 above EMA200"
  - **Period** (`#bhp button[data-v]`, segmented (label "Period"), default 6M): Visible range.
    - `3M` (value 63): 19 Aug – 17 Nov · 64 sessions
    - `6M` (value 126): 13 May – 17 Nov · 127 sessions
    - `1Y` (value 250): 31 Oct 2025 – 17 Nov 2026 · 251 sessions
    - `Custom` (value C): From/To popover; 2026-02-01..2026-05-31 → "2 Feb – 29 May · 72 sessions"
  - **Wheel / drag / keys** (`#brH .bz`, zoom + pan): Wheel zooms around the pointer (min 20 sessions; 3 notches in → "3 Jul – 22 Oct · 78 sessions", period buttons lose their highlight); drag pans ("5 Jun – 25 Sep"); + / − zoom and ← / → pan when focused.
  - **Chart hover** (`#brH .bz`, hover): Crosshair, date tag on the x-axis (v2), tooltip "Wed 26 Aug / 53.1% above EMA50 / IHSG 6,405.69 · −4.7% since 13 May"; with a sector as main line v2 shows both: "Energy 3,230.9 · −5.3% since 13 May · - - IHSG 6,501.67".
  - **Legend buttons (new in v2)** (`#brH .bhx .bxl`, toggle buttons): One button per line: main line ("IHSG" / sector, title "<name>: 19.3% above EMA50 today · click to hide"), each compare line, and "IHSG price (right)" (title "IHSG index level, right axis · click to hide"). Click hides/shows that line (label struck through when hidden).
- **Footer / legend**: "Green zone ≥ 70% · red zone ≤ 30% · scroll to zoom, drag to move" | "13 May – 17 Nov · 127 sessions"
- **Expand window** — detail table "<IHSG | Sector> · daily log" ("Last 60 sessions · % above EMA50"):
  - Columns: Date · Close (IHSG or sector index) · 1D · % > EMA50 · Δ 1D (pp) · Δ 5D (pp)
  - Default sort: Date ↓
  - Row click: marks that date on the window chart (guides + value) — new in v2
  - Sector select: IHSG (all stocks) + 11 sectors
  - Note: "How to read · Share of stocks closing above their moving average; 70% or more = strong, 30% or less = weak. Δ = change in percentage points. Example · …"
- **Data notes**: IHSG (all stocks) breadth: real recorded series (above_ema50 / above_ema200, 300 sessions). Sector breadth lines: ILLUSTRATIVE (code: "sector breadth history is dummy, built from the sector index vs its own EMA and pinned to today's value"); only the latest point matches real stock flags.
- **Defects observed**:
  - Fixed (D12): the price line is now labelled "IHSG price (right)" in subtitle and legend, can be hidden, and the tooltip gives both values.
  - New: subtitle wraps to 3 lines next to the controls.
- **Screenshots**: tab-br_full.png, tab-br_card-brH_EMA200.png, tab-br_card-brH_zoomed.png, tab-br_card-brH_legend-price-hidden.png, tab-br_card-brH_sector-main-hover.png, tab-br_card-brH_show-popover.png, tab-br_card-brH_show-5-lines.png, tab-br_card-brH_expand-window.png, tab-br_card-brH_window-date-marked.png

### 9.2 Breadth Heatmap Table (`#brT`)

- **Subtitle**: "% of stocks up 1D/1W/1M, above EMA50/200 · green ≥ 50%"
- **Chart type**: heatmap table
- **What it plots**:
  - rows: "IHSG (all)" (always first) + 11 sectors
  - columns:
    - Sector
    - Stocks (count)
    - Up 1D
    - Up 1W
    - Up 1M (% of stocks with a positive return)
    - > EMA50
    - > EMA200 (% of stocks above)
    - Δ EMA50 1W (pp change of % above EMA50 over 5 sessions)
  - colour: green > 50%, red < 50%, intensity by distance from 50; Δ column by size of change
- **Defaults**: Show %, sorted by > EMA50 ↓
- **Controls**:
  - **Show** (`#btc button[data-v]`, segmented (label "Show"), default %): Cell text.
    - `%` (value pct): e.g. "51%"
    - `Stock count` (value cnt): e.g. "50/99"
  - **Headers** (`#brT th[data-k] (Sector key now sn)`, sort headers (shared multi-level sort)): v2 shared sort; default > EMA50 ↓ faint; Sector ↑ = A → Z; "Sorted by … · Clear sort" in the legend; IHSG row stays first.
    - `Sector`
    - `Stocks`
    - `Up 1D`
    - `Up 1W`
    - `Up 1M`
    - `> EMA50`
    - `> EMA200`
    - `Δ EMA50 1W`
  - **Cells** (`#brT td.hc[data-tip]`, hover): Tooltip "46 of 99 stocks · 46.5%".
  - **Rows** (`#brT tbody tr[data-n]`, rows): Click: make that sector the Breadth selection (all Breadth cards follow; also locks it app-wide); click the selected row or "IHSG (all)" to go back to IHSG. v2: the other sector rows are dimmed while a sector is selected.
- **Footer / legend**: "Hover a cell for the stock count · Δ = change in % above EMA50 over 1 week" | "17 Nov"
- **Expand window** — detail table "Breadth change" (% of stocks above EMA50 and EMA200, now and change):
  - Columns: Sector (incl. IHSG) · > EMA50 · Δ 1W · Δ 1M · > EMA200 · Δ 1W · Δ 1M
  - Default sort: Δ 1W ↓
  - Row click: selects the sector in the window (new in v2); added "Δ …" columns are sortable
  - Window controls: "+ Column" button: popover "Change in % of stocks above" with EMA20 / EMA50 / EMA200 × 3D / 1W / 1M (EMA50 1W disabled, "Already shown"); each checked box adds a "Δ EMA20 3D"-style column to the window copy
  - Note: "How to read · > EMA50 / > EMA200 = share of the sector’s stocks closing above that average; Δ = change in percentage points over 1W and 1M. Example · …"
- **Data notes**: Up/>EMA columns: real (stock snapshot flags and returns). Δ EMA50 1W and window Δ columns: real for IHSG, ILLUSTRATIVE for sectors (dummy sector breadth history); EMA20 breadth illustrative everywhere.
- **Defects observed**:
  - New: in the window the card copy (756 px table) is wider than its 498 px pane → horizontal scroll.
- **Screenshots**: tab-br_card-brT_count.png, tab-br_full_selected-Energy.png, tab-br_card-brT_expand-window.png, tab-br_card-brT_window-added-columns.png

### 9.3 Breadth by sector (`#brA`)

- **Subtitle**: "% of the sector's stocks above their EMA50 today"
- **Chart type**: dot / lollipop plot (0–100%)
- **What it plots**:
  - rows: 11 sectors sorted ↓
  - value: share of the sector's stocks meeting the measure (%), dot green ≥ 50% else red, value at right
  - axis: 0%, 50%, 100%
- **Defaults**: Measure % > EMA50
- **Controls**:
  - **Measure** (`#brm button[data-v]`, segmented (label "Measure"), default % > EMA50): Changes the measure and subtitle.
    - `% > EMA50` (value ema): Financials 26% … Infra 9%
    - `% > IHSG 5D` (value ihsg): subtitle "% of the sector's stocks with 5D return above IHSG (+3.49%)"; Tech 68% … Basic Mat. 30%
    - `% > 0% 5D` (value pos): subtitle "% of the sector's stocks with a positive 5D return"; Tech 76% … Basic Mat. 63%
  - **Rows** (`#brA .dots .r[data-n]`, rows): Hover: tooltip "Industrials / 13 of 56 stocks · 23.2% / above their EMA50". Click: Breadth selection (as heatmap rows); again → IHSG.
- **Footer / legend**: "Green dot = more than half the stocks · hover a row for the stock count"
- **Expand window** — detail table "<IHSG | Sector> · stocks" ("161 of 833 above EMA50 · 149 above EMA200"):
  - Columns: Ticker · > EMA50 (Above/Below) · > EMA200 (Above/Below) · vs EMA50 (%) · 1M
  - Default sort: vs EMA50 ↓
  - Search: Search stock
  - Note: "How to read · > EMA50 / > EMA200 = the stock closes above that average; vs EMA50 = how far the close is from it. Example · BTPS closes +12.1% from its EMA50, so it is above it."
- **Data notes**: Real: stock flags/returns. Window "vs EMA50" distance: ILLUSTRATIVE.
- **Defects observed**:
  - Still: axis labels 0% / 50% / 100% struck through by the axis line.
- **Screenshots**: tab-br_card-brA_measure-ihsg.png, tab-br_card-brA_axis.png, tab-br_card-brA_expand-window.png

### 9.4 Advancers · Unchanged · Decliners (`#brN`)

- **Subtitle**: "Stocks up, flat and down over 1D · sorted by share up"
- **Chart type**: 100% stacked horizontal bars
- **What it plots**:
  - rows: "IHSG (all)" + 11 sectors sorted by share up
  - segments: up (green) / unchanged (grey) / down (red) stock counts; count printed when the segment ≥ 7%
  - right label: up / total (e.g. "333/833")
  - reference: dashed line at 50%
- **Defaults**: Period 1D
- **Controls**:
  - **Period** (`#adh button[data-v]`, segmented (label "Period"), default 1D): Return horizon for up/flat/down.
    - `1D` (value r1d): IHSG (all) 333 / 169 / 331
    - `1W` (value r5d): IHSG (all) 568 up / 63 / 202
    - `1M` (value r1m): IHSG (all) 315 up / 476 down
  - **Rows** (`#brN .adr > div[data-n]`, rows): Hover: tooltip "Tech · 1D / Up 20 · Flat 7 · Down 14 of 41"; segment title "333 stocks". Click: Breadth selection; "IHSG (all)" row → back to IHSG.
- **Footer / legend**: legend "Up", "Unchanged", "Down", "dashed line = 50%" | "17 Nov"
- **Expand window** — detail table "<IHSG | Sector> · stocks 1D" ("333 advancing · 169 unchanged · 331 declining"):
  - Columns: Ticker · Status (Adv / Dec / Unch) · Close · Change 1D · Volume
  - Default sort: Change 1D ↓
  - Search: Search stock
  - Note: "How to read · Status = the stock’s move over the chosen period: Adv = up, Unch = flat, Dec = down. Close and volume are illustrative. Example · …"
- **Data notes**: Counts: real (r1d/r5d/r1m of the stock snapshot; a missing return counts as unchanged). Window Close and Volume: ILLUSTRATIVE, although a real close per stock exists in the recorded day file (day.stocks.close).
- **Defects observed**:
  - Still: title and subtitle truncated at 1440 px.
  - Still: dashed 50% line over the count labels.
- **Screenshots**: tab-br_card-brN_period-1M.png, tab-br_card-brN_header.png, tab-br_card-brN_expand-window.png

### 9.5 Stock detail (`#brD`)

- **Subtitle**: "Close vs EMAs · IHSG (all stocks): 161 of 833 above EMA50"
- **Chart type**: table (all stocks of the selection; scrolls)
- **What it plots**:
  - columns:
    - Ticker
    - Status (Above / Below EMA50, or EMA200 when "% above" = EMA200)
    - Distance from EMA: 20 / 50 / 200 (close vs EMA, %)
    - Days (sessions in the current status)
    - Since (date the status began)
- **Defaults**: Status All, sorted by 50 ↓
- **Controls**:
  - **Status** (`#bdf button[data-v]`, segmented (label "Status"), default All): Row filter.
    - `All` (value all): 833 rows
    - `Above` (value up): 161 rows
    - `Below` (value dn): 672 rows
  - **Headers** (`#brD th[data-k]`, sort headers (shared multi-level sort)): v2 shared sort; default 50 ↓ faint (200 ↓ when % above = EMA200); Ticker ↑ = A → Z; legend "Sorted by Status ↓, then EMA20 ↓ · Clear sort". The Status header lost its "Above or below EMA50" tip (it now shows the generic sort help).
    - `Ticker`
    - `Status`
    - `20`
    - `50`
    - `200`
    - `Days`
    - `Since`
  - **Rows** (`#brD tbody tr[data-t]`, hover): Tooltip "BELI · PT Global Digital Niaga Tbk / Tech / Below EMA50 for 75 sessions, since 3 Aug / Close vs EMA20 −1.9% · EMA50 −7.3% · EMA200 −18.5%". Click does nothing.
- **Footer / legend**: "Distance = close vs EMA · Status uses EMA50" | "17 Nov"
- **Expand window**: Window auto-sized to 560×852 (v1 820×660); no side table; adds a "Search stock" box ("BB" → "11 of 833 shown · 17 Nov").
- **Data notes**: Status Above/Below: real flags. Distances (20/50/200), Days and Since: ILLUSTRATIVE (seeded, signed to agree with the flags).
- **Defects observed**: none.
- **Screenshots**: tab-br_card-brD_row-hover.png, tab-br_card-brD_expand-window.png

## 10. In the code or markup but not shown

| Id | Title | How hidden | Content |
|---|---|---|---|
| `snCard` | Sector Snapshot | style display:none | tiles IHSG + 11 sectors: 1D return, 1M, 63-session sparkline; click pins. |
| `.sx-grid (spb)` | Sector Performance | hidden attribute | cumulative return vs IHSG; Period 20D / 60D / YTD / 1Y / Custom (Custom ignored by the handler). |
| `.sx-grid (stc)` | Sector stocks | hidden attribute | Top 5D / Bottom 5D table: Stock, 5D vs IHSG, 1M, > EMA50, Foreign 5D, Value / day; "Export CSV" (#csv) and "All N stocks" (#allst) buttons have no click handler. The only consumer of foreign-flow data. |
| `#mkS` | Market map horizon summary | CSS display:none !important | Sector 1D / 5D / 1M / 3M / YTD and vs IHSG pp row. |
| `rsC` | Acceleration and streak | CSS #rsC{display:none} | 3D vs IHSG, 10D vs IHSG, Acceleration (pp/session = 3D/3 − 10D/10), Sessions above IHSG, Rank (N D), Rank change 5D. |
| `pmA` | Sector × Sector | wrapper display:none | cell = row − column N-D return; colour = 5D z-score vs the pair's last 250 sessions; "Cell text" 3D / 5D / 10D. |
| `pmB` | <A> vs <B> (pair detail) | wrapper display:none | Difference 3D/5D/10D, Z-score 5D, Correlation 60D, ratio vs 20-session mean cross, 60-session ratio chart. |
| `brM` | % Above Moving Average | style display:none | > EMA20 / > EMA50 / > EMA200 / Stocks; Liquidity All / ≥ Rp 1B / ≥ Rp 10B. Note: its "> EMA20" is actually the share with a positive 1M return. |
| `brC` | Quality of the move | wrapper display:none | top-3 contributor share of the 5D move; chip "Divergence not recorded" (BR-05). |
| `brB` | Breadth history | wrapper display:none | all stocks % above EMA50, 250 sessions, thrust detection; chip "Sector history not recorded". |
| `#rotn` | (Rotation) seg handler | no markup | handler for a non-existent control. |
| `brT tag` | Breadth tags | computed, never rendered | Distribution? / Recovery / Overbought / Oversold. |
| `.fw-pin` | Window pin button | CSS display:none !important (v2) | pin logic still in code; windows can no longer survive a tab switch. |

## 11. Phone width (390 × 844)

v2: unchanged — no responsive layout (same single max-width:1200px media query); measurements identical to v1 except the market map content (scrollWidth 492 in a 224 px card). The EDGE shell shows its mobile top bar (menu, EDGE, search, theme, avatar); header actions stack; the tab bar wraps over 3 lines with the meta text mixed in.

- **ov**: KPI tiles squeezed to ~70 px (labels cut, e.g. "IHSG…", "Beatin…"); Momentum card 128 px wide (axes overlap); Sector × Horizon cells unreadable; market map 224 px.
- **rs**: Left-column cards (Sector Drill-down, "· stocks", Weekly Excess Return) collapse to 2 px wide (invisible); Rank change and Relative Return stay 500 px and overflow (view scrollWidth 540).
- **rot**: Relative Rotation Graph and Direction & speed collapse to 2 px (invisible); Rotation detail and stock quadrant stay 690 px (view scrollWidth 730).
- **pm**: Sector Pair Matrix and Beta table collapse to 2 px (invisible); Pair Ratio and Stretched Pairs stay 500 px (overflow).
- **br**: Five cards squeezed to 103–163 px: heatmap columns unreadable, chart squeezed, titles truncated.

Screenshots: mobile390_tab-ov.png, mobile390_tab-rs.png, mobile390_tab-rot.png, mobile390_tab-pm.png, mobile390_tab-br.png

## 12. Defects of the first version: status in v2

| Id | v1 defect (where) | Status in v2 | Detail | Evidence |
|---|---|---|---|---|
| D01 | No mobile layout: on Relative Strength, Rotation and Pair Matrix the left-column cards collapse to 2 px (invisible) and the right-column cards overflow sideways; Overview and Breadth cards are squeezed to unreadable widths. (All tabs @390 px) | **still** | Same at 390 px: RS/Rotation/Pair Matrix left-column cards 2 px wide, right-column cards 500–690 px (view scrollWidth 540/730/540). | audit_v2/raw/mobile.json; mobile390_tab-*.png |
| D02 | Illustrative (dummy) values are drawn next to real ones; only window footnotes or code comments say so. Must be replaced by real per-stock price history / per-sector breadth history. (Relative Strength · Sector "· stocks"; Breadth · Breadth vs Price (sector lines), Heatmap Δ, Stock detail distances/days; windows of Beta (stock β/corr), A/U/D (close/volume), Breadth by sector (vs EMA50)) | **still** | Illustrative values unchanged (code comments "Design phase: … dummy" for stock paths and sector breadth history; window notes; A/U/D How to read: "Close and volume are illustrative"). | v2/logic.js rsL/brSeries/brDum/fwdPMT/fwdBRN |
| D03 | Subtitle "Click a sector to see its stocks" — click only locks the sector; subsector rows never open. (Relative Strength · Sector Drill-down) | **still (wording changed)** | Clicking a sector still only locks it, subsector rows never open (open set always empty) — the v2 subtitle now even says "… per sector and subsector". | #rsD; audit_v2/raw/rs.json "subRows": 0 |
| D04 | Reset link in the subtitle is clipped and unclickable once 3 sort levels are active. (Pair Matrix · Stretched Pairs) | **fixed** | "Reset" left the subtitle; "Clear sort" sits in the legend and works with 3 levels. | #pmS .lgd .mss .rsr; tab-pm_card-pmS_3-level-sort.png |
| D05 | 11 tiles in a 684 px card: 4 tiles hidden behind horizontal scroll at 1440 px; subtitle truncated. (Rotation · Direction & speed) | **partly fixed** | Still 7 of 11 tiles visible (1060 px in 684 px) and the subtitle is still cut, but a hover now shows the full subtitle. | #rotD .cmp; defect_probe.json D05 |
| D06 | Line tooltip is hidden in the same mousemove whenever the hovered line changes (document mousemove handler sees a detached target after the re-render). (Overview · Cumulative Return) | **still** | Line tooltip hidden after 4 of 4 moves in a dense area. | audit_v2/raw/ov.json "Line hover dense area" |
| D07 | X and Y may be the same horizon (diagonal, meaningless); quadrant label dropped; zero line runs through quadrant labels at default. (Overview · Momentum) | **still** | 3M vs 3M allowed; 3 quadrant labels at 1M vs 1M; zero line through "UP ON BOTH"/"TURNING DOWN". | tab-ov_card-mm_y-3M-same-as-x.png; tab-ov_full.png |
| D08 | Tiles not clickable; map keeps the last locked sector after unlock; tiny subsectors get no tile; horizon summary strip hidden by CSS. (Overview · Market map) | **still** | Tiles not clickable; map keeps last locked sector; Alternative Energy Equipment 0 tiles; #mkS hidden (subsector pick-out added in the window only). | audit_v2/raw/ov.json |
| D09 | Custom range over 26 weeks is cut silently (2 Jan → 7 May). (Relative Strength · Weekly Excess Return) | **still** | Custom 2 Jan–17 Nov → "26 weeks · 7 May – 17 Nov". | audit_v2/raw/rs.json |
| D10 | Custom start moved forward to leave room for the MA (2025-09-01 → 3 Nov) without a message. (Pair Matrix · Pair Ratio) | **still** | Custom 2025-09-01..2026-03-31 → "3 Nov – 31 Mar", no message. | audit_v2/raw/pm.json |
| D11 | Date ranges spanning two years are printed without years ("24 Oct – 17 Nov", "3 Nov – 17 Nov", "31 Oct – 17 Nov"). (Rotation (axis, subtitle), Pair Ratio 1Y, Beta 250D) | **partly fixed** | Axes, subtitles and legends still without year (Timeline "24 Oct – 17 Nov", Pair Ratio 1Y "3 Nov – 17 Nov", Beta 250D "31 Oct – 17 Nov"); the new hover date tag shows the year ("Fri 24 Oct '25"). | defect_probe.json D11, ihTag |
| D12 | With a sector as main line, the price line is still IHSG while the tooltip shows the sector index. (Breadth · Breadth vs Price) | **fixed** | Subtitle "… · IHSG price on the right", legend button "IHSG price (right)", tooltip shows sector and IHSG values, price line can be hidden. | tab-br_card-brH_sector-main-hover.png; defect_probe.json D12 |
| D13 | Title and subtitle truncated; 50% line overlaps the count labels. (Breadth · A/U/D) | **still** | A/U/D title and subtitle truncated; 50% line through "169". | tab-br_card-brN_header.png; defect_probe.json D13 |
| D14 | Axis labels 0% / 50% / 100% struck through by the axis line. (Breadth · Breadth by sector) | **still** | Axis labels still struck through. | tab-br_card-brA_axis.png |
| D15 | Right-hand detail table wider than its 492 px panel at the default size: last columns cut off until the window is resized or scrolled. (Expand windows (Sector × Horizon, Market map, "· stocks", RRG, stock quadrant, Beta, Stretched Pairs)) | **fixed** | Windows are sized to their content: no detail column cut off in any of the 20 windows at 1440×900. | defect_probe.json win.*.clipped = [] |
| D16 | Clearing the highlight does not clear the lock; there is no visible lock indicator anywhere. (Rotation · Direction & speed / Rotation detail) | **partly fixed** | RRG/timeline one-click selection clears selection and lock together, and the lock is now visible in more cards (halos, dimming); tile click and "Clear" still leave the lock. | audit_v2/raw/rot.json; tab-rot_full_rotpick.png |
| D17 | Sort arrows inconsistent: "Sector ↓" sorts A→Z (Drill-down, Rotation detail, Beta), "Ticker ↑" sorts A→Z (Stock detail). (Several tables) | **fixed** | Shared sort: ↑ = A → Z / low → high and ↓ = descending in every table (Sector ↑, Ticker ↑). | audit_v2/raw/{rs,rot,pm,br}.json |
| D18 | First IHSG week tooltip "1 week 0.00%" (no prior week). (Rotation · RRG) | **still** | First-week tooltip "1 week 0.00%". | defect_probe.json D18 |
| D19 | "A ahead/behind" relies on fixed pair orientation; ranking is by spread only, not by a stretch measure. (Pair Matrix · Stretched Pairs) | **partly fixed** | Subtitle now says "Pairs ranked by return gap, first − second sector over 1M (pp)"; "A ahead/behind" still follows fixed pair order. | audit_v2/raw/pm.json |
| D20 | Date menu offers only the latest close; Open in Screener shows "not available in this prototype"; "Broker data to Mon 9 Nov" pill but no visible card uses broker data. (Header) | **still** | Header unchanged (one date, Screener toast, broker pill unused). | hdr_*.png |
| D21 | Popover counts 64 trading days for the 63-session 3M range; footer says "show or hide" but lines are only greyed. (Overview · Cumulative Return) | **still** | "64 trading days"; legend off still draws the grey line (label now struck through). | audit_v2/raw/ov.json |

## 13. New defects in v2

| Id | Severity | Where | Defect | Evidence |
|---|---|---|---|---|
| N01 | medium | Rotation · Rotation detail | With Previous = 10D/1M ago the subtitle says "speed = RRG distance moved in 10/21 sessions" but the Speed column keeps the 5-session values (Tech 11.66 in all three) and the footer still says "5 sessions". | #rotB; defect_probe.json N1; tab-rot_card-rotB_previous-1M.png |
| N02 | low | Floating windows | Auto-sized windows cascade +28 px per window opened in the session even when alone: the 3rd opened Sector Drill-down / Stock detail window ends 4 px below the viewport and the Market map window 4 px past the right edge (border and part of the header cut). | defect_probe.json win rsD#2, brD#2, mkCard#2; tab-ov_card-mk_window-subsector-picked.png |
| N03 | low | Floating windows | Backdrop click closes the top window, so with the mouse only one window can be open; the 3-window limit/toast and the pin logic remain in code but are unreachable (pin button hidden by CSS). | audit_v2/raw/ov.json; css .fw-pin{display:none!important} |
| N04 | low | Overview · Cumulative Return | The new IHSG legend toggle is not saved: after reload IHSG is shown again while period/axes/sort/legend selection are restored. | audit_v2/raw/ov.json "Persistence after reload" |
| N05 | low | Breadth · Heatmap window | The card copy table (756 px) is wider than its 498 px pane → horizontal scroll inside the window. | defect_probe.json win brT#0 bodyTbl |
| N06 | low | Pair Matrix · Beta & Stretched Pairs; Breadth · Breadth vs Price | New subtitles do not fit at 1440 px: Beta and Stretched Pairs cut with an ellipsis (full text only on hover); Breadth vs Price wraps to 3 lines. | defect_probe.json trunc; tab-pm_full.png; tab-br_full.png |
| N07 | low | Weekly Excess Return, Stretched Pairs, Sector × Horizon | Default orders use a measure with no column (20-session excess, absolute spread), so no default arrow is shown; the sector header cell of the heatmaps is blank (only an arrow when sorted). | tab-rs_card-rsW_sorted-2-levels.png |
| N08 | low | Rotation · windows | Inside the Rotation detail and stock-quadrant windows the card legend is hidden by CSS, so the "Clear" highlight link and the quadrant counts are not available there. | css .fw [data-fwid="rotC"] .lgd,.fw [data-fwid="rotB"] .lgd{display:none!important} |

## 14. Screenshot list (88)

hdr_datebtn_open.png, hdr_scrbtn_toast.png, mobile390_tab-br.png, mobile390_tab-ov.png, mobile390_tab-pm.png, mobile390_tab-rot.png, mobile390_tab-rs.png, ov_window-backdrop-howtoread.png, ov_windows-max3-toast.png, tab-br_card-brA_axis.png, tab-br_card-brA_expand-window.png, tab-br_card-brA_measure-ihsg.png, tab-br_card-brD_expand-window.png, tab-br_card-brD_row-hover.png, tab-br_card-brH_EMA200.png, tab-br_card-brH_expand-window.png, tab-br_card-brH_legend-price-hidden.png, tab-br_card-brH_sector-main-hover.png, tab-br_card-brH_show-5-lines.png, tab-br_card-brH_show-popover.png, tab-br_card-brH_window-date-marked.png, tab-br_card-brH_zoomed.png, tab-br_card-brN_expand-window.png, tab-br_card-brN_header.png, tab-br_card-brN_period-1M.png, tab-br_card-brT_count.png, tab-br_card-brT_expand-window.png, tab-br_card-brT_window-added-columns.png, tab-br_full.png, tab-br_full_selected-Energy.png, tab-ov_card-hx_expand-window.png, tab-ov_card-hx_multisort.png, tab-ov_card-hx_row-pin.png, tab-ov_card-mk_window-subsector-picked.png, tab-ov_card-mm_dot-pinned.png, tab-ov_card-mm_expand-window.png, tab-ov_card-mm_x-1W.png, tab-ov_card-mm_y-3M-same-as-x.png, tab-ov_card-rc_expand-window.png, tab-ov_card-rc_ihsg-off.png, tab-ov_card-rc_legend-BasicMat-on.png, tab-ov_card-rc_line-hover.png, tab-ov_card-rc_period-YTD.png, tab-ov_full.png, tab-ov_full_pinned-Energy.png, tab-pm_card-pmM_colsort.png, tab-pm_card-pmM_expand-window.png, tab-pm_card-pmM_mode-Correlation.png, tab-pm_card-pmR_MA20.png, tab-pm_card-pmR_expand-window.png, tab-pm_card-pmR_hover-datetag.png, tab-pm_card-pmR_period-1Y.png, tab-pm_card-pmR_window-date-marked.png, tab-pm_card-pmS_3-level-sort.png, tab-pm_card-pmS_expand-window.png, tab-pm_card-pmT_bench-LQ45.png, tab-pm_card-pmT_expand-window.png, tab-pm_full.png, tab-rot_card-rotA_date-moved.png, tab-rot_card-rotA_dot-hover.png, tab-rot_card-rotA_expand-window.png, tab-rot_card-rotA_ihsg-off.png, tab-rot_card-rotA_tail-12W.png, tab-rot_card-rotA_view-Timeline.png, tab-rot_card-rotB_expand-window.png, tab-rot_card-rotB_previous-1M.png, tab-rot_card-rotC_bench-Sector.png, tab-rot_card-rotC_expand-window.png, tab-rot_card-rotC_stock-selected.png, tab-rot_card-rotC_window-stock-marked.png, tab-rot_card-rotD_multi.png, tab-rot_full.png, tab-rot_full_locked-Energy.png, tab-rot_full_multi-select.png, tab-rot_full_rotpick.png, tab-rs_card-rsA_expand-window.png, tab-rs_card-rsB_compare-1M.png, tab-rs_card-rsB_expand-window.png, tab-rs_card-rsD_expand-window.png, tab-rs_card-rsD_sort-RRG.png, tab-rs_card-rsL_hover.png, tab-rs_card-rsL_window-row-highlight.png, tab-rs_card-rsW_custom-long.png, tab-rs_card-rsW_expand-window.png, tab-rs_card-rsW_sorted-2-levels.png, tab-rs_card-rsW_weeks-4W.png, tab-rs_full.png, tab-rs_full_locked-Energy.png
