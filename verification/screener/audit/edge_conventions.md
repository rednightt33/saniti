# EDGE conventions for the Screener: audit (area `edge_conventions`)

Read-only audit of repository HEAD `3db84ae`, plus live catalog reads from the market Postgres through pgweb on 2026-10-27. No file in `/home/user/saniti` was changed (`git status` is clean). Raw evidence is in `/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/audit/edge_conventions/` (`evidence_index.txt`, `live_edge_bff_catalog.txt`, `proposed_migration_screener_DRAFT.sql`).

Labels: **FACT** means seen now in code, data or a recorded log. **INFERENCE** is drawn from facts but not tested. **PROPOSED** is a design for approval. **UNKNOWN** is not established.

---

## 0. Answers in short

| Q | Answer |
|---|---|
| 1. Where the page and API go | **PROPOSED:** keep both inside `edge-bff`, following the Terminal and Backtest pattern. Page: a third Vite + TypeScript sub-app `apps/edge-bff/screener/`, built by a new Dockerfile stage into `static/screener-app/` and shown in a same-origin frame at `/screener` (new "Screener" tab). API: a new feature module `app/screener.py` modelled on `app/backtest.py`. It uses `routes(app, session, write)`, the error shape `{error:{code,field?,message?,details?}}`, a `guard()` that answers `*_DISABLED` / `*_NOT_READY`, and a store over the house `Store`. Market-data computation must **not** run as SQL inside edge-bff: its role cannot read any public table (FACT). Computation goes in the browser over the rack, in a private worker service, or in a published snapshot (section 2.3). A separate public service for the page goes against every convention here. |
| 2. Storage for saved screens and the watchlist | **FACT:** none exists anywhere. There is no table matching watch/screen/prefer/saved/favorit in any schema, and repo-wide `watchlist` hits are leftover CSS in `static/index.html` only. The prototype keeps everything in `localStorage` (`edge-screens`, `edge-metrics`, `edge-watchlist`, `edge-scr-theme`). The only per-user server metadata today is per conversation (`edge_bff.conversation_ui`: bookmark, title, pins, hidden, kind). **PROPOSED:** two tables in `edge_bff`, `screener_screens` and `watchlist_items` (draft in section 3.3), plus the provisioning-script and test updates that edge_bff conventions require. |
| 3. Send to Backtest | **FACT:** the Backtest page reads nothing at boot except two layout keys. It holds no "import", and no wire→card conversion exists. **PROPOSED:** a one-shot `sessionStorage` handoff written by the Screener frame and read once by the Backtest boot after `applyCatalog`. Same-origin precedent: `edge-side-attach:<id>`, covered by a Chromium test. Navigation goes through a same-origin `postMessage` to the parent EDGE shell, so the data never travels in the URL. Payload is in the Backtest's own vocabulary (`RegCard` / `LegacyCard`). A URL hash is an optional extra for copyable links. A server-side draft is not needed for a single owner. |
| 4. Security | Secrets, keys, database URLs, internal addresses, raw upstream errors and the session token never reach the browser. Section 5 lists how the code guarantees each, plus three gaps the Screener must not copy. |
| 5. Railway | Everything runs in `sfo`. The `terminal-display` bucket is in `sin`. edge-bff deploys from GitHub `main` (watch `/apps/edge-bff/**`). backtest-worker, terminal-api and terminal-publisher deploy by CLI upload. Private calls go over `http://<svc>.railway.internal:8080`. Merge-deploy pitfalls M248 and M252 apply (section 6). |

---

## 1. How EDGE is built today (FACT unless marked)

### 1.1 One service, one origin, one owner
- edge-bff is one FastAPI app (`app/main.py:160-669`, `create_app`). It runs as one uvicorn process with `--workers 1`, behind one replica (`Dockerfile:33`, `.railway/railway.ts:181-190`).
- It serves:
  - the EDGE single-page app (`static/index.html`, about 12.5k lines);
  - the two built sub-apps, `/terminal-app/` and `/backtest-app/`;
  - its own API under `/api/v1`;
  - a gateway to terminal-api under `/api/terminal/v1`.
- Owner model (single user):
  - `Settings.owner` comes from `EDGE_OWNER` (`config.py:48`; validated against `[A-Za-z0-9._:@-]{1,128}` at `config.py:72`).
  - Dev values: `EDGE_OWNER=edge-private`, `EDGE_LOGIN=edge` (README:310-311; RAILWAY_CHANGELOG:3844).
  - There is one login and one scrypt verifier (`config.py:49`, `main.py:411-412`).
  - Every session row stores `owner_key`. The session dependency rejects a row whose owner is not `settings.owner` (`main.py:245-250`).
  - Every owned query filters `WHERE owner_key=%s` (store.py, backtest.py).
  - There is no owners/users table (live: the six `edge_bff` tables only).
  - The browser never names an owner. edge-bff sets `X-Saniti-Owner` towards Orc (README:247; `client.py:36`).
  - For terminal-api, the owner is one gateway subscriber: subscriber 2, `edge-owner@terminal.local` (DATABASE_CHANGELOG:2690-2692).
  - **INFERENCE:** a multi-user Screener would need an owner directory and a terminal-api account per owner. Neither exists, so per-owner tables keyed by `owner_key text` (no foreign key) are the house pattern to follow.

