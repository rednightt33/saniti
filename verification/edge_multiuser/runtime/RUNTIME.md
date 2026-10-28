# EDGE runtime for many users: Terminal, Backtest and Screener (synthesis, read-only, 2026-10-28)

**User direction, 2026-10-28 (`PLAN.md` EDGE-MULTIUSER, "Arah user berikutnya"):** "Yang mesti dipastikan adalah screener
worker beserta backtest machine secara arsitektur harus bisa menghandle multi-user termasuk terminal. Untuk AI org, leave as
is saja. Untuk terminal backtest dan screener, efisiensi biaya dan efisiensi proses menjadi prioritas. Akurasi juga. ... Kita
tidak mau biaya terlalu mahal, tapi kita juga tidak mau user kalau memproses, melakukan screen dan lain-lain menjadi terlalu
lama." Users are external (P29, `EXEC.md:8503-8505`). Accounts are on hold (`PLAN.md`, "Dipending, 2026-10-28"), so every
per-user rule keys on `owner_key`: one owner today, many later. AI Orc (Monitor) is out of scope and is not changed.

**What this file is.** One runtime architecture for the three tabs, built from three area designs and the earlier audits:
- `mu_runtime/backtest.md` (proposals B1-B12, decisions D-R1..D-R7; models `bt_queue.py`, `bt_cost.py`);
- `mu_runtime/terminal.md` (proposals T1-T12, decisions D-T1..D-T6);
- the Screener report sections MULTI-USER SCALE AND COST (6d) and PAGE LOAD SEQUENCE (6c) (`verification/screener/AUDIT.md`
  lines 1728-2250; copies `report/06c_page_load_sequence.md`, `report/06d_multi_user_scale_cost.md`), with decisions P29-P34
  taken on 2026-10-28 (`EXEC.md:8503-8510`);
- `verification/edge_multiuser/capacity_fairness_scale_cost.md` (cited as CAP) and `verification/edge_multiuser/AUDIT.md`
  (cited as MU);
- `mu_runtime/silo_research.md` (one service copy per user against a pool; Railway Serverless).

Detail stays in those files; this one fixes the shared rules, the order, the numbers on one basis, and the decisions.
`BACKTEST_END_TO_END.md` and `apps/edge-bff/backtest/CONTRACT.md` were read in full by the Backtest and Terminal designs
(AGENTS.md rule); nothing below changes a CONTRACT rule without naming the decision that would.

**Read-only.** No repository edit, no state-changing git, no Railway mutation, no database write. Re-checked live for this
synthesis on 2026-10-28 about 20:00 UTC:
- `npx -y @railway/cli@5.71.0 status --json` (saved without secrets as `mu_runtime/rt_status.json`): edge-bff, terminal-api,
  backtest-worker and terminal-publisher each run 1 replica in `sfo` with no memory limit override; healthcheck `/ready` on
  edge-bff only (terminal-api and backtest-worker `null`); no service sleeps; `screener-worker` is not on Railway yet (27
  service instances, none named so).
- `git show origin/main:` (main `15ec418`): `apps/backtest-worker/src/server.ts:108` (two threads, `jobs` and `previews`) and
  `:113` (one `job`); `apps/edge-bff/app/backtest.py:516-527` (oldest QUEUED job of any owner with nothing running);
  `apps/terminal-api/app/store.py:44-46` (one advisory lock per subscriber); `apps/edge-bff/terminal/src/data/worker.ts:36-42`
  (the Terminal stores only verified bytes but draws whatever it downloaded).
- The Screener as it is being built on branch `claude/charming-hamilton-faq25e` (HEAD `7807d2b`, plus the running build's
  uncommitted files `apps/screener-worker/src/{pool,refresh,server,thread,catalog,preview}.ts`, read as they stood). Cited as
  "Screener build"; line numbers can move while that build runs.

**Labels.** FACT (file:line, measurement or command), INFERENCE (derived), PROPOSED (design, waiting for "go"), UNKNOWN (with
the check that settles it), TEMPORARY (a stopgap to be replaced). **Prices** (06d.1, Railway docs read 2026-10-28): RAM USD 10
per GB-month, CPU USD 20 per vCPU-month, egress USD 0.05 per GB, volume USD 0.15 per GB-month, bucket storage USD 0.015 per
GB-month; bucket egress and private-network traffic free.

---

## 0. Summary

1. **One pool per service, users separated by `owner_key`, not a copy per user.** INFERENCE (`silo_research.md` §4): all
   three tabs serve the same public data from one publication; a copy per user repeats the same download, decode and
   precompute, waits 15-25 s on every return, and loses to a pool by 10-70× once users overlap in market hours.
2. **The Screener is already being built this way** (FACT, Screener build): owner lanes with cost-weighted round robin,
   a per-owner CPU budget per minute (P33), a shared result cache, one copy of the bars per replica in SharedArrayBuffer,
   gzip answers relayed as bytes, `/ready`, version pinning with a grace window. It is the reference shape for the others.
3. **Backtest is the tab that does not scale today** (FACT): one job and one preview at a time for all of EDGE, first come
   first served across owners. Most of a warm run is fixed polling (5.5-5.9 s end to end for 0.45-0.58 s of compute).
   B1 (event-driven hand-off) + B2 (decoded cache) cut a warm single run to about 1.5 s; B3 + B4 add K slots in one
   replica with a fair claim (INFERENCE: about 10,000 jobs an hour at K = 4).
4. **Terminal is cheap and fast enough per user; what does not scale is identity.** FACT: everyone is one terminal
   subscriber under one lock with quotas set to 1e9 (TEMPORARY). T2 gives each owner a subscriber, T4 makes each open one
   grant that counts only missing files.
5. **New, found by combining the designs (section 5):** the Backtest worker and the people share that one terminal-api
   account. Each grant re-aggregates the account's last 24 h of rows, so the hold time grows with all users' traffic. Once
   the Backtest is scaled (B3) but the worker still books its grants on the people's account, the shared lock reaches
   about 64 % busy at 50 users at once and saturates near 60 (INFERENCE, `rt_lock.py`). **T1 (worker service accounts
   with counters) or B7 (grant-free planning) must land before Backtest K ≥ 4**, and T4 or T2 before about 150 users at
   once.
6. **Shared principles (section 3):** `owner_key` everywhere; nothing user-specific in shared caches; content-addressed
   data, one publication per view; deterministic compute shared across users and re-verified by tests; fairness where
   contention happens, budgets where every request passes once; threads before replicas; events, not polls, on the
   user's path; scale-out on measured triggers.
7. **Cost (INFERENCE, section 6), all three tabs plus their share of edge-bff, per month:** about USD 22 / 28 / 56 for
   10 / 50 / 200 users at once (about 33 / 167 / 667 daily users). About USD 19-21 is fixed up to 50 users at once; one
   more daily user costs USD 0.04-0.09 a month. The largest single item is the Screener's two replicas held in memory
   (USD 12-24, P32). Today's Backtest design would cost about USD 13 / 21 / 49 for the same load and cannot serve the 50
   and 200 cases.
