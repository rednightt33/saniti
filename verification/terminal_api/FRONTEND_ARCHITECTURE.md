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
