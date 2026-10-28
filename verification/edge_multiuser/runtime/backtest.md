# Backtest: multi-user runtime design (read-only, 2026-10-28)

**User direction (2026-10-28, `PLAN.md:947-957`):** "Yang mesti dipastikan adalah screener worker beserta backtest machine secara
arsitektur harus bisa menghandle multi-user termasuk terminal. Untuk AI org, leave as is saja. Untuk terminal backtest dan
screener, efisiensi biaya dan efisiensi proses menjadi prioritas. Akurasi juga. ... Kita tidak mau biaya terlalu mahal, tapi
kita juga tidak mau user kalau memproses, melakukan screen dan lain-lain menjadi terlalu lama." Users will be external (P29,
`PLAN.md:914-915`). Accounts are on hold, so every per-user rule below keys on `owner_key`: one owner today, many later. AI Orc is
out of scope.

**Area:** the Backtest runtime: `apps/backtest-worker`, `apps/edge-bff/app/backtest.py`, the shared core
`apps/edge-bff/backtest/src/core`, and the page only where it waits on the runtime. terminal-api appears only as the data gate
the worker reads through.

**Read-only.** Nothing was changed in the repository, on Railway or in the database. The evidence was gathered on 2026-10-28
from these sources:
- repository `main` at `3847fc4`;
- `BACKTEST_END_TO_END.md` and `apps/edge-bff/backtest/CONTRACT.md`, both read in full (AGENTS.md rule);
- the earlier audits `verification/edge_multiuser/capacity_fairness_scale_cost.md` (cited as CAP), `verification/edge_multiuser/AUDIT.md`
  (cited as MU) and the Screener report 6d (`scratchpad/report/06d_multi_user_scale_cost.md`, cited as 6d);
- Railway read with `@railway/cli@5.71.0`: `status --json` and `metrics --raw` for `backtest-worker`;
- the live database read with `pgq2.py` (role pgweb, read-only). This role can read the `edge_bff` statistics but not its rows.

**Labels:**
- FACT: seen in code (file:line), in a recorded measurement or in a live read;
- INFERENCE: derived from facts;
- PROPOSED: a design element waiting for approval;
- UNKNOWN: not settled, with the check that would settle it;
- TEMPORARY: a stopgap meant to be replaced.

**Prices** are the ones in 6d.1, read from Railway's documentation on 2026-10-28:
- RAM USD 10 per GB-month;
- CPU USD 20 per vCPU-month (USD 0.0000077 per vCPU-second);
- egress USD 0.05 per GB;
- volume USD 0.15 per GB-month;
- bucket storage USD 0.015 per GB-month;
- bucket egress and private-network traffic are free.

---

## 0. Summary

1. **Today one Backtest job and one preview run at a time, for every user of EDGE.**
   - FACT, worker: `apps/backtest-worker/src/server.ts:108` has one `jobs` thread and one `previews` thread. `:113` keeps a
     single `job` and `:270` answers 409 `BUSY`. Previews wait in a FIFO queue (`:197-235`).
   - FACT, edge-bff: one loop takes the oldest QUEUED job of any owner with nothing running and follows it to the end
     before it claims the next (`apps/edge-bff/app/backtest.py:516-527, 629-650`).
   - INFERENCE: this is first come, first served across owners, with no rotation. An owner who queues 3 jobs delays every
     other owner (CAP finding 3).
2. **Most of a short job's wall time is waiting on fixed polls, not computing.**
   - FACT: a warm single run computes 0.45-0.58 s in the worker but takes 5.5-5.9 s from submit to end. A warm 12-stock
     portfolio computes 5.5 s and takes 10.8 s (`apps/backtest-worker/README.md:430-432`).
   - FACT, the waits in the code: the loop sleeps `EDGE_POLL_SECONDS` (2 s) when it finds no job (`backtest.py:645`); the
     follower sleeps 2 s before its first status call (`:808`); the page polls every 1 s (`backtest/src/run.ts:21`).
   - INFERENCE: event-driven hand-off cuts a warm single run to about 1.5 s end to end, with no change to any number.
3. **A warm run is CPU spent on decoding, not on the engine.**
   - FACT: caches hold gzip bytes, so every use re-hashes, inflates and decodes them (`BACKTEST_END_TO_END.md:623-624`;
     `apps/backtest-worker/src/terminal.ts:479-521`).
   - INFERENCE: most of the warm 5.5 s for 12 flow stocks (2.49 M broker rows, 28 MB gzip, `CONTRACT.md:188-189`) is
     JSON parse and building rows.
   - PROPOSED: a decoded-series cache keyed by file sha256. The bytes are still verified on every use, so the CONTRACT
     rule stands.
4. **Server previews are the first thing to saturate.**
   - FACT: one preview thread; a 12-stock preview issues one `/bundle` per stock (`apps/backtest-worker/src/load.ts:332-345`).
   - FACT: every grant, from the page, the worker or the Screener, takes the same advisory lock in terminal-api
     (`BACKTEST_END_TO_END.md:418-419`).
   - FACT, measured: 20 concurrent `/bundle` take a median 0.53 s (`ERRORS_AND_SOLUTIONS.md:2302-2304`).
   - INFERENCE: about 38 grants/s in all. At 200 users at once, previews and jobs would need about 34 grants/s on
     average in busy hours.
5. **The engine is deterministic, so identical requests can share one computation, except for one per-owner piece.**
   - FACT: everything in a result is a function of the canonical request, the files read and the engine and registry
     versions.
   - FACT, the exceptions: `meta.duration_ms`, and the trial count and Deflated Sharpe, which use the owner's prior trials
     (`apps/edge-bff/backtest/src/core/result.ts:202-214, 231`; `robustness.ts:74-88`; `stats.ts:64, 106-110`).
   - PROPOSED: reuse exactly by `request_hash`, and recompute the per-owner part with the core's own functions.
6. **Recommended order:**
   - (1) event-driven hand-off, then the decoded cache;
   - (2) K job threads and P preview threads in one replica, a slot-aware fair claim, per-owner limits, deploy drain;
   - (3) reuse and pre-warming after each publication;
   - (4) grant-free planning in terminal-api;
   - (5) a second worker only for availability or above about 10,000 jobs an hour.
   - One replica at K = 4 serves about 10,000 jobs an hour at 70 % use (INFERENCE). Railway bills CPU by use, so a larger
     K costs little while idle.
7. **Cost (INFERENCE, section 6).** For Backtest compute, RAM, result storage and egress, with 10 / 50 / 200 users at once
   (4 busy hours a day): about USD 5 / 7.5 / 16 a month with the proposals. The architecture of today would cost about
   USD 13 / 20 / 47 for the same load, and could not serve 50 or more users. The two cost levers are resident RAM (caches per
   thread) and result retention in Postgres.

---

## 1. Today (verified)

### 1.1 Processes, state and limits