8. **Latency targets (section 7):** cached ticker switch ≤ 0.9 s (today about 1.8-2.5 s), warm single backtest ≤ 2 s
   (today 5.5-5.9 s), 12-stock flow portfolio ≤ 3 s (today 10.8 s), Screener run after an edit p95 ≤ 2 s, preview p95
   ≤ 1 s, all held at 10, 50 and 200 users at once by the triggers of section 10.
9. **Accuracy (section 8):** one gap is live today: the Terminal page draws bytes whose sha256 does not match (T7). The
   Screener reads the reference file under a fixed key (T5). HEAD's publisher would bring back M250 if deployed before
   the content-key commits are present (risk R1).
10. **Order (section 9):** Phase 0 measure; Phase 1 with the Screener (T1, T3, T5, T7, healthchecks, R1 check); Phase 2
    Backtest (B1+B2, then B3+B4+B10 with owner lanes for previews, then B5/B9/B11, B8, B7, B6); Phase 3 Terminal (T4,
    T11, T6, T8, T9); Phase 4 the gate before the first external user. Decisions RT1-RT15 in section 12.

---

## 1. One basis for the numbers

The area designs counted users differently (FACT): `backtest.md` and 6d count users **at once** in busy hours; `terminal.md`
counts **daily** users with 30 % of them active at the peak (its section 7). This file uses:

| Symbol | Meaning | Value |
|---|---|---|
| U | Users active at the same moment, in the busy hours | 10 / 50 / 200 |
| N | Daily users, N = U / 0.3 (the 30 % at-peak ratio of `terminal.md` §7 and 06d.9) | about 33 / 167 / 667 |
| Terminal profile | per daily user and trading day: 50 ticker opens (30 distinct), 5 IHSG or compare loads, 2 asset adds | `terminal.md` §7 |
| Backtest profile | per user at once: one job every 120 s in 4 busy hours, 22 days; half the users edit portfolios half the time, one server preview per 15 s | `backtest.md` §6 |
| Screener profile | per daily user: 200 debounced runs a day, half served from a cache; uncached run 0.5 vCPU-s; about 37 editing users per replica at K = 2, 75 at K = 4 | 06d.9 |

So `terminal.md`'s "200 daily users" is U = 60 here, and its numbers are re-scaled below. All profiles are INFERENCE until
the user's numbers (P29, MU5) and the load test (Phase 0) replace them.

---

## 2. Today (FACT)

