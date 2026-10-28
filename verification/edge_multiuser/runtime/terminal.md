# Terminal data path for many users: cost, speed, accuracy (read-only design, 2026-10-28)

**Scope.** User 2026-10-28 (`PLAN.md` EDGE-MULTIUSER, "Arah user berikutnya"): "Yang mesti dipastikan adalah screener worker
beserta backtest machine secara arsitektur harus bisa menghandle multi-user termasuk terminal. Untuk AI org, leave as is saja.
Untuk terminal backtest dan screener, efisiensi biaya dan efisiensi proses menjadi prioritas. Akurasi juga." Users are external
(P29). Accounts are on hold, so every proposal keys per-user limits on `owner_key` (one owner today, many later). This file is
the Terminal area: how the Terminal page (and the Backtest page's chart loads, which use the same path) gets per-ticker files
from the bucket through terminal-api. AI Orc is out of scope.

**Read-only.** No repository edit, no state-changing git, no Railway mutation, no database write. Required reading done
(AGENTS.md: `BACKTEST_END_TO_END.md` and `apps/edge-bff/backtest/CONTRACT.md` in full, because `/bundle` is a route the
Backtest reads).

**Evidence base (read 2026-10-28 19:20-19:45 UTC).**
- Repository: branch `claude/charming-hamilton-faq25e`, HEAD `25b08e6`. Deployed code differs from HEAD in places, so the
  deployed commit is named where it matters:
  - edge-bff deployment `7b05b9fd` (SUCCESS 2026-10-28 16:52 UTC) is built from `main` `baa0903`; the Terminal page at
    `origin/main` `15ec418` is that code (`live.ts` there has `loadAsset`/`loadAssetFlow`, absent at HEAD).
  - terminal-api deployment `689dc465` (SUCCESS 2026-10-27 15:56 UTC) is a CLI upload of `main` `6f318ea`
    (`RAILWAY_CHANGELOG.md`, EXEC-BACKTEST-LOAD entry). HEAD adds only `/xsection` and the `/state` xsection index; `store.py`
    and `quota.py` are unchanged (`git diff 6f318ea HEAD --stat -- apps/terminal-api/app`). Line numbers below are HEAD's.
  - terminal-publisher deployment `b8b51052` (2026-10-28 12:01 UTC). Its 12:00 UTC run logged `event="gc" ...
    families=["broker","events","pack","price"] objects_listed=17498`, i.e. the content-key build of PR #41 (ERRORS M250 fix,
    `6051f4d`) is live. HEAD's `apps/terminal-publisher/publisher.py:514, 533` still writes fixed keys (`content_key` is absent:
    `grep -c content_key` = 0; `git merge-base --is-ancestor 6051f4d HEAD` false).
- Railway (`@railway/cli@5.71.0`): `status --json`, `metrics` (7 days, hourly points; HTTP 16 h), `logs` of terminal-publisher.
- Live database through pgweb (`tools/pgq2.py`, read-only role, which cannot read schema `terminal`; statistics only):
  `pg_stat_user_tables`, `pg_stat_user_indexes`, `pg_postmaster_start_time()` = 2026-10-22 05:09 UTC.
- One unauthenticated HTTPS probe of the public shell and frame document (`curl -D -`), no data route.

**Labels.** FACT (file:line, measurement or command), INFERENCE, PROPOSED, UNKNOWN. Prices as recorded in the Screener report
6d and the capacity audit (Railway docs read 2026-10-28): RAM USD 10/GB-month (USD 0.0139/GB-hour), vCPU USD 20/vCPU-month,
egress USD 0.05/GB, volume USD 0.15/GB-month, bucket storage USD 0.015/GB-month, bucket egress and S3 operations free,
private network free (`verification/terminal_api/PHASE1_PHASE2.md:271-272`; 06d.1).

---

## 1. Summary (one screen)

1. **The Terminal is cheap at any of the user counts asked; cost is not the constraint.** INFERENCE from FACT inputs (section
   7): the whole Terminal path (terminal-api, publisher, bucket, its share of edge-bff egress and Postgres) costs about
   USD 2.0 / 2.2 / 2.8 a month at 10 / 50 / 200 daily users today, and about USD 3.2 / 3.3 / 3.8 with the proposals (which add
   a second terminal-api replica for availability). The marginal user costs under USD 0.01 a month, because browsers
   download from the bucket (free egress) and the server only signs URLs.
2. **What does not scale is identity, fairness and the per-open critical path, not throughput.** FACT: every page and every
   worker request is one subscriber under one advisory lock (`apps/terminal-api/app/main.py:174-180`, `store.py:45-46`) with
   quotas overridden to 1e9 (TEMPORARY, `verification/terminal_api/jobs/quota_unlimited_edge_owner.sql`). INFERENCE: in
   steady use the lock is about 30 % busy at 200 users (the backtest worker's grants included), but a burst serialises (60 users opening at once: up to about
   6-8 s for the last grant, section 8), a backtest job's 13-16 grants queue in front of users, and without the override one
   heavy user or a scraper exhausts everyone's quota; with it there is no per-person bound or audit at all.
3. **Each ticker open costs 4 grants and re-downloads 3 unversioned reference files, and the chart waits for one of them.**
   FACT (deployed `15ec418`): a ticker switch or a timeframe change reloads the frame (`main.ts:46`, `search.ts:53`); each load
   asks `/reference/tickers`, `/brokers`, `/logos` (each a locked grant with an audit row, then a bucket download without
   sha256, so never cached) and one `/bundle`, and awaits the ticker list before using the remembered ticker
   (`live.ts:152-165`). INFERENCE: the ticker-list download (one bucket round trip, 0.72-1.42 s per object from the US sandbox,
   ERRORS M240) sits in the critical path of every warm open.
4. **Accuracy gaps on the Terminal page.** FACT: the Terminal's `download()` draws bytes whose sha256 differs from the one
   `/bundle` announced; it only skips caching them (`worker.ts:36-42` at `15ec418`; ERRORS M250 item 5). The Backtest page and
   worker refuse such bytes (`inflateVerified`). Also (INFERENCE from `bucket.py:61-77` and two processes): for up to 60 s after a
   publication, and for any page left open across a publication, one chart can mix files of two publications (the base ticker
   from one, IHSG, compare or asset series from the next). And (FACT) HEAD's publisher would bring back in-place overwrites
   (M250) if deployed before the content-key commits are cherry-picked.
5. **Proposed path (section 5):** (T1) service accounts for the two workers, (T2) one terminal subscriber per `owner_key`
   through the gateway, so locks and quotas are per person, (T3) the subscriber lookup folded into the grant, (T4) one
   `/bundle` per open carrying `refs` and a `have` list, which grants and counts only files the browser does not hold, (T5)
   content-addressed reference files listed in `state.json`, (T6) cache-first boot (already approved into the plan as
   TERMINAL-CACHE-FIRST), (T7) sha256 and size checked before drawing, (T8) one publication per page, (T9) terminal-api
   healthcheck, pool sizing, second replica, manifest warm-up and logo cache, (T10) per-owner quotas sized from the page's own
   request pattern with the four gate parts, (T11) one bundle per added asset, (T12) measurements. No CDN, no long-lived
   presigned URLs, no region move now (section 4).
