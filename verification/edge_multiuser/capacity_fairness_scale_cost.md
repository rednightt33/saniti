# EDGE multi-user: capacity, fairness, scale and cost across services (read-only planning, 2026-10-28)

Scope: PLAN.md EDGE-MULTIUSER (user 2026-10-28: "infrastruktur harus bisa di scale UP + efficient cost wise"; P29 "External /
Ini termasuk tab2 lagi ya monitor, terminal, backtest juga"; "YEs" to the report's recommendations for P24-P34 and D1-D14,
EXEC.md:8503-8516). This file covers capacity, fairness, horizontal scale and cost of terminal-api, backtest-worker,
screener-worker, edge-bff, market-ai-orc (with the sandbox and governors), Postgres and Railway. Identity and sessions are in
the sibling file `identity_sessions_per_user_state.md` (same folder) and are referenced, not repeated.

Read-only: no repository edit, no git change, no Railway mutation, no database write. Evidence was read on 2026-10-28 from:
the repository at branch `claude/charming-hamilton-faq25e` HEAD `ce941a3` (main `010af1e`; file:line below is HEAD unless
marked), the live database through pgweb (role `pgweb`, read-only; it cannot read schemas `terminal`, `edge_bff`, `ai_audit`,
only their statistics), and Railway through `@railway/cli@5.71.0` (`status --json`, `metrics`, `variables --json` keys only,
`postgres pgbouncer status`, `postgres pitr status`, GraphQL `usage` grouped by service). No secret value was printed.

Labels: FACT (with file:line, query or command), INFERENCE, PROPOSED, UNKNOWN. Prices as in the Screener report 6d (Railway
docs read 2026-10-28): RAM USD 10 per GB-month, vCPU USD 20 per vCPU-month, egress USD 0.05/GB, volume USD 0.15/GB-month,
bucket egress free, private network free.

---

## 1. Key findings (one screen)

1. **AI chat (Monitor) runs one message at a time for all of EDGE.** FACT: edge-bff starts one Orc job loop
   (`apps/edge-bff/app/main.py:191`), which claims one job and awaits it to the end before claiming the next
   (`apps/edge-bff/app/worker.py:32-43`, claim `store.py:158-169`). Measured AI runs average 100-200 s, p90 250-450 s
   (live `AI_research_run_audit`, 495 runs 2026-10-07..26, query in 3.2). INFERENCE: two users sending at once already
   queue; with 10 the last waits about 25 minutes. This is the first multi-user blocker and is not in the Screener
   report's 6d.
2. **Behind it, AI concurrency is capped at 4 analysis sessions per sandbox, and the sandbox cannot add replicas.** FACT:
   `PY_SANDBOX_MAX_SESSIONS` is capped at 4 in code (`apps/market-python-sandbox/app/config.py:287`), dev sets 4
   (`PROJECT_CONTEXT.md:53`); the sandbox has a volume, so one replica (`PROJECT_CONTEXT.md:87`); orc keeps its stop
   registry and progress in memory "because the service runs one replica" (`apps/market-ai-orc/app/stop.py:7-8`,
   `app/progress.py:24`).
3. **Backtest: one job and one preview at a time for all of EDGE, first come first served across owners.** FACT: one job
   thread and one preview thread (`apps/backtest-worker/src/server.ts:108`, `409 BUSY` at 270/277); edge-bff's claim
   takes the oldest QUEUED job of any owner with nothing RUNNING (`apps/edge-bff/app/backtest.py:516-527`). INFERENCE: with
   one slot this is FIFO, not a rotation: an owner's three queued jobs submitted first all run before another owner's
   (correction to 6d.8 E5, which says the claim already rotates). A job may hold the slot up to `BACKTEST_TIMEOUT_SECONDS`
   900 (`apps/backtest-worker/README.md:220`).
4. **terminal-api: one gateway account for everyone.** FACT: every proxied request is the one subscriber
   `TERMINAL_PROXY_SUBSCRIBER` (`apps/terminal-api/app/main.py:174-180`); every grant takes that subscriber's advisory lock
   and recomputes usage from the day's `terminal.access_log` rows (`store.py:44-67`); quotas overridden to 1e9, TEMPORARY
   (`BACKTEST_END_TO_END.md:321-322`). Measured: 20 concurrent `/bundle` median 0.53 s, max 0.71 s; quota count 0.85 ms
   (`ERRORS_AND_SOLUTIONS.md:2302-2305`). INFERENCE: not the first bottleneck (about 40 grants/s), but per-user identity
   and quotas are a precondition for external users (P31).
5. **The project is on Railway Pro.** FACT: `railway status --json`, edge-bff deployment `32a25029` `meta.plan = "pro"`;
   per-replica limits shown by `railway metrics` are 24 vCPU / 24 GB (Postgres 4 GB). This settles 6d M-U1 (plan) for the
   GitHub-built services. Replica ceiling: Pro 42 per service (pricing page, 6d) and the CLI's `scale` help says "Maximum:
   50 total replicas across regions".
6. **Today's platform costs about USD 33 a month in usage (dev, one user), two thirds of it RAM.** FACT from the usage API
   (2026-10-24..28, scaled to 30 days): RAM 22.05, volumes 8.41, CPU 2.12, egress 0.85. Postgres 13.86 (of which its 51 GB
   volume 7.65), sandbox 7.24, every EDGE-path service USD 0.5-1.6 each (table 2.2). The Postgres page-cache episode
   (about USD 60/month at 6 GB, `RAILWAY_CHANGELOG.md:4222-4225`) is over: 0.51 GB average since the 4 GB limit.
