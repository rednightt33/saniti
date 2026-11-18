# Page layouts and patterns

All shown in `../assets/showcase.html`. The design proposals the user sent (2026-11-14 to 2026-11-18) are taken as
**patterns adapted to the tokens** (decision 2026-11-18): their own values (8 px card radius, 6 px segments, 30 px
buttons, 17 px titles, `#666` secondary text, `#0050ff` accent) are replaced by the spec's.

## Page skeleton
```
┌ rail (shell) ┬──────────────────────────────────────────────────────────────┐
│              │ .head  h1 + purpose line            date pills · actions      │
│              │ .kpis  4–6 KPI tiles (one row; 3 per row ≤1139 px, 2 ≤599 px) │
│              │ grid of .card (two or three columns; one column on a phone)   │
│              │   each card: .card-h (title/subtitle · Period seg) + .card-b  │
└──────────────┴──────────────────────────────────────────────────────────────┘
```
Page padding 20/24 px (`--s-9`/`--s-10`), gaps 16 px (`--s-8`). The page scrolls inside the frame; headers do not stick
unless the page is a long table.

## Board (columns of compact cards) — Radar
One column per group (S1–S8), each a `.card` with a small header (code, name, count, a 70×18 count bar) and a list of
compact stock rows (symbol, change, day tag, 46×16 price line). Columns scroll sideways as a whole on narrow screens.

## Stock card — Watchlist
Logo (28 px circle or monogram), symbol + name, last price + 1D + 1M, trend line (fluid × 40), up to 4 indicator chips,
"Foreign flow as of <date>" once, badges (corporate action `.pill.info`, Radar ink pill). Cards in an auto-fill grid
(min 300 px). A dashed "Add stock" card ends the grid.

## Widget cards (proposal: Watchlist home widgets, `edge-homepage-cards_3.html`)
Slot sizes: compact (≥250 px: one big number + one line + a 26 px trend), tall side panel (a stock list with 64×22
sparklines, a timeline), medium (one question per card: performance vs IHSG, heat cells, foreign net bars, sector
exposure stacked bar, top movers, 52-week range bars, RSI distribution), wide (full table, flow timeline, signal
matrix, calendar). A card that needs data EDGE does not have says so in its note; never fill with invented numbers.

## Right panel (proposal: `right-panel-candidates_screener_dan_backtest.html`)
Cards 320 px wide stacked in `.side` beside the Terminal/Screener/Backtest main area: small header (title, ⋯), a row of
3 spec `.kpi` boxes, then one compact chart or list. On a phone the panel becomes full width under the main area.

## Floating window (proposals: `1_2.html` Foreign × Domestic window, `2_2.html` Verdict change drivers)
`.win` 880×520 or 720×560 (the Terminal's Broker summary / inventory windows): head `.win-h` (title, grey context
"ALFQ · Regular · Top 3 · to Mon 9 Nov", pin and close icon buttons), controls row `.win-ctl` (period seg, Top N select,
board), body `.win-b`. Inside: a map or trail chart on the left, a compact table (`.tbl.compact`) and a one-line
equation box ("Verdict = Foreign + Domestic") explaining how the numbers add up.

## Day counts (proposal: `flow_day_count_options.html`)
Indicators whose value is a count of days (FL26 streak, FL12/FL29/FL35 "k of N days") are drawn as boxes, not lines:
one column per session, one box per day, filled `--up`/`--down`, empty `--sel` (`EdgeDS.kofn`); or a one-row heat
strip when the pane must be short (`EdgeDS.heat`). Percent stays in the legend ("55% · 11 of 20 days").

## Signal matrix and timeline
Matrix: one row per stock, columns per signal family, cells Strong `.c.s` / Neutral `.c.n` / Weak `.c.w`.
Timeline `.tl`: a dot on a rule (`pos`/`neg`/`info` colour), the event, a grey line with source and time.