6. **Load time (section 8, INFERENCE):** steady load time does not change between 10, 50 and 200 users in either design
   (terminal-api stays under about 5 % busy). The proposals change the per-open path: a cached ticker switch from about
   1.8-2.5 s to about 0.7-0.9 s, a warm tab open from 1.77 s (FACT) to about 1.3-1.5 s, measured from the US sandbox; from
   Indonesia nothing has ever been measured (UNKNOWN, `ERRORS_AND_SOLUTIONS.md:2307`).

---

## 2. Today, measured

### 2.1 Topology and runtime (FACT)

| Part | State | Evidence |
|---|---|---|
| edge-bff | `sfo`, 1 replica, `--workers 1`, healthcheck `/ready`; forwards `/api/terminal/v1/*` with the one `x-terminal-proxy-key` over the private network, one pooled `httpx.AsyncClient` | `railway status --json` (deployment `7b05b9fd`, `multiRegionConfig {sfo: 1}`); `apps/edge-bff/app/main.py:401-431` |
| edge-bff session check | one `SELECT owner_key` per proxied request (logos included), pool 1-6 | `main.py:265-270`; `store.py:27, 63-65` |
| terminal-api | `sfo`, 1 replica, `uvicorn --workers 2`, sync routes; **no healthcheck path**; public domain `terminal-api-dev.up.railway.app` | `railway status --json` (`689dc465`, `healthcheckPath` null); `apps/terminal-api/Dockerfile:10` |
| terminal-api DB pool | `min_size=1, max_size=8` per process: 16 of the role's 20 | `apps/terminal-api/app/store.py:24-25`; live `pg_roles.rolconnlimit` `terminal_api_login` 20 |
| Identity | a request with the proxy key is the subscriber `TERMINAL_PROXY_SUBSCRIBER`, looked up in its own transaction on every request | `main.py:157-180`; `store.py:117-119` |
| Grant | per-subscriber `pg_advisory_xact_lock`, limits, usage aggregated from the subscriber's last 24 h of `terminal.access_log`, one INSERT; prune of rows > 90 days at most every 6 h per process | `main.py:340-361`; `store.py:45-80` |
| Reference grant | `/reference/{name}`: the same lock, limits, usage and INSERT for one file, no sha256 | `main.py:288-300` |
| Logo | `/logo/{T}`: no quota or audit; reads the logo object from the bucket on **every** call (no body cache), `Cache-Control: private, max-age=604800` | `main.py:302-314`; `bucket.py:104-119` |
| Manifest cache | per process, cleared when `state.json` `finished_at` changes (checked at most every 60 s) or above 4,000 entries; a miss reads the manifest from the `sin` bucket | `bucket.py:11, 61-77, 92-102`; `config.py:24` |
| Presign | local SigV4 signing, TTL `url_ttl_seconds` 120 | `bucket.py:121-122`; migration `20261025_100_create_terminal_schema.sql:79` |
| Bucket | `terminal-display` in `sin` (Tigris host `*.t3.storageapi.dev`), HTTP/1.1, 17,498 objects listed by the 12:00 UTC run | `.railway/railway.ts:23`; ERRORS M240 (`ERRORS_AND_SOLUTIONS.md:2264-2282`); publisher log 2026-10-28 12:11:32 UTC |
| Publisher | twice a day; 2026-10-28 12:00 UTC run: 2,057.7 s, 1,758 files, 16.49 MB written; planning read 800 manifests in 7.5 min (12:03:28 → 12:10:58) | `railway logs -s terminal-publisher` |
| Browser cache | IndexedDB `terminal-files`, 50 MB LRU, keyed by sha256, shared by Terminal and Backtest | `apps/edge-bff/terminal/src/data/rack.ts:15-16, 29-70` |
| Quota defaults | `files_per_hour` 60, `tickers_per_hour` 30, `tickers_per_day` 150, `megabytes_per_day` 300, `history_per_hour` 20, URL TTL 120 s | migration `20261025_100:78-88` |

Railway's edge compresses and speaks HTTP/2 (FACT, probe from the sandbox 2026-10-28): `/terminal` → `content-encoding: gzip`,
103,617 bytes, `HTTP/2`, `cache-control: no-store`, `x-railway-edge: iad1`; `/terminal-app/` → 4,142 bytes gzip, no-store. This
settles the Screener report's L-U1 (the app has no gzip middleware, the edge compresses).

### 2.2 What one Terminal view asks (FACT from code at `15ec418`; sizes as labelled)

| Action | Requests through edge-bff | terminal-api grants (= audit rows) | Files counted in quota | Bytes counted | Bucket downloads cold / warm |
|---|---|---|---|---|---|
| Tab open, ticker switch or timeframe change (frame reload, `main.ts:46`, `search.ts:53`) | frame document, session, 3 × `/reference`, 1 × `/bundle` (`live.ts:150-165`) | 4 | 3 + 5 for a stock (price pack, broker archive, 2 yearly broker files, events), 3 + 1 for IHSG | refs about 54 KB (INFERENCE below) + the bundle (FACT examples: IHSG price pack 42,106 B, ERRORS M250; BBRI broker archive 2.2 MB, `BACKTEST_END_TO_END.md:479`; ANTM 21 yearly files 2.38 MB, `FUTURE_PLAN.md`) | 8 / 3 (the refs are never cached) + any file whose sha256 changed |
| Relative performance (IHSG) | 1 × `/bundle` | 1 | 1 | about 42 KB | 1 / 0 |
| Compare series | 1 × `/bundle` per series | 1 | 1 | about 30-40 KB | 1 / 0 |
| Add asset (at most 2; EXEC-TERMINAL-ASSETS) | 2 × `/bundle` (price, then broker; `live.ts:212-227`) | 2 | 1 + up to 4 | price pack + broker files | up to 5 / 0 |
| Logo shown (lazy `<img>`, search list, symbol pill, legend; `context.ts:48-49`) | 1 GET each | 0 | 0 | 0 | 0 for the browser; terminal-api reads the bucket each time |
| Backtest page, shown ticker | session (memoised), 1 × `/bundle` (price ± broker) | 1 | 1-4 | price ± broker | as above |

Reference sizes (INFERENCE, built from the live tables the publisher reads, same column layout, gzip level 9): `ref/tickers`
845 rows → 14,449 B; `ref/brokers` 112 rows → 1,274 B; `ref/logos` (845 rows with a 64-hex sha256 each, synthetic values)
→ about 37.7 KB. Exact per-ticker file sizes need manifests, which need the gateway key (UNKNOWN here; settle with the load
test of T12).

### 2.3 Server-side timings and load (FACT)

