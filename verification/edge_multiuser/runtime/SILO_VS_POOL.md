# One service copy per user (SILO) or one shared service (POOL): the decision for Screener, Backtest and Terminal

Read-only decision paper, 2026-10-28. No repository change, no Railway mutation (nothing created, slept, scaled or
deployed), no database write. Inputs: `mu_runtime/silo_research.md` (Railway docs, best practice), `mu_runtime/silo_bench.md`
(measurements, cost model), `mu_runtime/RUNTIME.md` (the shared runtime design), plus read-only checks made for this paper
(section 10). All `mu_runtime/` paths are under
`/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/mu_runtime/`.

Labels: **FACT** (URL, file:line, or a measurement with its saved output), **INFERENCE** (derived from FACTs),
**PROPOSED** (needs the user's go), **UNKNOWN** (with the check that settles it), **ASSUMPTION** (a usage-profile input).

---

## 0. Decision in one screen

1. **No copy per user for Screener, Backtest or Terminal.** One shared service each (POOL), users kept apart by
   `owner_key` lanes, quotas and per-owner identity (RUNTIME RP1-RP12). PROPOSED.
2. **The user's premise is half right.** A service that *sleeps* costs no compute while idle (FACT, Railway docs and the
   usage reading in 2.2). But that is a property of sleeping, not of copying: a sleeping POOL has the same zero idle
   cost, and it is warm for everyone once one user wakes it. Today no EDGE service sleeps (FACT, `.railway/railway.ts:113,
   147` are the only `sleepApplication: true`).
3. **SILO loses on speed.** Every session would start on a cold copy: about **20-27 s** before the first Screener result
   (14-19 s with four threads), against **3-13 ms** (default screen) or **0.14-0.26 s** (custom) from a warm pool (FACT
   bench). A Backtest copy's first job takes about 5.4 s against 0.3 s warm (FACT, emulated `sfo` latencies).
4. **SILO is never cheaper than a sleeping POOL**: USD 3.5 / 12.7 / 48.3 a month for 10 / 50 / 200 light users against
   USD 3.5 / 4.4 / 6.4, with 100 % of sessions waiting against 27 % / 2 % / 0.5 % (INFERENCE, `silo_bench.md` §6).
   SILO beats an *always-on* POOL only below about 26-65 light users, and only by at most about USD 12 a month.
5. **SILO breaks Railway and database limits early**: 100 services a project (28 used), 25 new services a day,
   20 connections for `terminal_api_login` (a terminal-api copy holds at least 2), and edge-bff only accepts the fixed
   hostnames `backtest-worker.railway.internal` and `screener-worker.railway.internal` (FACT, `apps/edge-bff/app/config.py:106,
   118`).
6. **SILO multiplies accuracy risk**: N copies refresh, fail and redeploy independently, so users can see different data
   or engine versions with nobody noticing. The POOL has 2 Screener replicas with pinning and a digest check.
7. **Sleep on the POOL: always on at launch** (RUNTIME RT14 kept). Sleeping all three outside a 14-h trading-day window
   would save about **USD 8.6 a month** (USD 15.8 → 7.2 at 10 users; INFERENCE), but the first user outside the window
   waits 14-27 s, and it needs code changes first (the Screener polls every 60 s, so it can never sleep as built: FACT
   `apps/screener-worker/src/refresh.ts:47, 213`). The switch conditions are in section 7.2.
8. **HYBRID (the AWS "bridge") only by exception**: a dedicated Backtest worker for a paying or heavy tenant (about USD 4 a
   month always on), never a dedicated Screener or terminal-api. The Terminal page is already per user: it computes in
   each browser and downloads straight from the bucket.
9. **Conditions where copies would win** (section 8): a contract that requires dedicated compute, per-user private data
   or untrusted per-user code, or one tenant that lanes and budgets cannot contain. Cost alone is never one.
10. **Measure on dev next** (section 9): the real Screener cold start on Railway, a wake of a 0.5 GB Node service over the
    private network (time, 502 share, disk kept or not), and the pool fairness load test. Two read-only checks were done
    here: a sleeping service's memory is not billed (2.2), and private-network wakes succeed on the first try 7 of 8 times.

---

## 1. The question, and what the three models mean here

The user (2026-10-28): "jika screener, backtest, dan terminal adalah idle, dalam artian ketika user tidak mengakses maka
tidak ada biaya, we might as well to create more the same service. Jadi misalkan ada service, kita duplicate service yang
sama untuk serve user ID 123, kemudian kita duplicate lagi service yang sama untuk serve user 456 dan seterusnya. Coba saja
di explore pakai benchmark yang best practice." Priorities (`PLAN.md:970-974`): cost efficiency, process speed (users
must not wait long), accuracy. AI Orc is out of scope. Users are external (P29, `EXEC.md:8560-8562`).

