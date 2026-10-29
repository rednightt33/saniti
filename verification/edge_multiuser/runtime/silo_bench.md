# Silo benchmark: one copy per user, or a shared pool (Screener, Backtest, Terminal), measured

Question (user, 2026-10-28): "jika screener, backtest, dan terminal adalah idle, dalam artian ketika user tidak mengakses
maka tidak ada biaya, we might as well to create more the same service. Jadi misalkan ada service, kita duplicate service
yang sama untuk serve user ID 123, kemudian kita duplicate lagi service yang sama untuk serve user 456 dan seterusnya.
Coba saja di explore pakai benchmark yang best practice." The user's priorities are cost, speed (users must not wait
long) and accuracy. AI Orc is out of scope.

This file holds the numbers. It measures what a fresh per-user copy costs to start and to serve, compares that with a
warm shared copy, and prices both models for 10, 50 and 200 external users. The research companion,
`/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/mu_runtime/silo_research.md`, covers
Railway documentation, best practice and the blockers. Sections are cited below as "research §x".

**Scope.** This was a read-only task. No repository file changed, Railway was not mutated (no service was created, slept,
scaled or deployed) and nothing was written to the database. Railway was read once (`railway logs`, read-only, §5).
Every script and raw output is under
`/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/mu_runtime/bench/` (`scripts/`,
`raw/`, `data/`; `data/` holds market data and stays local).

**Labels.**
- FACT: measured here (file in `bench/raw/`), or cited by file:line or URL.
- INFERENCE: computed or concluded from FACT inputs.
- PROPOSED: a recommendation.
- UNKNOWN: not established.
- ASSUMPTION: a usage-profile input that the user's numbers (P29) replace.

---

## 0. Results in one screen

1. **Idle copies cost nothing on Railway only when they sleep. Then each new session pays the copy's cold start.**
   - FACT (docs): "A slept service accrues no compute charges".
   - FACT, measured here: a fresh Screener copy needs **15.6-20.1 s** of data work on one thread (9.5-11.9 s on four
     threads) before its first answer. That is real code on the real full history: decode, verify, build, and
     pre-warm all 53 indicators (64,220 tails).
   - The full wait is that plus the Railway wake (≈1 s, FACT, §5) and the 11.8 MB download (2.5-5 s, INFERENCE).
     **≈ 20-27 s on one thread, ≈ 14-19 s on four.**
   - A warm shared copy answers the same first screen in **3-13 ms** (default or preset) or **0.14-0.26 s** (custom).
     FACT, measured.
2. **A Backtest copy starts fast but runs cold.**
   - FACT: listening in 0.26-0.32 s, 117-121 MB after its catalog.
   - The page waits **≈ 3.6-4.0 s** for the catalog after a wake (INFERENCE), against ≈ 0.25 s from a warm pool
     (`BACKTEST_END_TO_END.md` §17).
   - Every session's first jobs download their files again: +0.8 s for a single stock, +1.5 s for a 12-stock flow
     portfolio at worker level (FACT, dev numbers).
3. **A Terminal copy gains nothing and cannot sleep.**
   - The browser already downloads straight from the bucket.
   - terminal-api holds a database pool, which keeps a service awake (docs).
   - Each copy takes at least 2 of the 20 connections the `terminal_api_login` role allows (FACT).
4. **Cost (INFERENCE, light profile, §6).**

   | Model | 10 users | 50 users | 200 users |
   |---|---|---|---|
   | SILO, Screener and Backtest per user, terminal-api shared | USD 3.5 | USD 12.7 | USD 48.3 |
   | SILO, all three per user | USD 17.3 | USD 86 | USD 346 |
   | POOL, 24/7 (2 Screener replicas) | USD 15.8 | USD 16.0 | USD 17.9 |
   | POOL, Serverless, kept awake 14 h on trading days | **USD 7.2** | **USD 7.4** | **USD 9.2** |
   | POOL, Serverless, asleep whenever idle | USD 3.5 | USD 4.4 | USD 6.4 |

   - SILO beats a 24/7 pool only below about 26-65 light users.
   - A pool that sleeps is at least as cheap at every size.
   - The keep-awake pool also has zero cold waits.
5. **Every SILO session waits through a cold start; a pool's sessions do not.**
   - SILO: 100 % of sessions pay the cold start (INFERENCE).
   - POOL, Serverless without keep-alive: 26.6 %, 2.1 % and 0.5 % of sessions (10, 50, 200 users; Monte Carlo, §6.3).
   - POOL kept awake in trading hours: 0 %.
6. **SILO repeats work the pool does once (INFERENCE, §6.4).**
   - Snapshot builds: 472, 2,363 and 9,450 a month, against 84-124.
   - Downloads: 5.6, 28 and 111 GB a month, against 1-1.5 GB.
   - Start-up CPU: 2.7, 14 and 55 vCPU-hours, against 0.5-0.7.
   - A shared result cache across users does not exist in SILO. The CPU of a re-run is cheap; the time is not:
     0.14-0.26 s against 8-16 ms per repeated custom screen (FACT).
7. **Railway caps SILO before 50 users in one project.**
   - 100 services a project, 28 used (research §2.3, §4.3).
   - 25 new services a day for a new account.
   - The `terminal_api_login` role allows 20 connections.
   - The workers' grant quota (default 300 MB/day) would carry 265 MB/day at 10 users and 5.3 GB/day at 200.