### 1.2 Request protections (`main.py`)

| Protection | Where |
|---|---|
| Exact `Origin == EDGE_PUBLIC_ORIGIN` on every POST/PATCH/PUT/DELETE, sign-in included (403 `ORIGIN_REJECTED`) | `main.py:222-225` |
| Body cap of 131,072 bytes on writes (413 `REQUEST_TOO_LARGE`) | `main.py:226-232` |
| Session: opaque 64-hex cookie `edge_session` (HttpOnly, SameSite=Strict, Secure in deployment); only its sha256 is stored | `main.py:246-247,419-423`; `security.py:22-23` |
| CSRF: `X-CSRF-Token` = HMAC-SHA256(session secret, token), compared in constant time, on every write route that uses `write` | `main.py:252-255`; `security.py:26-27` |
| Sign-in limiter: 5 failures per minute per IP, process-local | `main.py:401-414` |
| Response headers: `Cache-Control: no-store` (default), `nosniff`, `Referrer-Policy: same-origin`, CSP chosen by path prefix | `main.py:233-243` |
| CSP of EDGE's own page: `script-src 'self' 'unsafe-inline'`, `connect-src 'self'`, `frame-ancestors 'self'` | `main.py:242` |
| CSP of the sub-apps (`TERMINAL_CSP`, and `BACKTEST_CSP = TERMINAL_CSP`): `script-src 'self'` (no inline), `worker-src 'self'`, `style-src 'self' 'unsafe-inline' fonts.googleapis.com`, `img-src 'self' data: blob:`, `connect-src 'self' https://*.t3.storageapi.dev`, `frame-ancestors 'self'` | `main.py:39-48` |
| Input models forbid unknown fields | `main.py:57-58` |
| No CORS, no OpenAPI or docs routes | `main.py:197`; README:275 |

### 1.3 Database access pattern
- `Store.connect()` opens a **new psycopg connection per call**, with `SET LOCAL statement_timeout = '5s'` (`store.py:25-29`).
- Every call runs through `asyncio.to_thread` from the routes.
- The login role `edge_bff_login` has a connection limit of 20 and role settings `statement_timeout=5s`, `lock_timeout=2s`, `idle_in_transaction_session_timeout=15s`, `search_path=edge_bff,pg_catalog` (live `pg_roles`).
- PLAN BACKTEST-LOAD (PLAN.md:898-960) measured `/auth/session` at a median of 240 ms from the sandbox and proposes `psycopg_pool`. It is not approved to execute yet.
- **INFERENCE:** a Screener API should make few coarse calls (one screen run, one list of saved screens), not one call per ticker. Each call costs a session lookup on a fresh connection.
- `app/backtest.py:287-292`: long relayed calls must be awaited on the event loop (`httpx.AsyncClient`), never in the thread pool. A thread held by a waiting call delays every request's session check.
- edge-bff's runtime role can read **0 of the 87** public relations (live `has_table_privilege` count). The schema comment reads "EDGE sessions, delivery jobs and UI metadata only". README:236-239 says the backtest tables "hold no market data", and the backtest worker reads market data only through terminal-api (CONTRACT.md section 1).

### 1.4 The feature-module model (`app/backtest.py`)
- The module docstring names the contract sections (lines 1-5). Constants carry their reasons, for example `CONTROL_TIMEOUT=30` and `CATALOG_CACHE_SECONDS=60` with "not derivable" notes (lines 37-50).
- `BacktestError(status, error)` produces the contract shape. Its handler is registered inside `routes()` (lines 53-57, 1052-1054).
- `BacktestStore` wraps the house `Store`. It maps `UndefinedTable` to 503 `BACKTEST_NOT_READY`, so a missing table switches off only this feature, and `/ready` never reads these tables (lines 406-424; main.py:181-183).
- `Backtests.guard()` answers 503 `BACKTEST_DISABLED` when no worker URL is configured, else checks the tables once (lines 942-947).
- Relays go through `ask()`:
  - a 2xx answer passes its JSON;
  - a 4xx error from the worker is relayed as it is, after `error_of` reduces it to code/field/message/details and `public_data` filters it;
  - the worker's 504 `TIMEOUT` is relayed as 504;
  - anything else becomes 503 `BACKTEST_UNAVAILABLE` (lines 949-968).
- Request bodies are read by `loads`, which refuses NaN, Infinity, numbers beyond a double, lone surrogates and over-deep nesting with 422 `INVALID_INPUT` (lines 94-105, 1040-1047).
- Writes are idempotent through `client_request_id` (a submission key), with 409 `SUBMISSION_CONFLICT`, under a per-owner advisory lock (lines 437-457, 1085-1111).
- Settings come in pairs (URL and key together, key at least 32 characters, host `backtest-worker.railway.internal` over http outside `local`). Limits have no defaults, so the service will not start without them (`config.py:29-38, 91-104`).
- Logs carry only an exception class, SQLSTATE or a redacted first line (`failure_of`, lines 138-167).