| Model | Meaning in EDGE | Industry name |
|---|---|---|
| SILO | One Railway service per user for each of `screener-worker`, `backtest-worker` (and optionally `terminal-api`), each with Serverless so an idle copy sleeps. edge-bff routes each user to their copies | AWS "silo"; Azure "automated single-tenant deployments" (`silo_research.md` §3) |
| POOL | One service each, shared by all users, isolated logically: owner lanes, per-owner CPU budget (P33), fair claim (B4), per-owner terminal identity (T2) | AWS "pool"; Azure shared compute |
| HYBRID | POOL for everyone, plus a dedicated copy only for a named exception (paid tier, compliance, a heavy tenant) | AWS "bridge" / tiering; Azure vertical partitioning |

"Replica per user" is not an option on Railway: public traffic goes to a random replica, there are no sticky sessions,
and the private DNS returns all replicas in random order with no load balancer (FACT, `silo_research.md` §2.4-2.5).

---

## 2. The facts that decide it

### 2.1 Railway sleeping (Serverless)

| Fact | Source | Label |
|---|---|---|
| "Once a service stops sending packets it is considered inactive after 5 minutes"; in practice it "sleeps somewhere between 5 and 10 minutes after its last outbound traffic". The guides say 10 minutes | https://docs.railway.com/reference/app-sleeping (re-read 2026-10-28); https://docs.railway.com/guides/cut-idle-costs-serverless | FACT |
| Measured: `telegram-trigger` fell asleep 6 min 21 s after its last request (`silo_bench.md` §5), and about 4.5-6.5 min in the sibling probe | `silo_bench.md` §5; `silo_research.md` §2.10 | FACT, n = 2 |
| "A service is woken when it receives traffic from the internet or from another service in the same project", including the private network | app-sleeping (re-read) | FACT |
| "The first request sent to a slept service may return a 502 Bad Gateway response" | app-sleeping (re-read) | FACT |
| "Enabling Serverless will apply the setting across all Replicas": no "keep one warm" | app-sleeping (re-read) | FACT |
| Serverless "de-prioritizes your workload"; a wake "may require a rebuild" | app-sleeping (re-read) | FACT |
| Applied only to containers created after it is enabled, so it needs a redeploy | `silo_research.md` §2.1 | FACT |
| What keeps a service awake: any outbound packet, including a held Postgres connection, polling, telemetry and private-network calls. Bad fits named by Railway: latency-sensitive first requests, workers polling queues or holding database connections | `silo_research.md` §2.1 (deployments/serverless, cut-idle-costs guide) | FACT |
| "A slept service accrues no compute charges"; egress is still billed | cut-idle-costs guide | FACT |

### 2.2 Billing while asleep, read from this project (new here)

FACT (Railway usage API, `usage(projectId, 2026-10-24..2026-10-28, groupBy SERVICE_ID)`, output
`mu_runtime/svp/usage_w4d.json`; hourly metrics `mu_runtime/svp/tm_mem.json`):

| Service (Serverless?) | Memory billed in 4 days | Average | CPU billed |
|---|---|---|---|
| telegram-monitor (yes) | 10.0 GB-min | 1.7 MB | 0.24 vCPU-min |
| telegram-trigger (yes) | 0.3 GB-min in 7 days (`usage_w7d.json`) | ≈ 0 | ≈ 0 |
| terminal-api (no) | 819.1 GB-min | 142 MB | 24.3 vCPU-min |
| edge-bff (no) | 472.3 GB-min | 82 MB | 32.8 vCPU-min |
| backtest-worker (no) | 280.0 GB-min | 49 MB | 5.7 vCPU-min |

INFERENCE: telegram-monitor's hourly memory metric reads about 46 MB in 155 of 169 hours, so if that memory had been
resident all the time, 4 days would bill about 0.046 GB × 5,760 min = 265 GB-min. The usage API counted 10.0, about
4 %: memory is not billed while asleep, as the docs say. This mostly settles `silo_research.md` U1. The invoice itself is
not readable with the project token (capacity report §2.2), so "billed" means Railway's usage API here.

### 2.3 What would keep each EDGE service awake today (FACT from code and flow logs)

| Service | Outbound while idle | Evidence | Can it sleep as built? |
|---|---|---|---|
| screener-worker (being built) | Reads `/state` every 60 s on a timer | `apps/screener-worker/src/refresh.ts:47` (`POLL_MS = 60_000`), `:213` (`setInterval`) | No. It never sleeps until the poll is limited to a window or done on request |
| backtest-worker | None found: no timer in `src/`; `/state` at most every 60 s, only on a request | `grep setInterval apps/backtest-worker/src/*.ts` (none); `verification/screener/AUDIT.md:137` row; flow logs: traffic in only 9 distinct minutes of the last 24 h (`svp/net_bt24.jsonl`) | Yes, probably (UNKNOWN whether flow logs are sampled) |
| terminal-api | Postgres pool `min_size=1`, 2 uvicorn processes; flow logs show egress to port 5432 at 18:40:14, 18:41:01, 18:42:03 UTC | `apps/terminal-api/app/store.py:24`; `apps/terminal-api/Dockerfile:10`; `svp/net_terminal-api.jsonl` | No, while it holds the pool (Railway names this a bad fit) |
| edge-bff | Session store and Backtest loop on Postgres; the only public entry | `.railway/railway.ts:181-190`; `apps/edge-bff/app/backtest.py:706` (`while True`) | No, and it must not |

