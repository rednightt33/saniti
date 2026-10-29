# backtest-worker (EDGE backtest)

Private HTTP service that computes the EDGE backtests. It is part of the backtest feature described in
`apps/edge-bff/backtest/CONTRACT.md`, which holds the rules and the decisions taken for the user.

- **Caller.** edge-bff (`app/backtest.py` WorkerClient) is the only caller. The page never reaches the worker.
- **Runtime.** Node 22 with type stripping and no npm dependency (user decision K1 = C, 2026-10-26).
- **What computes a result.** Every number comes from the shared core (`apps/edge-bff/backtest/src/core`). The core
  uses the Terminal's own indicator module (`apps/edge-bff/terminal/src/calc/indicators.ts`). The page, the Terminal
  chart and the worker therefore share one formula per indicator.
- **Data access.** The worker reads market data only through terminal-api: `/bundle` and the presigned file URLs it
  returns, `/manifest/{ticker}` (dates only, no file granted) and `/reference/{tickers|brokers}`. It holds no Postgres
  and no bucket credentials. terminal-api counts every file `/bundle` and `/reference` grant in the gateway account's
  quota and writes an audit row for each answer; `/manifest` grants nothing, has no quota and writes no audit row.

## Layout

| File | Role |
|---|---|
| `src/server.ts` | `node:http` API: authentication, routes, the job record, the preview queue, timeouts, start-up checks |
| `src/compute.ts` | the two long-lived `worker_threads` threads, one for jobs and one for signals previews; progress and results are sent as messages, cancellation uses a shared flag, `kill()` handles a run over its time |
| `src/run.ts` | one job end to end (`runJob`) and one signals preview (`runSignals`) |
| `src/validate.ts` | request checks before any download (unknown fields, page options, a portfolio's picked stocks, flow availability, broker codes against the broker list, the core's own validation) |
| `src/load.ts` | reads the files of a run within the limits: every manifest first, a portfolio's tickers without published files left out, the limits checked, then each ticker's downloads from its manifest while its URLs can still serve them or every file it names is cached, else from a new one; a URL that expired all the same is fetched again once; the date the broker data is published through (`brokerDataThrough`) |
| `src/terminal.ts` | the terminal-api client: `/bundle`, `/manifest`, the reference files, presigned files, sha256 and size checks, the cache (memory, optionally disk) |
| `src/catalog.ts` | `GET /v1/catalog` from the reference files (the tickers with their groups, the groupings the portfolio picker filters by), IHSG's published bars, the limits, the flow switch and the broker data's date |
| `src/config.ts` | environment variables, their defaults and their checks |
| `src/version.ts` | `engine_version`, `registry_version`, the start-up registry check |
| `src/errors.ts`, `src/log.ts` | the error shape and statuses; JSON log lines |
| `scripts/build-registry.mjs` | builds the core's `backtest-registry.json`; the server checks its hash at start |

## API

The header `x-backtest-worker-key: $BACKTEST_WORKER_KEY` is required on every route except `/health`. Without it the
worker answers `401 {"error":{"code":"UNAUTHORIZED"}}`.

