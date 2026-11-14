# EDGE Radar: page specification for the static HTML build

**Purpose of this file:** hand the Radar page to another AI or developer so they can produce the static HTML that becomes
the live front end. It describes what is on the page, how every control behaves, the states, the visual rules and the
data the page receives. The reference prototype is [`index-r10.html`](index-r10.html) in this folder (open it in a browser;
routes `#/radar` and `#/filter/S1`). Where this file and the prototype differ, this file wins.

**Status:** design approved by the user on 2026-11-12 to 2026-11-14 (`PLAN.md` RADAR). Not built. The data contract in
section 7 is the proposal of the implementation plan (`EXEC.md` EXEC-RADAR) and may change there.

**Who uses it:** the owner (admin). The rules of each filter are shown on purpose; a separate version for normal users,
with the rules hidden, comes later (user 2026-11-14: "Ini adalah menu admin (which owner) nanti kita buat lagi saja
khusus untuk user normal").

**Language:** every label is English (EDGE rule, 2026-10-19).

---

## 1. What the page answers

"Which stocks did the screener library find on the last data day, which filters found them, and why?" Results are
candidates to study, never buy or sell signals. The page says this under its title.

## 2. Where it lives

- A new page of EDGE with its own item in the left rail (56 px rail of the EDGE shell), placed after Screener:
  Monitor, Terminal, Backtest, Screener, **Radar**. Tooltip "Radar".
- Rail icon (24 × 24 view box, stroke 1.7, round caps and joins, no fill, drawn at 22 px):
  ```svg
  <path d="M4 4a16 16 0 0 1 16 16"/><path d="M4 10.5a9.5 9.5 0 0 1 9.5 9.5"/><path d="M4 20 13 11"/>
  <circle cx="16.3" cy="8.2" r="1.3"/><circle cx="4" cy="20" r=".6"/>
  ```
- Like Terminal, Backtest and Screener, the page is its own app shown in the shell's frame. The rail in the prototype is
  a preview of the shell only; the page itself starts at the content area.

## 3. Board (route `#/radar`)

### 3.1 Header
- Title "Radar". Sub-line: "Stocks picked up by the screener library, and which filters found them. Candidates to study,
  not buy or sell signals."
- Right side:
  - **Data pills**, one per source with the last date it holds: "Prices to Thu 12 Nov" (neutral) and "Broker data to Mon 9 Nov"
    (amber when it is behind the prices). Tooltip: results use the last date both sources have.
  - **Date button** "Results for Mon 9 Nov ▾": menu of the dates that have results ("Mon 9 Nov · after close" …); only
    dates with a published result are enabled.

### 3.2 Control bar (one card, one row on desktop)
| Control | Options | Default | Behaviour |
|---|---|---|---|
| Universe | All stocks · Index (LQ45, IDX30, IDX80, KOMPAS100, JII, …) · Group (Danantara, Salim, Sinarmas, Astra, Bakrie, Djarum, MNC, …) | All stocks | Narrows the stocks shown. It does not recompute anything: ranks across stocks (S2, S3) stay computed on every stock that passed the gate. The menu says so in a note. Lists come from `Stock_List` (current members). |
| Gate | Broad · Liquid | Broad | Broad drops the 50% of stocks with the smallest total buying over 5 sessions; Liquid drops 80%. Beside it, muted: the day's rupiah cut-off, e.g. "≥ Rp 1.85B / 5 days". Tooltips explain each. |
| Level | Loose · Standard · Strict | Standard | Changes the thresholds of every filter except S8, which has its own levels (its column says "own levels" when Level is not Standard). |
| Show | All hits · New today · In 2+ filters | All hits | New today = stocks whose run in that filter started on the result date. In 2+ filters = stocks also found by another filter. |
| Search | text | empty | Filters cards by ticker or company name. Esc clears. |

Selected option of every segmented control: **ink fill, surface text** (black with white text in light theme; inverted
in dark theme). User 2026-11-14.

### 3.3 Columns
Seven columns, in this order: **S1, S2, S3, S6, S6Δ, S7, S8**. Each column is a card:

- **Head** (a button that opens the filter detail):
  - id (S1 …) top left; English name under it;
  - top right: the **count** as dots, one dot per stock up to 10, then "+N", then the number (option 8, user
    2026-11-14). Zero: no dots, the number in grey;
  - a 20-session bar sparkline of the daily count; all bars grey, **today's bar in ink** (black);
  - right of the sparkline: "+3 vs yday" (green up, red down) when all controls are at their defaults; "filtered" when
    any control narrows the view; "own levels" for S8 when Level is not Standard.
- **Body:** one card per stock, ordered by the filter's own sort key (section 5). **The column is as tall as its cards**;
  a column taller than the screen stops at the screen height and scrolls inside (user 2026-11-14).
- **Empty column:** the body says why, in this order of cause: "No match for this search." · "None in <universe> today." ·
  "None with this view." · "None pass at the <level> level."
- **All columns empty:** below the columns, a box "No stocks match these settings. Try All stocks, the Broad gate or the
  Loose level." with a "Reset settings" button.

### 3.4 Stock card
```
TICKER                     +0.55%      ← ticker bold; 1D change green/red/ink for 0
[New|Day N] [+N] [Outlier] [Watch]  ⟋⟍⟋   ← tags left, 20-session price line right
```
- **New** (blue tag) when the stock entered the filter on the result date; otherwise **Day N** (grey tag) = consecutive
  sessions in the filter, counting today.
- **+N** (grey) = number of other filters that found the stock; tooltip lists them.
- **Outlier** (amber) when the stock's figure is driven by one event; tooltip gives the reason (e.g. "One-day block:
  Rp 61.8B of the foreign net came on 28 Oct").
- **Watch** (grey, S8 only) = large and unusual, but not in the top 5% of its own history.
- **Price line**: 20 sessions of closes, 46 × 16 px, green if up over the 20 sessions, red if down. It wraps to the next
  line when the tags fill the card.
- The whole card is a button that opens the filter detail with that stock selected.

## 4. Filter detail (route `#/filter/<id>?s=<TICKER>`)

- **Back link** "‹ Radar". Title "S6 · Foreign accumulation (5D)"; sub-line: the filter's question (section 5).
  Right: data pills and **Follow** (shows "Coming soon").
- **"How to read it"** note (one line card): the filter's reading warning (section 5). S8 adds that it has its own levels.
- **Stocks found per day** (wide card): bars = number of stocks in the filter per session over the last 250 sessions
  (left axis), line = IHSG (right axis). Selecting a bar (click, or ← → keys) shows that day's members in the Today card.
- **Today in <id>** (side card): entered / stayed (average days) / left; "Left" chips with the letter of the condition that
  stopped being met; "Most overlap" with another filter; the members of the selected day as ticker chips (new today in
  blue; on past days, members no longer in the filter are struck through). Clicking a chip selects that stock.
- **Candidates** (table card):
  - header: count text "13 stocks meet all 3 · 2 near misses · Standard · Broad gate"; S6Δ only: "Change in: Ratio ·
    Rank · Both"; search; compact Universe button; "Sort: By <own key> · New first";
  - a legend row of the conditions with their letters and current thresholds (admin page: rules are visible);
  - columns: Stock (ticker + name) · Conditions (A–D squares, filled = met) · 1D · the filter's own columns (section 5) ·
    In radar (New/Day N, Outlier) · Also in (tags of the other filters);
  - **Near misses** below a separator row: stocks that meet all conditions but one, greyed, tag "Near miss";
  - rows are focusable; Enter/Space selects; ↑ ↓ move.
- **Preview** (side card, selected stock): ticker, name, last price and 1D; Outlier note when flagged; "When <id> found it"
  with a 3M · 6M · 1Y switch: price line with shaded spans on the days the filter held the stock, a bar strip of those
  spans, "N days found · M runs", the last three runs ("Active · day 1" for the current one); button
  **"Open <TICKER> in Terminal"** (stores the ticker for the Terminal and asks the shell to switch page).
- No CSV export. No backtest summary. No "Why it is here" block (all removed by the user on 2026-11-14).

## 5. The filters (what each column means)

Thresholds are Loose / **Standard** / Strict. Gate and the universe G2 apply to all. Full definitions and evidence:
`SCREENER_LIBRARY.md` (sections 2, 3, 9, 11, 12, 13).

| Id | Name | Question | Conditions (Standard) | Sort | Own columns |
|---|---|---|---|---|---|
| S1 | Heavy foreign accumulation | Foreign net buying over 5 sessions that is unusually large for this stock | A foreign net 5D > 0 · B foreign net ≥ 5% of buying · C ≥ P95 of its own 252 values (Loose P90; Strict P95 and z ≥ 2) · D net buying on ≥ 3 of 5 days | z-score | Foreign 5D · of buying · vs own 1Y · z · Buy days |
| S2 | Strengthening foreign flow | Foreign ratio that rose most against the 5 sessions before, across stocks | A foreign net 5D > 0 · B ratio change > 0 · C change in the top 10% of gated stocks (Loose 25%, Strict 5%) | change | Foreign 5D · Ratio now · 5 sessions ago · Change · Rank |
| S3 | Concentrated net buying | Net buying held by a few brokers, against stocks with a similar number of net buyers | A ≥ 10 net buyers · B CR3 − 3/k ≥ P80 in its group of k (P70/P90) · C intensity ≥ P75 (P60/P90) | average of the two ranks | Net buyers · Top 3 − even · Group rank · Intensity · Rank · Foreign 5D |
| S6 | Foreign accumulation (5D) | Foreign net buying that is a large share of all buying and high for the stock's own year | A foreign net 5D > 0 · B foreign ratio ≥ 5% (3/10) · C ratio ≥ P95 of its own 252 values (P90/P98) | foreign ratio | Foreign 5D · Ratio · vs own 1Y · Buy days |
| S6Δ | Foreign accumulation, strengthening | Stocks in S6 whose ratio, or its rank in the own year, rose against 5 sessions ago | S6's A–C · D by "Change in": Ratio up ≥ 20 pt (12/35) · Rank up ≥ 65 pt (40/90) · Both. Thresholds proposed, not decided | the chosen change | Ratio · Ratio change · vs own 1Y · Rank change · Foreign 5D |
| S7 | Institutions in, retail out | Institutional brokers turned net buyers while retail brokers sold, against 5 sessions ago | A FL34 up ≥ 20 pt vs 5 sessions ago (10/40) · B FL34 now ≥ 0 · C institutional net > 0 · D institutional side ≥ 5% of buying | FL34 now | FL34 before · FL34 now · Change · Institutional net · of buying |
| S8 | One-day foreign buying spike | One session of foreign net buying far above the stock's usual day | A robust z ≥ 3 on the foreign ratio or on net vs ADV20 · B net ≥ 10% of ADV20 · C net ≥ P95 of its own 252 days. Strong = A+B+C; Watch = A+B without C | robust z | Foreign 1D · Robust z · of ADV20 · vs own · Level |

Reading warnings ("How to read it"):
- S1: Unusual for this stock, not large in rupiah. A small stock can be unusual with little money; the 5% floor keeps those out.
- S2: A large rise often means a recovery from heavy selling, not heavy buying.
- S3: Shows who is buying, not where the price goes. All investors are counted, so foreigners can be selling.
- S6: High for this stock, measured as a share of buying. Says nothing about rupiah size against other stocks.
- S6Δ: Built on S6. A rise can start from net selling; read it together with S6's level.
- S7: Broker labels describe each broker's usual clients, not the investor of each trade. One broker can make up the whole institutional side.
- S8: One day of buying, often a single block. Strong = all three checks; Watch = large and unusual, but not in the top 5% of its own history.

## 6. Visual system

- **Tokens:** EDGE Design Spec v1, identical to `apps/edge-bff/screener/src/styles/screener.css` (`:root` and the dark block
  `:root.dark, :root[data-theme="dark"]`). Light: bg #fafafa, surface #ffffff, border #eaeaea, text #171717 / #4d4d4d /
  #8f8f8f, green #087f5b, red #d62839, up #089981, down #f23645, blue #0070f3, amber #b45309. Dark: bg #0a0a0a, surface
  #111111, border #262626, text #ededed / #b4b4b4 / #7c7c7c. Grays used by the board: gray-50 #fafafa (dark #0f0f0f),
  gray-100 #f3f3f3 (#1a1a1a), gray-300 #dcdcdc (#3a3a3a), gray-500 #8f8f8f (#6f6f6f).
- **Type:** Inter (400, 500, 600, 700), tabular figures. Sizes 10.5 / 11 / 11.5 / 12 / 12.5 / 13 (body) / 14 / 15 / 18 /
  22 (h1). Weight 600 for titles and tickers.
- **Spacing:** 2, 4, 6, 8, 10, 12, 14, 16, 20, 24, 32 px. Radius 4 (tags), 6, 8 (buttons, inputs), 10, 12 (cards), 14 (dialogs).
- **Controls:** button height 32 (small 28), segmented button 22–26, pill 20, tag 18.
- **Theme:** follows the shell (light/dark). Colours of numbers: green up, red down, ink for zero.
- **Motion:** none beyond hover and focus; respect `prefers-reduced-motion`.
- **Focus:** 2 px blue outline on every interactive element; menus and lists work with arrow keys and Esc.
- **Responsive:** ≥ 1200 px seven columns; below, four per row; ≤ 720 px the rail is hidden (as in EDGE), the control bar
  wraps, the board scrolls sideways one column at a time (82% wide, snap), a column stops at 70% of the screen height.
  No horizontal page scroll at 375 px.

## 7. Data the page receives (proposal; final in `EXEC.md` EXEC-RADAR)

The page never queries the database. It reads small daily files, gzip JSON, through edge-bff:

1. **Board file** for a result date (one request when the page opens): for each filter, every stock that passes at the
   loosest setting (Loose level, Broad gate), with what the page needs to apply Level, Gate, Universe and Show itself:
   ```json
   { "date": "2026-11-09", "sources": { "price_to": "2026-11-12", "broker_to": "2026-11-09" },
     "gate_cut_idr": { "broad": 1.85e9, "liquid": 1.761e10 },
     "filters": [ { "id": "S1", "counts20": { "standard|broad": [4,5,6] },
       "rows": [ { "t": "BOGA", "name": "Apollo Global Interactive", "close": 1835, "chg1d": 0.55, "buy5_idr": 6.29e10,
                   "pass": { "loose|broad": true, "standard|broad": true, "strict|broad": true, "standard|liquid": true },
                   "met": { "standard": [1,1,1,1] }, "day": 1, "values": { "net5": 6.18e10, "ratio": 98.2, "pct": 100, "z": 7.85, "days": 4 },
                   "flag": "One-day block: ...", "spark20": [1790, 1801] } ] } ],
     "lists": { "LQ45": ["ADRO", "DEWA"] } }
   ```
2. **Filter file** for a filter and date (one request when a detail page opens): 250 daily counts per setting, daily
   members (for the bar chart and the activity spans), entered/left with the failed condition, near misses with their
   values.
3. **Price line** of the selected stock for the preview: the Terminal's existing price file for that ticker.

The browser caches files by date; switching controls never re-downloads.

## 8. States to design

Loading (skeleton columns, no spinner under 1 s) · a source behind (amber pill) · no result for the date yet ("Results for
<date> are not ready: broker data arrives after the close") · load error (message with a Retry button; never a blank
board) · empty column · all empty · search with no match · past date selected (Day N and New refer to that date).

## 9. Out of scope for this build

Follow (shows "Coming soon"), custom filters, CSV export, backtest summary, the normal-user version with hidden rules,
S4 and S5 (not designed yet). Leaderboard and Rotation Map are separate pages with their own specifications
(`LEADERBOARD_SPEC.md`, `ROTATION_SPEC.md` at the repository root).

## 10. Decision log (user's words)

| Date | Decision | Words |
|---|---|---|
| 2026-11-12 | The library becomes a page of its own | "saya mau screener ini dijadikan page baru" |
| 2026-11-14 | Columns S1, S2, S3, S6, S6Δ, S7, S8; name Radar | "A1 S8 ikut, dan halaman tetap bernama Radar" |
| 2026-11-14 | Universe as a view filter, default All; Gate Broad/Liquid; Level switch; data pills; own sort keys | "B3 OK", "B4 OK", "B5 OK", "B6 OK", "C7 OK" |
| 2026-11-14 | Conditions and near misses as in R9; no backtest; Follow stays "Coming soon"; no CSV; Open in Terminal without an indicator | "C8 as is tidak dirubah", "C9 hapus dulu", "C10 …", "D11 …" |
| 2026-11-14 | Price line in each card; no "Why it is here"; selected options black with white text | screenshots and messages of 2026-11-14 |
| 2026-11-14 | Columns as tall as their stocks | "tinggi kotaknya itu menyesuaikan jumlah saham" |
| 2026-11-14 | Count shown as dots (option 8) | "Opsi 8" |
| 2026-11-14 | Admin page; rules visible; a normal-user version later | "Ini adalah menu admin (which owner) nanti kita buat lagi saja khusus untuk user normal" |
| 2026-11-14 | Data path: daily files written by the publisher | "2. Ok" |
