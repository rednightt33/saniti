# Sector Analysis — changes from the first version (v1) to the FINAL version (v2)

Audit date 2026-11-26. v1 = `scratchpad/sector/src.html`, v2 = `scratchpad/sector/v2/src.html`; same data (window.SX). Every item below was verified in the browser (raw logs in `audit_v2/raw/`); the styling items (focus rings, hidden pin button, legends hidden in Rotation windows, removed dimming) were read in `v2/css.css` and the window sizing/backdrop in `v2/logic.js`. Screenshots are in `audit_v2/`.

## 1. What did not change

- Header (title, pills, date menu with only the latest close, Open in Screener toast), tabs, KPI row: identical.
- Cards, their order and layout, every segmented control, select and option (periods, windows, horizons, benchmarks): identical.
- All figures (same data, same formulas); illustrative values in the same places.
- Hidden cards: identical (Sector Snapshot, Sector Performance, Sector stocks, market-map horizon strip, Acceleration and streak, Sector × Sector, pair detail, % Above Moving Average, Quality of the move, Breadth history).
- Phone width: identical (no responsive layout).

## 2. Changed or new on every tab

| Area | v1 | v2 |
|---|---|---|
| Sorting | Single-column sort in most tables; 3-level sort only in Rotation detail, Beta and Stretched Pairs with "Reset" in the subtitle; arrow meaning differed by table (Sector ↓ = A→Z, Ticker ↑ = A→Z). | One shared multi-level sort on every sortable table/heatmap and window table (up to 3 levels; again = reverse; third click removes); default order marked by a faint arrow; "Sorted by … · Clear sort" in the legend when ≥ 2 levels; ↑ = ascending / A→Z, ↓ = descending everywhere; header tooltip explains the clicks. New sortable: Weekly Excess Return (sector and each week). |
| Lock / selection visibility | Only Rank change and the RRG muted the other sectors; no page-level indicator. | Also: halo + bigger dot (Momentum, RRG head), dimmed other rows/cells (Sector × Horizon, Weekly heatmap, Pair Matrix, Breadth heatmap), bold row. Still no page-level indicator. |
| Rotation selection | RRG dot = lock/unlock; highlights from Rotation detail stayed. | One-click selection on RRG dots and timeline rows: replaces highlighted sectors with the clicked one; clicking the only selected one again clears selection and lock. |
| Line-chart hover | Crosshair + tooltip. | Plus a dark date tag on the x-axis with weekday and year ("Mon 16 Nov '26") on Cumulative Return, "· stocks", RRG IHSG strip, Pair Ratio, Breadth vs Price. |
| Floating windows | 1180×660 fixed; pin button; up to 3 windows; page usable behind; no footer help. | Auto-sized to content (cascade +28 px); dark backdrop, click outside closes (one window at a time with the mouse); pin button hidden → all windows close on tab switch; "How to read · … Example · …" footer built from the first row; more clickable detail rows; detail columns no longer cut off. |
| Window row clicks (new) | Only some windows had clickable rows. | Cumulative Return, Momentum, Sector × Horizon → lock sector; Market map → pick out subsector on the map; Pair Matrix and Stretched Pairs → select pair (in the window); Pair Ratio and Breadth vs Price → mark that date on the chart; Breadth heatmap → select sector. |
| Subtitles | Short or "how to click" texts. | Rewritten as definitions (list below); a cut-off subtitle shows its full text on hover. |
| Axis titles | Y-axis titles horizontal inside the plot. | Momentum, RRG and stock quadrant: y-axis title written vertically along the axis, x-axis title centred below. |
| Focus / inputs | Blue focus rings. | Grey focus rings; no focus ring on inputs/selects. |

## 3. Card by card

### Overview · Cumulative Return

- Legend restyled: text + square swatch, off = struck through.
- New IHSG toggle "--- IHSG" (title "Click to hide/show IHSG") hides the IHSG line and label; not saved on reload.
- Hover date tag.
- Window: rows lock the sector; How to read; 1375×629.

### Overview · Momentum

- Y title vertical ("Return 1M →"), X title centred.
- Locked dot bigger with halo.
- Window rows lock the sector; How to read.

### Overview · Sector × Horizon