| Route | Answer |
|---|---|
| `GET /health` | `{ok: true, engine_version, registry_version}` |
| `GET /v1/catalog` | `Catalog` (contract.ts): every reference ticker with its `groups`, the `groupings` the portfolio picker filters by (every column of the reference ticker file other than ticker, name and type, in file order, stocks counted; null, `''` and `Undefined` unclassified), the limits with `max_portfolio_tickers` (CONTRACT.md section 8, PF6) |
| `POST /v1/validate {request}` | `200 {ok: true, lineage_key, variant_hash, tickers}` (a portfolio's picked stocks in ticker order, the hashes of that canonical form), or `422` with the error: the request checks (`validate.ts`), then `FLOW_DATA_THROUGH` and `PERIOD_AFTER_DATA` with the code, field and message the job would fail with, read from terminal-api's manifests only (no `/bundle`, no file); `424 DATA_MISSING` (field `IHSG.price`) when IHSG has no price file |
| `POST /v1/signals` | the body is a `SignalsPreviewRequest`; the answer is a `SignalsPreview` |
| `POST /v1/jobs {job_id, request, context}` | `202 {job_id}`, `409 BUSY` or `422` |
| `GET /v1/jobs/{id}` | `JobStatus`, or `404 UNKNOWN_JOB` |
| `GET /v1/jobs/{id}/result` | `200` with the gzip of the result JSON (`Content-Encoding: gzip`), as often as it is asked until the next job starts; `409 NOT_FINISHED`; `410 RESULT_GONE` for the finished job a newer job replaced; `404 UNKNOWN_JOB` for any other id |
| `POST /v1/jobs/{id}/cancel` | `202 JobStatus`; a running job stops at its next check and ends `CANCELLED` |

### Signals previews

- Previews run on the preview thread while the caller waits.
- One preview computes at a time; the others wait in arrival order.
- When the caller disconnects, its preview is cancelled. A caller that leaves while the worker still reads the
  reference lists queues nothing, so the next preview never waits behind one computed for nobody (review V1).
- A preview reads the picked stocks `tickers`, checked as a portfolio's (below; field `tickers`, `tickers[i]`).
- A preview leaves out the tickers the run leaves out, with the run's shared code (`signals.ts`): a ticker without
  published files, or whose own data cannot serve the entry rule. They are listed in `warnings` as the result's
  `TICKERS_EXCLUDED` (`count`, `tickers`, `reasons`). When none is left the preview is refused with `UNIVERSE_EMPTY`
  (field `tickers`), as the run is, and a preview that reads broker files is held to `FLOW_DATA_THROUGH`. A preview
  never fails where the matching run succeeds (lead decision 2026-10-26).

### Jobs

- **One job at a time.** While a job runs, a job with another id gets `409 BUSY`. A POST with the current job's id
  answers `202` again, because edge-bff retries a POST whose answer it lost.
- **Checked before it is accepted.** The request is checked before the `202`. A refused request is a `422` and never
  becomes a job. A POST whose caller leaves while the worker reads the reference lists starts no job (review V1):
  edge-bff, which lost the answer, finds the id unknown and posts it again.
- **Only the latest job is kept.** The worker forgets the previous job when a new one starts, and keeps none across a
  restart. edge-bff turns the resulting 404 into `WORKER_LOST`.
- **The result is kept until the next job starts** (lead decision 2026-10-26). A caller that lost an answer can fetch
  it again. Once a newer job has started, the replaced job's result answers `410 RESULT_GONE` (its status `404`).
- **Progress phases.** `queued`, `loading`, `signals`, `backtest`, `sensitivity`, `monte_carlo`, `finalizing`, with
  `done` and `total` counts.
- **Cancellation.** The job checks for it between phases, between tickers while loading, inside the engine (per ticker
  and per calendar day), and between sensitivity cells. A result that completes after a cancel is dropped.
- **Time limit.** A job over `BACKTEST_TIMEOUT_SECONDS` ends `FAILED TIMEOUT`, and its thread is terminated. The next
  job starts a new thread.

### Synchronous calls

Validation, the catalog and a preview each get `BACKTEST_TIMEOUT_SECONDS`. Over that time they answer
`504 TIMEOUT`, and a preview over its time has its thread terminated. A preview and a job hand-over first read the
reference lists under a limit of their own (`504 TIMEOUT` as well).

### Errors

Errors have the shape `{"error": {code, field?, message?, details?}}`.

| Status | Codes |
|---|---|
| 422 | validation errors (among them `UNKNOWN_FIELD`, `INVALID_PORTFOLIO`, `UNKNOWN_TICKER`, `INVALID_CONDITION`, `UNKNOWN_BROKER`, `FLOW_UNAVAILABLE`, `FLOW_OUTPUT_EMPTY`, `INDICATOR_OUTPUT_EMPTY`, `PERIOD_AFTER_DATA`, `PERIOD_BEFORE_DATA`, `FLOW_DATA_THROUGH`, `UNIVERSE_EMPTY`), `LIMIT_EXCEEDED` (`details.limit`: `max_download_bytes`, `max_broker_rows`, `max_conditions`, `max_result_bytes`), `INVALID_JSON`, `INVALID_JOB_ID`, `INVALID_CONTEXT` |
| 424 | data errors: `DATA_MISSING`, `DATA_INTEGRITY`, `DATA_UNAVAILABLE` |
| 409 | `BUSY`, `NOT_FINISHED` |
| 404 | `UNKNOWN_JOB`, `NOT_FOUND` |
| 405 | `METHOD_NOT_ALLOWED` |
| 410 | `RESULT_GONE` |
| 504 | `TIMEOUT` |
| 500 | `INTERNAL_ERROR`, or `OUT_OF_MEMORY` when a thread ran out of heap |

A job's error is the same object, carried in `JobStatus.error`.

## What a job does

1. **Check the request** (`validate.ts`). Any field the page does not send is refused with `UNKNOWN_FIELD` and its
   path; `client_request_id` is edge-bff's, which takes it out before calling the worker. The checks include the
   page's options, the core's `validateRun`, the registry parameters and the condition shapes. A broker condition's
   code must be in terminal-api's broker reference list (`UNKNOWN_BROKER`). A condition id has the page's shape (1 to 6
   base-36 digits, `INVALID_CONDITION`), a list has at most `BACKTEST_MAX_CONDITIONS` enabled conditions
   (`LIMIT_EXCEEDED`), and a disabled condition is held to the same shape as an enabled one (it is stored with the job).
   A number or price line the chosen modes do not read is held to its type all the same (a number; a price line as a
   line mode takes it), not to the range its mode would check, and a price-action type without a threshold has no
   `value`.
2. **Resolve the tickers.**
   - Single mode: the one ticker, which must be of type `stock`.
   - Portfolio mode (user N 2026-10-27, PF1-PF5): the picked stocks `portfolio.tickers`, 1 to
     `BACKTEST_MAX_PORTFOLIO_TICKERS` (at most `engine.ts` MAX_PORTFOLIO_TICKERS, 12) distinct
     stocks of terminal-api's reference ticker list. The publisher writes that list from `IDX_Stock_Universe`, the
     same list it publishes the tickers' files from. An empty, too long or duplicated list is `INVALID_PORTFOLIO`
     (field `portfolio.tickers`); a ticker that is not a published stock, an index among them (an index is not
     tradable), is `UNKNOWN_TICKER` (field `portfolio.tickers[i]`). The page picks them by search or by the catalog's
     groupings: every column of the reference file other than ticker, name and type (sector and industry today; a
     value of null, `''` or `Undefined` is unclassified).
   - The order is not part of the request: the worker sorts the picked stocks (`signals.ts` byTicker) before it
     hashes, records the lineage or runs (`hash.ts` canonicalRequest), so the same set in any order gives the same
     `request_hash`, `variant_hash`, `lineage_key` and result bytes (PF3). The set is part of the variant, not of the
     lineage: another set of stocks with the same rules is another trial of the same line (PF4).
   - `portfolio.max_positions` is 1 to `BACKTEST_MAX_POSITIONS` (at most `engine.ts` MAX_POSITIONS, 12) and may exceed
     the number of stocks picked: a slot is `1 / max_positions` of equity whatever the number of stocks, and an idle
     slot stays cash (PF5).
3. **Load the data** (`load.ts`).
   - IHSG prices, and each ticker's prices and corporate actions.
   - Broker files only when a flow condition or `rank_by: 'fnet'` needs them. Measured 2026-10-27, the 12 largest
     broker files (BBRI TLKM BBCA ASII BMRI ANTM ADRO PGAS BBNI BUMI BRPT UNVR) hold 2,494,454 rows and 28.4 MB gzip
     together, far under `BACKTEST_MAX_BROKER_ROWS` (20,000,000 in dev): a full portfolio of picked stocks fits.
   - Every manifest is read first. A portfolio leaves out a stock terminal-api does not publish (404) or that has no
     file of a dataset the run reads (`DATA_MISSING`, listed in the warning `TICKERS_EXCLUDED`); in single mode that is
     the run's `DATA_MISSING`. The run is refused with `LIMIT_EXCEEDED`, before any download, when the manifest sizes
     exceed `BACKTEST_MAX_DOWNLOAD_BYTES` or the broker rows exceed `BACKTEST_MAX_BROKER_ROWS`. Cached files count
     too, so the same request gets the same answer whatever the cache holds. The engine runs exactly the picked
     stocks: each is loaded or left out, once, and `engine.ts` run refuses market data of another set
     (`INTERNAL_ERROR`, a loader error and never a result).
   - Then each ticker's files, from its manifest while that manifest's age plus `BACKTEST_HTTP_TIMEOUT_MS` is under
     its URLs' lifetime (`expires_in_seconds`) or while every file it names is in the memory or disk cache (no URL is
     needed), else from a new `/bundle` answer asked right before the ticker's downloads. A ticker whose file the
     bucket still refuses with 403 (an expired URL; a cached copy that fails its check is downloaded) is loaded once
     more from a new answer. A new answer's files are the ones read (`data_version`); they replace the ticker's first
     files in the totals, which are checked again before its downloads and on the files read. Each answer counts its
     files in terminal-api's quota and writes an audit row: a ticker costs one answer, two once its manifest is too
     old and a file of it is not cached, three with a 403.
