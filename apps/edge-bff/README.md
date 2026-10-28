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

Build and checks, from `terminal/`: `npm ci`, `npm run build` (typecheck + build), `npx vitest run tests/calc`
(parity), and the 1:1 check `TERMINAL_REFERENCE_HTML=<reference file> node tests/visual/compare.mjs <out>` then
`python3 tests/visual/diff.py <out>` (must report 0 differing pixels). `/terminal-app/?fixture=reference` runs the
page on the reference's synthetic data.

## Backtest tab (EDGE backtest, 2026-10-26)

Rules and decisions: `backtest/CONTRACT.md`; wire types: `backtest/src/core/contract.ts`. The page `backtest/`
(TypeScript + Vite) is built by the Dockerfile's `backtest` stage into `static/backtest-app/` (not kept in git) and
shown under the EDGE top bar in a frame at `/backtest` (Backtest tab, next to Terminal). `/backtest-app/` has the
terminal page's CSP (its own scripts only, inline style attributes, Google Fonts, and `connect-src` to the bucket
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

| Method/path (session cookie; PUT, POST and DELETE with Origin + `X-CSRF-Token`) | Result |
| --- | --- |
| GET `/api/v1/screener/catalog` | the worker's `CatalogResponse` with edge-bff's own limits added to `limits[]` (`saved_items`, `watchlist`, `saved_definition_bytes`, `request_bytes`, each with its rule and one right and one wrong example; a limit the worker lists is kept as it is); `ETag` = sha256 of the JSON bytes, `If-None-Match` -> 304 |
| GET `/api/v1/screener/universe` | the worker's `UniverseResponse`; `ETag` / 304 as the catalog |
| POST `/api/v1/screener/run` | `RunRequest` -> `RunResponse`, relayed as sent (`client_order` included) and answered with the worker's gzip bytes and `ETag`; latest wins per (owner, page): 409 `SCREEN_REPLACED` |
| POST `/api/v1/screener/preview` | `PreviewRequest` -> `PreviewResponse`, as the run; latest wins per (owner, page) in its own lane: 409 `PREVIEW_REPLACED` |
| POST `/api/v1/screener/validate` | `ValidateRequest` -> `{valid, definition_hash, normalized}` or the worker's 422 |
| POST `/api/v1/screener/counts` | `CountsRequest` -> `CountsResponse` (the worker's limit on definitions), as the run |
| GET `/api/v1/screener/items?kind=screen\|metric` | `{items: SavedItem[]}` of the owner (one kind, or both without `kind`), latest changed first, each with `needs_review` |
| PUT `/api/v1/screener/items/{item_id}` | `{kind, name, definition, revision?}` -> the stored item: no `revision` creates, the revision it was read with replaces (revision + 1); validated by the worker first (`/v1/validate`, its refusal relayed); 409 `REVISION_CONFLICT` (the id exists, or a stale revision), 409 `NAME_TAKEN` (`name` per owner and kind), 404 `NOT_FOUND`, 422 `LIMIT_EXCEEDED` |
| DELETE `/api/v1/screener/items/{item_id}` | 204; 404 `NOT_FOUND` |
| GET `/api/v1/screener/watchlist` | `{tickers: [{ticker, added_at}]}` (one list per owner) |
| PUT / DELETE `/api/v1/screener/watchlist/{ticker}` | 204, idempotent; 422 `INVALID_INPUT` (`ticker`, terminal-api's rule `^[A-Z0-9]{1,12}$`), 422 `LIMIT_EXCEEDED` |

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

## Front-end structure: editing the page without touching the API (EXEC-X, 2026-10-08)

The page is edited as one HTML file and its API wiring is not locked to the view. Four layers, each with one job:

| Layer | File | Change it when |
| --- | --- | --- |
| Transport (API, session, SSE) | `static/edge-client.js` | a BFF route or its JSON changes |
| View contract | `static/edge-view.js` (`EdgeView.toView`) | Orc's response shape changes; the only code that reads it |
| Words | `static/edge-labels.js` | wording, a label, a code's words, a status name |
| Look and layout | `static/index.html` (markup, CSS, renderers) | anything visual; renderers read the view model only |

- The Details panel (`EdgeView.sources`) lists Orc's `execution.hurdles` as "Hambatan proses", in Orc's own words
  (EXEC-FRICTION, M142); nothing when there were none.
- An answer's assumptions and limitations (`lists`) are folded under the answer as "Asumsi (n)" and "Batasan (n)"
  (EXEC-STYLE S3); nothing when a list is empty.
- Links that start with `/api/` (the export downloads) stay real requests; every other root link is kept portable
  through `staticUrl` (EXEC-EXPORT). After each redraw the element that had focus gets it back with its caret, and a
  keystroke in the message box redraws only when the box turns empty or non-empty (EXEC-TYPING).
- A table in an answer sorts by a click on a column title: descending (↓), ascending (↑), then the original order; the
  hovered title shows ⇅; a Total row stays last; Indonesian numbers, money scales and dates are read (`MdTable`,
  EXEC-SORT). The table's look is unchanged. A dash (`–`, a missing value in a table Orc builds, EXEC-TABLE) sorts
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
tab), and with migration `20261028_001` the screener's saved items and watchlist (see Screener tab), which hold no
market data. Jobs retain original inputs for deterministic replay, not answers. Pins/bookmarks do
not extend Orc's retention (code default 30 days, actual configuration must be checked before rollout). Expired
history returns 410.
There is currently no automatic purge of terminal job inputs/UI metadata or of backtest jobs: define an operational
retention policy before long-term use. Backtest result parts are deleted after 30 days; the backtest trials are never
reset (K3). Saved screener items and the watchlist are the user's own objects and are not purged (each owner at most
`SCREEN_LIMIT` items of each kind and `WATCHLIST_LIMIT` tickers); every statement on them names the owner. Sessions are cleaned when the loop starts and then hourly.

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
| POST `/auth/sign-in` | `{login,password}`; session cookie, login, CSRF token |
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
| EDGE_SESSION_SECRET | Random 32+ character secret, entered securely |
| EDGE_PUBLIC_ORIGIN | Exact HTTPS origin of the new service; set after domain allocation |
| EDGE_ENVIRONMENT | `dev` (use `local` only for loopback tests) |
| EDGE_SECURE_COOKIE | `true`; local tests alone use false |
| EDGE_SESSION_SECONDS | 86400 |
| EDGE_ORC_TIMEOUT_SECONDS | 3900, must exceed active Orc maximum + margin (minimum 3900 seconds) |
| EDGE_LEASE_SECONDS / EDGE_HEARTBEAT_SECONDS | 90 / 20 |
| EDGE_POLL_SECONDS / EDGE_WORKER_ENABLED | 2 / true |

Use one uvicorn process/one replica initially. Disable request access logs and proxy headers; authentication attempt
limiting is process-local. HTTPS termination is Railway's responsibility. No plaintext password, database credential,
Orc key, session secret or Railway token is bundled or stored in Git. Public errors are generic; private diagnostic
keys/addresses are filtered. The original inline renderer requires CSP `unsafe-inline`; unsafe-eval is not enabled.

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
