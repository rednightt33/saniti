# Adding a page to EDGE

How the Overview (EXEC-OVERVIEW), Radar (EXEC-RADAR) and Watchlist (EXEC-WATCHLIST) were added; copy the Watchlist,
the newest. Paths are relative to `apps/edge-bff/` unless they start with `apps/`. Line numbers drift: search for the
Watchlist's lines and add the new page beside them. Read `AGENTS.md` first (plans, approvals, release order, records).

## 1. The page itself: a Vite + TypeScript sub-app
- Copy `watchlist/` structure: `index.html` (icon sprite from `../assets/icons.svg`, `<div id="view">`),
  `src/main.ts` (theme from `localStorage['edge-auth-monitor-theme']`, follows the `storage` event),
  `src/app.ts` (render), `src/model.ts` (pure functions: formats, layout, the tests' target), `src/api.ts` (the only
  data path, same origin, session cookie, CSRF on writes), `src/types.ts`, `src/styles/<page>.css`,
  `vite.config.ts` (base `/<page>-app/`, one classic IIFE script at the end of `<body>`: the sub-app CSP forbids inline
  scripts), `tests/` (`model.test.ts`, `bundle.test.mjs`, a `fixture/` build with made-up data).
- CSS: the spec and canonical layer first (copy `spec-v1.2.css` + `edge-canonical.css` into `src/styles/` or import
  them), then the page CSS. No framework.
- No navigation of its own: the shell draws the rail. To open another page, post `{type:"edge-nav", route}` to the
  parent (shell `static/index.html`, "edge-nav" listener).
- Every browser storage key the page uses gets its entry in `shared/edge-session.ts` (`STORAGE`, kind `browser` or
  `user`); then `node shared/build-shell.mjs` and commit `static/edge-session.js` (AGENTS.md, ERRORS M473).

## 2. The BFF (`app/main.py`)
- `<PAGE>_APP = STATIC / '<page>-app'`, a `@app.get('/<page>')` route that serves the shell, `page_app('<page>-app',
  <PAGE>_APP)`, the page's CSP choice (the Watchlist reuses the Terminal CSP for logos from the bucket).
- Data routes in their own module (`app/<page>.py`, like `app/watchlist.py`): a session dependency, writes behind CSRF,
  refusals as `{error:{code, field, message}}` naming the fix (AGENTS.md gate rule), limits returned to the page.
- If the page is owner-only: a capability in the session answer (`'<page>': …` beside `'watchlist'`).
- `Dockerfile`: a build stage for the sub-app and `COPY --from=<page> … ./static/<page>-app`; `.dockerignore`
  `static/<page>-app`.

## 3. The shell (`static/index.html`, `static/edge-labels.js`)
- `edge-labels.js`: `<page>: { nav:"<Name>", frameTitle:"<Name>" }` and the document title.
- `index.html`: the `nav` list entry and its rail icon; `OWNER_PAGES` if owner-only; a `<Page>Page` component that
  renders `<main class="terminal-page"><iframe class="terminal-frame" src="/<page>-app/">`; the route table entry
  (`{path:"/<page>", names:["<page>"], auth:true, title:"<page>"}`) and the switch that renders it; the phone ☰ menu.

## 4. Data from the publisher (when the page needs a daily file)
- `apps/terminal-publisher/<page>.py` builds the file (stored values only; a "complete date" derived from counts),
  registered in `publisher.py` `PAGES`; `apps/terminal-api/app/bucket.py` `PAGE_FAMILIES` and `main.py` `PAGE_LABELS`;
  `apps/telegram-monitor` stage name. The BFF relays it with `app/pages.py` (`PageFiles`).
- A formulas document in plain Indonesian (`<PAGE>_FORMULAS.md`) with its generator and test (AGENTS.md rule).
- Check the publisher's SQL under the publisher's own role, not an admin role (ERRORS M466).

## 5. Checks before release
- Unit tests of `model.ts`; the bundle test; the BFF tests (`tests/test_<page>.py`, `tests/test_<page>_page.py`);
  the shell nav tests (`test_overview`, `test_radar`, `test_backtest` count the rail).
- Browser checks at 1440 / 1152 / 390 / 360 px and dark mode: no sideways scroll, no console error, Inter loaded.
- Every CI suite, not only the page's own: a document's line-pointer test lives in another app (ERRORS M467).
- Independent recalculation of the figures from PostgreSQL when the page shows numbers.

## 6. Release (with the user's go per step)
Publisher and terminal-api first (and a Run Now for the first file), then `main` (edge-bff), then any migration the new
code needs, then a live check as the owner; records in `RAILWAY_CHANGELOG.md`, `DATABASE_CHANGELOG.md`, `EXEC.md`,
`ERRORS_AND_SOLUTIONS.md`.