4. **Check the period against the data.**
   - `FLOW_DATA_THROUGH` (`period.to`), before any download: a run that uses broker data, when `period.to` is after
     the date the broker data is published through. That date is the newest broker `data_through` of the stocks'
     manifests (`catalog.flow.data_through`): the publisher writes its date into the manifest of each stock whose files
     changed, so a stock without new files keeps an older one. When no loaded ticker's manifest reaches `period.to`,
     the other stocks' manifests are asked until one does; the run is refused only when none does, so exactly when
     `catalog.flow.data_through` is before `period.to`.
   - `PERIOD_AFTER_DATA`: `period.to` is after IHSG's last published bar.
   - `DATA_MISSING`: in single mode, no bar of the ticker falls inside the period.
   - Single mode: a `period.from` before the ticker's first published bar starts the run on that bar, with the warning
     `PERIOD_CLIPPED` naming both dates. A portfolio keeps its period.
   - `PERIOD_BEFORE_DATA` (engine): the primary benchmark has no close on or before the first day of the result
     calendar.
5. **Run the engine:** `prepare`, then `run` (`engine.ts`). A portfolio leaves out a ticker whose own data cannot
   serve the strategy: an indicator or flow series without any value on its bars up to `period.to`
   (`INDICATOR_OUTPUT_EMPTY`, `FLOW_OUTPUT_EMPTY`) or no broker row on them (`FLOW_UNAVAILABLE`), when its entry
   cannot switch on without that condition; otherwise the condition is false on every bar and the ticker runs, so
   what it trades up to a day never depends on its bars after that day (CONTRACT.md section 2). The warning
   `TICKERS_EXCLUDED` lists every left-out ticker with its error (`count`, `tickers`, `reasons`); `meta.tickers` holds
   the tickers the run ran on. A request error still fails the run, and in single mode these data errors do too. A
   broker without any row on a ticker's bars has a net of 0 there. When every picked stock is left out the run is
   refused with `UNIVERSE_EMPTY` (field `portfolio.tickers`; the message gives the count and the reasons by code),
   never a cash-only result (lead decision 2026-10-26). The result calendar is IHSG's bar dates and those of every
   picked stock whose bars were loaded, left out by the engine or not (PF8, CONTRACT.md section 4): whether a stock
   is left out is decided on its bars up to `period.to`, so the dates of the run, and the entries they allow, never
   depend on it. A stock the loader left out (no published file) has no bars read and adds no date. Measured by the
   lead 2026-10-27, the published prices have no stock bar on a day without an IHSG bar, so on them the calendar is
   IHSG's and PF8 changes no result.