| Measure | Value | Source |
|---|---|---|
| edge-bff `POST /api/terminal/v1/bundle`, last 16 h | 29 requests, p50 94 ms, p90 331 ms | `railway metrics -s edge-bff --http --path ... --since 16h` |
| edge-bff `GET .../reference/tickers` | 14 requests, p50 128 ms | same |
| edge-bff `GET /api/v1/auth/session` | 29 requests, p50 26 ms | same |
| Concurrent `/bundle` (packs) | 1 → 0.23 s; 5 → median 0.31 (max 0.42); 10 → 0.42 (0.97); 20 → 0.53 (0.71) | `ERRORS_AND_SOLUTIONS.md`, "EXEC-TERMINAL-SPEED — selesai" |
| Quota count (usage aggregate) | 0.85 ms, seq scan 59 buffers, 3,271 rows | same |
| Bucket per object | TTFB 0.72-1.42 s from the US sandbox, HTTP/1.1, 6 connections per host | ERRORS M240 |
| Page (US sandbox, `verification/backtest/page_timing_dev.py`) | Terminal chart first open 2.28 s, second open 1.77 s (2026-10-27); 2026-10-26 `?perf=1` second visit ANTM 2.5 s, of which 2.2 s waiting for the ticker list and `/bundle` | `BACKTEST_END_TO_END.md:745-746`; `PLAN.md:888-889` |
| From Indonesia | never received | `ERRORS_AND_SOLUTIONS.md:2307` |

Railway resources, 7 days to 2026-10-28 19:00 UTC, hourly points (FACT; cost INFERENCE at the prices above):

| Service | avg RSS | avg vCPU | public TX | USD/month |
|---|---|---|---|---|
| terminal-api | 0.114 GB (max 0.443) | 0.003 | 0.04 GB/7 d | ≈ 1.2 (the usage API gave 1.52 for 10-24..28, capacity audit 2.2) |
| terminal-publisher | 8.07 GB-hours/7 d | 0.46 vCPU-hours/7 d | 1.006 GB/7 d (uploads to the bucket count as egress) | ≈ 0.48 + 0.06 + 0.22 = 0.75 |
| edge-bff | 0.119 GB | 0.005 | 0.20 GB/7 d (all tabs) | ≈ 1.0 (all tabs) |