### 1.5 Error shape: the rule and its exceptions
- Contract shape: `{"error":{code, field?, message?, details?}}` (CONTRACT.md section 11). House routes send `{"error":{"code"}}` only (`main.py:200-201`).
- **Exceptions (FACT):**
  - The `session` and `write` dependencies raise FastAPI `HTTPException`. With no handler for it, 401 and 403 come back as `{"detail":"Authentication required"}` and `{"detail":"Invalid CSRF token"}` (`main.py:249, 254`).
  - The Backtest client copes: `live.ts:29-40` maps any 401 to its own sign-in message.
  - Unexpected exceptions become a generic 503 `SERVICE_UNAVAILABLE` (`main.py:215-218`).

### 1.6 Schema `edge_bff` (live and migrations)
- Live tables, with row estimates from `reltuples`: `sessions` (28), `jobs` (340), `conversation_ui` (88), `backtest_jobs` (43), `backtest_results` (181), `backtest_trials` (250).
- Grants: `conversation_ui`, `jobs` and `sessions` give `edge_bff_runtime` `arwd`. `backtest_jobs` gives `arw`, `backtest_results` `ard`, `backtest_trials` `arw`. PUBLIC has nothing.
- There are **no default privileges** in `edge_bff`; the only default ACL is `public` granting `pgweb_reader` read. So every new table needs explicit GRANTs. `edge_bff_login` is a member of `edge_bff_runtime`. pgweb has no USAGE on `edge_bff`, so row contents could not be read: only the catalog.
- `conversation_ui` columns (live) match migrations 008, 002 and 20261024_002: `owner_key, conversation_id, title(1..200), bookmarked, pinned_request_ids text[] (≤500), created_at, updated_at, hidden_at, kind MAIN|BRANCH|SIDE, parent_conversation_id, parent_request_id`, primary key `(owner_key, conversation_id)`. It holds conversation UI metadata only. The "preference" API is a desired-state PATCH (`main.py:614-629`). **No generic per-user preference or saved-object table exists.** Model choice, theme and panel sizes live in browser `localStorage` (`edge-model-choice`, `edge-auth-monitor-theme`, `edge-details-width`, ...).
- Migration conventions, seen in all five `edge_bff` files:
  - `BEGIN; SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='1min'`;
  - a `$preflight$` block that refuses a missing prerequisite or an already-existing object;
  - checked identifiers (`^conv_[0-9a-f]{32}$`, `^bt_[0-9a-f]{32}$`) and length checks;
  - `COMMENT ON` for the tables and non-obvious columns;
  - `REVOKE ALL … FROM PUBLIC` and exact per-table GRANTs;
  - a `$verify$` block that checks each needed privilege **one call at a time**, checks that nothing more is held (TRUNCATE/REFERENCES/TRIGGER), and checks that PUBLIC holds nothing;
  - the rollback body as a comment;
  - comment-only changes go in their own migration (`20261027_005`).
- Coupled files that must change with any new `edge_bff` table:
  - `scripts/provision_edge_bff_login.py:10,14,36` refuses provisioning when the login can reach any relation outside `TABLES` / `BACKTEST_GRANTS` ("EDGE has unexpected reachable relations");
  - `tests/conftest.py:19-24` applies each migration in order, and `:32` truncates;
  - the migration verify tests in `tests/test_backtest.py:962-1100`.
- `DATABASE_SCHEMA.md` is generated from schema `public` only (its header; `.github/workflows/database-schema-docs.yml`). `edge_bff` is documented in `apps/edge-bff/README.md`, the migrations, `DATABASE_CHANGELOG.md` and `verification/edge`.

### 1.7 Static front end and tabs
- README "Front-end structure" (README:119-184) sets four layers for the **EDGE single-page app**:
  - transport: `edge-client.js`;
  - the Orc response view: `edge-view.js`, used for Orc only;
  - words: `edge-labels.js`;
  - look: `index.html`.
- `preview/edge_preview.py` round-trips only `index.html` and `static/*.js`. It has no knowledge of the sub-apps (grep).
- A tab is added in about ten places today. Backtest is the model:
  1. `index.html:10614` nav array `[label, route]`;
  2. `index.html:10653` Shell's `disabled: !["monitor","terminal","backtest"].includes(r)`;
  3. a page component that renders `Shell` + `<iframe class="terminal-frame" src="/backtest-app/" title=EdgeLabels.backtest.frameTitle>` (`index.html:10804-10808`);
  4. `App.currentPath` (`index.html:12432`);
  5. `go()` allowlist and path map (`index.html:12447-12448`);
  6. the render switch (`index.html:12460`);
  7. `edge-labels.js:131-132` `backtest:{nav,frameTitle}`;
  8. `main.py:281-288` adds `@app.get('/backtest')` to the paths served by index;
  9. `main.py:347-359` adds the page and hashed-asset routes;
  10. `main.py:242` maps the CSP by path prefix.
- Tests pin this:
  - `test_backtest.py:1441-1447` checks the labels come from `edge-labels.js` and that no literal `"Backtest"` appears in the page;
  - `test_backtest.py:1993` asserts the tab list is exactly `['Monitor','Terminal','Backtest']`, so it must change for a Screener tab.
- `index.html` still carries `.screener-*` and `.watchlist-*` CSS (lines 2185-2309, 2494-2522, 7698-8286, 9106) and `.nav-watchlist` (6911) from the original `final 8 oct.html`. There is no markup or behaviour behind them.