| Item | State | Evidence |
|---|---|---|
| Worker service | 1 replica in `sfo`. No healthcheck path, restart `ON_FAILURE`, no memory limit override (24 vCPU / 24 GB plan ceiling). Deployment `292f7caa` SUCCESS 2026-10-27 16:30 UTC | FACT, `railway status --json` 2026-10-28 (`numReplicas` 1, `healthcheckPath` null, `limitOverride` null) |
| Worker compute | Two long-lived worker threads, `jobs` and `previews`. One task at a time per thread | FACT, `server.ts:108`; `compute.ts:1-6` |
| Jobs in the worker | One job, held in memory. Its result is kept until the next job starts, then 410 `RESULT_GONE`. After a restart every id is 404 `UNKNOWN_JOB`, which edge-bff turns into `WORKER_LOST` | FACT, `server.ts:113, 269-279, 286-288`; `BACKTEST_END_TO_END.md:450-451` |
| Previews in the worker | A FIFO queue with one computing. A caller that leaves is dropped from the queue or cancelled | FACT, `server.ts:197-235` |
| Shutdown | SIGTERM closes the server and kills both threads at once, with no drain | FACT, `server.ts:338-341, 354-356` |
| Byte caches | A memory LRU per thread (`BACKTEST_CACHE_BYTES`, dev 1.5 GB per thread) and one disk directory shared by every thread (`/tmp/backtest-cache`, 1 GiB, lost on redeploy). Every use runs `inflateVerified` (sha256, size, inflate) | FACT, `terminal.ts:24-30, 196-213, 244-330, 479-521`; README `:210-211` |
| Decode | Each use rebuilds the price series, the broker rows and the flow from the inflated JSON | FACT, `terminal.ts:525-550` |
| Grants per run | Step 1 asks one `/bundle` per ticker before any download: IHSG plus the stocks (13 for a 12-stock job, 12 for a 12-stock preview). Each `/bundle` is a grant, an access-log row and a lock | FACT, `load.ts:323-352`; `BACKTEST_END_TO_END.md:339-348, 413-419` |
| Versions | `engine_version` hashes every core file and every `apps/backtest-worker/src/*.ts` file, so any worker code change gives a new `engine_version` | FACT, `apps/backtest-worker/src/version.ts:4-9, 25-31` |
| edge-bff loop | One `BacktestLoop` in the edge-bff process. It claims the oldest QUEUED job of an owner with no RUNNING job (`ORDER BY created_at`) and follows that job to its end before claiming again | FACT, `backtest.py:516-527, 629-650, 719-726` |
| Waits in the loop | Idle poll 2 s; the follower sleeps 2 s before each status call; a `BUSY` answer waits 2 s | FACT, `backtest.py:645, 808, 781`; `config.py:20-22, 64` |
| Per-owner rules | 1 RUNNING per owner (unique partial index); 3 QUEUED per owner (429 `QUEUE_FULL`, under an owner advisory lock); 1 preview in flight per owner, latest wins (per process) | FACT, migration `20261026_005:54`; `backtest.py:437-456, 1002-1046`; `config.py:37` |
| Owner | Every route uses `settings.owner` | FACT, `backtest.py:1050` |
| Worker URL rule | edge-bff accepts only the host `backtest-worker.railway.internal` | FACT, `config.py:105-108` |
| Results | `edge_bff.backtest_results`: gzip bytea parts kept 30 days. Single mode gunzips, merges and re-gzips on every read | FACT, migration `20261026_005:60-69`; `backtest.py:1132-1150` |
| Ingest | edge-bff parses the whole result JSON in Python, splits it and stores it in one transaction (`loads` + `split_result` in a thread) | FACT, `backtest.py:871-899, 575-602` |
| Live tables | `backtest_jobs` 46 rows, `backtest_results` 204 parts (6.2 MB), `backtest_trials` 250 rows. `idx_scan` on jobs is 116,532: the 2-s claim poll | FACT, `pg_stat_user_tables` 2026-10-28 |

### 1.2 Where the time of one job goes

| Step | Single, warm (FACT total 5.5-5.9 s) | Portfolio of 12 with flow, warm (FACT total 10.8 s) |
|---|---|---|
| Page submit, then edge-bff `/v1/validate` (manifests only) | about 0.1-0.3 s (INFERENCE) | same |
| Until the loop claims the job (idle poll 2 s) | 0-2 s, about 1 s on average (INFERENCE from `:645`) | same |
| Dispatch to the worker | under 0.1 s | same |
| Worker compute | 0.45-0.58 s (FACT) | 5.5 s (FACT): mostly decoding (INFERENCE) |
| Follower notices the end (2-s sleeps) | about 2 s (INFERENCE from `:808`) | rounds 5.5 s up to the next 2-s step |
| Fetch, split and store the result | about 0.1-0.3 s | about 0.3 s |
| Page notices (1-s poll) | 0-1 s | 0-1 s |

INFERENCE: about 4-5 s of the warm single run's 5.5 s is polling. A cold run adds downloads from the `sin` bucket (FACT:
28.35 MB in 6.1 s, README `:431`).

### 1.3 Resources

- **Memory and CPU:** FACT, `railway metrics` for the last 3 days, hourly:
  - average 0.17 GB over the last 2 days, 78 MB now;
  - 0.50-0.61 GB in the hours of the dev E2E;
  - a maximum of 2.05 GB in the hour of 2026-10-27 08:00 UTC. That hour held three redeploys for the region test
    (`RAILWAY_CHANGELOG.md:4767-4772`), so the per-run peak in it is UNKNOWN;
  - CPU at most 0.04 vCPU as an hourly average.
- **Recorded peak:** FACT, the one-minute peak was 1.31 GB during a preview, a run and a cancel of 12 stocks (README `:439`).
- **Page cache counts as memory:** FACT, Railway billed Linux page cache as memory for Postgres (6.14 GB, "about USD
  60/month", `RAILWAY_CHANGELOG.md:4221-4225`). INFERENCE: the worker's 1 GiB disk cache can show up as memory too unless the
  service has a memory limit.
- **Usage cost:** about USD 0.5 a month for the worker (CAP 2.2, usage API 10-24..28).

### 1.4 What breaks first with many users (INFERENCE, numbers in section 5)

1. **Portfolio previews with flow conditions.**
   - One thread, about 3 s of decoding each. With one preview per 10-15 s of editing, about 3-5 users editing such
     portfolios fill it.
   - Each such preview also takes 12 grants.
2. **Jobs.**
   - One slot. Each job holds it for at least the 2-s poll step: about 3.6 s per job in a 70/30 mix of single and
     portfolio runs.
   - The slot saturates at about 16 users at once with one run a minute each, or about 33 with one run every two minutes.
     Then `QUEUE_FULL` appears.
3. **terminal-api grants.** About 38 grants/s under one lock, shared with the Terminal page and the Screener.
4. **Result storage.** 136 KB per job, about 30 days kept in Postgres. At 200 users at once this is about 72 GB.
5. **Deploys.** A worker deploy kills running jobs (`WORKER_LOST`) and empties the disk cache.
6. **Fairness.** FIFO across owners.

---

## 2. Invariants every proposal keeps (accuracy)

| # | Invariant | Where it is guaranteed today | How the proposals keep it |
|---|---|---|---|
| I1 | The same canonical request on the same files with the same `engine_version` and `registry_version` gives the same result; only `meta.duration_ms` differs | FACT, `BACKTEST_END_TO_END.md:572-573`; tests `run.test.ts:209`, `server.test.ts:403` | Threads, caches and reuse only change *where* a computation runs or *whether* it runs. New parity tests (section 8) compare the result bytes with `duration_ms` zeroed |
| I2 | `data_version` is the hash of the files actually read; every byte copy is checked against its manifest on every use | FACT, `datafile.ts:268-278`; `CONTRACT.md:86-89` | B2 keeps the check on every use. B6 reuses only on an equal `data_version` |
| I3 | `request_hash` = hash of the canonical request + engine + registry + data versions | FACT, `hash.ts:131-132` | The reuse key |
| I4 | Trials are counted per owner and lineage; a run's prior trials are read when the job is handed over | FACT, `backtest.py:557-563, 763`; `CONTRACT.md:338-349` (K3) | Unchanged. **1 RUNNING per owner stays** (migration `:54`). INFERENCE: two running jobs of one owner on one lineage would read the same prior trials, and neither would count the other's variants. That would flatter the Deflated Sharpe, so the per-owner cap of 1 is also a K3 guard. A reused result still records the owner's trials |
| I5 | No market data from PostgreSQL; the worker holds no database or bucket credentials | FACT, `CONTRACT.md:20-22` | Unchanged. Reuse state lives in edge-bff's tables |
| I6 | Limits are checked on the manifests, before any download, and never depend on the cache | FACT, `load.ts:350-352` | B3's memory admission comes *after* this check. B6's reuse probe comes after the same checks, so it gives the same refusals |

---

## 3. What in a result is shared and what is per owner (FACT, then PROPOSED rule)

The result is built in `result.ts:187-235`. It splits into three parts:

- **Shared** (a pure function of the canonical request, the files read, `engine_version` and `registry_version`):
  - `dates`, `equity`, `benchmark`, `drawdown`, `exposure`, `daily_returns`, `oos`, `stats`, `trade_stats`, `trade_returns`,
    `tables`, `trades`, `events`;
  - `robustness.monte_carlo` (seeded by the request) and `robustness.sensitivity`;
  - in `meta`: the versions, `request_hash`, `lineage_key`, `seed`, `mode`, `tickers`, `benchmark`, `data_through`,
    `warnings`;
  - `meta.trials.variants`: the run's own distinct variants with their Sharpe (`robustness.ts:64-79`: `own`, which does
    not depend on the prior trials).