7. **The marginal cost of an external user is almost all AI tokens.** INFERENCE (5.3): infrastructure about USD 0.1 per
   active user-month for Terminal, Backtest, Screener, egress and storage together; AI USD 2-30 per active user-month at
   USD 0.02-0.07 per AI turn (FACT samples, 3.2). There is one shared OpenRouter key with a USD limit the user raises by
   hand (`RAILWAY_CHANGELOG.md:1136`, 233: a stage was skipped when the key had USD 0.007 left) and no per-owner budget in
   orc (FACT: no match for an owner budget in `apps/market-ai-orc/app/*.py`). One user can exhaust AI for everyone.
8. **Per-role connection limits, not `max_connections`, bound horizontal scale.** FACT (live `pg_roles`):
   `edge_bff_login` 20, `terminal_api_login` 20, `market_ai_orc` 5, `market_ai_conversation` 10, `market_ai_audit` 10,
   `market_sql_governor` 5, `terminal_publisher_login` 4; `max_connections` 500. Pools: edge-bff 6 per process
   (`store.py:27`), terminal-api 8 per process × 2 processes (`apps/terminal-api/app/store.py:24`, `Dockerfile:10`) = 16 of
   20, so terminal-api cannot add a replica without a role change; orc opens a new connection per call
   (`apps/market-ai-orc/app/conversations.py:235-237`). No PgBouncer, no HA, PITR disabled (FACT, `railway postgres
   pgbouncer status`, `pitr status`).
9. **Postgres runs with `shared_buffers` 128 MB, `work_mem` 4 MB, 4 GB memory limit.** FACT (live `pg_settings`): buffer
   hit 89.8 % over 6.4 days, 17,302 temp files, 371 GB spilled (`pg_stat_database`). INFERENCE: user-facing AI SQL shares
   this with batch work; concurrent external AI use will need memory and tuning before more connections.
10. **There is no production environment.** FACT: "one environment, `dev`; there is no production yet"
    (`BACKTEST_END_TO_END.md:656`). External users on `dev` share it with tests, golden runs and manual deploys.

---

## 2. Measured baseline

### 2.1 Railway topology (FACT, `railway status --json` 2026-10-28)

| Service | Region / replicas | Process model | Volume | Built from |
|---|---|---|---|---|
| edge-bff | sfo / 1 | uvicorn `--workers 1` (`.railway/railway.ts:184`) | none | GitHub `main` |
| terminal-api | sfo / 1 | uvicorn `--workers 2` (`apps/terminal-api/Dockerfile:10`) | none | CLI upload |
| backtest-worker | sfo / 1 | node, 2 compute threads | none (disk cache on container disk, `BACKTEST_CACHE_DIR` set) | CLI upload |
| screener-worker | not created yet | (designed in 6d) | none (designed) | GitHub `main` (P3) |
| market-ai-orc | sfo / 1 | uvicorn, 1 process, sync route `def run_agent` (`app/main.py:694-696`) | none | GitHub `main` |
| market-python-sandbox | sfo / 1 | ≤ 4 analysis sessions | `/data` volume, so 1 replica | GitHub `main` |
| market-sql-governor, market-web-governor, market-audit-store | sfo / 1 each | uvicorn | web-governor `/data` volume | GitHub `main` |
| Postgres | sfo / 1, 4 GB limit | PG 18.6 | 51 GB used (volume) | image |
| Buckets | `terminal-display` sin; others sjc | | | |

Variable names only (FACT, `railway variables --json`, keys printed): terminal-api has `TERMINAL_PROXY_KEY` and
`TERMINAL_PROXY_SUBSCRIBER`; edge-bff has `EDGE_TERMINAL_URL` and `TERMINAL_PROXY_KEY`; backtest-worker has
`BACKTEST_CACHE_DIR` and `BACKTEST_CACHE_DIR_BYTES`. None of these is declared in `.railway/railway.ts` (lines 158-161,
176-190). INFERENCE: config-as-code drift to settle with `railway config pull --force` when EDGE-MULTIUSER touches Railway.

### 2.2 Usage and cost per service (FACT: GraphQL `usage(projectId, 2026-10-24..2026-10-28, groupBy SERVICE_ID)`, scaled ×7.5 to 30 days)

| Service | avg vCPU | avg RAM GB | volume GB | USD/month (CPU+RAM+egress+volume) |
|---|---|---|---|---|
| Postgres | 0.048 | 0.513 | 51.0 | 13.86 |
| market-python-sandbox | 0.023 | 0.663 | 1.2 | 7.24 |
| market-sql-governor | 0.003 | 0.144 | | 1.59 |
| terminal-api | 0.004 | 0.142 | | 1.52 |
| market-web-governor | 0.002 | 0.127 | 0.8 | 1.42 |
| market-ai-orc | 0.002 | 0.130 | | 1.34 |
| pgweb | 0.000 | 0.095 | | 1.04 |
| edge-bff | 0.006 | 0.082 | | 1.00 |
| market-audit-store | 0.003 | 0.078 | | 0.84 |
| backtest-worker | 0.001 | 0.049 | | 0.51 |
| everything else | | | | 2.07 |
| **Total** | | | | **33.43** (RAM 22.05, volumes 8.41, CPU 2.12, egress 0.85) |