6. **Sensitivity:** 25 reruns from `sensitivityPlan` (`robustness.ts`) on the same prepared data. Identical cells run
   once.
7. **Build the result:** `buildResult` (`result.ts`), which computes the statistics, tables, trials and the Monte
   Carlo. The result also carries `variant_hash`, `lineage_key` and `request_hash`, plus the versions (`hash.ts`).
8. **Pack the result:** JSON, then gzip, on the job thread. A result over `BACKTEST_MAX_RESULT_BYTES` of JSON is
   refused (`LIMIT_EXCEEDED`, `details.limit: max_result_bytes`) before it is packed: edge-bff would not store it.

The same request on the same published files gives the same result, except `meta.duration_ms`.

### Versions

- `data_version`: the sha256 over the files read (CONTRACT.md section 2).
- `registry_version`: the hash of `indRegistry.json` and `indicators.ts`, written into the registry artifact. At
  start, the server recomputes it from the files in the image and exits 1 when they differ.
- `engine_version`: the first 16 hex characters of a sha256 over the paths and sha256 of every file that decides a
  number: `apps/edge-bff/backtest/src/core/*.ts` and `*.json`, and `apps/backtest-worker/src/*.ts`. It is computed at
  start, not kept by hand, so it changes whenever that code changes.

## Configuration

Every variable is read once at start. A missing or invalid variable exits with code 1; the log line names the
variable and never its value.

"Required" variables have no default in the code. The Railway dev column holds the lead's initial dev values
(2026-10-26); the limits and the HTTP settings among them are to be measured again in the dev E2E (K7b).