Postgres (FACT, live statistics since 2026-10-22 05:09 UTC, 6.6 days):
- `terminal.access_log`: 6,952 rows, 2,424 kB with indexes (≈ 357 B per row), seq scans 3,886 against index scans 526.
- `terminal.subscriber_email_key`: 44,485 index scans, `quota_override_pkey` 4,370, `terminal.quota` seq scans 4,369.
  INFERENCE: about 4,370 grant transactions (one `limits()` each) against about 44,000 proxied requests, each of which opened
  its own transaction only to look up the gateway subscriber (`main.py:176-177`). About 90 % of terminal-api's transactions
  are that lookup (mostly the backtest worker's `/manifest` and `/state` calls).

---

## 3. What grows with users and what does not

| Item | Grows with | Today | At 200 daily users (INFERENCE; profile in section 7) |
|---|---|---|---|
| Publisher runs, bucket objects and storage, `state.json` reads | publications (2 a day) | 2 runs, about 0.7 GB | same |
| terminal-api memory (manifests ≤ 4,000 per process, logo index) | universe, not users | 0.114 GB | same per replica |
| Manifest reads from `sin` after a publication | publications × processes × tickers opened | ≤ 845 × 2 | same (bounded by the universe) |
| Grants, edge-bff session checks, audit rows | users × opens | 4 per open | 41,800 rows/day today, 11,400 with T4 |
| `access_log` size at 90 days | users × opens × 90 | 2.4 MB | 1.34 GB today, 0.37 GB with T4 |
| Usage aggregate per grant on the shared account | all users' rows of the last 24 h | 0.85 ms at 3,271 rows | about 10-30 ms with the workers' rows (section 8); per person with T2 it is bounded by that person's own quota |
| edge-bff egress (frame, JSON, logos, shell) | users × opens | 0.2 GB/7 d (all tabs) | about 11 GB/month (section 7) |
| Bucket downloads by browsers | users × (first opens + daily changed files) | free | free |
| Browser cache (≤ 50 MB per browser) | per device | — | on users' devices, no server cost |
| Screener and backtest worker grants | publications × replicas (Screener); jobs (Backtest) | shared account | own service accounts with T1 |

---

## 4. Options evaluated

### 4.1 Per-user grants without one global lock

| Option | What it does | Verdict |
|---|---|---|
| (a) Per-owner subscriber under the gateway (P31, decided "identitas terminal-api per user plus akun layanan untuk worker", `EXEC.md:8507-8510`) | edge-bff names the session's `owner_key`; terminal-api maps it to its own subscriber row; the existing per-subscriber lock, quotas and audit then apply per person | **PROPOSED (T2)**. Keeps the one mechanism that already works for direct subscribers; no new service |
| (b) Long-lived signed URLs for content-addressed files | SigV4 allows up to 7 days; a URL signed once per (key, day) would be the same for every user, so HTTP caches and a CDN could share it | **Not proposed.** The grant is still needed for quota and audit (who opened which ticker), so it removes no request; a leaked URL gives anyone the file for days, which the data terms (E6/MU2, UNKNOWN) may forbid; the browser already caches by sha256 in IndexedDB, so it gains nothing per user (`BACKTEST_END_TO_END.md:302-304`: every presigned URL is new and readers keep their own sha256 caches) |
| (c) terminal-api or edge-bff streams the files itself (authenticated, `immutable` by sha) | HTTP/2 via Railway's edge instead of the bucket's HTTP/1.1 | **Not proposed.** Egress becomes billable (about 0.4 GB per active user-month of first-open bytes, INFERENCE: about USD 4 a month at 200 users), and for users in Indonesia the bytes would cross the Pacific twice (`sin` bucket → `sfo` service → user) instead of coming from Singapore |

### 4.2 CDN and long cache headers

- **Data files (presigned).** A long `max-age` has no effect: each grant gives a new URL (FACT, `BACKTEST_END_TO_END.md:302-304`).
  Content keys (M250, live) already make the sha256 cache exact. A CDN in front of the bucket would need edge-verified tokens
  (another vendor and design) and saves no money (bucket egress and S3 operations are free, FACT recorded). INFERENCE: it
  could save the bucket's per-object TTFB on cold opens; whether that TTFB is large from Indonesia is UNKNOWN (U-T2).
  **Not now;** revisit only if the Indonesian measurement (T12) shows the bucket TTFB dominating cold opens.
- **Objects edge-bff or terminal-api serve under a stable versioned URL** (logos with `?v=<sha>`, `context.ts:49`; reference
  lists once versioned, T5; the frame's hashed assets already `immutable`, `main.py:364`): `Cache-Control: private,
  max-age=31536000, immutable` removes every repeat request. **PROPOSED (T9 logos; T5/T6 refs go to IndexedDB by sha).**
- **xsection files (Screener):** read by the screener-worker, never by browsers; per-replica caches by sha256; no CDN question.
- Railway's edge: no cache headers in the probe and no CDN feature found (INFERENCE; U-T3).

### 4.3 Bucket region against service region

- FACT: bucket `sin`, services and Postgres `sfo`. From the US sandbox a bucket object costs 0.72-1.42 s TTFB (M240); the
  backtest worker measured `sfo` → bucket 2,268 ms per file and `sin` → terminal-api 892 ms per `/bundle`
  (`BACKTEST_END_TO_END.md:393-398`), so the worker stayed in `sfo`.
- INFERENCE: for browsers in Indonesia the `sin` bucket is the near side (likely tens to a few hundred ms TTFB, UNKNOWN U-T2)
  and `sfo` is the far side (about 0.2 s per API round trip). Today's open makes 3-4 sequential `sfo` round trips (frame,
  session, refs or bundle) and 1-2 bucket round trips; with T4-T6 a cached switch makes 2 (frame, session) and none to the
  bucket before drawing.
- **PROPOSED: keep the bucket in `sin` and the services in `sfo`.** Moving the API tier to `sin` saves at most about 0.35 s
  per open from Indonesia (INFERENCE) but needs either Postgres (51 GB) in `sin` or one-round-trip grants plus cached sessions
  across the Pacific; not worth it before T12 measures Indonesia. Server-side readers of the bucket (terminal-api manifests,
  workers) are covered by their per-publication caches (T9 warm-up).

### 4.4 Counters against the log aggregate

- FACT: usage is recomputed from the subscriber's last 24 h of `access_log` on every grant (`store.py:56-67`).
- INFERENCE: with one subscriber per person (T2), a person's rows per day are bounded by that person's own quotas (a few hundred
  at most), so the aggregate stays about 1 ms; counters are not needed for people. For the worker service accounts (tens of
  thousands of grants a day at 200 users) a counter is the right shape (T1).
- **PROPOSED:** people keep the rolling log aggregate (exact rolling windows, no new table); service accounts get an hourly
  counter with a ceiling. Counters for people only if trigger T6 of the capacity audit fires (grant > 50 ms p95).

### 4.5 terminal-api processes and replicas

- INFERENCE: per grant about 5-10 ms of CPU across request handling and up to 5 presigns; two processes give hundreds of
  grants a second, against a peak of about 2-12 grants a second at 200 users. Throughput needs no replica up to well beyond
  200 users.
- A replica is for availability: today a crash or a deploy without a healthcheck (FACT: none configured) leaves every Terminal
  and Backtest page with 503 `TERMINAL_UNAVAILABLE` until the process is back.
- Constraints for a second replica (FACT): pool 2 × 8 per replica against the role's 20; manifest cache, prune timer and
  `pruned` flag are per process (`main.py:338, 357-360`), which is safe (idempotent DELETE, caches only).

---

## 5. Proposals

Each proposal: need; general class; fix and owning layer (exact files); covers / does not cover; risks and cost; verification;
permanence. All PROPOSED; nothing executed.

### T1 — Service accounts for backtest-worker and screener-worker (P31, second half)

- **Need.** FACT: the backtest worker and the screener-worker present the gateway key and are booked on the people's
  subscriber (`BACKTEST_END_TO_END.md:313-327`; CONTRACT U1, TEMPORARY). A 12-stock job's 13-16 grants (16 download lanes,
  `BACKTEST_END_TO_END.md:458-460`) take the same lock as the person browsing; their rows inflate the person's usage
  aggregate; the gateway key, which T2 must trust to name an owner, sits in three services.
- **Class.** One shared identity for callers with different trust and volume.
- **Fix and layer.**
  - terminal-api `app/config.py`: `TERMINAL_SERVICE_KEYS` (names only; values are Railway secrets) mapping a key to a service
    account e-mail; `app/main.py` `proxied()`/`subscriber()` (lines 157-188) resolve the presented key to the gateway or to one
    service account; `gateway()` (190-198) admits `/xsection` only for the screener service account.
  - Migration `database/migrations/<date>_terminal_owner_service_accounts.sql`: `terminal.subscriber.kind`
    (`person` | `service`), the two service rows, `terminal.usage_hour(subscriber_id, hour_start, files, bytes, PRIMARY KEY
    (subscriber_id, hour_start))` with grants for `terminal_runtime`, and a `$verify$` block.
  - `app/store.py`: for `kind = 'service'`, `UPSERT usage_hour ... RETURNING` with a ceiling (runaway guard) instead of
    `usage()`; the audit row stays.
  - Workers: no code change; Railway variables point the worker's existing `TERMINAL_PROXY_KEY` variable at its own key
    (for example `${{terminal-api.TERMINAL_BACKTEST_KEY}}`).
- **Covers.** Worker/person lock contention; per-service audit and bound; removes the gateway key from the workers, so the
  owner header of T2 can be trusted. **Does not cover.** People's identity (T2).
- **Risks and cost.** Deploy order: terminal-api accepting both old and new keys first, then the worker variables, then the
  old mapping removed; CLI deploys under ERRORS M248, outside the publisher window. Service audit rows at 200 users about
  60,000 a day (INFERENCE: 4,000 jobs × 15 grants), about 1.9 GB at 90 days: a decision whether service rows keep 90 days or
  14 (D-T6). Cost: none at runtime.
- **Verification.** `apps/terminal-api/tests/test_api.py`: `test_service_key_acts_as_its_own_account_and_cannot_name_an_owner`,
  `test_xsection_admits_only_the_screener_service_account`, `test_service_ceiling_refuses_with_its_message`; Backtest E2E
  `verification/backtest/e2e_dev.py`; `access_log` rows per subscriber read back with a role that can read `terminal`.
- **Permanent.** Replaces TEMPORARY U1 for the workers.

### T2 — One terminal subscriber per `owner_key`, through the gateway (P31, first half)

- **Need.** FACT: no per-person quota or audit; one lock for all (`main.py:174-180`, `store.py:45-46`). With external users
  either the 1e9 override stays (no bound: scraping and data-terms risk) or it goes (one heavy user refuses everyone).
- **Class.** Multi-tenant identity collapsed into one account at a gateway.
- **Fix and layer.**
  - edge-bff `app/main.py`: the `session` dependency (265-270) returns the session row's `owner_key` (today always
    `settings.owner`); `forward_terminal` (401-423) sends `x-terminal-proxy-owner: <owner_key>` and never forwards a
    client-supplied one (it builds its headers itself today, line 412, so a browser header cannot pass; keep it so).
  - terminal-api `app/main.py` `subscriber()`: with the gateway key, the owner header is required and mapped through
    `terminal.subscriber.edge_owner_key` (new nullable unique column, same migration as T1); a missing row is created with
    the tier defaults (`INSERT ... ON CONFLICT (edge_owner_key) DO NOTHING`, then `SELECT`), no usable password, `kind
    'person'`. A service key with an owner header is 400.
  - Today this yields one row for the one owner (the current subscriber 2 can be linked by setting its `edge_owner_key`), so
    nothing visible changes; with accounts (P30, on hold) each owner gets its row without a terminal-api change.
  - The 1e9 override moves to that row as before and stays TEMPORARY until T10's values are decided and T4 is live.
- **Covers.** Per-person locks (no cross-user serialisation), quotas and audit; bursts parallelise across people. **Does not
  cover.** Who may sign in (edge-bff accounts, on hold); copying of data a person is allowed to see.
- **Risks and cost.** Trust in the owner header rests on the gateway key being only in edge-bff (T1 first) and on terminal-api
  not being reachable from outside with that key: FACT `BACKTEST_END_TO_END.md:420-421` (the public domain accepts the key
  from anywhere). Decision D-T2: remove terminal-api's public domain (its own subscriber sign-in is not used by EDGE pages,
  which go through edge-bff), or refuse proxied keys on requests that arrived through the public edge. Cost: none.
- **Verification.** `test_api.py`: `test_owner_header_needs_the_gateway_key_and_maps_to_its_own_subscriber`,
  `test_two_owners_have_separate_quotas_locks_and_audit_rows`; a Postgres-backed test (the suite's `FakeStore` cannot hold
  advisory locks or upserts; new `apps/terminal-api/tests/test_store_pg.py` with a disposable database URL, as edge-bff's
  `EDGE_TEST_POSTGRES_URL`): `test_owner_subscriber_is_created_once_under_concurrency`,
  `test_owner_grants_do_not_wait_on_another_owners_lock`. edge-bff `tests/test_terminal.py`:
  `test_gateway_forwards_the_session_owner_and_never_a_client_owner_header`.
- **Permanent.**

### T3 — The subscriber lookup inside the grant, and cached for read-only routes

- **Need.** FACT (section 2.3): about 44,000 lookup transactions in 6.6 days against about 4,400 grants; each proxied request
  opens one transaction and holds a pooled connection only to read the gateway row (`main.py:174-180`).
- **Class.** A per-request database round trip for data that changes rarely.
- **Fix and layer.** terminal-api `app/main.py`, `app/store.py`: grants read and check the subscriber (`active`,
  `expires_at`) inside their own transaction, after the lock; `/manifest`, `/state` and `/logo` use an in-process map key →
  subscriber id kept 60 s.
- **Covers.** About 90 % fewer terminal-api transactions; one round trip less per grant. **Does not cover.** edge-bff's own
  session check.
- **Risks and cost.** A deactivated account still reads manifests, state and logos for up to 60 s (they grant nothing). Cost:
  none.
- **Verification.** `test_api.py`: `test_inactive_account_is_refused_at_the_grant`,
  `test_read_routes_reuse_the_account_for_60_seconds`; the `subscriber_email_key` index-scan rate before and after.
- **Permanent.**

### T4 — One `/bundle` per open, with `refs` and a `have` list

- **Need.** FACT (section 2.2): 4 grants per open, 8 files counted, and bytes counted again for every cached re-open
  (`main.py:340-361` counts every chosen file). The quota therefore measures page loads, not access, and refuses a person who
  only re-opens cached tickers.
- **Class.** Accounting by request instead of by access; many small calls on the critical path.
- **Fix and layer.**
  - terminal-api `app/main.py` `BundleRequest` (69-77): optional `have: list[sha256]` (at most 64) and `refs:
    list['tickers','brokers','logos']`. The answer keeps every file's `sha256`, `bytes`, `rows`, and gives a `url` only for
    files not in `have`; `grant()` counts the granted files and bytes only; the ticker still counts as opened (one audit
    row, `file_count` = files granted). `refs` grants the reference files of the `state.json` index (T5) in the same
    transaction under `quota.REF`.
  - Pages: `apps/edge-bff/terminal/src/data/live.ts` `bundle()` (82-89) sends `have` = the sha256 values of the files it last
    saw for that ticker that are still in IndexedDB, and `refs`; `rack.ts` gains `has(sha)` (a key lookup that does not
    touch `used`). The Backtest page's `apps/edge-bff/backtest/src/api/live.ts` bundles send `have` the same way (CONTRACT
    §10 D-P5 unchanged: the same cache, the same verification).
  - Backward compatible: a client that sends neither field gets today's answer and counting (the backtest worker, until the
    backtest area adopts `have` for its own cache: CONTRACT §2 "Every answer counts its files", review COST-1).
- **Covers.** 1 grant per open; files and bytes counted only on real access; 3 presigns and 3 audit rows less per open.
  **Does not cover.** The session round trip; the frame reload.
- **Risks and cost.** A client lying about `have` only denies itself URLs. Contract change to a route the Backtest reads:
  `BACKTEST_END_TO_END.md` §6.2 and CONTRACT §2 are updated in the same change. Cost: none.
- **Verification.** `test_api.py`: `test_bundle_have_grants_and_counts_only_missing_files`,
  `test_bundle_have_still_counts_the_ticker_as_opened`, `test_bundle_refs_are_granted_in_the_same_transaction`,
  `test_bundle_without_have_or_refs_answers_as_before`; edge-bff `test_terminal.py`:
  `test_gateway_forwards_bundle_have_and_refs_unchanged`; page vitest `terminal/tests/data/live.test.ts` (have list built
  from the cache; one bundle per open).
- **Permanent.**

### T5 — Content-addressed reference files, listed in `state.json`

- **Need.** FACT: `ref/tickers`, `ref/brokers`, `ref/logos` carry no sha256 and are downloaded on every open
  (`BACKTEST_END_TO_END.md:296-297, 718-719`; "Belum" in EXEC-TERMINAL-SPEED); the chart awaits the ticker list
  (`live.ts:161-165` at `15ec418`).
- **Class.** Unversioned objects beside content-addressed ones; a per-open download that never changes the answer.
- **Fix and layer.**
  - Publisher (owned with the Screener branch, which carries the publisher changes): write
    `ref/<name>.<sha16>.json.gz` with the existing deterministic `encode` and list them in `state.json` `refs` = `{name: {key,
    sha256, bytes, rows}}` in the `xsection` index's shape; keep writing the fixed-key copies for old readers; prune like
    `prune_xsection`.
  - terminal-api `app/bucket.py`: `refs_index()` validated like `xsection_index` (lines 21-43); `/state` shows it; `/bundle
    refs` (T4) and `/reference/{name}` presign from it when present.
  - Pages: refs read from IndexedDB by sha256 like data files; the ticker list stops being on the critical path (T6).
- **Covers.** About 54 KB and one bucket round trip per open; names and sectors pinned to the publication. **Does not
  cover.** Logos' image bodies (T9).
- **Risks and cost.** Cross-area: the publisher change must land with the content-key commits (see risk R1). Cost: none.
- **Verification.** Publisher tests (`apps/terminal-publisher/tests/test_publisher.py`): refs keys content-addressed, equal
  bytes give the same key, pruning keeps the previous index; terminal-api: `test_state_lists_refs_and_bundle_refs_presign_only_indexed_keys`.
- **Permanent.**

### T6 — Cache-first boot (TERMINAL-CACHE-FIRST, approved into the plan 2026-10-26, `PLAN.md:879-896`)

- **Need.** INFERENCE: every switch reloads the frame and waits for session → ticker list → bundle before drawing data that is
  usually already in IndexedDB (2.2 of 2.5 s in the 2026-10-26 measurement were that wait).
- **Class.** Data the client holds, drawn only after the server re-confirms it.
- **Fix and layer.** Terminal page:
  - new `apps/edge-bff/terminal/src/data/boot.ts`: a `localStorage` pointer `ml.boot = {login, finished_at, refs: {name:
    sha}, tickers: {T: {price: [sha], broker: [sha], events: [sha]}}}` (at most about 50 tickers, oldest dropped);
  - `live.ts` `liveData()`: after `GET /api/v1/auth/session` answers (its `login` must equal the pointer's, else the pointer
    is dropped), draw the remembered ticker and the ticker list from IndexedDB, and send the one `/bundle` (T4) at the same
    time; if its sha256 values equal the pointer's, nothing more happens; else the new files replace the drawing with an
    "Updating…" mark (the safe form of P24 (a), `06c_page_load_sequence.md` §6c.4 S3);
  - do not await the ticker list before using a remembered ticker (validate it when the list arrives).
  - The frame reload on switch stays (removing it means re-architecting the sections that "take the candles once",
    `main.ts:34-36` at `15ec418`); with this change a reload costs the frame document (4 KB), the session and IndexedDB reads.
- **Covers.** Warm opens and cached switches. **Does not cover.** First opens of a ticker (bucket download), shell costs (P25,
  P26 of the Screener report).
- **Risks and cost.** The open question of the plan item: old data must not show before the session check (shared devices);
  this design draws only after an authenticated answer. M253 lesson: tested with late data. Cost: none.
- **Verification.** vitest `terminal/tests/data/boot.test.ts`: another login's pointer dropped; a pointer whose files are not
  in IndexedDB is not drawn; new sha256 values replace the drawing; smoke with a slow session, slow `/bundle` and a new
  publication; page timing (T12).
- **Permanent.**

### T7 — Verify sha256 and size before drawing (accuracy)

- **Need.** FACT: `download()` draws bytes whose sha256 differs from `/bundle`'s (`apps/edge-bff/terminal/src/data/worker.ts:
  36-42` at `15ec418`; M250 item 5); the size is never checked. The Backtest page and worker refuse such bytes
  (`inflateVerified`, `BACKTEST_END_TO_END.md:293-295`).
- **Class.** A reader trusting unverified bytes while its siblings verify.
- **Fix and layer.** `terminal/src/data/worker.ts` `download()`: `FileRef` carries `bytes`; a downloaded body whose length or
  sha256 differs is refused (`DATA_INTEGRITY`, "A data file did not match its published checksum; reload the page."), not
  drawn and not cached; the page asks one new `/bundle` once before showing it (a content key cannot change, so a mismatch
  means a stale answer or a damaged transfer). `live.ts` passes `f.bytes`.
- **Covers.** Every Terminal chart, flow and event panel. **Does not cover.** Source data errors (M238, M243, K4 remain).
- **Risks and cost.** One sha256 per downloaded file, already computed today for caching. None otherwise.
- **Verification.** vitest `terminal/tests/data/download.test.ts`: mismatched size or hash → error, not cached, not drawn; one
  retry with a new bundle.
- **Permanent.**

### T8 — One publication per page load (accuracy)

- **Need.** INFERENCE from `bucket.py:61-77` and two processes: for up to 60 s after a run, one process can serve the new
  manifests and the other the old; and a page left open across a publication loads IHSG, compare and asset series from the
  new one onto a base series from the old (different last bar).
- **Class.** Mixed versions inside one view.
- **Fix and layer.** terminal-api `/bundle` answers `finished_at` (from `bucket.state()`, already read for the manifest cache);
  `live.ts` keeps the first one and, when a later answer differs, shows "New data was published. Reload to update." (one
  line, no automatic reload while the user draws).
- **Covers.** The 60 s skew window, now and with replicas; long-open pages. **Does not cover.** Data mixed inside the
  publisher's own run (M250 handles that with content keys).
- **Risks and cost.** None measurable.
- **Verification.** `test_api.py`: `test_bundle_answer_names_its_publication`; vitest: a later answer with another
  `finished_at` shows the note and keeps the drawing.
- **Permanent.**

### T9 — terminal-api runtime: healthcheck, pool, replicas, manifest warm-up, logo cache

- **Need.** FACT: no healthcheck path; 1 replica; pool 8 per process against the role's 20; manifests read lazily from `sin`
  after each publication (about 1 s each, `bucket.py:62-64` docstring, `FUTURE_PLAN.md`: first manifest 1.18 s); logos read
  from the bucket on every call (M240: 1.19-2.61 s).
- **Class.** Single instance without readiness; cold per-process caches after a version change; uncached immutable bodies.
- **Fix and layer.**
  - Railway config and `.railway/railway.ts` (terminal-api block, line 158): `healthcheckPath: '/ready'` (exists,
    `main.py:221-227`); at external launch `numReplicas: 2` in `sfo`.
  - `app/config.py` + `app/store.py:24`: `TERMINAL_POOL_MAX` (default 8); 4 with two replicas (2 × 2 × 4 = 16 ≤ 20), or a
    role limit raised by migration.
  - `app/bucket.py` `_fresh()`: on a new `finished_at`, a background thread reads every published ticker's manifest (16 at a
    time; about 1 min) so users do not pay the cold read; later, if the publisher writes one manifest index object per run
    (cross-area; it would also cut the publisher's 7.5-min planning), one GET instead.
  - `app/bucket.py` `logo()`: bodies kept in memory per publication (all logos about 4 MB, `FUTURE_PLAN.md` logo item);
    `main.py:313`: `Cache-Control: private, max-age=31536000, immutable` (the URL carries `?v=<sha>`).
  - D-T2 public domain (see T2).
- **Covers.** Zero-downtime deploys; one replica's crash; first open after a publication; logo latency. **Does not cover.**
  Postgres availability (no HA, no PITR: capacity audit §3.6).
- **Risks and cost.** Second replica about USD 1.2-1.5 a month (section 7); a warm-up thread per process adds about 1,700
  free GETs per publication. With two replicas, `pruned` and the manifest caches stay per process (safe).
- **Verification.** `test_api.py`: `test_pool_size_comes_from_the_environment`,
  `test_manifest_cache_is_warmed_after_a_new_publication`, `test_logo_body_is_cached_per_publication_and_immutable`;
  `railway status` read back (healthcheck, replicas); a deploy while the load test runs shows no 503.
- **Permanent.**

### T10 — Per-owner quotas sized from the page's request pattern, with the four gate parts

- **Need.** Defaults were set for direct subscribers before packs and the Terminal's current page: at 8 files per open
  `files_per_hour` 60 allows 7 opens an hour (FACT arithmetic from section 2.2 and migration `20261025_100:80`).
- **Class.** Limits that count page mechanics instead of access.
- **Fix and layer.** After T4 (counting only granted files), values for the default tier (PROPOSED; D-T1 is the user's):

  | Quota | Today | Proposed | Reasoning (INFERENCE) |
  |---|---|---|---|
  | `tickers_per_hour` | 30 | 60 | a browsing user switching every minute for an hour |
  | `tickers_per_day` | 150 | 200 | about 24 % of the 845 tickers a day; the whole universe takes 5 days and shows in the audit |
  | `files_per_hour` | 60 | 300 | 60 first opens × 5 files; cached files no longer count |
  | `megabytes_per_day` | 300 | 500 | granted bytes only: about 150 average or 170 large-cap first opens |
  | `history_per_hour` | 20 | 20 | the Terminal page does not call `/history` |
  | `url_ttl_seconds` | 120 | 120 | the page downloads at once; fewer URLs with T4 |

  The 1e9 override is removed for people when T2, T4 and these values are live; service accounts get their ceilings (T1).
- **Gate parts (AGENTS.md "Gates and evidence").** (a) Rule visible before: `/bundle` answers `usage` (`tickers_day: [used,
  limit, resets_at]` and the others) and the page shows "N new tickers left today" when under 20 % remains. (b) How to pass:
  tickers already opened in the window stay available; new ones from `resets_at`. (c) Right: re-opening BBCA after the limit
  (already counted) loads; wrong: a 201st distinct ticker. (d) Message (`app/quota.py:23-25` `Refusal.message`, extended):
  "Daily limit of new tickers reached (200 distinct tickers in 24 hours). Tickers you already opened today still load; new
  tickers open again from 14:05 WIB." `resets_at` is computed in the same aggregate (the earliest moment a counted ticker
  leaves the window).
- **Covers.** Per-person bound and evidence for the data terms. **Does not cover.** Whether the terms allow external display
  at all (E6/MU2, UNKNOWN), or copying of what a person may see.
- **Risks and cost.** Values too low frustrate users, too high weaken the anti-bulk bound; measured use after launch (T12)
  resizes them. Cost: none.
- **Verification.** `test_api.py`: `test_quota_refusal_names_the_limit_and_the_reset_time`,
  `test_bundle_answers_usage_for_the_page`; existing `test_quota_distinct_tickers_stops_a_crawl` kept.
- **Mechanism permanent; values TEMPORARY until the user sets tiers (P29 "paket atau kuota berbeda per user").**

### T11 — One bundle per added asset

- **Need.** FACT: an added asset asks `/bundle` twice (price, then broker; `live.ts:212-227` at `15ec418`).
- **Fix and layer.** `live.ts` `loadAsset`/`loadAssetFlow`: one bundle with `['price', 'broker']` and `have`; the Web Worker
  already answers in stages (price first).
- **Covers.** One grant per asset. **Risks and cost.** None. **Verification.** vitest: an asset costs one bundle.
  **Permanent.**

### T12 — Measurements that settle the open numbers

1. `?perf=1` once from Indonesia (the user), on a cold and a warm open and a ticker switch: settles U-T1, U-T2 and the region
   question (4.3).
2. `verification/terminal_api/page_timing_dev.py` (new, from `verification/backtest/page_timing_dev.py`): tab open cold and
   warm, cached and uncached switch, requests and grants per open, bytes; before and after T4-T7.
3. Multi-owner load test of `/bundle` from a temporary private-network job service (precedent `feature-05-06-job`,
   `RAILWAY_CHANGELOG.md:4249`), 10 / 50 / 200 synthetic owners with the T2 header, steady and burst (all at once): p50,
   p95, max grant time, terminal-api CPU, pool waits, Postgres CPU; before T2 (one account) and after.
4. After launch, weekly: grants and distinct tickers per owner per day (from `access_log` with a role that can read
   `terminal`) to resize T10.

---

## 6. Order of work and dependencies (PROPOSED; each step needs the user's "go")

| Step | Items | Depends on | Why first |
|---|---|---|---|
| 0 | T12.1 (Indonesia reading), T12.2 baseline | — | numbers before changes |
| 1 | T7, T9 healthcheck, T3, T1 | none (T1 coordinates with the Backtest and Screener areas for variables) | accuracy; isolates worker traffic; no user-visible change |
| 2 | T5, T4, T11 | T5 needs the publisher content-key commits on the branch (R1) | one grant per open; quota by access |
| 3 | T6, T8 | T4, T5 | the per-open latency |
| 4 | T2, T10 (override removed for people), D-T2 | T1, T4 | before the first external user |
| 5 | T9 second replica, pool, warm-up, logo cache; T12.3 | T2 | availability, then trigger thresholds |

---

## 7. Cost per month (INFERENCE from FACT inputs)

**Profile (INFERENCE, to replace with P29 numbers):** per daily user and trading day 50 ticker opens (30 distinct), 5 IHSG or
compare loads, 2 asset adds, 20 EDGE shell loads; 21 trading days; 30 % of daily users active at the peak.

**Inputs.** terminal-api replica USD 1.2 (7-day metrics: 0.114 GB × 10 + 0.003 vCPU × 20); publisher USD 0.75 (7-day metrics
scaled: 34.6 GB-hours, 2.0 vCPU-hours, 4.3 GB upload egress); bucket about 0.7 GB × 0.015 = USD 0.01; edge-bff egress per
user-month: opens 50 × about 9 KB (frame 4.1 KB, bundle and reference answers, session) + logos about 0.15 MB/day + shell 20 ×
103.6 KB = about 2.7 MB a day, 56 MB a month (USD 0.003; the shell is shared with the other tabs); `access_log` 357 B per row
kept 90 days; grant CPU about 10 ms.

| | 10 users | 50 users | 200 users |
|---|---|---|---|
| Grants (audit rows) per day, today / T4 | 2,090 / 570 | 10,450 / 2,850 | 41,800 / 11,400 |
| `access_log` at 90 days (every day counted as a trading day: an upper bound), today / T4 | 0.07 / 0.02 GB | 0.34 / 0.09 GB | 1.34 / 0.37 GB |
| terminal-api | 1.2 (1 replica) / 2.4 (2) | 1.2 / 2.4 | 1.3 / 2.4 (grant CPU about 0.07 / 0.02) |
| publisher | 0.75 | 0.75 | 0.75 |
| bucket storage | 0.01 | 0.01 | 0.01 |
| edge-bff egress (Terminal and shell) | 0.03 | 0.14 | 0.56 |
| Postgres (volume and CPU of grants) | 0.01 / 0.00 | 0.05 / 0.02 | 0.21 / 0.06 |
| **Total USD/month, today's design / proposed** | **≈ 2.0 / 3.2** | **≈ 2.2 / 3.3** | **≈ 2.8 / 3.8** |
| Per user | 0.20 / 0.32 | 0.04 / 0.07 | 0.014 / 0.019 |

The proposals cost about USD 1.2 a month more, all of it the second terminal-api replica (availability, D-T3); everything
else they change lowers rows, grants and requests. Not counted: the backtest worker's grants (its area), the EDGE shell's
fixed cost, Railway's Pro fee. For comparison: a CDN would cost USD 0-20 a month and save nothing billable; streaming files
through a service would add about USD 4 a month at 200 users (4.1).

---

## 8. Load time for 10 / 50 / 200 users (INFERENCE unless marked)

**Steady state.** Peak opens: 0.1 / 0.5 / 2 a second (10 / 50 / 200 users). Today's design: 4 grants per open plus the
workers on one lock. Hold time per grant ≈ 2 ms + about 0.26 ms per 1,000 rows of the account's last 24 h (from FACT 0.85 ms at
3,271 rows); rows per day ≈ 2,090 + 3,000 / 10,450 + 15,000 / 41,800 + 60,000 (people + backtest worker) → hold about 3 / 9 /
28 ms; at 0.5 / 2.5 / 10 grants a second (people and worker) the lock is busy under 1 % / about 2 % / about 29 %, a mean
extra wait (M/D/1) of about 0 / 0.1 / 6 ms. So steady load times equal the single-user
values in both designs.

**Bursts (all users active at the peak open at the same moment).** Today: grants × about 25-35 ms each, the effective rate the
FACT burst test shows (20 concurrent: max 0.71 s), plus the larger hold time: 3 users → 12 grants → ≈ 0.4 s; 15 users → 60
grants → ≈ 1.5-2.1 s; 60 users → 240 grants → ≈ 6-8 s for the last. Proposed (T2 per-owner locks, T4 one grant per open): 3 /
15 / 60 grants spread over 16 database connections and edge-bff's 6-connection session checks → ≈ 0.05 / 0.1 / 0.2-0.3 s.

**Per-open path (measured basis: the US sandbox, `x-railway-edge: iad1`; Indonesia UNKNOWN).**

| Scenario | Today | Proposed (T4-T7) | Basis |
|---|---|---|---|
| Tab first open, empty browser | 2.28 s (FACT) | ≈ 2.0-2.3 s | the bucket's per-object TTFB (0.72-1.42 s from the US) dominates; one call less before it |
| Tab open, same publication, files cached | 1.77 s (FACT) | ≈ 1.3-1.5 s | shell and frame (Backtest first render 1.12 s warm, FACT) + session + IndexedDB |
| Ticker switch, ticker cached | ≈ 1.8-2.5 s (FACT 2.5 s on 2026-10-26, before the edge-bff pool) | ≈ 0.7-0.9 s | frame 4 KB + session + IndexedDB; no bucket or terminal-api call before drawing |
| Ticker switch, first open of the ticker | ≈ 2.0-2.5 s | ≈ 1.5-2.2 s from the US; ≈ 1.0-1.4 s from Indonesia if the `sin` TTFB is 0.1-0.4 s (UNKNOWN) | bundle + one bucket round trip |
| First open after the evening publication (price pack and current broker year changed) | as "first open" for 2 of 5 files, plus up to 1 s cold manifest | ≈ cached switch, then "Updating…" within one bundle + one download | T6 draws the cached version first; T9 warm-up removes the manifest read |

For users in Indonesia (INFERENCE, assuming about 0.2 s per `sfo` round trip through Railway's Singapore edge): today a cached
switch makes 3-4 sequential `sfo` round trips plus one bucket round trip; proposed, 2 `sfo` round trips before drawing.

---

## 9. Risks (beyond each item)

- **R1 (accuracy).** FACT: HEAD's `apps/terminal-publisher/publisher.py:514, 533` writes per-ticker files and packs under fixed
  keys; the live publisher (log `gc` lines) has the M250 content keys from PR #41 (`6051f4d`, `cf60fed`), which `PLAN.md` says
  are cherry-picked into this branch, but `git merge-base --is-ancestor 6051f4d HEAD` is false. Deploying the publisher from
  HEAD before the cherry-pick would bring back `DATA_INTEGRITY` during every run for the Backtest and, without T7, silently
  mismatched Terminal charts. Owner: the Screener/publisher work; check before its deploy.
- **R2.** The deployed Terminal page (`15ec418`) differs from HEAD's (`loadAsset`, `loadAssetFlow`, `rack.ts`): changes are
  built on `main`'s version (the capacity audit's MP-11 note says the same).
- **R3.** T4 and T5 change routes the Backtest reads; `BACKTEST_END_TO_END.md` §6.2/§11.1 and CONTRACT §2/§12 (U1) are updated
  with them (AGENTS.md).
- **R4.** terminal-api and the publisher deploy by CLI upload (`BACKTEST_END_TO_END.md:657-661`): the M248 procedure, outside
  00:00-01:00 and 12:00-13:05 UTC.
- **R5.** `.railway/railway.ts` does not declare `TERMINAL_PROXY_*` (capacity audit §2.1): `railway config pull --force` before
  any T1/T9 Railway change.

---

## 10. Unknowns (with the check that settles each)

| # | Unknown | Check |
|---|---|---|
| U-T1 | Load times from Indonesia | T12.1 |
| U-T2 | Bucket TTFB from Indonesia to `sin`; whether Tigris serves repeated reads from nearer copies | T12.1 request log (`?perf=1` per-file times) |
| U-T3 | Whether Railway's edge caches `public`/`immutable` answers | two timed GETs of a hashed asset with cache headers inspected |
| U-T4 | How the private network spreads edge-bff's pooled connections over two terminal-api replicas (06d M-U2) | T12.3 per-replica request counts |
| U-T5 | Real Terminal use per person (opens, distinct tickers, bytes) | P29 numbers; T12.4 after launch |
| U-T6 | Whether the data may be shown to external users and under which limits (E6, MU2) | the user, per source |
| U-T7 | Source of publisher deployment `b8b51052` (not in any branch's `RAILWAY_CHANGELOG.md`); its log shows content keys (`gc`) and no `xsection` line | Railway deployment metadata; the Screener work's records |
| U-T8 | Exact bytes per ticker bundle (average and large caps) | manifests read with the gateway key in T12.2/T12.3 |

## 11. Decisions for the user

- **D-T1** Quota values per person (T10 table), and whether they differ per plan.
- **D-T2** Remove terminal-api's public domain (or refuse gateway and service keys arriving through it) before the owner
  header is trusted.
- **D-T3** A second terminal-api replica from the first external user (about USD 1.2 a month).
- **D-T4** TERMINAL-CACHE-FIRST's open question: draw cached data only after the first authenticated answer (recommended,
  T6), or before it.
- **D-T5** Keep services in `sfo` and the bucket in `sin` until the Indonesian reading (recommended).
- **D-T6** Audit retention for service-account rows: 90 days as for people (user 2026-10-26) or shorter.

## 12. Evidence index (read-only commands)

- `npx -y @railway/cli@5.71.0 status --json` (regions, replicas, healthcheck paths, deployment ids, domains; saved without
  secrets as `mu_runtime_status.json` in the scratchpad).
- `railway metrics -s <terminal-api|edge-bff|backtest-worker|terminal-publisher> --since 7d --cpu --memory --network --json
  --raw`; `railway metrics -s edge-bff --since 16h --http --method <M> --path <P>` for `/api/terminal/v1/bundle`,
  `/api/terminal/v1/reference/tickers`, `/api/v1/auth/session`.
- `railway logs -s terminal-publisher -n 400` (2026-10-28 12:00 UTC run: plan, `gc`, progress, `done`).
- `curl -D - -H 'Accept-Encoding: gzip, br' https://edge-bff-dev.up.railway.app/terminal` and `/terminal-app/`.
- pgweb: `pg_stat_user_tables` and `pg_stat_user_indexes` for schema `terminal`, `pg_roles`, `pg_settings`,
  `pg_postmaster_start_time()`; reference-size estimates built from `IDX_Stock_Universe` and `IDX_Broker_Profile` rows.
- git: `git diff 6f318ea HEAD --stat -- apps/terminal-api/app`; `git show 15ec418:apps/edge-bff/terminal/src/data/{live,worker}.ts`;
  `git merge-base --is-ancestor 6051f4d HEAD`; `git show screener-pr41-integration:apps/terminal-publisher/publisher.py`.