- Shared multi-level sort (keys sn, h0…h6), legend "Sorted by … · Clear sort", faint default 1M ↓; levels saved locally.
- Lock dims other rows, bolds the name.
- Window rows lock; How to read; Avg rank column no longer cut.

### Overview · Market map

- Subtitle "Grouped by subsector" → "Tile size = 20D avg trading value · colour = 5D return − IHSG · grouped by subsector".
- Window: click a subsector row to pick it out on the map (others dimmed); How to read; Leader columns no longer cut.

### Relative Strength · Sector Drill-down

- Subtitle "Click a sector to see its stocks · click a column to sort" → "Return, return vs IHSG and RS rating (1–99 rank of 1M vs IHSG) per sector and subsector".
- Shared sort (Sector ↑ = A→Z, default RS ↓ faint).
- Window How to read; 872×852 stacked.

### Relative Strength · Rank change

- Window How to read only (dimming of the other lines when locked already existed in v1).

### Relative Strength · Relative Return

- Subtitle "… , last 5 sessions" → "… over the last 5 sessions (pp)"; Absolute: "Sector index return over the last 5 sessions · dashed line = IHSG".
- Window How to read.

### Relative Strength · "· stocks"

- Subtitle "Top 10 by trading value, cumulative" → "Return since 19 Aug · top 10 traded" (follows the period).
- Hover date tag; window How to read.

### Relative Strength · Weekly Excess Return

- Subtitle → "Sector − IHSG return per 5-day week (pp)".
- NEW sortable headers (sector name and each week, 3 levels, Clear sort); default order still 20-session excess.
- Lock dims other rows; window How to read.

### Rotation · RRG

- Subtitle "vs IHSG · 17 Nov (latest) · tail 4W" → "RS-Ratio × RS-Mom vs IHSG · 17 Nov · tail 4W"; Timeline "Quadrant each week · …" → "RRG quadrant of each sector per week · …".
- Vertical RS-Momentum axis title, wider margins, all 11 labels drawn (v1 hid 1), no dark rings; footer "Click a dot to pin the sector · hover for values" ("… · hover a dot for names not shown" when labels are hidden).
- Locked head: halo + bigger dot; timeline locked-row outline removed.
- One-click selection (rotPick).
- IHSG strip date tag with year; window How to read, 1352×683.

### Rotation · Direction & speed

- Selected tile: darker border; unselected tiles no longer dimmed.
- Full subtitle on hover.

### Rotation · Rotation detail

- Subtitle "Click headers to sort · each click adds a level" → "Quadrant now vs 5D ago · speed = RRG distance moved in 5 sessions" (follows Previous, see new defect N01).
- "Reset" → "Clear sort" in the legend; shared sort.
- Window: card legend hidden; How to read.

### Rotation · Stock momentum quadrant

- Subtitle "1M × 5D vs IHSG · 54 stocks" → "Dot = stock · across = 1M − IHSG, up = 5D − IHSG (pp) · size = value".
- NEW: click a dot to select the stock (ring, halo, bold label), again to clear; no rings for unlabelled dots; footer "· point at a dot for names not shown".
- Vertical y title, x baseline + ticks.
- Window: row click rings the stock but others are no longer muted; legend hidden; How to read.

### Pair Matrix · Sector Pair Matrix

- Column headers: shared multi-level sort (was single), legend "click column names to sort rows (each adds a level)" + Clear sort.
- Non-A rows dimmed.
- Window: rows select the pair (window); How to read.

### Pair Matrix · Pair Ratio

- Subtitle "Pair Ratio · line up = A ahead of B" → "A ÷ B, start = 100 · line up = A ahead".
- Hover date tag.
- Window: click a date to mark it on the chart; How to read.

### Pair Matrix · Beta & Correlation

- Subtitle "Sorted by Beta ↓ · Reset" → "β = sector move per 1% IHSG move, from 120D daily returns · Corr = how closely they move".
- Reset → Clear sort in legend; default Beta ↓ faint.
- Window How to read.

### Pair Matrix · Stretched Pairs

- Subtitle "Sorted by |Spread 1M| ↓ · Reset" → "Pairs ranked by return gap, first − second sector over 1M (pp)".
- Reset → Clear sort in legend (now clickable).
- Window rows select the pair; How to read.

