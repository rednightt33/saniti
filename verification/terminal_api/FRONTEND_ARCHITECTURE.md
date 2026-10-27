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

- `live.ts` asks `POST /bundle` with `packs: true` and hands the worker `FileRef {url, sha, name}` lists. The worker
  reads each file from IndexedDB by sha256 first (`cacheGet`), else downloads it and stores it when the bytes hash to
  that sha256 (`cachePut`, 50 MB LRU). Broker: the last two refs are the recent years (answered as `broker`), the rest
  (the archive pack first) follow as `brokerAll`.
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
