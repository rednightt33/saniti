# EDGE private frontend and BFF

One service serves the supplied vanilla HTML, authenticates one private user, queues delivery to the existing Orc,
and exposes persisted lifecycle snapshots over SSE. Standard follows Orc's configured mode. EXEC-MODELS (user
2026-10-13): each message may choose one of Orc's offered models and a reasoning level next to the composer (starting on
DeepSeek V4.1 Flash high, kept in this browser as `edge-model-choice`); Orc checks the choice. There is no
provider/path override and no per-token, reasoning, or per-tool stream.

The HTML comes from `final 8 oct.html`; its original CSS and workspace renderer are retained. Demo conversations,
market values, result tables, prices, sources, upload simulation and timed execution are removed. The renderer
accepts canonical response types rather than a fixed research template. AI text uses text nodes, never raw HTML.
`static/edge-client.js` holds the session/API/SSE/adapters separately from view handlers (see Front-end structure).

## Terminal tab (EXEC-TERMINAL-API T3-T5, 2026-10-25)

The financial terminal is a separate page, `terminal/` (TypeScript + Vite), built into `static/terminal-app/` by the
Dockerfile's Node stage (not kept in git) and shown under the EDGE top bar in a frame at `/terminal` (Terminal tab).
It is a module-by-module port of the reference page `03-terminal-right-panel.html`; keep it 1:1 with it.

| Need | Where |
| --- | --- |
| a section of the page (chart, statistics, flow, events, drawings, indicators, broker panel, search) | `terminal/src/app/<section>.ts` |
| data shapes; live data from the rack; the reference's synthetic data | `terminal/src/data/types.ts`, `live.ts`, `fixture.ts` |
| an indicator formula (spec `verification/terminal_api/INDICATOR_SPEC.md`) | `terminal/src/calc/indicators.ts`, tests `terminal/tests/calc` |
| the gateway to terminal-api (data routes only, EDGE session + CSRF) | `app/main.py` (`forward_terminal`), `tests/test_terminal.py` |
| saved chart layouts (EXEC-TERMINAL-LAYOUTS): the menu, what a layout holds (`LAYOUT_KEYS`) | `terminal/src/app/layouts.ts`, `terminal/src/data/layoutsApi.ts`, tests `terminal/tests/data/layouts.test.ts` |
| the layouts API on edge-bff, table `edge_bff.terminal_layouts` (migration `20261106_001`) | `app/layouts.py`, `tests/test_layouts.py` |
| indicator presets (EXEC-IND-PRESETS): Save as preset, the My presets group of the Indicators window, the name and confirmation dialogs | `terminal/src/app/presets.ts`, `terminal/src/app/indMenu.ts`, `terminal/src/ui/dialogs.ts`, `terminal/src/data/presetsApi.ts` |
| the presets API on edge-bff, table `edge_bff.indicator_presets` (migration `20261106_002`) | `app/presets.py`, `tests/test_presets.py` |
| drawings (EXEC-DRAW-PANES): the price chart's, each Flow Timeline's and each indicator pane's, kept on the EDGE account | `terminal/src/app/drawings.ts`, `terminal/src/data/drawingsApi.ts`, pane ids in `terminal/src/app/indicators.ts` |
| the drawings API on edge-bff, table `edge_bff.terminal_drawings` (migration `20261107_001`) | `app/drawings.py`, `tests/test_drawings.py` |

Saved layouts (user 2026-11-06: "di akun edge. Tidak usah mengganti saham."), EDGE session, writes with CSRF:

| Route | Contract |
| --- | --- |
| GET `/api/v1/terminal/layouts` | `{layouts: [Layout without state], limit}` of the owner, the most recently opened first |
| GET `/api/v1/terminal/layouts/{layout_id}` | the Layout with `state` (setting name -> text); 404 `NOT_FOUND` |
| PUT `/api/v1/terminal/layouts/{layout_id}` | `{name, state, summary?, revision?}`: no `revision` creates (201), the revision it was read with replaces (revision + 1); 409 `REVISION_CONFLICT` (`details.revision`), 409 `NAME_TAKEN`, 422 `INVALID_INPUT` by field (more than 64 settings, text with NUL or an unpaired surrogate included), 422 `LIMIT_EXCEEDED` (65,536 bytes of state), 403 `LIMIT_REACHED` (the plan's `terminal.layouts_max`, at most 50 layouts; `details.limit` the capability key, `allowed`, `needed`); a body over 131,072 bytes is 413 before the route |
| PATCH `/api/v1/terminal/layouts/{layout_id}` | `{favorite?, opened?: true}`: the star, or the Recently used order; no revision |
| DELETE `/api/v1/terminal/layouts/{layout_id}` | 204; 404 `NOT_FOUND` |

Without the table (migration not applied) every route answers 503 `LAYOUTS_NOT_READY` with `Retry-After`; `/ready` never
reads it. `layout_id` is `lay_` and 32 lowercase hex digits, made by the page.

Indicator presets (user 2026-11-06: "men-save indikator beserta dengan filternya"; "Q1 A" on the EDGE account, "Q2 A"
the full version): one indicator with its parameters, filters and style, added again from the Indicators window on any
ticker. A preset is a template: changing the indicator on the chart does not change it. EDGE session, writes with CSRF:

| Route | Contract |
| --- | --- |
| GET `/api/v1/terminal/presets` | `{presets: [Preset with config], limit}` of the owner, favorites first, then the most recently used |
| PUT `/api/v1/terminal/presets/{preset_id}` | `{name, def_id, config, summary?, revision?}`: no `revision` creates (201), the revision it was read with replaces (revision + 1); `config` is `{params, style?, on?, fold?}` (objects at most 8 deep, text without NUL or an unpaired surrogate, at most 16,384 bytes); 409 `REVISION_CONFLICT` (`details.revision`), 409 `NAME_TAKEN`, 422 `INVALID_INPUT` by field, 422 `LIMIT_EXCEEDED` (`preset_bytes`), 403 `LIMIT_REACHED` (the plan's `terminal.presets_max`, at most 100) |
| PATCH `/api/v1/terminal/presets/{preset_id}` | `{favorite?, used?: true}`: the star, or the used order; no revision |
| DELETE `/api/v1/terminal/presets/{preset_id}` | 204; 404 `NOT_FOUND` |

Without the table every preset route answers 503 `PRESETS_NOT_READY` with `Retry-After: 30`; the rest of the Terminal
works. `preset_id` is `ipr_` and 32 lowercase hex digits, made by the page. When a preset is added, a parameter the
indicator no longer has goes back to its default; a preset of an indicator the Terminal no longer has is listed as "no
longer available" and cannot be added.

Drawings (user 2026-11-07: "semua gambar harus di simpan di akun EDGE, sama seperti trading view"; panes "1A", "2A"): one
set per ticker and place, `set_id` `chart` (the price chart), `flow` (the Flow Timeline) or `pane_` and the indicator
pane's 16 hexadecimal digits (kept with the indicator in `ml.ind.v1`, so a layout brings its panes' drawings back). The
panes take the Flow Timeline's tools (lines, Brush, Text); a pane's drawings go with the pane when the user removes it and
come back with Undo. EDGE session, writes with CSRF:

| Route | Contract |
| --- | --- |
| GET `/api/v1/terminal/drawings?ticker=BBRI` | `{sets: [{ticker, set_id, drawings, revision, ...}], limits}` of the owner for that ticker |
| PUT `/api/v1/terminal/drawings/{ticker}/{set_id}` | `{drawings, revision?}`: no `revision` creates (201), the revision it was read with replaces (revision + 1); `drawings` is the drawing library's list (at most 10 levels, at most 100,000 bytes); 409 `REVISION_CONFLICT` (`details.revision`), 422 `INVALID_INPUT` by field, 422 `LIMIT_EXCEEDED` (`set_bytes`), 403 `LIMIT_REACHED` (the plan's `terminal.drawings_max`, at most 5,000 sets per owner) |
| DELETE `/api/v1/terminal/drawings/{ticker}/{set_id}` | 204; 404 `NOT_FOUND` |

Without the table every drawings route answers 503 `DRAWINGS_NOT_READY` with `Retry-After: 30`; the page then keeps the
drawings in the browser (and says so once) and moves them to the account the next time it can read it. The sets kept in
the browser before (`ml.drawings.*`) move to the account once, merged by drawing id. A change is written 0.4 s after the
last one (a drag sends many); one still waiting when the page goes away is sent then (keepalive).

Build and checks, from `terminal/`: `npm ci`, `npm run build` (typecheck, then the public build into
`static/terminal-app/` and the admin's lab build into `static/terminal-app-lab/`, 3f: LIVE_PROMOTION.md section 3),
`npx vitest run tests/calc`
(parity), and the 1:1 check `TERMINAL_REFERENCE_HTML=<reference file> node tests/visual/compare.mjs <out>` then
`python3 tests/visual/diff.py <out>` (must report 0 differing pixels). `/terminal-app/?fixture=reference` runs the
page on the reference's synthetic data, but only in a fixture build (ERRORS M469): run `npx vite build --mode fixture`
before the 1:1 check (`compare.mjs` refuses a build without fixture mode) and `npm run build` after it. The production
build (`npm run build`, the one the Dockerfile makes and edge-bff serves without a session) has no fixture mode: the
switch is `import.meta.env.MODE === 'fixture'` (not `DEV`, which follows `NODE_ENV`), so the fixture module and its
broker summary are dropped from the bundle (`tests/data/fixture_bundle.test.mjs`).

## Backtest tab (EDGE backtest, 2026-10-26)

Rules and decisions: `backtest/CONTRACT.md`; wire types: `backtest/src/core/contract.ts`. The page `backtest/`
(TypeScript + Vite) is built by the Dockerfile's `backtest` stage into `static/backtest-app/` (not kept in git) and
shown under the EDGE top bar in a frame at `/backtest` (Backtest tab, next to Terminal). `/backtest-app/` has the
terminal page's CSP (its own scripts only, inline style attributes, EDGE's own Inter, and `connect-src` to the bucket
because the signal preview downloads the files `/api/terminal/v1/bundle` presigns). The computation runs in the private
`backtest-worker` (Node); edge-bff queues the jobs, keeps the results and counts the trials.

| Method/path (session cookie; POST with Origin + `X-CSRF-Token`) | Result |
| --- | --- |
| GET `/api/v1/backtests/catalog` | the worker's `Catalog` as it is (each ticker with its `groups`, the portfolio picker's `groupings`, `limits` with `max_portfolio_tickers`), kept 60 s (the last one while the worker does not answer) |
| POST `/api/v1/backtests` | body = `BacktestRequest` + optional `client_request_id`; the worker checks it (`/v1/validate`, its 422/424 relayed as they are), then 202 `{request_id, state, created}`; the same `client_request_id` returns the same job (a portfolio's picked stocks in another order are the same request, CONTRACT.md PF3), another request under it 409 `SUBMISSION_CONFLICT`; 429 `QUEUE_FULL` with 3 queued jobs |
| GET `/api/v1/backtests?limit=` | the latest jobs (30, at most 100), each `JobStatus` + its `request` |
| GET `/api/v1/backtests/{id}` | `JobStatus` (progress as the worker reports it) |
| GET `/api/v1/backtests/{id}/result` | the `core` part; in single mode with the ticker's events merged back (= the worker's `BacktestResult`); gzip; 409 `NOT_FINISHED`, 410 `RESULT_EXPIRED` |
| GET `/api/v1/backtests/{id}/events?ticker=X` | `{conditions, exits}` of one ticker (part `events:X`); 404 `EVENTS_NOT_FOUND` |
| POST `/api/v1/backtests/{id}/cancel` | 202 `JobStatus`: queued -> `CANCELLED` at once, running -> stopped at the worker by the loop; 409 `NOT_RUNNING` |
| POST `/api/v1/backtests/signals` | `SignalsPreview` of the picked stocks (`tickers`) from the worker (no job, no trial); latest wins per owner: 409 `PREVIEW_REPLACED` when a newer preview arrives first; newer is the page's own order where the body carries `client_order {page, seq}` (taken out before the worker; a preview its page had already sent a newer one of answers 409 at once and never reaches the worker, CONTRACT.md section 9, ERRORS M247) |