### Breadth · Breadth vs Price

- Subtitle "% of all stocks above EMA50" → "% of all stocks closing above their EMA50 · IHSG price on the right".
- NEW legend buttons hide/show each line and the IHSG price line.
- Tooltip with a sector shows sector and IHSG values; hover date tag.
- Window: click a date to mark it; How to read.

### Breadth · Heatmap Table

- Subtitle → "% of stocks up 1D/1W/1M, above EMA50/200 · green ≥ 50%".
- Shared sort (Sector ↑, default > EMA50 ↓ faint); other rows dimmed when a sector is selected.
- Window: rows select the sector, added Δ columns sortable; How to read.

### Breadth · Breadth by sector / A·U·D

- Window How to read only.

### Breadth · Stock detail

- Subtitle "IHSG (all stocks) · 161 of 833 above EMA50" → "Close vs EMAs · IHSG (all stocks): 161 of 833 above EMA50".
- Shared sort (Ticker ↑ = A→Z, default 50 ↓ faint); Status header lost its "Above or below EMA50" tip.
- Window 560×852.

## 4. Removed

- Window pin button (hidden by CSS; windows always close on tab switch).
- "Reset" links in the subtitles of Rotation detail, Beta & Correlation and Stretched Pairs (replaced by "Clear sort" in the legend).
- Dark rings marking hidden labels (RRG, Momentum, stock quadrant).
- Outline around the locked row in the RRG Timeline; dimming of unselected Direction & speed tiles; muting of other dots when a stock is picked in the stock-quadrant window.
- "(latest)" in the RRG subtitle; header titles of the Weekly heatmap week columns now prefix the sort help.

## 5. Defects of v1: status in v2

Counts: 13 still, 4 fixed, 4 partly fixed (of 21).

