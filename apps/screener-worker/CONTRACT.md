# screener-worker: the private API contract

The rules between edge-bff (`apps/edge-bff/app/screener.py`, its only caller) and the screener-worker. The wire types
are in `apps/edge-bff/screener/src/core/contract.ts` (report API CONTRACT section 8); this file states what the worker
promises on top of them. Report references: `06` TARGET ARCHITECTURE, `06d` MULTI-USER SCALE AND COST, `08` API
CONTRACT (approval-gate report, EXEC-SCREENER).

## 1. Transport and identity

- Private network only (`http://screener-worker.railway.internal:8080` on Railway); the browser never reaches it.
- `x-screener-worker-key: $SCREENER_WORKER_KEY` (at least 32 characters) on every route except `GET /health` and
  `GET /ready`. A missing or wrong key answers `401 {"error":{"code":"UNAUTHORIZED"}}` (the backtest worker's code; it
  is not a contract code because the page never sees it: edge-bff logs it and answers `503 SCREENER_UNAVAILABLE`).
- `x-screener-owner`: the first 16 hex of HMAC-SHA256(`SCREENER_WORKER_KEY`, `owner_key`) (contract.ts
  `WORKER_OWNER_TAG`), on every call except `/health` and `/ready`. It selects the owner's lane and budget; the worker
  never learns the owner. Absent: one shared lane `-`. Malformed: `422 INVALID_INPUT` field `x-screener-owner`.
- `/ready` takes no key because a Railway healthcheck sends no header; it says only whether a snapshot is loaded.
- A request body is read to its end before the answer, at most `SCREENER_MAX_REQUEST_BYTES` of it kept (`413
  REQUEST_TOO_LARGE` beyond). A caller that closes its connection before the answer cancels its work.

## 2. Routes

| Route | Answer | Encoding |
|---|---|---|
| `GET /health` | `WorkerHealth {ok, versions, published_at, snapshot_age_seconds, refresh}`; `versions` null and `refresh` `loading` before the first snapshot; `refreshing` while a publication is built; else `ready` or `failed_keeping_previous`. `snapshot_age_seconds` = now − `published_at` | JSON |
| `GET /ready` | `200 {ready: true}` with a snapshot; else `503 {ready: false, retry_after_seconds, error: {code: SCREENER_NOT_READY}}` with `Retry-After` | JSON |
| `GET /v1/catalog` | `CatalogResponse` (8.4): `versions`, `data` (with `refresh`), `limits[]`, `indicators[]`, `metrics[]`, `fundamentals[]`, `periods`, `groupings`, `presets[]` | gzip when accepted; `ETag`; `If-None-Match` → `304` |
| `GET /v1/universe` | `UniverseResponse`: every listed stock, hidden ones included, with remarks | gzip when accepted; `ETag`; `304` |
| `POST /v1/run` | `RunRequest` → `RunResponse` (8.5) | gzip (`Content-Encoding: gzip`), `ETag` |
| `POST /v1/preview` | `PreviewRequest` → `PreviewResponse` (8.6) | gzip, `ETag` |
| `POST /v1/counts` | `CountsRequest` → `CountsResponse`; an entry whose definition is refused carries `{item_id, error}` | gzip, `ETag` |
| `POST /v1/validate` | `{schema_version: 1, definition}` → `{valid: true, definition_hash, normalized, versions}` (versions additive: the registries it was checked against) or the first refusal | JSON |

Every computed answer opens with `versions` and `data` (a run answer with `schema_version` first), so edge-bff reads
`price_data` and `published_at` from the first inflated bytes of a gzip answer without parsing the rest (6d.5).
`ETag` is `"<sha256 of the JSON bytes>"`. Catalog and universe bytes depend only on the publication, the versions and
the publication's outcome: two replicas at one publication answer the same bytes and the same `ETag`.

## 3. Versions and pinning (06d.4)

- `versions` = `{screener_engine, registry, screener_registry, price_data, flow_data: null}` (+ `definition_hash` on a
  run). `price_data` is `datafile.dataVersion` over (ticker, `price`, pack sha256) of every ticker of the publication.