Cross-checks: the windows 10-14..21 (7 days), 10-21..24 and 10-24..28 add up consistently (total RAM 26,282, 16,027 and
12,728 GB-minutes). A single query for 10-01..27 returned less than the last week alone, so month-long windows of this API
are not used here (UNKNOWN why). Workspace billing (`railway usage`) is not readable with the project token
(UNAUTHORIZED), so the invoice and the Pro fee treatment are UNKNOWN; Pro is USD 20 a month including USD 20 of usage (6d).
One service id with a 1.7 GB volume (`7af77ccf…`) is not in the dev instance list (UNKNOWN which).

Live load signals (FACT): edge-bff HTTP last 16 h 254 requests, p50 1,065 ms, p90 1,935 ms, 0 5xx (`railway metrics
--http`; mixed routes including long relays and SSE, so not a per-route latency). Current client connections visible:
`edge_bff_login` 3, `terminal_api_login` 5 (`pg_stat_activity`).

### 2.3 Postgres (FACT, live)

- `max_connections` 500, `superuser_reserved_connections` 3, `shared_buffers` 16384 × 8 kB = 128 MB, `work_mem` 4 MB,
  `effective_cache_size` 4 GB, `max_parallel_workers` 8; database 42 GB; largest tables `Feature_02_Broker_Rolling` 15 GB,
  `IDX_Broker_Summary` 10 GB, `Feature_05_…_Detail` 9.8 GB.
- Role settings (`pg_db_role_setting`): `edge_bff_login` statement 5 s; `terminal_api_login` 10 s; `market_ai_orc` 5 s
  read-only; `market_sql_governor` 60 s read-only; `terminal_publisher_login` 120 s.
- Since start 2026-10-22: 8.1 M commits, buffer hit 89.78 %, 17,302 temp files (371 GB), 3 deadlocks.
- EDGE tables are small: `terminal.access_log` 6,918 rows (since 2026-10-25), seq_scan 3,886 against idx_scan 488;
  `edge_bff.backtest_results` 204 parts, 6.2 MB for 46 jobs (about 136 KB per job); AI conversation tables about 60 KB per
  turn and `ai_audit` about 120 KB per run (sizes from `pg_class`, row estimates).

---

## 3. Per service: today, the multi-user limit, what blocks more replicas, proposals

### 3.1 edge-bff (the one public entry)