Listening address: both workers listen on `0.0.0.0` (FACT, `apps/backtest-worker/src/server.ts:334`,
`apps/screener-worker/src/server.ts:522`). `telegram-monitor` once failed a private-network wake with `connection
refused` and was fixed by listening on IPv6 (FACT, `RAILWAY_CHANGELOG.md:3715`). INFERENCE: a sleeping worker should
listen on `::` until a test shows `0.0.0.0` wakes correctly in this environment.

### 2.4 Wake over the private network (new here)

FACT (`railway logs` of `idx-price-cron` and `idx-price-recovery-cron`, 2026-10-24..28, `svp/cron_*.jsonl`): 8 private
calls to `telegram-monitor`; 7 accepted at attempt 1, 1 at attempt 2 (2026-10-24 23:01:22 UTC). The caller retries 4
times with a 20 s timeout and 1, 2, 4 s back-off (`apps/idx-price-cron/price_update.py:96-134`). UNKNOWN whether
`telegram-monitor` was asleep before each call (other services also notify it). INFERENCE: wake by private call works,
and a caller must retry; edge-bff would need the same retry for any sleeping worker.

### 2.5 Cold-start times (FACT unless marked; `silo_bench.md` §2-§4)

| Step | Screener copy | Backtest copy |
|---|---|---|
| Railway wake (small Python service) | ≈ 1.0 s (1,033 and 1,049 ms against 25-27 ms warm, project logs) | same |
| Process start to listening | 0.25-0.42 s | 0.26-0.32 s |
| Data before the first answer | 11.8 MB download (2.5-5 s, INFERENCE) + inflate/verify 1.2-1.5 s + slice 1.5-2.1 s + pre-warm of 53 indicators 6-16 s | catalog 2.3-3.0 s from `sfo`; files per job about 2.3 s each from the `sin` bucket |
| Total before the first useful answer | **15.6-20.1 s** data part on 1 thread, 9.5-11.9 s on 4; **≈ 19.6-26.7 s / 13.5-18.5 s** with wake and download (INFERENCE) | first single job **5.4 s** on a fresh copy (emulated `sfo`), 0.3 s when repeated |
| CPU per cold start | 17-25 vCPU-s | about 1 vCPU-s plus downloads |
| RSS | peak 0.73-1.17 GB, steady 0.36-0.52 GB | 110-120 MB idle, 0.22-0.24 GB price-only jobs, 1.31 GB one-minute peak on dev with flow |

Why the Screener start is long (FACT, code): `/ready` answers 200 only once a snapshot is loaded
(`apps/screener-worker/src/server.ts:376-379`), and a cold start pre-warms every default with all compute threads first
(`server.ts:221-223`). Shipping a precomputed snapshot does not help: 50 MB gzip, as slow to download as to compute
(FACT, `silo_bench.md` §2.3).

### 2.6 Limits

| Limit | Value | Source | Label |
|---|---|---|---|
| Services per project | 100; the project has 28 | error text and staff, station.railway.com (`silo_research.md` §2.3); `rt_status.json` | FACT (community, not docs) |
| New services a day | 25 for a "new" account, "cannot be raised" | staff, station.railway.com | FACT (community); whether this account is "new" is UNKNOWN |
| Replicas | 42 per service, 50 in total | docs (`silo_research.md` §2.3) | FACT |
| API | 10,000 requests an hour, 50 a second (Pro) | https://docs.railway.com/integrations/api | FACT |
| `terminal_api_login` connections | 20; terminal-api holds at least 2 (2 processes × `min_size=1`) | capacity report §1 item 8; `store.py:24`; `Dockerfile:10` | FACT |
| `edge_bff_login` connections | 20 (pool 6 per process) | capacity report line 155 | FACT |
| Worker grant quota | 300 MB a day per terminal subscriber by default | `database/migrations/20261025_100_create_terminal_schema.sql:79-83` | FACT |
| edge-bff routing | worker URLs must be the fixed private hostnames | `apps/edge-bff/app/config.py:106, 118` | FACT |

---

## 3. Benchmark numbers used below (FACT, `silo_bench.md`)

