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
| `src/validate.ts` | request checks before any download (unknown fields, page options, universes, flow availability, broker codes against the broker list, the core's own validation) |
| `src/load.ts` | reads the files of a run within the limits: every manifest first, a portfolio's tickers without published files left out, the limits checked, then the downloads; a URL that expired is fetched again; the date the broker data is published through (`brokerDataThrough`) |
| `src/terminal.ts` | the terminal-api client: `/bundle`, `/manifest`, the reference files, presigned files, sha256 and size checks, the cache (memory, optionally disk) |
| `src/catalog.ts` | `GET /v1/catalog` from the reference files, IHSG's published bars, the limits, the flow switch and the broker data's date |
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
| `GET /v1/catalog` | `Catalog` (contract.ts) |
| `POST /v1/validate {request}` | `200 {ok: true, lineage_key, variant_hash, tickers}`, or `422` with the error: the request checks (`validate.ts`), then `FLOW_DATA_THROUGH` and `PERIOD_AFTER_DATA` with the code, field and message the job would fail with, read from terminal-api's manifests only (no `/bundle`, no file) |
| `POST /v1/signals` | the body is a `SignalsPreviewRequest`; the answer is a `SignalsPreview` |
| `POST /v1/jobs {job_id, request, context}` | `202 {job_id}`, `409 BUSY` or `422` |
| `GET /v1/jobs/{id}` | `JobStatus`, or `404 UNKNOWN_JOB` |
| `GET /v1/jobs/{id}/result` | `200` with the gzip of the result JSON (`Content-Encoding: gzip`), as often as it is asked until the next job starts; `409 NOT_FINISHED`; `410 RESULT_GONE` for the finished job a newer job replaced; `404 UNKNOWN_JOB` for any other id |
| `POST /v1/jobs/{id}/cancel` | `202 JobStatus`; a running job stops at its next check and ends `CANCELLED` |

### Signals previews

- Previews run on the preview thread while the caller waits.
- One preview computes at a time; the others wait in arrival order.
- When the caller disconnects, its preview is cancelled.
- A preview leaves out the tickers the run leaves out, with the run's shared code (`signals.ts`): a ticker without
  published files, or whose own data cannot serve the entry rule. They are listed in `warnings` as the result's
  `TICKERS_EXCLUDED` (`count`, `tickers`, `reasons`). When none is left the preview is refused with `UNIVERSE_EMPTY`, as
  the run is, and a preview that reads broker files is held to `FLOW_DATA_THROUGH`. A preview never fails where the
  matching run succeeds (lead decision 2026-10-26).

### Jobs

- **One job at a time.** While a job runs, a job with another id gets `409 BUSY`. A POST with the current job's id
  answers `202` again, because edge-bff retries a POST whose answer it lost.
- **Checked before it is accepted.** The request is checked before the `202`. A refused request is a `422` and never
  becomes a job.
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
`504 TIMEOUT`, and a preview over its time has its thread terminated.

### Errors

Errors have the shape `{"error": {code, field?, message?, details?}}`.

| Status | Codes |
|---|---|
| 422 | validation errors (among them `UNKNOWN_FIELD`, `INVALID_CONDITION`, `UNKNOWN_BROKER`, `FLOW_UNAVAILABLE`, `FLOW_OUTPUT_EMPTY`, `INDICATOR_OUTPUT_EMPTY`, `PERIOD_AFTER_DATA`, `PERIOD_BEFORE_DATA`, `FLOW_DATA_THROUGH`, `UNIVERSE_EMPTY`), `LIMIT_EXCEEDED` (`details.limit`: `max_download_bytes`, `max_broker_rows`, `max_conditions`, `max_result_bytes`), `INVALID_JSON`, `INVALID_JOB_ID`, `INVALID_CONTEXT` |
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
2. **Resolve the tickers.**
   - Single mode: the one ticker, which must be of type `stock`.
   - Portfolio mode: universe `all` is every stock of terminal-api's reference ticker list; `sector:<name>` is the
     stocks of that sector. The publisher writes that list from `IDX_Stock_Universe`, the same list it publishes the
     tickers' files from.
3. **Load the data** (`load.ts`).
   - IHSG prices, and each ticker's prices and corporate actions.
   - Broker files only when a flow condition or `rank_by: 'fnet'` needs them.
   - Every manifest is read first. A portfolio leaves out a stock terminal-api does not publish (404) or that has no
     file of a dataset the run reads (`DATA_MISSING`, listed in the warning `TICKERS_EXCLUDED`); in single mode that is
     the run's `DATA_MISSING`. The run is refused with `LIMIT_EXCEEDED`, before any download, when the manifest sizes
     exceed `BACKTEST_MAX_DOWNLOAD_BYTES` or the broker rows exceed `BACKTEST_MAX_BROKER_ROWS`. Cached files count
     too, so the same request gets the same answer whatever the cache holds.
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
   serve the strategy: an indicator or flow series without any value on its bars (`INDICATOR_OUTPUT_EMPTY`,
   `FLOW_OUTPUT_EMPTY`) or no broker row on its bars (`FLOW_UNAVAILABLE`). The warning `TICKERS_EXCLUDED` lists every
   left-out ticker with its error (`count`, `tickers`, `reasons`); `meta.tickers` holds the tickers the run ran on. A
   request error still fails the run, and in single mode these data errors do too. A broker without any row on a
   ticker's bars has a net of 0 there. When every ticker of the universe is left out the run is refused with
   `UNIVERSE_EMPTY` (field `portfolio.universe`; the message gives the count and the reasons by code), never a
   cash-only result (lead decision 2026-10-26).
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
| `TERMINAL_URL` | required | terminal-api's private origin, e.g. `http://terminal-api.railway.internal:8080` | terminal-api origin |
| `TERMINAL_PROXY_KEY` | required | `${{terminal-api.TERMINAL_PROXY_KEY}}` | terminal-api gateway key (D-U1), ≥ 32 characters, never logged |
| `BACKTEST_CACHE_BYTES` | required | 1500000000 | memory cache budget per thread (gzip bytes); 0 = none |
| `BACKTEST_CACHE_DIR`, `BACKTEST_CACHE_DIR_BYTES` | off | not set | optional disk cache and its budget; the directory must be writable by uid 1000 |
| `BACKTEST_DOWNLOAD_CONCURRENCY` | required | 16 | HTTP requests in flight per thread |
| `BACKTEST_DOWNLOAD_RETRIES` | required | 3 | retries of a network error or 5xx answer |
| `BACKTEST_RETRY_BASE_MS` | required | 500 | backoff `base × 2^k` between retries |
| `BACKTEST_HTTP_TIMEOUT_MS` | required | 60000 | per HTTP request |
| `BACKTEST_FILE_ORIGIN` | required | `https://*.t3.storageapi.dev` (the host edge-bff's CSP allows for the same presigned downloads, `app/main.py`) | the origin every file and reference URL must have: scheme, host (a leading `*.` matches subdomains) and port; any other URL is `DATA_INTEGRITY` and never requested |
| `BACKTEST_MAX_FILE_BYTES` | required | 67108864 (the largest published file measured 2026-10-26 is BBRI's broker-archive pack: 2,218,292 bytes gzip, 14,456,717 inflated; the archive grows about 1.8 MB per year) | the most bytes one file may inflate to, and the most bytes of a body that is not a data file (a reference file, a terminal-api answer); over it `DATA_INTEGRITY` |
| `BACKTEST_MAX_DOWNLOAD_BYTES` | required | 1500000000 | bytes of published files one job or preview may read |
| `BACKTEST_MAX_BROKER_ROWS` | required | 20000000 | broker rows one job or preview may read |
| `BACKTEST_TIMEOUT_SECONDS` | required | 900 | longest job, preview, validation or catalog |
| `BACKTEST_MAX_CONDITIONS` | required | 32 | enabled conditions one list (entry, exit signals) may have; reported as `catalog.limits.max_conditions`; more is `LIMIT_EXCEEDED` (`details.limit: max_conditions`) |
| `BACKTEST_MAX_RESULT_BYTES` | required | set from the dev E2E measurement; edge-bff takes the same value by the Railway reference `${{backtest-worker.BACKTEST_MAX_RESULT_BYTES}}` | the most JSON a job's result may have; over it the job ends `FAILED LIMIT_EXCEEDED` (`details.limit: max_result_bytes`) before the result is packed. Not in the catalog: the page cannot act on it |
| `BACKTEST_MAX_POSITIONS` | 10 | 10 (default) | ≤ 10, the page's input and `engine.ts` MAX_POSITIONS; may only be lowered |
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

**Memory.** Each compute thread has its own client and cache. Memory is therefore up to 2 × `BACKTEST_CACHE_BYTES`,
plus the HTTP thread's IHSG files for the catalog.

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

## Logs

Logs go to stdout, one JSON object per line: `{ts, level, event, …}`. The compute threads pass their lines to the
main thread. The logs never contain a header, a request body, a key or a presigned URL.

| Event | Fields |
|---|---|
| `start`, `stop` | the configuration without its secrets; the signal |
| `config_invalid`, `registry_mismatch` | the variable at fault; the two registry hashes (the process then exits 1) |
| `http` | method, path, status, ms |
| `job_start`, `job_end` | state, code, ms, result bytes |
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
- runs `node --experimental-strip-types src/server.ts`;
- copies only the worker's `package.json`, `src` and `scripts`, the shared core, `terminal/src/calc` and
  `terminal/src/data/indRegistry.json`, in the repository layout under `/app`.

To run it locally:

```sh
cd apps/backtest-worker && npm start
```

`npm start` needs the variables above.

## Tests

Run `npm test` (`node --experimental-strip-types --test tests/*.test.ts`). It needs no dependency and no network.

**`tests/run.test.ts`** runs jobs and previews through `run.ts` against `tests/fake-terminal.mjs`. The fake serves the
Terminal parity fixtures (real stored bars of 7 stocks and IHSG) in the publisher's format. The tests cover:

- the page's default request; each result must equal what the core computes directly from the same bars;
- portfolio and sector universes;
- determinism, with a cold and a warm cache;
- 29 refusals, none of which reads any market data;
- the period and data checks, `PERIOD_CLIPPED` with either benchmark;
- a portfolio that leaves out a stock without published files and a stock with too short a history (`TICKERS_EXCLUDED`),
  and `UNIVERSE_EMPTY` when every ticker is left out;
- the limits, refused before any download;
- flow and broker files: `FLOW_DATA_THROUGH` before any download, the manifest scan, `UNKNOWN_BROKER`, a listed
  broker without rows, a portfolio that leaves out stocks without broker data; corporate actions;
- cancellation in every phase;
- an expired presigned URL;
- previews: the run's exclusions in the run's warning, `UNIVERSE_EMPTY`, `FLOW_DATA_THROUGH`, the run's signal counts.

**`tests/validate.test.ts`** builds requests the way the page does, with every card the page can make (every legacy
card and operator, the templates, every registry indicator, every price line), and checks that the worker accepts each
of them field for field; `client_request_id` and any other extra key are refused; broker codes are checked; condition
ids, the enabled-condition limit and disabled conditions are checked.

**`tests/server.test.ts`** drives the HTTP API the way edge-bff does. It covers:

- authentication on every route; health and the catalog;
- validation and its errors; `PERIOD_AFTER_DATA` and `FLOW_DATA_THROUGH` from the manifests only (no `/bundle`, no
  file), with the job's code, field and message;
- single, portfolio and identical-request jobs through the gzip result, which must equal `runJob` in the test process;
- `BUSY`, the same id again, `UNKNOWN_JOB`, `NOT_FINISHED`; a result fetched again, then `RESULT_GONE` once a newer job
  started;
- the catalog's `flow.data_through` and a ticker name of null; the broker list reaching the validation;
- cancellation and the timeout;
- a data error after the hand-over;
- invalid job bodies;
- previews, including one the caller abandons;
- log lines without secrets;
- start-up as the image runs it, including exit 1 on a bad configuration.

**`tests/terminal.test.ts`** covers the terminal-api client: loads, data errors, retries, the cache, concurrency, the
manifest and the broker date scan, secrets kept out of messages and logs, the bucket origin, the body and inflate caps,
and no Postgres client anywhere in the worker.

## Durations observed

These were measured on the development container (Node 22.22) with the fixture bars from 2018 to 2026-10-23. They are
observations, not limits.

| Run | Total | Loading | Signals + backtest | Sensitivity (25 runs) | Monte Carlo (1000) and statistics |
|---|---|---|---|---|---|
| Single, UNVR, page defaults, cold | ≈ 265 ms | 46 ms | 23 ms | 124 ms | 71 ms |
| Single, UNVR, page defaults, warm | ≈ 190 ms | 30 ms | 7 ms | 82 ms | 73 ms |
| Portfolio `all`, 7 tickers, warm | ≈ 155 ms | 46 ms | 14 ms | 61 ms | 34 ms |
| Portfolio, 70 tickers (copies of the fixtures), warm | ≈ 1.0 s | 356 ms | 125 ms | 423 ms | 71 ms |
| Portfolio, 280 tickers (copies of the fixtures), warm | ≈ 3.2 s | 1.25 s | 0.46 s | 1.33 s | 0.11 s |

Other observations:

- **Through the HTTP API.** A single job takes about 450 ms, including the thread start (about 100 ms the first time)
  and the status polling.
- **Result size.** A single result is about 250 KB of JSON, or 52 KB gzip. A 280-ticker result is about 0.9 MB of JSON.
- **Heap.** The 280-ticker run used up to about 380 MB of heap.