**Today (FACT).** One process, one replica (`.railway/railway.ts:184-187`; README "Use one uvicorn process/one replica
initially … authentication attempt limiting is process-local", `apps/edge-bff/README.md:412-413`). Pool 1-6 connections
(`store.py:27`), every DB and Orc call through `asyncio.to_thread`. Two background loops in the process: the Orc job loop
(one job at a time, finding 1) and the Backtest loop (one job at a time, `backtest.py:629-650`). Every response without its
own header gets `Cache-Control: no-store` (`main.py:254`), including `index.html` (474 KB, 103 KB gzip; no gzip middleware in
`main.py`), so every page open re-downloads it unless Railway's edge compresses (UNKNOWN).

**What blocks more than one process or replica.**

| Item | Effect with N > 1 | Evidence | Proposal |
|---|---|---|---|
| Sign-in limiter in memory, keyed by the TCP peer under `--no-proxy-headers` | 5 × N per key; and the key is likely Railway's edge, a global lockout today | `main.py:179, 440-449`; sibling file §2.1 | Postgres per login and per client IP (sibling file, E2) |
| Orc job loop in every process | N processes run N AI jobs at once with no global cap (SKIP LOCKED keeps them safe) | `worker.py:32-43`; `main.py:191` | PROPOSED: a separate service `edge-bff-worker` (same image, `EDGE_WORKER_ENABLED=true`, no public domain) and web replicas with it false; inside it K concurrent Orc dispatch tasks (K ≤ sandbox slots), fair per owner (4) |
| Backtest loop in every process | N loops claim N jobs (state RUNNING, lease, deadline running) but the one worker answers BUSY to all but one; the others spin on BUSY until their deadline (`backtest.py:766-781`) | INFERENCE from the code | same split: loops only in `edge-bff-worker`; job slots = worker slots (3.3) |
| Preview latest-wins maps (Backtest, Screener) | order kept per process only; cost, not correctness (6d.5) | `backtest.py:934-936, 1002-1033` | keep |
| Pool vs role limit | N × 6 ≤ 20, so N ≤ 3 | `store.py:27`; live `rolconnlimit` | raise `edge_bff_login` by migration, or PgBouncer (3.6) |
| Screener catalog cache | safe with the monotonic rule | `apps/edge-bff/app/screener.py:1-12` (branch) | keep |

**Capacity (INFERENCE).** Per request: a session `SELECT` (about 4 ms over a static file, 6d) plus a relay. Open SSE
streams poll the database every `EDGE_POLL_SECONDS` 2 s (`main.py:557-575`). The limit is the event loop and the default
thread pool (`min(32, cpu+4)` threads) in front of a 6-connection pool; it is unmeasured (6d S25).

**Proposals (PROPOSED).** (a) Split web and loops as above before any replica. (b) Serve `index.html` with gzip and an
`ETag`/short `max-age` instead of `no-store` (UI shell only; data stays `no-store`). (c) Scale order: `--workers 2`, then
replicas, within the role limit. (d) The sign-in limiter and accounts as in the sibling file.

### 3.2 market-ai-orc, the sandbox and the governors (the Monitor tab)

**Today (FACT).**
- One replica; `/v1/agent/run` is a sync route held for the whole run (`app/main.py:694-696`), so runs share FastAPI's
  thread pool (anyio default 40, INFERENCE) with the progress, request and message routes.
- Stop registry and progress live in memory (`app/stop.py:7-8, 16-17`; `app/progress.py:24`); conversations use Postgres
  leases, one running message per conversation (`app/conversations.py:10-12`).
- Owner comes from `X-Saniti-Owner` (`app/conversations.py:97-103`); edge-bff sends `settings.owner` for everyone (sibling
  file §2.5).
- Run time budget: `AI_MAX_ANALYSIS_SECONDS` 1800 on dev and mode 4 up to `AI_MODE4_MAX_SECONDS` 3600
  (`AI_MODELS.md:161`; `app/config.py:375-416`); edge-bff waits up to `EDGE_ORC_TIMEOUT_SECONDS` ≥ 3900 (`config.py:125`).
- Sandbox: ≤ 4 sessions (code cap), container limit 24 GB / 24 vCPU, sessions of up to 4096 MB (`PROJECT_CONTEXT.md:53`).
- Governor: role limit 5, statement timeout 60 s; `SQL_HEAVY_QUERY_CONCURRENCY` is set on Railway (value not read).
- Cost is computed per run (`app/orchestrator.py:2693`, audit outbox field `cost`, `app/audit_outbox.py:146`) and per model
  call in the logs (`app/provider_log.py:48` `total_cost`), but nothing enforces a per-owner budget. The web governor
  already keeps calls and cost per user turn in `web_orc_budget` (`PROJECT_CONTEXT.md:14`): a precedent.

**Measured AI load (FACT, `public."AI_research_run_audit"`, 2026-10-07..26).** 495 runs (about 23 a day of dev testing);
DeepSeek V4.1 Flash 375 runs, average 459k total tokens, 9.2 tool calls, 155 s; daily average duration 28-290 s, daily p90
57-923 s; statuses: 417 COMPLETED, 30 LIMITED, 20 FAILED, 19 AWAITING_CONFIRMATION, 9 NEEDS_CLARIFICATION. The `budget`
JSON's `cpu_seconds.used` is 0 in all 292 rows that carry it (not usable for sandbox CPU).

**Recorded cost per AI turn (FACT, `RAILWAY_CHANGELOG.md`).** Router-only greeting USD 0.0004, FACT 0.001, ANALYSIS
0.004-0.016 (1092-1097); suites: 31 turns USD 2.19 (0.071 per turn, 1192), 33 turns 0.92 (0.028, 1926), 33 turns 0.64
(0.019, 2013), 10 turns 0.63 (0.063, 894). Web `/v1/ask` budget USD 0.05 per question (1827). Range used below: USD
0.02-0.07 per AI turn, central 0.03.

**Concurrency (INFERENCE, Little's law).** A user who sends, waits about 155 s and reads about 120 s keeps a run busy 56 %
of the time. Concurrent users served without queueing ≈ slots / 0.56: today 1 slot (edge-bff) → about 2 users; with the
edge-bff loop fixed, 4 sandbox sessions → about 7 users per sandbox (fewer if a run opens several sessions; more if many
turns are CHAT/FACT without the sandbox).

**What blocks more replicas.**
- orc: in-memory stop and progress (a stop or progress call may reach another replica); Railway has no sticky sessions
  (6d). Options: (a) keep 1 orc replica and scale it vertically (threads, the 24 vCPU / 24 GB ceiling) — the run is mostly
  waiting on the model; (b) move stop flags and progress to Postgres (the conversation lease row already exists).
  PROPOSED (a) until a measured trigger; orc is not CPU-bound (0.002 vCPU average).
- sandbox: volume-pinned and code-capped at 4 sessions. Options: (a) raise the code cap after a memory test (24 GB / 4 GB
  per session allows about 5); (b) shard: `market-python-sandbox-2..n` services, each with its own volume, orc picks a
  shard per conversation (affinity by conversation id, since reuse of extracted data is per conversation,
  `PROJECT_CONTEXT.md:53`); (c) move its SQLite state off the volume. PROPOSED (b) when the trigger fires; it keeps the
  isolation model.
- governor: role limit 5 → the cap on concurrent AI SQL; raise with the measured Postgres headroom.
- web-governor: volume-pinned; low use; keep 1.

**Fairness and budget (PROPOSED).** One running message per owner (edge-bff's `edge_bff_one_active_owner` index already
gives this, migration `20261008_002:47-48`) plus a round-robin claim over owners; a per-owner AI budget per day in USD
taken from orc's own run cost, checked before dispatch, with its rule, how to pass it, a right and a wrong example and a
refusal message naming the limit and the reset time (AGENTS.md "Gates and evidence"); an alert at a share of the
OpenRouter key limit. Decision for the user: whether external users get AI at all and their budget (PLAN.md EDGE-MULTIUSER
open question).

### 3.3 backtest-worker (the Backtest tab)

**Today (FACT).** One job thread and one preview thread; one job kept in memory, its result kept until the next job
(`server.ts:1-30, 108`); previews wait in an unbounded arrival-order queue (`server.ts:199-235`), bounded in practice by
edge-bff's one preview per owner. Cache: `BACKTEST_CACHE_BYTES` 1.5 GB per thread (memory) and a 1 GB disk cache
(`README.md:210-211`). Timeout 900 s (`README.md:220`).

**Measured (FACT, `apps/backtest-worker/README.md:422-440`).** Single job 0.45-1.31 s in the worker, 5.0-5.9 s submit to
end (edge-bff polls every 2 s); 12-stock portfolio 5.5-7.05 s in the worker, 10.8-12.4 s submit to end, 28.35 MB on a cold
run; RAM one-minute peak 1.31 GB, idle 0.32 GB (now 0.049 GB average, 2.2); CPU peak 0.43 vCPU.

**Throughput (INFERENCE).** One slot serves about 5-12 s per job end to end, so at most 300-700 jobs an hour, and one
900 s job blocks everyone. A concurrent user running one portfolio a minute uses about 12 % of the slot: about 6 such users
per slot at 70 % utilisation. FIFO across owners (finding 3).

**What blocks more replicas.** The job and its result live in one process; with random routing (no sticky sessions, 6d)
edge-bff's `GET /v1/jobs/{id}` and `/result` could reach a replica that does not hold the job (404 `UNKNOWN_JOB` → treated
as lost). Options:
- (a) more job threads in one process (vertical): the slot count becomes K; RAM grows by up to one 1.5 GB cache per thread
  (lower `BACKTEST_CACHE_BYTES` per thread or share the disk cache, which already spans threads);
- (b) several worker services (`backtest-worker`, `backtest-worker-2`, …) each with its own private hostname; edge-bff
  holds one dispatch slot per service and records which service holds the job (a column on `backtest_jobs`): job affinity
  without sticky sessions;
- (c) results pushed by the worker to storage (it has no database credentials by design; a bucket write needs credentials
  it does not hold today).
PROPOSED: (a) to K = 2 after a parity and memory test, then (b); edge-bff claim changed to round-robin over owners (the
owner whose last job started longest ago first) with the per-owner queue of 3 kept (`config.py:37`) and a per-owner jobs
per day limit if P33-style budgets extend to the Backtest (user decision). Previews: one per owner in flight already;
round-robin the worker's preview queue by an owner tag (as the Screener's `x-screener-owner`).