- **Per owner:**
  - `meta.trials.prior`, `this_run` and `total` (`trialSet(prior, variants)`, `robustness.ts:74-80`);
  - `robustness.deflated` (`deflatedSharpe(st, srs)`, `robustness.ts:85-88`). It reads the run's `st.srd`, `st.n`,
    `st.skew` and `st.kurt` through `st.psr` (`stats.ts:63-64`) and the trial Sharpes `srs`, which are the prior trials
    plus the run's own.
- **Per run:** `meta.duration_ms`.

**PROPOSED rule, with its test.** The per-owner part is a pure function of these inputs:
- the shared part's deflation inputs `{srd, n, skew, kurt}` (the raw values, NaN carried as null);
- `meta.trials.variants`;
- the owner's prior trials.

A new core function `ownerPart(inputs, variants, prior)` in `robustness.ts` computes it with the existing `trialSet` and
`dsr`. `buildResult` uses the same function, so a fresh run and a reused run share one code path. The test (section 8,
test W5): for random priors, `ownerPart(deflationInputs(r), r.meta.trials.variants, prior)` gives bit-identical `trials` and
`deflated` to a fresh `buildResult` with that prior.

---

## 4. Proposals

Each proposal has: need · general class · fix and owning layer · covers / does not cover · risks and cost · verification ·
permanent or TEMPORARY.

### B1. Event-driven hand-off instead of fixed polls

- **Need.** About 4-5 s of a warm run is polling (1.2). Each job holds the single slot for at least 2 s.
- **Class.** Latency, plus slot occupancy (throughput).
- **Fix and owning layer.**
  - *edge-bff `backtest.py`.* `submit` sets an in-process `asyncio.Event` that wakes the loop at once. Another process
    keeps the 2-s idle poll as the fallback.
  - *edge-bff, the follower.* It calls the worker with the async client (`WorkerClient.acall`, already used for relays so
    that waits do not hold the thread pool, `backtest.py:287-292`).
  - *Worker `server.ts`.* `GET /v1/jobs/{id}?wait_ms=N` (N at most 25,000) answers as soon as the state or phase differs
    from what the caller last saw, else after N ms. The follower then fetches the result at once. A new
    `DELETE /v1/jobs/{id}` frees the held result.
  - *Page.* `run.ts` waits on `GET /api/v1/backtests/{id}?wait_ms=` (edge-bff wakes on its own follower's end in-process
    and falls back to a 250 ms database read when the follower runs in another process), or, smaller, polls every 250 ms
    for the first 3 s and every 1 s after.
- **Covers.** Submit-to-claim, claim-to-end and end-to-page delays, for every job. **Does not cover** the compute itself
  (B2) or downloads (B8).
- **Risks and cost.**
  - Long-polls hold sockets, not threads; they must stay on the event loop (FACT: this pattern exists for previews).
  - A few more edge-bff requests, with `wait_ms` capped.
  - No cost change.
- **Verification.**
  - Dev E2E (`verification/backtest/e2e_dev.py`): single warm submit-to-end at most 2 s (from 5.5-5.9 s), 12-stock warm
    at most compute + 1 s.
  - Tests: `server.test.ts` (long-poll answers on the end and on the deadline) and `test_backtest.py` (the loop wakes on
    submit and fetches the result without waiting a poll step).
- **Permanent.**

### B2. Decoded-series cache (verify the bytes, reuse the decode)

- **Need.** Warm runs and previews redo inflate, JSON parse, row building and flow (`terminal.ts:479-550`). This is the
  largest CPU item (INFERENCE, 0.3).
- **Class.** Process efficiency, which is also cost (CPU and transient memory).
- **Fix and owning layer.** *Worker `terminal.ts` (`TerminalClient.loadTicker`).*
  - A per-thread LRU, `BACKTEST_DECODED_CACHE_BYTES` (PROPOSED 256 MB, then sized from measurement). It maps
    (ticker, dataset, sorted file sha256 list) to the decoded value: `PriceSeries`, `FlowData` with no broker rows kept,
    or corporate actions.
  - On each use the bytes are still read (memory, then disk) and checked by sha256 and size. Only inflate and decode
    are skipped. This keeps CONTRACT section 2 ("checked against its manifest again each time it is used") as written.
  - Pure-decoded use without re-reading the bytes would save about another 0.1 s per 28 MB. It is a separate decision
    (D-R5) because it changes that rule.
  - The per-thread gzip memory cache `BACKTEST_CACHE_BYTES` drops from 1.5 GB to about 64 MB (B3).
- **Covers.** Warm jobs, previews, the sensitivity reruns (they already share the prepared data, `run.ts:144-166`), and
  pre-warming (B8). **Does not cover** cold downloads.
- **Risks and cost.**
  - A decoded object is shared between jobs on the same thread. If engine code ever mutated a cached array, a later job
    would read changed data.
    - Guard: a test running A, B, A must give equal bytes with the cache on and off.
    - Guard: a debug mode (`BACKTEST_DECODED_CACHE_CHECK=1`, tests and the dev E2E) checks a hash of each cached buffer
      after every job.
  - RAM: up to the budget per thread. INFERENCE sizes: one price series about 100 KB (2,126 bars × 6 values), one flow
    ticker about 1-2 MB (about 50-120 brokers × 2,126 doubles, `flow.ts:30-36`). 256 MB holds every price series plus
    about 100 flow tickers.
- **Verification.**
  - `run.test.ts`: cold, warm and decoded-hit results equal; the A-B-A test.
  - `measure_dev.py`: 12-stock flow portfolio warm compute from 5.5 s to a measured value (target 1.5 s or less);
    preview warm time.
- **Permanent.**

### B3. K job threads and P preview threads in one replica, with memory admission

