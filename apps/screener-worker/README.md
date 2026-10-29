# screener-worker (EDGE screener)

Private HTTP service that holds the latest rack publication in memory and answers the EDGE Screener: catalog, universe,
screens, chart previews and counts. It is the service the approval-gate report designs (EXEC-SCREENER, go 2026-10-28):
`06` TARGET ARCHITECTURE (6.4-6.7 snapshot, refresh and swap; 6.10 planner; 6.16 logs; 6.17 variables), `06d`
MULTI-USER SCALE AND COST (versions, caches, gzip relay, per-owner lanes), `08` API CONTRACT (8.8 errors, 8.9 limits,
8.10 caches, 8.11 the private API) and `07` §7.1 (its files). The rules it promises edge-bff are in `CONTRACT.md`.

- **Caller.** edge-bff (`apps/edge-bff/app/screener.py`) is the only caller, on the private network. The browser never
  reaches the worker.
- **Runtime.** Node 22 with type stripping and no npm dependency, started with the backtest worker's module loader
  (`apps/backtest-worker/loader/register.mjs`, imported, never copied or changed).
- **What computes a number.** The screener core (`apps/edge-bff/screener/src/core`): the binder, the planner, the
  evaluators, the series cache and the validation. The core computes every indicator with the Terminal's `F`
  (`apps/edge-bff/terminal/src/calc/indicators.ts`) through the backtest core's `Calc`. Comparisons use the backtest
  core's `compare`. The worker adds no formula: it loads data, schedules work and caches answers.