| Measure | Value |
|---|---|
| Screener input file | 11,758,425 B gzip, 74.3 MB inflated, 845 tickers, 1,330,722 rows |
| Screener spawn to ready, 1 / 2 / 4 threads | median 17.1 / 13.1 / 11.1 s |
| Screener worker's own builder (WIP code) | 17.8 s, 19.6 vCPU-s, peak 548 MB, steady 408 MB |
| Default screen on a warm copy | 3-13 ms |
| 3-condition custom screen, first / repeated | 143-256 ms / 7.6-15.7 ms |
| Backtest copy: listening / first catalog (emulated `sfo`) | 0.26-0.32 s / 2.95-2.99 s |
| Backtest first single job on a fresh copy / repeated (emulated `sfo`) | 5.44 s / 0.31 s |
| Backtest on dev with flow, cold / warm (worker time) | single 1.31 / 0.45-0.58 s; 12-stock portfolio 7.05 / 5.5 s (`apps/backtest-worker/README.md:429-432`) |
| Empty runtimes | Node 56-82 MB, FastAPI 42 MB, terminal-api app 61 MB per process |
| Railway wake | ≈ 1.0 s (n = 2) |

---

## 4. Cost and latency per service: SILO against POOL against HYBRID

### 4.1 Basis

INFERENCE from `silo_bench.md` §6 (`bench/raw/cost_model*.json`). N = daily external users, each active every trading day
(21 a month), 2 sessions × 20 minutes a day (light), 30 % of N at once at the peak (3 / 15 / 60). Prices: RAM USD 10 per
GB-month, CPU USD 20 per vCPU-month (FACT). Egress to browsers, edge-bff, the publisher, Postgres and the Pro fee are equal
in every model and left out. RUNTIME.md counts users *at once* instead (U = 10 / 50 / 200, N ≈ 33 / 167 / 667) and
prices the whole proposed design at USD 21.7 / 28.4 / 55.9; the two bases are not mixed below.

POOL variants:
- **POOL-on**: always on (RUNTIME RT14). Screener 2 replicas (P32) × 2 threads.
- **POOL-window**: Serverless, kept awake about 08:10-22:10 WIB on trading days, asleep at night and on weekends.
- **POOL-sleep**: Serverless, asleep whenever no user was active for the tail (7.5 min), cron wake at 08:00 WIB.

### 4.2 Screener

| USD a month | 10 users | 50 users | 200 users |
|---|---|---|---|
| SILO, each copy sleeps when idle | 1.58 | 7.88 | 31.51 |
| SILO, copies that cannot sleep (as built: the 60-s poll) | 36-52 | 180-260 | 720-1,040 |
| POOL-on | 10.57 | 10.60 | 10.68 (14-16 if 60 users at once need 3-4 threads a replica, RUNTIME §4.6) |
| POOL-window | 4.32 | 4.34 | 4.42 |
| POOL-sleep | 1.62 | 2.20 | 2.35 |
| HYBRID: one dedicated always-on copy | + 3.6-5.2 per dedicated copy | | |

The "cannot sleep" row is INFERENCE: 0.36-0.52 GB steady per copy (FACT) × USD 10 × N.

| What the user waits for (worker side) | SILO | POOL-on / POOL-window (inside the window) | POOL-sleep |
|---|---|---|---|
| First result of a session | **19.6-26.7 s** (1 thread) or **13.5-18.5 s** (4 threads), plus a possible 502 retry | **3-13 ms** default or preset; **0.14-0.26 s** custom | as the pool, except a cold share of 26.6 % / 2.1 % / 0.5 % of sessions that wait as SILO |
| The same custom screen another user already ran | 0.14-0.26 s (no shared cache) | 8-16 ms (shared result and series cache) | as the pool |
| A publication lands during use | every awake copy rebuilds: about 20 vCPU-s and 13-20 s each | 2 replicas rebuild once; the previous snapshot serves meanwhile | as the pool |
| Snapshot builds a month | 472 / 2,363 / 9,450 | 124 (on) / 84 (window) | 338 / 216 / 210 |

### 4.3 Backtest

| USD a month | 10 users | 50 users | 200 users |
|---|---|---|---|
| SILO, each copy sleeps when idle | 0.72 | 3.60 | 14.41 |
| SILO, copies always on (110-230 MB each) | 11-23 | 55-115 | 220-460 |
| POOL-on | 4.04 | 4.19 | 4.78 |
| POOL-window | 1.67 | 1.83 | 2.41 |
| POOL-sleep | 0.64 | 1.02 | 1.63 |
| HYBRID: one dedicated always-on worker (0.40 GB) | + 4.0 per dedicated worker | | |

| What the user waits for | SILO | POOL (warm) |
|---|---|---|
| Page menus | no wait if edge-bff serves its shared catalog cache (FACT: one cache, 60 s, last value kept while the worker cannot answer, `apps/edge-bff/app/backtest.py:42-44, 934, 1056-1069`); 3.6-4.0 s if the page must ask the user's own copy | about 0.25 s |
| First job or preview of a session | wake ≈ 1 s + reference lists and packs on an empty cache: 5.4 s for a single stock (emulated `sfo`); +1.5 s for a 12-stock flow portfolio at worker level (FACT dev) | 0.3 s single (price-only, warm), 0.45-0.58 s with flow; any ticker any user loaded this publication is already warm |
| Queue | none: one copy each | p95 0 s up to 50 users at once with 2 slots; 0.3-3.9 s at 200 with 4 slots, 0 s with 8 (`backtest.md` §5, INFERENCE) |

