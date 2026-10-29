# Terminal frontend — architecture (EXEC-TERMINAL-API T3–T5)

Inspection 2026-10-25 before any frontend code. Decisions from the user: TypeScript + Vite (T5), a Terminal tab next to
Monitor in EDGE at `https://edge-bff-dev.up.railway.app/` with the EDGE owner session for testing (T3), edge-bff forwards
`/api/terminal/...` to terminal-api (T4), and "visually and in interaction 1:1 with the static HTML reference".

## 1. What exists

| Part | Finding |
|---|---|
| Reference `03-terminal-right-panel.html` | 3,990 lines, 767 KB, one file: CSS (lines 1–~770), markup, `indRegistry` (53 indicators, JSON), Lightweight Charts **5.2.1** and lightweight-charts-drawing **0.6.2** inlined, app script (~lines 1040–3990): synthetic data (`makeRng(7139)`), chart, compare series, timeframe buttons, Statistics panel, Flow Timeline, Broker panel, indicators dialog (Inputs/Style), drawing tools, resizable/collapsible panels, 14 `localStorage` keys (`ml.*`). |
| EDGE (`apps/edge-bff`) | FastAPI serving one 470 KB `static/index.html` with an in-house React-like runtime (`element`, `initialValue`, `onLifecycle`); `nav = [["Monitor","monitor"]]`; page scripts served by name (`/{name}.js`); CSP `script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'self'`; session cookie `edge_session` SameSite=Strict for one owner; no build step; Dockerfile copies `app/` and `static/`; Railway deploys it from `main` (watch path `/apps/edge-bff/**`). Tests: pytest + Playwright Chromium against a real BFF and a disposable Postgres. |
| Libraries on npm | `lightweight-charts@5.2.1` and `lightweight-charts-drawing@0.6.2` (MIT) exist with exactly the inlined versions, so the TS build uses identical library code. |
| Local tooling | Node + npm, Vite 8, TypeScript 7, Playwright Chromium (`/opt/pw-browsers`), PostgreSQL 16 binaries (`/usr/lib/postgresql/16`) for the EDGE test fixture. |

## 2. Target structure

```
apps/edge-bff/terminal/              Vite + TypeScript project (inside the edge-bff build context and watch path)
  index.html                         markup of the reference, no inline script
  src/styles/terminal.css            the reference CSS, unchanged
  src/data/  api.ts files.ts         manifest, presigned URLs, gzip JSON → columnar bars/broker/events
             fixture.ts              the reference's synthetic generator (makeRng 7139 …), for 1:1 verification only
  src/calc/  indicators.ts stats.ts broker.ts   pure functions (T1 spec); no DOM
  src/worker/calc.worker.ts          runs calc off the main thread
  src/chart/ src/panels/ src/ui/     the reference's chart, Statistics, Broker, Flow Timeline, dialogs, drawing, layout
  tests/                             unit parity (vitest) + Playwright 1:1 suite
apps/edge-bff/static/terminal-app/   Vite build output (hashed assets), served by edge-bff; built by the Dockerfile's
                                     Node stage, not kept in git
```

As built (2026-10-25): `src/app/` holds one module per section of the reference (chart, stats, volume, axis, picker,
flow, events, drawings, indicators, search, broker), `src/ui/select.ts` the dropdown, `src/data/` the fixture
(`fixture.ts`, `fixtureConstants.ts` copied by script) and the live loader (`live.ts`), `src/calc/indicators.ts` the
T1 module. The sections start in the reference's order (`src/main.ts`). Calculations run on the main thread: all 53
indicators on 2,123 bars take 20–50 ms, so no Web Worker was added (T5 named one; reconsider if a heavier
calculation arrives).