| Variable | Default | Railway dev | Meaning |
|---|---|---|---|
| `PORT` | 8080 | 8080 (default) | HTTP port (`0.0.0.0`) |
| `BACKTEST_WORKER_KEY` | required | the secret shared with edge-bff | shared secret with edge-bff, ≥ 32 characters, never logged |
| `TERMINAL_URL` | required | terminal-api's private origin, e.g. `http://terminal-api.railway.internal:8080` | terminal-api origin: http(s), no path, no user name or password |
| `TERMINAL_PROXY_KEY` | required | `${{terminal-api.TERMINAL_PROXY_KEY}}` | terminal-api gateway key (D-U1), ≥ 32 characters, never logged |
| `BACKTEST_CACHE_BYTES` | required | 1500000000 | memory cache budget per thread (gzip bytes); 0 = none |
| `BACKTEST_CACHE_DIR`, `BACKTEST_CACHE_DIR_BYTES` | off | `/tmp/backtest-cache`, 1073741824 (the container's own disk, one replica; about three times the whole published data set: the publisher's packs were 302 MB on 2026-10-26) | optional disk cache and its budget. Every thread (and every replica on the same volume) shares the directory, under one budget: the directory's total, least recently used by any of them removed first. The directory must be one uid 1000 can create or write; one it cannot is no disk cache (each download logs `terminal_cache_error`). The budget must leave room on the volume |
| `BACKTEST_DOWNLOAD_CONCURRENCY` | required | 16 | HTTP requests in flight per thread |
| `BACKTEST_DOWNLOAD_RETRIES` | required | 3 | retries of a network error or 5xx answer |
| `BACKTEST_RETRY_BASE_MS` | required | 500 | backoff `base × 2^k` between retries |
| `BACKTEST_HTTP_TIMEOUT_MS` | required | 60000 | per HTTP request, body included; also the margin a `/bundle` answer's URLs must have left to be used for a download (its age plus this under `expires_in_seconds`), so a shorter value asks fewer new answers |
| `BACKTEST_FILE_ORIGIN` | required | `https://*.t3.storageapi.dev` (the host edge-bff's CSP allows for the same presigned downloads, `app/main.py`) | the origin every file and reference URL must have: scheme, host (a leading `*.` matches subdomains) and port; any other URL is `DATA_INTEGRITY` and never requested |
| `BACKTEST_MAX_FILE_BYTES` | required | 67108864 (the largest published file measured 2026-10-26 is BBRI's broker-archive pack: 2,218,292 bytes gzip, 14,456,717 inflated; the archive grows about 1.8 MB per year) | the most bytes one file may inflate to, and the most bytes of a body that is not a data file (a reference file, a terminal-api answer, a bucket error answer); over it `DATA_INTEGRITY` (a terminal-api or bucket error answer: `DATA_UNAVAILABLE`) |
| `BACKTEST_MAX_DOWNLOAD_BYTES` | required | 1500000000 | bytes of published files one job or preview may read |
| `BACKTEST_MAX_BROKER_ROWS` | required | 20000000 (the 12 stocks with the most broker rows hold 2,494,454 in all, measured from the manifests 2026-10-27, so no valid request reaches it today; it guards memory as the broker history grows: the worst-case 12-stock run peaked at 1.31 GB on Railway) | broker rows one job or preview may read |
| `BACKTEST_TIMEOUT_SECONDS` | required | 900 | longest job, preview, validation or catalog |
| `BACKTEST_MAX_CONDITIONS` | required | 32 | enabled conditions one list (entry, exit signals) may have; reported as `catalog.limits.max_conditions`; more is `LIMIT_EXCEEDED` (`details.limit: max_conditions`) |
| `BACKTEST_MAX_RESULT_BYTES` | required | 33554432, from the dev E2E (2026-10-27): the largest result a valid request can make is about 12 positions × every trading day of the published period as trades; measured 3,829,496 bytes of JSON for 4,176 trades (12 stocks, 12 positions, an entry true about every other bar, exit after one bar, 2018-01-02 to 2026-10-26), about 860 bytes a trade, so the bound (12 × about 2,150 days) is about 22 MB today. edge-bff takes the same value by the Railway reference `${{backtest-worker.BACKTEST_MAX_RESULT_BYTES}}` | the most JSON a job's result may have; over it the job ends `FAILED LIMIT_EXCEEDED` (`details.limit: max_result_bytes`) before the result is packed. Not in the catalog: the page cannot act on it |
| `BACKTEST_MAX_POSITIONS` | 12 (`engine.ts` MAX_POSITIONS) | 12 (default) | the most positions a portfolio may hold; reported as `catalog.limits.max_positions`; may only be lowered |
| `BACKTEST_MAX_PORTFOLIO_TICKERS` | 12 (`engine.ts` MAX_PORTFOLIO_TICKERS) | 12 (default) | the most stocks a portfolio or preview may pick; reported as `catalog.limits.max_portfolio_tickers`; may only be lowered |
| `BACKTEST_MONTE_CARLO_RUNS` | 1000 | 1000 (default) | the page's `monteCarlo(…, runs = 1000)`; a request asks for exactly this or 0 |
| `BACKTEST_QUEUED_PER_OWNER` | 3 | 3 (default) | reported in the catalog; edge-bff enforces it |
| `BACKTEST_FLOW_ENABLED` | off | 1 | `1` turns on the flow and broker conditions and `rank_by: 'fnet'` |

**Flow conditions.** They are enabled with `BACKTEST_FLOW_ENABLED=1`. The published broker files were checked against
SQL (`verification/backtest/FLOW_DATA_CHECK.md`): 12 tickers, every published year, 0 mismatches, values in IDR. While
the flag is off, `catalog.flow.reason` says so, and those conditions are refused with `FLOW_UNAVAILABLE`. While it is
on, `catalog.flow.data_through` is the date the broker data is published through. The broker data can end before the
price data, so a run that reads it and ends after that date is refused (`FLOW_DATA_THROUGH`).

**Limits.** The limits have no default in the code. The values above are the lead's initial dev values and must be
measured again in the dev E2E (K7b), not guessed. `BACKTEST_MAX_FILE_BYTES` is set from the largest published file
(above). `BACKTEST_MAX_RESULT_BYTES` gets its value from the results the dev E2E measures; edge-bff reads the
worker's value through the Railway reference, so both have the same value, and edge-bff stops reading a result past
it too.

**Timeouts.** edge-bff has its own `BACKTEST_TIMEOUT_SECONDS`, which limits the whole job on its side, polling
included. At that deadline edge-bff ends the job `TIMEOUT` and sends the worker a cancel.

**Memory.** Each compute thread has its own client and memory cache. Memory is therefore up to 2 ×
`BACKTEST_CACHE_BYTES`, plus the HTTP thread's IHSG files for the catalog. The disk cache (`BACKTEST_CACHE_DIR`) is
one for all of them. Every thread's client reads and writes the same directory, and so do a thread started again
after `kill()` and another replica on the same volume. A file one of them put is read from disk by the others. After
every put the cached files are brought within `BACKTEST_CACHE_DIR_BYTES` in all, the file least recently used by any
of them removed first. Two things are on top of the budget for a while: a file being put, until its put has evicted
(it is written as a `*.tmp` and then renamed), and, when clients put more at once than the budget holds, the files
put at once, until the next put (a put never removes a file another client put meanwhile). A `*.tmp` that `kill()`
cut off before its rename is removed once it is an hour old. This matters because a signals preview and the run
after it are on two threads and read the same files. Without the disk cache the run downloads every file of the
preview again. Measured on Railway dev 2026-10-27: a preview of 12 stocks downloaded 48 files (28.27 MB), and the
run after it the same 48 again plus 12 events files. Every download costs bucket egress. A ticker whose step-1
answer is too old asks a second `/bundle` answer (quota, audit row) only when a file of it is not cached. Each
cached copy is still checked when it is used, so a file another client damaged or removed is downloaded again, never
an error. Railway dev sets `/tmp/backtest-cache` (Configuration): the container's own disk, which serves the threads
of its one replica and starts empty at each deploy; replicas would share files only on a common volume. The budget
must leave room on the volume: a full volume fails every put (`terminal_cache_error` `ENOSPC`), which evicting
within the budget cannot fix.

**Catalog cost with flow on.** `catalog.flow.data_through` asks terminal-api for the manifest of every published stock
(`/manifest`, no file granted, no quota), `BACKTEST_DOWNLOAD_CONCURRENCY` at a time, on every catalog build.
terminal-api keeps manifests in memory until the publisher's next run; edge-bff keeps the catalog for a minute. The
worker does not cache the value: none of terminal-api's answers marks a publish exactly (`load.ts brokerDataThrough`
gives the reasons from `apps/terminal-publisher/publisher.py`), so a cache could keep an old date after a publish. A
check (job, preview, validation) asks no further manifest once one reaches `period.to`.

**What the worker accepts from terminal-api and the bucket.** A file or reference URL off `BACKTEST_FILE_ORIGIN` is
`DATA_INTEGRITY` and never requested; redirects are refused. Bodies are read as streams and dropped at their size: a
data file at its manifest `bytes` (`DATA_INTEGRITY`), anything else at `BACKTEST_MAX_FILE_BYTES`. A file never
inflates past `BACKTEST_MAX_FILE_BYTES` (`DATA_INTEGRITY`); the reference files, which have no manifest and are
decoded on the HTTP thread, are bounded the same way. A `TERMINAL_URL` with a user name or password is refused at
start, and the start log names its origin only.

**Presigned URLs.** How many step-1 manifests are used for their downloads depends on their lifetime minus
`BACKTEST_HTTP_TIMEOUT_MS`: a portfolio whose loading outlasts that margin asks a new `/bundle` answer for each
later ticker (job step 3). The margin also covers a request that waits for a free slot; one that waits longer can
still find its URL expired, and the one retry on 403 then loads it. A download in flight is shared only by callers of
the same file and URL; a file already verified is served from the cache by sha256 whatever its URL. Known limits:
the publisher rewrites a changed file under the same bucket key (`apps/terminal-publisher/publisher.py` `publish`,
`put_pack`), so a manifest used across a publish reads other bytes and fails the run with `DATA_INTEGRITY`; a ticker
whose new answer is a 404 or lacks a dataset fails the run with `DATA_MISSING`, in a portfolio too; `FLOW_DATA_THROUGH`
reads the step-1 manifests only; a ticker whose files are all cached is still asked again once its manifest is too
old.

## Logs

Logs go to stdout, one JSON object per line: `{ts, level, event, …}`. The compute threads pass their lines to the
main thread. The logs never contain a header, a request body, a key or a presigned URL.

| Event | Fields |
|---|---|
| `start`, `stop` | the configuration without its secrets; the signal |
| `config_invalid`, `registry_mismatch` | the variable at fault; the two registry hashes (the process then exits 1) |
| `http` | method, path, status, ms |
| `job_start`, `job_end` | state, code, ms, result bytes; the job's class (`mode`, `tickers`, `broker`: whether it reads the broker files); `job_end` also `phases_ms` (EXEC-MU-RUNTIME Phase 0: the milliseconds of each status phase the job reached, `start` to the thread's first report, then `loading`, `signals`, `backtest`, `sensitivity`, `monte_carlo`, `finalizing` until the packed result arrived; `server.ts PhaseClock`) and the process memory (`rss_bytes`, `max_rss_bytes` since start) |
| `preview_end` | one per queued signals preview (EXEC-MU-RUNTIME Phase 0): `outcome` (`ok`, `failed` with its `code`, `timeout`, `left`: the caller went away), `preview_wait_ms` (its wait in the preview queue), `compute_ms` (null when it never started), `ahead` (previews computing or queued when it arrived), `refs_ms`, `tickers`, the memory |
| `job_cancel` | |
| `terminal_bundle`, `terminal_file` | ticker, file, cache use |
| `terminal_retry` | |
| `request_failed`, `compute_failed` | name, code, message, first stack frames; only for unexpected errors |