The only real gain of a Backtest copy is its own slot. The pool gets the same with K slots and the fair claim (B3, B4).

### 4.4 Terminal

The Terminal page already runs per user: it computes in the browser and downloads from the bucket, whose egress is free
(FACT, `RUNTIME.md` §4.4). What could be copied is `terminal-api`, the gate that signs URLs and counts quotas.

| USD a month | 10 users | 50 users | 200 users |
|---|---|---|---|
| SILO terminal-api per user (it holds a database pool, so it cannot sleep) | 15 | 75 | 300 |
| POOL terminal-api (1 replica; 2 at 200) | 1.20 | 1.20 | 2.40 |
| HYBRID: a per-user subscriber, lock and quota inside the pool (T2) | 1.20 | 1.20 | 2.40 |

SILO terminal-api also hits the role limit: 10 copies × 2 connections = the whole `terminal_api_login` limit of 20
(FACT inputs, 2.6). Latency gains nothing: a burst of 60 users opening at once drops from 6-8 s today to 0.2-0.3 s with T2
+ T4 in the pool (`terminal.md`, INFERENCE), the same isolation SILO would give.

### 4.5 All three, and where SILO wins

| USD a month (light profile) | 10 users | 50 users | 200 users | Sessions that start cold |
|---|---|---|---|---|
| SILO, all three per user | 17.30 | 86.48 | 345.92 | 100 % |
| SILO, Screener + Backtest per user, terminal-api shared | 3.50 | 12.68 | 48.32 | 100 % |
| POOL-on | 15.81 | 15.99 | 17.86 | 0 % |
| POOL-window | 7.19 | 7.37 | 9.23 | 0 % inside the window |
| POOL-sleep | 3.46 | 4.42 | 6.38 | 26.6 % / 2.1 % / 0.5 % |
| HYBRID: POOL-on + 1 dedicated Backtest worker | 19.81 | 19.99 | 21.86 | 0 % |

INFERENCE:
- **SILO is dominated by POOL-sleep at every size**: equal cost at 10 users (3.50 against 3.46), 3× cheaper at 50, 8×
  at 200, and far fewer cold sessions.
- SILO (terminal-api shared) beats POOL-on below about 65 light users (23 heavy) and POOL-window below about 26 light
  users (10 heavy) (`silo_bench.md` §6.2). The most it saves is about USD 12 a month (10 users against POOL-on), paid
  for by a 14-27 s wait at the start of every session.
- Heavy profile (4 × 30 min a day): SILO 7.3 / 31.9 / 125.2; POOL-window 7.2 / 7.6 / 10.1; POOL-sleep 4.0 / 4.7 / 7.3.
- The money in SILO's repeated work is small (9,450 cold starts ≈ USD 1.5 of CPU at 200 users); the loss is waiting,
  limits, operations and version skew.

---

## 5. Accuracy

Every Screener answer is a pure function of (publication, engine version, canonical request); every Backtest result of
(files read, `engine_version`, request) (FACT, `RUNTIME.md` §8 A3, A4, A10). Accuracy therefore depends on every
instance loading the same verified publication and running the same code and limits.

| Risk | POOL | SILO | Label |
|---|---|---|---|
| Same published data version | 2 Screener replicas refresh all-or-nothing; requests pinned with `DATA_VERSION_PENDING` and a grace window; `snapshot_digest` compared across replicas (S22) (FACT, Screener build `refresh.ts:13-31`, `server.ts`) | N copies each load whatever is current when they wake or poll; up to N versions live during a publication; a copy whose refresh fails keeps the previous snapshot (`REFRESH_FAILED`) and serves one user stale data that only that copy's logs show | INFERENCE |
| Verification of bytes | sha256 and size on every use (FACT, `inflateVerified`) | the same in every copy | FACT, equal |
| Code version | 3 services, one deploy each; Railway healthcheck at deploy | N redeploys per release (20-600, `silo_bench.md` §6.4); a failed or skipped one leaves a user on an old `engine_version`, so two users get different numbers for the same request | INFERENCE |
| Config and limits | one set of variables per service (16 on backtest-worker, `.railway/railway.ts:176-180`) | N copies of every limit (timeouts, max conditions, budgets); one drifted value changes one user's refusals and results (A7) | INFERENCE |
| Cross-user leaks | shared caches hold no owner data (RP2); answers carry no owner fields | none by construction | FACT / INFERENCE |
| Backtest trial counting (Deflated Sharpe) | 1 RUNNING per owner, trials in Postgres | unchanged (trials are in Postgres) | INFERENCE |