| Part | Runtime today | Per-owner rules today | Evidence |
|---|---|---|---|
| edge-bff | 1 replica `sfo`, `--workers 1`, healthcheck `/ready`; the one public entry; runs the Backtest loop in-process | owner = `settings.owner` on every route; Backtest preview latest-wins per owner (not per page) | `rt_status.json`; `backtest.py:1050`, `:936, 1016-1026`; 6d.1 |
| terminal-api | 1 replica `sfo`, 2 uvicorn processes, no healthcheck; pool 8 per process (16 of the role's 20) | none: one gateway subscriber for pages and both workers, one advisory lock, quotas 1e9 (TEMPORARY) | `rt_status.json`; `store.py:24-25, 44-46`; `main.py:174-180`; `terminal.md` §2.1 |
| terminal-publisher + bucket | twice a day (07:30, 19:00 WIB); bucket `terminal-display` in `sin`; content keys live (log `gc`, 17,498 objects) | — | `terminal.md` §2.1 |
| Terminal page | computes in the browser; IndexedDB 50 MB by sha256; 4 grants per open; reference lists unversioned | quota counts page loads, not access | `terminal.md` §2.2 |
| backtest-worker | 1 replica `sfo`, no healthcheck, no memory limit; threads `jobs` and `previews`, one job held | edge-bff: 1 RUNNING and 3 QUEUED per owner; FIFO across owners | `server.ts:108, 113, 270`; `backtest.py:516-527`; migration `20261026_005:54` |
| screener-worker | not deployed; being built (dev only, P3) | owner lanes, `SCREENER_OWNER_INFLIGHT`, `SCREENER_OWNER_CPU_MS` per minute per replica (P33), queue, deadline | `rt_status.json`; Screener build `pool.ts:1-25`, `config.ts:32-36` |
| Postgres | `sfo`, 4 GB limit; role limits `edge_bff_login` 20, `terminal_api_login` 20; no HA, no PITR | `backtest_jobs`, `sessions` keyed by `owner_key` | CAP findings 8-9 |
| Railway | Pro plan; no service sleeps; one environment (`dev`) | — | CAP finding 5, 10; `rt_status.json` |

Measured user-facing times (FACT, from the US sandbox; Indonesia never measured, `ERRORS_AND_SOLUTIONS.md:2307`): Terminal
chart 2.28 s first open, 1.77 s second open; Terminal second visit ANTM 2.5 s, of which 2.2 s waiting for the ticker list
and `/bundle`; Backtest page ready 1.37 s / 1.12 s; Backtest warm single run 5.5-5.9 s, warm 12-stock flow portfolio
10.8 s (`apps/backtest-worker/README.md:430-432`); 20 concurrent `/bundle` median 0.53 s (`ERRORS_AND_SOLUTIONS.md:2302-2304`).

---

## 3. Shared principles (PROPOSED as the rule for all three tabs)

Each principle names where it already holds, the gap, and the test that keeps it.

| # | Principle | Holds today (FACT) | Gap → proposal | Enforced by |
|---|---|---|---|---|
| RP1 | **`owner_key` is the only user identity in the runtime.** edge-bff takes it from the session row; workers get an opaque tag (first 16 hex of HMAC(worker key, `owner_key`)); terminal-api gets the owner from edge-bff only, never from a browser | Stores keyed by `owner_key` (6d.1); Screener tag (`app/screener.py:157-161`; worker `server.ts:389-391`, Screener build) | owner still `settings.owner` (accounts on hold); terminal-api has no owner (T2); Backtest worker gets no tag (X2) | T2 `test_gateway_forwards_the_session_owner_and_never_a_client_owner_header`; Screener tag tests |
| RP2 | **Nothing user-specific in a shared cache or a shared answer.** Shared caches are keyed only by publication, versions and the canonical request; per-owner parts are computed outside them | Screener answers carry no owner, name or watch flag (6d.2); Backtest's one per-owner piece is isolated (`backtest.md` §3) | Backtest reuse (B6) with `ownerPart`; the Terminal's `localStorage` pointer per login (T6) | Screener "two owners, same bytes except `timings_ms`"; W5 `ownerPart` parity; E2 `reused_from` never exposed; T6 `boot.test.ts` |
| RP3 | **Data is content-addressed per publication, and one view or result uses one publication.** No reader opens a fixed key; every file is checked by sha256 and size on every use | Content keys live (M250); Backtest `inflateVerified` on every use; Screener refresh all-or-nothing with skew retries (Screener build `refresh.ts:13-31`) | reference lists under fixed keys (T5, read by the Screener too); Terminal draws unverified bytes (T7); a chart can mix publications (T8); HEAD publisher (R1) | section 8, A1-A3 |
| RP4 | **Deterministic compute is computed once and shared.** Anything that is a pure function of (publication, versions, canonical request) is cached or pre-warmed for every user; reuse only on equality of the whole version tuple | Screener result cache, preset pre-warm, defaults once per publication (6d.2); Terminal compute in the browser (free) | Backtest decoded cache (B2), pre-warm (B8), exact reuse (B6); terminal-api manifest warm-up (T9) | W1, W2, E2; S22 `snapshot_digest` equal across replicas |
| RP5 | **Fairness is enforced where contention happens, by measured cost, with bounded waits.** One in flight per (owner, page), latest wins | Screener lanes with deficit round robin by predicted cost and a deadline (Screener build `pool.ts:14-25`) | Backtest claim is FIFO (B4: least compute in the last hour, aging 60 s); Backtest preview queue is FIFO and becomes unfair once latest-wins is per page (X2); terminal-api lock is global (T2) | E1; Screener S23; T2 `test_owner_grants_do_not_wait_on_another_owners_lock` |
| RP6 | **Budgets are enforced where every request passes once, and every refusal has the four gate parts** (AGENTS.md "Gates and evidence") | Screener per-request budget and per-owner CPU per minute (P33), per replica | per-replica bound is up to R × the value with R replicas (CAP 3.5); daily budgets for Backtest (B5) and Terminal (T10) not built; one ledger (X3) | E3; T10 `test_quota_refusal_names_the_limit_and_the_reset_time`; P33 refusal test |
| RP7 | **Threads before replicas, replicas before services.** RAM is billed resident, CPU by use; a replica repeats every cache | Screener one copy of the bars shared by K threads (Screener build `snapshot.ts:17-28`) | Backtest K threads with memory admission and idle trim (B3) | W1, W3; memory test per K |
| RP8 | **Events, not fixed polls, on the user's path; draw what the browser holds, then confirm** | Screener `ETag`/`304`, cached paint after the first authenticated answer (6c.4); Backtest page `PROVISIONAL` render | Backtest 2-s polls (B1); Terminal waits for list and bundle (T6) | latency table (section 7), page timing scripts |
| RP9 | **One publication event drives every warm-up.** A new `state.json` `finished_at` (after the run) starts: Screener refresh, Backtest catalog and pre-warm, terminal-api manifest warm-up, page version checks | Screener refresh (`refresh.ts` rule 1), Backtest catalog `ByPublication` | B8, T9 warm-up, T8 | refresh logs; B8 `prewarm` log |
| RP10 | **Deploys never lose a user's work and never mix versions.** Healthcheck on every service, drain on SIGTERM, version pinning across replicas | Screener `/ready` and grace window; edge-bff `/ready` | backtest-worker and terminal-api have no healthcheck (`rt_status.json`); worker kills jobs on SIGTERM (B10) | W3 drain test; deploy under load shows no 503 |
| RP11 | **Services have their own identity, separate from people** | — | both workers present the gateway key and book grants on the people's account (T1) | T1 tests |
| RP12 | **Scale on measured triggers, from logs the services already write** | Screener log fields (6.16) | one trigger table (section 10) | Phase 0 load test |

**New cross-cutting proposals** (not in the area files; each with the standard fields):

- **X1 — Order constraint between the Backtest and the terminal-api account.**
  - Need: section 5 (INFERENCE): scaling Backtest without T1 or B7 saturates the shared terminal-api lock near U = 60
    and slows every Terminal user too.
  - Class: a shared gate whose cost grows with the traffic of all its callers.
  - Fix and layer: plan rule, no code. B3 at K ≥ 4 ships only after T1 (terminal-api); B7 before U ≈ 50; T4 or T2 before
    U ≈ 150.
  - Covers: the cross-area bottleneck. Does not cover: the per-person quota values (T10).
  - Risks and cost: none; it orders work. Verification: the Phase 0 load test reads grant hold time (p95) with the
    worker on the shared account and on its own account. Permanent (as a dependency).
- **X2 — Owner lanes for Backtest previews.**
  - Need: FACT, previews wait in one FIFO on the worker (`server.ts:197-235`); `backtest.md` B3 relies on edge-bff's "one
    preview in flight per owner". B9 moves latest-wins to (owner, page), as the Screener has it, so one owner with several
    pages can hold several places in the FIFO (INFERENCE).
  - Class: per-owner fairness inside one worker queue.
  - Fix and layer: edge-bff `backtest.py` sends `x-backtest-owner` = the same HMAC tag as the Screener's `owner_tag`
    (`app/screener.py:157-161`, one shared helper); worker `server.ts` takes the next preview by round robin over owner
    tags, reusing the Screener build's lane scheduler (`apps/screener-worker/src/pool.ts`) rather than writing a second one.
  - Covers: preview fairness at P threads. Does not cover: jobs (B4 does).
  - Risks and cost: a worker code change (new `engine_version`, numbers unchanged); importing Screener code into the
    Backtest worker couples their releases, so the scheduler moves to a small shared module both import. No cost.
  - Verification: `server.test.ts`: owner A with 4 pages and owner B with 1 → B's preview starts second;
    `test_backtest.py`: the tag is sent and never the raw `owner_key`. Permanent.
- **X3 — Fairness local, budgets global: one usage ledger.**
  - Need: P33's budget is per replica, so with P32's two replicas an owner may use up to 2× the value (CAP 3.5); B5 and
    T10 add daily budgets in two more places.
  - Class: metering and admission across replicas and tabs.
  - Fix and layer: keep the worker lanes and per-minute caps as they are (fairness, instant); add MU MP-12's
    `edge_bff.usage_ledger(owner_key, feature, window_kind, window_start, units, ...)` written by edge-bff from what it
    already relays (`duration_ms`, `timings_ms`), with an in-process batch of at most 5 s per owner and feature so writes
    stay off the request path; daily limits (B5, a Screener daily CPU limit if wanted) read it. B5's own reading of
    `backtest_jobs` stays valid until the ledger exists.
  - Covers: one daily budget per owner across replicas and tabs. Does not cover: in-run cost (bounded by per-request caps).
  - Risks and cost: one UPSERT per owner and feature every few seconds; overshoot of at most one batch. Migration
    `database/migrations/<date>_edge_bff_usage.sql`.
  - Verification: ledger read-back against the worker logs over a load test; the four-part refusal. Permanent; values are
    the user's (RT5).
- **X4 — One shared multi-owner load harness.**
  - Need: Phase 0 needs S21/S23 (Screener), L1 (Backtest) and T12.3 (Terminal); three harnesses would repeat the same
    synthetic-owner plumbing.
  - Class: measurement infrastructure shared by the three areas.
  - Fix and layer: one temporary private-network job service (precedent `feature-05-06-job`, `RAILWAY_CHANGELOG.md:4249`)
    driving edge-bff's stores and the workers with synthetic `owner_key` values and tags, results in
    `verification/edge_multiuser/LOAD.md` with deployment ids.
  - Covers: per-owner p50/p95, `BUSY` share, queue waits, RSS and CPU per worker, terminal-api grant hold (section 5) at
    10 / 50 / 200 synthetic owners, steady and in bursts. Does not cover: real user behaviour (P29 numbers), times from
    Indonesia (T12.1).
  - Risks and cost: it creates a Railway service (needs approval) and loads the shared `dev` environment, so it runs
    outside the publisher windows and golden tests; its synthetic rows are removed afterwards and the removal read back.
    Cents of usage for a day.
  - Verification: the results file with deployment ids and log locations; the service deleted and `railway status` read
    back. TEMPORARY.
- **X5 — Shared module rule for `apps/backtest-worker/src/terminal.ts`.**
  - Need: FACT, the Screener imports `TerminalClient`, `inflateVerified` and `fileOriginOf` from the Backtest worker
    (Screener build `refresh.ts:38-39`, `config.ts:44-47`), and any change to a Backtest worker `src/*.ts` changes
    `engine_version` (`apps/backtest-worker/src/version.ts:4-9`). B2 and B7 change `terminal.ts`.
  - Class: one module shared by two services with separate version hashes.
  - Fix and layer: documentation and tests: a change to `terminal.ts` runs both workers' test suites; the Screener never
    edits it (its `refresh.ts` header already says so). Record the rule in `BACKTEST_END_TO_END.md` and the Screener
    onboarding document.
  - Covers: a Backtest change silently altering the Screener's downloads or checks. Does not cover: the Screener's own
    copies of terminal-api calls (`refresh.ts` `TerminalApi`), which it owns.
  - Risks and cost: longer test runs for Backtest changes; nothing at runtime.
  - Verification: the Phase 2a checklist lists both suites; a review note on each `terminal.ts` change. Permanent.

---

## 4. Per-service design

### 4.1 The owner chain (PROPOSED; accounts change only its first link)

```
browser ──cookie──▶ edge-bff: session row ─▶ owner_key
                      │
                      ├─▶ backtest_jobs.owner_key  (claim: B4 fair by compute; 1 RUNNING per owner; daily limits B5/X3)
                      ├─▶ backtest-worker: x-backtest-owner = HMAC tag (preview lanes, X2)
                      ├─▶ screener-worker: x-screener-owner = HMAC tag (lanes, P33)            [built]
                      ├─▶ terminal-api: gateway key + x-terminal-proxy-owner = owner_key (T2) → its own subscriber, lock, quota, audit
                      └─▶ edge_bff.usage_ledger(owner_key, ...) (X3)
workers ──own service key (T1)──▶ terminal-api: service account, hourly counter, own lock
```

### 4.2 edge-bff (the shared entry and the Backtest loop)

- Relays worker answers as gzip bytes, never parsing a 2xx (FACT for the Screener, `app/screener.py:239-278`); the Backtest
  result ingest stops parsing and splitting in Python (B11: the worker splits).
- Latest wins per (owner, page) for every server preview and screen: one helper (FACT built for the Screener,
  `app/screener.py:774-790`; the Backtest moves to it with B9 and X2).
- Backtest loop: wakes on submit (B1), runs up to `BACKTEST_SLOTS` followers with a slot column so any number of edge-bff
  processes stay safe (B4).
- Capacity (INFERENCE): at U = 200 about 75 requests a second in busy hours (Screener about 60, Terminal about 10,
  Backtest previews and status about 5), each with one session `SELECT` on a pool of 6 (UNKNOWN until S25 measures the
  relay). If the event-loop lag trigger fires, a second process is the step, but not as plain `--workers 2`: FACT, one
  switch `EDGE_WORKER_ENABLED` starts both the Orc job loop and the Backtest loop in every process (`app/main.py:191, 194`;
  `app/config.py:23, 65`), so a second process would also double AI Orc's dispatch, which the user said to leave as is.
  PROPOSED: MU MP-14 first (one private `edge-bff-worker` service from the same image with the loops, about USD 1 a month;
  the public service with `EDGE_WORKER_ENABLED=false`), then web processes or replicas. The role limit allows at most 3
  processes of 6 connections in all (`store.py:22-27`; 6d.5), and the sign-in limiter must move to Postgres before a
  second web process (6d.5 table; accounts work, on hold). B4 makes the Backtest claim safe with any number of loops.

### 4.3 terminal-api, terminal-publisher and the bucket (the shared data gate)

- Identity: T1 (service accounts for both workers, hourly counters with a ceiling, own lock) and T2 (one subscriber per
  `owner_key` through the gateway; D-T2 removes or fences the public domain first).
- Fewer transactions: T3 (subscriber read inside the grant; read-only routes cache it 60 s): about 90 % of terminal-api's
  transactions today are that lookup (FACT, `terminal.md` §2.3).
- Fewer grants: T4 (one `/bundle` per open with `have` and `refs`), B7 (`/plan` without grants for the worker).
- Content addressing: T5 (reference lists under content keys, listed in `state.json`); R1 check before any publisher deploy.
- Availability: T9 (`/ready` healthcheck, `TERMINAL_POOL_MAX`, a second replica at launch, manifest warm-up on
  `finished_at`, logo bodies cached per publication).
- Not proposed (`terminal.md` §4): long-lived presigned URLs, a CDN, streaming files through a service, moving regions
  before an Indonesian reading.

### 4.4 Terminal page (computes in the browser)

- T6 cache-first boot after the first authenticated answer; T7 sha256 and size checked before drawing; T8 one publication
  per page; T11 one bundle per added asset. The frame reload on switch stays (`terminal.md` T6).
- The page is the cheapest per-user compute there is: its CPU is the user's, its downloads come from the bucket for free.

### 4.5 backtest-worker and the Backtest loop

- In order: B1 event-driven hand-off; B2 decoded-series cache (bytes still verified on every use, CONTRACT §2 unchanged);
  B3 K job threads and P preview threads with memory admission and idle trim; B4 fair, slot-aware claim; B10 healthcheck,
  drain, memory limit; X2 owner lanes for previews; B5 daily limits (off by default); B9 debounce and per-page latest-wins;
  B11 worker-side result split and retention; B8 pre-warm per publication; B7 grant-free planning; B6 exact reuse with
  `ownerPart` once logs show duplicates; B12 a second worker service with explicit origins only on trigger.
- Kept: 1 RUNNING job per owner. It is also the trial-count guard (`backtest.md` I4): two running jobs of one owner on one
  lineage would each miss the other's variants and flatter the Deflated Sharpe.
- Sizing (INFERENCE, `backtest.md` §5): K = 2 / 4 / 8 and P = 1 / 2 / 4 for U = 10 / 50 / 200, one replica.

### 4.6 screener-worker

- As built (FACT, Screener build): admission order cache hit → per-request budget → per-owner CPU per minute → queue;
  lanes by owner tag with deficit round robin by predicted cost; deadline with cancel and thread restart (`pool.ts:1-25`);
  bars once in SharedArrayBuffer (`snapshot.ts:17-28`); refresh every 60 s only on a new `finished_at`, skip when the files
  are unchanged, all-or-nothing swap (`refresh.ts:13-31`); `/ready`, pinning with `DATA_VERSION_PENDING` and the grace
  window (`server.ts:1-25`).
- Still to do for many users: the Railway block in `.railway/railway.ts` (healthcheck `/ready`, memory limit = measured
  peak × 1.5, 6d.4), its own terminal key from its first deploy (T1), T5 for the reference file it reads under a fixed key
  (`snapshot.ts:13-14`, "fixed key, ERRORS M250 class"), the second replica at the first external user (P32, decided),
  and the ledger for daily budgets if wanted (X3).
- Sizing (INFERENCE, `rt_cost.py` `screener_queue`, 06d.9 profile): 06d.9 sizes replicas for 70 % thread use (about 37
  editing users per replica at K = 2). Held to the 300 ms queue p95 of 06d.10 instead, the same queueing model as the
  Backtest gives 2 × K = 2 at U = 10 (p95 0 s), 2 × K = 3 at U = 50 (0.11 s; 2 × K = 2 would give about 0.84 s) and
  2 × K = 8 at U = 200 (0 s; 3 × K = 4 would give about 0.62 s at the same RAM). Threads before replicas again: two
  replicas (P32's floor) with more threads cost the same RAM as three with fewer, meet the target, and keep P33's
  per-replica bound at 2× rather than 3× (X3). RSS per replica is taken as 0.4 + 0.1 × K GB, interpolated from 06d.4's
  0.6 GB at K = 2 and 0.8 GB at K = 4 (INFERENCE; S19 measures it).

### 4.7 Postgres

- No market data at request time in any of the three tabs (FACT: Backtest CONTRACT I5; Screener 6d.9; Terminal through
  the bucket).
- What grows with users: `backtest_results` (B11: newest 50 per owner and at most 30 days), `terminal.access_log` (T4 cuts
  rows by about 3.7×; B7 removes the worker's rows for warm runs), the ledger (X3, counters, not a log).
- Role limits bound replicas: `terminal_api_login` 20 → `TERMINAL_POOL_MAX` 4 with two replicas (T9); `edge_bff_login`
  20 → at most 3 edge-bff processes.

---

## 5. The shared grant gate under combined load (INFERENCE; model `mu_runtime/rt_lock.py`)

Each grant takes the account's advisory lock and aggregates the account's last 24 h of `access_log` rows (FACT,
`apps/terminal-api/app/store.py:44-67`; index `(subscriber_id, at DESC)`, migration `20261025_100:59`). `terminal.md` §8
derives a hold time of about 2 ms + 0.26 ms per 1,000 rows from the FACT 0.85 ms at 3,271 rows. `terminal.md` assumed
60,000 worker rows a day at its largest case; `backtest.md`'s profile gives far more once the Backtest is scaled (its own
§6: 1.7 / 8.4 / 33.5 worker grants per second in busy hours at U = 10 / 50 / 200). Putting both on one account:

| U at once | Rows of the shared account per day | Hold per grant | Grants per second (people + worker) | Lock busy |
|---|---|---|---|---|
| 10 | 31,000 | 10 ms | 3.0 | 3 % |
| 30 | 93,000 | 26 ms | 9.0 | 24 % |
| 50 | 155,000 | 42 ms | 15.0 | 64 % |
| 60 | 187,000 | 51 ms | 18.1 | 91 % |
| 200 | 622,000 | 164 ms | 60.2 | saturated (985 %) |

Reading:
- Today's Backtest (one slot) saturates first, at 16-33 users at once (`backtest.md` §1.4), which caps the worker's
  grants. The gate becomes the limit only after B3, which is why X1 orders T1 (or B7) before K ≥ 4.
- With T1 the worker's grants leave the people's account (own lock, hourly counter). The people's shared account alone
  reaches 70 % at about U = 165, so T4 (one grant per open) or T2 (one lock per person) is needed before about 150 users
  at once. With T2 each person's aggregate is bounded by that person's quota (a few hundred rows), so it stays about
  2 ms.
- UNKNOWN (U-RT1): whether the aggregate's cost grows linearly with rows. Settled by the Phase 0 load test (grant hold
  p95 at 10 / 50 / 200 synthetic owners, on one account and on per-owner accounts).

---

## 6. Combined cost per month (INFERENCE; model `mu_runtime/rt_cost.py`)

Inputs: the area models (`bt_cost.py`; `terminal.md` §7; 06d.9) re-based to U and N of section 1. Proposed design means:
Backtest B1-B3, B7, B11 (K = 2 / 4 / 8); Terminal T1-T10 with two terminal-api replicas (D-T3); Screener as built with
P32 (2 replicas from the first external user) at K = 2 / 3 / 8 (section 4.6); at U = 200 one more edge-bff service or
process (MP-14 split, section 4.2), about USD 1.

| Component (USD per month) | U = 10 (N ≈ 33) | U = 50 (N ≈ 167) | U = 200 (N ≈ 667) | Fixed part (any U) |
|---|---|---|---|---|
| Terminal: terminal-api, publisher, bucket, egress, grant rows | 3.3 | 3.7 | 5.3 | 3.2 (2 terminal-api replicas 2.4, publisher 0.75) |
| Backtest: worker RAM (idle floor + busy hours), CPU, results, egress | 4.9 | 7.5 | 15.8 | 2.6 (0.3 GB outside busy hours) |
| Screener: replicas, CPU, egress | 12.5 | 16.2 | 32.8 | 12.0 (2 × 0.6 GB); 14.0 at K = 3; 24.0 at K = 8 |
| edge-bff (shared entry, all tabs) | 1.0 | 1.0 | 2.0 | 1.0 |
| **Total** | **≈ 21.7** | **≈ 28.4** | **≈ 55.9** | **≈ 18.8** (20.8 at U = 50, 31.8 at U = 200) |
| Per daily user | 0.65 | 0.17 | 0.08 | — |
| Variable part per daily user | 0.09 | 0.05 | 0.04 | — |

Today's design for the same load (INFERENCE): Terminal about 2.1 / 2.7 / 4.8 (one terminal-api replica, but the shared
lock fails near U = 60, section 5); Backtest about 12.9 / 20.6 / 49.4, including about USD 2.5 of terminal-api CPU and
90-day audit rows for the worker's grants at U = 200, and it cannot serve U = 50 or 200 at all (one slot).