### 1.8 Vite sub-apps and the image
- Terminal and Backtest each use `package.json` (vite 7.1.9, typescript 5.9.3, vitest 3.2.4, `lightweight-charts` 5.2.1) and a `vite.config.ts` with `base:'/<name>-app/'`.
- Each builds one IIFE script loaded at the end of `<body>` (`classicScriptAtEnd`), with `inlineDynamicImports`, so no inline script is emitted. That fits `script-src 'self'`.
- Backtest has three build modes: production, `--mode smoke` and `--mode fixture`. A 1:1 visual check exists (`tests/visual/compare.mjs` + `diff.py`).
- Dockerfile stages:
  - `node:22-slim AS terminal` → `/build/static/terminal-app`;
  - `node:22-slim AS backtest`, which also copies `terminal/src`, because the shared core imports the indicator formulas;
  - final `python:3.12-slim` with `COPY --from=…` into `static/*-app`, running as uid 10001 (`Dockerfile:3-33`).
- The build context is `apps/edge-bff` (service `rootDirectory`). **INFERENCE:** a Screener sub-app may import only from inside `apps/edge-bff` (`terminal/src/calc`, `backtest/src/core`), not from `apps/backtest-worker`.
- The asset route accepts only `[A-Za-z0-9_-]+(\.[A-Za-z0-9_-]+)*\.(js|css|woff2|svg|png)` (`main.py:33`). A separate `.json` or `.wasm` asset would answer 404, so data must be bundled.
- `.dockerignore` excludes each sub-app's `node_modules`, `tests`, `dist*` and `static/<name>-app`. `test_backtest.py:1497-1524` pins the exact Dockerfile `COPY` list and the ignore rules, so it must change for a new stage.
- The prototype vendors TradingView Lightweight Charts **v5.2.1** inline (prototype line 553). This is the same version EDGE already installs from npm, so no vendored copy is needed (INFERENCE).

### 1.9 Tests and CI
- `apps/edge-bff/tests`: pytest needs a **disposable** Postgres (`EDGE_TEST_POSTGRES_URL`). It creates a temporary database, applies the `edge_bff` migrations, and creates `public.market_private` to prove the runtime role cannot read it (`conftest.py:11-28`; `test_edge.py:112,128`).
- Chromium tests use Playwright with `/usr/bin/chromium` or `EDGE_TEST_CHROMIUM`.
- The only GitHub workflow is `database-schema-docs.yml`. **No CI runs edge-bff or the sub-app tests**; they run by hand.

### 1.10 Deploy
- edge-bff: GitHub `rednightt33/saniti` `main`, `rootDirectory /apps/edge-bff`, Dockerfile, watch `/apps/edge-bff/**`, healthcheck `/ready` (120 s), restart ALWAYS, `sfo` × 1 (`railway.ts:181-190`).
- Service `c3656044-2817-44a7-9b55-54910bab416f`, domain `edge-bff-dev.up.railway.app` (RAILWAY_CHANGELOG:3841-3842).
- Pitfalls:
  - M248: two deploy sources for one service; the last deploy wins, in both directions.
  - M252: the PR merge commit `fdd00e7` was SKIPPED with "No changes to watched files" and was deployed by hand with `serviceInstanceDeployV2`. Status MITIGATED, cause OPEN.
  - M250: rack files overwritten under the same key during publisher runs (00:00–01:00 and 12:00–13:05 UTC) give `DATA_INTEGRITY`. Status OPEN; content-addressed keys were chosen as the fix.
- **INFERENCE:** a Screener inside `apps/edge-bff` deploys with edge-bff automatically, still subject to M252. After every merge, check the deployment for the merge commit.

---

## 2. Q1: where the Screener page and API should live

### 2.1 Page (PROPOSED)
`apps/edge-bff/screener/` is a Vite + TypeScript sub-app, a module-by-module port of the prototype, as Terminal and Backtest are. Its own header is already `hidden` in the prototype (line 531), which fits a frame under the EDGE top bar. Why:
- **(FACT)** It gets the same origin, cookie and CSRF as the other tabs, with no CORS and no second sign-in.
- **(FACT)** It runs under the strict sub-app CSP (no inline scripts). The prototype has 0 inline `on*=` handlers and 39 `innerHTML` writes with an `esc()` helper. It loads Google Fonts Inter, which the CSP already allows.
- **(INFERENCE)** It reuses `backtest/src/core` (registry, conditions, datafile, flow) and `terminal/src/calc/indicators.ts` (the 53 formulas), so values match the Terminal and Backtest by construction.

The alternative, a new public service, would need its own authentication (terminal-api has its own sign-in), CORS and an origin rule. **Not recommended.**

### 2.2 API (PROPOSED)
`app/screener.py`, mounted with `screener.routes(app, session, write)` beside `backtests.routes` (`main.py:397`). Its shape:
- `ScreenerError` in the contract shape;
- `ScreenerStore` over `Store`, mapping `UndefinedTable` to 503 `SCREENER_NOT_READY`;
- `guard()` answering 503 `SCREENER_DISABLED` when its compute backend is not configured (only if a backend exists, see 2.3);
- request bodies read through the same `loads()` (move it to a shared helper, or import it from `backtest.py`).

Routes, a suggested set:

| Method / path | Purpose |
|---|---|
| GET `/api/v1/screener/catalog` | registry indicators (53) with defaults, universe groupings, `data_through`; cached like the backtest catalog |
| POST `/api/v1/screener/run` | definition → matches/rows (only when screening runs server-side, 2.3 B/C) |
| GET `/api/v1/screener/screens` · PUT/DELETE `/api/v1/screener/screens/{screen_id}` | saved screens (section 3) |
| GET `/api/v1/watchlist` · PUT/DELETE `/api/v1/watchlist/{ticker}` | the owner's watchlist (section 3) |

Route ordering matters, as with `/api/v1/backtests/catalog` before `/{request_id}` (`backtest.py:1056` vs `1120`). Every write uses `Depends(write)`, never `session` alone (see 5.3).

### 2.3 Where the screening is computed (PROPOSED options; the decision belongs to the compute auditors and the user)

| Option | Convention fit | Facts that bear on it |
|---|---|---|
| A. In the browser over the rack (as the Backtest preview: `/api/terminal/v1/bundle` + presigned files + shared core, IndexedDB cache `terminal-files`) | No new service, no new table | One bundle per ticker (`terminal-api main.py:356-411`). About 845 tickers (catalog 2026-10-27). The gateway subscriber's quotas are TEMPORARY 1e9 (DATABASE_CHANGELOG:2699-2702); the defaults are 60 files/h, 30 tickers/h, 150 tickers/day, 300 MB/day (`20261025_100:80-83`). M250 during publisher runs. |
| B. A private worker (new `screener-worker`, or a route in `backtest-worker`) reached as `http://<svc>.railway.internal:8080` with a key header | The exact backtest pattern (config pair, `ask()`, relay on the event loop) | backtest-worker computes "one preview at a time" (CONTRACT.md section 8) and is CLI-deployed. Putting screens there shares its lane, which the "existing Backtest worker must not break" rule warns against (INFERENCE). |
| C. A daily snapshot of default-parameter values published to the rack by terminal-publisher, with A or B for custom parameters | Fits the "rack" design (BACKTEST-LOAD plan, a shared rack loader) | Publisher runs twice a day; PLAN.md:898-960 proposes a rack-versioned catalog and a shared loader. |

Under every option, **edge-bff must not query market tables**: its role has no SELECT on any of the 87 public relations (FACT), and granting one would break the "no market data in edge-bff" design (README:236-239; CONTRACT.md section 1).

### 2.4 Touch-point checklist for the Screener tab (PROPOSED, from the Backtest precedent)
- `index.html`: the six places listed in 1.7.
- `edge-labels.js`: `screener:{nav:"Screener", frameTitle:"Stock screener"}`. All labels stay English (README:169-172).
- `main.py`: `@app.get('/screener')`; `SCREENER_APP`; page and asset routes; `SCREENER_CSP` (= `TERMINAL_CSP` if it reads presigned files, else without the bucket in `connect-src`); the middleware branch.
- `Dockerfile`: a `screener` stage plus `COPY --from=screener`.
- `.dockerignore`: `screener/node_modules`, `screener/tests`, `screener/dist*`, `static/screener-app`.
- Tests: the tab and CSP test; the browser tab test (update `['Monitor','Terminal','Backtest']`); the image-context test (COPY list).
- `README.md`: a "Screener tab" section.
- `BACKTEST_END_TO_END.md` and `CONTRACT.md`, if Send to Backtest changes the Backtest boot (AGENTS.md requires reading both before a Backtest change).
- The Cmd/Ctrl+K key: EDGE's top bar shows "Search markets — Coming soon" (`index.html` Shell `effect0`), while the prototype binds the same key to its own search. **INFERENCE:** inside the frame the frame wins while it has focus, so the two do not clash technically, but the user sees two behaviours for one key.

---

## 3. Q2: saved screens and watchlist storage

### 3.1 What exists (FACT)
- Server side: nothing.
  - Live catalog: no relation named like `%watch%`, `%screen%`, `%prefer%`, `%saved%` or `%favorit%` in any schema of the market Postgres. Its schemas are `ai_audit`, `edge_bff`, `migration_archive`, `public` and `terminal`.
  - `git grep -i watchlist` finds only CSS in `static/index.html`. `screener` appears in `index.html` CSS, PLAN.md and an unrelated `find_condition_runs` note in `apps/market-ai-backend/README.md:48`.
  - FUTURE_PLAN.md and PLAN.md have no item on server-side user objects.
  - The schemas of Orc (AI_*) and terminal (`terminal.*`: subscribers, sessions, quotas, access log) hold no such object either (live table list).
- Browser side:
  - The prototype: `localStorage` `edge-screens` (array of `{name, date, state}`; prototype 1187-1207, 1455-1456, 1645-1651), `edge-metrics` ("My metrics", 1144), `edge-watchlist` (a set of tickers, 1515) and `edge-scr-theme` (1154, 1711).
  - The Terminal keeps its user state in `localStorage` `ml.*`: `ml.symbol` (`main.ts:117`, `live.ts:164`), `ml.ind.v1` (indicator list with parameters, `indicators.ts:193`), `ml.drawings.<symbol>` (`drawings.ts:42`, a "persistence adapter (backend: replace the bodies with fetch calls)"), plus panel and window state.
  - The Backtest keeps only `ml.bw` and `ml.panel` (`layout.ts:12-31`).
  - `edge-client.js:139` removes four legacy keys at load; none collides with the prototype's keys.
  - **INFERENCE:** prototype data saved on another origin (`file://` or wherever the prototype was opened) cannot be read by EDGE, so there is nothing to migrate.