### 3.4 terminal-api (Terminal tab, and the files of Backtest and Screener)

**Today (FACT).**
- Gateway identity: requests with `x-terminal-proxy-key` act as the one subscriber `TERMINAL_PROXY_SUBSCRIBER`
  (`main.py:157-180`); edge-bff forwards every Terminal call with that key (`apps/edge-bff/app/main.py:398-431`);
  backtest-worker and screener-worker use the same key (`BACKTEST_END_TO_END.md:313-325`). `/xsection` admits the gateway
  key only (`main.py:190-198, 418-440`).
- Quotas (`database/migrations/20261025_100_create_terminal_schema.sql:79-88`): files 60/h, tickers 30/h and 150/day,
  300 MB/day, history 20/h, URL TTL 120 s, 2 sessions; the gateway subscriber overridden to 1e9, TEMPORARY
  (`verification/terminal_api/jobs/quota_unlimited_edge_owner.sql`).
- Every grant: per-subscriber `pg_advisory_xact_lock` (`store.py:44-46`), limits, usage aggregated from the subscriber's
  last day of `access_log` (`store.py:55-67`), one audit row per `/bundle` (`file_count`, migration `20261026_100`);
  presigned URLs are signed locally and the browser downloads from the `sin` bucket (free egress).
- Every Terminal ticker open calls `/bundle` even when the files are in the browser cache (`apps/edge-bff/terminal/src/data/
  live.ts:82-83, 159-165`), and `grant()` counts every granted file's bytes (`main.py:340-361`). INFERENCE: quotas count
  grants, not downloads; a cached re-open uses quota.
- Pool 8 per process, 2 processes = 16 of the role's 20.

**Capacity (INFERENCE).** About 25 ms serialized per grant under the one lock (20 concurrent → median 0.53 s) → about 40
grants/s; a user opening a ticker every 10 s → about 280 concurrent users at 70 %. Not first to break; becomes per-user
once accounts exist.