Rule for any multi-instance setup, POOL included (PROPOSED): every answer carries its data version, engine version and
snapshot digest; edge-bff refuses an answer whose engine version differs from the release it expects, and a daily check
compares every instance's digest for the current publication. With 2-3 instances this is cheap; with N copies it becomes
a fleet audit.

---

## 6. Operations

| Area | POOL (3 services) | SILO (N users × 2-3 services) | Label |
|---|---|---|---|
| Services against the cap | 3 (plus 1 dedicated in HYBRID) | 21-30 at 10 users; 101-150 at 50 (over 100); 401-600 at 200 | INFERENCE from FACT cap |
| Creating copies | none | `serviceCreate` + `serviceInstanceUpdate` (sleep, replicas, healthcheck) + deploy, within 25 a day and 10,000 API calls an hour | FACT API (`silo_research.md` §2.6) |
| Deploys per release | 3; backtest-worker and terminal-api by CLI upload today (`.railway/railway.ts:175` comment; capacity report §2.1) | N × (CLI upload or image redeploy); AGENTS.md requires each deployment read back at `SUCCESS` | FACT / INFERENCE |
| Infrastructure as code | `.railway/railway.ts` by hand; `railway config pull --force` and `plan` after each change (AGENTS.md) | generated per copy or left out of IaC; drift already exists today for 3 services (capacity report §2.1: variables missing from `railway.ts`) | FACT / INFERENCE |
| Secrets | one worker key per service pair (`BACKTEST_WORKER_KEY` on edge-bff and worker) | one shared key across copies (one leak opens all) or N keys with a routing table; rotation N times | INFERENCE |
| Routing | fixed private hostname, enforced by config (`config.py:106, 118`) | a user → copy table in Postgres and a code change to edge-bff's hostname check | FACT / PROPOSED |
| Monitoring | Railway metrics per service; one trigger table (RUNTIME §10) | N dashboards; alerts per copy; "copy awake too long" becomes a cost alarm | INFERENCE |
| Database connections | terminal-api 2-4, edge-bff 6 per process | terminal-api per copy ≥ 2 (limit 20) | FACT |
| Worker data quota | one service account per worker (T1) | one per copy, or all copies on one account (265 MB a day at 10 users against the 300 MB default; 5.3 GB at 200) | FACT / INFERENCE |

---

## 7. Recommendation per service (PROPOSED)

### 7.1 Shape

| Service | Decision | Why (the deciding facts) |
|---|---|---|
| **screener-worker** | **POOL**: 2 replicas from the first external user (P32, decided), threads before replicas, owner lanes and per-owner CPU budget (P33, built), one shared snapshot per publication | The snapshot is identical for every user; a copy pays 14-27 s and 0.36-0.52 GB for nothing user-specific; per-user compute is milliseconds |
| **backtest-worker** | **POOL** with K job slots and P preview slots, fair claim by compute (B3, B4, X2). **HYBRID** only as an exception: a second worker service (B12 a) on trigger S-12, or a dedicated always-on worker for a paying or heavy tenant (about USD 4 a month) | The one real SILO gain, a private slot, is available in the pool; the pool shares the file cache across users |
| **terminal-api** | **POOL**, one subscriber, lock and quota per `owner_key` (T2), worker service accounts (T1) | It cannot sleep with a database pool, each copy takes 2 of 20 connections, and T2 gives the same per-user isolation |
| **Terminal page** | As is: per user in the browser | Already the cheapest per-user compute: the user's CPU, free bucket egress |

### 7.2 Sleep (Serverless) on the pool: always on at launch

This settles the difference between `RUNTIME.md` RT14 (always on) and `silo_bench.md` §0.8 (keep awake 14 h, sleep
otherwise). Decision: **RT14 for launch**; the window is a later switch with written conditions.

Why (INFERENCE from FACTs above):
- The saving is about USD 8.6 a month for all three together (15.81 → 7.19 at 10 users; 17.86 → 9.23 at 200).
- Outside the window (nights, weekends, when retail users often screen for the next week) the first user waits
  14-27 s for the Screener and about 5 s for a first backtest. That conflicts with "users must not wait long".
- It is not free to turn on: the Screener's 60-s poll must stop outside the window (code), both workers should listen on
  `::`, edge-bff must retry a wake (502 or refused) and show a "starting" state, and a cron or edge-bff call must wake the
  pool at 08:10 WIB. Railway also de-prioritizes slept workloads and a wake may need a rebuild (FACT, docs).

Switch to POOL-window for screener-worker and backtest-worker (terminal-api stays on) when all of these hold:
1. D4 and D5 (section 9) measured on Railway: the Screener's real cold start to `/ready`, and a wake of a 0.5 GB Node
   service over the private network with its 502 share.