Reading:
- **Fixed cost dominates up to about U = 50** (87 % at U = 10, 73 % at U = 50). The levers are resident RAM: the
  Screener's snapshot per replica (one copy of the bars per replica, already built; threads before replicas), the
  Backtest's per-thread caches
  (B2/B3: small byte caches, decoded cache budget, idle trim), and memory limits so page cache is not billed (B10, 6d.4;
  FACT, Railway billed Postgres page cache as memory, `RAILWAY_CHANGELOG.md:4221-4225`).
- **CPU is cheap**: USD 0.0000077 per vCPU-second. A warm backtest costs about USD 0.000005, an uncached screen about
  USD 0.000004. Waiting time is bought with threads, not replicas.
- **Storage is the slow leak**: Backtest results (72 GB at 30 days at U = 200 without B11) and worker audit rows (about
  11 GB at 90 days at U = 200 without B7). B11 and B7 remove most of both.
- **Not counted**: Postgres base cost (USD 13.86 today, mostly the 51 GB market-data volume, CAP 2.2), Railway's Pro fee,
  AI Orc (out of scope; CAP 5.3 puts AI at about 98 % of a user's cost if it is opened to external users), a second
  Backtest worker (USD 3-5, only on D-R7 or trigger), the Phase 0 load-test service (temporary).
- **Sleeping pools** (`silo_research.md` §5): Railway Serverless could save about USD 8 a month on the Screener outside
  market hours, but the first user after a sleep waits a platform wake plus the Screener start (15-25 s), and the
  Screener's 60-s `/state` poll keeps it awake anyway. RT14 recommends always-on.

---

## 7. Latency targets per action (PROPOSED as acceptance criteria; measured from the US sandbox until the Indonesian reading)

| Action | Today (FACT unless marked) | Target | What gets there | Basis |
|---|---|---|---|---|
| Terminal tab open, files cached | 1.77 s | ≤ 1.5 s | T4, T5, T6 | shell and frame 1.12 s (Backtest warm, FACT) + session + IndexedDB |
| Terminal tab open, empty browser | 2.28 s | ≤ 2.3 s | T4 (one call less) | bucket TTFB 0.72-1.42 s per object from the US (M240) |
| Switch to a ticker already cached | about 1.8-2.5 s (2.5 s on 2026-10-26) | ≤ 0.9 s | T6, T4, T5 | 2.2 of 2.5 s was waiting for list and bundle |
| Switch to a ticker not cached | about 2.0-2.5 s (INFERENCE) | ≤ 2.2 s (US); Indonesia UNKNOWN | T4 | one bundle + one bucket round trip |
| Backtest page ready | 1.37 s cold / 1.12 s warm | keep | — | EXEC-BACKTEST-LOAD |
| Backtest single run, warm, submit to result | 5.5-5.9 s | ≤ 2 s | B1, B2 | compute 0.45-0.58 s |
| Backtest 12-stock flow portfolio, warm | 10.8 s | ≤ 3 s | B1, B2 | compute 5.5 s, mostly decode (INFERENCE) |
| Backtest run, cold after a publication | + up to 6 s (28 MB) | popular tickers at warm speed | B8 | 28.35 MB in 6.1 s from `sfo` |
| Backtest server preview (portfolio with flow) | about 3 s compute + FIFO wait (INFERENCE) | p95 ≤ 1 s | B2, B3 (P threads), B9, X2 | `backtest.md` §5 |
| Screener page, first results (empty screen) | not built | ≤ 1.8 s cold, ≤ 1.4 s warm | 6c.4 sequence | Backtest first render (FACT) + one round trip |
| Screener run after an edit | worker 0.35-0.56 s wall per uncached screen (FACT, `audit/benchmark.md` §2a-c) | p95 ≤ 2 s through edge-bff; default-only ≤ 0.5 s; cache hit ≈ one round trip | result cache, lanes | 06d.10, 11b.5 |
| Screener preview (row click) | not built | p95 ≤ 1 s | — | 11b.5 S16 |
| New publication visible on any page | Backtest catalog ≤ 60 s | ≤ 2 min after `finished_at` + one request | RP9, 6c.5 item 4, T8 | 11b.5 S14 |

**Under load** (INFERENCE, the area models; held by the triggers of section 10):

| Signal | U = 10 | U = 50 | U = 200 | Target |
|---|---|---|---|---|
| Backtest job queue wait p95 (B1+B2) | 0 s (K = 2) | 0 s (K = 4) | 0.3-3.9 s (K = 4), 0 s (K = 8) | ≤ 5 s |
| Backtest preview wait p95 | 0.4 s (P = 1) | 0.3 s (P = 2) | 0.7 s (P = 4) | ≤ 1 s |
| Screener worker queue p95 | 0 s (2 × K = 2) | 0.11 s (2 × K = 3) | 0 s (2 × K = 8) | ≤ 300 ms |
| Terminal grant hold p95 | about 10 ms | 2 ms per person (T2) | 2 ms per person (T2) | ≤ 50 ms |
| Terminal burst: 60 users open at once, last grant | 6-8 s today | 0.2-0.3 s with T2 + T4 | — | ≤ 1 s |

---

## 8. Accuracy guarantees and the tests that enforce them

| # | Guarantee | Terminal | Backtest | Screener | Tests |
|---|---|---|---|---|---|
| A1 | Every byte used matches its manifest sha256 and size, on every use | **Gap (FACT):** draws mismatched bytes (`worker.ts:36-42` at `15ec418`) → T7 | FACT `inflateVerified` on every use; kept under B2 (D-R5 a) | FACT verified on the builder thread (`refresh.ts` rules 4-5) | T7 `download.test.ts`; W2; Screener refresh tests |
| A2 | A published key never changes its bytes (content keys) | M250 live; refs fixed → T5 | same | reads `ref/tickers.json.gz` under a fixed key (`snapshot.ts:13-14`) → T5 | publisher tests; pre-deploy check `git merge-base --is-ancestor 6051f4d HEAD` (R1) |
| A3 | One view or result uses one publication | **Gap:** up to 60 s skew and long-open pages → T8 | `data_version` = the files actually read (I2) | pinning, grace window, `DATA_VERSION_PENDING` | T8 tests; S22 |
| A4 | The same inputs give the same bytes wherever and whenever computed (threads, caches, replicas, reuse) | in the browser | I1; W1 (K threads = sequential), W2 (cold = warm = decoded hit, A-B-A) | fresh answers of two owners equal apart from `timings_ms`; equal `snapshot_digest` across replicas | W1, W2, W5, E2; Screener parity tests; S22 |
| A5 | Nothing of one owner reaches another | browser cache per device; pointer per login (T6) | `reused_from` never shown; per-owner part recomputed | answers carry no owner fields; opaque tag | E2; T6 `boot.test.ts`; Screener owner tests |
| A6 | Per-owner statistics stay honest (K3 trials) | — | 1 RUNNING per owner; `ownerPart` parity | — | W5, E1 |
| A7 | Limits are checked before compute and never depend on cache state | quotas per grant; T4 counts only granted files | I6 (`load.ts:350-352`) | per-request budget before compute (`pool.ts` admission 2) | W4; T10 tests; Screener budget tests |
| A8 | Scheduling changes order, never results | — | W1 | lanes | W1; Screener lane tests |
| A9 | Every refusal names the problem and the fix (four gate parts) | T10 | B5 | P33 `owner_cpu_budget`, `compute_budget` | the refusal tests of each |
| A10 | Any code that can change a number changes the version | — | `engine_version` hashes core and worker files (`version.ts`) | `screener_engine`, `snapshot_digest` | existing version tests |

---

## 9. Phased build plan (PROPOSED; each phase needs the user's "go")

Every step follows AGENTS.md: tests, migrations with `$verify$` and read-back, changelogs, `ERRORS_AND_SOLUTIONS.md`,
deployment `SUCCESS` read back, CLI deploys of terminal-api and the publisher under the M248 procedure outside
00:00-01:00 and 12:00-13:05 UTC (`terminal.md` R4).

### Phase 0 — Measure (no user-visible change)

| Step | Files |
|---|---|
| Backtest phase timings, `request_key`, `preview_wait_ms` in the logs (`backtest.md` §7) | `apps/backtest-worker/src/run.ts`, `src/server.ts`, `src/validate.ts`; `apps/edge-bff/app/backtest.py` (log fields) |
| Terminal page timing script (T12.2) | `verification/terminal_api/page_timing_dev.py` (new, from `verification/backtest/page_timing_dev.py`) |
| One `?perf=1` reading from Indonesia (T12.1) | the user, on a cold open, a warm open and a ticker switch |
| Shared multi-owner load harness (X4): S21/S23, L1, T12.3, and the section 5 lock reading | temporary job service (approval); `verification/edge_multiuser/LOAD.md` |

### Phase 1 — With the Screener (same branch, same deploy windows)

| Step | Items | Files |
|---|---|---|
| 1a | R1 check (content-key commits present), then T5 refs under content keys | `apps/terminal-publisher/publisher.py`, `apps/terminal-publisher/tests/test_publisher.py` |
| 1b | One terminal-api CLI deploy with the Screener's `/xsection` (report 8.12): T1, T3, T5 `refs_index`, T9 healthcheck `/ready` and `TERMINAL_POOL_MAX` | `apps/terminal-api/app/{config,main,store,bucket}.py`; `apps/terminal-api/tests/test_api.py`; `apps/terminal-api/tests/test_store_pg.py` (new); `database/migrations/<date>_terminal_owner_service_accounts.sql`; `.railway/railway.ts`; `BACKTEST_END_TO_END.md` §6.2; `CONTRACT.md` §2, §12 (U1) |
| 1c | screener-worker Railway block: healthcheck `/ready`, memory limit from its measured peak, its own terminal key (T1), 1 replica on dev | `.railway/railway.ts`; Railway variables (names only in the changelog) |
| 1d | backtest-worker: `TERMINAL_PROXY_KEY` points at its service key (T1); no code change; Backtest E2E | Railway variables; `RAILWAY_CHANGELOG.md` |
| 1e | T7 Terminal integrity (accuracy, independent of the Screener) | `apps/edge-bff/terminal/src/data/worker.ts`, `live.ts`; `apps/edge-bff/terminal/tests/data/download.test.ts` |

### Phase 2 — Backtest

| Step | Items | Files |
|---|---|---|
| 2a | B1 + B2 | worker `src/server.ts`, `src/terminal.ts` (both workers' tests, X5), `src/config.ts`, `README.md`; edge-bff `app/backtest.py`, `app/config.py`; page `apps/edge-bff/backtest/src/run.ts`; tests `run.test.ts`, `server.test.ts`, `tests/test_backtest.py` |
| 2b | B3 (K = 2, P = 2) + B4 + B10 + X2; precondition T1 live (X1) | worker `src/server.ts`, `src/compute.ts`, `src/load.ts`, `src/config.ts`; shared lane scheduler module; edge-bff `app/backtest.py`; `database/migrations/<date>_edge_bff_backtest_multiuser.sql` (`slot` + unique index); `.railway/railway.ts` (healthcheck, memory limit) |
| 2c | B5 (off by default), B9, B11 | edge-bff `app/backtest.py`, `app/config.py`; page `signals.ts`, `preview.ts`; worker `src/compute.ts`; `CONTRACT.md` §8, §9, §11 |
| 2d | B8 pre-warm; B7 `/plan` before U ≈ 50 | worker `src/catalog.ts`, `src/load.ts`; `apps/terminal-api/app/main.py` + tests |
| 2e | B6 when BT6 ≥ 10 %; B12 (a) when BT8 fires | core `robustness.ts`, `result.ts`, `contract.ts`; worker `src/load.ts`, `src/run.ts`; edge-bff `app/backtest.py`; migration columns `request_key`, `reuse_inputs`, `reused_from` |

### Phase 3 — Terminal

| Step | Items | Files |
|---|---|---|
| 3a | T4 + T11 (needs T5) | `apps/terminal-api/app/main.py` (`BundleRequest`, `grant()`); `apps/edge-bff/terminal/src/data/live.ts`, `rack.ts`; `apps/edge-bff/backtest/src/api/live.ts`; tests in `test_api.py`, `test_terminal.py`, `terminal/tests/data/live.test.ts` |
| 3b | T6 + T8 | `apps/edge-bff/terminal/src/data/boot.ts` (new), `live.ts`; terminal-api `/bundle` answers `finished_at`; `boot.test.ts` |
| 3c | T9 rest: manifest warm-up on `finished_at`, logo bodies per publication | `apps/terminal-api/app/bucket.py`, `main.py:313` |

### Phase 4 — Gate before the first external user (accounts and launch stay on hold)

T2 with D-T2; T10 values and the 1e9 override removed for people; P32 second Screener replica; D-T3 second terminal-api
replica; D-R7 Backtest availability; B5 and X3 values; data terms per source (MU2, E6); environment (MU20); the Phase 0
harness re-run at the target U with every row of section 7 met.

---

## 10. Scale-out triggers (PROPOSED thresholds; Phase 0 sets them)

| # | Signal (source) | Threshold | Action |
|---|---|---|---|
| S-1 | Backtest queue wait p95 over 15 min in busy hours (`started_at - created_at`) | > 5 s | K + 2, within the memory check S-3 |
| S-2 | Backtest preview wait p95 (`preview_wait_ms`) | > 1 s | P + 1 |
| S-3 | Worker RSS (Railway metrics), either worker | > 70 % of the memory limit | lower cache budgets or raise the limit to peak × 1.5 |
| S-4 | Screener `queue_ms` p95, `BUSY` share, replica CPU | > 300 ms / > 1 % / > 70 % of K | raise K, then a replica (6d.10) |
| S-5 | Light owners' p95 while one owner loops heavy work (S23, E1) | > 1.5 × their solo p95 | tighten lanes or budgets |
| S-6 | terminal-api grant hold p95, or lock busy (new log field) | > 50 ms / > 50 % | T1, then T4 or T2 (X1) |
| S-7 | `/bundle` p95 through edge-bff | > 1 s | B7 if not done; check S-6 |
| S-8 | edge-bff event-loop lag p95, pool waits | > 50 ms / > 0 at peak | MP-14 split (loops in one service, AI Orc unchanged), then web processes (≤ 3 processes in all) |
| S-9 | Connections per role against `rolconnlimit` | > 70 % | lower pools or raise the role limit by migration |
| S-10 | `backtest_results` and `terminal.access_log` size | > 10 GB / > 2 GB | B11 retention; B7; D-T6 |
| S-11 | Duplicate share of Backtest `request_key` | ≥ 10 % | build B6 |
| S-12 | K ≥ 8 and S-1 still firing, or an availability floor decided | — | B12 (a), a second worker service |
| S-13 | Railway usage per service week on week | > +30 % | review against section 6 |

---

## 11. Risks

- **R1 (accuracy).** FACT: HEAD's `apps/terminal-publisher/publisher.py:514, 533` writes fixed keys and
  `git merge-base --is-ancestor 6051f4d HEAD` is false (`terminal.md` §9 R1), while `EXEC.md` records the cherry-pick as
  decided. A publisher deploy from this branch before the content-key commits are present would bring back
  `DATA_INTEGRITY` for the Backtest and mismatched charts for the Terminal (until T7). Phase 1a checks it first.
- **R2 (order).** Scaling the Backtest before T1 or B7 moves the bottleneck to terminal-api and slows every Terminal user
  (section 5, X1).
- **R3 (shared code).** `terminal.ts` is shared by both workers (X5); a Backtest change there changes `engine_version` and
  can change the Screener's downloads.
- **R4 (deploys).** terminal-api and the publisher deploy by CLI upload (M248), outside the publisher windows; each
  Phase 1 deploy is one window.
- **R5 (memory billing).** Railway bills resident memory, page cache included; backtest-worker has no memory limit today
  (FACT, `rt_status.json`). Every worker gets a limit from a measured peak.
- **R6 (replicas).** How the private network spreads connections over replicas is UNKNOWN (6d M-U2); it matters for
  P32's two Screener replicas and a second terminal-api replica. The Backtest avoids it with explicit origins (B12 a).
- **R7 (role limits).** Two terminal-api replicas × 2 processes × 8 = 32 > 20 unless `TERMINAL_POOL_MAX` is 4; edge-bff ≤ 3
  processes.
- **R8 (platform).** One Postgres without HA or PITR, one `dev` environment shared with tests (CAP findings 8-10, MU20).
- **R9 (data terms).** Whether each source may be shown to external users is UNKNOWN (E6, MU2). It gates launch, not the
  runtime.
- **R10 (models).** Every number in sections 5-7 is a model on inferred profiles; the area designs used different bases,
  re-based here. Phase 0 replaces them.
- **R12 (AI Orc coupling).** FACT: the same switch starts the Orc loop and the Backtest loop in every edge-bff process
  (`apps/edge-bff/app/main.py:191, 194`). Any second edge-bff process for these tabs goes through the MP-14 split first,
  so AI Orc's dispatch stays as it is (section 4.2).
- **R11 (code drift).** The deployed edge-bff and Terminal page are built from `main` (`baa0903`, page `15ec418`), not this
  branch; Terminal changes are built on `main`'s version (`terminal.md` R2).

---

## 12. Decisions for the user

| Id | Question | Options | Recommendation |
|---|---|---|---|
| RT1 | Adopt the shared principles RP1-RP12 as the rule for Terminal, Backtest and Screener | yes / amend | Yes. The Screener already follows them; Backtest and Terminal converge on them |
| RT2 | Order of work | phases 0-4 of section 9, with X1 (T1 or B7 before Backtest K ≥ 4) | "go" for Phase 0 and Phase 1 together with the Screener; Phase 2 next; Phase 3 after; Phase 4 waits with accounts |
| RT3 | Latency targets of section 7 as acceptance criteria per phase | accept / change values | Accept; measured from the sandbox plus one Indonesian `?perf=1` reading |
| RT4 | Backtest result reuse across owners (D-R1) | off / same owner / any owner | Same owner first; any owner only after logs show ≥ 10 % duplicates |
| RT5 | Per-owner budgets: where and when (D-R2, D-T1, P33 values, X3) | per replica only / plus one daily ledger in edge-bff | Build the mechanisms now with generous values (Backtest daily limits off; Terminal override kept for the one owner); the ledger before the first external user; values from the load test and the user's tiers |
| RT6 | Re-queue a Backtest job lost in a deploy or crash (D-R3; changes D-B1) | keep `WORKER_LOST` / re-queue once | Re-queue once: trials are written only on finish |
| RT7 | terminal-api audit of worker data: each use or each download (D-R4); retention of service-account rows (D-T6) | use / download; 90 days / shorter | Download (B7), and keep 90 days for every row as the user decided on 2026-10-26: with B7 the worker's rows are only downloads |
| RT8 | Decoded cache without re-reading bytes (D-R5) | keep re-verifying / trust the decoded copy | Keep re-verifying (CONTRACT §2 unchanged) |
| RT9 | Backtest result retention (D-R6) | 30 days / newest N per owner and ≤ 30 days / a bucket | Newest 50 per owner and at most 30 days |
| RT10 | Availability at the first external user (D-R7, D-T3; P32 decided for the Screener) | one replica each / two | Screener 2 (decided); terminal-api 2 (about USD 1.2 a month); Backtest 1 with drain and re-queue, a second worker service at open launch or on S-12 |
| RT11 | terminal-api's public domain (D-T2) | remove / refuse gateway and service keys that arrive through it | Remove before the owner header is trusted (EDGE pages use edge-bff only) |
| RT12 | Cache-first Terminal: draw cached data only after the first authenticated answer (D-T4) | after / before | After (shared devices) |
| RT13 | Regions (D-T5) | keep services `sfo`, bucket `sin` / move | Keep until the Indonesian reading |
| RT14 | Sleep the pools when idle (Railway Serverless) | always on / sleep outside market hours with a pre-warm cron | Always on: saves at most about USD 8 a month, costs the first user 15-25 s; revisit if the Screener's cold start shrinks |
| RT15 | Fairness weighting for Backtest jobs | round robin by count (MU MP-15) / least compute in the last hour with 60 s aging (B4) | By compute with aging: job costs differ about 10× (0.5 s against 5.5 s) |

---

## 13. Unknowns

| # | Unknown | Check |
|---|---|---|
| U-RT1 | Whether the terminal-api usage aggregate grows linearly with the account's rows (section 5) | Phase 0 harness: grant hold p95 at 10 / 50 / 200 synthetic owners |
| U-RT2 | Load times from Indonesia, and the `sin` bucket's TTFB there (U-T1, U-T2) | one `?perf=1` reading by the user |
| U-RT3 | Real users: daily, at once, and per-tab use (P29 numbers, MU5) | the user; logs after launch |
| U-RT4 | Private-network spread over replicas (6d M-U2); traffic before a new replica's healthcheck (M-U3) | DNS answers and per-replica counts in the harness |
| U-RT5 | Per-phase CPU of a warm backtest (decode against engine), RSS per thread (U-B1, U-B2) | Phase 0 timings; the B3 memory test |
| U-RT6 | Railway's drain or overlap settings for a deploy (U-B3) | Railway documentation, then a test deploy |
| U-RT7 | Screener RSS per replica and cold start in production shape (M-U4) | 6d S19, S24 |
| U-RT8 | Duplicate share of identical Backtest requests (U-B5) | `request_key` logging (S-11) |
| U-RT9 | Data terms per source for external users (E6, MU2) | the user, per provider |

---

## 14. Evidence index (read-only)

- Area designs: `mu_runtime/backtest.md`, `mu_runtime/terminal.md`, `mu_runtime/silo_research.md`; Screener 6c/6d
  (`verification/screener/AUDIT.md`, copies in `report/`); `verification/edge_multiuser/capacity_fairness_scale_cost.md`,
  `verification/edge_multiuser/AUDIT.md`.
- Models: `mu_runtime/bt_queue.py`, `mu_runtime/bt_cost.py` (Backtest); `mu_runtime/rt_cost.py` (combined cost);
  `mu_runtime/rt_lock.py` (shared grant gate). Run with `python3 -I <file>`.
- Railway: `npx -y @railway/cli@5.71.0 status --json` at about 20:00 UTC 2026-10-28, saved as `mu_runtime/rt_status.json`
  (no secrets; replicas, healthchecks, sleep, limits, deployment ids `7b05b9fd`, `689dc465`, `292f7caa`, `b8b51052`).
- Code: `git show origin/main:` (`15ec418`) for `apps/backtest-worker/src/server.ts`, `apps/edge-bff/app/backtest.py`,
  `apps/terminal-api/app/store.py`, `apps/edge-bff/terminal/src/data/worker.ts`; branch HEAD `7807d2b` for
  `apps/edge-bff/app/screener.py`, `apps/screener-worker/src/config.ts`, `snapshot.ts`; the running Screener build's
  uncommitted `apps/screener-worker/src/{pool,refresh,server}.ts`; `database/migrations/20261025_100_create_terminal_schema.sql:59`.
- Records: `PLAN.md` EDGE-MULTIUSER (user's words of 2026-10-28); `EXEC.md:8476-8516` (EXEC-SCREENER decisions P29-P34).