8. **PROPOSED: pool with Serverless, plus per-user fairness inside it (owner lanes, quotas, round-robin claim).**
   - Keep it awake from about 08:10 to 22:10 WIB on trading days; it sleeps at night and on weekends.
   - Dedicated copies only as a paid or heavy-user exception, for the Backtest: about USD 4 per user-month always on.
   - This matches research §5 and the AWS "bridge" pattern.

---

## 1. Method

| Item | Value | Label |
|---|---|---|
| Machine | Sandbox, 4 vCPU Intel Xeon @ 2.10 GHz, 16 GB, node v22.22.0, Python 3.13 | FACT |
| Contention | Other agents' processes (playwright tests, builds) shared the 4 CPUs. Load average per run is in each raw file (`load_start`, `load_end`): 0.9-5.1. Wall times are upper-bound-like. Process CPU time is the steadier cost figure. Railway's vCPU speed against this Xeon is UNKNOWN | FACT / UNKNOWN |
| Harness | `bench/scripts/run_proc.mjs`: spawns a fresh process. Wall time runs from spawn to its `ready` line. RSS is sampled from `/proc/<pid>/status` every 20 ms (VmRSS; VmHWM = peak) | FACT |
| Code under test | Read-only imports of the repository: `apps/edge-bff/backtest/src/core/datafile.ts` (`inflateVerified`, `priceSeries`, `dataVersion`), `apps/edge-bff/screener/src/core/{registry,metrics}.ts` (`startParams`, `resolveIndicator`, the one `series()` path, `SeriesCache`, `tailLength`), `apps/edge-bff/terminal/src/calc/indicators.ts` through `Calc`, loaded with `apps/backtest-worker/loader/register.mjs`. The real `apps/backtest-worker` process (the Dockerfile CMD) with `apps/backtest-worker/tests/fake-terminal.mjs`. The work-in-progress `apps/screener-worker/src/snapshot.ts` | FACT |
| Source state | HEAD moved from `80af819` to `7807d2b` during the runs. `metrics.ts` changed at 19:45 UTC (additive fields; the `series()` and `tailOf` path is unchanged). The first screener batch ran 19:34-19:47 UTC, the second at about 19:52 UTC; both batches agree (§2.1). Hashes of the WIP worker files: `bench/raw/ws_snapshot_sources.txt` | FACT |
| Data | The full price history dump of the audit, `scratchpad/audit/benchmark/data/price_full.json`: 845 tickers (844 stocks + IHSG), 1,330,722 rows, 2018-01-02..2026-10-27 (AUDIT.md PERFORMANCE EVIDENCE 11.2). It was turned into the proposed `price` xsection file (AUDIT.md 6.5: columns `t,d,o,h,l,c,v`, `tickers` list) with the publisher's encoding (`bench/scripts/make_xsection.py`) | FACT |
| Not measured | Railway-internal timings of a Screener or Backtest copy; the single-object download rate from the `sin` bucket; whether a container's disk survives sleep (M-U7). Each is UNKNOWN; §8 lists the check | UNKNOWN |

---

## 2. (a) Screener copy: cold start, data part (download excluded)

Script: `bench/scripts/screener_cold.mts`. Run: `bench/scripts/run_screener.sh` plus the reruns. Summary:
`bench/raw/screener_summary.json`. Steps in one fresh process:
1. Read the cached bytes.
2. `inflateVerified`: size, sha256, gunzip, JSON and the column check.
3. Slice each ticker into a pack-shaped document, then `priceSeries`.
4. `dataVersion`.
5. Pre-warm every indicator of the screener registry at `startParams`, every output (53 indicators, 76 outputs), through
   `series(…, prewarm = true)`, with tails of `tailLength(130)` = 131 bars.
6. Then serve, in order:
   - a default screen, all pre-warmed: RSI(14) < 30 and close > SMA(20);
   - a 3-condition custom screen: RSI(7) < 30, close > SMA(75), and MACD(12,26,9) crossing above its signal within 4
     bars, of which two series are dynamic;
   - the same custom screen again (an LRU hit).

### 2.1 Input and results (FACT, measured)

| Input | Value |
|---|---|
| xsection `price` file (gzip -9) | 11,758,425 B. The 845 per-ticker packs total 14.22 MB (AUDIT.md 11.5) |
| Inflated JSON | 74,272,565 B (AUDIT.md 6.5 estimated 75-80 MB) |
| Rows / tickers | 1,330,722 / 845 |
| Build time of the file (Python, publisher encoding) | 27.2 s (`bench/raw/make_xsection.txt`) |