Errors are `{"error": {code, field?, message?, details?}}` (CONTRACT.md section 11). A body that is not a JSON object
(also one nested deeper than the parser takes, one with a number beyond a double such as `1e400` or an integer of
400 digits, or one with a string UTF-8 cannot encode, a lone surrogate such as `"\ud800"`) is 422 `INVALID_INPUT`,
before anything is relayed or a preview replaced. edge-bff checks no field of a request: the worker
does (for a portfolio 1 to `limits.max_portfolio_tickers` distinct published stocks, `INVALID_PORTFOLIO` /
`UNKNOWN_TICKER`), and edge-bff relays its refusal. The catalog, the validation at submit and the
signals preview are relayed calls: the worker's 4xx error is passed on with its status, and its own 504 `TIMEOUT`
(the call took longer than the worker's `BACKTEST_TIMEOUT_SECONDS`) is passed on as 504 with its error, so edge-bff
waits for an answer up to `BACKTEST_TIMEOUT_SECONDS` + 30 s (connecting stays limited to 30 s). The worker unreachable
or answering outside its API (a 504 without the worker's `TIMEOUT` error too) is 503 `BACKTEST_UNAVAILABLE`, the feature
off (no `BACKTEST_WORKER_URL`) 503 `BACKTEST_DISABLED`, the tables missing 503 `BACKTEST_NOT_READY` (`/ready` does not
read them). The relayed calls are awaited on the event loop, not in a thread, and a preview whose page went away is
cancelled, which closes its connection to the worker. Previews are latest wins (CONTRACT.md P8): a preview that arrives
while an older one of the same owner is still in flight ends that one (its worker call is closed, it answers 409
`PREVIEW_REPLACED`) and is sent to the worker once that call has ended, so at most one preview per owner is in flight.

Tables (migration `database/migrations/20261026_005_edge_bff_backtest.sql`): `edge_bff.backtest_jobs` (request,
lineage and variant hash from the worker, state QUEUED/RUNNING/FINISHED/FAILED/CANCELLED, progress, lease, error,
versions, sizes; one RUNNING job per owner), `edge_bff.backtest_results` (gzip JSON per `(request_id, part)`: `core`
and `events:<ticker>`, with bytes and sha256; deleted after 30 days) and `edge_bff.backtest_trials` (K3: one row per
owner, lineage and distinct variant of the finished runs' `meta.trials.variants`; never reset). A trial row holds the
daily Sharpe, kind and request of the latest run that reported the variant; its `recorded_seq` (identity) keeps the
place where it was first recorded. The loop passes a line's trials to the worker as `prior_trials` in `recorded_seq`
order: runs in the order they finished, each run's variants in its order. The runtime role gets only what the code
does: jobs SELECT/INSERT/UPDATE, results SELECT/INSERT/DELETE, trials SELECT/INSERT/UPDATE; PUBLIC gets nothing (the
migration's verify block checks both). No market data.

The loop (`app/backtest.py`, started with the ORC loop when `BACKTEST_WORKER_URL` is set) takes the oldest queued job
under a lease (`EDGE_LEASE_SECONDS`, heartbeat `EDGE_HEARTBEAT_SECONDS`), reads its line's trials and posts
`{job_id, request, context: {job_id, prior_trials}}` to the worker (`409 BUSY` = another job there: it waits; a post
left unanswered whose id the worker does not know, as one whose caller left while the worker read its reference lists,
is posted again, three attempts in all), reads its
status every `EDGE_POLL_SECONDS` (progress stored, cancellation forwarded; an ended job keeps the worker's final
progress), and on `FINISHED` fetches the result, stores its parts and its variants and marks the job `FINISHED` with
the versions in one transaction. The result is unpacked by edge-bff as it arrives and never past
`BACKTEST_MAX_RESULT_BYTES` of JSON (over it: `FAILED LIMIT_EXCEEDED`, nothing stored). The worker keeps a finished
result until its next job starts, so a result that could not be fetched is fetched again at the next poll; one that
was fetched but could not be stored because the database failed in a way a retry may mend (`OperationalError`) is
kept and stored again at every poll until `BACKTEST_TIMEOUT_SECONDS`, then `FAILED RESULT_NOT_STORED`; any other store
failure is `FAILED RESULT_NOT_STORED` at once. Any other database call around a job (the hand-over, the follower, the
heartbeat) that fails so is made again at the next poll or beat until the same deadline, an end until
`EDGE_LEASE_SECONDS` past it. A database failure is not counted as an unanswered worker call; each one is logged
(`backtest_result_store_failed`, `backtest_job_store_failed` with its `step`) with the exception's class and its
SQLSTATE or libpq's text without credentials, names or addresses. The lease token fences the follower; the expiry only
lets reap end a job its follower left. A follower that finds the job no longer its own (reap took it, or a write of its
own committed although the database's answer was lost) stops and logs `backtest_lease_lost` once, with the job's state
read then.
Measurement lines (EXEC-MU-RUNTIME Phase 0; `verification/edge_multiuser/runtime/backtest.md` section 7), INFO, ids,
hashes, counts, states and milliseconds only: `backtest_submit` (each submission: `request_key`, the sha256 of the
request in the worker's canonical form, to count identical requests; the validation and queue-insert times; a refusal's
code), `backtest_claim` (`queue_wait_ms`), `backtest_poll` (each status read: round trip, state, phase),
`backtest_job_timing` (one per job when the follower leaves it: queue wait, hand-over, the worker's own time, the poll
slack between its end and the read that saw it, result download, split and store, end to end; `JobTiming`) and
`backtest_preview` (each preview: outcome, the wait for the owner's older preview, the worker's answer time). The
module's lines reach the service log since this change: under uvicorn's own logging set-up an INFO line of
`edge_bff.backtest` used to find no handler and was dropped (`backtest_state` included).
A job is never sent twice: the worker forgetting it (`404 UNKNOWN_JOB`) or no longer keeping its result (`410
RESULT_GONE`: a newer job started there) is `FAILED WORKER_LOST` at once, not answering three times in a row is `FAILED
WORKER_LOST` too, as is a job reap took because its lease expired (edge-bff stopped while following it; the worker is
told to cancel it), and a job running longer than `BACKTEST_TIMEOUT_SECONDS` is cancelled and `FAILED TIMEOUT`.
Expired result parts are deleted when the loop starts and then once an hour.

"Required" variables have no default in the code: with `BACKTEST_WORKER_URL` set, edge-bff does not start without
them. The Railway dev column holds the dev values (the limits are initial values, re-measured in the dev E2E, K7b).

| Variable | Default | Railway dev | Meaning |
| --- | --- | --- | --- |
| BACKTEST_WORKER_URL | empty = feature off | `http://backtest-worker.railway.internal:8080` | the worker's private Railway endpoint (`http`, host `backtest-worker.railway.internal`; anything else is refused outside `EDGE_ENVIRONMENT=local`) |
| BACKTEST_WORKER_KEY | empty | `${{backtest-worker.BACKTEST_WORKER_KEY}}` (Railway reference; never a value here) | sent as `x-backtest-worker-key`; at least 32 characters; set together with the URL |
| BACKTEST_TIMEOUT_SECONDS | required | 900 (the worker's value) | longest job on edge-bff's side; the relayed calls wait this + 30 s for the worker's answer |
| BACKTEST_MAX_RESULT_BYTES | required | `${{backtest-worker.BACKTEST_MAX_RESULT_BYTES}}` (Railway reference) | the most JSON a result may unpack to; the same value as the worker's, which refuses a larger result before sending it |
| BACKTEST_QUEUED_PER_OWNER | 3 | 3 (default; not set) | queued jobs per owner (`429 QUEUE_FULL` above it); the worker's catalog reports its own value, default 3 |

Tests: `tests/test_backtest.py` (fake worker as a local HTTP server, disposable Postgres, one Chromium check of the
tab, and the image's build context: `.dockerignore` matched as Docker matches it, against the Dockerfile's COPY lines).

## Screener tab (EXEC-SCREENER, 2026-10-28)

Design: the approval report of EXEC-SCREENER (`EXEC.md`; TARGET ARCHITECTURE 6.14-6.17, API CONTRACT section 8, PAGE
LOAD SEQUENCE 6c); wire types: `screener/src/core/contract.ts`. The page `screener/` (TypeScript + Vite) is built by the
Dockerfile's `screener` stage into `static/screener-app/` (not kept in git) and shown under the EDGE top bar in a frame
at `/screener` (Screener tab, next to Backtest; wording in `static/edge-labels.js`). The stage places `terminal/src`
and `backtest/src` beside the page as in the repository: the screener core imports the Backtest core and, through it,
the Terminal's formulas, and the page reuses Terminal and Backtest page helpers (`tests/test_screener.py` checks that
every file the page reaches outside its folder is in those trees). `/screener-app/` has the backtest page's CSP except
the bucket (`SCREENER_CSP`: `connect-src 'self'` only): the page reads no rack file, every answer comes from
`/api/v1/screener`. Screens, previews and counts are computed by the private `screener-worker` (Node) from the rack;
edge-bff relays them, keeps the catalog and the universe per worker state, and stores the saved items and the watchlist.

Layout since EXEC-SCREENER-V21 (2026-11-06; the user's "Type A three-panel v21" design): Screen builder | Results |
Display chart under the filter + presets bar (`screener/index.html`, `screener/src/layout/`). An edit does not re-run the
screen: the table stays, marked out of date, until Screen now (`screener/src/run.ts` gate, `screener/src/screen-gate.ts`;
Alt+S, Ctrl/Cmd+Enter); a saved screen, the boot's last screen, Retry and a publication change run at once. Extra table
columns (`screener/src/extra-columns.ts`) are asked with an auxiliary POST run on a second `client_order.page`, pinned
with `data_version` to the table's publication, so it never replaces the table's run. Values are written in the
catalog's format (`entries.ts formatOfOpt`, `format.ts fmtValue`), never from the wire's coarse `Cell.unit`.
Since EXEC-SCREENER-ADD (2026-11-06) a condition is added in one window only, "Add a condition"
(`screener/src/add-condition.ts`): the page action Add indicator, Alt+A, "/", the builder's search box, "+", the quick chips
and My metrics' Add all open it; the detailed Indicators window is gone. The preview chart draws only the overlays whose
`unit` (on each overlay of the preview answer) is `price`.

| Method/path (session cookie; PUT, POST and DELETE with Origin + `X-CSRF-Token`) | Result |
| --- | --- |
| GET `/api/v1/screener/catalog` | the worker's `CatalogResponse` with edge-bff's own limits added to `limits[]` (`saved_items`, `watchlist`, `saved_definition_bytes`, `request_bytes`, each with its rule and one right and one wrong example; a limit the worker lists is kept as it is); `ETag` = sha256 of the JSON bytes, `If-None-Match` -> 304 |
| GET `/api/v1/screener/universe` | the worker's `UniverseResponse`; `ETag` / 304 as the catalog |
| POST `/api/v1/screener/run` | `RunRequest` -> `RunResponse`, relayed as sent (`client_order` included) and answered with the worker's gzip bytes and `ETag`; latest wins per (owner, page): 409 `SCREEN_REPLACED` |
| POST `/api/v1/screener/preview` | `PreviewRequest` -> `PreviewResponse`, as the run; latest wins per (owner, page) in its own lane: 409 `PREVIEW_REPLACED` |
| POST `/api/v1/screener/validate` | `ValidateRequest` -> `{valid, definition_hash, normalized}` or the worker's 422 |
| POST `/api/v1/screener/counts` | `CountsRequest` -> `CountsResponse` (the worker's limit on definitions), as the run |
| GET `/api/v1/screener/items?kind=screen\|metric` | `{items: SavedItem[]}` of the owner (one kind, or both without `kind`), latest changed first, each with `needs_review` |
| PUT `/api/v1/screener/items/{item_id}` | `{kind, name, definition, revision?}` -> the stored item: no `revision` creates, the revision it was read with replaces (revision + 1); validated by the worker first (`/v1/validate`, its refusal relayed); 409 `REVISION_CONFLICT` (the id exists, or a stale revision), 409 `NAME_TAKEN` (`name` per owner and kind), 404 `NOT_FOUND`, 403 `LIMIT_REACHED` (the plan's `screener.saved_items` per kind) |
| DELETE `/api/v1/screener/items/{item_id}` | 204; 404 `NOT_FOUND` |
| GET `/api/v1/screener/watchlist` | `{tickers: [{ticker, added_at}]}` (one list per owner) |
| PUT / DELETE `/api/v1/screener/watchlist/{ticker}` | 204, idempotent; 422 `INVALID_INPUT` (`ticker`, terminal-api's rule `^[A-Z0-9]{1,12}$`), 403 `LIMIT_REACHED` (the plan's `watchlist.per_list`, or `watchlist.lists` when the first list is made) |

Errors are `{"error": {code, field?, message?, details?}}`; every refusal edge-bff gives itself names the field where
there is one and the fix (AGENTS.md "Gates and evidence"). A body that is not a JSON object the contract can carry is
422 `INVALID_INPUT` before anything is relayed, as for the backtest (`backtest.loads`), and a body over 131,072 bytes
413 `REQUEST_TOO_LARGE` with its fix. The relayed calls are awaited on the event loop; the worker's 4xx error is passed
on with its status, its own 504 `TIMEOUT` as 504 (edge-bff waits `SCREENER_TIMEOUT_SECONDS` + 30 s for an answer), its
own 503 `SCREENER_NOT_READY` (no snapshot yet) as 503 with `Retry-After`; its worker-only 409 `DATA_VERSION_PENDING` (a
replica that has not loaded the requested publication yet) is asked once more on a new connection, then answered 503
`SCREENER_NOT_READY` with `Retry-After: 2`. Only the worker's refusals of the contract (report 8.8: `INVALID_INPUT`,
`INVALID_CONDITION`, `UNKNOWN_INDICATOR`, `PARAM_OUT_OF_RANGE`, `METRIC_UNAVAILABLE`, `LIMIT_EXCEEDED` 422,
`DATA_UNAVAILABLE`, `DATA_INTEGRITY` 424, `BUSY`, `DATA_VERSION_CHANGED` 409, `REQUEST_TOO_LARGE` 413), each at its
status, are passed on (internal addresses redacted); the worker unreachable or answering outside its API (another code
or status, a route it does not have, an answer over 16 MiB) is 503 `SCREENER_UNAVAILABLE` (logged with its status and
code only), the feature off (no `SCREENER_WORKER_URL`) 503 `SCREENER_DISABLED`, the tables missing 503
`SCREENER_NOT_READY` with `Retry-After: 60` (`/ready` does not read them). Every worker call but `/health` carries the
key and `x-screener-owner`, the first 16 hex of HMAC-SHA256(`SCREENER_WORKER_KEY`, owner), so the worker can be fair
per owner without learning the owner (report 8.11, 6d.6). A run, preview, counts or validate answer the worker sends
gzip is passed to the browser as its bytes with its `ETag`, never parsed here (only the versions at its head are read);
it is inflated only for a client that takes no gzip (report 6d.5). Runs and previews are latest wins per (owner, page),
each in its own lane, as the backtest's signals preview: a call that arrives while an older one of the same page is in
flight ends that one (its worker call is closed; 409) and is sent once it has ended, while another page's calls (a
second tab, or another person on today's one login) go on; a call its page had already sent a newer one of (by
`client_order {page, seq}`) answers 409 at once and never reaches the worker; a call whose page went away is cancelled,
which closes its connection to the worker.

The catalog and the universe are kept in memory per worker state: edge-bff reads the worker's `/health` (versions and
the last refresh outcome; the transient `refreshing` and `loading` change no catalog byte) at most every 60 s and
fetches a document again only when that state changed; a worker answer at another `price_data` and not at an older
publication (the previous snapshot in its grace window) has them fetched again at their next request (PAGE LOAD
SEQUENCE 6c.5). A document is never replaced by one of an older `published_at` (a replica that has not swapped yet,
report 6d.5). While the worker cannot answer, the last ones are kept. Answers keep the house `Cache-Control: no-store`;
the page keeps the bytes itself and sends `If-None-Match`.

Saved items (P12 a, user 2026-10-28): a saved screen (`kind` `screen`, `definition` `{definition, view?}`) or a My
metric (`kind` `metric`, `definition` `{test}`, validated as the one condition of a screen of the required universe
fields; the worker's field is then named from the test). A definition is stored as the page sent it, with the
worker's `definition_hash` and the registry versions of that validation, and never adjusted: on load, an item saved
under other registry versions than the worker's current ones is validated again and each refusal is listed in
`needs_review` with its field (kept per definition and versions; not listed while the worker cannot answer, and after
one unanswered question the rest of that list is not asked either, so the list waits for one call at most). Limits
(`app/screener.py`, the `PIN_LIMIT` precedent; values set in Phase 1, to be recorded in `EXEC.md`): `SCREEN_LIMIT` 50
saved screens and 50 My metrics per owner (so the worker's counts call takes every saved screen at once),
`WATCHLIST_LIMIT` 500 tickers, a definition at most 65,536 bytes of JSON as the table's CHECK measures its jsonb text
(a space after each colon and comma, UTF-8; edge-bff counts the same way before the worker, and the CHECK refuses a
number the database writes out longer with the same code). These and `inflight_per_page` (1 screen and 1 preview per
page) are published in the catalog's `limits[]` with their rule and examples.

Tables (migration `database/migrations/20261028_001_edge_bff_screener.sql`): `edge_bff.screener_items` (item id
`scr_` + 32 hex, owner, kind, name unique per owner and kind, definition, schema and registry versions, definition
hash, revision) and `edge_bff.watchlist_items` (owner, ticker). The runtime role gets only what the code does: saved
items SELECT/INSERT/UPDATE/DELETE, watchlist SELECT/INSERT/DELETE; PUBLIC gets nothing (the migration's verify block
checks both). No market data.

| Variable | Default | Railway dev | Meaning |
| --- | --- | --- | --- |
| SCREENER_WORKER_URL | empty = feature off | `http://screener-worker.railway.internal:8080` | the worker's private Railway endpoint (`http`, host `screener-worker.railway.internal`; anything else is refused outside `EDGE_ENVIRONMENT=local`) |
| SCREENER_WORKER_KEY | empty | `${{screener-worker.SCREENER_WORKER_KEY}}` (Railway reference; never a value here) | sent as `x-screener-worker-key` (not to `/health`); at least 32 characters; set together with the URL |
| SCREENER_TIMEOUT_SECONDS | required with the URL | the worker's `SCREENER_DEADLINE_MS` in seconds (20 initially) | the worker's deadline; the relayed calls wait this + 30 s for its answer (1 to 3600) |

Tests: `tests/test_screener.py` (fake worker as a local HTTP server, disposable Postgres, the migration's verify block
and the provisioning script's reach, one Chromium check of the tab, and the screener stage of the image).

## Radar tab (EXEC-RADAR, 2026-11-14)

The screener library's filters S1, S2, S3, S6, S6Δ, S7 and S8 as a board and a filter detail, for the owner (an admin
page: the rules and thresholds are shown). Design: R10 (`verification/radar/index-r10.html`, user D7) and
`verification/radar/RADAR_PAGE_SPEC.md`; data contract: `verification/radar/FILES.md`. The page `radar/` (TypeScript +
Vite, no dependency) is built by the Dockerfile's `radar` stage into `static/radar-app/` (not kept in git) and shown in a
frame at `/radar` (Radar tab after Screener, wording in `static/edge-labels.js`; the tab shows only when
`/api/v1/auth/session` and the sign-in say `capabilities.radar`). `/radar-app/` takes the Screener page's CSP
(`connect-src 'self'`): `app/radar.py` lists the Radar files (`GET /api/v1/radar/index`) and relays their bytes
(`GET /api/v1/radar/file/<name>?sha=`) from terminal-api, which presigns them for the gateway key only. The page picks
Feature 07's rows (`radar/src/model.ts`) and evaluates no rule. Open in Terminal stores the symbol (`ml.symbol`) and
posts `edge-nav`; the shell's one listener accepts it from its own frames only, for a page of the rail (ERRORS M425,
also the Screener's). Tests: `tests/test_radar.py` (routes, refusals, the tab and edge-nav in Chromium),
`radar/tests/` (`npm test`).

## Overview tab (EXEC-OVERVIEW, 2026-11-15)

The Market Overview for the owner: KPI strip, market map, IHSG chart, Sector Performance, % above EMA50/EMA200, Top
Movers and Foreign Flow, every text in English (decision 8). Design: `market-overview-target-c-ihsg-flow.html` (the
user's attachment, 2026-11-15); every figure is explained in `OVERVIEW_FORMULAS.md`. The page `overview/` (TypeScript +
Vite, no dependency) is built by the Dockerfile's `overview` stage into `static/overview-app/` (not kept in git) and
shown in a frame at `/overview` (the first tab of the rail, decision 7; wording in `static/edge-labels.js`; the tab
shows only with `capabilities.overview`). `app/pages.py` is the relay both owner pages share (`app/radar.py`,
`app/overview.py`): `GET /api/v1/overview/index` lists the files and `GET /api/v1/overview/file/<name>?sha=` relays their
bytes from terminal-api, immutable per sha. The page computes no figure: `overview/src/model.ts` only picks the user's
universe, period and metric and sums, weights or orders the publisher's rows. Open in Terminal works as the Radar's.
Tests: `tests/test_overview.py` (routes, refusals, the tab first in the rail and edge-nav in Chromium, the image stage),
`overview/tests/` (`npm test`); look check and independent recalculation in `verification/overview/REHEARSAL.md`.

## Sector Analysis tab (EXEC-SECTOR-ANALYSIS S3, 2026-11-26)

The user's prototype as a page of its own (decisions UD66 A-J and UD67, the go "1A 2A 3 go" of 2026-11-26; the build
contract `verification/sector_analysis/CONTRACT.md`). The gateway and the shell (S3):

- **Data:** `app/sector.py` on `app/pages.py`, as the Overview's: `GET /api/v1/sector/index` lists the publisher's
  family `sector/` and `GET /api/v1/sector/file/<name>?sha=` relays a file's bytes from terminal-api (its `/sector`
  routes, the gateway key only), `private, no-cache` with the ETag (a 304 only after the check). Both need `sector.view`.
  Names: `sector-meta`, `sector-series`, `sector-day-YYYY-MM-DD` and `sector-stocks-<index>`, the index ticker
  lowercased (`sector-stocks-idxfinance`: terminal-api keeps only lowercase names of at most 32 characters, CONTRACT
  3.4); refusals `SECTOR_INVALID_NAME`, `SECTOR_FILE_NOT_PUBLISHED`, `SECTOR_FILE_REPLACED`, `SECTOR_UNAVAILABLE`,
  `SECTOR_NOT_CONFIGURED`.
- **Page:** the build of `sector/` (the page part, S4; the Dockerfile's `sector` stage, not kept in git) at
  `static/sector-app/`, shown in a frame at `/sector`, the
  Overview's policy (`connect-src 'self'`); its words in `static/edge-labels.js` (`sector`: "Sector Analysis"), the rail
  entry and the phone's pages menu right after Overview (icon `navSector`), shown only with `capabilities.sector`
  (terminal-api configured). Open in Terminal uses `edge-nav` as the Overview's (decision G).
- **Release and plans:** tab `sector` released in `catalog/releases.json` (decision F: on the beta from `main`; the live
  site only when `live` moves, on the user's request). Migration `20261126_050`: `sector.view` for the paid plan,
  `sector.example` for the free and the guest plan (decision J), the admin's `*` both.
- **Example (decision J):** `app/examples.py` `SectorLatest`, as the Overview's: the live publication's opening view on
  its newest day (`sector-meta` with that one date, `sector-series` up to it, that day's file), each file cut to the
  contract's fields; the older days and every `sector-stocks-<index>` stay with `sector.view`. The shell opens it as
  every example (`ExampleTabPage`, `?example=1`); the page keeps its five tabs switchable and locks every other control
  with `lockOnly` (`shared/example-view.ts`), whose click asks for the Overview example's sign-in or upgrade box.

Tests: `tests/test_sector.py` (routes, refusals, names, plans, the release, the example, the rail, the phone menu and the
visitor's example in Chromium), terminal-api `tests/test_api.py` (`/sector`).

## Watchlist tab (EXEC-WATCHLIST L5, 2026-11-16)

The account's named lists of stocks, each with the indicators it shows, every text in English. Design: the approved
light mockup `watchlist_light_mockup.html` (2026-11-16; its CSS is the Design Spec v1 and the page CSS of
`verification/watchlist/design/watchlist_20261116.html`, copied into `watchlist/src/styles/watchlist.css`). The page
`watchlist/` (TypeScript + Vite, no dependency) is built by the Dockerfile's `watchlist` stage into
`static/watchlist-app/` (not kept in git) and shown in a frame at `/watchlist` (the tab right after Overview in the rail
and the phone's pages menu; wording in `static/edge-labels.js`; the tab shows only with `capabilities.watchlist`).
Figures: the publisher's `watchlist-stocks` file (`apps/terminal-publisher/watchlist.py`, `WATCHLIST_FORMULAS.md`)
through `GET /api/v1/watchlist/index` and `/file/watchlist-stocks?sha=` (`app/pages.py`, as the Overview's). Lists:
`/api/v1/watchlist/lists` (`app/watchlist.py`), every write with the session's CSRF token; the page takes its limits
from the answer's `limits` and shows edge-bff's refusal message. A first visit with no list creates "Watchlist". The page
offers exactly the file's `catalog` (a list's `indicators` null = the file's `default`; keys the catalog does not hold
are skipped) and computes no figure: `watchlist/src/model.ts` only formats by unit, filters, sorts the view and builds
the Undo bodies. Logos are the Terminal's (`/api/terminal/v1/reference/logos`, read at most every 12 hours per browser,
and `/api/terminal/v1/logo/<T>?v=`); the logo list is a presigned bucket URL, so `/watchlist-app/` takes the Terminal
page's policy (`WATCHLIST_CSP`). Open in Terminal and the Radar badge use `edge-nav` as the Overview and the Radar.
Tests: `tests/test_watchlist.py` (the lists API), `tests/test_watchlist_page.py` (the page's route and policy, the tab
after Overview, the pages menu, the capability, edge-nav, the image stage and, when built, the real page creating the
first list and adding a stock in Chromium), `watchlist/tests/` (`npm test`). Look check: `npm run build:fixture` builds
`dist-fixture/` on a made-up file (`tests/fixture/watchlist-stocks.sample.json`) and an in-memory list store
(`?theme=dark`, `?empty=1`).

## Front-end structure: editing the page without touching the API (EXEC-X, 2026-10-08)

The browser tab names the page (EXEC-TERMINAL-IND-EDIT, user 2026-11-05): `App()` in `static/edge-app.js` sets
`document.title` from `EdgeLabels.pages` in `static/edge-labels.js` (Sign In, Monitor, Terminal, Backtest, Screener); the
static `<title>` is only "EDGE". `tests/test_page_titles.py` checks it in a browser.

The page is edited as one HTML file and its API wiring is not locked to the view. Four layers, each with one job:

| Layer | File | Change it when |
| --- | --- | --- |
| Transport (API, session, SSE) | `static/edge-client.js` | a BFF route or its JSON changes |
| Session, error contract, browser storage (shared by the shell and the six pages) | `shared/edge-session.ts`, built for the shell into `static/edge-session.js` | a refusal code, the CSRF retry, or a browser storage key (see "Accounts groundwork" below) |
| View contract | `static/edge-view.js` (`EdgeView.toView`) | Orc's response shape changes; the only code that reads it |
| Words | `static/edge-labels.js` | wording, a label, a code's words, a status name |
| Look and layout | `static/index.html` (markup, CSS) and `static/edge-app.js` (the renderers and the shell's app) | anything visual; renderers read the view model only |
| Font | `static/fonts/` (Inter 4.001, the variable weight axis in Google's seven subsets, SIL Open Font License 1.1 in `OFL.txt`; `inter-400-700.css` for the shell and five pages, `inter-400-600.css` for the Terminal, the weights each asked Google Fonts for), served at `/fonts/<name>` | never from Google Fonts (re-check R2-28, user 2026-11-19 "5a pakai inter"): every policy keeps `font-src 'self'`, a page links one of the two sheets (`tests/test_decisions_small.py`) |

The shell runs no inline script (EXEC-MU-ACCOUNTS fix round, re-check R2-19): the head's viewport script is
`static/edge-boot.js` and the app is `static/edge-app.js`, so its policy keeps `script-src 'self'` without
`'unsafe-inline'`, with `form-action 'self'` (`app/main.py` protections; `tests/test_fix_plans.py`). A new script is a
file in `static/` loaded with `<script src>`, never an inline `<script>` or an `on...=` attribute. The preview tool
inlines every such file and writes each back on import.

- Look (MONITOR-REVAMP, user 2026-10-29): the Monitor page and the top bar of every tab follow the user's
  `AI_revamp.html` (EDGE / Market Lab Design Spec v1): its tokens on `.app` (light, and dark under `html.dark`), its
  components mapped onto this page's markup in the last block of `index.html`'s style ("MONITOR-REVAMP"). A browser
  with no saved theme starts light (`edge-auth-monitor-theme`; the Screener reads the same key and default). The phone
  layout (max-width 720px) keeps its own arrangement and takes the colours and type.
- Conversation list (MONITOR-REVAMP, user 2026-10-30): a Branch row sits under its parent conversation with the
  branch icon (`kind`/`parent_conversation_id` of the list API); the sidebar's Share ("Share latest answer") opens the
  Share menu of the conversation's latest answer; ⌘K/Ctrl+K focuses "Search conversations".
- Answer (user 2026-10-30): dates in every answer read "19 October 2026" (code, links and times as written); the
  suggestions fold per kind ("Suggested next questions", "Insight ideas", "Further research"), closed at first; a
  running ring turns once in 0.15 s like the Terminal's.
- Status colours (M317, user 2026-10-31): every status dot (conversation list, the phone's session row) has the colour
  of its run's state from `Edge.statusTone`: green completed, yellow waiting for the user or not whole (approval, a
  reply, paused, limited, stopped), red failed, blue running, a blue ring before the first question; none is grey. The
  list API adds the latest question's `last_state` and `last_run_status` (`edge_bff.jobs`) so a conversation not opened
  yet is coloured too. The answer head keeps one 8 px rhythm and shows the level as its label ("High"); on a phone the
  session row holds Details, bookmark, share and the run's state, and the action row keeps one gap.
- Tables (EXEC-TABLE-CLAUDE, user 2026-10-31: "duplikat saja pakai contoh dari Claude"): an answer table reads like a
  Claude table: no frame or grey header band, a semibold header over one stronger line, hairlines between rows, each
  title and cell left-aligned and in the middle of its row, numbers included (TABLE-ALIGN-A, user 2026-10-31: the
  alignment of the table before MONITOR-REVAMP, E13), the table as wide as its content so every gap between columns
  is the same, one line above the titles as strong as the one under them, the sort arrow faint after the title,
  and the table's edges on the answer text's. A title over 14 characters wraps there and is never squeezed narrower.
  A wrapped number title shows its arrow only on hover, focus or when sorted. Response history and Pinned responses
  share one type (title 12 px medium in two 17 px lines, status 10.5 px); a history dot takes `Edge.statusTone`. The
  page shows no "Draft" label before the first question. The conversation's last pixels fade into the page above the
  message box (24 px; phone 8 px), inside the space below the last answer, so no hard edge reads as a dividing line.

- The Details panel (`EdgeView.sources`) lists Orc's `execution.hurdles` as "Hambatan proses", in Orc's own words
  (EXEC-FRICTION, M142); nothing when there were none.
- An answer's assumptions and limitations (`lists`) are folded under the answer as "Asumsi (n)" and "Batasan (n)"
  (EXEC-STYLE S3); nothing when a list is empty.
- Links that start with `/api/` (the export downloads) stay real requests; every other root link is kept portable
  through `staticUrl` (EXEC-EXPORT). After each redraw the element that had focus gets it back with its caret, and a
  keystroke in the message box redraws only when the box turns empty or non-empty (EXEC-TYPING).
- A table in an answer sorts by a click on a column title: descending (↓), ascending (↑), then the original order; the
  title shows its arrow, faint until hovered or sorted (MONITOR-REVAMP); a Total row stays last; Indonesian numbers,
  money scales and dates are read (`MdTable`, EXEC-SORT). A dash (`–`, a missing value in a table Orc builds, EXEC-TABLE) sorts
  last like an empty cell.
- The left panel shows each conversation's latest question under its title (`last_message` from the job table,
  EXEC-UI-1012 B1). The conversation's title is Orc's first-message router title when there is one (only the first
  question; a title the user set is kept), else the first 80 characters of the question (EXEC-UI-1012 C). Search
  matches the title or any of the conversation's questions.
- The trash button next to the bookmark asks first, then hides the conversation from the list
  (`DELETE /api/v1/conversations/{id}` sets `edge_bff.conversation_ui.hidden_at`, migration `20261012_008`); Orc keeps
  its history and results under its own retention, and a running conversation is refused (409) (EXEC-DELETE).
- In Details, the line between Pinned responses and Response History is dragged (pointer events: touch or mouse; arrow
  keys) and its height kept in this browser (`edge-pins-height`); each section title collapses its section
  (`edge-pins-open`, `edge-flow-open`) (EXEC-DETAILS).
- Responses and the composer share the same reading column, including the space used by a classic scrollbar.
  Drag the small grip on the composer's top border up to enlarge the message box or down to shrink it (mouse or
  touch); focus it and use Arrow Up/Down for keyboard resizing. The chosen height survives typing during the current
  page session and is capped by the viewport so the conversation and send controls stay accessible. Enter submits on
  desktop; Shift+Enter and touch keyboards retain multiline editing. Sending preserves the Details open/closed choice.
  Pinned responses and Response History each keep their header visible while their own list scrolls; history is newest
  first, while pinned order is unchanged (EXEC-UI-1019, verification: `verification/bff_ui_1019/README.md`).
- Each finished answer shows how long it took (Orc's `execution.duration_ms`, else the saved start-to-finish time)
  next to its tokens and in its Response History line (EXEC-DURATION).
- `EdgeView.toView(envelope)` returns display-ready parts (status, meta, answer, clarification, pause, plan, findings,
  lists, methodology, artifacts; `EdgeView.sources` for the Details panel). Its `version` changes when a part changes
  shape. A field the view does not know yet still shows through the generic view, named from its key.
- Every choice the page shows carries an action descriptor: `route` (a quick choice), `plan` (APPROVE, REVISE,
  CANCEL with its plan id), `message` (the choice's words are sent) or `input` (the user writes first). `act()` in the
  page is the only place that sends one, so a new kind of choice from the backend needs no new button code.
- The BFF serves every page script in `static/` by name (`/<name>.js`), so a new front-end file needs no route.
- Backend codes reach the page as words: Orc writes the lines inside an answer in plain Indonesian and its interface
  texts (progress steps, hurdles, run failures) in English (`app/user_texts.py`), and the page words a code through
  `edge-labels.js` or, when a code has no words yet, shows it readable, never raw. EXEC-UI-1019B (user 2026-10-19:
  "semua label tetap bahasa Inggris"): every label of the interface is English; the user's messages and the AI's
  answer keep their own language, and the three `*Message` texts (sent as the user's own message: export request,
  plan approval and cancellation) stay Indonesian.

Editing workflow (no server, no login, no AI call):

```bash
python preview/edge_preview.py build preview/edge_preview.html   # one file: the page, its scripts, saved dev responses
# open and edit that file in any editor or design tool, then:
python preview/edge_preview.py import preview/edge_preview.html  # back to static/index.html and static/*.js
```

`import` refuses a file the tool did not build and writes only what changed. `tests/test_frontend_contract.py` checks
the script route, the round trip and the view contract on every saved response (`tests/fixtures/orc_responses.json`);
`tests/test_answer_view.py` drives the real page through the BFF with those responses.

### Sharing an answer (EXEC-SHARE-UI, 2026-10-19; EXEC-UI-1019B)

"Share" in an answer's action row offers PDF, PNG and Word (.docx) of one card: the EDGE logo drawn inline as SVG
(`EDGE_LOGO_SVG`, the same drawing as `static/edge-logo.svg`; an outside image came out empty in a user's PNG) and the
date, the answer's metadata row (request, model logo, name and level, tokens, duration; no cost), the question in a
black box, the evidence line in black with its green check on the right, the answer without its title and with every
table row, Assumptions and Limitations closed (title and count), the methodology, and a footer (latest data date of its
tables, request ID, "Not investment advice"). The card is a cleaned clone of the answer in light colours (`EdgeShare` in
`static/index.html`, footer data from `EdgeView.shareInfo`). PDF: the browser prints the card alone
(`body.edge-share-printing`). PNG: `static/html-to-image.js` (html-to-image 1.11.13, MIT, `static/html-to-image.LICENSE`,
loaded on first use; the CSP allows scripts from this origin only) draws it 760 CSS px wide at up to 3x (2,280 px; a
card taller than about 2,340 CSS px takes a smaller ratio so it stays within 16 million pixels), then the Web Share API
shares it, or it is downloaded. Word: `static/edge-docx.js` (no library, loaded on first use) writes WordprocessingML in
an uncompressed ZIP: the logo as PNG, the question box, the answer with its tables as Word tables, Assumptions and
Limitations written out (Word has no folded sections) and the footer. Tests: `tests/test_share_card.py`. The composer's
"Research Mode" menu (Standard / Deep Research, display only) was removed on 2026-10-19.

### Table download, provider timeouts and the running step (2026-10-20)

- A table Orc built from a kept result (its `answer_tables` entry has an `output_id`) shows a download icon beside
  the enlarge icon. A click asks `POST /api/v1/conversations/{id}/outputs/{output_id}/export` with the columns and
  titles the answer shows (each output column once); Orc writes every row as XLSX with the definition sheet and the
  input sheets (extracted again when the sandbox no longer keeps them, marked with the date) and no model call. The
  icon shows "Preparing file…" meanwhile, then the browser downloads `GET /api/v1/exports/{export_id}`. A second click
  while Orc still writes the same table's file is refused (409 `EXPORT_IN_PROGRESS`, "This table's file is already
  being prepared"). A table the model typed itself has no icon.
- A run that failed because the AI provider sent no output (`PROVIDER_STALLED`, `PROVIDER_TIMEOUT`, after Orc's one
  automatic retry) or kept thinking without answering (`REASONING_RUNAWAY`) says so and offers **Retry** (sent again
  at once with the run's own model and level) and **Change model** (the question back in the message box with the
  model menu open) (EXEC-M181, user 2026-10-20).
- The step running now shows how long it has taken ("Thinking · 2m 10s"), counted on each second from Orc's
  `duration_ms`.
- EXEC-UI-1019B layout: one 24 px gap between the answer's sections, tables centred, a column title longer than 14
  characters wraps within 14ch, the AI answer's copy button reads "Copy", the sticky panel heads use the panel colour,
  and the favicon and app icons use the new round EDGE mark.
- Tests: `tests/test_ui_1019b.py`.

### Answer head and composer polish (EXEC 2026-10-20, user screenshots)

- The table icons stand 8 px above the table; a title made from the question (or the router's) is cut at a word with
  an ellipsis (`Edge.shortTitle`); the evidence line sits 10 px under the metadata row (as the row under the title)
  in the row's type, with a green check for a positive evidence label.
- A conversation's bookmark and delete buttons show their hover on every row; "Data Scope" uses the model picker's
  type; the message box in use gets a soft shadow instead of a darker border; a running answer's progress sits close
  under the question, the page follows new progress steps while it follows the latest message, and the composer no
  longer shows a "Standard" lane label (every EDGE message runs the fast lane).
- Tests: `tests/test_ui_1020.py`.

## Persistence and ownership

Orc owns history, answers, methodology, evidence, usage and exports. BFF accesses them only through authenticated
Orc endpoints, not SQL. Its dedicated restricted schema holds its operational tables: sessions, jobs and UI metadata,
and, with migration `20261026_005`, the three backtest tables (backtest jobs, result parts and trials; see Backtest
tab), with migration `20261028_001` the screener's saved items and watchlist (see Screener tab), and with migration
`20261106_001` the Terminal's saved chart layouts, with `20261106_002` its indicator presets and with `20261107_001` its drawings (see Terminal tab), which hold no market data. Migration `20261116_002` adds `auth_throttle`, the sign-in throttle (see Accounts groundwork). Jobs retain original inputs for deterministic replay, not answers. Pins/bookmarks do
not extend Orc's retention (code default 30 days, actual configuration must be checked before rollout). Expired
history returns 410.
There is currently no automatic purge of terminal job inputs/UI metadata or of backtest jobs: define an operational
retention policy before long-term use. Backtest result parts are deleted after 30 days; the backtest trials are never
reset (K3). Saved screener items and the watchlist are the user's own objects and are not purged (each owner at most
`SCREEN_LIMIT` items of each kind and `WATCHLIST_LIMIT` tickers); every statement on them names the owner. Saved Terminal
layouts are the user's own objects too and are not purged (at most `LAYOUT_LIMIT` = 50 per owner, owner in every statement). Sessions are cleaned when the loop starts and then hourly.

Deployment configuration rejects an administrative database username; it requires `edge_bff_login`.
The server sets `X-Saniti-Owner`; a browser cannot choose an owner. One active job per owner is intentional for this
single-user first delivery. Different tabs cannot start concurrent paid runs. A submission key identifies a logical
submission: same key + payload returns the same request; changed payload returns 409. Retry in the UI prepares a
new submission. An ambiguous transport retry reuses the identical key; it is not an automatic new AI execution.

## Worker and SSE

The managed worker claims jobs with `FOR UPDATE SKIP LOCKED`, a 90-second lease and 20-second heartbeats. Expired
leases can be reclaimed. All writes are fenced by the lease token and expiry. Every dispatch first reads Orc's
request identity. A saved result is delivered without POST; RUNNING is polled. Ambiguous dispatch is checked twice
before at most three total attempts using the same request ID and exact payload. Orc's idempotency, not the BFF
lease alone, prevents a second execution. The 3900-second HTTP timeout covers the verified mode-4 3600-second
budget plus margin. No timeout or browser disconnect claims to cancel Orc.

SSE is cookie-authenticated, same-origin, uncompressed, and unbuffered. Events are `snapshot` with the monotonic
job `state_version` as `id`. Reconnection restores the current snapshot, not a historical event sequence. Connections
rotate after 240 seconds; browser EventSource reconnects automatically with Last-Event-ID, falling back to REST
polling after repeated failures. Terminal snapshots close the stream. Refresh restores the active job from the
server. Logout revokes the session and disconnects browser followers.

## API contracts

EXEC-CHOICES: every choice the system offers (an ask-back question, a Research Plan to approve, a paused answer, the
suggestions what to ask next) is shown as one "Response choices" panel: sent at once (arrow) or completed in the message
box first (pen); the chosen one stays marked.

All routes are under `/api/v1`; all writes require exact Origin and, except sign-in, `X-CSRF-Token` from the session
endpoint. Cookie `edge_session` is opaque, HttpOnly, Secure and SameSite=Strict in deployment; only its hash is stored.
No CORS is enabled. Responses are not cached. Inputs forbid unknown fields.

| Method/path | Input/result |
| --- | --- |
| POST `/auth/sign-in` | `{login,password}`; session cookie, login, CSRF token; 401 `INVALID_CREDENTIALS`, 429 `SIGN_IN_RATE_LIMIT` with `Retry-After` (see Accounts groundwork) |
| GET `/auth/session` | Authenticated login, CSRF, supported capabilities |
| POST `/auth/sign-out` | Revoke session; clear cookie |
| POST `/runs` | `{submission_key,message,conversation_id?,chosen_option?,plan_reply?,model?,reasoning_level?}`; 202 request identity |
| GET `/models` | Orc's offered models, reasoning levels and prices per one million tokens (Orc reads OpenRouter hourly; cached here ten minutes; the last list is kept when Orc fails, 503 `MODELS_UNAVAILABLE` before any). Read once at sign-in, before the work page shows |
| GET `/runs` | `{active: snapshot or null}`; refresh recovery |
| GET `/runs/{request_id}` | Owner-scoped snapshot, saved canonical response when terminal |
| GET `/runs/{request_id}/events` | Same snapshot as SSE, `Last-Event-ID` supported |
| GET `/conversations` | Search/title, bookmark filter, offset/limit pagination; BFF-owned conversations |
| GET `/conversations/{id}/messages` | Canonical history pagination `after/limit`, UI metadata; 410 if expired |
| PATCH `/conversations/{id}/preferences` | Desired `{bookmarked?,title?}` |
| PATCH `/runs/{id}/preferences` | Desired `{pinned}`; canonical response must exist |
| POST `/conversations/{id}/outputs/{output_id}/export` | `{columns, titles}` (at most 60 each); Orc writes the table's XLSX (no model call); `{export_id, file_name, size_bytes, format}`; 404 for another owner's conversation or a malformed output id; Orc's refusal code is kept (409 `EXPORT_IN_PROGRESS`) |
| GET `/exports/{export_id}` | Owner-checked streaming proxy of an existing Orc artifact |

`plan_reply` is `{plan_id, action: APPROVE|REVISE|CANCEL, revision_instruction?}`. The client reads the issued plan
ID; Orc validates latest-plan state and ownership. Cancel applies to a pending plan, not an active request.
`chosen_option` uses an Orc-issued route. Free-text replies remain ordinary message submissions.

BFF lifecycle: QUEUED/RUNNING/RECOVERING/FINISHED/FAILED/INTERRUPTED. Orc domain status is independently one of
COMPLETED/NEEDS_CLARIFICATION/AWAITING_CONFIRMATION/LIMITED/FAILED. FINISHED means a canonical result was saved,
even if its domain status is FAILED. The read endpoint's saved envelope excludes POST's `conversation` decoration.
Sources are drawn only from actual evidence/annotations/data_record. Usage/cost appears only when the saved execution reports it.

## Railway dev configuration

| Variable | Value/source |
| --- | --- |
| EDGE_DATABASE_URL | New restricted `edge_bff_login` on existing market Postgres, private endpoint; secure value |
| EDGE_ORC_URL | `http://market-ai-orc.railway.internal:8080` |
| MARKET_AI_ORC_API_KEY | Railway reference to existing Orc variable |
| EDGE_OWNER | `edge-private`, stable server-owned identity; never browser supplied |
| EDGE_LOGIN | `edge`, selected under the user's 2026-10-08 delegation; set before deployment |
| EDGE_PASSWORD_VERIFIER | Scrypt verifier of the securely generated private password |
| EDGE_INITIAL_PASSWORD | Temporary credential handoff in Railway Variables; unused by the application. Owner retrieves securely, then removes this variable after copying the password |
| EDGE_ADMIN_USERNAME, EDGE_ADMIN_EMAIL (orc-test-runner) | The live site's admin login (user #1's username), chosen by the agent with the user's leave of 2026-11-20 ("feel free to suggest login ID dan passwordnya. kalau bisa jadikan ini variable di railway"); kept on the private runner since 2026-11-20 (never in the public process); unused by the application: the job `scripts/onboarding/edge_account_login_job.py` writes them into the account |
| EDGE_ADMIN_INITIAL_PASSWORD (orc-test-runner) | The live admin's generated first password, a handoff for the user to read in Railway Variables; unused by the application (the switch-on sign-in checks the account's own identity, written by `scripts/edge_account_login.py`). A password changed on the site no longer matches it: remove the variable once copied, or have it updated |
| EDGE_PRIVACY_URL, EDGE_TERMS_URL | The footer's Privacy and Terms links (EXEC option A, 2026-11-20): an https address or a path of this site (`/...`); unset, no link is shown (both are unset until the user gives the texts). `GET /api/v1/auth/config` names them under `legal` |
| EDGE_SESSION_SECRET | Random 32+ character secret, entered securely |
| EDGE_PUBLIC_ORIGIN | Exact HTTPS origin of the new service; set after domain allocation |
| EDGE_ENVIRONMENT | `dev` (use `local` only for loopback tests) |
| EDGE_SECURE_COOKIE | `true`; local tests alone use false |
| EDGE_SESSION_SECONDS | 86400 |
| EDGE_ORC_TIMEOUT_SECONDS | 3900, must exceed active Orc maximum + margin (minimum 3900 seconds) |
| EDGE_LEASE_SECONDS / EDGE_HEARTBEAT_SECONDS | 90 / 20 |
| EDGE_POLL_SECONDS / EDGE_WORKER_ENABLED | 2 / true (false: no background loop at all, local runs and the tests) |
| EDGE_SITE | unset = `beta` (this service); `live` only on edge-bff-live (section "Beta and live websites") |
| EDGE_AI_WORKER_ENABLED / EDGE_BACKTEST_LOOP_ENABLED / EDGE_HOUSEKEEPING_ENABLED | unset: the AI job loop on the beta only, the backtest loop and the hourly housekeeping on; true or false only (a typo stops the start) |

Use one uvicorn process/one replica initially. Disable request access logs and proxy headers. Authentication attempt
limiting lives in PostgreSQL (`edge_bff.auth_throttle`, EXEC-MU-ACCOUNTS Phase 0), so it holds across restarts and
instances. HTTPS termination is Railway's responsibility. No plaintext password, database credential,
Orc key, session secret or Railway token is bundled or stored in Git. Public errors are generic; private diagnostic
keys/addresses are filtered. An exception no handler expected is answered 503 by the outermost middleware
(`errors.UnexpectedErrors`) and logged by its class and SQLSTATE only, so its text (a failing row's personal data)
never reaches the server log (re-check R2-25). The original inline renderer requires CSP `unsafe-inline`; unsafe-eval is not enabled.

## Local validation

Use a **disposable** Postgres admin URL; tests create/drop databases and roles. Never point these at Railway.

```bash
python -m venv /tmp/edge-venv
/tmp/edge-venv/bin/pip install -r requirements-dev.txt
# Also install ../market-ai-orc/requirements-dev.txt for the real canonical contract test.
EDGE_TEST_POSTGRES_URL=postgresql://postgres@127.0.0.1:55432/postgres /tmp/edge-venv/bin/python -m pytest -q
```

Browser tests use installed Chromium `/usr/bin/chromium` (set `EDGE_TEST_CHROMIUM` for another path); install
Chromium locally or use Playwright's verified browser installer. They launch a local BFF/worker with real local
Postgres and a deterministic Orc substitute. The separate contract test obtains JSON from actual Orc HTTP/storage
with a scripted model, satisfying the repository's M68 rule. No OpenRouter call is made by these tests.

`tests/test_visual.py` also checks desktop/tablet/mobile interactions (360–1600 pixels), animated loading,
refresh without duplicate execution, failed/limited replies, retry, research-plan and clarification controls,
saved bookmark/pin preferences, panel focus and keyboard navigation. Set `EDGE_UI_ARTIFACT_DIR` to a local
directory to save screenshots and console/HTTP results. Optional `EDGE_UI_RECORD_VIDEO=1` also records videos;
this requires Playwright's FFmpeg installation (or the installed system FFmpeg in its browser cache).
These fixtures run locally only and are never enabled in the deployed service. Mobile history and Details
are drawers; active server cancellation remains unavailable.

## Rollout gate and rollback

See `EDGE_DELIVERY.md`. Migration is **APPLIED** and verified at 10:13:24 UTC on 2026-10-08 after admin preflight.
See `verification/edge` for live columns, constraints, indexes and grants. The only Orc code
change is additive GET `/v1/agent/requests/{request_id}`; no existing runner/tool/model/provider configuration changes.
The user approved dev deployment directly from `codex/edge-bff`; keep main unmerged. Further merge approval is separate.

After approved reconciliation: apply the forward migration; provision the restricted login with
`scripts/provision_edge_bff_login.py`; verify actual grants; deploy the additive Orc endpoint; create the one BFF
service and its secure variables/domain; deploy BFF; verify unpaid health/auth/read paths. A paid AI smoke test
requires separate approval. Do not apply the full IaC project until its live plan has been checked for unrelated drift.

Rollback stops BFF dispatch and disables its public ingress, then restores the previous Orc deployment if necessary.
A dispatched Orc run can continue and save its result. Preserve the new operational schema/rows for review; dropping
it or deleting jobs requires a separate destructive decision. No original market or canonical tables are changed.

Local container validation also confirmed uid 10001 can read root-owned code/static after COPY, and health/auth/CSRF/
queue persistence work in the image. Copied private file modes are normalized with read/traverse permission only.


## Waiting for sandbox initialization

Before a new dispatch, the worker first reconciles the original request ID, then reads Orc's authenticated
`/v1/agent/readiness`. An initializing response uses RECOVERING / SERVICES_INITIALIZING, shown as
`Waiting for services to be ready.`; it does not consume a dispatch attempt. Existing delivery deadlines,
lease/heartbeat, ownership, Stop and ambiguous-delivery reconciliation remain in force. Stop is checked again after
readiness. Older Orc without this additive endpoint remains supported during rolling deployment.
The existing progress endpoint shows `Initiating sandbox session.` during an actual session open, then the ordinary
calculation steps. No new queue, progress transport, browser credential or service is required. See M187.

## Branch and side chat (EXEC-ASK-BRANCH, 2026-10-24)

Under each finished answer, **Branch** opens a new tab with a conversation that continues that answer, and **Ask about
this answer** opens the answer's side chat in a panel (full screen on a phone); a selected passage can be sent there
with "Ask in side chat". `POST /api/v1/runs/{request_id}/branch {kind: BRANCH|SIDE, title}` asks Orc for the new
conversation (`POST /v1/conversations/{id}/branch`) and writes its list row (`edge_bff.conversation_ui.kind`, parent
conversation and answer; migration `20261024_002`). One side chat per answer; side chats are left out of the
conversation list and linked under their answer ("Side chat (n)"). Every conversation has its own address,
`/c/<conversation_id>` (EXEC-CHAT-URL; served by the BFF, older `#/monitor?c=` links still open); `?view=side` is the
compact view the side panel frames, so the CSP allows framing by EDGE itself only
(`frame-ancestors 'self'`, M213). One running question per owner stays the database rule, so a side-chat question waits
while the main conversation runs.

## Conversation addresses (EXEC-CHAT-URL, 2026-10-24)

Served by the BFF, EDGE uses plain paths: `/monitor` for a new conversation and `/c/<conversation_id>` for each
conversation (the BFF serves the page there; any other id is 404). Choosing a conversation writes its address, so a
reload, a bookmark or a new tab opens it and Back/Forward move between conversations; signing in at an address opens
that conversation. The one-file preview (`preview/edge_preview.py`, scripts inlined, no server) keeps hash routes; the
page tells the two apart by whether its scripts came from the server.

## Standalone page for design work (EXEC-UI-1025b, 2026-10-24)

`python preview/edge_preview.py build edge-standalone.html` writes the whole EDGE page as one HTML file with dummy data
(no server, no AI; model logos included). It shows the same views as the live page, Branch and side chat included. A
redesigned copy returns to the sources with `python preview/edge_preview.py import edge-standalone.html`; change only
the look (markup and CSS), not the behaviour, and the tests run as usual.

## Rights from the session (EXEC-BACKTEST-REVAMP P5, 2026-11-15)

`app/rights.py`:
- `rights_of(settings, owner)` gives every admin right to an owner in `EDGE_ADMIN_OWNERS` (comma list; default
  `EDGE_OWNER`; a blank entry, a space or a duplicate stops the start).
- `refuse_context` refuses a page body that carries `context` (422 `UNKNOWN_FIELD`).
- `catalog_for` leaves `access: 'admin'` entries out of a session's catalog.

Where it applies:
- The Backtest routes read the owner from the session (`request.state.owner`, set by `main.py session`).
- The worker calls carry `context.rights`; a queued job computes them at dispatch, together with the owner's trials of
  the last 90 days (`owner_trials`, K6 a).
- Result parts are joined on `owner_key`.
- The Screener routes carry the same rights and filter the Screener catalog per session (its own ETag).

Items per plan (EXEC-MU-ACCOUNTS Phase 3b, CONTRACT.md 8b "3b in detail"), `app/allow.py`:
- Every worker call that sends `rights` sends the whole `context: {rights, allow, limits}`: Backtest validate,
  signals and the job context at dispatch (read from the owner's principal then); Screener validate, run, preview,
  counts and a saved item's validation and review.
- `allow` holds, per kind (`indicator`, `flow_indicator`, `candle_pattern`, `screener_metric`), `"*"` (the principal
  holds `*`, or the family is `{"all": true}`) or the sorted ids of `catalog/releases.json` the principal holds in that
  worker's family (Backtest: `backtest.*`, Screener: `screener.*`; both use `screener.metric` for metrics). With the
  switch off the configured owner gets `"*"` for every kind. `limits` is `{}` until a plan sets a worker limit.
- A worker's 403 `CAPABILITY_REQUIRED` is relayed as it is, with `details.display_name` added; a queued job the worker
  refuses at dispatch ends `FAILED` with that refusal; a saved item it refuses on review lists it in `needs_review`.
- The Screener's saved-item review cache is keyed by `allow.digest(context)`, so one plan's answer never serves another.

## Accounts groundwork (EXEC-MU-ACCOUNTS Phase 0, 2026-11-16)

Phase 0 of the multi-user plan changes nothing the current user sees; it secures what a second account would reach.
The contract is `verification/edge_multiuser/access_tiers/CONTRACT.md` (sections 3, 4, 6 and 12); the defects it closes
are ERRORS M259, M468, M469, M471, M472 and M473.

Sign-in throttle (`app/throttle.py`, table `edge_bff.auth_throttle`, migration `20261116_002`):
- 10 sign-in tries per login (case-folded, trimmed) and client address in 15 minutes, counted in PostgreSQL, so every
  instance and every restart sees the same count; tries from another address do not keep the account out (re-check
  R1-9). Each try is decided and counted in one locked transaction before the password check (`throttle.attempt`:
  advisory lock on the scope and key hash, window sum, UPSERT), so a concurrent burst reaches the password check at
  most 10 times (C1 H1, ERRORS M477). The next try answers 429 `SIGN_IN_RATE_LIMIT` with `details.retry_after_s`,
  `Retry-After` and the wait in its message. A success clears that count, so only failed tries remain. Each counter
  has its own label inside the key's HMAC (R1-10), so no typed value can produce another counter's key.
- Switch on, per account (R1-16, NIST SP 800-63B-4): at most 100 consecutive failed passwords over both logins and
  every address (`identities.sign_in_failures`, migration `20261119_010`), decided and counted before the check; the
  100th locks the password 24 h, answered as a wrong password; then the count restarts at 90. A success, a reset by
  email code (which also clears the resetting client's per-login count) or a change clears it; the operator unlock
  (below) too.
- Password work (every derivation and Pwned Passwords call: sign-in, registration, reset, change) runs on its own pool
  of 4 threads (`passwords.PasswordWork`), never on the default executor the database calls use; over 16 requests at
  once the next is answered 503 `SERVICE_UNAVAILABLE` with `Retry-After` (R2-37).
- Every login typed is counted, known or not, and the password is checked before the login is compared, so neither
  the answer nor its timing tells whether an account exists.
- The client address (right-most `X-Forwarded-For`, else the socket peer) is recorded under `signin_ip` (30 in 15
  minutes) but not enforced until a probe proves what Railway's edge sends (contract section 4, "Client IP").
- Keys are stored only as HMAC-SHA256 with `EDGE_SESSION_SECRET`; rows older than 2 days are deleted by the hourly
  session clean-up.
- `/ready` now also reads `edge_bff.auth_throttle`: an edge-bff of this version is not ready (503 `NOT_READY`) until
  the migration is applied, rather than refusing every sign-in.

Error contract (`app/errors.py`, M471): every refusal of edge-bff's own, FastAPI's and Starlette's included, has the
shape `{"error": {"code", "message", "details"}}`; messages are plain English without internal names (EXEC-UI-1019B).

| Status | Code | The page does |
| --- | --- | --- |
| 401 | `UNAUTHENTICATED` | goes to sign-in (the only answer that means "signed out") |
| 401 | `USER_CHANGED` (made by the page, not the server) | another login's session appeared under an open page: the write is not sent, pending writes are dropped, the user state is cleared and the page reloads |
| 403 | `CSRF_INVALID` (only the CSRF check sends it) | reads the session once more and repeats the write once, only if the session is still the page's own login |
| 403 | `FORBIDDEN` (any other 403) | keeps the session and shows the refusal; never retried |
| 403 | `CAPABILITY_REQUIRED` (`details.capability`, `details.display_name`) | keeps the session and shows the words |
| 403 | `ORIGIN_REJECTED` | unchanged |
| 404 | `NOT_FOUND` | not found (another user's item reads the same) |
| 405 | `METHOD_NOT_ALLOWED` | shows the refusal |
| 422 | `INVALID_INPUT` (`details.fields`: the API names, never the values) | shows the refusal |
| 429 | `SIGN_IN_RATE_LIMIT` (`details.retry_after_s`) | shows the wait message |

`PLAN_EXPIRED`, `MFA_REQUIRED` and `LIMIT_REACHED` are read by the pages already (words in `static/edge-labels.js`,
`EdgeLabels.access`) and are sent from Phase 1 on. Every `main.py` refusal, the older `error(code, status)` helper's
included (`INVALID_CREDENTIALS`, `ORIGIN_REJECTED`, store and Orc codes), carries `code`, `message` and `details`; a
code relayed without a message of its own gets its status class's message. Server and page share one English wording
(`app/errors.py`, `EdgeLabels.access`).

Manual agent routes (M259, M474): `GET /api/v1/dev/manual/steps` and `POST /api/v1/dev/manual/steps/{step_id}` are
for an owner in `EDGE_ADMIN_OWNERS` only (default `EDGE_OWNER`; 403 `CAPABILITY_REQUIRED`, capability `admin.manual`),
and the POST is a write (Origin and `X-CSRF-Token`). Orc answers only the steps of the run's own owner.

Hooks prefix (`app/hooks.py`, contract section 6): the Origin check skips exactly `/api/v1/hooks/`, for callers such
as a payment or email provider that cannot send EDGE's Origin; the body size cap and the security headers stay. A hook
route has no session or CSRF, must verify a signature over the raw body, and is registered in `HOOK_ROUTES` with its
verifier. No hook route exists in Phase 0.

Route walk (`tests/test_route_table.py`): every `/api` route is public by an explicit list (sign-in, `/health`,
`/ready`) or depends on the session; every write depends on `write` (session and CSRF), sign-in and hooks excepted;
every hook route is registered with its verifier. A new route that misses one fails CI.

Shared front-end layer (`shared/`, M471, M473):
- `shared/edge-session.ts` is the one session module of EDGE. The six Vite pages (Terminal, Backtest, Screener,
  Radar, Overview, Watchlist) import it; every page stage of the Dockerfile copies `shared/` beside its own folder, and
  `.github/workflows/edge-bff-image.yml` builds every stage when `shared/` changes.
- The shell loads the same code as `/edge-session.js` (`window.EdgeSession`, before `edge-client.js`), built by
  `node shared/build-shell.mjs` (from `apps/edge-bff`, after `npm ci` in `terminal/`, whose esbuild it uses).
  `node shared/build-shell.mjs --check` and `tests/test_storage_registry.py` fail when `static/edge-session.js` is not
  the build of the source: run the build after every edit of the module and commit both files.
- It owns the error contract above, the session call with CSRF, and the storage registry.
- Page identity (C1 M1, C2 #2, ERRORS M477): each page keeps the login of its first session read. A later session
  read of another login is refused with 401 `USER_CHANGED` and the write is never sent, so a CSRF repeat goes out only
  for the page's own account. A change of login (`USER_CHANGED`) or the `cleared` broadcast of another page drops the
  pending writes; the page's own 401 (its session ended) keeps them, stamped with its identity (`1888e8b2`). On
  `cleared` an app page reloads, and the shell resets its views of the previous account (the sign-in page shows) and
  reads the session again. A page ignores its own broadcasts. The shell repeats a write after `CSRF_INVALID` only
  when the session read again is its own login. The Screener stops writing `scr.last` after a reset, the `pagehide`
  flush included.
- Storage registry: every localStorage, sessionStorage and IndexedDB key of the shell and the pages has one entry in
  `STORAGE`, classed `browser` (how this browser shows EDGE: theme, widths, folds) or `user` (anything of an
  account). Sign-out, or a sign-in with another login than the last one on this browser, removes the `user` keys and
  the IndexedDB `terminal-files` (`clearUserState`). `tests/test_storage_registry.py` fails on a key found in the code
  without an entry: **a new browser storage key needs its entry in `shared/edge-session.ts`, then
  `node shared/build-shell.mjs`.**
- A browser with no last-login mark (EDGE last used there before Phase 0), or with a Phase 0 mark (the bare login),
  holds state of an unknown account and is cleared at the first sign-in, except for user #1: the session answer's
  `access.seed` (the switch-off principal or the seed row) keeps it, moves its Phase 0 drawing stamps and uploads its
  preferences once, with the switch off and on (`noteIdentity`, `checkUser`; ERRORS M478 C3 B1, C4). A sign-out
  broadcast also clears every other tab's sessionStorage `user` keys.
- Terminal drawings kept in the browser while the account cannot be reached are stamped with the page's identity
  (never the last-login mark; nothing is kept while it is unknown) and join only that login's account (M468, M477).

## Beta and live websites (EXEC-MU-ACCOUNTS "Production environment", user decisions 2026-11-19)

One Railway environment, two websites on one database: the beta is this service, edge-bff, at its Railway address, for
the admin only, with `EDGE_MULTIUSER` off as today; the live site is a second service, edge-bff-live, on the user's
domain, with the switch on. Only the website is doubled: the database, the market-file bucket, terminal-api,
backtest-worker, screener-worker, the AI and every data job are one and shared. `EDGE_SITE` (`beta`, the default, or
`live`) tells the two apart (fix round of the round-2 re-check, ERRORS R2-1, R2-2, R2-3, R2-7, R2-8, R2-13, R2-23,
R2-26, R2-33, R2-34, R2-36, R2-38; `.railway/railway.ts` holds the live service as a comment until its variables are set).

- **Impossible pairings stop the start** (`config.py validate`): `EDGE_SITE=live` without `EDGE_MULTIUSER=true`; the beta
  with the switch on (outside `EDGE_ENVIRONMENT=local`, where the tests run both); `EDGE_AI_WORKER_ENABLED=true` on the
  live site; `EDGE_EMAIL_MODE=log` with the switch on outside `local` (it was allowed in `dev`, the Railway environment
  both sites run in), unless `EDGE_EMAIL_LOG_ALLOWED=true` says so on purpose (a test with no real person).
- **Each queued row carries its site** (`edge_bff.jobs.site`, `edge_bff.backtest_jobs.site`, migrations `20261119_020`
  and `_021`, default `beta`: every earlier row is the admin's). Each site's loop claims, reaps and prunes only its own
  site's jobs, so a job is dispatched by the code, the principal and the release file of the site that took it.
- **The loops** (each with its switch, all off with `EDGE_WORKER_ENABLED=false`): the AI job loop on the beta only (AI is
  admin-only, D1); a backtest loop on each site; the email sender only where the switch is on (the live site); the
  hourly housekeeping (`app/worker.py Housekeeping`: expired sessions, throttle rows, never-verified registrations, then
  the outbox rows of addresses left with no account) in
  its own task, each purge in its own transaction and try, in batches of 500, retried after a doubling backoff, and
  skipped while the other site runs the same purge (an advisory try-lock). Once edge-bff-live runs, the beta gets
  `EDGE_HOUSEKEEPING_ENABLED=false` so the live site is its one owner.
- **What the live site does not serve** (`principal.py beta_only`, `live_view`): the Monitor (AI) and admin tabs, the
  admin rights of `rights.py` and every item at the lab stage. Their routes answer 404 `NOT_FOUND` there, before the
  session is read (`/monitor` and `/c/<id>` too), and every principal is masked: it never holds them, `'*'` included
  (it reads as every flag capability of the catalog that is not beta-only; the workers' `allow` is never `"*"` there).
  The second factor is decided by the account's own grants, so user #1 still needs it on the live site.
- **Sessions are bound to their site**: the beta (switch off) accepts only sessions without an account, the live site
  only an account's sessions.
- **Start-up** (ERRORS R2-3, R2-36): readiness, the seeds and the catalog names run before the loops; while they fail
  (a database restarting, a migration not applied), `/ready` answers 503, no loop runs, and the attempt is made again
  every `EDGE_POLL_SECONDS` (and on each `/ready`), logged `startup_not_ready`, then `startup_done`.
- **`GET /version`** answers `{"site", "commit"}` (`RAILWAY_GIT_COMMIT_SHA`, null when unset), for the push to live.
- **Shared secrets** (ERRORS R2-8, R2-26): `EDGE_SESSION_SECRET` (throttle and CSRF HMAC), `EDGE_CODE_SECRET` (email
  codes) and `EDGE_MFA_KEY` (the one TOTP row per user) key rows of the shared tables, so edge-bff-live holds edge-bff's
  values as Railway references (`${{edge-bff.NAME}}`), never values of its own.

### Guests, the boxes and the pre-launch mode (track guest, decisions of 2026-11-19)

The user's words: "user tetap bisa search ticker, tapi ketika dia klik ticker selain bbca maka akan keluar pop up box to
login (jika belum login) dan jika sudah login maka akan keluar pop up box (to upgrade plan)"; "1a - bukan hanya chart,
nanti ada indikator dll yg juga mungkin di show ke user. jadi design harus plug and play dan fluid"; for the live site
before the launch "Terbuka, tapi belum bisa mendaftar", "Dan hanya admin yang bisa login (saya)", then "A". Notes:
`verification/edge_multiuser/fix_round/guest.md`.

- **The guest plan** (migration `20261119_070`): `edge_bff.plans.for_guests` marks the one plan a visitor without an
  account gets (seed `guest`: the free plan's Terminal grants, BBCA, price, 730 days, no indicator). Its rows are read
  on every guest request through the same `read_grants` and `can()` as every plan (`principal.py guest_principal`), so
  a change of its rows changes what visitors see with no code; it never holds `*`, `admin.access`, an admin right or a
  beta-only key, whatever its rows say.
- **Where a visitor gets it** (`EDGE_GUESTS`, default on the live site, refused with the switch off): only on the routes
  that ask for it, `auth.need(capability, guests=True)` and `auth.visitor`: the Terminal relay `/api/terminal/v1/*`, `GET
  /api/v1/catalog/{kind}` and `GET /api/v1/auth/guest` (the guest plan's access in the session answer's shape, `visitor`
  true, no CSRF token). Every other route answers 401 without a session, so the shell shows the sign-in page there
  (`tests/test_route_table.py GUEST_OPEN`). A guest writes without CSRF (no session to ride; the Origin check holds).
- **The client address** (`principal.py client_of`): the right-most `X-Forwarded-For` entry, the hop Railway's edge adds
  to every request it forwards, when it is an IP address; without one (a request that did not pass the edge, or a hop
  that is not an address) there is no guest principal and the answer is 401 (fail closed). The socket peer counts only on
  a developer machine (`EDGE_ENVIRONMENT=local`). The visitor's key towards terminal-api (`x-terminal-client`) is an HMAC
  of the address under `EDGE_SESSION_SECRET`, never the address; terminal-api counts each visitor's quotas with it.
- **The boxes** (`terminal/src/app/locked.ts`, the shell's `LockedDialog`, words `EdgeLabels.locked`): the Terminal
  derives what is locked from the session answer's access and the catalog route (`live.ts lockRules`), lists every
  ticker in its search with a lock on the ones the plan lacks, and asks the shell for the box when one is chosen, or a
  locked indicator, or the saved layouts without `terminal.layouts`: a visitor gets "Sign in" (and "Create account"
  while registration is open), an account the upgrade box ("Coming soon" and `EDGE_UPGRADE_CONTACT`, or that the contact
  comes soon). A visitor's drawings last as long as the page.
- **The pre-launch mode** (`EDGE_PRELAUNCH`, default on the live site until the launch, refused with the switch off):
  registration, its code and its resends answer 403 `REGISTRATION_CLOSED` (the register page says registration opens
  soon); only the admin (an account whose grants hold `*` or `admin.access`) and the accounts marked
  `edge_bff.users.test_account` sign in; every other account gets 403 `SIGN_IN_CLOSED` after its password was checked
  like any other. The mark changes only beside its `admin_audit` row of the same transaction (a deferred trigger);
  `scripts/edge_test_account.py` makes or marks a test account for an address and a plan (as a job:
  `scripts/onboarding/edge_test_account_job.py`), and the person sets the password with "Forgot password". Visitors
  still open the Terminal.
- **`GET /api/v1/auth/config`** with the switch on: `{"multiuser", "registration", "prelaunch", "guests",
  "upgrade_contact"}`; with it off `{"multiuser": false}` as before.

## Accounts (EXEC-MU-ACCOUNTS Phase 1, 2026-11-16/17)

Phase 1 builds EDGE accounts behind the switch `EDGE_MULTIUSER` (default `false`; it goes on only at Phase 6). Contract:
`verification/edge_multiuser/access_tiers/CONTRACT.md` sections 0-5 and 12. Tables: migrations `20261116_003`,
`20261117_001` and `20261117_002` (`DATABASE_CHANGELOG.md`). The independent checkers' findings and their fixes:
ERRORS M478.

The switch and what it changes:

| | `EDGE_MULTIUSER=false` (default, today) | `EDGE_MULTIUSER=true` (Phase 6) |
| --- | --- | --- |
| Sign-in | `EDGE_LOGIN` / `EDGE_PASSWORD_VERIFIER`, exactly as before | a username or email and the account's password (`edge_bff.identities`) |
| Principal | user #1: owner `EDGE_OWNER`, every capability (`*`), admin rights from `EDGE_ADMIN_OWNERS`, version `env` | the session's account: role `admin` every capability, role `user` none (the plan catalog of Phase 2 replaces this) |
| Account routes (table below) | 404 `NOT_FOUND`, except `GET /api/v1/auth/config` = `{"multiuser": false}` | open |
| Email sender loop | not started | started with the worker (`EDGE_EMAIL_ENABLED`; an error `email_sender_off` is logged when it is off) |
| Admin MFA | none | required before any admin route (403 `MFA_REQUIRED`) |
| Sessions | as before, and only a session the switch-off sign-in made (no account: `user_id` NULL); an account's session never opens a switch-off site (ERRORS R2-1) | idle timeout `EDGE_SESSION_IDLE_SECONDS` (default 28800), at most 5 per user, `last_seen_at` written at most once a minute; sessions still waiting for the admin's second factor capped apart at 3, never counted towards or revoking the 5; a new session token when MFA is passed |
| Seed of user #1 | at every start when `edge_bff.users` is empty; its password identity follows `EDGE_PASSWORD_VERIFIER` while it holds the seed's own copy (`identities.seed_verifier_sha256`); once the account set its own password with the switch on, it is never overwritten (ERRORS R2-2) | the identity is the account's own and is never overwritten |
| Preferences (below) | served for user #1 | served per account |

The seed: user #1 is the configured owner (`edge-private` on dev), role `admin`, status `active`. Its username is
`EDGE_LOGIN` lower-cased when that fits the username rule and is not reserved, else `admin_1` (`edge` is reserved, so
dev's seed is `admin_1`). Its password identity is a copy of `EDGE_PASSWORD_VERIFIER`, so the password does not
change. On dev, user #1's live login was then set by the operator (2026-11-20, ERRORS M513 A1): the username in
`EDGE_ADMIN_USERNAME` and the first password in `EDGE_ADMIN_INITIAL_PASSWORD` (both variables of `edge-bff-live`),
written by `scripts/edge_account_login.py`; the beta's login (`EDGE_LOGIN`, `EDGE_PASSWORD_VERIFIER`) is unchanged. Every replica takes one advisory lock, so two starting together make one row. A failed seed keeps the
switch-off sign-in working (logged `account_seed_failed`); with the switch on the start-up is tried again and no loop
starts until it succeeds (`/ready` answers 503 meanwhile). A switch-off start copies a changed `EDGE_PASSWORD_VERIFIER`
only over the seed's own copy: `identities.seed_verifier_sha256` is the sha256 of the verifier the seed last wrote, and a
password change or reset on the switch-on site (the live one) writes another verifier, which no later start overwrites
(migration `20261119_022`). The switch-off sign-in itself still reads `EDGE_PASSWORD_VERIFIER`.

Principal (`app/principal.py`): the owner of every request comes from it and only from it. Every router takes
`routes(app, auth)`: `auth.principal` (401 `UNAUTHENTICATED`), `auth.writer` (plus CSRF), `auth.need(capability)`
(403 `CAPABILITY_REQUIRED`), `auth.admin()` (the capability and MFA). `tests/test_principal.py` greps `app/` for
`settings.owner`: only the seed and the switch-off mapping may read it. `GET /api/v1/auth/session` keeps today's keys
and adds `owner_key`, `username` and `access` (`plan`, `role`, `status`, `expires_at`, `mfa_ok`, `capabilities`,
`limits`, `version`, `next`).

Account routes (`app/auth_flows.py`; POST with the exact Origin; a refusal in the error contract's shape):

| Route | Body | Answer |
| --- | --- | --- |
| GET `/auth/config` (public) | — | `{"multiuser": true/false}`; the sign-in page shows Register and "Forgot password?" only when true |
| POST `/auth/register` | `username`, `first_name`, `last_name`, `email`, `phone`, `password`, `password_repeat` | always 202 `CODE_SENT` for valid input, whether the email or username exists or not; an existing address gets the "account exists" email instead of a code. A new pending registration of its own, bound to this browser by the registration cookie (below); an earlier registration of the address is never changed |
| POST `/auth/register/verify` | `email`, `code` (`username` to choose another) | 200 and the session cookie, only from the browser that registered (its registration cookie); the address's other pending registrations are deleted; 400 `CODE_INVALID_OR_EXPIRED` for any wrong, expired or used code, or a code of another browser's registration; 409 `USERNAME_TAKEN` only after the code is proved |
| POST `/auth/code/resend` | `email`, `purpose` (`register`/`reset`) | always 202 |
| POST `/auth/password/forgot` | `email` | always 202 |
| POST `/auth/password/reset` | `email`, `code`, `password`, `password_repeat` | 200 `{"next": "sign_in"}`; every session revoked, nobody signed in, a notification email |
| POST `/auth/password/change` (writer) | `current_password`, `password`, `password_repeat` | other sessions revoked, a notification email |
| POST `/auth/sign-out-all` (writer) | — | every session of the account |
| POST `/auth/mfa/enroll` (admin, write) | — | `otpauth://` URI and 10 recovery codes, shown once |
| POST `/auth/mfa/verify` (writer) | `code` or `recovery_code` | the session's `mfa_passed_at`, a new session token (the pending one revoked; take the answer's `csrf_token`); the session answer; 403 `MFA_LOCKED` (below) |
| POST `/hooks/email/resend` | Resend's signed event | Svix signature checked over the raw body; each `svix-id` once (`email_hook_events`); a bounce or complaint goes to `email_suppression` |

Registration cookie (ERRORS M478, C1 P1-H1, C2 #1): `edge_registration`, a random token, HttpOnly, SameSite=Strict,
path `/api/v1/auth/`, 24 h; only its SHA-256 is stored (`users.registration_hash`). A code activates only the pending
registration whose cookie comes with it, so the code must be entered in the same browser where the account was
registered (the code page says so). Every registration is its own pending row; an address has at most one account
that is not pending (`users_email_one_account`).

Tabs a principal cannot open (3e, CONTRACT.md 8b):

- Every tab the site offers stays in the rail.
- A tab without `<tab>.view` (`*` opens every tab) shows `LockedTabPage` (`static/edge-app.js`) instead of its app.
  - A visitor is asked to sign in.
  - An account gets the plan words: Coming soon and the contact of `EDGE_UPGRADE_CONTACT`.
  - The words are `EdgeLabels.locked`.
- The Terminal shows its locked parts in place: the IHSG of Statistics, the Flow Timeline's head and the Events
  button each say Locked and open the same box (`terminal/src/main.ts` `lockedPage`).

The A2 fix (ERRORS M517, CONTRACT.md section 4 "Codes" and "Throttle") added two more cookies:

- **Reset cookie** `edge_reset`: a random token, HttpOnly, SameSite=Strict, 1 h, set by every "Forgot password?" and
  reset resend answer.
  - A reset code works only in the browser that asked for it (`email_codes.binding_hash`, migration `20261120_001`).
  - So a stranger's wrong codes or requests never use up or replace the owner's code.
- **Device cookie** `edge_device`: HMAC-signed with `EDGE_SESSION_SECRET` over the account id, the time and the
  account's current verifier. It is set where the password is proved (sign-in, registration finished, password change)
  and ends with the password or after 180 days. Nothing is stored.
  - That browser's tries skip the account's lock of 100 consecutive failures (it has 10 failures a day of its own).
  - Its reset requests use 5 code emails a day of their own instead of the address's 10.
  - It never signs anyone in.
- **Per-client cap:** one client address causes at most 4 of an address's 10 daily code emails.
- **Registration count:** a registration's hourly and daily count is the address's from that client.
- **Pending registrations at sign-in:** a sign-in compares the newest pending registration of each client address
  (`users.registration_client_hash`, migration `20261120_002`), so one stranger's registrations fill one of the three
  places.
- **Known browser and the per-login limit:** a known browser's sign-in skips the per-login limit of its client address
  (a stranger on the same network shares it). Its tries count under its own limit, in one step before the check.
- **Wrong-code counts:** a reset's wrong-code counts are keyed by the browser that asked for the code.

Sign-in of a pending account (C1 P1-M1): the right password of a registration not yet verified answers the same 401
`INVALID_CREDENTIALS` as a wrong one; within the send limits a fresh code is mailed and this browser gets the
registration cookie. `EMAIL_NOT_VERIFIED` (contract section 4) is not used any more. With registration open, the
sign-in page adds to a 401: "If you have just registered, check your email for a code and enter it on the Verify page",
with a link. A 401 that restarted nothing keeps this browser's registration cookie (sets it again; an unused one when it
has none). Every switch-on sign-in derives the password exactly 1 + `PENDING_CHECKED` (3) times, padded with the
configured verifier, so its time says nothing about how many registrations an address has.

Rules: codes are 6 digits, HMAC-SHA256 with `EDGE_CODE_SECRET`, valid 300 s, 5 tries each and at most 20 failed tries
per user per day (429 `LIMIT_REACHED`); a reset's failed codes are also counted per address, whether or not it has an
account, so that 429 tells nothing about the address (R1-8); a `USERNAME_TAKEN` answer uses one of the code's 5 tries
(R1-12). One code email per address per 60 s (a notification email never holds a code back, R2-10) and 10 emails a
day; a new registration of an address (from any browser) mails it at most once per hour and three times a day, inside
those 10 (a later one in the hour answers the same 202 and changes nothing; recorded decision N4 in M478: whoever's
address was registered by someone else first may wait up to an hour for their own code), and one registration is
mailed at most 3 times a day (its code, resends and sign-in restarts; R1-13). Registering again from the same browser
when nothing new was made keeps that browser's registration cookie (R1-11). Passwords 8 to 256 characters after NFKC
normalisation (verifiers made before it are still accepted), any character, refused when found in Pwned Passwords
(k-anonymity range API, 2 s; when it cannot answer the password is accepted and `PWNED_CHECK_UNAVAILABLE` logged); a
verifier is scrypt N=2^14, r=8, p=5 (OWASP's minimum equivalent, `scrypt$n=16384,r=8,p=5$<salt>$<hash>`; R2-29), and
one of the cost before it (`scrypt$<salt>$<hash>`, p=1) still signs in and is replaced at that sign-in; a check costs
the same whatever the verifier's age. A reset, a change, a sign-in and an MFA verify write under the account's lock and
only while what they rest on still holds (R2-9). A phone is normalised to E.164 (`08…` → `+628…`), not verified; a
pending user is deleted 24 h after creation, and 24 h after they were made the sent, failed, expired or suppressed
outbox rows of an address with no account go too (`edge_bff.purge_email_outbox(max_rows)`, migration `20261119_012`,
the housekeeping's batches; the runtime holds no DELETE on the outbox; R2-24). Retention (the user's decision of
2026-11-19, "a"): every sent, failed, expired or suppressed outbox row of every address goes 30 days after it was made
(the same function), with the email codes no longer usable (used, or expired unused) 30 days after they ended
(`store.PURGES` `codes`) and the handled webhook deliveries 30 days after they arrived
(`edge_bff.purge_email_hook_events(max_rows)`, `hook_events`; the runtime holds no DELETE on them either); a row not
yet sent, a live code and `email_suppression` are kept.

Email (`app/mailer.py`, `app/email_texts.py`, plain English): a code and its email are written in one transaction
(`edge_bff.email_outbox`). The sender is its own task beside the backtest loop, claiming one row at a time with
`FOR UPDATE SKIP LOCKED` and a lease.
- `EDGE_EMAIL_MODE=log` (default): the email is written to the log, the code masked unless `EDGE_ENVIRONMENT=local`,
  and the row is marked sent with its payload kept, so a tester reads the code from the row. Allowed only with
  `EDGE_ENVIRONMENT=local` when the switch is on (ERRORS R2-26: no longer `dev`, the Railway environment of the live
  site too), or with the explicit `EDGE_EMAIL_LOG_ALLOWED=true` for a test of the live site before its Resend key, with
  no real person (logged `email_log_mode_allowed` at every start while it is on).
- `EDGE_EMAIL_MODE=resend`: POST `https://api.resend.com/emails` with the row's `Idempotency-Key`; retried after 5 s,
  30 s and 2 min, then `failed`; the payload is nulled once sent; a code email past its expiry becomes `expired`, never
  sent. Needs `RESEND_API_KEY` and `EDGE_EMAIL_FROM` (an address); `RESEND_WEBHOOK_SECRET` (`whsec_…`) signs the
  webhook at `/api/v1/hooks/email/resend`.

Admin MFA (`app/mfa.py`): TOTP (RFC 6238, SHA-1, 30 s, 6 digits, ±1 step, a used step never accepted again).
Besides the 10 tries per 15 minutes, 100 consecutive wrong authenticator codes (10 recovery codes) lock that way in
(403 `MFA_LOCKED`, "Wait 24 hours or reset your password by email; an operator can also unlock it.", with
`details.unlock_at` and `details.use`, the other way while it is open: `recovery_code` or `code`, none when both are
locked, by the lock test `mfa_try` decides with, ERRORS M519). The `/mfa` page shows the unlock time in local time,
goes to the way `use` names, waits for the unlock when it names none, and keeps "Forgot password?"). A lock lasts 24 h, then the count restarts at 90 (8), so 10 (2)
more tries come before the next lock; a correct code resets the counts; a password reset by email code clears counts
and locks. A confirmed authenticator is replaced only by a session that passed MFA within the last 10 minutes
(`auth_flows.MFA_RECENT_SECONDS`, decided with the enrolment's row lock; an older pass answers 403 `MFA_REQUIRED` with
`details.recent_s` 600, and the `/mfa` page asks for a code of the current authenticator, then starts the set-up again),
and only when a code of the new one proves it: until then the new enrolment waits beside it (`mfa_totp.pending_nonce`, recovery codes marked
`pending`, migration `20261119_011`) and the old authenticator and its recovery codes keep working (R1-7). A code
confirms only the enrolment it was checked against (R2-11); the cap is decided and counted under the enrolment's row
lock (R2-12). Operator unlock: `scripts/edge_mfa_unlock.py --username <name> --reason "<why>"`, run as a job on the
private network only (EXEC.md EXEC-MU-ACCOUNTS, Phase 1 deploy steps, step 9); it clears that account's MFA and
password counts and locks, writes one `admin_audit` row with actor `operator`, and prints only the user id and the
counts. The secret
is HMAC-SHA256(`EDGE_MFA_KEY`, user id ‖ a stored 16-byte nonce)[:20], never stored: changing `EDGE_MFA_KEY` after an
admin has enrolled invalidates every authenticator, so the key is set once and kept. The `/mfa` page shows the QR code
with the vendored `static/qrcode-generator.js` (qrcode-generator 1.4.4, MIT, licence in
`static/qrcode-generator.LICENSE`), served from this origin.
The phone and every recovery code lost (live checker ACC-3): the same script with `--remove-enrolment` removes the authenticator and its recovery codes and ends the account's sessions (audited `mfa.remove`); the next sign-in starts the first set-up. A signed-in admin replaces the authenticator from "Password and sign-in".

Variables (all checked at start; with the switch off a missing one never stops it, a set one is still checked; the
secrets never appear in `repr(Settings)`):
`EDGE_MULTIUSER` (true/false only), `EDGE_SESSION_IDLE_SECONDS` (at least 60), `EDGE_CODE_SECRET` and `EDGE_MFA_KEY`
(at least 32 characters; required with the switch on), `EDGE_EMAIL_MODE` (log/resend), `EDGE_EMAIL_ENABLED` (true/false
only, like every loop switch), `EDGE_EMAIL_FROM`, `RESEND_API_KEY`, `RESEND_WEBHOOK_SECRET`, `EDGE_SITE` (beta/live).

Preferences (`app/preferences.py`, contract 4b, user 2026-11-16): an account's preferences and saved items that the
pages kept only in the browser come back on any device. `GET /api/v1/preferences` gives every key of the principal's
owner with its version and the limits; `PUT /api/v1/preferences/{key}` (writer) `{value, version}`: 201 created, 200
replaced, 409 `PREFERENCE_CONFLICT` with the current value for a stale version, 422 `PREFERENCE_LIMIT` (64 keys,
64 KiB per value, 1 MiB in all). They work with the switch off too, for user #1.

Front-end (`static/index.html`, `shared/edge-session.ts`):
- One route table, `ROUTES` in `edge-app.js`, read by `go()` and `currentPath`: the tab pages (`auth`), `/login`, and
  the account pages `/register`, `/verify`, `/forgot`, `/reset` (`open`: shown only while `/auth/config` says
  `multiuser`, else the sign-in page) and `/mfa`. `main.py` serves each path; a new page needs a row here and a route
  there, and its words in `EdgeLabels.pages`.
- Identity: a page keys its user by the session's `owner_key` (else the login), so a renamed username is the same user.
- Sync rule of the storage registry: every `user` key is either `sync` (a preference or saved item, copied to the
  account through `/api/v1/preferences`; only an exact localStorage key) or `cache` (the account holds the original
  elsewhere, or it is transient). After its session read the shell loads the account copy into this browser and, when
  the local state is this same identity's, uploads a local value the server lacks once; a change is written a second
  later with the version it was read with. `tests/test_storage_registry.py` fails on a `user` key without exactly one
  flag, and on a change of the synced set (`SYNCED`): a new synced key is a decision recorded in the test.

## Plans and releases (EXEC-MU-ACCOUNTS Phase 2, 2026-11-17)

The switch `EDGE_MULTIUSER` stays off: the configured owner keeps every capability (`*`, version `env`) and nothing
visible changes. With the switch on, access comes from data, never from code (CONTRACT.md section 8a):

- **Plans** (`edge_bff.plans`, migration `20261117_003`): `admin`, `paid` and `free` (the default). The plan keys
  appear only in that migration's seed; `tests/test_plan_catalog.py` fails on a plan key in `app/`.
- **Capabilities** (`edge_bff.capabilities`): each has a kind and a plain-English meaning. The database refuses a
  value that does not fit its kind (trigger `capability_value_check`). Should one be read anyway, it fails closed: a
  limit reads 0 and a list reads [] (ERRORS M480).
  - `flag`: `true`, or `false` in an override that takes the plan's flag away.
  - `limit`: a non-negative integer; no row means no limit.
  - `list`: strings.
  - `items`: `{ids, stages, all}`. An item `<family>:<id>`, for example `terminal.indicator:I01`, is held when its id
    is listed, its release stage is listed, or `all` is true.
- **Grants:** `plan_capabilities` (per plan, versioned) and `user_capability_overrides` (per user, with a reason and an
  optional end). An override replaces the plan's value.
- **Subscriptions** (`edge_bff.subscriptions`): one `active` row per user. A row counts only between `starts_at` and
  `expires_at` (NULL = no end); expiry is decided at read time. A user without a live subscription gets the default
  plan, and `access.expired_plan` names a plan that ended.
- **Resolution** (`app/accounts.py`, one statement; `app/principal.py`): `p.can(key)` and `p.limit(key)`. A route
  refuses with `CAPABILITY_REQUIRED`, or `PLAN_EXPIRED` when only the ended plan held the capability.
  - The MFA requirement follows the resolved capabilities (`*` or `admin.access`).
  - Every answer made for a principal (any path, the Terminal's data calls included) carries `X-Edge-Entitlements`.
    That is the principal's version, which also covers the plan's end and the release stages. The shared page module
    reads the session again when it changes.
  - An admin route always needs `admin.access` (and so MFA). With the switch on, `/ready` needs the catalog tables.
- **User #1:** at start, edge-bff gives the seed account an active `manual` subscription with no end, to the plan that
  holds `*` (found by data). It is given once, while the seed row has no subscription at all; a cancelled one is never
  given back. Its log events are `account_seed_plan_ambiguous`,
  `account_seed_plan_refused` and `account_seed_plan_failed`.
- **Release stages:** `catalog/releases.json` (hand-kept; `app/releases.py`) gives each indicator, Flow indicator,
  candlestick pattern, Screener metric and Screener preset the stage `lab` (admin only) or `released`. An id missing
  from the file is `lab`. `tests/test_releases.py` fails until a new registry id has its line, and its message prints
  the line to add.
- **Tab stages:** the file's `tabs` list gives each tab its stage; an unlisted tab is `lab`. A tab is the first part
  of a capability key or a page of the shell.
  - On the live site a lab tab's keys are refused to everyone, the admin's `*` included, and its rail entry is
    hidden (`hidden_tabs`). The beta keeps it.
  - `tests/test_live_switch.py` fails when a tab has no entry.
  - How work moves from the beta to the live site: `LIVE_PROMOTION.md` and `scripts/live_diff.py`.
- **Catalog route:** `GET /api/v1/catalog/{kind}` lists the entries the principal holds. The page module reads it with
  `catalog(kind)`, cached in memory per entitlement version.
- **To change what a plan holds:** UPDATE `edge_bff.plan_capabilities` (raise its `version`) through a reviewed migration
  or operator statement, with the user's approval. It takes effect on the next request; no deploy is needed.

## Route gates per tab (EXEC-MU-ACCOUNTS Phase 3a, 2026-11-17)

With the switch off nothing changes: the configured owner's principal holds `*` (EDGE_ADMIN_OWNERS unset means that
owner). With the switch on, each route asks `auth.need(capability)` (writes `auth.need(capability, write=True)`, the
CSRF check first) and refuses 403 `CAPABILITY_REQUIRED`, or `PLAN_EXPIRED` when only the ended plan held it
(CONTRACT.md 8b, decision D5: reads need the view or the item's capability, writes the run or save one):

- Backtest (`app/backtest.py`): `backtest.view` for the catalog, the list, status, result, events and cancel;
  `backtest.run` for signals and submit. A queued job is checked again at dispatch: an owner whose plan no longer holds
  `backtest.run` gets the job FAILED `CAPABILITY_REQUIRED` (or `PLAN_EXPIRED`), and the worker is never called.
- Screener (`app/screener.py`): `screener.view` for the catalog, universe, saved items and the star list;
  `screener.run` for run, preview, validate, counts, saving an item and the star; deleting an item needs the view.
- Terminal saves: `terminal.layouts`, `terminal.presets` and `terminal.drawings` on every route of their module.
- Watchlist lists (`app/watchlist.py`): `watchlist.view` (the page files are gated in `app/pages.py`).
- `tests/test_phase3a_gates.py` walks `app.routes` of these modules: a new route without its `ROUTE_CAPS` entry, or
  without the `need` that entry names, fails with the entry to add.

Fix round after the checkers (ERRORS M481):
- the Screener star (`/api/v1/screener/watchlist`) also needs `watchlist.view`, and makes the first Watchlist list
  only within `watchlist.lists`;
- a full backtest queue answers 429 `LIMIT_REACHED` naming `details.limit` (`backtest.queued_jobs`), `allowed` and
  `retry_after_s`, with `Retry-After` 30; the Backtest catalog's `limits.queued_per_owner` shows the account's own number;
- refusals name the capability as the person sees it (`details.display_name` from `edge_bff.capabilities`, read at
  start and at most every 300 s), never the internal key;
- with the switch off, the start refuses an `EDGE_ADMIN_OWNERS` that leaves out `EDGE_OWNER` (it would lock the one
  account out of every tab).

Saved-item caps are `min(plan limit, HARD)` (`Principal.capped`), HARD being the module constant, the storage
guarantee no plan or override can raise: `terminal.layouts_max` (`LAYOUT_LIMIT` 50), `terminal.presets_max`
(`PRESET_LIMIT` 100), `terminal.drawings_max` (`SET_LIMIT` 5000), `screener.saved_items` (`SCREEN_LIMIT` 50),
`watchlist.lists`/`per_list`/`indicators` (20/50/8; `per_list` also caps the Screener's star) and
`backtest.queued_jobs` (`BACKTEST_QUEUED_PER_OWNER` 3). The routes that publish limits (`/api/v1/terminal/layouts`,
`presets`, `drawings`, `/api/v1/watchlist/lists` `limits`, the Screener catalog's `limits[]`) report the principal's
own numbers. The paid seed holds today's values (migration `20261117_004`, decision D6). A lowered plan keeps the
rows but cannot read them until it is raised again (D5); a replace of an existing item is never refused by a cap.

## Route gates: Monitor, Terminal proxy, page files (EXEC-MU-ACCOUNTS Phase 3a, 2026-11-17)

CONTRACT.md section 8b, decisions D1 and D5. With the switch off the configured owner holds `*` (EDGE_ADMIN_OWNERS
unset = that owner), so nothing changes for it; an owner EDGE_ADMIN_OWNERS does not list is refused these routes too.

- **Monitor (AI), admin only for now (D1):** every read (runs, progress, events, conversations, messages, models,
  exports) needs `monitor.view`; every write (submit, stop, branch, pin, rename, hide, table export) needs
  `monitor.chat`. A run's model (the request's, else Orc's `server_default`) must be held as `monitor.model:<id>`, and
  `saniti/claude-manual` needs `admin.manual` (`app/monitor.py`). `/api/v1/models` keeps one shared cache and lists, per
  principal, only the models it holds (a default only when held). Models and providers are not changed here.
- **At dispatch** (`app/worker.py`): a queued run's owner is read again; without `monitor.chat` or the model the run ends
  FAILED `CAPABILITY_REQUIRED` before any Orc call.
- **Terminal proxy** (`/api/terminal/v1/*`): `terminal.view` before any call to terminal-api.
- **Page files** (`app/pages.py`): `/api/v1/<family>/index` and `/file/<name>` need `overview.view`, `radar.view`,
  `watchlist.view` or `sector.view` (EXEC-SECTOR-ANALYSIS), checked before the shared caches. Files are sent `private, no-cache` with their ETag; a `?sha=`
  request with a matching If-None-Match answers 304 only after the check. The principal's terminal headers are built
  before the caches too, so what edge-bff refuses for that principal itself (a quota of 0) holds whether the caches are
  warm or cold (re-check R1-31). A page file is granted, counted and audited on terminal-api for the principal whose
  request missed the caches, once per process and sha256; a read from the caches counts against no one's Terminal
  quota (re-check R1-5, R1-31: the caches are shared by design, CONTRACT.md section 15). terminal-api's quota refusal of
  a grant is 429 `LIMIT_REACHED` with `Retry-After` (it was `<FAMILY>_QUOTA`).
- `tests/test_phase3a_monitor_pages.py` walks these routes: a new one needs its line in `ROUTE_CAPS`.

## Contact support (EXEC-MU-ACCOUNTS Phase 4, 2026-11-22)

- **After the Phase 4 checker (ERRORS M536):** the emails go to every active account holding the admin right by its
  grants (`admin.admin_holders`; the role grants nothing), the owner's address being user #1's; an email whose ticket is
  gone is dropped, with or without images (`email_dropped`, `ticket_gone`). An upload is bounded before its body is
  read: 30 an hour per account counted, refused ones too (`throttle.SUPPORT_UPLOAD`, 429 `support_uploads`), and the
  hour and day limits checked first; the images are decoded off the event loop, and the 500 MB ceiling is checked under
  one lock for every sender. `TELEGRAM_NOTIFY_URL` needs a real host and a port after a colon.

The user, 2026-11-22: "saya minta dibuatkan panel sebelah kiri di live iconnya kotak surat ... Ada yang submit maka
langsung ke admin dan telegram dan ke email pribadi saya"; "hanya yang login ... lampiran hanya 2A"; "go".
`app/support.py`, migration `20261122_001`, `tests/test_support.py`; CONTRACT.md 10 "Contact support".

- **Who sends:** a signed-in account holding `support.send` (the free and the paid plan; the admin through `*`; an
  override `false` takes it from one account). A visitor holds it on no plan: the shell's mailbox opens the sign-in box.
- **`POST /api/v1/support`** (CSRF), JSON `{kind, subject, body, details, images: [{name, type, data}]}` ->
  201 `{ticket_id, created_at}`:
  - `kind` one of `bug`, `question`, `account`, `billing`, `feature`, `data`; `subject` 1 to 120 characters, one line
    (runs of white space become one space); `body` 1 to 5000 characters; a hidden or control character (Unicode
    categories Cc, Cf, Cs, Zl, Zp; the description's line breaks and tabs and the joiners kept;
    `text_rules.hidden_character`) is refused with its own reason;
  - `details`: only the page's own keys (`page`, `frame`, `viewport`, `timezone`, `language`; short strings); edge-bff
    adds the browser (User-Agent), the build, the site, the plan and the time;
  - `images`: at most 3, base64; each a PNG, JPG or WebP as its own first bytes say (never its name or stated type),
    at most 5 MiB; its name kept without folders, ending in its type's extension;
  - every refusal is 400 `INVALID_INPUT` `{fields, reasons}` naming the field and the fix, or 400 with field `request`
    for a body that is not a JSON object.
- **Read only when allowed** (`main.py` support_precheck, before the body): a stated `Content-Length` above
  `REQUEST_BYTES` (three images as base64 and 64 KiB), or not a number, 413 `REQUEST_TOO_LARGE`; no session 401; a second
  factor still pending 403 `MFA_REQUIRED`; no `support.send` 403 `CAPABILITY_REQUIRED`. A body without a stated length (a
  proxy may forward it chunked) is read after these checks, up to `REQUEST_BYTES`. Every other write keeps 128 KiB.
- **Limits:** `EDGE_SUPPORT_PER_HOUR` (default 5) and `EDGE_SUPPORT_PER_DAY` (default 20) per account, counted under a
  lock per account: 429 `LIMIT_REACHED` with `details.limit` `support_hour` or `support_day`, `allowed`,
  `retry_after_s` and `Retry-After`. The images of every ticket together at most `EDGE_SUPPORT_STORAGE_MB` (default 500):
  past it 503 `SUPPORT_STORAGE_FULL`, and the message goes without its images.
- **Where it goes** (one transaction, then after the commit):
  - `edge_bff.support_tickets` and `support_attachments` (gone with the account);
  - one email per active admin account with an address (`edge_bff.email_outbox`, purpose `support`): the message in
    full with the technical details and the images attached when the live site's sender sends it (Resend
    `attachments`), Reply-To the sender's address. In the log mode its text is never logged (`private`). An email whose
    ticket was deleted before it was sent is dropped (`email_dropped`);
  - a Telegram summary to telegram-monitor (`TELEGRAM_NOTIFY_URL`, its `/notify`; `TELEGRAM_SUPPORT_SECRET`, the secret
    of its source `EDGE_Support` only; either unset: no summary): the number, site, type, subject, username, plan,
    number of images and the admin page's link (`EDGE_ADMIN_ORIGIN`, the beta's https origin; unset: no link). Only an
    answer 200 counts; the instance that runs the housekeeping (the live site) sends a summary not yet answered again
    every 10 minutes, at most 5 times, within a day;
  - the admin page's Support inbox (the beta; Phase 4, slice 4).
- **Kept** (the user, 2026-11-22: "2B"): a ticket's images are deleted 90 days after it is marked done (`IMAGE_DAYS`;
  the hourly housekeeping's `support_images` purge, `store.PURGES`, which sets `images_purged_at` and frees the storage
  ceiling); the text stays until the account is deleted; the admin page deletes a ticket by hand.
- **The shell** (`static/edge-app.js` SupportDialog, `static/edge-labels.js` `support`, `static/edge-client.js`
  `Edge.sendSupport`): the mailbox (Contact support) in the left menu and in the phone's EDGE bar, shown while the site
  offers the tab `support`. A visitor's click opens the sign-in box (LockedDialog, kind `support`); an account without
  `support.send` gets the upgrade box. The dialog uses the support dialog of EDGE's own design, whose styles
  `static/index.html` had kept (`.support-form`, `.support-body`, `.support-field`, `.support-attach`, `.support-files`,
  `.support-error`, `.support-success`, `.support-foot`). It checks each file as the server does (its first bytes, its
  size, at most three: `SUPPORT_LIMITS`, held equal to `app/support.py` by `tests/test_support.py`), shows each reason
  of the server under its field and a refusal of the whole message (the hourly limit, the storage) above the actions,
  and, once sent, the ticket's number, issue type and subject; the focus returns to the mailbox.
  `tests/test_support_browser.py`: the visitor, the account with its images, the reasons, the limit, the layout, the
  phone at 390 and 360 px.

## Admin page (EXEC-MU-ACCOUNTS Phase 4, 2026-11-22)

- **After the Phase 4 checker (ERRORS M536):** every admin route and the code step act only as a known, active account
  (`Auth.admin_account`: with the switch off user #1's seed is read again when the start did not read it, else 503
  `ADMIN_ACCOUNT_UNAVAILABLE`; a disabled owner 403 `ACCOUNT_DISABLED`, and no new admin session). The admin right is
  judged at every moment it may apply (`admin_timeline`: an admin override's end, a subscription's start or end); an
  action is refused for the last admin only when it takes that holder away, now or for good (`kept_admins`), and the
  account answer closes Disable for that holder. A registering account is listed and found by the name it asked for
  (`requested_username`); Resend code is closed without `EDGE_CODE_SECRET`; the list carries each account's usage. A
  sign-in through the authenticator code (`/mfa`) keeps the page it was shown at, its query too.

The user, 2026-11-22: "1A 2A 3A", then "1A, 2B, 3A". `app/admin.py` (its docstring lists every route),
`tests/test_admin.py`, `tests/test_admin_page.py`; CONTRACT.md 10. The admin actions on accounts are slice 5; there is no
account deletion (the user, 2026-11-22: "Tidak usah ada opsi ini").

- **The page** (`admin/`, TypeScript + Vite, built into `static/admin-app` by the image's `admin` stage; the design
  system's spec v1.2 and canonical layer copied into `admin/src/styles/`): the code step first, then six views, the
  Support inbox first (New, Done, All; a ticket in full with its images, Mark done or new, Send to Telegram again,
  Delete ticket with a reason), Overview, Accounts (search, status, plan; one account with Show for its address or phone,
  which asks why), Audit (action, from, until; Download CSV), Plans (read-only), Settings. Every text a person wrote is
  set as text, never markup. Its own words and data paths are in its build only; the shell holds the route, an icon, the
  four words of `admin` in `edge-labels.js` and the frame wrapper (`tests/test_admin_page.py` holds that). Its copy of the
  spec keeps the system's rules as they are and names EDGE's own Inter in its usage note (`admin/tests/styles.test.mjs`).
- **Who gets its files** (`main.py` `page_app(..., admin_only=True)`): the admin on the beta (`auth.lab_admin`:
  `admin.access` past the second factor, never on the live site), before the code step, whose screen they draw; a
  visitor, any other account and the live site get 404, the assets `private`. Its policy is the Screener's
  (`connect-src 'self'`). `GET /admin` is the shell on the beta and 404 on the live site, as `/monitor`.
- **The shell** (`static/edge-app.js`): the route `{path:"/admin", ..., needs:"admin.access"}`; `AdminPage` frames
  `/admin-app/` with the ticket of its own address (`/admin?ticket=<id>`, the Telegram summary's link); the rail's
  shield (desktop) and the account menu's "Admin page" (every width) for a principal the site offers `admin` and that
  holds `admin.access`. **A sign-in stays where it was shown** (`landing`, `opens`): signed out at a workspace page the
  account can open (the route's `needs`, else `<title>.view`), the sign-in keeps that page and its query; an account page
  (`/login`, `/verify`, `/mfa`) or a page the account cannot open leads to the landing page as before. This holds for
  every tab: a person signed out at `/backtest` lands on `/backtest`.
- **The actions on an account (slice 5; the user, 2026-11-22: "A, lanjut slice 5")**, each with a reason and its audit
  row in the same transaction, none on the admin's own account:
  - `POST users/{id}/status` `{status: active|disabled, reason}` (`account.status`): disabled, every session of the
    account ends (every site, `accounts.ACCOUNT_SESSIONS`); an account still registering is not activated here;
  - `POST users/{id}/plan` `{plan_key, expires_at|null, reason}` (`account.plan`, the plan and end before and after): a
    manual subscription from now (`provider` manual, `provider_ref` admin-page, a word no plan key is), the active one
    cancelled; extending is the
    same plan with a later end; the end is a moment after now with its zone (the page sends the chosen day's last moment);
  - `POST users/{id}/sessions/revoke` `{reason}` (`account.sessions_revoke`, the number ended);
  - `POST users/{id}/resend-code` `{reason}` (`account.resend_code`): a new registration code to an account still
    registering, through the flows' own `_issue_code` after the address's lock; it is bound to the registration's browser
    (it finishes nothing alone) and keeps the registration's 3 mails a day (429 with its wait). It needs `EDGE_CODE_SECRET`
    equal to the live site's (else 503 `CODE_UNAVAILABLE`, the log naming it): a code hashed with another key is one
    the live site never takes.
  - **The guards**, checked after the write in the same transaction (a refusal rolls everything back): an account's
    admin right ('*' or `admin.access`, resolved by `accounts.GRANTS`, the sessions' own rule) never changes here, another
    admin's plan is the operator's, the visitors' plan is never given, and at least one active account keeps the admin
    right. A refusal of the database's own rules (the restricted-plan rule's 23514, a value outside its domain) is the
    field's reason in the database's words with its hint.
  - The account's answer says which actions are open (`actions`: `{open, why}`) and `holds_admin`; the page offers the
    open ones and shows the why of the others; the routes refuse alike (`tests/test_admin_actions.py`).
- **The runtime role**: `tests/test_runtime_role.py` runs every admin route and the support upload with the app's every
  connection acting as `edge_bff_runtime` (the role edge-bff's login holds deployed; `conftest.RoleStore`), the routes
  taken from the app, so a new admin route is checked against the role's grants from its first commit.
  `EDGE_TEST_APP_ROLE=edge_bff_runtime` runs any suite that way (the helpers too).
- **Its session**: the code step renews the session (a new token); the page reads the session again for its next write,
  and the shell's next write repeats once on `CSRF_INVALID` with the renewed session (`shared/edge-session.ts` send), so
  nothing needs a reload (`tests/test_admin_page.py`: Contact support sent after the step).

- **Where:** the beta only. Every `/api/v1/admin/*` route depends on `auth.admin_page`: `admin.access` is a beta-only
  capability (`BETA_ONLY_TABS`), so the live site answers 404 before any session is read.
- **The code step (1A):** the beta's sessions (switch off) count as past the second factor, so the admin page asks for
  the authenticator code of user #1 itself, the one used on the live site. `GET /api/v1/admin/step-up` answers
  `{needed, enrolled, available}`; `POST /api/v1/admin/step-up` (CSRF) `{code}` is checked by
  `AuthFlows.check_second_factor` (the same throttle, failure caps, lock and used steps as `POST /api/v1/auth/mfa/verify`,
  on the same rows) and answers a new session cookie and CSRF token (`Store.session_step_up`: the old session revoked,
  the new one with `mfa_passed_at`, the same end), so the code is asked once per beta session. A `recovery_code` is
  refused unchecked (400 `INVALID_INPUT`, field `recovery_code`): single-use and shared with the live site, one spent here
  would be gone there. Codes locked (the live site's count): 403 `MFA_LOCKED` with `details.step_up` and no `use`
  ("...locked on both sites for now. Wait 24 hours..."). Before the step every admin data route answers 403
  `MFA_REQUIRED` with `details.step_up` ("The admin page needs your authenticator code..."). It needs `EDGE_MFA_KEY`
  equal to the live site's (`config.shared_key_marks` logs both marks at start); unset: 503 `MFA_UNAVAILABLE`, whose
  words name no setting (they ask for the operator) while the log line `admin_step_up_unavailable` names it. With the
  switch on: 404.
- **Reads:** `overview` (accounts by status and plan, live sessions, tickets, image bytes, emails waiting or failed),
  `users` (`q`: any part of a username or name, with `%` and `_` taken as typed, or an address in full, any case, never a
  part of one, so a masked address cannot be narrowed without a reveal; `status`, `plan`, paging by `before` and `limit`
  1 to 200, the address and phone masked), `users/{id}`, `audit` and `audit.csv` (filters `action`, `actor`, `target`,
  `since`, `until`; the file at most `CSV_ROWS` 10,000 rows, more refused with 400 naming `since`, never cut short; every
  cell through `text_rules.export_cell`), `plans`
  (read-only), `settings` (only the names in `SHOWN_SETTINGS`; a new setting is shown once it is named there, and the
  test refuses a `repr=False` one), `support` (`status` new, done or all), `support/{id}` (the sender's address masked)
  and `support/{id}/images/{n}`: the image as its own type, `Content-Security-Policy: default-src 'none'; img-src 'self';
  style-src 'unsafe-inline'; sandbox`, `Cache-Control: private, no-store`, `Cross-Origin-Resource-Policy: same-origin`
  (`main.py` keeps a response's own sandboxed `default-src 'none'` policy instead of the page policy).
- **Actions** (CSRF; each audited in the same transaction, `edge_bff.admin_audit`): `users/{id}/reveal`
  `{field: email|phone, reason}` (`account.reveal`; an account without the value answers `value: null`, unaudited); `support/{id}/status` `{status: done|new, reason?}`
  (`support.status`; done sets `done_at` and `done_by_user_id`, which starts the images' 90 days, new clears them);
  `support/{id}/telegram` (the summary sent again while it was never answered; 503 `TELEGRAM_UNAVAILABLE` when the site
  has no Telegram settings, the log line `support_telegram_unavailable` naming each missing one); `DELETE support/{id}` `{reason}` (`support.delete`; the ticket and its images). A reason is
  1 to 1000 characters with no hidden character but line breaks. A refusal is 400 `INVALID_INPUT` naming the field and
  the fix, or 404 `NOT_FOUND`.

## Terminal data gate: headers and refusals (EXEC-MU-ACCOUNTS Phase 3c, 2026-11-18)

CONTRACT.md 8b "3c in detail", decisions D2, D3 and D6. One module, `app/terminal_access.py`, builds what terminal-api
is told and refuses what the plan lacks; `tests/test_terminal_access.py` checks it. With the switch off the configured
owner holds `*`: its header says `admin: true`, its body is forwarded byte for byte and terminal-api answers as before.

- **Headers** (`headers(settings, p)`, the only place the proxy key is read): every terminal-api call made for a
  principal, from the proxy (`main.py forward_terminal`) and from the page files (`pages.py PageFiles`), carries
  `x-terminal-proxy-key`, `x-terminal-proxy-owner: <owner_key>` and `x-terminal-capabilities`, compact ASCII JSON of at
  most 8 KiB built from the principal only:
  `{"v":1,"version":"<principal version>","admin":bool,"tickers":"*"|[..],"datasets":"*"|[..],"history_days":null|N,"quota":{..}}`.
  - `admin`: `*` is held (then `tickers` and `datasets` are `"*"`, `history_days` null, `quota` `{}`);
  - `tickers`: the list `terminal.tickers` (no row: `"*"`);
  - `datasets`: the ids of `DATASET_IDS` (terminal-api's `price`, `broker`, `events`, `yield`, then `intraday` and
    `reference`) that `p.can('terminal.dataset:<id>')` grants, always a list for a principal without `*`;
  - `history_days`: `terminal.history_days` (no row: null);
  - `quota`: the limits the plan sets of `terminal.tickers_per_hour`, `tickers_per_day`, `files_per_hour` and
    `megabytes_per_day` (migration `20261118_002`: paid and free 60, 200, 300, 500), under terminal-api's own names;
    one the plan leaves out is left out, and terminal-api keeps its default. terminal-api takes 1 to 10^9: a larger value
    is sent as 10^9, and 0 answers 429 `LIMIT_REACHED` (`details.limit`, `retry_after_s` 3600, `Retry-After`) before
    terminal-api is asked (leaving it out would give the wider default).
  - Both terminal headers always go together beside the gateway key (terminal-api refuses one alone); an owner key
    outside terminal-api's rule `^[A-Za-z0-9._:@-]{1,128}$` answers 503 `TERMINAL_UNAVAILABLE`, logged.
  - The dataset and quota names are read from `apps/terminal-api` by the test, so they are written in one place here.
  - Longer than 8 KiB (a list of about 900 tickers): 503 `TERMINAL_UNAVAILABLE`, logged; never cut short.
  - Every value the plan catalog can hold maps onto what terminal-api takes (re-check R1-22): `history_days` above
    36600 is sent as 36600; 0 (the value of a limit that cannot be read) is sent as 0, terminal-api's empty window; a
    ticker outside `^[A-Z0-9]{1,12}$` is left out and logged (`terminal_tickers_dropped`, its count); a quota of 0 is
    403 `CAPABILITY_REQUIRED` naming the limit (waiting would not help). The catalog also refuses such values when they
    are written (migration `20261119_050`: `capabilities.value_min`, `value_max`, `item_pattern`).
- **Page-sent headers:** a request to a terminal-forwarding route that carries `x-terminal-proxy-key`,
  `x-terminal-proxy-owner` or `x-terminal-capabilities` is refused 400 `HEADER_NOT_ALLOWED` (`details.header`) before
  anything else (`terminal_access.guard`); no request header is ever copied to terminal-api.
- **Refused first** (`terminal_access.check`, a principal without `*`), 403 `CAPABILITY_REQUIRED` with
  `details.capability` and `details.display_name`, before any terminal-api call:
  - a ticker outside `tickers` (`terminal.tickers`): `manifest/<T>`, `logo/<T>` (a logo carries no market data, but one
    rule for every ticker path keeps the class closed; the page shows its monogram), `files`, `bundle`,
    `history/*?ticker=` (exactly one) and `cut/<T>/<dataset>`;
  - a dataset outside `datasets` (`terminal.dataset:<id>`): `files`' dataset, `history/price` and `history/broker`,
    `cut/<T>/<dataset>`;
  - with `history_days` 0, every dated path (`files`, `bundle`, `cut/*`, `history/*`): `terminal.history_days`;
  - `reference/*` is not refused (re-check R2-32): terminal-api answers a plan without the dataset `reference` with
    its own copy of the file (the whole ticker list since decision 1 of 2026-11-19, track guest; the rows of its
    tickers in a file with data per ticker; the broker list only with `broker`), announced as
    `/api/terminal/v1/reference/<name>/cut?sha256=<hex>` and relayed byte for byte like a cut;
  - a `bundle` whose every asked dataset is locked (its `datasets`, terminal-api's default `price, broker, events` when
    absent, plus `intraday` with a `timeframe`); with one open dataset it is forwarded and terminal-api answers the
    locked ones `{locked: true, capability}`;
  - `history/*` while `history_days` is set (`terminal.history_days`): it serves only the dates before the published
    files, outside the last N days;
  - a body or query that cannot be read (not JSON, not an object, a ticker that is not text, a repeated `ticker`):
    422 `INVALID_INPUT`. The checked JSON is what is forwarded (re-serialised), so terminal-api reads what was checked.
  - A forwarded GET route the check does not know is refused (fail closed); the test ties the route regex to it.
- **terminal-api's answers** (`terminal_access.relayed`, one rule for `forward_terminal`, the cut relay and the page
  files; re-check R1-1, R1-26, R2-4; CONTRACT.md section 3):
  - for a principal without `*`, an answer without `x-terminal-capabilities-applied: 1 <version>` (a terminal-api from
    before Phase 3c ignores the owner headers and would serve the plan in full) is 503 `TERMINAL_UNAVAILABLE`, logged
    (`terminal_capabilities_not_applied`); the switch-off owner holds `*` and needs none;
  - an acknowledged 2xx JSON answer reaches the page through `client.public_data` (ERRORS M260, the user's go
    2026-11-19 "a"): no private key (`PRIVATE_KEYS`: `reasoning`, `token`, `api_key`, ...) and no `*.railway.internal`
    address, as every Orc and worker relay; a cut's bytes and a logo are relayed as they are (never parsed). The walk
    in `tests/test_decisions_small.py` calls every route holding `terminal_access.guard` with each kind of proxy path,
    terminal-api planting both in every answer;
  - its 403 `capability_required` is 403 `CAPABILITY_REQUIRED` with `details.capability` and `details.display_name`;
  - its 429 is 429 `LIMIT_REACHED` with `details.limit` (`terminal.<quota>`), `details.allowed`,
    `details.retry_after_s` and `Retry-After`, from the fields terminal-api adds (an hour when it names none);
  - its 401, any other 403 (its own account, key or host rule) and a 400 about the owner headers edge-bff built are
    503 `TERMINAL_UNAVAILABLE`, logged with its status and code (`terminal_refused`), never the EDGE sign-in;
  - its 400 about the request is 400 `INVALID_INPUT` and its 404 404 `NOT_FOUND`, with its code as `details.reason`
    (and the field names of a 400); every 5xx is 503 `TERMINAL_UNAVAILABLE`. Its messages never reach the page.
- **The cut** `GET /api/terminal/v1/cut/<TICKER>/<dataset>` (`price`, `broker`, `events`, `yield`; D2 = A;
  terminal-api builds it with deterministic gzip and answers `application/gzip`). `/bundle` names a capped owner's files
  `{"year": null, "pack": "cut", "url": "/api/terminal/v1/cut/<T>/<ds>?sha256=<hex>", ..}`; the query is forwarded. The
  bytes are read raw from terminal-api and relayed exactly (no JSON parse, no decoding, no Content-Encoding added or
  relayed), with only Content-Type, Content-Length (checked against the bytes read), ETag, X-Terminal-Cut-Sha256 and
  Cache-Control, the latter always `private`; at most 64 MiB. Another status is answered by `terminal_access.relayed`.
  - The page loads a URL of this origin (one starting with `/`) with the session cookie (`credentials: 'same-origin'`,
    `terminal/src/data/rack.ts` `credentialsFor`), and a presigned URL of the storage host still without any cookie
    (`omit`); `terminal/tests/data/cut_credentials.test.ts`.
- **Route walk:** every route that calls terminal-api (`terminal_read`, `terminal_write`, `page_index`, `page_file`)
  depends on `terminal_access.guard`, and no other module reads the proxy key, so a new route cannot skip either.