## Build and run

The build context is the repository root:

```sh
docker build -f apps/backtest-worker/Dockerfile -t backtest-worker .
```

The image:

- uses `node:22-slim` and runs as the user `node`;
- runs `node --experimental-strip-types --import ./loader/register.mjs src/server.ts` (the loader gives the Terminal's
  sources, written for Vite, the resolution Vite gives them: a relative import without an extension is tried as `.ts`
  where Node finds nothing, `loader/resolve.mjs`, ERRORS M249);
- copies only the worker's `package.json`, `src`, `scripts` and `loader`, the shared core, `terminal/src/calc` and
  `terminal/src/data/indRegistry.json`, in the repository layout under `/app`.

To run it locally:

```sh
cd apps/backtest-worker && npm start
```

`npm start` needs the variables above.

## Tests

Run `npm test` (`node --experimental-strip-types --import ./loader/register.mjs --test tests/*.test.ts`). It needs no dependency and no network.

**`tests/run.test.ts`** runs jobs and previews through `run.ts` against `tests/fake-terminal.mjs`. The fake serves the
Terminal parity fixtures (real stored bars of 7 stocks and IHSG) in the publisher's format. The tests cover:

- the page's default request; each result must equal what the core computes directly from the same bars;
- portfolios of picked stocks, three of them, and more positions than stocks (PF5);
- determinism, with a cold and a warm cache; the same picked stocks in three orders give the same hashes, result
  bytes and preview (PF3), another set another variant on the same lineage (PF4);