- **Data access.** terminal-api only, with the gateway key: `GET /state` (the publication and its xsection index),
  `POST /xsection` (presigned URLs for the publication's cross-sectional files), `GET /manifest/{ticker}` (the cross-check)
  and `GET /reference/tickers` (through `TerminalClient`). It downloads only from presigned URLs on
  `SCREENER_FILE_ORIGIN`. It holds no Postgres or bucket credential and writes nothing except its own disk cache.

## Layout

| File | Role |
|---|---|
| `src/server.ts` | `node:http` API: key and owner tag, routes, version pinning, admission, the result/counts/preview caches, the refresh host (build, install, swap, grace), preset pre-warm, request logs, `main()` |
| `src/refresh.ts` | `TerminalApi` (`/state`, `/xsection`, `/manifest`) and `Refresher`: poll, skip-unchanged, caps before any grant, grant only uncached files, skew retry and deferral, origin check, manifest cross-check, backoff |
| `src/snapshot.ts` | `buildSnapshot`: the price file sliced through `priceSeries`, shared-memory bar columns, universe rows and remarks, the pinned tails of the 53 defaults (76 outputs), the core's declared derived series (`declaredDerivedSeries`) and the presets' series, `snapshot_digest`; `ThreadSnapshot` (one thread's view) |
| `src/pool.ts` | the compute threads (`worker_threads`), the builder thread, owner lanes (deficit round robin), the queue, the per-owner budget (P33), deadlines, cancellation and kill |
| `src/thread.ts` | the code each thread runs: install or drop a snapshot, build, pre-warm, digest, run, counts, preview |
| `src/run.ts` | request envelopes and normalization, the cost estimate and its tracker, `runTask` (core `runScreen`), gzip and `ETag`, the result cache key |
| `src/preview.ts` | one ticker's preview: the core's `previewCells`, overlays, event markers, performance against IHSG |
| `src/catalog.ts` | `/v1/catalog` and `/v1/universe` documents (gzip bytes and `ETag`), the limits as `{name, value, unit, rule, example_ok, example_refused}` |
| `src/config.ts` | environment variables (no defaults for limits) and their checks |
| `src/version.ts` | `screener_engine` (sha256 over the files that compute an answer) and the start-up registry check |
| `src/errors.ts`, `src/log.ts` | the error shape and statuses; JSON log lines |
| `tests/` | `node:test` suites with a fake terminal-api (`fake-terminal.mjs`, built on the backtest worker's fake) |

## API

Summary; `CONTRACT.md` holds the rules. The header `x-screener-worker-key: $SCREENER_WORKER_KEY` is required on every
route except `/health` and `/ready` (else `401 UNAUTHORIZED`). `x-screener-owner` (16 hex, HMAC of the owner key that
edge-bff computes) selects the owner's lane and budget.

| Route | Answer |
|---|---|
| `GET /health` | `{ok, versions, published_at, snapshot_age_seconds, refresh}`; `refresh` is `loading`, `refreshing`, `ready` or `failed_keeping_previous` |
| `GET /ready` | `200 {ready: true}` with a snapshot, else `503 SCREENER_NOT_READY` with `Retry-After` (the Railway healthcheck) |
| `GET /v1/catalog` | indicators, metrics and fundamentals with their availability at this publication, periods, groupings, presets with their availability, the limits, `versions` and `data`; `ETag`, `304` on `If-None-Match` |
| `GET /v1/universe` | every listed stock with last, change, ADV20, groups and remarks (stale, price break with its ex-date); `ETag` |
| `POST /v1/run` | `RunResponse`: rows (match, near), per-condition counts and source (`precomputed` or `dynamic`), `plan` when asked; gzip, `ETag` |
| `POST /v1/preview` | one ticker's bars, overlays and markers at a pinned `data_version`; gzip |
| `POST /v1/counts` | match and near counts for up to `SCREENER_MAX_COUNTS` definitions; gzip |
| `POST /v1/validate` | `{valid, definition_hash, normalized, versions}` or the first refusal |

Every computed answer opens with `versions` and `data`, so edge-bff reads `price_data` and `published_at` from the first
bytes of a gzip answer and relays the rest unparsed.

## Refresh, snapshot and swap

1. **Poll.** `GET /state` every 60 s. The refresh starts only when `finished_at` changes, and one refresh runs at a time.
2. **Caps before any grant.** The index must name `price` and `actions`. A file above `SCREENER_MAX_FILE_BYTES`, or a
   download total above `SCREENER_MAX_REFRESH_BYTES`, fails the refresh before `/xsection` is called.
3. **Skip unchanged.** The same sha256 for both files and the same reference contents: nothing is downloaded, recomputed
   or swapped. Only `published_at` advances (log `refresh_skipped`); the snapshot's cached answers are dropped, so
   no answer names the older publication, and the presets are computed again in the system lane.
4. **Grant only what is missing.** `POST /xsection` names only the files that neither cache holds. The answer must name
   the publication `/state` named (`finished_at`, and each file's sha256 and size). A skewed answer (terminal-api's two
   processes may lag each other by up to a minute) is asked again `SCREENER_DOWNLOAD_RETRIES` times, then the refresh
   is deferred by 15 s (log `refresh_deferred`, not a failure). Every URL must be on `SCREENER_FILE_ORIGIN`.
5. **Build.** The builder thread downloads, then `TerminalClient.file` and `inflateVerified` check the sha256 and size
   and inflate under `SCREENER_MAX_INFLATED_BYTES`. The builder then decodes: each ticker's slice goes through the
   backtest core's `priceSeries`, every ticker must be in the reference file, and IHSG must be present. Each ticker is
   then checked against its `/manifest`: the rows must equal the sum of its yearly files and the last date their newest.
   The 53 defaults (76 outputs), the declared derived series of the default cards (bar fields, the Donchian prior
   bands, the rising lags and vs-MA averages) and the presets' series are pre-warmed into shared tails of
   `SCREENER_WITHIN_MAX` + 1 bars, on the builder thread and, at a cold start, on the compute threads too. Then
   `snapshot_digest` is computed.
6. **Swap all-or-nothing.** Every compute thread installs the new snapshot. Only when all have installed it does the
   snapshot become current. Then the presets run in a system lane and their answers are kept pinned in the result cache.
   The previous snapshot keeps serving requests pinned to it for `SCREENER_PREVIOUS_GRACE_S`, then is dropped with its
   caches.
7. **Failure.** Any integrity failure keeps the previous snapshot, logs `REFRESH_FAILED` with its code, and retries the
   same publication after a backoff of 60 s doubling to 16 min. A newer publication is tried at once.

Memory: the bars of every ticker are stored once per replica in `SharedArrayBuffer` columns (O, H, L, C, V as
`Float64Array`, a null volume as NaN, T as an index into one date table). F never runs on a typed view: a ticker's bars
are materialized back into plain arrays equal to `priceSeries`' output (`tests/typed_views.test.ts`). The pinned tails
sit in one shared `Float64Array` and are installed in each thread's `SeriesCache` as pinned entries.

A request reads a ticker through the thread's `TickerView` (`snapshot.ts`): the dates are the thread's own copy, kept
for the snapshot's life (about 10.6 MB per thread); a price column is made on its first read and the backtest core's
`Calc` on the first computation; `missingInput` is answered from the snapshot's per-ticker mask. A screen of
pre-warmed series therefore reads no bar column (`tests/views.test.ts`). The planner holds every survivor's view to the
end of a screen, so a request releases the `Calc` (and its memo of full outputs) of a ticker that falls out of its
LRU of `CALC_KEEP` (256) tickers; without that, five custom conditions kept about 0.2 GB of outputs per request and a
ten-condition ANY screen ran out of a 600 MB heap. `return_rank` (stage S1) is computed once per thread and snapshot
(at most 16 windows). Each thread runs under `SCREENER_THREAD_HEAP_MB` (V8 old generation): without it V8 let each
thread's heap grow towards its default limit (about 2 GB per thread on a 16 GB host) with the garbage of the screens.
Measured local figures: `verification/screener/BENCHMARK_LOCAL.md`.

## Admission and fairness (06d.6, P33)

In order: result-cache hit (answered at once, outside every queue and budget) → per-request cost budget
(`SCREENER_MAX_CPU_MS`, `422 LIMIT_EXCEEDED compute_budget` with the costliest series) → per-owner budget per minute
(`SCREENER_OWNER_CPU_MS`, `422 LIMIT_EXCEEDED owner_cpu_budget` with `retry_after_seconds`) → replica queue
(`SCREENER_QUEUE`, `409 BUSY`) → the owner's lane (`SCREENER_OWNER_INFLIGHT` running; deficit round robin across lanes,
weighted by predicted cost, quantum `SCREENER_MAX_CPU_MS / 4`). A newer request of the same page replaces a waiting
older one (`409 SCREEN_REPLACED` / `PREVIEW_REPLACED`). The deadline is `SCREENER_DEADLINE_MS` from arrival (`504
TIMEOUT`). A running request past its deadline, or one whose caller left, is asked to stop through a shared flag. A
thread that does not stop within 1 s is terminated and restarted with its snapshots installed again.

The cost model is the core's (`plan.ts` `costEstimate`) over the worker's per-series unit costs: indicator cost class
and largest length, or a transform's or pattern's largest numeric argument. Its milliseconds per unit are learned per
replica from measured runs (exponential average, alpha 0.2). Pre-warmed series cost nothing.

## Versions and caches

- `screener_engine`: sha256 over the screener core, the worker's `src`, the backtest core, the Terminal's calculation
  module, `apps/backtest-worker/src/terminal.ts` and the Node major version. A change to any of them changes the version.
- Start-up check: the indicator registry generator reproduces `REGISTRY_VERSION`, the screener registry has no
  problem, and its sources' sha256 match. Otherwise the process exits with `startup_check_failed`.
- Result cache (gzip bytes): keyed by the snapshot identity (price data plus the actions and reference contents),
  `screener_engine`, `registry`, `screener_registry`, `definition_hash`, `exhaustive` and `explain`. Nothing
  user-specific goes into the key or the answer. Previews share the result cache; counts have their own (`CountsCache`,
  at most 50,000 entries, about 18 MB, least recently used out, the presets' counts pinned). Every cache is per replica
  and dropped with its snapshot.
- `SCREENER_CACHE_BYTES` is split into K + 1 equal shares: one series LRU per compute thread and one for the result
  cache. The pinned snapshot is not counted.

## Configuration

Every limit has no default: the process logs `config_invalid` naming the variable (never its value) and exits.
Initial values are the report's provisional ones (8.9, P5), to be replaced by the Phase 17 measurements.

| Variable | Meaning | Initial value |
|---|---|---|
| `PORT` | HTTP port | `8080` (the only default) |
| `SCREENER_WORKER_KEY` | shared secret with edge-bff, at least 32 characters | secret, shared with edge-bff |
| `TERMINAL_URL` | terminal-api origin (private network), no path or credentials | `http://terminal-api.railway.internal:<port>` |
| `TERMINAL_PROXY_KEY` | terminal-api gateway key, at least 32 characters | `${{terminal-api.TERMINAL_PROXY_KEY}}` |
| `SCREENER_FILE_ORIGIN` | the bucket origin every presigned URL must have | as `BACKTEST_FILE_ORIGIN` |
| `SCREENER_THREADS` | K compute threads (plus one builder thread during a refresh) | from the replica's vCPU |
| `SCREENER_THREAD_HEAP_MB` | each compute and builder thread's V8 old-generation limit (MB, at least 64); a thread that needs more stops alone (`500 OUT_OF_MEMORY`, restarted) | 512 (BENCHMARK_LOCAL.md) |
| `SCREENER_CACHE_BYTES` | series LRUs plus result cache, split K + 1 | Phase 17; local proposal 268435456 (BENCHMARK_LOCAL.md §8) |
| `SCREENER_CACHE_DIR`, `SCREENER_CACHE_DIR_BYTES` | optional file cache by sha256 on the container's disk (no volume) and its budget | e.g. `/tmp/screener-cache` |
| `SCREENER_DOWNLOAD_CONCURRENCY`, `SCREENER_DOWNLOAD_RETRIES`, `SCREENER_RETRY_BASE_MS`, `SCREENER_HTTP_TIMEOUT_MS` | download settings (`TerminalOptions` requires them); the retries also bound the skew retries | as backtest-worker |
| `SCREENER_MAX_CPU_MS` | per-request compute budget | Phase 17; local proposal 4500 (the cost model under-predicts up to 4.4 x, §7) |
| `SCREENER_CAP_BUDGET_MS` | the length caps (`registry.ts capOf`); a value whose caps refuse a registry default is refused at start | Phase 17; local proposal = `SCREENER_MAX_CPU_MS` (4500, caps 567) |
| `SCREENER_DEADLINE_MS` | request deadline, queue included; edge-bff's `SCREENER_TIMEOUT_SECONDS` = this / 1000 | 20000 |
| `SCREENER_MAX_CONDITIONS` | enabled conditions per definition | 20 |
| `SCREENER_MAX_METRIC_FILTERS` | universe metric filters | 8 |
| `SCREENER_WITHIN_MAX` | longest `within`; tails are this + 1 bars | 130 |
| `SCREENER_MAX_COUNTS` | definitions per counts request | 50 |
| `SCREENER_MAX_RESPONSE_BYTES` | JSON bytes of one answer | 2097152; local proposal 4194304 (an answer inside the limits reaches about 2.8 MB) |
| `SCREENER_QUEUE` | waiting requests per replica | 4 |
| `SCREENER_OWNER_INFLIGHT` | running requests per owner tag | 2; local proposal K - 1 (at K = 2 one owner otherwise holds every thread: light owners' p95 x 32-41, with 1: x 1.6) |
| `SCREENER_OWNER_CPU_MS` | P33: thread ms per owner tag per minute; at least `SCREENER_MAX_CPU_MS` | Phase 17; local proposal 30000 |
| `SCREENER_PREVIOUS_GRACE_S` | seconds the previous snapshot serves pinned requests | 600 |
| `SCREENER_MAX_FILE_BYTES` | gzip bytes per xsection file | 2 × measured: 24000000 (price file 11,758,823 B) |
| `SCREENER_MAX_INFLATED_BYTES` | inflated bytes per file (`TerminalClient` `maxFileBytes`) | 2 × measured: 150000000 (price document 74,272,854 B) |
| `SCREENER_MAX_REFRESH_BYTES` | gzip bytes per refresh | 2 × measured: 24000000 (a cold refresh 11,772,808 B) |
| `SCREENER_MAX_REQUEST_BYTES` | bytes of one request body (`413 REQUEST_TOO_LARGE`) | 131072 (edge-bff's own limit) |

Added to the report's 6.17 list, each because a component needs a value and limits have no default: the four
download settings and the disk budget, `SCREENER_OWNER_CPU_MS` (P33), `SCREENER_MAX_REQUEST_BYTES` and
`SCREENER_THREAD_HEAP_MB` (the per-thread heap limit, performance review 2026-10-29).

## Logs

One JSON object per line on stdout (`{ts, level, event, ...}`), from the HTTP thread and the compute threads. No key,
header, body or presigned URL is ever logged.

| Event | When |
|---|---|
| `start`, `stop`, `config_invalid`, `startup_check_failed` | process life; `start` carries the configuration without secrets and the versions |
| `refresh`, `refresh_skipped`, `refresh_deferred`, `refresh_skew`, `refresh_state_unavailable`, `REFRESH_FAILED`, `swap` | a publication: per-phase ms (state, grant, download, decode, manifest check, pre-warm per thread, install, presets), bytes, `snapshot_digest`, RSS; the failure code and the backoff |
| `run`, `preview`, `counts` | one line per request that explains its cost: owner tag, `definition_hash`, `data_version`, cache hit, predicted ms, stages (tickers in and out, ms), conditions (source, evaluated, pruned), pinned and LRU hits, series computed, queue, busy and total ms, payload bytes, status |
| `http` | one line per request (method, path, status, ms) except `/health` and `/ready` |
| `thread_killed`, `thread_error`, `task_failed`, `install_failed`, `request_failed`, `preset_failed`, `terminal_retry` | faults, with the error's name, code, message and (unexpected errors) the first stack frames |

## Build and run

```
# from apps/screener-worker
npm start      # node --experimental-strip-types --import ../backtest-worker/loader/register.mjs src/server.ts
npm test       # node:test, every suite, one file at a time

# image (repository root as context; copies only the 07 §7.1 files)
docker build -f apps/screener-worker/Dockerfile -t screener-worker .
```

The image keeps the repository layout under `/app`, because the worker imports the cores by relative path and
`screener_engine` hashes them by that path. It runs as the image's `node` user.

## Tests

`npm test` runs every suite with a fake terminal-api (`tests/fake-terminal.mjs`: `/state`, `/xsection` with the proxy key and
skew, `/manifest`, `/reference/tickers`, presigned bucket URLs, faults per file). Last run: 57 of 57 pass.

| Suite | What it locks |
|---|---|
| `config.test.ts` | every limit required with no default; errors name the variable, not the value; cap and owner-budget checks; `screener_engine` is a content hash; the start-up check |
| `refresh.test.ts` | a publication loads end to end; integrity failures (sha256, manifest cross-check, reference) answer `424` with no snapshot and keep the previous one when held; file, refresh and inflate caps before any grant; a warm disk cache grants nothing; skew retry then deferral; skip unchanged; one refresh at a time; pinning across a swap (grace, `DATA_VERSION_CHANGED`, `DATA_VERSION_PENDING`) |
| `snapshot.test.ts`, `typed_views.test.ts` | slices equal `priceSeries`; groupings parity with the Backtest; remarks; pinned tails equal F; digest stable across builds; materialized bars equal F bit for bit |
| `views.test.ts` | a request's `TickerView`: `missingInput` from the snapshot's mask equals the scan; a screen of pre-warmed series reads no column and answers as plain arrays do; views out of `CALC_KEEP` release their `Calc` with the same answer; `return_rank` once per thread, same ranks |
| `counts_cache.test.ts`, `heap.test.ts` | the counts cache's bound, order, pinned presets and snapshot drop; `SCREENER_THREAD_HEAP_MB` required, applied to compute and builder threads, an out-of-memory thread stops alone and is started again |
| `run.test.ts` | VALUE, STATE, EVENT, ALL / ANY / AT LEAST with the near rule, precomputed vs dynamic, pruning never changes the answer: all against F and the backtest core's `compare` directly |
| `pool.test.ts` | owner inflight, round robin and cost-weighted deficit round robin, queue `BUSY`, same-page replacement, deadline, kill and respawn with reinstall, a caller that leaves, the owner budget (P33) |
| `server.test.ts` | the key; protocol errors (404, 405, 413, 422); the envelope; catalog limits and `ETag` / `304`; the result cache shared byte for byte across owners; universe-only screens; P4 hidden tickers and remarks; compute and owner budgets (a cache hit is never refused); response and counts caps; counts with per-entry errors; preview; request logs without secrets |

## Durations observed (local, not the service)

Local runs of the performance review (2026-10-29), Node 22.22 in the build sandbox (4 vCPU, shared with other
builds), the real full history (845 tickers, 1.33 M bars) through the real publisher and terminal-api app, K = 2,
`SCREENER_THREAD_HEAP_MB` 512. Local figures, not the Railway service's: `verification/screener/BENCHMARK_LOCAL.md` has
the method, every scenario, K = 1 and K = 4, and the proposed limits. Phase 17 measures the service.

| Step | Local |
|---|---|
| First snapshot ready (cold, no file cache) | 16 s: download 1.6 s, decode 2.6 s, manifest check 1.8 s, defaults 8.7 s on builder plus 2 threads, install 0.06 s, presets 0.17 s; peak RSS 0.89 GB |
| Refresh while serving (builder alone) | 34 s (pre-warm 26 s; 47-58 s under load); peak RSS 1.46 GB with both snapshots |
| Pinned series | 113 (76 default outputs, the declared derived series and the presets' series) |
| RSS | 0.57 GB idle after start; 1.81 GB with both caches full (512 MiB) and the previous snapshot in its grace |
| Default-parameter screen, whole market | p50 11 ms (1 condition) to 42 ms (10 conditions); about 2 ms from the result cache |
| Custom-parameter RSI screen | p50 0.30 s cold, 11 ms with the series in the thread's LRU |
| Counts of 50 saved default screens | 0.8-0.9 s |
| Catalog / universe | 177 KB / 225 KB JSON (22.5 KB / 35.8 KB gzip) |

## Open items

- `UNAUTHORIZED`, `NOT_FOUND`, `METHOD_NOT_ALLOWED`, `INTERNAL_ERROR` and `OUT_OF_MEMORY` are worker-only codes:
  edge-bff relays only the contract's refusals at their status (`app/screener.py` `RELAYED`), so these reach the page
  as `503 SCREENER_UNAVAILABLE`. `owner_cpu_budget` is a contract `LimitName` (integration, 2026-10-28).
- Railway: the service, its variables and its watch patterns (`/apps/screener-worker/**`, the cores and the
  registry generators) are not created yet. That is the deploy step, not this build.
- A counts request is one job on one thread: 50 saved screens with distinct custom series took 15-18 s locally (deadline 20 s), and a timeout loses every entry computed before it (`BENCHMARK_LOCAL.md`).
- One ticker whose every row is dropped by `priceSeries` (`DATA_MISSING`) fails the whole refresh by design (keeps the
  previous snapshot). Review whether the publisher can ever produce that.