- **Need.** One job slot and one preview slot serve all owners. Railway bills CPU by use and scales a replica vertically
  up to the plan limit (6d.1, from Railway's scaling documentation), so threads are the cheapest concurrency.
- **Class.** Throughput, wait time, cost.
- **Fix and owning layer.** *Worker `server.ts`, `compute.ts`, `config.ts`.*
  - Thread counts:
    - `BACKTEST_JOB_THREADS` (K): default 1, so behaviour stays as today until set. PROPOSED start 2, then 4 after the
      tests.
    - `BACKTEST_PREVIEW_THREADS` (P): default 1, PROPOSED 2.
  - Jobs:
    - a `Map` of jobs replaces the single `job`;
    - `BUSY` only when all K threads hold a job;
    - a timeout or cancel kills only that job's thread (today `threads.jobs.kill()`, `:160`).
  - Held results: kept until `DELETE`, or `BACKTEST_RESULT_HOLD_SECONDS` (PROPOSED 600), or a byte budget
    `BACKTEST_RESULT_HOLD_BYTES` (PROPOSED 256 MB). Past these the result is 410 `RESULT_GONE` (D-B1 semantics stay).
  - Previews: a pool of P threads over the existing FIFO. edge-bff already allows only one preview in flight per owner,
    so FIFO is already one per owner (INFERENCE).
  - **Memory admission.** Before step 2, a job or preview reserves its planned decode memory from a process budget
    `BACKTEST_DECODE_BUDGET_BYTES`:
    - the planned memory is Σ manifest bytes × an inflate-and-object factor, TEMPORARY 20 until measured (FACT ratio
      gzip to JSON: 2.2 MB to 14.5 MB, README `:217`);
    - the budget is counted with `Atomics` on a SharedArrayBuffer shared by the threads;
    - a job waits rather than running out of memory;
    - the cache hits of B2 reserve nothing.
  - **Idle trim.** Threads beyond the first job and the first preview thread exit after
    `BACKTEST_IDLE_THREAD_SECONDS` (PROPOSED 600) idle and are started again on demand (about 100 ms, README `:418`), so
    resident memory falls back when nobody uses it.
- **Covers.** Concurrency, preview latency, memory safety. **Does not cover** fairness (B4) or a replica failure (B10, B12).
- **Risks and cost.**
  - One process holds all slots: a crash loses up to K jobs (B10 handles a deploy).
  - RAM at peak about 0.1 + K × 0.3 + 0.8 GB (INFERENCE: base, decoded caches and heaps, one admitted heavy decode). That
    is about 1.3 GB at K = 2 and about 2.1 GB at K = 4, for the busy hours only (idle trim).
  - The download lanes (`BACKTEST_DOWNLOAD_CONCURRENCY` 16) are per thread: K × 16 requests at once to terminal-api.
    Lower to 8 with K = 4.
  - `server.ts` changes, so `engine_version` changes (FACT, `version.ts`); the numbers do not.
- **Verification.**
  - `server.test.ts`: K jobs at once; `BUSY` at K + 1; hold, ack and eviction; a kill on timeout leaves the other jobs
    running.
  - `run.test.ts`: N jobs run concurrently on K threads give the same bytes as sequential runs.
  - A memory test on dev: K = 2 and then K = 4, with the 12 largest broker stocks cold at once on every thread, read with
    `railway metrics`. Then set the Railway memory limit to peak × 1.5.
- **Permanent.** The factor 20 and the 600 s are TEMPORARY values.

### B4. Slot-aware, fair claim in edge-bff

- **Need.** FIFO across owners (FACT, `backtest.py:516-527`). With K slots, one loop that follows one job at a time also
  wastes slots. Several edge-bff processes would each claim (CAP 3.1).
- **Class.** Fairness and scheduling, with multi-process safety.
- **Fix and owning layer.** *edge-bff `backtest.py` (`claim`, `BacktestLoop`), plus a migration.*
  - **Slots.**
    - `BACKTEST_SLOTS` = Σ K over the worker targets.
    - New column `backtest_jobs.slot text` with a unique partial index on `slot` `WHERE state='RUNNING'`.
    - `claim(slot)` takes a free slot, so N edge-bff processes never run more than `BACKTEST_SLOTS` jobs.
    - The loop runs up to `BACKTEST_SLOTS` follower tasks at once.
  - **Order.** Among owners with a QUEUED job and no RUNNING job (the per-owner cap stays 1, I4), take the owner with the
    least compute in the last hour, then the oldest queued job:
    - compute in the last hour is `Σ duration_ms` of that owner's jobs with `created_at > now() - 1 h`, read through the
      existing index `(owner_key, created_at DESC)` (migration `:56`);
    - **aging**: a job queued longer than `BACKTEST_MAX_WAIT_SECONDS` (PROPOSED 60) goes first, so a heavy owner is never
      starved.
    - This weights by measured cost instead of plain round-robin by job count. MU MP-15 proposes the latter; with a
      10× spread in job cost (FACT 0.5 s against 5.5 s) a count-based rotation still lets heavy owners take most of the CPU.
  - Lock with `FOR UPDATE SKIP LOCKED` on the chosen job, as today.
- **Covers.** Fair waits between owners, and safety with many processes. **Does not cover** totals per day (B5).
- **Risks and cost.**
  - A slightly heavier claim query (a scan over QUEUED rows plus one aggregate per waiting owner on an index).
    INFERENCE: milliseconds at hundreds of queued rows.
  - Run an `EXPLAIN (ANALYZE, BUFFERS)` against a seeded copy before shipping (AGENTS.md performance rule).
- **Verification.** `test_backtest.py`:
  - owner A queues 3 heavy jobs, then owner B queues 1, and B starts second;
  - two `BacktestLoop`s on one database never hold more than `BACKTEST_SLOTS` RUNNING jobs;
  - an owner never has two RUNNING jobs;
  - aging lets A in after 60 s under steady light load.
  - Load test MU IT8.
- **Permanent.** The 1 h window and the 60 s are tunable values.

### B5. Per-owner limits

- **Need.** External users with one shared machine (P29). Today only 3 queued and 1 running per owner exist.
- **Class.** Cost guarantee (CPU per owner), protecting the other users' waits.
- **Fix and owning layer.** *edge-bff `submit` (`BacktestStore.submit`), under the owner advisory lock it already takes.*
  - Two new limits, each 0 = off by default, so the one owner of today is not limited:
    - `BACKTEST_JOBS_PER_DAY` (count of the owner's jobs with `created_at` since 00:00 WIB);
    - `BACKTEST_COMPUTE_SECONDS_PER_DAY` (`Σ duration_ms`; reused jobs count 0).
  - Both are read from `backtest_jobs` through the existing `(owner_key, created_at)` index. No new table is needed, and
    the multi-tab `usage_ledger` of MU can replace this later.
  - The limits and today's use go in `catalog.limits` and a new `GET /api/v1/backtests/usage`.
  - The refusal is 429 `BACKTEST_DAILY_LIMIT`. Its four parts (AGENTS.md "Gates and evidence"):
    - the rule shown before acting (`usage` and `catalog.limits`);
    - how to pass it (wait until 00:00 WIB, or use fewer stocks or switch sensitivity off to spend less compute);
    - one right and one wrong example in CONTRACT section 11;
    - a message naming the limit, the use and the reset time.
  - Values per user class are the user's decision (D-R2).
- **Covers.** Totals per day. **Does not cover** previews: their in-flight cap is 1 per owner, and a per-minute cap
  follows only if logs show abuse.
- **Risks and cost.** A wrong value blocks users; ship off by default and measure. No infrastructure cost.
- **Verification.** `test_backtest.py`: the refusal at the limit with the four parts; reused jobs not counted; the reset at
  00:00 WIB. Page toast text through `toastError`.
- **Permanent.** The values are product settings.

### B6. Shared result reuse (exact)

- **Need.** The engine is deterministic: a second identical request should cost no compute and finish at once. This is
  most useful under bursts on templates and popular tickers, and for an owner who re-runs.
- **Class.** Cost and latency through deduplicated computation.
- **Fix and owning layer.**
  - *Worker `/v1/validate`* answers a new `request_key` = sha256(canonical request + `engine_version` +
    `registry_version`), the request hash without the data version. *edge-bff* stores it on the job row.
  - *edge-bff, at hand-over.* `context.reuse` lists up to 3 FINISHED jobs of any owner with the same `request_key`,
    newest first, parts still stored. Each carries its `data_version` and its small `reuse_inputs`
    `{srd, n, skew, kurt, variants}`, written at finish from the result's `stats.all` and `meta.trials.variants`.
  - *Worker `load.ts`, a `probe` hook* after step 1, the `planned` check (`FLOW_DATA_THROUGH`) and the limits, before any
    download:
    - the planned `data_version` is `dataVersion` over the step-1 files;
    - if it is in `context.reuse`, the job ends with outcome `{kind: 'reuse', data_version, trials, deflated}`, computed
      by `ownerPart` (section 3) with the owner's prior trials: no download, no engine;
    - this is exact by I1 and I3: the same request hash means the same shared part.
  - *edge-bff ingest of a reuse.*
    - It copies the source job's parts and patches the core part's `meta.trials.{prior, this_run, total}`,
      `robustness.deflated` and `meta.duration_ms`. These are JSON field assignments; the numbers come from the worker's
      core.
    - It stores the parts and records the trials from `variants` exactly as for a fresh run.
    - It marks the job `reused_from` (internal, never shown to another owner).
  - *Optional in-flight coalescing.* Do not claim a QUEUED job whose `request_key` equals a RUNNING job's. It waits for
    that job, then hits. If that job fails, the waiting job runs.
  - *Stage B, at submit*, needs B7: with grant-free planning, `/v1/validate` also answers the planned `data_version`, and
    edge-bff finishes a hit at submit with no queue and no slot, through a stateless `POST /v1/trials` that runs
    `ownerPart`.
- **Covers.** Identical requests across and within owners, exactly. **Does not cover** near-identical requests: those are
  new variants, and B2 makes them cheap.
- **Risks and cost.**
  - Privacy: a fast answer reveals that *someone* ran the identical request on the same data; no content is revealed (as
    in 6d.2). Whether to share across owners or only within an owner is D-R1.
  - Complexity: a migration with columns `request_key`, `reuse_inputs jsonb`, `reused_from` and an index
    `(request_key, data_version) WHERE state='FINISHED'`; a new contract outcome.
  - Value is UNKNOWN until measured. PROPOSED: ship `request_key` first and log its duplicate share for 2 weeks; build the
    rest when the share is at least 10 % or bursts appear.
  - Every worker deploy changes `engine_version` (FACT), so hits never cross deploys. That is conservative, and correct.
- **Verification.**
  - Core (`result.test.ts`): the `ownerPart` parity (section 3).
  - Worker (`run.test.ts`): a probe hit makes 0 downloads (`fake-terminal.mjs` counters) and gives the same `trials` and
    `deflated` as a fresh run.
  - edge-bff (`test_backtest.py`): a reused job's `/result` bytes, decoded, equal a fresh job's for the same owner and
    prior, with `duration_ms` zeroed; owner B's `backtest_trials` rows equal those of a fresh run; no `reused_from` in any
    answer.
- **Permanent**, once measured to be worth it.

### B7. Grant-free planning in terminal-api (dependency; owned by the terminal-api layer)

- **Need.** Every warm job and preview takes one grant per ticker under one lock (1.4.3), plus an audit row. INFERENCE: at
  200 users at once that is about 10.6 M grants a month, 33.5/s on average in busy hours, against about 38/s of capacity.
- **Class.** Shared gate capacity and audit volume.
- **Fix and owning layer.**
  - *terminal-api `app/main.py`.* `POST /api/terminal/v1/plan {tickers: [...], datasets, packs: true}`, gateway key only:
    - per ticker, the same file choice as `/bundle` (one shared selection function), with sha256, bytes, rows,
      year/pack, `data_through` and `generated_at`;
    - no URL, no grant, no quota, no audit row, like `/manifest` today (`BACKTEST_END_TO_END.md:334`).
  - *Worker `load.ts`.* Plans with one `/plan` call. It asks `/bundle` only for tickers with a file it does not hold.
- **Covers.** Warm runs and previews make no grants (only cache misses do). The planned `data_version` is exact before the
  queue (B6 stage B). **Does not cover** the Terminal page's own grants (the per-user identity, P31).
- **Risks and cost.**
  - The access log would no longer record each *use* of cached files by the worker, only each download. Whether the
    audit must record uses is UNKNOWN (D-R4; data terms, MU2).
  - A small terminal-api change outside the backtest; its tests must show `/plan` equals `/bundle` without the URLs.
- **Verification.** terminal-api pytest (`/plan` against `/bundle` for packs and yearly files; refused without the gateway
  key). Worker `load.test.ts`: a warm job makes 0 `/bundle` calls. Count access-log rows per job before and after.
- **Permanent.**

### B8. Pre-warm per publication

- **Need.**
  - FACT: the publisher runs at 07:30 and 19:00 WIB, and every daily run changes each traded ticker's price pack
    (`BACKTEST_END_TO_END.md:162-166`).
  - INFERENCE: the first run of each popular ticker after a publication is cold: 1.3 s single and about 7 s for a 12-stock
    flow portfolio (FACT cold times, README `:429-431`), just when users come back in the evening.
- **Class.** Shared warm cache per publication.
- **Fix and owning layer.** *Worker `catalog.ts` `ByPublication` and the threads.*
  - When `finished_at` changes, each replica downloads and decodes (B2) IHSG and the top-N tickers by use.
  - The worker counts tickers per job in memory, or edge-bff passes a hint list built from the last 7 days of
    `backtest_jobs`.
  - N = `BACKTEST_PREWARM_TICKERS` (PROPOSED 50). It runs on idle thread time and stops when a user job arrives.
- **Covers.** Cold waits after a publication for popular stocks. **Does not cover** rare stocks.
- **Risks and cost.**
  - Bucket egress is free.
  - About 50 grants per publication per replica (none with B7).
  - CPU tens of vCPU-seconds per publication, under USD 0.01 a month (INFERENCE).
  - Memory inside the B2 budget.
  - With M250 still open, a pre-warm during a publisher run can meet `DATA_INTEGRITY`. Pre-warm only after
    `finished_at` changes, which is after the run.
- **Verification.** Log `prewarm` with tickers, bytes and ms. Dev: the first job after a publication for a pre-warmed
  ticker runs at warm speed.
- **Permanent.**

### B9. Previews: debounce, pool, optional result cache

- **Need.**
  - FACT: the page asks a server preview on each settings change, latest wins, with no debounce (`preview.ts:1-15`;
    `signals.ts:111-117`; no debounce found in `apps/edge-bff/backtest/src`).
  - FACT: each preview takes grants and a preview thread.
- **Class.** Load shaping.
- **Fix and owning layer.**
  - *Page `signals.ts`/`preview.ts`.* A 300 ms debounce before asking. The Screener design uses 350 ms (6d.6). No markup
    or CSS change (1:1 rule).
  - *Worker.* P threads (B3) and B2.
  - *Optional worker preview-result LRU* keyed by (canonical preview request, planned `data_version`, versions), exact
    after B7. Build it only if logs show repeats (the page already caches answers per settings key).
  - *edge-bff.* Latest wins per (`owner_key`, page) instead of per owner, as for the Screener (6d.6). Keep the existing
    `client_order`.
- **Covers.** Preview rate and latency. **Does not cover** previews in single mode, which the browser computes.
- **Risks and cost.** 300 ms more before a preview answer while typing. None for infrastructure.
- **Verification.** Page vitest (one request after a burst of edits); `test_backtest.py` (two pages of one owner do not
  replace each other).
- **Permanent.**

### B10. Deploy safety and failure handling

- **Need.** FACT: no healthcheck on the worker, and SIGTERM kills running jobs (1.1). With users all day, every CLI deploy
  fails running jobs (`WORKER_LOST`).
- **Class.** Availability.
- **Fix and owning layer.**
  - *Railway and `.railway/railway.ts`.*
    - healthcheck `/health`;
    - a memory limit (PROPOSED peak × 1.5 from B3's test), so page cache is reclaimed (1.3);
    - drain time as Railway allows (UNKNOWN: the name and maximum of Railway's draining or overlap setting; check its
      documentation).
  - *Worker `server.ts`.* On SIGTERM, refuse new jobs (409 `BUSY` with `draining`), finish running jobs up to
    `BACKTEST_DRAIN_SECONDS` (PROPOSED 60, above the p99 job), then exit.
  - *Decision D-R3.* Re-queue once a job the worker lost *before* it reported FINISHED (404 `UNKNOWN_JOB` after a
    restart). The trials are written only by `finish`, under the lease (FACT, `backtest.py:575-602`), so a re-run cannot
    double-count. This changes D-B1 ("never resubmits", `CONTRACT.md:690`), which is why it is a decision.
- **Covers.** Deploys and restarts. **Does not cover** a lost replica while R = 1 (B12).
- **Risks and cost.** Deploys take up to 60 s longer. No running cost.
- **Verification.** Dev: a deploy during a 12-stock job ends it FINISHED. `server.test.ts`: the drain refuses new jobs and
  finishes running ones.
- **Permanent.**

### B11. Result relay and storage

- **Need.**
  - FACT: edge-bff parses and splits every result in Python on the one public process (`backtest.py:871-899`). A result
    can be up to 32 MiB of JSON (README `:222`).
  - FACT: results stay 30 days in Postgres at about 136 KB per job (CAP 2.3).
  - FACT: single mode merges the parts on every read (`:1145-1150`).
- **Class.** Shared-entry CPU and storage cost.
- **Fix and owning layer.**
  - *Worker `compute.ts`.* It splits on the thread and answers the parts (gzip each, sha256) with a small JSON head
    (versions, trials, lineage). *edge-bff* validates the head and stores the bytes without parsing them. The CONTRACT
    section 9 part format stays.
  - *edge-bff ingest.* Stores the single-mode merged part once (`BACKTEST_END_TO_END.md:723-724`).
  - *Retention.* Keep the newest `BACKTEST_RESULTS_PER_OWNER` (PROPOSED 50) per owner and no more than 30 days (D-R6).
    Moving results to a bucket (10× cheaper per GB) needs edge-bff bucket credentials, a separate decision.
- **Covers.** edge-bff CPU per job; storage growth. **Does not cover** the result size itself.
- **Risks and cost.** A contract change between worker and edge-bff (section 8 of CONTRACT); older results pruned earlier.
- **Verification.** `test_backtest.py`: the stored parts equal those of today's split; the retention cap.
- **Permanent.**

### B12. Horizontal scale-out (later: availability, or more than about 10,000 jobs an hour)

- **Need.**
  - FACT: jobs and results are in worker memory.
  - FACT: Railway has no sticky sessions (6d.1).
  - UNKNOWN: how the private network spreads connections over the replicas of one service (6d M-U2).
- **Class.** Job affinity versus stateless runs.
- **Option (a) PROPOSED: explicit worker origins.**
  - Fix and owning layer:
    - `BACKTEST_WORKER_URLS` lists origins, each with its K. The config rule (`config.py:105-108`) accepts
      `backtest-worker(-[a-z0-9]+)?.railway.internal`.
    - Each origin is a Railway service from the same image.
    - The B4 `slot` value names origin and thread, so the follower calls the origin that holds its job.
  - Covers: deterministic affinity, with no DNS unknowns.
  - Risks and cost: one more service to deploy; about USD 3-5 a month idle (INFERENCE, 0.3 GB resident).
- **Option (b): a stateless streamed run.**
  - Fix and owning layer: `POST /v1/run` keeps the request open and streams progress lines, then the result. Cancel is
    closing the connection, the mechanism previews already use (`server.ts:222-229`). The worker keeps no job and no
    result, and any replica serves any job.
  - Covers: the cleanest scale-out.
  - Risks: a rewrite of CONTRACT sections 8-9 and the loop's dispatch, follow and ingest. It needs M-U2 settled so that
    connections spread.
- **Verification.** Option (a): two services on dev, with each job's calls reaching its origin (logs). Option (b): a
  replica restart mid-stream gives `WORKER_LOST` or a re-queue (D-R3).
- **Permanent.**

---

## 5. Capacity and waits (INFERENCE; model in `mu_runtime/bt_queue.py`)

- **Model.** M/M/c with a variability correction, Poisson arrivals.
- **Users and arrivals.** U users at once each submit one job every Z seconds: Z = 60 s is a busy user, Z = 120 s the
  central case.
- **Slot occupancy per job**, a mix of 70 % single and 30 % portfolio runs:
  - T0, today: 3.6 s, from the FACT e2e times and the 2-s poll step;
  - T1, B1: 1.9 s;
  - T2, B1 and B2: 1.0 s. INFERENCE: single 0.5 s compute + 0.15 s overhead; 12-stock flow portfolio about 1.5 s + 0.2 s.
- These are to be replaced by the measured `c_job` (section 7).

**Jobs per hour per replica at 70 % use:** T0 about 700; T1 about 1,300; T2 about 2,500 per thread, so K = 2 about 5,000,
K = 4 about 10,000, K = 8 about 20,000.

**p95 queue wait** (time before compute starts):

| Users at once | Z | T0 today (K = 1) | T2, K = 1 | T2, K = 2 | T2, K = 4 | T2, K = 8 |
|---|---|---|---|---|---|---|
| 10 | 60 s | 14 s (ρ 0.60) | 1.4 s | 0 s | 0 s | 0 s |
| 10 | 120 s | 5.8 s | 0.6 s | 0 s | 0 s | 0 s |
| 50 | 60 s | saturated (ρ 3.0) | 16.9 s | 1.4 s | 0 s | 0 s |
| 50 | 120 s | saturated (ρ 1.5) | 3.6 s | 0.2 s | 0 s | 0 s |
| 200 | 60 s | saturated | saturated | saturated | 3.9 s (ρ 0.83) | 0 s (ρ 0.42) |
| 200 | 120 s | saturated | saturated | 8.2 s | 0.3 s | 0 s |

**Previews**, with half the users editing portfolios and one server preview per 10 s each:
- service time 3.0 s today against 0.3 s with B2;
- one preview thread with today's 3 s saturates already at 10 users;
- with B2: P = 1 holds 10 users (p95 0.4 s); P = 2 holds 50 users (0.3 s); P = 4 holds 200 users (0.7 s);
- the B9 debounce lowers the rate further.

**End to end for a user, warm, no queue** (INFERENCE, B1 and B2): single about 1.3-1.6 s (today 5.5-5.9 s FACT); 12-stock
flow portfolio about 2.0-2.5 s (today 10.8 s FACT). Cold after a publication without B8: plus downloads, up to 6 s for 28 MB.

**Recommended sizing** (PROPOSED; one replica, set from section 7 measurements):

| Users at once | Job threads K | Preview threads P | Replicas |
|---|---|---|---|
| up to 10 | 2 | 1 | 1 |
| up to 50 | 4 | 2 | 1 (2 if the availability floor D-R7 says so) |
| up to 200 | 8 | 4 | 1-2, with B7 required |

---

## 6. Cost per month (INFERENCE; model in `mu_runtime/bt_cost.py`; Backtest only)

**Assumptions:**
- 4 busy hours a day, 22 trading days, Z = 120 s;
- server previews: half the users edit portfolios, half of the time, one preview per 15 s;
- CPU per job: today 2.0 vCPU-s, proposed 0.7 with 10 % reuse; per preview: today 1.6, proposed 0.25;
- RAM, today: 1.1 GB resident all month (two per-thread gzip caches, FACT 0.5-0.6 GB in E2E hours);
- RAM, proposed: peak 0.1 + K × 0.3 + 0.8 GB in busy hours and 0.3 GB otherwise (B3 idle trim);
- results: 136 KB per job (FACT average); one 150 KB view per job.

| Users at once | Jobs / previews a month | CPU USD (today / proposed) | RAM USD (today / proposed) | Results in Postgres: 30 days today / per-owner cap 50 (B11) | Egress USD | Total USD (today's design / proposed) |
|---|---|---|---|---|---|---|
| 10 | 26,400 / 52,800 | 1.06 / 0.23 | 11.0 / 4.5 | 3.6 GB 0.54 / 0.2 GB 0.03 | 0.20 | 12.8 / **4.9** |
| 50 | 132,000 / 264,000 | 5.30 / 1.15 | 11.0 / 5.2 | 18 GB 2.69 / 1.0 GB 0.15 | 0.99 | 20.0 (cannot serve it) / **7.5** |
| 200 | 528,000 / 1,056,000 | 21.2 / 4.6 | 11.0 / 6.7 | 72 GB 10.8 / 4.1 GB 0.61 | 3.96 | 46.9 (cannot serve it) / **15.8** |

**Notes:**
- Add about USD 3-5 a month for a second worker replica or service, if D-R7 asks for one.
- **Grants without B7:**
  - 0.53 M, 2.65 M and 10.6 M a month for 10, 50 and 200 users: 1.7, 8.4 and 33.5 grants/s in busy hours;
  - each is a Postgres transaction under one lock plus an access-log row in terminal-api;
  - at 200 users this nears the about 38/s ceiling, and the access log grows by about 10 M rows a month;
  - B7 removes nearly all of them.
- **Reading:** Backtest stays a small fixed cost. The levers are resident RAM (B2 and B3: small byte caches, idle trim)
  and retention (B11). CPU is cheap: USD 0.0000077 per vCPU-second (6d.1). Waiting time is bought with threads, not
  replicas.

---

## 7. Scaling triggers and what to measure (PROPOSED)

| # | Signal (source) | Threshold | Action |
|---|---|---|---|
| BT1 | Queue wait: `started_at - created_at` of `backtest_jobs`, p95 over 15 min in busy hours | > 5 s | K + 2, up to the vCPU and RAM check of BT3 |
| BT2 | Preview wait: the worker log `preview_wait_ms` (new), p95 | > 1 s | P + 1 |
| BT3 | Worker RSS (`railway metrics`) | > 70 % of the memory limit | Lower the decoded cache or the decode budget, or raise the limit |
| BT4 | `BUSY` answers or slot saturation (all `BACKTEST_SLOTS` RUNNING) | > 5 % of busy minutes | As BT1 |
| BT5 | terminal-api grant time (edge-bff and worker logs), `/bundle` p95 | > 1 s | B7 if not done |
| BT6 | Duplicate share of `request_key` among submitted jobs | ≥ 10 % or bursts | Build B6 |
| BT7 | `backtest_results` size (`pg_total_relation_size`) | > 10 GB | B11 retention, or a bucket |
| BT8 | K ≥ 8 and BT1 still firing, or an availability floor decided | — | B12 option (a) |

**Measure first:**
- per-phase times (`loading`, `signals`, `sensitivity`, `monte_carlo`, decode against download) in `job_end`;
- `c_job` and `c_preview` per class;
- RSS per thread at K = 1, 2, 4;
- the e2e times of B1;
- the duplicate share of `request_key`.

All of these come from a multi-owner load test, using the private-network harness of CAP §6 with synthetic `owner_key`
values driven through edge-bff's store, no accounts needed. Results go to `verification/backtest/` with deployment IDs,
as the house requires.

---

## 8. Exact changes and tests

| Layer | File | Change (proposal) |
|---|---|---|
| Core (shared) | `apps/edge-bff/backtest/src/core/robustness.ts` | `deflationInputs(st)`, `ownerPart(inputs, variants, prior)` (B6). `result.ts` uses them (one code path) |
| Core | `apps/edge-bff/backtest/src/core/contract.ts` | `JobContext.reuse?`; job outcome `reuse`; `Limits` adds `jobs_per_day` and `compute_seconds_per_day` (B5, B6) |
| Worker | `apps/backtest-worker/src/server.ts` | job `Map`, K and P threads, hold, ack and `DELETE`, `wait_ms` long-poll, drain, `/health` slots and `draining` (B1, B3, B10) |
| Worker | `src/compute.ts` | thread pool, per-thread kill, idle trim, worker-side split of the result parts (B3, B11) |
| Worker | `src/terminal.ts` | decoded-series LRU after `inflateVerified`; the byte cache made small (B2) |
| Worker | `src/load.ts` | `probe` hook after `planned` and the limits; decode-memory admission before step 2; `/plan` use (B3, B6, B7) |
| Worker | `src/run.ts`, `src/validate.ts` | `request_key` from validate; reuse outcome; phase timings in the `job_end` log (B6, section 7) |
| Worker | `src/catalog.ts` | pre-warm on a new publication (B8) |
| Worker | `src/config.ts`, `README.md` | `BACKTEST_JOB_THREADS`, `BACKTEST_PREVIEW_THREADS`, `BACKTEST_DECODED_CACHE_BYTES`, `BACKTEST_DECODE_BUDGET_BYTES`, `BACKTEST_RESULT_HOLD_SECONDS`/`_BYTES`, `BACKTEST_IDLE_THREAD_SECONDS`, `BACKTEST_DRAIN_SECONDS`, `BACKTEST_PREWARM_TICKERS` |
| edge-bff | `apps/edge-bff/app/backtest.py` | wake event; async follower with long-poll; K followers on slots; fair claim with aging; daily limits; reuse (context, copy and patch, trials); stored merged single part; ingest of pre-split parts; latest wins per (owner, page); retention (B1, B4, B5, B6, B9, B11) |
| edge-bff | `apps/edge-bff/app/config.py` | `BACKTEST_SLOTS`, `BACKTEST_WORKER_URLS` (later), the limits, `BACKTEST_REUSE` (`off`, `owner` or `all`, D-R1), the retention cap |
| Database | new `database/migrations/<date>_edge_bff_backtest_multiuser.sql` | `slot`, `request_key`, `reuse_inputs jsonb`, `reused_from`; unique `(slot) WHERE state='RUNNING'`; `(request_key, data_version) WHERE state='FINISHED'`; `$verify$` block; grants unchanged (jobs already have UPDATE). `DATABASE_SCHEMA.md` is not hand-edited (D-D2) |
| Page | `apps/edge-bff/backtest/src/run.ts`, `signals.ts`/`preview.ts` | status wait or short early polls (B1); preview debounce (B9). No markup or CSS change |
| terminal-api (dependency) | `apps/terminal-api/app/main.py`, tests | `POST /plan` sharing the `/bundle` file selection (B7) |
| Railway | `.railway/railway.ts`, `RAILWAY_CHANGELOG.md` | worker healthcheck, memory limit, variables; then `railway config pull --force` and `config plan` |
| Records | `CONTRACT.md` sections 2, 3, 8, 9, 11, 12 (new D-R decisions); `BACKTEST_END_TO_END.md` sections 7, 8, 11.1, 15; `ERRORS_AND_SOLUTIONS.md` entries for FIFO, poll latency and deploy loss | per AGENTS.md |

**Tests:**

| # | Test | Locks |
|---|---|---|
| W1 | `run.test.ts`: N jobs run concurrently on K threads give the same bytes as sequential runs (`duration_ms` zeroed) | I1 under B3 |
| W2 | `run.test.ts`: cold, warm, decoded-hit and the A-B-A order give equal bytes; the debug buffer hash is unchanged | I1, I2 under B2 |
| W3 | `server.test.ts`: K running, `BUSY` at K + 1, hold, ack, eviction (410), long-poll on the end and on the timeout, drain | B1, B3, B10 |
| W4 | `load.test.ts`: a reuse hit makes 0 downloads and 0 decodes; refusals (`FLOW_DATA_THROUGH`, limits) are unchanged before the probe; admission waits instead of failing | I6, B3, B6 |
| W5 | `result.test.ts`: `ownerPart` parity with `buildResult` for random priors, NaN skew included | Section 3 |
| E1 | `test_backtest.py`: fair claim (A × 3 heavy, then B: B second), aging, slots across two loops, 1 RUNNING per owner | B4, I4 |
| E2 | `test_backtest.py`: a reused result equals a fresh one per owner; trials rows equal; `reused_from` never exposed; `BACKTEST_REUSE=owner` blocks cross-owner hits | B6 |
| E3 | `test_backtest.py`: `BACKTEST_DAILY_LIMIT` refusal with the four parts; reused jobs not counted; reset at 00:00 WIB | B5 |
| E4 | `test_backtest.py`: pre-split parts stored byte-equal to today's split; the merged single part; retention cap | B11 |
| T1 | terminal-api: `/plan` equals `/bundle` without URLs; gateway only; no access-log row | B7 |
| L1 | Dev load test (section 7) with synthetic owners: p95 waits, RSS, grants per second | sections 5, 6 |

---

## 9. What stays untouched

- **The engine and every formula:** `engine.ts`, `conditions.ts`, `signals.ts`, `flow.ts`, `stats.ts`, `ledger.ts`, the
  computations in `result.ts`, and the indicator formulas (`registry_version`). `ownerPart` is a refactor of existing calls.
  Any edit to a core file or a worker `src/*.ts` changes `engine_version` (FACT), which is intended.
- **Hashes:** lineage key, variant hash and request hash definitions (`hash.ts`); `data_version` (`datafile.ts`).
- **Trial semantics (K3):** per owner and lineage, latest Sharpe, `recorded_seq`, never reset.
- **Data sources:** the published files, terminal-api `/bundle`, the publisher (B7 adds a route and changes none), and no
  PostgreSQL market data (I5).
- **The page:** markup, CSS and render (the 1:1 rule).
- **AI Orc and the Monitor tab.** The Terminal page's own data path (P31 per-user identity) belongs to the terminal area.

---

## 10. Decisions for the user

| Id | Question | Options | Recommendation |
|---|---|---|---|
| D-R1 | Reuse results across owners? | (a) off; (b) the same owner only; (c) any owner | (b) first: no privacy question at all. (c) after BT6 shows value |
| D-R2 | Per-owner daily limits for external users | values per user class: jobs a day, compute seconds a day | off until P29 numbers exist; then set with the four-part refusal |
| D-R3 | Re-queue a job lost before it finished (changes D-B1) | (a) keep `WORKER_LOST`; (b) re-queue once | (b): trials are written only on finish, so it is safe |
| D-R4 | Must terminal-api's audit record each *use* of cached data by the worker, or each download? | use / download | download (B7). Depends on the data terms (MU2) |
| D-R5 | Decoded cache without re-reading the bytes (changes the CONTRACT section 2 rule) | (a) keep re-verifying bytes on every use; (b) trust the thread's own decoded copy | (a) now; (b) only if measured worth more than 0.1 s per job |
| D-R6 | Result retention | 30 days (today) / newest N per owner and at most 30 days / a bucket | newest 50 per owner and at most 30 days |
| D-R7 | Availability floor of the worker for external users | 1 replica with drain / 2 workers (B12 a) | 1 with drain now; 2 at an external launch |

## 11. Unknowns

| # | Unknown | Check |
|---|---|---|
| U-B1 | Per-phase CPU of a warm run (decode against engine) | phase timings in `job_end` (section 7) |
| U-B2 | RSS per extra thread and the decode peak for the heaviest planned run | B3's memory test |
| U-B3 | Railway's draining and overlap settings for a deploy | Railway documentation, then a test deploy |
| U-B4 | How the private network spreads connections over replicas (6d M-U2) | DNS answers and per-replica logs (6d.11) |
| U-B5 | The real duplicate share of identical requests | `request_key` logging (BT6) |
| U-B6 | Real users at once and runs per user (P29, MU5) | the user's numbers, then logs |
| U-B7 | The cause of the 2.05 GB hour on 2026-10-27 08:00 UTC | per-minute metrics of that hour, or a repeat of the 12-stock cold run at K = 1 |

## 12. Order of work (PROPOSED; nothing runs before the user's "go")

1. **Measure** (section 7 instrumentation only: phase timings, `request_key` logged, preview wait).
2. **B1 + B2.** Biggest latency win; no contract change except the long-poll.
3. **B3 (K = 2, P = 2) + B4 + B10.** Throughput, fairness, deploy safety.
4. **B5** off by default, **B9**, **B11**.
5. **B8**, then **B6** when BT6 fires; **B7** with the terminal-api owner (before about 50 portfolio editors at once).
6. **B12 (a)** when BT8 fires or D-R7 asks for it.

Each step changes `engine_version` only through code. Each step follows the AGENTS.md workflow: tests, the dev E2E outside
the M250 publisher windows, the changelogs, and deployment SUCCESS read back.

## Evidence index (read-only)

- Code at `main` `3847fc4`, as cited by file:line.
- `npx -y @railway/cli@5.71.0 status --json`, saved without secrets as `scratchpad/mu_runtime_status.json`.
- `metrics -s backtest-worker --since 3d --cpu --memory --raw --json`, saved as `scratchpad/mu_bt_metrics.json`.
- `pgq2.py`: `pg_stat_user_tables` for `edge_bff.backtest_*`; `pg_roles` connection limits (`edge_bff_login` 20,
  `terminal_api_login` 20); `pg_stat_activity` per role.
- Models: `scratchpad/mu_runtime/bt_queue.py` (waits) and `scratchpad/mu_runtime/bt_cost.py` (cost).