| Id | v1 defect | Status | Detail | Evidence |
|---|---|---|---|---|
| D01 | No mobile layout: on Relative Strength, Rotation and Pair Matrix the left-column cards collapse to 2 px (invisible) and the right-column cards overflow sideways; Overview and Breadth cards are squeezed to unreadable widths. | **still** | Same at 390 px: RS/Rotation/Pair Matrix left-column cards 2 px wide, right-column cards 500–690 px (view scrollWidth 540/730/540). | audit_v2/raw/mobile.json; mobile390_tab-*.png |
| D02 | Illustrative (dummy) values are drawn next to real ones; only window footnotes or code comments say so. Must be replaced by real per-stock price history / per-sector breadth history. | **still** | Illustrative values unchanged (code comments "Design phase: … dummy" for stock paths and sector breadth history; window notes; A/U/D How to read: "Close and volume are illustrative"). | v2/logic.js rsL/brSeries/brDum/fwdPMT/fwdBRN |
| D03 | Subtitle "Click a sector to see its stocks" — click only locks the sector; subsector rows never open. | **still (wording changed)** | Clicking a sector still only locks it, subsector rows never open (open set always empty) — the v2 subtitle now even says "… per sector and subsector". | #rsD; audit_v2/raw/rs.json "subRows": 0 |
| D04 | Reset link in the subtitle is clipped and unclickable once 3 sort levels are active. | **fixed** | "Reset" left the subtitle; "Clear sort" sits in the legend and works with 3 levels. | #pmS .lgd .mss .rsr; tab-pm_card-pmS_3-level-sort.png |
| D05 | 11 tiles in a 684 px card: 4 tiles hidden behind horizontal scroll at 1440 px; subtitle truncated. | **partly fixed** | Still 7 of 11 tiles visible (1060 px in 684 px) and the subtitle is still cut, but a hover now shows the full subtitle. | #rotD .cmp; defect_probe.json D05 |
| D06 | Line tooltip is hidden in the same mousemove whenever the hovered line changes (document mousemove handler sees a detached target after the re-render). | **still** | Line tooltip hidden after 4 of 4 moves in a dense area. | audit_v2/raw/ov.json "Line hover dense area" |
| D07 | X and Y may be the same horizon (diagonal, meaningless); quadrant label dropped; zero line runs through quadrant labels at default. | **still** | 3M vs 3M allowed; 3 quadrant labels at 1M vs 1M; zero line through "UP ON BOTH"/"TURNING DOWN". | tab-ov_card-mm_y-3M-same-as-x.png; tab-ov_full.png |
| D08 | Tiles not clickable; map keeps the last locked sector after unlock; tiny subsectors get no tile; horizon summary strip hidden by CSS. | **still** | Tiles not clickable; map keeps last locked sector; Alternative Energy Equipment 0 tiles; #mkS hidden (subsector pick-out added in the window only). | audit_v2/raw/ov.json |
| D09 | Custom range over 26 weeks is cut silently (2 Jan → 7 May). | **still** | Custom 2 Jan–17 Nov → "26 weeks · 7 May – 17 Nov". | audit_v2/raw/rs.json |
| D10 | Custom start moved forward to leave room for the MA (2025-09-01 → 3 Nov) without a message. | **still** | Custom 2025-09-01..2026-03-31 → "3 Nov – 31 Mar", no message. | audit_v2/raw/pm.json |
| D11 | Date ranges spanning two years are printed without years ("24 Oct – 17 Nov", "3 Nov – 17 Nov", "31 Oct – 17 Nov"). | **partly fixed** | Axes, subtitles and legends still without year (Timeline "24 Oct – 17 Nov", Pair Ratio 1Y "3 Nov – 17 Nov", Beta 250D "31 Oct – 17 Nov"); the new hover date tag shows the year ("Fri 24 Oct '25"). | defect_probe.json D11, ihTag |
| D12 | With a sector as main line, the price line is still IHSG while the tooltip shows the sector index. | **fixed** | Subtitle "… · IHSG price on the right", legend button "IHSG price (right)", tooltip shows sector and IHSG values, price line can be hidden. | tab-br_card-brH_sector-main-hover.png; defect_probe.json D12 |
| D13 | Title and subtitle truncated; 50% line overlaps the count labels. | **still** | A/U/D title and subtitle truncated; 50% line through "169". | tab-br_card-brN_header.png; defect_probe.json D13 |
| D14 | Axis labels 0% / 50% / 100% struck through by the axis line. | **still** | Axis labels still struck through. | tab-br_card-brA_axis.png |
| D15 | Right-hand detail table wider than its 492 px panel at the default size: last columns cut off until the window is resized or scrolled. | **fixed** | Windows are sized to their content: no detail column cut off in any of the 20 windows at 1440×900. | defect_probe.json win.*.clipped = [] |
| D16 | Clearing the highlight does not clear the lock; there is no visible lock indicator anywhere. | **partly fixed** | RRG/timeline one-click selection clears selection and lock together, and the lock is now visible in more cards (halos, dimming); tile click and "Clear" still leave the lock. | audit_v2/raw/rot.json; tab-rot_full_rotpick.png |
| D17 | Sort arrows inconsistent: "Sector ↓" sorts A→Z (Drill-down, Rotation detail, Beta), "Ticker ↑" sorts A→Z (Stock detail). | **fixed** | Shared sort: ↑ = A → Z / low → high and ↓ = descending in every table (Sector ↑, Ticker ↑). | audit_v2/raw/{rs,rot,pm,br}.json |
| D18 | First IHSG week tooltip "1 week 0.00%" (no prior week). | **still** | First-week tooltip "1 week 0.00%". | defect_probe.json D18 |
| D19 | "A ahead/behind" relies on fixed pair orientation; ranking is by spread only, not by a stretch measure. | **partly fixed** | Subtitle now says "Pairs ranked by return gap, first − second sector over 1M (pp)"; "A ahead/behind" still follows fixed pair order. | audit_v2/raw/pm.json |
| D20 | Date menu offers only the latest close; Open in Screener shows "not available in this prototype"; "Broker data to Mon 9 Nov" pill but no visible card uses broker data. | **still** | Header unchanged (one date, Screener toast, broker pill unused). | hdr_*.png |
| D21 | Popover counts 64 trading days for the 63-session 3M range; footer says "show or hide" but lines are only greyed. | **still** | "64 trading days"; legend off still draws the grey line (label now struck through). | audit_v2/raw/ov.json |

## 6. New defects in v2

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