### 3.2 Choice (PROPOSED)
- **Server tables** for saved screens and the watchlist: durable across browsers and devices, and owner-scoped like everything else in `edge_bff`.
- Keep in `localStorage` only per-browser conveniences: theme, panel sizes, preview open/closed, the last open screen. Use a `scr.*` or `ml.scr.*` prefix rather than the prototype's `edge-*`, because `edge-*` is the EDGE shell's namespace on the same origin.
- **Open decision:** whether "My metrics" (named indicator + parameter set) become a third table, a `kind` column, or stay in the browser.

### 3.3 Minimal schema (PROPOSED; draft: `proposed_migration_screener_DRAFT.sql` in the scratch folder; not applied, not syntax-checked against a server)

```sql
CREATE TABLE edge_bff.screener_screens (
  screen_id text PRIMARY KEY CHECK (screen_id ~ '^scr_[0-9a-f]{32}$'),
  owner_key text NOT NULL,
  name text NOT NULL CHECK (length(name) BETWEEN 1 AND 120 AND name = btrim(name)),
  definition jsonb NOT NULL CHECK (jsonb_typeof(definition)='object' AND octet_length(definition::text) <= 65536),
  schema_version integer NOT NULL CHECK (schema_version >= 1),
  registry_version text CHECK (length(registry_version) BETWEEN 1 AND 200),
  revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),      -- optimistic concurrency: 409 on a stale revision
  created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (owner_key, name));                                     -- the prototype replaces a screen of the same name
CREATE INDEX screener_screens_owner_updated ON edge_bff.screener_screens(owner_key, updated_at DESC);
CREATE TABLE edge_bff.watchlist_items (
  owner_key text NOT NULL,
  ticker text NOT NULL CHECK (ticker ~ '^[A-Z0-9]{1,12}$'),     -- terminal-api's ticker rule (backtest.py:34)
  added_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (owner_key, ticker));
-- + COMMENTs; REVOKE ALL FROM PUBLIC;
-- GRANT SELECT,INSERT,UPDATE,DELETE ON screener_screens; GRANT SELECT,INSERT,DELETE ON watchlist_items TO edge_bff_runtime;
-- $preflight$ (schema/role exist, tables absent) and $verify$ (each grant one call at a time; no TRUNCATE/REFERENCES/
-- TRIGGER and no UPDATE on watchlist_items; PUBLIC nothing); rollback body as a comment.
```

Required companions (from the conventions, FACT on what each file enforces):
- `scripts/provision_edge_bff_login.py`: add the grants, or it refuses.
- `tests/conftest.py`: apply the migration and add to the TRUNCATE list.
- Migration tests modelled on `test_the_migration_refuses_*`.
- `README.md` "Persistence and ownership".
- `DATABASE_CHANGELOG.md`, with the live read-back recorded under `verification/`.
- Store methods with `WHERE owner_key=%s` on every statement.
- Limits enforced in code with refusal codes, for example `SCREEN_LIMIT` (422) and `WATCHLIST_LIMIT` (422), as `PIN_LIMIT` does (`store.py:297-298`). Values to decide; ≤500 is the existing pin precedent.

No automatic purge: these are user-owned objects; README:242-244 records that UI metadata is not purged either.