| Threads K (runs) | Spawn to ready (min / median / max) | Boot | Inflate + sha256 + parse | Slice + `priceSeries` | Pre-warm wall | Pre-warm CPU | Process CPU, spawn to served | RSS at ready | Peak RSS |
|---|---|---|---|---|---|---|---|---|---|
| 1 (6) | **15.6 / 17.1 / 20.1 s** | 0.25-0.42 s | 1.23-1.52 s | 1.54-2.09 s | 12.4-16.3 s | 13.0-16.2 s | **17.1-20.7 s** | 732-750 MB | **733-750 MB** |
| 2 (3) | **11.0 / 13.1 / 14.4 s** | 0.26-0.30 s | 1.26-1.48 s | 1.66-2.11 s | 7.7-10.5 s | 15.3-17.9 s | 19.4-22.5 s | 516-520 MB | **1,030-1,033 MB** |
| 4 (3) | **9.5 / 11.1 / 11.9 s** | 0.26-0.28 s | 1.14-1.47 s | 1.72-2.05 s | 6.2-8.0 s | 16.3-20.3 s | 20.3-25.1 s | 514-524 MB | **1,157-1,171 MB** |

- **Snapshot:** 64,220 tails (845 × 76), 0 errors, 67.9 MB of tails in every run (FACT).
- **Idle RSS of an awake copy** (FACT, n = 1 each):
  - K = 1: 732 MB for at least 30 s after ready, then 358 MB at 60 s (V8 returned memory).
  - K = 2 and K = 4: 521-523 MB at 5, 15 and 30 s (the worker threads' heaps are gone).
  - Steady planning value: **0.36-0.52 GB**, with the first minute at about 0.73 GB.
- **Threads trade wall time for memory.** Going from K = 1 to K = 4 cuts the median wait by 35 % (17.1 → 11.1 s). It
  raises the median total CPU by 20 % (18.7 → 22.3 vCPU-s) and the median peak RSS by 58 % (0.74 → 1.17 GB). Each
  pre-warm thread receives a copy of its tickers' bars.

**Serving from the fresh copy** (FACT, all 12 runs):

| Request | Time | CPU |
|---|---|---|
| Default screen (lookups of pre-warmed tails), first | 4.1-13.4 ms | — |
| Default screen, again | 3.1-7.9 ms | — |
| 3-condition custom screen, first (2 dynamic series × 845 tickers) | **143-256 ms** | 153-270 ms |
| The same custom screen again (series LRU hit) | **7.6-15.7 ms** | — |

### 2.2 Cross-check with the screener-worker's own builder (FACT, n = 1)

- **What ran.** `apps/screener-worker` exists since commit `7807d2b` (19:45 UTC). It has `snapshot.ts` and
  `refresh.ts` but no runnable server entry yet; part of it is uncommitted work in progress. So no end-to-end run of the
  service was possible.
- **What was measured.** Its `buildSnapshot`, then `prewarmChunk` over all tickers on one thread, then
  `snapshotDigest`. The script is `bench/scripts/ws_snapshot.mts`, with the presets from `presets.json` (26 presets);
  the output is `bench/raw/ws_snapshot_r1.json` (load 0.94).

| Step | Wall | CPU | RSS |
|---|---|---|---|
| inflate + verify + parse | 1.24 s | 1.37 s | 509 MB |
| `buildSnapshot` (SharedArrayBuffer columns, universe rows, series list) | 2.10 s | 2.09 s | 548 MB |
| `prewarmChunk`, 845 tickers × 85 series (76 + 9 from presets; 44 preset references were skipped by the WIP resolver) | 14.07 s | 15.62 s | 408 MB |
| **Spawn to ready** | **17.8 s** | **19.6 s total** | **peak 548 MB, steady 408 MB** |

INFERENCE: the worker's builder agrees with §2.1: about 18 s on one thread and about 20 vCPU-s per cold start. Its
shared-column layout holds less memory (peak 548 MB, steady 408 MB) than the plain-array path (733-750 MB).

### 2.3 Could a copy load a precomputed snapshot instead? (FACT, n = 1; `bench/raw/snapshot_ship.json`)

- **Measured.** The 64,220 tails serialized as one Float64 body plus an index take 68,997,672 B. gzip -6 gives
  50,092,492 B and gzip -1 gives 50,906,469 B: float64 tails barely compress. Loading from local disk (inflate and
  rebuild the cache) takes 0.61 s (1.10 s CPU).
- INFERENCE: from the `sin` bucket at 4.7 MB/s, 50 MB takes about 10.7 s, against 6.2-16.3 s of pre-warm. So the trade
  saves CPU but not wait.
- Float32 would halve the bytes but change values that comparisons read, which would break accuracy (6.5 History).
- The 11.8 MB input is the cheapest thing to move.

### 2.4 Download and the full cold start of a copy (INFERENCE from FACT parts)

| Part | One thread | Four threads | Source |
|---|---|---|---|
| Railway wake of a slept service | ≈ 1.0 s | ≈ 1.0 s | FACT §5: a request that woke the service took 1,033 and 1,049 ms, against 25-27 ms warm |
| `GET /state` + `POST /xsection` | ≈ 0.3 s | ≈ 0.3 s | INFERENCE: two calls at the 166 ms `/bundle` median from `sfo` (`BACKTEST_END_TO_END.md` 6.5) |
| Download of 11.76 MB from `sin` | 2.5-5 s | 2.5-5 s | FACT 4.7 MB/s aggregate over 16 lanes (`apps/backtest-worker/README.md:431`) and 2,268 ms median per object (`BACKTEST_END_TO_END.md` 6.5). The single-object throughput is UNKNOWN |
| Spawn to snapshot ready | 15.6-20.1 s | 9.5-11.9 s | FACT §2.1 |
| 845 `/manifest` cross-checks | 0 (overlaps the decode) to +2.3 s | same | AUDIT.md 6.5 rule 4; 2.3 s FACT (`BACKTEST_END_TO_END.md` 6.5) |
| First screen | 0.004-0.26 s | 0.004-0.26 s | FACT §2.1 |
| **Wait for the first screen of a session that wakes a copy** | **≈ 19.6-26.7 s** | **≈ 13.5-18.5 s** | |
| The same screen on a warm pool | **0.003-0.26 s** | | FACT §2.1 |

Bytes per cold start: 11.76 MB from the bucket (egress free, AUDIT.md 6d.1) and one `/xsection` grant counted against
`megabytes_per_day`. CPU per cold start: about 20 vCPU-s, which is USD 0.00015 (§6.1). The first request may also
answer 502 (docs, §5), so edge-bff must retry.

---

## 3. (b) Backtest copy: cold start and first jobs

Script: `bench/scripts/bt_cold.mts`. It runs the real worker process with the image's command
`node --experimental-strip-types --import ./loader/register.mjs src/server.ts`, the dev limits
(`BACKTEST_END_TO_END.md` 7.4) and a fresh `BACKTEST_CACHE_DIR`. The tests' fake terminal-api and bucket
(`tests/fake-terminal.mjs`) serve:
- REAL price packs and yearly files in the publisher's format, for IHSG plus 15 stocks;
- reference rows for all 845 tickers;
- a `/state` publication.

There are no broker files in the sandbox, so the jobs are price-only: the page's default entry without flow cards, as in
`tests/server.test.ts` `pageDefault`. A second process then starts on the same, now filled, disk cache. Raw:
`bench/raw/bt_local_r1.json`, `bt_local_r2.json`, `bt_emul_sfo_r1.json`.

### 3.1 Local (fake terminal-api on localhost) (FACT, 2 runs, 2 processes each)

| Measure | Fresh copy, empty disk | Restart, disk cache filled |
|---|---|---|
| Spawn to listening (`start` log line) | **0.26-0.32 s** | 0.27-0.28 s |
| RSS at listening / after the first catalog | 109-110 / 117-119 MB | 112 / 120-121 MB |
| First `GET /v1/catalog` answered (from spawn) | 0.32-0.36 s | 0.32-0.33 s |
| Single BBCA, first job (submit → FINISHED, polled every 25 ms; worker `duration_ms`) | 0.42-0.45 s (0.22-0.24 s) | 0.37-0.43 s (0.19-0.20 s) |
| Single BBCA, again | 0.17 s (0.15-0.16 s) | — |
| 12-stock portfolio, first | 0.40-0.45 s (0.38-0.41 s) | 0.40-0.45 s (0.36-0.43 s) |
| 12-stock portfolio, again | 0.29-0.32 s (0.26-0.28 s) | — |
| Peak RSS | 234-244 MB | 219 MB |
| Idle RSS 10 s / 30 s after the jobs | 221-231 / 147-167 MB | — |
| Disk cache after the run | 13 files, 328,953 B | |

### 3.2 With `sfo` latencies emulated (FACT for the emulation; the delays are INFERENCE)

The fake added 166 ms to every API answer (the `/bundle` median from `sfo`) and 2,100 ms to every bucket object, so a
file takes about the 2,268 ms per-object median from `sfo`. Run once, at load 1.6.

| Measure | Fresh copy | Restart with disk cache |
|---|---|---|
| First catalog answered (from spawn) | **2.99 s** | 2.95 s |
| Single BBCA, first job (submit → FINISHED) | **5.44 s**: reference lists, then the IHSG and BBCA packs, each about 2.3 s | 3.24 s: the reference lists again (no sha256, so no disk copy; `BACKTEST_END_TO_END.md` §15) |
| Single BBCA, again | 0.31 s | — |
| 12-stock portfolio, first | 2.79 s (11 new packs in parallel lanes) | 0.62 s |
| 12-stock portfolio, again | 0.45 s | — |

### 3.3 Recorded on Railway dev, with flow (FACT, `apps/backtest-worker/README.md:422-440`, `BACKTEST_END_TO_END.md` 7.4)

| Run | Worker | Submit to end (edge-bff polls every 2 s) | Downloaded |
|---|---|---|---|
| Single with flow, cold | 1.31 s | 4.99 s | 6 files, 1.25 MB |
| Single, warm | 0.45-0.58 s | 5.5-5.9 s | none |
| 12-stock flow portfolio, cold | 7.05 s | 12.42 s | 60 files, 28.35 MB in 6.1 s |
| 12-stock flow portfolio, warm | 5.5 s | 10.8 s | none |

Memory: a one-minute peak of 1.31 GB (preview, run and cancel); 0.32 GB for the cold API sequence; CPU peak 0.43 vCPU.
Catalog build 2.3 s from `sfo`.

### 3.4 What a copy per user means for the Backtest (INFERENCE from 3.1-3.3)

- **Page open after a wake.** About 1.0 s wake + 0.3 s start + 2.3-2.7 s catalog = **3.6-4.0 s** before the menus work.
  A warm pool keeps the catalog per publication, about 0.25 s (`BACKTEST_END_TO_END.md` §17; first open 1.37 s
  including the page).
- **First jobs of every session are cold.**
  - Worker time rises from 0.45-0.58 s to 1.31 s for a single stock, and from 5.5 to 7.05 s for a 12-stock flow
    portfolio (28 MB download).
  - In a pool, a ticker any user loaded this publication is already warm.
  - Whether a copy's disk cache survives sleep is UNKNOWN (M-U7). If it does, the restart column of 3.2 applies.
- **The one real gain is isolation.** Each user has their own job slot, so there is no queue. The pool reaches the same
  with K job threads and a fair claim (`mu_runtime/backtest.md` B3-B4): p95 queue wait 0 s for up to 50 users at once
  at K = 2, and 0.3-3.9 s at 200 users with K = 4 (`backtest.md` §5).

---

## 4. (c) Process baselines: an idle but awake copy

FACT: 3 runs each, at load about 1.1; each process killed 2 s after ready. Raw files: `bench/raw/base_*.json`.

| Process | Spawn to listening | RSS, idle | If kept awake 24/7 (INFERENCE, USD 10/GB-month) |
|---|---|---|---|
| Empty `node:http` server | 53-71 ms | 56 MB | USD 0.55 a month |
| The same with the worker's flags (`--experimental-strip-types` + loader) | 118-161 ms | 82 MB | USD 0.80 |
| Empty FastAPI app under uvicorn | 273-304 ms | 42 MB | USD 0.41 |
| terminal-api app (`create_app` with the tests' `FakeStore`/`FakeBucket`; boto3 and psycopg imported; no database pool) | 419-546 ms | 61 MB per process | Railway, real, 2 processes with pool: 0.142 GB average, about USD 1.5 (capacity report §2.2) |
| backtest-worker, listening (§3.1) | 0.26-0.32 s | 110 MB; 150-230 MB after jobs | USD 1.5-2.3 |
| Screener copy holding a snapshot (§2.1) | 9.5-20.1 s | 0.36-0.52 GB steady, 0.73 GB in the first minute | **USD 3.6-5.2** (up to 7.4) |

Reading (INFERENCE):
- The Node or Python runtime is not the cost: 42-82 MB, or under USD 1 a month even awake 24/7.
- The cost of a copy is the data it holds: the Screener snapshot (0.36-0.74 GB) and the Backtest caches (up to 1.31 GB
  at a peak).
- A per-user copy that cannot sleep costs that floor for every user. 200 always-warm users would cost about
  200 × (5.2 + 2.3 + 1.5) ≈ USD 1,800 a month, against about USD 18 for the pool.

---

## 5. Railway facts the model uses

| Fact | Source | Label |
|---|---|---|
| Sleeps after 5-10 min without outbound packets. Woken by public traffic or by private-network traffic from the same project. "The first request sent to a slept service may return a 502 Bad Gateway response". Applies to all replicas. "Slept services still consume a slot". Open database connections, polling and outbound requests keep a service awake | https://docs.railway.com/deployments/serverless (also served at /reference/app-sleeping), read 2026-10-28 | FACT |
| "A slept service accrues no compute charges". Egress is still billed. Bad fits: "latency-sensitive" first requests, "workers holding database connections or polling queues" | https://docs.railway.com/guides/cut-idle-costs-serverless | FACT |
| RAM USD 10/GB-month (USD 0.000231/GB-min); CPU USD 20/vCPU-month (USD 0.000463/vCPU-min); egress USD 0.05/GB; builds free; Pro 42 replicas per service | https://docs.railway.com/reference/pricing/plans | FACT |
| Wake measured in this project. `telegram-trigger` (Serverless, Python) logged "Stopping Container" at 19:42:06.165Z, 6 min 21 s after its last request (19:35:45Z). The next request arrived at 19:42:46.729Z (HTTP log), "Starting Container" followed at 19:42:46.851Z, and that request took totalDuration 1,033 ms (upstream 1,010 ms); the next two took 27 ms and 25 ms. An earlier wake at 19:35:36Z took 1,049 ms, then 27 ms and 1 ms. The probe was the sibling task's (research §2.10); the logs were read here | `railway logs -s telegram-trigger --http --json`, and deploy logs, read-only; `bench/raw/railway_tt_http.jsonl`, `railway_tt_deploy.jsonl` | FACT, n = 2 |
| 100 services a project, of which the project uses 28; 25 new services a day for a new account | research §2.3, §4.3 (error text and staff replies) | FACT (staff/community, not docs) |
| `terminal_api_login` allows 20 connections; terminal-api runs 2 processes with pool `min_size=1, max_size=8` | capacity report §1 item 8; `apps/terminal-api/app/store.py:24`; `apps/terminal-api/Dockerfile` CMD `--workers 2` | FACT |
| Default terminal quotas: `megabytes_per_day` 300, `files_per_hour` 60 | `database/migrations/20261025_100_create_terminal_schema.sql:79-83` | FACT |

---

## 6. (d) Usage model and the four architectures for 10, 50 and 200 users

Script: `bench/scripts/cost_model.py`. Outputs: `bench/raw/cost_model.json` (base),
`cost_model_tail10.json` (10-minute sleep tail) and `cost_model_heavy.json` (heavy profile). Each output has a matching
`.txt`.

### 6.1 Inputs

| Input | Value | Label |
|---|---|---|
| Users N | 10, 50, 200 external users, each active on every trading day (an upper bound for SILO, which scales with N) | ASSUMPTION |
| Trading days a month | 21; no weekend sessions | ASSUMPTION |
| Sessions per user per day; active minutes per session | 2 × 20 min (light). Heavy: 4 × 30 min | ASSUMPTION |
| Session windows (WIB) | 08:00-10:00 (weight 0.45), 15:30-17:30 (0.25), 19:00-22:00 (0.30); each user's sessions in different windows; uniform start | ASSUMPTION |
| Per session | Screener: 15 uncached custom screens + 10 lookups. Backtest: 3 jobs + 6 previews | ASSUMPTION |
| Peak concurrency | 0.3 × N at once: 3, 15, 60 | ASSUMPTION (as capacity report §5.4, 6d.9) |
| Awake tail after the last request | 7.5 min (base); 10 min (sensitivity) | FACT range 5-10 (docs), measured 6.4 |
| Screener copy RSS awake / pooled replica RSS | 0.55 GB / 0.52 GB | FACT §2.1 (0.36-0.74 / 0.516-0.521 at K = 2) |
| Screener CPU per cold start / per uncached custom screen / per lookup | 20 / 0.22 / 0.005 vCPU-s | FACT §2.1, §2.2 |
| Screener file per load | 11,758,425 B | FACT §2.1 |
| Backtest copy RSS awake / pooled | 0.25 GB / 0.40 GB | FACT 0.11-0.23 local and 0.32 dev / INFERENCE (`backtest.md` §6) |
| Backtest CPU per job / per preview / per cold start | 2.0 / 1.0 / 1.0 vCPU-s | INFERENCE (`backtest.md` §6: 2.0 today per job; preview between 1.6 and 0.25) |
| terminal-api copy | USD 1.50 a month, always on (its database pool keeps it awake) | FACT 0.142 GB + 0.004 vCPU average (capacity report §2.2) |
| terminal-api pooled | USD 1.2 a replica; 1 replica, 2 at 200 users | FACT/INFERENCE (`terminal.md` §7) |
| Pool screener | R = 2 replicas (P32 availability), K = 2; 62 publications a month; previous snapshot kept 10 min per publication; result-cache hit rate h = 0.5 | 6d (P32, 6d.4, 6d.9) |
| SILO publication refresh | 0.25 per user-day (a publication lands while a copy is awake: about 08:05 and 20:03 WIB) | ASSUMPTION |
| Prices | USD 0.000231/GB-min, USD 20/2,592,000 per vCPU-s | FACT §5 |

**Models.**
- **SILO:** one Screener copy and one Backtest copy per user, each with Serverless. Every session wakes them, pays their
  cold start and keeps them awake for L + tail minutes. terminal-api is either per user (it cannot sleep) or shared.
- **POOL 24/7:** shared services as designed (6d). Screener R = 2 × K = 2, one Backtest worker, one or two terminal-api.
- **POOL, Serverless, asleep whenever idle:** the same pool with Serverless and a cron wake at 08:00 WIB. It sleeps
  whenever no user was active for the tail. Simulated over 200 random trading days.
- **POOL, Serverless, kept awake 14 h:** the same pool kept awake about 08:10-22:10 WIB on trading days. Its own
  `/state` poll in that window is outbound traffic, so it stays awake (docs). It stops polling outside the window and
  sleeps at night and on weekends. A cron or edge-bff wakes it at 08:10.
- **HYBRID:** the kept-awake pool plus per-user lanes (no added cost). A dedicated always-on Backtest worker
  (0.40 GB, USD 4.0 a month) only for premium or heavy users: shown for 1 such user, and for 10 % of N.

### 6.2 Monthly cost (INFERENCE, USD, light profile, tail 7.5 min)

| N | Model | Screener | Backtest | terminal-api | Dedicated | **Total** | Per user |
|---|---|---|---|---|---|---|---|
| 10 | SILO, all three per user | 1.58 | 0.72 | 15.00 | — | **17.30** | 1.73 |
| 10 | SILO, terminal-api shared | 1.58 | 0.72 | 1.20 | — | **3.50** | 0.35 |
| 10 | POOL 24/7 | 10.57 | 4.04 | 1.20 | — | **15.81** | 1.58 |
| 10 | POOL, asleep whenever idle | 1.62 | 0.64 | 1.20 | — | **3.46** | 0.35 |
| 10 | POOL, kept awake 14 h | 4.32 | 1.67 | 1.20 | — | **7.19** | 0.72 |
| 10 | HYBRID (kept awake + 1 dedicated) | 4.32 | 1.67 | 1.20 | 4.00 | **11.19** | 1.12 |
| 50 | SILO, all three per user | 7.88 | 3.60 | 75.00 | — | **86.48** | 1.73 |
| 50 | SILO, terminal-api shared | 7.88 | 3.60 | 1.20 | — | **12.68** | 0.25 |
| 50 | POOL 24/7 | 10.60 | 4.19 | 1.20 | — | **15.99** | 0.32 |
| 50 | POOL, asleep whenever idle | 2.20 | 1.02 | 1.20 | — | **4.42** | 0.09 |
| 50 | POOL, kept awake 14 h | 4.34 | 1.83 | 1.20 | — | **7.37** | 0.15 |
| 50 | HYBRID (kept awake + 1 / 5 dedicated) | 4.34 | 1.83 | 1.20 | 4.00 / 20.00 | **11.37 / 27.37** | 0.23 / 0.55 |
| 200 | SILO, all three per user | 31.51 | 14.41 | 300.00 | — | **345.92** | 1.73 |
| 200 | SILO, terminal-api shared | 31.51 | 14.41 | 2.40 | — | **48.32** | 0.24 |
| 200 | POOL 24/7 | 10.68 | 4.78 | 2.40 | — | **17.86** | 0.09 |
| 200 | POOL, asleep whenever idle | 2.35 | 1.63 | 2.40 | — | **6.38** | 0.03 |
| 200 | POOL, kept awake 14 h | 4.42 | 2.41 | 2.40 | — | **9.23** | 0.05 |
| 200 | HYBRID (kept awake + 1 / 20 dedicated) | 4.42 | 2.41 | 2.40 | 4.00 / 80.00 | **13.23 / 89.23** | 0.07 / 0.45 |

Not counted, because they are the same in every model:
- egress to browsers;
- edge-bff;
- the publisher;
- Postgres;
- the Railway Pro fee.

**Sensitivity (INFERENCE).**

| Case | SILO, terminal-api shared (10 / 50 / 200 users) | Pool kept awake (10 / 50 / 200 users) | Pool asleep whenever idle (10 / 50 / 200 users) |
|---|---|---|---|
| Base (light profile, tail 7.5 min) | USD 3.5 / 12.7 / 48.3 | USD 7.2 / 7.4 / 9.2 | USD 3.5 / 4.4 / 6.4 |
| Tail 10 min | USD 3.7 / 13.7 / 52.2 | unchanged | USD 3.6 / 4.5 / 6.4 |
| Heavy profile (4 × 30 min) | USD 7.3 / 31.9 / 125.2 | USD 7.2 / 7.6 / 10.1 | USD 4.0 / 4.7 / 7.3 |

The pool-asleep simulation fits at most 3 sessions a day (3 windows), so its heavy-profile figures are a lower bound.

**Break-even (INFERENCE from the rows).**
- SILO with a shared terminal-api adds about USD 0.23 per user-month (light) or about USD 0.62 (heavy).
- Against the pool kept awake 14 h (about USD 6 fixed plus terminal-api): equal at about 26 light users or about 10
  heavy users.
- Against the pool 24/7: equal at about 65 light users or about 23 heavy users.
- Against the pool asleep whenever idle: SILO is never cheaper; they are equal at 10 users.

### 6.3 What the user waits for (INFERENCE from FACT §2-§4)

Worker-side waits only. The browser ↔ edge-bff round trip is the same in every model.

| Moment | SILO (copy asleep at the start of every session) | POOL 24/7, or kept awake | POOL, asleep whenever idle | HYBRID |
|---|---|---|---|---|
| Share of sessions that start on a cold copy (10 / 50 / 200 users) | **100 % / 100 % / 100 %** | 0 % | 26.6 % / 2.1 % / 0.5 % (simulated: 112, 45 and 42 sessions a month); tail 10 min: 24.2 % / 2.1 % / 0.5 % | as its pool |
| First Screener screen of a session | **19.6-26.7 s** (K = 1) or **13.5-18.5 s** (K = 4), plus a possible 502 retry | **3-13 ms** default or preset; **0.14-0.26 s** custom | cold share: as SILO; others: as the pool | as the pool |
| Later screens | same in all models: 3-13 ms default; 0.14-0.26 s new custom | | | |
| Same custom screen already run by another user | 0.14-0.26 s (no cross-user cache) | 8-16 ms (shared result and series cache) | same as the pool | same as the pool |
| A publication lands during a session | each awake copy reloads: about 20 vCPU-s and 13-20 s per copy (the previous snapshot serves meanwhile, or the user waits) | R = 2 replicas reload once each | same as the pool | same as the pool |
| Backtest page usable after open | **3.6-4.0 s** | about 0.25 s catalog (1.12-1.37 s page, §17 FACT) | cold share: about 3.6-4.0 s | same as the pool |
| First Backtest job of a session | cold files: single +0.8 s at worker level (1.31 against 0.45-0.58 s); flow portfolio +1.5 s (7.05 against 5.5 s; 28 MB). A fresh price-only copy took 5.4 s for its first single job with `sfo` latencies emulated | warm when any user loaded the ticker this publication; p95 queue 0 s up to 50 at once (K = 2), 0.3-3.9 s at 200 (K = 4) | as the pool, after the wake | dedicated user: no queue, warm if always on |
| Terminal ticker open | no gain: the browser downloads from the bucket; a copy cannot sleep | per-user subscriber locks (`terminal.md` T2, T4): burst of 60 users about 0.2-0.3 s, against 6-8 s today | same as the pool | same as the pool |

### 6.4 Repeated work and limits (INFERENCE from 6.1)

| Per month | SILO, 10 users | SILO, 50 users | SILO, 200 users | POOL 24/7 | POOL kept awake | POOL asleep whenever idle (10 / 50 / 200 users) |
|---|---|---|---|---|---|---|
| Screener snapshot builds (about 20 vCPU-s each) | 472 | 2,363 | 9,450 | 124 | 84 | 338 / 216 / 210 |
| Screener file downloads | 5.6 GB | 27.8 GB | 111 GB | 1.5 GB | 1.0 GB | 4.0 / 2.5 / 2.5 GB |
| Start-up CPU (Screener + Backtest) | 2.7 vCPU-h | 13.7 vCPU-h | 54.8 vCPU-h | 0.7 vCPU-h | 0.5 vCPU-h | 1.9 / 1.2 / 1.2 vCPU-h |
| Grant volume per day on the workers' account (default quota 300 MB/day) | 265 MB | 1.3 GB | 5.3 GB | 47 MB | 47 MB | about 190 / 120 / 120 MB |
| Services (cap 100 a project, 28 used) | 21 (shared terminal-api) or 30 | 101 or 150: **over the cap** | 401 or 600: **over the cap** | 3 | 3 | 3 |
| terminal-api connections at minimum (role limit 20) | 2 (shared) or **20 (per user: at the limit)** | 2 or **100: over** | 2-4 or **400: over** | 2 | 2 | 2 |
| Redeploys per release | 20-30 | 100-150 | 400-600 | 3 | 3 | 3 |
| Copies at different code or data versions during a rollout or a publication | up to N | up to N | up to N | 2, with pinning and a grace window (6d.4) | 2 | 2 |

In money, the repeated work is small: 9,450 cold starts cost about USD 1.5 of CPU a month. The loss is in wait time,
limits, operations and version skew, not in the bill.

---

## 7. What SILO loses by not sharing across users (INFERENCE from FACT)

- **Screener snapshot.** It is the same bytes for every user of one publication (6d.2: a function of the publication
  only). SILO builds it once per user and per wake: 3.8-76 times as often as the 24/7 pool (124 builds) and 5.6-112
  times as often as the kept-awake pool (84) (§6.4). Every build is a 13.5-27 s wait for someone.
- **Presets and default screens.** They are pre-warmed in every copy too. That is no loss in time after the copy is
  warm, but each copy pays it again inside its cold start.
- **Custom results and series.** Another user's identical screen in the pool is an 8-16 ms hit. In SILO it costs
  0.14-0.26 s of compute again (FACT §2.1). The CPU cost is negligible (USD 0.0000017 per screen); the time is visible.
- **Backtest files.** The pool's memory and disk caches serve every user (BBCA loaded once per publication). SILO
  downloads per user and per wake: 1.25 MB for one flow stock, 28 MB for a flow portfolio (FACT §3.3), 2-6 s each.
  The exact result reuse proposed in `backtest.md` B6 cannot exist across users.
- **Terminal.** Nothing is lost or gained: each browser has its own IndexedDB cache in both models
  (`apps/edge-bff/terminal/src/data/rack.ts:15-16`).

---

## 8. Unknowns, and the check that settles each (PROPOSED; each Railway step needs the user's go)

| # | Unknown | Check |
|---|---|---|
| S-U1 | Screener and Backtest timings on a Railway vCPU against this Xeon | Phase 17 S24 (6d.11): cold start of a real `screener-worker` replica, per step, with its RSS curve |
| S-U2 | Single-object download rate of an 11.8 MB file from `sin` to `sfo` | The same S24 run; the refresh log's download timing |
| S-U3 | Wake time of a Node service holding 0.4-0.7 GB, and the 502 share on first requests | A Serverless test service (needs the user's go), 20 wakes; research B1 |
| S-U4 | Whether a container's disk (the backtest disk cache) survives sleep and wake | The same test: a file written before sleep, read after the wake (M-U7) |
| S-U5 | The real usage profile: users, sessions, minutes, windows | The user's P29 numbers, then edge-bff logs per owner |
| S-U6 | The Monte Carlo windows (3 windows, uniform starts) against real session times | Replace with logged session starts once external users exist |

---

## 9. Files

All paths are under `/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/mu_runtime/bench/`.

| What | Files |
|---|---|
| Scripts | `scripts/make_xsection.py`; `scripts/screener_cold.mts`; `scripts/run_screener.sh`; `scripts/run_proc.mjs`; `scripts/summarize_screener.py`; `scripts/ws_snapshot.mts`; `scripts/snapshot_ship.mts`; `scripts/bt_cold.mts`; `scripts/empty_server.mjs`; `scripts/empty_server_ts.mts`; `scripts/tapi_base.py`; `scripts/cost_model.py` |
| Raw outputs | `raw/screener_k{1,2,4}_r*.json` (`screener_k1_try.json` was the trial run, excluded); `raw/screener_summary.json`; `raw/ws_snapshot_r1.json`; `raw/ws_snapshot_sources.txt`; `raw/snapshot_ship.json`; `raw/bt_local_r{1,2}.json`; `raw/bt_emul_sfo_r1.json`; `raw/base_*.json`; `raw/railway_tt_http.jsonl`; `raw/railway_tt_deploy.jsonl`; `raw/cost_model{,_tail10,_heavy}.{json,txt}`; `raw/make_xsection.txt`; `raw/run_screener.log` |
| Data, local only (market data) | `data/xsection_price.json.gz` and `.meta.json`; `data/snapshot_tails.bin.gz`; `data/btcache-*` |