- `data_version` (optional on run and counts, required on preview) pins a request to a snapshot: the current one, or the
  previous one for `SCREENER_PREVIOUS_GRACE_S` after a swap.
- A version the replica held and dropped, or one older than both: `409 DATA_VERSION_CHANGED` (the page reads the catalog
  again and runs again).
- A version the replica does not know while terminal-api names a publication it has not loaded (its `/state` read again
  at most every 5 s for this check): `409 DATA_VERSION_PENDING` (worker-only). edge-bff retries once on a new
  connection, then answers `503 SCREENER_NOT_READY` with `Retry-After: 2`.
- No snapshot yet: `503 SCREENER_NOT_READY` with `Retry-After` while the first one loads; `424 DATA_INTEGRITY` (the
  latest publication failed its checks) or `424 DATA_UNAVAILABLE` (nothing could be loaded) when it failed and no
  earlier snapshot is held.

## 4. Admission (06d.6; P33)

In this order, before a computing request reaches a thread:

1. A result-cache hit is answered at once, outside every queue and budget.
2. The per-request budget: the worst case (every non-pre-warmed series of every enabled condition and metric filter on
   every S0 survivor, as the cost model predicts) above `SCREENER_MAX_CPU_MS` → `422 LIMIT_EXCEEDED {limit:
   'compute_budget', allowed, needed, costliest}`, never cut short.
3. The per-owner budget (P33): thread milliseconds the owner tag used in the last 60 s, plus the predicted cost of its
   waiting and running requests, plus this one, above `SCREENER_OWNER_CPU_MS` → `422 LIMIT_EXCEEDED {limit:
   'owner_cpu_budget', allowed, needed, retry_after_seconds}`; the message names the wait.
4. The queue: more than `SCREENER_QUEUE` requests waiting on the replica → `409 BUSY {limit: 'queue'}`.
5. The owner's lane: at most `SCREENER_OWNER_INFLIGHT` running per owner tag; the rest wait in the lane, served by deficit
   round robin across lanes weighted by the predicted cost. A newer request of the same page (`client_order.page`,
   higher `seq`) replaces a waiting older one, which answers `409 SCREEN_REPLACED` / `PREVIEW_REPLACED`.
6. The deadline: `SCREENER_DEADLINE_MS` from arrival, queue included → `504 TIMEOUT`.

## 5. Caches (8.10, 6d.2)

- Result cache (gzip answer bytes): keyed by the snapshot identity (`price_data` plus the actions and reference
  contents), `screener_engine`, `registry`, `screener_registry`, `definition_hash` and the options that change the
  bytes (`exhaustive`, `explain`); nothing of the owner, the page or the order is in the key or in the answer. A hit
  returns the first computation's bytes, `timings_ms` included. Each available preset's result is kept in it for the
  publication (computed by the refresh, never evicted until the snapshot is dropped).
- Counts: match and near counts per (snapshot, definition), filled by every run and counts request.
- Previews: per (snapshot, definition, ticker).
- Series: each compute thread's SeriesCache holds the snapshot's pinned tails and an LRU of custom-parameter tails.
- Files: by sha256 in `SCREENER_CACHE_DIR` (TerminalClient's DiskCache); a cached file is read without a grant.
- Every cache is per replica (P34 a) and dropped with its snapshot.

## 6. Errors

Every error is `{"error": {code, field?, message?, details?}}` with the statuses of report 8.8 (contract.ts
`WORKER_ERROR_STATUS`); refusals name the field where there is one and the fix. Worker-only codes: `UNAUTHORIZED`
(401), `NOT_FOUND` (404, a route), `METHOD_NOT_ALLOWED` (405), `INTERNAL_ERROR` / `OUT_OF_MEMORY` (500, logged with the
stack, answered without it), and `DATA_VERSION_PENDING` (409).

## 7. What the worker never does

It holds no Postgres or bucket credential; it reads terminal-api only with the gateway key (`/state`, `/xsection`,
`/manifest`, `/reference/tickers`) and presigned URLs on `SCREENER_FILE_ORIGIN`; it writes nothing anywhere but its own
disk cache; it logs no key, header, body or presigned URL; it computes no formula of its own (every number is the
screener core's, over the Terminal's `F` through the backtest core's `Calc`).
