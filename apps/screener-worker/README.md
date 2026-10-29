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
`src/config.ts` (`loadConfig`) is the source of this table: it reads exactly these 30 names, and every one is required
except `PORT` (default 8080) and `SCREENER_CACHE_DIR` (optional; with it `SCREENER_CACHE_DIR_BYTES` is required). The
proposed dev values are **LOCAL and provisional**: measured in the build sandbox, not on Railway
(`verification/screener/BENCHMARK_LOCAL.md` section 8, 2026-10-29), unless the row names another source. The Phase 17
benchmark on the dev service (report 11b; DEPLOY_RUNBOOK step 11) replaces every one of them. The whole set passes
`loadConfig` (checked 2026-10-29 with test keys: 28 of the 29 set names are required, the cap at 4500 ms is 567).

| Variable | Read and checked (`src/config.ts`) | Meaning | Proposed dev value (LOCAL, provisional) |
|---|---|---|---|
| `PORT` | :84-85, 1-65535, default 8080 (`DEFAULT_PORT`, :53) | HTTP port | not set: 8080, the port the private URL names |
| `SCREENER_WORKER_KEY` | :86-87, at least 32 characters (contract.ts `WORKER_KEY_MIN_LENGTH`) | shared secret with edge-bff (`x-screener-worker-key`) | secret: 64 hex generated on Railway, never printed; edge-bff reads it by reference |
| `TERMINAL_URL` | :88-92, an http(s) origin, no path, user name or password | terminal-api origin on the private network | `http://terminal-api.railway.internal:8080` |
| `TERMINAL_PROXY_KEY` | :93-94, at least 32 characters | the key the worker sends terminal-api as `x-terminal-proxy-key` (`/state`, `/xsection`, `/manifest`, `/reference`) | a reference, never a value: `${{terminal-api.TERMINAL_SERVICE_KEY_SCREENER_WORKER}}`, the worker's own service account (EXEC-MU-RUNTIME T1; `/xsection` admits it, terminal-api `main.py` `xsection_caller`), once terminal-api holds it; until then the gateway key `${{terminal-api.TERMINAL_PROXY_KEY}}` (TEMPORARY) |
| `SCREENER_FILE_ORIGIN` | :95-96, `scheme://host[:port]` (terminal.ts `fileOriginOf`) | the bucket origin every presigned URL must have | the value of backtest-worker's `BACKTEST_FILE_ORIGIN`, copied without printing it |
| `SCREENER_THREADS` | :126, at least 1 | K compute threads (plus one builder thread during a refresh) | 2 (K = 2 on a 4-vCPU replica; K = 4 failed the 1.5 x rule; re-measure on the service's vCPU) |
| `SCREENER_THREAD_HEAP_MB` | :126, at least 64 | each compute and builder thread's V8 old-generation limit (MB); a thread that needs more stops alone (`500 OUT_OF_MEMORY`, restarted) | 512 (every thread stayed at or under 354 MB with a 384 MB limit) |
| `SCREENER_CACHE_BYTES` | :126, at least 0 | series LRUs plus result cache, split K + 1 (`cacheShare`, :130) | 268435456 (256 MiB: 89,478,485 B per share at K = 2) |
| `SCREENER_CACHE_DIR` | :97, optional | file cache by sha256 on the container's disk (no volume); must be writable by uid 1000 (image `USER node`) | `/tmp/screener-cache` |
| `SCREENER_CACHE_DIR_BYTES` | :121, at least 1, required only with `SCREENER_CACHE_DIR` | the disk cache's budget | 48000000 (not measured: 2 x `SCREENER_MAX_REFRESH_BYTES`, the files of two publications at their caps; a cold refresh downloaded 11,772,808 B) |
| `SCREENER_DOWNLOAD_CONCURRENCY` | :122, at least 1 | HTTP requests in flight to terminal-api and the bucket (the 845 `/manifest` reads) | 16 (backtest-worker README's value; the local benchmark ran 8) |
| `SCREENER_DOWNLOAD_RETRIES` | :122, at least 0 | retries of a network error or a 5xx; also the quick retries of a skewed `/xsection` | 3 (backtest-worker's; the benchmark ran 2) |
| `SCREENER_RETRY_BASE_MS` | :123, at least 0 | backoff base: retry k waits base x 2^k | 500 (backtest-worker's; the benchmark ran 200) |
| `SCREENER_HTTP_TIMEOUT_MS` | :123, at least 1 | longest one HTTP request may take, body included | 60000 (backtest-worker's and the benchmark's) |
| `SCREENER_MAX_CPU_MS` | :99, at least 1 | per-request compute budget (`422 LIMIT_EXCEEDED compute_budget`) | 4500 (20000 / 4.36, the worst measured under-prediction of the cost model, BENCHMARK_LOCAL.md section 7) |
| `SCREENER_CAP_BUDGET_MS` | :100, at least 1; :117-118 refuses a value whose caps refuse a registry default | the length caps (`registry.ts capOf`) | 4500, equal to `SCREENER_MAX_CPU_MS` (caps 1261 -> 567) |
| `SCREENER_DEADLINE_MS` | :101, at least 1 | request deadline, queue included (`504 TIMEOUT`) | 20000; edge-bff's `SCREENER_TIMEOUT_SECONDS` = this / 1000 = 20 |
| `SCREENER_MAX_CONDITIONS` | :102, at least 1 | enabled conditions per definition | 20 |
| `SCREENER_MAX_METRIC_FILTERS` | :103, at least 0 | universe metric filters per definition | 8 |
| `SCREENER_WITHIN_MAX` | :104, at least 1 | longest `within`; tails are this + 1 bars (`metrics.ts tailLength`) | 130 |
| `SCREENER_MAX_COUNTS` | :105, at least 1 | definitions per counts request (at least edge-bff's `SCREEN_LIMIT`, 50) | 50 |
| `SCREENER_MAX_RESPONSE_BYTES` | :106, at least 1 | JSON bytes of one answer | 4194304 (an answer inside the limits reaches about 2.8 MB; report 8.9 had 2097152) |
| `SCREENER_QUEUE` | :107, at least 0 | users' requests waiting for a thread on this replica (`409 BUSY`); the system lane is not counted | 4 (2 x K) |
| `SCREENER_OWNER_INFLIGHT` | :108, at least 1 | running requests per owner tag (the owner's lane) | 1 (K - 1: light owners' p95 x 1.6 with a heavy owner, x 32-41 with 2; report's provisional 2) |
| `SCREENER_OWNER_CPU_MS` | :109, at least 1; :119 at least `SCREENER_MAX_CPU_MS` | P33: thread ms per owner tag per minute (`422 LIMIT_EXCEEDED owner_cpu_budget` with the wait) | 30000 |
| `SCREENER_PREVIOUS_GRACE_S` | :110, at least 0 | seconds the previous snapshot serves requests pinned to it | 600 (report 06d / 8.9 provisional; not measured) |
| `SCREENER_MAX_FILE_BYTES` | :111, at least 1 | gzip bytes of one xsection file, checked on the index before any grant | 24000000 (2 x 11,758,823 B measured locally; re-derive from the dev publisher run, DEPLOY_RUNBOOK step 6) |
| `SCREENER_MAX_INFLATED_BYTES` | :112, at least 1 | bytes one file may inflate to (`TerminalClient maxFileBytes`) | 150000000 (2 x 74,272,854 B) |
| `SCREENER_MAX_REFRESH_BYTES` | :113, at least 1 | gzip bytes one refresh may download in total | 24000000 (2 x 11,772,808 B) |
| `SCREENER_MAX_REQUEST_BYTES` | :114, at least 1 | bytes of one request body (`413 REQUEST_TOO_LARGE`, limit `request_bytes`) | 131072 (edge-bff's own body cap, `app/screener.py REQUEST_BYTES`) |
| memory limit (Railway, not a variable) | `.railway/railway.ts` `limitOverride.containers.memoryBytes` | the replica's memory | 2.75 GB (2750000000) at K = 2: 1.5 x the 1.81 GB measured with 512 MiB of caches full and the previous snapshot in its grace (256 MiB leaves more margin); the report's 2 GB start value has no margin |

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
skew, `/manifest`, `/reference/tickers`, presigned bucket URLs, faults per file). Last run: 61 of 61 pass (2026-10-29).

| Suite | What it locks |
|---|---|
| `config.test.ts` | every limit required with no default; errors name the variable, not the value; cap and owner-budget checks; `screener_engine` is a content hash; the start-up check |
| `readme_config.test.ts` | this README's "Configuration" table against `loadConfig` itself (the names it reads, recorded; each left out in turn): one row per name read and no other, each row's `config.ts` line reads it, its minimum is the `whole()` minimum, optional rows are the ones it starts without, the proposed values pass it together, the counts in the prose; and that each kind of drift fails |
| `onboarding_pointers.test.ts` (rule and parser in `doc-pointers.ts`) | every `path:line` pointer of the repository's `SCREENER_ONBOARDING.md` against the files as they are now, read by the rule its "Pointers" bullet states: each names one file and existing lines, and the symbol written next to it is on its first cited line; and that each kind of drift fails (a line that moved under its symbol, a bare pointer after another file's pointer, a line past the end, an ambiguous name, a renamed symbol) |
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
