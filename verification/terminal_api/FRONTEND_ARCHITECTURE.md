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
apps/edge-bff/static/terminal/       Vite build output (hashed assets), served by edge-bff
```

- edge-bff serves `/terminal` (the built page) and `/terminal/assets/*` (immutable cache). The EDGE nav gets
  `["Terminal","terminal"]`; the route shows the page in a same-origin iframe under the EDGE top bar, so the
  reference CSS and EDGE's 470 KB CSS never mix and the terminal stays 1:1 with the reference.
- The terminal page gets its own stricter CSP: `script-src 'self'` (no inline script), `worker-src 'self'`,
  `connect-src 'self' https://*.t3.storageapi.dev` (presigned downloads); EDGE's own CSP is unchanged.
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

## 5. Open point — deployment

edge-bff deploys from `main`; the user said not to merge to `main` yet (2026-10-25). Building and verifying can be done
entirely locally (local edge-bff + disposable Postgres + the deployed terminal-api over HTTPS). Putting the Terminal tab
on `edge-bff-dev` needs either the merge to `main` or a CLI upload of this branch's edge-bff, which the next push to
`main` by another session would overwrite. Decision needed before the dev deployment.