**What per-user identity and quotas need (PROPOSED, P31 decided as "identitas terminal-api per user plus akun layanan
untuk worker", EXEC.md:8508-8509).**
1. **Per-user subscriber via the gateway.** edge-bff forwards the session's `owner_key` in a header accepted only with the
   valid proxy key; terminal-api maps it to a `terminal.subscriber` row (new nullable unique column for the EDGE owner),
   created with the EDGE account (admin route) or on first use with default quotas. Locks, quotas and audit become per
   person; the global serialization disappears.
2. **Service accounts for the workers.** `backtest-worker` and `screener-worker` each get their own key and subscriber row
   with quotas sized to their measured use (a cold 12-stock portfolio is 28 MB; the Screener 15-30 MB per publication per
   replica, 6d.7). User fairness for worker downloads stays in edge-bff (jobs per owner), because the worker's caches serve
   many users from one download; charging those bytes to one user at terminal-api would be wrong.
3. **Counters instead of log aggregation** (`FUTURE_PLAN.md:907-924` item b): a per-subscriber row per hour and per day
   updated in the grant transaction, so a check is one indexed `UPDATE … RETURNING`, independent of log size; the log stays
   for audit (90 days).
4. **Quota sizing for the Terminal tab.** With packs a stock `/bundle` grants about 5 files (`ERRORS_AND_SOLUTIONS.md:2304`),
   so `files_per_hour` 60 allows about 12 ticker opens an hour: too few for an external Terminal user. Count opened tickers
   (already `tickers_per_hour`) and bytes, and let the page send the sha256 values it already holds so terminal-api grants
   and counts only missing files (PROPOSED; it also saves presign work). Values per user tier are the user's decision.
5. **Role limit.** A second terminal-api replica needs `terminal_api_login` > 20 or a smaller pool.

### 3.5 screener-worker (designed in 6d; decisions now taken)

With "YEs" (EXEC.md:8504-8510): P32 two replicas from the first external user, P33 a per-user CPU budget built in the
Screener, P34 per-replica caches. 6d's design holds (stateless replicas, snapshot per publication, threads before replicas,
owner lanes, about 37 editing users per replica at K = 2, cost about USD 5-8 per replica a month). Two consequences:
- **P33 with P32 (INFERENCE).** A per-owner bound enforced inside each worker replica becomes up to R × the bound with R
  replicas (6d.6). With R = 2 from the first external user, the budget belongs where every request passes once: edge-bff,
  charged from each answer's `timings_ms` after the fact and checked before the next call; in Postgres if edge-bff has
  more than one replica. PROPOSED: one usage ledger for all tabs (section 4) instead of a Screener-only counter.
- **Cost (6d.9, INFERENCE).** 2 replicas × about 0.6 GB → about USD 12 a month fixed; per user about USD 0.01 a month of
  CPU.

### 3.6 Postgres

**Today (FACT).** Single instance in `sfo`, 4 GB limit, 0.51 GB average RAM since the limit, 0.048 vCPU average; no
PgBouncer, no HA, PITR disabled; `shared_buffers` 128 MB, buffer hit 89.8 %, 371 GB of temp spills in 6.4 days.

**Connection budget (FACT role limits; INFERENCE sums).** Sum of the limited roles = 79 (edge 20, terminal 20,
conversation 10, audit 10, orc 5, governor 5, pgweb 5, publisher 4) plus `postgres` and `market_ai_app` (unlimited).
Each backend costs memory (INFERENCE: several MB, more with `work_mem` sorts), so 4 GB, not `max_connections` 500, is the
real ceiling. PROPOSED: PgBouncer in transaction mode before total connections pass about 60-80 or before edge-bff and
terminal-api scale out; check first that psycopg's automatic prepared statements are off or supported
(`prepare_threshold`), and that only transaction-level advisory locks are used (FACT: `pg_advisory_xact_lock` in
terminal-api `store.py:46` and edge-bff `screener.py:445`, which suit transaction pooling).

**Storage growth per user (INFERENCE from sizes in 2.3).** AI about 180 KB per turn (conversation + audit), Backtest about
136 KB per job (30-day results; trials never purged, `BACKTEST_END_TO_END.md:689`), Terminal about 1 row per ticker open
(90 days). At 10 turns and 20 jobs per trading day, about 0.1 GB per active user-month: USD 0.015 of volume, but working-set
RAM and vacuum load grow with it.

**Availability (UNKNOWN target).** No HA and no PITR on the database every tab depends on; the user's availability target
for external users is not recorded.

---

## 4. Fairness model across tabs (PROPOSED)