2. The code conditions above are built and tested.
3. Either the user accepts the outside-window wait, or the cold start falls to about 8 s or less. A lead for that
   (PROPOSED, for the Screener build, not decided here): answer `/ready` after decode (FACT parts: boot 0.25-0.42 s +
   inflate 1.23-1.52 s + slice 1.54-2.09 s ≈ 3-4 s on one thread) and pre-warm in the background, computing a missing
   series on request (0.14-0.26 s for two series over 845 tickers, FACT). Same `series()` path, so the numbers do not
   change (A4); the owner CPU budget must not be charged for pre-warm work. If the container disk survives sleep (U3),
   the 11.8 MB download is skipped too.
4. Usage logs show the pool is idle long enough outside the window to matter.

backtest-worker is the easiest to sleep (no idle outbound traffic found, 2.3) but saves the least (about USD 2.4 a
month), so it follows the same switch rather than a separate one.

---

## 8. When a copy per user would be the better choice, and how to do it safely

### 8.1 Conditions (any one; cost alone is never one)

| # | Condition | What to copy | Label |
|---|---|---|---|
| C1 | A customer contract or regulator requires dedicated compute, and the customer pays at least the always-on cost (Screener USD 3.6-5.2, Backtest about USD 4 a month per copy) | a stamp for that customer (AWS premium-tier silo) | INFERENCE from AWS tiering |
| C2 | Per-user private data or untrusted per-user code (user-uploaded datasets, user-written strategy code) | a per-job sandbox, not a per-user service (the AI sandbox pattern, out of scope) | INFERENCE from Fly.io and Railway Sandboxes guidance |
| C3 | One tenant's steady load exceeds what lanes and budgets can contain (S-5 keeps firing for that owner) | a dedicated Backtest worker for that tenant (HYBRID) | INFERENCE from Azure noisy-neighbour guidance |
| C4 | One pool hits a platform ceiling (42 replicas, 24 vCPU / 24 GB per replica) | a second stamp per group of users (Deployment Stamps), not per user | INFERENCE; far beyond 200 users (RUNTIME §4.6 needs 2 replicas × 8 threads at U = 200) |

Not conditions: "fewer than about 26-65 light users" (a sleeping pool is as cheap and waits less), or "isolation from a
noisy neighbour" in general (lanes, P33 and the fair claim give it).

### 8.2 How, if ever chosen (PROPOSED design, each step needs the user's go)

1. **Unit:** a stamp per tenant or group, holding the Backtest worker (and the Screener only under C1); terminal-api and
   edge-bff stay shared.
2. **One image per release:** build once in CI, deploy every copy from the same image digest (Railway image sources
   exist in this IaC: `pgweb` uses `image("sosedoff/pgweb:0.17.0")`, `.railway/railway.ts:97`). Canary one copy, then the
   rest; stop at the first failure; every answer's engine version checked by edge-bff (section 5).