- 34 refusals, none of which reads any market data, among them an index or an unpublished stock picked, a stock
  picked twice, one stock or one position more than the limits, and the former `universe` field;
- the period and data checks, `PERIOD_CLIPPED` with either benchmark;
- a portfolio that leaves out a stock without published files and a stock with too short a history (`TICKERS_EXCLUDED`)
  when its entry cannot switch on without the long condition, and runs that stock with the condition false when it
  can; `UNIVERSE_EMPTY` when every ticker is left out;
- the limits, refused before any download;
- flow and broker files: `FLOW_DATA_THROUGH` before any download, the manifest scan, `UNKNOWN_BROKER`, a listed
  broker without rows, a portfolio that leaves out a stock without a broker file, and a stock without broker rows only
  when its entry needs its flow conditions; corporate actions;
- cancellation in every phase;
- an expired presigned URL;
- previews: the run's exclusions in the run's warning, `UNIVERSE_EMPTY`, `FLOW_DATA_THROUGH`, the run's signal counts.

**`tests/validate.test.ts`** builds requests the way the page does, with every card the page can make (every legacy
card and operator, the templates, every registry indicator, every price line), and checks that the worker accepts each
of them field for field; `client_request_id` and any other extra key are refused; broker codes are checked; condition
ids, the enabled-condition limit and disabled conditions are checked; a number or price line the chosen modes do not
read is held to its type (and a cleared or out-of-range value there is accepted), and a price-action condition holds
only what its type reads. A portfolio picks 1 to `limits.max_portfolio_tickers` distinct published stocks (12
accepted, 13 refused; an index or another type is no stock, PF2), the same stocks in any order come back as one list
in ticker order (PF3), and `max_positions` goes up to `limits.max_positions`, more than the stocks picked included
(PF5).

**`tests/server.test.ts`** drives the HTTP API the way edge-bff does. It covers:

- authentication on every route; health and the catalog with each ticker's groups, the groupings and the limits;
- validation and its errors, the picked stocks in any order giving one answer; `PERIOD_AFTER_DATA` and
  `FLOW_DATA_THROUGH` from the manifests only (no `/bundle`, no file), with the job's code, field and message;
- single, portfolio and identical-request jobs through the gzip result, which must equal `runJob` in the test process;
- `BUSY`, the same id again, `UNKNOWN_JOB`, `NOT_FINISHED`; a result fetched again, then `RESULT_GONE` once a newer job
  started;
- the catalog's `flow.data_through` and a ticker name of null; the broker list reaching the validation;
- cancellation and the timeout;
- a data error after the hand-over;
- invalid job bodies, and a 4000-deep object in a field the chosen mode does not read (422 at validation and at the
  hand-over, never a 500);
- previews, including one the caller abandons; a preview or job hand-over whose caller leaves while the reference
  lists are held queues nothing and loads no data, and the next preview does not wait behind it (review V1);
- a result over `BACKTEST_MAX_RESULT_BYTES`, its sizes checked whatever the digits of the job's own duration (review
  V3);