Open decisions: one watchlist (prototype) or several named lists (EDGE's leftover CSS has `.watchlist-selector .new-watchlist`, `index.html:8278`); per-screen limits; whether the definition is validated server-side against the registry (edge-bff validates no backtest field either: README:55-57).

---

## 4. Q3: Send to Backtest

### 4.1 Facts about the receiving side
- The Backtest frame always opens `/backtest-app/` with a **fixed `src`** (`index.html:10807`). Switching tab replaces the frame, so the Backtest page **boots again each time** the tab opens (`App` renders one page at a time, `index.html:12460`).
- `boot()` (`app.ts:32-52`): catalog → `applyCatalog()` (defaults: MAPI or the first stock, the period, no picked stocks; `state.ts:105-113`) → `load()` → bind → render. It reads **no URL, hash, `sessionStorage` or strategy key**; only `ml.bw` and `ml.panel` (`layout.ts`).
- The page state holds **cards** (`LegacyCard | RegCard`, `api/types.ts`; `core/catalog.ts:61-67, 123-127`). `request.ts:24-52` converts state to wire; **no wire→card conversion exists**.
- Limits: `limits.max_conditions` (per list, `reg.ts withinLimit`), and `limits.max_portfolio_tickers`, 12 by the PF decision (CONTRACT.md lines 6-8). Ops that Backtest's `RegCard` accepts are `gt`, `lt`, `ca` and `cb` only.
- The prototype's `openSend`:
  - builds `{v:1, source:'EDGE Screener', screen, date, mode, tickers:[{tk,px,vol}], conds, logic, atLeast}` and a link `backtest.html#import=<base64 JSON>` (prototype 1675-1693);
  - its `toBacktest` maps 13 prototype keys onto Backtest legacy types `rsi, stoch, adx/dmi, macd, ma, macross, volspike, breakout, bb, fnet, broker, top5`, whose op codes and parameter keys all exist in `LEGACY` (`catalog.ts:41-56`; compared field by field);
  - `px` and `vol` are synthetic values the Backtest does not use.
  - **UNKNOWN:** whether the threshold units (for example `fnet` in Rp B) match in every case; the compute or parity auditors should confirm.
- In-repo precedent:
  - The parent page writes `sessionStorage` `edge-side-attach:<conversation_id>` (`index.html:10951`).
  - The same-origin framed side chat reads it once and deletes it (`index.html:10973`).
  - Chromium test `tests/test_ask_branch.py:70-84` proves the attached chip appears in the frame.
  - Separately, the Terminal reads `localStorage` `ml.symbol` at boot (`main.ts:117`), so "open this ticker in Terminal" needs no Terminal change.

### 4.2 Options

| Option | How | Fit | Cost / risk |
|---|---|---|---|
| **sessionStorage handoff (PROPOSED)** | The Screener frame writes `edge-backtest-import` = `{v:1, source:'screener', screen_name, mode, ticker\|tickers, entry:{logic, at_least, cards:[RegCard\|LegacyCard]}, left_out:[{text, reason}]}`; then it asks the shell to go to `/backtest`; Backtest `boot()` reads and deletes the key once after `applyCatalog`, builds cards through `legacyCard()` / registry defaults, runs `withinLimit` and the core validation, and shows a toast naming what was left out | Same-origin; tab-scoped; one-shot; the data never in the URL, history or logs; same pattern as the tested side-chat handoff | Needs a small Backtest boot change, which touches the BACKTEST-LOAD plan (PLAN.md:898-960, same `app.ts`); coordinate with that session. **INFERENCE:** sessionStorage is shared between same-origin frames of one tab, as the side chat proves for parent→frame; frame→shell→frame must be locked by a new Chromium test. |
| URL hash `/backtest#import=<base64>` (prototype) | The shell passes the hash into the frame `src` | Copyable link; no storage | `BacktestPage` must forward the hash (fixed `src` today); the payload sits in browser history; length limits; stale links outlive their data |
| postMessage carrying the data | The Screener frame → shell → new Backtest frame | Explicit | Both frames are never alive together, so the shell must buffer; it adds the most code |
| Server-side draft | `POST /api/v1/backtests/drafts` → id; `/backtest?draft=<id>` | Cross-device, auditable | A new table, routes and migration for a single-user, one-shot action; not needed now |

Navigation: the frame cannot call the shell's `go()` today. **PROPOSED:** the shell listens for `message` events with `event.origin === location.origin` and `event.source` equal to its own frame, and accepts only `{type:'edge-nav', route:'backtest'|'terminal'}`, calling `go(route)`. Data never goes in the message. Alternative: a `window.EdgeNav` hook the same-origin frame calls through `parent`.

Rules for the payload (PROPOSED):
- Registry indicators travel as `RegCard` (`ind`, `p`, `lhs`, `op`, `rhs`), so default and custom parameters pass unchanged.
- Screener-only operators (anything other than `gt`, `lt`, `ca`, `cb`), fundamental conditions and universe filters go in `left_out` with a reason, as the prototype's dialog already shows ("Screen only").
- Portfolio: at most `max_portfolio_tickers` (12) picked stocks. Above that, the dialog asks which 12 (open product question).

---

## 5. Q4: what must never reach the browser, and how it is guaranteed

### 5.1 Never sent, with the mechanism (FACT)

| Secret / private item | Mechanism |
|---|---|
| `EDGE_DATABASE_URL` (password), DB error text, row values | Only in `Settings`; unexpected exceptions become a generic 503 (`main.py:215-218`); logs through `failure_of` (`backtest.py:138-167`) |
| `MARKET_AI_ORC_API_KEY`, `TERMINAL_PROXY_KEY`, `BACKTEST_WORKER_KEY` | Added only on server-to-server calls (`client.py:36`, `main.py:375`, `backtest.py:300-301`); private hosts enforced (`config.py:75-98`) |
| `EDGE_SESSION_SECRET`, password verifier | Server-side HMAC and scrypt only (`security.py`) |
| Session token | HttpOnly cookie; JavaScript never reads it; the DB stores only sha256 (`main.py:246-247, 422`) |
| Owner identity | Server-chosen `settings.owner`; never accepted from the browser (README:247) |
| Internal addresses (`*.railway.internal`) and private keys in upstream JSON | `public_data` redaction plus the `PRIVATE_KEYS` filter on Orc answers and worker errors (`client.py:12-25`; `backtest.py:175-182`) |
| Bucket credentials | Never in edge-bff; the browser receives only presigned URLs with a TTL from terminal-api (`terminal-api main.py:375-386`); bucket CORS allows GET/HEAD from `edge-bff-dev.up.railway.app` (RAILWAY_CHANGELOG:4597) |
| Admin and sign-in routes of terminal-api | The gateway allowlist forwards only `manifest`, `reference`, `history`, `logo`, `files` and `bundle` (`main.py:34-36, 367-368`) |
| Market tables | edge-bff's role can read none (live: 0 of 87) |
| Cross-site use | Exact Origin, CSRF, SameSite=Strict, no CORS, `frame-ancestors 'self'`, `nosniff`, `no-store` |

### 5.2 For the Screener specifically (PROPOSED)
- Every write route uses `Depends(write)`.
- Every store statement filters `owner_key`.
- Saved definitions are bounded by the 128 KiB body cap and a column CHECK.
- Company and sector names from the reference file are rendered as text, or through `esc()` without exception. The prototype mixes `innerHTML` with `esc()` in 39 places; EDGE's rule is "AI text uses text nodes, never raw HTML" (README:11).
- A server-side compute backend is reached only through private networking with a ≥32-character key, and its errors are relayed through `error_of` + `public_data`.
- Sign-out leaves the Screener's `localStorage` conveniences in place, as it does for the other tabs. Hold nothing sensitive there.

### 5.3 Gaps the Screener must not copy (FACT; low severity, recorded for the lead)
1. `POST /api/v1/dev/manual/steps/{step_id}` uses `Depends(session)`, not `write`, so it has no CSRF check (`main.py:547-554`). Its test's "no CSRF token" case sends no Origin either, so the 403 comes from the Origin check (`tests/test_manual_routes.py:33`; `test_edge.py:14-17`). The exact-Origin middleware still blocks cross-site posts. This deviates from README:273, "all writes require … X-CSRF-Token".
2. The terminal gateway relays terminal-api's JSON **without** `public_data` (`main.py:382-386`), unlike the Orc and worker relays.
3. 401 and 403 from the auth dependencies are `{"detail": …}`, not the error shape (`main.py:249, 254`).

---

## 6. Q5: Railway topology relevant to a Screener (FACT unless marked)

| Item | Fact (source) |
|---|---|
| Project / env | `lucid-patience` `8aef1702-030b-49cb-9df7-5ac2e0a42691` / dev `4d3e5af2-302b-4a2e-84e2-7d7476d6ff49` (PROJECT_CONTEXT.md:10-12) |
| edge-bff | `c3656044-…`, GitHub `main`, root `/apps/edge-bff`, watch `/apps/edge-bff/**`, Dockerfile, 1 × `sfo`, public `edge-bff-dev.up.railway.app` (railway.ts:181-190; RAILWAY_CHANGELOG:3841-3842) |
| backtest-worker | `9156a5c3-…`, **CLI upload** of its build context, `sfo`, private only, no Postgres or bucket credentials (RAILWAY_CHANGELOG:4694-4706; railway.ts:176-180). The IaC says builder `RAILPACK` while the changelog records builder `DOCKERFILE` (INFERENCE: the IaC field is stale) |
| terminal-api | `ba235c68-…`, **CLI upload**, `sfo`; public `terminal-api-dev.up.railway.app` and private `terminal-api.railway.internal:8080`; holds the bucket credentials and its own DB login on schema `terminal` (RAILWAY_CHANGELOG:4544-4569) |
| terminal-publisher | `523a3135-…`, **CLI upload**, cron twice a day (07:30 and 19:00 WIB per the 2026-10-26 entry), writes bucket `terminal-display` (region **`sin`**) |
| market-ai-orc | GitHub `main` `/apps/market-ai-orc`, private `market-ai-orc.railway.internal:8080` |
| Postgres (market) | `sfo`, private endpoint `postgres`, TCP proxy, 4 GB memory limit (railway.ts:9-13); PostgreSQL 18.6 (live); `max_connections` 500 (PLAN.md BACKTEST-LOAD) |
| Other databases | `Postgres-E8GM` (web research, `sfo`, railway.ts:7-8). `DB2` is **not** in `railway.ts` today; it was captured in the 2026-09 pull (RAILWAY_CHANGELOG:3664). Current existence: UNKNOWN (not read) |
| Other buckets | `market-sql-datasets`, `market-ai-conversation-outputs` and `market-ai-audit-artifacts` in `sjc` |
| Private networking | http over `<service>.railway.internal:8080`; edge-bff refuses any other host for Orc, terminal-api and backtest-worker outside `EDGE_ENVIRONMENT=local` (config.py:75-98) |
| IaC drift | `railway.ts:189` lists edge-bff variables without `EDGE_TERMINAL_URL` and `TERMINAL_PROXY_KEY`, which were set live on 2026-10-25 (RAILWAY_CHANGELOG:4594-4595) |
| Deploy pitfalls | M248 (two sources for one service), M252 (merge commit SKIPPED), M250 (deploy and read outside publisher windows 00:00–01:00 and 12:00–13:05 UTC) |

**INFERENCE for the Screener:**
- Option A (2.3) adds no Railway resource; the page ships with edge-bff from `main`.
- Option B adds a private service. If it is CLI-uploaded like backtest-worker, it needs the same rollback discipline, and a new `SCREENER_*` URL/key pair on edge-bff set by Railway reference (as `BACKTEST_WORKER_KEY = ${{backtest-worker.BACKTEST_WORKER_KEY}}`).
- Option C changes terminal-publisher (CLI) and the rack layout; it should wait for the M250 content-addressed-keys fix.

---

## 7. Coordination risks (INFERENCE)
- PLAN BACKTEST-LOAD (approved for planning, not "go") changes the same Backtest `boot()`, adds a shared rack loader and an edge-bff connection pool. The Screener's rack reads and the Send to Backtest import should build on that loader and land after or with it. Two sessions editing `apps/edge-bff/backtest` caused the M248 overwrites before.
- No CI: every new test must be run by hand before merge, and the image-context and tab-list tests will fail until updated.