3. **Config:** every common value as a Railway shared variable, `${{ shared.VARIABLE_KEY }}`, which becomes a reference
   variable in each service (FACT, https://docs.railway.com/variables); per copy only its id and its key. Keys derived
   as HMAC(master, copy id) in edge-bff, so edge-bff holds one secret, not N; values sealed.
4. **Routing:** `edge_bff.stamp(owner_key → stamp_id, private host, state, engine_version)` in Postgres, with a
   migration; edge-bff's fixed-hostname check (`config.py:106, 118`) becomes an allowlist of registered stamps.
5. **Creation:** a small provisioning job calls `serviceCreate` and `serviceInstanceUpdate` (`sleepApplication: true`,
   healthcheck `/ready`, region `sfo`, memory limit), and keeps a few stamps pre-created (a warm pool, as Fly.io does)
   because of the 25-a-day cap; idle stamps are deleted with `serviceDelete` after an agreed period. Each run is logged
   (AGENTS.md requires `RAILWAY_CHANGELOG.md` for infrastructure changes; a provisioning log table plus a changelog
   summary needs the user's decision).
6. **Sleep for real:** no timer polls (read `/state` on request with the 60-s guard), no database pool, listen on `::`;
   edge-bff retries the first 502 or refused connection with back-off (the `price_update.py:96-134` pattern) and the page
   shows "starting".
7. **Data identity:** each stamp gets its own terminal service account (T1) so its grants and quota are its own.
8. **Monitoring:** logs labelled with the stamp id; alerts for a stamp on an old version, a failed refresh, or awake
   longer than its sessions (cost leak).
9. **Ceiling:** 100 services a project minus 28 today; past that, a second project loses the private network (public
   domain per copy, billed egress, auth on every copy), so about 70 single-service stamps is the practical limit.

---

## 9. What to measure on dev to confirm

| # | Measure | How | Settles | Needs approval |
|---|---|---|---|---|
| D1 | Memory billed while asleep | usage API per service (done here, 2.2) and repeated over a month | U1 | No (done, read-only) |
| D2 | Private-network wake reliability | the price crons' `telegram_notify_accepted` attempts (done here, 2.4: 7 of 8 at attempt 1); keep reading weekly | first-call failure share | No (read-only) |
| D3 | Public wake time spread | 10 timed `GET /health` on `telegram-trigger` across a day after `SLEEPING` is read (`silo_research.md` B1) | platform wake floor, 502 share | No (read-only GETs) |
| D4 | Real Screener cold start on Railway | first dev deploy of screener-worker (Phase 1c, already planned): refresh log fields per step (`download`, inflate, `defaults_ms`, `install_ms`, `presets_ms`) and the RSS curve, at 2 and 4 threads | S-U1, S-U2, U-RT7 | Yes (part of Phase 1c) |
| D5 | Wake of a realistic Node service | a throwaway Serverless service on dev holding about 0.5 GB, woken 20 times by a private call from a test job: first-response status (200, 502, refused), time to first answer, `0.0.0.0` against `::`, and a marker file written before sleep and read after (disk kept?) | S-U3, S-U4, U3 | Yes (creates a service; delete after) |
| D6 | Does a service really fall asleep | after D5's idle period, status `SLEEPING`; `railway logs --network` to list any outbound packet that keeps it awake | sleep fidelity | No for reading; D5's service for the test |
| D7 | Pool fairness under many owners | the shared load harness X4 (Screener S21/S23, Backtest L1, Terminal T12.3) at 1, 10, 50 synthetic owners | that the POOL gives SILO's isolation | Yes (temporary job service) |
| D8 | SILO control, only if the user wants the option measured | `serviceCreate` → deploy → `/ready` → first screen on one copy, then `serviceDelete`; time and API calls | creation time, the "minute or more" | Yes |

Order: D1-D3 now (read-only); D4 with the Screener's Phase 1c; D5-D6 only if the sleep switch of 7.2 is wanted; D7 in
Phase 0; D8 only on request.

---

## 10. Unknowns

| # | Unknown | Check |
|---|---|---|
| SP-U1 | Whether a container's disk survives sleep (Backtest cache, Screener download) | D5 marker file |
| SP-U2 | Wake time and 502 share for a 0.5 GB Node service over the private network | D5 |
| SP-U3 | Whether Railway flow logs are complete or sampled (2.3 relies on them for backtest-worker) | Railway docs, or D6 on a controlled service |
| SP-U4 | Whether this account counts as "new" for the 25-a-day cap; whether the 100-service cap can be raised | Railway support, only if SILO is ever chosen |
| SP-U5 | Real usage profile (sessions, hours, weekends) of external users | P29 numbers, then edge-bff logs per owner |
| SP-U6 | Screener cold start on Railway vCPUs against the sandbox Xeon | D4 |

---

## 11. Evidence made for this paper (read-only, 2026-10-28 about 20:10 UTC)

Saved under `mu_runtime/svp/` (no secrets; checked with `grep -il "token|secret|password"`, no match):

| Command | Output |
|---|---|
| `npx -y @railway/cli@5.71.0 api -f scratchpad/multiuser/usage.graphql --raw-var p=<project> --raw-var s=2026-10-24T00:00:00Z --raw-var e=2026-10-28T00:00:00Z` (and 10-21..28) | `usage_w4d.json`, `usage_w7d.json` |
| `railway metrics -s telegram-monitor -e dev --memory --since 7d --json --raw` | `tm_mem.json` |
| `railway logs -s idx-price-cron` and `-s idx-price-recovery-cron`, `--json --since 7d` | `cron_idx-price-cron.jsonl`, `cron_idx-price-recovery-cron.jsonl` |
| `railway logs -s backtest-worker --network --json --since 24h`; `-s terminal-api --network --since 2h` | `net_bt24.jsonl`, `net_terminal-api.jsonl` |
| WebFetch https://docs.railway.com/reference/app-sleeping and https://docs.railway.com/variables | quotes in 2.1 and 8.2 |

Repository files read (working tree at HEAD `a4e44b1`; the Screener build files may hold uncommitted edits): `.railway/railway.ts:95-190`; `apps/screener-worker/src/refresh.ts:15, 47, 213`;
`apps/screener-worker/src/server.ts:221-223, 376-379, 522`; `apps/backtest-worker/src/server.ts:334`;
`apps/terminal-api/app/store.py:24`; `apps/terminal-api/Dockerfile:10`; `apps/edge-bff/app/config.py:106, 118`;
`apps/edge-bff/app/backtest.py:42-44, 706, 934, 1056-1069`; `apps/idx-price-cron/price_update.py:96-134`;
`RAILWAY_CHANGELOG.md:3713-3716`; `apps/backtest-worker/README.md:422-440`; `verification/screener/AUDIT.md:133-140`;
`verification/edge_multiuser/capacity_fairness_scale_cost.md` §2; `PLAN.md:970-978`; `EXEC.md:8560-8567`.