- edge-bff serves the EDGE route `/terminal` (EDGE's page with the Terminal tab next to Monitor) and the built page
  at `/terminal-app/` with `/terminal-app/assets/*` (immutable cache); the tab shows `/terminal-app/` in a same-origin
  iframe under the EDGE top bar, so the reference CSS and EDGE's 470 KB CSS never mix.
- The build is one IIFE script loaded as a classic script at the end of `<body>` and one stylesheet in `<head>`, the
  way the reference runs: a deferred module script started later and met the web font at another moment, which moved
  the opening view by one bar in the 1:1 check.
- `lightweight-charts-drawing` is patched at build time exactly as the reference inlines it (accent `#1e53e5` →
  `#171717`, one constant; the build fails if the constant is not found once). `lightweight-charts` 5.2.1 is identical.
- The terminal page gets its own stricter CSP: `script-src 'self'` (no inline script, no eval), `worker-src 'self'`,
  `connect-src 'self' https://*.t3.storageapi.dev` (presigned downloads); inline style attributes stay allowed (the
  reference builds them); EDGE's own CSP is unchanged.
- Dockerfile: a Node stage runs `npm ci && npm run build`, the Python stage copies `static/terminal`.

## 3. Data and login (T3/T4)

- Browser → `edge-bff /api/terminal/v1/...` → terminal-api over the private network. edge-bff checks the EDGE owner
  session and calls terminal-api with a proxy key (`TERMINAL_PROXY_KEY`, both services) naming one subscriber account
  for the owner (`TERMINAL_PROXY_SUBSCRIBER`); quotas and audit apply to that account. Subscribers signing in directly
  stay possible through the same proxy later.
- Presigned file URLs point at the bucket; the bucket CORS rule adds `https://edge-bff-dev.up.railway.app`.

## 4. 1:1 verification method

1. **Same data:** the TS app has a fixture mode (`/terminal?fixture=reference`) that generates exactly the reference's
   synthetic OHLCV, broker profile and flow (ported generator, same seeds).
2. **Pixels:** Playwright opens the reference HTML and the TS page at the same viewports (1600×1000, 1280×800,
   390×844), waits for fonts and charts, and compares full-page and per-panel screenshots (pixel diff; the only
   accepted differences are listed, e.g. intentional indicator conventions).
3. **Interactions:** one scripted scenario run on both pages: panel resize/collapse/expand and their persisted
   `ml.*` keys, section accordions, timeframe and compare buttons, crosshair hover read-outs, indicator add/remove,
   Inputs/Style edits, drawing tools, broker filters (investor, board, net/gross, ranges, top-N), inventory broker
   picks, flow filters, cumulative toggle. After each step: DOM text of every panel and a screenshot diff.
4. **Numbers:** the TS calc module equals the reference engine on fixture data except the approved convention changes
   (ATR, ADX, RSI flat, OBV, Parabolic SAR → TA-Lib; RVOL includes the current bar), which are checked against
   Feature 04 / TA-Lib values instead (T1).
5. **Live:** with real data, panel figures are checked against SQL (as `validate.py` does).

## 5. Open point — deployment (still open, FUTURE_PLAN.md)

edge-bff deploys from `main`; the user said not to merge to `main` yet (2026-10-25). Building and verifying can be done
entirely locally (local edge-bff + disposable Postgres + the deployed terminal-api over HTTPS). Putting the Terminal tab
on `edge-bff-dev` needs either the merge to `main` or a CLI upload of this branch's edge-bff, which the next push to
`main` by another session would overwrite. Decision needed before the dev deployment.

## 6. 1:1 result (fixture mode, 2026-10-25)

`apps/edge-bff/terminal/tests/visual/` (`compare.mjs`, `scenarios.mjs`, `diff.py`; the reference file is passed with
`TERMINAL_REFERENCE_HTML`, never committed). Each page runs in a fresh browser context at 1600×1000, 1280×800 and
390×844; the web fonts are fetched once and served from memory to both pages. 28 cumulative steps: line/candle style,
price/return, compare series, indicator picker search and adding RSI, MACD and Bollinger Bands, the settings dialog
(Style tab, Cancel), the events popover, crosshair hover and leave, statistics accordion, collapse and expand,
seasonality weekday, broker filters (investor, gross, 5D, sell side) and a broker pick, flow investor filter and the
cumulative toggle, the Lines menu, drawing a trend line (Alt+T and drag), the cursor menu (Dot), the right-click menu
and the symbol search.

Two consecutive runs: 75 screenshots, **0 differing pixels** (12 pixels of canvas anti-aliasing noise, channel
difference ≤ 2 of 255, are counted separately); a third run after the live-loader change: 0 at 1600 and 1280, one
pixel at 3/255 (246 vs 243, the canvas edge at 390×844) in three phone steps; the markup of every panel and overlay, the panel texts and the
`localStorage` contents are equal (drawings compared without their clock-made ids). The reference against itself
gives 0 as well. Earlier runs found and fixed: template-literal whitespace (markup), the module-script timing and the
per-context font downloads.

## 7. Live check (real data, 2026-10-25)

`verification/terminal_api/terminal_live_check.py`: a local edge-bff with the built page forwards `/api/terminal` to
the deployed terminal-api with the gateway key; the browser opens `/terminal-app/` signed in as the EDGE owner.
BBCA, GOTO and IHSG load without page errors; BBCA's close 5,025 and volume 495.6M (2026-10-23), broker net and lots
(YU +709.0 B / 1.38M lots, SQ, AK) and the foreign net of the day (−767 B) equal SQL; an index (no broker data) shows
"no broker data". The broker-action gauge and the Bandar detector are hidden on live data (formulas not approved).
Parallel downloads of one ticker: 26 files, 1.55 MB, about 5 s from the sandbox.

## 8. Staged loading, Web Worker and screen-filling layout (EXEC-TERMINAL-UI-1026, 2026-10-26)

- Loading (`src/data/live.ts`): session → ticker and broker references together with `POST /bundle` for the remembered
  ticker → one Web Worker (`src/data/worker.ts`, built as `assets/worker-*.js`, CSP `worker-src 'self'`) downloads and
  parses every file and answers price, broker, events in that order. `main.ts` draws on the price; `later()` hands the
  broker data to the Flow Timeline (`ctx.setFlowData`) and to Broker activity (`ctx.setBrokerPanelData`, rendered when
  the panel is open); Statistics asks for IHSG (`M.loadIhsg`) only when Relative performance draws.
- Measured (Chromium profile, BBCA, files served from the test cache, edge-bff local → terminal-api live): API calls
  13 → 4; chart drawn at 1.9 s (before: everything at about 8 s); main-thread long tasks 0.9 s in shorter blocks, the
  longest 414 ms (before 1.6 s, longest 1,154 ms); what remains is the chart library's first paint of about 2,100 bars.
- Layout: `html.fit` (index.html) fills the frame; `?fixture=reference` removes it before the first draw, so the 1:1
  check keeps the reference's 976 px column. 1:1 result after these changes: 0 differing pixels and no text or markup
  difference over the 75 screenshots. Fit layout (fixture data, `&fit=1`): no page scroll at 1280×542, 1366×592,
  1536×672, 1440×732, 1920×892 and 2560×1242; chart 413–822 px; Flow folded below 650 px.

## 9. Packs, browser file cache and stage timings (EXEC-TERMINAL-SPEED, 2026-10-26)

- `live.ts` asks `POST /bundle` with `packs: true` and hands the worker `FileRef {url, sha, bytes, name}` lists
  (`bytes` since EXEC-MU-RUNTIME T7). The worker reads each file from IndexedDB by sha256 first, else downloads it, and
  uses and stores (50 MB LRU) only bytes of the announced size and sha256 (section 15). Broker: the last two refs are the
  recent years (answered as `broker`), the rest (the archive pack first) follow as `brokerAll`.
- `src/app/perf.ts`: `mark(name)` at session, ticker list and bundle, price read, page script, chart drawn, Flow last
  two years, Flow every year; the worker posts per-file stats (`stats`). `?perf=1` shows them (`.ml-perf`).
- The loading ring turns in 0.15 s (`.ml-spin`, user 2026-10-26).

## 10. Panel order, broker periods and the annotation rail (EXEC-TERMINAL-PANELS, 2026-10-26)

- `src/ui/reorder.ts` (live): a grip in each `.st-head` of `#leftScroll` and `#rightScroll`; dragging moves the section,
  Alt+↑/↓ on a header moves it by keyboard; the order is kept in `ml.stats.order` / `ml.broker.order`.
- Broker activity reads the broker dates after `panelStart(latest)` (`worker.ts`, two years). `main.ts` `later()` hands
  the panel the recent answer, then the full one; `broker.ts` keeps each panel's period by date (`kept`), the filters and
  the picked brokers across that redraw.
- `makeRange` (live): Custom opens `openRangeCalendar` (`src/ui/calendar.ts`, one month grid, year chips, only broker
  dates pickable, "Select on chart"). `ctx.selectRangeOnChart` (`src/app/rangeSelect.ts`) puts a layer over the chart
  (pan and zoom off, restored from a deep copy) and returns the first and last session; `applyChartRange` sets it on
  every panel (`setDates`, clipped to the panel's dates with a note).
- `events.ts` (live): with events on, `.chart-wrap.ev-rail` gives the chart 24 px less and the markers sit on the rail.
- Live check: `verification/terminal_api/panels_live_check.py`.

## 11. EXEC-TERMINAL-PANELS-2 (2026-10-27)

- `reorder.ts`: the `.st-head` itself is the drag handle (press and move 5 px; touch holds 250 ms first); the click that
  ends a drag is swallowed only within the same task.
- `broker.ts` `renderAccPaired` (live): accumulators and distributors in one table, rank k beside rank k, one scale.
- `calendar.ts`: every day is clickable; `setDates` maps a range without sessions to the last session before it.
- `rangeSelect.ts`: drag, or click the first and the last day (the same day twice = one day); the band spans whole bars.
- `events.ts` (live): `subscribeCrosshairMove` marks the marker of the session under the crosshair (`.ev-mk.hot`).
- Broker inventory (live, C): `renderInvLive` reads the chart's visible logical range (re-run on every range change,
  one per frame), draws `niceTicks` on a y-axis and a crosshair line; `chart.subscribeCrosshairMove` moves the line, a
  hover on the inventory calls `ctx.crosshairAt(i)` (flow.ts), which sets the main and Flow crosshairs.

## 12. EXEC-TERMINAL-FRESH (2026-10-27)

- `live.ts` `bundle` keeps each dataset's `data_through`; `ctx.brokerEnd` (`context.ts` `brokerEnd`) is the last session on
  or before the broker date. Flow bars and the cumulative line are whitespace after it, the summary stops there, the
  tooltip says "No broker data yet", `.flow-nodata` hatches the sessions after it and `.stale-badge` sits in the Flow
  and Broker activity titles; Net Buy Flow indicators are null after it.
- `drawings.ts`: a second DrawingManager on the Flow chart for the Lines group (key `ml.drawings.flow.{TICKER}`, shared
  undo, `dragFinish`, right-click cancel, its own Remove drawings).
- EXEC-TERMINAL-FULL: the yellow labels are gone; `src/ui/fullscreen.ts` (live) folds the three panels through their own
  buttons, hides the Flow bar and footer (`html.ml-full`), asks the Fullscreen API (EDGE's frame has `allow="fullscreen"`)
  and puts the panels and their stored choices back on leaving.
- EXEC-TERMINAL-FULL-2: the full-screen button only folds the panels (no Fullscreen API; Esc leaves); the symbol pill
  has no "IDX" label in live mode.

## 13. Weekly and monthly candles (EXEC-TERMINAL-WM, 2026-10-27)

- `src/data/timeframe.ts` builds W/M candles from the daily sessions (`aggregateRows`, `buckets`, `candleOf`); `ml.tf`
  holds the choice and a different button reloads the page (sections take their data once at start).
- `live.ts`: candles for the chart, `ends` (each candle's last session) for compare/IHSG alignment, events on the
  candle holding the next session; the worker sums broker net per candle (`brokerData(docs, dates, groups)`).
- `ctx.endDates` serves the chart range selection and Broker inventory; `M.barOf` maps drawing points (G1) on load;
  Statistics and Flow labels and the volatility annualisation follow the timeframe.
- EXEC-TERMINAL-CUM: the Flow's cumulative line (live) is `cumulativeFrom(net, first visible candle)`, recomputed on
  every range change (Stockbit's F Flow from the start of its period); `FLOW_CUMULATIVE_FROM = 'history'` or
  `?cum=history` brings back the sum from the first session.

## 14. Panel windows (EXEC-TERMINAL-POPOUT W1 + I2, 2026-10-27)

- `src/ui/floatwin.ts`: a window over the page (`.fw`, live): moves by its title bar, resizes from its corner, comes to
  the front when pressed (z 50–58, pinned 59, below the dropdowns and the calendar), stays in the page (`clampBox`);
  pin, back to panel and close in the title bar; place, size and pin in `ml.win.<id>`.
- `src/app/popout.ts`: the ⤢ button beside each right-panel header (a sibling of the header button) opens Broker
  summary, Top brokers or Broker inventory as a window; open windows (`ml.win.open`) and their choices
  (`ml.winst.<id>`) come back after a reload. Each window draws from `M.broker`; periods 1D/5D/20D, Chart (the
  visible sessions, redrawn on every range change) or Custom (the range calendar, "Select on chart").
- `src/data/brokerAgg.ts`: `aggregate` (sums per broker for an investor type and board), `avgPrice` (value ÷ lots ×
  100), `sessionSpan`, `sidesTable` (EXEC-TERMINAL-BS-SIDE: buyers left, sellers right, largest first; Net or Gross; Top N
  per side, search, a total per side and for the period, % of value),
  `inventory` (daily net and running sum per broker with its period sums), `invStats`, `toCsv`.
- `broker.ts` shares `ctx.brokerShared`: the Broker inventory brokers (one set for the panel and the window), `pick`
  (highlight and add), `changed` (the panel and every window redraw), `ensureDefaults` (three largest net buyers of the
  last 20 sessions, also when the broker data arrives with the panel closed).
- No frequency columns: the rack carries no `buy_freq`/`sell_freq` (user 2026-10-27: "tanpa frekuensi dulu.").

## 15. One rack module for every page (EXEC-BACKTEST-LOAD K3, 2026-10-27)

- `src/data/rack.ts`: the browser file cache (IndexedDB `terminal-files`, the record and the 50 MB limit as before) and
  the presigned download with retries (ERRORS M251), used by the Terminal's worker and the Backtest page's loading
  worker (`apps/edge-bff/backtest/src/api/load.worker.ts`).
- EXEC-MU-RUNTIME T7 (2026-10-29, accuracy): `rack.ts readVerified` is the Terminal's one check of a published file, the
  rule of the Backtest core's `inflateVerified` (the Terminal is built alone, so it cannot import that core). A file
  `/bundle` announces, and a reference file `/reference` announces with `sha256` and `bytes` (T5), is used and stored
  only when its bytes have that size and sha256, downloaded or cached (a cached copy is checked on every use; one that
  differs is downloaded again and replaced); an announcement without a valid sha256 and size is refused before any
  download; a reference file without them (an older terminal-api or publication) is read as before and not stored.
  A failed check is `IntegrityError` (`DATA_INTEGRITY`, "A data file did not match its published checksum; reload the
  page."), never drawn: `live.ts checked` runs the ticker's job once more on one new `/bundle` (`once`: one new
  `/reference`), then the page shows the message (the chart's notice; the Flow note and the side panels keep their own
  texts). The new job puts its broker data on the sessions the chart draws (the first job's price when it was read),
  so a publication between the two answers never shifts the Flow against the candles. Before T7 the Terminal drew a
  downloaded file whose sha256 differed (it only did not store it), never checked the size and trusted a cached copy.
  Tests: `tests/data/download.test.ts`.
- EXEC-BACKTEST-SPIN: the loading ring is `src/styles/spin.css` and `src/ui/spin.ts` (`context.ts` re-exports `spin`),
  imported by the Terminal and the Backtest page; one speed (0.15 s, 1.6 s with reduced motion).

## 16. Broker summary side by side, Alt+B, blue crosshair (EXEC-TERMINAL-BS-SIDE, 2026-10-28)

- The Broker summary window (`popout.ts renderBS`) is a paired table like Top brokers: net buyers left, net sellers
  right (Gross: buy value left, sell value right), largest first; per side Broker, the two values, Buy avg, Sell avg,
  % of value, mirrored around the middle line; a Total per side; no column sorting. The CSV keeps every column with a
  Side column. A window remembered with the old column sort keeps its Net or Gross choice (`sort: 'share'` = Gross).
- `broker.ts`: Alt+B (live, not while typing, once the broker data has come) is Custom → Select on chart of the right
  panel: the chosen period goes to its four panels and Broker summary is shown (a collapsed panel opens). Windows keep
  their own Custom button.
- `rangeSelect.ts`: while choosing, the layer hands the pointer to the chart's crosshair (`SEL_LINE`, the band's blue;
  the session under the pointer at the pointer's price) and puts the crosshair options back on finish or Esc. A
  position set from code fires no `subscribeCrosshairMove` (lightweight-charts 5.2.1 synthetic position), so the legend,
  the Flow chart and Broker inventory are moved through `ctx.crosshairAt` (flow.ts) first.
- Live check: `verification/terminal_api/bs_side_live_check.py`.

## 17. Added assets and their Flow Timelines (EXEC-TERMINAL-ASSETS, 2026-10-28)

- `src/app/assets.ts` (live only): the + button opens the ticker search (`search.ts` `ctx.openTickerSearch`, `pick` and
  `tag`); at most `MAX_ASSETS` = 2 besides the chart's ticker. Each asset: a legend row (`.as-rows` after `#flowTip`),
  one series (Line, Step line, Area, Bars, Candles; price source; colour, width; price line; scale right / left / own;
  min tick), the settings dialog (the indicators' `.idlg` look: Inputs, Style, Visibility, Defaults), saved in
  `ml.assets.v1` (defaults in `ml.assets.defaults`).
- Data (`live.ts`): `loadAsset(ticker)` = its daily prices as candles of the chart (`timeframe.ts alignCandles`: a session
  it did not trade repeats its last close, nothing before its first close); `loadAssetFlow(ticker)` = its broker files
  from `/bundle`, read by the worker on the chart's daily sessions (`WorkerJob.dates`), recent years first.
- Flow pane per asset (`.bottom.af`, after `#flowPanel`, a grid row of its own of height `--af-h`): badge in the asset's
  colour, its own Broker / Board / Investor filters, summary, tooltip, cumulative line (the Cumulative toggle), fold.
  Locked to the chart: time range both ways (a new pane takes the chart's range first), crosshair (`ctx.crosshairAt` also
  moves the panes), axis widths (`flow.ts` aligns `ctx.extraFlowCharts`); the chart's Flow height leaves room for them
  (`ctx.extraFlowHeight`, `ctx.refitFlow`). With panes, the chart's Flow title shows its ticker badge too.
- Drawings (`drawings.ts`): every Flow chart is a host (`attachFlow`); Flow tools = the Lines group + Brush + Text; an armed
  Flow tool moves to the Flow chart pressed; drawings of an asset's Flow are kept under `ml.drawings.flow.<ticker>`.
- Check: `verification/terminal_api/assets_check/` (`mock_server.py` serves a build and stands in for EDGE and
  terminal-api with synthetic files of the rack's shape; `check_assets.mjs`, `check2.mjs`).
- EXEC-TERMINAL-ASSETS-2: each asset pane has a grip (`.af-grip`, the chart Flow's look; height per ticker in
  `ml.assets.flow.h.<ticker>`, double-click resets, the chart keeps 240 px), the chart ticker's badge style, and the
  hatch after its broker data's last date (`.flow-nodata`, placed like `flow.ts placeNoData`). Check: `check3.mjs`.