- log lines without secrets;
- start-up as the image runs it, including exit 1 on a bad configuration.

**`tests/load.test.ts`** runs `load.ts` against the fake terminal-api, whose bucket refuses a URL after its lifetime
with S3's 403: a step-1 manifest that is still usable serves its ticker (one `/bundle` per ticker); a slow load of
many tickers succeeds without any URL reaching the bucket after its lifetime, at most two `/bundle` answers per
ticker; a publish between the two steps gives the new files' `data_version`, and a limit at the step-1 total refuses
the new files before they are downloaded; a ticker whose every file is cached is loaded from its step-1 answer however
old (one `/bundle` per ticker), and a damaged cached copy is downloaded with the step-1 URL, then from a new answer
once that URL has expired.

**`tests/terminal.test.ts`** covers the terminal-api client: the reference ticker file (every column but ticker, name
and type a grouping, in file order; null, `''` and `Undefined` unclassified), the two portfolio limits, loads, data
errors, retries, the cache, concurrency, when a `/bundle` answer is usable, a download in flight shared only by
callers of its URL, a file downloaded from two URLs at once counted once in the disk cache, one disk cache directory
shared by several clients (a file another client put is read from disk; one budget for the directory; least recently
used by any client, a memory hit included; a file another client removed is a miss and one it damaged is downloaded
again; a file used while its client evicts is kept; two clients that put at once never remove each other's file; a
stale `*.tmp` removed; a directory that cannot be created is no disk cache), the manifest and the broker date scan,
secrets kept out of messages and logs, the bucket origin, the body and inflate caps, and no Postgres client anywhere
in the worker.

## Durations observed

These were measured on the development container (Node 22.22) with the fixture bars from 2018 to 2026-10-23. They are
observations, not limits.

| Run | Total | Loading | Signals + backtest | Sensitivity (25 runs) | Monte Carlo (1000) and statistics |
|---|---|---|---|---|---|
| Single, UNVR, page defaults, cold | ≈ 265 ms | 46 ms | 23 ms | 124 ms | 71 ms |
| Single, UNVR, page defaults, warm | ≈ 190 ms | 30 ms | 7 ms | 82 ms | 73 ms |
| Portfolio, the 7 fixture stocks, warm | ≈ 155 ms | 46 ms | 14 ms | 61 ms | 34 ms |
| Portfolio, 70 tickers (copies of the fixtures, before the 12-stock limit), warm | ≈ 1.0 s | 356 ms | 125 ms | 423 ms | 71 ms |
| Portfolio, 280 tickers (copies of the fixtures, before the 12-stock limit), warm | ≈ 3.2 s | 1.25 s | 0.46 s | 1.33 s | 0.11 s |

Other observations:

- **Through the HTTP API.** A single job takes about 450 ms, including the thread start (about 100 ms the first time)
  and the status polling.
- **Result size.** A single result is about 250 KB of JSON, or 52 KB gzip. A 280-ticker result is about 0.9 MB of JSON.
- **Heap.** The 280-ticker run used up to about 380 MB of heap.

On Railway dev (2026-10-27, region `sfo`, the bucket in `sin`; the jobs through edge-bff, submit to the end of the job
including edge-bff's polling every 2 s; `verification/backtest/e2e_dev.py` and `measure_dev.py`, outputs in the
project folder `backtest/e2e-2026-10-27/`):

| Run | Worker | Submit to end | Downloaded | Result JSON (gzip) |
|---|---|---|---|---|
| Single, MAPI, page defaults with flow, cold | 1.31 s | 4.99 s | 6 files, 1.25 MB | 357 KB (95 KB) |
| Single, the same, warm | 0.45–0.58 s | 5.5–5.9 s | none | 357 KB (95 KB) |
| Portfolio, the 12 stocks with the most broker rows, flow, max 5, cold | 7.05 s | 12.42 s | 60 files, 28.35 MB in 6.1 s (4.7 MB/s) | 944 KB (274 KB) |
| Portfolio, the same, warm | 5.5 s | 10.8 s | none | 944 KB (274 KB) |
| Cancel of that portfolio while loading | ended 1.0 s after the cancel reached the worker | 4.2 s after the cancel call | | |

- **Region.** The same cold sequence with the worker in `sin` (next to the bucket): single 1.81 s (submit to end
  6.95 s), portfolio 7.34 s (16.21 s), catalog 22.3 s against 2.3 s: a file downloads faster (median 448 ms against
  2,268 ms) but the largest files take as long, and every terminal-api call crosses to `sfo` (`/bundle` median 892 ms
  against 166 ms). The worker stays in `sfo`.
- **Memory.** Railway's one-minute peak was 1.31 GB while a 12-stock preview, its run and a cancel ran within the
  minute; 0.32 GB for the cold API sequence alone. CPU peaked at 0.43 vCPU (one-minute average).