| Layer | Monitor (AI) | Backtest | Screener | Terminal |
|---|---|---|---|---|
| In flight per owner | 1 running message (exists) | 1 running job, 3 queued (exists); 1 preview (exists) | 1 run + 1 preview per (owner, page) (6d) | browser-driven |
| Scheduling across owners | round-robin claim, K slots ≤ sandbox sessions | round-robin claim, K job slots | owner lanes, deficit round robin (6d) | per-user lock after P31 |
| Per-owner budget (decided for the Screener, P33; the others are the user's decision) | USD per day from orc's run cost | jobs (or job-seconds) per day | CPU ms per minute | tickers/bytes per day (terminal quotas) |
| Where enforced | edge-bff before dispatch | edge-bff claim/submit | edge-bff (single entry), worker lanes as backstop | terminal-api |

One ledger table in `edge_bff` (owner, feature, window start, units) written by edge-bff from the answers it already
relays (orc run cost, backtest `duration_ms`, screener `timings_ms`), read before admitting the next request. Each refusal
gets the four parts AGENTS.md requires. Tiers (P29 open question "paket atau kuota berbeda per user") become a per-owner
row of limits, like `terminal.quota_override`.

---

## 5. Cost model

### 5.1 Formula (INFERENCE)

```
monthly_usd = F_platform
            + Σ_services extra_replicas × replica_usd            (capacity, from the triggers in section 6)
            + N × (m_ai + m_infra)                               (per active user)

F_platform  ≈ 33.4  today's usage (2.2), of which volumes 8.4
            + 12    screener-worker × 2 replicas (P32, 6d.9)
m_ai        = trading_days × turns_per_day × c_turn              (c_turn USD 0.02-0.07, FACT samples 3.2)
m_infra     = backtest + screener + terminal + egress + storage  (≈ USD 0.1, 5.3)
replica_usd = 10 × RSS_GB + 20 × avg_vCPU                         (per month)
per concurrent hour: RAM USD 0.0139 per GB-hour, CPU USD 0.0278 per vCPU-hour
```

### 5.2 Inputs per concurrent user (what one more user at the same moment occupies)

| Tab | Occupies while active | Cap today | Infra USD per concurrent user-hour (INFERENCE) |
|---|---|---|---|
| Monitor | 1 AI slot, 1 orc thread, a sandbox session when it analyses, governor connections | 1 run for all EDGE (edge-bff); 4 sessions (sandbox) | session 1-4 GB + about 1 vCPU while computing: USD 0.04-0.08; tokens about USD 0.4-1.4 at 20 turns an hour |
| Backtest | a share of 1 job slot (5-12 s per job) and 1 preview thread | 1 job, 1 preview for all EDGE | CPU about 7 vCPU-s per job: under USD 0.001 at 10 jobs an hour; the cost is the worker's resident cache, fixed |
| Screener | an owner lane; uncached runs 0.5 vCPU-s | about 37 editing users per replica at K = 2 (6d) | about USD 0.001 |
| Terminal | 1 grant per ticker open (about 25 ms serialized today) | about 40 grants/s | negligible; downloads from the bucket are free |
| edge-bff | session check per call, SSE poll every 2 s while a run is watched | unmeasured | negligible until a second replica is needed |

### 5.3 Per active user per month (INFERENCE; inputs to be replaced by P29 numbers and logs)

Assumed profile: 21 trading days, 10 AI turns, 20 backtest jobs, 200 Screener runs, 50 ticker opens and 20 page opens a day.

| Component | Arithmetic | USD/user-month |
|---|---|---|
| AI tokens | 21 × 10 × 0.03 (range 0.02-0.07, 5-20 turns) | **6.3** (2.1-29.4) |
| Backtest CPU | 420 jobs × 7 vCPU-s × 20/2,592,000 | 0.02 |
| Screener CPU | 6d.9 | 0.01 |
| Terminal (terminal-api CPU, audit rows) | 1,050 grants × about 30 ms | < 0.01 |
| Egress | index.html 0.47 MB × 420 opens + API about 0.2 GB = about 0.4 GB × 0.05 | 0.02 |
| Postgres storage | about 0.1 GB × 0.15 | 0.02 |
| **Total** | | **≈ 6.4** (infra ≈ 0.08; AI ≈ 98 %) |

### 5.4 Scenarios (INFERENCE; the capacity column follows section 6)

| Daily users (at once) | Capacity added | Fixed USD/month | Per-user USD/month × N | Total | Per user |
|---|---|---|---|---|---|
| Dev today: 1 (1) | none | 33 | 6 | ≈ 40 | 40 |
| 10 (3) | screener ×2; edge-bff web/worker split; AI K = 2-4 slots | ≈ 50 | 64 | ≈ 115 | 11.5 |
| 50 (15) | + sandbox shard 2 (about 8), backtest K = 2 or a 2nd worker (5-13), Postgres +2 GB (20), PgBouncer (1) | ≈ 95 | 320 | ≈ 415 | 8.3 |
| 200 (60) | + sandbox 4 shards (about 30), backtest 3 slots (about 30), edge-bff ×3, terminal-api ×2, Postgres 8 GB (+40) | ≈ 165 | 1,280 | ≈ 1,445 | 7.2 |

Reading: infrastructure stays a small fixed cost that grows in steps; AI tokens scale linearly with use and dominate from
the first external users. The efficiency levers are therefore per-user AI budgets and routing cheap turns to the router
(CHAT USD 0.0004), not infrastructure tuning. The Screener's and Terminal's shared, per-publication computation keeps their
marginal cost near zero (6d.2).

---

## 6. Scaling triggers and what to measure (PROPOSED thresholds; to be set from a load test)

| # | Signal (source) | Threshold | Action |
|---|---|---|---|
| T1 | AI queue wait: age of the oldest QUEUED `edge_bff.jobs` row, p95 over 15 min in market hours | > 30 s | raise K Orc dispatch slots up to free sandbox sessions; then a sandbox shard |
| T2 | Sandbox sessions busy (sandbox logs; open waits/refusals) | 4/4 for > 5 % of market minutes | sandbox shard (3.2 option b) |
| T3 | AI spend per day (orc run cost; OpenRouter `GET /api/v1/key`) | > 50 % / 80 % of the key limit; any owner over budget | alert / refuse per owner (budget gate) |
| T4 | Backtest queue wait: oldest QUEUED `backtest_jobs`, p95 | > 30 s | K = 2 job threads, then a second worker service |
| T5 | Backtest worker RSS (Railway metrics) | > 70 % of its limit | lower per-thread cache or raise limit |
| T6 | terminal-api `/bundle` p95 (edge-bff relay timing) and grant time | > 1 s / > 50 ms | per-user identity (P31) if not done; then counters |
| T7 | edge-bff event-loop lag p95, pool waits (psycopg_pool stats), 5xx | > 50 ms or waits > 0 at peak | `--workers 2`, then replicas within the role limit |
| T8 | Connections per role vs `rolconnlimit` (`pg_stat_activity` as a privileged role) | > 70 % | raise the role limit by migration or add PgBouncer |
| T9 | Postgres RAM vs 4 GB, buffer hit, temp spills during market hours | > 70 % / < 95 % / growing | raise the memory limit (USD 10/GB-month), tune `shared_buffers`/`work_mem` |
| T10 | Screener triggers | 6d.10 | 6d.10 |
| T11 | Weekly usage per service (the GraphQL `usage` query used here) | +30 % week on week | review against the per-user model (5.3) |

**Measure first (PROPOSED, a multi-user load test across tabs; FUTURE_PLAN.md:902-924 item e and 6d.11).** It needs
distinct owners: either the user directory (sibling file) or a private-network test harness that sends distinct
`X-Saniti-Owner` values to orc and distinct owner tags to the workers (the orc-test-runner and `feature-05-06-job`
precedents, `RAILWAY_CHANGELOG.md:4249`). Scenarios: 1, 10, 50 synthetic owners per tab; AI queue wait and cost per turn by
route; backtest FIFO vs round-robin wait for light owners while one owner queues 3 heavy jobs; terminal grants per second
with one shared and with per-user subscribers; edge-bff relay overhead at 50-200 concurrent requests; Postgres RAM, hit
ratio and connections during the run; Railway usage before and after. Results with deployment ids and log locations, as
the house requires.

---

## 7. Order of work for EDGE-MULTIUSER (PROPOSED; approval needed, nothing executed)

1. **Decide the inputs (user):** expected daily and concurrent users (P29 numbers), AI for external users and its budget,
   tiers, sign-up model, data permissions (6d E6), availability target, and whether external users stay on `dev`.
2. **Identity** (sibling file): user directory, owner from the session, sign-in limits in Postgres.
3. **AI concurrency and budgets:** split edge-bff web and loops; K Orc dispatch slots with round-robin; per-owner AI ledger
   and gate; key-limit alert.
4. **Terminal identity (P31):** per-user subscriber through the gateway, worker service accounts, counters, quota sizing,
   "files I have" on `/bundle`; then drop the TEMPORARY 1e9 override.
5. **Backtest throughput and fairness:** round-robin claim, K = 2 job threads, owner-tagged preview queue, per-service job
   affinity if a second worker is added.
6. **Screener as built in Phase 1** (P32-P34) with the budget in the shared ledger.
7. **Postgres headroom:** PgBouncer, role limits, memory and tuning, HA/PITR per the availability decision.
8. **Load test and cost calibration** (section 6), then set the trigger thresholds.

---

## 8. Corrections and additions to the Screener report 6d

- 6d.1 "Which plan the project is on is UNKNOWN (M-U1)": FACT now, `meta.plan = "pro"` on GitHub-built deployments
  (`railway status --json`); per-replica limit shown as 24 vCPU / 24 GB.
- 6d.1 "Recorded resource cost … USD 60/month at 6 GB": historical; Postgres averages 0.51 GB since the 4 GB limit
  (usage API 10-24..28).
- 6d.8 E5 "the claim already rotates across owners": with one slot the claim is FIFO by `created_at` over owners with
  nothing running (`backtest.py:516-527`), so there is no rotation (INFERENCE from the SQL).
- 6d does not mention that edge-bff dispatches one AI message at a time for all owners (`worker.py:32-43`), nor the sandbox's
  code cap of 4 sessions: both bound the Monitor tab before anything else.
- 6d.6 per-owner limits per replica: with P32 (two replicas) and P33 (per-user CPU budget) now decided, enforce the budget
  in edge-bff (section 3.5).

## 9. Open questions (UNKNOWN unless answered)

1. P29 numbers: daily active users, users at once, AI turns per user per day, Backtest jobs per user per day.
2. AI for external users: on or off, budget per user per day (USD), and what happens at the limit.
3. Tiers or plans per user (different quotas for Terminal, Backtest, Screener, AI).
4. A production environment separate from `dev` (BACKTEST_END_TO_END.md:656) before external users.
5. Availability target (HA, PITR for Postgres; two replicas for which services).
6. Region: users in Indonesia reach `sfo` (API) and `sin` (files); timings from the user's location are not measured
   (6c L-U4); moving Postgres (51 GB) is a separate decision.
7. Whether Railway's edge compresses responses (affects `index.html` egress) and how its private network spreads requests
   over replicas (6d M-U2).
8. Data permissions for external display (6d E6) — blocks everything external.
9. Why the usage API returns less for 10-01..27 than for 10-21..27, and which service `7af77ccf…` is (1.7 GB volume).

## 10. Evidence index (commands and queries, read-only)

- `npx -y @railway/cli@5.71.0 status --json` (plan, regions, replicas, start commands, healthchecks; saved without secret
  fields as `.status.json` in this folder).
- `railway metrics --all --since 7d --cpu --memory --network`; `railway metrics --service edge-bff --http --since 16h`.
- `railway api -f usage.graphql` (this folder) for 10-14..21, 10-21..24, 10-24..28, 10-21..28 (saved `.usage4d.json`,
  `.usage7d.json`).
- `railway variables --service <s> --json` keys only for terminal-api, edge-bff, backtest-worker, market-python-sandbox.
- `railway postgres pgbouncer status` (attached false), `railway postgres pitr status` (disabled, HA no).
- pgweb (via `tools/pgq2.py`): `pg_settings`, `pg_roles.rolconnlimit`, `pg_db_role_setting`, `pg_stat_activity`,
  `pg_stat_database`, `pg_stat_user_tables` (terminal, edge_bff), `pg_class` sizes, `AI_research_run_audit` aggregates.
